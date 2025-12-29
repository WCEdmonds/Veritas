"""Database models for Veritas GFO."""
from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid

from app.database import Base


class CaseType(str, enum.Enum):
    """Type of fraud investigation."""
    GRANT = "GRANT"  # Business grant/loan fraud
    UNEMPLOYMENT = "UNEMPLOYMENT"  # Unemployment insurance fraud
    BENEFITS = "BENEFITS"  # General benefits fraud (SNAP, housing, etc.)


class CaseStatus(str, enum.Enum):
    """Case processing status."""
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class RiskLevel(str, enum.Enum):
    """Risk assessment levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class VerificationSource(str, enum.Enum):
    """Sources of verification data."""
    GOOGLE_MAPS = "GOOGLE_MAPS"
    OPENCORPORATES = "OPENCORPORATES"
    LEXIS_NEXIS = "LEXIS_NEXIS"
    LINKEDIN_PROXY = "LINKEDIN_PROXY"
    DOC_ANALYSIS = "DOC_ANALYSIS"


class Case(Base):
    """Main investigation unit representing a fraud case."""
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref_id = Column(String(255), nullable=False, index=True)

    # Case type and common fields
    case_type = Column(SQLEnum(CaseType), default=CaseType.GRANT, index=True)
    applicant_name = Column(String(255))
    applicant_address = Column(Text)

    # Grant/Loan-specific fields
    applicant_tax_id = Column(String(50))  # EIN for businesses

    # Unemployment/Benefits-specific fields
    applicant_ssn = Column(String(11))  # SSN for individuals (encrypted in production)
    applicant_dob = Column(String(10))  # Date of birth (YYYY-MM-DD)
    applicant_phone = Column(String(20))
    applicant_email = Column(String(255))
    previous_employer = Column(String(255))  # For unemployment claims
    claim_amount = Column(Integer)  # Weekly benefit amount or grant amount

    # Investigation results
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(SQLEnum(CaseStatus), default=CaseStatus.NEW, index=True)
    final_risk_score = Column(Integer)  # 0-100
    summary_narrative = Column(Text)  # LLM generated conclusion

    # Relationships
    evidence_logs = relationship("EvidenceLog", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")


class EvidenceLog(Base):
    """Evidence gathered by investigative tools."""
    __tablename__ = "evidence_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True)
    source = Column(SQLEnum(VerificationSource), nullable=False)
    raw_data = Column(JSONB)  # Full JSON response from API
    synthesized_finding = Column(Text)  # Agent's takeaway
    risk_flag = Column(Boolean, default=False)  # Did this tool find a problem?
    image_url = Column(Text)  # For stored Street View screenshots
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    case = relationship("Case", back_populates="evidence_logs")


class AuditLog(Base):
    """Audit trail for all actions (crucial for government compliance)."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True))  # If human action
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), index=True)
    action = Column(String(50))  # e.g., "OVERRIDE_AGENT", "VIEW_CASE"
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    case = relationship("Case", back_populates="audit_logs")
