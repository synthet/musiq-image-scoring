@echo off
echo Resuming library-wide re-cluster from checkpoint...
echo Checkpoint: reports\clip-culling\rollout_recluster.checkpoint.json
echo Log:        reports\clip-culling\rollout_recluster.log
echo.
wsl bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && python scripts/research/clip_culling/rollout_recluster.py 2>&1 | tee -a reports/clip-culling/rollout_recluster.log"
pause
