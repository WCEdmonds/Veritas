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


# Tool Output Schemas
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
