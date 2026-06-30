"""Карточка байка: блок остатка до след. ТО по видам (next − текущий пробег). Чистый рендер msg_bike_card."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# (1) _svc_remaining — единичные случаи (граничные включительно)
print("(1) _svc_remaining:")
res.append(ok(S._svc_remaining(42823, "37823") == (" (อีก 5000 กม.)", " (ещё 5000 км)"), ">0 → ещё N км"))
res.append(ok(S._svc_remaining(38000, "38000") == (" (⚠️ ครบกำหนดแล้ว)", " (⚠️ пора сейчас)"), "==0 → пора сейчас (граница)"))
res.append(ok(S._svc_remaining(44000, "45000") == (" (⚠️ เกิน 1000 กม.)", " (⚠️ просрочено на 1000 км)"), "<0 → просрочено на N км"))
res.append(ok(S._svc_remaining(None, "100") is None and S._svc_remaining(4000, "") is None, "нет next/пробега → None (не выдумываем)"))
res.append(ok(S._svc_remaining(4000, "1 200") == (" (อีก 2800 กม.)", " (ещё 2800 км)"), "пробег с пробелом парсится"))

# (2) карточка: oil в норме → остаток; gear просрочен; abs нет данных; airfilter ровно 0
oil = {"km": "37823", "next": 42823, "status": "ok"}
cols = [
    {"kind": "gear", "next": 37000, "status": "ok", "km": 37823},      # 37000-37823 = -823 → просрочено
    {"kind": "abs", "next": None, "status": None, "km": 37823},        # нет данных
    {"kind": "airfilter", "next": 37823, "status": "ok", "km": 37823}, # ровно 0 → пора сейчас
]
m = S.msg_bike_card("NMAX 155 4255", "37823", oil, cols, None)
print("\n(2) карточка с остатками (RU):")
res.append(ok("ТО Oil: в норме, следующее 42823 км (ещё 5000 км)" in m, "масло: остаток «ещё 5000 км»"))
res.append(ok("редуктор (gear): следующее 37000 км (⚠️ просрочено на 823 км)" in m, "gear: «⚠️ просрочено на 823 км»"))
res.append(ok("ABS: нет данных" in m, "abs без next → «нет данных»"))
res.append(ok("возд. фильтр: следующее 37823 км (⚠️ пора сейчас)" in m, "airfilter ровно 0 → «пора сейчас»"))

print("(2) карточка TH-блок без кириллицы:")
th_block = m[m.index("🇹🇭"):m.index("🇷🇺")] if "🇹🇭" in m and "🇷🇺" in m else ""
res.append(ok("อีก" in m and "เกิน" in m, "TH суффиксы (อีก/เกิน) присутствуют"))
res.append(ok(not re.search(r"[А-Яа-яЁё]", th_block), "в 🇹🇭-блоке остатка НЕТ кириллицы (двуязычность цела)"))

# (3) регресс: старый ассерт карточки (подстроки целы после добавления остатка)
m2 = S.msg_bike_card("NINJA 400 6334", "37823", {"km": "37823", "next": 42823, "status": "ok"},
                     [{"kind": "gear", "next": 44000, "status": "ok", "km": 40000}],
                     {"state": "В аренде", "client": "Jack"})
print("(3) регресс старых подстрок:")
res.append(ok("ТО Oil: в норме, следующее 42823" in m2 and "редуктор (gear): следующее 44000" in m2, "старые подстроки целы (тест_card не сломан)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
