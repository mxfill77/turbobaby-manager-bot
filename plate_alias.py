"""Пары номеров «табличка на байке ↔ зелёная книга» в поиске байка (25.10.2026, PLATEALIAS2510).

Правило владельца 25.10: тема идёт по номеру, который ВИСИТ НА БАЙКЕ; расхождение с зелёной книгой —
предупреждение. Лист1 после 24.10 несёт книжные номера, поэтому у части байков номер темы и номер
строки парка разные (сверка фото 25.10: тема 83 «…2478» против строки «…9286» и т.д.). Поиск байка
(`BridgeClient.find_bike`) ищет строку ТОЛЬКО по номеру из названия — тема с номером таблички свою
строку не находила: «Инфо», срок масла, верхняя граница пробега молчали.

ПОЧЕМУ ОТДЕЛЬНЫЙ МОДУЛЬ, А НЕ ПРАВКА bridge_client.py: файл закреплён отпечатком в приёмке контура
WhatsApp-договоров (tests/test_contractref_accept.py, tests/test_wa_book_ctx.py) — любая его правка
краснит чужие замки. Здесь — обёртка метода класса, ставится один раз процессом Splinter
(`install`); процессы WA-агента её не получают и ведут себя как прежде.

Пары — plate_aliases.json рядом с модулем; файла нет/битый → пар нет, поиск прежний. Пара
симметрична: когда Лист1 перейдёт на номер таблички, старое книжное название тоже найдётся.
"""
import json
import os
import re

ALIASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plate_aliases.json")
#: Кубатуры моторов — НЕ номер байка (зеркало правила `BridgeClient.find_bike`).
CC = {"125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"}
_MAP = None


def plate_of(text):
    """Номер байка из названия: последнее число ≥3 цифр, кроме кубатуры. Нет → None."""
    nums = [n for n in re.findall(r"\d{3,}", str(text or "").lower()) if n not in CC]
    return nums[-1] if nums else None


def alias_map(path=None):
    """{номер: {парные номера}} из файла пар, читается один раз. Нет/битый файл → None."""
    global _MAP
    if path is not None:
        _MAP = None
    if _MAP is None:
        try:
            with open(path or ALIASES_FILE, encoding="utf-8") as fh:
                pairs = json.load(fh).get("pairs") or []
            m = {}
            for p in pairs:
                a = str(p.get("on_bike") or "").strip()
                b = str(p.get("green_book") or "").strip()
                if a and b and a != b:
                    m.setdefault(a, set()).add(b)
                    m.setdefault(b, set()).add(a)
            _MAP = m
        except (OSError, ValueError, AttributeError):
            _MAP = False                              # не перечитывать файл на каждом вызове
    return _MAP or None


def partners(digits):
    """Парные номера по возрастанию. Пары нет → пустой кортеж."""
    m = alias_map()
    if m is None:
        return ()
    return tuple(sorted(m.get(str(digits or "").strip(), ())))


def wrap(find_bike):
    """Обёртка метода: сперва прежний поиск; промах и у номера есть пара → поиск по парному номеру."""
    if getattr(find_bike, "_plate_alias", False):
        return find_bike

    def find_bike_with_alias(self, query):
        found = find_bike(self, query)
        if found:
            return found
        for alt in partners(plate_of(query)):
            got = find_bike(self, alt)
            if got and plate_of(got.get("name", "")) == alt:
                return got
        return found

    find_bike_with_alias._plate_alias = True
    find_bike_with_alias.__wrapped__ = find_bike
    find_bike_with_alias.__doc__ = (find_bike.__doc__ or "") + "\n(+ пары табличка↔книга, plate_alias)"
    return find_bike_with_alias


def install(cls):
    """Поставить обёртку на `cls.find_bike` один раз (повторный вызов ничего не меняет).

    Не класс или нет метода `find_bike` (тесты подставляют `bridge_client.BridgeClient = lambda …`) →
    ничего не делает и не бросает: импорт Splinter не должен падать из-за обёртки поиска."""
    try:
        if isinstance(cls, type) and callable(getattr(cls, "find_bike", None)):
            cls.find_bike = wrap(cls.find_bike)
    except Exception:                                 # noqa: BLE001 — обёртка не смеет ронять импорт
        pass
    return cls
