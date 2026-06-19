"""Дев-бот (полу-оркестратор), пункт 5 лестницы — первый заход.

ТОЛЬКО зелёные read-only задачи по ЖЁСТКОМУ allowlist (БЕЗ LLM, детерминированно). Живёт в HQ
topic 328 (Splinter там молчит). 205 = pc_agent/userbot на ПК — НЕ наша тема. Команды ТОЛЬКО от Филиппа (504608015).
origin=agent → ЛЮБАЯ попытка красной записи ловится токен-замком 4.2 (rejected+пуш), деплой —
тесты-гейтом 4.3. Красное/вне-allowlist → НЕ выполняет, просит «да». Не новый процесс — на bot.py.
"""
import os
import re
import time
import logging
import subprocess
from collections import Counter

import bridge_client

log = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "bin", "python3")

DEVBOT_USER = 504608015                 # Филипп — единственный, кто командует дев-ботом
HQ_CHAT_ID = -1003853365891
DEVBOT_TOPIC = 328                      # тема dev-bot (VPS). 205 = pc_agent/userbot (ПК) — НЕ наша
CC_LOG_ID = "1464zaINaLnOwXMsHNaEyy-4FpuQCVTYF"

BRIDGE = None   # выставляется из bot.py при старте (devbot.BRIDGE = bridge)

# === ОРКЕСТРАТОР (ступень1 заход2б-1): дев-бот ↔ очередь ===
# Префикс в 328 → кладём задачу в очередь оркестратора; фоновый job приносит результат обратно.
QUEUE_FROM = "Filipp-328"               # метка источника задач из ТГ (фильтр для отчёта)
_TASK_PREFIXES = ("задача:", "оркестратор:", "task:")
_reported = set()                       # id задач, уже отрапортованных (done/failed; дедуп, память процесса)
_report_seeded = False                  # seed-on-start: не спамим историей done/failed при рестарте
_asked = set()                          # id задач needs_approval, по которым УЖЕ задан вопрос (дедуп)

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


def _try_enqueue(text, bridge):
    """Если текст начинается с префикса задачи — кладём в очередь оркестратора. Иначе None.
    Проверяется ДО allowlist (иначе ключевые слова в тексте задачи перехватили бы зелёную команду)."""
    t = (text or "").strip()
    low = t.lower()
    for p in _TASK_PREFIXES:
        if low.startswith(p):
            task_text = t[len(p):].strip()
            if not task_text:
                return "🤖 Пустая задача. Формат: «задача: <что сделать>»."
            r = bridge.enqueue_task(QUEUE_FROM, task_text)
            if r.get("ok"):
                return (f"✅ Задача {r.get('id')} поставлена в очередь — демон возьмёт её (опрос ~60с). "
                        f"Принесу результат сюда, когда будет done/failed.")
            return f"🤖 Не удалось поставить задачу в очередь: {r.get('error')}"
    return None


async def report_results(context) -> None:
    """Фоновый job (раз в ~45с): приносит в 328 результат задач from=Filipp-328, ставших done/failed.
    Дедуп: _reported (память процесса). Seed-on-start: первый прогон лишь помечает уже-завершённые
    как отрапортованные, чтобы при рестарте не присылать всю историю заново."""
    global _report_seeded
    bridge = BRIDGE
    if bridge is None:
        return
    finished = []
    try:
        for st in ("done", "failed"):
            r = bridge.get_pending(st)
            if not r.get("ok"):
                continue
            for it in r.get("items", []):
                if str(it.get("from")) == QUEUE_FROM:
                    finished.append((st, it))
    except Exception as e:
        log.warning("devbot.report_results: опрос очереди упал (%s)", e)
        return
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
        for chunk in _chunks(head):
            try:
                await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=DEVBOT_TOPIC, text=chunk)
            except Exception as e:
                log.warning("devbot.report_results: отправка результата задачи %s упала (%s)", qid, e)

    # needs_approval (заход 2б-2): задача упёрлась в красную зону — спрашиваем «да N»/«нет N».
    # БЕЗ seed (незакрытый вопрос после рестарта стоит переспросить); дедуп = _asked в памяти процесса.
    try:
        na = bridge.get_pending("needs_approval")
    except Exception as e:
        log.warning("devbot.report_results: опрос needs_approval упал (%s)", e)
        return
    if not na.get("ok"):
        return
    pend = sorted((it for it in na.get("items", []) if str(it.get("from")) == QUEUE_FROM),
                  key=lambda x: int(x.get("id") or 0))
    for it in pend:
        qid = it.get("id")
        if qid in _asked:
            continue
        _asked.add(qid)
        what = it.get("result") or "(не уточнено)"
        q = (f"⚠️ Задача {qid} требует подтверждения красной зоны:\n\n{what}\n\n"
             f"Подтвердить? Ответь «да {qid}» (разрешить) или «нет {qid}» (отклонить).")
        for chunk in _chunks(q):
            try:
                await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=DEVBOT_TOPIC, text=chunk)
            except Exception as e:
                log.warning("devbot.report_results: вопрос по задаче %s не ушёл (%s)", qid, e)


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


def _g_help():
    return ("🤖 Дев-бот — зелёные read-only команды:\n"
            "  health — здоровье системы\n"
            "  аудит — сводка открытых замечаний\n"
            "  боевой / writelog — последние боевые записи\n"
            "  cclog — свежие cc_log\n"
            "  ошибки — сводка splinter.log\n"
            "  мозг / brain — латентность Brain\n"
            "  помощь\n"
            "\n🎻 Оркестратор (демон исполняет через claude -p):\n"
            "  задача: <что сделать> — поставить задачу в очередь; результат принесу сюда\n"
            "  да N / нет N — ответ на запрос подтверждения красной зоны по задаче N\n"
            "  (красную зону демон сам НЕ проходит — спросит «да N»)\n"
            "Красное (запись/деплой) сам НЕ делаю — нужно твоё «да».")


# allowlist: набор ключевых слов → зелёная функция (берёт bridge)
_ALLOWLIST = [
    (("health", "хелс", "здоров"), lambda b: _g_health()),
    (("аудит", "audit"), lambda b: _g_audit(b)),
    (("боев", "writelog", "write log"), lambda b: _g_writelog(b)),
    (("cclog", "cc_log", "cc лог", "cc-лог"), lambda b: _g_cclog(b)),
    (("ошибк", "errors", "splinter.log", "лог сплинтер"), lambda b: _g_errors()),
    (("мозг", "brain", "свеж"), lambda b: _g_brain(b)),
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
    """Команда дев-боту в его теме (328). ТОЛЬКО от Филиппа; только зелёное из allowlist.
    Вне-allowlist/красное → НЕ выполняет, просит «да». Зелёное гоняет как origin=agent (без билета):
    любая попытка красной записи внутри → ловится токен-замком 4.2."""
    if getattr(msg, "message_thread_id", None) != DEVBOT_TOPIC:
        return   # не тема dev-bot (напр. 205 = pc_agent на ПК) — НЕ реагируем вообще
    if not msg.from_user or msg.from_user.id != DEVBOT_USER:
        return   # чужой — игнор
    tid = getattr(msg, "message_thread_id", None)

    # 0) Ответ на запрос подтверждения «да N» / «нет N» — ПЕРВЫМ (специфичный паттерн).
    appr = _try_approval_reply(msg.text or "", bridge)
    if appr is not None:
        for chunk in _chunks(appr):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # 1) Задача оркестратору (префикс) — проверяем ПЕРЕД allowlist. enqueue_task не красная зона
    #    (служебный лист очереди), origin=human по умолчанию — гейт 4.2 не трогаем.
    enq = _try_enqueue(msg.text or "", bridge)
    if enq is not None:
        for chunk in _chunks(enq):
            await context.bot.send_message(chat_id=msg.chat_id, message_thread_id=tid, text=chunk)
        return

    # 2) Зелёная read-only команда из allowlist
    fn = _match(msg.text or "")
    if fn is None:
        await context.bot.send_message(
            chat_id=msg.chat_id, message_thread_id=tid,
            text=("🤖 Это не зелёная команда (или красное: запись/деплой). Сам НЕ выполняю — нужно твоё «да». "
                  "Зелёное: health / аудит / боевой / cclog / ошибки / мозг / помощь."))
        return
    try:
        with bridge_client.agent_write(None):   # origin=agent, без билета → красная запись будет отклонена
            reply = fn(bridge)
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
    try:
        with bridge_client.agent_write(None):
            parts = ["🌅 Утренняя сводка дев-бота", "", _g_health(), "",
                     _g_audit(bridge), "", _g_brain(bridge)]
        text = "\n".join(parts)
    except Exception as e:
        text = f"🌅 Утренняя сводка: ошибка сбора ({type(e).__name__}: {e})"
    for chunk in _chunks(text):
        await context.bot.send_message(chat_id=HQ_CHAT_ID, message_thread_id=DEVBOT_TOPIC, text=chunk)
