"""Разбор пункта кураторской сводки на ОПЕРАЦИИ — чистая функция «текст → список операций».

ЗАЧЕМ (класс карточек 251, 254, 257; 05.08.2026). Сводная карточка владельцу складывала под
ОДНО «да» операции разного веса: 251 и 254 несли деплой моста ВМЕСТЕ с двумя правками живых
данных, 257 — деплой вместе с пробой правки. Владелец отказал каждой, и правильно: правило «одна
карточка = одна операция» у карточек гарда закрыто давно, а в кураторских сводках осталось. Цена
отказа — вся готовая работа пункта: по 251 и 254 её собирали заново.

ЧТО СЧИТАЕТСЯ ОПЕРАЦИЕЙ. Не «слово, похожее на действие», а НАЗВАННЫЙ ОБЪЕКТ операции того же
словаря, которым машина зовёт операции сама: имена мостовых write-действий (зеркало
`pretool_guard.RED_TOKEN_HIT` — покрытие стережёт тест, поэтому список не разойдётся молча),
головы команд разрешительного слоя (`clasp push|redeploy|deploy`, `systemctl restart|start|stop`,
`sqlite3`, `git push`) и те русские обороты, которыми КУРАТОР ДЕМОНСТРИРУЕМО пишет о них в живом
корпусе («рестарт splinter», «перезапустить демон оркестратора», «правка строки … 38982→36982»,
«понижение I16 37000→36982»).

ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО. Тип пункта («разрешение» против «принял к сведению») по-прежнему НЕ
угадывается — признака в свободной строке куратора нет, и угадывание вернуло бы класс 95/100 с
другой стороны. Модуль отвечает на ОДИН фактический вопрос: сколько РАЗНЫХ операций названо в
тексте. Решение «делить или нет» принимает демон, и делит он только при ДВУХ и более — на одной
операции поведение остаётся байт-в-байт прежним (см. `orchestrator_daemon._curator_human_place`).

ЧИСТОТА. Импорт ровно один (`re`): ни файлов, ни сети, ни моста — модуль ничего не может сделать
с миром, он только считает. Ошибка классификации поэтому стоит лишней карточки, а не операции.
"""
import re

_F = re.IGNORECASE | re.UNICODE

# Стрелка изменения числа — тем же видом, каким её пишет куратор в живом корпусе (251/254).
_RE_NUMCHANGE = re.compile(r"\d[\d\s]*\s*(?:→|->|=>)\s*\d", _F)

# --- 1. Деплой моста Apps Script -------------------------------------------------------------
# `clasp pull` НЕ ловим намеренно: чтение прода операцией не является (в 254 оно упомянуто рядом
# как предупреждение — и операцией стать не должно).
_RE_CLASP = re.compile(r"\bclasp\s+(?:push|redeploy|deploy)\b|\bredeploy\b", _F)

# --- 2. Свои сервисы --------------------------------------------------------------------------
_SERVICES = {
    "splinter": "splinter",
    "orchestrator-daemon": "orchestrator-daemon",
    "orchestrator_daemon": "orchestrator-daemon",
    "демон оркестратора": "orchestrator-daemon",
    "демона оркестратора": "orchestrator-daemon",
    "демон-оркестратор": "orchestrator-daemon",
    "wa-webhook": "wa-webhook",
}
_RE_SERVICE = re.compile(
    "|".join(re.escape(k) for k in sorted(_SERVICES, key=len, reverse=True)), _F)
# Глагол управления сервисом. Ищется ОКНОМ вокруг имени, а не строго перед ним: живой корпус даёт
# оба порядка («рестарт splinter» в 95 и «splinter не перезапущен, рестарт …» в 197).
_RE_SVC_VERB = re.compile(
    r"systemctl\s+(?:restart|start|stop)\b|перезапус\w*|перезагруз\w*|рестарт\w*|\bstart\b|\bstop\b", _F)
_SVC_WINDOW = 80

# --- 3. Мостовые write-действия (зеркало RED_TOKEN_HIT; покрытие стережёт тест) ---------------
_BRIDGE_OPS = {
    "set_fleet_oil": "запись «ТО масло» в Лист1 Байки (колонка I)",
    "set_fleet_service": "запись планового ТО в Лист1 Байки",
    "add_transaction": "проводка денег в кассу (Money/Cashflow)",
    "void_last": "отмена последней денежной проводки (Money)",
    "create_booking": "создание брони в CRM «клиенты»",
    "activate_booking": "активация брони → «В аренде» (CRM)",
    "closing_upsert": "запись закрытия аренды (CRM)",
    "delete_event": "УДАЛЕНИЕ события из истории",
    "edit_event": "правка строки события на месте (прежнее значение стирается)",
}
_RE_BRIDGE = re.compile(r"\b(" + "|".join(sorted(_BRIDGE_OPS, key=len, reverse=True)) + r")\b", _F)
# Русский оборот той же операции: «правка строки … (38982→36982)». Числовая перемена обязательна —
# без неё «правка приёмника» (карточка 100) стала бы операцией, которой там нет.
_RE_ROW_EDIT = re.compile(r"правк\w*\s+(?:строк|ячейк|записи|запись)\w*", _F)
_ROW_EDIT_WINDOW = 120

# --- 4. Живые таблицы: адресуемая ячейка с переменой числа -------------------------------------
_RE_CELL = re.compile(r"\b([A-Z]{1,2}\d{1,4})\b")          # I16, AB7 — БЕЗ IGNORECASE намеренно
_CELL_WINDOW = 40
_RE_SHEET = re.compile(r"Лист1|\bCRM\b|Зарплат\w*", _F)
_SHEET_WINDOW = 80

# --- 5. Прочие головы команд разрешительного слоя ----------------------------------------------
_RE_SQLITE = re.compile(r"\bsqlite3\b|\bmemory\.db\b", _F)
_RE_GIT_PUSH = re.compile(r"\bgit\s+push\b", _F)
_RE_ENV = re.compile(r"(?<!\w)\.env\b", _F)

_LABELS = {
    "bridge_deploy": "деплой моста Apps Script (публикация кода в прод)",
    "sheet": "запись в живую рабочую таблицу",
    "sqlite": "SQL по базе памяти",
    "git_push": "push в удалённый репозиторий",
    "env_file": "правка файла секретов .env",
}


def _add(out, pos, key, label, literal):
    out.append({"pos": pos, "key": key, "label": label, "literal": str(literal).strip()})


def occurrences(text):
    """ВСЕ вхождения операций с позициями, БЕЗ дедупа по семье — в порядке появления.

    Отделено от `operations` 06.08.2026 (класс карточек 349/357/358): позицию вхождения читает
    `curator_claim.filter_claims`, решая, стоит ли имя в позиции ЗАЯВКИ. Словарь операций от этого
    остаётся ОДИН — расходиться двум перечням негде по построению.
    Возврат: [{"pos", "key", "label", "literal"}].
    """
    t = str(text or "")
    if not t.strip():
        return []
    out = []

    m = _RE_CLASP.search(t)
    if m:
        _add(out, m.start(), "bridge_deploy", _LABELS["bridge_deploy"], m.group(0))

    for m in _RE_SERVICE.finditer(t):
        name = _SERVICES[m.group(0).lower()]
        lo, hi = max(0, m.start() - _SVC_WINDOW), min(len(t), m.end() + _SVC_WINDOW)
        if _RE_SVC_VERB.search(t[lo:hi]):
            _add(out, m.start(), f"service:{name}",
                 f"перезапуск сервиса {name}", m.group(0))

    for m in _RE_BRIDGE.finditer(t):
        key = m.group(1).lower()
        _add(out, m.start(), key, _BRIDGE_OPS[key], m.group(0))

    for m in _RE_ROW_EDIT.finditer(t):
        if _RE_NUMCHANGE.search(t[m.end():m.end() + _ROW_EDIT_WINDOW]):
            _add(out, m.start(), "edit_event", _BRIDGE_OPS["edit_event"], m.group(0))

    cells = False
    for m in _RE_CELL.finditer(t):
        if _RE_NUMCHANGE.search(t[m.end():m.end() + _CELL_WINDOW]):
            cells = True
            _add(out, m.start(), f"sheet:{m.group(1)}",
                 f"{_LABELS['sheet']} (ячейка {m.group(1)})", m.group(0))
    if not cells:
        # Таблица названа без адреса ячейки — операция всё равно названа, но грубее.
        for m in _RE_SHEET.finditer(t):
            lo, hi = max(0, m.start() - _SHEET_WINDOW), min(len(t), m.end() + _SHEET_WINDOW)
            if _RE_NUMCHANGE.search(t[lo:hi]):
                _add(out, m.start(), "sheet", _LABELS["sheet"], m.group(0))

    for rx, key in ((_RE_SQLITE, "sqlite"), (_RE_GIT_PUSH, "git_push"), (_RE_ENV, "env_file")):
        m = rx.search(t)
        if m:
            _add(out, m.start(), key, _LABELS[key], m.group(0))

    return sorted(out, key=lambda x: x["pos"])


def dedup(occs):
    """Вхождения → операции: одна семья (`key`) = одна операция, побеждает ПЕРВОЕ вхождение."""
    seen, uniq = set(), []
    for op in sorted(list(occs or []), key=lambda x: x["pos"]):
        if op["key"] in seen:
            continue
        seen.add(op["key"])
        uniq.append({"key": op["key"], "label": op["label"], "literal": op["literal"]})
    return uniq


def operations(text):
    """Текст пункта → список названных операций в порядке первого появления.

    Возврат: [{"key": <ключ семьи>, "label": <человеческое имя>, "literal": <как написал куратор>}].
    Ключ — ЕДИНИЦА РАЗВЕДЕНИЯ: одна семья = одна карточка. `clasp push` и `clasp redeploy` в одном
    пункте дают ОДНУ операцию (штатный цикл деплоя моста — это один выкат, а не два), а рестарт
    splinter и рестарт orchestrator-daemon — РАЗНЫЕ (разные объекты, разный вес).
    """
    return dedup(occurrences(text))
