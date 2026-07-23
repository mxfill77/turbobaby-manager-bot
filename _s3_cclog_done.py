"""cc_log DONE (шаг 3/7 родитель 33: сверка сводов + list_brain) + KB_PULSE — ОДНОЙ операцией.
Запись ПОД врезкой (матч ═-only строки), write только если read ok. Зона 🟢."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
"DONE " + ts + " UTC (тз:328, headless, шаг 3/7 родитель 33): сверка KB_RULES/KB_INFRA с KB_MASTER после ступени 2 + list_brain.\n"
"— KB_RULES поправлен ТОЧЕЧНО (write_doc name=rules, бэкап _s3_rules.bak-20260703, 14279→15192): "
"(1) разд.1 маршрутизация — добавлен блок «ОБНОВЛЕНИЕ 03.07.2026»: тема 328 принимает «тз: <ТЗ>» (headless-CC) и "
"«декомпозируй: <крупное ТЗ>» (шаги [i/N родитель id], halt-on-fail), ограничение «recon только Termux» снято, "
"restart splinter headless-CC делает сам оранжевым циклом; (2) строка «КРАСНЫЕ ПОДТВЕРЖДЕНИЯ» приведена к доктрине "
"разд.8 (git push/restart — НЕ красное; красное = clasp/таблицы/деньги/удаление); (3) разд.5: несуществующий "
"KB_ROADMAP_v2 → KB_ROADMAP_MASTER (ключ roadmap_master, по KB_MASTER разд.5). Контрольное чтение ✅.\n"
"— KB_INFRA: противоречий со ступенью 2 НЕТ (свод про таблицы/формулы, маршрутизации/подтверждений не касается) — без правок.\n"
"— list_brain: 24 ключа манифеста, ДУБЛЕЙ ключей НЕТ, все id уникальны. Сверка с реальной папкой Brain (Drive):\n"
"  ORPHAN-ФАЙЛЫ В ПАПКЕ БЕЗ КЛЮЧА МАНИФЕСТА (НЕ удалял, только список): "
"1) KB_claude_code_log_archive_OLD (Google Doc 367КБ, id 19hO_c8FRDZY2t_KhgmlPiTSg-CvocQIvLGVa894OBfY — остаток "
"миграции Doc→plain 02.07, кандидат в _archive/удаление по «да»); "
"2) KB_ROADMAP_v2 (plain 15КБ, id 1ekCOwspbXhJP7F2eVr3tKuwdLJ9ke9IH, лежит в КОРНЕ Brain, менялся 28.06 — "
"KB_MASTER разд.5 считает имя несуществующим, а файл жив и НЕ в архиве: расхождение, решить на ревизии); "
"3) KB_NORTH_STAR (plain 4.9КБ, id 1D7JphAt8dfOLXIJBV_pZWTUcOgjau5FR — живой док, KB_MASTER на него ссылается, "
"но ключа в манифесте НЕТ — кандидат на регистрацию, не мёртвый).\n"
"  КЛЮЧИ МАНИФЕСТА ВНЕ КОРНЯ ПАПКИ: payments_plan (13WtxQaDLdixR4EsjUFimtNhESn9nFDtk) — лежит в Brain/_archive, "
"через Bridge читается (ок, статус ОТЛОЖЕНО); roadmap_master (1Z70EpgGZmaYMaZ064sXQlCCP8z8sFyZWfzVPvRB4jWE) — "
"через Bridge ЧИТАЕТСЯ (len 12589), но Drive-поиск по названию его НЕ находит (вероятно корзина или вне My Drive) — "
"ПРОВЕРИТЬ НА РЕВИЗИИ, не трогал.\n"
"СТАТУС: технически готово (правки записаны и перечитаны); функционально — штабу перечитать KB_RULES разд.1 при "
"следующей маршрутизации.\n"
"ХВОСТЫ (на ревизию, всё — НЕ удалять без «да»): судьба KB_ROADMAP_v2-файла в корне; archive_OLD в _archive/удаление; "
"регистрация KB_NORTH_STAR ключом; статус roadmap_master (корзина?); заметка вне моей задачи — KB_MASTER разд.2 "
"маршрутизация и разд.6 чек-лист [4] сами ещё несут доступень-2 формулировки (recon→только Termux; KB_ROADMAP_v2).\n"
)

lines = old.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:10]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
new = "".join(lines[:ins]) + entry + "\n" + "".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| вставка после строки", ins, "| old:", len(old), "new:", len(new))

pulse = (ts + " | 🟢 | шаг 3/7 (родитель 33): KB_RULES синхронизирован со ступенью 2 (маршрутизация 328 «тз:»/"
         "«декомпозируй:», доктрина git push/restart, роадмап-ссылка), KB_INFRA чист, list_brain: дублей нет, "
         "3 orphan-файла выписаны в cc_log | ничего не жду | детали→cc_log DONE " + ts + " шаг 3/7")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
