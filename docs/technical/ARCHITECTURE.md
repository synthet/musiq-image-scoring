# Architecture Documentation

## Overview

The Image Scoring project is a sophisticated system designed to evaluate, tag, and organize large collections of images using deep learning models. It provides a multi-faceted interface including a Python-based backend, a Firebird database for metadata storage, an MCP (Model Context Protocol) server for external integration, and a Gradio-based WebUI for interaction.

## Core Components

### 1. Database Layer (`modules/db.py`)
The system uses **Firebird SQL** as its persistent storage engine. The `db.py` module abstracts all database interactions.
- **Connection Management**: Handles connections to the Firebird database, including support for WSL paths.
- **Schema Management**: Includes utilities for initializing and validating the database schema.
- **Data Access Objects**: Provides functions for CRUD operations on images, folders, stacks, and culling sessions.
- **State Management**: Tracks the processing status of folders (scoring, tagging, clustering).

### 2. Processing Pipeline (`modules/pipeline.py`)
Image processing is handled by a concurrent pipeline architecture to maximize throughput.
- **Stages**:
    - **Prep**: Loads and preprocesses images (handling various formats like NEF/RAW).
    - **Score**: Passes images through configured models (MUSIQ, Aesthetic, etc.).
    - **Result**: Aggregates scores and writes them to the database.
- **Workers**: Each stage runs in its own thread/process, communicating via queues.

### 3. Engine & Orchestration (`modules/engine.py`, `modules/scoring.py`)
- **Engine**: The high-level orchestrator that manages batch processing jobs. It coordinates the pipeline, handles stops/pauses, and reports progress.
- **Scoring**: Specifically handles the invocation of scoring models (e.g., MUSIQ).

### 4. Models (`musiq/`)
- The project implements the **MUSIQ** (Multi-scale Image Quality Transformer) model for assessing technical and aesthetic image quality.
- **TensorFlow/PyTorch**: The models uses TensorFlow (CPU optimized) and potentially PyTorch for other scorers.

### 5. MCP Server (`modules/mcp_server.py`)
The project exposes its capabilities via the **Model Context Protocol (MCP)**.
- **Tools**: Exposes database queries, job management, and system diagnostics to AI agents (like Cursor or Windsurf).
- **Resources**: Provides access to logs and configuration.

### 6. WebUI (`modules/ui/`)
A **Gradio**-based web interface allows users to interact with the system.
- **Tabs**: Organized by function (Gallery, Scoring, Tagging, Stacks, Culling).
- **State**: Manages user session state and interaction logic.

For how Gradio fits next to FastAPI and when a separate inference-serving stack would be warranted, see [GRADIO_SERVING_DECISION.md](../reports/GRADIO_SERVING_DECISION.md).

### 7. API (`modules/api.py`)
A **FastAPI** layer that exposes endpoints for the WebUI and potential external consumers, wrapping the underlying engine and runners.

### 8. Runs queue (`jobs` table, `JobDispatcher`)
Batch runs are queued in the database and drained by a background dispatcher after startup. **See [RUNS_QUEUE_AND_RESTART.md](RUNS_QUEUE_AND_RESTART.md)** for persistence, dequeue ordering, and what happens to `running` jobs when the WebUI restarts.

## Data Flow

1.  **Ingestion**: User selects a folder in the WebUI or triggers a job via MCP.
2.  **Scanning**: `db.py` scans the filesystem and registers images in the database.
3.  **Processing**: `engine.py` initializes the pipeline. Images flow from disk -> Prep -> Model -> Result -> Database.
4.  **Presentation**: The WebUI queries the database to display images, scores, and tags.

## Key Concepts

- **Stacks**: Groups of similar images (e.g., bursts) used for culling.
- **Culling**: The process of selecting the best images from a stack or folder.
- **Scoring**: Numerical evaluation of image quality (0-10 or similar scales).
- **Tagging**: Keyword extraction and classification.

## Deployment

- **Windows**: Native execution via batch scripts.
- **Docker**: Containerized deployment for isolation and reproducibility (see `docker-compose.yml`).
- **WSL**: Support for running the database or scoring engine in WSL for performance.
