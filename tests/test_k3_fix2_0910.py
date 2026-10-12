#!/usr/bin/env python3
"""K3-FIX шаг 2 (09.10.2026, поручение TB-K3-TARGETED-FIXES-0910) — регрессия находок стенда К3:
F1 (на карточке нет опоры черновика: источников, времени чтения, версий фактов сверки — K02 D5, K06 D7);
N1 (нажавшему и на карточку уходил внутренний код «sent/unsure/not_sent» вместо слов — K02, K07, K08, K10, K11);
K17 (TB-K3-REAL-GAPS-0910 п.4, judge_cases §7: рестарт посреди двери ТЕКСТА без PDF — карточка оставалась с живой
кнопкой «Отправить», исход «неизвестно» ложился только следующим нажатием).
Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на f2f7295 и на коммите шага 1 (76eb9b1) тесты F1/N1/K17 падают, на ремонте
проходят; тест с пометкой КОНТРОЛЬ — зелёный на всех трёх (прежнее поведение, которое ремонт не задел).

Всё на подделках (`test_wa_attach_svc.World`: Bot API, дверь провайдера, модель с итогом сверки — подделки): сети нет,
модель, мост, Telegram, WhatsApp не зовутся."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.append(HERE)

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import test_wa_attach_svc as AS  # noqa: E402
import test_k3_fix_0910 as F1S  # noqa: E402  (шаг 1: мир с крючками в двери и второй экземпляр службы)

UNK = "исход неизвестен — не повторять, проверить переписку"      # слово N2 шага 1 — то же для N1 (литералом: на
#                                                                     f2f7295 константы нет, набор обязан стартовать)
CODES = re.compile(r"(?<![\w.])(sent|unsure|not_sent|sending|claimed|pending)(?![\w.])")
SRC = {"rental": "снимок броней (лист «клиенты»)", "cash": "касса Bot Data «транзакции» (tx_find)",
       "contract": "реестр подписей TB e-Sign (contract_find)", "contract_pdf": "подписанный PDF (contract_pdf)"}
_TOOLS_OUT = AS.tools_out                      # исходный итог сверки набора службы (подмена — только на время теста)


def _live_like(pdf=True):
    """Итог сверки в форме живого кода: у ответа источник (`source`), время чтения (`at`, разные минуты), поле `version`
    с заполнителями, которые версией источника НЕ являются (у договора — `signed_at`), и чужое поле подделки моста."""
    out = _TOOLS_OUT()
    out["results"] = [r for r in out["results"] if pdf or r["tool"] != "contract_pdf"]
    for i, r in enumerate(out["results"]):
        r["source"] = SRC[r["tool"]]
        r["at"] = AS.T0 + 40 + 70 * i
        r["req"] = "%s #%d" % (r["tool"], i)
    out["results"][1]["version"] = AS.SIGNED
    out["results"][1]["stand_meta"] = {"version": "K3-registry-v1"}
    return out


def _with_tools(fn):
    old = AS.tools_out
    AS.tools_out = fn
    return old


def _cards(w):
    return [p["text"] for p in w.http.of("sendMessage")]


def _card_words(w):
    return [e["text"].rsplit("\n— ", 1)[-1] for e in w.edits() if "\n— " in e["text"]]


def _no_codes(texts):
    bad = [t for t in texts if CODES.search(t)]
    assert not bad, "внутренний код состояния в словах сотруднику: %s" % bad


# ═══ F1: опора черновика на карточке ══════════════════════════════════════════════════════════════════

def test_f1_card_sources_time_version():
    """K02/K06: карточка называет КАЖДЫЙ факт сверки — источник, время ЧТЕНИЯ, версию; версии ни одна дверь не отдаёт —
    «неизвестна»; `signed_at` договора и поле подделки моста версией не стали."""
    live = _live_like()
    old = _with_tools(lambda: _live_like())
    try:
        w = AS.World(AS.ON)
        w.ready()
    finally:
        AS.tools_out = old
    card = "\n".join(_cards(w))
    for r in live["results"]:
        assert r["source"] in card, "источника «%s» нет на карточке" % r["source"]
        assert "прочитано %s" % A.hm_phuket(r["at"]) in card, (r["tool"], A.hm_phuket(r["at"]))
    assert card.count("версия: неизвестна") == len(live["results"]), card
    assert "версия: %s" % AS.SIGNED not in card and "K3-registry" not in card, card


def test_f1_version_only_from_source():
    """Версия на карточке — ТОЛЬКО поле «версия, выданная источником» (`source_version`, F2_CONTRACT §1.1); заполнители
    `version` («856 симв.», signed_at) и `stand_meta` — «неизвестна»."""
    r1 = {"tool": "rules", "outcome": T.FACT, "source": "мозг business_rules", "at": AS.T0, "version": "856 симв.",
          "stand_meta": {"version": "K3-rules-v1"}, "req": "rules []", "facts": [{"kind": "rules", "len": 856}]}
    r2 = {"tool": "contract_pdf", "outcome": T.FACT, "source": SRC["contract_pdf"], "at": AS.T0 + 60, "version": "",
          "source_version": "drive-rev-7", "req": "pdf", "facts": [{"kind": "pdf", "id": "F41"}]}
    got = X.opora_of({"state": "done", "results": [r1, r2]})
    lines = got.split("\n")
    assert [ln for ln in lines if "мозг business_rules" in ln][0].endswith("версия: неизвестна"), got
    assert [ln for ln in lines if "contract_pdf" in ln][0].endswith("версия: drive-rev-7"), got
    assert "856" not in got and "K3-rules" not in got, got


def test_f1_cap_and_dropped_named():
    """Длина — с потолком; усечение и факты, снятые опорой судьи, названы числом, а не спрятаны."""
    many = [{"tool": "cash", "outcome": T.FACT, "source": "касса %d" % i, "at": AS.T0 + i, "req": "cash %d" % i,
             "facts": [{"kind": "cash", "row": i, "msg_id": "m%d" % i, "amount": 1, "currency": "THB"}]}
            for i in range(9)]
    got = X.opora_of({"state": "done", "results": many})
    assert got.count("\n• cash · ") == X.OPORA_ROWS and "не показано строк опоры: %d" % (9 - X.OPORA_ROWS) in got, got
    assert len(got) <= X.OPORA_CHARS + 300, len(got)
    gone = [{"tool": "contract", "outcome": T.FACT, "source": SRC["contract"], "at": AS.T0, "req": "c",
             "facts": [{"kind": "contract", "row": 1, "doc_id": "D1"}]},
            {"tool": "contract", "outcome": T.REFUSED, "source": SRC["contract"], "at": AS.T0 + 5, "req": "c",
             "facts": []},
            {"tool": "rental", "outcome": T.FACT, "source": SRC["rental"], "at": AS.T0 + 9, "req": "r",
             "facts": [{"kind": "rental", "booking_id": "B7"}]}]
    got = X.opora_of({"state": "done", "results": gone})
    assert SRC["rental"] in got and "• contract" not in got and "не в опоре судьи" in got and got.endswith(": 1"), got


def test_f1_no_bridge_calls_stored_with_draft():
    """Опора берётся из уже прочитанного снимка сверки: ни одного обращения к дверям моста за карточку; лежит со строкой
    вложения черновика и та же — на карточке."""
    old = _with_tools(lambda: _live_like())
    try:
        w = AS.World(AS.ON)
        w.ready()
    finally:
        AS.tools_out = old
    assert w.model.find.calls == [] and w.model.fetch.calls == [], (w.model.find.calls, w.model.fetch.calls)
    stored = w.q("SELECT opora FROM attach WHERE draft_id=1")[0][0]
    assert stored and stored in _cards(w)[-1], (stored, _cards(w)[-1])


def test_f1_control_flag_off_card_unchanged():
    """КОНТРОЛЬ (зелёный и до ремонта): флаг вложений выкл — прежнее ядро, на карточке опоры нет."""
    w = AS.World(AS.BASE)
    w.ready()
    assert type(w.core) is A.Core and "🧾" not in "\n".join(_cards(w)), _cards(w)


# ═══ N1: состояния частей — словами, не кодами ═══════════════════════════════════════════════════════

def test_n1_text_only_sent_words():
    """K07/K08/K10/K11: текст без PDF ушёл — нажавшему «текст: ушёл», на карточке «текст: ушёл (wamid …)», не «sent»."""
    old = _with_tools(lambda: _live_like(pdf=False))
    try:
        w = AS.World(AS.ON)
        w.ready()
        w.press("wa:send:1:1")
    finally:
        AS.tools_out = old
    assert w.answers()[-1] == "текст: ушёл", w.answers()
    words = _card_words(w)
    assert words and words[-1].startswith("текст: ушёл (wamid …wamid.T1) — Дарья"), words
    _no_codes(w.answers() + words)


def test_n1_text_only_unsure_words_second_press():
    """K02: исход двери неизвестен — нажавшему и на карточке «исход неизвестен — не повторять, проверить переписку»;
    второе нажатие — «уже решено … исход неизвестен …», повтора нет; кода «unsure» сотрудник не видит."""
    old = _with_tools(lambda: _live_like(pdf=False))
    try:
        w = AS.World(AS.ON, text="unknown")
        w.ready()
        w.press("wa:send:1:1")
        w.press("wa:send:1:1")
    finally:
        AS.tools_out = old
    a = w.answers()
    assert a[0] == "текст: " + UNK, a
    assert a[1].startswith("уже решено") and UNK in a[1], a
    assert _card_words(w) and _card_words(w)[-1].startswith("текст: " + UNK + " — Дарья"), _card_words(w)
    assert len(w.sends) == 1, w.sends
    _no_codes(a + _card_words(w))


class Why(AS.World):
    def send(self, to, text, db_path=None):
        out = AS.World.send(self, to, text, db_path)
        if out["outcome"] == "not_sent":
            out["reason"] = "окно 24 ч закрыто — напишите клиенту с телефона"
        return out


def test_n1_text_only_not_sent_reason():
    """Текст не ушёл — «не ушёл: причина» словами двери, не «not_sent»."""
    old = _with_tools(lambda: _live_like(pdf=False))
    try:
        w = Why(AS.ON, text="not_sent")
        w.ready()
        w.press("wa:send:1:1")
    finally:
        AS.tools_out = old
    assert w.answers()[-1] == "текст: не ушёл: окно 24 ч закрыто — напишите клиенту с телефона", w.answers()
    _no_codes(w.answers() + _card_words(w))


def test_n1_two_part_unsure_words_and_wamids():
    """Две части: PDF неизвестен — слово N2 «исход неизвестен — не повторять, проверить», а не «неизвестно»; на карточке
    у ушедшего текста — его wamid; кнопки PDF прежние."""
    w = AS.World(AS.ON, media="unknown")
    w.ready()
    w.press("wa:send:1:1")
    assert w.answers()[-1] == "текст: ушёл · PDF: " + UNK, w.answers()
    words = _card_words(w)
    assert words and words[-1].startswith("текст: ушёл (wamid …wamid.T1) · PDF: " + UNK), words
    assert AS.kb_data(w.edits()[-1]) == ["wa:pdf:1:1", "wa:pdf_risk:1:1"], w.edits()[-1]


def test_n1_vocabulary_no_codes():
    """Одно слово на состояние: sending/sent/unsure/not_sent → «отправляется» / «ушёл (wamid …)» / «исход неизвестен — не
    повторять, проверить» / «не ушёл: причина»; часть посреди чужого захода (N2) называется словом, а не кодом."""
    wm = "wamid.HBgLNjY4MTIzNDU2NzgVAgARGBI"
    assert X.state_word(A.SENDING) == "отправляется"
    assert X.state_word(A.SENT, wamid=wm) == "ушёл (wamid …%s)" % wm[-8:] and X.state_word(A.SENT) == "ушёл"
    assert X.state_word(A.UNSURE) == UNK
    assert X.state_word(A.NOT_SENT, "сервер отказал 400", pdf=True) == "не ушёл: сервер отказал 400"
    got = X.reread_words(A.SENDING, X.P_CLAIMED)
    assert "отправляется" in got and "(sending)" not in got and "(claimed)" not in got, got
    _no_codes([got] + [X.parts_words(s, p, "x", text_reason="y") for s in (A.SENT, A.NOT_SENT, A.UNSURE, A.SENDING)
                       for p in (None, A.SENT, A.NOT_SENT, A.UNSURE, A.SENDING)])


def test_n1_press_pdf_already_decided_word():
    """«Дослать PDF» по кнопке прежней попытки после досылки — «уже решено: PDF — …, попытка 2 — ушёл», а не «— sent»."""
    w = AS.World(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"
    w.press("wa:pdf:1:1")
    w.press("wa:pdf:1:2")
    last = w.answers()[-1]
    assert last.startswith("уже решено: PDF") and last.endswith("попытка 2 — ушёл"), w.answers()
    _no_codes(w.answers())


def test_n1_text_only_second_instance_card_not_overwritten():
    """Р7 без PDF: второй экземпляр стартует посреди двери ТЕКСТА (исход старта — на карточку); поздний ответ первого
    экземпляра — словами по базе («исход неизвестен», «опоздал»), карточку «текст: ушёл» НЕ перетирает; повтора нет."""
    old = _with_tools(lambda: _live_like(pdf=False))
    try:
        w = F1S.HW(AS.ON)
        w.ready()
        w.hooks["send"] = lambda: F1S._second(w)
        w.press("wa:send:1:1")
        w.core.tick(AS.T0 + 400)
    finally:
        AS.tools_out = old
    ans = w.answers()[-1]
    assert ans.startswith("текст: " + UNK) and "опоздал" in ans, ans
    words = _card_words(w)
    assert words and not [x for x in words if x.startswith("текст: ушёл")], words
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)
    _no_codes([ans] + words)


# ═══ K17: рестарт посреди двери текста БЕЗ PDF ════════════════════════════════════════════════════════

def test_k17_text_only_restart_card_unknown():
    """judge_cases §7 (K17 real): процесс умер посреди двери текста, PDF нет — старт переводит текст в «неизвестно» и
    кладёт исход на карточку вместо живой кнопки «Отправить»; нажатие после рестарта — «уже решено … исход неизвестен»,
    второй отправки нет. Предотвращённый повтор дублем НЕ назван."""
    old = _with_tools(lambda: _live_like(pdf=False))
    try:
        w = AS.World(AS.ON, text="crash")
        w.ready()
        try:
            w.press("wa:send:1:1")
        except AS.Crash:
            pass
        w.text_out = "sent"
        w.restart()
        assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.UNSURE,)]
        w.core.tick(AS.T0 + 400)
        card = w.edits()[-1] if w.edits() else {"text": ""}
        words = card["text"].rsplit("\n— ", 1)[-1]
        assert words.startswith("текст: " + UNK + " — рестарт службы"), card["text"][-200:]
        assert AS.kb_data(card) == [], "на карточке осталась кнопка: %s" % AS.kb_data(card)
        w.press("wa:send:1:1")
    finally:
        AS.tools_out = old
    assert w.answers()[-1].startswith("уже решено") and UNK in w.answers()[-1], w.answers()
    assert len(w.sends) == 1, "после рестарта текст ушёл второй раз: %s" % w.sends
    said = [card["text"]] + w.answers() + [ln for ln in w.lines if "старт" in ln]
    assert not [s for s in said if "дубл" in s], said
    _no_codes(w.answers() + [words])


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
