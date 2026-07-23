"""cc_log DONE + pulse (ОДНА операция) — конверт одобренной заявки 48: clasp-деплой капов Z3:AB15, хендофф в Termux."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

DONE = (
    "DONE 2026-07-05: [конверт одобренной заявки 48 — clasp-деплой капов Z3, тема 328] Филипп нажал «да» "
    "на clasp-деплой Bridge. Прер-проверка перед хендоффом (read-only): QuotePrice.js в /root/turbobaby-bridge-gs "
    "несёт CAPS_ANCHOR {col:26(Z), headerRow:3, dataRows:12}; бэкап QuotePrice.js.bak-capsanchor-20260705 на месте; "
    "node --check QuotePrice.js+Bridge.js ✅; код закоммичен (4addf05); гейт 38 зелёных. ВЫВОД: clasp push/redeploy — "
    "настоящее красное (Termux/руки, headless без skip-permissions физически не деплоит; одобрение конверта обход "
    "НЕ даёт) → выдал NEEDS_APPROVAL: op=other с карточкой команд для Termux. Команды: из /root/turbobaby-bridge-gs "
    "`clasp push` затем `clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw`. "
    "Проверка после: ping=v1.0.0 alive + list_brain (cc_log/review). Откат: redeploy прошлой версии "
    "(бэкап .bak-capsanchor-20260705). СТАТУС: технически готово к деплою; функц. НЕ подтверждено — прод НЕ задеплоен, "
    "ждёт руку в Termux. ХВОСТЫ: 1) человек делает clasp push+redeploy; 2) после деплоя боевой set_caps 12 моделей "
    "confirmed (отдельная красная карточка «да») → пишет Z3:AB15; 3) quote_price NMAX 4255/30д → cap 5000."
)

PULSE = (
    "2026-07-05 | 🟡 | заявка 48 одобрена: прер-проверка перед clasp-деплоем капов Z3 пройдена "
    "(CAPS_ANCHOR Z3/col26, бэкап, node ✅, коммит 4addf05, гейт 38 зелёных) | жду: рука в Termux — "
    "clasp push+redeploy из /root/turbobaby-bridge-gs (headless деплоить не может), затем ping/list_brain, "
    "потом боевой set_caps 12 моделей | детали→cc_log запись «конверт заявки 48 clasp-деплой капов Z3»"
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

wp = c.write_doc(PULSE, name="pulse")
print("pulse write:", wp.get("ok"))
