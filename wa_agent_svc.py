#!/usr/bin/env python3
"""СЛУЖБА wa-agent — сборка в один процесс: ядро (`wa_agent.Core`), руки Telegram (`wa_agent_tg.Tg`),
дверь отправки текста (`wa_send.send_text`) и реакции наружу (`wa_send.send_reaction`) (WAAGENTSVC0210).

КЛЮЧИ — тем же путём, что у службы показа и двери: `wa_tg_mirror._env()` (load_dotenv корня дерева,
очередь, база показа, `WA_TG_BOT_TOKEN`, `WA_TG_CHAT_ID`), ключ 360dialog дверь берёт сама
(`wa_send.api_key`). Значения ключей не печатаются нигде — в строке старта только «есть/нет».

ВЫКЛЮЧАТЕЛИ — все по умолчанию ВЫКЛЮЧЕНЫ (включает только явное 1/true/yes/on):
  WA_AGENT_DRAFTS — модель и черновики. Выключен — модель не зовётся, курсор идёт за очередью
                    (`Core.follow`). Включён без адаптера модели — всё равно выключен, словами в старте.
  WA_AGENT_CARDS  — карточки и нажатия в «Агентах».
  WA_AGENT_REACT  — реакции из тем показа наружу клиенту.
  WA_SEND         — дверь. Выключена — «Отправить» отвечает «отправка выключена» ДО двери
                    (`Core.press` спрашивает `SendDoor.is_open`), черновик ждёт.
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

ROOT = os.path.dirname(os.path.abspath(__file__))
SUMMARY_EVERY = 300                       # сводка числами раз в 5 минут
F_DRAFTS, F_CARDS, F_REACT, F_SEND = "WA_AGENT_DRAFTS", "WA_AGENT_CARDS", "WA_AGENT_REACT", "WA_SEND"
FLAGS = (F_DRAFTS, F_CARDS, F_REACT, F_SEND)
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
            "agent_db": os.environ.get("WA_AGENT_DB", os.path.join(base, "wa_agent.db")),
            "log_path": os.environ.get("WA_AGENT_LOG", os.path.join(ROOT, "wa_agent.log"))}


class SendDoor(wa_agent.Door):
    """Дверь текста: `wa_send.send_text` с очередью службы (окно 24 ч, ключ, три исхода — там).
    `is_open` — ручка WA_SEND тем же правилом, что у двери (`wa_send.send_enabled`)."""

    def __init__(self, queue_path, environ=None, send=None):
        self.queue_path = queue_path
        self.environ = environ if environ is not None else os.environ
        self.send = send or wa_send.send_text

    def is_open(self):
        return wa_send.send_enabled(self.environ)

    def send_text(self, to, text):
        if not self.is_open():
            return {"outcome": wa_send.NOT_SENT, "reason": DOOR_OFF_WORDS, "wamid": None}
        return self.send(to, text, db_path=self.queue_path)


class NoModel(wa_agent.Model):
    """Адаптера модели нет: текста нет никогда. Служба с ним черновики не включает."""

    def draft(self, number, upto_id):
        return None


def build(env, environ=None, model=None, http=None, send=None, react_send=None, clock=time.time,
          line=None):
    """Собрать ядро и руки. model=None — адаптера нет, черновики выключены при любом WA_AGENT_DRAFTS.
    → (core, tg, flags, words): flags — запрошенные, words — действующие состояния словами."""
    environ = environ if environ is not None else os.environ
    line = line or (lambda s: log.info("%s", s))
    flags = flags_of(environ)
    drafts = flags[F_DRAFTS] and model is not None
    tg = wa_agent_tg.Tg(env.get("tg_token"), enabled=flags[F_CARDS], show_chat=env.get("show_chat"),
                        mirror_db=env.get("mirror_db"), http=http, clock=clock, log=line,
                        react=flags[F_REACT], react_send=react_send)
    door = SendDoor(env["queue_db"], environ=environ, send=send)
    core = wa_agent.Core(env["agent_db"], env["queue_db"], model or NoModel(), tg, door, clock=clock,
                         log=line, drafts=drafts)
    tg.bind(core)
    words = {
        F_DRAFTS: ("вкл" if drafts else "выкл") + ("" if drafts or not flags[F_DRAFTS]
                                                   else " (флаг 1, адаптера модели нет)"),
        F_CARDS: ("вкл" if tg.enabled else "выкл") + ("" if tg.enabled or not flags[F_CARDS]
                                                      else " (флаг 1, ключа бота нет)"),
        F_REACT: ("вкл" if tg.react else "выкл") + ("" if tg.react or not flags[F_REACT]
                                                    else " (флаг 1, ключа бота нет)"),
        F_SEND: "вкл" if door.is_open() else "выкл",
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
    return ("сводка: %s · черновики %s · карточек %d · на паузе %d · реакций наружу %s · опросов ok=%d "
            "сбой=%d 409=%d · тактов %d упало %d"
            % (" ".join("%s=%s" % (k, words[k].split(" ")[0]) for k in FLAGS), _pairs(core.counts()),
               cards, paused, _pairs(reacts), tg.polls["ok"], tg.polls["fail"], tg.polls["conflict"],
               stats.get("ticks", 0), stats.get("tick_fail", 0)))


def serve(core, tg, words, should_stop, clock=time.time, sleep=time.sleep, every=SUMMARY_EVERY,
          line=None):
    """Цикл службы: `wa_agent_tg.run` + сводка раз в `every` секунд (первая — сразу)."""
    line = line or (lambda s: log.info("%s", s))
    stats, last = {}, [None]

    def on_turn(now):
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
    core, tg, _flags, words = build(env)
    log.info("%s", start_line(env, words))
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    stats = serve(core, tg, words, lambda: bool(stop))
    log.info("wa-agent: остановлен (тактов %d)", stats.get("ticks", 0))


if __name__ == "__main__":
    main()
