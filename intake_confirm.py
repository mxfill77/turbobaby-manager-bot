"""Ответ подтверждающего на карточку брони и исход записи брони в CRM (INTAKECONFIRM1610, 16.10.2026).

Чистое решение, руки — в `splinter._intake_reply_strict`. Импорт ровно один (`re`): модуль не открывает
файлов, не ходит в сеть и не читает окружение.

`decide(text)` — согласие только ЯВНОЕ и однозначное. Прежняя ветка «3) approve / нет / правки» искала
ПОДСТРОКУ («да» в «когда»/«не надо», «ставь» в «не ставь», «ок» в «около») и проверяла её РАНЬШЕ отказа —
ложное согласие на денежно-значимую запись. Здесь судятся СЛОВА целиком, отказ сильнее согласия, сомнение
даёт переспрос (ASK), а не запись.

YES возможен, только если в ответе есть хотя бы одно слово, ВСЕ слова взяты из CONSENT_WORDS, вопроса нет, а
всё, что осталось после вырезания слов, — из белого списка (`YES_RESIDUE_OK`, знаки согласия CONSENT_EMOJI и их
модификаторы). Любой иной знак рядом с согласием («да 👎», «да 🤔», «да？», «да...») — сомнение → ASK.

NO (отказ) — только ЯСНЫЙ: отказ стоит первым, и за ним конец фразы, знак препинания или ещё один отказ
(«нет», «не ставь», «нет, когда оплатит»). «нет проблем», «нет вопросов», «отмена не нужна», «сейчас нет» → ASK.
Отрицание рядом со словом о правке («правок нет», «правки не нужны», «не надо править») — не отказ и не правка, а
сомнение → ASK. Исключение — правило (а) проекта: «нет правок», «без правок», «не исправляй» → прочее (молчание,
таблица проекта N19).

Почти-согласие («ага», «хорошо», «подтверждено», «дааа», «+», …) согласием не является — ASK, а не молчание.

`outcome(res, sent)` — исход вызова `create_booking` тремя словами (+ прежний duplicate): записано · не
записано (мост сам вынес отказ ДО записи) · НЕИЗВЕСТНО (ответ потерян, а POST мог исполниться). Сомнение — в
«неизвестно»: незнакомый или пустой код, ответ не словарь, исключение после отправки.

APPROVEFIX1610 (16.10.2026, Codex TB-OWNER-EFFICIENCY-1610-2054, карта QUEUE4_INTAKE_SUBSTR_MAP М1–М6) — карточки
ВЫДАЧИ и ПРИЁМА тем же разбором:
  * `decide(text, extra_consent, extra_neg_stems, extra_near_stems)` — слова действия карточки. Без них (по умолчанию)
    поведение брони то же до байта: дополнения только расширяют словари, порядок и правила прежние;
  * `km_arg(text)` — пробег сдачи: ровно одно число целиком (без усечения; допустима группировка «35 300»), длина —
    прежний диапазон разбора Splinter 2–7 цифр (не новая норма). Второе число, длинное число, одна цифра — пробега нет;
  * `red_outcome(res, sent, action)` — исход activate_booking/close_booking тремя словами. Список «мост отказал ДО
    записи» у каждого действия СВОЙ, снят с контракта bridge_prod (Booking.js activateBooking/closeBooking, Bridge.js);
    список брони сюда не переносится.
"""
import re

YES, NO, EDIT, ASK, SILENT = "yes", "no", "edit", "ask", "silent"
BOOKED, DUPLICATE, NOT_WRITTEN, UNKNOWN = "booked", "duplicate", "not_written", "unknown"

# ---- словари проекта §2.1 — дословно ------------------------------------------------------------------
CONSENT_WORDS = frozenset({"да", "ок", "окей", "ok", "okay", "yes", "давай", "конечно",
                           "ставь", "поставь", "ставим", "поставим", "ставлю", "поставлю",
                           "подтверждаю", "подтверждаем"})
REFUSE_WORDS = frozenset({"нет", "неа", "no", "nope", "нельзя", "стоп", "stop", "cancel"})
REFUSE_STEMS = ("отмен", "отклон")
NEG_REFUSE_NEXT = frozenset({"надо", "нужно", "сейчас", "согласен", "согласна", "согласны"})
NEG_REFUSE_STEMS = ("став", "подтвер")
EDIT_STEMS = ("правк", "исправ", "поправ")
EDIT_NEGATORS = frozenset({"не", "нет", "без"})
CONSENT_EMOJI = ("\U0001F44D", "\U0001F44C", "✅", "✔", "☑", "\U0001F197")  # 👍 👌 ✅ ✔ ☑ 🆗

# Отказы моста, вынесенные ДО записи (bridge_prod: Bridge.js / Booking.js) — запись не начиналась.
# write_failed, internal_error, коды клиента (timeout, request_failed, json_parse_error, receipt_unknown,
# card_deadline) сюда НЕ входят намеренно: запись могла лечь (целиком или частично).
NOT_WRITTEN_ERRORS = frozenset({"bad_json", "no_ticket", "unknown_action", "missing_bike", "missing_name",
                                "bike_not_resolved", "bad_dates", "sheet_not_found", "booking_conflict"})

# ---- дополнения выпуска (находки критиков 16.10; названы в отчёте) --------------------------------------
# Слова о правке сверх основ проекта: «правок» (род. п. мн. ч., беглая «о» — основа «правк» его не покрывает),
# «править/правите», «правь». Существительное о правке отличается от глагола: «нет правок» — отсутствие правок,
# а «нет исправь дату» — отказ + просьба исправить (правило (а) после «нет»/«без» — только для существительных).
EDIT_EXTRA_STEMS = ("правок", "правит")
EDIT_EXTRA_WORDS = frozenset({"правь", "правьте"})
EDIT_NOUN_STEMS = ("правк", "правок", "поправк", "поправок", "исправлен")
# «не» + это слово = отказ (сверх NEG_REFUSE_NEXT проекта): «не нужны», «не стоит», «не будем».
NEG_REFUSE_NEXT_EXTRA = frozenset({"нужны", "нужна", "нужен", "стоит", "будем", "требуется", "требуются"})
# Почти-согласие: согласием НЕ является (запись не идёт), но и молчать на него нельзя — человек решит, что бронь
# стоит. Вердикт — ASK. «не» + почти-согласие = отказ («не хорошо», «не подтверждено»).
NEAR_CONSENT_WORDS = frozenset({
    "ага", "угу", "хорошо", "хор", "принято", "принял", "приняла", "принимаю", "согласен", "согласна", "согласны",
    "согласовано", "верно", "правильно", "ладно", "лады", "норм", "нормально", "отлично", "годится", "пойдет",
    "подходит", "можно", "давайте", "го", "оке", "окэй", "окс", "кк", "бронируй", "бронируем", "забронируй",
    "yep", "yeah", "yup", "ya", "sure", "fine", "good", "agree", "agreed", "approve", "approved", "confirm",
    "confirmed", "kk", "k", "okey", "alright", "right"})
NEAR_CONSENT_STEMS = ("подтвер",)            # «подтверждено», «подтвердил», «подтверди» (кроме двух слов YES)
# После каких слов отказа смежный второй отказ ещё отказ («нет нет», «нет не ставь»).
REFUSE_CHAIN_WORDS = frozenset({"нет", "неа", "no", "nope", "стоп", "stop"})
NEAR_BIGRAMS = frozenset({("без", "проблем"), ("нет", "проблем"), ("нет", "вопросов"), ("без", "вопросов"),
                          ("нет", "возражений"), ("без", "возражений"), ("no", "problem"), ("no", "problems")})
_STRETCHED = r"д+а+(?:д+а+)*|о+к+|о+к+е+й+|o+k+|o+k+a+y+|y+e+s+"   # «дааа», «дада», «окк», «yess»
# Вопрос — не только ASCII «?».
QUESTION_MARKS = ("?", "？", "¿", "⁇", "⁈", "⁉", "❓", "❔")
# Знаки отказа и сомнения без слов: сами по себе — переспрос, а рядом с «да» — не согласие.
REFUSE_EMOJI = ("\U0001F44E", "❌", "❎", "✖", "\U0001F6AB", "⛔", "\U0001F645")   # 👎 ❌ ❎ ✖ 🚫 ⛔ 🙅
DOUBT_EMOJI = ("\U0001F914", "\U0001F937")                                                   # 🤔 🤷
# Что может стоять рядом со словами согласия в ответе YES (кроме самих знаков согласия и их модификаторов).
YES_RESIDUE_OK = frozenset(" \t\r\n.,!-–—:)«»\"'")
_EMOJI_MODS = frozenset([chr(c) for c in range(0x1F3FB, 0x1F400)] + [chr(0xFE0F), chr(0x200D)])   # тон кожи, VS16, ZWJ
_PLUS_ONLY = r"\s*\+{1,3}\s*1?\s*"

_TOKEN = r"[a-zа-я0-9]+"

# ---- APPROVEFIX1610: слова карточек выдачи и приёма (дополняют словари проекта, брони не касаются) -------------------
# Согласие — только повелительные и «мы»-формы действия карточки; «не» + слово с основы — отказ; слово с основы, не
# названное согласием («завершена?», «завершу сам», «активировал»), — почти-согласие → переспрос, а не запись.
ACTIVATE_CONSENT = frozenset({"активируй", "активируйте", "активируем"})
ACTIVATE_STEMS = ("актив",)
CLOSE_CONSENT = frozenset({"завершай", "завершайте", "заверши", "завершите", "завершаем",
                           "закрывай", "закрывайте", "закрываем"})
CLOSE_STEMS = ("заверш", "закрыв")

# Пробег сдачи (М6): число ЦЕЛИКОМ. Группы по три цифры через пробел (обычный, неразрывный, узкий) — одно число.
KM_DIGITS_MIN, KM_DIGITS_MAX = 2, 7            # прежний разбор Splinter `\d{2,7}` (splinter.py:13060, :9387)
_KM_SEP = "    "
_NUMBER = r"(?<![0-9])(?:[0-9]{1,3}(?:[" + _KM_SEP + r"][0-9]{3})+|[0-9]+)(?![0-9])"

# Мост вынес отказ ДО записи (bridge_prod): общий слой Bridge.js — bad_json :256, no_ticket :285, unknown_action :530;
# activateBooking — missing_args :319, bike_not_resolved :322, sheet_not_found :326, booking_not_found :352 (строка
# не тронута); closeBooking — missing_args :381, bike_not_resolved :385, sheet_not_found :389, not_active :423,
# not_found :427, ambiguous :432, km_required :440, bad_km_end :444, odo_unverifiable :451, odometer_back :457.
# write_failed (closeBooking :474 — запись могла лечь частью), internal_error (Bridge.js:542) и коды клиента — НЕ здесь.
RED_NOT_WRITTEN = {
    "activate": frozenset({"bad_json", "no_ticket", "unknown_action", "missing_args", "bike_not_resolved",
                           "sheet_not_found", "booking_not_found"}),
    "close": frozenset({"bad_json", "no_ticket", "unknown_action", "missing_args", "bike_not_resolved",
                        "sheet_not_found", "not_active", "not_found", "ambiguous", "km_required", "bad_km_end",
                        "odo_unverifiable", "odometer_back"}),
}
WRITTEN = "written"


def _adjacent(s, a, b):
    """Смежны ли токены a и b: между ними в строке только пробелы (запятая и иной знак смежность рвут)."""
    return s[a.end():b.start()].strip() == ""


def _is_edit(w):
    return w.startswith(EDIT_STEMS) or w.startswith(EDIT_EXTRA_STEMS) or w in EDIT_EXTRA_WORDS


def _is_edit_noun(w):
    return w.startswith(EDIT_NOUN_STEMS)


_NO_EXTRA = (frozenset(), (), ())       # (согласие, основы отказа после «не», основы почти-согласия) — бронь


def _is_near(w, xv=_NO_EXTRA):
    if w in CONSENT_WORDS or w in xv[0]:
        return False
    return (w in NEAR_CONSENT_WORDS or w.startswith(NEAR_CONSENT_STEMS) or bool(re.fullmatch(_STRETCHED, w))
            or bool(xv[2] and w.startswith(xv[2])))


def _neg_pair(w2, xv=_NO_EXTRA):
    """«не» + w2 — отказ (правило (б) проекта + дополнения)."""
    return (w2 in CONSENT_WORDS or w2 in xv[0] or w2 in NEG_REFUSE_NEXT or w2 in NEG_REFUSE_NEXT_EXTRA
            or w2.startswith(NEG_REFUSE_STEMS) or bool(xv[1] and w2.startswith(xv[1])) or _is_near(w2, xv))


def _units(s, toks, xv=_NO_EXTRA):
    """Слева направо: единицы [вид, первый токен, последний токен, метка]. Виды: edit · refuse · consent · near ·
    other. Метка «neg» — пара «не + X» (правило (б)), «a» — пара правила (а)."""
    units = []
    i, n = 0, len(toks)
    while i < n:
        w = toks[i].group(0)
        adj = i + 1 < n and _adjacent(s, toks[i], toks[i + 1])
        w2 = toks[i + 1].group(0) if adj else None
        if w2 is not None:
            if w in EDIT_NEGATORS and _is_edit(w2) and (w == "не" or _is_edit_noun(w2)):
                units.append(["other", i, i + 1, "a"])           # а) «нет правок», «без правок», «не исправляй»
                i += 2
                continue
            if (w, w2) in NEAR_BIGRAMS:
                units.append(["near", i, i + 1, "bigram"])       # «нет проблем», «без возражений»
                i += 2
                continue
            if w == "не" and _neg_pair(w2, xv):
                units.append(["refuse", i, i + 1, "neg"])        # б) «не ставь», «не надо», «не ок»
                i += 2
                continue
        if _is_edit(w):
            kind = "edit"
        elif w in REFUSE_WORDS or w.startswith(REFUSE_STEMS):
            kind = "refuse"
        elif w in CONSENT_WORDS or w in xv[0]:
            kind = "consent"
        elif _is_near(w, xv):
            kind = "near"
        elif w == "не" and not adj:
            kind = "refuse"                                      # «Не.», «не, не надо» — разговорное «нет»
        else:
            kind = "other"
        units.append([kind, i, i, "one"])
        i += 1
    return units


def _units_adjacent(s, toks, u, v):
    return _adjacent(s, toks[u[2]], toks[v[1]])


def _negated_edits(s, toks, units):
    """Отрицание рядом со словом о правке («правок нет», «правки не нужны», «не надо править») — сомнение."""
    for k, u in enumerate(units):
        if u[0] != "edit":
            continue
        prev = units[k - 1] if k > 0 and _units_adjacent(s, toks, units[k - 1], u) else None
        nxt = units[k + 1] if k + 1 < len(units) and _units_adjacent(s, toks, u, units[k + 1]) else None
        hit = []
        if prev is not None and prev[0] == "refuse" and prev[3] == "neg":
            hit.append(prev)
        if nxt is not None and nxt[0] == "refuse":
            hit.append(nxt)
        if hit:
            u[0] = "doubt"
            for h in hit:
                h[0] = "doubt"


def _clear_refusal(s, toks, units):
    """Ясный отказ: первая единица — отказ, а за ним конец фразы, знак препинания или ещё один отказ. Смежное
    продолжение отказом разрешено только после голого слова отказа («нет нет», «нет не ставь»): у прочих
    («отмена не нужна», «нельзя не ставить») второе отрицание переворачивает смысл — это сомнение, а не отказ.
    Условие записано положительно: «не ясный отказ» (False) — обычный ответ предиката над уже разобранными
    единицами, а не пустое из ветки промаха разбора (храповик `blind_readers`)."""
    if units and units[0][0] == "refuse":
        k = 0
        while (k + 1 < len(units) and units[k + 1][0] == "refuse" and units[k][3] == "one"
               and toks[units[k][1]].group(0) in REFUSE_CHAIN_WORDS
               and _units_adjacent(s, toks, units[k], units[k + 1])):
            k += 1
        return k + 1 == len(units) or not _units_adjacent(s, toks, units[k], units[k + 1])
    return False


def _residue_ok(s, toks):
    """Всё, что не слова, — из белого списка YES: пробелы и спокойные знаки, знаки согласия и их модификаторы."""
    parts, last = [], 0
    for t in toks:
        parts.append(s[last:t.start()])
        last = t.end()
    parts.append(s[last:])
    rest = "".join(parts)
    if ".." in rest:
        return False                                             # «да...» — колебание
    for ch in rest:
        if ch in YES_RESIDUE_OK or ch in CONSENT_EMOJI or ch in _EMOJI_MODS:
            continue
        return False
    return True


def decide(text, extra_consent=(), extra_neg_stems=(), extra_near_stems=()):
    """Ответ подтверждающего → YES | NO | EDIT | ASK | SILENT. Каркас — порядок проекта §2.1, дополнения
    (почти-согласие, ясность отказа, отрицание при правке, белый список знаков рядом с согласием) названы выше.

    APPROVEFIX1610: необязательные слова действия карточки (выдача — ACTIVATE_*, приём — CLOSE_*): согласие,
    основы отказа после «не», основы почти-согласия. Без них — бронь, поведение прежнее."""
    xv = (frozenset(extra_consent), tuple(extra_neg_stems), tuple(extra_near_stems))
    s = str(text or "").lower().replace("ё", "е")
    if re.fullmatch(_PLUS_ONLY, s):
        return ASK                                               # «+», «++», «+1» — как 👍: переспрос
    toks = list(re.finditer(_TOKEN, s))
    if not toks:
        marks = CONSENT_EMOJI + REFUSE_EMOJI + DOUBT_EMOJI
        return ASK if any(e in s for e in marks) else SILENT
    units = _units(s, toks, xv)
    _negated_edits(s, toks, units)
    kinds = {u[0] for u in units}
    consent, refuse, near = "consent" in kinds, "refuse" in kinds, "near" in kinds
    if "edit" in kinds:
        return EDIT
    if any(q in s for q in QUESTION_MARKS):
        return ASK if (consent or refuse or near or "doubt" in kinds) else SILENT
    if "doubt" in kinds:
        return ASK
    if refuse and (consent or near):
        return ASK
    if refuse:
        return NO if _clear_refusal(s, toks, units) else ASK
    if consent and kinds == {"consent"} and _residue_ok(s, toks):
        return YES
    if consent or near:
        return ASK
    return SILENT


def outcome(res, sent):
    """Исход вызова create_booking → BOOKED | DUPLICATE | NOT_WRITTEN | UNKNOWN.

    sent — вызов create_booking состоялся (флаг ставится строго перед ним)."""
    if not sent:
        return NOT_WRITTEN                       # вызов create_booking не состоялся
    if not isinstance(res, dict):
        return UNKNOWN                           # исключение после отправки или не словарь
    if res.get("ok"):
        return BOOKED
    if res.get("outcome") == "unknown":
        return UNKNOWN                           # receipt_unknown
    err = str(res.get("error") or "")
    if err == "duplicate":
        return DUPLICATE
    if err in NOT_WRITTEN_ERRORS:
        return NOT_WRITTEN
    return UNKNOWN


# ---- APPROVEFIX1610: карточки выдачи и приёма -------------------------------------------------------------------------
def decide_action(text, action):
    """decide со словами карточки: action ∈ {"activate", "close"}; иное — бронь (без дополнений)."""
    if action == "activate":
        return decide(text, ACTIVATE_CONSENT, ACTIVATE_STEMS, ACTIVATE_STEMS)
    if action == "close":
        return decide(text, CLOSE_CONSENT, CLOSE_STEMS, CLOSE_STEMS)
    return decide(text)


def km_arg(text):
    """Пробег сдачи в ответе → (пробег | None, текст без него). Пробег — ровно одно число в тексте, взятое ЦЕЛИКОМ,
    длиной KM_DIGITS_MIN…KM_DIGITS_MAX цифр (группы «35 300» — одно число). Нет числа, два числа, одна цифра, восемь и
    больше цифр — пробега нет, текст возвращается как был (число остаётся словом, и согласия «все слова — согласие» не
    будет). Смысл остального текста здесь не судится — это работа decide."""
    s = str(text or "")
    found = list(re.finditer(_NUMBER, s))
    if len(found) != 1:
        return None, s
    m = found[0]
    digits = "".join(ch for ch in m.group(0) if ch.isdigit())
    if not (KM_DIGITS_MIN <= len(digits) <= KM_DIGITS_MAX):
        return None, s
    return digits, s[:m.start()] + " " + s[m.end():]


def calm_rest(text):
    """Всё, что не слова, — из белого списка YES (как в decide): для чужих словарей слов (К4 rental_case_rules)."""
    s = str(text or "").lower().replace("ё", "е")
    return _residue_ok(s, list(re.finditer(_TOKEN, s)))


def is_edit_word(w):
    """Слово о правке (основы проекта + дополнения выпуска) — для чужих словарей слов (К4 rental_case_rules)."""
    return _is_edit(str(w or "").lower().replace("ё", "е"))


def red_outcome(res, sent, action):
    """Исход activate_booking / close_booking → WRITTEN | NOT_WRITTEN | UNKNOWN.

    sent — вызов состоялся (флаг ставится строго перед ним). NOT_WRITTEN — только код из RED_NOT_WRITTEN[action]
    (мост отказал ДО записи); исключение после отправки, ответ не словарь, пустой или незнакомый код — UNKNOWN."""
    if not sent:
        return NOT_WRITTEN
    if not isinstance(res, dict):
        return UNKNOWN
    if res.get("ok"):
        return WRITTEN
    if res.get("outcome") == "unknown":
        return UNKNOWN
    if str(res.get("error") or "") in RED_NOT_WRITTEN.get(action, frozenset()):
        return NOT_WRITTEN
    return UNKNOWN
