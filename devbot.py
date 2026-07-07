"""Дев-бот (полу-оркестратор), пункт 5 лестницы — первый заход.

ТОЛЬКО зелёные read-only задачи по ЖЁСТКОМУ allowlist (БЕЗ LLM, детерминированно). Живёт в HQ
topic 328 (Splinter там молчит). 205 = pc_agent/userbot на ПК — НЕ наша тема. Команды ТОЛЬКО от Филиппа (504608015).
origin=agent → ЛЮБАЯ попытка красной записи ловится токен-замком 4.2 (rejected+пуш), деплой —
тесты-гейтом 4.3. Красное/вне-allowlist → НЕ выполняет, просит «да». Не новый процесс — на bot.py.
"""
import os
import re
import json
import time
import asyncio
import datetime
import logging
import subprocess
from collections import Counter

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import bridge_client

log = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "bin", "python3")

DEVBOT_USER = 504608015                 # Филипп — единственный, кто командует дев-ботом
HQ_CHAT_ID = -1003853365891
DEVBOT_TOPIC = 328                      # тема dev-bot (VPS). 205 = pc_agent/userbot (ПК) — НЕ наша
CC_LOG_ID = "1464zaINaLnOwXMsHNaEyy-4FpuQCVTYF"


def pc_dev_topic():
    """Тема «PC-дев» (вторая полоса lane=pc, 04.07.2026) — id из env PC_DEV_TOPIC_ID.
    0/пусто/мусор = полоса ВЫКЛЮЧЕНА (id Филипп даёт после создания темы). Читается лениво
    на каждый вызов: bot.py импортирует devbot ДО load_dotenv(), модульная константа
    зафиксировала бы пустое значение."""
    try:
        return int(os.getenv("PC_DEV_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0


def inbox_topic():
    """Тема «Единый инбокс подтверждений» (ст3 оркестратора, KB_MASTER §7 Вариант Б, 06.07.2026)
    из env INBOX_TOPIC_ID. 0/пусто/мусор = ИНБОКС ВЫКЛЮЧЕН → карточки needs_approval идут по старым
    полосам 328/829 (текущее поведение, без регресса); задан → approve-карточки ОБЕИХ полос сходятся
    в эту тему. Лениво (как pc_dev_topic — bot.py импортирует devbot ДО load_dotenv())."""
    try:
        return int(os.getenv("INBOX_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0

BRIDGE = None   # выставляется из bot.py при старте (devbot.BRIDGE = bridge)

# === Фикс заморозки event loop (разбор таймаутов get_pending 02.07.2026) ===
# Синхронные requests к Bridge прямо в async job вешали ВЕСЬ event loop PTB до 60-240с
# (окна деградации Apps Script /exec). Фикс: опрос очереди — ОДНИМ синхронным прогоном в
# отдельном потоке (asyncio.to_thread) + отдельный клиент с коротким timeout: опрос
# идемпотентен, при таймауте просто ждём следующий тик 45с, а не держим 60с.
POLL_TIMEOUT = 15                       # сек на get_pending при опросе очереди (вместо 60)
_REPORT_STATUSES = ("done", "failed", "needs_approval", "in_progress")
_poll_bridge = None                     # ленивый клиент опроса (timeout=POLL_TIMEOUT)
_poll_bridge_for = None                 # BRIDGE, под который создан _poll_bridge (тесты меняют BRIDGE)


def _get_poll_bridge():
    """Отдельный BridgeClient для 45с-опроса очереди (timeout=POLL_TIMEOUT вместо 60с).
    Тестовый/нестандартный BRIDGE без url/token опрашиваем как есть (моки в tests/)."""
    global _poll_bridge, _poll_bridge_for
    b = BRIDGE
    if b is None:
        return None
    if _poll_bridge is None or _poll_bridge_for is not b:
        url = getattr(b, "url", None)
        token = getattr(b, "token", None)
        _poll_bridge = (bridge_client.BridgeClient(url=url, token=token, timeout=POLL_TIMEOUT)
                        if url and token else b)
        _poll_bridge_for = b
    return _poll_bridge


def _poll_queue_sync(pb):
    """СИНХРОННЫЙ опрос очереди одним прогоном — звать ТОЛЬКО через asyncio.to_thread.
    Склейка статусов: get_pending_multi = 1 CSV-вызов на новом Bridge (фоллбэк по-статусно
    на старом/мокнутом). lane='all' (04.07.2026): опрашиваем ОБЕ полосы (vps+pc) — карточки
    pc-задач devbot разносит в тему PC-дев (_item_topic). → {status: [items c from∈QUEUE_FROMS]}
    | None (ошибка → ждём тик)."""
    fn = getattr(pb, "get_pending_multi", None)
    if fn is not None:
        r = fn(_REPORT_STATUSES, lane="all")
    else:                                   # мок в тестах без multi — по-статусно
        items = []
        for st in _REPORT_STATUSES:
            rr = pb.get_pending(st, lane="all")
            if not rr.get("ok"):
                return None
            for it in rr.get("items", []):
                if isinstance(it, dict):
                    it.setdefault("status", st)
                items.append(it)
        r = {"ok": True, "items": items}
    if not r.get("ok"):
        return None
    by = {st: [] for st in _REPORT_STATUSES}
    for it in r.get("items", []):
        st = str(it.get("status") or "")
        if st in by and str(it.get("from")) in QUEUE_FROMS:
            by[st].append(it)
    return by

# === ОРКЕСТРАТОР (ступень1 заход2б-1 + ступень2 O4): дев-бот ↔ очередь ===
# Префикс в 328 → кладём задачу в очередь оркестратора; фоновый job приносит результат обратно.
QUEUE_FROM = "Filipp-328"               # метка источника быстрых задач «задача:» (таймаут 10 мин)
QUEUE_FROM_DEV = "Filipp-328-dev"       # метка дев-ТЗ «тз:» (ступень 2 O4, таймаут 45 мин у демона)
QUEUE_FROM_DEC = "Filipp-328-dec"       # метка декомпозиции «декомпозируй:» (ступень 2 часть C):
                                        # родитель + его шаги «[шаг i/N родитель id]» + сводка
QUEUE_FROM_PC = "Filipp-pc"             # быстрая задача из темы PC-дев (lane=pc, исполняет ПК-агент)
QUEUE_FROM_PC_DEV = "Filipp-pc-dev"     # дев-ТЗ из темы PC-дев (lane=pc)
QUEUE_FROM_PC_DEC = "Filipp-pc-dec"     # декомпозиция ПК-театра (кусок 2, 07.07.2026): родитель
                                        # БЕЗ lane (план строит VPS-демон — единственный мозг),
                                        # шаги демон релизит на lane=pc по одному; карточки → 829
QUEUE_FROMS_PC = (QUEUE_FROM_PC, QUEUE_FROM_PC_DEV, QUEUE_FROM_PC_DEC)  # метки полосы pc (карточки → тема PC-дев)
QUEUE_FROMS = (QUEUE_FROM, QUEUE_FROM_DEV, QUEUE_FROM_DEC) + QUEUE_FROMS_PC  # фильтр отчётов: все наши
_TASK_PREFIXES = ("задача:", "оркестратор:", "task:")
_DEV_PREFIXES = ("тз:", "dev:", "tz:")  # дев-режим: произвольное ТЗ через headless CC, до 45 мин
_DEC_PREFIXES = ("декомпозируй:", "разбей:", "decompose:")  # крупное ТЗ → план шагов → по одному
_reported = set()                       # id задач, уже отрапортованных (done/failed; дедуп, память процесса)
_report_seeded = False                  # seed-on-start: не спамим историей done/failed при рестарте
_asked = set()                          # id задач needs_approval, по которым УЖЕ задан вопрос (дедуп)
# heartbeat/детект-зависания (части 1-2): анонс «в работе» и предупреждение «зависла» — по разу на задачу
_inprogress_seen = set()                # id задач in_progress, по которым УЖЕ слали «🔄 в работе» (дедуп)
_stalled = set()                        # id задач, по которым УЖЕ слали «⚠️ зависла» (дедуп)
STALL_SEC = 720                         # in_progress с updated старше → демон завис/умер (TASK_TIMEOUT 600 + запас 120)

# «да N» / «нет N» (+ англ., + опц. # и пунктуация) — ответ Филиппа на запрос подтверждения (заход 2б-2)
_APPROVAL_RE = re.compile(r"^(да|нет|yes|no)\b[\s,.:]*#?\s*(\d+)\s*$", re.IGNORECASE)
_YES = ("да", "yes")


def _try_approval_reply(text, bridge):
    """«да N» → approve_task(N); «нет N» → complete_task(N, failed). Иначе None.
    Проверяется ПЕРВОЙ в handle_command (специфичный паттерн ответа на запрос подтверждения)."""
    m = _APPROVAL_RE.match((text or "").strip())
    if not m:
        return None
    word = m.group(1).lower()
    qid = int(m.group(2))
    if word in _YES:
        r = bridge.approve_task(qid, "Filipp")
        if r.get("ok"):
            _reported.discard(qid)   # пусть дальнейший done/failed по ней отрапортуется штатно
            return (f"✅ Задача {qid} одобрена — демон выполнит approved-операцию по op-коду "
                    f"(git_push / restart_splinter) и принесёт результат сюда. Вне авто-перечня → failed «сделай в Termux».")
        if r.get("error") == "not_awaiting":
            return f"🤖 Задача {qid} не ждёт подтверждения (статус {r.get('status')}). Ничего не сделал."
        if r.get("error") == "not_found":
            return f"🤖 Задачи {qid} нет в очереди."
        return f"🤖 approve не прошёл: {r.get('error')}"
    else:
        r = bridge.complete_task(qid, "failed", "отклонено Филиппом")
        if r.get("ok"):
            _reported.add(qid)       # уже сообщили «отклонена» — не дублируем failed-рапортом
            return f"🚫 Задача {qid} отклонена — статус failed."
        return f"🤖 Не удалось отклонить задачу {qid}: {r.get('error')}"


# ===================== РОУТЕР ТЕАТРА (кусок 3 «единый пульт», 07.07.2026) =====================
# ОДИН вход (тема 328) для всех команд — система САМА определяет театр исполнения (vps | pc).
# Слой 1 (детерминированный, БЕЗ LLM): явный префикс «пк:»/«pc:» сразу после команды → pc
# (префикс срезается); keyword-классы pc/vps — ровно один класс совпал → он и театр. Оба или
# ни один → слой 2: думатель-классификатор (claude -p, --model haiku --fallback-model sonnet,
# --max-turns 1 — чистый генератор, ничего не исполняет; строгий JSON {"theater":"vps"|"pc"}).
# FAIL-SAFE любого сбоя слоя 2 (запуск/таймаут/exit!=0/мусор) → vps (= прежнее поведение, не
# хуже) + строка-подсказка в карточке приёма. Тема 829 = явный запасной вход БЕЗ роутера
# (форс pc, как раньше). Театр=pc: одиночные «тз:»/«задача:» → ТА ЖЕ 328-метка from (карточки
# идут в тему ПОСТАНОВКИ 328 по from-метке) + lane=pc (claim'ит ПК-агент); «декомпозируй:» →
# родитель QUEUE_FROM_PC_DEC (опора на кусок 2: план строит VPS-демон, шаги lane=pc по одному,
# отчёты цепи — в теме PC-дев по метке цепи). Изоляция полос НЕ ослаблена: роутер только
# ВЫБИРАЕТ полосу при enqueue, claim-механику не трогает. Красное НЕ ослаблено (роутер ничего
# не исполняет). Откат: THEATER_ROUTER=0 в .env + restart splinter — прежнее поведение
# байт-в-байт (пк:-префикс НЕ срезается, 🎭 не показывается, слой 2 не зовётся).
CLAUDE_BIN = "/usr/bin/claude"          # зеркало orchestrator_daemon.CLAUDE_BIN (импорт демона в
                                        # процесс бота нельзя — signal.signal на import, см. выше)
ROUTER_KW_PC = ("userbot", "suggest", "playbook", "модербот", "dispatch",
                "d:\\turbobaby-userbot", "приветстви", "черновик клиенту")
ROUTER_KW_VPS = ("splinter", "bridge", "manager-bot", "registry", "гейт", "cc_log",
                 "devbot", "orchestrator_daemon", "vps")
ROUTER_HINT = "театр: vps (по умолчанию); нужен ПК — префикс пк:"
_PC_TEXT_PREFIXES = ("пк:", "pc:")      # явный префикс театра сразу после команды («тз: пк: …»)


def _router_on():
    """THEATER_ROUTER (деф. 1 = включён). Лениво на каждый вызов: bot.py импортирует devbot
    ДО load_dotenv() (как pc_dev_topic)."""
    return str(os.getenv("THEATER_ROUTER", "1")).strip().lower() not in ("0", "false", "off")


def _router_timeout():
    """Таймаут слоя 2 в секундах (THEATER_ROUTER_TIMEOUT, деф. 45с; haiku отвечает за секунды)."""
    try:
        return int(os.getenv("THEATER_ROUTER_TIMEOUT", "45") or 45)
    except (TypeError, ValueError):
        return 45


def _classify_theater(task_text):
    """Слой 2: думатель-классификатор театра — claude -p дешёвым кондуктором haiku→sonnet
    (--max-turns 1, --output-format json; зеркало orchestrator_daemon._thinker_exec).
    → 'vps' | 'pc' | None при ЛЮБОМ сбое (fail-safe, решает вызывающий)."""
    model = (os.getenv("ROUTER_MODEL") or "haiku").strip() or "haiku"
    fallback = (os.getenv("ROUTER_MODEL_FALLBACK") or "sonnet").strip() or "sonnet"
    prompt = (
        "Ты — роутер театра исполнения дев-задач TurboBaby. Театры:\n"
        "- vps: серверный репозиторий manager-bot на VPS (Splinter-бот, bot.py, Apps Script "
        "Bridge, гейт тестов, cc_log, devbot, orchestrator_daemon, деплой/рестарт на VPS).\n"
        "- pc: репозиторий userbot на ПК Windows (D:\\turbobaby-userbot: suggest.py, playbook, "
        "модербот, Dispatch, приветствия и черновики ответов клиентам).\n"
        "Определи театр задачи. Ответь СТРОГО одним JSON без пояснений и без markdown:\n"
        "{\"theater\":\"vps\"|\"pc\",\"reason\":\"одна строка\"}\n\n"
        f"ЗАДАЧА (дословно):\n{str(task_text or '')[:2000]}")
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    child_env.pop("ANTHROPIC_API_KEY", None)   # как думатели демона: по ~/.claude, не платный API
    child_env.pop("OPENAI_API_KEY", None)
    cmd = [CLAUDE_BIN, "-p",
           "--model", model,
           "--fallback-model", fallback,
           "--output-format", "json",
           "--max-turns", "1",
           prompt]                             # prompt последним (тест-моки читают args[-1])
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=_router_timeout(), env=child_env)
    except Exception as e:
        log.warning("theater-router: классификатор не отработал (%s) — fail-safe vps", e)
        return None
    if proc.returncode != 0:
        log.warning("theater-router: классификатор exit=%s — fail-safe vps", proc.returncode)
        return None
    out = (proc.stdout or "").strip()
    try:
        env_j = json.loads(out)
        if isinstance(env_j, dict) and "result" in env_j:   # CLI-конверт --output-format json
            out = (env_j.get("result") or "").strip()
    except Exception:
        pass
    i, j = out.find("{"), out.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(out[i:j + 1])
    except Exception:
        return None
    th = str(d.get("theater") or "").strip().lower() if isinstance(d, dict) else ""
    return th if th in ("vps", "pc") else None


def _route_theater(task_text):
    """Роутер театра → (театр 'vps'|'pc', текст без явного пк:-префикса, note|None —
    строка-подсказка при fail-safe слоя 2)."""
    t = (task_text or "").strip()
    low = t.lower()
    for p in _PC_TEXT_PREFIXES:
        if low.startswith(p):
            return "pc", t[len(p):].strip(), None
    pc_hit = any(k in low for k in ROUTER_KW_PC)
    vps_hit = any(k in low for k in ROUTER_KW_VPS)
    if pc_hit != vps_hit:                      # ровно один класс совпал → слой 1 решил
        return ("pc" if pc_hit else "vps"), t, None
    th = _classify_theater(t)                  # оба/ни один → слой 2 (думатель)
    if th is not None:
        return th, t, None
    return "vps", t, ROUTER_HINT               # fail-safe: vps + подсказка владельцу


def _route_328(task_text):
    """Роутер для темы 328. Выключен (THEATER_ROUTER=0) → (None, текст как есть, None) —
    прежнее поведение байт-в-байт, 🎭 в карточке не показываем.
    ТОТАЛЬНЫЙ fail-safe (инцидент 07.07.2026): ЛЮБОЕ исключение роутера (не только пойманные
    внутри _classify_theater сбои классификатора — unauthorized CLI, exit!=0, таймаут, мусор) →
    театр vps + подсказка в карточке. Постановка задачи из-за роутера НЕ падает НИКОГДА."""
    if not _router_on():
        return None, task_text, None
    try:
        return _route_theater(task_text)
    except Exception as e:
        log.warning("theater-router: роутер упал (%s) — ТОТАЛЬНЫЙ fail-safe vps", e)
        return "vps", task_text, ROUTER_HINT


def _router_card(theater, note):
    """Хвост карточки приёма с решением роутера: «🎭 vps|pc» (+ подсказка fail-safe).
    theater=None (роутер выключен) → пустая строка (карточка как раньше)."""
    if theater is None:
        return ""
    s = f"\n🎭 {theater}"
    if note:
        s += f"\n{note}"
    return s


def _find_enqueued(bridge, frm, text):
    """Verify после сбойного enqueue: есть ли НАША задача (тот же from + текст ДОСЛОВНО) в new
    (обе полосы)? → id | None. Любой сбой чтения → None (не хуже прежнего)."""
    try:
        rr = bridge.get_pending("new", lane="all")
        if not rr.get("ok"):
            return None
        for it in rr.get("items", []):
            if isinstance(it, dict) and str(it.get("from") or "") == frm \
                    and str(it.get("task_text") or "") == text:
                return it.get("id")
    except Exception:
        return None
    return None


def _enqueue_reliable(bridge, frm, text, lane=None):
    """Постановка, которая НЕ падает наружу зря (инцидент 07.07.2026, задача 138): Bridge в сбое
    (404 на redirect-echo) может ИСПОЛНИТЬ enqueue, потеряв ответ («unauthorized»/request_failed
    клиенту) — Филипп видел «не удалось», хотя задача встала. Слепой ретрай дал бы ДУБЛЬ, поэтому:
    (1) enqueue; ok → как раньше; (2) сбой → verify: задача с тем же from+текстом уже в new →
    ответ потерялся, считаем поставленной (её id); (3) не нашли → РОВНО один повтор enqueue;
    (4) снова сбой → честная ошибка (карточка «не удалось», как раньше). Не хуже прежнего ни в
    одной ветке; красное не ослаблено (это только постановка в очередь)."""
    kw = {} if lane is None else {"lane": lane}      # без lane зовём БЕЗ kwarg (форма как раньше)
    r = bridge.enqueue_task(frm, text, **kw)
    if r.get("ok"):
        return r
    err1 = r.get("error")
    qid = _find_enqueued(bridge, frm, text)
    if qid is not None:
        log.warning("enqueue: ответ потерялся (%s), но задача %s найдена в new — поставлена", err1, qid)
        return {"ok": True, "id": qid}
    r2 = bridge.enqueue_task(frm, text, **kw)
    if r2.get("ok"):
        log.warning("enqueue: первая попытка упала (%s) — повтор успешен (id=%s)", err1, r2.get("id"))
    else:
        log.warning("enqueue: обе попытки упали (%s / %s) — честная ошибка Филиппу", err1, r2.get("error"))
    return r2


def _try_enqueue(text, bridge, lane="vps"):
    """Если текст начинается с префикса задачи — кладём в очередь оркестратора. Иначе None.
    «тз:»/«dev:» → метка QUEUE_FROM_DEV (демон даст 45 мин); «задача:» → быстрый режим (10 мин).
    Проверяется ДО allowlist (иначе ключевые слова в тексте задачи перехватили бы зелёную команду).
    lane='pc' (тема PC-дев, 04.07.2026): «тз:»/«задача:» → enqueue с lane='pc' и метками
    Filipp-pc-dev / Filipp-pc (исполняет ПК-агент); «декомпозируй:» (ПК-театр кусок 2,
    07.07.2026) → родитель QUEUE_FROM_PC_DEC БЕЗ lane (план строит VPS-демон — единственный
    планировщик), шаги демон релизит на lane=pc по одному.
    lane='vps' (328, кусок 3 «единый пульт» 07.07.2026): текст задачи идёт через роутер театра
    (_route_328). Театр vps → вызовы enqueue_task байт-в-байт как раньше (БЕЗ lane — Bridge
    дефолтит vps); театр pc → одиночные с 328-меткой + lane='pc' (карточки в тему постановки),
    «декомпозируй:» → родитель QUEUE_FROM_PC_DEC (кусок 2). Карточка приёма показывает 🎭."""
    t = (text or "").strip()
    low = t.lower()
    pc = (lane == "pc")
    for p in _DEC_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return ("🤖 Пустое ТЗ. Формат: «декомпозируй: <крупное ТЗ>» — разобью на шаги "
                        "и выполню по одному.")
            if pc:
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEC, task_text)
                if r.get("ok"):
                    return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (театр PC): план "
                            f"построит VPS-дирижёр (~60с), шаги уйдут ПК-агенту по одному "
                            f"(lane=pc). Каждый шаг отчитается сюда; красный спрошу кнопкой; "
                            f"в конце — сводка. ПК выключен → цепь честно упадёт по таймауту.")
                return f"🤖 Не удалось поставить ТЗ на декомпозицию: {r.get('error')}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return ("🤖 Пустое ТЗ. Формат: «декомпозируй: <крупное ТЗ>» — разобью на шаги "
                        "и выполню по одному.")
            if theater == "pc":
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEC, task_text)
                if r.get("ok"):
                    return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (театр PC): план "
                            f"построит VPS-дирижёр (~60с), шаги уйдут ПК-агенту по одному "
                            f"(lane=pc); отчёты шагов и сводка цепи — в теме PC-дев (метка цепи "
                            f"pc), красный шаг спрошу кнопкой. ПК выключен → цепь честно упадёт "
                            f"по таймауту." + _router_card("pc", note))
                return f"🤖 Не удалось поставить ТЗ на декомпозицию: {r.get('error')}"
            r = _enqueue_reliable(bridge, QUEUE_FROM_DEC, task_text)
            if r.get("ok"):
                return (f"🧩 ТЗ {r.get('id')} в очереди на декомпозицию (демон возьмёт ~60с). "
                        f"Сначала верну план шагов, затем шаги пойдут отдельными задачами по одному "
                        f"(каждый отчитается сюда; красный шаг спрошу кнопкой), в конце — сводка."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить ТЗ на декомпозицию: {r.get('error')}"
    for p in _DEV_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return "🤖 Пустое ТЗ. Формат: «тз: <что сделать>» (дев-режим, до 45 мин)."
            if pc:
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC_DEV, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ ТЗ {r.get('id')} в очереди полосы PC (lane=pc) — возьмёт ПК-агент. "
                            f"Статусы/красные вопросы/итог принесу в эту тему.")
                return f"🤖 Не удалось поставить ТЗ в очередь: {r.get('error')}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return "🤖 Пустое ТЗ. Формат: «тз: <что сделать>» (дев-режим, до 45 мин)."
            if theater == "pc":
                r = _enqueue_reliable(bridge, QUEUE_FROM_DEV, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ ТЗ {r.get('id')} в очереди (театр PC, lane=pc) — возьмёт ПК-агент. "
                            f"Статусы/красные вопросы/итог принесу сюда, в тему постановки."
                            + _router_card("pc", note))
                return f"🤖 Не удалось поставить ТЗ в очередь: {r.get('error')}"
            r = _enqueue_reliable(bridge, QUEUE_FROM_DEV, task_text)
            if r.get("ok"):
                return (f"✅ ТЗ {r.get('id')} в очереди (дев-режим, до 45 мин; демон возьмёт ~60с). "
                        f"Работает headless Claude Code: зелёное/оранжевое (вкл. restart splinter "
                        f"через гейт) сам, настоящее красное спрошу кнопкой. Результат принесу сюда."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить ТЗ в очередь: {r.get('error')}"
    for p in _TASK_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return "🤖 Пустая задача. Формат: «задача: <что сделать>»."
            if pc:
                r = _enqueue_reliable(bridge, QUEUE_FROM_PC, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ Задача {r.get('id')} в очереди полосы PC (lane=pc) — возьмёт ПК-агент. "
                            f"Принесу результат в эту тему, когда будет done/failed.")
                return f"🤖 Не удалось поставить задачу в очередь: {r.get('error')}"
            theater, task_text, note = _route_328(task_text)
            if not task_text:
                return "🤖 Пустая задача. Формат: «задача: <что сделать>»."
            if theater == "pc":
                r = _enqueue_reliable(bridge, QUEUE_FROM, task_text, lane="pc")
                if r.get("ok"):
                    return (f"✅ Задача {r.get('id')} в очереди (театр PC, lane=pc) — возьмёт "
                            f"ПК-агент. Результат принесу сюда, в тему постановки."
                            + _router_card("pc", note))
                return f"🤖 Не удалось поставить задачу в очередь: {r.get('error')}"
            r = _enqueue_reliable(bridge, QUEUE_FROM, task_text)
            if r.get("ok"):
                return (f"✅ Задача {r.get('id')} поставлена в очередь — демон возьмёт её (опрос ~60с). "
                        f"Принесу результат сюда, когда будет done/failed."
                        + _router_card(theater, note))
            return f"🤖 Не удалось поставить задачу в очередь: {r.get('error')}"
    return None


# ===================== INLINE-КНОПКИ (вместо «да N») =====================
# Спека: KB_DEVBOT_BUTTONS_SPEC. Под needs_approval — ✅/❌ (одноразовые) + 🔄/📋 (многоразовые);
# под done — только 🔄/📋. callback_data: approve|reject|check|next : <id>. Зелёная зона (UI Splinter).
def _kb_approval(qid):
    """Кнопки под needs_approval: одноразовые ✅ Да, деплой / ❌ Нет + многоразовые 🔄 Проверь / 📋 Дальше."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, деплой", callback_data=f"approve:{qid}"),
         InlineKeyboardButton("❌ Нет", callback_data=f"reject:{qid}")],
        [InlineKeyboardButton("🔄 Проверь", callback_data=f"check:{qid}"),
         InlineKeyboardButton("📋 Дальше", callback_data=f"next:{qid}")],
    ])


def _kb_done(qid):
    """Кнопки под done: многоразовые 🔄 Проверь / 📋 Дальше (✅/❌ тут не нужны — задача уже завершена)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Проверь", callback_data=f"check:{qid}"),
         InlineKeyboardButton("📋 Дальше", callback_data=f"next:{qid}")],
    ])


def _find_task(bridge, qid):
    """Найти задачу по id среди всех статусов очереди → (status, item) | (None, None). read-only
    (get_pending, lane='all' — кнопки 🔄/📋 работают и под карточками полосы pc)."""
    for st in ("needs_approval", "approved", "in_progress", "new", "done", "failed"):
        try:
            r = bridge.get_pending(st, lane="all")
        except Exception:
            continue
        if not r.get("ok"):
            continue
        for it in r.get("items", []):
            if str(it.get("id")) == str(qid):
                return st, it
    return None, None


def _is_pc_item(it):
    """Задача полосы pc? По полю lane (новый Bridge) ИЛИ по метке from (работает и до redeploy)."""
    lane = str((it or {}).get("lane") or "").strip().lower()
    return lane == "pc" or str((it or {}).get("from") or "") in QUEUE_FROMS_PC


def _item_topic(it):
    """Тема для карточки задачи — по метке from = тема ПОСТАНОВКИ (кусок 3 «единый пульт»,
    07.07.2026): from полосы pc (Filipp-pc*) → тема PC-дев; иначе → 328. Задача, поставленная
    в 328 и роутнутая на театр pc (from=Filipp-328*, lane=pc), отчитывается в 328 — где её
    ставили. По lane тему НЕ решаем (lane = полоса ИСПОЛНЕНИЯ, не тема владельца); ярлык [pc]
    в карточке остаётся по lane (_item_lane_label)."""
    if str((it or {}).get("from") or "") in QUEUE_FROMS_PC:
        return pc_dev_topic() or DEVBOT_TOPIC
    return DEVBOT_TOPIC


def _item_lane_label(it):
    """Ярлык полосы для строки инбокса: pc → 'pc', иначе 'vps'."""
    return "pc" if _is_pc_item(it) else "vps"


# === Отпечаток конверта для дедупа В СПИСКЕ /inbox (ст3, часть г) ===
# ЗЕРКАЛО orchestrator_daemon.parse_op / _OP_PREFIX_RE (см. AUTO_OPS там). Импортировать демон в
# процесс бота нельзя: его модуль на import ставит signal.signal — в рабочем потоке to_thread это
# ValueError, а в main-потоке перебил бы обработчики PTB. Логика отпечатка крошечная — повторяем.
# КОРНЕВОЙ дедуп конвертов в очереди тут НЕ решаем (отдельный заход §7) — только схлопывание строк.
_INBOX_AUTO_OPS = ("git_push", "restart_splinter")
_INBOX_OP_RE = re.compile(r"op\s*=\s*([a-z_]+)", re.IGNORECASE)
_INBOX_OP_PREFIX_RE = re.compile(r"^\s*op\s*=\s*[a-z_]+\s*\|\s*", re.IGNORECASE)


def _inbox_fingerprint(what):
    """Отпечаток карточки needs_approval = (op-код, очищенный от 'op=… |' текст). НЕ по id —
    одинаковые конверты (один и тот же op + один и тот же текст) схлопываются в списке в одну строку."""
    w = str(what or "")
    m = _INBOX_OP_RE.search(w)
    op = m.group(1).lower() if m else "other"
    if op not in _INBOX_AUTO_OPS:
        op = "other"
    card = _INBOX_OP_PREFIX_RE.sub("", w).strip()
    return op, card


def build_inbox(bridge):
    """ЕДИНЫЙ ИНБОКС (ст3, часть в+г): текст-список ВСЕХ открытых needs_approval по ОБЕИМ полосам
    (get_pending needs_approval lane='all' — чистый read-only GET, без записи). Дедуп в списке по
    отпечатку конверта (_inbox_fingerprint, НЕ id): одинаковые карточки — одной строкой ×N со списком
    id и возрастом старейшей. Пусто/ошибка → человеческая строка. Зона 🟢 (read-only)."""
    try:
        r = bridge.get_pending("needs_approval", lane="all")
    except Exception as e:
        return f"📥 Инбокс: ошибка чтения очереди ({type(e).__name__}: {e})."
    if not r.get("ok"):
        return f"📥 Инбокс: очередь недоступна ({r.get('error')})."
    items = [it for it in (r.get("items") or []) if isinstance(it, dict)]
    if not items:
        return "📥 Инбокс пуст — открытых подтверждений нет 👍"
    # группировка по отпечатку конверта
    groups = {}   # fp -> {"op", "card", "lanes":set, "ids":[], "ages":[]}
    for it in items:
        what = str(it.get("result") or "")
        op, card = _inbox_fingerprint(what)
        g = groups.setdefault((op, card), {"op": op, "card": card, "lanes": set(), "ids": [], "ages": []})
        g["lanes"].add(_item_lane_label(it))
        try:
            g["ids"].append(int(it.get("id")))
        except (TypeError, ValueError):
            g["ids"].append(it.get("id"))
        age = _task_age_sec(it.get("updated"))
        if age is not None:
            g["ages"].append(age)
    total = len(items)
    out = [f"📥 Инбокс подтверждений: открыто {total} (по обеим полосам vps+pc):"]
    # старейшая группа сверху (по максимальному возрасту в группе; без возраста → в конец)
    ordered = sorted(groups.values(),
                     key=lambda g: (-(max(g["ages"]) if g["ages"] else -1), min(str(i) for i in g["ids"])))
    for g in ordered:
        ids = g["ids"]
        n = len(ids)
        lanes = "/".join(sorted(g["lanes"]))
        op = g["op"]
        card1 = (g["card"] or "(карточка пустая — см. исходную задачу)").splitlines()[0][:200]
        oldest = max(g["ages"]) if g["ages"] else None
        if n == 1:
            age_txt = f", висит {int(oldest // 60)} мин" if oldest is not None else ""
            out.append(f"  • id {ids[0]} [{lanes}] op={op}{age_txt}")
        else:
            id_list = ", ".join(str(i) for i in sorted(ids, key=lambda x: str(x)))
            age_txt = f", старейшая {int(oldest // 60)} мин" if oldest is not None else ""
            out.append(f"  • ×{n} [{lanes}] op={op} (id: {id_list}{age_txt})")
        out.append(f"      {card1}")
    out.append("\nОтвет: тапни ✅/❌ под карточкой в теме, либо «да N» / «нет N».")
    return "\n".join(out)


async def _strip_and_mark(q, mark):
    """Одноразовые ✅/❌: убрать кнопки и дописать пометку к тексту сообщения.
    editMessageText заодно снимает reply_markup; если упало — хотя бы снять кнопки."""
    base = (q.message.text or "") if q.message else ""
    new_text = f"{base}\n\n{mark}" if base else mark
    try:
        await q.edit_message_text(text=new_text)
    except Exception as e:
        log.warning("devbot._strip_and_mark: edit_message_text упал (%s)", e)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


async def _send_thread(context, q, text):
    """Отдельным сообщением в ту же тему (для многоразовых 🔄/📋 — исходные кнопки остаются)."""
    tid = getattr(q.message, "message_thread_id", None) or DEVBOT_TOPIC
    for chunk in _chunks(text):
        try:
            await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=tid, text=chunk)
        except Exception as e:
            log.warning("devbot._send_thread: отправка не прошла (%s)", e)


async def _btn_answer(q, txt=None, **kw):
    """q.answer() с защитой — паттерн _o3_answer (хвост ревизии §7): колбэк, отлежавшийся
    в очереди за долгим Bridge-вызовом (approve/check ходят в Apps Script по несколько секунд),
    протухает — BadRequest «Query is too old». Ack тогда невозможен, но ДЕЙСТВИЕ кнопки
    обязано выполниться; упавший q.answer не валит хендлер."""
    try:
        await q.answer(txt, **kw)
    except Exception as e:
        log.warning("devbot: q.answer протух/упал (действие кнопки всё равно выполняю): %s", e)


async def _cb_approve(q, qid, bridge):
    """approve:<id> → approve_task (та же логика «да N»). ОДНОРАЗОВО + идемпотентность."""
    r = await asyncio.to_thread(bridge.approve_task, qid, "Filipp")
    if r.get("ok"):
        _reported.discard(qid)            # пусть дальнейший done/failed отрапортуется штатно
        await _btn_answer(q, "✅ одобрено")
        await _strip_and_mark(q, "✅ одобрено")
    elif r.get("error") == "not_awaiting":
        # уже approved/done/failed → идемпотентно: сообщить + убрать кнопки (гонка/повторный тап)
        await _btn_answer(q, "уже обработано")
        await _strip_and_mark(q, f"✅ уже обработано (статус {r.get('status')})")
    elif r.get("error") == "not_found":
        await _btn_answer(q, "задачи нет в очереди")
        await _strip_and_mark(q, "🤖 задачи нет в очереди")
    else:
        await _btn_answer(q, f"approve не прошёл: {r.get('error')}")


async def _cb_reject(q, qid, bridge):
    """reject:<id> → complete_task failed (как «нет N»). ОДНОРАЗОВО."""
    r = await asyncio.to_thread(bridge.complete_task, qid, "failed", "отклонено Филиппом (кнопка)")
    if r.get("ok"):
        _reported.add(qid)                # уже сообщили «отклонена» — не дублируем failed-рапортом
        await _btn_answer(q, "❌ отклонено")
        await _strip_and_mark(q, "❌ отклонено")
    elif r.get("error") == "not_found":
        await _btn_answer(q, "задачи нет в очереди")
        await _strip_and_mark(q, "🤖 задачи нет в очереди")
    else:
        await _btn_answer(q, f"reject не прошёл: {r.get('error')}")


async def _cb_check(context, q, qid, bridge):
    """check:<id> → свежий статус задачи. МНОГОРАЗОВО (кнопка остаётся → новое сообщение)."""
    await _btn_answer(q, "проверяю…")
    status, item = await asyncio.to_thread(_find_task, bridge, qid)
    if status is None:
        txt = f"🔄 Задача {qid}: не найдена в очереди."
    else:
        res = (item.get("result") or "").strip()
        upd = item.get("updated") or ""
        txt = f"🔄 Задача {qid}: статус {status}" + (f"\nupdated: {upd}" if upd else "")
        if res:
            txt += f"\n\n{res[:1500]}"
    await _send_thread(context, q, txt)


async def _cb_next(context, q, qid, bridge):
    """next:<id> → подсказка по следующему шагу. МНОГОРАЗОВО (кнопка остаётся → новое сообщение)."""
    await _btn_answer(q, "📋")
    status, _item = await asyncio.to_thread(_find_task, bridge, qid)
    if status is None:
        txt = f"📋 Задача {qid}: не найдена — поставь новую командой «задача: <что сделать>»."
    elif status == "done":
        txt = (f"📋 Задача {qid} — done. Следующий шаг: новой командой «задача: <что дальше>» "
               f"или 🔄 Проверь для свежего статуса.")
    elif status == "needs_approval":
        txt = f"📋 Задача {qid} ждёт твоего решения (красная зона). Тапни ✅ Да, деплой / ❌ Нет."
    elif status in ("approved", "in_progress", "new"):
        txt = f"📋 Задача {qid}: статус {status} — в работе. Жди завершения или 🔄 Проверь."
    else:
        txt = f"📋 Задача {qid}: статус {status}."
    await _send_thread(context, q, txt)


async def handle_callback(update, context, bridge) -> None:
    """Inline-кнопки дев-бота (вместо «да N»). ТОЛЬКО Филипп (504608015); чужой → answer «не для тебя».
    answerCallbackQuery на каждый тап. approve/reject — одноразовые; check/next — многоразовые."""
    q = update.callback_query
    if not q:
        return
    uid = q.from_user.id if q.from_user else None
    if uid != DEVBOT_USER:
        await _btn_answer(q, "не для тебя", show_alert=False)
        return
    try:
        action, sid = (q.data or "").split(":", 1)
        qid = int(sid)
    except Exception:
        await _btn_answer(q)
        return
    # origin=human (как «да N»): тап Филиппа = ручное действие, токен-замок 4.2 не вмешивается.
    try:
        if action == "approve":
            await _cb_approve(q, qid, bridge)
        elif action == "reject":
            await _cb_reject(q, qid, bridge)
        elif action == "check":
            await _cb_check(context, q, qid, bridge)
        elif action == "next":
            await _cb_next(context, q, qid, bridge)
        else:
            await _btn_answer(q)
    except Exception as e:
        log.exception("devbot.handle_callback error (%s:%s)", action, qid)
        await _btn_answer(q, f"ошибка: {type(e).__name__}")


def _task_age_sec(updated_iso):
    """Возраст последнего updated задачи в секундах (по ISO из очереди). None при ошибке разбора
    → зависание НЕ объявляем (лучше не пугать ложняком, чем поднять тревогу из-за парсинга)."""
    try:
        s = str(updated_iso).replace("Z", "+00:00")
        t = datetime.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None


async def report_results(context) -> None:
    """Фоновый job (раз в ~45с): приносит в 328 результат задач from=Filipp-328, ставших done/failed.
    Дедуп: _reported (память процесса). Seed-on-start: первый прогон лишь помечает уже-завершённые
    как отрапортованные, чтобы при рестарте не присылать всю историю заново.
    Фикс 02.07: весь опрос очереди — ОДИН прогон в отдельном потоке (to_thread, timeout 15с) —
    event loop не встаёт, бот отвечает на кнопки/сообщения, даже когда Bridge тупит."""
    global _report_seeded
    pb = _get_poll_bridge()
    if pb is None:
        return
    try:
        by = await asyncio.to_thread(_poll_queue_sync, pb)
    except Exception as e:
        log.warning("devbot.report_results: опрос очереди упал (%s)", e)
        return
    if by is None:
        return          # таймаут/ошибка опроса — не страшно, следующий тик через 45с

    finished = [(st, it) for st in ("done", "failed") for it in by[st]]
    finished.sort(key=lambda x: int(x[1].get("id") or 0))   # старые задачи рапортуем первыми

    if not _report_seeded:
        for _st, it in finished:
            _reported.add(it.get("id"))
        _report_seeded = True
        return

    for st, it in finished:
        qid = it.get("id")
        if qid in _reported:
            continue
        _reported.add(qid)
        emoji = "✅" if st == "done" else "❌"
        body = it.get("result") or "(пустой результат)"
        head = f"{emoji} Задача {qid} — {st}\n\n{body}"
        chunks = _chunks(head)
        for i, chunk in enumerate(chunks):
            kw = {"chat_id": HQ_CHAT_ID, "message_thread_id": _item_topic(it), "text": chunk}
            if st == "done" and i == len(chunks) - 1:   # 🔄/📋 только под done, на последнем чанке
                kw["reply_markup"] = _kb_done(qid)
            try:
                await context.bot.send_message(**kw)
            except Exception as e:
                log.warning("devbot.report_results: отправка результата задачи %s упала (%s)", qid, e)

    # needs_approval (заход 2б-2): задача упёрлась в красную зону — спрашиваем «да N»/«нет N».
    # БЕЗ seed (незакрытый вопрос после рестарта стоит переспросить); дедуп = _asked в памяти процесса.
    # ЕДИНЫЙ ИНБОКС (ст3, часть б): если INBOX_TOPIC_ID задан — approve-карточки ОБЕИХ полос сходятся
    # в тему-инбокс; не задан → прежнее поведение (_item_topic: vps→328, pc→829), без регресса.
    # Кнопки approve/reject/check/next те же — callback тем-агностичен (по id, не по теме).
    # done/failed/heartbeat выше ОСТАЮТСЯ по полосам _item_topic (в инбокс НЕ сводятся).
    inbox = inbox_topic()
    pend = sorted(by["needs_approval"], key=lambda x: int(x.get("id") or 0))
    for it in pend:
        qid = it.get("id")
        if qid in _asked:
            continue
        _asked.add(qid)
        _approval_topic = inbox or _item_topic(it)
        what = it.get("result") or "(не уточнено)"
        lane = _item_lane_label(it)
        q = (f"⚠️ Задача {qid} [{lane}] требует подтверждения красной зоны:\n\n{what}\n\n"
             f"Подтвердить? Тапни кнопку ниже — или ответь «да {qid}» / «нет {qid}».")
        chunks = _chunks(q)
        for i, chunk in enumerate(chunks):
            kw = {"chat_id": HQ_CHAT_ID, "message_thread_id": _approval_topic, "text": chunk}
            if i == len(chunks) - 1:   # кнопки ✅/❌/🔄/📋 на последнем чанке
                kw["reply_markup"] = _kb_approval(qid)
            try:
                await context.bot.send_message(**kw)
            except Exception as e:
                log.warning("devbot.report_results: вопрос по задаче %s не ушёл (%s)", qid, e)

    # in_progress (heartbeat/детект-зависания, части 1-2): «🔄 в работе» один раз + «⚠️ зависла» один раз.
    # Анти-спам: дедуп _inprogress_seen / _stalled — НЕ шлём на каждом 45с-проходе.
    running = sorted(by["in_progress"], key=lambda x: int(x.get("id") or 0))
    for it in running:
        qid = it.get("id")
        if qid not in _inprogress_seen:        # анонс «в работе» — один раз на задачу
            _inprogress_seen.add(qid)
            task_text = str(it.get("task_text") or "")[:120]
            msg = f"🔄 Задача {qid} в работе…\n\n{task_text}"
            for chunk in _chunks(msg):
                try:
                    await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=_item_topic(it), text=chunk)
                except Exception as e:
                    log.warning("devbot.report_results: анонс in_progress %s не ушёл (%s)", qid, e)
        if qid not in _stalled:                # детект зависания — один раз на задачу
            age = _task_age_sec(it.get("updated"))
            if age is not None and age > STALL_SEC:
                _stalled.add(qid)
                mins = int(age // 60)
                if _is_pc_item(it):
                    hint = "ПК-агент полосы pc не отвечает — проверь агента на ПК."
                else:
                    hint = "демон оркестратора не отвечает.\nПроверь: systemctl status orchestrator-daemon"
                w = f"⚠️ Задача {qid} зависла — нет heartbeat ~{mins} мин ({hint})"
                for chunk in _chunks(w):
                    try:
                        await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=_item_topic(it), text=chunk)
                    except Exception as e:
                        log.warning("devbot.report_results: warn о зависании %s не ушло (%s)", qid, e)


# ===================== ЗЕЛЁНЫЕ ЗАДАЧИ (read-only) =====================
def _g_health():
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "health.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        return r.stdout.strip() or "health: нет вывода"
    except Exception as e:
        return f"health не запустился: {e}"


def _g_audit(bridge):
    r = bridge.audit_list()
    if not r.get("ok"):
        return f"аудит недоступен: {r.get('error')}"
    items = r.get("items") or []
    opn = [it for it in items if str(it.get("status", "")).lower() in ("new", "open", "", "pending")]
    by = Counter(str(it.get("verdict", "?")) for it in opn)
    out = [f"🔎 Аудит: всего {len(items)}, открытых {len(opn)}"]
    for v, c in by.most_common():
        out.append(f"  {v}: {c}")
    return "\n".join(out)


def _g_writelog(bridge, n=15):
    r = bridge.read_write_log(limit=n)
    if not r.get("ok"):
        return f"боевой_лог недоступен: {r.get('error')}"
    items = r.get("items") or []
    out = [f"⬛ Боевой лог (посл. {len(items)} из {r.get('total')}):"]
    for it in items:
        crit = f" [{it.get('critical')}]" if it.get("critical") else ""
        out.append(f"  {it.get('logged_at')} | {it.get('initiator')} | {it.get('action')} | {it.get('result')}{crit}")
    return "\n".join(out)


def _g_cclog(bridge, n=12):
    r = bridge._call("read_doc", id=CC_LOG_ID)
    if not r.get("ok"):
        return f"cc_log недоступен: {r.get('error')}"
    lines = (r.get("text") or "").splitlines()
    return "📋 cc_log (свежие):\n" + "\n".join(lines[:n])


def _g_errors():
    try:
        with open(os.path.join(ROOT, "splinter.log"), encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"splinter.log недоступен: {e}"
    err = sum(1 for l in lines if "[ERROR]" in l)
    warn = sum(1 for l in lines if "[WARNING]" in l)
    tail = [l.rstrip()[:120] for l in lines if "[ERROR]" in l][-5:]
    return (f"🪵 splinter.log: ERROR {err}, WARNING {warn} (строк {len(lines)})\n" +
            "\n".join("  " + t for t in tail))


def _g_brain(bridge):
    out = ["🧠 Brain (латентность чтения):"]
    for name in ("cc_log", "review", "project_state", "knowledge_base"):
        t0 = time.time()
        r = bridge._call("read_doc", name=name)
        dt = time.time() - t0
        out.append(f"  {name}: {dt:.1f}с {'ok' if r.get('ok') else '✗'} ({len(r.get('text') or '')})")
    return "\n".join(out)


def _g_overdue(bridge):
    """Просрочки ТО парка — переиспользуем прод-скан O3 (splinter._o3_overdue_scan, read-only).
    Топ-10 худших строками; «не делалось» помечаем, остальное «+N км»."""
    import splinter                     # локальный импорт — не плодить связность на уровне модуля
    ov = splinter._o3_overdue_scan(bridge).get("overdue") or []
    if not ov:
        return "🔧 Просрочек ТО нет 👍"
    out = [f"🔧 Просрочки ТО: {len(ov)} байков (худшие сверху, топ-10):"]
    for o in ov[:10]:
        parts = []
        for it in o["items"]:
            lbl = splinter._MAND_LABEL.get(it["kind"], (str(it["kind"]), str(it["kind"])))[1]
            parts.append(f"{lbl} ❗не делалось" if it.get("nobase") else f"{lbl} +{it['over_km']}км")
        out.append(f"  ⚠️ {splinter._o3_bike_label(o['bike'], o['plate'])} · " + ", ".join(parts))
    if len(ov) > 10:
        out.append(f"  …ещё {len(ov) - 10} (полный board — /o3board)")
    return "\n".join(out)


def _g_pulse(bridge):
    """Пульс проекта — одна строка KB_PULSE (read_doc name=pulse), мгновенный «где я сейчас»."""
    r = bridge._call("read_doc", name="pulse")
    if not r.get("ok"):
        return f"пульс недоступен: {r.get('error')}"
    return "📟 " + (r.get("text") or "").strip()


def _g_registry():
    """Реестр знания — сверка карта↔реальность (registry_check.py, read-only: git + read_doc +
    счёт файлов Brain, БЕЗ LLM). Сжатый отчёт для телефона: «✅ СХОДИТСЯ» или список расхождений.
    Подпроцессом (как гейт) — своя LiveWorld/BridgeClient внутри скрипта, изоляция контура цела."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "registry_check.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"🧭 реестр упал (exit={r.returncode}):\n{out}"
    except subprocess.TimeoutExpired:
        return "🧭 реестр не уложился в 120с (Bridge/сеть тупит) — попробуй позже."
    except Exception as e:
        return f"🧭 реестр не запустился: {e}"


def _g_gate():
    """Прогон гейта 4.3 (тесты, ~7с). Зелёный read-only прогон — сам ничего не деплоит."""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "gate.py")], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "").strip() or (r.stderr or "").strip() or "(нет вывода)"
        return out if r.returncode == 0 else f"🔴 ГЕЙТ КРАСНЫЙ (exit={r.returncode}):\n{out}"
    except Exception as e:
        return f"гейт не запустился: {e}"


def _g_help():
    return ("🤖 Дев-бот — зелёные read-only команды:\n"
            "  health — здоровье системы\n"
            "  аудит — сводка открытых замечаний\n"
            "  боевой / writelog — последние боевые записи\n"
            "  cclog — свежие cc_log\n"
            "  ошибки — сводка splinter.log\n"
            "  мозг / brain — латентность Brain\n"
            "  просрочки — просрочки ТО парка (скан O3, топ-10)\n"
            "  статус / пульс — строка KB_PULSE (где проект сейчас)\n"
            "  сверься / реестр — сверка карта↔реальность (реестр знания, read-only)\n"
            "  гейт — прогон тестов 4.3 (~7с)\n"
            "  помощь\n"
            "\n🎻 Оркестратор (демон исполняет через headless Claude Code):\n"
            "  тз: <что сделать> — дев-ТЗ (до 45 мин): правки кода/тесты/гейт/push/restart splinter\n"
            "    сам (restart — через гейт + проверку старта); настоящее красное — спрошу кнопкой\n"
            "  задача: <что сделать> — быстрая задача (до 10 мин), та же дисциплина\n"
            "  декомпозируй: <крупное ТЗ> — план шагов → шаги отдельными задачами по одному → сводка\n"
            "  да N / нет N — ответ на запрос подтверждения красной зоны по задаче N\n"
            "  (в теме PC-дев те же «тз:»/«задача:»/«декомпозируй:» уходят ПК-театру: план на "
            "VPS, шаги — ПК-агент, полоса lane=pc)\n"
            "  (красную зону демон сам НЕ проходит — спросит кнопкой)\n"
            "Красное (запись в таблицы/деньги/деплой Bridge) сам НЕ делаю — нужно твоё «да».")


# allowlist: набор ключевых слов → зелёная функция (берёт bridge)
_ALLOWLIST = [
    (("health", "хелс", "здоров"), lambda b: _g_health()),
    (("аудит", "audit"), lambda b: _g_audit(b)),
    (("боев", "writelog", "write log"), lambda b: _g_writelog(b)),
    (("cclog", "cc_log", "cc лог", "cc-лог"), lambda b: _g_cclog(b)),
    (("ошибк", "errors", "splinter.log", "лог сплинтер"), lambda b: _g_errors()),
    (("мозг", "brain", "свеж"), lambda b: _g_brain(b)),
    (("просрочк", "overdue"), lambda b: _g_overdue(b)),
    (("статус", "пульс", "pulse", "status"), lambda b: _g_pulse(b)),
    (("сверься", "сверка", "сверить", "реестр", "registry"), lambda b: _g_registry()),
    (("гейт", "gate"), lambda b: _g_gate()),
    (("помощ", "help", "команд"), lambda b: _g_help()),
]


def _match(text):
    t = (text or "").strip().lower()
    for keys, fn in _ALLOWLIST:
        if any(k in t for k in keys):
            return fn
    return None


def _chunks(s, n=3500):
    s = s or ""
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]


# ===================== ТОЧКИ ВХОДА =====================
async def handle_command(msg, context, bridge) -> None:
    """Команда дев-боту в его темах: 328 (полоса vps) и PC-дев (полоса pc, env PC_DEV_TOPIC_ID).
    ТОЛЬКО от Филиппа; в 328 — префиксы + зелёное из allowlist; в PC-дев — ТОЛЬКО «тз:»/«задача:»
    (→ enqueue lane=pc) и ответы «да N»/«нет N». Вне-allowlist/красное → НЕ выполняет, просит «да».
    Зелёное гоняет как origin=agent (без билета): красная запись внутри → токен-замок 4.2."""
    tid = getattr(msg, "message_thread_id", None)
    pc_topic = pc_dev_topic()
    if tid == DEVBOT_TOPIC:
        lane = "vps"
    elif pc_topic and tid == pc_topic:
        lane = "pc"
    else:
        return   # не наша тема (напр. 205 = pc_agent на ПК) — НЕ реагируем вообще
    if not msg.from_user or msg.from_user.id != DEVBOT_USER:
        return   # чужой — игнор

    # 0) Ответ на запрос подтверждения «да N» / «нет N» — ПЕРВЫМ (специфичный паттерн).
    # Bridge-вызовы — через to_thread (фикс 02.07): event loop не встаёт, пока /exec тупит.
    appr = await asyncio.to_thread(_try_approval_reply, msg.text or "", bridge)
    if appr is not None:
        for chunk in _chunks(appr):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # 1) Задача оркестратору (префикс) — проверяем ПЕРЕД allowlist. enqueue_task не красная зона
    #    (служебный лист очереди), origin=human по умолчанию — гейт 4.2 не трогаем.
    enq = await asyncio.to_thread(_try_enqueue, msg.text or "", bridge, lane)
    if enq is not None:
        for chunk in _chunks(enq):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # Полоса pc: зелёный allowlist НЕ гоняем (он про VPS) — только подсказка формата.
    if lane == "pc":
        await context.bot.send_message(
            chat_id=msg.chat_id, message_thread_id=tid,
            text=("🤖 Тема PC-дев (lane=pc): «тз: <ТЗ>» или «задача: <что сделать>» — уйдёт "
                  "ПК-агенту; «декомпозируй: <крупное ТЗ>» — план на VPS, шаги ПК-агенту по "
                  "одному; «да N» / «нет N» — ответ на красный вопрос. "
                  "Зелёные VPS-команды (health/аудит/…) — в теме 328."))
        return

    # 2) Зелёная read-only команда из allowlist
    fn = _match(msg.text or "")
    if fn is None:
        await context.bot.send_message(
            chat_id=msg.chat_id, message_thread_id=tid,
            text=("🤖 Это не зелёная команда (или красное: запись/деплой). Сам НЕ выполняю — нужно твоё «да». "
                  "Зелёное: health / аудит / боевой / cclog / ошибки / мозг / просрочки / статус / сверься / гейт / помощь. "
                  "Дев-ТЗ: «тз: <что сделать>»."))
        return
    def _run_green():
        with bridge_client.agent_write(None):   # origin=agent, без билета → красная запись будет отклонена
            return fn(bridge)
    try:
        reply = await asyncio.to_thread(_run_green)   # фикс 02.07: не морозим loop на зелёной команде
    except Exception as e:
        reply = f"🤖 ошибка зелёной задачи: {type(e).__name__}: {e}"
    for chunk in _chunks(reply):
        await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)


async def morning_summary(context) -> None:
    """Утренняя авто-сводка в topic 328 (health + открытый аудит + латентность Brain). read-only, agent."""
    bridge = BRIDGE
    if bridge is None:
        log.warning("devbot.morning_summary: BRIDGE не выставлен")
        return
    def _collect():
        with bridge_client.agent_write(None):
            return "\n".join(["🌅 Утренняя сводка дев-бота", "", _g_health(), "",
                              _g_audit(bridge), "", _g_brain(bridge)])
    try:
        text = await asyncio.to_thread(_collect)   # фикс 02.07: сбор сводки не морозит loop
    except Exception as e:
        text = f"🌅 Утренняя сводка: ошибка сбора ({type(e).__name__}: {e})"
    for chunk in _chunks(text):
        await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=DEVBOT_TOPIC, text=chunk)
