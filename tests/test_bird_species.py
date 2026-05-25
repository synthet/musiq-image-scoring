"""
Tests for modules/bird_species.py — BioCLIP 2 bird species classification.

All tests in this file are runnable without GPU or ML dependencies unless
explicitly marked with @pytest.mark.ml.

Run with:
    pytest tests/test_bird_species.py -v -m "not ml"
"""

import json
import threading
import pytest

from modules.bird_species import (
    BirdSpeciesRunner,
    BioCLIPClassifier,
    _load_default_species,
    _get_image_ids_with_species_keyword,
)


# ──────────────────────────────────────────────────────────────────────────────
# _load_default_species
# ──────────────────────────────────────────────────────────────────────────────

def test_load_default_species_returns_list():
    species = _load_default_species()
    assert isinstance(species, list)
    assert len(species) > 0


def test_load_default_species_skips_comments_and_blanks():
    species = _load_default_species()
    for name in species:
        assert not name.startswith("#"), f"Comment line leaked into species list: {name!r}"
        assert name.strip() != "", "Blank entry found in species list"


def test_load_default_species_missing_file(tmp_path, monkeypatch):
    import modules.bird_species as bs
    monkeypatch.setattr(bs, "_DEFAULT_SPECIES_LIST_PATH", tmp_path / "nonexistent.txt")
    result = bs._load_default_species()
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# BirdSpeciesRunner — state machine
# ──────────────────────────────────────────────────────────────────────────────

def test_runner_initial_state():
    runner = BirdSpeciesRunner()
    is_running, log_text, status_msg, current, total = runner.get_status()
    assert is_running is False
    assert status_msg == "Idle"
    assert current == 0
    assert total == 0
    assert log_text == ""


def test_runner_already_running_guard():
    runner = BirdSpeciesRunner()
    runner.is_running = True
    result = runner.start_batch("/some/path")
    assert result == "Error: Already running."


def test_runner_stop_sets_stop_event():
    runner = BirdSpeciesRunner()
    assert not runner.stop_event.is_set()
    runner.stop()
    assert runner.stop_event.is_set()


def test_runner_start_batch_spawns_thread(monkeypatch):
    """start_batch() should set is_running=True and start a daemon thread."""
    runner = BirdSpeciesRunner()
    threads_started = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            self._target = target
        def start(self):
            threads_started.append(True)

    monkeypatch.setattr(threading, "Thread", _FakeThread)

    # Patch _run_batch_internal to be a no-op so the thread body doesn't execute
    monkeypatch.setattr(runner, "_run_batch_internal", lambda *a, **kw: None)

    # Patch db.create_job so we don't need a DB
    import modules.db as _db
    monkeypatch.setattr(_db, "create_job", lambda *a, **kw: 99)

    result = runner.start_batch(None, job_id=1)
    assert result == "Started"
    assert runner.is_running is True
    assert threads_started == [True]


# ──────────────────────────────────────────────────────────────────────────────
# _get_image_ids_with_species_keyword — chunking
# ──────────────────────────────────────────────────────────────────────────────

def test_get_image_ids_with_species_keyword_empty():
    result = _get_image_ids_with_species_keyword([])
    assert result == set()


def test_get_image_ids_with_species_keyword_chunking(monkeypatch):
    """Large ID lists (>900) must be split into multiple DB queries."""
    sql_calls = []

    class _FakeCursor:
        def execute(self, sql, params):
            sql_calls.append(params)
        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()
        def close(self):
            pass

    import modules.db as _db
    monkeypatch.setattr(_db, "get_db", lambda: _FakeConn())

    large_id_list = list(range(1, 1901))  # 1900 IDs → requires ≥2 chunks
    result = _get_image_ids_with_species_keyword(large_id_list)

    assert isinstance(result, set)
    # Must have issued at least 2 separate SQL calls
    assert len(sql_calls) >= 2, (
        f"Expected ≥2 SQL calls for 1900 IDs, got {len(sql_calls)}"
    )
    # No single call should have more than 900 params
    for params in sql_calls:
        assert len(params) <= 900, f"Chunk size exceeded Firebird limit: {len(params)}"


# ──────────────────────────────────────────────────────────────────────────────
# BioCLIPClassifier — construction (no ML needed)
# ──────────────────────────────────────────────────────────────────────────────

def test_bioclip_classifier_model_none_before_load(monkeypatch):
    """Model should not be loaded on instantiation."""
    monkeypatch.setattr("builtins.__import__", __import__)  # no-op guard
    import torch as _torch
    monkeypatch.setattr(_torch.cuda, "is_available", lambda: False)
    clf = BioCLIPClassifier()
    assert clf.model is None
    assert clf.device == "cpu"


@pytest.mark.ml
def test_bioclip_text_feature_cache_hit():
    """Calling _get_text_features twice with the same list should reuse cached result."""
    import torch

    clf = BioCLIPClassifier(device="cpu")
    clf.load_model()

    species = ["American Robin", "Bald Eagle"]
    features_a = clf._get_text_features(species)
    features_b = clf._get_text_features(species)

    assert features_a is features_b, "Expected the same cached tensor object"


@pytest.mark.ml
def test_bioclip_text_feature_cache_invalidated_on_new_list():
    """Changing the species list must invalidate the cache."""
    import torch

    clf = BioCLIPClassifier(device="cpu")
    clf.load_model()

    features_a = clf._get_text_features(["American Robin"])
    features_b = clf._get_text_features(["Bald Eagle"])  # different list

    assert features_a is not features_b, "Cache should have been invalidated"


# ──────────────────────────────────────────────────────────────────────────────
# JobDispatcher routing
# ──────────────────────────────────────────────────────────────────────────────

class _DummyRunner:
    def __init__(self, is_running=False, result="Started"):
        self.is_running = is_running
        self.result = result
        self.calls = []

    def start_batch(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    def get_status(self):
        return self.is_running, "", "Idle", 0, 0

    def stop(self):
        pass


def test_dispatcher_routes_bird_species(monkeypatch):
    from modules.job_dispatcher import JobDispatcher

    bird_runner = _DummyRunner()
    dispatcher = JobDispatcher(bird_species_runner=bird_runner)

    queued_job = {
        "id": 101,
        "job_type": "bird_species",
        "input_path": "D:/Photos/Birds",
        "queue_payload": json.dumps({
            "input_path": "D:/Photos/Birds",
            "threshold": 0.15,
            "top_k": 2,
            "overwrite": True,
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **kw: None)
    monkeypatch.setattr(
        JobDispatcher,
        "_jit_replan_phase",
        lambda self, job_id, payload, queue_key, input_path: (payload, [1], False),
    )

    dispatcher._tick()

    assert len(bird_runner.calls) == 1
    _args, kwargs = bird_runner.calls[0]
    assert kwargs.get("job_id") == 101
    assert kwargs.get("threshold") == 0.15
    assert kwargs.get("top_k") == 2
    assert kwargs.get("overwrite") is True


def test_runner_missing_file_marks_skipped_not_failed(monkeypatch):
    """File-not-found at classify time must record status='skipped' (terminal at
    current executor version) so the workflow heal stops re-queuing the folder.
    Regression: bird_species heal loop on /mnt/d/Photos/Z8/180-600mm/2026/2026-05-09
    where one image with last_error='File not found' kept respawning the same job.
    """
    import modules.bird_species as bs

    class _FakeClassifier:
        last_image_embedding = None
        def load_model(self):
            pass
        def classify(self, *a, **kw):
            raise AssertionError("classify must not be called when file is missing")

    runner = BirdSpeciesRunner()
    runner.classifier = _FakeClassifier()

    calls = []

    def _fake_set_status(image_id, phase_code, status, **kw):
        calls.append({"image_id": image_id, "phase_code": phase_code, "status": status, **kw})

    monkeypatch.setattr(bs, "_load_default_species", lambda: ["American Robin"])
    monkeypatch.setattr(bs, "_resolve_inference_path", lambda row, fp: "/does/not/exist/missing.jpg")
    monkeypatch.setattr(bs.os.path, "exists", lambda p: False)

    import modules.db as _db
    monkeypatch.setattr(_db, "get_images_with_keyword",
                        lambda **kw: [{"id": 162932, "file_path": "/mnt/d/Photos/missing.NEF", "keywords": "birds"}])
    monkeypatch.setattr(_db, "update_job_status", lambda *a, **kw: None)
    monkeypatch.setattr(_db, "job_should_stop_processing", lambda *a, **kw: False)
    monkeypatch.setattr(_db, "set_image_phase_status", _fake_set_status)
    monkeypatch.setattr(bs, "_get_image_ids_with_species_keyword", lambda ids: set())

    from modules.events import event_manager
    monkeypatch.setattr(event_manager, "broadcast_threadsafe", lambda *a, **kw: None)

    runner._run_batch_internal(
        input_path="/mnt/d/Photos",
        candidate_species=None,
        threshold=0.1,
        top_k=3,
        overwrite=True,
        job_id=12345,
    )

    status_calls = [c for c in calls if c["image_id"] == 162932]
    assert len(status_calls) == 1, f"Expected one phase-status write, got {calls}"
    c = status_calls[0]
    assert c["status"] == "skipped", (
        f"Missing file must set status='skipped' (terminal); got {c['status']!r}. "
        "Using 'failed' would cause heal_workflow_bird_species to re-queue indefinitely."
    )
    assert c.get("skip_reason") == "file_missing"
    assert c.get("executor_version") == bs.BIRD_SPECIES_RUNNER_VERSION


def test_runner_writes_bioclip_species_confidence_maps(monkeypatch):
    import modules.bird_species as bs

    class _FakeClassifier:
        last_image_embedding = None

        def classify(self, *args, **kwargs):
            return [("American Robin", 0.82), ("Mallard", 0.09)]

    runner = BirdSpeciesRunner()
    runner.classifier = _FakeClassifier()
    helper_calls = []
    status_calls = []

    import modules.db as _db

    monkeypatch.setattr(bs.os.path, "exists", lambda p: True)
    monkeypatch.setattr(bs, "_resolve_inference_path", lambda row, fp: fp)
    monkeypatch.setattr(_db, "get_images_with_keyword", lambda **kw: [{
        "id": 42,
        "file_path": "/photos/bird.jpg",
        "keywords": "birds,travel,species:Old Match",
    }])
    monkeypatch.setattr(_db, "update_image_keywords_for_image", lambda *args, **kw: helper_calls.append((args, kw)))
    monkeypatch.setattr(_db, "set_image_phase_status", lambda *args, **kw: status_calls.append((args, kw)))

    runner._run_batch_internal(
        input_path="/photos",
        candidate_species=["American Robin", "Mallard"],
        threshold=0.1,
        top_k=3,
        overwrite=True,
        job_id=None,
    )

    assert len(helper_calls) == 1
    args, kwargs = helper_calls[0]
    assert args[0] == 42
    merged_keywords = args[1]
    assert "birds" in merged_keywords
    assert "travel" in merged_keywords
    assert "species:Old Match" not in merged_keywords
    assert "species:American Robin" in merged_keywords
    assert "species:Mallard" in merged_keywords
    assert kwargs["source"] == "auto"
    assert kwargs["confidence_map"] == {
        "species:american robin": 0.82,
        "species:mallard": 0.09,
    }
    assert kwargs["source_map"] == {
        "species:american robin": "bioclip",
        "species:mallard": "bioclip",
    }
    assert any(args[2] == "done" for args, _ in status_calls)


def test_dispatcher_bird_species_runner_busy_blocks_dequeue(monkeypatch):
    from modules.job_dispatcher import JobDispatcher

    bird_runner = _DummyRunner(is_running=True)
    dispatcher = JobDispatcher(bird_species_runner=bird_runner)

    def _should_not_dequeue():
        raise AssertionError("dequeue_next_job must not be called while bird_species runner is busy")

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", _should_not_dequeue)

    assert dispatcher._any_runner_busy() is True
    assert dispatcher._get_active_runner() == "bird_species"
    dispatcher._tick()  # must not raise
