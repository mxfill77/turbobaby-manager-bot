"""
SQLite база эпизодической памяти.
Хранит:
- conversations: всю историю общения
- rules: правила которые усвоил бот
- corrections: исправления от пользователя
- notes: заметки о клиентах/байках
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER,
    user_name TEXT,
    role TEXT NOT NULL,        -- 'user' / 'assistant'
    content TEXT NOT NULL,
    is_voice BOOLEAN DEFAULT 0,
    topic_id TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id);
CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(timestamp);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    rule TEXT NOT NULL,
    context TEXT,
    source TEXT DEFAULT 'user',  -- 'user' / 'auto' / 'inferred'
    active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user_said TEXT NOT NULL,
    bot_did_before TEXT,
    bot_does_now TEXT,
    applied BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entity_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    entity_type TEXT NOT NULL,   -- 'client' / 'bike' / 'rental'
    entity_key TEXT NOT NULL,
    note TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_entity ON entity_notes(entity_type, entity_key);

CREATE TABLE IF NOT EXISTS topic_bike (
    chat_id    INTEGER NOT NULL,
    topic_id   INTEGER NOT NULL,
    bike_name  TEXT NOT NULL,
    source     TEXT DEFAULT 'auto',   -- forum_created / resolved / manual / bootstrap
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, topic_id)
);

CREATE TABLE IF NOT EXISTS info_pin (
    chat_id    INTEGER NOT NULL,
    topic_id   INTEGER NOT NULL,
    msg_id     INTEGER NOT NULL,      -- id закреплённого сообщения с кнопкой «ℹ️ Инфо»
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, topic_id)
);

CREATE TABLE IF NOT EXISTS o3_task (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bike            TEXT NOT NULL,
    plate           TEXT,
    kinds           TEXT,             -- csv видов ТО: oil,abs,airfilter
    from_where      TEXT,             -- office / client / area
    when_slot       TEXT,             -- now / today
    status          TEXT DEFAULT 'new',   -- new / draft / sent
    delivery_msg_id INTEGER,          -- id сообщения-наряда в группе доставок
    board_chat      INTEGER,
    board_msg       INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS o3_card (
    board_chat INTEGER NOT NULL,      -- чат board (HQ в тесте / обслуживание в бою)
    plate      TEXT NOT NULL,         -- номер байка; спец-ключ '__header__' = заголовок-счётчик board
    msg_id     INTEGER NOT NULL,      -- id сообщения-карточки (editMessageText на rescan, без дублей)
    updated_at TEXT NOT NULL,
    PRIMARY KEY (board_chat, plate)
);
"""


class Memory:
    """Память бота — SQLite с автокоммитом."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path, isolation_level=None)

    def _init_db(self):
        conn = self._conn()
        try:
            conn.executescript(SCHEMA)
            # Миграция: добавить topic_id в старую БД, если колонки ещё нет
            cols = [r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()]
            if "topic_id" not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN topic_id TEXT DEFAULT ''")
                log.info("Memory DB: добавлена колонка topic_id (миграция)")
            # Индекс по теме — создаём ПОСЛЕ того как колонка точно есть
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_topic ON conversations(chat_id, topic_id)")
            log.info(f"Memory DB initialized: {self.db_path}")
        finally:
            conn.close()

    # === Conversations ===

    def save_message(self, chat_id: int, user_id: Optional[int], user_name: Optional[str],
                     role: str, content: str, is_voice: bool = False, topic_id=None):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO conversations (timestamp, chat_id, user_id, user_name, role, content, is_voice, topic_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), chat_id, user_id, user_name, role, content, is_voice,
                 str(topic_id) if topic_id is not None else "")
            )
        finally:
            conn.close()

    def recent_messages(self, chat_id: int, limit: int = 20, topic_id=None) -> List[Dict]:
        """Последние N сообщений в чате для контекста Claude.
        Если topic_id задан — только сообщения этой темы (форум обслуживания:
        каждая тема = свой байк, истории тем НЕ смешиваются).
        Для topic_id применяется SERVICING_HISTORY_TTL_H: сообщения старше N часов
        не входят в контекст (поверх history_limit). Fail-safe: ошибка парса env → без фильтра."""
        conn = self._conn()
        try:
            if topic_id is not None:
                cutoff_str = None
                try:
                    ttl_h = float(os.environ.get("SERVICING_HISTORY_TTL_H", "48"))
                    if ttl_h > 0:
                        cutoff_str = (datetime.now() - timedelta(hours=ttl_h)).isoformat()
                except (ValueError, TypeError):
                    pass
                if cutoff_str:
                    cursor = conn.execute(
                        "SELECT role, content FROM conversations WHERE chat_id = ? AND topic_id = ? "
                        "AND timestamp >= ? ORDER BY id DESC LIMIT ?",
                        (chat_id, str(topic_id), cutoff_str, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT role, content FROM conversations WHERE chat_id = ? AND topic_id = ? "
                        "ORDER BY id DESC LIMIT ?",
                        (chat_id, str(topic_id), limit)
                    )
            else:
                cursor = conn.execute(
                    "SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, limit)
                )
            rows = cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        finally:
            conn.close()

    # === Rules ===

    def add_rule(self, rule: str, context: str = "", source: str = "user") -> int:
        conn = self._conn()
        try:
            # Защита от дублей: если очень похожее правило уже есть — не плодим, вернём его id
            def _norm(s):
                return "".join(ch.lower() for ch in (s or "") if ch.isalnum())
            new_norm = _norm(rule)
            if new_norm:
                existing = conn.execute(
                    "SELECT id, rule FROM rules WHERE active = 1"
                ).fetchall()
                for row in existing:
                    ex_norm = _norm(row[1])
                    if not ex_norm:
                        continue
                    # совпадение по нормализованному тексту, или одно содержит другое (почти то же)
                    if new_norm == ex_norm or new_norm in ex_norm or ex_norm in new_norm:
                        return row[0]   # дубль — вернём существующий
            cursor = conn.execute(
                "INSERT INTO rules (created_at, rule, context, source) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), rule, context, source)
            )
            return cursor.lastrowid
        finally:
            conn.close()

    def active_rules(self) -> List[Dict]:
        conn = self._conn()
        try:
            cursor = conn.execute(
                "SELECT id, rule, context, created_at FROM rules WHERE active = 1 ORDER BY id DESC"
            )
            return [
                {"id": r[0], "rule": r[1], "context": r[2], "created_at": r[3]}
                for r in cursor.fetchall()
            ]
        finally:
            conn.close()

    # === Привязка тема→байк (персист, переживает рестарт) ===

    def set_topic_bike(self, chat_id, topic_id, bike_name: str, source: str = "auto"):
        """Upsert привязки тема→байк. Пустое имя НЕ пишем. Ручной override (source='manual')
        автоматическим источником НЕ перезатираем."""
        name = (bike_name or "").strip()
        if not (chat_id and topic_id and name):
            return
        conn = self._conn()
        try:
            if source != "manual":
                row = conn.execute(
                    "SELECT source FROM topic_bike WHERE chat_id=? AND topic_id=?",
                    (int(chat_id), int(topic_id))
                ).fetchone()
                if row and row[0] == "manual":
                    return   # не затираем ручную привязку авто-резолвом
            conn.execute(
                "INSERT INTO topic_bike (chat_id, topic_id, bike_name, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id, topic_id) DO UPDATE SET "
                "bike_name=excluded.bike_name, source=excluded.source, updated_at=excluded.updated_at",
                (int(chat_id), int(topic_id), name, source, datetime.now().isoformat())
            )
        finally:
            conn.close()

    def get_topic_bike(self, chat_id, topic_id) -> str:
        if not (chat_id and topic_id):
            return ""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT bike_name FROM topic_bike WHERE chat_id=? AND topic_id=?",
                (int(chat_id), int(topic_id))
            ).fetchone()
            return row[0] if row else ""
        finally:
            conn.close()

    def all_topic_bikes(self) -> Dict:
        """{(chat_id, topic_id): bike_name} — для seed _TOPIC_NAMES при старте."""
        conn = self._conn()
        try:
            rows = conn.execute("SELECT chat_id, topic_id, bike_name FROM topic_bike").fetchall()
            return {(int(r[0]), int(r[1])): r[2] for r in rows}
        finally:
            conn.close()

    # === Info-pin (закреп кнопки «ℹ️ Инфо» в темах обслуживания; зеркало topic_bike) ===

    def set_info_pin(self, chat_id, topic_id, msg_id):
        """Upsert id закреплённого сообщения-кнопки «ℹ️ Инфо» для темы."""
        if not (chat_id and topic_id and msg_id):
            return
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO info_pin (chat_id, topic_id, msg_id, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id, topic_id) DO UPDATE SET "
                "msg_id=excluded.msg_id, updated_at=excluded.updated_at",
                (int(chat_id), int(topic_id), int(msg_id), datetime.now().isoformat())
            )
        finally:
            conn.close()

    def get_info_pin(self, chat_id, topic_id):
        """id закреплённого сообщения-кнопки темы или None."""
        if not (chat_id and topic_id):
            return None
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT msg_id FROM info_pin WHERE chat_id=? AND topic_id=?",
                (int(chat_id), int(topic_id))
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()

    def all_info_pins(self) -> Dict:
        """{(chat_id, topic_id): msg_id} — для seed _INFO_PINNED при старте."""
        conn = self._conn()
        try:
            rows = conn.execute("SELECT chat_id, topic_id, msg_id FROM info_pin").fetchall()
            return {(int(r[0]), int(r[1])): int(r[2]) for r in rows}
        finally:
            conn.close()

    # === O3 наряды (ступень 1: просрочки → наряд → доставки; своя таблица, НЕ Лист1/CRM) ===

    _O3_COLS = ["id", "bike", "plate", "kinds", "from_where", "when_slot", "status",
                "delivery_msg_id", "board_chat", "board_msg", "created_at", "updated_at"]

    def o3_task_create(self, bike, plate="", kinds="", from_where="", when_slot="",
                       status="sent", delivery_msg_id=None, board_chat=None, board_msg=None):
        """Создать запись наряда O3 (обычно по факту отправки, status='sent'). Возвращает id."""
        now = datetime.now().isoformat()
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO o3_task (bike, plate, kinds, from_where, when_slot, status, "
                "delivery_msg_id, board_chat, board_msg, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(bike), str(plate or ""), str(kinds or ""), str(from_where or ""),
                 str(when_slot or ""), str(status or "new"),
                 int(delivery_msg_id) if delivery_msg_id else None,
                 int(board_chat) if board_chat else None,
                 int(board_msg) if board_msg else None, now, now)
            )
            return cur.lastrowid
        finally:
            conn.close()

    def o3_task_update(self, task_id, **fields):
        """Обновить поля наряда (status/delivery_msg_id/kinds/from_where/when_slot/...) + updated_at."""
        allowed = {"bike", "plate", "kinds", "from_where", "when_slot", "status",
                   "delivery_msg_id", "board_chat", "board_msg"}
        cols = [k for k in fields if k in allowed]
        if not task_id or not cols:
            return
        sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=?"
        vals = [fields[c] for c in cols] + [datetime.now().isoformat(), int(task_id)]
        conn = self._conn()
        try:
            conn.execute(f"UPDATE o3_task SET {sets} WHERE id=?", vals)
        finally:
            conn.close()

    def o3_task_get(self, task_id):
        """Наряд по id → dict или None."""
        if not task_id:
            return None
        conn = self._conn()
        try:
            row = conn.execute(
                f"SELECT {', '.join(self._O3_COLS)} FROM o3_task WHERE id=?", (int(task_id),)).fetchone()
        finally:
            conn.close()
        return dict(zip(self._O3_COLS, row)) if row else None

    def o3_tasks_active(self, status="sent"):
        """Наряды со статусом (по умолч. sent) → list dict. Для пометки байков «в наряде» на board."""
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT {', '.join(self._O3_COLS)} FROM o3_task WHERE status=? ORDER BY id DESC",
                (str(status),)).fetchall()
        finally:
            conn.close()
        return [dict(zip(self._O3_COLS, r)) for r in rows]

    # === O3 board «карточка-на-байк»: msg_id карточек для editMessageText на rescan (без дублей) ===

    def o3_card_set(self, board_chat, plate, msg_id):
        """Запомнить/обновить msg_id карточки байка (или заголовка, plate='__header__') на board."""
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO o3_card (board_chat, plate, msg_id, updated_at) VALUES (?, ?, ?, ?)",
                (int(board_chat), str(plate), int(msg_id), datetime.now().isoformat()))
        finally:
            conn.close()

    def o3_cards(self, board_chat):
        """Все карточки board-чата → {plate: msg_id} (вкл. '__header__')."""
        conn = self._conn()
        try:
            rows = conn.execute("SELECT plate, msg_id FROM o3_card WHERE board_chat=?",
                                (int(board_chat),)).fetchall()
        finally:
            conn.close()
        return {str(p): int(m) for p, m in rows}

    def o3_card_del(self, board_chat, plate):
        """Забыть карточку (байк помечен «✅ решено» — новая просрочка получит НОВУЮ карточку)."""
        conn = self._conn()
        try:
            conn.execute("DELETE FROM o3_card WHERE board_chat=? AND plate=?",
                         (int(board_chat), str(plate)))
        finally:
            conn.close()

    # === Corrections ===

    def add_correction(self, user_said: str, bot_did_before: str = "", bot_does_now: str = ""):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO corrections (created_at, user_said, bot_did_before, bot_does_now) "
                "VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), user_said, bot_did_before, bot_does_now)
            )
        finally:
            conn.close()

    # === Entity notes ===

    def add_note(self, entity_type: str, entity_key: str, note: str):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO entity_notes (created_at, entity_type, entity_key, note) "
                "VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), entity_type, entity_key, note)
            )
        finally:
            conn.close()

    def find_notes(self, entity_type: str, entity_key: str) -> List[Dict]:
        conn = self._conn()
        try:
            cursor = conn.execute(
                "SELECT note, created_at FROM entity_notes "
                "WHERE entity_type = ? AND entity_key LIKE ? ORDER BY id DESC",
                (entity_type, f"%{entity_key}%")
            )
            return [{"note": r[0], "created_at": r[1]} for r in cursor.fetchall()]
        finally:
            conn.close()

    # === Utility: контекст для Claude ===

    def get_context_for_claude(self, chat_id: int, history_limit: int = 12, topic_id=None) -> Dict:
        """Возвращает блок памяти для каждого запроса к Claude.
        topic_id — если задан, история берётся только по этой теме (темы не смешиваются)."""
        return {
            "history": self.recent_messages(chat_id, limit=history_limit, topic_id=topic_id),
            "rules": self.active_rules()[:30],
        }


if __name__ == "__main__":
    # Тест
    logging.basicConfig(level=logging.INFO)
    m = Memory()
    m.save_message(chat_id=123, user_id=1, user_name="Filipp", role="user", content="Привет")
    m.save_message(chat_id=123, user_id=None, user_name="Bot", role="assistant", content="Привет, Филипп!")
    m.add_rule("HONDA CLICK 125 не сдаём", "Установлено Филиппом 28.05.2026")
    print("Recent messages:", m.recent_messages(123))
    print("Active rules:", m.active_rules())
