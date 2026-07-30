#!/usr/bin/env python3
"""cclog — ОДНОКОМАНДНАЯ запись строки-итога в cc_log из интерактивной сессии (наблюдаемость живого CC).

Зачем: интерактивный Claude Code сам в cc_log НЕ пишет → штаб (Claude-на-сайте) слеп к его
результатам (видит только Drive-журналы, не терминал). Этот скрипт даёт живому CC залогировать итог
ОДНОЙ командой, без ручного read_doc→prepend→write_doc. Обязательный ФИНАЛ каждой интерактивной
задачи — см. CLAUDE.md.

Использование (из репо; или через алиасы `cclog`/`logdone`, см. CLAUDE.md):
  venv/bin/python3 cclog.py "<текст итога>"                 → DONE YYYY-MM-DD HH:MM UTC (<канал>): <текст>
  venv/bin/python3 cclog.py PLAN "<что начал>"             → PLAN ...
  venv/bin/python3 cclog.py BLOCKED "<что мешает>"         → BLOCKED ...
  Тип (первый арг, регистр не важен): DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED. По умолчанию DONE.
  --raw  — метка (<канал>-raw) вместо (Termux); используется алиасом logdone для сырых заходов.

Формат записи (канонический, одно событие = одна строка):
  KIND YYYY-MM-DD HH:MM UTC (<канал>): текст         — обычный вызов (Claude Code / cclog)
  KIND YYYY-MM-DD HH:MM UTC (<канал>-raw): текст     — сырой ручной заход (logdone, без Claude Code)
  Метки «(Termux…)» — ЛЕГАСИ: с 28.07.2026 подпись — ФАКТИЧЕСКИЙ канал (Termux/ssh/local); старые строки не переписываются
  Миграция выполнена 28.07.2026 по решению владельца: ENTRY_RE расширен, голдены test_cclog
  пинуют канал через CCLOG_CHANNEL. Читателя меток в коде нет (проверено grep по обоим репо).
  H:MM обязательны в каждой записи. Переносы строк в тексте коллапсируются в пробел.

Дисциплина cc_log (CLAUDE.md): новые записи СВЕРХУ, ПОД врезкой-шапкой (после её ═-only-линии);
защита от затирки — пишем ТОЛЬКО если read_doc вернул ok. Зона 🟢 (журнал Brain, не рабочие таблицы).
Опция --pulse "<строка>" — заодно перезаписать KB_PULSE (та же операция, как требует CLAUDE.md).

GUARD (инцидент 17.07.2026): write_cclog() и main() проверяют length-monotonic инвариант перед
write_doc: новый контент НИКОГДА не короче старого — если короче, запись отклоняется с алертом в 328.
Единый канонический путь: write_cclog() или main() через cclog.py — НЕ прямой write_doc(name="cc_log").

РЕЕСТР СЛЕДОВ (30.07.2026, зеркало ПК-фикса «статус не должен врать»): каждая УСПЕШНАЯ запись
оставляет строку в cc_log_ledger.jsonl (status_truth.ledger_append). Раньше следа «журнал записан»
не было вовсе — и когда задача падала по таймауту, доказать выполненную работу было нечем.
"""
import sys
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
import status_truth
import task_metrics


def _channel() -> str:
    """Фактический канал, откуда пришла запись, — метка в подписи строки.

    До 28.07.2026 подпись была прибита к «Termux», хотя записи давно шли и по ssh
    с ПК, и локально с самого сервера: метка врала об источнике. Теперь считается.
    Переопределяется переменной среды CCLOG_CHANNEL (тесты пинуют ею формат).
    """
    import os
    forced = (os.environ.get("CCLOG_CHANNEL") or "").strip()
    if forced:
        return forced
    if os.environ.get("TERMUX_VERSION") or "com.termux" in (os.environ.get("PREFIX") or ""):
        return "Termux"
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        return "ssh"
    return "local"


def _is_flag(a: str) -> bool:
    """Флаг, а не текст: дефис, а следом НЕ цифра (иначе «-7000» из кассы стало бы флагом)."""
    return len(a) > 1 and a[0] == "-" and not (a[1].isdigit() or a[1] == ".")


USAGE = """cclog — строка-итог в журнал мозга (cc_log).

  cclog [ТИП] <текст>           ТИП: DONE PLAN NOTE BLOCKED WAITING SKIPPED (умолчание DONE)
  cclog [ТИП] -- <текст>        всё после -- считается текстом (даже начинающимся с дефиса)
  cclog ... --pulse "<строка>"  заодно перезаписать doc pulse
  cclog ... --raw               сырой заход (метка «<канал>-raw»)
  cclog -h | --help             эта справка — В ЖУРНАЛ НЕ ПИШЕТСЯ

Метка канала считается сама: Termux / ssh / local; переопределяется CCLOG_CHANNEL."""


# Telegram-координаты для алерта guard'а (тема 328 HQ-форума)
_HQ_CHAT_ID = -1003853365891
_DEVBOT_TOPIC = 328

TYPES = ("DONE", "PLAN", "NOTE", "BLOCKED", "WAITING", "SKIPPED")
_RELAY_KINDS = frozenset(TYPES)

# Канонический паттерн одной записи (используется тестами).
# Допускает все метки источника: Termux / Termux-raw / headless via Termux / headless via Termux-raw.
ENTRY_RE = re.compile(
    r"^(?:DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED) \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC "
    r"\((?:headless via )?[\w .+-]+\): .+$"
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


def _note_written(kind: str, entry: str, label: str = "") -> None:
    """РЕЕСТР УСПЕШНЫХ ЗАПИСЕЙ (зеркало ПК-фикса, 30.07.2026). До него следа «журнал записан»
    не существовало вовсе: cclog писал в мозг и молчал — а когда задача потом падала по таймауту,
    доказать, что работа была, оказывалось нечем. Отмечаем ТОЛЬКО после ok от моста (реестр
    обещаний, а не намерений). Под тест-прогоном боевой реестр НЕ трогаем (класс METRICS-мусора
    25.07: тестовые строки неотличимы от живых). Любой сбой реестра проглатывается внутри
    ledger_append — запись в журнал уже состоялась, след её отменить не может."""
    if task_metrics.under_test((sys.argv[0] if sys.argv else ""), os.environ, sys.modules):
        return
    status_truth.ledger_append(kind, entry, label=label)


def _make_entry(kind: str, text: str, now=None, label: str = "") -> str:
    label = label or _channel()
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


def _alert_shrink(old_len: int, new_len: int, entry_preview: str = "") -> None:
    """Алерт в 328 при срабатывании length-monotonic guard.
    Вызывается при попытке записать в cc_log контент КОРОЧЕ существующего — аномалия."""
    msg = (
        f"⚠️ cc_log SHRINK GUARD: запись отклонена\n"
        f"старый контент: {old_len} байт → новый: {new_len} байт\n"
        f"Аномалия! Проверьте cc_log вручную.\n"
        f"Превью записи: {entry_preview[:200]}"
    )
    print(msg, file=sys.stderr)
    # fail-safe: ошибки алерта не должны скрывать основную ошибку
    try:
        if os.environ.get("PRETOOL_NOPUSH") == "1" or os.environ.get("ORCH_TEST_MODE") == "1":
            return
        from notify import _send_message, _get_token
        tok = _get_token()
        if tok:
            _send_message(tok, msg, chat_id=_HQ_CHAT_ID, thread_id=_DEVBOT_TOPIC)
    except Exception as e:
        print(f"_alert_shrink: пуш не ушёл: {e}", file=sys.stderr)


def write_cclog(kind: str = "DONE", text: str = "", pulse=None,
                label: str = "", bridge=None) -> bool:
    """Канонический API записи в cc_log для программного использования.

    Единый путь: read → _make_entry → _insert_under_vrezka → length-guard → write.
    Всегда использует r.get("text","") (правильный ключ Bridge API).
    Headless-скрипты должны использовать ЭТУ функцию вместо ручного read-modify-write.

    Returns True on success, False on failure (guard/read/write).
    """
    if bridge is None:
        bridge = BridgeClient()
    r = bridge._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print(f"write_cclog: READ FAIL — не пишем (защита от затирки): {r}", file=sys.stderr)
        return False
    old = r.get("text", "")    # ПРАВИЛЬНЫЙ ключ (не "content")
    entry = _make_entry(kind, text, label=label)
    new = _insert_under_vrezka(old, entry)
    # Length-monotonic guard: новый контент никогда не должен быть короче старого
    if len(new) < len(old):
        _alert_shrink(len(old), len(new), entry_preview=entry)
        return False
    w = bridge.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print(f"write_cclog: WRITE FAIL: {w}", file=sys.stderr)
        return False
    _note_written(kind, entry, label=label or _channel())
    if pulse is not None:
        pulse_str = _ensure_pulse_hhmm(str(pulse))
        bridge.write_doc(text=pulse_str, name="pulse")
    return True


def main(argv) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(USAGE)
        return 0
    raw = "--raw" in argv
    if raw:
        argv = [a for a in argv if a != "--raw"]
    label = (_channel() + "-raw") if raw else _channel()

    pulse = None
    if "--pulse" in argv:
        p = argv.index("--pulse")
        pulse = argv[p + 1] if p + 1 < len(argv) else ""
        argv = argv[:p] + argv[p + 2:]

    kind = "DONE"
    if argv and argv[0].upper() in TYPES:
        kind = argv[0].upper()
        argv = argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        bad = [a for a in argv if _is_flag(a)]
        if bad:
            sys.stderr.write("cclog: неизвестный флаг: %s — в журнал НЕ записано\n\n%s\n"
                             % (" ".join(bad), USAGE))
            return 2
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
    old = r.get("text", "")    # ПРАВИЛЬНЫЙ ключ (не "content" — см. инцидент 17.07.2026)
    line = _make_entry(kind, text, label=label)
    new = _insert_under_vrezka(old, line)
    # Length-monotonic guard: _insert_under_vrezka всегда добавляет контент; если нет — аномалия
    if len(new) < len(old):
        _alert_shrink(len(old), len(new), entry_preview=line)
        return 1
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("cclog: WRITE FAIL:", w, file=sys.stderr)
        return 1
    _note_written(kind, line, label=label)
    print(f"cclog: OK cc_log ← {line}  (old={len(old)} → new={len(new)})")

    if pulse is not None:
        pulse = _ensure_pulse_hhmm(pulse)
        wp = c.write_doc(text=pulse, name="pulse")
        print(f"cclog: pulse ← {'OK' if wp.get('ok') else 'FAIL ' + str(wp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))