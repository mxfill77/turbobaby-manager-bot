"""Read-only разведка листа «Календарь бронирования» CRM-таблицы.
Пробуем gviz CSV-экспорт (если таблица доступна по ссылке) — только чтение, ничего не пишем."""
import urllib.request, urllib.parse, sys

SHEET_ID = "1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0"
name = sys.argv[1] if len(sys.argv) > 1 else "Календарь бронирования"
url = ("https://docs.google.com/spreadsheets/d/" + SHEET_ID +
       "/gviz/tq?tqx=out:csv&sheet=" + urllib.parse.quote(name))
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", "replace")
        print("HTTP", r.status, "| bytes:", len(data))
        lines = data.split("\n")
        print("| rows:", len(lines))
        for ln in lines[:40]:
            print(ln[:400])
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:300])
