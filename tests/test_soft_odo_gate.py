"""Мягкий гейт убывания одометра (задача 383, этап 2).

Тесты:
A. delta ≤500 первый раз → soft-gate (механик сам)
B. delta >500 → эскалация на Пыма/владельца
C. Повтор подряд → эскалация даже при delta ≤500
D. handle_mileage_confirm: механик подтверждает ≤500 → разрешено + аудит
E. handle_mileage_confirm: не-Пым/не-владелец пытается ≥500 → блок + аудит
F. handle_mileage_confirm: Пым подтверждает >500 → разрешено + аудит
G. Аудит-след при отказе («нет»)
H. OCR-дыра: сырой vision-пробег НЕ попадает в mileage поля add_event

ЛЕГАСИ-СЬЮТ ПРЕЖНЕГО ОПРЕДЕЛЕНИЯ, ИЗОЛИРОВАН `ODO_LOWER=0` (23.08.2026). Его предмет — дверь
понижения ДО правила владельца 23.08: там расхождение подтверждалось односложным «намеренно», а
понижение больше 500 км уходило к Пыму/владельцу. Правило 23.08 отменило ОБА («пустое пояснение
и односложное согласие причиной не считаются»; «подтвердить понижение может ТОТ ЖЕ человек,
который прислал число, отдельный подтверждающий не требуется» — владелец назвал цену прямо:
меняем предотвращение на прослеживаемость). Новое определение живёт в `tests/test_odo_lower.py`
и `tests/test_odo_lower_path.py`; здесь флаг отката держит ПРЕЖНИЙ путь, чтобы он оставался
доказанным байт-в-байт. Приём тот же, что у CURATOR / PLAN_ADAPT / CARD_DUTY / CURATOR_STATE.
"""
import os, sys, asyncio, time, datetime
from unittest.mock import patch, AsyncMock, MagicMock
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# setdefault НЕ хватает: сьют наследует окружение гейта, а боевой дефолт ветки — «1».
os.environ["ODO_LOWER"] = "0"
import splinter as S

CHAT = -1002751134848
TOPIC = 77
BIKE = "NINJA 400 6334"
PREV_KM = 35000


def run(coro):
    return asyncio.run(coro)


class _FakeUser:
    def __init__(self, username=None, uid=None):
        self.username = username
        self.id = uid or 0


class _FakeMsg:
    def __init__(self, username=None, uid=None):
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.from_user = _FakeUser(username=username, uid=uid)


class _FakeBridge:
    def __init__(self):
        self.events = []
        self.service_calls = []

    def add_event(self, **kw):
        self.events.append(kw)
        return {"ok": True, "saved": True}

    def service_upsert(self, **kw):
        self.service_calls.append(kw)
        return {"ok": True, "status": "ok", "next_km": 40000}


def _setup_floor(new_km):
    """Поставить prev в буфер, вернуть floor."""
    key = (CHAT, TOPIC)
    from collections import deque
    S._RECENT_PHOTOS[key] = deque([{
        "ts": time.time(),
        "vis": {"mileage": str(PREV_KM), "mileage_confidence": "high"},
        "sender": "@test",
    }], maxlen=S._RECENT_LIMIT)
    return PREV_KM


def _clear():
    S._SOFT_ODO_PENDING.pop((CHAT, TOPIC), None)
    S._PENDING_MILEAGE.pop((CHAT, TOPIC), None)
    S._ODO_DROP_CONSEC.clear()
    S._RECENT_PHOTOS.pop((CHAT, TOPIC), None)
    S._SVC_TOKENS.clear()


# ── A. delta ≤500 первый раз → soft-gate сообщение (не hard-block) ────────────

async def _run_ask_soft(new_km):
    _clear()
    _setup_floor(new_km)
    sent = []

    async def fake_send(context, *, chat_id, text, message_thread_id=None, **kw):
        sent.append(text)
        return MagicMock(message_id=1)

    with patch.object(S, "_send", side_effect=fake_send):
        await S._ask_mileage_confirm(None, CHAT, TOPIC, BIKE, str(new_km))
    return sent


def test_soft_gate_small_drop():
    """delta ≤500: soft-gate (не жёсткий отказ), pending = escalate=False."""
    new_km = PREV_KM - 300   # delta = 300 ≤ 500
    sent = run(_run_ask_soft(new_km))
    assert sent, "soft-gate должен отправить сообщение"
    text = sent[0]
    assert "намеренно" in text.lower() or "ตั้งใจ" in text, (
        f"soft-gate сообщение должно спрашивать 'намеренно': {text[:120]}")
    soft = S._SOFT_ODO_PENDING.get((CHAT, TOPIC))
    assert soft is not None, "Soft gate pending должен быть установлен"
    assert soft["escalate"] is False, "delta 300 ≤ 500 → escalate=False"
    # Старый msg_mileage_drop не должен содержаться
    assert "не может уменьшиться" not in text, f"Старый hard-block не должен использоваться: {text[:120]}"


# ── B. delta >500 → эскалация ──────────────────────────────────────────────────

def test_escalate_big_drop():
    """delta >500: эскалация, pending = escalate=True."""
    new_km = PREV_KM - 600   # delta = 600 > 500
    sent = run(_run_ask_soft(new_km))
    assert sent, "escalate должен отправить сообщение"
    text = sent[0]
    assert "пым" in text.lower() or "pym" in text.lower() or "pleum" in text.lower() or "เจ้าของ" in text, (
        f"Эскалация должна упоминать Пыма/владельца: {text[:200]}")
    soft = S._SOFT_ODO_PENDING.get((CHAT, TOPIC))
    assert soft is not None and soft["escalate"] is True, "delta 600 > 500 → escalate=True"


# ── C. Повтор → эскалация даже при delta ≤500 ─────────────────────────────────

def test_consecutive_escalates():
    """Второй раз подряд убывание → эскалация независимо от delta."""
    _clear()
    new_km = PREV_KM - 100   # delta всего 100 — но второй раз
    key = (CHAT, TOPIC)
    # Подготовка: буфер prev + consec (ПОСЛЕ _clear, чтобы не затёрлось)
    _setup_floor(new_km)
    S._ODO_DROP_CONSEC[BIKE] = (1, time.time() - 60)   # свежая запись
    sent = []

    async def fake_send(context, *, chat_id, text, message_thread_id=None, **kw):
        sent.append(text)
        return MagicMock(message_id=1)

    async def _run():
        with patch.object(S, "_send", side_effect=fake_send):
            await S._ask_mileage_confirm(None, CHAT, TOPIC, BIKE, str(new_km))

    run(_run())
    soft = S._SOFT_ODO_PENDING.get(key)
    assert soft is not None and soft["escalate"] is True, (
        "Повторное убывание должно → escalate=True даже при delta ≤500")


# ── D. Механик подтверждает ≤500 → разрешено + аудит ─────────────────────────

def test_mechanic_confirms_small_drop():
    """Trusted механик подтверждает soft-gate ≤500 → permitted, аудит записывается."""
    _clear()
    new_km = PREV_KM - 300
    key = (CHAT, TOPIC)
    S._PENDING_MILEAGE[key] = (str(new_km), BIKE, PREV_KM, False)
    S._SOFT_ODO_PENDING[key] = {
        "new_km": new_km, "prev_km": PREV_KM, "bike": BIKE,
        "escalate": False, "ts": time.time(),
    }

    bridge = _FakeBridge()
    after_called = []

    async def fake_after(ctx, br, cid, tid, bike, mileage, oil_hint=False):
        after_called.append(mileage)

    msg = _FakeMsg(username="Pleummmm")   # Пым — доверенный

    with patch.object(S, "_after_mileage", side_effect=fake_after):
        result = run(S.handle_mileage_confirm(msg, None, bridge, "да"))

    assert result is True, "handle_mileage_confirm должен вернуть True"
    assert after_called, "_after_mileage должен быть вызван (подтверждено)"
    # Аудит записан
    audit_events = [e for e in bridge.events if e.get("event_type") == "odo_audit"]
    assert audit_events, "Аудит-след должен быть записан при подтверждении"
    assert "подтверждено" in audit_events[0]["notes"], (
        f"Аудит должен содержать 'подтверждено': {audit_events[0]['notes']}")
    # Soft gate очищен
    assert key not in S._SOFT_ODO_PENDING, "Soft gate должен быть очищен после подтверждения"


# ── E. Не-Пым/не-владелец при эскалации → блок + аудит ──────────────────────

def test_non_owner_blocked_on_escalated():
    """Не-Пым/не-владелец пытается подтвердить drop >500 → блок + аудит."""
    _clear()
    new_km = PREV_KM - 600
    key = (CHAT, TOPIC)
    S._PENDING_MILEAGE[key] = (str(new_km), BIKE, PREV_KM, False)
    S._SOFT_ODO_PENDING[key] = {
        "new_km": new_km, "prev_km": PREV_KM, "bike": BIKE,
        "escalate": True, "ts": time.time(),
    }

    bridge = _FakeBridge()
    sent = []

    async def fake_send(context, *, chat_id, text, message_thread_id=None, **kw):
        sent.append(text)

    after_called = []

    async def fake_after(*a, **k):
        after_called.append(1)

    msg = _FakeMsg(username="mechanic_user")   # не Пым, не владелец

    with patch.object(S, "_send", side_effect=fake_send), \
         patch.object(S, "_after_mileage", side_effect=fake_after):
        result = run(S.handle_mileage_confirm(msg, None, bridge, "да"))

    assert result is True, "Должен вернуть True (обработал)"
    assert not after_called, "_after_mileage НЕ должен вызываться (заблокировано)"
    # Pending должен жить (ждём Пыма/владельца)
    assert key in S._SOFT_ODO_PENDING, "Soft gate должен остаться (ждём авторизованного)"
    # Аудит записан
    audit_events = [e for e in bridge.events if e.get("event_type") == "odo_audit"]
    assert audit_events, "Аудит-след должен быть записан при блоке"
    assert "заблокировано" in audit_events[0]["notes"], (
        f"Аудит должен содержать 'заблокировано': {audit_events[0]['notes']}")
    # Сообщение о необходимости Пыма
    assert sent, "Должно быть сообщение о необходимости Пыма/владельца"


# ── F. Пым подтверждает drop >500 → разрешено + аудит ───────────────────────

def test_pym_confirms_big_drop():
    """Пым подтверждает drop >500 → allowed + аудит с 'Пым/владелец'."""
    _clear()
    new_km = PREV_KM - 600
    key = (CHAT, TOPIC)
    S._PENDING_MILEAGE[key] = (str(new_km), BIKE, PREV_KM, False)
    S._SOFT_ODO_PENDING[key] = {
        "new_km": new_km, "prev_km": PREV_KM, "bike": BIKE,
        "escalate": True, "ts": time.time(),
    }

    bridge = _FakeBridge()
    after_called = []

    async def fake_after(ctx, br, cid, tid, bike, mileage, oil_hint=False):
        after_called.append(mileage)

    # Пым по username
    pym_username = next(iter(S.PYM_USERNAMES))
    msg = _FakeMsg(username=pym_username)

    with patch.object(S, "_after_mileage", side_effect=fake_after):
        result = run(S.handle_mileage_confirm(msg, None, bridge, "да"))

    assert result is True
    assert after_called, "_after_mileage должен быть вызван (Пым подтвердил)"
    audit_events = [e for e in bridge.events if e.get("event_type") == "odo_audit"]
    assert audit_events, "Аудит должен быть записан"
    assert "подтверждено" in audit_events[0]["notes"]
    assert key not in S._SOFT_ODO_PENDING, "Soft gate очищен"


# ── G. Аудит при отказе («нет») ───────────────────────────────────────────────

def test_audit_on_rejection():
    """Пользователь говорит «нет» → аудит-след с outcome='отказ'."""
    _clear()
    new_km = PREV_KM - 300
    key = (CHAT, TOPIC)
    S._PENDING_MILEAGE[key] = (str(new_km), BIKE, PREV_KM, False)
    S._SOFT_ODO_PENDING[key] = {
        "new_km": new_km, "prev_km": PREV_KM, "bike": BIKE,
        "escalate": False, "ts": time.time(),
    }

    bridge = _FakeBridge()
    sends = []

    async def fake_send(ctx, *, chat_id, text, message_thread_id=None, **kw):
        sends.append(text)

    msg = _FakeMsg(username="Pleummmm")

    with patch.object(S, "_send", side_effect=fake_send):
        result = run(S.handle_mileage_confirm(msg, None, bridge, "нет"))

    assert result is True
    audit_events = [e for e in bridge.events if e.get("event_type") == "odo_audit"]
    assert audit_events, "Аудит-след должен быть записан при отказе"
    assert "отказ" in audit_events[0]["notes"], (
        f"Аудит должен содержать 'отказ': {audit_events[0]['notes']}")
    assert key not in S._SOFT_ODO_PENDING, "Soft gate очищен"


# ── H. OCR-дыра: сырой vision-пробег НЕ попадает в mileage add_event ─────────

async def _run_servicing_with_vis_mileage():
    """Имитируем фото с vision-пробегом (без text mileage) → add_event получает mileage=''."""
    key = (CHAT, TOPIC)
    S._RECENT_PHOTOS.pop(key, None)
    S._PENDING_WORKS.pop(key, None)
    S._ODOMETER_ASK_TS.clear()

    class FakeMsg:
        text = None
        caption = None
        photo = [1]
        chat_id = CHAT
        message_thread_id = TOPIC
        message_id = 999
        from_user = _FakeUser(username="Pleummmm")
        date = datetime.datetime(2026, 7, 24, 10, 0, tzinfo=datetime.timezone.utc)

    bridge = _FakeBridge()

    class FakeClaude:
        def quick(self, system, text, max_tokens=300, **kw):
            return "{}"   # пустой parse — нет event из текста

        def vision(self, system, img, max_tokens=400, **kw):
            import json
            return json.dumps({"mileage": "34500", "mileage_confidence": "high",
                               "fuel": "", "damage": None, "dirt": False})

    async def fake_dl(pm):
        return b"img"

    async def fake_ask_conf(ctx, cid, tid, bike, mileage, oil_hint=False):
        pass   # перехватываем — не отправляем

    async def fake_send(*a, **k):
        return MagicMock(message_id=1)

    with patch.object(S, "_download_photo", side_effect=fake_dl), \
         patch.object(S, "_ask_mileage_confirm", side_effect=fake_ask_conf), \
         patch.object(S, "_send", side_effect=fake_send), \
         patch.object(S, "bike_from_topic", return_value=BIKE), \
         patch.object(S, "group_label", return_value="тест"):
        await S._handle_servicing(FakeMsg(), context=None, bridge=bridge,
                                  claude=FakeClaude(), photo_msgs=[FakeMsg()])

    return bridge


def test_ocr_mileage_not_in_add_event():
    """Vision-пробег (raw OCR) не попадает в mileage поля add_event до подтверждения."""
    bridge = run(_run_servicing_with_vis_mileage())
    # Ищем add_event (не odo_audit)
    plain_events = [e for e in bridge.events if e.get("event_type") != "odo_audit"]
    if not plain_events:
        # Событие могло не записаться (info_works пусты, нет parsed.type = "event")
        # Проверим что нет ни одного события с mileage=34500
        bad = [e for e in bridge.events if str(e.get("mileage")) == "34500"]
        assert not bad, f"OCR-пробег 34500 НЕ должен попасть в add_event: {bad}"
        return
    for ev in plain_events:
        assert str(ev.get("mileage", "")) != "34500", (
            f"OCR-пробег 34500 НЕ должен попасть в add_event до подтверждения: {ev}")


if __name__ == "__main__":
    tests = [
        ("A soft_gate_small_drop",          test_soft_gate_small_drop),
        ("B escalate_big_drop",             test_escalate_big_drop),
        ("C consecutive_escalates",         test_consecutive_escalates),
        ("D mechanic_confirms_small_drop",  test_mechanic_confirms_small_drop),
        ("E non_owner_blocked_escalated",   test_non_owner_blocked_on_escalated),
        ("F pym_confirms_big_drop",         test_pym_confirms_big_drop),
        ("G audit_on_rejection",            test_audit_on_rejection),
        ("H ocr_mileage_not_in_add_event",  test_ocr_mileage_not_in_add_event),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
        except Exception as e:
            print(f"  ❌ {name}: EXCEPTION {e}")
    print(f"\n{passed}/{len(tests)} passed")
    if passed < len(tests):
        sys.exit(1)
