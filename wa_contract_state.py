# -*- coding: utf-8 -*-
"""Состояние дела договора для МОДЕЛИ — чистые функции блока фактов (CSTATE1510, вариант C).

ЗАЧЕМ. Живой случай 14.10: клиент написал «Подписал», модель ответила без договора (contract не звала) — карточку с PDF
дал только код событием подписи. Записи цепочки код уже ведёт (signed_cards, signed_asks, attach, pdf_parts, part_log,
part_status, drafts, contract_expect), но модели их не видно. Блок кладёт их в начало запроса КАЖДОГО вызова; что
ответить и какой инструмент позвать — решает модель, прикладывает и проверяет PDF по-прежнему код.

ЧТО ЗДЕСЬ. Только слова: `topic` (вопрос клиента о договоре?), `signed_claim` (клиент сообщает, что подписал?) и
`render` (факты → блок | None). Факты читает `wa_agent_cstate.read_facts` (база агента, mode=ro, только по ТОЧНОМУ
номеру); сюда приходит уже словарь фактов без текста клиента, номера и имён.

ПРАВИЛА БЛОКА. ≤ BLOCK_LINES строк и ≤ BLOCK_CHARS знаков; у каждой строки — время и источник. Время того же дня (по
Пхукету), что и чтение, — «ЧЧ:ММ» (день называет шапка «на ДД.ММ ЧЧ:ММ»); другого дня — «ДД.ММ ЧЧ:ММ», а старше
AGE_DAYS суток — ещё и с давностью словами («N сут назад»): в «ДД.ММ» нет года, и прошлогодний факт без давности читался
бы как вчерашний. Версия договора называет давность всегда, когда подписана не сегодня, и — если срок её аренды прошёл —
«аренда этой версии закончилась»: прошлый договор не выдаётся за договор нынешнего обращения. «неизвестно (…)» там, где
таблицы нет или база не прочитана, — а не «нет»; отрицательный исход реестра из уже оконченного ожидания назван прошлым
(«проверка ожидания окончена; последняя …»), а не текущим. Ни текста клиента, ни номера, ни имён, ни сумм, ни основы
«достав»; кто отправил — только ролью («сотрудник» / «автоотправка»). Блок — только если по номеру есть хотя бы одна
запись или вопрос клиента о договоре; иначе None, и запрос модели побайтно прежний.

ГРАНИЦА УСТРОЙСТВОМ: импорты ровно `re` и `datetime`; ни файлов, ни сети, ни базы (страж — ast в тесте)."""
import datetime
import re

PHUKET = datetime.timezone(datetime.timedelta(hours=7))      # = wa_agent.PHUKET_OFFSET (тест сверяет)
BLOCK_LINES, BLOCK_CHARS = 8, 1200
LINE_MAX = 135                                                # 8 строк × (2 + 135) + шапка ≤ BLOCK_CHARS (тест)
DOC_TAIL = 6                                                  # doc_id — только хвостом, не длиннее
AGE_DAYS = 7                                                  # = wa_agent_attach.STATUS_DAYS (тест сверяет)
AGE_LONG_DAYS = 60                                            # дольше — «больше 2 мес. назад» (числа из 3+ цифр в блоке нет)
STATUS_RANK = {"read": 4, "delivered": 3, "sent": 2, "failed": 1}    # ранг статуса провайдера: read > … > failed
HEAD = ("ДОГОВОР КЛИЕНТА — факты кода из базы агента на %s (Пхукет). «неизвестно» и «в базе нет» ≠ «договора нет»: "
        "реестр — contract, PDF — contract_pdf (приложит и проверит код). Служебные метки клиенту не называть.")
HEAD_START = HEAD.split(" на ")[0]                           # «ДОГОВОР КЛИЕНТА — факты кода из базы агента»

W_UNKNOWN = "неизвестно (%s)"
# версия решена: карточкой подписи · ответом модели (её сверкой) · документом, который человек отправил сам (signed_cards
# без черновика: из темы или с телефона — `wa_agent_attach._signed_human_doc`)
SRC_WORDS = {"card": "карточка подписи", "answer": "сверка ответа", "human": "документ ушёл человеком"}
OUTCOME_WORDS = {"empty": "подписанного не было", "timeout": "реестр не ответил", "refused": "дверь реестра отказала",
                 "fact": "подписанный найден", "conflict": "договор не этого клиента или аренды",
                 "ambiguous": "подписанных несколько — выбор за человеком", "cancelled": "договор отозван или отменён",
                 "unknown": "исход двери неизвестен", "incomplete": "сверка не завершена"}   # = wa_agent_tools.OUTCOMES
WHY_WORDS = {"ask": "просьба", "signed_claim": "клиент сообщил о подписи"}
ASKED_WORDS = {"pure": "чистая", "mixed": "с вопросом"}
KIND_WORDS = {"card": "карточка", "answer": "к ответу"}
WHO_WORDS = {"auto": "автоотправка", "staff": "сотрудник"}

# ── вопрос о договоре и «подписал» ───────────────────────────────────────────────────────────────────────────────
# Тема — по СЛОВУ, а не по подстроке: «Договорились», «подписка», «sign up», «signal», «Central» (เซ็นทรัล) о договоре
# не говорят. «договор» — только сам падеж (не «договорились» / «договоримся»); «подпис…/подпиш…» — кроме подписки
# (сущ.) и возвратных форм «подписаться / подпишитесь…» (подписка на канал); «sign» — кроме «sign up / in / out».
_TOPIC = re.compile(r"\bдоговор(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b|\bконтракт\w*|\bпдф\w*|\bpdfs?\b|\bcontract\w*|\bagreement|"
                    r"\bsign(?:s|ed|ing|ature|atures)?\b(?!\s+(?:up|in|out)\b)|\blease\b|สัญญา|ลงนาม|"
                    r"เซ็น(?!ทร|เตอร์)")
_SIGN_WORD = re.compile(r"\bподпи[сш]\w*")
_SIGN_NOT = re.compile(r"подписк\w*|подпис(?:ал(?:ся|ась|ись|ось)|аться|ыва(?:ться|лся|лась|лись|йся|йтесь|ется|ются|юсь|"
                       r"ешься))|подпиш(?:усь|ись|итесь|ется|утся|ешься)")
# сообщение о подписи: прошедшее время/краткое причастие, не прилагательное («подписанный договор» — не сообщение)
_CLAIM_RU = re.compile(r"\bподпис(?:ал|ала|али|ано|ан)\b")
_CLAIM_EN = re.compile(r"\b(?:i|we|i've|we've|ive|have|has|had|just|already|is|was|been|it's|its)\s+"
                       r"(?:just\s+|already\s+|now\s+)?signed\b"
                       r"|\bsigned\s+(?:it|this|that|already|now|the\s+(?:contract|agreement|document|form|lease))\b"
                       r"|(?:^|[,;:—–]\s*)\s*(?:all\s+|just\s+|already\s+)?signed(?=\s*(?:$|[,;:—–]))")
_CLAIM_TH = re.compile(r"(?:เซ็น(?!ทร|เตอร์)|ลงนาม)[^\s?]{0,12}?(?:แล้ว|เรียบร้อย)")
# отрицание самого действия перед формой; «нет» / «no» / «ไม่» сами по себе — нет («Нет-нет, я подписал»,
# «ไม่ต้องห่วง เซ็นแล้ว» — сообщения о подписи); «ไม่» ВПЛОТНУЮ перед глаголом — отказ («ไม่เซ็นแล้ว» — больше не подпишу)
_NEG = re.compile(r"\b(?:не|not|never)\b|n't|ยังไม่|ไม่ได้")
_NEG_TH_NEAR = re.compile(r"ไม่\s*$")
NEG_SPAN = 30                                                 # отрицание ищется в стольких знаках перед формой
# не сообщение о подписи: будущее/долженствование страдательным («будет подписан», «должен быть подписан»),
# сослагательное «подписал бы», «signed up» (зарегистрировался)
_FUTURE_BEFORE = re.compile(r"(?:\bбуд(?:ет|ут|у|ем|ете|ешь)|\bбыть)\s+(?:\S+\s+){0,2}$")
_AFTER_NOT = re.compile(r"^\s*(?:бы\b|up\b)")
# вопрос — по ЧАСТИ предложения с формой: «Подписал, что дальше?» — сообщение и вопрос о другом; «Вы подписали?» и
# «Вы подписали, да?» (хвост-переспрос) — вопрос; тайские частицы вопроса в той же части — вопрос («เซ็นแล้วหรือยัง»)
_CLAUSE = re.compile(r"[,;:—–]|\s-\s")
_TAG = re.compile(r"^\s*(?:да|ведь|верно|правильно|правда|так|нет|ок|ok|okay|right|yes|correct|yeah|yep|no|ага)"
                  r"(?:\s+(?:же|ведь|ли))?\s*$")
_Q_TH = re.compile(r"หรือยัง|รึยัง|หรือเปล่า|รึเปล่า|ไหม|มั้ย|มั๊ย|เหรอ|หรอ|ยัง\s*$|หรือ\s*$")
_SENT = re.compile(r"([^.!?\n]+)([.!?\n]*)")
_RAW_AT = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")
_RAW_DAY = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
_DOC_SAFE = re.compile(r"[^A-Za-z0-9_\-]")


def _norm(text):
    """Нижний регистр, ё → е, апостроф одним знаком."""
    return str(text or "").lower().replace("ё", "е").replace("’", "'").replace("`", "'")


def topic(text):
    """Вопрос клиента о договоре (договор / контракт / подпис… / PDF / contract / agreement / sign / สัญญา / เซ็น)?
    По слову: «Договорились», «подписка», «подпишитесь на канал», «sign up», «signal», «เซ็นทรัล» — нет."""
    s = _norm(text)
    if _TOPIC.search(s):
        return True
    return any(_SIGN_NOT.fullmatch(m.group(0)) is None for m in _SIGN_WORD.finditer(s))


def _asked(body, end, m):
    """Форма m — внутри вопроса? Вопрос — знак «?» в конце предложения, и часть предложения с формой до него не отделена
    запятой (или отделена лишь хвостом-переспросом «, да?»); либо тайская частица вопроса в той же части."""
    tail = body[m.end():]
    cut = _CLAUSE.search(tail)
    if _Q_TH.search(tail[:cut.start()] if cut else tail):
        return True
    if "?" not in end:
        return False
    if cut is None:
        return True
    last = _CLAUSE.split(tail)[-1]
    return _TAG.match(last) is not None


def _claim_in(body, end):
    """Одно предложение: форма «подписал» без отрицания, будущего и сослагательного рядом и не внутри вопроса."""
    hits = [m for rx in (_CLAIM_RU, _CLAIM_EN, _CLAIM_TH) for m in rx.finditer(body)]
    for m in hits:
        pre = body[max(0, m.start() - NEG_SPAN):m.start()]
        if _NEG.search(pre) or _NEG_TH_NEAR.search(pre) or _FUTURE_BEFORE.search(pre):
            continue
        if _AFTER_NOT.match(body[m.end():]) or _asked(body, end, m):
            continue
        return True
    return False


def signed_claim(text):
    """Клиент СООБЩАЕТ, что подписал договор («Подписал», «Подписал, что дальше?», «I have signed», «เซ็นสัญญาแล้ว»)?
    Отрицание («не подписал», «haven't signed», «ยังไม่ได้เซ็น», «ไม่เซ็นแล้ว»), вопрос о самой подписи («где подписать?»,
    «Вы подписали?», «เซ็นแล้วหรือยัง»), будущее («подпишу завтра», «будет подписан»), сослагательное («подписал бы»),
    «signed up» и прилагательное («пришлите подписанный договор») — нет. Направление сомнения — в «нет»: признак только
    открывает ожидание подписи (проверка реестра кодом), клиенту по нему не уходит ничего."""
    s = _norm(text)
    return any(_claim_in(m.group(1), m.group(2)) for m in _SENT.finditer(s))


# ── время и слова ────────────────────────────────────────────────────────────────────────────────────────────────

def _num(ts):
    return isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0


def _day(ts):
    return datetime.datetime.fromtimestamp(float(ts), PHUKET).date()


def dm(ts):
    """Эпоха → «ДД.ММ ЧЧ:ММ» по Пхукету; нет числа — «время неизвестно»."""
    if not _num(ts):
        return "время неизвестно"
    return datetime.datetime.fromtimestamp(float(ts), PHUKET).strftime("%d.%m %H:%M")


def age_words(days):
    """Давность в сутках (по календарю Пхукета) → слова | "" (сегодня или в будущем)."""
    if not isinstance(days, int) or days <= 0:
        return ""
    if days == 1:
        return "вчера"
    return "%d сут назад" % days if days <= AGE_LONG_DAYS else "больше 2 мес. назад"


def when(ts, now):
    """Эпоха → время строки блока: тот же день (Пхукет), что чтение, — «ЧЧ:ММ» (день называет шапка); другой —
    «ДД.ММ ЧЧ:ММ»; в прошлом на AGE_DAYS суток и больше — ещё и давность словами. Нет числа — «время неизвестно»."""
    if not _num(ts):
        return "время неизвестно"
    if not _num(now):
        return dm(ts)
    days = (_day(now) - _day(ts)).days
    if days == 0:
        return datetime.datetime.fromtimestamp(float(ts), PHUKET).strftime("%H:%M")
    return dm(ts) + (", " + age_words(days) if days >= AGE_DAYS else "")


def dm_raw(value):
    """Время реестра «гггг-мм-дд чч:мм» (уже Пхукет) → «ДД.ММ ЧЧ:ММ»; не разобрано — так и сказано."""
    m = _RAW_AT.match(str(value or ""))
    return "%s.%s %s:%s" % (m.group(3), m.group(2), m.group(4), m.group(5)) if m else "время подписи не разобрано"


def raw_day(value):
    """«гггг-мм-дд…» → дата | None (не разобрано)."""
    m = _RAW_DAY.match(str(value or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def doc_tail(doc):
    """doc_id — хвостом не длиннее DOC_TAIL знаков, только латиница, цифры, «_» и «-»."""
    return "…" + _DOC_SAFE.sub("", str(doc or ""))[-DOC_TAIL:]


def _unknown(fact):
    return isinstance(fact, dict) and "unknown" in fact


def _version_line(v, now):
    if _unknown(v):
        return "версия: " + W_UNKNOWN % v["unknown"]
    if not isinstance(v, dict):
        return "версия: в базе нет (карточки подписи и сверки ответов)"
    line = "версия: подписан %s · doc %s · %s" % (dm_raw(v.get("signed_at")), doc_tail(v.get("doc")),
                                                 SRC_WORDS.get(v.get("src"), "источник не разобран"))
    # давность и срок аренды версии: прошлый договор не выдаётся за договор нынешнего обращения (в «ДД.ММ» нет года)
    signed, today = raw_day(v.get("signed_at")), _day(now) if _num(now) else None
    note = []
    if signed and today:
        note.append(age_words((today - signed).days))
    end = raw_day(v.get("date_to"))
    if end and today and end < today:
        note.append("аренда этой версии закончилась")
    note = [x for x in note if x]
    return line + (" · " + ", ".join(note) if note else "")


def _registry_line(e, now):
    if _unknown(e):
        return "реестр: " + W_UNKNOWN % e["unknown"]
    if not isinstance(e, dict):
        return None
    words = OUTCOME_WORDS.get(e.get("outcome"), "исход не разобран")
    if _expect_live(e, now):
        if e.get("checked_at") is None:
            return "реестр: не проверялся с открытия ожидания %s" % when(e.get("opened_at"), now)
        return "реестр: проверен %s — %s (проверка ожидания)" % (when(e.get("checked_at"), now), words)
    if e.get("checked_at") is None:
        return None
    if e.get("outcome") == "fact":                            # найденный подписанный — факт и после закрытия ожидания
        return "реестр: проверен %s — %s (проверка ожидания)" % (when(e.get("checked_at"), now), words)
    # ожидание окончено: прежний исход — прошлое, а не «сейчас договора нет»
    return "реестр: проверка ожидания окончена; последняя %s — %s, сейчас не проверялся" % (
        when(e.get("checked_at"), now), words)


def _pdf_line(p, now):
    if _unknown(p):
        return "PDF клиенту: " + W_UNKNOWN % p["unknown"]
    if not isinstance(p, dict):
        return None
    state = p.get("state")
    if state == "sent":
        # кто отправил — отдельной фразой после «;»: роль «сотрудник» рядом со временем читалась бы приходом сотрудника
        return "PDF клиенту: ушёл %s; отправил: %s" % (when(p.get("at"), now), WHO_WORDS.get(p.get("who"), "сотрудник"))
    if state == "wait":
        return "PDF клиенту: ждёт нажатия (черновик с %s)" % when(p.get("at"), now)
    if state == "not_sent":
        return "PDF клиенту: не ушёл%s" % (" (%s)" % when(p.get("at"), now) if p.get("at") else "")
    return "PDF клиенту: исход неизвестен (%s) — не повторять вслепую" % when(p.get("at"), now)


def _wa_line(w, now):
    if _unknown(w):
        return "WhatsApp: " + W_UNKNOWN % w["unknown"]
    if not isinstance(w, dict):
        return None
    st, at = w.get("status"), when(w.get("at"), now)
    if st == "read":
        return "WhatsApp: прочитан %s (статус провайдера)" % at
    if st == "delivered":
        return "WhatsApp: получен телефоном %s (статус провайдера)" % at
    if st == "sent":
        return "WhatsApp: принят, получение не подтверждено (статус %s)" % at
    if st == "failed":
        return "WhatsApp: не дошёл %s (статус провайдера)" % at
    return "WhatsApp: статуса нет%s" % (" (старше 7 суток не собирается)" if w.get("old") else "")


def _human_line(h, now):
    if _unknown(h):
        return "документ человека: " + W_UNKNOWN % h["unknown"]
    if not isinstance(h, dict):
        return None
    if h.get("via") == "noted":
        # версия решена документом человека, строки темы нет (с телефона или раньше записи): время — когда код отметил
        return "документ человека: отмечен кодом %s — тема или телефон (какой — не видно)" % when(h.get("at"), now)
    return "документ человека: %s из темы (какой — не видно)" % when(h.get("at"), now)


def _ask_line(a, now):
    if _unknown(a):
        return "просьба прислать договор: " + W_UNKNOWN % a["unknown"]
    if not isinstance(a, dict):
        return None
    return "просьба прислать договор: %s, %s → %s" % (when(a.get("at"), now),
                                                      ASKED_WORDS.get(a.get("asked"), "вид не разобран"),
                                                      KIND_WORDS.get(a.get("kind"), "исход не разобран"))


def _expect_live(e, now):
    """Ожидание открыто и срок не вышел (проход ещё мог не отметить истечение — читается как есть)."""
    due = e.get("due_at")
    return e.get("state") == "open" and not (isinstance(due, (int, float)) and _num(now) and due <= now)


def _expect_line(e, now):
    if _unknown(e):
        return "ожидание подписи: " + W_UNKNOWN % e["unknown"]
    if not isinstance(e, dict):
        return None
    state, due = e.get("state"), e.get("due_at")
    if state == "open" and not _expect_live(e, now):
        state = "expired"                                     # срок вышел, проход ещё не отметил — читается как есть
    if state == "open":
        return "ожидание подписи: открыто с %s (%s), реестр проверяется сам до %s" % (
            when(e.get("opened_at"), now), WHY_WORDS.get(e.get("why"), "причина не разобрана"), when(due, now))
    if state == "closed" and e.get("closed_by") == "card":
        return "ожидание подписи: закрыто %s карточкой%s" % (when(e.get("closed_at"), now),
                                                            " (ждёт нажатия)" if e.get("card_wait") else "")
    if state == "closed":
        return "ожидание подписи: закрыто %s — версия уже решена без новой карточки" % when(e.get("closed_at"), now)
    if state == "expired":
        return "ожидание подписи: истекло %s (срок — 24 ч от сообщения клиента)" % when(due, now)
    return "ожидание подписи: состояние не разобрано"


def _cut(line):
    return line if len(line) <= LINE_MAX else line[:LINE_MAX - 1].rstrip() + "…"


def render(facts, now):
    """Факты `wa_agent_cstate.read_facts` (+ «topic» — вопрос о договоре) → блок для начала запроса модели | None.
    None — по номеру нет ни одной записи и вопрос не о договоре: запрос модели побайтно прежний."""
    if not isinstance(facts, dict) or not (facts.get("topic") or facts.get("records")):
        return None
    e = facts.get("expect")
    at = float(now)
    lines = [HEAD % dm(facts.get("read_at") or now), _version_line(facts.get("version"), at), _registry_line(e, at),
             _pdf_line(facts.get("pdf"), at), _wa_line(facts.get("wa"), at), _human_line(facts.get("human_doc"), at),
             _ask_line(facts.get("ask"), at), _expect_line(e, at)]
    out = [lines[0]] + ["• " + _cut(x) for x in lines[1:] if x]
    while len(out) > 2 and (len(out) > BLOCK_LINES or len("\n".join(out)) > BLOCK_CHARS):
        out.pop()                                             # по построению не случается: ≤ 8 строк по ≤ LINE_MAX
    return "\n".join(out)
