#!/bin/bash
# ============================================================
# Docker WSL2 Smoke Test Script
# ============================================================
# Comprehensive verification of Docker + GPU setup in WSL2
# ============================================================

echo "Starting Docker Smoke Test inside WSL..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

FAILED=0
GPU_FAILED=0

# Test 1: Docker Installation
if command -v docker &> /dev/null; then
    print_pass "Docker is installed: $(docker --version)"
else
    print_fail "Docker is not installed"
    FAILED=1
fi

# Test 2: Docker Daemon Running
if docker ps > /dev/null 2>&1; then
    print_pass "Docker daemon is running and accessible."
else
    print_fail "Docker daemon is not accessible."
    FAILED=1
fi

# Test 3: NVIDIA GPU Support
echo "Checking for NVIDIA GPU support..."
if command -v nvidia-smi &> /dev/null; then
    print_pass "nvidia-smi is available inside WSL."
    nvidia-smi --query-gpu=index,name,uuid --format=csv,noheader | while IFS=, read -r idx name uuid; do
        echo "GPU $idx: $name (UUID: $uuid)"
    done
else
    print_fail "nvidia-smi is not available."
    print_warn "NVIDIA drivers may not be installed or WSL GPU support is disabled."
    FAILED=1
fi

# Test 4: NVIDIA Container Toolkit
echo "Verifying NVIDIA Container Toolkit integration..."
if command -v nvidia-ctk &> /dev/null; then
    print_pass "NVIDIA Container Toolkit is installed."
    nvidia-ctk --version
else
    print_warn "NVIDIA Container Toolkit is NOT installed."
    print_info "Run: ./scripts/install_nvidia_docker.sh to install it."
    GPU_FAILED=1
fi

# Test 5: Docker GPU Flag Support
if docker run --help 2>&1 | grep -q '\-\-gpus'; then
    print_pass "Docker supports --gpus flag."
else
    print_fail "Docker does not support --gpus flag."
    GPU_FAILED=1
fi

# Test 6: Docker Daemon GPU Configuration
if [ -f /etc/docker/daemon.json ]; then
    if grep -q "nvidia" /etc/docker/daemon.json; then
        print_pass "Docker daemon has NVIDIA runtime configured."
        print_info "Current daemon.json:"
        cat /etc/docker/daemon.json
    else
        print_warn "Docker daemon.json exists but NVIDIA runtime not configured."
        print_info "Run: sudo nvidia-ctk runtime configure --runtime=docker"
        GPU_FAILED=1
    fi
else
    print_warn "No /etc/docker/daemon.json found."
    GPU_FAILED=1
fi

# Test 7: Basic Container Test
echo "Running hello-world container..."
if docker run --rm hello-world > /dev/null 2>&1; then
    print_pass "Successfully ran hello-world container."
else
    print_fail "Could not run hello-world container."
    FAILED=1
fi

# Test 8: GPU Access in Container
echo "Testing GPU access inside a container..."
if docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi 2>&1 | grep -q "NVIDIA-SMI"; then
    print_pass "GPU is accessible from within a container!"
    docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
else
    print_fail "Could not access GPU from within a container."
    GPU_FAILED=1
    
    echo ""
    print_info "Diagnostic output:"
    docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi 2>&1 || true
    
    echo ""
    print_warn "This usually means NVIDIA Container Toolkit is not correctly configured for Docker."
    print_info "To fix this issue, run: ./scripts/fix_nvidia_docker.sh"
fi

echo ""
echo "============================================================"
echo " Smoke Test Results"
echo "============================================================"

if [ $FAILED -eq 0 ]; then
    if [ $GPU_FAILED -eq 0 ]; then
        print_pass "All tests passed! Docker + GPU environment is fully functional."
        echo ""
        echo "[SUCCESS] Your environment is ready for Docker-based Vexlum with GPU acceleration!"
    else
        print_warn "Docker works, but GPU acceleration is not available."
        echo ""
        echo "To enable GPU support:"
        echo "  1. Run: ./scripts/fix_nvidia_docker.sh"
        echo "  2. Or manually: ./scripts/install_nvidia_docker.sh"
        echo ""
        echo "[PARTIAL SUCCESS] Docker is ready, but GPU support needs configuration."
    fi
else
    print_fail "Critical tests failed. Docker environment is not ready."
    echo ""
    echo "Please review the errors above and:"
    echo "  1. Ensure Docker is installed: ./scripts/install_docker_wsl.sh"
    echo "  2. Run post-install setup: ./scripts/setup_docker_postinstall.sh"
    echo "  3. Restart WSL: wsl --shutdown (from Windows PowerShell)"
    exit 1
fi
