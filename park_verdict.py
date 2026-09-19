"""ИСХОД ПО РЕГИСТРУ ТО — решение, а не чтение (20.09.2026).

Отвечает на ОДИН вопрос: «по этому регистру байк в норме, просрочен или мы не знаем?» — и
отвечает ТРЕМЯ СЛОВАМИ, у каждого из которых один смысл:

    в норме       остаток до замены посчитан и он неотрицательный
    просрочено    остаток посчитан и он отрицательный
    НЕИЗВЕСТНО    посчитать было НЕ ИЗ ЧЕГО — и сказано, чего именно не хватило

ТРЕТЬЕ СЛОВО ЗДЕСЬ ГЛАВНОЕ, А НЕ ЗАПАСНОЕ. Это тот же замок против ложного зелёного, что у
[[scan_result]], [[fleet_cell]], О3 и `write_fact`: «в норме» возвращается РОВНО ОДНИМ путём —
клетка разобрана, интервал известен, пробег известен, вычитание состоялось. Всё прочее —
НЕИЗВЕСТНО, и молчаливым нулём оно не притворяется никогда. Перепись
`docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md` показала цену обратного: 12 просрочек
из 35 были фантомами ровно оттого, что «не знаем» считалось числом.

ПОЧЕМУ «ПУСТО» И «НЕ ПРОЧИТАНО» РАЗВЕДЕНЫ, ХОТЯ СЛОВО ИСХОДА У НИХ ОДНО. Слово владельцу одно —
делать с таким регистром нечего в обоих случаях, — а ПРИЧИНА разная и чинится разным: «пусто»
это факт о ЛИСТЕ (клетку никто не заполнял, лечится записью ТО), «не прочитано» это факт О НАС
(разметки клеток не прислали, лечится запросом `fleet(cells=True)` к обученному мосту). Свести их
в одну фразу значило бы второй раз потерять различие, ради которого написан [[fleet_cell]].
Поэтому исход несёт `why` из `WHY_*`, и причины перечислимы.

НОЛЬ — ЭТО НЕИЗВЕСТНО, И ЭТО СУЖДЕНИЕ, А НЕ ТРАНСПОРТ. `fleet_cell` доносит настоящий числовой
ноль как `ok` НАМЕРЕННО (он транспорт и ничего не толкует). Судит его тот, кто считает
просрочки, — то есть этот модуль: «последняя замена на нулевом пробеге» в живом парке означает
«замены не было», а не «заменили в день покупки», и выдать отсюда «просрочено на 41667 км» было
бы фантомом из той же переписи. Отрицательное число (живой случай `abs_last_km = −5000` у байка
8969) — тем же судом: регистр НЕИЗВЕСТЕН, а не «просрочен сильнее всех».

ПОРЯДОК СИЛЫ У БАЙКА — ГРОМКОЕ ВПЕРЁД: просрочено > НЕИЗВЕСТНО > в норме. Доказанная просрочка
громче незнания (её видно и с ней надо что-то делать), а незнание громче нормы (одного слепого
регистра довольно, чтобы «байк в норме» перестало быть правдой обо всём байке).

ГРАНИЦА УСТРОЙСТВОМ: импортов РОВНО ДВА, и оба — ГОТОВЫЙ ВОКАБУЛЯР: [[fleet_cell]] (какие поля
суть регистры ТО) и [[scan_result]] (какими бывают исходы чтения клетки). Ни одного своего
перечисления о тех же смыслах здесь не заводится — два словаря об одном разошлись бы молча.
Спросить мир модулю нечем: ни файлов, ни сети, ни моста, ни подпроцесса — появись у него руки,
он смог бы «дочитать» клетку сам, и тогда ответ зависел бы от того, кто спросил. Проверяется
разбором (ast) инвариантом `PARK_VERDICT_PURE`, а не докстрингом.
"""
import fleet_cell
import scan_result

# Три слова исхода. Больше слов у исхода нет.
IN_NORM = "в норме"
OVERDUE = "просрочено"
UNKNOWN = "НЕИЗВЕСТНО"

# Порядок = порядок громкости (см. шапку): что идёт раньше, то и побеждает у байка.
OUTCOMES = (OVERDUE, UNKNOWN, IN_NORM)

# Почему НЕИЗВЕСТНО. Первые четыре — о КЛЕТКЕ, последние два — о том, чем её мерить.
WHY_UNREAD = "не прочитано"          # разметки клеток нет: факт О НАС
WHY_EMPTY = "пусто"                  # клетка не заполнена: факт О ЛИСТЕ
WHY_TEXT = "не число"                # содержимое есть, числом не стало
WHY_ZERO = "ноль"                    # «замены не было», а не «заменили на нуле»
WHY_NEGATIVE = "отрицательное число"  # пробег назад не идёт
WHY_NO_INTERVAL = "интервал не задан"  # вид у этого байка не трекается (gear на мото)
WHY_NO_ODO = "пробег неизвестен"     # мерить не от чего

WHYS = (WHY_UNREAD, WHY_EMPTY, WHY_TEXT, WHY_ZERO, WHY_NEGATIVE,
        WHY_NO_INTERVAL, WHY_NO_ODO)

# Четыре регистра ТО — СПИСОК ГОТОВЫЙ, из контракта клетки (кол. I/J/K/L Лист1).
REGISTERS = fleet_cell.SERVICE_FIELDS

_SUFFIX = "_last_km"


def kind_of(field):
    """Поле строки парка → вид ТО (`oil_last_km` → `oil`). Вывод, а не второй словарь."""
    f = str(field or "")
    return f[: -len(_SUFFIX)] if f.endswith(_SUFFIX) else f


def _int_or_none(x):
    """Целое или None. Логическое числом не считаем (True в JSON — это `true`, не 1 км)."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _unknown(field, why, detail="", last_km=None, interval=None):
    return {
        "register": field,
        "kind": kind_of(field),
        "outcome": UNKNOWN,
        "why": why,
        "detail": str(detail or ""),
        "last_km": last_km,
        "interval": interval,
        "due_at_km": None,
        "remaining_km": None,
        "overdue_km": None,
    }


def register(field, cell, cur_km, interval):
    """Исход ОДНОГО регистра.

    `field`    — поле строки парка (`oil_last_km` …), из `REGISTERS`;
    `cell`     — `ScanResult` от `fleet_cell.read` (исход клетки, а не голое число);
    `cur_km`   — текущий пробег байка (число либо None/'' — «не знаем»);
    `interval` — интервал вида для этого байка (число либо None — «вид не трекается»).

    Порядок разбора — ИСТОЧНИК → ПРАВИЛО → МИР: сперва «что вообще лежало в клетке», потом «чем
    это мерить», потом «от чего отсчитывать». Первое недостающее и называется причиной: чинить
    всё равно придётся его."""
    # (1) ИСТОЧНИК: что лежало в клетке. Исходы берутся готовыми у contract'а клетки.
    outcome = getattr(cell, "outcome", None)
    detail = getattr(cell, "detail", "") or ""
    if outcome is None:
        return _unknown(field, WHY_UNREAD, "исход клетки не получен — контракт клетки не звали")
    if outcome == scan_result.OUTCOME_UNREADABLE:
        return _unknown(field, WHY_UNREAD, detail)
    if outcome == scan_result.OUTCOME_EMPTY:
        return _unknown(field, WHY_EMPTY, detail)
    if outcome != scan_result.OUTCOME_OK:
        # Осмотр БЫЛ, содержимое ЕСТЬ, числом оно не стало (`mismatch` контракта клетки).
        return _unknown(field, WHY_TEXT, detail)

    last = _int_or_none(getattr(cell, "payload", None))
    if last is None:
        return _unknown(field, WHY_TEXT, "разобранное значение клетки не целое число")
    if last == 0:
        return _unknown(field, WHY_ZERO, detail, last_km=last, interval=_int_or_none(interval))
    if last < 0:
        return _unknown(field, WHY_NEGATIVE, detail, last_km=last,
                        interval=_int_or_none(interval))

    # (2) ПРАВИЛО: чем мерить.
    iv = _int_or_none(interval)
    if iv is None or iv <= 0:
        return _unknown(field, WHY_NO_INTERVAL, detail, last_km=last, interval=iv)

    # (3) МИР: от чего отсчитывать.
    cur = _int_or_none(cur_km)
    if cur is None or cur <= 0:
        return _unknown(field, WHY_NO_ODO, detail, last_km=last, interval=iv)

    due = last + iv
    remaining = due - cur
    return {
        "register": field,
        "kind": kind_of(field),
        "outcome": IN_NORM if remaining >= 0 else OVERDUE,
        "why": "",
        "detail": detail,
        "last_km": last,
        "interval": iv,
        "due_at_km": due,
        "remaining_km": remaining if remaining >= 0 else None,
        "overdue_km": None if remaining >= 0 else -remaining,
    }


def loudest(outcomes):
    """Самый громкий исход из набора (см. порядок силы в шапке). Пусто → НЕИЗВЕСТНО."""
    seen = set(outcomes or ())
    for o in OUTCOMES:
        if o in seen:
            return o
    return UNKNOWN


def bike(name, cells, cur_km, intervals):
    """Исход БАЙКА: четыре регистра + сводное слово.

    `cells`     — {поле: ScanResult} по всем `REGISTERS`;
    `intervals` — {вид: интервал или None}.

    Регистра нет в `cells` вовсе → он НЕИЗВЕСТЕН с причиной «не прочитано»: отсутствие ответа
    ответом не считается (тот же знаменатель у нуля, что у `scan_result`)."""
    regs = []
    for field in REGISTERS:
        cell = (cells or {}).get(field)
        if cell is None:
            regs.append(_unknown(field, WHY_UNREAD, "строка парка не несёт этой клетки"))
            continue
        regs.append(register(field, cell, cur_km,
                             (intervals or {}).get(kind_of(field))))
    return {
        "bike": str(name or ""),
        "current_km": _int_or_none(cur_km),
        "outcome": loudest(r["outcome"] for r in regs),
        "registers": regs,
        "unknown_by_why": tally(regs),
    }


def tally(registers):
    """Сколько регистров НЕИЗВЕСТНЫ и по какой причине — раздельно, в порядке `WHYS`."""
    out = {}
    for r in registers or ():
        if r.get("outcome") == UNKNOWN:
            why = r.get("why") or WHY_UNREAD
            out[why] = out.get(why, 0) + 1
    return {w: out[w] for w in WHYS if w in out}


def park_tally(bikes):
    """Сводка по парку: сколько байков видно и у скольких исход какой."""
    by = {o: 0 for o in OUTCOMES}
    whys = {}
    for b in bikes or ():
        by[b.get("outcome", UNKNOWN)] = by.get(b.get("outcome", UNKNOWN), 0) + 1
        for why, n in (b.get("unknown_by_why") or {}).items():
            whys[why] = whys.get(why, 0) + n
    return {
        "bikes_seen": len(bikes or ()),
        "by_outcome": by,
        "unknown_registers_by_why": {w: whys[w] for w in WHYS if w in whys},
    }
