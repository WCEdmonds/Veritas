"""
Database initialization script.

Creates tables and optionally adds test data.
"""
import asyncio
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal, Base
from app.models import Case, CaseStatus
from app.agent.orchestrator import FraudInvestigationOrchestrator


def init_database():
    """Create all database tables."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def create_test_case(db: Session) -> str:
    """Create a test case for demonstration."""
    print("\nCreating test case...")

    test_case = Case(
        external_ref_id="DEMO-2024-001",
        applicant_name="QuickStart Solutions LLC",
        applicant_tax_id="98-7654321",
        applicant_address="456 Business Park Drive, Suite 200, Austin, TX 78701",
        status=CaseStatus.NEW
    )

    db.add(test_case)
    db.commit()
    db.refresh(test_case)

    print(f"✓ Test case created: {test_case.id}")
    print(f"  External Ref: {test_case.external_ref_id}")
    print(f"  Applicant: {test_case.applicant_name}")

    return str(test_case.id)


async def run_test_investigation(case_id: str, db: Session):
    """Run investigation on test case."""
    print(f"\nRunning investigation on case {case_id}...")

    orchestrator = FraudInvestigationOrchestrator(db)

    try:
        result = await orchestrator.investigate(case_id)
        print("✓ Investigation completed")
        print(f"  Risk Score: {result.get('risk_score')}")
        print(f"  Risk Level: {result.get('risk_level')}")
        print(f"  Recommendation: {result.get('recommendation')}")
    except Exception as e:
        print(f"✗ Investigation failed: {e}")


def main():
    """Main initialization function."""
    print("=" * 60)
    print("Veritas GFO - Database Initialization")
    print("=" * 60)

    # Initialize database
    init_database()

    # Ask if user wants to create test data
    response = input("\nCreate test case? (y/n): ").strip().lower()

    if response == 'y':
        db = SessionLocal()
        try:
            case_id = create_test_case(db)

            # Ask if user wants to run investigation
            response = input("\nRun investigation on test case? (y/n): ").strip().lower()

            if response == 'y':
                asyncio.run(run_test_investigation(case_id, db))
        finally:
            db.close()

    print("\n" + "=" * 60)
    print("Initialization complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start the API server: uvicorn app.main:app --reload")
    print("2. Open the frontend: http://localhost:3000")
    print("3. View API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
