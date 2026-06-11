import math

from modules.keyword_relevance import (
    RELEVANCE_SIGMOID_TEMPERATURE,
    cosine_to_relevance,
)


def test_cosine_to_relevance_monotonic_and_bounded():
    lows = cosine_to_relevance(-0.5)
    mid = cosine_to_relevance(0.0)
    high = cosine_to_relevance(0.5)
    assert 0.0 < lows < mid < high < 1.0
    # cosine 0 -> sigmoid(0) == 0.5
    assert math.isclose(mid, 0.5, abs_tol=1e-9)


def test_cosine_to_relevance_matches_sigmoid():
    cos = 0.27
    expected = 1.0 / (1.0 + math.exp(-cos / RELEVANCE_SIGMOID_TEMPERATURE))
    assert math.isclose(cosine_to_relevance(cos), expected, rel_tol=1e-6)


def test_cosine_to_relevance_handles_non_finite_and_bad_input():
    assert cosine_to_relevance(float("nan")) == 1.0
    assert cosine_to_relevance(float("inf")) == 1.0
    assert cosine_to_relevance("oops") == 1.0


def test_cosine_to_relevance_extreme_values_stay_inside_unit_interval():
    assert 0.0 < cosine_to_relevance(-1000.0) < cosine_to_relevance(1000.0) < 1.0
