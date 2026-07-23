# -*- coding: utf-8 -*-
"""Read-only: кто прислал «пк: декомпозируй:» (uid из memory.db) и что ответил мозг."""
import sqlite3

conn = sqlite3.connect("file:memory.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, ts, chat_id, user_id, user_name, role, topic_id, substr(text,1,220) AS t "
    "FROM messages WHERE ts >= '2026-07-11 17:00' AND chat_id = -1003853365891 "
    "ORDER BY id LIMIT 40").fetchall()
for r in rows:
    print(dict(r))
conn.close()
