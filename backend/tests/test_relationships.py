"""
Tests for the relationship analysis engine and the ConflictOfInterestTool.

Run from backend/:  python -m pytest tests/test_relationships.py -q
"""
import asyncio
import math

import pytest

from app.agent.grants import ConflictOfInterestTool
from app.agent.relationships import (
    HARD_SIGNALS,
    EntityRecord,
    MockRelationshipProvider,
    NullProvider,
    Ownership,
    RelationshipEngine,
    canonical_address,
    canonical_email,
    canonical_org_name,
    canonical_phone,
    compare_entities,
    entity_id,
    given_names_match,
    hash_bank_account,
    jaro_winkler,
    parse_person_name,
    posterior_probability,
    same_person_score,
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- normalisation

def test_person_name_parsing_handles_honorifics_suffixes_and_last_first():
    assert parse_person_name("Dr. Daniel R. Hale Jr.").canonical == "daniel hale"
    assert parse_person_name("HALE, Daniel").canonical == "daniel hale"
    assert parse_person_name("Prof. Priya Raman, PhD").canonical == "priya raman"


def test_nicknames_and_initials_match():
    assert given_names_match("bill", "william")
    assert given_names_match("jen", "jennifer")
    assert given_names_match("d", "daniel")
    assert not given_names_match("daniel", "jennifer")


def test_entity_id_collapses_nicknames_and_legal_suffixes():
    assert entity_id("Dr. Dan Hale", "person") == entity_id("Daniel Hale", "person")
    assert entity_id("The Northstar Analytics, L.L.C.", "organization") == entity_id("Northstar Analytics LLC", "organization")
    assert canonical_org_name("Meridian Research Group, Inc.") == "meridian research"


def test_org_name_abbreviations_and_state_codes_expand():
    from app.agent.relationships import org_name_containment
    assert canonical_org_name("IL DEPT. OF HUMAN SERVICES") == canonical_org_name("Illinois Department of Human Service")
    assert canonical_org_name("PA DEPT OF PUBLIC WELFARE") == "pennsylvania department public welfare"
    assert canonical_org_name("NEW YORK CITY HA") == canonical_org_name("New York City Housing Authority")
    assert canonical_org_name("Univ. of Colorado Denver") == "university colorado denver"
    assert canonical_org_name("IL DEPT. OF HUMAN SERVICES (2)") == canonical_org_name("IL DEPT OF HUMAN SERVICES")
    assert canonical_org_name("Acme Holdings 2 LLC") != canonical_org_name("Acme Holdings LLC")   # series entities differ
    assert canonical_org_name("3M Company") == "3m"
    # 'CO' is a legal suffix for companies but a state for government bodies
    assert canonical_org_name("Acme Widget Co") == "acme widget"
    assert canonical_org_name("Acme Health Services Co") == "acme health"      # not 'county'
    assert canonical_org_name("CO Department of Health") == "colorado department health"
    assert canonical_org_name("St. Mary's Hospital") == "st marys hospital"
    assert canonical_org_name("PA ST OFFICE OF THE GOVERNOR") == "pennsylvania state office governor"
    # Lower-case 'ca' or a company called 'Ca Labs' must not become California
    assert "california" not in canonical_org_name("Ca Labs Inc")
    assert org_name_containment("University of California", "University of California Irvine")
    assert not org_name_containment("State of Missouri", "Department of Economic Development Missouri")
    assert not org_name_containment("Acme", "Acme Research")      # single-token names never contain


def test_address_canonicalisation_splits_unit_and_abbreviates():
    a = canonical_address("1200 Research Parkway, Suite 400, Boulder, CO 80301-1234")
    b = canonical_address("1200 Research Pkwy Ste 400 Boulder CO 80301")
    c = canonical_address("1200 Research Pkwy #410, Boulder CO 80301")
    assert a.full == b.full
    assert a.unit == "400" and c.unit == "410"
    assert a.base == c.base and a.full != c.full


def test_phone_and_email_canonicalisation():
    assert canonical_phone("+1 (303) 555-0142") == "3035550142"
    assert canonical_email("D.Hale+grants@Gmail.com") == ("dhale@gmail.com", "gmail.com")
    assert canonical_email("jhale@Northstar-Analytics.com")[1] == "northstar-analytics.com"


def test_jaro_winkler_and_same_person():
    assert jaro_winkler("martha", "marhta") > 0.95
    assert jaro_winkler("abc", "xyz") == 0.0
    assert same_person_score(parse_person_name("Bill Hale"), parse_person_name("William Hale")) >= 0.9
    assert same_person_score(parse_person_name("Patricia Hale"), parse_person_name("Daniel Hale")) == 0.0


# ---------------------------------------------------------------- scoring

def test_posterior_probability_is_monotone_and_prior_anchored():
    assert math.isclose(posterior_probability(0.0, 0.5), 0.5)
    assert posterior_probability(10, 0.02) > posterior_probability(5, 0.02) > posterior_probability(0, 0.02)
    assert posterior_probability(0, 0.02) < 0.03


def test_name_only_evidence_never_reaches_confirmed_band():
    """A shared surname alone must land in the review band, not be reported as a conflict."""
    provider = NullProvider()
    a = EntityRecord(name="Daniel Hale", kind="person", role="key_personnel")
    b = EntityRecord(name="Patricia Hale", kind="person", role="related")
    signals = compare_entities(a, b, provider)
    assert [s.kind for s in signals] == ["shared_surname"]
    assert not any(s.kind in HARD_SIGNALS for s in signals)
    prob = posterior_probability(sum(s.llr_bits for s in signals), 0.02)
    assert 0.35 <= prob < 0.80


def test_common_surname_is_weaker_than_rare_surname():
    provider = NullProvider()
    smiths = compare_entities(EntityRecord(name="John Smith", kind="person"), EntityRecord(name="Mary Smith", kind="person"), provider)
    hales = compare_entities(EntityRecord(name="John Hale", kind="person"), EntityRecord(name="Mary Hale", kind="person"), provider)
    assert smiths[0].llr_bits < hales[0].llr_bits


def test_registered_agent_alone_is_ignored():
    provider = NullProvider()
    a = EntityRecord(name="Acme Corp", registered_agent="CT Corporation System")
    b = EntityRecord(name="Zeta LLC", registered_agent="CT Corporation System")
    signals = compare_entities(a, b, provider)
    prob = posterior_probability(sum(s.llr_bits for s in signals), 0.02)
    assert prob < 0.35


def test_shared_bank_account_is_near_conclusive():
    provider = NullProvider()
    h = hash_bank_account("102000021", "4455667788")
    a = EntityRecord(name="Acme Corp", bank_account_hashes=[h])
    b = EntityRecord(name="Zeta LLC", bank_account_hashes=[h])
    signals = compare_entities(a, b, provider)
    assert posterior_probability(sum(s.llr_bits for s in signals), 0.02) > 0.99


# ---------------------------------------------------------------- engine with submitted data only

def test_engine_links_parties_through_shared_identifiers_without_a_provider():
    """Different names, nothing in common except the application's own data."""
    engine = RelationshipEngine(NullProvider())
    applicant = EntityRecord(name="Blue Mesa Research Institute", role="applicant",
                             addresses=["55 Canyon Rd Suite 200, Santa Fe, NM 87501"], phones=["505-555-0101"])
    vendor = EntityRecord(name="Rio Grande Data Services", role="vendor",
                          addresses=["55 Canyon Road, Ste 200, Santa Fe NM 87501"], phones=["(505) 555-0101"])
    clean = EntityRecord(name="Staples Inc", role="vendor", addresses=["500 Staples Dr, Framingham, MA 01702"])
    result = run(engine.analyze(applicant, [vendor, clean]))
    names = {f.counterparty for f in result.findings}
    assert "Rio Grande Data Services" in names
    assert "Staples Inc" not in names
    finding = result.findings[0]
    assert finding.direct and finding.probability > 0.99
    assert {s["signal"] for s in finding.signals} == {"same_phone", "same_address"}
    assert any("200.112" in c or "200.318" in c for c in finding.uniform_guidance)


def test_engine_finds_spouse_controlled_contractor_via_two_hop_path():
    engine = RelationshipEngine(MockRelationshipProvider())
    applicant = EntityRecord(name="Meridian Research Group", role="applicant", tax_ids=["84-1234567"])
    pi = EntityRecord(name="Dr. Dan Hale", kind="person", role="key_personnel")
    contractor = EntityRecord(name="Northstar Analytics, L.L.C.", role="contractor")
    result = run(engine.analyze(applicant, [contractor], key_personnel=[pi], application_date="2025-10-01"))
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.relationship_type == "spouse_controlled_entity"
    assert f.immediate_family and f.self_dealing
    assert not f.direct
    assert f.path == ["Daniel Hale", "Jennifer Hale", "Northstar Analytics, L.L.C."]
    assert "married to" in f.path_description
    assert any("2 CFR 200.318(c)(1)" in c for c in f.uniform_guidance)


def test_engine_computes_indirect_ownership_through_holding_company():
    engine = RelationshipEngine(MockRelationshipProvider())
    applicant = EntityRecord(name="Meridian Research Group", role="applicant")
    pi = EntityRecord(name="Daniel Hale", kind="person", role="key_personnel")
    vendor = EntityRecord(name="Summit Field Services Inc", role="vendor")
    result = run(engine.analyze(applicant, [vendor], key_personnel=[pi]))
    f = result.findings[0]
    assert f.relationship_type == "indirect_ownership"
    assert f.indirect_ownership_percent == 60.0          # 60% of Holdings × 100% of Summit
    assert "owns 60% of Hale Family Holdings LLC" in f.path_description
    assert any("60% indirect ownership" in c for c in f.uniform_guidance)


def test_engine_routes_surname_only_match_to_review_not_conflict():
    engine = RelationshipEngine(MockRelationshipProvider())
    applicant = EntityRecord(name="Meridian Research Group", role="applicant")
    pi = EntityRecord(name="Daniel Hale", kind="person", role="key_personnel")
    contractor = EntityRecord(name="Front Range Statistical Consulting LLC", role="contractor")
    result = run(engine.analyze(applicant, [contractor], key_personnel=[pi]))
    assert result.findings == []
    assert len(result.review_recommended) == 1
    r = result.review_recommended[0]
    assert r.relationship_type == "possible_family" and r.band == "review"
    assert r.uniform_guidance and "200.112" in r.uniform_guidance[0]


def test_engine_does_not_flag_unrelated_vendor_sharing_registered_agent():
    engine = RelationshipEngine(MockRelationshipProvider())
    applicant = EntityRecord(name="Meridian Research Group", role="applicant")
    pi = EntityRecord(name="Daniel Hale", kind="person", role="key_personnel")
    vendor = EntityRecord(name="Dell Technologies Inc", role="vendor")
    result = run(engine.analyze(applicant, [vendor], key_personnel=[pi]))
    assert result.findings == [] and result.review_recommended == []


def test_graph_export_contains_shared_identifier_nodes_and_flags():
    engine = RelationshipEngine(MockRelationshipProvider())
    applicant = EntityRecord(name="Meridian Research Group", role="applicant")
    pi = EntityRecord(name="Daniel Hale", kind="person", role="key_personnel")
    contractor = EntityRecord(name="Northstar Analytics LLC", role="contractor")
    result = run(engine.analyze(applicant, [contractor], key_personnel=[pi]))
    g = result.graph
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"person", "organization", "identifier"} <= kinds
    flagged = [n for n in g["nodes"] if n["flagged"]]
    assert flagged and flagged[0]["label"] == "Northstar Analytics LLC"
    assert any(e["kind"] == "spouse" for e in g["edges"])
    assert any(e["kind"] == "has_identifier" for e in g["edges"])
    sides = {n["side"] for n in g["nodes"]}
    assert {"applicant", "counterparty", "identifier"} <= sides


# ---------------------------------------------------------------- tool wrapper

def test_tool_output_is_backward_compatible_and_scores_risk():
    tool = ConflictOfInterestTool()
    out = run(tool.execute(
        applicant_name="Meridian Research Group",
        applicant_address="1200 Research Pkwy Suite 400, Boulder, CO 80301",
        applicant_tax_id="84-1234567",
        key_personnel=[{"name": "Daniel Hale", "role": "PI"}],
        contractors=[{"name": "Northstar Analytics LLC", "role": "Data analysis"},
                     {"name": "Front Range Statistical Consulting LLC", "role": "Statistics"}],
        vendors=[{"name": "Summit Field Services Inc", "role": "Equipment"},
                 {"name": "Dell Technologies Inc", "role": "Hardware"}],
        application_date="2025-10-01",
    ))
    assert out.has_conflict and out.self_dealing
    assert {c.entity2 for c in out.conflicts_detected} == {"Northstar Analytics LLC", "Summit Field Services Inc"}
    assert [r.entity2 for r in out.review_recommended] == ["Front Range Statistical Consulting LLC"]
    assert out.risk_score >= 90
    assert out.relationship_graph["nodes"]
    assert out.entities_analyzed > 5
    # Old consumers still get these fields
    first = out.conflicts_detected[0]
    assert first.entity1 and first.entity2 and 0 <= first.confidence <= 1 and first.evidence
    serialised = out.model_dump() if hasattr(out, "model_dump") else out.dict()
    assert "relationship_graph" in serialised


def test_tool_handles_no_data_gracefully():
    tool = ConflictOfInterestTool(provider=NullProvider())
    out = run(tool.execute(applicant_name="Nobody Org", contractors=[{"name": "Some Vendor"}]))
    assert not out.has_conflict and out.risk_score == 0 and out.conflicts_detected == []


def test_submitted_owner_percentages_drive_self_dealing_without_provider():
    tool = ConflictOfInterestTool(provider=NullProvider())
    out = run(tool.execute(
        applicant_name="Harbor Light Community Development Corp",
        key_personnel=[{"name": "Angela Ruiz", "role": "Executive Director"}],
        contractors=[{"name": "Ruiz Construction LLC", "role": "General contractor",
                      "owners": [{"name": "Angela M. Ruiz", "percent": 51}]}],
    ))
    assert out.self_dealing
    c = out.conflicts_detected[0]
    assert c.relationship_type in {"ownership_interest", "owner_of"}
    assert c.indirect_ownership_percent == 51.0


def test_person_ownership_record_is_treated_as_person_not_org():
    rec = EntityRecord(name="Holdco", owners=[Ownership("Angela Ruiz", 51), Ownership("Ruiz Family Trust", 49)])
    engine = RelationshipEngine(NullProvider())
    applicant = EntityRecord(name="Applicant Org", role="applicant")
    result = run(engine.analyze(applicant, [rec]))
    kinds = {n["label"]: n["kind"] for n in result.graph["nodes"]}
    assert kinds["Angela Ruiz"] == "person"
    assert kinds["Ruiz Family Trust"] == "organization"
