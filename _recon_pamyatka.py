"""Read-only разведка CRM 1sL-rw0k: ищем лист «памятка»/«Цены»/low-season, картируем занятость."""
import urllib.request

SHEET_ID = "1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0"
url = "https://docs.google.com/spreadsheets/d/" + SHEET_ID + "/export?format=xlsx"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
print("downloaded bytes:", len(data))
with open("/root/turbobaby-manager-bot/_recon_crm.xlsx", "wb") as f:
    f.write(data)

import openpyxl
wb = openpyxl.load_workbook("/root/turbobaby-manager-bot/_recon_crm.xlsx", data_only=True)
print("== ВСЕ ЛИСТЫ ==")
for n in wb.sheetnames:
    ws = wb[n]
    print("  [%s]  dims=%s  max_row=%s max_col=%s" % (n, ws.dimensions, ws.max_row, ws.max_column))


def colname(i):
    s = ""
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


kw = ["памятк", "цен", "price", "low", "season", "сезон", "тариф", "прайс", "аренд"]
cands = [n for n in wb.sheetnames if any(k in n.lower() for k in kw)]
print("\n== КАНДИДАТЫ по имени:", cands)

# на всякий: покажем ВСЕ листы кратко, чтобы вручную выбрать
for n in wb.sheetnames:
    ws = wb[n]
    # карта занятых колонок: для первых 60 строк какие колонки непусты
    colcount = {}
    last_row_with_data = 0
    for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200)), start=1):
        for c in row:
            if c.value not in (None, ""):
                colcount[c.column] = colcount.get(c.column, 0) + 1
                last_row_with_data = ri
    occ = sorted(colcount.keys())
    occ_str = ",".join("%s(%d)" % (colname(c), colcount[c]) for c in occ)
    print("\n--- ЛИСТ [%s] --- last_data_row=%d занятые колонки: %s" % (n, last_row_with_data, occ_str))
