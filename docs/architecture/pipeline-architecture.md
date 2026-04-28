# Pipeline Architecture

Pipeline flow, worker sequence, and Electron integration for the Vexlum Scoring Scoring application.

## Overview

The pipeline processes images through five phases: **Indexing**, **Metadata**, **Scoring**, **Culling**, and **Keywords**. Indexing and Metadata run inside the Scoring flow (no dedicated runners). Run All Pending invokes the orchestrator, which runs Scoring, Culling, and Keywords in sequence.

## Sequence: Run All Pending Flow

```mermaid
sequenceDiagram
    participant User
    participant GradioUI
    participant Orchestrator
    participant ScoringRunner
    participant Engine
    participant PrepWorker
    participant ScoringWorker
    participant ResultWorker
    participant DB

    User->>GradioUI: Click Run All Pending
    GradioUI->>Orchestrator: start(folder_path)
    Orchestrator->>Orchestrator: get_folder_phase_summary
    Orchestrator->>Orchestrator: Build phase plan (scoring, culling, keywords)
    Orchestrator->>ScoringRunner: start_batch(folder_path, job_id)
    ScoringRunner->>Engine: process_directory
    Engine->>PrepWorker: ImageJob (per file)
    PrepWorker->>PrepWorker: INDEXING, METADATA, RAW convert
    PrepWorker->>ScoringWorker: job
    ScoringWorker->>ScoringWorker: ML inference
    ScoringWorker->>ResultWorker: job
    ResultWorker->>ResultWorker: write XMP/embedded metadata
    ResultWorker->>DB: upsert_image, set_image_phase_status
    ResultWorker->>GradioUI: progress_callback (log)
    GradioUI->>User: Update stepper, console
```

## Flowchart: Per-File Pipeline

```mermaid
flowchart TD
    Start[Image file] --> Prep[PrepWorker]
    Prep --> Index{target_phases has INDEXING?}
    Index -->|Yes| SetIndex[Set INDEXING DONE]
    Index -->|No/Empty| Meta
    SetIndex --> Meta
    Prep --> Meta{target_phases has METADATA?}
    Meta -->|Yes| ExifMeta[EXIF/UUID/Thumbnail]
    Meta -->|No/Empty| ScorePrep
    ExifMeta --> SetMeta[Set METADATA DONE]
    SetMeta --> ScorePrep[SCORING prep RAW convert]
    ScorePrep --> Score[ScoringWorker ML]
    Score --> Result[ResultWorker]
    Result --> WriteMeta[Write XMP + embedded]
    WriteMeta --> Upsert[DB upsert]
    Upsert --> SetScore[Set SCORING DONE]
    SetScore --> SetMeta2[Set METADATA DONE]
    SetMeta2 --> End[Next file]
```

## Electron + Gradio Integration

```mermaid
flowchart LR
    subgraph Electron [Electron App]
        WebView[WebView]
        IPC[IPC Handlers]
    end
    subgraph Backend [Python Backend]
        Gradio[Gradio UI :7860]
        FastAPI[FastAPI]
        MCP[MCP SSE]
    end
    subgraph Data [Data Layer]
        Firebird[(SCORING_HISTORY.FDB)]
    end

    WebView -->|HTTP| Gradio
    WebView -->|HTTP| FastAPI
    IPC --> Firebird
    Gradio --> Firebird
    FastAPI --> Firebird
    MCP --> Gradio
```

## Key Integration Points

| Component | Role |
|-----------|------|
| **Electron WebView** | Loads Gradio UI at `/app`, REST API at `:7860` |
| **IPC** | Electron main process queries Firebird directly via `electron/db.ts` |
| **Gradio** | Pipeline tab, progress stepper, Run All Pending / Stop All |
| **Orchestrator** | Builds phase plan from `get_folder_phase_summary`, runs Scoring → Culling → Keywords |
| **Shared DB** | `SCORING_HISTORY.FDB` (Firebird) — schema owned by Python `modules/db.py` |

## Related Documentation

- [PIPELINE_PHASE_RUNNERS.md](PIPELINE_PHASE_RUNNERS.md) — Phase-by-phase execution flow
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture overview
- [API_CONTRACT.md](API_CONTRACT.md) — REST API endpoints
