import sys, json, sqlite3
sys.path.insert(0, '/root/turbobaby-manager-bot')

conn = sqlite3.connect('/root/turbobaby-manager-bot/memory.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== conversations for topic_id=83 (XADV 750 GREY 2478) ===")
cur.execute("PRAGMA table_info(conversations)")
cols = [c[1] for c in cur.fetchall()]
print(f"Columns: {cols}")

cur.execute("SELECT * FROM conversations WHERE topic_id=83 ORDER BY rowid DESC LIMIT 10")
rows = cur.fetchall()
for row in rows:
    d = dict(row)
    content = str(d.get('content',''))[:300]
    d['content'] = content
    print(json.dumps(d, ensure_ascii=False, default=str))

print("\n=== entity_notes for 2478 ===")
cur.execute("PRAGMA table_info(entity_notes)")
cols2 = [c[1] for c in cur.fetchall()]
print(f"entity_notes columns: {cols2}")
cur.execute("SELECT * FROM entity_notes WHERE entity_key LIKE '%2478%' OR entity_key LIKE '%83%' ORDER BY rowid DESC LIMIT 10")
for row in cur.fetchall():
    print(json.dumps(dict(row), ensure_ascii=False, default=str))

print("\n=== info_pin for topic 83 ===")
cur.execute("PRAGMA table_info(info_pin)")
cols3 = [c[1] for c in cur.fetchall()]
print(f"info_pin columns: {cols3}")
cur.execute("SELECT * FROM info_pin WHERE topic_id=83 OR chat_id=-1002751134848 LIMIT 5")
for row in cur.fetchall():
    d = dict(row)
    content = str(d.get('content',''))[:200]
    d['content'] = content
    print(json.dumps(d, ensure_ascii=False, default=str))

conn.close()
