import pytest

pytestmark = pytest.mark.wsl

try:
    from modules.clustering import ClusteringEngine
    from modules.scoring import ScoringRunner
    from modules.tagging import TaggingRunner
except ImportError as e:
    pytest.skip(f"ML/runner deps not available: {e}", allow_module_level=True)


def test_scoring_start_batch_selector_empty_does_not_require_path(monkeypatch):
    runner = ScoringRunner()
    calls = []

    def fake_run(input_path, job_id, skip_existing, resolved_image_ids=None, **kwargs):
        calls.append((input_path, job_id, skip_existing, resolved_image_ids))
        runner.status_message = "Done (no images)"

    monkeypatch.setattr(runner, "_run_batch_internal", fake_run)

    result = runner.start_batch(None, job_id=12, skip_existing=True, resolved_image_ids=[])
    runner._thread.join(timeout=1)

    assert result == "Started"
    assert calls == [(None, 12, True, [])]


def test_tagging_selector_empty_marks_job_completed(monkeypatch):
    runner = TaggingRunner()
    runner.scorer = object()  # skip model loading path

    status_updates = []
    events = []

    monkeypatch.setattr("modules.tagging.db.get_all_images", lambda limit=-1: [])
    monkeypatch.setattr(
        "modules.tagging.db.update_job_status",
        lambda *args, **kwargs: status_updates.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "modules.events.event_manager.broadcast_threadsafe",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )

    runner._run_batch_internal(
        input_path=None,
        custom_keywords=None,
        overwrite=False,
        generate_captions=False,
        job_id=44,
        resolved_image_ids=[],
    )

    assert runner.status_message == "Done (no images)"
    assert any(args and args[0] == 44 and args[1] == "completed" for args, _ in status_updates)
    assert any(args and args[0] == "job_completed" for args, _ in events)


def test_clustering_selector_empty_returns_no_images(monkeypatch):
    engine = ClusteringEngine()

    monkeypatch.setattr("modules.clustering.db.get_clustered_folders", lambda: [])
    monkeypatch.setattr(
        "modules.clustering.db.get_images_by_folder",
        lambda folder: (_ for _ in ()).throw(AssertionError("Folder lookup should not run for empty selectors")),
    )
    gen = engine._cluster_images_impl(
        distance_threshold=None,
        time_gap_seconds=None,
        force_rescan=False,
        target_folder=None,
        job_id=None,
        target_image_ids=[],
    )

    first = next(gen)
    assert first[0] == "No images matched target IDs."
    with pytest.raises(StopIteration):
        next(gen)
