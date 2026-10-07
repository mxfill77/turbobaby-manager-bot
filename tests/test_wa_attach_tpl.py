#!/usr/bin/env python3
"""INTEG0710 — связка выключателей ветки integ-0710 в СЛУЖБЕ: пояснения (NIGHT0710-B2, WA_AGENT_HINTS) × PDF клиенту
(NIGHT0710-B3v, WA_AGENT_ATTACH) × шаблон после 24 часов (NIGHT0710-B3g, WA_AGENT_TEMPLATES).

Каждая ветка проверяла свой выключатель одна; связку не покрывал ни один их набор (находки проб интегратора к слияниям
2 и 3, tmp/integ_0710/merge_aux/MERGE.md). Здесь:
  (1) сборка ядра — каждый флаг доходит до ядра своей дорогой (AttachCore получает и пояснения, и шаблоны, и правило
      языка), строки старта;
  (2) карточка — строка PDF, строка шаблона и подсказка пояснения вместе, кнопки;
  (3) нажатия — «Исправить»/«Отправить» при PDF и пояснениях, «Отправить» при закрытом окне ДО захвата;
  (4) граница, которую не видит git: окно 24 ч закрылось между пробой ядра и воротами двери при ядре с PDF-частью —
      черновик ждёт (замысел Б3г), часть PDF ждёт текста (замысел Б3в: «текст ещё не решён — PDF ждёт его»), на карточке
      «📨 Отправить шаблоном» с живыми кнопками, и правка карточки ложится ПОСЛЕ COMMIT текстовой части (Б3в: Telegram в
      транзакции не зовётся).

Подделки — World из tests/test_wa_attach_svc.py (Bot API, модель со сверкой Т4а, двери договоров, провайдер); сети нет,
модель не зовётся. Окно 24 ч меряет дверь (живые часы): очередь World датирована T0 = 1 790 000 000 (≈ 21.09.2026), поэтому
при WA_AGENT_TEMPLATES окно закрыто, а граница (4) задаётся подменой пробы окна и ответа двери."""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import test_wa_attach_svc as AS  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_tg as G  # noqa: E402

ALL3 = dict(AS.ON, WA_AGENT_HINTS="1", WA_AGENT_TEMPLATES="1")
HINTS_ATT = dict(AS.ON, WA_AGENT_HINTS="1")
ATT_TPL = dict(AS.ON, WA_AGENT_TEMPLATES="1")
HINTS_ONLY = dict(AS.BASE, WA_AGENT_HINTS="1")
TPL_ONLY = dict(AS.BASE, WA_AGENT_TEMPLATES="1")
KB3 = ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"]


def _lines(w, head):
    return [ln for ln in w.lines if ln.startswith(head)]


def _card(w, ver=1, did=1):
    row = w.core.db.execute("SELECT body FROM tg_cards WHERE draft_id=? AND ver=? ORDER BY card_id DESC",
                            (did, ver)).fetchone()
    return row[0] if row else ""


def _last_card_kb(w):
    cards = [p for p in w.http.of("sendMessage") if (p.get("reply_markup") or {}).get("inline_keyboard")]
    return [b["callback_data"] for row in cards[-1]["reply_markup"]["inline_keyboard"] for b in row]


# ═══ (1) сборка ядра: каждый выключатель доходит до ядра своей дорогой ═══════════════════════════════════════

def test_all_three_flags_core_and_start_lines():
    """Три флага: ядро с PDF-частью, пояснения и шаблоны включены, правило языка принесено; три строки старта «вкл»."""
    w = AS.World(ALL3)
    x = AS.X()
    assert isinstance(w.core, x.AttachCore) and w.core.attach, type(w.core)
    assert w.core.hints is True and w.core.templates is True and callable(w.core.lang_of), (
        w.core.hints, w.core.templates, w.core.lang_of)
    for head in ("пояснения (WA_AGENT_HINTS): вкл", "PDF клиенту (WA_AGENT_ATTACH): вкл",
                 "шаблоны (WA_AGENT_TEMPLATES): вкл"):
        assert _lines(w, head), (head, w.lines)


def test_hints_attach_core_carries_hints_templates_off():
    """Пояснения и PDF: ядро с PDF-частью несёт пояснения; шаблоны выключены и названы «выкл»."""
    w = AS.World(HINTS_ATT)
    x = AS.X()
    assert isinstance(w.core, x.AttachCore) and w.core.attach, type(w.core)
    assert w.core.hints is True and w.core.templates is False, (w.core.hints, w.core.templates)
    assert _lines(w, "пояснения (WA_AGENT_HINTS): вкл") and _lines(w, "шаблоны (WA_AGENT_TEMPLATES): выкл"), w.lines


def test_attach_templates_core_carries_templates_hints_off():
    """PDF и шаблоны: ядро с PDF-частью несёт шаблоны и правило языка; пояснения выключены и названы «выкл»."""
    w = AS.World(ATT_TPL)
    x = AS.X()
    assert isinstance(w.core, x.AttachCore) and w.core.attach, type(w.core)
    assert w.core.templates is True and callable(w.core.lang_of) and w.core.hints is False, (
        w.core.templates, w.core.lang_of, w.core.hints)
    assert _lines(w, "пояснения (WA_AGENT_HINTS): выкл") and _lines(w, "шаблоны (WA_AGENT_TEMPLATES): вкл"), w.lines


def test_attach_only_hints_and_templates_off():
    """Только PDF: ядро с PDF-частью, пояснения и шаблоны выключены (как на ветке Б3в)."""
    w = AS.World(AS.ON)
    assert w.core.attach and w.core.hints is False and w.core.templates is False, (
        w.core.attach, w.core.hints, w.core.templates)


def test_hints_only_plain_core():
    """Только пояснения: прежнее ядро wa_agent.Core с пояснениями, о PDF ни строки."""
    w = AS.World(HINTS_ONLY)
    assert type(w.core) is A.Core and w.core.hints is True and w.core.templates is False, type(w.core)
    assert not [ln for ln in w.lines if "WA_AGENT_ATTACH" in ln], w.lines


def test_templates_only_plain_core():
    """Только шаблоны: прежнее ядро wa_agent.Core с шаблонами, пояснения выкл, о PDF ни строки."""
    w = AS.World(TPL_ONLY)
    assert type(w.core) is A.Core and w.core.templates is True and w.core.hints is False, type(w.core)
    assert not [ln for ln in w.lines if "WA_AGENT_ATTACH" in ln], w.lines


def test_flags_off_core_as_before():
    """Всё выключено: прежнее ядро, шаблонов и пояснений нет, строки старта говорят «выкл»."""
    w = AS.World(AS.BASE)
    assert type(w.core) is A.Core and w.core.templates is False and w.core.hints is False, type(w.core)
    assert _lines(w, "шаблоны (WA_AGENT_TEMPLATES): выкл") and _lines(w, "пояснения (WA_AGENT_HINTS): выкл"), w.lines


# ═══ (2) карточка ═══════════════════════════════════════════════════════════════════════════════════════════

def test_all_three_card_lines_and_buttons():
    """Три флага, окно закрыто: на карточке строка PDF, строка шаблона и подсказка пояснения (шаблон — выше подсказки);
    кнопки — прежние три и вторым рядом «📨» этой версии."""
    w = AS.World(ALL3)
    w.ready()
    body = _card(w)
    assert "📄 «Отправить» шлёт ВТОРЫМ сообщением" in body, body
    assert "«%s»" % G.W_TPL_BUTTON in body and "reply_request" in body, body
    assert G.W_EXPLAIN in body, body
    assert body.index("📄") < body.index("«%s»" % G.W_TPL_BUTTON) < body.index(G.W_EXPLAIN), body
    assert _last_card_kb(w) == KB3 + ["wa:tpl:1:1"], _last_card_kb(w)


def test_hints_attach_card_pdf_and_explain_lines():
    """Пояснения и PDF: карточка несёт строку PDF (Б3в) и подсказку пояснения (Б2), строки шаблона нет; кнопки — три."""
    w = AS.World(HINTS_ATT)
    w.ready()
    body = _card(w)
    assert "📄 «Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора" in body, body
    assert G.W_EXPLAIN in body and G.W_TPL_BUTTON not in body, body
    assert body.index("📄") < body.index(G.W_EXPLAIN), body
    assert _last_card_kb(w) == KB3, _last_card_kb(w)


def test_attach_only_card_no_explain_no_template():
    """Только PDF: строка PDF есть, подсказки пояснения и строки шаблона нет; кнопки — три (как на ветке Б3в)."""
    w = AS.World(AS.ON)
    w.ready()
    body = _card(w)
    assert "📄 «Отправить» шлёт ВТОРЫМ сообщением" in body, body
    assert G.W_EXPLAIN not in body and G.W_TPL_BUTTON not in body, body
    assert _last_card_kb(w) == KB3, _last_card_kb(w)


# ═══ (3) нажатия ════════════════════════════════════════════════════════════════════════════════════════════

def test_hints_attach_hint_refused_words_no_model_call():
    """Пояснения и PDF: «Исправить» зовёт пояснение, а ядро с PDF-частью его не принимает словами (A15 Б2) — версии нет,
    модель на пояснение не зовётся, черновик ждёт как был."""
    import wa_agent_attach as X
    w = AS.World(HINTS_ATT)
    w.ready()
    calls = w.model.calls
    w.press("wa:fix:1:1")
    assert w.answers()[-1] == G.W_HINT_ASKED, w.answers()
    inv = w.core.db.execute("SELECT msg_id FROM tg_hint_prompts WHERE draft_id=1 AND ver=1").fetchone()
    assert inv and inv[0], inv
    w.uid += 1
    w.tg.handle({"update_id": w.uid, "message": {"message_id": 950, "from": AS.HUMAN, "chat": {"id": AS.CHAT},
                                                 "text": "про шлемы всегда «бесплатно»",
                                                 "reply_to_message": {"message_id": inv[0]}}})
    said = [p["text"] for p in w.http.of("sendMessage")]
    assert said[-1] == X.W_HINT_NO_CHECK, said[-1]
    w.clock.t += 200
    w.core.tick(w.clock.t)
    assert w.model.calls == calls, (w.model.calls, calls)
    assert w.q("SELECT state, ver FROM drafts WHERE id=1") == [(A.PENDING, 1)], w.q("SELECT state, ver FROM drafts")


def test_hints_attach_send_text_and_pdf_no_rule():
    """Пояснения и PDF: «Отправить» на версии 1 — текст и PDF двумя частями (как Б3в), правила из пояснения нет."""
    w = AS.World(HINTS_ATT)
    w.ready()
    w.press("wa:send:1:1")
    assert w.sends == [(AS.NUM, AS.TEXT)], w.sends
    assert len(w.media) == 1 and w.media[0][3] == "contract_41.pdf", w.media
    assert w.q("SELECT COUNT(*) FROM lessons")[0][0] == 0, w.q("SELECT * FROM lessons")


def test_all_three_send_refused_before_capture():
    """Три флага, окно закрыто: «✅ Отправить» отвечает словами ДО захвата — клиенту ни текста, ни PDF, черновик ждёт,
    правил нет; карточка правится с кнопкой «📨»."""
    w = AS.World(ALL3)
    w.ready()
    w.press("wa:send:1:1")
    assert w.answers()[-1].startswith("окно 24 ч закрыто"), w.answers()
    assert w.sends == [] and w.media == [], (w.sends, w.media)
    assert w.q("SELECT state, ver FROM drafts WHERE id=1") == [(A.PENDING, 1)], w.q("SELECT state, ver FROM drafts")
    assert w.q("SELECT COUNT(*) FROM lessons")[0][0] == 0
    last = w.edits()[-1]
    assert AS.kb_data(last) == KB3 + ["wa:tpl:1:1"], AS.kb_data(last)


# ═══ (4) граница Б3в × Б3г: окно закрылось между пробой ядра и воротами двери ═══════════════════════════════

def _closing_door(w):
    """Проба окна: первое измерение (проба ядра при нажатии) — открыто, дальше — закрыто (24 ч истекли между ними);
    дверь отказывает ДО сети с window=closed, как wa_send при закрытом окне."""
    seen = []

    def window(number, now=None):
        seen.append(number)
        return {"state": "open" if len(seen) == 1 else "closed", "age": 90000}

    w.core.door.window = window
    w.core.door.send = lambda to, text, db_path=None: {"outcome": "not_sent", "reason": "окно 24 ч закрыто",
                                                       "window": "closed", "wamid": None}
    return seen


def test_attach_templates_window_closes_at_door():
    """Ядро с PDF-частью и шаблонами, окно закрылось у ворот двери: черновик ждёт (pending, версия 1), PDF не уходил и
    часть PDF ждёт текста (wait, попытка 1), ПОСЛЕДНЯЯ правка карточки — с живыми кнопками и «📨 Отправить шаблоном»,
    ответ нажавшему — словами ядра про окно; правка карточки — вне транзакции текстовой части."""
    w = AS.World(ATT_TPL)
    w.ready()
    _closing_door(w)
    in_tx = []
    orig = w.core.tg.card_tpl

    def card_tpl(*a, **k):
        in_tx.append(w.core.db.in_transaction)
        return orig(*a, **k)

    w.core.tg.card_tpl = card_tpl
    w.press("wa:send:1:1")
    state = w.q("SELECT state, ver FROM drafts WHERE id=1")
    part = w.part()
    edits = w.edits()
    last_kb = AS.kb_data(edits[-1]) if edits else []
    facts = "черновик=%s · часть PDF=%s · правок карточки=%d · кнопки последней=%s · ответ=%r · в транзакции=%s" % (
        state, part, len(edits), last_kb, w.answers()[-1] if w.answers() else None, in_tx)
    print("  факты: " + facts)
    assert state == [(A.PENDING, 1)], facts
    assert w.sends == [] and w.media == [], facts
    assert part is not None and part[0] == "wait" and part[1] == 1, facts
    assert last_kb == KB3 + ["wa:tpl:1:1"], facts
    assert w.answers()[-1].startswith("окно 24 ч закрыто"), facts
    assert in_tx == [False], facts


def test_attach_templates_after_door_closed_pdf_not_stuck():
    """После границы часть PDF ждёт текста, а не решена: окно снова измерено открытым (дрожание пробы) — «Отправить»
    шлёт текст и PDF той же первой попыткой, как у Б3в (захват части не проигран «уже решено»)."""
    w = AS.World(ATT_TPL)
    w.ready()
    _closing_door(w)
    w.press("wa:send:1:1")
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.PENDING,)], w.q("SELECT state FROM drafts")
    w.core.door.window = lambda number, now=None: {"state": "open", "age": 60}
    w.core.door.send = w.send
    w.press("wa:send:1:1")
    assert w.sends == [(AS.NUM, AS.TEXT)], w.sends
    assert len(w.media) == 1 and w.media[0][3] == "contract_41.pdf", w.media
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.SENT,)], w.q("SELECT state FROM drafts")
    part = w.part()
    assert part is not None and part[0] == A.SENT and part[1] == 1, part


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
