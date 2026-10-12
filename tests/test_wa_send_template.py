#!/usr/bin/env python3
"""NIGHT0710-B3g: дверь шаблонов `wa_send.send_template`. Ровно три имени (решение владельца 02.10, WATEMPLATES0210),
языки ru/en, число и форма переменных, своя ручка WA_AGENT_TEMPLATES поверх WA_SEND, одобрение у Meta — по ОТВЕТУ
ПРОВАЙДЕРА (`GET /v1/configs/templates`, три исхода), отправка — тот же `_send_loop` и те же три исхода.

СЕТИ НЕТ: швы `_get`/`_post` подменены подделкой либо ловушкой (роняет тест при первом касании), а
`urllib.request.urlopen` — ловушкой на весь прогон. Живая форма списка — `tmp/wa_tpl_0210/server_outputs_1914.txt`
(WATEMPLATES0210 §2): waba_templates + count/total, status строчными, category прописными.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])
os.environ["PRETOOL_NOPUSH"] = "1"


def _no_net(*a, **kw):
    raise AssertionError("тест обратился к сети")


urllib.request.urlopen = _no_net

import wa_send as S  # noqa: E402

NUM = "66812345678"
KEY = "real_key_abcdef0123456789"
SECRET = "SECRETKEYvalue_abcdef0123456789xyz"
NAMES = ("payment_reminder", "rental_end_reminder", "reply_request")


def env(send="1", tpl="1", key=KEY):
    return {"WA_SEND": send, "WA_AGENT_TEMPLATES": tpl, "WA_360_API_KEY": key}


class Trap:
    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise AssertionError("к сети обратились там, где нельзя")


class Get:
    def __init__(self, status=200, body="", err=None):
        self.status, self.body, self.err, self.calls, self.keys = status, body, err, [], []

    def __call__(self, url, key, timeout):
        self.calls.append(url)
        self.keys.append(key)
        return self.status, self.body, self.err


class Post:
    def __init__(self, answers):
        self.answers, self.calls, self.keys = list(answers), [], []

    def __call__(self, url, payload, key, timeout):
        self.calls.append({"url": url, "payload": payload})
        self.keys.append(key)
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def tpl(name="reply_request", lang="ru", status="approved", category="UTILITY", reason=None):
    return {"name": name, "language": lang, "status": status, "category": category, "rejected_reason": reason,
            "id": "id_%s_%s" % (name, lang)}


def listing(items, total=None, form="waba_templates"):
    body = {form: items, "count": len(items)}
    if total is not False:
        body["total"] = len(items) if total is None else total
    return json.dumps(body)


def full(status="approved", category="UTILITY", reason=None, only=None):
    """Все шесть поданных пар; only — (имя, язык), у которой свой статус, остальные pending."""
    out = []
    for n in NAMES:
        for lg in ("ru", "en"):
            if only is None or (n, lg) == only:
                out.append(tpl(n, lg, status, category, reason))
            else:
                out.append(tpl(n, lg, "pending"))
    return listing(out)


LIVE_0110 = full("pending")          # живое чтение 01.10 19:32 UTC: все шесть pending (WATEMPLATES0210 §2)
OK_POST = (200, '{"messages":[{"id":"wamid.T1"}]}', None)


def send(name="reply_request", lang="ru", params=("байка",), get=None, post=None, e=None, to=NUM):
    return S.send_template(to, name, lang, list(params) if isinstance(params, tuple) else params,
                           env=e or env(), get=get or Trap(), transport=post or Trap(), sleep=lambda s: None)


# ═══ (1) список и тексты ═══════════════════════════════════════════════════════════════

def test_names_exactly_three_langs_params():
    assert tuple(sorted(S.TEMPLATE_PARAMS)) == NAMES, S.TEMPLATE_PARAMS
    assert S.TEMPLATE_PARAMS == {"rental_end_reminder": 2, "payment_reminder": 1, "reply_request": 1}
    assert S.TEMPLATE_LANGS == ("ru", "en")
    assert set(S.TEMPLATE_TEXTS) == {(n, lg) for n in NAMES for lg in ("ru", "en")}
    for (n, lg), text in S.TEMPLATE_TEXTS.items():
        want = S.TEMPLATE_PARAMS[n]
        assert all("{{%d}}" % i in text for i in range(1, want + 1)) and "{{%d}}" % (want + 1) not in text, (n, lg)


def test_texts_verbatim_watemplates():
    assert S.TEMPLATE_TEXTS[("reply_request", "ru")] == ("Здравствуйте! Это TurboBaby. У нас вопрос по аренде {{1}}. "
                                                         "Ответьте, пожалуйста, на это сообщение, когда будет удобно.")
    assert S.TEMPLATE_TEXTS[("reply_request", "en")] == ("Hello, this is TurboBaby! We have a question about your {{1}} "
                                                         "rental. Please reply to this message whenever it is convenient.")
    assert S.template_text("reply_request", "ru", ["байка"]).count("байка") == 1
    assert S.template_text("rental_end_reminder", "en", ["XMAX 300", "October 5"]) == (
        "Hello, this is TurboBaby! Your XMAX 300 rental ends on October 5. Would you like to extend it or return "
        "the bike? Just reply to this message.")
    assert S.template_text("marketing", "ru", ["x"]) is None


def test_flag_default_off():
    assert S.TEMPLATES_FLAG == "WA_AGENT_TEMPLATES"
    assert S.templates_enabled({}) is False and S.templates_enabled({"WA_AGENT_TEMPLATES": "0"}) is False
    assert S.templates_enabled({"WA_AGENT_TEMPLATES": "yes_please"}) is False
    assert S.templates_enabled({"WA_AGENT_TEMPLATES": "1"}) is True


# ═══ (2) отказы ДО сети: ни GET, ни POST ═════════════════════════════════════════════════

def test_refusals_before_network():
    cases = [
        ({"e": env(send="0")}, "WA_SEND"),
        ({"e": env(tpl="0")}, "шаблоны выключены"),
        ({"e": {"WA_SEND": "1", "WA_360_API_KEY": KEY}}, "шаблоны выключены"),
        ({"e": env(key="PLACEHOLDER")}, "ключ"),
        ({"name": "Reply_request"}, "вне разрешённых"),
        ({"name": " reply_request"}, "вне разрешённых"),
        ({"name": "promo_sale"}, "вне разрешённых"),
        ({"lang": "en_US"}, "только ru и en"),
        ({"lang": "th"}, "только ru и en"),
        ({"lang": None}, "только ru и en"),
        ({"params": ()}, "переменных 1, передано 0"),
        ({"params": ("байка", "лишний")}, "передано 2"),
        ({"params": ("",)}, "пустая"),
        ({"params": ("   ",)}, "пустая"),
        ({"params": ("XMAX\n300",)}, "переводом строки"),
        ({"params": ("a\tb",)}, "табуляцией"),
        ({"params": ("a     b",)}, "пятью пробелами"),
        ({"params": ("x" * 61,)}, "длиннее"),
        ({"params": "байка"}, "не списком"),
        ({"name": "rental_end_reminder", "params": ("XMAX",)}, "переменных 2, передано 1"),
        ({"to": ""}, "номер"),
    ]
    for kw, want in cases:
        g, p = Trap(), Trap()
        r = send(get=g, post=p, **kw)
        assert r["outcome"] == S.NOT_SENT and g.calls == 0 and p.calls == 0, (kw, r)
        assert want in r["reason"], (kw, r["reason"])
        assert r["window"] != S.WINDOW_CLOSED, r


# ═══ (3) одобрение — по ответу провайдера ═══════════════════════════════════════════════

def test_approval_table():
    rows = [
        (full("approved", only=("reply_request", "ru")), S.TPL_APPROVED, "approved"),
        (full("APPROVED", only=("reply_request", "ru")), S.TPL_APPROVED, "approved"),
        (LIVE_0110, S.TPL_NOT_APPROVED, "статус pending"),
        (full("REJECTED", reason="INVALID_FORMAT", only=("reply_request", "ru")), S.TPL_NOT_APPROVED,
         "причина: INVALID_FORMAT"),
        (full("paused", only=("reply_request", "ru")), S.TPL_NOT_APPROVED, "статус paused"),
        (full("disabled", only=("reply_request", "ru")), S.TPL_NOT_APPROVED, "статус disabled"),
        (full("in_appeal", only=("reply_request", "ru")), S.TPL_NOT_APPROVED, "статус in_appeal"),
        (full("approved", "MARKETING", only=("reply_request", "ru")), S.TPL_NOT_APPROVED, "MARKETING"),
        (listing([tpl("reply_request", "en")]), S.TPL_NOT_APPROVED, "у провайдера нет"),
        (listing([tpl("reply_request", "en")], total=False), S.TPL_UNKNOWN, "полнота списка не названа"),
        (listing([tpl()], total=7), S.TPL_UNKNOWN, "неполный (1 из 7)"),
        (listing([tpl(), tpl()]), S.TPL_UNKNOWN, "2 раз"),
        (listing([tpl(status="")]), S.TPL_UNKNOWN, "статус шаблона"),
        (listing([tpl()], form="data"), S.TPL_APPROVED, "approved"),
        ("<html>oops</html>", S.TPL_UNKNOWN, "не JSON"),
        ("[1,2]", S.TPL_UNKNOWN, "не объект"),
        ('{"count": 0}', S.TPL_UNKNOWN, "нет списка"),
    ]
    for body, want, words in rows:
        got, why = S.template_approval(body, "reply_request", "ru")
        assert got == want and words in why, (body[:80], got, why)


def test_send_only_on_approved():
    get, post = Get(200, full("approved", only=("reply_request", "ru"))), Post([OK_POST])
    r = send(get=get, post=post)
    assert r["outcome"] == S.SENT and r["wamid"] == "wamid.T1" and r["approval"] == S.TPL_APPROVED, r
    assert len(get.calls) == 1 and S.TEMPLATES_PATH in get.calls[0] and len(post.calls) == 1, (get.calls, post.calls)
    body = post.calls[0]["payload"]
    assert body == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": NUM, "type": "template",
                    "template": {"name": "reply_request", "language": {"code": "ru"},
                                 "components": [{"type": "body",
                                                 "parameters": [{"type": "text", "text": "байка"}]}]}}, body
    assert post.calls[0]["url"] == S.API_BASE + S.SEND_PATH
    assert get.keys == [KEY] and post.keys == [KEY]
    assert r["text"] == S.template_text("reply_request", "ru", ["байка"]) and r["window"] == S.WINDOW_NOT_CHECKED


def test_not_approved_no_post_words():
    for body, words in ((LIVE_0110, "статус pending"),
                        (full("rejected", reason="TAG_CONTENT_MISMATCH", only=("reply_request", "ru")),
                         "TAG_CONTENT_MISMATCH"),
                        (full("approved", "MARKETING", only=("reply_request", "ru")), "MARKETING")):
        post = Post([OK_POST])
        r = send(get=Get(200, body), post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and words in r["reason"], r
        assert r["approval"] == S.TPL_NOT_APPROVED and r["verify"] is False and r["window"] != S.WINDOW_CLOSED, r


def test_unread_list_is_unknown_no_post():
    cases = [(Get(500, '{"error":{"message":"boom"}}'), "500"),
             (Get(401, '{"meta":{"success":false,"http_code":401,"developer_message":"Invalid api key"}}'),
              "Invalid api key"),
             (Get(None, "", "URLError"), "не прочитан"),
             (Get("x", ""), "код ответа"),
             (Get(200, "not json"), "не JSON")]
    for get, words in cases:
        post = Post([OK_POST])
        r = send(get=get, post=post)
        assert r["outcome"] == S.NOT_SENT and post.calls == [] and r["approval"] == S.TPL_UNKNOWN, r
        assert words in r["reason"] and "одобрение не проверено" in r["reason"], r["reason"]


def test_get_exception_and_budget():
    def boom(url, key, timeout):
        raise OSError("x")
    post = Post([OK_POST])
    r = send(get=boom, post=post)
    assert r["outcome"] == S.NOT_SENT and r["approval"] == S.TPL_UNKNOWN and post.calls == [], r
    g = Trap()
    r = S.send_template(NUM, "reply_request", "ru", ["байка"], env=env(), get=g, transport=Trap(), budget=0.0)
    assert g.calls == 0 and r["approval"] == S.TPL_UNKNOWN and "бюджет" in r["reason"], r


# ═══ (4) ответы POST — те же три исхода, без слепого повтора ═══════════════════════════════

def test_post_outcomes():
    ok_get = full("approved", only=("reply_request", "ru"))
    graph = json.dumps({"error": {"message": "(#132001) Template name does not exist in the translation",
                                  "type": "OAuthException", "code": 132001,
                                  "error_data": {"details": "template name (reply_request) does not exist in ru"}}})
    rows = [
        ([(400, graph, None)], S.NOT_SENT, 1, "код Meta 132001"),
        ([(500, "{}", None)], S.UNKNOWN, 1, "500"),
        ([(None, "", "timeout")], S.UNKNOWN, 1, "транспорт молчит"),
        ([(200, "{}", None)], S.UNKNOWN, 1, "идентификатора"),
        ([(429, "{}", None), OK_POST], S.SENT, 2, "принято"),
    ]
    for answers, want, n, words in rows:
        post = Post(answers)
        r = send(get=Get(200, ok_get), post=post)
        assert r["outcome"] == want and len(post.calls) == n and words in r["reason"], (answers[0][:2], r)
        assert r["verify"] is (want == S.UNKNOWN)
    post = Post([(400, graph, None)])
    r = send(get=Get(200, ok_get), post=post)
    assert "does not exist in ru" in r["reason"], r["reason"]


# ═══ (5) ключ не течёт; окно не «закрыто» ═════════════════════════════════════════════

def test_key_never_in_words():
    for get in (Get(200, LIVE_0110), Get(500, "{}"), Get(None, "", "URLError"),
                Get(200, full("approved", only=("reply_request", "ru")))):
        r = send(get=get, post=Post([(400, '{"error":{"message":"bad"}}', None)]), e=env(key=SECRET))
        blob = json.dumps(r, ensure_ascii=False)
        assert SECRET not in blob and SECRET[:12] not in blob, blob


# ═══ (6) границы: текст прежний, сеть одна ════════════════════════════════════════════

def test_boundaries_text_path_unchanged():
    src = open(S.__file__, encoding="utf-8").read()
    assert src.count("urlopen") == 1, "выход в сеть — ровно один `_open`"
    assert set(S._out(S.SENT, "x")) == {"outcome", "reason", "wamid", "window", "attempts", "verify"}
    assert S.build_payload(NUM, "привет")["type"] == "text"


def test_get_goes_through_open():
    seen = []
    real = S._open

    def fake_open(req, timeout):
        seen.append((req.get_method(), req.full_url, req.get_header("D360-api-key")))
        if req.get_method() == "GET":
            return 200, full("approved", only=("reply_request", "ru")), None
        return OK_POST
    S._open = fake_open
    try:
        r = S.send_template(NUM, "reply_request", "ru", ["байка"], env=env(), sleep=lambda s: None)
    finally:
        S._open = real
    assert r["outcome"] == S.SENT, r
    assert [m for m, _u, _k in seen] == ["GET", "POST"], seen
    assert seen[0][1] == "%s%s?limit=%d" % (S.API_BASE, S.TEMPLATES_PATH, S.TEMPLATES_LIMIT), seen
    assert seen[0][2] == KEY and seen[1][1] == S.API_BASE + S.SEND_PATH, seen


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
