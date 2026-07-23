"""cc_log DONE (сверка KB_faq vs docs/turbobaby_faq_v1.md, задача 328) + KB_PULSE — ОДНОЙ операцией.
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
"DONE " + ts + " UTC (headless, задача 328: сверка FAQ Brain↔файл): СОВПАДАЕТ, обновление НЕ потребовалось.\n"
"— read_doc name=faq (KB_faq) vs docs/turbobaby_faq_v1.md: ИДЕНТИЧНЫ посимвольно (7665 code points оба; "
"12406 у файла — это байты UTF-8, не расхождение). Заголовок совпадает («# TurboBaby — FAQ и шаблоны ответов (v1)»), "
"полный прайс на месте в обоих (раздел «Точный прайс (из CRM…)», 10 моделей PCX150…XADV750 + депозиты).\n"
"— write_doc name=faq НЕ делал (delta 0); CLAUDE.md НЕ правил: правило синка FAQ уже вписано 03.07 "
"(commit 0775893, раздел «Каналы мозга»: канон = KB_faq, docs-файл = зеркало, направление обратное остальной базе) — "
"дубль не плодим. Read-only, прод не трогал.\n"
"СТАТУС: функционально подтверждено (живой read_doc + посимвольное сравнение). ХВОСТЫ: прежние без изменений "
"(функц. тест suggest.py с userbot-стороны).\n"
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

pulse = (ts + " | 🟢 | сверка FAQ (задача 328): KB_faq == docs/turbobaby_faq_v1.md посимвольно (7665), "
         "прайс и заголовок на месте — обновление и правка CLAUDE.md не нужны (правило синка уже есть, 0775893) | "
         "ничего не жду | детали→cc_log DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
