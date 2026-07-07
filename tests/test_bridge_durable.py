"""DURABLE-слой bridge_client (фикс intermittent 404 Google, 07.07.2026, хвост §7).
Проверяет: (а) POST→302 → follow-redirect-as-GET, 404 echo-слоя ретраится GET'ом БЕЗ
повторного POST (write не дублируется); (б) серия сбоев read-запроса → backoff-ретрай,
успех со 2-й попытки, паузы экспоненциальные; (в) клин — 3 подряд транспорт-сбоя →
HTTP-сессия пересоздана; (г) unauthorized/«Invalid or missing token» на редиректе →
РОВНО одна пересылка запроса с токеном; (д) write-POST при транспорт-сбое НЕ ретраится
(один POST), идемпотентный POST — ретраится; бизнес-ошибка ok:false НЕ ретраится.
Сети нет: сессия подменена FakeSession."""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x/exec")
os.environ.setdefault("BRIDGE_TOKEN", "T")

import requests
import bridge_client
from bridge_client import BridgeClient

ECHO = "http://echo.googleusercontent.test/macros/echo?x=1"


class Resp:
    def __init__(self, status=200, payload=None, text="", location=None):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.headers = {"Location": location} if location else {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Скриптованная последовательность ответов; пишет журнал вызовов."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.closed = False

    def _next(self):
        assert self.script, "скрипт FakeSession исчерпан — лишний HTTP-вызов"
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._next()

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._next()

    def close(self):
        self.closed = True


def client(script):
    c = BridgeClient(url="http://x/exec", token="T", timeout=1)
    c.retry_base = 0.0      # паузы в тестах нулевые (сам факт вызова паузы ловим отдельно)
    c.retry_jitter = 0.0
    c._session = FakeSession(script)
    return c


def posts(c):
    return [x for x in c._session.calls if x[0] == "POST"]


def gets(c):
    return [x for x in c._session.calls if x[0] == "GET"]


def test_redirect_404_followed_as_get_without_repost():
    """(а) POST→302; echo-GET даёт 404, потом 200 — ответ достали, POST ушёл РОВНО один раз."""
    c = client([
        Resp(302, location=ECHO),
        Resp(404, text="Not Found (Google flaky)"),
        Resp(200, payload={"ok": True, "task": {"id": 7}}),
    ])
    r = c.claim_task(7)
    assert r.get("ok") and r["task"]["id"] == 7
    assert len(posts(c)) == 1, "write-POST продублирован!"
    g = gets(c)
    assert len(g) == 2 and all(x[1] == ECHO for x in g), "редирект не отработан GET'ами на Location"
    assert g[0][2].get("allow_redirects") is False
    print("OK (а): 404 на редиректе → follow-as-GET достаёт ответ, POST не дублируется")


def test_get_backoff_success_second_attempt():
    """(б) read-GET: сбой → backoff → успех со 2-й попытки; пауза экспоненциальная."""
    sleeps = []
    orig_sleep = bridge_client.time.sleep
    bridge_client.time.sleep = lambda s: sleeps.append(s)
    try:
        c = client([
            requests.exceptions.ConnectionError("boom"),
            Resp(200, payload={"ok": True, "pong": 1}),
        ])
        c.retry_base = 0.5
        r = c.ping()
        assert r.get("ok"), f"ретрай не вытащил ответ: {r}"
        assert len(gets(c)) == 2
        assert sleeps and abs(sleeps[0] - 0.5) < 1e-9, f"нет backoff-паузы: {sleeps}"
        # и экспонента: серия сбоев подряд → паузы растут
        c2 = client([
            requests.exceptions.ConnectionError("b1"),
            requests.exceptions.ConnectionError("b2"),
            Resp(200, payload={"ok": True}),
        ])
        c2.retry_base = 0.5
        sleeps.clear()
        assert c2.ping().get("ok")
        assert abs(sleeps[0] - 0.5) < 1e-9 and abs(sleeps[1] - 1.0) < 1e-9, f"паузы не экспоненциальные: {sleeps}"
    finally:
        bridge_client.time.sleep = orig_sleep
    print("OK (б): серия сбоев → backoff (0.5, 1.0), успех со 2-й попытки")


def test_wedge_recreates_session():
    """(в) 3 подряд транспорт-сбоя → сессия пересоздана (анти-клин), старая закрыта."""
    fake = FakeSession([
        requests.exceptions.ConnectionError("f1"),
        requests.exceptions.ConnectionError("f2"),
        requests.exceptions.ConnectionError("f3"),
    ])
    c = client([])
    c._session = fake
    for _ in range(3):
        r = c.complete_task(1, "done", "x")   # write → без полного ретрая, 1 сбой за вызов
        assert r.get("error") == "request_failed"
    assert c._session is not fake, "сессия НЕ пересоздана после 3 подряд сбоев"
    assert isinstance(c._session, requests.Session)
    assert fake.closed, "старая заклинившая сессия не закрыта"
    assert c._consec_transport_fails == 0
    # успех сбрасывает счётчик — 2 сбоя + успех + 2 сбоя НЕ пересоздают
    fake2 = FakeSession([
        requests.exceptions.ConnectionError("f1"),
        requests.exceptions.ConnectionError("f2"),
        Resp(200, payload={"ok": True}),
        requests.exceptions.ConnectionError("f3"),
        requests.exceptions.ConnectionError("f4"),
    ])
    c2 = client([])
    c2._session = fake2
    for _ in range(5):
        c2.complete_task(1, "done", "x")
    assert c2._session is fake2, "счётчик не сбросился на успехе"
    print("OK (в): клин (3 подряд request_failed) → HTTP-сессия пересоздана; успех сбрасывает счётчик")


def test_unauthorized_on_redirect_resends_token():
    """(г) echo-слой съел токен → unauthorized: запрос переслан заново С токеном, ровно 1 раз."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload={"ok": False, "error": "unauthorized",
                           "message": "Invalid or missing token"}),
        Resp(302, location=ECHO),
        Resp(200, payload={"ok": True, "id": 42}),
    ])
    r = c.enqueue_task("Filipp-328", "тест")
    assert r.get("ok") and r.get("id") == 42
    p = posts(c)
    assert len(p) == 2, "пересылка с токеном не случилась (или случилась не один раз)"
    for _, _, kw in p:
        assert kw["json"].get("token") == "T", "токен потерян при пересылке"
    print("OK (г): unauthorized на редиректе → токен переслан заново, ответ достали")


def test_unauthorized_persistent_no_loop():
    """(г2) unauthorized и на пересылке → отдаём ошибку, петли нет (ровно 2 отправки)."""
    bad = {"ok": False, "error": "unauthorized", "message": "Invalid or missing token"}
    c = client([
        Resp(302, location=ECHO), Resp(200, payload=dict(bad)),
        Resp(302, location=ECHO), Resp(200, payload=dict(bad)),
    ])
    r = c.enqueue_task("Filipp-328", "тест")
    assert not r.get("ok") and r.get("error") == "unauthorized"
    assert "_unauthorized" not in r, "служебный флаг утёк наружу"
    assert len(posts(c)) == 2
    print("OK (г2): постоянный unauthorized → 2 отправки максимум, честная ошибка")


def test_write_post_not_retried_idempotent_retried():
    """(границы) транспорт-сбой ДО ответа: write-POST один (дубль страшнее), read-POST ретраится."""
    c = client([requests.exceptions.ConnectionError("boom")])
    r = c.complete_task(5, "done", "res")
    assert r.get("error") == "request_failed"
    assert len(posts(c)) == 1, "write-POST отретраен — риск дубля записи!"
    c2 = client([
        requests.exceptions.ConnectionError("boom"),
        Resp(200, payload={"ok": True, "items": []}),
    ])
    r2 = c2.get_balance()
    assert r2.get("ok")
    assert len(posts(c2)) == 2, "идемпотентный POST не отретраен"
    print("OK (границы): write-POST без полного ретрая, идемпотентный — с ретраем")


def test_business_error_and_timeout_contract():
    """(контракт) ok:false бизнес-ошибка не ретраится и отдаётся как есть; timeout — прежняя ошибка."""
    c = client([Resp(200, payload={"ok": False, "error": "bike_not_resolved", "message": "нет"})])
    r = c.ping()
    assert r.get("error") == "bike_not_resolved" and len(c._session.calls) == 1
    c2 = client([requests.exceptions.Timeout("slow")] * 3)
    r2 = c2.ping()
    assert r2 == {"ok": False, "error": "timeout", "message": "Timeout >1s"}
    print("OK (контракт): бизнес-ошибка без ретрая; timeout-контракт прежний")


if __name__ == "__main__":
    test_redirect_404_followed_as_get_without_repost()
    test_get_backoff_success_second_attempt()
    test_wedge_recreates_session()
    test_unauthorized_on_redirect_resends_token()
    test_unauthorized_persistent_no_loop()
    test_write_post_not_retried_idempotent_retried()
    test_business_error_and_timeout_contract()
    print("ВСЕ ТЕСТЫ bridge_durable ПРОШЛИ")
