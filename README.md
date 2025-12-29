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

## Development Phases

1. ✅ Foundation: Project structure and Docker setup
2. Data Layer: PostgreSQL schema and models
3. Agent Tools: API integrations (Google Maps, OpenCorporates, etc.)
4. Orchestrator: LangGraph-based investigation engine
5. API Layer: FastAPI endpoints
6. Frontend: Case management dashboard

## License

Proprietary - Government Use Only
