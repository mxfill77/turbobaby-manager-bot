# -*- coding: utf-8 -*-
"""«Отправить» с подписанным PDF договора — две части, у каждой свой исход (WAPARTSEND0410, Т4б-1).
Флаг WA_AGENT_ATTACH, по умолчанию выкл: служба собирает прежний `wa_agent.Core`, поведение 24ad256 байт-в-байт.

ЧТО ЭТО. Подготовка в отдельной копии; встроит интегратор. Ядро (`wa_agent.py`) и инструменты Т4а (`wa_agent_tools.py`)
не правятся: `AttachCore` — наследник `Core`, каждое его переопределение при выключенном флаге отдаёт управление
родителю, а своих таблиц не заводит.

ОТКУДА ВЛОЖЕНИЕ. Только из сверки Т4а этого же черновика (`ModelAdapter.last["tools"]`): `attach_of` берёт PDF, если
сверка ОДНОЗНАЧНО приняла подписанный договор ЭТОЙ аренды — ровно один подписанный договор (`contract` = fact), PDF
этого договора сверен клиентом моста (`contract_pdf` = fact, id = pdf_id договора, sha256 и размер есть) и аренда из
листа (`rental` = fact) на тот же байк. Иначе вложения нет, и черновик хранит ПРИЧИНУ словами. В базе — только
метаданные (id, имя, размер, sha256, строка реестра); байты PDF берутся из `contract_pdf` в момент отправки.

ДВЕ ЧАСТИ. Текст — прежний черновик (`drafts.state`). PDF — строка `pdf_parts`: wait (ждёт текста) → claimed (захват,
байты сверяются) → sending (ДО двери) → sent · not_sent · unsure. PDF зовётся ТОЛЬКО после sent текста; текст не ушёл
или неизвестен — дверь PDF не звали, файл без текста не уходит. sha256 байтов при отправке не равен sha256 сверки —
PDF not_sent с причиной. Повтора нет: unsure двери и рестарт посреди части — «неизвестно».

«ДОСЛАТЬ PDF». Текст sent, PDF not_sent — свой захват по номеру попытки (второе нажатие — «уже решено»). PDF
«неизвестно» — сначала сверка доставки по статусам провайдера (`wa_inbox`, msg_type='status', наши wamid
исключены): подтверждена — PDF sent, дослать нельзя; не подтверждена — дослать только отдельным явным разрешением
этого повтора, со словами о риске дубля; статусы не прочитаны — дослать нельзя.

«ПЕРЕСОБРАТЬ СО СВЕРКОЙ». Ждущий черновик superseded тем же захватом (state+ver), новый проход Т4а даёт новый черновик
со своей карточкой. При флаге вкл. черновик без сверки (нет строки `attach`) не уходит: «Отправить» снимает его stale.

ЖУРНАЛ. `part_log` и строки `self.log`: кто, когда, часть, попытка, исход, wamid, sha256 — без текстов и номеров.
"""

import base64
import hashlib
import re

import wa_agent as A

F_ATTACH = "WA_AGENT_ATTACH"

ACT_REBUILD = "rebuild"           # «Пересобрать со сверкой»
ACT_PDF = "pdf"                   # «Дослать PDF»
ACT_PDF_RISK = "pdf_risk"         # «Дослать PDF — риск дубля»: отдельное явное разрешение повтора при «неизвестно»

P_WAIT, P_CLAIMED = "wait", "claimed"
PDF_MIME = "application/pdf"
STATUS_OK = ("sent", "delivered", "read")      # статус провайдера, подтверждающий, что сообщение у WhatsApp
STATUS_SKEW = 120                              # часы провайдера и наши: статус раньше попытки на столько — ещё её

W_NO_CHECK = ("устарело: черновик без сверки — при WA_AGENT_ATTACH не уходит; ничего не отправлено, "
              "черновик пересобирается")
W_TEXT_NOT = "текст не ушёл — дверь PDF не звали"
W_TEXT_UNSURE = "текст: неизвестно — PDF не шлём, файл без текста не уходит"
W_RISK = ("доставка PDF статусами провайдера не подтверждена — повтор может дать клиенту ВТОРОЙ такой же PDF; "
          "дослать можно только отдельной кнопкой «Дослать PDF — риск дубля»")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attach (
    draft_id    INTEGER PRIMARY KEY,              -- черновик, прошедший сверку Т4а при WA_AGENT_ATTACH
    file_id     TEXT,                             -- NULL — вложения нет, причина в reason
    name        TEXT,
    size        INTEGER,
    sha256      TEXT,
    row         INTEGER,                          -- строка реестра подписей
    doc_id      TEXT,
    reason      TEXT,
    ts          REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS pdf_parts (
    draft_id    INTEGER PRIMARY KEY,
    state       TEXT    NOT NULL,                 -- wait → claimed → sending → sent | not_sent | unsure
    attempt     INTEGER NOT NULL DEFAULT 1,
    who         TEXT,
    at          REAL,
    sending_at  REAL,
    wamid       TEXT,
    sha256      TEXT,
    reason      TEXT,
    permit      INTEGER NOT NULL DEFAULT 0        -- попытка по явному разрешению повтора при «неизвестно»
);
CREATE INDEX IF NOT EXISTS pdf_parts_wamid ON pdf_parts(wamid);
CREATE TABLE IF NOT EXISTS part_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id    INTEGER NOT NULL,
    part        TEXT    NOT NULL,                 -- text | pdf
    attempt     INTEGER NOT NULL,
    who         TEXT,
    at          REAL    NOT NULL,
    outcome     TEXT    NOT NULL,
    wamid       TEXT,
    sha256      TEXT,
    reason      TEXT
);
"""

_SHA = re.compile(r"^[0-9a-f]{64}$")


def enabled(env):
    """WA_AGENT_ATTACH — только «1» включает; всё прочее — выкл."""
    return str((env or {}).get(F_ATTACH) or "").strip() == "1"


def _bike(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def attach_of(tools_out):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → (метаданные PDF | None, причина словами).
    Вложение — только при однозначно принятом подписанном договоре этой аренды; иначе — почему вложения нет."""
    if not isinstance(tools_out, dict):
        return None, "сверки не было"
    if tools_out.get("state") != "done":
        return None, "сверка не завершена (%s) — вложения нет" % tools_out.get("state")
    res = [r for r in tools_out.get("results") or [] if isinstance(r, dict)]

    def by(tool):
        return [r for r in res if r.get("tool") == tool]

    con = by("contract")
    facts = [f for r in con if r.get("outcome") == "fact" for f in r.get("facts") or []]
    if not con:
        return None, "договор не сверялся (contract не звали)"
    if not facts:
        last = con[-1]
        return None, "договор не принят сверкой: %s — %s" % (last.get("outcome"), last.get("reason") or "")
    if len({f.get("doc_id") for f in facts}) != 1:
        return None, "сверка приняла разные договоры — выбрать нельзя"
    c = facts[-1]
    rent = [f for r in by("rental") if r.get("outcome") == "fact" for f in r.get("facts") or []]
    if not rent:
        why = (by("rental")[-1].get("reason") or by("rental")[-1].get("outcome")) if by("rental") else "rental не звали"
        return None, "аренда не подтверждена сверкой (%s) — договор не привязать" % why
    if len({_bike(f.get("bike")) for f in rent}) != 1 or not _bike(c.get("bike")) \
            or _bike(rent[-1].get("bike")) != _bike(c.get("bike")):
        return None, "байк аренды и договора расходится"
    pdf = [r for r in by("contract_pdf")]
    if not pdf:
        return None, "PDF договора не сверен (contract_pdf не звали)"
    pf = [f for r in pdf if r.get("outcome") == "fact" for f in r.get("facts") or []
          if str(f.get("id") or "") == str(c.get("pdf_id") or "") and c.get("pdf_id")]
    if not pf:
        bad = [r for r in pdf if r.get("outcome") != "fact"]
        if bad:
            return None, "PDF не принят сверкой: %s — %s" % (bad[-1].get("outcome"), bad[-1].get("reason") or "")
        return None, "сверен PDF не этого договора"
    p = pf[-1]
    sha = str(p.get("sha256") or "").lower()
    size = p.get("size")
    if not _SHA.match(sha) or not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return None, "у PDF нет sha256 или размера — прикладывать нельзя"
    return {"file_id": str(p.get("id")), "name": str(p.get("name") or "contract.pdf"), "size": size,
            "sha256": sha, "row": p.get("row") if p.get("row") is not None else c.get("row"),
            "doc_id": c.get("doc_id")}, ""


def parts_words(text_state, pdf_state=None, pdf_reason=""):
    """Исходы частей — рукам словами: «текст: ушёл · PDF: ушёл / не ушёл: причина / неизвестно»."""
    word = {A.SENT: "ушёл", A.NOT_SENT: "не ушёл", A.UNSURE: "неизвестно"}
    out = "текст: %s" % word.get(text_state, text_state or "?")
    if pdf_state is None:
        return out
    if pdf_state == A.NOT_SENT:
        return out + " · PDF: не ушёл: %s" % (str(pdf_reason or "причина не названа")[:200])
    return out + " · PDF: %s" % word.get(pdf_state, pdf_state)


class _Probe:
    """Модель-обёртка: после каждого черновика запоминает итог сверки Т4а по (номер, upto) — ядро о нём не знает."""

    def __init__(self, inner, seen):
        self._inner, self._seen = inner, seen

    def draft(self, number, upto_id):
        got = self._inner.draft(number, upto_id)
        last = getattr(self._inner, "last", None)
        self._seen[(number, upto_id)] = last.get("tools") if isinstance(last, dict) else None
        return got

    def __getattr__(self, name):
        return getattr(self._inner, name)


class AttachCore(A.Core):
    """Ядро с PDF договора второй частью. attach=False — каждый метод отдаёт управление `Core` (голден 24ad256)."""

    def __init__(self, *args, attach=False, pdf_fetch=None, **kw):
        self.attach = bool(attach)
        self.pdf_fetch = pdf_fetch                  # file_id → ответ `bridge_client.contract_pdf` (content_b64, verified)
        self._seen = {}
        self._hold = None                           # черновик, чей исход на карточку пишем после обеих частей
        super().__init__(*args, **kw)
        if self.attach:
            self.model = _Probe(self.model, self._seen)

    # ── база ──────────────────────────────────────────────────────────────────────────────

    def _startup(self):
        super()._startup()
        if not self.attach:
            return
        self.db.executescript(_SCHEMA)
        n1 = self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE state=?",
                             (A.UNSURE, "рестарт посреди отправки PDF — могло уйти, не повторяем", A.SENDING)).rowcount
        n2 = self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE state=?",
                             (A.NOT_SENT, "рестарт до двери PDF — не отправлено", P_CLAIMED)).rowcount
        rows = self.db.execute("SELECT p.draft_id, d.state FROM pdf_parts p JOIN drafts d ON d.id=p.draft_id "
                               "WHERE p.state=?", (P_WAIT,)).fetchall()
        for did, tstate in rows:
            if tstate in (A.SENDING, A.CLAIMED, A.PENDING, A.SCHEDULED):
                continue                            # текст ещё не решён — PDF ждёт его
            why = ("рестарт между частями — PDF не звали" if tstate == A.SENT else
                   W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT)
            self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=?",
                            (A.NOT_SENT, why, did, P_WAIT))
        if n1 or n2 or rows:
            self.log("старт: PDF sending→unsure %d, claimed→not_sent %d, ждали текста %d" % (n1, n2, len(rows)))

    def _attach(self, draft_id):
        return self.db.execute("SELECT file_id, name, size, sha256, row, reason FROM attach WHERE draft_id=?",
                               (draft_id,)).fetchone()

    def _part(self, draft_id):
        return self.db.execute("SELECT state, attempt, who, at, wamid, reason, sending_at FROM pdf_parts "
                               "WHERE draft_id=?", (draft_id,)).fetchone()

    def _plog(self, draft_id, part, attempt, who, now, outcome, wamid=None, sha=None, reason=""):
        self.db.execute("INSERT INTO part_log(draft_id, part, attempt, who, at, outcome, wamid, sha256, reason) "
                        "VALUES(?,?,?,?,?,?,?,?,?)", (draft_id, part, int(attempt), who, now, outcome, wamid, sha,
                                                      str(reason or "")[:300]))
        self.log("черновик %d: часть %s, попытка %d, %s → %s%s%s" % (
            draft_id, part, int(attempt), who, outcome, ", wamid есть" if wamid else "",
            ", sha256 %s…" % sha[:12] if sha else ""))

    # ── черновик: итог сверки → вложение или причина ───────────────────────────────────────

    def make_drafts(self, now):
        made = super().make_drafts(now)
        if not self.attach:
            return made
        for did in made:
            number, upto = self.db.execute("SELECT number, upto_id FROM drafts WHERE id=?", (did,)).fetchone()
            out = self._seen.pop((number, upto), None)
            if out is None:
                continue                            # сверки не было: строки нет — «без сверки»
            meta, why = attach_of(out)
            m = meta or {}
            self.db.execute("INSERT OR REPLACE INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, "
                            "reason, ts) VALUES(?,?,?,?,?,?,?,?,?)",
                            (did, m.get("file_id"), m.get("name"), m.get("size"), m.get("sha256"), m.get("row"),
                             m.get("doc_id"), why or None, now))
            self.log("черновик %d: вложение %s" % (
                did, "PDF договора, sha256 %s…" % m["sha256"][:12] if meta else "нет — %s" % why))
        self._seen.clear()
        return made

    # ── нажатие ───────────────────────────────────────────────────────────────────────────

    def press(self, draft_id, ver, action, who, now=None):
        if not self.attach:
            return super().press(draft_id, ver, action, who, now)
        now = self.clock() if now is None else now
        if action == ACT_REBUILD:
            return self.rebuild(draft_id, ver, who, now)
        if action in (ACT_PDF, ACT_PDF_RISK):
            return self.press_pdf(draft_id, ver, who, now, permit=action == ACT_PDF_RISK)
        # напоминание (WAFOLLOWUP0210) сверкой Т4а не строится никогда — замок «без сверки» его не касается
        if action == A.ACT_SEND and self._attach(draft_id) is None and self.draft_kind(draft_id) != A.KIND_FOLLOW:
            n = self.db.execute("UPDATE drafts SET state=?, reason=?, closed_at=? WHERE id=? AND state=? AND ver=?",
                                (A.STALE, W_NO_CHECK, now, draft_id, A.PENDING, int(ver))).rowcount
            if n != 1:
                return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
            self.log("черновик %d → stale: без сверки при WA_AGENT_ATTACH" % draft_id)
            self._done(draft_id, W_NO_CHECK, now)
            return {"ok": False, "state": A.STALE, "words": W_NO_CHECK}
        return super().press(draft_id, ver, action, who, now)

    def rebuild(self, draft_id, ver, who, now=None):
        """«Пересобрать со сверкой»: ждущий черновик superseded тем же захватом, новый проход Т4а → новый черновик."""
        now = self.clock() if now is None else now
        n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=?, closed_at=?, reason=? "
                            "WHERE id=? AND state=? AND ver=?",
                            (A.SUPERSEDED, who, now, now, "пересобран со сверкой", draft_id, A.PENDING,
                             int(ver))).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number = self.db.execute("SELECT number FROM drafts WHERE id=?", (draft_id,)).fetchone()[0]
        self.db.execute("UPDATE clients SET next_try=0 WHERE number=?", (number,))
        made = self.make_drafts(now)
        new = self.db.execute("SELECT id FROM drafts WHERE number=? AND state=? AND id>?",
                              (number, A.PENDING, draft_id)).fetchone()
        words = ("пересобран: новый черновик %d со сверкой" % new[0] if new else
                 "пересобирается: модель не дала черновика — новый придёт карточкой")
        self.log("черновик %d → superseded (пересобрать со сверкой, %s); новых черновиков %d" % (
            draft_id, who, len(made)))
        self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
        return {"ok": True, "state": A.SUPERSEDED, "words": words, "new": new[0] if new else None}

    def _done(self, draft_id, words, now):
        if self._hold == draft_id:
            return                                  # исход обеих частей ляжет на карточку одной правкой
        super()._done(draft_id, words, now)

    def _deliver(self, draft_id, number, upto, text, who, now, from_state):
        if not self.attach:
            return super()._deliver(draft_id, number, upto, text, who, now, from_state)
        meta = self._attach(draft_id)
        if not meta or not meta[0]:
            res = super()._deliver(draft_id, number, upto, text, who, now, from_state)
            self._plog(draft_id, "text", 1, who, now, res["state"] or "?", self._wamid(draft_id))
            return res
        self.db.execute("INSERT OR IGNORE INTO pdf_parts(draft_id, state, attempt) VALUES(?,?,1)", (draft_id, P_WAIT))
        self._hold = draft_id
        try:
            res = super()._deliver(draft_id, number, upto, text, who, now, from_state)
        finally:
            self._hold = None
        tstate = res.get("state")
        if tstate is None:                          # захват sending проигран — решил другой; часть ждёт его исхода
            return res
        self._plog(draft_id, "text", 1, who, now, tstate, self._wamid(draft_id))
        if tstate != A.SENT:
            why = W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT
            self.db.execute("UPDATE pdf_parts SET state=?, reason=?, who=?, at=? WHERE draft_id=? AND state=?",
                            (A.NOT_SENT, why, who, now, draft_id, P_WAIT))
            self._plog(draft_id, "pdf", 1, who, now, A.NOT_SENT, reason=why)
            pstate, preason = A.NOT_SENT, why
        else:
            pstate, preason = self._send_pdf(draft_id, number, who, now, 1, (P_WAIT,), meta)
        words = parts_words(tstate, pstate, preason)
        self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
        return dict(res, words=words, parts={"text": tstate, "pdf": pstate})

    def _wamid(self, draft_id):
        row = self.db.execute("SELECT wamid FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    # ── часть PDF ─────────────────────────────────────────────────────────────────────────

    def _send_pdf(self, draft_id, number, who, now, attempt, from_states, meta, permit=False):
        """Захват части → байты из contract_pdf и сверка sha256 → sending ДО двери → дверь → исход. → (state, reason)."""
        file_id, name, size, sha, _row, _why = meta
        q = "UPDATE pdf_parts SET state=?, attempt=?, who=?, at=?, permit=?, reason=NULL WHERE draft_id=? " \
            "AND state IN (%s)" % ",".join("?" * len(from_states))
        if self.db.execute(q, (P_CLAIMED, int(attempt), who, now, int(bool(permit)), draft_id)
                           + tuple(from_states)).rowcount != 1:
            return None, "уже решено"

        def fail(why, outcome=A.NOT_SENT):
            self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=?",
                            (outcome, why, draft_id, P_CLAIMED))
            self._plog(draft_id, "pdf", attempt, who, now, outcome, sha=sha, reason=why)
            return outcome, why

        try:
            got = self.pdf_fetch(file_id) if self.pdf_fetch else {"ok": False, "error": "двери contract_pdf нет"}
        except Exception as e:                                       # noqa: BLE001
            got = {"ok": False, "error": "дверь contract_pdf упала: %s" % type(e).__name__}
        if not (isinstance(got, dict) and got.get("ok") and got.get("verified") is True):
            err = got.get("error") if isinstance(got, dict) else "ответ не словарь"
            return fail("PDF не получен из contract_pdf: %s" % (err or "без verified"))
        try:
            raw = base64.b64decode(got.get("content_b64") or "", validate=True)
        except Exception as e:                                       # noqa: BLE001
            return fail("PDF не декодирован: %s" % type(e).__name__)
        now_sha = hashlib.sha256(raw).hexdigest()
        if now_sha != sha:
            return fail("sha256 PDF при отправке %s… не равен sha256 сверки %s… — файл изменился, не отправлено" % (
                now_sha[:12], sha[:12]))
        # ── sending ДО двери: рестарт после этой строки повтора не даст ──
        if self.db.execute("UPDATE pdf_parts SET state=?, sending_at=?, sha256=? WHERE draft_id=? AND state=?",
                           (A.SENDING, now, now_sha, draft_id, P_CLAIMED)).rowcount != 1:
            return None, "уже решено"
        media = {"kind": "document", "mime": PDF_MIME, "size": len(raw), "filename": name, "caption": "",
                 "fetch": lambda cap: (raw, "")}
        try:
            res = self.door.send_media(number, media) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = A._DOOR_STATE.get(res.get("outcome"), A.UNSURE)
        wamid = res.get("wamid") if state == A.SENT else None
        reason = A.relay_words(state, res) if state == A.NOT_SENT else str(res.get("reason") or "")[:300]
        self.db.execute("UPDATE pdf_parts SET state=?, reason=?, wamid=? WHERE draft_id=? AND state=?",
                        (state, reason, wamid, draft_id, A.SENDING))
        if state == A.SENT:
            self._sent_out(wamid, number, "", A.VIA_AGENT, now, kind="document")
        self._plog(draft_id, "pdf", attempt, who, now, state, wamid, now_sha, reason)
        return state, reason

    def delivery_check(self, number, since):
        """Статусы провайдера после попытки → ("confirmed", wamid) · ("not_confirmed", None) · ("unknown", почему).
        Наши известные wamid (черновики, outbox, PDF) — чужая часть, не эта."""
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT wamid, text FROM wa_inbox WHERE from_number=? AND msg_type='status' "
                                 "AND COALESCE(ts_msg, ts_queued) >= ? ORDER BY id",
                                 (number, float(since or 0) - STATUS_SKEW)).fetchall()
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            return "unknown", "статусы провайдера не прочитаны (%s)" % type(e).__name__
        for wamid, word in rows:
            if not wamid or str(word or "").strip().lower() not in STATUS_OK:
                continue
            if self._our_wamid(wamid) or self.db.execute("SELECT 1 FROM pdf_parts WHERE wamid=?",
                                                         (wamid,)).fetchone():
                continue
            return "confirmed", wamid
        return "not_confirmed", None

    def press_pdf(self, draft_id, attempt, who, now=None, permit=False):
        """«Дослать PDF» (attempt — номер попытки на кнопке). → {"ok", "state", "words"}."""
        now = self.clock() if now is None else now
        row = self.db.execute("SELECT number, state FROM drafts WHERE id=?", (draft_id,)).fetchone()
        part, meta = self._part(draft_id), self._attach(draft_id)
        if not row or not part or not meta or not meta[0]:
            return {"ok": False, "state": None, "words": "у черновика нет PDF-части"}
        number, tstate = row
        pstate, patt, pwho, pat, _wamid, preason, psend = part
        if int(attempt) != patt or pstate not in (A.NOT_SENT, A.UNSURE):
            return {"ok": False, "state": pstate, "words": "уже решено: PDF — %s, %s, попытка %d%s" % (
                pwho or "—", A.hm_phuket(pat) if pat else "—", patt, " — %s" % pstate)}
        if tstate != A.SENT:
            return {"ok": False, "state": pstate, "words": "дослать нельзя: %s" % (
                W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT)}
        if pstate == A.UNSURE:
            verdict, extra = self.delivery_check(number, psend)
            if verdict == "unknown":
                self.log("черновик %d: «Дослать PDF» — %s, дослать нельзя" % (draft_id, extra))
                return {"ok": False, "state": A.UNSURE, "words": "%s — дослать нельзя, PDF: неизвестно" % extra}
            if verdict == "confirmed":
                n = self.db.execute("UPDATE pdf_parts SET state=?, wamid=?, reason=? WHERE draft_id=? AND state=? "
                                    "AND attempt=?", (A.SENT, extra, "доставка подтверждена статусом провайдера",
                                                      draft_id, A.UNSURE, patt)).rowcount
                if n != 1:
                    return {"ok": False, "state": None, "words": "уже решено"}
                self._sent_out(extra, number, "", A.VIA_AGENT, now, kind="document")
                self._plog(draft_id, "pdf", patt, who, now, A.SENT, extra, reason="сверка статусов: доставлено")
                words = parts_words(A.SENT, A.SENT) + " (подтверждено статусом провайдера) — дослать нельзя"
                self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
                return {"ok": False, "state": A.SENT, "words": words}
            if not permit:
                self.log("черновик %d: «Дослать PDF» — доставка не подтверждена, нужен явный повтор" % draft_id)
                return {"ok": False, "state": A.UNSURE, "words": W_RISK, "need_permit": True}
        pstate2, why = self._send_pdf(draft_id, number, who, now, patt + 1, (pstate,), meta, permit=permit)
        if pstate2 is None:
            return {"ok": False, "state": None, "words": "уже решено: PDF — повтор уже идёт"}
        words = parts_words(A.SENT, pstate2, why)
        self._done(draft_id, "%s — дослал %s, %s%s" % (words, who, A.hm_phuket(now),
                                                        " (риск дубля принят)" if permit else ""), now)
        return {"ok": pstate2 == A.SENT, "state": pstate2, "words": words}

    def parts(self, draft_id):
        """Исходы частей черновика → {"text": state, "pdf": state | None, "words": …}."""
        row = self.db.execute("SELECT state FROM drafts WHERE id=?", (draft_id,)).fetchone()
        part = self._part(draft_id) if self.attach else None
        t = row[0] if row else None
        return {"text": t, "pdf": part[0] if part else None,
                "words": parts_words(t, part[0] if part else None, part[5] if part else "")}


def make_core(env, *args, pdf_fetch=None, **kw):
    """Флаг выкл — прежний `Core` (24ad256); вкл — `AttachCore` с дверью байтов PDF."""
    if not enabled(env):
        return A.Core(*args, **kw)
    return AttachCore(*args, attach=True, pdf_fetch=pdf_fetch, **kw)
