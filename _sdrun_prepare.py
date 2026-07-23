"""Готовит НОВЫЙ settings.json с двумя УЗКИМИ allow-паттернами deferred-рестарта.
НЕ пишет в .claude/settings.json (гейт headless!) — кладёт готовый файл в корень репо,
применение = одна команда cp из Termux (руками Филиппа). Зона 🟢 (read + файл в репо)."""
import json

SRC = "/root/turbobaby-manager-bot/.claude/settings.json"
DST = "/root/turbobaby-manager-bot/_sdrun_new_settings.json"

NARROW = [
    "Bash(systemd-run --on-active=* systemctl restart orchestrator-daemon)",
    "Bash(systemd-run --on-active=* systemctl restart splinter)",
]

with open(SRC) as f:
    raw = f.read()
data = json.loads(raw)
allow = data["permissions"]["allow"]
print("json ok; allow entries:", len(allow))

present = [p for p in NARROW if p in allow]
print("уже в allow:", present or "нет")

anchor = "Bash(systemctl restart orchestrator-daemon)"
idx = allow.index(anchor) + 1
for i, p in enumerate([p for p in NARROW if p not in allow]):
    allow.insert(idx + i, p)

with open(DST, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

check = json.load(open(DST))
assert all(p in check["permissions"]["allow"] for p in NARROW)
assert len(check["permissions"]["allow"]) == len(json.loads(raw)["permissions"]["allow"]) + len(NARROW) - len(present)
print("OK: подготовлен", DST, "| allow:", len(check["permissions"]["allow"]))
