"""НОЛЬ, ПОЛУЧЕННЫЙ НЕ ОТ ХРАНИЛИЩА, НЕ СТАНОВИТСЯ СТРОКОЙ В КАССЕ (21.09.2026).

Место одно — фиксация баланса (`splinter._handle_money`, ветка `ptype == "balance_set"`). Оно
тяжелее соседей тем, что ноль здесь не печатается человеку, а ПИШЕТСЯ ДЕНЬГАМИ:

    adj = цель − текущее,   текущее = cur_bal.get(cur, 0)   ← ноль по умолчанию
    abs(adj) > 0.001  →  bridge.add_transaction(category="adjustment", amount=adj)

Молчащий мост при пустом кэше давал `текущее = 0`, то есть `adj = цель` — строку «фиксация» на
ВСЮ сумму, которой никто не заказывал. Различить «мост молчит» и «кошелёк пуст» БЫЛО ЧЕМ: `ok`
лежит в ответе моста и терялся на той же строке, в `.get("balance", {})`, ДО судьи — старой двери
`get_balance_with_fallback` оставалась истинность словаря, и ошибка шла в ОБЕ стороны (пустой
кошелёк, `ok:true` + `balance:{}`, читался как больной мост и брал чужое число из кэша).

ЗАМОК — обе стороны одного правила:
    · мост пересчитал  → поправка считается и пишется, БАЙТ-В-БАЙТ как до правки;
    · мост молчит/отказал → в кассу НЕ уходит НИ ОДНОЙ строки, человеку звучит третий исход
      принятой формой 13.08 («⚠️ Баланс НЕ СВЕРЕН» + дата, на двух языках), якорь в кэш не ложится.

Сеть не дёргается ни разу: мост, отправка в Telegram и разбор LLM — свои. Кэш держим в СВОЁМ
каталоге: боевой `wallet_cache.json` — состояние прода, и сьют, пишущий в него, сам становится
источником выдуманных балансов. Боевой базы, денежных путей и боевых файлов состояния тест не
касается вовсе.
"""
import os
import sys
import asyncio
import datetime
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
_CACHE_DIR = tempfile.mkdtemp(prefix="tb_balset_")
os.environ["WALLET_CACHE_FILE"] = os.path.join(_CACHE_DIR, "wallet_cache.json")

import balance_fact as BF
import wallet_cache as WC
import splinter as S

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))


def section(t):
    print("\n" + t)


def _reset_cache():
    try:
        os.remove(os.environ["WALLET_CACHE_FILE"])
    except OSError:
        pass


SELF_CHAT = -1003909369438            # Самоорганизация
WALLET = "Самоорганизация"
AT_1227 = datetime.datetime(2026, 8, 13, 12, 27, 0, tzinfo=datetime.timezone.utc).timestamp()

LIVE_OK = {"ok": True, "action": "get_balance", "group": WALLET, "balance": {"THB": 1029.0}}
EMPTY_OK = {"ok": True, "action": "get_balance", "group": WALLET, "balance": {}}   # кошелёк ПУСТ
DEAD_302 = {"ok": False, "error": "request_failed",
            "message": "Bridge request error (get_balance): HTTP 302"}
SILENT = {}                                                    # мост не ответил вовсе

SENDS = []


async def _rec_send(context=None, chat_id=None, text="", **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send
S._is_trusted = lambda m: True
S.pending_currency_for = lambda *a, **k: None


class Msg:
    def __init__(self):
        self.text = "должно быть 5715"
        self.caption = None
        self.photo = None
        self.chat_id = SELF_CHAT
        self.message_thread_id = None
        self.date = datetime.datetime(2026, 9, 21, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 7070
        self.from_user = type("U", (), {"username": "pleummmm", "id": 111})()


class FakeClaude:
    """Разбор кассы — свой. Сеть и LLM не дёргаются ни разу."""

    def __init__(self, payload):
        self.payload = payload

    def quick(self, *a, **kw):
        return self.payload


class FakeBridge:
    """Мост, чьё здоровье задаётся снаружи. Считает КАЖДОЕ обращение — цена доказывается счётчиком."""

    def __init__(self, bal_reply):
        self.bal_reply = bal_reply
        self.calls = []
        self.tx = []

    def get_balance(self, **kw):
        self.calls.append("get_balance")
        return self.bal_reply

    def add_transaction(self, **kw):
        self.calls.append("add_transaction")
        self.tx.append(kw)
        return {"ok": True, "saved": True}


def run(bridge, balance=None):
    """Прогнать фиксацию. `balance` — то, что владелец назвал целью."""
    SENDS.clear()
    payload = {"type": "balance_set",
               "balance": {"THB": 5715} if balance is None else balance}
    import json
    asyncio.run(S._handle_money(Msg(), None, bridge, FakeClaude(json.dumps(payload))))
    return "\n".join(SENDS)


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(1) ЗДОРОВЫЙ ПУТЬ — поправка считается от сверенного числа, как считалась")
_reset_cache()
b = FakeBridge(LIVE_OK)
txt = run(b)
ok(b.calls == ["get_balance", "add_transaction"],
   "здоровый путь: РОВНО одно обращение за балансом и одна проводка")
ok(len(b.tx) == 1 and abs(b.tx[0]["amount"] - 4686.0) < 0.001,
   "поправка = 5715 − 1029 = 4686 (считается от ЖИВОГО числа моста)")
ok(b.tx[0]["category"] == "adjustment", "категория строки прежняя — adjustment")
ok("Зафиксировал баланс:" in txt and "НЕ СВЕРЕН" not in txt,
   "здоровый путь: прежний текст, слов «не сверено» нет")
ok(WC.load_wallet_balance(WALLET) == {"THB": 5715.0}, "якорь цели лёг в кэш, как ложился")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(2) КОРЕНЬ: мост молчит, кэша нет → ноль по умолчанию писал ВСЮ сумму")
for name, reply in (("отказ моста (HTTP 302)", DEAD_302), ("мост не ответил вовсе", SILENT)):
    _reset_cache()
    b = FakeBridge(reply)
    txt = run(b)
    ok("add_transaction" not in b.calls and b.tx == [],
       f"{name}: в кассу НЕ ушло ни одной строки")
    ok("Баланс НЕ зафиксировал" in txt and "не записал ни строки" in txt,
       f"{name}: человеку сказан третий исход словами")
    ok("⚠️ Баланс НЕ СВЕРЕН" in txt, f"{name}: принятая форма 13.08, а не своя выдумка")
    ok("ยอดยังไม่ได้ตรวจสอบ" in txt and "ไม่ได้บันทึกลงบัญชี" in txt,
       f"{name}: то же по-тайски — решение принимает Пым")
    ok(WC.load_wallet_balance(WALLET) == {},
       f"{name}: якорь НЕ лёг — фиксации не было, и кэш этого не утверждает")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(3) Мост молчит, кэш ЕСТЬ → поправка от несвежего числа тоже не пишется")
_reset_cache()
WC.save_wallet_balance(WALLET, {"THB": 1529.0}, at=AT_1227)
b = FakeBridge(DEAD_302)
txt = run(b)
ok("add_transaction" not in b.calls, "кэш не даёт права писать деньгами")
ok("13.08 12:27 UTC" in txt, "названа дата, когда число было верно (без неё «не сверено» немо)")
ok("1 529 ฿" in txt, "последнее сверенное число показано — молчать тоже нельзя")
ok(WC.load_wallet_balance(WALLET) == {"THB": 1529.0}, "молчащий мост кэш НЕ перезаписал якорем")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(4) ИНВЕРСИЯ ТОГО ЖЕ КЛАССА: пустой кошелёк — это ПРАВДА, а не молчание")
_reset_cache()
WC.save_wallet_balance(WALLET, {"THB": 1529.0}, at=AT_1227)
b = FakeBridge(EMPTY_OK)
txt = run(b)
ok(len(b.tx) == 1 and abs(b.tx[0]["amount"] - 5715.0) < 0.001,
   "ok + пустой баланс = честный НОЛЬ: поправка на всю цель законна")
ok("Зафиксировал баланс:" in txt, "пустой кошелёк фиксируется, а не отвергается")
ok(WC.load_wallet_balance(WALLET) == {"THB": 5715.0},
   "чужое число из кэша к пустому кошельку НЕ подставлено (прежде подставлялось)")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(5) ГРАНИЦЫ: где строки в кассу не было и раньше — ничего не изменилось")
_reset_cache()
b = FakeBridge(DEAD_302)
txt = run(b, balance={"THB": None, "EUR": None, "PASSPORT": None})
ok(b.tx == [] and "Зафиксировал баланс:" in txt,
   "цели нет вовсе → прежний путь и прежний текст, третий исход не шумит")
_reset_cache()
b = FakeBridge(LIVE_OK)
txt = run(b, balance={"THB": 1029})
ok(b.tx == [] and "Зафиксировал баланс:" in txt,
   "цель равна живому балансу → поправки нет, как не было")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(6) ОТКАТ: CASH_FACT=0 → прежнее поведение, включая сам дефект")
os.environ["CASH_FACT"] = "0"
try:
    _reset_cache()
    b = FakeBridge(DEAD_302)
    txt = run(b)
    ok(len(b.tx) == 1 and abs(b.tx[0]["amount"] - 5715.0) < 0.001,
       "откат: молчащий мост снова даёт ноль по умолчанию и строку на всю сумму (тот самый дефект)")
    ok("Зафиксировал баланс:" in txt and "НЕ зафиксировал" not in txt,
       "откат: новых слов в тексте нет")
    ok(b.calls.count("get_balance") == 1, "откат: обращений к мосту столько же, сколько было")
finally:
    os.environ.pop("CASH_FACT", None)

_reset_cache()
b = FakeBridge(DEAD_302)
run(b)
ok(b.tx == [], "ручку вернули → правка снова работает")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(7) ЧУЖОГО НЕ ТРОГАЕМ")
ok(S._balance_block("Баланс", {"THB": 1029.0}) == ["Баланс:", "  1 029 ฿"],
   "голый dict → блок баланса прежний байт-в-байт")
v_none = BF.Balance(BF.STATE_NONE, {}, None, "мост не ответил")
ok(S._balance_block("Баланс", v_none) == ["⚠️ Баланс НЕ СВЕРЕН — таблица не ответила, "
                                          "последнего значения нет"],
   "нет ни числа, ни кэша → числа не печатаем ВОВСЕ (нуль врал бы громче молчания)")
src = open("/root/turbobaby-manager-bot/balance_fact.py", encoding="utf-8").read()
ok(src.count("\nimport ") + src.count("\nfrom ") == 1,
   "у решения кассы РОВНО один импорт — спросить мост ему нечем")

# ─────────────────────────────────────────────────────────────────────────────────────────────
import shutil
shutil.rmtree(_CACHE_DIR, ignore_errors=True)
os.environ.pop("WALLET_CACHE_FILE", None)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
