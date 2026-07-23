#!/usr/bin/env python3
"""Мини-ревизия 08.07 «O3 куски 1-2»: точечные правки KB_MASTER (§3 блок ⭐08.07, §4 O3-статус,
§7 хвосты) + write_doc + post-write verify (read back, сверка длины code points).
Живой док ведём через write_doc(id) — зона зелёная по CLAUDE.md (гигиена мозга)."""
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"
SNAP = "/tmp/KB_MASTER_snapshot_20260708.md"

with open(SNAP, encoding="utf-8") as f:
    text = f.read()
orig_len = len(text)

edits = []


def edit(anchor, replacement, label):
    edits.append((anchor, replacement, label))


# --- §3: новый блок ⭐08.07 между итогом ⭐07.07-позднего-вечера и «СРЕДА "РУЛЮ С ТЕЛЕФОНА"» ---
A1 = ("  пультом 328; мета-дирижёр (самопочинка + адаптация) действует на обеих полосах.\n"
      "\nСРЕДА «РУЛЮ С ТЕЛЕФОНА")
BLOCK_0807 = """  пультом 328; мета-дирижёр (самопочинка + адаптация) действует на обеих полосах.

- ⭐ 08.07 — O3 КУСКИ 1–2 СОБРАНЫ (бронь: кнопка → CRM/Booking.js → мост в группу) + ФИКС КОРНЯ СИРОТ O4:
  • ФИКС КОРНЯ ПОВТОРНЫХ СИРОТ 138/146 (0501f42, гейт 66 зелёных): claim-verify в process_new — после
    клиентского сбоя claim (кроме семантических not_found/wrong_lane/no_id) немедленный verify-GET
    in_progress СВОЕЙ полосы: задача там → claim долетел, мой (vps одно-воркерная = доказательство
    владения) → исполнение штатно, сироты нет; иначе прежний пропуск цикла (fail-safe, настоящее
    застревание добьёт реапер 6de3cfc). Claim НЕ идемпотентен — именно verify, не слепой re-POST.
    Тесты test_claim_verify.py (в гейте). Реапер закрывал ПОСЛЕДСТВИЯ, это — КОРЕНЬ.
  • DURABLE-СЛОЙ BRIDGE ПРОТИВ INTERMITTENT 404 GOOGLE (4f892d7, хвост §7 закрыт): follow-redirect-as-GET
    (3xx → явный GET на Location), backoff-ретраи echo-GET (404/5xx/timeout, 3 попытки + jitter), полный
    ретрай только read-only/идемпотентным, unauthorized-resend токена, анти-клин Session; контракт ошибок
    байт-в-байт. Тесты test_bridge_durable.py (7, в гейте).
  • O3-1 «КНОПКА БРОНЬ» — ЖИВОЙ ЭКЗАМЕН PASS (ПК-репо userbot: 8b86924 + полировка ee384b9, U/D/C/H):
    контакт из client_ref, имя из Telethon-профиля, модель из черновика, цена ВСЕГДА из Bridge.
  • O3-2a BOOKING.JS ДОКРУЧЕН И ЗАДЕПЛОЕН (be09494, Bridge прод @65): конфликт-чек занятости, bad_dates,
    нормализация дат, активация брони по date_start; смок conflict/bad_dates PASS, откат зафиксирован
    (redeploy прошлой версии).
  • O3-2b RECON INTAKE: вход = группа «Входящие брони», триггер «🆕 БРОНЬ», INTAKE_APPROVERS, билет 4.2.
  • O3-2c МОСТ (ПК-репо userbot 38fc79a): «✅ В CRM» → userbot постит в группу «Входящие брони» —
    bot-to-bot слепота (бот не видит сообщений бота) обойдена. СКВОЗНОЙ ЭКЗАМЕН: 5/6 станций живьём,
    остановлен стражем INTAKE ЧЕСТНО (нет Maps+паспорта) — дожим станции 6 и доработка 2.1 (автосбор
    гео/паспорта из диалога) = хвосты Раздела 7.
  ИТОГ 08.07: цепочка брони «кнопка у менеджера → CRM (Booking.js) → карточка в группе Входящие брони»
  собрана и проверена живьём до стража INTAKE; следующий заход O3 = КУСОК 3 (депозит/выдача/приём).

СРЕДА «РУЛЮ С ТЕЛЕФОНА"""
# закрывающую кавычку названия среды не трогаем — якорь обрезан до уникального префикса
edit(A1, BLOCK_0807, "§3 блок ⭐08.07")

# --- §4: приоритетный абзац — статус O3 куски 1-2 ---
A2 = ("(бронь/выдача/приём — см. 🧭 ниже). Красное ТОЛЬКО кнопкой Филиппа — не ослаблено.")
R2 = ("(бронь/выдача/приём — см. 🧭 ниже). ⭐08.07: O3 КУСКИ 1–2 СОБРАНЫ (кнопка «Бронь» → CRM/Booking.js "
      "→ мост в группу; сквозной экзамен 5/6 станций живьём, остановлен стражем INTAKE честно — детали в "
      "Разделе 3 ⭐08.07; хвост-дожим экзамена + доработка 2.1 автосбор гео/паспорта — Раздел 7). "
      "Следующий заход O3 = КУСОК 3 (депозит/выдача/приём) — разведка пошла. "
      "Красное ТОЛЬКО кнопкой Филиппа — не ослаблено.")
edit(A2, R2, "§4 приоритетный абзац")

# --- §4: пункт [O3] главной оси ---
A3 = ("Чек-лист выдачи + персист-состояние байка + сигналы. Проектирует штаб ДО кода.")
R3 = ("Чек-лист выдачи + персист-состояние байка + сигналы. Проектирует штаб ДО кода.\n"
      "     ⭐ 08.07: КУСКИ 1–2 (бронь) СОБРАНЫ — O3-1 кнопка «Бронь» (живой экзамен PASS) + O3-2a/b/c "
      "(Booking.js Bridge @65 + RECON INTAKE + мост userbot→группа). СЛЕДУЮЩИЙ ЗАХОД = КУСОК 3 "
      "(депозит/выдача/приём), разведка пошла. Детали в Разделе 3 ⭐08.07.")
edit(A3, R3, "§4 пункт [O3]")

# --- §7: два новых хвоста сверху списка ---
A4 = ("По каждому: что / почему отложено / что разблокирует.\n")
R4 = ("По каждому: что / почему отложено / что разблокирует.\n"
      "- ДОЖИМ СКВОЗНОГО ЭКЗАМЕНА O3-2 (станция 6/6, заведено 08.07): экзамен цепочки брони прошёл 5/6 "
      "станций живьём и остановлен стражем INTAKE ЧЕСТНО — в тестовом диалоге не было Maps-локации и "
      "паспорта. РАЗБЛОКИРУЕТ: прогон финальной станции на диалоге с полным набором интейка "
      "(Maps + паспорт) — либо вручную, либо после доработки 2.1 ниже.\n"
      "- ДОРАБОТКА O3-2.1 — АВТОСБОР ГЕО/ПАСПОРТА ИЗ ДИАЛОГА (заведено 08.07): страж INTAKE требует "
      "Maps+паспорт, сейчас они попадают в карточку только если менеджер собрал руками; научить userbot "
      "вытаскивать их из переписки клиента автоматически. РАЗБЛОКИРУЕТ: отдельный заход по O3 куску 2.1 "
      "(клиентский контур, ПК-репо).\n")
edit(A4, R4, "§7 два новых хвоста")

# --- §7: хвост INTERMITTENT 404 — кандидат durable-фикса ВЫПОЛНЕН (4f892d7) ---
A5 = ("  КАНДИДАТ durable-фикса: bridge_client follow-redirect-as-GET + backoff. "
      "РАЗБЛОКИРУЕТ: отдельный зелёный заход.")
R5 = ("  [✅ ЗАКРЫТ 08.07] durable-слой СДЕЛАН (4f892d7): follow-redirect-as-GET + backoff-ретраи + "
      "анти-клин Session в bridge_client (тесты test_bridge_durable.py, в гейте). Сами 404/таймауты — "
      "сторона Google; наблюдать повторные эпизоды.")
edit(A5, R5, "§7 хвост 404 durable закрыт")

for anchor, repl, label in edits:
    n = text.count(anchor)
    if n != 1:
        print(f"ANCHOR FAIL [{label}]: встречается {n} раз (нужно ровно 1) — СТОП, ничего не пишу")
        sys.exit(1)
    text = text.replace(anchor, repl)
    print(f"OK edit: {label}")

new_len = len(text)
with open("/tmp/KB_MASTER_new_20260708.md", "w", encoding="utf-8") as f:
    f.write(text)
print(f"len {orig_len} → {new_len} (+{new_len - orig_len})")

c = BridgeClient()
w = c.write_doc(text=text, id=KB_MASTER_ID)
if not w.get("ok"):
    print("WRITE FAIL:", w)
    sys.exit(1)
print("write_doc OK:", {k: w.get(k) for k in ("ok", "len", "id") if k in w})

# post-write verify: читаем прод обратно и сверяем длину code points + маркеры
r = c._call("read_doc", id=KB_MASTER_ID)
if not r.get("ok"):
    print("VERIFY READ FAIL:", r)
    sys.exit(1)
back = r.get("text", "")
markers = ["⭐ 08.07 — O3 КУСКИ 1–2 СОБРАНЫ", "claim-verify в process_new",
           "ДОЖИМ СКВОЗНОГО ЭКЗАМЕНА O3-2", "ДОРАБОТКА O3-2.1", "[✅ ЗАКРЫТ 08.07] durable-слой СДЕЛАН"]
missing = [m for m in markers if m not in back]
print(f"post-write verify: read-back len={len(back)} vs written={new_len} "
      f"{'MATCH' if len(back) == new_len else 'MISMATCH'}; markers missing={missing or 'нет'}")
if len(back) != new_len or missing:
    sys.exit(1)
print("VERIFIED: KB_MASTER обновлён и сверен по живому проду")
