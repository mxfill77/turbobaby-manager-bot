# -*- coding: utf-8 -*-
"""Цена через ход — примесь к адаптеру модели (PRICECARRY1610, отрезок P1 «цена»; флаг службы WA_AGENT_PRICE_CARRY).

ЗАЧЕМ. `ModelAdapter._price` считает цену ТОЛЬКО при слове цены в последних сообщениях клиента (`_PRICE_ASK` по хвосту,
wa_agent_model.py `_price`, первая проверка). «Сколько стоит PCX 160?» → мы: «на какие даты?» → «с 10 по 15 октября»: в
хвосте слова цены нет, расчёт не вызывается, блока «ЦЕНА» нет, и модель (правило 4) числа не называет — «коллега
уточнит». Названное клиентом в ответ на НАШ вопрос пропадало.

ЧТО ДЕЛАЕТ. `PriceCarryMixin` переопределяет РОВНО `_history` (запоминает историю вызова) и `_price`. Сначала ответ
родителя; он остаётся как есть, если родитель посчитал цену или назвал свою причину (слово цены в хвосте есть). Иначе
перенос берётся, только если ВСЕ три: (1) в блоке клиента ПЕРЕД нашим последним ответом есть слово цены — тот же
`wa_agent_model._PRICE_ASK`, своего списка нет; (2) наш последний ответ — встречный вопрос о датах: вопрос «…?» со словом
о датах или сроке, и суммы в батах в нём нет; (3) в хвосте есть признак срока. Не выполнено хоть одно — ответ родителя
байт-в-байт и ни одной строки журнала (обычный путь, путь без цены, «спасибо/ок» после нашего вопроса).

Перенос взят — цена считается с ДАТАМИ ХВОСТА и тем же байком: модель хвоста; её нет — модель вопроса о цене; нет и там
— самое новое сообщение клиента с моделью в переписке `ctx` (те же до 6 сообщений, что у цены). Ворота — родителя:
`K.quote` (дверь не больше раза; срок до месяца, один сезон, модель с ценой и в парке) и минимум класса
(`M.term_minimum` + `M.mark_minimum`). Источник недоступен (парк не прочитан, дверь упала, отказала, не ответила) —
исход тех же ворот «Цена НЕИЗВЕСТНА»: числа нет.

РАСЧЁТ НЕ ВЫЗЫВАЕТСЯ (ответ «цены нет», как без примеси; строка журнала с причиной; прежнее не подставляется):
  · даты противоречат — в хвосте больше одного срока, срок и число суток не сходятся, дата вне диапазона, даты по
    убыванию; вопрос о цене называл ДРУГИЕ даты или другое число суток (даты в переписке расходятся — цену называет
    человек);
  · срок хвоста неполный — без месяца, только число суток, только начало (склейки срока из разных сообщений нет);
  · срок уже начался или прошёл;
  · смена модели — в хвосте другая модель, модель не из парка, неоднозначное сокращение; модель вопроса не определена;
  · двери цены у адаптера нет.
Смена периода после нашего ответа С ЧИСЛОМ переноса не даёт (условие 2): старый результат не тащится, состояния у
примеси нет — каждый вызов `build` считает заново.

ГРАНИЦЫ. Брони не пишутся, альтернатив нет, промпт и инструменты не тронуты: блок «ЦЕНА» — та же строка `K.quote`, что у
родителя. Импорты — ровно `datetime`, `re`, `wa_agent_model`, `wa_agent_knowledge`; файлов, сети и базы модуль не
касается, дверь и парк — двери адаптера (`self.door`, `self.fleet`). В журнал — только числа и слова: ни номера, ни
моделей, ни дат, ни текста клиента.

ПОДКЛЮЧЕНИЕ. `with_price_carry(cls)` → класс «примесь + cls» (один на cls); служба (`wa_agent_svc.price_carry_of`)
меняет класс уже собранного адаптера (`ModelAdapter`, `ContractStateAdapter`, с примесью BOOKCTX или без). Флаг выключен
— модуль не импортируется вовсе."""
import datetime
import re

import wa_agent_knowledge as K
import wa_agent_model as M

LOG_HEAD = "цена через ход: "
NO_ASK = "о цене не спрашивают"          # слова родителя, когда слова цены в хвосте нет (тест сверяет с `_price`)

# ── наш встречный вопрос о датах ────────────────────────────────────────────────────────────────────────────────
# Вопрос — кусок текста до «?» в пределах предложения; слово о датах — в нём. «дат…» с границей слова: «кандидат» и
# «передать» датой не считаются.
_QUESTION = re.compile(r"[^.!?\n…]*\?")
_DATE_Q = re.compile(
    r"(?i)(?<![а-яё])(?:дат(?:а|ы|у|е|ой|ам|ами|ах)?|числ(?:о|а|у|ом|е|ам|ах)|срок(?:а|у|ом|и|ов)?)(?![а-яё])"
    r"|(?<![а-яё])когда(?![а-яё])|(?<![а-яё])с\s+какого|(?<![а-яё])по\s+какое|(?<![а-яё])сколько\s+(?:дн|сут|ноч)"
    r"|\bdates?\b|\bwhen\b|\bhow\s+long\b|\bhow\s+many\s+(?:days|nights)\b|\bwhich\s+days?\b|\bwhat\s+days?\b"
    r"|\bfrom\s+which\b")
# сумма в батах в нашем ответе — цену мы уже назвали, переноса нет
_AMOUNT = re.compile(r"(?i)\d[\d\s.,]*\s*(?:฿|бат|baht|thb)|฿\s*\d")
# ── признак срока в хвосте (любой, разобранный или нет) ─────────────────────────────────────────────────────────
_RX_LOOSE = re.compile(r"(?i)(?<![\d.:/])\d{1,2}\s*(?:-|–|—|/)\s*\d{1,2}(?![\d.:/])"
                       r"|(?<!\w)(?:с|со|до|по|from|till|until)\s+\d{1,2}(?![\d.:/])"
                       r"|(?<!\d)\d{1,2}\s*-?\s*(?:го|ое|st|nd|rd|th)(?!\w)|(?<!\d)\d{1,2}\s+числа")
_RX_REL = re.compile(r"(?i)(?<!\w)(?:послезавтра|завтра|сегодня)(?:шн\w*)?(?!\w)|\b(?:day\s+after\s+tomorrow|tomorrow|"
                     r"today|tonight)\b")
# похоже на модель (латиница + трёхзначная кубатура) — как у наличия по переписке (wa_book_ctx, сверяет тест)
_RX_MODEL_LIKE = re.compile(r"(?i)(?<![a-z0-9])[a-z][a-z-]*[a-z]\s*-?\s*\d{3}(?!\d)")

# ── коды и слова отказа (в журнал и в слова цены) ───────────────────────────────────────────────────────────────
MANY, LOOSE = "many", "loose"
W_MANY = "даты в ответе противоречат друг другу"
W_LOOSE = "срок в ответе неполный (без месяца, без конца или только число суток)"
W_PAST = "срок из ответа уже начался или прошёл"
W_PREV = "даты ответа расходятся с датами вопроса о цене"
W_MODEL_TAIL = "в ответе модель не из парка"
W_ALIAS = "в ответе модель не определена (сокращение подходит к нескольким)"
W_CHANGED = "в ответе другая модель, чем в вопросе о цене"
W_NO_MODEL = "модель вопроса о цене не определена"
W_NO_DOOR = "двери цены нет"
L_HIST = "история не та — ответ родителя"
L_FAIL = "сбой %s — ответ родителя"
L_STOP = "%s — расчёт не вызван, прежнее не подставлено"
L_DONE = "вопрос о цене обменом раньше, наш вопрос о датах, ответ датами — расчёт: %s, дверь %d"
L_FLEET = "парк не прочитан: %s"

_CLASSES = {}                                  # with_price_carry: класс «примесь + cls», один на cls


# ── чистые функции ──────────────────────────────────────────────────────────────────────────────────────────────

def date_question(text):
    """Наш ответ → встречный вопрос о датах: есть вопрос («…?») со словом о датах или сроке."""
    return any(_DATE_Q.search(q.group()) for q in _QUESTION.finditer(str(text or "")))


def has_amount(text):
    """В тексте сумма в батах (наш ответ уже назвал цену)."""
    return _AMOUNT.search(str(text or "")) is not None


def term_sign(text, today, day=None):
    """В словах есть хоть какой-то срок (разобранный или нет): диапазон, дата, число суток, вольная запись, день словом."""
    s = str(text or "")
    return bool(M.find_ranges(s, today, day) or M.find_dates(s, today, day) or M.count_list(s)
                or _RX_LOOSE.search(s) or _RX_REL.search(s))


def _uniq(dates):
    out = []
    for d in dates:
        if d not in out:
            out.append(d)
    return out


def _counts(text):
    return sorted({n for _a, n in M.count_list(text) if 0 < n <= M.TERM_MAX_DAYS})


def tail_term(ask, today, day=None):
    """Срок ответа клиента → (ds, de, None) — ровно один полный срок; иначе (None, None, код): MANY — сроков больше
    одного или они не сходятся (с числом суток, с датой вне диапазона, по убыванию); LOOSE — полного срока нет (без
    месяца, только число суток, только начало). Правила разбора — функции цены (`find_ranges`, `find_dates`,
    `count_list`): срок, который сочтёт цена, и срок переноса — одни и те же даты."""
    s = str(ask or "")
    rs = M.find_ranges(s, today, day)
    full = sorted({(r["ds"], r["de"]) for r in rs if r["ds"] is not None})
    bare = [r for r in rs if r["ds"] is None]
    counts = _counts(s)
    seen = _uniq(M.find_dates(s, today, day))
    if len(full) > 1:
        return None, None, MANY
    if full:
        ds, de = full[0]
        ends = {(ds.day, ds.month), (de.day, de.month)}
        if bare or [n for n in counts if n != (de - ds).days] or not {(d.day, d.month) for d in seen} <= ends:
            return None, None, MANY
        return ds, de, None
    if bare:
        return None, None, LOOSE
    if len(seen) == 2 and len(counts) <= 1:
        ds, de = seen
        if de <= ds or [n for n in counts if n != (de - ds).days]:
            return None, None, MANY
        return ds, de, None
    if len(seen) == 1 and len(counts) == 1:
        return seen[0], seen[0] + datetime.timedelta(days=counts[0]), None
    if len(seen) > 2 or len(counts) > 1:
        return None, None, MANY
    return None, None, LOOSE


def prev_conflict(prev, today, ds, de):
    """Слова вопроса о цене называли другой срок, чем ответ [ds, de] → True: дата вопроса не конец срока ответа, полный
    срок вопроса другой, число суток вопроса (или его диапазона без месяца) не равно сроку ответа."""
    s = str(prev or "")
    ends = {(ds.day, ds.month), (de.day, de.month)}
    rs = M.find_ranges(s, today)
    dates = M.find_dates(s, today) + [d for r in rs if r["ds"] is not None for d in (r["ds"], r["de"])]
    if not {(d.day, d.month) for d in dates} <= ends:
        return True
    days = set(_counts(s)) | {r["days"] for r in rs}
    return bool(days) and (de - ds).days not in days


def model_like_unknown(text, hits):
    """В словах модель (латиница + кубатура), которой нет среди упоминаний парка `hits` → True."""
    s = str(text or "")
    return any(not any(h[0] < m.end() and m.start() < h[1] for h in hits) for m in _RX_MODEL_LIKE.finditer(s))


def _client_texts(ctx):
    for c in ctx or ():
        if isinstance(c, (tuple, list)) and len(c) >= 2 and c[0] == M.WHO_CLIENT:
            yield str(c[1] or "")


def carry_model(ask, prev, ctx, bikes):
    """Тот же байк → (модель, None) | (None, слова отказа). Модель хвоста; нет — вопроса о цене; нет — самого нового
    сообщения клиента с моделью в переписке. Одна модель парка — иначе отказ: другая модель в хвосте, модель не из парка,
    неоднозначное сокращение, ни одной или несколько моделей у вопроса."""
    t_hits = M.model_hits(ask, bikes)
    if model_like_unknown(ask, t_hits):
        return None, W_MODEL_TAIL
    if any(h[2] is None for h in t_hits):
        return None, W_ALIAS
    hits = M.model_hits(prev, bikes)
    if not hits:
        hits = next((h for h in (M.model_hits(t, bikes) for t in _client_texts(ctx)) if h), [])
    asked = {h[2] for h in hits}
    t_ids = {h[2] for h in t_hits}
    if hits and (None in asked or len(asked) != 1):
        return None, W_NO_MODEL
    if t_ids and asked and t_ids != asked:
        return None, W_CHANGED
    got = t_ids or asked
    if len(got) != 1:
        return None, W_NO_MODEL
    return next(iter(got)), None


# ── примесь ─────────────────────────────────────────────────────────────────────────────────────────────────────

class PriceCarryMixin:
    """Примесь к адаптеру модели: цена на даты, которыми клиент ответил на наш встречный вопрос о датах."""

    def _history(self, number, upto_id):
        items, missing = super()._history(number, upto_id)
        self._pcarry_hist = (str(number), items)
        return items, missing

    def _price(self, ask, today, ctx=(), ask_day=None):
        res = super()._price(ask, today, ctx, ask_day)
        seen = self.__dict__.pop("_pcarry_hist", None)
        if res[0] is not None or res[1] != NO_ASK:
            return res                                # родитель посчитал или назвал свою причину — как есть
        try:
            got = self._pcarry(seen, ask, today, ctx, ask_day)
        except Exception as e:                                       # noqa: BLE001 — сбой примеси: ответ родителя
            self.log(LOG_HEAD + L_FAIL % type(e).__name__)
            return res
        return res if got is None else got

    def _pcarry_stop(self, why):
        self.log(LOG_HEAD + L_STOP % why)
        return None, LOG_HEAD + L_STOP % why

    def _pcarry(self, seen, ask, today, ctx, ask_day):
        """→ (исход цены | None, слова) | None (ответ родителя без строки журнала: перенос не нужен)."""
        if seen is None:
            if term_sign(ask, today, ask_day):
                self.log(LOG_HEAD + L_HIST)
            return None
        items = seen[1]
        tail = self._tail(items)
        tail_text = K.mask("\n".join(it["text"] or ("[%s]" % it["word"] if it["word"] else "")
                                     for it in tail)[-M.TAIL_MAX:])[0]
        if tail_text != ask or self._context(items, tail) != list(ctx or ()):
            if term_sign(ask, today, ask_day):
                self.log(LOG_HEAD + L_HIST)
            return None
        prev, ours = self._before(items)
        if not (M._PRICE_ASK.search(prev) and date_question(ours) and not has_amount(ours)
                and term_sign(ask, today, ask_day)):
            return None                               # перенос не нужен — ответ родителя, журнал прежний
        ds, de, code = tail_term(ask, today, ask_day)
        if code is not None:
            return self._pcarry_stop(W_MANY if code == MANY else W_LOOSE)
        if ds < today:
            return self._pcarry_stop(W_PAST)
        if prev_conflict(prev, today, ds, de):
            return self._pcarry_stop(W_PREV)
        if self.fleet is None or self.door is None:
            return self._pcarry_stop(W_NO_DOOR)
        try:
            bikes = M.fleet_bikes(self.fleet())
        except Exception as e:                                       # noqa: BLE001 — отказ парка ≠ «модели нет»
            bikes = None
            self.log(LOG_HEAD + L_FLEET % type(e).__name__)
        if bikes is None:                             # как у родителя: модель не найти — исход ворот без парка
            return self._pcarry_done(K.quote("?", ds, de, self.door, lambda m: None))
        model, why = carry_model(ask, prev, ctx, bikes)
        if model is None:
            return self._pcarry_stop(why)
        term = {"ds": ds, "de": de, "days": M.term_days(ds, de)}
        mn = M.term_minimum([model]).get(model)
        if mn is not None and 0 < term["days"] < mn:  # короче минимума класса — дверь на минимум, как у родителя
            term = dict(term, de=ds + datetime.timedelta(days=mn), min=mn, client=term["days"])
        return self._pcarry_done(M.mark_minimum(K.quote(model, term["ds"], term["de"], self.door,
                                                        lambda m: M.units_of(m, bikes), self.no_price_models), term))

    def _pcarry_done(self, res):
        self.log(LOG_HEAD + L_DONE % (res["outcome"], int(res.get("door_calls") or 0)))
        return res, LOG_HEAD + "цена: %s" % res["outcome"]


def with_price_carry(cls):
    """Класс адаптера → он же с примесью (один на cls). Уже с примесью — как есть: повторное надевание ничего не меняет."""
    if issubclass(cls, PriceCarryMixin):
        return cls
    got = _CLASSES.get(cls)
    if got is None:
        got = _CLASSES[cls] = type("PriceCarry" + cls.__name__, (PriceCarryMixin, cls), {"__module__": __name__})
    return got
