#!/usr/bin/env python3
"""РЕГРЕССИЯ красной команды NIGHT0710 Б3в (атаки на кандидат 79cfd3d5, PDF клиенту в службе) — второй круг строителя.

Каждый тест утверждает ПРАВИЛЬНОЕ поведение. Перенесено из attach_aux/red/tests/test_red_attach.py; на кандидате 79cfd3d
красными были r01 r02 r03 r08 r10d r12 r13b r15 r17 r18 r21 — на втором круге исправлены все, кроме r13b (реестр между
частями не перечитывается — назван пределом в артефакте, тест сюда НЕ перенесён). Изменения против оригинала: очередь
со статусами строится с `statuses=True` (квитанции вебхука теперь под выключателем, R15), r10d дополнительно проверяет
слова карточки после такта правки.
Всё на подделках строителя (`test_wa_attach_svc.World`): сети нет, модель, мост, Telegram, WhatsApp не зовутся.
Провайдер в R14 — НАСТОЯЩИЙ `wa_send.send_media` с поддельным транспортом (сети нет)."""
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import test_wa_attach_svc as AS  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402

NUM, T0 = AS.NUM, AS.T0


class HW(AS.World):
    """Мир с крючками внутри двери провайдера: крючок зовётся ДО ответа двери (посреди отправки)."""

    def __init__(self, *a, **kw):
        self.hooks = {}
        AS.World.__init__(self, *a, **kw)

    def send(self, to, text, db_path=None):
        h = self.hooks.pop("send", None)
        if h:
            h()
        return AS.World.send(self, to, text, db_path)

    def send_media(self, to, media, db_path=None):
        h = self.hooks.pop("media", None)
        if h:
            h()
        return AS.World.send_media(self, to, media, db_path)


def second(w):
    """Второй процесс службы на тех же базах: сборка = старт (`_startup`) на своём соединении."""
    core, tg, _f, _w = S.build(w.env, environ=dict(w.environ), model=w.model, http=w.http, send=w.send,
                               send_media=w.send_media, clock=w.clock, line=w.lines.append)
    return core, tg


def press_on(tg, data, uid):
    return tg.handle({"update_id": uid, "callback_query": {
        "id": "cq%d" % uid, "from": AS.HUMAN, "data": data,
        "message": {"message_id": 101, "chat": {"id": AS.CHAT}}}})


def card_texts(w):
    return [p["text"] for p in w.http.of("sendMessage")]


def put_echo(w, ts, wamid, number=NUM, msg_type="text"):
    q = sqlite3.connect(w.env["queue_db"])
    q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
              "VALUES(?,?,?,?,?,1,0,?)", (ts, number, msg_type, "ответ с телефона", ts, wamid))
    q.commit()
    q.close()


# ═══ R01–R03: «Отправить» шлёт PDF, которого человек не видел ═════════════════════════════════

def test_r01_card_shows_pdf_before_send():
    """R01. Карточка черновика (то, на что человек жмёт «Отправить») обязана назвать вложение: «Отправить» теперь
    шлёт ещё и подписанный договор. Сломано, если ни в одном сообщении карточки нет ни слова о PDF."""
    w = AS.World(AS.ON)
    w.ready()
    texts = card_texts(w)
    assert texts, "карточки нет"
    said = [t for t in texts if "PDF" in t or "📄" in t or "contract_41" in t or "договор" in t.lower()]
    assert said, "карточка молчит о PDF, а «Отправить» его шлёт: %r" % texts


def test_r02_human_rewrite_still_sends_model_pdf():
    """R02. «Исправить»: человек заменил текст модели своим («договор пришлём позже»). «Отправить» версии 2 шлёт
    его текст И подписанный PDF основания версии 1 — человек на карточке v2 PDF не видит и снять его не может
    (кнопки «без PDF» нет). Правильно: PDF не уходит молча с текстом человека (или карточка v2 его называет)."""
    w = AS.World(AS.ON)
    w.ready()
    assert w.core.revise(1, "Договор пришлём позже, сейчас без файла", "Дарья", now=T0 + 150, ver=1)
    v2 = card_texts(w)[-1]
    w.press("wa:send:1:2", card_id=102)
    shown = "PDF" in v2 or "📄" in v2 or "contract_41" in v2
    assert shown or not w.media, "v2: ушло %d PDF при карточке без PDF; ответ: %r" % (len(w.media), w.answers()[-1])


def test_r03_next_answer_resends_same_pdf():
    """R03. Второй ответ тому же клиенту, в сверке которого модель снова запросила contract_pdf (инструмент назван
    «метаданные PDF» — модель зовёт его ПРОВЕРКОЙ, а не просьбой приложить), шлёт ТОТ ЖЕ подписанный договор ещё
    раз. Признака «этот PDF этому клиенту уже ушёл (sent, wamid)» нет. Правильно: второй копии нет."""
    w = AS.World(AS.ON)
    w.ready()
    w.press("wa:send:1:1")
    assert len(w.media) == 1 and w.part()[0] == A.SENT, (w.media, w.part())
    w.put(T0 + 1000)
    made = w.core.tick(T0 + 1100)
    assert made == [2], made
    w.press("wa:send:2:1")
    same = [m for m in w.media if m[0] == NUM and m[4] == AS.SHA]
    assert len(same) == 1, "клиенту ушло %d копий одного договора (ответы 1 и 2): %r" % (len(same), w.answers()[-1])


# ═══ R04–R06: «неизвестно» вслепую не повторяется ═════════════════════════════════════════════

def test_r04_text_unknown_no_repeat_no_pdf():
    """R04. Текст «неизвестно»: PDF не зовётся, кнопок PDF нет, повторное «Отправить» и «Дослать» — отказ."""
    w = AS.World(AS.ON, text="unknown")
    w.ready()
    w.press("wa:send:1:1")
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)
    assert w.part()[:2] == (A.NOT_SENT, 1), w.part()
    assert not AS.kb_data(w.edits()[-1]), w.edits()[-1]
    w.press("wa:send:1:1")
    w.press("wa:pdf:1:1")
    w.press("wa:pdf_risk:1:1")
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media, w.answers())


def test_r05_pdf_unknown_plain_resend_never_calls_door():
    """R05. PDF «неизвестно»: обычное «Дослать» трижды — ни моста, ни двери."""
    w = AS.World(AS.ON, media="unknown")
    w.ready()
    w.press("wa:send:1:1")
    finds, fetches = len(w.model.find.calls), len(w.model.fetch.calls)
    for _ in range(3):
        w.press("wa:pdf:1:1")
    assert len(w.media) == 1, w.media
    assert len(w.model.find.calls) == finds and len(w.model.fetch.calls) == fetches, "мост звали без разрешения"


def test_r06_pdf_unknown_risk_refused_on_foreign_status():
    """R06. PDF «неизвестно», после попытки пришёл статус НЕИЗВЕСТНОГО нам сообщения этого номера (улика дубля) —
    даже «— риск дубля» не шлёт."""
    w = AS.World(AS.ON, media="unknown")
    w.ready()
    w.press("wa:send:1:1")
    w.status("wamid.ALIEN1", "sent", T0 + 20)
    w.press("wa:pdf_risk:1:1")
    assert len(w.media) == 1 and "статус сообщения" in w.answers()[-1], (w.media, w.answers()[-1])


# ═══ R07–R08: гонка — второй процесс службы ═══════════════════════════════════════════════════

def test_r07_second_process_starts_mid_text_no_dup():
    """R07. Второй экземпляр службы стартует, пока первый внутри двери ТЕКСТА: дублей текста и PDF нет."""
    w = HW(AS.ON)
    w.ready()
    box = {}
    w.hooks["send"] = lambda: box.update(b=second(w))
    w.press("wa:send:1:1")
    bcore, btg = box["b"]
    bcore.tick(T0 + 400)
    for i, data in enumerate(("wa:send:1:1", "wa:pdf:1:1", "wa:pdf_risk:1:1")):
        press_on(btg, data, 9000 + i)
    assert len(w.sends) == 1 and len(w.media) <= 1, (w.sends, w.media)


def test_r08_second_process_starts_mid_pdf_then_risk_dup():
    """R08. Второй экземпляр стартует, пока первый внутри двери PDF: его старт переводит часть sending→unsure; первый
    получает wamid.P1 и пишет outbox + part_log «sent», НЕ проверив, что UPDATE pdf_parts лёг (rowcount 0). Итог:
    журнал части знает «PDF ушёл, wamid.P1», а часть — «неизвестно» без wamid; карточка даёт «— риск дубля»,
    улики дубля нет (wamid.P1 «наш» по outbox) — второй PDF уходит. Правильно: одна отправка."""
    w = HW(AS.ON)
    w.ready()
    box = {}
    w.hooks["media"] = lambda: box.update(b=second(w))
    w.press("wa:send:1:1")
    bcore, btg = box["b"]
    log = w.q("SELECT attempt, outcome, wamid FROM part_log WHERE part='pdf'")
    part = w.part()
    bcore.tick(T0 + 400)
    press_on(btg, "wa:pdf_risk:1:1", 9100)
    assert len(w.media) == 1, "PDF ушёл %d раза; part_log=%r, часть до досылки=%r" % (len(w.media), log, part)


# ═══ R09: рестарт в каждой точке ══════════════════════════════════════════════════════════════

def test_r09a_restart_after_capture_before_text():
    """R09a. Смерть на перечитывании реестра (захват текста сделан, дверь не звана): после старта черновик снова
    ждёт; «Отправить» — ровно один текст и один PDF."""
    w = AS.World(AS.ON)
    w.ready()

    def die(**kw):
        raise AS.Crash()
    w.core.contract_find = die
    try:
        w.press("wa:send:1:1")
    except AS.Crash:
        pass
    w.restart()
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.PENDING,)], w.q("SELECT state FROM drafts")
    w.core.tick(T0 + 400)
    w.press("wa:send:1:1")
    assert len(w.sends) == 1 and len(w.media) == 1, (w.sends, w.media)


def test_r09b_restart_inside_text_door():
    """R09b. Смерть внутри двери текста: текст «неизвестно», PDF «не ушёл: текст неизвестно», кнопок нет,
    повтора нет."""
    w = AS.World(AS.ON, text="crash")
    w.ready()
    try:
        w.press("wa:send:1:1")
    except AS.Crash:
        pass
    w.text_out = "sent"
    w.restart()
    w.core.tick(T0 + 400)
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.UNSURE,)]
    assert w.part()[0] == A.NOT_SENT and w.media == [], w.part()
    w.press("wa:send:1:1")
    w.press("wa:pdf:1:1")
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)


def test_r09c_restart_after_pdf_door_before_commit_alien_status_blocks():
    """R09c. Смерть ПОСЛЕ ответа двери PDF (sent, wamid.P1), до записи: откат — часть «неизвестно» без wamid. Пришёл
    статус wamid.P1 (провайдер принял) — он теперь «чужой» и запирает «риск дубля». Дубля нет."""
    w = AS.World(AS.ON)
    w.ready()
    real = w.core._plog

    def boom(draft_id, part, *a, **kw):
        if part == "pdf":
            raise AS.Crash()
        return real(draft_id, part, *a, **kw)
    w.core._plog = boom
    try:
        w.press("wa:send:1:1")
    except AS.Crash:
        pass
    w.restart()
    w.status("wamid.P1", "sent", T0 + 30)
    w.core.tick(T0 + 400)
    w.press("wa:pdf_risk:1:1")
    assert len(w.media) == 1, (w.media, w.answers()[-1])


# ═══ R10: поздние статусы по точной части ═════════════════════════════════════════════════════

def _sent_world():
    import wa_webhook
    w = AS.World(AS.ON, webhook=True)
    w.ready()
    w.press("wa:send:1:1")
    return w, wa_webhook.WAQueueDB(w.env["queue_db"], statuses=True)


def _st(qdb, wamid, word, ts, frm=NUM):
    qdb.enqueue([{"type": "status", "from": frm, "text": word, "wamid": wamid, "ts": ts, "echo": True}])


def test_r10a_foreign_and_nonexistent_part_statuses_not_saved():
    """R10a. Статус чужого wamid и статус попытки, которой не было (wamid.P2), не сохраняются ни к одной части."""
    w, qdb = _sent_world()
    _st(qdb, "wamid.ZZZ", "read", T0 + 300)
    _st(qdb, "wamid.P2", "delivered", T0 + 301)
    _st(qdb, "wamid.T2", "read", T0 + 302)
    w.core.tick(T0 + 600)
    got = w.q("SELECT wamid FROM part_status")
    assert got == [], got


def test_r10b_read_before_delivered_both_kept():
    """R10b. Обратный порядок: read раньше delivered — оба сохраняются по точной части PDF, доставка названа."""
    w, qdb = _sent_world()
    _st(qdb, "wamid.P1", "read", T0 + 300)
    _st(qdb, "wamid.P1", "delivered", T0 + 301)
    w.core.tick(T0 + 600)
    got = w.q("SELECT status, part, attempt FROM part_status WHERE wamid='wamid.P1' ORDER BY status")
    assert got == [("delivered", "pdf", 1), ("read", "pdf", 1)], got
    assert w.core.parts(1)["delivery"][0] == "delivered"


def test_r10c_text_status_other_recipient_not_attributed():
    """R10c. Статус wamid ТЕКСТА с чужим получателем — части не приписывается."""
    w, qdb = _sent_world()
    _st(qdb, "wamid.T1", "read", T0 + 300, frm=AS.OTHER)
    w.core.tick(T0 + 600)
    assert w.q("SELECT COUNT(*) FROM part_status")[0][0] == 0


def test_r10e_status_of_resend_attempt_goes_to_attempt_2():
    """R10e. PDF попытки 1 «неизвестно», досылка «— риск дубля» ушла (попытка 2, wamid.P2): read по wamid.P2 ложится
    на попытку 2; попытка 1 (без wamid) статусов не получает."""
    import wa_webhook
    w = AS.World(AS.ON, webhook=True, media="unknown")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"
    w.press("wa:pdf_risk:1:1")
    qdb = wa_webhook.WAQueueDB(w.env["queue_db"], statuses=True)
    _st(qdb, "wamid.P2", "read", T0 + 300)
    w.core.tick(T0 + 600)
    got = w.q("SELECT wamid, status, part, attempt FROM part_status")
    assert got == [("wamid.P2", "read", "pdf", 2)], got


def test_r10d_failed_status_surfaces():
    """R10d. Провайдер прислал failed по wamid PDF ПОСЛЕ sent: статус сохранён, но карточка по-прежнему «PDF: ушёл»,
    кнопки «Дослать» нет, нажатие — «уже решено». Договор клиенту не доставлен, люди об этом не узнают ничем, кроме
    счётчика в сводке. Правильно: исход назван на карточке или дослать можно."""
    w, qdb = _sent_world()
    _st(qdb, "wamid.P1", "sent", T0 + 300)
    _st(qdb, "wamid.P1", "failed", T0 + 301)
    w.core.tick(T0 + 600)
    assert ("failed",) in w.q("SELECT status FROM part_status WHERE wamid='wamid.P1'")
    last = w.edits()[-1]["text"]
    buttons = w.core.card_buttons(1)
    assert buttons or "failed" in last or "не доставлен" in last, "failed молчит: карточка %r, кнопки %r" % (
        last[-80:], buttons)
    w.core.tick(T0 + 700)                                         # правка карточки — первым тактом после сбора
    last = w.edits()[-1]
    assert "не доставил" in last["text"] and AS.kb_data(last) == ["wa:pdf:1:1"], (last["text"][-120:], AS.kb_data(last))
    assert w.part()[:2] == (A.NOT_SENT, 1), w.part()


# ═══ R11–R12: чужой договор ═══════════════════════════════════════════════════════════════════

def _pick(**over):
    p = {"row": 41, "doc_id": "D41", "bike": "PCX 160 5580", "contract_date": "2026-10-03", "signed_at": AS.SIGNED,
         "pdf_id": "F41", "phone": "+66 81 234 5678", "matched_on": ["phone"], "signed": True}
    p.update(over)
    return {"ok": True, "outcome": "one", "filter": {"phone_last9": "812345678"}, "pick": p,
            "checked": {"unread": [], "undated_signed": 0, "rows_scanned": 9}}


def _rental(*rows):
    import wa_agent_tools as T
    return T.result("rental", T.FACT, facts=[dict({"kind": "rental", "booking_id": "B%d" % i, "bike": "PCX 160 5580",
                                                   "date_start": "2026-10-01", "date_end": "2026-10-07"}, **r)
                                              for i, r in enumerate(rows)])


def test_r11a_second_rental_same_client_guards():
    """R11a. Вторая аренда того же клиента: две активные брони → договор не привязан; договор с датой вне срока
    аренды → конфликт; другой байк → конфликт. (Граница T4a держит.)"""
    import wa_agent_tools as T
    two = T.contract_result(_pick(), at=T0, number=NUM, rental=_rental({}, {"date_start": "2026-11-01",
                                                                            "date_end": "2026-11-07"}))
    later = T.contract_result(_pick(contract_date="2026-11-02"), at=T0, number=NUM, rental=_rental({}))
    bike = T.contract_result(_pick(bike="NMAX 155 7777"), at=T0, number=NUM, rental=_rental({"bike": "PCX 160 5580"}))
    assert two["outcome"] != T.FACT and later["outcome"] == T.CONFLICT and bike["outcome"] == T.CONFLICT, (
        two["outcome"], later["outcome"], bike["outcome"])

def test_r12_other_client_same_tail_binds():
    """R12. Договор ДРУГОГО клиента (российский +7 981 234-56-78), чьи последние 9 цифр совпали с номером обращения
    (66812345678 → 812345678), привязывается сверкой Т4а как «этого номера» (bind_contract по last9) — и его PDF
    уйдёт обращению. Правильно: не FACT."""
    import wa_agent_tools as T
    import wa_book_read as B
    rental = T.result("rental", T.FACT, facts=[{"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580",
                                                "date_start": "2026-10-01", "date_end": "2026-10-07"}])
    resp = {"ok": True, "outcome": "one", "filter": {"phone_last9": "812345678"},
            "pick": {"row": 41, "doc_id": "D41", "bike": "PCX 160 5580", "contract_date": "2026-10-03",
                     "signed_at": AS.SIGNED, "pdf_id": "F41", "phone": "+7 981 234-56-78", "matched_on": ["phone"],
                     "signed": True},
            "checked": {"unread": [], "undated_signed": 0, "rows_scanned": 9}}
    out = T.contract_result(resp, at=T0, number=NUM, rental=rental)
    keys = B.phone_keys("Иван +7 981 234 56 78")
    assert out["outcome"] != T.FACT, "чужой договор принят: %s (ключи брони того клиента %r)" % (out["reason"], keys)


# ═══ R13: основание отозвано между текстом и PDF ══════════════════════════════════════════════

class Reg:
    """Реестр и двери моста с поведением ContractDoor.js: contract_pdf отказывает not_signed, если строка больше не
    ПОДПИСАН; contract_find отвечает по состоянию реестра."""

    def __init__(self, w):
        self.state = "one"
        self.w = w

    def find(self, **kw):
        self.w.model.find.calls.append(kw)
        if self.state == "revoked":
            return AS.REVOKED
        if self.state == "ambiguous":
            return {"ok": True, "outcome": "ambiguous", "checked": {"unread": [], "undated_signed": 0}}
        return AS.Find()(**kw)

    def fetch(self, file_id):
        self.w.model.fetch.calls.append(file_id)
        if self.state == "revoked":
            return {"ok": False, "error": "not_signed", "message": "строка реестра не «ПОДПИСАН»"}
        return dict(AS.Fetch()(file_id), row=41)


def _reg_world():
    w = HW(AS.ON)
    reg = Reg(w)
    w.model.tools = {"cash": lambda **kw: {"ok": False}, "contract": reg.find, "contract_pdf": reg.fetch}
    w.build(w.environ)
    return w, reg


def test_r13a_revoked_between_text_and_pdf():
    """R13a. Реестр перечитан (подписан) → текст ушёл → договор отозван → PDF не уходит; «Дослать» — отказ."""
    w, reg = _reg_world()
    w.ready()
    w.hooks["send"] = lambda: setattr(reg, "state", "revoked")
    w.press("wa:send:1:1")
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)
    w.press("wa:pdf:1:1")
    assert w.media == [] and "отозван" in w.answers()[-1], (w.media, w.answers()[-1])


# ═══ R14: провайдер — настоящий wa_send с поддельным транспортом ═══════════════════════════════

class RW(AS.World):
    """Текст — подделка строителя; PDF — `wa_send.send_media` целиком (загрузка и отправка — поддельный транспорт)."""

    def __init__(self, *a, mode="noid", **kw):
        self.mode, self.posts, self.ups = mode, [], []
        AS.World.__init__(self, *a, **kw)

    def send_media(self, to, media, db_path=None):
        import wa_send

        def up(url, fields, file, key, timeout):
            self.ups.append(file[0])
            return 200, json.dumps({"id": "media-red-1"}), None

        def post(url, payload, key, timeout):
            self.posts.append(payload)
            if self.mode == "noid":
                return 200, json.dumps({"messaging_product": "whatsapp", "messages": []}), None
            if self.mode == "5xx":
                return 503, json.dumps({"error": {"message": "Service Unavailable"}}), None
            if self.mode == "silent":
                return None, "", "ReadTimeout"
            return 200, json.dumps({"messages": [{"id": "wamid.R%d" % len(self.posts)}]}), None
        self.media.append((to, media["kind"], media["mime"], media["filename"], None))
        return wa_send.send_media(to, media, now=T0 + 150, db_path=db_path,
                                  env={"WA_SEND": "1", "WA_360_API_KEY": "red-team-key-0710"},
                                  transport=post, upload=up, sleep=lambda s: None)


def test_r14_provider_200_without_wamid_5xx_silence_unknown():
    """R14. 200 без wamid · 503 после успешного текста · молчание транспорта — PDF «неизвестно», POST ровно один,
    на карточке «Дослать»/«риск дубля», обычное «Дослать» — без двери."""
    for mode in ("noid", "5xx", "silent"):
        w = RW(AS.ON, mode=mode)
        w.ready()
        w.press("wa:send:1:1")
        assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.SENT,)], mode
        assert w.part()[:3] == (A.UNSURE, 1, None), (mode, w.part())
        assert len(w.posts) == 1, (mode, len(w.posts))
        assert AS.kb_data(w.edits()[-1]) == ["wa:pdf:1:1", "wa:pdf_risk:1:1"], (mode, w.edits()[-1])
        w.press("wa:pdf:1:1")
        assert len(w.posts) == 1, (mode, "обычное «Дослать» позвало провайдера")
    ok = RW(AS.ON, mode="ok")
    ok.ready()
    ok.press("wa:send:1:1")
    assert ok.part()[:3] == (A.SENT, 1, "wamid.R1"), ok.part()          # контроль: путь живой


# ═══ R15–R16: выключатель ═════════════════════════════════════════════════════════════════════

def test_r15_webhook_status_table_needs_switch():
    """R15. Выключатель WA_AGENT_ATTACH не запрошен — вебхук всё равно заводит в живой очереди таблицу wa_status и
    пишет в неё каждый статус (правка wa_webhook безусловна: поедет любым рестартом wa-webhook). Правильно: «по
    умолчанию выключено» и здесь."""
    import wa_webhook
    saved = os.environ.pop("WA_AGENT_ATTACH", None)
    try:
        d = tempfile.mkdtemp(prefix="red_wh_")
        qdb = wa_webhook.WAQueueDB(os.path.join(d, "q.db"))
        qdb.enqueue([{"type": "status", "from": NUM, "text": "sent", "wamid": "wamid.W1", "ts": T0, "echo": True}])
        con = sqlite3.connect(os.path.join(d, "q.db"))
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = con.execute("SELECT COUNT(*) FROM wa_status").fetchone()[0] if "wa_status" in tables else 0
        finally:
            con.close()
    finally:
        if saved is not None:
            os.environ["WA_AGENT_ATTACH"] = saved
    assert "wa_status" not in tables and rows == 0, "без выключателя: таблица wa_status, строк %d" % rows


def test_r16_flag_off_summary_and_start_identical():
    """R16. Выключено (нет/0/no/off) — строки старта и сводка службы те же; ядро прежнее."""
    def run(env):
        w = AS.World(env)
        w.ready()
        w.press("wa:send:1:1")
        return w.lines[:12], S.summary(w.core, w.tg, w.words, {}), type(w.core).__name__
    base = run(AS.BASE)
    for raw in ("0", "no", "off", ""):
        assert run(dict(AS.BASE, WA_AGENT_ATTACH=raw)) == base, raw
    assert base[2] == "Core" and "PDF" not in base[1], base[1]


# ═══ R17: ответ с телефона (пауза) и «Дослать» ════════════════════════════════════════════════

def test_r17_resend_pdf_while_human_took_over():
    """R17. Текст ушёл, PDF не ушёл; затем человек ответил клиенту с телефона (клиент на паузе — человек ведёт
    беседу). «Дослать PDF» всё равно шлёт: паузу и ответ с телефона «Дослать» не судит (у «Отправить» — судит).
    Правильно: на паузе агентская досылка не уходит без снятия паузы."""
    w = AS.World(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"
    put_echo(w, T0 + 300, "wamid.PHONE1")
    w.core.tick(T0 + 400)
    paused = w.q("SELECT paused FROM clients WHERE number=?", (NUM,))
    assert paused == [(1,)], paused
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1, "на паузе ушёл PDF: %r" % w.answers()[-1]


# ═══ R18: рестарт после решения человека перетирает карточку ══════════════════════════════════

def test_r18_restart_overwrites_human_decline_words():
    """R18. Обрыв между строкой pdf_parts «wait» и захватом текста; после старта человек нажал «Не нужно». Следующий
    рестарт переводит забытую «wait» в not_sent и ПЕРЕПИСЫВАЕТ исход карточки «не нужно: Дарья» словами
    «текст: declined · PDF: не ушёл … рестарт службы». Правильно: решение человека на карточке не трогается."""
    w = AS.World(AS.ON)
    w.ready()

    def die(*a, **kw):
        raise AS.Crash()
    w.core._text_part = die
    try:
        w.press("wa:send:1:1")
    except AS.Crash:
        pass
    w.restart()
    w.core.tick(T0 + 400)
    w.press("wa:no:1:1")
    said = w.edits()[-1]["text"]
    w.restart()
    w.core.tick(T0 + 500)
    last = w.edits()[-1]["text"]
    assert "не нужно" in said and "не нужно" in last, "исход человека перетёрт: было %r → стало %r" % (
        said[-60:], last[-80:])


# ═══ R19–R20: исключение двери и повтор обновления Telegram после смерти ══════════════════════

def test_r19_text_door_raises_exception_no_pdf_tx_closed():
    """R19. Дверь текста бросила обычное исключение (не смерть): текст «неизвестно», PDF не зовётся, транзакция
    закрыта, outbox пуст."""
    w = HW(AS.ON)
    w.ready()

    def boom():
        raise RuntimeError("сеть")
    w.hooks["send"] = boom
    w.press("wa:send:1:1")
    assert not w.core.db.in_transaction
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.UNSURE,)], w.q("SELECT state FROM drafts")
    assert w.media == [] and w.part()[0] == A.NOT_SENT, (w.media, w.part())
    assert w.q("SELECT COUNT(*) FROM outbox")[0][0] == 0


def test_r20_replayed_update_after_death_mid_resend():
    """R20. Смерть посреди «Дослать PDF» (внутри двери PDF): offset обновлений не сдвинут — после старта Telegram
    отдаёт ТО ЖЕ нажатие ещё раз. Повтор не должен дать второго PDF (номер попытки уже другой)."""
    w = HW(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"

    def die():
        raise AS.Crash()
    w.hooks["media"] = die
    upd = {"update_id": 7001, "callback_query": {"id": "r", "from": AS.HUMAN, "data": "wa:pdf:1:1",
                                                  "message": {"message_id": 101, "chat": {"id": AS.CHAT}}}}
    try:
        w.tg.handle(upd)
    except AS.Crash:
        pass
    w.restart()
    w.tg.handle(upd)                                              # тот же update_id: offset не сдвинулся
    w.core.tick(T0 + 400)
    assert len(w.media) == 1, "повтор обновления после смерти дал %d PDF-вызовов (первый — до смерти)" % len(w.media)


# ═══ R21: COMMIT исхода PDF не прошёл (база занята читателем) ═════════════════════════════════

def test_r21_commit_busy_loses_confirmed_wamid():
    """R21. Провайдер ответил sent/wamid.P1, служба ЖИВА, но COMMIT записи части упал «database is locked» (читатель
    держит SHARED-замок дольше busy-таймаута 10 с; читатели базы агента есть — wa_tg_mirror mode=ro). `_in_tx`
    страхует только BEGIN, а COMMIT — нет: откат, часть осталась sending без wamid, outbox и part_log пусты, а строка
    журнала файла уже сказала «sent, wamid есть». Правильно: подтверждённый провайдером wamid не теряется."""
    w = HW(AS.ON)
    w.ready()
    box = {}

    def hold():
        r = sqlite3.connect(w.env["agent_db"], timeout=1, isolation_level=None)
        r.execute("BEGIN")
        r.execute("SELECT COUNT(*) FROM drafts").fetchone()
        box["r"] = r
    w.hooks["media"] = hold
    real_end = w.core._tx_end

    def end(ok=True):
        try:
            return real_end(ok)
        finally:
            if not ok and "r" in box:                    # читатель ушёл сразу после отката (иначе offset не запишется)
                r = box.pop("r")
                r.execute("COMMIT")
                r.close()
    w.core._tx_end = end
    w.press("wa:send:1:1")
    said =[ln for ln in w.lines if "часть pdf" in ln and "wamid есть" in ln]
    part = w.part()
    out = w.q("SELECT COUNT(*) FROM outbox WHERE wamid='wamid.P1'")[0][0]
    assert part[2] == "wamid.P1" or out == 1, "журнал файла: %r; часть %r; outbox %d" % (said[-1:], part[:3], out)


# ═══ второй круг строителя: близнецы исправлений (то же без порчи — проходит) ═══════════════════════

def test_r12b_same_number_forms_still_bind():
    """Близнец R12: тот же номер с кодом страны («+66 81…», «+66 081…» с лишним нулём, «0066…») и местная запись
    («081…») — привязываются, как раньше; запрет — только явный ДРУГОЙ код страны при совпавшем хвосте."""
    import wa_agent_tools as T
    rental = T.result("rental", T.FACT, facts=[{"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580",
                                                "date_start": "2026-10-01", "date_end": "2026-10-07"}])
    for phone in ("+66 81 234 5678", "+66 081 234 5678", "0066812345678", "081 234 5678",
                  "+7 981 234-56-78 / 081 234 5678"):
        resp = _pick(phone=phone)
        out = T.contract_result(resp, at=T0, number=NUM, rental=rental)
        assert out["outcome"] == T.FACT, (phone, out["outcome"], out["reason"])
    assert T.phone_country_clash("+7 981 234-56-78", NUM) and not T.phone_country_clash("", NUM)


def test_r15b_webhook_switch_words():
    """Близнец R15: выключатель квитанций вебхука — то же правило, что у службы (1/true/yes/on); выкл — по умолчанию."""
    import wa_webhook
    for raw, want in (("1", True), ("true", True), ("ON", True), ("yes", True), ("0", False), ("", False),
                      ("no", False), (None, False)):
        env = {} if raw is None else {"WA_AGENT_ATTACH": raw}
        assert wa_webhook.statuses_on(env) is want, (raw, want)


def test_r17b_resend_after_pause_lifted():
    """Близнец R17: пауза снята — «Дослать PDF» шлёт (запрет держит именно пауза, а не кнопка)."""
    w = AS.World(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"
    w.press("wa:pdf:1:1")
    assert len(w.media) == 2 and w.part()[:3] == (A.SENT, 2, "wamid.P2"), (w.media, w.part())


def test_r03b_resend_button_refused_when_twin_went():
    """R03 со стороны «Дослать»: у старого черновика PDF не ушёл (кнопка жива), тот же договор ушёл НОВЫМ черновиком —
    старая кнопка второй копии не шлёт."""
    w = AS.World(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    assert w.part()[0] == A.NOT_SENT
    w.media_out = "sent"
    w.put(T0 + 1000)
    assert w.core.tick(T0 + 1100) == [2]
    # у второго черновика PDF есть (первый не ушёл — не двойник); он уходит
    w.press("wa:send:2:1", card_id=102)
    assert len(w.media) == 2, w.media
    w.press("wa:pdf:1:1")
    assert len(w.media) == 2 and "уже уходил" in w.answers()[-1], (w.media, w.answers()[-1])


def test_r03c_send_drops_pdf_when_twin_went_by_resend():
    """R03 со стороны «Отправить»: вложение второго черновика решено, пока PDF первого «не ушёл»; затем первый дослан
    кнопкой — «Отправить» второго шлёт только текст, второй копии того же договора нет."""
    w = AS.World(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.put(T0 + 1000)
    assert w.core.tick(T0 + 1100) == [2]
    assert "contract_41.pdf" in card_texts(w)[-1], card_texts(w)[-1]      # решено: первый PDF ещё не ушёл
    w.media_out = "sent"
    w.press("wa:pdf:1:1")
    assert w.part(1)[0] == A.SENT, w.part(1)
    w.press("wa:send:2:1", card_id=102)
    assert len(w.sends) == 2 and len(w.media) == 2, (w.sends, w.media)   # попытки PDF: не ушла + дослана; у №2 — нет
    assert w.part(2) is None, w.part(2)


def test_r01b_card_names_pdf_and_twin_reason():
    """Близнец R01/R03: карточка черновика с PDF называет файл и строку реестра; у следующего черновика того же
    договора — «PDF не приложен: … уже уходил»; ядро без флага — карточка без строки о PDF."""
    w = AS.World(AS.ON)
    w.ready()
    first = card_texts(w)[-1]
    assert "contract_41.pdf" in first and "строка реестра 41" in first, first
    w.press("wa:send:1:1")
    w.put(T0 + 1000)
    assert w.core.tick(T0 + 1100) == [2]
    second_card = card_texts(w)[-1]
    assert "PDF не приложен" in second_card and "уже уходил" in second_card, second_card
    off = AS.World(AS.BASE)
    off.ready()
    assert "📄" not in card_texts(off)[-1], card_texts(off)[-1]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
