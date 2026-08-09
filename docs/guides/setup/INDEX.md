---
type: Documentation Index
title: "Setup & Deployment — Index"
description: "Routes setup guides: Docker and gpu-shell, host topology, GPU, Postgres, agent/IDE, and Windows/WSL deployment."
resource: guides/setup/INDEX.md
tags: [setup, docker, wsl, gpu, index]
timestamp: 2026-08-09T16:10:00Z
okf_version: 0.1
---

# Setup & Deployment — Index

## Docker

| Document | Description |
|----------|-------------|
| [wsl-vs-docker-topology.md](wsl-vs-docker-topology.md) | Ubuntu vs docker-desktop: what runs where, Docker-only limits, shutdown safety, photo binds |
| [DOCKER_SETUP.md](DOCKER_SETUP.md) | Docker installation (WSL2) + Compose Postgres/WebUI + gpu-shell |

## Agent / IDE

| Document | Description |
|----------|-------------|
| [mcp-compact-servers.md](mcp-compact-servers.md) | Unified Node MCP setup (is-be-mcp / is-ui-mcp), sse_status, multi-root Cursor |
| [agent-cull-review-gemini-cli.md](agent-cull-review-gemini-cli.md) | Gemini CLI + Docker/WSL paths for agent-assisted cull review |

## GPU & CUDA

| Document | Description |
|----------|-------------|
| [GPU_SETUP.md](GPU_SETUP.md) | GPU setup guide (merged) |
| [INSTALL_CUDA.md](INSTALL_CUDA.md) | CUDA installation (RTX 4060) |
| [WSL2_TENSORFLOW_GPU_SETUP.md](WSL2_TENSORFLOW_GPU_SETUP.md) | TensorFlow GPU in WSL2 |

## WSL Environment

| Document | Description |
|----------|-------------|
| [PYTHON_VERSION_CAVEATS.md](PYTHON_VERSION_CAVEATS.md) | Canonical requirements files by platform + Python compatibility caveats |
| [ENVIRONMENTS.md](ENVIRONMENTS.md) | Virtual environments (.venv, ~/.venvs/tf, tests) |
| [WINDOWS_WSL_DEPLOYMENT.md](WINDOWS_WSL_DEPLOYMENT.md) | Windows + WSL2 deployment guide |
| [WSL_PYTHON_PACKAGES.md](WSL_PYTHON_PACKAGES.md) | Python packages in WSL2 venv |
| [WSL_UBUNTU_PACKAGES.md](WSL_UBUNTU_PACKAGES.md) | Ubuntu packages in WSL2 |
| [WSL_WRAPPER_VERIFICATION.md](WSL_WRAPPER_VERIFICATION.md) | WSL wrapper script verification |

## Windows Scripts

| Document | Description |
|----------|-------------|
| [WINDOWS_SCRIPTS_README.md](WINDOWS_SCRIPTS_README.md) | Windows batch/PS scripts for GPU runner |

*Plan:* [Windows native WebUI](../../planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md)

**See also:** [Main docs index](../../INDEX.md) · [Guides index](../INDEX.md)
