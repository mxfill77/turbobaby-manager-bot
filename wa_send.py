#!/usr/bin/env python3
"""WA-1: отправка текста клиенту через 360dialog Direct API (production).

ЧТО ЭТО ЗА КИРПИЧ. До 06.09.2026 отправляющей двери не существовало вовсе: `wa_webhook.py`
говорит о себе «It NEVER sends any message back to WhatsApp», и это правда — VPS был чистым
транзитом. Дверь заводится ЗДЕСЬ и отдельно, чтобы транзит остался транзитом: вебхук её не
импортирует и не зовёт (проверяется тестом), решение «что ответить» по-прежнему живёт на ПК.

СЕГОДНЯ ЕЁ НИКТО НЕ ЗОВЁТ — это состояние, а не недоделка (порядок запуска KB_WA_PLAN §4:
тренажёр, потом канал). Модуль построен и покрыт тестами; включение — ход владельца.

═══════════════════════════════════════════════════════════════════════════════════════════
ДВЕ РУЧКИ, ОБЕ ЗАКРЫТЫ ПО УМОЛЧАНИЮ
═══════════════════════════════════════════════════════════════════════════════════════════

  WA_SEND=1          — без неё дверь не отправляет НИЧЕГО и говорит об этом словами.
                       Умолчание «выключено» выбрано намеренно: клиентский контур заморожен
                       решением владельца, а первая ошибка этой двери — сообщение живому
                       человеку, которое не отзывается.
  WA_360_API_KEY     — ключ 360dialog, заголовок `D360-API-KEY`. Пусто либо заполнитель
                       («PLACEHOLDER» и родня) → отказ ДО обращения к сети.

ЗНАЧЕНИЕ КЛЮЧА НЕ ПОКАЗЫВАЕТСЯ НИГДЕ. Ни в отказе, ни в журнале, ни в исключении не печатается
ни одного его символа — наружу уходит только «ключ не годен» и почему (пусто / заполнитель).

═══════════════════════════════════════════════════════════════════════════════════════════
ОКНО 24 ЧАСА — ВНЕШНЕЕ ПРАВИЛО META, А НЕ НАША ОСТОРОЖНОСТЬ
═══════════════════════════════════════════════════════════════════════════════════════════

Свободным текстом клиенту можно отвечать 24 часа с ЕГО последнего сообщения. Вне окна Meta
принимает только утверждённые шаблоны — а их у TurboBaby нет и заводить их эта дверь не будет:
рассылки прямо запрещены бизнес-правилами. Поэтому вне окна дверь не «пробует и смотрит, что
скажет сервер», а отказывает САМА, до сети.

ТРИ ИСХОДА У ОКНА, а не два (замок против ложного зелёного — тот же, что у `write_fact` и О3):

    ОТКРЫТО      знаем время последнего входящего, и ему меньше 24 часов  → шлём
    ЗАКРЫТО      знаем время, и ему больше 24 часов                       → «шаблоны не шлём»
    НЕИЗВЕСТНО   времени нет вовсе: очередь пуста, не читается, молода     → НЕ шлём

Третий исход не вежливая форма второго, и слова у них РАЗНЫЕ намеренно. «Закрыто» — измеренный
факт о клиенте; «неизвестно» — факт о НАС: у нас нет записи. Свести их в одну фразу значило бы
выдать незнание за измерение. Оба отказывают, но читатель по строке видит, что именно случилось.

═══════════════════════════════════════════════════════════════════════════════════════════
ТРИ ИСХОДА У ОТПРАВКИ — И «НЕИЗВЕСТНО» СИЛЬНЕЕ, ЧЕМ КАЖЕТСЯ
═══════════════════════════════════════════════════════════════════════════════════════════

    SENT       сервер ответил успехом И назвал идентификатор сообщения
    NOT_SENT   сервер ОТВЕТИЛ ОТКАЗОМ — он посмотрел на запрос и не принял его
    UNKNOWN    ответа нет либо он без идентификатора: сообщение МОГЛО уйти

UNKNOWN — не «наверное, не ушло». Молчание транспорта после POST означает ровно то, что мы не
знаем: запрос мог долететь и быть исполненным. Поэтому повторять вслепую нельзя — второй вызов
кладёт ВТОРОЕ сообщение живому человеку. Это тот же урок, которым живёт `write_fact`
(`receipt_unknown` → перечитай факт, не повторяй), и вызывающему он адресован здесь дословно
полем `verify` в ответе.

═══════════════════════════════════════════════════════════════════════════════════════════
ПОВТОРЫ ПОД ОБЩИМ ДЕДЛАЙНОМ, А НЕ ЛЕСТНИЦЕЙ
═══════════════════════════════════════════════════════════════════════════════════════════

В этом репозитории дважды измерен один класс: вложенные лестницы повторов без общего потолка
(карточка «Инфо» — 17100 с на кнопку, 13.08.2026; опрос очереди — 855 с, 15.08.2026). Поэтому
здесь потолок стоит на ВСЕЙ отправке (`SEND_BUDGET_SEC`), а не на плече: каждая попытка берёт
`min(плечо, остаток бюджета)`, и если бюджет исчерпан — к сети не касаемся ВОВСЕ.

ПОВТОРЯЕМ НЕ ВСЁ. Отказ, который сервер вынес САМ (4xx кроме 429), повторять бессмысленно и
вредно — второй такой же запрос получит тот же отказ. Повторяются только 429, 5xx и молчание
транспорта, то есть случаи, где вопрос «принято ли» ещё не решён.
"""

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

from scan_result import ScanResult

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── адрес 360dialog production (Direct API) ──────────────────────────────────────────────
API_BASE = "https://waba-v2.360dialog.io"
SEND_PATH = "/messages"
KEY_HEADER = "D360-API-KEY"

# ── окно Meta ────────────────────────────────────────────────────────────────────────────
WINDOW_SECS = 86400          # 24 часа с последнего входящего клиента
FUTURE_SKEW = 300            # метка времени вперёд дальше этого = часы врут, это не измерение

WINDOW_OPEN, WINDOW_CLOSED, WINDOW_UNKNOWN = "open", "closed", "unknown"

# ── исходы отправки ──────────────────────────────────────────────────────────────────────
SENT, NOT_SENT, UNKNOWN = "sent", "not_sent", "unknown"

# ── бюджеты ──────────────────────────────────────────────────────────────────────────────
SEND_BUDGET_SEC = 60.0       # потолок на ВСЮ отправку, включая паузы между попытками
LEG_TIMEOUT_SEC = 20.0       # плечо одного POST, урезается остатком бюджета
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0           # паузы 1 с, 2 с — растут вдвое

RETRY_STATUSES = frozenset((429, 500, 502, 503, 504))

# Значения, которыми ключ объявляет себя ненастоящим. Сверяется в верхнем регистре, по
# ВХОЖДЕНИЮ: «PLACEHOLDER», «wa-placeholder-key» и «TODO_SET_ME» одинаково не ключи.
_PLACEHOLDERS = ("PLACEHOLDER", "CHANGEME", "CHANGE_ME", "TODO", "XXXXX", "YOUR_KEY", "DUMMY")


# ═══ чистые решения (ни сети, ни диска — их проверяют прямыми вызовами в тестах) ══════════

def send_enabled(env=None) -> bool:
    """Включена ли дверь. Всё, кроме явного «1»/«true»/«yes», читается как выключено."""
    env = env if env is not None else os.environ
    return str(env.get("WA_SEND") or "").strip().lower() in ("1", "true", "yes", "on")


def key_usable(key) -> tuple:
    """Ключ → (годен ли, причина). ЗНАЧЕНИЕ В ПРИЧИНУ НЕ ПОПАДАЕТ НИКОГДА."""
    raw = (key or "").strip()
    if not raw:
        return False, "ключ 360dialog не задан (WA_360_API_KEY пуст)"
    up = raw.upper()
    for mark in _PLACEHOLDERS:
        if mark in up:
            return False, "в WA_360_API_KEY стоит заполнитель, а не ключ — боевой ещё не заведён"
    return True, "ключ задан"


def window_state(last_inbound_ts, now, window_secs: float = WINDOW_SECS) -> tuple:
    """Последнее входящее клиента + «сейчас» → (состояние окна, подробности).

    Метка в будущем дальше FUTURE_SKEW — не измерение, а расхождение часов: считаем, что
    времени у нас нет (НЕИЗВЕСТНО), а не что окно свежайшее.
    """
    try:
        ts = float(last_inbound_ts or 0.0)
    except (TypeError, ValueError):
        return WINDOW_UNKNOWN, {"why": "метка последнего входящего не число"}
    if ts <= 0:
        return WINDOW_UNKNOWN, {"why": "входящих от этого номера у нас не записано ни одного"}
    age = float(now) - ts
    if age < -FUTURE_SKEW:
        return WINDOW_UNKNOWN, {"why": "метка последнего входящего в будущем — часам не верим",
                                "age": age}
    if age <= window_secs:
        return WINDOW_OPEN, {"age": age, "limit": window_secs, "last": ts}
    return WINDOW_CLOSED, {"age": age, "limit": window_secs, "last": ts}


def classify_response(status, body_text, err=None) -> tuple:
    """Ответ сервера → (исход, причина, wamid, повторять ли).

    Три исхода, и граница между ними — ОТВЕТИЛ ЛИ сервер по существу:
      • ответил успехом с идентификатором  → SENT
      • ответил отказом, который вынес сам → NOT_SENT (повтор ничего не изменит)
      • не ответил / ответил без опознания → UNKNOWN (могло уйти — вслепую не повторять)
    """
    if err:
        return UNKNOWN, "транспорт молчит (%s) — запрос мог долететь" % err, None, True
    try:
        code = int(status)
    except (TypeError, ValueError):
        return UNKNOWN, "код ответа не прочитан", None, True

    if 200 <= code < 300:
        wamid = _wamid(body_text)
        if wamid:
            return SENT, "принято, id сообщения назван", wamid, False
        # Успех без идентификатора: назвать это отправкой нельзя — доказательства нет.
        return UNKNOWN, "код %d, но идентификатора сообщения в ответе нет" % code, None, False

    if code in RETRY_STATUSES:
        return (UNKNOWN if code >= 500 else NOT_SENT,
                "сервер ответил %d%s" % (code, _api_error(body_text)), None, True)

    return NOT_SENT, "сервер отказал %d%s" % (code, _api_error(body_text)), None, False


def _wamid(body_text):
    """Идентификатор отправленного сообщения из тела ответа, иначе None."""
    try:
        data = json.loads(body_text or "")
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    msgs = data.get("messages")
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        mid = msgs[0].get("id")
        return str(mid) if mid else None
    return None


def _api_error(body_text):
    """Собственные слова API об отказе — они говорят владельцу больше, чем наш пересказ.

    ПРОМАХ РАЗБОРА ЗВУЧИТ, а не возвращает пустоту. Пустая строка здесь означает РОВНО одно:
    «сервер ничего не сказал» — и означать что-то ещё она не вправе. Тело, которое пришло, но
    не разобралось, — это НАША слепота, и молчать о ней значит выдать её за молчание сервера
    (тот же класс «нуль по неразбору», которым живёт `scan_result`: нуль без знаменателя не
    отдаётся).
    """
    raw = str(body_text or "").strip()
    said = ""                            # пусто = «сервер ничего не сказал», и только это
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = None
            said = ": ответ сервера не разобран (тело есть, но это не JSON)"
        if data is not None and not isinstance(data, dict):
            said = ": ответ сервера не разобран (JSON есть, но это не объект)"
        elif isinstance(data, dict):
            err = data.get("error")
            err = err if isinstance(err, dict) else {}
            msg = err.get("message") or err.get("title") or ""
            said = (": " + str(msg)[:200]) if msg else ""
    # Выход ОДИН, и он не сидит в ветке промаха: каждое состояние назвало себя выше явно.
    return said


def backoff_delay(attempt: int) -> float:
    """Пауза ПЕРЕД попыткой номер `attempt` (первая — без паузы): 0, 1, 2, 4 …"""
    return 0.0 if attempt <= 1 else BACKOFF_BASE * (2 ** (attempt - 2))


# ═══ руки ════════════════════════════════════════════════════════════════════════════════

def last_inbound_ts(number, db_path=None):
    """Когда этот номер писал НАМ в последний раз → `ScanResult` с меткой в `payload`.

    ВОЗВРАЩАЕТ КОНТРАКТ, А НЕ ГОЛОЕ ЧИСЛО, и это не формальность. Голый `None` сливал ДВА
    разных мира в один: «очередь прочитана, входящих от этого номера в ней нет» и «очередь
    прочитать не удалось». Отказ отправки в обоих случаях один, а СЛОВА обязаны быть разными:
    в первом случае мы измерили, во втором — не смогли, и заявлять клиенту первое, когда
    случилось второе, значит выдать слепоту за факт. Ровно тот класс, ради которого заведён
    `scan_result` («нуль без знаменателя не отдаётся»).

    Исходы: `unreadable` — базы нет либо она не читается; `empty` — прочитали, входящих этого
    номера нет; `ok` — прочитали и метка есть. Только чтение. Эхо своих исходящих и квитанции
    статусов входящими не считаются: окно открывает сообщение КЛИЕНТА, а не наше о нём
    представление.
    """
    path = db_path or os.environ.get("WA_QUEUE_DB") or os.path.join(ROOT, "wa_queue.db")
    if not str(number or "").strip():
        return ScanResult(0, 0, subject="входящих", detail="номер не назван")
    if not os.path.exists(path):
        return ScanResult.unreadable("входящих", detail="очереди нет по пути " + os.path.basename(path))
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            row = conn.execute(
                """SELECT COUNT(*), MAX(COALESCE(NULLIF(ts_msg, 0), ts_queued))
                     FROM wa_inbox
                    WHERE from_number = ? AND echo = 0 AND msg_type <> 'status'""",
                (str(number),),
            ).fetchone()
    except Exception as e:
        return ScanResult.unreadable("входящих", detail="очередь не читается: " + type(e).__name__)
    seen = int((row or [0])[0] or 0)
    ts = (row or [0, None])[1]
    # Осмотрено — сколько входящих этого номера в очереди; разобрано — удалось ли получить из
    # них метку времени. Строки есть, а метки нет → mismatch, а не «давно»: это разошедшийся
    # источник, и он обязан прозвучать.
    return ScanResult(seen, 1 if ts else 0, subject="входящих", payload=ts)


def _post(url, payload: dict, key: str, timeout: float):
    """Один POST. Возвращает (status, body_text, err). Сеть трогается ТОЛЬКО здесь.

    Это единственный шов, который тесты подменяют, — поэтому ни один тест не выходит наружу.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header(KEY_HEADER, key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return e.code, text, None
    except Exception as e:
        return None, "", type(e).__name__


def build_payload(to: str, text: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": str(to),
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }


def send_text(to, text, now=None, db_path=None, env=None, transport=None,
              sleep=time.sleep, budget=SEND_BUDGET_SEC, clock=time.monotonic):
    """Отправить текст клиенту. Возвращает словарь-исход, НИКОГДА не бросает.

    Ключи ответа:
      outcome  sent | not_sent | unknown
      reason   человеческая причина (значения ключа в ней нет никогда)
      wamid    идентификатор сообщения при sent, иначе None
      window   open | closed | unknown
      attempts сколько раз обращались к сети (0 — если до сети не дошло)
      verify   True, когда исход unknown: ПЕРЕД любым повтором надо выяснить, ушло ли
    """
    env = env if env is not None else os.environ
    now = time.time() if now is None else float(now)
    post = transport or _post

    def out(outcome, reason, window=WINDOW_UNKNOWN, wamid=None, attempts=0):
        return {"outcome": outcome, "reason": reason, "wamid": wamid,
                "window": window, "attempts": attempts, "verify": outcome == UNKNOWN}

    if not str(to or "").strip():
        return out(NOT_SENT, "номер получателя не назван")
    if not str(text or "").strip():
        return out(NOT_SENT, "пустой текст не отправляем")

    # ── ручка двери ──
    if not send_enabled(env):
        return out(NOT_SENT, "дверь отправки выключена (WA_SEND не равен 1) — не отправлено")

    # ── ключ ──
    key = env.get("WA_360_API_KEY") or ""
    key_ok, key_why = key_usable(key)
    if not key_ok:
        return out(NOT_SENT, key_why + " — не отправлено")

    # ── окно 24 часа: судим ДО сети ──
    #
    # Исход чтения очереди и исход ОКНА — разные вещи, и слепота читателя не смеет выглядеть
    # как измеренный факт о клиенте. Поэтому сперва спрашиваем контракт: не прочитали / шаблон
    # разошёлся → говорим ИМЕННО это; прочитали → судим окно по метке.
    scan = last_inbound_ts(to, db_path)
    if not scan.ok:
        return out(NOT_SENT,
                   "окно неизвестно: %s — не отправлено (это НЕ «окно закрыто»: про клиента мы "
                   "ничего не измерили)" % scan.say(), window=WINDOW_UNKNOWN)

    state, info = window_state(scan.payload, now)
    if state == WINDOW_CLOSED:
        hours = int((info.get("age") or 0) // 3600)
        return out(NOT_SENT,
                   "окно закрыто (последнее сообщение клиента %d ч назад, предел 24 ч) — "
                   "шаблоны не шлём" % hours, window=state)
    if state == WINDOW_UNKNOWN:
        return out(NOT_SENT,
                   "окно неизвестно: %s — не отправлено (это НЕ «окно закрыто», это отсутствие "
                   "записи у нас)" % info.get("why", "причина не названа"), window=state)

    # ── отправка под общим дедлайном ──
    url = API_BASE + SEND_PATH
    payload = build_payload(to, text)
    # ДЕДЛАЙН ЖИВЁТ НА СВОИХ ЧАСАХ, а не на `now`. `now` — семантическое «сейчас» для окна
    # 24 часа, и тест вправе подать его фальшивым; смешать их значило бы, что подставленное
    # время мгновенно съедает бюджет и отправка не случается никогда. Часы монотонные:
    # перевод системного времени не должен ни продлевать, ни обрывать отправку.
    deadline = clock() + float(budget)
    attempts = 0
    last = out(UNKNOWN, "ни одной попытки не состоялось", window=state)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        pause = backoff_delay(attempt)
        if pause and clock() + pause >= deadline:
            last = out(last["outcome"], last["reason"] + "; бюджет исчерпан до следующей попытки",
                       window=state, attempts=attempts)
            break
        if pause:
            sleep(pause)

        left = deadline - clock()
        if left <= 0:
            last = out(last["outcome"], last["reason"] + "; бюджет исчерпан, к сети не обращались",
                       window=state, attempts=attempts)
            break

        attempts += 1
        try:
            status, body, err = post(url, payload, key, min(LEG_TIMEOUT_SEC, left))
        except Exception as e:                                        # noqa: BLE001
            status, body, err = None, "", type(e).__name__
        outcome, reason, wamid, retry = classify_response(status, body, err)
        last = out(outcome, reason, window=state, wamid=wamid, attempts=attempts)
        if not retry:
            return last

    return last
