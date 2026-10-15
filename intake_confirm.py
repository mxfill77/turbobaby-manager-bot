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


def _adjacent(s, a, b):
    """Смежны ли токены a и b: между ними в строке только пробелы (запятая и иной знак смежность рвут)."""
    return s[a.end():b.start()].strip() == ""


def _is_edit(w):
    return w.startswith(EDIT_STEMS) or w.startswith(EDIT_EXTRA_STEMS) or w in EDIT_EXTRA_WORDS


def _is_edit_noun(w):
    return w.startswith(EDIT_NOUN_STEMS)


def _is_near(w):
    if w in CONSENT_WORDS:
        return False
    return w in NEAR_CONSENT_WORDS or w.startswith(NEAR_CONSENT_STEMS) or bool(re.fullmatch(_STRETCHED, w))


def _neg_pair(w2):
    """«не» + w2 — отказ (правило (б) проекта + дополнения)."""
    return (w2 in CONSENT_WORDS or w2 in NEG_REFUSE_NEXT or w2 in NEG_REFUSE_NEXT_EXTRA
            or w2.startswith(NEG_REFUSE_STEMS) or _is_near(w2))


def _units(s, toks):
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
            if w == "не" and _neg_pair(w2):
                units.append(["refuse", i, i + 1, "neg"])        # б) «не ставь», «не надо», «не ок»
                i += 2
                continue
        if _is_edit(w):
            kind = "edit"
        elif w in REFUSE_WORDS or w.startswith(REFUSE_STEMS):
            kind = "refuse"
        elif w in CONSENT_WORDS:
            kind = "consent"
        elif _is_near(w):
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
    («отмена не нужна», «нельзя не ставить») второе отрицание переворачивает смысл — это сомнение, а не отказ."""
    if not units or units[0][0] != "refuse":
        return False
    k = 0
    while (k + 1 < len(units) and units[k + 1][0] == "refuse" and units[k][3] == "one"
           and toks[units[k][1]].group(0) in REFUSE_CHAIN_WORDS
           and _units_adjacent(s, toks, units[k], units[k + 1])):
        k += 1
    return k + 1 == len(units) or not _units_adjacent(s, toks, units[k], units[k + 1])


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


def decide(text):
    """Ответ подтверждающего → YES | NO | EDIT | ASK | SILENT. Каркас — порядок проекта §2.1, дополнения
    (почти-согласие, ясность отказа, отрицание при правке, белый список знаков рядом с согласием) названы выше."""
    s = str(text or "").lower().replace("ё", "е")
    if re.fullmatch(_PLUS_ONLY, s):
        return ASK                                               # «+», «++», «+1» — как 👍: переспрос
    toks = list(re.finditer(_TOKEN, s))
    if not toks:
        marks = CONSENT_EMOJI + REFUSE_EMOJI + DOUBT_EMOJI
        return ASK if any(e in s for e in marks) else SILENT
    units = _units(s, toks)
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
