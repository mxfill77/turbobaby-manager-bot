"""DONE в cc_log (ПОД врезкой, матч ═-only строки) + KB_PULSE той же операцией. Зелёная зона.
Защита: пишем ТОЛЬКО если read ok; врезку сохраняем."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import re

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)

old = r.get("text", "")
# бэкап-снимок на диск перед правкой
with open("/tmp/cc_log_backup_triple_20260702.txt", "w", encoding="utf-8") as f:
    f.write(old)

lines = old.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    print("ВРЕЗКА НЕ НАЙДЕНА — НЕ пишу")
    raise SystemExit(1)

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
"DONE " + ts + ": ТРОЙНАЯ ПРОВЕРКА (headless «тз:» из 328, read-only). "
"1) СВЕЖЕСТЬ МОЗГА: pulse 21:26 UTC (лаг ~6 мин, 🟢) · cc_log верхний DONE 21:26 (лаг ~6 мин, 🟢) · "
"KB_MASTER упоминает решение 03.07 (обновлён <1 сут, якорь ревизии 11.07). "
"АНОМАЛИЯ: в cc_log запись «PLAN 2026-07-02 21:45 ждёт ревью» лежит НИЖЕ DONE 21:26 и была в будущем "
"относительно 21:32 — похоже, ошибочная дата/время старой записи (вероятно 01.07 21:45), поправить при подрезке. "
"2) SPLINTER.LOG 24ч: 69 записей (33 ERROR / 36 WARN), всплески 14ч и 19–20ч UTC. Паттерны: "
"12x Bridge timeout get_pending + 18x apscheduler skip devbot_report (job 45s не успевает из-за таймаутов Bridge — связка) · "
"~13x Bridge 404/500 (флап Apps Script echo-redirect) · 4x O3 флуд-контроль RetryAfter + 4x q.answer протух (обработано штатно) · "
"2x НЕОБРАБОТАННЫЕ исключения: q.answer() БЕЗ try/except в splinter.py:712 (handle_info_button) и :3748/:3773 (handle_o3_button) — "
"фикс 749cf46 покрыл не все точки. РЕКОМЕНДАЦИИ: (а) обернуть эти q.answer() как в фиксе 749cf46; (б) зарегистрировать "
"глобальный error handler в Application; (в) get_pending — поднять interval devbot_report 45s→90s или таймаут-бюджет; красное не трогал. "
"3) ПРОСРОЧКИ ПАРКА (прод-скан _o3_overdue_scan, 28 байков с просрочками). ТОП-5: "
"3503 CB650R (масло +5074 км! ABS не делалось +29374, фильтр +19374) · "
"4505 CBR650R (фильтр не делался +44768, ABS +23768) · "
"4253 NMAX (4 вида сразу: ABS +30136, фильтр +20136, масло/редуктор +336) · "
"8950 FORZA (ABS +20225, фильтр +10225, редуктор +825) · "
"6334 NINJA400 (ABS +12974, фильтр +17974). "
"ПЕРВЫМ НА ТО: 3503 CB650R — единственный с острой просрочкой МАСЛА (+5074 км на 650cc = риск дорогого ремонта двигателя, "
"масло деградирует быстрее всего), одним заездом закрыть ABS+фильтр. Близкий №2 — 4505 CBR650R (тормоза/фильтр, но масло у него в норме). "
"ХВОСТЫ: 3 точки q.answer без try/except; аномальная дата PLAN-записи; 28 байков в просрочке — board /o3board."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟢 | тройная read-only проверка выполнена (свежесть мозга 🟢 лаги ≤6мин; лог 24ч: 69 W/E, "
"2 необработанных q.answer + таймауты get_pending; ТО первым — 3503 CB650R, масло +5074) | ничего не жду | "
"детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))

# даты в cc_log — нужна ли подрезка (старше текущих суток)
dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", new)))
print("даты в cc_log:", dates[:3], "...", dates[-3:] if len(dates) > 3 else "")
