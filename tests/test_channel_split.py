#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РАЗДЕЛЕНИЕ КАНАЛОВ ПО НАЗНАЧЕНИЮ (решение владельца, 05.08.2026).

ПРАВИЛО: инбокс 1160 — только то, на что владелец ОТВЕЧАЕТ (карточки красной зоны, кураторские
сводки с решением). Лента 829 — информационное, на что отвечать не надо. Отчёт в 328 — номер,
строка сути и ссылка; тело длиннее порога живёт в артефакте. Пустая очередь на ОБЕИХ полосах —
одно короткое сообщение, а не повтор каждые 45 секунд.

Четыре секции = четыре пункта регресса владельца, плюс граница «короткий отчёт не изменился».
Ни сети, ни Telegram, ни .env-секретов: `notify._send_message` подменён, токен подменён,
артефакты пишутся в REPORTS_DIR из окружения.

Запуск: PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_channel_split.py
"""
import os
import sys
import shutil
import asyncio
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
# Темы владельца берём ЛИТЕРАЛАМИ (прод-значения): регресс говорит про 1160 и 829, а не «про то,
# что стоит в .env». load_dotenv существующие переменные не перекрывает.
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
    except Exception as e:                       # до правки модуля/двери может не быть — это FAIL,
        ok(False, f"секция упала: {type(e).__name__}: {e}")   # а не крах всего прогона


# ── ДОСЛОВНЫЕ БОЕВЫЕ ТЕЛА (снимок очереди 05.08.2026) ────────────────────────────────────
BODY_SHORT = "проба видимости ok\n\nFACT: read-only"          # задача 15, 35 симв.

BODY_LONG = (
    "🧭 куратор: цель (задача 118) НЕ закрыта — остались зелёные хвосты.\n"
    "причина: Рестарт не нужен — демон уже на fc07efa (PID 267939, лог 11:47:30, задача 116 done); "
    "остался зелёный хвост: ложная красная карточка охранника держит задачу 117 и блокирует "
    "рестарт splinter.\n"
    "поставлены продолжения (from=Filipp-curator, корень 118):\n"
    "1. задача id 127: Задача 117 висит в needs_approval: headless объявил NEEDS_APPROVAL на "
    "рестарт splinter, хотя CLAUDE.md это запрещает (рестарт своих сервисов — оранжевый, в allow). "
    "Найди корень (pretool_guard.py, headless_settings.json, .claude/settings.json, преамбула "
    "демона), почини, добавь регресс-тест в tests/, прогони gate.py. Задачу 117 не трогать, "
    "красного не делать\n"
    "FACT: commit fc07efa в git log origin/main"
)                                                              # задача 126, >600 симв.

BODY_LONG_FAILED = (
    "[причина=exec_error · ошибка выполнения]: задача упала → думатель: halt, причина: exit=143 — "
    "процесс убит внешним SIGTERM (рестарт/kill/таймаут), а не дефект формулировки: текст ТЗ "
    "самодостаточен, переформулировка ничего не чинит; причина смерти неясна, задача read-only и "
    "упирается в решение владельца («утвержу — тогда код») — нужен человек.\n"
    "Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
    "claude -p упал (exit=143): exit=143 СЛЕДОВ РАБОТЫ в окне 03.08 04:08–04:18 UTC не найдено "
    "(коммитов 0, записей журнала 0) — судя по уликам, работа не начиналась либо оборвалась "
    "до первого следа."
)                                                              # задача 227, ровно 602 симв.

# Красная карточка гарда — дословный вид (pretool_guard._card): она ОБЯЗАНА остаться в 1160.
RED_CARD = ("🔴 ЖИВАЯ ТАБЛИЦА — НУЖНО ДА: запись ТО масла в Лист1 Байки\n"
            "Объект: NMAX 155 4957 · Число: 35200\n"
            "Что смотреть: строка байка в Лист1, колонка I")
# Информационное — то, ради чего правило и вводилось: ответа не ждёт, значит инбоксу не место.
INFO_MSG = "✅ Code-сессия завершена: задача 296, гейт зелёный, push сделан"


# ═════ (1) ДВЕРЬ В ИНБОКС: красное — в 1160, информационное — в ленту 829 ═════════════════
def sec1():
    import notify

    sent = []

    def fake_send(token, text, chat_id=None, thread_id=None, buttons=None):
        sent.append((chat_id, thread_id, text))
        return True, 4242

    orig_send, orig_token = notify._send_message, notify._get_token
    orig_count = os.environ.pop("NOTIFY_COUNT_FILE", None)
    orig_nopush = os.environ.pop("PRETOOL_NOPUSH", None)
    notify._send_message = fake_send
    notify._get_token = lambda: "TOKEN-МОК"                    # .env не читаем, сети нет
    try:
        r = notify.send_card(RED_CARD)
        ok(len(sent) == 1, f"красная карточка отправлена ровно 1 раз, факт {len(sent)}")
        ok(bool(sent) and sent[0][0] == notify.HQ_CHAT_ID, "красная карточка — в чат HQ")
        ok(bool(sent) and sent[0][1] == INBOX_TOPIC,
           f"красная карточка — в тему {INBOX_TOPIC}, факт {sent[0][1] if sent else '—'}")
        ok(bool(sent) and sent[0][2] == RED_CARD, "текст карточки не изменён")
        ok(r == (4242, notify.HQ_CHAT_ID), f"возврат прежней формы (mid, chat), факт {r}")

        sent.clear()
        r2 = notify.send_inbox(INFO_MSG, answerable=False)
        topics = [t for _c, t, _x in sent]
        ok(INBOX_TOPIC not in topics,
           f"«Code-сессия завершена» в {INBOX_TOPIC} НЕ приходит вовсе, факт темы {topics}")
        ok(topics == [FEED_TOPIC], f"информационное ушло в ленту {FEED_TOPIC}, факт {topics}")
        ok(r2 is None, "информационная дверь не возвращает id карточки (кнопок там нет)")

        # Ленты нет (адрес не задан) → сообщение НЕ уходит НИКУДА, а не «падает» в инбокс.
        sent.clear()
        os.environ["PC_DEV_TOPIC_ID"] = "0"
        notify.send_inbox(INFO_MSG, answerable=False)
        ok(sent == [], f"без адреса ленты информационное молчит, а не уходит в инбокс, факт {sent}")
        os.environ["PC_DEV_TOPIC_ID"] = str(FEED_TOPIC)

        # Инбокс выключен → красное падает в личку (прежний фолбэк цел).
        sent.clear()
        os.environ["INBOX_TOPIC_ID"] = "0"
        notify.send_card(RED_CARD)
        ok(bool(sent) and sent[0][0] is None and sent[0][1] is None,
           "инбокс выключен → красная карточка в личку (фолбэк не тронут)")
        os.environ["INBOX_TOPIC_ID"] = str(INBOX_TOPIC)
    finally:
        notify._send_message, notify._get_token = orig_send, orig_token
        if orig_count is not None:
            os.environ["NOTIFY_COUNT_FILE"] = orig_count
        if orig_nopush is not None:
            os.environ["PRETOOL_NOPUSH"] = orig_nopush


# ═════ (2) ЧИСТАЯ ФУНКЦИЯ: тело → итог + ссылка, короткое не трогаем ══════════════════════
def sec2():
    import report_digest as rd

    ok(rd.digest(BODY_SHORT) is None,
       "короткий отчёт (35 симв.) → None = карточка байт-в-байт прежняя")
    ok(rd.digest("x" * rd.CHAT_BODY_MAX) is None, "ровно порог → прежний путь (граница включительно)")
    ok(rd.digest("x" * (rd.CHAT_BODY_MAX + 1)) is not None, "порог+1 → режем")

    d = rd.digest(BODY_LONG)
    ok(d is not None and len(d) < len(BODY_LONG) // 2,
       f"длинный отчёт ужат более чем вдвое: {len(BODY_LONG)} → {len(d or '')}")
    ok(bool(d) and d.splitlines()[0].startswith("🧭 куратор: цель (задача 118) НЕ закрыта"),
       "первая строка карточки = сводка, назначенная самим исполнителем")
    ok(bool(d) and "FACT: commit fc07efa в git log origin/main" in d,
       "строка FACT: остаётся в чате — «done» не должен требовать нажатия, чтобы быть проверяемым")
    ok(bool(d) and "headless_settings.json" not in d, "тело отчёта в карточку не попало")

    d2 = rd.digest(BODY_LONG_FAILED)
    ok(bool(d2) and d2.startswith("[причина=exec_error"), "failed: сводка тоже берётся позицией")
    ok(bool(d2) and "FACT" not in d2, "нет FACT: — строка не выдумывается")

    ok(rd.digest("─────\n═════\n") is None, "короткая рамка — прежний путь")
    only_decor = ("─" * 40 + "\n") * 20
    d3 = rd.digest(only_decor)
    ok(bool(d3) and "итог не назван" in d3, "тело из одних разделителей → честная строка, не пустота")

    note = ("✂️ РЕЗУЛЬТАТ ОБРЕЗАН ДЕМОНОМ: полная длина 40000 симв., в очередь попало 4500 — "
            "срезано 35500 симв. (потолок RESULT_MAX=4500).")
    dcut = rd.digest(BODY_LONG + "\n\n" + note) or ""
    ok(note in dcut,
       "пометка обрезки едет ДОСЛОВНО (иначе обрубок выдан за полный отчёт)")
    ok("40000" in dcut and "35500" in dcut,
       "числа пометки в карточке: «обрезан» без «насколько» — та же дыра с другой стороны")

    art = rd.artifact_text(126, "done", "тз: почини", BODY_LONG)
    ok(BODY_LONG in art and "тз: почини" in art, "артефакт несёт ТЗ и отчёт дословно")


# ═════ (3) КАРТОЧКА В 328: номер + суть + ссылка; короткая — как была ═════════════════════
class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 1})()


class FakeCtx:
    def __init__(self, bot):
        self.bot = bot


def _reset(devbot):
    devbot._reported.clear()
    devbot._asked.clear()
    devbot._inprogress_seen.clear()
    devbot._stalled.clear()
    devbot._curator_pending.clear()
    devbot._report_seeded = True
    devbot._queue_busy = None
    devbot._closed_since_busy = []


def _snapshot(**kw):
    by = {st: [] for st in ("done", "failed", "needs_approval", "in_progress", "new", "approved")}
    by.update({k: v for k, v in kw.items()})
    return by


def _has_full_button(markup):
    """Под карточкой есть кнопка ПОЛНОГО отчёта (callback full:<id>), а не просто какие-то кнопки:
    до правки под done уже стояли 🔄/📋, и проверка «reply_markup есть» зелёная в обоих случаях."""
    try:
        return any(str(getattr(b, "callback_data", "")).startswith("full:")
                   for row in markup.inline_keyboard for b in row)
    except Exception:
        return False


def _run(devbot, by, bot):
    devbot._get_poll_bridge = lambda: object()
    devbot._poll_queue_sync = lambda pb: by
    devbot._drain_claim_events = lambda path=None: []
    asyncio.run(devbot.report_results(FakeCtx(bot)))


def sec3():
    tmp = tempfile.mkdtemp(prefix="tb_reports_")
    os.environ["REPORTS_DIR"] = tmp
    try:
        import devbot
        _reset(devbot)
        long_it = {"id": 126, "from": "Filipp-328-dev", "status": "done", "result": BODY_LONG,
                   "task_text": "тз: разбери цель 118", "updated": "2026-08-05T03:00:00Z"}
        bot = FakeBot()
        _run(devbot, _snapshot(done=[long_it]), bot)
        cards = [k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC]
        ok(len(cards) == 1, f"длинный отчёт = ОДНА карточка (было два чанка у 3500+), факт {len(cards)}")
        txt = cards[0]["text"] if cards else ""
        ok(txt.startswith("✅ Задача 126 — done"), "карточка начинается номером задачи и исходом")
        ok("🧭 куратор: цель (задача 118) НЕ закрыта" in txt, "строка сути на месте")
        ok("📄 отчёт целиком" in txt and "симв." in txt, "ссылка названа с длиной полного отчёта")
        ok("headless_settings.json" not in txt, "тело отчёта в чат не уехало")
        ok(len(txt) < 600, f"карточка короче порога, факт {len(txt)} симв.")
        ok(bool(cards) and _has_full_button(cards[0].get("reply_markup")),
           "под карточкой кнопка ПОЛНОГО отчёта (callback full:), а не только 🔄/📋")
        art = os.path.join(tmp, "2026-08-05", "task-126.md")
        ok(os.path.exists(art), f"артефакт записан: {art}")
        ok(os.path.exists(art) and BODY_LONG in open(art, encoding="utf-8").read(),
           "артефакт несёт тело ДОСЛОВНО")
        ok(os.path.relpath(art, tmp).replace(os.sep, "/") in txt or "task-126.md" in txt,
           "путь артефакта назван в карточке")

        # failed с длинным телом — тоже режется, и у него появляется кнопка (её раньше не было)
        _reset(devbot)
        bot = FakeBot()
        fail_it = {"id": 227, "from": "Filipp-328-dev", "status": "failed",
                   "result": BODY_LONG_FAILED, "task_text": "тз: смок", "updated": "2026-08-05T03:00:00Z"}
        _run(devbot, _snapshot(failed=[fail_it]), bot)
        ftxt = bot.sent[0]["text"] if bot.sent else ""
        ok(ftxt.startswith("❌ Задача 227 — failed"), "failed: номер и исход")
        ok("СЛЕДОВ РАБОТЫ" not in ftxt, "failed: тело не в чате")
        ok(bool(bot.sent) and _has_full_button(bot.sent[0].get("reply_markup")),
           "failed с урезанным телом получил кнопку полного отчёта (её у failed не было вовсе)")

        # ГРАНИЦА: короткий отчёт — байт-в-байт прежняя карточка, без ссылки и без 📄
        _reset(devbot)
        bot = FakeBot()
        short_it = {"id": 15, "from": "Filipp-328", "status": "done", "result": BODY_SHORT,
                    "task_text": "задача: проба", "updated": "2026-08-05T03:00:00Z"}
        _run(devbot, _snapshot(done=[short_it]), bot)
        stxt = bot.sent[0]["text"] if bot.sent else ""
        ok(BODY_SHORT in stxt, "короткий отчёт показан ЦЕЛИКОМ")
        ok("📄 отчёт целиком" not in stxt, "у короткого отчёта ссылки нет")
        ok(not os.path.exists(os.path.join(tmp, "2026-08-05", "task-15.md")),
           "у короткого отчёта артефакт не создаётся")
    finally:
        os.environ.pop("REPORTS_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)


# ═════ (4) СИГНАЛ «ОЧЕРЕДЬ ПУСТА»: ровно один на переход ══════════════════════════════════
def _idle_msgs(bot):
    return [k["text"] for k in bot.sent
            if k.get("message_thread_id") == DEV_TOPIC and "Очередь пуста" in str(k.get("text"))]


def sec4():
    import devbot
    _reset(devbot)
    busy = _snapshot(new=[{"id": 300, "from": "Filipp-328-dev", "status": "new",
                           "task_text": "тз: работай", "updated": "2026-08-05T03:00:00Z"}])
    empty = _snapshot()

    bot = FakeBot()
    _run(devbot, empty, bot)
    ok(_idle_msgs(bot) == [], "первый снимок пустой очереди (рестарт) сигнала НЕ рождает")

    bot = FakeBot()
    _run(devbot, busy, bot)
    ok(_idle_msgs(bot) == [], "пока очередь занята — сигнала нет")

    bot = FakeBot()
    done_it = {"id": 301, "from": "Filipp-328-dev", "status": "done", "result": BODY_SHORT,
               "task_text": "тз: работай", "updated": "2026-08-05T03:00:00Z"}
    _run(devbot, _snapshot(done=[done_it]), bot)
    msgs = _idle_msgs(bot)
    ok(len(msgs) == 1, f"переход в пустоту → РОВНО одно сообщение, факт {len(msgs)}")
    ok(bool(msgs) and "301" in msgs[0], f"названы номера закрытых, факт: {msgs[0] if msgs else '—'}")
    ok(bool(msgs) and len(msgs[0]) < 300, "сообщение короткое")

    bot = FakeBot()
    _run(devbot, empty, bot)
    ok(_idle_msgs(bot) == [], "пустота держится — повтора нет")
    bot = FakeBot()
    _run(devbot, empty, bot)
    ok(_idle_msgs(bot) == [], "и на третьем тике тоже нет")

    bot = FakeBot()
    _run(devbot, busy, bot)
    bot = FakeBot()
    _run(devbot, empty, bot)
    ok(len(_idle_msgs(bot)) == 1, "новая работа → новая пустота → снова ровно один сигнал")

    # Ждущая ответа карточка = очередь НЕ пуста (иначе «всё завершено» при висящем красном).
    _reset(devbot)
    bot = FakeBot()
    _run(devbot, busy, bot)
    bot = FakeBot()
    _run(devbot, _snapshot(needs_approval=[{"id": 302, "from": "Filipp-328-dev",
                                            "status": "needs_approval", "result": "op=other | ждём",
                                            "task_text": "тз: красное",
                                            "updated": "2026-08-05T03:00:00Z"}]), bot)
    ok(_idle_msgs(bot) == [], "открытая красная карточка держит очередь непустой")


section("(1) дверь в инбокс: красное → 1160, информационное → лента 829:", sec1)
section("(2) чистая функция отчёта: итог + ссылка, короткое не трогаем:", sec2)
section("(3) карточка 328: номер + суть + ссылка, артефакт на диске:", sec3)
section("(4) сигнал «очередь пуста»: ровно один на переход:", sec4)

print("\nИТОГ:", "ВСЕ PASS" if all(_res) else f"ЕСТЬ FAIL ({sum(_res)}/{len(_res)})")
raise SystemExit(0 if all(_res) else 1)
