#!/bin/bash

# MSXplain Docker Management Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Function to check if OHIF image exists
check_ohif_image() {
    if ! docker image inspect ohif-viewer > /dev/null 2>&1; then
        print_warning "OHIF viewer image 'ohif-viewer' not found."
        print_status "Building OHIF viewer image..."
        cd ohif-orthanc/Viewers
        docker build -t ohif-viewer .
        cd ../..
    fi
}

# Function to build services
build_services() {
    print_status "Building Docker services..."
    docker-compose build --no-cache
    print_success "Services built successfully!"
}

# Function to start services
start_services() {
    print_status "Starting MSXplain services..."
    docker-compose up -d
    
    print_status "Waiting for services to be ready..."
    sleep 10
    
    print_success "Services started successfully!"
    print_status "Service URLs:"
    echo "  Frontend:     http://localhost:3001"
    echo "  Backend API:  http://localhost:8000"
    echo "  OHIF Viewer:  http://localhost:3000"
    echo "  Orthanc:      http://localhost:8042"
}

# Function to stop services
stop_services() {
    print_status "Stopping MSXplain services..."
    docker-compose down
    print_success "Services stopped successfully!"
}

# Function to show service status
status_services() {
    print_status "Service status:"
    docker-compose ps
}

# Function to show logs
show_logs() {
    service=${1:-""}
    if [ -z "$service" ]; then
        docker-compose logs -f
    else
        docker-compose logs -f "$service"
    fi
}

# Function to clean up
cleanup() {
    print_status "Cleaning up Docker resources..."
    docker-compose down -v
    docker system prune -f
    print_success "Cleanup completed!"
}

# Main menu
show_help() {
    echo "MSXplain Docker Management Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  build     Build all Docker services"
    echo "  start     Start all services"
    echo "  stop      Stop all services"
    echo "  restart   Restart all services"
    echo "  status    Show service status"
    echo "  logs      Show logs (optionally for specific service)"
    echo "  cleanup   Stop services and clean up volumes"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build"
    echo "  $0 start"
    echo "  $0 logs backend"
    echo "  $0 logs frontend"
}

# Check if Docker is available
check_docker

# Parse command line arguments
case "${1:-help}" in
    build)
        check_ohif_image
        build_services
        ;;
    start)
        check_ohif_image
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        print_status "Restarting services..."
        stop_services
        start_services
        ;;
    status)
        status_services
        ;;
    logs)
        show_logs "$2"
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
