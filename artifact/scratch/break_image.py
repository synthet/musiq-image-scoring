
from modules import db
msg = db.execute_sql("UPDATE images SET score_general = NULL WHERE id = 24957")
print(f"Update result: {msg}")
