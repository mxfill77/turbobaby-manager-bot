#!/usr/bin/env python3
"""Предельный возраст знаний черновика и строка журнала о них (WAKNOWFRESH0310). Снимок узла перечитывается
не чаще max_age (600 с); при отказе моста прежний текст идёт с возрастом, но не дольше max_stale (3 × max_age
= 1800 с). Старше — вместо текста узла «НЕИЗВЕСТНО: снимок старше N мин, <причина>», ни одной строки текста, и
причина «знания устарели» в handoff: «Отправить» на версии 1 есть, пометка видна (WACARDUI0510). На каждый вызов — строка журнала «знания: …»:
имя, прочитан ли сейчас, длина, sha16, возраст; текста узлов в журнале нет.
Всё на подделках: модель, мост (узлы, парк, дверь цены), часы, Bot API и дверь отправки — из test_wa_agent_model;
сети нет, модели нет. Тексты узлов выдуманы.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — адаптер модели на подделках

TEXT = {"faq": "FAQ-СТРОКА-1: доставка по Пхукету от 3 суток\nFAQ-СТРОКА-2: депозит наличными или паспорт",
        "business_rules": "ПРАВИЛО-СТРОКА-1: шлем обязателен\nПРАВИЛО-СТРОКА-2: права категории A\n"
                          "ПРАВИЛО-СТРОКА-3: предоплату называет человек"}
LINES = [ln for t in TEXT.values() for ln in t.split("\n")]
SHA = {n: hashlib.sha256(t.encode("utf-8")).hexdigest()[:16] for n, t in TEXT.items()}
STALE = "знания устарели"
ACT_STALE = "знания устарели: агент писал без свежих правил и FAQ — сверьте ответ сами"
T0 = TM.T0
MAX_AGE, MAX_STALE = 600, 1800
Q = "Здравствуйте, хочу взять PCX 160 на неделю"      # кода «нужен человек» нет, блока «ЦЕНА» нет
REPLY = json.dumps({"text": "Добрый день! Подскажите даты.", "lang": "ru", "handoff": [], "why": "вопрос"},
                   ensure_ascii=False)


class Bridge:
    """Подделка read_doc: мост жив — узел; лёг — TimeoutError (как отказ транспорта у `bridge_client`)."""

    def __init__(self):
        self.down, self.reads = False, []

    def read_doc(self, name):
        self.reads.append(name)
        if self.down:
            raise TimeoutError()
        return {"ok": True, "text": TEXT[name]}


def draft_at(kn, t, q=Q):
    """Новый мир с ОБЩИМИ снимками знаний и часами адаптера на t → (мир, промпт, причины, карточка)."""
    w = TM.World(reply=REPLY)
    w.adapter.knowledge = kn
    w.adapter.clock = lambda: t
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    system, user = w.call.calls[-1]
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    return w, system + "\n" + user, hand, cards[-1]


def know_lines(w):
    return [ln for ln in w.lines if ln.startswith("знания: ")]


def actions(text):
    return [ln[2:] for ln in text.split("\n") if ln.startswith("• ")]


def no_node_text(where, what):
    leaked = [ln for ln in LINES if ln in where]
    assert not leaked, (what, leaked)


# ═══ проверки Штаба (п.4): t0 — ок; отказы; t0+max_age+1 — прежний текст; t0+max_stale+1 — НЕИЗВЕСТНО ══════════

def test_timeline_snapshot():
    br = Bridge()
    kn = K.Knowledge(br.read_doc, max_age=MAX_AGE)
    assert kn.max_stale == 3 * MAX_AGE == MAX_STALE, kn.max_stale                     # предел по умолчанию
    snap = kn.refresh(T0)                                                             # t0 — мост жив
    for n in K.NODES:
        assert snap[n]["call"] == K.CALL_READ and K.node_block(snap[n], T0).endswith(TEXT[n]), snap[n]
    br.down = True                                                                    # дальше — отказы
    snap = kn.refresh(T0 + 300)                                                       # моложе max_age — моста нет
    assert br.reads.count("faq") == 1 and snap["faq"]["call"] == K.CALL_KEPT, br.reads
    snap = kn.refresh(T0 + MAX_AGE + 1)                                               # прежний текст с возрастом
    for n in K.NODES:
        b = K.node_block(snap[n], T0 + MAX_AGE + 1)
        assert snap[n]["call"] == K.CALL_FAILED and "мост не отвечает (TimeoutError)" in snap[n]["why"], snap[n]
        assert "снят 10 мин назад" in b and b.endswith(TEXT[n]) and "НЕИЗВЕСТНО" not in b, b
        assert K.node_age(snap[n], T0 + MAX_AGE + 1) == MAX_AGE + 1, snap[n]          # неудача возраст не освежила
    assert K.stale_reasons(snap.values(), T0 + MAX_AGE + 1) == []
    snap = kn.refresh(T0 + MAX_STALE)                                                 # ровно на пределе — ещё текст
    assert all(K.node_block(snap[n], T0 + MAX_STALE).endswith(TEXT[n]) for n in K.NODES)
    assert K.stale_reasons(snap.values(), T0 + MAX_STALE) == []
    snap = kn.refresh(T0 + MAX_STALE + 1)                                             # старше предела
    for n in K.NODES:
        b = K.node_block(snap[n], T0 + MAX_STALE + 1)
        assert b.startswith("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)." % n), b
        no_node_text(b, n)
    got = K.stale_reasons(snap.values(), T0 + MAX_STALE + 1)
    assert [r["words"] for r in got] == [STALE] and got[0]["reason"] == K.R_STALE, got


def test_draft_old_text_then_unknown():
    br = Bridge()
    kn = K.Knowledge(br.read_doc)                                                     # как у адаптера: 600 / 1800
    w, prompt, hand, card = draft_at(kn, T0)                                          # t0 — ок
    assert all(ln in prompt for ln in LINES) and hand == [], hand
    assert TM.buttons(card)[0] == "wa:send:1:1", TM.buttons(card)
    br.down = True
    w, prompt, hand, card = draft_at(kn, T0 + MAX_AGE + 1)                            # отказ — прежний текст
    assert all(ln in prompt for ln in LINES) and "снят 10 мин назад" in prompt, prompt[-600:]
    assert hand == [] and TM.buttons(card)[0] == "wa:send:1:1", (hand, TM.buttons(card))
    w, prompt, hand, card = draft_at(kn, T0 + MAX_STALE + 1)                          # старше предела
    no_node_text(prompt, "промпт")
    for n in K.NODES:
        assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" % n) in prompt, n
    assert "НУЖЕН ЧЕЛОВЕК: " + STALE in prompt, prompt[-600:]
    assert hand == [STALE], hand
    assert TM.buttons(card) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)   # «Отправить» есть (WACARDUI0510)
    assert actions(card["text"]) == [ACT_STALE], card["text"]
    assert TM.G.W_SEND_HAND in card["text"], card["text"]
    w.press("wa:send:1:1", 101)                                                       # решил человек
    assert w.door.sends == [(TM.NUM, w.drafts()[0][3])], w.door.sends


def test_journal_line_sha16_without_text():
    br = Bridge()
    kn = K.Knowledge(br.read_doc)
    w, _p, _h, _c = draft_at(kn, T0)
    got = know_lines(w)
    assert len(got) == 1, got                                                         # строка на вызов
    assert got[0] == ("знания: business_rules — прочитан, снимок %d симв., sha16 %s, возраст 0 с; "
                      "faq — прочитан, снимок %d симв., sha16 %s, возраст 0 с"
                      % (len(TEXT["business_rules"]), SHA["business_rules"], len(TEXT["faq"]), SHA["faq"])), got
    br.down = True
    w, _p, _h, _c = draft_at(kn, T0 + MAX_AGE + 1)
    got = know_lines(w)
    assert len(got) == 1 and "faq — не прочитан (мост не отвечает (TimeoutError)), снимок %d симв., sha16 %s, " \
        "возраст 601 с" % (len(TEXT["faq"]), SHA["faq"]) in got[0] and "НЕИЗВЕСТНО" not in got[0], got
    w, _p, _h, _c = draft_at(kn, T0 + MAX_STALE + 1)
    got = know_lines(w)
    assert len(got) == 1 and "faq — не прочитан (мост не отвечает (TimeoutError)), снимок %d симв., sha16 %s, " \
        "возраст 1801 с > предела 1800 с — НЕИЗВЕСТНО, текста в промпте нет" % (len(TEXT["faq"]), SHA["faq"]) \
        in got[0], got
    assert SHA["business_rules"] in got[0], got
    for ln in w.lines:
        no_node_text(ln, "журнал")


def test_journal_never_read_unknown():
    br = Bridge()
    br.down = True
    w, prompt, hand, _c = draft_at(K.Knowledge(br.read_doc), T0)
    assert know_lines(w) == ["знания: business_rules — не прочитан (мост не отвечает (TimeoutError)), снимка нет — "
                             "НЕИЗВЕСТНО; faq — не прочитан (мост не отвечает (TimeoutError)), снимка нет — "
                             "НЕИЗВЕСТНО"], know_lines(w)
    # WADRAFTFIX0310 (п.3): чтение пробовали и оно не удалось — та же причина, что у устаревшего (было: причины нет)
    assert "УЗЕЛ faq: НЕИЗВЕСТНО — не прочитан" in prompt and hand == [STALE], hand


def test_cache_prefix_no_text_when_stale():
    br = Bridge()
    kn = K.Knowledge(br.read_doc)
    w = TM.World(reply=REPLY)
    w.adapter.knowledge, w.adapter.cache = kn, "1h"
    s0, _u0, _ = w.adapter.build(TM.NUM, 0, now=T0)
    assert all(ln in s0[1]["text"] for ln in LINES), s0[1]["text"][:300]
    br.down = True
    s1, u1, info = w.adapter.build(TM.NUM, 0, now=T0 + MAX_STALE + 1)
    no_node_text(s1[0]["text"] + s1[1]["text"] + u1, "кэш")
    assert "УЗЕЛ faq: НЕИЗВЕСТНО: снимок старше 30 мин" in s1[1]["text"], s1[1]["text"][:300]
    assert "TimeoutError" not in s1[1]["text"], s1[1]["text"][:300]                  # причина — не в префиксе
    assert "faq — НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" in u1, u1[:400]
    assert [r["words"] for r in info["code_reasons"]][:1] == [STALE], info["code_reasons"]
    s2, _u2, _ = w.adapter.build(TM.NUM, 0, now=T0 + MAX_STALE + 700)
    assert s1 == s2, "префикс сменился от возраста"


# ═══ ветки правки ═════════════════════════════════════════════════════════════════════════

def test_recovers_after_bridge_back():
    br = Bridge()
    kn = K.Knowledge(br.read_doc)
    kn.refresh(T0)
    br.down = True
    kn.refresh(T0 + MAX_STALE + 1)
    br.down = False
    w, prompt, hand, card = draft_at(kn, T0 + MAX_STALE + 2)
    assert all(ln in prompt for ln in LINES) and "снят 0 мин назад" in prompt and hand == [], hand
    assert know_lines(w)[0].startswith("знания: business_rules — прочитан, "), know_lines(w)


def test_stale_first_with_many_reasons():
    br = Bridge()
    kn = K.Knowledge(br.read_doc)
    kn.refresh(T0)
    br.down = True
    many = "Свободен ли байк? Скидку дадите? Какой депозит? Был штраф."
    _w, _p, hand, card = draft_at(kn, T0 + MAX_STALE + 1, q=many)
    assert hand[0] == STALE and len(hand) >= 4, hand
    assert actions(card["text"])[0] == ACT_STALE, card["text"]


def test_custom_limits_and_followup_line():
    br = Bridge()
    kn = K.Knowledge(br.read_doc, max_age=60, max_stale=100)
    kn.refresh(T0)
    br.down = True
    snap = kn.refresh(T0 + 100)
    assert not K.node_stale(snap["faq"], T0 + 100)
    snap = kn.refresh(T0 + 101)
    assert K.node_stale(snap["faq"], T0 + 101) and "старше 1 мин" in K.node_block(snap["faq"], T0 + 101)
    w = TM.World(reply=REPLY)
    w.adapter.knowledge = kn
    w.adapter.build_followup(TM.NUM, 0, now=T0 + 101)                                  # напоминание — та же строка
    got = know_lines(w)
    assert len(got) == 1 and "возраст 101 с > предела 100 с" in got[0], got
    assert K.word_categories(STALE) == [K.R_STALE] and WM.sha16(TEXT["faq"]) == SHA["faq"]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
