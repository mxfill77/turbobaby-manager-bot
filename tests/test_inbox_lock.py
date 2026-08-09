#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗАМОК ИНБОКСА: спрашивающее не уходит мимо 1160, молчаливое туда не попадает (09.08.2026).

ЧТО ЗДЕСЬ ПРОВЕРЯЕТСЯ И ЧЕГО ЗДЕСЬ НЕТ. Дверь `notify.send_inbox(text, answerable)` заведена
05.08.2026, и её оба направления уже покрыты `tests/test_channel_split.py` (секция 1), а путь
аудита contradiction/HIGH — `tests/test_audit_inbox.py` (B1–B5). Дублировать их здесь нечем и
незачем. Этот файл закрывает ОСТАТОК, записанный тогда же дословно: дверь была «контракт, а не
забор» — ничто не мешало новому отправителю взять адрес инбокса самому.

Два замка, по одному на направление:

  ЗАБОР (страж `INBOX_SINGLE_DOOR`, ast, в гейте) — внутри notify.py в инбокс ведёт РОВНО одна
  дверь. Проверяется не чтением докстринга, а подделками живого исходника: функция, которая
  берёт адрес сама; дверь без параметра `answerable`; новая отправка в Telegram.

  ЗАМОК (`devbot._inbox_lock_topic`) — карточка с кнопкой ВЕРДИКТА (`approve:`/`reject:`) уезжает
  в инбокс, что бы вызывающий ни посчитал темой. Признак — факт об отправляемом объекте
  (callback_data реальной клавиатуры), а не слово в тексте: подпись переписать можно, callback
  есть то, что нажатие сделает.

ГРАНИЦА ЗАМКА ВАЖНА НЕ МЕНЬШЕ САМОГО ЗАМКА: кнопки навигации (🔄 Проверь / 📋 Дальше) и ссылка
«📄 отчёт» ответом НЕ являются. Замок, который тащил бы в инбокс любую кнопку, сам наносил бы
дефект, ради которого заведён, — поэтому карточка done с «📄 отчёт» обязана остаться в теме
постановки, и это проверяется наравне с положительным случаем.

Клавиатуры берутся у ЖИВОГО производителя (`devbot._kb_approval` / `_kb_done` / `_kb_full`),
а не собираются моком: разъедутся формы — тест покраснеет здесь, а не в теме у владельца.

Ни сети, ни Telegram, ни .env-секретов, ни боевых файлов состояния: `context.bot` фиктивный,
темы заданы литералами прод-значений.

Запуск: PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_inbox_lock.py
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
# Темы — ЛИТЕРАЛЫ прод-значений: регресс говорит про 1160/829/328, а не «про то, что в .env».
# load_dotenv существующие переменные не перекрывает.
os.environ["INBOX_TOPIC_ID"] = "1160"
os.environ["PC_DEV_TOPIC_ID"] = "829"

INBOX_TOPIC = 1160
FEED_TOPIC = 829
DEV_TOPIC = 328

_res = []


def ok(cond, msg):
    _res.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'} - {msg}")


def section(title, fn):
    print(title)
    try:
        fn()
    except Exception as e:                                    # до правки модуля может не быть —
        ok(False, f"секция упала: {type(e).__name__}: {e}")   # это FAIL, а не крах прогона


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeBot:
    """Пишет вызовы send_message; сети нет."""

    def __init__(self):
        self.calls = []            # [(chat_id, thread_id, text, has_markup)]

    async def send_message(self, **kw):
        self.calls.append((kw.get("chat_id"), kw.get("message_thread_id"),
                           kw.get("text"), kw.get("reply_markup") is not None))
        return type("M", (), {"message_id": 777})()


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


class FakeQuery:
    """Нажатая карточка: у неё есть тема, из которой прежде брался адрес продолжения."""

    def __init__(self, thread_id):
        self.message = type("Msg", (), {"message_thread_id": thread_id})()


# ═════ (1) ЗАБОР: в инбокс внутри notify.py ведёт РОВНО одна дверь ════════════════════════
def sec_fence():
    import invariants_check as ic

    src = open(os.path.join(ic.REPO, "notify.py"), encoding="utf-8").read()
    ok(ic._door_ast_findings(src) == [],
       "живой notify.py: дверь единственная, страж молчит")

    # (а) новый отправитель берёт адрес инбокса САМ — ровно тот «Code-сессия завершена»,
    #     из-за которого правило и заводится.
    bypass = src + (
        "\n\ndef say_done(text):\n"
        "    dest = _inbox_dest()\n"
        "    token = _get_token()\n"
        "    return _send_message(token, text, chat_id=dest[0], thread_id=dest[1])\n"
    )
    f = ic._door_ast_findings(bypass)
    ok(any("_inbox_dest" in w for w, _y in f),
       "обход двери: адрес инбокса взят мимо маршрута — страж флагует")
    ok(any("say_done" in y for _w, y in f),
       "страж НАЗЫВАЕТ обходчика по имени, а не сообщает «что-то не так»")
    ok(any("_send_message" in w for w, _y in f),
       "новая отправка в Telegram замечена отдельным флагом")

    # (б) у двери пропал признак маршрута.
    noflag = src.replace("def send_inbox(text, answerable):", "def send_inbox(text):")
    ok(noflag != src, "подделка «дверь без признака» действительно построена")
    ok(any("answerable" in y for _w, y in ic._door_ast_findings(noflag)),
       "дверь без параметра «answerable» — страж флагует: признак обязан быть назван")

    # (в) маршрут инбокса зовут в обход двери.
    second = src.replace("def send_card(text):",
                         "def send_now(text):\n    return _send_inbox_card(text)\n\n\n"
                         "def send_card(text):")
    ok(second != src, "подделка «второй вход в маршрут» действительно построена")
    ok(any("_send_inbox_card" in w for w, _y in ic._door_ast_findings(second)),
       "второй вход в маршрут инбокса — страж флагует")

    # (г) FAIL-CLOSED: правило не должно молча зеленеть, потеряв предмет.
    ok(any("предмет" in y for _w, y in
           ic._door_ast_findings("def send_inbox(text, answerable):\n    return None\n")),
       "предмет пропал (двери некуда вести) → флаг, а не молчаливое зелёное")

    # (д) страж зарегистрирован в гейте, а не просто существует функцией.
    ok(any(n == "INBOX_SINGLE_DOOR" for n, _fn in ic.CHECKS),
       "страж зарегистрирован среди инвариантов")


# ═════ (2) НАПРАВЛЕНИЕ A: молчаливое в инбокс НЕ попадает ═════════════════════════════════
def sec_silent_not_in_inbox():
    import devbot

    # (а) карточка done с ссылкой «📄 отчёт»: кнопка есть, ответа не ждёт → тема постановки.
    for label, markup in (("done + 📄 отчёт", devbot._kb_done(42, full=True)),
                          ("done без ссылки", devbot._kb_done(42)),
                          ("failed + 📄 отчёт", devbot._kb_full(42))):
        got = devbot._inbox_lock_topic(DEV_TOPIC, markup, 42)
        ok(got == DEV_TOPIC,
           f"{label}: остаётся в теме постановки {DEV_TOPIC}, факт {got}")

    # (б) сообщение вовсе без кнопок (heartbeat, «зависла», сводка) — тема не трогается.
    ok(devbot._inbox_lock_topic(DEV_TOPIC, None, 42) == DEV_TOPIC,
       "без клавиатуры замок не вмешивается (heartbeat/сводка остаются в 328)")
    ok(devbot._inbox_lock_topic(FEED_TOPIC, None, 42) == FEED_TOPIC,
       "заметка ленты 829 замком в инбокс не утаскивается")

    # (в) реальная доставка: карточка done уходит именно в 328, инбокс не задет.
    ctx = FakeContext()
    run(devbot._send_card_with_retry(ctx, 42, ["итог задачи 42"], DEV_TOPIC,
                                     devbot._kb_done(42, full=True), "done"))
    topics = [t for _c, t, _x, _m in ctx.bot.calls]
    ok(topics == [DEV_TOPIC], f"итог задачи доставлен в {DEV_TOPIC}, факт {topics}")
    ok(INBOX_TOPIC not in topics, f"итог задачи в {INBOX_TOPIC} НЕ попадает вовсе")


# ═════ (3) НАПРАВЛЕНИЕ B: спрашивающее мимо инбокса не уходит ═════════════════════════════
def sec_asking_goes_to_inbox():
    import devbot

    kb = devbot._kb_approval(43)
    ok(devbot._is_verdict_markup(kb), "клавиатура ✅/❌ опознана как кнопка вердикта")
    ok(not devbot._is_verdict_markup(devbot._kb_done(43, full=True)),
       "🔄/📋/📄 вердиктом НЕ считаются (иначе замок сам натаскал бы информационное)")

    # (а) вызывающий посчитал тему 328 — замок уводит в инбокс.
    got = devbot._inbox_lock_topic(DEV_TOPIC, kb, 43)
    ok(got == INBOX_TOPIC, f"вопрос из темы {DEV_TOPIC} уведён в инбокс, факт {got}")
    got_pc = devbot._inbox_lock_topic(FEED_TOPIC, kb, 43)
    ok(got_pc == INBOX_TOPIC, f"вопрос полосы pc ({FEED_TOPIC}) уведён в инбокс, факт {got_pc}")

    # (б) реальная доставка через узкое место: тема подменена ДО отправки, текст не тронут.
    ctx = FakeContext()
    body = "⚠️ Задача 43 [vps] требует подтверждения красной зоны"
    run(devbot._send_card_with_retry(ctx, 43, [body], DEV_TOPIC, kb, "вопрос-конверт"))
    ok([t for _c, t, _x, _m in ctx.bot.calls] == [INBOX_TOPIC],
       f"карточка-вопрос доставлена в {INBOX_TOPIC}, факт "
       f"{[t for _c, t, _x, _m in ctx.bot.calls]}")
    ok(ctx.bot.calls and ctx.bot.calls[0][2] == body, "текст карточки НЕ изменён — только адрес")
    ok(ctx.bot.calls and ctx.bot.calls[0][3], "кнопки на месте (карточка осталась карточкой)")

    # (в) многочанковая карточка: кнопки на последнем чанке, тема инбокса у ВСЕХ чанков.
    ctx = FakeContext()
    run(devbot._send_card_with_retry(ctx, 44, ["чанк 1", "чанк 2"], DEV_TOPIC,
                                     devbot._kb_approval(44), "вопрос-конверт"))
    ok(all(t == INBOX_TOPIC for _c, t, _x, _m in ctx.bot.calls),
       "все чанки вопроса — в инбоксе (карточка не рвётся между темами)")

    # (г) продолжение после стейл-ответа: нажата легаси-карточка в 328 → новый вопрос в инбокс.
    ctx = FakeContext()
    run(devbot._send_stale_followup(ctx, FakeQuery(DEV_TOPIC),
                                    {"id": 45, "result": "следующий вопрос"}))
    topics = [t for _c, t, _x, _m in ctx.bot.calls]
    ok(topics == [INBOX_TOPIC],
       f"следующий открытый вопрос уехал в инбокс, а не в тему нажатой карточки, факт {topics}")


# ═════ (4) ГРАНИЦЫ: замок не ломает штатные режимы ════════════════════════════════════════
def sec_borders():
    import devbot

    kb = devbot._kb_approval(46)

    # (а) инбокс ВЫКЛЮЧЕН → прежнее поведение по полосам, без регресса и без выдумывания темы.
    os.environ["INBOX_TOPIC_ID"] = "0"
    try:
        ok(devbot._inbox_lock_topic(DEV_TOPIC, kb, 46) == DEV_TOPIC,
           "инбокс выключен → вопрос идёт по теме вызывающего (режим «инбокса нет» цел)")
        ok(devbot._inbox_lock_topic(FEED_TOPIC, kb, 46) == FEED_TOPIC,
           "инбокс выключен → вопрос полосы pc остаётся в теме pc")
    finally:
        os.environ["INBOX_TOPIC_ID"] = str(INBOX_TOPIC)

    # (б) инбокс — мусор в env → та же ветка «выключено», а не исключение.
    os.environ["INBOX_TOPIC_ID"] = "не-число"
    try:
        ok(devbot._inbox_lock_topic(DEV_TOPIC, kb, 46) == DEV_TOPIC,
           "мусор в INBOX_TOPIC_ID → тема вызывающего, замок не падает")
    finally:
        os.environ["INBOX_TOPIC_ID"] = str(INBOX_TOPIC)

    # (в) тема УЖЕ инбокс → замок ничего не меняет (идемпотентность).
    ok(devbot._inbox_lock_topic(INBOX_TOPIC, kb, 46) == INBOX_TOPIC,
       "тема уже инбокс → замок оставляет как есть")

    # (г) чужая/битая клавиатура → замок молчит, а не гадает.
    class Broken:
        @property
        def inline_keyboard(self):
            raise RuntimeError("битый объект")

    ok(devbot._is_verdict_markup(Broken()) is False, "битая клавиатура → не вердикт (fail-safe)")
    ok(devbot._inbox_lock_topic(DEV_TOPIC, Broken(), 46) == DEV_TOPIC,
       "битая клавиатура темы не меняет")
    ok(devbot._is_verdict_markup(object()) is False, "чужой объект вердиктом не считается")
    ok(devbot._is_verdict_markup(None) is False, "нет клавиатуры → не вердикт")

    # (д) признак — callback, а не подпись: кнопка «✅ Да, деплой» без approve-callback вопросом
    #     не является, и наоборот — approve-callback под любой подписью является.
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    looks_like = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да, деплой",
                                                             callback_data="check:46")]])
    ok(not devbot._is_verdict_markup(looks_like),
       "подпись «✅ Да, деплой» без approve-callback вердиктом НЕ считается")
    plain_name = InlineKeyboardMarkup([[InlineKeyboardButton("посмотреть",
                                                             callback_data="reject:46")]])
    ok(devbot._is_verdict_markup(plain_name),
       "callback reject: под нейтральной подписью — вердикт (судим по действию, не по слову)")


print("=" * 78)
print("ЗАМОК ИНБОКСА: спрашивающее — в 1160, молчаливое — мимо (09.08.2026)")
print("=" * 78)
section("\n(1) ЗАБОР: в инбокс ведёт ровно одна дверь", sec_fence)
section("\n(2) НАПРАВЛЕНИЕ A: молчаливое в инбокс не попадает", sec_silent_not_in_inbox)
section("\n(3) НАПРАВЛЕНИЕ B: спрашивающее мимо инбокса не уходит", sec_asking_goes_to_inbox)
section("\n(4) ГРАНИЦЫ: штатные режимы не сломаны", sec_borders)

_p = sum(1 for x in _res if x)
print("\n" + "=" * 78)
print(f"ИТОГ: {_p}/{len(_res)}")
print("=" * 78)
sys.exit(0 if _p == len(_res) else 1)
