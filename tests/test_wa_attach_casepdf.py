#!/usr/bin/env python3
"""CASEPDF1510: агент сам отдаёт клиенту СВОЙ актуальный подписанный договор по ЯВНОЙ просьбе — поверх SIGNEDCARD1410
(`wa_agent_attach.AttachCore`), переиспользуя готовое: привязка кодом (`T.bind_ctx`/`T.call_tool("contract")`),
`_code_pdf`, `attach_of`, `_signed_held`/`_pdf_twin`, `_signed_insert`, штатное нажатие `press`/`_deliver` и раздельные
квитанции частей (`part_log`, `pdf_parts`). Нового анализа, SDK и параллельного генератора нет: ответ клиенту строит модель,
детектор (`contract_ask`) — только ограничитель первого узкого транспорта.

M2 — просьба открывает свою версию (и подписанную раньше водораздела); M3 — смешанная просьба: PDF к ответу модели, ответ не
снимается; M4 — WA_AGENT_AUTOSEND_CONTRACT: карточка подписи по ЧИСТОЙ просьбе нажимается системой (AUTO_WHO).

Стенд — живые форматы `tests/test_wa_signed_card.py` (World, Registry, Pdfs, Book, live_rows, номер 79999966963, стр.34/35
ОТОЗВАН, стр.36 ПОДПИСАН 2026-10-14 19:04, sha PDF36); детектор передаётся ядру параметром `ask_of`, как это делает служба.
Сети нет; модель, мост, Telegram и WhatsApp не зовутся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import contract_ask as CA  # noqa: E402
import test_wa_signed_card as SC  # noqa: E402  (живые форматы стенда подписи)

NUM, T_SIGN, PDF36, PDF37, SHA36 = SC.NUM, SC.T_SIGN, SC.PDF36, SC.PDF37, SC.SHA36
RU_TEXT, SORRY_RU = X.SIGNED_TEXT["ru"], X.SIGNED_SORRY["ru"]
SIGNED_AT = "2026-10-14 19:04"
ASK_RU = "Пришлите, пожалуйста, договор"                     # парафраз: живьём явной просьбы не было
MIXED_RU = "Пришлите договор и во сколько доставка?"
LIVE_NEGATIVES = (                                          # корпус 60 дней — дословно, ни одна не просьба
    "Мы же договорились",
    "А если допустим заключим контракт на год? Можно прям очень хорошую цену будет получить?)",
    "Подписал",
    "Какую сумму в рублях и куда перевести и будет ли договор?",
    "За 10 не договоримся?",
    "Тогда договорились",
)
LATE = T_SIGN + 7 * 3600                                    # первый старт через 7 ч: водораздел (−6 ч) ПОЗЖЕ подписи


class World(SC.World):
    """Стенд подписи + детектор просьбы (как у службы: `ask_of=contract_ask.verdict_many`) и флаг автоотправки."""

    def __init__(self, autosend=False, ask=True, **kw):
        self.autosend, self.ask = autosend, ask
        SC.World.__init__(self, **kw)

    def new_core(self):
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                            clock=self.clock, attach=True, pdf_fetch=self.pdfs, contract_find=self.registry,
                            signed=self.signed, signed_lookback_h=self.lookback_h,
                            ask_of=CA.verdict_many if self.ask else None, autosend=self.autosend)

    def asks(self):
        return self.q("SELECT draft_id, number, doc_id, signed_at, file_id, sha256, asked, kind, auto_at IS NOT NULL, "
                      "auto_state FROM signed_asks ORDER BY draft_id")

    def part_log(self, did):
        return self.q("SELECT part, attempt, who, outcome FROM part_log WHERE draft_id=? ORDER BY id", (did,))

    def auto_lines(self):
        return [ln for ln in self.lines if ln.startswith("подпись: автоотправка")]


def _arm(w, after):
    """Сразу после очереди ПЕРВОЙ карточки подписи (до автоотправки этого же такта) — шаг after(w, черновик), один раз."""
    real, done = w.core._card_new, []

    def wrapped(did, ver, now):
        got = real(did, ver, now)
        if not done and w.core.draft_kind(did) == X.KIND_SIGNED:
            done.append(did)
            after(w, did)
        return got
    w.core._card_new = wrapped


def _model_rental_only():
    """Сверка модели: аренду прочитала, договор (contract) не звала — путь реальной модели на «и во сколько доставка?»."""
    return {"state": "done", "results": [SC.res("rental", "fact", [
        {"kind": "rental", "booking_id": "B6334", "bike": SC.BIKE, "date_start": "2026-10-14", "date_end": "2026-10-17"}])]}


def _pure_late(autosend):
    w = World(start=LATE, autosend=autosend)
    w.put(LATE + 60, ASK_RU)
    w.tick(LATE + 600)
    return w


def _only_card(w):
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines()[-6:])
    return sd[0][0]


# ── (а) чистая просьба, версия раньше водораздела → одна карточка; автоотправка: выкл — ничего, вкл — ровно одна ──────

def test_a_pure_before_watershed_one_card_flag_off_nothing_sent():
    w = _pure_late(False)
    did = _only_card(w)
    sd = w.signed_drafts()[0]
    assert sd[1] == A.PENDING and sd[2] == SORRY_RU + RU_TEXT, sd           # с подписи 7 ч — шаблон с извинением
    assert w.attach(did)[:7] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", SIGNED_AT), w.attach(did)
    assert w.versions() == [(NUM, "D36", SIGNED_AT, "PDF36", SHA36, did)], w.versions()
    assert w.asks() == [(did, NUM, "D36", SIGNED_AT, "PDF36", SHA36, "pure", "card", 0, None)], w.asks()
    assert w.door.sends == [] and w.door.media == [], "флаг автоотправки выкл — клиенту ничего"
    assert w.auto_lines() == [], w.auto_lines()
    assert any("подписан раньше водораздела, но клиент сам просит договор (pure)" in ln for ln in w.sign_lines())
    assert any("по просьбе клиента (pure)" in ln for ln in w.sign_lines()), w.sign_lines()
    assert w.tg.cards == [did]
    for ln in w.lines:                                             # ни текста клиента, ни его номера целиком
        assert ASK_RU not in ln and NUM not in ln, ln


def test_a_watershed_holds_without_request_or_detector():
    """Контроль: без просьбы («Подписал») и без детектора (служба без карточки подписи) водораздел держит."""
    c = World(start=LATE)
    c.put(LATE + 60, "Подписал")
    c.tick(LATE + 600)
    assert c.signed_drafts() == [] and any("раньше водораздела, карточки нет" in ln for ln in c.sign_lines())
    b = World(start=LATE, ask=False)
    b.put(LATE + 60, ASK_RU)
    b.tick(LATE + 600)
    assert b.signed_drafts() == [] and b.core.ask_of is None


def test_a_pure_autosend_on_exactly_one_send_text_then_pdf():
    w = _pure_late(True)
    did = _only_card(w)
    text = SORRY_RU + RU_TEXT
    assert w.door.sends == [(NUM, text)], w.door.sends
    assert w.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36)], w.door.media
    assert w.part_log(did) == [("text", 1, X.AUTO_WHO, A.SENT), ("pdf", 1, X.AUTO_WHO, A.SENT)], w.part_log(did)
    assert w.q("SELECT state, decided_by FROM drafts WHERE id=?", (did,)) == [(A.SENT, X.AUTO_WHO)]
    assert w.q("SELECT state, wamid FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.SENT, "wamid.P1")]
    assert len(w.registry.calls) == 2, "реестр: проход и перечитывание при нажатии"
    assert w.pdfs.calls == ["PDF36", "PDF36"], ("сверка прохода и байты ДО текста — одно чтение на нажатие", w.pdfs.calls)
    assert w.auto_lines() == ["подпись: автоотправка черновика %d — текст: ушёл · PDF: ушёл" % did], w.auto_lines()
    assert w.asks()[0][6:] == ("pure", "card", 1, A.SENT), w.asks()
    assert w.core.signed_counts() == {"карточка": 1, "просьба_карточка": 1, "автоотправка": 1,
                                      "автоотправка_ушла": 1}, w.core.signed_counts()
    assert w.tg.cards == [did] and any(d == did and "PDF: ушёл" in words and X.AUTO_WHO in words
                                       for d, words in w.tg.done), w.tg.done
    # повтор тактов и рестарт — вторых отправок нет
    for k in range(1, 4):
        w.tick(LATE + 600 + k * (X.SIGNED_EVERY + 1))
    w.restart()
    w.tick(LATE + 600 + X.SIGNED_IDLE + 5 * X.SIGNED_EVERY)
    w.tick(LATE + 600 + 2 * X.SIGNED_IDLE + 6 * X.SIGNED_EVERY)
    assert len(w.door.sends) == 1 and len(w.door.media) == 1, (w.door.sends, w.door.media)
    assert [r[0] for r in w.signed_drafts()] == [did] and len(w.auto_lines()) == 1


def test_a_summary_names_autosend():
    w = _pure_late(True)

    class TgStub:
        polls = {"ok": 0, "fail": 0, "conflict": 0}
    w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_cards (x INTEGER)")
    w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_react_out (outcome TEXT)")
    line = S.summary(w.core, TgStub(), {k: "выкл" for k in S.FLAGS}, {})
    assert " · подписей автоотправка=1 автоотправка_ушла=1 карточка=1 просьба_карточка=1" in line, line


# ── (б) смешанная просьба → карточки подписи нет, ответ модели жив и несёт PDF; клиенту ничего без нажатия ──────────

def test_b_mixed_model_answer_keeps_text_and_carries_pdf():
    w = World(tools_out=_model_rental_only(), text="Доставка завтра в 10:00.", autosend=True)
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    assert w.q("SELECT id, state, kind, text FROM drafts ORDER BY id") == [
        (1, A.PENDING, None, "Доставка завтра в 10:00.")], w.q("SELECT id, state, kind, text FROM drafts")
    assert w.signed_drafts() == [], "смешанная просьба — карточки подписи нет"
    a = w.attach(1)
    assert a[:10] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", SIGNED_AT, NUM, "2026-10-14",
                      "2026-10-17"), a
    assert a[11] is None and X.OPORA_ASKED in (a[10] or ""), a
    assert (a[10] or "").count(X.OPORA_ASKED) == 3, ("аренда, договор и PDF — прочитаны кодом", a[10])
    assert w.versions() == [(NUM, "D36", SIGNED_AT, "PDF36", SHA36, 1)], "версия покрыта ответом модели"
    assert w.asks() == [(1, NUM, "D36", SIGNED_AT, "PDF36", SHA36, "mixed", "answer", 0, None)], w.asks()
    assert w.core.card_pdf(1, 1).startswith("📄 «Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора")
    assert w.door.sends == [] and w.door.media == [] and w.auto_lines() == [], "автоотправки у ответа модели нет"
    assert any("клиент просит договор: договор и PDF привязал КОД" in ln for ln in w.lines), w.lines[-8:]
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 700)    # человек нажал — текст модели и PDF
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.sends == [(NUM, "Доставка завтра в 10:00.")] and w.door.media[0][4] == SHA36
    for ln in w.lines:
        assert MIXED_RU not in ln and NUM not in ln, ln


def test_b_mixed_model_silent_no_signed_card():
    """Смешанная просьба, модель пока молчит (черновика нет): карточка подписи НЕ создаётся — шаблон «Направляем договор»
    не ответил бы на второй вопрос; ответит модель, и PDF к её ответу приложит код (M3). Клиенту ничего."""
    w = World(autosend=True)
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.signed_drafts() == [] and w.versions() == [] and w.asks() == [], (w.signed_drafts(), w.sign_lines())
    assert w.door.sends == [] and w.door.media == [] and w.auto_lines() == []
    assert any("вместе с другим вопросом: карточки подписи нет" in ln for ln in w.sign_lines()), w.sign_lines()
    w.model.tools_out, w.model.text = _model_rental_only(), "Доставка завтра в 10:00."   # модель ответила
    w.x("UPDATE clients SET next_try=0 WHERE number=?", (NUM,))
    w.tick(T_SIGN + 600 + 2 * X.SIGNED_EVERY + 2)
    assert w.attach(1)[0] == "PDF36" and w.signed_drafts() == [] and w.door.sends == [], w.attach(1)


def test_b_mixed_before_watershed_still_attached():
    w = World(start=LATE, tools_out=_model_rental_only(), text="Доставка завтра в 10:00.")
    w.put(LATE + 60, MIXED_RU)
    w.tick(LATE + 600)
    assert w.attach(1)[0] == "PDF36" and w.signed_drafts() == [], (w.attach(1), w.sign_lines())


def test_b_mixed_bind_fails_previous_row():
    """Код привязать не смог (в реестре два подписанных) — строка attach прежняя, ответ модели жив, без PDF."""
    rows = SC.live_rows()
    rows[1].update(status="ПОДПИСАН", signed=True)
    w = World(rows=rows, tools_out=_model_rental_only(), text="Доставка завтра в 10:00.")
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    a = w.attach(1)
    assert a[0] is None and a[11] == X.W_CONTRACT_NOT_CALLED, a
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.PENDING,)] and w.asks() == []
    assert any("код PDF не приложил" in ln for ln in w.lines), w.lines[-6:]


def test_b_mixed_without_detector_previous_row():
    w = World(ask=False, tools_out=_model_rental_only(), text="Доставка завтра в 10:00.")
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    assert w.attach(1)[0] is None and w.attach(1)[11] == X.W_CONTRACT_NOT_CALLED


# ── (в) не просьба (все 6 живых негативов) → прежнее поведение, ни одного лишнего вызова двери ─────────────────────

def _scenario(phrase, ask, autosend, tools=None, text=None):
    w = World(ask=ask, autosend=autosend, tools_out=tools, text=text)
    w.put(T_SIGN + 60, phrase)
    for t in (T_SIGN + 600, T_SIGN + 600 + X.SIGNED_EVERY + 1, T_SIGN + 600 + X.SIGNED_IDLE + 2 * X.SIGNED_EVERY):
        w.tick(t)
    return w


def _snap(w):
    return {"registry": list(w.registry.calls), "pdfs": list(w.pdfs.calls), "rental": list(w.rental_calls),
            "sends": list(w.door.sends), "media": list(w.door.media), "cards": list(w.tg.cards),
            "drafts": w.q("SELECT id, state, kind, text, upto_id, decided_by FROM drafts ORDER BY id"),
            "attach": w.q("SELECT draft_id, file_id, sha256, reason, opora FROM attach ORDER BY draft_id"),
            "versions": w.versions(), "lines": list(w.lines)}


def test_c_live_negatives_previous_behaviour_no_extra_door_calls():
    for phrase in LIVE_NEGATIVES:
        assert CA.verdict(phrase) is None, phrase
        for tools, text in ((None, None), (_model_rental_only(), "Хорошо!")):
            base = _snap(_scenario(phrase, False, False, tools, text))
            got = _scenario(phrase, True, True, tools, text)
            new = _snap(got)
            diff = [k for k in base if base[k] != new[k]]
            assert not diff, (phrase, text, diff, [(base[k], new[k]) for k in diff][:1])
            assert got.asks() == [] and got.auto_lines() == [] and got.door.sends == [], (phrase, got.auto_lines())


# ── (г) окно закрыто / пауза / эхо с телефона / двойник ушёл / отозван при нажатии / PDF подменён → автоотправки нет ──

def test_d_window_closed_at_autosend():
    w = World(autosend=True)
    real, calls = w.core._signed_window, []

    def window(number, now):
        calls.append(now)
        return real(number, now) if len(calls) == 1 else (False, "окно 24 ч закрыто или кончается")
    w.core._signed_window = window
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == [], w.door.sends
    assert w.auto_lines() == ["подпись: автоотправка черновика %d — не делалась: окно 24 ч: окно 24 ч закрыто или "
                              "кончается; карточка ждёт нажатия «Отправить»" % did], w.auto_lines()
    assert w.asks()[0][8:] == (0, X.AUTO_SKIP) and w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)]


def test_d_door_closed_attempt_not_spent():
    """Дверь WA_SEND закрыта — автоотправка не делается и попытку версии не тратит (нажатие было бы впустую)."""
    w = World(autosend=True)
    w.door.is_open = lambda: False
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert any("черновика %d — не делалась: отправка выключена (WA_SEND)" % did in ln for ln in w.auto_lines())
    assert w.asks()[0][8:] == (0, X.AUTO_SKIP) and w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)]


def test_d_pause_at_autosend():
    w = World(autosend=True)
    _arm(w, lambda w, did: w.x("UPDATE clients SET paused=1 WHERE number=?", (NUM,)))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert any("черновика %d — не делалась: клиент на паузе" % did in ln for ln in w.auto_lines()), w.auto_lines()


def test_d_phone_echo_between_card_and_autosend():
    w = World(autosend=True)
    _arm(w, lambda w, did: w.put(T_SIGN + 590, "", kind="echo"))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert any("черновика %d — не делалась: после черновика ответили с телефона" % did in ln
               for ln in w.auto_lines()), w.auto_lines()


def test_d_phone_echo_before_pass_no_card():
    """Ответили с телефона после просьбы — клиент на паузе, просьба закрыта человеком: ни карточки, ни отправки."""
    w = World(autosend=True)
    w.put(T_SIGN + 60, ASK_RU)
    w.put(T_SIGN + 120, "Сейчас пришлю", kind="echo")
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and w.door.sends == [] and w.door.media == []
    assert w.q("SELECT paused FROM clients WHERE number=?", (NUM,)) == [(1,)]
    assert any("клиент на паузе" in ln for ln in w.lines) and w.auto_lines() == []


def test_d_twin_already_sent_no_card_repeat_named():
    reg = SC.Registry(SC.live_rows()[:2])
    w = World(tools_out=SC.model_pdf36(), text="Договор ниже", registry=reg, autosend=True)
    w.put(T_SIGN + 60, "Подписал")
    w.tick(T_SIGN + 300)
    assert w.attach(1)[3] == SHA36
    reg.rows.append(SC.live_rows()[2])
    assert w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 400)["ok"]          # договор уже ушёл ответом модели
    w.model.tools_out, w.model.text = None, None
    w.put(T_SIGN + 500, "Пришлите договор ещё раз, пожалуйста")
    w.tick(T_SIGN + 500 + X.SIGNED_EVERY + 100)
    assert w.signed_drafts() == [] and len(w.door.media) == 1 and len(w.door.sends) == 1, w.door.media
    assert any("повтор по просьбе не автоматизирован" in ln and "уже уходил черновиком 1" in ln
               for ln in w.sign_lines()), w.sign_lines()
    assert w.auto_lines() == []


def test_d_revoked_at_press_nothing_sent():
    w = World(autosend=True)
    _arm(w, lambda w, did: w.registry.revoke(36))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.STALE,)]
    assert w.auto_lines() == ["подпись: автоотправка черновика %d — %s" % (
        did, X.W_BASIS % "подписанного договора больше нет — договор отозван")], w.auto_lines()
    for k in range(1, 4):                                          # отозванная версия: ни карточки, ни отправки
        w.tick(T_SIGN + 600 + k * (X.SIGNED_IDLE + X.SIGNED_EVERY))
    assert len(w.signed_drafts()) == 1 and w.door.sends == [] and w.door.media == []


def test_d_pdf_replaced_at_press_nothing_sent_card_waits():
    w = World(autosend=True)
    _arm(w, lambda w, did: w.pdfs.files.__setitem__("PDF36", (36, PDF37)))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)], "черновик ждёт, кнопки живы"
    said = w.auto_lines()
    assert len(said) == 1 and "sha256" in said[0] and "клиенту ничего не отправлено" in said[0], said
    assert w.asks()[0][8:] == (1, A.PENDING), w.asks()


# ── (д) просьба ДО подписи: не отвечена — карточка и автоотправка; отвечена — обычная карточка события ─────────────

def _before_signing(text, answered=False):
    reg = SC.Registry(SC.live_rows()[:2])
    w = World(registry=reg, tools_out=SC.NO_CONTRACT, text="Договор пришлём сразу после подписи.", autosend=True)
    w.put(T_SIGN - 700, text)
    for t in (T_SIGN - 400, T_SIGN - 279, T_SIGN - 158):          # три прохода «договора нет» — пауза номера SIGNED_IDLE
        w.tick(t)
        if answered and t == T_SIGN - 400:
            assert w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN - 390)["ok"]   # ответ модели ушёл — просьба отвечена
    assert w.signed_drafts() == [] and len(reg.calls) == 3, (w.signed_drafts(), reg.calls)
    reg.rows.append(SC.live_rows()[2])                            # подписан в 19:04
    return w, reg


def test_e_request_before_signing_card_and_autosend_after():
    w, reg = _before_signing(ASK_RU)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)], "ответ модели ждёт"
    w.tick(T_SIGN + 60)                                           # внутри паузы «договора нет»: просьба её не ждёт
    did = _only_card(w)
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.SUPERSEDED,)], "первая карточка версии заменила ответ"
    assert w.door.sends == [(NUM, RU_TEXT)] and w.door.media[0][4] == SHA36, (w.door.sends, w.door.media)
    assert w.part_log(did) == [("text", 1, X.AUTO_WHO, A.SENT), ("pdf", 1, X.AUTO_WHO, A.SENT)]
    assert len(reg.calls) == 5, "проход + перечитывание при нажатии"


def test_e_no_request_waits_for_idle():
    """Контроль той же хронологии без просьбы: номер на паузе «договора нет» — до её конца реестр не спрашивается."""
    w, reg = _before_signing("Подписываю")
    w.tick(T_SIGN + 60)
    assert w.signed_drafts() == [] and len(reg.calls) == 3, reg.calls


def test_e_request_already_answered_event_card_only():
    w, reg = _before_signing(ASK_RU, answered=True)
    w.tick(T_SIGN + 60)
    w.tick(T_SIGN + 60 + X.SIGNED_IDLE + X.SIGNED_EVERY)
    did = _only_card(w)
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)], "обычная карточка события ждёт нажатия"
    assert w.door.sends == [(NUM, "Договор пришлём сразу после подписи.")] and w.door.media == [], w.door.sends
    assert w.asks() == [] and w.auto_lines() == [], (w.asks(), w.auto_lines())


# ── (е) потолки: сутки на службу и одна автоотправка на версию ───────────────────────────────────────────────────

def _fill(w, n, at):
    for i in range(n):
        w.x("INSERT INTO signed_asks(draft_id, number, doc_id, signed_at, file_id, sha256, asked, kind, upto_id, ts, "
            "auto_at, auto_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (9000 + i, "6680000%04d" % i, "D%d" % (900 + i), "2026-10-14 10:00", "P%d" % i, "0" * 64, "pure", "card", 1,
             at - i, at - i, A.SENT))


def test_f_daily_cap():
    w = World(autosend=True)
    _fill(w, X.AUTOSEND_DAY_MAX, T_SIGN + 600 - 3600)
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = _only_card(w)
    assert w.door.sends == [] and w.door.media == []
    assert any("черновика %d — не делалась: суточный потолок автоотправок %d исчерпан" % (did, X.AUTOSEND_DAY_MAX)
               in ln for ln in w.auto_lines()), w.auto_lines()


def test_f_daily_cap_rolls_after_24h():
    w = World(autosend=True)
    _fill(w, X.AUTOSEND_DAY_MAX, T_SIGN + 600 - 86400 - 60)       # старше суток — не в счёт
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    assert len(w.door.sends) == 1 and len(w.door.media) == 1, w.auto_lines()


def test_f_one_autosend_per_version_after_reopen():
    """Автоотправка не дошла (PDF подменён — черновик ждёт), клиент написал «Спасибо» — карточка снята, версия снова
    открыта: новая карточка той же версии автоотправки НЕ получает (одна на версию) — только нажатием человека."""
    w = World(autosend=True)
    _arm(w, lambda w, did: w.pdfs.files.__setitem__("PDF36", (36, PDF37)))
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    first = _only_card(w)
    w.pdfs.files["PDF36"] = (36, PDF36)
    w.put(T_SIGN + 700, "Спасибо")
    w.tick(T_SIGN + 700 + X.SIGNED_EVERY + 100)
    sd = w.signed_drafts()
    assert [r[0] for r in sd][0] == first and len(sd) == 2 and sd[1][1] == A.PENDING, (sd, w.sign_lines()[-4:])
    assert w.door.sends == [] and w.door.media == []
    assert any("черновика %d — не делалась: по этой версии договора автоотправка уже была" % sd[1][0] in ln
               for ln in w.auto_lines()), w.auto_lines()
    out = w.core.press(sd[1][0], 1, A.ACT_SEND, "Даня", T_SIGN + 1000)
    assert out["ok"] and len(w.door.sends) == 1 and len(w.door.media) == 1, out


# ── (ж) выключено — байт-в-байт прежнее; строка старта службы ─────────────────────────────────────────────────

def test_g_signed_off_nothing_new():
    w = World(signed=False, autosend=True)
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    assert w.core.ask_of is None and not w.core.autosend
    tables = {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "signed_asks" not in tables and "signed_cards" not in tables, tables
    assert w.registry.calls == [] and w.pdfs.calls == [] and w.rental_calls == [] and w.door.sends == []


def test_g_no_detector_no_table_flag_ignored():
    w = World(ask=False, autosend=True)
    assert w.core.ask_of is None and not w.core.autosend
    assert "signed_asks" not in {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}
    assert w.core.signed_counts() == {}


def test_g_svc_start_lines_and_wiring():
    import test_wa_attach_svc as AS

    class Model(AS.Model):
        def _tool_doors(self, number, upto_id):
            return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}

    def built(environ, doors=True):
        w = AS.World(environ)
        if doors:
            w.model = Model()
            w.lines[:] = []
            w.build(environ)
        return w
    head = "автоотправка своего договора по просьбе (%s): " % S.F_AUTOSEND
    on = dict(AS.ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_AUTOSEND_CONTRACT="1")
    w = built(on)
    said = [ln for ln in w.lines if ln.startswith(head)]
    assert len(said) == 1 and said[0].startswith(head + "вкл — "), said
    assert w.core.autosend and w.core.ask_of is CA.verdict_many, (w.core.autosend, w.core.ask_of)
    w2 = built(dict(AS.ON, WA_AGENT_SIGNED_CARD="1"))             # карточка подписи вкл, автоотправка не запрошена
    said = [ln for ln in w2.lines if ln.startswith(head)]
    assert len(said) == 1 and said[0].startswith(head + "выкл — ") and not w2.core.autosend, said
    assert w2.core.ask_of is CA.verdict_many, "детектор работает и без автоотправки (M2/M3)"
    w3 = built(dict(AS.ON, WA_AGENT_AUTOSEND_CONTRACT="1"))       # автоотправка без карточки подписи — не засчитана
    said = [ln for ln in w3.lines if ln.startswith(head)]
    assert len(said) == 1 and "не засчитана" in said[0] and not getattr(w3.core, "autosend", False), said
    w4 = built(AS.ON)                                             # ничего не запрошено — строки нет вовсе
    assert not [ln for ln in w4.lines if S.F_AUTOSEND in ln] and getattr(w4.core, "ask_of", None) is None
    w5 = built(AS.BASE, doors=False)                              # PDF клиенту выкл — прежнее ядро, строки нет
    assert type(w5.core) is A.Core and not [ln for ln in w5.lines if S.F_AUTOSEND in ln]
    assert (S.F_AUTOSEND, S.AUTOSEND_DAY_MAX) == (X.F_AUTOSEND, X.AUTOSEND_DAY_MAX)
    assert S.autosend_of({}, False) == (False, None, None)


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
