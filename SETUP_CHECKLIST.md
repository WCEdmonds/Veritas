# Veritas GFO - Complete Setup Checklist

## 1. Required API Keys ✅ MANDATORY

### Core LLM Provider (Choose One)

**Option A: OpenAI** (Recommended for GPT-4 Vision)
```bash
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
```
- Get from: https://platform.openai.com/api-keys
- Cost: ~$0.01 per investigation
- **Required for**: StreetViewVisionTool (Layer 1)

**Option B: Anthropic Claude**
```bash
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=anthropic
```
- Get from: https://console.anthropic.com/
- Cost: ~$0.008 per investigation
- **Note**: Cannot use vision features; StreetViewVisionTool will use mock data

---

## 2. External Data Sources ⚠️ OPTIONAL

### Google Maps API (Layer 1 - Physical)

**Status**: Optional (Mock data available)

```bash
GOOGLE_MAPS_API_KEY=AIza...
```

**What you get**:
- ✅ Real Street View images + GPT-4 Vision analysis
- ✅ Actual property owner records (via Google Places)

**Without it**:
- ❌ Falls back to keyword-based mock data
- ❌ Cannot verify actual building types

**Cost**: $0.007 per Street View image
**Get from**: https://console.cloud.google.com/ (Enable: Street View Static API)

---

### OpenCorporates API (Layer 2 - Corporate)

**Status**: Optional (Mock data available)

```bash
OPENCORPORATES_API_KEY=...
```

**What you get**:
- ✅ Real company incorporation dates
- ✅ Actual business registry status
- ✅ Corporate officer lists

**Without it**:
- ❌ Falls back to keyword-based mock data
- ❌ "QuickStart" in name → triggers "15 days old"

**Cost**: Free tier (100 requests/month), Pro ($250/month)
**Get from**: https://api.opencorporates.com/

**Alternative (Free)**:
```bash
# Use SEC Edgar for US companies (no API key needed)
SEC_EDGAR_ENABLED=true
```
- Public domain data
- US companies only
- No rate limits

---

### Layer 3: Identity Verification (⚠️ LexisNexis NOT Required)

LexisNexis is **OPTIONAL**. Most clients won't have access. Use these alternatives instead:

#### Option 1: Free/Cheap Alternatives (Recommended)

**A. Phone Verification** (PhoneCarrierTool)

```bash
# Option 1: Twilio Lookup API (Recommended)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
PHONE_VERIFICATION_PROVIDER=twilio

# Option 2: NumVerify (Free Tier)
NUMVERIFY_API_KEY=...
PHONE_VERIFICATION_PROVIDER=numverify

# Option 3: Pattern Matching (No API needed)
PHONE_VERIFICATION_PROVIDER=pattern  # Free, detects common VOIP prefixes
```

**Comparison**:
| Provider | Cost | Accuracy | VOIP Detection |
|----------|------|----------|----------------|
| Twilio | $0.005/lookup | 95% | ✅ Excellent |
| NumVerify | Free (250/mo) | 80% | ✅ Good |
| Pattern | Free | 60% | ⚠️ Basic |

**B. Email Verification** (EmailDigitalFootprintTool)

```bash
# Option 1: Have I Been Pwned (Recommended)
HIBP_API_KEY=...  # Free for non-commercial use
EMAIL_VERIFICATION_PROVIDER=hibp

# Option 2: EmailRep.io (Free)
EMAILREP_API_KEY=...
EMAIL_VERIFICATION_PROVIDER=emailrep

# Option 3: Google Custom Search
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_CX=...
EMAIL_VERIFICATION_PROVIDER=google
```

**What each provides**:
- **HIBP**: Breach history (free, rate-limited)
- **EmailRep.io**: Reputation score, social profiles (250/day free)
- **Google**: Social media presence via search (100/day free)

**C. Breach History** (BreachHistoryTool)

```bash
# Use Have I Been Pwned (same as above)
HIBP_API_KEY=...
BREACH_VERIFICATION_PROVIDER=hibp
```

**D. Employee Ghost Check** (EmployeeGhostCheckTool)

```bash
# Option 1: Direct SSA Death Master File (Recommended - Free!)
DMF_SOURCE=direct
DMF_FILE_PATH=/data/ssdmf.txt  # Download from SSA

# Option 2: Skip this check entirely
ENABLE_GHOST_CHECK=false
```

**Download SSA Death Master File**:
```bash
# Free download (updated monthly)
wget https://www.ssdmf.com/Library/Home/DownloadLatest
# Or purchase from: https://www.ntis.gov/
```

#### Option 2: Use LexisNexis (If You Have Access)

```bash
LEXISNEXIS_API_KEY=...
LEXISNEXIS_ENDPOINT=...
ENABLE_LEXISNEXIS=true

# All Layer 3 tools will use LexisNexis
PHONE_VERIFICATION_PROVIDER=lexisnexis
EMAIL_VERIFICATION_PROVIDER=lexisnexis
BREACH_VERIFICATION_PROVIDER=lexisnexis
```

**Cost**: Enterprise only (~$50K/year minimum contract)

---

## 3. Recommended Configuration (No LexisNexis)

### Minimum Viable Setup (Free/Cheap)

```bash
# Required
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai

# Layer 1: Physical (Optional)
GOOGLE_MAPS_API_KEY=AIza...

# Layer 2: Corporate (Free alternative)
SEC_EDGAR_ENABLED=true

# Layer 3: Identity (Free alternatives)
PHONE_VERIFICATION_PROVIDER=pattern  # Free pattern matching
HIBP_API_KEY=...  # Free breach check
EMAIL_VERIFICATION_PROVIDER=hibp

# Layer 5: Employee verification (Free)
DMF_SOURCE=direct
DMF_FILE_PATH=/data/ssdmf.txt

# Databases (included in Docker)
DATABASE_URL=postgresql://veritas:veritas_pass@postgres:5432/veritas_db
REDIS_URL=redis://redis:6379/0
CHROMA_URL=http://chromadb:8000
NEO4J_URI=bolt://neo4j:7687
NEO4J_PASSWORD=veritas_graph_pass

# Security
API_SECRET_KEY=your-secret-key-here
AGENCY_API_TOKEN=dev-token-12345
```

**Total Cost**: ~$20-40/month (OpenAI + Google Maps usage)

---

## 4. Environment File Template

### `backend/.env` (Updated)

```bash
# ===== REQUIRED =====
# LLM Provider (choose one)
LLM_PROVIDER=openai  # or "anthropic"
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
LLM_TEMPERATURE=0

# Database
DATABASE_URL=postgresql://veritas:veritas_pass@postgres:5432/veritas_db
REDIS_URL=redis://redis:6379/0

# Security
API_SECRET_KEY=  # Generate with: openssl rand -hex 32
AGENCY_API_TOKEN=dev-token-12345

# ===== LAYER 1: PHYSICAL (OPTIONAL) =====
GOOGLE_MAPS_API_KEY=

# ===== LAYER 2: CORPORATE (OPTIONAL) =====
OPENCORPORATES_API_KEY=
# OR use free alternative:
SEC_EDGAR_ENABLED=true

# ===== LAYER 3: IDENTITY (CHOOSE ALTERNATIVES) =====
# LexisNexis (OPTIONAL - most clients won't have this)
ENABLE_LEXISNEXIS=false
# LEXISNEXIS_API_KEY=
# LEXISNEXIS_ENDPOINT=

# Phone Verification (choose one)
PHONE_VERIFICATION_PROVIDER=pattern  # "twilio", "numverify", or "pattern"
# TWILIO_ACCOUNT_SID=
# TWILIO_AUTH_TOKEN=
# NUMVERIFY_API_KEY=

# Email Verification (choose one)
EMAIL_VERIFICATION_PROVIDER=hibp  # "hibp", "emailrep", or "google"
HIBP_API_KEY=  # Free for non-commercial
# EMAILREP_API_KEY=
# GOOGLE_SEARCH_API_KEY=
# GOOGLE_SEARCH_CX=

# Breach History
BREACH_VERIFICATION_PROVIDER=hibp  # Uses same HIBP key above

# ===== LAYER 5: CROSS-CASE INTELLIGENCE =====
CHROMA_URL=http://chromadb:8000
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=veritas_graph_pass

# Employee Ghost Check (choose one)
DMF_SOURCE=direct  # "direct" (SSA file) or "lexisnexis"
DMF_FILE_PATH=/data/ssdmf.txt
# OR disable entirely:
# ENABLE_GHOST_CHECK=false
```

---

## 5. Quick Start Instructions

### Step 1: Install Dependencies

```bash
# Clone repository
git clone <repo-url>
cd Veritas

# Copy environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### Step 2: Configure Minimum Required Keys

```bash
# Edit backend/.env
nano backend/.env

# Set these 3 values:
# 1. OPENAI_API_KEY=sk-...
# 2. API_SECRET_KEY=$(openssl rand -hex 32)
# 3. AGENCY_API_TOKEN=dev-token-12345
```

### Step 3: (Optional) Download SSA Death Master File

```bash
# Create data directory
mkdir -p data

# Download SSA Death Master File (free, public domain)
# Option 1: NTIS (official, $50 one-time)
# https://www.ntis.gov/products/ssa-death-master-file

# Option 2: Free mirror (updated monthly)
wget -O data/ssdmf.txt https://ssdmf.info/download/latest

# Set in .env
echo "DMF_FILE_PATH=/data/ssdmf.txt" >> backend/.env
```

### Step 4: Start Services

```bash
docker-compose up -d
```

Wait 30 seconds for initialization, then verify:

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}
```

### Step 5: Test System

```bash
# Submit test case
curl -X POST http://localhost:8000/api/v1/cases \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "applicant_name": "QuickStart LLC",
    "applicant_tax_id": "12-3456789",
    "applicant_address": "123 Smith St",
    "external_ref_id": "TEST-001"
  }'

# Trigger investigation
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/investigate \
  -H "X-AGENCY-TOKEN: dev-token-12345"
```

---

## 6. Tool Behavior Matrix

### What Works Without External APIs

| Layer | Tool | With APIs | Without APIs |
|-------|------|-----------|--------------|
| **1** | StreetViewVision | Real images + GPT-4V | Mock: "Smith" = residential |
| **1** | PropertyOwner | Real ownership data | Mock: "Smith" = related party |
| **2** | RegistryStatus | Real incorporation dates | Mock: "QuickStart" = 15 days |
| **2** | DomainForensics | Real WHOIS data | Mock: "QuickStart" = 15 days |
| **2** | WebContentScraper | Real website scraping | Mock: Lorem Ipsum detection |
| **3** | PhoneCarrier | Real carrier lookup | Pattern: "555" = VOIP |
| **3** | EmailFootprint | Real social profiles | Mock: "fraud@" = no profiles |
| **3** | BreachHistory | Real breach data | Mock: 0 breaches (suspicious) |
| **4** | PDFMetadata | ✅ Always works | ✅ Local file analysis |
| **4** | Advanced Forensics | ✅ Always works | ✅ Pixel-level analysis |
| **5** | VectorSimilarity | ✅ Always works | ✅ ChromaDB (local) |
| **5** | JobBoardScraper | Real Indeed/LinkedIn | Mock: 0 postings |
| **5** | EmployeeGhostCheck | SSA DMF or LexisNexis | Mock or disabled |
| **5** | GraphNetwork | ✅ Always works | ✅ Neo4j (local) |

**Key Insight**: Layers 4 and 5 work **100% offline** with no external APIs!

---

## 7. Cost Breakdown

### Scenario A: Minimum Setup (Mock Data)

**Required**:
- OpenAI API: ~$0.01 per investigation
- Server hosting: ~$50-100/month

**Monthly cost for 1,000 investigations**: ~$60-110

---

### Scenario B: Recommended Setup (No LexisNexis)

**Required**:
- OpenAI API: ~$0.01 per investigation
- Google Maps: ~$0.007 per investigation
- Server hosting: ~$50-100/month

**Optional (Free Tiers)**:
- HIBP (breach data): Free
- NumVerify (phone): 250/month free
- SEC Edgar (corporate): Free

**Monthly cost for 1,000 investigations**: ~$67-117

---

### Scenario C: Full Enterprise (With LexisNexis)

**Required**:
- OpenAI API: ~$0.01 per investigation
- Google Maps: ~$0.007 per investigation
- LexisNexis: ~$50,000/year minimum
- Server hosting: ~$200/month (production)

**Monthly cost for 1,000 investigations**: ~$4,384

**LexisNexis only makes sense if**:
- Processing 10,000+ cases/month
- Government contract requires it
- Need legally defensible identity verification

---

## 8. Alternative Identity Providers

If you have access to other identity verification services:

### Supported Integrations

```bash
# Experian (alternative to LexisNexis)
IDENTITY_PROVIDER=experian
EXPERIAN_API_KEY=...
EXPERIAN_ENDPOINT=...

# TransUnion TLOxp
IDENTITY_PROVIDER=transunion
TRANSUNION_API_KEY=...

# Melissa Data (cheaper alternative)
IDENTITY_PROVIDER=melissa
MELISSA_API_KEY=...

# Custom REST API
IDENTITY_PROVIDER=custom
CUSTOM_API_ENDPOINT=https://your-service/api
CUSTOM_API_KEY=...
```

Contact support to add custom provider integrations.

---

## 9. Recommended Setup for Different Clients

### State/Local Government (Budget-Conscious)

```bash
# Use free alternatives
GOOGLE_MAPS_API_KEY=<your-key>  # $7 per 1000 investigations
SEC_EDGAR_ENABLED=true  # Free
PHONE_VERIFICATION_PROVIDER=pattern  # Free
EMAIL_VERIFICATION_PROVIDER=hibp  # Free
DMF_SOURCE=direct  # One-time $50 or free mirror
```

**Total cost**: ~$60-70/month for 1,000 investigations

---

### Federal Agency (GovCloud)

```bash
# Use LexisNexis if contract exists
ENABLE_LEXISNEXIS=true
LEXISNEXIS_API_KEY=<your-key>
GOOGLE_MAPS_API_KEY=<your-key>
OPENCORPORATES_API_KEY=<your-key>
```

**Total cost**: ~$4,200-4,400/month (LexisNexis contract)

---

### Private Sector / Auditors

```bash
# Use cheap alternatives
GOOGLE_MAPS_API_KEY=<your-key>
TWILIO_ACCOUNT_SID=<your-sid>  # $0.005/lookup
EMAILREP_API_KEY=<your-key>  # Free tier
OPENCORPORATES_API_KEY=<your-key>  # $250/month
DMF_SOURCE=direct
```

**Total cost**: ~$320/month for 1,000 investigations

---

## 10. Testing Your Configuration

### Verify Each Layer

```bash
# Layer 1: Physical
curl -X POST http://localhost:8000/api/v1/debug/test-tool \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{"tool": "street_view_vision", "address": "123 Main St"}'

# Layer 2: Corporate
curl -X POST http://localhost:8000/api/v1/debug/test-tool \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{"tool": "registry_status", "company": "Test LLC"}'

# Layer 3: Identity
curl -X POST http://localhost:8000/api/v1/debug/test-tool \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{"tool": "phone_carrier", "phone": "555-0100"}'

# Layer 4: Forensics
curl -X POST http://localhost:8000/api/v1/debug/test-tool \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -F "tool=advanced_forensics" \
  -F "file=@test_document.pdf"

# Layer 5: Intelligence
curl -X POST http://localhost:8000/api/v1/debug/test-tool \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{"tool": "graph_network", "phone": "555-0100"}'
```

Each should return tool-specific output (mock or real data depending on config).

---

## Summary

**Bottom Line**: You can run Veritas with **ZERO** third-party data vendors by:

1. Using OpenAI API ($0.01/case)
2. Enabling free SEC Edgar for corporate data
3. Using pattern matching for phone verification
4. Using HIBP for email/breach checks (free)
5. Downloading SSA Death Master File (one-time $50 or free)

**Layers 4 and 5 work completely offline** with no external dependencies—these are your most powerful fraud detection tools and require no external APIs.

LexisNexis is **completely optional** and only recommended for high-volume federal contracts where it's already contracted.
