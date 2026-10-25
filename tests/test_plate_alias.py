# -*- coding: utf-8 -*-
"""ПАРА «ТАБЛИЧКА ↔ ЗЕЛЁНАЯ КНИГА» В ПОИСКЕ БАЙКА (25.10.2026, PLATEALIAS2510).

Живой случай: по правилу владельца тема идёт по номеру, который висит на байке (тема 83 стала
«XADV 750CC GREY 2478»), а Лист1 после 24.10 несёт номер из зелёной книги («XADV 750CC GREY 9286»).
bridge_client.find_bike искал строку ТОЛЬКО по номеру из названия → тема не находила свою строку.
Проверяется: пара находит строку в обе стороны, без пары ничего не меняется, соседние номера
(4246/4248) не путаются, нет файла пар → прежний поиск.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import bridge_client
from bridge_client import BridgeClient

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


FLEET_BOOK = [   # Лист1 после 24.10 — номера из зелёной книги
    {"name": "XADV 750CC GREY 9286", "row": 37},
    {"name": "XMAX 300CC NEW BROWN 8676", "row": 32},
    {"name": "XSR 155CC GREEN 1023", "row": 27},
    {"name": "CB 300CC R 461", "row": 5},
    {"name": "ADV 350CC BLACK 5662", "row": 3},
    {"name": "XMAX 300CC GREEN 4248", "row": 24},
    {"name": "XMAX 300CC GREY 4246", "row": 25},
    {"name": "XADV 750CC BLACK 5104", "row": 34},
]


def client(bikes):
    c = BridgeClient(url="http://x/exec", token="T", timeout=1)
    c.fleet = lambda *a, **k: {"data": {"bikes": [dict(b) for b in bikes]}}
    return c


def use_aliases(path):
    bridge_client._PLATE_ALIASES_FILE = path
    bridge_client._PLATE_ALIASES = None


REAL = os.path.join(ROOT, "plate_aliases.json")

print("(1) живой файл пар читается:")
use_aliases(REAL)
m = bridge_client._plate_alias_map() or {}
ok(m.get("2478") == {"9286"} and m.get("9286") == {"2478"}, "83: 2478 ↔ 9286 (в обе стороны)")
ok(all(p in m for p in ("9315", "5849")), "пары 1190 и 62 на месте")
ok("7943" not in m and "9011" not in m and "1023" not in m and "461" not in m,
   "XSR 1023 и CB 461 без пар: книжные номера уже висят на байках (слово владельца 25.10)")

print("(2) тема по табличке находит строку Лист1 с книжным номером:")
c = client(FLEET_BOOK)
for q, row in (("XADV 750CC GREY 2478", 37), ("XMAX 300CC NEW BROWN 9315", 32),
               ("ADV 350CC BLACK 5849", 3)):
    ok(c.find_bike(q).get("row") == row, f"«{q}» → строка {row}")
ok(c.find_bike("XSR 155CC GREEN 1023").get("row") == 27, "XSR по книжному номеру — прямое совпадение")
ok(c.find_bike("CB 300CC R 461").get("row") == 5, "CB по книжному номеру — прямое совпадение")

print("(3) прежний поиск не изменился:")
ok(c.find_bike("XADV 750CC GREY 9286").get("row") == 37, "книжный номер — прямое совпадение")
ok(c.find_bike("XADV 750CC BLACK 5104").get("row") == 34, "байк без пары — как раньше")
ok(c.find_bike("XMAX 300CC GREY 4246").get("row") == 25, "4246 → своя строка, не 4248")
ok(c.find_bike("XMAX 300CC GREEN 4248").get("row") == 24, "4248 → своя строка, не 4246")
ok(c.find_bike("NMAX 155CC 9999") == {}, "неизвестный номер → пусто (пара ничего не выдумывает)")

print("(4) Лист1 перейдёт на номер таблички — найдётся и старое книжное название:")
FLEET_PHYS = [dict(b) for b in FLEET_BOOK]
FLEET_PHYS[0]["name"] = "XADV 750CC GREY 2478"
cp = client(FLEET_PHYS)
ok(cp.find_bike("XADV 750CC GREY 9286").get("row") == 37, "«…9286» → строка «…2478» (пара симметрична)")
ok(cp.find_bike("XADV 750CC GREY 2478").get("row") == 37, "«…2478» → прямое совпадение")

print("(5) файла пар нет / битый → прежнее поведение, без исключений:")
use_aliases(os.path.join(tempfile.gettempdir(), "no_such_plate_aliases_%d.json" % os.getpid()))
ok(client(FLEET_BOOK).find_bike("XADV 750CC GREY 2478") == {}, "нет файла → пары нет → пусто, как до правки")
bad = os.path.join(tempfile.mkdtemp(prefix="plate_alias_t"), "bad.json")
with open(bad, "w", encoding="utf-8") as f:
    f.write("{not json")
use_aliases(bad)
ok(client(FLEET_BOOK).find_bike("XADV 750CC GREY 2478") == {}, "битый файл → пусто, не падает")
use_aliases(REAL)

print("%d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
