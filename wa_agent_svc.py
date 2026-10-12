#!/usr/bin/env python3
"""СЛУЖБА wa-agent — сборка в один процесс: ядро (`wa_agent.Core`), руки Telegram (`wa_agent_tg.Tg`),
дверь отправки текста (`wa_send.send_text`) и реакции наружу (`wa_send.send_reaction`) (WAAGENTSVC0210).

КЛЮЧИ — тем же путём, что у службы показа и двери: `wa_tg_mirror._env()` (load_dotenv корня дерева,
очередь, база показа, `WA_TG_BOT_TOKEN`, `WA_TG_CHAT_ID`), ключ 360dialog дверь берёт сама
(`wa_send.api_key`). Значения ключей не печатаются нигде — в строке старта только «есть/нет».

ВЫКЛЮЧАТЕЛИ — все по умолчанию ВЫКЛЮЧЕНЫ (включает только явное 1/true/yes/on):
  WA_AGENT_DRAFTS — модель и черновики. Выключен — модель не зовётся, курсор идёт за очередью
                    (`Core.follow`). Включён — `main` собирает адаптер `wa_agent_model` (WAAGENTMODEL0210);
                    адаптер не собрался (нет ключа, моста) — выключен, словами в старте.
  WA_AGENT_CARDS  — карточки и нажатия в «Агентах».
  WA_AGENT_REACT  — реакции из тем показа наружу клиенту.
  WA_AGENT_RELAY  — текст человека из темы клиента → клиенту в WhatsApp; «Отправить» — строкой в теме
                    (WARELAYTEXT0210); медиа из темы своим видом (WARELAYMEDIA0210). Дверь та же — WA_SEND.
  WA_SEND        — дверь. Выключена — «Отправить» отвечает «отправка выключена» ДО двери
                    (`Core.press` спрашивает `SendDoor.is_open`), черновик ждёт.
  WA_AGENT_WATCH — ожидание «клиент без ответа» (`wa_watch.Watch`, WAUNANSWERED0210): последнее
                    сообщение клиента без нашего ответа дольше порога — одно сообщение в «Агенты».
                    Читателя getUpdates не заводит; от черновиков, пауз и двери не зависит.
                    Порог — настройка WA_AGENT_WATCH_SEC (секунды, по умолчанию 600 = 10 мин), тихие часы —
                    WA_AGENT_WATCH_QUIET «ЧЧ-ЧЧ» по Пхукету (по умолчанию выкл): тревога этих часов придёт в их
                    конце одной сводкой. Битая настройка — умолчание и строка журнала (WAWATCHTEN0210).
  WA_AGENT_PACE  — человеческий ритм «Отправить» (WAHUMANPACE0210): первый ответ беседы — не раньше 3–5 мин
                    после сообщения клиента, следующий — по длине текста; раньше срока — «уйдёт в ЧЧ:ММ» и
                    «Отменить». Выключен — «Отправить» шлёт сразу. Текст человека из темы ритм не касается.
                    Отложенное до выключения уходит в срок и при выключенном.
  WA_AGENT_LESSONS — уроки людей (WAAGENTLESSON0210): «Исправить» с другим текстом пишет кандидата урока,
                    «Сделать правилом» переводит его в действующие, действующие идут в промпт агента,
                    «Откатить №N» убирает. Выключен — «Исправить» как раньше, уроков в промпте нет.
  WA_AGENT_FOLLOWUP — напоминание притихшему (WAFOLLOWUP0210): 15 мин тишины клиента после нашего сообщения,
                    окно 24 ч открыто — черновик-напоминание модели на «Отправить» (не больше двух на беседу);
                    модель вправе сказать «не нужно». Выключен — притихших не ищем. Работает только с черновиками.
  WA_AGENT_BOOK_READ — брони ТОЛЬКО на чтение (WABOOKTOOLS0210, `wa_book_read`): на явный вопрос «свободен ли байк
                    на даты» или «когда кончается аренда» адаптер кодом до модели читает снимок `clients`+`fleet` моста
                    (GET, в памяти 10 мин) и даёт факт с возрастом; нет факта — «нужен человек». Выключен — таблица
                    броней не читается, промпт прежний. Работает только с черновиками.
  WA_AGENT_TEMPLATES — шаблон после 24 часов (NIGHT0710-B3g): окно клиента закрыто — «✅ Отправить» отвечает словами
                    ДО захвата, карточка предлагает «📨 Отправить шаблоном» (reply_request ru/en, одобренный у Meta —
                    по ответу провайдера); проверяет и дверь (`wa_send.templates_enabled`). Выключен — как раньше.
  WA_AGENT_CACHE — кэш промпта (WAAGENTCACHE0210, `wa_agent_model`): «1h»/«5m» — срок, 1/true/yes/on — «1h»; инструкция
                    и снимки узлов знаний без возраста идут впереди одним префиксом с отметкой кэша, остальное — после.
                    Выключен (пусто или иное значение) — запрос модели прежний. Цена вызова по usage пишется всегда:
                    строкой журнала и итогом в сводку. Работает только с черновиками.
  WA_AGENT_HINTS — пояснение → правило (NIGHT0710-B2): «Исправить» зовёт пояснение текстом, такт делает по нему версию
                    моделью (карточка «💬 версия N по пояснению»); «Отправить» на ней владельца (id строго из
                    LESSON_OWNER_IDS, список WA_AGENT_LESSON_ADMINS не действует) — действующее правило с номером,
                    автором, временем, источником и откатом, сотрудника — кандидат; суточный список владельцу после
                    21:00 по Пхукету — одно сообщение. Правила идут в промпт тем же блоком уроков со следующего
                    черновика (адаптеру база агента даётся и без WA_AGENT_LESSONS). Выключен — «Исправить» и
                    «Отправить» как раньше, правил из пояснений в промпте нет. Версии по пояснению — только с черновиками.
  WA_AGENT_ATTACH — PDF договора второй частью «Отправить» (NIGHT0710-B3v, `wa_agent_attach.AttachCore`): текст и
                    подписанный PDF той же аренды двумя частями, у каждой своё подтверждение провайдера; «Дослать PDF»
                    кнопкой. Засчитывается ТОЛЬКО при черновиках и сверке Т4а (WA_AGENT_TOOLS: двери contract_pdf и
                    contract берутся из `model.tools`); без сверки — прежнее ядро и строка «флаг 1, сверки нет». PDF
                    реально приложится только при WA_AGENT_BOOK_READ (без броней аренда не станет фактом). Флаг не
                    запрошен — ни строки, ни импорта: путь прежний байт-в-байт.
НАСТРОЙКА WA_AGENT_LESSON_ADMINS — id Telegram через запятую: кто переводит урок в действующие и откатывает.
  Нет — владелец (те же id, что splinter.OWNER_IDS); битая — только владелец; исход — строкой на старте.
НАСТРОЙКА WA_AGENT_GREET_SHA256 — отпечаток текста автоприветствия WhatsApp Business (WAGREETECHO0210):
  sha256 текста или его начало от 10 знаков, несколько — через запятую; самого текста нет нигде. Эхо с
  этим отпечатком И не позже 10 с после «первого» входящего паузы не ставит, первый вопрос не закрывает.
  Нет или битая — признака нет, любое эхо ставит паузу, как раньше; исход — строкой на старте.
  Ожидание `wa_watch` берёт отпечаток отсюда же (WACHAINFIX0210); нет настройки — автоответ там ловит одно
  время (≤ 10 с после «первого» входящего).
Все выключены — ни одного вызова Telegram и двери: такт ядра читает только очередь (mode=ro).

ЦИКЛ — `wa_agent_tg.run`, один поток; читатель `getUpdates` у бота показа ОДИН — эта служба. Второй
читатель даёт 409: строка журнала на серию, опрос раз в 30 с, такт идёт, служба не падает.

КАНАЛ TELEGRAM — WA_AGENT_TG (TGCOREA0610, план TGPLAN0510 З2), по умолчанию ВЫКЛЮЧЕН: выключен — ни второго ядра,
ни его базы, ни строки журнала; служба байт-в-байт прежняя. Включён — второе ядро `wa_agent.Core` на очереди
tg_queue.db (TG_QUEUE_DB, по умолчанию рядом с этим файлом — тот же путь, что у двери приёма wa_webhook) и СВОЁМ
файле агента tg_agent.db (TG_AGENT_DB, по умолчанию рядом с wa_agent.db): курсор, смещение бота, клиенты и
черновики у двух ядер разные, номера черновиков не пересекаются по базам. Совпал файл агента или очереди с файлом
WA — канал НЕ собирается (строка журнала). У ядра TG выключены ритм, напоминание, ожидание, уроки, показ в форуме,
перенос из темы и реакции; дверь отправки закрыта насовсем (`TgDoor.is_open` → False всегда, wa_send не зовётся);
модели не даются брони и инструменты (ключ tg:<id> по цифрам дал бы чужой «телефон»). Карточки — в те же «Агенты»
тем же ботом, кнопки `tg:…`; читатель getUpdates по-прежнему ОДИН (руки WA): нажатие `tg:` и реплай на карточку
ядра TG уходят ядру TG, `wa:` — ядру WA. Строка старта канала называет его отдельной строкой.
Поверх (TGCOREC0610, проверка Штаба): сбой сборки канала (ядро, модель, прицеп к читателю) — «канал не собран: <имя
ошибки>», WA работает как при выключенном флаге; файлы агента и очереди TG не совпадают ни друг с другом, ни с
файлами WA (агент, очередь, показ, архив) — по realpath, у существующих ещё и samefile; падение такта TG — строка на
серию и строка восстановления с числом упавших тактов; карточка TG при закрытой двери — без «Отправить»; кнопки
уроков — с префиксом рук; строки модели TG — с приставкой «TG: »; сводка TG — с недоставленными карточками.
Шапка карточки TG (TGHEAD1210, предложение NIGHT0710-B4 §2.3) — «TG · @ник · имя» из raw последних TG_HEAD_LOOK рядов
ЭТОГО клиента в очереди TG (только чтение, mode=ro): ник и имя кладёт в ряд лента ПК (tg_feed.py, необязательные поля),
дверь — ряд целиком в raw. Невидимые символы (Cc/Cf/Cs) вычищаются, имя ≤ TG_HEAD_NAME_MAX, шапка ≤ TG_HEAD_MAX знаков.
Нет данных — прежняя «TG · tg:<id>» байт-в-байт; сбой чтения — она же и строка журнала с именем ошибки (без имён).

ОТПРАВКА В TELEGRAM ЧЕРЕЗ ПК — WA_AGENT_TG_SEND (TGSEND1310), по умолчанию ВЫКЛЮЧЕНА: выключена (или не запрошена) —
дверь TG закрыта насовсем, как выше, ни файла очереди, ни строки, ни импорта `tg_outbox`; канал байт-в-байт прежний.
Включена (вместе с WA_AGENT_TG) — `TgDoor` открыт: «✅ Отправить» кладёт ответ в СВОЮ очередь `tg_outbox.db`
(TG_OUTBOX_DB, по умолчанию рядом с tg_queue.db; совпал с любым файлом WA или TG — дверь закрыта, словами в старте)
и ЖДЁТ подтверждения ПК не дольше WA_AGENT_TG_SEND_SEC (по умолчанию 20 с, 5–60: не дольше бюджета отправки WhatsApp,
который цикл службы уже допускает на нажатии). Исходы: ПК подтвердил «ушло» с msg_id → sent, `wamid` = ключ эха
`tg:<chat>:<msg_id>:out` (тот, с которым эхо вернётся лентой в tg_queue.db); ПК отказал → not_sent с причиной; срок
вышел, а ПК ряд НЕ забрал → ряд отменяется атомарно (queued → cancelled), not_sent «ПК не забрал за N с — не
отправлено»; ПК забрал, но не подтвердил → unknown (UNSURE) «проверьте чат клиента перед повтором». Отменённый ряд
не выдаётся ПК ни одной дорогой. Выдачу и подтверждение несёт вход `wa_webhook` (/tg-queue/outbox, /tg-queue/ack;
тот же Bearer, что у /tg-queue/push). Выключатель ОДИН — этот: вход его не читает, а судит по пульсу двери в очереди
(`TgSendCore.tick` пишет его каждым тактом); нет пульса `tg_outbox.DOOR_FRESH` с — ПК слышит «отправка выключена»,
выдача пуста. Своё эхо — `TgSendCore`: эхо с
ключом нашей отправки не ответ человека (ни паузы, ни снятия черновиков); подтверждение пришло после срока двери —
сверка по id сообщения из очереди; id не известен вовсе (исход unknown) — тот же текст в том же чате в окне 15 мин,
одно эхо на одну отправку. Эхо человека с телефона — как было.

ЖУРНАЛ — файл `wa_agent.log` (или WA_AGENT_LOG): только id, состояния и числа; сводка числами раз в
5 минут. Текстов, номеров и имён клиентов в журнале нет. При включённых черновиках сводка несёт очередь
карточек и число ждущих черновиков без доставленной карточки (WADRAFTSAFE0210). Ответ Telegram неизвестен —
отдельным полем: отправка карточки (возможна вторая карточка) и правка исхода (не подтверждена) (WACARDDONEFIX0210).
"""

import json
import logging
import os
import re
import signal
import time
import unicodedata
import uuid

import wa_agent
import wa_agent_tg
import wa_send
import wa_watch

ROOT = os.path.dirname(os.path.abspath(__file__))
SUMMARY_EVERY = 300                       # сводка числами раз в 5 минут
F_DRAFTS, F_CARDS, F_REACT, F_SEND = "WA_AGENT_DRAFTS", "WA_AGENT_CARDS", "WA_AGENT_REACT", "WA_SEND"
F_RELAY = "WA_AGENT_RELAY"                # тема клиента → WhatsApp (WARELAYTEXT0210)
F_WATCH = "WA_AGENT_WATCH"                # ожидание «клиент без ответа» (WAUNANSWERED0210)
F_GREET = "WA_AGENT_GREET_SHA256"         # отпечаток текста автоприветствия (WAGREETECHO0210)
F_PACE = "WA_AGENT_PACE"                  # человеческий ритм «Отправить» (WAHUMANPACE0210)
F_LESSONS = "WA_AGENT_LESSONS"            # уроки людей из «Исправить» (WAAGENTLESSON0210)
F_LESSON_ADMINS = "WA_AGENT_LESSON_ADMINS"  # кто переводит урок в действующие и откатывает; пусто — владелец
F_FOLLOW = "WA_AGENT_FOLLOWUP"            # напоминание притихшему (WAFOLLOWUP0210)
F_HINTS = "WA_AGENT_HINTS"                # пояснение → правило (NIGHT0710-B2), по умолчанию выключен
F_BOOK = "WA_AGENT_BOOK_READ"             # брони только на чтение: наличие и конец аренды (WABOOKTOOLS0210)
F_CACHE = "WA_AGENT_CACHE"                # кэш промпта: срок «1h»/«5m» или выкл (WAAGENTCACHE0210)
F_TOOLS = "WA_AGENT_TOOLS"                # инструменты чтения и журнал сверки (AGENTLOOPA0310); выкл — один вызов
F_ATTACH = "WA_AGENT_ATTACH"              # PDF договора второй частью «Отправить» (NIGHT0710-B3v); не в FLAGS
F_TEMPLATES = wa_send.TEMPLATES_FLAG      # шаблон после 24 часов (NIGHT0710-B3g): одно имя у ядра и двери
FLAGS = (F_DRAFTS, F_CARDS, F_REACT, F_RELAY, F_SEND, F_WATCH)
DOOR_OFF_WORDS = "отправка выключена (WA_SEND) — дверь не звана"
PRESS_BRIDGE_SEC = 60                     # бюджет плеч моста на ОДИН вызов двери договоров при нажатии (= карточки «Инфо»)
F_TG = "WA_AGENT_TG"                      # канал Telegram: второе ядро на tg_queue.db (TGCOREA0610); выкл — нет его
TG_PREFIX = "tg"                          # первое слово callback_data кнопок ядра TG
TG_DOOR_WORDS = "отправка в Telegram закрыта насовсем — ответьте клиенту сами"
TG_FAIL = "канал не собран: %s"           # сбой сборки канала TG — имя ошибки (TGCOREC0610)
F_TG_SEND = "WA_AGENT_TG_SEND"            # отправка в Telegram через ПК (TGSEND1310); по умолчанию выкл
TG_SEND_POLL = 0.5                        # дверь TG перечитывает свой ряд очереди раз в столько секунд
F_TG_GREET = "WA_AGENT_TG_GREET"          # автоприветствие TG по времени (TGGREET1310); по умолчанию вкл, «0» — выкл
TG_GREET_OFF = ("0", "off", "false", "no")
TG_GREET_SILENCE = 7 * 86400              # приветствие Telegram Business — после 7+ сут без переписки (меньший выбор)


def tg_greet_of(environ):
    """Признак автоприветствия канала TG (TGGREET1310) → (отпечатки ядра, слова). Отпечатка у TG нет: приветствие
    Telegram — картинка без текста, и её эхо через 0 с закрывало первый вопрос клиента. Признак — только время
    (`wa_agent.GREET_ANY`): эхо ≤ GREET_SEC после «первого» входящего, перед которым GREET_SILENCE тишины."""
    if str(environ.get(F_TG_GREET) or "").strip().lower() in TG_GREET_OFF:
        return (), "приветствие TG: выкл — любое эхо закрывает вопрос, как раньше"
    return ((wa_agent.GREET_ANY,),
            "приветствие TG: эхо ≤ %d с после первого входящего (до него %d сут тишины) — автоприветствие, вопрос "
            "открыт" % (wa_agent.GREET_SEC, TG_GREET_SILENCE // 86400))


# шапка карточки TG (TGHEAD1210, NIGHT0710-B4 §2.3): ник и имя клиента из raw его рядов очереди TG
TG_HEAD_LOOK = 50                         # рядов ЭТОГО клиента (от новых к старым), где ищутся ник и имя
TG_HEAD_NAME_MAX = 64                     # имя клиента в шапке, знаков (у Telegram имя и фамилия — по 64)
TG_HEAD_MAX = 128                         # шапка целиком, знаков
_TG_KEY = re.compile(r"tg:([0-9]{1,20})")            # ключ клиента канала TG (wa_webhook.tg_row_event: «from»)
_TG_NICK = re.compile(r"[A-Za-z0-9_]{1,32}")         # ник Telegram: латиница, цифры, «_», не длиннее 32
_TG_HIDDEN = frozenset(("Cc", "Cf", "Cs"))           # невидимые: управляющие, формата (направление письма), суррогаты
# буквы, видимые как «ничего»: заполнители хангыля U+115F U+1160 U+3164 U+FFA0 и пустой брайль U+2800 (в исходнике —
# кодами: невидимых знаков в тексте программы нет)
_TG_FILLERS = frozenset(chr(c) for c in (0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800))
_TG_WS = re.compile(r"\s+")

log = logging.getLogger("wa_agent")


def flags_of(environ):
    """Четыре выключателя → {имя: bool}. Нет имени или не 1/true/yes/on — выключен."""
    return {name: wa_agent_tg.flag_on(environ.get(name)) for name in FLAGS}


def env_of():
    """Пути и ключ бота тем же путём, что у службы показа (`wa_tg_mirror._env`)."""
    import wa_tg_mirror
    env = wa_tg_mirror._env()
    base = os.path.dirname(os.path.abspath(env["queue_db"]))
    return {"queue_db": env["queue_db"], "mirror_db": env["state_db"],
            "tg_token": env["tg_token"], "show_chat": env["tg_chat"],
            "archive_db": env.get("archive_db"), "archive_manifest": env.get("archive_manifest"),
            "archive_media": env.get("archive_media"),
            "agent_db": os.environ.get("WA_AGENT_DB", os.path.join(base, "wa_agent.db")),
            "log_path": os.environ.get("WA_AGENT_LOG", os.path.join(ROOT, "wa_agent.log")),
            # канал Telegram (TGCOREA0610): очередь — тот же путь, что у двери приёма (wa_webhook._env), агент — свой
            "tg_queue_db": os.environ.get("TG_QUEUE_DB", os.path.join(ROOT, "tg_queue.db")),
            "tg_agent_db": os.environ.get("TG_AGENT_DB", os.path.join(base, "tg_agent.db"))}


class SendDoor(wa_agent.Door):
    """Дверь текста: `wa_send.send_text` с очередью службы (окно 24 ч, ключ, три исхода — там).
    `is_open` — ручка WA_SEND тем же правилом, что у двери (`wa_send.send_enabled`)."""

    def __init__(self, queue_path, environ=None, send=None, send_media=None, send_template=None):
        self.queue_path = queue_path
        self.environ = environ if environ is not None else os.environ
        self.send = send or wa_send.send_text
        self.media = send_media or wa_send.send_media
        self.tpl = send_template or wa_send.send_template

    def is_open(self):
        return wa_send.send_enabled(self.environ)

    def send_text(self, to, text):
        if not self.is_open():
            return {"outcome": wa_send.NOT_SENT, "reason": DOOR_OFF_WORDS, "wamid": None}
        return self.send(to, text, db_path=self.queue_path)

    def send_media(self, to, media):
        """Медиа из темы (WARELAYMEDIA0210): `wa_send.send_media` с очередью службы — тот же путь."""
        if not self.is_open():
            return {"outcome": wa_send.NOT_SENT, "reason": DOOR_OFF_WORDS, "wamid": None}
        return self.media(to, media, db_path=self.queue_path)

    def window(self, number, now=None):
        """Окно 24 ч клиента правилом двери (NIGHT0710-B3g): `wa_send.last_inbound_ts` по очереди службы →
        `window_state`. Очередь не прочитана — unknown, а не «закрыто»."""
        scan = wa_send.last_inbound_ts(number, self.queue_path)
        if not scan.ok:
            return {"state": wa_send.WINDOW_UNKNOWN, "age": None}
        state, info = wa_send.window_state(scan.payload, time.time() if now is None else now)
        return {"state": state, "age": info.get("age")}

    def send_template(self, to, name, lang, params):
        """Шаблон (NIGHT0710-B3g): `wa_send.send_template` — WA_SEND, WA_AGENT_TEMPLATES, белый список, одобрение по
        ответу провайдера, три исхода — там."""
        if not self.is_open():
            return {"outcome": wa_send.NOT_SENT, "reason": DOOR_OFF_WORDS, "wamid": None}
        return self.tpl(to, name, lang, params, env=self.environ)


class NoModel(wa_agent.Model):
    """Адаптера модели нет: текста нет никогда. Служба с ним черновики не включает."""

    def draft(self, number, upto_id):
        return None


# ═══ канал Telegram (TGCOREA0610) ═════════════════════════════════════════════════════════

class TgDoor(wa_agent.Door):
    """Дверь ядра TG. Без очереди (`outbox=None`, по умолчанию) — закрыта НАСОВСЕМ, как была: `is_open` — False
    всегда, отправка текста и медиа — «не отправлено» словами, ни wa_send, ни сети, ни файла. Писать клиенту
    Telegram сервер сам не умеет (TGPLAN0510 п. 4) и не учится.

    С очередью (WA_AGENT_TG_SEND, TGSEND1310) — открыта: текст уходит РУКАМИ ПК. `send_text` кладёт ряд в
    `tg_outbox.db` и ждёт подтверждения ПК не дольше `wait` секунд (часы `mono`, пауза `sleep`, перечитывание раз
    в `poll`). Исход — три слова контракта `Door`, синхронно; ответ ПК → sent/not_sent/unknown; срок вышел, ряд не
    забран → отмена queued → cancelled ОДНИМ условным UPDATE и not_sent; забран без ответа → unknown. Медиа этой
    дверью не уходят (переноса из темы у канала TG нет)."""

    def __init__(self, outbox=None, wait=None, clock=time.time, mono=time.monotonic, sleep=time.sleep,
                 poll=TG_SEND_POLL, log=None):
        self.outbox = outbox
        self.wait = int(wait if wait is not None else 20)
        self.clock, self.mono, self.sleep, self.poll = clock, mono, sleep, float(poll)
        self.log = log or (lambda s: None)

    def is_open(self):
        return self.outbox is not None

    def send_text(self, to, text):
        if self.outbox is None:
            return {"outcome": wa_send.NOT_SENT, "reason": TG_DOOR_WORDS, "wamid": None}
        return self._send_via_pc(to, text)

    def send_media(self, to, media):
        if self.outbox is None:
            return {"outcome": wa_send.NOT_SENT, "reason": TG_DOOR_WORDS, "wamid": None}
        return {"outcome": wa_send.NOT_SENT, "reason": "медиа в Telegram этой дверью не уходят — только текст",
                "wamid": None}

    # ── отправка через ПК (TGSEND1310) ────────────────────────────────────────────────────

    @staticmethod
    def _out(outcome, reason, wamid=None):
        return {"outcome": outcome, "reason": reason, "wamid": wamid}

    def _final(self, row):
        """Исход ряда очереди → ответ двери; ряд ещё не решён → None."""
        import tg_outbox as O
        state = (row or {}).get("state")
        if state == O.SENT and isinstance(row.get("msg_id"), int):
            return self._out(wa_send.SENT, "ушло через userbot на ПК (сообщение %d)" % row["msg_id"],
                             O.echo_wamid(row["chat_id"], row["msg_id"]))
        if state == O.FAILED:
            return self._out(wa_send.NOT_SENT, "ПК отказал: %s — клиенту ничего не ушло"
                             % (str(row.get("error") or "причина не названа")[:160]))
        if state == O.UNKNOWN:
            return self._out(wa_send.UNKNOWN, "ПК не уверен, ушло ли (%s) — проверьте чат клиента перед повтором"
                             % (str(row.get("error") or "причина не названа")[:120]))
        if state == O.CANCELLED:
            return self._out(wa_send.NOT_SENT, "ПК не забрал за %d с — не отправлено" % self.wait)
        return None

    def _send_via_pc(self, to, text):
        import tg_outbox as O
        chat = O.chat_of(to)
        if chat is None:
            return self._out(wa_send.NOT_SENT, "ключ клиента не tg:<число> — не отправлено")
        if chat <= 0:
            return self._out(wa_send.NOT_SENT, "чат не личный — в группы и каналы агент не пишет, не отправлено")
        body = str(text or "")
        if not body.strip():
            return self._out(wa_send.NOT_SENT, "пустой текст — не отправлено")
        if O.tg_len(body) > O.TEXT_MAX:
            return self._out(wa_send.NOT_SENT, "текст %d знаков, Telegram берёт не больше %d — сократите через "
                                               "«Исправить», не отправлено" % (O.tg_len(body), O.TEXT_MAX))
        t0 = self.mono()
        token = uuid.uuid4().hex                               # свой ДО записи: отменить можно и при потерянном ответе
        try:
            rid, _ = self.outbox.put(chat, body, self.wait, token=token, now=self.clock())
        except Exception as e:                                       # noqa: BLE001
            # запись могла лечь (сбой на подтверждении транзакции) — снимаем её по своему токену
            try:
                self.outbox.cancel_queued(token, "дверь: запись не подтвердилась")
                row = self.outbox.get(token)
            except Exception:                                        # noqa: BLE001
                self.log("дверь: очередь отправки не записана и не перечитана (%s) — исход неизвестен"
                         % type(e).__name__)
                return self._out(wa_send.UNKNOWN, "очередь отправки не записана и не перечитана (%s) — проверьте "
                                                  "чат клиента перед повтором" % type(e).__name__)
            if row is None or row.get("state") == O.CANCELLED:
                return self._out(wa_send.NOT_SENT, "очередь отправки не записана (%s) — не отправлено"
                                 % type(e).__name__)
            rid = row.get("id")
        deadline = t0 + self.wait
        while True:
            try:
                fin = self._final(self.outbox.get(token))
            except Exception:                                        # noqa: BLE001 — прочтём в следующий раз
                fin = None
            if fin is not None:
                self.log("дверь: ряд %s → %s за %.1f с" % (rid, fin["outcome"], self.mono() - t0))
                return fin
            left = deadline - self.mono()
            if left <= 0:
                break
            self.sleep(min(self.poll, left))
        # срок вышел: незабранный ряд отменяется условно; забранный — дверь перестаёт ждать, исход неизвестен
        try:
            if self.outbox.cancel_queued(token, "дверь: ПК не забрал за %d с" % self.wait):
                self.log("дверь: ряд %s отменён — ПК не забрал за %d с" % (rid, self.wait))
                return self._out(wa_send.NOT_SENT, "ПК не забрал за %d с — не отправлено" % self.wait)
            row = self.outbox.get(token)
            fin = self._final(row)
            if fin is not None:
                self.log("дверь: ряд %s → %s в срок" % (rid, fin["outcome"]))
                return fin
            if (row or {}).get("state") == O.CLAIMED:
                self.outbox.give_up(token, now=self.clock())
                self.log("дверь: ряд %s забран ПК, подтверждения за %d с нет — исход неизвестен" % (rid, self.wait))
                return self._out(wa_send.UNKNOWN, "ПК забрал, но не подтвердил за %d с — проверьте чат клиента "
                                                  "перед повтором" % self.wait)
        except Exception as e:                                       # noqa: BLE001
            self.log("дверь: ряд %s — очередь не прочитана в срок (%s)" % (rid, type(e).__name__))
            return self._out(wa_send.UNKNOWN, "очередь отправки не прочитана в срок (%s) — проверьте чат клиента "
                                              "перед повтором" % type(e).__name__)
        return self._out(wa_send.UNKNOWN, "ряд очереди в непонятном состоянии — проверьте чат клиента перед повтором")


_OWN_ECHO_SCHEMA = """CREATE TABLE IF NOT EXISTS tg_own_echo (
    echo_wamid TEXT PRIMARY KEY,
    token      TEXT NOT NULL UNIQUE,
    how        TEXT NOT NULL,
    ts         REAL NOT NULL
)"""


class TgSendCore(wa_agent.Core):
    """Ядро канала TG при ОТКРЫТОЙ двери (WA_AGENT_TG_SEND, TGSEND1310). Отличий от `wa_agent.Core` два:

    1. СВОЁ ЭХО. Ушедшее через ПК вернётся лентой рядом dir=out. Прежний `_our_wamid` узнаёт его по ключу, который
       дверь вернула полем wamid (`tg:<chat>:<msg>:out` в drafts/outbox). Поверх — две дороги для случаев, когда дверь
       ключа не знала: (а) подтверждение ПК пришло ПОСЛЕ срока двери — ряд очереди `sent` с этим chat_id+msg_id;
       (б) id сообщения не известен вовсе (ПК сказал «не уверен» или молчит) — тот же текст в том же чате, очередь
       поставлена в окне [эхо − 15 мин, эхо + 2 мин]. Одна отправка закрывает не больше одного эха (`tg_own_echo`,
       UNIQUE token). Не наше или сверить нечем → прежнее «ответ человека» (пауза — направление сомнения прежнее).
    2. СЛОВА ИСХОДА. Карточка и ответ на нажатие несут причину двери (`_door_words`), а не голое состояние."""

    def __init__(self, *a, outbox=None, **kw):
        self.tg_outbox = outbox
        self._beat_fail = None
        super().__init__(*a, **kw)
        self.db.execute(_OWN_ECHO_SCHEMA)

    def tick(self, now=None):
        """Такт ядра + ПУЛЬС двери в очередь: по нему вход wa_webhook отвечает ПК «отправка включена»
        (единственный выключатель — WA_AGENT_TG_SEND у этой службы). Пульс не лёг — строка на серию, такт идёт;
        вход через DOOR_FRESH скажет ПК «выключена», и нажатие честно ответит «ПК не забрал»."""
        try:
            self.tg_outbox.beat(self.clock() if now is None else now)
            if self._beat_fail:
                self.log("дверь: пульс в очередь снова пишется")
            self._beat_fail = None
        except Exception as e:                                       # noqa: BLE001
            if self._beat_fail is None:
                self.log("дверь: пульс в очередь не записан (%s) — ПК увидит «отправка выключена»" % type(e).__name__)
            self._beat_fail = type(e).__name__
        return super().tick(now)

    def _door_words(self, state, res):
        reason = str((res or {}).get("reason") or "").strip()
        return state + (" — " + reason if reason else "")

    def _our_wamid(self, wamid):
        if super()._our_wamid(wamid):
            return True
        try:
            return self._tg_own(wamid)
        except Exception as e:                                       # noqa: BLE001
            self.log("эхо: сверка с очередью отправки не удалась (%s) — считаю ответом человека, как прежде"
                     % type(e).__name__)
            return False

    def _tg_own(self, wamid):
        import tg_outbox as O
        pe = O.parse_echo(wamid)
        if pe is None or self.tg_outbox is None:
            return False
        if self.db.execute("SELECT 1 FROM tg_own_echo WHERE echo_wamid=?", (wamid,)).fetchone():
            return True
        chat, msg = pe
        token, how = self.tg_outbox.sent_token(chat, msg), "id"
        if token is None:
            q = self._queue()
            try:
                # подпись медиа — колонка caption (вход 01.10); очередь старше её не несёт — только текст
                have = {r[1] for r in q.execute("PRAGMA table_info(wa_inbox)")}
                row = q.execute("SELECT COALESCE(text, %s''), ts_msg FROM wa_inbox WHERE wamid=? ORDER BY id LIMIT 1"
                                % ("caption, " if "caption" in have else ""), (wamid,)).fetchone()
            finally:
                q.close()
            if not row or row[1] is None:
                return False
            body, how = O.norm_text(row[0]), "text"
            used = {r[0] for r in self.db.execute("SELECT token FROM tg_own_echo")}
            token = next((t for t, txt in self.tg_outbox.maybe_sent(chat, float(row[1]))
                          if t not in used and body and O.norm_text(txt) == body), None)
            if token is None:
                return False
        n = self.db.execute("INSERT OR IGNORE INTO tg_own_echo(echo_wamid, token, how, ts) VALUES(?,?,?,?)",
                            (wamid, token, how, self.clock())).rowcount
        if n == 1:
            self.log("эхо: наша отправка через ПК (сверка %s) — не ответ человека: паузы нет, черновики живы"
                     % ("по id сообщения" if how == "id" else "по тексту"))
            return True
        return bool(self.db.execute("SELECT 1 FROM tg_own_echo WHERE echo_wamid=?", (wamid,)).fetchone())


def tg_nick(value):
    """Поле `username` ряда ленты → ник без «@» · "" (null: активного ника у клиента нет) · None (не строка или не по
    алфавиту ника Telegram — мусор, поле «неизвестно»). "" здесь — знание из ряда, а не промах: промах — None."""
    if isinstance(value, str):
        value = value.strip()
        return value if _TG_NICK.fullmatch(value) else None
    return "" if value is None else None


def _tg_visible(ch):
    cat = unicodedata.category(ch)
    return ch not in _TG_FILLERS and (cat[0] in "LNPS" or cat in ("Co", "Cn"))


def tg_clean(value, cap):
    """Поле `name` ряда ленты → одна строка без невидимых символов (Cc/Cf/Cs вычищены, пробелы и разрывы строк — один
    пробел), не длиннее cap знаков · "" (null, пусто или ни одного видимого знака — U+3164, пустой брайль) · None (не
    строка и не null — мусор, поле «неизвестно»). "" — знание из ряда, а не промах: промах — None."""
    if not isinstance(value, str):
        return "" if value is None else None
    s = "".join(" " if ch.isspace() else ch for ch in value
                if ch.isspace() or unicodedata.category(ch) not in _TG_HIDDEN)
    s = _TG_WS.sub(" ", s).strip()[:cap].rstrip()
    return s if any(_tg_visible(ch) for ch in s) else ""


def tg_head(number, raws):
    """Шапка карточки TG из raw рядов очереди ЭТОГО клиента (от новых к старым) → «TG · @ник · имя» | None.

    raw — ряд ленты ПК целиком (tg_feed.line: необязательные `username`/`name`, NIGHT0710-B4 З3; дверь кладёт его в raw,
    wa_webhook.tg_row_event). Каждое поле — из самого нового ряда, где оно ЕСТЬ: ключа нет (ряд до 07.10, собеседник не
    передан) — ищем дальше, повтор ряда старые строки не дополняет; null — «нет», поиск по полю останавливает. Ряд не
    JSON, не объект, чужой chat_id, поле не по контракту — пропуск. Ника нет — вместо него id клиента. None — сказать
    нечего: вызывающий ставит прежнюю шапку байт-в-байт. Исключений не бросает."""
    m = _TG_KEY.fullmatch(str(number))
    if not m:
        return None
    cid, nick, name = int(m.group(1)), None, None
    for raw in raws or ():
        if nick is not None and name is not None:
            break
        try:
            rec = json.loads(raw)
        except Exception:                                            # noqa: BLE001 — мусор в raw: пропуск ряда
            continue
        rid = rec.get("chat_id") if isinstance(rec, dict) else None
        if not isinstance(rid, int) or isinstance(rid, bool) or rid != cid:
            continue
        if nick is None and "username" in rec:
            nick = tg_nick(rec["username"])
        if name is None and "name" in rec:
            name = tg_clean(rec["name"], TG_HEAD_NAME_MAX)
    if not (nick or name):
        return None
    who = "@" + nick if nick else m.group(1)
    return ("TG · " + who + (" · " + name if name else ""))[:TG_HEAD_MAX].rstrip()


class TgSide(wa_agent_tg.Tg):
    """Руки ядра TG: те же карточки в «Агенты», префикс кнопок `tg`, getUpdates не зовут (reader=False).
    Шапка — «TG · @ник · имя» (TGHEAD1210, `tg_head`): ник и имя клиента из raw последних TG_HEAD_LOOK рядов ЭТОГО
    клиента в очереди TG — очередь ядра, только чтение (`Core._queue`, mode=ro). Нет данных — «TG · <ключ клиента>»
    байт-в-байт как было; сбой чтения — она же и строка журнала с именем ошибки. Темы показа у канала нет, базу показа
    WA не читаем. «Отправить» — только при открытой двери ядра (send_closed=False, решение владельца 00:59, TGCOREC0610)."""

    def _topic(self, number):
        head = "TG · " + str(number)
        if not _TG_KEY.fullmatch(str(number)):
            return head, ""
        try:
            q = self.core._queue()
            try:
                raws = [r[0] for r in q.execute(
                    "SELECT raw FROM wa_inbox WHERE from_number=? AND raw IS NOT NULL ORDER BY id DESC LIMIT ?",
                    (str(number), TG_HEAD_LOOK)).fetchall()]
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            self.log("шапка: очередь TG не прочитана — %s, шапка прежняя" % type(e).__name__)
            return head, ""
        try:
            return (tg_head(number, raws) or head), ""
        except Exception as e:                                       # noqa: BLE001 — замок: tg_head не бросает
            self.log("шапка: не собрана — %s, шапка прежняя" % type(e).__name__)
            return head, ""


class TgHands(wa_agent.Telegram):
    """Что видит ядро TG: только интерфейс карточек. Строки показа (`agent_line`) у этих рук НЕТ — `show_agent`
    ядра TG молчит по устройству; уроки — базовые «ничего»."""

    def __init__(self, side):
        self.side = side
        self.chat = side.chat

    def card(self, draft_id, ver, number, text):
        return self.side.card(draft_id, ver, number, text)

    def card_done(self, draft_id, card_id, words):
        return self.side.card_done(draft_id, card_id, words)

    def card_wait(self, draft_id, card_id, words, ver):
        return self.side.card_wait(draft_id, card_id, words, ver)

    def ask_pause(self, number, pause_no, via=None):
        return self.side.ask_pause(number, pause_no, via)


def _key(path):
    return os.path.normcase(os.path.realpath(str(path)))


def _same(a, b):
    """Один ли это файл (TGCOREC0610): realpath (регистр — по правилу ОС); у существующих — ещё и samefile
    (жёсткая ссылка, иной путь к тому же файлу). Путь не задан — не совпадает ни с чем."""
    if not a or not b:
        return False
    if _key(a) == _key(b):
        return True
    try:
        return os.path.exists(str(a)) and os.path.exists(str(b)) and os.path.samefile(str(a), str(b))
    except OSError:
        return False


TG_FILES = (("агента TG", "tg_agent_db"), ("очереди TG", "tg_queue_db"))
WA_FILES = (("агента WA", "agent_db"), ("очереди WA", "queue_db"), ("показа WA", "mirror_db"),
            ("архива WA", "archive_db"))


def tg_clash(env):
    """Совпадение файлов канала TG (TGCOREC0610): агент и очередь TG — ни друг с другом, ни с ЛЮБЫМ файлом WA
    (агент, очередь, показ, архив), не только своего рода. → слова совпадения или ''."""
    if _same(env.get("tg_agent_db"), env.get("tg_queue_db")):
        return "файл агента TG совпал с файлом очереди TG"
    for tname, tkey in TG_FILES:
        for wname, wkey in WA_FILES:
            if _same(env.get(tkey), env.get(wkey)):
                return "файл %s совпал с файлом %s" % (tname, wname)
    return ""


def tg_send_of(environ, env, clock=time.time):
    """WA_AGENT_TG_SEND (TGSEND1310) → (очередь | None, ожидание с, слова строки старта | None).
    Не запрошен — (None, 0, None): ни импорта `tg_outbox`, ни файла, ни слова — канал байт-в-байт прежний.
    Запрошен: файл очереди совпал с файлом агента/очереди TG или ЛЮБЫМ файлом WA (realpath, samefile) — дверь
    закрыта, словами; очередь не открылась — то же; иначе очередь и слова «вкл …». Исключение не бросает."""
    if not wa_agent_tg.flag_on(environ.get(F_TG_SEND)):
        return None, 0, None
    import tg_outbox
    wait, wait_words = tg_outbox.wait_of(environ.get(tg_outbox.WAIT_ENV))
    path = tg_outbox.path_of(environ, env.get("tg_queue_db") or ROOT)
    for name, key in TG_FILES + WA_FILES:
        if _same(path, env.get(key)):
            return None, wait, "флаг 1, файл исходящей TG совпал с файлом %s — отправка закрыта" % name
    try:
        outbox = tg_outbox.Outbox(path, clock=clock)
        outbox.beat()                                                # дверь открыта с этой минуты (пульс — такт ядра)
    except Exception as e:                                           # noqa: BLE001
        return None, wait, "флаг 1, очередь %s не открылась (%s) — отправка закрыта" % (
            os.path.basename(path), type(e).__name__)
    return outbox, wait, ("вкл — «Отправить» кладёт ответ в %s, userbot ПК шлёт с бизнес-аккаунта; ждём подтверждения "
                          "ПК до %s: не забрал — отменено, не ушло; забрал без ответа — исход неизвестен; вход "
                          "вебхука видит дверь по пульсу такта (нет пульса %d с — ПК слышит «выключена»)"
                          % (os.path.basename(path), wait_words, tg_outbox.DOOR_FRESH))


def build_tg(env, reader, flags, model=None, http=None, clock=time.time, line=None, greet=(), send=None,
             door_kw=None):
    """Второе ядро канала Telegram. → (ядро | None, слова). Собирается ТОЛЬКО при WA_AGENT_TG; файл агента или
    очереди TG совпал с другим файлом канала или с любым файлом WA — не собирается (смешало бы курсор, смещение,
    клиентов и номера черновиков). Исключение сборки идёт наружу — его ловит `build` (TGCOREC0610).
    send — (очередь | None, ожидание с) от `tg_send_of` (TGSEND1310): очередь есть — дверь открыта и ядро
    `TgSendCore`; нет (умолчание) — дверь закрыта насовсем и ядро прежнее `wa_agent.Core`. door_kw — часы и пауза
    двери (тесты)."""
    line = line or (lambda s: log.info("%s", s))
    tg_agent, tg_queue = env.get("tg_agent_db"), env.get("tg_queue_db")
    if not tg_agent or not tg_queue:
        return None, "канал не собран: путь файла агента или очереди TG не задан"
    clash = tg_clash(env)
    if clash:
        return None, "канал не собран: %s — смешал бы два канала" % clash
    tline = (lambda s: line("TG: " + str(s)))
    side = TgSide(env.get("tg_token"), enabled=flags[F_CARDS], http=http, clock=clock, log=tline,
                  prefix=TG_PREFIX, reader=False, send_closed=False)
    drafts = flags[F_DRAFTS] and model is not None
    outbox, wait = (send or (None, 0))[:2]
    if outbox is None:
        core = wa_agent.Core(env["tg_agent_db"], tg_queue, model or NoModel(), TgHands(side), TgDoor(), clock=clock,
                             log=tline, drafts=drafts, greet=greet, pace=False, lessons=False, followup=False)
    else:
        door = TgDoor(outbox, wait=wait, clock=clock, log=tline, **(door_kw or {}))
        core = TgSendCore(env["tg_agent_db"], tg_queue, model or NoModel(), TgHands(side), door, clock=clock,
                          log=tline, drafts=drafts, greet=greet, pace=False, lessons=False, followup=False,
                          outbox=outbox)
    core.greet_silence = TG_GREET_SILENCE
    side.bind(core)
    reader.attach(side)
    core.watch = None
    return core, ("вкл — черновики %s, карточки %s" % ("вкл" if drafts else "выкл", "вкл" if side.enabled else "выкл"))


def tg_core_of(tg):
    """Ядро TG у читателя (или None — канал выключен)."""
    side = getattr(tg, "peers", {}).get(TG_PREFIX)
    return side.core if side is not None else None


TG_DOOR_SHUT_START = "отправка закрыта насовсем (is_open всегда False)"


def tg_door_start(core):
    """Слова о двери TG для строки старта: закрыта — прежние байт-в-байт; открыта (TGSEND1310) — очередь и ожидание."""
    door = getattr(core, "door", None)
    outbox = getattr(door, "outbox", None)
    if outbox is None:
        return TG_DOOR_SHUT_START
    return ("отправка через userbot ПК открыта (%s): очередь %s, ждём подтверждения ПК до %d с"
            % (F_TG_SEND, os.path.basename(str(getattr(outbox, "path", ""))), int(getattr(door, "wait", 0))))


def tg_start_line(env, core, words):
    return ("wa-agent: канал TG (%s): %s · база агента %s (своя) · очередь %s (только чтение) · %s · ритм, "
            "напоминание, ожидание, уроки, показ, тема → клиенту и реакции выкл · кнопки %s:… — этому ядру, читатель "
            "getUpdates — один (руки WA)"
            % (F_TG, words, os.path.basename(str(env.get("tg_agent_db") or "")),
               "есть" if os.path.exists(str(env.get("tg_queue_db") or "")) else "нет", tg_door_start(core), TG_PREFIX)
            if core is not None else "wa-agent: канал TG (%s): %s" % (F_TG, words))


def make_model(env, line=None, bridge=None, call=None, lessons=False, book=False, cache=None, tools=False,
               hints=False):
    """Адаптер модели (WAAGENTMODEL0210): история — очередь и архив службы показа, знания, парк и цена —
    мост (только чтение), плательщик — платный ключ тем же путём, что у Splinter. → (модель | None, почему).
    Зовётся ТОЛЬКО при включённом WA_AGENT_DRAFTS: выключен — ни моста, ни ключа, ни модели.
    lessons — WA_AGENT_LESSONS: включён — действующие уроки из базы агента идут в промпт (WAAGENTLESSON0210).
    book — WA_AGENT_BOOK_READ: включён — снимок броней `clients`(filter=all)+`fleet` моста, GET (WABOOKTOOLS0210).
    cache — срок кэша промпта «1h»/«5m» или None (WA_AGENT_CACHE, WAAGENTCACHE0210).
    hints — WA_AGENT_HINTS (NIGHT0710-B2): правила из пояснений идут в промпт; база агента читается и без уроков."""
    import wa_agent_model
    import wa_book_read
    try:
        if bridge is None:
            import bridge_client
            bridge = bridge_client.BridgeClient()
        call = call or wa_agent_model.paid_call(env_file=os.path.join(ROOT, ".env"))
    except Exception as e:                                           # noqa: BLE001
        return None, "адаптер не собран: %s" % type(e).__name__
    model = wa_agent_model.ModelAdapter(
        env["queue_db"], call, read_doc=lambda n: bridge._call("read_doc", name=n), fleet=bridge.fleet,
        door=bridge.quote_price, archive_db=env.get("archive_db") or "",
        manifest=env.get("archive_manifest") or "", media_dir=env.get("archive_media") or "",
        agent_db=env.get("agent_db") or "", log=line or (lambda s: log.info("%s", s)),
        lessons_db=(env.get("agent_db") or "") if lessons or hints else "", hints=hints, text_lessons=lessons,
        book=wa_book_read.Snapshot(lambda: bridge.clients(filter="all"), bridge.fleet) if book else None,
        cache=cache,
        # WA_AGENT_TOOLS (AGENTLOOPA0310): двери чтения кассы и договоров; выкл — None, черновик как в 9c4aac6
        tools={"cash": bridge.tx_find, "contract": bridge.contract_find,
               "contract_pdf": bridge.contract_pdf} if tools else None)
    return model, ""


def _press_budget(seconds):
    """Общий бюджет плеч моста (`bridge_client.card_budget`) со СВОЕЙ меткой нажатия — таймаут на нажатии в журнале не
    выдаёт себя за таймаут сверки агента (второй круг); модуля нет (ПК без fcntl) — без бюджета."""
    try:
        import bridge_client
        return bridge_client.card_budget(seconds, label="нажатия PDF (двери договоров)")
    except Exception:                                                # noqa: BLE001
        import contextlib
        return contextlib.nullcontext()


def press_door(fn, budget=None):
    """Дверь моста на нажатии (NIGHT0710-B3v): вызов под общим бюджетом плеч — поток службы один, и больной мост не
    держит такт и нажатия дольше PRESS_BRIDGE_SEC на вызов (бюджет кончился — мост отвечает ok=False, PDF не уходит)."""
    budget = budget or _press_budget

    def call(*a, **kw):
        with budget(PRESS_BRIDGE_SEC):
            return fn(*a, **kw)
    return call


def attach_of(environ, drafts, model, budget=None):
    """Флаг WA_AGENT_ATTACH → (вкл?, двери {pdf_fetch, contract_find} | None, слова строки старта | None).
    Правило флага ОДНО со всеми выключателями (`flag_on`). Засчитывается только при черновиках и сверке Т4а —
    `model.tools` с дверями `contract_pdf` и `contract` (тот же клиент моста, что у сверки): без сверки любое
    «Отправить» уходило бы в stale (`W_NO_CHECK`), без двери реестра — в stale «реестр не перечитан».
    Флаг не запрошен → (False, None, None): строки старта нет, путь прежний байт-в-байт."""
    if not wa_agent_tg.flag_on(environ.get(F_ATTACH)):
        return False, None, None
    tools = getattr(model, "tools", None) if drafts else None
    if not isinstance(tools, dict) or not callable(tools.get("contract_pdf")) or not callable(tools.get("contract")):
        why = ("черновиков нет (WA_AGENT_DRAFTS выкл или адаптера модели нет)" if not drafts else
               "сверки нет (%s выкл)" % F_TOOLS if tools is None else "у сверки нет дверей contract_pdf/contract")
        return False, None, "флаг 1, %s — прежнее ядро, «Отправить» шлёт только текст" % why
    doors = {"pdf_fetch": press_door(tools["contract_pdf"], budget),
             "contract_find": press_door(tools["contract"], budget)}
    book = wa_agent_tg.flag_on(environ.get(F_BOOK))
    return True, doors, ("вкл — «Отправить» шлёт текст и подписанный PDF двумя частями, «Дослать PDF» кнопкой; "
                         "двери contract_pdf и contract — от сверки, бюджет моста %d с на вызов; брони %s"
                         % (PRESS_BRIDGE_SEC, "вкл" if book else
                            "ВЫКЛ — аренда не станет фактом, PDF не приложится, уйдёт только текст"))


def tg_model_of(env, environ, line=None):
    """Модель ядра TG (TGCOREA0610, TGCOREC0610): история — tg_queue.db, архива телефона нет; без уроков, броней и
    инструментов (ключ tg:<id> по цифрам дал бы чужой «телефон»); строки адаптера — с приставкой «TG: », чтобы их не
    читали строками модели WA. → (модель | None, почему). Исключение идёт наружу — его ловит `models_of`."""
    import wa_agent_model
    line = line or (lambda s: log.info("%s", s))
    env_t = dict(env, queue_db=env["tg_queue_db"], agent_db=env["tg_agent_db"], archive_db="",
                 archive_manifest="", archive_media="")
    return make_model(env_t, line=lambda s: line("TG: " + str(s)),
                      cache=wa_agent_model.cache_ttl_of(environ.get(F_CACHE)))


def models_of(env, environ, line=None):
    """Модели службы (то, что делает `main`): WA — при WA_AGENT_DRAFTS, вызов той же формы, что прежде; TG — при
    WA_AGENT_TG и WA_AGENT_DRAFTS (`tg_model_of`). Сбой сборки модели TG — не падение службы: имя ошибки третьим
    полем, канал не соберётся (TGCOREC0610). → (модель, почему, модель TG, почему TG, сбой TG | None)."""
    model, why = None, ""
    if flags_of(environ)[F_DRAFTS]:
        import wa_agent_model
        # WA_AGENT_TOOLS выкл — вызов той же формы, что в 9c4aac6 (без ключа tools)
        more = {"tools": True} if wa_agent_tg.flag_on(environ.get(F_TOOLS)) else {}
        if wa_agent_tg.flag_on(environ.get(F_HINTS)):
            more["hints"] = True              # WA_AGENT_HINTS (NIGHT0710-B2): выкл — вызов прежней формы
        model, why = make_model(env, lessons=wa_agent_tg.flag_on(environ.get(F_LESSONS)),
                                book=wa_agent_tg.flag_on(environ.get(F_BOOK)),
                                cache=wa_agent_model.cache_ttl_of(environ.get(F_CACHE)), **more)
    tg_model, tg_why, tg_fail = None, "", None
    if wa_agent_tg.flag_on(environ.get(F_TG)) and flags_of(environ)[F_DRAFTS]:
        try:
            tg_model, tg_why = tg_model_of(env, environ, line=line)
        except Exception as e:                                       # noqa: BLE001
            tg_fail = type(e).__name__
    return model, why, tg_model, tg_why, tg_fail


def model_line(model):
    """Строка старта о модели (WAOPUSHIGHC0510): модель, уровень и предел вызова словами — их несёт `call.settings`
    от `wa_agent_model.paid_call`; ключей в строке нет. Адаптера нет — модель не зовётся."""
    if model is None:
        return "модель: адаптера нет — модель не зовётся"
    import wa_agent_model
    return wa_agent_model.settings_words(getattr(getattr(model, "call", None), "settings", None))


def build(env, environ=None, model=None, http=None, send=None, react_send=None, clock=time.time,
          line=None, send_media=None, tg_model=None, tg_fail=None, tg_door_kw=None):
    """Собрать ядро и руки. model=None — адаптера нет, черновики выключены при любом WA_AGENT_DRAFTS.
    → (core, tg, flags, words): flags — запрошенные, words — действующие состояния словами.
    WA_AGENT_TG (TGCOREA0610) — второе ядро (`build_tg`, модель tg_model); его берут `tg_core_of(tg)`,
    words[WA_AGENT_TG] — его состояние словами. Выключен — ни ключа в words, ни строки журнала.
    Сбой сборки канала (TGCOREC0610): модель — tg_fail (имя ошибки от `models_of`), ядро или прицеп — исключение
    `build_tg`; канал НЕ собран, words[WA_AGENT_TG] = «канал не собран: <имя>», руки TG от читателя отцеплены —
    WA работает как при выключенном флаге."""
    environ = environ if environ is not None else os.environ
    line = line or (lambda s: log.info("%s", s))
    flags = flags_of(environ)
    drafts = flags[F_DRAFTS] and model is not None
    tg = wa_agent_tg.Tg(env.get("tg_token"), enabled=flags[F_CARDS], show_chat=env.get("show_chat"),
                        mirror_db=env.get("mirror_db"), http=http, clock=clock, log=line,
                        react=flags[F_REACT], react_send=react_send, relay=flags[F_RELAY], watch=flags[F_WATCH])
    door = SendDoor(env["queue_db"], environ=environ, send=send, send_media=send_media)
    # автоприветствие (WAGREETECHO0210): настройка — отпечаток, не текст; нет или битая — любое эхо — пауза
    greet, greet_words = wa_agent.greet_fps(environ.get(F_GREET))
    line("автоприветствие (%s): %s" % (F_GREET, greet_words))
    # ритм (WAHUMANPACE0210): тем же правилом, что выключатели; выключен — «Отправить» шлёт сразу
    pace = wa_agent_tg.flag_on(environ.get(F_PACE))
    line("ритм (%s): %s" % (F_PACE, "вкл — «Отправить» до срока ставит отправку на срок" if pace
                            else "выкл — «Отправить» шлёт сразу"))
    # уроки людей (WAAGENTLESSON0210): выключены — «Исправить» как раньше; право перевода — список или владелец
    lessons = wa_agent_tg.flag_on(environ.get(F_LESSONS))
    admins, admin_words = wa_agent.lesson_admins_of(environ.get(F_LESSON_ADMINS))
    line("уроки (%s): %s · право перевода и отката: %s" % (
        F_LESSONS, "вкл — «Исправить» пишет кандидата урока" if lessons else "выкл — «Исправить» как раньше",
        admin_words))
    # напоминание притихшему (WAFOLLOWUP0210): тем же правилом; без черновиков не работает (такт их не ищет)
    follow = wa_agent_tg.flag_on(environ.get(F_FOLLOW))
    # пояснение → правило (NIGHT0710-B2): выключено — «Исправить» и «Отправить» как раньше
    hints = wa_agent_tg.flag_on(environ.get(F_HINTS))
    line("пояснения (%s): %s" % (F_HINTS, "вкл — «Исправить» = пояснение агенту, версия по нему; «Отправить» "
                                          "владельца — правило, сотрудника — кандидат; суточный список после %d:00; "
                                          "право: только владелец (id)" % wa_agent.HINT_LIST_HOUR if hints
                                 else "выкл — «Исправить» как раньше"))
    line("напоминание (%s): %s" % (F_FOLLOW, ("вкл — 15 мин тишины после нашего: черновик-напоминание, "
                                              "не больше %d на беседу" % wa_agent.FOLLOW_MAX) if follow
                                   else "выкл — притихших не ищем"))
    # брони на чтение (WABOOKTOOLS0210): снимок собирает make_model; здесь — только строка старта
    line("брони (%s): %s" % (F_BOOK, "вкл — наличие и конец аренды из таблицы броней, только чтение"
                             if wa_agent_tg.flag_on(environ.get(F_BOOK)) else "выкл — таблица броней не читается"))
    # кэш промпта (WAAGENTCACHE0210): срок несёт адаптер, его собрал make_model; здесь — только строка старта
    ttl = getattr(model, "cache", None)
    line("кэш промпта (%s): %s" % (F_CACHE, "вкл, срок %s — инструкция и узлы знаний впереди с отметкой кэша" % ttl
                                   if ttl else "выкл — запрос модели как раньше"))
    line(model_line(model))                     # модель, уровень и предел (WAOPUSHIGHC0510); ключей нет
    # шаблон после 24 часов (NIGHT0710-B3g): тем же правилом; ту же ручку проверяет и дверь
    templates = wa_agent_tg.flag_on(environ.get(F_TEMPLATES))
    line("шаблоны (%s): %s" % (F_TEMPLATES, "вкл — окно 24 ч закрыто: «✅ Отправить» отвечает словами, на карточке "
                               "«📨 Отправить шаблоном» (одобренный у Meta, ru/en)" if templates
                               else "выкл — вне окна только отказ двери, как раньше"))
    # PDF клиенту (NIGHT0710-B3v): флаг не запрошен — ни строки, ни импорта; не засчитан — прежнее ядро и слова
    attach, doors, attach_words = attach_of(environ, drafts, model)
    if attach_words:
        line("PDF клиенту (%s): %s" % (F_ATTACH, attach_words))
    if attach:
        import wa_agent_attach
        core = wa_agent_attach.AttachCore(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                                          log=line, drafts=drafts, greet=greet, pace=pace, lessons=lessons,
                                          lesson_admins=admins, followup=follow, hints=hints, templates=templates,
                                          lang_of=wa_agent_tg.K.lang_of, attach=True, **doors)
    else:
        core = wa_agent.Core(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                             log=line, drafts=drafts, greet=greet, pace=pace, lessons=lessons, lesson_admins=admins,
                             followup=follow, hints=hints, templates=templates, lang_of=wa_agent_tg.K.lang_of)
    tg.bind(core)
    # ожидание (WAUNANSWERED0210): выключено — объекта нет, ни таблицы, ни чтения, ни Telegram;
    # отпечаток приветствия — тот же, что у ядра (WACHAINFIX0210); порог и тихие часы — настройки
    # (WAWATCHTEN0210): битая — умолчание (порог 600 с, тихих часов нет) и строка журнала со словом «битая»
    watch_sec, sec_words, _ = wa_watch.threshold_of(environ.get(wa_watch.F_SEC))
    quiet, quiet_words, _ = wa_watch.quiet_of(environ.get(wa_watch.F_QUIET))
    line("ожидание: порог (%s): %s · тихие часы (%s): %s" % (wa_watch.F_SEC, sec_words, wa_watch.F_QUIET,
                                                           quiet_words))
    core.watch = wa_watch.Watch(core.db, env["queue_db"], tg.watch_alarm, head=tg._head, clock=clock,
                                log=line, greet=greet, threshold=watch_sec, quiet=quiet) if tg.watch else None
    words = {
        F_DRAFTS: ("вкл" if drafts else "выкл") + ("" if drafts or not flags[F_DRAFTS]
                                                   else " (флаг 1, адаптера модели нет)"),
        F_CARDS: ("вкл" if tg.enabled else "выкл") + ("" if tg.enabled or not flags[F_CARDS]
                                                      else " (флаг 1, ключа бота нет)"),
        F_REACT: ("вкл" if tg.react else "выкл") + ("" if tg.react or not flags[F_REACT]
                                                    else " (флаг 1, ключа бота нет)"),
        F_RELAY: ("вкл" if tg.relay else "выкл") + ("" if tg.relay or not flags[F_RELAY]
                                                    else " (флаг 1, ключа бота нет)"),
        F_SEND: "вкл" if door.is_open() else "выкл",
        F_WATCH: ("вкл" if tg.watch else "выкл") + ("" if tg.watch or not flags[F_WATCH]
                                                    else " (флаг 1, ключа бота нет)"),
    }
    if wa_agent_tg.flag_on(environ.get(F_TG)):
        if tg_fail:
            words[F_TG] = TG_FAIL % tg_fail
        else:
            try:
                tg_greet, tg_greet_words = tg_greet_of(environ)
                # отправка через ПК (TGSEND1310): не запрошена — (None, 0, None), сборка и слова прежние
                outbox, wait, send_words = tg_send_of(environ, env, clock=clock)
                _tg_core, words[F_TG] = build_tg(env, tg, flags, model=tg_model, http=http, clock=clock, line=line,
                                                 greet=tg_greet, send=(outbox, wait) if outbox is not None else None,
                                                 door_kw=tg_door_kw)
                if _tg_core is not None:
                    words[F_TG] += " · " + tg_greet_words
                    if send_words:
                        words[F_TG] += " · отправка TG (%s): %s" % (F_TG_SEND, send_words)
            except Exception as e:                                   # noqa: BLE001
                tg.peers.pop(TG_PREFIX, None)                        # прицеп мог лечь до сбоя — читатель снова один
                words[F_TG] = TG_FAIL % type(e).__name__
    return core, tg, flags, words


def start_line(env, words):
    return ("wa-agent: %s · ключ бота %s · группа показа %s · очередь %s (только чтение) · база показа %s "
            "(только чтение) · читатель getUpdates — только эта служба"
            % (" ".join("%s=%s" % (k, words[k]) for k in FLAGS),
               "есть" if env.get("tg_token") else "нет", "есть" if env.get("show_chat") else "нет",
               "есть" if os.path.exists(env["queue_db"]) else "нет",
               "есть" if os.path.exists(env.get("mirror_db") or "") else "нет"))


def _pairs(d):
    return " ".join("%s=%d" % (k, d[k]) for k in sorted(d)) or "0"


def spend_words(s):
    """Итог трат адаптера модели (WAAGENTCACHE0210) — только числа."""
    return ("модель: вызовов %d · вход %d · запись в кэш %d · чтение из кэша %d · выход %d · $%.4f (без кэша $%.4f)"
            % (s["calls"], s["in"], s["cw"], s["cr"], s["out"], s["usd"], s["usd_nocache"]))


def summary(core, tg, words, stats):
    """Сводка ЧИСЛАМИ: состояния черновиков, карточки, паузы, реакции наружу, опросы, такты; траты модели."""
    spend = getattr(getattr(core, "model", None), "spend", None)
    db = core.db
    cards = db.execute("SELECT COUNT(*) FROM tg_cards").fetchone()[0]
    paused = db.execute("SELECT COUNT(*) FROM clients WHERE paused=1").fetchone()[0]
    reacts = dict(db.execute("SELECT outcome, COUNT(*) FROM tg_react_out GROUP BY outcome").fetchall())
    relays = dict(db.execute("SELECT state, COUNT(*) FROM relay GROUP BY state").fetchall())
    watch = getattr(core, "watch", None)
    return ("сводка: %s · черновики %s · карточек %d · на паузе %d · реакций наружу %s · из тем %s · "
            "опросов ok=%d сбой=%d 409=%d · тактов %d упало %d%s"
            % (" ".join("%s=%s" % (k, words[k].split(" ")[0]) for k in FLAGS), _pairs(core.counts()),
               cards, paused, _pairs(reacts), _pairs(relays), tg.polls["ok"], tg.polls["fail"], tg.polls["conflict"],
               stats.get("ticks", 0), stats.get("tick_fail", 0),
               " · тревог ожидания %s" % _pairs(watch.counts()) if watch is not None else "")
            + (" · уроков %s" % _pairs(core.lesson_counts()) if getattr(core, "lessons", False) else "")
            + (" · напоминаний %s" % _pairs(core.follow_counts()) if getattr(core, "followup", False) else "")
            + (" · пояснений %s" % _pairs(core.hint_counts()) if getattr(core, "hints", False) else "")
            + (" · %s" % spend_words(spend) if isinstance(spend, dict) else "")
            + cards_words(core) + pdf_words(core))


def pdf_words(core):
    """Части PDF по состояниям (NIGHT0710-B3v) — только у ядра с PDF-частью; иначе пусто (строка прежняя)."""
    if not getattr(core, "attach", False):
        return ""
    parts = dict(core.db.execute("SELECT state, COUNT(*) FROM pdf_parts GROUP BY state").fetchall())
    stats = dict(core.db.execute("SELECT status, COUNT(*) FROM part_status GROUP BY status").fetchall())
    return " · PDF-частей %s · статусов частей %s" % (_pairs(parts), _pairs(stats))


def cards_words(core):
    """Очередь карточек (WADRAFTSAFE0210): состояния и ждущие черновики без доставленной карточки. В сводке —
    при включённых черновиках или если такие черновики есть; иначе пусто (выключено — строка прежняя).
    «Неизвестно» отдельно (WACARDDONEFIX0210): карточки, у которых ответ Telegram на отправку терялся, — возможна
    вторая карточка, единственность не обещается; правки исхода без подтверждения. Нет таких — поля нет."""
    if not hasattr(core, "undelivered"):
        return ""
    n = core.undelivered()
    lost, unk = core.card_unknown() if hasattr(core, "card_unknown") else (0, 0)
    if not (getattr(core, "drafts", False) or n or lost or unk):
        return ""
    words = " · карточки в «Агенты» %s · черновиков без доставленной карточки %d" % (_pairs(core.card_counts()), n)
    if lost or unk:
        words += (" · ответ Telegram неизвестен: отправка карточки %d — возможна вторая карточка, единственность "
                  "не обещается; правка исхода не подтверждена %d" % (lost, unk))
    return words


class TwoCores:
    """Такт двух ядер в одном потоке (TGCOREA0610): ядро WA — как было (его падение — прежнее «такт упал» цикла),
    затем ядро TG; падение такта TG — свой счётчик (каждый такт), такт WA им не задет. Журнал (TGCOREC0610): строка
    на СЕРИЮ упавших тактов подряд и строка восстановления с их числом — канал без очереди падал бы строкой раз
    в такт."""

    def __init__(self, wa, tg, line, stats):
        self.wa, self.tg, self.line, self.stats = wa, tg, line, stats
        self.down = 0                                               # упавших тактов TG подряд

    def tick(self, now=None):
        try:
            return self.wa.tick(now)
        finally:
            try:
                self.tg.tick(now)
            except Exception as e:                                   # noqa: BLE001
                self.stats["tg_tick_fail"] = self.stats.get("tg_tick_fail", 0) + 1
                self.down += 1
                if self.down == 1:
                    self.line("TG: такт упал: %s — строка на серию; такт WA идёт, число упавших — в сводке TG"
                              % type(e).__name__)
            else:
                if self.down:
                    self.line("TG: такт снова идёт — упало тактов подряд: %d" % self.down)
                    self.down = 0


def tg_summary(tg_core, stats):
    """Сводка канала TG числами (только при включённом канале); недоставленные карточки — словами, как у WA
    (`cards_words`, TGCOREC0610)."""
    return ("сводка TG: черновики %s · карточек %d · на паузе %d · тактов TG упало %d"
            % (_pairs(tg_core.counts()), tg_core.db.execute("SELECT COUNT(*) FROM tg_cards").fetchone()[0],
               tg_core.db.execute("SELECT COUNT(*) FROM clients WHERE paused=1").fetchone()[0],
               stats.get("tg_tick_fail", 0))
            + cards_words(tg_core) + tg_send_words(tg_core))


def tg_send_words(tg_core):
    """Очередь отправки через ПК по состояниям (TGSEND1310) — только у ядра с открытой дверью; иначе пусто
    (сводка TG прежняя). Своё эхо, узнанное по id и по тексту, — числами."""
    outbox = getattr(tg_core, "tg_outbox", None)
    if outbox is None:
        return ""
    own = dict(tg_core.db.execute("SELECT how, COUNT(*) FROM tg_own_echo GROUP BY how").fetchall())
    return " · отправка через ПК %s · своё эхо %s" % (_pairs(outbox.counts()), _pairs(own))


def serve(core, tg, words, should_stop, clock=time.time, sleep=time.sleep, every=SUMMARY_EVERY,
          line=None):
    """Цикл службы: `wa_agent_tg.run` + сводка раз в `every` секунд (первая — сразу).
    Канал TG включён — такт обоих ядер (`TwoCores`) и строка «сводка TG»; выключен — цикл прежний."""
    line = line or (lambda s: log.info("%s", s))
    stats, last = {}, [None]
    watch = getattr(core, "watch", None)
    tg_core = tg_core_of(tg)

    def on_turn(now):
        if watch is not None:
            try:
                watch.tick(now)                                     # сам не чаще раза в wa_watch.EVERY
            except Exception as e:                                   # noqa: BLE001
                line("ожидание упало: %s" % type(e).__name__)
        if last[0] is None or now - last[0] >= every:
            last[0] = now
            try:
                line(summary(core, tg, words, stats))
            except Exception as e:                                   # noqa: BLE001
                line("сводка не собрана: %s" % type(e).__name__)
            if tg_core is not None:
                try:
                    line(tg_summary(tg_core, stats))
                except Exception as e:                               # noqa: BLE001
                    line("сводка TG не собрана: %s" % type(e).__name__)

    wa_agent_tg.run(core if tg_core is None else TwoCores(core, tg_core, line, stats), tg, should_stop,
                    clock=clock, sleep=sleep, log=line, on_turn=on_turn, stats=stats)
    return stats


def main():
    env = env_of()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(env["log_path"], encoding="utf-8")])
    # модели WA и TG (TGCOREC0610 — одной функцией, её и проверяет набор); сбой модели TG — канал не собран;
    # WA_AGENT_HINTS (NIGHT0710-B2) передаёт в make_model та же функция (INTEG0710)
    model, why, tg_model, tg_why, tg_fail = models_of(env, os.environ)
    core, tg, _flags, words = build(env, model=model, tg_model=tg_model, tg_fail=tg_fail)
    if model is not None and getattr(model, "tools", None) is not None:
        # новое входящее посреди сверки обрывает её (AGENTLOOPA0310): тот же признак, что ядро судит после модели
        model.fresh = lambda number, upto: core._fresh(number, upto) is not None
    log.info("%s", start_line(env, words))
    if F_TG in words:
        log.info("%s", tg_start_line(env, tg_core_of(tg), words[F_TG]))
        if tg_why:
            log.info("wa-agent: канал TG — %s, черновиков TG нет", tg_why)
    if why:
        log.info("wa-agent: WA_AGENT_DRAFTS=1, но %s — черновиков нет", why)
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    stats = serve(core, tg, words, lambda: bool(stop))
    log.info("wa-agent: остановлен (тактов %d)", stats.get("ticks", 0))


if __name__ == "__main__":
    main()
