import sqlite3

db = "/root/turbobaby-manager-bot/wa_queue.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for tname in tables:
    print(f"\n=== Table: {tname} ===")
    cur.execute(f"PRAGMA table_info({tname})")
    cols = [r[1] for r in cur.fetchall()]
    print("Columns:", cols)
    cur.execute(f"SELECT * FROM {tname} ORDER BY rowid DESC LIMIT 5")
    rows = cur.fetchall()
    if not rows:
        print("(empty)")
    for row in rows:
        print(dict(zip(cols, row)))

conn.close()
