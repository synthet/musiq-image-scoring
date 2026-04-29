# API Schema for LLM Agents

This document provides a machine-readable schema description of the Vexlum Scoring Scoring WebUI REST API, optimized for LLM agent consumption.

## Quick Access

- **OpenAPI JSON Schema**: `http://127.0.0.1:7860/openapi.json`
- **Simplified Schema**: `http://127.0.0.1:7860/api/schema`
- **Interactive Docs**: `http://127.0.0.1:7860/docs` (Swagger UI)
- **Alternative Docs**: `http://127.0.0.1:7860/redoc` (ReDoc)

## Base URL

All API endpoints are prefixed with `/api`:
```
http://127.0.0.1:7860/api
```

## Authentication

Currently, no authentication is required. All endpoints are publicly accessible.

## Endpoint Categories

### Shared Selector Fields (batch start endpoints)
- `image_ids: number[]`
- `image_paths: string[]`
- `folder_ids: number[]`
- `folder_paths: string[]`
- `recursive: boolean` (default `true`)

Selectors can be mixed; overlaps are deduplicated and each image is processed once.


### 1. Scoring Operations

#### POST /api/scoring/start
Start a batch image scoring job.

**Request Body:**
```json
{
  "input_path": "string (optional when selectors are used)",
  "image_ids": "number[]",
  "image_paths": "string[]",
  "folder_ids": "number[]",
  "folder_paths": "string[]",
  "recursive": "boolean (default: true)",
  "skip_existing": "boolean (default: true) - Skip images with complete scores",
  "force_rescore": "boolean (default: false) - Force re-scoring of all images"
}
```

**Response:**
```json
{
  "success": "boolean",
  "message": "string",
  "data": {
    "job_id": "integer",
    "input_path": "string"
  }
}
```

**Status Codes:**
- 200: Job started successfully
- 400: Invalid path or path not found
- 503: Scoring runner not available

#### POST /api/scoring/stop
Stop the currently running scoring job.

**Response:**
```json
{
  "success": "boolean",
  "message": "string",
  "data": {
    "is_running": "boolean"
  }
}
```

#### GET /api/scoring/status
Get current scoring job status.

**Response:**
```json
{
  "is_running": "boolean",
  "status_message": "string",
  "progress": {
    "current": "integer",
    "total": "integer"
  },
  "log": "string",
  "job_type": "string | null (scoring, fix_db, or null)"
}
```

#### POST /api/scoring/fix-db
Start database fix operation (re-score incomplete records).

**Response:**
```json
{
  "success": "boolean",
  "message": "string",
  "data": {
    "job_id": "integer"
  }
}
```

#### POST /api/scoring/single
Score a single image (blocking operation).

**Request Body:**
```json
{
  "file_path": "string (required) - Full path to image file"
}
```

**Response:**
```json
{
  "success": "boolean",
  "message": "string",
  "data": {
    "file_path": "string"
  }
}
```

#### POST /api/scoring/fix-image
Fix metadata for a single image (recalculate from existing data, no AI models).

**Request Body:**
```json
{
  "file_path": "string (required)"
}
```

### 2. Tagging Operations

#### POST /api/tagging/start
Start a batch tagging job.

**Request Body:**
```json
{
  "input_path": "string (optional) - Directory path to scope tagging",
  "image_ids": "number[]",
  "image_paths": "string[]",
  "folder_ids": "number[]",
  "folder_paths": "string[]",
  "recursive": "boolean (default: true)",
  "custom_keywords": "array<string> | null - Custom keywords or null for defaults",
  "overwrite": "boolean (default: false) - Overwrite existing keywords",
  "generate_captions": "boolean (default: false) - Generate captions using BLIP"
}
```

**Response:**
```json
{
  "success": "boolean",
  "message": "string",
  "data": {
    "input_path": "string"
  }
}
```

#### POST /api/tagging/stop
Stop the currently running tagging job.

#### GET /api/tagging/status
Get current tagging job status (same format as scoring status).

#### POST /api/tagging/single
Tag a single image (blocking operation).

**Request Body:**
```json
{
  "file_path": "string (required)",
  "custom_keywords": "array<string> | null",
  "generate_captions": "boolean (default: true)"
}
```

### 3. General Operations

#### GET /api/status
Get status of all runners (scoring and tagging).

**Response:**
```json
{
  "scoring": {
    "available": "boolean",
    "is_running": "boolean",
    "status_message": "string",
    "progress": {
      "current": "integer",
      "total": "integer"
    },
    "log": "string",
    "job_type": "string | null"
  },
  "tagging": {
    "available": "boolean",
    "is_running": "boolean",
    "status_message": "string",
    "progress": {
      "current": "integer",
      "total": "integer"
    },
    "log": "string"
  }
}
```

#### GET /api/health
Health check endpoint.

**Response:**
```json
{
  "status": "string (typically 'healthy')",
  "scoring_available": "boolean",
  "tagging_available": "boolean"
}
```

#### GET /api/jobs/recent
Get recent job history.

**Query Parameters:**
- `limit`: integer (default: 10, max: 1000)

**Response:**
```json
[
  {
    "id": "integer",
    "input_path": "string",
    "status": "string",
    "created_at": "datetime",
    "updated_at": "datetime"
  }
]
```

#### GET /api/jobs/{job_id}
Get details for a specific job.

**Path Parameters:**
- `job_id`: integer (required)

**Response:**
```json
{
  "id": "integer",
  "input_path": "string",
  "status": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "log": "string"
}
```

## Error Responses

All endpoints may return standard HTTP error responses:

- **400 Bad Request**: Invalid input parameters
  ```json
  {
    "detail": "Error message"
  }
  ```

- **404 Not Found**: Resource not found
  ```json
  {
    "detail": "Resource not found"
  }
  ```

- **500 Internal Server Error**: Server error
  ```json
  {
    "detail": "Error message"
  }
  ```

- **503 Service Unavailable**: Runner not initialized
  ```json
  {
    "detail": "Scoring runner not available"
  }
  ```

## Usage Patterns for LLM Agents

### Pattern 1: Start and Monitor Job
1. POST `/api/scoring/start` with input_path
2. Poll GET `/api/scoring/status` every 2-5 seconds
3. Check `is_running` field
4. When `is_running` is false, job is complete

### Pattern 2: Check System State
1. GET `/api/health` to verify API availability
2. GET `/api/status` to check all runners
3. Proceed with operations based on availability

### Pattern 3: Single Image Processing
1. POST `/api/scoring/single` for immediate scoring
2. POST `/api/tagging/single` for immediate tagging
3. No polling needed (blocking operations)

### Pattern 4: Error Handling
1. Check response `success` field for operation results
2. Check HTTP status code for request-level errors
3. Read `message` field for human-readable error descriptions

## Path Format Notes

- **Windows paths**: `D:/Photos/2024` or `D:\\Photos\\2024`
- **WSL paths**: `/mnt/d/Photos/2024`
- Paths are automatically converted between formats
- Use forward slashes in JSON requests (even on Windows)

## Model Information

### Scoring Models
- **SPAQ**: Spatial Perception of Aesthetic Quality
- **AVA**: Aesthetic Visual Analysis
- **KonIQ**: Konstanz Image Quality
- **PaQ2PiQ**: Perceptual Quality to Perceptual Image Quality
- **LIQE**: Learning Image Quality Evaluator

### Tagging Models
- **CLIP**: Contrastive Language-Image Pre-Training (keyword extraction)
- **BLIP**: Bootstrapping Language-Image Pre-training (caption generation)

## Example LLM Agent Workflow

```python
# 1. Check health
response = GET /api/health
if not response.scoring_available:
    return "Scoring service not available"

# 2. Start scoring job
response = POST /api/scoring/start
    body: {"input_path": "D:/Photos/2024", "skip_existing": true}
job_id = response.data.job_id

# 3. Monitor progress
while True:
    status = GET /api/scoring/status
    if not status.is_running:
        break
    print(f"Progress: {status.progress.current}/{status.progress.total}")
    sleep(3)

# 4. Check final status
final_status = GET /api/scoring/status
print(f"Job completed: {final_status.status_message}")
```

## Schema Access for Code Generation

LLM agents can programmatically access the schema:

1. **OpenAPI JSON**: Fetch `/openapi.json` for complete OpenAPI 3.0 schema
2. **Simplified Schema**: Fetch `/api/schema` for LLM-optimized format
3. **Interactive Docs**: Visit `/docs` for human-readable documentation

The OpenAPI schema includes:
- Complete request/response models
- Parameter descriptions
- Example values
- Error responses
- Authentication requirements (if any)

## Notes for LLM Agents

1. All endpoints return JSON
2. All timestamps are in ISO 8601 format
3. Job IDs are integers
4. Progress is reported as current/total counts
5. Logs may be truncated for very long outputs
6. Operations are asynchronous unless noted as "blocking"
7. Paths support both Windows and WSL formats automatically
8. Provide `input_path` or selector fields on tagging/clustering/scoring start requests

## Related Documents

- [Docs index](../../README.md)
- [API reference](API.md)
- [API schema implementation notes](API_SCHEMA_IMPLEMENTATION.md)

