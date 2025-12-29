# Veritas - Government Fraud Orchestrator (GFO)

A secure, containerized web application for government fraud detection using AI-powered agent orchestration.

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

## 4-Layer Investigation Framework

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
- **PDFMetadataTool**: Detect Photoshop/Canva manipulation of financial documents

See [TOOLSET_DOCUMENTATION.md](TOOLSET_DOCUMENTATION.md) for detailed specifications.

## Risk Matrix Scoring

Risk scores are calculated using weighted factors across all layers:

- **Layer 1 (Physical)**: Up to 40 points
- **Layer 2 (Corporate)**: Up to 50 points
- **Layer 3 (Identity)**: Up to 25 points
- **Layer 4 (Forensics)**: KILL SWITCH - Immediate score of 100 if document manipulation detected

**Risk Levels**:
- 80-100: CRITICAL → **DENY**
- 70-79: HIGH → **DENY**
- 40-69: MEDIUM → **FURTHER REVIEW**
- 0-39: LOW → **APPROVE**

## Development Status

1. ✅ Foundation: Project structure and Docker setup
2. ✅ Data Layer: PostgreSQL schema and models
3. ✅ Agent Tools: 9-tool investigative framework across 4 layers
4. ✅ Orchestrator: LangGraph-based investigation with risk matrix
5. ✅ API Layer: FastAPI endpoints with background processing
6. ✅ Frontend: Case management dashboard with evidence visualization

## License

Proprietary - Government Use Only
