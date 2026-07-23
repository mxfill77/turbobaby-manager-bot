"""cc_log DONE (шаг 7/7 родитель 33: git ahead=0 + орфаны + сводка ревизии) + KB_PULSE — ОДНОЙ операцией.
Запись ПОД врезкой (матч ═-only строки), write только если read ok. Зона 🟢."""
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

entry = (
"DONE " + ts + " UTC ([шаг 7/7 родитель 33], headless): git до ahead=0 + список орфанов корня + СВОДКА РЕВИЗИИ.\n"
"— Гейт зелёный (29 тестов, 9.3с) → git push ok: 346a154..e45908b main (ушёл e45908b — синк CLAUDE.md шага 4). "
"ahead=0 ПОДТВЕРЖДЁН (git status -sb: main...origin/main без ahead).\n"
"— bridge-gs: /root/turbobaby-bridge-gs — НЕ git-репозиторий (fatal: not a git repository), это чистая clasp-папка; "
"коммитить/пушить нечего, версии хранит сам Apps Script (clasp pull + version history). Хвост-вопрос на ревизию: "
"заводить ли git-зеркало этой папки.\n"
"— ОРФАНЫ/УСТАРЕВШЕЕ (122 файла ~9.0 МБ; НИЧЕГО НЕ УДАЛЯЛ — кнопка Филиппу, удаление = 🔴):\n"
"  • _*.py хелперы корня: 63 шт ~150 КБ (одноразовые cclog/recon/step-скрипты 06.06–03.07, вкл. 4 хелпера _s7_* этого шага);\n"
"  • _delivery_6m.jsonl 1.2МБ, _recon_result.json 90КБ, _state_mock_test.js 5КБ;\n"
"  • бэкапы кода: splinter.py.bak-* 19 шт ~5.3МБ (26.06–02.07), bot.py.bak-* 5, devbot 4, orchestrator_daemon 3, "
"pretool_guard 3, memory.py 2, bridge_client/notify по 1;\n"
"  • CLAUDE.md.bak-* 7 шт ~365КБ (26.06–03.07), _s3_rules.bak-20260703 25КБ;\n"
"  • memory.db.bak-* 4 шт ~1.1МБ (05–08.06 — старше месяца);\n"
"  • .claude/settings*.bak* 6 шт 20КБ — НО .bak-approve-20260701 и .bak-reclass-20260702 = прописанный ОТКАТ режима "
"авто-approve (CLAUDE.md), их ОСТАВИТЬ;\n"
"  • bridge-gs: BotData.js.bak-bridgefreeze-20260702, Bridge.js.bak-fase1, ReadFleet.js.bak-fase1.\n"
"  ВАЖНО: всё это untracked (в git-истории НЕТ) — удаление безвозвратно, потому только по «да». Предложение: удалить "
"всё старше 7 дней; оставить бэкапы 02–03.07 (свежие откаты активных правок) + .claude/*.bak-approve/reclass.\n"
"— СВОДКА РЕВИЗИИ ПО РОДИТЕЛЮ 33 (все 7 шагов done, halt-on-fail не сработал ни разу):\n"
"  1/7 разведка мозг↔реальность после ступени 2 O4 — список 8 расхождений (NOTE 00:48);\n"
"  2/7 KB_MASTER §3/§4/§7 + roadmap_master актуализированы (ступень 2 в проде, доктрина подтверждений);\n"
"  3/7 KB_RULES точечно поправлен (328: тз:/декомпозируй:, красное по доктрине, roadmap_master), KB_INFRA без правок, "
"list_brain: 24 ключа без дублей, 3 orphan-дока Brain в списке на решение;\n"
"  4/7 CLAUDE.md синк с O4 — раздел «ДЕВ-КОНТУР O4» (commit e45908b);\n"
"  5/7 рамка владельца сверена, готовый текст версии 03.07 — в NOTE (вставляет владелец);\n"
"  6/7 гигиена cc_log — всё сегодняшнее, подрезка не потребовалась;\n"
"  7/7 git ahead=0 + этот список орфанов.\n"
"СТАТУС: push и ahead=0 — функционально подтверждено; список орфанов — read-only факт; удаление ЖДЁТ «да» (кнопка).\n"
"ХВОСТЫ (открытые после родителя 33): (а) владельцу вставить рамку 03.07 в приложение Claude (NOTE шага 5); "
"(б) KB_MASTER §2 исполнитель 5 + маршрутизация recon и §6 чек-лист [4] — ещё доступень-2 формулировки; "
"(в) судьба Brain-орфанов из шага 3 (archive_OLD, KB_ROADMAP_v2-файл, регистрация KB_NORTH_STAR, roadmap_master вне папки?); "
"(г) чистка орфанов корня — по кнопке; (д) git-зеркало bridge-gs — решить; "
"(е) функциональная обкатка ступени 2 продолжается.\n"
)

lines = old.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:10]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
new = "".join(lines[:ins]) + entry + "\n" + "".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| вставка после строки", ins, "| old:", len(old), "new:", len(new))

pulse = (ts + " | 🟢 | [шаг 7/7 родитель 33 — ФИНАЛ] git ahead=0 (гейт 29✅ → push e45908b), bridge-gs = clasp-папка "
         "без git (пушить нечего), орфаны корня 122 файла ~9МБ переписаны списком — НЕ удалял | жду «да» кнопкой на "
         "чистку орфанов; владельцу — вставить рамку 03.07 (NOTE шага 5) | детали→cc_log DONE " + ts + " шаг 7/7")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
