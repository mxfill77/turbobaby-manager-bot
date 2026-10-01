# -*- coding: utf-8 -*-
"""Тесты wa_agent_knowledge (задание 0103-76t.0110): цена, «нужен человек», узлы, маска.
Только подделки: ни моста, ни модели, ни сети. Ответ двери — форма живого ответа CBQUOTE3009."""
import ast
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import wa_agent_knowledge as K
except ImportError:
    sys.path.insert(0, ROOT)
    import wa_agent_knowledge as K


def door_reply(days, day=416, total=None, deposit=15000):
    return {"action": "quote_price", "ok": True, "bike": "CB 300CC R 9011", "model": "HONDA CB 300R",
            "days": days, "day_price": day, "total": round(757 * days * 0.55) if total is None else total,
            "deposit": deposit, "available": True, "conflicts": 0,
            "season": {"label": "low", "global_discount": 0.15, "source": "x"},
            "cap_price": 9900, "cap_active": True, "text": "HONDA CB 300R | дней", "_status": 200}


class Door:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def __call__(self, unit, ds, de):
        self.calls.append((unit, ds, de))
        if self.exc:
            raise self.exc
        return self.reply


def units_cb(model):
    return ["CB 300CC R 9011"]


def no_digits(line):
    return re.search(r"\d", line or "") is None


def no_from_form(line):
    return re.search(r"(?i)(\bот|from)\s*\d", line or "") is None


# ------------------------------- цена -------------------------------

def test_one_season_number():
    d = Door(door_reply(27))
    r = K.quote("CB 300R", "2026-10-04", "2026-10-31", d, units_cb)
    assert r["outcome"] == K.PRICE_NUMBER, r
    assert (r["days"], r["day_price"], r["total"], r["deposit"]) == (27, 416, 11241, 15000), r
    assert "11 241 ฿" in r["line"] and "416 ฿ в сутки" in r["line"] and "15 000 ฿" in r["line"], r["line"]
    assert no_from_form(r["line"]) and len(d.calls) == 1 and d.calls[0][1:] == ("2026-10-04", "2026-10-31")


def test_dotted_dates_number():
    r = K.quote("CB 300R", "04.10.2026", "31.10.2026", Door(door_reply(27)), units_cb)
    assert r["outcome"] == K.PRICE_NUMBER and r["total"] == 11241


def test_peak_across_new_year_is_one_season():
    r = K.quote("CB 300R", "2026-12-20", "2027-01-05", Door(door_reply(16)), units_cb)
    assert r["outcome"] == K.PRICE_NUMBER, r


def test_season_border_human():
    d = Door(door_reply(11))
    r = K.quote("CB 300R", "2026-10-25", "2026-11-05", d, units_cb)
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_SEASON_CROSS, r
    assert d.calls == [] and r["total"] is None and no_digits(r["line"]) and no_from_form(r["line"])


def test_season_border_last_day_human():
    r = K.quote("CB 300R", "2026-10-20", "2026-11-01", Door(door_reply(12)), units_cb)
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_SEASON_CROSS, r


def test_long_term_human():
    d = Door(door_reply(30))
    r = K.quote("CB 300R", "2026-10-04", "2026-11-03", d, units_cb)
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_LONG_TERM and d.calls == [], r
    r = K.quote("CB 300R", "2027-06-01", "2027-06-30", Door(door_reply(29)), units_cb)
    assert r["outcome"] == K.PRICE_NUMBER, r


def test_model_without_price_human():
    d = Door(door_reply(7))
    r = K.quote("Vespa GTS", "2027-06-01", "2027-06-08", d, units_cb, no_price_models=("VESPA GTS",))
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_NO_PRICE_MODEL and d.calls == [], r
    r = K.quote("CB 300R", "2027-06-01", "2027-06-08", Door(door_reply(7, day=0, total=0)), units_cb)
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_NO_PRICE_MODEL, r
    r = K.quote("Ducati", "2027-06-01", "2027-06-08", Door(door_reply(7)), lambda m: [])
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_NO_PRICE_MODEL, r
    assert no_digits(r["line"])


def test_door_no_number_human():
    r = K.quote("CB 300R", "2027-06-01", "2027-06-08", Door({"ok": True, "available": True}), units_cb)
    assert r["outcome"] == K.PRICE_HUMAN and r["reason"] == K.R_DOOR_NO_PRICE, r
    assert r["total"] is None and no_digits(r["line"])


def test_door_silent_unknown_not_zero_not_from():
    for door in (Door(None), Door(exc=TimeoutError()), Door({"ok": False, "error": "x"}), Door("мусор")):
        r = K.quote("CB 300R", "2027-06-01", "2027-06-08", door, units_cb)
        assert r["outcome"] == K.PRICE_UNKNOWN, r
        assert r["total"] is None and r["day_price"] is None, r
        assert no_digits(r["line"]) and no_from_form(r["line"]) and "НЕИЗВЕСТНА" in r["line"], r


def test_fleet_unread_unknown_door_not_called():
    for units in (lambda m: None, lambda m: (_ for _ in ()).throw(OSError())):
        d = Door(door_reply(7))
        r = K.quote("CB 300R", "2027-06-01", "2027-06-08", d, units)
        assert r["outcome"] == K.PRICE_UNKNOWN and d.calls == [], r


def test_days_mismatch_unknown():
    r = K.quote("CB 300R", "2026-10-04", "2026-10-31", Door(door_reply(28)), units_cb)
    assert r["outcome"] == K.PRICE_UNKNOWN, r


def test_bad_dates_unknown():
    for ds, de in (("", "2027-06-08"), ("2027-06-08", "2027-06-01"), ("завтра", "потом")):
        r = K.quote("CB 300R", ds, de, Door(door_reply(7)), units_cb)
        assert r["outcome"] == K.PRICE_UNKNOWN, (ds, de, r)


def test_periods_cover_every_day_once():
    for year in (2027, 2028):
        day = datetime.date(year, 1, 1)
        while day.year == year:
            hits = [p for p in K.SEASON_PERIODS if K.period_of(day, (p,))]
            assert len(hits) == 1, (day, hits)
            day += datetime.timedelta(days=1)


# ------------------------------- «нужен человек» -------------------------------

def reasons(text, price=None):
    return [x["reason"] for x in K.handoff(text, price)]


def test_discount_human():
    assert K.R_DISCOUNT in reasons("а скидку дадите, если возьму надолго?")
    assert K.R_DISCOUNT in reasons("any discount for two weeks?")


def test_availability_human():
    assert reasons("свободен ли PCX на пятое?") == [K.R_AVAILABILITY]
    assert K.R_AVAILABILITY in reasons("is the NMAX available next week?")


def test_money_human():
    for t in ("байк повреждён после падения", "мне пришёл штраф", "когда вернёте депозит?",
              "я не согласен, это спорный вычет", "я уже оплатил вчера", "there is a scratch, damage",
              "I paid by transfer"):
        assert K.R_MONEY in reasons(t), t


def test_money_negatives():
    for t in ("хочу спортбайк на неделю", "I'm fine, thanks", "привет, сколько стоит PCX на неделю?",
              "hello, how much is a scooter for a week?"):
        assert reasons(t) == [], (t, reasons(t))


def test_language_human():
    for t in ("ราคาเท่าไหร่ครับ", "Скільки коштує байк на тиждень?", "Wie viel kostet der Roller pro Woche",
              "你好，摩托车多少钱"):
        assert K.R_LANGUAGE in reasons(t), t
    for t in ("Сколько стоит Honda PCX на неделю?", "How much is the PCX for a week?", "ok", "👍"):
        assert K.R_LANGUAGE not in reasons(t), t


def test_price_reason_goes_to_handoff():
    p = K.quote("CB 300R", "2026-10-25", "2026-11-05", Door(), units_cb)
    assert reasons("сколько стоит?", p) == [K.R_SEASON_CROSS]


# ------------------------------- узлы -------------------------------

def test_node_not_read_unknown():
    for rd in (lambda n: (_ for _ in ()).throw(TimeoutError()), lambda n: {"ok": False, "error": "quota", "text": "старое"},
               lambda n: {"ok": True, "text": "   "}, lambda n: "мусор"):
        node = K.read_node("faq", rd, now=1000.0)
        assert node["read"] is False and node["text"] is None and node["why"], node
        block = K.node_block(node, now=1000.0)
        assert "НЕИЗВЕСТНО" in block and block.strip(), block


def test_node_read_with_age():
    node = K.read_node("faq", lambda n: {"ok": True, "text": "ответ про доставку"}, now=1000.0)
    assert node["read"] and node["len"] == len("ответ про доставку")
    assert K.node_age(node, now=1300.0) == 300.0
    assert "снят 5 мин назад" in K.node_block(node, now=1300.0)


def test_knowledge_keeps_old_snapshot_on_failure():
    replies = [{"ok": True, "text": "правило"}, {"ok": True, "text": "faq"}]
    kn = K.Knowledge(lambda n: replies.pop(0) if replies else {"ok": False, "error": "x"}, max_age=600)
    kn.refresh(now=0.0)
    snap = kn.refresh(now=700.0)
    assert snap["faq"]["read"] and snap["faq"]["text"] in ("правило", "faq"), snap
    assert K.node_age(snap["faq"], now=700.0) == 700.0 and snap["faq"]["why"], snap
    kn2 = K.Knowledge(lambda n: {"ok": False, "error": "x"})
    s2 = kn2.refresh(now=0.0)
    assert all(not v["read"] and v["text"] is None for v in s2.values())


# ------------------------------- маска -------------------------------

SECRETS = (
    ("пароль: Qwerty123!", "Qwerty123"),
    ("мой пароль от wifi 12345678", "12345678"),
    ("password is hunter2x", "hunter2x"),
    ("код 4821, никому не говорите", "4821"),
    ("ключ AbC9dEf1GhI2jKl3", "AbC9dEf1GhI2jKl3"),
    ("вот sk-ant-api03-abcdefghijklmnop1234", "sk-ant-api03"),
    ("токен бота 123456789:AAFabcdefghijklmnopqrstuvwxyz012345", "AAFabcdefghij"),
    ("карта 4111 1111 1111 1111", "4111 1111 1111 1111"),
    ("логин ivan, а это Xk9mQ2vL7pR4tZ", "Xk9mQ2vL7pR4tZ"),
    ("https://x.example/cb?token=Zz9yYx8wWv7u&id=1", "Zz9yYx8wWv7u"),
)


def test_mask_catches_samples():
    for text, secret in SECRETS:
        out, n = K.mask(text)
        assert secret not in out and n >= 1 and "[скрыто:" in out, (text, out)


def test_mask_keeps_price_date_phone():
    text = ("Цена 11 241 ฿ за 27 суток, 416 ฿ в сутки, депозит 15 000 ฿, с 04.10.2026 по 31.10.2026 "
            "(2026-10-04), звоните +66 81 234 5678, +66812345678 или 89161234567, байк CB 300R, PCX160, "
            "в 10:00, ссылка https://maps.app.goo.gl/AbCdEf12345XyZ и www.turbobaby.example/bikes/pcx160")
    out, n = K.mask(text)
    assert out == text and n == 0, out


# ------------------------------- устройство -------------------------------

def test_imports_no_network():
    tree = ast.parse(open(K.__file__, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names == {"datetime", "re", "time"}, names


def test_bridge_contract():
    path = os.path.join(ROOT, "bridge_client.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    fns = {n.name: [a.arg for a in n.args.args] for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert fns.get("quote_price") == ["self", "bike", "date_start", "date_end"], fns.get("quote_price")
    assert fns.get("_call", [])[:2] == ["self", "action"], fns.get("_call")


def test_prompt_parts_sizes():
    p = K.quote("CB 300R", "2026-10-04", "2026-10-31", Door(door_reply(27)), units_cb)
    node = K.read_node("faq", lambda n: {"ok": True, "text": "x" * 100}, now=0.0)
    parts = K.prompt_parts(p, K.handoff("скидка?"), [node, K.read_node("business_rules", lambda n: None)], now=60.0)
    assert set(parts) == {"price", "handoff", "node:faq", "node:business_rules"}, parts
    assert "НЕИЗВЕСТНО" in parts["node:business_rules"] and "11 241" in parts["price"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    sys.exit(1 if bad else 0)
