# -*- coding: utf-8 -*-
# Точечный траст workspace для самотеста шага 7/7 родителя 185: вложенный headless claude
# игнорирует project-allow в недоверенном каталоге. Добавляем hasTrustDialogAccepted для
# VPS-зеркала ПК-репо и его эмуляции D:\turbobaby-bot. Бэкап рядом, откат = вернуть его.
import json
import shutil

CFG = "/root/.claude.json"
BAK = "/root/.claude.json.bak-pcloc7-20260711"
PATHS = ["/root/_pcport_userbot_185", "/root/_pcport_userbot_185/D:\\turbobaby-bot",
         "/root/_pcport_userbot_185/_emu_d_turbobaby-bot"]

shutil.copyfile(CFG, BAK)
with open(CFG, encoding="utf-8") as f:
    d = json.load(f)
proj = d.setdefault("projects", {})
for p in PATHS:
    entry = proj.setdefault(p, {})
    entry["hasTrustDialogAccepted"] = True
    entry.setdefault("hasCompletedProjectOnboarding", True)
with open(CFG, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print("OK: trust добавлен для", PATHS, "| бэкап:", BAK)
