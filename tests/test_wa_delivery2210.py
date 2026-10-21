#!/usr/bin/env python3
"""DELIVERY2210 (22.10.2026): инструмент сверки delivery — зона и цена по зонам владельца (`delivery_zones_get`).

До правки дверь была заглушкой «двери delivery нет — неизвестно» (живой случай …1754: «район и доставка» — агент не знал
ничего). Зоны — живой ПОЗИЦИОННЫЙ формат [name, lat, lon, price, radius_km] (снят read-only, fixtures ПК-полосы
delivery_zones_get.live.json, 16 зон) — dict-only резолвер ронял все зоны (CLAUDE.md ПК). Сети и модели нет."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wa_agent_tools as T  # noqa: E402

LIVE = {"ok": True, "zones": [
    ["Раваи", 7.771, 98.327, 590, 4], ["Чалонг", 7.8465, 98.339, 590, 4], ["Пхукет-таун", 7.8804, 98.3923, 490, 4],
    ["Кейп Панва", 7.805, 98.412, 590, 4], ["Паклок", 7.9645, 98.4085, 490, 5], ["Таланг восток", 7.9256, 98.3672, 490, 5],
    ["Таланг север", 7.9931, 98.3655, 390, 5], ["Майкхао", 8.143, 98.302, 990, 6], ["Аэропорт", 8.1132, 98.3169, 690, 3],
    ["Найтон", 8.055, 98.276, 590, 4], ["Банг Тао", 7.991, 98.293, 290, 4], ["Сурин", 7.9788, 98.277, 290, 3],
    ["Камала", 7.9505, 98.283, 290, 4], ["Патонг", 7.8965, 98.2965, 290, 4], ["Карон", 7.8475, 98.2945, 390, 3],
    ["Ката", 7.82, 98.2985, 490, 3]]}


def fact(place):
    r = T.delivery_result(LIVE, 1.0, {"place": place})
    return r, (r["facts"][0] if r["outcome"] == T.FACT else None)


def test_by_name_ru_en():
    for place, zone, price in (("Раваи, вилла у моря", "Раваи", 590), ("Rawai beach", "Раваи", 590),
                               ("отель в Патонге? нет, Patong Beach Hotel", "Патонг", 290),
                               ("Laguna Phuket", "Банг Тао", 290), ("Kata Noi", "Ката", 490),
                               ("Cape Panwa Hotel", "Кейп Панва", 590)):
        r, f = fact(place)
        assert f and f["zone"] == zone and f["price"] == price and f["how"] == "район", (place, r)


def test_by_point_full_link():
    r, f = fact("https://www.google.com/maps/place/x/@7.7712,98.3265,17z")
    assert f and f["zone"] == "Раваи" and f["how"] == "точка" and f["price"] == 590, r
    r, f = fact("7.8970, 98.2970")
    assert f and f["zone"] == "Патонг", r


def test_unknowns_name_reason():
    for place, part in (("", "не названо"), ("https://maps.app.goo.gl/AbCdEf", "короткая ссылка"),
                        ("Kata Karon", "нескольким зонам"), ("Krabi town", "не найден"),
                        ("@7.6000,98.3000", "вне зон")):
        r, f = fact(place)
        assert f is None and r["outcome"] == T.UNKNOWN and part in r["reason"], (place, r)
    r = T.delivery_result({"ok": True, "zones": [{"name": "Раваи"}]}, 1.0, {"place": "Rawai"})
    assert r["outcome"] == T.UNKNOWN and "не прочитаны" in r["reason"], r


def test_wiring_price_is_anchor_and_door():
    r, f = fact("Rawai")
    assert 590 in T.known_amounts({}, [f], {"sums": {}, "diffs": []}), "цена зоны — опора чисел"
    assert T._fact_ref(f)["zone"] == "Раваи" and T._fact_ref(f)["price"] == 590
    r = T._read("delivery", {"place": "Rawai"}, {"delivery": lambda **k: LIVE})
    assert r["outcome"] == T.FACT and r["facts"][0]["zone"] == "Раваи", r
    r = T._read("delivery", {"place": "Rawai"}, {})
    assert r["outcome"] == T.UNKNOWN and "двери delivery нет" in r["reason"], r
    assert 'delivery {"place"' in T.TOOLS_BLOCK


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("FAIL", t.__name__, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
