"""Точечная правка KB_RULES под ступень 2 O4 (шаг 3/7 родитель 33). Зона 🟢/🟠:
бэкап текста на диск ПЕРЕД write, замены строго по якорям, write только если read ok и все якоря найдены."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="rules")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")

with open("/root/turbobaby-manager-bot/_s3_rules.bak-20260703", "w", encoding="utf-8") as f:
    f.write(old)
print("бэкап:", len(old), "символов → _s3_rules.bak-20260703")

REPL = [
    # 1) красные подтверждения: git push больше не красное (доктрина разд.8)
    (
        "- КРАСНЫЕ ПОДТВЕРЖДЕНИЯ (деплой/git push/одобрение) → КНОПКИ дев-бота (✅/❌, тап). Termux — обычным языком.",
        "- КРАСНЫЕ ПОДТВЕРЖДЕНИЯ (бизнес-красное: clasp-деплой / запись в рабочие таблицы / деньги / удаление;\n"
        "  git push и restart splinter — НЕ красное, авто по доктрине разд.8) → КНОПКИ дев-бота (✅/❌, тап). Termux — обычным языком.",
    ),
    # 2) обновление маршрутизации после ступени 2 O4 — блок под ИТОГ раздела 1
    (
        "ИТОГ: прежде чем дать задачу дев-боту — это чтение кода/recon? Если да → Termux (иначе встанет).",
        "ИТОГ: прежде чем дать задачу дев-боту — это чтение кода/recon? Если да → Termux (иначе встанет).\n"
        "ОБНОВЛЕНИЕ 03.07.2026 (ступень 2 O4 в проде, KB_MASTER разд.3/4 — правило выше частично устарело):\n"
        "тема 328 теперь принимает ПРОИЗВОЛЬНЫЕ задачи — «тз: <ТЗ>» (очередь → headless Claude Code) и\n"
        "«декомпозируй: <крупное ТЗ>» (планировщик read-only → 2–7 шагов «[шаг i/N родитель id]» по одному,\n"
        "halt-on-fail, красный шаг кнопкой). Чтение кода/recon МОЖНО слать в 328 через «тз:» — ограничение\n"
        "«только Termux» снято; белый список 7 остаётся для мгновенных типовых команд без headless.\n"
        "Termux — для глубокого красного, тонкой/крупной стройки и интерактива. Restart splinter headless-CC\n"
        "делает САМ оранжевым циклом (гейт gate.py → restart → проверка чистого старта → отчёт); красное\n"
        "(Лист1/CRM/деньги/clasp/sqlite3/delete) — по-прежнему ТОЛЬКО кнопкой Филиппа (см. разд.8).",
    ),
    # 3) KB_ROADMAP_v2 в манифесте не существует — единственный роадмап = roadmap_master (KB_MASTER разд.5)
    (
        "ЖИВЫЕ доки (KB_MASTER, KB_ROADMAP_v2,\nKB_RULES/KB_INFRA/KB_STATE_MODEL)",
        "ЖИВЫЕ доки (KB_MASTER, KB_ROADMAP_MASTER (ключ roadmap_master),\nKB_RULES/KB_INFRA/KB_STATE_MODEL)",
    ),
]

new = old
for a, b in REPL:
    n = new.count(a)
    if n != 1:
        print(f"ЯКОРЬ НЕ УНИКАЛЕН/НЕ НАЙДЕН (count={n}): {a[:60]!r} — НЕ пишу")
        raise SystemExit(1)
    new = new.replace(a, b)

w = c.write_doc(text=new, name="rules")
print("rules WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))

chk = c._call("read_doc", name="rules")
t = chk.get("text", "")
print("контроль: ok=", chk.get("ok"), "len=", len(t),
      "| ОБНОВЛЕНИЕ 03.07 присутствует:", "ОБНОВЛЕНИЕ 03.07.2026 (ступень 2 O4" in t,
      "| roadmap_master присутствует:", "KB_ROADMAP_MASTER (ключ roadmap_master)" in t)
