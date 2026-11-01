"""Offline tests for the USAspending backtest's evaluation functions, using a
hand-built cache so no network is needed."""
import asyncio

from benchmarks import backtest_usaspending as bt


def _loc(line1, city, state, zipc, line2=None):
    return {"address_line1": line1, "address_line2": line2, "city_name": city, "state_code": state, "zip": zipc,
            "country_code": "USA"}


def _cache(tmp_path):
    c = bt.Cache(str(tmp_path))
    c.data["details"] = {
        # Family A: parent and a child at the same HQ address
        "a-P": {"name": "ACME HEALTH SYSTEM", "duns": "100", "recipient_level": "P",
                "location": _loc("10 MAIN ST", "DENVER", "CO", "80202"), "parents": [],
                "alternate_names": ["ACME HEALTH SYSTEM INC", "ACME HLTH SYS"]},
        "a-C": {"name": "ACME HEALTH SYSTEM RESEARCH INSTITUTE", "duns": "101", "recipient_level": "C",
                "location": _loc("10 MAIN STREET", "DENVER", "CO", "80202-1234"),
                "parents": [{"parent_duns": "100", "parent_name": "ACME HEALTH SYSTEM", "parent_id": "a-P"},
                            {"parent_duns": "101", "parent_name": "ACME HEALTH SYSTEM RESEARCH INSTITUTE", "parent_id": "a-C2"}],
                "alternate_names": []},
        # Family B: parent and child in different cities, no shared identifiers
        "b-P": {"name": "BLUE RIVER UNIVERSITY", "duns": "200", "recipient_level": "P",
                "location": _loc("1 CAMPUS DR", "BOULDER", "CO", "80309"), "parents": [], "alternate_names": []},
        "b-C": {"name": "BLUE RIVER UNIVERSITY MEDICAL CAMPUS", "duns": "201", "recipient_level": "C",
                "location": _loc("500 HOSPITAL WAY", "AURORA", "CO", "80045"),
                "parents": [{"parent_duns": "200", "parent_name": "BLUE RIVER UNIVERSITY", "parent_id": "b-P"}],
                "alternate_names": []},
        # Unrelated parents used as decoys, one in the same building as family A but a different family
        "c-P": {"name": "CANYON COUNTY", "duns": "300", "recipient_level": "P",
                "location": _loc("10 MAIN ST STE 900", "DENVER", "CO", "80202"), "parents": [], "alternate_names": []},
        "d-P": {"name": "DELTA NONPROFIT", "duns": "400", "recipient_level": "P",
                "location": _loc("77 PINE ST", "SANTA FE", "NM", "87501"), "parents": [], "alternate_names": []},
        "e-P": {"name": "EASTSIDE SCHOOL DISTRICT", "duns": "500", "recipient_level": "P",
                "location": _loc("9 ELM AVE", "DENVER", "CO", "80203"), "parents": [], "alternate_names": []},
    }
    return c


def test_affiliate_test_scores_true_parents_and_decoys(tmp_path):
    rep = asyncio.run(bt.affiliate_test(_cache(tmp_path), decoys=3, seed=1))
    assert rep["child_parent_pairs"] == 2
    # Family A shares the HQ building and a long name prefix: must be confirmed or at least reviewed.
    assert rep["true_parent_confirmed"] + rep["true_parent_review"] >= 1
    assert rep["pairs_sharing_a_building"] == 1
    assert rep["decoy_candidates"] > 0
    assert 0.0 <= rep["decoy_false_flag_rate"] <= 1.0


def test_in_context_u_counts_only_unrelated_pairs(tmp_path):
    u = bt.in_context_u(_cache(tmp_path))
    # Denver has a-P, a-C (same family), c-P, e-P: unrelated same-city pairs are (a,c)x2, (a,e)x2, (c,e) = 5
    assert u["unrelated_same_city_pairs"] == 5
    # a-P/a-C vs c-P share the building at 10 Main St: 2 of 5 unrelated pairs
    assert abs(u["u_same_building_in_context"] - 0.4) < 1e-6
    assert u["u_same_address_in_context"] == 0.0


def test_alias_test_counts_links(tmp_path):
    al = bt.alias_test(_cache(tmp_path))
    assert al["alias_pairs"] == 2
    # "ACME HEALTH SYSTEM INC" drops the suffix; "ACME HLTH SYS" expands abbreviations: both canonical-equal
    assert al["linked_exact_canonical"] == 2
    assert al["unlinked_examples"] == []


def test_record_and_family_helpers():
    d = {"name": "X", "duns": "1", "location": _loc("1 A St", "Denver", "CO", "80202"),
         "parents": [{"parent_duns": "9"}, {"parent_duns": "1"}]}
    assert bt.family_of(d) == "9"
    rec = bt.record_of(d, "vendor")
    assert rec.addresses == ["1 A St, Denver, CO 80202"] and rec.role == "vendor"
    assert bt.record_of({"name": "Y", "location": {"country_code": "CAN", "address_line1": "1"}}, "vendor") is None
