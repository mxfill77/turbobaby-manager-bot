"""КАССА НЕ ПОКАЗЫВАЕТ БАЛАНС ИЗ КЭША МОЛЧА (13.08.2026).

КЛАСС. Ответ кассы несёт ДВА утверждения о мире — «записал» и «баланс такой». 13.08 оба были
сказаны без основания, и ни одно не прозвучало сомнением.

  · `add_transaction` ушёл и НЕ вернулся (`Bridge request error (add_transaction): HTTP 302`,
    12:29:44). Писчее плечо пересылок не имеет намеренно, поэтому исход НЕИЗВЕСТЕН и мост прямо
    требует перечитать факт — а возврат в `splinter._record_transaction` не присваивался ВОВСЕ:
    требование было адресовано некому.
  · `get_balance` тоже не ответил (HTTP 302 после 3 полных попыток, 12:33 и 12:35), отдал `{}`, и
    `wallet_cache` МОЛЧА подставил последнее известное 1529. Группа дважды увидела «Баланс: 1 529»
    при расходах −120 и −500; лист при этом верен и считает 1029, обе строки легли без дублей.

ЗАМЕР (splinter.log, 01.06–13.08, 73 суток): ответов кассы с балансом 281 (272 проводки + 9
фиксаций), из них ЖИВЫМ пересчётом 280, ПОДМЕНОЙ КЭША 1 — та самая 13.08 12:35:07. Отказов
писчего плеча у `add_transaction` за всё наблюдение 1 (13.08 12:29:44). Класс редок и потому
особенно опасен: он не тренирует недоверие, а приходит один раз — в день, когда мост болен.

ПОЧЕМУ НЕ «ВЫКЛЮЧИТЬ КЭШ». При больном мосте молчание хуже: Пым решит, что бот умер, и перестанет
писать в группу вовсе. Кэш ОСТАЁТСЯ — меняется не число, а то, ЧЕМ оно СЕБЯ НАЗЫВАЕТ.

ТРИ ИСХОДА, А НЕ ДВА — тот же замок против ложного зелёного, что у О3, контракта клетки и
`write_fact`; вокабуляр исходов записи взят ОТТУДА ЖЕ (`STATE_LANDED/ABSENT/UNKNOWN`), второго
словаря о тех же смыслах здесь не заводится.

    БАЛАНС                                                     ЗАПИСЬ
    FRESH  мост пересчитал из строк      → число живое         LANDED   строка в листе стоит
    STALE  мост молчит, кэш есть         → «НЕ СВЕРЕНО» + дата ABSENT   такой строки в листе нет
    NONE   мост молчит, кэша нет         → сказать нечего      UNKNOWN  перечитать не удалось

ПУСТОЙ ОТВЕТ И МОЛЧАНИЕ — РАЗНЫЕ ВЕЩИ, И ЭТО КОРЕНЬ ПОДМЕНЫ. Прежнее решение судило ИСТИННОСТЬ
словаря (`if bridge_balance:`), а `computeBalance_` возвращает `{}` ЗАКОННО — у кошелька нет строк
(BotData.js:881). Значит пустой кошелёк читался как больной мост и получал чужое число из кэша, а
больной мост — как пустой кошелёк. Здесь судится ОТВЕТ (`ok`), а не истинность числа: `ok` с
пустым балансом есть FRESH ноль, и это правда о мире.

ВРЕМЯ, КОГДА ЧИСЛО БЫЛО ВЕРНО, — ЧАСТЬ ОТВЕТА, А НЕ УКРАШЕНИЕ. Без него «не сверено» неотличимо
от «не сверено пять минут назад» и от «не сверено вчера», а решение Пыма (ждать или считать
наличные руками) зависит именно от этого. Метки нет (кэш лёг прежним кодом) → так и говорим:
время неизвестно. Выдумывать «наверное, недавно» нельзя — это ровно та подмена, против которой
модуль и стоит.

ГРАНИЦА УСТРОЙСТВОМ: импорт РОВНО ОДИН — `write_fact` (у него один свой, `scan_result`). Ему
нечем ни спросить мост, ни прочитать кэш, ни узнать время: факты приносит вызывающий, модуль
только судит принесённое. Появись у него руки — он мог бы сходить за балансом сам, и «сверено»
стало бы зависеть от того, КАК спросили. Проверяется разбором (ast) инвариантом
`BALANCE_FACT_PURE`, а не докстрингом. Руки — `wallet_cache.answer` и
`splinter._record_transaction`. Тесты `tests/test_cash_balance_fact.py`.
"""
import write_fact

#: Исходы БАЛАНСА. Три, и третий — не запасной.
STATE_FRESH = "fresh"
STATE_STALE = "stale"
STATE_NONE = "none"

#: Исходы ЗАПИСИ — взяты у `write_fact`, а не заведены заново: смысл тот же, слово должно быть то же.
STATE_LANDED = write_fact.STATE_LANDED
STATE_ABSENT = write_fact.STATE_ABSENT
STATE_UNKNOWN = write_fact.STATE_UNKNOWN

#: Поля строки кассы, по которым узнаётся НАША проводка в ответе `tx_summary`.
#: Только МАШИННЫЕ поля: их пишет бот и не трогает человек. Свободный текст (`description`,
#: `sender`) намеренно НЕ сверяется — лист вправе его подрезать/переформатировать, а ложное
#: «проводки НЕТ» стоит дороже неточности: Пым запишет вторую строку руками.
MATCH_FIELDS = ("amount", "currency", "category", "bike")


class Balance:
    """Что касса вправе сказать о балансе. Читать `.fresh`, произносить словами вызывающего."""

    __slots__ = ("state", "value", "at", "detail")

    def __init__(self, state, value=None, at=None, detail=""):
        self.state = state
        self.value = value if isinstance(value, dict) else {}
        self.at = at
        self.detail = str(detail or "")

    @property
    def fresh(self):
        """ТОЛЬКО пересчитанное мостом из строк. Кэш сюда не попадает по построению."""
        return self.state == STATE_FRESH

    @property
    def shows_number(self):
        """Есть ли что показать вообще. У NONE числа нет — и придумывать его нечем."""
        return self.state in (STATE_FRESH, STATE_STALE)

    def say(self):
        """Одна строка для журнала — всегда называет, ОТКУДА число."""
        if self.state == STATE_FRESH:
            return f"баланс пересчитан мостом из строк: {self.value}"
        if self.state == STATE_STALE:
            when = "время неизвестно" if self.at is None else f"верно на {self.at}"
            tail = f" ({self.detail})" if self.detail else ""
            return f"баланс НЕ СВЕРЕН — мост молчит, показываю кэш {self.value} ({when}){tail}"
        tail = f": {self.detail}" if self.detail else ""
        return f"баланс НЕ СВЕРЕН и кэша нет — числа не показываю{tail}"

    def __repr__(self):
        return f"Balance({self.state}: value={self.value!r}, at={self.at!r})"


class TxFact:
    """Что мир говорит о нашей проводке. Читать `.landed`, произносить `.say()`."""

    __slots__ = ("state", "expected", "seen", "detail")

    def __init__(self, state, expected=None, seen=0, detail=""):
        self.state = state
        self.expected = expected if isinstance(expected, dict) else {}
        self.seen = seen
        self.detail = str(detail or "")

    @property
    def landed(self):
        """ТОЛЬКО доказанное присутствие. «Неизвестно» сюда не попадает по построению."""
        return self.state == STATE_LANDED

    @property
    def absent(self):
        """Доказанное отсутствие — единственный случай, когда зовём записать руками."""
        return self.state == STATE_ABSENT

    def say(self):
        if self.state == STATE_LANDED:
            return (f"проводка {_say_move(self.expected)} СТОИТ в листе — факт перечитан")
        if self.state == STATE_ABSENT:
            return (f"проводки {_say_move(self.expected)} в листе НЕТ "
                    f"(сегодняшних совпадений 0) — строка не легла")
        tail = f": {self.detail}" if self.detail else ""
        return f"лист перечитать НЕ УДАЛОСЬ — исход НЕИЗВЕСТЕН, записанной не считаю{tail}"

    def __repr__(self):
        return f"TxFact({self.state}: expected={self.expected!r}, seen={self.seen!r})"


def _say_move(sig):
    amount = sig.get("amount")
    cur = sig.get("currency") or "?"
    return f"{'?' if amount is None else amount} {cur}"


def _num(x):
    """Число или None. Логическое числом не считается: `True` — это `true`, а не сумма."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _txt(x):
    return str("" if x is None else x).strip().lower()


# ── БАЛАНС ──────────────────────────────────────────────────────────────────────────────────

def balance_verdict(reply, cached=None, cached_at=None):
    """Ответ моста (ЦЕЛИКОМ, а не поле `balance`) + кэш и его метка времени → `Balance`.

    Судит ОТВЕТ, а не истинность числа: `ok` с пустым балансом — это FRESH ноль (у кошелька нет
    строк), а не повод лезть в кэш. Всё, что не есть внятное `ok` с балансом-словарём, — молчание
    моста, и тогда число может прийти только из кэша и только со словом «НЕ СВЕРЕНО»."""
    ok = isinstance(reply, dict) and bool(reply.get("ok"))
    if ok:
        bal = reply.get("balance")
        if isinstance(bal, dict):
            return Balance(STATE_FRESH, bal)
        # Мост сказал «ok», а баланса не дал — свежим это назвать нечем.
        return _from_cache(cached, cached_at, "мост ответил ok без баланса")
    why = _refusal(reply)
    return _from_cache(cached, cached_at, why)


def _refusal(reply):
    if not isinstance(reply, dict):
        return "ответ моста не разобран"
    err = reply.get("error")
    return f"мост отказал: {err}" if err else "мост не ответил"


def _from_cache(cached, cached_at, why):
    value = cached if isinstance(cached, dict) else {}
    if not value:
        return Balance(STATE_NONE, {}, None, why)
    return Balance(STATE_STALE, value, cached_at, why)


# ── ПРОВОДКА ────────────────────────────────────────────────────────────────────────────────

def needs_verify(reply):
    """Надо ли перечитывать лист после этого ответа моста?

    Решение НЕ переписывается: берётся готовое у `write_fact` (форма `_claim_task_verified`).
    Успех — нет: здоровый путь не платит НИ ОДНОГО лишнего обращения к больному мосту. Отказ,
    вынесенный САМИМ мостом, — нет: исход определён. Молчание транспорта, отказ расписки и любой
    незнакомый код — да."""
    return write_fact.needs_verify(reply)


def signature(amount, currency, category="", bike=""):
    """Отпечаток нашей проводки — то, по чему она узнаётся в листе.

    Ключа сообщения (`msg_id`) в ответе `tx_summary` НЕТ (BotData.js:1443-1446 кладёт в `items`
    семь полей, ключа среди них нет), поэтому узнавание идёт по машинным полям строки. Это
    названный предел, а не оплошность: точная сверка по ключу — правка Apps Script, то есть
    красная зона владельца."""
    return {
        "amount": _num(amount),
        "currency": str(currency or "THB").upper(),
        "category": _txt(category or "other"),
        "bike": _txt(bike),
    }


def _same(sig, item):
    if _num(item.get("amount")) != sig.get("amount"):
        return False
    if str(item.get("currency") or "THB").upper() != sig.get("currency"):
        return False
    if _txt(item.get("category") or "other") != sig.get("category"):
        return False
    return _txt(item.get("bike")) == sig.get("bike")


def tx_verdict(sig, summary):
    """Отпечаток проводки + ответ `tx_summary` → `TxFact`. Судит ТОЛЬКО принесённое.

    НОЛЬ совпадений → ABSENT: нашей строки в листе НЕТ, и этого достаточно, чтобы позвать записать
    руками. РОВНО ОДНО → LANDED. ДВА И БОЛЬШЕ → UNKNOWN, и это не придирка: строк-близнецов у
    кассы бывает много (два одинаковых расхода за день — обычное дело), а сколько их было ДО нашей
    отправки, мы не знаем. Приписать себе чужую строку значит назвать записанным то, чего мы не
    писали, — тот же подлог, только с другой стороны."""
    if sig.get("amount") is None:
        return TxFact(STATE_UNKNOWN, sig, 0, "сумма проводки не число — сверять нечем")
    if not isinstance(summary, dict) or not summary.get("ok"):
        return TxFact(STATE_UNKNOWN, sig, 0, _refusal(summary))
    items = summary.get("items")
    if not isinstance(items, list):
        return TxFact(STATE_UNKNOWN, sig, 0, "мост ответил ok без списка строк")
    seen = sum(1 for it in items if isinstance(it, dict) and _same(sig, it))
    if seen == 0:
        return TxFact(STATE_ABSENT, sig, 0)
    if seen == 1:
        return TxFact(STATE_LANDED, sig, 1)
    return TxFact(STATE_UNKNOWN, sig, seen,
                  f"в листе {seen} одинаковых строк — какая из них наша, не различить")
