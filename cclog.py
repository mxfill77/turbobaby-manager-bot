#!/usr/bin/env python3
"""cclog — ОДНОКОМАНДНАЯ запись строки-итога в cc_log из Termux (наблюдаемость живого CC).

Зачем: интерактивный Claude Code в Termux сам в cc_log НЕ пишет → штаб (Claude-на-сайте) слеп к его
результатам (видит только Drive-журналы, не терминал). Этот скрипт даёт живому CC залогировать итог
ОДНОЙ командой, без ручного read_doc→prepend→write_doc. Обязательный ФИНАЛ каждой Termux-задачи —
см. CLAUDE.md, раздел «НАБЛЮДАЕМОСТЬ TERMUX».

Использование (из репо; или через алиас `cclog`, см. CLAUDE.md):
  venv/bin/python3 cclog.py "<текст итога>"                 → DONE <UTC> UTC (Termux): <текст>
  venv/bin/python3 cclog.py PLAN "<что начал>"             → PLAN ...
  venv/bin/python3 cclog.py BLOCKED "<что мешает>"         → BLOCKED ...
  Тип (первый арг, регистр не важен): DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED. По умолчанию DONE.

Дисциплина cc_log (CLAUDE.md): новые записи СВЕРХУ, ПОД врезкой-шапкой (после её ═-only-линии);
защита от затирки — пишем ТОЛЬКО если read_doc вернул ok. Зона 🟢 (журнал Brain, не рабочие таблицы).
Опция --pulse "<строка>" — заодно перезаписать KB_PULSE (та же операция, как требует CLAUDE.md).
"""
import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

TYPES = ("DONE", "PLAN", "NOTE", "BLOCKED", "WAITING", "SKIPPED")


def _insert_under_vrezka(old: str, line: str) -> str:
    """Вставить запись СВЕРХУ, но ПОД врезкой-шапкой (после первой ═-only-линии в первых 15 строках).
    Врезки нет → просто сверху. Матч по ═-only-строке (вся строка из ═), НЕ по фикс-длине (правило 25.06)."""
    lines = old.split("\n")
    idx = None
    for i, ln in enumerate(lines[:15]):
        s = ln.strip()
        if s and set(s) == {"═"}:
            idx = i
            break
    if idx is None:
        return line + "\n\n" + old
    head = "\n".join(lines[:idx + 1])
    rest = "\n".join(lines[idx + 1:]).lstrip("\n")
    return head + "\n\n" + line + "\n\n" + rest


def main(argv) -> int:
    pulse = None
    if "--pulse" in argv:
        p = argv.index("--pulse")
        pulse = argv[p + 1] if p + 1 < len(argv) else ""
        argv = argv[:p] + argv[p + 2:]

    kind = "DONE"
    if argv and argv[0].upper() in TYPES:
        kind = argv[0].upper()
        argv = argv[1:]
    text = " ".join(argv).strip()
    if not text:
        print("usage: cclog.py [DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED] <текст> [--pulse <строка>]",
              file=sys.stderr)
        return 2

    c = BridgeClient()
    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print("cclog: READ FAIL — НЕ пишу (защита от затирки):", r, file=sys.stderr)
        return 1
    old = r.get("text", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"{kind} {ts} UTC (Termux): {text}"
    new = _insert_under_vrezka(old, line)
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("cclog: WRITE FAIL:", w, file=sys.stderr)
        return 1
    print(f"cclog: OK cc_log ← {line}  (old={len(old)} → new={len(new)})")

    if pulse is not None:
        wp = c.write_doc(text=pulse, name="pulse")
        print(f"cclog: pulse ← {'OK' if wp.get('ok') else 'FAIL ' + str(wp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
