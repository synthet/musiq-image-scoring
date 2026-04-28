# Technical summary: Vexlum

## 1. Project Overview
**MUSIQ (Multi-scale Image Quality Transformer)** is a comprehensive image analysis tool that combines technical quality assessment (sharpness, noise, artifacts) with aesthetic scoring. It provides both a Command Line Interface (CLI) for batch processing and a Gradio-based WebUI for digital asset management.

## 2. High-Level Architecture
The system operates as a hybrid application bridging a Windows host and a WSL 2 environment. This split is not merely a workaround but a strategic necessity, as TensorFlow dropped native GPU support on Windows after version 2.10.

### Architecture Diagram
```mermaid
graph TD
    User[User] --> WebUI[Gradio WebUI (Windows/WSL)]
    User --> CLI[CLI Scripts]
    
    subgraph "Windows Native (UX Layer)"
        WebUI
        FB_Service[Firebird Server Service]
    end

    subgraph "WSL 2 (Compute Layer)"
        Worker[ML Worker / Batch Scripts]
        TF_GPU[TensorFlow 2.20 + CUDA 12]
        Worker --> TF_GPU
        Worker -->|TCP Loopback| FB_Service
    end
    
    WebUI -->|Spawns| Worker
    WebUI -->|TCP Loopback| FB_Service
```

## 3. Technology Stack

### Core
*   **Language**: Python 3.x
*   **Web Framework**: Gradio (v5.x)
*   **Orchestration**: Custom Python scripts (`launch.py`, `batch_process_images.py`)

### Machine Learning
The project utilizes a dual-framework approach forced by platform support:

*   **TensorFlow (v2.15/v2.20)**:
    *   **Windows**: Uses `tensorflow-cpu==2.15.0`. **CPU-Only**. Native GPU support is unavailable for modern TF versions on Windows.
    *   **WSL 2**: Uses `tensorflow==2.20.0`. **GPU-Accelerated**. Leverages NVIDIA CUDA 12.x for ~10-15x performance gains.
    *   **DirectML**: Considered but avoided due to variable ops coverage and stability concerns compared to native CUDA in WSL.
*   **PyTorch**: Used for LIQE and Keyword Extraction (BLIP+CLIP).
    *   Running in subprocesses allows isolation from TensorFlow dependency conflicts.

### Database
*   **System**: Firebird SQL (v5.x).
*   **Connectivity**: Critical configuration to avoid file locking mechanism ("lck") issues.
    *   **Protocol**: TCP (`inet://...`) is mandatory when accessing from WSL.
    *   **Address**: `inet://<host_ip>:3050/<windows_path_to_db>`.
    *   **Strategy**: Windows runs the Firebird service; WSL acts as a remote client.

## 4. Environment & Deployment Strategy

### Recommended Architecture: Hybrid (Option A)
*   **Windows**: Hosts the WebUI (Gradio) for a responsive, native "clicky" experience and easier file management.
*   **WSL 2**: Acts as a high-performance "ML Worker" service.
*   **Why**: Best balance of User Experience (Windows) and Raw Performance (Linux/CUDA).

### Alternative: Docker Desktop (Option B)
*   **Setup**: Containers for `webui` running on top of the WSL 2 backend.
*   **Pros**: High reproducibility, prevents "works on my machine" issues.
*   **Cons**: Higher complexity (volumes, ports), slower I/O if crossing filesystems excessively.
*   **Role**: Docker on Windows *relies* on WSL 2 anyway for Linux containers/GPU-PV.

### Docker Runner (Option C) - NEW
*   **Launch**: Run `run_webui_docker.bat`.
*   **Architecture**: Docker container with CUDA 12.6, connects to host Firebird via `host.docker.internal`.
*   **Ideal for**: Users who want a clean environment without manual WSL/Python setup.

### Environment Specifications

#### A. Windows (Native)
*   **Primary Use**: Interactive WebUI, Asset Management.
*   **Dependencies**: `tensorflow-cpu`, `firebird-driver`, `Pillow`.
*   **Limitation**: No VILA model support; slow batch scoring.

#### B. WSL 2 (Production/Batch)
*   **Primary Use**: High-volume Batch Processing, Full Model Support.
*   **Dependencies**:
    *   **CUDA Stack**: `nvidia-cuda-runtime-cu12`, `nvidia-cudnn-cu12`, `nvidia-cublas-cu12`.
    *   **System Libs**: `libgl1`, `libsm6`.
*   **Integration**:
    *   **Workspace**: Code should live in WSL (`~/src/`) for performance.
    *   **Files**: Access Windows data via `/mnt/[drive]/`.

## 5. Key Modules
*   **`modules/db.py`**: Handles database connections, complex cross-platform networking (WSL->Windows), and schema migrations.
*   **`modules/pipeline.py`** & **`modules/scoring.py`**: Orchestrates the multi-model scoring process.
*   **`launch.py`**: Bootstrapper that ensures dependencies are met and the Firebird database server is running before starting the app.

## 6. Data Flow & Security
1.  **Ingestion**: Images read from NTFS drives.
2.  **Processing**: 
    *   If Windows: CPU inference (Slow, Safe).
    *   If WSL: UDP/TCP bridge to Windows Firebird; GPU inference (Fast).
3.  **Storage**: Firebird DB stores paths and scores. 
    *   *Critical*: Do not open `.fdb` files directly from WSL; database corruption will occur due to locking protocol mismatch. Always use TCP.

## Related Documents

- [Docs index](../README.md)
- [Project structure](PROJECT_STRUCTURE.md)
- [WSL tests](../testing/WSL_TESTS.md)
- [Docker setup](../guides/setup/DOCKER_SETUP.md)
- [Weighted scoring strategy](WEIGHTED_SCORING_STRATEGY.md)
- [Model weights](../reference/models/MODEL_WEIGHTS.md)

