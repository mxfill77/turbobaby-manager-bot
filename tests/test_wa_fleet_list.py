#!/usr/bin/env python3
"""FLEETLIST2210 (22.10.2026, Codex TB-AGENT-CRITERIA-2210-OWNER-REVIEW): отказ offer «модели нет в парке» при ручке
WA_AGENT_FLEET_LIST (служба выставляет wa_offer_tool.FLEET_LIST_ON) несёт перечень моделей текущего снимка парка; без ручки — текст прежний байт-в-байт. Синтетика."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wa_offer_tool as O  # noqa: E402

BIKES = [{"name": "PCX 160 SYN1"}, {"name": "PCX 160 SYN2"}, {"name": "NMAX 155 SYN3"}, {"name": "XADV 750 SYN4"}]


def main():
    bad = 0

    def check(name, ok, got=""):
        nonlocal bad
        bad += not ok
        print(("PASS " if ok else "FAIL ") + name, "" if ok else repr(got)[:300])

    O.FLEET_LIST_ON = False
    off = O.model_of("Vespa 150", BIKES)
    check("ручки нет — отказ прежний", off[:2] == (None, "fleet") and off[2] == O.W_FLEET % "Vespa 150", off)
    O.FLEET_LIST_ON = True                     # так её выставляет wa_agent_svc.offer_of при ручке WA_AGENT_FLEET_LIST=1
    on = O.model_of("Vespa 150", BIKES)
    check("ручка — отказ с перечнем парка", on[1] == "fleet" and on[2].startswith(O.W_FLEET % "Vespa 150")
          and "в парке сейчас:" in on[2] and "только offer" in on[2], on)
    names = sorted({O.M.B.model_key(b["name"]) for b in BIKES})
    check("перечень — модели снимка, без дублей юнитов", all(n in on[2] for n in names)
          and on[2].count(names[0]) == 1, (names, on[2]))
    check("модель из парка — как прежде", O.model_of("PCX 160", BIKES)[1] is None)
    check("пустой парк — без хвоста", O.fleet_tail([]) == "")
    check("потолок длины", len(O.fleet_tail([{"name": "M%03d X" % i} for i in range(300)])) <= O.FLEET_LIST_MAX)
    # сквозь цикл сверки (стенд test_wa_offer_tool): «какие модели есть» — offer с пустой моделью без дат
    sys.path.insert(0, HERE)
    import test_wa_offer_tool as TO
    s = TO.Script(TO.offer({"model": ""}), TO.final("В парке сейчас PCX 160, NMAX 155."))
    a, door = TO.adapter(s, question="какие модели есть?")
    a.draft(TO.NUMBER, 5)
    r = TO.offers(a)[0]
    check("сквозь сверку: перечень парка без дат, двери цены нет, не факт",
          "в парке сейчас:" in r["reason"] and "PCX 160" in r["reason"] and door.calls == []
          and r["outcome"] != TO.T.FACT and O.FLEET_BLOCK in s.seen[0], (r, door.calls))
    O.FLEET_LIST_ON = False
    s0 = TO.Script(TO.offer({"model": ""}), TO.final("x"))
    a0, _d0 = TO.adapter(s0, question="какие модели есть?")
    a0.draft(TO.NUMBER, 5)
    check("ручки нет — пустая модель даёт прежний отказ, блок прежний",
          "в парке сейчас" not in TO.offers(a0)[0]["reason"] and O.FLEET_BLOCK not in s0.seen[0], TO.offers(a0)[0])
    print("ИТОГ %d/8" % (8 - bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
