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
Все выключены — ни одного вызова Telegram и двери: такт ядра читает только очередь (mode=ro).

ЦИКЛ — `wa_agent_tg.run`, один поток; читатель `getUpdates` у бота показа ОДИН — эта служба. Второй
читатель даёт 409: строка журнала на серию, опрос раз в 30 с, такт идёт, служба не падает.

ЖУРНАЛ — файл `wa_agent.log` (или WA_AGENT_LOG): только id, состояния и числа; сводка числами раз в
5 минут. Текстов, номеров и имён клиентов в журнале нет.
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
FLAGS = (F_DRAFTS, F_CARDS, F_REACT, F_RELAY, F_SEND, F_WATCH)
DOOR_OFF_WORDS = "отправка выключена (WA_SEND) — дверь не звана"

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


def make_model(env, line=None, bridge=None, call=None):
    """Адаптер модели (WAAGENTMODEL0210): история — очередь и архив службы показа, знания, парк и цена —
    мост (только чтение), плательщик — платный ключ тем же путём, что у Splinter. → (модель | None, почему).
    Зовётся ТОЛЬКО при включённом WA_AGENT_DRAFTS: выключен — ни моста, ни ключа, ни модели."""
    import wa_agent_model
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
        agent_db=env.get("agent_db") or "", log=line or (lambda s: log.info("%s", s)))
    return model, ""


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
    core = wa_agent.Core(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                         log=line, drafts=drafts)
    tg.bind(core)
    # ожидание (WAUNANSWERED0210): выключено — объекта нет, ни таблицы, ни чтения, ни Telegram
    core.watch = wa_watch.Watch(core.db, env["queue_db"], tg.watch_alarm, head=tg._head, clock=clock,
                                log=line) if tg.watch else None
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


def summary(core, tg, words, stats):
    """Сводка ЧИСЛАМИ: состояния черновиков, карточки, паузы, реакции наружу, опросы, такты."""
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
               " · тревог ожидания %s" % _pairs(watch.counts()) if watch is not None else ""))


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
        model, why = make_model(env)
    core, tg, _flags, words = build(env, model=model)
    log.info("%s", start_line(env, words))
    if why:
        log.info("wa-agent: WA_AGENT_DRAFTS=1, но %s — черновиков нет", why)
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    stats = serve(core, tg, words, lambda: bool(stop))
    log.info("wa-agent: остановлен (тактов %d)", stats.get("ticks", 0))


if __name__ == "__main__":
    main()
