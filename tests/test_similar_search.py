"""Tests for similar image search (modules.similar_search)."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

# Import after path is set by conftest
from modules import similar_search


class TestNormalize:
    """Tests for _normalize (L2 normalization)."""

    def test_normalize_1d_unit_vector_unchanged(self):
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_array_almost_equal(out, v)

    def test_normalize_1d_scales_to_unit(self):
        v = np.array([3.0, 4.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_almost_equal(np.linalg.norm(out), 1.0)
        np.testing.assert_array_almost_equal(out, [0.6, 0.8])

    def test_normalize_1d_zero_vector_unchanged(self):
        v = np.array([0.0, 0.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_array_almost_equal(out, v)

    def test_normalize_2d_row_wise(self):
        m = np.array([[3.0, 4.0], [0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        out = similar_search._normalize(m)
        np.testing.assert_almost_equal(np.linalg.norm(out[0]), 1.0)
        np.testing.assert_almost_equal(np.linalg.norm(out[2]), 1.0)
        np.testing.assert_array_almost_equal(out[0], [0.6, 0.8])
        np.testing.assert_array_almost_equal(out[1], [0.0, 0.0])  # zero row unchanged


class TestSearchSimilarImages:
    """Tests for search_similar_images with mocked DB."""

    def test_error_when_no_example_provided(self):
        result = similar_search.search_similar_images()
        assert isinstance(result, dict)
        assert "error" in result
        assert "example_path" in result["error"] or "example_image_id" in result["error"]

    def test_error_when_example_path_not_in_db(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {}
            result = similar_search.search_similar_images(example_path="/nonexistent.jpg")
        assert isinstance(result, dict)
        assert "error" in result
        assert "not found" in result["error"].lower() or "Image" in result["error"]

    def test_returns_list_sorted_by_similarity(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        c1 = q.copy()
        c2 = np.random.randn(dim).astype(np.float32)
        c2 = c2 / np.linalg.norm(c2)
        # Ensure c1 is more similar to q than c2
        sim1 = float(np.dot(q, c1))
        sim2 = float(np.dot(q, c2))
        assert sim1 >= sim2

        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = [
                (2, "/c1.jpg", c1.tobytes()),
                (3, "/c2.jpg", c2.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10
            )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["similarity"] >= result[1]["similarity"]
        assert result[0]["image_id"] == 2
        assert result[0]["file_path"] == "/c1.jpg"
        assert "similarity" in result[0]

    def test_excludes_self_from_results(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 42, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            # Only candidate is the same image (id 42)
            mock_db.get_embeddings_for_search.return_value = [
                (42, "/q.jpg", q.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10
            )
        assert isinstance(result, list)
        assert len(result) == 0

    def test_min_similarity_filter(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        c_high = q * 0.99  # very similar
        c_low = np.random.randn(dim).astype(np.float32)
        c_low = c_low / np.linalg.norm(c_low)
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = [
                (2, "/high.jpg", c_high.tobytes()),
                (3, "/low.jpg", c_low.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10, min_similarity=0.9
            )
        assert isinstance(result, list)
        assert all(r["similarity"] >= 0.9 for r in result)
        assert len(result) <= 2

    def test_limit_respected(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        candidates = [
            (i, f"/img{i}.jpg", (q + np.random.randn(dim).astype(np.float32) * 0.1).tobytes())
            for i in range(2, 12)
        ]
        for i, _, b in candidates:
            # normalize would be applied in search; we just need valid bytes
            pass
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = candidates
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=3
            )
        assert isinstance(result, list)
        assert len(result) == 3

    def test_error_when_no_embeddings_in_db(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = np.random.randn(1280).astype(np.float32).tobytes()
            mock_db.get_embeddings_for_search.return_value = []
            result = similar_search.search_similar_images(example_path="/q.jpg")
        assert isinstance(result, dict)
        assert "error" in result
        assert "embedding" in result["error"].lower() or "Run clustering" in result["error"]


class TestFindNearDuplicates:
    """Tests for find_near_duplicates with mocked DB."""

    def test_returns_empty_when_no_embeddings(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_embeddings_for_search.return_value = []
            result = similar_search.find_near_duplicates()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_empty_when_one_embedding(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_embeddings_for_search.return_value = [
                (1, "/a.jpg", np.random.randn(1280).astype(np.float32).tobytes())
            ]
            result = similar_search.find_near_duplicates()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_finds_near_duplicates(self):
        dim = 1280
        v1 = np.random.randn(dim).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)
        
        v2 = v1 * 0.999 + np.random.randn(dim).astype(np.float32) * 0.001
        v2 = v2 / np.linalg.norm(v2)
        
        v3 = np.random.randn(dim).astype(np.float32)
        v3 = v3 / np.linalg.norm(v3)
        
        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_config:
                # Mock config so our duplicate_threshold is lower for testing
                mock_config.side_effect = lambda k, default: 0.95 if k == "similarity.duplicate_threshold" else default
                mock_db.get_embeddings_for_search.return_value = [
                    (1, "/v1.jpg", v1.tobytes()),
                    (2, "/v2.jpg", v2.tobytes()),
                    (3, "/v3.jpg", v3.tobytes()),
                ]
                
                result = similar_search.find_near_duplicates()
                
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["image_id_a"] == 1
        assert result[0]["image_id_b"] == 2
        assert result[0]["file_path_a"] == "/v1.jpg"
        assert result[0]["file_path_b"] == "/v2.jpg"
        assert result[0]["similarity"] >= 0.95

    def test_limit_enforced(self):
        dim = 1280
        v = np.random.randn(dim).astype(np.float32)
        v = v / np.linalg.norm(v)
        
        candidates = []
        for i in range(1, 11): 
            candidates.append((i, f"/v{i}.jpg", v.tobytes()))
            
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_embeddings_for_search.return_value = candidates
            
            result = similar_search.find_near_duplicates(limit=5)
            
        assert isinstance(result, list)
        assert len(result) == 5
        
    def test_excludes_self_pairs_and_symmetric(self):
        dim = 1280
        v = np.random.randn(dim).astype(np.float32)
        v = v / np.linalg.norm(v)
        
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_embeddings_for_search.return_value = [
                (1, "/v1.jpg", v.tobytes()),
                (2, "/v2.jpg", v.tobytes()),
            ]
            
            result = similar_search.find_near_duplicates()
            
        assert isinstance(result, list)
        assert len(result) == 1
        pair = result[0]
        assert (pair["image_id_a"] == 1 and pair["image_id_b"] == 2)

class TestFindOutliers:
    """Tests for find_outliers with mocked DB."""

    DIM = 1280

    def _make_cluster(self, n, seed=42):
        """Create n similar unit vectors (tight cluster)."""
        rng = np.random.RandomState(seed)
        base = rng.randn(self.DIM).astype(np.float32)
        base /= np.linalg.norm(base)
        vecs = []
        for _ in range(n):
            v = base + rng.randn(self.DIM).astype(np.float32) * 0.02
            v /= np.linalg.norm(v)
            vecs.append(v)
        return vecs

    def test_returns_empty_for_small_folder(self):
        """Folder below min_folder_size returns empty outliers with reason."""
        vecs = self._make_cluster(5)
        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]

        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_cfg:
                mock_cfg.side_effect = lambda k, d: {
                    "similarity.outlier_z_threshold": 2.0,
                    "similarity.outlier_k_neighbors": 3,
                    "similarity.outlier_min_folder_size": 20,
                }.get(k, d)
                mock_db.get_embeddings_for_search.return_value = candidates

                result = similar_search.find_outliers(folder_path="/photos")

        assert result["outliers"] == []
        assert result["stats"]["reason"] == "folder_too_small"

    def test_detects_injected_outlier(self):
        """A random vector injected into a tight cluster is flagged."""
        vecs = self._make_cluster(25, seed=10)
        # Inject a truly random outlier
        rng = np.random.RandomState(99)
        outlier = rng.randn(self.DIM).astype(np.float32)
        outlier /= np.linalg.norm(outlier)
        vecs.append(outlier)
        outlier_id = len(vecs)

        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]

        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_cfg:
                mock_cfg.side_effect = lambda k, d: {
                    "similarity.outlier_z_threshold": 1.5,
                    "similarity.outlier_k_neighbors": 5,
                    "similarity.outlier_min_folder_size": 10,
                }.get(k, d)
                mock_db.get_embeddings_for_search.return_value = candidates

                result = similar_search.find_outliers(folder_path="/photos")

        flagged_ids = [o["image_id"] for o in result["outliers"]]
        assert outlier_id in flagged_ids

    def test_z_threshold_controls_sensitivity(self):
        """Tighter threshold flags more images."""
        vecs = self._make_cluster(25, seed=7)
        # Add two moderately different vectors
        rng = np.random.RandomState(77)
        for _ in range(2):
            v = rng.randn(self.DIM).astype(np.float32)
            v /= np.linalg.norm(v)
            vecs.append(v)

        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]

        def run_with_z(z_val):
            with patch("modules.similar_search.db") as mock_db:
                with patch("modules.config.get_config_value") as mock_cfg:
                    mock_cfg.side_effect = lambda k, d: {
                        "similarity.outlier_z_threshold": z_val,
                        "similarity.outlier_k_neighbors": 5,
                        "similarity.outlier_min_folder_size": 10,
                    }.get(k, d)
                    mock_db.get_embeddings_for_search.return_value = candidates
                    return similar_search.find_outliers(folder_path="/photos")

        loose = run_with_z(3.0)
        tight = run_with_z(1.0)
        assert len(tight["outliers"]) >= len(loose["outliers"])

    def test_includes_explainability_fields(self):
        """Flagged outliers include nearest_neighbors, and stats has folder info."""
        vecs = self._make_cluster(25, seed=3)
        rng = np.random.RandomState(42)
        outlier = rng.randn(self.DIM).astype(np.float32)
        outlier /= np.linalg.norm(outlier)
        vecs.append(outlier)

        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]

        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_cfg:
                mock_cfg.side_effect = lambda k, d: {
                    "similarity.outlier_z_threshold": 1.5,
                    "similarity.outlier_k_neighbors": 5,
                    "similarity.outlier_min_folder_size": 10,
                }.get(k, d)
                mock_db.get_embeddings_for_search.return_value = candidates

                result = similar_search.find_outliers(folder_path="/photos")

        assert len(result["outliers"]) >= 1
        o = result["outliers"][0]
        assert "nearest_neighbors" in o
        assert len(o["nearest_neighbors"]) <= 3
        assert "similarity" in o["nearest_neighbors"][0]
        assert "outlier_score" in o
        assert "z_score" in o

        stats = result["stats"]
        assert "folder_mean" in stats
        assert "folder_std" in stats
        assert "z_threshold" in stats

    def test_limit_respected(self):
        """Results are capped at the limit parameter."""
        vecs = self._make_cluster(25, seed=5)
        # Add many outliers
        rng = np.random.RandomState(88)
        for _ in range(10):
            v = rng.randn(self.DIM).astype(np.float32)
            v /= np.linalg.norm(v)
            vecs.append(v)

        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]

        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_cfg:
                mock_cfg.side_effect = lambda k, d: {
                    "similarity.outlier_z_threshold": 1.0,
                    "similarity.outlier_k_neighbors": 5,
                    "similarity.outlier_min_folder_size": 10,
                }.get(k, d)
                mock_db.get_embeddings_for_search.return_value = candidates

                result = similar_search.find_outliers(folder_path="/photos", limit=3)

        assert len(result["outliers"]) <= 3

    def test_reports_embedding_missing(self):
        """Images with None embeddings are reported in skipped list."""
        vecs = self._make_cluster(22, seed=11)
        candidates = [(i, f"/img{i}.jpg", v.tobytes()) for i, v in enumerate(vecs, 1)]
        # Add two images with no embedding
        candidates.append((100, "/missing1.jpg", None))
        candidates.append((101, "/missing2.jpg", None))

        with patch("modules.similar_search.db") as mock_db:
            with patch("modules.config.get_config_value") as mock_cfg:
                mock_cfg.side_effect = lambda k, d: {
                    "similarity.outlier_z_threshold": 2.0,
                    "similarity.outlier_k_neighbors": 5,
                    "similarity.outlier_min_folder_size": 10,
                }.get(k, d)
                mock_db.get_embeddings_for_search.return_value = candidates

                result = similar_search.find_outliers(folder_path="/photos")

        assert len(result["skipped"]) == 2
        assert result["skipped"][0]["anomaly_class"] == "embedding_missing"
        assert result["skipped"][0]["image_id"] == 100



class TestSearchSimilarPostgresSql:
    """Postgres pgvector path must not reference dropped images.image_embedding."""

    def test_search_similar_sql_omits_legacy_column_when_absent(self):
        query_vec = np.random.randn(1280).astype(np.float32)
        mock_row = {"image_id": 2, "file_path": "/b.jpg", "similarity": 0.91}

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = [mock_row]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = False

        with patch("modules.similar_search.db") as mock_db:
            mock_db._get_db_engine.return_value = "postgres"
            mock_db.get_image_embedding.return_value = query_vec.tobytes()
            mock_db._pg_default_embedding_space_subquery_sql.return_value = "(SELECT 1)"
            mock_db._postgres_has_default_embedding_sql.return_value = "TRUE"
            mock_db._postgres_default_embedding_select_expr.return_value = "ie.embedding"
            mock_db.connection.return_value = mock_cm

            result = similar_search.search_similar_images(example_image_id=1, limit=5)

        assert isinstance(result, list)
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "i.image_embedding" not in executed_sql
        assert "ie.embedding" in executed_sql


class TestSearchByTextFilters:
    """Unit tests for text-search SQL helpers and filtered search."""

    def test_build_filter_sql_folder_ids(self):
        join_sql, where_sql, params = similar_search._build_text_search_filter_sql(
            folder_ids=[1, 2, 3],
            min_rating=None,
            color_label=None,
            keyword=None,
            captured_date=None,
        )
        assert "folder_id IN" in where_sql
        assert params == [1, 2, 3]
        assert join_sql == ""

    def test_build_filter_sql_rating_label_keyword_date(self):
        join_sql, where_sql, params = similar_search._build_text_search_filter_sql(
            folder_ids=None,
            min_rating=4,
            color_label="Green",
            keyword="bird",
            captured_date="2025-08-01",
        )
        assert "rating >=" in where_sql
        assert "label = " in where_sql
        assert "image_keywords" in where_sql
        assert "DATE(" in where_sql
        assert "image_exif ex" in join_sql
        assert params[0] == 4
        assert params[1] == "Green"
        assert "%bird%" in params[2]
        assert params[-1] == "2025-08-01"

    def test_text_search_order_relevance_only(self):
        assert similar_search._text_search_order_sql(None, None) == "e.embedding <=> %s::vector"
        assert similar_search._text_search_order_sql("similarity", "DESC") == "e.embedding <=> %s::vector"

    def test_text_search_order_secondary_capture_date(self):
        sql = similar_search._text_search_order_sql("capture_date", "DESC")
        assert "e.embedding <=> %s::vector" in sql
        assert "DESC" in sql
        assert "COALESCE" in sql

    def test_search_by_text_passes_folder_ids_to_sql(self):
        query_vec = np.random.randn(512).astype(np.float32)
        mock_row = {"image_id": 10, "file_path": "/a.nef", "similarity": 0.9}

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = [mock_row]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = False

        with patch("modules.similar_search.db") as mock_db:
            mock_db._get_db_engine.return_value = "postgres"
            mock_db._pg_embedding_table_for_dim.return_value = "image_embeddings_512"
            mock_db.connection.return_value = mock_cm
            with patch("modules.embedding_spaces.get_embedding_space_id", return_value=1):
                with patch(
                    "modules.similar_search._get_clip_text_embedding",
                    return_value=query_vec,
                ):
                    result = similar_search.search_by_text(
                        query="bird",
                        limit=5,
                        folder_ids=[7, 8],
                        min_rating=3,
                        color_label="Green",
                    )

        assert isinstance(result, list)
        assert len(result) == 1
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "folder_id IN" in executed_sql
        assert "rating >=" in executed_sql
        assert "label = " in executed_sql


@pytest.mark.ml
class TestSearchSimilarImagesIntegration:
    """Integration test: requires test DB and optional TF. Skip if no embeddings."""

    def test_search_similar_images_import_and_call(self):
        """Smoke test: call search with example_image_id only (no path)."""
        from modules import db
        db.init_db()
        # Get any image id from test DB
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT id FROM images LIMIT 1")
            row = c.fetchone()
            conn.close()
        except Exception:
            conn.close()
            pytest.skip("No images table or no rows")
        if not row:
            pytest.skip("Test DB has no images")
        image_id = row[0]
        result = similar_search.search_similar_images(example_image_id=image_id, limit=5)
        # Either list of results or error (e.g. no embeddings)
        assert isinstance(result, (list, dict))
        if isinstance(result, dict) and "error" in result:
            assert "embedding" in result["error"].lower() or "Could not" in result["error"]
        elif isinstance(result, list):
            assert all("image_id" in r and "similarity" in r for r in result)
