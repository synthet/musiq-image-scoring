"""Runner activity snapshot for operator status pages (/app)."""

from __future__ import annotations


def _unified_monitor_status(scoring_runner, tagging_runner, selection_runner):
    """Find whichever runner is active and return data for the live run monitor."""
    for runner_obj, name in [
        (scoring_runner, "Quality Analysis"),
        (selection_runner, "Similarity Clustering"),
        (tagging_runner, "Tagging"),
    ]:
        if not runner_obj:
            continue
        result = runner_obj.get_status()
        is_running, log, msg, cur, tot = result[:5]
        depth = result[5] if len(result) > 5 else 0
        if is_running:
            return True, name, msg, cur, tot, log, depth
    return False, "", "", 0, 0, "", 0


def get_runner_activity_snapshot(
    scoring_runner,
    tagging_runner,
    selection_runner,
    clustering_runner=None,
):
    """Return a plain-dict snapshot of all runner states for operator status pages."""
    is_running, name, msg, cur, tot, log, _depth = _unified_monitor_status(
        scoring_runner, tagging_runner, selection_runner
    )
    runners = []
    for runner_obj, label in [
        (scoring_runner, "Quality Analysis"),
        (selection_runner, "Similarity Clustering"),
        (tagging_runner, "Tagging"),
        (clustering_runner, "Clustering"),
    ]:
        if runner_obj is None:
            continue
        result = runner_obj.get_status()
        r_running, r_log, r_msg, r_cur, r_tot = result[:5]
        runners.append({
            "name": label,
            "running": r_running,
            "message": r_msg,
            "current": r_cur,
            "total": r_tot,
            "log": r_log,
        })
    return {
        "any_running": is_running,
        "active_runner": name if is_running else None,
        "active_message": msg if is_running else "",
        "active_progress": f"{cur}/{tot}" if is_running and tot else "",
        "active_log": log if is_running else "",
        "runners": runners,
    }
