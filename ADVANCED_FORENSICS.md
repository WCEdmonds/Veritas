# Layer 4 Enhanced: Advanced Document Forensics

## Overview

While basic PDF metadata analysis (Layer 4) detects simple manipulation flags, **Advanced Forensics** uses sophisticated image analysis and document structure inspection to catch forgeries that pass basic checks:

- **Error Level Analysis (ELA)**: JPEG compression inconsistencies
- **Noise Pattern Analysis (PRNU)**: Camera sensor fingerprinting
- **Clone Detection**: Copy-move forgery using SIFT
- **PDF Incremental Updates**: Hidden edit history
- **Font & Glyph Analysis**: Font collision and kerning inconsistencies

---

## A. Error Level Analysis (ELA)

### The Question
*"Why does this $50,000 invoice show different JPEG compression artifacts than the rest of the document?"*

### How It Works

1. **Re-compression Test**: Load original image and re-save at 95% JPEG quality
2. **Difference Calculation**: Compare pixel-by-pixel differences between original and re-compressed
3. **Anomaly Detection**: Edited regions show different error levels than untouched regions

### The Science

When you edit a JPEG and re-save:
- **Original areas**: Already compressed, minimal new artifacts
- **Edited areas**: Freshly compressed, show different error patterns
- **Result**: Edited regions "glow" in ELA visualization

### Tool: `ErrorLevelAnalysisTool`

**Input**:
```python
image_path = "/uploads/invoice_scan.jpg"
quality = 95  # Re-compression quality
```

**Output**:
```json
{
  "is_forged": true,
  "max_error_level": 47,
  "anomaly_score": 23.5,
  "suspicious_regions": [],
  "ela_image_path": "/tmp/ela_output.jpg"
}
```

### Risk Weight
**+40 points** if anomaly_score > 15% (significant compression inconsistencies)

### Real-World Example

**Scenario**: PPP Loan Forgery

Fraudster scanned a legitimate bank statement showing $5,000 balance, then:
1. Edited in Photoshop to change $5,000 → $500,000
2. Re-saved as JPEG

**Detection**: ELA revealed the edited dollar amount had 3x higher error level than surrounding text, proving manipulation.

---

## B. Noise Pattern Analysis (PRNU)

### The Question
*"Was this signature copy-pasted from a different document?"*

### How It Works

1. **Noise Extraction**: Extract high-frequency noise patterns (camera sensor artifacts)
2. **Block Division**: Divide image into 64x64 pixel blocks
3. **Consistency Analysis**: Compare noise patterns across blocks
4. **Inconsistency Detection**: Different noise patterns = copy-paste from different source

### The Science

Every camera sensor has unique manufacturing defects that create a noise "fingerprint":
- **Original photo**: Consistent noise pattern across entire image
- **Copy-pasted region**: Different noise pattern (from different camera/scan)
- **Result**: PRNU mismatch reveals forgery

### Tool: `NoisePatternAnalysisTool`

**Input**:
```python
image_path = "/uploads/contract_signature.jpg"
```

**Output**:
```json
{
  "is_copy_paste_detected": true,
  "consistency_score": 62.5,
  "suspicious_blocks": 12,
  "total_blocks": 48
}
```

### Risk Weight
**+30 points** if consistency_score < 70% (20%+ blocks show noise inconsistency)

### Real-World Example

**Scenario**: Contract Signature Forgery

Fraudster took legitimate contract and copy-pasted a signature from a different document scanned on a different scanner.

**Detection**: PRNU analysis showed signature region had different noise characteristics than the rest of the contract, proving it was spliced from another source.

---

## C. Clone Detection (Copy-Move Forgery)

### The Question
*"Did someone copy-paste the signature from one location to another on the same check?"*

### How It Works

1. **Feature Extraction**: Use SIFT to extract keypoint descriptors from image
2. **Self-Matching**: Find regions within the same image with identical descriptors
3. **Cluster Analysis**: Group matching keypoints into regions
4. **Clone Detection**: Multiple identical regions = copy-move forgery

### The Science

Natural images have unique features. If two regions have IDENTICAL keypoint descriptors:
- One was cloned from the other
- Common in check fraud (duplicate amounts, signatures)

### Tool: `CloneDetectionTool`

**Input**:
```python
image_path = "/uploads/check_scan.jpg"
```

**Output**:
```json
{
  "clone_detected": true,
  "clone_pairs": 3,
  "confidence": 0.94,
  "description": "Found 3 regions with identical feature descriptors (SIFT). Likely copy-move forgery."
}
```

### Risk Weight
**+50 points** if clone_detected = true with confidence > 0.85

### Real-World Example

**Scenario**: Check Amount Duplication

Fraudster wrote check for $100, then:
1. Scanned the check
2. Copy-pasted the "1" to make it read "$1100"
3. Printed the modified check

**Detection**: SIFT keypoints for the duplicated "1" were identical to the original "1", exposing the clone.

---

## D. PDF Incremental Updates (Hidden Edit History)

### The Question
*"Why does this PDF have 3 different versions embedded inside it?"*

### How It Works

1. **EOF Marker Count**: Count `%%EOF` markers in PDF file structure
2. **XRef Table Analysis**: Count cross-reference tables
3. **Version Extraction**: Reconstruct document versions from incremental updates

### The Science

When you edit a PDF and click "Save" (not "Save As"):
- Editor **appends** changes to end of file
- Original data remains embedded
- Multiple `%%EOF` markers indicate edit layers

**Normal PDF**: 1 EOF, 1 xref table
**Edited PDF**: Multiple EOFs, multiple xref tables

### Tool: `PDFIncrementalUpdateTool`

**Input**:
```python
pdf_path = "/uploads/bank_statement.pdf"
```

**Output**:
```json
{
  "is_incrementally_updated": true,
  "eof_count": 3,
  "xref_count": 3,
  "edit_layers": 3,
  "versions": [
    {
      "version": 1,
      "byte_position": 12450,
      "description": "Original"
    },
    {
      "version": 2,
      "byte_position": 15892,
      "description": "Edit layer 1"
    },
    {
      "version": 3,
      "byte_position": 18234,
      "description": "Edit layer 2"
    }
  ],
  "suspicion": "HIGH"
}
```

### Risk Weight
**+40 points** if eof_count > 2 (multiple edit layers)

### Real-World Example

**Scenario**: Bank Statement Manipulation

Fraudster received bank statement showing:
- **Original**: $500 balance
- **Edit 1**: Changed to $50,000
- **Edit 2**: Changed date to earlier month

**Detection**: PDF contained 3 `%%EOF` markers. By extracting version 1, investigators recovered the original $500 balance, proving manipulation.

---

## E. Font & Glyph Analysis

### The Question
*"Why does this 'official' bank document have two different fonts for the dollar amounts?"*

### How It Works

1. **Font Extraction**: Parse PDF font dictionary to list all embedded fonts
2. **Collision Detection**: Flag documents with multiple similar fonts (e.g., "Courier-Bank" + "Courier-New")
3. **Kerning Analysis**: Measure character spacing for manual typing vs automated generation

### The Science

Banks use specific embedded fonts from mainframe systems:
- **Legitimate docs**: Single font, perfect kerning (automated)
- **Forged docs**: Multiple fonts, irregular kerning (manual edits in Word/Acrobat)

**Font Collision Example**:
- Original bank statement uses "CourierBank-Roman" (proprietary)
- Fraudster edits in Word, which substitutes "CourierNew" (system font)
- PDF now contains BOTH fonts

### Tool: `FontAnalysisTool`

**Input**:
```python
pdf_path = "/uploads/payroll_summary.pdf"
```

**Output**:
```json
{
  "font_anomaly_detected": true,
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
```

### Risk Weight
**+35 points** if font_anomaly_detected = true with confidence > 0.80

### Real-World Example

**Scenario**: W2 Form Forgery

Fraudster received legitimate W2 showing $30,000 income, then:
1. Opened in Adobe Acrobat
2. Manually typed over the amount to read "$300,000"
3. Saved the edited PDF

**Detection**:
- Font analysis revealed TWO embedded fonts: "Helvetica" (original IRS font) and "Arial" (fraudster's edit)
- Kerning analysis showed the $300,000 had irregular spacing compared to the automated IRS fields

---

## F. ForensicPipeline (Orchestrator)

### Comprehensive Analysis

The `ForensicPipeline` runs all forensic checks in parallel and generates a weighted forgery report.

### Usage

```python
from app.agent.forensics_advanced import ForensicPipeline

pipeline = ForensicPipeline()

result = await pipeline.analyze_document(
    file_path="/uploads/suspicious_invoice.pdf",
    file_type="auto"  # "pdf", "image", or "auto"
)
```

### Output

```json
{
  "file_path": "/uploads/suspicious_invoice.pdf",
  "file_type": "pdf",
  "is_forged": true,
  "forgery_confidence": 87.5,
  "checks_performed": [
    "incremental_updates",
    "font_analysis",
    "ela",
    "prnu",
    "clone_detection"
  ],
  "anomalies": [
    {
      "type": "PDF_INCREMENTAL_UPDATES",
      "severity": "HIGH",
      "details": {
        "eof_count": 3,
        "edit_layers": 3
      }
    },
    {
      "type": "PDF_FONT_ANOMALY",
      "severity": "MEDIUM",
      "details": {
        "fonts_detected": ["CourierBank-Roman", "ArialMT"],
        "confidence": 0.89
      }
    },
    {
      "type": "IMAGE_COMPRESSION_ANOMALY",
      "severity": "HIGH",
      "details": {
        "anomaly_score": 23.5
      }
    }
  ]
}
```

### Confidence Calculation

Weighted by severity:
- **CRITICAL**: 1.0 weight
- **HIGH**: 0.7 weight
- **MEDIUM**: 0.4 weight
- **LOW**: 0.2 weight

```python
confidence = sum(severity_weights[a["severity"]] for a in anomalies) / len(anomalies) * 100
```

---

## Integration with Risk Matrix

### Updated Scoring (Layer 4 Enhanced)

```python
risk_score = 0

# LAYER 4: ADVANCED FORENSICS (KILL SWITCH)
if ForensicPipeline.forgery_confidence >= 80:
    risk_score = 100  # Automatic denial
elif ForensicPipeline.forgery_confidence >= 50:
    risk_score += 40   # High risk

# Individual tool scoring
if PDFIncrementalUpdate.eof_count > 2:
    risk_score += 40

if FontAnalysis.font_anomaly_detected:
    risk_score += 35

if CloneDetection.clone_detected:
    risk_score += 50

if ELA.anomaly_score > 15:
    risk_score += 40

if PRNU.consistency_score < 70:
    risk_score += 30
```

---

## Performance Considerations

### Processing Time

| Check | Image (1MB) | PDF (1MB) |
|-------|-------------|-----------|
| ELA | 100-200ms | N/A |
| PRNU | 200-400ms | N/A |
| Clone Detection | 500-800ms | N/A |
| Incremental Updates | N/A | 50-100ms |
| Font Analysis | N/A | 100-200ms |
| **Total Pipeline** | ~1.5 seconds | ~200ms |

### Optimization

- Run image and PDF checks in **parallel**
- Cache results for repeated document checks
- Use background processing for batch analysis

---

## Limitations & Future Enhancements

### Current Limitations

1. **Clone Detection**: Requires OpenCV for full SIFT implementation
2. **Font Analysis**: Mock data; requires PyPDF2/pdfminer for production
3. **ELA**: Works best on JPEG images; PNG/TIFF require different approaches

### Future Enhancements

1. **Deep Learning Forgery Detection**: Train CNN on known forgeries
2. **Blockchain Verification**: Check document hashes against blockchain ledger
3. **Metadata Timeline**: Cross-reference edit timestamps with submission timeline
4. **OCR Consistency**: Compare OCR results before/after suspected edits

---

## Testing

### Test Advanced Forensics

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -F "file=@suspicious_invoice.pdf" \
  -F "applicant_name=Test Company LLC"
```

### Expected Output

If document contains forgery indicators, investigation report will show:

```
## Key Findings

1. CRITICAL: Advanced forensics detected forgery (87% confidence)
2. High Risk: Document forensics shows forgery indicators (88% confidence)
3. High Risk: Domain created 15 days ago
```

---

## Summary

Advanced Forensics transforms document verification from "Was this edited?" to **"Exactly how was this edited?"**:

| Basic Forensics | Advanced Forensics |
|-----------------|-------------------|
| Checks metadata flags | Analyzes pixel-level artifacts |
| Detects simple edits | Detects sophisticated forgeries |
| Binary (edited/not edited) | Confidence score (0-100%) |
| Fooled by "Save As" | Finds hidden edit history |

**Key Insight**: Fraudsters can fool basic metadata checks. They cannot fool physics (compression artifacts, noise patterns, font rendering).
