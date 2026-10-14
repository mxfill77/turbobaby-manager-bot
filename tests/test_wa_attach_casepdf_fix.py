#!/usr/bin/env python3
"""CASEPDF1510 — ревизия по находкам двух критиков (поверх `tests/test_wa_attach_casepdf.py`, тот же стенд живых форматов
`tests/test_wa_signed_card.py`). Каждый случай — проверка ПОВЕДЕНИЯ, а не корпус фраз:

 (1) blocker: карточка по чистой просьбе сняла ответ, который правил человек (версия 2 · пояснение) или где модель просила
     человека, — автоотправки НЕТ, карточка ждёт нажатия; причины «нужен человек» видны на карточке подписи;
 (2) карточка события ждёт → клиент «Пришлите договор» → ответ модели (contract не звала) несёт проверенный PDF, привязанный
     КОДОМ; одно нажатие человека — текст и PDF; второй карточки нет;
 (3) автоотправка: текст ушёл, PDF нет — исход «text_only:…», а не «sent», и «ушла» в счёте нет;
 (4) неотвеченная просьба не дёргает реестр каждые SIGNED_EVERY дольше ASK_EAGER_SEC — дальше прежний ритм паузы;
 (5) просьба по решённой версии и смешанная просьба при живом ответе без PDF названы словами, как есть;
 (6) выключатель службы WA_AGENT_CONTRACT_ASK=0 — откат детектора (ask_of=None, путь SIGNEDCARD1410).

Сети нет; модель, мост, Telegram и WhatsApp — подделки. WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
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
import wa_agent_tools as T  # noqa: E402
import test_wa_signed_card as SC  # noqa: E402  (живые форматы стенда подписи)
import test_wa_attach_casepdf as CP  # noqa: E402  (стенд выпуска: детектор + автоотправка)

NUM, T_SIGN, SHA36 = SC.NUM, SC.T_SIGN, SC.SHA36
RU_TEXT, ASK_RU, MIXED_RU, SIGNED_AT = CP.RU_TEXT, CP.ASK_RU, CP.MIXED_RU, CP.SIGNED_AT
NO_CALL = {"state": "done", "results": []}                 # сверка модели завершена, contract модель НЕ звала
WAIT_TEXT = "Договор пришлём сразу после подписи."


def _signs_later(model_text, ask=ASK_RU):
    """Просьба ДО подписи, ответ модели ждёт; реестр пока без подписанного. → (мир, реестр)."""
    reg = SC.Registry(SC.live_rows()[:2])
    w = CP.World(registry=reg, tools_out=SC.NO_CONTRACT, text=model_text, autosend=True)
    w.put(T_SIGN - 700, ask)
    w.tick(T_SIGN - 400)
    assert w.q("SELECT id, state, ver FROM drafts") == [(1, A.PENDING, 1)], w.q("SELECT id, state, ver FROM drafts")
    return w, reg


def _signed_now(w, reg):
    reg.rows.append(SC.live_rows()[2])                      # подписан в 19:04
    w.tick(T_SIGN + 60)
    return CP._only_card(w)


def _asks(w, did):
    return w.q("SELECT replaced_id, auto_at IS NULL, auto_state FROM signed_asks WHERE draft_id=?", (did,))


# ── (1) blocker: решение человека и просьба модели о человеке шаблоном не отменяются ────────────────────────────────

def test_1_revised_by_human_card_waits_no_autosend():
    w, reg = _signs_later(WAIT_TEXT)
    assert w.core.revise(1, "Сначала внесите депозит 5000, потом отправим договор", "Даня", now=T_SIGN - 300)
    assert w.q("SELECT ver FROM drafts WHERE id=1") == [(2,)]
    did = _signed_now(w, reg)
    assert w.door.sends == [] and w.door.media == [], "решение человека шаблоном без нажатия не отменяется"
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.PENDING,)], "карточка ждёт нажатия"
    assert _asks(w, did) == [(1, 1, X.AUTO_SKIP)], _asks(w, did)
    said = w.auto_lines()
    assert len(said) == 1 and "который правил человек: версия 2 — решает человек" in said[0], said
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 200)           # человек решил сам — уходит штатно
    assert out["ok"] and w.door.sends == [(NUM, RU_TEXT)] and len(w.door.media) == 1, out


def test_1_human_hint_card_waits_no_autosend():
    w, reg = _signs_later(WAIT_TEXT)
    w.x("INSERT INTO hints(draft_id, ver_from, text, prev_text, author, ts, state) VALUES(1, 1, ?, ?, ?, ?, 'wait')",
        ("сначала депозит", WAIT_TEXT, "Даня", T_SIGN - 300))
    did = _signed_now(w, reg)
    assert w.door.sends == [] and w.door.media == []
    said = w.auto_lines()
    assert len(said) == 1 and "к которому было пояснение человека — решает человек" in said[0], said


def test_1_model_asked_for_human_reasons_on_card_no_autosend():
    why = "клиент спрашивает про скидку — решает человек"
    w, reg = _signs_later({"text": WAIT_TEXT, "handoff": [why]})
    assert w.core.handoff(1) == [why]
    did = _signed_now(w, reg)
    assert w.door.sends == [] and w.door.media == []
    assert w.core.handoff(did) == [why], "причины «нужен человек» видны на карточке подписи"
    said = w.auto_lines()
    assert len(said) == 1 and "где модель просила человека: причин 1 — решает человек" in said[0], said
    dump = repr(w.q("SELECT * FROM signed_asks"))
    assert "скидк" not in dump and ASK_RU not in dump, dump          # ни слов модели, ни текста клиента


def test_1_control_untouched_answer_still_autosent():
    """Контроль той же хронологии: ответ модели никто не трогал, причин нет — автоотправка, как в выпуске."""
    w, reg = _signs_later(WAIT_TEXT)
    did = _signed_now(w, reg)
    assert w.door.sends == [(NUM, RU_TEXT)] and len(w.door.media) == 1, w.auto_lines()
    assert _asks(w, did)[0][0] == 1 and w.q("SELECT replaced_why FROM signed_asks WHERE draft_id=?", (did,)) == [(None,)]
    assert w.core.handoff(did) == []


def test_1_event_card_replacing_handoff_unchanged():
    """Карточка события без просьбы (SIGNEDCARD1410): причины модели на карточку подписи НЕ переносятся — путь прежний."""
    w, reg = _signs_later({"text": "Спасибо!", "handoff": ["что-то"]}, ask="Подписываю")
    did = _signed_now(w, reg)
    assert w.core.handoff(did) == [] and w.q("SELECT * FROM signed_asks") == [] and w.door.sends == []


# ── (2) чистая просьба после снятой карточки события: PDF едет с ответом модели ───────────────────────────────────

def test_2_pure_ask_after_event_card_pdf_rides_model_answer():
    w = CP.World(autosend=True)
    w.put(T_SIGN + 60, "Подписал")
    w.tick(T_SIGN + 600)
    first = CP._only_card(w)
    w.model.tools_out, w.model.text = NO_CALL, "Сейчас пришлю."
    w.put(T_SIGN + 700, ASK_RU)
    t = T_SIGN + 700 + w.core.quiet + 60
    w.tick(t)
    assert w.q("SELECT state FROM drafts WHERE id=?", (first,)) == [(A.STALE,)], "карточку события сняло ядро"
    ans = w.q("SELECT id FROM drafts WHERE kind IS NULL AND state=?", (A.PENDING,))
    assert len(ans) == 1, w.q("SELECT id, state, kind FROM drafts")
    ans = ans[0][0]
    assert w.q("SELECT text FROM drafts WHERE id=?", (ans,)) == [("Сейчас пришлю.",)], "текст модели не тронут"
    a = w.attach(ans)
    assert a[0] == "PDF36" and a[3] == SHA36 and X.OPORA_ASKED in (a[10] or ""), a
    assert w.q("SELECT asked, kind, auto_at FROM signed_asks WHERE draft_id=?", (ans,)) == [("pure", "answer", None)]
    assert len(w.signed_drafts()) == 1 and w.door.sends == [] and w.door.media == [], "автоотправки у ответа модели нет"
    out = w.core.press(ans, 1, A.ACT_SEND, "Даня", t + 30)                   # одно нажатие — текст и PDF
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.sends == [(NUM, "Сейчас пришлю.")] and len(w.door.media) == 1
    for k in range(1, 4):
        w.tick(t + 30 + k * (X.SIGNED_IDLE + X.SIGNED_EVERY))
    assert len(w.signed_drafts()) == 1 and len(w.door.sends) == 1 and len(w.door.media) == 1, "второй карточки нет"
    assert w.versions() == [(NUM, "D36", SIGNED_AT, "PDF36", SHA36, ans)], w.versions()


def test_2_pure_first_card_still_replaces_answer():
    """Граница: первая карточка версии по-прежнему заменяет ждущий ответ — M3 к чистой просьбе тогда не применяется."""
    w = CP.World(tools_out=NO_CALL, text="Сейчас пришлю.")
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = CP._only_card(w)
    assert w.attach(1)[0] is None and w.q("SELECT state FROM drafts WHERE id=1") == [(A.SUPERSEDED,)]
    assert w.q("SELECT draft_id, asked, kind FROM signed_asks") == [(did, "pure", "card")]


# ── (3) исход автоотправки — по обеим частям ─────────────────────────────────────────────────────────────────

def test_3_autosend_text_only_not_recorded_as_sent():
    w = CP.World(autosend=True)
    w.door.media_out = "not_sent"
    w.put(T_SIGN + 60, ASK_RU)
    w.tick(T_SIGN + 600)
    did = CP._only_card(w)
    assert w.door.sends == [(NUM, RU_TEXT)] and len(w.door.media) == 1, (w.door.sends, w.door.media)
    st = w.q("SELECT auto_state FROM signed_asks WHERE draft_id=?", (did,))[0][0]
    assert st == "%s:%s" % (X.AUTO_TEXT_ONLY, A.NOT_SENT), st
    counts = w.core.signed_counts()
    assert counts.get("автоотправка") == 1 and "автоотправка_ушла" not in counts, counts


# ── (4) неотвеченная просьба: частый опрос реестра — только в окне ASK_EAGER_SEC ───────────────────────────────

def test_4_unanswered_ask_eager_only_within_window():
    reg = SC.Registry(SC.live_rows()[:2])
    w = CP.World(registry=reg)                               # модель молчит, подписанного нет
    w.put(T_SIGN + 60, ASK_RU)
    t0, step = T_SIGN + 600, X.SIGNED_EVERY + 1
    n = int(2 * 3600 / step)
    for k in range(n):
        w.tick(t0 + k * step)
    calls = len(reg.calls)
    eager = (X.ASK_EAGER_SEC - (t0 - (T_SIGN + 60))) // step + 2
    tail = (n * step - X.ASK_EAGER_SEC) // X.SIGNED_IDLE + 3
    assert calls <= eager + tail and calls < n // 2, (calls, eager, tail, n)
    reg.rows.append(SC.live_rows()[2])                      # подписал позже окна — карточка прежним ритмом паузы
    t1, made = t0 + n * step, None
    for k in range(int((X.SIGNED_IDLE + 2 * step) / step) + 2):
        w.tick(t1 + k * step)
        if w.signed_drafts():
            made = k
            break
    assert made is not None, w.sign_lines()[-4:]


def test_4_inside_window_ask_still_does_not_wait():
    """Граница: внутри окна просьба паузу «договора нет» не ждёт (приёмка: подписали через несколько проходов — карточка
    следующим тактом)."""
    reg = SC.Registry(SC.live_rows()[:2])
    w = CP.World(registry=reg)
    w.put(T_SIGN + 60, ASK_RU)
    for k in range(4):
        w.tick(T_SIGN + 600 + k * (X.SIGNED_EVERY + 1))
    assert len(reg.calls) == 4, reg.calls
    reg.rows.append(SC.live_rows()[2])
    w.tick(T_SIGN + 600 + 4 * (X.SIGNED_EVERY + 1))
    assert len(w.signed_drafts()) == 1


# ── (5) слова — как есть ──────────────────────────────────────────────────────────────────────────────────────

def test_5_ask_on_decided_version_named():
    w = CP.World()
    did = SC._card(w)
    assert w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 650)["ok"]
    w.put(T_SIGN + 700, "Пришлите договор ещё раз, пожалуйста")
    w.tick(T_SIGN + 700 + w.core.quiet + 60)
    assert len(w.signed_drafts()) == 1 and len(w.door.sends) == 1 and len(w.door.media) == 1
    assert any("версия решена черновиком %d" % did in ln and "повтор по просьбе не автоматизирован" in ln
               for ln in w.sign_lines()), w.sign_lines()
    for ln in w.lines:
        assert NUM not in ln and "Пришлите договор ещё раз" not in ln, ln


def test_5_mixed_line_names_live_answer_without_pdf():
    reg = SC.Registry()
    reg.fail = T.last9(NUM)                                 # привязка кодом при ответе модели — таймаут
    w = CP.World(registry=reg, tools_out=CP._model_rental_only(), text="Доставка завтра в 10:00.")
    w.put(T_SIGN + 60, MIXED_RU)
    w.tick(T_SIGN + 600)
    assert w.attach(1)[0] is None
    reg.fail = None
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.signed_drafts() == [] and w.door.sends == [] and w.door.media == []
    assert any("живой ответ модели (черновик 1) этот PDF не несёт" in ln for ln in w.sign_lines()), w.sign_lines()
    assert not any("PDF прикладывается к ответу модели" in ln for ln in w.lines)


# ── (6) откат детектора выключателем службы ─────────────────────────────────────────────────────────────────

def test_6_svc_contract_ask_off_rolls_back():
    import test_wa_attach_svc as AS

    class Model(AS.Model):
        def _tool_doors(self, number, upto_id):
            return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}

    def built(environ):
        w = AS.World(environ)
        w.model = Model()
        w.lines[:] = []
        w.build(environ)
        return w
    head = "автоотправка своего договора по просьбе (%s): " % S.F_AUTOSEND
    assert S.F_CONTRACT_ASK == X.F_CONTRACT_ASK
    for raw in ("0", "off", "no", "false"):
        w = built(dict(AS.ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_AUTOSEND_CONTRACT="1", WA_AGENT_CONTRACT_ASK=raw))
        said = [ln for ln in w.lines if ln.startswith(head)]
        assert len(said) == 1 and said[0].startswith(head + "выкл — детектор просьбы клиента выключен (%s)"
                                                     % S.F_CONTRACT_ASK) and "не засчитан" in said[0], (raw, said)
        assert w.core.signed and w.core.ask_of is None and not w.core.autosend, raw
        tables = {r[0] for r in w.core.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "signed_cards" in tables and "signed_asks" not in tables, tables
    for raw in (None, "1", "yes", ""):
        env = dict(AS.ON, WA_AGENT_SIGNED_CARD="1")
        if raw is not None:
            env["WA_AGENT_CONTRACT_ASK"] = raw
        w = built(env)
        assert w.core.ask_of is X.ask_verdict_many, raw


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
