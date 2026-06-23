@echo off
echo Resuming library-wide re-cluster from checkpoint...
echo Checkpoint: reports\clip-culling\rollout_recluster.checkpoint.json
echo Log:        reports\clip-culling\rollout_recluster.log
echo.
wsl -d Ubuntu bash -lc "bash /mnt/d/Projects/image-scoring-backend/scripts/research/clip_culling/resume_recluster.sh"
pause
