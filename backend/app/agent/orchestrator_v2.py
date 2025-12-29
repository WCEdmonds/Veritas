"""
Enhanced LangGraph-based Agent Orchestrator with 5-Layer Investigation.

Implements comprehensive fraud detection using:
- Layer 1: Physical Verification
- Layer 2: Corporate Verification
- Layer 3: Digital Identity
- Layer 4: Document Forensics (Basic + Advanced)
- Layer 5: Cross-Case Intelligence

Uses sophisticated Risk Matrix scoring with weighted factors.
"""
from typing import Dict, Any, List, TypedDict
import asyncio
from datetime import datetime
import json

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Case, EvidenceLog, VerificationSource, CaseStatus, CaseType

# Import all investigative tools
from app.agent.physical import StreetViewVisionTool, PropertyOwnerTool
from app.agent.corporate import RegistryStatusTool, DomainForensicsTool, WebContentScraperTool
from app.agent.identity import PhoneCarrierTool, EmailDigitalFootprintTool, BreachHistoryTool
from app.agent.forensics import PDFMetadataTool
from app.agent.forensics_advanced import ForensicPipeline
from app.agent.intelligence import (
    VectorSimilarityTool,
    JobBoardScraperTool,
    EmployeeGhostCheckTool,
    GraphNetworkTool
)
from app.agent.unemployment import (
    SSNValidationTool,
    EmployerVerificationTool,
    CrossStateClaimCheckTool,
    PrisonInmateCheckTool,
    AddressHistoryTool
)


class InvestigationState(TypedDict):
    """State passed between agent nodes."""
    case_id: str
    case_data: Dict[str, Any]
    tool_outputs: Dict[str, Any]  # Changed to dict for easier access by tool name
    investigation_log: List[str]
    final_verdict: Dict[str, Any]
    current_step: str
    next_tools: List[str]


class EnhancedFraudInvestigationOrchestrator:
    """
    Enhanced orchestrator with 4-layer investigation and risk matrix scoring.
    """

    # Tool registry mapping tool names to classes
    TOOL_REGISTRY = {
        # Layer 1: Physical
        "street_view_vision": StreetViewVisionTool,
        "property_owner": PropertyOwnerTool,

        # Layer 2: Corporate (Grant/Loan fraud)
        "registry_status": RegistryStatusTool,
        "domain_forensics": DomainForensicsTool,
        "web_content_scraper": WebContentScraperTool,

        # Layer 2: Identity/Employment (Unemployment/Benefits fraud)
        "ssn_validation": SSNValidationTool,
        "employer_verification": EmployerVerificationTool,
        "cross_state_claim_check": CrossStateClaimCheckTool,
        "prison_inmate_check": PrisonInmateCheckTool,
        "address_history": AddressHistoryTool,

        # Layer 3: Identity (All case types)
        "phone_carrier": PhoneCarrierTool,
        "email_footprint": EmailDigitalFootprintTool,
        "breach_history": BreachHistoryTool,

        # Layer 4: Forensics (Basic)
        "pdf_metadata": PDFMetadataTool,

        # Layer 5: Cross-Case Intelligence
        "vector_similarity": VectorSimilarityTool,
        "job_board_scraper": JobBoardScraperTool,
        "employee_ghost_check": EmployeeGhostCheckTool,
        "graph_network": GraphNetworkTool,
    }

    def __init__(self, db: Session):
        self.db = db
        self.llm = self._initialize_llm()
        self.forensic_pipeline = ForensicPipeline()
        self.graph = self._build_graph()

    def _initialize_llm(self):
        """Initialize the LLM based on configured provider."""
        if settings.llm_provider == "anthropic":
            return ChatAnthropic(
                model=settings.llm_model or "claude-3-sonnet-20240229",
                api_key=settings.anthropic_api_key,
                temperature=settings.llm_temperature
            )
        else:
            return ChatOpenAI(
                model=settings.llm_model or "gpt-4-turbo-preview",
                api_key=settings.openai_api_key,
                temperature=settings.llm_temperature
            )

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(InvestigationState)

        # Add nodes
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("reporter", self._reporter_node)

        # Define edges (simplified: no analyzer loop for MVP)
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "reporter")
        workflow.add_edge("reporter", END)

        return workflow.compile()

    async def investigate(self, case_id: str) -> Dict[str, Any]:
        """Run the full investigation workflow for a case."""
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Update status
        case.status = CaseStatus.PROCESSING
        self.db.commit()

        # Initialize state
        initial_state: InvestigationState = {
            "case_id": str(case_id),
            "case_data": {
                "applicant_name": case.applicant_name,
                "applicant_tax_id": case.applicant_tax_id,
                "applicant_address": case.applicant_address,
                "external_ref_id": case.external_ref_id,
            },
            "tool_outputs": {},
            "investigation_log": [],
            "final_verdict": {},
            "current_step": "planner",
            "next_tools": [],
        }

        # Run the graph
        result = await self.graph.ainvoke(initial_state)

        # Update case with final results
        case.final_risk_score = result["final_verdict"].get("risk_score", 0)
        case.summary_narrative = result["final_verdict"].get("narrative", "")
        case.status = CaseStatus.REVIEW_REQUIRED
        self.db.commit()

        return result["final_verdict"]

    async def _planner_node(self, state: InvestigationState) -> InvestigationState:
        """
        Planner: Selects comprehensive toolset based on case type.

        Different tools for:
        - GRANT: Business fraud detection (corporate, domain, employment verification)
        - UNEMPLOYMENT/BENEFITS: Individual fraud detection (identity, SSN, employment history)
        """
        case_data = state["case_data"]
        case_type = case_data.get("case_type", "GRANT")  # Default to GRANT for backwards compatibility

        tools_to_run = []

        # === COMMON TOOLS (All Case Types) ===

        # Layer 1: Physical verification (always relevant)
        if case_data.get("applicant_address"):
            tools_to_run.append("street_view_vision")  # Verify address exists/is residential vs commercial

        # Layer 3: Identity verification (always relevant)
        tools_to_run.extend([
            "phone_carrier",      # VOIP detection
            "email_footprint",    # Social media presence
            "breach_history",     # Compromised credentials
        ])

        # Layer 4: Document forensics (always relevant)
        tools_to_run.append("pdf_metadata")          # Basic manipulation detection
        tools_to_run.append("advanced_forensics")    # Advanced forgery detection

        # Layer 5: Cross-case intelligence (always relevant)
        tools_to_run.extend([
            "vector_similarity",     # Plagiarism detection
            "employee_ghost_check",  # Death Master File
            "graph_network",         # Fraud ring detection
        ])

        # === CASE TYPE-SPECIFIC TOOLS ===

        if case_type == "GRANT":
            # Business grant/loan fraud - focus on corporate verification
            tools_to_run.extend([
                "registry_status",      # Company formation date
                "domain_forensics",     # Website age
                "web_content_scraper",  # Lorem Ipsum detection
                "property_owner",       # Related party transactions
                "job_board_scraper",    # Growth verification via hiring
            ])

        elif case_type in ["UNEMPLOYMENT", "BENEFITS"]:
            # Individual benefits fraud - focus on identity & employment
            tools_to_run.extend([
                "ssn_validation",           # SSN authenticity & Death Master File
                "employer_verification",    # Verify previous employer
                "cross_state_claim_check",  # Multi-state fraud detection
                "prison_inmate_check",      # Incarceration check
                "address_history",          # Fraud ring address detection
            ])

        state["next_tools"] = tools_to_run
        state["investigation_log"].append(
            f"Planner selected {len(tools_to_run)} tools for {case_type} investigation"
        )

        return state

    async def _executor_node(self, state: InvestigationState) -> InvestigationState:
        """
        Executor: Runs all selected tools in parallel.
        """
        tools_to_run = state["next_tools"]
        case_data = state["case_data"]

        # Build tasks for parallel execution
        tasks = []
        tool_names = []

        for tool_name in tools_to_run:
            if tool_name not in self.TOOL_REGISTRY:
                continue

            tool_class = self.TOOL_REGISTRY[tool_name]
            tool = tool_class()

            # Determine arguments based on tool type
            task = self._create_tool_task(tool, tool_name, case_data)
            if task:
                tasks.append(task)
                tool_names.append(tool_name)

        # Execute all tools in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for tool_name, result in zip(tool_names, results):
            if isinstance(result, Exception):
                state["investigation_log"].append(f"Tool {tool_name} failed: {str(result)}")
                continue

            # Store tool output
            state["tool_outputs"][tool_name] = result

            # Save evidence to database
            evidence = self._create_evidence_log(state["case_id"], tool_name, result)
            self.db.add(evidence)

        self.db.commit()

        state["investigation_log"].append(f"Executed {len(tool_names)} tools successfully")

        return state

    def _create_tool_task(self, tool, tool_name: str, case_data: Dict[str, Any]):
        """Create appropriate async task for tool execution."""
        applicant_name = case_data.get("applicant_name", "")
        applicant_address = case_data.get("applicant_address", "")

        if tool_name == "street_view_vision":
            return tool.execute(address=applicant_address, claimed_industry="business")
        elif tool_name == "property_owner":
            return tool.execute(address=applicant_address, applicant_name=applicant_name)
        elif tool_name == "registry_status":
            return tool.execute(company_name=applicant_name)
        elif tool_name == "domain_forensics":
            # Extract domain from company name (simplified)
            domain = applicant_name.lower().replace(" ", "").replace("llc", "").replace("inc", "") + ".com"
            return tool.execute(domain=domain)
        elif tool_name == "web_content_scraper":
            website = f"https://{applicant_name.lower().replace(' ', '')}.com"
            return tool.execute(website_url=website)
        elif tool_name == "phone_carrier":
            # In production, would come from application data
            return tool.execute(phone_number="555-0100")
        elif tool_name == "email_footprint":
            # In production, would come from application data
            email = f"contact@{applicant_name.lower().replace(' ', '')}.com"
            return tool.execute(email=email)
        elif tool_name == "breach_history":
            email = f"contact@{applicant_name.lower().replace(' ', '')}.com"
            return tool.execute(email=email, age=35)
        elif tool_name == "pdf_metadata":
            # In production, would analyze uploaded documents
            return tool.execute(document_path="/fake/bank_statement.pdf")
        elif tool_name == "advanced_forensics":
            # Run ForensicPipeline for advanced document analysis
            return self.forensic_pipeline.analyze_document(
                file_path="/fake/bank_statement.pdf",
                file_type="auto"
            )
        elif tool_name == "vector_similarity":
            # In production, would use actual application narrative
            narrative = f"Application from {applicant_name} for business expansion grant"
            return tool.execute(narrative_text=narrative, case_id=case_data.get("case_id", ""))
        elif tool_name == "job_board_scraper":
            # In production, would extract from application data
            claimed_employees = 50
            return tool.execute(company_name=applicant_name, claimed_employees=claimed_employees)
        elif tool_name == "employee_ghost_check":
            # In production, would use actual employee list
            employee_list = [
                {"name": "John Doe", "ssn_last4": "1234", "role": "Manager"}
            ]
            return tool.execute(employee_list=employee_list)
        elif tool_name == "graph_network":
            # In production, would extract from application data
            phone = "555-0100"
            email = f"contact@{applicant_name.lower().replace(' ', '')}.com"
            return tool.execute(
                case_id=case_data.get("case_id", ""),
                phone=phone,
                email=email,
                address=applicant_address,
                ip_address="192.168.1.1"
            )
        elif tool_name == "ssn_validation":
            # In production, would come from case data
            ssn = case_data.get("applicant_ssn", "123-45-6789")
            dob = case_data.get("applicant_dob", "1980-01-01")
            return tool.execute(ssn=ssn, name=applicant_name, dob=dob)
        elif tool_name == "employer_verification":
            # In production, would come from claim data
            employer = case_data.get("previous_employer", "Acme Corporation")
            ssn = case_data.get("applicant_ssn", "123-45-6789")
            return tool.execute(
                employer_name=employer,
                claimant_name=applicant_name,
                claimant_ssn=ssn,
                claimed_termination_date="2024-01-15"
            )
        elif tool_name == "cross_state_claim_check":
            ssn = case_data.get("applicant_ssn", "123-45-6789")
            return tool.execute(
                ssn=ssn,
                name=applicant_name,
                current_state="CA"
            )
        elif tool_name == "prison_inmate_check":
            ssn = case_data.get("applicant_ssn", "123-45-6789")
            dob = case_data.get("applicant_dob", "1980-01-01")
            return tool.execute(
                name=applicant_name,
                dob=dob,
                ssn=ssn,
                state="CA"
            )
        elif tool_name == "address_history":
            ssn = case_data.get("applicant_ssn", "123-45-6789")
            return tool.execute(
                current_address=applicant_address,
                name=applicant_name,
                ssn=ssn
            )

        return None

    def _create_evidence_log(
        self,
        case_id: str,
        tool_name: str,
        result: Any
    ) -> EvidenceLog:
        """Create evidence log entry from tool result."""
        # Map tool names to verification sources
        source_mapping = {
            "street_view_vision": VerificationSource.GOOGLE_MAPS,
            "property_owner": VerificationSource.GOOGLE_MAPS,
            "registry_status": VerificationSource.OPENCORPORATES,
            "domain_forensics": VerificationSource.OPENCORPORATES,
            "web_content_scraper": VerificationSource.OPENCORPORATES,
            "phone_carrier": VerificationSource.LEXIS_NEXIS,
            "email_footprint": VerificationSource.LEXIS_NEXIS,
            "breach_history": VerificationSource.LEXIS_NEXIS,
            "pdf_metadata": VerificationSource.DOC_ANALYSIS,
            "advanced_forensics": VerificationSource.DOC_ANALYSIS,
            "vector_similarity": VerificationSource.DOC_ANALYSIS,
            "job_board_scraper": VerificationSource.OPENCORPORATES,
            "employee_ghost_check": VerificationSource.LEXIS_NEXIS,
            "graph_network": VerificationSource.DOC_ANALYSIS,
        }

        source = source_mapping.get(tool_name, VerificationSource.DOC_ANALYSIS)

        # Extract risk flag from result
        risk_flag = False
        if hasattr(result, 'visual_risk_flag'):
            risk_flag = result.visual_risk_flag
        elif hasattr(result, 'related_party_risk'):
            risk_flag = result.related_party_risk
        elif hasattr(result, 'risk_flag'):
            risk_flag = result.risk_flag
        elif hasattr(result, 'is_manipulated'):
            risk_flag = result.is_manipulated

        # Generate finding text
        finding = self._generate_finding_text(tool_name, result)

        # Extract image URL if available
        image_url = getattr(result, 'image_url', None)

        return EvidenceLog(
            case_id=case_id,
            source=source,
            raw_data=result.dict() if hasattr(result, 'dict') else {},
            synthesized_finding=finding,
            risk_flag=risk_flag,
            image_url=image_url,
        )

    def _generate_finding_text(self, tool_name: str, result: Any) -> str:
        """Generate human-readable finding from tool result."""
        if tool_name == "street_view_vision":
            return f"Building Type: {result.building_type}. Signage: {'Detected' if result.signage_detected else 'Not detected'}. {result.description}"
        elif tool_name == "property_owner":
            return f"Property Owner: {result.owner_name}. Zoning: {result.zoning_code}. Related Party Risk: {result.related_party_risk}"
        elif tool_name == "registry_status":
            return f"Status: {result.status}. Incorporated: {result.incorporation_date} ({result.days_since_incorp} days ago)"
        elif tool_name == "domain_forensics":
            return f"Domain Age: {result.domain_age_days} days. Template Site: {result.is_template_site}. Risk Score: {result.risk_score}"
        elif tool_name == "web_content_scraper":
            return f"Lorem Ipsum: {result.has_lorem_ipsum}. Staff Mentioned: {result.staff_count_mentioned}. Consistency: {result.consistency_score}/100"
        elif tool_name == "phone_carrier":
            return f"Carrier: {result.carrier}. Line Type: {result.line_type}. Risk Flag: {result.risk_flag}"
        elif tool_name == "email_footprint":
            return f"Social Profiles: {result.profile_count}. Score: {result.social_score}. Platforms: {', '.join(result.registered_profiles[:3])}"
        elif tool_name == "breach_history":
            return f"Breach Count: {result.breach_count}. Synthetic Identity Suspicion: {result.synthetic_identity_suspicion}"
        elif tool_name == "pdf_metadata":
            return f"Software: {result.software_tool}. Manipulated: {result.is_manipulated}"
        elif tool_name == "advanced_forensics":
            # Handle dict result from ForensicPipeline
            if isinstance(result, dict):
                forged = result.get("is_forged", False)
                confidence = result.get("forgery_confidence", 0)
                anomaly_count = len(result.get("anomalies", []))
                return f"Forgery Detected: {forged}. Confidence: {confidence:.1f}%. Anomalies: {anomaly_count}"
            return str(result)
        elif tool_name == "vector_similarity":
            return f"Plagiarism: {result.is_plagiarized}. Score: {result.plagiarism_score:.2f}. Similar Cases: {result.similar_cases_count}"
        elif tool_name == "job_board_scraper":
            return f"Job Postings: {result.total_job_postings}. Recent (30d): {result.recent_postings_30d}. Growth Verified: {result.growth_claim_verified}"
        elif tool_name == "employee_ghost_check":
            return f"Employees Verified: {result.employees_verified}/{result.total_employees_claimed}. Ghost Count: {len(result.ghost_employees)}"
        elif tool_name == "graph_network":
            return f"Connected Entities: {result.connected_entities_count}. Fraud Ring: {result.fraud_ring_detected}. Network Risk: {result.network_risk_score}"
        elif tool_name == "ssn_validation":
            return f"SSN: {result.ssn}. Valid: {result.is_valid}. Deceased: {result.is_deceased}. State: {result.state_issued}"
        elif tool_name == "employer_verification":
            return f"Employer: {result.employer_name}. Exists: {result.employer_exists}. Employment Verified: {result.employment_verified}"
        elif tool_name == "cross_state_claim_check":
            return f"States: {len(result.states_with_claims)}. Multi-State Fraud: {result.is_multi_state_fraud}. Concurrent Claims: {result.concurrent_claims}"
        elif tool_name == "prison_inmate_check":
            return f"Incarcerated: {result.is_incarcerated}. Facility: {result.facility_name if result.is_incarcerated else 'N/A'}"
        elif tool_name == "address_history":
            return f"Tenure: {result.address_tenure_days} days. Changes (6mo): {result.address_changes_6mo}. Fraud Ring Address: {result.is_fraud_ring_address}"

        return str(result)

    async def _reporter_node(self, state: InvestigationState) -> InvestigationState:
        """
        Reporter: Applies Risk Matrix scoring and generates BLUF narrative.

        Implements the weighted scoring system:
        - Layer 1 (Physical): 40 points max
        - Layer 2 (Corporate): 50 points max
        - Layer 3 (Identity): 25 points max
        - Layer 4 (Forensics): KILL SWITCH (automatic 100) + Advanced Forensics
        - Layer 5 (Intelligence): 140 points max (fraud rings)
        """
        tool_outputs = state["tool_outputs"]

        # Initialize risk score
        risk_score = 0
        risk_factors = []

        # LAYER 4: FORENSIC WEIGHTING (KILL SWITCH)
        if "pdf_metadata" in tool_outputs:
            pdf = tool_outputs["pdf_metadata"]
            if pdf.is_manipulated:
                risk_score = 100
                risk_factors.append(f"CRITICAL: Document manipulation detected ({pdf.software_tool})")

        # LAYER 4: ADVANCED FORENSICS (KILL SWITCH)
        if "advanced_forensics" in tool_outputs:
            adv_forensics = tool_outputs["advanced_forensics"]
            if isinstance(adv_forensics, dict):
                if adv_forensics.get("is_forged", False):
                    confidence = adv_forensics.get("forgery_confidence", 0)
                    if confidence >= 80:
                        risk_score = 100
                        risk_factors.append(f"CRITICAL: Advanced forensics detected forgery ({confidence:.0f}% confidence)")
                    elif confidence >= 50:
                        risk_score += 40
                        risk_factors.append(f"High Risk: Document forensics shows forgery indicators ({confidence:.0f}% confidence)")

        # Only continue scoring if not already killed
        if risk_score < 100:
            # LAYER 5: CROSS-CASE INTELLIGENCE (FRAUD RINGS)
            if "graph_network" in tool_outputs:
                graph = tool_outputs["graph_network"]
                if graph.fraud_ring_detected:
                    risk_score += 50
                    risk_factors.append(f"CRITICAL: Fraud ring detected ({graph.connected_entities_count} connected entities)")

            if "vector_similarity" in tool_outputs:
                vector = tool_outputs["vector_similarity"]
                if vector.is_plagiarized and vector.plagiarism_score > 0.85:
                    risk_score += 40
                    risk_factors.append(f"High Risk: Plagiarized narrative (score: {vector.plagiarism_score:.2f})")

            if "employee_ghost_check" in tool_outputs:
                ghost = tool_outputs["employee_ghost_check"]
                verification_rate = ghost.employees_verified / max(ghost.total_employees_claimed, 1)
                if verification_rate < 0.70:
                    risk_score += 30
                    risk_factors.append(f"High Risk: Low employee verification rate ({verification_rate*100:.0f}%)")

            if "job_board_scraper" in tool_outputs:
                jobs = tool_outputs["job_board_scraper"]
                if not jobs.growth_claim_verified and jobs.total_job_postings == 0:
                    risk_score += 20
                    risk_factors.append(f"Medium Risk: Growth claimed but no hiring activity")

            # LAYER 2: CORPORATE WEIGHTING
            if "domain_forensics" in tool_outputs:
                domain = tool_outputs["domain_forensics"]
                if domain.domain_age_days < 30:
                    risk_score += 30
                    risk_factors.append(f"High Risk: Domain created {domain.domain_age_days} days ago")

            if "registry_status" in tool_outputs:
                registry = tool_outputs["registry_status"]
                if registry.days_since_incorp < 30:
                    risk_score += 20
                    risk_factors.append(f"High Risk: Company formed {registry.days_since_incorp} days ago")

            # LAYER 1: PHYSICAL WEIGHTING
            if "street_view_vision" in tool_outputs:
                street = tool_outputs["street_view_vision"]
                if street.visual_risk_flag and street.building_type == "residential":
                    risk_score += 25
                    risk_factors.append(f"High Risk: Residential property for commercial business")

            if "property_owner" in tool_outputs:
                prop = tool_outputs["property_owner"]
                if prop.related_party_risk:
                    risk_score += 15
                    risk_factors.append(f"Medium Risk: Related party property ownership")

            # LAYER 3: IDENTITY WEIGHTING
            if "phone_carrier" in tool_outputs:
                phone = tool_outputs["phone_carrier"]
                if phone.line_type == "VOIP":
                    risk_score += 10
                    risk_factors.append(f"Low Risk: VOIP phone number ({phone.carrier})")

            if "email_footprint" in tool_outputs:
                email = tool_outputs["email_footprint"]
                if email.profile_count == 0:
                    risk_score += 15
                    risk_factors.append(f"Medium Risk: No social media presence")

            # UNEMPLOYMENT/BENEFITS-SPECIFIC SCORING
            if "ssn_validation" in tool_outputs:
                ssn_result = tool_outputs["ssn_validation"]
                if ssn_result.is_deceased:
                    risk_score = 100  # KILL SWITCH: Ghost claimant
                    risk_factors.append(f"CRITICAL: SSN belongs to deceased individual (ghost claimant)")
                elif not ssn_result.is_valid:
                    risk_score += 40
                    risk_factors.append(f"High Risk: SSN validation failed - {', '.join(ssn_result.anomalies)}")

            if "cross_state_claim_check" in tool_outputs:
                cross_state = tool_outputs["cross_state_claim_check"]
                if cross_state.is_multi_state_fraud:
                    risk_score += 60
                    risk_factors.append(f"CRITICAL: Multi-state fraud - {cross_state.concurrent_claims} concurrent claims in {len(cross_state.states_with_claims)} states")

            if "prison_inmate_check" in tool_outputs:
                inmate = tool_outputs["prison_inmate_check"]
                if inmate.is_incarcerated:
                    risk_score = 100  # KILL SWITCH: Ineligible claimant
                    risk_factors.append(f"CRITICAL: Claimant is incarcerated at {inmate.facility_name}")

            if "employer_verification" in tool_outputs:
                employer = tool_outputs["employer_verification"]
                if not employer.employer_exists:
                    risk_score += 50
                    risk_factors.append(f"CRITICAL: Previous employer does not exist - fake employment history")
                elif not employer.employment_verified:
                    risk_score += 35
                    risk_factors.append(f"High Risk: Employment could not be verified in wage records")

            if "address_history" in tool_outputs:
                address = tool_outputs["address_history"]
                if address.is_fraud_ring_address:
                    risk_score += 50
                    risk_factors.append(f"CRITICAL: Fraud ring address - {address.claims_at_address} claims at this location")
                elif address.address_changes_6mo >= 5:
                    risk_score += 25
                    risk_factors.append(f"High Risk: Address hopping - {address.address_changes_6mo} moves in 6 months")

        # Cap at 100
        risk_score = min(risk_score, 100)

        # Determine risk level
        if risk_score >= 80:
            risk_level = "CRITICAL"
            recommendation = "DENY"
        elif risk_score >= 70:
            risk_level = "HIGH"
            recommendation = "DENY"
        elif risk_score >= 40:
            risk_level = "MEDIUM"
            recommendation = "FURTHER_REVIEW"
        else:
            risk_level = "LOW"
            recommendation = "APPROVE"

        # Generate BLUF narrative
        narrative = self._generate_bluf_narrative(
            state["case_data"],
            risk_score,
            risk_level,
            risk_factors,
            tool_outputs
        )

        # Store verdict
        state["final_verdict"] = {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "narrative": narrative,
            "key_findings": risk_factors,
        }

        state["investigation_log"].append("Final report generated")

        return state

    def _generate_bluf_narrative(
        self,
        case_data: Dict[str, Any],
        risk_score: int,
        risk_level: str,
        risk_factors: List[str],
        tool_outputs: Dict[str, Any]
    ) -> str:
        """Generate Bottom Line Up Front (BLUF) narrative."""
        applicant = case_data.get("applicant_name", "Unknown Entity")

        # BLUF: Bottom line first
        bluf = f"**BLUF: Risk Score {risk_score}/100 ({risk_level})**\n\n"

        if risk_score >= 80:
            bluf += f"Investigation of {applicant} reveals **CRITICAL fraud indicators**. "
            bluf += "Immediate denial recommended.\n\n"
        elif risk_score >= 70:
            bluf += f"Investigation of {applicant} reveals **HIGH-RISK fraud indicators**. "
            bluf += "Denial recommended.\n\n"
        elif risk_score >= 40:
            bluf += f"Investigation of {applicant} reveals **MEDIUM-RISK concerns**. "
            bluf += "Additional verification required before approval.\n\n"
        else:
            bluf += f"Investigation of {applicant} shows **LOW-RISK profile**. "
            bluf += "Standard approval process recommended.\n\n"

        # Key Findings
        bluf += "## Key Findings\n\n"
        for i, factor in enumerate(risk_factors, 1):
            bluf += f"{i}. {factor}\n"

        if not risk_factors:
            bluf += "No significant fraud indicators detected.\n"

        # Detailed Evidence
        bluf += "\n## Evidence Summary\n\n"

        # Layer 5: Cross-Case Intelligence
        if "graph_network" in tool_outputs:
            graph = tool_outputs["graph_network"]
            if graph.fraud_ring_detected:
                bluf += f"**FRAUD RING DETECTED**: {graph.connected_entities_count} connected entities sharing contact information. "
                bluf += f"This application is part of a coordinated fraud operation.\n\n"

        if "vector_similarity" in tool_outputs:
            vector = tool_outputs["vector_similarity"]
            if vector.is_plagiarized:
                bluf += f"**PLAGIARISM DETECTED**: Application narrative matches {vector.similar_cases_count} previous applications "
                bluf += f"(similarity: {vector.plagiarism_score*100:.0f}%). Indicates scripted fraud.\n\n"

        if "employee_ghost_check" in tool_outputs:
            ghost = tool_outputs["employee_ghost_check"]
            if len(ghost.ghost_employees) > 0:
                bluf += f"**GHOST EMPLOYEES**: {len(ghost.ghost_employees)} employees could not be verified. "
                bluf += "Possible payroll fraud.\n\n"

        # Layer 4: Document Forensics
        if "advanced_forensics" in tool_outputs:
            adv_forensics = tool_outputs["advanced_forensics"]
            if isinstance(adv_forensics, dict) and adv_forensics.get("is_forged", False):
                confidence = adv_forensics.get("forgery_confidence", 0)
                anomaly_count = len(adv_forensics.get("anomalies", []))
                bluf += f"**ADVANCED FORENSICS**: Document forgery detected ({confidence:.0f}% confidence, {anomaly_count} anomalies). "
                bluf += "Sophisticated document manipulation identified.\n\n"

        if "pdf_metadata" in tool_outputs:
            pdf = tool_outputs["pdf_metadata"]
            if pdf.is_manipulated:
                bluf += f"**BASIC FORENSICS**: Evidence of manipulation using {pdf.software_tool}. "
                bluf += "This is a critical fraud indicator.\n\n"

        # Layer 2: Corporate
        if "registry_status" in tool_outputs:
            reg = tool_outputs["registry_status"]
            bluf += f"**Corporate Registration**: {reg.legal_name} incorporated on {reg.incorporation_date} "
            bluf += f"({reg.days_since_incorp} days ago). Status: {reg.status}.\n\n"

        if "job_board_scraper" in tool_outputs:
            jobs = tool_outputs["job_board_scraper"]
            if not jobs.growth_claim_verified:
                bluf += f"**Hiring Activity**: {jobs.total_job_postings} job postings found. "
                bluf += "Growth claims could not be verified.\n\n"

        # Layer 1: Physical
        if "street_view_vision" in tool_outputs:
            street = tool_outputs["street_view_vision"]
            bluf += f"**Physical Verification**: {street.description}\n\n"

        # Recommendation
        bluf += f"\n## Recommendation\n\n"
        if risk_score >= 70:
            bluf += "**DENY** this application based on fraud indicators.\n"
        elif risk_score >= 40:
            bluf += "**REQUEST ADDITIONAL INFORMATION** before making final determination.\n"
        else:
            bluf += "**APPROVE** with standard due diligence.\n"

        return bluf
