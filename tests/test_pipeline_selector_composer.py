from modules import pipeline_selector_composer as composer


def test_compose_selector_request_missing_path_adds_folder_and_image_selectors():
    """Windows paths sent to a Linux API are neither file nor dir locally; still match DB folder/file paths."""
    ghost = "/__no_such_path_image_scoring__/session"
    payload = composer.compose_selector_request(input_path=ghost)
    assert ghost in (payload["folder_paths"] or [])
    assert ghost in (payload["image_paths"] or [])


def test_compose_selector_request_accepts_native_lists(tmp_path):
    folder = str(tmp_path)
    payload = composer.compose_selector_request(
        input_path=folder,
        image_ids_raw=["1", 2],
        image_paths_raw=["a.jpg", "b.jpg"],
        folder_ids_raw=["3"],
        folder_paths_raw=["/x", "/y"],
        exclude_image_paths_raw=["e.jpg"],
        recursive=False,
    )

    assert payload["input_path"] == folder
    assert payload["image_ids"] == [1, 2]
    assert payload["folder_ids"] == [3]
    assert payload["folder_paths"][-1] == folder
    assert payload["exclude_image_paths"] == ["e.jpg"]
    assert payload["recursive"] is False


def test_validate_and_preview_reports_duplicate_entries(monkeypatch):
    monkeypatch.setattr(
        composer,
        "resolve_selectors",
        lambda **kwargs: {
            "resolved_image_ids": [10, 11],
            "missing_image_paths": [],
            "missing_folder_paths": [],
        },
    )

    preview = composer.validate_and_preview(
        {
            "image_ids": [1, 1],
            "image_paths": ["x.jpg", "x.jpg"],
            "folder_ids": [2],
            "folder_paths": ["/a"],
            "exclude_image_paths": [],
            "recursive": True,
        }
    )

    assert preview["preview_count"] == 2
    assert any("Duplicate inclusion entries detected" in warning for warning in preview["warnings"])
