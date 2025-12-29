"""
Veritas Government Fraud Orchestrator - Main FastAPI Application
"""
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging

from app.database import get_db, engine, Base
from app.models import Case, EvidenceLog, AuditLog, CaseStatus
from app.schemas import (
    CaseCreate,
    CaseListResponse,
    CaseDetailResponse,
    CaseAdjudicate,
    PaginatedResponse
)
from app.middleware import AgencyAuthMiddleware, AuditLoggingMiddleware
from app.agent.orchestrator import FraudInvestigationOrchestrator
from app.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Veritas GFO API",
    description="Government Fraud Orchestrator - AI-powered fraud detection system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLoggingMiddleware)
app.add_middleware(AgencyAuthMiddleware)


# Health check endpoint (no auth required)
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "veritas-gfo",
        "version": "0.1.0"
    }


# Background task to run investigation
async def run_investigation(case_id: str, db: Session):
    """
    Background task to run the fraud investigation.

    This runs asynchronously so the API can return immediately.
    """
    try:
        orchestrator = FraudInvestigationOrchestrator(db)
        await orchestrator.investigate(case_id)
        logger.info(f"Investigation completed for case {case_id}")
    except Exception as e:
        logger.error(f"Investigation failed for case {case_id}: {e}")
        # Update case status to indicate failure
        case = db.query(Case).filter(Case.id == case_id).first()
        if case:
            case.status = CaseStatus.REVIEW_REQUIRED
            case.summary_narrative = f"Investigation failed: {str(e)}"
            db.commit()


@app.post("/api/v1/ingest", response_model=CaseListResponse, status_code=status.HTTP_201_CREATED)
async def ingest_case(
    case_data: CaseCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Ingest a new fraud case and trigger investigation.

    This endpoint:
    1. Creates a new case record in the database
    2. Triggers a background investigation workflow
    3. Returns immediately with the case ID

    The investigation runs asynchronously and updates the case status.
    """
    # Create new case
    new_case = Case(
        external_ref_id=case_data.external_ref_id,
        applicant_name=case_data.applicant_name,
        applicant_tax_id=case_data.applicant_tax_id,
        applicant_address=case_data.applicant_address,
        status=CaseStatus.NEW
    )

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Log the ingestion
    audit_log = AuditLog(
        user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
        case_id=new_case.id,
        action="CASE_INGESTED"
    )
    db.add(audit_log)
    db.commit()

    # Trigger background investigation
    background_tasks.add_task(run_investigation, str(new_case.id), db)

    logger.info(f"New case ingested: {new_case.id}")

    return new_case


@app.get("/api/v1/cases", response_model=PaginatedResponse)
async def list_cases(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[CaseStatus] = None,
    min_risk_score: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    List all cases with pagination and filtering.

    Filters:
    - status_filter: Filter by case status (NEW, PROCESSING, REVIEW_REQUIRED, etc.)
    - min_risk_score: Only show cases with risk score >= this value
    """
    query = db.query(Case)

    # Apply filters
    if status_filter:
        query = query.filter(Case.status == status_filter)

    if min_risk_score is not None:
        query = query.filter(Case.final_risk_score >= min_risk_score)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    cases = query.order_by(Case.created_at.desc()).offset(offset).limit(page_size).all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return PaginatedResponse(
        items=cases,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/api/v1/cases/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_id: UUID,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific case.

    Returns:
    - Case metadata
    - All evidence logs with findings
    - Final risk assessment and narrative
    """
    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    # Log the view action
    audit_log = AuditLog(
        user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
        case_id=case.id,
        action="VIEW_CASE"
    )
    db.add(audit_log)
    db.commit()

    return case


@app.post("/api/v1/cases/{case_id}/adjudicate")
async def adjudicate_case(
    case_id: UUID,
    adjudication: CaseAdjudicate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Human adjudication endpoint to approve or deny a case.

    This is the final decision point where a human analyst
    reviews the AI's findings and makes a determination.
    """
    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    # Validate status
    if adjudication.status not in [CaseStatus.APPROVED, CaseStatus.DENIED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be APPROVED or DENIED"
        )

    # Update case
    case.status = adjudication.status

    # Append notes to narrative if provided
    if adjudication.notes:
        case.summary_narrative += f"\n\n---\n**Human Adjudication Notes:**\n{adjudication.notes}"

    db.commit()

    # Log the adjudication
    audit_log = AuditLog(
        user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
        case_id=case.id,
        action=f"ADJUDICATE_{adjudication.status.value}"
    )
    db.add(audit_log)
    db.commit()

    logger.info(f"Case {case_id} adjudicated: {adjudication.status}")

    return {
        "case_id": case_id,
        "status": case.status,
        "message": "Case successfully adjudicated"
    }


@app.get("/api/v1/cases/{case_id}/evidence")
async def get_case_evidence(
    case_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get all evidence logs for a specific case.

    Returns detailed information about each verification step.
    """
    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    evidence_logs = db.query(EvidenceLog).filter(
        EvidenceLog.case_id == case_id
    ).order_by(EvidenceLog.created_at).all()

    return {
        "case_id": case_id,
        "evidence_count": len(evidence_logs),
        "evidence": evidence_logs
    }


@app.get("/api/v1/stats")
async def get_stats(db: Session = Depends(get_db)):
    """
    Get system statistics.

    Returns aggregate metrics about cases and risk levels.
    """
    total_cases = db.query(Case).count()
    pending_review = db.query(Case).filter(
        Case.status == CaseStatus.REVIEW_REQUIRED
    ).count()
    high_risk = db.query(Case).filter(
        Case.final_risk_score >= 70
    ).count()

    return {
        "total_cases": total_cases,
        "pending_review": pending_review,
        "high_risk_cases": high_risk,
        "cases_by_status": {
            status.value: db.query(Case).filter(Case.status == status).count()
            for status in CaseStatus
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
