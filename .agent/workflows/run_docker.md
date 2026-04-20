---
description: Launch the Image Scoring application using Docker Compose (GPU-accelerated)
---

// turbo
1. **Launch Docker WebUI**:
   Start the application and its environment in Docker:
   ```cmd
   .\run_webui_docker.bat
   ```
   *Alternatively, via terminal:*
   ```bash
   docker-compose up --build
   ```

2. **Wait for Initialization**:
   The container will check for PostgreSQL connectivity and run database migrations automatically.

3. **Access Interface**:
   Open your browser to:
   `http://localhost:7860`

4. **Monitoring**:
   - Check container logs for CUDA/GPU detection.
   - Use `docker stats` to monitor resource usage.

5. **Stop**:
   To stop the services:
   ```bash
   docker-compose down
   ```
