"""ГЕЙТ E2b: ОДИН ПРОБЕГ — НЕ «ЗАМЕНА МАСЛА» (25.10.2026).

Перепись записей кол.I за 01–25.10: сообщение С ОДНИМ ПРОБЕГОМ («41920», «31973», «Эти работы на
37480», «บันทึก») мозг отдавал в `set_service` без вида или с видом «oil», которого человек не
называл; гейт E2b подставлял «oil» по умолчанию, бот выдавал карточку «Сделано: моторное масло», и
«да» доверенного клало в кол.I несуществующую замену (NINJA 400 6334 дважды: 38237 → 41928 →
41958, срок масла на 3721 км позже; NMAX 8952; CB 650R 3503; NMAX 4957; FORZA 8950 — висела).

Что держит сьют:
  (1) гейт заводит «масло» только при слове о масле в САМОМ сообщении; без него — вид «mileage»;
  (2) явный другой вид (gear/abs/airfilter/…) — как был; задним числом со словом о масле — как был;
  (3) bot.py ведёт «mileage» в `splinter.brain_mileage`, а не в карточку работ;
  (4) `brain_mileage`: доверенный — запись пробега + хвост `_after_mileage`, без карточки работ;
      не доверенный или число ниже записанного — вопрос о пробеге; мусор — ничего.
Мост и Telegram — заглушки; имена боевых операций склеены из кусков.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")

from unittest.mock import MagicMock   # noqa: E402

import claude_client as cc            # noqa: E402
import splinter as S                  # noqa: E402

BIKE = "TESTBIKE NINJA 400 9997"
CHAT, TOPIC = -1009000000044, 8814


def _client(text):
    bridge = MagicMock()
    bridge.find_bike.return_value = {"name": BIKE, "oil_last_km": 38237}
    c = cc.ClaudeClient.__new__(cc.ClaudeClient)
    c.bridge = bridge
    c._force_bike = BIKE
    c._force_mileage = None
    c._force_mileage_conf = ""
    c.pending_service_confirm = []
    c._user_message = text
    return c


def _gate(text, args):
    c = _client(text)
    res = json.loads(c._execute_tool("set_service", dict({"bike": BIKE}, **args)))
    return res, (c.pending_service_confirm[0] if c.pending_service_confirm else {})


# ============================================================================================
#  (1)–(2) ВИД РАБОТЫ — ПО СЛОВАМ ЧЕЛОВЕКА
# ============================================================================================
def test_bare_mileage_is_not_an_oil_change():
    """Живой случай NINJA 6334 17.10/25.10: Пым прислал только пробег — карточки «масло» нет."""
    for text, args in (("41920", {"current_km": 41920, "confirmed": True}),
                       ("41958", {"current_km": 41958, "confirmed": True}),
                       ("บันทึก", {"current_km": 31973, "service_type": "oil", "confirmed": True}),
                       ("Эти работы на 37480", {"current_km": 37480, "service_type": "oil"})):
        res, item = _gate(text, args)
        assert res.get("blocked") == "service_gate", res
        assert item.get("kind") == "mileage", (text, item)
        assert "только ПРОБЕГ" in res.get("ОБЯЗАТЕЛЬНО", ""), res          # мозгу: работу не придумывать


def test_twin_oil_named_by_human_stays_oil():
    """БЛИЗНЕЦЫ: о масле сказано — работа «масло», как было (в том числе задним числом)."""
    _, item = _gate("Замена масла на 1200", {"current_km": 1200, "service_type": "oil"})
    assert item.get("kind") == "oil" and not item.get("backdated"), item
    _, back = _gate("บันทึกการเปลี่ยนน้ำมันเครื่องครั้งล่าสุด 41928",
                    {"oil_last_km": 41928, "current_km": 41958, "service_type": "oil"})
    assert back.get("kind") == "oil" and back.get("backdated") is True and back.get("km") == 41928, back


def test_twin_other_explicit_kind_unchanged():
    _, item = _gate("поменяли масло в редукторе", {"current_km": 30100, "service_type": "gear"})
    assert item.get("kind") == "gear", item
    _, item2 = _gate("41000", {"current_km": 41000, "service_type": "airfilter"})
    assert item2.get("kind") == "airfilter", item2


def test_backdated_without_oil_word_is_just_mileage():
    """Живой круг 25.10 06:28: на «ยืนยัน» мозг повторил oil_last_km — без слова о масле это пробег."""
    _, item = _gate("ยืนยัน", {"oil_last_km": 41928, "current_km": 41958, "service_type": "oil"})
    assert item.get("kind") == "mileage" and item.get("km") == 41958, item


# ============================================================================================
#  (3) bot.py ведёт «mileage» в дверь пробега
# ============================================================================================
def test_bot_routes_mileage_to_brain_mileage():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "bot.py"), encoding="utf-8").read()
    i = src.find('it.get("kind") == "mileage"')
    assert i > 0, "в bot.py нет ветки вида «mileage»"
    j = src.find("splinter.brain_mileage(", i)
    k = src.find("splinter.sp_confirm_from_brain(", i)
    assert 0 < j < k, "«mileage» обязан уходить в brain_mileage раньше карточки работ"


# ============================================================================================
#  (4) brain_mileage
# ============================================================================================
class _User:
    def __init__(self, username):
        self.id, self.username, self.is_bot, self.first_name = 1, username, False, "T"


class _Msg:
    def __init__(self, username):
        self.chat_id, self.message_thread_id, self.from_user, self.date = CHAT, TOPIC, _User(username), None
        self.text, self.message_id = "41973", 999


class _Doors:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        self.saved = {n: getattr(S, n) for n in ("_odo_confirmed", "_after_mileage", "_ask_mileage_confirm",
                                                 "_mileage_q_forget")}

        def _odo(*a, **k):
            self.calls.append(("odo", a[4]))

        async def _after(*a, **k):
            self.calls.append(("after", a[5]))

        async def _ask(*a, **k):
            self.calls.append(("ask", a[4]))
        S._odo_confirmed, S._after_mileage, S._ask_mileage_confirm = _odo, _after, _ask
        S._mileage_q_forget = lambda *a, **k: None
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(S, k, v)
        return False


def _brain(username, km="41973", last=None):
    S._LAST_RECORDED_KM.pop((CHAT, TOPIC), None)
    if last is not None:
        S._LAST_RECORDED_KM[(CHAT, TOPIC)] = (last, 0)
    with _Doors() as d:
        asyncio.run(S.brain_mileage(None, MagicMock(), CHAT, TOPIC, BIKE, km, _Msg(username)))
    S._LAST_RECORDED_KM.pop((CHAT, TOPIC), None)
    return d.calls


def test_trusted_mileage_is_recorded_with_tail_no_card():
    assert _brain("Pleummmm") == [("odo", "41973"), ("after", "41973")]


def test_untrusted_mileage_asks_pym():
    assert _brain("testmech") == [("ask", "41973")]


def test_trusted_lower_than_recorded_asks():
    assert _brain("Pleummmm", km="14968", last=41958) == [("ask", "14968")]


def test_garbage_does_nothing():
    assert _brain("Pleummmm", km="12") == [] and _brain("Pleummmm", km="abc") == []


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
