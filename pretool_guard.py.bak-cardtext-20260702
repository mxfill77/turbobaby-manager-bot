#!/usr/bin/env python3
"""PreToolUse hook Claude Code — закрывает СЛЕПОЕ ПЯТНО записи в Лист1/CRM/деньги.

Контекст: `venv/bin/python3 *` в allow → ЛЮБОЙ мой python-скрипт (вкл. ПИШУЩИЙ в рабочие таблицы через Bridge)
исполнялся БЫ без сигнала. Этот hook перехватывает python-команды и, если скрипт содержит WRITE-признак
(запись в Лист1/CRM, деньги, удаление), форсит permissionDecision="ask" + пушит человеческую КРАСНУЮ КАРТОЧКУ
в Telegram владельцу. Читающий python (recon/gate/tests/reports через write_doc в журналы) — не трогает (defer).

ПОЗИЦИЯ БЕЗОПАСНОСТИ: hook ТОЛЬКО ДОБАВЛЯЕТ подтверждения (никогда не выдаёт новых разрешений).
- red/неоднозначный python → "ask" (+карточка).
- зелёный python и всё прочее → exit 0 (defer к штатным allow/ask rules; venv python уже в allow).
- FAIL-SAFE: нечитаемо/непонятно → "ask" (в сторону подтверждения, НЕ пропуска).
НЕ трогает реальный гейт записи confirmed=true в Bridge (ReadFleet.js) — тот независим (третий слой защиты).
Зона 🟢 (конфиг агента; прод Splinter/таблицы не трогает). НИЧЕГО не печатает в stdout, кроме JSON-решения.
"""
import sys, os, json, re, shlex

PROJECT = "/root/turbobaby-manager-bot"

# WRITE-признаки рабочих таблиц/денег/удаления. confirmed=true — УНИВЕРСАЛЬНЫЙ (Bridge требует его на КАЖДУЮ
# запись в Лист1 → любая боевая запись его содержит). write_doc/state_set/add_event/service_upsert/o3_task_*/
# set_info_pin — ЗЕЛЁНЫЕ (Brain-журналы / Bot Data / свои таблицы), их здесь НЕТ намеренно.
RED_TOKENS = (
    "confirmed=true", "confirmed=True", "confirmed = true", '"confirmed": true', '"confirmed":true',
    "set_fleet_oil", "set_fleet_service", "add_transaction", "void_last",
    "create_booking", "activate_booking", "closing_upsert", "delete_event", "DOWRITE",
)
_GREEN_MODULES = {"py_compile", "json.tool", "pytest", "unittest", "pip", "venv", "http.server"}
_SQLITE_WRITE = re.compile(r"\b(UPDATE|DELETE\s+FROM|INSERT\s+INTO)\b", re.IGNORECASE)


def _defer():
    sys.exit(0)   # ничего не печатаем → штатный permission-flow (allow/ask rules)


def _ask(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


_WHAT = {
    "confirmed": "запись в Лист1/CRM (рабочая таблица парка/аренд)",
    "set_fleet_oil": "запись «ТО масло» в Лист1 (колонка I)",
    "set_fleet_service": "запись планового ТО в Лист1 (редуктор/ABS/возд.фильтр)",
    "add_transaction": "проводка ДЕНЕГ (касса/Money)",
    "void_last": "отмена последней денежной проводки",
    "create_booking": "создание брони в CRM «клиенты»",
    "activate_booking": "активация брони (В аренде) в CRM",
    "closing_upsert": "запись закрытия аренды (CRM)",
    "delete_event": "УДАЛЕНИЕ события из истории",
    "DOWRITE": "скрипт помечен DOWRITE=1 (реальная запись, не dry-run)",
    "sqlite": "прямая запись в memory.db (UPDATE/DELETE/INSERT)",
    "ambiguous": "python-скрипт не удалось прочитать/распознать — не могу гарантировать, что он только читает",
}


def _card(hit):
    what = _WHAT.get(hit, "запись в рабочие данные")
    return ("🔴 КРАСНОЕ · " + what +
            " · последствия: уйдёт в РЕАЛЬНЫЙ учёт (люди пишут туда параллельно, бэкап не спасёт от затирки) · "
            "проверь: та ли строка/байк/сумма, есть бэкап, не менялось ли за ~10 мин. Жду твоё «да».")


def _push(card):
    if os.environ.get("PRETOOL_NOPUSH") == "1":
        return   # тест-режим валидации хука: не спамить Telegram красными карточками
    try:
        sys.path.insert(0, PROJECT)
        from notify import notify
        notify(card)
    except Exception:
        pass   # пуш — вторичный канал; не роняем решение из-за сети/ошибки


def _is_python(cmd):
    return re.search(r"(^|\s|/)(python3?|venv/bin/python3?)(\s|$)", cmd) is not None


def _read_file(path, cwd):
    for cand in (path, os.path.join(cwd or PROJECT, path), os.path.join(PROJECT, path)):
        try:
            if os.path.isfile(cand):
                with open(cand, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(400000)
        except Exception:
            continue
    return None


def _analyze(cmd, cwd):
    """→ (kind, hit): kind ∈ {'red','ambiguous','green'}; hit — токен для карточки."""
    # 1) быстрый греп по САМОЙ команде (инлайн -c, env DOWRITE, argv)
    for tok in RED_TOKENS:
        if tok in cmd:
            return "red", ("DOWRITE" if tok == "DOWRITE" else tok.split("=")[0].split('"')[0].strip() or tok)
    # 2) разобрать команду на токены
    try:
        toks = shlex.split(cmd)
    except Exception:
        return "ambiguous", "ambiguous"   # кривое квотирование → подтверждаем на всякий
    content = ""
    i = 0
    saw_target = False
    while i < len(toks):
        t = toks[i]
        if t == "-c":                                  # инлайн-код в следующем токене
            content += (toks[i + 1] if i + 1 < len(toks) else "")
            saw_target = True
            i += 2; continue
        if t == "-":                                   # stdin → прочитать нечего
            return "ambiguous", "ambiguous"
        if t == "-m":                                  # модуль (py_compile/pytest/json.tool — ОБРАБАТЫВАЮТ файлы-
            mod = toks[i + 1] if i + 1 < len(toks) else ""   # аргументы, НЕ исполняют их write-логику → не читаем
            if mod in _GREEN_MODULES:                  # арг-файлы: иначе `-m py_compile splinter.py` ложно ловит
                return "green", ""                     # токены из ИСХОДНИКА splinter.py (он их определяет)
            return "ambiguous", "ambiguous"
        if t.endswith(".py"):
            body = _read_file(t, cwd)
            if body is None:
                return "ambiguous", "ambiguous"        # путь есть, файл не прочли → подтверждаем
            content += body
            saw_target = True
        i += 1
    blob = cmd + "\n" + content
    for tok in RED_TOKENS:
        if tok in content:
            return "red", ("DOWRITE" if tok == "DOWRITE" else tok.split("=")[0].split('"')[0].strip() or tok)
    if "memory.db" in blob and _SQLITE_WRITE.search(blob):
        return "red", "sqlite"
    if not saw_target:
        return "ambiguous", "ambiguous"                # python без внятной цели (REPL и т.п.) → подтверждаем
    return "green", ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        _defer()                                       # не распарсили вход → отдать штатным rules
    if (data.get("tool_name") or "") != "Bash":
        _defer()
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    cwd = data.get("cwd") or PROJECT
    if not cmd or not _is_python(cmd):
        _defer()                                       # не-python → allow/ask rules сами
    try:
        kind, hit = _analyze(cmd, cwd)
    except Exception:
        kind, hit = "ambiguous", "ambiguous"           # любая ошибка анализа → fail-safe ask
    if kind == "green":
        _defer()                                       # читающий python → штатный allow (venv python в allow)
    card = _card(hit)
    _push(card)
    _ask(card)


if __name__ == "__main__":
    main()
