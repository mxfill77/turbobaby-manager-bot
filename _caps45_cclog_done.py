"""DONE в cc_log (ПОД врезкой) + KB_PULSE той же операцией. Зелёная зона."""
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
with open("/tmp/cc_log_backup_caps45done_20260705.txt", "w", encoding="utf-8") as f:
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
"DONE " + ts + ": [капы — доделка без рук владельца, тз 328] commit 477ae4c, push d1edd28..477ae4c (гейт 37 зелёных). "
"(1) KB: раздел «Правила цен v2»+памятка 12 моделей+«нет в парке»+правило «менеджеры без Bot Data» были в git с d1edd28; "
"добавлено уточнение п.3 «J-текст дословно КРОМЕ кап-случая»; Brain synced write_doc(name=knowledge_base), delta 0 (48816). "
"(2) Зеркало Bridge: QuotePrice.js — setCaps (блок «Модель|Кап ฿/мес|Активен» K3:M15 Календаря целиком: валидация, "
"обновление НА МЕСТЕ найденной шапки K..T, дочистка хвоста; confirmed-гейт как у записи в Лист1) и toggleCap (Активен "
"одной модели, тот же гейт); Bridge.js — роутинг + оба в REDZONE_LOCK; quote_price/cap-поля не тронуты; node --check ОК; "
"бэкапы QuotePrice.js.bak-setcaps-20260705, Bridge.js.bak-setcaps-20260705. "
"(3) tests/test_set_caps.py — 11 тестов-зеркал (в гейте), round-trip set→read, дрейф-guard payload = финальная таблица. "
"СТАТУС: технически готово (зеркало+тесты); функционально НЕ в проде — clasp из headless блокирован (известный лимит). "
"РУКАМИ ИЗ TERMUX (clasp pull НЕ делать — затрёт капы): "
"cd /root/turbobaby-bridge-gs && clasp push, затем "
"clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw. "
"ПОСЛЕ «деплой сделан»: (а) вызвать set_caps с финальной таблицей 12 моделей (payload = SET_CAPS_PAYLOAD из "
"tests/test_set_caps.py; запись в живой Календарь = красное, отдельная карточка «да»); (б) живой quote_price NMAX на "
"30 дней — показать cap_price/cap_active и текст оффера; (в) обновить пульс. "
"ХВОСТЫ: деплой руками за Филиппом · боевой set_caps+quote_price после деплоя · логика подмены цены на userbot — отдельно."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟡 | тз 328 «капы-доделка» собрано: set_caps/toggle_cap в зеркале Bridge + 11 тестов (гейт 37 зелёных, "
"commit 477ae4c, push ок), KB уточнена и синкнута (delta 0) | жду от Филиппа деплой руками из Termux: "
"cd /root/turbobaby-bridge-gs && clasp push && clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw "
"(clasp pull НЕ делать), после «деплой сделан» → боевой set_caps (красная карточка) + живой quote_price NMAX | "
"детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
