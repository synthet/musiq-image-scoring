#!/usr/bin/env bash
set -e

# Docker smoke test for Vexlum environment
# Checks for Docker, GPU support, and container connectivity

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Docker Smoke Test inside WSL...${NC}"

# 1. Check if Docker is installed
if command -v docker >/dev/null 2>&1; then
    echo -e "${GREEN}[PASS] Docker is installed: $(docker --version)${NC}"
else
    echo -e "${RED}[FAIL] Docker is not installed or not in PATH.${NC}"
    exit 1
fi

# 2. Check if Docker daemon is running
if docker info >/dev/null 2>&1; then
    echo -e "${GREEN}[PASS] Docker daemon is running and accessible.${NC}"
else
    echo -e "${RED}[FAIL] Docker daemon is not running or current user does not have permissions.${NC}"
    echo -e "${YELLOW}Tip: Ensure Docker Desktop is running and WSL integration is enabled for this distribution.${NC}"
    exit 1
fi

# 3. Check for NVIDIA GPU support in WSL
echo -e "${YELLOW}Checking for NVIDIA GPU support...${NC}"
if command -v nvidia-smi >/dev/null 2>&1; then
    echo -e "${GREEN}[PASS] nvidia-smi is available inside WSL.${NC}"
    nvidia-smi -L
else
    echo -e "${YELLOW}[WARN] nvidia-smi not found. GPU acceleration might not be available.${NC}"
fi

# 4. Check NVIDIA Container Toolkit
echo -e "${YELLOW}Verifying NVIDIA Container Toolkit integration...${NC}"
if docker run --help | grep -q "\-\-gpus" ; then
    echo -e "${GREEN}[PASS] Docker supports --gpus flag.${NC}"
else
    echo -e "${RED}[FAIL] Docker does not seem to support --gpus flag. check NVIDIA Container Toolkit installation.${NC}"
fi

# 5. Run a hello-world container
echo -e "${YELLOW}Running hello-world container...${NC}"
if docker run --rm hello-world >/dev/null 2>&1; then
    echo -e "${GREEN}[PASS] Successfully ran hello-world container.${NC}"
else
    echo -e "${RED}[FAIL] Failed to run hello-world container.${NC}"
    exit 1
fi

# 6. Check GPU container support (optional but recommended)
if command -v nvidia-smi >/dev/null 2>&1; then
    echo -e "${YELLOW}Testing GPU access inside a container...${NC}"
    if docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
        echo -e "${GREEN}[PASS] Successfully accessed GPU from within a container.${NC}"
    else
        echo -e "${RED}[FAIL] Could not access GPU from within a container.${NC}"
        echo -e "${YELLOW}This usually means NVIDIA Container Toolkit is not correctly configured for Docker.${NC}"
    fi
fi

echo -e "\n${GREEN}Docker Smoke Test Completed Successfully!${NC}"
