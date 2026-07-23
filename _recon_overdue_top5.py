"""Read-only: топ-5 просрочек ТО парка через прод-скан splinter._o3_overdue_scan (тот же, что /o3board)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import splinter

b = BridgeClient()
ov = splinter._o3_overdue_scan(b).get("overdue") or []
print(f"Всего байков с просрочками: {len(ov)}")
for o in ov[:8]:
    label = splinter._o3_bike_label(o["bike"], o["plate"])
    print(f"\n⚠️ {label} | пробег {o['current_km']} км")
    for it in o["items"]:
        lbl = splinter._MAND_LABEL.get(it["kind"], (str(it["kind"]), str(it["kind"])))[1]
        if it.get("nobase"):
            print(f"   {lbl}: ❗не делалось (порог {it['next']} км, перебор {it['over_km']} км)")
        else:
            print(f"   {lbl}: просрочено на {it['over_km']} км (last {it['last']}, next {it['next']})")
