"""Read-only: полный дамп «Календарь бронирования» → файл + карта непустых ячеек ниже строки 40."""
import urllib.request, urllib.parse, csv, io

SHEET_ID = "1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0"
url = ("https://docs.google.com/spreadsheets/d/" + SHEET_ID +
       "/gviz/tq?tqx=out:csv&sheet=" + urllib.parse.quote("Календарь бронирования"))
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    data = r.read().decode("utf-8", "replace")

with open("/root/turbobaby-manager-bot/_quote_calendar_full.csv", "w") as f:
    f.write(data)

rows = list(csv.reader(io.StringIO(data)))
print("total rows:", len(rows))


def colname(i):
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s

shown = 0
for ri, row in enumerate(rows):
    if ri < 40:
        continue
    cells = [(ci, v) for ci, v in enumerate(row) if v.strip()]
    if cells:
        parts = ["%s%d=%s" % (colname(ci), ri + 1, v.strip()[:90]) for ci, v in cells]
        print(" | ".join(parts)[:700])
        shown += 1
    if shown > 120:
        print("...cut...")
        break
