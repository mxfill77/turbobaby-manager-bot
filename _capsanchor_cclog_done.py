"""cc_log DONE + pulse (ОДНА операция) — перенос адреса капов K3:M15 → Z3:AB15 (CAPS_ANCHOR)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

DONE = (
    "DONE 2026-07-05 11:3x: [капы — перенос адреса K3:M15 → Z3:AB15, тз 328] commit 4addf05, push "
    "20762b6..4addf05, гейт 38 зелёных. Блок капов мешал менеджеру (вставал впритык к живой J-квоте "
    "строк байков 4–36 «Календаря»). QuotePrice.js (/root/turbobaby-bridge-gs, бэкап .bak-capsanchor-20260705): "
    "введена ЕДИНАЯ константа CAPS_ANCHOR {col:26(Z), headerRow:3, dataRows:12} — читатель (quoteReadCaps_) "
    "и писатели (setCaps/toggleCap) берут адрес ОТСЮДА → всегда синхронны, будущий перенос = 1 строка. Скан "
    "K..T убран (шапка не «Модель» по адресу → null, обратная совместимость), новый хелпер quoteColLetter_ "
    "(26→Z/27→AA/28→AB, header_cell='Z3'), удалены QUOTE_CAP_SCAN_FROM/TO/MAX_ROWS/quoteFindCapCol_. Bridge.js: "
    "комментарий роутинга обновлён. Рабочую A..J и старый K/L/M «Календаря» код НЕ трогает. Тесты-зеркала "
    "переписаны на Z3:AB15 (test_quote_caps 11 + test_set_caps 12): дрейф-guard CAPS_ANCHOR==Z3/12строк + "
    "«скан-констант нет», round-trip set→read, дочистка хвоста, col_letter. node --check ✅. СТАТУС: технически "
    "готово (гейт зелёный, синтаксис ок); функц. НЕ подтверждено — прод-Bridge НЕ задеплоен. "
    "ХВОСТЫ (руки/да Филиппа): 1) clasp push+redeploy QuotePrice.js+Bridge.js (карточка); 2) после деплоя "
    "боевой set_caps 12 моделей confirmed (красная карточка «да») → пишет в Z3:AB15; 3) проверка "
    "quote_price NMAX 4255/30д → cap 5000. Старый K3:M15 останется с прежним содержимым до боевого set_caps "
    "(он пишет ТОЛЬКО Z-регион); K/L/M чистить руками при желании."
)

PULSE = (
    "2026-07-05 11:3x | 🟡 | капы: адрес блока перенесён K3:M15 → Z3:AB15 (CAPS_ANCHOR, одна константа), "
    "commit 4addf05 push, гейт 38 зелёных | жду: clasp push+redeploy (Termux) → боевой set_caps 12 моделей "
    "confirmed (да) → quote_price NMAX cap 5000 | детали→cc_log запись «перенос адреса капов Z3»"
)

# --- cc_log: read → вставить под врезкой (после первой ═-only строки) → write ---
r = c._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log fail: {r}"
lines = r["text"].split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
assert sep is not None, "врезка ═-only не найдена — прерываю (не порчу шапку)"
new_lines = lines[: sep + 1] + ["", DONE] + lines[sep + 1 :]
wr = c.write_doc("\n".join(new_lines), name="cc_log")
print("cc_log write:", wr.get("ok"), "| new len:", len("\n".join(new_lines)))

# --- pulse: перезапись ---
wp = c.write_doc(PULSE, name="pulse")
print("pulse write:", wp.get("ok"))
