"""КАССА НЕ ПОКАЗЫВАЕТ БАЛАНС ИЗ КЭША МОЛЧА (13.08.2026) — замок в ОБЕ стороны.

Голдены сняты с ДОСЛОВНОГО случая 13.08 (splinter.log 12:27–12:35): расход −500 при кэше 1529 и
верном листе 1029; `add_transaction` умер в HTTP 302, `get_balance` — тоже, после 3 полных попыток.

ЗАМОК (пункт 4 ТЗ) — две стороны одного правила:
    · пересчёт УДАЛСЯ  → баланс показан как свежий, БАЙТ-В-БАЙТ как до правки;
    · мост отдал ПУСТО → показано «не сверено» + дата, и число не выдаёт себя за свежее.

Сеть не дёргается ни разу: мост, отправка в Telegram и файл кэша — свои. Кэш держим в СВОЁМ
каталоге: боевой `wallet_cache.json` — состояние прода, и сьют, пишущий в него, сам становится
источником выдуманных балансов (ровно так туда попало фикстурное «Money Cashflow: 1000»).
"""
import os
import sys
import json
import asyncio
import datetime
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
_CACHE_DIR = tempfile.mkdtemp(prefix="tb_cash_fact_")
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


# ── ДОСЛОВНАЯ ФАКТУРА 13.08 ──────────────────────────────────────────────────────────────────
MONEY_CHAT = -1003873906891          # Money Cashflow
SELF_CHAT = -1003909369438           # Самоорганизация (там и случился инцидент)
LIVE_OK = {"ok": True, "action": "get_balance", "group": "Самоорганизация",
           "balance": {"THB": 1029.0}}                    # лист считает 1029 — он верен
DEAD_302 = {"ok": False, "error": "request_failed",
            "message": "Bridge request error (get_balance): HTTP 302"}
TX_DEAD_302 = {"ok": False, "error": "request_failed",
               "message": "Bridge request error (add_transaction): HTTP 302"}
TX_RECEIPT_LOST = {"ok": False, "error": "receipt_unknown", "outcome": "unknown"}
AT_1227 = 1786624020.0                                    # 13.08.2026 12:27 UTC ровно


# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(1) БАЛАНС: три исхода, и пустой ответ ≠ молчание")
v = BF.balance_verdict(LIVE_OK, {"THB": 1529.0}, AT_1227)
ok(v.state == BF.STATE_FRESH and v.value == {"THB": 1029.0}, "ok+баланс → FRESH, кэш не спрошен")
ok(v.fresh, "FRESH.fresh")

v = BF.balance_verdict({"ok": True, "balance": {}}, {"THB": 1529.0}, AT_1227)
ok(v.state == BF.STATE_FRESH and v.value == {},
   "ok+ПУСТОЙ баланс → FRESH ноль (кошелёк пуст), а НЕ подмена кэшем — корень класса")

v = BF.balance_verdict(DEAD_302, {"THB": 1529.0}, AT_1227)
ok(v.state == BF.STATE_STALE and v.value == {"THB": 1529.0} and v.at == AT_1227,
   "мост молчит + кэш → STALE с датой")
ok(not v.fresh and v.shows_number, "STALE: не свежий, но число есть")

v = BF.balance_verdict(DEAD_302, {}, None)
ok(v.state == BF.STATE_NONE and not v.shows_number, "мост молчит и кэша нет → NONE, числа нет")

ok(BF.balance_verdict(None, {"THB": 7.0}, None).state == BF.STATE_STALE,
   "ответ не словарь → не свежий (fail-closed)")
ok(BF.balance_verdict({"ok": True}, {"THB": 7.0}, AT_1227).state == BF.STATE_STALE,
   "ok без поля balance → свежим не называем")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(2) ЗАМОК СТОРОНА А: пересчёт удался → баланс показан как свежий (байт-в-байт)")
fresh = BF.Balance(BF.STATE_FRESH, {"THB": 1029.0})
new_txt = S.msg_recorded_cf(-500, fresh, "THB", wallet="Самоорганизация")
old_txt = S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB", wallet="Самоорганизация")
ok(new_txt == old_txt, "вердикт FRESH и голый dict дают ОДИН И ТОТ ЖЕ текст")
ok("Баланс:\n  1 029 ฿" in new_txt, "RU: обычный блок баланса, 1 029 ฿")
ok("ยอดคงเหลือ:\n  1 029 ฿" in new_txt, "TH: обычный блок баланса")
ok("Записал  -500 ฿" in new_txt, "RU: «Записал» — расписка не терялась")
ok("не сверен" not in new_txt.lower() and "ตรวจสอบ" not in new_txt,
   "свежий баланс НЕ несёт слова «не сверено» ни на одном языке")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(3) ЗАМОК СТОРОНА Б: мост отдал пусто → «не сверено» + дата, на двух языках")
stale = BF.Balance(BF.STATE_STALE, {"THB": 1529.0}, AT_1227)
txt = S.msg_recorded_cf(-500, stale, "THB", wallet="Самоорганизация")
ok("Баланс НЕ СВЕРЕН" in txt, "RU: сказано «Баланс НЕ СВЕРЕН»")
ok("ยอดยังไม่ได้ตรวจสอบ" in txt, "TH: сказано то же по-тайски")
ok("13.08 12:27 UTC" in txt, "названа ДАТА, когда значение было верным")
ok("последнее сверенное значение" in txt, "RU: число названо последним сверенным")
ok("ยอดล่าสุดที่ตรวจสอบแล้ว" in txt, "TH: число названо последним сверенным")
ok("Баланс:\n  1 529 ฿" not in txt and "ยอดคงเหลือ:\n  1 529 ฿" not in txt,
   "1 529 НЕ показан как обычный свежий баланс — ни на одном языке")
ok(txt.count("1 529 ฿") == 2, "число показано (по разу на язык) — касса не молчит")
ok("⚠️" in txt, "пометка видима")

none = BF.Balance(BF.STATE_NONE, {}, None)
txt0 = S.msg_recorded_cf(-500, none, "THB", wallet="Самоорганизация")
ok("последнего значения нет" in txt0 and "ไม่มียอดล่าสุด" in txt0,
   "кэша нет → сказано прямо, на двух языках")
ok("  0 ฿" not in txt0 and "Баланс:" not in txt0,
   "нуля вместо баланса НЕТ — он врал бы громче молчания")

nots = BF.Balance(BF.STATE_STALE, {"THB": 1529.0}, None)
ok("время неизвестно" in S.msg_recorded_cf(-500, nots, "THB")
   and "ไม่ทราบเวลา" in S.msg_recorded_cf(-500, nots, "THB"),
   "метки времени нет (кэш лёг прежним кодом) → честное «время неизвестно», а не выдумка")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(4) РАСПИСКА ПРОВОДКИ: когда перечитывать, и во что это обходится")
ok(BF.needs_verify({"ok": True, "saved": True}) is False, "успех → лист НЕ перечитываем")
ok(BF.needs_verify({"ok": True, "duplicate": True}) is False, "дубль по ключу → успех, не читаем")
ok(BF.needs_verify(TX_DEAD_302) is True, "HTTP 302 (дословный случай 13.08) → перечитываем")
ok(BF.needs_verify(TX_RECEIPT_LOST) is True, "отказ расписки → перечитываем")
ok(BF.needs_verify(None) is True, "ответ не словарь → перечитываем (судить не по чему)")
ok(BF.needs_verify({"ok": False, "error": "card_deadline"}) is False,
   "отказ, вынесенный САМИМ мостом → исход определён, не читаем")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(5) ФАКТ ПРОВОДКИ В ЛИСТЕ: три исхода")
sig = BF.signature(-500, "THB", "fuel", "NMAX 4724")
row = {"date": "2026-08-13", "sender": "@pleummmm", "amount": -500, "currency": "THB",
       "category": "fuel", "bike": "NMAX 4724", "description": "-500"}
other = dict(row, amount=-120, category="other", bike="")

f = BF.tx_verdict(sig, {"ok": True, "items": [other]})
ok(f.state == BF.STATE_ABSENT and f.absent, "0 совпадений → ABSENT (строки нет)")
f = BF.tx_verdict(sig, {"ok": True, "items": [other, row]})
ok(f.state == BF.STATE_LANDED and f.landed, "ровно 1 совпадение → LANDED")
f = BF.tx_verdict(sig, {"ok": True, "items": [row, row]})
ok(f.state == BF.STATE_UNKNOWN and f.seen == 2,
   "2 близнеца → UNKNOWN: чужую строку себе не приписываем")
ok(BF.tx_verdict(sig, DEAD_302).state == BF.STATE_UNKNOWN, "мост молчит → UNKNOWN")
ok(BF.tx_verdict(sig, {"ok": True}).state == BF.STATE_UNKNOWN, "ok без items → UNKNOWN")
ok(BF.tx_verdict(BF.signature(None, "THB"), {"ok": True, "items": []}).state == BF.STATE_UNKNOWN,
   "сумма не число → сверять нечем → UNKNOWN")
ok(not BF.tx_verdict(sig, {"ok": True, "items": [row, row]}).landed
   and not BF.tx_verdict(sig, DEAD_302).landed,
   "НИ ОДИН неизвестный исход не читается как «записано»")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(6) «ЗАПИСАЛ» — УТВЕРЖДЕНИЕ: без факта оно не звучит")
landed = BF.TxFact(BF.STATE_LANDED, sig, 1)
absent = BF.TxFact(BF.STATE_ABSENT, sig, 0)
unk = BF.TxFact(BF.STATE_UNKNOWN, sig, 0, "мост молчит")
base = S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB")
ok(S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB", tx=landed) == base,
   "факт доказан → текст БАЙТ-В-БАЙТ прежний")
ok(S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB", tx=None) == base,
   "расписки не теряли → текст БАЙТ-В-БАЙТ прежний")
t_abs = S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB", tx=absent)
ok("НЕ записал  -500 ฿" in t_abs and "запиши вручную" in t_abs, "RU: ABSENT → «НЕ записал»")
ok("บันทึกไม่สำเร็จ" in t_abs and "กรุณาบันทึกด้วยมือ" in t_abs, "TH: ABSENT → то же по-тайски")
ok("Записал  -500" not in t_abs, "слова «Записал» при ABSENT НЕТ")
t_unk = S.msg_recorded_cf(-500, {"THB": 1029.0}, "THB", tx=unk)
ok("НЕ ЗНАЮ" in t_unk and "прежде чем писать повторно" in t_unk,
   "RU: UNKNOWN → «не знаю» + предупреждение о повторе (дубль хуже потери)")
ok("ไม่ทราบว่าบันทึก" in t_unk and "ตรวจก่อนบันทึกซ้ำ" in t_unk, "TH: UNKNOWN → то же по-тайски")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(7) КЭШ: метка времени дописана СБОКУ — старый код читает файл как читал")
_reset_cache()
WC.save_wallet_balance("Самоорганизация", {"THB": 1529.0}, at=AT_1227)
with open(os.environ["WALLET_CACHE_FILE"], encoding="utf-8") as f:
    raw = json.load(f)
ok(raw.get("Самоорганизация") == {"THB": 1529.0},
   "кошелёк остался НА ВЕРХНЕМ УРОВНЕ — прежний код прочтёт его без правок")
ok(raw.get("__at__", {}).get("Самоорганизация") == AT_1227, "метка времени лежит отдельным ключом")
ok(WC.load_wallet_at("Самоорганизация") == AT_1227, "метка читается")
ok(WC.load_wallet_balance("__at__") == {}, "карта времён кошельком не притворяется")

_reset_cache()
with open(os.environ["WALLET_CACHE_FILE"], "w", encoding="utf-8") as f:
    json.dump({"Самоорганизация": {"THB": 1529.0}}, f)      # ЛЕГАСИ-файл: меток нет вовсе
ok(WC.load_wallet_balance("Самоорганизация") == {"THB": 1529.0}, "легаси-файл читается")
ok(WC.load_wallet_at("Самоорганизация") is None, "легаси: времени нет → None, а не выдумка")
v = WC.answer("Самоорганизация", DEAD_302)
ok(v.state == BF.STATE_STALE and v.at is None, "легаси-кэш + мёртвый мост → STALE «время неизвестно»")

_reset_cache()
v = WC.answer("Самоорганизация", LIVE_OK)
ok(v.fresh and WC.load_wallet_balance("Самоорганизация") == {"THB": 1029.0},
   "FRESH обновляет кэш")
ok(WC.load_wallet_at("Самоорганизация") is not None, "…и ставит метку времени")
_reset_cache()
ok(WC.answer("Самоорганизация", DEAD_302).state == BF.STATE_NONE, "мост молчит, кэша нет → NONE")
ok(not os.path.exists(os.environ["WALLET_CACHE_FILE"]),
   "молчание моста кэш НЕ создаёт и не портит")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(8) ЖИВОЙ ПУТЬ: сквозь _record_transaction, обе стороны + цена здорового пути")
SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send


class Msg:
    def __init__(self):
        self.text = "-500"
        self.caption = None
        self.photo = None
        self.chat_id = SELF_CHAT
        self.message_thread_id = None
        self.date = datetime.datetime(2026, 8, 13, 12, 27, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 4242
        self.from_user = type("U", (), {"username": "pleummmm", "id": 111})()


class FakeBridge:
    """Мост, чьё здоровье задаётся снаружи. Считает КАЖДОЕ обращение — цена доказывается счётчиком."""

    def __init__(self, tx_reply, bal_reply, summary=None):
        self.tx_reply, self.bal_reply, self.summary = tx_reply, bal_reply, summary
        self.calls = []

    def add_transaction(self, **kw):
        self.calls.append("add_transaction")
        return self.tx_reply

    def get_balance(self, **kw):
        self.calls.append("get_balance")
        return self.bal_reply

    def tx_summary(self, **kw):
        self.calls.append("tx_summary")
        return self.summary


PARSED = {"type": "transaction",
          "moves": [{"amount": -500, "currency": "THB", "category": "fuel", "bike": "", "deposit": None}]}


def run(bridge):
    SENDS.clear()
    asyncio.run(S._record_transaction(None, bridge, None, Msg(), PARSED, "Самоорганизация"))
    return "\n".join(SENDS)


# (а) здоровый путь — и он не платит НИ ОДНОГО лишнего обращения
_reset_cache()
b = FakeBridge({"ok": True, "saved": True}, LIVE_OK)
txt = run(b)
ok(b.calls == ["add_transaction", "get_balance"],
   "здоровый путь: РОВНО 2 обращения, перечитывания листа нет (цена = 0)")
ok("Баланс:\n  1 029 ฿" in txt and "Учтено  -500 ฿" in txt,
   "здоровый путь: свежий баланс и «Учтено» (Самоорганизация = подтверждение каждой записи)")
ok("НЕ СВЕРЕН" not in txt, "здоровый путь: слова «не сверено» нет")

# (б) ДОСЛОВНЫЙ 13.08: обе ноги моста мертвы, кэш держит 1529, лист на самом деле верен
_reset_cache()
WC.save_wallet_balance("Самоорганизация", {"THB": 1529.0}, at=AT_1227)
b = FakeBridge(TX_DEAD_302, DEAD_302,
               {"ok": True, "items": [{"amount": -500, "currency": "THB", "category": "fuel",
                                       "bike": "", "description": "-500"}]})
txt = run(b)
ok("tx_summary" in b.calls, "расписка потеряна → лист ПЕРЕЧИТАН")
ok("Баланс НЕ СВЕРЕН" in txt and "13.08 12:27 UTC" in txt,
   "13.08: баланс назван НЕ СВЕРЕННЫМ и названа дата — молчаливой подмены больше нет")
ok("ยอดยังไม่ได้ตรวจสอบ" in txt, "13.08: то же по-тайски")
ok("Учтено  -500 ฿" in txt,
   "проводка перечитана и НАЙДЕНА в листе → «Учтено» законно (лист 13.08 и правда верен)")
ok(WC.load_wallet_balance("Самоорганизация") == {"THB": 1529.0},
   "молчащий мост кэш НЕ перезаписал")

# (в) расписка потеряна И строки в листе нет → зовём записать руками
_reset_cache()
b = FakeBridge(TX_DEAD_302, LIVE_OK, {"ok": True, "items": []})
txt = run(b)
ok("НЕ записал  -500 ฿" in txt and "บันทึกไม่สำเร็จ" in txt,
   "строки в листе нет → «НЕ записал», на двух языках")

# (г) расписка потеряна и лист тоже не ответил → «не знаю», а не «записал»
_reset_cache()
b = FakeBridge(TX_DEAD_302, LIVE_OK, DEAD_302)
txt = run(b)
ok("НЕ ЗНАЮ" in txt and "Учтено  -500" not in txt,
   "лист не перечитан → «не знаю», записанной проводка НЕ считается")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(9) ОТКАТ: CASH_FACT=0 → путь кассы байт-в-байт прежний")
os.environ["CASH_FACT"] = "0"
try:
    _reset_cache()
    WC.save_wallet_balance("Самоорганизация", {"THB": 1529.0}, at=AT_1227)
    b = FakeBridge(TX_DEAD_302, DEAD_302, {"ok": True, "items": []})
    txt = run(b)
    ok(b.calls == ["add_transaction", "get_balance"],
       "откат: листа не перечитываем — обращений столько же, сколько было до правки")
    ok("Баланс:\n  1 529 ฿" in txt,
       "откат: прежнее поведение — кэш 1529 показан обычным балансом (та самая подмена)")
    ok("НЕ СВЕРЕН" not in txt and "НЕ записал" not in txt, "откат: новых слов в тексте нет")
finally:
    os.environ.pop("CASH_FACT", None)

_reset_cache()
b = FakeBridge(TX_DEAD_302, DEAD_302, {"ok": True, "items": []})
run(b)
ok("tx_summary" in b.calls, "ручку вернули → правка снова работает")

# ═════════════════════════════════════════════════════════════════════════════════════════════
section("(10) ГРАНИЦЫ: чужого не трогаем")
ok(S._balance_block("Баланс", {"THB": 1029.0}) == ["Баланс:", "  1 029 ฿"],
   "голый dict → блок баланса прежний байт-в-байт")
ok(S._balance_block("Баланс", {"THB": 1029.0, "EUR": 150})
   == ["Баланс:", "  1 029 ฿", "  150 EUR"], "мультивалютный блок прежний")
b_stale = BF.Balance(BF.STATE_STALE, {"THB": 1529.0, "EUR": 150}, AT_1227)
lines = S._balance_block("Баланс", b_stale)
ok(lines[0].startswith("⚠️") and "150 EUR" in lines[-1],
   "не сверено: пометка у ПЕРВОГО числа, прочие валюты на месте")
ok(S._when_utc(None) is None and S._when_utc("мусор") is None,
   "битая метка времени → None, а не выдуманная дата")
src = open("/root/turbobaby-manager-bot/balance_fact.py", encoding="utf-8").read()
ok(src.count("\nimport ") + src.count("\nfrom ") == 1,
   "у решения кассы РОВНО один импорт — спросить мост ему нечем")

# ─────────────────────────────────────────────────────────────────────────────────────────────
import shutil
shutil.rmtree(_CACHE_DIR, ignore_errors=True)
os.environ.pop("WALLET_CACHE_FILE", None)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
