"""
LangGraph-based Agent Orchestrator for fraud investigation.

Implements a ReAct (Reason + Act) loop with state machine:
Planner -> Executor -> Analyzer -> Reporter
"""
from typing import Dict, Any, List, TypedDict, Annotated
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
from app.agent.tools import (
    GoogleStreetViewTool,
    CorpRegistryTool,
    PeopleVerificationTool
)


class InvestigationState(TypedDict):
    """State passed between agent nodes."""
    case_id: str
    case_data: Dict[str, Any]
    tool_outputs: List[Dict[str, Any]]
    investigation_log: List[str]
    final_verdict: Dict[str, Any]
    current_step: str
    next_tools: List[str]


class FraudInvestigationOrchestrator:
    """
    Orchestrates the fraud investigation workflow using LangGraph.

    The agent follows this flow:
    1. Planner: Analyzes case and decides which tools to use
    2. Executor: Runs the selected tools in parallel
    3. Analyzer: Reviews tool outputs, decides if more investigation needed
    4. Reporter: Generates final risk assessment and narrative
    """

    def __init__(self, db: Session):
        self.db = db
        self.llm = self._initialize_llm()
        self.graph = self._build_graph()

    def _initialize_llm(self):
        """Initialize the LLM based on configured provider."""
        if settings.llm_provider == "anthropic":
            return ChatAnthropic(
                model=settings.llm_model,
                api_key=settings.anthropic_api_key,
                temperature=settings.llm_temperature
            )
        else:  # Default to OpenAI
            return ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                temperature=settings.llm_temperature
            )

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(InvestigationState)

        # Add nodes
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("analyzer", self._analyzer_node)
        workflow.add_node("reporter", self._reporter_node)

        # Define edges
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "analyzer")

        # Conditional edge from analyzer
        workflow.add_conditional_edges(
            "analyzer",
            self._should_continue_investigation,
            {
                "continue": "planner",  # Loop back for more investigation
                "report": "reporter"
            }
        )

        workflow.add_edge("reporter", END)

        return workflow.compile()

    async def investigate(self, case_id: str) -> Dict[str, Any]:
        """
        Run the full investigation workflow for a case.

        Args:
            case_id: UUID of the case to investigate

        Returns:
            Final investigation results
        """
        # Load case data
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Update status to PROCESSING
        case.status = CaseStatus.PROCESSING
        self.db.commit()

        # Initialize state
        initial_state: InvestigationState = {
            "case_id": str(case_id),
            "case_data": {
                "applicant_name": case.applicant_name,
                "applicant_tax_id": case.applicant_tax_id,
                "applicant_address": case.applicant_address,
                "external_ref_id": case.external_ref_id
            },
            "tool_outputs": [],
            "investigation_log": [],
            "final_verdict": {},
            "current_step": "planner",
            "next_tools": []
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
        Planner: Analyzes case and decides which tools to use.
        """
        system_prompt = """You are a Federal fraud investigation planner.

Your job is to analyze the case data and decide which investigation tools to use.

Available tools:
- google_street_view: Verify the physical location matches the business type
- corporate_registry: Check company registration status and formation date
- people_verification: Verify the applicant's identity

Based on the case data, select which tools to run. Consider:
- Always verify the business location if an address is provided
- Check corporate registry if this is a business entity
- Verify people if this is an individual applicant

Respond with a JSON array of tool names to execute:
["tool1", "tool2", ...]"""

        case_summary = f"""
Case: {state['case_data'].get('applicant_name')}
Address: {state['case_data'].get('applicant_address')}
Tax ID: {state['case_data'].get('applicant_tax_id')}

Previous investigation steps: {len(state['investigation_log'])}
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"What tools should we use to investigate this case?\n\n{case_summary}")
        ]

        response = await self.llm.ainvoke(messages)

        try:
            tools_to_run = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback: run all tools
            tools_to_run = ["google_street_view", "corporate_registry", "people_verification"]

        state["next_tools"] = tools_to_run
        state["investigation_log"].append(f"Planner selected tools: {tools_to_run}")

        return state

    async def _executor_node(self, state: InvestigationState) -> InvestigationState:
        """
        Executor: Runs the selected tools in parallel.
        """
        tools_to_run = state["next_tools"]
        case_data = state["case_data"]

        tool_results = []

        # Run tools in parallel
        tasks = []
        for tool_name in tools_to_run:
            if tool_name == "google_street_view":
                tool = GoogleStreetViewTool()
                tasks.append(self._run_google_street_view(tool, case_data))
            elif tool_name == "corporate_registry":
                tool = CorpRegistryTool()
                tasks.append(self._run_corporate_registry(tool, case_data))
            elif tool_name == "people_verification":
                tool = PeopleVerificationTool()
                tasks.append(self._run_people_verification(tool, case_data))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and save to database
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                state["investigation_log"].append(f"Tool {tools_to_run[i]} failed: {str(result)}")
                continue

            tool_results.append(result)

            # Save evidence to database
            evidence = EvidenceLog(
                case_id=state["case_id"],
                source=result["source"],
                raw_data=result["raw_data"],
                synthesized_finding=result["synthesized_finding"],
                risk_flag=result["risk_flag"],
                image_url=result.get("image_url")
            )
            self.db.add(evidence)

        self.db.commit()

        state["tool_outputs"].extend(tool_results)
        state["investigation_log"].append(f"Executed {len(tool_results)} tools successfully")

        return state

    async def _run_google_street_view(
        self,
        tool: GoogleStreetViewTool,
        case_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run Google Street View tool and format result."""
        address = case_data.get("applicant_address", "")
        result = await tool.execute(address=address)

        risk_flag = not result.is_commercial and "business" in case_data.get("applicant_name", "").lower()

        return {
            "source": VerificationSource.GOOGLE_MAPS,
            "raw_data": result.dict(),
            "synthesized_finding": f"Location analysis: {result.building_description}. Commercial property: {result.is_commercial}",
            "risk_flag": risk_flag,
            "image_url": result.image_url
        }

    async def _run_corporate_registry(
        self,
        tool: CorpRegistryTool,
        case_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run Corporate Registry tool and format result."""
        company_name = case_data.get("applicant_name", "")
        result = await tool.execute(company_name=company_name)

        # Check if company was formed very recently (< 30 days)
        risk_flag = False
        if result.incorporation_date:
            try:
                inc_date = datetime.strptime(result.incorporation_date, "%Y-%m-%d")
                days_old = (datetime.now() - inc_date).days
                risk_flag = days_old < 30
            except:
                pass

        return {
            "source": VerificationSource.OPENCORPORATES,
            "raw_data": result.dict(),
            "synthesized_finding": f"Corporate status: {result.status}. Incorporated: {result.incorporation_date}. {'RISK: Recently formed' if risk_flag else 'Normal age'}",
            "risk_flag": risk_flag
        }

    async def _run_people_verification(
        self,
        tool: PeopleVerificationTool,
        case_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run People Verification tool and format result."""
        name = case_data.get("applicant_name", "")
        result = await tool.execute(name=name)

        risk_flag = result.deceased or not result.identity_verified

        return {
            "source": VerificationSource.LEXIS_NEXIS,
            "raw_data": result.dict(),
            "synthesized_finding": f"Identity verified: {result.identity_verified}. Deceased: {result.deceased}. Address match: {result.address_match}",
            "risk_flag": risk_flag
        }

    async def _analyzer_node(self, state: InvestigationState) -> InvestigationState:
        """
        Analyzer: Reviews tool outputs and decides if more investigation is needed.
        """
        system_prompt = """You are a Federal fraud investigation analyst.

Review the evidence gathered so far. Determine if you have enough information to make a final determination, or if you need to gather more evidence.

Respond with JSON:
{
    "sufficient_evidence": true/false,
    "reasoning": "explanation",
    "additional_tools_needed": ["tool1", "tool2"] or []
}"""

        evidence_summary = "\n".join([
            f"- {output['source']}: {output['synthesized_finding']}"
            for output in state["tool_outputs"]
        ])

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Evidence gathered:\n{evidence_summary}\n\nDo we have enough to make a final determination?")
        ]

        response = await self.llm.ainvoke(messages)

        try:
            analysis = json.loads(response.content)
            state["investigation_log"].append(f"Analysis: {analysis['reasoning']}")

            if not analysis["sufficient_evidence"]:
                state["next_tools"] = analysis.get("additional_tools_needed", [])
        except json.JSONDecodeError:
            # Default to sufficient evidence if parsing fails
            pass

        return state

    def _should_continue_investigation(self, state: InvestigationState) -> str:
        """Decide whether to continue investigating or move to reporting."""
        # Continue if we have tools to run and haven't looped too many times
        if state["next_tools"] and len(state["investigation_log"]) < 10:
            return "continue"
        return "report"

    async def _reporter_node(self, state: InvestigationState) -> InvestigationState:
        """
        Reporter: Generates final risk assessment and narrative.
        """
        system_prompt = """You are a Federal Investigator OIG Agent. Review the gathered evidence and write a final report.

Guidelines:
- Start with BLUF (Bottom Line Up Front) - the conclusion first
- Assign a risk score from 0-100
- If Business Creation Date is < 30 days from Application Date -> HIGH RISK (70+)
- If Address is Residential and Industry is Manufacturing/Commercial -> HIGH RISK (70+)
- If Person is Deceased -> CRITICAL RISK (90+)
- Cite specific evidence for every claim
- Be factual and strict
- Use clear, professional government language

Respond with JSON:
{
    "risk_score": 0-100,
    "risk_level": "LOW/MEDIUM/HIGH/CRITICAL",
    "narrative": "Full markdown report with BLUF",
    "key_findings": ["finding 1", "finding 2", ...],
    "recommendation": "APPROVE/DENY/FURTHER_REVIEW"
}"""

        evidence_summary = "\n\n".join([
            f"**{output['source']}**\n{output['synthesized_finding']}\nRisk Flag: {output['risk_flag']}"
            for output in state["tool_outputs"]
        ])

        case_data_str = json.dumps(state["case_data"], indent=2)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"""
Case Data:
{case_data_str}

Evidence Gathered:
{evidence_summary}

Generate the final investigative report.""")
        ]

        response = await self.llm.ainvoke(messages)

        try:
            verdict = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback verdict
            risk_flags = sum(1 for output in state["tool_outputs"] if output["risk_flag"])
            risk_score = min(risk_flags * 30, 100)

            verdict = {
                "risk_score": risk_score,
                "risk_level": "HIGH" if risk_score > 70 else "MEDIUM" if risk_score > 40 else "LOW",
                "narrative": "Investigation completed. See evidence logs for details.",
                "key_findings": [output["synthesized_finding"] for output in state["tool_outputs"]],
                "recommendation": "FURTHER_REVIEW"
            }

        state["final_verdict"] = verdict
        state["investigation_log"].append("Final report generated")

        return state
