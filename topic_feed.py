"""Лента темы обслуживания на диске (01.10.2026, задание Штаба 0091-76h, SPLTOPICFEED0110).

ЗАЧЕМ. Разговорный мозг в теме байка решал почти вслепую: видел только свой диалог с владельцем/
Пымом (`memory.db.conversations`, 12 строк, 48 ч), буфер разбора фото (3 ч, память процесса) и
открытое важное. Сообщений механиков, своих же вопросов с id, реплаев и того, что легло в учёт, он
не видел, а перезапуск стирал и то немногое (живой случай NMAX 155 BLACK 8952: фото 30.09 → вопрос
«Вижу пробег 38872» → перезапуск → реплай «38972» через 19 ч ушёл в мозг, тот переспросил).
Лента — память темы на сервере: каждое событие строкой, переживает перезапуск.

ХРАНИЛИЩЕ. Каталог `topic_feed/` рядом с модулем (подмена — `TOPIC_FEED_DIR`; у прогона тестов —
свой каталог на процесс, как у прочих файлов состояния splinter). Файл на тему:
`<chat>_<topic>.jsonl`, строка JSON на событие, ТОЛЬКО дописывается — удаления и перезаписи нет.
Поля события:
  chat, topic       — чат и тема (тема None → 0)
  mid               — id сообщения Telegram (у события учёта — id сообщения-основания, если есть)
  ts                — время события, unix-секунды (у входящего — время сообщения в Telegram)
  role              — staff | pym | owner | bot
  kind              — text | photo | button | bot_ask | bot_msg | record | vision
  reply_to          — id сообщения, на которое это реплай (служебное «тема создана» реплаем не считается)
  text              — краткий текст, не длиннее TEXT_MAX
  + поля вида: hint (вид подсказки), km / questioned_km / what / done / failed / source (учёт),
    mileage / conf / photo_kind / n (разбор фото)

FAIL-SAFE. Ни одна функция модуля не бросает и не ждёт: запись — один `open(..., "a")` без
блокировок, сбой → одна строка журнала и `False`, сообщение идёт дальше прежним путём.
Откат: `TOPIC_FEED=0` (не писать) и/или `TOPIC_FEED_CONTEXT=0` (не давать мозгу) + рестарт.
"""
import json
import logging
import os
import time as _time

log = logging.getLogger("splinter")

KINDS = ("text", "photo", "button", "bot_ask", "bot_msg", "record", "vision")
# Решения решателя в тени (0094-76k, SPLDECIDER0110). Читатель по умолчанию их ПРОПУСКАЕТ: контекст
# мозга и окно последних событий одинаковы с тенью и без неё; видеть их — `read(..., shadow=True)`.
SHADOW_KINDS = ("decision",)
ROLES = ("staff", "pym", "owner", "bot")
TEXT_MAX = 300
_TEST_MARKS = ("PRETOOL_NOPUSH", "PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PYTEST_CURRENT_TEST")
_SAID = {"path": False, "fail": 0.0}


def _flag(name, default="1"):
    return str(os.getenv(name, default)).strip().lower() not in ("0", "false", "no", "off", "")


def write_enabled():
    """`TOPIC_FEED=0` → лента не пишется (поведение до 01.10)."""
    return _flag("TOPIC_FEED")


def context_enabled():
    """`TOPIC_FEED_CONTEXT=0` → мозг получает прежний контекст байт в байт."""
    return _flag("TOPIC_FEED_CONTEXT")


def feed_dir():
    p = os.getenv("TOPIC_FEED_DIR")
    if not p:
        p = (f"/tmp/topic_feed_test_{os.getpid()}"
             if any(os.getenv(m) for m in _TEST_MARKS)
             else os.path.join(os.path.dirname(os.path.abspath(__file__)), "topic_feed"))
    if not _SAID["path"]:
        _SAID["path"] = True
        log.info(f"  🧵 лента темы: каталог {p}")
    return p


def _norm_topic(topic):
    try:
        return int(topic) if topic not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def path_for(chat, topic):
    return os.path.join(feed_dir(), f"{int(chat)}_{_norm_topic(topic)}.jsonl")


def _short(text, n=TEXT_MAX):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _fail(what, e):
    # не чаще строки в минуту: при лежащем диске журнал не захлёбывается
    now = _time.time()
    if now - _SAID["fail"] >= 60:
        _SAID["fail"] = now
        log.warning(f"  🧵 лента темы: {what} не удалось ({type(e).__name__}: {e}) — сообщение идёт дальше")


def append(chat, topic, kind, *, mid=None, ts=None, role="", reply_to=None, text="", **extra):
    """Дописать событие. Не бросает. `True` — записано; `None` — НЕ записано (выключено или сбой:
    причина в журнале). `None`, а не `False`: «не знаю, легло ли» не выдаётся за ответ «нет»
    (храповик слепых читателей, `blind_readers.py`)."""
    if not write_enabled():
        return None
    try:
        ev = {"chat": int(chat), "topic": _norm_topic(topic),
              "mid": (int(mid) if mid is not None else None),
              "ts": float(ts if ts is not None else _time.time()),
              "role": role or "", "kind": kind,
              "reply_to": (int(reply_to) if reply_to is not None else None),
              "text": _short(text)}
        for k, v in extra.items():
            if v is not None and v != "" and v != []:
                ev[k] = v
        d = feed_dir()
        os.makedirs(d, exist_ok=True)
        with open(path_for(chat, topic), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        _fail(f"запись события {kind}", e)
        return None


def read(chat, topic, *, days=7, limit=30, now=None, shadow=False):
    """Последние `limit` событий темы не старше `days` суток, по времени. Не бросает.
    Файла нет → `[]` (в теме ещё не было событий — это ответ). Сбой чтения → `None` («не знаю»):
    контекст скажет «лента не прочитана», а не «событий 0». События тени (`SHADOW_KINDS`) — только
    при `shadow=True`."""
    try:
        p = path_for(chat, topic)
        now = _time.time() if now is None else now
        horizon = now - days * 86400
        out = []
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue          # оборванная строка не губит ленту
                    if not isinstance(ev, dict) or float(ev.get("ts") or 0) < horizon:
                        continue
                    if ev.get("chat") != int(chat) or ev.get("topic") != _norm_topic(topic):
                        continue          # чужая тема в чужом файле не появится, но проверяем поле
                    if not shadow and ev.get("kind") in SHADOW_KINDS:
                        continue          # решение тени — не событие темы: мозг его не видит
                    out.append(ev)
        out.sort(key=lambda e: float(e.get("ts") or 0))
        return out[-limit:] if limit else out
    except Exception as e:
        _fail("чтение ленты", e)
        return None


def find(chat, topic, mid, *, days=30):
    """Событие темы с этим id сообщения (последнее по времени), либо None."""
    if mid is None:
        return None
    for ev in reversed(read(chat, topic, days=days, limit=0) or ()):
        if ev.get("mid") == int(mid) and ev.get("kind") != "vision":
            return ev
    return None


def reply_to_of(msg):
    """id сообщения, на которое реплай; служебное «тема создана» реплаем не считается."""
    r = getattr(msg, "reply_to_message", None)
    if r is None or getattr(r, "forum_topic_created", None):
        return None
    return getattr(r, "message_id", None)


def msg_ts(msg):
    d = getattr(msg, "date", None)
    try:
        return d.timestamp() if d is not None else None
    except Exception:
        return None


_ROLE_RU = {"staff": "сотрудник", "pym": "Пым", "owner": "владелец", "bot": "бот"}
_KIND_RU = {"text": "текст", "photo": "фото", "button": "кнопка", "bot_ask": "вопрос бота",
            "bot_msg": "ответ бота", "record": "запись в учёт", "vision": "разбор фото"}


def render_event(ev, tz_shift_h=7):
    """Строка события для мозга: время Пхукета, роль, вид, id, реплай, суть."""
    try:
        t = _time.strftime("%d.%m %H:%M", _time.gmtime(float(ev.get("ts") or 0) + tz_shift_h * 3600))
    except Exception:
        t = "?"
    head = f"{t} [{_ROLE_RU.get(ev.get('role'), ev.get('role') or '?')}] {_KIND_RU.get(ev.get('kind'), ev.get('kind'))}"
    if ev.get("mid") is not None:
        head += f" #{ev['mid']}"
    if ev.get("reply_to") is not None:
        head += f" ↩#{ev['reply_to']}"
    bits = []
    k = ev.get("kind")
    if k == "vision":
        if ev.get("mileage"):
            bits.append(f"пробег {ev['mileage']}" + (f" (уверенность {ev['conf']})" if ev.get("conf") else ""))
        if ev.get("photo_kind"):
            bits.append(f"снимок: {ev['photo_kind']}")
        if ev.get("n"):
            bits.append(f"фото {ev['n']}")
    elif k == "record":
        if ev.get("what"):
            bits.append(str(ev["what"]))
        if ev.get("km") is not None:
            bits.append(f"км {ev['km']}")
        if ev.get("questioned_km") is not None and str(ev.get("questioned_km")) != str(ev.get("km")):
            bits.append(f"спрашивали {ev['questioned_km']}")
        if ev.get("done"):
            bits.append("работы " + ",".join(map(str, ev["done"])))
        if ev.get("failed"):
            bits.append("не легло " + ",".join(map(str, ev["failed"])))
    elif k == "bot_ask" and ev.get("hint"):
        bits.append(f"вид {ev['hint']}")
    if ev.get("text"):
        bits.append(f"«{ev['text']}»")
    return head + (": " + " · ".join(bits) if bits else "")
