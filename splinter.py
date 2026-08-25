"""
🐀 Splinter — бот-супервайзер TurboBaby.

Слушает операционные группы и работает по-разному в зависимости от chat_id:
  - money      : Money Cashflow + Самоорганизация — считает деньги, сверяет с Пымом
  - servicing  : Обслуживание байков — события (вернулся/сдан/ремонт), фото, топливо/пробег
  - delivery   : Delivery cooperation — ход доставок
  - attendance : Отметка сотрудников — опоздания (рабочий день 10:00–19:00)

ПРИНЦИП:
  - Доверие к Пыму. Не сходится → сначала уточняем у Пыма (тег @Pleummmm), не у Филиппа.
  - Splinter делает запись, Пым проверяет. Копим записи → периодически зовём проверить.
  - Splinter НИКОГДА не двигает деньги. Только учёт, сверка, напоминания.
  - Общается только с Пымом; остальных читает для учёта.
"""

import os
import json
import base64
import html
import logging
import bridge_client   # токен-замок 4.2 (agent_write) для красной записи брони в CRM + паспорт B2
import wallet_cache    # §касса: персистентный fallback-кэш баланса (переживает рестарт splinter)
import scan_result     # контракт читателя живого текста: пара «осмотрено/разобрано» + исход
import fleet_cell      # контракт клетки Лист1: значение / пусто / не-число / нечитаемо
import card_deadline   # общий дедлайн сборки карточки «Инфо» + слова о непрочитанном
import write_fact      # синк зеркала по ПЕРЕЧИТАННОМУ факту, а не по флагу расписки
import balance_fact    # §касса: свежий баланс / «не сверено» + дата / нечего сказать; факт проводки
import service_receipt # квитанция ТО: ОБЕ половины (тайская+русская) из ОДНОГО исхода записи
import odo_ceiling     # верхняя граница пробега при записи ТО: обе двери под одним гейтом
import undo_last       # отмена последней записи ТО: объект из расписки моста → карточка владельцу
import work_name       # история обслуживания: слова механика — человеку, ярлык вида — расчётам
import card_works      # «в работе»: ОДИН список на обе половины; доказанно записанное уходит
import works_ledger    # сторож партии: принято N · записано M, каждая не легшая позиция — поимённо
import service_debt    # долг принятой работы: строка ДО показа кнопки; гаснет только доказанным
import hint_dedup      # замок повторных подсказок: байк × вид × СОСТОЯНИЕ, одна дверь на 14 мест
import odo_fresh       # срок годности подтверждённого пробега: не спрашиваем число, которое знаем
import odo_lower
import batch_odo     # работы на другом пробеге: третий исход карточки подтверждения работ       # понижение пробега: расхождение ЧИСЛОМ + причина + письменное пояснение
import reply_floor     # пол ответа: бот не молчит и не отказывает глухо (правила владельца 23.08)
import contextvars as _ctxvars   # свидетель «мы уже говорили» — по задаче, а не глобально
# §12: типизированный upstream-down (громкий провал API-пути). В проде импортируется РЕАЛЬНЫЙ класс
# из claude_client (тот же, что бросает quick()/vision()) → except его ловит. Часть тестов подменяет
# claude_client урезанным стабом без этого имени — тогда безопасный локальный фоллбэк (money-raise
# путь такие стаб-тесты не гоняют; денежные тесты берут РЕАЛЬНЫЙ claude_client).
try:
    from claude_client import SplinterLLMError
except Exception:                                # стаб claude_client в тестах без SplinterLLMError
    class SplinterLLMError(Exception):
        pass
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger("splinter")

# === Аудитор (надзор за качеством исходящих сообщений) ===
# Подключается из bot.py через set_auditor(). Если не задан — отправка идёт без проверки.
_auditor = None


def set_auditor(auditor):
    """Передать ссылку на Auditor из bot.py (один раз при старте)."""
    global _auditor
    _auditor = auditor


_SEP = "➖➖➖➖➖➖➖➖"   # единый разделитель между 🇹🇭 и 🇷🇺 блоками


def _with_separator(text):
    """Вставить разделитель-линию между 🇹🇭 и 🇷🇺 блоками двуязычного сообщения. ИДЕМПОТЕНТНО:
    если перед 🇷🇺 уже линия — не трогаем; если пустая строка — заменяем её на линию (единообразие).
    Одноязычные (нет одного из флагов) — не трогаем."""
    if "🇹🇭" not in text or "🇷🇺" not in text:
        return text
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.lstrip().startswith("🇷🇺"):
            prev = lines[i - 1].strip() if i > 0 else None
            if prev == _SEP:
                return text                  # уже с линией
            if prev == "":
                lines[i - 1] = _SEP          # пустую строку (денежные) → линия, для единообразия
            else:
                lines.insert(i, _SEP)         # слипшиеся блоки → вставить линию
            return "\n".join(lines)
    return text


#: Сколько раз мы заговорили в ЭТОЙ задаче обработки обновления. Читается сразу после дверей
#: разбора: не выросло — бот промолчал, а молчание владелец запретил как исход (23.08).
_SPOKE = _ctxvars.ContextVar("splinter_spoke", default=0)


def _never_silent_on():
    """Ручка отката пола ответа. `NEVER_SILENT=0` → ветка мертва ДО сбора фактов."""
    return str(_os_env("NEVER_SILENT", "1")).strip() not in ("0", "", "нет", "no", "off")


def _os_env(name, default=""):
    """Значение окружения без импорта наверх (os уже импортирован модулем)."""
    return os.getenv(name, default)


async def _send(context, *, chat_id, text, message_thread_id=None, bilingual=True, group="", reply_markup=None, parse_mode=None):
    """Единая точка отправки сообщений Splinter в группы.
    Перед отправкой прогоняет текст через auditor.check_response_text — тот
    детерминированно ловит смешение RU/TH и пишет находки в журнал аудита.
    Сообщение отправляется в любом случае (вариант А: только журналируем, не глушим),
    чтобы тайцы не остались без уведомления из-за ложного срабатывания.
    """
    if bilingual:
        text = _with_separator(text)   # единый разделитель 🇹🇭/🇷🇺 централизованно
    if _auditor is not None:
        try:
            r = _auditor.check_response_text(
                answer=text, bilingual=bilingual, user_request="",
                group=group, topic_id=message_thread_id,
            )
            if r.get("verdict") not in ("ok", ""):
                log.warning(f"  🔎 АУДИТ Splinter [{r.get('verdict')}] {r.get('detail')}")
        except Exception as e:
            log.warning(f"  → аудит исходящего не сработал: {e}")
    kw = {"chat_id": chat_id, "text": text}
    if message_thread_id is not None:
        kw["message_thread_id"] = message_thread_id
    if reply_markup is not None:
        kw["reply_markup"] = reply_markup
    if parse_mode is not None:
        kw["parse_mode"] = parse_mode
    sent = await context.bot.send_message(**kw)
    # СВИДЕТЕЛЬ РЕЧИ (правило владельца 23.08 «никогда не молчать»). `_send` — ЕДИНСТВЕННАЯ дверь
    # к `send_message` во всём модуле, поэтому счётчик здесь и есть полный ответ на вопрос
    # «сказали ли мы хоть слово». Отметка ставится ПОСЛЕ удачной отправки: упавшая отправка речью
    # не является. ContextVar, а не поле/глобаль: PTB даёт каждому обновлению свою задачу со СВОЕЙ
    # копией контекста, и ответ соседнего сообщения не имеет права сойти за наш (глобаль дала бы
    # ложное «мы говорили», то есть ровно запрещённое молчание).
    try:
        _SPOKE.set(_SPOKE.get() + 1)
    except Exception:      # свидетель не имеет права уронить отправку
        pass
    return sent


async def _send_retry(context, *, attempts=3, delay=1.5, **kw):
    """Отправка с ретраем на СЕТЕВОЙ таймаут — для ПОДТВЕРЖДЕНИЙ (запись уже прошла и идемпотентна по
    msg_id). Ретраит ТОЛЬКО доставку сообщения, транзакцию НЕ трогает (нет задвоения). Все попытки
    упали → лог, не бросает (баланс уже верен). Причина: инцидент 09:43 — add_transaction ok, но
    _send подтверждения упал httpx.ConnectTimeout → Пым не увидел."""
    import asyncio
    from telegram.error import TimedOut, NetworkError, RetryAfter
    last = None
    for i in range(attempts):
        try:
            return await _send(context, **kw)
        except RetryAfter as e:
            # ФЛУД-КОНТРОЛЬ Telegram (массовая рассылка по темам): ждём РОВНО окно, что просит Telegram,
            # + запас, потом повтор ЭТОЙ ЖЕ отправки (тему не теряем). Класс-фикс: единый retry на флуд.
            last = e
            wait = getattr(e, "retry_after", delay) + 1
            log.warning(f"  → _send_retry: флуд-контроль (RetryAfter {getattr(e,'retry_after','?')}s), "
                        f"попытка {i + 1}/{attempts}, ждём {wait}s")
            if i < attempts - 1:
                await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as e:
            last = e
            log.warning(f"  → _send_retry: попытка {i + 1}/{attempts} упала ({type(e).__name__}); "
                        f"повтор через {delay}s")
            if i < attempts - 1:
                await asyncio.sleep(delay)
    log.error(f"  → _send_retry: НЕ доставлено после {attempts} попыток ({last}); "
              f"запись/баланс верны (идемпотентно по msg_id)")
    return None


# === Кто такой Пым (главный по деньгам) ===
PYM_USERNAMES = {"pleummmm"}  # lower-case, без @

# === ОБРАЩЕНИЕ К ТАЙЦАМ В ИСХОДЯЩИХ — ТОЛЬКО @username, без имени (правило 28.06) ===
# Единая точка: в любом исходящем тексте бота таец упоминается/адресуется ТОЛЬКО через эти хэндлы,
# имя («Пым»/«Earth»/«Pleum»…) в тексте бота НЕ писать. Новых тайцев добавлять сюда (ключ→@username),
# не хардкодить хэндл по тексту.
THAI_HANDLES = {
    "pym": "@Pleummmm",   # Пым — главный по деньгам/визирование ТО (id/username из PYM_USERNAMES)
    # сюда добавлять остальных тайцев по мере появления их @username (механики и т.д.)
}
PYM_HANDLE = THAI_HANDLES["pym"]

# === Аккаунты владельца (Филипп пишет из них) — тоже доверенные ===
OWNER_USERNAMES = {"turbophuket", "turbophuket1"}
# Владелец МНОГОАККАУНТНЫЙ: 504608015 (HQ-личный) + 6879003264 (@turbophuket1, бизнес) + 5466425480 (@samhold, личный).
# ЕДИНЫЙ источник owner-id для ВСЕХ owner-команд — строгий «==id» молча отвергал другой аккаунт
# (баг /pin_info_all 29.06: @turbophuket1 6879003264 отвергнут; 30.06 добавлен 3-й @samhold 5466425480).
# Новый аккаунт владельца добавлять ТОЛЬКО сюда — все команды на is_owner_user подхватят автоматически.
OWNER_IDS = {504608015, 6879003264, 5466425480}

# Доверенные авторы: их записи Splinter учитывает и на них реагирует
TRUSTED_AUTHORS = PYM_USERNAMES | OWNER_USERNAMES

# Авторизаторы approve брони в группе «Входящие брони» (intake) — ОТДЕЛЬНОЕ множество.
# Менеджерам (Даня/Даша) даём право approve ТОЛЬКО на бронь в intake; прав внутреннего
# контура (касса/обслуживание) у них НЕТ — те остаются на Пыме + владельце. Пым сюда НЕ входит.
INTAKE_APPROVERS = {"turbophuket", "turbophuket1", "deramor", "rogova_darya"}  # lower, без @

# === Группы и их режим (chat_id → mode) ===
GROUPS = {
    -1003873906891:    "money",       # Money Cashflow — главный журнал
    -1003909369438:    "money",       # Самоорганизация — мелкая касса
    -1002751134848: "servicing",   # การบำรุงรักษา / Обслуживание
    -1002445921469: "delivery",    # Delivery cooperation
    -1003966216195: "attendance",  # Отметка сотрудников / การลงเวลาเข้า
    -1003997419806: "intake",      # TurboBaby — Входящие брони (клиентский контур, RU)
}

INTAKE_CHAT = -1003997419806      # группа «Входящие брони» (язык RU, без тайского)

# Стабильные имена кошельков/групп (chat_id → метка для учёта).
# ВАЖНО: баланс считается по этой метке, не по TG-названию (оно может меняться).
GROUP_NAMES = {
    -1003873906891:    "Money Cashflow",
    -1003909369438:    "Самоорганизация",
    -1002751134848: "Обслуживание",
    -1002445921469: "Delivery",
    -1003966216195: "Отметка",
    -1003997419806: "Входящие брони",
}


def group_label(chat_id):
    return GROUP_NAMES.get(chat_id, str(chat_id))


# === Темы чужого контура в HQ — Splinter ПОЛНОСТЬЮ игнорирует ===
# В HQ (-1003853365891): тема 205 «Обучение юзербота» — pc_agent/userbot (на ПК);
# тема 328 — dev-bot (VPS, полу-оркестратор). Обе адресованы агентам, не Splinter. Splinter туда
# не лезет: не отвечает, мозг не запускает, учёт/аудитор НЕ работают — это не опергруппы.
# (Тема 161 «Аудит» гейтится отдельно через AUDIT_THREAD_ID в bot.py — здесь не указываем.)
HQ_CHAT_ID = -1003853365891
IGNORED_THREADS = {205, 328}


def _pc_dev_topic():
    """Тема «PC-дев» (вторая полоса lane=pc, 04.07.2026) из env PC_DEV_TOPIC_ID; 0 = не создана.
    Лениво (не модульной константой): bot.py импортирует splinter ДО load_dotenv()."""
    try:
        return int(os.getenv("PC_DEV_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0


def _inbox_topic():
    """Тема «Единый инбокс подтверждений» (ст3 оркестратора, 06.07.2026) из env INBOX_TOPIC_ID;
    0 = инбокс выключен. Лениво (как _pc_dev_topic — bot.py импортирует splinter ДО load_dotenv).
    Splinter молчит в теме-инбоксе: там devbot собирает approve-карточки, опергруппы там нет."""
    try:
        return int(os.getenv("INBOX_TOPIC_ID", "0") or 0)
    except (TypeError, ValueError):
        return 0


def is_ignored_thread(chat_id, topic_id) -> bool:
    """True → Splinter полностью молчит в этой теме (чужой контур userbot/агента в HQ).
    Проверять РАНО, до мозга/учёта/аудитора/любой реакции. Темы PC-дев (env PC_DEV_TOPIC_ID)
    и инбокс подтверждений (env INBOX_TOPIC_ID) тоже игнорятся: там командует devbot, Splinter
    молчит как в 328."""
    if chat_id != HQ_CHAT_ID:
        return False
    if topic_id in IGNORED_THREADS:
        return True
    pc = _pc_dev_topic()
    if pc and topic_id == pc:
        return True
    inbox = _inbox_topic()
    return bool(inbox) and topic_id == inbox


# Через сколько записей звать Пыма проверить (для накопительного режима)
NUDGE_EVERY = 5

# Группы где подтверждаем КАЖДУЮ запись с балансом (как старый @Turbobabyrepair_bot).
# Остальные денежные группы — накопительный режим (молча копим, периодически тегаем Пыма).
MONEY_CONFIRM_EACH = {-1003909369438}  # Самоорганизация (мелкая касса)

# Куда идут переносы "в самоорганизацию" (мелкая касса)
PETTYCASH_CHAT_ID = -1003909369438
PETTYCASH_LABEL = "Самоорганизация"

# Каждые N записей в Money Cashflow — спросить Пыма про сверку наличных
RECONCILE_EVERY = 8

# Рабочий день (для attendance)
WORK_START_HOUR = 10
WORK_END_HOUR = 19

# Счётчики записей с последнего "зайди проверь" (в памяти, сбрасывается при рестарте)
_entry_counts = {}


# ============================================================
#  ПАРСИНГ ДЕНЕГ через Claude
# ============================================================

MONEY_SYSTEM = """Ты разбираешь ОДНО сообщение из кассового журнала аренды мотобайков.
Верни СТРОГО JSON, без пояснений и markdown.

Поля:
  type: "transaction" | "balance_check" | "balance_set" | "undo" | "question" | "none"

  transaction — проводка прихода/расхода. Может содержать НЕСКОЛЬКО движений
      (например деньги + возврат паспорта в одном сообщении):
    moves: массив движений (минимум одно), каждое движение:
        amount: число (ОТРИЦАТЕЛЬНОЕ для расхода/списания/возврата, ПОЛОЖИТЕЛЬНОЕ для прихода) — уважай знак автора
        currency: "THB" | "EUR" | "USD" | "USDT" | "PASSPORT" | "UNKNOWN" | null
        category: "rental" | "salary" | "advance" | "fuel" | "taxi" | "topup" | "other"
        bike: строка или null
        deposit: "passport" | "cash" | null  — ТОЛЬКО описание денежной строки, на счётчик НЕ влияет
    transfer_to_pettycash: true ТОЛЬКО если перенос в мелкую кассу/самоорганизацию
        (фразы "в самоорганизацию", "в кассу", "top up management", "пополнение кассы"). Иначе false.

    ВАЖНО про паспорта: паспорт — это валюта PASSPORT (amount = ±количество паспортов),
        а НЕ деньги. "-1 passport" = вернули паспорт клиенту -> движение {"amount":-1,"currency":"PASSPORT"}.
        "+1 passport" = приняли паспорт в залог -> {"amount":1,"currency":"PASSPORT"}.
        Если в сообщении И деньги, И паспорт — верни ОБА движения в moves.

  balance_check — автор ПРОСТО называет текущий баланс чтобы сверить (без слов «зафиксируй/установи»):
    balance: {"THB": число|null, "EUR": число|null, "PASSPORT": число|null}

  balance_set — автор хочет УСТАНОВИТЬ/зафиксировать баланс как есть (стартовый или правка).
    Признаки: "зафиксируй", "прими как есть", "установи", "должно быть", "это стартовый", "запиши баланс".
    balance: {"THB": число|null, "EUR": число|null, "PASSPORT": число|null}

  question — автор спрашивает (например "какой баланс?", "сколько в кассе?", "сходится?"):
    q: краткая суть вопроса

  undo — автор хочет ОТМЕНИТЬ последнюю запись.
    Признаки: "отмени", "отмена", "убери последнее", "удали последнюю", "не то записал", "верни как было", "ошибка".

  none — болтовня/не относится к учёту.

Валюта: Bath/Baht/บาท/฿ = THB; Euro/евро/€ = EUR; Dollar/dollar/доллар/USD/$ = USD;
USDT/Tether = USDT; passport/паспорт = PASSPORT.
ВАЖНО про валюту движения:
 - Валюта в тексте НЕ упомянута вообще → currency: null (по умолчанию баты, переспроса НЕ будет).
 - Упомянута и понятна → ставь её код (THB/EUR/USD/USDT).
 - Упомянута, но это НЕ из списка (странное/непонятное слово, неясная валюта) → currency: "UNKNOWN"
   (бот переспросит, НЕ запишет вслепую). UNKNOWN ставь ТОЛЬКО когда валюта реально названа, но непонятна.

Примеры:
"ADV 8004  +4,900 Bath  1 passport" -> {"type":"transaction","moves":[{"amount":4900,"currency":"THB","category":"rental","bike":"ADV 8004","deposit":"passport"},{"amount":1,"currency":"PASSPORT","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"ADV 6004  +700 Bath  -1 passport" -> {"type":"transaction","moves":[{"amount":700,"currency":"THB","category":"rental","bike":"ADV 6004","deposit":"passport"},{"amount":-1,"currency":"PASSPORT","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"-1 passport" -> {"type":"transaction","moves":[{"amount":-1,"currency":"PASSPORT","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"+1 passport" -> {"type":"transaction","moves":[{"amount":1,"currency":"PASSPORT","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"Earth salary  -5,000 Bath" -> {"type":"transaction","moves":[{"amount":-5000,"currency":"THB","category":"salary","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"Ninja 6334  +700 Dollar" -> {"type":"transaction","moves":[{"amount":700,"currency":"USD","category":"rental","bike":"Ninja 6334","deposit":null}],"transfer_to_pettycash":false}
"+500 USDT" -> {"type":"transaction","moves":[{"amount":500,"currency":"USDT","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"+700 рупий" -> {"type":"transaction","moves":[{"amount":700,"currency":"UNKNOWN","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"-1000 в самоорганизацию" -> {"type":"transaction","moves":[{"amount":-1000,"currency":"THB","category":"topup","bike":null,"deposit":null}],"transfer_to_pettycash":true}
"-290" -> {"type":"transaction","moves":[{"amount":-290,"currency":"THB","category":"other","bike":null,"deposit":null}],"transfer_to_pettycash":false}
"Balance 5,715 Bath 150 Euro 1 Passport" -> {"type":"balance_check","balance":{"THB":5715,"EUR":150,"PASSPORT":1}}
"Balance 5,715 Bath 150 Euro 1 Passport. Зафиксируй" -> {"type":"balance_set","balance":{"THB":5715,"EUR":150,"PASSPORT":1}}
"Прими как есть 5715 бат" -> {"type":"balance_set","balance":{"THB":5715,"EUR":null,"PASSPORT":null}}
"должно быть 5715" -> {"type":"balance_set","balance":{"THB":5715,"EUR":null,"PASSPORT":null}}
"какой сейчас баланс кассы?" -> {"type":"question","q":"баланс кассы"}
"отмени последнее" -> {"type":"undo"}
"убери последнюю запись, ошибся" -> {"type":"undo"}
"не то записал, верни" -> {"type":"undo"}
"Do you have work today?" -> {"type":"none"}

Верни ТОЛЬКО JSON-объект."""


# === INTAKE (приём карточек брони, клиентский контур) ===
INTAKE_SYSTEM = """Тебе дают КАРТОЧКУ БРОНИ из служебной группы (формат стабильный, начинается с «🆕 БРОНЬ»).
Извлеки поля в СТРОГИЙ JSON. Если поля нет — пустая строка.
{
  "client": "<имя клиента>",
  "contacts": "<ВСЕ контакты ОДНОЙ строкой: @username + телефон из профиля + телефон от клиента — собрать ВСЁ, не терять>",
  "model": "<модель/байк как в карточке>",
  "date_start": "<дата начала как в карточке, как есть>",
  "date_end": "<дата конца как в карточке, как есть>",
  "date_start_iso": "<дата начала в формате YYYY-MM-DD; если год не указан — текущий>",
  "date_end_iso": "<дата конца в формате YYYY-MM-DD>",
  "term": "<срок словами, напр. '7 дней'>",
  "experience": "<опыт вождения кратко>",
  "deposit_type": "деньги|паспорт|<пусто если не ясно>",
  "delivery_name": "<район/название точки доставки>",
  "delivery_url": "<ссылка Google Maps>",
  "helmets": "<число шлемов>"
}
Контакты — собери ВСЕ части (username + все телефоны). Верни ТОЛЬКО JSON."""

# Черновики intake в памяти: {chat_id: {поля, ts, passport_photo, status}}. Один активный на группу.
_INTAKE_DRAFTS = {}

# B2: буфер OCR паспорта по чату: {chat_id: {file_id, fields|None, ocr_status, ts}}.
# Связывает фото↔карточку в обе стороны (фото могло прийти ДО или ПОСЛЕ карточки, окно 5 мин).
_INTAKE_PASSPORT = {}

# O3-3a ВЫДАЧА: ожидающая подтверждения активация брони (Бронь→В аренде) — {chat_id: {...}}.
# Карточка уходит в INTAKE_CHAT (авторизаторы = INTAKE_APPROVERS; Пым/тайцы НЕ авторизуют — §9),
# «да» исполняется красным шагом под билетом 4.2. Один активный запрос на чат, TTL как approve.
_HANDOVER_ACTIVATIONS = {}
_HO_ACT_TTL = 1800          # сек; просроченный запрос «да» больше не исполняет
_HO_ACT_WARN_TS = {}        # bike → ts последнего ⚠️ «бронь не нашёл» (анти-спам повторных handover-фраз)
_HO_ACT_WARN_COOLDOWN = 600

# O3-3b фаза II ПРИЁМ: ожидающее подтверждения закрытие аренды (В аренде→Завершена) — {chat_id: {...}}.
# Зеркало _HANDOVER_ACTIVATIONS: карточка в INTAKE_CHAT (авторизаторы INTAKE_APPROVERS),
# «да» → close_booking красным шагом под билетом 4.2. Один активный запрос на чат, TTL как approve.
_RETURN_CLOSES = {}
_RET_CLOSE_TTL = 1800       # сек; просроченный запрос «да» больше не исполняет
_RET_CLOSE_WARN_TS = {}     # bike → ts последнего ⚠️ «В аренде не нашёл» (анти-спам повторных return-фраз)
_RET_CLOSE_WARN_COOLDOWN = 600

# Стандартный денежный депозит по модели (из прайса) — для ПОКАЗА в резюме (этап A не пишет).
# Порядок важен: специфичные/дорогие выше, иначе короткий ключ перехватит.
_DEPOSIT_BY_MODEL = [
    (("xadv",), 25000),
    (("ninja", "vulcan", "cbr 650", "cbr650", "cb 650", "cb650", "xsr 900", "xsr900", "r7"), 20000),
    (("cb 300", "cb300", "rebel", "mt-03", "mt03", "mt 03"), 15000),
    (("xmax 300 new", "xmax new", "adv 350", "adv350", "xsr 155", "xsr155"), 7000),
    (("pcx 160", "pcx160", "adv 160", "adv160", "forza", "xmax"), 5000),
    (("pcx 150", "pcx150", "adv 150", "adv150", "nmax"), 3000),
]

# Детект района доставки: Пхукет / вне Пхукета / неизвестно (короткая ссылка ничего не выдаёт).
_PHUKET_HINTS = ("пхукет", "phuket", "kamala", "камала", "bangtao", "бангтао", "таланг", "thalang",
                 "патонг", "patong", "kata", "ката", "karon", "карон", "rawai", "раваи", "chalong",
                 "чалонг", "найхарн", "nai harn", "surin", "сурин", "laguna", "лагуна", "cherng talay")
_NON_PHUKET = ("бангкок", "bangkok", "krabi", "краби", "phang", "пхангнга", "samui", "самуи",
               "pattaya", "паттайя", "chiang", "чианг", "ко самуи", "koh samui")

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BKK_TZ = _ZoneInfo("Asia/Bangkok")
except Exception:
    _BKK_TZ = None

SERVICING_SYSTEM = """Ты следишь за группой обслуживания мотобайков.
Верни СТРОГО JSON, без пояснений.

Поля:
  type: "event" | "none"
  event_type: "return" | "handover" | "repair" | "intake" | "other"
    (return = байк вернулся, handover = выдан клиенту, repair = ремонт/неисправность, intake = приёмка/осмотр)
  bike: строка или null
  fuel: строка или null (если упомянут уровень топлива)
  mileage: строка или null (если упомянут пробег/км)
  works: массив строк — КОНКРЕТНЫЕ выполненные работы, если техник перечислил что СДЕЛАНО
    (напр. ["замена масла","замена масляного фильтра","задние колодки","регулировка цепи"]).
    Каждый пункт — отдельной строкой. Если про выполненные работы ничего нет — пустой массив [].
  notes: короткое описание на русском

Если просто болтовня без события: type "none".

Примеры:
"Надо проверить вариатор когда вернется в офис" -> {"type":"event","event_type":"repair","bike":null,"fuel":null,"mileage":null,"works":[],"notes":"проверить вариатор по возвращении"}
"N-max 7530 вернулся, пробег 12450, бензин полный" -> {"type":"event","event_type":"return","bike":"N-max 7530","fuel":"полный","mileage":"12450","works":[],"notes":"байк вернулся"}
"На байке сделали: замена масла, масляный фильтр, задние колодки, регулировка цепи" -> {"type":"event","event_type":"repair","bike":null,"fuel":null,"mileage":null,"works":["замена масла","масляный фильтр","задние колодки","регулировка цепи"],"notes":"выполнены работы по обслуживанию"}

Верни ТОЛЬКО JSON-объект."""


# === ДВУЯЗЫЧИЕ: русский — ОСНОВА, тайский — ТОЧНЫЙ ПЕРЕВОД (вариант 1, штаб 24.06) ===
# Свободные ответы тайцам: сначала RU-текст, затем TH = детерминированный перевод этого RU
# (НЕ параллельная генерация). Так смысл/конкретика гарантированно совпадают. Шаблоны msg_* не трогаем.
TRANSLATE_RU_TH = """Переведи русский текст на ТАЙСКИЙ для рабочего чата мотопроката (Пхукет, общение с тайскими сотрудниками).
ПРАВИЛА:
- Передай ВЕСЬ смысл и КОНКРЕТИКУ оригинала: детали повреждений, числа, суммы, пробег, привязку к депозиту, инструкции — НИЧЕГО не выкидывай и не сокращай.
- Транспорт здесь — мотобайк: «байк/мотоцикл/скутер» переводи как รถมอเตอร์ไซค์ / รถ. НИКОГДА не используй รถยนต์ (это легковой автомобиль) — это мотопрокат, машин тут нет.
- В ответе ТОЛЬКО тайский текст. Без кириллицы. Числа — цифрами; названия моделей/номера байков — латиницей как в оригинале. Эмодзи сохраняй.
- Тон рабочий, вежливый (ครับ). НЕ добавляй пояснений вида «вот перевод» — верни ТОЛЬКО перевод."""

# Запрещённые «автомобильные» слова → байк (страховка против соскальзывания LLM / авто-перевода Telegram).
import re as _re_lang
_CAR_RU = _re_lang.compile("автомобил[а-я]*|машин[ауыеой]?", _re_lang.IGNORECASE)
_THAI_RE = _re_lang.compile("[฀-๿]")


def _no_car(text):
    """Байк НЕ «автомобиль/машина/รถยนต์». Применяется к RU и к TH-переводу."""
    t = _CAR_RU.sub("байк", text or "")
    return t.replace("รถยนต์", "รถมอเตอร์ไซค์")


def _extract_ru(text):
    """Достать РУССКУЮ основу из произвольного pin/ответа (если пришёл старый двуязычный — берём 🇷🇺-часть)."""
    t = text or ""
    if "🇷🇺" in t:
        return t.split("🇷🇺", 1)[1].split("🇹🇭")[0].strip(" :\n")
    if "🇹🇭" in t:
        return (t.split("🇹🇭")[0].strip() or t.strip())
    return t.strip()


def _translate_ru_th(claude, ru_text):
    """RU→TH точный перевод ОДНИМ вызовом (+страховка _no_car). Фоллбэк при пустом/сбое —
    короткий тайский указатель на RU-блок (без кириллицы, чтобы аудитор не флагал смешение)."""
    ru = (ru_text or "").strip()
    if not ru:
        return ""
    try:
        th = (claude.quick(TRANSLATE_RU_TH, ru, max_tokens=500, model="LIGHT",
                           tag="translate", escalate_to="MAIN") or "").strip()
    except Exception:
        log.exception("  → перевод RU→TH упал")
        th = ""
    th = _no_car(th)
    if not th or not _THAI_RE.search(th):   # нет тайских символов → фоллбэк
        return "ดูรายละเอียดในข้อความภาษารัสเซียด้านล่างครับ"
    return th


def bilingual_from_ru(claude, ru_text, head="🐀 Splinter"):
    """Собрать двуязычное сообщение из РУССКОЙ основы: 🇹🇭 точный перевод (первым) + 🇷🇺 оригинал.
    Гарантирует ОБА блока. Используется для свободных ответов тайцам (не шаблоны)."""
    ru = _no_car((ru_text or "").strip())
    th = _translate_ru_th(claude, ru)
    body = f"🇹🇭 {th}\n{_SEP}\n🇷🇺 {ru}"
    return (head + "\n" + body) if head else body


def bilingual_pin(claude, raw):
    """Пин/важное: из RU-основы (или старого двуязычного) собрать TH-перевод + RU. Без шапки 🐀."""
    return bilingual_from_ru(claude, _extract_ru(raw), head="")


VISION_BIKE_SYSTEM = """На фото — мотобайк, его приборная панель, колесо или деталь (приёмка/сдача/сервис).
Извлеки данные и верни СТРОГО JSON:
  fuel: уровень топлива словом ("full"/"3/4"/"half"/"1/4"/"empty") или null если не видно
  mileage: ОБЩИЙ пробег с одометра (ODO), только цифры. ВНИМАНИЕ:
     - бери именно ODO (общий пробег, обычно 5-6 цифр), НЕ trip/TRIP A/B (сбрасываемый, обычно мал)
     - НЕ путай со скоростью (спидометр), оборотами (RPM), временем, напряжением
     - читай ЦИФРУ ЗА ЦИФРОЙ слева направо, не угадывай по форме
     - частые путаницы на мелких/цифровых табло: 1↔7, 0↔8, 5↔6, 3↔8 — присмотрись
     - если хоть одна цифра смазана/под углом/перекрыта/не уверен → mileage_confidence:"low"
     - если совсем не разобрать или нет приборной панели с цифрами → mileage:null
  mileage_confidence: "high" | "low" — high ТОЛЬКО если все цифры чёткие и читаются однозначно
  tire: состояние шин если видно колесо/протектор:
     {position: "front"|"rear"|null, condition: "new"|"good"|"worn"|"bald"|null, note: "..."}
     или null если колёс не видно
  damage: ТОЛЬКО реальные повреждения (скол, трещина, вмятина, разбито, треснуто,
     сломана деталь, оторвано, не работает) — краткое описание, или null если их нет.
     ВАЖНО: грязь, пыль, налёт, разводы, следы эксплуатации, потёртость, мелкие
     поверхностные царапины — это НЕ damage. Если видишь только грязь/пыль — damage:null.
  dirt: true если байк грязный/пыльный/в разводах/есть следы эксплуатации; иначе false.
     (грязь идёт сюда, а НЕ в damage)
  kind: "dashboard" | "wheel" | "bike" | "receipt" | "other"
  notes: короткая заметка на русском
ВАЖНО: техника здесь — мотобайк/скутер. В notes и damage НИКОГДА не называй её «автомобиль/машина» — только «байк/мотоцикл/скутер».
Если не разобрать — ставь null. Лучше null, чем выдумка. Верни ТОЛЬКО JSON."""

VISION_RECEIPT_SYSTEM = """На фото — чек/квитанция ИЛИ купюры (наличные).
Верни СТРОГО JSON:
  amount: сумма числом или null
  currency: "THB" | "EUR" | "USD" | "USDT" | null  — какая валюта на фото (฿/บาท=THB, €=EUR,
     доллары $=USD, USDT=USDT). Если не уверен/не видно — null. НЕ угадывай.
  currency_confidence: "high" | "low"  — high только если валюта явно различима
  vendor: за что (бензин/АЗС/магазин/такси) или null
  notes: короткая заметка на русском
Верни ТОЛЬКО JSON. Купюры часто мятые/частичные — если сомневаешься в валюте, ставь null/low."""


# === Буфер недавних фото-разборов (для вопросов "проверь фото резины/пробега") ===
# {chat_id: [ {vis, sender, time}, ... ]} — храним последние N на группу
import time as _time
import hashlib as _hashlib   # подпись текста работы — разводит РАЗНЫЕ работы с одним стемом (класс 4957)
from collections import deque
_RECENT_PHOTOS = {}
_RECENT_LIMIT = 12          # сколько последних фото помнить на группу
_RECENT_TTL = 3 * 3600      # 3 часа — потом считаем устаревшим

# Отложенные ИНФО-работы (колодки/цепь/масл.фильтр/вилка/прочее) — техник назвал работы ТЕКСТОМ
# без пробега; пишем их в историю «события» строкой-на-работу, КОГДА в теме придёт чёткий пробег
# (фото/число).
# {(chat_id, topic_id): {"works":[...], "at":{ключ-работы: ts}, "bike":str, "msg_id_base":str, "ts":float}}
# БУФЕР ДОПИСЫВАЕТСЯ, А НЕ ЗАМЕЩАЕТСЯ (класс-фикс 22.08.2026, разбор 5960). До этого дня здесь
# стояло голое присваивание по ключу темы, и ВТОРАЯ партия работ в той же теме молча стирала
# первую: 01.08 в 05:53:50 отложено четыре работы, в 07:31:02 в ту же ячейку легло три — «долив
# тормозной жидкости» исчез без единой строки в журнале. Добавление идёт по КОНТЕНТНОМУ ключу
# (`_work_key`, тот же, которым дедупится запись), поэтому переформулировка той же работы
# («передняя шина» → «замена передней шины») партию не раздувает, а РАЗНЫЕ работы не схлопываются.
# Срок годности — у КАЖДОЙ позиции свой (`at`): иначе свежая работа наследовала бы возраст старой
# и протухала бы вместе с ней.
_PENDING_WORKS = {}
_PENDING_WORKS_TTL = 3 * 3600   # 3 часа — потом перечень протух, не пишем

# ЧАСТЬ D: message_id ПРОМЕЖУТОЧНЫХ бот-вопросов ТО-цикла (пробег? замена? фото одометра?) —
# копим по теме, удаляем на ФИНАЛЕ цикла (✅ записано/принято). Финал и закреп-просрочку НЕ копим.
# {(chat_id, topic_id): [(message_id, ts), ...]}. Волатильный; TTL от утечек.
_SVC_CYCLE_MSGS = {}
_SVC_CYCLE_TTL = 3 * 3600


def _remember_cycle_msg(chat_id, topic_id, sent):
    """Запомнить message_id промежуточного бот-вопроса (для удаления на финале цикла)."""
    mid = getattr(sent, "message_id", None) if sent else None
    if mid is None:
        return
    _SVC_CYCLE_MSGS.setdefault((chat_id, topic_id), []).append((mid, _time.time()))


async def _clear_cycle_msgs(context, chat_id, topic_id):
    """ФИНАЛ цикла ТО → удалить накопленные промежуточные бот-вопросы (best-effort).
    Закреп-просрочку и финальные сообщения НЕ трогаем — их id сюда не попадают.
    delete_message может упасть (>48ч / уже удалено / нет прав) → ловим, флоу не роняем."""
    msgs = _SVC_CYCLE_MSGS.pop((chat_id, topic_id), [])
    now = _time.time()
    for mid, ts in msgs:
        if now - ts > _SVC_CYCLE_TTL:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception as e:
            log.info(f"  → чистка ТО: не удалил вопрос {mid} (best-effort): {e}")


# ЕДИНОЕ ИТОГОВОЕ сообщение ТО-цикла: накопитель по теме. Записи (работы/масло/столбцы) кладут сюда
# результат, НЕ шлют по отдельности; в терминальной точке цикла — ОДНА сводка _emit_summary, накопитель
# очищается. {(chat_id, topic_id): {current_km, works:[], works_km, oil:{km,next,status}|None, cols:[...], ts}}
_SVC_SUMMARY = {}
_SVC_SUMMARY_TTL = 3 * 3600


def _summary_acc(chat_id, topic_id):
    """Накопитель сводки для темы (создаёт/обновляет ts; протухший пересоздаёт)."""
    acc = _SVC_SUMMARY.get((chat_id, topic_id))
    if acc is None or _time.time() - acc.get("ts", 0) > _SVC_SUMMARY_TTL:
        acc = {"current_km": "", "works": [], "works_km": "", "oil": None, "cols": [], "failed": []}
        _SVC_SUMMARY[(chat_id, topic_id)] = acc
    acc.setdefault("failed", [])   # легаси-накопители (созданы до фикса) — не падать на .get
    acc["ts"] = _time.time()
    return acc


def _summary_note_failed(chat_id, topic_id, failed):
    """Работа НЕ записалась → это ВИДНО (класс-фикс 4957, корень 3). Кладём в накопитель, чтобы
    сводка НАЗВАЛА потерю поимённо. Раньше провал записи был виден только в логе (а логи никто из
    команды не читает) — «механик сдал четыре работы, записалась одна, и никто не узнал».
    Fail-safe: нет chat_id / сбой накопителя → только лог, вызывающего не роняем."""
    try:
        if chat_id is None or not failed:
            return
        acc = _summary_acc(chat_id, topic_id)
        for w, why in failed:
            item = (str(w), str(why))
            if item not in acc["failed"]:
                acc["failed"].append(item)
    except Exception:
        log.exception("  → пометка «не записалось» в накопитель сбоила (лог остаётся)")


async def _emit_summary(context, chat_id, topic_id, bike, skip_oil=False, reply_markup=None):
    """ТЕРМИНАЛ цикла → собрать ОДНУ сводку из накопителя, отправить, накопитель очистить.
    skip_oil=True (overdue [Просто пробег]) — масло уже в закрепе, в сводке его не дублируем;
    тогда шлём сводку ТОЛЬКО если есть работы/столбцы. Возвращает отправленный Message (для закрепа
    итога) ИЛИ None если ничего не отправили.

    `reply_markup` — клавиатура квитанции (кнопка отмены записи, 14.08.2026). У двери масла
    СВОЕГО сообщения нет вовсе: её единственный видимый след — эта сводка, поэтому кнопке негде
    было сесть и её тут не было. Значение приносит ТОЛЬКО дверь, которая ПРЯМО СЕЙЧАС записала
    (`_write_oil`); у прочих зовущих (ветка «просто пробег», столбцы) остаётся None, и путь
    байт-в-байт прежний — иначе кнопка отмены появилась бы на сводке, за которой записи не было."""
    acc = _SVC_SUMMARY.pop((chat_id, topic_id), None)
    if not acc:
        return None
    # failed в условии — обязательно: если ВСЕ работы провалились, сводки бы не было вовсе
    # и потеря снова стала бы невидимой (класс-фикс 4957, корень 3).
    has = bool(acc.get("works") or acc.get("cols") or acc.get("failed")
               or (acc.get("oil") and not skip_oil))
    if not has:
        return None
    # КЛАСС-ФИКС кнопочных подтверждений: сводка-квитанция через _send_retry — ConnectTimeout (сетевой блип)
    # не оставляет владельца в тишине после нажатия кнопки. Действие уже выполнено, переотправка идемпотентна.
    return await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                             text=msg_service_summary(bike, acc, skip_oil=skip_oil),
                             reply_markup=reply_markup)


# Анти-спам для просьбы «пришли чёткое фото одометра» (масло без читаемого пробега):
# не повторять чаще раза в 10 мин на тему. {(chat_id, topic_id): ts}. Волатильный — ок для троттлинга.
_ODOMETER_ASK_TS = {}
_ODOMETER_ASK_COOLDOWN = 600   # сек

# ============================================================================================
#  ЗАМОК ПОВТОРНЫХ ПОДСКАЗОК — РУКИ (решение живёт в hint_dedup.py, импортов там ноль)
# ============================================================================================
#  ОДНА дверь `_hint_send` на ВСЕ 14 мест переписи 22.08.2026 — не 14 заплат. Правило одно:
#  та же подсказка по тому же байку не уходит второй раз, пока не изменилось СОСТОЯНИЕ,
#  её породившее; долго держащееся состояние даёт право на повтор через `_HINT_REPEAT_H`
#  (24 ч — число выведено из корпуса, обоснование в докстринге hint_dedup).
#
#  ПРЕЖНИЕ ТРОТТЛЫ НЕ ТРОНУТЫ: `_should_ask_odometer` (10 мин), `_sp_ask_ok` (90 с),
#  `_SP_LAST_SENT`/`last_reminded_at` (6 ч), закреп ТО (5 суток) живут как жили. Замок стоит
#  ПОВЕРХ них и умеет РОВНО одно — не повторять; разрешить он не умеет физически.
#
#  ПАМЯТЬ НА ДИСКЕ, а не только в процессе: splinter за окно переписи перезапускался 126 раз
#  (≈2 раза в сутки), а у половины видов своей персистентной защиты нет вовсе — держи замок
#  только в памяти, и каждый рестарт открывал бы повтору дверь. Файл свой, рабочих таблиц и
#  зеркала «обслуживание» не касается.
#  ГДЕ ЛЕЖИТ ПАМЯТЬ — РЕШАЕТСЯ НА КАЖДОМ ЗОВЕ, А НЕ НА ИМПОРТЕ, и прогон тестов в боевое
#  состояние не пишет НИКОГДА. Класс известен этому репозиторию дословно: в боевом
#  `wallet_cache.json` жила фикстура `tests/test_deposit_link.py`, попадавшая туда на каждом
#  прогоне гейта. Здесь он вскрылся живьём: после первого полного гейта в боевом файле лежали
#  РЕАЛЬНЫЕ имена байков и номера тем из легаси-фикстур (4957, 4248, 4724, 6334) — то есть
#  замок мог подавить НАСТОЯЩУЮ подсказку по настоящему байку. Изолировать сьюты по одному —
#  игра в догонялки: следующий новый сьют откроет дыру снова. Поэтому судим ПРИЗНАК прогона,
#  теми же четырьмя именами, которыми это делает гард (`gate.py` ставит их подпроцессам сам).
_HINT_TEST_MARKS = ("PRETOOL_NOPUSH", "PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PYTEST_CURRENT_TEST")
_HINT_STATE_SAID = False        # путь памяти называем в журнале ОДИН раз — чтобы прод было чем сверить


def _hint_state_path():
    """Файл памяти замка. Явная подмена сильнее всего; признак прогона тестов уводит во
    временный каталог. Ошибка в эту сторону безвредна: память уедет в /tmp, замок продолжит
    работать, а лишняя подсказка дешевле подавленной настоящей."""
    global _HINT_STATE_SAID
    p = os.getenv("HINT_DEDUP_STATE")
    if not p:
        # У прогона тестов файл СВОЙ НА ПРОЦЕСС, и это не мелочь: с общим именем память
        # утекала из одного прогона гейта в следующий (поймано живьём — на неизменном дереве
        # покраснели ДРУГИЕ два сьюта, чем в прошлый раз, потому что их подсказки подавила
        # память прошлого прогона). Персистентность нужна проду, чтобы пережить рестарт
        # splinter; тесту она нужна ровно в пределах его собственного процесса.
        p = (f"/tmp/hint_dedup_state_test_{os.getpid()}.json"
             if any(os.getenv(m) for m in _HINT_TEST_MARKS)
             else os.path.join(os.path.dirname(os.path.abspath(__file__)), "hint_dedup_state.json"))
    if not _HINT_STATE_SAID:
        _HINT_STATE_SAID = True
        log.info(f"  🔁 замок повторных подсказок: память в {p}")
    return p


_HINT_SEEN = None               # кэш в памяти процесса; None = ещё не читали с диска

#  «Повтор подавлен» — ОТДЕЛЬНЫЙ ответ, а не None. Это не эстетика: `_send` вправе вернуть что
#  угодно, включая None (так делает любой мок), и если бы подавление опознавалось по None, то
#  подавлением считалась бы ЛЮБАЯ отправка, ничего не вернувшая. Живой случай поймал сьют
#  tests/test_service_pending.py: у висяка отметка `_SP_LAST_SENT` после такого «подавления» не
#  ставилась вовсе — то есть замок повторов МОЛЧА ломал прежний троттл 6 ч и давал ДВА
#  напоминания вместо одного. Разводим по существу: подавил замок — свой ответ, и только он.
HINT_SKIPPED = object()


def _hint_enabled() -> bool:
    """Ручка отката: HINTS_DEDUP=0 в .env + рестарт splinter → путь байт-в-байт прежний."""
    return str(os.getenv("HINTS_DEDUP", "1")).strip().lower() not in ("0", "false", "no", "off")


def _hint_repeat_h() -> float:
    """Право на повтор при долго держащемся состоянии, часы. 0 → замок повторов не держит."""
    try:
        return float(os.getenv("HINT_REPEAT_H", hint_dedup.REPEAT_H_DEFAULT))
    except (TypeError, ValueError):
        return hint_dedup.REPEAT_H_DEFAULT


def _hint_load():
    """Память замка с диска. Любая беда → пустая память, то есть подсказка снова «первая»
    (направление сомнения — В ОТПРАВКУ: замолчать по незнанию нельзя)."""
    global _HINT_SEEN
    if _HINT_SEEN is None:
        try:
            with open(_hint_state_path(), encoding="utf-8") as f:
                data = json.load(f)
            _HINT_SEEN = data if isinstance(data, dict) else {}
        except Exception:
            _HINT_SEEN = {}
    return _HINT_SEEN


def _hint_save():
    """Запись памяти замка. Не удалась → факт отправки не запомнен; хуже лишней подсказки
    ничего не случится (сбой в сторону разговорчивости, а не молчания)."""
    try:
        with open(_hint_state_path(), "w", encoding="utf-8") as f:
            json.dump(_HINT_SEEN or {}, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"  → память замка подсказок не записалась: {e}")


async def _hint_send(context, *, kind, bike, state, chat_id, topic_id, text, **kw):
    """ЕДИНАЯ ДВЕРЬ ПОДСКАЗКИ. Спрашивает замок ДО отправки, запоминает факт ПОСЛЕ неё —
    упавшая отправка подсказку не тратит. Возвращает то же, что `_send`, либо `HINT_SKIPPED`,
    если повтор подавлен (место отправки обязано это учесть: подавлено = сообщения НЕТ)."""
    global _HINT_SEEN
    if not _hint_enabled():
        # Ручка отката гасит ветку ДО чтения памяти: ни файла, ни решения — путь байт-в-байт
        # прежний. Это же и держит прогон тестов подальше от боевого состояния.
        return await _send(context, chat_id=chat_id, text=text, message_thread_id=topic_id, **kw)
    seen = _hint_load()
    now = _time.time()
    v = hint_dedup.verdict(kind, bike, state, seen.get(hint_dedup.key(chat_id, topic_id, bike, kind)),
                           now, chat_id=chat_id, topic_id=topic_id,
                           repeat_h=_hint_repeat_h())     # выключенная ветка ушла выше, до памяти
    if not v["send"]:
        _age = f"{v['age_h']:.1f}ч" if v.get("age_h") is not None else "?"
        log.info(f"  🔁 подсказка {kind} ПОДАВЛЕНА (замок повторов): {v['why']}, прошло {_age} "
                 f"< {_hint_repeat_h():.0f}ч · байк={bike or '—'} тема={topic_id or '—'}")
        return HINT_SKIPPED
    sent = await _send(context, chat_id=chat_id, text=text, message_thread_id=topic_id, **kw)
    if v["key"]:
        seen[v["key"]] = {"fp": v["fp"], "ts": now}
        _HINT_SEEN = hint_dedup.prune(seen, now)
        _hint_save()
    log.info(f"  ✅ подсказка {kind} отправлена ({v['why']}) · байк={bike or '—'}")
    return sent


# Трекер «бот ждёт ответа»: (chat_id, topic_id) -> время вопроса бота.
# Если бот недавно задал вопрос в теме — следующее сообщение владельца/Пыма
# без тега считаем ответом ему (не нужно тегать/реплаить).
_AWAITING_REPLY = {}
_AWAIT_TTL = 10 * 60        # 10 минут окно ожидания ответа

def mark_awaiting(chat_id, topic_id=None):
    """Бот задал вопрос в этой теме — ждём ответ без тега."""
    _AWAITING_REPLY[(chat_id, topic_id)] = _time.time()

def is_awaiting(chat_id, topic_id=None) -> bool:
    """Ждёт ли бот ответа в этой теме (в окне TTL)."""
    ts = _AWAITING_REPLY.get((chat_id, topic_id))
    if not ts:
        return False
    if _time.time() - ts > _AWAIT_TTL:
        _AWAITING_REPLY.pop((chat_id, topic_id), None)
        return False
    return True

def clear_awaiting(chat_id, topic_id=None):
    _AWAITING_REPLY.pop((chat_id, topic_id), None)

# Кэш названий форум-тем: {(chat_id, topic_id): "название темы"}
# В названии темы записан байк (по договорённости Филиппа).
# ВНИМАНИЕ: кэш в памяти, стирается рестартом → персистится в memory.db (таблица topic_bike),
# при старте seed-ится обратно (seed_topic_bikes). Источник правды = БД, _TOPIC_NAMES = её кэш.
_TOPIC_NAMES = {}

# Память (memory.db) для персиста привязки тема→байк. Подключается из bot.py через set_memory().
_MEMORY = None


def set_memory(memory):
    """Подключить memory.db (персист тема→байк). Зовётся из bot.py при старте."""
    global _MEMORY
    _MEMORY = memory


def seed_topic_bikes():
    """Загрузить персистентные привязки тема→байк из memory.db в _TOPIC_NAMES при старте,
    чтобы пережить рестарт (иначе бот слепнет по темам). Возвращает кол-во загруженных."""
    if _MEMORY is None:
        return 0
    try:
        for (cid, tid), name in _MEMORY.all_topic_bikes().items():
            if name:
                _TOPIC_NAMES[(int(cid), int(tid))] = name
        log.info(f"Привязки тема→байк загружены из memory.db: {len(_TOPIC_NAMES)} тем")
    except Exception as e:
        log.warning(f"seed_topic_bikes error: {e}")
    return len(_TOPIC_NAMES)


# ===================== КНОПКА «ℹ️ Инфо по байку» в темах обслуживания (pinned-inline, токен-free) =====================
# Постоянная закреп-кнопка: таец жмёт вместо печати → та же карточка, что текст «дай инфу». Чтение карточки =
# ЗЕЛЁНОЕ (без гейта). callback статичный 'info:card', байк резолвится из ТЕМЫ → переживает рестарт (нет токен-буфера).
_INFO_PINNED = set()     # {(chat_id, topic_id)} — где кнопка уже закреплена (seed из memory.db на старте)
_INFO_TAP_TS = {}        # {(chat_id, topic_id): ts} — debounce 5с показа карточки по кнопке (Q6)
_INFO_PIN_PAUSE = 0.5    # сек между пинами в pin_info_all — ровный темп против флуд-контроля (RetryAfter — страховка)
_INFO_PIN_TEXT = ("🐀 Splinter · ℹ️\n"
                  "🇹🇭 กดปุ่มเพื่อดูข้อมูลรถคันนี้\n"
                  "🇷🇺 Нажми кнопку — покажу инфо по байку")


def _info_keyboard():
    """Клавиатура кнопки «Инфо» — из МАССИВА строк (расширяемо). Активна ТОЛЬКО «ℹ️ Инфо»;
    три будущие кнопки пред-размечены комментом (НЕ рендерятся — раскомментить при сборке их веток)."""
    rows = [
        [InlineKeyboardButton("🇹🇭 ข้อมูล / 🇷🇺 Инфо", callback_data="info:card")],
        # РАЗЪЁМ под будущие кнопки тайцев (механизм пина/резолва тот же; добавить = раскомментить + ветка в handle_info_button):
        # [InlineKeyboardButton("🇹🇭 ส่งมอบ / 🇷🇺 Выдал клиенту", callback_data="info:handover")],
        # [InlineKeyboardButton("🇹🇭 คืนรถ / 🇷🇺 Возврат",        callback_data="info:return")],
        # [InlineKeyboardButton("🇹🇭 บันทึกงาน / 🇷🇺 Записать работу", callback_data="info:work")],
    ]
    return InlineKeyboardMarkup(rows)


def seed_info_pins():
    """Загрузить закрепы кнопки из memory.db в _INFO_PINNED при старте → рестарт не плодит дубли."""
    if _MEMORY is None:
        return 0
    try:
        for key in _MEMORY.all_info_pins().keys():
            _INFO_PINNED.add((int(key[0]), int(key[1])))
        log.info(f"Инфо-кнопки (закрепы) загружены из memory.db: {len(_INFO_PINNED)} тем")
    except Exception as e:
        log.warning(f"seed_info_pins error: {e}")
    return len(_INFO_PINNED)


async def ensure_info_pin(context, chat_id, topic_id):
    """ЛЕНИВО (Q1): на активности в servicing-теме гарантировать закреп кнопки «ℹ️ Инфо».
    Дедуп через _INFO_PINNED (O(1), без I/O после первого раза). bike нет → пропустить (кнопке нечего показывать).
    Возвращает статус: 'already' / 'nobike' / 'pinned' / 'fail' (для итога /pin_info_all). Отправка через
    _send_retry → переживает флуд-контроль (RetryAfter) и сетевой блип — тему не теряем при массовом засеве."""
    if not topic_id:
        return "nobike"
    key = (int(chat_id), int(topic_id))
    if key in _INFO_PINNED:
        return "already"
    bike = bike_from_topic(chat_id, topic_id)
    if not bike:
        return "nobike"
    try:
        sent = await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                                 text=_INFO_PIN_TEXT, bilingual=False, reply_markup=_info_keyboard())
    except Exception:
        log.exception("  → инфо-кнопка: не смог отправить сообщение")
        return "fail"
    if sent is None:
        return "fail"
    _INFO_PINNED.add(key)   # сообщение отправлено один раз — больше не шлём (даже если пин ниже упадёт)
    if _MEMORY is not None:
        try:
            _MEMORY.set_info_pin(chat_id, topic_id, sent.message_id)
        except Exception as e:
            log.warning(f"  → инфо-кнопка: персист msg_id не удался: {e}")
    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id,
                                           disable_notification=True)
        log.info(f"  → инфо-кнопка закреплена: тема {topic_id} ({bike}) msg={sent.message_id}")
    except Exception as e:
        log.warning(f"  → инфо-кнопка: не смог закрепить (права админа?): {e}")
    return "pinned"   # сообщение+персист есть; в _INFO_PINNED → повторный засев тему не тронет (дедуп)


async def _repin_info(context, chat_id, topic_id):
    """Пере-закрепить кнопку «ℹ️ Инфо» ПОСЛЕ unpin_all (закрытие ТО Oil снимает ВСЕ пины темы).
    ИНВАРИАНТ: любой unpin_all в теме → следом _repin_info. Сообщение живо (откреплено), msg_id в memory.db.
    Зовётся ПОСЛЕ пина ТО-сводки → кнопка оказывается СВЕРХУ (Q2 — всегда видна). Идемпотентно."""
    if _MEMORY is None or not topic_id:
        return
    try:
        mid = _MEMORY.get_info_pin(chat_id, topic_id)
    except Exception:
        mid = None
    if not mid:
        return
    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=int(mid),
                                           disable_notification=True)
        log.info(f"  → инфо-кнопка пере-закреплена сверху после ТО: тема {topic_id} msg={mid}")
    except Exception as e:
        log.warning(f"  → инфо-кнопка: пере-закреп не удался: {e}")


async def _btn_answer(q, txt=None, **kw):
    """q.answer() с защитой — общий для кнопок ВНЕ O3 (паттерн _o3_answer, фикс 749cf46):
    колбэк, отлежавшийся в очереди за долгой обработкой (флуд-контроль на эдитах, апдейты
    последовательные), протухает — BadRequest «Query is too old». Ack тогда невозможен,
    но ДЕЙСТВИЕ кнопки обязано выполниться; упавший q.answer не валит хендлер."""
    try:
        await q.answer(txt, **kw)
    except Exception as e:
        log.warning(f"  → q.answer протух/упал (действие кнопки всё равно выполняю): {e}")


async def handle_info_button(update, context, bridge):
    """Кнопка «ℹ️ Инфо по байку» (CallbackQueryHandler '^info:' в bot.py). Чтение карточки — ЗЕЛЁНОЕ,
    тайцам БЕЗ гейта. Байк резолвится ИЗ ТЕМЫ (статичный callback, без токен-буфера → переживает рестарт)."""
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    action = data.split(":", 1)[1] if ":" in data else ""
    msg = q.message
    chat_id = msg.chat.id if msg else None
    topic_id = getattr(msg, "message_thread_id", None) if msg else None
    if action != "card":
        await _btn_answer(q)   # будущие info:handover/return/work — пока не обслуживаем
        return
    # Debounce 5с на (chat,topic) (Q6): два быстрых тапа → одна карточка
    key = (chat_id, topic_id)
    if _time.time() - _INFO_TAP_TS.get(key, 0) < 5:
        await _btn_answer(q, "⏳")
        return
    _INFO_TAP_TS[key] = _time.time()
    await _btn_answer(q)   # П4: мгновенно гасим «часик» на кнопке (до сбора карточки)
    bike = bike_from_topic(chat_id, topic_id)
    if not bike:
        await _send(context, chat_id=chat_id, message_thread_id=topic_id, bilingual=False,
                    text="🐀 Splinter\n🇹🇭 ยังไม่ได้ผูกรถกับหัวข้อนี้\n🇷🇺 Тема пока не привязана к байку")
        return
    # П4: мгновенная двуязычная заглушка «⏳ Вывожу…» → собрать карточку → ЗАМЕНИТЬ её editMessageText (то же
    # сообщение, не плодим новое). ОБХОД _card_allowed: явный тап кнопки ВСЕГДА отвечает (тротл — против спама на болтовне).
    ph = None
    try:
        ph = await _send(context, chat_id=chat_id, message_thread_id=topic_id, bilingual=False,
                         text="🐀 Splinter\n🇹🇭 ⏳ กำลังดึงข้อมูลล่าสุดของรถ...\n🇷🇺 ⏳ Вывожу актуальную информацию по байку...")
    except Exception:
        log.exception("  → инфо-кнопка: заглушка не ушла")
    try:
        card = _with_separator(_build_bike_card(bridge, chat_id, topic_id, bike))
        if ph is not None:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=ph.message_id,
                                                 text=card, parse_mode="HTML")
        else:   # заглушка не ушла → шлём карточку обычным путём (не оставляем без ответа)
            await _send(context, chat_id=chat_id, message_thread_id=topic_id, parse_mode="HTML", text=card)
    except Exception:
        log.exception("  → инфо-кнопка: ошибка карточки")
        if ph is not None:   # заменить «⏳» на понятную ошибку, не оставлять висеть заглушку
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=ph.message_id,
                    text="🐀 Splinter\n🇹🇭 ⚠️ ดึงข้อมูลไม่สำเร็จ ลองใหม่อีกครั้ง\n🇷🇺 ⚠️ Не удалось получить данные, попробуйте ещё раз")
            except Exception:
                log.exception("  → инфо-кнопка: не заменил заглушку на ошибку")


async def pin_info_all(context):
    """Q1 ручной засев (команда /pin_info_all владельца): пройтись по ВСЕМ темам обслуживания и закрепить
    кнопку «ℹ️ Инфо». РОВНЫМ ТЕМПОМ (пауза между отправками) против флуд-контроля; RetryAfter ловится в
    _send_retry (тему не теряем). Дедуп: уже закреплённые (в _INFO_PINNED) — без отправки. Возвращает
    разбивку {pinned, already, nobike, fail, total} для итога владельцу."""
    import asyncio
    st = {"pinned": 0, "already": 0, "nobike": 0, "fail": 0, "total": 0}
    for (cid, tid) in list(_TOPIC_NAMES.keys()):
        if int(cid) != SERVICING_CHAT:
            continue
        st["total"] += 1
        res = await ensure_info_pin(context, cid, tid)
        st[res] = st.get(res, 0) + 1
        if res in ("pinned", "fail"):   # реальная отправка была → выдержать темп (already/nobike — без отправки, без паузы)
            await asyncio.sleep(_INFO_PIN_PAUSE)
    log.info(f"  → /pin_info_all итог: запинено {st['pinned']} / уже {st['already']} / "
             f"без байка {st['nobike']} / не вышло {st['fail']} (всего {st['total']})")
    return st


SERVICING_CHAT = -1002751134848

# Карта тема→байк, собранная userbot-скриптом fetch_topics.py в файл topics_map.json.
# {topic_id(int): "название темы = байк"}. Грузится из файла и перечитывается при изменении.
# Так Splinter САМ знает байк каждой темы, без ручного забивания.
import json as _json
import os as _os
_TOPIC_MAP_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "topics_map.json")
_TOPIC_MAP = None
_TOPIC_MAP_MTIME = 0

# Ручные переопределения (на случай если у темы кривое название — можно поправить тут).
_TOPIC_BIKE_OVERRIDE = {
    # (SERVICING_CHAT, 79): "NMAX 155CC ... PHUKET ####",
}


def _load_topic_map():
    """Загружает/перезагружает topics_map.json если он изменился. Возвращает {topic_id:int -> название}."""
    global _TOPIC_MAP, _TOPIC_MAP_MTIME
    try:
        mtime = _os.path.getmtime(_TOPIC_MAP_FILE)
    except OSError:
        if _TOPIC_MAP is None:
            _TOPIC_MAP = {}
        return _TOPIC_MAP
    if _TOPIC_MAP is None or mtime != _TOPIC_MAP_MTIME:
        try:
            with open(_TOPIC_MAP_FILE, "r", encoding="utf-8") as f:
                raw = _json.load(f)
            _TOPIC_MAP = {int(k): v for k, v in raw.items()}
            _TOPIC_MAP_MTIME = mtime
            log.info(f"Карта тем загружена: {len(_TOPIC_MAP)} тем из topics_map.json")
        except Exception as e:
            log.warning(f"Не смог прочитать topics_map.json: {e}")
            if _TOPIC_MAP is None:
                _TOPIC_MAP = {}
    return _TOPIC_MAP


def _topic_name_from_msg(msg):
    """Достаёт название форум-темы из сообщения (Telegram даёт его в разных местах)."""
    # 1) сообщение о создании темы
    fc = getattr(msg, "forum_topic_created", None)
    if fc and getattr(fc, "name", None):
        return fc.name
    # 1b) сообщение о ПЕРЕИМЕНОВАНИИ темы — новое имя
    fe = getattr(msg, "forum_topic_edited", None)
    if fe and getattr(fe, "name", None):
        return fe.name
    # 2) reply на сообщение создания темы
    r = getattr(msg, "reply_to_message", None)
    if r:
        fc2 = getattr(r, "forum_topic_created", None)
        if fc2 and getattr(fc2, "name", None):
            return fc2.name
    return None


def _remember_topic_name(chat_id, topic_id, msg):
    """Запоминает название темы если оно встретилось — в память И в memory.db (write-through),
    чтобы привязка пережила рестарт."""
    name = _topic_name_from_msg(msg)
    if name and topic_id:
        _TOPIC_NAMES[(chat_id, topic_id)] = name
        if _MEMORY is not None:
            try:
                _MEMORY.set_topic_bike(chat_id, topic_id, name, source="forum_created")
            except Exception as e:
                log.warning(f"persist topic_bike error: {e}")
    return _TOPIC_NAMES.get((chat_id, topic_id))


def bike_from_topic(chat_id, topic_id):
    """Имя байка темы. Приоритет: ручной override → memory.db/кэш _TOPIC_NAMES (персист,
    seed-ится из БД при старте) → карта topics_map.json (вторичный fallback)."""
    if not topic_id:
        return ""
    ov = _TOPIC_BIKE_OVERRIDE.get((chat_id, topic_id))
    if ov:
        return ov
    # Персистентный слой: _TOPIC_NAMES seed-нут из memory.db при старте + пополняется write-through.
    cached = _TOPIC_NAMES.get((chat_id, topic_id))
    if cached:
        return cached
    # topics_map.json — вторичный fallback (только обслуживание; на сервере может отсутствовать).
    if chat_id == SERVICING_CHAT:
        mapped = _load_topic_map().get(topic_id)
        if mapped:
            return mapped
    return ""


def set_topic_bike(chat_id, topic_id, bike):
    """Ручная привязка байка к теме — override в памяти + персист в memory.db (source='manual')."""
    if topic_id and bike:
        _TOPIC_BIKE_OVERRIDE[(chat_id, topic_id)] = bike
        _TOPIC_NAMES[(chat_id, topic_id)] = bike
        if _MEMORY is not None:
            try:
                _MEMORY.set_topic_bike(chat_id, topic_id, bike, source="manual")
            except Exception as e:
                log.warning(f"persist topic_bike(manual) error: {e}")
        return True
    return False


def _remember_recent_photo(chat_id, vis, msg, topic_id=None):
    if not vis:
        return
    key = (chat_id, topic_id)   # отдельный буфер на КАЖДУЮ тему (байк), не смешиваем
    buf = _RECENT_PHOTOS.setdefault(key, deque(maxlen=_RECENT_LIMIT))
    sender = ("@" + msg.from_user.username) if (msg.from_user and msg.from_user.username) else "?"
    buf.append({"vis": vis, "sender": sender, "ts": _time.time()})


def last_mileage_in_topic(chat_id, topic_id=None, exclude_km=None):
    """Самый свежий пробег из фото ЭТОЙ темы, или None.
    Возвращает (km, confidence) где confidence 'high'/'low'/''.
    Берём даже low (лучше показать цифру с оговоркой, чем 'нет данных'),
    но приоритет — самому свежему high, если он есть в окне TTL.
    exclude_km — пропустить замеры с этим значением (чтобы при сторже пробега
    не сравнивать текущее фото само с собой: оно уже в буфере)."""
    buf = _RECENT_PHOTOS.get((chat_id, topic_id))
    if not buf:
        return None
    now = _time.time()
    try:
        _mileage_ttl_sec = float(os.environ.get("MILEAGE_TTL_DAYS", "7")) * 86400
    except (ValueError, TypeError):
        _mileage_ttl_sec = 7 * 86400
    newest_any = None   # (km, conf) — самый свежий любой
    newest_high = None  # (km, conf) — самый свежий high
    for it in reversed(buf):   # с конца — самый свежий
        _ts = it.get("ts")
        if _ts is not None and (now - _ts > _mileage_ttl_sec):
            continue
        v = it["vis"]
        km = v.get("mileage")
        if not km:
            continue
        try:
            km_int = int(str(km).replace(" ", "").replace(",", ""))
        except ValueError:
            continue
        if exclude_km is not None and km_int == exclude_km:
            continue   # это текущий замер — не сравниваем с собой
        conf = v.get("mileage_confidence", "") or ""
        if newest_any is None:
            newest_any = (km_int, conf)
        if conf == "high" and newest_high is None:
            newest_high = (km_int, conf)
            break  # самый свежий high — лучший вариант
    return newest_high or newest_any


def recent_photos_summary(chat_id, topic_id=None) -> str:
    """Сводка недавних фото ИМЕННО этой темы (байка) — для передачи мозгу."""
    buf = _RECENT_PHOTOS.get((chat_id, topic_id))
    if not buf:
        return ""
    now = _time.time()
    lines = []
    for i, it in enumerate(buf, 1):
        if now - it["ts"] > _RECENT_TTL:
            continue
        v = it["vis"]
        parts = []
        if v.get("mileage"):
            conf = v.get("mileage_confidence", "")
            parts.append(f"пробег {v['mileage']}" + (f" (уверенность {conf})" if conf else ""))
        if v.get("fuel"):
            parts.append(f"топливо {v['fuel']}")
        if v.get("tire"):
            t = v["tire"]
            if isinstance(t, dict):
                parts.append(f"шина {t.get('position') or ''} {t.get('condition') or ''} {t.get('note') or ''}".strip())
            else:
                parts.append(f"шина: {t}")
        if v.get("damage"):
            parts.append(f"повреждения: {v['damage']}")
        if v.get("kind"):
            parts.append(f"тип: {v['kind']}")
        if parts:
            lines.append(f"  фото#{i} ({it['sender']}): " + "; ".join(parts))
    if not lines:
        return ""
    return "Недавние фото в этой группе (разбор vision):\n" + "\n".join(lines)


def _parse_json(raw: str) -> dict:
    """Достаёт JSON из ответа модели (убирает ```json ограждения если есть)."""
    if not raw:
        return {}
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    # берём от первой { до последней }
    i, j = txt.find("{"), txt.rfind("}")
    if i == -1 or j == -1:
        return {}
    try:
        return json.loads(txt[i:j + 1])
    except json.JSONDecodeError:
        log.warning(f"Splinter: не смог распарсить JSON: {raw[:200]}")
        return {}


def _is_pym(msg) -> bool:
    u = msg.from_user
    if not u or not u.username:
        return False
    return u.username.lower() in PYM_USERNAMES


def _is_trusted(msg) -> bool:
    """Пым ИЛИ аккаунт владельца (Филипп) — их записи учитываем."""
    u = msg.from_user
    if not u or not u.username:
        return False
    return u.username.lower() in TRUSTED_AUTHORS


def is_owner_user(u) -> bool:
    """Владелец по id ИЛИ username (двухаккаунтный: HQ-личный 504608015 + бизнес @turbophuket1 6879003264).
    ЕДИНЫЙ гейт owner-команд — чтобы строгий «==id» не отвергал второй аккаунт. Принимает telegram.User
    (update.effective_user / msg.from_user). Узнаёт по id (OWNER_IDS) ЛИБО по username (OWNER_USERNAMES:
    HQ-личный username не имеет → ловится по id)."""
    if not u:
        return False
    if getattr(u, "id", None) in OWNER_IDS:
        return True
    return (getattr(u, "username", "") or "").lower() in OWNER_USERNAMES


def _is_owner(msg) -> bool:
    """Владелец по сообщению — делегирует в единый is_owner_user (id ИЛИ username)."""
    return is_owner_user(getattr(msg, "from_user", None))


def _intake_can_approve(msg) -> bool:
    """Может ли автор подтвердить (approve) бронь в группе intake:
    владелец + менеджеры Даня/Даша (INTAKE_APPROVERS). Пым сюда НЕ входит."""
    u = msg.from_user
    if not u or not u.username:
        return False
    return u.username.lower() in INTAKE_APPROVERS


def _bot_mentioned(msg, context) -> bool:
    t = (msg.text or msg.caption or "").lower()
    uname = ""
    try:
        uname = (context.bot.username or "").lower()
    except Exception:
        pass
    return (uname and ("@" + uname) in t) or ("turbobaby_manager_bot" in t)


def _addressed_bot(msg, context) -> bool:
    """К боту ОБРАЩАЮТСЯ: тег @bot ИЛИ реплай на сообщение бота."""
    if _bot_mentioned(msg, context):
        return True
    r = getattr(msg, "reply_to_message", None)
    fu = getattr(r, "from_user", None) if r else None
    if fu is not None:
        if getattr(fu, "is_bot", False):
            return True
        try:
            if (fu.username or "").lower() == (context.bot.username or "").lower():
                return True
        except Exception:
            pass
    return False


# Анти-спам карточки байка (пакет Б): не слать ту же карточку чаще раза в окно на тему.
_CARD_LAST = {}            # (chat_id, topic_id) -> ts последней отправленной карточки
_CARD_COOLDOWN = 180       # сек


def _is_explicit_status_query(text):
    """«Явный» короткий статус-запрос: сообщение фактически И ЕСТЬ запрос карточки
    (начинается со статус-слова / очень короткое), а не слово, утонувшее в общем трёпе."""
    t = (text or "").strip().lower()
    if len(t) > 30:
        return False
    return any(t.startswith(k) for k in _STATUS_KEYWORDS)


def _card_allowed(chat_id, topic_id):
    """Троттл+дедуп карточки: не чаще раза в _CARD_COOLDOWN на тему."""
    key = (chat_id, topic_id)
    now = _time.time()
    if now - _CARD_LAST.get(key, 0) < _CARD_COOLDOWN:
        return False
    _CARD_LAST[key] = now
    return True


# RETURN-контекст (пакет Б): сигналы возврата аренды (приоритет над ремонтом/ТО-заявкой).
_RETURN_WORDS = ("верну", "вернул", "вернулся", "возврат", "сдал", "сдаёт", "сдает",
                 "приёмк", "приемк", "забрал", "отдал", "клиент верн")

# HANDOVER-контекст (пакет «гейт выдачи»): байк ВЫДАЁТСЯ клиенту (НЕ возврат, НЕ стоянка, НЕ ремонт).
# Дешёвый гейт: event_type=="handover" ИЛИ слова выдачи. Гасит советы по уходу/стоянке и нудёж «нет фото».
_HANDOVER_WORDS = ("выда", "повезу клиент", "везу клиент", "доставлю клиент", "доставляю клиент",
                   "отвезу клиент", "клиент забира", "клиент забер", "вручаю", "передаю клиент",
                   "повёз клиент", "повез клиент", "уезжает к клиент", "уходит клиент")


def _is_handover_context(parsed, text):
    """True если байк ВЫДАЁТСЯ клиенту. Дёшево: event_type==handover ИЛИ слова выдачи в тексте.
    (CRM/Delivery-сверка — отдельный «дорогой» этап, сюда НЕ тащим.)"""
    if (parsed or {}).get("event_type") == "handover":
        return True
    blob = (text or "").lower()
    return any(w in blob for w in _HANDOVER_WORDS)


def _is_return_context(parsed, text, vis, bridge, bike):
    """True если это ВОЗВРАТ аренды (а не плановый сервис/ремонт). Дёшево сначала (event_type/слова),
    CRM-проверка статуса «В аренде» — read-only и ТОЛЬКО при handback-сигнале (damage/топливо+пробег/handover)."""
    et = (parsed or {}).get("event_type")
    if et == "return":
        return True
    blob = (text or "").lower()
    if any(w in blob for w in _RETURN_WORDS):
        return True
    # handover (выдача) УБРАН из handback — это НЕ возврат (отделён, гасится своим _ho_ctx на месте вызова).
    handback = (bool((vis or {}).get("damage"))
                or ((parsed or {}).get("fuel") and (parsed or {}).get("mileage")))
    if handback and bike:
        try:
            st = str((bridge.find_bike(bike) or {}).get("status", "")).strip().lower()
            if "аренде" in st:   # байк В АРЕНДЕ + признак сдачи → это возврат, не плановое ТО
                return True
        except Exception:
            log.exception("  → return-ctx: CRM-проверка статуса упала")
    return False


async def _download_photo(msg) -> bytes:
    """Скачивает самое крупное фото сообщения в bytes (или None)."""
    if not msg.photo:
        return None
    try:
        f = await msg.photo[-1].get_file()
        ba = await f.download_as_bytearray()
        return bytes(ba)
    except Exception as e:
        log.warning(f"Splinter: не скачал фото: {e}")
        return None


def _fmt(n) -> str:
    try:
        return f"{float(n):,.0f}".replace(",", " ")
    except (ValueError, TypeError):
        return str(n)


def _fmt_count(n):
    """Целое число (паспорта) без хвоста «.0»."""
    try:
        f = float(n)
        return str(int(f)) if f.is_integer() else str(n)
    except (ValueError, TypeError):
        return str(n)


# Единицы валют для подписи/баланса (один код на оба языка). UNKNOWN сюда не попадает —
# он перехватывается переспросом ДО записи.
_CUR_UNIT = {"THB": "฿", "EUR": "EUR", "USD": "$", "USDT": "USDT", "PASSPORT": "passport"}


def _cur_unit(currency):
    return _CUR_UNIT.get(str(currency or "THB").upper(), str(currency or "THB").upper())


def _balance_parts(bal):
    """Строки баланса кошелька, по одной валюте. THB показываем всегда (даже 0 —
    осмысленно для пустого/нового кошелька). EUR/USD/USDT и PASSPORT — только если != 0
    (нулевой остаток = шум). Без эмодзи-замены слов."""
    bal = bal or {}
    parts = [f"{_fmt(bal.get('THB', 0))} ฿"]
    for code in ("EUR", "USD", "USDT"):
        v = bal.get(code)
        if v:
            parts.append(f"{_fmt(v)} {_cur_unit(code)}")
    pas = bal.get("PASSPORT")
    if pas:  # != 0 (включая отрицательные); 0 не показываем
        parts.append(f"{_fmt_count(pas)} passport")
    return parts


def _cash_fact_on():
    """Ручка отката всего класса: `CASH_FACT=0` + рестарт splinter → путь кассы БАЙТ-В-БАЙТ прежний
    (кэш молча, расписка не читается). Читается на КАЖДЫЙ ответ, а не при импорте: иначе тест не
    смог бы доказать откат, не поднимая процесс заново."""
    return str(os.getenv("CASH_FACT", "1")).strip().lower() not in ("0", "false", "no", "off")


# ── §касса: ЧИСЛО ИЗ КЭША НЕ ВЫГЛЯДИТ КАК СВЕЖИЙ БАЛАНС (13.08.2026) ───────────────────────────
# Группа двуязычная, и решение «ждать или считать наличные руками» принимает Пым — значит слово
# «не сверено» обязано стоять на ОБОИХ языках и РЯДОМ С ЧИСЛОМ, а не только в метке блока: число
# читают первым. Дата — часть ответа: без неё «не сверено» неотличимо от «не сверено вчера».
_UNVERIFIED_HEAD = {
    "ru": "⚠️ Баланс НЕ СВЕРЕН — таблица не ответила",
    "th": "⚠️ ยอดยังไม่ได้ตรวจสอบ — ตารางไม่ตอบ",
}
_UNVERIFIED_TAIL = {
    "ru": "последнее сверенное значение, {when}",
    "th": "ยอดล่าสุดที่ตรวจสอบแล้ว {when}",
}
_UNVERIFIED_NOTIME = {"ru": "время неизвестно", "th": "ไม่ทราบเวลา"}
_UNVERIFIED_EMPTY = {
    "ru": "⚠️ Баланс НЕ СВЕРЕН — таблица не ответила, последнего значения нет",
    "th": "⚠️ ยอดยังไม่ได้ตรวจสอบ — ตารางไม่ตอบ ไม่มียอดล่าสุด",
}


def _when_utc(at):
    """Метка «когда это число было верно». None → честное «время неизвестно», а не выдумка."""
    if at is None:
        return None
    try:
        from datetime import datetime, timezone
        # Осознанно tz-aware: `utcfromtimestamp` объявлен устаревшим и шумит в боевой лог,
        # а метка обязана быть именно UTC (класс 17.07: локальные «09:xx» вместо «02:xx UTC»).
        return datetime.fromtimestamp(float(at), timezone.utc).strftime("%d.%m %H:%M UTC")
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _bal_verdict(bal):
    """Принять И вердикт, И голый dict. Голый dict = путь, где ответ моста уже потерян вызывающим,
    и назвать его иначе, чем свежим, нечем — поведение таких мест остаётся прежним байт-в-байт."""
    if isinstance(bal, balance_fact.Balance):
        return bal
    return balance_fact.Balance(balance_fact.STATE_FRESH, bal or {})


def _balance_block(label, bal, lang="ru"):
    """Баланс столбиком: строка-метка «<label>:», затем валюты с отступом 2 пробела.

    СВЕЖИЙ баланс печатается БАЙТ-В-БАЙТ как прежде. Не сверенный — под своей меткой и с пометкой
    у самого числа; сказать нечего — не печатаем числа ВОВСЕ (нуль вместо баланса врал бы громче
    молчания)."""
    v = _bal_verdict(bal)
    if v.fresh:
        return [f"{label}:", *[f"  {p}" for p in _balance_parts(v.value)]]
    lang = "th" if lang == "th" else "ru"
    if not v.shows_number:
        return [_UNVERIFIED_EMPTY[lang]]
    when = _when_utc(v.at) or _UNVERIFIED_NOTIME[lang]
    tail = _UNVERIFIED_TAIL[lang].format(when=when)
    parts = _balance_parts(v.value)
    return [_UNVERIFIED_HEAD[lang], f"  {parts[0]}  · {tail}", *[f"  {p}" for p in parts[1:]]]


# ============================================================
#  ШАБЛОНЫ (тайский + русский)
# ============================================================

def _sign(amount):
    return "+" if (amount or 0) >= 0 else "-"


def _bilingual(wallet, th_lines, ru_lines):
    """Двуязычное сообщение по правилу Филиппа: НЕ чередовать языки построчно.
    Одна шапка «🐀 Splinter · <ИмяКошелька>», затем монолитный тайский блок,
    затем монолитный русский. Флаг — отдельной строкой в начале блока.
    th_lines/ru_lines — строки контента своего языка (без флагов)."""
    head = f"🐀 Splinter · {wallet}" if wallet else "🐀 Splinter"
    return "\n".join([head, "", "🇹🇭", *th_lines, "", "🇷🇺", *ru_lines])


def _recorded_unit(amount, currency):
    """Подпись записанного движения. Печатаем РЕАЛЬНУЮ единицу валюты (฿/EUR/$/USDT/passport),
    один код для обоих языков. Раньше хардкодили ฿ для любой валюты — отсюда «+700 ฿» на доллары."""
    sign = _sign(amount)
    cur = str(currency or "THB").upper()
    if cur == "PASSPORT":
        return f"{sign}{_fmt_count(abs(amount or 0))} passport"
    return f"{sign}{_fmt(abs(amount or 0))} {_cur_unit(cur)}"


# ── §касса: «ЗАПИСАЛ» — ЭТО УТВЕРЖДЕНИЕ, И ОНО ТРЕБУЕТ РАСПИСКИ ────────────────────────────────
# Расписка потеряна → лист перечитан (`balance_fact.tx_verdict`). Строки нет — говорим прямо, что
# НЕ записали. Перечитать не удалось — говорим, что не знаем, и просим проверить ПЕРЕД повтором:
# главный риск здесь не потерянная строка, а вторая такая же, вписанная руками поверх легшей.
_TX_ABSENT = {
    "ru": "❌ НЕ записал  {rec} — строки в таблице нет, запиши вручную",
    "th": "❌ บันทึกไม่สำเร็จ  {rec} — ไม่มีในตาราง กรุณาบันทึกด้วยมือ",
}
_TX_UNKNOWN = {
    "ru": "⚠️ Записал ли  {rec} — НЕ ЗНАЮ, таблица не ответила. Проверь строку, прежде чем писать повторно",
    "th": "⚠️ ไม่ทราบว่าบันทึก  {rec} สำเร็จหรือไม่ — ตารางไม่ตอบ กรุณาตรวจก่อนบันทึกซ้ำ",
}


def _recorded_head(word, rec, tx, lang):
    """Шапка подтверждения. Расписки не спрашивали или факт доказан → прежнее слово байт-в-байт."""
    if tx is None or getattr(tx, "landed", False):
        return f"{word}  {rec}"
    if getattr(tx, "absent", False):
        return _TX_ABSENT[lang].format(rec=rec)
    return _TX_UNKNOWN[lang].format(rec=rec)


def msg_recorded_each(amount, bal, currency: str = "THB", wallet: str = "Самоорганизация", tx=None):
    """Касса (Самоорганизация): подтверждение каждой записи."""
    rec = _recorded_unit(amount, currency)
    return _bilingual(
        wallet,
        [_recorded_head("บันทึกแล้ว", rec, tx, "th"), *_balance_block("ยอดคงเหลือ", bal, "th")],
        [_recorded_head("Учтено", rec, tx, "ru"), *_balance_block("Баланс", bal)],
    )


def msg_recorded_cf(amount, bal, currency: str = "THB", wallet: str = "Money Cashflow", tx=None):
    """Money Cashflow: подтверждение записи."""
    rec = _recorded_unit(amount, currency)
    return _bilingual(
        wallet,
        [_recorded_head("บันทึกแล้ว", rec, tx, "th"), *_balance_block("ยอดคงเหลือ", bal, "th")],
        [_recorded_head("Записал", rec, tx, "ru"), *_balance_block("Баланс", bal)],
    )


def msg_topup_pettycash(amount, bal, wallet: str = "Самоорганизация", source: str = "Money Cashflow"):
    """Пополнение кассы переносом из другого кошелька (в группе Самоорганизации)."""
    a = _fmt(abs(amount or 0))
    return _bilingual(
        wallet,
        [f"เติมเงิน  +{a} ฿  (โอนมาจาก {source})", *_balance_block("ยอดคงเหลือ", bal, "th"),
         "", f"{PYM_HANDLE} ถูกต้องไหมครับ?"],
        [f"Пополнение  +{a} ฿  (перенос из {source})", *_balance_block("Баланс", bal),
         "", f"{PYM_HANDLE}, всё верно?"],
    )


def msg_reconcile(wallet, bal):
    """Периодическая сверка с Пымом — только по текущему кошельку."""
    return _bilingual(
        wallet,
        [*_balance_block("ยอดคงเหลือ", bal, "th"), "",
         f"{PYM_HANDLE} เงินสดในมือตรงกับยอดในระบบไหมครับ? มีรายการตกหล่นไหม? 🙏"],
        [*_balance_block("Баланс", bal), "",
         f"{PYM_HANDLE} наличные на руках сходятся с балансом? Ничего не упустили? 🙏"],
    )


def msg_balance_set(wallet, parts):
    rows = [f"  {p}" for p in (parts or ["0 ฿"])]
    return _bilingual(
        wallet,
        ["ตั้งยอดเริ่มต้น:", *rows, "จากนี้จะนับต่อจากยอดนี้ครับ"],
        ["Зафиксировал баланс:", *rows, "Дальше считаю отсюда"],
    )


def msg_undo(amount, description, bal, wallet: str = "Money Cashflow"):
    sign = "+" if (amount or 0) >= 0 else "-"
    a = _fmt(abs(amount or 0))
    desc = f" ({description})" if description else ""
    return _bilingual(
        wallet,
        [f"ยกเลิกรายการล่าสุดแล้ว:  {sign}{a} ฿", *_balance_block("ยอดคงเหลือ", bal, "th")],
        [f"Отменил последнюю запись:  {sign}{a} ฿{desc}", *_balance_block("Баланс", bal)],
    )


def _overview_rows(wallets):
    """Список кошельков столбиком: «• Имя:» и валюты с отступом под ним."""
    rows = []
    for name, cur in wallets.items():
        rows.append(f"• {name}:")
        rows.extend(f"    {p}" for p in _balance_parts(cur))
    return rows


def msg_balances_overview(wallets):
    """Все кошельки. Список языконезависим (имена собственные + коды валют),
    поэтому повторяем его в каждом блоке под локализованным заголовком."""
    if not wallets:
        return _bilingual(None, ["ยอดเงินทุกกระเป๋า:", "  (ว่างเปล่า)"],
                                ["Балансы кошельков:", "  (пусто)"])
    rows = _overview_rows(wallets)
    return _bilingual(None, ["ยอดเงินทุกกระเป๋า:", *rows],
                            ["Балансы кошельков:", *rows])


def msg_balance_match(cur, bal):
    return (
        f"🐀 Splinter\n"
        f"✅ ยอดตรงกัน:  {_fmt(bal)} {cur}\n"
        f"✅ Баланс сходится:  {_fmt(bal)} {cur}"
    )


def msg_balance_mismatch(cur, bot_bal, pym_bal, diff):
    return (
        f"🐀 Splinter\n"
        f"⚠️ ยอดไม่ตรงกัน / Баланс не сходится:\n"
        f"   ระบบ / у меня:    {_fmt(bot_bal)} {cur}\n"
        f"   บันทึก / записано:  {_fmt(pym_bal)} {cur}\n"
        f"   ส่วนต่าง / разница:   {_fmt(abs(diff))} {cur}\n"
        f"\n"
        f"🇹🇭 {PYM_HANDLE} ผมอาจตกหล่นรายการบางอย่าง ช่วยตรวจสอบหน่อยครับ 🙏\n"
        f"🇷🇺 {PYM_HANDLE}, возможно я пропустил запись — глянь 🙏"
    )


def msg_expense_high(category, amount, avg):
    cat_ru = {"fuel": "бензин", "taxi": "такси"}.get(category, category)
    cat_th = {"fuel": "ค่าน้ำมัน", "taxi": "ค่าแท็กซี่"}.get(category, category)
    return (
        f"🐀 Splinter\n"
        f"⛽ {cat_th}วันนี้ {_fmt(amount)} ฿  (ปกติ ~{_fmt(avg)} ฿)\n"
        f"⛽ {cat_ru.capitalize()} сегодня {_fmt(amount)} ฿  (обычно ~{_fmt(avg)} ฿)\n"
        f"\n"
        f"🇹🇭 {PYM_HANDLE} ปกติไหมครับ?\n"
        f"🇷🇺 {PYM_HANDLE}, всё ок или разберём?"
    )


def msg_photo_reminder(bike):
    b = f" {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"📸 รถคันนี้{b} ขาดรูปน้ำมันและเลขไมล์\n"
        f"📸 По байку{b} не хватает фото топлива и пробега\n"
        f"\n"
        f"🇹🇭 รบกวนทีมส่งรูปด้วยครับ {PYM_HANDLE} ช่วยดูหน่อยนะครับ 🙏\n"
        f"🇷🇺 Команда, пришлите фото. {PYM_HANDLE} проконтролируй 🙏"
    )


def msg_dirty_care(bike):
    """Мягкое сообщение когда байк грязный (НЕ повреждён). Без тега Пыма.
    Грязь у нас не штрафуется (мойка бесплатна) — просто просим привести в порядок."""
    b = f" {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🧽 รถ{b} ดูเลอะ แนะนำล้าง เคลือบแว็กซ์ แล้วคลุมผ้าด้วยครับ 🙏\n"
        f"🧽 Байк{b} грязноват — помыть, обработать воском и накрыть чехлом 🙏"
    )


# Признаки замены масла (вкл. gear oil — тот же интервал, отдельно НЕ делим).
_OIL_KEYWORDS = ("масл", "oil", "น้ำมัน", "моторн", "редуктор",
                 "เปลี่ยนน้ำมัน", "ถ่ายน้ำมัน", "gear oil")


def _is_oil_context(text, vis):
    """True если речь/фото про замену масла (по словам в тексте/подписи и vis.notes)."""
    blob = ((text or "") + " " + str((vis or {}).get("notes", ""))).lower()
    return any(kw in blob for kw in _OIL_KEYWORDS)


# Слова «замена ВЫПОЛНЕНА» (прошедшее время/факт) — НЕ будущее «надо заменить».
# Используется ТОЛЬКО как ПОДСКАЗКА (oil_hint) «стоит спросить про замену», не как решение.
# Решение всегда — явный вопрос человеку (кнопки [После замены]/[Просто пробег]).
_OIL_DONE_WORDS = ("заменил", "заменен", "заменён", "заменены", "заменено", "замена",
                   "поменял", "поменян", "готов", "сделал", "сделан",
                   "เปลี่ยนแล้ว", "แล้ว", "เสร็จ")


def _is_oil_done_marker(text, vis):
    """Подсказка: в тексте/подписи — маркер выполненной замены масла (масло-контекст И слово
    прошедшего времени). Не решает само — лишь повод задать вопрос «после замены или просто пробег?»."""
    blob = ((text or "") + " " + str((vis or {}).get("notes", ""))).lower()
    return _is_oil_context(text, vis) and any(w in blob for w in _OIL_DONE_WORDS)


def _should_ask_odometer(chat_id, topic_id, ignore_buffer=False):
    """Анти-спам для просьбы про одометр: НЕ просим если по теме уже есть уверенный (high)
    пробег в недавнем буфере, и не повторяем чаще раза в _ODOMETER_ASK_COOLDOWN.
    ignore_buffer=True — при ЯВНОМ маркере выполненной работы (доработочный замер из буфера
    НЕ считается пост-ремонтным одометром) игнорируем high-буфер, уважаем ТОЛЬКО cooldown 10 мин.
    Так чинится ложное подавление (кейс NINJA 6334 09.06: пробег сверки 71-мин давности глушил переспрос)."""
    if not ignore_buffer:
        lm = last_mileage_in_topic(chat_id, topic_id)
        if lm and lm[1] == "high":
            return False   # чёткий пробег уже получен — просить незачем
    key = (chat_id, topic_id)
    now = _time.time()
    if now - _ODOMETER_ASK_TS.get(key, 0) < _ODOMETER_ASK_COOLDOWN:
        return False   # недавно уже просили — не спамим
    _ODOMETER_ASK_TS[key] = now
    return True


def msg_ask_odometer(bike, kinds=None):
    """Просьба прислать ЧЁТКОЕ фото одометра — для привязки пробега к работам. Текст ПО ФАКТУ работ
    (kinds), БЕЗ хардкода «масло». 🇹🇭 — тайские лейблы kinds (без кириллицы), 🇷🇺 — русские.
    Без kinds → нейтрально. БЕЗ тега Пыма. Ничего в ТО не пишем — только просьба."""
    b = f" {bike}" if bike else ""
    if kinds:
        return (
            f"🐀 Splinter\n"
            f"🇹🇭 เพื่อบันทึก ({_sp_labels_th(kinds)}){b} — รบกวนถ่ายรูปเลขไมล์ (ODO) ให้ชัด ๆ หน่อยครับ 🙏\n"
            f"🇷🇺 Для записи ({_sp_labels_ru(kinds)}){b} — пришлите, пожалуйста, ЧЁТКОЕ фото пробега (одометр, ODO) 🙏"
        )
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 รบกวนถ่ายรูปเลขไมล์ (ODO){b} ให้ชัด ๆ หน่อยครับ 🙏\n"
        f"🇷🇺 Пришлите, пожалуйста, ЧЁТКОЕ фото пробега (одометр, ODO){b} 🙏"
    )


def msg_work_receipt(bike, works):
    """Квитанция на ЭТАПЕ ТЕКСТА: работы ПРИНЯТЫ (ещё в буфере, НЕ записаны) — просим пробег.
    Факт записи подтверждается ОТДЕЛЬНО (msg_works_logged) ПОСЛЕ прихода пробега, чтобы не
    выглядело «записал», когда записи ещё нет. Список работ в ОБОИХ блоках: 🇹🇭 тайские
    названия (_works_th_str, аудит row9 08.07: TH был 49 симв < 40% RU), 🇷🇺 русские."""
    b = f" {bike}" if bike else ""
    works_str = ", ".join(dict.fromkeys(str(w).strip() for w in works if str(w).strip()))
    th_str = _works_th_str(works)
    th_part = f": {th_str}" if th_str else ""
    ru_part = f": {works_str}" if works_str else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 รับงานแล้วครับ{b}{th_part} — รบกวนส่งเลขไมล์ด้วยครับ 🙏\n"
        f"🇷🇺 Принял работы{b}{ru_part} — пришли пробег 🙏"
    )


def msg_works_logged(bike, km, works):
    """Пост-квитанция ПО ФАКТУ записи инфо-работ в историю (после flush/записи с км).
    Список работ в ОБОИХ блоках (тот же класс, что row9): 🇹🇭 тайские названия
    (_works_th_str, без кириллицы; km — цифры, bike — латиница), 🇷🇺 русские."""
    b = f" {bike}" if bike else ""
    works_str = ", ".join(dict.fromkeys(str(w).strip() for w in works if str(w).strip()))
    th_str = _works_th_str(works)
    th_part = f": {th_str}" if th_str else ""
    ru_part = f": {works_str}" if works_str else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 ✅ บันทึกงานลงประวัติที่เลขไมล์ {km} กม. แล้วครับ{b}{th_part} 🛠️\n"
        f"🇷🇺 ✅ Записал работы на пробеге {km} км{b}{ru_part} 🛠️"
    )


# Словарь русских названий работ → тайские (для пословного списка в 🇹🇭-блоке, без кириллицы).
# Стартовый набор согласован с Филиппом; пополняется. Неизвестная работа → 'งานอื่น ๆ (ru)'.
_WORK_TH = {
    # ТОЧНЫЕ/частые формы (в т.ч. склонённые — works приходят из parse в разных падежах)
    "замена моторного масла": "เปลี่ยนน้ำมันเครื่อง", "моторное масло": "เปลี่ยนน้ำมันเครื่อง",
    "масляный фильтр": "ไส้กรองน้ำมันเครื่อง", "масляного фильтр": "ไส้กรองน้ำมันเครื่อง",
    "воздушный фильтр": "ไส้กรองอากาศ", "воздушного фильтр": "ไส้กรองอากาศ",
    "задние тормозные колодки": "ผ้าเบรกหลัง", "задних тормозных колодок": "ผ้าเบรกหลัง",
    "передние тормозные колодки": "ผ้าเบรกหน้า", "передних тормозных колодок": "ผ้าเบรกหน้า",
    "регулировка цепи": "ปรับโซ่", "замена цепи": "เปลี่ยนโซ่",
    "тормозная жидкость": "น้ำมันเบรก", "масло редуктора": "น้ำมันเกียร์",
    # подшипник колеса (C): передний/задний по формулировке; общий стем — ниже. ลูกปืนล้อหน้า/หลัง = подшипник пер./зад. колеса.
    "подшипник переднего колеса": "ลูกปืนล้อหน้า", "переднего подшипник": "ลูกปืนล้อหน้า",
    "передний подшипник": "ลูกปืนล้อหน้า", "подшипник переднего": "ลูกปืนล้อหน้า",
    "подшипник заднего колеса": "ลูกปืนล้อหลัง", "заднего подшипник": "ลูกปืนล้อหลัง",
    "задний подшипник": "ลูกปืนล้อหลัง", "подшипник заднего": "ลูกปืนล้อหลัง",
    # кейс 6334 (14.07): сальники вилки, задняя звезда, смазка цепи, регулировка натяжения
    "сальники вилки": "ซีลโช้คหน้า", "сальник вилки": "ซีลโช้คหน้า",
    "задняя звезда": "เฟืองโซ่หลัง", "задней звезды": "เฟืองโซ่หลัง",
    "передняя звезда": "เฟืองโซ่หน้า",
    "смазка цепи": "หล่อลื่นโซ่", "смазать цепь": "หล่อลื่นโซ่",
    "регулировка натяжения": "ปรับตึงโซ่", "регулировка натяжения цепи": "ปรับตึงโซ่",
    "натяжение цепи": "ปรับตึงโซ่",
    # СТЕМЫ (ловят любые склонения; проверяются ПОСЛЕ длинных ключей → не перебивают точные)
    "подшип": "ลูกปืน",
    "воздушн": "ไส้กรองอากาศ", "колод": "ผ้าเบรก", "цеп": "โซ่", "фильтр": "ไส้กรองน้ำมันเครื่อง",
    "свеч": "หัวเทียน", "аккумулятор": "แบตเตอรี่", "редуктор": "น้ำมันเกียร์",
    "ремень": "สายพาน", "вариатор": "ชุดสายพาน", "шин": "ยาง", "покрышк": "ยาง", "abs": "น้ำมัน ABS",
    # стемы для кейса 6334 и типовых работ
    "сальник": "ซีล", "звезд": "เฟืองโซ่", "натяжен": "ปรับตึง", "смазк": "หล่อลื่น",
}

# LLM-выученные переводы (пополняется за сессию через _learn_works_th; fail-safe = fallback ниже).
_WORK_TH_LEARNED: dict = {}

# Системный промпт для LLM-перевода неизвестных работ (один вызов на запись, fail-safe = skip).
_WORK_TH_SYSTEM = (
    "Переведи каждую работу по ТО мотоцикла на тайский язык. "
    "Ответ: СТРОГО одна строка на работу, формат «RU|TH» (русское|тайское). "
    "В TH: только тайские символы, 1–4 слова. Без кириллицы. Без пояснений."
)


def _work_th(w):
    """Тайское название работы: словарь (точное→стем) → LLM-кэш → fallback 'งานอื่น ๆ (ru)'.
    Fallback включает русский текст в скобках — механик видит ЧТО делалось, даже для неизвестных."""
    s = str(w).strip().lower()
    if s in _WORK_TH:
        return _WORK_TH[s]
    if s in _WORK_TH_LEARNED:
        return _WORK_TH_LEARNED[s]
    for k in sorted(_WORK_TH, key=len, reverse=True):
        if k in s:
            return _WORK_TH[k]
    short = str(w).strip()[:30]
    return f"งานอื่น ๆ ({short})" if short else "งานอื่น ๆ"


def _learn_works_th(claude, works):
    """Один LLM-вызов на запись: перевод работ, которых нет в словаре → _WORK_TH_LEARNED.
    Fail-safe: любая ошибка/мусор → pass (будет использован fallback 'งานอื่น ๆ (ru)')."""
    unknown = [w for w in dict.fromkeys(str(x).strip() for x in (works or []) if str(x).strip())
               if _work_th(w).startswith("งานอื่น ๆ")]
    if not unknown or not claude:
        return
    try:
        raw = (claude.quick(_WORK_TH_SYSTEM, "\n".join(unknown), max_tokens=200,
                            model="LIGHT", tag="work_th", escalate_to="MAIN") or "").strip()
        for line in raw.split("\n"):
            if "|" in line:
                ru_part, th_part = line.split("|", 1)
                ru_k = ru_part.strip().lower()
                th_v = th_part.strip()
                if ru_k and th_v and _THAI_RE.search(th_v):
                    _WORK_TH_LEARNED[ru_k] = th_v
    except Exception:
        pass


def _works_th_str(works):
    """Список работ по-тайски одной строкой для 🇹🇭-блока квитанций: _work_th на каждую.
    Дедуп ПЕРЕВОДОВ с сохранением порядка (одна и та же работа два раза → один лейбл).
    Разные работы с одним переводом (два синонима масла) → один лейбл.
    Разные неизвестные работы → разные fallback 'งานอื่น ๆ (ru1)', 'งานอื่น ๆ (ru2)' — не схлопываются."""
    return ", ".join(dict.fromkeys(_work_th(w) for w in (works or []) if str(w).strip()))


def msg_service_summary(bike, acc, skip_oil=False):
    """ЕДИНАЯ сводка в конце ТО-цикла: столбцы (масло/gear/abs/возд.фильтр) + история + пробег.
    Работы — ПО ПУНКТАМ (буллет « — »), в ОБОИХ блоках: 🇹🇭 тайские названия (_WORK_TH), 🇷🇺 русские.
    🇹🇭 ЧИСТЫЙ тайский (метки столбцов из _SVC_COL_LABEL). Секции без данных опускаем. Cyrillic в 🇹🇭 НЕТ."""
    km = acc.get("current_km") or acc.get("works_km") or (acc.get("oil") or {}).get("km") or ""
    head = f"🐀 Splinter · 📌 {bike}" if bike else "🐀 Splinter"
    # Шапка не врёт: есть непрошедшие записи → «записал НЕ всё» (класс-фикс 4957, корень 3).
    _bad = bool(acc.get("failed"))
    th = [("🇹🇭 ⚠️ บันทึกได้ไม่ครบครับ" if _bad else "🇹🇭 ✅ บันทึกครบแล้วครับ")
          + (f" — เลขไมล์ปัจจุบัน {km} กม." if km else "")]
    ru = [("🇷🇺 ⚠️ Записал НЕ всё" if _bad else "🇷🇺 ✅ Готово")
          + (f" — текущий пробег {km} км." if km else "")]
    oil = acc.get("oil")
    if oil and not skip_oil:
        nxt, st = oil.get("next"), str(oil.get("status", "ok"))
        if st in ("due", "overdue") and nxt:
            try:
                over = int(oil.get("km")) - int(nxt)
            except (ValueError, TypeError):
                over = None
            tail_th = f" เกินกำหนด {over} กม. (ครบ {nxt})" if over and over > 0 else f" ใกล้ครบ (ครบ {nxt})"
            tail_ru = f" просрочка {over} км (срок {nxt})" if over and over > 0 else f" скоро срок ({nxt})"
            th.append(f"   • เปลี่ยนน้ำมันเครื่อง:{tail_th}")
            ru.append(f"   • ТО Oil:{tail_ru}")
        else:
            th.append("   • เปลี่ยนน้ำมันเครื่อง: ปกติ" + (f" ครบกำหนดถัดไป {nxt} กม." if nxt else ""))
            ru.append("   • ТО Oil: в норме" + (f", следующее {nxt} км" if nxt else ""))
    for c in acc.get("cols", []):
        th_lbl, ru_lbl = _SVC_COL_LABEL.get(c.get("kind"), (c.get("kind"), c.get("kind")))
        nxt = c.get("next")
        th.append(f"   • {th_lbl}: {c.get('km')} กม." + (f" (ครบ {nxt})" if nxt else ""))
        ru.append(f"   • {ru_lbl}: {c.get('km')} км" + (f" (след. {nxt})" if nxt else ""))
    works = [w for w in (dict.fromkeys(str(x).strip() for x in (acc.get("works") or []))) if w]
    if works:
        wkm = acc.get("works_km", "")
        th.append("   • บันทึกลงประวัติ" + (f" (ที่ {wkm} กม.)" if wkm else "") + ": 🛠️")
        ru.append("   • В историю" + (f" (на {wkm} км)" if wkm else "") + ": 🛠️")
        for w in works:                       # КАЖДАЯ работа отдельной строкой, буллет « — »
            th.append(f"      — {_work_th(w)}")
            ru.append(f"      — {w}")
    # НЕ ЗАПИСАЛОСЬ — говорим вслух (класс-фикс 4957, корень 3). Молчаливый провал записи и был
    # тем, из-за чего «записалась одна работа из четырёх, и никто не узнал».
    failed = [f for f in (acc.get("failed") or []) if f]
    if failed:
        th.append("   • ⚠️ บันทึกไม่สำเร็จ — กรุณาบันทึกเอง:")
        ru.append("   • ⚠️ НЕ записалось (впишите вручную):")
        for w, why in failed:
            th.append(f"      — {_work_th(w)}")
            ru.append(f"      — {w} ({why})")
    return head + "\n" + "\n".join(th) + "\n" + "\n".join(ru)


# ЗАХОД 2: распознавание запроса карточки байка («инфа/статус/что по байку»).
_STATUS_KEYWORDS = ("инфа", "инфо", "инфу", "статус", "состояни", "что по байк", "что с байк",
                    "как байк", "сводка по", "карточк", "status", "info")


def _is_status_request(text):
    """Короткий свободный запрос статуса/карточки байка (не длинное сообщение о работах)."""
    t = (text or "").strip().lower()
    if not t or len(t) > 60:
        return False
    return any(k in t for k in _STATUS_KEYWORDS)


# Стабильный СТЕМ работы — единый ключ для идемпотентности записи (A1) и дедупа рендера (A2):
# «замена колодок»/«тормозные колодки»/«колодки» → один ключ «колодки». Известные работы по keyword;
# неизвестные → нормализованный текст (стабильно, но различимо).
_WORK_STEMS = (
    ("колод", "колодки"), ("тормоз", "колодки"), ("brake", "колодки"),
    ("подшип", "подшипник"), ("bearing", "подшипник"), ("ลูกปืน", "подшипник"),
    ("цеп", "цепь"), ("chain", "цепь"), ("โซ่", "цепь"),
    ("вилк", "вилка"),
    ("покрышк", "шина"), ("tyre", "шина"), ("tire", "шина"), ("ยาง", "шина"),
    ("воздушн", "воздфильтр"),
    ("редуктор", "редуктор"), ("gear", "редуктор"),
    ("фильтр", "фильтр"),
    ("моторн", "масло"), ("масл", "масло"),
    ("abs", "abs"),
)


#: ШИНА судится ГРАНИЦЕЙ СЛОВА, а не подстрокой (23.08.2026). Подстрока «шин» живёт внутри
#: «маШИНа»/«маШИНы», и простой `"шин" in s` сделал бы мойку машины заменой шины. `\bшин` этого
#: не может физически: в «машина» перед «шин» стоит буква, границы слова там нет.
#: «РЕЗИНА» — ТА ЖЕ РАБОТА, И КЛЮЧ У НЕЁ ОБЯЗАН БЫТЬ ТОТ ЖЕ (25.08.2026, разбор 5960). Механик
#: назвал работу «передняя резина», а в историю она легла словами «замена передней шины»:
#: ключи выходили `передняярезина/перед` (стема нет → нормализованный текст) против `шина/перед`,
#: и ОДНА И ТА ЖЕ работа не сходилась сама с собой ни в дедупе записи, ни в снятии с ожидания.
#: Форма узкая НАМЕРЕННО — только именные окончания: `\bрезин[аыуое]\b` берёт «резина/резины/
#: резину/резине», но не трогает «прорезиненный» (границы слова там нет) и не делает шиной
#: «резиновый коврик». Правило ОДНО на обе роли (стем ключа и вид работы): «резина» и есть шина,
#: и вид `tyre` у неё законный — он заведён решением владельца 23.08 ровно затем, чтобы шина не
#: сваливалась в «прочие работы».
_TYRE_RE = r"\bшин|покрышк|\bрезин[аыуое]\b|\btyre\b|\btire\b|ยาง"


def _work_stem(w):
    """Стабильный стем работы (ключ дедупа по контенту). Известные → канонический ключ; иначе — нормализованный текст."""
    s = str(w).lower()
    if _re_pl.search(_TYRE_RE, s):
        return "шина"
    for kw, stem in _WORK_STEMS:
        if kw in s:
            return stem
    return _re_pl.sub(r"[^0-9a-zа-яё]+", "", s) or "work"


# УТОЧНИТЕЛЬ МЕСТА работы (класс-фикс 4957, корень 3): «передние колодки» и «задние колодки» — ДВЕ
# РАЗНЫЕ работы с общим стемом. 29.07 обе получили ключ info:4957:колодки:38982 → вторая пришла
# duplicate=True и исчезла молча (splinter.log 09:32:18). Уточнитель входит в ключ, поэтому пары
# перед/зад (колодки, подшипники, шины, амортизаторы) больше не схлопываются.
# Регулярки узкие НАМЕРЕННО: «передн», а не «перед» — иначе «передача» стала бы «передней».
_WORK_QUALS = (
    ("перед", r"передн|спереди|\bfront\b|หน้า"),
    ("зад",   r"задн|сзади|\brear\b|\bback\b|หลัง"),
    ("лев",   r"левы|левог|левой|левом|слева|\bleft\b|ซ้าย"),
    ("прав",  r"правы|правог|правой|правом|справа|\bright\b|ขวา"),
)


def _work_qual(w):
    """Уточнитель места работы («перед»/«зад»/«лев»/«прав») или '' — часть контентного ключа."""
    s = str(w).lower()
    out = [q for q, rx in _WORK_QUALS if _re_pl.search(rx, s)]
    return "+".join(out)


def _work_key(w):
    """КОНТЕНТНЫЙ КЛЮЧ работы = стем + уточнитель места. Единый для идемпотентности записи (A1)
    и дедупа рендера (A2). «замена колодок»/«тормозные колодки» → один ключ (переформулировка не
    плодит строк), а «передние колодки»/«задние колодки» → РАЗНЫЕ (это разные работы)."""
    stem = _work_stem(w)
    q = _work_qual(w)
    return f"{stem}/{q}" if q else stem


def _work_keys_distinct(works):
    """Ключи для ПАРТИИ работ, гарантированно различающие РАЗНЫЕ формулировки.
    Страховка на незнакомую лексику: если два РАЗНЫХ текста работ всё же дали один ключ, обоим
    добавляется устойчивая подпись текста — лучше лишняя строка в истории, чем молча потерянная
    работа. Одинаковые тексты остаются одним ключом (идемпотентность повторного прогона цела)."""
    keys = {w: _work_key(w) for w in works}
    by_key = {}
    for w, k in keys.items():
        by_key.setdefault(k, []).append(w)
    for k, ws in by_key.items():
        if len(ws) > 1:
            for w in ws:
                sig = _hashlib.md5(_re_pl.sub(r"\s+", " ", str(w).strip().lower())
                                   .encode("utf-8")).hexdigest()[:4]
                keys[w] = f"{k}~{sig}"
            log.warning(f"  ⚠️ разные работы дали один ключ {k!r}: {ws} — развожу подписью "
                        f"(работа не должна теряться в дедупе)")
    return keys


# Инфо-работа из истории «события»: notes вида «<работа> — <км> км/กม». Отсекает шум (фото-описания,
# напоминания) — для секции «сервис на пробеге» в карточке (ЗАХОД 3).
_SVC_HIST_RE = r"^(.+?)\s*—\s*(\d+)\s*(?:км|กม)"   # _re_pl импортирован ниже — compile в рантайме


def _parse_service_items(items, limit=6):
    """Из read_events отобрать ИНФО-работы «<работа> — <км> км» → [{work, km}], newest-first, до limit.
    A2: ДЕДУП по (КЛЮЧУ работы, км) — точный повтор (та же работа на том же км) показывается ОДИН раз;
    та же работа на РАЗНЫХ км — обе (реальная история, не дубль). Ключ = стем + уточнитель места
    (класс-фикс 4957): «передние колодки» и «задние колодки» на одном км — ДВЕ строки, не одна."""
    out = []
    seen = set()
    for it in items or []:
        m = _re_pl.match(_SVC_HIST_RE, str(it.get("notes") or "").strip(), _re_pl.IGNORECASE)
        if m:
            work = m.group(1).strip(); km = m.group(2)
            key = (_work_key(work), km)
            if key not in seen:
                seen.add(key)
                out.append({"work": work, "km": km})
                if len(out) >= limit:
                    break
    return out


# Обязательные виды планового ТО (всегда показываем в карточке) — источник «последней замены» = Лист1 cols
# I/J/K/L (find_bike *_last_km). gear — только скутеры (на мото интервал None → скрываем).
_MAND_KINDS = ("oil", "gear", "abs", "airfilter")
_MAND_LABEL = {                       # kind → (🇹🇭-метка, 🇷🇺-метка) — БЕЗ декоративных эмодзи (стиль 30.06)
    "oil":       ("น้ำมันเครื่อง", "Масло"),
    "gear":      ("น้ำมันเกียร์",  "Редуктор"),
    "abs":       ("น้ำมัน ABS",   "ABS"),
    "airfilter": ("ไส้กรองอากาศ",  "Возд. фильтр"),
}
_SEP_LINE = "─────"                   # сдержанный тонкий разделитель секций


def _hb(s):
    """HTML-экранирование динамики (имена/работы могут содержать <>&) — карточка шлётся parse_mode=HTML."""
    return html.escape(str(s))


def _mand_line(kind, last, interval, cur):
    """Строка обязательного вида ТО (HTML, БЕЗ отступа — компактно): (th, ru) ИЛИ None (gear на мото). ОДИН
    статус-маркер; важное (просрочено/не делалось/остаток) — <b>. Данные те же — только формат."""
    if interval is None:
        return None
    th_lbl, ru_lbl = _MAND_LABEL.get(kind, (str(kind), str(kind)))
    try:
        last_i = int(str(last).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        last_i = 0
    if last_i <= 0:
        return (f"{th_lbl} — ❗ <b>ยังไม่เคยทำ</b>",
                f"{ru_lbl} — ❗ <b>не делалось</b>")
    nxt = last_i + int(interval)
    try:
        rem = nxt - int(str(cur).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return (f"{th_lbl} — เปลี่ยน {last_i} · ครบ {nxt} กม.",
                f"{ru_lbl} — замена {last_i} · срок {nxt} км")
    if rem > 0:
        return (f"{th_lbl} — ✅ อีก <b>{rem}</b> กม. (ครบ {nxt})",
                f"{ru_lbl} — ✅ ещё <b>{rem}</b> км (срок {nxt})")
    if rem == 0:
        return (f"{th_lbl} — ⚠️ <b>ครบกำหนดแล้ว</b> (ครบ {nxt})",
                f"{ru_lbl} — ⚠️ <b>пора сейчас</b> (срок {nxt})")
    return (f"{th_lbl} — ⚠️ <b>เกินกำหนด {abs(rem)} กม.</b>",
            f"{ru_lbl} — ⚠️ <b>просрочено на {abs(rem)} км</b>")


def _km_ago(cur, km, th):
    """Инлайн-текст скобки для истории работ: ТЕКУЩИЙ пробег (`cur` = _odo_current, ТОТ ЖЕ, что
    в шапке карточки) − пробег работы. Точный расчёт, не выдумывать.

    ЕДИНОЕ ПРАВИЛО НА ОБА ЯЗЫКА (правится здесь и только здесь — копий по языкам нет):
      d == 0  → «на текущем пробеге» / «ไมล์ปัจจุบัน»  — правда: км работы РАВЕН текущему;
      d >  0  → «N км назад» / «N กม.ที่แล้ว»;
      d <  0  → '' — МЕТКИ НЕТ ВОВСЕ (рендер не печатает и скобки);
      нечисло → «на пробеге» / «บนไมล์» — нейтральная заглушка, о факте ничего не утверждает.

    ПОЧЕМУ d < 0 молчит (класс-фикс 31.07.2026, карточка 4957): прежде ветка была `d <= 0` —
    работа ВЫШЕ текущего пробега «мягко деградировала» в «на текущем пробеге». В карточке 4957
    это дало шапку «пробег 37000 км» и рядом «38982 км (на текущем пробеге)»: 38982 ≠ 37000,
    метка врала. Невыразимое расхождение нельзя подменять утверждением о факте — честнее
    промолчать: км работы виден как есть, а сверять его с текущим владелец не обязан вслепую.
    (Само расхождение — отдельная болезнь данных; карточка её не прячет и не «залечивает».)"""
    try:
        d = int(str(cur).replace(" ", "").replace(",", "")) - int(str(km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return "บนไมล์" if th else "на пробеге"
    if d == 0:
        return "ไมล์ปัจจุบัน" if th else "на текущем пробеге"
    if d < 0:
        return ""
    return f"{d} กม.ที่แล้ว" if th else f"{d} км назад"


def msg_bike_card(bike, cur_km, mand, rental, service=None, sp_open=None, sp_last=None, unread=None):
    """КАРТОЧКА байка (HTML) — аккуратная двуязычная справка (фикс вёрстки 30.06).

    `unread` — ТРЕТИЙ ИСХОД сборки (13.08.2026): None → карточка полная и её вид БАЙТ-В-БАЙТ
    прежний; иначе {"missing": [ключи источников], "budget": сек, "spent": сек,
    "deadline_hit": bool}. Непрочитанный источник обязан НАЗВАТЬСЯ, а не оставить пустое место:
    пустая секция читается как факт о байке («ничего в работе», «сервиса не было»), а строка ТО
    без данных вообще превращается в «❗ не делалось» — ложь в обе стороны сразу (подтолкнёт к
    лишней работе там, где её делали, и успокоит там, где не делали).
    \U0001f400 имя → пустая → [\U0001f1f9\U0001f1ed блок] → пустая → _SEP (вставляет _send) → [\U0001f1f7\U0001f1fa блок].
    Каждый блок: ШАПКА (флаг + <b>пробег</b> сверху) → аренда → Плановое ТО → В работе → История.
    Секции = жирная МЕТКА + пустая строка-отступ (без ─────-линий); вид ТО на своей строке. Данные те же — только вёрстка."""
    head = f"\U0001f400 <b>{_hb(bike)}</b>" if bike else "\U0001f400 Splinter"
    _u = unread or {}
    miss = set(_u.get("missing") or ())
    _UNREAD_TH = "⚠️ <b>อ่านไม่ได้</b> (ไม่ใช่ว่าไม่มี)"
    _UNREAD_RU = "⚠️ <b>не прочитано</b> (это не «нет»)"

    def _rent(th):
        if not rental:
            return []
        state = str(rental.get("state", "")); cl = _hb(rental.get("client", ""))
        _exp = rental.get("expired"); _end = _hb(str(rental.get("end") or "").replace(" , ", ", "))
        if state.lower().startswith("в аренд"):
            if th:
                out = [f"เช่า: ลูกค้า {cl}" if cl else "เช่า: ให้เช่าอยู่"]
                if _exp: out.append(f"⚠️ <b>หมดสัญญา {_end}</b>")
            else:
                out = [f"аренда: у клиента {cl}" if cl else "аренда: у клиента"]
                if _exp: out.append(f"⚠️ <b>истекла {_end}</b>")
            return out
        if state.lower() == "дома":
            return ["เช่า: อยู่ที่ออฟฟิศ"] if th else ["аренда: дома (в офисе)"]
        if state:
            return [f"สถานะ: {_hb(state)}"] if th else [f"статус: {_hb(state)}"]
        return []

    by_kind = {m.get("kind"): m for m in (mand or [])}
    to_th, to_ru = [], []
    if "fleet" in miss:
        # Отметки ТО живут в строке байка. Строка не прочитана → `last` пуст у ВСЕХ видов, и
        # _mand_line сказал бы «❗ не делалось» про каждый — про масло, которое, возможно, меняли
        # вчера. Поэтому вместо четырёх выдуманных строк — одна честная.
        to_th, to_ru = [_UNREAD_TH], [_UNREAD_RU]
    else:
        for kind in _MAND_KINDS:
            m = by_kind.get(kind)
            if not m:
                continue
            line = _mand_line(kind, m.get("last"), m.get("interval"), cur_km)
            if line:
                to_th.append(line[0]); to_ru.append(line[1])

    work_th, work_ru = [], []
    if sp_open and (sp_open.get("kinds") or sp_open.get("works")):
        _st = str(sp_open.get("status") or ""); _odo = str(sp_open.get("odo") or "")
        _pos = sp_open.get("pos")
        if _pos is None:
            # ЛЕГАСИ-ВЫЗОВ (единый список не собрался / карточка построена не нашими руками) —
            # прежний рендер БАЙТ-В-БАЙТ: две колонки, как до 25.08.2026.
            _th_w = _sp_labels_th(sp_open.get("kinds") or [])
            _ru_w = ", ".join(_hb(w) for w in (sp_open.get("works") or [])) or _sp_labels_ru(sp_open.get("kinds") or [])
        else:
            # ОДИН СПИСОК — ОБЕ ПОЛОВИНЫ (25.08.2026). Половины различаются ТОЛЬКО языком имени:
            # слово механика есть → оно (по-тайски через словарь работ `_work_th`), слова нет →
            # ярлык вида. Длина, порядок и состав у половин общие по построению.
            _th_w = ", ".join(_work_th(p["word"]) if p.get("word")
                              else _SP_KIND_LABEL.get(p.get("kind"), (p.get("kind"), p.get("kind")))[0]
                              for p in _pos) or "—"
            _ru_w = ", ".join(_hb(p["word"]) if p.get("word")
                              else _hb(_SP_KIND_LABEL.get(p.get("kind"), (p.get("kind"), p.get("kind")))[1])
                              for p in _pos) or "—"
        work_th = [f"<b>{_th_w}</b>" + (f" · ไมล์ {_odo}" if _odo else "") + f" · {_SP_STATUS_TH.get(_st, _st)}"]
        work_ru = [f"<b>{_ru_w}</b>" + (f" · одометр {_odo}" if _odo else "") + f" · {_SP_STATUS_RU.get(_st, _st)}"]

    hist_th, hist_ru = [], []
    if sp_last and sp_last.get("done"):
        _dl_th = _sp_labels_th(sp_last["done"]); _dl_ru = _sp_labels_ru(sp_last["done"])
        _lo = str(sp_last.get("odo") or ""); _ld = str(sp_last.get("date") or "")
        hist_th.append(f"ล่าสุด: {_dl_th}" + (f" · {_lo} กม." if _lo else "") + (f" ({_ld})" if _ld else ""))
        hist_ru.append(f"Последний сервис: {_dl_ru}" + (f" · {_lo} км" if _lo else "") + (f" ({_ld})" if _ld else ""))
    # service (доп. работы на пробеге, read_events) рендерятся БЛОЧНО в _block ниже — не сплошной строкой.
    # Источник не ответил → секция ОБЯЗАНА сказать это сама: молча пустая «В работе» читается как
    # «работ нет», а пустая «История» — как «сервиса не было».
    if "service_pending_get" in miss:
        work_th, work_ru = [_UNREAD_TH], [_UNREAD_RU]
    if "service_pending_list" in miss:
        hist_th, hist_ru = [_UNREAD_TH], [_UNREAD_RU]
    # Шапка: пробега нет И источники пробега не прочитаны → «не прочитан», а не «Статус байка»
    # (последнее выглядит как «пробег неизвестен по природе», хотя он просто не доехал).
    _odo_unread = (not cur_km) and bool(miss & {"service_list", "fleet"})

    def _block(th):
        if th:
            L = ["\U0001f1f9\U0001f1ed " + (f"<b>ไมล์ {cur_km} กม.</b>" if cur_km else
                                            ("<b>⚠️ อ่านไมล์ไม่ได้</b>" if _odo_unread else "<b>สถานะรถ</b>"))]
            rl, tos, wk, hs = _rent(True), to_th, work_th, hist_th
            sec_to, sec_wk, sec_hs = "<b>เซอร์วิสตามกำหนด</b>", "<b>กำลังทำ</b>", "<b>ประวัติ</b>"
        else:
            L = ["\U0001f1f7\U0001f1fa " + (f"<b>пробег {cur_km} км</b>" if cur_km else
                                            ("<b>⚠️ пробег не прочитан</b>" if _odo_unread else "<b>Статус байка</b>"))]
            rl, tos, wk, hs = _rent(False), to_ru, work_ru, hist_ru
            sec_to, sec_wk, sec_hs = "<b>Плановое ТО</b>", "<b>В работе</b>", "<b>История</b>"
        if rl:
            L += rl
        if tos:
            L += ["", sec_to] + tos
        if wk:
            L += ["", sec_wk] + wk
        if hs:
            L += ["", sec_hs] + hs
        # П3: доп. работы на пробеге — блочно (заголовок + на работу 2 строки: «{км} км ({N км назад})» + название).
        if service:
            _hdr = "<b>ประวัติเซอร์วิสเพิ่มเติมตามไมล์:</b>" if th else "<b>Обслужено дополнительно на пробегах:</b>"
            L += ["", _hdr]
            for s in (service or []):
                _km = s.get("km"); _wk = s.get("work")
                # Скобка со сравнением — ОДНО решение на обе языковые ветки: _km_ago вернул пусто
                # (работа выше текущего пробега) → скобок нет вовсе, а не «()» и не ложная метка.
                _ago = _km_ago(cur_km, _km, th)
                _par = f" ({_ago})" if _ago else ""
                _nm = _hb(_work_th(_wk)) if th else _hb(_wk)
                L += ["", (f"{_km} กม.{_par}" if th else f"{_km} км{_par}"), _nm]
        elif "read_events" in miss:
            L += ["", ("<b>ประวัติเซอร์วิสเพิ่มเติมตามไมล์:</b>" if th
                       else "<b>Обслужено дополнительно на пробегах:</b>"),
                  (_UNREAD_TH if th else _UNREAD_RU)]
        # ТРЕТИЙ ИСХОД целиком: чего не хватило и почему. Список составляет card_deadline —
        # у него ярлыки источников на обоих языках и он не умеет ничего, кроме как их сложить.
        _blk = card_deadline.missing_block(miss, th=th, budget=_u.get("budget"),
                                           spent=_u.get("spent"),
                                           deadline_hit=bool(_u.get("deadline_hit")))
        if _blk:
            L += [""] + _blk
        return L

    out = [head, ""] + _block(True) + ["", ""] + _block(False)
    return "\n".join(out)


def _odo_km_int(x):
    """Число километров из ячейки/поля или None (пробелы и запятые живого формата — терпим)."""
    try:
        return int(str(x).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def _odo_own_freshest(rows):
    """САМАЯ СВЕЖАЯ строка СВОЕГО одометра: `(км строкой, updated_at строкой)`, иначе `('', '')`.

    ОДНО ПРАВИЛО ВЫБОРА НА ДВУХ ЧИТАТЕЛЕЙ — `_odo_current` (какое число показать/записать) и
    `_odo_known_fresh` (спрашивать ли его вообще). Две копии этого правила разошлись бы молча:
    карточка брала бы одну строку, а решение о вопросе — другую.

    Правило то же, что было в `_odo_current` до выноса: строки байка с `current_km > 0`; есть
    датированные — берём МАКСИМУМ по `updated_at` (поправка вниз обязана побеждать прежнее большее
    число); датированных нет вовсе — легаси-ветка `max` по числу, и время тогда пустое (возраст
    неизвестен → срок годности такой строке не считается)."""
    own = [(str(r.get("updated_at") or ""), _odo_km_int(r.get("current_km"))) for r in (rows or [])]
    own = [(u, km) for (u, km) in own if km and km > 0]
    if not own:
        return "", ""
    dated = [d for d in own if d[0]]
    if dated:
        at, km = max(dated, key=lambda d: d[0])
        return str(km), at
    return str(max(km for _, km in own)), ""


def _odo_fresh_ttl():
    """Окно свежести подтверждённого числа, мин. Ручка `ODO_FRESH_MIN` (.env), `0` = ветка мертва.
    Величина и её вывод из корпуса 23.08.2026 — в шапке `odo_fresh`."""
    return odo_fresh.parse_ttl(_os.getenv(odo_fresh.TTL_ENV))


def _odo_known_fresh(bridge, bike, recs=None, now_ts=None):
    """РУКИ срока годности: что бот УЖЕ знает о пробеге этого байка и не протухло ли оно.

    Решение — чистый `odo_fresh.verdict`; здесь только сбор фактов. Источник РОВНО ОДИН и тот же,
    что у `_odo_current`: СВОЙ одометр Bot Data «обслуживание» (`current_km` + `updated_at`).
    ФОЛЛБЭК Лист1 сюда НЕ входит НАМЕРЕННО: max(I/J/K/L) — это одометр НА МОМЕНТ ЗАМЕНЫ, у него нет
    времени подтверждения вовсе, и выдать его за «свежее известное число» значило бы записать
    прошлогодний пробег молча.

    Цена: одно read-only чтение `service_list` — и только в той ветке, где иначе ушёл бы ВОПРОС
    человеку (за 60 суток таких веток 38). Здоровый путь не платит ничего.
    FAIL-SAFE: мост молчит / строки нет / разбор упал → «неизвестно», то есть спрашиваем, как
    спрашивали."""
    ttl = _odo_fresh_ttl()
    if ttl <= 0:
        return odo_fresh.verdict("", "", 0, 0)
    rows = recs
    if rows is None:
        try:
            rows = [r for r in (bridge.service_list().get("items") or [])
                    if _same_bike(r.get("bike"), bike)]
        except Exception:
            log.exception("  → свежесть одометра: service_list упал (fail-safe: спрашиваем)")
            rows = []
    try:
        km, at = _odo_own_freshest(rows)
        return odo_fresh.verdict(km, at, _time.time() if now_ts is None else now_ts, ttl)
    except Exception:
        log.exception("  → свежесть одометра: разбор строк упал (fail-safe: спрашиваем)")
        return odo_fresh.verdict("", "", 0, ttl)


def _odo_current(bridge, bike, recs=None, fleet_row=None):
    """ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ по ТЕКУЩЕМУ пробегу байка (класс-фикс 4957, корень 4).

    ИСТОЧНИК = СВОЙ одометр бота: Bot Data «обслуживание».current_km. Туда — и только туда — кладёт
    подтверждённое человеком число _odo_store (см. _odo_confirmed). Из строк байка берём САМУЮ
    СВЕЖУЮ по updated_at: поправка вниз («вижу 38982» → «нет, 36982») обязана побеждать прежнее
    большее число, а max по строкам её бы похоронил.

    НЕ УЧАСТВУЮТ (в этом и была болезнь):
      • Лист1 кол.H — это пробег ПРИ ПОКУПКЕ (ReadFleet.js: «стартовый, НЕ текущий»), к сегодняшнему
        одометру отношения не имеет;
      • км из строк «события» — это СЛЕД РАБОТЫ, а не показание одометра. Именно он держал 38982
        поверх живых 37000 (Лист1 I16) и 36982 (кол.J) двое суток: одна ошибочная строка истории
        назначала себя «текущим пробегом» навсегда.

    ФОЛЛБЭК (только если своего одометра ещё нет): max(I/J/K/L) — это одометр НА МОМЕНТ ЗАМЕНЫ,
    то есть реальное показание. Нет и его → '' (честное «не знаю», карточка покажет «Статус байка»).
    Легаси-строки без updated_at → max по current_km (прежнее поведение, ничего не ломаем)."""
    rows = recs
    if rows is None:
        try:
            rows = [r for r in (bridge.service_list().get("items") or [])
                    if _same_bike(r.get("bike"), bike)]
        except Exception:
            log.exception("  → одометр: service_list упал (иду в фоллбэк Лист1)")
            rows = []
    km, _at = _odo_own_freshest(rows)
    if km:
        return km
    fb = fleet_row if fleet_row is not None else (bridge.find_bike(bike) or {})
    last = [_odo_km_int((fb or {}).get(f"{k}_last_km")) for k in _MAND_KINDS]
    last = [x for x in last if x and x > 0]
    return str(max(last)) if last else ""


def _info_card_budget():
    """Бюджет одной сборки карточки, сек. Ручка `INFO_CARD_BUDGET_SEC` (.env), `0` = дедлайна нет.
    Величина и её вывод из замера 13.08.2026 — в шапке `card_deadline`."""
    return card_deadline.parse_budget(_os.getenv(card_deadline.BUDGET_ENV))


def _build_bike_card(bridge, chat_id, topic_id, bike):
    """Собрать ТЕКСТ карточки байка из ЧИТАЕМЫХ источников (find_bike + service_list + read_events).
    Ничего не пишет и не отправляет — только строит строку. Разделён с отправкой, чтобы инфо-кнопка могла
    показать loading-заглушку и заменить её editMessageText (П4). Все Bridge-вызовы синхронны → def, не async.

    ОБЩИЙ ДЕДЛАЙН (13.08.2026): вся сборка идёт внутри ОДНОГО бюджета `bridge_client.card_budget`.
    Потолок стоит на КАРТОЧКЕ, а не на плече: три вложенные лестницы повторов (полные попытки ×
    хопы редиректа × попытки эхо-слоя = 57 плеч на действие) остаются, но исчерпать бюджет целиком
    больше не могут — исчерпавшись, он гасит оставшиеся действия ДО сети. Что не успело прочитаться,
    карточка называет вслух (`unread`), а не показывает пустым местом."""
    _budget = _info_card_budget()
    with bridge_client.card_budget(_budget) as _cb:
        _text = _build_bike_card_body(bridge, chat_id, topic_id, bike, _cb)
    return _text


def _build_bike_card_body(bridge, chat_id, topic_id, bike, _cb=None):
    """Тело сборки карточки (см. `_build_bike_card` — там открывается общий бюджет)."""
    fb = bridge.find_bike(bike) or {}
    canon = fb.get("name") or bike
    try:
        recs = [r for r in (bridge.service_list().get("items", []) or []) if _same_bike(r.get("bike"), bike)]
    except Exception:
        recs = []

    # ЗАХОД 3: сервис-на-пробеге — 6 последних инфо-работ из истории «события» (read_events).
    # ЭТО ИСТОРИЯ, А НЕ ОДОМЕТР: в расчёт текущего пробега их км больше НЕ входит (корень 4).
    service = []
    try:
        ev = bridge.read_events(canon, limit=6)
        service = _parse_service_items(ev.get("items", []), limit=6)
    except Exception:
        log.exception("  → read_events для карточки упал")
    # Текущий пробег — ИЗ ОДНОГО ИСТОЧНИКА (_odo_current, класс-фикс 4957 корень 4), а не max по
    # разнородной куче. Прежний max(колH, обслуживание, км работ) держал ошибочные 38982 из строки
    # «события» поверх живых 37000/36982 — след работы назначал себя одометром. Расхождение
    # «работа выше текущего» (баг 5849) лечится не подтягиванием шапки вверх, а тем, что каждое
    # подтверждённое число теперь попадает в сам источник (_odo_store); рендер такой строки
    # МОЛЧИТ — _km_ago не даёт метки вовсе (фикс 31.07.2026: прежнее «мягкое» «на текущем пробеге»
    # было ложью — в карточке 4957 стояло «38982 км (на текущем пробеге)» при шапке 37000).
    cur_km = _odo_current(bridge, bike, recs=recs, fleet_row=fb)
    # ПЛАНОВОЕ ТО — 4 ОБЯЗАТЕЛЬНЫХ вида из Лист1 (cols I/J/K/L = *_last_km), интервал из книги знаний.
    # Показываем ВСЕГДА (где нет записи → «не делалось»); gear на мото → interval None → скрыт в рендере.
    mand = [{"kind": k, "last": fb.get(f"{k}_last_km"), "interval": _service_interval(k, canon, bridge)}
            for k in _MAND_KINDS]
    rental = None
    if fb.get("status"):
        _end = (fb.get("current_rental") or {}).get("end_date", "")
        rental = {"state": fb.get("status"), "client": (fb.get("current_rental") or {}).get("client", ""),
                  "expired": _rental_expired(fb.get("status"), _end), "end": _end}   # Z3
    # Z1: то_заявки — ОТКРЫТАЯ (в работе) + последняя ЗАКРЫТАЯ (последний сервис). read-only, мягко (методов может не быть в моках).
    sp_open = None; sp_last = None
    try:
        _g = bridge.service_pending_get(chat_id, topic_id, bike)
        _it = _g.get("item") if _g.get("ok") else None
        if _it and str(_it.get("status")) not in ("закрыто", ""):
            sp_open = {"kinds": (_sp_split(_it.get("declared")) or _sp_split(_it.get("done"))),
                       "works": _sp_works_from_note(_it.get("note")),
                       "odo": str(_it.get("odometer") or ""), "status": str(_it.get("status") or "")}
            # ОДИН ИСТОЧНИК НА ОБЕ ПОЛОВИНЫ + СНЯТИЕ ЗАПИСАННОГО (25.08.2026, разбор 5960).
            # До этого тайская половина рендерила `kinds`, а русская — `works`, то есть ДВЕ
            # РАЗНЫЕ колонки одной строки заявки, и совпадали они ровно тогда, когда механик
            # работ словами не называл. Теперь список ОДИН (`pos`), обе половины рендерят его.
            # ФАКТЫ УЖЕ НА РУКАХ — ни одного лишнего обращения к мосту: регистры это `fb`
            # (строка парка, прочитана выше ради планового ТО), история это `service`
            # (`read_events`, прочитан выше ради секции «сервис на пробеге»). Источник НЕ
            # прочитан → `None`, и позиция остаётся ВИДИМОЙ с исходом «неизвестно»: незнание
            # мира снимать работу с ожидания не вправе.
            try:
                _miss_now = set(_cb.missing()) if _cb is not None else set()
                _regs = None if "fleet" in _miss_now else {
                    k: fb.get(f"{k}_last_km") for k in _SP_COL_KINDS}
                _hist = None if "read_events" in _miss_now else service
                _res = card_works.pending(
                    sp_open["kinds"], sp_open["works"], kind_of=_service_kind, key_of=_work_key,
                    col_kinds=_SP_COL_KINDS, registers=_regs, history=_hist, odo=sp_open["odo"])
                sp_open["pos"] = _res["show"]
                if _res["gone"]:
                    log.info("  → " + card_works.line(_res))
            except Exception:
                # Решение споткнулось → рендер идёт ПРЕЖНИМ путём (две колонки), то есть не
                # хуже, чем было до правки: `pos` просто не появляется.
                log.exception("  → карточка: единый список «в работе» не собрался — прежний рендер")
    except Exception:
        log.exception("  → карточка: чтение открытой то_заявки упало")
    try:
        _closed = [r for r in (bridge.service_pending_list(status="закрыто").get("items") or [])
                   if _same_bike(r.get("bike"), bike)]
        _closed.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
        if _closed:
            _c0 = _closed[0]
            # E3(e): валидируем kind перед показом — НЕ показываем невалидный «масляный фильтр» (filter)
            # и НЕ дублируем регламент (oil/gear/abs/airfilter — у них свои секции выше). Улику не правим.
            _done_last = [k for k in _sp_split(_c0.get("done")) if k not in _SP_COL_KINDS and k != "filter"]
            if _done_last:
                sp_last = {"done": _done_last, "odo": str(_c0.get("odometer") or ""),
                           "date": str(_c0.get("updated_at") or "")[:10]}
    except Exception:
        log.exception("  → карточка: чтение закрытых то_заявки упало")
    unread = None
    if _cb is not None:
        _missing = _cb.missing()
        if _missing:
            unread = {"missing": _missing, "budget": _cb.budget,
                      "spent": _cb.spent(_time.monotonic()), "deadline_hit": _cb.deadline_hit}
            log.warning(f"  → карточка {canon}: источники не прочитаны {_missing} "
                        f"(бюджет {_cb.budget} с, дедлайн исчерпан: {_cb.deadline_hit})")
    return msg_bike_card(canon, cur_km, mand, rental, service, sp_open=sp_open, sp_last=sp_last,
                         unread=unread)


async def _send_bike_card(context, bridge, chat_id, topic_id, bike):
    """Собрать карточку (см. _build_bike_card) и отправить (bilingual → _with_separator, parse_mode=HTML)."""
    await _send(context, chat_id=chat_id, message_thread_id=topic_id, parse_mode="HTML",
                text=_build_bike_card(bridge, chat_id, topic_id, bike))


def _write_info_works(bridge, group_name, topic_id, bike, info_works, km, msg_id_base, msg_date="",
                      chat_id=None, failed_out=None, sender=""):
    """Вариант A (разбор перечня по адресам): КАЖДУЮ инфо-работу — отдельной строкой в «события»
    с привязкой пробега. msg_id = info:{plate}:{стем-работы}:{км} (КОНТЕНТНЫЙ ключ) → повторный прогон той
    же работы на том же км дедупится Bridge'ом. Колоночные работы сюда НЕ попадают — у них свой адрес.
    chat_id — только для журнала отката (_km_event_journal); на саму запись не влияет."""
    grp = group_name + (f" / тема {topic_id}" if topic_id else "")
    plate = _plate_from_name(bike) or "?"
    uniq = list(dict.fromkeys(info_works))
    keys = _work_keys_distinct(uniq)
    written, mids, failed = [], [], []
    for w in uniq:
        note = (f"{w} — {km} км" if km else f"{w}")[:200]
        # A1 ИДЕМПОТЕНТНОСТЬ по КОНТЕНТУ: msg_id = info:{plate}:{ключ-работы}:{км}. Повторный прогон/повторное
        # фото на ту же работу+км даёт ТОТ ЖЕ ключ → Bridge.addEvent дедупит (botMsgExists_ по msg_id, BotData.js).
        # msg_id_base (per-сообщение) больше НЕ используем — он плодил новое событие на каждый прогон.
        mid = f"info:{plate}:{keys.get(w) or _work_key(w)}:{km or '-'}"
        try:
            # `sender` дописывается ТОЛЬКО когда он назван: пустой не передаётся вовсе, поэтому
            # дверь буфера (она зовёт без него) остаётся байт-в-байт прежней.
            # `msg_id=` остаётся ЯВНЫМ аргументом, а через `**` едет только необязательный
            # `sender`: страж `tests/test_event_key.py` считает ЖИВЫЕ вызовы с явным ключом
            # (`explicit >= 6`) — свернуть ключ в словарь значило бы спрятать его от стража,
            # то есть ослабить проверку, не ослабив инварианта. Лечится путём, а не правкой теста.
            _extra = {"sender": str(sender)} if sender else {}
            r = bridge.add_event(msg_date=msg_date, group=grp, bike=bike, event_type="repair",
                                 fuel="", mileage=str(km or ""), photos=0, notes=note,
                                 msg_id=mid, **_extra) or {}
        except Exception:
            log.exception(f"  → инфо-работа «{note}»: add_event упал")
            r = {"ok": False, "error": "exception"}
        _ok, _dup = bool(r.get("ok")), bool(r.get("duplicate"))
        log.info(f"  → инфо-работа в историю: «{note}» msg_id={mid} add_event ok={r.get('ok')} "
                 f"saved={r.get('saved')} dup={r.get('duplicate')}")
        # ЧЕСТНЫЙ УЧЁТ (класс-фикс 4957, корень 3): раньше сюда попадала ЛЮБАЯ работа независимо от
        # ответа Bridge — отказ и схлопнутый дубль выглядели как «записано». Теперь в истории считается
        # то, что там реально есть: ok+saved (новая строка) ИЛИ duplicate (строка уже была). Отказ —
        # это ПОТЕРЯ, и она называется вслух (сводка + WARNING), а не молчит.
        if _ok and not _dup:
            written.append(w); mids.append(mid)
        elif _dup:
            written.append(w)
            log.warning(f"  → инфо-работа «{note}» уже была в истории (ключ {mid}) — новой строки нет")
        else:
            failed.append((w, str(r.get("error") or "нет ответа Bridge")))
            log.error(f"  ⚠️ инфо-работа НЕ записана: «{note}» ключ={mid} ошибка={r.get('error')!r}")
    if failed:
        _summary_note_failed(chat_id, topic_id, failed)
    if failed_out is not None:
        # Сторожу партии нужна ПРИЧИНА, а не только факт «в написанных нет»: список отказов
        # уезжает наружу тем же составом, каким лёг в накопитель сводки.
        failed_out.extend(failed)
    _km_event_journal(chat_id, topic_id, km, ids=mids, works=written, bike=bike,
                      group=group_name, msg_date=msg_date)
    return written   # список работ, которые РЕАЛЬНО есть в истории (для пост-квитанции по факту)


def _pw_slot(w):
    """Ключ ПОЗИЦИИ БУФЕРА = нормализованный ТЕКСТ работы (регистр и пробелы не считаются).

    ПОЧЕМУ НЕ КОНТЕНТНЫЙ КЛЮЧ `_work_key`, хотя он и стоит рядом. `_work_key` — СТЕМ, он
    намеренно грубый и склеивает РАЗНЫЕ работы: у «долив тормозной жидкости», «полная замена
    тормозной жидкости», «прокачка тормозов» и «прокачка тормозной системы» стем ОДИН —
    `колодки`. Сама запись это переживает, потому что `_write_info_works` разводит совпавшие
    стемы подписью текста (`_work_keys_distinct`), — а дедуп буфера разводить нечем: он не
    пишет, он ВЫБРАСЫВАЕТ. Возьми буфер стем — и вторая партия 01.08 («полная замена тормозной
    жидкости», «прокачка тормозов») схлопнулась бы в уже лежащий «долив тормозной жидкости»,
    то есть две названные работы исчезли бы МОЛЧА и сторож партии их даже не увидел бы: они не
    были бы ПРИНЯТЫ. Это ровно тот класс, ради которого заход и делается, только с другой
    стороны. Поэтому здесь дедупится ПОВТОР ТЕХ ЖЕ СЛОВ, и ничего кроме.

    НАПРАВЛЕНИЕ СОМНЕНИЯ — В СОХРАНЕНИЕ ПОЗИЦИИ, и цена названа: переформулировка («передняя
    шина» → «замена передней шины», у них и стемы разные) остаётся ДВУМЯ позициями и даёт две
    строки в истории. Лишняя строка видна человеку и стоит секунды; проглоченная работа — это
    невыполненное ТО живого байка. Тот же выбор уже сделан у `_work_keys_distinct` дословно:
    «лучше лишняя строка в истории, чем молча потерянная работа»."""
    return _re_pl.sub(r"\s+", " ", str(w or "").strip().lower())


def _pw_add(chat_id, topic_id, works, bike, msg_id_base):
    """ДОПИСАТЬ работы в буфер темы (а не заместить его). Возвращает актуальный перечень буфера.

    Класс 22.08.2026: присваивание по ключу темы стирало предыдущую партию МОЛЧА — 01.08 в
    05:53:50 отложено четыре работы, в 07:31:02 в ту же ячейку легло три, и «долив тормозной
    жидкости» исчез без единой строки. Дедуп идёт по ПОВТОРУ ТЕХ ЖЕ СЛОВ (`_pw_slot`, см. там
    почему не стем). У каждой позиции свой возраст: срок годности старой не убивает свежую."""
    key = (chat_id, topic_id)
    cur = _PENDING_WORKS.get(key) or {}
    names = list(cur.get("works") or [])
    at = dict(cur.get("at") or {})
    now = _time.time()
    seen = {_pw_slot(w) for w in names}
    again = []
    for w in (works or []):
        k = _pw_slot(w)
        if not k or k in seen:
            again.append(w)
            continue
        seen.add(k)
        names.append(w)
        at[k] = now
    _PENDING_WORKS[key] = {"works": names, "at": at, "bike": bike or cur.get("bike", ""),
                           "msg_id_base": msg_id_base or cur.get("msg_id_base", ""), "ts": now}
    if again:
        log.info(f"  → инфо-работы: те же слова уже в буфере, не дублирую: {again} (тема {topic_id})")
    return names


def _pw_take(chat_id, topic_id):
    """Забрать буфер темы РАЗ И НАВСЕГДА, разделив его на СВЕЖИЕ и ПРОТУХШИЕ позиции.
    Возвращает (fresh:list, stale:list, bike, msg_id_base). Буфера нет → ([], [], "", "")."""
    pend = _PENDING_WORKS.pop((chat_id, topic_id), None)
    if not pend:
        return [], [], "", ""
    at = pend.get("at") or {}
    now, ttl = _time.time(), _PENDING_WORKS_TTL
    born = pend.get("ts", 0)
    fresh, stale = [], []
    for w in (pend.get("works") or []):
        ts = at.get(_pw_slot(w), born)      # легаси-буфер (до 22.08) возраста позиций не знает
        (stale if now - ts > ttl else fresh).append(w)
    return fresh, stale, pend.get("bike", ""), pend.get("msg_id_base", "")


def _flush_pending_works(bridge, chat_id, topic_id, group_name, bike, km, msg_date="", lost_out=None):
    """Пришёл чёткий пробег в теме → дописать ОТЛОЖЕННЫЕ инфо-работы (буфер темы) с этим км.
    Забор буфера = ровно один раз (без задвоения). Протухшие (> TTL) позиции не пишем, но и молча
    не теряем — называем вслух. Возвращает СПИСОК записанных работ (для пост-квитанции) или [].
    `lost_out` — сюда сторож партии забирает (работа, причина) по каждой НЕ легшей позиции."""
    fresh, stale, pend_bike, msg_id_base = _pw_take(chat_id, topic_id)
    if stale:
        # Протухший буфер = ПОТЕРЯ работ, а не рутина: называем её вслух (класс-фикс 4957, корень 3).
        log.error(f"  ⚠️ отложенные инфо-работы протухли (>{_PENDING_WORKS_TTL//3600}ч), НЕ записаны: {stale}")
        _summary_note_failed(chat_id, topic_id, [(w, f"пробег так и не пришёл за {_PENDING_WORKS_TTL//3600}ч")
                                                 for w in stale])
        if lost_out is not None:
            lost_out.extend((w, "no_km", "") for w in stale)
    if not fresh:
        return []
    _failed = []
    written = _write_info_works(bridge, group_name, topic_id, bike or pend_bike,
                                fresh, km, msg_id_base, msg_date, chat_id=chat_id,
                                failed_out=_failed)
    if lost_out is not None:
        lost_out.extend((w, "write_failed", str(why or "")) for w, why in _failed)
    return written


def _km_door(bridge, chat_id, topic_id, bike, km, *, source, msg_date="", lost_out=None):
    """ЕДИНАЯ ДВЕРЬ ВЫГРУЗКИ БУФЕРА: любой ПОДТВЕРЖДЁННЫЙ пробег дописывает отложенные работы.

    Класс 22.08.2026 (разбор 5960): выгрузка висела на дверях подтверждения пробега — кнопке и
    числу в самом сообщении, — а фаза 2 берёт одометр СВОИМ разбором (`splinter.py`, ветка
    `handle_service_result`) и буфера не касалась вовсе. Из-за этого 01.08 и 22.08 разошлись на
    ровном месте: 22.08 число пришло кнопкой → работы легли, 01.08 то же число `41357` пришло
    текстом → четыре работы остались в буфере и не легли никуда. Дверей у пробега три (текст,
    кнопка, фаза 2), логика выгрузки — ОДНА, и живёт она здесь; каждая дверь только зовёт её и
    сама решает, что делать с записанным (накопитель сводки, квитанция).

    Возвращает (written:list, lost:list[(работа, код причины, хвост)]). Без моста писать некуда —
    буфер НЕ трогаем (забрали бы работы в пустоту), но и не молчим о них."""
    if not bridge:
        peek = list((_PENDING_WORKS.get((chat_id, topic_id)) or {}).get("works") or [])
        if peek:
            log.error(f"  ⚠️ дозапись отложенных работ невозможна (моста нет), в буфере остались: {peek}")
            # Единственная дорога потери, у которой до этой строки был ТОЛЬКО лог, — а логов из
            # команды не читает никто (класс-фикс 4957, корень 3). Двери 1 и 3 квитанции не
            # печатают вовсе: их единственный видимый след — сводка, значит потеря обязана
            # называться ИМЕННО там, иначе «моста нет» снова стало бы тишиной.
            _summary_note_failed(chat_id, topic_id,
                                 [(w, "писать было некуда — буфер не выгружен") for w in peek])
            if lost_out is not None:
                lost_out.extend((w, "no_bridge", "") for w in peek)
            return [], [(w, "no_bridge", "") for w in peek]
        return [], []
    lost = [] if lost_out is None else lost_out
    written = []
    try:
        written = _flush_pending_works(bridge, chat_id, topic_id, group_label(chat_id),
                                       bike, str(km), msg_date, lost_out=lost)
    except Exception:
        log.exception("  → дозапись отложенных инфо-работ подтверждённым пробегом упала")
    if written:
        log.info(f"  → инфо-работы дописаны ПОДТВЕРЖДЁННЫМ пробегом {km}: {written} (source={source})")
        _sp_note_settle_works(bridge, chat_id, topic_id, bike, written)
    return written, list(lost)


def _sp_note_settle_works(bridge, chat_id, topic_id, bike, written):
    """ЗАПИСАННОЕ СНИМАЕТСЯ С ОЖИДАНИЯ (25.08.2026, разбор 5960 §3.2).

    Писавшая дверь о заявке НЕ ЗНАЛА: `_write_info_works` зовёт `add_event` и не касается
    `service_pending_*` ни одним вызовом — поэтому 25.08 колодки и шина легли в историю на 41666,
    а в «в работе» висели дальше. Единая дверь пробега (`_km_door`) знает, что РЕАЛЬНО легло
    (`written` — там только `ok+saved` либо `duplicate`), значит снятие живёт здесь, и оно одно
    на все три двери подтверждённого пробега.

    ЦЕНА НАЗВАНА: одно чтение заявки, и ТОЛЬКО когда что-то действительно записано (за 60 суток
    таких дверей 38). Снимать нечего → мосту не пишем вовсе — ни одного обращения.

    FAIL-SAFE: заявки нет · мост молчит · разбор споткнулся → нота остаётся как была. Карточка от
    этого не соврёт: она судит мир САМА (`card_works`), а нота — вторая, не единственная опора."""
    try:
        sp = _sp_open(bridge, chat_id, topic_id, bike)
        if not sp:
            return
        base = str(sp.get("note") or "")
        fresh = _sp_note_drop_works(base, written)
        if fresh == base:
            return
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                      bike=bike, note=fresh)
        log.info(f"  → «в работе» {bike}: снято записанное {written} → note={fresh!r}")
    except Exception:
        log.exception("  → снятие записанных работ с ожидания упало (нота осталась прежней)")


# ============================================================
#  ПУТЬ ПОДТВЕРЖДЕНИЯ ОДОМЕТРА — ОДНО ПРАВИЛО НА ВСЕ ВЕТКИ ЗАПИСИ
#  (класс-фикс 31.07.2026 по разбору инцидента NMAX 155 GREEN-B 4957, тема 79, 29.07.2026)
#
#  Что было: гейт сырого OCR (06c1ab2) закрыл ТОЛЬКО ветку ОБЫЧНОГО события. Ветка ИНФО-работ
#  писала vision-км как есть → в историю байка легло «замена передних тормозных колодок — 38982 км»
#  (splinter.log 09:32:16), хотя человек тут же поправил число на 36982. Классическая зеркальная
#  дыра: закрыли одну ветку — через пять дней вылезла вторая. Поэтому правило ОДНО и живёт в
#  ОДНОМ месте (_km_for_record), а не двумя копиями гейта по коду.
# ============================================================

def _msg_date_of(msg):
    """Дата сообщения строкой YYYY-MM-DD (или '') — для дозаписи работ тем же днём."""
    try:
        d = getattr(msg, "date", None)
        return str(d.date()) if d else ""
    except Exception:
        return ""


def _km_for_record(parsed, vis):
    """ЕДИНОЕ ПРАВИЛО: в ЗАПИСЬ (лист «события» — и обычное событие, и инфо-работы) идёт ТОЛЬКО
    ЧЕЛОВЕЧЕСКОЕ число, то есть пробег из ТЕКСТА сообщения (parsed.mileage). Сырой OCR
    (vis.mileage) до подтверждения человеком не пишется НИ ПО ОДНОМУ пути.
    vis принимается аргументом намеренно: чтобы место решения было видно и никто не «дочинил»
    ветку мимо этой функции. Подтверждённое фото-число приходит в запись не отсюда, а с пути
    подтверждения: _ask_mileage_confirm → handle_mileage_confirm / кнопка → _odo_confirmed."""
    return str((parsed or {}).get("mileage") or "")


# Журнал СВОИХ строк «события» с привязкой к пробегу — материал для отката.
# Ключ (chat_id, topic_id) → {"km", "ts", "ids", "works", "plain", "bike", "group", "date"}.
# Держим только последний записанный км темы и только в окне: откат бьёт по ТОЧНЫМ msg_id.
_KM_EVENTS_WRITTEN = {}
_KM_EVENTS_TTL = 3 * 3600


def _km_event_journal(chat_id, topic_id, km, *, ids=(), works=(), plain=(),
                      bike="", group="", msg_date=""):
    """Запомнить, что мы записали в «события» с этим пробегом (для возможного отката).
    Fail-safe: нет chat_id/км/содержимого → ничего не пишем, вызывающего не роняем."""
    try:
        if chat_id is None or not str(km or "").strip() or not (ids or plain):
            return
        key = (chat_id, topic_id)
        rec = _KM_EVENTS_WRITTEN.get(key)
        if not rec or str(rec.get("km")) != str(km):
            rec = {"km": str(km), "ts": _time.time(), "ids": [], "works": [], "plain": [],
                   "bike": bike, "group": group, "date": msg_date}
            _KM_EVENTS_WRITTEN[key] = rec
        rec["ts"] = _time.time()
        rec["bike"] = rec.get("bike") or bike
        rec["group"] = rec.get("group") or group
        rec["date"] = rec.get("date") or msg_date
        for i in ids:
            if i and i not in rec["ids"]:
                rec["ids"].append(i)
        for w in works:
            if w and w not in rec["works"]:
                rec["works"].append(w)
        for p in plain:
            if p:
                rec["plain"].append(dict(p))
                mid = str(p.get("msg_id") or "")
                if mid and mid not in rec["ids"]:
                    rec["ids"].append(mid)
    except Exception:
        log.exception("  → журнал записанных км: сбой (fail-safe, откат просто не сработает)")


def _rollback_km_events(bridge, chat_id, topic_id, *, wrong_km, right_km, sender="?", source=""):
    """СТРАХОВКА: человек назвал ДРУГОЕ число, а строки с прежним уже легли в «события» →
    удаляем СВОИ строки по ТОЧНЫМ msg_id и переписываем их верным числом. Раньше отката не было
    НИ В ОДНОЙ ветке: ошибочный км оставался в истории байка навсегда, поправка правила только
    служебную запись обслуживания.
    Узко и обратимо: (1) удаляем только то, что записали САМИ (ключи `info:…` / `{chat_id}:…`),
    (2) только по журналу этой темы и только если журнал именно про WRONG_KM (растущий одометр
    и чужие строки не трогаем), (3) только в окне _KM_EVENTS_TTL, (4) на стороне Bridge
    deleteEvent сам отказывает на широком фильтре.
    Возвращает {"deleted", "rewritten", "skip"} — для лога и тестов. Fail-safe: любая неготовность
    (нет bridge/журнала/метода delete_event, то же число, протухло) = ноль действий."""
    key = (chat_id, topic_id)
    try:
        if not bridge:
            return {"deleted": 0, "rewritten": [], "skip": "no_bridge"}
        if str(wrong_km or "") == str(right_km or "") or not str(right_km or "").strip():
            return {"deleted": 0, "rewritten": [], "skip": "same_km"}
        rec = _KM_EVENTS_WRITTEN.get(key)
        if not rec or str(rec.get("km")) != str(wrong_km):
            return {"deleted": 0, "rewritten": [], "skip": "no_journal"}
        if _time.time() - rec.get("ts", 0) > _KM_EVENTS_TTL:
            _KM_EVENTS_WRITTEN.pop(key, None)
            return {"deleted": 0, "rewritten": [], "skip": "stale"}
        if not callable(getattr(bridge, "delete_event", None)):
            return {"deleted": 0, "rewritten": [], "skip": "no_delete_api"}
        _KM_EVENTS_WRITTEN.pop(key, None)
        own = (f"{chat_id}:", "info:")
        deleted = 0
        for mid in rec.get("ids", []):
            if not str(mid).startswith(own):
                log.warning(f"  → откат км: ключ {mid!r} не наш — пропускаю (чужие строки не трогаем)")
                continue
            try:
                r = bridge.delete_event(msg_id=str(mid)) or {}
                deleted += int(r.get("deleted") or 0)
                log.info(f"  → откат км: delete_event msg_id={mid} ok={r.get('ok')} "
                         f"deleted={r.get('deleted')} error={r.get('error')}")
            except Exception:
                log.exception(f"  → откат км: delete_event({mid}) упал")
        rewritten = []
        if rec.get("works"):
            rewritten = _write_info_works(bridge, rec.get("group") or group_label(chat_id), topic_id,
                                          rec.get("bike") or "", rec["works"], str(right_km), "",
                                          rec.get("date") or "", chat_id=chat_id)
        for p in rec.get("plain", []):
            try:
                kw = dict(p)
                kw["mileage"] = str(right_km)
                bridge.add_event(**kw)
                rewritten.append(str(kw.get("msg_id") or ""))
            except Exception:
                log.exception("  → откат км: перезапись обычного события упала")
        _odo_audit_write(bridge, chat_id, topic_id, rec.get("bike") or "", right_km, wrong_km,
                         sender=sender, outcome=f"откат записей ({deleted} стр.) → {right_km}")
        log.info(f"  ↩️ откат км {wrong_km}→{right_km} тема={topic_id}: удалено {deleted} строк, "
                 f"переписано {len(rewritten)} (source={source})")
        return {"deleted": deleted, "rewritten": rewritten, "skip": ""}
    except Exception:
        log.exception("  → откат записанных км упал (fail-safe: ничего не меняем)")
        return {"deleted": 0, "rewritten": [], "skip": "exception"}


def _odo_store(bridge, chat_id, topic_id, bike, km):
    """Подтверждённое человеком число → В ИСТОЧНИК ПРАВДЫ (класс-фикс 4957, корень 4).

    Раньше подтверждённый пробег оседал в ЛЕТУЧЕМ накопителе сводки (_SVC_SUMMARY: 3 часа в памяти,
    умирает с рестартом) и доезжал до «обслуживание» только если поток дошёл до _after_mileage —
    а ветка B1 (открытая то_заявка «ждёт_факт») уводит в ранний return раньше. Отсюда и жили ДВА
    пробега параллельно: свой одометр отставал, а карточка добирала недостающее из чего попало.
    Теперь запись в свой одометр — часть самого подтверждения, а не побочный эффект ветки.

    Bot Data «обслуживание» = СВОЯ таблица бота (🟢). Лист1/CRM тут не трогаются вовсе.
    Fail-safe: нет bridge/байка/числа или Bridge сбоит → лог, путь подтверждения не рвётся."""
    km_int = _odo_km_int(km)
    if not bridge or not bike or not km_int or km_int <= 0:
        return False
    try:
        r = bridge.service_upsert(bike=bike, topic_id=topic_id or "",
                                  service_type="oil", current_km=km_int) or {}
        log.info(f"  → одометр {bike} = {km_int} (подтверждено человеком) → обслуживание "
                 f"ok={r.get('ok')} status={r.get('status')}")
        return bool(r.get("ok"))
    except Exception:
        log.exception("  → запись подтверждённого одометра в «обслуживание» упала (fail-safe)")
        return False


def _odo_confirmed(bridge, chat_id, topic_id, bike, km, *, questioned_km=None,
                   sender="?", source="", msg_date=""):
    """ЕДИНАЯ ТОЧКА «человек подтвердил/назвал пробег». Зовётся ИЗ ВСЕХ путей подтверждения
    (текст handle_mileage_confirm — обычный и мягкий гейт, кнопка svc:mok, кнопка svc:sodo),
    чтобы правило жило в одном месте, а не копиями по веткам.
    Делает ровно две вещи, которых раньше не было ни в одной ветке:
      1) ОТКАТ — если человек назвал ЧИСЛО, ОТЛИЧНОЕ от того, о котором спрашивали (поправка
         «36982» на вопрос «вижу 38982»), а строки с прежним числом уже записаны — они снимаются
         и переписываются верным числом (_rollback_km_events);
      2) ДОЗАПИСЬ — отложенные инфо-работы (буфер _PENDING_WORKS) дописываются ПОДТВЕРЖДЁННЫМ
         числом. До этого фикса они писались сырым OCR прямо в момент фото; теперь гейт
         _km_for_record их придерживает — и без этой дозаписи работы бы тихо протухли.
    Возвращает список дописанных работ. Fail-safe: любое исключение логируется, путь
    подтверждения не рвётся."""
    if questioned_km is not None:
        _rollback_km_events(bridge, chat_id, topic_id, wrong_km=str(questioned_km),
                            right_km=str(km), sender=sender, source=source or "confirm")
    # 3) ОДОМЕТР — в источник правды СРАЗУ, до любых веток и ранних return (корень 4).
    _odo_store(bridge, chat_id, topic_id, bike, km)
    # ДВЕРЬ 1 и 2 (текст/кнопка подтверждения). Логика выгрузки — одна на все три двери (`_km_door`);
    # без bridge писать некуда — буфер там НЕ трогается (забрали бы работы в пустоту).
    written, _ = _km_door(bridge, chat_id, topic_id, bike, km, source=source or "confirm",
                          msg_date=msg_date)
    if written:
        try:
            acc = _summary_acc(chat_id, topic_id)
            acc["works"] += written
            acc["works_km"] = str(km)
            acc["current_km"] = str(km)
        except Exception:
            log.exception("  → накопитель сводки на дозаписи работ сбоил (не критично)")
    return written


# ============================================================
#  ОБРАБОТЧИКИ ПО РЕЖИМАМ
# ============================================================

# === §12: молчаливых потерь LLM больше НЕТ — единый обработчик upstream-down ==================
# Раньше: money-сообщение → quick() upstream упал → '' → parse {} → type=None → тихо потеряно.
# Теперь: quick(raise_on_upstream=True) бросает SplinterLLMError → сюда. Критерий пуша (Поправка Б
# штаба): касается ДЕНЕГ (money-чат/перевод/депозит/чек-с-суммой) → ГРОМКИЙ пуш «впиши руками»;
# НЕ деньги (фото-байк/ask/judge слепнет) → лог + тихий счётчик, БЕЗ пуша.
# Дедуп (Поправка А штаба): при длящемся обвале первый пуш в окне ГРОМКИЙ, дальше СХЛОПКА
# «ещё N потерялось за окно» — владельца не спамим по одному.
_LLM_LOSS_WINDOW = 600          # окно схлопки громких пушей, сек (~10 мин)
_llm_loss = {"loud_ts": 0.0, "collapsed": 0, "quiet": 0}


def _note_llm_loss(*, money, wallet="", lost_text="", detail="", kind="") -> bool:
    """LLM upstream упал на разборе — фиксируем, чтобы операция не пропала тихо.
    money=True → громкий пуш владельцу (с дедупом за окно); money=False → лог + тихий счётчик.
    Возврат: был ли отправлен громкий пуш (для тестов/диагностики)."""
    if not money:
        _llm_loss["quiet"] += 1
        log.error(f"  → LLM upstream down (НЕ-деньги, лог без пуша): kind={kind} {detail}")
        return False
    log.error(f"  → LLM upstream down на ДЕНЬГАХ: wallet={wallet} kind={kind} "
              f"lost={lost_text[:120]!r} {detail}")
    now = _time.time()
    if now - _llm_loss["loud_ts"] > _LLM_LOSS_WINDOW:
        # новый эпизод/окно → ГРОМКИЙ пуш (+ хвост схлопнутых за прошлое окно, если были)
        extra = ""
        if _llm_loss["collapsed"] > 0:
            extra = f"\n(+ ещё {_llm_loss['collapsed']} операц. потерялось в прошлом окне)"
        _llm_loss["loud_ts"] = now
        _llm_loss["collapsed"] = 0
        try:
            import notify
            notify.notify(
                "⚠️ ОПЕРАЦИЯ ПОТЕРЯЛАСЬ (LLM upstream упал)\n"
                f"Кошелёк: {wallet or '?'}\n"
                f"Впиши руками: {lost_text or '(текст недоступен)'}" + extra,
                force=True)   # боевой алерт кассы — тест-мут не глушит
        except Exception:
            log.exception("  → пуш о потере money упал")
        return True
    # в окне — СХЛОПКА: копим счётчик, владельца не спамим
    _llm_loss["collapsed"] += 1
    log.warning(f"  → потеря money схлопнута в окне ({_llm_loss['collapsed']} за окно) — пуш не шлём")
    return False


async def _handle_money(msg, context, bridge, claude):
    """Money Cashflow / Самоорганизация — считаем, сверяем с Пымом."""
    # Записи учитываем от Пыма ИЛИ от аккаунта владельца (Филипп). Остальных читаем, но не как проводки.
    if not _is_trusted(msg):
        log.info(f"  → skipped: не доверенный автор @{msg.from_user.username if msg.from_user else '?'}")
        return

    text = msg.text or msg.caption or ""
    if not text.strip():
        log.info(f"  → skipped: пустой текст (есть фото? {bool(msg.photo)})")
        return

    # Перехват ответа на переспрос валюты (фикс валюты): если для кошелька открыт pending — резолвим.
    if pending_currency_for(msg.chat_id, getattr(msg, "message_thread_id", None)):
        if await handle_currency_confirm(msg, context, bridge, claude, text):
            return

    chat_id = msg.chat_id
    wallet = group_label(chat_id)

    # §12: разбор кассы — raise_on_upstream=True. UPSTREAM упал (кредит/Auth/timeout/CLI) →
    # SplinterLLMError → громкий пуш «впиши руками» + ответ в чат, проводка НЕ теряется тихо.
    # ЧЕСТНЫЙ type:none (модель ответила) — сюда НЕ попадает, идёт штатно (тихо, как раньше).
    try:
        raw = claude.quick(MONEY_SYSTEM, text, max_tokens=400, raise_on_upstream=True,
                          model="HEAVY", tag="money")
    except SplinterLLMError as e:
        _note_llm_loss(money=True, wallet=wallet, lost_text=text, detail=str(e), kind="money")
        try:
            await _send(context, chat_id=chat_id,
                        text=("🐀 Splinter\n⚠️ Не смог обработать сейчас (LLM временно недоступен). "
                              "Запись НЕ потеряна — впиши вручную или повтори, когда восстановится."),
                        bilingual=False)
        except Exception:
            log.exception("  → money loss: ответ в чат упал")
        return

    parsed = _parse_json(raw)
    ptype = parsed.get("type")
    log.info(f"  → parsed type={ptype} transfer={parsed.get('transfer_to_pettycash')}")

    if ptype == "transaction":
        moves = parsed.get("moves") or []
        if not moves:
            log.info("  → skipped: transaction без moves")
            return
        # Нет валюты в тексте = баты (правильный дефолт, БЕЗ переспроса). Нормализуем null/пусто → THB.
        for m in moves:
            if not m.get("currency"):
                m["currency"] = "THB"
        log.info(f"  → moves={[(m.get('amount'), m.get('currency')) for m in moves]}")

        # Валюта НАЗВАНА, но непонятна (UNKNOWN) → НЕ пишем вслепую, переспрашиваем.
        if any(str(m.get("currency")).upper() == "UNKNOWN" for m in moves):
            await _ask_currency(context, bridge, claude, msg, parsed, wallet)
            return

        # РАЗДЕЛ B: фото-хинт валюты. Vision ПРЕДЛАГАЕТ валюту по фото; при РАСХОЖДЕНИИ с текстом
        # (текст = баты, а на фото уверенно инвалюта) — переспрос (НЕ запись вслепую). Vision = слабый хинт.
        money_move = next((m for m in moves if m.get("currency") != "PASSPORT"), None)
        receipt = None
        if msg.photo and money_move:
            receipt = await _vision_receipt(claude, msg)
            hint = (receipt or {}).get("currency")
            hconf = str((receipt or {}).get("currency_confidence", "")).lower()
            if (hint and str(hint).upper() in ("USD", "USDT", "EUR") and hconf == "high"
                    and str(money_move.get("currency")).upper() == "THB"):
                await _ask_currency(context, bridge, claude, msg, parsed, wallet,
                                    suggested=str(hint).upper())
                return

        await _record_transaction(context, bridge, claude, msg, parsed, wallet, receipt=receipt)

    elif ptype == "balance_check":
        bal = parsed.get("balance", {}) or {}
        pym_thb = bal.get("THB")
        if pym_thb is None:
            return
        res = bridge.check_balance(currency="THB", pym_balance=pym_thb, group=wallet, note=wallet)
        _entry_counts[chat_id] = 0
        if res.get("match"):
            await _send(context, chat_id=chat_id, text=msg_balance_match("฿", res.get("bot_balance")))
        elif res.get("match") is False:
            await _send(context, 
                chat_id=chat_id,
                text=msg_balance_mismatch("฿", res.get("bot_balance"), pym_thb, res.get("diff", 0)),
            )

    elif ptype == "balance_set":
        # Установить/зафиксировать баланс кошелька (стартовый или правка) — приоритет владельцу
        target = parsed.get("balance", {}) or {}
        cur_bal = wallet_cache.get_balance_with_fallback(
            wallet, bridge.get_balance(group=wallet).get("balance", {}))
        parts = []
        for cur in ("THB", "EUR", "PASSPORT"):
            tgt = target.get(cur)
            if tgt is None:
                continue
            now_v = cur_bal.get(cur, 0)
            adj = round(float(tgt) - float(now_v), 2)
            if abs(adj) > 0.001:
                bridge.add_transaction(
                    msg_date=str(msg.date.date()) if msg.date else "",
                    group=wallet,
                    sender="@" + (msg.from_user.username or "") + " (фиксация)",
                    amount=adj, currency=cur, category="adjustment",
                    bike="", deposit="",
                    description=f"фиксация баланса до {tgt} {cur}",
                    raw=text, msg_id=f"{chat_id}:{msg.message_id}:set:{cur}",
                )
        # якорь сохраняем в кэш сразу (target — намерение владельца; Bridge мог записать с задержкой)
        anchor_cache = {k: float(v) for k, v in target.items() if v is not None}
        if anchor_cache:
            wallet_cache.save_wallet_balance(wallet, anchor_cache)
            parts = [f"{_fmt(v)} {k}" for k, v in target.items() if v is not None]
        else:
            parts = []
        await _send(context, chat_id=chat_id, text=msg_balance_set(wallet, parts))
        _entry_counts[chat_id] = 0

    elif ptype == "question":
        # Отвечаем балансом ТОЛЬКО этого кошелька (не палим другие кошельки).
        # Прямой вопрос «сколько в кассе?» — тот же класс: молчащий мост давал здесь «0 ฿»,
        # то есть НОЛЬ вместо баланса, и кэша у этой ветки не было вовсе.
        this_bal = (wallet_cache.answer(wallet, bridge.get_balance(group=wallet))
                    if _cash_fact_on() else
                    bridge.get_balance(group=wallet).get("balance", {}))
        await _send(context,
            chat_id=chat_id,
            text=_bilingual(wallet, _balance_block("ยอดคงเหลือ", this_bal, "th"),
                            _balance_block("Баланс", this_bal)),
        )

    elif ptype == "undo":
        # Отмена последней записи ИМЕННО этого кошелька
        res = bridge.void_last(group=wallet)
        log.info(f"  → undo: {res}")
        if res.get("voided"):
            await _send(context, 
                chat_id=chat_id,
                text=msg_undo(res.get("amount", 0), res.get("description", ""), res.get("balance", {}), wallet=wallet),
            )
        else:
            await _send(context,
                chat_id=chat_id,
                text=_bilingual(wallet, ["ไม่มีรายการให้ยกเลิกครับ"],
                                ["Нечего отменять — активных записей нет."]),
            )

    else:
        # type "none": если ВЛАДЕЛЕЦ явно тегнул бота — не молчим, уточняем у него
        if _is_owner(msg) and _bot_mentioned(msg, context):
            await _send(context, 
                chat_id=chat_id,
                text=("🐀 Splinter\n"
                      "Не совсем понял, Фил 🙏 Я умею:\n"
                      "• проводка — «-500 бензин», «+4900 аренда ADV 8004»\n"
                      "• перенос — «-1000 в самоорганизацию»\n"
                      "• сверить баланс — «Balance 5715 Bath 150 Euro 1 Passport»\n"
                      "• зафиксировать баланс — то же + «зафиксируй»\n"
                      "• спросить — «какой баланс?»"),
            )


# === Фикс валюты: USD/USDT + переспрос на названную-но-непонятную валюту + фото-хинт ===
# Нет валюты в тексте = баты (дефолт, без переспроса). Названа явно → пишем её. Названа, но
# непонятна (UNKNOWN) ИЛИ фото уверенно противоречит тексту → переспрос, запись только после ответа.
_PENDING_CURRENCY = {}     # (chat_id, topic_id) -> {"parsed":dict, "wallet":str, "ts":float}
_PENDING_CUR_TTL = 3600
# ответ человека на «в какой валюте?» → код валюты
_CUR_WORDS = {
    "thb": "THB", "฿": "THB", "baht": "THB", "bath": "THB", "бат": "THB", "บาท": "THB",
    "eur": "EUR", "euro": "EUR", "евро": "EUR", "€": "EUR",
    "usd": "USD", "dollar": "USD", "доллар": "USD", "$": "USD", "бакс": "USD",
    "usdt": "USDT", "tether": "USDT", "юсдт": "USDT", "тезер": "USDT",
}


def pending_currency_for(chat_id, topic_id):
    """Есть ли открытый переспрос валюты для кошелька (с авто-протуханием по TTL)."""
    p = _PENDING_CURRENCY.get((chat_id, topic_id))
    if p and _time.time() - p.get("ts", 0) > _PENDING_CUR_TTL:
        _PENDING_CURRENCY.pop((chat_id, topic_id), None)
        return None
    return p


def _currency_from_reply(text):
    """Ответ человека → код валюты (THB/EUR/USD/USDT) или None если валюта не распознана."""
    t = (" " + (text or "").strip().lower() + " ")
    for w, code in _CUR_WORDS.items():
        if w in t:
            return code
    return None


async def _vision_receipt(claude, msg):
    """Разбор фото (чек/купюры) через vision → dict {amount, currency, currency_confidence,...} или None."""
    img = await _download_photo(msg)
    if not img:
        return None
    try:
        return _parse_json(claude.vision(VISION_RECEIPT_SYSTEM, img, max_tokens=300))
    except Exception:
        return None


async def _ask_currency(context, bridge, claude, msg, parsed, wallet, suggested=""):
    """Переспрос валюты (НЕ записываем): кладём parsed в pending, шлём двуязычный вопрос."""
    chat_id = msg.chat_id
    topic = getattr(msg, "message_thread_id", None)
    mv = next((m for m in (parsed.get("moves") or []) if m.get("currency") != "PASSPORT"), None)
    amt = abs(mv.get("amount", 0)) if mv else 0
    _PENDING_CURRENCY[(chat_id, topic)] = {"parsed": parsed, "wallet": wallet, "ts": _time.time()}
    mark_awaiting(chat_id, topic)
    sug_th = f" (น่าจะ {suggested}?)" if suggested else ""
    sug_ru = f" (похоже {suggested}?)" if suggested else ""
    await _send(context, chat_id=chat_id, message_thread_id=topic,
                text=(f"🐀 Splinter\n"
                      f"🇹🇭 💱 จำนวน {_fmt(amt)} เป็นสกุลเงินอะไรครับ{sug_th}? พิมพ์ THB / USD / EUR / USDT 🙏\n"
                      f"{_SEP}\n"
                      f"🇷🇺 💱 Сумма {_fmt(amt)} — в какой валюте{sug_ru}? Напиши THB / USD / EUR / USDT 🙏"))
    log.info(f"  → переспрос валюты (сумма {amt}, hint='{suggested}')")


async def handle_currency_confirm(msg, context, bridge, claude, text) -> bool:
    """Перехват ответа на переспрос валюты. True если обработал (валюта распознана → запись)."""
    chat_id = msg.chat_id
    topic = getattr(msg, "message_thread_id", None)
    pend = _PENDING_CURRENCY.get((chat_id, topic))
    if not pend:
        return False
    code = _currency_from_reply(text)
    if not code:
        return False                      # не валюта — отдаём обычному пути (человек уточнит/новое сообщение)
    _PENDING_CURRENCY.pop((chat_id, topic), None)
    clear_awaiting(chat_id, topic)
    parsed = pend["parsed"]
    # Проставляем подтверждённую валюту на денежные движения (UNKNOWN/THB-дефолт), паспорт не трогаем.
    for m in (parsed.get("moves") or []):
        if m.get("currency") != "PASSPORT":
            m["currency"] = code
    await _record_transaction(context, bridge, claude, msg, parsed, pend["wallet"])
    log.info(f"  → валюта подтверждена: {code} → запись")
    return True


# === O3-3c часть Б: привязка deposit-прихода Money к брони по байку ===
# Money-парсер клиента НЕ знает (deposit=passport/cash + bike из текста) — мост к брони строим
# по байку: приоритет — intake-окно после «✅ Бронь записана», иначе read-only резолв по CRM.
_DEPOSIT_LINK_WINDOW = 1800   # 30 мин intake-окна
_RECENT_BOOKINGS = {}         # plate -> {"booking_id", "row", "ts"} — брони, созданные intake


def _deposit_resolve_booking(bridge, bike):
    """Бронь для deposit-прихода по байку (READ-ONLY). Приоритет: intake-окно 30 мин после
    «✅ Бронь записана» по тому же байку (CRM не читаем). Иначе CRM: строки Бронь/В аренде по
    номеру байка — РОВНО одна и с booking_id (col Y) → линк; ноль/несколько/без uuid/сбой →
    None (запись как сейчас + подсказка «уточни бронь» у вызывателя).
    → {"booking_id", "row"} | None."""
    plate = plateFromName_(bike or "")
    if not plate:
        return None
    rec = _RECENT_BOOKINGS.get(plate)
    if rec and rec.get("booking_id") and _time.time() - rec.get("ts", 0) <= _DEPOSIT_LINK_WINDOW:
        return {"booking_id": str(rec["booking_id"]), "row": rec.get("row")}
    try:
        cl = bridge._call("clients", filter="all").get("data", {})
        rows = cl.get("clients", []) if isinstance(cl, dict) else (cl or [])
    except Exception:
        return None
    cand = [c for c in rows if plateFromName_(str(c.get("bike", ""))) == plate
            and str(c.get("status", "")).strip().lower() in ("бронь", "в аренде")]
    if len(cand) != 1 or not str(cand[0].get("booking_id") or "").strip():
        return None
    return {"booking_id": str(cand[0]["booking_id"]).strip(), "row": cand[0].get("row")}


async def _record_transaction(context, bridge, claude, msg, parsed, wallet, receipt=None):
    """Запись проводок + сверка чека + перенос в кассу + подтверждение. Валюта уже разрешена
    (THB по умолчанию / явная / подтверждённая). receipt — предзагруженный разбор фото (без 2-го vision)."""
    chat_id = msg.chat_id
    text = msg.text or msg.caption or ""
    moves = parsed.get("moves") or []
    # deposit-ПРИХОД (deposit=passport/cash на плюсовом движении) → пробуем привязать к брони.
    # Возвраты депозита (минус) не трогаем — на возврате бронь уже «Завершена», подсказка спамила бы.
    dep_move = next((m for m in moves if m.get("deposit") and (m.get("amount") or 0) > 0), None)
    dep_link = _deposit_resolve_booking(bridge, dep_move.get("bike")) if dep_move else None
    tx_facts = {}          # id(move) → balance_fact.TxFact; пусто = расписки в порядке
    lost = []              # движения, чья расписка потеряна: их факт перечитываем ИЗ ЛИСТА
    for i, mv in enumerate(moves):
        r = bridge.add_transaction(
            msg_date=str(msg.date.date()) if msg.date else "",
            group=wallet,
            sender="@" + (msg.from_user.username or ""),
            amount=mv.get("amount", 0),
            currency=(mv.get("currency") or "THB"),
            category=mv.get("category", "other"),
            bike=mv.get("bike") or "",
            deposit=mv.get("deposit") or "",
            description=text[:200],
            raw=text,
            msg_id=f"{chat_id}:{msg.message_id}:m{i}",
            booking_id=(dep_link["booking_id"] if (dep_link and mv is dep_move) else ""),
        )
        # РАСПИСКА ПРОВОДКИ ЧИТАЕТСЯ (13.08.2026). Писчее плечо пересылок не имеет намеренно и при
        # молчании транспорта отдаёт «исход неизвестен: перечитай факт» — прежде это требование
        # было адресовано некому: возврат не присваивался вовсе, и 13.08 проводка ушла в HTTP 302
        # молча. Решение «перечитывать ли» берётся готовым у write_fact (форма _claim_task_verified).
        if _cash_fact_on() and balance_fact.needs_verify(r):
            lost.append(mv)
            log.warning(f"  → касса: расписка проводки {mv.get('amount')} "
                        f"{mv.get('currency')} потеряна ({(r or {}).get('error')}) — перечитаю лист")
    if lost:
        # ОДНО чтение на сообщение, а не на движение: лист у всех движений один и тот же.
        # Здоровый путь сюда не заходит вовсе — цена платится только больным мостом.
        summary = bridge.tx_summary(period="today")
        for mv in lost:
            sig = balance_fact.signature(mv.get("amount", 0), mv.get("currency") or "THB",
                                         mv.get("category", "other"), mv.get("bike") or "")
            fact = balance_fact.tx_verdict(sig, summary)
            tx_facts[id(mv)] = fact
            log.warning(f"  → касса: {fact.say()}")

    money_move = next((m for m in moves if m.get("currency") != "PASSPORT"), None)
    money_amount = money_move.get("amount", 0) if money_move else 0
    money_currency = (money_move.get("currency") or "THB") if money_move else "THB"
    passport_move = next((m for m in moves if m.get("currency") == "PASSPORT"), None)
    display_move = money_move or passport_move
    disp_amount = display_move.get("amount", 0) if display_move else money_amount
    disp_currency = (display_move.get("currency") or "THB") if display_move else money_currency

    # Сверка суммы чека (если фото). Ярлык — реальная единица валюты движения.
    if msg.photo and money_move:
        rec = receipt if receipt is not None else await _vision_receipt(claude, msg)
        ramount = (rec or {}).get("amount")
        wamount = abs(money_amount or 0)
        try:
            mismatch = ramount and abs(abs(float(ramount)) - wamount) >= 1
        except (ValueError, TypeError):
            mismatch = False
        if mismatch:
            u = _cur_unit(money_currency)
            await _send(context, chat_id=chat_id,
                        text=(f"🐀 Splinter\n"
                              f"🧾 {PYM_HANDLE} ในใบเสร็จ {_fmt(ramount)} {u} แต่เขียนไว้ {_fmt(wamount)} {u} "
                              f"ต่างกันนะครับ ตรวจหน่อย 🙏\n"
                              f"🧾 {PYM_HANDLE}, на чеке {_fmt(ramount)} {u}, а записано {_fmt(wamount)} {u} — "
                              f"не сходится, глянь пожалуйста 🙏"))

    # БАЛАНС СУДИТСЯ ПО ЦЕЛОМУ ОТВЕТУ МОСТА, А НЕ ПО ИСТИННОСТИ СЛОВАРЯ (13.08.2026): `ok` с пустым
    # балансом — честный ноль пустого кошелька, а молчание моста обязано звучать «не сверено».
    wallet_bal = (wallet_cache.answer(wallet, bridge.get_balance(group=wallet))
                  if _cash_fact_on() else
                  wallet_cache.get_balance_with_fallback(
                      wallet, bridge.get_balance(group=wallet).get("balance", {})))

    # === Перенос в мелкую кассу === (только денежное движение, паспорт не переносим)
    is_transfer = parsed.get("transfer_to_pettycash") and money_move and chat_id != PETTYCASH_CHAT_ID
    if is_transfer:
        plus = abs(money_amount or 0)
        bridge.add_transaction(
            msg_date=str(msg.date.date()) if msg.date else "",
            group=PETTYCASH_LABEL,
            sender="@" + (msg.from_user.username or "") + " (авто-перенос)",
            amount=plus,
            currency=money_currency,
            category="topup",
            bike="", deposit="",
            description=f"пополнение переносом из {wallet}",
            raw=text,
            msg_id=f"{chat_id}:{msg.message_id}:topup",
        )
        pc_bal = (wallet_cache.answer(PETTYCASH_LABEL, bridge.get_balance(group=PETTYCASH_LABEL))
                  if _cash_fact_on() else
                  bridge.get_balance(group=PETTYCASH_LABEL).get("balance", {}))
        await _send(context, chat_id=PETTYCASH_CHAT_ID,
                    text=msg_topup_pettycash(plus, pc_bal, wallet=PETTYCASH_LABEL, source=wallet))

    # === Подтверждение записи ===
    # O3-3c часть Б: итог привязки депозита строкой в подтверждении (линк или «уточни бронь»)
    link_note = ""
    if dep_move and dep_link:
        link_note = f"\n🔗 привязано к брони строка {dep_link.get('row') or '—'}"
        log.info(f"  → депозит {dep_move.get('bike')}: привязан к брони "
                 f"строка {dep_link.get('row')} ({dep_link['booking_id'][:12]}…)")
    elif dep_move:
        link_note = "\n⚠️ депозит: бронь по байку не определил — уточни бронь"
        log.info(f"  → депозит {dep_move.get('bike') or '—'}: бронь не определена (0/несколько)")
    # Показываем факт ТОГО движения, которое и названо в подтверждении.
    disp_tx = tx_facts.get(id(display_move)) if display_move is not None else None
    _entry_counts[chat_id] = _entry_counts.get(chat_id, 0) + 1
    if chat_id in MONEY_CONFIRM_EACH:
        await _send_retry(context, chat_id=chat_id,
                          text=msg_recorded_each(disp_amount, wallet_bal, disp_currency,
                                                 wallet=wallet, tx=disp_tx) + link_note)
        _entry_counts[chat_id] = 0
    else:
        await _send_retry(context, chat_id=chat_id,
                          text=msg_recorded_cf(disp_amount, wallet_bal, disp_currency,
                                               wallet=wallet, tx=disp_tx) + link_note)
        if _entry_counts[chat_id] >= RECONCILE_EVERY:
            await _send_retry(context, chat_id=chat_id, text=msg_reconcile(wallet, wallet_bal))
            _entry_counts[chat_id] = 0


# === Фикс B: подтверждение пробега с ФОТО приборки перед решением по ТО ===
# vision врёт на LCD → распознанную цифру подтверждаем у человека, потом _after_mileage.
# Значение: (mileage:str, bike:str, floor:int|None, oil_hint:bool, ts:float) — ts добавлен
# класс-фиксом 4957 (корень 5). Легаси-кортежи без ts читаются как «без метки» → считаются свежими.
_PENDING_MILEAGE = {}   # (chat_id, topic_id) -> (mileage, bike, floor, oil_hint, ts)
# ПРЕДЕЛ ЖИЗНИ ВОПРОСА О ПРОБЕГЕ (класс-фикс 4957, корень 5): вопрос, заданный 29.07 в 09:32,
# провисел в памяти 46 часов и 31.07 в 07:29 UTC МОЛЧА съел сообщение владельца — в splinter.log
# нет даже строки «Splinter [servicing] …», перехват случился раньше неё. Ровно 3 часа, как у
# буфера отложенных работ (_PENDING_WORKS_TTL): они живут одной парой «работы ждут пробега».
_PENDING_MILEAGE_TTL = 3 * 3600
_CONFIRM_YES = {"да", "ага", "верно", "ок", "окей", "yes", "ใช่", "ถูก", "ถูกต้อง", "ถูกต้องครับ"}
_CONFIRM_NO = {"нет", "не", "no", "ไม่", "ไม่ใช่"}

# === Фикс _row22: текстовая КОРРЕКЦИЯ пробега после уже сделанной записи ===
# Кейс: vision/«да» записали неверный пробег (напр. 39374 вместо 33974), человек поправляет
# ТЕКСТОМ «не верно пробег 33974». Раньше это уходило в мозг (болтал, не переписывал), а правка
# ВНИЗ упёрлась бы в монотонного сторожа B. Решение: ловим коррекцию → переспрос → ТОЛЬКО по «да»
# перезаписываем service_upsert(new) В ОБХОД сторожа B (санкционированная человеком правка вниз).
# Сторож B для ФОТО НЕ ослабляется — обход живёт только на этом подтверждённом текстовом пути.
_LAST_RECORDED_KM = {}    # (chat_id, topic_id) -> (km:int, ts) — что реально записали через service_upsert
_LAST_REC_TTL = 3600      # коррекцию принимаем только если запись была недавно (1 ч)
_PENDING_CORRECTION = {}  # (chat_id, topic_id) -> (old_km:int, new_km:int, bike:str, ts)

# === Мягкий гейт убывания одометра (задача 383) ===
_SOFT_ODO_THRESHOLD = 500      # Δkm ≤ этого — механик подтверждает сам; > — нужен Пым/владелец
_ODO_DROP_CONSEC = {}          # bike → (count:int, ts:float) — повторное убывание → эскалация
_ODO_DROP_CONSEC_TTL = 3600    # окно «подряд» = 1 час
_SOFT_ODO_PENDING = {}         # (chat_id, topic_id) → {new_km, prev_km, bike, escalate, ts}

# === Сторож Б (класс H): единый гейт снижения одометра ===
# Авторизует снижение km ТОЛЬКО явное «да»/кнопка от ВЛАДЕЛЬЦА. Лог тапа/текста — ДО применения.
# Fail-safe: исключение в guard → allow (прежнее поведение). Гейт «да» Пыма не ослаблен.
_ODOGUARD_CONFIRMED = {}  # (chat_id, topic_id) -> {new_km:int, ts:float, source:str}
_ODOGUARD_TTL = 300       # авторизация действительна 5 мин


def _odoguard_authorize(chat_id, topic_id, new_km, source="?"):
    """Зарегистрировать явное «да» владельца на снижение одометра.
    Вызывать СРАЗУ ПОСЛЕ явного подтверждения, ДО вызова _apply_correction."""
    try:
        km_int = int(str(new_km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return
    _ODOGUARD_CONFIRMED[(chat_id, topic_id)] = {
        "new_km": km_int, "ts": _time.time(), "source": source,
    }
    log.info(f"  🔑 сторож Б: авторизован {km_int} тема={topic_id} source={source}")


def _odoguard_check(chat_id, topic_id, new_km, caller="?"):
    """Единый сторож Б (класс H): гейт перед записью снижения одометра.
    Возвращает True (разрешено, токен потреблён) или False (заблокировано).
    Fail-safe: любое исключение → True (прежнее поведение)."""
    try:
        try:
            new_int = int(str(new_km).replace(" ", "").replace(",", ""))
        except (ValueError, TypeError):
            return True
        tok = _ODOGUARD_CONFIRMED.get((chat_id, topic_id))
        if tok is None:
            log.warning(f"  🔒 сторож Б БЛОК [{caller}]: нет авторизации km={new_int} тема={topic_id}")
            return False
        if tok["new_km"] != new_int:
            log.warning(
                f"  🔒 сторож Б БЛОК [{caller}]: km≠авт {tok['new_km']}≠{new_int} тема={topic_id}"
            )
            return False
        if _time.time() - tok["ts"] > _ODOGUARD_TTL:
            log.warning(f"  🔒 сторож Б БЛОК [{caller}]: авторизация устарела тема={topic_id}")
            _ODOGUARD_CONFIRMED.pop((chat_id, topic_id), None)
            return False
        src = tok["source"]
        _ODOGUARD_CONFIRMED.pop((chat_id, topic_id), None)
        log.info(f"  ✅ сторож Б [{caller}]: ok km={new_int} source={src}")
        return True
    except Exception:
        log.exception(f"  сторож Б: исключение fail-safe → allow [{caller}]")
        return True


def _odo_is_consec(bike):
    """Было ли убывание одометра по этому байку в последний час (повтор → эскалация)?"""
    if not bike:
        return False
    rec = _ODO_DROP_CONSEC.get(str(bike))
    if not rec:
        return False
    return (_time.time() - rec[1]) < _ODO_DROP_CONSEC_TTL


def _odo_drop_record(bike):
    """Запомнить убывание по байку для детекта повторного."""
    if not bike:
        return
    rec = _ODO_DROP_CONSEC.get(str(bike))
    _ODO_DROP_CONSEC[str(bike)] = ((rec[0] + 1) if rec else 1, _time.time())


def _sender_from_user(u):
    """username или id строкой — для аудит-следа."""
    if not u:
        return "?"
    if getattr(u, "username", None):
        return "@" + u.username
    uid = getattr(u, "id", None)
    return str(uid) if uid else "?"


def _odo_audit_write(bridge, chat_id, topic_id, bike, new_km, prev_km, sender, outcome, has_photo=False):
    """Аудит-след убывания одометра «было / стало / кто / фото». Fail-safe: не роняет вызывающего."""
    try:
        if not bridge:
            log.info(f"  ОДО аудит (no bridge): {prev_km}→{new_km} {outcome} кто={sender}")
            return
        _grp = f"сервис / topic {topic_id}" if topic_id else "сервис"
        notes = (
            f"аудит ОДО: было={prev_km} стало={new_km} "
            f"| кто={sender} | {outcome} | фото={'да' if has_photo else 'нет'}"
        )
        r = bridge.add_event(
            msg_date="", group=_grp, bike=str(bike or ""),
            event_type="odo_audit", fuel="", mileage=str(new_km),
            photos=1 if has_photo else 0, notes=notes[:300],
            msg_id=f"odo_audit:{chat_id}:{topic_id}:{new_km}",
            sender=sender,
        )
        log.info(f"  ОДО аудит ok={r.get('ok')} {prev_km}→{new_km} {outcome}")
    except Exception:
        log.exception("  ОДО аудит: ошибка записи (fail-safe)")


# негатор правки: «не верно / неверно / неправильно / ошибся / wrong»
_CORRECTION_RE = r"(не\s*верн|неверн|неправильн|ошиб|не\s*прав|wrong|ผิด)"
# Масло-нарративы задним числом — исключаются из _CORRECTION_RE, даже если содержат негатор.
# Покрывают: «масло/замена масла было(а) на N», «поменял/заменил/менял (масло) на N», TH: «เปลี่ยนแล้ว»
_OIL_PAST_WORDS = ("была на", "было на", "был на", "поменял", "заменил", "менял",
                   "เปลี่ยนแล้ว", "เปลี่ยนน้ำมันแล้ว", "ถ่ายน้ำมันแล้ว")


def pending_correction_for(chat_id, topic_id):
    """Есть ли открытый переспрос коррекции пробега для этой темы (перехват в handle_text)."""
    return _PENDING_CORRECTION.get((chat_id, topic_id))


def detect_oil_backdated_km(text):
    """Текст — нарратив замены масла задним числом («было на N», «поменял на N»)?
    Нужен oil-контекст + прошедшее время/факт + число 4-6 цифр. → km:int или None.
    Используется для исключения из detect_mileage_correction и в handle_oil_backdated_service."""
    t = str(text or "").strip().lower()
    if not any(kw in t for kw in _OIL_KEYWORDS):
        return None
    if not any(w in t for w in _OIL_PAST_WORDS):
        return None
    m = _re_pl.search(r"\d[\d  ,]{2,}\d", t)
    if not m:
        m = _re_pl.search(r"\b\d{4,6}\b", t)
    if not m:
        return None
    try:
        n = int(m.group(0).replace(" ", "").replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return None
    return n if 1000 <= n <= 999999 else None


def detect_mileage_correction(text):
    """Текст — это коррекция пробега? Нужен негатор + число 4-6 цифр. Вернуть new_km:int или None."""
    t = str(text or "").strip()
    # Исключить масло-нарративы задним числом — у них свой маршрут (handle_oil_backdated_service).
    if detect_oil_backdated_km(t) is not None:
        return None
    if not _re_pl.search(_CORRECTION_RE, t.lower()):
        return None
    m = _re_pl.search(r"\d[\d  ,]{2,}\d", t)   # 4+ цифр (с пробелами/запятыми)
    if not m:
        return None
    try:
        n = int(m.group(0).replace(" ", "").replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return None
    return n if 1000 <= n <= 999999 else None


def msg_correction_ask(bike, old_km, new_km):
    """Двуязычный переспрос правки пробега (🇹🇭 первым / 🇷🇺, единый разделитель)."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    less = new_km < old_km
    th_note = " (น้อยกว่าที่บันทึกไว้ ยืนยันว่าถูกต้อง)" if less else ""
    ru_note = " Это меньше записанного — подтверди, что верно." if less else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 แก้เลขไมล์{b_th} {old_km} → {new_km} กม. ไหมครับ?{th_note} กดปุ่ม «ใช่» หรือพิมพ์ «да» 🙏\n"
        f"{_SEP}\n"
        f"🇷🇺 📟 Исправить пробег{b_ru} {old_km} → {new_km} км?{ru_note} Нажми «Да» или напиши «да» 🙏"
    )


def _mileage_q_age(pend):
    """Возраст вопроса о пробеге в секундах; None — метки времени нет (легаси-запись/тест-фикстура)."""
    try:
        ts = pend[4] if (isinstance(pend, (tuple, list)) and len(pend) > 4) else None
        return (_time.time() - float(ts)) if ts else None
    except (TypeError, ValueError):
        return None


def _mileage_q_stale(pend):
    """Вопрос о пробеге протух? Без метки времени → НЕ протух (fail-safe: прежнее поведение)."""
    age = _mileage_q_age(pend)
    return bool(age is not None and age > _PENDING_MILEAGE_TTL)


def pending_mileage_for(chat_id, topic_id):
    """Есть ли ЖИВОЙ открытый вопрос о пробеге для этой темы (для перехвата в handle_text).
    Протухший вопрос открытым НЕ считается (класс-фикс 4957, корень 5): иначе он и ответ съедает,
    и держит уступку голого числа в handle_service_result. Снимает его expire_stale_mileage_question
    — с внятным «вопрос устарел», а не молча."""
    pend = _PENDING_MILEAGE.get((chat_id, topic_id))
    if pend is None or _mileage_q_stale(pend):
        return None
    return pend


def pending_odo_lower_for(chat_id, topic_id):
    """Есть ли ЖИВОЙ открытый вопрос о ПОНИЖЕНИИ для этой темы (для перехвата в handle_text).

    ЗАЧЕМ ОТДЕЛЬНАЯ ДВЕРЬ (23.08.2026, шаг 2 цели 120). Роутер зовёт `handle_mileage_confirm`
    только при живом `pending_mileage_for`, то есть по состоянию `_PENDING_MILEAGE`. Вопрос о
    понижении живёт в ДРУГОМ состоянии (`_ODO_LOWER_PENDING`), и до сих пор он ездил зайцем:
    единственный его источник `_ask_mileage_confirm` двумя строками выше заводил и запись о
    вопросе про пробег. У двери регистра такой записи нет вовсе — пояснение, написанное после
    её отказа, не дошло бы до обработчика НИ РАЗУ, и вопрос висел бы вечно. Прямой вызов
    обработчика в тесте этого не ловит: он входит МИМО роутерного гейта.

    ПРЕДЕЛ ЖИЗНИ — ТОТ ЖЕ `_PENDING_MILEAGE_TTL`, а не новое число: это тот же по смыслу
    «открытый вопрос в теме», и второй величины об одном сроке заводить не за чем. Протухший
    открытым НЕ считается — тогда текст идёт обычным путём, как у вопроса о пробеге."""
    low = _ODO_LOWER_PENDING.get((chat_id, topic_id))
    if not low:
        return None
    ts = low.get("ts")
    if ts is not None and (_time.time() - ts) > _PENDING_MILEAGE_TTL:
        return None
    return low


async def expire_stale_mileage_question(context, chat_id, topic_id, text="") -> bool:
    """КОРЕНЬ 5: у вопроса о пробеге есть предел жизни. Снимаем протухший ДО любого разбора входящего,
    и если человек прислал именно ОТВЕТ (да/нет/число) — говорим, что вопрос устарел, вместо того
    чтобы проглотить сообщение (31.07 07:29 UTC: ответ владельца исчез в вопросе 46-часовой давности).
    Зовётся из роутера первой в servicing-ветке. Возвращает True, если вопрос был снят.
    Fail-safe: любая ошибка → False, поток сообщения не меняется."""
    try:
        key = (chat_id, topic_id)
        pend = _PENDING_MILEAGE.get(key)
        if pend is None or not _mileage_q_stale(pend):
            return False
        age_h = int((_mileage_q_age(pend) or 0) // 3600)
        asked_km, bike = str(pend[0]), str(pend[1] or "")
        _PENDING_MILEAGE.pop(key, None)
        _SOFT_ODO_PENDING.pop(key, None)
        clear_awaiting(chat_id, topic_id)
        log.info(f"  → вопрос о пробеге {asked_km} ({bike or '?'}) протух ({age_h}ч) — снят, "
                 f"ответ человека НЕ перехватываем")
        looks_like_answer = _is_bare_confirm(text) or (str(text or "").strip().lower() in _CONFIRM_NO)
        if not looks_like_answer:
            return True
        b_th = f" ({bike})" if bike else ""
        b_ru = f" по {bike}" if bike else ""
        _pw = (_PENDING_WORKS.get(key) or {}).get("works") or []
        tail_th = (f"\n🇹🇭 งานที่รออยู่: {_works_th_str(_pw)} — ส่งเลขไมล์เพื่อบันทึกครับ" if _pw else "")
        tail_ru = (f"\n🇷🇺 Ждут пробега работы: {', '.join(_pw)} — пришли пробег, чтобы записать" if _pw else "")
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=(f"🐀 Splinter\n"
                          f"🇹🇭 📟 คำถามเลขไมล์ {asked_km} กม.{b_th} ถามไว้ {age_h} ชม.ที่แล้ว — หมดอายุแล้วครับ "
                          f"ไม่ได้นับคำตอบนี้เป็นการยืนยัน ถ้าจะบันทึก ส่งเลขไมล์ปัจจุบันมาใหม่นะครับ 🙏{tail_th}\n"
                          f"{_SEP}\n"
                          f"🇷🇺 📟 Вопрос про пробег {asked_km} км{b_ru} задан {age_h} ч назад — он устарел. "
                          f"Этот ответ подтверждением НЕ засчитал. Если нужно записать — пришли текущий "
                          f"пробег заново 🙏{tail_ru}"))
        return True
    except Exception:
        log.exception("  → снятие протухшего вопроса о пробеге сбоило (fail-safe: поток не меняем)")
        return False


def msg_mileage_drop(bike, new_km, last_km):
    """Фикс B (сторож): распознанный пробег МЕНЬШЕ последнего известного — физически
    невозможно (одометр не убывает). Просим правильное число / переснять. В ТО НЕ пишем."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 อ่านเลขไมล์ได้ {new_km} กม.{b_th} แต่ครั้งก่อนคือ {last_km} กม. "
        f"เลขไมล์ลดลงไม่ได้ — น่าจะอ่านผิด ส่งเลขที่ถูกต้องหรือถ่ายรูปใหม่ให้ชัด ๆ นะครับ 🙏\n"
        f"🇷🇺 📟 Вижу пробег {new_km} км{b_ru}, но последний известный — {last_km} км. "
        f"Пробег не может уменьшиться — похоже на ошибку распознавания. "
        f"Пришли правильное число или переснимите фото 🙏"
    )


def msg_soft_odo_self(bike, new_km, prev_km):
    """Мягкий гейт убывания ≤500 км — механик подтверждает сам."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    try:
        delta = abs(int(str(prev_km)) - int(str(new_km)))
    except (ValueError, TypeError):
        delta = "?"
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 อ่านไมล์ได้ {new_km} กม.{b_th} แต่ครั้งก่อน {prev_km} กม. (ลด {delta} กม.)\n"
        f"ตั้งใจไหมครับ? (เช่น เปลี่ยนมาตรวัด) กด «ใช่» หรือส่งเลขที่ถูกต้อง 🙏\n"
        f"{_SEP}\n"
        f"🇷🇺 📟 Вижу {new_km} км{b_ru}, но последний был {prev_km} км (−{delta} км).\n"
        f"Это намеренно (например, новый спидометр)? Нажми «Да» или пришли верное число 🙏"
    )


def msg_soft_odo_escalate(bike, new_km, prev_km, reason=""):
    """Мягкий гейт убывания — нужен Пым/владелец (Δ>500 или повтор)."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    try:
        delta = abs(int(str(prev_km)) - int(str(new_km)))
    except (ValueError, TypeError):
        delta = "?"
    reason_ru = f" ({reason})" if reason else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 ไมล์ {new_km} กม.{b_th} ลดจาก {prev_km} กม. (−{delta} กม.){reason_ru}\n"
        f"ต้องยืนยันโดย {PYM_HANDLE} หรือเจ้าของครับ 🙏\n"
        f"{_SEP}\n"
        f"🇷🇺 📟 Пробег {new_km} км{b_ru} меньше прошлого {prev_km} км (−{delta} км){reason_ru}.\n"
        f"Требуется подтверждение {PYM_HANDLE} или владельца 🙏"
    )


def msg_soft_odo_need_owner(bike):
    """Ответ когда не-Пым/не-владелец пытается подтвердить эскалированное убывание."""
    b_ru = f" по {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 ⚠️ การลดเลขไมล์นี้ต้องยืนยันโดย {PYM_HANDLE} หรือเจ้าของครับ\n"
        f"{_SEP}\n"
        f"🇷🇺 ⚠️ Это убывание{b_ru} требует подтверждения {PYM_HANDLE} или владельца"
    )


#: (chat_id, topic_id) → {bike, recorded, sent, reason, oil_hint, register, ts}.
#: Живёт между «выбрал причину» и «написал пояснение». Пустая `reason` — причину ещё не выбрали.
_ODO_LOWER_PENDING = {}


def _odo_lower_on():
    """Ручка отката понижения с пояснением. `ODO_LOWER=0` → прежний путь БАЙТ-В-БАЙТ."""
    return str(_os_env("ODO_LOWER", "1")).strip() not in ("0", "", "нет", "no", "off")


def _odo_lower_kb(tok_by_reason):
    """Три кнопки причин в порядке правила владельца. Четвёртой («просто да») здесь нет намеренно."""
    rows = []
    for key in odo_lower.REASON_ORDER:
        lbl = odo_lower.REASONS[key]
        rows.append([InlineKeyboardButton(f"{lbl['th']} / {lbl['ru']}",
                                          callback_data=f"svc:lowr:{tok_by_reason[key]}")])
    return InlineKeyboardMarkup(rows)


async def _odo_lower_ask(context, chat_id, topic_id, bike, recorded, sent,
                         oil_hint=False, source="", register=""):
    """Показать расхождение ЧИСЛОМ и дать выбор причины. Руки; решение — `odo_lower.ask`.

    `register` — если понижение метит в регистр Лист1 (сегодня только «oil»), запись пойдёт
    веткой исправления моста с причиной и автором; пусто — понижение живёт в теме и в журнале."""
    say = odo_lower.ask(bike, recorded, sent, source=source)
    if say is None:                       # понижения нет — звать было не за чем
        return False
    _ODO_LOWER_PENDING[(chat_id, topic_id)] = {
        "bike": bike or "", "recorded": say["recorded"], "sent": say["sent"],
        "reason": "", "oil_hint": bool(oil_hint), "register": str(register or ""),
        "ts": _time.time(),
    }
    mark_awaiting(chat_id, topic_id)
    toks = {k: _svc_put({"kind": "odo_lower", "chat": chat_id, "topic": topic_id,
                         "bike": bike or "", "reason": k})
            for k in odo_lower.REASON_ORDER}
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=f"🐀 Splinter\n🇹🇭 {say['th']}\n🇷🇺 {say['ru']}",
                reply_markup=_odo_lower_kb(toks))
    log.info(f"  → ПОНИЖЕНИЕ: {bike} записано={say['recorded']} прислано={say['sent']} "
             f"(−{say['drop']}) — жду причину и пояснение, регистр={register or 'нет'}")
    return True


async def _odo_lower_explanation(msg, context, bridge, text, low) -> bool:
    """Пришёл текст, когда причина уже выбрана: это и есть письменное пояснение.

    Не принято — говорим, ЧТО дописать, и вопрос ОСТАЁТСЯ открытым (глухого «нет» тут нет по
    построению). Принято — понижение идёт, а слова человека уезжают вместе с числом."""
    key = (msg.chat_id, getattr(msg, "message_thread_id", None))
    who = _sender_from_user(getattr(msg, "from_user", None))
    plan = odo_lower.plan(low.get("reason"), text, who)
    if not plan["ok"]:
        log.info(f"  → ПОНИЖЕНИЕ: пояснение не принято ({plan['state']}) — вопрос остаётся")
        await _send(context, chat_id=msg.chat_id, message_thread_id=key[1],
                    text=f"🐀 Splinter\n🇹🇭 ⚠️ {plan['say_th']}\n🇷🇺 ⚠️ {plan['say_ru']}")
        return True
    await _odo_lower_commit(context, bridge, key[0], key[1], low, plan, who,
                            msg_date=_msg_date_of(msg))
    return True


async def _odo_lower_commit(context, bridge, chat_id, topic_id, low, plan, who, msg_date=""):
    """Пояснение принято → понижение идёт. Пояснение сохраняется ТРЕМЯ следами, и это не роскошь:
    квитанция человеку СЕЙЧАС, строка аудита в «события» — чтобы прочитать ПОТОМ, и (когда
    понижение метит в регистр) причина+автор в самой ветке исправления моста, где след
    fail-closed: журнал не лёг → мост откатывает правку."""
    bike = low.get("bike") or ""
    recorded, sent = low.get("recorded"), low.get("sent")
    _ODO_LOWER_PENDING.pop((chat_id, topic_id), None)
    _SOFT_ODO_PENDING.pop((chat_id, topic_id), None)
    _PENDING_MILEAGE.pop((chat_id, topic_id), None)
    clear_awaiting(chat_id, topic_id)
    _odo_drop_record(bike)

    # (1) СЛЕД, КОТОРЫЙ ЧИТАЮТ ПОТОМ. Слова человека едут ДОСЛОВНО — ярлык причины их
    # предваряет, а не заменяет (правило полноты истории 23.08).
    _odo_audit_write(bridge, chat_id, topic_id, bike, sent, recorded, sender=who,
                     outcome=f"понижение принято · {plan['line']}")

    # (2) РЕГИСТР ЛИСТ1 — только веткой исправления, то есть С ПРИЧИНОЙ И АВТОРОМ. Обычный путь
    # понижения не знает и знать не должен: пара «причина+автор» и есть то, что его открывает.
    failed = None
    if low.get("register") == "oil" and bridge is not None:
        plate = _plate_from_name(bike)
        if plate:
            res = bridge.set_fleet_oil(number=plate, oil_km=sent, confirmed=True,
                                       fix_reason=plan["line"], fixed_by=who)
            if not (isinstance(res, dict) and res.get("ok")):
                failed = res if isinstance(res, dict) else {"error": ""}
            log.info(f"  → ПОНИЖЕНИЕ регистра: {plate} → {sent} ok={(res or {}).get('ok')}")

    # (3) ЗАМЕНА ОДОМЕТРА — СОБЫТИЕ, А НЕ ПРАВКА СТАРОЙ ЗАПИСИ (правило владельца 23.08):
    # пробег начинается заново, и это отдельная строка истории байка.
    if plan["writes_history"] and bridge is not None:
        try:
            bridge.add_event(msg_date=msg_date or "", group="сервис", bike=str(bike),
                             event_type="odometer_replaced", fuel="", mileage=str(sent),
                             photos=0, notes=f"замена одометра: {plan['explanation']}"[:300],
                             msg_id=f"odo_new:{chat_id}:{topic_id}:{sent}", sender=who)
        except Exception:
            log.exception("  → ПОНИЖЕНИЕ: строка истории о замене одометра не легла (fail-safe)")

    if failed is not None:
        # Отказ моста не отменяет сказанного человеку: он видит числа, что случилось и что делать.
        detail_ru, detail_th = _refuse_words(failed, plate=_plate_from_name(bike), sent=sent)
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=(f"🐀 Splinter\n🇹🇭 ⚠️ {detail_th}\n🇷🇺 ⚠️ {detail_ru}\n"
                                f"🇷🇺 Пояснение я сохранил: «{plan['explanation']}»"))
        return False

    rec = odo_lower.receipt(bike, recorded, sent, low.get("reason"), plan["explanation"], who)
    await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                      text=f"🐀 Splinter\n🇹🇭 {rec['th']}\n🇷🇺 {rec['ru']}")
    _odo_confirmed(bridge, chat_id, topic_id, bike, str(sent), questioned_km=sent,
                   sender=who, source=f"понижение с пояснением ({plan['reason']})",
                   msg_date=msg_date)
    try:
        await _after_mileage(context, bridge, chat_id, topic_id, bike, str(sent),
                             bool(low.get("oil_hint")))
    except Exception:
        log.exception("  → ПОНИЖЕНИЕ: ошибка ТО-трекера после записи")
    return True


#  ============================================================
#  РАБОТЫ БЫЛИ НА ДРУГОМ ПРОБЕГЕ — ТРЕТИЙ ИСХОД КАРТОЧКИ ПОДТВЕРЖДЕНИЯ (25.08.2026)
#  Решение — `batch_odo` (чистая функция), здесь только РУКИ. Пробег в разговоре ОДИН на тему, и
#  у отдельной работы своего пробега нет вовсе; партия прошлым числом получает СВОИ пробег и дату
#  и ложится ТОЛЬКО в историю — текущий одометр байка не двигается ни одной веткой.
#  ============================================================

#: (chat_id, topic_id) → {bike, done, works, km, date_iso, date_human, expl, stage, ts}.
#: `stage`: "ask" — ждём пробег и дату; "expl" — ждём письменное пояснение (партия ниже записанного).
_BATCH_ODO_PENDING = {}


def _batch_odo_on():
    """Ручка отката. `BATCH_ODO=0` → третьей кнопки нет вовсе, путь мёртв ДО разбора чего-либо."""
    return batch_odo.enabled(_os_env("BATCH_ODO", "1"))


def pending_batch_odo_for(chat_id, topic_id):
    """Есть ли ЖИВОЙ открытый вопрос о партии на другом пробеге (для перехвата в роутере).

    Дверь отдельная по той же причине, что у `pending_odo_lower_for`: вопрос живёт в СВОЁМ
    состоянии, а `handle_mileage_confirm` роутер зовёт по `_PENDING_MILEAGE`, которого у этой
    ветки нет вовсе — без своей двери ответ человека не дошёл бы до обработчика НИ РАЗУ.
    Предел жизни — тот же `_PENDING_MILEAGE_TTL`: это тот же по смыслу «открытый вопрос в теме»,
    и второй величины об одном сроке заводить не за чем."""
    pend = _BATCH_ODO_PENDING.get((chat_id, topic_id))
    if not pend:
        return None
    ts = pend.get("ts")
    if ts is not None and (_time.time() - ts) > _PENDING_MILEAGE_TTL:
        return None
    return pend


def _batch_odo_names(bridge, chat_id, topic_id, bike, done):
    """Виды партии → СЛОВА ЧЕЛОВЕКА, а не ярлыки (правило полноты истории 23.08).

    Разбор — ТОТ ЖЕ `work_name.words_of` с ТЕМ ЖЕ живым `_service_kind`, что у `_sp_write_done`:
    второй мерки «какие слова относятся к этому виду» здесь не заводится. Слов вида нет вовсе →
    ярлык, как и там: подменять нечего."""
    said = None
    on = _work_name_on()
    if on:
        try:
            said = _sp_words_said(bridge, chat_id, topic_id, bike)
        except Exception:
            log.exception("  → партия на другом пробеге: слова заявки не прочитаны (беру ярлыки)")
            said = None
    names, seen = [], set()
    for k in (done or []):
        mine = work_name.words_of(k, said, _service_kind) if on else []
        if not mine:
            pair = _SP_KIND_LABEL.get(k) or (k, k)
            mine = [pair[1]]
        for w in mine:
            slot = _pw_slot(w)
            if slot and slot not in seen:
                seen.add(slot)
                names.append(w)
    return names


async def _batch_odo_ask(context, bridge, chat_id, topic_id, bike, done):
    """Нажата третья кнопка → спросить ПРОБЕГ и ДАТУ партии. Ничего не пишет."""
    works = _batch_odo_names(bridge, chat_id, topic_id, bike, done)
    cur = ""
    try:
        cur = _odo_current(bridge, bike) if bike else ""
    except Exception:
        log.exception("  → партия на другом пробеге: текущий пробег не прочитан (спрошу без него)")
    _BATCH_ODO_PENDING[(chat_id, topic_id)] = {
        "bike": bike or "", "done": list(done or []), "works": list(works),
        "km": None, "date_iso": "", "date_human": "", "expl": "",
        "current_km": str(cur or ""), "stage": "ask", "ts": _time.time(),
    }
    mark_awaiting(chat_id, topic_id)
    say = batch_odo.question(bike, works, cur)
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=f"🐀 Splinter\n🇹🇭 {say['th']}\n{_SEP}\n🇷🇺 {say['ru']}")
    log.info(f"  → ПАРТИЯ на другом пробеге: {bike or '?'} виды={list(done or [])} "
             f"работы={works} текущий={cur or '?'} — жду пробег и дату")
    return True


async def _batch_odo_answer(msg, context, bridge, text, pend) -> bool:
    """Пришёл текст при открытом вопросе о партии. Два этапа в одной двери: сперва пробег+дата,
    потом (если партия ниже записанного) письменное пояснение.

    Вопрос НЕ закрывается глухо ни на одном отказе: каждый отказ говорит, ЧТО прислать, и ждёт
    дальше — глухого «нет» тут нет по построению (правило «бот не молчит и не отказывает глухо»)."""
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    who = _sender_from_user(getattr(msg, "from_user", None))

    if pend.get("stage") == "expl":
        # ДОРОГА ПОНИЖЕНИЯ НЕ ИЗОБРЕТАЕТСЯ ВТОРОЙ РАЗ: приёмку пояснения целиком судит `odo_lower`
        # (его словарь согласия, его порог букв, его исходы) — через `batch_odo.explanation_verdict`.
        v = batch_odo.explanation_verdict(text)
        if not v["ok"]:
            log.info(f"  → ПАРТИЯ: пояснение не принято ({v['state']}) — вопрос остаётся")
            await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                        text=f"🐀 Splinter\n🇹🇭 ⚠️ {v['say_th']}\n{_SEP}\n🇷🇺 ⚠️ {v['say_ru']}")
            return True
        pend["expl"] = v["text"]
        await _batch_odo_commit(context, bridge, chat_id, topic_id, pend, who)
        return True

    today = None
    try:
        today = msg.date.date() if getattr(msg, "date", None) else None
    except Exception:
        today = None
    v = batch_odo.verdict(text, today=today)
    if not v["ok"]:
        log.info(f"  → ПАРТИЯ: ответ не полон ({v['state']}) — вопрос остаётся")
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=f"🐀 Splinter\n🇹🇭 ⚠️ {v['say_th']}\n{_SEP}\n🇷🇺 ⚠️ {v['say_ru']}")
        pend["ts"] = _time.time()
        return True
    pend["km"], pend["date_iso"], pend["date_human"] = v["km"], v["date_iso"], v["date_human"]

    low = batch_odo.lowering(pend.get("current_km"), v["km"])
    if low["known"] and low["lower"]:
        pend["stage"] = "expl"
        pend["ts"] = _time.time()
        say = batch_odo.explanation_ask(pend.get("bike"), low)
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=f"🐀 Splinter\n🇹🇭 {say['th']}\n{_SEP}\n🇷🇺 {say['ru']}")
        log.info(f"  → ПАРТИЯ ниже записанного: {pend.get('bike') or '?'} записано={low['recorded']} "
                 f"партия={low['named']} (−{low['drop']}) — жду письменное пояснение")
        return True
    await _batch_odo_commit(context, bridge, chat_id, topic_id, pend, who)
    return True


async def _batch_odo_commit(context, bridge, chat_id, topic_id, pend, who):
    """Партия ложится на НАЗВАННЫЙ пробег и НАЗВАННУЮ дату — и только в историю.

    ОДОМЕТР НЕ ДВИГАЕТСЯ НИ ОДНОЙ ВЕТКОЙ, и это устройством, а не обещанием: здесь нет ни
    `_odo_store`, ни `_odo_confirmed`, ни `service_upsert(current_km=…)`, ни `set_fleet_*` —
    приём взят у `_write_oil_backdated`, где одометр цел ровно потому, что его никто не шлёт.
    Дверь истории ОДНА и та же, что у выгрузки буфера (`_write_info_works`): ключ там
    КОНТЕНТНЫЙ (`info:{номер}:{ключ-работы}:{км}`), поэтому две партии на РАЗНЫХ пробегах дают
    РАЗНЫЕ ключи, то есть две группы строк, а не одну."""
    bike = pend.get("bike") or ""
    km = pend.get("km")
    date_iso, date_human = pend.get("date_iso") or "", pend.get("date_human") or ""
    works = list(pend.get("works") or [])
    expl = pend.get("expl") or ""
    _BATCH_ODO_PENDING.pop((chat_id, topic_id), None)
    clear_awaiting(chat_id, topic_id)

    failed = []
    written = []
    try:
        written = _write_info_works(bridge, "обслуживание", topic_id, bike, works, km, "",
                                    msg_date=date_iso, chat_id=chat_id, failed_out=failed,
                                    sender=str(who or "")) or []
    except Exception:
        log.exception("  → ПАРТИЯ: запись истории упала")
        failed = [(w, "exception") for w in works]

    # СЛЕД ПОЯСНЕНИЯ, КОТОРЫЙ ЧИТАЮТ ПОТОМ — тот же приём, что у понижения: слова человека едут
    # ДОСЛОВНО отдельной строкой, а не только в квитанции, которая живёт в чате один экран.
    if expl and bridge is not None:
        try:
            bridge.add_event(msg_date=date_iso, group="обслуживание", bike=str(bike),
                             event_type="repair", fuel="", mileage=str(km), photos=0,
                             notes=f"партия прошлым числом ({date_human}): {expl}"[:300],
                             msg_id=f"batch:{chat_id}:{topic_id}:{km}", sender=str(who or ""))
        except Exception:
            log.exception("  → ПАРТИЯ: строка с пояснением не легла (fail-safe, квитанция скажет)")

    lost = [w for w, _e in failed]
    regs = [(_SP_KIND_LABEL.get(k) or (k, k))[1] for k in (pend.get("done") or [])
            if k in _SP_COL_KINDS]
    rec = batch_odo.receipt(bike, written, lost, km, date_human, explanation=expl,
                            current_km=pend.get("current_km"), registers=regs)
    await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                      text=f"🐀 Splinter\n🇹🇭 {rec['th']}\n{_SEP}\n🇷🇺 {rec['ru']}")
    log.info(f"  → ПАРТИЯ записана: {bike or '?'} км={km} дата={date_iso} "
             f"строк={len(written)} потерь={len(lost)} исход={rec['state']} "
             f"регистры НЕ тронуты={regs or '—'}")

    # Заявка закрывается ТОЙ ЖЕ дверью, что у обычного пути (`_sp_debt_close` по вердикту), а не
    # второй: работы СДЕЛАНЫ, просто датированы прошлым. Не закрылась — история уже записана,
    # и висящая заявка честнее потерянной строки.
    try:
        if _service_debt_on():
            _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=list(pend.get("done") or []),
                           batch=list(pend.get("done") or []), odometer=km, row_terminal=True,
                           write={"landed": bool(written), "known": True,
                                  "detail": (f"партия прошлым числом {date_human} на {km} км "
                                             f"({who or 'trusted'}): строк {len(written)}")})
    except Exception:
        log.exception("  → ПАРТИЯ: закрытие заявки упало (история записана, заявка осталась)")
    return written, failed


async def _ask_mileage_confirm(context, chat_id, topic_id, bike, mileage, oil_hint=False):
    """Спросить подтверждение распознанного с фото пробега + поставить pending/awaiting.
    Фикс B (сторож пробега): если распознанное число МЕНЬШЕ последнего известного по теме —
    это ошибка vision (одометр не убывает). Тогда вместо «верно?» шлём флаг и НЕ пишем в ТО
    до корректной цифры; floor в pending не даёт «да» подтвердить заведомо неверное число.
    oil_hint: подсказка «в сообщении был маркер замены» — пробросится в _after_mileage, чтобы
    задать вопрос «после замены или просто пробег?» даже если ТО формально ещё не подошло."""
    floor = None
    try:
        new_km = int(str(mileage).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        new_km = None
    if new_km is not None:
        prev = last_mileage_in_topic(chat_id, topic_id, exclude_km=new_km)
        if prev and new_km < prev[0]:
            floor = prev[0]

    # ts (5-й элемент) — предел жизни вопроса, класс-фикс 4957 корень 5.
    _PENDING_MILEAGE[(chat_id, topic_id)] = (str(mileage), bike or "", floor, bool(oil_hint),
                                             _time.time())
    mark_awaiting(chat_id, topic_id)

    if floor is not None:
        # Мягкий гейт (задача 383): вместо жёсткого отказа — переспрос.
        delta = floor - new_km
        consec = _odo_is_consec(bike)
        escalate = (delta > _SOFT_ODO_THRESHOLD) or consec
        reason = "повтор" if consec else ""
        _SOFT_ODO_PENDING[(chat_id, topic_id)] = {
            "new_km": new_km, "prev_km": floor, "bike": bike or "",
            "escalate": escalate, "ts": _time.time(),
        }
        if _odo_lower_on():
            # ПРАВИЛО ВЛАДЕЛЬЦА 23.08: односложное согласие причиной не считается. Прежняя
            # единственная кнопка «✅ Да, намеренно» была ровно им — и ничего не сохраняла.
            # Теперь расхождение названо ЧИСЛОМ, причина выбирается из трёх, а пояснение
            # человек пишет словами; без него понижение не идёт.
            #
            # ЭСКАЛАЦИЯ ЗДЕСЬ БОЛЬШЕ НЕ ДЕЛИТ ПУТЬ, и это прямая буква правила: «подтвердить
            # понижение может ТОТ ЖЕ человек, который прислал число, отдельный подтверждающий
            # не требуется… цена названа владельцем сознательно: меняем предотвращение на
            # прослеживаемость». Второй рубеж при этом НЕ снят — он стоит там, где и стоял, у
            # самой живой таблицы: мост сам отвергает понижение регистра больше своего порога
            # (`oil_drop_needs_trusted`), и этот отказ теперь ГОВОРИТ, что делать.
            await _odo_lower_ask(context, chat_id, topic_id, bike, floor, new_km,
                                 oil_hint=oil_hint, source="фото")
        elif escalate:
            await _send(context, chat_id=chat_id,
                        text=msg_soft_odo_escalate(bike, new_km, floor, reason),
                        message_thread_id=topic_id)
        else:
            tok = _svc_put({"kind": "soft_odo", "chat": chat_id, "topic": topic_id,
                            "bike": bike or "", "new_km": new_km, "prev_km": floor,
                            "oil_hint": bool(oil_hint)})
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ ใช่ ตั้งใจ / Да, намеренно", callback_data=f"svc:sodo:{tok}"),
            ]])
            await _send(context, chat_id=chat_id,
                        text=msg_soft_odo_self(bike, new_km, floor),
                        message_thread_id=topic_id, reply_markup=kb)
        return

    # Кнопка [✅ ใช่/Да] — быстрое подтверждение распознанного числа. Текст-ответ «да»/правильное
    # число тоже работает (handle_mileage_confirm). floor/oil_hint кладём в токен (сторож B сохранён).
    tok = _svc_put({"kind": "mileconf", "chat": chat_id, "topic": topic_id, "bike": bike or "",
                    "mileage": str(mileage), "floor": floor, "oil_hint": bool(oil_hint)})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ใช่ / Да", callback_data=f"svc:mok:{tok}")],
    ])
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    # ЗАМОК ПОВТОРОВ (вид L). Состояние = САМО РАСПОЗНАННОЕ ЧИСЛО: другая цифра — другой
    # вопрос, он уходит снова; та же цифра, снятая с фото второй раз, — повтор.
    # `_PENDING_MILEAGE`/`mark_awaiting` выставлены ВЫШЕ и замком не трогаются: ответ «да»
    # или числом работает и на подавленном повторе (вопрос-то уже стоял).
    sent = await _hint_send(
        context, kind="L", bike=bike, state=("mileage_confirm", mileage),
        chat_id=chat_id, topic_id=topic_id,
        text=(f"🐀 Splinter\n"
              f"🇹🇭 อ่านเลขไมล์ได้ {mileage} กม.{b_th} ถูกต้องไหมครับ? กดปุ่ม «ใช่» หรือส่งเลขที่ถูกต้อง 🙏\n"
              f"🇷🇺 📟 Вижу пробег {mileage} км{b_ru} (с фото). Верно? Нажми «Да» или пришли правильное число 🙏"),
        reply_markup=kb,
    )
    if sent is not HINT_SKIPPED:
        _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос → удалить на финале


async def handle_mileage_confirm(msg, context, bridge, text) -> bool:
    """Перехват ответа на подтверждение пробега. Возвращает True если обработал (был pending
    и ответ распознан как да/число/нет). Иначе False → обычный путь (гейт не трогаем)."""
    key = (msg.chat_id, getattr(msg, "message_thread_id", None))
    # ПОНИЖЕНИЕ ЖДЁТ ПОЯСНЕНИЯ — этот текст и есть оно. Проверка стоит ПЕРЕД `pend` намеренно:
    # вопрос о пробеге к этому моменту уже отвечен числом, и его отсутствие не должно уводить
    # пояснение в общий путь, где оно молча стало бы новым сообщением ни о чём.
    low = _ODO_LOWER_PENDING.get(key)
    if low and low.get("reason"):
        return await _odo_lower_explanation(msg, context, bridge, text, low)
    # ПАРТИЯ НА ДРУГОМ ПРОБЕГЕ ЖДЁТ ЧИСЛА И ДАТЫ — по той же причине и на том же месте, что и
    # пояснение к понижению: своего `_PENDING_MILEAGE` у этой ветки нет, и без перехвата здесь
    # ответ человека ушёл бы в общий путь и стал бы сообщением ни о чём.
    _batch = _BATCH_ODO_PENDING.get(key)
    if _batch:
        return await _batch_odo_answer(msg, context, bridge, text, _batch)
    pend = _PENDING_MILEAGE.get(key)
    if not pend:
        return False
    if _mileage_q_stale(pend):
        # Протухший вопрос не имеет права засчитать ответ (корень 5). Штатно его снимает
        # expire_stale_mileage_question из роутера; здесь — страховка для прямых вызовов.
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(*key)
        log.info(f"  → протухший вопрос о пробеге снят в handle_mileage_confirm — ответ отдаю обычному пути")
        return False
    mileage, bike = pend[0], pend[1]
    floor = pend[2] if len(pend) > 2 else None   # фикс B: пол пробега (флаг-режим)
    oil_hint = pend[3] if len(pend) > 3 else False   # подсказка «был маркер замены»
    t = (text or "").strip().lower()
    m = _re_pl.search(r"\d{4,}", t.replace(" ", "").replace(",", ""))
    if t in _CONFIRM_YES:
        num = mileage
    elif m:
        num = m.group(0)            # правка: человек прислал правильное число
    elif t in _CONFIRM_NO:
        soft = _SOFT_ODO_PENDING.pop(key, None)
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(*key)
        if soft and bridge:
            _odo_audit_write(bridge, key[0], key[1], soft.get("bike", ""),
                             soft.get("new_km", 0), soft.get("prev_km", 0),
                             sender=_sender_from_user(getattr(msg, "from_user", None)),
                             outcome="отказ (нет)")
        await _send(context, chat_id=msg.chat_id,
                    text=("🐀 Splinter\n"
                          "🇹🇭 โอเค ส่งรูปเลขไมล์ชัดๆ อีกครั้งนะครับ 🙏\n"
                          "🇷🇺 Ок, пришли, пожалуйста, чёткое фото одометра ещё раз 🙏"),
                    message_thread_id=key[1])
        return True
    else:
        return False                # не подтверждение — отдаём обычному пути
    # Мягкий гейт убывания (задача 383): «да» или число ниже floor → проверяем soft gate.
    if floor is not None:
        try:
            num_int = int(str(num).replace(" ", "").replace(",", ""))
        except (ValueError, TypeError):
            num_int = None
        if num_int is not None and num_int < floor:
            soft = _SOFT_ODO_PENDING.get(key)
            sender = _sender_from_user(getattr(msg, "from_user", None))
            if soft:
                escalate = soft.get("escalate", True)
                u = getattr(msg, "from_user", None)
                authed = (not escalate) or is_owner_user(u) or (
                    u and getattr(u, "username", None) and u.username.lower() in PYM_USERNAMES)
                if not authed:
                    # Блок: не Пым/владелец при эскалации — аудит, pending живёт
                    _odo_audit_write(bridge, key[0], key[1], soft.get("bike", bike),
                                     num_int, floor, sender=sender,
                                     outcome="заблокировано (нужен Пым/владелец)")
                    await _send(context, chat_id=msg.chat_id,
                                text=msg_soft_odo_need_owner(bike),
                                message_thread_id=key[1])
                    return True
                # Авторизовано: подтверждаем убывание
                _SOFT_ODO_PENDING.pop(key, None)
                _PENDING_MILEAGE.pop(key, None)
                clear_awaiting(*key)
                _odo_drop_record(soft.get("bike") or bike)
                u = getattr(msg, "from_user", None)
                who = ("Пым/владелец" if (is_owner_user(u) or (
                    u and getattr(u, "username", None) and u.username.lower() in PYM_USERNAMES))
                    else "механик")
                _odo_audit_write(bridge, key[0], key[1], soft.get("bike", bike),
                                 num_int, floor, sender=sender,
                                 outcome=f"подтверждено ({who})")
                _odo_confirmed(bridge, msg.chat_id, key[1], bike, num, questioned_km=mileage,
                               sender=sender, source="текст (мягкий гейт)",
                               msg_date=_msg_date_of(msg))
                try:
                    await _after_mileage(context, bridge, msg.chat_id, key[1], bike, num, oil_hint)
                except Exception:
                    log.exception("  → soft odo gate: ошибка ТО-трекера")
                return True
            else:
                # Soft gate не установлен (не должно случаться в новом флоу) — оставляем hard block
                await _send(context, chat_id=msg.chat_id,
                            text=msg_mileage_drop(bike, num, floor),
                            message_thread_id=key[1])
                return True
    _PENDING_MILEAGE.pop(key, None)
    clear_awaiting(*key)
    # ЕДИНАЯ ТОЧКА подтверждения: откат строк с прежним числом (если человек поправил) + дозапись
    # отложенных инфо-работ ПОДТВЕРЖДЁННЫМ км. Стоит ДО B1 — заявка может увести нас в ранний
    # return, а работы и откат не должны от этого зависеть.
    _odo_confirmed(bridge, msg.chat_id, key[1], bike, num, questioned_km=mileage,
                   sender=_sender_from_user(getattr(msg, "from_user", None)),
                   source="текст", msg_date=_msg_date_of(msg))
    # B1 (вариант б): по байку ОТКРЫТА заявка ТО в статусе 'ждёт_факт' (механик уже отписался о работе,
    # ждали ТОЛЬКО одометр) → подтверждённый фото-одометр доводит заявку до подтверждения Пыму.
    # Сторож убывания B уже пройден выше (берём проверенное число). Запись — по-прежнему по «да» Пыма (гейт сохранён).
    try:
        _sp = _sp_open(bridge, msg.chat_id, key[1], bike) if bike else None
        if _sp and str(_sp.get("status")) == "ждёт_факт":
            _declared = _sp_split(_sp.get("declared"))
            _done = _sp_split(_sp.get("done")) or list(_declared)   # B3: нет done → заявленное считаем сделанным
            await _sp_advance_to_confirm(context, bridge, msg.chat_id, key[1], bike, _declared, _done, num)
            return True
    except Exception:
        log.exception("  → B1: довод заявки фото-одометром упал")
    # Пробег подтверждён И прошёл сторож B → решаем: спросить «после замены?» или просто квитанция.
    try:
        await _after_mileage(context, bridge, msg.chat_id, key[1], bike, num, oil_hint)
    except Exception:
        log.exception("  → ошибка ТО-трекера (подтверждение пробега)")
    return True


async def handle_mileage_correction(msg, context, bridge, text) -> bool:
    """Текстовая КОРРЕКЦИЯ пробега ПОСЛЕ недавней записи (фикс _row22). Если поймали — НЕ пишем
    сразу: ставим _PENDING_CORRECTION + двуязычный переспрос. True если перехватили."""
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    key = (chat_id, topic_id)
    rec = _LAST_RECORDED_KM.get(key)
    if not rec or _time.time() - rec[1] > _LAST_REC_TTL:
        return False                      # нет недавней записи — нечего исправлять
    if not _is_trusted(msg):
        return False                      # правку принимаем только от доверенных
    new_km = detect_mileage_correction(text)
    if new_km is None:
        return False
    old_km = rec[0]
    if new_km == old_km:
        return False
    bike = bike_from_topic(chat_id, topic_id) or ""
    if str(new_km) in _re_pl.findall(r"\d{3,4}", bike):   # не спутать с номером байка (plate)
        return False
    _PENDING_CORRECTION[key] = (old_km, new_km, bike, _time.time())
    mark_awaiting(chat_id, topic_id)
    tok = _svc_put({"kind": "correction", "chat": chat_id, "topic": topic_id,
                    "bike": bike, "old_km": old_km, "new_km": new_km})
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ ใช่ / Да", callback_data=f"svc:fix:{tok}")]])
    sent = await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                       text=msg_correction_ask(bike, old_km, new_km), reply_markup=kb)
    _remember_cycle_msg(chat_id, topic_id, sent)
    log.info(f"  → коррекция пробега: переспрос {old_km}→{new_km} (тема {topic_id})")
    return True


async def handle_correction_confirm(msg, context, bridge, text) -> bool:
    """Перехват ответа на переспрос коррекции пробега. True если обработал (да/нет)."""
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    key = (chat_id, topic_id)
    pend = _PENDING_CORRECTION.get(key)
    if not pend:
        return False
    t = (text or "").strip().lower()
    if t in _CONFIRM_YES:
        # Класс H (сторож Б): только ВЛАДЕЛЕЦ подтверждает снижение одометра.
        # Пым или посторонний «да» — НЕ применяем (pending остаётся, ждём владельца).
        if not _is_owner(msg):
            uname = getattr(getattr(msg, "from_user", None), "username", None) or "?"
            log.warning(
                f"  🔒 сторож Б: confirm не от владельца (@{uname}) тема={topic_id} — pending сохранён"
            )
            return False
        old_km, new_km, bike = pend[0], pend[1], pend[2]
        _PENDING_CORRECTION.pop(key, None)
        clear_awaiting(*key)
        uname = getattr(getattr(msg, "from_user", None), "username", None) or str(
            getattr(getattr(msg, "from_user", None), "id", "?")
        )
        _odoguard_authorize(chat_id, topic_id, new_km, source=f"text:{uname}")
        await _apply_correction(context, bridge, chat_id, topic_id, bike, old_km, new_km)
        return True
    if t in _CONFIRM_NO:
        old_km = pend[0]
        _PENDING_CORRECTION.pop(key, None)
        clear_awaiting(*key)
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=(f"🐀 Splinter\n"
                          f"🇹🇭 โอเค เก็บค่าเดิม {old_km} กม. ไว้ครับ\n"
                          f"{_SEP}\n"
                          f"🇷🇺 Ок, оставил прежний пробег {old_km} км."))
        return True
    return False                          # не да/нет — отдаём дальше (мозг/новая коррекция)


async def _apply_correction(context, bridge, chat_id, topic_id, bike, old_km, new_km):
    """Санкционированная правка одометра через единый сторож Б (класс H).
    Требует предварительной авторизации _odoguard_authorize от владельца.
    Без авторизации — блокируется. Кол.H/I (set_fleet_*) не пишем — только обслуживание."""
    if not _odoguard_check(chat_id, topic_id, new_km, caller="_apply_correction"):
        log.warning(
            f"  🔒 _apply_correction ЗАБЛОКИРОВАНА сторожем Б: {old_km}→{new_km} тема={topic_id}"
        )
        return
    # СТРАХОВКА-ОТКАТ (та же функция, что на пути подтверждения): текстовая правка «не верно,
    # пробег N» исправляла ТОЛЬКО служебную запись обслуживания, а строки «события» с прежним
    # числом оставались в истории байка. Теперь правка снимает и переписывает их тоже.
    _rollback_km_events(bridge, chat_id, topic_id, wrong_km=str(old_km), right_km=str(new_km),
                        sender="правка (текст)", source="_apply_correction")
    info = _run_service_tracker(bridge, chat_id, topic_id, bike, new_km)   # service_upsert(new)
    # Новый last-known = исправленное значение: будущие ФОТО сравнивает сторож B уже от него
    # (_run_service_tracker обновил _LAST_RECORDED_KM; дублируем в буфер фото как свежий high).
    buf = _RECENT_PHOTOS.setdefault((chat_id, topic_id), deque(maxlen=_RECENT_LIMIT))
    buf.append({"vis": {"mileage": str(new_km), "mileage_confidence": "high"},
                "sender": "correction", "ts": _time.time()})
    b_ru = f" по {bike}" if bike else ""
    b_th = f" ({bike})" if bike else ""
    extra_ru = f" Следующее ТО на {info['next_km']} км." if (info and info.get("next_km")) else ""
    extra_th = f" ТО ครั้งถัดไปที่ {info['next_km']} กม." if (info and info.get("next_km")) else ""
    await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс: подтверждение кнопки svc:fix
                      text=(f"🐀 Splinter\n"
                            f"🇹🇭 ✅ แก้เลขไมล์แล้ว{b_th}: {old_km} → {new_km} กม.{extra_th}\n"
                            f"{_SEP}\n"
                            f"🇷🇺 ✅ Пробег исправлен{b_ru}: {old_km} → {new_km} км.{extra_ru}"))
    log.info(f"  → коррекция пробега ПРИМЕНЕНА (сторож Б ✅): {old_km}→{new_km} (тема {topic_id})")


async def handle_oil_backdated_service(msg, context, bridge, text) -> bool:
    """Перехват нарратива «масло/замена задним числом на N» от доверенного (Пым/владелец).
    Одометр НЕ трогается — только oil_last (кол.I) через кнопку подтверждения Пыма.
    Fail-safe: если не распознал (bike не известен, число не то) → False → прежний manager_reply."""
    if not _is_trusted(msg):
        return False
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    bike = bike_from_topic(chat_id, topic_id) or ""
    if not bike:
        return False
    km = detect_oil_backdated_km(text)
    if km is None:
        return False

    # Validation: N > prev oil_last, N ≤ current odometer (если известен)
    fleet = {}
    try:
        fleet = bridge.find_bike(bike) or {}
    except Exception:
        pass
    oil_last = fleet.get("oil_last_km")

    # Текущий одометр — из буфера фото темы (наиболее актуален в servicing)
    lm = last_mileage_in_topic(chat_id, topic_id)
    cur_km = None
    if lm:
        try:
            cur_km = int(str(lm[0]).replace(" ", "").replace(",", ""))
        except Exception:
            pass

    if oil_last and km <= oil_last:
        reason = f"N={km} не больше текущего oil_last={oil_last}"
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=msg_oil_backdated_invalid(bike, km, reason))
        log.info(f"  → backdated oil INVALID (N≤oil_last): km={km} oil_last={oil_last}")
        return True
    if cur_km is not None and km > cur_km:
        reason = f"N={km} > текущий одометр={cur_km}"
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=msg_oil_backdated_invalid(bike, km, reason))
        log.info(f"  → backdated oil INVALID (N>odo): km={km} cur={cur_km}")
        return True

    # Всё ок — показываем карточку Пыму для подтверждения записи в кол.I
    tok = _svc_put({"kind": "oil_backdated", "chat": chat_id, "topic": topic_id,
                    "bike": bike, "km": str(km)})
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "✅ ยืนยัน / Подтвердить", callback_data=f"svc:oilbk:{tok}")]])
    sent = await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                       text=msg_oil_backdated_confirm(bike, km), reply_markup=kb)
    _remember_cycle_msg(chat_id, topic_id, sent)
    mark_awaiting(chat_id, topic_id)
    log.info(f"  → backdated oil: переспрос Пыму {km} км (тема {topic_id})")
    return True


# === Фиксация замены масла: ЯВНЫЙ ВОПРОС кнопками (без угадывания маркер/TTL/окно) ===
# После подтверждения пробега, если замена осмысленна (ТО due/overdue или была подсказка-маркер),
# бот спрашивает кнопками: [После замены] / [Просто пробег]. [После замены] от ДОВЕРЕННОГО →
# set_fleet_oil(confirmed=True) в Лист1 кол.I (КРАСНАЯ зона). [Просто пробег] → квитанция/закреп, в кол.I НЕ пишем.

# Кубатуры моторов — НЕ номер байка (зеркало plateFromName_ в ReadFleet.js).
_CC_PLATE = {"125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"}


def _plate_from_name(text):
    """Голый номер байка из названия: последнее число ≥3 цифр, кроме кубатуры. Иначе None.
    Зеркало plateFromName_ (ReadFleet.js) — set_fleet_oil резолвит строку Лист1 именно по нему."""
    nums = [n for n in _re_pl.findall(r"\d{3,}", str(text or "").lower()) if n not in _CC_PLATE]
    return nums[-1] if nums else None


#: Кол.J — регистр ЗАМЕНЫ МАСЛА в трансмиссии, и берётся он по ДЕЙСТВИЮ, а не по слову.
#: Узел (где) и предмет (что) нужны ОБА: «масло в редукторе» — кол.J, «замена ремня» — нет.
_GEAR_NODE = ("редуктор", "трансмис", "gear", "เกียร์", "เฟือง", "шестер")
_GEAR_SUBST = ("масл", "oil", "น้ำมัน")


def _classify_work(w):
    """Класс работы для маршрутизации (Фаза 1) → адрес записи:
      'oil'       — моторное масло → Лист1 кол.I (set_fleet_oil, отдельный кнопочный флоу);
      'gear'      — ЗАМЕНА МАСЛА редуктора/трансмиссии → кол.J (set_fleet_service);
      'abs'       — ABS oil → кол.K;
      'airfilter' — воздушный (аир) фильтр → кол.L;
      'info'      — без столбца (масляный фильтр, колодки, цепь, вилка, ремень, прочее) → «события».
    Порядок проверок важен: воздушный фильтр → airfilter; иной фильтр → info (раньше масла).

    РЕГИСТР РЕДУКТОРА БЕРЁТСЯ ПО ДЕЙСТВИЮ, А НЕ ПО СОВПАДЕНИЮ ПОДСТРОКИ (22.08.2026). Прежде здесь
    стояло `any(k in s for k in (... "ремн" ...))`, и слово «ремня» одной подстрокой уводило работу
    в кол.J: 22.08 в 10:07:12 «замена ремня» записала кол.J = 41641 км по байку NMAX 155 GREY 5960,
    владелец отменил это через 28 секунд, а вернуть число пришлось РУКОЙ в таблице (мост понижение
    отвергает, `setFleetService_` → `km_decreasing`). Ремень вариатора на скутере — расходник со
    СВОИМ сроком, у которого регистра нет вовсе; заняв чужой, он обнуляет его смысл — таблица
    начинает утверждать, что масло редуктора меняли тогда, когда его не трогали. Тот же класс, что
    у литерала (`40c8425`), имени в аргументе (`05c110b`) и цитаты маркера (`6a7baf9`): решение
    по слову, а не по действию. Теперь кол.J требует ДВУХ признаков сразу — УЗЕЛ (редуктор/
    трансмиссия/gear/เกียร์/เฟือง/шестерни) И ПРЕДМЕТ (масло), — и порядок слов роли не играет:
    «масло в редукторе», «редуктор — замена масла», «gear oil» дают кол.J, а «замена ремня» и
    «полная чистка вариатора» — нет ни при каком порядке. Работа без своего регистра идёт СОБЫТИЕМ
    со словами человека (`work_name`), то есть не теряется: меняется адрес, а не факт записи."""
    s = str(w).lower()
    is_filter = ("фильтр" in s or "filter" in s or "กรอง" in s)
    if is_filter and ("возд" in s or "air" in s or "аир" in s or "อากาศ" in s):
        return "airfilter"          # воздушный фильтр → кол.L
    if is_filter:
        return "info"               # масляный/прочий фильтр — столбца нет → события
    if "abs" in s or "абс" in s:
        return "abs"                # ABS oil → кол.K
    if any(k in s for k in _GEAR_NODE) and any(k in s for k in _GEAR_SUBST):
        return "gear"               # ЗАМЕНА МАСЛА редуктора → кол.J (узел + предмет, оба)
    if "вилк" in s or "fork" in s:
        return "info"               # масло вилки — столбца нет → события
    if any(k in s for k in ("масл", "oil", "น้ำมัน")):
        return "oil"                # моторное масло → кол.I
    return "info"                   # колодки/цепь/прочее → события


def _is_oil_work(w):
    """True ТОЛЬКО для замены МОТОРНОГО масла (кол.I). Делегирует в _classify_work — единый источник."""
    return _classify_work(w) == "oil"


def _same_bike(a, b):
    """Один ли это байк: по НОМЕРУ (plate), как serviceUpsert. Иначе fallback на точное имя.
    Чинит рассинхрон 'имя темы' vs 'каноничное имя из Лист1' при матчинге строк ТО-трекера."""
    pa, pb = _plate_from_name(a), _plate_from_name(b)
    if pa and pb:
        return pa == pb
    return str(a).strip() == str(b).strip()


def _is_trusted_user(u):
    """Доверенный ли автор (для callback-кнопок): Пым/владелец. u = telegram User."""
    return bool(u and u.username and u.username.lower() in TRUSTED_AUTHORS)


# ── МЕТКА КНОПКИ ПЕРЕЖИВАЕТ ПЕРЕЗАПУСК (25.08.2026, разбор 5960 §5) ──────────────────────────
# Хранилище токенов вопроса «после замены/просто пробег» (callback_data ≤64б → короткий int-токен).
# ЖИВОЙ СЛУЧАЙ: кнопка Пыму выдана 25.08 09:23:04 (`svc:done:6`), splinter перезапущен в 10:10:21 —
# и метка умерла вместе с памятью процесса; нажатие отвечало «⚠️ Кнопка устарела», не записав
# ничего. Хуже того, счётчик `_SVC_SEQ` при старте начинался с НУЛЯ: выдав свою шестую метку,
# процесс воскресил бы мёртвую кнопку и увёл её на ЧУЖУЮ операцию (возможно, по другому байку).
#
# Лечится тем же приёмом, каким уже живёт замок подсказок (`hint_dedup_state.json`): память на
# диске рядом с модулем, у прогона тестов — свой файл на процесс. Три следствия:
#   • метка переживает перезапуск — кнопка механика и кнопка Пыма работают после рестарта;
#   • НОМЕРА НЕ ПОВТОРЯЮТСЯ: счётчик поднимается до максимума прочитанного, поэтому «шестая метка
#     нового процесса» больше не может оказаться шестой меткой прошлого;
#   • ПОДДЕЛЬНАЯ/ЧУЖАЯ метка отвергается: запись помнит свои чат и тему, и `_svc_get` сверяет их
#     с сообщением, на котором НАЖАЛИ. Метка чужой темы не исполняется — даже если номер угадан.
# ВОЗРАСТ: `SVC_TOKEN_TTL_H` (дефолт 48 ч) — ровно горизонт жизни самой заявки
# (`_SP_REMIND_MAX_AGE_H`): пока о заявке напоминают, её кнопка обязана работать, а после
# эскалации владельцу висящая метка не должна оживать.
# FAIL-SAFE В ОБЕ СТОРОНЫ: файл не прочитан/не записан → память живёт только в процессе, то есть
# РОВНО прежнее поведение. Откат: `SVC_TOKENS_PERSIST=0` + рестарт splinter.
_SVC_TOKENS = {}   # token(int) -> {chat,topic,bike,km,status,next_km,km_left}
_SVC_SEQ = [0]
_SVC_TOKENS_LOADED = False      # память с диска поднимается один раз за процесс
_SVC_TOKENS_SAID = False        # путь памяти называем в журнале ОДИН раз
_SVC_TOKEN_AT = "_at"           # когда метка выдана (сек. эпохи) — по нему судится возраст
_SVC_TOKEN_OLD = "_restored"    # метка поднята с диска, а не выдана этим процессом


def _svc_tokens_persist():
    """Ручка отката: `SVC_TOKENS_PERSIST=0` + рестарт splinter → метки снова живут только в памяти."""
    return str(os.getenv("SVC_TOKENS_PERSIST", "1")).strip().lower() not in ("0", "false", "no", "off")


def _svc_tokens_ttl():
    """Сколько живёт метка, секунд. `0` → возраст не судим вовсе (метка живёт, пока лежит в файле)."""
    try:
        return max(0.0, float(os.getenv("SVC_TOKEN_TTL_H", _SP_REMIND_MAX_AGE_H))) * 3600.0
    except (TypeError, ValueError):
        return _SP_REMIND_MAX_AGE_H * 3600.0


def _svc_tokens_path():
    """Файл памяти меток. Явная подмена сильнее всего; признак прогона тестов уводит во временный
    каталог — со СВОИМ именем на процесс, иначе память одного прогона гейта утекала бы в следующий
    (живой урок замка подсказок)."""
    global _SVC_TOKENS_SAID
    p = os.getenv("SVC_TOKENS_STATE")
    if not p:
        p = (f"/tmp/svc_tokens_test_{os.getpid()}.json"
             if any(os.getenv(m) for m in _HINT_TEST_MARKS)
             else os.path.join(os.path.dirname(os.path.abspath(__file__)), "svc_tokens.json"))
    if not _SVC_TOKENS_SAID:
        _SVC_TOKENS_SAID = True
        log.info(f"  🔖 метки кнопок ТО: память в {p}")
    return p


def _svc_tokens_load():
    """Поднять метки с диска ОДИН раз за процесс: протухшие отбросить, счётчик увести за максимум
    прочитанного номера (номера не повторяются → воскресшей чужой кнопки не бывает).
    Любая беда → пустая память, то есть прежнее «кнопка устарела»: хуже, чем было, не станет."""
    global _SVC_TOKENS_LOADED
    if _SVC_TOKENS_LOADED or not _svc_tokens_persist():
        return
    _SVC_TOKENS_LOADED = True
    try:
        with open(_svc_tokens_path(), encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return
        ttl, now, kept, gone = _svc_tokens_ttl(), _time.time(), 0, 0
        top = 0
        for k, v in raw.items():
            try:
                tok = int(k)
            except (TypeError, ValueError):
                continue
            top = max(top, tok)          # номер занят, даже если запись протухла
            if not isinstance(v, dict):
                continue
            if ttl and (now - float(v.get(_SVC_TOKEN_AT) or 0)) > ttl:
                gone += 1
                continue
            v[_SVC_TOKEN_OLD] = True
            _SVC_TOKENS[tok] = v
            kept += 1
        _SVC_SEQ[0] = max(_SVC_SEQ[0], top)
        log.info(f"  🔖 метки кнопок ТО подняты с диска: живых {kept}, протухших {gone}, "
                 f"счётчик с {_SVC_SEQ[0] + 1}")
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning(f"  → память меток кнопок не прочиталась ({e}) — метки живут только в памяти")


def _svc_tokens_save():
    """Записать память меток. Не удалась → метка живёт в процессе, как жила до 25.08 (сбой в
    сторону прежнего поведения, а не в сторону исполнения чужой кнопки)."""
    if not _svc_tokens_persist():
        return
    try:
        with open(_svc_tokens_path(), "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in (_SVC_TOKENS or {}).items()},
                      f, ensure_ascii=False, default=str)
    except Exception as e:
        log.warning(f"  → память меток кнопок не записалась: {e}")


def _svc_put(data):
    _svc_tokens_load()
    _SVC_SEQ[0] += 1
    tok = _SVC_SEQ[0]
    try:
        data = dict(data or {})
        data.setdefault(_SVC_TOKEN_AT, _time.time())
    except Exception:
        pass
    _SVC_TOKENS[tok] = data
    if len(_SVC_TOKENS) > 200:                       # держим последние 200
        for k in sorted(_SVC_TOKENS)[:-200]:
            _SVC_TOKENS.pop(k, None)
    _svc_tokens_save()
    return tok


def _svc_get(token, chat_id=None, topic_id=None):
    """Метка по номеру — либо None, и тогда кнопка отвечает «устарела», как отвечала.

    ТРИ ОТКАЗА, и каждый назван в журнале: метки нет · метка старше TTL · метка НЕ ЭТОЙ темы.
    Третий — замок против подделки и против воскресшего номера: адрес операции берётся из метки,
    поэтому метка, чей адрес расходится с местом нажатия, не исполняется вовсе. Место нажатия
    неизвестно (мок/личка) → сверять нечем, ведём себя как прежде."""
    _svc_tokens_load()
    d = _SVC_TOKENS.get(token)
    if not d:
        return None
    ttl = _svc_tokens_ttl()
    if ttl and (_time.time() - float(d.get(_SVC_TOKEN_AT) or 0)) > ttl:
        log.warning(f"  🔖 метка {token} старше {ttl / 3600:.0f} ч — не исполняю")
        _svc_drop(token)
        return None
    if chat_id is not None and d.get("chat") is not None and d.get("chat") != chat_id:
        log.warning(f"  🔖 метка {token} принадлежит чату {d.get('chat')}, нажата в {chat_id} — не исполняю")
        return None
    if topic_id is not None and d.get("topic") is not None and d.get("topic") != topic_id:
        log.warning(f"  🔖 метка {token} принадлежит теме {d.get('topic')}, нажата в {topic_id} — не исполняю")
        return None
    return d


def _svc_drop(token):
    """Метка отработала (или отвергнута) — убрать и из памяти, и с диска: иначе после перезапуска
    уже нажатая кнопка сработала бы ВТОРОЙ раз, то есть записала бы то же дважды."""
    _SVC_TOKENS.pop(token, None)
    _svc_tokens_save()


def _svc_question_open(chat_id, topic_id):
    """Открыт ли по этой теме вопрос [После замены]/[Просто пробег] (ждём нажатия кнопки).

    Поднятые с диска метки СЮДА НЕ ВХОДЯТ намеренно: этот предикат гасит ПОВТОРНЫЙ вопрос в
    текущем разговоре, а не отвечает «висит ли где-то кнопка». Считай мы их — после перезапуска
    вчерашняя метка глушила бы сегодняшний вопрос. Поведение остаётся байт-в-байт прежним."""
    return any(d.get("chat") == chat_id and d.get("topic") == topic_id and not d.get(_SVC_TOKEN_OLD)
               for d in _SVC_TOKENS.values())


def msg_oil_or_km(bike, km):
    """Вопрос с двумя вариантами: фото ПОСЛЕ замены масла или просто текущий пробег (RU/TH)."""
    b = f" · 📌 {bike}" if bike else ""
    return (
        f"🐀 Splinter{b}\n"
        f"🇹🇭 📟 {km} กม. — รูปนี้ถ่าย «หลังเปลี่ยนน้ำมัน» หรือ «แค่เลขไมล์ปัจจุบัน» ครับ? กดปุ่มด้านล่าง 👇\n"
        f"🇷🇺 📟 {km} км — это фото ПОСЛЕ замены масла или просто текущий пробег? Нажми кнопку 👇"
    )


def msg_oil_need_trusted(bike, km):
    """«Да» пришло от недоверенного (техник) → запись в журнал подтверждает Пым/владелец."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" на {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 🔧 การบันทึกการเปลี่ยนน้ำมันเครื่อง ยืนยันโดย {PYM_HANDLE} หรือเจ้าของเท่านั้น. "
        f"{PYM_HANDLE} ยืนยันการเปลี่ยนน้ำมัน{b_th} = {km} กม. ไหมครับ? ตอบ «ใช่» หรือ «ไม่»\n"
        f"🇷🇺 🔧 Запись ТО в журнал подтверждает {PYM_HANDLE} или владелец. "
        f"{PYM_HANDLE}, подтвердите замену масла{b_ru} = {km} км? да/нет"
    )


def msg_oil_backdated_confirm(bike, km):
    """Переспрос Пыму: замена масла задним числом на N км — подтвердить запись в кол.I?"""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 เปลี่ยนน้ำมัน{b_th} ที่ {km} กม. (ย้อนหลัง) — ยืนยันบันทึก ТО (col.I) ไหมครับ? {PYM_HANDLE} 🙏\n"
        f"{_SEP}\n"
        f"🇷🇺 📟 Замена масла{b_ru} задним числом на {km} км — подтвердить запись в ТО (кол.I)? {PYM_HANDLE}"
    )


def msg_oil_backdated_invalid(bike, km, reason_ru):
    """Сообщение об ошибке валидации при записи задним числом."""
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 📟 ไมล์เปลี่ยนน้ำมัน{b_th} {km} กม. ตรวจสอบไม่ผ่าน: {reason_ru} ระบุตัวเลขที่ถูกต้องครับ 🙏\n"
        f"{_SEP}\n"
        f"🇷🇺 📟 Пробег замены масла{b_ru} {km} км — не прошёл проверку: {reason_ru}. Уточни правильное число 🙏"
    )


# ===================== ИНТЕРВАЛЫ ТО из книги знаний (Brain) с фоллбэком на хардкод =====================
# Бот читает блок ```json SERVICE_INTERVALS``` из knowledge_base через read_doc, кэширует ~10 мин.
# Docs флапает → ЛЮБАЯ ошибка чтения/парса = фоллбэк на хардкод (расчёт ТО НЕ должен падать).
# Хардкод-дубли (_oil_interval / oil_interval_for) НЕ удалены — это и есть фоллбэк.
_SVC_INTERVALS_CACHE = {"data": None, "ts": 0.0}
# Интервалы статичны (меняются раз в месяцы) → длинный TTL: read_doc книги знаний почти никогда
# не попадает в КРИТИЧЕСКИЙ путь ответа на «Да» (фикс D «задержка после Да»). Правка интервалов в книге
# подхватится в пределах часа без рестарта; рестарт/prewarm_service_intervals() перечитывают сразу.
_SVC_INTERVALS_TTL = 3600   # 1 час (было 10 мин)
_SVC_INTERVALS_FALLBACK = {
    "oil": {"scooter": 4000, "moto": 5000},
    "gear": {"scooter": 4000, "moto": None},
    "abs": 10000,
    "airfilter": 20000,
    "oilfilter": {"ref": 20000},
    "scooter_keywords": ["nmax", "xmax", "adv", "forza", "pcx", "click"],
    "moto_default": 5000,
}


def _parse_service_intervals_block(text):
    """Достать JSON из блока ```…SERVICE_INTERVALS\\n{...}``` в knowledge_base. None если нет/кривой.
    Захватываем ВСЁ между маркером и закрывающим ``` (вложенные {} — поэтому не \\{.*?\\})."""
    m = _re_pl.search(r"SERVICE_INTERVALS[^\n]*\n(.*?)```", text or "", _re_pl.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(1).strip())
        return d if isinstance(d, dict) and "oil" in d else None
    except Exception:
        return None


def _load_service_intervals(bridge):
    """dict интервалов: из книги знаний (кэш ~10 мин) ИЛИ фоллбэк-хардкод. НЕ кидает исключений."""
    now = _time.time()
    c = _SVC_INTERVALS_CACHE
    if c["data"] is not None and now - c["ts"] < _SVC_INTERVALS_TTL:
        return c["data"]
    data = None
    try:
        r = bridge._call("read_doc", name="knowledge_base")
        if r.get("ok"):
            data = _parse_service_intervals_block(r.get("text", ""))
            if data:
                log.info("  → интервалы ТО: прочитаны из книги знаний")
    except Exception:
        log.warning("  → интервалы ТО: read_doc упал — фоллбэк на хардкод")
    if not data:
        data = _SVC_INTERVALS_FALLBACK
    c["data"], c["ts"] = data, now
    return data


def prewarm_service_intervals(bridge):
    """Фикс D: прогреть кэш интервалов на старте (один read_doc книги знаний), чтобы ПЕРВЫЙ ответ
    на «Да» после рестарта не платил холодное чтение Drive в критическом пути квитанции.
    Зовётся из bot.on_startup после ping Bridge. Best-effort: при ошибке тихо живём на фоллбэке."""
    try:
        _load_service_intervals(bridge)
        log.info("  → интервалы ТО: кэш прогрет на старте (фикс D)")
    except Exception:
        log.warning("  → интервалы ТО: прогрев на старте не удался (фоллбэк/ленивое чтение)")


def _bike_class(bike_name, intervals):
    """'scooter' / 'moto' по ключевым словам блока. XADV → moto (его интервал масла = мото)."""
    n = str(bike_name).lower().replace("-", "").replace(" ", "")
    if "xadv" in n:
        return "moto"
    kws = intervals.get("scooter_keywords") or _SVC_INTERVALS_FALLBACK["scooter_keywords"]
    return "scooter" if any(k in n for k in kws) else "moto"


def _service_interval(kind, bike_name, bridge):
    """Интервал ТО (км) для типа kind (oil/gear/abs/airfilter) и байка. None = НЕ трекать
    (напр. gear на мото/XADV). Источник — книга знаний с фоллбэком на хардкод."""
    iv = _load_service_intervals(bridge)
    spec = iv.get(kind)
    if spec is None:                                 # книга неполна → пер-видовой хардкод-фоллбэк
        spec = _SVC_INTERVALS_FALLBACK.get(kind)     # (гарантирует airfilter=20000, abs=10000 и т.д.)
    if spec is None:
        return None
    if isinstance(spec, dict):                       # oil/gear: по типу байка
        val = spec.get(_bike_class(bike_name, iv))
        return int(val) if val else None
    try:                                             # abs/airfilter: одно число на всех
        return int(spec)
    except (ValueError, TypeError):
        return None


def _run_service_tracker(bridge, chat_id, topic_id, bike, mileage):
    """service_upsert(current_km) → словарь статуса ТО. None если байк/число невалидны. НЕ шлёт сообщений."""
    if not bike:
        return None
    try:
        km = int(str(mileage).replace(" ", ""))
    except (ValueError, TypeError):
        return None
    fleet_bike = bridge.find_bike(bike)
    oil_last = fleet_bike.get("oil_last_km") if fleet_bike else None
    name_l = str(fleet_bike.get("name", bike)).lower() if fleet_bike else str(bike).lower()
    # Интервал масла — из книги знаний (Фаза 2 ЧАСТЬ A), фоллбэк на хардкод _oil_interval при флапе Docs.
    interval = _service_interval("oil", name_l, bridge) or _oil_interval(name_l)
    up = dict(bike=bike, topic_id=topic_id or "", current_km=km, interval_km=interval)
    if oil_last:
        up["last_service_km"] = oil_last
    res = bridge.service_upsert(**up)
    log.info(f"  → ТО {bike}: oil_last(I)={oil_last} interval={interval} → {res}")
    # Запомнить что реально записали — для текстовой коррекции пробега (фикс _row22).
    if res.get("ok"):
        _LAST_RECORDED_KM[(chat_id, topic_id)] = (km, _time.time())
    return {"km": km, "status": res.get("status"), "next_km": res.get("next_km"),
            "km_left": res.get("km_left"), "stype": res.get("service_type", "oil")}


def _service_debt_on():
    """Ветка жива? Ручка `SERVICE_DEBT` (.env). `0` → ни строки долга, ни своей ветки сторожа."""
    return service_debt.enabled(_os.getenv(service_debt.FLAG_ENV))


def _sp_debt_open(bridge, chat_id, topic_id, bike, kinds, km, door, oil_hint=False):
    """ДОЛГ ЗАВОДИТСЯ ДО ПОКАЗА КНОПКИ — руки для ОБЕИХ кнопочных дверей (решение — `service_debt`).

    Почему именно ДО, а не после нажатия: носителей у принятой работы было два, и оба нестойкие —
    токен в памяти процесса (`_SVC_TOKENS`, рестарт стирает) и текст сообщения с кнопкой (его
    удаляет `_clear_cycle_msgs` на терминале другого цикла). Строка листа переживает и то и другое,
    поэтому она обязана появиться РАНЬШЕ, чем человек увидит кнопку: только так работа переживает
    ненажатие. Доказанный случай — `tok=18` (NMAX 155 GREY 5960, 01.08: принято 2, записано 0).

    FAIL-SAFE В СТОРОНУ КНОПКИ: мост молчит → строку не завели, но кнопку показываем как
    показывали. Долг — это добавленная видимость, а не новый забор перед работой человека.
    """
    if not _service_debt_on() or not bike:
        return None
    # ПРИЁМ СУДИТСЯ ПЕРВЫМ, ДО ЕДИНОГО ОБРАЩЕНИЯ К МОСТУ: работа не принята (числа нет · замену
    # никто не объявлял) → выходим здесь, и вопрос человеку не платит мосту ничего.
    _ok, _why = service_debt.accepted(door, kinds, km, oil_hint=oil_hint)
    if not _ok:
        return None
    try:
        prev = _sp_open(bridge, chat_id, topic_id, bike) or {}
    except Exception:
        log.exception("  → долг ТО: открытую заявку не прочитать — сольём перечни без неё")
        prev = {}
    f = service_debt.open_fields(door, kinds, km, oil_hint=oil_hint,
                                 prev_declared=_sp_split(prev.get("declared")),
                                 prev_done=_sp_split(prev.get("done")))
    if f is None:
        return None
    # ПОЗИЦИОННЫЙ СЛЕД В `note` — единственное поле строки, которого следующий визит того же
    # байка НЕ передаёт, а мост сохраняет из `cur`. Долг, стоявший на `done`/`status`, сосед
    # затирал молча (живой 5960: 01.08 abs,pads@41357 → 22.08 gear@41641 в ТОЙ ЖЕ строке).
    _note = service_debt.ledger_add(prev.get("note"), f["kinds"], f["odometer"])
    try:
        r = bridge.service_pending_upsert(
            chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
            declared=_sp_join(f["declared"]), done=_sp_join(f["done"]),
            odometer=f["odometer"], status=f["status"], note=_note)
    except Exception:
        log.exception(f"  → долг ТО {bike}: строка НЕ завелась (мост упал) — кнопку всё равно даём")
        return None
    if not (isinstance(r, dict) and r.get("ok")):
        log.warning(f"  → долг ТО {bike}: строка НЕ завелась ({(r or {}).get('error')}) — "
                    f"кнопку даём, но следа у работы нет")
        return None
    log.info(f"  → долг ТО заведён ДО кнопки: {bike} [{','.join(f['kinds'])}] "
             f"{f['odometer']} км · дверь «{door}» · {f['why']}")
    return f


def _sp_debt_cell(bridge, bike, kinds, odometer):
    """РУКИ признака «перечитанная клетка регистра»: сходить в Лист1 и принести ВЕЛИЧИНУ.

    Своего суждения не выносит — сравнение `клетка ≥ долг` делает `service_debt.verdict`. Здесь
    важно именно `≥`, а не `==` (`write_fact` требует равенства): владелец, записавший работу
    рукой, кладёт СВОЁ число, обычно большее. Любая дырка → `read=False`, и записанным это НЕ
    считается. Цену платит только строка, которая иначе будет ШУМЕТЬ, — вызов стоит за порогом
    громкости, здоровый путь не платит ничего.
    """
    ks = [k for k in (kinds or []) if k in _SP_COL_KINDS]
    if not ks:
        return {"read": False, "km": None, "detail": "колоночных видов в долге нет — регистра нет"}
    want = str(_plate_from_name(bike) or "")
    if not want:
        return {"read": False, "km": None, "detail": f"номер байка из «{bike}» не выделен"}
    try:
        fr = bridge.fleet(cells=True)
    except Exception as e:
        return {"read": False, "km": None, "detail": f"парк не прочитан ({e})"}
    if not isinstance(fr, dict) or not fr.get("ok"):
        return {"read": False, "km": None,
                "detail": f"парк не прочитан (мост: {(fr or {}).get('error')})"}
    rows = ((fr.get("data") or {}).get("bikes") or [])
    hits = [b for b in rows if isinstance(b, dict) and _plate_from_name(b.get("name", "")) == want]
    if len(hits) != 1:
        return {"read": False, "km": None, "detail": f"строк парка по {want}: {len(hits)}"}
    best = None
    for k in ks:
        field = write_fact.field_for(k)
        if field is None:
            continue
        try:
            cell = bridge.cell(hits[0], field)
        except Exception as e:
            return {"read": False, "km": None, "detail": f"клетка «{field}» не прочитана ({e})"}
        if not getattr(cell, "ok", False):
            say = getattr(cell, "say", None)
            return {"read": False, "km": None,
                    "detail": f"клетка «{field}»: {say() if callable(say) else 'не разобрана'}"}
        got = service_debt._int(getattr(cell, "payload", None))
        # Партия закрыта, только если КАЖДАЯ её колоночная позиция легла → берём слабейшую клетку.
        if got is None:
            return {"read": False, "km": None, "detail": f"клетка «{field}» без числа"}
        best = got if best is None else min(best, got)
    return {"read": True, "km": best, "detail": f"регистры {','.join(ks)} прочитаны"}


def _sp_debt_close(bridge, chat_id, topic_id, bike, write=None, cell=None, human=None,
                   odometer=None, kinds=(), batch=None, row_terminal=False, row=None):
    """ЕДИНСТВЕННАЯ ДВЕРЬ ЗАКРЫТИЯ — только по вердикту `service_debt.verdict`, то есть только по
    ДОКАЗАННОМУ. Второй двери в системе нет: прямой `service_pending_close` из `_sp_write_done`
    (легаси-хвост фазы 2, находка Н4 ревизии `930da84`) ходил мимо вердикта и закрывал строку даже
    при непустом `failed` — теперь и он идёт сюда.

    ЗАМОК: не доказано — строка остаётся открытой, и молчать о ней нельзя. «Проверить не удалось»
    закрытием не является; по таймеру не закрывается ничего и никогда (у `verdict` параметра
    возраста нет вовсе).

    ЧТО ДЕЛАЕТ ВЕРДИКТ, А ЧТО `settle`: первый отвечает «долг закрыт ли», вторая — «чья строка и
    какая позиция». Поэтому ПЕРЕД тем как что-то закрыть, дверь СПРАШИВАЕТ МИР (одно чтение), а
    не пишет вслепую: раньше на месте этого чтения стоял слепой POST, и он же дописывал строку-эхо
    там, где закрывать было нечего. Чтение вместо записи — строго дешевле по последствиям.

      batch        — что дверь принесла ЦЕЛИКОМ (партия), если следа в ноте ещё нет;
      row_terminal — дверь и есть терминал самой заявки (фаза 2), «не сделано» ей законно;
      row          — уже прочитанная строка (сторож её держит в руках — не платим за второе чтение).
    """
    if not _service_debt_on() or not bike:
        return None
    v = service_debt.verdict(write=write, cell=cell, human=human, odometer=odometer)
    log.info("  → " + service_debt.line(v, bike, kinds))
    if not v["closed"]:
        return v
    it = row if row is not None else _sp_open(bridge, chat_id, topic_id, bike)
    if not it:
        # Н1: открытой строки нет (или мост молчит) — закрывать НЕЧЕГО. Прежде здесь уходил
        # слепой close, а он upsert: мост ДОПИСЫВАЛ пустую строку о заявке, которой не было.
        v["applied"] = "открытой строки нет — эха не пишем"
        log.info(f"  → долг ТО {bike}: {v['applied']}")
        return v
    s = service_debt.settle(it.get("note"),
                            declared=_sp_split(it.get("declared")),
                            done=_sp_split(it.get("done")),
                            closing=list(kinds or ()),
                            batch=list(batch if batch is not None else (kinds or ())),
                            odometer=odometer, row_terminal=row_terminal)
    v["applied"] = s["why"]
    v["remaining"] = s["remaining"]
    if not s["own"] or not s["changed"]:
        log.info(f"  → долг ТО {bike}: {s['why']} — строку не трогаем")
        return v
    try:
        if s["close_row"]:
            bridge.service_pending_close(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                         bike=bike, note=s["note"])
            log.info(f"  → долг ТО {bike}: строка ЗАКРЫТА по признаку «{v['by']}» — {s['why']}")
        else:
            bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                          bike=bike, note=s["note"])
            log.info(f"  → долг ТО {bike}: {s['why']} (признак «{v['by']}»)")
    except Exception:
        log.exception(f"  → долг ТО {bike}: применение закрытия упало (долг остался открытым)")
    return v


async def _ask_oil_or_km(context, chat_id, topic_id, bike, km, status, next_km, km_left,
                         oil_hint=False, bridge=None):
    """Задать вопрос кнопками [После замены]/[Просто пробег] (фиксация через явный ответ).

    ДОЛГ ЗАВОДИТСЯ ТОЛЬКО ПРИ `oil_hint`, и это ЗАМЕР, а не вкус: за 83 суток трекер отработал 129
    раз, `due/overdue` вышло 55, а записей масла — 8. Заводи долг на каждом показе кнопки — и ≥47
    строк висели бы по работе, которую НИКТО не заявлял (байку просто пришёл срок, человек прислал
    фото приборки). Сторож, который держит всегда, не лучше того, который не держит никогда.
    `oil_hint` = `_is_oil_done_marker` = человек СКАЗАЛ, что замена сделана, — вот это принятая
    работа; сам срок ТО есть НАШ вопрос человеку, а не его заявка."""
    _debt = (_sp_debt_open(bridge, chat_id, topic_id, bike, ["oil"], km,
                           service_debt.DOOR_OIL, oil_hint=oil_hint) if bridge is not None else None)
    tok = _svc_put({"chat": chat_id, "topic": topic_id, "bike": bike or "", "km": str(km),
                    "status": status, "next_km": next_km, "km_left": km_left,
                    "debt": bool(_debt)})
    # Кнопки в ДВА ряда, тайский ПЕРВЫМ (тайцы — основные в обслуживании; RU не теряется на узком экране).
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 หลังเปลี่ยนน้ำมัน / После замены", callback_data=f"svc:oil:{tok}")],
        [InlineKeyboardButton("📷 แค่เลขไมล์ / Просто пробег", callback_data=f"svc:km:{tok}")],
    ])
    # ЗАМОК ПОВТОРОВ (вид H). Состояние = ВЕРДИКТ ТО (статус + следующий порог), а НЕ текущий
    # пробег: он ползёт с каждой поездкой и делал бы вопрос «новым» на каждом фото приборки.
    # Заменили масло → next_km прыгнул → состояние другое → вопрос снова законен.
    sent = await _hint_send(context, kind="H", bike=bike,
                            state=("oil_or_km", status, next_km),
                            chat_id=chat_id, topic_id=topic_id,
                            text=msg_oil_or_km(bike, km), reply_markup=kb)
    if sent is not HINT_SKIPPED:
        _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос → удалить на финале


async def _after_mileage(context, bridge, chat_id, topic_id, bike, mileage, oil_hint=False):
    """Пробег подтверждён (прошёл сторож B). Прогоняем ТО-трекер; если замена осмысленна
    (ТО due/overdue ИЛИ была подсказка-маркер) — спрашиваем кнопками. Иначе — квитанция «пробег принят»."""
    info = _run_service_tracker(bridge, chat_id, topic_id, bike, mileage)
    if not info:
        return
    # Сосуществование с двухфазным потоком: если по теме открыта ТО-заявка — старый одно-фазный
    # вопрос [После замены]/[Просто пробег] НЕ задаём (запись по заявке владеет фаза-2 + «да» Пыма).
    _sp_owns = bool(_sp_open(bridge, chat_id, topic_id, bike))
    if (info["status"] in ("due", "overdue") or oil_hint) and not _sp_owns:
        await _ask_oil_or_km(context, chat_id, topic_id, bike, info["km"],
                             info["status"], info["next_km"], info["km_left"],
                             oil_hint=oil_hint, bridge=bridge)
        # НЕ финал — задали вопрос [После замены]/[Просто пробег], цикл продолжается. Промежутки НЕ чистим.
    else:
        # ТО в норме = ТЕРМИНАЛ цикла. Масло → накопитель; ОДНА сводка (масло+история+столбцы) вместо
        # отдельного msg_mileage_ok. Если в накопителе ничего (чистый пробег без работ) — сводка сама даст
        # «пробег + ТО в норме» (как раньше msg_mileage_ok).
        acc = _summary_acc(chat_id, topic_id)
        acc["current_km"] = str(info["km"])
        acc["oil"] = {"km": info["km"], "next": info["next_km"], "status": info.get("status", "ok")}
        await _emit_summary(context, chat_id, topic_id, bike)
        await _clear_cycle_msgs(context, chat_id, topic_id)   # ЧАСТЬ D: финал → чистим вопросы
    # Фаза 2: на приходе пробега прогнать и НЕ-масляные ТО (gear/abs/возд.фильтр), по кому есть запись.
    await _check_other_services(context, bridge, chat_id, topic_id, bike, info["km"])


async def _check_other_services(context, bridge, chat_id, topic_id, bike, km):
    """Фаза 2 (зеркало масла): на приходе пробега пересчитать НЕ-масляные ТО (gear/abs/airfilter),
    по кому есть SERVICE-запись для этого байка; при просрочке — закрепить напоминание (stype-aware).
    До первой фиксации J/K/L записей нет → ничего не делает. Масло обрабатывается своим флоу выше."""
    try:
        recs = bridge.service_list().get("items", [])
    except Exception:
        log.exception("  → ТО (доп.типы): не смог прочитать service_list")
        return
    try:
        km_int = int(str(km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return
    for rec in recs:
        kind = str(rec.get("service_type", ""))
        if kind in ("", "oil") or not _same_bike(rec.get("bike"), bike):
            continue
        iv = _service_interval(kind, rec.get("bike") or bike, bridge)
        if not iv:
            continue
        try:
            res = bridge.service_upsert(bike=rec.get("bike") or bike, topic_id=topic_id or "",
                                        service_type=kind, current_km=km_int, interval_km=iv)
        except Exception:
            log.exception(f"  → ТО {kind}: service_upsert на пробеге упал")
            continue
        if res.get("status") in ("due", "overdue"):
            log.info(f"  → ТО {kind} {res.get('status')}: next_km={res.get('next_km')} → напоминание")
            try:
                await _pin_overdue_reminder(context, bridge, chat_id, topic_id, bike,
                                            km_int, res.get("next_km"), res.get("status"), stype=kind)
            except Exception:
                log.exception(f"  → ТО {kind}: ошибка напоминания")


async def _close_service_reminder(context, bridge, chat_id, topic_id, bike):
    """После записи ТО — снять ВСЕ закреплённые ТО-напоминания (они копились по циклам) +
    очистить pinned_msg_id записи + закрыть открытые «важное» по этой теме (best-effort)."""
    canon, pin = None, None
    try:
        rec = next((r for r in bridge.service_list().get("items", [])
                    if _same_bike(r.get("bike"), bike)), {})
        canon = rec.get("bike") or bike
        pin = rec.get("pinned_msg_id")
    except Exception:
        log.exception("  → ТО: ошибка чтения записи для снятия закрепа")
    # Снять закрепы: в теме (форум) тема = ОДИН байк → там только наши ТО-пины; снимаем ВСЕ разом
    # (одиночный unpin оставлял старые накопленные пины висеть). Фоллбэк — открепить последний id.
    try:
        if topic_id is not None:
            await context.bot.unpin_all_forum_topic_messages(chat_id=chat_id, message_thread_id=topic_id)
        elif pin:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=int(pin))
    except Exception as e:
        log.warning(f"  → ТО: не смог открепить напоминания темы: {e}")
        if pin:
            try:
                await context.bot.unpin_chat_message(chat_id=chat_id, message_id=int(pin))
            except Exception as e2:
                log.warning(f"  → ТО: фоллбэк-открепление не вышло: {e2}")
    # Очистить pinned_msg_id записи (идемпотентность: повторное закрытие не дёргает старый id).
    if canon:
        try:
            bridge.service_set_pin(bike=canon, service_type="oil", pinned_msg_id="")
        except Exception:
            log.exception("  → ТО: не смог очистить pinned_msg_id записи")
    try:
        for it in bridge.important_list(status="open").get("items", []):
            if topic_id is not None and str(it.get("topic_id")) == str(topic_id):
                bridge.important_close(row=it.get("_row"), confirmed_by="Splinter (ТО Oil закрыто)")
    except Exception:
        log.exception("  → ТО: ошибка закрытия important")


async def _write_oil(context, bridge, chat_id, topic_id, bike, km, confirmed_by=""):
    """Боевая запись ТО Oil в Лист1 кол.I (set_fleet_oil confirmed=True) + снять закреп + отчёт.
    Вызывается ТОЛЬКО после [После замены] от доверенного. Резолвит ГОЛЫЙ номер байка.

    ЧЕМ ЭТА ДВЕРЬ ОТЛИЧАЕТСЯ ОТ ДВЕРИ ФАЗЫ 2 И ПОЧЕМУ КНОПКА ОТМЕНЫ СЮДА НЕ ПОПАЛА (14.08.2026):
    у двери фазы 2 есть СВОЯ квитанция акта, и кнопка села в её клавиатуру одной строкой
    (`reply_markup=_svc_undo_kb(...)` в ветках `done`/`codo`/«число-да»). Здесь своего сообщения
    нет вовсе: результат уезжает в накопитель `_summary_acc`, а единственный видимый след акта —
    ОБЩАЯ и ЗАКРЕПЛЯЕМАЯ сводка `_emit_summary`, у которой параметра клавиатуры не было. Плюс
    расписка `res` читалась ровно на один флаг `ok` и умирала — журнала отмены эта дверь не вела
    вовсе. Теперь акт помнится ИЗ ТОЙ ЖЕ расписки (лишних обращений к мосту ноль), а кнопка едет
    на сводке этого акта — НОВЫХ сообщений в группу не добавлено ни одного.

    ДОЛГАЯ ЖИЗНЬ ЗАКРЕПА КНОПКЕ НЕ СТРАШНА: сводка висит закреплённой до следующего цикла, но
    замки живут не в кнопке, а в `undo_last.verdict` — старше 3 ч отвечает честным «не ручаюсь,
    что запись всё ещё последняя», после новой записи — «не последняя», после рестарта бота —
    «журнала нет». Кнопка, пережившая своё окно, не отменяет, а объясняет."""
    plate = _plate_from_name(bike)
    if not plate:
        fb = bridge.find_bike(bike) or {}
        plate = _plate_from_name(fb.get("name", ""))
    if not plate:
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс: ответ кнопки записи
                          text=("🐀 Splinter\n"
                                "🇹🇭 ขอโทษครับ ไม่พบเลขทะเบียนรถ — บอกชื่อรุ่น+เลขให้หน่อยครับ 🙏\n"
                                "🇷🇺 Не смог определить номер байка для записи ТО — уточни модель+номер 🙏"))
        return
    try:
        km_int = int(str(km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return

    res = bridge.set_fleet_oil(number=plate, oil_km=km_int, confirmed=True)
    log.info(f"  → ТО Oil set_fleet_oil({plate},{km_int},confirmed=True) → {res}")
    if res.get("ok"):
        # Масло записано (замена) = ТЕРМИНАЛ цикла. Отдельное «✅ ТО Oil обновлено» НЕ шлём — копим в
        # накопитель, ниже одна сводка. next = km + интервал (из книги знаний, фоллбэк на хардкод).
        _canon = res.get("bike_name", bike)
        _iv = _service_interval("oil", _canon, bridge) or _oil_interval(_canon)
        # ОТМЕНА: акт помним ИЗ ТОЙ ЖЕ расписки, из которой строкой выше прочитан флаг `ok`.
        # Журнал трогаем ТОЛЬКО на успехе: провал записи мир не менял, и обнулять указатель темы
        # (то есть гасить кнопку прошлой, ЛЕГШЕЙ записи) ему не за что.
        _undo_tok = _svc_undo_remember_write(chat_id, topic_id, _canon or bike, plate,
                                             confirmed_by, km_int, "oil", res)
        # ПРИЗНАК 1 ИЗ ТРЁХ — ДОКАЗАННАЯ ЗАПИСЬ (зеркало двери столбца, см. `_write_service_col`).
        _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=["oil"], odometer=km_int,
                       write={"landed": True, "known": True,
                              "detail": f"oil = {km_int} км, расписка моста ok"})
        acc = _summary_acc(chat_id, topic_id)
        acc["current_km"] = str(km_int)
        acc["oil"] = {"km": km_int, "next": (km_int + _iv) if _iv else None, "status": "ok"}
        await _close_service_reminder(context, bridge, chat_id, topic_id, bike)   # снимает ВСЕ старые пины (unpin_all)
        _sum_msg = await _emit_summary(context, chat_id, topic_id, bike,
                                       reply_markup=_svc_undo_kb(_undo_tok))
        await _clear_cycle_msgs(context, chat_id, topic_id)   # ЧАСТЬ D: финал → чистим вопросы
        # П.3: ЗАКРЕП ИТОГА после замены масла. Старый итог/просрочка-пин уже сняты unpin_all выше →
        # не копятся. Сводку (итог) закрепляем сверху; на следующей замене unpin_all снимет её перед новой.
        if _sum_msg is not None:
            try:
                await context.bot.pin_chat_message(chat_id=chat_id, message_id=_sum_msg.message_id,
                                                   disable_notification=True)
                log.info(f"  → итог ТО закреплён: {bike} msg={_sum_msg.message_id}")
            except Exception as e:
                log.warning(f"  → не смог закрепить итог ТО (права админа?): {e}")
        # ИНВАРИАНТ: unpin_all выше снял ВСЕ пины темы, в т.ч. кнопку «ℹ️ Инфо» → пере-закрепить её
        # ПОСЛЕ итога, чтобы кнопка была СВЕРХУ (Q2 — всегда видна). Любой unpin_all в теме → следом _repin_info.
        await _repin_info(context, chat_id, topic_id)
    else:
        # ОТКАЗ ГОВОРИТ, ЧТО ДЕЛАТЬ (правило владельца 23.08). Прежние ветки называли числа, но
        # не действие, а последняя печатала человеку внутренний код моста дословно.
        #
        # ДВЕРЬ САМА ОТКРЫВАЕТ ВОПРОС О ПРИЧИНЕ (23.08.2026, шаг 2 цели 120). Слова этого отказа
        # уже обещали выбор — `reply_floor._SAY["oil_decreasing"]` дословно говорит «понизить
        # можно: выбери причину и напиши пояснение своими словами», — а выбирать было НЕ ИЗ
        # ЧЕГО: `_odo_lower_ask(register="oil")` был написан и покрыт тестом, но из этой ветки
        # не звался, и живым `register="oil"` не приходил НИ ОТКУДА. Обещание без машины и есть
        # тот класс, что уже ловили у карточек владельцу: обещанное обязано случаться.
        #
        # ЗАПИСАННОЕ ЧИСЛО БЕРЁТСЯ ИЗ ТОЙ ЖЕ РАСПИСКИ, из которой строкой выше прочитан флаг
        # `ok` (`old_oil`), — у моста НЕ спрашиваем НИ ОДНОГО лишнего раза, тем же приёмом, что
        # у `_svc_undo_remember_write`. Нет числа в расписке → `odo_lower.ask` не построит
        # расхождения, вопрос не откроется, и человек получит прежние слова.
        _res = res if isinstance(res, dict) else {}
        _asked = False
        if odo_lower.opens_question(_res.get("error")) and _odo_lower_on():
            _rec = _res.get("old_oil")
            if _rec is None:
                _rec = _res.get("old_km")
            try:
                _asked = await _odo_lower_ask(context, chat_id, topic_id,
                                              _res.get("bike_name") or bike, _rec, km_int,
                                              source="кнопка записи", register="oil")
            except Exception:
                # Сорвался вопрос — человек всё равно услышит слова отказа. Правило 1 («никогда
                # не молчать») сильнее нового удобства: молчание — единственный запрещённый исход.
                log.exception("  → ПОНИЖЕНИЕ: не смог открыть вопрос о причине (fail-safe: слова)")
                _ODO_LOWER_PENDING.pop((chat_id, topic_id), None)
                _asked = False
        if not _asked:
            # ПРЕЖНИЙ ПУТЬ БАЙТ-В-БАЙТ: ручка `ODO_LOWER=0`, чужой код отказа, число не названо
            # или понижения нет вовсе. Молчанием ни один из этих случаев не кончается.
            detail_ru, detail_th = _refuse_words(res, plate=plate, sent=km_int)
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс: ответ кнопки записи
                              text=(f"🐀 Splinter\n🇹🇭 ⚠️ {detail_th}\n🇷🇺 ⚠️ {detail_ru}"))
        # Открылся вопрос — он и ЕСТЬ ответ: те же три числа плюс выбор причины. Печатать рядом
        # ещё и слова отказа значило бы сказать одно дважды, причём вторая копия снова обещала
        # бы выбор, который уже на экране.


def _refuse_words(res, *, plate="", sent=None):
    """Ответ моста → ЧЕЛОВЕЧЕСКИЕ слова отказа: что случилось · какие числа · что делать.

    ЕДИНАЯ ДВЕРЬ слов отказа для обеих дверей записи: две формулировки об одном отказе разошлись
    бы, и человек получил бы два разных ответа на одно событие. Внутренний код в текст не идёт ни
    одной веткой — он уходит в журнал отдельным полем (правило владельца 23.08 «внутренние коды
    человеку не показываются»). Решение — `reply_floor.refusal`, здесь только руки."""
    r = res if isinstance(res, dict) else {}
    err = str(r.get("error") or "")
    recorded = r.get("old_oil")
    if recorded is None:
        recorded = r.get("old_km")
    got = sent if sent is not None else r.get("new_oil", r.get("new_km"))
    drop = r.get("drop")
    if drop is None:
        drop = odo_lower.diff(recorded, got)["drop"]
    say = reply_floor.refusal(err, {
        "plate": plate or r.get("number") or "",
        "recorded": recorded, "sent": got, "drop": drop,
        "threshold": r.get("threshold"), "who": PYM_HANDLE,
    })
    log.info(f"  → отказ записи: код={say['log']} исход={say['state']} "
             f"(человеку показаны слова, не код)")
    return say["ru"], say["th"]


async def _write_oil_backdated(context, bridge, chat_id, topic_id, bike, oil_km, confirmed_by=""):
    """Боевая запись задним числом: set_fleet_oil(oil_km=N, confirmed=True) → кол.I.
    Одометр НЕ трогается: service_upsert только last_service_km, current_km НЕ передаём.
    Вызывается ТОЛЬКО после svc:oilbk от доверенного (Пым/владелец).

    ВТОРАЯ ДВЕРЬ МАСЛА, и она отличается от первой: СВОЯ квитанция у неё ЕСТЬ (сообщение ниже),
    не было только журнала акта и клавиатуры. Поэтому кнопка садится прямо на квитанцию — тем же
    вызовом `_svc_undo_kb`, что у двери фазы 2."""
    plate = _plate_from_name(bike)
    if not plate:
        fb = bridge.find_bike(bike) or {}
        plate = _plate_from_name(fb.get("name", ""))
    if not plate:
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=("🐀 Splinter\n"
                                "🇹🇭 ขอโทษครับ ไม่พบเลขทะเบียนรถ — บอกชื่อรุ่น+เลขให้หน่อยครับ 🙏\n"
                                "🇷🇺 Не смог определить номер байка — уточни модель+номер 🙏"))
        return
    try:
        km_int = int(str(oil_km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return

    res = bridge.set_fleet_oil(number=plate, oil_km=km_int, confirmed=True)
    log.info(f"  → backdated ТО Oil set_fleet_oil({plate},{km_int},confirmed=True) → {res}")
    b_th = f" ({bike})" if bike else ""
    b_ru = f" по {bike}" if bike else ""
    if res.get("ok"):
        _canon = res.get("bike_name", bike)
        _iv = _service_interval("oil", _canon, bridge) or _oil_interval(_canon)
        _next = km_int + _iv if _iv else None
        # service_upsert: только last_service_km — current_km НЕ передаём (не трогаем одометр)
        bridge.service_upsert(bike=bike, service_type="oil",
                              last_service_km=km_int, interval_km=_iv)
        # ОТМЕНА: та же расписка, ноль лишних обращений к мосту (см. `_write_oil`).
        _undo_tok = _svc_undo_remember_write(chat_id, topic_id, _canon or bike, plate,
                                             confirmed_by, km_int, "oil", res)
        next_str = f" · следующее ТО на {_next} км" if _next else ""
        next_th = f" · ТО ครั้งถัดไปที่ {_next} กม." if _next else ""
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=(f"🐀 Splinter\n"
                                f"🇹🇭 ✅ บันทึก ТО น้ำมัน{b_th} ย้อนหลัง = {km_int} กม. แล้วครับ{next_th}\n"
                                f"{_SEP}\n"
                                f"🇷🇺 ✅ ТО Oil{b_ru} задним числом записано: {km_int} км{next_str}"),
                          reply_markup=_svc_undo_kb(_undo_tok))
        log.info(f"  → backdated ТО Oil ЗАПИСАНО: {bike} oil_km={km_int} next={_next}")
    else:
        # Та же дверь слов отказа, что у первой двери масла: двум формулировкам об одном отказе
        # разойтись негде по построению.
        detail_ru, detail_th = _refuse_words(res, plate=plate, sent=km_int)
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=(f"🐀 Splinter\n🇹🇭 ⚠️ {detail_th}\n🇷🇺 ⚠️ {detail_ru}"))


# Метки видов ТО группы B (TH, RU) — для кнопок/квитанций. kind → (тайский, русский).
_SVC_COL_LABEL = {
    "gear":      ("น้ำมันเกียร์", "редуктор (gear)"),
    "abs":       ("น้ำมัน ABS", "ABS"),
    "airfilter": ("ไส้กรองอากาศ", "возд. фильтр"),
}


async def _ask_service_col(context, chat_id, topic_id, bike, kind, km, bridge=None):
    """Кнопка-фиксация регламента группы B (gear→J/abs→K/airfilter→L) в свой столбец Лист1.
    Боевая запись — ТОЛЬКО доверенным (как масло). Пробег показываем в кнопке — человек сверяет.

    ДОЛГ ЗАВОДИТСЯ ДО КНОПКИ И БЕЗУСЛОВНО: сюда заходят только с НАЗВАННОЙ работой (`works`) и
    числом — то есть работа уже принята, и вопрос лишь в том, ляжет ли она. У двери масла условие
    строже (`oil_hint`), и разница объяснена в её шапке."""
    th_lbl, ru_lbl = _SVC_COL_LABEL.get(kind, (kind, kind))
    _debt = (_sp_debt_open(bridge, chat_id, topic_id, bike, [kind], km,
                           service_debt.DOOR_COL) if bridge is not None else None)
    tok = _svc_put({"kind": "svc_col", "chat": chat_id, "topic": topic_id,
                    "bike": bike or "", "svc_kind": kind, "km": str(km),
                    "debt": bool(_debt)})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ บันทึก {th_lbl} / Зафиксировать {ru_lbl}", callback_data=f"svc:col:{tok}")],
    ])
    b = f" · 📌 {bike}" if bike else ""
    sent = await _send(context, chat_id=chat_id, message_thread_id=topic_id,
        text=(f"🐀 Splinter{b}\n"
              f"🇹🇭 🔧 บันทึก «{th_lbl}» = {km} กม. ไหมครับ? กดปุ่ม (ยืนยันโดย {PYM_HANDLE}/เจ้าของ) 👇\n"
              f"🇷🇺 🔧 Зафиксировать «{ru_lbl}» = {km} км? Нажми кнопку (подтверждает {PYM_HANDLE}/владелец) 👇"),
        reply_markup=kb)
    _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос → удалить на финале


async def _write_service_col(context, bridge, chat_id, topic_id, bike, kind, km):
    """Боевая запись регламента группы B в Лист1 (gear→J/abs→K/airfilter→L) через set_fleet_service.
    Вызывается ТОЛЬКО после [Зафиксировать] от доверенного. Резолвит ГОЛЫЙ номер байка.
    Кол.I «ТО Oil» и H не трогает (это set_fleet_oil/стартовый)."""
    th_lbl, ru_lbl = _SVC_COL_LABEL.get(kind, (kind, kind))
    plate = _plate_from_name(bike)
    if not plate:
        fb = bridge.find_bike(bike) or {}
        plate = _plate_from_name(fb.get("name", ""))
    if not plate:
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=("🐀 Splinter\n"
                          "🇹🇭 ขอโทษครับ ไม่พบเลขทะเบียนรถ — บอกชื่อรุ่น+เลขให้หน่อยครับ 🙏\n"
                          "🇷🇺 Не смог определить номер байка для записи — уточни модель+номер 🙏"))
        return
    try:
        km_int = int(str(km).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return
    res = bridge.set_fleet_service(number=plate, kind=kind, km=km_int, confirmed=True)
    log.info(f"  → ТО {kind} set_fleet_service({plate},{kind},{km_int},confirmed=True) → {res}")
    if res.get("ok"):
        # Столбец записан = ТЕРМИНАЛ. Отдельное «✅ Записано» НЕ шлём — копим в накопитель, ниже одна сводка.
        # Фаза 2: трекинг срока (зеркало масла). service_upsert сбрасывает цикл (next_km=km+интервал).
        # gear на мото/XADV (iv=None) — НЕ трекаем, но столбец записан (next в сводке тогда без срока).
        canon = res.get("bike_name", bike)
        # ПРИЗНАК 1 ИЗ ТРЁХ — ДОКАЗАННАЯ ЗАПИСЬ. Долг гасит ОТВЕТ МИРА (расписка сказала `ok`), а
        # не наше намерение записать: строка закрывается вердиктом `service_debt`, а не флагом.
        _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=[kind], odometer=km_int,
                       write={"landed": True, "known": True,
                              "detail": f"{kind} = {km_int} км, расписка моста ok"})
        iv = _service_interval(kind, canon, bridge)
        _col_next = None
        if iv:
            try:
                up = bridge.service_upsert(bike=canon, topic_id=topic_id or "", service_type=kind,
                                           current_km=km_int, last_service_km=km_int, interval_km=iv)
                _col_next = up.get("next_km")
                log.info(f"  → ТО {kind} трекинг: service_upsert(interval={iv}) → next_km={_col_next} status={up.get('status')}")
            except Exception:
                log.exception(f"  → ТО {kind}: service_upsert при фиксации упал (столбец записан)")
        else:
            log.info(f"  → ТО {kind}: не трекаем (нет интервала по типу байка — напр. gear на мото)")
        acc = _summary_acc(chat_id, topic_id)
        acc["current_km"] = str(km_int)
        acc["cols"].append({"kind": kind, "km": km_int, "next": _col_next})
        await _emit_summary(context, chat_id, topic_id, bike)
        await _clear_cycle_msgs(context, chat_id, topic_id)   # ЧАСТЬ D: финал → чистим вопросы
    else:
        # Третья дверь записи — та же единая дверь слов. Понижение колонок J/K/L мост не умеет
        # вовсе (в отличие от кол.I), и отказ теперь говорит об этом ПРЯМО и с действием, а не
        # «не записал, проверь число» про число, которое человек прислал верно.
        detail_ru, detail_th = _refuse_words(res, plate=plate, sent=km_int)
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс: ответ кнопки записи
                          text=(f"🐀 Splinter\n🇹🇭 ⚠️ {detail_th}\n🇷🇺 ⚠️ {detail_ru}"))


async def _pin_overdue_reminder(context, bridge, chat_id, topic_id, bike, km, next_km, status,
                                stype="oil", always_notify=False):
    """Полное напоминание о просрочке ТО (msg_service_due) + закреп. Без записи в кол.I.
    always_notify=True (ответ на кнопку [Просто пробег]) — текст шлём ВСЕГДА, даже если закреп
    свежий; в этом случае не рекрепим. Иначе крепим раз в 5 дней. Матч строки по НОМЕРУ."""
    lst = bridge.service_list().get("items", [])
    rec = next((r for r in lst if _same_bike(r.get("bike"), bike) and str(r.get("service_type")) == stype), {})
    pinned = rec.get("pinned_msg_id")
    last_reminded = rec.get("last_reminded_at")
    now = _time.time()
    need_remind = True
    if last_reminded:
        try:
            need_remind = (now - float(last_reminded)) >= 5 * 24 * 3600
        except (ValueError, TypeError):
            need_remind = True
    if pinned and not need_remind and not always_notify:
        return
    canon = rec.get("bike") or bike
    text = msg_service_due(bike, stype, km, next_km, status)
    try:
        # ЗАМОК ПОВТОРОВ (вид E для масла, E2 для gear/abs/возд.фильтра). Состояние = ВЕРДИКТ
        # регламента (тип + статус + следующий порог), а НЕ текущий пробег: он ползёт сам и
        # выдавал бы просрочку за новый повод на каждом замере. ТО сделали → next_km прыгнул →
        # состояние другое → напоминание законно снова.
        # always_notify — ответ на КНОПКУ человека [Просто пробег]: спросили — отвечаем ВСЕГДА,
        # замок сюда не лезет (повтор по просьбе повтором бота не является).
        if always_notify:
            sent = await _send(context, chat_id=chat_id, text=text, message_thread_id=topic_id)
        else:
            sent = await _hint_send(context, kind=("E" if stype == "oil" else "E2"), bike=bike,
                                    state=("service_due", stype, status, next_km),
                                    chat_id=chat_id, topic_id=topic_id, text=text)
            if sent is HINT_SKIPPED:
                return      # повтор подавлен → сообщения НЕТ, значит и крепить нечего
        if need_remind or not pinned:   # крепим/обновляем ТОЛЬКО когда реально нужно
            if pinned:   # не копим: снимаем ПРОШЛЫЙ закреп перед новым
                try:
                    await context.bot.unpin_chat_message(chat_id=chat_id, message_id=int(pinned))
                except Exception as e:
                    log.warning(f"  → не смог снять прошлый закреп перед новым: {e}")
            try:
                await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id, disable_notification=False)
            except Exception as e:
                log.warning(f"  → не смог закрепить (нужны права админа боту?): {e}")
            bridge.service_set_pin(bike=canon, service_type=stype,
                                   pinned_msg_id=sent.message_id, last_reminded_at=str(now))
            log.info(f"  → ТО напоминание закреплено: {bike} {stype} {status}")
        else:
            log.info(f"  → ТО напоминание (повтор по запросу, без рекрепа): {bike} {stype} {status}")
    except Exception:
        log.exception("  → ошибка отправки/закрепа ТО")


async def handle_service_button(update, context, bridge) -> None:
    """Обработка кнопок [После замены]/[Просто пробег] (CallbackQueryHandler '^svc:' в bot.py).
    [После замены] — запись в Лист1 ТОЛЬКО доверенным (Пым/владелец); техник → просим Пыма нажать.
    [Просто пробег] — в кол.I НЕ пишем: due/overdue → закреп просрочки, иначе квитанция."""
    q = update.callback_query
    if not q:
        return
    try:
        _, action, tok = (q.data or "").split(":", 2)
        token = int(tok)
    except Exception:
        await _btn_answer(q)
        return
    if action == "undo":
        # ОТМЕНА ПОСЛЕДНЕЙ ЗАПИСИ ТО — своя память (`_SVC_UNDO`), поэтому решается ДО общего
        # поиска в `_SVC_TOKENS`: у отмены свои отказы, и общее «кнопка устарела, пришли фото»
        # тут врало бы о том, что делать. Нажать может ЛЮБОЙ в теме (механик и Пым) — записи
        # эта ветка НЕ делает вовсе, она только просит владельца.
        await _svc_undo_ask(q, context, token)
        return

    # МЕТКА СВЕРЯЕТСЯ С МЕСТОМ НАЖАТИЯ (25.08.2026). Адрес операции — чат, тема, байк, пробег —
    # берётся ИЗ МЕТКИ и раньше не сверялся ни с чем: угаданный (или воскресший после рестарта)
    # номер увёл бы запись на чужую тему. Где нажали — знает само сообщение; не знаем (мок, личка)
    # → сверять нечем, ведём себя как прежде.
    _msg = getattr(q, "message", None)
    data = _svc_get(token, getattr(_msg, "chat_id", None),
                    getattr(_msg, "message_thread_id", None))
    if not data:
        await _btn_answer(q)
        try:
            await q.edit_message_text(
                "🐀 Splinter\n"
                "🇹🇭 ⚠️ ปุ่มหมดอายุ (บอทรีสตาร์ท) — รบกวนส่งรูปเลขไมล์อีกครั้งนะครับ 🙏\n"
                f"{_SEP}\n"
                "🇷🇺 ⚠️ Кнопка устарела (перезапуск бота). Пришли фото пробега ещё раз 🙏")
        except Exception:
            pass
        return
    chat_id, topic_id = data["chat"], data["topic"]
    bike, km = data.get("bike", ""), data.get("km", "")

    if action == "fix":
        # [✅ Да] на переспрос текстовой КОРРЕКЦИИ пробега (фикс _row22) — эквивалент текстового «да».
        # Класс H (сторож Б): только ВЛАДЕЛЕЦ авторизует снижение. Проверяем ДО очистки состояния.
        old_km, new_km = data.get("old_km"), data.get("new_km")
        uname = getattr(q.from_user, "username", None) or str(getattr(q.from_user, "id", "?"))
        if not is_owner_user(q.from_user):
            await _btn_answer(q, "Снижение пробега — только владелец / Owner confirms km decrease",
                              show_alert=True)
            log.warning(f"  🔒 сторож Б: fix-btn не от владельца (@{uname}) тема={topic_id} — кнопка живёт")
            return
        await _btn_answer(q, "กำลังแก้… · Исправляю…")
        key = (chat_id, topic_id)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        _PENDING_CORRECTION.pop(key, None)
        clear_awaiting(*key)
        log.info(f"  🔧 fix-btn: @{uname} bike={bike} {old_km}→{new_km}")
        _odoguard_authorize(chat_id, topic_id, new_km, source=f"btn:{uname}")
        try:
            await _apply_correction(context, bridge, chat_id, topic_id, bike, old_km, new_km)
        except Exception:
            log.exception("  → ошибка применения коррекции пробега (кнопка)")
        return

    if action == "mok":
        # [✅ Да] на подтверждение распознанного пробега — эквивалент текстового «да».
        # Сторож B сохранён: если число < floor — не принимаем, шлём msg_mileage_drop.
        await _btn_answer(q)
        mileage = data.get("mileage", "")
        floor = data.get("floor")
        oil_hint = bool(data.get("oil_hint"))
        key = (chat_id, topic_id)
        if floor is not None:
            try:
                if int(str(mileage).replace(" ", "").replace(",", "")) < floor:
                    await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс
                                      text=msg_mileage_drop(bike, mileage, floor))
                    return
            except (ValueError, TypeError):
                pass
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(*key)
        # ЕДИНАЯ ТОЧКА подтверждения (зеркало текстового пути): кнопка «Да» подтверждает ровно то
        # число, о котором спрашивали → откат не нужен, но отложенные инфо-работы дописываются.
        _odo_confirmed(bridge, chat_id, topic_id, bike, mileage, questioned_km=mileage,
                       sender=_sender_from_user(q.from_user), source="кнопка «Да»")
        # (2) B1-хук в КНОПОЧНОМ пути (зеркало текстового handle_mileage_confirm): открытая 'ждёт_факт' заявка →
        # подтверждённый фото-пробег доводит её до кнопки Пыма (запись только по svc:done от доверенного — гейт сохранён).
        try:
            _sp = _sp_open(bridge, chat_id, topic_id, bike) if bike else None
            if _sp and str(_sp.get("status")) == "ждёт_факт":
                _declared = _sp_split(_sp.get("declared"))
                _done = _sp_split(_sp.get("done")) or list(_declared)
                await _sp_advance_to_confirm(context, bridge, chat_id, topic_id, bike, _declared, _done, mileage)
                return
        except Exception:
            log.exception("  → B1(кнопка svc:mok): довод заявки фото-пробегом упал")
        try:
            await _after_mileage(context, bridge, chat_id, topic_id, bike, mileage, oil_hint)
        except Exception:
            log.exception("  → ошибка ТО-трекера (кнопка Да)")
        return

    if action == "col":
        # [Зафиксировать <тип>] группы B (gear/abs/airfilter) → set_fleet_service. ТОЛЬКО доверенный.
        svc_kind = data.get("svc_kind", "")
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец", show_alert=False)
            th_lbl, ru_lbl = _SVC_COL_LABEL.get(svc_kind, (svc_kind, svc_kind))
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс
                              text=(f"🐀 Splinter\n"
                                    f"🇹🇭 🔧 การบันทึก «{th_lbl}» ยืนยันโดย {PYM_HANDLE} หรือเจ้าของเท่านั้น\n"
                                    f"🇷🇺 🔧 Запись «{ru_lbl}» подтверждает {PYM_HANDLE} или владелец"))
            return   # токен и кнопка живут — Пым нажмёт позже
        await _btn_answer(q, "กำลังบันทึก… · Записываю…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        await _write_service_col(context, bridge, chat_id, topic_id, bike, svc_kind, km)
        return

    if action == "oil":
        # [После замены] → боевая запись кол.I. ТОЛЬКО доверенный.
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец", show_alert=False)
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс
                              text=msg_oil_need_trusted(bike, km))
            return   # токен и кнопки живут — Пым нажмёт [После замены] позже
        await _btn_answer(q, "กำลังบันทึกน้ำมันเครื่อง… · Записываю ТО Oil…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        # Кто подтвердил — в журнал отмены («Записал: …» в карточке владельцу), как у двери фазы 2.
        _cb = ("@" + q.from_user.username) if (q.from_user and q.from_user.username) else "trusted"
        await _write_oil(context, bridge, chat_id, topic_id, bike, km, confirmed_by=_cb)
    elif action == "done":
        # ШАГ 5 (КРАСНЫЙ): подтверждение записи факта ТО по заявке. ТОЛЬКО доверенный (trust не ослаблен).
        # Пишет СДЕЛАННЫЕ позиции (кол.I/J/K/L set_fleet_* confirmed=True под сторожем + синк «обслуживание»),
        # прочее → событие. Earth сам нажать НЕ может — бот ждёт Пыма/владельца (токен+кнопка живут).
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец", show_alert=False)
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,   # класс-фикс
                              text=("🐀 Splinter\n"
                                    f"🇹🇭 🔧 บันทึกผลเซอร์วิส ยืนยันโดย {PYM_HANDLE} หรือเจ้าของเท่านั้นครับ\n"
                                    f"{_SEP}\n"
                                    f"🇷🇺 🔧 Запись результата ТО подтверждает {PYM_HANDLE} или владелец"))
            return   # токен и кнопка живут — Пым нажмёт позже
        await _btn_answer(q, "กำลังบันทึก… · Записываю ТО…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        done = data.get("done", []) or []
        odo = data.get("odo", "")
        cb = ("@" + q.from_user.username) if (q.from_user and q.from_user.username) else "trusted"
        written, failed = await _sp_write_done(context, bridge, chat_id, topic_id, bike, done, odo, confirmed_by=cb)
        # ДВЕРЬ 1 (кнопка). Верхняя граница переспросила → вопрос уже отправлен, квитанции быть
        # не должно: «не записано» рядом с вопросом читалось бы как отказ, а это ОЖИДАНИЕ ответа.
        if _sp_ceiling_asked(failed):
            log.info(f"  → ТО фаза2 кнопка {cb}: верхняя граница переспросила, запись не начиналась "
                     f"odo={odo} bike={bike or '?'}")
            return
        # ОБЕ ПОЛОВИНЫ КВИТАНЦИИ — ИЗ ОДНОГО ИСХОДА (14.08.2026). Прежде русская несла
        # отрицательную ветку, а тайская печатала «บันทึกแล้ว» БЕЗУСЛОВНО: 13.08 в одной строке
        # механик читал успех, владелец — «ничего не записано» (байки 4957/37015 и 4724/20747).
        # Три исхода (записано · не записано · неизвестен) и имена работ — в `service_receipt`.
        rec = service_receipt.receipt(written, failed, odo, _SP_KIND_LABEL,
                                     ledger=_svc_ledger_take(chat_id, topic_id))
        # E1: подтверждение через _send_retry — запись (_sp_write_done) УЖЕ прошла и идемпотентна,
        # переотправка безопасна. Без retry ConnectTimeout «съедал» подтверждение → владелец дублировал «Да».
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=(f"🐀 Splinter · 📌 {bike}\n"
                                f"🇹🇭 {rec['th']}\n"
                                f"{_SEP}\n"
                                f"🇷🇺 {rec['ru']}"),
                          reply_markup=_svc_undo_kb(_SVC_UNDO_LAST.get((chat_id, topic_id))))
        log.info(f"  → ТО фаза2 запись по «да» {cb}: written={written} failed={failed} odo={odo} "
                 f"исход={rec['state']}")
    elif action == "bodo":
        # [Работы на другом пробеге] — ТРЕТИЙ ИСХОД карточки. Кнопка НИЧЕГО не пишет: она только
        # открывает вопрос о пробеге и дате партии. Доверие — то же, что у «Подтвердить запись»:
        # карточка адресована Пыму, и разводить два разных права на одной карточке нельзя.
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец",
                              show_alert=False)
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                              text=("🐀 Splinter\n"
                                    f"🇹🇭 🔧 บันทึกผลเซอร์วิส ยืนยันโดย {PYM_HANDLE} หรือเจ้าของเท่านั้นครับ\n"
                                    f"{_SEP}\n"
                                    f"🇷🇺 🔧 Запись результата ТО подтверждает {PYM_HANDLE} или владелец"))
            return   # токен и кнопки живут — Пым нажмёт позже
        await _btn_answer(q, "เลขไมล์อื่น… · Другой пробег…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        try:
            await _batch_odo_ask(context, bridge, chat_id, topic_id, bike,
                                 data.get("done", []) or [])
        except Exception:
            log.exception("  → ПАРТИЯ: вопрос о пробеге и дате не открылся (fail-safe)")
            _BATCH_ODO_PENDING.pop((chat_id, topic_id), None)
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                              text=("🐀 Splinter\n"
                                    "🇹🇭 ⚠️ เปิดคำถามเรื่องเลขไมล์ของงานชุดนี้ไม่สำเร็จ "
                                    "ส่งงานพร้อมเลขไมล์และวันที่มาใหม่ได้ครับ\n"
                                    f"{_SEP}\n"
                                    "🇷🇺 ⚠️ Не смог открыть вопрос о пробеге партии. "
                                    "Пришли работы вместе с пробегом и датой ещё раз 🙏"))
    elif action == "km":
        # [Просто пробег] → в кол.I НЕ пишем. Квитанцию шлём ВСЕГДА (раньше при уже-закреплённой
        # просрочке _pin_overdue_reminder выходил молча → человек видел тишину).
        await _btn_answer(q)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        try:
            km_int = int(str(km).replace(" ", ""))
        except (ValueError, TypeError):
            km_int = km
        # ПРИЗНАК 3 ИЗ ТРЁХ — ЯВНОЕ РЕШЕНИЕ ЧЕЛОВЕКА. «Просто пробег» и означает «работы не было»:
        # человек здесь авторитет, а не свидетель, доказательств сверх его слов не требуется.
        # Зовём ТОЛЬКО если долг на этой двери заводился (`debt` в токене) — иначе платили бы мосту
        # за закрытие несуществующей строки на каждом нажатии.
        if data.get("debt"):
            _uname = ("@" + q.from_user.username) if (q.from_user and q.from_user.username) else "человек"
            _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=["oil"], odometer=km_int,
                           human={"decided": True, "who": _uname,
                                  "detail": "нажато «Просто пробег» — замены не было"})
        if data.get("status") in ("due", "overdue"):
            # Просрочка/срок → ПОЛНОЕ напоминание-закреп (msg_service_due). Масло — в закрепе; в сводке
            # его НЕ дублируем (skip_oil), сводку шлём ТОЛЬКО если есть работы/столбцы.
            await _pin_overdue_reminder(context, bridge, chat_id, topic_id, bike,
                                        km_int, data.get("next_km"), data.get("status"),
                                        always_notify=True)
            await _emit_summary(context, chat_id, topic_id, bike, skip_oil=True)
        else:
            # ТО в норме = ТЕРМИНАЛ. Масло → накопитель; ОДНА сводка (масло+история+столбцы).
            acc = _summary_acc(chat_id, topic_id)
            acc["current_km"] = str(km_int)
            acc["oil"] = {"km": km_int, "next": data.get("next_km"), "status": "ok"}
            await _emit_summary(context, chat_id, topic_id, bike)
        # ЧАСТЬ D: [Просто пробег] = финал цикла (закреп-просрочку оставляем, вопросы убираем).
        await _clear_cycle_msgs(context, chat_id, topic_id)
    elif action == "oilbk":
        # [✅ Подтвердить] замены масла задним числом (из handle_oil_backdated_service). ТОЛЬКО доверенный.
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец", show_alert=False)
            b_th = f" ({bike})" if bike else ""
            b_ru = f" по {bike}" if bike else ""
            await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                              text=(f"🐀 Splinter\n"
                                    f"🇹🇭 🔧 บันทึก ТО ย้อนหลัง{b_th} ยืนยันโดย {PYM_HANDLE} หรือเจ้าของเท่านั้นครับ\n"
                                    f"{_SEP}\n"
                                    f"🇷🇺 🔧 Запись ТО задним числом{b_ru} подтверждает {PYM_HANDLE} или владелец"))
            return   # токен и кнопка живут — Пым нажмёт позже
        await _btn_answer(q, "กำลังบันทึก ТО ย้อนหลัง… · Записываю ТО задним числом…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        _cb = ("@" + q.from_user.username) if (q.from_user and q.from_user.username) else "trusted"
        await _write_oil_backdated(context, bridge, chat_id, topic_id, bike, km, confirmed_by=_cb)
    elif action == "codo":
        # ВЕРХНЯЯ ГРАНИЦА: «да, число верное» на переспрос о разрыве вверх (14.08.2026).
        # Trust НЕ ослаблен — это тот же ШАГ 5 (запись в Лист1), что и ветка `done`: подтверждает
        # Пым или владелец. Механик своё же число утвердить не может.
        if not _is_trusted_user(q.from_user):
            await _btn_answer(q, f"ยืนยันโดย {PYM_HANDLE}/เจ้าของ · Подтверждает {PYM_HANDLE} или владелец",
                              show_alert=False)
            return   # токен и кнопка живут — Пым нажмёт позже
        await _btn_answer(q, "กำลังบันทึก… · Записываю ТО…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        done = data.get("done", []) or []
        odo = data.get("odo", "")
        cb = ("@" + q.from_user.username) if (q.from_user and q.from_user.username) else "trusted"
        log.info(f"  → верхняя граница подтверждена кнопкой {cb}: {bike or '?'} odo={odo} "
                 f"(было текущим {data.get('cur') or '?'}, разрыв {data.get('gap') or '?'})")
        # ceiling_ok=True — единственное место, где граница снимается. Прочие сторожа (trust,
        # km_decreasing на мосту, confirmed=true в коде Bridge) не ослаблены ни одним словом.
        written, failed = await _sp_write_done(context, bridge, chat_id, topic_id, bike, done, odo,
                                               confirmed_by=cb, ceiling_ok=True)
        rec = service_receipt.receipt(written, failed, odo, _SP_KIND_LABEL,
                                     ledger=_svc_ledger_take(chat_id, topic_id))
        await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                          text=(f"🐀 Splinter · 📌 {bike}\n"
                                f"🇹🇭 {rec['th']}\n"
                                f"{_SEP}\n"
                                f"🇷🇺 {rec['ru']}"),
                          reply_markup=_svc_undo_kb(_SVC_UNDO_LAST.get((chat_id, topic_id))))
        log.info(f"  → ТО фаза2 запись по «да» верхней границы {cb}: written={written} "
                 f"failed={failed} odo={odo} исход={rec['state']}")

    elif action == "lowr":
        # Кнопка причины понижения. Она НИЧЕГО не записывает — она только называет причину;
        # запись открывает написанное следом пояснение (правило владельца 23.08).
        key = (chat_id, topic_id)
        low = _ODO_LOWER_PENDING.get(key)
        reason = str(data.get("reason") or "")
        if not low:
            await _btn_answer(q, "คำถามหมดอายุแล้ว · Вопрос уже закрыт", show_alert=True)
            return
        if not odo_lower.reason_ok(reason):
            await _btn_answer(q, "ไม่รู้จักเหตุผลนี้ · Причина не опознана", show_alert=True)
            return
        low["reason"] = reason
        _svc_drop(token)
        lbl = odo_lower.REASONS[reason]
        await _btn_answer(q, f"{lbl['th']} · {lbl['ru']}")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        log.info(f"  → ПОНИЖЕНИЕ: причина «{reason}» выбрана, жду пояснение словами")
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=(f"🐀 Splinter\n"
                          f"🇹🇭 ✍️ เหตุผล: {lbl['th']} — ช่วยพิมพ์อธิบายเป็นคำพูดของคุณด้วยครับ "
                          f"ว่าเกิดอะไรขึ้น (แค่ «ใช่» ไม่นับ)\n"
                          f"🇷🇺 ✍️ Причина: {lbl['ru']} — теперь напиши пояснение своими словами, "
                          f"что случилось. Одного «да» не хватит: пояснение сохранится "
                          f"вместе с записью, его будут читать потом."))

    elif action == "sodo":
        # Мягкий гейт ODO ≤500 км: кнопка «Да, намеренно» от механика.
        new_km = data.get("new_km")
        prev_km = data.get("prev_km")
        oil_hint = bool(data.get("oil_hint"))
        key = (chat_id, topic_id)
        soft = _SOFT_ODO_PENDING.get(key)
        sender = _sender_from_user(q.from_user)
        if soft and soft.get("escalate"):
            # Стало эскалацией — кнопка механика не работает
            await _btn_answer(q, f"ต้องยืนยันโดย {PYM_HANDLE}/เจ้าของ · Требует {PYM_HANDLE}/владельца",
                              show_alert=True)
            return
        await _btn_answer(q, "กำลังยืนยัน… · Подтверждаю…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _svc_drop(token)
        _SOFT_ODO_PENDING.pop(key, None)
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(chat_id, topic_id)
        _odo_drop_record(bike)
        _odo_audit_write(bridge, chat_id, topic_id, bike, new_km, prev_km,
                         sender=sender, outcome="подтверждено (кнопка механика)")
        log.info(f"  → sodo-кнопка: {sender} bike={bike} {prev_km}→{new_km}")
        # ЕДИНАЯ ТОЧКА подтверждения (та же, что в тексте и в кнопке «Да»).
        _odo_confirmed(bridge, chat_id, topic_id, bike,
                       str(new_km) if new_km is not None else "",
                       questioned_km=new_km, sender=sender, source="кнопка «Да, намеренно»")
        try:
            await _after_mileage(context, bridge, chat_id, topic_id, bike,
                                 str(new_km) if new_km is not None else "", oil_hint)
        except Exception:
            log.exception("  → svc:sodo: ошибка _after_mileage")
    else:
        await _btn_answer(q)


# ============================================================
#  ТАБЛО ВЫДАЧИ (Delivery) — слой 1 площадки O3
#  ТОЛЬКО факт выдачи: доска броней дня → «✅ Выдан» → переспрос байка (он/другой) →
#  state_set('в аренде'). Денежный РАЗЪЁМ появляется ПОСЛЕ выдачи и НЕ активен (следующий слой).
#  Касса/CRM-A/closing/апрув НЕ трогаем. Единственная персист-запись = state_set (зелёная, не REDZONE).
# ============================================================
DELIVERY_CHAT_ID = -1002445921469
_HB_TOKENS = {}   # token(int) -> {chat,msg_id,bike,client,date_due,booking_id,handed,candidates,test}
_HB_SEQ = [0]

# --- ТЕСТ-РЕЖИМ табло выдачи: обкатка в HQ без тайцев, на ВЫДУМАННЫХ бронях (реальный CRM не читаем). ---
# Вернуть в боевой Delivery: HB_TEST_MODE = False + restart. Delivery командой /board в тест-режиме НЕ трогается.
HB_TEST_MODE = True
HB_TEST_CHAT_ID = -1003853365891          # HQ / TurboControl (тестовая лента)
_HB_TEST_PREFIX = "🧪ТЕСТ "               # префикс байка в состояние_байка для тест-выдач (легко найти и вычистить)
_HB_TEST_BOOKINGS = [
    {"bike": "NMAX 4957", "name": "Ivan",  "date_end": "2026-07-05 13:00", "booking_id": "TEST-1"},
    {"bike": "XMAX 5773", "name": "Petr",  "date_end": "2026-07-03 11:00", "booking_id": "TEST-2"},
    {"bike": "PCX 3081",  "name": "Maria", "date_end": "2026-07-08 10:00", "booking_id": "TEST-3"},
]
_HB_TEST_HOME = ["CB 300CC R 9011", "FORZA 350 5050", "NINJA 400 8080"]   # мок-кандидаты «дома» для «другой»


def _hb_put(data):
    _HB_SEQ[0] += 1
    tok = _HB_SEQ[0]
    _HB_TOKENS[tok] = data
    if len(_HB_TOKENS) > 200:                       # держим последние 200 (как _SVC_TOKENS)
        for k in sorted(_HB_TOKENS)[:-200]:
            _HB_TOKENS.pop(k, None)
    return tok


def _hb_phuket(fmt):
    """Время/дата Пхукета (UTC+7) — для пометок и фильтра «сегодня»."""
    from datetime import datetime, timedelta
    return (datetime.utcnow() + timedelta(hours=7)).strftime(fmt)


def _hb_sender(q):
    u = getattr(q, "from_user", None)
    if u and getattr(u, "username", None):
        return "@" + u.username
    return (getattr(u, "first_name", None) or "кто-то") if u else "кто-то"


def _hb_bookings_today(bridge):
    """Брони на выдачу СЕГОДНЯ: clients(all) → status='бронь' + date_start=сегодня (Пхукет).
    date_start формат 'yyyy-MM-dd HH:mm' (Bridge formatDate) → сравниваем первые 10 символов."""
    try:
        rows = ((bridge._call("clients", filter="all").get("data") or {}).get("clients")) or []
    except Exception:
        log.exception("  → HB: чтение clients упало")
        return []
    today = _hb_phuket("%Y-%m-%d")
    out = []
    for c in rows:
        if str(c.get("status", "")).strip().lower() != "бронь":
            continue
        if str(c.get("date_start") or "")[:10] != today:
            continue
        out.append(c)
    return out


def _hb_home_bikes(bridge):
    """Имена байков статуса ДОМА (кандидаты на замену при «другой»). В ТЕСТ-режиме — мок-список (CRM не читаем)."""
    if HB_TEST_MODE:
        return list(_HB_TEST_HOME)
    try:
        bikes = ((bridge.fleet().get("data") or {}).get("bikes")) or []
    except Exception:
        log.exception("  → HB: чтение fleet упало")
        return []
    return [str(b.get("name") or "").strip() for b in bikes
            if str(b.get("status", "")).strip().upper() == "ДОМА" and b.get("name")]


def _hb_area(note):
    """Район доставки из note брони (атрибут карточки), если указан. Пусто — если нет.
    Карточка ВЫДАЧИ район показывает опционально; у карточки ЗАБОРА он станет обязательной ЛОКАЦИЕЙ."""
    import re
    m = re.search(r"(?:доставка|район|delivery|area)\s*[:：]\s*([^|;\n]+)", str(note or ""), re.I)
    return m.group(1).strip() if m else ""


async def hb_post_board(context, bridge):
    """РУЧНОЙ репост выдач дня. ОДНА бронь = ОТДЕЛЬНАЯ КАРТОЧКА (отдельный пост) с данными
    ЭТОЙ брони (байк·клиент·дата·[район]) + её 2 кнопки (✅ Выдан / 🔁 Другой). Утром бот постит N карточек.
    ТЕСТ-РЕЖИМ (HB_TEST_MODE): в HQ на ВЫДУМАННЫХ бронях. БОЕВОЙ: в Delivery, брони из clients(сегодня)."""
    target = HB_TEST_CHAT_ID if HB_TEST_MODE else DELIVERY_CHAT_ID
    bookings = _HB_TEST_BOOKINGS if HB_TEST_MODE else _hb_bookings_today(bridge)
    _tth = ["🧪 ทดสอบ"] if HB_TEST_MODE else []
    _tru = ["🧪 ТЕСТ"] if HB_TEST_MODE else []
    if not bookings:   # эталон _bilingual: монолитный 🇹🇭-блок, затем 🇷🇺-блок (без слешей)
        await _send(context, chat_id=target, text=_bilingual(None,
            _tth + ["📋 รายการส่งมอบวันนี้", "ไม่มีรายการส่งมอบวันนี้"],
            _tru + ["📋 Выдачи на сегодня", "Броней на выдачу сегодня нет."]))
        return
    n = len(bookings)
    # БЕЗ общей шапки: карточки идут сразу, каждая самодостаточна (видимый заголовок «Выдачи на сегодня»
    # убран как лишний). «Итог дня» (сводка неподтверждённых выдач) — место под футер, строится в след. слое.
    # ОТДЕЛЬНАЯ КАРТОЧКА на КАЖДУЮ бронь (отдельный пост) — НЕ общий список.
    for c in bookings:
        bike = str(c.get("bike") or "").strip()
        client = str(c.get("name") or "").strip()
        due = str(c.get("date_end") or "").strip()
        area = _hb_area(c.get("note"))
        tok = _hb_put({"chat": target, "msg_id": None, "bike": bike, "client": client,
                       "date_due": due, "booking_id": str(c.get("booking_id") or ""),
                       "handed": False, "candidates": [], "test": HB_TEST_MODE})
        th_d = [f"{bike} · {client}"]; ru_d = [f"{bike} · {client}"]
        if due:
            th_d.append(f"ถึง {due}"); ru_d.append(f"до {due}")
        if area:
            th_d.append(f"📍 {area}"); ru_d.append(f"📍 {area}")
        # КАРТОЧКА ОДНОЙ брони: данные брони + легенда (✅ и 🔁 — только актуальные эмодзи карточки).
        txt = _bilingual(None,
            _tth + ["🛵 ส่งมอบรถ"] + th_d + ["", "✅ ส่งมอบ", "🔁 เปลี่ยนรถ"],
            _tru + ["🛵 Выдача"]    + ru_d + ["", "✅ Выдан", "🔁 Другой байк"])
        # ВЕРТИКАЛЬНО, под ЕЁ ОДИН байк: широкая ✅ (эмодзи+данные) + 🔁 С БАЙКОМ (подмена ЭТОГО байка).
        # 🔁 подписана байком (НЕ голая): между карточками безымянная иконка читалась как пустая оторванная кнопка.
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ {bike} · {client}"[:64], callback_data=f"delivery:hand:{tok}")],
            [InlineKeyboardButton(f"🔁 {bike}"[:64], callback_data=f"delivery:other:{tok}")],
        ])
        await _send(context, chat_id=target, text=txt, reply_markup=kb)
    log.info(f"  → HB: {n} карточек выдач запощено (по одной на бронь, test={HB_TEST_MODE}, chat={target})")


async def _hb_mark(q, mark, kb=None):
    """Дописать НЕСТИРАЕМУЮ пометку в тело карточки + выставить клавиатуру (паттерн devbot._strip_and_mark)."""
    base = (q.message.text or "") if q.message else ""
    new_text = f"{base}\n\n{mark}" if base else mark
    try:
        await q.edit_message_text(text=new_text, reply_markup=kb)
    except Exception as e:
        log.warning(f"  → HB _hb_mark edit упал: {e}")
        try:
            await q.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass


async def _hb_do_handover(q, context, bridge, tok, d, bike, edit):
    """Подтверждение выдачи: state_set('в аренде') — каноничное имя из find_bike; client/date_due/booking_id
    из резолва, захваченного на доске (для замены байка бронь та же, меняется только байк). Зелёная (не REDZONE).
    edit=False → подтверждение НОВЫМ сообщением (путь «✅ Выдан» с доски — доску не трогаем);
    edit=True → правим ТЕКУЩЕЕ сообщение (путь «🔁 Другой»→список→pick). После — денежный РАЗЪЁМ (НЕ активен, след.слой)."""
    if d.get("test"):
        _bk = _HB_TEST_PREFIX + bike      # ТЕСТ-выдача: НЕ резолвим реальный байк; явно-тестовый ключ (чистить по префиксу)
    else:
        _bk = (bridge.find_bike(bike) or {}).get("name") or bike
    try:
        bridge.state_set(bike=_bk, status="в аренде", client=d.get("client", ""),
                         date_due=d.get("date_due", ""), booking_id=(d.get("booking_id") or ""),
                         last_event_msg_id=f"{d.get('chat')}:{d.get('msg_id')}")
        log.info(f"  → HB выдача: bike={_bk} status=в аренде booking_id={d.get('booking_id')} "
                 f"client={d.get('client') or '-'} date_due={d.get('date_due') or '-'}")
    except Exception:
        log.exception("  → HB state_set (выдача) упал")
    d["handed"] = True
    d["bike"] = _bk
    _sndr = _hb_sender(q); _cl = d.get('client') or '—'
    _tth = ["🧪 ทดสอบ"] if d.get("test") else []
    _tru = ["🧪 ТЕСТ"] if d.get("test") else []
    # Подтверждение по эталону _bilingual: 🇹🇭-блок целиком, затем 🇷🇺-блок (нестираемый след выдачи).
    body = _bilingual(None,            # после выдачи появился разъём 💵 → легенда 💵
        _tth + ["✅ ส่งมอบให้ลูกค้าแล้ว", f"{_bk} · {_cl}", f"{_sndr} · {_hb_phuket('%H:%M')} (ภูเก็ต)", "", "💵 รับเงิน"],
        _tru + ["✅ выдал клиенту", f"{_bk} · {_cl}", f"{_sndr} · {_hb_phuket('%H:%M')} (Пхукет)", "", "💵 Оплата получена"])
    # ГЕЙТ выдача→деньги: денежный РАЗЪЁМ ТОЛЬКО ЗДЕСЬ (после факта выдачи), НЕ активен (следующий слой). Кнопка=💵 (смысл в легенде).
    # РАЗЪЁМ под клиентскую дорожку (СЛЕДУЮЩИЙ слой): «🚗 Выезжаем» + гейт «жду» — здесь НЕ рендерим.
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💵", callback_data=f"delivery:pay:{tok}")]])
    if edit:
        try:
            await q.edit_message_text(text=_with_separator(body), reply_markup=kb)
        except Exception as e:
            log.warning(f"  → HB confirm edit упал: {e}")
            try:
                await q.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                pass
    else:
        # НОВОЕ сообщение (доску не трогаем). РЕТРАЙ на сетевой таймаут: state_set уже прошёл и идемпотентен,
        # переотправка подтверждения безопасна. Без ретрая ConnectTimeout «съедал» подтверждение → «ничего не происходит».
        await _send_retry(context, chat_id=d["chat"], text=body, reply_markup=kb)


async def handle_delivery_button(update, context, bridge) -> None:
    """Кнопки табло выдачи (CallbackQueryHandler '^delivery:' в bot.py). Слой 1: только факт выдачи.
    hand (с доски) → переспрос байка; ok (он)/other (другой)/pick (выбор замены) → выдача;
    pay (денежный разъём) — НЕ активен (следующий слой)."""
    q = update.callback_query
    if not q:
        return
    parts = (q.data or "").split(":")
    if len(parts) < 3 or parts[0] != "delivery":
        await _btn_answer(q)
        return
    action = parts[1]
    try:
        tok = int(parts[2])
    except Exception:
        await _btn_answer(q)
        return
    d = _HB_TOKENS.get(tok)
    if not d:
        await _btn_answer(q)
        try:
            await q.edit_message_text("🐀 Splinter\n⚠️ Карточка устарела (перезапуск бота). Перепостите доску выдач 🙏")
        except Exception:
            pass
        return

    if action == "pay":
        await _btn_answer(q, "💵 ได้รับเงินแล้ว · Оплата — следующий слой (пока не активна)")   # РАЗЪЁМ-тост: ничего не пишем
        return

    if action == "back":
        # выход из выбора замены ДО записи — ЧИСТАЯ отмена (ничего не записано). Доска остаётся выше.
        await _btn_answer(q, "↩️ Отменено")
        txt = _with_separator(_bilingual(None,
            ["↩️ ยกเลิกการเปลี่ยนรถ", "กลับไปที่รายการส่งมอบด้านบน"],
            ["↩️ Замена отменена", "Вернитесь к списку выдач выше"]))
        try:
            await q.edit_message_text(text=txt, reply_markup=None)   # кнопки убраны, ничего не записано
        except Exception:
            pass
        return

    if action == "hand":
        # доска: выдать ПЛАНОВЫЙ байк СРАЗУ (без переспроса — байк/клиент видны на кнопке).
        # Доску НЕ редактируем (там другие брони) → подтверждение НОВЫМ сообщением (edit=False).
        await _btn_answer(q, "✅")
        await _hb_do_handover(q, context, bridge, tok, d, d["bike"], edit=False)
        return

    if action == "other":
        # доска: подмена байка → список байков ДОМА кнопками, НОВЫМ сообщением (доску не трогаем)
        d["candidates"] = _hb_home_bikes(bridge)[:12]   # cap 12 (пагинация — следующий слой)
        if not d["candidates"]:
            await _btn_answer(q, "Нет байков «дома» для замены")
            return
        await _btn_answer(q)
        rows = [[InlineKeyboardButton(f"✅ {nm}"[:50], callback_data=f"delivery:pick:{tok}:{i}")]
                for i, nm in enumerate(d["candidates"])]   # кнопки замены = эмодзи + ДАННЫЕ (как кнопки выдачи)
        rows.append([InlineKeyboardButton("◀️", callback_data=f"delivery:back:{tok}")])   # голая ◀️ (смысл в легенде)
        _tth = ["🧪 ทดสอบ"] if d.get("test") else []
        _tru = ["🧪 ТЕСТ"] if d.get("test") else []
        txt = _bilingual(None,            # легенда актуальная: на экране кнопки ✅ (выбрать) и ◀️ (назад)
            _tth + ["🔁 เลือกรถคันอื่น (อยู่บ้าน)", "", "✅ เลือก", "◀️ ย้อนกลับ"],
            _tru + ["🔁 Выберите другой байк (дома)", "", "✅ Выбрать", "◀️ Назад"])
        await _send(context, chat_id=d["chat"], text=txt, reply_markup=InlineKeyboardMarkup(rows))
        return

    if action == "pick":
        # выбран байк на замену → выдача; правим ЭТО сообщение-список (edit=True)
        try:
            idx = int(parts[3])
            bike = d["candidates"][idx]
        except Exception:
            await _btn_answer(q, "Не понял выбор")
            return
        await _btn_answer(q, "✅")
        await _hb_do_handover(q, context, bridge, tok, d, bike, edit=True)
        return

    await _btn_answer(q)


# ============================================================
#  O3 СТУПЕНЬ 1 — ПРОСРОЧКИ → BOARD → КОНСТРУКТОР НАРЯДА → ДОСТАВКИ
#  Первый кирпич конвейера. Читает парк (fleet+service_list), считает просрочки 4 обязательных ТО,
#  постит board-список в тему «🔧 Наряды», таец/штаб кнопками собирает наряд (вид→откуда→когда) и
#  отправляет его в группу доставок. Лист1/CRM/касса/state_set НЕ трогает (наряд ≠ смена статуса байка).
#  Хранение отправленных нарядов — своя таблица memory.db o3_task (🟢, как info_pin). Скан/хранение 🟢, постинг 🟠.
# ============================================================
O3_TEST_MODE = True                          # обкатка: board+наряд в HQ на РЕАЛЬНОМ парке (доставки/тайцы не дёргаются)
O3_TEST_CHAT_ID = -1003853365891             # HQ / TurboControl (тестовая лента)
NARYADY_TOPIC = None                         # topic_id темы «🔧 Наряды» в группе ОБСЛУЖИВАНИЯ (-1002751134848).
                                             #   Задать ПОСЛЕ создания темы; None → board без темы (в тесте — HQ).
_O3_TOKENS = {}                              # tok(int) -> draft {bike,plate,current_km,overdue_kinds,kinds,from_where,when}
_O3_SEQ = [0]
_O3_BOARD = {"chat": None, "msg": None}      # заголовок board (для o3_task board_chat/board_msg)

_O3_FROM_LABEL = {"office": ("ที่ออฟฟิศ", "в офисе"), "client": ("ที่ลูกค้า", "у клиента"),
                  "area": ("ตามพื้นที่", "по району")}
_O3_WHEN_LABEL = {"now": ("ตอนนี้", "сейчас"), "today": ("วันนี้", "сегодня")}

_O3_CARD_CAP = 30      # предохранитель: карточек ≤ 30 (худшие сверху), остальное строкой в заголовке — не спамим тему
_O3_CARD_PAUSE = 0.5   # сек между карточками — ровный темп против флуд-контроля (урок pin_info_all)
_O3_HEADER_KEY = "__header__"                # plate-ключ заголовка board в memory.o3_card
_O3_KIND_NOTE = {      # правило вида: kind → (TH, RU) ОБЯЗАТЕЛЬНАЯ строка в наряде (расширяемо: новый вид → пара строк)
    "abs": ("⚠️ เปลี่ยนน้ำมัน ABS: ต้องทำความสะอาดกระบอกสูบด้วย",
            "⚠️ При замене ABS: чистка цилиндров ОБЯЗАТЕЛЬНА"),
}
_O3_KIND_MARK = {      # kind → (TH, RU) КОРОТКАЯ пометка в карточке байка рядом со строкой вида
    "abs": ("⚠️ ต้องล้างกระบอกสูบ", "⚠️ чистка цилиндров обязательна"),
}


def _o3_put(data):
    _O3_SEQ[0] += 1
    tok = _O3_SEQ[0]
    _O3_TOKENS[tok] = data
    if len(_O3_TOKENS) > 200:                 # держим последние 200 (как _HB_TOKENS)
        for k in sorted(_O3_TOKENS)[:-200]:
            _O3_TOKENS.pop(k, None)
    return tok


def _o3_kind_ru(kind):
    return _MAND_LABEL.get(kind, (kind, kind))[1]


def _o3_kind_th(kind):
    return _MAND_LABEL.get(kind, (kind, kind))[0]


def _o3_bike_label(bike, plate):
    """«номер имя» — номер ОДИН раз, вперёд; из имени дубль номера убран (фикс паритета 02.07:
    имя латиницей — одна строка на оба языка, RU и TH получают ОДИНАКОВУЮ полную метку байка)."""
    name = " ".join(w for w in str(bike).split() if w != str(plate)) or str(bike)
    return f"{plate} {name}".strip()


def _o3_cell_km(cell):
    """ЗНАЧЕНИЕ клетки → целые км. None = число есть, а километрами не стало (nan/inf/мусор).

    Контракт уже поручился, что это число, поэтому None здесь — не «пусто», а «взять нечего»:
    такая клетка уходит в «не удалось проверить», а НЕ в «не измерено» (мы не знаем, что там было)."""
    try:
        return int(cell.payload)
    except (TypeError, ValueError, OverflowError):
        return None


def _o3_impossible_why(bike_row, kind, last):
    """Значение ЕСТЬ, но пробегом быть не может → фраза-причина. Иначе "".

    СУДИТ, НО НЕ ЧИНИТ. Транспорт (`fleet_cell`) донёс число как есть — здесь оно называется
    невозможным вслух и уходит в отдельный список владельцу. Никакой подмены значения: −5000 так
    и останется −5000 в расчёте, потому что править живой Лист1 — решение владельца, а не скана."""
    why = []
    if last < 0:
        why.append(f"отрицательное ({last})")
    elif last == 0:
        why.append("нулевое (замена на нулевом пробеге)")
    buy = fleet_cell.read(bike_row, "mileage")          # кол.H — пробег ПРИ ПОКУПКЕ
    if buy.ok:
        buy_km = _o3_cell_km(buy)
        if buy_km is not None and last > 0 and buy_km > last:
            why.append(f"пробег при покупке {buy_km} больше пробега замены {last}")
    return " · ".join(why)


def _o3_overdue_scan(bridge):
    """Park-wide скан просрочек 4 обязательных ТО (масло/gear[скутер]/ABS/возд.фильтр). ЧТЕНИЕ+расчёт (🟢).
    fleet(cells=True) (38 байков, *_last_km + РАЗМЕТКА клеток) + service_list (current_km). Текущий
    пробег — ТОТ ЖЕ единый источник, что у карточки (_odo_current): свой одометр «обслуживание»,
    фоллбэк I/J/K/L; кол.H (пробег ПРИ ПОКУПКЕ) не участвует — класс-фикс 4957 закрыт на ОБЕИХ
    полосах, не только в карточке.

    ТРИ СОСТОЯНИЯ КЛЕТКИ ВМЕСТО ОДНОГО НУЛЯ (10.08.2026, контракт `fleet_cell`, мост @79):
        ЗНАЧЕНИЕ    → судим по нему: next = last+interval, next−текущий ≤ 0 → ПРОСРОЧКА;
        ПУСТО       → «НЕ ИЗМЕРЕНО»: мерить было нечего, срок отсчитывать не от чего;
        НЕ-ЧИСЛО    → «НЕ ИЗМЕРЕНО»: содержимое есть («-», слово, дата), пробегом не стало;
        нечитаемо   → «НЕ УДАЛОСЬ ПРОВЕРИТЬ»: разметки не прислали (старый деплой моста) — и это
                      НЕ повод молчать и НЕ повод считать просрочку.
    ПОЧЕМУ ЭТО ГЛАВНАЯ ПРАВКА, А НЕ КОСМЕТИКА. Прежде `last = _i(…) or 0` схлопывал пустую клетку,
    прочерк, настоящий ноль и отрицательное в ОДНО «last ≤ 0» → ветку `nobase` («не делалось»,
    порог `cur ≥ interval`), и байк попадал в ТОТ ЖЕ список просрочек. Перепись
    `docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md`: из 35 просроченных байков 12 —
    фантомы ровно отсюда, встречное число 23. «Не измерено» и «просрочено» — РАЗНЫЕ вопросы к
    владельцу: первый лечится замером, второй — заменой, и складывать их в одно число значит
    требовать работу там, где никто ничего не мерил.
    НАСТОЯЩИЙ НОЛЬ ОСТАЁТСЯ ПРОСРОЧКОЙ (числа те же, что давал `nobase`: next=interval): замена
    БЫЛА, записана на нулевом пробеге — но вслух названа невозможной (`impossible`).

    ВОЗВРАТ — `scan_result.ScanResult`, payload = СЛОВАРЬ (прежде был список просрочек):
        {"overdue": [{bike,plate,current_km,items:[{kind,last,next,over_km,impossible}]}],  худшие сверху
         "unmeasured": [{bike,plate,current_km,items:[{kind,state,why,due_by_mileage}]}],
         "unchecked":  [{bike,plate,current_km,items:[{kind,why}]}],
         "impossible": [{bike,plate,kind,value,why}],
         "counts": {overdue_bikes, overdue_items, unmeasured_bikes, unmeasured_items,
                    unchecked_bikes, unchecked_items, by_kind:{kind:{overdue,unmeasured,unchecked}}}}
    Три числа НЕ сворачиваются одно в другое НИГДЕ — ни в скане, ни у потребителей.
    ПОЧЕМУ НЕ ПРЕЖНИЙ `{"overdue": […]}`: прежняя форма отдавала ПУСТОЙ СПИСОК и при упавшем
    `fleet()`, и при здоровом парке без просрочек — владельцу печаталось «Просрочек ТО нет 👍» на
    парке из 38 байков, у которого никто ничего не смотрел (перепись
    `docs/artifacts/2026-08-08-zero-on-parse-miss-census.md`, §2 канал 16 — самое дорогое место).
    Исход прохода — как и был:
        источник не прочитан (исключение / ответ без списка байков) → unreadable, осмотра не было;
        байков 0                                                    → empty, знаменатель назван;
        байков N, решение по существу принято по 0 из них           → mismatch (ТРЕТИЙ исход:
            текущий пробег не разобрался ни у одного — «просрочек нет» тут значит «не искали»);
        иначе                                                       → ok.
    РАЗОБРАН = байк, у которого ЕСТЬ имя и РАЗОБРАЛСЯ текущий пробег: без пробега вердикт
    «не просрочено» ни на чём не стоит (`nxt - cur <= 0` при неизвестном cur — не ответ)."""
    def _i(x):
        try:
            return int(str(x).replace(" ", "").replace(",", ""))
        except (ValueError, TypeError):
            return None
    try:
        resp = bridge.fleet(cells=True)   # просим РАЗМЕТКУ клеток: без неё три состояния неразличимы
    except Exception as e:
        log.exception("  → O3 scan: fleet упал")
        return scan_result.ScanResult.unreadable("байков", detail=f"fleet() упал: {e}")
    if not isinstance(resp, dict) or resp.get("ok") is False:
        why = (resp.get("error") if isinstance(resp, dict) else type(resp).__name__)
        log.warning(f"  → O3 scan: fleet() ответил отказом: {why}")
        return scan_result.ScanResult.unreadable("байков", detail=f"fleet() ответил отказом: {why}")
    bikes = (resp.get("data") or {}).get("bikes")
    if not isinstance(bikes, list):
        # Ключа нет / не список — это НЕ «парк пуст», это «списка нам не дали». Прежний код тут
        # молча подставлял [] (`or []`) и получал зелёный нуль.
        log.warning("  → O3 scan: в ответе fleet() нет списка байков")
        return scan_result.ScanResult.unreadable("байков", detail="в ответе fleet() нет списка байков")
    try:
        svc = bridge.service_list().get("items", []) or []
    except Exception:
        svc = []
    overdue, unmeasured, unchecked, impossible, parsed = [], [], [], [], 0
    by_kind = {k: {"overdue": 0, "unmeasured": 0, "unchecked": 0} for k in _MAND_KINDS}
    for b in bikes:
        try:
            name = str(b.get("name") or "").strip()
            if not name:
                continue                          # осмотрен, но не разобран: строка без имени
            plate = _plate_from_name(name) or "?"
            cur_i = _i(_odo_current(bridge, name,
                                    recs=[r for r in svc if _same_bike(r.get("bike"), name)],
                                    fleet_row=b))
            cur = cur_i or 0                      # расчёт прежний; счётчик — отдельно от расчёта
            if cur_i is not None:
                parsed += 1                       # решение по этому байку принято ПО СУЩЕСТВУ
            items, unmeas, unchk = [], [], []
            for kind in _MAND_KINDS:
                interval = _service_interval(kind, name, bridge)
                if interval is None:              # gear на мото/XADV → не трекаем ВООБЩЕ
                    continue
                cell = fleet_cell.read(b, f"{kind}_last_km")
                if cell.outcome == scan_result.OUTCOME_UNREADABLE:
                    # Разметки не прислали. НЕ «не измерено» (мы не знаем, что в клетке) и уж точно
                    # НЕ просрочка: третье число говорит владельцу, что вопрос остался открытым.
                    unchk.append({"kind": kind, "why": cell.say()})
                    by_kind[kind]["unchecked"] += 1
                    continue
                if not cell.ok:                   # ПУСТО либо НЕ-ЧИСЛО → НЕ ИЗМЕРЕНО
                    unmeas.append({"kind": kind, "state": cell.outcome, "why": cell.say(),
                                   # мерить пора? — прежний порог `nobase`, теперь ПОМЕТКА внутри
                                   # «не измерено», а не билет в список просрочек
                                   "due_by_mileage": bool(cur >= int(interval))})
                    by_kind[kind]["unmeasured"] += 1
                    continue
                last = _o3_cell_km(cell)
                if last is None:                  # значение есть, километрами не стало
                    unchk.append({"kind": kind, "why": f"значение не стало километрами ({cell.payload!r})"})
                    by_kind[kind]["unchecked"] += 1
                    continue
                why = _o3_impossible_why(b, kind, last)
                if why:                           # называем вслух, НЕ чиним и НЕ выкидываем из счёта
                    impossible.append({"bike": name, "plate": plate, "kind": kind,
                                       "value": last, "why": why})
                nxt = last + int(interval)
                if nxt - cur <= 0:                # ПРОСРОЧКА — и только она
                    items.append({"kind": kind, "last": last, "next": nxt, "over_km": cur - nxt,
                                  "impossible": why})
                    by_kind[kind]["overdue"] += 1
            if items:
                items.sort(key=lambda x: x["over_km"], reverse=True)
                overdue.append({"bike": name, "plate": plate, "current_km": cur, "items": items})
            if unmeas:
                unmeasured.append({"bike": name, "plate": plate, "current_km": cur, "items": unmeas})
            if unchk:
                unchecked.append({"bike": name, "plate": plate, "current_km": cur, "items": unchk})
        except Exception:
            # Байк, который не разобрался целиком, ОСМОТРЕН и НЕ РАЗОБРАН — счётчик это скажет.
            # Прежде такая строка роняла ВЕСЬ скан (сорок байков молчали из-за одного).
            log.exception("  → O3 scan: байк не разобран, идём дальше")
    overdue.sort(key=lambda x: x["items"][0]["over_km"], reverse=True)   # худшие (макс over_km) сверху
    payload = {
        "overdue": overdue, "unmeasured": unmeasured, "unchecked": unchecked,
        "impossible": impossible,
        "counts": {
            "overdue_bikes": len(overdue), "overdue_items": sum(len(o["items"]) for o in overdue),
            "unmeasured_bikes": len(unmeasured),
            "unmeasured_items": sum(len(o["items"]) for o in unmeasured),
            "unchecked_bikes": len(unchecked),
            "unchecked_items": sum(len(o["items"]) for o in unchecked),
            "by_kind": by_kind,
        },
    }
    return scan_result.ScanResult(len(bikes), parsed, subject="байков", payload=payload)


def _o3_counts_line(payload):
    """ТРИ ЧИСЛА ОДНОЙ СТРОКОЙ, и ни одно не свёрнуто в другое (ТЗ 10.08.2026).

    Единицы названы явно: просрочка — про БАЙКА (историческое «35 из 38» считало байков), а
    «не измерено» и «не удалось проверить» — про КЛЕТКИ (у одного байка их до четырёх). Без
    единицы числа снова стали бы сравнимыми на глаз и слиплись бы в одно."""
    c = (payload or {}).get("counts") or {}
    return (f"просрочено {c.get('overdue_bikes', 0)} байков "
            f"({c.get('overdue_items', 0)} клеток) · "
            f"не измерено {c.get('unmeasured_items', 0)} клеток "
            f"у {c.get('unmeasured_bikes', 0)} байков · "
            f"не удалось проверить {c.get('unchecked_items', 0)} клеток "
            f"у {c.get('unchecked_bikes', 0)} байков")


def _o3_card_render(o, active_plates):
    """(text, kb|None) карточки ОДНОГО байка (доводка 02.07, как Delivery): шапка «⚠️ номер имя», просроченные
    виды построчно («просрочено N км» / «❗ не делалось (пробег N ≥ порога, пора)»), короткая пометка вида
    (_O3_KIND_MARK: ABS → чистка цилиндров). Байк в наряде → строка «✅ в наряде» и БЕЗ кнопки; иначе кнопка
    [🔧 Собрать наряд] → тот же конструктор (o3:pick), flow дальше без изменений."""
    plate, in_work = o["plate"], o["plate"] in active_plates
    lbl = _o3_bike_label(o["bike"], plate)   # номер вперёд, один раз — одинаково в TH и RU
    th = [f"⚠️ {lbl}"]
    ru = [f"⚠️ {lbl}"]
    for it in o["items"]:
        lbl_th, lbl_ru = _MAND_LABEL.get(it["kind"], (str(it["kind"]), str(it["kind"])))
        # Ветка «❗ не делалось» (nobase) УБРАНА 10.08.2026 вместе со своим источником: клетка без
        # замера больше не приходит сюда вовсе — она уходит в «не измерено» (см. _o3_overdue_scan).
        # В карточке-наряде остаётся ровно то, что ею и является: просрочка по ЗНАЧЕНИЮ.
        th.append(f"{lbl_th} — เลยกำหนด {it['over_km']} กม.")
        ru.append(f"{lbl_ru} — просрочено {it['over_km']} км")
        mk = _O3_KIND_MARK.get(it["kind"])
        if mk:
            th[-1] += " · " + mk[0]
            ru[-1] += " · " + mk[1]
    kb = None
    if in_work:
        th.append("✅ ในใบสั่งงาน"); ru.append("✅ в наряде")
    else:
        tok = _o3_put({"bike": o["bike"], "plate": o["plate"], "current_km": o["current_km"],
                       "overdue_kinds": [it["kind"] for it in o["items"]],
                       "kinds": [it["kind"] for it in o["items"]],   # по умолчанию выбраны ВСЕ просроченные
                       "from_where": None, "when": None})
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔧 สร้างใบสั่งงาน / Собрать наряд", callback_data=f"o3:pick:{tok}")]])
    return _bilingual(None, th, ru), kb


def _o3_header_render(n_total, extra_plates, payload=None):
    """(text, kb) заголовка board: счётчик просрочек + [🔄 Обновить]; байки сверх капа карточек — строкой.

    ТРИ ЧИСЛА РАЗДЕЛЬНО (10.08.2026): под счётчиком просрочек — строка «не измерено» и «не удалось
    проверить». Карточки-наряды по-прежнему только на ПРОСРОЧКИ (наряд = работа), но молчать о двух
    других числах нельзя: «просрочек нет 👍» на парке, где половина клеток не измерена, — это
    ровно тот зелёный нуль, ради которого заведён контракт."""
    c = ((payload or {}).get("counts") or {})
    un_i, un_b = c.get("unmeasured_items", 0), c.get("unmeasured_bikes", 0)
    nk_i, nk_b = c.get("unchecked_items", 0), c.get("unchecked_bikes", 0)
    th = [f"🔧 ใบสั่งงาน · เลยกำหนดเซอร์วิส · {n_total} คัน"]
    ru = [f"🔧 Наряды · просрочки парка · {n_total} байков"]
    if not n_total:
        th.append("ไม่มีรายการเลยกำหนด 👍"); ru.append("Просрочек нет 👍")
    if un_i:
        th.append(f"🔎 ยังไม่ได้วัด {un_i} ช่อง / {un_b} คัน — ไม่นับว่าเลยกำหนด")
        ru.append(f"🔎 не измерено {un_i} клеток у {un_b} байков — это НЕ просрочка, это замер")
    if nk_i:
        th.append(f"❔ ตรวจไม่ได้ {nk_i} ช่อง / {nk_b} คัน")
        ru.append(f"❔ не удалось проверить {nk_i} клеток у {nk_b} байков")
    if extra_plates:
        th.append(f"…อีก {len(extra_plates)} คัน นอกการ์ด: " + ", ".join(extra_plates))
        ru.append(f"…ещё {len(extra_plates)} вне карточек: " + ", ".join(extra_plates))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 อัปเดต / Обновить", callback_data="o3:rescan")]])
    return _bilingual(None, th, ru), kb


async def _o3_msg_edit(context, chat_id, msg_id, text, kb):
    """editMessageText карточки/заголовка с ретраем на флуд-контроль (RetryAfter). «Message is not
    modified» = текст не поменялся с прошлого rescan — норма, не ошибка. → True/False (обновлено ли)."""
    import asyncio
    from telegram.error import RetryAfter
    for i in range(3):
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                                 text=_with_separator(text), reply_markup=kb)
            return True
        except RetryAfter as e:
            wait = getattr(e, "retry_after", 1) + 1
            log.warning(f"  → O3 card edit: флуд-контроль (RetryAfter), попытка {i + 1}/3, ждём {wait}s")
            await asyncio.sleep(wait)
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
            log.warning(f"  → O3 card edit упал (msg={msg_id}): {e}")
            return False
    return False


async def _o3_board_sync(context, bridge, allow_post_header=True):
    """СИНК board «карточка-на-байк» (доводка 02.07): заголовок-счётчик + каждый просроченный байк —
    СВОЁ сообщение-карточка со СВОЕЙ кнопкой (как Delivery). Повторные вызовы (🔄 rescan / повторный
    /o3board / после отправки наряда) дубли НЕ плодят: msg_id карточек в memory.db o3_card →
    существующие обновляются editMessageText, новые просрочки досылаются, ушедшие из просрочки
    помечаются «✅ решено» (след остаётся, msg_id забывается), байк в наряде — «✅ в наряде» без кнопки.
    «РЕШЕНО» ГОВОРИТСЯ ТОЛЬКО О РЕШЁННОМ (10.08.2026): байк, ушедший из просрочек потому, что его
    клетка оказалась ПУСТОЙ или НЕ-ЧИСЛОМ, помечается «🔎 не измерено» и msg_id за ним СОХРАНЯЕТСЯ —
    вопрос не закрыт, а сменил вид. Прежняя ветка сказала бы «✅ решено, просрочек нет» ровно тем
    двенадцати фантомам, ради которых правка и делалась: доска показала бы починку там, где никто
    ничего не мерил.
    Троттл _O3_CARD_PAUSE между карточками + _send_retry (RetryAfter) — урок pin_info_all.
    Предохранитель: карточек ≤ _O3_CARD_CAP (худшие сверху), остальное строкой в заголовке.
    Скан/хранение 🟢, постинг 🟠. Лист1/CRM/касса/state_set НЕ трогаем."""
    import asyncio
    target = O3_TEST_CHAT_ID if O3_TEST_MODE else SERVICING_CHAT
    topic = None if O3_TEST_MODE else NARYADY_TOPIC
    scan = _o3_overdue_scan(bridge)
    if not scan.ok:
        # Контракт читателя (08.08.2026): пустой список тут значит «не смотрели», а не «чисто».
        # Синк на нём ЗАПРЕЩЁН — он не просто напечатал бы «Просрочек нет 👍», он пометил бы
        # «✅ решено» КАЖДУЮ висящую карточку (шаг 3 ниже): просрочки исчезли бы с доски, не
        # перестав существовать. Молчим и говорим владельцу, что скан не состоялся.
        log.warning(f"  → O3 board sync ОТМЕНЁН (скан не состоялся): {scan.say()}")
        return {"overdue": 0, "cards": 0, "new": 0, "gone": 0,
                "scan_failed": True, "scan_said": scan.say()}
    payload = scan.payload or {}
    overdue = payload.get("overdue") or []
    # Байки, ушедшие из просрочек НЕ потому, что их починили: клетка пуста / не число / не прочитана.
    # Их карточки нельзя гасить словом «решено» — см. докстринг.
    pending = {o["plate"] for o in (payload.get("unmeasured") or [])}
    pending |= {o["plate"] for o in (payload.get("unchecked") or [])}
    active = set()
    try:
        active = {str(t.get("plate")) for t in (_MEMORY.o3_tasks_active() if _MEMORY else [])}
    except Exception:
        log.exception("  → O3 board: активные наряды не прочитаны")
    cards = {}
    try:
        cards = dict(_MEMORY.o3_cards(target)) if _MEMORY else {}
    except Exception:
        log.exception("  → O3 board: карточки из memory.db не прочитаны")
    header_mid = cards.pop(_O3_HEADER_KEY, None)

    # показываем топ-CAP худших + ВСЕ байки, у кого карточка уже висит (их продолжаем обновлять)
    show = [o for i, o in enumerate(overdue) if i < _O3_CARD_CAP or o["plate"] in cards]
    extra = [o["plate"] for i, o in enumerate(overdue) if i >= _O3_CARD_CAP and o["plate"] not in cards]

    # 1) заголовок: edit существующего / новый (только при allow_post_header)
    htext, hkb = _o3_header_render(len(overdue), extra, payload)
    if header_mid:
        await _o3_msg_edit(context, target, header_mid, htext, hkb)
    elif allow_post_header:
        msg = await _send_retry(context, chat_id=target, message_thread_id=topic, text=htext, reply_markup=hkb)
        if msg is not None:
            header_mid = msg.message_id
            if _MEMORY:
                try:
                    _MEMORY.o3_card_set(target, _O3_HEADER_KEY, header_mid)
                except Exception:
                    log.exception("  → O3 board: заголовок не персистнулся")
    _O3_BOARD["chat"], _O3_BOARD["msg"] = target, header_mid   # для o3_task(board_chat/board_msg)

    # 2) карточки: существующая → editMessageText, новая → send (ровный темп против флуда)
    shown, new_cnt = set(), 0
    for o in show:
        shown.add(o["plate"])
        text, kb = _o3_card_render(o, active)
        mid = cards.get(o["plate"])
        if mid:
            await _o3_msg_edit(context, target, mid, text, kb)
        else:
            msg = await _send_retry(context, chat_id=target, message_thread_id=topic,
                                    text=text, reply_markup=kb)
            if msg is not None:
                new_cnt += 1
                if _MEMORY:
                    try:
                        _MEMORY.o3_card_set(target, o["plate"], msg.message_id)
                    except Exception:
                        log.exception("  → O3 board: карточка не персистнулась")
        await asyncio.sleep(_O3_CARD_PAUSE)

    # 3) ушедшие из просрочки → «✅ решено» (след остаётся), msg_id забыть (новая просрочка = новая карточка).
    #    НО: ушёл из-за неизмеренной/непрочитанной клетки → «🔎 не измерено», msg_id СОХРАНЯЕТСЯ.
    left = [(p, m) for p, m in cards.items() if p not in shown]
    gone = [(p, m) for p, m in left if p not in pending]
    unmet = [(p, m) for p, m in left if p in pending]
    for plate, mid in gone:
        done = _bilingual(None, [f"✅ {plate} — เรียบร้อยแล้ว ไม่มีงานเลยกำหนด"],
                          [f"✅ {plate} — решено, просрочек нет"])
        await _o3_msg_edit(context, target, mid, done, None)
        if _MEMORY:
            try:
                _MEMORY.o3_card_del(target, plate)
            except Exception:
                log.exception("  → O3 board: карточка не забылась")
        await asyncio.sleep(_O3_CARD_PAUSE)
    for plate, mid in unmet:
        note = _bilingual(None, [f"🔎 {plate} — ยังไม่ได้วัด: ช่องว่าง/ไม่ใช่ตัวเลข ยังไม่ใช่งานเลยกำหนด"],
                          [f"🔎 {plate} — не измерено: клетка пуста либо не число. "
                           f"Это не «решено» — просрочку по ней судить не от чего"])
        await _o3_msg_edit(context, target, mid, note, None)
        await asyncio.sleep(_O3_CARD_PAUSE)
    c = payload.get("counts") or {}
    log.info(f"  → O3 board sync: просрочек={len(overdue)}, карточек={len(show)}, новых={new_cnt}, "
             f"решено={len(gone)}, не измерено={c.get('unmeasured_items', 0)} клеток, "
             f"не проверено={c.get('unchecked_items', 0)} клеток, «не измерено» карточек={len(unmet)}, "
             f"test={O3_TEST_MODE}, chat={target}, topic={topic}")
    return {"overdue": len(overdue), "cards": len(show), "new": new_cnt, "gone": len(gone),
            "unmeasured": c.get("unmeasured_items", 0), "unmeasured_bikes": c.get("unmeasured_bikes", 0),
            "unchecked": c.get("unchecked_items", 0), "unchecked_bikes": c.get("unchecked_bikes", 0),
            "counts_line": _o3_counts_line(payload)}


async def o3_post_board(context, bridge):
    """/o3board (owner): синк board «карточка-на-байк». ТЕСТ (O3_TEST_MODE) → HQ на реальном парке.
    БОЕВОЙ → тема «Наряды» группы ОБСЛУЖИВАНИЯ. Повторный вызов дубли НЕ плодит (синк по o3_card).
    → stats {overdue,cards,new,gone} — для сводки-ответа владельцу (фикс «тишины» 02.07:
    повторный синк = всё эдиты-на-месте, без сводки выглядел как молчание бота)."""
    return await _o3_board_sync(context, bridge, allow_post_header=True)


async def _o3_refresh_board(context, bridge):
    """Обновить карточки после события (🔄 rescan / отправка наряда): тот же синк, но новый заголовок
    НЕ постим (не спамить, если board ещё не поднимали)."""
    await _o3_board_sync(context, bridge, allow_post_header=False)


def _o3_from_ru(d): return _O3_FROM_LABEL.get(d.get("from_where"), ("", ""))[1]
def _o3_from_th(d): return _O3_FROM_LABEL.get(d.get("from_where"), ("", ""))[0]
def _o3_when_ru(d): return _O3_WHEN_LABEL.get(d.get("when"), ("", ""))[1]
def _o3_when_th(d): return _O3_WHEN_LABEL.get(d.get("when"), ("", ""))[0]


def _o3_naryad_lines(d):
    """Строки наряда без шапки — (th_lines, ru_lines): байк · работы · откуда · когда. Выбран вид с
    обязательной пометкой (_O3_KIND_NOTE: ABS → чистка цилиндров) → строка добавляется АВТОМАТИЧЕСКИ (RU+TH)."""
    kinds = d.get("kinds", [])
    kinds_th = ", ".join(_o3_kind_th(k) for k in kinds)
    kinds_ru = ", ".join(_o3_kind_ru(k) for k in kinds)
    lbl = _o3_bike_label(d["bike"], d.get("plate", ""))   # полное имя, номер один раз (фикс паритета 02.07)
    th = [lbl, f"งาน: {kinds_th}", f"รับรถ: {_o3_from_th(d)}", f"เมื่อไร: {_o3_when_th(d)}"]
    ru = [lbl, f"работы: {kinds_ru}", f"забрать: {_o3_from_ru(d)}", f"когда: {_o3_when_ru(d)}"]
    for k in kinds:
        note = _O3_KIND_NOTE.get(k)
        if note:
            th.append(note[0])
            ru.append(note[1])
    return th, ru


def _o3_step_vids(d, tok):
    """Шаг 1 конструктора — мультивыбор видов (тоггл ✅/▫️) → «Далее»."""
    lbl = _o3_bike_label(d["bike"], d["plate"])   # полное имя в ОБОИХ языках, номер один раз (фикс 02.07)
    th = [f"🔧 ใบสั่งงาน · {lbl}", "เลือกงาน (กดสลับ):"]
    ru = [f"🔧 Наряд · {lbl}", "Выбери виды (тап — вкл/выкл):"]
    rows = []
    for kind in d.get("overdue_kinds", []):
        mark = "✅ " if kind in d.get("kinds", []) else "▫️ "
        rows.append([InlineKeyboardButton(f"{mark}{_o3_kind_th(kind)} / {_o3_kind_ru(kind)}"[:64],
                                          callback_data=f"o3:vid:{tok}:{kind}")])
    rows.append([InlineKeyboardButton("▶️ ต่อไป / Далее", callback_data=f"o3:step:{tok}:from")])
    rows.append([InlineKeyboardButton("↩️ ยกเลิก / Отмена", callback_data=f"o3:back:{tok}")])
    return _bilingual(None, th, ru), InlineKeyboardMarkup(rows)


def _o3_step_from(d, tok):
    """Шаг 2 — откуда забрать байк."""
    lbl = _o3_bike_label(d["bike"], d["plate"])
    th = [f"🔧 {lbl} · {', '.join(_o3_kind_th(k) for k in d.get('kinds', []))}", "รับรถจากไหน?"]
    ru = [f"🔧 {lbl} · {', '.join(_o3_kind_ru(k) for k in d.get('kinds', []))}", "Откуда забрать?"]
    rows = [[InlineKeyboardButton("🏢 ที่ออฟฟิศ / В офисе", callback_data=f"o3:from:{tok}:office")],
            [InlineKeyboardButton("🙋 ที่ลูกค้า / У клиента", callback_data=f"o3:from:{tok}:client")],
            [InlineKeyboardButton("📍 ตามพื้นที่ / По району", callback_data=f"o3:from:{tok}:area")],
            [InlineKeyboardButton("↩️ ยกเลิก / Отмена", callback_data=f"o3:back:{tok}")]]
    return _bilingual(None, th, ru), InlineKeyboardMarkup(rows)


def _o3_step_when(d, tok):
    """Шаг 3 — когда."""
    lbl = _o3_bike_label(d["bike"], d["plate"])
    th = [f"🔧 {lbl} · {_o3_from_th(d)}", "เมื่อไร?"]
    ru = [f"🔧 {lbl} · {_o3_from_ru(d)}", "Когда?"]
    rows = [[InlineKeyboardButton("⏱ ตอนนี้ / Сейчас", callback_data=f"o3:when:{tok}:now")],
            [InlineKeyboardButton("📅 วันนี้ / Сегодня", callback_data=f"o3:when:{tok}:today")],
            [InlineKeyboardButton("↩️ ยกเลิก / Отмена", callback_data=f"o3:back:{tok}")]]
    return _bilingual(None, th, ru), InlineKeyboardMarkup(rows)


def _o3_step_confirm(d, tok):
    """Шаг 4 — предпросмотр наряда + «Отправить»."""
    th, ru = _o3_naryad_lines(d)
    rows = [[InlineKeyboardButton("✅ ส่งให้ทีมส่งรถ / Отправить в доставки", callback_data=f"o3:send:{tok}")],
            [InlineKeyboardButton("↩️ ยกเลิก / Отмена", callback_data=f"o3:back:{tok}")]]
    return _bilingual(None, ["🔧 ตรวจสอบใบสั่งงาน:"] + th, ["🔧 Проверь наряд:"] + ru), InlineKeyboardMarkup(rows)


async def _o3_answer(q, txt=None):
    """q.answer() с защитой (урок обкатки №3, 02.07): колбэк, отлежавшийся в очереди за долгим
    синком board (флуд-контроль на эдитах, обработка апдейтов последовательная), протухает —
    BadRequest «Query is too old». Ack тогда невозможен, но ДЕЙСТВИЕ кнопки обязано выполниться;
    раньше упавший q.answer валил весь хендлер → кнопки выглядели «мёртвыми»."""
    try:
        await q.answer(txt)
    except Exception as e:
        log.warning(f"  → O3 q.answer протух/упал (действие кнопки всё равно выполняю): {e}")


async def _o3_edit(q, text, kb):
    """Заменить сообщение-конструктор следующим шагом (editMessageText + разделитель 🇹🇭/🇷🇺)."""
    try:
        await q.edit_message_text(text=_with_separator(text), reply_markup=kb)
    except Exception as e:
        log.warning(f"  → O3 edit шага упал: {e}")


async def _o3_do_send(q, context, bridge, tok, d):
    """Отправить наряд в доставки (в тесте → HQ). Запись o3_task(sent). Обновить board (байк «в наряде»).
    Конструктор → подтверждение (нестираемый след). Лист1/CRM/касса/state_set НЕ трогаем."""
    target = O3_TEST_CHAT_ID if O3_TEST_MODE else DELIVERY_CHAT_ID
    sndr = _hb_sender(q); now = _hb_phuket("%H:%M")
    th, ru = _o3_naryad_lines(d)
    _tth = ["🧪 ทดสอบ"] if O3_TEST_MODE else []
    _tru = ["🧪 ТЕСТ"] if O3_TEST_MODE else []
    body = _bilingual(None,
        _tth + ["🔧 ใบสั่งงานเซอร์วิส"] + th + [f"โดย {sndr} · {now} (ภูเก็ต)"],
        _tru + ["🔧 Наряд на ТО"] + ru + [f"от {sndr} · {now} (Пхукет)"])
    dmsg = await _send(context, chat_id=target, text=body)
    delivery_msg_id = dmsg.message_id if dmsg else None
    try:
        if _MEMORY:
            _MEMORY.o3_task_create(bike=d["bike"], plate=d.get("plate", ""),
                                   kinds=",".join(d.get("kinds", [])), from_where=d.get("from_where", ""),
                                   when_slot=d.get("when", ""), status="sent", delivery_msg_id=delivery_msg_id,
                                   board_chat=_O3_BOARD.get("chat"), board_msg=_O3_BOARD.get("msg"))
    except Exception:
        log.exception("  → O3: запись o3_task упала")
    log.info(f"  → O3 наряд отправлен: {d.get('plate')} kinds={d.get('kinds')} from={d.get('from_where')} "
             f"when={d.get('when')} test={O3_TEST_MODE} chat={target}")
    conf = _bilingual(None, _tth + ["✅ ส่งใบสั่งงานไปทีมส่งรถแล้ว"] + th,
                      _tru + ["✅ Наряд отправлен в доставки"] + ru)
    try:
        await q.edit_message_text(text=_with_separator(conf), reply_markup=None)
    except Exception:
        pass
    await _o3_refresh_board(context, bridge)   # байк на board помечается «в наряде»


async def handle_o3_button(update, context, bridge):
    """Кнопки O3 (CallbackQueryHandler '^o3:'). Ступень 1: board pick → конструктор (вид→откуда→когда) →
    Отправить наряд в доставки. Доступно всем в теме (таец+штаб). Лист1/CRM/касса/state_set НЕ трогаем."""
    q = update.callback_query
    if not q:
        return
    parts = (q.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "rescan":
        await _o3_answer(q, "🔄")
        try:   # кнопка 🔄 живёт ПОД заголовком → усыновить его msg_id (переживает рестарт бота)
            if _MEMORY and q.message:
                _MEMORY.o3_card_set(q.message.chat.id, _O3_HEADER_KEY, q.message.message_id)
        except Exception:
            log.exception("  → O3 rescan: заголовок не усыновлён")
        await _o3_refresh_board(context, bridge)
        return
    try:
        tok = int(parts[2])
    except Exception:
        await _o3_answer(q)
        return
    d = _O3_TOKENS.get(tok)
    if not d:
        await _o3_answer(q)
        try:
            await q.edit_message_text(_with_separator(_bilingual(None,
                ["⚠️ ใบสั่งงานหมดอายุ (บอทรีสตาร์ท) กดอัปเดต board ใหม่ 🙏"],
                ["⚠️ Наряд устарел (перезапуск бота). Обновите board 🙏"])))
        except Exception:
            pass
        return

    if action == "pick":                       # открыть конструктор НОВЫМ сообщением (board не трогаем)
        await _o3_answer(q)
        text, kb = _o3_step_vids(d, tok)
        await _send(context, chat_id=q.message.chat.id,
                    message_thread_id=getattr(q.message, "message_thread_id", None), text=text, reply_markup=kb)
        return

    if action == "vid":                        # мультивыбор видов (тоггл)
        kind = parts[3] if len(parts) > 3 else ""
        if kind in d.get("kinds", []):
            d["kinds"].remove(kind)
        elif kind in d.get("overdue_kinds", []):
            d["kinds"].append(kind)
        await _o3_answer(q)
        text, kb = _o3_step_vids(d, tok)
        await _o3_edit(q, text, kb)
        return

    if action == "step" and len(parts) > 3 and parts[3] == "from":
        if not d.get("kinds"):
            await _o3_answer(q, "เลือกอย่างน้อย 1 งาน / Выбери хотя бы один вид")
            return
        await _o3_answer(q)
        text, kb = _o3_step_from(d, tok)
        await _o3_edit(q, text, kb)
        return

    if action == "from":
        d["from_where"] = parts[3] if len(parts) > 3 else "office"
        await _o3_answer(q)
        text, kb = _o3_step_when(d, tok)
        await _o3_edit(q, text, kb)
        return

    if action == "when":
        d["when"] = parts[3] if len(parts) > 3 else "now"
        await _o3_answer(q)
        text, kb = _o3_step_confirm(d, tok)
        await _o3_edit(q, text, kb)
        return

    if action == "send":
        if not (d.get("kinds") and d.get("from_where") and d.get("when")):
            await _o3_answer(q, "ใบสั่งงานยังไม่ครบ / Наряд не заполнен")
            return
        await _o3_answer(q, "✅")
        await _o3_do_send(q, context, bridge, tok, d)
        return

    if action == "back":                       # чистая отмена — ничего не отправлено
        await _o3_answer(q, "↩️ ยกเลิกแล้ว / Отменено")
        try:
            await q.edit_message_text(text=_with_separator(_bilingual(None,
                ["↩️ ยกเลิกใบสั่งงาน"], ["↩️ Наряд отменён (ничего не отправлено)"])), reply_markup=None)
        except Exception:
            pass
        return

    await _o3_answer(q)


def _aggregate_album_vis(vis_list):
    """Слить разборы фото АЛЬБОМА в ОДИН вердикт (чтобы ответить один раз, без дублей):
    - пробег → берём фото с наибольшей уверенностью одометра (лучшее фото приборки);
    - топливо → первое непустое;
    - повреждение/грязь → OR по альбому (упоминаем агрегированно, один раз);
    - notes → склейка уникальных."""
    if not vis_list:
        return {}
    if len(vis_list) == 1:
        return vis_list[0]

    def _conf_rank(v):
        c = str(v.get("mileage_confidence", "")).lower()
        return {"high": 2, "medium": 1, "mid": 1}.get(c, 0)

    agg = {}
    mil = [v for v in vis_list if v.get("mileage")]
    if mil:
        best = max(mil, key=_conf_rank)   # лучшее фото приборки альбома
        agg["mileage"] = best.get("mileage")
        agg["mileage_confidence"] = best.get("mileage_confidence")
    for v in vis_list:
        if v.get("fuel"):
            agg["fuel"] = v.get("fuel")
            break
    for v in vis_list:
        if v.get("tire"):
            agg["tire"] = v.get("tire")
            break
    dmgs = [str(v.get("damage")) for v in vis_list if v.get("damage")]
    if dmgs:
        agg["damage"] = "; ".join(dict.fromkeys(dmgs))[:200]
    agg["dirt"] = any(v.get("dirt") for v in vis_list)
    notes = [str(v.get("notes")) for v in vis_list if v.get("notes")]
    if notes:
        agg["notes"] = " | ".join(dict.fromkeys(notes))[:200]
    return agg


# ===================== ЛИСТ ЗАКРЫТИЯ =====================
# Ручные поля команды «закрытие <байк> поле=значение»: рус-ключ → колонка листа.
_CLOSING_FIELDS = {"топливо": "fuel_level", "доплата_дни": "surcharge_days",
                   "доплата_топливо": "surcharge_fuel", "ущерб": "damage", "прочее": "other",
                   "депозит": "deposit_action", "заметка": "note", "статус": "status"}


def _date_start_key(c):
    """Ключ сортировки по date_start: свежее = больше. datetime.min если не распарсить.
    Живые форматы CRM: '2026-07-01 10:00' (ISO+time), '01.07.2026 10:00' (RU+time),
    '2026-07-01' (ISO), '01.07.2026' (RU)."""
    import datetime as _dt
    s = str(c.get("date_start") or "").strip()
    for prefix, fmt in ((16, "%Y-%m-%d %H:%M"), (16, "%d.%m.%Y %H:%M"),
                        (10, "%Y-%m-%d"), (10, "%d.%m.%Y")):
        try:
            return _dt.datetime.strptime(s[:prefix], fmt)
        except (ValueError, AttributeError):
            pass
    return _dt.datetime.min


def _closing_resolve_booking(bridge, bike):
    """Активная бронь/аренда (Бронь/В аренде) по байку → (booking_id, name, date_end).
    При нескольких кандидатах — свежайшая date_start. Нет → (None, '', '')."""
    try:
        cl = bridge._call("clients", filter="all").get("data", {})
        rows = cl.get("clients", []) if isinstance(cl, dict) else (cl or [])
    except Exception:
        return (None, "", "")
    want = plateFromName_(bike)
    cand = [c for c in rows if plateFromName_(str(c.get("bike", ""))) == want
            and str(c.get("status", "")).strip().lower() in ("бронь", "в аренде")]
    if not cand:
        return (None, "", "")
    last = max(cand, key=_date_start_key)
    return (last.get("booking_id") or None, last.get("name") or "", last.get("date_end") or "")


def _handover_resolve_activation(bridge, bike):
    """O3-3a: кандидат на активацию при выдаче. Последняя строка CRM по байку со статусом
    Бронь/В аренде → dict {row, name, date_start, date_end, status} или None (брони нет).
    status=="в аренде" → активировать нечего (уже активна) — решает вызыватель."""
    try:
        cl = bridge._call("clients", filter="all").get("data", {})
        rows = cl.get("clients", []) if isinstance(cl, dict) else (cl or [])
    except Exception:
        return None
    want = plateFromName_(bike)
    cand = [c for c in rows if plateFromName_(str(c.get("bike", ""))) == want
            and str(c.get("status", "")).strip().lower() in ("бронь", "в аренде")]
    if not cand:
        return None
    last = cand[-1]
    return {"row": last.get("row"), "name": last.get("name") or "",
            "date_start": str(last.get("date_start") or ""),
            "date_end": str(last.get("date_end") or ""),
            "status": str(last.get("status", "")).strip().lower()}


async def _handover_activation_card(context, bridge, bike):
    """O3-3a: на handover-контексте предложить активацию брони (Бронь→В аренде) карточкой
    в INTAKE_CHAT (там авторизаторы INTAKE_APPROVERS). Сама активация — ТОЛЬКО после «да»,
    красным шагом 4.2 в _handle_intake. Брони нет → ⚠️ «активируй руками» (handover не падает)."""
    cand = _handover_resolve_activation(bridge, bike)
    now = _time.time()
    if cand is None:
        # анти-спам: повторные handover-фразы по тому же байку не дублируют ⚠️ чаще кулдауна
        if now - _HO_ACT_WARN_TS.get(bike, 0) < _HO_ACT_WARN_COOLDOWN:
            return
        _HO_ACT_WARN_TS[bike] = now
        log.info(f"  → ВЫДАЧА {bike}: брони в CRM не нашёл — ⚠️ во Входящие, активация руками")
        await _send(context, chat_id=INTAKE_CHAT, bilingual=False,
                    text=f"🐀 Splinter\n⚠️ ВЫДАЧА {bike}: брони в CRM не нашёл (байк/имя/дата) — "
                         f"активируй руками (Бронь→В аренде).")
        return
    if cand.get("status") == "в аренде":
        log.info(f"  → ВЫДАЧА {bike}: строка {cand.get('row')} уже «В аренде» — активация не нужна")
        return
    prev = _HANDOVER_ACTIVATIONS.get(INTAKE_CHAT)
    if (prev and prev.get("status") == "awaiting" and prev.get("row") == cand.get("row")
            and now - prev.get("ts", 0) <= _HO_ACT_TTL):
        return   # та же бронь уже ждёт «да» — карточку не дублируем
    _HANDOVER_ACTIVATIONS[INTAKE_CHAT] = {
        "bike": bike, "name": cand["name"], "date_start": cand["date_start"],
        "row": cand.get("row"), "ts": now, "status": "awaiting",
    }
    dates = (cand["date_start"] + " — " + cand["date_end"]).strip(" —")
    log.info(f"  → ВЫДАЧА {bike}: карточка активации во Входящие (строка {cand.get('row')}, "
             f"клиент {cand['name'] or '—'})")
    await _send(context, chat_id=INTAKE_CHAT, bilingual=False,
                text=(f"🐀 Splinter\n🏍 ВЫДАЧА: {bike} → {cand['name'] or '—'}, "
                      f"бронь строка {cand.get('row')} ({dates or 'даты —'}).\n"
                      f"Активирую (Бронь→В аренде)? да / нет"))


def _return_resolve_close(bridge, bike):
    """O3-3b фаза II: кандидат на закрытие при возврате. Строго «В аренде» по байку;
    при нескольких — свежайшая date_start; закрытые/архивные исключены.
    Нет → None (вызыватель пошлёт ⚠️ «активной аренды не нашёл, закрой руками»)."""
    try:
        cl = bridge._call("clients", filter="all").get("data", {})
        rows = cl.get("clients", []) if isinstance(cl, dict) else (cl or [])
    except Exception:
        return None
    want = plateFromName_(bike)
    cand = [c for c in rows if plateFromName_(str(c.get("bike", ""))) == want
            and str(c.get("status", "")).strip().lower() == "в аренде"]
    if not cand:
        return None
    last = max(cand, key=_date_start_key)
    return {"row": last.get("row"), "name": last.get("name") or "",
            "date_start": str(last.get("date_start") or ""),
            "status": str(last.get("status", "")).strip().lower(),
            "deposit_raw": last.get("deposit_raw"),
            "deposit": last.get("deposit")}


def _return_deposit_disp(raw, parsed):
    """O3-3c часть В: депозит для карточки ПРИЁМА из CRM col S. RAW живёт: число (getValues) |
    строка-число | 'passport' | '' (разведка = Contract.js:315-351; депозит = деньги ИЛИ паспорт).
    Bridge-поле deposit = parseNumber(S) ест 'passport' в 0 — для показа НЕ годится; оно
    fallback ТОЛЬКО на старом Bridge без deposit_raw (там passport неотличим от пустого S →
    честное «не указан ⚠️» до redeploy). → строка для карточки или None (S пуст)."""
    if raw is None:                       # старый Bridge: ключа deposit_raw в строке нет
        try:
            p = float(parsed)
            if p > 0:
                return f"{_fmt(p)} ฿"
        except (TypeError, ValueError):
            pass
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:                                  # число/строка-число (вкл. '20000.0' из float-raw)
        return f"{_fmt(float(s.replace(',', '.')))} ฿"
    except ValueError:
        return s                          # 'passport' и прочее нечисловое — показываем сырьём


async def _return_close_card(context, bridge, bike, km="", total_due=None):
    """O3-3b фаза II: на return-контексте предложить закрытие аренды (В аренде→Завершена)
    карточкой в INTAKE_CHAT (авторизаторы INTAKE_APPROVERS). Само закрытие — ТОЛЬКО после «да»,
    красным шагом 4.2 в _handle_intake. Строки «В аренде» нет → ⚠️ «заверши руками» (возврат
    не падает); последняя уже «Завершена» → молчание (повторная return-фраза, идемпотентно).
    km — пробег на сдаче из return-контекста (может быть пуст → карточка просит цифру);
    total_due — итог листа закрытия (в K уйдёт ТОЛЬКО числовой > 0)."""
    cand = _return_resolve_close(bridge, bike)
    now = _time.time()
    if cand is None:
        # анти-спам: повторные return-фразы по тому же байку не дублируют ⚠️ чаще кулдауна
        if now - _RET_CLOSE_WARN_TS.get(bike, 0) < _RET_CLOSE_WARN_COOLDOWN:
            return
        _RET_CLOSE_WARN_TS[bike] = now
        log.info(f"  → ПРИЁМ {bike}: строки «В аренде» в CRM не нашёл — ⚠️ во Входящие, закрытие руками")
        await _send(context, chat_id=INTAKE_CHAT, bilingual=False,
                    text=f"🐀 Splinter\n⚠️ ПРИЁМ {bike}: активной аренды в CRM не нашёл — "
                         f"заверши руками (В аренде→Завершена).")
        return
    prev = _RETURN_CLOSES.get(INTAKE_CHAT)
    if (prev and prev.get("status") == "awaiting" and prev.get("row") == cand.get("row")
            and now - prev.get("ts", 0) <= _RET_CLOSE_TTL):
        return   # та же аренда уже ждёт «да» — карточку не дублируем
    _paid = None   # в K пойдёт только числовой итог > 0 (0/пусто/мусор → K не трогаем)
    try:
        _t = float(total_due)
        if _t > 0:
            _paid = _t
    except (TypeError, ValueError):
        pass
    km = str(km or "").strip()
    _RETURN_CLOSES[INTAKE_CHAT] = {
        "bike": bike, "name": cand["name"], "date_start": cand["date_start"],
        "row": cand.get("row"), "km": km, "paid_total": _paid,
        "ts": now, "status": "awaiting",
    }
    km_line = (f"Пробег на сдаче: {km}." if km
               else "Пробег на сдаче: не увидел — ответь «да <цифра пробега>».")
    due_line = (f" Итог закрытия: {_fmt(_paid)} ฿." if _paid is not None else "")
    _dep = _return_deposit_disp(cand.get("deposit_raw"), cand.get("deposit"))
    dep_line = (f"\n💰 Верни депозит: {_dep}" if _dep else "\n💰 Депозит: не указан ⚠️")
    log.info(f"  → ПРИЁМ {bike}: карточка закрытия во Входящие (строка {cand.get('row')}, "
             f"клиент {cand['name'] or '—'}, km={km or '-'}, итог={_paid if _paid is not None else '-'}, "
             f"депозит={_dep or 'не указан'})")
    await _send(context, chat_id=INTAKE_CHAT, bilingual=False,
                text=(f"🐀 Splinter\n📥 ПРИЁМ: {bike} вернулся от {cand['name'] or '—'}, "
                      f"строка {cand.get('row')}. {km_line}{due_line}{dep_line}\n"
                      f"Завершаю (Завершена"
                      + (f" + пробег {km}" if km else "")
                      + (f" + оплачено {_fmt(_paid)}" if _paid is not None else "")
                      + ")? да / нет"))


def _closing_crm_debt(bridge, bike):
    """Долг (CRM I/J) активной брони байка для чек-листа. None если не нашли."""
    try:
        rows = bridge._call("clients", filter="all").get("data", {}).get("clients", [])
        want = plateFromName_(bike)
        cand = [c for c in rows if plateFromName_(str(c.get("bike", ""))) == want
                and str(c.get("status", "")).strip().lower() in ("бронь", "в аренде")]
        return cand[-1].get("debt") if cand else None
    except Exception:
        return None


def _closing_card(it, debt):
    """Карточка закрытия RU+TH (тайцам — что собрать; нам — итого/чек-лист). Не блокирует."""
    g = lambda k: (str(it.get(k)) if it.get(k) not in (None, "") else "—")
    total = g("total_due")
    debt_s = "—" if debt is None else str(debt)
    th = ("🇹🇭 ปิดสัญญา — รถ " + g("bike") + "\n"
          "  น้ำมัน: " + g("fuel_level") + " · คืนรถ: " + g("date_return") + "\n"
          "  ส่วนเพิ่ม: วัน " + g("surcharge_days") + " · น้ำมัน " + g("surcharge_fuel") +
          " · เสียหาย " + g("damage") + " · อื่นๆ " + g("other") + "\n"
          "  รวมเก็บเพิ่ม: " + total + " ฿ · มัดจำ: " + g("deposit_action"))
    ru = ("🇷🇺 Закрытие — байк " + g("bike") + "\n"
          "  Топливо: " + g("fuel_level") + " · возврат: " + g("date_return") + "\n"
          "  Доплаты: дни " + g("surcharge_days") + " · топливо " + g("surcharge_fuel") +
          " · ущерб " + g("damage") + " · прочее " + g("other") + "\n"
          "  ИТОГО к доплате: " + total + " ฿ · депозит: " + g("deposit_action") + "\n"
          "  Чек-лист: долг CRM=" + debt_s + " · статус=" + g("status"))
    return "🐀 Splinter\n" + th + "\n" + ru


async def _handle_closing_cmd(msg, context, bridge, text):
    """Команда «закрытие <байк> [поле=значение ...]» — дозаполнить ручные поля + показать карточку RU+TH."""
    chat_id = msg.chat_id
    tid = getattr(msg, "message_thread_id", None)
    import re as _re_c
    rest = _re_c.sub(r"^\s*(закрыти[ея]|closing)\b", "", text, flags=_re_c.I).strip()
    pairs = _re_c.findall(r"(\w+)\s*[=:]\s*(\"[^\"]*\"|\S+)", rest)
    fields = {}
    for k, v in pairs:
        col = _CLOSING_FIELDS.get(k.lower())
        if col:
            fields[col] = v.strip('"')
    bikepart = _re_c.sub(r"(\w+)\s*[=:]\s*(\"[^\"]*\"|\S+)", "", rest).strip()
    bike = bikepart or bike_from_topic(chat_id, tid) or ""
    if not bike:
        await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                    text="🐀 Splinter\nУкажи байк: «закрытие <байк> [доплата_дни=300 ущерб=500 топливо=half]».")
        return
    bid, bname, _bend = _closing_resolve_booking(bridge, bike)
    try:
        bridge.closing_upsert(booking_id=(bid or ""), bike=bike, name=bname, **fields)
        cg = bridge.closing_get(booking_id=bid) if bid else bridge.closing_get(bike=bike)
    except Exception as e:
        await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                    text=f"🐀 Splinter\n❌ Закрытие: ошибка {type(e).__name__}: {e}")
        return
    if not cg.get("ok"):
        await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                    text=f"🐀 Splinter\n⚠️ Строки закрытия по «{bike}» нет (байк ещё не возвращён?).")
        return
    await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                text=_closing_card(cg["item"], _closing_crm_debt(bridge, bike)))


# ============================================================
#  ДВУХФАЗНЫЙ СЕРВИСНЫЙ ПОТОК ТО (заявка → факт → «да» доверенного)
#  Механик (не trusted) ТРИГГЕРИТ обе фазы; запись в Лист1 — ТОЛЬКО по «да» Пыма/владельца.
#  Хранилище состояния: Bot Data «то_заявки» (переживает рестарт). trust НЕ ослаблен.
# ============================================================

# kind → (TH, RU) для перечней заявки/факта. oil/gear/abs/airfilter имеют столбец; остальные — события.
_SP_KIND_LABEL = {
    "oil": ("น้ำมันเครื่อง", "моторное масло"),
    "gear": ("น้ำมันเฟืองท้าย", "масло редуктора"),
    "abs": ("น้ำมัน ABS", "масло ABS"),
    "airfilter": ("ไส้กรองอากาศ", "воздушный фильтр"),
    "filter": ("ไส้กรองน้ำมัน", "масляный фильтр"),
    "pads": ("ผ้าเบรก", "тормозные колодки"),
    "chain": ("โซ่", "цепь"),
    "tyre": ("ยาง", "шина"),
    "other": ("งานอื่น ๆ", "прочие работы"),
}
_SP_COL_KINDS = ("oil", "gear", "abs", "airfilter")   # пишутся в Лист1 (столбец); прочее — событийно
_SP_REMIND_AFTER_MIN = 6 * 60   # висяк: заявка без закрытия старше 6ч → напоминание
_SP_REMIND_THROTTLE_MIN = 6 * 60
_SP_REMIND_MAX_AGE_H = 48       # B4: заявка старше этого (ч) → ОДНА эскалация владельцу/Пыму, тайцам больше не долбим
_SP_LAST_SENT = {}              # B5: in-memory анти-дубль напоминаний (key=(chat,topic,bike) → ts последней отправки)
_SP_RECENT_CLOSE_MIN = 15       # E2a: окно «недавно закрыта заявка» — голые «да/число» в нём гасим (не в мозг)
_SP_BARE_CONFIRM = {"да", "ок", "окей", "угу", "ага", "yes", "ok", "okay", "готово", "принято", "+", "👍"}
_SP_ASK_TS = {}                 # E4: in-memory троттл переспросов фазы-2 (key=(chat,topic) → ts последнего ask)
_SP_ASK_THROTTLE_SEC = 90       # E4: не переспрашивать чаще, чем раз в N сек на тему
# E (класс E): дедуп записи в Лист1 — повтор тройки (plate, service_type, km) в окне → без второй строки
_SVC_WRITE_DEDUP = {}           # (plate_or_bike, kind, km_int) -> ts последней успешной записи
_SVC_DEDUP_WIN_SEC = int(os.getenv("SERVICE_DEDUP_WIN_MIN", "60")) * 60

# ── ОТМЕНА ПОСЛЕДНЕЙ ЗАПИСИ ОБСЛУЖИВАНИЯ (14.08.2026) ────────────────────────────────────────
# РУКИ модуля `undo_last` (решение там; здесь только память и отправка). Журнал заполняется ИЗ
# РАСПИСКИ моста — той самой, из которой прежде читался один флаг `ok`, — поэтому механизм не
# платит ни одного лишнего обращения к мосту.
_SVC_UNDO = {}                  # tok(int) -> запись акта (undo_last.act)
_SVC_UNDO_LAST = {}             # (chat, topic) -> tok ПОСЛЕДНЕГО акта темы (замок «только последняя»)
_SVC_UNDO_SEQ = [0]             # свой счётчик токенов: кнопка отмены живёт своей памятью, не _SVC_TOKENS


def _svc_undo_on():
    """Ветка жива? Ручка `SERVICE_UNDO` (.env). `0` → ни журнала, ни кнопки, путь записи прежний."""
    return undo_last.enabled(_os.getenv(undo_last.FLAG_ENV))


def _svc_undo_remember(chat_id, topic_id, bike, plate, by, odo, positions, blind):
    """Запомнить акт записи. Возвращает токен либо None (нечего помнить / ветка выключена).

    Помним ТОЛЬКО акт с хотя бы одной НАЗВАННОЙ позицией: кнопка отмены не должна изображать
    возможность там, где прежнее значение неизвестно и возвращать не на что. Неназванный акт
    ОБНУЛЯЕТ указатель темы — иначе кнопка новой квитанции отменяла бы ПРОШЛУЮ запись."""
    if not _svc_undo_on():
        return None
    if not positions:
        _SVC_UNDO_LAST[(chat_id, topic_id)] = None
        return None
    try:
        _SVC_UNDO_SEQ[0] += 1
        tok = _SVC_UNDO_SEQ[0]
        key = (chat_id, topic_id)
        _SVC_UNDO[tok] = undo_last.act(tok, _time.time(), chat_id, topic_id, bike, plate, by, odo,
                                       positions, blind)
        _SVC_UNDO_LAST[key] = tok
        if len(_SVC_UNDO) > 200:                       # держим последние 200 (как _SVC_TOKENS)
            for k in sorted(_SVC_UNDO)[:-200]:
                _SVC_UNDO.pop(k, None)
        return tok
    except Exception:
        log.exception("  → журнал отмены ТО: не записал акт (fail-safe: кнопки не будет)")
        return None


def _svc_undo_remember_write(chat_id, topic_id, bike, plate, by, odo, kind, answer):
    """Одна запись ОДНОГО регистра (двери масла) → журнал отмены. Токен либо None.

    ОДИН разбор расписки на обе двери масла (`_write_oil`, `_write_oil_backdated`) — разойтись им
    тогда негде (класс двух зеркальных течей). Логика та же, что у двери фазы 2 в `_sp_write_done`:
    объект берётся из ТОЙ ЖЕ расписки, из которой строкой выше прочитан флаг `ok`, поэтому лишних
    обращений к мосту РОВНО ноль. Прежнего значения в расписке нет (нуль по неразбору · мост его
    не назвал) → позиции нет, а значит нет и кнопки: возможность, которой нет, не изображается."""
    if not _svc_undo_on():
        return None
    pos, blind = [], 0
    try:
        _p, _why = undo_last.position(
            kind, fleet_cell.FIELD_COL.get(write_fact.field_for(kind), ""), answer, want_km=odo)
        if _p:
            pos.append(_p)
        else:
            blind = 1
            log.info(f"  → отмена ТО {bike} {kind}: объект не назван — {_why}")
    except Exception:
        blind = 1
        log.exception("  → отмена ТО: разбор расписки упал (позиция не названа)")
    tok = _svc_undo_remember(chat_id, topic_id, bike, plate, by, odo, pos, blind)
    if tok:
        log.info(f"  → отмена ТО: акт {tok} запомнен ({kind}, дверь масла) — кнопка живёт "
                 f"{undo_last.TTL_DEFAULT // 3600} ч")
    return tok


def _svc_undo_kb(tok):
    """Клавиатура квитанции: одна кнопка «запись неверна». None = кнопки нет (и это честно)."""
    if not tok:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(undo_last.BUTTON_LABEL,
                                                      callback_data=f"svc:undo:{tok}")]])


async def _svc_undo_ask(q, context, token):
    """Нажата «Запись неверна» → замки `undo_last` → карточка владельцу либо честный отказ.

    ЖИВУЮ ТАБЛИЦУ ЭТА ВЕТКА НЕ ТРОГАЕТ ВООБЩЕ: ни одного вызова записи здесь нет и быть не
    должно — отмена правит Лист1, а это «да» владельца. Работа ветки — назвать объект (байк ·
    регистр · строка · какое число убираем и на что возвращаем) и не изобразить возможность
    там, где её нет. Trust НЕ требуется: сказать «запись неверна» вправе и механик — от его
    слов в таблице не меняется ничего."""
    entry = _SVC_UNDO.get(token)
    key = (entry.get("chat"), entry.get("topic")) if isinstance(entry, dict) else (None, None)
    v = undo_last.verdict(entry, token, _SVC_UNDO_LAST.get(key), _time.time(),
                          undo_last.TTL_DEFAULT)
    who = getattr(q, "from_user", None)
    asked_by = ("@" + who.username) if (who and getattr(who, "username", None)) \
        else f"id{getattr(who, 'id', '?')}"
    chat_id = key[0] if key[0] is not None else getattr(getattr(q, "message", None), "chat_id", None)
    topic_id = key[1] if key[0] is not None else getattr(getattr(q, "message", None),
                                                         "message_thread_id", None)
    th, ru = undo_last.reply(v, _SP_KIND_LABEL)

    if v["state"] == undo_last.STATE_CARD:
        text = undo_last.card(v, asked_by=asked_by, labels=_SP_KIND_LABEL)
        sent = False
        try:
            import notify
            sent = bool(notify.send_card(text))     # инбокс 1160: карточка ЖДЁТ ответа владельца
        except Exception:
            log.exception("  → отмена ТО: карточка владельцу не отправлена")
        if sent:
            entry["asked"] = True                   # отмена отмены запрещена
            log.info(f"  ↩️ отмена ТО от {asked_by}: {undo_last.say(v)}")
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        else:
            # Молчать нельзя: мы НЕ довезли до владельца то, что требует его воли.
            th = ("⚠️ ส่งให้เจ้าของไม่สำเร็จครับ — รบกวนบอกเจ้าของเองนะครับ")
            ru = ("⚠️ Карточку владельцу отправить НЕ смог — скажи ему сам: "
                  + undo_last._short(v["entry"]))
            log.warning(f"  ↩️ отмена ТО от {asked_by}: карточка НЕ доехала — {undo_last.say(v)}")
    else:
        log.info(f"  ↩️ отмена ТО от {asked_by}: {undo_last.say(v)}")

    await _btn_answer(q)
    if chat_id is None:                    # адреса нет — отвечать некуда, молча не падаем
        log.warning("  ↩️ отмена ТО: адрес темы не восстановлен, ответ не отправлен")
        return
    await _send_retry(context, chat_id=chat_id, message_thread_id=topic_id,
                      text=(f"🐀 Splinter\n🇹🇭 {th}\n{_SEP}\n🇷🇺 {ru}"))

# B2: маркеры «работа завершена» (ДОВОДЯТ заявку к гейту Пыма, САМИ в Лист1 НЕ пишут).
# Длинные/distinctive — подстрокой; короткие/неоднозначные (да/ок/все) — ТОЛЬКО как целое слово (без ложных срабатываний).
_SP_DONE_SUBSTR = ("закончил", "законч", "готов", "сделал", "сделан", "поменял", "заменил", "замен",
                   "เสร็จ", "แล้ว", "เรียบร้อย", "ทั้งหมด", "finished", "完成")
_SP_DONE_WORDS = {"да", "ок", "окей", "все", "всё", "ok", "okay", "done", "ready", "全部"}


def _service_kind(w):
    """Тонкий классификатор работы для перечней заявки/факта. Возвращает ключ _SP_KIND_LABEL,
    либо '' если работа НЕВАЛИДНА как kind (E3: «масляный фильтр» — такого на NMAX/инд.моделях НЕТ)."""
    s = str(w).lower()
    base = _classify_work(w)
    if base in ("oil", "gear", "abs", "airfilter"):
        return base
    # E3(a): фильтр — валиден ТОЛЬКО воздушный (airfilter). Масляного фильтра нет → невалидно ('').
    if "фильтр" in s or "filter" in s or "กรอง" in s:
        if any(a in s for a in ("возд", "air", "อากาศ")):
            return "airfilter"
        return ""   # «масляный фильтр» / неуточнённый фильтр — НЕ записываем (невалидная работа)
    if any(k in s for k in ("колод", "тормоз", "brake", "ผ้าเบรก")):
        return "pads"
    if any(k in s for k in ("цеп", "chain", "โซ่")):
        return "chain"
    # ШИНА — ОТДЕЛЬНЫЙ ВИД (23.08.2026, решение владельца). До этого она сваливалась в «прочие
    # работы» и теряла имя вида; регистра у неё нет и не заводится — её адрес ИСТОРИЯ байка.
    # Граница слова обязательна: см. `_TYRE_RE` (иначе «машина» стала бы шиной).
    if _re_pl.search(_TYRE_RE, s):
        return "tyre"
    return "other"


# Ключевые слова перечня из СВОБОДНОГО текста (когда parse не дал works) — для declared/done.
_SP_TEXT_KINDS = (
    ("oil", ("моторн", "เครื่อง", "motor oil")),
    ("gear", ("редуктор", "gear", "เฟือง", "трансмис")),
    ("airfilter", ("возд", "air", "อากาศ")),
    ("abs", ("abs", "абс")),
    ("pads", ("колод", "тормоз", "ผ้าเบรก")),
    ("chain", ("цеп", "chain", "โซ่")),
)


def _oil_named_explicitly(text, works, vis):
    """МОТОРНОЕ масло названо ЯВНО? (класс-фикс 4957, корень 3 — граница)
    Да, если работа классифицирована как oil (кол.I) ИЛИ в тексте прямое «моторное/เครื่อง/motor oil».
    Слово «масло» само по себе основанием НЕ является: «поменял масло в редукторе» — это кол.J,
    и предлагать по нему запись кол.I нельзя (живая таблица, чужой столбец)."""
    if any(_classify_work(w) == "oil" for w in (works or [])):
        return True
    blob = ((text or "") + " " + str((vis or {}).get("notes", ""))).lower()
    _oil_kws = dict(_SP_TEXT_KINDS).get("oil", ())
    return any(kw in blob for kw in _oil_kws)


def _declared_kinds(text, works, vis, strict_oil=False):
    """Список kind-ов из works (точный) + скан свободного текста/notes. Сохраняет порядок, без дублей.
    strict_oil=False (ЗАЯВКА/intake): oil от явного слова «масло/моторное» («привёз на масло»).
    strict_oil=True (ФАКТ/done): oil ТОЛЬКО при глаголе замены — мягкое упоминание (карточка ТО Oil,
    «масло в норме», «масляный фильтр») oil НЕ даёт."""
    out = []
    def add(k):
        if k and k not in out:   # E3(a): пустой kind ('' от невалидной работы, напр. масляный фильтр) — отбрасываем
            out.append(k)
    for w in (works or []):
        add(_service_kind(w))
    blob = ((text or "") + " " + str((vis or {}).get("notes", ""))).lower()
    for k, kws in _SP_TEXT_KINDS:
        if any(kw in blob for kw in kws):
            add(k)
    # E3(b): oil как kind — ТОЛЬКО при ЯВНОМ масле + глаголе замены. «масляный фильтр» (масля…) и
    # «масло в норме»/карточка ТО Oil — НЕ дают oil (мягкий контекст ≠ замена масла).
    _oil_word = _re_pl.search(r"масл[оаы]|моторн|น้ำมันเครื่อง|\boil\b", blob)
    _oil_repl = any(v in blob for v in ("замен", "помен", "сменил", "залил", "เปลี่ยน"))
    # strict (факт/done): нужен и глагол замены; intake/заявка: достаточно явного слова масла.
    _oil_ok = bool(_oil_word) and (_oil_repl if strict_oil else True)
    if _oil_ok and "oil" not in out:
        add("oil")
    return out


def _sp_join(kinds):
    return ",".join(kinds)


def _sp_split(s):
    return [k for k in str(s or "").split(",") if k]


def _sp_labels_ru(kinds):
    return ", ".join(_SP_KIND_LABEL.get(k, (k, k))[1] for k in kinds) or "—"


def _sp_labels_th(kinds):
    return ", ".join(_SP_KIND_LABEL.get(k, (k, k))[0] for k in kinds) or "—"


def _is_done_marker(text):
    """B2: ответ механика содержит маркер «работа завершена» (закончил/готово/да/เสร็จแล้ว/…).
    Длинные формы — подстрокой; короткие (да/ок/все) — целым словом (без ложных срабатываний).
    НЕГАТИВ («ещё НЕ закончил» / «ยังไม่เสร็จ» / «not done») → НЕ завершение (консервативно: переспросим)."""
    low = str(text or "").lower()
    toks = set(_re_pl.findall(r"\w+", low))
    if ({"не", "нет", "not"} & toks) or ("ยัง" in low) or ("ไม่" in low):
        return False
    if any(s in low for s in _SP_DONE_SUBSTR):
        return True
    return bool(toks & _SP_DONE_WORDS)


def _sp_merge_done(declared, done):
    """B3: слить заявленное и распознанное-сделанное, сохраняя порядок и без дублей (declared первыми)."""
    out = list(declared)
    for k in done:
        if k not in out:
            out.append(k)
    return out


def _sp_age_hours(created_at, now_ts):
    """Возраст заявки в часах по created_at (ISO Z/+00:00). None при ошибке разбора."""
    try:
        import datetime as _dt
        ts = _dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp()
        return (now_ts - ts) / 3600.0
    except Exception:
        return None


# Карточка байка: читаемые статусы заявки (RU/TH) для секции «в работе». Хэндл тайца — через PYM_HANDLE.
_SP_STATUS_RU = {"заявлено": "заявлено", "ждёт_факт": "ждёт результат",
                 "ждёт_подтверждения": f"ждёт подтверждения {PYM_HANDLE}"}
_SP_STATUS_TH = {"заявлено": "รับเรื่องแล้ว", "ждёт_факт": "รอแจ้งผล",
                 "ждёт_подтверждения": f"รอ {PYM_HANDLE} ยืนยัน"}


def _sp_works_from_note(note):
    """Z4: дословный список работ из note (сегмент WORKS:{...}). Пусто, если нет."""
    m = _re_pl.search(r"WORKS:\{(.*?)\}", str(note or ""))
    return [w.strip() for w in m.group(1).split(";") if w.strip()] if m else []


def _sp_note_set_works(base_note, raw_works):
    """Z4: встроить/обновить дословные работы в note сегментом WORKS:{...}, СОХРАНИВ прочий текст note
    (напр. ' | escalated'). Объединяет с уже записанными работами, без дублей."""
    existing = _sp_works_from_note(base_note)
    clean = [str(w).strip().replace("}", "").replace(";", ",") for w in (raw_works or []) if str(w).strip()]
    merged = list(dict.fromkeys(existing + clean))
    rest = _re_pl.sub(r"WORKS:\{.*?\}\s*\|?\s*", "", str(base_note or "")).strip(" |")
    seg = ("WORKS:{" + "; ".join(merged) + "}") if merged else ""
    if seg and rest:
        return seg + " | " + rest
    return seg or rest


def _sp_note_drop_works(base_note, drop_works, key_of=None):
    """Z4-СНЯТИЕ: убрать из `WORKS:{…}` работы, которые ДОКАЗАННО легли, сохранив прочий текст note.

    Близнец `_sp_note_set_works`, которого не было вовсе (разбор 5960, §3.1): нота умела только
    ДОПОЛНЯТЬСЯ, и работа, ушедшая в историю другой дверью, оставалась в «в работе» навсегда.

    СНИМАЕТСЯ ПО КОНТЕНТНОМУ КЛЮЧУ, а не по буквальному совпадению строк: в историю уходят слова
    одной двери («замена передней шины»), в ноте лежат слова другой («передняя резина»), и
    сравнение текстов не сняло бы НИЧЕГО. Ключ — тот же `_work_key`, которым дедупится сама
    запись, поэтому «снято» и «записано» здесь означают ровно одно и то же.

    ПУСТОЙ СЕГМЕНТ ПИШЕТСЯ КАК `WORKS:{}`, А НЕ КАК ПУСТАЯ СТРОКА: мост берёт поле, только если
    оно `!== ''` (`servicePendingUpsert_` → `pick()`), то есть очистить ноту в ноль физически
    нельзя — тот же приём, которым живёт `service_debt.LEDGER_EMPTY`.

    Снимать нечего → возвращаем ноту БАЙТ-В-БАЙТ: мосту в этом случае не пишем вовсе."""
    existing = _sp_works_from_note(base_note)
    if not existing:
        return str(base_note or "")
    kf = key_of or _work_key
    def _k(w):
        try:
            return kf(str(w).strip())
        except Exception:
            return str(w).strip().lower()
    drop = {_k(w) for w in (drop_works or []) if str(w).strip()}
    keep = [w for w in existing if _k(w) not in drop]
    if len(keep) == len(existing):
        return str(base_note or "")
    rest = _re_pl.sub(r"WORKS:\{.*?\}\s*\|?\s*", "", str(base_note or "")).strip(" |")
    seg = "WORKS:{" + "; ".join(keep) + "}"
    return (seg + " | " + rest) if rest else seg


def _rental_expired(status, end_date):
    """Z3: True если Лист1 статус 'В аренде', но дата конца аренды (формат DD.MM.YYYY[...]) уже в прошлом."""
    if not str(status or "").strip().lower().startswith("в аренд"):
        return False
    m = _re_pl.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", str(end_date or ""))
    if not m:
        return False
    try:
        import datetime as _dt
        d = _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return d < _dt.datetime.utcnow().date()
    except Exception:
        return False


def _sp_open(bridge, chat_id, topic_id, bike):
    """Открытая заявка по теме/байку или None (best-effort, не кидает)."""
    try:
        r = bridge.service_pending_get(chat_id, topic_id or "", bike or "")
        return r.get("item") if r.get("ok") else None
    except Exception:
        log.exception("  → service_pending_get упал")
        return None


def msg_sp_intake_ack(bike, kinds):
    """Фаза 1: заявка принята — НИЧЕГО не пишем в ТО, ждём «готово»."""
    b = f" · 📌 {bike}" if bike else ""
    return (f"🐀 Splinter{b}\n"
            f"🇹🇭 ✅ รับเรื่องแล้วครับ: {_sp_labels_th(kinds)} — เริ่มงานได้เลย แล้วแจ้งตอนเสร็จนะครับ\n"
            f"{_SEP}\n"
            f"🇷🇺 ✅ Принял заявку на ТО: {_sp_labels_ru(kinds)}. Отпишись, когда закончишь — тогда зафиксируем.")


def msg_sp_ask_done(bike, declared):
    """Фаза 2 без перечня факта: переспрос механику что сделал/не сделал."""
    b = f" · 📌 {bike}" if bike else ""
    return (f"🐀 Splinter{b}\n"
            f"🇹🇭 จากที่แจ้งไว้ ({_sp_labels_th(declared)}) — ทำอะไรเสร็จบ้าง อะไรยังครับ? และเลขไมล์ตอนนี้เท่าไหร่?\n"
            f"{_SEP}\n"
            f"🇷🇺 Из заявленного ({_sp_labels_ru(declared)}) — что сделал, что нет? И какой сейчас одометр?")


def msg_sp_confirm_pym(bike, done, notdone, odo):
    """Фаза 2: запрос доверенному на подтверждение записи (кнопка)."""
    b = f" · 📌 {bike}" if bike else ""
    nd = f"\n🇷🇺 Не сделано: {_sp_labels_ru(notdone)}" if notdone else ""
    nd_th = f"\n🇹🇭 ยังไม่ได้ทำ: {_sp_labels_th(notdone)}" if notdone else ""
    return (f"🐀 Splinter{b}\n"
            f"🇹🇭 งาน {bike} เสร็จแล้ว ทำ: {_sp_labels_th(done)}{nd_th}\n"
            f"🇹🇭 เลขไมล์ {odo} กม. — ถูกไหม? ยืนยันบันทึก? {PYM_HANDLE}\n"
            f"{_SEP}\n"
            f"🇷🇺 По {bike} работы завершены. Сделано: {_sp_labels_ru(done)}{nd}\n"
            f"🇷🇺 Одометр {odo} км — верно? Подтвердить запись? {PYM_HANDLE} (или пришли правильное число)")


async def _sp_advance_to_confirm(context, bridge, chat_id, topic_id, bike, declared, done, odo):
    """B1: довести заявку до 'ждёт_подтверждения' и показать кнопку Пыму. Общий хвост фазы-2 —
    зовётся И из текстового ответа (handle_service_result), И из подтверждённого фото-одометра
    (handle_mileage_confirm). САМ в Лист1 НЕ пишет: запись только по svc:done от доверенного (гейт сохранён)."""
    notdone = [k for k in declared if k not in done]
    bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                                  done=_sp_join(done), odometer=str(odo), status="ждёт_подтверждения")
    tok = _svc_put({"chat": chat_id, "topic": topic_id, "bike": bike,
                    "done": done, "odo": str(odo), "kind": "sp_done"})
    rows = [[InlineKeyboardButton("✅ ยืนยันบันทึก / Подтвердить запись",
                                  callback_data=f"svc:done:{tok}")]]
    # ТРЕТИЙ ИСХОД (25.08.2026): до него у человека было ровно два — подтвердить всё на ТЕКУЩЕМ
    # числе либо не подтверждать ничего, а работы разных дней цеплялись к одному пробегу.
    if _batch_odo_on():
        tok2 = _svc_put({"chat": chat_id, "topic": topic_id, "bike": bike,
                         "done": done, "odo": str(odo), "kind": "batch_odo"})
        rows.append([InlineKeyboardButton(batch_odo.BUTTON_LABEL,
                                          callback_data=f"svc:bodo:{tok2}")])
    kb = InlineKeyboardMarkup(rows)
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=msg_sp_confirm_pym(bike, done, notdone, odo), reply_markup=kb)
    mark_awaiting(chat_id, topic_id)
    log.info(f"  → ТО фаза2 → подтверждение Пыму: {bike} done={done} odo={odo} (tok={tok})")


async def sp_confirm_from_brain(context, bridge, chat_id, topic_id, bike, kind, km=None,
                                backdated=False):
    """row12 (аудит 08.07): мозг вызвал set_service в servicing-теме — E2b-гейт запись блокирует,
    но работа НЕ должна теряться молча («Принято» без следа → Инфо молчал про редуктор). Оформляем
    ШТАТНУЮ то_заявку: есть одометр → сразу кнопка Пыму (_sp_advance_to_confirm; запись в Лист1
    только по его «да» — гейт цел); одометра нет → заявка 'ждёт_факт' + просьба одометра
    (B1 довезёт подтверждённым фото-одометром). Инфо-карточка видит заявку в «В работе» (sp_open).
    backdated=True (oil_last_km из set_service): запись задним числом → специальная карточка
    (одометр НЕ трогается), кнопка _write_oil_backdated.
    Bot Data (то_заявки) = зелёная зона."""
    # Спецпуть для задним-числом масла из мозга (oil_last_km в set_service)
    if backdated and kind == "oil" and km:
        odo_str = str(km).strip().replace(" ", "").replace(",", "")
        if _re_pl.fullmatch(r"\d{3,6}", odo_str):
            tok = _svc_put({"kind": "oil_backdated", "chat": chat_id, "topic": topic_id,
                            "bike": bike, "km": odo_str})
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                "✅ ยืนยัน / Подтвердить", callback_data=f"svc:oilbk:{tok}")]])
            await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                        text=msg_oil_backdated_confirm(bike, int(odo_str)), reply_markup=kb)
            mark_awaiting(chat_id, topic_id)
            log.info(f"  → E2b backdated oil: {bike} oil_km={odo_str} → кнопка Пыму")
            return

    kind = str(kind or "").strip().lower()
    if kind not in _SP_KIND_LABEL:
        kind = "other"
    sp = _sp_open(bridge, chat_id, topic_id, bike) or {}
    declared = _sp_merge_done(_sp_split(sp.get("declared")), [kind])
    done = _sp_merge_done(_sp_split(sp.get("done")), [kind])
    odo = str(km or "").strip().replace(" ", "").replace(",", "")
    if not _re_pl.fullmatch(r"\d{3,6}", odo):
        odo = ""
    # Заявка уже ждёт Пыма с этой работой (и тем же одометром) → кнопку не дублируем.
    if (str(sp.get("status")) == "ждёт_подтверждения" and kind in _sp_split(sp.get("done"))
            and (not odo or str(sp.get("odometer") or "") == odo)):
        log.info(f"  → E2b-заявка: {bike} {kind} уже ждёт подтверждения — не дублирую")
        return
    if odo:
        # Сторож Б (класс H) — мягкий: мозг не имеет токена владельца; если odo меньше последнего
        # известного — логируем предупреждение (fail-safe: НЕ блокируем, гейт «да» Пыма сохранён).
        _rec = _LAST_RECORDED_KM.get((chat_id, topic_id))
        if _rec:
            try:
                if int(odo) < _rec[0]:
                    log.warning(
                        f"  ⚠️ сторож Б [sp_confirm_from_brain]: odo={odo} < last={_rec[0]}"
                        f" тема={topic_id} bike={bike} — fail-safe пропускаем (гейт Пыма сохранён)"
                    )
            except (ValueError, TypeError):
                pass
        await _sp_advance_to_confirm(context, bridge, chat_id, topic_id, bike, declared, done, odo)
        return
    bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                                  declared=_sp_join(declared), done=_sp_join(done), status="ждёт_факт")
    if _sp_ask_ok(chat_id, topic_id):
        # ЗАМОК ПОВТОРОВ (вид A3). Состояние = перечень сделанного по заявке из мозга.
        await _hint_send(context, kind="A3", bike=bike, state=("e2b_ask_odo", done),
                         chat_id=chat_id, topic_id=topic_id,
                         text=msg_ask_odometer(bike, kinds=done))
    mark_awaiting(chat_id, topic_id)
    log.info(f"  → E2b-заявка без одометра: {bike} {kind} → ждёт_факт")


async def service_phase1_intake(context, bridge, chat_id, topic_id, bike, declared, works_raw=None):
    """Фаза 1: фиксируем НАМЕРЕНИЕ (заявка). В Лист1/обслуживание НИЧЕГО не пишем.
    Z4: дословные работы (works_raw) кладём в note (для правдивой карточки «в работе»)."""
    try:
        # НОТА СТРОИТСЯ ПОВЕРХ СУЩЕСТВУЮЩЕЙ, А НЕ ПОВЕРХ ПУСТОТЫ (23.08.2026). База `""` затирала
        # ноту открытой строки целиком, а с 23.08 в ней живут ПОЗИЦИИ ДОЛГА — и новый визит того
        # же байка стирал бы висящую работу соседа ровно тем движением, которым фиксирует свою.
        # Чтение платится только там, где ноту и правда пишем (за 83 суток таких заявок 18).
        _note = ""
        if works_raw:
            _base = (_sp_open(bridge, chat_id, topic_id, bike) or {}).get("note")
            _note = _sp_note_set_works(_base, works_raw)
        _extra = {"note": _note} if _note else {}
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                      bike=bike, declared=_sp_join(declared), status="заявлено", **_extra)
    except Exception:
        log.exception("  → service_pending_upsert (фаза1) упал")
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=msg_sp_intake_ack(bike, declared))
    mark_awaiting(chat_id, topic_id)
    log.info(f"  → ТО фаза1: заявка {bike} declared={declared}")


def _sp_ask_ok(chat_id, topic_id):
    """E4(a): троттл переспросов фазы-2 — не чаще раза в _SP_ASK_THROTTLE_SEC на тему (не дёргать на каждое сообщение)."""
    key = (chat_id, topic_id)
    now = _time.time()
    if now - _SP_ASK_TS.get(key, 0) < _SP_ASK_THROTTLE_SEC:
        return False
    _SP_ASK_TS[key] = now
    return True


def _is_bare_confirm(text):
    """E2a: сообщение = голое подтверждение/число без иного смысла (да/ок/угу/yes/цифры)."""
    t = str(text or "").strip().lower().rstrip("!. ")
    if not t:
        return False
    if t in _SP_BARE_CONFIRM:
        return True
    return bool(_re_pl.fullmatch(r"\d{3,6}", t))   # голое число (пробег)


async def handle_post_close_ack(msg, context, bridge, text) -> bool:
    """E2a [гейт]: если по теме/байку заявка ТО ЗАКРЫТА за последние _SP_RECENT_CLOSE_MIN минут И входящее —
    голое «да/ок/число», НЕ пускаем сообщение в мозг (иначе claude.ask пишет ТО мимо двухфазного гейта —
    каскад 4255). Шлём ack «уже записано». Возвращает True если перехватили."""
    if not _is_bare_confirm(text):
        return False
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    bike = bike_from_topic(chat_id, topic_id) or ""
    if not bike:
        return False
    try:
        closed = [r for r in (bridge.service_pending_list(status="закрыто").get("items") or [])
                  if _same_bike(r.get("bike"), bike)]
    except Exception:
        log.exception("  → E2a: чтение закрытых заявок упало")
        return False
    now = _time.time()
    fresh = any((_sp_age_hours(r.get("updated_at"), now) or 1e9) * 60 <= _SP_RECENT_CLOSE_MIN for r in closed)
    if not fresh:
        return False
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=(f"🐀 Splinter · 📌 {bike}\n"
                      f"🇹🇭 ✅ บันทึกแล้วครับ — ผลเซอร์วิสยืนยันโดย {PYM_HANDLE} ด้วยปุ่ม ไม่ใช่แชท\n"
                      f"{_SEP}\n"
                      f"🇷🇺 ✅ Уже записано. Результат сервиса подтверждает {PYM_HANDLE} кнопкой, не в чате."))
    log.info(f"  → E2a: голое подтверждение по {bike} после недавнего закрытия — погашено (не в мозг)")
    return True


async def handle_service_result(msg, context, bridge, claude, text) -> bool:
    """Фаза 2: ответ механика по открытой заявке (status заявлено/ждёт_факт).
    Нет перечня факта → переспрос «что сделал?»; есть факт+одометр → запрос Пыму (кнопка).
    Возвращает True если перехватили. Запись в Лист1 здесь НЕ делается (только по «да» доверенного)."""
    chat_id = msg.chat_id
    topic_id = getattr(msg, "message_thread_id", None)
    bike = bike_from_topic(chat_id, topic_id) or ""
    sp = _sp_open(bridge, chat_id, topic_id, bike)
    if not sp:
        return False
    status = str(sp.get("status"))
    # === КОРЕНЬ 2 (класс-фикс 31.07.2026, инцидент NMAX 155 GREEN-B 4957 тема 79, 29.07) ===
    # Пока по теме ВИСИТ незакрытый вопрос о пробеге («📟 Вижу пробег 38982 км. Верно?»), голое
    # число = ОТВЕТ на этот вопрос, а не «результат работ». Роутер bot.py зовёт нас ПЕРВЫМИ
    # (шаг 0, bot.py:824) — раньше handle_mileage_confirm (шаг 2, bot.py:832): поправка механика
    # «36982» уезжала одометром в заявку, а ветка подтверждения не отрабатывала ВООБЩЕ —
    # ни сторожа убывания, ни аудит-следа, ни отката уже записанного, и неподтверждённый OCR
    # 38982 оставался висеть в pending. Уступаем такое сообщение обычному пути (return False)
    # → шаг 2 → handle_mileage_confirm.
    # УЗКО, по ДЕЙСТВИЮ: только голое 4–6-значное число (ровно то, что примет handle_mileage_confirm)
    # и только пока заявка НЕ 'ждёт_подтверждения' — там голое число ДОВЕРЕННОГО есть санкция на
    # запись в Лист1 (ветка «ответ 2» ниже), её не трогаем.
    if (status != "ждёт_подтверждения"
            and pending_mileage_for(chat_id, topic_id)
            and _re_pl.fullmatch(r"\s*\d{4,6}\s*", str(text or ""))):
        log.info(f"  → ТО фаза2 уступает подтверждению пробега: по теме висит вопрос о пробеге, "
                 f"голое число {str(text).strip()!r} → handle_mileage_confirm ({bike or '?'})")
        return False
    # Запасной путь (ответ 2): заявка ждёт подтверждения, ДОВЕРЕННЫЙ прислал голое число вместо кнопки →
    # берём его число одометром и пишем факт (trust соблюдён — это Пым/владелец, не механик).
    if status == "ждёт_подтверждения":
        m = _re_pl.fullmatch(r"\s*(\d{4,6})\s*", str(text or ""))
        if m and _is_trusted_user(getattr(msg, "from_user", None)):
            done = _sp_split(sp.get("done"))
            cb = ("@" + msg.from_user.username) if (msg.from_user and msg.from_user.username) else "trusted"
            # Слова механика у этой двери УЖЕ на руках (`sp` прочитан выше) — передаём их, чтобы
            # ветка истории не спрашивала мост второй раз о том же самом.
            written, failed = await _sp_write_done(context, bridge, chat_id, topic_id, bike, done,
                                                   m.group(1), confirmed_by=cb,
                                                   works=_sp_works_from_note(sp.get("note")))
            # ДВЕРЬ 2 (голое число доверенного) — тот же выход, что у кнопки. Именно эта дверь
            # 14.08 случайно записала ВЕРНОЕ число там, где кнопка записала бы 367474.
            if _sp_ceiling_asked(failed):
                log.info(f"  → ТО фаза2 число-да {cb}: верхняя граница переспросила, запись не "
                         f"начиналась odo={m.group(1)} bike={bike or '?'}")
                return True
            # ТА ЖЕ дверь, что у кнопки: здесь до 14.08 БЕЗУСЛОВНЫ были ОБЕ половины, а отказ
            # дописывался хвостом только по-русски — тайская молчала о нём вовсе.
            rec = service_receipt.receipt(written, failed, m.group(1), _SP_KIND_LABEL,
                                         ledger=_svc_ledger_take(chat_id, topic_id))
            await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                        text=(f"🐀 Splinter · 📌 {bike}\n"
                              f"🇹🇭 {rec['th']}\n"
                              f"{_SEP}\n"
                              f"🇷🇺 {rec['ru']}"),
                        reply_markup=_svc_undo_kb(_SVC_UNDO_LAST.get((chat_id, topic_id))))
            log.info(f"  → ТО фаза2 запись по числу-да {cb}: written={written} failed={failed} "
                     f"odo={m.group(1)} исход={rec['state']}")
            return True
        return False
    if status not in ("заявлено", "ждёт_факт"):
        return False
    declared = _sp_split(sp.get("declared"))
    # Распознаём перечень факта и одометр из ответа.
    parsed = _parse_json(claude.quick(SERVICING_SYSTEM, text, max_tokens=300, model="MAIN",
                                 tag="servicing", expect_json=True)) if text else {}
    works = [str(w).strip() for w in (parsed.get("works") or []) if w and str(w).strip()]
    done = _declared_kinds(text, works, {}, strict_oil=True)   # E3(b): в ФАКТЕ oil только при явной замене
    # E3(c): накопительно — НЕ теряем ранее распознанное (подшипник и т.п.); объединяем со stored done строки.
    done = _sp_merge_done(_sp_split(sp.get("done")), done)
    odo = parsed.get("mileage") or ""
    if not odo:
        m = _re_pl.search(r"\b(\d{4,6})\b", str(text or ""))
        odo = m.group(1) if m else ""
    # Z4: дословные работы из ответа → в note (для правдивой карточки «в работе»). Отдельный upsert по note;
    # последующие upsert'ы статуса/done не передают note → pick('note') сохранит этот сегмент. Зелёная (Bot Data).
    if works:
        try:
            bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                                          note=_sp_note_set_works(sp.get("note"), works))
        except Exception:
            log.exception("  → Z4 запись дословных работ в note упала")
    # B2: естественный маркер завершения (закончил/готово/да/เสร็จแล้ว/…), не только всё/เสร็จหมด.
    completed = _is_done_marker(text)
    # E4(b): видимость фазы-2 (закрываем слепое пятно — раньше переспросы были не видны в логе).
    log.info(f"  → ТО фаза2 разбор: status={status} works={works} done={done} odo={odo or '-'} "
             f"completed={completed} text={str(text)[:50]!r}")
    # B3: завершение БЕЗ называния конкретных ЗАЯВЛЕННЫХ работ → считаем все заявленные сделанными;
    # названные доп.работы (подшипник=other сверх колодок) ДОБАВЛЯЕМ, заявленное не теряем.
    if completed:
        named_declared = [k for k in done if k in declared]
        if not named_declared:
            done = _sp_merge_done(declared, done)
    # Нет ни перечня факта, ни маркера завершения → переспрашиваем механика (E4(a): троттл — не на каждое сообщение).
    if not done and not completed:
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                      bike=bike, status="ждёт_факт")
        if _sp_ask_ok(chat_id, topic_id):
            # ЗАМОК ПОВТОРОВ (вид B). Состояние = сама заявка: перечень заявленного и статус.
            # Механик дозаявил работу — состояние другое, переспрос уходит снова. Троттл 90 с
            # (`_sp_ask_ok`) НЕ тронут и стоит выше.
            await _hint_send(context, kind="B", bike=bike,
                             state=("sp_ask_done", declared, "ждёт_факт"),
                             chat_id=chat_id, topic_id=topic_id,
                             text=msg_sp_ask_done(bike, declared))
            log.info("  → ТО фаза2: переспрос «что сделал»")
        else:
            log.info("  → ТО фаза2: переспрос «что сделал» ПОДАВЛЕН (троттл E4)")
        mark_awaiting(chat_id, topic_id)
        return True
    if completed and not done:
        done = list(declared)
    if not odo:
        # СНАЧАЛА СПРАШИВАЕМ СВОЙ ОДОМЕТР, а уже потом человека (23.08.2026). До этого дверь судила
        # ТОЛЬКО текущее сообщение: за 60 суток из 20 переспросов у 8 число по этому байку УЖЕ было
        # подтверждено, трижды — минутой ранее (замер в шапке `odo_fresh`). Свежее число НЕ пишется
        # никуда само: оно едет в ту же кнопку Пыму, где он видит его глазами и подтверждает.
        _known = _odo_known_fresh(bridge, bike)
        if _known.get("use"):
            odo = _known["km"]
            log.info(f"  → ТО фаза2: переспрос одометра НЕ нужен — {_known['why']} ({bike})")
    if not odo:
        # факт есть, пробега в ТЕКСТЕ нет → просим одометр; фото-одометр доведёт заявку через
        # handle_mileage_confirm (B1) — в статусе ждёт_факт. done сохраняем в строке заявки.
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                      bike=bike, done=_sp_join(done), status="ждёт_факт")
        if _sp_ask_ok(chat_id, topic_id):
            # ЗАМОК ПОВТОРОВ (вид A2). Состояние = что уже сделано по заявке: механик назвал
            # ещё одну работу — состояние другое, переспрос уходит снова.
            await _hint_send(context, kind="A2", bike=bike,
                             state=("sp_ask_odo", (done or declared), "ждёт_факт"),
                             chat_id=chat_id, topic_id=topic_id,
                             text=msg_ask_odometer(bike, kinds=(done or declared)))   # (b) текст по факту работ заявки
            log.info("  → ТО фаза2: переспрос одометра")
        else:
            log.info("  → ТО фаза2: переспрос одометра ПОДАВЛЕН (троттл E4)")
        mark_awaiting(chat_id, topic_id)
        return True
    # B1 (общий хвост): довести до 'ждёт_подтверждения' + кнопка Пыму (запись только по его «да»).
    await _sp_advance_to_confirm(context, bridge, chat_id, topic_id, bike, declared, done, odo)
    return True


def _sp_fact_after_write(bridge, bike, plate, kind, km):
    """РУКИ перечитывания: расписки нет → сходить в Лист1 и принести КЛЕТКУ (решение — `write_fact`).

    Зовётся ТОЛЬКО после неудачи записи (`write_fact.needs_verify`), поэтому здоровый путь не
    платит ни одного лишнего обращения к мосту — замер и цена в докстринге `write_fact`.
    Форма взята у `_claim_task_verified`: после клиентского сбоя write — немедленное read-only
    чтение целевого места. Любая дырка в фактах (мост молчит · строки парка нет · номер
    неоднозначен · разметки клеток нет) → `unknown`, и записанным это НЕ считается."""
    field = write_fact.field_for(kind)
    if field is None:
        return write_fact.unknown(km, f"вид «{kind}» в колонке Лист1 не живёт — перечитывать нечего")
    want = str(plate or _plate_from_name(bike) or "")
    if not want:
        return write_fact.unknown(km, f"номер байка из «{bike}» не выделен — искать строку нечем")
    try:
        fr = bridge.fleet(cells=True)
    except Exception as e:
        return write_fact.unknown(km, f"парк не прочитан (fleet упал: {e})")
    if not isinstance(fr, dict) or not fr.get("ok"):
        why = (fr or {}).get("error") if isinstance(fr, dict) else "ответ не словарь"
        return write_fact.unknown(km, f"парк не прочитан (мост: {why})")
    rows = ((fr.get("data") or {}).get("bikes") or [])
    hits = [b for b in rows if isinstance(b, dict)
            and _plate_from_name(b.get("name", "")) == want]
    if len(hits) != 1:
        return write_fact.unknown(km, f"строк парка по номеру {want}: {len(hits)} из "
                                      f"{len(rows)} — судить не на чем")
    try:
        cell = bridge.cell(hits[0], field)
    except Exception as e:
        return write_fact.unknown(km, f"клетка «{field}» не прочитана ({e})")
    return write_fact.verdict(km, cell)


def _odo_ceiling_limit():
    """Порог верхней границы, км. Ручка `ODO_CEILING_KM` (.env), `0` = ветка мертва.
    Величина и её вывод из замера 14.08.2026 — в шапке `odo_ceiling`."""
    return odo_ceiling.parse_limit(_os.getenv(odo_ceiling.LIMIT_ENV))


async def _sp_ceiling_stop(context, bridge, chat_id, topic_id, bike, done, odo_int):
    """РУКИ верхней границы: спросить прибор о текущем пробеге и, если разрыв вверх больше порога,
    НЕ писать, а переспросить кнопкой. True = запись остановлена (вопрос уже отправлен).

    FAIL-SAFE В СТОРОНУ ЗАПИСИ, симметрично нижней границе: `_ask_mileage_confirm` при неизвестном
    прежнем числе floor не ставит и пропускает запись — здесь так же. Молчание моста не повод
    останавливать работу механика; цена названа в шапке `odo_ceiling`."""
    try:
        limit = _odo_ceiling_limit()
        if not limit:
            return False
        cur = _odo_current(bridge, bike)          # единый источник правды, '' = не прочитан
        v = odo_ceiling.verdict(odo_int, cur, limit)
        if v["state"] != odo_ceiling.STATE_ASK:
            log.info(f"  → верхняя граница {bike or '?'}: {odo_ceiling.say(v)}")
            return False
        log.warning(f"  🔒 верхняя граница {bike or '?'}: {odo_ceiling.say(v)}")
        tok = _svc_put({"kind": "codo", "chat": chat_id, "topic": topic_id, "bike": bike or "",
                        "done": list(done or []), "odo": str(odo_int),
                        "cur": str(v.get("cur") or ""), "gap": str(v.get("gap") or "")})
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ใช่ เลขถูกต้อง / Да, число верное",
                                 callback_data=f"svc:codo:{tok}"),
        ]])
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=(f"🐀 Splinter · 📌 {bike}\n"
                          f"🇹🇭 {odo_ceiling.question_th(bike, v)}\n"
                          f"{_SEP}\n"
                          f"🇷🇺 {odo_ceiling.question_ru(bike, v)}"),
                    reply_markup=kb)
        return True
    except Exception:
        log.exception("  → верхняя граница: исключение — fail-safe, пишем как прежде")
        return False


def _sp_ceiling_asked(failed):
    """Записи не было — верхняя граница переспросила, и вопрос УЖЕ отправлен. Обе двери читают
    сигнал ОДНИМ предикатом: разойтись в чтении им должно быть так же негде, как в самом гейте."""
    try:
        return any(e == odo_ceiling.ERR for _, e in (failed or []))
    except Exception:
        return False


def _work_name_on():
    """Ветка «названная работа в истории» жива? Ручка `WORK_NAME` (.env). `0` → прежний ярлык."""
    return work_name.enabled(_os.getenv(work_name.FLAG_ENV))


def _sp_words_said(bridge, chat_id, topic_id, bike):
    """Дословные работы механика по ОТКРЫТОЙ заявке (сегмент `WORKS:{…}` поля note).

    Зовётся ЛЕНИВО и ТОЛЬКО из ветки «регистра нет»: колоночный путь (кол. I/J/K/L) слов не
    читает и не платит за них НИ ОДНОГО обращения к мосту — это проверяется счётчиком вызовов
    в тесте, а не обещанием. Любая дырка (мост молчит · заявки нет · сегмента нет) → пустой
    список, то есть прежний ярлык: незнание слов записью в историю не наказывается."""
    try:
        return _sp_works_from_note((_sp_open(bridge, chat_id, topic_id, bike) or {}).get("note"))
    except Exception:
        log.exception("  → история ТО: дословные работы не прочитались — пойдёт ярлык вида")
        return []


#: Вердикт сторожа партии: кладёт `_sp_write_done` (там факты), забирает дверь квитанции (там текст).
#: Накопитель по теме — тот же приём, что у `_SVC_SUMMARY`/`_SVC_UNDO_LAST`; живёт до квитанции.
_SVC_LEDGER = {}


def _svc_ledger_take(chat_id, topic_id):
    """Забрать вердикт сторожа РОВНО ОДИН РАЗ — иначе он приклеился бы ко второй квитанции."""
    return _SVC_LEDGER.pop((chat_id, topic_id), None)


def _sp_ledger_note(chat_id, topic_id, done, written, failed, info_written, info_lost,
                    expanded=()):
    """СТОРОЖ ПАРТИИ (класс 22.08.2026): принято N · записано M, и каждая потеря — поимённо.

    Считается ФАКТ, а не намерение: колоночная позиция засчитывается регистром только если она
    в `written` (то есть мост подтвердил либо перечитанный факт доказал), инфо-работа — только
    если её вернул `_write_info_works` (там `ok+saved` или `duplicate`, отказ туда не попадает).
    Всё прочее — потеря с названной причиной. Решение и обе половины текста — `works_ledger`."""
    fail_why = {}
    for item in (failed or []):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            fail_why[str(item[0])] = str(item[1] or "")
    pos = []
    _exp = set(expanded or ())
    for k in (done or []):
        # Вид, разошедшийся на именованные работы, позицией НЕ считается — его позиции суть сами
        # работы, и они уже пришли в `info_written`/`info_lost`. Иначе одна работа считалась бы
        # дважды (как вид и как работа), а пятёрка работ — как одна позиция.
        if k in _exp:
            continue
        pair = _SP_KIND_LABEL.get(k) or (k, k)
        if k in (written or []):
            out = works_ledger.IN_REGISTER if k in _SP_COL_KINDS else works_ledger.AS_EVENT
            pos.append(works_ledger.position(pair[1], out, name_th=pair[0]))
        else:
            pos.append(works_ledger.position(pair[1], works_ledger.LOST, why="write_failed",
                                             detail=fail_why.get(str(k), ""), name_th=pair[0]))
    for w in (info_written or []):
        pos.append(works_ledger.position(w, works_ledger.AS_EVENT, name_th=_work_th(w)))
    for item in (info_lost or []):
        w, why, detail = (list(item) + ["", ""])[:3]
        pos.append(works_ledger.position(w, works_ledger.LOST, why=why, detail=detail,
                                         name_th=_work_th(w)))
    v = works_ledger.tally(pos)
    _SVC_LEDGER[(chat_id, topic_id)] = v
    log.info("  → " + works_ledger.line(v))
    return v


async def _sp_write_done(context, bridge, chat_id, topic_id, bike, done, odo, confirmed_by="",
                         ceiling_ok=False, works=None):
    """ШАГ 5 (КРАСНЫЙ): по «да» доверенного пишем СДЕЛАННЫЕ позиции. Сторож km_decreasing НЕ трогаем
    (он на стороне set_fleet_*). Каждая колоночная позиция: set_fleet_* (кол.I/J/K/L, confirmed=True)
    + service_upsert (синк «обслуживание» — закрывает разрыв _write_oil→обслуживание). Прочее → событие.
    Возвращает (written:list, failed:list).

    ВЕРХНЯЯ ГРАНИЦА ПРОБЕГА СТОИТ ЗДЕСЬ, А НЕ В ДВЕРЯХ (14.08.2026). Дверей записи две — кнопка
    Пыма (`handle_service_button`, ветка `done`) и голое число доверенного (`handle_service_result`,
    ветка `ждёт_подтверждения`), — и до 14.08 они вели себя ПО-РАЗНОМУ: 14.08 09:06 по байку
    NMAX RED WHITE 9548 обе получили `odo=367474` при текущем 36474, но легло верное число только
    потому, что владелец ответил сообщением, а не кнопкой. Гейт стоит в ЕДИНСТВЕННОМ общем месте —
    разойтись дверям тогда физически негде. Порог и его вывод из замера 74 суток — в шапке
    `odo_ceiling`; `ceiling_ok=True` приходит ТОЛЬКО с кнопки «да, число верное» (svc:codo)."""
    plate = _plate_from_name(bike) or _plate_from_name((bridge.find_bike(bike) or {}).get("name", ""))
    try:
        odo_int = int(str(odo).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return [], [("odo", "bad_odometer")]
    if not ceiling_ok:
        stop = await _sp_ceiling_stop(context, bridge, chat_id, topic_id, bike, done, odo_int)
        if stop:
            return [], [("odo", odo_ceiling.ERR)]
    written, failed = [], []
    undo_pos, undo_blind = [], 0     # позиции отмены и сколько их осталось БЕЗ названного объекта
    said = works                     # слова механика; None = ещё не спрашивали (см. _sp_words_said)
    # ПОЗИЦИИ ИСТОРИИ — по РАБОТЕ, а не по виду (23.08.2026). `expanded` перечисляет виды, которые
    # разошлись на именованные работы: сторож обязан считать ИХ, а не вид целиком, иначе пятёрка
    # работ дала бы «принято 1» и потеря четырёх осталась бы невидимой.
    named_rows, named_lost, expanded = [], [], []
    for k in done:
        try:
            if k in _SP_COL_KINDS:
                # Класс E дедуп: повтор той же тройки (plate, kind, km) в окне → пропустить запись в Лист1
                _dedup_key = (plate or bike, k, odo_int)
                try:
                    _prev_ts = _SVC_WRITE_DEDUP.get(_dedup_key)
                    if _prev_ts is not None and _time.time() - _prev_ts < _SVC_DEDUP_WIN_SEC:
                        log.info(
                            f"  → дедуп ТО: {bike} {k} {odo_int} км — повтор в окне"
                            f" {_SVC_DEDUP_WIN_SEC // 60} мин, запись пропущена"
                        )
                        written.append(k)
                        continue
                except Exception:
                    log.exception("  → дедуп ТО: стор сбоил — fail-safe, пишем как обычно")
                iv = _service_interval(k, bike, bridge) or 4000
                if k == "oil":
                    r = bridge.set_fleet_oil(number=plate, oil_km=odo_int, confirmed=True)
                else:
                    r = bridge.set_fleet_service(number=plate, kind=k, km=odo_int, confirmed=True)
                # СИНК РЕШАЕТ ПЕРЕЧИТАННЫЙ ФАКТ, А НЕ ФЛАГ РАСПИСКИ (13.08.2026). Расписка не
                # пришла → величина в Лист1 могла ЛЕЧЬ (плечо одно, пересылок нет), и прежний
                # `if r.get("ok")` гасил синк зеркала на ровном месте. См. `write_fact`.
                fact = None
                if not r.get("ok") and write_fact.needs_verify(r):
                    fact = _sp_fact_after_write(bridge, bike, plate, k, odo_int)
                    log.warning(f"  → ТО {bike} {k} {odo_int}: расписка не пришла "
                                f"({r.get('error')}) — {fact.say()}")
                if r.get("ok") or (fact is not None and fact.landed):
                    bridge.service_upsert(bike=bike, service_type=k, current_km=odo_int,
                                          last_service_km=odo_int, interval_km=iv)
                    try:
                        _SVC_WRITE_DEDUP[_dedup_key] = _time.time()
                    except Exception:
                        pass
                    # ОТМЕНА: объект берётся из ТОЙ ЖЕ расписки, из которой выше прочитан флаг
                    # `ok`. Прежнего значения в ней нет (нуль по неразбору · расписка не пришла и
                    # факт перечитан) → позиция не называется, и кнопка её не изображает.
                    try:
                        _pos, _why = undo_last.position(
                            k, fleet_cell.FIELD_COL.get(write_fact.field_for(k), ""), r,
                            want_km=odo_int)
                        if _pos:
                            undo_pos.append(_pos)
                        else:
                            undo_blind += 1
                            log.info(f"  → отмена ТО {bike} {k}: объект не назван — {_why}")
                    except Exception:
                        undo_blind += 1
                        log.exception("  → отмена ТО: разбор расписки упал (позиция не названа)")
                    written.append(k)
                else:
                    # Исход неудачи называется вслух: «не легло» и «неизвестно» — РАЗНЫЕ вещи.
                    failed.append((k, r.get("error") if fact is None
                                   else f"{r.get('error')}/{fact.state}"))
            else:
                # фильтр/колодки/цепь/прочее — регистра нет → событие с одометром (фаза2 scope).
                # В ИСТОРИЮ ИДЁТ НАЗВАННАЯ РАБОТА, А НЕ ЯРЛЫК (14.08.2026, живой случай 9548:
                # механик сказал «замена аккумулятора», в таблицу ушло «прочие работы»). Ярлык
                # никуда не делся — он по-прежнему адресует расчёт и держит `msg_id`, то есть
                # дедуп; человеку же достаются слова человека. Разбор — `work_name`, слова —
                # ленивым чтением ТОЙ ЖЕ заявки (колоночный путь выше сюда не заходит вовсе).
                _on = _work_name_on()
                if _on and said is None:
                    said = _sp_words_said(bridge, chat_id, topic_id, bike)
                # СТРОКА НА КАЖДУЮ НАЗВАННУЮ РАБОТУ (23.08.2026, решение владельца). Прежде вид
                # давал РОВНО ОДНУ строку: `work_name.history_note` склеивал все слова этого вида
                # через `JOIN` («; ») в один `notes`, а ключ `sp:{chat}:{topic}:{вид}:{км}` был
                # один на всю партию — пять работ вида «прочие» ложились ОДНОЙ строкой, и карточка
                # показывала их одной работой (её `_SVC_HIST_RE` нежадный, берёт всё до « — »).
                # Соседняя дверь того же класса (`_write_info_works`, выгрузка буфера) пишет строку
                # на работу с 29.07 — здесь зовётся ОНА ЖЕ, чтобы двум путям истории было негде
                # разойтись (класс «две зеркальные течи», ENV_PLAYBOOK п.9). Ключ там КОНТЕНТНЫЙ
                # (`info:{plate}:{ключ-работы}:{км}`), поэтому забор идемпотентности из шапки
                # `work_name` цел: та же работа ДРУГИМИ словами даёт тот же `_work_key` → ту же
                # строку, а РАЗНЫЕ работы — разные ключи → разные строки.
                _mine = work_name.words_of(k, said, _service_kind) if _on else []
                if _mine:
                    _iw_fail = []
                    try:
                        import datetime as _dt
                        _dnow = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
                    except Exception:
                        _dnow = ""   # даты нет → строка всё равно ложится (у неё есть recorded_at)
                    _iw_ok = _write_info_works(bridge, "обслуживание", topic_id, bike, _mine,
                                               odo_int, "", msg_date=_dnow, chat_id=chat_id,
                                               failed_out=_iw_fail,
                                               sender=str(confirmed_by or ""))
                    named_rows.extend(_iw_ok)
                    named_lost.extend((w, "write_failed", d) for w, d in _iw_fail)
                    expanded.append(k)
                    log.info(f"  → история ТО {bike} вид={k}: строк {len(_iw_ok)} из "
                             f"{len(_mine)} названных (работы: {_mine})")
                    if _iw_ok:
                        written.append(k)
                    else:
                        failed.append((k, "history_write_failed"))
                else:
                    # Слов этого вида механик не сказал вовсе (вид опознан сканом свободного
                    # текста) — ярлык, БАЙТ-В-БАЙТ прежняя строка и прежний ключ. Ярлык здесь не
                    # подменяет слова: подменять нечего, а «прочие работы» называют себя
                    # КАТЕГОРИЕЙ и никого за название не выдают (см. шапку `work_name`).
                    v = work_name.history_note(k, said, odo_int, _SP_KIND_LABEL, _service_kind,
                                               on=_on)
                    bridge.add_event(group="обслуживание" + (f" / тема {topic_id}" if topic_id else ""),
                                     bike=bike, event_type="repair", mileage=str(odo_int),
                                     notes=v["text"], sender=str(confirmed_by or ""),
                                     msg_id=f"sp:{chat_id}:{topic_id}:{k}:{odo_int}")
                    log.info(f"  → история ТО {bike} вид={k}: «{v['text']}» "
                             f"источник={v['source']} ({v['why']})")
                    written.append(k)
        except Exception:
            log.exception(f"  → ТО фаза2 запись {k} упала")
            failed.append((k, "exception"))
    # ДВЕРЬ ФАЗЫ 2 (кнопка Пыма / число доверенного) — ТОЖЕ подтверждённый пробег, значит тоже
    # выгружает буфер отложенных работ. До 22.08.2026 этой двери у буфера не было вовсе: фаза 2
    # берёт одометр своим разбором, и 01.08 четыре работы остались лежать, пока то же число
    # писалось в регистры. Логика выгрузки одна на все три двери — `_km_door`.
    _info_written, _info_lost = _km_door(bridge, chat_id, topic_id, bike, odo_int,
                                         source=f"фаза 2 ({confirmed_by or 'trusted'})")
    # СТОРОЖ ПАРТИИ: принято N · записано M. Расходятся — квитанция назовёт каждую потерю.
    # Строки истории этой двери подмешиваются к работам буфера ТЕМ ЖЕ составом: у сторожа
    # позиция — РАБОТА, и происхождение работы (буфер или прямая дверь) на счёт не влияет.
    try:
        _sp_ledger_note(chat_id, topic_id, done, written, failed,
                        list(_info_written) + named_rows, list(_info_lost) + named_lost,
                        expanded=expanded)
    except Exception:
        log.exception("  → сторож партии сбоил (квитанция уйдёт прежней)")
    _tok = _svc_undo_remember(chat_id, topic_id, bike, plate, confirmed_by, odo_int,
                              undo_pos, undo_blind)
    if _tok:
        log.info(f"  → отмена ТО: акт {_tok} запомнен ({len(undo_pos)} позиц., без объекта "
                 f"{undo_blind}) — кнопка живёт {undo_last.TTL_DEFAULT // 3600} ч")
    # ЗАКРЫТИЕ ОДНО И СУДИТСЯ ВЕРДИКТОМ (23.08.2026, находка Н4 ревизии `930da84`). Прежде здесь
    # стояла ВТОРАЯ дверь — прямой `service_pending_close` мимо `service_debt.verdict`, и она
    # закрывала строку ЦЕЛИКОМ даже при непустом `failed`: партия `gear,abs`, у которой лёг один
    # `gear`, уходила в «закрыто» вместе с не легшим `abs`, и о потере не говорил никто. Теперь
    # дверь та же, что у кнопок: гаснут РОВНО доказанные позиции, неудавшиеся остаются висеть и
    # получают голос сторожа. `row_terminal=True` — потому что «да» доверенного и есть терминал
    # самой заявки: «не сделано» ей законный исход, а не незакрытый хвост.
    # Ветка `else` — ОТКАТ (`SERVICE_DEBT=0`), прежний путь байт-в-байт, а не вторая дверь.
    if _service_debt_on():
        _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=list(written), batch=list(done),
                       odometer=odo_int, row_terminal=True,
                       write={"landed": bool(written), "known": True,
                              "detail": (f"фаза 2 ({confirmed_by or 'trusted'}): записано "
                                         f"{','.join(written) or '—'}"
                                         + (f", не легло {','.join(k for k, _e in failed)}"
                                            if failed else ""))})
    else:
        try:
            bridge.service_pending_close(chat_id=str(chat_id), topic_id=str(topic_id or ""),
                                         bike=bike,
                                         note=f"written={','.join(written)} by {confirmed_by}")
        except Exception:
            log.exception("  → service_pending_close упал")
    return written, failed


async def _sp_escalate_stuck(context, bridge, chat_id, topic_id, bike, declared, age_h, note):
    """B4: заявка висит дольше TTL → ОДНА эскалация владельцу (notify) + тег Пыма в теме; пометить note=escalated.
    После этого тайцам напоминания прекращаются (см. reminder). Запись в Лист1 НЕ трогаем."""
    # единицы времени по языку: 🇹🇭 «ชม.» (без кириллицы), 🇷🇺 «ч»
    age_ru = f"{int(age_h)}ч" if age_h is not None else "долго"
    age_th = f"{int(age_h)} ชม." if age_h is not None else "นาน"
    try:
        import notify
        notify.notify(f"🔧 ТО завис: {bike} ({_sp_labels_ru(declared)}) — заявка открыта {age_ru} без закрытия. "
                      f"Глянь/закрой вручную или дожми подтверждение.", force=True)   # боевой прод-алерт
    except Exception:
        log.exception("  → B4 эскалация владельцу (notify) упала")
    try:
        # ЗАМОК ПОВТОРОВ (вид G) — только на сообщение В ТЕМУ БАЙКА. Алерт владельцу (notify
        # выше) и пометка note=escalated замком НЕ трогаются: класс — подсказки в темах.
        # Состояние = сама заявка (рождение + перечень); возраст в состояние не входит.
        await _hint_send(context, kind="G", bike=bike,
                         state=("sp_escalate", declared),
                         chat_id=int(chat_id), topic_id=(int(topic_id) if topic_id else None),
                         text=(f"🐀 Splinter · 📌 {bike}\n"
                               f"🇹🇭 ⚠️ งานเซอร์วิส ({_sp_labels_th(declared)}) ค้างนาน {age_th} ยังไม่ปิด — {PYM_HANDLE} ช่วยปิด/ยืนยันหน่อยครับ 🙏\n"
                               f"{_SEP}\n"
                               f"🇷🇺 ⚠️ Заявка на ТО ({_sp_labels_ru(declared)}) висит {age_ru} без закрытия — {PYM_HANDLE}, закрой/подтверди вручную 🙏"))
    except Exception:
        log.exception(f"  → B4 эскалация в тему {bike} упала")
    try:
        new_note = (str(note) + " | escalated").strip(" |") if note else "escalated"
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike, note=new_note)
    except Exception:
        log.exception("  → B4 пометка note=escalated упала")
    log.info(f"  → ТО висяк ЭСКАЛАЦИЯ: {bike} age={age_ru} declared={declared} → владельцу+Пыму, тайцам стоп")


async def _sp_debt_voice(context, bridge, it, now):
    """СТОРОЖ ВИСЯКОВ — ВЕТКА ДОЛГА (`ждёт_подтверждения`): напоминание и эскалация по ВОЗРАСТУ.

    ПОРЯДОК ЗДЕСЬ И ЕСТЬ ЗАМОК. Сначала спрашиваем, вправе ли мы вообще говорить (`voice` —
    возраст), и только пройдя порог идём к миру за признаком 2 из трёх (перечитанная клетка
    регистра). Оба шага в эту сторону безопасны: возраст НЕ закрывает долг ни в одной ветке —
    `service_debt.voice` не умеет вернуть ни один из `CLOSERS` физически, — а клетка закрывает
    его ПО ФАКТУ, а не по времени. Молчим ровно в двух случаях: порог не пройден (ещё рано) либо
    запись ДОКАЗАНА (говорить не о чем). «Проверить не удалось» молчанием не является.

    ЦЕНУ ПЛАТИТ ТОЛЬКО ШУМЯЩАЯ СТРОКА: чтение парка стоит за порогом громкости, поэтому здоровый
    путь (долг моложе 6 ч, либо долгов нет вовсе) не платит мосту ни одного лишнего обращения."""
    bike = it.get("bike", "")
    chat_id = it.get("chat_id")
    topic_id = it.get("topic_id") or None
    declared = _sp_split(it.get("declared"))
    note = str(it.get("note") or "")
    # ГОЛОС ИДЁТ ПО ПОЗИЦИЯМ СЛЕДА, а не по полю `done`: `done` принадлежит ПОСЛЕДНЕМУ визиту
    # байка (мост кладёт его целиком), а долг — тем позициям, которые так и не легли. Следа нет
    # (легаси-строка) → прежний путь по `done` байт-в-байт.
    _led = service_debt.ledger_read(note)
    done = [k for k, _o in _led] or _sp_split(it.get("done")) or declared
    _want = service_debt.ledger_odometer(_led)
    odo_want = it.get("odometer") if _want is None else _want
    age_h = _sp_age_hours(it.get("created_at"), now)
    v = service_debt.voice(service_debt.STATUS, age_h, escalated=("escalated" in note),
                           remind_after_h=_SP_REMIND_AFTER_MIN / 60.0,
                           max_age_h=_SP_REMIND_MAX_AGE_H)
    if v["speak"] == service_debt.QUIET:
        return
    # ПРИЗНАК 2 ИЗ ТРЁХ — записали мимо бота (владелец рукой в Лист1). Спрашиваем ПЕРЕД тем как
    # шуметь: кричать о работе, которая уже лежит в регистре, — тот же ложный сторож наоборот.
    closed = _sp_debt_close(bridge, chat_id, topic_id, bike, kinds=done,
                            odometer=odo_want, row=it,
                            cell=_sp_debt_cell(bridge, bike, done, odo_want))
    if closed is not None and closed.get("closed"):
        return
    if v["speak"] == service_debt.ESCALATE:
        await _sp_escalate_stuck(context, bridge, chat_id, topic_id, bike, declared, age_h, note)
        return
    # B5 + троттл `last_reminded_at` — те же, что у прежней ветки (персист между рестартами).
    _k = (str(chat_id), str(topic_id or ""), bike)
    if now - _SP_LAST_SENT.get(_k, 0) < _SP_REMIND_THROTTLE_MIN * 60:
        return
    lr = it.get("last_reminded_at")
    if lr:
        try:
            import datetime as _dt
            ts = _dt.datetime.fromisoformat(str(lr).replace("Z", "+00:00")).timestamp()
            if (now - ts) / 60 < _SP_REMIND_THROTTLE_MIN:
                return
        except Exception:
            pass
    _age_ru = f"{int(age_h)}ч" if age_h is not None else "долго"
    _age_th = f"{int(age_h)} ชม." if age_h is not None else "นาน"
    # ЗАМОК ПОВТОРОВ (вид F, своё состояние). Текст адресован Пыму/владельцу и говорит «кнопка не
    # нажата», а НЕ «отпишись»: механик уже отписался, гонять его по своей же работе незачем.
    if await _hint_send(context, kind="F", bike=bike,
                        state=("sp_debt", it.get("created_at"), _sp_join(done)),
                        chat_id=int(chat_id),
                        topic_id=(int(topic_id) if topic_id else None),
                        text=(f"🐀 Splinter · 📌 {bike}\n"
                              f"🇹🇭 ⏳ งาน ({_sp_labels_th(done)}) ทำแล้วแต่ยังไม่ได้กดยืนยัน {_age_th} — "
                              f"{PYM_HANDLE}/เจ้าของ กดปุ่มยืนยันหน่อยครับ 🙏\n"
                              f"{_SEP}\n"
                              f"🇷🇺 ⏳ Работа ({_sp_labels_ru(done)}) сделана, но кнопку подтверждения "
                              f"не нажали {_age_ru} — {PYM_HANDLE}/владелец, подтвердите 🙏")) is HINT_SKIPPED:
        return
    _SP_LAST_SENT[_k] = now
    try:
        bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                                      last_reminded_at=__import__("datetime").datetime.now(
                                          __import__("datetime").timezone.utc).isoformat())
    except Exception:
        log.exception(f"  → долг ТО {bike}: отметка времени напоминания не легла")
    log.info(f"  → ДОЛГ ТО напоминание {bike} [{_sp_join(done)}] "
             f"age={(f'{age_h:.1f}ч' if age_h is not None else '?')} → {v['to']} ({v['why']})")


async def scheduled_service_pending_reminder(context, bridge):
    """Висяк: открытые заявки (заявлено/ждёт_факт) старше порога без отписки → напоминание (throttle + TTL).
    B4: старше _SP_REMIND_MAX_AGE_H → ОДНА эскалация владельцу, тайцам стоп. B5: in-memory анти-дубль. B6: лог отправок."""
    try:
        r = bridge.service_pending_list(open=True, older_than_min=_SP_REMIND_AFTER_MIN)
        items = r.get("items", []) if r.get("ok") else []
    except Exception:
        log.exception("  → service_pending_list (висяк) упал")
        return
    now = _time.time()
    for it in items:
        status = str(it.get("status"))
        # ВЕТКУ ВЫБИРАЕТ СЛЕД, А НЕ СТАТУС (23.08.2026, находка Н5). Статус принадлежит
        # ПОСЛЕДНЕМУ визиту байка: приезд редуктора переводил строку в `ждёт_факт`, и висевшие
        # позиции соседа замолкали — «строка живёт, о ней не говорит никто», ровно тот класс,
        # что закрыт 23.08 с другой стороны. Открытые позиции следа есть → долг, чей бы визит
        # ни переписал поля. Сегмент есть и ПУСТ → долг снят, строку ведёт прежний путь.
        # Сегмента нет вовсе → как было, по статусу. При `SERVICE_DEBT=0` — прежний `continue`.
        if _service_debt_on():
            _note_it = str(it.get("note") or "")
            _debt_row = bool(service_debt.ledger_read(_note_it)) or (
                status == service_debt.STATUS and not service_debt.ledger_present(_note_it))
        else:
            _debt_row = (status == service_debt.STATUS)
        if _debt_row:
            # ДОЛГ ПРОХОДИТ ПРОВЕРКУ ВОЗРАСТА, А НЕ ПРОПУСКАЕТСЯ ДО НЕЁ (23.08.2026). Прежде здесь
            # стоял голый `continue`, и он стоял ВЫШЕ проверки возраста (строки 7040-7041) —
            # поэтому работа, ждущая кнопки, не получала НИ висяк-напоминания, НИ B4-эскалации
            # владельцу: строка жила, и о ней не говорил никто. Комментарий «отдельный канал» был
            # верен по замыслу и ложен по факту — канала не существовало. Теперь он есть, и он
            # ЗДЕСЬ; отличается только адресат (Пым/владелец, а не механик: механик своё сделал).
            # Ручка `SERVICE_DEBT=0` возвращает прежний `continue` байт-в-байт.
            if _service_debt_on():
                try:
                    await _sp_debt_voice(context, bridge, it, now)
                except Exception:
                    log.exception(f"  → долг ТО {it.get('bike')}: ветка сторожа упала")
            continue
        bike = it.get("bike", "")
        chat_id = it.get("chat_id"); topic_id = it.get("topic_id") or None
        declared = _sp_split(it.get("declared"))
        note = str(it.get("note") or "")
        # B4: TTL по возрасту заявки → одна эскалация владельцу/Пыму, дальше тайцам не долбим
        age_h = _sp_age_hours(it.get("created_at"), now)
        if age_h is not None and age_h >= _SP_REMIND_MAX_AGE_H:
            if "escalated" not in note:
                await _sp_escalate_stuck(context, bridge, chat_id, topic_id, bike, declared, age_h, note)
            continue
        # B5: in-memory анти-дубль (две близкие итерации в одном процессе — рестарт first=300 рядом с часовым тиком)
        _k = (str(chat_id), str(topic_id or ""), bike)
        if now - _SP_LAST_SENT.get(_k, 0) < _SP_REMIND_THROTTLE_MIN * 60:
            continue
        # throttle по last_reminded_at (персист между рестартами)
        lr = it.get("last_reminded_at")
        if lr:
            try:
                import datetime as _dt
                ts = _dt.datetime.fromisoformat(str(lr).replace("Z", "+00:00")).timestamp()
                if (now - ts) / 60 < _SP_REMIND_THROTTLE_MIN:
                    continue
            except Exception:
                pass
        try:
            # ЗАМОК ПОВТОРОВ (вид F) — ЗДЕСЬ ОН И РЕШАЕТ КЛАСС. Состояние = САМА ЗАЯВКА: когда
            # родилась, в каком статусе, что заявлено. Возраст и номер попытки состоянием НЕ
            # являются — на них и держались серии ×6/×6/×5 (за все три статус не менялся ни
            # разу: 'ждёт_факт' от первой отправки до последней). Механик дозаявил работу или
            # заявка сменила статус → состояние другое → напоминание уходит снова; заявку
            # закрыли и открыли новую → другое рождение → тоже снова (живой случай NMAX 9548
            # 14.08: возраст сбросился 23.0 ч → 6.4 ч — это ВТОРАЯ заявка, а не повтор первой).
            # Троттл 6 ч и TTL 48 ч НЕ тронуты и стоят выше — замок лишь режет ПОВТОР ТЕКСТА.
            if await _hint_send(context, kind="F", bike=bike,
                                state=("sp_stuck", it.get("created_at"), status, declared),
                                chat_id=int(chat_id),
                                topic_id=(int(topic_id) if topic_id else None),
                                text=(f"🐀 Splinter · 📌 {bike}\n"
                                      f"🇹🇭 ⏳ {bike} แจ้งเข้าเซอร์วิส ({_sp_labels_th(declared)}) แต่ยังไม่แจ้งผล — เสร็จหรือยังครับ?\n"
                                      f"{_SEP}\n"
                                      f"🇷🇺 ⏳ {bike} на ТО ({_sp_labels_ru(declared)}), результат не отписан — закончили?")) is HINT_SKIPPED:
                continue        # повтор подавлен → ни отметки времени, ни записи в заявку
            _SP_LAST_SENT[_k] = now
            bridge.service_pending_upsert(chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                                          last_reminded_at=__import__("datetime").datetime.now(
                                              __import__("datetime").timezone.utc).isoformat())
            _att = (int(age_h // (_SP_REMIND_THROTTLE_MIN / 60)) + 1) if age_h is not None else 1
            log.info(f"  → ТО висяк-напоминание {bike} attempt≈{_att} "
                     f"age={(f'{age_h:.1f}ч' if age_h is not None else '?')} status={status}")  # B6
        except Exception:
            log.exception(f"  → висяк-напоминание {bike} упало")


async def _handle_servicing(msg, context, bridge, claude, photo_msgs=None):
    """Обслуживание байков — события + vision на фото (топливо/пробег/повреждения).
    photo_msgs — пачка сообщений-фото (альбом склеен по media_group_id; для одиночного = [msg]).
    Альбом разбираем по каждому фото, но СЛИВАЕМ в один вердикт → один ответ."""
    text = msg.text or msg.caption or ""
    if photo_msgs is None:
        photo_msgs = [msg] if msg.photo else []
    has_photo = bool(photo_msgs)
    chat_id = msg.chat_id
    group_name = group_label(chat_id)
    topic_id = getattr(msg, "message_thread_id", None)
    # Название темы = байк (по договорённости). Запоминаем когда встречается.
    _remember_topic_name(chat_id, topic_id, msg)

    # Лист закрытия: команда «закрытие <байк> [поле=значение]» (ручные доплаты + показ карточки)
    if (text or "").strip().lower().startswith(("закрыти", "closing")):
        await _handle_closing_cmd(msg, context, bridge, text)
        return

    # ЗАХОД 2: запрос КАРТОЧКИ байка («инфа/статус/что по байку») — отвечаем карточкой из ЧИТАЕМЫХ
    # источников (пробег, ТО Oil, J/K/L, аренда), НИЧЕГО не пишем. Только текст без фото.
    # Анти-спам (пакет Б): карточку шлём ТОЛЬКО когда к боту ОБРАЩАЮТСЯ (@tag/reply) ИЛИ это ЯВНЫЙ
    # короткий статус-запрос, и не чаще раза в окно на тему (троттл). Раньше — на любое статус-слово
    # в общем трёпе без дедупа → троила карточку.
    if (text.strip() and not has_photo and _is_status_request(text)
            and (_addressed_bot(msg, context) or _is_explicit_status_query(text))):
        _card_bike = bike_from_topic(chat_id, topic_id) or ""
        if _card_bike and _card_allowed(chat_id, topic_id):
            log.info(f"  → запрос карточки байка: {_card_bike}")
            try:
                await _send_bike_card(context, bridge, chat_id, topic_id, _card_bike)
            except Exception:
                log.exception("  → ошибка карточки байка")
            return
        if _card_bike:
            log.info(f"  → карточка {_card_bike} подавлена троттлом (<{_CARD_COOLDOWN}s)")
            return

    # Разбираем текст (если есть) на событие
    parsed = {}
    if text.strip():
        parsed = _parse_json(claude.quick(SERVICING_SYSTEM, text, max_tokens=300, model="MAIN",
                                 tag="servicing", expect_json=True))

    # Разбираем фото через vision (топливо/пробег/повреждения). На альбом — каждое фото,
    # затем агрегируем в ОДИН вердикт (один ответ вместо дубля на каждое фото).
    vis = {}
    if has_photo:
        vis_list = []
        for pm in photo_msgs:
            img = await _download_photo(pm)
            if not img:
                log.warning(f"  → photo download failed")
                continue
            # Фото-байк (ТО/приёмка) — НЕ деньги (Поправка Б штаба): upstream упал → vision() сам
            # логирует «upstream down (graceful '')» и отдаёт '' → лог БЕЗ пуша, разбор деградирует
            # штатно (raise_on_upstream не включаем — громкий пуш только на ДЕНЬГАХ).
            v = _parse_json(claude.vision(VISION_BIKE_SYSTEM, img, max_tokens=400))
            log.info(f"  → vision: fuel={v.get('fuel')} mileage={v.get('mileage')} "
                     f"conf={v.get('mileage_confidence')} tire={v.get('tire')} damage={v.get('damage')}")
            # Копим разбор в буфер недавних фото ЭТОЙ ТЕМЫ (для вопросов "проверь фото резины/пробега")
            _remember_recent_photo(chat_id, v, pm, topic_id=topic_id)
            vis_list.append(v)
        vis = _aggregate_album_vis(vis_list)
        if len(vis_list) > 1:
            log.info(f"  → альбом: склеил {len(vis_list)} фото → mileage={vis.get('mileage')} "
                     f"conf={vis.get('mileage_confidence')} damage={vis.get('damage')} dirt={vis.get('dirt')}")

    # Работы из разбора — отдельно от type (техник может перечислить работы, а parse вернуть
    # type≠"event": так и было в кейсе NINJA 6334 09.06 — works был, но в события не записалось и молчали).
    works = [str(w).strip() for w in (parsed.get("works") or []) if w and str(w).strip()]

    # Диагностика parse (закрываем пробел: раньше результат разбора в лог НЕ писался — кейс
    # «молчание на текст-работ» был невидим в splinter.log). Пишем ДО любых ранних return.
    log.info(f"  → parse: type={parsed.get('type')} event_type={parsed.get('event_type')} "
             f"mileage={parsed.get('mileage')} works={works}")

    # Если ни текст-событие, ни работы, ни осмысленное фото — выходим.
    is_event = parsed.get("type") == "event"
    has_vis = bool(vis and (vis.get("fuel") or vis.get("mileage") or vis.get("damage")))
    if not is_event and not works and not has_vis and not has_photo:
        return

    # Сливаем: текст приоритетнее для типа события, фото — для топлива/пробега
    fuel = parsed.get("fuel") or vis.get("fuel") or ""
    mileage = parsed.get("mileage") or vis.get("mileage") or ""
    bike = parsed.get("bike") or bike_from_topic(chat_id, topic_id) or ""
    event_type = parsed.get("event_type") or ("photo" if has_photo else "other")
    notes = (parsed.get("notes") or vis.get("notes") or "")[:200]
    if vis.get("damage"):
        notes = (notes + f" | повреждения: {vis['damage']}").strip()[:200]
    elif vis.get("dirt"):
        notes = (notes + " | грязный").strip()[:200]

    _u_sp = getattr(msg, "from_user", None)
    _sender = ("@" + _u_sp.username) if (_u_sp and getattr(_u_sp, "username", None)) else ""

    # === RETURN-КОНТЕКСТ (пакет Б) — СЧИТАЕМ ПЕРВЫМ, ВОЗВРАТ ВЫИГРЫВАЕТ (Слой 1 наблюдателя выдач) ===
    # Принцип: лучше лишний раз завести closing, чем ПОТЕРЯТЬ реальный возврат (деньги/закрытие важнее
    # косметики советов). Поэтому _ret_ctx НЕ зависит от handover. При возврате гасим phase-1 intake и
    # repair-наряд (works→в «события» инфо), ведём ветку ПРИЁМКИ (closing_upsert + пинг Пыму).
    _ret_ctx = _is_return_context(parsed, text, vis, bridge, bike)
    if _ret_ctx:
        log.info(f"  → RETURN-контекст по {bike or '?'}: ветка приёмки (phase-1/наряд погашены)")

    # === HANDOVER-КОНТЕКСТ (выдача клиенту) — ТОЛЬКО если это НЕ возврат. Гасит советы ухода/стоянки и нудёж «нет фото».
    # Развязка: возврат имеет приоритет → конфликт «вернул…выдам» трактуется как ВОЗВРАТ (closing не теряем).
    _ho_ctx = (not _ret_ctx) and _is_handover_context(parsed, text)
    if _ho_ctx:
        log.info(f"  → HANDOVER-контекст по {bike or '?'}: выдача клиенту (советы ухода/стоянки/нудёж-фото погашены)")

    # === ФАЗА 1 (двухфазный ТО): механик ЗАЯВИЛ работы (intake/масло-контекст, БЕЗ маркера «готово»
    # и без свежего пробега) → фиксируем НАМЕРЕНИЕ в «то_заявки», в Лист1/обслуживание НИЧЕГО.
    # Записываем intake-событие для истории и НЕ продолжаем (заявка != факт). Факт = отдельное «готово».
    # Сигнал заявки = СТРОГО event_type=="intake" («привёз/пригнал на ТО» — будущее намерение, как в
    # реальном логе 06-20). НЕ ловим оил-контекст в общем — иначе перехватим пояснения работ (буфер-флоу).
    _sp_declared = _declared_kinds(text, works, vis)
    _sp_is_intake = (parsed.get("event_type") == "intake") and not _is_oil_done_marker(text, vis)
    if _sp_is_intake and _sp_declared and bike and not _ret_ctx and not _sp_open(bridge, chat_id, topic_id, bike):
        try:
            bridge.add_event(msg_date=(str(msg.date.date()) if msg.date else ""),
                             group=group_name + (f" / тема {topic_id}" if topic_id else ""),
                             bike=bike, event_type="intake", notes=notes[:200],
                             photos=1 if has_photo else 0, sender=_sender,
                             msg_id=f"{chat_id}:{msg.message_id}")
            await service_phase1_intake(context, bridge, chat_id, topic_id, bike, _sp_declared, works_raw=works)
        except Exception:
            log.exception("  → ТО фаза1 (intake) упала")
        return

    # === РАЗБОР ПЕРЕЧНЯ РАБОТ ПО АДРЕСАМ (вариант A: строка-на-работу) ===
    # Масло → кол.I (флоу ниже), gear/abs/возд.фильтр → группа B (кол.J/K/L, флоу ниже).
    # ИНФО-работы (колодки/цепь/масл.фильтр/вилка/прочее) → история «события» ОТДЕЛЬНОЙ строкой на
    # работу, с привязкой пробега. Перечень в одну repair-строку БОЛЬШЕ не валим — разносим.
    non_oil_works = [w for w in works if not _is_oil_work(w)]
    if non_oil_works:
        event_type = "repair"   # для force/_service_ctx ниже (перечень в notes НЕ лепим)
    info_works = [w for w in works if _classify_work(w) == "info"]
    # ОДНО ПРАВИЛО ЗАПИСИ (класс-фикс 4957): в «события» идёт только ЧЕЛОВЕЧЕСКОЕ число.
    # Раньше здесь стоял сырой vis.mileage — и ветка инфо-работ писала OCR мимо подтверждения
    # («колодки — 38982 км», splinter.log 29.07 09:32:16), пока ветка обычного события уже была
    # закрыта гейтом 06c1ab2. Теперь обе ветки берут км из ОДНОЙ функции.
    km_now = _km_for_record(parsed, vis)
    _ev_msg_id = f"{chat_id}:{msg.message_id}"
    _msg_date = str(msg.date.date()) if msg.date else ""

    # Пришёл чёткий пробег в теме → дописать ОТЛОЖЕННЫЕ инфо-работы прошлого сообщения с этим км.
    _logged_works = []
    if km_now:
        # Перевести неизвестные работы из буфера ДО flush (один LLM-вызов, обновляет _WORK_TH_LEARNED).
        _pend_peek = _PENDING_WORKS.get((chat_id, topic_id))
        if _pend_peek:
            _learn_works_th(claude, _pend_peek.get("works", []))
        # ДВЕРЬ 3 (пробег назван В ЭТОМ сообщении) — та же единая логика выгрузки, что у кнопки и фазы 2.
        _fl_written, _ = _km_door(bridge, chat_id, topic_id, bike, str(km_now),
                                  source="пробег в сообщении", msg_date=_msg_date)
        _logged_works += _fl_written

    _ev_r = None
    if info_works:
        # Перевести неизвестные работы из текущего сообщения (один LLM-вызов, fail-safe = fallback).
        _learn_works_th(claude, info_works)
        if km_now:
            # Пробег есть В ЭТОМ сообщении → пишем инфо-работы СРАЗУ, по строке на работу, с км.
            _logged_works += _write_info_works(bridge, group_name, topic_id, bike, info_works,
                                               str(km_now), _ev_msg_id, _msg_date, chat_id=chat_id)
        else:
            # Пробега нет → ДОПИСЫВАЕМ перечень в буфер (не замещаем: класс 22.08 — вторая партия
            # темы стирала первую молча); запишем при приходе пробега (flush). Ниже уйдёт переспрос.
            _pw_all = _pw_add(chat_id, topic_id, info_works, bike, _ev_msg_id)
            log.info(f"  → инфо-работы отложены до пробега: {info_works} (тема {topic_id})"
                     + (f" | в буфере всего {len(_pw_all)}: {_pw_all}" if len(_pw_all) > len(info_works) else ""))
    else:
        # Нет инфо-работ — обычное событие сообщения (фото/возврат/топливо/только колоночные) пишем как раньше.
        # OCR-дыра (задача 383, гейт 06c1ab2): сырой vision-пробег до подтверждения человеком НЕ пишем
        # в события. Число берём ТОЙ ЖЕ функцией, что и ветка инфо-работ выше — правило одно на обе.
        _ev_mileage = _km_for_record(parsed, vis)
        _ev_kw = dict(
            msg_date=_msg_date,
            group=group_name + (f" / тема {topic_id}" if topic_id else ""),
            bike=bike, event_type=event_type, fuel=str(fuel), mileage=str(_ev_mileage),
            photos=1 if has_photo else 0, notes=notes, msg_id=_ev_msg_id, sender=_sender,
        )
        _ev_r = bridge.add_event(**_ev_kw)
        if _ev_mileage and (_ev_r or {}).get("ok"):
            _km_event_journal(chat_id, topic_id, _ev_mileage, plain=[_ev_kw], bike=bike,
                              group=group_name, msg_date=_msg_date)
    # ДИАГ: бот раньше ВЫБРАСЫВАЛ return add_event — теперь видно saved/duplicate/error + разбор работ.
    log.info(f"  → add_event: ok={(_ev_r or {}).get('ok')} saved={(_ev_r or {}).get('saved')} "
             f"duplicate={(_ev_r or {}).get('duplicate')} error={(_ev_r or {}).get('error')} "
             f"msg_id={_ev_msg_id} info_works={len(info_works)} km_now={km_now or '-'} event_type={event_type}")

    # Лист закрытия: на ВОЗВРАТЕ авто-создаём/обновляем строку закрытия (seed bike/fuel/date + booking_id).
    # Ветка ПРИЁМКИ — на ЛЮБОМ return-контексте (не только точном event_type=="return"): сид Лист закрытия
    # (топливо/пробег/booking) + пинг Пыму по депозиту/ущербу. closing_upsert = Bot Data (своя таблица).
    # НЕ зависим от _ev_r (при info-работах событие пишет _write_info_works, _ev_r=None).
    if _ret_ctx and bike:
        _cu = None
        try:
            _bid, _bname, _bend = _closing_resolve_booking(bridge, bike)
            _dret = _msg_date or _bend or ""
            _cu = bridge.closing_upsert(booking_id=(_bid or ""), bike=bike, name=_bname,
                                        date_return=_dret, fuel_level=str(fuel or ""),
                                        note=("" if _bid else "бронь не найдена"))
            log.info(f"  → closing авто (return-ctx): bike={bike} booking_id={_bid} ok={(_cu or {}).get('ok')} "
                     f"total_due={(_cu or {}).get('total_due')}")
            # Пинг Пыму ПРИЁМКИ — только если нет damage (damage-ветка ниже пингует сама, без дубля).
            if not vis.get("damage"):
                _ru_intake = (f"Принял возврат {bike}"
                              + (f", топливо {fuel}" if fuel else "")
                              + (f", пробег {mileage}" if mileage else "")
                              + f". Занёс в лист закрытия. {PYM_HANDLE} — глянь депозит/ущерб 🙏")
                await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                            text=bilingual_from_ru(claude, _ru_intake))
        except Exception as e:
            log.warning(f"  → closing авто-создание не удалось: {e}")
        # O3-3b фаза II ДОПОЛНЕНИЕ (closing-путь выше не трогаем): карточка ПРИЁМА аппруверам —
        # предложение закрыть аренду в CRM (В аренде→Завершена) после «да». Свой try —
        # сбой карточки возврат/лист закрытия НЕ ломает. km = пробег return-контекста.
        try:
            await _return_close_card(context, bridge, bike, km=str(mileage or ""),
                                     total_due=(_cu or {}).get("total_due"))
        except Exception as e:
            log.warning(f"  → карточка приёма (закрытие) не удалась: {e}")

    # === ВЫДАЧА (этап 2 трекинга): на handover-контексте фиксируем state «в аренде» в bot-owned
    # вкладке состояния. Зеркало ветки возврата выше (_ret_ctx). Источник деталей = CRM
    # (_closing_resolve_booking), текст = только триггер. Защита от дубля = простой upsert по bike
    # (идемпотентно, без гейта на смену статуса). guard: пустой bike → пропуск + лог (не пишем мусор).
    if _ho_ctx and bike:
        try:
            _bid, _bname, _bend = _closing_resolve_booking(bridge, bike)
            _bk = (bridge.find_bike(bike) or {}).get("name") or bike   # каноничное имя = ключ вкладки
            bridge.state_set(bike=_bk, status="в аренде", client=_bname,
                             date_due=_bend, booking_id=(_bid or ""),
                             last_event_msg_id=_ev_msg_id)
            log.info(f"  → state выдача (handover-ctx): bike={_bk} status=в аренде "
                     f"booking_id={_bid} client={_bname or '-'} date_due={_bend or '-'}"
                     + ("" if _bid else " | бронь не найдена (детали добьются позже)"))
        except Exception as e:
            log.warning(f"  → state выдача не удалась: {e}")
        # O3-3a ДОПОЛНЕНИЕ (state-путь выше не трогаем): предложить активацию брони в CRM
        # карточкой аппруверам. Свой try — сбой активационной ветки handover НЕ ломает.
        try:
            await _handover_activation_card(context, bridge, bike)
        except Exception as e:
            log.warning(f"  → карточка активации выдачи не удалась: {e}")
    elif _ho_ctx and not bike:
        log.info("  → state выдача пропущена: handover-ctx, но bike пуст (не пишем мусор)")

    # ЕДИНАЯ СВОДКА: инфо-работы записаны (flush/немедленно) → НЕ шлём отдельно, копим в накопитель.
    # Сводка уйдёт ОДНИМ сообщением в терминальной точке цикла (после масла/столбцов).
    if _logged_works:
        acc = _summary_acc(chat_id, topic_id)
        acc["works"] += _logged_works
        acc["works_km"] = str(km_now)
        acc["current_km"] = str(km_now)

    # === ТО-трекер ===
    _conf_ok = str(vis.get("mileage_confidence", "")) != "low"
    # Подсказка (НЕ решение): в сообщении маркер «масло заменили» → после подтверждения пробега
    # зададим вопрос «после замены или просто пробег?» даже если ТО формально ещё не подошло.
    oil_hint = _is_oil_done_marker(text, vis)
    if vis.get("mileage") and not parsed.get("mileage") and _conf_ok:
        # Пробег с ФОТО приборки → СНАЧАЛА подтверждаем цифру (vision врёт на LCD) + сторож B,
        # затем _after_mileage решит: спросить кнопками или просто квитанция.
        await _ask_mileage_confirm(context, chat_id, topic_id, bike,
                                   str(vis.get("mileage")), oil_hint=oil_hint)
    elif mileage and _conf_ok:
        # Пробег из ТЕКСТА (человек ввёл руками) — доверяем числу, сразу решаем (спросить/квитанция).
        try:
            await _after_mileage(context, bridge, chat_id, topic_id, bike, mileage, oil_hint)
        except Exception:
            log.exception("  → ошибка ТО-трекера")

    # === Группа B (Фаза 1): запись регламента в СВОЙ столбец Лист1 (gear→J/abs→K/airfilter→L) ===
    # Техник назвал работу группы B + есть пробег → кнопка-фиксация (боевая запись ТОЛЬКО доверенным).
    # Масло (кол.I) идёт своим флоу выше; info-работы (масл.фильтр/колодки/цепь) — только в «события».
    # Пробег показываем в кнопке — человек сверяет цифру перед записью; set_fleet_service хранит откат.
    # RETURN-контекст: НЕ наряд на ремонт — works на возврате уже легли в «события» (инфо) выше; кнопки-фиксацию ТО гасим.
    if works and bike and mileage and _conf_ok and not _ret_ctx:
        seen_kinds = []
        for w in works:
            k = _classify_work(w)
            if k in ("gear", "abs", "airfilter") and k not in seen_kinds:
                seen_kinds.append(k)
        for k in seen_kinds:
            try:
                await _ask_service_col(context, chat_id, topic_id, bike, k, str(mileage),
                                      bridge=bridge)
            except Exception:
                log.exception(f"  → ошибка кнопки фиксации группы B ({k})")

    # Реальное ПОВРЕЖДЕНИЕ → зовём Пыма (это к осмотру / возможным вычетам).
    # Грязь сюда НЕ попадает — она отсекается на уровне vision (damage=null, dirt=true).
    if vis.get("damage"):
        # RU — основа (с конкретикой повреждения + депозит), TH = точный перевод этого RU (вариант 1).
        _ru_dmg = (f"⚠️ {PYM_HANDLE}, на фото повреждения: {vis['damage']} — глянь. "
                   f"Если это возврат — посмотри по депозиту 🙏")
        # ЗАМОК ПОВТОРОВ (вид J). Состояние = ЧТО назвал vision: другое повреждение — другое
        # состояние, подсказка уходит снова; тот же скол, снятый второй раз, — повтор.
        await _hint_send(context, kind="J", bike=bike, state=("damage", vis["damage"]),
                         chat_id=chat_id, topic_id=topic_id,
                         text=bilingual_from_ru(claude, _ru_dmg))
        return

    # === Пояснение работ ТЕКСТОМ без свежего пробега В ЭТОМ сообщении ===
    # Кейс NINJA 6334 09.06: техник перечислил работы текстом, фото пробега в ЭТОМ сообщении нет
    #   → раньше бот молчал (ни события, ни реплики). Теперь НЕ молчим:
    #   квитанция «записал работы» + при работах СО своим столбцом (масло/gear/abs/возд.фильтр) — переспрос пробега.
    # «Свежий пробег в ЭТОМ сообщении» = чёткое число из текста ИЛИ high-ODO с фото ЭТОГО сообщения
    #   (mileage уже = parsed.mileage или vis.mileage; буфер сюда НЕ входит — он и давал ложное подавление).
    # В столбец БЕЗ пробега НЕ пишем: запись группы B/масла выше по потоку требует mileage — её не трогаем.
    km_this_msg = bool(mileage) and _conf_ok
    if works and not km_this_msg:
        # (a) НЕ ЗАДВАИВАТЬ: ОДНО сообщение. msg_work_receipt уже называет работы И просит пробег
        # («Принял работы {works} — пришли пробег») → пробег покрыт для ВСЕХ работ (правило «пробег всегда»).
        # Дублирующий msg_ask_odometer (блок2, к тому же с хардкод-«масло») убран.
        # row12 (аудит 08.07): работы группы B (gear/abs/airfilter) без пробега В ЭТОМ сообщении
        # РАНЬШЕ терялись молча (кнопка фиксации ниже требует пробег в том же сообщении, инцидент
        # X MAX GREEN 4248 06:11). Теперь фиксируем их в то_заявке 'ждёт_факт': подтверждённый
        # одометр довезёт до кнопки Пыма (B1), Инфо-карточка показывает «в работе». На возврате
        # (_ret_ctx) заявку не открываем — works уже легли в «события» (не наряд).
        if bike and not _ret_ctx:
            # КЛАСС-ФИКС 4957 (корень 3): фильтр держал ровно gear/abs/airfilter, и МОТОРНОЕ МАСЛО
            # выпадало из перечня совсем — 29.07 механик сдал масло+редуктор+две пары колодок, а в
            # заявку легло только ['gear'] (splinter.log 09:24:47). Колодки жили в «событиях», масло
            # не жило нигде: у него есть кол.I, но без одометра туда не пишут, а заявка его не брала.
            # Теперь берём ВСЕ колоночные виды (_SP_COL_KINDS) — заявка доводит масло до кнопки Пыма
            # ровно так же, как редуктор; запись в Лист1 по-прежнему только по его «да».
            _bkinds = [k for k in _declared_kinds(text, works, vis)
                       if k in _SP_COL_KINDS and (k != "oil" or _oil_named_explicitly(text, works, vis))]
            if _bkinds:
                _sp0 = {}
                _decl_all = _done_all = []
                _staged = False
                try:
                    _sp0 = _sp_open(bridge, chat_id, topic_id, bike) or {}
                    _decl_all = _sp_merge_done(_sp_split(_sp0.get("declared")), _bkinds)
                    _done_all = _sp_merge_done(_sp_split(_sp0.get("done")), _bkinds)
                    bridge.service_pending_upsert(
                        chat_id=str(chat_id), topic_id=str(topic_id or ""), bike=bike,
                        declared=_sp_join(_decl_all), done=_sp_join(_done_all),
                        status="ждёт_факт")
                    log.info(f"  → работы группы B без пробега → то_заявка ждёт_факт: {_bkinds} ({bike})")
                    _staged = True
                except Exception:
                    log.exception("  → заявка на работы группы B (без пробега) упала")
                # СНАЧАЛА СПРАШИВАЕМ СВОЙ ОДОМЕТР, а уже потом человека (23.08.2026). Дверь судила
                # ТОЛЬКО текущее сообщение: за 60 суток из 18 таких вопросов у 8 число по этому
                # байку УЖЕ было подтверждено, у трёх — минутами ранее (замер в шапке `odo_fresh`).
                # Свежее число САМО НИКУДА НЕ ПИШЕТСЯ: оно едет в кнопку Пыму — тот же гейт Лист1,
                # где он видит цифру глазами и подтверждает «да». Уже висящую кнопку с тем же
                # числом вторым вопросом не подпираем (заявка уже 'ждёт_подтверждения').
                if _staged:
                    try:
                        _known = _odo_known_fresh(bridge, bike)
                        if (_known.get("use")
                                and str(_sp0.get("status") or "") != "ждёт_подтверждения"):
                            log.info(f"  → «принял работы — пришли пробег» НЕ нужен — "
                                     f"{_known['why']} ({bike})")
                            await _sp_advance_to_confirm(context, bridge, chat_id, topic_id, bike,
                                                         _decl_all, _done_all, _known["km"])
                            return
                    except Exception:
                        log.exception("  → короткий путь по своему одометру не удался "
                                      "(fail-safe: спрашиваем пробег, как спрашивали)")
        # ЗАМОК ПОВТОРОВ (вид I). Состояние = ПЕРЕЧЕНЬ работ: назвали другие работы — другое
        # состояние, квитанция уходит снова; тот же перечень второй раз — повтор.
        await _hint_send(context, kind="I", bike=bike, state=("works", works),
                         chat_id=chat_id, topic_id=topic_id, text=msg_work_receipt(bike, works))
        return

    # Масло-контекст, но БЕЗ чёткого пробега в ЭТОМ сообщении → САМ просим ЧЁТКОЕ фото одометра.
    # (damage уже отработан выше и сделал return — повреждение приоритетнее.)
    # Ничего в ТО не пишем, число не выдумываем. Анти-спам: буфер high-пробега + троттлинг.
    no_clear_km = (not mileage) or str(vis.get("mileage_confidence", "")) == "low"
    if _is_oil_context(text, vis) and no_clear_km and _should_ask_odometer(chat_id, topic_id):
        # ЗАМОК ПОВТОРОВ (вид A1). Состояние = «просим одометр под масло, чёткого пробега нет».
        # Пришёл пробег — ветка не срабатывает вовсе; не пришёл — просить второй раз за сутки
        # нечего. Кулдаун 10 мин (`_should_ask_odometer`) НЕ тронут и стоит выше.
        sent = await _hint_send(context, kind="A1", bike=bike, state=("ask_odo", "oil"),
                                chat_id=chat_id, topic_id=topic_id,
                                text=msg_ask_odometer(bike, kinds=["oil"]))  # (b) масло по факту oil-контекста
        if sent is not HINT_SKIPPED:
            _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос
        return

    # Только ГРЯЗЬ (без повреждений) → мягко просим помыть/обработать. Пыма НЕ тегаем.
    # Фикс C: в сервис-контексте совет «помыть/воск/чехол» неуместен — идёт работа по ТО, не мойка.
    # Сервис-контекст = масло/ремонт/чек ИЛИ фото приборки с пробегом (ТО-флоу) ИЛИ открыт вопрос svc по теме.
    _service_ctx = (oil_hint or _is_oil_context(text, vis)
                    or event_type == "repair" or vis.get("kind") == "receipt"
                    or bool(vis.get("mileage"))
                    or _svc_question_open(chat_id, topic_id))
    # HANDOVER: байк выдаётся клиенту — совет «помыть/воск/чехол» (стоянка) неуместен → гасим.
    if vis.get("dirt") and not _service_ctx and not _ho_ctx:
        # ЗАМОК ПОВТОРОВ (вид C). Состояние = вердикт vision о грязи. Пока байк числится
        # грязным, состояние не меняется — совет «помыть» второй раз за сутки ничего не
        # сообщает; помыли (dirt отпал) — ветка не срабатывает вовсе, замок тут ни при чём.
        await _hint_send(context, kind="C", bike=bike, state=("dirt", vis.get("dirt")),
                         chat_id=chat_id, topic_id=topic_id, text=msg_dirty_care(bike))
        return

    # Возврат без топлива/пробега → напоминаем фото. НЕ при handover (выдача — свой флоу) и НЕ если
    # пробег темы уже свежий в буфере (бот уже видел одометр — не нудим повторно).
    if (event_type in ("return", "handover") and (not fuel or not mileage)
            and not _ho_ctx and not last_mileage_in_topic(chat_id, topic_id)):
        # ЗАМОК ПОВТОРОВ (вид D). Состояние = вид события И ЧЕГО не хватает: пришло топливо,
        # но не пробег — состояние другое, напоминание уходит снова.
        await _hint_send(context, kind="D", bike=bike,
                         state=("no_photo", event_type, bool(fuel), bool(mileage)),
                         chat_id=chat_id, topic_id=topic_id, text=msg_photo_reminder(bike))


def msg_mileage_ok(bike, km, next_km, km_left):
    """Короткая квитанция на подтверждённый текущий пробег, когда ТО в норме (не due/overdue).
    Двуязычно RU/TH. Если next_km неизвестен (нет ТО Oil в кол.I) — без ТО-детали."""
    head = f"🐀 Splinter · 📌 {bike}" if bike else "🐀 Splinter"
    if next_km:
        try:
            left = int(km_left)
            left_th = f" (เหลือ ~{left} กม.)"
            left_ru = f" (осталось ~{left} км)"
        except (ValueError, TypeError):
            left_th = left_ru = ""
        return (
            f"{head}\n"
            f"🇹🇭 ✅ รับเลขไมล์ {km} กม. แล้วครับ — รอบเปลี่ยนน้ำมันปกติ ครบกำหนดถัดไปที่ {next_km} กม.{left_th}\n"
            f"🇷🇺 ✅ Пробег {km} км принят. ТО в норме, следующее на {next_km} км{left_ru}"
        )
    return (
        f"{head}\n"
        f"🇹🇭 ✅ รับเลขไมล์ {km} กม. แล้วครับ\n"
        f"🇷🇺 ✅ Пробег {km} км принят"
    )


def msg_service_due(bike, stype, current_km, next_km, status):
    """Двуязычное напоминание о ТО для закрепа в теме байка."""
    type_th = {"oil": "เปลี่ยนน้ำมันเครื่อง", "tire": "เปลี่ยนยาง", "tyre": "เปลี่ยนยาง"}.get(stype, stype)
    type_ru = {"oil": "замена масла", "tire": "замена резины", "tyre": "замена резины"}.get(stype, stype)
    over = ""
    if status == "overdue" and next_km and current_km:
        od = int(current_km) - int(next_km)
        over_th = f" (เกินมา {od} กม.)"
        over_ru = f" (просрочено на {od} км)"
    else:
        over_th = over_ru = ""
    head_th = "⚠️ ถึงกำหนด" + (over_th if status == "overdue" else "")
    head_ru = "⚠️ Пора" + (over_ru if status == "overdue" else "")
    return (
        f"🐀 Splinter · 📌 {bike}\n"
        f"🇹🇭 {head_th}: {type_th}\n"
        f"   เลขไมล์ตอนนี้ {current_km} กม. · ครบกำหนดที่ {next_km} กม.\n"
        f"🇷🇺 {head_ru}: {type_ru}\n"
        f"   текущий пробег {current_km} км · срок на {next_km} км\n"
        f"\n"
        f"🇹🇭 หลังทำเสร็จ ส่งรูปเลขไมล์ + ใบเสร็จด้วยครับ 🙏\n"
        f"🇷🇺 После выполнения — фото пробега + чек от сервиса 🙏"
    )


def _oil_interval(bike_name):
    """Интервал замены масла (км) по типу байка:
    - Скутеры NMAX / XMAX / ADV / FORZA / PCX → 4000
    - XADV и мотоциклы (XSR, CB, CBR, MT, NINJA, VULCAN, R7...) → 5000
    """
    n = str(bike_name).lower().replace("-", "").replace(" ", "")
    if "xadv" in n:
        return 5000
    if "nmax" in n or "xmax" in n or "adv" in n or "forza" in n or "pcx" in n or "click" in n:
        return 4000
    return 5000


# ===================== INTAKE — приём карточек брони (ЭТАП A) =====================
# Только: парсинг карточки → проверка полноты/наличия/района → резюме + вопрос approve.
# НЕ пишет в CRM и НЕ шлёт задачи тайцам (это этап B). Язык — RU.

def _intake_is_card(text) -> bool:
    return bool(text) and text.lstrip().startswith("🆕 БРОНЬ")


def _intake_parse(claude, text) -> dict:
    return _parse_json(claude.quick(INTAKE_SYSTEM, text, max_tokens=500, model="MAIN",
                              tag="intake", expect_json=True)) or {}


def _deposit_for_model(model):
    """Стандартный денежный депозит (฿) по модели или None. Для показа в резюме (этап A)."""
    m = (model or "").lower()
    for keys, amount in _DEPOSIT_BY_MODEL:
        if any(k in m for k in keys):
            return amount
    return None


def _delivery_phuket_status(name, url) -> str:
    """'ok' | 'out' | 'unknown' — район доставки. Короткая Maps-ссылка без адреса → unknown."""
    blob = ((name or "") + " " + (url or "")).lower()
    if any(k in blob for k in _NON_PHUKET):
        return "out"
    if any(k in blob for k in _PHUKET_HINTS):
        return "ok"
    return "unknown"


def _intake_validate(d) -> list:
    """Чего не хватает в пакете для брони (список меток). Пусто = полный пакет."""
    missing = []
    if not d.get("model"):                              missing.append("модель")
    if not (d.get("date_start") or d.get("date_start_iso")): missing.append("даты/срок")
    if not d.get("contacts"):                           missing.append("контакт")
    if not d.get("delivery_url"):                       missing.append("ссылка Google Maps на доставку")
    if not d.get("helmets"):                            missing.append("кол-во шлемов")
    if not d.get("deposit_type"):                       missing.append("способ депозита")
    if not d.get("passport_photo"):                     missing.append("фото паспорта")
    return missing


import re as _re_pl
_CC_PLATES = {"125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"}


def plateFromName_(text):
    """Номер байка из имени (логика find_bike): последнее число 3+ цифр, НЕ кубатура. None если нет."""
    nums = [n for n in _re_pl.findall(r"\d{3,}", str(text or "").lower()) if n not in _CC_PLATES]
    return nums[-1] if nums else None


def _model_match(model, bike) -> bool:
    if not model or not bike:
        return False
    p = plateFromName_(model)
    if p:
        return plateFromName_(bike) == p
    tokens = [w for w in str(model).lower().split() if len(w) >= 3 and not w.isdigit()]
    bl = str(bike).lower()
    return any(w in bl for w in tokens)


def _intake_availability(bridge, model, date_start_iso, date_end_iso) -> str:
    """READ-ONLY проверка наличия по листу «клиенты». Никогда не блокирует — информирует.
    День-в-день → требует тайцев. Иначе — пересечения по модели на запрошенные даты."""
    from datetime import datetime
    today = None
    if _BKK_TZ:
        try:
            today = datetime.now(_BKK_TZ).date().isoformat()
        except Exception:
            today = None
    if date_start_iso and today and date_start_iso == today:
        return ("день-в-день — НЕ подтверждать автоматически, нужен живой запрос тайцам "
                "в Обслуживание («что есть готовое»)")
    if not date_start_iso or not date_end_iso:
        return "даты не распознаны — проверить наличие вручную"
    try:
        res = bridge.clients(filter="active")
        clients = (res.get("data") or res).get("clients") or res.get("clients") or []
    except Exception as e:
        return f"не смог прочитать CRM ({e}) — проверить вручную"
    conflicts = []
    for c in clients:
        st = str(c.get("status", "")).strip().lower()
        if not (c.get("is_active") or st == "бронь"):
            continue
        if not _model_match(model, c.get("bike", "")):
            continue
        cs = str(c.get("date_start") or "")[:10]
        ce = str(c.get("date_end") or "")[:10]
        if cs and ce and date_start_iso <= ce and date_end_iso >= cs:
            conflicts.append(f"{c.get('name', '?')} ({cs}…{ce}, {st or 'активна'})")
    if conflicts:
        return ("по модели есть пересечения на эти даты: " + "; ".join(conflicts[:3]) +
                ". Уточнить свободный борт / предложить альтернативу (не глухое «нет»).")
    return "пересечений по модели на эти даты в листе «клиенты» не найдено (предварительно свободна)"


def _intake_summary(d, availability, delivery_status) -> str:
    dep = d.get("deposit_type", "")
    if dep == "паспорт":
        dep_line = "паспорт"
    elif dep == "деньги":
        amt = _deposit_for_model(d.get("model"))
        dep_line = f"деньги ≈{amt}฿ (по модели)" if amt else "деньги (сумму уточнить по модели)"
    else:
        dep_line = dep or "не указан"
    url = d.get("delivery_url", "")
    nm = d.get("delivery_name", "") or "—"
    if delivery_status == "out":
        deliv_line = f"{nm} ({url}) ⚠️ ВНЕ Пхукета — не доставляем, нужен САМОВЫВОЗ"
    elif delivery_status == "unknown":
        deliv_line = f"{nm} ({url}) ⚠️ район не определён — проверить вручную"
    else:
        deliv_line = f"{nm} ({url})"
    dates = (str(d.get("date_start", "")) + " — " + str(d.get("date_end", ""))).strip(" —")
    term = f" ({d.get('term')})" if d.get("term") else ""
    return (
        "🐀 Splinter · Карточка принята.\n"
        f"Клиент: {d.get('client', '—')} · контакты: {d.get('contacts', '—')}\n"
        f"Модель: {d.get('model', '—')} · даты {dates or '—'}{term}\n"
        f"Опыт: {d.get('experience', '—')}\n"
        f"Депозит: {dep_line}\n"
        f"Доставка: {deliv_line}\n"
        f"Шлемы: {d.get('helmets', '—')} · паспорт-фото: {'да' if d.get('passport_photo') else 'нет'}\n"
        f"{_intake_passport_line(d)}"
        f"Наличие: {availability}\n"
        "\nСтавлю бронь? да / нет / правки"
    )


def _intake_passport_line(d) -> str:
    """Строка резюме по OCR паспорта (двуязычно RU+TH). Поля ПРЕДВАРИТЕЛЬНЫЕ — «проверьте». Пусто, если фото нет."""
    pp = d.get("passport_ocr")
    if not pp:
        return ""
    if pp.get("ocr_status") == "ok" and pp.get("fields"):
        f = pp["fields"]
        fn = f.get("full_name") or "?"
        co = f.get("country") or "?"
        ex = f.get("expire_date") or "?"
        return f"Паспорт распознал (проверьте): {fn}, {co}, до {ex}\n"
    return "⚠️ Паспорт НЕ распознан — проверьте фото\n"


async def _intake_finalize(draft, msg, context, bridge):
    """Ре-валидация пакета → если неполный, сказать чего не хватает; если полный — резюме+approve."""
    chat_id = msg.chat_id
    tid = getattr(msg, "message_thread_id", None)
    missing = _intake_validate(draft)
    if missing:
        draft["status"] = "incomplete"
        await _send(context, chat_id=chat_id,
                    text="🐀 Splinter\n⚠️ Для брони не хватает: " + ", ".join(missing) +
                         ".\nДополните — продолжу.", bilingual=False, message_thread_id=tid)
        return
    deliv = _delivery_phuket_status(draft.get("delivery_name"), draft.get("delivery_url"))
    avail = _intake_availability(bridge, draft.get("model"),
                                 draft.get("date_start_iso"), draft.get("date_end_iso"))
    draft["status"] = "awaiting_approval"
    await _send(context, chat_id=chat_id, text=_intake_summary(draft, avail, deliv),
                bilingual=False, message_thread_id=tid)


async def _intake_passport_ocr(photo_msg, chat_id, context, bridge):
    """B2: скачать фото паспорта → Drive (папка «Паспорта») → EdenAI OCR. Результат в _INTAKE_PASSPORT.
    Каждый красный вызов (upload/ocr) — через токен-замок 4.2. Возврат (ok_ocr, fields|None)."""
    raw = await _download_photo(photo_msg)
    if not raw:
        return (False, None)
    b64 = base64.b64encode(raw).decode()
    # 1) залить в Drive (4.2)
    try:
        with bridge_client.agent_write((bridge.issue_write_ticket() or {}).get("ticket")):
            up = bridge.upload_passport_photo(b64, filename="passport")
    except Exception as e:
        up = {"ok": False, "error": "exception", "message": str(e)}
    file_id = up.get("file_id") if up.get("ok") else None
    # 2) OCR (4.2)
    fields, ocr_status = None, "failed"
    if file_id:
        try:
            with bridge_client.agent_write((bridge.issue_write_ticket() or {}).get("ticket")):
                ocr = bridge.ocr_passport(file_id=file_id)
        except Exception as e:
            ocr = {"ok": False, "error": "exception", "message": str(e)}
        if ocr.get("ok"):
            fields, ocr_status = ocr.get("fields"), "ok"
        else:
            log.info(f"  🆕 INTAKE: OCR паспорта не удался: {ocr.get('error')}")
    else:
        log.info(f"  🆕 INTAKE: загрузка фото паспорта в Drive не удалась: {up.get('error')}")
    _INTAKE_PASSPORT[chat_id] = {"file_id": file_id, "fields": fields,
                                 "ocr_status": ocr_status, "ts": _time.time()}
    return (ocr_status == "ok", fields)


def _intake_passport_save(chat_id, draft, bridge):
    """B2: сохранить распознанный паспорт в лист «паспорта» (booking_key=model|client|date_start). 4.2."""
    pp = _INTAKE_PASSPORT.get(chat_id)
    if not pp or not pp.get("file_id"):
        return
    key = f"{draft.get('model','')}|{draft.get('client','')}|{draft.get('date_start','')}"
    f = pp.get("fields") or {}
    try:
        with bridge_client.agent_write((bridge.issue_write_ticket() or {}).get("ticket")):
            bridge.save_passport(booking_key=key, bike=draft.get("model"), name=draft.get("client"),
                                 date_start=draft.get("date_start"), drive_file_id=pp.get("file_id"),
                                 ocr_status=pp.get("ocr_status"), **f)
    except Exception as e:
        log.warning(f"  🆕 INTAKE: save_passport не прошёл: {e}")


async def _handle_intake(msg, context, bridge, claude, photo_msgs=None):
    """Приём карточек брони (этап A): карточка → пакет/наличие → резюме+approve. CRM read-only.
    photo_msgs — пачка фото (альбом склеен по media_group_id) → один «паспорт получен» + один finalize."""
    chat_id = msg.chat_id
    text = (msg.text or msg.caption or "").strip()
    if photo_msgs is None:
        photo_msgs = [msg] if msg.photo else []
    has_photo = bool(photo_msgs)
    now = _time.time()

    # 1) Фото паспорта отдельным сообщением → OCR (B2) + связать с карточкой (окно 5 мин, обе стороны)
    if has_photo and not _intake_is_card(text):
        tid_ = getattr(msg, "message_thread_id", None)
        ok_ocr, _fields = await _intake_passport_ocr(photo_msgs[0], chat_id, context, bridge)
        d = _INTAKE_DRAFTS.get(chat_id)
        if d and now - d.get("ts", 0) <= 300:
            d["passport_photo"] = True
            d["passport_ocr"] = _INTAKE_PASSPORT.get(chat_id)
            _intake_passport_save(chat_id, d, bridge)
            await _intake_finalize(d, msg, context, bridge)   # резюме покажет распознан/нет + полноту пакета
        else:
            # фото пришло ДО карточки — подтвердим, привяжем когда придёт карточка
            ack = ("🐀 Splinter\n📎 Паспорт получен и распознан — привяжу к карточке."
                   if ok_ocr else
                   "🐀 Splinter\n📎 Паспорт получен, но не распознался — пришлите карточку/перефото.")
            await _send(context, chat_id=chat_id, text=ack, bilingual=False, message_thread_id=tid_)
        return

    # 1b) Команда «договор [booking_key | Имя дата]» (B3, по команде, только аппруверы; НЕ авто-на-approve).
    #     Без аргументов → берёт последнюю бронь чата (model|client|date_start) — удобно reply'ем после карточки.
    low0 = text.lower()
    if (low0.startswith("договор") or low0.startswith("contract")) and _intake_can_approve(msg):
        tid = getattr(msg, "message_thread_id", None)
        sp = text.split(None, 1)
        args = sp[1].strip() if len(sp) > 1 else ""
        bk = nm = ds = None
        if "|" in args:
            bk = args
        elif args:
            toks = args.rsplit(None, 1)
            if len(toks) == 2:
                nm, ds = toks[0].strip(), toks[1].strip()
            else:
                nm = args
        else:
            d2 = _INTAKE_DRAFTS.get(chat_id)
            if d2 and d2.get("model") and d2.get("client") and d2.get("date_start"):
                bk = f"{d2['model']}|{d2['client']}|{d2['date_start']}"
        if not bk and not (nm and ds):
            await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                        text=("🐀 Splinter\nУкажи бронь: «договор <booking_key>» или «договор <Имя> <дата>», "
                              "либо отправь после карточки брони."))
            return
        try:
            with bridge_client.agent_write((bridge.issue_write_ticket() or {}).get("ticket")):
                res = bridge.make_contract(booking_key=bk, name=nm, date_start=ds)
        except Exception as e:
            res = {"ok": False, "error": "exception", "message": str(e)}
        if res.get("ok"):
            log.info(f"  🆕 INTAKE: договор готов {res.get('name')} → {res.get('url')}")
            reminder = ""
            if (res.get("flags") or {}).get("km_request"):
                reminder += "⚠️ Пробег под запрос — впиши вручную.\n"
            reminder += "Проверь перед печатью: топливо, время выдачи, пробег."
            await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                        text=f"🐀 Splinter\n✅ Договор готов: {res.get('url')}\n{reminder}")
        else:
            await _send(context, chat_id=chat_id, message_thread_id=tid, bilingual=False,
                        text=f"🐀 Splinter\n❌ Договор не сделан: {res.get('error')}. {res.get('message','')}")
        return

    # 2) Карточка брони
    if _intake_is_card(text):
        parsed = _intake_parse(claude, text)
        draft = dict(parsed)
        draft.update(ts=now, passport_photo=False, status="new")
        # B2: паспорт мог прийти ДО карточки (буфер свежий <5 мин) — привязать + сохранить в лист «паспорта»
        pp = _INTAKE_PASSPORT.get(chat_id)
        if pp and now - pp.get("ts", 0) <= 300:
            draft["passport_photo"] = True
            draft["passport_ocr"] = pp
        _INTAKE_DRAFTS[chat_id] = draft
        if pp and now - pp.get("ts", 0) <= 300:
            _intake_passport_save(chat_id, draft, bridge)
        log.info(f"  🆕 INTAKE: карточка — модель={draft.get('model')} клиент={draft.get('client')}")
        await _intake_finalize(draft, msg, context, bridge)
        return

    # 3) approve / нет / правки — только от авторизатора и только по карточке в ожидании
    d = _INTAKE_DRAFTS.get(chat_id)
    if d and d.get("status") == "awaiting_approval" and _intake_can_approve(msg):
        low = text.lower()
        tid = getattr(msg, "message_thread_id", None)
        if any(w in low for w in ("да", "ок", "ставь", "подтвержд")):
            d["status"] = "approved"
            _who = msg.from_user.username if msg.from_user else "?"
            # --- собрать поля брони из распарсенной карточки ---
            dep_type = d.get("deposit_type")
            if dep_type == "паспорт":
                deposit = "passport"
            elif dep_type == "деньги":
                deposit = _deposit_for_model(d.get("model"))   # сумма по модели (число) или None
            else:
                deposit = None
            note_bits = []
            if d.get("experience"):    note_bits.append("опыт: " + str(d["experience"]))
            if d.get("delivery_name"): note_bits.append("доставка: " + str(d["delivery_name"]))
            if d.get("term"):          note_bits.append("срок: " + str(d["term"]))
            booking_fields = dict(
                bike=d.get("model"), name=(d.get("client") or "—"),
                date_start=d.get("date_start"), date_end=d.get("date_end"),
                deposit=deposit, helmets=d.get("helmets"),
                contacts=d.get("contacts"), note=(" | ".join(note_bits) or None),
            )
            # --- КРАСНАЯ запись в CRM через токен-замок 4.2 (issue ticket → agent_write → create_booking) ---
            try:
                ticket = (bridge.issue_write_ticket() or {}).get("ticket")
                with bridge_client.agent_write(ticket):
                    res = bridge.create_booking(**booking_fields)
            except Exception as e:
                res = {"ok": False, "error": "exception", "message": str(e)}
            if res.get("ok"):
                d["status"] = "booked"
                _row = res.get("row")
                # O3-3c часть Б: intake-окно 30 мин — deposit-приход в Money по этому байку
                # привяжется к свежесозданной брони без чтения CRM (приоритет над резолвом).
                _bid = res.get("booking_id")
                _pl = plateFromName_(res.get("bike") or d.get("model") or "")
                if _bid and _pl:
                    _RECENT_BOOKINGS[_pl] = {"booking_id": str(_bid), "row": _row, "ts": now}
                log.info(f"  🆕 INTAKE: бронь записана (строка {_row}, @{_who}) {d.get('model')}")
                await _send(context, chat_id=chat_id,
                            text=f"🐀 Splinter\n✅ Бронь записана, строка {_row}, статус «Бронь».",
                            bilingual=False, message_thread_id=tid)
            elif res.get("error") == "duplicate":
                _row = res.get("row")
                await _send(context, chat_id=chat_id,
                            text=f"🐀 Splinter\n⚠️ Уже есть такая бронь (строка {_row}).",
                            bilingual=False, message_thread_id=tid)
            else:
                _err = res.get("error") or "?"
                _emsg = res.get("message") or ""
                log.warning(f"  🆕 INTAKE: бронь НЕ записана ({_err}: {_emsg}) {d.get('model')}")
                await _send(context, chat_id=chat_id,
                            text=f"🐀 Splinter\n❌ Не записалось: {_err}. {_emsg}",
                            bilingual=False, message_thread_id=tid)
        elif any(w in low for w in ("нет", "отмена", "не ставь", "отклон")):
            d["status"] = "rejected"
            await _send(context, chat_id=chat_id, text="🐀 Splinter\n❌ Бронь отклонена.",
                        bilingual=False, message_thread_id=tid)
        elif "правк" in low or "исправ" in low:
            await _send(context, chat_id=chat_id,
                        text="🐀 Splinter\n✏️ Принял, жду исправленную карточку.", bilingual=False, message_thread_id=tid)
        return

    # 4) O3-3a: подтверждение активации выдачи (Бронь→В аренде) — ТОЛЬКО авторизаторы
    #    (INTAKE_APPROVERS; Пым/тайцы не авторизуют), ТОЛЬКО пока запрос свежий (TTL).
    #    Ветка ПОСЛЕ intake-draft (та выше возвращается сама — приоритет брони не сломан).
    act = _HANDOVER_ACTIVATIONS.get(chat_id)
    if (act and act.get("status") == "awaiting" and _intake_can_approve(msg)
            and now - act.get("ts", 0) <= _HO_ACT_TTL):
        low = text.lower()
        tid = getattr(msg, "message_thread_id", None)
        if any(w in low for w in ("да", "ок", "активируй", "подтвержд")):
            _who = msg.from_user.username if msg.from_user else "?"
            # --- КРАСНАЯ запись в CRM через токен-замок 4.2 (issue ticket → agent_write) ---
            try:
                ticket = (bridge.issue_write_ticket() or {}).get("ticket")
                with bridge_client.agent_write(ticket):
                    res = bridge.activate_booking(bike=act["bike"], name=act["name"],
                                                  date_start=(act.get("date_start") or None))
            except Exception as e:
                res = {"ok": False, "error": "exception", "message": str(e)}
            if res.get("ok"):
                act["status"] = "activated"
                _row = res.get("row") or act.get("row")
                log.info(f"  → ВЫДАЧА: бронь активирована (строка {_row}, @{_who}) {act['bike']}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text=f"🐀 Splinter\n✅ В аренде, строка {_row}.")
            else:
                act["status"] = "error"
                _err = res.get("error") or "?"
                _emsg = res.get("message") or ""
                log.warning(f"  → ВЫДАЧА: активация НЕ прошла ({_err}: {_emsg}) {act['bike']}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text=f"🐀 Splinter\n❌ Активация не прошла: {_err}. {_emsg}\n"
                                 f"Статус в CRM не менял — переведи руками.")
            return
        if any(w in low for w in ("нет", "отмена", "не актив", "отклон")):
            act["status"] = "rejected"
            await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                        text="🐀 Splinter\n❌ Активацию отменил — статус в CRM не менял.")
            return

    # 5) O3-3b фаза II: подтверждение ПРИЁМА (В аренде→Завершена) — ТОЛЬКО авторизаторы, TTL.
    #    Ветка ПОСЛЕДНЯЯ: приоритет «да» = карточка брони (3) → активация выдачи (4) → закрытие (5);
    #    ветки выше возвращаются сами на своём матче — «да» между тремя карточками не путается.
    ret = _RETURN_CLOSES.get(chat_id)
    if (ret and ret.get("status") == "awaiting" and _intake_can_approve(msg)
            and now - ret.get("ts", 0) <= _RET_CLOSE_TTL):
        low = text.lower()
        tid = getattr(msg, "message_thread_id", None)
        # отказ проверяем ПЕРВЫМ: «не завершай»/«не закрывай» содержат yes-слово «заверш»/«закрывай» —
        # порядок yes-первым закрыл бы аренду на явном отказе
        if any(w in low for w in ("нет", "отмена", "не заверш", "не закрыв", "отклон")):
            ret["status"] = "rejected"
            await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                        text="🐀 Splinter\n❌ Закрытие отменил — статус в CRM не менял.")
            return
        if any(w in low for w in ("да", "ок", "заверш", "закрывай", "подтвержд")):
            _who = msg.from_user.username if msg.from_user else "?"
            # цифра в ответе авторизатора = правка/добор пробега на сдаче («да 35200» — перекрывает контекст)
            _m = _re_lang.search(r"\d{2,7}", text.replace(" ", ""))
            _km = (_m.group(0) if _m else "") or ret.get("km") or None
            # --- КРАСНАЯ запись в CRM через токен-замок 4.2 (issue ticket → agent_write) ---
            try:
                ticket = (bridge.issue_write_ticket() or {}).get("ticket")
                with bridge_client.agent_write(ticket):
                    res = bridge.close_booking(bike=ret["bike"], name=ret["name"],
                                               date_start=(ret.get("date_start") or None),
                                               km_end=_km, paid_total=ret.get("paid_total"))
            except Exception as e:
                res = {"ok": False, "error": "exception", "message": str(e)}
            if res.get("ok"):
                ret["status"] = "closed"
                _row = res.get("row") or ret.get("row")
                log.info(f"  → ПРИЁМ: аренда завершена (строка {_row}, @{_who}) {ret['bike']} "
                         f"km_end={_km or '-'} paid={ret.get('paid_total') if ret.get('paid_total') is not None else '-'}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text=f"🐀 Splinter\n✅ Завершена, строка {_row}.")
            elif res.get("error") == "unknown_action":
                # Bridge ещё без деплоя фазы I (конверт close_booking ждёт деплоя владельцем) — карточку
                # НЕ гасим: статус остаётся awaiting, после деплоя то же «да» закроет аренду штатно.
                log.warning(f"  → ПРИЁМ: Bridge без close_booking (unknown_action) {ret['bike']} — жду деплоя")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text="🐀 Splinter\n⏳ Закрытие аренды (closeBooking) ещё не задеплоено на Bridge — "
                                 "требуется решение владельца (деплой Bridge); карточка останется, "
                                 "после деплоя снова «да».")
            elif res.get("error") == "km_required":
                # fail-closed (инцидент row705): Bridge без пробега на сдаче аренду НЕ закрывает.
                # Карточку НЕ гасим — «да <цифра пробега>» тем же запросом добьёт закрытие.
                log.warning(f"  → ПРИЁМ: закрытие без пробега отклонено (km_required) {ret['bike']}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text="🐀 Splinter\n❌ Закрыть не могу: нет пробега на сдаче — без него аренду "
                                 "не закрываем. Ответь «да <цифра пробега>» — или заверши руками "
                                 "(В аренде→Завершена). Статус в CRM не менял.")
            elif res.get("error") == "odo_unverifiable":
                # fail-closed (инцидент row705): одометр строки (Q) пуст/нечисловой — чек
                # «одометр не уменьшается» провести нельзя, автозакрытие запрещено.
                ret["status"] = "error"
                log.warning(f"  → ПРИЁМ: одометр строки не сверить (odo_unverifiable) {ret['bike']}: "
                            f"{res.get('message') or ''}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text=f"🐀 Splinter\n❌ Закрыть не могу: одометр строки в CRM пуст/не читается — "
                                 f"сверить пробег автоматически нельзя. Сверь и заверши руками "
                                 f"(В аренде→Завершена, строка {res.get('row') or ret.get('row') or '?'}). "
                                 f"Статус в CRM не менял.")
            else:
                ret["status"] = "error"
                _err = res.get("error") or "?"
                _emsg = res.get("message") or ""
                log.warning(f"  → ПРИЁМ: закрытие НЕ прошло ({_err}: {_emsg}) {ret['bike']}")
                await _send(context, chat_id=chat_id, bilingual=False, message_thread_id=tid,
                            text=f"🐀 Splinter\n❌ Закрытие не прошло: {_err}. {_emsg}\n"
                                 f"Статус в CRM не менял — заверши руками.")
            return


async def _handle_delivery(msg, context, bridge, claude):
    """Delivery cooperation — фиксируем ход доставок (пока просто лог)."""
    text = msg.text or msg.caption or ""
    if not text.strip():
        return
    chat_id = msg.chat_id
    group_name = group_label(chat_id)
    bridge.add_event(
        msg_date=str(msg.date.date()) if msg.date else "",
        group=group_name, bike="", event_type="delivery",
        fuel="", mileage="", photos=1 if msg.photo else 0,
        notes=text[:200],
        msg_id=f"{chat_id}:{msg.message_id}",
    )


async def _handle_attendance(msg, context, bridge, claude):
    """Отметка сотрудников — фиксируем приход, флагаем опоздание (>10:00)."""
    if not msg.date:
        return
    chat_id = msg.chat_id
    group_name = group_label(chat_id)
    local_hour = msg.date.hour  # UTC; уточним TZ при необходимости
    note = msg.text or "(отметка)"
    bridge.add_event(
        msg_date=str(msg.date.date()),
        group=group_name, bike="", event_type="attendance",
        fuel="", mileage="", photos=0,
        notes=f"{note[:150]} | t={msg.date.strftime('%H:%M')} UTC",
        msg_id=f"{chat_id}:{msg.message_id}",
    )


# ============================================================
#  ГЛАВНАЯ ТОЧКА ВХОДА
# ============================================================

def is_splinter_group(chat_id: int) -> bool:
    return chat_id in GROUPS


async def _reply_floor_speak(context, msg, crashed=False, spoke_before=0):
    """Заход отработал и не сказал НИ СЛОВА → сказать. Молчание запрещено как исход (23.08).

    Что именно сказать, решает `reply_floor.fallback`; здесь только руки. Ответ уходит В ТУ ЖЕ
    тему, откуда пришло сообщение, — иначе «бот ответил» было бы правдой не для того человека.
    Сам пол молчит РОВНО в двух случаях: ручка выключена и мы уже говорили; всё прочее — речь."""
    if not _never_silent_on():
        return False
    if _SPOKE.get() != spoke_before:
        return False                      # уже сказали — второе слово было бы шумом
    topic_id = getattr(msg, "message_thread_id", None)
    try:
        bike = _topic_name_from_msg(msg) or ""
    except Exception:
        bike = ""
    say = reply_floor.fallback({
        "bike": bike,
        "crashed": bool(crashed),
        "photo": bool(getattr(msg, "photo", None)),
    })
    log.info(f"  → ПОЛ ОТВЕТА: заход промолчал (исход {say['state']}, упал={bool(crashed)}) "
             f"— отвечаю сам, тема={topic_id}")
    try:
        await _send_retry(context, chat_id=msg.chat_id, message_thread_id=topic_id,
                          text=f"🐀 Splinter\n🇹🇭 {say['th']}\n🇷🇺 {say['ru']}")
        return True
    except Exception:
        # Пол не имеет права стать новой причиной падения: он последний в цепи.
        log.exception("  → ПОЛ ОТВЕТА: не смог отправить ответ (fail-safe)")
        return False


async def handle(update, context, bridge, claude, album_msgs=None):
    """Вызывается из bot.py для сообщений из операционных групп.
    album_msgs — список сообщений-фото альбома (склейка по media_group_id); для одиночного
    фото/текста = None (тогда берём photo из самого msg). Обработка альбома = ОДИН прогон."""
    msg = update.message
    if not msg:
        return
    mode = GROUPS.get(msg.chat_id)
    if not mode:
        return
    # Пачка фото: альбом (album_msgs) ИЛИ одиночное фото ([msg]) ИЛИ нет фото ([]).
    photo_msgs = album_msgs if album_msgs else ([msg] if msg.photo else [])

    # Диагностический лог — видно что сообщение долетело до Splinter
    _u = msg.from_user.username if msg.from_user else "?"
    _t = (msg.text or msg.caption or ("[фото]" if msg.photo else "")) or ""
    log.info(f"Splinter [{mode}] {msg.chat_id} @{_u}: {_t[:80]}")

    # Индикатор «печатает» — показываем что бот принял сообщение в работу
    try:
        _k = {"chat_id": msg.chat_id, "action": "typing"}
        _tt = getattr(msg, "message_thread_id", None)
        if _tt:
            _k["message_thread_id"] = _tt
        await context.bot.send_chat_action(**_k)
    except Exception:
        pass

    # ПОЛ ОТВЕТА (правило владельца 23.08 «никогда не молчать»). Снимок свидетеля ДО разбора;
    # после разбора он либо вырос (мы говорили), либо нет — и тогда говорим сами.
    _spoke_before = _SPOKE.get()
    _crashed = False
    try:
        if mode == "money":
            await _handle_money(msg, context, bridge, claude)
        elif mode == "servicing":
            await _handle_servicing(msg, context, bridge, claude, photo_msgs)
        elif mode == "delivery":
            await _handle_delivery(msg, context, bridge, claude)
        elif mode == "attendance":
            await _handle_attendance(msg, context, bridge, claude)
        elif mode == "intake":
            await _handle_intake(msg, context, bridge, claude, photo_msgs)
    except Exception:
        _crashed = True
        log.exception(f"Splinter error in {mode} ({msg.chat_id})")
    # ОБЛАСТЬ УЖЕ (и это прямой запрет задания): пол стоит ТОЛЬКО на темах байков внутреннего
    # контура. Клиентский контур (`intake`) не трогается ни одним словом — там разговор ведёт
    # менеджер, и лишняя реплика бота видна клиенту.
    if mode == "servicing":
        await _reply_floor_speak(context, msg, crashed=_crashed, spoke_before=_spoke_before)
