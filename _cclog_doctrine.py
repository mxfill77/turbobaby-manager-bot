"""DONE в cc_log (доктрина подтверждений в CLAUDE.md + KB_RULES) + пульс — ОДНА операция.
Новая запись ПОД врезкой (после её закрывающей ═-only строки). Пишем ТОЛЬКО если read ok."""
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
lines = old.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    print("Врезка (═-only строка) НЕ найдена — НЕ пишу, чтобы не потерять шапку.")
    raise SystemExit(1)

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
"DONE " + ts + " UTC (тз:328, headless): ДОКТРИНА ПОДТВЕРЖДЕНИЙ дописана в CLAUDE.md + KB_RULES.\n"
"Суть: кнопка/ask имеет смысл ТОЛЬКО там, где владелец добавляет информацию, которой нет у машины — "
"бизнес-решения (тот ли клиент/сумма/байк, запись в Лист1/CRM, деньги, деструктив). Техническую "
"корректность проверяют тесты+гейт, а не человеческое «да» — подтверждения на технику "
"(restart/push/тесты/конфиг) не создавать. + критерий при сомнении: «что владелец проверит своим да?».\n"
"КУДА: CLAUDE.md → подраздел «ДОКТРИНА ПОДТВЕРЖДЕНИЙ (02.07.2026)» внутри «ПОЛИТИКА ПОДТВЕРЖДЕНИЙ — "
"РЕДАКЦИЯ Б»; KB_RULES (name=rules) → новый раздел 8 в конце (13168→14279 симв, write ok, хвост сверен).\n"
"Бэкап: CLAUDE.md.bak-confirm-doctrine-20260702 + commit ea92795 (только CLAUDE.md, docs — push не гнал: "
"чисто документационная правка, уйдёт со следующим push). Статус: технически готово = функционально "
"готово (правка текста, кода не касалась). ХВОСТЫ: прежние без изменений.\n"
)

new_lines = lines[: sep + 1] + [entry] + lines[sep + 1 :]
new = "\n".join(new_lines)

w = c.write_doc(text=new, name="cc_log")
print("CC_LOG WRITE:", w.get("ok"), "| old_len:", len(old), "new_len:", len(new))
if not w.get("ok"):
    print("cc_log write FAIL — пульс НЕ обновляю (не расходиться с правдой):", w)
    raise SystemExit(1)

pulse = (ts + " | 🟢 | доктрина подтверждений дописана в CLAUDE.md (подраздел в «Политике подтверждений») "
"и KB_RULES §8; commit ea92795 | ничего не жду | детали→cc_log запись «ДОКТРИНА ПОДТВЕРЖДЕНИЙ " + ts + "»")
p = c.write_doc(text=pulse, name="pulse")
print("PULSE WRITE:", p.get("ok"))
