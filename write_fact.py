"""СИНК ЗЕРКАЛА ИДЁТ ПО ПЕРЕЧИТАННОМУ ФАКТУ, А НЕ ПО ФЛАГУ РАСПИСКИ (13.08.2026).

КЛАСС. Писчее плечо моста делает РОВНО одну отправку и пересылок не имеет (`bridge_client.
_durable_request`, класс 02.08): вторая отправка положила бы вторую запись. Поэтому отказ
расписки честно отдаёт `outcome='unknown'` и ТРЕБОВАНИЕ перечитать факт — «повторять запрос
вслепую нельзя». Требование адресовано вызывающему, и у демона оно выполнено дважды
(`_claim_task_verified`, `_enqueue_reliable`), а на пути ТО — нет: решение о синке зеркала
принимал ФЛАГ `r.get("ok")`, то есть расписка, а не мир. Расписка не пришла → флаг ложный →
величина в Лист1 стоит, а строки зеркала «обслуживание» нет вовсе.

ЗАМЕР (splinter.log, 01.06–13.08, 73 суток; строки «ТО фаза2 запись по «да»»): записей ТО по
«да» — 12, отказов писчего плеча — 2, ОБА `receipt_unknown`, оба 13.08:
`written=[] failed=[('abs','receipt_unknown')] odo=37015` (байк 4957) и то же на `odo=20747`
(байк 4724). Иных кодов отказа у этого плеча за всё наблюдение не было НИ РАЗУ. Перечитывание
живым контрактом клетки 13.08: обе величины СТОЯТ в Лист1 кол.K, исход `ok`, значение совпало —
значит после правки доехали бы 2 из 2, а по флагу не доехало 2 из 12.

ЦЕНА НАЗВАНА ЧИСЛОМ. Перечитывание идёт ТОЛЬКО после неудачи записи, а не после каждой записи:
2 события за 11 суток окна = **0.18 лишнего чтения в сутки** (одно `fleet(cells=1)` на событие),
за все 73 суток — 0.027. Здоровый путь не платит НИ ОДНОГО лишнего обращения к больному мосту —
это проверяется счётчиком вызовов в тесте, а не обещанием.

ТРИ ИСХОДА, А НЕ ДВА — ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО (тот же, что у О3 и у контракта клетки):
    ЛЕГЛО       клетка прочитана и в ней РОВНО наша величина   → синк идёт
    НЕ ЛЕГЛО    клетка прочитана, нашей величины в ней нет      → синка нет, и это ЗВУЧИТ
    НЕИЗВЕСТНО  клетку прочитать не удалось                     → синка нет, записанным НЕ считаем
«Неизвестно» — отдельное слово, а не вежливое «легло»: молчание опаснее лишней проверки. Сюда
уходит ВСЁ, что не есть доказанное равенство, — мост не ответил, строки парка нет, номер
неоднозначен, разметки клеток нет (старый деплой), в клетке не число, контракт отдал `ok` без
числа. Признать записанным то, что мы не прочитали, значит вернуть ровно тот дефект, ради
которого модуль написан, только с другой стороны.

«НЕ ЛЕГЛО» НЕ УТВЕРЖДАЕТ БОЛЬШЕГО, ЧЕМ ЗНАЕТ. Клетка с ДРУГИМ числом означает «нашей величины
там нет» — этого достаточно, чтобы синк не шёл (зеркало получило бы величину, которой в Лист1
нет), и фраза называет ОБА числа, а не объявляет, что запись не исполнилась: её мог перекрыть
сосед. Пустая клетка — тот же исход по той же причине: величины нет.

ПОЧЕМУ ПЕРЕЧИТЫВАЕМ И ПРИ ИНЫХ НЕУДАЧАХ, А НЕ ТОЛЬКО ПРИ ОТКАЗЕ РАСПИСКИ. Форма взята у
`_claim_task_verified` («брать, не изобретать»): там verify не дёргают на СЕМАНТИЧЕСКИХ отказах
(`not_found`/`wrong_lane`/`no_id`) — на них исход ОПРЕДЕЛЁН, мост ответил сам. Здесь то же:
`SETTLED_ERRORS` — отказы, которые мост ВЫНЕС САМ (проверил номер, подтверждение, убывание
пробега), плюс `card_deadline`, при котором запрос не уходил вовсе. Всё прочее — молчание
транспорта: расписка, таймаут, оборванный запрос, незнакомый код. Направление сомнения тут
ДЕШЁВОЕ и потому открытое: лишнее перечитывание стоит одного чтения (замер: 0 случаев за
73 суток вне расписки), а НЕперечитывание стоит молча потерянной строки зеркала.

ГРАНИЦА УСТРОЙСТВОМ: у модуля РОВНО ОДИН импорт — контракт `scan_result` (у которого импортов
ноль). Ему нечем ни читать, ни писать, ни ходить в сеть: клетку приносит вызывающий, модуль
только судит принесённое. Проверяется разбором (ast) инвариантом `WRITE_FACT_PURE`, а не
докстрингом. Руки — `splinter._sp_fact_after_write`. Тесты `tests/test_write_fact.py`.
"""
from scan_result import OUTCOME_EMPTY

#: Исходы перечитывания. Три, и третий — не запасной.
STATE_LANDED = "landed"
STATE_ABSENT = "absent"
STATE_UNKNOWN = "unknown"

#: Вид работ ТО → поле строки парка (оно же колонка Лист1, см. `fleet_cell.FIELD_COL`).
#: Зеркало `splinter._SP_COL_KINDS` и `ReadFleet.js` (oil→I, gear→J, abs→K, airfilter→L).
FIELD_BY_KIND = {
    "oil": "oil_last_km",
    "gear": "gear_last_km",
    "abs": "abs_last_km",
    "airfilter": "airfilter_last_km",
}

#: Отказ расписки — тот самый контракт `bridge_client._receipt_unknown`.
RECEIPT_UNKNOWN = "receipt_unknown"
OUTCOME_UNKNOWN = "unknown"

#: Отказы, которые мост ВЫНЕС САМ: исход определён, перечитывать нечего.
#: Зеркало докстрингов `set_fleet_oil` / `set_fleet_service` + `card_deadline` (запрос не уходил).
SETTLED_ERRORS = frozenset((
    "missing_number", "bad_oil_km", "bad_km", "bad_kind", "not_confirmed", "not_found",
    "ambiguous", "oil_decreasing", "km_decreasing", "write_failed", "fix_incomplete",
    "oil_drop_needs_trusted", "audit_failed", "card_deadline",
    # верхняя граница пробега (`odo_ceiling.ERR`): мост не звали вовсе — исход определён,
    # перечитывать нечего, запись не начиналась.
    "odo_ceiling",
))


class Fact:
    """Что мир говорит о нашей записи. Читать `.landed`, произносить `.say()`."""

    __slots__ = ("state", "expected", "found", "detail")

    def __init__(self, state, expected, found=None, detail=""):
        self.state = state
        self.expected = expected
        self.found = found
        self.detail = str(detail or "")

    @property
    def landed(self):
        """ТОЛЬКО доказанное равенство. «Неизвестно» сюда не попадает по построению."""
        return self.state == STATE_LANDED

    def say(self):
        """Одна строка для журнала — всегда называет, ЧТО именно прочитано."""
        if self.state == STATE_LANDED:
            return f"величина {_say_num(self.expected)} СТОИТ в клетке — факт перечитан, синк идёт"
        if self.state == STATE_ABSENT:
            tail = f" ({self.detail})" if self.detail else ""
            return (f"величины {_say_num(self.expected)} в клетке НЕТ "
                    f"(там {_say_num(self.found)}) — синка нет{tail}")
        tail = f": {self.detail}" if self.detail else ""
        return (f"клетку перечитать НЕ УДАЛОСЬ — исход НЕИЗВЕСТЕН, записанным не считаю{tail}")

    def __repr__(self):
        return f"Fact({self.state}: expected={self.expected!r}, found={self.found!r})"


def _say_num(x):
    return "?" if x is None else f"{x}"


def _num(x):
    """Число или None. Логическое числом не считается: `True` — это `true`, а не единица км."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def field_for(kind):
    """Поле строки парка для вида работ, либо None — такой вид в колонке Лист1 не живёт."""
    return FIELD_BY_KIND.get(str(kind or ""))


def needs_verify(result):
    """Надо ли перечитывать факт после этого ответа моста?

    Успех — нет (здоровый путь не платит ни одного лишнего обращения). Отказ, вынесенный САМИМ
    мостом, — нет (исход определён). Молчание транспорта, отказ расписки и любой незнакомый код —
    да. Ответ не словарь → да: судить не по чему, а перечитывание дешевле потери."""
    if not isinstance(result, dict):
        return True
    if result.get("ok"):
        return False
    if result.get("outcome") == OUTCOME_UNKNOWN or result.get("error") == RECEIPT_UNKNOWN:
        return True
    return str(result.get("error") or "") not in SETTLED_ERRORS


def unknown(expected, detail=""):
    """Исход НЕИЗВЕСТЕН — конструктор для рук: перечитать не удалось на их стороне."""
    return Fact(STATE_UNKNOWN, expected, None, detail)


def verdict(expected, cell):
    """Ожидаемая величина + `ScanResult` клетки (см. `fleet_cell.read`) → `Fact`.

    Судит ТОЛЬКО принесённое: сходить за клеткой модулю нечем. Любая дырка в фактах —
    «неизвестно», и ни одна из них не читается как «записано»."""
    want = _num(expected)
    if want is None:
        return unknown(expected, f"величина записи не число ({expected!r}) — сверять нечем")

    outcome = getattr(cell, "outcome", None)
    if outcome is None:
        return unknown(expected, f"клетку принесли не контрактом ({cell!r})")

    if getattr(cell, "ok", False):
        got = _num(getattr(cell, "payload", None))
        if got is None:
            return unknown(expected, "контракт назвал клетку разобранной, а числа не дал")
        if got == want:
            return Fact(STATE_LANDED, expected, getattr(cell, "payload", None))
        return Fact(STATE_ABSENT, expected, getattr(cell, "payload", None),
                    "в клетке ДРУГАЯ величина")

    if outcome == OUTCOME_EMPTY:
        return Fact(STATE_ABSENT, expected, None, "клетка пуста")

    say = getattr(cell, "say", None)
    return unknown(expected, say() if callable(say) else str(outcome))
