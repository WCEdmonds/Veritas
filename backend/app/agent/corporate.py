"""
Layer 2: Corporate Verification Tools

Tools for verifying company registration, web presence, and digital footprint.
"""
import httpx
import re
from typing import Dict, Any
from datetime import datetime, timedelta

from app.config import settings
from app.schemas import (
    RegistryStatusOutput,
    DomainForensicsOutput,
    WebContentScraperOutput
)
from app.agent.base import BaseTool


class RegistryStatusTool(BaseTool):
    """
    Verify legal standing of business entity.

    Checks incorporation status, formation date, and good standing
    with state authorities.
    """

    def __init__(self):
        super().__init__()
        self.api_key = settings.opencorporates_api_key

    async def execute(
        self,
        company_name: str,
        jurisdiction: str = "us"
    ) -> RegistryStatusOutput:
        """
        Look up company registration information.

        Args:
            company_name: Legal name of business
            jurisdiction: State/country code (e.g., 'us_ca')

        Returns:
            RegistryStatusOutput with registration details
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(company_name, jurisdiction)

        try:
            url = "https://api.opencorporates.com/v0.4/companies/search"
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
                    # Company not found
                    return RegistryStatusOutput(
                        legal_name=company_name,
                        incorporation_date=datetime.now().strftime("%Y-%m-%d"),
                        status="NOT_FOUND",
                        days_since_incorp=0
                    )

                company = data["results"]["companies"][0]["company"]
                inc_date = company.get("incorporation_date", datetime.now().strftime("%Y-%m-%d"))

                # Calculate days since incorporation
                inc_datetime = datetime.strptime(inc_date, "%Y-%m-%d")
                days_since = (datetime.now() - inc_datetime).days

                return RegistryStatusOutput(
                    legal_name=company.get("name", company_name),
                    incorporation_date=inc_date,
                    status=company.get("current_status", "UNKNOWN"),
                    days_since_incorp=days_since
                )

        except Exception as e:
            print(f"Error in RegistryStatusTool: {e}")
            return await self._mock_response(company_name, jurisdiction)

    async def _mock_response(
        self,
        company_name: str,
        jurisdiction: str
    ) -> RegistryStatusOutput:
        """
        Return mock registry data.

        Triggers:
        - "QuickStart" in name -> Recently formed (HIGH RISK)
        - "Legacy" in name -> Established company
        - "Defunct" in name -> Dissolved status
        """
        name_lower = company_name.lower()

        # Fraud trigger: Newly formed shell company
        if "quickstart" in name_lower or "new" in name_lower:
            incorporation_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
            status = "Active"
            days_since = 15  # RED FLAG: < 30 days

        # Dissolved company (another red flag)
        elif "defunct" in name_lower or "dissolved" in name_lower:
            incorporation_date = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")
            status = "Dissolved"
            days_since = 1095

        # Established company
        else:
            incorporation_date = (datetime.now() - timedelta(days=1825)).strftime("%Y-%m-%d")  # ~5 years
            status = "Active"
            days_since = 1825

        return RegistryStatusOutput(
            legal_name=company_name,
            incorporation_date=incorporation_date,
            status=status,
            days_since_incorp=days_since
        )


class DomainForensicsTool(BaseTool):
    """
    Identify "pop-up" websites created solely for grant applications.

    Analyzes domain age, registrar, and technical indicators of
    hastily-created fraudulent websites.
    """

    def __init__(self):
        super().__init__()
        # In production: Use WhoisXML API
        self.api_key = None

    async def execute(self, domain: str) -> DomainForensicsOutput:
        """
        Analyze domain registration and website characteristics.

        Args:
            domain: Domain name (e.g., "example.com")

        Returns:
            DomainForensicsOutput with forensic analysis
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(domain)

        # In production: Call WhoisXML API and BuiltWith
        return await self._mock_response(domain)

    async def _mock_response(self, domain: str) -> DomainForensicsOutput:
        """
        Return mock domain data.

        Triggers:
        - "quickstart" in domain -> New domain (HIGH RISK)
        - "legacy" in domain -> Old established domain
        - "template" in domain -> Template site indicator
        """
        domain_lower = domain.lower()

        # Fraud trigger: Brand new domain
        if "quickstart" in domain_lower or "new" in domain_lower:
            domain_age_days = 12  # RED FLAG: < 30 days
            is_template = True
            registrar = "Namecheap"  # Budget registrar
            risk_score = 80

        # Template site indicator
        elif "template" in domain_lower or "site" in domain_lower:
            domain_age_days = 45
            is_template = True
            registrar = "GoDaddy"
            risk_score = 60

        # Established legitimate domain
        else:
            domain_age_days = 1250  # ~3.5 years
            is_template = False
            registrar = "AWS Route 53"
            risk_score = 20

        return DomainForensicsOutput(
            domain_age_days=domain_age_days,
            is_template_site=is_template,
            registrar=registrar,
            risk_score=risk_score
        )


class WebContentScraperTool(BaseTool):
    """
    Verify staff and operational history claims via website content.

    Scrapes company website and analyzes for fraud indicators like
    Lorem Ipsum placeholder text, stock photos, and generic content.
    """

    def __init__(self):
        super().__init__()
        # In production: Use Firecrawl or Puppeteer
        self.api_key = None

    async def execute(self, website_url: str) -> WebContentScraperOutput:
        """
        Scrape and analyze website content.

        Args:
            website_url: URL to analyze

        Returns:
            WebContentScraperOutput with content analysis
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(website_url)

        # In production: Scrape site and analyze with LLM
        return await self._mock_response(website_url)

    def _detect_lorem_ipsum(self, text: str) -> bool:
        """Detect Lorem Ipsum placeholder text."""
        lorem_patterns = [
            r"lorem ipsum",
            r"dolor sit amet",
            r"consectetur adipiscing",
            r"sed do eiusmod"
        ]
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in lorem_patterns)

    async def _mock_response(self, website_url: str) -> WebContentScraperOutput:
        """
        Return mock web content analysis.

        Triggers:
        - "quickstart" in URL -> Fake template site
        - "lorem" in URL -> Lorem ipsum detected
        - "professional" in URL -> Real content
        """
        url_lower = website_url.lower()

        # Fraud trigger: Fake template site with Lorem Ipsum
        if "quickstart" in url_lower or "template" in url_lower or "lorem" in url_lower:
            return WebContentScraperOutput(
                has_lorem_ipsum=True,
                staff_count_mentioned=0,
                consistency_score=10,  # Very low - fake site
                about_us_text="Lorem ipsum dolor sit amet, consectetur adipiscing elit. Our company is the best."
            )

        # Borderline case: Generic content
        if "new" in url_lower or "startup" in url_lower:
            return WebContentScraperOutput(
                has_lorem_ipsum=False,
                staff_count_mentioned=3,
                consistency_score=40,
                about_us_text="We are a dynamic company focused on innovation and excellence. Our team is dedicated to success."
            )

        # Legitimate professional site
        return WebContentScraperOutput(
            has_lorem_ipsum=False,
            staff_count_mentioned=15,
            consistency_score=85,
            about_us_text="Founded in 2015, our company has served over 500 clients. Our team of 15 professionals brings decades of combined experience in manufacturing solutions."
        )
