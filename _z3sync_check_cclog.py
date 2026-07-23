"""cc_log DONE + pulse (ОДНА операция) — проверка синка clasp-папки на Z3-код (тз 328)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

DONE = (
    "DONE 2026-07-05 12:xx: [Z3-синк clasp-папки — проверка, тз 328] ИТОГ: копировать НЕЧЕГО — "
    "предпосылка задачи инвертирована. /root/turbobaby-bridge-gs (clasp-папка) УЖЕ на Z3-коде: "
    "QuotePrice.js (Jul5 11:19, 23259б) содержит CAPS_ANCHOR {col:26(Z), headerRow:3, dataRows:12}=Z3:AB15, "
    "старый K..T-скан (QUOTE_CAP_SCAN_FROM/TO/MAX_ROWS, quoteFindCapCol_) ПОЛНОСТЬЮ удалён (упоминания "
    "K3:M15 остались лишь в комментариях-истории «был K3:M15»); хелпер quoteColLetter_ есть. Bridge.js "
    "(Jul5 11:19) — роутинг set_caps/toggle_cap с комментарием Z3:AB15. node --check оба ✅. Диффом против "
    "локального бэкапа QuotePrice.js.bak-capsanchor-20260705 подтверждён переход K-скан→CAPS_ANCHOR. "
    "В зеркале /root/turbobaby-manager-bot ВЕРХНЕУРОВНЕВОГО QuotePrice.js/Bridge.js НЕТ (git трекает только "
    "ReadDocs.gs); единственная копия в зеркале — СТАРЫЙ K3-бэкап в _bridge_bak-quoteprice-20260703/ (Jul3). "
    "Т.е. Z3-код всегда авторился прямо в clasp-папке (как и сказано в коммите 4addf05). ПОЧЕМУ «clasp push "
    "already up to date @62»: раз локальный clasp-файл УЖЕ Z3 и push «up to date» — значит HEAD@62 уже "
    "содержит Z3; остаток = redeploy прод-деплоя на HEAD (прод закреплён на старой версии). Диагноз задачи "
    "(«правка в зеркале, не в clasp») ошибочен: будь так, локальный clasp-файл был бы K3 и push залил бы "
    "старьё, а не «up to date». Ничего НЕ деплоено (read-only). СТАТУС: технически подтверждено (синтаксис+"
    "содержимое); функц. НЕ подтверждено (прод НЕ трогал). ХВОСТЫ (руки/Termux): clasp push → redeploy "
    "<deploymentId AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw> → ping+list_brain."
)

PULSE = (
    "2026-07-05 12:xx | 🟢 | Z3-синк clasp-папки: копировать НЕЧЕГО — /root/turbobaby-bridge-gs УЖЕ на Z3 "
    "(QuotePrice.js CAPS_ANCHOR col:26 Z3:AB15, K-скан удалён; Bridge.js Z3-роутинг; node --check оба ✅), "
    "предпосылка «правка в зеркале» инвертирована, в зеркале только старый K3-бэкап | жду: clasp push+redeploy "
    "прод (Termux) | детали→cc_log запись «Z3-синк clasp-папки»"
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
