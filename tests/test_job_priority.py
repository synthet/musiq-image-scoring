from modules.job_priority import resolve_job_enqueue_priority


def test_auto_drive_default_priority():
    assert resolve_job_enqueue_priority(
        {"tool_id": "runs_auto_drive", "auto_drive_plan_key": "abc"},
        job_type="metadata",
    ) == 100


def test_interactive_submit_boost():
    assert resolve_job_enqueue_priority(
        {"tool_id": "run_submit"},
        job_type="metadata",
    ) == 300


def test_maintenance_lower_priority():
    assert resolve_job_enqueue_priority(
        {"tool_id": "scoring_start"},
        job_type="maintenance",
    ) == 50


def test_small_batch_boost():
    assert resolve_job_enqueue_priority(
        {"tool_id": "run_submit", "resolved_image_ids": [1, 2, 3]},
        job_type="scoring",
    ) == 350


def test_explicit_payload_priority_wins():
    assert resolve_job_enqueue_priority(
        {"tool_id": "run_submit", "priority": 250},
        job_type="scoring",
    ) == 250
