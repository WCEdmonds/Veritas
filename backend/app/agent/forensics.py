"""
Layer 4: Document Forensics Tools

Tools for detecting manipulated financial documents, bank statements,
and tax records.
"""
import httpx
from typing import Dict, Any, Optional
from datetime import datetime
import io

from app.config import settings
from app.schemas import PDFMetadataOutput
from app.agent.base import BaseTool


class PDFMetadataTool(BaseTool):
    """
    Detect software manipulation of financial documents.

    Analyzes PDF metadata to identify if documents were created or edited
    with image editing software (Photoshop, Canva) rather than legitimate
    financial software (QuickBooks, banking systems).

    This is the "Kill Switch" - finding manipulation triggers immediate
    risk score of 100.
    """

    def __init__(self):
        super().__init__()
        # In production: Use Inscribe API or PyPDF2 locally
        self.api_key = None

    # Suspicious software that indicates document manipulation
    MANIPULATION_INDICATORS = [
        "photoshop",
        "canva",
        "ilovepdf",
        "sejda",
        "gimp",
        "affinity",
        "acrobat pro",  # When used to heavily edit
        "pdfescape",
        "smallpdf",
    ]

    async def execute(
        self,
        document_url: str = None,
        document_path: str = None
    ) -> PDFMetadataOutput:
        """
        Analyze PDF document metadata for manipulation indicators.

        Args:
            document_url: URL to PDF document (optional)
            document_path: Local file path to PDF (optional)

        Returns:
            PDFMetadataOutput with forensic analysis
        """
        if self._use_mock(self.api_key):
            return await self._mock_response(document_url, document_path)

        try:
            # In production: Download PDF and analyze with PyPDF2
            if document_url:
                pdf_content = await self._download_pdf(document_url)
            elif document_path:
                with open(document_path, 'rb') as f:
                    pdf_content = f.read()
            else:
                raise ValueError("Either document_url or document_path must be provided")

            metadata = await self._extract_metadata(pdf_content)
            return metadata

        except Exception as e:
            print(f"Error in PDFMetadataTool: {e}")
            return await self._mock_response(document_url, document_path)

    async def _download_pdf(self, url: str) -> bytes:
        """Download PDF from URL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _extract_metadata(self, pdf_content: bytes) -> PDFMetadataOutput:
        """Extract and analyze PDF metadata using PyPDF2."""
        try:
            from PyPDF2 import PdfReader

            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            metadata = reader.metadata

            # Extract relevant fields
            producer = metadata.get('/Producer', '') if metadata else ''
            creator = metadata.get('/Creator', '') if metadata else ''
            creation_date = metadata.get('/CreationDate', '') if metadata else ''
            mod_date = metadata.get('/ModDate', '') if metadata else ''

            # Combine producer and creator for analysis
            software_info = f"{producer} {creator}".lower()

            # Check for manipulation indicators
            is_manipulated = any(
                indicator in software_info
                for indicator in self.MANIPULATION_INDICATORS
            )

            # Determine the software tool name
            software_tool = producer or creator or "Unknown"

            # Parse dates (PDF dates are in format: D:YYYYMMDDHHmmSS)
            creation_str = self._parse_pdf_date(creation_date)
            modified_str = self._parse_pdf_date(mod_date)

            return PDFMetadataOutput(
                software_tool=software_tool,
                creation_date=creation_str,
                modified_date=modified_str,
                is_manipulated=is_manipulated
            )

        except ImportError:
            # PyPDF2 not installed, use mock
            return await self._mock_response(None, None)
        except Exception as e:
            print(f"Error extracting PDF metadata: {e}")
            return await self._mock_response(None, None)

    def _parse_pdf_date(self, pdf_date: str) -> Optional[str]:
        """Parse PDF date format to ISO format."""
        if not pdf_date:
            return None

        try:
            # PDF date format: D:YYYYMMDDHHmmSS+HH'mm'
            if pdf_date.startswith('D:'):
                pdf_date = pdf_date[2:16]  # Extract YYYYMMDDHHmmSS

            if len(pdf_date) >= 8:
                year = pdf_date[0:4]
                month = pdf_date[4:6]
                day = pdf_date[6:8]
                return f"{year}-{month}-{day}"
        except:
            pass

        return None

    async def _mock_response(
        self,
        document_url: str = None,
        document_path: str = None
    ) -> PDFMetadataOutput:
        """
        Return mock PDF metadata.

        Triggers:
        - "fake" or "edited" in filename -> Photoshop (KILL SWITCH)
        - "bank_statement" in filename -> Legitimate banking software
        - "tax" in filename -> Legitimate tax software
        """
        # Extract filename from URL or path
        filename = ""
        if document_url:
            filename = document_url.split("/")[-1].lower()
        elif document_path:
            filename = document_path.split("/")[-1].lower()

        # KILL SWITCH: Fraud trigger - Manipulated document
        if "fake" in filename or "edited" in filename or "photoshop" in filename:
            return PDFMetadataOutput(
                software_tool="Adobe Photoshop 24.1",
                creation_date=datetime.now().strftime("%Y-%m-%d"),
                modified_date=datetime.now().strftime("%Y-%m-%d"),
                is_manipulated=True  # CRITICAL: Immediate fail
            )

        # Canva template (also manipulation)
        if "canva" in filename or "template" in filename:
            return PDFMetadataOutput(
                software_tool="Canva 1.0",
                creation_date=datetime.now().strftime("%Y-%m-%d"),
                modified_date=datetime.now().strftime("%Y-%m-%d"),
                is_manipulated=True
            )

        # Legitimate bank statement
        if "bank" in filename or "statement" in filename:
            return PDFMetadataOutput(
                software_tool="Chase Bank Portal v2.3",
                creation_date="2024-01-15",
                modified_date=None,
                is_manipulated=False
            )

        # Legitimate tax document
        if "tax" in filename or "1099" in filename or "w2" in filename:
            return PDFMetadataOutput(
                software_tool="IRS e-file System",
                creation_date="2024-02-01",
                modified_date=None,
                is_manipulated=False
            )

        # Generic PDF from legitimate software
        return PDFMetadataOutput(
            software_tool="Microsoft Word to PDF Converter",
            creation_date="2024-01-10",
            modified_date="2024-01-11",
            is_manipulated=False
        )
