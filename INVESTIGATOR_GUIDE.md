# Veritas GFO - Investigator's Guide

## What This System Does

Veritas automates the digital investigative research that would normally take hours of manual work:

1. **Physical Verification**: Is this a real business location or someone's house?
2. **Corporate Due Diligence**: When was the company formed? Is it active?
3. **Digital Footprint Analysis**: Does the applicant have a normal online presence?
4. **Document Forensics**: Are financial documents authentic or manipulated?

The system runs all these checks in parallel and generates a risk-scored report in minutes.

---

## Quick Start (5 Minutes)

### 1. Start the System

```bash
# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Wait 30 seconds for services to initialize
```

### 2. Access the Dashboard

Open: **http://localhost:3000**

You'll see the case management dashboard.

### 3. Submit a Test Case

**Option A: Via Dashboard (Coming Soon)**

**Option B: Via API**

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{
    "external_ref_id": "GRANT-2024-001",
    "applicant_name": "Acme Manufacturing LLC",
    "applicant_tax_id": "12-3456789",
    "applicant_address": "456 Industrial Parkway, Suite 100, Austin, TX 78701"
  }'
```

### 4. Monitor Investigation

The system will:
- Change status: `NEW` → `PROCESSING` → `REVIEW_REQUIRED`
- Run 9 investigative tools in parallel
- Calculate risk score (0-100)
- Generate BLUF narrative

This takes **30-60 seconds**.

### 5. Review Results

Click "View Details" on the case to see:
- **Risk Score Badge**: Color-coded (Green/Yellow/Red)
- **Investigation Narrative**: BLUF-style report
- **Evidence Cards**: Each verification step with findings
- **Visual Verification**: Street View image (if available)

### 6. Make Decision

Click one of:
- **Approve**: Low-risk case passes
- **Deny**: High-risk case rejected
- **Request More Info**: Medium-risk needs human review

---

## Understanding Risk Scores

| Score | Level | What It Means | Action |
|-------|-------|---------------|--------|
| 0-39 | **LOW** | Normal business profile | Approve |
| 40-69 | **MEDIUM** | Some concerns, needs review | Human judgment |
| 70-79 | **HIGH** | Serious fraud indicators | Deny |
| 80-100 | **CRITICAL** | Multiple red flags or document manipulation | Deny immediately |

---

## What Each Tool Checks

### Layer 1: Physical Verification

**StreetViewVisionTool**
- Fetches Google Street View image of claimed address
- AI analyzes: Is this residential or commercial?
- **Red Flag**: Residential address for "manufacturing" business
- **Points**: +25 if mismatch detected

**PropertyOwnerTool**
- Looks up property tax records
- Checks if applicant owns the property (self-dealing)
- **Red Flag**: Applicant rents from themselves
- **Points**: +15 if related party detected

### Layer 2: Corporate Verification

**RegistryStatusTool**
- Verifies business is registered with Secretary of State
- Calculates company age
- **Red Flag**: Company formed < 30 days ago (shell company)
- **Points**: +20 for new companies

**DomainForensicsTool**
- Checks when company website was created
- **Red Flag**: Domain < 30 days old (pop-up website)
- **Points**: +30 for brand new domains

**WebContentScraperTool**
- Analyzes website content
- **Red Flag**: Lorem Ipsum text, no staff bios
- **Points**: Informational (contributes to narrative)

### Layer 3: Digital Identity

**PhoneCarrierTool**
- Looks up phone number carrier
- **Red Flag**: VOIP/burner phone (Twilio, Google Voice)
- **Points**: +10 for VOIP

**EmailDigitalFootprintTool**
- Checks email on social platforms (LinkedIn, Twitter, etc.)
- **Red Flag**: Zero online presence (synthetic identity)
- **Points**: +15 for no profiles

**BreachHistoryTool**
- Checks HaveIBeenPwned for data breaches
- **Counter-intuitive**: Real adults usually in ≥1 breach
- **Red Flag**: Zero breaches may indicate fake identity
- **Points**: Informational

### Layer 4: Document Forensics

**PDFMetadataTool** ⚠️ **KILL SWITCH**
- Analyzes PDF metadata of bank statements, tax docs
- **Critical Red Flag**: Created with Photoshop/Canva
- **Points**: Automatic 100 (immediate denial)

---

## Real-World Investigation Workflow

### Scenario 1: High-Risk Case

**Applicant**: "QuickStart Solutions LLC"
**Address**: "123 Smith Street, Austin, TX"

**Investigation Results**:
- ❌ Company formed 15 days ago
- ❌ Website domain created 12 days ago
- ❌ Address is residential home
- ❌ No social media presence for owner
- ❌ Phone is VOIP number

**Risk Score**: 95/100 (CRITICAL)
**Recommendation**: **DENY** - Multiple fraud indicators

---

### Scenario 2: Low-Risk Case

**Applicant**: "Heritage Manufacturing Inc"
**Address**: "456 Industrial Parkway, Suite 200, Austin, TX"

**Investigation Results**:
- ✓ Company formed 5 years ago
- ✓ Website domain 3.5 years old
- ✓ Commercial office building with signage
- ✓ Owner has LinkedIn, Twitter, Facebook profiles
- ✓ Mobile phone from Verizon

**Risk Score**: 15/100 (LOW)
**Recommendation**: **APPROVE** - Normal business profile

---

### Scenario 3: Document Manipulation (Kill Switch)

**Applicant**: Any company
**Uploaded**: Bank statement PDF

**Investigation Results**:
- ❌ PDF metadata shows "Adobe Photoshop 24.1"
- ❌ File modified yesterday (but claims to be from 6 months ago)

**Risk Score**: 100/100 (CRITICAL)
**Recommendation**: **DENY IMMEDIATELY** - Fraudulent documents

---

## Adding Real API Keys

The system works with mock data out of the box, but for production use:

### 1. Edit `.env` File

```bash
# Required for real investigations
OPENAI_API_KEY=sk-your-actual-key-here
# OR
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here

# Optional (will use mock data if missing)
GOOGLE_MAPS_API_KEY=your-google-key
OPENCORPORATES_API_KEY=your-opencorporates-key
```

### 2. Restart Services

```bash
docker-compose restart backend
```

The system will automatically use real APIs when keys are present.

---

## Advanced: Bulk Case Processing

For high-volume scenarios:

```bash
# Submit multiple cases via script
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/v1/ingest \
    -H "Content-Type: application/json" \
    -H "X-AGENCY-TOKEN: dev-token-12345" \
    -d @case_${i}.json
done

# Monitor completion
curl http://localhost:8000/api/v1/stats \
  -H "X-AGENCY-TOKEN: dev-token-12345"
```

---

## Troubleshooting

**Investigation stuck in PROCESSING**:
```bash
# Check backend logs
docker-compose logs backend

# Look for errors in investigation
```

**Risk score is always 0**:
- Check that LLM API key is set (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- Mock mode should still calculate scores based on patterns

**"No evidence collected yet"**:
- Wait 30-60 seconds - investigations run in background
- Check `docker-compose logs backend` for errors

**Frontend can't connect to backend**:
```bash
# Verify backend is running
curl http://localhost:8000/health

# Check CORS settings if accessing from different domain
```

---

## API Reference

**Submit Case**:
```bash
POST /api/v1/ingest
Headers: X-AGENCY-TOKEN: dev-token-12345
Body: {
  "external_ref_id": "GRANT-001",
  "applicant_name": "Company Name",
  "applicant_tax_id": "12-3456789",
  "applicant_address": "123 Main St, City, ST 12345"
}
```

**List Cases**:
```bash
GET /api/v1/cases?status_filter=REVIEW_REQUIRED&min_risk_score=70
```

**Get Case Details**:
```bash
GET /api/v1/cases/{case_id}
```

**Adjudicate**:
```bash
POST /api/v1/cases/{case_id}/adjudicate
Body: {
  "status": "APPROVED",  // or "DENIED"
  "notes": "Approved after manual review"
}
```

**System Stats**:
```bash
GET /api/v1/stats
```

Full API documentation: **http://localhost:8000/docs**

---

## Best Practices

1. **Review Medium-Risk Cases First**: Focus on 40-69 scores
2. **Trust the Kill Switch**: Document manipulation = automatic deny
3. **Check Evidence, Not Just Score**: Read the narrative and evidence cards
4. **Look for Patterns**: Multiple weak signals can indicate sophisticated fraud
5. **Document Your Decision**: Use the "notes" field when adjudicating

---

## Getting Help

- **API Docs**: http://localhost:8000/docs
- **System Logs**: `docker-compose logs -f backend`
- **Database Access**: Use any PostgreSQL client with connection from `.env`

---

**Remember**: This system does the initial research. You make the final call.
