"""
Naive backtest of the relationship engine on real federal award recipients.

USAspending.gov publishes every recipient of federal grants with its address,
its registered parent organisation (from SAM), and the alternate names it has
appeared under.  That gives three real tests with no licensed data:

1. Affiliate detection.  For each child recipient, hide the parent label and ask
   the engine to pick the true parent out of a line-up of decoy parents using
   only names and addresses.  Recall on true parents and false-flag rate on
   decoys measure the identifier-only layer on real organisations.  Decoys are
   drawn half from the same state, so "same city" is not a giveaway.

2. In-context coincidence rates.  How often do two grant recipients from
   DIFFERENT corporate families in the same city share a building or a suite?
   This is the u probability the Colorado registry could not give us: the
   population is actual award recipients, not random companies.

3. Alias resolution.  Each recipient's alternate names are the same entity under
   another spelling.  What share does the name normaliser link?  This measures
   how much "same entity" detection can rely on names at all.

    cd backend
    python -m benchmarks.backtest_usaspending --pages 40 --max-children 300 --cache /path/to/cache
    python -m benchmarks.backtest_usaspending --evaluate-only --cache /path/to/cache --json report.json

Rate-friendly: one request at a time, retries with backoff, everything cached.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.agent.relationships import (
    EntityRecord,
    NullProvider,
    RelationshipEngine,
    canonical_address,
    canonical_org_name,
    org_name_similarity,
)

API = "https://api.usaspending.gov/api/v2"
UA = {"User-Agent": "veritas-relationship-backtest/0.1", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_json(url: str, body: Optional[Dict[str, Any]] = None, retries: int = 6) -> Optional[Dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA, method="POST" if body is not None else "GET")
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read()
            if raw:
                return json.loads(raw)
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                return None
            print(f"    retry {attempt + 1}/{retries} after error: {exc}", file=sys.stderr)
        time.sleep(delay)
        delay = min(delay * 2, 30)
    return None


class Cache:
    def __init__(self, directory: str) -> None:
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "usaspending_recipients.json")
        self.data: Dict[str, Any] = {"list": [], "details": {}}
        if os.path.exists(self.path):
            with open(self.path) as fh:
                self.data = json.load(fh)

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh)
        os.replace(tmp, self.path)


def collect_recipients(cache: Cache, pages: int, start_page: int, limit: int) -> None:
    seen = {r["id"] for r in cache.data["list"]}
    for page in range(start_page, start_page + pages):
        res = fetch_json(f"{API}/recipient/", {"order": "desc", "sort": "amount", "page": page, "limit": limit,
                                               "award_type": "grants"})
        if not res or not res.get("results"):
            print(f"  page {page}: no results, stopping", file=sys.stderr)
            break
        new = [r for r in res["results"] if r["id"] not in seen]
        cache.data["list"].extend(new)
        seen.update(r["id"] for r in new)
        cache.save()
        print(f"  page {page}: +{len(new)} recipients (total {len(seen)})", file=sys.stderr)
        if not res["page_metadata"].get("hasNext"):
            break
        time.sleep(0.4)


def fetch_detail(cache: Cache, rid: str) -> Optional[Dict[str, Any]]:
    if rid in cache.data["details"]:
        return cache.data["details"][rid]
    d = fetch_json(f"{API}/recipient/duns/{rid}/")
    if d is not None:
        d = {k: d.get(k) for k in ("name", "duns", "uei", "recipient_level", "location", "parents",
                                   "alternate_names", "business_types")}
    cache.data["details"][rid] = d
    cache.save()
    time.sleep(0.3)
    return d


def build_dataset(cache: Cache, max_children: int) -> None:
    children = [r for r in cache.data["list"] if r["recipient_level"] == "C"]
    done = 0
    for r in children:
        if done >= max_children:
            break
        d = fetch_detail(cache, r["id"])
        if not d or not d.get("location"):
            continue
        for p in d.get("parents") or []:
            if p.get("parent_duns") == d.get("duns") or not p.get("parent_id"):
                continue
            fetch_detail(cache, p["parent_id"])
        done += 1
        if done % 20 == 0:
            print(f"  children processed: {done}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def address_of(detail: Dict[str, Any]) -> Optional[str]:
    loc = detail.get("location") or {}
    if not loc.get("address_line1") or loc.get("country_code") not in (None, "USA", "US"):
        return None
    line = " ".join(x for x in (loc.get("address_line1"), loc.get("address_line2")) if x)
    return f"{line}, {loc.get('city_name') or ''}, {loc.get('state_code') or ''} {loc.get('zip') or ''}".strip()


def record_of(detail: Dict[str, Any], role: str) -> Optional[EntityRecord]:
    addr = address_of(detail)
    if not detail.get("name") or not addr:
        return None
    return EntityRecord(name=detail["name"], kind="organization", role=role, addresses=[addr],
                        address_types={addr: "commercial"}, sources=["usaspending"])


def family_of(detail: Dict[str, Any]) -> str:
    """Corporate family key: the ultimate parent's DUNS, else own DUNS."""
    others = [p.get("parent_duns") for p in (detail.get("parents") or []) if p.get("parent_duns") != detail.get("duns")]
    return others[0] if others else (detail.get("duns") or detail.get("name") or "")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

async def affiliate_test(cache: Cache, decoys: int, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    details = cache.data["details"]
    parents_by_id = {rid: d for rid, d in details.items() if d and d.get("recipient_level") == "P" and address_of(d)}
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for rid, d in details.items():
        if not d or d.get("recipient_level") != "C" or not address_of(d):
            continue
        for p in d.get("parents") or []:
            if p.get("parent_duns") == d.get("duns"):
                continue
            pd = parents_by_id.get(p.get("parent_id"))
            if pd and canonical_org_name(pd["name"]) != canonical_org_name(d["name"]):
                pairs.append((d, pd))
                break
    engine = RelationshipEngine(NullProvider())
    outcomes = []
    signal_hits: collections.Counter = collections.Counter()
    decoy_hits: collections.Counter = collections.Counter()
    share_any = 0
    for child, parent in pairs:
        child_state = (child.get("location") or {}).get("state_code")
        same_state = [p for p in parents_by_id.values() if p is not parent and (p.get("location") or {}).get("state_code") == child_state
                      and family_of(p) != family_of(child)]
        other = [p for p in parents_by_id.values() if p is not parent and family_of(p) != family_of(child)]
        pool = rng.sample(same_state, min(len(same_state), decoys // 2)) + \
               rng.sample(other, min(len(other), decoys - min(len(same_state), decoys // 2)))
        candidates = [parent] + pool
        recs = [record_of(c, "vendor") for c in candidates]
        applicant = record_of(child, "applicant")
        if applicant is None or recs[0] is None:
            continue
        recs = [r for r in recs if r is not None]
        result = await engine.analyze(applicant, recs)
        confirmed = {canonical_org_name(f.counterparty): f for f in result.findings}
        review = {canonical_org_name(f.counterparty): f for f in result.review_recommended}
        pk = canonical_org_name(parent["name"])
        band = "confirmed" if pk in confirmed else "review" if pk in review else "none"
        f = confirmed.get(pk) or review.get(pk)
        if f:
            for s in f.signals:
                signal_hits[s["signal"]] += 1
        ca, cp = canonical_address(applicant.addresses[0]), canonical_address(recs[0].addresses[0])
        shares = bool(ca and cp and ca.base == cp.base)
        share_any += shares
        for decoy in candidates[1:]:
            dk = canonical_org_name(decoy["name"])
            if dk in confirmed:
                decoy_hits["confirmed"] += 1
                for s in confirmed[dk].signals:
                    decoy_hits[f"signal:{s['signal']}"] += 1
            elif dk in review:
                decoy_hits["review"] += 1
            else:
                decoy_hits["none"] += 1
        outcomes.append({"child": child["name"], "parent": parent["name"], "band": band,
                         "shares_building": shares, "probability": f.probability if f else None,
                         "type": f.relationship_type if f else None, "decoys": len(candidates) - 1})
    n = len(outcomes)
    conf = sum(1 for o in outcomes if o["band"] == "confirmed")
    rev = sum(1 for o in outcomes if o["band"] == "review")
    shared_and_conf = sum(1 for o in outcomes if o["shares_building"] and o["band"] == "confirmed")
    total_decoys = sum(decoy_hits[k] for k in ("confirmed", "review", "none"))
    return {
        "child_parent_pairs": n,
        "true_parent_confirmed": conf, "true_parent_review": rev, "true_parent_missed": n - conf - rev,
        "recall_confirmed": round(conf / max(1, n), 3),
        "recall_confirmed_or_review": round((conf + rev) / max(1, n), 3),
        "pairs_sharing_a_building": share_any,
        "recall_when_building_shared": round(shared_and_conf / max(1, share_any), 3),
        "decoy_candidates": total_decoys,
        "decoys_confirmed": decoy_hits["confirmed"], "decoys_review": decoy_hits["review"],
        "decoy_false_flag_rate": round(decoy_hits["confirmed"] / max(1, total_decoys), 4),
        "decoy_signals_when_confirmed": {k[7:]: v for k, v in decoy_hits.items() if k.startswith("signal:")},
        "signals_on_true_parents": dict(signal_hits),
        "examples_confirmed": [o for o in outcomes if o["band"] == "confirmed"][:8],
        "examples_missed_sharing_building": [o for o in outcomes if o["shares_building"] and o["band"] != "confirmed"][:5],
    }


def in_context_u(cache: Cache) -> Dict[str, Any]:
    details = [d for d in cache.data["details"].values() if d and address_of(d)]
    by_city: Dict[str, List[Tuple[str, str, str]]] = collections.defaultdict(list)
    for d in details:
        ca = canonical_address(address_of(d))
        loc = d.get("location") or {}
        if ca:
            by_city[f"{(loc.get('city_name') or '').lower()}|{loc.get('state_code')}"].append((family_of(d), ca.base, ca.full))
    pairs = same_base = same_full = 0
    for rows in by_city.values():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if rows[i][0] == rows[j][0]:
                    continue  # same corporate family: not an unrelated pair
                pairs += 1
                if rows[i][1] == rows[j][1]:
                    same_base += 1
                    if rows[i][2] == rows[j][2]:
                        same_full += 1
    return {
        "recipients_with_address": len(details),
        "unrelated_same_city_pairs": pairs,
        "u_same_building_in_context": round(same_base / max(1, pairs), 6),
        "u_same_address_in_context": round(same_full / max(1, pairs), 6),
        "reference": {"colorado_city_conditioned": {"same_building": 0.000255, "same_address": 0.00051},
                      "engine_defaults": {"same_building": 0.01, "same_address": 0.001}},
    }


def alias_test(cache: Cache) -> Dict[str, Any]:
    exact = similar = total = 0
    unlinked_examples = []
    for d in cache.data["details"].values():
        if not d:
            continue
        primary = d.get("name") or ""
        for alias in d.get("alternate_names") or []:
            if not alias or alias.upper() == "MULTIPLE RECIPIENTS" or alias.upper() == primary.upper():
                continue
            total += 1
            if canonical_org_name(alias) == canonical_org_name(primary):
                exact += 1
            elif org_name_similarity(alias, primary) >= 0.6:
                similar += 1
            elif len(unlinked_examples) < 8:
                unlinked_examples.append({"primary": primary, "alias": alias})
    return {"alias_pairs": total, "linked_exact_canonical": exact, "linked_similar": similar,
            "share_linked": round((exact + similar) / max(1, total), 3), "unlinked_examples": unlinked_examples}


def print_report(rep: Dict[str, Any]) -> None:
    a = rep["affiliate_test"]
    print("\n=== 1. Affiliate detection: pick the registered parent out of a line-up, names + addresses only ===")
    print(f"child/parent pairs: {a['child_parent_pairs']}   confirmed {a['true_parent_confirmed']}  review {a['true_parent_review']}  missed {a['true_parent_missed']}")
    print(f"recall (confirmed): {a['recall_confirmed']}   recall (confirmed or review): {a['recall_confirmed_or_review']}")
    print(f"pairs where child and parent share a building: {a['pairs_sharing_a_building']}  -> confirmed in {a['recall_when_building_shared']*100:.0f}% of those")
    print(f"decoy parents: {a['decoy_candidates']}   confirmed {a['decoys_confirmed']}  review {a['decoys_review']}   false-flag rate {a['decoy_false_flag_rate']}")
    print(f"signals on true parents: {a['signals_on_true_parents']}")
    if a["decoy_signals_when_confirmed"]:
        print(f"signals behind decoy false flags: {a['decoy_signals_when_confirmed']}")
    for o in a["examples_confirmed"][:5]:
        print(f"  ✓ {o['child']}  ->  {o['parent']}  ({o['type']}, {o['probability']})")
    for o in a["examples_missed_sharing_building"][:3]:
        print(f"  ✗ shares building but not confirmed: {o['child']}  ->  {o['parent']}  (band {o['band']})")
    u = rep["in_context_u"]
    print("\n=== 2. Coincidence rates among UNRELATED grant recipients in the same city ===")
    print(f"recipients: {u['recipients_with_address']}   unrelated same-city pairs: {u['unrelated_same_city_pairs']}")
    print(f"u same building: {u['u_same_building_in_context']}   (Colorado registry {u['reference']['colorado_city_conditioned']['same_building']}, engine default {u['reference']['engine_defaults']['same_building']})")
    print(f"u same address : {u['u_same_address_in_context']}   (Colorado registry {u['reference']['colorado_city_conditioned']['same_address']}, engine default {u['reference']['engine_defaults']['same_address']})")
    al = rep["alias_test"]
    print("\n=== 3. Alias resolution: does the name normaliser link a recipient's alternate names? ===")
    print(f"alias pairs: {al['alias_pairs']}   exact canonical match {al['linked_exact_canonical']}   similar {al['linked_similar']}   linked share {al['share_linked']}")
    for ex in al["unlinked_examples"][:5]:
        print(f"  not linked: '{ex['primary']}'  vs  '{ex['alias']}'")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True, help="directory for the cached download")
    ap.add_argument("--pages", type=int, default=30)
    ap.add_argument("--start-page", type=int, default=2, help="skip page 1 (the very largest recipients)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-children", type=int, default=250)
    ap.add_argument("--decoys", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--evaluate-only", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    cache = Cache(args.cache)
    if not args.evaluate_only:
        print("collecting recipient list...", file=sys.stderr)
        collect_recipients(cache, args.pages, args.start_page, args.limit)
        print("fetching child and parent details...", file=sys.stderr)
        build_dataset(cache, args.max_children)
    rep = {
        "affiliate_test": asyncio.run(affiliate_test(cache, args.decoys, args.seed)),
        "in_context_u": in_context_u(cache),
        "alias_test": alias_test(cache),
    }
    print_report(rep)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(rep, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
