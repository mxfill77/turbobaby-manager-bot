"""TB-NIGHT-2210-A2 — WA case -> "🆕 БРОНЬ" intake card seam. OFF engineering code, stdlib only.

Three steps, each with an explicit data contract:

  prepare(...)   PURE. Checks every required fact and returns Prepared (card text + opaque media ref) or
                 the list of precise employee-visible reasons. Sends nothing, writes nothing.
  commit(...)    Uses an INJECTED journal (compare-and-set) and an INJECTED transport. Writes UNKNOWN
                 (in-flight) BEFORE each real send, so a crash/exception never looks like success or
                 like "not sent". One card per case_key.
  reconcile(...) Readback through the injected transport. The only way out of UNKNOWN / partial.

Nothing here knows a real Telegram/WA/Bridge API, credential, chat id or production table.
Outcome constants are bound to the actual K3 source values (see SRC_*). Consent lifetimes have no source
value and must be injected; absent -> non-actionable.
"""
import datetime
import hashlib
import json
import re

# ---- journal states (the six required states) ----
PREPARED = "prepared"
TEXT_SENT = "text_sent"
MEDIA_SENT = "media_sent"
ACCEPTED = "accepted"
FAILED = "failed"
UNKNOWN = "unknown"
STATES = (PREPARED, TEXT_SENT, MEDIA_SENT, ACCEPTED, FAILED, UNKNOWN)

# ---- consent decision values ----
C_ACCEPT, C_DECLINE, C_QUESTION, C_AMBIGUOUS = "accept", "decline", "question", "ambiguous"

CARD_PREFIX = "🆕 БРОНЬ"            # == splinter._intake_is_card / suggest.INTAKE_POST_PREFIX
SPLINTER_BIND_SEC = 300             # splinter._handle_intake: photo binds to a draft only within 300 s
BIND_MARGIN_SEC = 10                # implementation safety margin for that window (not business policy)
HIGH_FROM = (12, 15)                # task + splinter._ab_high_season docstring: 15.12–15.03
HIGH_TO = (3, 15)                   # treated INCLUSIVE here (never looser than splinter, see A2_FINAL.md)

R_PREPAY = "нужна предоплата"
R_NOT_CONFIGURED = "не настроено: сроки жизни OFFER→согласие не заданы интегратором — карточка не готовится"


# ---- source constants (K3 worktree, read by root; values only, no new policy) ----
SRC_FACT = "fact"            # wa_agent_tools.py:124  FACT, EMPTY, REFUSED, TIMEOUT
SRC_FREE = "free"            # wa_book_read.py:47     FREE, BUSY, FOUND, UNKNOWN
SRC_PRICE_NUMBER = "number"  # wa_agent_knowledge.py:31 PRICE_NUMBER; quote() outcome with day_price/total


class Config(object):
    """Outcome values default to the actual source constants above. The two consent lifetimes have NO source
    value: they must be injected by the integrator; while either is None, prepare() is non-actionable
    ("не настроено") and never produces a card. wa_agent_tools.stale() is per-call offer freshness
    (r.at vs last incoming), already applied by wa_offer_tool.accepted(); it is not a consent lifetime."""

    def __init__(self, offer_to_consent_max_sec=None, consent_max_age_sec=None, fact_outcome=SRC_FACT,
                 free_avail=SRC_FREE, exact_price_outcomes=(SRC_PRICE_NUMBER,)):
        self.fact_outcome = fact_outcome
        self.free_avail = free_avail
        self.exact_price_outcomes = frozenset(exact_price_outcomes)
        self.offer_to_consent_max_sec = offer_to_consent_max_sec
        self.consent_max_age_sec = consent_max_age_sec

    def lifetimes_ok(self):
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                   for v in (self.offer_to_consent_max_sec, self.consent_max_age_sec))


class Prepared(object):
    def __init__(self, ok, reasons, case_key=None, case_version=None, card_text=None, media_ref=None,
                 digest=None, corr=None):
        self.ok, self.reasons = ok, list(reasons)
        self.case_key, self.case_version = case_key, case_version
        self.card_text, self.media_ref, self.digest, self.corr = card_text, media_ref, digest, corr

    def as_dict(self):
        return dict(self.__dict__)


# ------------------------------------------------------------------ pure helpers

def _date(v):
    s = str(v or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def high_season(ds, de):
    """Rental from ds (pickup) to de (return) touches 15.12–15.03 of ANY season, both ends inclusive.
    Stricter than splinter._ab_high_season (half-open [ds, de) vs [15.12, 15.03)): a pickup on 15.03 or a
    return on 15.12 also counts. Year rollover: every season starting Dec of ds.year-1 .. de.year is checked."""
    for y in range(ds.year - 1, de.year + 1):
        hs = datetime.date(y, *HIGH_FROM)
        he = datetime.date(y + 1, *HIGH_TO)
        if ds <= he and de >= hs:
            return True
    return False


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v if v > 0 else None


def money_words(total):
    n = int(total) if float(total).is_integer() else total
    return ("{:,}".format(n)).replace(",", " ") + " ฿"


def _digits_have(text, total):
    """Our outgoing message names exactly this total (digits after removing spaces/commas/dots-as-separators)."""
    whole = float(total).is_integer()
    flat = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}\b)", "", str(text or ""))
    return whole and str(int(total)) in re.findall(r"\d+", flat)


_RESERVED = re.compile(r"฿|🆕|стоимость|источник согласия|бронь", re.I)


def _field(v, cap=160):
    """Single-line card field; reserved card labels inside client-supplied text are refused (None)."""
    s = re.sub(r"\s+", " ", str(v or "")).strip()[:cap]
    if _RESERVED.search(s):
        return None
    return s


def offer_fact(rec, cfg):
    """Accepted offer record (shape of wa_offer_tool.Offers._res / accepted()) -> its offer fact | None."""
    if not isinstance(rec, dict) or rec.get("outcome") != cfg.fact_outcome:
        return None
    for f in rec.get("facts") or ():
        if isinstance(f, dict) and f.get("kind") == "offer":
            return f
    return None


def offer_key(fact):
    """Identity of one priced offer. Any change of model, period, total or door time is a different offer."""
    raw = json.dumps([fact.get("model"), fact.get("date_start"), fact.get("date_end"), fact.get("total"),
                      fact.get("currency"), fact.get("door_at")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _season_high(rec):
    o = rec.get("offer") or {}
    if o.get("gate"):
        return True
    q = o.get("quote") if isinstance(o.get("quote"), dict) else {}
    s = q.get("season")
    label = s.get("label") if isinstance(s, dict) else s
    return str(label or "").lower() == "high"


# ------------------------------------------------------------------ prepare (pure)

def prepare(case, offers, consent, media, delivery, messages, cfg, now, today):
    """PURE. No send, no write, no clock read.

    case      {"case_key", "case_version", "model", "date_from", "date_to", "number", "client"?}
              current case scope as the caller's case store holds it NOW.
    offers    accepted offer records of THIS case (output of wa_offer_tool.accepted(..., last_in) at the draft
              where each was produced). The consented one must be the latest by door_at.
    consent   explicit decision {"case_key", "offer_key", "decision", "source_msg_id", "offer_msg_id",
              "agreed_total", "decided_by"}; who/what produced it is an integration decision (K3).
    media     opaque {"case_key", "media_id", "role": "passport", "downloaded": bool, "msg_id"} — never bytes.
    delivery  {"district": str} or {"url": "https://..."}.
    messages  this case's messages [{"id", "who": "клиент"|"мы", "ts", "text"}] (mapped from read_history).
    now       epoch seconds; today — Phuket date.
    -> Prepared(ok=True, card_text, media_ref, digest, corr) | Prepared(ok=False, reasons)."""
    reasons = []
    ck = (case or {}).get("case_key")
    if not ck:
        return Prepared(False, ["нет ключа дела"])
    if cfg is None or not cfg.lifetimes_ok():
        return Prepared(False, [R_NOT_CONFIGURED], ck, case.get("case_version"))
    model = (case or {}).get("model")
    ds, de = _date(case.get("date_from")), _date(case.get("date_to"))
    if not model or not _field(model) or ds is None or de is None or de <= ds:
        return Prepared(False, ["в деле нет модели или периода"], ck, case.get("case_version"))

    # 1. latest accepted FREE OFFER with exact total, matching the CURRENT case scope
    facts = [(r, offer_fact(r, cfg)) for r in (offers or ())]
    facts = [(r, f) for r, f in facts if f is not None]
    if not facts:
        return Prepared(False, ["нет принятого OFFER-факта (свободно, цена)"], ck, case.get("case_version"))
    rec, fact = max(facts, key=lambda p: (p[1].get("door_at") or 0))
    okey = offer_key(fact)
    total = _num(fact.get("total"))
    if fact.get("avail") != cfg.free_avail:
        reasons.append("последний OFFER — не «свободно»")
    if fact.get("snap_old"):
        reasons.append("OFFER по старому снимку броней")
    if fact.get("price_outcome") not in cfg.exact_price_outcomes or total is None or fact.get("currency") != "THB":
        reasons.append("в последнем OFFER нет точной цены")
    if fact.get("model") != model or _date(fact.get("date_start")) != ds or _date(fact.get("date_end")) != de:
        reasons.append("модель или период дела не совпадают с последним OFFER")

    # 2. explicit consent to THIS offer, after our message with THIS price, source = incoming msg id
    c = consent or {}
    by_id = {m.get("id"): m for m in (messages or ()) if isinstance(m, dict) and m.get("id") is not None}
    src = by_id.get(c.get("source_msg_id"))
    our = by_id.get(c.get("offer_msg_id"))
    if not c:
        reasons.append("нет согласия клиента")
    elif c.get("case_key") != ck:
        reasons.append("согласие из другого дела")
    elif c.get("decision") != C_ACCEPT:
        reasons.append("клиент не согласился явно (%s)" % (c.get("decision") or "нет решения"))
    elif c.get("offer_key") != okey:
        reasons.append("согласие дано на другой OFFER (модель, даты или цена изменились)")
    elif total is None or _num(c.get("agreed_total")) != total:
        reasons.append("сумма согласия не равна сумме OFFER")
    elif src is None or src.get("who") != "клиент":
        reasons.append("источник согласия не входящее сообщение клиента этого дела")
    elif our is None or our.get("who") != "мы" or not _digits_have(our.get("text"), total):
        reasons.append("нет нашего сообщения клиенту с этой ценой")
    else:
        t_src, t_our, t_door = src.get("ts"), our.get("ts"), fact.get("door_at")
        if not all(isinstance(t, (int, float)) for t in (t_src, t_our, t_door)):
            reasons.append("время OFFER/сообщений неизвестно")
        elif not (t_door <= t_our < t_src):
            reasons.append("согласие не после нашей цены по этому OFFER")
        elif t_src - t_door > cfg.offer_to_consent_max_sec or now - t_src > cfg.consent_max_age_sec:
            reasons.append("OFFER или согласие устарели — нужна новая сверка")
        elif "?" in str(src.get("text") or ""):
            reasons.append("в сообщении согласия есть вопрос")
        elif any(m.get("who") == "клиент" and isinstance(m.get("ts"), (int, float)) and m["ts"] > t_src
                 for m in by_id.values()):
            reasons.append("после согласия клиент писал ещё — согласие не последнее слово")

    # 3. passport media of the SAME case (opaque ref; OCR/identity stays in Splinter)
    md = media or {}
    if not md.get("media_id"):
        reasons.append("нет фото паспорта в деле")
    elif md.get("case_key") != ck:
        reasons.append("фото паспорта из другого дела")
    elif md.get("role") != "passport" or md.get("downloaded") is not True:
        reasons.append("медиа дела не помечено как скачанное фото паспорта")

    # 4. delivery place
    dv = delivery or {}
    district = _field(dv.get("district")) if dv.get("district") else ""
    url = str(dv.get("url") or "").strip()
    if district is None or (url and (not re.fullmatch(r"https://\S{4,300}", url) or _RESERVED.search(url))):
        reasons.append("место доставки содержит недопустимый текст")
    elif not district and not url:
        reasons.append("нет места доставки (район или ссылка)")

    # 5. prepayment gate (owner restriction) and same-day rule of splinter._autobook_check
    if high_season(ds, de):
        reasons.append("%s: срок %s — %s задевает высокий сезон 15.12–15.03" % (R_PREPAY, ds, de))
    elif _season_high(rec):
        reasons.append("%s: дверь цены говорит «high»" % R_PREPAY)
    if today is None or ds <= today:
        reasons.append("бронь на сегодня или раньше — только сотрудником")

    if reasons:
        return Prepared(False, reasons, ck, case.get("case_version"))

    client = _field(case.get("client")) or ""
    contacts = _field(case.get("number")) or ""
    lines = [CARD_PREFIX,
             "Клиент: %s" % client,
             "Контакты: %s" % (("WA " + contacts) if contacts else ""),
             "Модель: %s" % _field(model),
             "Начало: %s" % ds.isoformat(),
             "Конец: %s" % de.isoformat(),
             "Срок: %d сут." % (de - ds).days,
             "Доставка: %s" % " ".join(x for x in (district, url) if x),
             "Стоимость (согласовано): %s" % money_words(total),
             "Источник согласия: WA msg %s" % _field(c.get("source_msg_id"), 64)]
    card = "\n".join(lines)
    media_ref = {"case_key": ck, "media_id": md["media_id"], "msg_id": md.get("msg_id")}
    # park model = fact["model"] (checked against the case, printed on the card); the quote's own "model"
    # (quote(): q.model or model) is the TARIFF model and is never used for matching.
    digest = hashlib.sha256(json.dumps([ck, okey, c.get("source_msg_id"), md["media_id"], card],
                                       ensure_ascii=False).encode("utf-8")).hexdigest()
    corr = {"case_key": ck, "digest": digest[:16], "consent_msg_id": c.get("source_msg_id")}
    return Prepared(True, [], ck, case.get("case_version"), card, media_ref, digest, corr)


# ------------------------------------------------------------------ journal contract + reference stores

class InMemoryJournal(object):
    """Reference journal (tests). Contract: get(key) -> record|None; cas(key, expected_rev, record) -> bool,
    where expected_rev None means "create only if absent". Production store: NOT supplied (pending)."""

    def __init__(self):
        self.rows = {}

    def get(self, key):
        r = self.rows.get(key)
        return json.loads(json.dumps(r)) if r is not None else None

    def cas(self, key, expected_rev, record):
        cur = self.rows.get(key)
        fresh = (cur is None and expected_rev is None) or (cur is not None and cur["rev"] == expected_rev)
        if fresh:
            self.rows[key] = json.loads(json.dumps(record))
        return fresh


class SqliteJournal(object):
    """Reference durable journal for restart tests ONLY (own sandbox file, own throwaway schema).
    It is not a claim about, or replacement for, the production Core/IPC schema."""

    def __init__(self, path):
        import sqlite3
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS a2_ref_journal (k TEXT PRIMARY KEY, rev INTEGER, rec TEXT)")

    def get(self, key):
        row = self.db.execute("SELECT rec FROM a2_ref_journal WHERE k=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cas(self, key, expected_rev, record):
        rec = json.dumps(record, ensure_ascii=False)
        if expected_rev is None:
            cur = self.db.execute("INSERT OR IGNORE INTO a2_ref_journal (k, rev, rec) VALUES (?,?,?)",
                                  (key, record["rev"], rec))
        else:
            cur = self.db.execute("UPDATE a2_ref_journal SET rev=?, rec=? WHERE k=? AND rev=?",
                                  (record["rev"], rec, key, expected_rev))
        return cur.rowcount == 1

    def close(self):
        self.db.close()


# ------------------------------------------------------------------ commit / reconcile

def _step(journal, rec, clock, **change):
    new = dict(rec, **change)
    new["rev"] = rec["rev"] + 1
    new["updated"] = clock()
    if not journal.cas(rec["case_key"], rec["rev"], new):
        raise RuntimeError("journal moved concurrently")
    return new


def _ack(got):
    """Transport ack -> ("ok", msg_id) | ("failed", why) | ("unknown", why). Only an explicit definitive
    refusal is FAILED; missing id / odd shape is UNKNOWN (maybe posted)."""
    if isinstance(got, dict) and got.get("ok") is True and got.get("msg_id") not in (None, ""):
        return "ok", got["msg_id"]
    if isinstance(got, dict) and got.get("ok") is False and got.get("definitive") is True:
        return "failed", str(got.get("error") or "отказ транспорта")[:200]
    return "unknown", "ack без id сообщения"


def outcome(rec, note=""):
    return {"case_key": rec["case_key"] if rec else None, "state": rec["state"] if rec else None,
            "stage": rec.get("stage") if rec else None, "text_msg_id": rec.get("text_msg_id") if rec else None,
            "media_msg_id": rec.get("media_msg_id") if rec else None, "reason": rec.get("reason") if rec else None,
            "note": note}


def commit(prep, journal, transport, clock):
    """Prepared -> journal + injected transport. transport.send_text(text, corr) and
    transport.send_media(media_ref, corr, after_msg_id) return {"ok": True, "msg_id"} or
    {"ok": False, "definitive": True, "error"}; anything else or an exception -> UNKNOWN."""
    if not prep.ok:
        return {"case_key": prep.case_key, "state": None, "note": "не готово", "reasons": prep.reasons}
    key = prep.case_key
    rec = journal.get(key)
    if rec is None:
        rec = {"case_key": key, "case_version": prep.case_version, "digest": prep.digest, "state": PREPARED,
               "stage": None, "text_msg_id": None, "media_msg_id": None, "text_at": None, "reason": None,
               "rev": 1, "created": clock(), "updated": clock()}
        if not journal.cas(key, None, rec):
            return outcome(journal.get(key), "дело уже взято другим процессом")
    elif rec["digest"] != prep.digest:
        if not (rec["state"] == FAILED and rec.get("stage") == "text"):
            return outcome(rec, "по делу уже есть карточка — новая версия только сотрудником")
        rec = _step(journal, rec, clock, digest=prep.digest, case_version=prep.case_version, state=PREPARED,
                    stage=None, reason=None)
    if rec["state"] in (UNKNOWN, ACCEPTED, MEDIA_SENT) or (rec["state"] == FAILED and rec.get("stage") == "media"):
        return outcome(rec, "повтор: без отправки" if rec["state"] != UNKNOWN else "нужна сверка (reconcile)")
    if rec["state"] == FAILED:  # definitive refusal before any text: one fresh attempt per new commit call
        rec = _step(journal, rec, clock, state=PREPARED, stage=None, reason=None)

    if rec["state"] == PREPARED:
        rec = _step(journal, rec, clock, state=UNKNOWN, stage="text", reason="отправка текста начата")
        try:
            got = transport.send_text(prep.card_text, dict(prep.corr))
        except Exception as e:
            return outcome(_step(journal, rec, clock, reason="текст: исключение %s" % type(e).__name__),
                           "нужна сверка (reconcile)")
        kind, val = _ack(got)
        if kind == "failed":
            return outcome(_step(journal, rec, clock, state=FAILED, stage="text", reason=val))
        if kind == "unknown":
            return outcome(_step(journal, rec, clock, reason="текст: " + val), "нужна сверка (reconcile)")
        rec = _step(journal, rec, clock, state=TEXT_SENT, stage="text", text_msg_id=val, text_at=clock(),
                    reason=None)

    # rec["state"] == TEXT_SENT: next step (not a retry)
    if clock() - (rec.get("text_at") or 0) > SPLINTER_BIND_SEC - BIND_MARGIN_SEC:
        return outcome(_step(journal, rec, clock, state=FAILED, stage="media",
                             reason="окно привязки фото Splinter 300 с истекло — фото паспорта сотрудником"))
    rec = _step(journal, rec, clock, state=UNKNOWN, stage="media", reason="отправка фото начата")
    try:
        got = transport.send_media(dict(prep.media_ref), dict(prep.corr), rec["text_msg_id"])
    except Exception as e:
        return outcome(_step(journal, rec, clock, reason="фото: исключение %s" % type(e).__name__),
                       "нужна сверка (reconcile)")
    kind, val = _ack(got)
    if kind == "failed":
        return outcome(_step(journal, rec, clock, state=FAILED, stage="media", reason=val))
    if kind == "unknown":
        return outcome(_step(journal, rec, clock, reason="фото: " + val), "нужна сверка (reconcile)")
    return outcome(_step(journal, rec, clock, state=MEDIA_SENT, stage="media", media_msg_id=val, reason=None))


def reconcile(case_key, journal, transport, clock):
    """Readback: transport.readback(corr) -> {"text_msg_id": id|None, "media_msg_id": id|None} describing what is
    really in the group for this correlation. Exception/odd shape -> state unchanged."""
    rec = journal.get(case_key)
    if rec is None:
        return outcome(None, "дела нет в журнале")
    if rec["state"] not in (UNKNOWN, MEDIA_SENT, TEXT_SENT, FAILED):
        return outcome(rec, "сверять нечего")
    corr = {"case_key": case_key, "digest": rec["digest"][:16]}
    try:
        got = transport.readback(corr)
    except Exception as e:
        return outcome(rec, "readback не ответил (%s) — состояние прежнее" % type(e).__name__)
    if not isinstance(got, dict) or "text_msg_id" not in got or "media_msg_id" not in got:
        return outcome(rec, "readback без формы — состояние прежнее")
    t, m = got.get("text_msg_id"), got.get("media_msg_id")
    if t and m:
        return outcome(_step(journal, rec, clock, state=ACCEPTED, stage="readback", text_msg_id=t,
                             media_msg_id=m, reason=None))
    if t:
        return outcome(_step(journal, rec, clock, state=FAILED, stage="media", text_msg_id=t,
                             reason="карточка в группе, фото нет — фото паспорта сотрудником"))
    if m:
        return outcome(_step(journal, rec, clock, state=FAILED, stage="media", media_msg_id=m,
                             reason="фото без карточки — разобрать сотрудником"))
    return outcome(_step(journal, rec, clock, state=FAILED, stage="text",
                         reason="readback: ничего не опубликовано — можно подготовить заново"))
