"""
Grant Oversight Tools for Pre-Award Risk Assessment and Uniform Guidance Compliance.

Implements tools for detecting:
- Foreign entity links (shell companies, sanctions screening)
- Conflict of interest violations (related party transactions, self-dealing)
- Subcontractor verification (hidden relationships)

Supports:
- NSF Research Grants
- NIH R01/R21 Grants
- SBIR/STTR Programs
- Infrastructure Grants (IIJA)
- Community Development (CDBG)
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.agent.base import BaseTool


class ForeignEntityLinkOutput(BaseModel):
    """Output from foreign entity link detection."""
    applicant_name: str
    has_foreign_links: bool
    foreign_entities: List[Dict[str, str]] = Field(default_factory=list)
    sanctioned_entities: List[str] = Field(default_factory=list)
    shell_companies_detected: bool = False
    payment_routing_countries: List[str] = Field(default_factory=list)
    risk_score: int
    compliance_violations: List[str] = Field(default_factory=list)


class ForeignEntityLinkTool(BaseTool):
    """
    Detects hidden links to foreign entities, sanctioned vendors, and shell companies.

    Uses:
    - Corporate registry deep analysis (beneficial owners, board members)
    - IP address geolocation (server locations)
    - Payment routing analysis (bank accounts, wire transfers)
    - OFAC sanctions list screening
    - Entity Relationship Mapping (parent companies, subsidiaries)

    KILL SWITCH: Automatic 100 risk score for sanctioned entities.
    """

    name = "ForeignEntityLinkTool"
    description = "Detect hidden foreign entity links and sanctions violations for grant pre-award risk assessment"

    async def execute(
        self,
        applicant_name: str,
        subcontractors: List[str] = [],
        vendors: List[str] = []
    ) -> ForeignEntityLinkOutput:
        """
        Analyzes applicant and related entities for foreign links.

        Args:
            applicant_name: Name of grant applicant
            subcontractors: List of subcontractor names
            vendors: List of vendor names

        Returns:
            ForeignEntityLinkOutput with detected foreign entity links
        """
        # In production: Query sanctions lists (OFAC, UN, EU), corporate registries,
        # IP geolocation databases, payment routing records

        # Mock data with keyword triggers for demonstration
        all_entities = [applicant_name] + subcontractors + vendors
        foreign_entities = []
        sanctioned_entities = []
        shell_companies_detected = False
        payment_routing_countries = []
        compliance_violations = []

        for entity in all_entities:
            entity_lower = entity.lower()

            # TRIGGER 1: Sanctioned entity (OFAC list)
            if any(keyword in entity_lower for keyword in ["sanctioned", "blocked", "denied"]):
                sanctioned_entities.append(entity)
                compliance_violations.append(f"Entity '{entity}' appears on OFAC sanctions list")

            # TRIGGER 2: Chinese entity links
            if any(keyword in entity_lower for keyword in ["china", "chinese", "beijing", "shanghai"]):
                foreign_entities.append({
                    "entity": entity,
                    "country": "China",
                    "type": "Subcontractor",
                    "evidence": "Corporate registry shows Chinese beneficial ownership"
                })
                compliance_violations.append(f"Entity '{entity}' has Chinese ownership - SBIR/research grant restriction")

            # TRIGGER 3: Russian entity links
            if any(keyword in entity_lower for keyword in ["russia", "russian", "moscow"]):
                foreign_entities.append({
                    "entity": entity,
                    "country": "Russia",
                    "type": "Vendor",
                    "evidence": "Payment routing to Russian bank accounts"
                })
                sanctioned_entities.append(entity)
                compliance_violations.append(f"Entity '{entity}' routes payments to sanctioned Russian banks")

            # TRIGGER 4: Shell company indicators
            if any(keyword in entity_lower for keyword in ["llc", "holdings", "ventures"]):
                if "shell" in entity_lower or "offshore" in entity_lower:
                    shell_companies_detected = True
                    compliance_violations.append(f"Entity '{entity}' appears to be shell company (no operational presence)")

            # TRIGGER 5: Iran/North Korea (high-risk countries for research grants)
            if any(keyword in entity_lower for keyword in ["iran", "north korea", "nk", "dprk"]):
                foreign_entities.append({
                    "entity": entity,
                    "country": "Iran/North Korea",
                    "type": "Sanctions Violation",
                    "evidence": "Entity linked to sanctioned country"
                })
                sanctioned_entities.append(entity)
                compliance_violations.append(f"CRITICAL: Entity '{entity}' linked to high-risk sanctioned country")

        # Determine payment routing (in production: analyze bank account BIC codes, wire transfer records)
        if any("china" in e.lower() for e in all_entities):
            payment_routing_countries.append("China")
        if any("russia" in e.lower() for e in all_entities):
            payment_routing_countries.append("Russia")

        # Calculate risk score
        risk_score = 0
        has_foreign_links = len(foreign_entities) > 0

        if sanctioned_entities:
            risk_score = 100  # KILL SWITCH
        elif shell_companies_detected and has_foreign_links:
            risk_score = 85  # Shell company routing to foreign entity
        elif has_foreign_links and any("China" in e.get("country", "") for e in foreign_entities):
            risk_score = 70  # Chinese links (SBIR restriction)
        elif has_foreign_links:
            risk_score = 50

        return ForeignEntityLinkOutput(
            applicant_name=applicant_name,
            has_foreign_links=has_foreign_links,
            foreign_entities=foreign_entities,
            sanctioned_entities=sanctioned_entities,
            shell_companies_detected=shell_companies_detected,
            payment_routing_countries=payment_routing_countries,
            risk_score=risk_score,
            compliance_violations=compliance_violations
        )


class RelationshipOutput(BaseModel):
    """One detected relationship between the applicant side and a counterparty."""
    entity1: str
    entity2: str
    relationship_type: str          # spouse, household, ownership_interest, officer_of, spouse_controlled_entity,
                                    # indirect_ownership, common_control, operational_control, shell_cluster, ...
    confidence: float               # posterior probability 0..1
    evidence: List[str] = Field(default_factory=list)
    evidence_bits: float = 0.0      # total log-likelihood ratio (bits) behind the link
    direct: bool = True             # False when the link runs through intermediaries
    path: List[str] = Field(default_factory=list)          # entity names along the graph path
    path_description: str = ""      # "Daniel Hale → is married to Jennifer Hale → is an officer of Northstar..."
    signals: List[Dict[str, Any]] = Field(default_factory=list)   # per-signal breakdown (kind, bits, value)
    indirect_ownership_percent: float = 0.0
    immediate_family: bool = False
    self_dealing: bool = False
    band: str = "confirmed"         # confirmed | review


class ConflictOfInterestOutput(BaseModel):
    """Output from conflict of interest detection."""
    applicant_name: str
    has_conflict: bool
    conflicts_detected: List[RelationshipOutput] = Field(default_factory=list)
    review_recommended: List[RelationshipOutput] = Field(default_factory=list)   # grey band: resolve before flagging
    self_dealing: bool = False
    related_party_transactions: List[str] = Field(default_factory=list)
    uniform_guidance_violations: List[str] = Field(default_factory=list)
    risk_score: int
    relationship_graph: Dict[str, Any] = Field(default_factory=dict)   # nodes/edges for visualisation
    entities_analyzed: int = 0
    analysis_method: str = ""


class ConflictOfInterestTool(BaseTool):
    """
    Detects conflict of interest and self-dealing with probabilistic entity
    resolution and graph link analysis (see app.agent.relationships).

    Evidence used, strongest to weakest:
    - Identical tax ID or bank account between applicant-side parties and a counterparty
    - Officer / ownership overlap from corporate registries (with indirect ownership %)
    - Marriage and household records
    - Shared residential address, phone, email, private domain, device or IP
    - Shared commercial address, incorporation timing, shell-cluster patterns
    - Fuzzy name evidence (nicknames, Jaro-Winkler) weighted by surname frequency

    Each signal carries a log-likelihood ratio; signals are summed and combined
    with a prior to produce a posterior probability.  Links above the report
    threshold are returned as conflicts; links in the review band are returned
    separately so the autonomous resolver can fetch more evidence instead of
    sending the case straight to manual review.

    Uniform Guidance (2 CFR 200.112, 200.318(c)(1)-(2), 200.319) compliance check.
    """

    name = "ConflictOfInterestTool"
    description = "Detect conflict of interest and self-dealing using probabilistic relationship graph analysis"

    def __init__(self, provider=None, prior_related: float = 0.02,
                 report_threshold: float = 0.80, review_threshold: float = 0.35, max_hops: int = 3):
        super().__init__()
        from app.agent.relationships import MockRelationshipProvider, RelationshipEngine
        self.provider = provider if provider is not None else MockRelationshipProvider()
        self.engine = RelationshipEngine(self.provider, prior_related=prior_related,
                                         report_threshold=report_threshold,
                                         review_threshold=review_threshold, max_hops=max_hops)

    async def execute(
        self,
        applicant_name: str,
        contractors: List[Dict[str, Any]] = [],
        vendors: List[Dict[str, Any]] = [],
        applicant_address: str = "",
        applicant_tax_id: str = "",
        applicant_phone: str = "",
        applicant_email: str = "",
        applicant_website: str = "",
        key_personnel: List[Dict[str, Any]] = [],
        application_date: Optional[str] = None,
    ) -> ConflictOfInterestOutput:
        """
        Analyze relationships between the applicant side and every contractor / vendor.

        Args:
            applicant_name: Grant applicant organization
            contractors / vendors: party dicts.  Recognised keys: name, role, address,
                address_type, phone, email, website, tax_id/ein, officers, owners
                ([{name, percent}]), registered_agent, incorporation_date, bank_routing,
                bank_account, ip_addresses, device_ids, kind ("person"/"organization")
            applicant_*: applicant identifiers for cross-matching
            key_personnel: PI, co-PIs, officers: [{"name": "Daniel Hale", "role": "PI", ...}]
            application_date: ISO date; used for incorporation-timing signals
        """
        from app.agent.relationships import EntityRecord, entity_from_party

        applicant = EntityRecord(
            name=applicant_name, kind="organization", role="applicant",
            addresses=[applicant_address] if applicant_address else [],
            tax_ids=[applicant_tax_id] if applicant_tax_id else [],
            phones=[applicant_phone] if applicant_phone else [],
            emails=[applicant_email] if applicant_email else [],
            websites=[applicant_website] if applicant_website else [],
            sources=["application"],
        )
        counterparties = [entity_from_party(p, "contractor") for p in contractors if p.get("name")] + \
                         [entity_from_party(p, "vendor") for p in vendors if p.get("name")]
        personnel = []
        for p in key_personnel:
            if p.get("name"):
                rec = entity_from_party({**p, "kind": "person"}, "key_personnel")
                personnel.append(rec)
        role_lookup = {p.get("name", "").strip().lower(): p.get("role", "") for p in contractors + vendors}

        analysis = await self.engine.analyze(applicant, counterparties, personnel, application_date)

        def to_output(f) -> RelationshipOutput:
            return RelationshipOutput(
                entity1=f.path[0] if f.path else applicant_name,
                entity2=f.counterparty,
                relationship_type=f.relationship_type,
                confidence=f.probability,
                evidence=f.evidence,
                evidence_bits=f.evidence_bits,
                direct=f.direct,
                path=f.path,
                path_description=f.path_description,
                signals=f.signals,
                indirect_ownership_percent=f.indirect_ownership_percent,
                immediate_family=f.immediate_family,
                self_dealing=f.self_dealing,
                band=f.band,
            )

        conflicts = [to_output(f) for f in analysis.findings]
        review = [to_output(f) for f in analysis.review_recommended]

        uniform_guidance_violations: List[str] = []
        related_party_transactions: List[str] = []
        for f in analysis.findings:
            role = role_lookup.get(f.counterparty.lower(), f.counterparty_role)
            related_party_transactions.append(
                f"{f.counterparty_role.title()} '{f.counterparty}' ({role}) is a related party: "
                f"{f.relationship_type.replace('_', ' ')} at {f.probability*100:.0f}% confidence"
            )
            for cite in f.uniform_guidance:
                if cite not in uniform_guidance_violations:
                    uniform_guidance_violations.append(cite)

        self_dealing = any(f.self_dealing for f in analysis.findings)
        immediate_family = any(f.immediate_family for f in analysis.findings)
        has_conflict = bool(analysis.findings)

        # Risk score: strongest finding sets the floor, additional findings add a little.
        risk_score = 0
        if self_dealing:
            risk_score = 90
        elif immediate_family:
            risk_score = 75
        elif has_conflict:
            top = analysis.findings[0].relationship_type
            risk_score = 65 if top in {"common_control", "shell_cluster", "operational_control", "same_entity"} else 50
        if has_conflict and len(analysis.findings) > 1:
            risk_score = min(100, risk_score + 5 * (len(analysis.findings) - 1))
        if not has_conflict and review:
            risk_score = 25  # unresolved grey area; resolver should act before a human does

        return ConflictOfInterestOutput(
            applicant_name=applicant_name,
            has_conflict=has_conflict,
            conflicts_detected=conflicts,
            review_recommended=review,
            self_dealing=self_dealing,
            related_party_transactions=related_party_transactions,
            uniform_guidance_violations=uniform_guidance_violations,
            risk_score=risk_score,
            relationship_graph=analysis.graph,
            entities_analyzed=analysis.entity_count,
            analysis_method=analysis.method,
        )


class UtilityBillOutput(BaseModel):
    """Output from utility bill verification (autonomous grey area resolution)."""
    address: str
    verified: bool
    account_holder_name: str
    service_start_date: str
    matches_applicant: bool
    resolution_status: str  # "RESOLVED_LEGITIMATE", "RESOLVED_FRAUDULENT", "MANUAL_REVIEW_REQUIRED"
    evidence: List[str] = Field(default_factory=list)


class UtilityBillVerificationTool(BaseTool):
    """
    Autonomous grey area resolution tool for address mismatches.

    When address discrepancy is detected, automatically:
    1. Pull utility bills (electric, gas, water) for the claimed address
    2. Verify account holder name matches applicant
    3. Check service start date (recent move indicator)
    4. Cross-reference with USPS change-of-address records
    5. Verify property tax records

    This prevents manual review for legitimate recent moves.
    """

    name = "UtilityBillVerificationTool"
    description = "Automatically resolve address mismatches by verifying utility bills and property records"

    async def execute(
        self,
        address: str,
        applicant_name: str,
        claimed_move_date: Optional[str] = None
    ) -> UtilityBillOutput:
        """
        Fetch and verify utility bills for address.

        Args:
            address: Address to verify
            applicant_name: Expected account holder name
            claimed_move_date: When applicant claims to have moved (optional)

        Returns:
            UtilityBillOutput with verification results
        """
        # In production: Query utility company APIs, property tax databases,
        # USPS change-of-address system

        # Mock data with keyword triggers
        address_lower = address.lower()
        applicant_lower = applicant_name.lower()

        # TRIGGER 1: Legitimate recent move
        if "recent" in applicant_lower or "moved" in applicant_lower:
            return UtilityBillOutput(
                address=address,
                verified=True,
                account_holder_name=applicant_name,
                service_start_date="2024-11-15",
                matches_applicant=True,
                resolution_status="RESOLVED_LEGITIMATE",
                evidence=[
                    f"Utility bill for {address} shows {applicant_name} as account holder",
                    "Electric service started 2024-11-15 (45 days ago)",
                    "USPS change-of-address filed 2024-11-10",
                    "Property tax records show recent ownership transfer"
                ]
            )

        # TRIGGER 2: Fraud - utility bill doesn't match
        elif "fraud" in applicant_lower or "fake" in address_lower:
            return UtilityBillOutput(
                address=address,
                verified=False,
                account_holder_name="Different Person",
                service_start_date="2015-03-01",
                matches_applicant=False,
                resolution_status="RESOLVED_FRAUDULENT",
                evidence=[
                    f"Utility bill for {address} shows different account holder (not {applicant_name})",
                    "No USPS change-of-address found",
                    "Property tax records show no connection to applicant",
                    "Applicant's previous address still has active utilities"
                ]
            )

        # Default: Manual review needed
        else:
            return UtilityBillOutput(
                address=address,
                verified=False,
                account_holder_name="Unknown",
                service_start_date="Unknown",
                matches_applicant=False,
                resolution_status="MANUAL_REVIEW_REQUIRED",
                evidence=[
                    "Unable to access utility records for this address",
                    "Manual verification required"
                ]
            )
