"""DONE в cc_log (quote_price + склейка, ТЗ из 328) + пульс — ОДНА операция. Зелёная зона.
Врезка сохраняется: вставка ПОД шапкой (после последней ═-only строки в начале дока)."""
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
"DONE " + ts + " UTC: quote_price ГОТОВ в зеркале Bridge (ТЗ из 328, headless) — ждёт красной кнопки деплоя.\n"
"а) Новый /root/turbobaby-bridge-gs/QuotePrice.js — read-only экшен quote_price(bike, date_start, "
"date_end) → {day_price, total, deposit, available, conflicts, season, text}. НИЧЕГО не пишет (F2/F3 "
"Календаря НЕ трогает). Цены/депозиты читает ЖИВЫМИ из 'цены альт' (C=день с глоб.скидкой, H=депозит, "
"B2/B9/B19=глоб.скидки категорий = Календарь!H3/I3/J3); занятость — по 'клиенты' (Бронь ИЛИ В-аренде+"
"B<>ON, E<=end И F>=start — та же логика, что FILTER в F5 Календаря); байк резолвится resolveBikeName_ "
"(тот же резолвер, что у постановки брони в Booking.gs).\n"
"б) Разведка структуры БЕЗ владельца: лист вскрыт read-only через gviz CSV + XLSX-экспорт (формулы). "
"4 кривые «скидка за срок» перенесены 1-в-1 из колонки G 'цены альт' (XSR155 своя, мото1, мото2, "
"скутеры). СЕЗОННОСТЬ: отдельной таблицы сезонов НЕТ — сезон кодируется глоб.скидками H3/I3/J3 "
"(сейчас 15/15/25% = low). quote_price возвращает season={label: low/high, global_discount}.\n"
"в) Bridge.js: quote_price в doGet (read-only GET) + doPost + help.\n"
"г) Тест: node --check чисто; ЛОКАЛЬНЫЙ функциональный тест _quote_local_test.js — 27/27 PASS, "
"эталон = живые значения J-колонки Календаря 03.07 (7 дней: NMAX 2217/317, CBR650R 9519/1360, "
"ADV350 4928/704, XADV750 13759/1966 и др.) + края кривых (6д/20д/>30д) + доступность + форматы дат.\n"
"д) curl-тест на dev-деплое НЕ прогнан: clasp push = красное + авторизация clasp ПРОТУХЛА "
"(invalid_grant/invalid_rapt — нужен интерактивный clasp login из Termux). Честный статус: технически "
"готово + функционально сверено с листом ЛОКАЛЬНО; на живом Bridge не проверено.\n"
"е) В деплой-дельту входит давно ждущая СКЛЕЙКА СТАТУСОВ (BotData.js getPending_ CSV, хвост фикса "
"заморозки 02.07, commit 3978a91) — два изменения, ОДИН redeploy, одна кнопка.\n"
"Бэкапы: зеркало ДО правок = _bridge_bak-quoteprice-20260703/ (в репо бота); прод не тронут. "
"Откат после деплоя = clasp redeploy прошлой версии.\n"
"ХВОСТЫ: 1) владелец: clasp login → clasp push → clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNe"
"CcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw (карточка в 328); 2) после деплоя: ping + quote_price "
"(read-only) + get_pending CSV-проба — сверить, что devbot перестал фоллбэчить по-статусно; "
"3) обёртка quote_price() в bridge_client.py — отдельной зелёной задачей после деплоя.\n"
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

pulse = (ts + " | 🟡 | quote_price собран в зеркале Bridge (QuotePrice.js + роутинг) + склейка статусов "
         "в комплекте; локальный тест 27/27 против живого листа | жду: красная кнопка деплоя в 328 "
         "(clasp login протух → login+push+redeploy руками владельца) | детали→cc_log запись "
         "«quote_price " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
