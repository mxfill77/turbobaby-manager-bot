"""МУТАНТ-ТАБЛИЦА: ноль не от хранилища против КАЖДОЙ закрытой ветви, числом (21.09.2026).

Соседний сьют (`test_money_amount.py`) доказывает, что ветви отказывают. Этот отвечает на другой
вопрос — СКОЛЬКО денег проходило ДО правки и сколько проходит ПОСЛЕ, на одних и тех же мутантах.
Прогон «до» берётся не с другого дерева, а ТОЙ ЖЕ ручкой отката, которой правка и откатывается
(`MONEY_AMOUNT=0`): это строже worktree — доказывается, что ручка действительно возвращает
ПРЕЖНЕЕ поведение вместе с дефектом, а не просто «что-то меняет».

Считается ровно то, что стоит денег: СТРОКИ, ушедшие в живые листы кассы (`add_transaction`), и
ЧИСЛА, названные человеку. Мутанты — четыре способа получить ноль НЕ ОТ ХРАНИЛИЩА:
нет ключа (наш `.get`), `null`, строка и `nan` (все три — мостовой `Number(x) || 0`).

Сеть не дёргается ни разу; боевого кэша, боевой базы и боевых файлов состояния тест не касается.
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
_CACHE_DIR = tempfile.mkdtemp(prefix="tb_money_mut_")
os.environ["WALLET_CACHE_FILE"] = os.path.join(_CACHE_DIR, "wallet_cache.json")

import splinter as S

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))


PC_CHAT, PC_WALLET = -1003909369438, "Самоорганизация"
CF_CHAT = -1003873906891
SENDS = []


async def _rec_send(context=None, chat_id=None, text="", **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send
S._is_trusted = lambda m: True
S.pending_currency_for = lambda *a, **k: None


class Msg:
    def __init__(self, chat_id):
        self.text, self.caption, self.photo = "-500 бензин", None, None
        self.chat_id, self.message_thread_id = chat_id, None
        self.date = datetime.datetime(2026, 9, 21, 10, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 4242
        self.from_user = type("U", (), {"username": "pleummmm", "id": 111})()


class FakeClaude:
    def __init__(self, p):
        self.p = p

    def quick(self, *a, **kw):
        return self.p

    def vision(self, *a, **kw):
        return "{}"


class FakeBridge:
    def __init__(self, undo=None, check=None):
        self.undo_reply, self.check_reply = undo or {}, check or {}
        self.tx = []

    def get_balance(self, **kw):
        return {"ok": True, "balance": {"THB": 1029.0}}

    def add_transaction(self, **kw):
        self.tx.append(kw)
        return {"ok": True, "saved": True}

    def tx_summary(self, **kw):
        return {"ok": True, "items": []}

    def void_last(self, **kw):
        return self.undo_reply

    def check_balance(self, **kw):
        return self.check_reply


#: Подтверждение, УПАВШЕЕ после записи, — отдельный и худший исход, а не «просто ошибка»: строка
#: в листе уже стоит, а человек не услышал НИЧЕГО. Ловим и называем, а не даём сьюту развалиться.
CRASH = "⟪ПОДТВЕРЖДЕНИЕ УПАЛО: {}⟫"


def run(bridge, payload, chat_id=PC_CHAT):
    SENDS.clear()
    try:
        asyncio.run(S._handle_money(Msg(chat_id), None, bridge, FakeClaude(json.dumps(payload))))
    except Exception as e:                                  # noqa: BLE001 — предмет замера
        return "\n".join(SENDS) + CRASH.format(type(e).__name__)
    return "\n".join(SENDS)


NO_KEY = {"currency": "THB", "category": "fuel"}
NULL_AMT = {"amount": None, "currency": "THB", "category": "fuel"}
WORD_AMT = {"amount": "пятьсот", "currency": "THB", "category": "fuel"}
NAN_AMT = {"amount": float("nan"), "currency": "THB", "category": "fuel"}
MUT = (("нет ключа", NO_KEY), ("null", NULL_AMT), ("строка", WORD_AMT), ("nan", NAN_AMT))


def _rows(gate, make):
    """Сколько СТРОК ушло в листы кассы при данном положении ручки."""
    os.environ["MONEY_AMOUNT"] = gate
    total, texts = 0, []
    for _, mv in MUT:
        b = FakeBridge()
        texts.append(make(b, dict(mv)))
        total += len(b.tx)
    os.environ["MONEY_AMOUNT"] = "1"
    return total, texts


# ═════════════════════════════════════════════════════════════════════════════════════════════
print("\nВЕТВЬ В2 — проводка кассы (splinter._record_transaction, amount=mv.get(\"amount\", 0))")
mk2 = lambda b, mv: run(b, {"type": "transaction", "moves": [mv]})
before2, txt_before2 = _rows("0", mk2)
after2, txt_after2 = _rows("1", mk2)
print(f"  строк в лист: ДО правки {before2}/4, ПОСЛЕ {after2}/4")
ok(before2 == 4, "ДО: все четыре мутанта клали строку в живой лист (там она стала бы нулём)")
ok(after2 == 0, "ПОСЛЕ: ни одной строки — ветка отказала на всех четырёх")
ok(all("НЕ записал" in t for t in txt_after2), "ПОСЛЕ: каждому мутанту сказан третий исход")
ok(not any("НЕ записал" in t for t in txt_before2), "ДО: человек слышал подтверждение записи")
# ХУДШИЙ ИСХОД ИЗ ЗАМЕРЕННЫХ, найден прогоном, а не рассуждением: у нечислового `amount` строка
# в лист УЖЕ УШЛА, а подтверждение упало на `_sign("пятьсот")` — человек не услышал ничего.
crashed_before = [n for (n, _), t in zip(MUT, txt_before2) if "ПОДТВЕРЖДЕНИЕ УПАЛО" in t]
print(f"  подтверждение падало ПОСЛЕ записи: ДО правки {crashed_before}, ПОСЛЕ "
      f"{[n for (n, _), t in zip(MUT, txt_after2) if 'ПОДТВЕРЖДЕНИЕ УПАЛО' in t]}")
ok(crashed_before == ["строка"],
   "ДО: нечисловая сумма — строка в листе есть, подтверждения НЕТ (упало на _sign)")
ok(not any("ПОДТВЕРЖДЕНИЕ УПАЛО" in t for t in txt_after2),
   "ПОСЛЕ: ни одного падения — отказ наступает ДО записи и до текста")
ok("-nan ฿" in txt_before2[3] or "nan" in txt_before2[3],
   "ДО: nan доезжал до человека как «-nan ฿» и до листа — там он стал бы пустой ячейкой")

print("\nВЕТВЬ В3 — перенос в мелкую кассу (plus = abs(money_amount or 0))")
mk3 = lambda b, mv: run(b, {"type": "transaction", "transfer_to_pettycash": True,
                            "moves": [mv]}, chat_id=CF_CHAT)


def _pc_rows(gate):
    os.environ["MONEY_AMOUNT"] = gate
    n, texts = 0, []
    for _, mv in MUT:
        b = FakeBridge()
        texts.append(mk3(b, dict(mv)))
        n += sum(1 for t in b.tx if t.get("group") == PC_WALLET)
    os.environ["MONEY_AMOUNT"] = "1"
    return n, texts


before3, txt_before3 = _pc_rows("0")
after3, txt_after3 = _pc_rows("1")
crashed3 = [n for (n, _), t in zip(MUT, txt_before3) if "ПОДТВЕРЖДЕНИЕ УПАЛО" in t]
print(f"  строк в МЕЛКУЮ КАССУ: ДО правки {before3}/4, ПОСЛЕ {after3}/4; "
      f"падений ДО: {crashed3}")
ok(before3 == 3, "ДО: ноль из ветки запасного значения клал строку в ЧУЖОЙ кошелёк — 3 из 4")
ok(crashed3 == ["строка"],
   "ДО: четвёртый не «прошёл», а УПАЛ на abs(\"пятьсот\") — уже ПОСЛЕ строки в основном кошельке")
ok(after3 == 0, "ПОСЛЕ: ни одной строки в мелкую кассу")
ok("Пополнение  +0 ฿" in txt_before3[0] and "Пополнение  +0 ฿" in txt_before3[1],
   "ДО: в ЧУЖУЮ группу уходило дословно «Пополнение  +0 ฿»")
ok("Пополнение  +nan ฿" in txt_before3[3],
   "ДО: а nan доезжал туда же как «Пополнение  +nan ฿»")
ok(not any("Пополнение" in t for t in txt_after3), "ПОСЛЕ: этого сообщения нет вовсе")

print("\nВЕТВЬ В4 — отмена последней записи (res.get(\"amount\", 0) / res.get(\"balance\", {}))")
UNDO_MUT = (("voided без суммы", {"ok": True, "voided": True, "description": "бензин"}),
            ("мост молчит", {}),
            ("отказ моста", {"ok": False, "error": "request_failed"}))


def _undo(gate):
    os.environ["MONEY_AMOUNT"] = gate
    out = [run(FakeBridge(undo=r), {"type": "undo"}) for _, r in UNDO_MUT]
    os.environ["MONEY_AMOUNT"] = "1"
    return out


b4, a4 = _undo("0"), _undo("1")
zero_after = sum(1 for t in a4 if "+0 ฿" in t or "-0 ฿" in t)
print(f"  ложных нулей человеку: ДО правки 1/3, ПОСЛЕ {zero_after}/3")
# ЗНАК ТОЖЕ ВРАЛ, и не в ту сторону, в какую ждали: `_sign(None)` даёт «+», потому что
# `(None or 0) >= 0`. Отмена РАСХОДА печаталась как «+0 ฿» — приход. Замерено, не предположено.
ok("Отменил последнюю запись:  +0 ฿" in b4[0],
   "ДО: «Отменил последнюю запись:  +0 ฿» — ноль вместо суммы, да ещё со знаком прихода")
ok("Баланс:" in b4[0] and "0 ฿" in b4[0],
   "ДО: и «Баланс: 0 ฿» как СВЕЖЕЕ число (пустой dict → STATE_FRESH)")
ok("Нечего отменять" in b4[1] and "Нечего отменять" in b4[2],
   "ДО: молчание и отказ моста звучали утверждением о хранилище")
ok(zero_after == 0, "ПОСЛЕ: ни одного нуля вместо суммы")
ok("НЕ ЗНАЮ" in a4[1] and "НЕ ЗНАЮ" in a4[2], "ПОСЛЕ: у молчания моста свой, третий исход")

print("\nВЕТВЬ В5 — сверка баланса (res.get(\"diff\", 0))")
CHK_MUT = (("diff нет", {"ok": True, "match": False, "bot_balance": 1029.0}),
           ("diff=null", {"ok": True, "match": False, "bot_balance": 1029.0, "diff": None}),
           ("bot_balance нет", {"ok": True, "match": False, "diff": 129.0}))


def _chk(gate):
    os.environ["MONEY_AMOUNT"] = gate
    out = [run(FakeBridge(check=r), {"type": "balance_check", "balance": {"THB": 900}})
           for _, r in CHK_MUT]
    os.environ["MONEY_AMOUNT"] = "1"
    return out


b5, a5 = _chk("0"), _chk("1")
said_zero_after = sum(1 for t in a5 if "разница:   0 ฿" in t)
crashed5 = [n for (n, _), t in zip(CHK_MUT, b5) if "ПОДТВЕРЖДЕНИЕ УПАЛО" in t]
print(f"  ДО: «разница 0 ฿» 1/3, падений {crashed5}; ПОСЛЕ: «разница 0 ฿» {said_zero_after}/3")
ok("разница:   0 ฿" in b5[0],
   "ДО: расхождение объявлялось нулевым, то есть отрицало само себя")
ok(crashed5 == ["diff=null"],
   "ДО: `diff: null` не печатал ноль, а ронял ответ на abs(None) — человек не слышал ничего")
ok("None ฿" in b5[2], "ДО: пустой bot_balance печатался человеку дословно как «None ฿»")
ok(said_zero_after == 0, "ПОСЛЕ: ноль на месте расхождения не печатается ни разу")
ok(all("числа не назвала" in t for t in a5), "ПОСЛЕ: сказано, что числа нет")
ok(not any("ПОДТВЕРЖДЕНИЕ УПАЛО" in t for t in a5), "ПОСЛЕ: и ни одного падения")

print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
