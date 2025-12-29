"""
Advanced Document Forensics - Image & PDF Analysis

Detects sophisticated document forgeries using:
1. Image Forensics: ELA, PRNU, Clone Detection
2. PDF Forensics: Incremental updates, Font analysis, Kerning
"""
import io
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageChops, ImageEnhance
import hashlib

from app.agent.base import BaseTool


class ErrorLevelAnalysisTool(BaseTool):
    """
    Error Level Analysis (ELA) - Detects JPEG compression inconsistencies.

    Forged images show different compression artifacts in edited regions.
    When you edit a JPEG and re-save, the edited area has LESS compression
    artifacts than the original, creating a "glow" in ELA visualization.
    """

    def __init__(self):
        super().__init__()

    async def execute(self, image_path: str, quality: int = 95) -> Dict[str, Any]:
        """
        Perform Error Level Analysis on image.

        Args:
            image_path: Path to image file
            quality: JPEG quality for re-compression (default 95)

        Returns:
            ELA results with anomaly detection
        """
        try:
            # Load original image
            original = Image.open(image_path)

            # Convert to RGB if necessary
            if original.mode != 'RGB':
                original = original.convert('RGB')

            # Re-save at specified quality
            temp_buffer = io.BytesIO()
            original.save(temp_buffer, format='JPEG', quality=quality)
            temp_buffer.seek(0)
            recompressed = Image.open(temp_buffer)

            # Calculate difference (Error Level)
            ela_image = ImageChops.difference(original, recompressed)

            # Enhance to make differences visible
            extrema = ela_image.getextrema()
            max_diff = max([ex[1] for ex in extrema])

            if max_diff == 0:
                # No differences - suspicious (either pristine or heavily edited)
                scale = 1
            else:
                scale = 255.0 / max_diff

            ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

            # Analyze ELA image for anomalies
            anomalies = self._detect_anomalies(ela_image)

            return {
                "is_forged": anomalies["anomaly_detected"],
                "max_error_level": max_diff,
                "anomaly_score": anomalies["score"],
                "suspicious_regions": anomalies["regions"],
                "ela_image_path": "/tmp/ela_output.jpg"  # In production: save to S3
            }

        except Exception as e:
            print(f"Error in ELA: {e}")
            return {
                "is_forged": False,
                "error": str(e)
            }

    def _detect_anomalies(self, ela_image: Image.Image) -> Dict[str, Any]:
        """
        Detect regions with unusual error levels.

        Forged regions typically show:
        - Lower error levels (recently edited = less compression)
        - Sharp boundaries between error levels
        """
        # Convert to numpy array
        ela_array = np.array(ela_image)

        # Calculate statistics
        mean_error = np.mean(ela_array)
        std_error = np.std(ela_array)
        max_error = np.max(ela_array)

        # Detect anomalies (regions significantly different from mean)
        threshold = mean_error + (2 * std_error)
        anomaly_pixels = np.sum(ela_array > threshold)
        total_pixels = ela_array.size

        anomaly_ratio = anomaly_pixels / total_pixels

        # Score: Higher ratio of anomalous pixels = more likely forged
        anomaly_score = min(anomaly_ratio * 100, 100)

        return {
            "anomaly_detected": anomaly_score > 15,  # 15% threshold
            "score": round(anomaly_score, 2),
            "regions": []  # In production: use cv2.findContours to locate regions
        }


class NoisePatternAnalysisTool(BaseTool):
    """
    PRNU (Photo Response Non-Uniformity) Analysis.

    Every camera sensor has a unique noise pattern (like a fingerprint).
    If part of an image was copy-pasted from another source, it will have
    a DIFFERENT noise pattern, revealing the forgery.
    """

    def __init__(self):
        super().__init__()

    async def execute(self, image_path: str) -> Dict[str, Any]:
        """
        Analyze noise patterns for copy-paste detection.

        Args:
            image_path: Path to image file

        Returns:
            Noise analysis results
        """
        try:
            img = Image.open(image_path).convert('L')  # Grayscale
            img_array = np.array(img, dtype=np.float64)

            # Extract high-frequency noise
            noise_pattern = self._extract_noise(img_array)

            # Divide image into blocks and analyze consistency
            blocks = self._divide_into_blocks(noise_pattern, block_size=64)
            consistency = self._analyze_consistency(blocks)

            return {
                "is_copy_paste_detected": consistency["is_inconsistent"],
                "consistency_score": consistency["score"],
                "suspicious_blocks": consistency["suspicious_count"],
                "total_blocks": consistency["total_blocks"]
            }

        except Exception as e:
            print(f"Error in PRNU analysis: {e}")
            return {
                "is_copy_paste_detected": False,
                "error": str(e)
            }

    def _extract_noise(self, img_array: np.ndarray) -> np.ndarray:
        """Extract high-frequency noise pattern using wavelet transform."""
        # Simplified: Use local variance as proxy for noise
        # In production: Use wavelet transform (pywt)

        kernel_size = 5
        padded = np.pad(img_array, kernel_size // 2, mode='edge')

        noise = np.zeros_like(img_array)
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                window = padded[i:i + kernel_size, j:j + kernel_size]
                noise[i, j] = np.var(window)

        return noise

    def _divide_into_blocks(self, array: np.ndarray, block_size: int) -> List[np.ndarray]:
        """Divide image into blocks for analysis."""
        blocks = []
        h, w = array.shape

        for i in range(0, h, block_size):
            for j in range(0, w, block_size):
                block = array[i:i + block_size, j:j + block_size]
                if block.shape[0] == block_size and block.shape[1] == block_size:
                    blocks.append(block)

        return blocks

    def _analyze_consistency(self, blocks: List[np.ndarray]) -> Dict[str, Any]:
        """
        Analyze if noise patterns are consistent across blocks.

        Inconsistent blocks = likely copy-paste from different source.
        """
        if not blocks:
            return {"is_inconsistent": False, "score": 0, "suspicious_count": 0, "total_blocks": 0}

        # Calculate statistics for each block
        block_stats = [np.mean(block) for block in blocks]

        # Overall statistics
        global_mean = np.mean(block_stats)
        global_std = np.std(block_stats)

        # Count blocks significantly different from mean
        threshold = global_mean + (2 * global_std)
        suspicious_blocks = sum(1 for stat in block_stats if abs(stat - global_mean) > threshold)

        inconsistency_ratio = suspicious_blocks / len(blocks)
        consistency_score = (1 - inconsistency_ratio) * 100

        return {
            "is_inconsistent": inconsistency_ratio > 0.2,  # 20% threshold
            "score": round(consistency_score, 2),
            "suspicious_count": suspicious_blocks,
            "total_blocks": len(blocks)
        }


class CloneDetectionTool(BaseTool):
    """
    Clone Detection (Copy-Move Forgery) using SIFT.

    Detects when a region of an image is copied and pasted elsewhere in
    the same image. Common in check fraud (duplicating amounts/signatures).

    The Tell: Natural images have unique features. If two regions have
    IDENTICAL keypoint descriptors, one was cloned.
    """

    def __init__(self):
        super().__init__()

    async def execute(self, image_path: str) -> Dict[str, Any]:
        """
        Detect copy-move forgery using feature matching.

        Args:
            image_path: Path to image file

        Returns:
            Clone detection results
        """
        # This requires OpenCV which we haven't installed yet
        # For MVP: Return mock data
        return await self._mock_response(image_path)

    async def _mock_response(self, image_path: str) -> Dict[str, Any]:
        """
        Mock clone detection.

        In production: Use cv2.SIFT() to find duplicate keypoint clusters.
        """
        filename = image_path.split('/')[-1].lower()

        # Mock: Detect clones in files with "cloned" in name
        if "clone" in filename or "duplicate" in filename:
            return {
                "clone_detected": True,
                "clone_pairs": 3,
                "confidence": 0.94,
                "description": "Found 3 regions with identical feature descriptors (SIFT). Likely copy-move forgery."
            }

        return {
            "clone_detected": False,
            "clone_pairs": 0,
            "confidence": 0.0,
            "description": "No duplicate regions detected."
        }


class PDFIncrementalUpdateTool(BaseTool):
    """
    PDF Incremental Update Detection.

    When you edit a PDF and "Save" (not "Save As"), the editor appends
    changes to the end of the file. The ORIGINAL data is still there.

    The Tell: Multiple %%EOF markers indicate edit layers. You can
    "rollback" to see the original $500 before it was changed to $50,000.
    """

    def __init__(self):
        super().__init__()

    async def execute(self, pdf_path: str) -> Dict[str, Any]:
        """
        Detect incremental updates (hidden edit history) in PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Incremental update analysis
        """
        try:
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()

            # Count %%EOF markers
            eof_count = pdf_content.count(b'%%EOF')

            # Count xref tables (cross-reference tables)
            xref_count = pdf_content.count(b'xref')

            # Normal PDF: 1 EOF, 1 xref
            # Edited PDF: Multiple EOFs and xrefs

            is_edited = eof_count > 1 or xref_count > 1

            # Extract version history
            versions = self._extract_versions(pdf_content, eof_count)

            return {
                "is_incrementally_updated": is_edited,
                "eof_count": eof_count,
                "xref_count": xref_count,
                "edit_layers": eof_count,
                "versions": versions,
                "suspicion": "HIGH" if eof_count > 2 else "LOW"
            }

        except Exception as e:
            print(f"Error in incremental update detection: {e}")
            return {
                "is_incrementally_updated": False,
                "error": str(e)
            }

    def _extract_versions(self, pdf_content: bytes, eof_count: int) -> List[Dict[str, Any]]:
        """
        Extract different versions from incremental updates.

        In production: Parse each xref section to reconstruct versions.
        """
        versions = []

        # Simple version detection
        eof_positions = []
        start = 0
        while True:
            pos = pdf_content.find(b'%%EOF', start)
            if pos == -1:
                break
            eof_positions.append(pos)
            start = pos + 1

        for i, pos in enumerate(eof_positions):
            versions.append({
                "version": i + 1,
                "byte_position": pos,
                "description": f"Edit layer {i + 1}" if i > 0 else "Original"
            })

        return versions


class FontAnalysisTool(BaseTool):
    """
    PDF Font & Glyph Analysis.

    Banks use specific embedded fonts from their mainframe systems.
    Fraudsters editing in Word/Acrobat use system fonts that LOOK similar
    but have different kerning, glyph shapes, and internal names.

    The Tell:
    1. Font Collision: PDF lists "CourierBank" AND "CourierNew" - why two?
    2. Inconsistent Kerning: Automated systems have perfect spacing.
       Manual edits have irregular spacing.
    """

    def __init__(self):
        super().__init__()

    async def execute(self, pdf_path: str) -> Dict[str, Any]:
        """
        Analyze fonts and kerning for forgery indicators.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Font analysis results
        """
        try:
            # This requires PyPDF2 or pdfminer
            # For MVP: Return mock analysis
            return await self._mock_response(pdf_path)

        except Exception as e:
            print(f"Error in font analysis: {e}")
            return {
                "font_anomaly_detected": False,
                "error": str(e)
            }

    async def _mock_response(self, pdf_path: str) -> Dict[str, Any]:
        """
        Mock font analysis.

        In production: Use PyPDF2 to extract:
        - Font dictionary (/FontName, /FontFile)
        - Text rendering operators (Tj, TJ)
        - Kerning values
        """
        filename = pdf_path.split('/')[-1].lower()

        # Mock: Detect font anomalies in files with "edited" in name
        if "edit" in filename or "fake" in filename:
            return {
                "font_anomaly_detected": True,
                "fonts_detected": ["CourierBank-Roman", "ArialMT", "Helvetica"],
                "anomalies": [
                    {
                        "type": "FONT_COLLISION",
                        "description": "Document contains both 'CourierBank-Roman' (original) and 'ArialMT' (manual edit)"
                    },
                    {
                        "type": "INCONSISTENT_KERNING",
                        "description": "Line 23 shows irregular character spacing (manual typing)"
                    }
                ],
                "confidence": 0.89
            }

        return {
            "font_anomaly_detected": False,
            "fonts_detected": ["CourierBank-Roman"],
            "anomalies": [],
            "confidence": 0.95
        }


class ForensicPipeline:
    """
    Orchestrates all forensic checks in a single pipeline.

    Runs image and PDF forensics in parallel and generates
    comprehensive forgery report.
    """

    def __init__(self):
        # Image forensics
        self.ela_tool = ErrorLevelAnalysisTool()
        self.prnu_tool = NoisePatternAnalysisTool()
        self.clone_tool = CloneDetectionTool()

        # PDF forensics
        self.incremental_tool = PDFIncrementalUpdateTool()
        self.font_tool = FontAnalysisTool()

    async def analyze_document(
        self,
        file_path: str,
        file_type: str = "pdf"
    ) -> Dict[str, Any]:
        """
        Run full forensic pipeline on document.

        Args:
            file_path: Path to document
            file_type: "pdf", "image", or "auto"

        Returns:
            Comprehensive forensic analysis
        """
        results = {
            "file_path": file_path,
            "file_type": file_type,
            "is_forged": False,
            "forgery_confidence": 0.0,
            "checks_performed": [],
            "anomalies": []
        }

        if file_type in ["pdf", "auto"]:
            # PDF Forensics
            incremental_result = await self.incremental_tool.execute(file_path)
            font_result = await self.font_tool.execute(file_path)

            results["checks_performed"].extend(["incremental_updates", "font_analysis"])

            if incremental_result.get("is_incrementally_updated"):
                results["anomalies"].append({
                    "type": "PDF_INCREMENTAL_UPDATES",
                    "severity": "HIGH",
                    "details": incremental_result
                })

            if font_result.get("font_anomaly_detected"):
                results["anomalies"].append({
                    "type": "PDF_FONT_ANOMALY",
                    "severity": "MEDIUM",
                    "details": font_result
                })

        if file_type in ["image", "auto"]:
            # Image Forensics
            ela_result = await self.ela_tool.execute(file_path)
            prnu_result = await self.prnu_tool.execute(file_path)
            clone_result = await self.clone_tool.execute(file_path)

            results["checks_performed"].extend(["ela", "prnu", "clone_detection"])

            if ela_result.get("is_forged"):
                results["anomalies"].append({
                    "type": "IMAGE_COMPRESSION_ANOMALY",
                    "severity": "HIGH",
                    "details": ela_result
                })

            if prnu_result.get("is_copy_paste_detected"):
                results["anomalies"].append({
                    "type": "IMAGE_COPY_PASTE",
                    "severity": "HIGH",
                    "details": prnu_result
                })

            if clone_result.get("clone_detected"):
                results["anomalies"].append({
                    "type": "IMAGE_CLONE_FORGERY",
                    "severity": "CRITICAL",
                    "details": clone_result
                })

        # Calculate overall forgery probability
        if results["anomalies"]:
            results["is_forged"] = True

            # Weight by severity
            severity_weights = {"CRITICAL": 1.0, "HIGH": 0.7, "MEDIUM": 0.4, "LOW": 0.2}
            confidence = sum(
                severity_weights[a["severity"]] for a in results["anomalies"]
            ) / len(results["anomalies"])

            results["forgery_confidence"] = min(confidence * 100, 100)

        return results
