"""Selection stack sort: equal score_field breaks ties via quality_ranking (mirrors selection.py)."""

from modules.quality_ranking import quality_tiebreak_sort_key_best_first


def _selection_stack_sort_key(img: dict, score_col: str = "score_general") -> tuple:
    s = img.get(score_col) or 0
    c = img.get("created_at") or ""
    i = img.get("id") or 0
    return (
        -float(s) if s else 0,
        quality_tiebreak_sort_key_best_first(img),
        str(c),
        int(i),
    )


def test_equal_score_lower_iso_sorts_first():
    a = {
        "id": 1,
        "score_general": 0.5,
        "created_at": "2020-01-01",
        "iso": 800,
        "exposure_time": "1/250",
        "date_time_original": "2020-01-02",
    }
    b = {
        "id": 2,
        "score_general": 0.5,
        "created_at": "2020-01-01",
        "iso": 100,
        "exposure_time": "1/250",
        "date_time_original": "2020-01-02",
    }
    ordered = sorted([a, b], key=_selection_stack_sort_key)
    assert ordered[0]["id"] == 2
