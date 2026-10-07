#!/usr/bin/env python3
"""Д2 INTEG0710 «PDF выключает обучение»: при WA_AGENT_ATTACH и WA_AGENT_HINTS версия по пояснению проходит ТУ ЖЕ сверку
AttachCore, что версия модели (сверка Т4а → `attach_of`), в такте, до своей карточки; карточка называет итог ЕЁ сверки;
«Отправить» на ней — как в ядре Б2: владелец (по id) — действующее правило, сотрудник — кандидат; текст и подписанный PDF
уходят двумя частями.

До Д2 (A15, NIGHT0710-B2 круг 2) при WA_AGENT_ATTACH пояснение отклонялось словами (`W_HINT_NO_CHECK`), а версия по
пояснению шла под замок «без сверки» — обучение при PDF было выключено. Отрицательные формы (сверки версии нет, модель
сверку не умеет, флаги выключены) — здесь же.

Всё на подделках: ядро `AttachCore` (база во временном каталоге), руки Telegram (поддельный Bot API), НАСТОЯЩИЙ адаптер
`ModelAdapter` с НАСТОЯЩЕЙ сверкой `wa_agent_tools.run` и моделью-сценарием (rental → contract → contract_pdf → итог),
снимок броней, двери реестра договоров и PDF, дверь провайдера. Сети нет (соединение записывается и роняет вызов), модель,
мост, Telegram и WhatsApp не зовутся. spend_ledger подменяется шапкой test_wa_hint_rule (fcntl на ПК). Формат набора
дерева: PASS/FAIL/ИТОГ, код 1 при любом FAIL. WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import hashlib
import json
import os
import socket
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

_NET_TRIES = []                                                       # попытки соединения за прогон набора


def _no_net(*a, **kw):
    _NET_TRIES.append(repr(a)[:120])
    raise AssertionError("сеть в наборе запрещена: %r" % (a[:2],))


socket.socket.connect = lambda self, *a, **kw: _no_net(*a, **kw)      # noqa: E731
socket.socket.connect_ex = lambda self, *a, **kw: _no_net(*a, **kw)   # noqa: E731
socket.create_connection = _no_net

import test_wa_hint_rule as H  # noqa: E402  (подмена spend_ledger — в шапке набора)
import wa_agent_attach as X  # noqa: E402

A, G, WM, SV, TM = H.A, H.G, H.WM, H.SV, H.TM
NUM, CHAT, T0 = H.NUM, H.CHAT, H.T0
OWNER, STAFF = H.OWNER, H.STAFF
HINT, NEW, MODEL_TEXT, ASK_MARK = H.HINT, H.NEW, H.MODEL_TEXT, H.ASK_MARK
TOOLS_HEAD = "ИНСТРУМЕНТЫ (только чтение)"                             # первая строка блока сверки (wa_agent_tools)
RESULTS_HEAD = "РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ"
PDF = b"%PDF-1.4 signed contract bytes D2 INTEG0710"
SHA = hashlib.sha256(PDF).hexdigest()
PDF_NAME = "contract_41.pdf"
SIGNED = "2026-09-19 10:15:00"
BIKE = "PCX 160 5580"
RENT = {"status": "В аренде", "contacts": NUM, "bike": BIKE, "booking_id": "B7",       # строка листа «клиенты»
        "date_start": "2026-09-18 10:00", "date_end": "2026-09-25 10:00"}
PICK = {"row": 41, "doc_id": "D41", "bike": BIKE, "contract_date": "2026-09-19", "signed_at": SIGNED,
        "pdf_id": "F41", "phone": NUM, "signed": True}
REVOKED = {"ok": True, "outcome": "none_signed", "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0}}
OWNER_WHO = "Филипп (id 504608015)"
STAFF_WHO = "Дарья (id 501)"


# ═══ подделки ═══════════════════════════════════════════════════════════════════════════════════

class Find:
    """Дверь contract_find (форма ответа `bridge_client.contract_find`): подписанный договор ЭТОЙ аренды; answer — ответ
    целиком (отзыв и прочее)."""

    def __init__(self):
        self.calls, self.answer = [], None

    def __call__(self, **kw):
        self.calls.append(dict(kw))
        if self.answer is not None:
            return json.loads(json.dumps(self.answer))
        return {"ok": True, "outcome": "one", "pick": dict(PICK),
                "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0, "complete": True}}


class Fetch:
    """Дверь contract_pdf (форма `bridge_client.contract_pdf`: длину и sha256 сверяет клиент — verified)."""

    def __init__(self):
        self.calls = []

    def __call__(self, file_id):
        self.calls.append(file_id)
        return {"ok": True, "id": file_id, "verified": True, "name": PDF_NAME, "size": len(PDF), "sha256": SHA,
                "row": 41, "content_b64": base64.b64encode(PDF).decode()}


class Book:
    """Снимок броней (`wa_book_read.Snapshot.get` → строки, парк, возраст, почему)."""
    reads = 0

    def get(self, now):
        return [dict(RENT)], [], 60, ""


class CheckCall:
    """Модель-сценарий. Запрос сверки (блок инструментов) — rental → contract → contract_pdf → итог; запрос без блока
    (версия по пояснению без сверки, путь без флага) — сразу итог. Итог с блоком пояснения — NEW, иначе MODEL_TEXT.
    on_final — что сделать в момент итога версии по пояснению (клиент пишет, пока идёт сверка)."""
    STEPS = (("rental", {}), ("contract", {"phone": NUM}), ("contract_pdf", {"file_id": "F41"}))

    def __init__(self):
        self.calls, self.on_final = [], None

    def __call__(self, system, user):
        self.calls.append((system, user))
        use = {"model": "fake", "in": 10, "out": 5}
        if TOOLS_HEAD in user:
            done = user.split(RESULTS_HEAD, 1)[1] if RESULTS_HEAD in user else ""
            for tool, args in self.STEPS:
                if "%s →" % tool not in done:
                    return json.dumps({"tool": tool, "args": args}, ensure_ascii=False), use
        if self.on_final is not None and ASK_MARK in user:
            self.on_final()
        text = NEW if ASK_MARK in user else MODEL_TEXT
        return json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "сверено"}, ensure_ascii=False), use


class Door(TM.FakeDoor):
    """Дверь провайдера: текст (wamid.OUT…) и документ (wamid.PDF…) — оба sent."""

    def __init__(self):
        TM.FakeDoor.__init__(self)
        self.media = []

    def send_media(self, to, media):
        data, _why = media["fetch"](10 ** 9)
        self.media.append((to, media["kind"], media["filename"], hashlib.sha256(data).hexdigest()))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.PDF%d" % len(self.media)}


def world(tools=True, attach=True, hints=True, cls=None, **kw):
    """Мир Д2: test_wa_hint_rule.World с ядром AttachCore (или cls) и НАСТОЯЩИМ адаптером; tools — двери сверки Т4а у
    адаптера (как make_model(tools=True)); брони — снимок с арендой клиента; дверь провайдера — с документом."""
    find, fetch = Find(), Fetch()
    core_cls = cls or X.AttachCore
    ckw = dict(kw)
    if core_cls is not A.Core:
        ckw.update(attach=attach, pdf_fetch=fetch, contract_find=find)
    w = H.World(hints=hints, core_cls=core_cls, **ckw)
    w.find, w.fetch = find, fetch
    w.call = w.adapter.call = CheckCall()
    w.adapter.book = Book()
    w.adapter.tools = ({"cash": lambda **k: {"ok": False, "error": "касса не нужна"}, "contract": find,
                        "contract_pdf": fetch} if tools else None)
    w.door = w.core.door = Door()
    return w


def ready(w):
    w.ask()
    assert len(w.sent()) == 1, [m["text"][:40] for m in w.sent()]
    return w


def ver_text(w, did=1):
    return w.core.db.execute("SELECT ver, text, state FROM drafts WHERE id=?", (did,)).fetchone()


def hint_card_pdf():
    return X.W_HINT_CHECK % (2, X.W_HINT_CHECK_PDF % (PDF_NAME, X._size_words(len(PDF)), 41))


# ═══ 1. владелец: версия по пояснению со сверкой → карточка с итогом → текст + PDF + правило ════════════

def test_owner_send_checked_hint_version_rule_and_pdf():
    """Главный путь Д2. Пояснение сотрудника → такт (не приём сообщения) делает версию 2 СО СВЕРКОЙ Т4а — тем же путём,
    что версия модели (блок инструментов + блок пояснения, реестр — дверью сверки) → итог сверки на карточке версии 2
    (PDF уйдёт: имя · размер · строка реестра) → «Отправить» владельца (модель не зовётся): текст версии 2 и подписанный
    PDF двумя частями, действующее правило Б2 (номер, автор пояснения, нажал владелец по id); следующий черновик несёт
    правило. В журнале — номера и версии, текстов пояснения, ответа и номера клиента нет."""
    w = ready(world())
    assert PDF_NAME in w.card_text(1), w.card_text(1)                             # версия модели — PDF на карточке (Б3в)
    n0, f0 = len(w.call.calls), len(w.find.calls)
    w.explain(tick=False)
    ans = w.sent()[-1]["text"]
    assert ans.startswith("пояснение №1 принято"), ans
    assert len(w.call.calls) == n0, "модель звана при приёме пояснения, а не тактом"
    w.core.tick(w.t[0])
    assert ver_text(w) == (2, NEW, A.PENDING), ver_text(w)
    users = [u for _s, u in w.call.calls[n0:]]
    assert len(users) == 4 and all(ASK_MARK in u and TOOLS_HEAD in u for u in users), [u[:60] for u in users]
    assert w.find.calls[f0:] == [{"phone": NUM}], w.find.calls[f0:]                # реестр прочитан сверкой версии 2
    card2 = w.card_text(2)
    assert hint_card_pdf() in card2, card2
    assert "версия 2 по пояснению №1 (%s)" % STAFF_WHO in card2 and NEW in card2, card2
    assert "текст правил человек" not in card2, card2                              # текст версии писал агент
    assert w.core.db.execute("SELECT file_id, ver FROM attach WHERE draft_id=1").fetchone() == ("F41", 2)
    n1 = len(w.call.calls)
    words = w.send(OWNER)
    assert len(w.call.calls) == n1, "модель звана в нажатии"
    assert words.startswith("текст: ушёл · PDF: ушёл") and "правило №1 — действует" in words, words
    assert w.door.sends == [(NUM, NEW)], w.door.sends
    assert w.door.media == [(NUM, "document", PDF_NAME, SHA)], w.door.media
    assert w.rules() == [(1, A.LESSON_ACTIVE, STAFF_WHO, 501, T0 + 500, 1, 1, 2, HINT, OWNER_WHO, 504608015,
                          T0 + 500, 504608015)], w.rules()
    part = w.core.db.execute("SELECT state, wamid FROM pdf_parts WHERE draft_id=1").fetchone()
    assert part == (A.SENT, "wamid.PDF1"), part
    msg = [p for p in w.sent() if "Правило №1 · действующее правило" in p["text"]]
    assert msg and H.buttons(msg[-1]) == ["wa:unrule:1:0"], [p["text"][:50] for p in w.sent()[-3:]]
    w.ask("и ещё: доставка в Раваи?", ts=T0 + 200)                                  # обучение при PDF действует
    assert "№1: правило: " + HINT in H.rule_block(w.call.calls[-1][1]), w.call.calls[-1][1][:900]
    assert w.adapter.last["info"]["lessons"] == [1], w.adapter.last["info"]
    joined = "\n".join(w.lines)
    for s in (HINT, NEW, NUM):
        assert s not in joined, s
    assert "сверка версии 2 по пояснению" in joined, [ln for ln in w.lines if "вложение" in ln]
    assert not w.fell(), w.fell()


# ═══ 2. сотрудник: та же версия → текст + PDF, пояснение — кандидат ═════════════════════════════════════

def test_staff_send_checked_hint_version_candidate_and_pdf():
    """Вторая роль нажатия. «Отправить» сотрудника на версии по пояснению со сверкой — тот же текст и PDF двумя частями,
    а пояснение — только кандидат (решит владелец в суточном списке); сообщения правила с кнопками в группе нет."""
    w = ready(world())
    w.explain()
    assert ver_text(w) == (2, NEW, A.PENDING), (ver_text(w), w.sent()[-1]["text"][:120])
    assert hint_card_pdf() in w.card_text(2), w.card_text(2)
    before = len(w.sent())
    words = w.send(STAFF)
    assert words.startswith("текст: ушёл · PDF: ушёл") and "кандидат №1" in words, words
    assert w.door.sends == [(NUM, NEW)] and w.door.media == [(NUM, "document", PDF_NAME, SHA)], (w.door.sends,
                                                                                                w.door.media)
    r = w.rules()
    assert len(r) == 1 and r[0][1] == A.LESSON_CANDIDATE and r[0][9] is None and r[0][10] is None, r
    assert r[0][12] == 501 and (r[0][6], r[0][7]) == (1, 2), r
    after = w.sent()[before:]
    assert not [p for p in after if "Правило №" in p["text"]], [p["text"][:60] for p in after]
    assert not [b for p in after for b in H.buttons(p) if b.startswith(("wa:rule:", "wa:unrule:", "wa:lno:"))]
    assert not w.fell(), w.fell()


# ═══ 3. сверка версии — своя: договор отозван после версии модели ═════════════════════════════════════

def test_hint_version_check_is_its_own():
    """Сверка версии по пояснению — СВОЯ, а не унаследованная от версии 1: договор отозван между версией модели и
    пояснением — сверка версии 2 договора не принимает, карточка называет причину, «Отправить» владельца шлёт только
    текст (PDF не звали), правило Б2 рождается — одобрено содержание версии."""
    w = ready(world())
    assert PDF_NAME in w.card_text(1)
    w.find.answer = REVOKED
    w.explain()
    assert ver_text(w) == (2, NEW, A.PENDING), (ver_text(w), w.sent()[-1]["text"][:120])
    card2 = w.card_text(2)
    want = X.W_HINT_CHECK % (2, X.W_HINT_CHECK_NOPDF % "договор не принят сверкой: empty — подписанного нет")
    assert want in card2, card2
    assert w.core.db.execute("SELECT file_id, ver FROM attach WHERE draft_id=1").fetchone() == (None, 2)
    words = w.send(OWNER)
    assert words.startswith("sent") and "правило №1 — действует" in words, words
    assert w.door.sends == [(NUM, NEW)] and w.door.media == [] and w.fetch.calls == ["F41", "F41"], (
        w.door.sends, w.door.media, w.fetch.calls)                                 # PDF читала только сверка
    assert w.count_rules() == 1 and not w.fell(), (w.rules(), w.fell())


# ═══ 4. замок: сверки версии нет — «Отправить» снимает её, правила нет ═══════════════════════════════════

def test_hint_version_without_check_locked():
    """Пояснение принято, но путь сверки итога не дал (модель ответила без сверки) — карточка версии 2 говорит «сверки
    нет»; «Отправить» владельца снимает версию stale «без сверки»: клиенту ничего, правила нет."""
    w = ready(world())
    w.adapter.redraft_checked = lambda number, upto, prev, hint: w.adapter.redraft(number, upto, prev, hint)
    w.explain()
    assert ver_text(w)[:2] == (2, NEW), ver_text(w)
    card2 = w.card_text(2)
    assert X.W_HINT_CHECK_NONE % 2 in card2 and hint_card_pdf() not in card2, card2
    words = w.send(OWNER)
    assert words == X.W_NO_CHECK, words
    assert w.door.sends == [] and w.door.media == [] and w.count_rules() == 0, (w.door.sends, w.rules())
    assert ver_text(w)[2] == A.STALE, ver_text(w)


def test_previous_check_not_taken_for_hint_version():
    """Замок обёртки: итог сверки берётся только из `last`, записанного вызовом версии по пояснению. Путь сверки, не
    оставивший своего итога, не получает итог версии 1 (он ещё лежит в `last`) — версия «без сверки», «Отправить» её
    снимает, клиенту ничего."""
    w = ready(world())
    assert (w.adapter.last or {}).get("tools"), "версия 1 — со сверкой"
    w.adapter.redraft_checked = lambda number, upto, prev, hint: {"text": NEW, "handoff": [], "lang": "ru", "why": ""}
    w.explain()
    assert ver_text(w)[:2] == (2, NEW), ver_text(w)
    assert X.W_HINT_CHECK_NONE % 2 in w.card_text(2), w.card_text(2)
    assert w.send(OWNER) == X.W_NO_CHECK and w.door.sends == [] and w.count_rules() == 0, (w.answers(), w.rules())


def test_unfinished_hint_version_check_not_kept():
    """Версия по пояснению не дошла до карточки (клиент написал, пока шла сверка): пояснение — сбой словами, версии нет,
    итог её сверки такт не переживает (ключей версий в памяти обёртки нет)."""
    w = ready(world())
    w.call.on_final = lambda: w.put("ещё вопрос", ts=T0 + 300)
    n0 = len(w.call.calls)
    w.explain()
    assert len(w.call.calls) == n0 + 4, "сверка версии по пояснению не шла: %d вызовов" % (len(w.call.calls) - n0)
    assert ver_text(w)[:2] == (1, MODEL_TEXT), ver_text(w)
    assert w.core.db.execute("SELECT state FROM hints WHERE id=1").fetchone() == (A.HINT_FAIL,)
    assert not [k for k in w.core._seen if len(k) == 3], w.core._seen


# ═══ 5. границы «как раньше» ════════════════════════════════════════════════════════════════════════

def test_hint_refused_when_model_cannot_check():
    """Как раньше (A15): модель без сверки Т4а (дверей нет) — при WA_AGENT_ATTACH пояснение не принимается словами
    сразу, модель не зовётся, версии и строки пояснения нет."""
    w = ready(world(tools=False))
    n0 = len(w.call.calls)
    w.explain()
    assert [p for p in w.sent() if X.W_HINT_NO_CHECK in p["text"]], [p["text"][:80] for p in w.sent()[-3:]]
    assert len(w.call.calls) == n0 and ver_text(w)[0] == 1, (len(w.call.calls), ver_text(w))
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 0


def test_attach_off_hint_version_one_call_without_check():
    """Как раньше при WA_AGENT_ATTACH выкл (прежнее ядро Core): версия по пояснению — ОДИН вызов модели без сверки, даже
    когда у адаптера есть двери сверки (путь Б2); строки сверки и PDF на карточке нет; «Отправить» владельца — правило и
    текст."""
    w = ready(world(cls=A.Core))
    n0 = len(w.call.calls)
    w.explain()
    users = [u for _s, u in w.call.calls[n0:]]
    assert len(users) == 1 and ASK_MARK in users[0] and TOOLS_HEAD not in users[0], [u[:60] for u in users]
    card2 = w.card_text(2)
    assert "🔎 сверка Т4а" not in card2 and "📄" not in card2 and "по пояснению №1" in card2, card2
    words = w.send(OWNER)
    assert "правило №1 — действует" in words and w.door.sends == [(NUM, NEW)] and w.door.media == [], (
        words, w.door.sends, w.door.media)


def test_hints_off_attach_on_as_before():
    """Как раньше при WA_AGENT_HINTS выкл и WA_AGENT_ATTACH вкл: «Исправить» отвечает прежними словами (приглашения нет),
    пояснение ядру — прежний отказ `W_HINT_NO_CHECK`; версия модели уходит двумя частями (Б3в), правил нет."""
    w = ready(world(hints=False))
    assert w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1)) == H.OLD_FIX_WORDS, w.answers()
    assert w.invite() is None
    assert w.core.hint(1, 1, HINT, STAFF_WHO, 501) == {"ok": False, "words": X.W_HINT_NO_CHECK}
    words = w.send(OWNER, ver=1)
    assert words == "текст: ушёл · PDF: ушёл", words
    assert w.door.sends == [(NUM, MODEL_TEXT)] and len(w.door.media) == 1 and w.count_rules() == 0, (
        w.door.sends, w.door.media, w.rules())


# ═══ 6. живой путь службы ═══════════════════════════════════════════════════════════════════════════

LIVE_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TOOLS": "1",
           "WA_AGENT_BOOK_READ": "1", "WA_AGENT_ATTACH": "1", "WA_AGENT_HINTS": "1"}


class Bridge(H.LiveBridge):
    """Мост службы (`make_model`): знания, парк и цена — как в test_wa_hint_rule; брони, касса, реестр договоров и PDF —
    подделки той же формы, что у `bridge_client`."""

    def __init__(self):
        H.LiveBridge.__init__(self)
        self.find, self.fetch = Find(), Fetch()

    def clients(self, filter=None):
        return {"ok": True, "clients": [dict(RENT)]}

    def tx_find(self, **kw):
        return {"ok": False, "error": "касса не нужна"}

    def contract_find(self, **kw):
        return self.find(**kw)

    def contract_pdf(self, file_id):
        return self.fetch(file_id)


def _live():
    d = tempfile.mkdtemp(prefix="wa_attach_hint_live_")
    env = {"queue_db": os.path.join(d, "q.db"), "agent_db": os.path.join(d, "agent.db"), "tg_token": "123:SECRET",
           "show_chat": "", "mirror_db": "", "archive_db": os.path.join(d, "arch.db")}
    for path, schema in ((env["queue_db"], TM.QSCHEMA), (env["archive_db"], TM.ASCHEMA)):
        c = sqlite3.connect(path)
        c.execute(schema)
        c.commit()
        c.close()
    lines, sends, media, call, http, bridge = [], [], [], CheckCall(), TM.FakeHttp(), Bridge()
    model, why = SV.make_model(env, line=lines.append, bridge=bridge, call=call, book=True, tools=True, hints=True)
    assert model is not None, why

    def send(to, text, db_path=None):
        sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(sends)}

    def send_media(to, m, db_path=None):
        data, _why = m["fetch"](10 ** 9)
        media.append((to, m["kind"], m["filename"], hashlib.sha256(data).hexdigest()))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.PDF%d" % len(media)}
    core, tg, _flags, _words = SV.build(env, environ=dict(LIVE_ON), model=model, http=http, send=send,
                                        send_media=send_media, clock=lambda: T0 + 500, line=lines.append)
    return types.SimpleNamespace(env=env, lines=lines, sends=sends, media=media, call=call, http=http, model=model,
                                 core=core, tg=tg, bridge=bridge, uid=[0])


def _live_body(L, ver):
    row = L.core.db.execute("SELECT body FROM tg_cards WHERE draft_id=1 AND ver=?", (ver,)).fetchone()
    return row[0] if row else ""


def test_service_path_attach_and_hints_live():
    """Живой путь службы: make_model(tools, book, hints) → build(WA_AGENT_ATTACH=1, WA_AGENT_HINTS=1) → AttachCore →
    руки Tg.handle → Core.tick → make_hint_versions → _Probe.redraft → ModelAdapter.redraft_checked → _draft_tools →
    wa_agent_tools.run. Карточка версии 2 — с итогом её сверки; «Отправить» владельца — текст и PDF дверью службы, правило."""
    L = _live()
    assert type(L.core).__name__ == "AttachCore" and L.core.attach and L.core.hints, type(L.core)
    L.core.tick(T0 - 1000)
    H._live_put(L, "а шлем дадите?", T0)
    L.core.tick(T0 + 75)
    assert PDF_NAME in _live_body(L, 1), _live_body(L, 1)
    H._live_upd(L, callback_query={"id": "c1", "from": STAFF, "data": "wa:fix:1:1",
                                   "message": {"message_id": H._live_card(L, 1), "chat": {"id": CHAT}}})
    inv = L.core.db.execute("SELECT msg_id FROM tg_hint_prompts").fetchone()
    assert inv, [p.get("text", "")[:60] for p in L.http.of("sendMessage")]
    H._live_upd(L, message={"message_id": 900, "from": STAFF, "chat": {"id": CHAT}, "text": HINT,
                            "reply_to_message": {"message_id": inv[0]}})
    n0 = len(L.call.calls)
    L.core.tick(T0 + 100)
    assert H._live_card(L, 2), "версии по пояснению нет: " + "; ".join(L.lines[-6:])
    users = [u for _s, u in L.call.calls[n0:]]
    assert len(users) == 4 and all(ASK_MARK in u and TOOLS_HEAD in u for u in users), [u[:60] for u in users]
    assert hint_card_pdf() in _live_body(L, 2), _live_body(L, 2)
    H._live_upd(L, callback_query={"id": "c2", "from": OWNER, "data": "wa:send:1:2",
                                   "message": {"message_id": H._live_card(L, 2), "chat": {"id": CHAT}}})
    assert L.sends == [(NUM, NEW)] and L.media == [(NUM, "document", PDF_NAME, SHA)], (L.sends, L.media, L.lines[-6:])
    row = L.core.db.execute("SELECT state, decided_by_id, ver_to FROM lessons WHERE kind='hint'").fetchall()
    assert row == [(A.LESSON_ACTIVE, 504608015, 2)], row
    assert not [ln for ln in L.lines if "упало" in ln or "упал:" in ln], [ln for ln in L.lines if "упал" in ln]


# ═══ замок пробы ═══════════════════════════════════════════════════════════════════════════════════

def test_zz_modules_from_this_tree_and_no_network():
    """Модули ядра, PDF, адаптера, сверки и набор-основа взяты ИЗ этого дерева; попыток соединения за прогон — 0.
    Имя с «zz» — чтобы стоять последним (main гоняет случаи по имени)."""
    import wa_agent_tools as T
    root = os.path.normcase(os.path.realpath(os.environ.get("WA_AGENT_SRC") or ROOT))
    for mod in (A, X, WM, SV, T, H):
        path = os.path.normcase(os.path.realpath(getattr(mod, "__file__", "") or ""))
        assert path.startswith(os.path.normcase(os.path.realpath(ROOT)) + os.sep) or path.startswith(root + os.sep), (
            mod.__name__, path)
    assert _NET_TRIES == [], _NET_TRIES


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
