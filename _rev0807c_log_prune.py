#!/usr/bin/env python3
"""Финал ревизии 08.07 вечер: подрезка cc_log (гигиена, >40КБ + конец сессии; записи старше 2026-07-08 →
архив, АРХИВ ПИШЕТСЯ ПЕРВЫМ + сверка образца) → cc_log с RESULT-записью сверху ПОД врезкой → пульс
ТОЙ ЖЕ операцией. Зелёная зона (Brain-журналы)."""
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

TODAY = "2026-07-08"
MARK = re.compile(r"^(DONE|PLAN|NOTE|WAITING|BLOCKED|SKIPPED)\s+(\d{4}-\d{2}-\d{2})")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

RESULT = (
    f"DONE {NOW} UTC (headless 328): RESULT ревизия «08.07 вечер: O3-3c + UX-сага» (дополнение к 11:56). "
    "KB_MASTER обновлён (56274→60840 cp, post-write verify MATCH, 12/12 маркеров, снимок "
    "/tmp/KB_MASTER_snapshot_20260708c.md): §3 блок ⭐08.07 дописан — O3-3c три части (30b7e65 карточка "
    "ПРИЁМА raw-депозит col S «💰 Верни депозит» / 70a894c col N booking_id + Money-привязка "
    "intake-окно+байк, ленивая само-миграция шапки N1 / деплой Bridge @69→@72 + смок ТОЛЬКО ЧТЕНИЕ: "
    "deposit_raw row700='15000' ✅, TX_HEADERS N14='booking_id' ✅) + фикс декомпозера dd4a4e7 (red-слова "
    "родителя не валят план, «🔴 красные шаги: i,j» в карточке — урок 166, гейт 75/75) + UX-сага целиком "
    "(de36412 роль-развод + notify-hook; cp-сплиты ПРИМЕНЕНЫ владельцем байт-в-байт 13:09; fcff713 "
    "env-дубли в local-allow; bd5d516 страж: команда в теле ambiguous-карточки, дедуп ×N) + тест-строка "
    "1268 прибрана по содержимому; заголовок блока → «O3 ЗАВЕРШЁН ЦЕЛИКОМ (куски 1–3 + 3c)». "
    "§4: O3-3c ЗАМКНУТ — операционный контур O3 полный (бронь→выдача→приём→депозит), Bridge @72, UX-сага "
    "закрыта; горизонты: дожим экзамена 6/6 + доработка 2.1, живые обкатки ВЫДАЧА/ПРИЁМ/Money-привязка на "
    "реальных событиях, микрохвосты (guard --version, git commit -m матч, «(повтор)», gate-алерты финал). "
    "§7 сведён: хвост обкаток расширен на Money-привязку, [ЧИСТКА 1268 ✅ ЗАКРЫТА], новый хвост "
    "«МИКРОФИКСЫ СТРАЖА pretool_guard». registry_check ✅ СХОДИТСЯ (4 проверки, 0 расхождений, HEAD "
    "dd4a4e7). cc_log подрезан: 07.07 и старше → архив (архив записан ПЕРВЫМ, образец сверен). "
    "Хвостов новых сверх §7 нет."
)

PULSE = (f"{NOW} | 🟢 | Ревизия 08.07 вечер: KB_MASTER §3/§4/§7 дописаны — O3-3c ЗАМКНУТ, операционный "
         "контур O3 полный (бронь→выдача→приём→депозит, Bridge @72), UX-сага применена, 1268 прибрана; "
         "registry ✅ 4/4; cc_log подрезан | ничего не жду | детали→cc_log запись «ревизия 08.07 вечер»")

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — стоп:", r)
    raise SystemExit(1)
text = r.get("text", "")

with open("/tmp/cc_log_backup_prune_0807c.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("BACKUP /tmp/cc_log_backup_prune_0807c.txt:", len(text), "chars")

lines = text.split("\n")
hdr_end = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        hdr_end = i + 1
if hdr_end == 0:
    print("ВРЕЗКА НЕ НАЙДЕНА — стоп, ничего не пишу")
    raise SystemExit(1)
header = lines[:hdr_end]
body = lines[hdr_end:]

blocks, cur = [], []
for ln in body:
    if MARK.match(ln):
        if cur:
            blocks.append(cur)
        cur = [ln]
    else:
        cur.append(ln)
if cur:
    blocks.append(cur)

keep, old = [], []
for b in blocks:
    m = MARK.match(b[0])
    if m and m.group(2) < TODAY:
        old.append(b)
    else:
        keep.append(b)
print("blocks: keep(сегодня/шапочные)=%d old=%d" % (len(keep), len(old)))

if old:
    old_text = "\n".join("\n".join(b) for b in old).strip("\n")
    ra = c._call("read_doc", name="cc_log_archive")
    if not ra.get("ok"):
        print("READ архива FAIL — НЕ подрезаю:", ra)
        raise SystemExit(1)
    arch_old = ra.get("text", "")
    arch_new = old_text + "\n\n" + arch_old
    wa = c.write_doc(text=arch_new, name="cc_log_archive")
    print("WRITE archive:", wa.get("ok"), "| arch_len:", len(arch_old), "→", len(arch_new))
    if not wa.get("ok"):
        print("АРХИВ НЕ ЗАПИСАН — cc_log НЕ трогаю.")
        raise SystemExit(1)
    probe = old[-1][0][:80]
    ra2 = c._call("read_doc", name="cc_log_archive")
    if not (ra2.get("ok") and probe in ra2.get("text", "")):
        print("СВЕРКА АРХИВА ПРОВАЛЕНА — cc_log НЕ трогаю. probe:", probe)
        raise SystemExit(1)
    print("Сверка архива ok (образец найден):", probe[:60])

kept_text = "\n".join("\n".join(b) for b in keep).strip("\n")
new_cc = "\n".join(header) + "\n\n" + RESULT + "\n\n" + kept_text + "\n"
w = c.write_doc(text=new_cc, name="cc_log")
print("WRITE cc_log:", w.get("ok"), "| len:", len(text), "→", len(new_cc))
if not w.get("ok"):
    print("cc_log НЕ записан — пульс не трогаю (расходиться нельзя)")
    raise SystemExit(1)

r2 = c._call("read_doc", name="cc_log")
ok2 = r2.get("ok") and "RESULT ревизия «08.07 вечер: O3-3c + UX-сага»" in r2.get("text", "")
print("verify cc_log (RESULT сверху):", "OK" if ok2 else "FAIL")

wp = c.write_doc(text=PULSE, name="pulse")
print("WRITE pulse:", wp.get("ok"))
if not (ok2 and wp.get("ok")):
    raise SystemExit(1)
print("ФИНАЛ OK: cc_log подрезан + RESULT, пульс обновлён той же операцией")
