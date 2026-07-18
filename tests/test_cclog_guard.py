"""test_cclog_guard.py — length-monotonic guard + единый формат + race-mock.

Инцидент 17.07.2026: legacy scratchpad-скрипты (_log_test1.py, _test1_cclog.py, _write_cclog_checkx.py)
использовали r.get("content","") вместо r.get("text",""). Bridge API возвращает {"ok":True,"text":"..."};
"content" = "" → скрипт писал DONE_LINE+"" = tiny content → затирание ~200KB истории cc_log.

Тесты:
(A) length-guard через write_cclog(): guard блокирует shrink, разрешает рост
(B) length-guard через main(): аналогично, путь CLI
(C) race-mock: "content" vs "text" ключ — показывает почему канонический путь не стирает лог
(D) единый формат: write_cclog() всегда через _make_entry → ENTRY_RE
(E) alert вызван при guard-срабатывании
(F) write_cclog vs bypass: bypass с empty old даёт tiny; write_cclog с правильным read даёт full
"""
import os
import sys

os.environ.setdefault("ORCH_TEST_MODE", "1")   # no network
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # no Telegram
sys.path.insert(0, "/root/turbobaby-manager-bot")

import cclog

res = []
def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


# ─── Вспомогательные моки ───────────────────────────────────────────────────

BIG_CONTENT = "═" * 60 + "\n\nстарая запись\n" + "x" * 800  # ~870 символов

_writes = {}

class _Bridge:
    """Мок BridgeClient с заданным начальным содержимым cc_log."""
    def __init__(self, text=BIG_CONTENT):
        self._text = text

    def _call(self, action, **kw):
        if action == "read_doc":
            return {"ok": True, "text": self._text}
        return {"ok": False, "error": "unexpected"}

    def write_doc(self, text, name=None, id=None):
        _writes[name or id] = text
        return {"ok": True}


class _FailReadBridge(_Bridge):
    def _call(self, action, **kw):
        return {"ok": False, "error": "timeout"}


# Перехватываем _alert_shrink для счётчика вызовов
_alerts = []
_orig_alert = cclog._alert_shrink

def _mock_alert(old_len, new_len, entry_preview=""):
    _alerts.append({"old_len": old_len, "new_len": new_len})

cclog._alert_shrink = _mock_alert


# ─── (A) length-guard через write_cclog() ───────────────────────────────────

# A1: нормальная запись — длина растёт, guard не срабатывает
_writes.clear()
ok_a1 = cclog.write_cclog("DONE", "тест записи A1", bridge=_Bridge())
ok(ok_a1, "(A1) write_cclog: нормальная запись → success")
ok("cc_log" in _writes, "(A1) write_cclog: write_doc вызван")
ok(len(_writes.get("cc_log", "")) >= len(BIG_CONTENT),
   "(A1) write_cclog: новый контент длиннее старого (monotonic ✓)")

# A2: SHRINK guard — подменяем _insert_under_vrezka чтобы вернуть short
_orig_insert = cclog._insert_under_vrezka
cclog._insert_under_vrezka = lambda old, line: "tiny"
_writes.clear()
_alerts.clear()
ok_a2 = cclog.write_cclog("DONE", "shrink test", bridge=_Bridge())
cclog._insert_under_vrezka = _orig_insert  # восстановить немедленно

ok(not ok_a2, "(A2) write_cclog: SHRINK → возвращает False (guard сработал)")
ok("cc_log" not in _writes, "(A2) write_cclog: SHRINK → write_doc НЕ вызван")
ok(len(_alerts) > 0, "(A2) write_cclog: SHRINK → _alert_shrink вызван")
ok(_alerts[0]["old_len"] > _alerts[0]["new_len"],
   "(A2) write_cclog: alert содержит корректные old_len > new_len")

# A3: read FAIL → не пишем
_writes.clear()
ok_a3 = cclog.write_cclog("DONE", "fail test", bridge=_FailReadBridge())
ok(not ok_a3, "(A3) write_cclog: read FAIL → False")
ok("cc_log" not in _writes, "(A3) write_cclog: read FAIL → write НЕ вызван")

# A4: guard разрешает empty→nonempty (первая запись в пустом журнале)
_writes.clear()
ok_a4 = cclog.write_cclog("PLAN", "первая запись", bridge=_Bridge(text=""))
ok(ok_a4, "(A4) write_cclog: empty old → первая запись разрешена")
ok(len(_writes.get("cc_log", "")) > 0, "(A4) write_cclog: что-то записано")


# ─── (B) length-guard через main() (CLI-путь) ──────────────────────────────

# Подменяем BridgeClient в cclog на наш мок
cclog.BridgeClient = lambda: _Bridge()

_writes.clear()
rc_b1 = cclog.main(["DONE", "тест main B1"])
ok(rc_b1 == 0, "(B1) main: нормальная запись → rc=0")
ok(len(_writes.get("cc_log", "")) >= len(BIG_CONTENT),
   "(B1) main: новый контент длиннее старого (monotonic ✓)")

# B2: main() с SHRINK guard
cclog._insert_under_vrezka = lambda old, line: "tiny"
_writes.clear()
_alerts.clear()
rc_b2 = cclog.main(["DONE", "shrink via main"])
cclog._insert_under_vrezka = _orig_insert

ok(rc_b2 != 0, "(B2) main: SHRINK → rc≠0 (guard сработал)")
ok("cc_log" not in _writes, "(B2) main: SHRINK → write_doc НЕ вызван")
ok(len(_alerts) > 0, "(B2) main: SHRINK → _alert_shrink вызван")

# B3: main() read FAIL
cclog.BridgeClient = lambda: _FailReadBridge()
_writes.clear()
rc_b3 = cclog.main(["NOTE", "fail read main"])
ok(rc_b3 != 0, "(B3) main: read FAIL → rc≠0")
ok("cc_log" not in _writes, "(B3) main: read FAIL → write НЕ вызван")


# ─── (C) race-mock: "content" vs "text" ключ ───────────────────────────────
# Показывает ПОЧЕМУ произошёл инцидент и что canonical path защищает от него.

REAL_CONTENT = "═" * 60 + "\n\n" + "реальная история\n" * 50   # ~870 символов

class _RealBridge:
    """Мок с реальным содержимым (как возвращает Bridge — ключ "text")."""
    def _call(self, action, **kw):
        return {"ok": True, "text": REAL_CONTENT}

    def write_doc(self, text, name=None, id=None):
        _writes[name or id] = text
        return {"ok": True}

r = _RealBridge()._call("read_doc", name="cc_log")

# Баг bypass-скриптов: читали "content" вместо "text"
buggy_old = r.get("content", "")   # "" — пустая строка
canonical_old = r.get("text", "")  # "реальная история..."

ok(buggy_old == "", "(C1) race-mock: r.get('content','') = '' (баг legacy-скриптов)")
ok(len(canonical_old) > 100, "(C2) race-mock: r.get('text','') = реальный контент")
ok(len(buggy_old) < len(canonical_old),
   "(C3) race-mock: buggy_old < canonical_old → bypass-запись затёрла бы лог")

# Canonical write_cclog использует правильный ключ → лог сохраняется
_writes.clear()
ok_c4 = cclog.write_cclog("DONE", "canonical write", bridge=_RealBridge())
ok(ok_c4, "(C4) race-mock: write_cclog (canonical) → success")
ok("реальная история" in _writes.get("cc_log", ""),
   "(C4) race-mock: canonical write сохраняет реальный контент")

# Bypass с buggy_old="" → wrote tiny (показываем КАК бы это выглядело)
import cclog as _m
tiny_bypass = "DONE 2026-07-17 UTC (headless): тест 1" + buggy_old
ok(len(tiny_bypass) < len(REAL_CONTENT),
   "(C5) race-mock: bypass-запись была бы tiny < real → затирание подтверждено")


# ─── (D) единый формат: write_cclog() всегда через _make_entry → ENTRY_RE ──

import re
cclog.BridgeClient = lambda: _Bridge()
for kind in cclog.TYPES:
    _writes.clear()
    cclog.write_cclog(kind, f"текст типа {kind}", bridge=_Bridge())
    written = _writes.get("cc_log", "")
    # Ищем хотя бы одну строку в каноническом формате
    found = any(cclog.ENTRY_RE.match(ln) for ln in written.splitlines())
    ok(found, f"(D) write_cclog kind={kind}: ENTRY_RE match в записанном контенте")


# ─── (E) _alert_shrink вызван с корректными аргументами ─────────────────────

_alerts.clear()
cclog._insert_under_vrezka = lambda old, line: "short"
cclog.write_cclog("DONE", "trigger shrink", bridge=_Bridge(text="A" * 200))
cclog._insert_under_vrezka = _orig_insert

ok(len(_alerts) == 1, "(E1) _alert_shrink вызван ровно 1 раз на shrink")
if _alerts:
    ok(_alerts[0]["old_len"] == 200, "(E2) alert: old_len = 200 (длина исходного)")
    ok(_alerts[0]["new_len"] == len("short"), f"(E3) alert: new_len = {len('short')}")


# ─── (F) write_cclog vs прямой write_doc с wrong key ───────────────────────

class _CaptureWriteBridge(_RealBridge):
    def write_doc(self, text, name=None, id=None):
        _writes[name or id] = text
        return {"ok": True}

_writes.clear()
# Что было бы если bypass-скрипт взял buggy_old="" и написал напрямую:
tiny = "DONE 2026-07-17 03:00 UTC (headless): тест N"
_CaptureWriteBridge().write_doc(text=tiny, name="cc_log")
bypass_result = _writes.get("cc_log", "")

_writes.clear()
cclog.write_cclog("DONE", "тест N — canonical", bridge=_CaptureWriteBridge())
canonical_result = _writes.get("cc_log", "")

ok(len(bypass_result) < len(REAL_CONTENT),
   "(F1) bypass прямой write_doc: записывает tiny < реального лога → РИСК ЗАТИРАНИЯ")
ok(len(canonical_result) >= len(REAL_CONTENT),
   "(F2) write_cclog canonical: записывает full content ≥ реального лога → лог сохранён")


# ─── итог ────────────────────────────────────────────────────────────────────

# Восстанавливаем _alert_shrink (чтобы не мешать другим тестам при pytest)
cclog._alert_shrink = _orig_alert

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
