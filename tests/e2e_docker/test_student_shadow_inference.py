"""Docker inference E2E for a real student checkpoint (CUDA image).

Skipped in the fast subset; run via docker compose --profile e2e-inference.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.gpu, pytest.mark.ml]


def test_real_checkpoint_scores_sample_without_changing_live_composite():
    pytest.skip("Requires CUDA e2e image, local bundle, and sample NEF")


def test_raw_orientation_and_failure_contract_match_baseline():
    pytest.skip("Requires e2e inference container and RAW fixtures")
