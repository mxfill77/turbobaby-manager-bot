"""Дев-бот (полу-оркестратор), пункт 5 лестницы — первый заход.

ТОЛЬКО зелёные read-only задачи по ЖЁСТКОМУ allowlist (БЕЗ LLM, детерминированно). Живёт в HQ
topic 328 (Splinter там молчит). 205 = pc_agent/userbot на ПК — НЕ наша тема. Команды ТОЛЬКО от Филиппа (504608015).
origin=agent → ЛЮБАЯ попытка красной записи ловится токен-замком 4.2 (rejected+пуш), деплой —
тесты-гейтом 4.3. Красное/вне-allowlist → НЕ выполняет, просит «да». Не новый процесс — на bot.py.
"""
import os
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
