"""
Tests for modules/paths.py — the unified path resolver.

Covers pure converters, Docker remap, and resolve_to_existing with
mocked filesystem.  Cross-platform behavior tested via monkeypatched
``platform.system()`` and ``paths.RUNTIME_OS``.
"""

import os

import pytest

from modules import paths


# ===================================================================
# is_wsl_path / is_windows_path
# ===================================================================

class TestPathDetection:
    def test_is_wsl_path_basic(self):
        assert paths.is_wsl_path("/mnt/d/Photos/img.jpg") is True

    def test_is_wsl_path_root(self):
        assert paths.is_wsl_path("/mnt/c/") is True

    def test_is_wsl_path_false_for_windows(self):
        assert paths.is_wsl_path("D:\\Photos\\img.jpg") is False

    def test_is_wsl_path_false_for_linux(self):
        assert paths.is_wsl_path("/home/user/img.jpg") is False

    def test_is_wsl_path_empty(self):
        assert paths.is_wsl_path("") is False
        assert paths.is_wsl_path(None) is False

    def test_is_windows_path_backslash(self):
        assert paths.is_windows_path("D:\\Photos\\img.jpg") is True

    def test_is_windows_path_forward_slash(self):
        assert paths.is_windows_path("D:/Photos/img.jpg") is True

    def test_is_windows_path_false_for_wsl(self):
        assert paths.is_windows_path("/mnt/d/Photos") is False

    def test_is_windows_path_empty(self):
        assert paths.is_windows_path("") is False
        assert paths.is_windows_path(None) is False


# ===================================================================
# normalize
# ===================================================================

class TestNormalize:
    def test_collapse_double_slashes_in_mnt(self):
        assert paths.normalize("/mnt//d/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_triple_slashes(self):
        assert paths.normalize("/mnt///d///Photos") == "/mnt/d/Photos"

    def test_strips_trailing_slash(self):
        assert paths.normalize("/mnt/d/Photos/") == "/mnt/d/Photos"

    def test_preserves_drive_root(self):
        assert paths.normalize("D:/") == "D:/"

    def test_backslash_to_forward(self):
        assert paths.normalize("D:\\Photos\\img.jpg") == "D:/Photos/img.jpg"

    def test_empty_string(self):
        assert paths.normalize("") == ""
        assert paths.normalize(None) == ""

    def test_no_change_when_clean(self):
        assert paths.normalize("/mnt/d/Photos") == "/mnt/d/Photos"


# ===================================================================
# to_windows
# ===================================================================

class TestToWindows:
    def test_wsl_to_windows(self):
        assert paths.to_windows("/mnt/d/Photos/test.jpg") == "D:\\Photos\\test.jpg"

    def test_wsl_drive_c(self):
        assert paths.to_windows("/mnt/c/Users/Test/img.nef") == "C:\\Users\\Test\\img.nef"

    def test_already_windows_backslash(self):
        assert paths.to_windows("D:\\Photos\\test.jpg") == "D:\\Photos\\test.jpg"

    def test_already_windows_forward_slash(self):
        assert paths.to_windows("D:/Photos/test.jpg") == "D:\\Photos\\test.jpg"

    def test_hybrid_d_mnt_d(self):
        assert paths.to_windows("D:/mnt/d/Photos/test.jpg") == "D:\\Photos\\test.jpg"

    def test_hybrid_d_mnt_c(self):
        assert paths.to_windows("D:/mnt/c/Users/x/a.jpg") == "C:\\Users\\x\\a.jpg"

    def test_hybrid_backslash(self):
        assert paths.to_windows("D:\\mnt\\d\\Photos\\test.jpg") == "D:\\Photos\\test.jpg"

    def test_none_returns_none(self):
        assert paths.to_windows(None) is None

    def test_empty_returns_none(self):
        assert paths.to_windows("") is None

    def test_wsl_with_double_slashes(self):
        assert paths.to_windows("/mnt//d/Photos/img.jpg") == "D:\\Photos\\img.jpg"

    def test_drive_root_only(self):
        result = paths.to_windows("/mnt/d/")
        # Should be D:\ with nothing trailing
        assert result is not None
        assert result.startswith("D:\\")

    def test_hybrid_drive_root_only(self):
        result = paths.to_windows("D:/mnt/c/")
        assert result is not None
        assert result.startswith("C:\\")


# ===================================================================
# to_wsl
# ===================================================================

class TestToWsl:
    def test_windows_forward_slash(self):
        assert paths.to_wsl("D:/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_windows_backslash(self):
        assert paths.to_wsl("D:\\Photos\\img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_already_wsl(self):
        assert paths.to_wsl("/mnt/d/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_linux_path_unchanged(self):
        assert paths.to_wsl("/home/user/photos.jpg") == "/home/user/photos.jpg"

    def test_empty(self):
        assert paths.to_wsl("") == ""
        assert paths.to_wsl(None) == ""


# ===================================================================
# to_local (platform-dependent)
# ===================================================================

class TestToLocal:
    def test_wsl_to_windows_on_windows(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        assert paths.to_local("/mnt/d/Photos/img.jpg") == "D:/Photos/img.jpg"

    def test_wsl_double_slash_on_windows(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        assert paths.to_local("/mnt//d/Photos/img.jpg") == "D:/Photos/img.jpg"

    def test_drive_uppercase_on_windows(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        assert paths.to_local("/mnt/c/Users/test.nef") == "C:/Users/test.nef"

    def test_windows_unchanged_on_windows(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        assert paths.to_local("D:/Photos/img.jpg") == "D:/Photos/img.jpg"

    def test_windows_to_wsl_on_linux(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Linux")
        assert paths.to_local("D:/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_windows_backslash_to_wsl_on_linux(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Linux")
        assert paths.to_local("D:\\Photos\\img.jpg") == "/mnt/d/Photos/img.jpg"

    def test_linux_path_unchanged_on_linux(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Linux")
        assert paths.to_local("/home/user/photos/img.jpg") == "/home/user/photos/img.jpg"

    def test_empty(self, monkeypatch):
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        assert paths.to_local("") == ""
        assert paths.to_local(None) == ""


# ===================================================================
# all_variants
# ===================================================================

class TestAllVariants:
    def test_wsl_path_produces_both(self):
        variants = paths.all_variants("/mnt/d/Photos/img.jpg")
        strs = [v.replace("\\", "/") for v in variants]
        assert "/mnt/d/Photos/img.jpg" in strs
        assert "D:/Photos/img.jpg" in strs

    def test_windows_path_produces_both(self):
        variants = paths.all_variants("D:\\Photos\\img.jpg")
        strs = [v.replace("\\", "/") for v in variants]
        assert "D:/Photos/img.jpg" in strs or "D:\\Photos\\img.jpg" in [v for v in variants]
        assert "/mnt/d/Photos/img.jpg" in strs

    def test_deduplication(self):
        variants = paths.all_variants("/mnt/d/Photos")
        assert len(variants) == len(set(variants))

    def test_empty(self):
        assert paths.all_variants("") == []
        assert paths.all_variants(None) == []


# ===================================================================
# remap_docker_project
# ===================================================================

class TestRemapDockerProject:
    def test_remap_wsl_host_to_container(self, monkeypatch):
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", "D:\\Projects\\image-scoring-backend")
        from modules import config
        monkeypatch.setattr(config, "BASE_DIR", "/app")

        result = paths.remap_docker_project(
            "/mnt/d/Projects/image-scoring-backend/thumbnails/b6/abc.jpg"
        )
        assert result is not None
        assert result.replace("\\", "/") == "/app/thumbnails/b6/abc.jpg"

    def test_remap_windows_host_to_container(self, monkeypatch):
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", "D:\\Projects\\image-scoring-backend")
        from modules import config
        monkeypatch.setattr(config, "BASE_DIR", "/app")

        result = paths.remap_docker_project(
            "D:\\Projects\\image-scoring-backend\\thumbnails\\b6\\abc.jpg"
        )
        assert result is not None
        assert result.replace("\\", "/") == "/app/thumbnails/b6/abc.jpg"

    def test_no_remap_outside_project(self, monkeypatch):
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
        monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", "D:\\Projects\\image-scoring-backend")
        from modules import config
        monkeypatch.setattr(config, "BASE_DIR", "/app")

        result = paths.remap_docker_project("/mnt/d/Photos/Z8/DSC_4093.NEF")
        assert result is None

    def test_no_remap_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)

        result = paths.remap_docker_project("/mnt/d/Projects/image-scoring-backend/thumb.jpg")
        assert result is None


# ===================================================================
# resolve_to_existing
# ===================================================================

class TestResolveToExisting:
    def test_existing_path_returned(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_text("fake")
        result = paths.resolve_to_existing(str(f))
        assert result is not None
        assert os.path.exists(result)

    def test_nonexistent_returns_none(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda _p: False)
        result = paths.resolve_to_existing("/mnt/d/does/not/exist")
        assert result is None

    def test_windows_prefers_drive_on_windows(self, monkeypatch):
        """On Windows, /mnt/d/... should convert to D:/... and find that."""
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        checked = []

        def fake_exists(p):
            checked.append(p)
            return str(p).replace("\\", "/") == "D:/Photos/here"

        monkeypatch.setattr(os.path, "exists", fake_exists)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)

        result = paths.resolve_to_existing("/mnt/d/Photos/here")
        assert result is not None
        assert result.replace("\\", "/") == "D:/Photos/here"

    def test_empty_returns_none(self):
        assert paths.resolve_to_existing("") is None
        assert paths.resolve_to_existing(None) is None

    def test_whitespace_stripped(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_text("fake")
        result = paths.resolve_to_existing(f"  {f}  ")
        assert result is not None


# ===================================================================
# Workflow healing regression: /mnt/ path on Windows host
# ===================================================================

class TestWorkflowHealingRegression:
    """Mirrors the bug scenario: DB stores /mnt/d/Photos/2026/..., process
    runs on Windows, workflow healing must resolve to D:\\Photos\\2026\\...
    """

    def test_mnt_path_resolves_on_windows(self, monkeypatch):
        """to_local converts WSL path to Windows drive format."""
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        result = paths.to_local("/mnt/d/Photos/Z8/2026/2026-05-07")
        assert result == "D:/Photos/Z8/2026/2026-05-07"

    def test_resolve_scope_falls_through_to_drive_letter(self, monkeypatch):
        """resolve_to_existing on Windows tries the drive-letter conversion."""
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)

        target_win = os.path.normpath("D:/Photos/Z8/2026/2026-05-07")

        def fake_exists(p):
            return os.path.normpath(p) == target_win

        monkeypatch.setattr(os.path, "exists", fake_exists)

        result = paths.resolve_to_existing("/mnt/d/Photos/Z8/2026/2026-05-07")
        assert result is not None
        assert os.path.normpath(result) == target_win


# ===================================================================
# API layer regression: DB filename lookup + /mnt/ row + Windows host
# ===================================================================

class TestApiResolvePattern:
    """Mirrors the get_raw_preview / generate_thumbnail_endpoint pattern:
    1. Path doesn't exist as-is
    2. Try /mnt/ → D: conversion
    3. Adopt only if os.path.exists()
    """

    def test_resolve_to_existing_for_db_path_on_windows(self, monkeypatch):
        """Simulates: DB stores /mnt/d/Photos/DSC_1234.NEF, host is Windows."""
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)

        db_path = "/mnt/d/Photos/Z8/DSC_1234.NEF"

        def fake_exists(p):
            norm = p.replace("\\", "/")
            return norm == "D:/Photos/Z8/DSC_1234.NEF"

        monkeypatch.setattr(os.path, "exists", fake_exists)

        result = paths.resolve_to_existing(db_path)
        assert result is not None
        assert result.replace("\\", "/") == "D:/Photos/Z8/DSC_1234.NEF"

    def test_resolve_returns_none_when_truly_missing(self, monkeypatch):
        """No variant exists → None, not an exception."""
        monkeypatch.setattr(paths, "RUNTIME_OS", "Windows")
        monkeypatch.setattr(os.path, "exists", lambda _p: False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
        monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)

        result = paths.resolve_to_existing("/mnt/d/Photos/ghost.jpg")
        assert result is None


# ===================================================================
# Input tolerance: weird formats must not break the converters
# ===================================================================

class TestInputTolerance:
    """Every public converter must accept arbitrary input separator styles
    and produce a clean canonical output — the converters are the single
    chokepoint that DB lookups and filesystem accesses depend on.
    """

    # --- normalize ---

    def test_normalize_strips_whitespace(self):
        assert paths.normalize("  /mnt/d/Photos  ") == "/mnt/d/Photos"

    def test_normalize_collapses_runs_outside_mnt(self):
        # Was buggy before: D://Photos was kept
        assert paths.normalize("D://Photos") == "D:/Photos"

    def test_normalize_collapses_escaped_backslash_runs(self):
        # Raw input "D:\\Photos" (i.e. D:\\\\ in Python repr)
        assert paths.normalize("D:\\\\Photos") == "D:/Photos"
        assert paths.normalize("D:\\\\Photos\\\\sub") == "D:/Photos/sub"

    def test_normalize_collapses_leading_double_slash(self):
        # // (or UNC-style) — we don't preserve UNC; collapse to single /
        assert paths.normalize("//mnt/d/Photos") == "/mnt/d/Photos"
        assert paths.normalize("///mnt/d/Photos") == "/mnt/d/Photos"

    def test_normalize_bare_drive_to_drive_root(self):
        assert paths.normalize("d:") == "d:/"
        assert paths.normalize("D:") == "D:/"

    def test_normalize_idempotent(self):
        for s in [
            "/mnt/d/Photos",
            "D:/Photos",
            "D:\\\\Photos\\\\sub",
            "  /mnt//d/Photos/  ",
            "d:",
            "//mnt/d/Photos",
        ]:
            once = paths.normalize(s)
            twice = paths.normalize(once)
            assert once == twice, f"normalize not idempotent for {s!r}: {once!r} != {twice!r}"

    def test_normalize_non_string(self):
        # Tolerate ints / paths / etc. without crashing
        from pathlib import PurePosixPath
        assert paths.normalize(PurePosixPath("/mnt/d/Photos")) == "/mnt/d/Photos"

    # --- to_wsl ---

    def test_to_wsl_hybrid_does_not_double_mnt(self):
        # Was the worst bug: D:/mnt/d/Photos → /mnt/d/mnt/d/Photos
        assert paths.to_wsl("D:/mnt/d/Photos") == "/mnt/d/Photos"
        assert paths.to_wsl("D:\\mnt\\d\\Photos") == "/mnt/d/Photos"
        # Hybrid wins by inner drive letter, not outer
        assert paths.to_wsl("D:/mnt/c/Users") == "/mnt/c/Users"

    def test_to_wsl_handles_double_slashes(self):
        assert paths.to_wsl("d://Photos") == "/mnt/d/Photos"
        assert paths.to_wsl("D:\\\\Photos") == "/mnt/d/Photos"
        assert paths.to_wsl("D:\\\\Photos\\\\sub") == "/mnt/d/Photos/sub"

    def test_to_wsl_bare_drive(self):
        assert paths.to_wsl("d:") == "/mnt/d"
        assert paths.to_wsl("D:\\") == "/mnt/d"
        assert paths.to_wsl("D:/") == "/mnt/d"

    def test_to_wsl_already_wsl_with_doubles(self):
        assert paths.to_wsl("/mnt/d//Photos") == "/mnt/d/Photos"
        assert paths.to_wsl("//mnt/d/Photos") == "/mnt/d/Photos"

    def test_to_wsl_trailing_slash_stripped(self):
        assert paths.to_wsl("D:/Photos/") == "/mnt/d/Photos"
        assert paths.to_wsl("/mnt/d/Photos/") == "/mnt/d/Photos"

    def test_to_wsl_drive_case_lowered(self):
        assert paths.to_wsl("C:\\Users\\me") == "/mnt/c/Users/me"
        assert paths.to_wsl("c:\\users\\me") == "/mnt/c/users/me"

    def test_to_wsl_linux_path_unchanged_but_normalized(self):
        assert paths.to_wsl("/home/user/img.jpg") == "/home/user/img.jpg"
        assert paths.to_wsl("/home//user//img.jpg") == "/home/user/img.jpg"

    # --- to_windows ---

    def test_to_windows_hybrid(self):
        assert paths.to_windows("D:/mnt/d/Photos") == "D:\\Photos"
        # Inner drive wins
        assert paths.to_windows("D:/mnt/c/Users") == "C:\\Users"

    def test_to_windows_handles_double_slashes(self):
        assert paths.to_windows("d://Photos") == "D:\\Photos"
        assert paths.to_windows("//mnt/d/Photos") == "D:\\Photos"

    def test_to_windows_bare_drive(self):
        assert paths.to_windows("d:") == "D:\\"
        assert paths.to_windows("D:\\") == "D:\\"

    def test_to_windows_strips_trailing_slash(self):
        assert paths.to_windows("/mnt/d/Photos/") == "D:\\Photos"
        assert paths.to_windows("D:/Photos/") == "D:\\Photos"

    def test_to_windows_drive_case_uppered(self):
        assert paths.to_windows("c:\\users\\me") == "C:\\users\\me"
        assert paths.to_windows("/mnt/c/Users") == "C:\\Users"

    def test_to_windows_empty_inputs(self):
        assert paths.to_windows("") is None
        assert paths.to_windows(None) is None
        assert paths.to_windows("   ") is None

    # --- is_wsl_path / is_windows_path ---

    def test_is_wsl_path_tolerates_separators(self):
        assert paths.is_wsl_path("\\mnt\\d\\Photos") is True
        assert paths.is_wsl_path("//mnt/d/Photos") is True
        assert paths.is_wsl_path("/mnt//d/Photos") is True
        assert paths.is_wsl_path("  /mnt/d/Photos  ") is True

    def test_is_windows_path_tolerates_separators(self):
        assert paths.is_windows_path("d:") is True  # bare drive
        assert paths.is_windows_path("D:\\Photos") is True
        assert paths.is_windows_path("D:/Photos") is True
        assert paths.is_windows_path("  D:/Photos  ") is True


# ===================================================================
# Round-trip: converting back and forth must converge
# ===================================================================

class TestRoundTrip:
    @pytest.mark.parametrize("input_path,expected_wsl", [
        ("D:\\Photos\\test.jpg", "/mnt/d/Photos/test.jpg"),
        ("D:/Photos/test.jpg", "/mnt/d/Photos/test.jpg"),
        ("d:\\photos\\test.jpg", "/mnt/d/photos/test.jpg"),
        ("D:/mnt/d/Photos/test.jpg", "/mnt/d/Photos/test.jpg"),  # hybrid
        ("/mnt/d/Photos/test.jpg", "/mnt/d/Photos/test.jpg"),
        ("/mnt//d/Photos/test.jpg", "/mnt/d/Photos/test.jpg"),
        ("//mnt/d/Photos/test.jpg", "/mnt/d/Photos/test.jpg"),
        ("  D:\\Photos\\test.jpg  ", "/mnt/d/Photos/test.jpg"),
    ])
    def test_to_wsl_converges(self, input_path, expected_wsl):
        assert paths.to_wsl(input_path) == expected_wsl

    @pytest.mark.parametrize("input_path,expected_win", [
        ("D:\\Photos\\test.jpg", "D:\\Photos\\test.jpg"),
        ("D:/Photos/test.jpg", "D:\\Photos\\test.jpg"),
        ("/mnt/d/Photos/test.jpg", "D:\\Photos\\test.jpg"),
        ("D:/mnt/d/Photos/test.jpg", "D:\\Photos\\test.jpg"),  # hybrid
        ("//mnt/d/Photos/test.jpg", "D:\\Photos\\test.jpg"),
        ("  /mnt//d/Photos/test.jpg  ", "D:\\Photos\\test.jpg"),
    ])
    def test_to_windows_converges(self, input_path, expected_win):
        assert paths.to_windows(input_path) == expected_win

    def test_wsl_to_windows_round_trip(self):
        original = "/mnt/d/Photos/Z8/DSC_1234.NEF"
        assert paths.to_wsl(paths.to_windows(original)) == original

    def test_windows_to_wsl_round_trip(self):
        original = "D:\\Photos\\Z8\\DSC_1234.NEF"
        assert paths.to_windows(paths.to_wsl(original)) == original


# ===================================================================
# db_form / db_lookup_variants
# ===================================================================

class TestDbForm:
    def test_db_form_returns_wsl(self):
        assert paths.db_form("D:\\Photos\\img.jpg") == "/mnt/d/Photos/img.jpg"
        assert paths.db_form("/mnt/d/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"
        assert paths.db_form("D:/mnt/d/Photos/img.jpg") == "/mnt/d/Photos/img.jpg"
        assert paths.db_form("  d://Photos  ") == "/mnt/d/Photos"

    def test_db_form_idempotent(self):
        for s in [
            "D:\\Photos\\img.jpg",
            "/mnt/d/Photos/img.jpg",
            "d:",
            "D:/mnt/d/Photos",
        ]:
            once = paths.db_form(s)
            assert paths.db_form(once) == once, f"db_form not idempotent for {s!r}"

    def test_db_form_empty(self):
        assert paths.db_form("") == ""
        assert paths.db_form(None) == ""

    def test_db_lookup_variants_dedup(self):
        v = paths.db_lookup_variants("/mnt/d/Photos")
        assert len(v) == len(set(v))

    def test_db_lookup_variants_covers_both_forms(self):
        v = paths.db_lookup_variants("D:\\Photos\\img.jpg")
        assert "/mnt/d/Photos/img.jpg" in v
        assert "D:\\Photos\\img.jpg" in v
        assert "D:/Photos/img.jpg" in v  # forward-slash drive form

    def test_db_lookup_variants_empty_input(self):
        assert paths.db_lookup_variants("") == []
        assert paths.db_lookup_variants(None) == []
        assert paths.db_lookup_variants("   ") == []
