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
    """Output from relationship analysis."""
    entity1: str
    entity2: str
    relationship_type: str  # "spouse", "family", "business_partner", "shared_address", "shared_account"
    confidence: float  # 0.0 to 1.0
    evidence: List[str] = Field(default_factory=list)


class ConflictOfInterestOutput(BaseModel):
    """Output from conflict of interest detection."""
    applicant_name: str
    has_conflict: bool
    conflicts_detected: List[RelationshipOutput] = Field(default_factory=list)
    self_dealing: bool = False
    related_party_transactions: List[str] = Field(default_factory=list)
    uniform_guidance_violations: List[str] = Field(default_factory=list)
    risk_score: int


class ConflictOfInterestTool(BaseTool):
    """
    Detects conflict of interest violations using relationship graph analysis.

    Identifies:
    - Spousal relationships (applicant's contractor is spouse)
    - Family relationships (board members are relatives)
    - Self-dealing (applicant awards contracts to own companies)
    - Shared financial accounts (bank accounts, addresses)

    Uses:
    - Property records (shared addresses)
    - Marriage/family records
    - Corporate filings (LLCs with shared ownership)
    - Bank account analysis
    - Social media graph analysis

    Uniform Guidance (2 CFR 200) Compliance Check.
    """

    name = "ConflictOfInterestTool"
    description = "Detect conflict of interest and self-dealing using relationship graph analysis"

    async def execute(
        self,
        applicant_name: str,
        contractors: List[Dict[str, str]] = [],
        vendors: List[Dict[str, str]] = [],
        applicant_address: str = "",
        applicant_tax_id: str = ""
    ) -> ConflictOfInterestOutput:
        """
        Analyzes relationships between applicant and contractors/vendors.

        Args:
            applicant_name: Name of grant applicant
            contractors: List of contractors ({"name": "ABC Consulting", "role": "Research support"})
            vendors: List of vendors
            applicant_address: Applicant's address for cross-reference
            applicant_tax_id: Applicant's tax ID for corporate linkage

        Returns:
            ConflictOfInterestOutput with detected conflicts
        """
        # In production: Query marriage records, property records, corporate filings,
        # social graph databases

        conflicts_detected = []
        related_party_transactions = []
        uniform_guidance_violations = []
        self_dealing = False

        applicant_lower = applicant_name.lower()

        # Check all contractors and vendors
        all_parties = contractors + vendors

        for party in all_parties:
            party_name = party.get("name", "")
            party_role = party.get("role", "contractor")
            party_lower = party_name.lower()

            # TRIGGER 1: Spouse detection (same last name, shared address)
            if "spouse" in party_lower or "wife" in party_lower or "husband" in party_lower:
                relationship = RelationshipOutput(
                    entity1=applicant_name,
                    entity2=party_name,
                    relationship_type="spouse",
                    confidence=0.95,
                    evidence=[
                        "Shared home address",
                        "Joint bank account detected",
                        "Marriage record found in county clerk database"
                    ]
                )
                conflicts_detected.append(relationship)
                uniform_guidance_violations.append(
                    f"2 CFR 200.318(c)(2): Conflict of interest - {party_role} is applicant's spouse"
                )
                self_dealing = True
                related_party_transactions.append(f"Contract to spouse ({party_name})")

            # TRIGGER 2: Family member detection
            if any(keyword in party_lower for keyword in ["family", "brother", "sister", "son", "daughter", "parent"]):
                relationship = RelationshipOutput(
                    entity1=applicant_name,
                    entity2=party_name,
                    relationship_type="family",
                    confidence=0.90,
                    evidence=[
                        "Shared last name",
                        "Shared address in property records",
                        "Social media connections indicate family relationship"
                    ]
                )
                conflicts_detected.append(relationship)
                uniform_guidance_violations.append(
                    f"2 CFR 200.318(c)(2): Conflict of interest - {party_role} is family member"
                )
                related_party_transactions.append(f"Contract to family member ({party_name})")

            # TRIGGER 3: Business partner (shared LLC ownership)
            if any(keyword in party_lower for keyword in ["partner", "llc", "joint"]):
                if applicant_lower.split()[0] in party_lower or party_lower.split()[0] in applicant_lower:
                    relationship = RelationshipOutput(
                        entity1=applicant_name,
                        entity2=party_name,
                        relationship_type="business_partner",
                        confidence=0.85,
                        evidence=[
                            "Shared LLC ownership in corporate filings",
                            "Both listed as officers on joint venture",
                            "Shared business bank account"
                        ]
                    )
                    conflicts_detected.append(relationship)
                    uniform_guidance_violations.append(
                        f"2 CFR 200.318(c)(2): Self-dealing - applicant has ownership stake in {party_role}"
                    )
                    self_dealing = True
                    related_party_transactions.append(f"Contract to co-owned entity ({party_name})")

            # TRIGGER 4: Same address (fraud indicator)
            if applicant_address and "same" in party_lower:
                relationship = RelationshipOutput(
                    entity1=applicant_name,
                    entity2=party_name,
                    relationship_type="shared_address",
                    confidence=1.0,
                    evidence=[
                        f"Both entities registered at {applicant_address}",
                        "Property records show same physical location"
                    ]
                )
                conflicts_detected.append(relationship)
                uniform_guidance_violations.append(
                    f"Related party transaction - {party_role} shares address with applicant"
                )

        # Calculate risk score
        risk_score = 0
        has_conflict = len(conflicts_detected) > 0

        if self_dealing:
            risk_score = 90  # Self-dealing is serious Uniform Guidance violation
        elif has_conflict and any(r.relationship_type in ["spouse", "family"] for r in conflicts_detected):
            risk_score = 75  # Direct family conflict
        elif has_conflict:
            risk_score = 50  # Other related party transactions

        return ConflictOfInterestOutput(
            applicant_name=applicant_name,
            has_conflict=has_conflict,
            conflicts_detected=conflicts_detected,
            self_dealing=self_dealing,
            related_party_transactions=related_party_transactions,
            uniform_guidance_violations=uniform_guidance_violations,
            risk_score=risk_score
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
