#!/usr/bin/env python3
"""ЯДРО СЛУЖБЫ wa-agent — черновик ответа клиенту WhatsApp, согласование в группе, одно нажатие —
одно сообщение (WAAGENTCORE0110, шаг 2 плана WAAGENTLIVE0110 §7).

ЧТО ЭТО. Решение «когда писать черновик, когда его снять, кто нажал первым и ушло ли сообщение»
живёт ЗДЕСЬ и только здесь. Рук у ядра нет: модель, Telegram и дверь отправки приходят снаружи
интерфейсами (`Model`, `Telegram`, `Door` ниже), и ядро не импортирует ни сети, ни `wa_send`,
ни клиента модели. Службы и юнита ещё нет — это шаги 3–4 плана; запуск файла отказывает словами.

ЧТО ЧИТАЕТСЯ И ЧТО ПИШЕТСЯ.
  очередь `wa_queue.db` (`wa_inbox`)  — ТОЛЬКО `mode=ro`; вид строки решает `wa_kind.kind_of`.
  своя база `wa_agent.db`             — курсор, клиенты (пауза), черновики. Чужих баз не пишем.

ТАКТ (`Core.tick`):
  1. СКАН. Строки очереди `id > курсор`. Живое входящее (inbound, history=0) двигает «последнее
     сообщение клиента» и делает его ждущий черновик `stale`. Живое эхо (echo=1, history=0,
     msg_type не status, wamid не наш) — ответ человека с телефона: ждущий черновик `superseded`,
     клиент на ПАУЗЕ, в группу ОДИН вопрос «когда продолжать» на одну паузу (правило владельца
     30.09.2026-7 п.4). Пауза снимается только нажатием «Продолжить» (`Core.resume`).
     Исключение — автоприветствие WhatsApp Business (WAGREETECHO0210, вариант В3 WAAUTOGREET0210):
     эхо, у которого отпечаток текста равен настройке службы И которое пришло не позже GREET_SEC
     после «первого» входящего. Паузы нет, черновик жив, done_upto не трогается — первый вопрос
     клиента остаётся открытым (запись владельца 02.10.2026-1 п.3). Строка — в таблицу `autogreet`.
     На первом старте курсор встаёт на MAX(id): переписка до службы черновиков не даёт.
  2. ЧЕРНОВИК. Клиент не на паузе, ждущих сообщений больше, чем закрыто прежним решением, живого
     черновика нет, со времени последнего сообщения прошло `quiet` (60–90 с — клиенты пишут
     очередями). Перед записью — перепроверка очереди: пришло новое за время модели — не пишем.
     Живой черновик у клиента один: проверка кодом И частичный уникальный индекс базы.

НАЖАТИЕ (`Core.press`). Захват — условный UPDATE `state='pending' AND ver=?`, решает rowcount;
проигравший получает «уже решено: кто, когда, исход». Победитель перепроверяет очередь (эхо →
superseded и пауза; новое входящее → stale), пишет `sending` и ТОЛЬКО ПОТОМ зовёт дверь, затем
исход: sent (с wamid) · not_sent · unsure. Повтора нет нигде: `unknown` двери = `unsure`, а на
старте службы `sending` → `unsure` (сообщение могло уйти) — тот же замок, что `_init_state`
службы показа. `claimed` на старте → `pending`: дверь ещё не звали, отправки не было.

ЧЕЛОВЕЧЕСКИЙ РИТМ (WAHUMANPACE0210, выключатель службы WA_AGENT_PACE, по умолчанию выключен — «Отправить»
шлёт сразу, как раньше). Включён — после захвата и перепроверки очереди ядро считает срок (`_pace_due`):
первый ответ беседы — сообщение клиента + случайно PACE_FIRST_MIN–PACE_FIRST_MAX; следующий — сообщение
клиента + длина / PACE_CPS (не дольше PACE_TYPE_MAX), то есть модель и человек думали дольше набора — без
добавки. Срок не настал — черновик `scheduled` со сроком в базе, на карточке «уйдёт в ЧЧ:ММ» и «Отменить»;
отправку в срок делает такт (`send_due`) через тот же захват `sending` ДО двери. Рестарт срок не теряет и
не дублирует. Клиент написал ещё — отложенное снимается и не уходит, черновик пересобирается (WADRAFTSAFE0210;
до него одобренное уходило в срок и после нового сообщения клиента).

ДОСТАВКА КАРТОЧЕК И АКТУАЛЬНОСТЬ (WADRAFTSAFE0210). У каждой карточки (черновик + версия) состояние на диске,
таблица `card_out`: wait (ждёт доставки) → sending (`sendMessage` зван) → delivered (message_id, chat_id, время)
→ decided (исход на карточке; правку, которую Telegram отказал, такт повторяет). Отказ Telegram — повтор с
паузой CARD_RETRY, рестарт очередь продолжает; sending на старте → wait: карточка могла дойти, шлём снова —
дубль карточки безопасен, кнопки несут черновик и версию, второе нажатие — «уже решено». Повторяются ТОЛЬКО
карточки в Telegram, отправка клиенту — никогда. Черновик решён до доставки — карточка не шлётся, решена
недоставленной; ждущие черновики без доставленной карточки — числом в сводке службы (`undelivered`).
Исход вызова рук — три слова (WACARDDONEFIX0210): подтверждено · отказ · НЕИЗВЕСТНО. Руки упали (исключение,
таймаут, ответ Telegram потерян) — вызов мог лечь: отправка карточки — повтор как при отказе, но в `card_out.lost`
и в сводке отдельно («возможна вторая карточка», единственность не обещается); правка исхода засчитывается
ТОЛЬКО на True рук, исключение — повтор в тех же пределах EDIT_MAX и итог `unconfirmed` («не подтверждено»), а не
`ok`. Прочие вызовы рук (`_tg`) исключение по-прежнему глотают в None.
«Отправить» привязано к последнему сообщению клиента (`drafts.upto_id` против `clients.last_in_id` и очереди)
и версии контекста (`clients.ctx`: +1 на живое входящее, ответ с телефона, текст из темы, «Продолжить»;
`drafts.ctx` — на момент черновика). Устарело — ответ словами, наружу ничего, черновик пересобирается. Новое
входящее снимает и ждущий, и отложенный черновик; ответ с телефона и текст из темы — тоже оба.

УРОКИ ЛЮДЕЙ (WAAGENTLESSON0210, выключатель службы WA_AGENT_LESSONS, по умолчанию выключен — «Исправить»
как раньше). Включён — принятое «Исправить» с новым текстом пишет в таблицу `lessons` своей базы КАНДИДАТА
урока: номер, автор, время, источник (черновик, версии), было/стало, причина (реплай на сообщение урока,
пока он кандидат) или пусто. В промпт агента идут ТОЛЬКО действующие (`active_lessons`); перевод
кандидата в действующие — отдельной кнопкой и только тем, кто в праве (`lesson_admins_of`: настройка
WA_AGENT_LESSON_ADMINS, по умолчанию владелец); остальным — отказ словами. Откат по номеру убирает
урок из промпта. Хранилище своё — с уроками и правилами Splinter не смешивается.

НАПОМИНАНИЕ ПРИТИХШЕМУ (WAFOLLOWUP0210, выключатель службы WA_AGENT_FOLLOWUP, по умолчанию выключен). Включён —
раз в FOLLOW_EVERY такт ищет клиентов, у которых последнее слово НАШЕ (ушедшее через API или эхо с телефона,
автоприветствие не в счёт) и после него FOLLOW_QUIET тишины; окно 24 ч открыто (правило `wa_send.window_state`,
с запасом FOLLOW_SPARE); живого и отложенного черновика нет; клиент не на паузе; напоминаний в беседе меньше
FOLLOW_MAX. Тогда модель (`Model.followup`) пишет одно короткое напоминание — черновик вида «напоминание» с
карточкой на «Отправить» — или говорит «не нужно»: карточки нет, строка журнала. Модель спрашивается ОДИН раз
на наше последнее сообщение (`followups`). Клиент написал до нажатия — карточка «устарело». Ритм на
напоминание не действует: тишина в нём уже есть.

СТРОКА ПОКАЗА УШЕДШЕГО АГЕНТОМ (WAMIRROR0410). Дверь вернула sent и wamid — в теме клиента ОДНА строка: время,
«агент», кто подтвердил, № черновика, версия, часть (текст · PDF), текст. Исход «неизвестно» — строка «исход
неизвестен, проверьте телефон»; отказ двери строки не даёт. Флаг relay её НЕ решает (до правки строка жила только
при WA_AGENT_RELAY и при выключенном молча не ложилась). Итог показа — таблица `agent_show`, ключ «wamid|часть»
(у «неизвестно» wamid нет — «?черновик|часть|попытка»): wait → sending (ДО вызова рук) → shown (id сообщения темы) ·
gave_up. Показанный ключ второй строки не даёт ни повтором, ни рестартом; Telegram не принял или темы нет — повтор по
тому же ключу с паузой CARD_RETRY, не больше SHOW_MAX попыток; ответа Telegram нет (сеть) или рестарт посреди
вызова — тоже повтор, но в `lost`: единственность строки тогда не обещается (тот же замок, что у карточек).
Прошлое не показывается: ушедшее до первого старта этого кода (meta `show_since`) строки не получает. Руки — метод
`agent_line` у Telegram; рук нет — показа нет. Строка показа клиенту не уходит, паузы не ставит и текстом из темы
не считается: её пишет бот, а из темы наружу идёт только сообщение человека (`wa_agent_tg.Tg.on_topic`).

ЧЕГО ЯДРО НЕ ДЕЛАЕТ. Не шлёт без нажатия; не повторяет отправку; не судит окно 24 часа (это
дверь, `wa_send.window_state`); не держит текстов клиентов в журнале — только id, состояния, числа.
"""

import hashlib
import json
import random
import sqlite3
import time

import wa_kind

# ── состояния черновика ─────────────────────────────────────────────────────────────────
PENDING, CLAIMED, SENDING = "pending", "claimed", "sending"
SENT, NOT_SENT, UNSURE = "sent", "not_sent", "unsure"
SUPERSEDED, STALE, DECLINED = "superseded", "stale", "declined"
SCHEDULED = "scheduled"                       # «Отправить» нажато до срока ритма: ждёт срока (WAHUMANPACE0210)
STATES = (PENDING, CLAIMED, SENDING, SENT, NOT_SENT, UNSURE, SUPERSEDED, STALE, DECLINED, SCHEDULED)
LIVE = (PENDING, CLAIMED, SENDING)            # «живой» черновик: у клиента не больше одного
# scheduled — не «живой»: клиент написал ещё — следующий черновик родится, одобренное уйдёт в срок

# ── действия кнопок ─────────────────────────────────────────────────────────────────────
ACT_SEND, ACT_DECLINE, ACT_CANCEL = "send", "decline", "cancel"

# ── человеческий ритм (WAHUMANPACE0210) — числа замера по архиву копии телефона и очереди ──
PACE_FIRST_MIN, PACE_FIRST_MAX = 180, 300     # первый ответ беседы: сообщение клиента + случайно 3–5 мин
PACE_CPS = 1.75                               # знаков в секунду: медиана наших двух подряд, 10 933 пары
PACE_TYPE_MAX = PACE_FIRST_MAX                # набор длинного текста не дольше окна первого ответа
PACE_NEW_TALK = 4 * 3600                      # беседа новая: до сообщения клиента тишина в обе стороны > 4 ч

# ── доставка карточек в «Агенты» (WADRAFTSAFE0210) ───────────────────────────────────────
CARD_WAIT, CARD_SENDING, CARD_DELIVERED, CARD_DECIDED = "wait", "sending", "delivered", "decided"
CARD_RETRY = (5, 15, 30, 60, 120, 300)        # пауза перед повтором, с: попытка N — элемент N, дальше последний
EDIT_WAIT, EDIT_OK, EDIT_GAVE_UP = "wait", "ok", "gave_up"
EDIT_UNCONFIRMED = "unconfirmed"              # предел вышел, и хоть один ответ был неизвестен: могла лечь (WACARDDONEFIX0210)
EDIT_MAX = 12                                 # правка исхода: попыток не больше (≈ 40 мин), дальше — строка журнала
WROTE_WORDS = "клиент написал ещё (строка %d)"

# ── пауза между последним сообщением клиента и черновиком ───────────────────────────────
QUIET_MIN, QUIET_MAX, QUIET_DEFAULT = 60, 90, 75
SCAN_LIMIT = 500                              # строк очереди за один скан
MODEL_RETRY_SEC = 300                         # модель не дала текста — следующая попытка не раньше

# исход двери → состояние черновика; всё незнакомое — unsure (могло уйти, не повторяем)
_DOOR_STATE = {"sent": SENT, "not_sent": NOT_SENT, "unknown": UNSURE}

# ── автоприветствие WhatsApp Business (WAGREETECHO0210) ─────────────────────────────────
# Поля, отличающего автоответ от эха человека, в событии нет (WAAUTOGREET0210 §2) — только текст и
# время, и нужны ОБА: отпечаток текста равен настройке И ≤ GREET_SEC после «первого» входящего.
# Замер по всей очереди: приветствий ≤ 10 с — 119 из 128, чужих эхо ≤ 10 с после «первого» — 0 из
# 2 448 (самое быстрое — 12 с). Любая ошибка уходит в паузу, то есть в прежнее поведение.
GREET_SEC = 10                                # эхо не позже 10 с после «первого» входящего
GREET_SILENCE = 14 * 86400                    # «первое»: до него 14 суток тишины в обе стороны
GREET_FP_MIN = 10                             # отпечаток в настройке — sha256 или его начало от 10 знаков


# ── уроки людей (WAAGENTLESSON0210) ───────────────────────────────────────────────────────
LESSON_CANDIDATE, LESSON_ACTIVE, LESSON_ROLLED = "candidate", "active", "rolled_back"
# владелец по умолчанию — те же три аккаунта, что `splinter.OWNER_IDS` (тест сверяет литерал по тексту
# splinter.py, без импорта: Splinter тянет python-telegram-bot)
LESSON_OWNER_IDS = frozenset({504608015, 6879003264, 5466425480})
LESSON_REASON_MAX = 500                       # причина урока, символов
LESSON_OFF_WORDS = "уроки выключены (WA_AGENT_LESSONS)"

# ── напоминание притихшему (WAFOLLOWUP0210) ───────────────────────────────────────────────
KIND_FOLLOW = "followup"                      # drafts.kind: черновик-напоминание; NULL — ответ на сообщение
FOLLOW_QUIET = 15 * 60                        # тишина клиента после нашего последнего сообщения
FOLLOW_MAX = 2                                # напоминаний на беседу (граница беседы — PACE_NEW_TALK)
FOLLOW_EVERY = 60                             # поиск притихших — не чаще раза в минуту
FOLLOW_WINDOW = 24 * 3600                     # окно 24 ч — то же число, что wa_send.WINDOW_SECS (тест сверяет)
FOLLOW_SPARE = 30 * 60                        # до закрытия окна — не меньше этого: человеку нужно время нажать
FOLLOW_NOT_NEEDED, FOLLOW_DRAFTED = "not_needed", "drafted"
FOLLOW_STALE_WORDS = "устарело: клиент написал сам (строка %d) — напоминание не нужно"

# ── строка показа ушедшего агентом (WAMIRROR0410) ────────────────────────────────────────
PART_TEXT, PART_PDF = "text", "pdf"
SHOW_WAIT, SHOW_SENDING, SHOW_SHOWN, SHOW_GAVE_UP = "wait", "sending", "shown", "gave_up"
SHOW_MAX = 12                                 # попыток строки показа не больше (≈ 40 мин по CARD_RETRY), дальше — журнал
SHOW_SINCE = "show_since"                     # meta: показ ушедшего — с первого старта этого кода, прошлое — нет
W_SHOW_UNSURE = "исход неизвестен, проверьте телефон"


def follow_out(out):
    """Ответ Model.followup → ("text", текст) | ("skip", почему) | ("fail", None). Строка — текст;
    словарь {skip: True, why} — модель сказала «не нужно»; None, пусто и прочее — модель не дала ответа."""
    if isinstance(out, dict):
        if out.get("skip"):
            return "skip", str(out.get("why") or "")[:200]
        out = out.get("text")
    if isinstance(out, str) and out.strip():
        return "text", out
    return "fail", None


def lesson_admins_of(raw):
    """Настройка службы WA_AGENT_LESSON_ADMINS → (id Telegram, слова). Значение — id через запятую;
    пусто — владелец; хоть одно значение не число — владелец (битая настройка права не расширяет)."""
    s = str(raw or "").strip()
    if not s:
        return LESSON_OWNER_IDS, "владелец (WA_AGENT_LESSON_ADMINS не задан)"
    out = [p for p in s.replace(" ", ",").split(",") if p]
    if not out or any(not p.isdigit() for p in out):
        return LESSON_OWNER_IDS, "настройка WA_AGENT_LESSON_ADMINS битая — только владелец"
    return frozenset(int(p) for p in out), "список WA_AGENT_LESSON_ADMINS (%d id)" % len(set(out))


def active_lessons(db):
    """Действующие уроки → [(номер, было, стало, причина)] по номеру. Одно правило для ядра и адаптера
    модели: кандидат и откатанный в промпт не идут."""
    return db.execute("SELECT id, was_text, now_text, reason FROM lessons WHERE state=? ORDER BY id",
                      (LESSON_ACTIVE,)).fetchall()


def greet_fps(raw):
    """Настройка службы (WA_AGENT_GREET_SHA256) → (отпечатки, слова). Значение — hex sha256 текста
    приветствия или его начало от GREET_FP_MIN знаков, несколько — через запятую; текста в настройке
    нет. Пусто — признака нет; хоть одно значение битое — признака нет целиком: любое эхо ставит
    паузу, как до WAGREETECHO0210."""
    s = str(raw or "").strip().lower()
    if not s:
        return (), "настройки нет — любое эхо ставит паузу"
    out = [p for p in s.replace(" ", ",").split(",") if p]
    if not out or any(not GREET_FP_MIN <= len(p) <= 64 or p.strip("0123456789abcdef") for p in out):
        return (), "настройка битая — признака нет, любое эхо ставит паузу"
    return tuple(out), "отпечаток %s" % ", ".join(p[:10] for p in out)


def greet_hit(text, fps):
    """Отпечаток текста эха совпал с настройкой: sha256 текста начинается с одного из `greet_fps`.
    Одно правило для ядра и ожидания `wa_watch` (WACHAINFIX0210). Отпечатков нет — не совпал."""
    if not fps or not isinstance(text, str) or not text:
        return False
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return any(h.startswith(g) for g in fps)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS clients (
    number      TEXT PRIMARY KEY,
    last_in_id  INTEGER NOT NULL DEFAULT 0,   -- последнее живое входящее (id строки очереди)
    last_in_ts  REAL    NOT NULL DEFAULT 0,   -- его ts_queued (часы сервера)
    done_upto   INTEGER NOT NULL DEFAULT 0,   -- входящие до этого id закрыты решением/человеком
    paused      INTEGER NOT NULL DEFAULT 0,
    pause_no    INTEGER NOT NULL DEFAULT 0,   -- номер паузы: «Продолжить» снимает ровно свою
    paused_at   REAL,
    pause_row   INTEGER,                      -- id строки эха, поставившей паузу
    resumed_by  TEXT,
    resumed_at  REAL,
    next_try    REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      TEXT    NOT NULL,
    state       TEXT    NOT NULL,
    ver         INTEGER NOT NULL DEFAULT 1,
    text        TEXT    NOT NULL,
    upto_id     INTEGER NOT NULL,             -- последнее входящее, на которое отвечает черновик
    created_at  REAL    NOT NULL,
    decided_by  TEXT,
    decided_at  REAL,
    reason      TEXT,
    wamid       TEXT,
    card_id     INTEGER,
    closed_at   REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_draft ON drafts(number)
    WHERE state IN ('pending', 'claimed', 'sending');
CREATE INDEX IF NOT EXISTS drafts_wamid ON drafts(wamid);
CREATE TABLE IF NOT EXISTS relay (
    msg_id  INTEGER PRIMARY KEY,                  -- сообщение человека в теме показа (id Telegram)
    number  TEXT    NOT NULL,
    state   TEXT    NOT NULL,                     -- sending ДО двери, потом sent | not_sent | unsure
    reason  TEXT,
    wamid   TEXT,
    who     TEXT,
    ts      REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS relay_edits (
    msg_id  INTEGER PRIMARY KEY,                  -- на правку этого сообщения темы ответ уже дан
    ts      REAL
);
CREATE TABLE IF NOT EXISTS outbox (
    wamid   TEXT PRIMARY KEY,                     -- ушедшее клиенту через API (эхом не возвращается)
    number  TEXT NOT NULL,
    ts      REAL NOT NULL,
    text    TEXT NOT NULL,
    via     TEXT NOT NULL                         -- «тема» | «агент»
);
CREATE INDEX IF NOT EXISTS outbox_number ON outbox(number);
CREATE TABLE IF NOT EXISTS autogreet (
    row_id  INTEGER PRIMARY KEY,                  -- строка очереди: эхо-автоприветствие (паузы не было)
    number  TEXT    NOT NULL,
    wamid   TEXT,
    ts_msg  REAL,                                 -- время сообщения: место строки в истории агента
    after   REAL,                                 -- секунд после «первого» входящего
    ts      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS autogreet_number ON autogreet(number);
CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,    -- номер урока
    state       TEXT    NOT NULL,                     -- candidate | active | rolled_back
    author      TEXT    NOT NULL,                     -- кто исправил: имя (id N)
    author_id   INTEGER,
    ts          REAL    NOT NULL,
    draft_id    INTEGER NOT NULL,                     -- источник: черновик и его версии
    ver_from    INTEGER NOT NULL,
    ver_to      INTEGER NOT NULL,
    was_text    TEXT    NOT NULL,                     -- было
    now_text    TEXT    NOT NULL,                     -- стало
    reason      TEXT,                                 -- причина или NULL
    decided_by  TEXT,                                 -- перевод в действующие: кто, когда
    decided_at  REAL,
    rolled_by   TEXT,                                 -- откат: кто, когда
    rolled_at   REAL,
    UNIQUE (draft_id, ver_to)
);
CREATE TABLE IF NOT EXISTS followups (
    number      TEXT    NOT NULL,
    anchor      REAL    NOT NULL,                     -- время нашего последнего сообщения: модель — раз на него
    ts          REAL    NOT NULL,
    outcome     TEXT    NOT NULL,                     -- drafted | not_needed
    draft_id    INTEGER,
    PRIMARY KEY (number, anchor)
);
CREATE TABLE IF NOT EXISTS card_out (
    draft_id     INTEGER NOT NULL,                    -- карточка = черновик + версия (WADRAFTSAFE0210)
    ver          INTEGER NOT NULL,
    state        TEXT    NOT NULL,                    -- wait → sending → delivered → decided
    tries        INTEGER NOT NULL DEFAULT 0,          -- попыток доставки
    next_at      REAL    NOT NULL DEFAULT 0,          -- следующая попытка (доставки или правки) не раньше
    message_id   INTEGER,                             -- карточка в «Агентах»: есть — доставлена
    chat_id      INTEGER,
    delivered_at REAL,
    decided_at   REAL,
    words        TEXT,                                -- исход на карточке
    edit         TEXT,                                -- правка исхода: wait | ok | gave_up | unconfirmed; NULL — нечего
    edit_tries   INTEGER NOT NULL DEFAULT 0,
    created_at   REAL    NOT NULL,
    lost         INTEGER NOT NULL DEFAULT 0,          -- попыток отправки с неизвестным ответом (WACARDDONEFIX0210)
    edit_unk     INTEGER NOT NULL DEFAULT 0,          -- попыток правки с неизвестным ответом
    PRIMARY KEY (draft_id, ver)
);
CREATE TABLE IF NOT EXISTS draft_tr (
    draft_id    INTEGER NOT NULL,                     -- перевод для сотрудника (WACARDQ0410): черновик и ВЕРСИЯ
    ver         INTEGER NOT NULL,
    a_sha       TEXT    NOT NULL,                     -- отпечаток текста этой версии: перевод привязан к нему
    q_ru        TEXT,                                 -- перевод вопроса клиента
    a_ru        TEXT,                                 -- перевод ответа этой версии
    ts          REAL    NOT NULL,
    PRIMARY KEY (draft_id, ver)
);
CREATE TABLE IF NOT EXISTS agent_show (
    skey        TEXT    PRIMARY KEY,                  -- «wamid|часть»; исход неизвестен — «?черновик|часть|попытка» (WAMIRROR0410)
    wamid       TEXT,
    part        TEXT    NOT NULL,                     -- text | pdf
    draft_id    INTEGER NOT NULL,
    ver         INTEGER,
    attempt     INTEGER NOT NULL DEFAULT 1,
    number      TEXT    NOT NULL,
    who         TEXT,                                 -- кто подтвердил
    outcome     TEXT    NOT NULL,                     -- sent | unsure; отказ строки не даёт
    body        TEXT,                                 -- текст ушедшей версии; PDF — имя файла
    at          REAL    NOT NULL,                     -- время исхода
    state       TEXT    NOT NULL,                     -- wait → sending → shown | gave_up
    tries       INTEGER NOT NULL DEFAULT 0,
    lost        INTEGER NOT NULL DEFAULT 0,           -- попыток с неизвестным ответом Telegram
    next_at     REAL    NOT NULL DEFAULT 0,
    msg_id      INTEGER,                              -- строка показа в теме клиента
    chat_id     INTEGER,
    shown_at    REAL
);
CREATE INDEX IF NOT EXISTS agent_show_wamid ON agent_show(wamid);
"""

# «Тема клиента → WhatsApp» (WARELAYTEXT0210): текст человека из темы форума показа уходит клиенту.
# Ключ — id сообщения Telegram (`relay`); ушедшее через API — в `outbox`: история агента видит его
# видом «мы» (wa_history.read_sent), эхо с тем же wamid паузы не ставит (`_our_wamid`).
VIA_TOPIC, VIA_AGENT = "тема", "агент"
RELAY_DUP = "dup"
W_CLOSED = "не отправлено: окно 24 ч закрыто — напишите клиенту с телефона"
W_WIN_UNKNOWN = ("не отправлено: окно 24 ч неизвестно — входящих клиента у нас не записано; "
                 "напишите клиенту с телефона")
W_DOOR_OFF = "не отправлено: отправка выключена (WA_SEND)"
W_DOOR_ERR = "не отправлено: ошибка двери — %s"
W_UNSURE = "не знаю, дошло ли — второй раз не шлю; проверьте переписку в телефоне"
# Медиа из темы (WARELAYMEDIA0210): отказ, который человек исправит сам (вид, формат, размер, подпись,
# файл не получен), — словами двери `topic_words`; клиенту в этих случаях не ушло ничего.
W_TOPIC = "не отправлено: %s — наружу ничего"


def relay_words(state, res):
    """Исход двери → слова для темы. Окно закрыто, окно неизвестно, дверь выключена, ошибка двери —
    разные слова: человек по строке видит, что делать."""
    if state == SENT:
        return "отправлено"
    if state == UNSURE:
        return W_UNSURE
    reason = str((res or {}).get("reason") or "")
    if (res or {}).get("door_off") or "WA_SEND" in reason:
        return W_DOOR_OFF
    if (res or {}).get("topic_words"):
        return W_TOPIC % str(res["topic_words"])[:300]
    if (res or {}).get("window") == "closed":
        return W_CLOSED
    if reason.startswith("окно неизвестно"):
        return W_WIN_UNKNOWN
    return W_DOOR_ERR % (reason[:150] or "причина не названа")

# «Нужен человек» (WAAGENTMODEL0210): причины кода и модели — JSON-список слов в drafts.handoff.
# Черновик с причинами «Отправить» не шлёт, пока человек не нажал «Исправить» (версия > 1).
HANDOFF_LOCK_WORDS = "нужен человек — сначала «Исправить»: «Отправить» откроется на исправленной версии"


def handoff_of(raw):
    """drafts.handoff → [слова]; NULL — [] (причин нет). Битая запись — None («не прочитано», не «причин
    нет»): замок `send_locked` и карточка считают такой черновик черновиком с причинами."""
    try:
        val = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return None
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    return None


UNREAD_REASON = "причины не прочитаны — решает человек"


def draft_out(out):
    """Ответ Model.draft → (текст | None, [причины]). Строка — прежний контракт без причин."""
    if isinstance(out, dict):
        hand = out.get("handoff") or []
        hand = [str(h).strip() for h in hand if str(h).strip()] if isinstance(hand, list) else []
        return out.get("text"), hand
    return out, []


# ── вопрос клиента и перевод на карточке (WACARDQ0410) ───────────────────────────────────
# Вопрос — блок последних реплик клиента, ушедший в модель (под маской), — хранится у черновика; язык вопроса —
# вердикт КОДА адаптера. Перевод для сотрудника хранится С ВЕРСИЕЙ и отпечатком её текста (`draft_tr`): у версии
# человека (правка) перевода нет — карточка говорит, к какой версии он. Клиенту уходит только drafts.text.

def text_sha(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def draft_card(out):
    """Ответ Model.draft → поля карточки {question, q_lang, q_ru, a_ru} | None (прежний контракт: строка, словарь
    без вопроса). Не строка — пусто; переводы режет адаптер, здесь только типы."""
    if not isinstance(out, dict) or not isinstance(out.get("question"), str):
        return None

    def s(key):
        v = out.get(key)
        return v.strip() if isinstance(v, str) else ""
    return {"question": out["question"], "q_lang": s("q_lang"), "q_ru": s("q_ru"), "a_ru": s("text_ru")}


def tr_pick(rows, ver, text):
    """Переводы черновика [(ver, a_sha, q_ru, a_ru)] → (q_ru, a_ru, None) для ЭТОЙ версии с ЭТИМ текстом, иначе
    (None, None, версия, к которой перевод есть | None — перевода нет вовсе)."""
    for r_ver, a_sha, q_ru, a_ru in rows:
        if r_ver == int(ver) and a_sha == text_sha(text):
            return q_ru or "", a_ru or "", None
    other = sorted(r[0] for r in rows)
    return None, None, (other[0] if other else None)


# ═══ интерфейсы рук (подделки — в тестах; настоящие — шаги 3–4 плана) ═══════════════════

class Model:
    """draft(number, upto_id) → текст черновика или None (модель не дала текста), либо словарь
    {text, handoff[слова причин «нужен человек»], …} (адаптер модели, WAAGENTMODEL0210)."""

    def draft(self, number, upto_id):
        raise NotImplementedError

    def followup(self, number, upto_id):
        """Напоминание притихшему (WAFOLLOWUP0210) → текст | {skip: True, why} («не нужно») | None (модель
        не дала ответа). Адаптера нет — None."""
        return None


class AnswerLost(Exception):
    """Вызов Telegram ушёл, ответа нет (сеть, таймаут): сообщение могло лечь. Руки поднимают его там, где «не знаю»
    нельзя сказать отказом (отправка карточки, WACARDDONEFIX0210); ядро считает такой исход «неизвестно»."""


class Telegram:
    """Группа согласования. Ничего не возвращает, кроме card → id сообщения карточки (или None — отказ) и
    card_done → True (легла) · False (отказ) · None (править нечего). Исключение рук — исход НЕИЗВЕСТЕН: вызов мог
    лечь (WACARDDONEFIX0210)."""

    def card(self, draft_id, ver, number, text):
        raise NotImplementedError

    def card_done(self, draft_id, card_id, words):
        raise NotImplementedError

    def ask_pause(self, number, pause_no, via=None):
        raise NotImplementedError

    # agent_line(number, line) → id сообщения темы · None — НЕ входит в интерфейс намеренно (WAMIRROR0410): строку
    # показа ушедшего агентом пишут только руки, у которых этот метод есть; рук нет — показа нет.

    def card_wait(self, draft_id, card_id, words, ver):
        """«Отправить» до срока ритма (WAHUMANPACE0210): на карточке «уйдёт в ЧЧ:ММ» и кнопка «Отменить».
        Рук нет — ничего."""
        return None

    def lesson_card(self, lesson_id):
        """Кандидат урока (WAAGENTLESSON0210): сообщение с было/стало и кнопкой «Сделать правилом».
        Рук нет — ничего."""
        return None

    def lesson_done(self, lesson_id, words, state):
        """Урок переведён или откатан: сообщение урока получает исход; у действующего — «Откатить».
        Рук нет — ничего."""
        return None


class Door:
    """send_text(to, text) → {"outcome": sent|not_sent|unknown, "reason": str, "wamid": str|None}.
    Контракт совпадает с `wa_send.send_text` (тот НИКОГДА не бросает и сам судит окно 24 ч)."""

    def send_text(self, to, text):
        raise NotImplementedError

    def send_media(self, to, media):
        """Медиа из темы (WARELAYMEDIA0210) — контракт `wa_send.send_media`. Двери без медиа — отказ."""
        return {"outcome": "not_sent", "reason": "дверь не умеет медиа", "wamid": None}


def media_text(media):
    """Медиа → текст записи `outbox`: подпись; у геоточки — название, адрес или координаты."""
    m = media or {}
    if m.get("kind") == "location":
        return " · ".join(str(x) for x in (m.get("name"), m.get("address")) if x) or \
            "%s, %s" % (m.get("latitude"), m.get("longitude"))
    return str(m.get("caption") or "")


# ═══ ядро ════════════════════════════════════════════════════════════════════════════════

PHUKET_OFFSET = 7 * 3600                  # Пхукет, UTC+7 круглый год; тест сверяет с wa_history.PHUKET_OFFSET


def hm_phuket(ts):
    """«ЧЧ:ММ» по Пхукету — ОДНА функция времени для слов, которые видят сотрудники: карточки, ответы на нажатия,
    сторож, напоминания, уроки (WADRAFTFIX0210; офис живёт по Пхукету, прежде здесь было UTC). Журнал службы
    пишет своё время сам и сюда не ходит."""
    return time.strftime("%H:%M", time.gmtime(float(ts) + PHUKET_OFFSET)) if ts else "—"


def _int_or_none(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def show_line(at, outcome, who, draft_id, ver, part, body):
    """Строка показа ушедшего агентом (WAMIRROR0410): время · «агент» · кто подтвердил · № черновика, версия ·
    часть; «неизвестно» — со словами «исход неизвестен, проверьте телефон»; ниже — текст (PDF — имя файла)."""
    name = str(who or "").split(" (id ")[0] or "—"
    head = "%s · агент · подтвердил %s · черновик №%d, версия %d · %s" % (
        hm_phuket(at), name, int(draft_id), int(ver or 1), "PDF" if part == PART_PDF else "текст")
    if outcome == UNSURE:
        head += " · " + W_SHOW_UNSURE
    return head + ":\n" + str(body or "")


class Core:
    def __init__(self, db_path, queue_path, model, tg, door, quiet=QUIET_DEFAULT,
                 clock=time.time, log=None, drafts=True, greet=(), pace=False, rand=random.random,
                 lessons=False, lesson_admins=None, followup=False):
        quiet = int(quiet)
        # WA_AGENT_FOLLOWUP (WAFOLLOWUP0210): выключен — притихших не ищем, модель о напоминании не зовётся
        self.followup = bool(followup)
        self._follow_last = None
        # WA_AGENT_LESSONS (WAAGENTLESSON0210): выключен — «Исправить» урока не пишет, перевода нет;
        # lesson_admins — id Telegram, кто вправе переводить и откатывать (по умолчанию владелец)
        self.lessons = bool(lessons)
        self.lesson_admins = frozenset(LESSON_OWNER_IDS if lesson_admins is None else lesson_admins)
        # WA_AGENT_PACE (WAHUMANPACE0210): выключен — «Отправить» шлёт сразу; rand — доля окна первого ответа
        self.pace = bool(pace)
        self.rand = rand
        # отпечатки текста автоприветствия (`greet_fps`); пусто — признака нет, любое эхо — пауза
        self.greet = tuple(greet or ())
        if not QUIET_MIN <= quiet <= QUIET_MAX:
            raise ValueError("пауза черновика %d с вне %d–%d с" % (quiet, QUIET_MIN, QUIET_MAX))
        self.quiet = quiet
        # WA_AGENT_DRAFTS (WAAGENTSVC0210): выключен — модель не зовётся, черновиков и пауз нет,
        # курсор идёт за очередью (`follow`). Решает служба; ядро по умолчанию прежнее.
        self.drafts = bool(drafts)
        self.queue_path = queue_path
        self.model, self.tg, self.door = model, tg, door
        self.clock = clock
        self.log = log or (lambda line: None)
        self.db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        self.db.executescript(_SCHEMA)
        if "handoff" not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
            self.db.execute("ALTER TABLE drafts ADD COLUMN handoff TEXT")
        if "kind" not in {r[1] for r in self.db.execute("PRAGMA table_info(outbox)")}:
            self.db.execute("ALTER TABLE outbox ADD COLUMN kind TEXT")   # вид медиа; NULL — текст
        if "due_at" not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
            self.db.execute("ALTER TABLE drafts ADD COLUMN due_at REAL")  # срок отправки по ритму; NULL — сразу
        if "kind" not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
            self.db.execute("ALTER TABLE drafts ADD COLUMN kind TEXT")    # «followup» — напоминание; NULL — ответ
        # версия контекста (WADRAFTSAFE0210): у клиента — счётчик событий беседы, у черновика — на момент черновика
        if "ctx" not in {r[1] for r in self.db.execute("PRAGMA table_info(clients)")}:
            self.db.execute("ALTER TABLE clients ADD COLUMN ctx INTEGER NOT NULL DEFAULT 0")
        if "ctx" not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
            self.db.execute("ALTER TABLE drafts ADD COLUMN ctx INTEGER")  # NULL — черновик старше версии контекста
        # вопрос клиента и язык вопроса (WACARDQ0410); NULL — черновик старше или напоминание: карточка прежняя
        for col in ("question", "q_lang"):
            if col not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
                self.db.execute("ALTER TABLE drafts ADD COLUMN %s TEXT" % col)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(card_out)")}
        for col in ("lost", "edit_unk"):                                  # очередь старше WACARDDONEFIX0210
            if col not in have:
                self.db.execute("ALTER TABLE card_out ADD COLUMN %s INTEGER NOT NULL DEFAULT 0" % col)
        # показ ушедшего агентом (WAMIRROR0410): с этой минуты; ушедшее раньше строки не получает
        self.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (SHOW_SINCE, repr(float(self.clock()))))
        self._startup()

    # ── база ──────────────────────────────────────────────────────────────────────────────

    def _startup(self):
        """sending → unsure (могло уйти — не повторяем); claimed → pending (двери не звали).
        Входящие под unsure закрыты: новый черновик на них звал бы ко второй отправке.
        scheduled не трогаем: срок в базе, такт отправит его один раз (WAHUMANPACE0210)."""
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, (SELECT MAX(upto_id) FROM drafts "
                        "WHERE drafts.number=clients.number AND state=?)) WHERE number IN "
                        "(SELECT number FROM drafts WHERE state=?)", (SENDING, SENDING))
        n1 = self.db.execute("UPDATE drafts SET state=?, reason=? WHERE state=?",
                             (UNSURE, "рестарт посреди отправки — могло уйти, не повторяем",
                              SENDING)).rowcount
        n2 = self.db.execute("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL "
                             "WHERE state=?", (PENDING, CLAIMED)).rowcount
        if n1 or n2:
            self.log("старт: sending→unsure %d, claimed→pending %d" % (n1, n2))
        n3 = self.db.execute("UPDATE relay SET state=?, reason=? WHERE state=?",
                             (UNSURE, "рестарт посреди отправки из темы — могло уйти, не повторяем",
                              SENDING)).rowcount
        if n3:
            self.log("старт: из темы sending→unsure %d" % n3)
        # карточки (WADRAFTSAFE0210): sending → wait — могла дойти, шлём снова (дубль безопасен: кнопки по
        # черновику и версии); ждущие черновики, которых очередь не знает, — доставлена, если card_id есть.
        # Ответ на ту попытку неизвестен — в `lost`, как исключение рук (WACARDDONEFIX0210)
        n4 = self.db.execute("UPDATE card_out SET state=?, next_at=0, lost=lost+1 WHERE state=?",
                             (CARD_WAIT, CARD_SENDING)).rowcount
        n5 = self.db.execute("INSERT OR IGNORE INTO card_out(draft_id, ver, state, message_id, delivered_at, "
                             "created_at) SELECT id, ver, CASE WHEN card_id IS NULL THEN ? ELSE ? END, card_id, "
                             "CASE WHEN card_id IS NULL THEN NULL ELSE created_at END, created_at FROM drafts "
                             "WHERE state=?", (CARD_WAIT, CARD_DELIVERED, PENDING)).rowcount
        if n4 or n5:
            self.log("старт: карточка sending→wait %d (ответ неизвестен — возможна вторая карточка), ждущих "
                     "черновиков взято в очередь доставки %d" % (n4, n5))
        # строка показа (WAMIRROR0410): рестарт посреди вызова — могла лечь; повтор тот же, попытка — в `lost`
        n6 = self.db.execute("UPDATE agent_show SET state=?, next_at=0, lost=lost+1 WHERE state=?",
                             (SHOW_WAIT, SHOW_SENDING)).rowcount
        if n6:
            self.log("старт: строка показа sending→wait %d (ответ неизвестен — возможна вторая строка)" % n6)

    def _queue(self):
        return sqlite3.connect("file:%s?mode=ro" % self.queue_path, uri=True, timeout=5)

    def _cursor(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
        return int(row[0]) if row else None

    def _set_cursor(self, value):
        self.db.execute("INSERT INTO meta(key, value) VALUES('cursor', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(value)),))

    def _client(self, number):
        self.db.execute("INSERT OR IGNORE INTO clients(number) VALUES(?)", (number,))
        return self.db.execute("SELECT last_in_id, last_in_ts, done_upto, paused, pause_no, next_try "
                               "FROM clients WHERE number=?", (number,)).fetchone()

    def _live_draft(self, number):
        return self.db.execute("SELECT id, state FROM drafts WHERE number=? AND state IN (?,?,?)",
                               (number,) + LIVE).fetchone()

    def _our_wamid(self, wamid):
        """Эхо нашей отправки через API (черновик или текст из темы) — не ответ с телефона."""
        return bool(wamid) and (
            self.db.execute("SELECT 1 FROM drafts WHERE wamid=?", (wamid,)).fetchone() is not None
            or self.db.execute("SELECT 1 FROM outbox WHERE wamid=?", (wamid,)).fetchone() is not None)

    def _sent_out(self, wamid, number, text, via, now, kind=None):
        """Ушедшее через API → `outbox`: история агента (видом «мы», медиа — видом и подписью) и
        опознание эха."""
        if wamid:
            self.db.execute("INSERT OR IGNORE INTO outbox(wamid, number, ts, text, via, kind) "
                            "VALUES(?,?,?,?,?,?)", (wamid, number, now, text, via, kind))

    def _close(self, draft_id, state, words, now, from_states=(PENDING,)):
        """Снять черновик условно: только из названных состояний. True — снят этим вызовом."""
        q = "UPDATE drafts SET state=?, reason=?, closed_at=? WHERE id=? AND state IN (%s)" % \
            ",".join("?" * len(from_states))
        n = self.db.execute(q, (state, words, now, draft_id) + tuple(from_states)).rowcount
        if n == 1:
            self.log("черновик %d → %s" % (draft_id, state))
            self._done(draft_id, words, now)
        return n == 1

    def _tg(self, method, *args):
        """Вызов рук без исключений наружу: упали — строка журнала и None. Так зовутся все руки, кроме отправки
        карточки и правки её исхода: тем исход нужен тремя словами (`_tg_out`)."""
        return self._tg_out(method, *args)[1]

    def _tg_out(self, method, *args):
        """→ (True, ответ рук) · (None, None): руки упали (исключение, таймаут, ответ потерян) — исход НЕИЗВЕСТЕН,
        вызов мог лечь (WACARDDONEFIX0210). None рук «по контракту» и None от падения здесь различимы."""
        try:
            return True, getattr(self.tg, method)(*args)
        except Exception as e:                                       # noqa: BLE001
            self.log("telegram %s упал: %s" % (method, type(e).__name__))
            return None, None

    # ── доставка карточек (WADRAFTSAFE0210) ───────────────────────────────────────────────

    def _card_new(self, draft_id, ver, now):
        """Карточка версии ver — в очередь доставки и первая попытка сразу. → message_id | None."""
        self.db.execute("INSERT OR IGNORE INTO card_out(draft_id, ver, state, created_at) VALUES(?,?,?,?)",
                        (draft_id, int(ver), CARD_WAIT, now))
        return self._card_try(draft_id, int(ver), now)

    def _card_try(self, draft_id, ver, now):
        """Одна попытка доставки. Черновик ждёт с этой версией — `sending` ДО вызова Telegram, потом доставлена
        (message_id, chat_id, время) или снова ждёт с паузой CARD_RETRY. Черновик решён или исправлен до
        доставки — карточка не шлётся, она решена недоставленной. → message_id | None.
        Руки упали после вызова (WACARDDONEFIX0210) — НЕ отказ: ответ неизвестен, карточка могла лечь. Повтор тот
        же, но попытка ложится в `lost` и в сводку: возможна вторая карточка, единственность не обещается."""
        row = self.db.execute("SELECT number, state, ver, text FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[1] != PENDING or row[2] != ver:
            self.db.execute("UPDATE card_out SET state=?, decided_at=?, words=? WHERE draft_id=? AND ver=? "
                            "AND state IN (?,?)", (CARD_DECIDED, now, "решён до доставки: %s" % (
                                row[1] if row and row[2] == ver else "версия сменилась" if row else "черновика нет"),
                                draft_id, ver, CARD_WAIT, CARD_SENDING))
            return None
        if self.db.execute("UPDATE card_out SET state=?, tries=tries+1 WHERE draft_id=? AND ver=? AND state=?",
                           (CARD_SENDING, draft_id, ver, CARD_WAIT)).rowcount != 1:
            return None
        got, res = self._tg_out("card", draft_id, ver, row[0], row[3])
        mid = _int_or_none(res)
        if mid is not None:
            self.db.execute("UPDATE card_out SET state=?, message_id=?, chat_id=?, delivered_at=? WHERE draft_id=? "
                            "AND ver=? AND state=?", (CARD_DELIVERED, mid, _int_or_none(getattr(self.tg, "chat", None)),
                                                      now, draft_id, ver, CARD_SENDING))
            self.db.execute("UPDATE drafts SET card_id=? WHERE id=? AND ver=?", (mid, draft_id, ver))
            return mid
        tries = self.db.execute("SELECT tries FROM card_out WHERE draft_id=? AND ver=?", (draft_id, ver)).fetchone()[0]
        pause = CARD_RETRY[min(tries, len(CARD_RETRY)) - 1]
        lost = 0 if got else 1
        self.db.execute("UPDATE card_out SET state=?, next_at=?, lost=lost+? WHERE draft_id=? AND ver=? AND state=?",
                        (CARD_WAIT, now + pause, lost, draft_id, ver, CARD_SENDING))
        if lost:
            self.log("карточка черновика %d версия %d: ответ Telegram неизвестен (попытка %d) — могла лечь; повтор "
                     "через %d с, возможна вторая карточка" % (draft_id, ver, tries, pause))
        else:
            self.log("карточка черновика %d версия %d не доставлена (попытка %d) — повтор через %d с"
                     % (draft_id, ver, tries, pause))
        return None

    def _done(self, draft_id, words, now):
        """Исход черновика — на карточку его текущей версии."""
        row = self.db.execute("SELECT ver, card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if row:
            self._card_close(draft_id, row[0], words, now, row[1])
        self.show_agent(now)                  # исход ушедшего агентом — строкой в тему клиента (WAMIRROR0410)

    # ── строка показа ушедшего агентом (WAMIRROR0410) ─────────────────────────────────────

    def _show_since(self):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (SHOW_SINCE,)).fetchone()
        try:
            return float(row[0]) if row else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _show_put(self, wamid, part, draft_id, ver, attempt, number, who, outcome, body, at):
        """Итог одной части → строка `agent_show` по ключу «wamid|часть» (неизвестно — «?черновик|часть|попытка»).
        Ключ уже есть — ничего: повтор и рестарт второй строки не дают. → True — заведена этим вызовом."""
        skey = ("%s|%s" % (wamid, part)) if (outcome == SENT and wamid) else \
            "?%d|%s|%d" % (int(draft_id), part, int(attempt or 1))
        return self.db.execute("INSERT OR IGNORE INTO agent_show(skey, wamid, part, draft_id, ver, attempt, number, who, "
                               "outcome, body, at, state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (skey, wamid if outcome == SENT else None, part, int(draft_id), ver, int(attempt or 1),
                                number, who, outcome, body, at, SHOW_WAIT)).rowcount == 1

    def _show_scan(self):
        """Исходы частей, ушедших агентом после `show_since`, → строки `agent_show`. Текст — `drafts` (sent · unsure,
        в том числе unsure рестарта); PDF — `pdf_parts` (WAPARTSEND0410), если таблица есть. Отказ строки не даёт."""
        since = self._show_since()
        rows = self.db.execute(
            "SELECT d.id, d.ver, d.number, d.state, d.wamid, d.decided_by, d.text, "
            "COALESCE(d.closed_at, d.decided_at, d.created_at) FROM drafts d WHERE d.state IN (?,?) "
            "AND COALESCE(d.closed_at, d.decided_at, d.created_at) >= ? AND NOT EXISTS "
            "(SELECT 1 FROM agent_show s WHERE s.draft_id=d.id AND s.part=?)",
            (SENT, UNSURE, since, PART_TEXT)).fetchall()
        for did, ver, number, state, wamid, who, text, at in rows:
            self._show_put(wamid, PART_TEXT, did, ver, 1, number, who, state, text, at)
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pdf_parts'").fetchone():
            return
        rows = self.db.execute(
            "SELECT p.draft_id, d.ver, d.number, p.state, p.wamid, p.who, p.attempt, COALESCE(p.sending_at, p.at) "
            "FROM pdf_parts p JOIN drafts d ON d.id=p.draft_id WHERE p.state IN (?,?) "
            "AND COALESCE(p.sending_at, p.at, 0) >= ?", (SENT, UNSURE, since)).fetchall()
        for did, ver, number, state, wamid, who, attempt, at in rows:
            name = None
            try:
                got = self.db.execute("SELECT name FROM attach WHERE draft_id=?", (did,)).fetchone()
                name = got[0] if got else None
            except sqlite3.Error:
                pass
            self._show_put(wamid, PART_PDF, did, ver, attempt, number, who, state,
                           "📄 " + (name or "PDF договора"), at)

    def show_agent(self, now=None):
        """Строки показа ушедшего агентом: новые исходы — в `agent_show`, ждущие — рукам (`agent_line`).
        Рук без `agent_line` нет — ничего. → число строк, легших этим вызовом."""
        if not hasattr(self.tg, "agent_line"):
            return 0
        now = self.clock() if now is None else now
        self._show_scan()
        rows = self.db.execute("SELECT skey, number, at, outcome, who, draft_id, ver, part, body FROM agent_show "
                               "WHERE state=? AND next_at<=? ORDER BY at, draft_id, part DESC",
                               (SHOW_WAIT, now)).fetchall()
        shown = 0
        for skey, number, at, outcome, who, did, ver, part, body in rows:
            if self.db.execute("UPDATE agent_show SET state=?, tries=tries+1 WHERE skey=? AND state=?",
                               (SHOW_SENDING, skey, SHOW_WAIT)).rowcount != 1:
                continue
            got, res = self._tg_out("agent_line", number, show_line(at, outcome, who, did, ver, part, body))
            mid = _int_or_none(res)
            if mid is not None:
                self.db.execute("UPDATE agent_show SET state=?, msg_id=?, chat_id=?, shown_at=? WHERE skey=? AND state=?",
                                (SHOW_SHOWN, mid, _int_or_none(getattr(self.tg, "show_chat", None)), now, skey,
                                 SHOW_SENDING))
                self.log("показ: черновик %d, часть %s, %s → строка %d" % (did, part, outcome, mid))
                shown += 1
                continue
            tries = self.db.execute("SELECT tries FROM agent_show WHERE skey=?", (skey,)).fetchone()[0]
            lost = 0 if got else 1
            if tries >= SHOW_MAX:
                self.db.execute("UPDATE agent_show SET state=?, lost=lost+? WHERE skey=? AND state=?",
                                (SHOW_GAVE_UP, lost, skey, SHOW_SENDING))
                self.log("показ: черновик %d, часть %s — строка не легла за %d попыток, больше не шлём"
                         % (did, part, tries))
                continue
            pause = CARD_RETRY[min(tries, len(CARD_RETRY)) - 1]
            self.db.execute("UPDATE agent_show SET state=?, next_at=?, lost=lost+? WHERE skey=? AND state=?",
                            (SHOW_WAIT, now + pause, lost, skey, SHOW_SENDING))
            self.log("показ: черновик %d, часть %s — строка %s (попытка %d), повтор через %d с" % (
                did, part, "без ответа Telegram — могла лечь, возможна вторая" if lost else "не легла", tries, pause))
        return shown

    def show_counts(self):
        """Строки показа по состояниям — числа для сводки и проверок (WAMIRROR0410)."""
        return dict(self.db.execute("SELECT state, COUNT(*) FROM agent_show GROUP BY state").fetchall())

    def _card_close(self, draft_id, ver, words, now, card_id=None):
        """Карточка решена: исход словами, кнопки сняты. Доставлена — правка `card_done` (Telegram отказал или ответ
        неизвестен — повтор в `deliver_cards`); не доставлена — решена недоставленной, править нечего. Карточка вне очереди
        (запись старше неё) — прежний путь, один вызов без повтора."""
        row = self.db.execute("SELECT message_id FROM card_out WHERE draft_id=? AND ver=?",
                              (draft_id, int(ver))).fetchone()
        if row is None:
            self._tg("card_done", draft_id, card_id, words)
            return
        self.db.execute("UPDATE card_out SET state=?, decided_at=COALESCE(decided_at, ?), words=?, edit=?, "
                        "edit_tries=0, edit_unk=0, next_at=0 WHERE draft_id=? AND ver=?",
                        (CARD_DECIDED, now, words, EDIT_WAIT if row[0] else None, draft_id, int(ver)))
        if row[0]:
            self._card_edit(draft_id, int(ver), row[0], words, now)

    def _card_edit(self, draft_id, ver, mid, words, now):
        """Одна правка исхода, три исхода (WACARDDONEFIX0210). `card_done` → True — легла (ok); None по контракту —
        править нечего (ok, как раньше); False — Telegram отказал. Руки упали (исключение, таймаут) — ответ
        НЕИЗВЕСТЕН, правка могла лечь: не ok. Отказ и «неизвестно» — повтор с паузой, вместе не больше EDIT_MAX;
        за пределом — gave_up, если все ответы были отказами, и unconfirmed, если хоть один был неизвестен."""
        got, res = self._tg_out("card_done", draft_id, mid, words)
        if got and res is not False:
            self.db.execute("UPDATE card_out SET edit=? WHERE draft_id=? AND ver=?", (EDIT_OK, draft_id, ver))
            return True
        unk = 0 if got else 1
        self.db.execute("UPDATE card_out SET edit_tries=edit_tries+1, edit_unk=edit_unk+? WHERE draft_id=? AND ver=?",
                        (unk, draft_id, ver))
        n, u = self.db.execute("SELECT edit_tries, edit_unk FROM card_out WHERE draft_id=? AND ver=?",
                               (draft_id, ver)).fetchone()
        if n >= EDIT_MAX:
            self.db.execute("UPDATE card_out SET edit=? WHERE draft_id=? AND ver=?",
                            (EDIT_UNCONFIRMED if u else EDIT_GAVE_UP, draft_id, ver))
            if u:
                self.log("карточка черновика %d версия %d: исход не подтверждён за %d попыток (ответ Telegram "
                         "неизвестен %d раз) — мог лечь; не лёг — кнопки живы, нажатие ответит «уже решено»"
                         % (draft_id, ver, n, u))
            else:
                self.log("карточка черновика %d версия %d: исход не лёг за %d попыток — кнопки на ней живы, нажатие "
                         "ответит «уже решено»" % (draft_id, ver, n))
            return False
        pause = CARD_RETRY[min(n, len(CARD_RETRY)) - 1]
        self.db.execute("UPDATE card_out SET next_at=? WHERE draft_id=? AND ver=?", (now + pause, draft_id, ver))
        self.log("карточка черновика %d версия %d: исход %s (попытка %d) — повтор через %d с"
                 % (draft_id, ver, "не подтверждён — ответ Telegram неизвестен" if unk else "не лёг", n, pause))
        return False

    def deliver_cards(self, now):
        """Такт очереди карточек: ждущие доставки, чей срок настал, и правки исхода, которые Telegram отказал или
        чей ответ неизвестен (WACARDDONEFIX0210). → число доставленных этим тактом."""
        got = 0
        for did, ver in self.db.execute("SELECT draft_id, ver FROM card_out WHERE state=? AND next_at<=? "
                                        "ORDER BY next_at, draft_id", (CARD_WAIT, now)).fetchall():
            if self._card_try(did, ver, now) is not None:
                got += 1
        for did, ver, mid, words in self.db.execute(
                "SELECT draft_id, ver, message_id, words FROM card_out WHERE state=? AND edit=? AND next_at<=? "
                "ORDER BY next_at, draft_id", (CARD_DECIDED, EDIT_WAIT, now)).fetchall():
            self._card_edit(did, ver, mid, words, now)
        return got

    def card_counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM card_out GROUP BY state").fetchall())

    def undelivered(self):
        """Ждущие черновики без доставленной карточки своей версии — число для сводки службы."""
        return self.db.execute("SELECT COUNT(*) FROM drafts d WHERE d.state=? AND NOT EXISTS (SELECT 1 FROM "
                               "card_out c WHERE c.draft_id=d.id AND c.ver=d.ver AND c.message_id IS NOT NULL)",
                               (PENDING,)).fetchone()[0]

    def card_unknown(self):
        """«Неизвестно» отдельно (WACARDDONEFIX0210) → (карточек, у которых ответ на отправку терялся — возможна
        вторая карточка; правок исхода без подтверждения с неизвестным ответом — повтор идёт или unconfirmed)."""
        lost = self.db.execute("SELECT COUNT(*) FROM card_out WHERE lost>0").fetchone()[0]
        unk = self.db.execute("SELECT COUNT(*) FROM card_out WHERE edit_unk>0 AND edit IN (?,?)",
                              (EDIT_WAIT, EDIT_UNCONFIRMED)).fetchone()[0]
        return lost, unk

    # ── версия контекста (WADRAFTSAFE0210) ────────────────────────────────────────────────

    def _bump(self, number):
        """Событие беседы (живое входящее, ответ с телефона, текст из темы, «Продолжить») — версия контекста +1."""
        self.db.execute("UPDATE clients SET ctx=ctx+1 WHERE number=?", (number,))

    def _withdraw(self, number, state, words, now, before=None):
        """Снять отложенные ритмом черновики клиента (scheduled) — одобряли ответ на прежнюю беседу.
        before — снимать только отвечающие на строки раньше этой."""
        q, args = "SELECT id FROM drafts WHERE number=? AND state=?", (number, SCHEDULED)
        if before is not None:
            q, args = q + " AND upto_id<?", args + (int(before),)
        for (sid,) in self.db.execute(q, args).fetchall():
            self._close(sid, state, words, now, from_states=(SCHEDULED,))

    def _outdated(self, draft_id):
        """«Отправить» привязано к последнему сообщению клиента и версии контекста: после черновика клиент
        написал (`last_in_id` > `upto_id`) или контекст сменился (`clients.ctx` ≠ `drafts.ctx`) → слова;
        иначе None. Черновик старше версии контекста (ctx NULL) сверяется только по сообщению."""
        row = self.db.execute("SELECT d.upto_id, d.ctx, c.last_in_id, c.ctx FROM drafts d JOIN clients c "
                              "ON c.number=d.number WHERE d.id=?", (draft_id,)).fetchone()
        if not row:
            return None
        upto, dctx, last_in, cctx = row
        if last_in > upto:
            return WROTE_WORDS % last_in
        if dctx is not None and dctx != cctx:
            return "беседа сменилась после черновика (контекст %d → %d)" % (dctx, cctx)
        return None

    # ── вид строки очереди ────────────────────────────────────────────────────────────────

    @staticmethod
    def _live_kind(msg_type, echo, history):
        """inbound | echo | None. Живое — только history=0; квитанции и прочее — None."""
        kind = wa_kind.kind_of(msg_type, echo, history)
        if wa_kind._flag(history) is not False:
            return None
        if kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_ECHO):
            return kind
        return None

    # ── пауза ─────────────────────────────────────────────────────────────────────────────

    def _pause(self, number, row_id, now, via=None):
        """Человек ответил с телефона (или написал в теме, via): клиент на паузе. Вопрос в группу —
        один на паузу."""
        n = self.db.execute("UPDATE clients SET paused=1, pause_no=pause_no+1, paused_at=?, "
                            "pause_row=? WHERE number=? AND paused=0", (now, row_id, number)).rowcount
        if n == 1:
            no = self.db.execute("SELECT pause_no FROM clients WHERE number=?", (number,)).fetchone()[0]
            if via:
                self.log("клиент на паузе (%s, пауза %d)" % (via, no))
                self._tg("ask_pause", number, no, via)
            else:
                self.log("клиент на паузе (строка эха %d, пауза %d)" % (row_id, no))
                self._tg("ask_pause", number, no)

    def human_wrote(self, number, now):
        """Человек написал клиенту в теме показа — вмешательство (запись 30.09.2026-7 п.4): ждущий
        черновик снят, входящие до этого закрыты, клиент на паузе до «Продолжить»."""
        self._client(number)
        self._bump(number)
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?", (number,))
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], SUPERSEDED, "снят: человек написал клиенту в теме %s" % hm_phuket(now), now)
        self._withdraw(number, SUPERSEDED, "снят до срока: человек написал клиенту в теме %s — отложенное не уходит"
                       % hm_phuket(now), now)
        self._pause(number, None, now, via="написал в теме")

    def relay(self, msg_id, number, text, who, now=None, media=None):
        """Текст человека из темы клиента → клиенту в WhatsApp (WARELAYTEXT0210). Ключ — id сообщения
        Telegram: одно сообщение темы — не больше одной отправки; `sending` пишется ДО двери, рестарт
        не повторяет (`_startup`). → {"outcome": sent|not_sent|unknown|dup, "words", "wamid"}.
        media (WARELAYMEDIA0210) — медиа этого сообщения (`wa_send.send_media`): тот же ключ, та же
        пауза, тот же исход; в `outbox` — вид и подпись. Сверх: dropped_caption — подпись не ушла."""
        now = self.clock() if now is None else now
        mid = int(msg_id)
        if self.db.execute("INSERT OR IGNORE INTO relay(msg_id, number, state, who, ts) VALUES(?,?,?,?,?)",
                           (mid, number, SENDING, who, now)).rowcount != 1:
            row = self.db.execute("SELECT state FROM relay WHERE msg_id=?", (mid,)).fetchone()
            self.log("тема: сообщение %d уже разобрано (%s) — второй раз не шлём" % (mid, row[0] if row else "?"))
            return {"outcome": RELAY_DUP, "words": "", "wamid": None}
        self.human_wrote(number, now)
        if not self._door_open():
            res = {"outcome": "not_sent", "reason": "отправка выключена (WA_SEND)", "door_off": True}
        else:
            try:
                if media is not None:
                    res = self.door.send_media(number, media) or {}
                else:
                    res = self.door.send_text(number, text) or {}
            except Exception as e:                                   # noqa: BLE001
                res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = _DOOR_STATE.get(res.get("outcome"), UNSURE)
        wamid = res.get("wamid") if state == SENT else None
        self.db.execute("UPDATE relay SET state=?, reason=?, wamid=? WHERE msg_id=? AND state=?",
                        (state, str(res.get("reason") or "")[:300], wamid, mid, SENDING))
        kind = ((media or {}).get("label") or (media or {}).get("kind")) if media is not None else None
        if state == SENT:
            self._sent_out(wamid, number, media_text(media) if media is not None else text, VIA_TOPIC, now,
                           kind=kind)
        self.log("тема: сообщение %d%s → %s" % (mid, " (%s)" % kind if kind else "", state))
        return {"outcome": {SENT: "sent", NOT_SENT: "not_sent"}.get(state, "unknown"),
                "words": relay_words(state, res), "wamid": wamid,
                "dropped_caption": state == SENT and bool(res.get("dropped_caption"))}

    def edit_once(self, msg_id):
        """Правка сообщения темы клиенту не уходит; ответ об этом — один на сообщение. True — ответить."""
        return self.db.execute("INSERT OR IGNORE INTO relay_edits(msg_id, ts) VALUES(?,?)",
                               (int(msg_id), self.clock())).rowcount == 1

    def resume(self, number, pause_no, who, now=None):
        """«Продолжить». Снимает ровно свою паузу; второй нажавший получает «уже продолжено»."""
        now = self.clock() if now is None else now
        n = self.db.execute("UPDATE clients SET paused=0, resumed_by=?, resumed_at=? "
                            "WHERE number=? AND paused=1 AND pause_no=?",
                            (who, now, number, int(pause_no))).rowcount
        if n == 1:
            self._bump(number)
            self.log("пауза %s снята нажатием" % pause_no)
            return {"ok": True, "words": "продолжаем"}
        row = self.db.execute("SELECT resumed_by, resumed_at FROM clients WHERE number=?",
                              (number,)).fetchone()
        by, at = (row or (None, None))
        return {"ok": False, "words": "уже продолжено: %s, %s" % (by or "—", hm_phuket(at))}

    # ── такт ──────────────────────────────────────────────────────────────────────────────

    def tick(self, now=None):
        now = self.clock() if now is None else now
        self.send_due(now)                    # отложенное уходит в срок и при выключенных черновиках
        self.show_agent(now)                  # строки показа: новые исходы и повтор не легших (WAMIRROR0410)
        if not self.drafts:
            self.follow()
            self.deliver_cards(now)
            return []
        self.scan(now)
        made = self.make_drafts(now)
        if self.followup:
            made += self.make_followups(now)
        self.deliver_cards(now)               # повтор карточек, которые Telegram не принял (WADRAFTSAFE0210)
        return made

    def follow(self):
        """Черновики выключены: курсор встаёт на MAX(id) без разбора строк, ждущие входящие закрыты
        без черновика. Включение не поднимет черновиков на переписку выключенного времени — то же
        правило, что у первого старта. Живой черновик не трогается: его «Отправить» перепроверит
        очередь (`press` → `_fresh`)."""
        q = self._queue()
        try:
            top = q.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
        finally:
            q.close()
        if self._cursor() != top:
            self._set_cursor(top)
        self.db.execute("UPDATE clients SET done_upto=last_in_id WHERE done_upto < last_in_id")
        return top

    def scan(self, now):
        """Новые строки очереди после курсора. Первый старт — курсор на MAX(id), без разбора."""
        cur = self._cursor()
        q = self._queue()                     # закрываем сами: `with` у sqlite3 соединение не закрывает
        try:
            if cur is None:
                top = q.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
                self._set_cursor(top)
                self.log("курсор встал на %d (первый старт)" % top)
                return 0
            rows = q.execute("SELECT id, from_number, msg_type, echo, history, wamid, ts_queued, text, ts_msg "
                             "FROM wa_inbox WHERE id > ? ORDER BY id LIMIT ?",
                             (cur, SCAN_LIMIT)).fetchall()
        finally:
            q.close()
        for rid, number, msg_type, echo, history, wamid, ts_q, text, ts_m in rows:
            kind = self._live_kind(msg_type, echo, history)
            if kind and number:
                if kind == wa_kind.KIND_INBOUND:
                    self._on_inbound(number, rid, ts_q, now)
                elif not self._our_wamid(wamid):
                    self._on_echo(number, rid, now, text=text, ts_msg=ts_m, wamid=wamid)
            cur = rid
        self._set_cursor(cur)
        return len(rows)

    def _on_inbound(self, number, rid, ts_q, now):
        self._client(number)
        self.db.execute("UPDATE clients SET last_in_id=MAX(last_in_id, ?), last_in_ts=MAX(last_in_ts, ?) "
                        "WHERE number=?", (rid, float(ts_q or now), number))
        self._bump(number)
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], STALE, FOLLOW_STALE_WORDS % rid if self.draft_kind(live[0]) == KIND_FOLLOW
                        else "снят: " + WROTE_WORDS % rid + " — черновик пересобирается", now)
        # отложенное ритмом — тоже (WADRAFTSAFE0210): одобряли ответ, а клиент уже написал дальше
        self._withdraw(number, STALE, "снят до срока: " + WROTE_WORDS % rid + " — отложенное не уходит, черновик "
                       "пересобирается", now, before=rid)

    def _after_first(self, number, rid, ts_msg):
        """Секунд от «первого» входящего клиента до эха, если оно было не раньше GREET_SEC до эха; иначе
        None. «Первое» — живое входящее, перед которым у номера GREET_SILENCE ни одной строки в обе
        стороны (история тоже; квитанции не в счёт). Время — ts_msg: на нём стоит замер."""
        try:
            t = float(ts_msg)
        except (TypeError, ValueError):
            return None
        q = self._queue()                     # закрываем сами: `with` у sqlite3 соединение не закрывает
        try:
            cands = q.execute("SELECT id, msg_type, echo, history, ts_msg FROM wa_inbox WHERE from_number=? "
                              "AND id < ? AND ts_msg >= ? AND ts_msg <= ? ORDER BY id",
                              (number, rid, t - GREET_SEC, t)).fetchall()
            for cid, msg_type, echo, history, c_ts in cands:
                if self._live_kind(msg_type, echo, history) != wa_kind.KIND_INBOUND:
                    continue
                before = q.execute("SELECT COUNT(*) FROM wa_inbox WHERE from_number=? AND id<>? "
                                   "AND (msg_type IS NULL OR msg_type<>?) AND ts_msg>=? AND ts_msg<?",
                                   (number, cid, wa_kind.RECEIPT_TYPE, c_ts - GREET_SILENCE, c_ts)).fetchone()[0]
                if before == 0:
                    return t - c_ts
        finally:
            q.close()
        return None

    def _greet(self, number, rid, text, ts_msg):
        """Эхо — автоприветствие? → (секунд после «первого» входящего | None, слова для журнала).
        Нужны ОБА признака. Время меряется всегда: сменили текст приветствия — журнал покажет
        «отпечаток не совпал; 3 с после первого входящего», а не молчание."""
        after = self._after_first(number, rid, ts_msg)
        t_words = ("первого входящего за %d с до эха нет" % GREET_SEC if after is None
                   else "%d с после первого входящего" % after)
        if not self.greet:
            return None, "отпечатка приветствия в настройке нет; " + t_words
        if not greet_hit(text, self.greet):
            return None, "отпечаток не совпал; " + t_words
        return after, "отпечаток совпал; " + t_words

    def _greeted(self, rid):
        return self.db.execute("SELECT 1 FROM autogreet WHERE row_id=?", (rid,)).fetchone() is not None

    def _on_echo(self, number, rid, now, text=None, ts_msg=None, wamid=None):
        after, words = self._greet(number, rid, text, ts_msg)
        if after is not None:
            # автоприветствие — не ответ человека: паузы нет, черновик жив, done_upto не трогаем
            self.db.execute("INSERT OR IGNORE INTO autogreet(row_id, number, wamid, ts_msg, after, ts) "
                            "VALUES(?,?,?,?,?,?)", (rid, number, wamid, ts_msg, after, now))
            self.log("эхо строки %d: автоприветствие (%s) — паузы нет, черновик жив, первый вопрос открыт"
                     % (rid, words))
            return
        self.log("эхо строки %d: не автоприветствие (%s) — пауза" % (rid, words))
        self._client(number)
        self._bump(number)
        # человек ответил на всё, что было до его эха: эти входящие закрыты
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?", (number,))
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], SUPERSEDED, "снят: ответили с телефона %s" % hm_phuket(now), now)
        self._withdraw(number, SUPERSEDED, "снят до срока: ответили с телефона %s — отложенное не уходит"
                       % hm_phuket(now), now, before=rid)
        self._pause(number, rid, now)

    def make_drafts(self, now):
        made = []
        due = self.db.execute("SELECT number, last_in_id, ctx FROM clients WHERE paused=0 "
                              "AND last_in_id > done_upto AND last_in_ts <= ? AND next_try <= ?",
                              (now - self.quiet, now)).fetchall()
        for number, upto, ctx in due:
            if self._live_draft(number):
                continue
            try:
                out = self.model.draft(number, upto)
                text, hand = draft_out(out)
                card = draft_card(out)                               # вопрос и перевод для карточки (WACARDQ0410)
            except Exception as e:                                   # noqa: BLE001
                self.log("модель упала: %s" % type(e).__name__)
                text, hand, card = None, [], None
            if not isinstance(text, str) or not text.strip():
                self.db.execute("UPDATE clients SET next_try=? WHERE number=?",
                                (now + MODEL_RETRY_SEC, number))
                continue
            # пока думала модель, клиент мог написать ещё или человек ответить — не пишем
            if self._fresh(number, upto):
                continue
            cur = self.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, handoff, ctx, "
                                  "question, q_lang) VALUES(?,?,1,?,?,?,?,?,?,?)",
                                  (number, PENDING, text, upto, now,
                                   json.dumps(hand, ensure_ascii=False) if hand else None, ctx,
                                   card["question"] if card else None, card["q_lang"] if card else None))
            did = cur.lastrowid
            self.log("черновик %d (до строки %d, %d симв.%s)" % (
                did, upto, len(text), ", нужен человек: причин %d" % len(hand) if hand else ""))
            if card and (card["q_ru"] or card["a_ru"]):
                # перевод — к версии 1 и её тексту; у правки человека его нет (WACARDQ0410)
                self.db.execute("INSERT OR REPLACE INTO draft_tr(draft_id, ver, a_sha, q_ru, a_ru, ts) "
                                "VALUES(?,1,?,?,?,?)", (did, text_sha(text), card["q_ru"], card["a_ru"], now))
            if card:
                self.log("черновик %d: вопрос %d симв., язык вопроса %s, перевод %s" % (
                    did, len(card["question"]), card["q_lang"] or "—",
                    "есть" if (card["q_ru"] or card["a_ru"]) else "нет"))
            self._card_new(did, 1, now)       # не дошла — очередь доставки повторит (WADRAFTSAFE0210)
            made.append(did)
        return made

    def _fresh(self, number, after_id, inbound=True):
        """Что пришло в очередь по клиенту после after_id: (kind, id) первой живой строки или None.
        Эхо, которое скан признал автоприветствием (`autogreet`), — не новое: оно идёт следом за
        «первым» входящим, и без этого черновик на первый вопрос не родился бы никогда.
        inbound=False — только эхо. Такт отложенного с WADRAFTSAFE0210 зовёт с входящими: новое сообщение
        клиента снимает и отложенное (до него, WAHUMANPACE0210, отложенному в срок оно было не помеха)."""
        q = self._queue()
        try:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid FROM wa_inbox "
                             "WHERE from_number=? AND id > ? ORDER BY id", (number, after_id)).fetchall()
        finally:
            q.close()
        for rid, msg_type, echo, history, wamid in rows:
            kind = self._live_kind(msg_type, echo, history)
            if kind == wa_kind.KIND_INBOUND and inbound:
                return kind, rid
            if kind == wa_kind.KIND_ECHO and not self._our_wamid(wamid) and not self._greeted(rid):
                return kind, rid
        return None

    # ── нажатие ───────────────────────────────────────────────────────────────────────────

    def _decided(self, draft_id, ver=None):
        """Слова проигравшему. ver — версия нажатой кнопки: прежняя версия отвечает «устарело»."""
        row = self.db.execute("SELECT state, decided_by, decided_at, closed_at, ver FROM drafts "
                              "WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return "черновика нет"
        state, by, at, closed, ver_now = row
        if ver is not None and int(ver) != ver_now:
            return "устарело: версия %d, действует версия %d — %s" % (
                int(ver), ver_now, "жмите кнопки новой карточки" if state == PENDING
                else self._decided(draft_id))
        ver = ver_now
        if by:
            return "уже решено: %s, %s — %s" % (by, hm_phuket(at), state)
        return "уже решено: снят, %s — %s (версия %d)" % (hm_phuket(closed), state, ver)

    def press(self, draft_id, ver, action, who, now=None):
        """Нажатие кнопки карточки. → {"ok": bool, "state": …, "words": …}."""
        now = self.clock() if now is None else now
        target = CLAIMED if action == ACT_SEND else DECLINED
        if action not in (ACT_SEND, ACT_DECLINE, ACT_CANCEL):
            return {"ok": False, "state": None, "words": "неизвестное действие"}
        if action == ACT_CANCEL:
            # «Отменить» отложенного (WAHUMANPACE0210): тот же условный захват, что у такта отправки —
            # кто первым сменил scheduled, тот и решил; клиенту не уходит ничего
            n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=?, closed_at=?, reason=? "
                                "WHERE id=? AND state=? AND ver=?",
                                (DECLINED, who, now, now, "отменено до срока", draft_id, SCHEDULED,
                                 int(ver))).rowcount
            if n != 1:
                return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
            self.log("черновик %d: отложенное отменено" % draft_id)
            self._done(draft_id, "отменено до срока: %s, %s — клиенту ничего не ушло" % (who, hm_phuket(now)), now)
            return {"ok": True, "state": DECLINED, "words": "отменено — клиенту ничего не ушло"}
        if action == ACT_SEND and self.send_locked(draft_id, ver):
            # «нужен человек»: ДО захвата и до двери — черновик ждёт правки, кнопки живы
            self.log("черновик %d: «Отправить» заперто — нужен человек, ждём «Исправить»" % draft_id)
            return {"ok": False, "state": PENDING, "words": HANDOFF_LOCK_WORDS}
        if action == ACT_SEND and not self._door_open():
            # дверь выключена (WA_SEND): ДО захвата — черновик остаётся pending, кнопки живы
            row = self.db.execute("SELECT state, ver FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if row and row[0] == PENDING and row[1] == int(ver):
                self.log("черновик %d: «Отправить» — отправка выключена, черновик ждёт" % draft_id)
                return {"ok": False, "state": PENDING,
                        "words": "отправка выключена — черновик ждёт, кнопки живы"}
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=? "
                            "WHERE id=? AND state='pending' AND ver=?",
                            (target, who, now, draft_id, int(ver))).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number, upto, text = self.db.execute("SELECT number, upto_id, text FROM drafts WHERE id=?",
                                             (draft_id,)).fetchone()
        if action == ACT_DECLINE:
            self.db.execute("UPDATE drafts SET closed_at=? WHERE id=?", (now, draft_id))
            self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, ?) WHERE number=?", (upto, number))
            self._done(draft_id, "не нужно: %s, %s" % (who, hm_phuket(now)), now)
            return {"ok": True, "state": DECLINED, "words": "не отправляем"}

        # ── победитель: нажатие привязано к последнему сообщению клиента и версии контекста (WADRAFTSAFE0210) ──
        old = self._outdated(draft_id)
        if old:
            self._close(draft_id, STALE, "устарело при нажатии: %s — ничего не отправлено, черновик пересобирается"
                        % old, now, from_states=(CLAIMED,))
            return {"ok": False, "state": STALE, "words": "устарело: %s — ничего не отправлено" % old}

        # ── перепроверка очереди ДО двери; очередь не прочитана — захват назад, наружу ничего ──
        try:
            fresh = self._fresh(number, upto)
        except Exception as e:                                       # noqa: BLE001
            self.db.execute("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL WHERE id=? AND state=?",
                            (PENDING, draft_id, CLAIMED))
            self.log("черновик %d: очередь не прочитана при нажатии (%s) — ничего не отправлено, черновик ждёт"
                     % (draft_id, type(e).__name__))
            return {"ok": False, "state": PENDING,
                    "words": "очередь не прочитана — ничего не отправлено, черновик ждёт: нажмите ещё раз"}
        paused = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        if fresh or (paused and paused[0]):
            kind, rid = fresh or (wa_kind.KIND_ECHO, None)
            state = SUPERSEDED if kind == wa_kind.KIND_ECHO else STALE
            self._close(draft_id, state, "снят при нажатии: %s после черновика" %
                        ("ответ с телефона" if state == SUPERSEDED else "новое сообщение клиента"),
                        now, from_states=(CLAIMED,))
            if state == SUPERSEDED and rid is not None:
                self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?",
                                (number,))
                self._pause(number, rid, now)
            return {"ok": False, "state": state, "words": "не отправлено: " + (
                "ответили с телефона" if state == SUPERSEDED else "клиент написал ещё")}

        # ── человеческий ритм (WAHUMANPACE0210): срок не настал — отправка ставится на срок ──
        # напоминание (WAFOLLOWUP0210) ритму не подлежит: тишина в нём уже есть, а отложенное ушло бы и
        # после нового сообщения клиента (send_due снимает только по эху)
        if self.pace and self.draft_kind(draft_id) != KIND_FOLLOW:
            due, why = self._pace_due(number, upto, text, now)
            self.log("черновик %d: ритм — %s" % (draft_id, why))
            if due is not None and due > now:
                if self.db.execute("UPDATE drafts SET state=?, due_at=? WHERE id=? AND state=?",
                                   (SCHEDULED, due, draft_id, CLAIMED)).rowcount != 1:
                    return {"ok": False, "state": None, "words": self._decided(draft_id)}
                # входящие до черновика закрыты решением: новый черновик — только на новое сообщение
                self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, ?) WHERE number=?", (upto, number))
                words = "уйдёт в %s" % hm_phuket(due)
                self._tg("card_wait", draft_id, self._card(draft_id), "%s — нажал %s, %s" % (words, who, hm_phuket(now)),
                         int(ver))
                return {"ok": True, "state": SCHEDULED, "words": words}
        return self._deliver(draft_id, number, upto, text, who, now, CLAIMED)

    def _deliver(self, draft_id, number, upto, text, who, now, from_state):
        """Дверь для захваченного черновика: «Отправить» (claimed) или срок ритма (scheduled)."""
        # ── sending ДО двери: рестарт после этой строки повтора не даст ──
        if self.db.execute("UPDATE drafts SET state=? WHERE id=? AND state=?",
                           (SENDING, draft_id, from_state)).rowcount != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id)}
        try:
            res = self.door.send_text(number, text) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = _DOOR_STATE.get(res.get("outcome"), UNSURE)
        wamid = res.get("wamid") if state == SENT else None
        self.db.execute("UPDATE drafts SET state=?, reason=?, wamid=?, closed_at=? WHERE id=? AND state=?",
                        (state, str(res.get("reason") or "")[:300], wamid, now, draft_id, SENDING))
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, ?) WHERE number=?", (upto, number))
        self.log("черновик %d: дверь → %s" % (draft_id, state))
        if state == SENT:
            # ушедшее агентом: история агента; строка в теме клиента — из `agent_show` (WAMIRROR0410), не здесь
            self._sent_out(wamid, number, text, VIA_AGENT, now)
        self._done(draft_id, "%s: %s, %s" % (state, who, hm_phuket(now)), now)
        return {"ok": state == SENT, "state": state, "words": state}

    # ── человеческий ритм (WAHUMANPACE0210) ───────────────────────────────────────────────

    def send_due(self, now):
        """Отложенные, срок которых настал: по сроку, по одному, через тот же захват `sending`.
        Ответили с телефона после черновика или клиент на паузе (человек вмешался) — не шлём.
        Клиент написал ещё (в очереди, даже не разобранное сканом, или по версии контекста) — тоже не шлём:
        отложенное снято, черновик пересобирается (WADRAFTSAFE0210). Очередь не прочитана — ждёт такта."""
        rows = self.db.execute("SELECT id, number, upto_id, text, decided_by FROM drafts WHERE state=? "
                               "AND due_at<=? ORDER BY due_at, id", (SCHEDULED, now)).fetchall()
        out = []
        for did, number, upto, text, who in rows:
            try:
                fresh = self._fresh(number, upto)
            except Exception as e:                                   # noqa: BLE001
                self.log("черновик %d: очередь не прочитана в срок (%s) — отложенное ждёт следующего такта"
                         % (did, type(e).__name__))
                continue
            old = self._outdated(did)
            paused = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
            if (fresh and fresh[0] == wa_kind.KIND_INBOUND) or (old and not fresh):
                self._close(did, STALE, "снят в срок: %s — отложенное не уходит, черновик пересобирается" % (
                    WROTE_WORDS % fresh[1] if fresh else old), now, from_states=(SCHEDULED,))
                continue
            if fresh or (paused and paused[0]):
                self._close(did, SUPERSEDED, "снят в срок: %s — не отправлено" % (
                    "ответили с телефона" if fresh else "человек вмешался, клиент на паузе"), now,
                    from_states=(SCHEDULED,))
                continue
            res = self._deliver(did, number, upto, text, who or "—", now, SCHEDULED)
            self.log("черновик %d: срок ритма настал → %s" % (did, res.get("state")))
            out.append((did, res.get("state")))
        return out

    def _pace_due(self, number, upto, text, now):
        """Срок отправки по ритму → (срок | None — судить нечем, слова для журнала). Числами, без текста.
        Срок прошёл — решает `press`: уходит сразу.
        Наше — живое эхо с телефона (кроме автоприветствия), ушедшее через API (`outbox`) и отложенное
        этого клиента; клиента — живые входящие до строки черновика. Беседа новая, если до первого
        неотвеченного сообщения клиента тишина в обе стороны дольше PACE_NEW_TALK."""
        q = self._queue()
        try:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid, COALESCE(ts_msg, ts_queued) FROM wa_inbox "
                             "WHERE from_number=? AND id<=? ORDER BY id", (number, upto)).fetchall()
        finally:
            q.close()
        ins, outs = [], []
        for rid, msg_type, echo, history, wamid, ts in rows:
            kind = self._live_kind(msg_type, echo, history)
            if ts is None or kind is None:
                continue
            if kind == wa_kind.KIND_INBOUND:
                ins.append(float(ts))
            elif not self._greeted(rid):
                outs.append(float(ts))
        outs += [float(r[0]) for r in self.db.execute("SELECT ts FROM outbox WHERE number=?", (number,))]
        if not ins:
            return None, "входящих клиента до черновика в очереди нет — сразу"
        past = [t for t in outs if t <= now]
        unanswered = [t for t in ins if not past or t > max(past)]
        # у клиента уже есть отложенное: этот ответ — следующий за ним и его не обгоняет
        later = self.db.execute("SELECT MAX(due_at) FROM drafts WHERE number=? AND state=?",
                                (number, SCHEDULED)).fetchone()[0]
        if later is None and unanswered:
            first = unanswered[0]
            before = [t for t in ins + outs if t < first]
            if not before or first - max(before) > PACE_NEW_TALK:
                due = first + PACE_FIRST_MIN + self.rand() * (PACE_FIRST_MAX - PACE_FIRST_MIN)
                return due, "первый ответ беседы: срок %d с после сообщения клиента, нажато через %d с" % (
                    due - first, now - first)
        typing = min(len(text or "") / PACE_CPS, PACE_TYPE_MAX)
        base = ins[-1] if later is None else max(ins[-1], float(later))
        return base + typing, "следующий: набор %d с, от %s до нажатия %d с" % (
            typing, "сообщения клиента" if later is None else "срока отложенного", now - base)

    # ── напоминание притихшему (WAFOLLOWUP0210) ───────────────────────────────────────────

    def draft_kind(self, draft_id):
        """Вид черновика: KIND_FOLLOW — напоминание; None — ответ на сообщение клиента."""
        row = self.db.execute("SELECT kind FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    def _follow_due(self, number, now):
        """Пора ли напоминать → (якорь — время нашего последнего сообщения | None, верхний id строк клиента,
        слова для журнала). Числами, без текста. Наше — живое эхо (кроме автоприветствия) и `outbox`;
        клиента — живые входящие. Окно — правилом `wa_send.last_inbound_ts`/`window_state`: последнее
        входящее (echo=0, не квитанция, не реакция) не старше FOLLOW_WINDOW − FOLLOW_SPARE."""
        q = self._queue()
        try:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid, COALESCE(NULLIF(ts_msg, 0), ts_queued) "
                             "FROM wa_inbox WHERE from_number=? ORDER BY id", (number,)).fetchall()
        finally:
            q.close()
        ins, outs, win, top = [], [], None, 0
        for rid, msg_type, echo, history, wamid, ts in rows:
            top = max(top, rid)
            if ts is None:
                continue
            if not echo and msg_type is not None and msg_type not in ("status", "reaction"):
                win = float(ts) if win is None else max(win, float(ts))
            kind = self._live_kind(msg_type, echo, history)
            if kind == wa_kind.KIND_INBOUND or (msg_type == "reaction" and not echo and not history):
                ins.append(float(ts))         # реакция клиента окна не открывает, но тишину прерывает
            elif kind == wa_kind.KIND_ECHO and not self._greeted(rid):
                outs.append(float(ts))
        outs += [float(r[0]) for r in self.db.execute("SELECT ts FROM outbox WHERE number=?", (number,))]
        if win is None:
            return None, top, "окно 24 ч неизвестно — входящих клиента нет"
        if now - win > FOLLOW_WINDOW - FOLLOW_SPARE:
            return None, top, "окно 24 ч закрыто или кончается"
        if not outs:
            return None, top, "нашего сообщения нет"
        ours = max(outs)
        if ins and max(ins) >= ours:
            return None, top, "последнее слово за клиентом"
        if now - ours < FOLLOW_QUIET:
            return None, top, "тишины меньше %d с" % FOLLOW_QUIET
        # беседа — события подряд без тишины дольше PACE_NEW_TALK (та же граница, что у ритма)
        evs = sorted(t for t in ins + outs if t <= now)
        start = evs[-1]
        for t in reversed(evs[:-1]):
            if start - t > PACE_NEW_TALK:
                break
            start = t
        n = self.db.execute("SELECT COUNT(*) FROM drafts WHERE number=? AND kind=? AND created_at>=?",
                            (number, KIND_FOLLOW, start)).fetchone()[0]
        if n >= FOLLOW_MAX:
            return None, top, "напоминаний в беседе уже %d из %d" % (n, FOLLOW_MAX)
        return ours, top, "тишина %d с после нашего, окну осталось %d с, напоминание %d из %d" % (
            now - ours, FOLLOW_WINDOW - (now - win), n + 1, FOLLOW_MAX)

    def make_followups(self, now):
        """Притихшие клиенты → черновик-напоминание с карточкой или «не нужно» (строка журнала). Модель —
        один раз на наше последнее сообщение; не дала ответа — повтор не раньше MODEL_RETRY_SEC."""
        if self._follow_last is not None and 0 <= now - self._follow_last < FOLLOW_EVERY:
            return []
        self._follow_last = now
        made = []
        # грубый отсев по часам сервера (last_in_ts — ts_queued): очередь читаем только у писавших за окно
        # с часом запаса; точное окно — `_follow_due`
        rows = self.db.execute("SELECT number, ctx FROM clients WHERE paused=0 AND last_in_id > 0 "
                               "AND last_in_id <= done_upto AND next_try <= ? AND last_in_ts >= ?",
                               (now, now - FOLLOW_WINDOW - 3600)).fetchall()
        for number, ctx in rows:
            if self._live_draft(number) or self.db.execute(
                    "SELECT 1 FROM drafts WHERE number=? AND state=?", (number, SCHEDULED)).fetchone():
                continue
            anchor, top, why = self._follow_due(number, now)
            if anchor is None or self.db.execute("SELECT 1 FROM followups WHERE number=? AND anchor=?",
                                                 (number, anchor)).fetchone():
                continue
            try:
                kind, val = follow_out(self.model.followup(number, top))
            except Exception as e:                                   # noqa: BLE001
                self.log("напоминание: модель упала: %s" % type(e).__name__)
                kind, val = "fail", None
            if kind == "fail":
                self.db.execute("UPDATE clients SET next_try=? WHERE number=?", (now + MODEL_RETRY_SEC, number))
                self.log("напоминание: модель не дала ответа — повтор не раньше %d с" % MODEL_RETRY_SEC)
                continue
            # пока думала модель, клиент мог написать или человек ответить — не пишем
            if self._fresh(number, top):
                continue
            if kind == "skip":
                self.db.execute("INSERT OR IGNORE INTO followups(number, anchor, ts, outcome) VALUES(?,?,?,?)",
                                (number, anchor, now, FOLLOW_NOT_NEEDED))
                self.log("напоминание: модель — не нужно, карточки нет (%s)" % why)
                continue
            did = self.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, kind, ctx) "
                                  "VALUES(?,?,1,?,?,?,?,?)", (number, PENDING, val, top, now, KIND_FOLLOW,
                                                              ctx)).lastrowid
            self.db.execute("INSERT OR IGNORE INTO followups(number, anchor, ts, outcome, draft_id) VALUES(?,?,?,?,?)",
                            (number, anchor, now, FOLLOW_DRAFTED, did))
            self.log("черновик %d: напоминание (%s, %d симв.)" % (did, why, len(val)))
            self._card_new(did, 1, now)       # не дошла — очередь доставки повторит (WADRAFTSAFE0210)
            made.append(did)
        return made

    def follow_counts(self):
        return dict(self.db.execute("SELECT outcome, COUNT(*) FROM followups GROUP BY outcome").fetchall())

    def revise(self, draft_id, text, who, now=None, ver=None, who_id=None):
        """«Исправить»: текст человека, версия +1; кнопки прежней версии отвечают «устарело».
        ver — версия карточки, на которую ответили реплаем: правка прежней версии не принимается
        (тот же замок, что у нажатия). Принята — прежняя карточка «устарело», новая карточка с
        версией +1; «Отправить» на ней шлёт текст человека дословно.
        Уроки включены и текст другой — кандидат урока (было → стало) пишется ДО новой карточки:
        карточка показывает «урок №N записан кандидатом», под ней — сообщение урока (WAAGENTLESSON0210)."""
        now = self.clock() if now is None else now
        if not (text or "").strip():
            return False
        old = self.db.execute("SELECT text, ver FROM drafts WHERE id=?", (draft_id,)).fetchone()
        q, args = "UPDATE drafts SET text=?, ver=ver+1 WHERE id=? AND state='pending'", (text, draft_id)
        if ver is not None:
            q, args = q + " AND ver=?", args + (int(ver),)
        elif old:
            q, args = q + " AND ver=?", args + (old[1],)
        n = self.db.execute(q, args).rowcount
        if n == 1:
            number, ver_now, old_card = self.db.execute(
                "SELECT number, ver, card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
            self.log("черновик %d исправлен → версия %d (%s)" % (draft_id, ver_now, who))
            lesson = None
            if self.lessons and old and old[0] != text:
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO lessons(state, author, author_id, ts, draft_id, ver_from, ver_to, "
                    "was_text, now_text) VALUES(?,?,?,?,?,?,?,?,?)",
                    (LESSON_CANDIDATE, who, _int_or_none(who_id), now, draft_id, ver_now - 1, ver_now,
                     old[0], text))
                lesson = cur.lastrowid if cur.rowcount == 1 else None
                if lesson:
                    self.log("урок %d: кандидат (черновик %d, версия %d → %d, %s)" % (
                        lesson, draft_id, ver_now - 1, ver_now, who))
            self._card_close(draft_id, ver_now - 1, "устарело: исправлено — %s, %s, действует версия %d" % (
                who, hm_phuket(now), ver_now), now, old_card)
            # карточка новой версии — через очередь доставки: до доставки card_id пуст (WADRAFTSAFE0210)
            self.db.execute("UPDATE drafts SET card_id=NULL WHERE id=?", (draft_id,))
            self._card_new(draft_id, ver_now, now)
            if lesson:
                self._tg("lesson_card", lesson)
        return n == 1

    # ── уроки людей (WAAGENTLESSON0210) ───────────────────────────────────────────────────

    def lesson_of(self, draft_id, ver):
        """Номер урока, записанного правкой, давшей эту версию черновика; нет — None."""
        row = self.db.execute("SELECT id FROM lessons WHERE draft_id=? AND ver_to=?",
                              (draft_id, int(ver))).fetchone()
        return row[0] if row else None

    def lesson_admin(self, who_id):
        """Вправе ли переводить и откатывать уроки: id Telegram в списке. Нет id — не вправе."""
        uid = _int_or_none(who_id)
        return uid is not None and uid in self.lesson_admins

    def _lesson_decided(self, lesson_id):
        row = self.db.execute("SELECT state, decided_by, decided_at, rolled_by, rolled_at FROM lessons "
                              "WHERE id=?", (int(lesson_id),)).fetchone()
        if not row:
            return "урока №%d нет" % int(lesson_id)
        state, by, at, rby, rat = row
        if state == LESSON_ACTIVE:
            return "уже решено: урок №%d — действующее правило: %s, %s" % (int(lesson_id), by, hm_phuket(at))
        if state == LESSON_ROLLED:
            return "уже решено: урок №%d откатан: %s, %s" % (int(lesson_id), rby, hm_phuket(rat))
        return "урок №%d — кандидат" % int(lesson_id)

    def _lesson_deny(self, lesson_id, what):
        return "отказ: %s вправе только владелец или список WA_AGENT_LESSON_ADMINS — урок №%d не тронут" % (
            what, int(lesson_id))

    def lesson_promote(self, lesson_id, who, who_id, now=None):
        """«Сделать правилом»: кандидат → действующий, только тем, кто в праве. → {"ok", "state", "words"}."""
        now = self.clock() if now is None else now
        if not self.lessons:
            return {"ok": False, "state": None, "words": "%s — урок №%d не переведён" % (
                LESSON_OFF_WORDS, int(lesson_id))}
        if not self.lesson_admin(who_id):
            self.log("урок %d: «Сделать правилом» — отказ, нет права: %s" % (int(lesson_id), who))
            return {"ok": False, "state": None, "words": self._lesson_deny(lesson_id, "сделать правилом")}
        n = self.db.execute("UPDATE lessons SET state=?, decided_by=?, decided_at=? WHERE id=? AND state=?",
                            (LESSON_ACTIVE, who, now, int(lesson_id), LESSON_CANDIDATE)).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._lesson_decided(lesson_id)}
        self.log("урок %d → действующий (%s)" % (int(lesson_id), who))
        self._tg("lesson_done", int(lesson_id), "✅ действующее правило — %s, %s" % (who, hm_phuket(now)),
                 LESSON_ACTIVE)
        return {"ok": True, "state": LESSON_ACTIVE,
                "words": "урок №%d — действующее правило: идёт в промпт агента" % int(lesson_id)}

    def lesson_rollback(self, lesson_id, who, who_id, now=None):
        """«Откатить №N»: действующий (или кандидат) → откатан, только тем, кто в праве. Из промпта уходит
        со следующего черновика. Откат работает и при выключенных уроках — это шаг в безопасную сторону."""
        now = self.clock() if now is None else now
        if not self.lesson_admin(who_id):
            self.log("урок %d: откат — отказ, нет права: %s" % (int(lesson_id), who))
            return {"ok": False, "state": None, "words": self._lesson_deny(lesson_id, "откатить урок")}
        n = self.db.execute("UPDATE lessons SET state=?, rolled_by=?, rolled_at=? WHERE id=? AND state IN (?,?)",
                            (LESSON_ROLLED, who, now, int(lesson_id), LESSON_ACTIVE, LESSON_CANDIDATE)).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._lesson_decided(lesson_id)}
        self.log("урок %d → откатан (%s)" % (int(lesson_id), who))
        self._tg("lesson_done", int(lesson_id), "↩️ откатан — %s, %s; в промпт агента не идёт" % (who, hm_phuket(now)),
                 LESSON_ROLLED)
        return {"ok": True, "state": LESSON_ROLLED,
                "words": "урок №%d откатан — в промпт агента не идёт" % int(lesson_id)}

    def lesson_reason(self, lesson_id, text, who):
        """Причина урока — реплай на сообщение урока, пока он кандидат: действующий меняет только
        перевод и откат, иначе правка причины обходила бы право перевода. → True — записана."""
        text = (text or "").strip()[:LESSON_REASON_MAX]
        if not text:
            return False
        n = self.db.execute("UPDATE lessons SET reason=? WHERE id=? AND state=?",
                            (text, int(lesson_id), LESSON_CANDIDATE)).rowcount
        if n == 1:
            self.log("урок %d: причина записана (%s, %d симв.)" % (int(lesson_id), who, len(text)))
        return n == 1

    def lesson_counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM lessons GROUP BY state").fetchall())

    def _card(self, draft_id):
        row = self.db.execute("SELECT card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    def card_extra(self, draft_id, ver, text):
        """Вопрос и перевод для карточки версии ver с текстом text (WACARDQ0410) → None (вопроса нет: черновик старше
        или напоминание — карточка прежняя) | {question, q_lang, q_ru, a_ru, tr_ver}: переводы — только этой версии
        с этим текстом; tr_ver — версия, к которой перевод есть, если он не к этой."""
        row = self.db.execute("SELECT question, q_lang FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[0] is None:
            return None
        rows = self.db.execute("SELECT ver, a_sha, q_ru, a_ru FROM draft_tr WHERE draft_id=?", (draft_id,)).fetchall()
        q_ru, a_ru, tr_ver = tr_pick(rows, ver, text)
        return {"question": row[0], "q_lang": row[1] or None, "q_ru": q_ru, "a_ru": a_ru, "tr_ver": tr_ver}

    def handoff(self, draft_id):
        row = self.db.execute("SELECT handoff FROM drafts WHERE id=?", (draft_id,)).fetchone()
        hand = handoff_of(row[0]) if row else []
        return [UNREAD_REASON] if hand is None else hand

    def send_locked(self, draft_id, ver):
        """«Отправить» заперто: черновик ждёт с этой версией, у него есть причины «нужен человек»,
        и человек его ещё не исправлял (версия 1 — текст модели; «Исправить» даёт версию +1)."""
        row = self.db.execute("SELECT state, ver, handoff FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[0] != PENDING or row[1] != int(ver):
            return False
        hand = handoff_of(row[2])
        return (hand is None or bool(hand)) and row[1] == 1

    def _door_open(self):
        """Дверь без `is_open` — открыта (прежний контракт); `is_open` упал — закрыта."""
        probe = getattr(self.door, "is_open", None)
        if probe is None:
            return True
        try:
            return bool(probe())
        except Exception as e:                                       # noqa: BLE001
            self.log("дверь: is_open упал: %s — считаем выключенной" % type(e).__name__)
            return False

    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM drafts GROUP BY state").fetchall())


if __name__ == "__main__":
    raise SystemExit("wa_agent: ядро без рук (WAAGENTCORE0110) — служба собирается в wa_agent_svc.py "
                     "(WAAGENTSVC0210), Telegram в wa_agent_tg.py (WAAGENTTG0110)")
