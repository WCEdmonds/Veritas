"""
Layer 1: Physical Verification Tools

Tools for verifying physical business locations and property ownership.
"""
import httpx
import base64
from typing import Dict, Any
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from app.config import settings
from app.schemas import StreetViewVisionOutput, PropertyOwnerOutput
from app.agent.base import BaseTool


class StreetViewVisionTool(BaseTool):
    """
    Visual confirmation of business existence and type.

    Uses Google Maps Static API + GPT-4 Vision to analyze the building
    and detect mismatches between claimed business type and actual property.
    """

    def __init__(self):
        super().__init__()
        self.api_key = settings.google_maps_api_key

    async def execute(
        self,
        address: str,
        claimed_industry: str = "general business"
    ) -> StreetViewVisionOutput:
        """
        Analyze building via Street View and Vision AI.

        Args:
            address: Physical address to investigate
            claimed_industry: What the applicant claims (e.g., "manufacturing")

        Returns:
            StreetViewVisionOutput with visual analysis
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(address, claimed_industry)

        try:
            # Step 1: Fetch Street View image
            image_url = await self._fetch_street_view(address)

            # Step 2: Analyze with GPT-4 Vision
            analysis = await self._analyze_with_vision(image_url, claimed_industry)

            return StreetViewVisionOutput(
                building_type=analysis["building_type"],
                signage_detected=analysis["signage_detected"],
                visual_risk_flag=analysis["visual_risk_flag"],
                image_url=image_url,
                description=analysis["description"]
            )

        except Exception as e:
            print(f"Error in StreetViewVisionTool: {e}")
            return await self._mock_response(address, claimed_industry)

    async def _fetch_street_view(self, address: str) -> str:
        """Fetch Street View static image."""
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

            # Return as base64 data URL
            image_url = f"data:image/jpeg;base64,{base64.b64encode(response.content).decode()}"
            return image_url

    async def _analyze_with_vision(
        self,
        image_url: str,
        claimed_industry: str
    ) -> Dict[str, Any]:
        """Analyze image using GPT-4 Vision."""
        from langchain_openai import ChatOpenAI
        from langchain.schema import HumanMessage
        import json

        llm = ChatOpenAI(
            model="gpt-4-vision-preview",
            api_key=settings.openai_api_key,
            temperature=0
        )

        prompt = f"""Analyze this building image for fraud detection purposes.

The applicant claims this is a '{claimed_industry}' business.

Identify:
1. Building type: residential, industrial, office, or retail
2. Is business signage visible?
3. Detailed description of what you see

Respond in JSON:
{{
    "building_type": "residential|industrial|office|retail",
    "signage_detected": true/false,
    "description": "detailed description",
    "visual_risk_flag": true/false
}}

Set visual_risk_flag to TRUE if the building type is inconsistent with the claimed industry
(e.g., residential home for a manufacturing business)."""

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        )

        response = await llm.ainvoke([message])
        result = json.loads(response.content)
        return result

    async def _mock_response(
        self,
        address: str,
        claimed_industry: str
    ) -> StreetViewVisionOutput:
        """
        Return deterministic mock data based on trigger keywords.

        Triggers:
        - "Smith" in address -> Fraud scenario (residential for business)
        - "Suite" in address -> Normal commercial
        - Default -> Low risk
        """
        address_lower = address.lower()

        # Fraud trigger: "Smith" indicates fraudulent residential location
        if "smith" in address_lower:
            return StreetViewVisionOutput(
                building_type="residential",
                signage_detected=False,
                visual_risk_flag=True,  # RISK: Residential for business
                image_url="https://via.placeholder.com/600x400?text=Residential+Home",
                description="Single-family residential home. No business signage visible. Property appears to be a personal residence, not suitable for commercial operations."
            )

        # Normal commercial: "Suite" or "Building"
        if "suite" in address_lower or "building" in address_lower:
            return StreetViewVisionOutput(
                building_type="office",
                signage_detected=True,
                visual_risk_flag=False,
                image_url="https://via.placeholder.com/600x400?text=Office+Building",
                description="Multi-story office building with visible professional signage. Well-maintained commercial property suitable for business operations."
            )

        # Manufacturing/Industrial
        if "industrial" in claimed_industry.lower() or "manufacturing" in claimed_industry.lower():
            return StreetViewVisionOutput(
                building_type="industrial",
                signage_detected=True,
                visual_risk_flag=False,
                image_url="https://via.placeholder.com/600x400?text=Industrial+Facility",
                description="Industrial warehouse facility with loading docks. Commercial zoning appropriate for manufacturing operations."
            )

        # Default: Normal retail/office
        return StreetViewVisionOutput(
            building_type="retail",
            signage_detected=True,
            visual_risk_flag=False,
            image_url="https://via.placeholder.com/600x400?text=Commercial+Building",
            description="Commercial building with storefront. Appropriate for business operations."
        )


class PropertyOwnerTool(BaseTool):
    """
    Detect undisclosed related-party transactions.

    Checks if the applicant owns or is related to the property owner,
    which could indicate self-dealing or fraudulent rent payments.
    """

    def __init__(self):
        super().__init__()
        # In production, would use ATTOM Data or Estated API
        self.api_key = None  # Mock for MVP

    async def execute(
        self,
        address: str,
        applicant_name: str,
        principals: list = None
    ) -> PropertyOwnerOutput:
        """
        Look up property ownership and detect related parties.

        Args:
            address: Property address
            applicant_name: Name of the grant applicant
            principals: List of key company principals (optional)

        Returns:
            PropertyOwnerOutput with ownership details
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(address, applicant_name, principals)

        # In production: Call ATTOM or Estated API here
        # For MVP: Use mock data
        return await self._mock_response(address, applicant_name, principals)

    def _fuzzy_match(self, name1: str, name2: str) -> float:
        """Calculate fuzzy string similarity (0.0 to 1.0)."""
        return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()

    async def _mock_response(
        self,
        address: str,
        applicant_name: str,
        principals: list = None
    ) -> PropertyOwnerOutput:
        """
        Return mock property data.

        Triggers:
        - "Doe" in applicant name -> Related party risk
        - "Smith" in address -> Related party (owner matches applicant)
        """
        applicant_lower = applicant_name.lower()
        address_lower = address.lower()

        # Fraud trigger: Related party ownership
        if "doe" in applicant_lower or "smith" in address_lower:
            # Extract first name for owner
            owner_name = f"{applicant_name.split()[0]} Property LLC"
            related_party = True
        else:
            owner_name = "Commercial Properties Inc"
            related_party = False

        # Check fuzzy matching
        if not related_party and principals:
            for principal in principals:
                if self._fuzzy_match(owner_name, principal) > 0.8:
                    related_party = True
                    break

        # Residential zoning is a red flag for commercial business
        if "smith" in address_lower or related_party:
            zoning = "R1 (Single Family)"
        else:
            zoning = "C2 (Commercial)"

        return PropertyOwnerOutput(
            owner_name=owner_name,
            last_sale_date=(datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d"),
            zoning_code=zoning,
            related_party_risk=related_party
        )
