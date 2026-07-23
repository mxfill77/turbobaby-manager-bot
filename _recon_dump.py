"""Read-only: полный дамп листов «цены альт» и «памятка» (значения + формулы шапки)."""
import openpyxl

def colname(i):
    s = ""
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s

wbv = openpyxl.load_workbook("/root/turbobaby-manager-bot/_recon_crm.xlsx", data_only=True)
wbf = openpyxl.load_workbook("/root/turbobaby-manager-bot/_recon_crm.xlsx", data_only=False)

for name in ["цены альт", "памятка"]:
    ws = wbv[name]
    wf = wbf[name]
    print("\n############### ЛИСТ [%s] dims=%s ###############" % (name, ws.dimensions))
    for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 45)), start=1):
        cells = []
        for c in row:
            if c.value not in (None, ""):
                cells.append("%s%d=%r" % (colname(c.column), ri, c.value))
        if cells:
            print(" | ".join(cells)[:900])
    # формулы (если есть) в первых 32 строках, 12 колонок
    print("--- ФОРМУЛЫ [%s] (только ячейки-формулы) ---" % name)
    for ri in range(1, 33):
        for ci in range(1, 21):
            c = wf.cell(row=ri, column=ci)
            v = c.value
            if isinstance(v, str) and v.startswith("="):
                print("  %s%d = %s" % (colname(ci), ri, v[:120]))
