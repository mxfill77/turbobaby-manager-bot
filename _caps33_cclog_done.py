"""DONE в cc_log (ПОД врезкой, матч ═-only строки) + KB_PULSE той же операцией. Зелёная зона.
Конверт заявки 33 (капы low season): проверка состояния — шаги ручные, не выполнены."""
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
with open("/tmp/cc_log_backup_caps33_20260705.txt", "w", encoding="utf-8") as f:
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
"DONE " + ts + ": [конверт заявки 33 = одобрение заявки 31, капы low season] Проверка состояния вместо исполнения: "
"ОБА шага заявки — физически РУЧНЫЕ (шаг 1 = заполнить блок капов K3:M15 в живом «Календаре бронирования» руками; "
"шаг 2 = clasp push + clasp redeploy из Termux — clasp из headless блокирован, одобрение заявки гейт НЕ обходит). "
"Кнопка «да» их НЕ исполняет — конверт вернулся в headless, который исполнить их не может (петля 31→33). "
"ФАКТ-ПРОВЕРКА (read-only): quote_price по NMAX 4957 на 10.07–10.08 → day_price=219, total=6791, season=low, "
"cap-ключей в ответе НЕТ = прод-Bridge СТАРЫЙ, шаг 2 не выполнен (шаг 1 через старый Bridge не виден, но без шага 2 "
"неважен). Зеркало готово: /root/turbobaby-bridge-gs/QuotePrice.js с капами на месте, бэкап QuotePrice.js.bak-caps-20260705 есть. "
"НОВУЮ карточку NEEDS_APPROVAL НЕ выдаю — она лишь продолжит петлю; исполнение только руками Филиппа: "
"(1) Календарь бронирования: K3=«Модель» L3=«Кап ฿/мес» M3=«Активен», K4:M15 = NMAX|5000|да · XMAX OLD|8900|да · "
"XMAX NEW|9900|да · ADV350|10900|да · Forza300|7900|да · XSR155|7490|да · CB300R|9900|да · MT-03|10990|да · "
"Ninja400|11900|да · CB650R/CBR650R|18900|да · Vulcan|18900|да · XADV750|33900|да; "
"(2) Termux: cd /root/turbobaby-bridge-gs && clasp push, затем clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw "
"(clasp pull ПЕРЕД push НЕ делать — затрёт QuotePrice.js). "
"ПРОВЕРКА ПОСЛЕ: quote_price bike=4957 должен вернуть cap_price=5000, cap_active=true. "
"СТАТУС: read-only проверка выполнена; функционально капы НЕ в проде. "
"ХВОСТЫ: ручные шаги 1+2 за Филиппом · после деплоя прогнать контрольный quote_price · логика подмены цены на userbot — отдельная задача."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟡 | конверт заявки 33 (капы): проверил прод — Bridge старый, cap-ключей нет; оба шага ручные, "
"кнопка «да» их не исполняет, новую карточку не плодил (петля) | жду от Филиппа РУКАМИ: блок капов K3:M15 Календаря + "
"clasp push/redeploy из Termux (команды в cc_log) | детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
