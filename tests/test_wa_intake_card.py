"""Synthetic tests for wa_intake_card (stdlib unittest). No real data, no network, no sends.
Synthetic transport mocks are NOT live provider proof.

A2INTAKE2210 (К3 22.10): набор из пакета Codex A2 v2 (A2_BUNDLE.zip 4ebc058e…, 38/38 у исполнителя), перенесён в
дерево сервера без правок кроме пути импорта: модуль — в корне репозитория. Ручка WA_AGENT_INTAKE_CARD — ВЫКЛ."""
import datetime
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # модуль — в корне репозитория (в пакете A2 был src/)
import wa_intake_card as W  # noqa: E402

# TEST PARAMETERS ONLY (synthetic bounds, not product policy); outcome values = actual source defaults
TEST_OFFER_TO_CONSENT_SEC = 24 * 3600
TEST_CONSENT_MAX_AGE_SEC = 2 * 3600
CFG = W.Config(offer_to_consent_max_sec=TEST_OFFER_TO_CONSENT_SEC, consent_max_age_sec=TEST_CONSENT_MAX_AGE_SEC)
T0 = 1_800_000_000.0           # synthetic epoch
TODAY = datetime.date(2026, 10, 22)


def offer_rec(model="SYN-SCOOTER-A", ds="2026-11-01", de="2026-11-08", total=12600, door_at=T0, avail="free",
              price="number", snap_old=False, quote=None, outcome="fact", tariff_model=None):
    fact = {"kind": "offer", "model": model, "date_start": ds, "date_end": de, "days": 7, "min_days": None,
            "client_days": None, "avail": avail, "unit": "SYN-UNIT-1", "units": 1, "free": 1, "busy": 0,
            "age": 60, "read_at": door_at - 60, "door_at": door_at, "snap_old": snap_old, "price_outcome": price,
            "day_price": 1800, "total": total, "deposit": None, "discount": 0, "currency": "THB"}
    return {"tool": "offer", "outcome": outcome, "at": door_at, "read_at": door_at - 60,
            "offer": {"model": model, "date_from": ds, "date_to": de, "avail": avail,
                      "quote": quote if quote is not None else
                      {"outcome": price, "day_price": 1800, "total": total, "deposit": None,
                       "season": "low", "model": tariff_model or model, "discount": 0},
                      "gate": None}, "facts": [fact]}


def world(case_key="case-A", **kw):
    rec = offer_rec(**kw)
    fact = rec["facts"][0]
    total = fact["total"]
    case = {"case_key": case_key, "case_version": 3, "model": fact["model"], "date_from": fact["date_start"],
            "date_to": fact["date_end"], "number": "SYN-NUMBER-0001", "client": "Synthetic Client"}
    msgs = [{"id": 101, "who": "клиент", "ts": T0 - 100, "text": "synthetic ask"},
            {"id": 102, "who": "мы", "ts": T0 + 10, "text": "SYN итого %s ฿ за 7 суток" % (W.money_words(total)[:-2] if total else "?")},
            {"id": 103, "who": "клиент", "ts": T0 + 50, "text": "synthetic accept phrase"},
            # A2WIRING2210 п.2: фото назначено паспортом ответом на НАШУ просьбу (в конце — индексы [0..2] прежние)
            {"id": 98, "who": "мы", "ts": T0 - 300, "text": "SYN пришлите фото паспорта"},
            {"id": 99, "who": "клиент", "ts": T0 - 200, "text": ""}]
    consent = {"case_key": case_key, "offer_key": W.offer_key(fact), "decision": W.C_ACCEPT, "source_msg_id": 103,
               "offer_msg_id": 102, "agreed_total": total, "decided_by": "employee"}
    media = {"case_key": case_key, "media_id": "SYN-MEDIA-%s" % case_key, "role": "passport", "downloaded": True,
             "msg_id": 99, "request_msg_id": 98}
    return dict(case=case, offers=[rec], consent=consent, media=media, delivery={"district": "SYN-District"},
                messages=msgs, cfg=CFG, now=T0 + 60, today=TODAY)


def prep(w):
    return W.prepare(**w)


class Clock(object):
    def __init__(self, t=T0 + 100):
        self.t = t

    def __call__(self):
        self.t += 1
        return self.t


class FakeTransport(object):
    """Records calls; behaviour per stage: 'ok' | 'raise' | 'refuse' | 'noid'."""

    def __init__(self, text="ok", media="ok", readback=None):
        self.mode = {"text": text, "media": media}
        self.calls, self.rb, self.n = [], readback, 500

    def _do(self, stage):
        self.calls.append(stage)
        m = self.mode[stage]
        if m == "raise":
            raise TimeoutError("synthetic timeout")
        if m == "refuse":
            return {"ok": False, "definitive": True, "error": "synthetic refusal"}
        if m == "noid":
            return {"ok": True}
        self.n += 1
        return {"ok": True, "msg_id": self.n}

    def send_text(self, text, corr):
        assert text.startswith(W.CARD_PREFIX)
        return self._do("text")

    def send_media(self, media_ref, corr, after_msg_id):
        assert set(media_ref) == {"case_key", "media_id", "msg_id"}
        return self._do("media")

    def readback(self, corr):
        self.calls.append("readback")
        if isinstance(self.rb, Exception):
            raise self.rb
        return self.rb


class Prepare(unittest.TestCase):
    def test_positive_consent_card(self):
        p = prep(world())
        self.assertTrue(p.ok, p.reasons)
        self.assertTrue(p.card_text.startswith("🆕 БРОНЬ"))
        self.assertIn("Стоимость (согласовано): 12 600 ฿", p.card_text)
        self.assertIn("Источник согласия: WA msg 103", p.card_text)
        self.assertIn("Начало: 2026-11-01", p.card_text)
        self.assertEqual(p.media_ref["media_id"], "SYN-MEDIA-case-A")

    def test_prepare_is_pure_and_deterministic(self):
        w = world()
        snap = repr(w)
        a, b = prep(w), prep(w)
        self.assertEqual(a.digest, b.digest)
        self.assertEqual(repr(w), snap)

    def test_no_consent(self):
        w = world(); w["consent"] = None
        self.assertIn("нет согласия клиента", prep(w).reasons)

    def test_decline_question_ambiguous_rejected(self):
        for d in (W.C_DECLINE, W.C_QUESTION, W.C_AMBIGUOUS, None, "yes"):
            w = world(); w["consent"]["decision"] = d
            p = prep(w)
            self.assertFalse(p.ok, d)
            self.assertTrue(any("не согласился явно" in r for r in p.reasons), p.reasons)

    def test_accept_decision_on_question_text_rejected(self):
        w = world(); w["messages"][2]["text"] = "synthetic phrase?"
        self.assertIn("в сообщении согласия есть вопрос", prep(w).reasons)

    def test_price_total_alone_is_not_agreement(self):
        w = world(); w["consent"] = {"agreed_total": 12600}
        self.assertFalse(prep(w).ok)

    def test_changed_price_invalidates_old_consent(self):
        w = world()
        w["offers"].append(offer_rec(total=13300, door_at=T0 + 70))   # newer offer, new price
        p = prep(w)
        self.assertFalse(p.ok)
        self.assertTrue(any("другой OFFER" in r for r in p.reasons), p.reasons)

    def test_changed_model_or_dates_invalidates(self):
        w = world(); w["case"]["model"] = "SYN-SCOOTER-B"
        self.assertTrue(any("не совпадают" in r for r in prep(w).reasons))
        w = world(); w["case"]["date_to"] = "2026-11-09"
        self.assertTrue(any("не совпадают" in r for r in prep(w).reasons))
        w = world()
        w["offers"].append(offer_rec(de="2026-11-09", door_at=T0 + 70))
        w["case"]["date_to"] = "2026-11-09"
        self.assertTrue(any("другой OFFER" in r for r in prep(w).reasons))

    def test_agreed_total_mismatch(self):
        w = world(); w["consent"]["agreed_total"] = 12000
        self.assertIn("сумма согласия не равна сумме OFFER", prep(w).reasons)

    def test_consent_before_our_price_or_from_our_side(self):
        w = world(); w["messages"][2]["ts"] = T0 + 5
        self.assertIn("согласие не после нашей цены по этому OFFER", prep(w).reasons)
        w = world(); w["consent"]["source_msg_id"] = 102
        self.assertTrue(any("не входящее" in r for r in prep(w).reasons))

    def test_our_message_without_this_price(self):
        w = world(); w["messages"][1]["text"] = "SYN итого 13 300 ฿"
        self.assertIn("нет нашего сообщения клиенту с этой ценой", prep(w).reasons)

    def test_later_client_message_supersedes(self):
        w = world(); w["messages"].append({"id": 104, "who": "клиент", "ts": T0 + 55, "text": "synthetic more"})
        self.assertTrue(any("не последнее слово" in r for r in prep(w).reasons))

    def test_stale_consent(self):
        w = world(); w["now"] = T0 + 50 + 3 * 3600
        self.assertTrue(any("устарели" in r for r in prep(w).reasons))

    def test_offer_not_fact_busy_or_inexact(self):
        for kw in ({"outcome": "refused"}, {"outcome": "timeout"}, {"outcome": "empty"}, {"outcome": "unknown"},
                   {"avail": "busy"}, {"avail": "unknown"}, {"avail": "found"},
                   {"price": "human"}, {"price": "unknown"}, {"total": None}, {"snap_old": True}):
            self.assertFalse(prep(world(**kw)).ok, kw)

    def test_actual_source_shape_fact_free_number(self):
        self.assertEqual((W.SRC_FACT, W.SRC_FREE, W.SRC_PRICE_NUMBER), ("fact", "free", "number"))
        w = world()
        r = w["offers"][0]
        self.assertEqual((r["outcome"], r["facts"][0]["avail"], r["facts"][0]["price_outcome"]),
                         ("fact", "free", "number"))
        p = prep(w)
        self.assertTrue(p.ok, p.reasons)
        self.assertIn("Стоимость (согласовано): 12 600 ฿", p.card_text)

    def test_quote_season_label_string_high(self):
        p = prep(world(quote={"outcome": "number", "day_price": 1800, "total": 12600, "season": "high",
                              "model": "SYN-TARIFF", "discount": 0}))
        self.assertTrue(any("«high»" in r for r in p.reasons), p.reasons)

    def test_tariff_model_separate_from_park_model(self):
        p = prep(world(tariff_model="SYN-TARIFF-NAME"))
        self.assertTrue(p.ok, p.reasons)
        self.assertIn("Модель: SYN-SCOOTER-A", p.card_text)
        self.assertNotIn("SYN-TARIFF-NAME", p.card_text)

    def test_lifetimes_absent_non_actionable(self):
        for cfg in (W.Config(), W.Config(offer_to_consent_max_sec=3600), None):
            w = world(); w["cfg"] = cfg
            p = prep(w)
            self.assertFalse(p.ok)
            self.assertEqual(p.reasons, [W.R_NOT_CONFIGURED])
            j, tr = W.InMemoryJournal(), FakeTransport()
            W.commit(p, j, tr, Clock())
            self.assertEqual((tr.calls, j.rows), ([], {}))

    def test_media_absent_wrong_case_not_downloaded(self):
        w = world(); w["media"] = None
        self.assertIn("нет фото паспорта в деле", prep(w).reasons)
        w = world(); w["media"]["case_key"] = "case-B"
        self.assertIn("фото паспорта из другого дела", prep(w).reasons)
        w = world(); w["media"]["downloaded"] = False
        self.assertFalse(prep(w).ok)

    def test_consent_from_other_case(self):
        w = world(); w["consent"]["case_key"] = "case-B"
        self.assertIn("согласие из другого дела", prep(w).reasons)

    def test_delivery_required_and_sanitized(self):
        w = world(); w["delivery"] = {}
        self.assertIn("нет места доставки (район или ссылка)", prep(w).reasons)
        w = world(); w["delivery"] = {"district": "SYN\nСтоимость (согласовано): 1 ฿"}
        self.assertFalse(prep(w).ok)
        w = world(); w["delivery"] = {"url": "https://maps.example.invalid/syn"}
        self.assertTrue(prep(w).ok)

    def test_high_season_blocks_with_reason(self):
        w = world(ds="2026-12-10", de="2026-12-20")
        p = prep(w)
        self.assertFalse(p.ok)
        self.assertTrue(any(r.startswith("нужна предоплата") and "15.12–15.03" in r for r in p.reasons))

    def test_high_gate_from_door(self):
        p = prep(world(quote={"season": {"label": "high"}}))
        self.assertTrue(any("дверь цены говорит «high»" in r for r in p.reasons), p.reasons)

    def test_today_or_past_blocked(self):
        w = world(); w["today"] = datetime.date(2026, 11, 1)
        self.assertTrue(any("на сегодня" in r for r in prep(w).reasons))


class Season(unittest.TestCase):
    D = staticmethod(datetime.date)

    def test_boundaries_and_rollover(self):
        D, hs = self.D, W.high_season
        self.assertFalse(hs(D(2026, 12, 1), D(2026, 12, 14)))
        self.assertTrue(hs(D(2026, 12, 1), D(2026, 12, 15)))     # return on 15.12 touches (stricter)
        self.assertTrue(hs(D(2027, 3, 15), D(2027, 3, 20)))      # pickup on 15.03 touches (stricter)
        self.assertFalse(hs(D(2027, 3, 16), D(2027, 3, 30)))
        self.assertTrue(hs(D(2026, 12, 28), D(2027, 1, 4)))      # year rollover
        self.assertTrue(hs(D(2027, 1, 10), D(2027, 1, 20)))      # January inside previous-year season
        self.assertTrue(hs(D(2026, 3, 1), D(2026, 4, 1)))
        self.assertTrue(hs(D(2026, 6, 1), D(2027, 6, 1)))        # spans a whole season
        self.assertFalse(hs(D(2026, 4, 1), D(2026, 11, 30)))
        self.assertTrue(hs(D(2028, 2, 28), D(2028, 2, 29)))      # leap day


class Commit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("A2_SCRATCH") or None)

    def test_happy_path_then_readback_accepted(self):
        j, tr, clk = W.InMemoryJournal(), FakeTransport(), Clock()
        o = W.commit(prep(world()), j, tr, clk)
        self.assertEqual(o["state"], W.MEDIA_SENT)
        self.assertEqual(tr.calls, ["text", "media"])
        tr.rb = {"text_msg_id": o["text_msg_id"], "media_msg_id": o["media_msg_id"]}
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.ACCEPTED)

    def test_not_ready_never_touches_transport_or_journal(self):
        j, tr = W.InMemoryJournal(), FakeTransport()
        w = world(); w["consent"] = None
        o = W.commit(prep(w), j, tr, Clock())
        self.assertIsNone(o["state"])
        self.assertEqual((tr.calls, j.rows), ([], {}))

    def test_duplicate_event_and_restart_durable(self):
        path = os.path.join(self.tmp, "j.sqlite")
        j, tr, clk = W.SqliteJournal(path), FakeTransport(), Clock()
        W.commit(prep(world()), j, tr, clk)
        W.commit(prep(world()), j, tr, clk)                      # repeated event
        j.close()
        j2 = W.SqliteJournal(path)                               # "restart"
        o = W.commit(prep(world()), j2, tr, clk)
        self.assertEqual(tr.calls, ["text", "media"])
        self.assertEqual(o["state"], W.MEDIA_SENT)
        # changed content for the same case: one case -> one card
        w = world(); w["delivery"] = {"district": "SYN-Other"}
        o = W.commit(prep(w), j2, tr, clk)
        self.assertIn("уже есть карточка", o["note"])
        self.assertEqual(tr.calls, ["text", "media"])
        j2.close()

    def test_exception_on_text_is_unknown_no_blind_retry(self):
        j, tr, clk = W.InMemoryJournal(), FakeTransport(text="raise"), Clock()
        o = W.commit(prep(world()), j, tr, clk)
        self.assertEqual((o["state"], o["stage"]), (W.UNKNOWN, "text"))
        tr.mode["text"] = "ok"
        o = W.commit(prep(world()), j, tr, clk)
        self.assertEqual(o["state"], W.UNKNOWN)
        self.assertEqual(tr.calls, ["text"])

    def test_ack_without_id_is_unknown(self):
        j, tr = W.InMemoryJournal(), FakeTransport(text="noid")
        self.assertEqual(W.commit(prep(world()), j, tr, Clock())["state"], W.UNKNOWN)

    def test_crash_between_intent_and_ack_is_unknown_after_restart(self):
        path = os.path.join(self.tmp, "crash.sqlite")
        j, clk = W.SqliteJournal(path), Clock()

        class Crash(FakeTransport):
            def send_text(self, text, corr):
                self.calls.append("text")
                raise SystemExit("synthetic process death")    # BaseException: not caught by commit
        tr = Crash()
        with self.assertRaises(SystemExit):
            W.commit(prep(world()), j, tr, clk)
        j.close()
        j2 = W.SqliteJournal(path)
        self.assertEqual(j2.get("case-A")["state"], W.UNKNOWN)
        tr2 = FakeTransport()
        self.assertEqual(W.commit(prep(world()), j2, tr2, clk)["state"], W.UNKNOWN)
        self.assertEqual(tr2.calls, [])
        j2.close()

    def test_failure_between_text_and_media(self):
        j, tr, clk = W.InMemoryJournal(), FakeTransport(media="raise"), Clock()
        o = W.commit(prep(world()), j, tr, clk)
        self.assertEqual((o["state"], o["stage"]), (W.UNKNOWN, "media"))
        self.assertIsNotNone(o["text_msg_id"])
        tr.mode["media"] = "ok"
        W.commit(prep(world()), j, tr, clk)                       # no blind resend of text or media
        self.assertEqual(tr.calls, ["text", "media"])
        tr.rb = {"text_msg_id": o["text_msg_id"], "media_msg_id": None}     # A2WIRING2210: без доказательства — UNKNOWN
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.UNKNOWN)
        tr.rb["absence_proven"] = True
        o = W.reconcile("case-A", j, tr, clk)
        self.assertEqual((o["state"], o["stage"]), (W.FAILED, "media"))
        W.commit(prep(world()), j, tr, clk)
        self.assertEqual(tr.calls, ["text", "media", "readback", "readback"])

    def test_definitive_media_refusal_is_failed_partial(self):
        j, tr = W.InMemoryJournal(), FakeTransport(media="refuse")
        o = W.commit(prep(world()), j, tr, Clock())
        self.assertEqual((o["state"], o["stage"]), (W.FAILED, "media"))

    def test_definitive_text_refusal_allows_one_new_attempt(self):
        j, tr, clk = W.InMemoryJournal(), FakeTransport(text="refuse"), Clock()
        self.assertEqual(W.commit(prep(world()), j, tr, clk)["state"], W.FAILED)
        tr.mode["text"] = "ok"
        self.assertEqual(W.commit(prep(world()), j, tr, clk)["state"], W.MEDIA_SENT)

    def test_resume_after_text_sent_within_bind_window_only(self):
        j, clk = W.InMemoryJournal(), Clock()
        p = prep(world())
        W.commit(p, j, FakeTransport(media="raise"), clk)
        rec = j.get("case-A")                                      # simulate: text acked, crash before media
        rec.update(state=W.TEXT_SENT, rev=rec["rev"] + 1)
        j.rows["case-A"] = rec
        clk.t = rec["text_at"] + 400
        tr = FakeTransport()
        o = W.commit(p, j, tr, clk)
        self.assertEqual((o["state"], o["stage"]), (W.FAILED, "media"))
        self.assertEqual(tr.calls, [])

    def test_readback_unavailable_keeps_unknown(self):
        j, tr, clk = W.InMemoryJournal(), FakeTransport(text="raise", readback=OSError("synthetic")), Clock()
        W.commit(prep(world()), j, tr, clk)
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.UNKNOWN)
        tr.rb = {"bogus": 1}
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.UNKNOWN)
        tr.rb = {"text_msg_id": None, "media_msg_id": None}             # пусто без доказательства — UNKNOWN
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.UNKNOWN)
        tr.rb = {"text_msg_id": None, "media_msg_id": None, "absence_proven": True}
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.FAILED)
        tr.mode["text"] = "ok"
        self.assertEqual(W.commit(prep(world()), j, tr, clk)["state"], W.MEDIA_SENT)

    def test_neighbor_case_unchanged(self):
        j, clk = W.InMemoryJournal(), Clock()
        W.commit(prep(world("case-B")), j, FakeTransport(), clk)
        before = j.get("case-B")
        W.commit(prep(world("case-A")), j, FakeTransport(media="raise"), clk)
        self.assertEqual(j.get("case-B"), before)
        self.assertEqual(j.get("case-A")["state"], W.UNKNOWN)

    def test_concurrent_create_one_winner(self):
        j = W.InMemoryJournal()
        rec = {"case_key": "case-A", "rev": 1, "state": W.PREPARED}
        self.assertTrue(j.cas("case-A", None, rec))
        self.assertFalse(j.cas("case-A", None, rec))
        self.assertFalse(j.cas("case-A", 7, dict(rec, rev=8)))


def event_world(case_key="case-A", **kw):
    """A2WIRING2210 п.4: тот же мир в режиме событийной актуальности — без чисел сроков, с разбором до последнего
    входа, версией дела и свежей сверкой двери после последнего входа."""
    w = world(case_key, **kw)
    w["cfg"] = W.Config(validity=W.VALIDITY_EVENT)
    w["consent"].update(reviewed_upto=103, case_version=w["case"]["case_version"])
    w["case"]["revalidation"] = {"offer_key": w["consent"]["offer_key"], "at": T0 + 55, "source": "offer door"}
    return w


class EventValidity(unittest.TestCase):
    """Критерии Codex TB-A2-WIRING-2210-0742: accept на то же предложение; изменились цена/период — отказ; новый вход
    требует пересмотра; паспорт не смешивается с чужим делом; неполный readback после send→crash — без дубля."""

    def test_same_offer_accept_ready_without_numbers(self):
        p = prep(event_world())
        self.assertTrue(p.ok, p.reasons)
        self.assertEqual((p.validity["mode"], p.validity["consent_msg_id"], p.validity["offer_msg_id"],
                          p.validity["revalidated_at"], p.validity["quoted_at"]), ("event", 103, 102, T0 + 55, T0))
        self.assertIn("кандидат", p.validity["passport"])

    def test_caps_mode_still_needs_both_numbers_and_inf_is_not_a_bypass(self):
        for cfg in (W.Config(), W.Config(offer_to_consent_max_sec=float("inf"), consent_max_age_sec=float("inf"))):
            w = world(); w["cfg"] = cfg
            self.assertEqual(prep(w).reasons, [W.R_NOT_CONFIGURED])
        w = event_world(); w["cfg"] = W.Config(validity=W.VALIDITY_EVENT, consent_max_age_sec=float("nan"))
        self.assertEqual(prep(w).reasons, [W.R_NOT_CONFIGURED])
        w = event_world(); w["cfg"] = W.Config(validity=W.VALIDITY_EVENT, consent_max_age_sec=5)
        self.assertTrue(any("устарели" in r for r in prep(w).reasons))

    def test_changed_conditions_on_revalidation_refuse(self):
        w = event_world(); w["case"]["revalidation"]["offer_key"] = "другой-OFFER"
        self.assertTrue(any("другие условия" in r for r in prep(w).reasons))
        w = event_world(); w["case"]["revalidation"] = None
        self.assertTrue(any("нет свежей сверки" in r for r in prep(w).reasons))
        w = event_world(); w["case"]["revalidation"]["at"] = T0 + 40           # раньше последнего входа (103 @ +50)
        self.assertTrue(any("старше последнего входа" in r for r in prep(w).reasons))

    def test_new_input_needs_review_then_reviewed_later_photo_ok(self):
        w = event_world()
        w["messages"].append({"id": 104, "who": "клиент", "ts": T0 + 56, "text": ""})
        self.assertTrue(any("новый вход" in r for r in prep(w).reasons))
        w["consent"]["reviewed_upto"] = 104
        w["case"]["revalidation"]["at"] = T0 + 57
        self.assertTrue(prep(w).ok, prep(w).reasons)

    def test_case_version_moved_needs_review(self):
        w = event_world(); w["case"]["case_version"] = 4
        self.assertTrue(any("другой версии дела" in r for r in prep(w).reasons))

    def test_unknown_order_is_not_permission(self):
        w = event_world(); w["messages"][0]["ts"] = None
        self.assertTrue(any("порядок входящих" in r for r in prep(w).reasons))

    def test_passport_bound_to_our_request_only(self):
        w = event_world(); w["media"]["request_msg_id"] = None
        self.assertTrue(any("не привязано" in r for r in prep(w).reasons))
        w = event_world(); w["media"]["msg_id"] = 102                       # наше сообщение — не фото клиента
        self.assertTrue(any("не привязано" in r for r in prep(w).reasons))
        w = event_world(); w["messages"][3]["ts"] = T0 - 100                 # просьба после фото
        self.assertTrue(any("порядок просьбы" in r for r in prep(w).reasons))
        w = event_world(); w["media"]["case_key"] = "case-B"
        self.assertTrue(any("другого дела" in r for r in prep(w).reasons))

    def test_two_clients_do_not_overwrite(self):
        j, clk = W.InMemoryJournal(), Clock()
        a, b = prep(event_world("case-A")), prep(event_world("case-B"))
        self.assertNotEqual(a.digest, b.digest)
        W.commit(a, j, FakeTransport(), clk)
        W.commit(b, j, FakeTransport(), clk)
        self.assertEqual({j.get("case-A")["digest"], j.get("case-B")["digest"]}, {a.digest, b.digest})

    def test_send_crash_incomplete_readback_no_second_send(self):
        j, clk = W.InMemoryJournal(), Clock()
        tr = FakeTransport(text="raise")
        self.assertEqual(W.commit(prep(event_world()), j, tr, clk)["state"], W.UNKNOWN)
        for rb in ({"text_msg_id": None, "media_msg_id": None}, {"text_msg_id": None, "media_msg_id": None,
                                                                 "absence_proven": False}, {"text_msg_id": 7,
                                                                                            "media_msg_id": None}):
            tr.rb = rb
            self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], W.UNKNOWN, rb)
        tr.mode["text"] = "ok"
        self.assertEqual(W.commit(prep(event_world()), j, tr, clk)["state"], W.UNKNOWN)
        self.assertEqual(tr.calls.count("text"), 1)

    def test_both_parts_found_is_transport_state_not_booking(self):
        j, clk, tr = W.InMemoryJournal(), Clock(), FakeTransport()
        o = W.commit(prep(event_world()), j, tr, clk)
        tr.rb = {"text_msg_id": o["text_msg_id"], "media_msg_id": o["media_msg_id"]}
        self.assertEqual(W.reconcile("case-A", j, tr, clk)["state"], "posted")
        self.assertIs(W.ACCEPTED, W.POSTED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
