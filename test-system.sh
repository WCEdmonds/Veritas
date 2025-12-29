#!/bin/bash
# Quick test script to verify the Veritas GFO system

echo "========================================="
echo "Veritas GFO - System Test"
echo "========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✓ Docker is running"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys"
fi

echo "✓ Environment file exists"

# Start services
echo ""
echo "Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 10

# Check if backend is responding
echo ""
echo "Testing backend health..."
HEALTH=$(curl -s http://localhost:8000/health || echo "failed")
if [[ $HEALTH == *"healthy"* ]]; then
    echo "✓ Backend is healthy"
else
    echo "❌ Backend is not responding"
    docker-compose logs backend
    exit 1
fi

# Test case ingestion
echo ""
echo "Testing case ingestion..."
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-AGENCY-TOKEN: dev-token-12345" \
  -d '{
    "external_ref_id": "TEST-'$(date +%s)'",
    "applicant_name": "QuickStart Solutions LLC",
    "applicant_tax_id": "98-7654321",
    "applicant_address": "123 Smith Street, Austin, TX 78701"
  }')

if [[ $RESPONSE == *"id"* ]]; then
    echo "✓ Case ingestion successful"
    CASE_ID=$(echo $RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)
    echo "  Case ID: $CASE_ID"
else
    echo "❌ Case ingestion failed"
    echo "Response: $RESPONSE"
    exit 1
fi

# Wait for investigation to complete
echo ""
echo "Waiting for investigation to complete (30 seconds)..."
sleep 30

# Check case status
echo ""
echo "Checking case status..."
STATUS=$(curl -s http://localhost:8000/api/v1/cases/$CASE_ID \
  -H "X-AGENCY-TOKEN: dev-token-12345")

if [[ $STATUS == *"final_risk_score"* ]]; then
    echo "✓ Investigation completed"
    RISK_SCORE=$(echo $STATUS | grep -o '"final_risk_score":[0-9]*' | cut -d':' -f2)
    echo "  Risk Score: $RISK_SCORE"
else
    echo "⚠️  Investigation may still be processing"
fi

echo ""
echo "========================================="
echo "System Test Complete!"
echo "========================================="
echo ""
echo "Access the application:"
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Test case ID: $CASE_ID"
echo ""
