import sqlite3

conn = sqlite3.connect('memory.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== corrections table (all, last 20) ===")
cur.execute("SELECT id, created_at, user_said, bot_did_before, bot_does_now FROM corrections ORDER BY id DESC LIMIT 20")
for r in cur.fetchall():
    if '2478' in str(dict(r)) or '24500' in str(dict(r)) or '24997' in str(dict(r)) or 'XADV' in str(dict(r)):
        print(dict(r))

print("\n=== entity_notes for 2478/XADV ===")
cur.execute("SELECT * FROM entity_notes WHERE entity_key LIKE '%2478%' OR note LIKE '%2478%' OR note LIKE '%24500%' OR note LIKE '%24997%' OR entity_key LIKE '%XADV%' ORDER BY id DESC LIMIT 20")
for r in cur.fetchall():
    print(dict(r))

print("\n=== topic_bike for 2478 ===")
cur.execute("SELECT * FROM topic_bike WHERE bike_name LIKE '%2478%'")
for r in cur.fetchall():
    print(dict(r))

print("\n=== conversations for 2478 on 15.07 (topic_id from topic_bike) ===")
cur.execute("SELECT topic_id FROM topic_bike WHERE bike_name LIKE '%2478%'")
rows = cur.fetchall()
for row in rows:
    tid = row['topic_id']
    print(f"topic_id={tid}")
    cur.execute("SELECT timestamp, user_name, role, content FROM conversations WHERE topic_id=? AND timestamp >= '2026-07-15 10:' ORDER BY id LIMIT 30", (tid,))
    for r in cur.fetchall():
        print(f"  {r['timestamp']} [{r['role']}] {r['user_name']}: {r['content'][:200]}")

print("\n=== o3_task for 2478/XADV ===")
cur.execute("SELECT * FROM o3_task WHERE bike LIKE '%2478%' OR plate LIKE '%2478%' OR bike LIKE '%XADV%' ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(dict(r))

conn.close()
