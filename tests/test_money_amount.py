"""НОЛЬ НЕ ОТ ХРАНИЛИЩА НЕ СТАНОВИТСЯ ДЕНЬГАМИ — ОСТАВШИЕСЯ ВЕТВИ (21.09.2026).

Продолжение класса, у которого одна ветвь закрыта коммитом `fe66881` (фиксация баланса). Там
ноль подставлялся вместо НЕПОЛУЧЕННОГО баланса. Здесь — вместо НЕНАЗВАННОЙ суммы движения, и это
другой конец того же: сумму называет РАЗБОР, хранилище о ней не спрашивают ВООБЩЕ, поэтому
заметить подстановку ниже по пути некому.

ПОДСТАНОВКА ЖИВЁТ В ДВУХ МЕСТАХ, и отказов поэтому два, а не один:
    · НАШ `.get("amount", 0)`            — ключа в движении нет вовсе;
    · МОСТОВОЙ `Number(p.amount) || 0`   — ключ есть, значение `null`/строка/логическое; наш
      `.get` пропускает такое МИМО себя, ноль рождается уже за сетью, а ответ приходит
      `{ok:true, saved:true}` — неотличимый от честной записи (`bridge_prod/BotData.js:484`).

ВЕТВИ, КОТОРЫЕ ЗАКРЫВАЕТ ЭТОТ СЬЮТ (нумерация артефакта 2026-09-22-NOLNEDENGI-2209):
    В2  splinter.py `_record_transaction`  amount=mv.get("amount", 0)      → строка в лист на 0
    В3  splinter.py `_record_transaction`  plus = abs(money_amount or 0)   → ВТОРАЯ строка в
        ДРУГОЙ кошелёк + «Пополнение +0 ฿» в ЧУЖУЮ группу (ветка запасного значения дословно)
    В4  splinter.py `_handle_money` undo   res.get("amount", 0) / balance  → «−0 ฿», «Баланс 0 ฿»
        как СВЕЖИЙ, и молчание моста как «Нечего отменять»
    В5  splinter.py `_handle_money` check  res.get("diff", 0)              → «разница 0» = «сходится»

МУТАНТ НА КАЖДУЮ ВЕТВЬ: подсовываем ноль НЕ ОТ ХРАНИЛИЩА (нет ключа · `null` · строка · nan) и
числом показываем, что ветка отказала — ни одной проводки, названная причина в журнале.

Сеть не дёргается ни разу: мост, отправка в Telegram и разбор LLM — свои. Кэш держим в СВОЁМ
каталоге: боевой `wallet_cache.json` — состояние прода, и сьют, пишущий в него, сам стал бы
источником выдуманных балансов (побочная находка 13.08). Боевой базы, денежных путей и боевых
файлов состояния тест не касается вовсе.
"""
import os
import sys
import json
import asyncio
import logging
import datetime
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["MONEY_AMOUNT"] = "1"
_CACHE_DIR = tempfile.mkdtemp(prefix="tb_money_amount_")
os.environ["WALLET_CACHE_FILE"] = os.path.join(_CACHE_DIR, "wallet_cache.json")

import money_amount as MA
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


PC_CHAT = -1003909369438              # Самоорганизация = мелкая касса
PC_WALLET = "Самоорганизация"
CF_CHAT = -1003873906891              # Money Cashflow (перенос идёт ОТСЮДА в мелкую кассу)
CF_WALLET = "Money Cashflow"

LIVE_BAL = {"ok": True, "action": "get_balance", "balance": {"THB": 1029.0}}

SENDS = []


async def _rec_send(context=None, chat_id=None, text="", **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send
S._is_trusted = lambda m: True
S.pending_currency_for = lambda *a, **k: None


class LogCatch(logging.Handler):
    """СЛЕД судится по живому журналу splinter, а не по возвращённому значению: предмет пункта 3
    задания — «свежий ноль не виден ни в одном журнале», значит смотреть надо ровно туда."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def text(self):
        return "\n".join(self.lines)


CATCH = LogCatch()
S.log.addHandler(CATCH)
S.log.setLevel(logging.INFO)


class Msg:
    def __init__(self, chat_id=PC_CHAT, text="-500 бензин"):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = chat_id
        self.message_thread_id = None
        self.date = datetime.datetime(2026, 9, 21, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 9090
        self.from_user = type("U", (), {"username": "pleummmm", "id": 111})()


class FakeClaude:
    def __init__(self, payload):
        self.payload = payload

    def quick(self, *a, **kw):
        return self.payload

    def vision(self, *a, **kw):
        return "{}"


class FakeBridge:
    """Мост, считающий КАЖДОЕ обращение: цена доказывается счётчиком, а не обещанием."""

    def __init__(self, bal_reply=None, undo_reply=None, check_reply=None):
        self.bal_reply = LIVE_BAL if bal_reply is None else bal_reply
        self.undo_reply = undo_reply or {}
        self.check_reply = check_reply or {}
        self.calls = []
        self.tx = []

    def get_balance(self, **kw):
        self.calls.append("get_balance")
        return self.bal_reply

    def add_transaction(self, **kw):
        self.calls.append("add_transaction")
        self.tx.append(kw)
        return {"ok": True, "saved": True}

    def tx_summary(self, **kw):
        self.calls.append("tx_summary")
        return {"ok": True, "items": []}

    def void_last(self, **kw):
        self.calls.append("void_last")
        return self.undo_reply

    def check_balance(self, **kw):
        self.calls.append("check_balance")
        return self.check_reply


def run(bridge, payload, chat_id=PC_CHAT):
    """Прогнать кассу целиком, от разбора до отправки. Возвращает склеенный текст в группу."""
    SENDS.clear()
    CATCH.lines.clear()
    asyncio.run(S._handle_money(Msg(chat_id), None, bridge, FakeClaude(json.dumps(payload))))
    return "\n".join(SENDS)


def tx_payload(*moves):
    return {"type": "transaction", "moves": list(moves)}


GOOD = {"amount": -500, "currency": "THB", "category": "fuel"}
#: Четыре способа получить ноль НЕ ОТ ХРАНИЛИЩА. Первый — наш `.get`, остальные три — мостовой
#: `Number(x) || 0`: ключ ЕСТЬ, и наш `.get` их пропускает.
NO_KEY = {"currency": "THB", "category": "fuel"}
NULL_AMT = {"amount": None, "currency": "THB", "category": "fuel"}
WORD_AMT = {"amount": "пятьсот", "currency": "THB", "category": "fuel"}
NAN_AMT = {"amount": float("nan"), "currency": "THB", "category": "fuel"}
MUTANTS = (("ключа нет", NO_KEY), ("amount=null", NULL_AMT),
           ("amount=строка", WORD_AMT), ("amount=nan", NAN_AMT))


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(1) СУДЬЯ: три исхода, и «сумма названа» приходит РОВНО одним путём")
ok(MA.verdict(GOOD).said and MA.verdict(GOOD).value == -500.0,
   "число → SAID, значение разобрано")
ok(MA.verdict(NO_KEY).state == MA.STATE_ABSENT, "ключа нет → ABSENT (наш .get подставил бы ноль)")
for name, mv in (("null", NULL_AMT), ("строка", WORD_AMT), ("nan", NAN_AMT)):
    ok(MA.verdict(mv).state == MA.STATE_UNPARSED,
       f"{name} → UNPARSED (ключ есть, ноль подставил бы мост)")
ok(MA.verdict({"amount": float("inf")}).state == MA.STATE_UNPARSED,
   "бесконечность деньгами не бывает → UNPARSED")
ok(MA.verdict({"amount": True}).state == MA.STATE_UNPARSED,
   "логическое числом не считается: True это true, а не сумма (различитель balance_fact)")
ok(MA.verdict(None).state == MA.STATE_ABSENT, "источник не словарь → ABSENT, а не третий отказ")
ok(MA.verdict("").state == MA.STATE_ABSENT, "строка вместо движения → ABSENT")

section("(1а) СУДИТСЯ ПОДСТАНОВКА, А НЕ ЗНАЧЕНИЕ — названный ноль проходит")
ok(MA.verdict({"amount": 0}).said and MA.verdict({"amount": 0}).value == 0.0,
   "ноль, который НАЗВАЛИ, — число: класс про происхождение, а не про величину")
ok(MA.verdict({"amount": "0"}).said, "строка «0» разбирается в число — это ответ, а не его отсутствие")
ok(MA.verdict({"amount": -0.0}).said, "минус ноль — тоже названное число")

section("(1б) СЛЕД называет ПРИЧИНУ и МЕСТО подстановки")
ok(".get(\"amount\", 0)" in MA.verdict(NO_KEY).say(),
   "ABSENT: журнальная строка называет НАШ .get — чинить здесь")
ok("Number(x) || 0" in MA.verdict(NULL_AMT).say(),
   "UNPARSED: журнальная строка называет МОСТОВОЙ Number(x)||0 — чинить там")
ok("'пятьсот'" in MA.verdict(WORD_AMT).say(),
   "сырое значение показано: «не разобрал» обязано быть отличимо от «не нашёл»")
ok("движение 2 из 3" in MA.verdict(NO_KEY, where="движение 2 из 3").say(),
   "место названо словами вызывающего")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(2) ЗДОРОВЫЙ ПУТЬ БАЙТ-В-БАЙТ — ворота не задевают настоящую проводку")
_reset_cache()
b = FakeBridge()
txt_on = run(b, tx_payload(dict(GOOD)))
ok(b.tx and abs(b.tx[0]["amount"] - (-500.0)) < 0.001, "проводка ушла в лист с той же суммой")
ok(b.calls.count("add_transaction") == 1, "ровно одна запись, лишних обращений нет")
ok("НЕ записал" not in txt_on and "суммы нет" not in txt_on, "слов отказа в тексте нет")

os.environ["MONEY_AMOUNT"] = "0"
b2 = FakeBridge()
txt_off = run(b2, tx_payload(dict(GOOD)))
os.environ["MONEY_AMOUNT"] = "1"
ok(txt_on == txt_off, "текст здорового пути ПОСИМВОЛЬНО равен тексту без ворот")
ok([c for c in b.calls] == [c for c in b2.calls], "и список обращений к мосту тот же")

section("(2а) НАЗВАННЫЙ НОЛЬ ПИШЕТСЯ — ворота судят подстановку, а не величину")
b = FakeBridge()
txt = run(b, tx_payload({"amount": 0, "currency": "THB", "category": "other"}))
ok(b.tx and b.tx[0]["amount"] == 0, "движение «0» ушло в лист: человек назвал ноль — это ответ")
ok("НЕ записал" not in txt, "и отказа человеку не прозвучало")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(3) МУТАНТ ВЕТВИ В2 — ноль не от хранилища вместо суммы движения")
for name, mv in MUTANTS:
    _reset_cache()
    b = FakeBridge()
    txt = run(b, tx_payload(dict(mv)))
    ok("add_transaction" not in b.calls and b.tx == [],
       f"В2/{name}: в лист НЕ ушло ни одной строки (до правки легла бы на 0)")
    ok("❌ НЕ записал" in txt and "суммы нет" in txt,
       f"В2/{name}: человеку сказан третий исход словами")
    ok("ยังไม่ได้บันทึก" in txt, f"В2/{name}: то же по-тайски — решение принимает Пым")
    ok("НЕ ПИШЕТСЯ" in CATCH.text() and "движение 1 из 1" in CATCH.text(),
       f"В2/{name}: СЛЕД в журнале — с местом")
section("(3а) ПРИЧИНА В ЖУРНАЛЕ РАЗВОДИТ ДВА МЕСТА ПОДСТАНОВКИ")
run(FakeBridge(), tx_payload(dict(NO_KEY)))
ok(".get(\"amount\", 0)" in CATCH.text(), "ключа нет → журнал называет НАШ .get")
run(FakeBridge(), tx_payload(dict(NULL_AMT)))
ok("Number(x) || 0" in CATCH.text(), "amount=null → журнал называет МОСТОВОЙ Number(x)||0")

section("(3б) ЧАСТИЧНЫЙ ОТКАЗ: записанное записано, незаписанное НАЗВАНО в том же сообщении")
_reset_cache()
b = FakeBridge()
txt = run(b, tx_payload(dict(GOOD), dict(NULL_AMT)))
ok(len(b.tx) == 1 and abs(b.tx[0]["amount"] - (-500.0)) < 0.001,
   "здоровое движение записано — отказ соседа его не съел")
ok("❌ НЕ записал (суммы нет)" in txt and "движение 2 из 2" in txt,
   "и тут же названо, ЧТО не записано: подтверждение не выдаётся за полное")

section("(3в) ОТКАТ ВЕТВИ В2: MONEY_AMOUNT=0 возвращает прежнее поведение ВМЕСТЕ С ДЕФЕКТОМ")
os.environ["MONEY_AMOUNT"] = "0"
b = FakeBridge()
txt = run(b, tx_payload(dict(NULL_AMT)))
os.environ["MONEY_AMOUNT"] = "1"
ok(len(b.tx) == 1 and b.tx[0]["amount"] is None,
   "с выключенной ручкой движение снова уходит в мост без суммы (там станет нулём)")
ok("НЕ записал" not in txt, "и человек снова слышит подтверждение — откат доказан, не обещан")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(4) МУТАНТ ВЕТВИ В3 — перенос в ДРУГОЙ кошелёк (самая тяжёлая ветвь)")
_reset_cache()
b = FakeBridge()
txt = run(b, {"type": "transaction", "transfer_to_pettycash": True,
              "moves": [dict(GOOD)]}, chat_id=CF_CHAT)
ok(len(b.tx) == 2 and b.tx[1]["group"] == PC_WALLET and b.tx[1]["amount"] == 500.0,
   "здоровый путь: перенос по-прежнему кладёт ВТОРУЮ строку в мелкую кассу на 500")

for name, mv in MUTANTS:
    _reset_cache()
    b = FakeBridge()
    txt = run(b, {"type": "transaction", "transfer_to_pettycash": True,
                  "moves": [dict(mv)]}, chat_id=CF_CHAT)
    ok(not any(t.get("group") == PC_WALLET for t in b.tx),
       f"В3/{name}: в МЕЛКУЮ КАССУ не ушло ни одной строки")
    ok("Пополнение" not in txt, f"В3/{name}: и сообщения «Пополнение +0 ฿» в чужую группу нет")
    ok("ПЕРЕНОС НЕ СДЕЛАН" in CATCH.text() or "НЕ ПИШЕТСЯ" in CATCH.text(),
       f"В3/{name}: СЛЕД в журнале есть")

section("(4а) ВОРОТА В3 СТОЯТ САМИ — не держатся на фильтре В2")
mv = dict(NULL_AMT)
v = MA.verdict(mv, where="перенос")
ok(not v.said and "Number(x) || 0" in v.say(),
   "тот же судья зовётся отдельно для переноса — уберут фильтр В2, ворота удержат")
ok("if is_transfer and _money_amount_on():" in open(
    "/root/turbobaby-manager-bot/splinter.py", encoding="utf-8").read(),
   "ворота переноса — отдельная строка кода, а не следствие соседних")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(5) МУТАНТ ВЕТВИ В4 — отмена последней записи")
_reset_cache()
b = FakeBridge(undo_reply={"ok": True, "voided": True, "amount": -500,
                           "description": "бензин", "balance": {"THB": 1529.0}})
txt = run(b, {"type": "undo"})
ok("Отменил последнюю запись:  -500 ฿" in txt, "здоровый путь: строка отмены прежняя")
ok("1 529 ฿" in txt and "НЕ СВЕРЕН" not in txt, "и баланс из ответа показан как свежий")

_reset_cache()
b = FakeBridge(undo_reply={"ok": True, "voided": True, "description": "бензин"})
txt = run(b, {"type": "undo"})
ok("−0" not in txt and "-0 ฿" not in txt, "мутант: «−0 ฿» человеку НЕ показано")
ok("сумму таблица не назвала" in txt, "сказано словами, что числа нет")
ok("НЕ СВЕРЕН" in txt, "и баланс без числа не выдаётся за свежий ноль")
ok("отмена прошла, но" in CATCH.text(), "СЛЕД в журнале есть")

_reset_cache()
for name, reply in (("мост не ответил", {}), ("отказ моста", {"ok": False, "error": "request_failed"})):
    b = FakeBridge(undo_reply=reply)
    txt = run(b, {"type": "undo"})
    ok("Нечего отменять" not in txt,
       f"В4/{name}: молчание моста больше НЕ звучит утверждением о хранилище")
    ok("НЕ ЗНАЮ" in txt and "ВТОРУЮ запись" in txt,
       f"В4/{name}: третий исход + предупреждение о повторе вслепую")
    ok("исход ОТМЕНЫ НЕИЗВЕСТЕН" in CATCH.text(), f"В4/{name}: СЛЕД в журнале есть")

b = FakeBridge(undo_reply={"ok": True, "voided": False, "message": "нет активных записей"})
txt = run(b, {"type": "undo"})
ok("Нечего отменять" in txt,
   "ЧЕСТНЫЙ пустой лист по-прежнему звучит «нечего отменять» — ворота его не задели")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(6) МУТАНТ ВЕТВИ В5 — сверка баланса")
b = FakeBridge(check_reply={"ok": True, "match": False, "bot_balance": 1029.0,
                            "pym_balance": 900.0, "diff": 129.0})
txt = run(b, {"type": "balance_check", "balance": {"THB": 900}})
ok("129 ฿" in txt and "1 029 ฿" in txt, "здоровый путь: оба числа названы, как назывались")

for name, reply in (("diff отсутствует", {"ok": True, "match": False, "bot_balance": 1029.0}),
                    ("diff=null", {"ok": True, "match": False, "bot_balance": 1029.0, "diff": None}),
                    ("bot_balance отсутствует", {"ok": True, "match": False, "diff": 129.0})):
    b = FakeBridge(check_reply=reply)
    txt = run(b, {"type": "balance_check", "balance": {"THB": 900}})
    ok("разница:   0 ฿" not in txt and "разница: 0" not in txt,
       f"В5/{name}: «разница 0» (= «сходится») человеку НЕ показано")
    ok("числа не назвала" in txt, f"В5/{name}: сказано, что числа нет")
    ok("расхождение НЕ НАЗЫВАЮ" in CATCH.text(), f"В5/{name}: СЛЕД в журнале есть")


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(7) ГРАНИЦЫ — чего заход НЕ трогал")
src = open("/root/turbobaby-manager-bot/money_amount.py", encoding="utf-8").read()
import ast as _ast
_imports = [n for n in _ast.walk(_ast.parse(src))
            if isinstance(n, (_ast.Import, _ast.ImportFrom))]
ok(len(_imports) == 1, "импорт у решения РОВНО ОДИН — рук нет по построению")
ok(all(a.name == "balance_fact" for n in _imports if isinstance(n, _ast.Import) for a in n.names),
   "и это balance_fact: различитель числа взят готовым, второго не заводится")
ok("import money_amount" not in open(
    "/root/turbobaby-manager-bot/bridge_client.py", encoding="utf-8").read(),
   "клиент моста о новом решении не знает — граница записи не сдвинута")
guard = open("/root/turbobaby-manager-bot/pretool_guard.py", encoding="utf-8").read()
ok("money_amount" not in guard, "pretool_guard.py не изменён и о модуле не знает")
ok(WC.load_wallet_balance(CF_WALLET) in ({}, {"THB": 1029.0}),
   "кэш сьюта живёт в СВОЁМ каталоге — боевого wallet_cache.json заход не касался")


print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
