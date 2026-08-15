@echo off
echo Resuming library-wide re-cluster from checkpoint...
echo Checkpoint: reports\clip-culling\rollout_recluster.checkpoint.json
echo Log:        reports\clip-culling\rollout_recluster.log
echo.
call "%~dp0docker_gpu_exec.bat" bash scripts/research/clip_culling/resume_recluster.sh
pause
