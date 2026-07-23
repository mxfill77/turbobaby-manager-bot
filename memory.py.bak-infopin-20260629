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
from datetime import datetime
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
        каждая тема = свой байк, истории тем НЕ смешиваются)."""
        conn = self._conn()
        try:
            if topic_id is not None:
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
