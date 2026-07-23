# Симуляция строк 154-160 tests/test_settings_allowlist.py на checkout БЕЗ
# .claude/settings.local.json (гитигнорен -> в свежем/чужом клоне отсутствует).
import json, os
ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
LOCAL = os.path.join(ROOT, ".claude", "settings.local.json.MISSING-SIM")
try:
    live_proj = json.load(open(SETTINGS))["permissions"]
    live_local = json.load(open(LOCAL))["permissions"]
    print("оба файла прочитаны — падения нет")
except FileNotFoundError as e:
    print("ВОСПРОИЗВЕДЕНО: FileNotFoundError ->", e)
    print("тест умирает ДО WARN-fallback на _claspsplit_new_settings.local.json -> гейт 1 красный")
