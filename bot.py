"""
TurboBaby Manager Bot — главный entry-point.

Запуск:
    python bot.py

Что делает:
- Слушает сообщения в TG-группе "Turbo HQ"
- Принимает текст и голосовые
- Голосовые конвертирует в текст через Anthropic (Claude обрабатывает аудио напрямую)
  ИЛИ через OpenAI Whisper (если есть ключ — TODO)
- Отвечает через Claude API с доступом к Bridge для свежих данных
- Помнит историю чата в SQLite
- Каждое утро в 9:00 шлёт Daily Pulse в группу
"""

import os
import logging
import json
import asyncio
import tempfile
from datetime import time as dtime, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bridge_client import BridgeClient
from claude_client import ClaudeClient
from memory import Memory
from prompts import SYSTEM_PROMPT, daily_pulse_prompt
import splinter

# === Загружаем конфиг ===
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
USER_NAME = os.getenv("USER_NAME", "Филипп")
TZ_NAME = os.getenv("TIMEZONE", "Asia/Bangkok")
DAILY_HOUR = int(os.getenv("DAILY_PULSE_HOUR", "9"))
DAILY_MINUTE = int(os.getenv("DAILY_PULSE_MINUTE", "0"))

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Подавляем шум от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

log = logging.getLogger("turbobaby")


# === Инициализируем компоненты ===
bridge = BridgeClient()
memory = Memory()
claude = ClaudeClient(bridge=bridge, memory=memory)
from auditor import Auditor
auditor = Auditor(bridge=bridge, memory=memory, claude=claude)

# Подключаем аудитор к единой точке отправки Splinter (splinter._send):
# служебные двуязычные сообщения тоже прогоняются через check_response_text
# (журнально, отправку не глушит). Без этого вызова хук _send молчит.
splinter.set_auditor(auditor)
log.info("  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)")


# === HANDLERS ===

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start."""
    chat_id = update.effective_chat.id
    log.info(f"/start in chat {chat_id}")
    await update.message.reply_text(
        f"🚀 TurboBaby Manager Bot готов.\n\n"
        f"Я слушаю эту группу и помогаю с учётом текучки.\n"
        f"Пиши голосом или текстом — отвечу.\n\n"
        f"Chat ID этой группы: `{chat_id}`",
        parse_mode="Markdown"
    )


async def cmd_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pulse — ручной запрос Daily Pulse."""
    await update.message.reply_text("📊 Собираю сводку...")
    await send_daily_pulse(context.application, update.effective_chat.id)


async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /audit — отчёт надзора по запросу (за последние 7 дней)."""
    await update.message.reply_text("🔎 Проверяю работу бота...")
    try:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).isoformat()
        report = auditor.daily_report(since_iso=since)
    except Exception as e:
        report = f"🐀 Аудит: ошибка ({e})"
    for chunk in chunk_text(report, 4000):
        await update.message.reply_text(chunk)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ping — проверка живой ли Bridge."""
    result = bridge.ping()
    if result.get("ok"):
        await update.message.reply_text(
            f"✅ Bridge alive\n"
            f"Version: {result.get('version')}\n"
            f"Time: {result.get('time')}"
        )
    else:
        await update.message.reply_text(
            f"❌ Bridge error: {result.get('error')} — {result.get('message')}"
        )


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /rules — показывает активные правила в памяти."""
    rules = memory.active_rules()
    if not rules:
        await update.message.reply_text("Правил в памяти пока нет.")
        return
    text = "📚 Активные правила:\n\n"
    for r in rules[:20]:
        text += f"• {r['rule']}\n"
        if r.get('context'):
            text += f"  _{r['context']}_\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает chat_id текущего чата — работает в любой группе."""
    chat = update.effective_chat
    mode = splinter.GROUPS.get(chat.id, "— (не подключена к Splinter)")
    await update.message.reply_text(
        f"🆔 chat_id: {chat.id}\n"
        f"Название: {chat.title or '—'}\n"
        f"Тип: {chat.type}\n"
        f"Режим Splinter: {mode}"
    )


def _owner_addresses_bot(msg, context) -> bool:
    """Владелец (Филипп) ИЛИ Пым обращаются к Splinter: тег бота, ответ на его сообщение,
    ИЛИ бот сам недавно задал вопрос в этой теме и ждёт ответа (тег не нужен).
    Пым включена по правилу Филиппа: всегда реагировать на @Pleummmm."""
    u = msg.from_user
    allowed = splinter.OWNER_USERNAMES | splinter.PYM_USERNAMES
    if not u or not u.username or u.username.lower() not in allowed:
        return False
    r = msg.reply_to_message
    if r and r.from_user and context.bot and r.from_user.id == context.bot.id:
        return True
    t = (msg.text or "").lower()
    uname = ""
    try:
        uname = (context.bot.username or "").lower()
    except Exception:
        pass
    if (uname and ("@" + uname) in t) or ("turbobaby_manager_bot" in t):
        return True
    # Без тега: если бот сам задал вопрос в этой теме и ждёт ответа
    _tid = getattr(msg, "message_thread_id", None)
    if splinter.is_awaiting(msg.chat_id, _tid):
        return True
    return False


def _topic_label(chat_id, topic_id) -> str:
    """Читаемое имя темы для логов: 'тема 73 (NINJA 400 6334)'.
    Если тема не сопоставлена байку — просто 'тема 73'. В HQ/личке — 'HQ/личка'."""
    if topic_id is None:
        return "HQ/личка"
    try:
        bike = splinter.bike_from_topic(chat_id, topic_id)
    except Exception:
        bike = ""
    return f"тема {topic_id}" + (f" ({bike})" if bike else "")


async def _keep_typing(context, chat_id, topic_id, stop_event):
    """Фоново держит индикатор «печатает…» пока идёт обработка.
    Сам останавливается по stop_event (ответ готов / ошибка). Не зависает."""
    import asyncio
    while not stop_event.is_set():
        try:
            kwargs = {"chat_id": chat_id, "action": "typing"}
            if topic_id:
                kwargs["message_thread_id"] = topic_id
            await context.bot.send_chat_action(**kwargs)
        except Exception:
            pass  # индикатор не критичен — молча игнорируем сбои
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass  # 4 сек прошло — повторяем typing (Telegram гасит ~5 сек)


async def manager_reply(msg, context, context_note: str = "", bilingual: bool = False, force_bike: str = "", force_mileage=None, force_mileage_conf: str = ""):
    """Диалог через Claude-мозг (память, правила, инструменты). Работает в HQ, личке и
    в операционных группах когда к Splinter обращается владелец.
    bilingual=True — отвечать на двух языках и дублировать запрос (для групп с тайцами).
    force_bike — байк текущей темы (обслуживание): set_service принудительно его использует."""
    chat_id = msg.chat_id
    user_id = msg.from_user.id if msg.from_user else None
    user_name = (msg.from_user.first_name or USER_NAME) if msg.from_user else "User"
    text = msg.text
    _topic = getattr(msg, "message_thread_id", None)

    log.info(f"[{chat_id}] {user_name} ({_topic_label(chat_id, _topic)}) → мозг: {text[:100]}")
    memory.save_message(chat_id, user_id, user_name, "user", text, topic_id=_topic)

    ctx = memory.get_context_for_claude(chat_id, history_limit=12, topic_id=_topic)
    history = ctx["history"][:-1]
    rules = ctx["rules"]

    rules_block = ""
    if rules:
        rules_text = "\n".join(f"- {r['rule']}" for r in rules[:20])
        rules_block = f"\n\n## Правила из памяти (от Филиппа):\n{rules_text}"

    system = SYSTEM_PROMPT + rules_block
    if context_note:
        system += f"\n\n## Контекст сейчас:\n{context_note}"

    # Если Филипп отвечает на фото (или приложил фото) — подтягиваем его через vision,
    # чтобы мозг "видел" то же что и Филипп (иначе глохнет: "ты видел фото пробега?")
    photo_msg = None
    if msg.photo:
        photo_msg = msg
    elif msg.reply_to_message and msg.reply_to_message.photo:
        photo_msg = msg.reply_to_message
    if photo_msg is not None:
        try:
            ph = photo_msg.photo[-1]
            f = await context.bot.get_file(ph.file_id)
            buf = await f.download_as_bytearray()
            desc = claude.vision(
                "Опиши кратко что на фото: для байка — одометр/пробег (число км), уровень топлива, "
                "видимые повреждения, модель/номер. Для чека — сумма, валюта, продавец. "
                "Если виден одометр — обязательно укажи число. Коротко, по-русски.",
                bytes(buf), max_tokens=300,
            )
            system += f"\n\n## Фото, на которое смотрит Филипп:\n{desc}"
            log.info(f"  → мозг подтянул фото: {desc[:80]}")
        except Exception as e:
            log.warning(f"  → не смог подтянуть фото в мозг: {e}")

    if bilingual:
        system += (
            "\n\n## ФОРМАТ ОТВЕТА (обязательно):\n"
            "В этом чате есть тайские сотрудники. Отвечай ВСЕГДА на ДВУХ языках, тайский ПЕРВЫМ.\n"
            "Не используй эмодзи вместо слов (паспорт, доллар и т.п.) — пиши словами.\n"
            "Структура ответа строго такая:\n"
            "1) Сначала продублируй запрос собеседника:\n"
            "   🇹🇭 <запрос по-тайски>\n"
            "   🇷🇺 <запрос по-русски>\n"
            "2) Пустая строка.\n"
            "3) Затем ответ:\n"
            "   🇹🇭 <ответ по-тайски>\n"
            "   🇷🇺 <ответ по-русски>\n"
            "Без лишних преамбул. Тайский — естественный перевод носителя, не транслит."
        )

    # Фоновый индикатор «печатает…» на всё время работы мозга.
    # Сам гаснет когда ответ готов или при ошибке — не зависает.
    import asyncio
    import functools
    _stop_typing = asyncio.Event()
    _typing_task = asyncio.create_task(_keep_typing(context, chat_id, _topic, _stop_typing))
    try:
        # claude.ask синхронный и блокирующий — выносим в поток, чтобы event loop
        # параллельно слал индикатор «печатает» (иначе он бы завис на время запроса)
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None,
            functools.partial(
                claude.ask, user_message=text, system_prompt=system, history=history,
                force_bike=force_bike, force_mileage=force_mileage,
                force_mileage_conf=force_mileage_conf,
            ),
        )
    except Exception as e:
        log.exception("Claude error")
        _stop_typing.set()
        try:
            await _typing_task
        except Exception:
            pass
        await msg.reply_text(f"⚠️ Ошибка при обращении к Claude: {e}")
        return
    finally:
        if not _stop_typing.is_set():
            _stop_typing.set()
            try:
                await _typing_task
            except Exception:
                pass

    memory.save_message(chat_id, None, "Bot", "assistant", answer, topic_id=_topic)
    for chunk in chunk_text(answer, 4000):
        await msg.reply_text(chunk, parse_mode=None)

    # Окно «бот ждёт ответа без тега»:
    # пришедшее сообщение мы уже обработали → снимаем старый флаг,
    # затем если в НОВОМ ответе бот задаёт вопрос/просит подтверждение — ставим заново.
    splinter.clear_awaiting(chat_id, _topic)
    _ans_l = (answer or "").lower()
    _awaiting_markers = ("?", "верно", "подтверд", "закрепить", "открепить",
                         "ถูกไหม", "ยืนยัน", "ปักหมุดไหม", "напиши правильное")
    if any(m in _ans_l for m in _awaiting_markers):
        # awaiting только в ТЕМАХ байков (узкий контекст). В HQ/личке (тема None)
        # один общий поток — там не ловим ответ без тега, чтобы не встревать.
        if _topic is not None:
            splinter.mark_awaiting(chat_id, _topic)
            log.info(f"  → бот ждёт ответа в {_topic_label(chat_id, _topic)} (можно отвечать без тега 10 мин)")

    # Аудитор: проверяем каждое выполненное действие (факт vs правило).
    # Сам ничего не правит — пишет находки в журнал, критичное подсветит в HQ-отчёте.
    try:
        actions = getattr(claude, "last_actions", []) or []
        _grp = splinter.group_label(chat_id) if splinter.is_splinter_group(chat_id) else "HQ"
        for act in actions:
            res = auditor.check_action(
                tool=act.get("tool", ""), args=act.get("args", {}),
                claimed=act.get("claimed", ""), user_request=text,
                group=_grp, topic_id=_topic,
            )
            if res.get("verdict") not in ("ok", ""):
                log.warning(f"  🔎 АУДИТ: {res['verdict']} [{res.get('severity')}] {res.get('detail')}")
        # Проверка качества ответа: стиль, перевод, смешение языков
        rstyle = auditor.check_response_text(
            answer=answer, bilingual=bilingual, user_request=text,
            group=_grp, topic_id=_topic,
        )
        if rstyle.get("verdict") not in ("ok", ""):
            log.warning(f"  🔎 АУДИТ стиль: {rstyle.get('detail')}")
    except Exception as e:
        log.warning(f"auditor check error: {e}")
    pins = getattr(claude, "pending_pins", None) or []
    if pins:
        _tid = getattr(msg, "message_thread_id", None)
        for pin_text in pins:
            try:
                sent = await context.bot.send_message(
                    chat_id=chat_id, text=pin_text, message_thread_id=_tid
                )
                await context.bot.pin_chat_message(
                    chat_id=chat_id, message_id=sent.message_id, disable_notification=False
                )
                log.info(f"  → закреплено напоминание в теме {_tid}")
            except Exception as e:
                log.warning(f"  → не смог закрепить (нужны права админа боту?): {e}")
                await msg.reply_text(
                    "🐀 Не смог закрепить — нужны права админа с разрешением «Pin messages». "
                    "Дай боту права в настройках группы."
                )
        claude.pending_pins = []

    # Важное: закрепить + записать в лист важного с msg_id закрепа
    important = getattr(claude, "pending_important", None) or []
    if important:
        _tid = getattr(msg, "message_thread_id", None)
        _sender = ("@" + msg.from_user.username) if (msg.from_user and msg.from_user.username) else ""
        for item in important:
            try:
                sent = await context.bot.send_message(
                    chat_id=chat_id, text=item["pin_text"], message_thread_id=_tid
                )
                await context.bot.pin_chat_message(
                    chat_id=chat_id, message_id=sent.message_id, disable_notification=False
                )
                bridge.important_add(
                    chat_id=chat_id, topic_id=_tid or "",
                    group=splinter.group_label(chat_id),
                    kind=item["kind"], summary=item["summary"],
                    pinned_msg_id=sent.message_id, confirmed_by=_sender,
                )
                log.info(f"  → ВАЖНОЕ закреплено в теме {_tid}: {item['summary']}")
            except Exception as e:
                log.warning(f"  → не смог закрепить важное: {e}")
                await msg.reply_text("🐀 Не смог закрепить важное — нужны права админа «Pin messages».")
        claude.pending_important = []

    # Открепить закрытое важное
    unpin_rows = getattr(claude, "pending_unpin", None) or []
    if unpin_rows:
        try:
            lst = bridge.important_list(status="done").get("items", [])
            by_row = {it.get("_row"): it for it in lst}
            for row in unpin_rows:
                it = by_row.get(row)
                if it and it.get("pinned_msg_id"):
                    try:
                        await context.bot.unpin_chat_message(
                            chat_id=int(it.get("chat_id") or chat_id),
                            message_id=int(it["pinned_msg_id"]),
                        )
                        log.info(f"  → ВАЖНОЕ откреплено (row {row})")
                    except Exception as e:
                        log.warning(f"  → не смог открепить важное row {row}: {e}")
        except Exception as e:
            log.warning(f"  → ошибка при откреплении важного: {e}")
        claude.pending_unpin = []


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений."""
    msg = update.message
    if not msg or not msg.text:
        return

    chat_id = msg.chat_id

    # Операционные группы
    if splinter.is_splinter_group(chat_id):
        # Владелец обращается к Splinter напрямую (тег/ответ/ждём ответа) → диалог-мозг
        if _owner_addresses_bot(msg, context):
            wallet = splinter.group_label(chat_id)
            mode = splinter.GROUPS.get(chat_id)
            scope_map = {
                "money": (
                    f"Тема этой группы — НАЛИЧНАЯ касса «{wallet}». На вопросы про деньги/баланс/"
                    f"остаток отвечай ТОЛЬКО про наличные этого кошелька через get_wallet_balance "
                    f"(wallet='{wallet}'). НЕ используй финансы бизнеса (get_finance) и парк "
                    f"(get_fleet/get_clients) — это глобальное."
                ),
                "servicing": "Тема этой группы — обслуживание/ремонт байков. Отвечай узко по этому.",
                "delivery": "Тема этой группы — доставки (выдача/возврат/ход). Отвечай узко по этому.",
                "attendance": "Тема этой группы — отметки сотрудников и рабочее время. Отвечай узко по этому.",
            }
            scope = scope_map.get(mode, f"Тема группы — «{wallet}».")
            _spk = (msg.from_user.username or "").lower() if msg.from_user else ""
            speaker = "Пым (тайский менеджер, доверенная)" if _spk in splinter.PYM_USERNAMES else "владелец Филипп"
            note = (
                f"Ты — Splinter, бот-супервайзер TurboBaby. С тобой говорит {speaker}.\n"
                f"КОНТЕКСТ ДАННЫХ (узко по теме группы): {scope} "
                f"Глобальные бизнес-данные и финансы по всей компании Филипп получает ТОЛЬКО в Turbo HQ — "
                f"здесь их не выдавай, вежливо отсылай в HQ. Если вопрос про данные не из темы этой группы — уточни, не гадай.\n"
                f"ОБУЧЕНИЕ (доступно ВСЕГДА, в любой группе, по любой теме): если Филипп даёт новое правило, "
                f"вводную, поправку или говорит «запомни/учти» — ВСЕГДА принимай и сохраняй через remember_rule "
                f"(правила глобальные) или save_note, и подтверди. Узкий контекст данных НЕ должен мешать обучению."
            )
            # В обслуживании подмешиваем разбор недавних фото (резина/пробег/повреждения),
            # чтобы на "проверь фото резины/пробега" мозг видел всю недавнюю пачку, а не одно фото
            _bike_topic = ""
            if mode == "servicing":
                _tid = getattr(msg, "message_thread_id", None)
                # имя байка из названия темы (по договорённости Филиппа)
                splinter._remember_topic_name(chat_id, _tid, msg)
                _bike_topic = splinter.bike_from_topic(chat_id, _tid)
                if _bike_topic:
                    note += (
                        f"\n\n## БАЙК ЭТОЙ ТЕМЫ: {_bike_topic}\n"
                        f"КРИТИЧНО: все данные (пробег, ТО, set_service) относятся ТОЛЬКО к этому байку — он берётся из НАЗВАНИЯ ТЕМЫ. "
                        f"НЕ бери байк из истории переписки или прошлых сообщений — только из названия текущей темы. "
                        f"Если в истории обсуждался другой байк (например в прошлой теме) — ИГНОРИРУЙ, здесь работаем только с {_bike_topic}.\n"
                        f"current_km (текущий пробег) бери ТОЛЬКО из фото одометра ЭТОЙ темы или из текста ЭТОЙ темы. "
                        f"НЕ подставляй пробег из истории/прошлых байков. Если в этой теме пробега нет — не указывай current_km вообще."
                    )
                else:
                    note += (
                        f"\n\n## БАЙК ЭТОЙ ТЕМЫ: неизвестен\n"
                        f"КРИТИЧНО: ты НЕ знаешь название этой темы (= какой байк). НЕ угадывай байк из истории переписки. "
                        f"Если нужно записать ТО/пробег — сначала спроси у Филиппа какой это байк, не подставляй из памяти."
                    )
                photos_sum = splinter.recent_photos_summary(chat_id, topic_id=_tid)
                if photos_sum:
                    note += (
                        f"\n\n## {photos_sum}\n"
                        f"Это фото ТОЛЬКО из текущей темы (этого байка). НЕ бери пробег/данные из других тем.\n"
                        f"Если Филипп просит проверить фото (резину, пробег, состояние) — опирайся на этот разбор. "
                        f"Если пробег помечен 'уверенность low' — предупреди что цифра неточная, попроси переснять одометр крупно. "
                        f"Если по какой-то детали фото нет в списке — так и скажи, не выдумывай."
                    )
                # Открытое важное этой темы (для close_important и чтобы не дублировать)
                try:
                    _imp = bridge.important_list(status="open").get("items", [])
                    _imp_here = [it for it in _imp if str(it.get("topic_id")) == str(_tid)]
                    if _imp_here:
                        lines = "\n".join(f"- row {it.get('_row')}: {it.get('summary')} ({it.get('kind')})" for it in _imp_here)
                        note += (
                            f"\n\n## ОТКРЫТОЕ ВАЖНОЕ в этой теме:\n{lines}\n"
                            f"Если сообщение говорит что это РЕШЕНО (сделали/заменили/починили/готово) — "
                            f"спроси подтверждение ('решено? @Pleummmm подтверди, открепить?'), "
                            f"и ТОЛЬКО после подтверждения вызови close_important с нужным row."
                        )
                except Exception:
                    pass
                # Инструкция по надзору за важным
                note += (
                    f"\n\n## НАДЗОР ЗА ВАЖНЫМ\n"
                    f"Если в сообщении есть признак ВАЖНОГО (ДТП/авария, серьёзный ремонт, просрочка ТО, потеря ключа, "
                    f"течь масла/жидкости, проблема с тормозами, байк не заводится) И этого ещё нет в списке выше — "
                    f"НЕ крепи сразу. Сначала СПРОСИ в чате: 'Это выглядит важным: <суть>. Закрепить и напоминать? @Pleummmm подтверди'. "
                    f"ТОЛЬКО после ответа 'да' от Пыма/владельца вызови flag_important. Напоминание идёт раз в 3 дня автоматически."
                )
            _force_mileage = None
            _force_mileage_conf = ""
            if mode == "servicing":
                _mil = splinter.last_mileage_in_topic(chat_id, getattr(msg, "message_thread_id", None))
                if _mil:
                    _force_mileage, _force_mileage_conf = _mil
            await manager_reply(msg, context, context_note=note, bilingual=True,
                                force_bike=(_bike_topic if mode == "servicing" else ""),
                                force_mileage=_force_mileage,
                                force_mileage_conf=_force_mileage_conf)
            return
        # Иначе — обычный учёт (Splinter-бухгалтер)
        await splinter.handle(update, context, bridge, claude)
        return

    # Чужие группы — бот молчит (отвечает только в HQ и в личке)
    if msg.chat.type in ("group", "supergroup") and chat_id != GROUP_CHAT_ID:
        return

    # HQ / личка — полный диалог
    await manager_reply(msg, context)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений через Claude (он умеет принимать аудио)."""
    msg = update.message
    if not msg or not msg.voice:
        return

    chat_id = msg.chat_id
    user_id = msg.from_user.id if msg.from_user else None
    user_name = (msg.from_user.first_name or USER_NAME) if msg.from_user else "User"

    log.info(f"[{chat_id}] {user_name}: <voice {msg.voice.duration}s>")

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Скачиваем файл
    try:
        voice_file = await msg.voice.get_file()
        voice_path = os.path.join(tempfile.gettempdir(), f"voice_{msg.message_id}.ogg")
        await voice_file.download_to_drive(voice_path)
    except Exception as e:
        log.exception("Voice download error")
        await msg.reply_text(f"⚠️ Не удалось скачать голосовое: {e}")
        return

    # Транскрибируем через OpenAI Whisper
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        with open(voice_path, "rb") as f:
            transcription = oai.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ru",
            )
        transcribed = transcription.text.strip()
        log.info(f"Transcribed: {transcribed[:200]}")
    except Exception as e:
        log.exception("Transcription error")
        await msg.reply_text(
            f"⚠️ Не удалось транскрибировать голос: {e}\n\n"
            f"Tip: попробуй написать текстом."
        )
        return
    finally:
        try:
            os.remove(voice_path)
        except:
            pass

    if not transcribed:
        await msg.reply_text("⚠️ Не смог распознать голос. Попробуй ещё раз или напиши текстом.")
        return

    # Показываем транскрипцию пользователю
    await msg.reply_text(f"🎙 _{transcribed}_", parse_mode="Markdown")

    # Сохраняем в память как пользовательское сообщение
    memory.save_message(chat_id, user_id, user_name, "user", transcribed, is_voice=True)

    # Обрабатываем как обычный текст
    ctx = memory.get_context_for_claude(chat_id, history_limit=12)
    history = ctx["history"][:-1]
    rules = ctx["rules"]

    rules_block = ""
    if rules:
        rules_text = "\n".join(f"- {r['rule']}" for r in rules[:20])
        rules_block = f"\n\n## Правила из памяти (от Филиппа):\n{rules_text}"

    system = SYSTEM_PROMPT + rules_block

    try:
        answer = claude.ask(
            user_message=transcribed,
            system_prompt=system,
            history=history,
        )
    except Exception as e:
        log.exception("Claude error after voice")
        await msg.reply_text(f"⚠️ Ошибка при обращении к Claude: {e}")
        return

    memory.save_message(chat_id, None, "Bot", "assistant", answer)

    for chunk in chunk_text(answer, 4000):
        await msg.reply_text(chunk, parse_mode=None)


# === DAILY PULSE ===

async def send_daily_pulse(app: Application, chat_id: int = None):
    """Отправляет утреннюю сводку в группу."""
    chat_id = chat_id or GROUP_CHAT_ID
    if not chat_id:
        log.warning("GROUP_CHAT_ID не задан — пропускаем daily pulse")
        return

    log.info(f"Sending daily pulse to {chat_id}")

    pulse = bridge.daily_pulse()
    if not pulse.get("ok"):
        await app.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Не удалось получить сводку: {pulse.get('error')}"
        )
        return

    # Генерируем красивую сводку через Claude
    prompt = daily_pulse_prompt(json.dumps(pulse["data"], ensure_ascii=False, indent=2))

    try:
        answer = claude.ask(
            user_message=prompt,
            system_prompt=SYSTEM_PROMPT,
            history=[],
        )
    except Exception as e:
        log.exception("Pulse generation error")
        await app.bot.send_message(chat_id=chat_id, text=f"⚠️ Ошибка генерации сводки: {e}")
        return

    for chunk in chunk_text(answer, 4000):
        await app.bot.send_message(chat_id=chat_id, text=chunk)


async def scheduled_daily_pulse(context: ContextTypes.DEFAULT_TYPE):
    """Запускается по расписанию JobQueue."""
    await send_daily_pulse(context.application)


async def scheduled_audit_report(context: ContextTypes.DEFAULT_TYPE):
    """Суточная сводка аудитора в HQ: расхождения требование→результат, галлюцинации."""
    if not GROUP_CHAT_ID:
        return
    try:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=1)).isoformat()
        report = auditor.daily_report(since_iso=since)
        await context.application.bot.send_message(chat_id=GROUP_CHAT_ID, text=report)
        log.info("  → аудит-отчёт отправлен в HQ")
    except Exception as e:
        log.warning(f"audit report error: {e}")


async def scheduled_important_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Раз в сутки: повторяет закреп важного, которому пора (>=3 дней)."""
    try:
        due = bridge.important_due(days=3).get("items", [])
    except Exception as e:
        log.warning(f"important_due error: {e}")
        return
    for it in due:
        try:
            chat_id = int(it.get("chat_id"))
            topic_id = it.get("topic_id")
            text = f"⚠️ Напоминание / เตือนความจำ:\n{it.get('summary')}\n(не закрыто / ยังไม่เสร็จ)"
            kwargs = {"chat_id": chat_id, "text": text}
            if topic_id:
                kwargs["message_thread_id"] = int(topic_id)
            sent = await context.application.bot.send_message(**kwargs)
            try:
                await context.application.bot.pin_chat_message(
                    chat_id=chat_id, message_id=sent.message_id, disable_notification=True
                )
            except Exception:
                pass
            bridge.important_touch(row=it.get("_row"), pinned_msg_id=sent.message_id)
            log.info(f"  → напоминание о важном (row {it.get('_row')}): {it.get('summary')}")
        except Exception as e:
            log.warning(f"important reminder error row {it.get('_row')}: {e}")


# === UTILS ===

def chunk_text(text: str, max_len: int = 4000):
    """Разбивает длинный текст на куски для Telegram."""
    if len(text) <= max_len:
        yield text
        return
    lines = text.split("\n")
    buf = ""
    for line in lines:
        if len(buf) + len(line) + 1 > max_len:
            if buf:
                yield buf
            buf = line
        else:
            buf = buf + "\n" + line if buf else line
    if buf:
        yield buf


# === MAIN ===

async def on_startup(app: Application):
    """Запускается один раз при старте."""
    log.info("=" * 60)
    log.info("TurboBaby Manager Bot — STARTING")
    log.info(f"  Group chat ID: {GROUP_CHAT_ID}")
    log.info(f"  Timezone: {TZ_NAME}")
    log.info(f"  Daily pulse at: {DAILY_HOUR:02d}:{DAILY_MINUTE:02d}")

    # Проверяем Bridge
    ping = bridge.ping()
    if ping.get("ok"):
        log.info(f"  Bridge: ✅ alive (v{ping.get('version')})")
    else:
        log.warning(f"  Bridge: ⚠️ {ping.get('error')}")

    # Шлём приветствие в группу
    if GROUP_CHAT_ID:
        try:
            await app.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=(
                    f"🤖 TurboBaby Manager Bot запущен.\n\n"
                    f"Команды:\n"
                    f"/pulse — утренняя сводка\n"
                    f"/ping — проверить Bridge\n"
                    f"/rules — мои правила в памяти\n\n"
                    f"Или просто пиши голосом/текстом — я разберусь."
                )
            )
        except Exception as e:
            log.error(f"Failed to send greeting: {e}")

    log.info("=" * 60)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фото в операционных группах → Splinter (чеки, фото байков).
    Если владелец приложил подпись с обращением к боту — отдаём мозгу (он подтянет фото через vision)."""
    msg = update.message
    if not msg or not msg.photo:
        return
    if not splinter.is_splinter_group(msg.chat_id):
        return
    # Владелец прислал фото с подписью-обращением к боту → диалог-мозг
    cap = (msg.caption or "")
    _tid = getattr(msg, "message_thread_id", None)
    _trusted = splinter._is_trusted(msg)
    # Фото = обращение к боту, если:
    #  - подпись содержит тег/ответ на бота, ИЛИ
    #  - бот ждёт ответа в этой теме (только что задал вопрос), ИЛИ
    #  - фото БЕЗ подписи от владельца/Пыма в теме обслуживания (очевидно «вот пробег/чек»)
    _addressed = (
        _owner_addresses_bot_caption(msg, context, cap)
        or (_trusted and splinter.is_awaiting(msg.chat_id, _tid))
        or (_trusted and not cap and splinter.GROUPS.get(msg.chat_id) == "servicing")
    )
    if _addressed:
        # У фото нет msg.text — подставим подпись (или нейтральный запрос) чтобы мозг прочитал
        msg.text = cap or "Фото в теме — проверь, что на нём (пробег/чек/состояние)."
        await manager_reply(msg, context, context_note="Владелец/Пым прислал фото.", bilingual=True)
        return
    await splinter.handle(update, context, bridge, claude)


def _owner_addresses_bot_caption(msg, context, cap: str) -> bool:
    """Как _owner_addresses_bot, но для подписи к фото. Владелец + Пым."""
    u = msg.from_user
    allowed = splinter.OWNER_USERNAMES | splinter.PYM_USERNAMES
    if not u or not u.username or u.username.lower() not in allowed:
        return False
    r = msg.reply_to_message
    if r and r.from_user and context.bot and r.from_user.id == context.bot.id:
        return True
    t = cap.lower()
    uname = ""
    try:
        uname = (context.bot.username or "").lower()
    except Exception:
        pass
    return bool((uname and ("@" + uname) in t) or ("turbobaby_manager_bot" in t))


def main():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN не задан в .env")
        return
    if not GROUP_CHAT_ID:
        log.warning("GROUP_CHAT_ID не задан — Daily Pulse не будет работать")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pulse", cmd_pulse))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("chatid", cmd_chatid))

    # Сообщения
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Расписание Daily Pulse
    if GROUP_CHAT_ID:
        tz = ZoneInfo(TZ_NAME)
        app.job_queue.run_daily(
            scheduled_daily_pulse,
            time=dtime(hour=DAILY_HOUR, minute=DAILY_MINUTE, tzinfo=tz),
            name="daily_pulse",
        )
        log.info(f"Scheduled daily pulse at {DAILY_HOUR:02d}:{DAILY_MINUTE:02d} {TZ_NAME}")

        # Напоминания о важном — раз в сутки в 10:00 (проверяет что прошло >=3 дней)
        app.job_queue.run_daily(
            scheduled_important_reminders,
            time=dtime(hour=10, minute=0, tzinfo=tz),
            name="important_reminders",
        )
        log.info("Scheduled important reminders at 10:00 (every 3 days per item)")

        # Аудит-отчёт в HQ — раз в сутки в 09:30 (после Daily Pulse)
        app.job_queue.run_daily(
            scheduled_audit_report,
            time=dtime(hour=9, minute=30, tzinfo=tz),
            name="audit_report",
        )
        log.info("Scheduled audit report at 09:30")

    log.info("Bot polling started. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
