"""Read-only: полные G-формулы «цены альт» (по одной на кривую) + строки 28-31."""
import openpyxl

P = "/root/turbobaby-manager-bot/_quote_crm_export.xlsx"
wbf = openpyxl.load_workbook(P, data_only=False)
wbv = openpyxl.load_workbook(P, data_only=True)
wsf = wbf["цены альт"]
wsv = wbv["цены альт"]

for addr in ["G3", "G4", "G5", "G10", "G20"]:
    print("=== FULL FORMULA", addr, "===")
    print(wsf[addr].value)
    print("--- value:", wsv[addr].value)

for r in range(28, 36):
    vals = []
    for col in "ABCGH":
        a = "%s%d" % (col, r)
        f = wsf[a].value
        v = wsv[a].value
        if f is None and v is None:
            continue
        vals.append(a + "=" + (repr(v)[:60] if col in "ABH" else repr(f)[:60]))
    if vals:
        print(" | ".join(vals))
