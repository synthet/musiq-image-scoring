"""Ensure PHASE_PREREQUISITES matches PhaseExecutor.depends_on from phase_executors."""

import pytest

from modules.phase_executors import register_all
from modules.phases import PHASE_PREREQUISITES, PhaseCode, PhaseRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    PhaseRegistry._executors.clear()
    yield
    PhaseRegistry._executors.clear()


def test_phase_prerequisites_match_registered_executors():
    """Drift guard: registry depends_on must match PHASE_PREREQUISITES."""

    class _StubRunner:
        def start_batch(self, *_a, **_kw):
            return "ok"

    register_all(
        indexing_runner=_StubRunner(),
        metadata_runner=_StubRunner(),
        scoring_runner=_StubRunner(),
        tagging_runner=_StubRunner(),
        clustering_runner=_StubRunner(),
        selection_runner=_StubRunner(),
        bird_species_runner=_StubRunner(),
    )

    for code_str, expected_tuple in PHASE_PREREQUISITES.items():
        ex = PhaseRegistry._executors.get(PhaseCode(code_str))
        assert ex is not None, f"no executor registered for {code_str!r}"
        deps = tuple(
            d.value if isinstance(d, PhaseCode) else str(d)
            for d in (ex.depends_on or [])
        )
        assert deps == expected_tuple, (
            f"mismatch for {code_str}: registry={deps} PHASE_PREREQUISITES={expected_tuple}"
        )
