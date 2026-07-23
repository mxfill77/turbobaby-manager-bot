"""DONE в cc_log (карта листа «Календарь бронирования», read-only разведка, ТЗ из 328) + пульс —
ОДНА операция. Зелёная зона. Врезка сохраняется: вставка ПОД шапкой (после ═-only строки)."""
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

note = (
"DONE " + ts + " UTC: карта листа «Календарь бронирования» (CRM 1sL-rw0k…) — read-only разведка "
"по локальному XLSX-экспорту от 03.07 12:38 (формулы), CRM не трогал, ничего не писал.\n"
"КАРТА (диапазон A1:AA1896, реально A..J, данные со строки 5; K..AA ПУСТЫЕ):\n"
"• Вводные дат: F1 'Даты и срок'; F2 = дата начала (сейчас 08.07.2026), F3 = дата конца (15.07.2026) "
"— ЕДИНСТВЕННЫЕ ручные вводные периода. G2 'Дней', G3 = ABS(F3-F2) (сейчас 7).\n"
"• Глобальные скидки (сезон): H1 'Глобальная скидка'; подписи H2/I2/J2 = 'Моты 1'/'Моты 2'/'Скутеры'; "
"значения H3=15%, I3=15%, J3=25% — ручные ручки владельца, зеркалятся в 'цены альт' B2/B9/B19.\n"
"• A5:A1896 = полный список байков через IMPORTRANGE('список мото' 1ZBCmVvzo…, Лист1!C3:C).\n"
"• F5 = ARRAYFORMULA FILTER: список СВОБОДНЫХ байков на период F2..F3 — из A5:A вычитаются байки, "
"у кого в 'клиенты' (со строки 122) статус 'Бронь' ИЛИ 'В аренде' с B<>'ON' и пересечение периода "
"(E<=F3 И F>=F2). Выбор байка = его строка в колонке F.\n"
"• D5/E5 = служебные ARRAYFORMULA-флаги REGEXMATCH по F (LOWER+замена 'сс'→'cc'): 'xmax 300' / 'new' "
"— различение XMAX старый/новый.\n"
"• J5 = ОДНА ARRAYFORMULA на весь столбец: каскад IF(ISNUMBER(SEARCH('<модель>', F5:F1896))) → "
"текст-квота '<модель> | дней: G3 стоимость: TEXT(цены альт!G$<row>) …, депозит: TEXT(цены альт!H$<row>) бат'. "
"J САМ ЦЕНУ НЕ СЧИТАЕТ — только распознаёт модель по подстроке и форматирует; расчёт (скидка за срок "
"по дням G3 + глобальная H3/I3/J3) живёт в 'цены альт' кол. G (кривые), депозит — кол. H.\n"
"• B и C пустые (в шаблоне J стоит C5:C1896 — даёт двойной пробел в тексте).\n"
"• Разметки занятости ПО ДАТАМ (грид/календарь) НЕТ: занятость только вычисляемая, через FILTER в F5 "
"под ОДИН период F2/F3. Хвост листа (~со строки 42) — пустые протянутые формулы D/E/J до 1896.\n"
"Согласуется 1-в-1 с QuotePrice.js (quote_price повторяет G3/F5/J/H3-I3-J3 программно). "
"Источник: _quote_crm_export.xlsx + _quote_calendar_full.csv (уже были), скрипт _qcal_map.py. Хвостов нет.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", w.get("ok"), "| old_len:", len(old), "new_len:", len(new), "| insert_at_line:", ins)

pulse = (ts + " | 🟢 | карта листа 'Календарь бронирования' снята read-only (XLSX-формулы): F2/F3=даты, "
         "G3=дни, H3/I3/J3=глоб.скидки 15/15/25, F5=FILTER свободных, J=текст-квота (цена в 'цены альт' G) "
         "| ничего не жду | детали→cc_log запись «карта Календаря " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
