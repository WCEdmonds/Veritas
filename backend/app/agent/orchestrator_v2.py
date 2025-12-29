"""
Enhanced LangGraph-based Agent Orchestrator with 4-Layer Investigation.

Implements comprehensive fraud detection using:
- Layer 1: Physical Verification
- Layer 2: Corporate Verification
- Layer 3: Digital Identity
- Layer 4: Document Forensics

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
from app.models import Case, EvidenceLog, VerificationSource, CaseStatus

# Import all investigative tools
from app.agent.physical import StreetViewVisionTool, PropertyOwnerTool
from app.agent.corporate import RegistryStatusTool, DomainForensicsTool, WebContentScraperTool
from app.agent.identity import PhoneCarrierTool, EmailDigitalFootprintTool, BreachHistoryTool
from app.agent.forensics import PDFMetadataTool


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

        # Layer 2: Corporate
        "registry_status": RegistryStatusTool,
        "domain_forensics": DomainForensicsTool,
        "web_content_scraper": WebContentScraperTool,

        # Layer 3: Identity
        "phone_carrier": PhoneCarrierTool,
        "email_footprint": EmailDigitalFootprintTool,
        "breach_history": BreachHistoryTool,

        # Layer 4: Forensics
        "pdf_metadata": PDFMetadataTool,
    }

    def __init__(self, db: Session):
        self.db = db
        self.llm = self._initialize_llm()
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
        Planner: Selects comprehensive toolset for investigation.

        For MVP, we run all available tools to maximize signal collection.
        """
        case_data = state["case_data"]

        # Default comprehensive toolset
        tools_to_run = [
            "registry_status",      # Always check company registration
            "street_view_vision",   # Always verify physical location
        ]

        # Add domain forensics if we can extract domain
        if case_data.get("applicant_name"):
            tools_to_run.append("domain_forensics")
            tools_to_run.append("web_content_scraper")

        # Add property owner check if address provided
        if case_data.get("applicant_address"):
            tools_to_run.append("property_owner")

        # Add identity checks if available
        # In a real system, these would come from additional case data
        # For MVP, we'll include them with mock data
        tools_to_run.extend([
            "phone_carrier",
            "email_footprint",
            "breach_history",
        ])

        # Add document forensics (would be triggered by uploaded docs)
        tools_to_run.append("pdf_metadata")

        state["next_tools"] = tools_to_run
        state["investigation_log"].append(f"Planner selected {len(tools_to_run)} tools for investigation")

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

        return str(result)

    async def _reporter_node(self, state: InvestigationState) -> InvestigationState:
        """
        Reporter: Applies Risk Matrix scoring and generates BLUF narrative.

        Implements the weighted scoring system:
        - Layer 1 (Physical): 40 points max
        - Layer 2 (Corporate): 50 points max
        - Layer 3 (Identity): 25 points max
        - Layer 4 (Forensics): KILL SWITCH (automatic 100)
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

        # Only continue scoring if not already killed
        if risk_score < 100:
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

        if "registry_status" in tool_outputs:
            reg = tool_outputs["registry_status"]
            bluf += f"**Corporate Registration**: {reg.legal_name} incorporated on {reg.incorporation_date} "
            bluf += f"({reg.days_since_incorp} days ago). Status: {reg.status}.\n\n"

        if "street_view_vision" in tool_outputs:
            street = tool_outputs["street_view_vision"]
            bluf += f"**Physical Verification**: {street.description}\n\n"

        if "pdf_metadata" in tool_outputs:
            pdf = tool_outputs["pdf_metadata"]
            if pdf.is_manipulated:
                bluf += f"**DOCUMENT FORENSICS**: Evidence of manipulation using {pdf.software_tool}. "
                bluf += "This is a critical fraud indicator.\n\n"

        # Recommendation
        bluf += f"\n## Recommendation\n\n"
        if risk_score >= 70:
            bluf += "**DENY** this application based on fraud indicators.\n"
        elif risk_score >= 40:
            bluf += "**REQUEST ADDITIONAL INFORMATION** before making final determination.\n"
        else:
            bluf += "**APPROVE** with standard due diligence.\n"

        return bluf
