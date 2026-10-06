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
  WA_AGENT_CACHE — кэш промпта (WAAGENTCACHE0210, `wa_agent_model`): «1h»/«5m» — срок, 1/true/yes/on — «1h»; инструкция
                    и снимки узлов знаний без возраста идут впереди одним префиксом с отметкой кэша, остальное — после.
                    Выключен (пусто или иное значение) — запрос модели прежний. Цена вызова по usage пишется всегда:
                    строкой журнала и итогом в сводку. Работает только с черновиками.
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

ЖУРНАЛ — файл `wa_agent.log` (или WA_AGENT_LOG): только id, состояния и числа; сводка числами раз в
5 минут. Текстов, номеров и имён клиентов в журнале нет. При включённых черновиках сводка несёт очередь
карточек и число ждущих черновиков без доставленной карточки (WADRAFTSAFE0210). Ответ Telegram неизвестен —
отдельным полем: отправка карточки (возможна вторая карточка) и правка исхода (не подтверждена) (WACARDDONEFIX0210).
"""

import logging
import os
import signal
import time

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
F_BOOK = "WA_AGENT_BOOK_READ"             # брони только на чтение: наличие и конец аренды (WABOOKTOOLS0210)
F_CACHE = "WA_AGENT_CACHE"                # кэш промпта: срок «1h»/«5m» или выкл (WAAGENTCACHE0210)
F_TOOLS = "WA_AGENT_TOOLS"                # инструменты чтения и журнал сверки (AGENTLOOPA0310); выкл — один вызов
F_ATTACH = "WA_AGENT_ATTACH"              # PDF договора второй частью «Отправить» (NIGHT0710-B3v); не в FLAGS
FLAGS = (F_DRAFTS, F_CARDS, F_REACT, F_RELAY, F_SEND, F_WATCH)
DOOR_OFF_WORDS = "отправка выключена (WA_SEND) — дверь не звана"
PRESS_BRIDGE_SEC = 60                     # бюджет плеч моста на ОДИН вызов двери договоров при нажатии (= карточки «Инфо»)

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
            "log_path": os.environ.get("WA_AGENT_LOG", os.path.join(ROOT, "wa_agent.log"))}


class SendDoor(wa_agent.Door):
    """Дверь текста: `wa_send.send_text` с очередью службы (окно 24 ч, ключ, три исхода — там).
    `is_open` — ручка WA_SEND тем же правилом, что у двери (`wa_send.send_enabled`)."""

    def __init__(self, queue_path, environ=None, send=None, send_media=None):
        self.queue_path = queue_path
        self.environ = environ if environ is not None else os.environ
        self.send = send or wa_send.send_text
        self.media = send_media or wa_send.send_media

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


class NoModel(wa_agent.Model):
    """Адаптера модели нет: текста нет никогда. Служба с ним черновики не включает."""

    def draft(self, number, upto_id):
        return None


def make_model(env, line=None, bridge=None, call=None, lessons=False, book=False, cache=None, tools=False):
    """Адаптер модели (WAAGENTMODEL0210): история — очередь и архив службы показа, знания, парк и цена —
    мост (только чтение), плательщик — платный ключ тем же путём, что у Splinter. → (модель | None, почему).
    Зовётся ТОЛЬКО при включённом WA_AGENT_DRAFTS: выключен — ни моста, ни ключа, ни модели.
    lessons — WA_AGENT_LESSONS: включён — действующие уроки из базы агента идут в промпт (WAAGENTLESSON0210).
    book — WA_AGENT_BOOK_READ: включён — снимок броней `clients`(filter=all)+`fleet` моста, GET (WABOOKTOOLS0210).
    cache — срок кэша промпта «1h»/«5m» или None (WA_AGENT_CACHE, WAAGENTCACHE0210)."""
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
        lessons_db=(env.get("agent_db") or "") if lessons else "",
        book=wa_book_read.Snapshot(lambda: bridge.clients(filter="all"), bridge.fleet) if book else None,
        cache=cache,
        # WA_AGENT_TOOLS (AGENTLOOPA0310): двери чтения кассы и договоров; выкл — None, черновик как в 9c4aac6
        tools={"cash": bridge.tx_find, "contract": bridge.contract_find,
               "contract_pdf": bridge.contract_pdf} if tools else None)
    return model, ""


def _press_budget(seconds):
    """Общий бюджет плеч моста (`wa_agent_model.door_budget` → `bridge_client.card_budget`); модуля нет — без бюджета."""
    try:
        import wa_agent_model
        return wa_agent_model.door_budget(seconds)
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


def model_line(model):
    """Строка старта о модели (WAOPUSHIGHC0510): модель, уровень и предел вызова словами — их несёт `call.settings`
    от `wa_agent_model.paid_call`; ключей в строке нет. Адаптера нет — модель не зовётся."""
    if model is None:
        return "модель: адаптера нет — модель не зовётся"
    import wa_agent_model
    return wa_agent_model.settings_words(getattr(getattr(model, "call", None), "settings", None))


def build(env, environ=None, model=None, http=None, send=None, react_send=None, clock=time.time,
          line=None, send_media=None):
    """Собрать ядро и руки. model=None — адаптера нет, черновики выключены при любом WA_AGENT_DRAFTS.
    → (core, tg, flags, words): flags — запрошенные, words — действующие состояния словами."""
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
    # PDF клиенту (NIGHT0710-B3v): флаг не запрошен — ни строки, ни импорта; не засчитан — прежнее ядро и слова
    attach, doors, attach_words = attach_of(environ, drafts, model)
    if attach_words:
        line("PDF клиенту (%s): %s" % (F_ATTACH, attach_words))
    if attach:
        import wa_agent_attach
        core = wa_agent_attach.AttachCore(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                                          log=line, drafts=drafts, greet=greet, pace=pace, lessons=lessons,
                                          lesson_admins=admins, followup=follow, attach=True, **doors)
    else:
        core = wa_agent.Core(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                             log=line, drafts=drafts, greet=greet, pace=pace, lessons=lessons, lesson_admins=admins,
                             followup=follow)
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


def serve(core, tg, words, should_stop, clock=time.time, sleep=time.sleep, every=SUMMARY_EVERY,
          line=None):
    """Цикл службы: `wa_agent_tg.run` + сводка раз в `every` секунд (первая — сразу)."""
    line = line or (lambda s: log.info("%s", s))
    stats, last = {}, [None]
    watch = getattr(core, "watch", None)

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

    wa_agent_tg.run(core, tg, should_stop, clock=clock, sleep=sleep, log=line, on_turn=on_turn,
                    stats=stats)
    return stats


def main():
    env = env_of()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(env["log_path"], encoding="utf-8")])
    model, why = None, ""
    if flags_of(os.environ)[F_DRAFTS]:
        import wa_agent_model
        # WA_AGENT_TOOLS выкл — вызов той же формы, что в 9c4aac6 (без ключа tools)
        more = {"tools": True} if wa_agent_tg.flag_on(os.environ.get(F_TOOLS)) else {}
        model, why = make_model(env, lessons=wa_agent_tg.flag_on(os.environ.get(F_LESSONS)),
                                book=wa_agent_tg.flag_on(os.environ.get(F_BOOK)),
                                cache=wa_agent_model.cache_ttl_of(os.environ.get(F_CACHE)), **more)
    core, tg, _flags, words = build(env, model=model)
    if model is not None and getattr(model, "tools", None) is not None:
        # новое входящее посреди сверки обрывает её (AGENTLOOPA0310): тот же признак, что ядро судит после модели
        model.fresh = lambda number, upto: core._fresh(number, upto) is not None
    log.info("%s", start_line(env, words))
    if why:
        log.info("wa-agent: WA_AGENT_DRAFTS=1, но %s — черновиков нет", why)
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    stats = serve(core, tg, words, lambda: bool(stop))
    log.info("wa-agent: остановлен (тактов %d)", stats.get("ticks", 0))


if __name__ == "__main__":
    main()
