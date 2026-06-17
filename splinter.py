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

import json
import logging
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


async def _send(context, *, chat_id, text, message_thread_id=None, bilingual=True, group="", reply_markup=None):
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
    return await context.bot.send_message(**kw)


# === Кто такой Пым (главный по деньгам) ===
PYM_USERNAMES = {"pleummmm"}  # lower-case, без @

# === Аккаунты владельца (Филипп пишет из них) — тоже доверенные ===
OWNER_USERNAMES = {"turbophuket", "turbophuket1"}

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
# В HQ (-1003853365891) тема 205 «Обучение юзербота»: там сидит pc_agent (управление userbot).
# Команды старт/стоп/статус userbot адресованы агенту, не Splinter. Splinter туда не лезет:
# не отвечает, мозг не запускает, учёт/аудитор в этой теме НЕ работают — это не опергруппа.
HQ_CHAT_ID = -1003853365891
IGNORED_THREADS = {205}


def is_ignored_thread(chat_id, topic_id) -> bool:
    """True → Splinter полностью молчит в этой теме (чужой контур userbot/агента в HQ).
    Проверять РАНО, до мозга/учёта/аудитора/любой реакции."""
    return chat_id == HQ_CHAT_ID and topic_id in IGNORED_THREADS


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
from collections import deque
_RECENT_PHOTOS = {}
_RECENT_LIMIT = 12          # сколько последних фото помнить на группу
_RECENT_TTL = 3 * 3600      # 3 часа — потом считаем устаревшим

# Отложенные ИНФО-работы (колодки/цепь/масл.фильтр/вилка/прочее) — техник назвал работы ТЕКСТОМ
# без пробега; пишем их в историю «события» строкой-на-работу, КОГДА в теме придёт чёткий пробег
# (фото/число). {(chat_id, topic_id): {"works":[...], "bike":str, "msg_id_base":str, "ts":float}}
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
        acc = {"current_km": "", "works": [], "works_km": "", "oil": None, "cols": []}
        _SVC_SUMMARY[(chat_id, topic_id)] = acc
    acc["ts"] = _time.time()
    return acc


async def _emit_summary(context, chat_id, topic_id, bike, skip_oil=False):
    """ТЕРМИНАЛ цикла → собрать ОДНУ сводку из накопителя, отправить, накопитель очистить.
    skip_oil=True (overdue [Просто пробег]) — масло уже в закрепе, в сводке его не дублируем;
    тогда шлём сводку ТОЛЬКО если есть работы/столбцы. Возвращает отправленный Message (для закрепа
    итога) ИЛИ None если ничего не отправили."""
    acc = _SVC_SUMMARY.pop((chat_id, topic_id), None)
    if not acc:
        return None
    has = bool(acc.get("works") or acc.get("cols") or (acc.get("oil") and not skip_oil))
    if not has:
        return None
    return await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                       text=msg_service_summary(bike, acc, skip_oil=skip_oil))


# Анти-спам для просьбы «пришли чёткое фото одометра» (масло без читаемого пробега):
# не повторять чаще раза в 10 мин на тему. {(chat_id, topic_id): ts}. Волатильный — ок для троттлинга.
_ODOMETER_ASK_TS = {}
_ODOMETER_ASK_COOLDOWN = 600   # сек

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
    newest_any = None   # (km, conf) — самый свежий любой
    newest_high = None  # (km, conf) — самый свежий high
    for it in reversed(buf):   # с конца — самый свежий
        if now - it["ts"] > _RECENT_TTL:
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


def _is_owner(msg) -> bool:
    u = msg.from_user
    if not u or not u.username:
        return False
    return u.username.lower() in OWNER_USERNAMES


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


def _balance_block(label, bal):
    """Баланс столбиком: строка-метка «<label>:», затем валюты с отступом 2 пробела."""
    return [f"{label}:", *[f"  {p}" for p in _balance_parts(bal)]]


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


def msg_recorded_each(amount, bal, currency: str = "THB", wallet: str = "Самоорганизация"):
    """Касса (Самоорганизация): подтверждение каждой записи."""
    rec = _recorded_unit(amount, currency)
    return _bilingual(
        wallet,
        [f"บันทึกแล้ว  {rec}", *_balance_block("ยอดคงเหลือ", bal)],
        [f"Учтено  {rec}", *_balance_block("Баланс", bal)],
    )


def msg_recorded_cf(amount, bal, currency: str = "THB", wallet: str = "Money Cashflow"):
    """Money Cashflow: подтверждение записи."""
    rec = _recorded_unit(amount, currency)
    return _bilingual(
        wallet,
        [f"บันทึกแล้ว  {rec}", *_balance_block("ยอดคงเหลือ", bal)],
        [f"Записал  {rec}", *_balance_block("Баланс", bal)],
    )


def msg_topup_pettycash(amount, bal, wallet: str = "Самоорганизация", source: str = "Money Cashflow"):
    """Пополнение кассы переносом из другого кошелька (в группе Самоорганизации)."""
    a = _fmt(abs(amount or 0))
    return _bilingual(
        wallet,
        [f"เติมเงิน  +{a} ฿  (โอนมาจาก {source})", *_balance_block("ยอดคงเหลือ", bal),
         "", "พี่ Pleum ถูกต้องไหมครับ?"],
        [f"Пополнение  +{a} ฿  (перенос из {source})", *_balance_block("Баланс", bal),
         "", "Пым, всё верно?"],
    )


def msg_reconcile(wallet, bal):
    """Периодическая сверка с Пымом — только по текущему кошельку."""
    return _bilingual(
        wallet,
        [*_balance_block("ยอดคงเหลือ", bal), "",
         "@Pleummmm เงินสดในมือตรงกับยอดในระบบไหมครับ? มีรายการตกหล่นไหม? 🙏"],
        [*_balance_block("Баланс", bal), "",
         "@Pleummmm наличные на руках сходятся с балансом? Ничего не упустили? 🙏"],
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
        [f"ยกเลิกรายการล่าสุดแล้ว:  {sign}{a} ฿", *_balance_block("ยอดคงเหลือ", bal)],
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
        f"🇹🇭 พี่ Pleum ผมอาจตกหล่นรายการบางอย่าง ช่วยตรวจสอบหน่อยครับ 🙏\n"
        f"🇷🇺 Пым, возможно я пропустил запись — глянь 🙏"
    )


def msg_expense_high(category, amount, avg):
    cat_ru = {"fuel": "бензин", "taxi": "такси"}.get(category, category)
    cat_th = {"fuel": "ค่าน้ำมัน", "taxi": "ค่าแท็กซี่"}.get(category, category)
    return (
        f"🐀 Splinter\n"
        f"⛽ {cat_th}วันนี้ {_fmt(amount)} ฿  (ปกติ ~{_fmt(avg)} ฿)\n"
        f"⛽ {cat_ru.capitalize()} сегодня {_fmt(amount)} ฿  (обычно ~{_fmt(avg)} ฿)\n"
        f"\n"
        f"🇹🇭 พี่ Pleum ปกติไหมครับ?\n"
        f"🇷🇺 Пым, всё ок или разберём?"
    )


def msg_photo_reminder(bike):
    b = f" {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"📸 รถคันนี้{b} ขาดรูปน้ำมันและเลขไมล์\n"
        f"📸 По байку{b} не хватает фото топлива и пробега\n"
        f"\n"
        f"🇹🇭 รบกวนทีมส่งรูปด้วยครับ @Pleummmm ช่วยดูหน่อยนะครับ 🙏\n"
        f"🇷🇺 Команда, пришлите фото. @Pleummmm проконтролируй 🙏"
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


def msg_ask_odometer(bike):
    """Просьба прислать ЧЁТКОЕ фото одометра при замене масла без читаемого пробега.
    Двуязычно RU/TH (TH первым), БЕЗ тега Пыма. Ничего в ТО не пишем — только просьба."""
    b = f" {bike}" if bike else ""
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 เห็นว่ากำลังเปลี่ยนน้ำมัน{b} — รบกวนถ่ายรูปเลขไมล์ (ODO) ให้ชัด ๆ หน่อยครับ เพื่อบันทึกการเปลี่ยนถ่าย 🙏\n"
        f"🇷🇺 Вижу замену масла{b} — пришлите, пожалуйста, ЧЁТКОЕ фото пробега (одометр, ODO), чтобы зафиксировать замену 🙏"
    )


def msg_work_receipt(bike, works):
    """Квитанция на ЭТАПЕ ТЕКСТА: работы ПРИНЯТЫ (ещё в буфере, НЕ записаны) — просим пробег.
    Факт записи подтверждается ОТДЕЛЬНО (msg_works_logged) ПОСЛЕ прихода пробега, чтобы не
    выглядело «записал», когда записи ещё нет. Список работ по-русски → только в 🇷🇺-строке."""
    b = f" {bike}" if bike else ""
    works_str = ", ".join(dict.fromkeys(str(w).strip() for w in works if str(w).strip()))
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 รับงานแล้วครับ{b} — รบกวนส่งเลขไมล์ด้วยครับ 🙏\n"
        f"🇷🇺 Принял работы{b}: {works_str} — пришли пробег 🙏"
    )


def msg_works_logged(bike, km, works):
    """Пост-квитанция ПО ФАКТУ записи инфо-работ в историю (после flush/записи с км).
    Список работ по-русски → ТОЛЬКО в 🇷🇺-строке (🇹🇭 без кириллицы; km — цифры, bike — латиница)."""
    b = f" {bike}" if bike else ""
    works_str = ", ".join(dict.fromkeys(str(w).strip() for w in works if str(w).strip()))
    return (
        f"🐀 Splinter\n"
        f"🇹🇭 ✅ บันทึกงานลงประวัติที่เลขไมล์ {km} กม. แล้วครับ{b} 🛠️\n"
        f"🇷🇺 ✅ Записал работы на пробеге {km} км{b}: {works_str} 🛠️"
    )


# Словарь русских названий работ → тайские (для пословного списка в 🇹🇭-блоке, без кириллицы).
# Стартовый набор согласован с Филиппом; пополняется. Неизвестная работа → 'งานอื่น ๆ' (прочее).
_WORK_TH = {
    # ТОЧНЫЕ/частые формы (в т.ч. склонённые — works приходят из parse в разных падежах)
    "замена моторного масла": "เปลี่ยนน้ำมันเครื่อง", "моторное масло": "เปลี่ยนน้ำมันเครื่อง",
    "масляный фильтр": "ไส้กรองน้ำมันเครื่อง", "масляного фильтр": "ไส้กรองน้ำมันเครื่อง",
    "воздушный фильтр": "ไส้กรองอากาศ", "воздушного фильтр": "ไส้กรองอากาศ",
    "задние тормозные колодки": "ผ้าเบรกหลัง", "задних тормозных колодок": "ผ้าเบรกหลัง",
    "передние тормозные колодки": "ผ้าเบรกหน้า", "передних тормозных колодок": "ผ้าเบรกหน้า",
    "регулировка цепи": "ปรับโซ่", "замена цепи": "เปลี่ยนโซ่",
    "тормозная жидкость": "น้ำมันเบรก", "масло редуктора": "น้ำมันเกียร์",
    # СТЕМЫ (ловят любые склонения; проверяются ПОСЛЕ длинных ключей → не перебивают точные)
    "воздушн": "ไส้กรองอากาศ", "колодк": "ผ้าเบรก", "цеп": "โซ่", "фильтр": "ไส้กรองน้ำมันเครื่อง",
    "свеч": "หัวเทียน", "аккумулятор": "แบตเตอรี่", "редуктор": "น้ำมันเกียร์",
    "ремень": "สายพาน", "вариатор": "ชุดสายพาน", "шин": "ยาง", "покрышк": "ยาง", "abs": "น้ำมัน ABS",
}


def _work_th(w):
    """Тайское название работы по словарю (точное → частичное вхождение стема); неизвестная → 'งานอื่น ๆ'.
    Длинные ключи раньше: точные формы перебивают стемы (воздушн фильтр → air, иначе фильтр→oil)."""
    s = str(w).strip().lower()
    if s in _WORK_TH:
        return _WORK_TH[s]
    for k in sorted(_WORK_TH, key=len, reverse=True):
        if k in s:
            return _WORK_TH[k]
    return "งานอื่น ๆ"


def msg_service_summary(bike, acc, skip_oil=False):
    """ЕДИНАЯ сводка в конце ТО-цикла: столбцы (масло/gear/abs/возд.фильтр) + история + пробег.
    Работы — ПО ПУНКТАМ (буллет « — »), в ОБОИХ блоках: 🇹🇭 тайские названия (_WORK_TH), 🇷🇺 русские.
    🇹🇭 ЧИСТЫЙ тайский (метки столбцов из _SVC_COL_LABEL). Секции без данных опускаем. Cyrillic в 🇹🇭 НЕТ."""
    km = acc.get("current_km") or acc.get("works_km") or (acc.get("oil") or {}).get("km") or ""
    head = f"🐀 Splinter · 📌 {bike}" if bike else "🐀 Splinter"
    th = [f"🇹🇭 ✅ บันทึกครบแล้วครับ" + (f" — เลขไมล์ปัจจุบัน {km} กม." if km else "")]
    ru = [f"🇷🇺 ✅ Готово" + (f" — текущий пробег {km} км." if km else "")]
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
    return head + "\n" + "\n".join(th) + "\n" + "\n".join(ru)


# ЗАХОД 2: распознавание запроса карточки байка («инфа/статус/что по байку»).
_STATUS_KEYWORDS = ("инф", "статус", "состояни", "что по байк", "что с байк",
                    "как байк", "сводка по", "карточк", "status", "info")


def _is_status_request(text):
    """Короткий свободный запрос статуса/карточки байка (не длинное сообщение о работах)."""
    t = (text or "").strip().lower()
    if not t or len(t) > 60:
        return False
    return any(k in t for k in _STATUS_KEYWORDS)


# Инфо-работа из истории «события»: notes вида «<работа> — <км> км/กม». Отсекает шум (фото-описания,
# напоминания) — для секции «сервис на пробеге» в карточке (ЗАХОД 3).
_SVC_HIST_RE = r"^(.+?)\s*—\s*(\d+)\s*(?:км|กม)"   # _re_pl импортирован ниже — compile в рантайме


def _parse_service_items(items, limit=6):
    """Из read_events отобрать ИНФО-работы «<работа> — <км> км» → [{work, km}], newest-first, до limit."""
    out = []
    for it in items or []:
        m = _re_pl.match(_SVC_HIST_RE, str(it.get("notes") or "").strip(), _re_pl.IGNORECASE)
        if m:
            out.append({"work": m.group(1).strip(), "km": m.group(2)})
        if len(out) >= limit:
            break
    return out


def msg_bike_card(bike, cur_km, oil, cols, rental, service=None):
    """КАРТОЧКА байка по запросу: пробег + ТО Oil + J/K/L + аренда + сервис-на-пробеге (ЗАХОД 3).
    🇹🇭 чистый тайский (метки/статусы/работы тайскими через _work_th), 🇷🇺 русский. Секции без данных опускаем."""
    head = f"🐀 Splinter · 📌 {bike}" if bike else "🐀 Splinter"
    km_th = f" · ไมล์ {cur_km} กม." if cur_km else ""
    km_ru = f" · пробег {cur_km} км" if cur_km else ""
    th = [f"🇹🇭 📋 สถานะรถ{km_th}"]
    ru = [f"🇷🇺 📋 Статус байка{km_ru}"]

    def _oil_lines(o):
        nxt, st = o.get("next"), str(o.get("status") or "")
        if st in ("due", "overdue") and nxt:
            try:
                over = int(o.get("km")) - int(nxt)
            except (ValueError, TypeError):
                over = None
            t = f" เกินกำหนด {over} กม. (ครบ {nxt})" if over and over > 0 else f" ใกล้ครบ (ครบ {nxt})"
            r = f" просрочка {over} км (срок {nxt})" if over and over > 0 else f" скоро срок ({nxt})"
        else:
            t = " ปกติ" + (f" ครบกำหนดถัดไป {nxt} กม." if nxt else "")
            r = " в норме" + (f", следующее {nxt} км" if nxt else "")
        return t, r

    if oil:
        ot, orr = _oil_lines(oil)
        th.append(f"   • เปลี่ยนน้ำมันเครื่อง:{ot}")
        ru.append(f"   • ТО Oil:{orr}")
    for c in cols or []:
        th_lbl, ru_lbl = _SVC_COL_LABEL.get(c.get("kind"), (c.get("kind"), c.get("kind")))
        nxt = c.get("next")
        th.append(f"   • {th_lbl}:" + (f" ครบกำหนด {nxt} กม." if nxt else " บันทึกแล้ว"))
        ru.append(f"   • {ru_lbl}:" + (f" следующее {nxt} км" if nxt else " ведётся"))
    if rental:
        state = str(rental.get("state", ""))
        cl = rental.get("client", "")
        if state.lower().startswith("в аренд"):
            th.append("   • เช่า: ให้เช่าอยู่" + (f" (ลูกค้า {cl})" if cl else ""))
            ru.append("   • аренда: у клиента" + (f" {cl}" if cl else ""))
        elif state.lower() == "дома":
            th.append("   • เช่า: อยู่ที่ออฟฟิศ")
            ru.append("   • аренда: дома (в офисе)")
        elif state:
            th.append(f"   • สถานะ: {state}")
            ru.append(f"   • статус: {state}")
    if service:                       # ЗАХОД 3: сервис-на-пробеге (перечень обслуживаний с км)
        th.append("   🔧 ประวัติซ่อมบำรุง (ตามไมล์):")
        ru.append("   🔧 Сервис на пробеге:")
        for s in service:
            th.append(f"      — {_work_th(s.get('work'))} ({s.get('km')})")
            ru.append(f"      — {s.get('work')} ({s.get('km')})")
    return head + "\n" + "\n".join(th) + "\n" + "\n".join(ru)


async def _send_bike_card(context, bridge, chat_id, topic_id, bike):
    """Собрать карточку байка из ЧИТАЕМЫХ источников (find_bike + service_list) и отправить. Ничего не пишет."""
    fb = bridge.find_bike(bike) or {}
    canon = fb.get("name") or bike
    try:
        recs = [r for r in (bridge.service_list().get("items", []) or []) if _same_bike(r.get("bike"), bike)]
    except Exception:
        recs = []
    oil_rec = next((r for r in recs if str(r.get("service_type")) == "oil"), {})
    cur_km = oil_rec.get("current_km") or ""
    oil = None
    if oil_rec:
        oil = {"km": cur_km, "next": oil_rec.get("next_km"), "status": oil_rec.get("status")}
    elif fb.get("oil_last_km"):
        iv = _service_interval("oil", canon, bridge)
        oil = {"km": cur_km, "next": (int(fb["oil_last_km"]) + iv) if iv else None, "status": None}
    cols = [{"kind": str(r.get("service_type")), "next": r.get("next_km"),
             "status": r.get("status"), "km": r.get("current_km")}
            for r in recs if str(r.get("service_type")) in ("gear", "abs", "airfilter")]
    rental = None
    if fb.get("status"):
        rental = {"state": fb.get("status"), "client": (fb.get("current_rental") or {}).get("client", "")}
    # ЗАХОД 3: сервис-на-пробеге — 6 последних инфо-работ из истории «события» (read_events, фильтр по паттерну).
    service = []
    try:
        ev = bridge.read_events(canon, limit=6)
        service = _parse_service_items(ev.get("items", []), limit=6)
    except Exception:
        log.exception("  → read_events для карточки упал")
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=msg_bike_card(canon, cur_km, oil, cols, rental, service))


def _write_info_works(bridge, group_name, topic_id, bike, info_works, km, msg_id_base, msg_date=""):
    """Вариант A (разбор перечня по адресам): КАЖДУЮ инфо-работу — отдельной строкой в «события»
    с привязкой пробега. msg_id с суффиксом :wN — уникальность строк (дедуп Bridge не схлопывает их
    в одну) и идемпотентность отложенного flush. Колоночные работы сюда НЕ попадают — у них свой адрес."""
    grp = group_name + (f" / тема {topic_id}" if topic_id else "")
    written = []
    for i, w in enumerate(dict.fromkeys(info_works)):
        note = (f"{w} — {km} км" if km else f"{w}")[:200]
        r = bridge.add_event(msg_date=msg_date, group=grp, bike=bike, event_type="repair",
                             fuel="", mileage=str(km or ""), photos=0, notes=note,
                             msg_id=f"{msg_id_base}:w{i}")
        log.info(f"  → инфо-работа в историю: «{note}» add_event ok={(r or {}).get('ok')} "
                 f"saved={(r or {}).get('saved')} dup={(r or {}).get('duplicate')}")
        written.append(w)
    return written   # список фактически записанных работ (для пост-квитанции по факту)


def _flush_pending_works(bridge, chat_id, topic_id, group_name, bike, km, msg_date=""):
    """Пришёл чёткий пробег в теме → дописать ОТЛОЖЕННЫЕ инфо-работы (буфер прошлого сообщения) с этим
    км. pop() = ровно один раз (без задвоения). Протухший (> TTL) буфер не пишем.
    Возвращает СПИСОК записанных работ (для пост-квитанции) или []."""
    pend = _PENDING_WORKS.pop((chat_id, topic_id), None)
    if not pend:
        return []
    if _time.time() - pend.get("ts", 0) > _PENDING_WORKS_TTL:
        log.info(f"  → отложенные инфо-работы протухли (>{_PENDING_WORKS_TTL//3600}ч), не пишу: {pend.get('works')}")
        return []
    return _write_info_works(bridge, group_name, topic_id, bike or pend.get("bike", ""),
                             pend["works"], km, pend["msg_id_base"], msg_date)


# ============================================================
#  ОБРАБОТЧИКИ ПО РЕЖИМАМ
# ============================================================

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

    parsed = _parse_json(claude.quick(MONEY_SYSTEM, text, max_tokens=400))
    ptype = parsed.get("type")
    chat_id = msg.chat_id
    wallet = group_label(chat_id)
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
        cur_bal = bridge.get_balance(group=wallet).get("balance", {})
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
            parts.append(f"{_fmt(tgt)} {cur}")
        await _send(context, chat_id=chat_id, text=msg_balance_set(wallet, parts))
        _entry_counts[chat_id] = 0

    elif ptype == "question":
        # Отвечаем балансом ТОЛЬКО этого кошелька (не палим другие кошельки)
        this_bal = bridge.get_balance(group=wallet).get("balance", {})
        await _send(context,
            chat_id=chat_id,
            text=_bilingual(wallet, _balance_block("ยอดคงเหลือ", this_bal),
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


async def _record_transaction(context, bridge, claude, msg, parsed, wallet, receipt=None):
    """Запись проводок + сверка чека + перенос в кассу + подтверждение. Валюта уже разрешена
    (THB по умолчанию / явная / подтверждённая). receipt — предзагруженный разбор фото (без 2-го vision)."""
    chat_id = msg.chat_id
    text = msg.text or msg.caption or ""
    moves = parsed.get("moves") or []
    for i, mv in enumerate(moves):
        bridge.add_transaction(
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
        )

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
                              f"🧾 พี่ Pleum ในใบเสร็จ {_fmt(ramount)} {u} แต่เขียนไว้ {_fmt(wamount)} {u} "
                              f"ต่างกันนะครับ ตรวจหน่อย 🙏\n"
                              f"🧾 Пым, на чеке {_fmt(ramount)} {u}, а записано {_fmt(wamount)} {u} — "
                              f"не сходится, глянь пожалуйста 🙏"))

    wallet_bal = bridge.get_balance(group=wallet).get("balance", {})

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
        pc_bal = bridge.get_balance(group=PETTYCASH_LABEL).get("balance", {})
        await _send(context, chat_id=PETTYCASH_CHAT_ID,
                    text=msg_topup_pettycash(plus, pc_bal, wallet=PETTYCASH_LABEL, source=wallet))

    # === Подтверждение записи ===
    _entry_counts[chat_id] = _entry_counts.get(chat_id, 0) + 1
    if chat_id in MONEY_CONFIRM_EACH:
        await _send(context, chat_id=chat_id,
                    text=msg_recorded_each(disp_amount, wallet_bal, disp_currency, wallet=wallet))
        _entry_counts[chat_id] = 0
    else:
        await _send(context, chat_id=chat_id,
                    text=msg_recorded_cf(disp_amount, wallet_bal, disp_currency, wallet=wallet))
        if _entry_counts[chat_id] >= RECONCILE_EVERY:
            await _send(context, chat_id=chat_id, text=msg_reconcile(wallet, wallet_bal))
            _entry_counts[chat_id] = 0


# === Фикс B: подтверждение пробега с ФОТО приборки перед решением по ТО ===
# vision врёт на LCD → распознанную цифру подтверждаем у человека, потом _after_mileage.
_PENDING_MILEAGE = {}   # (chat_id, topic_id) -> (mileage:str, bike:str)
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
# негатор правки: «не верно / неверно / неправильно / ошибся / wrong»
_CORRECTION_RE = r"(не\s*верн|неверн|неправильн|ошиб|не\s*прав|wrong|ผิด)"


def pending_correction_for(chat_id, topic_id):
    """Есть ли открытый переспрос коррекции пробега для этой темы (перехват в handle_text)."""
    return _PENDING_CORRECTION.get((chat_id, topic_id))


def detect_mileage_correction(text):
    """Текст — это коррекция пробега? Нужен негатор + число 4-6 цифр. Вернуть new_km:int или None."""
    t = str(text or "").strip()
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


def pending_mileage_for(chat_id, topic_id):
    """Есть ли открытое подтверждение пробега для этой темы (для перехвата в handle_text)."""
    return _PENDING_MILEAGE.get((chat_id, topic_id))


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

    _PENDING_MILEAGE[(chat_id, topic_id)] = (str(mileage), bike or "", floor, bool(oil_hint))
    mark_awaiting(chat_id, topic_id)

    if floor is not None:
        await _send(context, chat_id=chat_id,
                    text=msg_mileage_drop(bike, new_km, floor),
                    message_thread_id=topic_id)
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
    sent = await _send(
        context,
        chat_id=chat_id,
        text=(f"🐀 Splinter\n"
              f"🇹🇭 อ่านเลขไมล์ได้ {mileage} กม.{b_th} ถูกต้องไหมครับ? กดปุ่ม «ใช่» หรือส่งเลขที่ถูกต้อง 🙏\n"
              f"🇷🇺 📟 Вижу пробег {mileage} км{b_ru} (с фото). Верно? Нажми «Да» или пришли правильное число 🙏"),
        message_thread_id=topic_id,
        reply_markup=kb,
    )
    _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос → удалить на финале


async def handle_mileage_confirm(msg, context, bridge, text) -> bool:
    """Перехват ответа на подтверждение пробега. Возвращает True если обработал (был pending
    и ответ распознан как да/число/нет). Иначе False → обычный путь (гейт не трогаем)."""
    key = (msg.chat_id, getattr(msg, "message_thread_id", None))
    pend = _PENDING_MILEAGE.get(key)
    if not pend:
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
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(*key)
        await _send(context, chat_id=msg.chat_id,
                    text=("🐀 Splinter\n"
                          "🇹🇭 โอเค ส่งรูปเลขไมล์ชัดๆ อีกครั้งนะครับ 🙏\n"
                          "🇷🇺 Ок, пришли, пожалуйста, чёткое фото одометра ещё раз 🙏"),
                    message_thread_id=key[1])
        return True
    else:
        return False                # не подтверждение — отдаём обычному пути
    # Сторож (фикс B): не подтверждаем «да» и не принимаем число НИЖЕ последнего известного —
    # пробег не убывает. Держим pending (floor сохраняется), ждём корректную цифру/фото.
    if floor is not None:
        try:
            if int(str(num).replace(" ", "").replace(",", "")) < floor:
                await _send(context, chat_id=msg.chat_id,
                            text=msg_mileage_drop(bike, num, floor),
                            message_thread_id=key[1])
                return True
        except (ValueError, TypeError):
            pass
    _PENDING_MILEAGE.pop(key, None)
    clear_awaiting(*key)
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
        old_km, new_km, bike = pend[0], pend[1], pend[2]
        _PENDING_CORRECTION.pop(key, None)
        clear_awaiting(*key)
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
    """САНКЦИОНИРОВАННАЯ правка (после «да»/кнопки): перезапись service_upsert(new) В ОБХОД сторожа B.
    Сторож B (floor) здесь НЕ применяется — это явное подтверждённое человеком исправление вниз.
    Сторож B для ФОТО не затрагивается. Кол.H/I (set_fleet_*) не пишем — только обслуживание."""
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
    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                text=(f"🐀 Splinter\n"
                      f"🇹🇭 ✅ แก้เลขไมล์แล้ว{b_th}: {old_km} → {new_km} กม.{extra_th}\n"
                      f"{_SEP}\n"
                      f"🇷🇺 ✅ Пробег исправлен{b_ru}: {old_km} → {new_km} км.{extra_ru}"))
    log.info(f"  → коррекция пробега ПРИМЕНЕНА (обход сторожа B): {old_km}→{new_km} (тема {topic_id})")


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


def _classify_work(w):
    """Класс работы для маршрутизации (Фаза 1) → адрес записи:
      'oil'       — моторное масло → Лист1 кол.I (set_fleet_oil, отдельный кнопочный флоу);
      'gear'      — масло редуктора/трансмиссии/ремень/шестерни → кол.J (set_fleet_service);
      'abs'       — ABS oil → кол.K;
      'airfilter' — воздушный (аир) фильтр → кол.L;
      'info'      — без столбца (масляный фильтр, колодки, цепь, вилка, прочее) → «события».
    Порядок проверок важен: воздушный фильтр → airfilter; иной фильтр → info (раньше масла)."""
    s = str(w).lower()
    is_filter = ("фильтр" in s or "filter" in s or "กรอง" in s)
    if is_filter and ("возд" in s or "air" in s or "аир" in s or "อากาศ" in s):
        return "airfilter"          # воздушный фильтр → кол.L
    if is_filter:
        return "info"               # масляный/прочий фильтр — столбца нет → события
    if "abs" in s or "абс" in s:
        return "abs"                # ABS oil → кол.K
    if any(k in s for k in ("gear", "ремн", "шестер", "редуктор", "трансмис", "เกียร์")):
        return "gear"               # масло редуктора → кол.J
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


# Хранилище токенов вопроса «после замены/просто пробег» (callback_data ≤64б → короткий int-токен).
_SVC_TOKENS = {}   # token(int) -> {chat,topic,bike,km,status,next_km,km_left}
_SVC_SEQ = [0]


def _svc_put(data):
    _SVC_SEQ[0] += 1
    tok = _SVC_SEQ[0]
    _SVC_TOKENS[tok] = data
    if len(_SVC_TOKENS) > 200:                       # держим последние 200
        for k in sorted(_SVC_TOKENS)[:-200]:
            _SVC_TOKENS.pop(k, None)
    return tok


def _svc_question_open(chat_id, topic_id):
    """Открыт ли по этой теме вопрос [После замены]/[Просто пробег] (ждём нажатия кнопки)."""
    return any(d.get("chat") == chat_id and d.get("topic") == topic_id
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
        f"🇹🇭 🔧 การบันทึกการเปลี่ยนน้ำมันเครื่อง ยืนยันโดย @Pleummmm หรือเจ้าของเท่านั้น. "
        f"@Pleummmm ยืนยันการเปลี่ยนน้ำมัน{b_th} = {km} กม. ไหมครับ? ตอบ «ใช่» หรือ «ไม่»\n"
        f"🇷🇺 🔧 Запись ТО в журнал подтверждает @Pleummmm или владелец. "
        f"@Pleummmm, подтвердите замену масла{b_ru} = {km} км? да/нет"
    )


# ===================== ИНТЕРВАЛЫ ТО из книги знаний (Brain) с фоллбэком на хардкод =====================
# Бот читает блок ```json SERVICE_INTERVALS``` из knowledge_base через read_doc, кэширует ~10 мин.
# Docs флапает → ЛЮБАЯ ошибка чтения/парса = фоллбэк на хардкод (расчёт ТО НЕ должен падать).
# Хардкод-дубли (_oil_interval / oil_interval_for) НЕ удалены — это и есть фоллбэк.
_SVC_INTERVALS_CACHE = {"data": None, "ts": 0.0}
_SVC_INTERVALS_TTL = 600   # 10 мин
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


async def _ask_oil_or_km(context, chat_id, topic_id, bike, km, status, next_km, km_left):
    """Задать вопрос кнопками [После замены]/[Просто пробег] (фиксация через явный ответ)."""
    tok = _svc_put({"chat": chat_id, "topic": topic_id, "bike": bike or "", "km": str(km),
                    "status": status, "next_km": next_km, "km_left": km_left})
    # Кнопки в ДВА ряда, тайский ПЕРВЫМ (тайцы — основные в обслуживании; RU не теряется на узком экране).
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 หลังเปลี่ยนน้ำมัน / После замены", callback_data=f"svc:oil:{tok}")],
        [InlineKeyboardButton("📷 แค่เลขไมล์ / Просто пробег", callback_data=f"svc:km:{tok}")],
    ])
    sent = await _send(context, chat_id=chat_id, text=msg_oil_or_km(bike, km),
                       message_thread_id=topic_id, reply_markup=kb)
    _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос → удалить на финале


async def _after_mileage(context, bridge, chat_id, topic_id, bike, mileage, oil_hint=False):
    """Пробег подтверждён (прошёл сторож B). Прогоняем ТО-трекер; если замена осмысленна
    (ТО due/overdue ИЛИ была подсказка-маркер) — спрашиваем кнопками. Иначе — квитанция «пробег принят»."""
    info = _run_service_tracker(bridge, chat_id, topic_id, bike, mileage)
    if not info:
        return
    if info["status"] in ("due", "overdue") or oil_hint:
        await _ask_oil_or_km(context, chat_id, topic_id, bike, info["km"],
                             info["status"], info["next_km"], info["km_left"])
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


async def _write_oil(context, bridge, chat_id, topic_id, bike, km):
    """Боевая запись ТО Oil в Лист1 кол.I (set_fleet_oil confirmed=True) + снять закреп + отчёт.
    Вызывается ТОЛЬКО после [После замены] от доверенного. Резолвит ГОЛЫЙ номер байка."""
    plate = _plate_from_name(bike)
    if not plate:
        fb = bridge.find_bike(bike) or {}
        plate = _plate_from_name(fb.get("name", ""))
    if not plate:
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
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
        acc = _summary_acc(chat_id, topic_id)
        acc["current_km"] = str(km_int)
        acc["oil"] = {"km": km_int, "next": (km_int + _iv) if _iv else None, "status": "ok"}
        await _close_service_reminder(context, bridge, chat_id, topic_id, bike)   # снимает ВСЕ старые пины (unpin_all)
        _sum_msg = await _emit_summary(context, chat_id, topic_id, bike)
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
    else:
        err = res.get("error", "")
        if err == "oil_decreasing":
            detail_ru = f"новое {km_int} меньше прошлого ТО {res.get('old_oil')} — не записал, проверь число"
            detail_th = f"ค่าใหม่ {km_int} น้อยกว่าครั้งก่อน {res.get('old_oil')} — ไม่บันทึก"
        elif err == "ambiguous":
            detail_ru = f"несколько байков с номером {plate} — уточни какой"
            detail_th = f"มีรถหลายคันเลข {plate} — ระบุให้ชัด"
        elif err == "not_found":
            detail_ru = f"не нашёл байк с номером {plate} в Лист1"
            detail_th = f"ไม่พบรถเลข {plate} ใน Лист1"
        else:
            detail_ru = f"не удалось записать ({err or 'ошибка'})"
            detail_th = f"บันทึกไม่สำเร็จ ({err or 'error'})"
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                    text=(f"🐀 Splinter\n🇹🇭 ⚠️ {detail_th}\n🇷🇺 ⚠️ {detail_ru}"))


# Метки видов ТО группы B (TH, RU) — для кнопок/квитанций. kind → (тайский, русский).
_SVC_COL_LABEL = {
    "gear":      ("น้ำมันเกียร์", "редуктор (gear)"),
    "abs":       ("น้ำมัน ABS", "ABS"),
    "airfilter": ("ไส้กรองอากาศ", "возд. фильтр"),
}


async def _ask_service_col(context, chat_id, topic_id, bike, kind, km):
    """Кнопка-фиксация регламента группы B (gear→J/abs→K/airfilter→L) в свой столбец Лист1.
    Боевая запись — ТОЛЬКО доверенным (как масло). Пробег показываем в кнопке — человек сверяет."""
    th_lbl, ru_lbl = _SVC_COL_LABEL.get(kind, (kind, kind))
    tok = _svc_put({"kind": "svc_col", "chat": chat_id, "topic": topic_id,
                    "bike": bike or "", "svc_kind": kind, "km": str(km)})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ บันทึก {th_lbl} / Зафиксировать {ru_lbl}", callback_data=f"svc:col:{tok}")],
    ])
    b = f" · 📌 {bike}" if bike else ""
    sent = await _send(context, chat_id=chat_id, message_thread_id=topic_id,
        text=(f"🐀 Splinter{b}\n"
              f"🇹🇭 🔧 บันทึก «{th_lbl}» = {km} กม. ไหมครับ? กดปุ่ม (ยืนยันโดย @Pleummmm/เจ้าของ) 👇\n"
              f"🇷🇺 🔧 Зафиксировать «{ru_lbl}» = {km} км? Нажми кнопку (подтверждает @Pleummmm/владелец) 👇"),
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
        err = res.get("error", "")
        if err == "km_decreasing":
            detail_ru = f"новое {km_int} меньше прошлого {res.get('old_km')} — не записал, проверь число"
            detail_th = f"ค่าใหม่ {km_int} น้อยกว่าครั้งก่อน {res.get('old_km')} — ไม่บันทึก"
        elif err == "ambiguous":
            detail_ru = f"несколько байков с номером {plate} — уточни какой"
            detail_th = f"มีรถหลายคันเลข {plate} — ระบุให้ชัด"
        elif err == "not_found":
            detail_ru = f"не нашёл байк с номером {plate} в Лист1"
            detail_th = f"ไม่พบรถเลข {plate} ใน Лист1"
        else:
            detail_ru = f"не удалось записать ({err or 'ошибка'})"
            detail_th = f"บันทึกไม่สำเร็จ ({err or 'error'})"
        await _send(context, chat_id=chat_id, message_thread_id=topic_id,
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
        sent = await _send(context, chat_id=chat_id, text=text, message_thread_id=topic_id)
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
        await q.answer()
        return
    data = _SVC_TOKENS.get(token)
    if not data:
        await q.answer()
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
        # Санкционированная человеком правка → перезапись в обход сторожа B (только этот путь).
        await q.answer("กำลังแก้… · Исправляю…")
        old_km, new_km = data.get("old_km"), data.get("new_km")
        key = (chat_id, topic_id)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _SVC_TOKENS.pop(token, None)
        _PENDING_CORRECTION.pop(key, None)
        clear_awaiting(*key)
        try:
            await _apply_correction(context, bridge, chat_id, topic_id, bike, old_km, new_km)
        except Exception:
            log.exception("  → ошибка применения коррекции пробега (кнопка)")
        return

    if action == "mok":
        # [✅ Да] на подтверждение распознанного пробега — эквивалент текстового «да».
        # Сторож B сохранён: если число < floor — не принимаем, шлём msg_mileage_drop.
        await q.answer()
        mileage = data.get("mileage", "")
        floor = data.get("floor")
        oil_hint = bool(data.get("oil_hint"))
        key = (chat_id, topic_id)
        if floor is not None:
            try:
                if int(str(mileage).replace(" ", "").replace(",", "")) < floor:
                    await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                                text=msg_mileage_drop(bike, mileage, floor))
                    return
            except (ValueError, TypeError):
                pass
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _SVC_TOKENS.pop(token, None)
        _PENDING_MILEAGE.pop(key, None)
        clear_awaiting(*key)
        try:
            await _after_mileage(context, bridge, chat_id, topic_id, bike, mileage, oil_hint)
        except Exception:
            log.exception("  → ошибка ТО-трекера (кнопка Да)")
        return

    if action == "col":
        # [Зафиксировать <тип>] группы B (gear/abs/airfilter) → set_fleet_service. ТОЛЬКО доверенный.
        svc_kind = data.get("svc_kind", "")
        if not _is_trusted_user(q.from_user):
            await q.answer("ยืนยันโดย @Pleummmm/เจ้าของ · Подтверждает @Pleummmm или владелец", show_alert=False)
            th_lbl, ru_lbl = _SVC_COL_LABEL.get(svc_kind, (svc_kind, svc_kind))
            await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                        text=(f"🐀 Splinter\n"
                              f"🇹🇭 🔧 การบันทึก «{th_lbl}» ยืนยันโดย @Pleummmm หรือเจ้าของเท่านั้น\n"
                              f"🇷🇺 🔧 Запись «{ru_lbl}» подтверждает @Pleummmm или владелец"))
            return   # токен и кнопка живут — Пым нажмёт позже
        await q.answer("กำลังบันทึก… · Записываю…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _SVC_TOKENS.pop(token, None)
        await _write_service_col(context, bridge, chat_id, topic_id, bike, svc_kind, km)
        return

    if action == "oil":
        # [После замены] → боевая запись кол.I. ТОЛЬКО доверенный.
        if not _is_trusted_user(q.from_user):
            await q.answer("ยืนยันโดย @Pleummmm/เจ้าของ · Подтверждает @Pleummmm или владелец", show_alert=False)
            await _send(context, chat_id=chat_id, message_thread_id=topic_id,
                        text=msg_oil_need_trusted(bike, km))
            return   # токен и кнопки живут — Пым нажмёт [После замены] позже
        await q.answer("กำลังบันทึกน้ำมันเครื่อง… · Записываю ТО Oil…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _SVC_TOKENS.pop(token, None)
        await _write_oil(context, bridge, chat_id, topic_id, bike, km)
    elif action == "km":
        # [Просто пробег] → в кол.I НЕ пишем. Квитанцию шлём ВСЕГДА (раньше при уже-закреплённой
        # просрочке _pin_overdue_reminder выходил молча → человек видел тишину).
        await q.answer()
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        _SVC_TOKENS.pop(token, None)
        try:
            km_int = int(str(km).replace(" ", ""))
        except (ValueError, TypeError):
            km_int = km
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
    else:
        await q.answer()


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

    # ЗАХОД 2: запрос КАРТОЧКИ байка («инфа/статус/что по байку») — отвечаем карточкой из ЧИТАЕМЫХ
    # источников (пробег, ТО Oil, J/K/L, аренда), НИЧЕГО не пишем. Только текст без фото.
    if text.strip() and not has_photo and _is_status_request(text):
        _card_bike = bike_from_topic(chat_id, topic_id) or ""
        if _card_bike:
            log.info(f"  → запрос карточки байка: {_card_bike}")
            try:
                await _send_bike_card(context, bridge, chat_id, topic_id, _card_bike)
            except Exception:
                log.exception("  → ошибка карточки байка")
            return

    # Разбираем текст (если есть) на событие
    parsed = {}
    if text.strip():
        parsed = _parse_json(claude.quick(SERVICING_SYSTEM, text, max_tokens=300))

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

    # === РАЗБОР ПЕРЕЧНЯ РАБОТ ПО АДРЕСАМ (вариант A: строка-на-работу) ===
    # Масло → кол.I (флоу ниже), gear/abs/возд.фильтр → группа B (кол.J/K/L, флоу ниже).
    # ИНФО-работы (колодки/цепь/масл.фильтр/вилка/прочее) → история «события» ОТДЕЛЬНОЙ строкой на
    # работу, с привязкой пробега. Перечень в одну repair-строку БОЛЬШЕ не валим — разносим.
    non_oil_works = [w for w in works if not _is_oil_work(w)]
    if non_oil_works:
        event_type = "repair"   # для force/_service_ctx ниже (перечень в notes НЕ лепим)
    info_works = [w for w in works if _classify_work(w) == "info"]
    _km_conf_ok = str(vis.get("mileage_confidence", "")) != "low"
    km_now = parsed.get("mileage") or (vis.get("mileage") if _km_conf_ok else "") or ""
    _ev_msg_id = f"{chat_id}:{msg.message_id}"
    _msg_date = str(msg.date.date()) if msg.date else ""

    # Пришёл чёткий пробег в теме → дописать ОТЛОЖЕННЫЕ инфо-работы прошлого сообщения с этим км.
    _logged_works = []
    if km_now:
        _logged_works += _flush_pending_works(bridge, chat_id, topic_id, group_name, bike, str(km_now), _msg_date)

    _ev_r = None
    if info_works:
        if km_now:
            # Пробег есть В ЭТОМ сообщении → пишем инфо-работы СРАЗУ, по строке на работу, с км.
            _logged_works += _write_info_works(bridge, group_name, topic_id, bike, info_works, str(km_now), _ev_msg_id, _msg_date)
        else:
            # Пробега нет → буферизуем перечень; запишем при приходе пробега (flush). Ниже уйдёт переспрос.
            _PENDING_WORKS[(chat_id, topic_id)] = {
                "works": info_works, "bike": bike, "msg_id_base": _ev_msg_id, "ts": _time.time(),
            }
            log.info(f"  → инфо-работы отложены до пробега: {info_works} (тема {topic_id})")
    else:
        # Нет инфо-работ — обычное событие сообщения (фото/возврат/топливо/только колоночные) пишем как раньше.
        _ev_r = bridge.add_event(
            msg_date=_msg_date,
            group=group_name + (f" / тема {topic_id}" if topic_id else ""),
            bike=bike, event_type=event_type, fuel=str(fuel), mileage=str(mileage),
            photos=1 if has_photo else 0, notes=notes, msg_id=_ev_msg_id,
        )
    # ДИАГ: бот раньше ВЫБРАСЫВАЛ return add_event — теперь видно saved/duplicate/error + разбор работ.
    log.info(f"  → add_event: ok={(_ev_r or {}).get('ok')} saved={(_ev_r or {}).get('saved')} "
             f"duplicate={(_ev_r or {}).get('duplicate')} error={(_ev_r or {}).get('error')} "
             f"msg_id={_ev_msg_id} info_works={len(info_works)} km_now={km_now or '-'} event_type={event_type}")

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
    if works and bike and mileage and _conf_ok:
        seen_kinds = []
        for w in works:
            k = _classify_work(w)
            if k in ("gear", "abs", "airfilter") and k not in seen_kinds:
                seen_kinds.append(k)
        for k in seen_kinds:
            try:
                await _ask_service_col(context, chat_id, topic_id, bike, k, str(mileage))
            except Exception:
                log.exception(f"  → ошибка кнопки фиксации группы B ({k})")

    # Реальное ПОВРЕЖДЕНИЕ → зовём Пыма (это к осмотру / возможным вычетам).
    # Грязь сюда НЕ попадает — она отсекается на уровне vision (damage=null, dirt=true).
    if vis.get("damage"):
        await _send(context, 
            chat_id=chat_id,
            text=(f"🐀 Splinter\n"
                  f"⚠️ พี่ Pleum เห็นความเสียหายในรูป ตรวจสอบหน่อยครับ 🙏\n"
                  f"⚠️ Пым, на фото видны повреждения: {vis['damage']} — глянь. "
                  f"Если это возврат — посмотри по депозиту 🙏"),
            message_thread_id=topic_id,
        )
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
        await _send(context, chat_id=chat_id,
                    text=msg_work_receipt(bike, works), message_thread_id=topic_id)
        col_kinds = {k for k in (_classify_work(w) for w in works)
                     if k in ("oil", "gear", "abs", "airfilter")}
        # Пробег нужен И колоночным (масло/gear/abs/возд.фильтр для записи в столбец), И инфо-работам
        # (колодки/цепь/фильтр — они отложены в буфер и ждут пробег для привязки «работа — км»).
        if col_kinds or info_works:
            # Обходим ложное подавление high-буфером доработочного замера ТОЛЬКО при ЯВНОМ маркере
            # выполненной работы (repair-событие или oil-done); cooldown 10 мин уважаем всегда.
            force = (event_type == "repair") or oil_hint
            if _should_ask_odometer(chat_id, topic_id, ignore_buffer=force):
                sent = await _send(context, chat_id=chat_id,
                                   text=msg_ask_odometer(bike), message_thread_id=topic_id)
                _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос
        return

    # Масло-контекст, но БЕЗ чёткого пробега в ЭТОМ сообщении → САМ просим ЧЁТКОЕ фото одометра.
    # (damage уже отработан выше и сделал return — повреждение приоритетнее.)
    # Ничего в ТО не пишем, число не выдумываем. Анти-спам: буфер high-пробега + троттлинг.
    no_clear_km = (not mileage) or str(vis.get("mileage_confidence", "")) == "low"
    if _is_oil_context(text, vis) and no_clear_km and _should_ask_odometer(chat_id, topic_id):
        sent = await _send(context,
            chat_id=chat_id, text=msg_ask_odometer(bike), message_thread_id=topic_id
        )
        _remember_cycle_msg(chat_id, topic_id, sent)   # ЧАСТЬ D: промежуточный вопрос
        return

    # Только ГРЯЗЬ (без повреждений) → мягко просим помыть/обработать. Пыма НЕ тегаем.
    # Фикс C: в сервис-контексте совет «помыть/воск/чехол» неуместен — идёт работа по ТО, не мойка.
    # Сервис-контекст = масло/ремонт/чек ИЛИ фото приборки с пробегом (ТО-флоу) ИЛИ открыт вопрос svc по теме.
    _service_ctx = (oil_hint or _is_oil_context(text, vis)
                    or event_type == "repair" or vis.get("kind") == "receipt"
                    or bool(vis.get("mileage"))
                    or _svc_question_open(chat_id, topic_id))
    if vis.get("dirt") and not _service_ctx:
        await _send(context,
            chat_id=chat_id,
            text=msg_dirty_care(bike),
            message_thread_id=topic_id,
        )
        return

    # Возврат/сдача без топлива или пробега → напоминаем команде + Пыма
    if event_type in ("return", "handover") and (not fuel or not mileage):
        await _send(context, 
            chat_id=chat_id, text=msg_photo_reminder(bike), message_thread_id=topic_id
        )


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
    return _parse_json(claude.quick(INTAKE_SYSTEM, text, max_tokens=500)) or {}


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
        f"Наличие: {availability}\n"
        "\nСтавлю бронь? да / нет / правки"
    )


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


async def _handle_intake(msg, context, bridge, claude, photo_msgs=None):
    """Приём карточек брони (этап A): карточка → пакет/наличие → резюме+approve. CRM read-only.
    photo_msgs — пачка фото (альбом склеен по media_group_id) → один «паспорт получен» + один finalize."""
    chat_id = msg.chat_id
    text = (msg.text or msg.caption or "").strip()
    if photo_msgs is None:
        photo_msgs = [msg] if msg.photo else []
    has_photo = bool(photo_msgs)
    now = _time.time()

    # 1) Фото паспорта отдельным сообщением → связать с последней карточкой (окно 5 мин)
    if has_photo and not _intake_is_card(text):
        d = _INTAKE_DRAFTS.get(chat_id)
        if d and now - d.get("ts", 0) <= 300:
            d["passport_photo"] = True
            await _send(context, chat_id=chat_id,
                        text="🐀 Splinter\n📎 Фото паспорта получено — привязал к последней карточке.",
                        bilingual=False, message_thread_id=getattr(msg, "message_thread_id", None))
            await _intake_finalize(d, msg, context, bridge)   # вдруг теперь пакет полный
        return

    # 2) Карточка брони
    if _intake_is_card(text):
        parsed = _intake_parse(claude, text)
        prev = _INTAKE_DRAFTS.get(chat_id)
        # фото могло прийти ДО карточки (в пределах 5 мин) — наследуем флаг
        passport = bool(prev and prev.get("passport_photo") and now - prev.get("ts", 0) <= 300)
        draft = dict(parsed)
        draft.update(ts=now, passport_photo=passport, status="new")
        _INTAKE_DRAFTS[chat_id] = draft
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
            log.info(f"  🆕 INTAKE: approve получен (@{_who}) для брони {d.get('model')} "
                     f"— ЭТАП B (createBooking + задача тайцам) НЕ реализован")
            await _send(context, chat_id=chat_id,
                        text="🐀 Splinter\n✅ Approve принят. (Этап B — постановка брони и задача "
                             "тайцам — пока не подключён, бронь НЕ ставлю.)", bilingual=False, message_thread_id=tid)
        elif any(w in low for w in ("нет", "отмена", "не ставь", "отклон")):
            d["status"] = "rejected"
            await _send(context, chat_id=chat_id, text="🐀 Splinter\n❌ Бронь отклонена.",
                        bilingual=False, message_thread_id=tid)
        elif "правк" in low or "исправ" in low:
            await _send(context, chat_id=chat_id,
                        text="🐀 Splinter\n✏️ Принял, жду исправленную карточку.", bilingual=False, message_thread_id=tid)
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
        log.exception(f"Splinter error in {mode} ({msg.chat_id})")
