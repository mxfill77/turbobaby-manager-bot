#!/usr/bin/env python3
"""cclog — ОДНОКОМАНДНАЯ запись строки-итога в cc_log из Termux (наблюдаемость живого CC).

Зачем: интерактивный Claude Code в Termux сам в cc_log НЕ пишет → штаб (Claude-на-сайте) слеп к его
результатам (видит только Drive-журналы, не терминал). Этот скрипт даёт живому CC залогировать итог
ОДНОЙ командой, без ручного read_doc→prepend→write_doc. Обязательный ФИНАЛ каждой Termux-задачи —
см. CLAUDE.md, раздел «НАБЛЮДАЕМОСТЬ TERMUX».

Использование (из репо; или через алиасы `cclog`/`logdone`, см. CLAUDE.md):
  venv/bin/python3 cclog.py "<текст итога>"                 → DONE YYYY-MM-DD HH:MM UTC (Termux): <текст>
  venv/bin/python3 cclog.py PLAN "<что начал>"             → PLAN ...
  venv/bin/python3 cclog.py BLOCKED "<что мешает>"         → BLOCKED ...
  Тип (первый арг, регистр не важен): DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED. По умолчанию DONE.
  --raw  — метка (Termux-raw) вместо (Termux); используется алиасом logdone для сырых заходов.

Формат записи (канонический, одно событие = одна строка):
  KIND YYYY-MM-DD HH:MM UTC (Termux): текст         — обычный вызов (Claude Code / cclog)
  KIND YYYY-MM-DD HH:MM UTC (Termux-raw): текст     — сырой Termux-заход (logdone, без Claude Code)
  H:MM обязательны в каждой записи. Переносы строк в тексте коллапсируются в пробел.

Дисциплина cc_log (CLAUDE.md): новые записи СВЕРХУ, ПОД врезкой-шапкой (после её ═-only-линии);
защита от затирки — пишем ТОЛЬКО если read_doc вернул ok. Зона 🟢 (журнал Brain, не рабочие таблицы).
Опция --pulse "<строка>" — заодно перезаписать KB_PULSE (та же операция, как требует CLAUDE.md).
"""
import sys
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

TYPES = ("DONE", "PLAN", "NOTE", "BLOCKED", "WAITING", "SKIPPED")
_RELAY_KINDS = frozenset(TYPES)

# Канонический паттерн одной записи (используется тестами).
# Допускает все метки источника: Termux / Termux-raw / headless via Termux / headless via Termux-raw.
ENTRY_RE = re.compile(
    r"^(?:DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED) \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC "
    r"\((?:Termux-raw|Termux|headless via Termux-raw|headless via Termux)\): .+$"
)


def _relay_payload(text: str):
    """Класс 1+3: определить, является ли text ретрансляцией готовой cc_log-записи.
    Признак: text начинается с KIND-ключевого слова (DONE|PLAN|...).
    Возвращает payload (строка после первого «: » в теле) — или None, если не ретрансляция.
    Пустой payload → fallback на всё тело после KIND-слова.
    Обратная совместимость: нормальный текст (не начинается с KIND) — None, без изменений."""
    first_space = text.find(" ")
    if first_space <= 0:
        return None
    if text[:first_space].upper() not in _RELAY_KINDS:
        return None
    after_kind = text[first_space + 1:]
    sep = after_kind.find(": ")
    payload = after_kind[sep + 2:] if sep != -1 else after_kind
    clean = payload.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    if not clean:
        clean = after_kind.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    return clean or None


def _ensure_pulse_hhmm(pulse: str, now=None) -> str:
    """Класс 2: гарантировать Ч:ММ в пульс-строке.
    Если строка начинается с YYYY-MM-DD без H:MM — инжектировать H:MM после даты.
    Если H:MM уже есть или строка не начинается с даты — вернуть без изменений."""
    if now is None:
        now = datetime.now(timezone.utc)
    if re.match(r"^\d{4}-\d{2}-\d{2}(?!\s+\d{2}:\d{2})", pulse):
        hhmm = now.strftime("%H:%M")
        return re.sub(r"^(\d{4}-\d{2}-\d{2})", r"\1 " + hhmm, pulse, count=1)
    return pulse


def _make_entry(kind: str, text: str, now=None, label: str = "Termux") -> str:
    """Сформировать каноническую однострочную запись.
    • Нормальный текст → «KIND YYYY-MM-DD HH:MM UTC ({label}): text»
    • Ретрансляция (text начинается с KIND-слова) → «KIND ts UTC (headless via {label}): payload»
      Одна метка источника вместо вложенного «(Termux): DONE … (headless): …».
    label: «Termux» (обычный вызов) или «Termux-raw» (сырой заход через logdone).
    H:MM обязательны. Переносы строк коллапсируются в пробел."""
    if now is None:
        now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M")
    relayed = _relay_payload(text)
    if relayed is not None:
        return f"{kind} {ts} UTC (headless via {label}): {relayed}"
    clean = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    return f"{kind} {ts} UTC ({label}): {clean}"


def _insert_under_vrezka(old: str, line: str) -> str:
    """Вставить запись СВЕРХУ, но ПОД врезкой-шапкой (после первой ═-only-линии в первых 15 строках).
    Врезки нет → просто сверху. Матч по ═-only-строке (вся строка из ═), НЕ по фикс-длине (правило 25.06).
    Обратная совместимость: старые записи в old (в т.ч. без H:M) не парсятся и не изменяются."""
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
    raw = "--raw" in argv
    if raw:
        argv = [a for a in argv if a != "--raw"]
    label = "Termux-raw" if raw else "Termux"

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
        print("usage: cclog.py [DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED] <текст> [--pulse <строка>] [--raw]",
              file=sys.stderr)
        return 2

    c = BridgeClient()
    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print("cclog: READ FAIL — НЕ пишу (защита от затирки):", r, file=sys.stderr)
        return 1
    old = r.get("text", "")
    line = _make_entry(kind, text, label=label)
    new = _insert_under_vrezka(old, line)
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("cclog: WRITE FAIL:", w, file=sys.stderr)
        return 1
    print(f"cclog: OK cc_log ← {line}  (old={len(old)} → new={len(new)})")

    if pulse is not None:
        pulse = _ensure_pulse_hhmm(pulse)
        wp = c.write_doc(text=pulse, name="pulse")
        print(f"cclog: pulse ← {'OK' if wp.get('ok') else 'FAIL ' + str(wp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
