#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""НАХОДКА ПО ЗАМОРОЖЕННОМУ КОНТУРУ НЕ РОЖДАЕТ КАРТОЧКУ (06.08.2026).

ЖИВОЙ ФАКТ: сводная карточка ревизора 244 копилась 30.3 ч (03.08 13:20 → 04.08 19:37), приехала
владельцу списком из 24 находок и была отклонена кнопкой 06.08 13:16 — подтверждать было нечего:
16 находок из 24 несут метку производителя «[клиентский контур, нужна твоя отмашка…]», а
клиентский контур ЗАМОРОЖЕН решением владельца. Такие находки — СПИСОК, а не вопрос: им место в
ленте 829 заметкой без кнопок.

ФИКСТУРА ДОСЛОВНАЯ — тело задачи 244 из снимка очереди 06.08.2026 02:16 UTC (взято ДО того, как
вердикт «отклонено Филиппом (кнопка)» затёр текст находок в поле result).

ГРАНИЦЫ, которые обязаны остаться зелёными В ОБОИХ ПРОГОНАХ (до и после правки): находки
НЕзамороженных контуров ведут себя как прежде; выключенная ручка = прежнее поведение
байт-в-байт; заметка в ленту не уходит — карточка идёт владельцу, как раньше.

Запуск: PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_revizor_frozen.py
"""
import os
import sys
import json
import time
import shutil
import asyncio
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# Темы владельца — ЛИТЕРАЛАМИ (прод-значения): регресс говорит про 1160 и 829, а не «про то, что
# стоит в .env». load_dotenv существующие переменные не перекрывает.
os.environ["INBOX_TOPIC_ID"] = "1160"
os.environ["PC_DEV_TOPIC_ID"] = "829"

INBOX_TOPIC = 1160
FEED_TOPIC = 829
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_STATE = "/tmp/cc_revizor_frozen.json"      # боевое состояние маршрута — тест его НЕ трогает

_res = []


def ok(cond, msg):
    _res.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'} - {msg}")


def section(title, fn):
    print(title)
    try:
        fn()
    except Exception as e:            # до правки модуля/функций может не быть — это FAIL секции,
        ok(False, f"секция упала: {type(e).__name__}: {e}")     # а не крах всего прогона


try:
    import revizor_route as RR
except Exception:                     # на дереве ДО правки модуля нет вовсе
    RR = None
import devbot as DB

# ── ДОСЛОВНОЕ ТЕЛО КАРТОЧКИ 244 (снимок очереди 06.08.2026 02:16 UTC, 4184 симв.) ──────────
CARD244 = (
    "🔍 Ревизор: находки — требуют твоего решения (спорный тариф / политика / неоднозначный кейс). Ревизор сам ничего не правит и клиентам не пишет." "\n"
    "• [класс #92] окно 690197908: чек «нет утверждений о наличии»: клеймы наличия: не в наличии" "\n"
    "• [класс в] окно 690197908: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] Черновик: «Подскажите даты — с какого числа и на какой срок?» — при том, что клиент уже сказал: «С 9-10 августа ⏎ Аренда на 20-30" "\n"
    "• [класс д] окно 690197908: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] «[собрано: модель ✅]» в 1-м черновике и «Вам подойдёт Nmax на 20-30 дней с 9-10 августа? [собрано:" "\n"
    "• [класс в] окно 766498048: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] To complete the booking, we will need the following: a clear photo of your passport, the name of y" "\n"
    "• [класс в] окно 766498048: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] Подскажите даты — с какого числа и на какой срок? [собрано: даты ❓] — клиент: «I would like to ren" "\n"
    "• [класс д] окно 766498048: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] [собрано: паспорт ✅] при черновике «Понял, документы завтра — ждём» и реплике клиента «I'll send t" "\n"
    "• [класс е] окно 766498048: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] Hello, could you please let me know what motorcycle you rode before? ... Hello, good. We await you" "\n"
    "• [класс б] окно 766498048: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] Уточните, пожалуйста, какую модель имеете в виду под «большой скутер»: ADV 350, XMAX 300 или XADV" "\n"
    "• [класс #92] окно 416468128: чек «депозит без противоречий»: разные суммы депозита: 3000 ฿, 5000 ฿, 7000 ฿, 15000 ฿, 20000 ฿, 25000 ฿" "\n"
    "• [класс #92] окно 244119252: чек «нет утверждений о наличии»: клеймы наличия: есть в наличии" "\n"
    "• [класс #92] окно 244119252: чек «депозит без противоречий»: разные суммы депозита: 3000 ฿, 5000 ฿, 7000 ฿, 15000 ฿, 20000 ฿, 25000 ฿" "\n"
    "• [класс г] окно 244119252: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] [собрано: даты ❓]" "\n"
    "• [класс #92] окно 494999232: чек «депозит без противоречий»: разные суммы депозита: 3000 ฿, 5000 ฿, 7000 ฿, 15000 ฿, 20000 ฿, 25000 ฿" "\n"
    "• [класс #92] окно 1226243168: чек «нет годов»: годы в тексте: 2023-2024" "\n"
    "• [класс #93] окно 1226243168: чек «yearcheck»: год поколения в тексте — проверить: «CBR 650R — 2023-2024 год, полностью в порядке техническ»" "\n"
    "• [класс е] окно 244119252: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] [менеджер]: Здравствуйте, на какие даты? Чем ранее управляли? — сразу после автоприветствия TG Business «Здравствуйте, спасибо, чт" "\n"
    "• [класс в] окно 244119252: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] клиент: «С 11 ноября», «На 10-11дней» → менеджер: «Здравствуйте, на какие даты? Чем ранее управляли?»" "\n"
    "• [класс г] окно 244119252: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] [собрано: даты ❓] / [сезон: низкий, цены действуют до 31 октября]" "\n"
    "• [класс д] окно 494999232: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] [собрано: срок ✅]" "\n"
    "• [класс в] окно 831088817: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] Подскажите даты — с какого числа и на какой срок?" "\n"
    "• [класс д] окно 831088817: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] [собрано: даты ❓ паспорт ✅]" "\n"
    "• [класс б] окно 831088817: [клиентский контур, нужна твоя отмашка; файлы не названы — контур неопределим, держим по fail-closed] На один день спорт-байки от 600 кубов у нас есть Ninja 400, CB650R, CBR650R, Vulcan 650S" "\n"
    "• [класс а] окно 831088817: По мотоциклам у нас минимальный срок аренды — 3 дня, к сожалению, на один день не оформим" "\n"
    "• [класс в] окно 1226243168: [клиентский контур, нужна твоя отмашка; клиентские файлы: suggest.py] Подскажите даты — с какого числа и на какой срок? [собрано: даты ❓]" "\n"
)
FROZEN_IN_244 = 16       # строк с меткой производителя «[клиентский контур …]» (замер 06.08)
OPEN_IN_244 = 8          # находки БЕЗ метки контура: #92 ×6, #93 ×1, «класс а» ×1 — вопрос жив

# Внутренний контур: та же форма находки, но метка контура НЕ стоит (замораживать нечего).
CARD_INTERNAL = (
    "🔍 Ревизор: находки — требуют твоего решения (спорный тариф / политика / неоднозначный "
    "кейс). Ревизор сам ничего не правит и клиентам не пишет.\n"
    "• [класс #92] окно 416468128: чек «депозит без противоречий»: разные суммы депозита: "
    "3000 ฿, 5000 ฿, 7000 ฿, 15000 ฿, 20000 ฿, 25000 ฿\n"
    "• [класс #92] окно 1226243168: чек «нет годов»: годы в тексте: 2023-2024"
)
ALL_FROZEN = (
    "🔍 Ревизор: находки — требуют твоего решения.\n"
    "• [класс в] окно 831088817: [клиентский контур, нужна твоя отмашка; клиентские файлы: "
    "suggest.py] Подскажите даты — с какого числа и на какой срок?\n"
    "• [класс д] окно 831088817: [клиентский контур, нужна твоя отмашка; файлы не названы — "
    "контур неопределим, держим по fail-closed] [собрано: даты ❓ паспорт ✅]"
)


def _bullets(text):
    return [l for l in str(text or "").splitlines() if l.lstrip().startswith("•")]


def _inbox_msgs(bot):
    return [k for k in bot.sent if k.get("message_thread_id") == INBOX_TOPIC]


def _inbox_text(bot):
    """Текст карточки владельцу ЦЕЛИКОМ. Длинная карточка режется на чанки по 3500 симв.
    (_chunks — простая нарезка среза), поэтому склейка возвращает ровно исходный текст."""
    return "".join(k["text"] for k in _inbox_msgs(bot))


# ═════ (1) РУЧКА ЗАМОРОЗКИ: факт меняется — значит это ручка, а не константа ═══════════════
def sec1():
    ok(RR.frozen_keys("client") == frozenset({"client"}), "CONTOUR_FREEZE=client → контур заморожен")
    for off in ("", "0", "off", "no", "none", "нет", "-", None, "   "):
        ok(RR.frozen_keys(off) == frozenset(), f"выключено ({off!r}) → замороженных контуров нет")
    ok(RR.frozen_keys("suggest.py") == frozenset(),
       "незнакомый ключ → пусто (ошибаемся в сторону «карточка владельцу», не в сторону молчания)")
    ok(RR.frozen_keys("client,pc") == frozenset({"client"}), "мусор рядом с ключом не мешает")
    ok(RR.contour_name("client") == "клиентский", "имя контура для человека")


# ═════ (2) МЕТКУ СТАВИТ ПРОИЗВОДИТЕЛЬ, И ТОЛЬКО В АННОТИРУЮЩЕЙ ПОЗИЦИИ ════════════════════
def sec2():
    F = frozenset({"client"})
    real = ("• [класс в] окно 831088817: [клиентский контур, нужна твоя отмашка; клиентские "
            "файлы: suggest.py] Подскажите даты")
    ok(RR.contour_of(real, F) == "client", "живая метка производителя опознана")
    ok(RR.contour_of("• [класс д] окно 1: [клиентский контур, нужна твоя отмашка; файлы не "
                     "названы — контур неопределим, держим по fail-closed] [собрано: даты ❓]",
                     F) == "client", "вторая живая форма метки (файлы не названы) опознана")
    quote = ("• [класс а] окно 5: клиент пишет: «а клиентский контур у вас заморожен?» — "
             "менеджер не ответил")
    ok(RR.contour_of(quote, F) is None,
       "те же слова в ЦИТАТЕ клиента (без скобки-аннотации) находкой контура НЕ делают")
    head = "🔍 Ревизор: находки по разделу [клиентский контур] — требуют решения"
    ok(RR.contour_of(head, F) is None, "шапка карточки — не находка, метку в ней не читаем")
    ok(RR.contour_of(real, frozenset()) is None, "ручка выключена → метка никого не трогает")
    ok(RR.fingerprint("•  [класс в]  окно 8:  текст") == RR.fingerprint("• [класс в] окно 8: текст"),
       "дедуп по находке не зависит от лишних пробелов")


# ═════ (3) ДОСЛОВНАЯ КАРТОЧКА 244: 16 в ленту, 8 остаются вопросом ════════════════════════
def sec3():
    F = frozenset({"client"})
    r = RR.route(CARD244, F)
    ok(r["changed"] is True, "карточка 244 признана изменяемой")
    ok(len(r["frozen"]) == FROZEN_IN_244,
       f"находок замороженного контура: {len(r['frozen'])} (ожидание {FROZEN_IN_244})")
    ok(all(k == "client" for _l, k in r["frozen"]), "все они отнесены к клиентскому контуру")
    card = r["card"] or ""
    ok(card != "", "карточка владельцу остаётся: 8 находок без метки контура — живой вопрос")
    ok(len(_bullets(card)) == OPEN_IN_244,
       f"в карточке ровно {OPEN_IN_244} находок, факт {len(_bullets(card))}")
    ok("клиентский контур, нужна твоя отмашка" not in card,
       "ни одной замороженной находки в карточке не осталось")
    ok(card.startswith("🔍 Ревизор: находки — требуют твоего решения"), "шапка карточки на месте")
    ok("[класс а] окно 831088817: По мотоциклам у нас минимальный срок аренды — 3 дня" in card,
       "находка «класс а» (без метки контура) осталась ДОСЛОВНО")
    ok("чек «депозит без противоречий»" in card and "чек «yearcheck»" in card,
       "чек-находки #92/#93 остались вопросом владельцу — их контур не заморожен")
    ok(_bullets(card) == [l for l in _bullets(CARD244)
                          if "клиентский контур" not in l], "порядок и текст прочих строк не тронуты")
    ok("уехали заметкой в ленту" in card and "16" in card,
       "карточка честно называет, сколько находок уехало и куда (молча не исчезает ничего)")
    ok("да " not in card.lower().replace("даты", "").replace("дата", ""),
       "служебная строка не предлагает отвечать «да»")

    r2 = RR.route(ALL_FROZEN, F)
    ok(r2["card"] is None and len(r2["frozen"]) == 2,
       "все находки заморожены → карточке взяться неоткуда (card=None)")

    r3 = RR.route(CARD_INTERNAL, F)
    ok(r3["changed"] is False and r3["card"] == CARD_INTERNAL,
       "внутренний контур: тело БАЙТ-В-БАЙТ, changed=False (граница «как прежде»)")
    r4 = RR.route(CARD244, frozenset())
    ok(r4["changed"] is False and r4["card"] == CARD244 and r4["frozen"] == [],
       "ручка выключена: та же карточка 244 идёт БАЙТ-В-БАЙТ (доказательство отката)")


# ═════ (4) ЗАМЕТКА ЛЕНТЫ: сводка, а не простыня; и она не притворяется вопросом ════════════
def sec4():
    F = frozenset({"client"})
    fr = RR.route(CARD244, F)["frozen"]
    note = RR.note(fr, window_label="окно: с 05.08 19:31 по 06.08 23:40 UTC",
                   artifact="reports/revizor/2026-08-06-2340.md")
    ok("16" in note, "заметка называет число находок")
    ok("ЗАМОРОЖЕН" in note.upper(), "заметка говорит, ПОЧЕМУ это не вопрос")
    ok("ответа не требует" in note, "заметка прямо говорит, что ответа не требует")
    ok(len(_bullets(note)) == RR.NOTE_TOP,
       f"поимённо ровно {RR.NOTE_TOP} находки, остальное числом (лента не должна стать простынёй)")
    ok("…ещё 13" in note, "остаток назван числом")
    ok("reports/revizor/2026-08-06-2340.md" in note, "путь к полному списку назван")
    ok(len(note) < 900, f"заметка помещается в экран телефона, факт {len(note)} симв.")
    low = note.lower()
    ok("подтверд" not in low and "задача " not in low and "кнопк" not in low,
       "в заметке нет ни номера задачи, ни кнопки, ни слова «подтвердить» — на неё не отвечают")
    ok(not any(l.startswith("• •") for l in _bullets(note)),
       "маркер пункта в заметке один (строка находки уже несёт свой)")
    ok("нужна твоя отмашка" not in note,
       "аннотация контура из показа снята — её смысл уже в заголовке заметки, а место она "
       "съедала у самой находки")
    ok("Черновик: «Подскажите даты" in note, "текст находки при этом виден, а не съеден аннотацией")
    art = RR.artifact_text(fr, "окно: с 05.08 19:31 по 06.08 23:40 UTC")
    ok(art.count("\n- ") == 16, "в артефакте — ВСЕ 16 находок целиком")
    ok(art.count("нужна твоя отмашка") == 16,
       "и ДОСЛОВНО, с аннотацией производителя (сжат показ, а не запись)")
    ok(RR.note([], artifact="x") == "", "нечего сказать → пустая строка (ленту не будим)")


# ═════ СКВОЗНОЙ ПРОГОН devbot.report_results (Telegram и лента подменены) ══════════════════
class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 1})()


class FakeCtx:
    def __init__(self, bot):
        self.bot = bot


class FakeNotify:
    """Дверь ленты. Возвращает то, что скажет тест: ok=False = «заметка не ушла»."""
    def __init__(self, ok=True):
        self.sent = []
        self.ok = ok

    def send_feed(self, text):
        self.sent.append(text)
        return self.ok


def _snapshot(**kw):
    by = {st: [] for st in ("done", "failed", "needs_approval", "in_progress", "new", "approved")}
    by.update(kw)
    return by


def _reset(state_file):
    DB._reported.clear(); DB._asked.clear(); DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._curator_pending.clear(); DB._revizor_silenced.clear() if hasattr(
        DB, "_revizor_silenced") else None
    DB._report_seeded = True
    DB._queue_busy = None
    DB._closed_since_busy = []
    os.environ["REVIZOR_STATE_FILE"] = state_file
    if os.path.exists(state_file):
        os.remove(state_file)


def _run(by, bot):
    DB._get_poll_bridge = lambda: object()
    DB._poll_queue_sync = lambda pb: by
    DB._drain_claim_events = lambda path=None: []
    asyncio.run(DB.report_results(FakeCtx(bot)))


def _card(result, qid=244, frm="Filipp-revizor"):
    return {"id": qid, "from": frm, "lane": "pc", "status": "needs_approval",
            "task_text": "[ревизор-находки] сводная карточка находок ревизора",
            "result": result, "created": "2026-08-03T13:20:12.264Z",
            "updated": "2026-08-04T19:37:24.027Z"}


def _with_env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _harness(fn, feed_ok=True, freeze="client"):
    """Один прогон в изоляции: своё состояние, свои артефакты, своя дверь ленты."""
    tmpd = tempfile.mkdtemp(prefix="tb_revfroz_")
    old = _with_env(REPORTS_DIR=os.path.join(tmpd, "reports"), CONTOUR_FREEZE=freeze,
                    REVIZOR_STATE_FILE=os.path.join(tmpd, "state.json"))
    nt = FakeNotify(ok=feed_ok)
    real_notify = getattr(DB, "notify", None)
    DB.notify = nt
    try:
        _reset(os.path.join(tmpd, "state.json"))
        fn(nt, tmpd)
    finally:
        if real_notify is not None:
            DB.notify = real_notify
        _restore(old)
        shutil.rmtree(tmpd, ignore_errors=True)


# ═════ (5) ГЛАВНЫЙ РЕГРЕСС: карточка ревизора при заморозке ════════════════════════════════
def sec5():
    def body(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244)]), bot)
        inbox = _inbox_msgs(bot)
        ok(len(nt.sent) == 1, f"в ленту ушла РОВНО одна сводка, факт {len(nt.sent)}")
        ok(bool(nt.sent) and "16" in nt.sent[0], "сводка называет 16 находок замороженного контура")
        ok(len(inbox) == 1, f"владельцу ушла одна карточка (в ней остались 8 вопросов), факт {len(inbox)}")
        txt = _inbox_text(bot)
        ok("клиентский контур, нужна твоя отмашка" not in txt,
           "ГЛАВНОЕ: ни одной находки замороженного контура в карточке владельца")
        ok("чек «депозит без противоречий»" in txt,
           "находки незамороженного контура доехали до владельца, как прежде")
        ok(bool(inbox) and inbox[0].get("reply_markup") is not None,
           "у карточки владельца кнопки на месте (вопрос остался вопросом)")
        art = os.path.join(tmpd, "reports", "revizor")
        files = os.listdir(art) if os.path.isdir(art) else []
        ok(len(files) == 1, f"полный список находок записан артефактом, факт {files}")
        ok(bool(files) and open(os.path.join(art, files[0]), encoding="utf-8").read().count("\n- ") == 16,
           "в артефакте все 16 находок целиком")

        # ПОЛНОСТЬЮ замороженная карточка: владельцу не уходит ВООБЩЕ
        bot2 = FakeBot()
        _run(_snapshot(needs_approval=[_card(ALL_FROZEN, qid=301)]), bot2)
        inbox2 = _inbox_msgs(bot2)
        ok(len(inbox2) == 0, f"все находки заморожены → карточки владельцу НЕТ, факт {len(inbox2)}")
        ok(len(nt.sent) == 1,
           "второй сводки в те же сутки НЕТ — суточное окно держит потолок 1 заметка/сутки")
        st = json.load(open(os.path.join(tmpd, "state.json"), encoding="utf-8"))
        ok(len(st.get("pending") or []) == 0,
           "обе её находки ДОСЛОВНО совпали с уже уехавшими (те же строки окна 831088817) → "
           "дедуп по находке, второй раз о них не рассказываем")

        # ...а НОВАЯ находка второй карточки в состоянии копится и ждёт ближайшей сводки
        fresh = ALL_FROZEN + ("\n• [класс б] окно 700000001: [клиентский контур, нужна твоя "
                              "отмашка; клиентские файлы: suggest.py] новая находка другой карточки")
        bot3 = FakeBot()
        _run(_snapshot(needs_approval=[_card(fresh, qid=302)]), bot3)
        ok(len(_inbox_msgs(bot3)) == 0, "карточка по-прежнему владельцу не уходит")
        st = json.load(open(os.path.join(tmpd, "state.json"), encoding="utf-8"))
        ok(len(st.get("pending") or []) == 1,
           "новая находка лежит в состоянии и уедет ближайшей сводкой (не потеряна)")
    _harness(body)


# ═════ (6) ГРАНИЦА: незамороженное и выключенная ручка — как прежде ════════════════════════
def sec6():
    def internal(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD_INTERNAL, qid=310)]), bot)
        inbox = _inbox_msgs(bot)
        ok(len(inbox) == 1, "находка внутреннего контура → карточка владельцу, как прежде")
        txt = _inbox_text(bot)
        want = (f"⚠️ Задача 310 [pc] требует подтверждения красной зоны:\n\n{CARD_INTERNAL}\n\n"
                f"Подтвердить? Тапни кнопку ниже — или ответь «да 310» / «нет 310».")
        ok(txt == want, "текст карточки БАЙТ-В-БАЙТ прежний (сверка со строкой живого кода)")
        ok(len(nt.sent) == 0, "в ленту не ушло ничего: замораживать нечего")
    _harness(internal)

    def rollback(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244, qid=320)]), bot)
        ok(len(_inbox_msgs(bot)) > 0 and len(nt.sent) == 0,
           "CONTOUR_FREEZE=0: карточка владельцу, лента молчит (откат)")
        ok(CARD244 in _inbox_text(bot),
           "тело карточки БАЙТ-В-БАЙТ как до правки — все 24 находки на месте")
    _harness(rollback, freeze="0")

    def foreign(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244, qid=330, frm="Filipp-328-dev")]), bot)
        ok(len(_inbox_msgs(bot)) > 0 and len(nt.sent) == 0,
           "чужая метка from: маршрут не применяется вовсе (правило узкое, только ревизор)")
        ok(CARD244 in _inbox_text(bot), "её тело не тронуто")
    _harness(foreign)


# ═════ (7) СУТОЧНАЯ СВОДКА: не чаще раза в сутки, и ни одна находка не пропадает ═══════════
def sec7():
    def body(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244)]), bot)
        ok(len(nt.sent) == 1, "первая сводка ушла сразу (ждать нечего)")

        # тот же тик через 45 с: находки те же → второй заметки нет
        bot2 = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244)]), bot2)
        ok(len(nt.sent) == 1, "повторный тик с теми же находками второй заметки НЕ рождает")

        # карточка ДОПОЛНИЛАСЬ новой находкой в пределах суток → она копится, заметки нет
        more = CARD244 + ("• [класс в] окно 999999: [клиентский контур, нужна твоя отмашка; "
                          "клиентские файлы: suggest.py] новая находка суток\n")
        bot3 = FakeBot()
        _run(_snapshot(needs_approval=[_card(more)]), bot3)
        ok(len(nt.sent) == 1, "новая находка в пределах суток ждёт сводки — лента не шумит")
        st = json.load(open(os.path.join(tmpd, "state.json"), encoding="utf-8"))
        ok(len(st.get("pending") or []) == 1, "она сохранена в состоянии (не потеряна)")

        # сутки прошли → сводка уходит и несёт именно накопленное
        st["last_note"] = "2026-08-01T00:00:00+00:00"
        json.dump(st, open(os.path.join(tmpd, "state.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        bot4 = FakeBot()
        _run(_snapshot(needs_approval=[_card(more)]), bot4)
        ok(len(nt.sent) == 2, "через сутки ушла ВТОРАЯ сводка")
        ok(len(nt.sent) > 1 and "новая находка суток" in nt.sent[1],
           "в ней ровно накопленное за сутки")
        ok(len(nt.sent) > 1 and "16" not in nt.sent[1].splitlines()[0],
           "уже отправленные находки во второй сводке не повторяются")
    _harness(body)


# ═════ (8) FAIL-SAFE: не смогли сказать в ленту — не гасим вопрос владельцу ════════════════
def sec8():
    def body(nt, tmpd):
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(ALL_FROZEN, qid=340)]), bot)
        inbox = _inbox_msgs(bot)
        ok(len(inbox) == 1,
           "лента недоступна → карточка идёт владельцу КАК РАНЬШЕ (молчать нельзя)")
        ok("клиентский контур" in _inbox_text(bot),
           "и несёт находки целиком — ничего не съедено")
        st = json.load(open(os.path.join(tmpd, "state.json"), encoding="utf-8"))
        ok(len(st.get("pending") or []) == 2, "находки остались ждущими — повтор на след. тике")
    _harness(body, feed_ok=False)

    def broken(nt, tmpd):
        with open(os.path.join(tmpd, "state.json"), "w", encoding="utf-8") as f:
            f.write("{битый JSON")
        bot = FakeBot()
        _run(_snapshot(needs_approval=[_card(CARD244, qid=350)]), bot)
        ok(len(nt.sent) == 1, "битое состояние → сводка всё равно уходит (дубль дешевле потери)")
    _harness(broken)


# ═════ (9) СИГНАЛ «ОЧЕРЕДЬ ПУСТА»: погашенная карточка владельца не ждёт ═══════════════════
def sec9():
    def body(nt, tmpd):
        bot = FakeBot()
        by = _snapshot(needs_approval=[_card(ALL_FROZEN, qid=360)])
        _run(by, bot)
        ok(DB._queue_open_count(by) == 0,
           "карточка, целиком уехавшая в ленту, «ждёт тебя» не держит")
        by2 = _snapshot(needs_approval=[_card(CARD_INTERNAL, qid=361)])
        _run(by2, FakeBot())
        ok(DB._queue_open_count(by2) == 1,
           "карточка с живым вопросом держит очередь непустой, как прежде")
    _harness(body)


# ═════ (10) ГИГИЕНА: боевое состояние и боевые артефакты прогон НЕ трогает ════════════════
def sec10():
    live_before = (os.path.exists(LIVE_STATE),
                   os.path.getmtime(LIVE_STATE) if os.path.exists(LIVE_STATE) else 0)
    live_reports = os.path.join(ROOT, "reports", "revizor")
    rep_before = sorted(os.listdir(live_reports)) if os.path.isdir(live_reports) else None
    _harness(lambda nt, tmpd: _run(_snapshot(needs_approval=[_card(CARD244, qid=370)]), FakeBot()))
    live_after = (os.path.exists(LIVE_STATE),
                  os.path.getmtime(LIVE_STATE) if os.path.exists(LIVE_STATE) else 0)
    rep_after = sorted(os.listdir(live_reports)) if os.path.isdir(live_reports) else None
    ok(live_before == live_after, "боевое состояние /tmp/cc_revizor_frozen.json не тронуто")
    ok(rep_before == rep_after, "боевой каталог reports/revizor не тронут")
    os.environ.pop("REVIZOR_STATE_FILE", None)
    ok(DB._revizor_state_path().endswith(".test"),
       "под тест-прогоном БЕЗ подмены путь уводится от боевого (урок 04.08 со стёртым спулом)")


for title, fn in (
    ("(1) ручка заморозки — факт, который меняется:", sec1),
    ("(2) метку ставит производитель, и только в аннотирующей позиции:", sec2),
    ("(3) дословная карточка 244 — 16 в ленту, 8 остаются вопросом:", sec3),
    ("(4) заметка ленты — сводка, а не простыня:", sec4),
    ("(5) сквозной прогон: находка замороженного контура НЕ рождает карточку:", sec5),
    ("(6) граница: незамороженное и выключенная ручка — как прежде:", sec6),
    ("(7) суточная сводка: не чаще раза в сутки, ничего не теряя:", sec7),
    ("(8) fail-safe: лента молчит → вопрос владельцу остаётся:", sec8),
    ("(9) сигнал «очередь пуста»:", sec9),
    ("(10) гигиена прогона:", sec10),
):
    section(title, fn)

print()
if all(_res):
    print(f"OK: {len(_res)}/{len(_res)} проверок маршрута находок ревизора")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in _res if not r)} из {len(_res)} проверок красные")
sys.exit(1)
