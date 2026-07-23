import sqlite3, os, sys

db_path = "/root/turbobaby-manager-bot/wa_queue.db"
if not os.path.exists(db_path):
    print("NOT FOUND:", db_path)
    sys.exit(1)

size_kb = os.path.getsize(db_path) / 1024
print(f"File: {db_path} ({size_kb:.1f} KB)")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

for tbl in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
    count = cur.fetchone()[0]
    print(f"\n=== {tbl} ({count} rows) ===")
    try:
        cur.execute(f"PRAGMA table_info([{tbl}])")
        cols = [r[1] for r in cur.fetchall()]
        print(f"Columns: {cols}")
        cur.execute(f"SELECT * FROM [{tbl}] ORDER BY rowid DESC LIMIT 20")
        rows = cur.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading {tbl}: {e}")

conn.close()
