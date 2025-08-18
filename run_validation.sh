#!/bin/bash
# Comprehensive Pipeline Validation Script

echo "=========================================="
echo "Environmental Data Pipeline Validation"
echo "=========================================="
echo ""

# Check if containers are running
echo "1. Checking if containers are running..."
if docker compose ps | grep -q "Up"; then
    echo "✓ Containers are running"
else
    echo "✗ Containers not running. Starting them..."
    echo "Running: docker compose up -d"
    docker compose up -d
    echo "Waiting 30 seconds for containers to be ready..."
    sleep 30
fi

echo ""
echo "2. Running orchestrator and container health checks..."
# Test orchestrator health
if curl -s "http://localhost:8000/health" > /dev/null; then
    echo "✓ Orchestrator is healthy"
    
    # Check container status through orchestrator
    if curl -s "http://localhost:8000/containers/status" | grep -q "healthy"; then
        echo "✓ Containers are healthy through orchestrator"
    else
        echo "✗ Some containers are unhealthy"
    fi
else
    echo "✗ Orchestrator is not responding"
fi

echo ""
echo "3. Running basic integration tests..."
python tests/test_pipeline.py

echo ""
echo "4. Running comprehensive validation tests..."
echo "   (This tests real data retrieval, metadata accuracy, and data currency)"
python tests/test_comprehensive_validation.py

echo ""
echo "=========================================="
echo "Validation Complete"
echo "=========================================="