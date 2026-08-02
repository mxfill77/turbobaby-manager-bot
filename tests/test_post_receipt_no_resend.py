"""ОТКАЗ РАСПИСКИ НА WRITE-POST НЕ ЛЕЧИТСЯ ПЕРЕСЫЛКОЙ (класс, 02.08.2026).

ОПРОВЕРГНУТАЯ ПОСЫЛКА. Докстринг `_durable_request` обосновывал пересылку так:
«Bridge проверяет токен ДО исполнения действия, значит запрос НЕ исполнен». Замер с
ПК-полосы (артефакт 2026-08-02-bridge-receipt-leg-not-token.md) это опроверг: write_doc
ИСПОЛНИЛСЯ, а расписка пришла отказом doGet — POST по цепочке 302 стал голым GET без
тела, и мост честно ответил «токена нет». Отпечаток плеча виден в ИСХОДНИКЕ прода:
  · Bridge.js:28-32  doGet  → {ok:false, error:'unauthorized', message:'Invalid or missing token'}
  · Bridge.js:234    doPost → {ok:false, error:'unauthorized'}          ← message'а НЕТ
Значит расписка с полем message пришла от doGet, а не от doPost: плечо POST'а к этому
моменту уже отработало. Пересылка в таком отказе кладёт ВТОРУЮ запись — для кассы
(addTransaction → appendRow, BotData.js:479) это дубль проводки.

ЧТО ПРОВЕРЯЕМ (красный до правки, зелёный после):
 (1) write-POST + отказ расписки → РОВНО ОДНА отправка, наружу «исход неизвестен»;
 (2) деньги (add_transaction) — вторая проводка не рождается;
 (3) успешный write-POST работает как прежде;
 (4) GET-повтор НЕ ослаблен — чтение идемпотентно, пересылка сохранена;
 (5) идемпотентный POST (объявлен безопасным для полного повтора) — пересылка сохранена;
 (6) постоянный отказ на GET — максимум 2 отправки, петли нет;
 (7) в ответе назван объект решения: какое плечо ответило и что делать дальше.
Сети нет: сессия подменена FakeSession.
"""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ["BRIDGE_ALLOW_FIXTURES"] = "1"   # транспорт-тест на фейковом URL (класс 193)
os.environ.setdefault("BRIDGE_URL", "http://x/exec")
os.environ.setdefault("BRIDGE_TOKEN", "T")

from bridge_client import BridgeClient   # noqa: E402

ECHO = "http://echo.googleusercontent.test/macros/echo?x=1"

# Расписка ровно того вида, что пришла живьём (splinter.log 01.08.2026 07:24:44 и ещё 13 раз
# за семь суток): тело от doGet — есть message. Это отпечаток «плечо POST уже отработало».
DOGET_REFUSAL = {"ok": False, "error": "unauthorized", "message": "Invalid or missing token"}


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
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.closed = False

    def _next(self):
        assert self.script, "скрипт FakeSession исчерпан — лишний HTTP-вызов (пересылка?)"
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
    c.retry_base = 0.0
    c.retry_jitter = 0.0
    c._session = FakeSession(script)
    return c


def posts(c):
    return [x for x in c._session.calls if x[0] == "POST"]


def gets(c):
    return [x for x in c._session.calls if x[0] == "GET"]


def test_write_post_receipt_refusal_not_resent():
    """(1) write-POST: расписка = отказ doGet → одна отправка, наружу «исход неизвестен»."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload=dict(DOGET_REFUSAL)),
        # третьего ответа в скрипте НЕТ намеренно: пересылка упрётся в «скрипт исчерпан»
    ])
    r = c.enqueue_task("Filipp-328", "живая задача владельца")
    assert len(posts(c)) == 1, "write-POST переслан по отказу расписки — риск ВТОРОЙ записи!"
    assert not r.get("ok")
    assert r.get("outcome") == "unknown", f"исход не назван неизвестным: {r}"
    assert "_unauthorized" not in r, "служебный флаг утёк наружу"
    print("OK (1): отказ расписки на write-POST → одна отправка, исход назван неизвестным")


def test_money_write_not_doubled():
    """(2) касса: add_transaction с отказом расписки НЕ рождает вторую проводку."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload=dict(DOGET_REFUSAL)),
    ])
    c._blackbox_log = lambda *a, **k: None    # чёрный ящик тут не при чём — меряем сам POST
    r = c.add_transaction(wallet="Наличка", amount=-800, currency="THB")
    assert len(posts(c)) == 1, "ПРОВОДКА ОТПРАВЛЕНА ДВАЖДЫ — дубль в кассе!"
    assert not r.get("ok") and r.get("outcome") == "unknown"
    print("OK (2): деньги — вторая проводка не рождается")


def test_successful_write_post_unchanged():
    """(3) успешный write-POST — как прежде: один POST, ответ наружу целиком."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload={"ok": True, "id": 42}),
    ])
    r = c.enqueue_task("Filipp-328", "живая задача владельца")
    assert r.get("ok") and r.get("id") == 42, f"успешный путь сломан: {r}"
    assert len(posts(c)) == 1 and len(gets(c)) == 1
    print("OK (3): успешный write-POST работает как прежде")


def test_get_resend_preserved():
    """(4) GET: чтение идемпотентно — пересылка с токеном сохранена (не ослаблять)."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload=dict(DOGET_REFUSAL)),
        Resp(200, payload={"ok": True, "version": "1.0.0"}),
    ])
    r = c.ping()
    assert r.get("ok"), f"GET-повтор ослаблен: {r}"
    g = gets(c)
    assert len(g) == 3, f"GET переслан не один раз: {len(g)}"
    assert g[0][2]["params"].get("token") == "T" and g[2][2]["params"].get("token") == "T"
    print("OK (4): GET-повтор не ослаблен — токен переслан, ответ достали")


def test_idempotent_post_resend_preserved():
    """(5) идемпотентный POST (объявлен безопасным для полного повтора) — пересылка сохранена."""
    c = client([
        Resp(200, payload=dict(DOGET_REFUSAL)),
        Resp(200, payload={"ok": True, "items": []}),
    ])
    r = c.get_balance()
    assert r.get("ok"), f"идемпотентный POST не переслан: {r}"
    assert len(posts(c)) == 2
    for _, _, kw in posts(c):
        assert kw["json"].get("token") == "T", "токен потерян при пересылке"
    print("OK (5): идемпотентный POST — пересылка сохранена")


def test_persistent_refusal_no_loop_on_get():
    """(6) отказ и на пересылке (GET) → максимум 2 отправки, петли нет, ошибка честная."""
    c = client([
        Resp(200, payload=dict(DOGET_REFUSAL)),
        Resp(200, payload=dict(DOGET_REFUSAL)),
    ])
    r = c.ping()
    assert not r.get("ok") and r.get("error") == "unauthorized"
    assert len(gets(c)) == 2, "петля пересылок"
    assert "_unauthorized" not in r
    print("OK (6): постоянный отказ на GET → 2 отправки максимум")


def test_answer_names_the_leg_and_the_next_step():
    """(7) ответ называет плечо расписки и следующий шаг — перечитать факт, не повторять."""
    c = client([
        Resp(302, location=ECHO),
        Resp(200, payload=dict(DOGET_REFUSAL)),
    ])
    c._blackbox_log = lambda *a, **k: None
    r = c.add_event(kind="ТО", text="проба")
    msg = str(r.get("message") or "")
    assert "doGet" in msg, f"плечо расписки не названо: {msg}"
    assert "перечита" in msg.lower(), f"следующий шаг не назван: {msg}"
    assert r.get("bridge_error") == "unauthorized", "исходный отказ моста потерян"
    # а вот отказ БЕЗ message (плечо doPost, Bridge.js:234) — тоже без пересылки:
    c2 = client([Resp(302, location=ECHO), Resp(200, payload={"ok": False, "error": "unauthorized"})])
    c2._blackbox_log = lambda *a, **k: None
    r2 = c2.add_event(kind="ТО", text="проба")
    assert len(posts(c2)) == 1, "write-POST переслан на отказе без message"
    assert r2.get("outcome") == "unknown"
    print("OK (7): назван объект решения — плечо расписки и «перечитай факт»")


if __name__ == "__main__":
    test_write_post_receipt_refusal_not_resent()
    test_money_write_not_doubled()
    test_successful_write_post_unchanged()
    test_get_resend_preserved()
    test_idempotent_post_resend_preserved()
    test_persistent_refusal_no_loop_on_get()
    test_answer_names_the_leg_and_the_next_step()
    print("ВСЕ ТЕСТЫ post_receipt_no_resend ПРОШЛИ")
