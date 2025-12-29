# Veritas GFO - Setup Guide

## Quick Start

1. **Clone and Configure**
   ```bash
   cd Veritas
   cp .env.example .env
   # Edit .env and add your API keys
   ```

2. **Start Services**
   ```bash
   docker-compose up -d
   ```

3. **Access Applications**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Detailed Setup

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- (Optional) Node.js 18+ for local frontend development
- (Optional) Python 3.11+ for local backend development

### Configuration

#### 1. API Keys

Edit `.env` file with your API keys:

```bash
# Required for LLM functionality
OPENAI_API_KEY=sk-your-key-here
# OR
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional (will use mock data if missing)
GOOGLE_MAPS_API_KEY=your-google-key
OPENCORPORATES_API_KEY=your-opencorporates-key
LEXISNEXIS_API_KEY=your-lexisnexis-key

# Security token for API access
AGENCY_TOKEN=your-secure-token-here
```

#### 2. Frontend Configuration

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_AGENCY_TOKEN=your-secure-token-here
```

### Running the Application

#### Using Docker (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

#### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### Testing the System

#### 1. Create a Test Case

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{
    "external_ref_id": "TEST-001",
    "applicant_name": "Acme Manufacturing LLC",
    "applicant_tax_id": "12-3456789",
    "applicant_address": "123 Main St, Suite 100, Springfield, IL 62701"
  }'
```

#### 2. Check Case Status

```bash
curl http://localhost:8000/api/v1/cases \
  -H "X-AGENCY-TOKEN: dev-token-12345"
```

#### 3. View in Dashboard

Open http://localhost:3000 and you should see the case appear.

### Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Next.js    │────▶│   FastAPI    │────▶│ PostgreSQL  │
│  Frontend   │     │   Backend    │     │  Database   │
│ (Port 3000) │     │ (Port 8000)  │     │ (Port 5432) │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    Redis     │
                    │ (Port 6379)  │
                    └──────────────┘
```

### API Workflow

1. **Ingest** (`POST /api/v1/ingest`): Create new case
2. **Background Processing**: Agent orchestrator runs investigation
3. **Status Updates**: Case status changes from NEW → PROCESSING → REVIEW_REQUIRED
4. **Human Review**: Analyst views case in dashboard
5. **Adjudication** (`POST /api/v1/cases/{id}/adjudicate`): APPROVE or DENY

### Agent Investigation Flow

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Planner │────▶│ Executor │────▶│ Analyzer │────▶│ Reporter │
└─────────┘     └──────────┘     └──────────┘     └──────────┘
     ▲                                  │
     └──────────────────────────────────┘
              (Loop if more data needed)
```

**Tools Used:**
- Google Street View: Verify business location
- OpenCorporates: Check company registration
- LexisNexis (Mock): Verify individual identity

### Security Features

- **API Authentication**: All endpoints require `X-AGENCY-TOKEN` header
- **Audit Logging**: All actions logged to `audit_logs` table
- **No Data Training**: LLM configured with `temperature=0` and no-logging headers
- **CORS**: Configured for localhost (update for production)

### Troubleshooting

**Database Connection Issues:**
```bash
docker-compose logs postgres
docker-compose restart postgres
```

**Backend Not Starting:**
```bash
docker-compose logs backend
# Check API keys in .env file
```

**Frontend Can't Connect:**
- Verify `NEXT_PUBLIC_API_URL` in frontend/.env.local
- Ensure backend is running on port 8000
- Check CORS settings in backend/app/main.py

**Investigation Not Running:**
- Verify LLM API key is set (OPENAI_API_KEY or ANTHROPIC_API_KEY)
- Check Redis is running: `docker-compose ps redis`
- View backend logs for errors

### Production Deployment

For production deployment:

1. **Update Environment Variables**
   - Use strong `AGENCY_TOKEN`
   - Configure production LLM endpoints
   - Set `ENVIRONMENT=production`

2. **Database**
   - Use managed PostgreSQL (RDS, Cloud SQL)
   - Enable SSL connections
   - Set up automated backups

3. **CORS**
   - Update `allow_origins` in backend/app/main.py
   - Use production frontend URL

4. **Kubernetes Deployment**
   - Use provided Helm charts (coming soon)
   - Configure secrets management
   - Set up monitoring and logging

### Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review API docs: http://localhost:8000/docs
- Inspect database: Use any PostgreSQL client with connection string from `.env`
