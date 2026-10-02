#!/usr/bin/env python3
"""ОЖИДАНИЕ «клиент без ответа» в службе wa-agent (WAUNANSWERED0210).

ЧТО ЭТО. Последнее сообщение клиента без нашего ответа дольше порога — ОДНО сообщение в «TurboBaby ·
Агенты»: имя темы, сколько клиент ждёт, ссылка на тему. Повтор — только после нового сообщения
клиента. Слой не пишет клиенту, не снимает паузу агента и не зовёт модель: он только называет
беседу, которая выпала (повод — владелец 02.10 01:23: «надо что бы без продолжения беседы не
оставлось»; дыра WAAGENTCORE0110 — пауза агента бессрочна, клиент ждёт молча).

ПОРОГ — ЗАМЕР, А НЕ КРУГЛОЕ ЧИСЛО. 2130 с = p90 времени от последнего сообщения клиента до нашего
ответа за 30 суток (541 промежуток, архив копии телефона + очередь, автоответ не в счёт): в 9
беседах из 10 мы отвечали быстрее — дольше уже необычно.

КОНТРАКТ НАБЛЮДЕНИЯ.
  результат  — у клиента, написавшего последним, есть наш ответ не позже порога; иначе одна тревога.
  источник   — очередь `wa_queue.db` (только mode=ro): живое входящее клиента и живое эхо с телефона
               (реплика или наша реакция); база агента: `outbox` (ушло через API — из темы или по
               «Отправить») и `tg_react_out` (наша реакция из темы, исход двери sent).
  способ     — раз в `every` с: последнее живое входящее каждого номера за сутки; ответ — что угодно
               наше ПОСЛЕ него, кроме автоответа (отпечаток текста приветствия ИЛИ эхо ≤ 10 с после
               «первого» входящего — до него 14 суток тишины, WAAUTOGREET0210). Отпечаток — та же
               настройка WA_AGENT_GREET_SHA256 и то же правило, что у ядра (`wa_agent.greet_fps`,
               `wa_agent.greet_hit`; WACHAINFIX0210); настройки нет — автоответ ловит одно время.
  отрицание  — ответили с телефона, по «Отправить», из темы или реакцией — тишина; повтор такта и
               рестарт — та же одна тревога (ключ «номер + строка входящего» в базе ДО Telegram).
Не знаю, наш ли ответ (флаг строки не разобран) — не ответ: молчание источника ответом не считается.

СОСТОЯНИЕ — своя таблица `watch_alarm` в базе агента. `sending` пишется ДО Telegram; рестарт
посреди вызова → `unsure`, второй раз не шлём. Отказ Telegram с кодом (не дошло точно) — до
`TRIES` попыток на следующих оборотах. Первый старт: курсор `watch_from` на MAX(id) — переписка
до включения тревог не даёт. Входящее старше суток тревоги не даёт (окно 24 ч закрыто,
рестарт после долгого простоя не сыплет сообщениями).

ЖУРНАЛ — только id, состояния и числа: ни текстов, ни номеров, ни имён.
"""

import hashlib
import sqlite3
import time

import wa_agent
import wa_kind

WATCH_SEC = 2130                     # порог: p90 ответа за 30 суток (WAUNANSWERED0210 п.2)
EVERY = 60                           # оборот ожидания не чаще раза в минуту
WINDOW = 86400                       # входящее старше суток тревоги не даёт
AUTO_SEC = 10                        # эхо ≤ 10 с после «первого» входящего — автоответ
SILENCE = 14 * 86400                 # «первое» входящее: до него 14 суток тишины в обе стороны
TRIES = 3                            # отказ Telegram с кодом — попыток всего
SENDING, SENT, FAIL, UNSURE = "sending", "sent", "fail", "unsure"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_alarm (
    number  TEXT    NOT NULL,
    in_id   INTEGER NOT NULL,          -- строка очереди: сообщение клиента, на которое тревога
    state   TEXT    NOT NULL,          -- sending ДО Telegram, потом sent | fail | unsure
    tries   INTEGER NOT NULL DEFAULT 1,
    msg_id  INTEGER,
    ts      REAL    NOT NULL,
    PRIMARY KEY (number, in_id)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def fp(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10] if text else ""


def wait_words(sec):
    m = int(sec // 60)
    return "%d мин" % m if m < 120 else "%d ч %02d мин" % (m // 60, m % 60)


class Watch:
    """db — соединение базы агента (общая с ядром); queue_path — очередь (только mode=ro);
    send(number, text) → (True, message_id) · (False, код) · (None, 'net'); head(number) → «имя\\nтема: ссылка»;
    greet — отпечатки приветствия из настройки службы (`wa_agent.greet_fps`), пусто — только время."""

    def __init__(self, db, queue_path, send, head=None, threshold=WATCH_SEC, every=EVERY, clock=time.time,
                 log=None, greet=()):
        self.db, self.queue_path, self.send = db, queue_path, send
        self.head = head or (lambda number: "без имени")
        self.threshold, self.every = int(threshold), int(every)
        self.clock = clock
        self.log = log or (lambda line: None)
        self.greet = tuple(greet or ())
        self.last = None
        self.db.executescript(_SCHEMA)
        n = self.db.execute("UPDATE watch_alarm SET state=? WHERE state=?", (UNSURE, SENDING)).rowcount
        if n:
            self.log("ожидание: старт — sending→unsure %d (могло уйти, не повторяем)" % n)

    def _queue(self):
        return sqlite3.connect("file:%s?mode=ro" % self.queue_path, uri=True, timeout=5)

    def _from(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='watch_from'").fetchone()
        return int(row[0]) if row else None

    # ── ответ ────────────────────────────────────────────────────────────────────────────

    def _auto(self, q, number, echo_text, echo_ts, in_id, in_ts):
        """Эхо — автоответ: отпечаток текста приветствия ИЛИ ≤ AUTO_SEC после «первого» входящего."""
        if wa_agent.greet_hit(echo_text, self.greet):
            return True
        if echo_ts is None or in_ts is None or not 0 <= echo_ts - in_ts <= AUTO_SEC:
            return False
        before = q.execute("SELECT COUNT(*) FROM wa_inbox WHERE from_number=? AND id<>? AND msg_type<>? "
                           "AND ts_msg>=? AND ts_msg<?", (number, in_id, wa_kind.RECEIPT_TYPE,
                                                         in_ts - SILENCE, in_ts)).fetchone()[0]
        return before == 0

    def _answered_api(self, q, number, since):
        """Ушло через API после `since`: outbox (тема, «Отправить») или наша реакция из темы."""
        if self.db.execute("SELECT 1 FROM outbox WHERE number=? AND ts>=? LIMIT 1", (number, since)).fetchone():
            return True
        try:
            reacts = self.db.execute("SELECT wamid FROM tg_react_out WHERE outcome='sent' AND emoji<>'' "
                                     "AND ts>=?", (since,)).fetchall()
        except sqlite3.OperationalError:                       # рук Telegram нет — реакций из темы нет
            return False
        for (wamid,) in reacts:
            row = q.execute("SELECT from_number FROM wa_inbox WHERE wamid=? LIMIT 1", (wamid,)).fetchone()
            if row and row[0] == number:
                return True
        return False

    # ── оборот ───────────────────────────────────────────────────────────────────────────

    def tick(self, now=None):
        now = self.clock() if now is None else now
        if self.last is not None and now - self.last < self.every:
            return []
        self.last = now
        q = self._queue()                     # закрываем сами: `with` у sqlite3 соединение не закрывает
        try:
            start = self._from()
            if start is None:
                top = q.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
                self.db.execute("INSERT INTO meta(key, value) VALUES('watch_from', ?) "
                                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(top),))
                self.log("ожидание: курсор встал на %d (первый старт)" % top)
                return []
            rows = q.execute("SELECT id, from_number, msg_type, echo, history, text, ts_queued, ts_msg "
                             "FROM wa_inbox WHERE id>? AND ts_queued>=? ORDER BY id",
                             (start, now - WINDOW)).fetchall()
            last_in, after = {}, {}
            for rid, number, msg_type, echo, history, text, ts_q, ts_m in rows:
                if not number:
                    continue
                kind = wa_kind.kind_of(msg_type, echo, history)
                if kind == wa_kind.KIND_INBOUND:
                    last_in[number] = (rid, float(ts_q or 0), ts_m)
                    after[number] = []
                elif number in last_in and wa_kind._flag(history) is False and wa_kind._flag(echo) is True \
                        and kind in (wa_kind.KIND_ECHO, wa_kind.KIND_REACTION):
                    after[number].append((text, ts_m, kind))
            fired = []
            for number, (in_id, in_ts, in_tm) in sorted(last_in.items()):
                if now - in_ts <= self.threshold:
                    continue
                if any(kind == wa_kind.KIND_REACTION or not self._auto(q, number, text, ts_m, in_id, in_tm)
                       for text, ts_m, kind in after[number]):
                    continue
                if self._answered_api(q, number, in_ts):
                    continue
                if self._alarm(number, in_id, in_ts, now):
                    fired.append(in_id)
        finally:
            q.close()
        return fired

    def _alarm(self, number, in_id, in_ts, now):
        """Одна тревога на (номер, строка входящего): запись ДО Telegram; отказ с кодом — ещё попытка."""
        if self.db.execute("INSERT OR IGNORE INTO watch_alarm(number, in_id, state, ts) VALUES(?,?,?,?)",
                           (number, in_id, SENDING, now)).rowcount != 1:
            if self.db.execute("UPDATE watch_alarm SET state=?, tries=tries+1, ts=? WHERE number=? AND in_id=? "
                               "AND state=? AND tries<?", (SENDING, now, number, in_id, FAIL, TRIES)).rowcount != 1:
                return False
        paused = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone() \
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='clients'").fetchone() else None
        text = ("⏰ Клиент ждёт ответа %s\n%s\nпоследнее сообщение клиента — %s (Пхукет); после него нашего "
                "ответа нет: ни с телефона, ни из темы, ни по «Отправить», ни реакцией%s.\n"
                "Порог %s — так долго мы не отвечали лишь в 1 беседе из 10 за 30 суток. "
                "Следующее напоминание по этому клиенту — только после его нового сообщения."
                % (wait_words(now - in_ts), self.head(number), wa_agent.hm_phuket(in_ts),
                   "; агент на паузе — черновика не будет до «Продолжить»" if paused and paused[0] else "",
                   wait_words(self.threshold)))
        try:
            ok, res = self.send(number, text)
        except Exception as e:                                       # noqa: BLE001
            ok, res = None, type(e).__name__
        state = SENT if ok else (FAIL if ok is False else UNSURE)
        self.db.execute("UPDATE watch_alarm SET state=?, msg_id=? WHERE number=? AND in_id=? AND state=?",
                        (state, res if ok else None, number, in_id, SENDING))
        self.log("ожидание: строка %d · ждёт %d с · тревога → %s" % (in_id, int(now - in_ts), state))
        return state == SENT

    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM watch_alarm GROUP BY state").fetchall())


if __name__ == "__main__":
    raise SystemExit("wa_watch: ожидание без рук (WAUNANSWERED0210) — живёт в службе wa_agent_svc.py")
