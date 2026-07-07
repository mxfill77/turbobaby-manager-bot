"""ФИКС КЛАССА инцидента 07.07.2026 (задача 138) — сторона DEVBOT (постановка из 328).
Инцидент: Bridge-сбой → enqueue получил «unauthorized» клиентски, Филипп увидел «Не удалось
поставить ТЗ», хотя задача сервер-сайд ВСТАЛА (повторная обработка дала 138).
Самотесты ТЗ: (а) сбой классификатора (unauthorized/exit!=0 CLI) → задача ТИХО встала в vps
с подсказкой; (б) ТОТАЛЬНЫЙ fail-safe — любое исключение роутера → vps, постановка не падает;
(в) _enqueue_reliable: ответ потерялся → verify находит задачу в new → ✅ с её id (без дубля);
verify пуст → РОВНО один повтор; оба сбоя → честная ошибка как раньше; успех → 1 вызов;
(г) e2e _try_enqueue при сбойном первом enqueue → карточка ✅. Сети/Telegram/claude НЕТ."""
import os, sys, types
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["THEATER_ROUTER"] = "1"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import devbot as DB


class FlakyBridge:
    """enqueue отвечает по сценарию (список результатов), get_pending отдаёт заготовку new."""
    def __init__(s, enq_results, pending_items=None):
        s.enq_results, s.enq_calls, s.pending_calls = list(enq_results), [], []
        s.pending_items = pending_items or []
    def enqueue_task(s, frm, txt, lane=None):
        s.enq_calls.append((frm, txt, lane))
        return s.enq_results.pop(0) if s.enq_results else {"ok": False, "error": "empty"}
    def get_pending(s, status="new", lane=None):
        s.pending_calls.append((status, lane))
        return {"ok": True, "items": list(s.pending_items)}


# (а) сбой классификатора (exit!=0 — та же ветка, что unauthorized CLI) → vps + подсказка
print("(а) unauthorized/exit!=0 классификатора → fail-safe vps:")
_real_run = DB.subprocess.run
DB.subprocess.run = lambda *a, **k: types.SimpleNamespace(
    returncode=1, stdout="unauthorized", stderr="OAuth token expired")
th, txt, note = DB._route_328("сделай что-нибудь неоднозначное")
res.append(ok(th == "vps" and note == DB.ROUTER_HINT and txt == "сделай что-нибудь неоднозначное",
              "классификатор exit!=0 → театр vps + подсказка, текст цел"))
b = FlakyBridge([{"ok": True, "id": 61}])
card = DB._try_enqueue("тз: сделай что-нибудь неоднозначное", b)
res.append(ok(card.startswith("✅") and "61" in card and "🎭 vps" in card and DB.ROUTER_HINT in card,
              f"постановка ТИХО прошла в vps ({card[:70]!r})"))
DB.subprocess.run = _real_run

# (б) ТОТАЛЬНЫЙ fail-safe: роутер бросает ЛЮБОЕ исключение → vps, постановка не падает
print("(б) тотальный fail-safe роутера:")
_real_route = DB._route_theater
def boom(text):
    raise RuntimeError("нежданная дыра роутера")
DB._route_theater = boom
th, txt, note = DB._route_328("любой текст задачи")
res.append(ok(th == "vps" and txt == "любой текст задачи" and note == DB.ROUTER_HINT,
              "исключение роутера → vps + подсказка (постановка не падает наружу)"))
b = FlakyBridge([{"ok": True, "id": 62}])
card = DB._try_enqueue("задача: любой текст задачи", b)
res.append(ok(card.startswith("✅") and "62" in card, f"e2e: карточка ✅ несмотря на смерть роутера"))
DB._route_theater = _real_route

# (в) _enqueue_reliable
print("(в) надёжная постановка:")
# успех сразу → один вызов, verify не дёргается
b = FlakyBridge([{"ok": True, "id": 70}])
r = DB._enqueue_reliable(b, "Filipp-328-dev", "текст")
res.append(ok(r.get("ok") and r.get("id") == 70 and len(b.enq_calls) == 1 and not b.pending_calls,
              "успех сразу → 1 вызов, без verify (как раньше)"))
# ответ потерялся, задача ВСТАЛА (кейс 138) → verify находит → ✅ её id, БЕЗ повторного enqueue
b = FlakyBridge([{"ok": False, "error": "unauthorized"}],
                pending_items=[{"id": 138, "from": "Filipp-328-dev", "task_text": "текст"}])
r = DB._enqueue_reliable(b, "Filipp-328-dev", "текст")
res.append(ok(r.get("ok") and r.get("id") == 138 and len(b.enq_calls) == 1
              and b.pending_calls == [("new", "all")],
              "ответ потерялся, задача в new → поставлена (id найден, ДУБЛЯ нет)"))
# verify пуст → РОВНО один повтор enqueue → успех
b = FlakyBridge([{"ok": False, "error": "request_failed"}, {"ok": True, "id": 71}])
r = DB._enqueue_reliable(b, "Filipp-328-dev", "текст")
res.append(ok(r.get("ok") and r.get("id") == 71 and len(b.enq_calls) == 2,
              "задачи в new нет → один повтор → успех"))
# оба сбоя → честная ошибка (как раньше), больше двух попыток НЕ делается
b = FlakyBridge([{"ok": False, "error": "unauthorized"}, {"ok": False, "error": "unauthorized"}])
r = DB._enqueue_reliable(b, "Filipp-328-dev", "текст")
res.append(ok(not r.get("ok") and r.get("error") == "unauthorized" and len(b.enq_calls) == 2,
              "оба сбоя → честная ошибка, ровно 2 попытки"))
# чужая задача в new (другой текст/from) — за свою НЕ выдаётся
b = FlakyBridge([{"ok": False, "error": "unauthorized"}, {"ok": True, "id": 72}],
                pending_items=[{"id": 999, "from": "Filipp-328-dev", "task_text": "ДРУГОЙ текст"}])
r = DB._enqueue_reliable(b, "Filipp-328-dev", "текст")
res.append(ok(r.get("ok") and r.get("id") == 72, "чужой текст в new не присваивается — идёт повтор"))
# бридж без get_pending (старый мок) → verify тихо пропущен, работает повтор
class NoPendingBridge:
    def __init__(s): s.n = 0
    def enqueue_task(s, frm, txt, lane=None):
        s.n += 1
        return {"ok": False, "error": "x"} if s.n == 1 else {"ok": True, "id": 73}
r = DB._enqueue_reliable(NoPendingBridge(), "Filipp-328-dev", "текст")
res.append(ok(r.get("ok") and r.get("id") == 73, "нет get_pending у моста → fail-safe, повтор работает"))

# (г) e2e: первый enqueue упал, verify нашёл → Филипп видит ✅ (кейс инцидента: «не удалось» больше нет)
print("(г) e2e постановка из 328:")
b = FlakyBridge([{"ok": False, "error": "unauthorized"}],
                pending_items=[{"id": 138, "from": DB.QUEUE_FROM_DEV, "task_text": "прогони гейт"}])
card = DB._try_enqueue("тз: прогони гейт", b)   # «гейт» = vps-keyword, слой 2 не зовётся
res.append(ok(card.startswith("✅") and "138" in card,
              f"кейс 138: вместо «Не удалось…» — честная ✅ с id ({card[:60]!r})"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
