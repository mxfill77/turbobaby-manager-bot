"""Read-only: сравнение KB_faq (read_doc name=faq) с docs/turbobaby_faq_v1.md — длина, заголовок, прайс."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="faq")
brain = r.get("text", "") or ""
print("brain ok=", r.get("ok"), "len(code points)=", len(brain))

with open("/root/turbobaby-manager-bot/docs/turbobaby_faq_v1.md", encoding="utf-8") as f:
    local = f.read()
print("local len(code points)=", len(local))

print("\n--- brain first 3 lines ---")
for ln in brain.split("\n")[:3]:
    print(" |", ln[:160])
print("--- local first 3 lines ---")
for ln in local.split("\n")[:3]:
    print(" |", ln[:160])

# наличие полного прайса — ищем характерные маркеры прайс-блока
markers = ["прайс", "Прайс", "PCX", "NMAX", "Fazzio", "XMAX", "1 месяц", "мес."]
print("\n--- markers ---")
for m in markers:
    print(f" {m!r}: brain={brain.count(m)} local={local.count(m)}")

print("\nidentical:", brain == local)
if brain != local:
    # первая точка расхождения
    n = min(len(brain), len(local))
    i = next((k for k in range(n) if brain[k] != local[k]), n)
    print("first diff at:", i)
    print("brain ctx:", repr(brain[max(0, i - 80):i + 80]))
    print("local ctx:", repr(local[max(0, i - 80):i + 80]))
