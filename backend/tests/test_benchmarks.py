"""
Smoke tests for the benchmark tooling: the synthetic harness must score the
engine well on planted patterns, and the u-estimator must produce sane,
loadable weights.  Kept small so they run in a few seconds.
"""
import asyncio
import json
import random

from app.agent.relationships import DEFAULT_WEIGHTS, RelationshipEngine, load_weights
from benchmarks import estimate_u
from benchmarks.synthetic import NEGATIVE, POSITIVE, World, run_benchmark, SyntheticProvider, build_case, run_case


def test_synthetic_benchmark_meets_floor_with_default_weights():
    summary = asyncio.run(run_benchmark(cases=40, seed=3, coverage=1.0, vital_records=True, weights=None))
    c = summary["confirmed_band"]
    assert summary["positives"] > 20 and summary["negatives"] > 40
    assert c["precision"] >= 0.9, summary
    assert c["recall"] >= 0.8, summary
    assert summary["false_positive_rate_on_negatives"] <= 0.1, summary
    # Soft-evidence negatives must (almost) never be confirmed.  The small tolerance covers
    # the synthetic world's deliberately tiny given-name vocabulary, which produces far more
    # exact full-name collisions between strangers than a real population.
    assert summary["by_pattern"]["surname_coincidence"]["confirmed"] <= 0.03
    assert summary["by_pattern"]["same_agent"]["confirmed"] <= 0.03


def test_synthetic_benchmark_without_vital_records_still_finds_structure():
    summary = asyncio.run(run_benchmark(cases=30, seed=5, coverage=1.0, vital_records=False, weights=None))
    # Holding chains and self-officer links come from the registry, not vital records.
    assert summary["by_pattern"]["holding_chain"]["confirmed"] >= 0.8
    assert summary["by_pattern"]["self_officer"]["confirmed"] >= 0.8


def test_planted_patterns_cover_all_kinds():
    rng = random.Random(11)
    world = World(rng, n_households=150, n_companies=200)
    seen = set()
    for _ in range(40):
        for p in build_case(world, rng).counterparties:
            seen.add(p.pattern)
    assert set(POSITIVE) <= seen and set(NEGATIVE) <= seen


def test_u_estimator_on_synthetic_registry(tmp_path):
    rng = random.Random(2)
    world = World(rng, n_households=300, n_companies=800)
    rows = []
    for c in world.companies.values():
        agent_person = world.people[c.officers[0]]
        rows.append(estimate_u.RegistryRow(c.name, c.address, c.agent, agent_is_person=False, agent_surname="",
                                           formed=c.formed))
        rows.append(estimate_u.RegistryRow(c.name + " Holdings", agent_person.home, agent_person.name, True,
                                           agent_person.last, c.formed))
    report = estimate_u.estimate(rows, mail_drop_threshold=20)
    w = report["weights"]
    assert 0 < w["same_address"]["u"] < 0.05
    assert 0.0005 < w["same_registered_agent"]["u"] < 0.5
    assert 0 < w["shared_surname"]["u"] < 0.1   # synthetic surnames are far more concentrated than a real registry
    out = tmp_path / "weights.json"
    estimate_u.write_weights(report, str(out))
    loaded = load_weights(str(out))
    assert set(DEFAULT_WEIGHTS) == set(loaded)
    assert loaded["same_address"][1] == w["same_address"]["u"]
    assert loaded["same_phone"] == DEFAULT_WEIGHTS["same_phone"]  # untouched kinds keep defaults
    engine = RelationshipEngine(weights=loaded)
    assert engine.weights["same_address"][1] == w["same_address"]["u"]


def test_colorado_row_conversion_handles_person_and_org_agents():
    raw = [
        {"entityname": "Acme LLC", "principaladdress1": "1 Main St", "principalcity": "Denver", "principalstate": "CO",
         "principalzipcode": "80202", "agentfirstname": "JANE", "agentlastname": "DOE", "entityformdate": "2020-01-02T00:00:00.000"},
        {"entityname": "Zeta Inc", "principaladdress1": "2 Main St", "principalcity": "Denver", "principalstate": "CO",
         "principalzipcode": "80202", "agentorganizationname": "CT Corporation System"},
        {"entityname": "No Address Co"},
    ]
    rows = estimate_u.colorado_to_rows(raw)
    assert len(rows) == 2
    assert rows[0].agent_is_person and rows[0].agent_surname == "doe" and rows[0].formed.year == 2020
    assert not rows[1].agent_is_person and rows[1].formed is None
    assert estimate_u._city_of(rows[0].address) == "denver"
