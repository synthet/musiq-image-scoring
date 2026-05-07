"""Culling heal runs must use canonical phase order (metadata before culling)."""

from pathlib import Path

from modules import workflow_healing


def test_enqueue_heal_culling_phases_metadata_before_culling(monkeypatch, tmp_path: Path):
    folder = tmp_path / "heal_folder"
    folder.mkdir()

    captured: dict = {}

    def fake_enqueue_job_with_phases(
        input_path,
        phase_code=None,
        job_type=None,
        queue_payload=None,
        description=None,
        phase_codes=None,
        first_phase_state="queued",
    ):
        captured["phase_codes"] = list(phase_codes or [])
        return 999, 1

    monkeypatch.setattr("modules.db.enqueue_job_with_phases", fake_enqueue_job_with_phases)

    job_id, pos = workflow_healing._enqueue_heal_run(str(folder), "culling", run_mode="validate_and_repair")

    assert job_id == 999
    assert pos == 1
    assert captured["phase_codes"] == ["metadata", "culling"]
