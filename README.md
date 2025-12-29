# Veritas - Government Fraud Orchestrator (GFO)

A secure, containerized web application for government fraud detection using AI-powered agent orchestration.

**📖 Documentation**:
- **[Investigator's Guide](INVESTIGATOR_GUIDE.md)** - Practical usage guide for analysts
- **[Toolset Documentation](TOOLSET_DOCUMENTATION.md)** - Technical tool specifications (Layers 1-4)
- **[Cross-Case Intelligence](CROSS_CASE_INTELLIGENCE.md)** - Layer 5 fraud ring detection
- **[Advanced Forensics](ADVANCED_FORENSICS.md)** - Layer 4 enhanced document forgery detection
- **[Setup Guide](SETUP.md)** - Detailed deployment instructions

## Architecture

- **Frontend**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, Shadcn/UI
- **Backend**: Python 3.11+, FastAPI
- **Agent Framework**: LangGraph for stateful agent workflows
- **Database**: PostgreSQL 16
- **Queue**: Redis
- **LLM Interface**: LiteLLM (proxy for Azure OpenAI, Anthropic, etc.)

## Project Structure

```
veritas/
├── backend/           # FastAPI backend service
├── frontend/          # Next.js frontend application
├── docker-compose.yml # Development environment
└── README.md
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Development Setup

1. Clone the repository
2. Copy environment files:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env.example.local
   ```

3. Configure API keys in `backend/.env`:
   - `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
   - `GOOGLE_MAPS_API_KEY`
   - `OPENCORPORATES_API_KEY`
   - `LEXISNEXIS_API_KEY` (optional, will use mock data)

4. Start services:
   ```bash
   docker-compose up -d
   ```

5. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Security Notes

- **GovCloud Compliant**: Designed for AWS GovCloud and air-gapped deployments
- **No Data Training**: LLM calls configured with temperature=0 and no-logging headers
- **API Authentication**: All endpoints require `X-AGENCY-TOKEN` header
- **Audit Trail**: All actions logged to `audit_logs` table

## 5-Layer Investigation Framework

Veritas employs a comprehensive multi-layer approach to fraud detection:

### Layer 1: Physical Verification
- **StreetViewVisionTool**: Visual confirmation via Google Street View + GPT-4 Vision
- **PropertyOwnerTool**: Detect undisclosed related-party transactions

### Layer 2: Corporate Verification
- **RegistryStatusTool**: Verify business legal standing and formation date
- **DomainForensicsTool**: Identify "pop-up" websites (< 30 days old)
- **WebContentScraperTool**: Analyze website content for Lorem Ipsum and fake staff bios

### Layer 3: Digital Identity
- **PhoneCarrierTool**: Detect burner phones (VOIP vs legitimate carriers)
- **EmailDigitalFootprintTool**: Synthetic identity detection via social presence
- **BreachHistoryTool**: Counter-intuitive breach analysis (0 breaches = suspicious)

### Layer 4: Document Forensics (Kill Switch)
- **PDFMetadataTool**: Detect basic document manipulation flags
- **Advanced Forensics Pipeline**:
  - **Error Level Analysis (ELA)**: JPEG compression inconsistencies
  - **Noise Pattern Analysis (PRNU)**: Camera sensor fingerprinting
  - **Clone Detection**: Copy-move forgery using SIFT
  - **PDF Incremental Updates**: Hidden edit history detection
  - **Font & Glyph Analysis**: Font collision and kerning analysis

### Layer 5: Cross-Case Intelligence (Fraud Ring Detection)
- **VectorSimilarityTool**: Plagiarism detection using ChromaDB embeddings
- **JobBoardScraperTool**: Verify growth claims via Indeed/LinkedIn
- **EmployeeGhostCheckTool**: Cross-reference against Death Master File
- **GraphNetworkTool**: Detect fraud rings via Neo4j graph analysis

See [TOOLSET_DOCUMENTATION.md](TOOLSET_DOCUMENTATION.md), [ADVANCED_FORENSICS.md](ADVANCED_FORENSICS.md), and [CROSS_CASE_INTELLIGENCE.md](CROSS_CASE_INTELLIGENCE.md) for detailed specifications.

## Risk Matrix Scoring

Risk scores are calculated using weighted factors across all layers:

- **Layer 1 (Physical)**: Up to 40 points
  - Residential property for commercial business: +25 pts
  - Related party property ownership: +15 pts

- **Layer 2 (Corporate)**: Up to 50 points
  - Domain age < 30 days: +30 pts
  - Company formation < 30 days: +20 pts

- **Layer 3 (Identity)**: Up to 25 points
  - VOIP phone number: +10 pts
  - No social media presence: +15 pts

- **Layer 4 (Forensics)**: KILL SWITCH + Advanced Analysis
  - Basic manipulation detected: Immediate score of 100
  - Advanced forensics (80%+ confidence): Immediate score of 100
  - Advanced forensics (50-79% confidence): +40 pts

- **Layer 5 (Intelligence)**: Up to 140 points
  - Fraud ring detected: +50 pts
  - Plagiarized narrative (>85% similarity): +40 pts
  - Employee verification rate < 70%: +30 pts
  - No hiring activity despite growth claims: +20 pts

**Risk Levels**:
- 80-100: CRITICAL → **DENY**
- 70-79: HIGH → **DENY**
- 40-69: MEDIUM → **FURTHER REVIEW**
- 0-39: LOW → **APPROVE**

## Development Status

1. ✅ Foundation: Project structure and Docker setup
2. ✅ Data Layer: PostgreSQL schema and models
3. ✅ Agent Tools: 13-tool investigative framework across 5 layers
4. ✅ Advanced Forensics: ELA, PRNU, Clone Detection, PDF Analysis, Font Analysis
5. ✅ Cross-Case Intelligence: Vector DB (ChromaDB), Graph DB (Neo4j)
6. ✅ Orchestrator: LangGraph-based investigation with enhanced risk matrix
7. ✅ API Layer: FastAPI endpoints with background processing
8. ✅ Frontend: Case management dashboard with evidence visualization
9. ✅ Landing Page: Modern waitlist page for state government outreach

## License

Proprietary - Government Use Only
