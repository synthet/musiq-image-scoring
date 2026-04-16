
from modules import db_postgres
def break_image(img_id):
    rowcount = db_postgres.execute_write("UPDATE images SET score_general = NULL WHERE id = %s", (img_id,))
    print(f"Cleared score_general for image {img_id}. Rows affected: {rowcount}")

if __name__ == "__main__":
    break_image(24957)
