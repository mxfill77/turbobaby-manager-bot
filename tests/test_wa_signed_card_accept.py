#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ВЫПУСКА «подписанный договор → одна карточка с PDF» (wa-agent, прод 76993f3). Чёрный ящик по ИНТЕРФЕЙСУ
выпуска, написан БЕЗ реализации: AttachCore(..., attach=True, signed=True, pdf_fetch=…, contract_find=…),
make_signed_cards(now), таблица signed_cards, drafts.kind='signed', строка attach, тексты шаблона, водораздел
signed_since, wa_agent_attach.SIGNED_EVERY, строка старта WA_AGENT_SIGNED_CARD в wa_agent_svc. Черновик клиенту не
уходит НИКОГДА без нажатия «Отправить» — это проверяется в каждом положительном случае.

ДВЕРИ ЖИВОГО ФОРМАТА, ДАННЫЕ СИНТЕТИЧЕСКИЕ (живой пример 14.10): номер 79999966963, байк «NINJA 400СС PHUKET 6334»,
аренда 2026-10-14..2026-10-17; реестр TB e-Sign: стр.34 ОТОЗВАН 17:47, стр.35 ОТОЗВАН 18:37, стр.36 ПОДПИСАН 19:04 с
pdf_id; телефон в контактах аренды — с неразрывными дефисами U+2011.
  · contract_find — форма `bridge_client.contract_find`: outcome one/ambiguous/none_signed/none, pick, checked
    (unread, undated_signed, complete), filter.phone_last9; без phone/name/bike — `no_filter`, как мост;
  · contract_pdf — форма `bridge_client.contract_pdf`: verified ставит КЛИЕНТ по байтам (не сошлись — ok:false,
    pdf_mismatch);
  · аренда — ТОЙ ЖЕ дверью, что у модели: модель — наследник `wa_agent_model.ModelAdapter` (переопределён только
    `draft`, языковая модель не зовётся), снимок броней — настоящий `wa_book_read.Snapshot` над поддельной дверью
    clients (`ModelAdapter._tool_doors` → rental фильтрует активные аренды по телефону, как в проде).
Сети нет: мост, модель, Telegram и WhatsApp — подделки; базы — временные (tempfile).

ТОЧКА ПОДСТРОЙКИ ОДНА — `World.new_core`: если реализация берёт дверь аренды именованным аргументом AttachCore, а не у
модели, аргумент с «rental» в имени получает `Rig.rental_door` (номер → ответ двери аренды модели).

ДЕРЕВО БЕЗ РЕАЛИЗАЦИИ (76993f3): набор падает по понятной причине — test_00_interface называет, чего нет (параметра
signed, метода make_signed_cards, SIGNED_EVERY); прочие случаи падают TypeError на `signed=`. test_01_fixture… и
test_blind_readers… проходят и там: первый доказывает СУЩЕСТВУЮЩИМ кодом (call_tool → attach_of → recheck_of), что
подделки дают FACT привязки и метаданные PDF, — красное в остальных случаях принадлежит выпуску, а не стенду.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import calendar
import hashlib
import inspect
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])
os.environ.pop("WA_AGENT_SIGNED_LOOKBACK_H", None)        # водораздел — умолчание выпуска: 6 ч

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_book_read as B  # noqa: E402
import k3_pdf_fixture  # noqa: E402  (скелет PDF сверяется перед дверью — фикстура живого формата)

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

PHUKET = 7 * 3600


def ts_of(local):
    """'yyyy-MM-dd HH:mm' по Пхукету (формат signed_at реестра) → эпоха."""
    return calendar.timegm(time.strptime(local, "%Y-%m-%d %H:%M")) - PHUKET


def local_of(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(ts) + PHUKET))


# ── живой пример (синтетика того же формата) ─────────────────────────────────────────────
NUM = "79999966963"
OTHER = "66812345678"
BIKE = "NINJA 400СС PHUKET 6334"
CONTACTS = "Иван +7 999‑996‑69‑63"            # копия из WhatsApp: неразрывные дефисы
CPHONE = "+7 999 996 69 63"                                     # телефон договора в реестре
SIGNED, REVOKED, SENT_FOR_SIGN = "ПОДПИСАН", "ОТОЗВАН", "ОТПРАВЛЕН"
S34, S35, S36, S37 = "2026-10-14 17:47", "2026-10-14 18:37", "2026-10-14 19:04", "2026-10-14 19:40"

T_START = ts_of("2026-10-14 18:00")      # первый старт службы С ФЛАГОМ
WATERSHED = T_START - 6 * 3600           # signed_since по умолчанию: 12:00 Пхукета
SIGN36 = ts_of(S36)
T_IN = SIGN36 + 60                       # клиент: «Подписал» в 19:05
T_CARD = SIGN36 + 600                    # такт карточки в 19:14 — 10 мин после подписи, без извинения
EVERY = 120                              # SIGNED_EVERY интерфейса
WINDOW_OPEN = 24 * 3600 - 30 * 60        # окно 24 ч минус запас 30 мин (правило напоминания ядра)

PDF = {n: k3_pdf_fixture.classic(("TB e-Sign row %d NINJA 6334" % n).encode()) for n in (34, 35, 36, 37)}
SHA = {n: hashlib.sha256(d).hexdigest() for n, d in PDF.items()}

RU, EN = "Направляем ваш подписанный договор.", "Here is your signed rental agreement."
RU_SORRY = "Извините за задержку с ответом и договором. "
EN_SORRY = "Sorry for the delay with our reply and the agreement. "
REPLACED = "заменён карточкой подписанного договора"
LINE_KEY = "карточка после подписи (WA_AGENT_SIGNED_CARD):"
LABEL = "📄 Договор подписан"
KEEP = object()


class Crash(BaseException):
    """Смерть процесса посреди вызова: except Exception её не ловит."""


def reg_row(n, status, signed_at, **over):
    """Строка реестра подписей — запись `contract_find` (items/pick)."""
    r = {"row": n, "doc_id": "DOC-%d" % n, "client": "Ivan Petrov", "contract_date": "2026-10-14",
         "contract_date_raw": "14.10.2026", "created_raw": "14.10.2026", "date_src": "contract_date",
         "status": status, "signed_at": signed_at, "bike": BIKE, "phone": CPHONE, "pdf_id": "F%d" % n,
         "matched_on": ["phone"]}
    r.update(over)
    return r


def rental_row(**over):
    """Строка листа «клиенты» (дверь clients filter=all) — активная аренда живого примера."""
    r = {"booking_id": "BK-6334-1014", "bike": BIKE, "date_start": "2026-10-14 10:00", "date_end": "2026-10-17 10:00",
         "status": "В аренде", "auto_cancel": "", "contacts": CONTACTS, "price": 1200, "to_pay": 3600,
         "deposit": 5000, "deposit_raw": "5000", "currency": "THB"}
    r.update(over)
    return r


# ── подделки дверей ──────────────────────────────────────────────────────────────────────

class Find:
    """Дверь contract_find формы `bridge_client.contract_find` над реестром стенда (`Rig.registry`).
    fail — исключение двери; answer — ответ целиком; mutate(out) — правка вычисленного ответа."""

    def __init__(self, rig):
        self.rig, self.calls, self.fail, self.answer, self.mutate = rig, [], None, None, None

    def __call__(self, phone="", name="", bike="", date_from="", date_to="", limit=None, **extra):
        self.calls.append({"phone": str(phone or ""), "name": str(name or ""), "bike": str(bike or ""),
                           "date_from": str(date_from or ""), "date_to": str(date_to or "")})
        if self.fail is not None:
            raise self.fail
        if self.answer is not None:
            return self.answer
        if not (str(phone or "").strip() or str(name or "").strip() or str(bike or "").strip()):
            return {"ok": False, "error": "no_filter"}
        key = T.last9(phone)
        rows = [r for r in self.rig.registry if key and key in T.contract_phones(r["phone"])]
        df, dt = str(date_from or ""), str(date_to or "")
        if df or dt:
            rows = [r for r in rows if (not df or r["contract_date"] >= df) and (not dt or r["contract_date"] <= dt)]
        items = [dict(r, signed=r["status"] == SIGNED) for r in rows]
        signed = [i for i in items if i["signed"]]
        out = {"ok": True, "items": items, "undated_items": [], "pick": None, "reason": None,
               "filter": {"phone_last9": key, "date_from": df or None, "date_to": dt or None},
               "checked": {"rows_scanned": len(self.rig.registry), "span_from": df or None, "span_to": dt or None,
                           "matched": len(items), "signed": len(signed), "returned": len(items), "truncated": False,
                           "undated": 0, "undated_signed": 0, "date_unparsed": 0, "unread": [], "complete": True}}
        if len(signed) == 1:
            out.update(outcome="one", pick=dict(signed[0], pdf_ready=True))
        elif len(signed) > 1:
            out.update(outcome="ambiguous", reason={"code": "ambiguous", "rows": [i["row"] for i in signed],
                                                    "message": "подписанных в сроке несколько"})
        else:
            out["outcome"] = "none_signed" if items else "none"
        if callable(self.mutate):
            self.mutate(out)
        return out


class Fetch:
    """Дверь contract_pdf формы `bridge_client.contract_pdf`: файл — только у подписанной строки реестра; verified
    ставит клиент (длина и sha256 байтов против названных мостом). claim[file_id] — sha256, который «называет мост»."""

    def __init__(self, rig):
        self.rig, self.calls, self.fail, self.answer = rig, [], None, None
        self.files = {"F%d" % n: data for n, data in PDF.items()}
        self.claim = {}

    def __call__(self, file_id=None, **kw):
        fid = str(file_id if file_id is not None else kw.get("id") or "")
        self.calls.append(fid)
        if self.fail is not None:
            raise self.fail
        if self.answer is not None:
            return self.answer
        rows = [r for r in self.rig.registry if r.get("pdf_id") == fid]
        if not rows:
            return {"ok": False, "error": "not_in_registry"}
        live = [r for r in rows if r["status"] == SIGNED]
        if not live:
            return {"ok": False, "error": "not_signed"}
        r = live[-1]
        data = self.files[fid]
        said = self.claim.get(fid) or hashlib.sha256(data).hexdigest()
        out = {"ok": True, "id": fid, "name": "TB-eSign-%d.pdf" % r["row"], "mime": "application/pdf",
               "size": len(data), "sha256": said, "content_b64": base64.b64encode(data).decode(), "row": r["row"],
               "client": r["client"], "contract_date": r["contract_date"], "signed_at": r["signed_at"]}
        if hashlib.sha256(data).hexdigest() != said:
            return dict(out, ok=False, error="pdf_mismatch", verified=False,
                        message="длина или sha256 содержимого не сошлись с ответом моста")
        return dict(out, verified=True)


class FakeModel(M.ModelAdapter):
    """Адаптер модели прода с подделанным ответом: двери (`_tool_doors`: аренда по снимку броней, договоры из
    `tools`) — настоящие; `draft` языковую модель не зовёт. check: None — без сверки Т4а; "none" — сверка без
    договора; "full" — сверка дверями (rental, contract, contract_pdf) в момент черновика."""

    def __init__(self, rig):
        super().__init__(rig.qpath, None, clock=rig.clock, agent_db=rig.dbpath, book=rig.book,
                         tools={"cash": lambda **kw: {"ok": False, "error": "касса в наборе не читается"},
                                "contract": rig.find, "contract_pdf": rig.fetch})
        self.rig, self.text, self.check, self.calls = rig, None, None, 0

    def draft(self, number, upto_id, hint=None):
        self.calls += 1
        info = {"last_in": self.rig.last_in(number)}
        tools = None
        if self.check == "none":
            tools = {"state": T.DONE, "results": []}
        elif self.check == "full":
            tools = self.rig.model_check(number)
        self.last = {"tools": tools, "info": info} if tools is not None else {"info": info}
        return self.text


class FakeTG(A.Telegram):
    def __init__(self):
        self.cards, self.done, self.asks, self.crash = [], [], [], False

    def card(self, draft_id, ver, number, text):
        if self.crash:
            self.crash = False
            raise Crash()
        self.cards.append((draft_id, ver, number, text))
        return 1000 + draft_id

    def card_done(self, draft_id, card_id, words):
        self.done.append((draft_id, words))
        return True

    def ask_pause(self, number, pause_no, via=None):
        self.asks.append((number, pause_no))


class FakeDoor(A.Door):
    """Провайдер: три исхода, wamid только при sent; window — правилом двери (`wa_send.window_state`) по очереди
    стенда; hook — вызов посреди текстовой двери (черновик в sending)."""

    def __init__(self, rig):
        self.rig, self.sends, self.media, self.text_out, self.media_out, self.hook = rig, [], [], "sent", "sent", None

    def send_text(self, to, text):
        if self.hook is not None:
            hook, self.hook = self.hook, None
            hook()
        self.sends.append((to, text))
        return {"outcome": self.text_out, "reason": "ok", "window": None,
                "wamid": "wamid.T%d" % len(self.sends) if self.text_out == "sent" else None}

    def send_media(self, to, media):
        data, _why = media["fetch"](10 ** 9)
        self.media.append((to, media["kind"], media["mime"], media["filename"], hashlib.sha256(data).hexdigest()))
        return {"outcome": self.media_out, "reason": "ok", "window": None,
                "wamid": "wamid.P%d" % len(self.media) if self.media_out == "sent" else None}

    def window(self, number, now=None):
        ts = self.rig.last_in(number)
        if ts is None:
            return {"state": "unknown", "age": None}
        age = float(self.rig.now if now is None else now) - float(ts)
        return {"state": "open" if age <= 86400 else "closed", "age": age}


# ── стенд ────────────────────────────────────────────────────────────────────────────────

class Rig:
    """Очередь, реестр, аренды, двери и модель — без ядра (на дереве без реализации тоже собирается)."""

    def __init__(self, start=T_START):
        self.dir = tempfile.mkdtemp(prefix="wa_signed_t_")
        self.qpath, self.dbpath = os.path.join(self.dir, "q.db"), os.path.join(self.dir, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        self.now = float(start)
        self.clock = lambda: self.now
        self.registry = [reg_row(34, REVOKED, S34), reg_row(35, REVOKED, S35), reg_row(36, SIGNED, S36)]
        self.rentals = [rental_row()]
        self.book_reads, self.book_fail = 0, None
        self.book = B.Snapshot(self._clients, self._fleet, ttl=0)
        self.find, self.fetch = Find(self), Fetch(self)
        self.model = FakeModel(self)
        self.lines = []

    def _clients(self):
        self.book_reads += 1
        if self.book_fail is not None:
            raise self.book_fail
        return {"ok": True, "clients": [dict(r) for r in self.rentals]}

    def _fleet(self):
        return {"ok": True, "bikes": [{"name": BIKE}]}

    def reg(self, n):
        return next(r for r in self.registry if r["row"] == n)

    def rental_door(self, *a, **kw):
        number = kw.get("number") or kw.get("phone") or (a[0] if a else NUM)
        return self.model._tool_doors(str(number), None)["rental"]()

    def model_check(self, number):
        """Сверка так, как её делает модель: rental, затем contract в контексте привязки, затем contract_pdf."""
        doors = self.model._tool_doors(number, None)
        rental = T.call_tool("rental", {}, doors, self.clock)
        ctx = T.bind_ctx(number, doors, [rental], self.clock)
        contract = T.call_tool("contract", {}, doors, self.clock, ctx)
        results = [rental, contract]
        ids = [f.get("pdf_id") for f in contract.get("facts") or [] if f.get("pdf_id")]
        if ids:
            results.append(T.call_tool("contract_pdf", {"file_id": ids[0]}, doors, self.clock,
                                       {"results": list(results)}))
        return {"state": T.DONE, "results": results}

    # очередь (схема wa_webhook)
    def put(self, ts, text="x", echo=0, msg_type="text", wamid=None, number=NUM):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,0,?)", (int(ts), number, msg_type, text, int(ts), echo, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def last_in(self, number):
        q = sqlite3.connect(self.qpath)
        try:
            row = q.execute("SELECT MAX(COALESCE(NULLIF(ts_msg, 0), ts_queued)) FROM wa_inbox WHERE from_number=? "
                            "AND echo=0 AND msg_type NOT IN ('status', 'reaction')", (number,)).fetchone()
        finally:
            q.close()
        return row[0] if row else None

    # база агента (чтение отдельным соединением; запись — только для состояний, которые в живом бывают)
    def q(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def x(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            db.execute(sql, args)
            db.commit()
        finally:
            db.close()

    def has_table(self, name):
        return bool(self.q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))

    def drafts(self):
        return self.q("SELECT id, state, kind, reason, number FROM drafts ORDER BY id")

    def draft(self, did):
        rows = self.q("SELECT id, state, kind, reason, number, ver FROM drafts WHERE id=?", (did,))
        return rows[0] if rows else None

    def signed_drafts(self):
        if not self.has_table("drafts"):
            return []
        return self.q("SELECT id, state, ver, text, upto_id, ctx, created_at, reason, number FROM drafts "
                      "WHERE kind='signed' ORDER BY id")

    def versions(self):
        if not self.has_table("signed_cards"):
            return None
        return self.q("SELECT number, doc_id, signed_at, file_id, sha256, draft_id, ts FROM signed_cards "
                      "ORDER BY ts, doc_id")

    def attach_row(self, did):
        rows = self.q("SELECT file_id, name, size, sha256, row, doc_id, signed_at, number, date_from, date_to, "
                      "reason, opora FROM attach WHERE draft_id=?", (did,))
        return rows[0] if rows else None

    def client(self, number=NUM):
        rows = self.q("SELECT last_in_id, ctx, paused FROM clients WHERE number=?", (number,))
        return rows[0] if rows else None

    def meta_signed(self):
        """Строки постоянной мета-таблицы с ключом о подписи (метка водораздела signed_since)."""
        out = []
        for (name,) in self.q("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%meta%'"):
            cols = {r[1] for r in self.q("PRAGMA table_info(%s)" % name)}
            if {"key", "value"} <= cols:
                out += [(name,) + tuple(r) for r in
                        self.q("SELECT key, value FROM %s WHERE key LIKE '%%signed%%' ORDER BY key" % name)]
        return out


class World(Rig):
    """Стенд + ядро AttachCore. signed=None — аргумент не передаётся (прежняя форма вызова)."""

    def __init__(self, signed=True, attach=True, find=True, fetch=True, real_tg=False, start=T_START, setup=None):
        Rig.__init__(self, start)
        if setup is not None:
            setup(self)                     # реестр, аренды, двери — до первого старта
        self.signed, self.attach, self.with_find, self.with_fetch = signed, attach, find, fetch
        self.real_tg = real_tg
        self.door = FakeDoor(self)
        if real_tg:
            import test_wa_agent_svc as SV
            self.http = SV.FakeHttp(SV.Clock(start))
            self.tg = G.Tg(SV.TOKEN, enabled=True, show_chat=SV.SHOW, mirror_db=None, http=self.http,
                           clock=self.clock, log=self.lines.append)
        else:
            self.tg = FakeTG()
        self.core = self.new_core()
        self.tick(start)                    # первый старт: курсор на MAX(id), водораздел пишется сейчас

    def new_core(self):
        kw = {"clock": self.clock, "log": self.lines.append, "attach": self.attach,
              "pdf_fetch": self.fetch if self.with_fetch else None,
              "contract_find": self.find if self.with_find else None, "lang_of": K.lang_of}
        if self.signed is not None:
            kw["signed"] = self.signed
        for name in inspect.signature(X.AttachCore.__init__).parameters:
            if "rental" in name.lower() and name not in kw:
                kw[name] = self.rental_door          # точка подстройки: дверь аренды аргументом (см. шапку)
        core = X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)
        if self.real_tg:
            self.tg.bind(core)
        return core

    def restart(self, at, signed=KEEP):
        """Смерть процесса и новый старт на той же базе (незакоммиченное откатывается)."""
        try:
            self.core.db.close()
        except Exception:                                            # noqa: BLE001
            pass
        self.now = float(at)
        if signed is not KEEP:
            self.signed = signed
        self.core = self.new_core()
        return self

    def tick(self, t):
        self.now = float(t)
        return self.core.tick(float(t))

    def press(self, did, action=A.ACT_SEND, t=None, ver=1, who="Даня"):
        if t is not None:
            self.now = float(t)
        return self.core.press(did, ver, action, who, self.now)


def card_world(text="Подписал ✅", **kw):
    """Живой пример: «Подписал» в 19:05, такт в 19:14 → одна карточка подписи."""
    w = World(**kw)
    w.put(T_IN, text)
    w.tick(T_CARD)
    sd = w.signed_drafts()
    assert len(sd) == 1, ("карточка подписи не родилась", sd, w.drafts(), w.lines[-8:])
    return w, sd[0][0]


def unsigned36(r):
    r.reg(36)["status"] = SENT_FOR_SIGN     # стр.36 ещё у клиента на подписи: реестр — none_signed


# ═══ 0. интерфейс и стенд ════════════════════════════════════════════════════════════════

def test_00_interface():
    """Интерфейс выпуска есть: SIGNED_EVERY = 120, AttachCore.make_signed_cards, именованный аргумент signed."""
    miss = []
    if getattr(X, "SIGNED_EVERY", None) != 120:
        miss.append("wa_agent_attach.SIGNED_EVERY = 120 (сейчас: %r)" % getattr(X, "SIGNED_EVERY", "нет"))
    if not callable(getattr(X.AttachCore, "make_signed_cards", None)):
        miss.append("метод AttachCore.make_signed_cards(now)")
    if "signed" not in inspect.signature(X.AttachCore.__init__).parameters:
        miss.append("именованный аргумент AttachCore(signed=…)")
    assert not miss, "интерфейса выпуска нет: " + "; ".join(miss)


def test_01_fixture_binds_by_existing_code():
    """Стенд честный: СУЩЕСТВУЮЩИЙ код (call_tool → attach_of с PDF, прочитанным кодом → recheck_of) на подделках
    живого формата даёт FACT аренды и договора стр.36 и метаданные его PDF. Проходит и без реализации выпуска."""
    r = Rig()
    r.now = float(T_CARD)
    doors = r.model._tool_doors(NUM, None)
    rental = T.call_tool("rental", {}, doors, r.clock)
    assert rental["outcome"] == T.FACT and "‑" in r.rentals[0]["contacts"], rental
    ctx = T.bind_ctx(NUM, doors, [rental], r.clock)
    contract = T.call_tool("contract", {}, doors, r.clock, ctx)
    assert contract["outcome"] == T.FACT, contract
    fact = contract["facts"][0]
    assert fact["row"] == 36 and fact["bound_by"] == "телефон" and contract["window"] == "2026-10-14…2026-10-17", \
        contract
    assert r.find.calls and all(c["phone"] for c in r.find.calls), r.find.calls
    code = {}

    def read_pdf(pdf_id, results):
        code["r"] = T.call_tool("contract_pdf", {"file_id": pdf_id}, {"contract_pdf": r.fetch}, r.clock,
                                {"results": results})
        return code["r"]
    meta, why = X.attach_of({"state": T.DONE, "results": [rental, contract]}, None, read_pdf=read_pdf)
    assert meta and why == "", why
    got = tuple(meta.get(k) for k in ("file_id", "sha256", "row", "doc_id", "signed_at", "date_from", "date_to",
                                      "pdf_by"))
    assert got == ("F36", SHA[36], 36, "DOC-36", S36, "2026-10-14", "2026-10-17", "код"), meta
    opora = X.opora_of({"state": T.DONE, "results": [rental, contract]}, None, code=code["r"])
    assert "прочитал КОД" in opora, opora
    ok, why2 = X.recheck_of(r.find(phone=NUM, date_from="2026-10-14", date_to="2026-10-17"), dict(meta))
    assert ok, why2
    assert r.find()["error"] == "no_filter", "подделка моста обязана отвергать поиск без фильтра"
    bad = dict(r.fetch("F36"))
    r.fetch.claim["F36"] = SHA[35]
    assert bad["verified"] is True and r.fetch("F36")["error"] == "pdf_mismatch", "verified ставит клиент по байтам"


# ═══ 1. живой пример: одна карточка, ничего не уходит без нажатия ═══════════════════════

def test_card_live_example():
    """«Подписал» → карточка: kind='signed', upto_id = last_in_id, ctx = clients.ctx, текст шаблона, строка attach
    (поля _attach_decide, опора «прочитал КОД»), версия в signed_cards; отозванные 34/35 карточки не получают; тактами
    час — клиенту не ушло ничего и второй карточки нет."""
    w = World()
    rid = w.put(T_IN, "Подписал ✅")
    w.tick(T_CARD)
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.drafts(), w.lines[-10:])
    did, state, ver, text, upto, ctx, created, reason, number = sd[0]
    last_in, cctx, _paused = w.client()
    assert (state, ver, text, number) == (A.PENDING, 1, RU, NUM), sd
    assert upto == last_in == rid and ctx == cctx and created == T_CARD, (sd, w.client())
    assert did in [c[0] for c in w.tg.cards], ("карточка не ушла в «Агенты»", w.tg.cards)
    a = w.attach_row(did)
    assert a is not None and a[:10] == ("F36", "TB-eSign-36.pdf", len(PDF[36]), SHA[36], 36, "DOC-36", S36, NUM,
                                        "2026-10-14", "2026-10-17"), a
    assert a[10] is None and "прочитал КОД" in (a[11] or ""), a
    assert w.versions() == [(NUM, "DOC-36", S36, "F36", SHA[36], did, T_CARD)], w.versions()
    for k in range(1, 31):
        w.tick(T_CARD + k * EVERY)
    assert w.door.sends == [] and w.door.media == [], ("ушло без нажатия", w.door.sends, w.door.media)
    assert len(w.signed_drafts()) == 1 and len(w.versions()) == 1, (w.signed_drafts(), w.versions())


def test_press_text_then_pdf_with_recheck():
    """«Отправить» карточки подписи — существующий путь: реестр перечитан (номер и срок аренды), затем текст, затем
    PDF стр.36 (sha256 сверки), квитанции обеих частей."""
    w, did = card_world()
    before = len(w.find.calls)
    out = w.press(did, t=T_CARD + 60)
    assert out["ok"] and out.get("parts") == {"text": A.SENT, "pdf": A.SENT}, out
    assert w.door.sends == [(NUM, RU)], w.door.sends
    assert [(m[3], m[4]) for m in w.door.media] == [("TB-eSign-36.pdf", SHA[36])], w.door.media
    again = w.find.calls[before:]
    assert again and again[-1]["phone"].endswith("999966963") and \
        (again[-1]["date_from"], again[-1]["date_to"]) == ("2026-10-14", "2026-10-17"), again
    rows = w.q("SELECT part, outcome, sha256 FROM part_log WHERE draft_id=? ORDER BY id", (did,))
    assert rows == [("text", A.SENT, None), ("pdf", A.SENT, SHA[36])], rows


def test_make_signed_cards_returns_count():
    """make_signed_cards(now) → число созданных карточек: 1, повтор той же версии — 0."""
    w = World()
    w.put(T_IN, "Подписал")
    w.now = float(T_CARD)
    w.core.scan(T_CARD)
    n1 = w.core.make_signed_cards(T_CARD)
    n2 = w.core.make_signed_cards(T_CARD + EVERY)
    assert n1 == 1 and n2 == 0, (n1, n2)
    assert len(w.signed_drafts()) == 1


def test_not_more_often_than_every_120s():
    """Такт подписи — не чаще SIGNED_EVERY: через 119 с реестр не спрашивается, через 120 — карточка."""
    w = World(setup=unsigned36)
    w.put(T_IN, "Подписал")
    w.tick(T_CARD)
    assert w.signed_drafts() == []
    calls = len(w.find.calls)
    assert calls >= 1, "кандидат был, а реестр не спрошен"
    w.reg(36)["status"] = SIGNED
    w.tick(T_CARD + EVERY - 1)
    assert w.signed_drafts() == [] and len(w.find.calls) == calls, (len(w.find.calls), calls)
    w.tick(T_CARD + EVERY)
    assert len(w.signed_drafts()) == 1, w.lines[-8:]


# ═══ 2. водораздел signed_since ═══════════════════════════════════════════════════════════

def test_watershed_exact_minute_gets_card():
    """signed_at РОВНО на метке (старт − 6 ч = 12:00) — не раньше метки: карточка есть (с извинением: > 30 мин)."""
    w = World(setup=lambda r: r.reg(36).update(signed_at=local_of(WATERSHED)))
    w.put(T_IN, "Подписал")
    w.tick(T_CARD)
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][3] == RU_SORRY + RU, sd


def test_watershed_minute_before_no_card():
    """signed_at на минуту раньше метки — старый договор: карточки нет ни этим тактом, ни следующими."""
    w = World(setup=lambda r: r.reg(36).update(signed_at=local_of(WATERSHED - 60)))
    w.put(T_IN, "Подписал")
    for k in range(4):
        w.tick(T_CARD + k * EVERY)
    assert w.signed_drafts() == [], w.signed_drafts()


def test_watershed_not_moved_by_restart():
    """Метка пишется в постоянную мета-таблицу при первом старте с флагом; рестарт через 6.5 ч её НЕ сдвигает:
    договор 19:04 (позже метки 12:00, но раньше «рестарт − 6 ч» = 19:34) получает карточку."""
    w = World()
    meta0 = w.meta_signed()
    assert meta0, ("метки водораздела в мета-таблице нет после первого старта с флагом",
                   w.q("SELECT key, value FROM meta"))
    w.core.db.close()                                       # служба легла
    w.put(T_IN, "Подписал")                                 # клиент пишет, пока службы нет
    t_r = SIGN36 + 6 * 3600 + 30 * 60
    w.restart(t_r)
    w.tick(t_r + 60)
    assert w.meta_signed() == meta0, (meta0, w.meta_signed())
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][3] == RU_SORRY + RU, sd


def test_watershed_written_only_by_start_with_flag():
    """Старт с выключенным флагом метку НЕ пишет: первый старт с флагом в 19:30 → метка 13:30; договор 13:00 —
    карточки нет, договор ровно 13:30 — есть."""
    t_on = ts_of("2026-10-14 19:30")
    for signed_at, want in (("2026-10-14 13:00", 0), (local_of(t_on - 6 * 3600), 1)):
        w = World(signed=False, setup=lambda r, s=signed_at: r.reg(36).update(signed_at=s))
        assert w.meta_signed() == [], ("метка водораздела записана стартом БЕЗ флага", w.meta_signed())
        w.restart(t_on, signed=True)
        w.put(t_on + 60, "Подписал")
        w.tick(t_on + 300)
        got = len(w.signed_drafts())
        assert got == want, (signed_at, got, w.meta_signed())


# ═══ 3. текст: язык и извинение ═══════════════════════════════════════════════════════════

def test_apology_after_30_minutes_only():
    """Ровно 30 мин после signed_at — без извинения; 31 мин — извинение первым; RU и EN, других слов нет."""
    for text, after, want in (("Подписал", 1800, RU), ("Подписал", 1860, RU_SORRY + RU),
                              ("Signed, thank you", 1800, EN), ("Signed, thank you", 1860, EN_SORRY + EN)):
        w = World()
        w.put(T_IN, text)
        w.tick(SIGN36 + after)
        sd = w.signed_drafts()
        assert len(sd) == 1 and sd[0][3] == want, (text, after, sd)


def test_language_by_last_inbound():
    """Язык — по ПОСЛЕДНЕМУ входящему: кириллица → RU, иначе EN (тайский и эмодзи — тоже EN)."""
    for texts, want in ((["Подписал"], RU), (["ok, подписал"], RU), (["Signed it, thanks"], EN),
                        (["เซ็นแล้วค่ะ"], EN), (["👍"], EN), (["Подписал", "Thanks!"], EN),
                        (["Signed", "Спасибо"], RU)):
        w = World()
        for k, t in enumerate(texts):
            w.put(T_IN + k * 10, t)
        w.tick(T_CARD)
        sd = w.signed_drafts()
        assert len(sd) == 1 and sd[0][3] == want, (texts, sd)


# ═══ 4. кто кандидат: телефон, пауза, окно 24 ч ══════════════════════════════════════════

def test_phone_with_nonbreaking_hyphens_binds():
    """Телефон в контактах аренды с U+2011 (и знаками направления, NBSP) — аренда находится дверью модели,
    карточка есть; контакты другого номера — аренды нет, карточки нет."""
    for contacts in (CONTACTS, "‪+7 999‑996‑69‑63‬ Ivan"):
        w = World(setup=lambda r, c=contacts: r.rentals[0].update(contacts=c))
        w.put(T_IN, "Подписал")
        w.tick(T_CARD)
        assert len(w.signed_drafts()) == 1, (contacts, w.lines[-8:])
    w = World(setup=lambda r: r.rentals[0].update(contacts="Иван +7 999‑111‑22‑33"))
    w.put(T_IN, "Подписал")
    w.tick(T_CARD)
    assert w.signed_drafts() == [], "договор без аренды этого номера получил карточку"


def test_paused_client_no_card_no_doors():
    """Клиент на паузе (ответили с телефона) не кандидат: карточки нет, двери не звались."""
    w = World()
    w.put(T_IN, "Подписал")
    w.put(T_IN + 30, "Получили, спасибо", echo=1, wamid="wamid.PHONE1")
    for k in range(4):
        w.tick(T_CARD + k * EVERY)
    assert w.client()[2] == 1, w.client()
    assert w.signed_drafts() == []
    assert w.find.calls == [] and w.fetch.calls == [] and w.book_reads == 0, \
        (w.find.calls, w.fetch.calls, w.book_reads)


def test_window_24h_minus_30min_boundary():
    """Окно — правилом напоминания ядра: последнее входящее ровно 23 ч 30 мин назад — карточка есть; на секунду
    больше — нет. Закрытое окно версию не «съедает»: клиент написал снова → карточка."""
    t_in = T_START + 60
    for age, want in ((WINDOW_OPEN, 1), (WINDOW_OPEN + 1, 0)):
        t = t_in + age
        w = World(setup=lambda r, s=local_of(t - 600): r.reg(36).update(signed_at=s))
        w.put(t_in, "Подписал")
        w.tick(t)
        got = len(w.signed_drafts())
        assert got == want, (age, got, w.lines[-6:])
    w.put(t + 1000, "Hello?")
    w.tick(t + 1200)
    assert len(w.signed_drafts()) == 1, "после нового входящего карточки нет — версию пометило закрытое окно"


# ═══ 5. живой черновик номера ════════════════════════════════════════════════════════════

def test_live_draft_with_same_sha_covers_version():
    """У живого черновика уже есть attach с этим sha256 — версия «покрыта»: новой карточки нет, черновик жив,
    версия записана; и после «Не нужно» на нём карточка этой версии не появляется."""
    w = World()
    w.model.text, w.model.check = "Договор во вложении", "full"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    d = w.drafts()
    assert len(d) == 1 and d[0][1] == A.PENDING and d[0][2] != "signed", d
    did1 = d[0][0]
    assert w.attach_row(did1)[3] == SHA[36], w.attach_row(did1)
    v = w.versions()
    assert v and len(v) == 1 and v[0][:5] == (NUM, "DOC-36", S36, "F36", SHA[36]) and v[0][5] in (None, did1), v
    w.tick(T_IN + 100 + EVERY)
    assert w.signed_drafts() == [] and w.draft(did1)[1] == A.PENDING and len(w.versions()) == 1
    assert w.press(did1, A.ACT_DECLINE, t=T_IN + 300)["ok"]
    w.model.text = None
    w.tick(T_IN + 100 + 3 * EVERY)
    w.tick(T_IN + 100 + 4 * EVERY)
    assert w.signed_drafts() == [] and len(w.versions()) == 1, (w.signed_drafts(), w.versions())


def test_live_pending_with_other_pdf_superseded():
    """Висящий pending с ДРУГИМ sha256 (PDF стр.35, потом отозванной) — superseded со словами «заменён карточкой
    подписанного договора», его карточка закрыта; карточка стр.36 — одна живая на номер."""
    t35 = ts_of(S35) + 60

    def setup(r):
        r.reg(35)["status"] = SIGNED
        unsigned36(r)
    w = World(setup=setup)
    w.model.text, w.model.check = "Спасибо! Договор во вложении", "full"
    w.put(t35, "Подписал")
    w.tick(t35 + 100)
    did1 = w.drafts()[0][0]
    assert w.attach_row(did1)[3] == SHA[35] and w.signed_drafts() == [], (w.attach_row(did1), w.signed_drafts())
    w.reg(35)["status"] = REVOKED
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    w.tick(T_CARD)
    old = w.draft(did1)
    assert old[1] == A.SUPERSEDED and REPLACED in (old[3] or ""), old
    assert [x for x in w.tg.done if x[0] == did1 and REPLACED in x[1]], w.tg.done
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.PENDING and w.attach_row(sd[0][0])[3] == SHA[36], sd
    live = [d for d in w.drafts() if d[1] in A.LIVE]
    assert [d[0] for d in live] == [sd[0][0]], live


def test_live_pending_without_pdf_superseded():
    """Ответ «Спасибо!» на «Подписал» без PDF висит → superseded «заменён карточкой подписанного договора», карточка
    подписи с PDF."""
    w = World(setup=unsigned36)
    w.model.text, w.model.check = "Спасибо!", "none"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    did1 = w.drafts()[0][0]
    assert w.attach_row(did1)[0] is None, w.attach_row(did1)
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    w.tick(T_IN + 100 + EVERY)
    old = w.draft(did1)
    assert old[1] == A.SUPERSEDED and REPLACED in (old[3] or ""), old
    assert [x for x in w.tg.done if x[0] == did1 and REPLACED in x[1]], w.tg.done
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][3] == RU and w.attach_row(sd[0][0])[0] == "F36", sd


def test_claimed_draft_skips_tick():
    """У номера claimed — такт пропущен: карточки нет, захваченный черновик не тронут; вернулся в pending —
    следующим тактом замена и карточка."""
    w = World(setup=unsigned36)
    w.model.text, w.model.check = "Спасибо!", "none"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    did1 = w.drafts()[0][0]
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    w.x("UPDATE drafts SET state=?, decided_by=?, decided_at=? WHERE id=?", (A.CLAIMED, "Даня", T_IN + 150, did1))
    w.tick(T_IN + 100 + EVERY)
    assert w.signed_drafts() == [] and w.draft(did1)[1] == A.CLAIMED, (w.signed_drafts(), w.draft(did1))
    w.x("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL WHERE id=?", (A.PENDING, did1))
    w.tick(T_IN + 100 + 2 * EVERY)
    assert w.draft(did1)[1] == A.SUPERSEDED and len(w.signed_drafts()) == 1, (w.draft(did1), w.signed_drafts())


def test_sending_draft_skips_tick():
    """Такт подписи посреди текстовой двери черновика (sending) — 0 карточек, черновик уходит как шёл; следующим
    тактом — карточка подписи."""
    w = World(setup=unsigned36)
    w.model.text, w.model.check = "Спасибо!", "none"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    did1 = w.drafts()[0][0]
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    seen = {}

    def hook():
        seen["state"] = w.draft(did1)[1]
        seen["made"] = w.core.make_signed_cards(T_IN + 100 + EVERY)
        seen["signed"] = len(w.signed_drafts())
    w.door.hook = hook
    out = w.press(did1, t=T_IN + 100 + EVERY)
    assert seen == {"state": A.SENDING, "made": 0, "signed": 0}, seen
    assert out["ok"] and w.door.sends == [(NUM, "Спасибо!")] and w.door.media == [], (out, w.door.sends)
    w.tick(T_IN + 100 + 2 * EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.PENDING, sd


def test_other_client_draft_untouched():
    """Замена — только у номера договора: ждущий черновик другого клиента не тронут."""
    w = World(setup=unsigned36)
    w.model.text, w.model.check = "Спасибо!", "none"
    w.put(T_IN, "Подписал")
    w.put(T_IN + 5, "Hi, is PCX free tomorrow?", number=OTHER)
    w.tick(T_IN + 100)
    by = {d[4]: d[0] for d in w.drafts()}
    assert set(by) == {NUM, OTHER}, w.drafts()
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    w.tick(T_IN + 100 + EVERY)
    assert w.draft(by[OTHER])[1] == A.PENDING and w.draft(by[NUM])[1] == A.SUPERSEDED, w.drafts()
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][8] == NUM, sd


# ═══ 6. привязка не FACT, двери падают, sha ═══════════════════════════════════════════════

def test_two_signed_in_term_no_card():
    """Два подписанных в сроке аренды (стр.35 и 36) — ambiguous: карточки нет."""
    w = World(setup=lambda r: r.reg(35).update(status=SIGNED))
    w.put(T_IN, "Подписал")
    for k in range(3):
        w.tick(T_CARD + k * EVERY)
    assert w.signed_drafts() == [] and not w.versions(), (w.signed_drafts(), w.versions())


def test_binding_not_fact_no_card():
    """Привязка не FACT — карточки нет, такт не падает: без дня (incomplete), реестр не целиком, байк другой, вне
    срока, отозван, аренда завершена, аренд две, телефон договора с чужим кодом страны."""
    def incomplete(out):
        out.update(outcome="incomplete", pick=None,
                   reason={"code": "undated_signed", "rows": [36], "message": "подписанный без известного дня"})
        out["checked"].update(undated=1, undated_signed=1, complete=False)

    def unread(out):
        out["checked"].update(unread=["лист «Архив»"], complete=False)
    cases = {
        "incomplete": lambda r: setattr(r.find, "mutate", incomplete),
        "unread": lambda r: setattr(r.find, "mutate", unread),
        "байк другой": lambda r: r.reg(36).update(bike="PCX 160CC WHITE PHUKET 5580"),
        "вне срока": lambda r: r.reg(36).update(contract_date="2026-10-20", contract_date_raw="20.10.2026"),
        "отозван": lambda r: r.reg(36).update(status=REVOKED),
        "аренда завершена": lambda r: r.rentals[0].update(status="Завершена"),
        "аренд две": lambda r: r.rentals.append(rental_row(booking_id="BK-2", bike="PCX 160CC WHITE PHUKET 5580")),
        "чужой код страны": lambda r: r.reg(36).update(phone="+44 999 996 69 63"),
    }
    for name, setup in cases.items():
        w = World(setup=setup)
        w.put(T_IN, "Подписал")
        try:
            w.tick(T_CARD)
            w.tick(T_CARD + EVERY)
        except Exception as e:                                       # noqa: BLE001
            raise AssertionError("%s: такт упал %s: %s" % (name, type(e).__name__, e))
        assert w.signed_drafts() == [], (name, w.signed_drafts())
        assert w.door.sends == [] and w.door.media == [], name


def test_door_failure_no_card_no_crash_then_recovers():
    """Дверь contract_find / pdf_fetch / аренды падает, таймаут, мусор — карточки нет, такт не падает, версия не
    помечена: дверь починилась — следующим тактом карточка."""
    cases = {
        "contract_find таймаут": ("find", TimeoutError("read timed out")),
        "contract_find упала": ("find", RuntimeError("bridge 502")),
        "contract_find не словарь": ("find_answer", "<html>502 Bad Gateway</html>"),
        "contract_find ok=false": ("find_answer", {"ok": False, "error": "request_failed"}),
        "pdf_fetch таймаут": ("fetch", TimeoutError("read timed out")),
        "pdf_fetch упала": ("fetch", RuntimeError("bridge 502")),
        "pdf_fetch отказ моста": ("fetch_answer", {"ok": False, "error": "not_in_signed_folder"}),
        "аренда: снимок броней упал": ("book", RuntimeError("bridge 502")),
    }
    for name, (where, what) in cases.items():
        w = World()
        target = {"find": w.find, "find_answer": w.find, "fetch": w.fetch, "fetch_answer": w.fetch}.get(where)
        if where == "book":
            w.book_fail = what
        elif where.endswith("_answer"):
            target.answer = what
        else:
            target.fail = what
        w.put(T_IN, "Подписал")
        try:
            w.tick(T_CARD)
            w.tick(T_CARD + EVERY)
        except Exception as e:                                       # noqa: BLE001
            raise AssertionError("%s: такт упал %s: %s" % (name, type(e).__name__, e))
        assert w.signed_drafts() == [], (name, w.signed_drafts())
        w.book_fail = None
        w.find.fail = w.find.answer = w.fetch.fail = w.fetch.answer = None
        w.tick(T_CARD + 2 * EVERY)
        assert len(w.signed_drafts()) == 1, (name, "после починки двери карточки нет — версию пометил отказ")


def test_pdf_bytes_not_matching_sha_no_card():
    """Мост назвал sha256, который не сходится с байтами (клиент: pdf_mismatch) — карточки нет; мост исправился —
    карточка с sha256 настоящих байтов."""
    w = World(setup=lambda r: r.fetch.claim.update(F36=SHA[35]))
    w.put(T_IN, "Подписал")
    w.tick(T_CARD)
    w.tick(T_CARD + EVERY)
    assert w.signed_drafts() == [] and w.door.media == [], w.signed_drafts()
    w.fetch.claim.clear()
    w.tick(T_CARD + 2 * EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 1 and w.attach_row(sd[0][0])[3] == SHA[36], sd


def test_pdf_changed_between_card_and_press_not_sent():
    """Байты PDF при нажатии не равны sha256 карточки (файл подменили) — PDF двери не отдаётся, причина про sha256."""
    w, did = card_world()
    w.fetch.files["F36"] = PDF[37]
    out = w.press(did, t=T_CARD + 60)
    assert w.door.media == [], ("ушёл не тот PDF", w.door.media)
    said = " ".join(str(x or "") for x in [out.get("words")] + [r[0] for r in w.q(
        "SELECT reason FROM pdf_parts WHERE draft_id=?", (did,))] + [w.draft(did)[3]])
    assert "sha256" in said, said


# ═══ 7. после карточки: нажатие, отзыв, новое входящее, рестарт, двойник ═════════════════

def test_revoked_between_card_and_press_nothing_sent():
    """Отзыв стр.36 между тактом и нажатием — существующий stale W_BASIS, клиенту ничего; той же версии второй
    карточки нет; новая подпись (стр.37) — своя карточка."""
    w, did = card_world()
    w.reg(36)["status"] = REVOKED
    out = w.press(did, t=T_CARD + 360)
    assert out["state"] == A.STALE and out["words"].startswith(
        "устарело: основание PDF не подтверждено реестром при нажатии"), out
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    w.tick(T_CARD + 480)
    assert len(w.signed_drafts()) == 1, w.signed_drafts()
    w.registry.append(reg_row(37, SIGNED, S37))
    w.tick(ts_of(S37) + 300)
    sd = w.signed_drafts()
    assert len(sd) == 2 and sd[1][1] == A.PENDING and sd[1][3] == RU and w.attach_row(sd[1][0])[3] == SHA[37], sd


def test_new_inbound_after_card_core_behaviour():
    """Новое входящее сразу после карточки — поведение ядра: подпись pending → stale словами обычного ответа;
    обычный новый черновик жив; второй карточки той же версии нет, и обычный ответ ради неё не снимается."""
    w, did = card_world()
    w.model.text, w.model.check = "Байк сдаётся 17.10 в 10:00", "none"
    rid2 = w.put(T_CARD + 30, "А когда вернуть байк?")
    w.tick(T_CARD + 150)
    d = w.draft(did)
    assert d[1] == A.STALE and d[3] == "снят: " + A.WROTE_WORDS % rid2 + " — черновик пересобирается", d
    others = [x for x in w.drafts() if x[0] != did]
    assert len(others) == 1 and others[0][1] == A.PENDING and others[0][2] != "signed", w.drafts()
    w.model.text = None
    w.tick(T_CARD + 150 + EVERY)
    w.tick(T_CARD + 150 + 2 * EVERY)
    assert len(w.signed_drafts()) == 1 and len(w.versions()) == 1, (w.signed_drafts(), w.versions())
    assert w.draft(others[0][0])[1] == A.PENDING, "обычный ответ снят ради версии, у которой карточка уже была"


def test_no_second_card_after_restart():
    """Повтор после рестарта: карточка ждёт · «Не нужно» · отправлена — рестарт, такты: карточка версии одна."""
    w, did = card_world()
    w.restart(T_CARD + 60)
    w.tick(T_CARD + 200)
    w.tick(T_CARD + 200 + EVERY)
    assert len(w.signed_drafts()) == 1 and len(w.versions()) == 1, "ждёт"
    w, did = card_world()
    assert w.press(did, A.ACT_DECLINE, t=T_CARD + 30)["ok"]
    w.restart(T_CARD + 60)
    w.tick(T_CARD + 200)
    w.tick(T_CARD + 200 + EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.DECLINED and len(w.versions()) == 1, ("не нужно", sd)
    w, did = card_world()
    assert w.press(did, t=T_CARD + 30)["ok"]
    w.restart(T_CARD + 60)
    w.tick(T_CARD + 200)
    w.tick(T_CARD + 200 + EVERY)
    assert len(w.signed_drafts()) == 1 and len(w.door.sends) == 1 and len(w.door.media) == 1, "отправлена"


def test_crash_at_card_restart_one_card():
    """Смерть процесса на отправке карточки → рестарт: ровно один черновик подписи и одна версия, карточка
    доставлена очередью ядра; клиенту ничего."""
    w = World()
    w.put(T_IN, "Подписал")
    w.tg.crash = True
    try:
        w.tick(T_CARD)
        crashed = False
    except Crash:
        crashed = True
    assert crashed, "карточка подписи не отправлялась"
    w.restart(T_CARD + 30)
    w.tick(T_CARD + 150)
    w.tick(T_CARD + 150 + EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 1 and len(w.versions()) == 1, (sd, w.versions())
    assert sd[0][0] in [c[0] for c in w.tg.cards], w.tg.cards
    assert w.door.sends == [] and w.door.media == []


def test_twin_pdf_sent_before_flag_no_card():
    """Этот PDF этому номеру уже ушёл (или мог уйти — «неизвестно») обычным черновиком до включения флага —
    _pdf_twin: карточки подписи нет, второй копии нет."""
    for media_out in ("sent", "unknown"):
        w = World(signed=False)
        w.model.text, w.model.check = "Договор во вложении", "full"
        w.door.media_out = media_out
        w.put(T_IN, "Подписал")
        w.tick(T_IN + 100)
        did1 = w.drafts()[0][0]
        w.press(did1, t=T_IN + 130)
        assert len(w.door.media) == 1, (media_out, w.door.media)
        w.model.text = None
        w.restart(T_IN + 200, signed=True)
        w.tick(T_IN + 300)
        w.tick(T_IN + 300 + EVERY)
        assert w.signed_drafts() == [], (media_out, w.signed_drafts())
        assert len(w.door.media) == 1, media_out


def test_same_file_under_new_version_is_twin():
    """Договор переоформлен строкой 37 с ТЕМ ЖЕ файлом (sha256 тот же), PDF уже ушёл карточкой 36 — новая версия,
    но двойник: карточки нет."""
    w, did = card_world()
    assert w.press(did, t=T_CARD + 30)["ok"] and len(w.door.media) == 1
    w.reg(36)["status"] = REVOKED
    w.registry.append(reg_row(37, SIGNED, S37, pdf_id="F36"))
    w.tick(ts_of(S37) + 300)
    w.tick(ts_of(S37) + 300 + EVERY)
    assert len(w.signed_drafts()) == 1 and len(w.door.media) == 1, w.signed_drafts()


# ═══ 8. флаг выкл и прежний путь ═════════════════════════════════════════════════════════

def test_flag_off_no_door_calls():
    """signed=False (и attach=False при signed=True) — ни одного вызова дверей договора, PDF и аренды, карточек
    подписи нет; без двери contract_find или pdf_fetch — тоже ничего и такт не падает."""
    for kw in ({"signed": False}, {"attach": False, "signed": True}, {"find": False}, {"fetch": False}):
        w = World(**kw)
        w.put(T_IN, "Подписал")
        for k in range(4):
            w.tick(T_CARD + k * EVERY)
        assert w.signed_drafts() == [] and not w.versions(), (kw, w.signed_drafts(), w.versions())
        assert w.find.calls == [] and w.fetch.calls == [] and w.book_reads == 0, \
            (kw, w.find.calls, w.fetch.calls, w.book_reads)


def _normal_path(signed, registry_signed=True):
    w = World(signed=signed, setup=None if registry_signed else unsigned36)
    w.model.text, w.model.check = "Договор во вложении", "full"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    w.press(1, t=T_IN + 200)
    w.model.text, w.model.check = "Пожалуйста", "none"
    w.put(T_IN + 300, "Спасибо")
    w.tick(T_IN + 400)
    w.tick(T_IN + 400 + EVERY)
    drafts = w.q("SELECT id, number, state, ver, text, upto_id, kind, reason, wamid FROM drafts ORDER BY id")
    attach = w.q("SELECT draft_id, file_id, sha256, row, reason FROM attach ORDER BY draft_id")
    return drafts, attach, w.door.sends, w.door.media, w.tg.cards, w.tg.done, w


def test_flag_off_same_as_before():
    """signed=False — то же, что вызов без аргумента (прежняя форма); и при signed=True без подписанной версии
    обычный путь (черновики, вложения, отправки, карточки) байт-в-байт тот же."""
    old, off = _normal_path(None), _normal_path(False)
    assert old[:6] == off[:6] and old[6].lines == off[6].lines, "signed=False отличается от прежнего вызова"
    off2, on2 = _normal_path(False, registry_signed=False), _normal_path(True, registry_signed=False)
    assert off2[:6] == on2[:6], ("без подписанной версии флаг изменил обычный путь", off2[:2], on2[:2])


def test_kind_signed_like_answer_label_on_card():
    """kind='signed' в руках Telegram — обычный ответ, кроме метки: карточка начинается «📄 Договор подписан», без
    «🔔 Напоминание»; карточка обычного черновика — прежняя «📝 Черновик»."""
    w = World(real_tg=True, setup=unsigned36)
    w.model.text, w.model.check = "Спасибо!", "none"
    w.put(T_IN, "Подписал")
    w.tick(T_IN + 100)
    w.reg(36)["status"] = SIGNED
    w.model.text = None
    w.tick(T_IN + 100 + EVERY)
    did = w.signed_drafts()[0][0]
    texts = [p["text"] for p in w.http.of("sendMessage")]
    firsts = [t.split("\n", 1)[0] for t in texts]
    assert [f for f in firsts if f.startswith("📝 Черновик №1 ")], firsts
    signed = [t for t in texts if t.split("\n", 1)[0].startswith(LABEL)]
    assert signed and "🔔" not in signed[-1].split("\n", 1)[0] and RU in signed[-1], firsts
    assert ("№%d" % did) in signed[-1].split("\n", 1)[0], firsts


def _svc(environ):
    """Служба `wa_agent_svc.build` на подделках: Bot API, провайдер, модель-адаптер стенда (двери сверки и брони)."""
    import test_wa_agent_svc as SV
    rig = Rig()
    env = {"queue_db": os.path.join(rig.dir, "svc_q.db"), "mirror_db": os.path.join(rig.dir, "mirror.db"),
           "agent_db": os.path.join(rig.dir, "svc_agent.db"), "tg_token": SV.TOKEN, "show_chat": SV.SHOW,
           "log_path": os.path.join(rig.dir, "wa_agent.log")}
    q = sqlite3.connect(env["queue_db"])
    q.execute(SV.QSCHEMA)
    q.commit()
    q.close()
    m = sqlite3.connect(env["mirror_db"])
    m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
              "stage TEXT, ts REAL, name TEXT)")
    m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
              "solo INTEGER)")
    m.commit()
    m.close()
    clock = SV.Clock(T_START)
    lines = []
    core, _tg, _flags, _words = S.build(
        env, environ=dict(environ), model=rig.model, http=SV.FakeHttp(clock),
        send=lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        send_media=lambda to, media, db_path=None: {"outcome": "not_sent", "reason": "набор не шлёт", "wamid": None},
        clock=clock, line=lines.append)
    return core, lines


SVC_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TOOLS": "1",
          "WA_AGENT_BOOK_READ": "1", "WA_AGENT_ATTACH": "1"}


def test_svc_flag_and_start_line():
    """WA_AGENT_SIGNED_CARD читает служба рядом с WA_AGENT_ATTACH, правилом всех выключателей (1/true — вкл), по
    умолчанию выкл; строка старта «карточка после подписи (WA_AGENT_SIGNED_CARD): вкл — …» / «… выкл — …»; без
    WA_AGENT_ATTACH карточки после подписи нет."""
    for val, on in ((None, False), ("0", False), ("", False), ("1", True), ("true", True)):
        environ = dict(SVC_ON)
        if val is not None:
            environ["WA_AGENT_SIGNED_CARD"] = val
        core, lines = _svc(environ)
        said = [ln.split(LINE_KEY, 1)[1].strip() for ln in lines if LINE_KEY in ln]
        if on:
            assert said and said[0].startswith("вкл —"), (val, lines)
        else:
            assert not [s for s in said if s.startswith("вкл")], (val, said)
        assert isinstance(core, X.AttachCore), (val, type(core))
        if hasattr(core, "signed"):
            assert bool(core.signed) is on, (val, core.signed)
    environ = dict(SVC_ON, WA_AGENT_SIGNED_CARD="1")
    environ.pop("WA_AGENT_ATTACH")
    core, lines = _svc(environ)
    assert not [ln for ln in lines if LINE_KEY + " вкл" in ln], lines
    assert not getattr(core, "signed", False), "карточка после подписи включилась без WA_AGENT_ATTACH"


# ═══ 9. база, журнал, храповик ═══════════════════════════════════════════════════════════

def test_signed_cards_table_and_key():
    """signed_cards(number, doc_id, signed_at, file_id, sha256, draft_id, ts), первичный ключ — версия
    (number, doc_id, signed_at, file_id)."""
    w, _did = card_world()
    info = w.q("PRAGMA table_info(signed_cards)")
    cols = {r[1] for r in info}
    assert {"number", "doc_id", "signed_at", "file_id", "sha256", "draft_id", "ts"} <= cols, info
    pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
    assert pk == ["number", "doc_id", "signed_at", "file_id"], pk


def test_journal_lines_signature():
    """Журнал: строка «подпись: …» с номером черновика, строкой реестра и началом sha256; текста клиента нет."""
    client_text = "Подписал, договор у меня на почте"
    w, did = card_world(text=client_text)
    sig = [ln for ln in w.lines if "подпись:" in ln]
    assert sig, w.lines[-12:]
    assert [ln for ln in sig if str(did) in ln and "36" in ln and SHA[36][:6] in ln], sig
    assert not [ln for ln in w.lines if client_text in ln], "текст клиента в журнале"


def test_blind_readers_ratchet_not_raised():
    """Новый код не поднимает храповик слепых читателей: в wa_agent_attach.py их нет, общее число не выше линии."""
    import blind_readers as BR
    with open(os.path.join(ROOT, "wa_agent_attach.py"), encoding="utf-8") as f:
        got = BR.find_blind(f.read(), "wa_agent_attach.py")
    assert got == [], got
    ok, lines = BR.ratchet(ROOT)
    assert ok, lines


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
