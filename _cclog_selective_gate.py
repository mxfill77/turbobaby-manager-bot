#!/usr/bin/env python3
import sys, os
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

bc = BridgeClient(timeout=30)

# Read cc_log
r = bc._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log failed: {r}"
body = r.get("text", "")

entry = (
    "DONE 2026-07-14 UTC: ускорение цепей ч.2 — селективный гейт промежуточных шагов. "
    "Реализовано в коммите d288947 (13.07.2026): gate.py — _step_selective(), _changed_py_files(), "
    "_affected_test_files(), run_selective_tests(); orchestrator_daemon.run_task — "
    "GATE_STEP_SELECTIVE=1 в child_env промежуточного шага (i < N). "
    "tests/test_gate_selective.py — 34 проверки. Гейт 91/91 ✅. "
    "Пометка «гейт селективный (N тестов)» / «гейт полный» / «fail-safe» в выводе. "
    "Хвосты: нет."
)

# Insert under header (find first === line, insert after it)
lines = body.split("\n")
insert_idx = 0
for i, l in enumerate(lines):
    if set(l.strip()) == {"═"} and l.strip():
        insert_idx = i + 1
        break

lines.insert(insert_idx, entry)
new_body = "\n".join(lines)

w = bc.write_doc(text=new_body, name="cc_log")
assert w.get("ok"), f"write cc_log failed: {w}"
print("cc_log written")

# Pulse
pulse = (
    "2026-07-14 UTC | 🟢 | ускорение цепей ч.2 — селективный гейт реализован (d288947); "
    "гейт 91/91 ✅ | ничего не жду | детали→cc_log «ускорение цепей ч.2 14.07»"
)
wp = bc.write_doc(text=pulse, name="pulse")
assert wp.get("ok"), f"write pulse failed: {wp}"
print("pulse written")
print("done")
