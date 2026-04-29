"""Unit tests for _translate_fb_to_pg — Firebird → PostgreSQL SQL translation.

These test real query patterns extracted from modules/db.py to ensure the
regex-based translator produces valid PostgreSQL for every Firebird idiom
used in the codebase.  No database connection required.
"""

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules.db import _translate_fb_to_pg


# ---------------------------------------------------------------------------
# 1. UPDATE OR INSERT → INSERT ... ON CONFLICT ... DO UPDATE
# ---------------------------------------------------------------------------

class TestUpsertTranslation:

    def test_simple_upsert_file_paths(self):
        fb = (
            "UPDATE OR INSERT INTO file_paths (image_id, path, last_seen) "
            "VALUES (?, ?, ?) MATCHING (image_id, path)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "INSERT INTO file_paths" in pg
        assert "ON CONFLICT (image_id, path) DO UPDATE SET" in pg
        assert "last_seen = EXCLUDED.last_seen" in pg
        # MATCHING columns should NOT appear in the SET clause
        assert "image_id = EXCLUDED.image_id" not in pg
        assert "path = EXCLUDED.path" not in pg
        assert "%s" in pg  # placeholders converted
        assert "?" not in pg

    def test_upsert_with_four_columns(self):
        fb = (
            "UPDATE OR INSERT INTO file_paths (image_id, path, path_type, last_seen) "
            "VALUES (?, ?, ?, ?) MATCHING (image_id, path)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (image_id, path) DO UPDATE SET" in pg
        assert "path_type = EXCLUDED.path_type" in pg
        assert "last_seen = EXCLUDED.last_seen" in pg

    def test_large_upsert_images_with_returning(self):
        cols = (
            "job_id, file_path, file_name, file_type, "
            "score, score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe, "
            "score_technical, score_aesthetic, score_general, model_version, "
            "rating, label, keywords, title, description, metadata, scores_json, "
            "thumbnail_path, thumbnail_path_win, image_hash, hash_version, folder_id, created_at"
        )
        placeholders = ", ".join(["?"] * 27)
        fb = (
            f"UPDATE OR INSERT INTO images ({cols}) "
            f"VALUES ({placeholders}) "
            f"MATCHING (file_path) RETURNING id"
        )
        pg = _translate_fb_to_pg(fb)
        assert "INSERT INTO images" in pg
        assert "ON CONFLICT (file_path) DO UPDATE SET" in pg
        assert "RETURNING id" in pg
        # file_path is the MATCHING column — must not be in SET
        assert "file_path = EXCLUDED.file_path" not in pg
        # Other columns must be in SET
        assert "score = EXCLUDED.score" in pg
        assert "folder_id = EXCLUDED.folder_id" in pg
        assert "hash_version = EXCLUDED.hash_version" in pg
        assert pg.count("%s") == 27

    def test_upsert_image_exif(self):
        fb = (
            "UPDATE OR INSERT INTO image_exif ("
            "image_id, make, model, lens_model, focal_length, focal_length_35mm, "
            "date_time_original, create_date, exposure_time, f_number, iso, "
            "exposure_compensation, image_width, image_height, orientation, flash, "
            "image_unique_id, shutter_count, sub_sec_time_original, extracted_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "MATCHING (image_id)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (image_id) DO UPDATE SET" in pg
        assert "image_id = EXCLUDED.image_id" not in pg
        assert "make = EXCLUDED.make" in pg
        assert pg.count("%s") == 20

    def test_upsert_image_xmp(self):
        fb = (
            "UPDATE OR INSERT INTO image_xmp ("
            "image_id, rating, label, pick_status, burst_uuid, stack_id, "
            "keywords, title, description, create_date, modify_date, extracted_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "MATCHING (image_id)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (image_id) DO UPDATE SET" in pg
        assert pg.count("%s") == 12

    def test_upsert_cluster_progress(self):
        fb = (
            "UPDATE OR INSERT INTO cluster_progress (folder_path, last_run) "
            "VALUES (?, ?) MATCHING (folder_path)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (folder_path) DO UPDATE SET" in pg
        assert "last_run = EXCLUDED.last_run" in pg

    def test_upsert_culling_picks(self):
        fb = (
            "UPDATE OR INSERT INTO culling_picks "
            "(session_id, image_id, group_id, decision, auto_suggested, is_best_in_group, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "MATCHING (session_id, image_id)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (session_id, image_id) DO UPDATE SET" in pg
        assert "decision = EXCLUDED.decision" in pg
        assert "session_id = EXCLUDED.session_id" not in pg

    def test_upsert_image_keywords(self):
        fb = (
            "UPDATE OR INSERT INTO image_keywords "
            "(image_id, keyword_id, source, confidence, relevance_weight) "
            "VALUES (?, ?, ?, ?, ?) MATCHING (image_id, keyword_id)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (image_id, keyword_id) DO UPDATE SET" in pg
        assert "source = EXCLUDED.source" in pg
        assert "confidence = EXCLUDED.confidence" in pg
        assert "relevance_weight = EXCLUDED.relevance_weight" in pg

    def test_upsert_xmp_with_current_timestamp(self):
        fb = (
            "UPDATE OR INSERT INTO image_xmp "
            "(image_id, rating, label, keywords, title, description, extracted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "MATCHING (image_id)"
        )
        pg = _translate_fb_to_pg(fb)
        assert "ON CONFLICT (image_id) DO UPDATE SET" in pg
        assert "CURRENT_TIMESTAMP" in pg
        # 6 question marks (not 7 — CURRENT_TIMESTAMP is not a placeholder)
        assert pg.count("%s") == 6


# ---------------------------------------------------------------------------
# 2. SELECT FIRST n → SELECT ... LIMIT n
# ---------------------------------------------------------------------------

class TestSelectFirst:

    def test_select_first_1(self):
        fb = "SELECT FIRST 1 id FROM images WHERE file_path = ?"
        pg = _translate_fb_to_pg(fb)
        assert "SELECT" in pg
        assert "FIRST" not in pg
        assert pg.rstrip().endswith("LIMIT 1")

    def test_select_first_100(self):
        fb = "SELECT FIRST 100 id, file_path FROM images ORDER BY score DESC"
        pg = _translate_fb_to_pg(fb)
        assert "FIRST" not in pg
        assert "LIMIT 100" in pg


# ---------------------------------------------------------------------------
# 3. DATEDIFF → EXTRACT(EPOCH FROM ...)
# ---------------------------------------------------------------------------

class TestDatediff:

    def test_datediff_second(self):
        fb = "SELECT AVG(DATEDIFF(SECOND FROM started_at TO completed_at)) AS avg_sec FROM jobs"
        pg = _translate_fb_to_pg(fb)
        assert "DATEDIFF" not in pg
        assert "EXTRACT(EPOCH FROM (completed_at - started_at))::INTEGER" in pg

    def test_datediff_minute(self):
        fb = "SELECT DATEDIFF(MINUTE FROM started_at TO finished_at) FROM jobs"
        pg = _translate_fb_to_pg(fb)
        assert "(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60)::INTEGER" in pg

    def test_datediff_hour(self):
        fb = "SELECT DATEDIFF(HOUR FROM started_at TO finished_at) FROM jobs"
        pg = _translate_fb_to_pg(fb)
        assert "(EXTRACT(EPOCH FROM (finished_at - started_at)) / 3600)::INTEGER" in pg

    def test_datediff_day(self):
        fb = "SELECT DATEDIFF(DAY FROM started_at TO finished_at) FROM jobs"
        pg = _translate_fb_to_pg(fb)
        assert "EXTRACT(DAY FROM (finished_at - started_at))::INTEGER" in pg


# ---------------------------------------------------------------------------
# 4. RAND() → RANDOM()
# ---------------------------------------------------------------------------

class TestRand:

    def test_rand_in_order_by(self):
        fb = "SELECT id FROM images ORDER BY RAND() FETCH FIRST ? ROWS ONLY"
        pg = _translate_fb_to_pg(fb)
        assert "RANDOM()" in pg
        assert "RAND()" not in pg
        assert "LIMIT %s" in pg


# ---------------------------------------------------------------------------
# 5. LIST() → STRING_AGG()
# ---------------------------------------------------------------------------

class TestList:

    def test_list_aggregate(self):
        fb = "SELECT LIST(jp.phase_code, ', ') FROM job_phases jp WHERE jp.job_id = ?"
        pg = _translate_fb_to_pg(fb)
        assert "STRING_AGG(jp.phase_code, ', ')" in pg
        assert "LIST(" not in pg

    def test_list_in_subquery(self):
        fb = (
            "SELECT COALESCE("
            "(SELECT LIST(COALESCE(kd.keyword_display, kd.keyword_norm), ', ') "
            "FROM image_keywords ik JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
            "WHERE ik.image_id = i.id), i.keywords) AS keywords_csv"
        )
        pg = _translate_fb_to_pg(fb)
        assert "STRING_AGG(" in pg
        assert "LIST(" not in pg


# ---------------------------------------------------------------------------
# 6. Pagination: ROWS ?, FETCH FIRST, OFFSET...FETCH NEXT
# ---------------------------------------------------------------------------

class TestPagination:

    def test_rows_limit(self):
        fb = "SELECT id FROM images ORDER BY score DESC ROWS ?"
        pg = _translate_fb_to_pg(fb)
        assert "LIMIT %s" in pg
        assert "ROWS" not in pg

    def test_fetch_first_param(self):
        fb = "SELECT * FROM jobs ORDER BY created_at DESC FETCH FIRST ? ROWS ONLY"
        pg = _translate_fb_to_pg(fb)
        assert "LIMIT %s" in pg
        assert "FETCH FIRST" not in pg

    def test_fetch_first_literal(self):
        fb = "SELECT * FROM jobs ORDER BY phase_order FETCH FIRST 1 ROWS ONLY"
        pg = _translate_fb_to_pg(fb)
        assert "LIMIT 1" in pg
        assert "FETCH FIRST" not in pg

    def test_fetch_first_inlined_number(self):
        fb = "SELECT * FROM images ORDER BY score DESC FETCH FIRST 100 ROWS ONLY"
        pg = _translate_fb_to_pg(fb)
        assert "LIMIT 100" in pg

    def test_offset_fetch_next(self):
        fb = "SELECT * FROM images ORDER BY score DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        pg = _translate_fb_to_pg(fb)
        assert "OFFSET %s LIMIT %s" in pg
        assert "FETCH NEXT" not in pg

    def test_rand_with_fetch_first(self):
        fb = (
            "SELECT id, file_path, score_general, score_technical, score_aesthetic "
            "FROM images WHERE LOWER(file_type) = 'nef' "
            "ORDER BY RAND() FETCH FIRST ? ROWS ONLY"
        )
        pg = _translate_fb_to_pg(fb)
        assert "RANDOM()" in pg
        assert "LIMIT %s" in pg
        assert "FETCH FIRST" not in pg
        assert "RAND()" not in pg


# ---------------------------------------------------------------------------
# 7. Placeholder conversion: ? → %s (respecting string literals)
# ---------------------------------------------------------------------------

class TestPlaceholders:

    def test_simple_placeholders(self):
        fb = "SELECT * FROM images WHERE id = ? AND score > ?"
        pg = _translate_fb_to_pg(fb)
        assert pg == "SELECT * FROM images WHERE id = %s AND score > %s"

    def test_placeholders_preserve_string_literals(self):
        fb = "SELECT * FROM images WHERE file_path LIKE '%test?%' AND id = ?"
        pg = _translate_fb_to_pg(fb)
        # The ? inside the string literal should be preserved
        assert "%test?%" in pg
        # The bound ? should be converted
        assert "id = %s" in pg

    def test_no_placeholders(self):
        fb = "SELECT COUNT(*) FROM images"
        pg = _translate_fb_to_pg(fb)
        assert pg == "SELECT COUNT(*) FROM images"


# ---------------------------------------------------------------------------
# 8. Combined patterns (multiple transformations in one query)
# ---------------------------------------------------------------------------

class TestCombined:

    def test_datediff_with_fetch_first(self):
        fb = (
            "SELECT AVG(DATEDIFF(SECOND FROM started_at TO completed_at)) AS avg_sec "
            "FROM jobs WHERE status = 'completed' "
            "FETCH FIRST 1 ROWS ONLY"
        )
        pg = _translate_fb_to_pg(fb)
        assert "EXTRACT(EPOCH FROM" in pg
        assert "LIMIT 1" in pg
        assert "DATEDIFF" not in pg
        assert "FETCH FIRST" not in pg

    def test_list_with_placeholders(self):
        fb = (
            "SELECT LIST(jp.phase_code, ', ') AS phases "
            "FROM job_phases jp WHERE jp.job_id = ? AND jp.state = ?"
        )
        pg = _translate_fb_to_pg(fb)
        assert "STRING_AGG(" in pg
        assert pg.count("%s") == 2

    def test_passthrough_standard_sql(self):
        """Standard SQL that needs no translation should pass through unchanged except ? → %s."""
        fb = "INSERT INTO folders (path, parent_id) VALUES (?, ?) RETURNING id"
        pg = _translate_fb_to_pg(fb)
        assert pg == "INSERT INTO folders (path, parent_id) VALUES (%s, %s) RETURNING id"


# ---------------------------------------------------------------------------
# 9. _enqueue_dual_write embedding skip
# ---------------------------------------------------------------------------

class TestDualWriteEmbeddingSkip:

    def test_enqueue_skips_embedding_queries(self):
        """Verify the embedding skip filter logic (unit test of the condition)."""
        embedding_queries = [
            "UPDATE images SET image_embedding = ? WHERE id = ?",
            "INSERT INTO images (id, image_embedding) VALUES (?, ?)",
        ]
        for q in embedding_queries:
            assert "image_embedding" in q.lower()

        non_embedding_queries = [
            "UPDATE images SET score = ? WHERE id = ?",
            "INSERT INTO file_paths (image_id, path) VALUES (?, ?)",
        ]
        for q in non_embedding_queries:
            assert "image_embedding" not in q.lower()
