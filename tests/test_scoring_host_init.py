"""ScoringRunner uses MultiModelHost via factory (mocked, no ML)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.scoring import ScoringRunner


@patch("modules.scoring._musiq_import_error", None)
def test_init_shared_scorer_builds_host():
    runner = ScoringRunner()
    host = MagicMock()
    host.VERSION = "host-test"

    with patch(
        "modules.engines.factory.create_production_scoring_host",
        return_value=host,
    ) as create_mock, patch(
        "modules.engines.factory.load_production_models",
        return_value=(True, "ok"),
    ) as load_mock:
        logs = []
        ok = runner._init_shared_scorer(lambda msg, level="INFO": logs.append(msg))

    assert ok is True
    assert runner.shared_scorer is host
    create_mock.assert_called_once()
    load_mock.assert_called_once()
    assert load_mock.call_args[0][0] is host
    assert any("Models initialized" in m for m in logs)


@patch("modules.scoring._musiq_import_error", None)
def test_init_shared_scorer_reuses_injected_engine():
    injected = MagicMock()
    runner = ScoringRunner(scoring_engine=injected)
    logs = []
    assert runner._init_shared_scorer(lambda msg, level="INFO": logs.append(msg)) is True
    assert runner.shared_scorer is injected
    assert any("injected" in m.lower() for m in logs)
