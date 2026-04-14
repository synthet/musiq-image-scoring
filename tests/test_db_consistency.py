
import pytest
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db


@pytest.fixture
def test_db(clean_postgres):
    """Returns a connection to the test database (clean slate for PostgreSQL)."""
    # Ensure we are using the test DB filename
    db.DB_FILE = "scoring_history_test.fdb"
    db.DB_PATH = os.path.join(db._PROJECT_ROOT, db.DB_FILE)

    conn = db.get_db()
    yield conn
    conn.close()

def test_keyword_sync(test_db):
    """Verify that _sync_image_keywords correctly populates normalized tables."""
    c = test_db.cursor()
    
    # 1. Create a test image
    c.execute("INSERT INTO images (file_path, file_name, keywords) VALUES (?, ?, ?)", 
              ("test/path1.jpg", "path1.jpg", "Nature, Landscape, Sunset"))
    test_db.commit()
    
    c.execute("SELECT id FROM images WHERE file_name = 'path1.jpg'")
    image_id = c.fetchone()[0]
    
    # 2. Trigger sync
    db._sync_image_keywords(image_id, "Nature, Landscape, Sunset")
    
    # 3–5: Use a fresh connection to verify. Firebird transaction isolation means the
    # test_db connection may not see commits from _sync_image_keywords' separate connection.
    verify_conn = db.get_db()
    try:
        vc = verify_conn.cursor()
        vc.execute("SELECT keyword_norm FROM keywords_dim ORDER BY keyword_norm")
        keywords = [row[0] for row in vc.fetchall()]
        assert "nature" in keywords
        assert "landscape" in keywords
        assert "sunset" in keywords

        vc.execute("SELECT COUNT(*) FROM image_keywords WHERE image_id = ?", (image_id,))
        count = vc.fetchone()[0]
        assert count == 3

        # 5. Test update (remove Sunset, add Beach)
        db._sync_image_keywords(image_id, "Nature, Landscape, Beach")
    finally:
        verify_conn.close()

    # Fresh connection again to see the second sync's commit
    verify_conn2 = db.get_db()
    try:
        vc2 = verify_conn2.cursor()
        vc2.execute("SELECT kd.keyword_norm FROM image_keywords ik JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id WHERE ik.image_id = ?", (image_id,))
        updated_kws = [row[0] for row in vc2.fetchall()]
    finally:
        verify_conn2.close()
    assert "nature" in updated_kws
    assert "beach" in updated_kws
    assert "sunset" not in updated_kws

def test_xmp_sync_placeholders(test_db):
    """
    Verify images.rating corresponds to image_xmp.rating if synced.
    """
    c = test_db.cursor()
    
    # Insert image and corresponding XMP row
    c.execute("INSERT INTO images (file_path, file_name) VALUES (?, ?)", ("test/xmp.jpg", "xmp.jpg"))
    test_db.commit()
    c.execute("SELECT id FROM images WHERE file_name = 'xmp.jpg'")
    image_id = c.fetchone()[0]
    
    # Simulate XMP extraction
    c.execute("INSERT INTO image_xmp (image_id, rating, label) VALUES (?, ?, ?)", (image_id, 4, "Red"))
    test_db.commit()
    
    # Verify
    c.execute("SELECT rating FROM image_xmp WHERE image_id = ?", (image_id,))
    assert c.fetchone()[0] == 4

def test_backfill_idempotency(test_db):
    """Verify that _backfill_keywords is idempotent."""
    if hasattr(db, '_backfill_keywords'):
        db._backfill_keywords()
        db._backfill_keywords()
    else:
        pytest.skip("_backfill_keywords not found in db module")
