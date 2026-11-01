"""
Estimate coincidence rates (Fellegi-Sunter "u" probabilities) from a real
corporate registry, with no labels required.

u(signal) is the probability that two UNRELATED parties share the identifier
by chance.  Two randomly chosen registry records are unrelated with near
certainty, so the exact-collision rate across all record pairs,

    u = sum_k n_k (n_k - 1) / (N (N - 1))

where n_k is the number of records carrying value k, is the u estimate.  This
is computed for every identifier a registry exposes: full address, building,
registered agent, formation date, formation month, canonical organisation
name, and the surname distribution of individual agents (which calibrates the
shared-surname signal).  Addresses carried by hundreds of entities are
reported as mail-drop / registered-agent addresses for the provider's
`is_registered_agent_address` list.

Data sources:

    # Colorado Secretary of State business entities (open data, no key needed)
    python -m benchmarks.estimate_u --fetch-colorado 100000 --cache co_entities.json --out calibrated_weights.json

    # Any CSV / JSON export with a column mapping
    python -m benchmarks.estimate_u --input entities.csv \
        --col-name entityname --col-address principaladdress1 --col-city principalcity \
        --col-state principalstate --col-zip principalzipcode --col-agent agentname --col-formed entityformdate

The output JSON is read by `app.agent.relationships.load_weights`; m values are
left at their defaults (m needs labelled or EM-estimated data) and the file
records the measured u next to the default so the change is visible.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.agent.relationships import (
    DEFAULT_WEIGHTS,
    _SURNAME_FREQUENCY,
    _parse_date,
    canonical_address,
    canonical_org_name,
    parse_person_name,
)

COLORADO_URL = "https://data.colorado.gov/resource/4ykn-tg5h.json"


@dataclass
class RegistryRow:
    name: str
    address: str
    agent: str
    agent_is_person: bool
    agent_surname: str
    formed: Optional[date]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def fetch_colorado(limit: int, cache: Optional[str] = None, page: int = 50000) -> List[Dict[str, Any]]:
    if cache and os.path.exists(cache):
        with open(cache) as fh:
            rows = json.load(fh)
        if len(rows) >= limit:
            return rows[:limit]
    rows: List[Dict[str, Any]] = []
    offset = 0
    while len(rows) < limit:
        n = min(page, limit - len(rows))
        params = {"$limit": n, "$offset": offset, "$where": "entitystatus='Good Standing'", "$order": "entityid"}
        url = f"{COLORADO_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            batch = json.load(resp)
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        print(f"  fetched {len(rows)} rows", file=sys.stderr)
        if len(batch) < n:
            break
    if cache:
        with open(cache, "w") as fh:
            json.dump(rows, fh)
    return rows


def colorado_to_rows(raw: Iterable[Dict[str, Any]]) -> List[RegistryRow]:
    rows = []
    for r in raw:
        addr = " ".join(x for x in [r.get("principaladdress1", ""), r.get("principaladdress2", "")] if x)
        if not addr:
            continue
        address = f"{addr}, {r.get('principalcity', '')}, {r.get('principalstate', '')} {r.get('principalzipcode', '')}"
        if r.get("agentorganizationname"):
            agent, is_person, surname = r["agentorganizationname"], False, ""
        else:
            first, last = r.get("agentfirstname", ""), r.get("agentlastname", "")
            agent = f"{first} {last}".strip()
            is_person, surname = bool(last), last.lower().strip()
        rows.append(RegistryRow(r.get("entityname", ""), address, agent, is_person, surname, _parse_date(r.get("entityformdate"))))
    return rows


def generic_to_rows(path: str, cols: Dict[str, str]) -> List[RegistryRow]:
    if path.endswith(".json"):
        with open(path) as fh:
            raw = json.load(fh)
    else:
        with open(path, newline="") as fh:
            raw = list(csv.DictReader(fh))
    rows = []
    for r in raw:
        name = r.get(cols["name"], "")
        parts = [r.get(cols.get("address", ""), ""), r.get(cols.get("city", ""), ""),
                 f"{r.get(cols.get('state', ''), '')} {r.get(cols.get('zip', ''), '')}".strip()]
        address = ", ".join(p for p in parts if p)
        agent = r.get(cols.get("agent", ""), "") or ""
        pn = parse_person_name(agent)
        is_person = bool(pn.first and pn.last) and not any(t in agent.lower() for t in ("llc", "inc", "corp", "company", "services", "agents"))
        rows.append(RegistryRow(name, address, agent, is_person, pn.last if is_person else "", _parse_date(r.get(cols.get("formed", ""), ""))))
    return rows


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------

def collision_rate(values: Iterable[Optional[str]],
                   strata: Optional[Iterable[Optional[str]]] = None) -> Tuple[float, int, collections.Counter]:
    """Exact probability that two random records share a value.

    With `strata` (e.g. the city of each record) the rate is computed over pairs
    that fall in the same stratum.  That is the fairer number for Veritas: the
    parties on one grant application are not two random companies from
    anywhere in the state, they are usually from the same metro area, so the
    chance they share an address or an agent by coincidence is higher than the
    statewide rate.
    """
    values = list(values)
    if strata is None:
        counts = collections.Counter(v for v in values if v)
        n = sum(counts.values())
        if n < 2:
            return 0.0, n, counts
        pairs_same = sum(c * (c - 1) for c in counts.values())
        return pairs_same / (n * (n - 1)), n, counts
    strata = list(strata)
    counts = collections.Counter(v for v in values if v)
    per_stratum: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    n_per_stratum: collections.Counter = collections.Counter()
    for v, s in zip(values, strata):
        if v and s:
            per_stratum[s][v] += 1
            n_per_stratum[s] += 1
    numer = sum(c * (c - 1) for cnt in per_stratum.values() for c in cnt.values())
    denom = sum(n * (n - 1) for n in n_per_stratum.values())
    n = sum(n_per_stratum.values())
    return (numer / denom if denom else 0.0), n, counts


def _city_of(address: str) -> Optional[str]:
    parts = [p.strip().lower() for p in address.split(",")]
    return parts[-2] if len(parts) >= 2 and parts[-2] else None


def estimate(rows: List[RegistryRow], mail_drop_threshold: int = 50, condition_on_city: bool = True) -> Dict[str, Any]:
    canon = [canonical_address(r.address) for r in rows]
    full = [c.full if c else None for c in canon]
    base = [c.base if c else None for c in canon]
    cities = [_city_of(r.address) for r in rows] if condition_on_city else None

    def rate(values: List[Optional[str]], mask: Optional[List[bool]] = None):
        if mask is not None:
            values = [v if keep else None for v, keep in zip(values, mask)]
        return collision_rate(values, cities)

    u_full, n_addr, full_counts = rate(full)
    u_base, _, base_counts = rate(base)

    # Mail-drop / registered-agent addresses: buildings shared by very many entities.
    mail_drops = {b: c for b, c in base_counts.items() if c >= mail_drop_threshold}
    keep = [bool(b) and b not in mail_drops for b in base]
    u_full_excl, n_excl, _ = rate(full, keep)
    u_base_excl, _, _ = rate(base, keep)
    # same_building means same base, different unit: P(same base) - P(same full)
    u_building_excl = max(u_base_excl - u_full_excl, 1e-7)

    u_agent, n_agent, agent_counts = rate([canonical_org_name(r.agent) if r.agent else None for r in rows])
    u_formed, n_formed, _ = rate([r.formed.isoformat() if r.formed else None for r in rows])
    u_month, _, _ = rate([f"{r.formed.year}-{r.formed.month:02d}" if r.formed else None for r in rows])
    u_name, _, name_counts = rate([canonical_org_name(r.name) if r.name else None for r in rows])

    surname_values = [r.agent_surname if (r.agent_is_person and r.agent_surname) else None for r in rows]
    u_surname, n_surname, surname_counts = rate(surname_values)
    surname_freq = {s: c / max(1, n_surname) for s, c in surname_counts.most_common(300)}

    def with_default(kind: str, u: float) -> Dict[str, float]:
        m, u_default = DEFAULT_WEIGHTS[kind]
        return {"m": m, "u": round(max(u, 1e-7), 8), "u_default": u_default,
                "bits_default": round(math.log2(m / u_default), 2), "bits_measured": round(math.log2(m / max(u, 1e-7)), 2)}

    # same_mail_drop_address is deliberately not calibrated here: the engine applies
    # it conditional on both parties already sitting at a mail-drop building, and a
    # registry-wide collision rate does not measure that conditional probability.
    weights = {
        "same_address": with_default("same_address", u_full_excl),
        "same_building": with_default("same_building", u_building_excl),
        "same_registered_agent": with_default("same_registered_agent", u_agent),
        "same_incorporation_date": with_default("same_incorporation_date", u_formed),
        "incorporated_same_month": with_default("incorporated_same_month", u_month),
        "same_org_name": with_default("same_org_name", u_name),
        "shared_surname": with_default("shared_surname", u_surname),
        "officer_shares_surname": with_default("officer_shares_surname", u_surname),
    }
    report = {
        "records": len(rows),
        "conditioned_on_city": condition_on_city,
        "u_statewide_same_address_for_reference": round(collision_rate([f for f, k in zip(full, keep) if k])[0], 8),
        "records_with_address": n_addr,
        "records_with_agent": n_agent,
        "records_with_formation_date": n_formed,
        "individual_agents": n_surname,
        "mail_drop_addresses": {b: c for b, c in sorted(mail_drops.items(), key=lambda kv: -kv[1])[:25]},
        "mail_drop_address_count": len(mail_drops),
        "top_registered_agents": {a: c for a, c in agent_counts.most_common(15)},
        "surname_frequency_top": {s: round(f, 5) for s, f in list(surname_freq.items())[:40]},
        "surname_frequency_vs_engine_table": {
            s: {"registry": round(surname_freq.get(s, 0.0), 5), "engine": f}
            for s, f in list(_SURNAME_FREQUENCY.items())[:15]
        },
        "weights": weights,
    }
    return report


def write_weights(report: Dict[str, Any], out: str, surname_table: bool = True) -> None:
    payload: Dict[str, Any] = {k: {"m": v["m"], "u": v["u"]} for k, v in report["weights"].items()}
    payload["_meta"] = {"records": report["records"], "note": "u measured as exact-collision rate over all record pairs; m left at default"}
    if surname_table:
        payload["_surname_frequency"] = report["surname_frequency_top"]
    with open(out, "w") as fh:
        json.dump(payload, fh, indent=2)


def print_report(report: Dict[str, Any]) -> None:
    print(f"records: {report['records']}  with address: {report['records_with_address']}  "
          f"with agent: {report['records_with_agent']}  individual agents: {report['individual_agents']}")
    print(f"pairs conditioned on same city: {report['conditioned_on_city']}   "
          f"(statewide same_address u for reference: {report['u_statewide_same_address_for_reference']})")
    print(f"\nmail-drop / registered-agent buildings (>= threshold entities): {report['mail_drop_address_count']}")
    for b, c in list(report["mail_drop_addresses"].items())[:8]:
        print(f"  {c:>6}  {b}")
    print("\ntop registered agents:")
    for a, c in list(report["top_registered_agents"].items())[:8]:
        print(f"  {c:>6}  {a}")
    print(f"\n{'signal':<28}{'u default':>12}{'u measured':>13}{'bits default':>14}{'bits measured':>15}")
    for k, v in report["weights"].items():
        print(f"{k:<28}{v['u_default']:>12.6f}{v['u']:>13.6f}{v['bits_default']:>14.2f}{v['bits_measured']:>15.2f}")
    print("\nsurname frequency, registry vs engine table:")
    for s, v in list(report["surname_frequency_vs_engine_table"].items())[:10]:
        print(f"  {s:<12} registry {v['registry']:.5f}   engine {v['engine']:.5f}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-colorado", type=int, metavar="N", help="download N Colorado business entities")
    ap.add_argument("--cache", help="JSON cache for the Colorado download")
    ap.add_argument("--input", help="CSV or JSON registry export")
    for col in ("name", "address", "city", "state", "zip", "agent", "formed"):
        ap.add_argument(f"--col-{col}", default=col)
    ap.add_argument("--mail-drop-threshold", type=int, default=50)
    ap.add_argument("--statewide", action="store_true",
                    help="compute rates over all pairs instead of pairs within the same city (lower, less realistic)")
    ap.add_argument("--out", help="write calibrated weights JSON here")
    ap.add_argument("--report-json", help="write the full report here")
    args = ap.parse_args(argv)

    if args.fetch_colorado:
        print(f"fetching {args.fetch_colorado} Colorado entities...", file=sys.stderr)
        rows = colorado_to_rows(fetch_colorado(args.fetch_colorado, args.cache))
    elif args.input:
        cols = {c: getattr(args, f"col_{c}") for c in ("name", "address", "city", "state", "zip", "agent", "formed")}
        rows = generic_to_rows(args.input, cols)
    else:
        ap.error("provide --fetch-colorado N or --input PATH")
        return 2

    report = estimate(rows, args.mail_drop_threshold, condition_on_city=not args.statewide)
    print_report(report)
    if args.out:
        write_weights(report, args.out)
        print(f"\nwrote weights to {args.out}")
    if args.report_json:
        with open(args.report_json, "w") as fh:
            json.dump(report, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
