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

ОСНОВАНИЕ — ОПОРА СУДЬИ (T4B3BASIS0510, Т4б-3). Факты берутся не из сырых `results`, а после `wa_agent_tools.sift` с
`since` = последнее входящее клиента (`ModelAdapter.last["info"]["last_in"]`) — та же опора, на которой стоит judge:
поздний отказ того же запроса и чтение раньше последнего входящего основание снимают. В `attach` — версия договора
(`signed_at`, без неё вложения нет) и ключ перечитывания: номер обращения и срок аренды.

ПЕРЕЧИТЫВАНИЕ ПЕРЕД ОТПРАВКОЙ. Дверь `contract_find` — параметром, как `pdf_fetch`. «Отправить» черновика с PDF
перечитывает реестр ДО текстовой части, «Дослать PDF» — ДО PDF. Пропуск (`recheck_of`) — только `one`, пустой `unread`,
`undated_signed` = 0, подписанный `pick` и совпавшие row, doc_id, pdf_id и signed_at. Иначе (отзыв, новая версия,
второй подписанный, неполный ответ, дверь упала или ответ не разобран): «Отправить» — черновик stale с причиной,
ничего не отправлено, пересборка со сверкой (как W_NO_CHECK); «Дослать» — отказ с причиной, PDF не уходит.

ДВЕ ЧАСТИ. Текст — прежний черновик (`drafts.state`). PDF — строка `pdf_parts`: wait (ждёт текста) → claimed (захват,
байты сверяются) → sending (ДО двери) → sent · not_sent · unsure. PDF зовётся ТОЛЬКО после sent текста; текст не ушёл
или неизвестен — дверь PDF не звали, файл без текста не уходит. sha256 байтов при отправке не равен sha256 сверки —
PDF not_sent с причиной. Повтора нет: unsure двери и рестарт посреди части — «неизвестно».

«ДОСЛАТЬ PDF». Текст sent, PDF not_sent — захват сравнением-и-записью с ОЖИДАЕМЫМ номером попытки (кнопка несёт
его; устаревший номер и второе нажатие — «уже решено»). PDF «неизвестно» — сначала статусы провайдера.

ПРАВДА О ДОСТАВКЕ (WAPARTFIX0410). Подтверждает PDF только статус с wamid ЭТОЙ попытки (`delivery_check`): delivered
или read — доставлен; sent — «принято WhatsApp», это ещё не доставка; у попытки нет wamid — исход остаётся
«неизвестно», чужим статусом он не подтверждается никогда. Статус неизвестного нам сообщения после попытки
(`_foreign_after`) — не подтверждение, а улика возможного дубля: PDF «неизвестно», дослать кнопкой нельзя. Чужих
статусов нет — дослать только отдельным явным разрешением повтора, со словами о риске дубля; статусы не прочитаны —
дослать нельзя. ПРЕДЕЛ: попытка «неизвестно» wamid не получает никогда (дверь не назвала id сообщения) — без wamid
подтверждения нет, доставленной система её не назовёт; решает человек.

«ПЕРЕСОБРАТЬ СО СВЕРКОЙ». Ждущий черновик superseded тем же захватом (state+ver), новый проход Т4а даёт новый черновик
со своей карточкой. При флаге вкл. черновик без сверки (нет строки `attach`) не уходит: «Отправить» снимает его stale.

ЖУРНАЛ. `part_log` и строки `self.log`: кто, когда, часть, попытка, исход, wamid, sha256 — без текстов и номеров.
"""

import base64
import hashlib
import re

import wa_agent as A
import wa_agent_tools as T

F_ATTACH = "WA_AGENT_ATTACH"

ACT_REBUILD = "rebuild"           # «Пересобрать со сверкой»
ACT_PDF = "pdf"                   # «Дослать PDF»
ACT_PDF_RISK = "pdf_risk"         # «Дослать PDF — риск дубля»: отдельное явное разрешение повтора при «неизвестно»

P_WAIT, P_CLAIMED = "wait", "claimed"
PDF_MIME = "application/pdf"
STATUS_DELIVERED = ("delivered", "read")       # доставка — только эти статусы
STATUS_ACCEPTED = "sent"                       # «принято WhatsApp» — у WhatsApp, но клиенту ещё не доставлено
STATUS_ANY = (STATUS_ACCEPTED,) + STATUS_DELIVERED
STATUS_SKEW = 120                              # часы провайдера и наши: статус раньше попытки на столько — ещё её
D_DELIVERED, D_ACCEPTED, D_UNKNOWN = "delivered", "accepted", "unknown"

W_NO_CHECK = ("устарело: черновик без сверки — при WA_AGENT_ATTACH не уходит; ничего не отправлено, "
              "черновик пересобирается")
W_TEXT_NOT = "текст не ушёл — дверь PDF не звали"
W_TEXT_UNSURE = "текст: неизвестно — PDF не шлём, файл без текста не уходит"
W_RISK = ("доставка PDF статусами провайдера не подтверждена — повтор может дать клиенту ВТОРОЙ такой же PDF; "
          "дослать можно только отдельной кнопкой «Дослать PDF — риск дубля»")
W_FOREIGN = ("после попытки есть статус сообщения, которого мы не знаем (%d) — возможно, это PDF; доставкой его не "
             "считаем: PDF — неизвестно; дослать кнопкой нельзя, повтор может дать дубль — проверьте переписку")
W_BASIS = "устарело: основание PDF не подтверждено реестром при нажатии — %s; ничего не отправлено, черновик пересобирается"
W_BASIS_PDF = "дослать нельзя: основание PDF не подтверждено реестром — %s; PDF не ушёл"
BASIS_COLS = (("signed_at", "TEXT"), ("number", "TEXT"), ("date_from", "TEXT"), ("date_to", "TEXT"))

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
    ts          REAL    NOT NULL,
    signed_at   TEXT,                             -- версия договора при сверке (T4B3BASIS0510)
    number      TEXT,                             -- ключ перечитывания: номер обращения …
    date_from   TEXT,                             -- … и срок аренды (ISO, пусто — неизвестен)
    date_to     TEXT
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


def _day(v):
    d = T.B.day_of(v) if v not in (None, "") else None
    return d.isoformat() if d is not None else ""


def _term(res, c, rent):
    """Срок аренды для перечитывания: окно привязки договора кодом (`bind_contract`, ISO «a…b») — иначе дни аренды."""
    key = T.fact_key(c)
    for r in reversed(res):
        if r.get("tool") == "contract" and r.get("outcome") == T.FACT and \
                any(isinstance(f, dict) and T.fact_key(f) == key for f in r.get("facts") or []):
            a, _, b = str(r.get("window") or "").partition("…")
            if _day(a) and _day(b):
                return _day(a), _day(b)
            break
    return _day(rent.get("date_start")), _day(rent.get("date_end"))


def attach_of(tools_out, since=None):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → (метаданные PDF | None, причина словами).
    Вложение — только при однозначно принятом подписанном договоре этой аренды В ОПОРЕ СУДЬИ (`sift` с `since` =
    последнее входящее клиента, T4B3BASIS0510); иначе — почему вложения нет."""
    if not isinstance(tools_out, dict):
        return None, "сверки не было"
    if tools_out.get("state") != "done":
        return None, "сверка не завершена (%s) — вложения нет" % tools_out.get("state")
    res = [r for r in tools_out.get("results") or [] if isinstance(r, dict)]
    try:
        facts, dropped = T.sift(res, since)
    except Exception as e:                                           # noqa: BLE001
        return None, "опора сверки не разобрана (%s) — вложения нет" % type(e).__name__

    def by(tool):
        return [r for r in res if r.get("tool") == tool]

    def kind(k):
        return [f for f in facts if isinstance(f, dict) and f.get("kind") == k]

    def snapped(tool, what):
        why = [d for d in dropped if d.startswith(tool + ":") or d.startswith(what + ":")]
        return "%s снят опорой судьи: %s — вложения нет" % (
            {"contract": "договор", "rental": "аренда", "contract_pdf": "PDF"}[tool], why[-1] if why else "не опора")

    con = by("contract")
    cfs = kind("contract")
    if not con:
        return None, "договор не сверялся (contract не звали)"
    if not cfs:
        if any(r.get("outcome") == T.FACT for r in con):
            return None, snapped("contract", "contract")
        last = con[-1]
        return None, "договор не принят сверкой: %s — %s" % (last.get("outcome"), last.get("reason") or "")
    if len({f.get("doc_id") for f in cfs}) != 1:
        return None, "сверка приняла разные договоры — выбрать нельзя"
    c = cfs[-1]
    rent = kind("rental")
    if not rent:
        if any(r.get("outcome") == T.FACT for r in by("rental")):
            return None, snapped("rental", "rental")
        why = (by("rental")[-1].get("reason") or by("rental")[-1].get("outcome")) if by("rental") else "rental не звали"
        return None, "аренда не подтверждена сверкой (%s) — договор не привязать" % why
    if len({_bike(f.get("bike")) for f in rent}) != 1 or not _bike(c.get("bike")) \
            or _bike(rent[-1].get("bike")) != _bike(c.get("bike")):
        return None, "байк аренды и договора расходится"
    pdf = [r for r in by("contract_pdf")]
    if not pdf:
        return None, "PDF договора не сверен (contract_pdf не звали)"
    pf = [f for f in kind("pdf") if str(f.get("id") or "") == str(c.get("pdf_id") or "") and c.get("pdf_id")]
    if not pf:
        if any(r.get("outcome") == T.FACT and any(str((f or {}).get("id") or "") == str(c.get("pdf_id") or "")
                                                  for f in r.get("facts") or []) for r in pdf) and c.get("pdf_id"):
            return None, snapped("contract_pdf", "pdf")
        bad = [r for r in pdf if r.get("outcome") != T.FACT]
        if bad:
            return None, "PDF не принят сверкой: %s — %s" % (bad[-1].get("outcome"), bad[-1].get("reason") or "")
        return None, "сверен PDF не этого договора"
    p = pf[-1]
    sha = str(p.get("sha256") or "").lower()
    size = p.get("size")
    if not _SHA.match(sha) or not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return None, "у PDF нет sha256 или размера — прикладывать нельзя"
    signed_at = str(c.get("signed_at") or "").strip()
    if not signed_at:
        return None, "у договора нет signed_at — версию перед отправкой не сверить, вложения нет"
    date_from, date_to = _term(res, c, rent[-1])
    return {"file_id": str(p.get("id")), "name": str(p.get("name") or "contract.pdf"), "size": size,
            "sha256": sha, "row": p.get("row") if p.get("row") is not None else c.get("row"),
            "doc_id": c.get("doc_id"), "signed_at": signed_at, "date_from": date_from, "date_to": date_to}, ""


def recheck_of(resp, basis):
    """Живое чтение реестра (`contract_find`) против основания черновика → (True, "") | (False, причина словами).
    Пропуск — только `one`, пустой `unread`, `undated_signed` = 0, подписанный `pick` и совпавшие row, doc_id, pdf_id и
    signed_at. Всё прочее — отказ: перечитать не удалось, ответ не разобран, отзыв, новая версия, второй подписанный."""
    if not isinstance(basis, dict) or not str(basis.get("signed_at") or "").strip():
        return False, "версия договора при сверке не записана — перечитать не с чем"
    if not isinstance(resp, dict):
        return False, "ответ реестра не разобран (не словарь)"
    if not resp.get("ok"):
        return False, "реестр не прочитан: %s" % (str(resp.get("error") or "ответ без ok")[:120])
    out = resp.get("outcome")
    checked = resp.get("checked") if isinstance(resp.get("checked"), dict) else None
    if out == "ambiguous":
        return False, "в реестре подписанных несколько — второй подписанный договор, выбрать нельзя"
    if out == "incomplete":
        return False, "ответ реестра неполон — подписанный без известного дня"
    if out == "none_signed":
        return False, "подписанного договора больше нет — договор отозван"
    if out == "none":
        return False, "договор в реестре не найден — договор отозван или убран"
    if out != "one":
        return False, "исход реестра не разобран: %s" % str(out)[:40]
    if checked is None:
        return False, "ответ реестра не разобран: нет checked"
    unread, undated = checked.get("unread"), checked.get("undated_signed")
    if not isinstance(unread, list) or not isinstance(undated, int) or isinstance(undated, bool):
        return False, "ответ реестра не разобран: нет полей полноты unread/undated_signed"
    if unread:
        return False, "реестр прочитан не целиком (не прочитано: %s)" % ", ".join(str(u) for u in unread)[:120]
    if undated != 0:
        return False, "подписанных без известного дня %d" % undated
    pick = resp.get("pick")
    if not isinstance(pick, dict):
        return False, "ответ реестра не разобран: нет pick"
    if pick.get("signed") is not True:
        return False, "договор не подписан — отозван"
    for key, have, want in (("row", pick.get("row"), basis.get("row")),
                            ("doc_id", pick.get("doc_id"), basis.get("doc_id")),
                            ("pdf_id", pick.get("pdf_id"), basis.get("file_id")),
                            ("signed_at", pick.get("signed_at"), basis.get("signed_at"))):
        if str(have if have is not None else "").strip() != str(want if want is not None else "").strip():
            return False, "договор сменился: %s при сверке %s, в реестре сейчас %s" % (
                key, str(want)[:40], str(have)[:40])
    return True, ""


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
        tools = last.get("tools") if isinstance(last, dict) else None
        info = last.get("info") if isinstance(last, dict) and isinstance(last.get("info"), dict) else {}
        # since — то же последнее входящее клиента, что судья получает в judge(since=info["last_in"]) (T4B3BASIS0510)
        self._seen[(number, upto_id)] = None if tools is None else (tools, info.get("last_in"))
        return got

    def __getattr__(self, name):
        return getattr(self._inner, name)


class AttachCore(A.Core):
    """Ядро с PDF договора второй частью. attach=False — каждый метод отдаёт управление `Core` (голден 24ad256)."""

    def __init__(self, *args, attach=False, pdf_fetch=None, contract_find=None, **kw):
        self.attach = bool(attach)
        self.pdf_fetch = pdf_fetch                  # file_id → ответ `bridge_client.contract_pdf` (content_b64, verified)
        self.contract_find = contract_find          # (phone, date_from, date_to) → ответ `bridge_client.contract_find`
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
        have = {r[1] for r in self.db.execute("PRAGMA table_info(attach)").fetchall()}
        for col, typ in BASIS_COLS:                 # база до T4B3BASIS0510: строки без версии — перечитать не с чем
            if col not in have:
                self.db.execute("ALTER TABLE attach ADD COLUMN %s %s" % (col, typ))
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

    def _basis(self, draft_id):
        """Основание PDF черновика: версия договора и ключ перечитывания (T4B3BASIS0510)."""
        row = self.db.execute("SELECT file_id, row, doc_id, signed_at, number, date_from, date_to FROM attach "
                              "WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return None
        return dict(zip(("file_id", "row", "doc_id", "signed_at", "number", "date_from", "date_to"), row))

    def _recheck(self, draft_id, number):
        """Живое чтение реестра перед отправкой → (True, "") | (False, причина). Дверь упала или её нет — отказ."""
        basis = self._basis(draft_id) or {}
        if not callable(self.contract_find):
            return False, "двери contract_find нет — реестр не перечитан"
        try:
            got = self.contract_find(phone=str(basis.get("number") or number or ""),
                                     date_from=str(basis.get("date_from") or ""), date_to=str(basis.get("date_to") or ""))
        except Exception as e:                                       # noqa: BLE001
            return False, "дверь contract_find упала: %s" % type(e).__name__
        try:
            return recheck_of(got, basis)
        except Exception as e:                                       # noqa: BLE001
            return False, "ответ реестра не разобран (%s)" % type(e).__name__

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
            seen = self._seen.pop((number, upto), None)
            if seen is None:
                continue                            # сверки не было: строки нет — «без сверки»
            out, since = seen
            meta, why = attach_of(out, since)       # опора судьи: sift с since = последнее входящее (T4B3BASIS0510)
            m = meta or {}
            self.db.execute("INSERT OR REPLACE INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, "
                            "reason, ts, signed_at, number, date_from, date_to) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (did, m.get("file_id"), m.get("name"), m.get("size"), m.get("sha256"), m.get("row"),
                             m.get("doc_id"), why or None, now, m.get("signed_at"), number if meta else None,
                             m.get("date_from"), m.get("date_to")))
            self.log("черновик %d: вложение %s" % (
                did, "PDF договора, sha256 %s…" % m["sha256"][:12] if meta else "нет — %s" % why))
        self._seen.clear()
        return made

    # ── нажатие ───────────────────────────────────────────────────────────────────────────

    def press(self, draft_id, ver, action, who, now=None, who_id=None):
        # who_id — id нажавшего (NIGHT0710-B2): пробрасывается ядру, иначе руки уронили бы нажатие TypeError'ом молча
        if not self.attach:
            return super().press(draft_id, ver, action, who, now, who_id=who_id)
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
        return super().press(draft_id, ver, action, who, now, who_id=who_id)

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
        ok, why = self._recheck(draft_id, number)   # реестр перечитан ДО текстовой части (T4B3BASIS0510)
        if not ok:
            words = W_BASIS % why
            if not self._close(draft_id, A.STALE, words, now, from_states=(from_state,)):
                return {"ok": False, "state": None, "words": self._decided(draft_id)}
            self.log("черновик %d → stale: основание PDF не подтверждено реестром при нажатии — ничего не отправлено"
                     % draft_id)
            return {"ok": False, "state": A.STALE, "words": words}
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
            pstate, preason = self._send_pdf(draft_id, number, who, now, 1, (P_WAIT,), meta, prev=1)
        words = parts_words(tstate, pstate, preason)
        self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
        return dict(res, words=words, parts={"text": tstate, "pdf": pstate})

    def _wamid(self, draft_id):
        row = self.db.execute("SELECT wamid FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    # ── часть PDF ─────────────────────────────────────────────────────────────────────────

    def _send_pdf(self, draft_id, number, who, now, attempt, from_states, meta, permit=False, prev=None):
        """Захват части → байты из contract_pdf и сверка sha256 → sending ДО двери → дверь → исход. → (state, reason).
        Захват — сравнение-и-запись: состояние из `from_states` И номер попытки равен ожидаемому `prev` (номер на кнопке).
        Номер уже сменился (другое нажатие решило раньше) — строк 0, «уже решено», двери нет."""
        file_id, name, size, sha, _row, _why = meta
        q = "UPDATE pdf_parts SET state=?, attempt=?, who=?, at=?, permit=?, reason=NULL WHERE draft_id=? " \
            "AND attempt=? AND state IN (%s)" % ",".join("?" * len(from_states))
        if self.db.execute(q, (P_CLAIMED, int(attempt), who, now, int(bool(permit)), draft_id, int(prev))
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

    def delivery_check(self, number, wamid):
        """Статусы провайдера по ТОЧНОМУ wamid попытки → (исход, слова). Исходы: delivered (delivered/read) ·
        accepted (только sent: «принято WhatsApp», не доставка) · unknown (wamid нет, статуса нет, не прочитано).
        Без wamid попытки подтверждать нечем: чужой статус этой попытке не принадлежит никогда."""
        if not wamid:
            return D_UNKNOWN, "у попытки нет wamid — статусом её не подтвердить"
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT text FROM wa_inbox WHERE wamid=? AND from_number=? AND msg_type='status'",
                                 (wamid, number)).fetchall()
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            return D_UNKNOWN, "статусы провайдера не прочитаны (%s)" % type(e).__name__
        words = {str(w or "").strip().lower() for (w,) in rows}
        hit = [w for w in STATUS_DELIVERED if w in words]
        if hit:
            return D_DELIVERED, "доставлен (статус %s по wamid попытки)" % hit[-1]
        if STATUS_ACCEPTED in words:
            return D_ACCEPTED, "принято WhatsApp (статус sent по wamid попытки) — доставка не подтверждена"
        return D_UNKNOWN, "статуса по wamid попытки нет"

    def _foreign_after(self, number, since):
        """Статусы НЕИЗВЕСТНЫХ нам сообщений этого номера после попытки → список wamid; None — не прочитаны.
        Наши wamid (черновики, outbox, PDF) — не они. Это не подтверждение доставки, а улика возможного дубля."""
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT wamid, text FROM wa_inbox WHERE from_number=? AND msg_type='status' "
                                 "AND COALESCE(ts_msg, ts_queued) >= ? ORDER BY id",
                                 (number, float(since or 0) - STATUS_SKEW)).fetchall()
            finally:
                q.close()
        except Exception:                                            # noqa: BLE001
            return None
        out = []
        for wamid, word in rows:
            if not wamid or str(word or "").strip().lower() not in STATUS_ANY:
                continue
            if self._our_wamid(wamid) or self.db.execute("SELECT 1 FROM pdf_parts WHERE wamid=?",
                                                         (wamid,)).fetchone():
                continue
            out.append(wamid)
        return out

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
            verdict, extra = self.delivery_check(number, _wamid)
            if verdict in (D_DELIVERED, D_ACCEPTED):
                # статус ТОЧНОГО wamid этой попытки: WhatsApp сообщение взял — PDF sent, повтор был бы дублем
                n = self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=? "
                                    "AND attempt=?", (A.SENT, extra, draft_id, A.UNSURE, patt)).rowcount
                if n != 1:
                    return {"ok": False, "state": None, "words": "уже решено"}
                self._sent_out(_wamid, number, "", A.VIA_AGENT, now, kind="document")
                self._plog(draft_id, "pdf", patt, who, now, A.SENT, _wamid, reason="сверка статусов: %s" % verdict)
                words = parts_words(A.SENT, A.SENT) + " (%s) — дослать нельзя" % extra
                self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
                return {"ok": False, "state": A.SENT, "words": words, "delivery": verdict}
            foreign = self._foreign_after(number, psend)
            if foreign is None:
                why = "статусы провайдера не прочитаны"
                self.log("черновик %d: «Дослать PDF» — %s, дослать нельзя" % (draft_id, why))
                return {"ok": False, "state": A.UNSURE, "words": "%s — дослать нельзя, PDF: неизвестно" % why}
            if foreign:
                self.log("черновик %d: «Дослать PDF» — после попытки статусы неизвестных сообщений: %d, "
                         "PDF неизвестно, дослать нельзя" % (draft_id, len(foreign)))
                return {"ok": False, "state": A.UNSURE, "words": W_FOREIGN % len(foreign), "delivery": D_UNKNOWN}
            if not permit:
                self.log("черновик %d: «Дослать PDF» — доставка не подтверждена, нужен явный повтор" % draft_id)
                return {"ok": False, "state": A.UNSURE, "words": W_RISK, "need_permit": True}
        ok, basis_why = self._recheck(draft_id, number)     # реестр перечитан ДО PDF (T4B3BASIS0510)
        if not ok:
            self.log("черновик %d: «Дослать PDF» — основание не подтверждено реестром, PDF не ушёл" % draft_id)
            return {"ok": False, "state": pstate, "words": W_BASIS_PDF % basis_why}
        pstate2, why = self._send_pdf(draft_id, number, who, now, patt + 1, (pstate,), meta, permit=permit,
                                      prev=int(attempt))
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
        out = {"text": t, "pdf": part[0] if part else None,
               "words": parts_words(t, part[0] if part else None, part[5] if part else "")}
        if part:
            # «ушёл» — дверь приняла; доставку говорит ТОЛЬКО статус wamid этой попытки (sent — «принято WhatsApp»)
            num = self.db.execute("SELECT number FROM drafts WHERE id=?", (draft_id,)).fetchone()
            out["delivery"] = self.delivery_check(num[0] if num else None, part[4])
        return out


def make_core(env, *args, pdf_fetch=None, contract_find=None, **kw):
    """Флаг выкл — прежний `Core` (24ad256); вкл — `AttachCore` с дверью байтов PDF и дверью реестра договоров."""
    if not enabled(env):
        return A.Core(*args, **kw)
    return AttachCore(*args, attach=True, pdf_fetch=pdf_fetch, contract_find=contract_find, **kw)
