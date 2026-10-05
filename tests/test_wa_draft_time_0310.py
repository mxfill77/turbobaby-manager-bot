#!/usr/bin/env python3
"""Время черновика и напоминания — после ВСЕХ блокирующих чтений (WATIMEFIX0310). Уроки людей (SQLite, ожидание
до 5 с) читаются до последнего снятия времени. По нему одним временем судятся возраст, причина «знания
устарели», строка журнала, блоки знаний и префикс кэша.

Проба Штаба:
- снимок знаний взят в t0, часы адаптера на t0+1799;
- мост лёг, отказы мгновенные;
- ждут только уроки — 2 с, часы → t0+1801;
- итог: «НЕИЗВЕСТНО», причина, в журнале 1801 с — в черновике и напоминании, с выключенным кэшем и с 1h.
Контроль — те же условия без ожидания уроков: 1799 с, текст узлов, причин нет.

Всё на подделках (test_wa_agent_model): модель, мост, часы, Bot API и дверь отправки. Сети нет, модели нет.
Уроки читаются настоящим `_lessons` из базы агента временного мира; ожидание подделано сдвигом часов.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent_knowledge as K  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — адаптер модели на подделках
import test_wa_know_fresh as F  # noqa: E402  — узлы, мост, хелперы знаний

T0 = TM.T0
STALE, ACT_STALE = F.STALE, F.ACT_STALE
LESSON = (7, "Шлем дадим.", "Шлем входит в аренду, второй — по запросу.", "уточнение владельца")


class Call(TM.FakeCall):
    """Подделка модели и для кэша: system — строка или список блоков (у TM.FakeCall — только строка)."""

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.reply, {"model": "fake", "in": len(flat(system) + user) // 4, "out": 20}


def lesson_world(cache=None, wait=2, rows=None):
    """Снимок в t0; часы на t0+1799; мост лёг, отказ мгновенный; уроки ждут `wait` с.
    rows — что вернуть вместо настоящего чтения (None — настоящий `_lessons` по базе агента мира).
    → (мир, часы, мост, часы на входе в уроки)."""
    clk = [T0]
    br = F.Bridge()
    kn = K.Knowledge(br.read_doc)
    kn.refresh(T0)
    br.down, br.reads = True, []
    clk[0] = T0 + 1799
    w = TM.World(reply=F.REPLY)
    ad = w.adapter
    ad.knowledge, ad.clock, ad.cache, ad.lessons_db = kn, (lambda: clk[0]), cache, w.dbpath
    ad.call = w.call = Call(F.REPLY)
    real, seen = ad._lessons, []

    def slow_lessons():
        seen.append(clk[0])
        clk[0] += wait                                    # SQLite ждёт (busy) — единственная задержка вызова
        got = real()
        return got if rows is None else rows

    ad._lessons = slow_lessons
    return w, clk, br, seen


def flat(system):
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


def know_line(w, age, stale=True):
    got = F.know_lines(w)
    assert len(got) == 1, got
    for n in K.NODES:
        want = "%s — не прочитан (мост не отвечает (TimeoutError)), снимок %d симв., sha16 %s, возраст %d с" % (
            n, len(F.TEXT[n]), F.SHA[n], age)
        if stale:
            want += " > предела 1800 с — НЕИЗВЕСТНО, текста в промпте нет"
        assert want in got[0], (want, got)
        assert stale or "предела" not in got[0], got
    return got[0]


def drafted(w):
    w.ask(F.Q)
    d = w.drafts()
    assert len(d) == 1, d
    system, user = w.call.calls[-1]
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    return system, user, hand, cards[-1]


# ═══ проба Штаба: 1799 с + уроки 2 с → 1801 с ════════════════════════════════════════════════════

def test_lessons_wait_draft():
    for cache in (None, "1h"):
        w, clk, br, seen = lesson_world(cache)
        system, user, hand, card = drafted(w)
        assert seen == [T0 + 1799] and clk[0] == T0 + 1801, (cache, seen, clk)
        assert br.reads == ["faq", "business_rules"], (cache, br.reads)            # отказы мгновенные, часы не двигают
        text = flat(system) + "\n" + user
        F.no_node_text(text, "черновик, кэш %s" % cache)
        if cache:
            pre = system[1]["text"]
            for n in K.NODES:
                assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин" % n) in pre, pre[:400]
                assert ("%s — НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" % n) in user, user
            assert "TimeoutError" not in pre, pre[:400]                             # причина сбоя — не в префиксе
        else:
            assert isinstance(system, str), type(system)
            for n in K.NODES:
                assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" % n) in user, n
        assert "НУЖЕН ЧЕЛОВЕК: " + STALE in user and hand == [STALE], (cache, hand)
        assert TM.buttons(card) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)   # «Отправить» есть (WACARDUI0510)
        assert TM.G.W_SEND_HAND in card["text"], card["text"]
        assert F.actions(card["text"]) == [ACT_STALE], card["text"]
        know_line(w, 1801)


def test_lessons_wait_followup():
    for cache in (None, "1h"):
        w, clk, br, seen = lesson_world(cache)
        system, user, _info = w.adapter.build_followup(TM.NUM, 0)
        assert seen == [T0 + 1799] and clk[0] == T0 + 1801, (cache, seen, clk)
        text = flat(system) + "\n" + user
        F.no_node_text(text, "напоминание, кэш %s" % cache)
        for n in K.NODES:
            assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин" % n) in text, (cache, text[-600:])
            assert ("НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)") in user, (cache, user[-600:])
        if cache:
            assert "TimeoutError" not in system[1]["text"], system[1]["text"][:400]
        know_line(w, 1801)


def test_no_wait_control():
    # контроль: уроки без ожидания — 1799 с, текст узлов в промпте, причин нет (граница даётся только ожиданием уроков)
    for cache in (None, "1h"):
        w, clk, _br, _seen = lesson_world(cache, wait=0)
        system, user, hand, card = drafted(w)
        assert clk[0] == T0 + 1799, clk
        text = flat(system) + "\n" + user
        assert all(ln in text for ln in F.LINES), (cache, text[-600:])
        assert hand == [] and TM.buttons(card)[0] == "wa:send:1:1", (cache, hand, TM.buttons(card))
        know_line(w, 1799, stale=False)
        w2, _c, _b, _s = lesson_world(cache, wait=0)
        system2, user2, _i = w2.adapter.build_followup(TM.NUM, 0)
        assert all(ln in flat(system2) + "\n" + user2 for ln in F.LINES), cache
        know_line(w2, 1799, stale=False)


def test_lessons_reach_prompt():
    # уроки, прочитанные раньше времени, доходят до промпта на прежнем месте: после знаний, до истории
    for cache in (None, "1h"):
        w, _clk, _br, seen = lesson_world(cache, rows=[LESSON])
        _system, user, _hand, _card = drafted(w)
        assert len(seen) == 1, seen
        w2, _c, _b, seen2 = lesson_world(cache, rows=[LESSON])
        _s2, user2, _i = w2.adapter.build_followup(TM.NUM, 0)
        assert len(seen2) == 1, seen2
        for u in (user, user2):
            i_know = u.index("ВОЗРАСТ ЗНАНИЙ" if cache else "УЗЕЛ business_rules")
            i_les = u.index("УРОКИ ЛЮДЕЙ")
            i_hist = u.index("ИСТОРИЯ ПЕРЕПИСКИ")
            assert i_know < i_les < i_hist, (cache, i_know, i_les, i_hist)
            assert "№7: было «Шлем дадим.» → стало «Шлем входит в аренду, второй — по запросу.»" in u, u[i_les:i_hist]


def test_lessons_real_read_ok():
    # настоящий `_lessons` по базе агента мира: прочитан без сбоя (строки «уроки не прочитаны» нет)
    w, _clk, _br, seen = lesson_world()
    drafted(w)
    assert len(seen) == 1 and not [ln for ln in w.lines if ln.startswith("уроки не прочитаны")], w.lines[-6:]


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
