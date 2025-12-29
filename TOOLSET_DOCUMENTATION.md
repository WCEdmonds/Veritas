# Veritas GFO - Expanded Toolset Documentation

## Overview

The Veritas Government Fraud Orchestrator employs a **4-layer investigative framework** to detect fraudulent grant applications. Each layer targets specific fraud patterns with specialized tools.

## Investigation Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRAUD INVESTIGATION                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Physical Verification (40 pts max)                │
│  Layer 2: Corporate Verification (50 pts max)               │
│  Layer 3: Digital Identity (25 pts max)                     │
│  Layer 4: Document Forensics (KILL SWITCH = 100 pts)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Physical Verification Tools

**Module**: `app/agent/physical.py`

### 1. StreetViewVisionTool

**Purpose**: Visual confirmation of business existence and type.

**API**: Google Maps Static API + GPT-4 Vision

**Logic**:
1. Fetch Street View image of claimed business address
2. Pass image to Vision Model with prompt analyzing building type and signage
3. Flag mismatches (e.g., residential home for "manufacturing" business)

**Output Schema**:
```python
{
  "building_type": "residential|industrial|office|retail",
  "signage_detected": bool,
  "visual_risk_flag": bool,  # True if mismatch detected
  "image_url": "https://...",
  "description": "Detailed visual analysis"
}
```

**Fraud Triggers** (Mock Mode):
- Address contains "Smith" → Residential property (HIGH RISK)
- Address contains "Suite" → Normal commercial (LOW RISK)

**Risk Weight**: +25 points if residential property for commercial business

---

### 2. PropertyOwnerTool

**Purpose**: Detect undisclosed related-party transactions.

**API**: ATTOM Data or Estated (Property Records)

**Logic**:
- Look up property owner via tax records
- Fuzzy match owner name against applicant and key principals
- Flag if owner == applicant (self-dealing rent payments)

**Output Schema**:
```python
{
  "owner_name": "Jane Doe",
  "last_sale_date": "2020-01-01",
  "zoning_code": "R1 (Single Family)",
  "related_party_risk": bool  # True if owner matches applicant
}
```

**Fraud Triggers** (Mock Mode):
- Applicant name contains "Doe" → Related party risk
- Address contains "Smith" → Same owner as applicant

**Risk Weight**: +15 points if related party ownership detected

---

## Layer 2: Corporate Verification Tools

**Module**: `app/agent/corporate.py`

### 3. RegistryStatusTool

**Purpose**: Verify legal standing and formation date.

**API**: OpenCorporates or Middesk

**Logic**:
- Lookup company in state business registry
- Check status == "Active" and "Good Standing"
- Calculate `days_since_incorp` (< 30 days = shell company indicator)

**Output Schema**:
```python
{
  "legal_name": "Acme LLC",
  "incorporation_date": "2023-12-01",
  "status": "Active|Dissolved",
  "days_since_incorp": 14
}
```

**Fraud Triggers** (Mock Mode):
- Company name contains "QuickStart" → Formed 15 days ago
- Company name contains "Defunct" → Dissolved status

**Risk Weight**: +20 points if incorporated < 30 days ago

---

### 4. DomainForensicsTool

**Purpose**: Identify "pop-up" websites created for the grant.

**API**: WhoisXML API + BuiltWith

**Logic**:
1. Get domain creation date (< 30 days = fraud indicator)
2. Check registrar (cheap registrars = risk factor)
3. Analyze tech stack for template indicators

**Output Schema**:
```python
{
  "domain_age_days": 12,
  "is_template_site": bool,
  "registrar": "Namecheap",
  "risk_score": 0-100
}
```

**Fraud Triggers** (Mock Mode):
- Domain contains "quickstart" → 12 days old, template site
- Domain contains "template" → Template indicators

**Risk Weight**: +30 points if domain < 30 days old

---

### 5. WebContentScraperTool

**Purpose**: Verify operational history claims via website content.

**API**: Firecrawl (or Puppeteer) + LLM

**Logic**:
- Scrape "About Us" and "Team" pages
- LLM analyzes for Lorem Ipsum, stock text, and generic content
- Calculate consistency score (0-100)

**Output Schema**:
```python
{
  "has_lorem_ipsum": bool,
  "staff_count_mentioned": int,
  "consistency_score": 0-100,  # Low = fake site
  "about_us_text": "Scraped content"
}
```

**Fraud Triggers** (Mock Mode):
- URL contains "lorem" or "template" → Lorem ipsum detected
- URL contains "quickstart" → Fake template site

**Risk Weight**: Informational (factors into overall narrative)

---

## Layer 3: Digital Identity Tools

**Module**: `app/agent/identity.py`

### 6. PhoneCarrierTool

**Purpose**: Detect burner phones and VOIP numbers.

**API**: Telesign or Numverify

**Logic**:
- Look up phone number carrier
- Flag if `line_type == "VOIP"` (Twilio, Google Voice)
- Real businesses use legitimate carrier lines

**Output Schema**:
```python
{
  "carrier": "Twilio",
  "line_type": "VOIP|MOBILE|LANDLINE",
  "risk_flag": bool  # True if VOIP
}
```

**Fraud Triggers** (Mock Mode):
- Phone contains "555" → VOIP (Twilio)
- Phone starts with "800" → Toll-free VOIP

**Risk Weight**: +10 points if VOIP line type

---

### 7. EmailDigitalFootprintTool

**Purpose**: Synthetic identity detection via social presence.

**API**: SEON or Hunter.io

**Logic**:
- Check email registration on social platforms (LinkedIn, Twitter, Spotify)
- Real people have 5+ profiles
- Synthetic identities have 0-1 profiles

**Output Schema**:
```python
{
  "registered_profiles": ["netflix", "linkedin"],
  "profile_count": int,
  "social_score": "LOW|MEDIUM|HIGH"
}
```

**Fraud Triggers** (Mock Mode):
- Email contains "fraud" or "temp" → 0-1 profiles (HIGH RISK)
- Normal email → 6+ profiles (LOW RISK)

**Risk Weight**: +15 points if 0 profiles (synthetic identity)

---

### 8. BreachHistoryTool

**Purpose**: Counter-intuitive identity verification via data breaches.

**API**: HaveIBeenPwned

**Logic**:
- Check if email appears in known data breaches
- **Counter-intuitive**: US adults >30 typically in ≥1 breach
- Zero breaches = likely synthetic identity created recently

**Output Schema**:
```python
{
  "breach_count": int,
  "synthetic_identity_suspicion": "LOW|MEDIUM|HIGH"
}
```

**Fraud Triggers** (Mock Mode):
- Email contains "new" or "fresh" → 0 breaches (suspicious if age >30)
- Email contains "old" → 8 breaches (normal)

**Risk Weight**: Informational (high suspicion contributes to narrative)

---

## Layer 4: Document Forensics Tools

**Module**: `app/agent/forensics.py`

### 9. PDFMetadataTool

**Purpose**: Detect manipulated financial documents.

**API**: PyPDF2 (local) or Inscribe

**Logic**:
- Extract PDF metadata (`Producer`, `Creator` fields)
- Flag if created/edited with image software:
  - Photoshop, Canva, iLovePDF, Sejda, GIMP
- Legitimate docs use banking software (Chase Portal, QuickBooks)

**Output Schema**:
```python
{
  "software_tool": "Adobe Photoshop 24.1",
  "creation_date": "2024-01-01",
  "modified_date": "2024-01-02",
  "is_manipulated": bool
}
```

**Fraud Triggers** (Mock Mode):
- Filename contains "fake" or "edited" → Photoshop detected
- Filename contains "bank" → Legitimate banking software

**Risk Weight**: **KILL SWITCH** - If `is_manipulated == True`, risk_score = 100 (immediate fail)

---

## Risk Matrix Scoring Algorithm

The **Reporter Node** aggregates signals from all layers using weighted scoring:

```python
risk_score = 0

# LAYER 4: FORENSIC WEIGHTING (KILL SWITCH)
if PDFMetadata.is_manipulated:
    risk_score = 100  # Immediate fail, skip other checks

# LAYER 2: CORPORATE WEIGHTING
if DomainForensics.domain_age_days < 30:
    risk_score += 30
if RegistryStatus.days_since_incorp < 30:
    risk_score += 20

# LAYER 1: PHYSICAL WEIGHTING
if StreetViewVision.visual_risk_flag and building_type == "residential":
    risk_score += 25
if PropertyOwner.related_party_risk:
    risk_score += 15

# LAYER 3: IDENTITY WEIGHTING
if PhoneCarrier.line_type == "VOIP":
    risk_score += 10
if EmailDigitalFootprint.profile_count == 0:
    risk_score += 15

# Cap at 100
risk_score = min(risk_score, 100)
```

---

## Risk Levels and Recommendations

| Risk Score | Level      | Recommendation      |
|------------|------------|---------------------|
| 80-100     | CRITICAL   | **DENY**            |
| 70-79      | HIGH       | **DENY**            |
| 40-69      | MEDIUM     | **FURTHER_REVIEW**  |
| 0-39       | LOW        | **APPROVE**         |

---

## Mock Data Trigger Keywords

For **MVP testing**, tools return deterministic fraud scenarios based on keywords:

### High-Risk Triggers
- **Name**: "QuickStart", "Doe", "Smith"
- **Address**: "Smith" (residential mismatch)
- **Domain**: "quickstart", "template", "lorem"
- **Email**: "fraud", "temp", "fake", "new", "synthetic"
- **Phone**: "555" (VOIP)
- **Document**: "fake", "edited", "photoshop"

### Low-Risk Triggers
- **Name**: "Legacy", "Professional"
- **Address**: "Suite", "Building"
- **Domain**: "legacy", "professional"
- **Email**: "old", "legacy"
- **Phone**: Regular numbers
- **Document**: "bank", "tax", "statement"

---

## BLUF Reporting Style

All final reports follow **Bottom Line Up Front (BLUF)** format:

```markdown
**BLUF: Risk Score 85/100 (CRITICAL)**

Investigation of QuickStart Solutions LLC reveals CRITICAL fraud indicators.
Immediate denial recommended.

## Key Findings

1. CRITICAL: Document manipulation detected (Adobe Photoshop 24.1)
2. High Risk: Company formed 15 days ago
3. High Risk: Domain created 12 days ago
4. High Risk: Residential property for commercial business

## Evidence Summary

**Corporate Registration**: QuickStart Solutions LLC incorporated on 2024-12-14
(15 days ago). Status: Active.

**Physical Verification**: Single-family residential home. No business signage
visible. Property appears to be a personal residence.

**DOCUMENT FORENSICS**: Evidence of manipulation using Adobe Photoshop 24.1.
This is a critical fraud indicator.

## Recommendation

**DENY** this application based on fraud indicators.
```

---

## Testing the Expanded Toolset

### Create High-Risk Test Case

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{
    "external_ref_id": "FRAUD-TEST-001",
    "applicant_name": "QuickStart Solutions LLC",
    "applicant_tax_id": "98-7654321",
    "applicant_address": "123 Smith Street, Austin, TX 78701"
  }'
```

**Expected Result**: Risk Score ~85-100 (CRITICAL)

**Triggered Fraud Indicators**:
- "QuickStart" → Recently formed company (15 days)
- "Smith" → Residential property mismatch
- Mock domain → Recently created (12 days)

---

### Create Low-Risk Test Case

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{
    "external_ref_id": "LEGIT-TEST-001",
    "applicant_name": "Legacy Manufacturing Inc",
    "applicant_tax_id": "12-3456789",
    "applicant_address": "456 Business Park Drive, Suite 200, Austin, TX"
  }'
```

**Expected Result**: Risk Score ~15-25 (LOW)

**Normal Indicators**:
- "Legacy" → Established company (5 years old)
- "Suite" → Commercial office space
- Normal domain age and social presence

---

## Production Deployment Considerations

### API Keys Required

1. **Google Maps API** (Street View + Geocoding)
2. **OpenCorporates API** (Business registry)
3. **WhoisXML API** (Domain forensics)
4. **Telesign/Numverify** (Phone carrier lookup)
5. **SEON/Hunter.io** (Email footprint)
6. **HaveIBeenPwned** (Breach history)
7. **OpenAI/Anthropic** (LLM for analysis)

### Rate Limiting

- Implement rate limiting for external API calls
- Use caching for repeated lookups
- Queue investigations during high load

### Cost Optimization

- **Priority 1 (Always Run)**: RegistryStatus, StreetViewVision
- **Priority 2 (High Risk Cases)**: DocumentForensics, PropertyOwner
- **Priority 3 (Medium Risk)**: DomainForensics, PhoneCarrier
- **Priority 4 (Optional)**: WebContentScraper, BreachHistory

---

## Future Enhancements

1. **Machine Learning Layer**: Train model on historical fraud patterns
2. **Network Analysis**: Detect fraud rings via shared addresses/phones
3. **Real-Time Monitoring**: Track changes to company status post-approval
4. **External Data Feeds**: Integrate watchlists (OFAC, SAM.gov exclusions)
5. **Image Forensics**: Detect photoshopped images in submitted documents

---

## Support

For questions about the expanded toolset:
- Review API documentation: http://localhost:8000/docs
- Check investigation logs in database: `evidence_logs` table
- Monitor background task execution via Docker logs

