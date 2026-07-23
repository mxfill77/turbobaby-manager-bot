"""Тест 5: записать DONE в cc_log и обновить pulse через bridge_client."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

ENTRY = "DONE 2026-07-17 01:00 UTC: тест 5 — задача получена и выполнена (контрольный тест headless-контура)\n"

PULSE = "2026-07-17 01:00 UTC | 🟢 | тест 5 выполнен | ничего не жду | детали→cc_log «тест 5»"

# 1. Read cc_log
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("read cc_log FAILED:", r.get("error"), r.get("message"))
    raise SystemExit(1)

text = r.get("text", "")
lines = text.split("\n")

# Find ═-only closing line of header block
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break

if sep is None:
    print("врезка (═-строка) не найдена — не пишу")
    raise SystemExit(1)

# 2. Prepend ENTRY under the header block (after sep line)
new_text = "\n".join(lines[: sep + 1]) + "\n" + ENTRY + "\n".join(lines[sep + 1 :])

# 3. Write cc_log back
w = c.write_doc(text=new_text, name="cc_log")
print("cc_log write ok:", w.get("ok"), "| len:", len(new_text))
if not w.get("ok"):
    print("cc_log write FAILED:", w.get("error"), w.get("message"))
    raise SystemExit(1)

# 4. Write pulse
p = c.write_doc(text=PULSE, name="pulse")
print("pulse write ok:", p.get("ok"))
if not p.get("ok"):
    print("pulse write FAILED:", p.get("error"), p.get("message"))
    raise SystemExit(1)

print("done")
