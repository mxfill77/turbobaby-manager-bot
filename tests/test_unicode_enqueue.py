"""Класс инцидента 14.07.2026 (тайский текст в ТЗ → «internal_error»).
RECON: Bridge вернул internal_error (LockService lock-timeout) совпав с первым Thai-ТЗ.
       Thai-текст сам по себе в цепи devbot→Bridge→GAS проходит корректно (JSON UTF-8,
       GAS String.slice BMP-корректен); причина падения — Google Sheets lock contention.
Фикс: (а) _find_enqueued — NFC-нормализация обеих сторон сравнения;
       (б) _try_enqueue — NFC на входе (consistent с хранилищем);
       (в) _bridge_err_detail — human-readable вместо голого кода «internal_error».
Тесты: Thai/emoji текст в очереди читается обратно байт-в-байт;
        internal_error+lock → «занят (Google lock)»; timeout → читаемо; регресс цел.
Сети / Telegram / claude НЕТ."""
import os, sys, unicodedata, types
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["THEATER_ROUTER"] = "0"   # выкл. роутер — изолируем Unicode-путь

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB

# ── Строки для тестов ─────────────────────────────────────────────────────────
THAI_TEXT  = "สวัสดี — ตรวจสอบ: ระบบจัดการรถจักรยานยนต์เช่า TurboBaby ภูเก็ต"
EMOJI_TEXT = "тест 🎉 😂 🚗 — спецсимволы: ❤️ 🇹🇭"
MIXED_TEXT = f"ทดสอบ: {EMOJI_TEXT}"
LOCK_MSG_DE = ("Zeitüberschreitung bei Anforderung der Exklusivbearbeitung: "
               "Ein anderer Vorgang hat die Exklusivbearbeitung zu lange gebunden.")
LOCK_MSG_EN = "Timed out waiting for lock"


class SimpleBridge:
    """Мок: enqueue всегда OK, get_pending отдаёт items."""
    def __init__(s, items=None):
        s.enq_calls = []
        s._items = items or []
    def enqueue_task(s, frm, txt, lane=None):
        s.enq_calls.append((frm, txt, lane))
        return {"ok": True, "id": 200}
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": list(s._items)}


class FailBridge:
    """Мок: оба enqueue всегда падают с internal_error+lock; get_pending пуст."""
    def __init__(s, err="internal_error", msg=LOCK_MSG_DE):
        s.err, s.msg = err, msg
    def enqueue_task(s, frm, txt, lane=None):
        return {"ok": False, "error": s.err, "message": s.msg}
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": []}


# ── (а) Thai / emoji текст через _try_enqueue ─────────────────────────────────
print("(а) Thai/emoji — постановка сохраняет текст байт-в-байт:")

b = SimpleBridge()
card = DB._try_enqueue(f"тз: {THAI_TEXT}", b)
res.append(ok(card.startswith("✅") and "200" in card,
              f"Thai ТЗ → ✅ карточка ({card[:60]!r})"))
res.append(ok(len(b.enq_calls) == 1, "enqueue вызван ровно 1 раз"))
res.append(ok(b.enq_calls[0][1] == THAI_TEXT,
              f"task_text = Thai дословно ({b.enq_calls[0][1][:40]!r})"))

b2 = SimpleBridge()
DB._try_enqueue(f"тз: {EMOJI_TEXT}", b2)
res.append(ok(len(b2.enq_calls) == 1 and b2.enq_calls[0][1] == EMOJI_TEXT,
              "emoji — без потерь"))

b3 = SimpleBridge()
DB._try_enqueue(f"тз: {MIXED_TEXT}", b3)
res.append(ok(len(b3.enq_calls) == 1 and b3.enq_calls[0][1] == MIXED_TEXT,
              "Thai+emoji — без потерь"))

# префикс «задача:» тоже корректен
b4 = SimpleBridge()
DB._try_enqueue(f"задача: {THAI_TEXT}", b4)
res.append(ok(len(b4.enq_calls) == 1 and b4.enq_calls[0][1] == THAI_TEXT,
              "префикс «задача:» с Thai — без потерь"))

# ── (б) _find_enqueued с тайским текстом ──────────────────────────────────────
print("(б) _find_enqueued — NFC-нормализация и точный матч:")

item_thai = {"id": 201, "from": "Filipp-328-dev", "task_text": THAI_TEXT}


class VerifyBridge:
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [item_thai]}


found = DB._find_enqueued(VerifyBridge(), "Filipp-328-dev", THAI_TEXT)
res.append(ok(found == 201, "Thai текст → правильно находит id"))

# NFD-вариант тоже находит (NFC-нормализация обеих сторон)
thai_nfd = unicodedata.normalize("NFD", THAI_TEXT)
found_nfd = DB._find_enqueued(VerifyBridge(), "Filipp-328-dev", thai_nfd)
res.append(ok(found_nfd == 201, "NFD-вход → NFC-нормализация → тот же id"))

# неверный from — не находит
found_wrong_from = DB._find_enqueued(VerifyBridge(), "Filipp-328-wrong", THAI_TEXT)
res.append(ok(found_wrong_from is None, "неверный from → None (не присваивается)"))

# неверный текст — не находит
item_other = {"id": 202, "from": "Filipp-328-dev", "task_text": "другой текст"}


class OtherVerify:
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [item_other]}


found_wrong_text = DB._find_enqueued(OtherVerify(), "Filipp-328-dev", THAI_TEXT)
res.append(ok(found_wrong_text is None, "другой текст в pending → None"))

# emoji тоже находит
item_emoji = {"id": 203, "from": "Filipp-328-dev", "task_text": EMOJI_TEXT}


class EmojiVerify:
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [item_emoji]}


found_emoji = DB._find_enqueued(EmojiVerify(), "Filipp-328-dev", EMOJI_TEXT)
res.append(ok(found_emoji == 203, "emoji текст → правильно находит id"))

# ── (в) _bridge_err_detail — human-readable ───────────────────────────────────
print("(в) _bridge_err_detail — человекочитаемые ошибки:")

# lock timeout (немецкий — инцидент 14.07)
r_lock_de = {"ok": False, "error": "internal_error", "message": LOCK_MSG_DE}
d = DB._bridge_err_detail(r_lock_de)
res.append(ok("internal_error" not in d and ("lock" in d.lower() or "занят" in d.lower()),
              f"lock DE → без 'internal_error', читаемо: {d!r}"))

# lock timeout (английский)
r_lock_en = {"ok": False, "error": "internal_error", "message": LOCK_MSG_EN}
d_en = DB._bridge_err_detail(r_lock_en)
res.append(ok("internal_error" not in d_en and ("lock" in d_en.lower() or "занят" in d_en.lower()),
              f"lock EN → без 'internal_error': {d_en!r}"))

# timeout
r_timeout = {"ok": False, "error": "timeout", "message": "Timeout >60s"}
d_t = DB._bridge_err_detail(r_timeout)
res.append(ok("timeout" in d_t.lower() or "не ответил" in d_t.lower(),
              f"timeout → читаемо: {d_t!r}"))

# generic internal_error без message
r_ie_bare = {"ok": False, "error": "internal_error", "message": ""}
d_ie = DB._bridge_err_detail(r_ie_bare)
res.append(ok("internal_error" in d_ie.lower(),
              f"generic internal_error → содержит код: {d_ie!r}"))

# internal_error с полезным message
r_ie_msg = {"ok": False, "error": "internal_error", "message": "Script timeout exceeded"}
d_ie_m = DB._bridge_err_detail(r_ie_msg)
res.append(ok("script" in d_ie_m.lower() or "timeout" in d_ie_m.lower(),
              f"internal_error+message → показывает message: {d_ie_m!r}"))

# неизвестная ошибка с message
r_other = {"ok": False, "error": "not_found", "message": "row does not exist"}
d_oth = DB._bridge_err_detail(r_other)
res.append(ok("not_found" in d_oth and "row" in d_oth,
              f"not_found → код+message: {d_oth!r}"))

# неизвестная без message
r_no_msg = {"ok": False, "error": "bad_json"}
d_nm = DB._bridge_err_detail(r_no_msg)
res.append(ok(d_nm == "bad_json", f"нет message → просто код: {d_nm!r}"))

# ── (г) e2e: Thai ТЗ + Bridge lock → карточка читаема ────────────────────────
print("(г) e2e Thai+lock_error → человекочитаемая карточка:")

card_fail = DB._try_enqueue(f"тз: {THAI_TEXT}", FailBridge())
res.append(ok("Не удалось" in card_fail, f"карточка содержит 'Не удалось'"))
res.append(ok("internal_error" not in card_fail,
              f"карточка НЕ показывает голый 'internal_error' ({card_fail[:80]!r})"))
res.append(ok("lock" in card_fail.lower() or "занят" in card_fail.lower(),
              f"карточка содержит читаемую причину ({card_fail[:80]!r})"))

# timeout через _try_enqueue
card_timeout = DB._try_enqueue(f"тз: {THAI_TEXT}",
                               FailBridge(err="timeout", msg="Timeout >60s"))
res.append(ok("Не удалось" in card_timeout and "internal_error" not in card_timeout,
              f"timeout-карточка читаема ({card_timeout[:80]!r})"))

# ── (д) регресс: обычный ASCII текст — поведение как раньше ──────────────────
print("(д) регресс ASCII текст:")

b_asc = SimpleBridge()
card_asc = DB._try_enqueue("тз: прогони гейт", b_asc)
res.append(ok(card_asc.startswith("✅") and "200" in card_asc,
              f"ASCII ТЗ → ✅ ({card_asc[:60]!r})"))
res.append(ok(b_asc.enq_calls[0][1] == "прогони гейт",
              "ASCII task_text без изменений"))

# _bridge_err_detail для старого поведения (err без message)
d_old = DB._bridge_err_detail({"ok": False, "error": "unauthorized"})
res.append(ok(d_old == "unauthorized", f"unauthorized без message → код как раньше: {d_old!r}"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
