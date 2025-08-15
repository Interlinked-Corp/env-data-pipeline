#!/bin/bash
# Environmental Data Pipeline - Development Startup Script

echo "Starting Environmental Data Pipeline Development Environment"
echo "=============================================================="

# Check Docker availability
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Please install Docker Desktop."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "ERROR: Docker not running. Please start Docker Desktop."
    exit 1
fi

echo "SUCCESS: Docker is available and running"

# Set default environment variables if not already set
export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-"test"}
export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-"test"}
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-"us-west-2"}
export OPENWEATHER_API_KEY=${OPENWEATHER_API_KEY:-""}

echo "Environment configured:"
echo "   AWS Region: $AWS_DEFAULT_REGION"
echo "   Weather API: ${OPENWEATHER_API_KEY:+configured}"

# Build containers
echo ""
echo "Building containers..."
if docker compose build; then
    echo "SUCCESS: Container build successful"
else
    echo "ERROR: Container build failed. Check the output above."
    echo "TIP: Try installing dependencies: pip install -r requirements.txt"
    exit 1
fi

# Start the pipeline
echo ""
echo "Starting pipeline services..."
if docker compose up -d; then
    echo "SUCCESS: Pipeline services started"
    
    echo ""
    echo "Service URLs:"
    echo "   LANDFIRE Container:    http://localhost:8001/health"
    echo "   MODIS Container:       http://localhost:8002/health"
    echo "   Weather Container:     http://localhost:8003/health"
    echo "   Elevation Container:   http://localhost:8004/health"
    echo "   Container Orchestrator: http://localhost:8000/health"
    echo "   Redis Cache:           localhost:6379"
    echo "   RabbitMQ:              http://localhost:15672 (guest/guest)"
    
    echo ""
    echo "Check service status:"
    echo "   docker compose ps"
    echo "   docker compose logs [service-name]"
    
    echo ""
    echo "Stop services:"
    echo "   docker compose down"
    
else
    echo "ERROR: Failed to start pipeline services"
    exit 1
fi

echo ""
echo "Development environment ready!"