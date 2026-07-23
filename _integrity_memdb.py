# read-only проверка целостности memory.db (PRAGMA, без записи)
import sqlite3

DB = "/root/turbobaby-manager-bot/memory.db"
con = sqlite3.connect("file:" + DB + "?mode=ro", uri=True)
cur = con.cursor()

ic = cur.execute("PRAGMA integrity_check").fetchall()
print("integrity_check:", ic)

fk = cur.execute("PRAGMA foreign_key_check").fetchall()
print("foreign_key_check rows:", len(fk))
if fk:
    print(fk[:10])

tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print("tables:", len(tables))
for t in tables:
    n = cur.execute("SELECT COUNT(*) FROM \"" + t + "\"").fetchone()[0]
    print("  " + t + ": " + str(n))

pc = cur.execute("PRAGMA page_count").fetchone()[0]
fl = cur.execute("PRAGMA freelist_count").fetchone()[0]
ps = cur.execute("PRAGMA page_size").fetchone()[0]
print("page_size:", ps, "page_count:", pc, "freelist:", fl)
con.close()
