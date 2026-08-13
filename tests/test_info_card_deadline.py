"""ОБЩИЙ ДЕДЛАЙН СБОРКИ КАРТОЧКИ «Инфо» — замок (13.08.2026).

Основание — замер 06:53 (5 прогонов живого пути): 11.0 / медиана 37.9 / max 407.7 с, 103 HTTP-плеча,
из них 51 лишнее, 405.5 с из 578.2 (70.1 %) сгорело в повторах. Настоящих таймаутов ноль: потолка
у ВСЕЙ карточки не было вовсе — три вложенные лестницы (3 полные попытки × 6 хопов × 3 эхо = 57
плеч на действие × 60 с × 5 действий) давали 17100 с на одну кнопку.

ЗАМОК (то, ради чего файл существует) краснеет, если:
  · дедлайн СНЯТ — дефолт бюджета перестал быть положительным либо сборка перестала его открывать;
  · какая-то ВЕТКА ЛЕСТНИЦЫ его обходит — плечо снова берёт полный `self.timeout`, повтор идёт без
    оглядки на остаток, обращение к мосту идёт мимо единой двери `_durable_request`;
  · исчерпанный бюджет снова МОЛЧА отдаёт неполную карточку (третий исход).

ВРЕМЯ В ТЕСТЕ ВИРТУАЛЬНОЕ. Часы и sleep у `bridge_client` подменяются: лестница жжёт виртуальные
секунды, поэтому проверка мгновенна и ДЕТЕРМИНИРОВАНА (иначе замер «уложились в бюджет» зависел бы
от нагрузки машины — тот самый ложный красный, ради которого гейт держат мокнутым).
"""
import os
import sys
import ast
import time as _real_time

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import card_deadline as CD
import bridge_client as BC
import splinter as S

REPO = "/root/turbobaby-manager-bot"
res = []


def ok(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    res.append(bool(cond))
    return bool(cond)


# ============================ (1) ЧИСТОЕ РЕШЕНИЕ: АРИФМЕТИКА ============================
print("(1) card_deadline — чистое решение")

ok(CD.BUDGET_DEFAULT > 0,
   f"дефолт бюджета положителен ({CD.BUDGET_DEFAULT} с) — дедлайн НЕ снят")
ok(CD.BUDGET_DEFAULT > 37.9,
   "дефолт выше самого дорогого ЧЕСТНОГО прогона замера (37.9 с) — честную работу не режет")
ok(CD.BUDGET_DEFAULT < 122.5,
   "дефолт ниже прогона-жалобы (122.5 с) — больные прогоны срезаются")

ok(CD.parse_budget(None) == CD.BUDGET_DEFAULT, "ручка не задана → дефолт")
ok(CD.parse_budget("") == CD.BUDGET_DEFAULT, "пустая ручка → дефолт")
ok(CD.parse_budget("abc") == CD.BUDGET_DEFAULT,
   "мусор в ручке → ДЕФОЛТ, а не ноль: опечатка не снимает предохранитель молча")
ok(CD.parse_budget("0") == 0.0, "ручка 0 → откат (дедлайна нет)")
ok(CD.parse_budget("-5") == 0.0, "отрицательное → откат")
ok(CD.parse_budget("12.5") == 12.5 and CD.parse_budget("12,5") == 12.5, "число читается (точка и запятая)")

ok(CD.deadline_at(100.0, 0) is None, "бюджет 0 → дедлайна нет вовсе")
ok(CD.deadline_at(100.0, 60) == 160.0, "дедлайн = сейчас + бюджет")

ok(CD.remaining(None, 100.0) is None,
   "остаток при закрытом дедлайне — None, а НЕ 0.0: «бюджета нет» ≠ «бюджет кончился»")
ok(CD.remaining(160.0, 100.0) == 60.0, "остаток считается")
ok(CD.expired(None, 10 ** 9) is False, "без дедлайна ничего не истекает (прежнее поведение)")
ok(CD.expired(160.0, 160.1) is True and CD.expired(160.0, 159.9) is False, "истечение по границе")

ok(CD.leg_timeout(None, 100.0, 60) == 60, "без дедлайна плечо берёт прежний бюджет 60 с")
ok(CD.leg_timeout(160.0, 100.0, 60) == 60, "остаток больше базы → плечо берёт базу")
ok(CD.leg_timeout(160.0, 150.0, 60) == 10.0,
   "остаток 10 с → плечу дают 10, а не 60 (иначе потолок перекрывался бы в 6 раз)")
ok(CD.leg_timeout(160.0, 159.9, 60) == CD.LEG_MIN, "остаток меньше пола → пол, а не 0.1 с")

ok(CD.may_start_leg(None, 10 ** 9) is True, "без дедлайна плечо начинать можно всегда")
ok(CD.may_start_leg(160.0, 158.0) is True and CD.may_start_leg(160.0, 159.5) is False,
   "плечо начинаем, только если остатка хватит на LEG_MIN")
ok(CD.may_wait(160.0, 100.0, 5) is True and CD.may_wait(160.0, 155.0, 5) is False,
   "паузу ждём, только если после неё влезет плечо")
ok(CD.may_wait(None, 10 ** 9, 999) is True, "без дедлайна пауза разрешена (прежнее поведение)")

# третий исход — слова
blk_ru = CD.missing_block(["fleet", "service_pending_get"], th=False, budget=60, spent=61.2,
                          deadline_hit=True)
blk_th = CD.missing_block(["fleet"], th=True, budget=60, spent=61.2, deadline_hit=True)
ok(CD.missing_block([], th=False) == [], "полная карточка → блока нет вовсе (вид не меняется)")
ok(any("не прочитан" in x for x in blk_ru), "блок называет непрочитанное")
ok(any("строка байка в Лист1" in x for x in blk_ru) and any("заявка в работе" in x for x in blk_ru),
   "источники названы человеческими словами, а не кодом действия")
ok(any("НЕ «нет данных»" in x for x in blk_ru),
   "сказано прямо: пустое место — это «не смог прочитать», а не «нет»")
ok(any("бюджет 60 с исчерпан" in x for x in blk_ru), "исчерпанный бюджет назван числом")
ok(len(blk_th) >= 3 and any("อ่านไม่ได้" in x for x in blk_th), "тайская половина блока есть")
ok(CD.source_label("невиданный_источник") == "невиданный_источник",
   "незнакомый источник называет СЕБЯ, а не растворяется в «прочем»")


# ============================ (2) ЗАМОК: УСТРОЙСТВО (ast) ============================
print("\n(2) ЗАМОК устройства: ни одна ветка лестницы не обходит дедлайн")

with open(os.path.join(REPO, "bridge_client.py"), encoding="utf-8") as f:
    bc_src = f.read()
bc_tree = ast.parse(bc_src)
FUNCS = {}
for node in ast.walk(bc_tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        FUNCS[node.name] = node


def body_names(fn_name):
    """Имена, встречающиеся в теле функции КАК КОД (правило исполняющей позиции: слово в
    комментарии или строке кодом не является)."""
    fn = FUNCS.get(fn_name)
    if fn is None:
        return set()
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def leg_timeouts(fn_name):
    """Чем задан timeout= у HTTP-вызовов внутри функции: множество выражений (в исходнике)."""
    fn = FUNCS.get(fn_name)
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg == "timeout":
                    out.add(ast.unparse(kw.value))
    return out


# лестница 1 — полные попытки
ok("_card_may_wait" in body_names("_durable_request_impl"),
   "лестница 1 (полные попытки): backoff-повтор сверяется с остатком бюджета")
# лестница 2 — хопы редиректа
ok("_card_room" in body_names("_exchange"),
   "лестница 2 (хопы редиректа): каждый хоп спрашивает, есть ли место в бюджете")
# лестница 3 — эхо-слой
ok("_card_may_wait" in body_names("_fetch_redirect_target")
   and "_card_room" in body_names("_fetch_redirect_target"),
   "лестница 3 (эхо-слой): и пауза, и плечо сверяются с бюджетом")
# плечо не берёт полный timeout
ok(leg_timeouts("_exchange") == {"self._leg_timeout()"},
   f"плечо в _exchange режется остатком, а не self.timeout ({leg_timeouts('_exchange')})")
ok(leg_timeouts("_fetch_redirect_target") == {"self._leg_timeout()"},
   f"плечо эхо-слоя режется остатком ({leg_timeouts('_fetch_redirect_target')})")
# дверь и короткое замыкание
ok("expired" in body_names("_durable_request") and "note" in body_names("_durable_request"),
   "единая дверь: исчерпанный бюджет гасит действие ДО сети, исход записывается")
# чистота решения: у card_deadline не должно быть инструментов
cd_tree = ast.parse(open(os.path.join(REPO, "card_deadline.py"), encoding="utf-8").read())
cd_imports = [n for n in ast.walk(cd_tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
ok(not cd_imports, "у решения НОЛЬ импортов — оно не может ни узнать время, ни сходить в сеть")
# сборка карточки открывает бюджет
sp_tree = ast.parse(open(os.path.join(REPO, "splinter.py"), encoding="utf-8").read())
build = [n for n in ast.walk(sp_tree)
         if isinstance(n, ast.FunctionDef) and n.name == "_build_bike_card"]
ok(len(build) == 1 and "card_budget" in {getattr(a, "attr", "") for a in ast.walk(build[0])
                                         if isinstance(a, ast.Attribute)},
   "сборка карточки ОТКРЫВАЕТ общий бюджет (снимут — здесь красное)")


# ============================ ВИРТУАЛЬНЫЕ ЧАСЫ + БОЛЬНОЙ МОСТ ============================
class Clock:
    """Часы для лестницы: sleep и медленное плечо двигают ВИРТУАЛЬНОЕ время."""

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return _real_time.time()

    def sleep(self, sec):
        self.now += float(sec)
        self.slept += float(sec)


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


class SickSession:
    """Мост, больной ровно так, как в замере: 302 на /exec, а эхо-слой отдаёт 404.
    КАЖДОЕ плечо стоит `leg_sec` виртуальных секунд — но не больше, чем ему выдали timeout'ом
    (иначе тест не увидел бы, режется плечо остатком или нет)."""

    def __init__(self, clock, leg_sec=8.0):
        self.clock = clock
        self.leg_sec = leg_sec
        self.legs = []

    def _leg(self, url, timeout):
        spent = min(self.leg_sec, float(timeout))
        self.clock.now += spent
        self.legs.append({"url": str(url), "timeout": float(timeout), "sec": spent})

    def get(self, url, **kw):
        self._leg(url, kw.get("timeout", 60))
        if "googleusercontent" in str(url):
            return Resp(404)
        return Resp(302, headers={"Location": "https://googleusercontent.com/echo"})

    def post(self, url, **kw):
        self._leg(url, kw.get("timeout", 60))
        return Resp(302, headers={"Location": "https://googleusercontent.com/echo"})

    def close(self):
        pass


class HealthySession(SickSession):
    """Здоровый мост: 302 → эхо отдаёт 200 с телом. Два плеча на действие, как в чистом прогоне."""

    def get(self, url, **kw):
        self._leg(url, kw.get("timeout", 60))
        if "googleusercontent" in str(url):
            return Resp(200, payload={"ok": True, "data": {"bikes": []}, "items": [], "text": ""})
        return Resp(302, headers={"Location": "https://googleusercontent.com/echo"})


def build_card(session_cls, budget, leg_sec=8.0):
    """Собрать карточку живым кодом на подменённых часах. → (текст, потрачено, плечи, клиент)."""
    clock = Clock()
    old_time, old_env = BC.time, os.environ.get(CD.BUDGET_ENV)
    BC.time = clock
    os.environ[CD.BUDGET_ENV] = str(budget)
    S._SVC_INTERVALS_CACHE["data"] = None      # холодный кэш книги → тот же путь, что в замере
    S._SVC_INTERVALS_CACHE["ts"] = 0
    try:
        client = BC.BridgeClient(url="http://x", token="t")
        sess = session_cls(clock, leg_sec)
        client._session = sess
        client._new_session = lambda: None     # анти-клин не должен подсовывать живую сессию
        t0 = clock.now
        text = S._build_bike_card(client, -100, 7, "TEST 4724")
        return text, clock.now - t0, sess.legs, client
    finally:
        BC.time = old_time
        if old_env is None:
            os.environ.pop(CD.BUDGET_ENV, None)
        else:
            os.environ[CD.BUDGET_ENV] = old_env
        S._SVC_INTERVALS_CACHE["data"] = None
        S._SVC_INTERVALS_CACHE["ts"] = 0


# ============================ (3) ЗАМОК: ПОВЕДЕНИЕ ============================
print("\n(3) ЗАМОК поведения: больной мост укладывается в бюджет")

BUDGET = 60.0
text_sick, spent_sick, legs_sick, _ = build_card(SickSession, BUDGET)
ok(spent_sick <= BUDGET + CD.LEG_MIN + 8.0,
   f"вся карточка уложилась в бюджет: {spent_sick:.1f} с при бюджете {BUDGET} с "
   f"(потолок одного начатого плеча сверху — честная цена)")
ok(len(legs_sick) < 57,
   f"плеч {len(legs_sick)} — лестница обрезана (без дедлайна одно действие давало до 57)")

# теми же фактами БЕЗ дедлайна — доказательство, что у теста есть зубы
text_off, spent_off, legs_off, _ = build_card(SickSession, 0)
ok(spent_off > BUDGET * 3,
   f"откат INFO_CARD_BUDGET_SEC=0 → те же факты тянутся {spent_off:.0f} с "
   f"(в {spent_off / max(spent_sick, 0.1):.1f} раза дольше) — снятие дедлайна ВИДНО")
ok(len(legs_off) > len(legs_sick),
   f"без дедлайна плеч {len(legs_off)} против {len(legs_sick)} с ним")

# плечо режется остатком, а не берёт полные 60
short = [l for l in legs_sick if l["timeout"] < 60]
ok(bool(short),
   f"хотя бы одно плечо получило урезанный бюджет ({len(short)} шт.) — потолок не на бумаге")
ok(all(l["timeout"] <= 60 for l in legs_sick), "ни одно плечо не получило больше прежних 60 с")


# ============================ (4) ЗАМОК: ОБХОДА НЕТ ============================
print("\n(4) ЗАМОК: ни одно обращение к мосту не идёт мимо бюджета")

seen = []
_orig_durable = BC.BridgeClient._durable_request


def spy(self, method, action, params=None, body=None, retry_full=False):
    seen.append((action, BC.current_card_budget() is not None))
    return _orig_durable(self, method, action, params=params, body=body, retry_full=retry_full)


BC.BridgeClient._durable_request = spy
try:
    build_card(HealthySession, BUDGET, leg_sec=0.5)
finally:
    BC.BridgeClient._durable_request = _orig_durable

ok(len(seen) >= 5, f"сборка обратилась к мосту {len(seen)} раз(а) — есть что проверять")
ok(all(inside for _, inside in seen),
   "КАЖДОЕ обращение видело живой бюджет — ветки в обход нет "
   + ("" if all(i for _, i in seen) else str([a for a, i in seen if not i])))
ok(BC.current_card_budget() is None, "после сборки бюджет закрыт — на демона и аудитора не течёт")


# ============================ (5) ТРЕТИЙ ИСХОД ============================
print("\n(5) третий исход: исчерпанный бюджет НЕ выдаёт неполные данные молча")

ok("не прочитан" in text_sick or "не прочитано" in text_sick,
   "карточка больного моста ГОВОРИТ, что данные неполные")
ok("не делалось" not in text_sick,
   "и НЕ пишет «не делалось» про ТО, которого не читала (пустое поле ≠ «нет»)")
ok("อ่านไม่ได้" in text_sick, "тайская половина тоже предупреждена")
ok("бюджет" in text_sick and "исчерпан" in text_sick, "названа причина: бюджет исчерпан")
ok("Статус байка" not in text_sick, "шапка не выдаёт непрочитанный пробег за «просто нет данных»")
ok("пробег не прочитан" in text_sick, "шапка называет непрочитанный пробег прямо")

# полная карточка — вид БАЙТ-В-БАЙТ прежний
full_old = S.msg_bike_card("X 4724", "37000", [{"kind": "oil", "last": 36000, "interval": 3000}],
                           None, service=None, sp_open=None, sp_last=None)
full_new = S.msg_bike_card("X 4724", "37000", [{"kind": "oil", "last": 36000, "interval": 3000}],
                           None, service=None, sp_open=None, sp_last=None, unread=None)
ok(full_old == full_new, "полная карточка: unread=None → текст байт-в-байт прежний")
ok("не прочитан" not in full_new and "⚠️ <b>ДАННЫЕ НЕПОЛНЫЕ" not in full_new,
   "у здоровой карточки блока потерь нет вовсе")

# «не найдено» ≠ «не прочитано»
st = BC.CardBudget(60, 0, 60)
st.note("service_pending_get", {"ok": False, "error": "not_found"})
ok(st.missing() == [],
   "семантический отказ моста (открытой заявки НЕТ) непрочитанным не считается — иначе крик звучал бы всегда")
st.note("fleet", {"ok": False, "error": "request_failed"})
ok(st.missing() == ["fleet"], "транспортный сбой → источник не прочитан")
st.note("fleet", {"ok": True})
ok(st.missing() == [], "ответил позже → жалоба снимается (иначе врали бы в другую сторону)")


# ============================ (6) ОТКАТ ============================
print("\n(6) откат ручкой INFO_CARD_BUDGET_SEC=0")

ok(CD.deadline_at(1000.0, CD.parse_budget("0")) is None,
   "ручка 0 → дедлайна нет; лестницы работают как до правки")
ok("не прочитан" in text_off or "не прочитано" in text_off,
   "честность про непрочитанное при откате ОСТАЁТСЯ — она не стоит ни запроса, ни секунды")

# бюджет не течёт между сборками (ContextVar, а не поле клиента)
ok(BC.current_card_budget() is None, "вне сборки бюджета нет — прочие потребители моста не задеты")
with BC.card_budget(60) as cb1:
    ok(BC.current_card_budget() is cb1, "внутри сборки бюджет виден")
ok(BC.current_card_budget() is None, "по выходе бюджет снят (даже если внутри было исключение)")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})",
      f"— {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
