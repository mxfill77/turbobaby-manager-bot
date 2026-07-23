"""cc_log DONE + pulse (ОДНА операция) — проверка синка Z3-кода капов в clasp-папку."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

DONE = (
    "DONE 2026-07-05 12:xx: [синк Z3-капов в clasp-папку, тз 328] РЕЗУЛЬТАТ: КОПИРОВАТЬ НЕЧЕГО — "
    "clasp-папка /root/turbobaby-bridge-gs УЖЕ содержит Z3-код. Проверка: QuotePrice.js (23259 б, "
    "правлен Jul 5 11:19, до commit 4addf05 11:23) → CAPS_ANCHOR {col:26(Z), headerRow:3, dataRows:12}, "
    "quoteReadCaps_/setCaps/toggleCap читают адрес отсюда, скан K..T убран, quoteColLetter_ (26→Z/AA/AB); "
    "Bridge.js → роутинг-комментарий 'set_caps блок капов Z3:AB15'. node --check ОБОИХ ✅. Премьеса тз "
    "инвертирована: в /root/turbobaby-manager-bot НЕТ QuotePrice.js вовсе (только tests/*.py + temp "
    "_quote_*.js без caps-логики; _bridge_bak-quoteprice-20260703/ = старый снимок Jul 3 БЕЗ QuotePrice); "
    "commit 4addf05 в manager-bot тронул ТОЛЬКО tests/ (test_quote_caps+test_set_caps), а .js-правка Z3 "
    "сделана прямо в bridge-gs. Значит зеркало-источник — сама bridge-gs, синкать не из чего. "
    "«already up to date @62» на clasp push = локальная bridge-gs УЖЕ совпадает с HEAD → Z3-код "
    "запушен в HEAD; на прод (закреплённый URL) он попадает ТОЛЬКО через clasp redeploy <prod-deploymentId>, "
    "НЕ через push. Т.е. недостающий шаг для прода — redeploy, а не push. Ничего не деплоил (read-only). "
    "СТАТУС: технически подтверждено (Z3-код в clasp-папке, синтаксис ок); функц. на проде НЕ подтверждено "
    "до redeploy+ping. ХВОСТЫ (Termux, карточки): 1) clasp push (для чистоты, вероятно up-to-date); "
    "2) clasp redeploy <prod-deploymentId> — промоушен Z3 на прод-URL; 3) ping + list_brain; 4) боевой set_caps."
)

PULSE = (
    "2026-07-05 12:xx | 🟢 | синк Z3-капов: КОПИРОВАТЬ НЕЧЕГО — /root/turbobaby-bridge-gs УЖЕ Z3 "
    "(CAPS_ANCHOR Z3, node ✅), в manager-bot QuotePrice.js нет; push даёт up-to-date@62 → на прод "
    "нужен clasp REDEPLOY, не push | жду: Termux clasp redeploy prod-deploymentId + ping | "
    "детали→cc_log запись «синк Z3-капов в clasp-папку»"
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
