#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СОКРАЩЕНИЕ ШУМА: три источника, одна цель (решение владельца, 05.08.2026).

Четыре пункта регресса — дословно из постановки владельца:
  (1) push заметки НЕ рождает (класс отозван; остальные четыре живы и не задеты);
  (2) рестарт splinter назван ВНУТРЕННИМ сервисом (а не клиентским ботом);
  (3) старт userbot/moderbot на ПК назван КЛИЕНТСКИМ ботом;
  (4) задача даёт РОВНО ОДНО сообщение в 328: вердикт куратора — строка внутри карточки, а
      продолжение цели названо в ней НОМЕРОМ; отдельного сообщения нет.
Плюс границы, без которых сокращение шума стало бы потерей смысла:
  (5) FAIL-SAFE: вердикт, который в строку не влезает («НЕ поставлено», «карточка НЕ встала»),
      уходит отдельным сообщением ЦЕЛИКОМ — молча не теряется ничего;
  (6) красное по-прежнему в инбоксе 1160, лента не трогает гард, а карточка не теряет кнопок.

ФИКСТУРА ВЕРДИКТА — ЖИВОГО ФОРМАТА: тело кураторской карточки берём не из мока, а у самого
производителя, `orchestrator_daemon._curator_card_text`. Разъедутся формулировки демона и разбор
devbot — тест покраснеет здесь, а не в теме 328 у владельца.

Запуск: PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_noise_cut.py
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
# Изоляция ПРИНУДИТЕЛЬНАЯ: импорт демона тянет боевой .env (load_dotenv), а нам нужны свои
# значения флагов — куратор включается посекционно там, где он предмет проверки.
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["INBOX_TOPIC_ID"] = "1160"
os.environ["PC_DEV_TOPIC_ID"] = "829"

DEV_TOPIC = 328
INBOX_TOPIC = 1160

_res = []


def ok(cond, msg):
    _res.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'} - {msg}")


def section(title, fn):
    print(title)
    try:
        fn()
    except Exception as e:            # до правки функции/ветки может не быть — это FAIL секции,
        ok(False, f"секция упала: {type(e).__name__}: {e}")   # а не крах прогона


# ── ДОСЛОВНЫЕ КОМАНДЫ ЖИВОГО КОРПУСА (транскрипты 29.07–05.08) ───────────────────────────
PUSH_CMDS = [
    "git -c core.hooksPath=deploy/hooks push origin main",
    "git push origin main 2>&1 | tail -20",
    "git push",
    "git -C /root/turbobaby-manager-bot push origin main",
    "git add -A && git commit -q -m 'фикс' && git push origin main",
]
RESTART_SPLINTER = [
    "systemctl restart splinter",
    "systemctl start splinter",
    "systemd-run --on-active=10s systemctl restart splinter",
]
CLIENT_PC = [
    "pkill -f userbot_listen.py",
    "python3 /root/pcport/userbot/userbot_listen.py",
    "systemctl restart moderation_bot",
    "pkill -f moderation_bot",
]
KEEP_ALIVE = {                        # четыре живых класса — каждый обязан остаться классом
    "git reset --hard HEAD": "отброс рабочего дерева",
    "git stash push -m 'wip'": "отброс рабочего дерева",
    "git clean -fd": "отброс рабочего дерева",
    "mv tests/test_curator.py /tmp/tb_scratch/test_curator.py": "вынос теста из гейта",
    "rm -f /tmp/cc_guard_block/321.json": "стирание маркеров гарда",
}


# ═════ (1) PUSH БОЛЬШЕ НЕ КЛАСС ══════════════════════════════════════════════════════════
def sec1():
    import posttool_feed as PF

    for cmd in PUSH_CMDS:
        ok(PF.classify(cmd) is None, f"push молчит: {cmd[:60]}")
    ok(not any(str(name).startswith("push") for name, _p in PF._CLASSES),
       "класса push нет в таблице _CLASSES")
    ok(len(PF._CLASSES) == 4, f"классов ровно четыре, факт {len(PF._CLASSES)}")
    ok(not hasattr(PF, "push_detail") and not hasattr(PF, "_push_out"),
       "предикат и деталь push удалены вместе с классом (мёртвый код не оставлен)")
    # Соседние классы push-командой не задеты и живы сами по себе
    for cmd, cls in KEEP_ALIVE.items():
        ok(PF.classify(cmd) == cls, f"жив класс «{cls}»: {cmd[:60]}")
    # push внутри цепи с ЖИВЫМ классом класс не отменяет (судим сегменты, а не строку целиком)
    ok(PF.classify("git push origin main && git reset --hard HEAD~1") == "отброс рабочего дерева",
       "push в цепи молчит, а отброс дерева рядом — говорит")


# ═════ (2) SPLINTER — ВНУТРЕННИЙ СЕРВИС ══════════════════════════════════════════════════
def sec2():
    import posttool_feed as PF

    for cmd in RESTART_SPLINTER:
        cls = PF.classify(cmd) or ""
        ok("внутренн" in cls, f"назван внутренним: {cmd} → {cls}")
        ok("клиентск" not in cls, f"НЕ клиентский бот: {cmd} → {cls}")
        ok("splinter" in cls, f"юнит назван в самой строке класса: {cmd} → {cls}")
    ok((PF.classify("systemctl restart splinter") or "").startswith("рестарт"),
       "глагол сохранён (рестарт/старт/стоп)")
    ok((PF.classify("systemctl stop splinter") or "").startswith("стоп"), "стоп — тоже событие")
    # Не-события и чужие юниты не изменились
    ok(PF.classify("systemctl status splinter") is None, "чтение статуса — не событие")
    ok(PF.classify("systemctl restart orchestrator-daemon") is None, "демон вне списка (§4)")
    ok(PF.classify("systemctl restart wa-webhook") is None, "wa-webhook вне списка намеренно")
    ok(PF.classify("cclog.py DONE 'нужен systemctl restart splinter'") is None,
       "слова о рестарте в аргументе журнальной команды заметки не рождают")


# ═════ (3) КЛИЕНТСКИЙ БОТ — ЭТО ПК-ПРОЦЕССЫ ══════════════════════════════════════════════
def sec3():
    import posttool_feed as PF

    for cmd in CLIENT_PC:
        cls = PF.classify(cmd) or ""
        ok("клиентск" in cls, f"назван клиентским: {cmd} → {cls}")
        ok("внутренн" not in cls, f"НЕ внутренний сервис: {cmd} → {cls}")
    ok((PF.classify("python3 /root/pcport/userbot/userbot_listen.py") or "").startswith("старт"),
       "запуск скрипта = старт клиентского бота")
    ok((PF.classify("pkill -f userbot_listen.py") or "").startswith("стоп"),
       "pkill = стоп клиентского бота")
    # Метка полосы в заметке остаётся и от класса не зависит (имя даёт цель, полоса — принадлежность)
    line = PF.render(PF.classify("systemctl restart splinter"), PF.who({}),
                     "systemctl restart splinter", {"stdout": ""})
    ok(line.startswith("🔔 рестарт внутреннего сервиса splinter"), f"строка заметки: {line[:70]}")
    ok(" · " + PF.lane() + " · " in line or (PF.lane() + " · ") in line,
       "метка полосы в заметке на месте")


# ═════ ОБЩИЙ ХАРНЕСС 328 ═════════════════════════════════════════════════════════════════
class FakeBot:
    def __init__(self):
        self.sent = []
        self.edits = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 100 + len(self.sent)})()

    async def edit_message_text(self, **kw):
        self.edits.append(kw)
        return type("M", (), {"message_id": kw.get("message_id")})()


class FakeCtx:
    def __init__(self, bot):
        self.bot = bot


def _snapshot(**kw):
    by = {st: [] for st in ("done", "failed", "needs_approval", "in_progress", "new", "approved")}
    by.update(kw)
    return by


def _reset(devbot):
    devbot._reported.clear()
    devbot._asked.clear()
    devbot._inprogress_seen.clear()
    devbot._stalled.clear()
    devbot._curator_pending.clear()
    try:
        devbot._curator_glued.clear()
    except Exception:
        pass
    devbot._report_seeded = True
    devbot._queue_busy = None
    devbot._closed_since_busy = []


def _run(devbot, by, bot, claims=()):
    devbot._get_poll_bridge = lambda: object()
    devbot._poll_queue_sync = lambda pb: by
    evs = list(claims)
    devbot._drain_claim_events = lambda path=None: evs
    asyncio.run(devbot.report_results(FakeCtx(bot)))


def _card_body(kind, key, verdict, tasks=(), placed=(), refused=(), human=None, hum=None):
    """Тело кураторской карточки ЖИВОГО формата — считает сам демон, не мок."""
    import orchestrator_daemon as OD
    v = {"verdict": verdict, "tasks": list(tasks), "human": human, "reason": "причина вердикта"}
    spawn = ({"root": key, "placed": list(placed), "refused": list(refused)}
             if verdict == "followup" else None)
    return OD._curator_card_text(kind, key, v, spawn, hum)


# ═════ (4) ОДНА ЗАДАЧА — ОДНО СООБЩЕНИЕ В 328 ════════════════════════════════════════════
def sec4():
    import devbot
    os.environ["CURATOR"] = "1"
    try:
        # 4a. Вердикт УСПЕЛ до первого рапорта (живой случай: думатель ~10с, тик 45с)
        _reset(devbot)
        body = _card_body("задача", 318, "followup", tasks=["доделай"],
                          placed=[(331, "доделай зеркало ПК")])
        task = {"id": 318, "from": "Filipp-328-dev", "status": "done",
                "result": "сделал\n\nFACT: commit abc1234 в git log origin/main",
                "task_text": "тз: почини ленту", "updated": "2026-08-05T07:30:00Z"}
        card = {"id": 321, "from": "Filipp-328-dec", "status": "done", "result": body,
                "task_text": "[куратор задача 318] вердикт куратора",
                "updated": "2026-08-05T07:31:00Z"}
        bot = FakeBot()
        _run(devbot, _snapshot(done=[task, card]), bot)
        msgs = [k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC]
        ok(len(msgs) == 1, f"задача + вердикт = ОДНО сообщение в 328, факт {len(msgs)}")
        txt = msgs[0]["text"] if msgs else ""
        ok(txt.startswith("✅ Задача 318"), "сообщение — это карточка задачи, а не карточка куратора")
        ok("🧭 Куратор" in txt, "вердикт куратора вклеен строкой в ту же карточку")
        ok("331" in txt, "продолжение цели названо НОМЕРОМ в той же строке")
        ok("причина вердикта" not in txt, "полотно куратора в чат не уехало — только строка")

        # 4b. Вердикт пришёл ПОЗЖЕ: правка того же сообщения, новых сообщений ноль
        _reset(devbot)
        bot = FakeBot()
        _run(devbot, _snapshot(done=[task]), bot)
        first = len([k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC])
        ok(first == 1, f"первый тик: одна карточка, факт {first}")
        ok("Куратор оценивает" in (bot.sent[0]["text"] if bot.sent else ""),
           "пока вердикта нет — честная плашка ожидания")
        _run(devbot, _snapshot(done=[task, card]), bot)
        after = len([k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC])
        ok(after == first, f"второй тик: НОВЫХ сообщений ноль, факт {after - first}")
        ok(len(bot.edits) == 1, f"вердикт доставлен правкой той же карточки, факт {len(bot.edits)}")
        etxt = bot.edits[0]["text"] if bot.edits else ""
        ok("🧭 Куратор" in etxt and "331" in etxt, "в правке — строка вердикта с номером продолжения")
        ok("Куратор оценивает" not in etxt, "надпись ожидания снята")

        # 4c. Анонс «в работе» о карточке-маркере не шлётся вовсе
        _reset(devbot)
        bot = FakeBot()
        ev = {"id": 321, "from": "Filipp-328-dec", "status": "in_progress",
              "task_text": "[куратор задача 318] вердикт куратора"}
        _run(devbot, _snapshot(done=[task, card]), bot, claims=[ev])
        ok(not any("в работе" in str(k.get("text", "")) for k in bot.sent),
           "анонс «🔄 в работе» о карточке-маркере не отправлен")

        # 4d. Вердикт human: карточка владельцу названа номером, второго сообщения нет
        _reset(devbot)
        bot = FakeBot()
        hbody = _card_body("задача", 303, "human", human="нужен рестарт splinter",
                           hum=(340, "created"))
        t2 = dict(task, id=303, task_text="тз: разбери карточки")
        c2 = {"id": 308, "from": "Filipp-328-dec", "status": "done", "result": hbody,
              "task_text": "[куратор задача 303] вердикт куратора",
              "updated": "2026-08-05T05:04:00Z"}
        _run(devbot, _snapshot(done=[t2, c2]), bot)
        m2 = [k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC]
        ok(len(m2) == 1, f"human-вердикт: тоже одно сообщение, факт {len(m2)}")
        ok("340" in (m2[0]["text"] if m2 else ""), "номер сводной карточки владельцу назван строкой")
        ok("инбокс" in (m2[0]["text"] if m2 else "").lower(), "сказано, где эта карточка ждёт")
    finally:
        os.environ["CURATOR"] = "0"


# ═════ (5) FAIL-SAFE: ЧТО В СТРОКУ НЕ ВЛЕЗЛО — УХОДИТ ЦЕЛИКОМ ════════════════════════════
def sec5():
    import devbot
    os.environ["CURATOR"] = "1"
    try:
        _reset(devbot)
        body = _card_body("задача", 318, "followup", tasks=["доделай", "и это"],
                          placed=[(331, "доделай")],
                          refused=[("и это", "исчерпан лимит корня (3 продолжений на цель)")])
        ok(devbot._curator_line(body) is None,
           "вердикт со сбоем постановки в строку НЕ ужимается (None)")
        task = {"id": 318, "from": "Filipp-328-dev", "status": "done", "result": "сделал",
                "task_text": "тз: почини", "updated": "2026-08-05T07:30:00Z"}
        card = {"id": 321, "from": "Filipp-328-dec", "status": "done", "result": body,
                "task_text": "[куратор задача 318] вердикт куратора",
                "updated": "2026-08-05T07:31:00Z"}
        bot = FakeBot()
        _run(devbot, _snapshot(done=[task, card]), bot)
        msgs = [k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC]
        ok(len(msgs) == 2, f"сбойный вердикт — отдельным сообщением, как раньше, факт {len(msgs)}")
        ok(any("НЕ поставлено" in str(k.get("text", "")) for k in msgs),
           "текст «НЕ поставлено» доехал до владельца ДОСЛОВНО")

        # Карточка владельцу не встала — тоже целиком
        _reset(devbot)
        nb = _card_body("задача", 303, "human", human="нужен рестарт", hum=None)
        ok(devbot._curator_line(nb) is None, "«сводная карточка НЕ встала» в строку не ужимается")

        # Пустое/чужое тело — молчим и не гасим карточку
        ok(devbot._curator_line("") is None, "пустое тело → None")
        ok(devbot._curator_line("что-то своё") is None, "неузнанный формат → None (карточка целиком)")

        # closed: карточки нет вовсе — ни строки, ни сообщения (проверяем отсутствие второго)
        _reset(devbot)
        bot = FakeBot()
        _run(devbot, _snapshot(done=[task]), bot)
        ok(len([k for k in bot.sent if k.get("message_thread_id") == DEV_TOPIC]) == 1,
           "цель закрыта без замечаний → ровно одна карточка задачи")
    finally:
        os.environ["CURATOR"] = "0"


# ═════ (6) ГРАНИЦЫ: красное в 1160, кнопки на месте, гард не тронут ══════════════════════
def sec6():
    import devbot
    import posttool_feed as PF

    _reset(devbot)
    bot = FakeBot()
    red = {"id": 350, "from": "Filipp-328-dev", "status": "needs_approval",
           "result": "🔴 ЖИВАЯ ТАБЛИЦА — НУЖНО ДА: запись ТО масла в Лист1 Байки",
           "task_text": "тз: запиши ТО", "updated": "2026-08-05T08:00:00Z"}
    _run(devbot, _snapshot(needs_approval=[red]), bot)
    inbox = [k for k in bot.sent if k.get("message_thread_id") == INBOX_TOPIC]
    ok(len(inbox) == 1, f"красная карточка по-прежнему в инбоксе 1160, факт {len(inbox)}")
    ok(all(k.get("message_thread_id") != DEV_TOPIC for k in bot.sent),
       "красное в 328 не продублировано")

    # Правка карточки не должна отнимать кнопку полного отчёта (её ставит часть 2 от 05.08)
    os.environ["CURATOR"] = "1"
    try:
        _reset(devbot)
        bot = FakeBot()
        long_body = ("итог работы. " * 60) + "\nFACT: commit abc1234 в git log origin/main"
        task = {"id": 360, "from": "Filipp-328-dev", "status": "done", "result": long_body,
                "task_text": "тз: длинный отчёт", "updated": "2026-08-05T08:10:00Z"}
        os.environ["REPORTS_DIR"] = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_scratch_lenta_0805shum", "reports_test")
        _run(devbot, _snapshot(done=[task]), bot)
        body = _card_body("задача", 360, "followup", tasks=["хвост"], placed=[(361, "хвост")])
        card = {"id": 362, "from": "Filipp-328-dec", "status": "done", "result": body,
                "task_text": "[куратор задача 360] вердикт куратора",
                "updated": "2026-08-05T08:11:00Z"}
        _run(devbot, _snapshot(done=[task, card]), bot)

        def _has_full(markup):
            try:
                return any(str(getattr(b, "callback_data", "")).startswith("full:")
                           for row in markup.inline_keyboard for b in row)
            except Exception:
                return False
        ok(bool(bot.edits) and _has_full(bot.edits[-1].get("reply_markup")),
           "после вклейки вердикта кнопка «📄 отчёт» осталась под карточкой")
    finally:
        os.environ["CURATOR"] = "0"

    # Лента по-прежнему не зовёт пишущих веток гарда. Судим ВЫЗОВ, а не подстроку: имя
    # `_guard_write_marker` стоит в докстринге ленты как обещание — подстрочная проверка ловила бы
    # собственное обещание и краснела на нём (тот самый класс «красное встаёт на слово»).
    import ast
    tree = ast.parse(open(PF.__file__, encoding="utf-8").read())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for forbidden in ("decision", "classify", "_guard_write_marker", "_push", "_card"):
        ok(forbidden not in called, f"лента не ВЫЗЫВАЕТ {forbidden} у гарда")


section("(1) push заметки не рождает:", sec1)
section("(2) рестарт splinter — внутренний сервис:", sec2)
section("(3) клиентский бот — ПК-процессы:", sec3)
section("(4) одна задача — одно сообщение в 328:", sec4)
section("(5) fail-safe: вердикт со сбоем уходит целиком:", sec5)
section("(6) границы: 1160, кнопки, гард:", sec6)

print(f"\nИТОГО: {sum(_res)}/{len(_res)}")
sys.exit(0 if all(_res) else 1)
