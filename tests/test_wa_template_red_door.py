#!/usr/bin/env python3
"""NIGHT0710-B3g, второй круг: атаки красной команды на дверь шаблонов, перенесены строителем в наборы дерева
целиком как регрессия (tpl_aux/red/tests/test_red_tpl_door.py). На кандидате №1 красные: R02d, R06u, R07, R09, R10b —
дефекты исправлены вторым коммитом; прочие атаки — замки устоявшего.

КРАСНАЯ КОМАНДА NIGHT0710-B3g: атаки на дверь шаблонов `wa_send.send_template`.

Каждая проверка — атака. Имя R## — номер атаки в RED.md. PASS = кандидат устоял, FAIL = сломан (сценарий в RED.md).
Сети нет: швы `get`/`transport` — подделки, `urllib.request.urlopen` — ловушка на весь прогон."""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"


def _no_net(*a, **kw):
    raise AssertionError("тест обратился к сети")


urllib.request.urlopen = _no_net

import wa_send as S  # noqa: E402

NUM = "66812345678"
KEY = "real_key_abcdef0123456789"
NAMES = ("payment_reminder", "rental_end_reminder", "reply_request")
OK_POST = (200, '{"messages":[{"id":"wamid.T1"}]}', None)


def env(send="1", tpl="1", key=KEY):
    return {"WA_SEND": send, "WA_AGENT_TEMPLATES": tpl, "WA_360_API_KEY": key}


class Trap:
    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise AssertionError("к сети обратились там, где нельзя")


class Get:
    def __init__(self, status=200, body="", err=None, on_call=None):
        self.status, self.body, self.err, self.calls, self.timeouts = status, body, err, [], []
        self.on_call = on_call

    def __call__(self, url, key, timeout):
        self.calls.append(url)
        self.timeouts.append(timeout)
        if self.on_call:
            self.on_call()
        return self.status, self.body, self.err


class Post:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, payload, key, timeout):
        self.calls.append(payload)
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def item(name="reply_request", lang="ru", status="approved", category="UTILITY", reason=None, drop=()):
    d = {"name": name, "language": lang, "status": status, "category": category, "rejected_reason": reason,
         "id": "id_%s_%s" % (name, lang)}
    for k in drop:
        d.pop(k, None)
    return d


def listing(items, total=None):
    body = {"waba_templates": items, "count": len(items), "limit": 1000, "offset": 0}
    if total is not False:
        body["total"] = len(items) if total is None else total
    return json.dumps(body)


def full(status="approved", category="UTILITY", reason=None):
    return listing([item(n, lg, status, category, reason) for n in NAMES for lg in ("ru", "en")])


def send(name="reply_request", lang="ru", params=("байка",), get=None, post=None, e=None, clock=None, budget=None):
    kw = {}
    if clock is not None:
        kw["clock"] = clock
    if budget is not None:
        kw["budget"] = budget
    return S.send_template(NUM, name, lang, list(params) if isinstance(params, tuple) else params,
                           env=e or env(), get=get or Trap(), transport=post or Trap(), sleep=lambda s: None, **kw)


# ═══ R01 — список без нужного языка ═════════════════════════════════════════════════════

def test_R01_list_without_language_complete():
    body = listing([item("reply_request", "en"), item("payment_reminder", "ru")])
    post = Post([OK_POST])
    r = send(get=Get(200, body), post=post)
    assert r["outcome"] == S.NOT_SENT and post.calls == [], r
    assert r["approval"] == S.TPL_NOT_APPROVED and "у провайдера нет" in r["reason"], r


def test_R01b_list_without_language_no_total():
    body = listing([item("reply_request", "en")], total=False)
    post = Post([OK_POST])
    r = send(get=Get(200, body), post=post)
    assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, r


def test_R01c_lang_variant_en_US_not_matched():
    """Meta иногда отдаёт язык как en_US — пара (reply_request, en) не найдена; полный список → «нет у провайдера»,
    POST нет (не шлём не тот шаблон)."""
    body = listing([item("reply_request", "en_US"), item("reply_request", "ru", "pending")])
    post = Post([OK_POST])
    r = send(lang="en", params=("bike",), get=Get(200, body), post=post)
    assert r["outcome"] == S.NOT_SENT and post.calls == [], r


# ═══ R02 — pending / rejected / paused / MARKETING ═══════════════════════════════════════

def test_R02_statuses_not_approved_words():
    for st in ("pending", "PENDING", "submitted", "rejected", "paused", "disabled", "in_appeal", "deleted",
               "pending_deletion", "limit_exceeded"):
        post = Post([OK_POST])
        r = send(get=Get(200, full(st, reason="INVALID_FORMAT" if st == "rejected" else None)), post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [], (st, r)
        assert r["approval"] == S.TPL_NOT_APPROVED and st[:30] in r["reason"], (st, r["reason"])
        if st == "rejected":
            assert "INVALID_FORMAT" in r["reason"], r["reason"]


def test_R02b_category_marketing_authentication():
    for cat in ("MARKETING", "marketing", "AUTHENTICATION"):
        post = Post([OK_POST])
        r = send(get=Get(200, full("approved", cat)), post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_NOT_APPROVED, (cat, r)
        assert cat[:30] in r["reason"], r["reason"]


def test_R02c_utility_lowercase_is_approved():
    post = Post([OK_POST])
    r = send(get=Get(200, full("Approved", "utility")), post=post)
    assert r["outcome"] == S.SENT and len(post.calls) == 1, r


def test_R02d_category_absent_is_not_a_meta_fact():
    """Провайдер НЕ НАЗВАЛ категорию (поля нет) — это «не прочитали», а не «Meta сменила категорию».
    FACT: слова отказа не вправе утверждать факт, которого в ответе нет."""
    body = listing([item("reply_request", "ru", drop=("category",))])
    post = Post([OK_POST])
    r = send(get=Get(200, body), post=post)
    assert post.calls == [] and r["outcome"] == S.NOT_SENT, r
    assert "сменила категорию" not in r["reason"], r["reason"]
    assert r["approval"] == S.TPL_UNKNOWN, (r["approval"], r["reason"])


# ═══ R03 — сбой списка ═══════════════════════════════════════════════════════════════════

def test_R03_list_failures_unknown_no_post():
    cases = [
        Get(500, '{"meta":{"developer_message":"boom"}}'), Get(502, ""), Get(503, "<html>gw</html>"),
        Get(401, '{"meta":{"developer_message":"Invalid api key"}}'), Get(403, ""), Get(404, ""),
        Get(None, "", "timeout"), Get(None, "", "RemoteDisconnected"), Get(200, "<html>captive</html>"),
        Get(200, "[]"), Get(200, '{"waba_templates": "x"}'), Get(200, ""), Get(200, "null"),
        Get("200 OK", full()), Get(None, full(), None),
    ]
    for g in cases:
        post = Post([OK_POST])
        r = send(get=g, post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, (g.status, r)
        assert "одобрение не проверено" in r["reason"], r["reason"]


def test_R03b_get_raises():
    def boom(url, key, timeout):
        raise TimeoutError("read timed out")
    post = Post([OK_POST])
    r = send(get=boom, post=post)
    assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, r


def test_R03c_duplicates_and_incomplete():
    for body in (listing([item(), item()]), listing([item()], total=50), listing([item()], total="1")):
        post = Post([OK_POST])
        r = send(get=Get(200, body), post=post)
        if body.count('"name"') == 1 and '"total": "1"' in body:
            assert r["outcome"] == S.SENT, r            # строковый total, пара найдена — одобрен (не судим полноту)
            continue
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, (body, r)


def test_R03d_status_absent_or_null():
    for it in (item(drop=("status",)), item(status=None), item(status="  ")):
        post = Post([OK_POST])
        r = send(get=Get(200, listing([it])), post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, (it, r)


# ═══ R06 — параметр {{1}} ════════════════════════════════════════════════════════════════

def test_R06_param_shapes_refused_before_network():
    bad = ["", "   ", "a\nb", "a\rb", "a\tb", "a     b", "x" * 1025, "x" * 61, None, 123, b"bike"]
    for p in bad:
        g = Trap()
        r = send(params=[p], get=g, post=Trap())
        assert r["outcome"] == S.NOT_SENT and g.calls == 0, (repr(p)[:30], r)
    for ps in ([], ["a", "b"], "байка", ("байка",) * 2, {"1": "x"}):
        g = Trap()
        r = send(params=ps, get=g, post=Trap())
        assert r["outcome"] == S.NOT_SENT and g.calls == 0, (repr(ps)[:30], r)


def test_R06u_unicode_line_breaks_in_param():
    """Перевод строки НЕ только \\n: U+2028/U+2029/U+0085/\\v/\\f — тоже перевод строки для WhatsApp. Дверь их пропускает
    к сети. (Параметры сегодня — константы кода, поэтому это теоретическая дыра; отмечается.)"""
    leaked = []
    for p in ("a b", "a b", "a\u0085b", "a\x0bb", "a\x0cb"):
        g = Get(200, full())
        r = send(params=[p], get=g, post=Post([OK_POST]))
        if g.calls:
            leaked.append(repr(p))
    assert not leaked, "до сети дошли параметры с переводом строки: %s" % ", ".join(leaked)


def test_R06c_four_spaces_allowed_five_refused():
    g = Get(200, full())
    r = send(params=["a    b"], get=g, post=Post([OK_POST]))
    assert r["outcome"] == S.SENT, r
    g = Trap()
    r = send(params=["a     b"], get=g, post=Trap())
    assert r["outcome"] == S.NOT_SENT and g.calls == 0, r


# ═══ R07 — имя и язык, подмена ═══════════════════════════════════════════════════════════

def test_R07_name_lang_substitution_refused_before_network():
    for name, lang in (("reply_request ", "ru"), ("Reply_request", "ru"), ("promo_sale", "ru"),
                       ("reply_request\x00", "ru"), ("reply_request", "en_US"), ("reply_request", "RU"),
                       ("reply_request", ""), ("reply_request", None), (None, "ru"), (["reply_request"], "ru")):
        g = Trap()
        try:
            r = send(name=name, lang=lang, get=g, post=Trap())
        except TypeError as e:              # unhashable имя — дверь обязана не бросать
            raise AssertionError("дверь бросила на имени %r: %s" % (name, e))
        assert r["outcome"] == S.NOT_SENT and g.calls == 0, (name, lang, r)


# ═══ R08 — POST: таймаут, 5xx, 429 — повтор только заведомо не принятого ═════════════════

def test_R08_post_outcomes_no_blind_repeat():
    rows = [
        ([(None, "", "timeout")], S.UNKNOWN, 1),
        ([(None, "", "RemoteDisconnected")], S.UNKNOWN, 1),
        ([(500, "{}", None)], S.UNKNOWN, 1),
        ([(503, "{}", None)], S.UNKNOWN, 1),
        ([(200, '{"messages":[]}', None)], S.UNKNOWN, 1),
        ([(429, "{}", None), OK_POST], S.SENT, 2),
        ([(None, "", S.PRE_SEND + "gaierror"), OK_POST], S.SENT, 2),
        ([(400, '{"error":{"message":"(#131047) Re-engagement message","code":131047}}', None)], S.NOT_SENT, 1),
    ]
    for answers, want, n in rows:
        post = Post(answers)
        r = send(get=Get(200, full()), post=post)
        assert r["outcome"] == want and len(post.calls) == n, (answers, r, len(post.calls))


# ═══ R09 — бюджет съеден проверкой одобрения: POST не было, а исход «неизвестно» ═════════

def test_R09_budget_eaten_by_get_is_not_unknown():
    """Медленный GET списка (провайдер тянет ответ: таймаут urllib — на ОПЕРАЦИЮ сокета, не на весь ответ) съел общий
    бюджет. POST не делался ни разу (attempts=0, «к сети не обращались»). Исход обязан быть not_sent: клиенту заведомо
    ничего не ушло. Кандидат отдаёт unknown → ядро пишет unsure и шаблон по этому черновику (и клиенту до нового
    входящего) не уйдёт уже никогда — при том что не уходил ни разу."""
    t = [1000.0]

    def clock():
        return t[0]

    def slow():
        t[0] += 61.0                          # ответ списка пришёл через 61 с

    post = Post([OK_POST])
    r = send(get=Get(200, full(), on_call=slow), post=post, clock=clock)
    assert post.calls == [], post.calls
    assert r["attempts"] == 0, r
    assert r["outcome"] != S.UNKNOWN, ("POST не было ни одного, а исход «%s»: %s" % (r["outcome"], r["reason"]))


def test_R09b_get_leg_bounded():
    g = Get(200, full())
    send(get=g, post=Post([OK_POST]))
    assert g.timeouts and max(g.timeouts) <= S.LEG_TIMEOUT_SEC, g.timeouts


# ═══ R10 — выключатели ═══════════════════════════════════════════════════════════════════

def test_R10_flags_refuse_before_network():
    for e in (env(tpl=""), env(tpl="0"), env(tpl="off"), env(tpl="false"), env(tpl="2"),
              {"WA_SEND": "1", "WA_360_API_KEY": KEY}, env(send="0"), env(send=""), env(key=""),
              env(key="PLACEHOLDER"), env(key="CHANGE_ME_key")):
        g = Trap()
        r = send(get=g, post=Trap(), e=e)
        assert r["outcome"] == S.NOT_SENT and g.calls == 0, (e, r)
    g = Get(200, full())
    r = send(get=g, post=Post([OK_POST]), e=env(tpl=" ON "))
    assert r["outcome"] == S.SENT, r


def test_R10b_key_never_in_reason():
    secret = "SECRETKEYvalue_abcdef0123456789xyz"
    for g, p in ((Get(401, '{"meta":{"developer_message":"bad key %s"}}' % secret), Post([OK_POST])),
                 (Get(200, full()), Post([(400, '{"error":{"message":"x","code":1}}', None)]))):
        r = send(get=g, post=p, e=env(key=secret))
        blob = json.dumps(r, ensure_ascii=False)
        assert secret not in blob, "значение ключа попало в ответ двери (провайдер процитировал его): " + blob[:300]


# ═══ R11 — дверь шлёт шаблон любому номеру, окна и следа клиента не спрашивая ════════════

def test_R11_door_alone_cold_number():
    """Дверь сама по себе шлёт шаблон номеру, который НИКОГДА нам не писал (окна она не меряет по замыслу).
    Рубеж «только тем, кто писал» держит ЯДРО (template_offer: окно ИЗМЕРЕННО закрыто). Фиксируем факт: защита
    одной стороной, не двумя."""
    post = Post([OK_POST])
    r = S.send_template("66999999999", "reply_request", "ru", ["байка"], env=env(), get=Get(200, full()),
                        transport=post, sleep=lambda s: None)
    assert r["outcome"] == S.SENT and r["window"] == S.WINDOW_NOT_CHECKED, r


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
