"""Tests for maintenance / Tools run display names."""

from modules.maintenance_job_display import maintenance_job_input_path


def test_maintenance_job_input_path_default_title():
    s = maintenance_job_input_path("reconcile", {"limit": 5000})
    assert s.startswith("Tools: Reconcile Finished Phases")
    assert "limit=5000" in s


def test_maintenance_job_input_path_ui_job_name():
    s = maintenance_job_input_path(
        "reconcile",
        {"limit": 100},
        job_name="Reconcile Finished Phases",
    )
    assert s.startswith("Tools: Reconcile Finished Phases")
    assert "limit=100" in s


def test_maintenance_job_input_path_scope_truncation():
    long_path = "/" + ("x" * 200)
    s = maintenance_job_input_path(
        "heal_thumbnails",
        {"limit": 50, "input_path": long_path},
    )
    assert "scope=" in s
    assert "..." in s
