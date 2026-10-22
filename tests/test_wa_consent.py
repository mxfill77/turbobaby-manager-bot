#!/usr/bin/env python3
"""A2CONSENT2210 (22.10.2026): producer согласия wa_consent — решение модели (структурное) + сверка кодом привязок к
РЕАЛЬНО отправленному OFFER, входящему клиента, делу и reviewed_upto; сквозь wa_intake_card.prepare (event-режим).
Только синтетика метаданных: ни сети, ни модели, ни отправок, ни данных клиентов."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import wa_consent as C  # noqa: E402
import wa_intake_card as W  # noqa: E402
from test_wa_intake_card import T0, world  # noqa: E402


def setup(case_key="case-A"):
    """Мир A2 + журнал отправленных: OFFER отправлен сообщением 102 (WA-id), клиент согласился сообщением 103."""
    w = world(case_key)
    w["cfg"] = W.Config(validity=W.VALIDITY_EVENT)
    fact = w["offers"][0]["facts"][0]
    fp = C.terms_fingerprint(fact, {"zone": "SYN-District", "price": 0})
    tmp = tempfile.mkdtemp(dir=os.environ.get("A2_SCRATCH") or None)
    j = C.SentOfferJournal(os.path.join(tmp, "sent_offers.json"))
    assert j.record(case_key, W.offer_key(fact), fp, fact["total"], "THB", 102, T0 + 10) is True
    dec = {"decision": "accept", "source_msg_id": 103, "offer_msg_id": 102, "terms_fp": fp, "reviewed_upto": 103,
           "case_key": case_key, "case_version": w["case"]["case_version"]}
    w["case"]["revalidation"] = {"offer_key": W.offer_key(fact), "at": T0 + 55, "source": "offer door"}
    return w, j, dec, fact, fp


class Producer(unittest.TestCase):
    def test_accept_same_offer_flows_into_prepare(self):
        w, j, dec, _f, _fp = setup()
        c = C.consent_from_decision(dec, w["case"], j.of_case("case-A"), w["messages"])
        self.assertEqual((c["decision"], c["reasons"], c["decided_by"]), ("accept", [], C.DECIDED_BY))
        w["consent"] = c
        p = W.prepare(**w)
        self.assertTrue(p.ok, p.reasons)
        self.assertEqual((p.validity["consent_msg_id"], p.validity["offer_msg_id"]), (103, 102))

    def test_question_decline_ambiguous_never_accept(self):
        w, j, dec, _f, _fp = setup()
        for d in ("question", "decline", "ambiguous", "да", None):
            c = C.consent_from_decision(dict(dec, decision=d), w["case"], j.of_case("case-A"), w["messages"])
            self.assertNotEqual(c["decision"], "accept", d)
            w["consent"] = c
            self.assertFalse(W.prepare(**w).ok, d)

    def test_changed_terms_or_other_offer_refused(self):
        w, j, dec, fact, _fp = setup()
        other = C.terms_fingerprint(dict(fact, total=fact["total"] + 700), {"zone": "SYN-District", "price": 0})
        cases = [dict(dec, terms_fp=other),                     # цена изменилась
                 dict(dec, offer_msg_id=777),                    # предложение не отправлялось (черновик)
                 dict(dec, case_key="case-B"),                   # чужое дело
                 dict(dec, case_version=2)]                      # дело сменило версию
        for d in cases:
            self.assertEqual(C.consent_from_decision(d, w["case"], j.of_case("case-A"), w["messages"])["decision"],
                             "ambiguous", d)

    def test_newer_sent_offer_makes_old_consent_stale(self):
        w, j, dec, fact, _fp = setup()
        fp2 = C.terms_fingerprint(dict(fact, date_end="2026-11-09"), {"zone": "SYN-District", "price": 0})
        j.record("case-A", "OFFER-2", fp2, fact["total"] + 1800, "THB", 105, T0 + 52)
        c = C.consent_from_decision(dec, w["case"], j.of_case("case-A"), w["messages"])
        self.assertIn("не на последнее", " ".join(c["reasons"]))

    def test_source_must_be_client_after_send_and_review_covers_last_input(self):
        w, j, dec, _f, _fp = setup()
        self.assertEqual(C.consent_from_decision(dict(dec, source_msg_id=102), w["case"], j.of_case("case-A"),
                                                 w["messages"])["decision"], "ambiguous")      # наше сообщение
        w["messages"][2]["ts"] = T0 + 5                                                     # раньше отправки (T0+10)
        self.assertEqual(C.consent_from_decision(dec, w["case"], j.of_case("case-A"), w["messages"])["decision"],
                         "ambiguous")
        w, j, dec, _f, _fp = setup()
        w["messages"].append({"id": 104, "who": "клиент", "ts": T0 + 56, "text": ""})
        self.assertIn("последний вход", " ".join(
            C.consent_from_decision(dec, w["case"], j.of_case("case-A"), w["messages"])["reasons"]))

    def test_two_clients_journals_do_not_mix(self):
        _wa, j, _d, fact, fp = setup("case-A")
        j.record("case-B", "OFFER-B", fp, fact["total"], "THB", 201, T0 + 10)
        self.assertEqual([r["offer_msg_id"] for r in j.of_case("case-A")], [102])
        self.assertEqual([r["offer_msg_id"] for r in j.of_case("case-B")], [201])

    def test_journal_needs_real_send_id_and_dedups(self):
        _w, j, _d, fact, fp = setup()
        self.assertIsNone(j.record("case-A", "K", fp, 1, "THB", None, T0))       # черновик без WA-id — не пишется
        self.assertIs(j.record("case-A", "K", fp, 1, "THB", 102, T0), True)      # тот же id — без второй строки
        self.assertEqual(len(j.of_case("case-A")), 1)
        self.assertEqual(C.SentOfferJournal(j.path).of_case("case-A")[0]["offer_msg_id"], 102)   # переживает рестарт

    def test_fingerprint_covers_delivery_and_prepay(self):
        _w, _j, _d, fact, fp = setup()
        self.assertNotEqual(fp, C.terms_fingerprint(fact, {"zone": "SYN-Other", "price": 0}))
        self.assertNotEqual(fp, C.terms_fingerprint(fact, {"zone": "SYN-District", "price": 0}, prepay="100%"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
