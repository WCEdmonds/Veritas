"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.models import CaseStatus, RiskLevel, VerificationSource


# Case Schemas
class CaseBase(BaseModel):
    """Base case schema."""
    external_ref_id: str
    applicant_name: Optional[str] = None
    applicant_tax_id: Optional[str] = None
    applicant_address: Optional[str] = None


class CaseCreate(CaseBase):
    """Schema for creating a new case."""
    pass


class CaseUpdate(BaseModel):
    """Schema for updating a case."""
    status: Optional[CaseStatus] = None
    final_risk_score: Optional[int] = Field(None, ge=0, le=100)
    summary_narrative: Optional[str] = None


class CaseAdjudicate(BaseModel):
    """Schema for adjudicating a case."""
    status: CaseStatus = Field(..., description="Must be APPROVED or DENIED")
    notes: Optional[str] = None


# Evidence Schemas
class EvidenceLogBase(BaseModel):
    """Base evidence log schema."""
    source: VerificationSource
    raw_data: Optional[dict] = None
    synthesized_finding: Optional[str] = None
    risk_flag: bool = False
    image_url: Optional[str] = None


class EvidenceLogCreate(EvidenceLogBase):
    """Schema for creating evidence log."""
    case_id: UUID


class EvidenceLogResponse(EvidenceLogBase):
    """Schema for evidence log response."""
    id: UUID
    case_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# Case Response Schemas
class CaseListResponse(BaseModel):
    """Schema for case list item."""
    id: UUID
    external_ref_id: str
    applicant_name: Optional[str]
    status: CaseStatus
    final_risk_score: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class CaseDetailResponse(CaseBase):
    """Schema for detailed case response."""
    id: UUID
    status: CaseStatus
    final_risk_score: Optional[int]
    summary_narrative: Optional[str]
    created_at: datetime
    evidence_logs: List[EvidenceLogResponse] = []

    class Config:
        from_attributes = True


# Pagination
class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[CaseListResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# Tool Output Schemas - Expanded Toolset

# Layer 1: Physical Verification Tools
class StreetViewVisionOutput(BaseModel):
    """Output from Street View Vision tool."""
    building_type: str  # residential, industrial, office, retail
    signage_detected: bool
    visual_risk_flag: bool  # True if residential but business is industrial
    image_url: str
    description: str


class PropertyOwnerOutput(BaseModel):
    """Output from Property Owner tool."""
    owner_name: str
    last_sale_date: Optional[str] = None
    zoning_code: Optional[str] = None
    related_party_risk: bool  # If owner name fuzzy matches applicant name


# Layer 2: Corporate Verification Tools
class RegistryStatusOutput(BaseModel):
    """Output from Registry Status tool."""
    legal_name: str
    incorporation_date: str
    status: str  # Active/Dissolved
    days_since_incorp: int


class DomainForensicsOutput(BaseModel):
    """Output from Domain Forensics tool."""
    domain_age_days: int
    is_template_site: bool
    registrar: str
    risk_score: int = Field(ge=0, le=100)


class WebContentScraperOutput(BaseModel):
    """Output from Web Content Scraper tool."""
    has_lorem_ipsum: bool
    staff_count_mentioned: int
    consistency_score: int = Field(ge=0, le=100)  # Low score = fake site
    about_us_text: Optional[str] = None


# Layer 3: Digital Identity Tools
class PhoneCarrierOutput(BaseModel):
    """Output from Phone Carrier tool."""
    carrier: str
    line_type: str  # VOIP, MOBILE, LANDLINE
    risk_flag: bool  # True if VOIP


class EmailDigitalFootprintOutput(BaseModel):
    """Output from Email Digital Footprint tool."""
    registered_profiles: List[str]
    profile_count: int
    social_score: str  # LOW, MEDIUM, HIGH


class BreachHistoryOutput(BaseModel):
    """Output from Breach History tool."""
    breach_count: int
    synthetic_identity_suspicion: str  # LOW, MEDIUM, HIGH


# Layer 4: Document Forensics Tools
class PDFMetadataOutput(BaseModel):
    """Output from PDF Metadata tool."""
    software_tool: str
    creation_date: Optional[str] = None
    modified_date: Optional[str] = None
    is_manipulated: bool


# Layer 5: Cross-Case Intelligence & Network Analysis
class VectorSimilarityOutput(BaseModel):
    """Output from Vector Similarity tool (plagiarism detection)."""
    similar_cases_count: int
    top_matches: List[dict]  # [{case_id, similarity_score, excerpt}]
    is_plagiarized: bool  # True if similarity > threshold
    plagiarism_score: float = Field(ge=0.0, le=1.0)
    narrative_excerpt: str


class JobBoardScraperOutput(BaseModel):
    """Output from Job Board Scraper tool."""
    total_job_postings: int
    recent_postings_30d: int
    recent_postings_90d: int
    posting_platforms: List[str]  # ["indeed", "linkedin"]
    is_actively_hiring: bool
    growth_claim_verified: bool  # Matches claimed growth


class EmployeeGhostCheckOutput(BaseModel):
    """Output from Employee Ghost Check tool."""
    total_employees_claimed: int
    employees_verified: int
    deceased_employees: int
    duplicate_ssn_employees: int
    ghost_employees: List[dict]  # [{name, ssn_last4, issue}]
    verification_rate: float = Field(ge=0.0, le=1.0)


class GraphNetworkOutput(BaseModel):
    """Output from Graph Network Analysis tool."""
    connected_entities_count: int
    fraud_ring_detected: bool
    shared_attributes: List[str]  # ["phone", "email", "address"]
    related_cases: List[dict]  # [{case_id, relationship, shared_data}]
    network_risk_score: int = Field(ge=0, le=100)


# Legacy Tool Output Schemas (for backwards compatibility)
class GoogleStreetViewOutput(BaseModel):
    """Output from Google Street View tool."""
    is_commercial: bool
    building_description: str
    image_url: str
    confidence: float = Field(ge=0.0, le=1.0)


class CorpRegistryOutput(BaseModel):
    """Output from Corporate Registry tool."""
    status: str  # Active/Dissolved
    incorporation_date: Optional[str] = None
    agent_name: Optional[str] = None
    jurisdiction: Optional[str] = None


class PeopleVerificationOutput(BaseModel):
    """Output from People Verification tool."""
    identity_verified: bool
    deceased: bool
    address_match: bool
    confidence_score: float = Field(ge=0.0, le=1.0)


# Agent State Schema
class AgentState(BaseModel):
    """State maintained by the agent orchestrator."""
    case_id: UUID
    case_data: dict
    tool_outputs: List[dict] = []
    investigation_log: List[str] = []
    final_verdict: Optional[dict] = None
    current_step: str = "planner"
