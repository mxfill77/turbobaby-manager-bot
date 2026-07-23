"""cc_log DONE (FAQ-линк + гигиена settings) + KB_PULSE — ОДНОЙ операцией.
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
"DONE " + ts + " UTC (headless, 2 хвоста перед клиентской обкаткой): FAQ-линк + гигиена settings.\n"
"— ЧАСТЬ 1 FAQ-линк: list_brain — KB_faq (id 1tv8Y…qs98) был зарегистрирован ТОЛЬКО под ключом `faq`, "
"ключа turbobaby_faq НЕ было → зарегистрирован register_brain_doc(turbobaby_faq → тот же id), манифест: 24 ключа. "
"Проверка: read_doc name=turbobaby_faq ok, вернул KB_faq (7665 символов, «TurboBaby — FAQ и шаблоны ответов v1»). "
"Свежесть: KB_faq и docs/turbobaby_faq_v1.md ПОБАЙТОВО ИДЕНТИЧНЫ (7665 code points; 12406 — это байты UTF-8) — "
"домерж НЕ потребовался, delta 0, write_doc в KB_faq не делал (снимок снят в /tmp/kb_faq_snapshot.md). "
"Правило в CLAUDE.md (раздел «Каналы мозга», commit 0775893): для FAQ канон = KB_faq (Brain), правки через "
"write_doc, VPS docs/turbobaby_faq_v1.md = зеркало (ре-синк ИЗ KB_faq) — направление обратное остальной базе.\n"
"— ЧАСТЬ 2 гигиена: .claude/settings.json (после cp владельца из Termux, сверен с _sdrun_new_settings.json — "
"идентичен: ровно 2 узких allow-паттерна systemd-run --on-active=* systemctl restart orchestrator-daemon|splinter) "
"закоммичен (commit 03c3b58); _sdrun_new_settings.json удалён (применён). "
"Гейт 33 теста зелёные (10.0с) → git push ok: 51c196d..03c3b58 main (0775893 + 03c3b58).\n"
"СТАТУС: регистрация ключа + read_doc(turbobaby_faq) — функционально подтверждено (живой вызов); "
"push — подтверждён (ahead=0 по факту push); чтение suggest.py userbot'ом — ждёт функционального теста с его стороны.\n"
"ХВОСТЫ: функциональный тест suggest.py (read_doc name=turbobaby_faq с userbot-стороны); "
"прежние хвосты родителя 33 без изменений.\n"
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

pulse = (ts + " | 🟢 | FAQ-линк готов: ключ turbobaby_faq → KB_faq зарегистрирован, read_doc ok, KB_faq==VPS-файл "
         "(delta 0, домерж не нужен), правило «канон=KB_faq» в CLAUDE.md; settings.json (2 узких systemd-run) "
         "закоммичен, _sdrun удалён, гейт 33✅ → push 03c3b58 | ничего не жду; хвост — функц. тест suggest.py | "
         "детали→cc_log DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
