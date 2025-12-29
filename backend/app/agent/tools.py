"""Investigation tools for the fraud detection agent."""
import asyncio
import httpx
import base64
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime

from app.config import settings
from app.schemas import (
    GoogleStreetViewOutput,
    CorpRegistryOutput,
    PeopleVerificationOutput
)


class BaseTool(ABC):
    """Base class for all investigation tools."""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters."""
        pass


class GoogleStreetViewTool(BaseTool):
    """
    Tool for verifying business location via Google Street View.

    Uses Google Static Street View API to capture building image,
    then analyzes with GPT-4 Vision to determine if location matches
    the claimed business type.
    """

    def __init__(self):
        super().__init__()
        self.api_key = settings.google_maps_api_key
        self.use_mock = not self.api_key

    async def execute(self, address: str) -> GoogleStreetViewOutput:
        """
        Fetch street view image and analyze building type.

        Args:
            address: Physical address to investigate

        Returns:
            GoogleStreetViewOutput with analysis results
        """
        if self.use_mock:
            return await self._mock_response(address)

        try:
            # Step 1: Get Street View image
            image_url = await self._fetch_street_view(address)

            # Step 2: Analyze image with GPT-4 Vision
            analysis = await self._analyze_image(image_url, address)

            return GoogleStreetViewOutput(
                is_commercial=analysis["is_commercial"],
                building_description=analysis["description"],
                image_url=image_url,
                confidence=analysis["confidence"]
            )

        except Exception as e:
            print(f"Error in GoogleStreetViewTool: {e}")
            return await self._mock_response(address)

    async def _fetch_street_view(self, address: str) -> str:
        """Fetch image from Google Street View Static API."""
        base_url = "https://maps.googleapis.com/maps/api/streetview"
        params = {
            "size": "600x400",
            "location": address,
            "key": self.api_key,
            "return_error_code": "true"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()

            # Save image and return URL (in production, upload to S3/storage)
            image_url = f"data:image/jpeg;base64,{base64.b64encode(response.content).decode()}"
            return image_url

    async def _analyze_image(self, image_url: str, address: str) -> Dict[str, Any]:
        """Analyze building image using GPT-4 Vision."""
        from langchain_openai import ChatOpenAI
        from langchain.schema import HumanMessage

        llm = ChatOpenAI(
            model="gpt-4-vision-preview",
            api_key=settings.openai_api_key,
            temperature=0
        )

        prompt = f"""You are a Federal fraud investigator analyzing a building at: {address}

Analyze this image and determine:
1. Is this a COMMERCIAL or RESIDENTIAL building?
2. Describe the building type, condition, and any visible signage
3. Does it appear to be a legitimate business location?

Respond in JSON format:
{{
    "is_commercial": true/false,
    "description": "detailed description",
    "confidence": 0.0-1.0
}}"""

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        )

        response = await llm.ainvoke([message])

        # Parse JSON from response
        import json
        result = json.loads(response.content)
        return result

    async def _mock_response(self, address: str) -> GoogleStreetViewOutput:
        """Return mock data when API key not available."""
        # Simulate different scenarios based on address
        is_commercial = "suite" in address.lower() or "building" in address.lower()

        return GoogleStreetViewOutput(
            is_commercial=is_commercial,
            building_description=f"{'Commercial office building' if is_commercial else 'Residential property'} at {address}. {'Signage visible.' if is_commercial else 'No business signage.'}",
            image_url="https://via.placeholder.com/600x400?text=Street+View+Mock",
            confidence=0.85
        )


class CorpRegistryTool(BaseTool):
    """
    Tool for verifying corporate registration via OpenCorporates.

    Checks if business is properly registered, active, and when
    it was incorporated.
    """

    def __init__(self):
        super().__init__()
        self.api_key = settings.opencorporates_api_key
        self.use_mock = not self.api_key

    async def execute(
        self,
        company_name: str,
        jurisdiction: str = "us"
    ) -> CorpRegistryOutput:
        """
        Look up company registration information.

        Args:
            company_name: Name of the business
            jurisdiction: State/country code (e.g., 'us_ca' for California)

        Returns:
            CorpRegistryOutput with registration details
        """
        if self.use_mock:
            return await self._mock_response(company_name, jurisdiction)

        try:
            url = f"https://api.opencorporates.com/v0.4/companies/search"
            params = {
                "q": company_name,
                "jurisdiction_code": jurisdiction,
                "api_token": self.api_key
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("results", {}).get("companies"):
                    return CorpRegistryOutput(
                        status="NOT_FOUND",
                        incorporation_date=None,
                        agent_name=None,
                        jurisdiction=jurisdiction
                    )

                company = data["results"]["companies"][0]["company"]

                return CorpRegistryOutput(
                    status=company.get("current_status", "UNKNOWN"),
                    incorporation_date=company.get("incorporation_date"),
                    agent_name=company.get("registered_agent_name"),
                    jurisdiction=company.get("jurisdiction_code")
                )

        except Exception as e:
            print(f"Error in CorpRegistryTool: {e}")
            return await self._mock_response(company_name, jurisdiction)

    async def _mock_response(
        self,
        company_name: str,
        jurisdiction: str
    ) -> CorpRegistryOutput:
        """Return mock data when API not available."""
        # Simulate recently formed companies as suspicious
        import random

        is_new = random.random() < 0.3  # 30% chance of being newly formed

        if is_new:
            incorporation_date = datetime.now().strftime("%Y-%m-%d")
            status = "Active"
        else:
            incorporation_date = "2018-05-15"
            status = "Active"

        return CorpRegistryOutput(
            status=status,
            incorporation_date=incorporation_date,
            agent_name=f"{company_name} Agent Services",
            jurisdiction=jurisdiction
        )


class PeopleVerificationTool(BaseTool):
    """
    Tool for verifying individual identity (Mock for LexisNexis).

    In production, this would integrate with LexisNexis InstantID
    or similar identity verification service.
    """

    def __init__(self):
        super().__init__()
        self.api_key = settings.lexisnexis_api_key
        # Always use mock for this tool in development
        self.use_mock = True

    async def execute(
        self,
        name: str,
        ssn_last4: Optional[str] = None,
        address: Optional[str] = None
    ) -> PeopleVerificationOutput:
        """
        Verify person's identity and check for fraud indicators.

        Args:
            name: Full name of the person
            ssn_last4: Last 4 digits of SSN (optional)
            address: Address to verify (optional)

        Returns:
            PeopleVerificationOutput with verification results
        """
        # In production, call LexisNexis InstantID API
        # For now, return mock data
        return await self._mock_response(name, ssn_last4, address)

    async def _mock_response(
        self,
        name: str,
        ssn_last4: Optional[str],
        address: Optional[str]
    ) -> PeopleVerificationOutput:
        """Return mock verification data."""
        import random

        # Simulate various scenarios
        identity_verified = random.random() > 0.2  # 80% verified
        deceased = random.random() < 0.05  # 5% deceased (red flag!)
        address_match = random.random() > 0.3 if address else False

        confidence = 0.9 if identity_verified and not deceased else 0.4

        return PeopleVerificationOutput(
            identity_verified=identity_verified,
            deceased=deceased,
            address_match=address_match,
            confidence_score=confidence
        )


class DocumentAnalysisTool(BaseTool):
    """
    Tool for analyzing submitted documents for fraud indicators.

    Uses OCR + LLM to extract data and check for inconsistencies.
    """

    async def execute(self, document_url: str) -> Dict[str, Any]:
        """
        Analyze uploaded document for fraud indicators.

        Args:
            document_url: URL or path to document

        Returns:
            Analysis results with extracted data and fraud flags
        """
        # Mock implementation
        return {
            "document_type": "bank_statement",
            "extracted_data": {
                "account_holder": "John Doe",
                "balance": "$50,000",
                "statement_date": "2024-01-15"
            },
            "fraud_indicators": [],
            "confidence": 0.85
        }


# Tool Registry
AVAILABLE_TOOLS = {
    "google_street_view": GoogleStreetViewTool,
    "corporate_registry": CorpRegistryTool,
    "people_verification": PeopleVerificationTool,
    "document_analysis": DocumentAnalysisTool
}


async def get_tool(tool_name: str) -> BaseTool:
    """Get an instance of a tool by name."""
    tool_class = AVAILABLE_TOOLS.get(tool_name)
    if not tool_class:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tool_class()
