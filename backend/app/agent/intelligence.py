"""
Layer 5: Cross-Case Intelligence & Network Analysis

Tools that analyze patterns across multiple cases to detect:
- Plagiarized narratives (fraud rings using scripts)
- Fraud networks (shared phone/email/address)
- Employee verification against death records
- Job posting activity vs growth claims
"""
import httpx
from typing import Dict, Any, List
from datetime import datetime, timedelta
import hashlib

from app.config import settings
from app.schemas import (
    VectorSimilarityOutput,
    JobBoardScraperOutput,
    EmployeeGhostCheckOutput,
    GraphNetworkOutput
)
from app.agent.base import BaseTool


class VectorSimilarityTool(BaseTool):
    """
    Detect plagiarized application narratives using vector similarity search.

    Fraud rings often use the same "hardship story" script across multiple
    applications. This tool embeds narratives and finds semantic duplicates.
    """

    def __init__(self, vector_db=None):
        super().__init__()
        self.vector_db = vector_db  # ChromaDB or Pinecone client
        self.similarity_threshold = 0.85  # 85% similarity = plagiarism

    async def execute(
        self,
        narrative_text: str,
        case_id: str = None
    ) -> VectorSimilarityOutput:
        """
        Check if narrative appears in other applications.

        Args:
            narrative_text: The hardship/business story text
            case_id: Current case ID (optional)

        Returns:
            VectorSimilarityOutput with plagiarism detection results
        """
        if not self.vector_db:
            # Use mock for MVP
            return await self._mock_response(narrative_text, case_id)

        try:
            # Embed the narrative
            embedding = await self._embed_text(narrative_text)

            # Search for similar past narratives
            results = self.vector_db.query(
                query_embeddings=[embedding],
                n_results=10,
                where={"case_id": {"$ne": case_id}} if case_id else None
            )

            # Process results
            top_matches = []
            for i, (distance, metadata) in enumerate(zip(results['distances'][0], results['metadatas'][0])):
                similarity = 1 - distance  # Convert distance to similarity
                if similarity > self.similarity_threshold:
                    top_matches.append({
                        "case_id": metadata.get("case_id"),
                        "similarity_score": round(similarity, 3),
                        "excerpt": metadata.get("excerpt", "")[:200]
                    })

            is_plagiarized = len(top_matches) > 0
            plagiarism_score = max([m["similarity_score"] for m in top_matches], default=0.0)

            return VectorSimilarityOutput(
                similar_cases_count=len(top_matches),
                top_matches=top_matches,
                is_plagiarized=is_plagiarized,
                plagiarism_score=plagiarism_score,
                narrative_excerpt=narrative_text[:200]
            )

        except Exception as e:
            print(f"Error in VectorSimilarityTool: {e}")
            return await self._mock_response(narrative_text, case_id)

    async def _embed_text(self, text: str) -> List[float]:
        """Generate embedding using OpenAI/Sentence Transformers."""
        from langchain.embeddings import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(openai_api_key=settings.openai_api_key)
        return embeddings.embed_query(text)

    async def _mock_response(
        self,
        narrative_text: str,
        case_id: str = None
    ) -> VectorSimilarityOutput:
        """
        Mock plagiarism detection.

        Triggers:
        - Text contains "rare disease" → Plagiarized (fraud ring script)
        - Text contains "hurricane" → Plagiarized (copy-paste disaster claims)
        - Generic text → Original
        """
        text_lower = narrative_text.lower()

        # Fraud trigger: Specific rare stories that appear multiple times
        if "rare disease" in text_lower or "specific hardship" in text_lower:
            return VectorSimilarityOutput(
                similar_cases_count=47,
                top_matches=[
                    {
                        "case_id": "CASE-2024-001",
                        "similarity_score": 0.94,
                        "excerpt": "My son was diagnosed with the same rare disease..."
                    },
                    {
                        "case_id": "CASE-2024-012",
                        "similarity_score": 0.91,
                        "excerpt": "After my son's rare disease diagnosis..."
                    },
                    {
                        "case_id": "CASE-2024-023",
                        "similarity_score": 0.89,
                        "excerpt": "When my son got the rare disease..."
                    }
                ],
                is_plagiarized=True,
                plagiarism_score=0.94,
                narrative_excerpt=narrative_text[:200]
            )

        # Hurricane/disaster fraud rings
        if "hurricane" in text_lower and "lost everything" in text_lower:
            return VectorSimilarityOutput(
                similar_cases_count=23,
                top_matches=[
                    {
                        "case_id": "CASE-2024-034",
                        "similarity_score": 0.88,
                        "excerpt": "After Hurricane XYZ, we lost everything..."
                    }
                ],
                is_plagiarized=True,
                plagiarism_score=0.88,
                narrative_excerpt=narrative_text[:200]
            )

        # Original narrative
        return VectorSimilarityOutput(
            similar_cases_count=0,
            top_matches=[],
            is_plagiarized=False,
            plagiarism_score=0.0,
            narrative_excerpt=narrative_text[:200]
        )


class JobBoardScraperTool(BaseTool):
    """
    Verify employment growth claims via job board activity.

    Companies claiming "rapid growth" and "50 employees" should be
    actively hiring. No job postings in 2 years = likely shell company.
    """

    def __init__(self):
        super().__init__()
        # In production: Use SerpAPI or direct scraping

    async def execute(
        self,
        company_name: str,
        claimed_employees: int = None
    ) -> JobBoardScraperOutput:
        """
        Search job boards for hiring activity.

        Args:
            company_name: Company to search for
            claimed_employees: Number of employees claimed (optional)

        Returns:
            JobBoardScraperOutput with hiring verification
        """
        # MVP: Use mock data
        return await self._mock_response(company_name, claimed_employees)

    async def _scrape_indeed(self, company_name: str) -> List[dict]:
        """Scrape Indeed for job postings (production implementation)."""
        # In production: Use SerpAPI or requests + BeautifulSoup
        pass

    async def _scrape_linkedin(self, company_name: str) -> List[dict]:
        """Scrape LinkedIn Jobs (production implementation)."""
        # In production: Use LinkedIn API or scraping
        pass

    async def _mock_response(
        self,
        company_name: str,
        claimed_employees: int = None
    ) -> JobBoardScraperOutput:
        """
        Mock job board data.

        Triggers:
        - "QuickStart" in name → No job postings (shell company)
        - "Growing" in name but no posts → Growth claim unverified
        - "Legacy" or "Professional" → Active hiring
        """
        name_lower = company_name.lower()

        # Fraud trigger: No hiring activity despite growth claims
        if "quickstart" in name_lower or "shell" in name_lower:
            return JobBoardScraperOutput(
                total_job_postings=0,
                recent_postings_30d=0,
                recent_postings_90d=0,
                posting_platforms=[],
                is_actively_hiring=False,
                growth_claim_verified=False
            )

        # Red flag: Claims growth but no hiring
        if "growing" in name_lower or (claimed_employees and claimed_employees > 20):
            return JobBoardScraperOutput(
                total_job_postings=1,
                recent_postings_30d=0,
                recent_postings_90d=0,
                posting_platforms=["indeed"],
                is_actively_hiring=False,
                growth_claim_verified=False  # Claims growth but not hiring
            )

        # Normal: Established company with hiring activity
        return JobBoardScraperOutput(
            total_job_postings=15,
            recent_postings_30d=3,
            recent_postings_90d=8,
            posting_platforms=["indeed", "linkedin", "glassdoor"],
            is_actively_hiring=True,
            growth_claim_verified=True
        )


class EmployeeGhostCheckTool(BaseTool):
    """
    Verify employees are real via Death Master File and payroll data.

    Fraud rings list deceased people or duplicate SSNs as "employees"
    to inflate headcount for grants.
    """

    def __init__(self):
        super().__init__()
        # In production: Use Argyle/Pinwheel for payroll verification
        # Use SSA Death Master File for deceased check

    async def execute(
        self,
        employee_list: List[dict]
    ) -> EmployeeGhostCheckOutput:
        """
        Verify employees against death records and payroll systems.

        Args:
            employee_list: [{name, ssn_last4, role}]

        Returns:
            EmployeeGhostCheckOutput with verification results
        """
        # MVP: Use mock data
        return await self._mock_response(employee_list)

    async def _check_death_master_file(self, ssn: str) -> bool:
        """Check if SSN appears in Death Master File (production)."""
        # In production: Query SSA Death Master File API
        pass

    async def _check_payroll_systems(self, ssn: str) -> dict:
        """Check active payroll via Argyle/Pinwheel (production)."""
        # In production: Use Argyle API to verify active employment
        pass

    async def _mock_response(
        self,
        employee_list: List[dict]
    ) -> EmployeeGhostCheckOutput:
        """
        Mock employee verification.

        Triggers:
        - Employee name contains "Ghost" → Deceased
        - Employee name contains "Duplicate" → Duplicate SSN
        - SSN "000-00-0000" → Fake
        """
        total_claimed = len(employee_list)
        deceased = []
        duplicates = []
        verified = 0

        for emp in employee_list:
            name = emp.get("name", "").lower()
            ssn = emp.get("ssn_last4", "")

            # Check for fraud indicators
            if "ghost" in name or ssn == "0000":
                deceased.append({
                    "name": emp.get("name"),
                    "ssn_last4": ssn,
                    "issue": "DECEASED (Death Master File)"
                })
            elif "duplicate" in name:
                duplicates.append({
                    "name": emp.get("name"),
                    "ssn_last4": ssn,
                    "issue": "DUPLICATE SSN"
                })
            else:
                verified += 1

        ghost_employees = deceased + duplicates
        verification_rate = verified / total_claimed if total_claimed > 0 else 0.0

        return EmployeeGhostCheckOutput(
            total_employees_claimed=total_claimed,
            employees_verified=verified,
            deceased_employees=len(deceased),
            duplicate_ssn_employees=len(duplicates),
            ghost_employees=ghost_employees,
            verification_rate=verification_rate
        )


class GraphNetworkTool(BaseTool):
    """
    Detect fraud rings via graph database network analysis.

    Maps all cases into a graph (Neo4j) and finds connected components
    based on shared phone numbers, emails, addresses, and IPs.
    """

    def __init__(self, neo4j_driver=None):
        super().__init__()
        self.neo4j = neo4j_driver
        self.fraud_threshold = 3  # 3+ shared attributes = fraud ring

    async def execute(
        self,
        case_id: str,
        phone: str = None,
        email: str = None,
        address: str = None,
        ip_address: str = None
    ) -> GraphNetworkOutput:
        """
        Search graph database for connected cases (fraud rings).

        Args:
            case_id: Current case ID
            phone: Phone number
            email: Email address
            address: Physical address
            ip_address: IP address from application

        Returns:
            GraphNetworkOutput with fraud ring detection
        """
        if not self.neo4j:
            # Use mock for MVP
            return await self._mock_response(case_id, phone, email, address, ip_address)

        try:
            # Query Neo4j for connected cases
            query = """
            MATCH (c:Case {id: $case_id})-[r:SHARES_ATTRIBUTE]-(connected:Case)
            RETURN connected.id as case_id,
                   type(r) as relationship,
                   r.attribute as shared_data
            """

            results = self.neo4j.run(query, case_id=case_id)

            # Process results
            related_cases = []
            shared_attrs = set()

            for record in results:
                related_cases.append({
                    "case_id": record["case_id"],
                    "relationship": record["relationship"],
                    "shared_data": record["shared_data"]
                })
                shared_attrs.add(record["relationship"])

            fraud_ring_detected = len(shared_attrs) >= self.fraud_threshold
            network_risk = min(len(related_cases) * 15, 100)

            return GraphNetworkOutput(
                connected_entities_count=len(related_cases),
                fraud_ring_detected=fraud_ring_detected,
                shared_attributes=list(shared_attrs),
                related_cases=related_cases[:10],  # Limit to top 10
                network_risk_score=network_risk
            )

        except Exception as e:
            print(f"Error in GraphNetworkTool: {e}")
            return await self._mock_response(case_id, phone, email, address, ip_address)

    async def _mock_response(
        self,
        case_id: str,
        phone: str = None,
        email: str = None,
        address: str = None,
        ip_address: str = None
    ) -> GraphNetworkOutput:
        """
        Mock fraud ring detection.

        Triggers:
        - Phone contains "555" → Shared across 14 cases (fraud ring)
        - Email domain is "fraud.com" → Part of network
        - Normal data → No connections
        """
        # Fraud trigger: Shared phone number across cases
        if phone and "555" in phone:
            return GraphNetworkOutput(
                connected_entities_count=14,
                fraud_ring_detected=True,
                shared_attributes=["phone", "backup_email", "ip_address"],
                related_cases=[
                    {
                        "case_id": "CASE-2024-001",
                        "relationship": "SHARED_PHONE",
                        "shared_data": phone
                    },
                    {
                        "case_id": "CASE-2024-007",
                        "relationship": "SHARED_PHONE",
                        "shared_data": phone
                    },
                    {
                        "case_id": "CASE-2024-012",
                        "relationship": "SHARED_BACKUP_EMAIL",
                        "shared_data": "backup@fraud.com"
                    }
                ],
                network_risk_score=85
            )

        # Fraud trigger: Email domain appears in multiple cases
        if email and "fraud" in email.lower():
            return GraphNetworkOutput(
                connected_entities_count=7,
                fraud_ring_detected=True,
                shared_attributes=["email_domain", "ip_address"],
                related_cases=[
                    {
                        "case_id": "CASE-2024-003",
                        "relationship": "SHARED_EMAIL_DOMAIN",
                        "shared_data": email.split("@")[1]
                    }
                ],
                network_risk_score=60
            )

        # Normal: No fraud ring detected
        return GraphNetworkOutput(
            connected_entities_count=0,
            fraud_ring_detected=False,
            shared_attributes=[],
            related_cases=[],
            network_risk_score=0
        )
