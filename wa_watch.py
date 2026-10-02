#!/usr/bin/env python3
"""ОЖИДАНИЕ «клиент без ответа» в службе wa-agent (WAUNANSWERED0210).

ЧТО ЭТО. Последнее сообщение клиента без нашего ответа дольше порога — ОДНО сообщение в «TurboBaby ·
Агенты»: имя темы, сколько клиент ждёт, ссылка на тему. Повтор — только после нового сообщения
клиента. Слой не пишет клиенту, не снимает паузу агента и не зовёт модель: он только называет
беседу, которая выпала (повод — владелец 02.10 01:23: «надо что бы без продолжения беседы не
оставлось»; дыра WAAGENTCORE0110 — пауза агента бессрочна, клиент ждёт молча).

ПОРОГ — НАСТРОЙКА WA_AGENT_WATCH_SEC, по умолчанию 600 с (WAWATCHTEN0210). Слово владельца 02.10 12:58:
«35 минут долго минут 10». Прежние 2130 с — p90 ответа за 30 суток (WAUNANSWERED0210); за 10 мин мы
отвечали в 80,4 % промежутков тех же 30 суток — значит, тревога звенит примерно на каждую пятую беседу.
Значение — целое число секунд от SEC_MIN до SEC_MAX; иное — умолчание и строка журнала (её пишет служба).
Текст тревоги называет порог в минутах из настройки.

ТИХИЕ ЧАСЫ — настройка WA_AGENT_WATCH_QUIET «ЧЧ-ЧЧ» по Пхукету (например 00-08, через полночь — 22-07),
по умолчанию выключены. Тревога, выпавшая на тихие часы, в Telegram не идёт: она ложится в базу
состоянием `quiet`, а на первом обороте после конца тихих часов все отложенные уходят ОДНОЙ сводкой. В
сводку попадает клиент, чьё отложенное сообщение и тогда последнее и без ответа; ответили до утра или
клиент написал снова — `dropped` (новое сообщение даст свою тревогу по общему правилу). Битая
настройка — тихих часов нет (тревога сразу) и строка журнала.

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
import re
import sqlite3
import time

import wa_agent
import wa_kind

F_SEC = "WA_AGENT_WATCH_SEC"         # порог, секунды (WAWATCHTEN0210)
F_QUIET = "WA_AGENT_WATCH_QUIET"     # тихие часы «ЧЧ-ЧЧ» по Пхукету (WAWATCHTEN0210)
WATCH_SEC = 600                      # порог по умолчанию: слово владельца 02.10 12:58 «минут 10»
EVERY = 60                           # оборот ожидания не чаще раза в минуту
WINDOW = 86400                       # входящее старше суток тревоги не даёт
SEC_MIN, SEC_MAX = EVERY, WINDOW - 1  # порог короче оборота не различим, а от суток и дольше не звенит никогда
AUTO_SEC = 10                        # эхо ≤ 10 с после «первого» входящего — автоответ
SILENCE = 14 * 86400                 # «первое» входящее: до него 14 суток тишины в обе стороны
TRIES = 3                            # отказ Telegram с кодом — попыток всего
LIST_MAX = 20                        # клиентов в сводке тихих часов поимённо; остальные — числом
SENDING, SENT, FAIL, UNSURE = "sending", "sent", "fail", "unsure"
QUIET, DROPPED = "quiet", "dropped"  # отложена тихими часами · снята до сводки (ответили, написал снова)
PAUSED_WORDS = "агент на паузе — черновика не будет до «Продолжить»"

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


def min_words(sec):
    """Порог словами в минутах: 600 → «10 мин», 2130 → «35 мин 30 с»."""
    sec = int(sec)
    return "%d мин" % (sec // 60) + (" %d с" % (sec % 60) if sec % 60 else "")


def threshold_of(raw):
    """Настройка WA_AGENT_WATCH_SEC → (секунды, слова, битая ли). Целое число секунд от SEC_MIN до SEC_MAX;
    пусто — умолчание; иное — умолчание, а служба пишет строку журнала со словом «битая»."""
    s = str(raw or "").strip()
    if not s:
        return WATCH_SEC, "%s (по умолчанию)" % min_words(WATCH_SEC), False
    if not re.fullmatch(r"[0-9]{1,6}", s) or not SEC_MIN <= int(s) <= SEC_MAX:
        return WATCH_SEC, ("настройка %s битая (нужно целое число секунд от %d до %d) — по умолчанию %s"
                           % (F_SEC, SEC_MIN, SEC_MAX, min_words(WATCH_SEC))), True
    return int(s), "%s (%s=%s)" % (min_words(int(s)), F_SEC, s), False


def quiet_of(raw):
    """Настройка WA_AGENT_WATCH_QUIET → ((с, до) часов Пхукета | None, слова, битая ли). «ЧЧ-ЧЧ»: 00-08,
    22-07 (через полночь), конец 24 — то же, что 00. Пусто — выключены; иное — выключены и «битая»."""
    s = str(raw or "").strip()
    if not s:
        return None, "выкл — тревога сразу в любой час", False
    m = re.fullmatch(r"([0-9]{1,2})\s*-\s*([0-9]{1,2})", s)
    a, b = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
    if not m or not 0 <= a <= 23 or not 0 <= b <= 24 or a == b % 24:
        return None, ("настройка %s битая (нужно «ЧЧ-ЧЧ» по Пхукету, например 00-08) — тихих часов нет, "
                      "тревога сразу" % F_QUIET), True
    return (a, b % 24), "%02d–%02d по Пхукету — тревоги этих часов придут в %02d:00 одной сводкой" % (
        a, b % 24, b % 24), False


def in_quiet(now, quiet):
    """Час `now` по Пхукету внутри тихих часов [с, до), через полночь тоже. Нет настройки — нет."""
    if not quiet:
        return False
    a, b = quiet
    h = int((float(now) + wa_agent.PHUKET_OFFSET) % 86400 // 3600)
    return a <= h < b if a < b else (h >= a or h < b)


class Watch:
    """db — соединение базы агента (общая с ядром); queue_path — очередь (только mode=ro);
    send(number, text) → (True, message_id) · (False, код) · (None, 'net'); head(number) → «имя\\nтема: ссылка»;
    greet — отпечатки приветствия из настройки службы (`wa_agent.greet_fps`), пусто — только время;
    threshold — порог из `threshold_of`; quiet — тихие часы из `quiet_of` (None — нет)."""

    def __init__(self, db, queue_path, send, head=None, threshold=WATCH_SEC, every=EVERY, clock=time.time,
                 log=None, greet=(), quiet=None):
        self.db, self.queue_path, self.send = db, queue_path, send
        self.head = head or (lambda number: "без имени")
        self.threshold, self.every = int(threshold), int(every)
        self.quiet = tuple(quiet) if quiet else None
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
            due = []                          # (номер, строка, время) — дольше порога и без ответа
            for number, (in_id, in_ts, in_tm) in sorted(last_in.items()):
                if now - in_ts <= self.threshold:
                    continue
                if any(kind == wa_kind.KIND_REACTION or not self._auto(q, number, text, ts_m, in_id, in_tm)
                       for text, ts_m, kind in after[number]):
                    continue
                if self._answered_api(q, number, in_ts):
                    continue
                due.append((number, in_id, in_ts))
        finally:
            q.close()
        if in_quiet(now, self.quiet):
            for number, in_id, _ in due:
                self._hold(number, in_id, now)
            return []
        fired = self._morning(due, now)
        for number, in_id, in_ts in due:      # отложенная и уже сводная строка здесь не шлётся: ключ занят
            if self._alarm(number, in_id, in_ts, now):
                fired.append(in_id)
        return fired

    def _paused(self, number):
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='clients'").fetchone():
            return False
        row = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        return bool(row and row[0])

    def _client(self, number, in_ts, now):
        """Слова о клиенте — одно место для тревоги и сводки: (ждёт, имя и тема, ЧЧ:ММ по Пхукету, на паузе)."""
        return wait_words(now - in_ts), self.head(number), wa_agent.hm_phuket(in_ts), self._paused(number)

    def _rule(self, many=False):
        return ("Порог — %s (%s). Следующее напоминание по %s — только после %s нового сообщения."
                % (min_words(self.threshold), F_SEC, "этим клиентам" if many else "этому клиенту",
                   "их" if many else "его"))

    def _send(self, number, text):
        try:
            ok, res = self.send(number, text)
        except Exception as e:                                       # noqa: BLE001
            ok, res = None, type(e).__name__
        return ok, res

    def _alarm(self, number, in_id, in_ts, now):
        """Одна тревога на (номер, строка входящего): запись ДО Telegram; отказ с кодом — ещё попытка."""
        if self.db.execute("INSERT OR IGNORE INTO watch_alarm(number, in_id, state, ts) VALUES(?,?,?,?)",
                           (number, in_id, SENDING, now)).rowcount != 1:
            if self.db.execute("UPDATE watch_alarm SET state=?, tries=tries+1, ts=? WHERE number=? AND in_id=? "
                               "AND state=? AND tries<?", (SENDING, now, number, in_id, FAIL, TRIES)).rowcount != 1:
                return False
        wait, head, hm, paused = self._client(number, in_ts, now)
        text = ("⏰ Клиент ждёт ответа %s\n%s\nпоследнее сообщение клиента — %s (Пхукет); после него нашего "
                "ответа нет: ни с телефона, ни из темы, ни по «Отправить», ни реакцией%s.\n%s"
                % (wait, head, hm, "; " + PAUSED_WORDS if paused else "", self._rule()))
        ok, res = self._send(number, text)
        state = SENT if ok else (FAIL if ok is False else UNSURE)
        self.db.execute("UPDATE watch_alarm SET state=?, msg_id=? WHERE number=? AND in_id=? AND state=?",
                        (state, res if ok else None, number, in_id, SENDING))
        self.log("ожидание: строка %d · ждёт %d с · тревога → %s" % (in_id, int(now - in_ts), state))
        return state == SENT

    # ── тихие часы (WAWATCHTEN0210) ──────────────────────────────────────────────────────

    def _hold(self, number, in_id, now):
        """Тревога тихих часов: строка `quiet` в базе, Telegram не зовётся; уйдёт в их конце сводкой."""
        if self.db.execute("INSERT OR IGNORE INTO watch_alarm(number, in_id, state, tries, ts) VALUES(?,?,?,0,?)",
                           (number, in_id, QUIET, now)).rowcount == 1:
            self.log("ожидание: строка %d · тихие часы — тревога отложена до их конца" % in_id)

    def _morning(self, due, now):
        """Первый оборот после тихих часов: отложенные — ОДНОЙ сводкой. В сводку идёт строка, которая и сейчас
        дольше порога и без ответа (она в `due`); прочие — `dropped`. Отказ с кодом — сводка ещё раз на
        следующем обороте (до TRIES), молчание сети — `unsure`, второй раз не шлём."""
        held = self.db.execute("SELECT number, in_id FROM watch_alarm WHERE state=? ORDER BY ts, in_id",
                               (QUIET,)).fetchall()
        if not held:
            return []
        live = {(number, in_id): in_ts for number, in_id, in_ts in due}
        keep = [(number, in_id, live[(number, in_id)]) for number, in_id in held if (number, in_id) in live]
        dropped = [(number, in_id) for number, in_id in held if (number, in_id) not in live]
        for number, in_id in dropped:
            self.db.execute("UPDATE watch_alarm SET state=?, ts=? WHERE number=? AND in_id=? AND state=?",
                            (DROPPED, now, number, in_id, QUIET))
        if not keep:
            self.log("ожидание: тихие часы кончились — отложенных %d, все сняты до сводки" % len(dropped))
            return []
        for number, in_id, _ in keep:
            self.db.execute("UPDATE watch_alarm SET state=?, tries=tries+1, ts=? WHERE number=? AND in_id=? "
                            "AND state=?", (SENDING, now, number, in_id, QUIET))
        title = ("тихих часов %02d–%02d (Пхукет)" % self.quiet if self.quiet
                 else "отложенных тревог (тихие часы сняты настройкой)")
        lines = []
        for k, (number, in_id, in_ts) in enumerate(keep[:LIST_MAX], 1):
            wait, head, hm, paused = self._client(number, in_ts, now)
            lines.append("%d) %s\nждёт %s · последнее сообщение — %s (Пхукет)%s"
                         % (k, head, wait, hm, " · " + PAUSED_WORDS if paused else ""))
        if len(keep) > LIST_MAX:
            lines.append("…и ещё %d — без имён, сводка не длиннее %d" % (len(keep) - LIST_MAX, LIST_MAX))
        text = ("⏰ Сводка %s: без нашего ответа ждут %d\n%s\n"
                "Тревоги тихих часов собраны в одну сводку; ни с телефона, ни из темы, ни по «Отправить», ни "
                "реакцией ответа не было. %s" % (title, len(keep), "\n".join(lines), self._rule(many=True)))
        ok, res = self._send(keep[0][0], text)
        for number, in_id, _ in keep:
            tries = self.db.execute("SELECT tries FROM watch_alarm WHERE number=? AND in_id=?",
                                    (number, in_id)).fetchone()[0]
            state = SENT if ok else (UNSURE if ok is None else (QUIET if tries < TRIES else FAIL))
            self.db.execute("UPDATE watch_alarm SET state=?, msg_id=? WHERE number=? AND in_id=? AND state=?",
                            (state, res if ok else None, number, in_id, SENDING))
        self.log("ожидание: сводка тихих часов · клиентов %d · снято до сводки %d → %s"
                 % (len(keep), len(dropped), SENT if ok else (UNSURE if ok is None else FAIL)))
        return [in_id for _, in_id, _ in keep] if ok else []

    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM watch_alarm GROUP BY state").fetchall())


if __name__ == "__main__":
    raise SystemExit("wa_watch: ожидание без рук (WAUNANSWERED0210) — живёт в службе wa_agent_svc.py")
