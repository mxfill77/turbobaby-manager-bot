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
     Фото, видео, документ с телефона (WAPAUSEMEDIA0410, решение владельца 05.10.2026): паузы нет — ни
     вопроса «когда продолжать», ни ожидания «Продолжить»; ждущий черновик, done_upto и версия контекста — как
     у всякого эха. Что ставит паузу, решает `wa_kind.echo_pauses` (голосовое, стикер и прочее — пауза).
     На первом старте курсор встаёт на MAX(id): переписка до службы черновиков не даёт.
  2. ЧЕРНОВИК. Клиент не на паузе, ждущих сообщений больше, чем закрыто прежним решением, живого
     черновика нет, со времени последнего сообщения прошло `quiet` (60–90 с — клиенты пишут
     очередями). Перед записью — перепроверка очереди: пришло новое за время модели — не пишем.
     Живой черновик у клиента один: проверка кодом И частичный уникальный индекс базы.

НАЖАТИЕ (`Core.press`). Захват — условный UPDATE `state='pending' AND ver=?`, решает rowcount;
проигравший получает «уже решено: кто, когда, исход». Победитель перепроверяет очередь (эхо →
superseded и пауза, у фото/видео/документа — без паузы; новое входящее → stale), пишет `sending` и ТОЛЬКО ПОТОМ зовёт дверь, затем
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

ПОЯСНЕНИЕ → ПРАВИЛО (NIGHT0710-B2, выключатель службы WA_AGENT_HINTS, по умолчанию выключен — «Исправить» и
«Отправить» как раньше). Включён — «Исправить» зовёт пояснение текстом (`hint`, очередь `hints`); версию +1 по
пояснению делает такт (`make_hint_versions`: модель, тот же условный UPDATE, что у правки текстом). «Отправить»
на такой версии (нажатие выиграно и не снято) пишет в ту же таблицу `lessons` строку вида `hint`: нажал владелец —
по id, строго `LESSON_OWNER_IDS` (`owner`), список WA_AGENT_LESSON_ADMINS не действует — действующее правило с
номером, автором пояснения, временем, источником (черновик, версии) и откатом; нажал сотрудник — кандидат. Правка
текстом и версия модели правила не рождают. Суточный список владельцу — одно сообщение (`hint_list_due`): новые
правила с «отменить», кандидаты с «правило»/«отклонить»; решает только владелец. Правила идут в промпт тем же
путём, что уроки (`active_lessons`), со следующего черновика.

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

ШАБЛОН ПОСЛЕ 24 ЧАСОВ (NIGHT0710-B3g, выключатель службы WA_AGENT_TEMPLATES, по умолчанию выключен — всё как раньше).
Включён — ядро спрашивает окно у ДВЕРИ (`Door.window`, своего правила окна нет). «✅ Отправить» при измеренно закрытом
окне отказывает ДО захвата словами (черновик ждёт), карточка получает «📨 Отправить шаблоном» (`template_offer`:
reply_request, язык текста версии ru|en, {{1}} — «байка»/«bike»). Нажатие — `press_template`: таблица `tpl_out`,
`sending` ДО двери, один шаблон на черновик и на последнее входящее клиента, повтора нет (not_sent — можно ещё
раз), ушедший — в `outbox`. Одобрение у Meta судит дверь по ответу провайдера; любой отказ — словами на карточке.
Клиент ответил — окно открыто, черновик пересобирается и уходит обычной кнопкой.

ЧЕГО ЯДРО НЕ ДЕЛАЕТ. Не шлёт без нажатия; не повторяет отправку; не судит окно 24 часа само (это
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

# ── пояснение → правило (NIGHT0710-B2) ────────────────────────────────────────────────────
LESSON_REJECTED = "rejected"                  # кандидат-пояснение отклонён владельцем: в промпт не идёт
KIND_HINT = "hint"                            # lessons.kind: правило из пояснения; NULL — урок правкой текстом
HINT_WAIT, HINT_DONE, HINT_FAIL = "wait", "done", "fail"
HINT_MAX = 600                                # пояснение, символов = LESSON_ITEM_MAX адаптера (A9a/A9f: хранится,
                                              # показывается на карточке и идёт в правило ОДИН и тот же текст)
HINTS_PER_TICK = 1                            # версий по пояснению за такт: каждая — платный вызов, такт держит опрос
HINT_LIST_HOUR = 21                           # суточный список владельцу — после этого часа по Пхукету
HINT_LIST_KEY, HINT_LIST_NEXT = "hint_list_day", "hint_list_next"   # meta: день ушедшего списка · повтор не раньше
HINT_LIST_RETRY = 300                         # Telegram не принял список — повтор не раньше, с
HINT_OFF_WORDS = "пояснения выключены (WA_AGENT_HINTS)"

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
PART_TPL = "tpl"                              # шаблон после 24 часов (NIGHT0710-B3g): эха у API-сообщения нет — строка здесь
SHOW_WAIT, SHOW_SENDING, SHOW_SHOWN, SHOW_GAVE_UP = "wait", "sending", "shown", "gave_up"
SHOW_MAX = 12                                 # попыток строки показа не больше (≈ 40 мин по CARD_RETRY), дальше — журнал
SHOW_SINCE = "show_since"                     # meta: показ ушедшего — с первого старта этого кода, прошлое — нет
W_SHOW_UNSURE = "исход неизвестен, проверьте телефон"

# ── шаблон после 24 часов (NIGHT0710-B3g, выключатель службы WA_AGENT_TEMPLATES, по умолчанию выключен) ──
# Окно 24 ч закрыто — свободный текст Meta не примет. «✅ Отправить» тогда отказывает ДО захвата (черновик ждёт), а
# карточка предлагает «📨 Отправить шаблоном» reply_request на языке клиента. Шаблон — только нажатием человека, один на
# черновик и на последнее сообщение клиента; одобрение у Meta судит дверь по ответу провайдера. Клиент ответил —
# окно открыто, черновик пересобирается и уходит обычной кнопкой.
VIA_TEMPLATE = "шаблон"
TPL_REPLY = "reply_request"
TPL_WORD = {"ru": "байка", "en": "bike"}          # {{1}} «аренда …»: общее слово — модель из аренды по номеру ненадёжна
TPL_OFF_WORDS = "шаблоны выключены (WA_AGENT_TEMPLATES) — ничего не отправлено"
W_TPL_CLOSED = "окно 24 ч закрыто%s — обычной кнопкой клиенту не уйдёт"
_TPL_SCHEMA = """
CREATE TABLE IF NOT EXISTS tpl_out (
    draft_id    INTEGER PRIMARY KEY,                  -- шаблон к черновику: не больше одного ушедшего
    number      TEXT    NOT NULL,
    upto_id     INTEGER NOT NULL,                     -- последнее входящее клиента: второго шаблона до нового нет
    ver         INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    lang        TEXT    NOT NULL,
    state       TEXT    NOT NULL,                     -- sending ДО двери, потом sent | not_sent | unsure
    reason      TEXT,
    wamid       TEXT,
    who         TEXT,
    tries       INTEGER NOT NULL DEFAULT 1,           -- not_sent можно ещё раз: Meta одобрит — шаблон уйдёт
    ts          REAL    NOT NULL,
    body        TEXT                                  -- что увидел клиент (текст шаблона) — для строки показа
);
"""


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
    """Действующие уроки → [(номер, было, стало, причина, вид, пояснение)] по номеру. Одно правило для ядра и
    адаптера модели: кандидат, откатанный и отклонённый в промпт не идут. Вид NULL — урок правкой текстом; база
    старше колонок вида (NIGHT0710-B2) — прежние четыре поля и вид NULL."""
    try:
        return db.execute("SELECT id, was_text, now_text, reason, kind, hint FROM lessons WHERE state=? ORDER BY id",
                          (LESSON_ACTIVE,)).fetchall()
    except sqlite3.OperationalError:
        return [tuple(r) + (None, None) for r in db.execute(
            "SELECT id, was_text, now_text, reason FROM lessons WHERE state=? ORDER BY id", (LESSON_ACTIVE,))]


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
CREATE TABLE IF NOT EXISTS hints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,    -- номер пояснения (NIGHT0710-B2)
    draft_id    INTEGER NOT NULL,
    ver_from    INTEGER NOT NULL,                     -- версия, к которой пояснение
    ver_to      INTEGER,                              -- версия, сделанная по нему; NULL — ещё нет
    text        TEXT    NOT NULL,                     -- пояснение (в журнал не идёт)
    prev_text   TEXT    NOT NULL,                     -- текст версии ver_from: «было» правила
    author      TEXT    NOT NULL,                     -- кто пояснил: имя (id N)
    author_id   INTEGER,
    msg_id      INTEGER,                              -- сообщение пояснения в группе: ответ словами — на него
    ts          REAL    NOT NULL,
    state       TEXT    NOT NULL,                     -- wait → done | fail
    reason      TEXT,                                 -- почему версии нет
    done_at     REAL,
    UNIQUE (draft_id, ver_from)
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
# «Отправить» есть на КАЖДОЙ версии (решение владельца 05.10 12:39, WACARDUI0510): причины — пометка первой строкой
# карточки, решает человек; нажатие на версии с причинами — строка журнала с их числом.
SEND_HAND_LOG = "черновик %d: «Отправить» на версии %d при причинах «нужен человек»: %d — решил человек (%s)"


def handoff_of(raw):
    """drafts.handoff → [слова]; NULL — [] (причин нет). Битая запись — None («не прочитано», не «причин
    нет»): карточка и журнал нажатия считают такой черновик черновиком с причинами."""
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


def draft_why(out):
    """Ответ Model.draft → (why, claims) для низа карточки (WACARDUI0510). why — строка сотруднику («» — модель не
    объяснила; прежний контракт-строка — тоже «»); claims — [[вид, что]] денежных утверждений без опоры, посчитанные
    КОДОМ адаптера ([] — проверено, без опоры нет), None — код числа не проверял. Клиенту из этого не уходит ничего."""
    if not isinstance(out, dict):
        return "", None
    why = out.get("why")
    why = why.strip() if isinstance(why, str) else ""
    claims = out.get("claims")
    if not isinstance(claims, (list, tuple)):
        return why, None
    return why, [[str(c[0]), c[1]] for c in claims if isinstance(c, (list, tuple)) and len(c) == 2]


def claims_of(raw):
    """drafts.claims → [[вид, что]] | None (не проверялось или запись не читается — «не проверено», а не «чисто»)."""
    if raw is None:
        return None
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return val if isinstance(val, list) else None


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

    def redraft(self, number, upto_id, prev_text, hint):
        """Версия по пояснению сотрудника (NIGHT0710-B2) → тот же ответ, что у draft. Адаптера нет — None: версии
        нет, пояснение отвечается словами."""
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

    def hint_note(self, hint_id, words):
        """Пояснение без версии (NIGHT0710-B2): ответ словами на сообщение пояснения. Рук нет — ничего."""
        return None

    def hint_list(self, lesson_ids):
        """Суточный список владельцу (NIGHT0710-B2) → [показанные номера] | None (не ушёл). Рук нет — None."""
        return None

    def card_tpl(self, draft_id, card_id, ver, words, offer):
        """Шаблон после 24 часов (NIGHT0710-B3g): карточка получает слова, кнопки живы; offer — кнопка
        «📨 Отправить шаблоном» (None — без неё). Рук нет — ничего."""
        return None


class Door:
    """send_text(to, text) → {"outcome": sent|not_sent|unknown, "reason": str, "wamid": str|None}.
    Контракт совпадает с `wa_send.send_text` (тот НИКОГДА не бросает и сам судит окно 24 ч)."""

    def send_text(self, to, text):
        raise NotImplementedError

    def send_media(self, to, media):
        """Медиа из темы (WARELAYMEDIA0210) — контракт `wa_send.send_media`. Двери без медиа — отказ."""
        return {"outcome": "not_sent", "reason": "дверь не умеет медиа", "wamid": None}

    def window(self, number):
        """Окно 24 ч клиента по правилу двери (NIGHT0710-B3g) → {"state": open|closed|unknown, "age": с} | None.
        Двери без пробы — None: окно не измерено, шаблон не предлагается."""
        return None

    def send_template(self, to, name, lang, params):
        """Шаблон (NIGHT0710-B3g) — контракт `wa_send.send_template`. Двери без шаблонов — отказ."""
        return {"outcome": "not_sent", "reason": "дверь не умеет шаблоны", "wamid": None}


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
        hm_phuket(at), name, int(draft_id), int(ver or 1),
        "PDF" if part == PART_PDF else "шаблон" if part == PART_TPL else "текст")
    if outcome == UNSURE:
        head += " · " + W_SHOW_UNSURE
    return head + ":\n" + str(body or "")


class Core:
    def __init__(self, db_path, queue_path, model, tg, door, quiet=QUIET_DEFAULT,
                 clock=time.time, log=None, drafts=True, greet=(), pace=False, rand=random.random,
                 lessons=False, lesson_admins=None, followup=False, hints=False, hint_hour=HINT_LIST_HOUR,
                 templates=False, lang_of=None):
        quiet = int(quiet)
        # WA_AGENT_HINTS (NIGHT0710-B2): выключен — «Исправить» и «Отправить» как раньше, правил из пояснений нет;
        # hint_hour — час суточного списка владельцу по Пхукету (24 — списка нет)
        self.hints = bool(hints)
        self.hint_hour = hint_hour
        # WA_AGENT_TEMPLATES (NIGHT0710-B3g): выключен — окно ядро не спрашивает, кнопки шаблона нет, «Отправить» прежнее;
        # lang_of — правило языка по тексту (`wa_agent_knowledge.lang_of`, приносит служба: ядро его не импортирует)
        self.templates = bool(templates)
        self.lang_of = lang_of
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
        # как считал агент и проверка чисел кодом (WACARDUI0510); NULL — черновик старше: низа карточки нет
        for col in ("why", "claims"):
            if col not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
                self.db.execute("ALTER TABLE drafts ADD COLUMN %s TEXT" % col)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(card_out)")}
        for col in ("lost", "edit_unk"):                                  # очередь старше WACARDDONEFIX0210
            if col not in have:
                self.db.execute("ALTER TABLE card_out ADD COLUMN %s INTEGER NOT NULL DEFAULT 0" % col)
        # правило из пояснения (NIGHT0710-B2): вид, пояснение, кто нажал «Отправить», id решавших, попадание в список
        have = {r[1] for r in self.db.execute("PRAGMA table_info(lessons)")}
        for col, typ in (("kind", "TEXT"), ("hint", "TEXT"), ("sent_by", "TEXT"), ("sent_by_id", "INTEGER"),
                         ("sent_at", "REAL"), ("decided_by_id", "INTEGER"), ("rolled_by_id", "INTEGER"),
                         ("listed_at", "REAL")):
            if col not in have:
                self.db.execute("ALTER TABLE lessons ADD COLUMN %s %s" % (col, typ))
        # показ ушедшего агентом (WAMIRROR0410): с этой минуты; ушедшее раньше строки не получает
        self.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (SHOW_SINCE, repr(float(self.clock()))))
        if self.templates:
            self.db.executescript(_TPL_SCHEMA)        # выключено — таблицы нет, база прежняя
            if "body" not in {r[1] for r in self.db.execute("PRAGMA table_info(tpl_out)")}:
                self.db.execute("ALTER TABLE tpl_out ADD COLUMN body TEXT")   # таблица кандидата №1 — без текста
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
        # шаблон (NIGHT0710-B3g): рестарт посреди отправки — мог уйти, не повторяем
        if self._tpl_table():
            n7 = self.db.execute("UPDATE tpl_out SET state=?, reason=? WHERE state=?",
                                 (UNSURE, "рестарт посреди отправки шаблона — мог уйти, не повторяем", SENDING)).rowcount
            if n7:
                self.log("старт: шаблон sending→unsure %d" % n7)

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
        if self._tpl_table():
            # шаблон (NIGHT0710-B3g): ушедший через API — эха нет, в тему клиента он ложится только отсюда
            rows = self.db.execute(
                "SELECT draft_id, ver, number, state, wamid, who, tries, ts, body, name, lang FROM tpl_out "
                "WHERE state IN (?,?) AND ts >= ?", (SENT, UNSURE, since)).fetchall()
            for did, ver, number, state, wamid, who, tries, at, body, name, lang in rows:
                self._show_put(wamid, PART_TPL, did, ver, tries, number, who, state,
                               body or "[шаблон %s (%s)]" % (name, lang), at)
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
        if self.hints:
            self.hint_list_due(now)           # суточный список владельцу (NIGHT0710-B2)
        if not self.drafts:
            self.follow()
            self.deliver_cards(now)
            return []
        self.scan(now)
        made = self.make_drafts(now)
        if self.followup:
            made += self.make_followups(now)
        if self.hints:
            self.make_hint_versions(now)      # версии по пояснениям (NIGHT0710-B2)
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
                    self._on_echo(number, rid, now, text=text, ts_msg=ts_m, wamid=wamid, msg_type=msg_type)
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

    def _on_echo(self, number, rid, now, text=None, ts_msg=None, wamid=None, msg_type=None):
        after, words = self._greet(number, rid, text, ts_msg)
        if after is not None:
            # автоприветствие — не ответ человека: паузы нет, черновик жив, done_upto не трогаем
            self.db.execute("INSERT OR IGNORE INTO autogreet(row_id, number, wamid, ts_msg, after, ts) "
                            "VALUES(?,?,?,?,?,?)", (rid, number, wamid, ts_msg, after, now))
            self.log("эхо строки %d: автоприветствие (%s) — паузы нет, черновик жив, первый вопрос открыт"
                     % (rid, words))
            return
        # фото, видео, документ с телефона — ответ человека, но паузы не ставит (WAPAUSEMEDIA0410)
        pause = wa_kind.echo_pauses(msg_type)
        self.log("эхо строки %d: не автоприветствие (%s) — %s" % (
            rid, words, "пауза" if pause else "вид %s, паузы нет (WAPAUSEMEDIA0410)" % wa_kind._type(msg_type)))
        self._client(number)
        self._bump(number)
        # человек ответил на всё, что было до его эха: эти входящие закрыты
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?", (number,))
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], SUPERSEDED, "снят: ответили с телефона %s" % hm_phuket(now), now)
        self._withdraw(number, SUPERSEDED, "снят до срока: ответили с телефона %s — отложенное не уходит"
                       % hm_phuket(now), now, before=rid)
        if pause:
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
                why, claims = draft_why(out)                         # низ карточки (WACARDUI0510)
            except Exception as e:                                   # noqa: BLE001
                self.log("модель упала: %s" % type(e).__name__)
                text, hand, card, why, claims = None, [], None, "", None
            if not isinstance(text, str) or not text.strip():
                self.db.execute("UPDATE clients SET next_try=? WHERE number=?",
                                (now + MODEL_RETRY_SEC, number))
                continue
            # пока думала модель, клиент мог написать ещё или человек ответить — не пишем
            if self._fresh(number, upto):
                continue
            cur = self.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, handoff, ctx, "
                                  "question, q_lang, why, claims) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)",
                                  (number, PENDING, text, upto, now,
                                   json.dumps(hand, ensure_ascii=False) if hand else None, ctx,
                                   card["question"] if card else None, card["q_lang"] if card else None,
                                   why, None if claims is None else json.dumps(claims, ensure_ascii=False)))
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

    def _pausing_echo(self, number, after_id):
        """id первого эха с телефона после after_id, которое ставит паузу (`wa_kind.echo_pauses`), или None.
        Те же признаки «ответ человека», что у `_fresh`; фото, видео, документ паузы не дают (WAPAUSEMEDIA0410)."""
        q = self._queue()
        try:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid FROM wa_inbox "
                             "WHERE from_number=? AND id > ? ORDER BY id", (number, after_id)).fetchall()
        finally:
            q.close()
        for rid, msg_type, echo, history, wamid in rows:
            if (self._live_kind(msg_type, echo, history) == wa_kind.KIND_ECHO and wa_kind.echo_pauses(msg_type)
                    and not self._our_wamid(wamid) and not self._greeted(rid)):
                return rid
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

    def press(self, draft_id, ver, action, who, now=None, who_id=None):
        """Нажатие кнопки карточки. → {"ok": bool, "state": …, "words": …}. who_id — id Telegram нажавшего
        (NIGHT0710-B2): по нему и только по нему судится «владелец» на версии по пояснению."""
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
        if action == ACT_SEND and not self._door_open():
            # дверь выключена (WA_SEND): ДО захвата — черновик остаётся pending, кнопки живы
            row = self.db.execute("SELECT state, ver FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if row and row[0] == PENDING and row[1] == int(ver):
                self.log("черновик %d: «Отправить» — отправка выключена, черновик ждёт" % draft_id)
                return {"ok": False, "state": PENDING,
                        "words": "отправка выключена — черновик ждёт, кнопки живы"}
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        if action == ACT_SEND and self.templates:
            # шаблоны (NIGHT0710-B3g): окно 24 ч закрыто — ДО захвата, черновик ждёт, на карточке — шаблон
            closed = self._send_closed(draft_id, ver, who, now)
            if closed:
                return closed
        n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=? "
                            "WHERE id=? AND state='pending' AND ver=?",
                            (target, who, now, draft_id, int(ver))).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number, upto, text = self.db.execute("SELECT number, upto_id, text FROM drafts WHERE id=?",
                                             (draft_id,)).fetchone()
        if action == ACT_SEND:
            hand = self.handoff(draft_id)
            if hand:                     # «нужен человек» (WACARDUI0510): замка нет — решил человек, след в журнале
                self.log(SEND_HAND_LOG % (draft_id, int(ver), len(hand), who))
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
                # черновик снят любым эхом с телефона; пауза — только если среди них есть ставящее её
                try:
                    prid = self._pausing_echo(number, upto)
                except Exception as e:                               # noqa: BLE001
                    prid = rid                # очередь не прочитана — как до WAPAUSEMEDIA0410: пауза
                    self.log("черновик %d: вид эха не прочитан (%s) — пауза, как прежде" % (draft_id, type(e).__name__))
                if prid is not None:
                    self._pause(number, prid, now)
            return {"ok": False, "state": state, "words": "не отправлено: " + (
                "ответили с телефона" if state == SUPERSEDED else "клиент написал ещё")}

        # ── пояснение → правило (NIGHT0710-B2): нажатие выиграно и не снято — до ритма и двери: одобрено содержание
        # версии, отказ WhatsApp одобрения не отменяет; одно место на «сразу» и «на срок», send_due правил не рождает
        rule = self._lesson_on_send(draft_id, int(ver), who, who_id, now) if self.hints else None

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
                return self._rule_words({"ok": True, "state": SCHEDULED, "words": words}, rule)
        return self._rule_words(self._deliver(draft_id, number, upto, text, who, now, CLAIMED), rule)

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
        if (state == NOT_SENT and self.templates and res.get("window") == "closed"
                and self._window(number)[0] == "closed"):
            # шаблоны (NIGHT0710-B3g): окно закрылось между пробой ядра и воротами двери (граница 24 ч, срок ритма) —
            # дверь отказала ДО сети; черновик назад в pending, на карточке — «📨 Отправить шаблоном», как у «Отправить»
            # при закрытом окне. Иначе черновик умер бы not_sent, а шаблон по нему не предлагался бы вовсе.
            if self.db.execute("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL WHERE id=? AND state=?",
                               (PENDING, draft_id, SENDING)).rowcount == 1:
                ver = self.db.execute("SELECT ver FROM drafts WHERE id=?", (draft_id,)).fetchone()[0]
                self.log("черновик %d: дверь — окно 24 ч закрылось при отправке, черновик ждёт, шаблон к месту" % draft_id)
                closed = self._send_closed(draft_id, ver, who, now)
                if closed:
                    return closed
                return {"ok": False, "state": PENDING, "words": "окно 24 ч закрылось при отправке — черновик ждёт"}
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
        if state == LESSON_REJECTED:
            return "уже решено: №%d отклонено: %s, %s" % (int(lesson_id), by, hm_phuket(at))
        return "урок №%d — кандидат" % int(lesson_id)

    def _lesson_deny(self, lesson_id, what):
        return "отказ: %s вправе только владелец или список WA_AGENT_LESSON_ADMINS — урок №%d не тронут" % (
            what, int(lesson_id))

    def lesson_promote(self, lesson_id, who, who_id, now=None):
        """«Сделать правилом»: кандидат → действующий, только тем, кто в праве. → {"ok", "state", "words"}.
        Правило из пояснения (NIGHT0710-B2) решает только владелец по id (`_hint_decide`)."""
        now = self.clock() if now is None else now
        if self._lesson_kind(lesson_id) == KIND_HINT:
            return self._hint_decide(lesson_id, LESSON_ACTIVE, who, who_id, now)
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
        # правило из пояснения (NIGHT0710-B2): откат — только владелец по id; список WA_AGENT_LESSON_ADMINS не действует
        hint = self._lesson_kind(lesson_id) == KIND_HINT
        if not (self.owner(who_id) if hint else self.lesson_admin(who_id)):
            self.log("урок %d: откат — отказ, нет права: %s" % (int(lesson_id), who))
            return {"ok": False, "state": None, "words": (self._hint_deny if hint else self._lesson_deny)(
                lesson_id, "откатить урок")}
        n = self.db.execute("UPDATE lessons SET state=?, rolled_by=?, rolled_at=?, rolled_by_id=? WHERE id=? AND "
                            "state IN (?,?)", (LESSON_ROLLED, who, now, _int_or_none(who_id), int(lesson_id),
                                               LESSON_ACTIVE, LESSON_CANDIDATE)).rowcount
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

    # ── пояснение → правило (NIGHT0710-B2) ───────────────────────────────────────────────────

    def owner(self, who_id):
        """Владелец ли нажавший: id Telegram строго в `LESSON_OWNER_IDS` (= splinter.OWNER_IDS). Имя не читается
        нигде; список WA_AGENT_LESSON_ADMINS здесь не действует. Нет id — не владелец."""
        uid = _int_or_none(who_id)
        return uid is not None and uid in LESSON_OWNER_IDS

    def _lesson_kind(self, lesson_id):
        row = self.db.execute("SELECT kind FROM lessons WHERE id=?", (int(lesson_id),)).fetchone()
        return row[0] if row else None

    def _hint_deny(self, lesson_id, what):
        return "отказ: %s вправе только владелец (по id Telegram) — №%d не тронут" % (what, int(lesson_id))

    def hint(self, draft_id, ver, text, who, who_id=None, msg_id=None, now=None):
        """Пояснение к версии черновика (реплай на приглашение «Исправить»). Модель здесь не зовётся: пояснение
        встаёт в очередь `hints`, версию делает такт (`make_hint_versions`) — приём обновлений не ждёт модели,
        рестарт пояснения не теряет. Одно пояснение на версию. → {"ok", "words"[, "hint"]}."""
        now = self.clock() if now is None else now
        if not self.hints:
            return {"ok": False, "words": HINT_OFF_WORDS}
        text = (text or "").strip()
        cut = len(text) > HINT_MAX                          # A9f: длинное режется — автору говорим, не молча
        text = text[:HINT_MAX]
        if not text:
            return {"ok": False, "words": "не принято: нужен текст пояснения"}
        row = self.db.execute("SELECT text FROM drafts WHERE id=? AND state=? AND ver=?",
                              (draft_id, PENDING, int(ver))).fetchone()
        if row is None:
            return {"ok": False, "words": "не принято: " + self._decided(draft_id, ver)}
        if self.draft_kind(draft_id) == KIND_FOLLOW:
            return {"ok": False, "words": "не принято: напоминание по пояснению не переписывается — поправьте его "
                                          "полным текстом реплаем на карточку"}
        cur = self.db.execute("INSERT OR IGNORE INTO hints(draft_id, ver_from, text, prev_text, author, author_id, "
                              "msg_id, ts, state) VALUES(?,?,?,?,?,?,?,?,?)",
                              (draft_id, int(ver), text, row[0], who, _int_or_none(who_id), msg_id, now, HINT_WAIT))
        if cur.rowcount != 1:
            # A12 (NIGHT0710-B2, круг 2): пояснение к этой версии уже было и кончилось сбоем (модель упала, клиент
            # написал) — черновик всё ещё ждёт на той же версии, значит новое пояснение законно. Строка `fail`
            # возвращается в очередь условным UPDATE (state='fail'): ждущее или сделанное пояснение не трогается.
            old = self.db.execute("SELECT id FROM hints WHERE draft_id=? AND ver_from=? AND state=?",
                                  (draft_id, int(ver), HINT_FAIL)).fetchone()
            if old is None or self.db.execute(
                    "UPDATE hints SET text=?, prev_text=?, author=?, author_id=?, msg_id=?, ts=?, state=?, "
                    "reason=NULL, done_at=NULL, ver_to=NULL WHERE id=? AND state=?",
                    (text, row[0], who, _int_or_none(who_id), msg_id, now, HINT_WAIT, old[0],
                     HINT_FAIL)).rowcount != 1:
                return {"ok": False, "words": "не принято: пояснение к версии %d уже есть — ждите версию %d" % (
                    int(ver), int(ver) + 1)}
            hid = old[0]
            self.log("черновик %d: пояснение %d к версии %d повторно после сбоя (%s, %d симв.)" % (
                draft_id, hid, int(ver), who, len(text)))
        else:
            hid = cur.lastrowid
            self.log("черновик %d: пояснение %d к версии %d (%s, %d симв.)" % (draft_id, hid, int(ver), who,
                                                                           len(text)))
        return {"ok": True, "hint": hid,
                "words": "пояснение №%d принято%s — агент делает версию %d" % (
                    hid, " (обрезано до %d симв. — длиннее в правило не идёт)" % HINT_MAX if cut else "",
                    int(ver) + 1)}

    def _hint_fail(self, hint_id, words, now):
        """Версии по пояснению нет: `fail` с причиной, ответ словами на сообщение пояснения."""
        if self.db.execute("UPDATE hints SET state=?, reason=?, done_at=? WHERE id=? AND state=?",
                           (HINT_FAIL, words[:300], now, hint_id, HINT_WAIT)).rowcount == 1:
            self.log("пояснение %d: версии нет — %s" % (hint_id, words.split(" — ")[0]))
            self._tg("hint_note", hint_id, "пояснение №%d: %s" % (hint_id, words))

    def make_hint_versions(self, now):
        """Версии по пояснениям, по HINTS_PER_TICK за такт. Модель (`Model.redraft`) переписывает черновик с учётом
        пояснения; новая версия — тем же условным UPDATE, что у правки текстом (state='pending' AND ver=?), прежняя
        карточка «устарело», новая — через очередь доставки. Черновик снят или сменил версию, клиент написал, модель
        не дала текста — версии нет (`_hint_fail`). → [(черновик, новая версия)]."""
        out = []
        rows = self.db.execute("SELECT id, draft_id, ver_from, text, prev_text, author FROM hints WHERE state=? "
                               "ORDER BY id LIMIT ?", (HINT_WAIT, HINTS_PER_TICK)).fetchall()
        for hid, did, v_from, hint_text, prev, author in rows:
            cur = self.db.execute("SELECT number, upto_id, state, ver, card_id FROM drafts WHERE id=?",
                                  (did,)).fetchone()
            if not cur or cur[2] != PENDING or cur[3] != v_from:
                self._hint_fail(hid, "устарело — " + self._decided(did, v_from), now)
                continue
            number, upto, _state, _ver, card_was = cur
            try:
                got = self.model.redraft(number, upto, prev, hint_text)
                new_text, reasons = draft_out(got)
                tr = draft_card(got)
            except Exception as e:                                   # noqa: BLE001
                self.log("пояснение %d: модель упала: %s" % (hid, type(e).__name__))
                new_text, reasons, tr = None, [], None
            if not isinstance(new_text, str) or not new_text.strip():
                self._hint_fail(hid, "модель не дала текста — версии нет; полный текст — реплаем на карточку", now)
                continue
            if self._fresh(number, upto):
                self._hint_fail(hid, "клиент написал ещё — версии нет, черновик пересобирается", now)
                continue
            v_to = v_from + 1
            if self.db.execute("UPDATE drafts SET text=?, ver=?, handoff=? WHERE id=? AND state=? AND ver=?",
                               (new_text, v_to, json.dumps(reasons, ensure_ascii=False) if reasons else None, did,
                                PENDING, v_from)).rowcount != 1:
                self._hint_fail(hid, "устарело — " + self._decided(did, v_from), now)
                continue
            self.db.execute("UPDATE hints SET state=?, ver_to=?, done_at=? WHERE id=?", (HINT_DONE, v_to, now, hid))
            self.log("черновик %d: версия %d по пояснению %d (%d симв.)" % (did, v_to, hid, len(new_text)))
            if tr and (tr["q_ru"] or tr["a_ru"]):
                self.db.execute("INSERT OR REPLACE INTO draft_tr(draft_id, ver, a_sha, q_ru, a_ru, ts) "
                                "VALUES(?,?,?,?,?,?)", (did, v_to, text_sha(new_text), tr["q_ru"], tr["a_ru"], now))
            self._card_close(did, v_from, "устарело: версия %d по пояснению №%d — %s" % (v_to, hid, author), now,
                             card_was)
            self.db.execute("UPDATE drafts SET card_id=NULL WHERE id=? AND ver=?", (did, v_to))
            self._card_new(did, v_to, now)
            out.append((did, v_to))
        return out

    def hint_of(self, draft_id, ver):
        """Версия сделана по пояснению → (номер пояснения, текст, автор) | None (версия модели или правка текстом)."""
        return self.db.execute("SELECT id, text, author FROM hints WHERE draft_id=? AND ver_to=? AND state=?",
                               (draft_id, int(ver), HINT_DONE)).fetchone()

    def _lesson_on_send(self, draft_id, ver, who, who_id, now):
        """«Отправить» выиграно на версии по пояснению: нажал владелец (`owner`, строго по id) — пояснение становится
        действующим правилом; сотрудник — кандидатом в суточный список. Версия модели и правка текстом правила не
        рождают. Одно правило на версию: UNIQUE(draft_id, ver_to). → (номер, состояние) | None. Сбой — строка
        журнала и None: обучение отправке не мешает."""
        try:
            src = self.db.execute("SELECT id, ver_from, text, prev_text, author, author_id FROM hints "
                                  "WHERE draft_id=? AND ver_to=? AND state=?", (draft_id, ver, HINT_DONE)).fetchone()
            if src is None:
                return None
            hid, v_from, hint_text, prev, author, author_id = src
            sent = self.db.execute("SELECT text FROM drafts WHERE id=?", (draft_id,)).fetchone()[0]
            boss = self.owner(who_id)
            state = LESSON_ACTIVE if boss else LESSON_CANDIDATE
            uid = _int_or_none(who_id)
            cur = self.db.execute(
                "INSERT OR IGNORE INTO lessons(state, author, author_id, ts, draft_id, ver_from, ver_to, was_text, "
                "now_text, kind, hint, sent_by, sent_by_id, sent_at, decided_by, decided_by_id, decided_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (state, author, author_id, now, draft_id, v_from, ver, prev, sent, KIND_HINT, hint_text, who, uid,
                 now, who if boss else None, uid if boss else None, now if boss else None))
            if cur.rowcount != 1:
                had = self.db.execute("SELECT id, state FROM lessons WHERE draft_id=? AND ver_to=?",
                                      (draft_id, ver)).fetchone()
                return tuple(had) if had else None
            lid = cur.lastrowid
            self.log("правило %d: %s по пояснению %d (черновик %d, версия %d, нажал %s)" % (
                lid, "действующее" if boss else "кандидат", hid, draft_id, ver, who))
            if boss:
                self._tg("lesson_card", lid)          # сообщение правила с «Откатить №N»
            return lid, state
        except Exception as e:                                       # noqa: BLE001
            self.log("правило по пояснению не записано (черновик %d): %s" % (draft_id, type(e).__name__))
            return None

    @staticmethod
    def _rule_words(res, rule):
        """Ответ нажатию + номер правила или кандидата (NIGHT0710-B2). Правила нет — ответ прежний."""
        if not rule:
            return res
        lid, state = rule
        res = dict(res)
        res["rule"] = lid
        res["words"] = "%s · %s" % (res.get("words"), "правило №%d — действует, идёт в промпт агента" % lid
                                    if state == LESSON_ACTIVE else
                                    "пояснение — кандидат №%d: решит владелец в суточном списке" % lid)
        return res

    def _hint_decide(self, lesson_id, state, who, who_id, now):
        """Кандидат-пояснение → действующее правило или отклонено: только владелец по id. → {"ok", "state", "words"}."""
        lid = int(lesson_id)
        what = "сделать правилом" if state == LESSON_ACTIVE else "отклонить"
        if not self.hints:
            return {"ok": False, "state": None, "words": "%s — №%d не тронут" % (HINT_OFF_WORDS, lid)}
        if not self.owner(who_id):
            self.log("правило %d: %s — отказ, не владелец: %s" % (lid, what, who))
            return {"ok": False, "state": None, "words": self._hint_deny(lid, what)}
        n = self.db.execute("UPDATE lessons SET state=?, decided_by=?, decided_by_id=?, decided_at=? WHERE id=? AND "
                            "state=? AND kind=?", (state, who, _int_or_none(who_id), now, lid, LESSON_CANDIDATE,
                                                   KIND_HINT)).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._lesson_decided(lid)}
        self.log("правило %d → %s (%s)" % (lid, state, who))
        self._tg("lesson_done", lid, "%s — %s, %s" % ("✅ действующее правило" if state == LESSON_ACTIVE
                                                      else "✖ отклонено", who, hm_phuket(now)), state)
        return {"ok": True, "state": state, "words": "№%d — %s" % (lid, "действующее правило: идёт в промпт агента"
                                                                    if state == LESSON_ACTIVE
                                                                    else "отклонено: в промпт агента не идёт")}

    def lesson_reject(self, lesson_id, who, who_id, now=None):
        """«Отклонить» кандидата-пояснение из суточного списка: только владелец по id. Урок правкой текстом так не
        решается — у него «Откатить»."""
        now = self.clock() if now is None else now
        if self._lesson_kind(lesson_id) != KIND_HINT:
            return {"ok": False, "state": None, "words": "№%d — не пояснение: отклонения нет" % int(lesson_id)}
        return self._hint_decide(lesson_id, LESSON_REJECTED, who, who_id, now)

    def _meta_get(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _meta_set(self, key, value):
        self.db.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(value)))

    def hint_list_due(self, now):
        """Суточный список владельцу: раз в сутки по Пхукету, после `hint_hour`, если есть не показанные новые
        правила или кандидаты из пояснений, — одно сообщение рук (`hint_list`). Замок «один список в сутки» — meta,
        переживает рестарт и ставится только по доставке; не ушёл — повтор не раньше HINT_LIST_RETRY.
        Не поместившиеся в список строки остаются на следующий. → [показанные номера] | None."""
        local = float(now) + PHUKET_OFFSET               # время по Пхукету арифметикой: функций времени ядро не зовёт
        day = int(local // 86400)
        if local % 86400 < self.hint_hour * 3600 or self._meta_get(HINT_LIST_KEY) == str(day):
            return None
        nxt = self._meta_get(HINT_LIST_NEXT)
        if nxt is not None and float(nxt) > now:
            return None
        ids = [r[0] for r in self.db.execute("SELECT id FROM lessons WHERE kind=? AND listed_at IS NULL AND state IN "
                                             "(?,?) ORDER BY id", (KIND_HINT, LESSON_CANDIDATE, LESSON_ACTIVE))]
        if not ids:
            return None
        shown = self._tg("hint_list", ids)
        if not shown:
            self._meta_set(HINT_LIST_NEXT, now + HINT_LIST_RETRY)
            self.log("суточный список: не ушёл — повтор не раньше %d с" % HINT_LIST_RETRY)
            return None
        self.db.execute("UPDATE lessons SET listed_at=? WHERE id IN (%s)" % ",".join("?" * len(shown)),
                        (now,) + tuple(int(x) for x in shown))
        self._meta_set(HINT_LIST_KEY, day)
        self.log("суточный список: строк %d из %d" % (len(shown), len(ids)))
        return shown

    def hint_counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM hints GROUP BY state").fetchall())

    def _card(self, draft_id):
        row = self.db.execute("SELECT card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    def card_extra(self, draft_id, ver, text):
        """Вопрос и перевод для карточки версии ver с текстом text (WACARDQ0410) → None (вопроса нет: черновик старше
        или напоминание — карточка прежняя) | {question, q_lang, q_ru, a_ru, tr_ver}: переводы — только этой версии
        с этим текстом; tr_ver — версия, к которой перевод есть, если он не к этой."""
        row = self.db.execute("SELECT question, q_lang, why, claims FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return None
        # как считал агент (WACARDUI0510): только у версии модели (1); у версии человека и у черновика старше — нет
        agent = row[2] is not None and int(ver) == 1
        if row[0] is None and not agent:
            return None
        out = {"question": row[0], "q_lang": row[1] or None, "q_ru": None, "a_ru": None, "tr_ver": None,
               "agent": agent, "why": row[2] if agent else None, "claims": claims_of(row[3]) if agent else None}
        if row[0] is not None:
            rows = self.db.execute("SELECT ver, a_sha, q_ru, a_ru FROM draft_tr WHERE draft_id=?",
                                   (draft_id,)).fetchall()
            out["q_ru"], out["a_ru"], out["tr_ver"] = tr_pick(rows, ver, text)
        return out

    def handoff(self, draft_id):
        row = self.db.execute("SELECT handoff FROM drafts WHERE id=?", (draft_id,)).fetchone()
        hand = handoff_of(row[0]) if row else []
        return [UNREAD_REASON] if hand is None else hand

    # ── шаблон после 24 часов (NIGHT0710-B3g) ─────────────────────────────────────────────

    def _tpl_table(self):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tpl_out'").fetchone() is not None

    def _window(self, number):
        """Окно 24 ч клиента — пробой двери (`Door.window`, правило `wa_send.last_inbound_ts`/`window_state`; своего
        правила у ядра нет) → (open | closed | unknown, возраст последнего входящего, с | None). Пробы нет или она
        упала — unknown: не измерено — не «закрыто»."""
        probe = getattr(self.door, "window", None)
        if probe is None:
            return "unknown", None
        try:
            got = probe(number)
        except Exception as e:                                       # noqa: BLE001
            self.log("дверь: проба окна упала: %s — окно неизвестно" % type(e).__name__)
            return "unknown", None
        if isinstance(got, str):
            return got, None
        got = got or {}
        return str(got.get("state") or "unknown"), got.get("age")

    def _text_lang(self, text):
        """Язык текста версии по правилу службы (`lang_of`): ru | en | other | None (букв нет, правила нет, упало)."""
        try:
            return self.lang_of(text) if self.lang_of else None
        except Exception as e:                                       # noqa: BLE001
            self.log("язык шаблона: правило упало: %s" % type(e).__name__)
            return None

    def _tpl_lang(self, text, q_lang):
        """Язык шаблона — язык КЛИЕНТА: язык его вопроса (drafts.q_lang, вердикт кода по буквам) первым; не записан
        или не ru/en — язык текста версии (`lang_of`). Клиенту уходит текст шаблона, а не версии, поэтому латиница
        в версии (модель, цена «THB/day») язык клиента не перебивает. Не ru и не en — None: шаблонов на нём нет."""
        for cand in (q_lang, self._text_lang(text)):
            if cand in ("ru", "en"):
                return cand
        return None

    def _tpl_nolang(self, text, q_lang):
        """Почему шаблона нет по языку — словами: язык не определён (ни вопроса, ни букв в версии) ≠ «не ru и не en»."""
        if not q_lang and self._text_lang(text) is None:
            return "язык клиента не определён (язык вопроса не записан, в тексте версии букв нет) — шаблон не предлагается"
        return "язык клиента не ru и не en — шаблоны поданы только на них"

    def _tpl_taken(self, draft_id, number, upto):
        """Шаблон по этому черновику или этому клиенту после того же входящего уже уходил (sending, sent, unsure) →
        (черновик, состояние, кто, когда) | None. not_sent — не уходил: можно ещё раз."""
        if not self._tpl_table():
            return None
        return self.db.execute("SELECT draft_id, state, who, ts FROM tpl_out WHERE (draft_id=? OR (number=? AND "
                               "upto_id>=?)) AND state IN (?,?,?) ORDER BY ts DESC LIMIT 1",
                               (draft_id, number, upto, SENDING, SENT, UNSURE)).fetchone()

    @staticmethod
    def _tpl_decided(taken):
        if not taken:
            return "шаблон уже уходил — второй раз не шлём"
        did, state, who, ts = taken
        return "шаблон уже %s (черновик №%d): %s, %s — второй раз не шлём, ждём ответа клиента" % (
            {SENT: "ушёл", UNSURE: "уходил, исход неизвестен", SENDING: "уходит"}.get(state, state), int(did),
            who or "—", hm_phuket(ts))

    def template_offer(self, draft_id, ver=None):
        """Шаблон к карточке → None (не к месту: выключено, черновик не ждёт, напоминание, дверь закрыта, окно не
        измерено ЗАКРЫТЫМ) | {"name", "lang", "params"} — кнопка «📨 Отправить шаблоном» | {"why": слова} — окно
        закрыто, а шаблона нет (язык не ru/en, шаблон уже уходил)."""
        if not self.templates:
            return None
        row = self.db.execute("SELECT number, state, ver, kind, text, q_lang, upto_id FROM drafts WHERE id=?",
                              (draft_id,)).fetchone()
        if not row or row[1] != PENDING or (ver is not None and int(ver) != row[2]):
            return None
        number, _state, _ver, kind, text, q_lang, upto = row
        if kind == KIND_FOLLOW:                       # напоминание молчащему вне окна — уже рассылка, не предлагаем
            return None
        if not self._door_open():
            return None
        if self._window(number)[0] != "closed":
            return None
        taken = self._tpl_taken(draft_id, number, upto)
        if taken:
            return {"why": self._tpl_decided(taken)}
        lang = self._tpl_lang(text, q_lang)
        if lang is None:
            return {"why": self._tpl_nolang(text, q_lang)}
        return {"name": TPL_REPLY, "lang": lang, "params": [TPL_WORD[lang]]}

    def _send_closed(self, draft_id, ver, who, now):
        """«✅ Отправить» при ИЗМЕРЕННО закрытом окне 24 ч: ДО захвата — черновик pending, клиенту ничего, на карточке
        словами — почему и «📨 Отправить шаблоном», если он к месту. Окно открыто или не измерено — None: путь
        прежний (дверь судит окно сама)."""
        row = self.db.execute("SELECT number, state, ver FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[1] != PENDING or row[2] != int(ver):
            return None
        state, age = self._window(row[0])
        if state != "closed":
            return None
        offer = self.template_offer(draft_id, ver)
        button = offer if offer and offer.get("name") else None
        try:
            ago = " (последнее сообщение клиента %d ч назад)" % (int(float(age)) // 3600) if age is not None else ""
        except (TypeError, ValueError):
            ago = ""
        words = W_TPL_CLOSED % ago + (
            "; на карточке «📨 Отправить шаблоном» %s (%s)" % (button["name"], button["lang"]) if button
            else "; шаблона нет: %s — напишите клиенту с телефона" % offer["why"] if offer and offer.get("why")
            else "; напишите клиенту с телефона")
        self.log("черновик %d: «Отправить» — окно 24 ч закрыто, черновик ждёт, %s" % (
            draft_id, "шаблон предложен" if button else "шаблона нет"))
        self._tg("card_tpl", draft_id, self._card(draft_id), int(ver),
                 "%s — нажал %s, %s" % (words, who, hm_phuket(now)), button)
        return {"ok": False, "state": PENDING, "words": words}

    def press_template(self, draft_id, ver, who, now=None):
        """«📨 Отправить шаблоном» → {"ok", "state", "words"}. Шаблон — ОДИН на черновик и последнее входящее клиента:
        `sending` пишется ДО двери, исход sent · not_sent (можно ещё раз) · unsure (не повторяем; рестарт посреди —
        unsure). Ушедший — в `outbox` (эхо не ставит паузу, история видит «мы»). Черновик остаётся pending: клиент
        ответит — окно откроется, черновик пересоберётся и уйдёт обычной кнопкой. Отказ — словами на карточке."""
        now = self.clock() if now is None else now
        if not self.templates:
            return {"ok": False, "state": None, "words": TPL_OFF_WORDS}
        if not self._door_open():
            return {"ok": False, "state": None, "words": "отправка выключена (WA_SEND) — шаблон не отправлен"}
        row = self.db.execute("SELECT number, state, ver, upto_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[1] != PENDING or row[2] != int(ver):
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number, upto = row[0], row[3]
        old = self._outdated(draft_id)
        if old:
            return {"ok": False, "state": PENDING, "words": "устарело: %s — шаблон не нужен, черновик пересоберётся" % old}
        # ── перепроверка очереди ДО двери, как у «✅ Отправить» (WADRAFTSAFE0210): ответили с телефона, клиент написал
        #    ещё или клиент на паузе (человек вмешался) — шаблон не уходит; очередь не прочитана — наружу ничего ──
        try:
            fresh = self._fresh(number, upto)
        except Exception as e:                                       # noqa: BLE001
            self.log("черновик %d: очередь не прочитана при нажатии шаблона (%s) — шаблон не отправлен, черновик ждёт"
                     % (draft_id, type(e).__name__))
            return {"ok": False, "state": PENDING,
                    "words": "очередь не прочитана — шаблон не отправлен, черновик ждёт: нажмите ещё раз"}
        paused = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        if fresh or (paused and paused[0]):
            kind, rid = fresh or (wa_kind.KIND_ECHO, None)
            state = SUPERSEDED if kind == wa_kind.KIND_ECHO else STALE
            why = ("ответили с телефона" if fresh and state == SUPERSEDED else "клиент написал ещё" if fresh
                   else "человек вмешался, клиент на паузе")
            self._close(draft_id, state, "снят при нажатии «📨»: %s — шаблон не отправлен" % why, now)
            if state == SUPERSEDED and rid is not None:
                self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?", (number,))
                try:
                    prid = self._pausing_echo(number, upto)   # «📨»: та же пауза, что у «Отправить»
                except Exception as e:                               # noqa: BLE001
                    prid = rid                # очередь не прочитана — как у «Отправить»: пауза
                    self.log("черновик %d: вид эха не прочитан (%s) — пауза, как прежде" % (draft_id, type(e).__name__))
                if prid is not None:
                    self._pause(number, prid, now)
            return {"ok": False, "state": state, "words": "шаблон не отправлен: " + why}
        offer = self.template_offer(draft_id, ver)
        if not offer:
            win = self._window(number)[0]
            return {"ok": False, "state": PENDING, "words": (
                "окно 24 ч открыто — шаблон не нужен, жмите «✅ Отправить»" if win == "open"
                else "окно 24 ч не измерено — шаблон не шлём" if win != "closed"
                else "к этому черновику шаблон не предлагается")}
        if offer.get("why"):
            return {"ok": False, "state": PENDING, "words": "шаблон не отправлен: " + offer["why"]}
        name, lang, params = offer["name"], offer["lang"], list(offer["params"])
        # ── захват: sending ДО двери; not_sent — можно ещё раз, остальное — нет ──
        if self.db.execute("INSERT OR IGNORE INTO tpl_out(draft_id, number, upto_id, ver, name, lang, state, who, ts) "
                           "VALUES(?,?,?,?,?,?,?,?,?)",
                           (draft_id, number, upto, int(ver), name, lang, SENDING, who, now)).rowcount != 1:
            if self.db.execute("UPDATE tpl_out SET state=?, number=?, upto_id=?, ver=?, name=?, lang=?, who=?, ts=?, "
                               "reason=NULL, wamid=NULL, tries=tries+1 WHERE draft_id=? AND state=?",
                               (SENDING, number, upto, int(ver), name, lang, who, now, draft_id,
                                NOT_SENT)).rowcount != 1:
                return {"ok": False, "state": PENDING,
                        "words": self._tpl_decided(self._tpl_taken(draft_id, number, upto))}
        try:
            res = self.door.send_template(number, name, lang, params) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = _DOOR_STATE.get(res.get("outcome"), UNSURE)
        wamid = res.get("wamid") if state == SENT else None
        reason = str(res.get("reason") or "")
        body = res.get("text") or "[шаблон %s (%s)]" % (name, lang)
        self.db.execute("UPDATE tpl_out SET state=?, reason=?, wamid=?, body=? WHERE draft_id=? AND state=?",
                        (state, reason[:300], wamid, body, draft_id, SENDING))
        if state == SENT:
            self._sent_out(wamid, number, body, VIA_TEMPLATE, now)
        hm = hm_phuket(now)
        if state == SENT:
            card_w = ("📨 шаблон %s (%s) ушёл: %s, %s — клиенту: «%s». Ответит клиент — окно откроется, черновик "
                      "пересоберётся и уйдёт обычной «✅ Отправить»" % (name, lang, who, hm, body[:300]))
            words = "шаблон ушёл (%s, %s) — ждём ответа клиента" % (name, lang)
        elif state == NOT_SENT:
            card_w = "📨 шаблон не отправлен: %s — %s, %s; черновик ждёт, кнопки живы" % (
                reason[:400] or "причина не названа", who, hm)
            words = "шаблон не отправлен: " + (reason[:170] or "причина не названа")
        else:
            card_w = "📨 шаблон: %s — %s, %s" % (W_UNSURE, who, hm)
            words = "шаблон: " + W_UNSURE
        self.log("черновик %d: шаблон %s (%s) → %s%s" % (
            draft_id, name, lang, state, ", одобрение %s" % res.get("approval") if res.get("approval") else ""))
        self._tg("card_tpl", draft_id, self._card(draft_id), int(ver), card_w, offer if state == NOT_SENT else None)
        if state in (SENT, UNSURE):
            self.show_agent(now)              # ушедший шаблон — строкой в тему клиента (WAMIRROR0410): эха у него нет
        return {"ok": state == SENT, "state": state, "words": words}

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
