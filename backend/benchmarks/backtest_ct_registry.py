"""
Backtest the relationship engine on Connecticut's public business registry,
which publishes every business's principals with their RESIDENCE addresses.

That residence address is what makes this a real test of identity resolution:

  * Two businesses whose principal has the same name AND the same residence are,
    with high confidence, controlled by the same person.  These are the positives.
  * Two businesses whose principals share a full name but live at different
    addresses are, with high confidence, two different people.  These are the
    hard negatives: the engine must not call them common control.
  * Unrelated businesses in the same city are the decoys.

The engine is given only what a grant application would carry (business names
and business addresses).  It has to find the shared principal through the
registry provider and then decide, from the principal's residence records,
whether the two same-named principals are one person.

Also measured: how often two unrelated same-city businesses have principals
who merely share a full name.  That is the in-context coincidence rate behind
the shared_officer_name and same_person_name signals.

    cd backend
    python -m benchmarks.backtest_ct_registry --cache /path/to/cache --principals 120000
    python -m benchmarks.backtest_ct_registry --cache /path/to/cache --evaluate-only --json report.json

Data: data.ct.gov datasets ka36-64k6 (principals) and n7gp-d28j (business master).
No API key is needed; the fetcher paces itself and caches everything.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.relationships import (
    EntityRecord,
    RelationshipEngine,
    canonical_address,
    canonical_org_name,
    person_key,
)

PRINCIPALS = "https://data.ct.gov/resource/ka36-64k6.json"
MASTER = "https://data.ct.gov/resource/n7gp-d28j.json"
UA = {"User-Agent": "veritas-relationship-backtest/0.1", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch(url: str, params: Dict[str, Any], retries: int = 6) -> Optional[List[Dict[str, Any]]]:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"    retry {attempt + 1}/{retries}: {exc}", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 30)
    return None


class Cache:
    def __init__(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "ct_registry.json")
        self.data: Dict[str, Any] = {"principals": [], "masters": {}}
        if os.path.exists(self.path):
            with open(self.path) as fh:
                self.data = json.load(fh)

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh)
        os.replace(tmp, self.path)


def collect_principals(cache: Cache, target: int, page: int = 20000) -> None:
    have = len(cache.data["principals"])
    while have < target:
        rows = fetch(PRINCIPALS, {
            "$select": "business_id,firstname,lastname,name__c,designation,business_street_address_1,business_city,"
                       "business_state,business_zip_code,residence_street_address_1,residence_city,residence_state,residence_zip_code",
            "$where": "lastname IS NOT NULL AND residence_street_address_1 IS NOT NULL AND residence_state='CT'",
            "$order": "business_id,lastname,firstname",
            "$limit": min(page, target - have), "$offset": have,
        })
        if not rows:
            break
        cache.data["principals"].extend(rows)
        have = len(cache.data["principals"])
        cache.save()
        print(f"  principals: {have}", file=sys.stderr)
        time.sleep(0.5)


def collect_masters(cache: Cache, business_ids: List[str], batch: int = 50) -> None:
    missing = [b for b in business_ids if b not in cache.data["masters"]]
    for i in range(0, len(missing), batch):
        chunk = missing[i:i + batch]
        quoted = ",".join("'" + b.replace("'", "") + "'" for b in chunk)
        rows = fetch(MASTER, {
            "$select": "id,name,business_type,status,billingstreet,billingcity,billingstate,billingpostalcode,"
                       "date_registration,dissolution_date,naics_code,citizenship",
            "$where": f"id in({quoted})", "$limit": batch,
        })
        if rows is None:
            print("  master fetch failed for a batch; continuing", file=sys.stderr)
            continue
        found = {r["id"]: r for r in rows}
        for b in chunk:
            cache.data["masters"][b] = found.get(b)
        cache.save()
        print(f"  masters: {len(cache.data['masters'])}", file=sys.stderr)
        time.sleep(0.4)


# ---------------------------------------------------------------------------
# Building the labelled pairs
# ---------------------------------------------------------------------------

def residence_of(p: Dict[str, Any]) -> Optional[str]:
    if not p.get("residence_street_address_1"):
        return None
    return f"{p['residence_street_address_1']}, {p.get('residence_city') or ''}, {p.get('residence_state') or ''} {p.get('residence_zip_code') or ''}".strip()


def business_address(m: Dict[str, Any]) -> Optional[str]:
    if not m or not m.get("billingstreet"):
        return None
    return f"{m['billingstreet']}, {m.get('billingcity') or ''}, {m.get('billingstate') or ''} {m.get('billingpostalcode') or ''}".strip()


def person_name(p: Dict[str, Any]) -> str:
    return f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip() or (p.get("name__c") or "")


def build_pairs(cache: Cache, max_positive: int, max_hard_negative: int, seed: int) -> Dict[str, Any]:
    """Group principals into (name, residence) identities and emit labelled business pairs."""
    rng = random.Random(seed)
    by_identity: Dict[Tuple[str, str], Set[str]] = collections.defaultdict(set)
    by_name: Dict[str, Set[Tuple[str, str]]] = collections.defaultdict(set)
    for p in cache.data["principals"]:
        key = person_key(person_name(p))
        res = residence_of(p)
        ca = canonical_address(res) if res else None
        if not key or not ca or len(key.split()) < 2:
            continue
        ident = (key, ca.base)
        by_identity[ident].add(p["business_id"])
        by_name[key].add(ident)

    positives: List[Tuple[str, str, str]] = []          # (biz_a, biz_b, person key)
    for (key, _), bizs in by_identity.items():
        if len(bizs) >= 2:
            a, b = sorted(bizs)[:2]
            positives.append((a, b, key))
    rng.shuffle(positives)
    positives = positives[:max_positive]

    hard_negatives: List[Tuple[str, str, str]] = []     # same name, different residence
    for key, idents in by_name.items():
        if len(idents) < 2:
            continue
        idents_l = sorted(idents)
        a_biz = sorted(by_identity[idents_l[0]])[0]
        b_biz = sorted(by_identity[idents_l[1]])[0]
        if a_biz != b_biz:
            hard_negatives.append((a_biz, b_biz, key))
    rng.shuffle(hard_negatives)
    hard_negatives = hard_negatives[:max_hard_negative]

    return {"positives": positives, "hard_negatives": hard_negatives,
            "identities": len(by_identity), "multi_business_identities": sum(1 for b in by_identity.values() if len(b) >= 2),
            "names_with_multiple_identities": sum(1 for i in by_name.values() if len(i) >= 2)}


# ---------------------------------------------------------------------------
# Registry provider over the cache
# ---------------------------------------------------------------------------

class CTRegistryProvider:
    """RelationshipDataProvider backed by the cached Connecticut registry.

    enrich_organization: business master + its principals as officers.
    enrich_person: the principal's residence; when several principals share the
    name, the address hint (the listing business's address) selects the row
    whose business matches; if that fails and the candidates live at different
    residences, return None rather than guess.
    """

    def __init__(self, cache: Cache) -> None:
        self.masters = {k: v for k, v in cache.data["masters"].items() if v}
        self.by_org: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for m in self.masters.values():
            self.by_org[canonical_org_name(m["name"])].append(m)
        self.principals_by_biz: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        self.principals_by_key: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for p in cache.data["principals"]:
            self.principals_by_biz[p["business_id"]].append(p)
            self.principals_by_key[person_key(person_name(p))].append(p)
        self.biz_by_addr_base: Dict[str, List[str]] = collections.defaultdict(list)
        for bid, m in self.masters.items():
            addr = business_address(m)
            ca = canonical_address(addr) if addr else None
            if ca:
                self.biz_by_addr_base[ca.base].append(bid)

    def record_for_business(self, bid: str, role: str) -> Optional[EntityRecord]:
        m = self.masters.get(bid)
        addr = business_address(m) if m else None
        if not m or not addr:
            return None
        return EntityRecord(name=m["name"], kind="organization", role=role, addresses=[addr],
                            address_types={addr: "commercial"}, sources=["ct_sos"])

    async def enrich_organization(self, name, tax_id=None, address=None):
        cands = self.by_org.get(canonical_org_name(name), [])
        if not cands:
            return None
        m = cands[0]
        if len(cands) > 1 and address:
            hint = canonical_address(address)
            for c in cands:
                a = business_address(c)
                if hint and a and canonical_address(a) and canonical_address(a).base == hint.base:
                    m = c
                    break
        addr = business_address(m)
        officers = [person_name(p) for p in self.principals_by_biz.get(m["id"], []) if p.get("lastname")]
        return EntityRecord(
            name=m["name"], kind="organization", role="related",
            addresses=[addr] if addr else [], address_types={addr: "commercial"} if addr else {},
            incorporation_date=(m.get("date_registration") or "")[:10] or None,
            officers=officers, sources=["ct_sos"],
        )

    async def enrich_person(self, name, address=None):
        rows = self.principals_by_key.get(person_key(name), [])
        if not rows:
            return None
        chosen: Optional[Dict[str, Any]] = None
        if address:
            hint = canonical_address(address)
            if hint:
                for r in rows:
                    biz = self.masters.get(r["business_id"])
                    a = business_address(biz) if biz else None
                    ca = canonical_address(a) if a else None
                    if ca and ca.base == hint.base:
                        chosen = r
                        break
        if chosen is None:
            residences = {canonical_address(residence_of(r)).base for r in rows if residence_of(r) and canonical_address(residence_of(r))}
            if len(residences) == 1:
                chosen = rows[0]
            else:
                return None
        res = residence_of(chosen)
        return EntityRecord(name=person_name(chosen), kind="person", role="related",
                            addresses=[res] if res else [], address_types={res: "residential"} if res else {},
                            sources=["ct_sos_principals"])

    def is_registered_agent_address(self, canonical_base_address: str) -> bool:
        return len(self.biz_by_addr_base.get(canonical_base_address, [])) >= 50


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

async def evaluate(cache: Cache, pairs: Dict[str, Any], decoys: int, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    provider = CTRegistryProvider(cache)
    engine = RelationshipEngine(provider)
    masters = provider.masters
    by_city: Dict[str, List[str]] = collections.defaultdict(list)
    for bid, m in masters.items():
        if business_address(m):
            by_city[(m.get("billingcity") or "").upper()].append(bid)

    def principals_keys(bid: str) -> Set[str]:
        return {person_key(person_name(p)) for p in provider.principals_by_biz.get(bid, [])}

    def decoy_pool(bid: str, exclude: Set[str]) -> List[str]:
        city = (masters[bid].get("billingcity") or "").upper()
        same_city = [b for b in by_city.get(city, []) if b not in exclude and not (principals_keys(b) & principals_keys(bid))]
        return rng.sample(same_city, min(decoys, len(same_city)))

    pos_out = []
    decoy_counter: collections.Counter = collections.Counter()
    for a, b, key in pairs["positives"]:
        ra, rb = provider.record_for_business(a, "applicant"), provider.record_for_business(b, "vendor")
        if not ra or not rb:
            continue
        pool = [provider.record_for_business(d, "vendor") for d in decoy_pool(a, {a, b})]
        pool = [r for r in pool if r]
        result = await engine.analyze(ra, [rb] + pool)
        confirmed = {canonical_org_name(f.counterparty): f for f in result.findings}
        review = {canonical_org_name(f.counterparty): f for f in result.review_recommended}
        kb = canonical_org_name(rb.name)
        f = confirmed.get(kb) or review.get(kb)
        band = "confirmed" if kb in confirmed else "review" if kb in review else "none"
        for d in pool:
            dk = canonical_org_name(d.name)
            decoy_counter["confirmed" if dk in confirmed else "review" if dk in review else "none"] += 1
            if dk in confirmed:
                for s in confirmed[dk].signals:
                    decoy_counter[f"signal:{s['signal']}"] += 1
        pos_out.append({"a": ra.name, "b": rb.name, "principal": key, "band": band,
                        "type": f.relationship_type if f else None, "probability": f.probability if f else None,
                        "path": f.path_description if f else None, "same_building": canonical_address(ra.addresses[0]).base == canonical_address(rb.addresses[0]).base})

    neg_out = []
    for a, b, key in pairs["hard_negatives"]:
        ra, rb = provider.record_for_business(a, "applicant"), provider.record_for_business(b, "vendor")
        if not ra or not rb:
            continue
        result = await engine.analyze(ra, [rb])
        kb = canonical_org_name(rb.name)
        f = next((x for x in result.findings if canonical_org_name(x.counterparty) == kb), None)
        r = next((x for x in result.review_recommended if canonical_org_name(x.counterparty) == kb), None)
        neg_out.append({"a": ra.name, "b": rb.name, "principal_name": key,
                        "band": "confirmed" if f else "review" if r else "none",
                        "type": (f or r).relationship_type if (f or r) else None,
                        "path": (f or r).path_description if (f or r) else None,
                        "same_building": canonical_address(ra.addresses[0]).base == canonical_address(rb.addresses[0]).base})

    # In-context coincidence: unrelated same-city businesses whose principals share a full name
    pairs_n = name_hits = 0
    for city, bids in by_city.items():
        if len(bids) < 2:
            continue
        sample = rng.sample(bids, min(len(bids), 120))
        for i in range(len(sample)):
            ki = principals_keys(sample[i])
            for j in range(i + 1, len(sample)):
                pairs_n += 1
                if ki & principals_keys(sample[j]):
                    name_hits += 1

    n_pos, n_neg = len(pos_out), len(neg_out)
    pos_conf = sum(1 for o in pos_out if o["band"] == "confirmed")
    pos_rev = sum(1 for o in pos_out if o["band"] == "review")
    neg_conf = sum(1 for o in neg_out if o["band"] == "confirmed")
    neg_rev = sum(1 for o in neg_out if o["band"] == "review")
    total_decoys = sum(decoy_counter[k] for k in ("confirmed", "review", "none"))
    return {
        "dataset": {"principals": len(cache.data["principals"]), "businesses_with_master": len(masters),
                    **{k: pairs[k] for k in ("identities", "multi_business_identities", "names_with_multiple_identities")}},
        "positives": {"n": n_pos, "confirmed": pos_conf, "review": pos_rev, "missed": n_pos - pos_conf - pos_rev,
                      "recall_confirmed": round(pos_conf / max(1, n_pos), 3),
                      "types": dict(collections.Counter(o["type"] for o in pos_out if o["band"] == "confirmed")),
                      "sharing_building": sum(1 for o in pos_out if o["same_building"])},
        "hard_negatives_same_name_different_residence": {
            "n": n_neg, "confirmed": neg_conf, "review": neg_rev, "none": n_neg - neg_conf - neg_rev,
            "false_confirm_rate": round(neg_conf / max(1, n_neg), 4),
            "types_when_confirmed": dict(collections.Counter(o["type"] for o in neg_out if o["band"] == "confirmed"))},
        "decoys": {"n": total_decoys, "confirmed": decoy_counter["confirmed"], "review": decoy_counter["review"],
                   "false_flag_rate": round(decoy_counter["confirmed"] / max(1, total_decoys), 4),
                   "signals_when_confirmed": {k[7:]: v for k, v in decoy_counter.items() if k.startswith("signal:")}},
        "in_context_u_principal_full_name_collision": {"same_city_unrelated_pairs": pairs_n, "pairs_sharing_a_principal_name": name_hits,
                                                       "u": round(name_hits / max(1, pairs_n), 6)},
        "examples_positive_confirmed": [o for o in pos_out if o["band"] == "confirmed"][:6],
        "examples_positive_missed": [o for o in pos_out if o["band"] == "none"][:6],
        "examples_negative_confirmed": [o for o in neg_out if o["band"] == "confirmed"][:6],
    }


def print_report(rep: Dict[str, Any]) -> None:
    d = rep["dataset"]
    print(f"principals {d['principals']}  businesses with master {d['businesses_with_master']}  identities {d['identities']}  "
          f"multi-business identities {d['multi_business_identities']}  names with >1 identity {d['names_with_multiple_identities']}")
    p = rep["positives"]
    print(f"\n=== Positives: same principal (name + residence) across two businesses ===")
    print(f"n {p['n']}  confirmed {p['confirmed']}  review {p['review']}  missed {p['missed']}   recall(confirmed) {p['recall_confirmed']}   types {p['types']}   sharing building {p['sharing_building']}")
    for o in rep["examples_positive_confirmed"][:4]:
        print(f"  ✓ {o['a']}  ~  {o['b']}   [{o['type']} {o['probability']}]  {o['path']}")
    for o in rep["examples_positive_missed"][:3]:
        print(f"  ✗ {o['a']}  ~  {o['b']}   principal {o['principal']}")
    n = rep["hard_negatives_same_name_different_residence"]
    print(f"\n=== Hard negatives: principals share a full name but live at different addresses ===")
    print(f"n {n['n']}  confirmed {n['confirmed']}  review {n['review']}  none {n['none']}   false-confirm rate {n['false_confirm_rate']}   {n['types_when_confirmed']}")
    for o in rep["examples_negative_confirmed"][:4]:
        print(f"  ✗ {o['a']}  ~  {o['b']}   [{o['type']}]  {o['path']}")
    dc = rep["decoys"]
    print(f"\n=== Decoys: unrelated same-city businesses ===")
    print(f"n {dc['n']}  confirmed {dc['confirmed']}  review {dc['review']}   false-flag rate {dc['false_flag_rate']}   {dc['signals_when_confirmed']}")
    u = rep["in_context_u_principal_full_name_collision"]
    print(f"\n=== Coincidence: unrelated same-city businesses whose principals share a full name ===")
    print(f"pairs {u['same_city_unrelated_pairs']}  hits {u['pairs_sharing_a_principal_name']}  u = {u['u']}   (engine u for shared_officer_name 0.0025)")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--principals", type=int, default=120000)
    ap.add_argument("--max-positive", type=int, default=400)
    ap.add_argument("--max-hard-negative", type=int, default=300)
    ap.add_argument("--decoy-businesses", type=int, default=3000, help="extra same-city businesses to fetch as decoys")
    ap.add_argument("--decoys", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--evaluate-only", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    cache = Cache(args.cache)
    if not args.evaluate_only:
        print("collecting principals...", file=sys.stderr)
        collect_principals(cache, args.principals)
    pairs = build_pairs(cache, args.max_positive, args.max_hard_negative, args.seed)
    if not args.evaluate_only:
        needed: List[str] = []
        for a, b, _ in pairs["positives"] + pairs["hard_negatives"]:
            needed.extend([a, b])
        rng = random.Random(args.seed)
        all_biz = sorted({p["business_id"] for p in cache.data["principals"]})
        needed.extend(rng.sample(all_biz, min(args.decoy_businesses, len(all_biz))))
        needed = list(dict.fromkeys(needed))
        print(f"fetching {len(needed)} business masters...", file=sys.stderr)
        collect_masters(cache, needed)
    rep = asyncio.run(evaluate(cache, pairs, args.decoys, args.seed))
    print_report(rep)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(rep, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
