#!/usr/bin/env python3
"""OFFERSENT2210 (22.10.2026): журнал ОТПРАВЛЕННЫХ предложений — факты offer черновика ждут отправки; в журнал идёт
только цена, названная в УШЕДШЕМ тексте, с WA-id; ручка WA_AGENT_OFFER_SENT (умолчание ВЫКЛ). Синтетика."""
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wa_agent  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_consent as C  # noqa: E402
import wa_offer_sent as OS  # noqa: E402


def fact(total=12600, model="SYN-A", ds="2026-11-01", de="2026-11-08", avail="free"):
    return {"kind": "offer", "model": model, "date_start": ds, "date_end": de, "avail": avail, "total": total,
            "currency": "THB", "door_at": 1.0, "price_outcome": "number"}


def last(*facts, outcome="fact"):
    return {"tools": {"offers": [{"tool": "offer", "outcome": outcome, "facts": list(facts)}]}}


def main():
    bad = 0

    def check(name, ok, got=""):
        nonlocal bad
        bad += not ok
        print(("PASS " if ok else "FAIL ") + name, "" if ok else repr(got)[:300])

    tmp = tempfile.mkdtemp(dir=os.environ.get("A2_SCRATCH") or None)
    j = C.SentOfferJournal(os.path.join(tmp, "sent.json"))
    r = OS.OfferSentRecorder(os.path.join(tmp, "pending.json"), j)
    ck = OS.case_key("SYN-NUM", fact())
    check("черновик: факт запомнен, журнал пуст", r.on_draft(7, "SYN-NUM", last(fact()), 10.0) == 1
          and j.of_case(ck) == [])
    check("отправка без WA-id — ничего", r.on_sent(7, None, "итого 12 600 ฿", 11.0) == 0 and j.of_case(ck) == [])
    check("отправка с WA-id и той же суммой — запись", r.on_sent(7, "wamid.SYN7", "итого 12 600 ฿ за 7 суток", 12.0) == 1
          and [x["offer_msg_id"] for x in j.of_case(ck)] == ["wamid.SYN7"], j.of_case(ck))
    check("повтор отправки того же черновика — без второй записи", r.on_sent(7, "wamid.SYN7", "12 600", 13.0) == 0
          and len(j.of_case(ck)) == 1)
    r.on_draft(8, "SYN-NUM", last(fact(total=9000, ds="2026-12-01", de="2026-12-06")), 20.0)
    check("сотрудник поправил цену в тексте — в журнал не идёт", r.on_sent(8, "wamid.SYN8", "итого 9 500 ฿", 21.0) == 0)
    check("занято / не факт / чужая валюта — не ждёт", r.on_draft(9, "SYN-NUM", last(fact(avail="busy")), 30.0) == 0
          and r.on_draft(10, "SYN-NUM", last(fact(), outcome="unknown"), 30.0) == 0
          and r.on_draft(11, "SYN-NUM", {"tools": {"offers": [{"outcome": "fact", "facts": [dict(fact(),
                                                                                                  currency="USD")]}]}},
                         30.0) == 0)
    check("ключ дела — номер+модель+период", OS.case_key("N", fact()) != OS.case_key("N", fact(ds="2026-11-02")))
    check("переживает рестарт", C.SentOfferJournal(j.path).of_case(ck)[0]["offer_msg_id"] == "wamid.SYN7")

    core = types.SimpleNamespace(offer_sent=None)
    check("ручки нет — ни регистратора, ни строки", S.offer_sent_of({}, core, os.path.join(tmp, "a.db")) == (None, None)
          and core.offer_sent is None)
    ok, words = S.offer_sent_of({S.F_OFFER_SENT: "1"}, core, os.path.join(tmp, "a.db"))
    check("ручка — регистратор у ядра", ok is True and isinstance(core.offer_sent, OS.OfferSentRecorder)
          and words.startswith("вкл"), (ok, words))

    lines = []
    boom = types.SimpleNamespace(offer_sent=types.SimpleNamespace(on_sent=lambda *a: 1 / 0), log=lines.append)
    wa_agent.Core._offer_hook(boom, "on_sent", 1, "w", "t", 0.0)
    check("сбой журнала не роняет ядро — строка журнала", lines and "сбой on_sent (ZeroDivisionError)" in lines[0], lines)
    check("по умолчанию у ядра регистратора нет", "self.offer_sent = None" in open(wa_agent.__file__, encoding="utf-8").read())
    print("ИТОГ %d/12" % (12 - bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
