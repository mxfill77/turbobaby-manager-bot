# -*- coding: utf-8 -*-
"""Шов К4 к staff_ask и обработчику реплая — CONTRACT_K4: шапка (стр. 10, `tests/test_rental_case_seam.py`), §9.1
(StaffAskPort, EscalationPort), §13 (S1–S7 и контрактные тесты), §4.7 п.2 и толкование С-1 (DESIGN_DECISIONS
«Сборка: толкования»).

Гонятся НАСТОЯЩИЕ адаптеры `rental_case_adapters` — `StaffAskPort`, `EscalationPort`, `s1_result` — поверх подделки
staff_ask (`F.FakeStaffAsk`, шов S1–S7) и отправителя (`F.FakeTelegram`). Приёмка и демо ходят через
`F.FakeStaffAskPort`/`F.FakeEscalationPort`, поэтому адаптеры шва другими наборами не покрыты. Каждый пункт S1–S7 —
своя проверка; семь контрактных тестов §13 — на адаптере и `Store`.

Рамки: stdlib unittest; запуск `python tests/test_rental_case_seam.py` (код выхода ≠ 0 при провале) или раннером
`tests/run_rental_case_suites.py --only seam`. Сеть запрещена: ПЕРВЫМ импортируется `tests/rental_case_fakes.py`
(подмена socket.socket); после каждого теста попыток сети 0. Базы — только `RC.Store.create` в
`tempfile.mkdtemp(prefix="k4seam_<метка>_", dir=K4_TTMP)`, НЕ удаляются. SQL в файле нет: чтение — через API `Store`
(`case_view`, `stuck`, `events`, `due_expectations`, `claim_for_posting`). Текущий `row_ver` ожидания после перехода
узнаётся CAS-пробой: `mark_post_result` с заведомо чужим `expect_row_ver` обязан дать `conflict` без записи (§1.3, I8),
и исход несёт текущую версию строки; ключ пробы `seam-probe:…` не фиксируется (откат).

Параметры — как `params_a` приёмки (CONTRACT §14 вариант А): AUTO_ASK=True, STAFF_ADDRESSEES topic {9001} /
delivery {9002} / agents {9003}, RESULT_RECORD_PLACE["readiness"]="sink:fake", FEEDS_CONNECTED={intervention, inbound},
APPROVER_IDS={1001}; прочие — UNKNOWN (в т. ч. WAIT_BEFORE_AGENTS, ANSWER_TTL).
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import rental_case_fakes as F  # noqa: E402 — ПЕРВЫМ: подмена socket.socket до импорта модулей дела
import rental_case as RC  # noqa: E402
import rental_case_adapters as A  # noqa: E402

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
MOMENT = F.epoch(2026, 10, 9, 12, 0)                                    # 09.10.2026 12:00 (+7), CONTRACT §14

BIKE_NMAX = "NMAX 155 6908"
IVAN_U = "+66 81 234 5678"
TOPIC_CHAT, THREAD = "-1001000000001", "55"
DELIVERY_CHAT = "-1001000000002"
AGENTS_CHAT = "-1001000000003"
FOREIGN_CHAT = "-1009999999999"

APPROVER = {"kind": "human", "id": 1001, "name": "owner-synthetic"}
CODE = {"kind": "code", "id": None, "name": "test"}
SPL = {"kind": "code", "id": None, "name": "splinter"}

Q_RU = "Будет ли NMAX 6908 готов к выдаче 15.10?"
Q_TH = "รถ NMAX 6908 จะพร้อมส่งมอบวันที่ 15.10 ไหมครับ"
Q_RU_PREV = "Байк 6908 готов к выдаче завтра?"
Q_RU_PRICE = "Цена продления до 20.10?"

S1_KEYS = ["deduped", "posts", "qid", "refusal", "unknown_places", "why"]   # CONTRACT §13 S1
POST_KEYS = ["chat", "msg_id", "place", "thread_id"]
OWN_WAIT_PLUS = 3 * 3600 + 60                                          # свой срок подделки (staff_ask.py:26) + 60 с
PROBE_ROW_VER = 10 ** 9                                                # заведомо чужая версия строки для CAS-пробы


def params_a(**over):
    """Синтетические значения UNKNOWN-параметров (CONTRACT §14 вариант А) поверх PARAMS_DEFAULT — как в приёмке."""
    p = dict(RC.PARAMS_DEFAULT)
    rrp = p.get("RESULT_RECORD_PLACE")
    rrp = dict(rrp) if isinstance(rrp, dict) else {}
    rrp.setdefault("handover", "crm:в аренде")
    rrp.setdefault("return", "crm:завершена")
    rrp["readiness"] = "sink:fake"
    sa = p.get("STAFF_ADDRESSEES")
    sa = dict(sa) if isinstance(sa, dict) else {}
    sa.update({"topic": frozenset([9001]), "delivery": frozenset([9002]), "agents": frozenset([9003])})
    p.update({"AUTO_ASK": True, "STAFF_ADDRESSEES": sa, "RESULT_RECORD_PLACE": rrp,
              "FEEDS_CONNECTED": frozenset(["intervention", "inbound"]), "APPROVER_IDS": frozenset([1001])})
    p.update(over)
    return p


def r_ivan():
    """812 — Иван «В аренде» NMAX 155 6908 01.10–12.10 (живой формат двери clients, F.make_row)."""
    return F.make_row(row=812, status=F.ST_RENTED, bike=BIKE_NMAX, name="Иван", date_start="2026-10-01 10:00",
                      date_end="2026-10-12 10:00", contacts=IVAN_U, deposit_raw="3000", to_pay=11000, moment=MOMENT,
                      booking_id="bk-812")


def full(x):
    """Необрезающий вывод (контейнер сравнений и текст сообщений)."""
    return json.dumps(x, ensure_ascii=False, default=str, sort_keys=True)


def data(out):
    d = (out or {}).get("data")
    return d if isinstance(d, dict) else {}


def verdict(out):
    """Вердикт ответа: data.verdict (CONTRACT §5.4); у сироты — ok(verdict="orphan", data.orphan_id)."""
    v = data(out).get("verdict")
    return v if v is not None else (out or {}).get("verdict")


def rcode(out):
    return str((out or {}).get("reason") or "").split(":")[0].strip()


def sha12(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def roles(res):
    return [p.get("role") for p in (res or {}).get("posted") or []]


def posted_mid(res, place):
    for p in (res or {}).get("posted") or []:
        if p.get("place") == place:
            return p.get("msg_id")
    return None


def valid_facts(view):
    """Valid-факты из case_view (§8.4 «facts: valid …; stale/revoked — отдельным списком»)."""
    f = (view or {}).get("facts")
    if isinstance(f, dict):
        return [x for x in f.get("valid") or [] if isinstance(x, dict)]
    return [x for x in f or [] if isinstance(x, dict)]


def crafted_exp(exp_id="RE-seam", staff_kind="байк", q_ru=Q_RU, q_th=Q_TH, bike=BIKE_NMAX):
    """Ожидание в форме claim_for_posting (exp_id, case_id, case_ver, subject) — для проверок адаптера без базы."""
    return {"exp_id": exp_id, "case_id": "RC-seam", "case_ver": 1, "kind": "staff_question",
            "subject": {"staff_kind": staff_kind, "q_ru": q_ru, "q_th": q_th, "urgency": "клиент интересуется",
                        "bike": bike}}


# =====================================================================================================================
# Мир одного теста: подделки staff_ask/Telegram, настоящие адаптеры, при нужде — база Store в K4_TTMP
# =====================================================================================================================


class World(object):
    def __init__(self, label, store=True, enabled=True, topic_of=None):
        self.clock = F.FakeClock(MOMENT)
        self.ids = F.SeqIds()
        self.counters = F.Counters()
        self.telegram = F.FakeTelegram(self.clock, self.counters)
        self.sa = F.FakeStaffAsk(self.clock, self.counters, enabled=enabled)
        self.topic_of = topic_of if topic_of is not None else (lambda bike: THREAD)
        self.port = self.staff_port()
        self.esc = A.EscalationPort(self.sa.escalate, self.telegram.send, agents_chat=AGENTS_CHAT, clock=self.clock)
        self.dir, self.path, self.st = None, None, None
        if store:
            self.dir = tempfile.mkdtemp(prefix="k4seam_%s_" % label, dir=TTMP)
            self.path = os.path.abspath(os.path.join(self.dir, "rental_case.db"))
            RC.Store.create(self.path, clock=self.clock, new_id=self.ids)
            self.st = RC.Store(self.path, role="splinter", clock=self.clock, new_id=self.ids, params=params_a())

    def staff_port(self, ask=None, send=None):
        """Настоящий A.StaffAskPort: ask/send — подделки (или подмена теста), чаты и тема — от вызывающего (К5)."""
        return A.StaffAskPort(ask if ask is not None else self.sa.ask, send if send is not None else self.telegram.send,
                              clock=self.clock, servicing_chat=TOPIC_CHAT, delivery_chat=DELIVERY_CHAT,
                              agents_chat=AGENTS_CHAT, topic_of=self.topic_of)

    def sent(self, place):
        return [s for s in self.telegram.sent if s["place"] == place]

    def direct_ask(self, q_ru=Q_RU, q_th=Q_TH, kind="байк", expect_id=None, case_id=None, case_ver=None):
        """S1 подделки напрямую (свой вопрос вызывающего — без expect_id — или вопрос дела)."""
        return F.run_coro(self.sa.ask(self.telegram.send, kind=kind, bike=BIKE_NMAX, q_ru=q_ru, q_th=q_th,
                                      servicing_chat=TOPIC_CHAT, topic_id=THREAD, delivery_chat=DELIVERY_CHAT,
                                      agents_chat=AGENTS_CHAT, now=self.clock(), case_id=case_id, case_ver=case_ver,
                                      expect_id=expect_id))

    def tick(self, plus=OWN_WAIT_PLUS):
        return F.run_coro(self.sa.tick(self.telegram.send, agents_chat=AGENTS_CHAT, now=self.clock() + plus))


class SeamCase(unittest.TestCase):
    maxDiff = None

    def world(self, label, **kw):
        w = World(label, **kw)
        if w.st is not None:
            self.addCleanup(w.st.close)                                  # уборка закрытием, не удалением
        return w

    def tearDown(self):
        self.assertEqual(F.net_attempts(), 0, "попытка сети: %s" % F.net_log())

    # --- утверждения ---
    def assertCode(self, out, code, reason=None, what=""):
        self.assertIsInstance(out, dict, "%s: исход не словарь: %r" % (what, out))
        self.assertEqual(out.get("code"), code, "%s: ждали %s(%s): %s" % (what, code, reason or "", full(out)))
        if reason is not None:
            self.assertEqual(rcode(out), reason, "%s: причина: %s" % (what, full(out)))

    def assertS1Form(self, r, what=""):
        self.assertIsInstance(r, dict, what)
        self.assertEqual(sorted(r), S1_KEYS, "%s: форма ответа S1: %s" % (what, full(r)))
        self.assertIsInstance(r["posts"], list, what)
        self.assertIsInstance(r["unknown_places"], list, what)
        self.assertIsInstance(r["deduped"], bool, what)
        for p in r["posts"]:
            self.assertEqual(sorted(p), POST_KEYS, "%s: форма поста S1: %s" % (what, full(p)))

    # --- шаги через API Store ---
    def open_case(self, w):
        t = w.clock()
        src = {"name": F.CLIENTS_SOURCE, "ref": "строка 812", "method": "door", "read_at": t, "observed_at": t}
        out = w.st.open_case(origin="test", by=CODE, idem_key="open:test:bk:bk-812", booking_id="bk-812",
                             rental_row=r_ivan(), contacts=[], source=src, model_req=None, force_new=False)
        self.assertCode(out, "ok", what="open_case строки 812")
        cid = out.get("case_id") or data(out).get("case_id")
        self.assertTrue(cid and str(cid).startswith("RC-"), full(out))
        return cid

    def request(self, w, cid, staff_kind="байк", q_ru=Q_RU, q_th=Q_TH, ver=1, attempt=1):
        idem = "ask:%s:%s:%s:%s:%d" % (cid, ver, "-", sha12(staff_kind, q_ru), attempt)
        out = w.st.request_staff_question(cid, task_id=None, staff_kind=staff_kind, q_ru=q_ru, q_th=q_th,
                                          urgency="клиент интересуется", by=APPROVER, idem_key=idem, expect_ver=ver)
        self.assertCode(out, "ok", what="request_staff_question")
        exp_id = data(out).get("exp_id")
        self.assertTrue(exp_id, full(out))
        return exp_id

    def claim(self, w, cid, exp_id):
        got = w.st.claim_for_posting(by=SPL, kinds=("staff_question",))
        mine = [e for e in got or [] if e.get("exp_id") == exp_id]
        self.assertEqual(len(mine), 1, "claim_for_posting не отдал %s: %s" % (exp_id, full(got)))
        self.assertEqual(self.exp_view(w, cid, exp_id)["state"], "in_flight")
        return dict(mine[0])

    def mark(self, w, exp_id, result, row_ver):
        return w.st.mark_post_result(exp_id, result=result, by=SPL,
                                     idem_key="mark_post_result:%s:%d" % (exp_id, row_ver), expect_row_ver=row_ver)

    def row_ver_now(self, w, exp_id):
        """Текущий row_ver ожидания через API: CAS-проба заведомо чужой версией → conflict без записи (§1.3, I8)."""
        self._probes = getattr(self, "_probes", 0) + 1
        before = self.api_state(w, None)
        out = w.st.mark_post_result(exp_id, result={"unknown": "seam-probe"}, by=SPL,
                                    idem_key="seam-probe:%s:%d" % (exp_id, self._probes), expect_row_ver=PROBE_ROW_VER)
        self.assertCode(out, "conflict", what="CAS-проба row_ver")
        self.assertEqual(self.api_state(w, None), before, "CAS-проба записала")
        cur = out.get("current_ver") if out.get("current_ver") is not None else out.get("current_row_ver")
        self.assertTrue(isinstance(cur, int) and not isinstance(cur, bool), "conflict без текущей версии: %s"
                        % full(out))
        return cur

    def exp_view(self, w, cid, exp_id):
        mine = [e for e in w.st.case_view(cid).get("expectations") or [] if e.get("exp_id") == exp_id]
        self.assertEqual(len(mine), 1, "ожидания %s нет в case_view" % exp_id)
        return mine[0]

    def ask_and_post(self, w, cid, **kw):
        """request_staff_question → claim_for_posting → A.StaffAskPort.post → mark_post_result."""
        exp_id = self.request(w, cid, **kw)
        item = self.claim(w, cid, exp_id)
        res = F.run_coro(w.port.post(item))
        m = self.mark(w, exp_id, res, item["row_ver"])
        return exp_id, item, res, m

    def reply(self, w, msg_id, reply_to, author_id, chat=TOPIC_CHAT, thread_id=THREAD, reply_to_is_bot=True,
              text="พร้อมครับ / готов"):
        return w.st.on_staff_answer(chat=chat, msg_id=str(msg_id), reply_to=reply_to, reply_to_is_bot=reply_to_is_bot,
                                    thread_id=thread_id, author_id=author_id, author_username="staff%s" % author_id,
                                    is_bot=False, text=text, at=w.clock(),
                                    by={"kind": "staff", "id": author_id, "name": "staff"})

    def stuck_orphans(self, w):
        return [s for s in w.st.stuck() or [] if s.get("what") == "orphan"]

    def api_state(self, w, cid):
        """Всё, что видно через API чтения: состав дела, stuck(), журнал дела (часы подделки стоят — read_at тот же)."""
        snap = {"stuck": w.st.stuck()}
        if cid is not None:
            snap["view"] = w.st.case_view(cid)
            snap["events"] = w.st.events(cid)
        return full(snap)


# =====================================================================================================================
# S1 — ask: форма ответа, отказы только до отправки, unknown_places, запись до отправки (G12), posted
# =====================================================================================================================


class S1Ask(SeamCase):
    def test_s1_answer_form_keys_every_outcome(self):
        """S1: ответ ask — ровно posts, unknown_places, refusal, qid, deduped, why — у posted, отказа, unknown и
        дедупа; пост — place, chat, msg_id, thread_id."""
        w = self.world("s1form", store=False)
        r = w.direct_ask(expect_id="RE-form")
        self.assertS1Form(r, "posted")
        self.assertEqual([p["place"] for p in r["posts"]], ["topic", "delivery"], full(r))
        self.assertS1Form(w.direct_ask(q_ru="", expect_id="RE-form-2"), "refusal")
        w.telegram.mode["topic"] = "refuse"
        self.assertS1Form(w.direct_ask(q_ru="другой вопрос", expect_id="RE-form-3"), "unknown_places")
        w.telegram.mode["topic"] = "ok"
        self.assertS1Form(w.direct_ask(expect_id="RE-form"), "deduped")

    def test_s1_refusals_before_first_send_adapter_refused(self):
        """S1: refusal ∈ {disabled, no_text, no_thai, no_topic} — только до первой отправки (попыток 0); адаптер →
        {"refused": код}, не unknown и не posted."""
        cases = (
            ("disabled", dict(enabled=False), {}),
            ("no_text", {}, {"q_ru": ""}),
            ("no_thai", {}, {"q_th": ""}),
            ("no_topic", dict(topic_of=lambda bike: None), {}),
        )
        for code, wkw, ekw in cases:
            with self.subTest(refusal=code):
                w = self.world("s1ref_%s" % code, store=False, **wkw)
                exp = crafted_exp(exp_id="RE-%s" % code, **ekw)
                raw = []

                async def rec_ask(send, **kw):
                    r = await w.sa.ask(send, **kw)
                    raw.append(r)
                    return r

                res = F.run_coro(w.staff_port(ask=rec_ask).post(exp))
                self.assertEqual(res, {"refused": code}, full(res))
                self.assertEqual(len(raw), 1)
                self.assertS1Form(raw[0], code)
                self.assertEqual((raw[0]["refusal"], raw[0]["posts"], raw[0]["unknown_places"]), (code, [], []),
                                 full(raw[0]))
                self.assertEqual(w.telegram.attempts, [], "отказ после попытки отправки (%s)" % code)
                self.assertEqual(w.counters.staff_posts, 0)

    def test_s1_send_none_after_attempt_unknown_place_not_refusal_record_before_send_g12(self):
        """S1: send(...) → None после попытки → место в unknown_places (refusal нет); запись вопроса ДО отправки
        (G12); адаптер → {"unknown": why}, без повтора."""
        w = self.world("s1none", store=False)
        w.telegram.mode["topic"] = "refuse"
        exp = crafted_exp(exp_id="RE-g12")
        seen, raw = [], []

        async def spy_send(place, chat, text, thread_id=None, reply_to=None):
            seen.append([q for q, a in w.sa.asks.items() if a.get("expect_id") == "RE-g12"])
            return await w.telegram.send(place, chat, text, thread_id, reply_to)

        async def rec_ask(send, **kw):
            r = await w.sa.ask(send, **kw)
            raw.append(r)
            return r

        res = F.run_coro(w.staff_port(ask=rec_ask, send=spy_send).post(exp))
        self.assertEqual(len(raw), 1)
        r = raw[0]
        self.assertS1Form(r, "send→None")
        self.assertEqual((r["posts"], r["unknown_places"], r["refusal"]), ([], ["topic"], None), full(r))
        self.assertTrue(r["qid"], "вопрос не записан: %s" % full(r))
        self.assertEqual(seen, [[r["qid"]]], "запись вопроса не предшествовала отправке (G12): %s" % full(seen))
        self.assertIn(r["qid"], w.sa.asks)
        self.assertEqual(len(w.telegram.attempts), 1, "повтор отправки")
        self.assertEqual(sorted(res), ["unknown"], full(res))
        self.assertTrue(str(res["unknown"]).strip(), full(res))

    def test_s1_delivery_none_partial_posts_is_posted_question_only(self):
        """S1: тема принята, Delivery → None после попытки → posts=[topic], unknown_places=[delivery]; адаптер: posts
        непуст → posted с одной ролью question (CONTRACT §9.1)."""
        w = self.world("s1part", store=False)
        w.telegram.mode["delivery"] = "refuse"
        raw = []

        async def rec_ask(send, **kw):
            r = await w.sa.ask(send, **kw)
            raw.append(r)
            return r

        res = F.run_coro(w.staff_port(ask=rec_ask).post(crafted_exp(exp_id="RE-part")))
        self.assertEqual(([p["place"] for p in raw[0]["posts"]], raw[0]["unknown_places"], raw[0]["refusal"]),
                         (["topic"], ["delivery"], None), full(raw[0]))
        self.assertEqual(roles(res), ["question"], full(res))
        self.assertEqual(res.get("qid"), raw[0]["qid"])
        self.assertEqual(len(w.telegram.attempts), 2)

    def test_s1_deliver_then_raise_post_exists_adapter_unknown_single_attempt(self):
        """S1/I43: доставлено, затем исключение отправителя → пост в Telegram есть, ask отдаёт unknown_places,
        адаптер → {"unknown"}, не refused; попытка одна."""
        w = self.world("s1dtr", store=False)
        w.telegram.mode["topic"] = "deliver_then_raise"
        raw = []

        async def rec_ask(send, **kw):
            r = await w.sa.ask(send, **kw)
            raw.append(r)
            return r

        res = F.run_coro(w.staff_port(ask=rec_ask).post(crafted_exp(exp_id="RE-dtr")))
        self.assertEqual(len(w.sent("topic")), 1, "пост не доставлен подделкой")
        self.assertEqual(len(w.telegram.attempts), 1, "повтор отправки")
        self.assertEqual((raw[0]["posts"], raw[0]["unknown_places"]), ([], ["topic"]), full(raw[0]))
        self.assertEqual(sorted(res), ["unknown"], full(res))

    def test_s1_ask_exception_unknown_type_name_called_once(self):
        """§9.1/I43: исключение staff_ask.ask → {"unknown": "<тип>"}; ask вызван один раз, отправок нет."""
        w = self.world("s1exc", store=False)
        calls = []

        async def boom(send, **kw):
            calls.append(kw)
            raise TimeoutError("таймаут клиента staff_ask (подделка)")

        res = F.run_coro(w.staff_port(ask=boom).post(crafted_exp(exp_id="RE-exc")))
        self.assertEqual(res, {"unknown": "TimeoutError"})
        self.assertEqual(len(calls), 1, "повтор вызова ask")
        self.assertEqual(w.telegram.attempts, [])

    def test_s1_posted_roles_at_qid_and_case_fields_passed(self):
        """S1 через Store: posted — роли question/delivery (вид «байк») и agents (вид «цена»), at = clock(), qid
        проброшен; в ask ушли expect_id=exp_id, case_id, case_ver; mark_post_result принимает форму адаптера."""
        w = self.world("s1post")
        ci = self.open_case(w)
        exp_id = self.request(w, ci)
        item = self.claim(w, ci, exp_id)
        res = F.run_coro(w.port.post(item))
        self.assertEqual(sorted(res), ["posted", "qid"], full(res))
        self.assertEqual(roles(res), ["question", "delivery"], full(res))
        self.assertEqual([p["place"] for p in res["posted"]], ["topic", "delivery"])
        self.assertEqual([p["at"] for p in res["posted"]], [w.clock.now, w.clock.now], "at ≠ clock()")
        mine = [q for q, a in w.sa.asks.items() if a.get("expect_id") == exp_id]
        self.assertEqual(mine, [res["qid"]], "qid не проброшен: %s" % full(res))
        sent = [(s["chat"], s["msg_id"], s["thread_id"]) for s in w.telegram.sent]
        self.assertEqual([(p["chat"], p["msg_id"], p["thread_id"]) for p in res["posted"]], sent)
        self.assertEqual(res["posted"][0]["thread_id"], THREAD)
        self.assertEqual(w.sa.calls[-1], ("ask", {"kind": "байк", "bike": item["subject"]["bike"],
                                                  "expect_id": exp_id, "case_id": ci, "case_ver": 1}))
        self.assertEqual(w.sa.calls[-1][1]["bike"], BIKE_NMAX)
        m = self.mark(w, exp_id, res, item["row_ver"])
        self.assertCode(m, "ok", what="mark_post_result(posted) формы адаптера")
        e = self.exp_view(w, ci, exp_id)
        self.assertEqual((e["state"], e["ext_qid"]), ("waiting", res["qid"]), full(e))

        exp2 = self.request(w, ci, staff_kind="цена", q_ru=Q_RU_PRICE, q_th="")
        item2 = self.claim(w, ci, exp2)
        res2 = F.run_coro(w.port.post(item2))
        self.assertEqual(roles(res2), ["agents"], full(res2))
        self.assertEqual((res2["posted"][0]["place"], res2["posted"][0]["chat"]), ("agents", AGENTS_CHAT))
        self.assertEqual(w.sa.calls[-1], ("ask", {"kind": "цена", "bike": BIKE_NMAX, "expect_id": exp2,
                                                  "case_id": ci, "case_ver": 1}))
        self.assertCode(self.mark(w, exp2, res2, item2["row_ver"]), "ok")
        self.assertEqual(self.exp_view(w, ci, exp2)["state"], "escalated")


# =====================================================================================================================
# S2 — дедуп с expect_id
# =====================================================================================================================


class S2Dedup(SeamCase):
    def test_s2_dedup_key_includes_expect_id_and_port_maps_deduped(self):
        """S2: ключ дедупа = sha1(вид|байк|вопрос|expect_id): тот же вопрос с другим expect_id — новый вопрос; с тем же —
        {"deduped": True, "qid": прежний, "posts": []} без отправки; адаптер → {"deduped": qid}."""
        w = self.world("s2key", store=False)
        r1 = w.direct_ask(expect_id="RE-1")
        self.assertTrue(r1["posts"] and not r1["deduped"], full(r1))
        r2 = w.direct_ask(expect_id="RE-2")
        self.assertFalse(r2["deduped"], full(r2))
        self.assertTrue(r2["posts"], full(r2))
        self.assertNotEqual(r2["qid"], r1["qid"])
        attempts = len(w.telegram.attempts)
        r3 = w.direct_ask(expect_id="RE-1")
        self.assertS1Form(r3, "deduped")
        self.assertEqual((r3["deduped"], r3["qid"], r3["posts"]), (True, r1["qid"], []), full(r3))
        self.assertEqual(len(w.telegram.attempts), attempts, "дедуп отправил")
        self.assertNotEqual(F.FakeStaffAsk.dedup_key("байк", BIKE_NMAX, Q_RU, "RE-1"),
                            F.FakeStaffAsk.dedup_key("байк", BIKE_NMAX, Q_RU, "RE-2"))
        res = F.run_coro(w.port.post(crafted_exp(exp_id="RE-1")))
        self.assertEqual(res, {"deduped": r1["qid"]}, full(res))
        self.assertEqual(len(w.telegram.attempts), attempts)
        self.assertEqual(A.s1_result(r3, w.clock()), {"deduped": r1["qid"]})


# =====================================================================================================================
# S3 — записи дела managed_by="rental_case": due()/tick() их пропускают
# =====================================================================================================================


class S3Managed(SeamCase):
    def test_s3_case_record_managed_skipped_by_due_and_tick_control_escalates(self):
        """S3: запись с expect_id несёт managed_by="rental_case"; due() и tick() через 3 ч + 60 с её пропускают
        (0 постов); контроль — запись без expect_id эскалируется своим сроком подделки (1 пост)."""
        w = self.world("s3")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        qid = res["qid"]
        self.assertEqual(w.sa.asks[qid].get("managed_by"), "rental_case")
        later = w.clock() + OWN_WAIT_PLUS
        self.assertNotIn(qid, w.sa.due(later))
        self.assertEqual(w.tick(), 0, "tick эскалировал вопрос дела")
        self.assertEqual(w.sent("agents"), [])
        own = w.direct_ask(q_ru="свой вопрос Splinter", q_th="คำถาม")
        self.assertIsNone(w.sa.asks[own["qid"]].get("managed_by"))
        self.assertEqual(w.sa.due(later), [own["qid"]], "контроль подделки: свой вопрос в due")
        self.assertEqual(w.tick(), 1, "контроль подделки: свой вопрос эскалируется")
        self.assertEqual(len(w.sent("agents")), 1)
        self.assertEqual((w.sa.asks[own["qid"]]["status"], w.sa.asks[qid]["status"]), ("escalated", "open"))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "waiting")


# =====================================================================================================================
# S4 — escalate
# =====================================================================================================================


class S4Escalate(SeamCase):
    def test_s4_escalate_forms_direct(self):
        """S4: escalate → {"posts": [пост «Агентов»]} | {"unknown_places": ["agents"]} | {"refusal"} для неизвестного
        и закрытого qid."""
        w = self.world("s4dir", store=False)
        q1 = w.direct_ask(q_ru="вопрос 1")["qid"]
        r = F.run_coro(w.sa.escalate(q1, w.telegram.send, agents_chat=AGENTS_CHAT, why="решение одобряющего"))
        self.assertEqual(len(r.get("posts") or []), 1, full(r))
        p = r["posts"][0]
        self.assertEqual(sorted(p), POST_KEYS, full(p))
        self.assertEqual((p["place"], p["chat"], p["thread_id"]), ("agents", AGENTS_CHAT, None))
        self.assertFalse(r.get("refusal"))
        q2 = w.direct_ask(q_ru="вопрос 2")["qid"]
        w.telegram.mode["agents"] = "refuse"
        r = F.run_coro(w.sa.escalate(q2, w.telegram.send, agents_chat=AGENTS_CHAT, why="решение одобряющего"))
        self.assertEqual((r.get("unknown_places"), r.get("posts") or [], r.get("refusal")), (["agents"], [], None),
                         full(r))
        w.telegram.mode["agents"] = "ok"
        attempts = len(w.telegram.attempts)
        r = F.run_coro(w.sa.escalate("нет-такого", w.telegram.send, agents_chat=AGENTS_CHAT, why="x"))
        self.assertTrue(r.get("refusal"), full(r))
        self.assertEqual(r.get("posts") or [], [])
        self.assertEqual(len(w.telegram.attempts), attempts, "отказ эскалации после попытки отправки")
        q3 = w.direct_ask(q_ru="вопрос 3")["qid"]
        attempts = len(w.telegram.attempts)
        self.assertTrue(w.sa.close(q3, reason="superseded"))
        r = F.run_coro(w.sa.escalate(q3, w.telegram.send, agents_chat=AGENTS_CHAT, why="x"))
        self.assertTrue(r.get("refusal"), full(r))
        self.assertEqual(len(w.telegram.attempts), attempts, "отказ эскалации после попытки отправки")

    def test_s4_escalation_port_forms(self):
        """S4 через A.EscalationPort: posted с role=escalation и qid; unknown_places → {"unknown"}; refusal →
        {"refused"} (неизвестный и закрытый qid); исключение escalate → {"unknown": "<тип>"}, вызов один."""
        w = self.world("s4port", store=False)
        q1 = w.direct_ask(q_ru="вопрос 1")["qid"]
        res = F.run_coro(w.esc.escalate({"exp_id": "RE-e1", "ext_qid": q1}))
        self.assertEqual(sorted(res), ["posted", "qid"], full(res))
        self.assertEqual(roles(res), ["escalation"], full(res))
        self.assertEqual((res["qid"], res["posted"][0]["place"], res["posted"][0]["chat"]), (q1, "agents", AGENTS_CHAT))
        self.assertEqual(res["posted"][0]["at"], w.clock.now)
        self.assertEqual(w.sa.calls[-1], ("escalate", {"qid": q1, "why": "решение одобряющего"}))
        q2 = w.direct_ask(q_ru="вопрос 2")["qid"]
        w.telegram.mode["agents"] = "refuse"
        res = F.run_coro(w.esc.escalate({"exp_id": "RE-e2", "ext_qid": q2}))
        self.assertEqual(sorted(res), ["unknown"], full(res))
        w.telegram.mode["agents"] = "ok"
        res = F.run_coro(w.esc.escalate({"exp_id": "RE-e3", "ext_qid": "нет-такого"}))
        self.assertEqual(sorted(res), ["refused"], full(res))
        q3 = w.direct_ask(q_ru="вопрос 3")["qid"]
        w.sa.close(q3, reason="superseded")
        res = F.run_coro(w.esc.escalate({"exp_id": "RE-e4", "ext_qid": q3}))
        self.assertEqual(sorted(res), ["refused"], full(res))
        calls = []

        async def boom(qid, send, **kw):
            calls.append(qid)
            raise TimeoutError("таймаут escalate (подделка)")

        port = A.EscalationPort(boom, w.telegram.send, agents_chat=AGENTS_CHAT, clock=w.clock)
        self.assertEqual(F.run_coro(port.escalate({"exp_id": "RE-e5", "ext_qid": q1})), {"unknown": "TimeoutError"})
        self.assertEqual(calls, [q1])

    def test_s4_escalation_port_result_accepted_by_store(self):
        """S4 → Store: эскалация одобряющим (WAIT_BEFORE_AGENTS=UNKNOWN, I43) → A.EscalationPort → mark_escalated
        принимает форму адаптера; ожидание escalated, пост «Агентов» один."""
        w = self.world("s4store")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        rv = self.row_ver_now(w, exp_id)
        out = w.st.claim_escalation(exp_id, by=APPROVER, idem_key="claim_escalation:%s:%d" % (exp_id, rv),
                                    expect_row_ver=rv)
        self.assertCode(out, "ok", what="claim_escalation одобряющим")
        e = self.exp_view(w, ci, exp_id)
        self.assertEqual(e["state"], "escalating")
        esc = F.run_coro(w.esc.escalate({"exp_id": exp_id, "ext_qid": e["ext_qid"]}))
        self.assertEqual(roles(esc), ["escalation"], full(esc))
        self.assertEqual(esc["qid"], res["qid"])
        rv = self.row_ver_now(w, exp_id)
        out = w.st.mark_escalated(exp_id, result=esc, by=SPL, idem_key="mark_escalated:%s:%d" % (exp_id, rv),
                                  expect_row_ver=rv)
        self.assertCode(out, "ok", what="mark_escalated(форма адаптера)")
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "escalated")
        self.assertEqual(len(w.sent("agents")), 1)


# =====================================================================================================================
# S5 — обработчик реплая: сначала дело, потом мозг, независимо друг от друга
# =====================================================================================================================


class S5ReplyHandler(SeamCase):
    def test_s5_case_first_brain_failure_answer_in_case(self):
        """S5: порядок ['case', 'brain']; обрыв мозга не мешает ответу в деле (accepted, ответ в case_view)."""
        w = self.world("s5a")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")

        def brain_down(line):
            raise ConnectionError("мозг недоступен (подделка)")

        handler = F.FakeReplyHandler(w.st.on_staff_answer, w.sa, brain_down)
        case_out, brain_out = handler.handle(TOPIC_CHAT, "7700", posted_mid(res, "topic"), True, THREAD, 9001,
                                             "staff9001", False, "готов", w.clock())
        self.assertEqual(handler.order, ["case", "brain"])
        self.assertEqual(verdict(case_out), "accepted", full(case_out))
        self.assertEqual(brain_out, {"error": "ConnectionError"})
        ans = [a for a in w.st.case_view(ci)["answers"] if (a.get("src") or {}).get("ref") == "%s:7700" % TOPIC_CHAT]
        self.assertEqual([(a["verdict"], a["exp_id"]) for a in ans], [("accepted", exp_id)], full(ans))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "answered")

    def test_s5_store_call_exception_brain_still_called(self):
        """S5: исключение вызова дела не мешает вызову мозга: порядок ['case', 'brain'], строка мозга записана."""
        w = self.world("s5b")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        lines = []

        def store_down(**kw):
            raise RuntimeError("хранилище недоступно (подделка)")

        def brain_ok(line):
            lines.append(line)
            return True, ""

        handler = F.FakeReplyHandler(store_down, w.sa, brain_ok)
        case_out, brain_out = handler.handle(TOPIC_CHAT, "7701", posted_mid(res, "topic"), True, THREAD, 9001,
                                             "staff9001", False, "готов", w.clock())
        self.assertEqual(handler.order, ["case", "brain"])
        self.assertEqual(case_out, {"error": "RuntimeError"})
        self.assertEqual((brain_out.get("recorded"), brain_out.get("qid")), (True, res["qid"]), full(brain_out))
        self.assertEqual(len(lines), 1)
        self.assertEqual(w.st.case_view(ci)["answers"], [], "ответ в деле при упавшем вызове дела")
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "waiting")


# =====================================================================================================================
# S6 — close
# =====================================================================================================================


class S6Close(SeamCase):
    def test_s6_close_hides_record_from_due_tick_dedup(self):
        """S6: close(qid) → запись closed; due, tick и дедуп её не видят — тот же ключ даёт новый qid (и у своего
        вопроса, и у вопроса дела с тем же expect_id); неизвестный qid → False."""
        w = self.world("s6", store=False)
        own = w.direct_ask(q_ru="свой вопрос")
        qa = own["qid"]
        later = w.clock() + OWN_WAIT_PLUS
        self.assertEqual(w.sa.due(later), [qa], "контроль: открытый свой вопрос в due")
        self.assertTrue(w.sa.close(qa, reason="superseded"))
        self.assertEqual(w.sa.asks[qa]["status"], "closed")
        self.assertEqual(w.sa.due(later), [])
        self.assertEqual(w.tick(), 0)
        self.assertEqual(w.sent("agents"), [])
        again = w.direct_ask(q_ru="свой вопрос")
        self.assertFalse(again["deduped"], full(again))
        self.assertTrue(again["posts"])
        self.assertNotEqual(again["qid"], qa)
        qm = w.direct_ask(expect_id="RE-6")["qid"]
        self.assertTrue(w.sa.close(qm, reason="superseded"))
        again = w.direct_ask(expect_id="RE-6")
        self.assertFalse(again["deduped"], full(again))
        self.assertNotEqual(again["qid"], qm)
        self.assertFalse(w.sa.close("нет-такого", reason="superseded"))


# =====================================================================================================================
# S7 — пост вопроса дела не передаётся в _dlive_mark решателя
# =====================================================================================================================


class S7Dlive(SeamCase):
    def test_s7_case_post_not_marked_for_solver_own_post_marked(self):
        """S7: пост вопроса с expect_id (через адаптер и Store) не попадает в dlive_marks; без expect_id — попадает."""
        w = self.world("s7")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        self.assertEqual([x for x in w.sa.dlive_marks if x[2] == res["qid"]], [], "S7 нарушен")
        own = w.direct_ask(q_ru="свой вопрос")
        topic = [p for p in own["posts"] if p["place"] == "topic"][0]
        self.assertEqual([x for x in w.sa.dlive_marks if x[2] == own["qid"]], [(TOPIC_CHAT, topic["msg_id"], own["qid"])])


# =====================================================================================================================
# §13 — контрактные тесты на адаптере и Store
# =====================================================================================================================


class C13Contract(SeamCase):
    def test_c13_1_bump_qids_to_close_close_tick_zero_posts(self):
        """§13 (1): подъём версии → staff_qids_to_close → close (S6) → tick подделки через 3 ч по ЕЁ сроку → 0
        постов (I41, I43)."""
        w = self.world("c1")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        out = w.st.bump_version(ci, reason="new_request", ref="wa:in:4", by=APPROVER,
                                idem_key="bump:%s:1:new_request:wa:in:4" % ci, expect_ver=1)
        self.assertCode(out, "ok", what="bump_version")
        qids = data(out).get("staff_qids_to_close") or []
        self.assertEqual(qids, [res["qid"]], full(out))
        for q in qids:
            self.assertTrue(w.sa.close(q, reason="superseded"))
        self.assertEqual(w.sa.asks[res["qid"]]["status"], "closed")
        self.assertEqual(w.tick(), 0)
        self.assertEqual(w.sent("agents"), [])
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "superseded")

    def test_c13_2_agents_question_single_post_not_due(self):
        """§13 (2): вопрос места «Агенты» — один пост; due_expectations его не отдаёт (+48 ч), tick подделки не
        добавляет поста (I41)."""
        w = self.world("c2")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci, staff_kind="цена", q_ru=Q_RU_PRICE, q_th="")
        self.assertCode(m, "ok")
        self.assertEqual(roles(res), ["agents"], full(res))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "escalated")
        self.assertEqual(len(w.sent("agents")), 1)
        due = w.st.due_expectations(now=w.clock() + 48 * 3600) or []
        self.assertEqual([e for e in due if e.get("exp_id") == exp_id], [], full(due))
        self.assertEqual(w.tick(), 0)
        self.assertEqual(len(w.sent("agents")), 1)

    def test_c13_3_delivered_then_exception_unknown_no_retry(self):
        """§13 (3): доставлено + исключение отправителя → адаптер {"unknown"} → flight_unknown; повтора нет
        (claim_for_posting его не отдаёт, попыток не прибавилось, ask вызван один раз; I15, I43)."""
        w = self.world("c3")
        ci = self.open_case(w)
        w.telegram.mode["topic"] = "deliver_then_raise"
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertEqual(sorted(res), ["unknown"], full(res))
        self.assertCode(m, "ok", what="mark_post_result(unknown)")
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "flight_unknown")
        self.assertEqual(len(w.sent("topic")), 1)
        attempts = len(w.telegram.attempts)
        w.clock.advance(3600)
        got = w.st.claim_for_posting(by=SPL)
        self.assertEqual([x for x in got or [] if x.get("exp_id") == exp_id], [])
        self.assertEqual(len(w.telegram.attempts), attempts, "повтор поста")
        self.assertEqual(len([c for c in w.sa.calls if c[0] == "ask" and c[1].get("expect_id") == exp_id]), 1)

    def test_c13_4_dedup_deduped_flight_unknown_human_decision(self):
        """§13 (4): staff_ask вернул уже открытый вопрос дела (deduped) → адаптер {"deduped": qid} →
        mark_post_result → flight_unknown + human_decision, не отказ (I-13)."""
        w = self.world("c4")
        ci = self.open_case(w)
        exp_id = self.request(w, ci)
        item = self.claim(w, ci, exp_id)
        first = F.run_coro(w.port.post(item))                         # прежняя попытка уже записана в staff_ask
        self.assertEqual(roles(first), ["question", "delivery"], full(first))
        res = F.run_coro(w.port.post(item))
        self.assertEqual(res, {"deduped": first["qid"]}, full(res))
        m = self.mark(w, exp_id, res, item["row_ver"])
        self.assertCode(m, "ok", what="mark_post_result(deduped)")
        e = self.exp_view(w, ci, exp_id)
        self.assertEqual((e["state"], e["next_check"]), ("flight_unknown", "human_decision"), full(e))

    def test_c13_5_delivery_addressee_answer_accepted_via_post(self):
        """§13 (5): ответ сотрудника Delivery связан по rc_post с адресатами Delivery → accepted; контроль — адресат
        темы на пост Delivery → reference_foreign_author, ожидание не двигается (§4.7 п.7)."""
        w = self.world("c5")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")
        dmid = posted_mid(res, "delivery")
        self.assertTrue(dmid, full(res))
        out = self.reply(w, "7499", dmid, 9001, chat=DELIVERY_CHAT, thread_id=None)
        self.assertCode(out, "ok", what="реплай не-адресата Delivery")
        self.assertEqual(verdict(out), "reference_foreign_author", full(out))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "waiting")
        out = self.reply(w, "7500", dmid, 9002, chat=DELIVERY_CHAT, thread_id=None)
        self.assertEqual(verdict(out), "accepted", full(out))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "answered")
        ans = [a for a in w.st.case_view(ci)["answers"] if a.get("verdict") == "accepted"]
        self.assertEqual([(a["author_id"], (a.get("src") or {}).get("source")) for a in ans],
                         [(9002, "staff_ask:delivery")], full(ans))

    def test_c13_6b_orphan_known_chats_foreign_chat_rejected_linked_after_post_found(self):
        """§13 (6), С-1(а)/(б): чаты мест topic/delivery хранилищу известны (прежний вопрос) — реплай боту на
        доставленный пост flight_unknown в чате темы → сирота; в чужом чате → rejected(not_linked) без записи;
        mark_post_result(posted) связывает сироту по точному (chat, reply_to) → accepted, ожидание answered (I40)."""
        w = self.world("c6b")
        ci = self.open_case(w)
        e0, item0, res0, m0 = self.ask_and_post(w, ci, q_ru=Q_RU_PREV)
        self.assertCode(m0, "ok", what="прежний вопрос: чаты мест topic/delivery известны хранилищу")
        w.telegram.mode["topic"] = "deliver_then_raise"
        exp_id = self.request(w, ci)
        item = self.claim(w, ci, exp_id)
        res = F.run_coro(w.port.post(item))
        self.assertEqual(sorted(res), ["unknown"], full(res))
        self.assertCode(self.mark(w, exp_id, res, item["row_ver"]), "ok")
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "flight_unknown")
        delivered = w.sent("topic")[-1]
        out = self.reply(w, "7600", delivered["msg_id"], 9001)
        self.assertCode(out, "ok", what="реплай на пост flight_unknown")
        self.assertEqual(verdict(out), "orphan", full(out))
        self.assertEqual([o["msg_id"] for o in self.stuck_orphans(w)], ["7600"])
        before = self.api_state(w, ci)
        out = self.reply(w, "7601", "99999", 9001, chat=FOREIGN_CHAT, thread_id=None, reply_to_is_bot=True)
        self.assertCode(out, "rejected", "not_linked", "реплай боту в чате вне чатов ожидания (С-1(б))")
        self.assertEqual(self.api_state(w, ci), before, "rejected(not_linked) записал")
        rv = self.row_ver_now(w, exp_id)
        found = {"posted": [{"place": "topic", "chat": TOPIC_CHAT, "msg_id": delivered["msg_id"], "thread_id": THREAD,
                             "role": "question", "at": delivered["at"]}], "qid": None}
        out = self.mark(w, exp_id, found, rv)
        self.assertCode(out, "ok", what="пост найден — mark_post_result(posted) из flight_unknown")
        view = w.st.case_view(ci)
        orph = [o for o in view["orphans"] if o.get("msg_id") == "7600"]
        self.assertEqual([o["state"] for o in orph], ["linked"], full(view["orphans"]))
        self.assertTrue(orph[0]["answer_id"])
        ans = [a for a in view["answers"] if a.get("answer_id") == orph[0]["answer_id"]]
        self.assertEqual([(a["verdict"], a["exp_id"]) for a in ans], [("accepted", exp_id)], full(ans))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "answered")
        self.assertEqual(self.stuck_orphans(w), [])

    def test_c13_6c_orphan_chat_unknown_kept_never_linked_elsewhere(self):
        """§13 (6), С-1(в): постов мест ещё не было — чат ожидания flight_unknown хранилищу неизвестен; реплай не боту
        → rejected(not_linked) без записи; реплай боту в любом чате → ok(orphan); mark_post_result(posted) в чате темы
        сироту чужого чата НЕ связывает (связь только по точному (chat, reply_to)): она остаётся сиротой, ответа в деле
        нет, ожидание waiting."""
        w = self.world("c6c")
        ci = self.open_case(w)
        w.telegram.mode["topic"] = "deliver_then_raise"
        exp_id = self.request(w, ci)
        item = self.claim(w, ci, exp_id)
        res = F.run_coro(w.port.post(item))
        self.assertEqual(sorted(res), ["unknown"], full(res))
        self.assertCode(self.mark(w, exp_id, res, item["row_ver"]), "ok")
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "flight_unknown")
        delivered = w.sent("topic")[-1]
        before = self.api_state(w, ci)
        out = self.reply(w, "7602", "99998", 9001, chat=FOREIGN_CHAT, thread_id=None, reply_to_is_bot=False)
        self.assertCode(out, "rejected", "not_linked", "реплай не боту")
        self.assertEqual(self.api_state(w, ci), before, "rejected(not_linked) записал")
        out = self.reply(w, "7601", "99999", 9001, chat=FOREIGN_CHAT, thread_id=None, reply_to_is_bot=True)
        self.assertCode(out, "ok", what="чат ожидания неизвестен — сирота (С-1(в))")
        self.assertEqual(verdict(out), "orphan", full(out))
        rv = self.row_ver_now(w, exp_id)
        found = {"posted": [{"place": "topic", "chat": TOPIC_CHAT, "msg_id": delivered["msg_id"], "thread_id": THREAD,
                             "role": "question", "at": delivered["at"]}], "qid": None}
        self.assertCode(self.mark(w, exp_id, found, rv), "ok")
        self.assertEqual([(o["msg_id"], o["chat"]) for o in self.stuck_orphans(w)], [("7601", FOREIGN_CHAT)],
                         "сирота чужого чата не осталась сиротой")
        view = w.st.case_view(ci)
        self.assertEqual(view["answers"], [], full(view["answers"]))
        self.assertEqual([o for o in view["orphans"] if o.get("state") == "linked"], [], full(view["orphans"]))
        self.assertEqual([e for e in w.st.events(ci) if e.get("type") == "orphan_linked"], [])
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "waiting")

    def test_c13_7_brain_failure_after_on_staff_answer_answer_in_case(self):
        """§13 (7): обрыв мозга после on_staff_answer — ответ в деле есть: accepted, факт staff_answer, ожидание
        answered, событие answer_received в журнале дела."""
        w = self.world("c7")
        ci = self.open_case(w)
        exp_id, item, res, m = self.ask_and_post(w, ci)
        self.assertCode(m, "ok")

        def brain_down(line):
            raise ConnectionError("мозг оборвался (подделка)")

        handler = F.FakeReplyHandler(w.st.on_staff_answer, w.sa, brain_down)
        case_out, brain_out = handler.handle(TOPIC_CHAT, "7702", posted_mid(res, "topic"), True, THREAD, 9001,
                                             "staff9001", False, "готов", w.clock())
        self.assertEqual(brain_out, {"error": "ConnectionError"})
        self.assertEqual(verdict(case_out), "accepted", full(case_out))
        view = w.st.case_view(ci)
        self.assertEqual([a["verdict"] for a in view["answers"]], ["accepted"], full(view["answers"]))
        self.assertEqual([f.get("kind") for f in valid_facts(view) if f.get("kind") == "staff_answer"],
                         ["staff_answer"], full(view["facts"]))
        self.assertEqual(self.exp_view(w, ci, exp_id)["state"], "answered")
        got = [e for e in w.st.events(ci) if e.get("type") == "answer_received"]
        self.assertEqual([e["payload"].get("msg_id") for e in got], ["7702"], full(got))


if __name__ == "__main__":
    unittest.main()
