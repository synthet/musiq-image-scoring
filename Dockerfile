# syntax=docker/dockerfile:1
# BuildKit cache mounts reuse downloaded .debs and pip wheels across builds (no --no-cache).
FROM nvidia/cuda:12.6.0-cudnn-runtime-ubuntu22.04

# Set non-interactive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Set Python specific environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCKER_CONTAINER=1

# Firebird Linux client library path (bundled in repo under FirebirdLinux/)
ENV LD_LIBRARY_PATH=/app/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib:$LD_LIBRARY_PATH

# Install system dependencies (incl. Python 3.11)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    libimage-exiftool-perl \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 from deadsnakes PPA (Ubuntu 22.04 default is 3.10)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

# Install pip for Python 3.11 and make python/python3 point to it
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer cache (only reruns pip when this file changes)
COPY requirements/requirements_wsl_gpu.txt /tmp/requirements.txt
# Pip uses BuildKit cache mount so wheels stay on the daemon between builds even if this step reruns
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip \
    && python3 -m pip install -r /tmp/requirements.txt

# Copy source code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x scripts/docker_entrypoint.sh

# Expose WebUI port
EXPOSE 7860

# Use the entrypoint script
ENTRYPOINT ["/bin/bash", "scripts/docker_entrypoint.sh"]

# Default command
CMD []
