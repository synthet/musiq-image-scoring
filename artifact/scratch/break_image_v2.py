
from modules import db_postgres, config
def break_image(img_id):
    cfg = config.load_config()
    db_cfg = cfg.get("database", {}).get("postgres", {})
    conn = db_postgres.get_connection(db_cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE images SET score_general = NULL WHERE id = %s", (img_id,))
            conn.commit()
            print(f"Cleared score_general for image {img_id}")
    finally:
        conn.close()

if __name__ == "__main__":
    break_image(24957)
