"""wa_delivery.py — DELIVERY2210 (22.10.2026): доставка по зонам владельца для инструмента сверки `delivery`.

Живой случай …1754 («район и доставка»): дверь была заглушкой «неизвестно». Зоны — `delivery_zones_get` моста, живой
ПОЗИЦИОННЫЙ формат [name, lat, lon, price, radius_km] (dict-only резолвер ронял все 16 зон). Место клиента: аргумент
модели `place` или, если его нет, последние сообщения клиента из переписки (дверь history). Точка из ПОЛНОЙ ссылки
Google Maps / «lat, lon» — ближайший центр в пределах радиуса; иначе название района — по списку написаний зоны (RU/EN;
зона без списка — её имя). Две зоны, короткая ссылка, точка вне зон, пусто — «неизвестно» со словами, не факт. Факт
несёт `price` — опору чисел черновика (`wa_agent_tools.known_amounts`); денежные судьи не трогаются. Модуль отдельный
сознательно: замки модуля судей (`wa_agent_tools`) считают его выражения и строки-шаблоны.
"""
import math
import re

SRC = "зоны доставки владельца (delivery_zones_get)"
ZONE_ALIASES = {
    "Раваи": ("раваи", "равай", "rawai"), "Чалонг": ("чалонг", "chalong"),
    "Пхукет-таун": ("пхукет-таун", "пхукет таун", "phuket town", "old town", "олд таун", "старый город"),
    "Кейп Панва": ("панва", "panwa"), "Паклок": ("паклок", "pa khlok", "paklok", "pa klok"),
    "Таланг восток": ("таланг восток", "thalang east"), "Таланг север": ("таланг север", "thalang north"),
    "Майкхао": ("майкхао", "май кхао", "mai khao", "maikhao"), "Аэропорт": ("аэропорт", "airport"),
    "Найтон": ("найтон", "nai thon", "naithon"), "Сурин": ("сурин", "surin"), "Камала": ("камала", "kamala"),
    "Банг Тао": ("банг тао", "бангтао", "bang tao", "bangtao", "лагуна", "laguna"),
    "Патонг": ("патонг", "patong"), "Карон": ("карон", "karon"), "Ката": ("ката", "kata"),
}
SHORT = re.compile(r"(?i)maps\.app\.goo\.gl|goo\.gl/maps")
POINT = (re.compile(r"@(-?\d{1,2}\.\d{3,}),(-?\d{1,3}\.\d{3,})"),
         re.compile(r"(?i)[?&](?:q|ll|query|destination|center)=(-?\d{1,2}\.\d{3,})(?:,|%2C)\s*(-?\d{1,3}\.\d{3,})"),
         re.compile(r"(?<![\d.])(\d{1,2}\.\d{3,}),\s*(\d{2,3}\.\d{3,})(?![\d.])"))
HISTORY_TAIL = 6          # сообщений клиента с конца переписки, если модель места не назвала


def zones_of(raw):
    """Ответ двери → [(name, lat, lon, price, radius)] только из верных позиционных строк."""
    zs = raw.get("zones") if isinstance(raw, dict) else None
    out = []
    for z in zs if isinstance(zs, list) else []:
        if isinstance(z, (list, tuple)) and len(z) >= 5 and str(z[0] or "").strip():
            try:
                out.append((str(z[0]).strip(), float(z[1]), float(z[2]), float(z[3]), float(z[4])))
            except (TypeError, ValueError):
                continue
    return out


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = (math.sin(math.radians(c - a) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def point(place):
    for rx in POINT:
        m = rx.search(place)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if 7.4 <= lat <= 8.4 and 98.1 <= lon <= 98.6:          # Пхукет; иное — не точка Пхукета
                return lat, lon
    return None


def judge_history(zones, items):
    """Переписка (двери history) → решение по ПОСЛЕДНЕМУ сообщению клиента, где место названо однозначно или спорно:
    идём от нового к старому (новое место отменяет прежнее — Codex TB-REVIEW-2210-AUTOBOOK-LIVE-DELTA); сообщение без
    места пропускается. Ничего не нашлось — «неизвестно»."""
    texts = [str(it.get("text") or "") for it in (items or []) if isinstance(it, dict) and it.get("who") == "клиент"]
    for t in reversed([t for t in texts if t.strip()][-HISTORY_TAIL:]):
        kind, out = judge(zones, t)
        if kind == "fact" or not str(out).startswith("район не найден"):
            return kind, out
    return judge(zones, "")


def judge(zones, place):
    """Зоны + место → ("fact", факт) | ("unknown", слова)."""
    if not zones:
        return "unknown", "зоны доставки не прочитаны — неизвестно"
    place = str(place or "").strip()
    if not place:
        return "unknown", "место клиента не названо — спроси район или ссылку Google Maps"
    pt = point(place)
    if pt:
        dist, z = sorted((km(pt[0], pt[1], z[1], z[2]), z) for z in zones)[0]
        if dist <= z[4]:
            return "fact", {"kind": "delivery", "zone": z[0], "price": int(round(z[3])), "how": "точка",
                            "km": round(dist, 1)}
        return "unknown", "точка вне зон доставки (ближайшая «%s», %.1f км) — цену назовёт человек" % (z[0], dist)
    if SHORT.search(place):
        return "unknown", "короткая ссылка Google Maps — точку не вижу; спроси район или полную ссылку"
    low = place.lower().replace("ё", "е")
    hits = [z for z in zones
            if any(re.search(r"(?<![a-zа-я])%s(?![a-zа-я])" % re.escape(a), low)
                   for a in (ZONE_ALIASES.get(z[0]) or (z[0].lower(),)))]
    if len(hits) == 1:
        z = hits[0]
        return "fact", {"kind": "delivery", "zone": z[0], "price": int(round(z[3])), "how": "район"}
    if len(hits) > 1:
        return "unknown", "место подходит к нескольким зонам (%s) — уточни район" % ", ".join(z[0] for z in hits)
    return "unknown", "район не найден среди зон доставки — спроси ссылку Google Maps или скажи, что уточним"
