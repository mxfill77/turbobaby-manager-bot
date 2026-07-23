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
# Порядок ВАЖЕН: конкретные действия ПЕРВЫМИ, обобщённые (DOWRITE/confirmed) — ПОСЛЕДНИМИ, чтобы скрипт с
# set_fleet_oil+confirmed=true распознался как set_fleet_oil (конкретно), а не как безликое confirmed.
RED_TOKEN_HIT = {
    "set_fleet_oil": "set_fleet_oil", "set_fleet_service": "set_fleet_service",
    "add_transaction": "add_transaction", "void_last": "void_last",
    "create_booking": "create_booking", "activate_booking": "activate_booking",
    "closing_upsert": "closing_upsert", "delete_event": "delete_event",
    "DOWRITE": "DOWRITE",
    "confirmed=true": "confirmed", "confirmed=True": "confirmed", "confirmed = true": "confirmed",
    '"confirmed": true': "confirmed", '"confirmed":true': "confirmed",
}
RED_TOKENS = tuple(RED_TOKEN_HIT.keys())
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


# per-действие: (Что — таблица/операция, Последствия, Проверь). Объект (байк/клиент/сумма/док/таблица)
# доклеивается к «Что» из _detail(), если извлёкся. Тексты короткие, человеческие — НЕ дамп кода.
_ACTIONS = {
    "confirmed": ("БОЕВАЯ запись в Лист1/CRM (confirmed=true)",
                  "уйдёт в реальный учёт парка/аренд; люди пишут туда руками параллельно",
                  "та ли строка/байк и значение — откат не вернёт затёртый чужой ввод"),
    "set_fleet_oil": ("запись «ТО масло» в Лист1 Байки (колонка I)",
                      "изменит учёт ТО байка в живой таблице парка",
                      "тот ли байк и пробег — правит боевую строку парка"),
    "set_fleet_service": ("запись планового ТО в Лист1 (редуктор/ABS/возд.фильтр)",
                          "изменит график ТО байка в живой таблице парка",
                          "тот ли байк и вид ТО — правит боевую строку парка"),
    "add_transaction": ("проводка ДЕНЕГ в кассу (Money/Cashflow)",
                        "изменит денежный учёт — баланс кошелька сдвинется",
                        "та ли сумма, знак (+/−) и кошелёк — откат = ручной сторно"),
    "void_last": ("отмена последней денежной проводки (Money)",
                  "откатит последнюю проводку в кассе",
                  "точно ли ПОСЛЕДНЯЯ проводка — та, что нужно снять"),
    "create_booking": ("создание брони в CRM «клиенты»",
                       "заведёт новую строку аренды в живой CRM",
                       "тот ли клиент/байк/даты — строка попадёт в биллинг"),
    "activate_booking": ("активация брони → «В аренде» (CRM)",
                         "переведёт байк в статус аренды в живой CRM",
                         "тот ли байк/клиент — сменит боевой статус аренды"),
    "closing_upsert": ("запись закрытия аренды (CRM)",
                       "закроет аренду и зафиксирует расчёт в живой CRM",
                       "тот ли клиент/байк и суммы закрытия — правит биллинг"),
    "delete_event": ("УДАЛЕНИЕ события из истории",
                     "сотрёт запись безвозвратно",
                     "то ли событие — удаление необратимо"),
    "DOWRITE": ("скрипт помечен DOWRITE=1 — реальная запись (не dry-run)",
                "выполнит боевую запись в рабочие данные",
                "прочитай, ЧТО именно пишет скрипт — это не пробный прогон"),
    "sqlite": ("прямая запись в memory.db (UPDATE/DELETE/INSERT)",
               "изменит локальную БД правил/истории бота",
               "та ли таблица и условие WHERE — есть ли бэкап memory.db"),
}
_AMBIGUOUS = ("не распознал операцию — скрипт может писать в рабочие данные, но точную операцию не разобрал",
              "неизвестно — не могу гарантировать, что скрипт только читает",
              "глянь команду выше вручную; подтверждай, только если знаешь, что она делает")


def _find(patterns, blob):
    for p in patterns:
        m = re.search(p, blob, re.IGNORECASE)
        if m:
            g = (m.group(1) or "").strip().strip('\'"').strip()
            if g:
                return g
    return ""


def _detail(hit, blob):
    """Человеческий ОБЪЕКТ операции из argv/тела скрипта. '' если не извлеклось (тогда карточка — по действию+таблице)."""
    bits = []
    if hit in ("confirmed", "set_fleet_oil", "set_fleet_service",
               "create_booking", "activate_booking", "closing_upsert", "delete_event"):
        bike = _find([r"\bplate\s*[=:]\s*['\"]?([A-Za-z0-9][A-Za-z0-9\- ]{1,11})",
                      r"\bbike(?:_id|_no|_num|_number)?\s*[=:]\s*['\"]?([A-Za-z0-9][A-Za-z0-9\- ]{1,11})",
                      r"['\"]plate['\"]\s*:\s*['\"]([A-Za-z0-9][A-Za-z0-9\- ]{1,11})"], blob)
        if bike:
            bits.append("байк " + bike)
        client = _find([r"\bclient\s*[=:]\s*['\"]?([^\"',)]{2,30})",
                        r"['\"]client['\"]\s*:\s*['\"]([^\"']{2,30})"], blob)
        if client:
            bits.append("клиент " + client)
        val = _find([r"\b(?:mileage|km|odo|пробег|value|val)\s*[=:]\s*['\"]?(\d{2,7})"], blob)
        if val and hit in ("set_fleet_oil", "set_fleet_service"):
            bits.append("пробег " + val)
    elif hit in ("add_transaction", "void_last"):
        amount = _find([r"\bamount\s*[=:]\s*['\"]?(-?\d[\d ]{0,9})",
                        r"['\"]amount['\"]\s*:\s*['\"]?(-?\d+)",
                        r"\bsum\s*[=:]\s*['\"]?(-?\d[\d ]{0,9})"], blob)
        if amount:
            bits.append("сумма " + amount.strip())
        wallet = _find([r"\bwallet\s*[=:]\s*['\"]?([\w\- ]{2,20})",
                        r"\baccount\s*[=:]\s*['\"]?([\w\- ]{2,20})"], blob)
        if wallet:
            bits.append("кошелёк " + wallet.strip())
    elif hit == "sqlite":
        table = _find([r"UPDATE\s+['\"`]?(\w+)", r"INSERT\s+INTO\s+['\"`]?(\w+)",
                       r"DELETE\s+FROM\s+['\"`]?(\w+)"], blob)
        if table:
            bits.append("таблица " + table)
    elif hit == "DOWRITE":
        doc = _find([r"write_doc\s*\(\s*(?:name|id)\s*=\s*['\"]?([\w\-]+)"], blob)
        if doc:
            bits.append("док " + doc)
    return " — " + ", ".join(bits) if bits else ""


def _is_test_script(cmd):
    """Тестовый прогон: запускаемый .py лежит в scratchpad (/tmp/claude-*/…/scratchpad/) или несёт
    _dryrun/_test в имени. Влияет ТОЛЬКО на текст карточки (🧪-пометка первой строкой) — классификацию
    red/ambiguous/green и решение ask/defer НЕ меняет. Боевые скрипты из репо — без пометки."""
    try:
        toks = shlex.split(cmd)
    except Exception:
        toks = cmd.split()
    for t in toks:
        if not t.endswith(".py"):
            continue
        if "/tmp/claude-" in t and "/scratchpad/" in t:
            return True
        base = os.path.basename(t)
        if "_dryrun" in base or "_test" in base:
            return True
    return False


def _card(hit, blob="", test=False):
    if hit == "ambiguous" or hit not in _ACTIONS:
        what, cons, check = _AMBIGUOUS
    else:
        what, cons, check = _ACTIONS[hit]
        what += _detail(hit, blob)
    head = "🧪 ТЕСТ (dry-run, не реальная операция)\n" if test else ""
    return (head +
            "🔴 КРАСНОЕ\n"
            "Что: " + what + "\n"
            "Последствия: " + cons + "\n"
            "Проверь: " + check + " — жду твоё «да».")


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
    """→ (kind, hit, blob): kind ∈ {'red','ambiguous','green'}; hit — ключ действия; blob — текст для _detail()."""
    # 1) быстрый греп по САМОЙ команде (инлайн -c, env DOWRITE, argv)
    for tok in RED_TOKENS:
        if tok in cmd:
            return "red", RED_TOKEN_HIT[tok], cmd
    # 2) разобрать команду на токены
    try:
        toks = shlex.split(cmd)
    except Exception:
        return "ambiguous", "ambiguous", cmd   # кривое квотирование → подтверждаем на всякий
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
            return "ambiguous", "ambiguous", cmd
        if t == "-m":                                  # модуль (py_compile/pytest/json.tool — ОБРАБАТЫВАЮТ файлы-
            mod = toks[i + 1] if i + 1 < len(toks) else ""   # аргументы, НЕ исполняют их write-логику → не читаем
            if mod in _GREEN_MODULES:                  # арг-файлы: иначе `-m py_compile splinter.py` ложно ловит
                return "green", "", cmd                # токены из ИСХОДНИКА splinter.py (он их определяет)
            return "ambiguous", "ambiguous", cmd
        if t.endswith(".py"):
            body = _read_file(t, cwd)
            if body is None:
                return "ambiguous", "ambiguous", cmd   # путь есть, файл не прочли → подтверждаем
            content += body
            saw_target = True
        i += 1
    blob = cmd + "\n" + content
    for tok in RED_TOKENS:
        if tok in content:
            return "red", RED_TOKEN_HIT[tok], blob
    if "memory.db" in blob and _SQLITE_WRITE.search(blob):
        return "red", "sqlite", blob
    if not saw_target:
        return "ambiguous", "ambiguous", blob          # python без внятной цели (REPL и т.п.) → подтверждаем
    return "green", "", blob


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
        kind, hit, blob = _analyze(cmd, cwd)
    except Exception:
        kind, hit, blob = "ambiguous", "ambiguous", cmd  # любая ошибка анализа → fail-safe ask
    if kind == "green":
        _defer()                                       # читающий python → штатный allow (venv python в allow)
    card = _card(hit, blob, _is_test_script(cmd))
    _push(card)
    _ask(card)


if __name__ == "__main__":
    main()
