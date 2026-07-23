"""DONE (чистка орфанов заявка 40) в cc_log + пульс ОДНОЙ операцией (POST write_doc, под врезкой)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

ENTRY = """DONE 2026-07-03 03:25 UTC (чистка орфанов, заявка 40 ✅ 03.07 08:31, headless): удалены 7 файлов ~1132 КБ старше 7 дней — _brain_recon.py; memory.db.bak-2026-06-05/-c2-20260608/-rules-20260608/-topicbike (04–08.06); bridge-gs Bridge.js.bak-fase1 + ReadFleet.js.bak-fase1 (09.06).
— Страховка: tar-снимок удалённого /tmp/orph40_backup_20260703.tar.gz (224 КБ, 7 файлов сверены до rm; живёт до ребута).
— ОСТАВЛЕНЫ 120 из 122 позиций списка [шаг 7/7 родитель 33]: всё с mtime <7 дней (26.06–03.07, вкл. свежие бэкапы 02–03.07 — откаты активных правок) + .claude/settings*.bak-approve-20260701/*.bak-reclass-20260702 (откат авто-approve). По mtime старше отсечки 26.06 03:05 UTC оказались только эти 7 — остальные хелперы/бэкапы моложе, чем выглядело по именам.
— Контроль: memory.db/bot.py/splinter.py/Bridge.js/ReadFleet.js на месте; git status — только untracked, tracked не задет; гейт ЗЕЛЁНЫЙ (29 тестов, 9.1с); splinter и orchestrator-daemon active. restart не требовался.
СТАТУС: функционально подтверждено (файлы удалены, контроль остатка + гейт пройдены).
ХВОСТЫ: 120 свежих орфанов остаются по правилу владельца — уйдут под ту же логику «старше 7 дней» при следующей чистке (после 10.07); +4 хелпера _orph40_* этой задачи."""

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log failed: {r}"
lines = r.get("text", "").split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
assert sep is not None, "врезка (═-only строка) не найдена"
new_text = "\n".join(lines[: sep + 1]) + "\n" + ENTRY + "\n\n" + "\n".join(lines[sep + 1 :])
w = c.write_doc(text=new_text, name="cc_log")
print("cc_log write ok:", w.get("ok"), "| new len:", len(new_text))
assert w.get("ok"), f"write cc_log failed: {w}"

PULSE = "2026-07-03 03:25 UTC | 🟢 | чистка орфанов (заявка 40) выполнена: 7 файлов ~1.1МБ старше 7 дней удалены (tar-снимок в /tmp), 120 свежих оставлены по правилу владельца, гейт зелёный, splinter/daemon active | ничего не жду | детали→cc_log запись «DONE 03.07 чистка орфанов заявка 40»"
p = c.write_doc(text=PULSE, name="pulse")
print("pulse write ok:", p.get("ok"))
