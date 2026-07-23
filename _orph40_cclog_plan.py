"""Запись PLAN (перечень удаляемого, заявка 40) в cc_log + пульс ОДНОЙ операцией.
Протокол: read_doc(name=cc_log) -> вставка ПОД врезкой (первая ═-only строка) -> write_doc(name=cc_log);
писать только если read ok. Затем write_doc(name=pulse) тем же шагом."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

ENTRY = """PLAN 2026-07-03 03:10 UTC (чистка орфанов, заявка 40 ✅ 03.07 08:31, headless): удаляю по правилу владельца «старше 7 дней» из списка DONE [шаг 7/7 родитель 33]. ТОЧНЫЙ ПЕРЕЧЕНЬ (7 файлов, ~1132 КБ, всё untracked):
— хелперы корня (1 шт, 1.4 КБ): _brain_recon.py (25.06);
— бэкапы memory.db (4 шт, 1108 КБ): memory.db.bak-2026-06-05, memory.db.bak-c2-20260608, memory.db.bak-rules-20260608, memory.db.bak-topicbike (04–08.06, старше месяца);
— бэкапы bridge-gs (2 шт, 22 КБ): Bridge.js.bak-fase1, ReadFleet.js.bak-fase1 (09.06).
ОСТАВЛЯЮ 120 из 122 позиций списка: всё с mtime <7 дней (26.06–03.07 — свежие откаты активных правок, вкл. бэкапы 02–03.07) + .claude/settings*.bak-approve-20260701/*.bak-reclass-20260702 (прописанный откат авто-approve). Критерий = mtime против отсечки 2026-06-26 03:05 UTC. Страховка: перед rm — tar-снимок удаляемого в /tmp/orph40_backup_20260703.tar.gz."""

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log failed: {r}"
text = r.get("text", "")
lines = text.split("\n")
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

PULSE = "2026-07-03 03:10 UTC | 🟡 | чистка орфанов (заявка 40): PLAN зафиксирован — удаляю 7 файлов ~1.1МБ старше 7 дней (1 хелпер + 4 memory.db.bak 04–08.06 + 2 bridge-gs .bak-fase1), 120 свежих оставляю | ничего не жду, выполняю удаление + гейт | детали→cc_log запись «PLAN 03.07 чистка орфанов заявка 40»"
p = c.write_doc(text=PULSE, name="pulse")
print("pulse write ok:", p.get("ok"))
