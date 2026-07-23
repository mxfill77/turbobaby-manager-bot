"""DONE в cc_log (ПОД врезкой, матч ═-only строки) + KB_PULSE той же операцией. Зелёная зона.
Защита: пишем ТОЛЬКО если read ok; врезку сохраняем; бэкап-снимок на диск."""
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
with open("/tmp/cc_log_backup_caps_20260705.txt", "w", encoding="utf-8") as f:
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
"DONE " + ts + ": капы-акции low season + правила цен v2 (headless «тз:» из 328), commit d1edd28, push прошёл (гейт 36/36). "
"СДЕЛАНО: 1) зеркало Bridge /root/turbobaby-bridge-gs/QuotePrice.js (бэкап .bak-caps-20260705): читает блок капов "
"«Календаря бронирования» (шапка «Модель|Кап ฿/мес|Активен» ищется по ячейке «Модель» в строке 3, колонки K..T; "
"12 строк данных до первой пустой), в ответ quote_price добавлены cap_price/cap_active; резолв: cap-ключ на каждой "
"строке QUOTE_MODELS (CB650R и CBR650R делят кап 18900; REBEL/XSR900/R7/PCX/ADV150-160/CLICK — без капа); блока "
"нет/не читается → null/false, quote_price не падает (обратная совместимость). Подмену цены НЕ делаю — она на userbot. "
"node --check чист. 2) 11 тестов tests/test_quote_caps.py (зеркало парсинга/резолва + node --check + дрейф-guard "
"cap-ключей из реального JS + passthrough обёртки bridge_client + старый Bridge без полей) — в гейте. "
"3) KB_knowledge_base: раздел «Правила цен v2» (сезоны high=1ноя–15мая/low=16мая–31окт; H3/I3/J3 крутит владелец, "
"бот читает; цена клиенту = J-текст дословно; кап-триггер «от <кап> ฿/мес — предложение низкого сезона» при "
"кап-активен И J-цена за срок > капа; мин-сроки скутеры 5дн/мото 3дн/XSR155 5дн + ответ «сдаём от N дней» с ценой "
"на минимум; несколько байков = раздельные цены одним сообщением; депозит при нескольких байках — только менеджер "
"и только если клиент сам спросил); Сезонная памятка = капы (XSR155 7490, CB650/CBR650 18900, Vulcan 18900, "
"+XADV750 33900); пометки «нет в парке» у PCX150/160, ADV150/160, REBEL300, XSR900, R7 (не удалены); ручное правило "
"«менеджеры НЕ имеют доступа к Bot Data — рычаги только в CRM». Brain synced (delta 0). "
"НЕ СДЕЛАНО (красное/лимит, карточка в 328): (а) заполнение блока капов в живом «Календаре бронирования» — 12 строк, "
"шапка в K3:M3 («Модель | Кап ฿/мес | Активен»), данные K4:M15 — красная зона (живая таблица CRM), нужно «да»+руки; "
"(б) clasp push + clasp redeploy прод-Bridge — clasp из headless блокирован, команды в карточке для Termux. "
"ПОРЯДОК ВЫКАТА: сначала блок в Календарь, потом redeploy (код без блока безопасен: null/false). "
"СТАТУС: технически готово (тесты+гейт); функционально НЕ подтверждено (прод-Bridge старый, блока в Календаре нет). "
"ХВОСТЫ: заполнить Календарь (карточка) · clasp push/redeploy из Termux (карточка) · логика подмены цены на userbot — отдельная задача."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟡 | капы low season: зеркало QuotePrice.js + cap_price/cap_active + 11 тестов + KB «Правила цен v2» "
"готовы, commit d1edd28 запушен, Brain synced | жду от Филиппа: заполнить блок капов K3:M15 Календаря (красное) и "
"clasp push+redeploy из Termux (карточка в 328) | детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
