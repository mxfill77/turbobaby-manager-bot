import sqlite3
import json

conn = sqlite3.connect('memory.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)

for t in tables:
    cur.execute(f"SELECT * FROM {t} WHERE CAST(rowid AS TEXT) IN (SELECT rowid FROM {t} WHERE 1=1 LIMIT 0) OR 1=1 LIMIT 0")
    cols = [d[0] for d in cur.description]
    print(f'\nTable {t} columns: {cols}')

# Look for events/service records for bike 2478 on 15.07
for t in tables:
    cur.execute(f"SELECT * FROM {t} LIMIT 1")
    if not cur.fetchone():
        continue
    cur.execute(f"SELECT * FROM {t} LIMIT 1")
    row = cur.fetchone()
    if row:
        cols = list(row.keys())
        text_cols = [c for c in cols if 'text' in c.lower() or 'content' in c.lower() or 'data' in c.lower() or 'value' in c.lower() or 'msg' in c.lower() or 'bike' in c.lower() or 'note' in c.lower()]
        print(f'Table {t}: potential text cols: {text_cols}')

conn.close()
