"""Тесты TTL-фильтра истории servicing-тем (SERVICING_HISTORY_TTL_H, класс D).
Проверяет: свежее → в контексте; старое > TTL → вырезается; fail-safe: мусор
в env → без фильтра; topic_id=None → фильтр не применяется."""
import os, sys, tempfile, sqlite3
from datetime import datetime, timedelta

os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
sys.path.insert(0, "/root/turbobaby-manager-bot")

from memory import Memory

CHAT = -100777
TOPIC = 55

def ok(cond, msg):
    assert cond, msg

def _make_mem():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    m = Memory(db_path=tmp.name)
    return m

def _ts(hours_ago: float) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).isoformat()

def _insert_msg(m, role, content, topic_id, hours_ago=0.0):
    conn = sqlite3.connect(m.db_path, isolation_level=None)
    ts = _ts(hours_ago)
    conn.execute(
        "INSERT INTO conversations (timestamp, chat_id, user_id, user_name, role, content, is_voice, topic_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, CHAT, 1, "test", role, content, 0, str(topic_id))
    )
    conn.close()

# ── A. Свежее сообщение (1h) → попадает в историю ────────────────────
def test_fresh_message_included():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "48"
    _insert_msg(m, "user", "свежее сообщение", TOPIC, hours_ago=1)
    msgs = m.recent_messages(CHAT, topic_id=TOPIC)
    ok(len(msgs) == 1, f"A: ожидали 1 сообщение, получили {len(msgs)}")
    ok(msgs[0]["content"] == "свежее сообщение", "A: неверный content")

# ── B. Старое сообщение (> TTL) → исключается ────────────────────────
def test_old_message_excluded():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "24"
    _insert_msg(m, "user", "старое сообщение", TOPIC, hours_ago=48)  # 48h > 24h TTL
    msgs = m.recent_messages(CHAT, topic_id=TOPIC)
    ok(len(msgs) == 0, f"B: старое сообщение должно быть отфильтровано, получили {len(msgs)}")

# ── C. Смесь: старое + свежее → только свежее ────────────────────────
def test_mixed_old_and_fresh():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "48"
    _insert_msg(m, "user", "старое", TOPIC, hours_ago=72)    # 72h > 48h
    _insert_msg(m, "assistant", "свежее", TOPIC, hours_ago=1) # 1h < 48h
    msgs = m.recent_messages(CHAT, topic_id=TOPIC)
    ok(len(msgs) == 1, f"C: ожидали 1 (свежее), получили {len(msgs)}: {msgs}")
    ok(msgs[0]["content"] == "свежее", f"C: content={msgs[0]['content']}")

# ── D. Невалидный env (мусор) → fail-safe: без фильтра, все сообщения ─
def test_invalid_env_no_filter():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "not_valid"
    _insert_msg(m, "user", "очень старое", TOPIC, hours_ago=1000)
    msgs = m.recent_messages(CHAT, topic_id=TOPIC)
    ok(len(msgs) == 1, f"D: fail-safe — невалидный env не должен фильтровать, получили {len(msgs)}")

# ── E. TTL=0 → без фильтра (все сообщения) ───────────────────────────
def test_zero_ttl_no_filter():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "0"
    _insert_msg(m, "user", "очень старое", TOPIC, hours_ago=9999)
    msgs = m.recent_messages(CHAT, topic_id=TOPIC)
    ok(len(msgs) == 1, f"E: TTL=0 → без фильтра, получили {len(msgs)}")

# ── F. Без topic_id → фильтр по времени НЕ применяется ──────────────
def test_no_topic_id_no_filter():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "1"   # 1h TTL
    _insert_msg(m, "user", "старое без темы", TOPIC, hours_ago=48)  # 48h > 1h
    # Без topic_id фильтр не должен применяться
    msgs = m.recent_messages(CHAT, topic_id=None)
    ok(len(msgs) == 1, f"F: без topic_id TTL не применяется, получили {len(msgs)}")

# ── G. Лимит соблюдается поверх TTL ──────────────────────────────────
def test_limit_respected():
    m = _make_mem()
    os.environ["SERVICING_HISTORY_TTL_H"] = "48"
    for i in range(5):
        _insert_msg(m, "user", f"msg{i}", TOPIC, hours_ago=i * 0.1)
    msgs = m.recent_messages(CHAT, limit=3, topic_id=TOPIC)
    ok(len(msgs) == 3, f"G: limit=3, получили {len(msgs)}")

# ── Запуск ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("A fresh_included",         test_fresh_message_included),
        ("B old_excluded",           test_old_message_excluded),
        ("C mixed_old_and_fresh",    test_mixed_old_and_fresh),
        ("D invalid_env_no_filter",  test_invalid_env_no_filter),
        ("E zero_ttl_no_filter",     test_zero_ttl_no_filter),
        ("F no_topic_no_filter",     test_no_topic_id_no_filter),
        ("G limit_respected",        test_limit_respected),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
        finally:
            os.environ.pop("SERVICING_HISTORY_TTL_H", None)
    print(f"\n{passed}/{len(tests)} passed")
    if passed < len(tests):
        sys.exit(1)
