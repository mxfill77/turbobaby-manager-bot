import sys, json, sqlite3
sys.path.insert(0, '/root/turbobaby-manager-bot')

conn = sqlite3.connect('/root/turbobaby-manager-bot/memory.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== topic_bike table ===")
cur.execute("PRAGMA table_info(topic_bike)")
cols = [c[1] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM topic_bike")
for row in cur.fetchall():
    d = dict(row)
    print(json.dumps(d, ensure_ascii=False, default=str))

print("\n=== corrections table ===")
cur.execute("PRAGMA table_info(corrections)")
cols = [c[1] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM corrections ORDER BY rowid DESC LIMIT 20")
for row in cur.fetchall():
    d = dict(row)
    if '2478' in str(d) or 'xadv' in str(d).lower() or '83' in str(d):
        print(json.dumps(d, ensure_ascii=False, default=str))

print("\n=== entity_notes table ===")
cur.execute("PRAGMA table_info(entity_notes)")
cols = [c[1] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM entity_notes WHERE key LIKE '%2478%' OR key LIKE '%83%' OR key LIKE '%xadv%'")
for row in cur.fetchall():
    d = dict(row)
    print(json.dumps(d, ensure_ascii=False, default=str))

print("\n=== conversations table (last 5 for topic 83) ===")
cur.execute("PRAGMA table_info(conversations)")
cols = [c[1] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM conversations WHERE topic_id=83 OR (content LIKE '%2478%') ORDER BY rowid DESC LIMIT 5")
for row in cur.fetchall():
    d = dict(row)
    content = str(d.get('content',''))[:200]
    d['content'] = content
    print(json.dumps(d, ensure_ascii=False, default=str))

conn.close()
