#!/usr/bin/env python3
"""Read-only аудит файлов настроек (задача 328): сырьё git status/diff/mtime/коммитов → cc_log.
Запись под врезкой (read→prepend→write, пишем только при ok) + пульс той же операцией. Зона 🟢."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

RAW = """DONE {ts} UTC (headless, задача 328): read-only аудит слоёв настроек — СЫРЬЁ без анализа.

── git status --porcelain (по трём файлам) ──
 M .claude/settings.json
(.claude/settings.local.json в выводе НЕТ; headless_settings.json чистый)

── git ls-files (что трекается) ──
.claude/settings.json
headless_settings.json
(.claude/settings.local.json НЕ трекается; git check-ignore -v:
/root/.config/git/ignore:1:**/.claude/settings.local.json	.claude/settings.local.json)

── git diff (unstaged, дословно) ──
diff --git a/.claude/settings.json b/.claude/settings.json
index 6136d77..836d2b0 100644
--- a/.claude/settings.json
+++ b/.claude/settings.json
@@ -178,9 +178,8 @@
     ],
     "ask": [
       "Bash(sqlite3 *)",
-      "Bash(clasp push*)",
-      "Bash(clasp redeploy*)",
-      "Bash(clasp deploy*)",
+      "Bash(clasp deploy)",
+      "Bash(clasp deploy *)",
       "Bash(clasp run*)",
       "Bash(systemctl stop*)",
       "Bash(sudo systemctl *)"

── git diff --cached ──
(пусто — staged-изменений нет)

── mtime + size ──
/root/turbobaby-manager-bot/.claude/settings.json | mtime=2026-07-08 12:39:35.551129124 +0000 | size=5761
/root/turbobaby-manager-bot/.claude/settings.local.json | mtime=2026-07-08 13:50:44.910983225 +0000 | size=2910
/root/turbobaby-manager-bot/headless_settings.json | mtime=2026-07-08 10:50:43.943048060 +0000 | size=1306

── последний коммит, трогавший файл ──
.claude/settings.json: b894daa 2026-07-07 10:20:14 +0000 chore(settings): фиксация применённого конфига — зелёные read-only утилиты в allow (снижение y/n 06.07) + удалён отработавший _sdrun_new_settings.json (применён cp 03.07; ревизия 07.07 чек-лист п.8)
.claude/settings.local.json: (git log пуст — файл никогда не коммитился, игнорится глобально)
headless_settings.json: de36412 2026-07-08 10:57:44 +0000 feat(ux): роль-развод permissions интерактив/headless + нотификация висящего промпта"""

PULSE = "{ts} | 🟢 | read-only аудит настроек (328): сырьё status/diff/mtime/коммитов уложено в cc_log; в репо не менял ничего | ничего не жду | детали→cc_log запись «аудит слоёв настроек {d}»"


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    entry = RAW.format(ts=ts)
    pulse = PULSE.format(ts=ts, d=ts[:10])

    c = BridgeClient()
    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print("READ FAIL — не пишу:", r)
        return 1
    old = r.get("text", "")
    lines = old.split("\n")
    idx = None
    for i, ln in enumerate(lines[:15]):
        s = ln.strip()
        if s and set(s) == {"═"}:
            idx = i
            break
    if idx is None:
        new = entry + "\n\n" + old
    else:
        head = "\n".join(lines[:idx + 1])
        rest = "\n".join(lines[idx + 1:]).lstrip("\n")
        new = head + "\n\n" + entry + "\n\n" + rest
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("WRITE FAIL:", w)
        return 1
    print(f"cc_log OK (old={len(old)} → new={len(new)})")
    wp = c.write_doc(text=pulse, name="pulse")
    print("pulse:", "OK" if wp.get("ok") else f"FAIL {wp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
