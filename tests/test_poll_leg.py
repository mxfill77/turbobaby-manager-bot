"""ПЛЕЧО ОПРОСА ОЧЕРЕДИ НЕ РУБИТ ЖИВОЙ ОТВЕТ, А МЁРТВЫЙ МОСТ НЕ ДЕРЖИТ ЗАХОД — замок (15.08.2026).

ОСНОВАНИЕ (splinter.log, 74.6 суток): 3863 таймаута плеча на action=get_pending (51.8/сут) при
живом мосте; 2524 лестницы со срубленной ПЕРВОЙ попыткой, у 2196 из них (87.0 %) ответ был ЖИВ и
дошёл повтором; 3618 лишних повторных исполнений чтения очереди и 1894 пропущенных тика опроса
(APScheduler держит max_instances=1 — пока job бежит, следующий тик отменяется).

ВЕЛИЧИНА ИЗ РАСПРЕДЕЛЕНИЯ. ОДИН И ТОТ ЖЕ вызов (6 статусов, lane=all) живёт в проде на ТРЁХ
плечах: 15с → 3863 из 82 887 = 4.66 % · 45с → 1 из 753 = 0.13 % · 60с (ТОТ ЖЕ опрос до 02.07.2026)
→ 64 из 23 332 = 0.27 % · 90с (демон) → ≤0.36 %. Укорочение 60→15 подняло долю В 17 РАЗ при
единственном различии — длине плеча. Масса лежит НИЖЕ 45с; сверху потолок ставит общий дедлайн
карточки «Инфо» (60с) — плечо обязано быть меньше него, иначе второй попытке не остаётся места.

ЗАМОК КРАСНЕЕТ В ОБЕ СТОРОНЫ:
  · МЕДЛЕННЫЙ, НО ЖИВОЙ ответ (25с) снова рубится — плечо укоротили либо бюджет съел попытку;
  · МЁРТВЫЙ мост держит заход дольше общего дедлайна — бюджет сняли, обошли или он не режет
    лестницы (три вложенные: 3 полные попытки × 6 хопов редиректа × 3 попытки эхо = 57 плеч).
Контрольные ветки («как было до правки») зелёные в ОБОИХ прогонах: они доказывают, что тест видит
разницу, а не зелен всегда.

ВРЕМЯ ВИРТУАЛЬНОЕ (приём tests/test_info_card_deadline.py): часы и sleep у `bridge_client`
подменяются, поэтому «уложились в бюджет» не зависит от нагрузки машины — иначе гейт давал бы
ложный красный.
"""
import os
import sys
import ast
import time as _real_time

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import requests
import card_deadline as CD
import bridge_client as BC
import devbot as D

REPO = "/root/turbobaby-manager-bot"
res = []


def ok(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    res.append(bool(cond))
    return bool(cond)


# ============================ ВИРТУАЛЬНЫЕ ЧАСЫ + МОСТ С ЗАДАННОЙ СКОРОСТЬЮ ============================
class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return _real_time.time()

    def sleep(self, sec):
        self.now += float(sec)


class Resp:
    def __init__(self, code, headers=None, payload=None):
        self.status_code = code
        self.headers = headers or {}
        self._payload = payload
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("нет тела")
        return self._payload


class Bridge:
    """Мост, который отвечает ЗА `answer_at` секунд. Плечо, которому дали меньше, — честный
    Timeout ровно на выданном ему бюджете: так ведёт себя requests, и так рубится живой ответ.
    `answer_at=None` — мост не отвечает вовсе (лёг)."""

    def __init__(self, clock, answer_at=25.0, echo_sec=1.0):
        self.clock = clock
        self.answer_at = answer_at
        self.echo_sec = echo_sec
        self.legs = []

    def _leg(self, url, timeout, cost):
        budget = float(timeout)
        if cost is None or cost > budget:          # ответ не успел в выданное плечо
            self.clock.now += budget
            self.legs.append({"url": str(url), "timeout": budget, "sec": budget, "cut": True})
            raise requests.exceptions.Timeout("плечо истекло")
        self.clock.now += cost
        self.legs.append({"url": str(url), "timeout": budget, "sec": cost, "cut": False})

    def get(self, url, **kw):
        if "googleusercontent" in str(url):        # эхо-слой: забрать ГОТОВЫЙ ответ, он дешёвый
            self._leg(url, kw.get("timeout", 60), self.echo_sec)
            return Resp(200, payload={"ok": True, "items": [
                {"id": 7, "status": "done", "from": "Filipp-328-dev", "result": "ok"}],
                "statuses": "done"})
        self._leg(url, kw.get("timeout", 60), self.answer_at)   # /exec: тут исполняется Apps Script
        return Resp(302, headers={"Location": "https://googleusercontent.com/echo"})

    def post(self, url, **kw):
        self._leg(url, kw.get("timeout", 60), self.answer_at)
        return Resp(302, headers={"Location": "https://googleusercontent.com/echo"})

    def close(self):
        pass


def poll(answer_at, leg, budget):
    """Живой `devbot._poll_queue_sync` на подменённых часах. → (снимок, потрачено, плечи)."""
    clock = Clock()
    old_time, old_leg, old_budget = BC.time, D.POLL_TIMEOUT, D.POLL_BUDGET
    BC.time = clock
    D.POLL_TIMEOUT, D.POLL_BUDGET = leg, budget
    try:
        client = BC.BridgeClient(url="http://x", token="t", timeout=leg)
        sess = Bridge(clock, answer_at)
        client._session = sess
        client._new_session = lambda: None      # анти-клин не подсовывает живую сессию
        t0 = clock.now
        by = D._poll_queue_sync(client)
        return by, clock.now - t0, sess.legs
    finally:
        BC.time = old_time
        D.POLL_TIMEOUT, D.POLL_BUDGET = old_leg, old_budget


# ============================ (1) ВЕЛИЧИНЫ: ГРАНИЦЫ, А НЕ ВКУС ============================
print("(1) константы опроса против общего дедлайна карточки")

ok(D.POLL_TIMEOUT > 15,
   f"плечо опроса поднято над прежними 15 с (сейчас {D.POLL_TIMEOUT} с) — живой ответ не рубится")
ok(D.POLL_TIMEOUT <= CD.BUDGET_DEFAULT,
   f"плечо {D.POLL_TIMEOUT} с НЕ перерастает общий дедлайн карточки {CD.BUDGET_DEFAULT:g} с")
ok(D.POLL_BUDGET <= CD.BUDGET_DEFAULT,
   f"общий бюджет опроса {D.POLL_BUDGET} с не выше дедлайна карточки — потолок достижим")
ok(D.POLL_TIMEOUT < D.POLL_BUDGET,
   "плечо СТРОГО меньше бюджета — второй попытке остаётся место (её и спасают транспорт-сбои)")
ok(D.POLL_BUDGET > 45,
   "бюджет длиннее тика опроса (45 с) — иначе одна попытка и лестницы нет вовсе")

src = open(os.path.join(REPO, "devbot.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = [n for n in ast.walk(tree)
      if isinstance(n, ast.FunctionDef) and n.name == "_poll_queue_sync"]
ok(len(fn) == 1 and any(isinstance(n, ast.With) for n in ast.walk(fn[0])),
   "опрос ОТКРЫВАЕТ общий бюджет (снимут — здесь красное)")
ok(len(fn) == 1 and "card_budget" in {getattr(a, "attr", "") for a in ast.walk(fn[0])
                                      if isinstance(a, ast.Attribute)},
   "бюджет открыт ТОЙ ЖЕ дверью, что у карточки — второй реализации потолка не заводим")

# ============================ (2) ЖИВОЙ, НО МЕДЛЕННЫЙ ОТВЕТ — ДОЖИДАЕТСЯ ============================
print("\n(2) мост отвечает за 25 с (живой, но медленный)")

by, spent, legs = poll(answer_at=25.0, leg=D.POLL_TIMEOUT, budget=D.POLL_BUDGET)
ok(by is not None, "снимок очереди ПОЛУЧЕН — плечо дождалось живого ответа")
ok(by is not None and [i["id"] for i in by.get("done", [])] == [7],
   "в снимке та самая строка очереди (ответ не потерян по дороге)")
ok(len([l for l in legs if l["cut"]]) == 0,
   "ни одного срубленного плеча — повторного исполнения чтения очереди мост не платит")
ok(spent < D.POLL_BUDGET, f"уложились в бюджет ({spent:.1f} с из {D.POLL_BUDGET} с)")

# КОНТРОЛЬ: то же самое прежним плечом 15 с — ответ срублен (тест видит разницу)
by15, spent15, legs15 = poll(answer_at=25.0, leg=15, budget=D.POLL_BUDGET)
ok(by15 is None,
   "КОНТРОЛЬ: прежнее плечо 15 с тот же живой ответ РУБИТ — снимка нет (это и есть класс)")
ok(len([l for l in legs15 if l["cut"]]) >= 2,
   f"КОНТРОЛЬ: прежнее плечо жжёт повторы ({len([l for l in legs15 if l['cut']])} срубленных плеч)")

# ============================ (3) МЁРТВЫЙ МОСТ НЕ ДЕРЖИТ ЗАХОД ============================
print("\n(3) мост не отвечает вовсе")

by_d, spent_d, legs_d = poll(answer_at=None, leg=D.POLL_TIMEOUT, budget=D.POLL_BUDGET)
ok(by_d is None,
   "снимка нет → None, то есть «не прочитал». Пустой снимок devbot прочёл бы как «задач нет»")
ok(spent_d <= D.POLL_BUDGET + CD.LEG_MIN,
   f"заход уложен в общий дедлайн: {spent_d:.1f} с при бюджете {D.POLL_BUDGET} с")

# КОНТРОЛЬ: без бюджета тот же мёртвый мост держит job кратно дольше
by_off, spent_off, legs_off = poll(answer_at=None, leg=D.POLL_TIMEOUT, budget=0)
ok(by_off is None, "КОНТРОЛЬ: при откате (бюджет 0) исход тот же — None")
ok(spent_off > D.POLL_BUDGET,
   f"КОНТРОЛЬ: без бюджета заход длиннее потолка ({spent_off:.1f} с) — бюджет реально режет")
ok(spent_d < spent_off,
   f"с бюджетом заход короче ({spent_d:.1f} с против {spent_off:.1f} с)")

# ЛЕСТНИЦА ЭХО-СЛОЯ (окно деградации: /exec отвечает 302, эхо не отдаёт ответ) — тоже под потолком
class SickEcho(Bridge):
    def get(self, url, **kw):
        if "googleusercontent" in str(url):
            self._leg(url, kw.get("timeout", 60), None)      # эхо молчит: 57-плечевой путь
        return super().get(url, **kw)


def poll_sick(leg, budget):
    clock = Clock()
    old_time, old_leg, old_budget = BC.time, D.POLL_TIMEOUT, D.POLL_BUDGET
    BC.time = clock
    D.POLL_TIMEOUT, D.POLL_BUDGET = leg, budget
    try:
        client = BC.BridgeClient(url="http://x", token="t", timeout=leg)
        sess = SickEcho(clock, 2.0)
        client._session = sess
        client._new_session = lambda: None
        t0 = clock.now
        by = D._poll_queue_sync(client)
        return by, clock.now - t0, sess.legs
    finally:
        BC.time = old_time
        D.POLL_TIMEOUT, D.POLL_BUDGET = old_leg, old_budget


by_s, spent_s, legs_s = poll_sick(D.POLL_TIMEOUT, D.POLL_BUDGET)
ok(spent_s <= D.POLL_BUDGET + CD.LEG_MIN,
   f"лестница эхо-слоя тоже под потолком: {spent_s:.1f} с при бюджете {D.POLL_BUDGET} с")
by_s0, spent_s0, legs_s0 = poll_sick(D.POLL_TIMEOUT, 0)
ok(spent_s0 > spent_s,
   f"КОНТРОЛЬ: без бюджета та же лестница жжёт больше ({spent_s0:.1f} с против {spent_s:.1f} с)")
ok(len(legs_s0) > len(legs_s),
   f"КОНТРОЛЬ: и плеч больше ({len(legs_s0)} против {len(legs_s)}) — режется ЧИСЛО плеч")

# ============================ (4) ГРАНИЦЫ: КАРТОЧКА НЕ ТРОНУТА ============================
print("\n(4) границы — карточка «Инфо» и прочие потребители моста")

ok(CD.BUDGET_DEFAULT == 60.0, "дедлайн карточки не изменён (60 с)")
with BC.card_budget(60) as cb:
    ok(cb.label == "карточки",
       "умолчание метки — «карточки»: строки журнала у пути карточки байт-в-байт прежние")
with BC.card_budget(D.POLL_BUDGET, label="опроса очереди") as cb2:
    ok(cb2.label == "опроса очереди",
       "заход опроса называет СЕБЯ — журнал не врёт про карточку там, где карточки нет")
ok(BC.current_card_budget() is None,
   "по выходе бюджет снят — опрос не течёт в соседние заходы (ContextVar, не поле клиента)")

ok(BC.BridgeClient(url="http://x", token="t").timeout == 60,
   "главный клиент моста НЕ тронут — у него прежние 60 с")
ok(D.POLL_TIMEOUT != 60,
   "у опроса СВОЁ плечо: он идёт отдельным клиентом, а не главным (event loop не морозим)")

D._poll_bridge = D._poll_bridge_for = None
D.BRIDGE = BC.BridgeClient(url="http://x", token="t")
pb = D._get_poll_bridge()
ok(getattr(pb, "timeout", None) == D.POLL_TIMEOUT,
   f"ленивый клиент опроса собран с плечом {D.POLL_TIMEOUT} с")
D._poll_bridge = D._poll_bridge_for = D.BRIDGE = None

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})",
      f"— {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
