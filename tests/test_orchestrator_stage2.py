"""Моки O4 ступень 2 (A+B, 03.07; Q2 разблокирован 03.07): «тз:» дев-режим (метка from → таймаут
45 мин), преамбула v3 (git push И restart splinter — CC сам; restart оранжевым циклом
гейт→restart→чистый старт→отчёт; настоящее красное op=other БЕЗ изменений; дисциплина cc_log+пульс;
сводка ≤400), NEEDS_APPROVAL-детект жив (фоллбэк), новые зелёные команды (просрочки/статус/гейт).
Сети/Telegram/claude нет — всё мокнуто."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
os.environ["THEATER_ROUTER"] = "0"  # изоляция от роутера театра (кусок 3): легаси-поведение 328

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD
import devbot as DB

# (1) таймауты: dev-метка → 45 мин, остальное → 10 мин
print("(1) выбор таймаута по метке from:")
res.append(ok(OD.TASK_TIMEOUT == 600 and OD.TASK_TIMEOUT_DEV == 2700, "константы 600/2700"))
res.append(ok(OD._task_timeout({"from": "Filipp-328-dev"}) == 2700, "from=*-dev → 2700с (45 мин)"))
res.append(ok(OD._task_timeout({"from": "Filipp-328"}) == 600, "from=Filipp-328 → 600с"))
res.append(ok(OD._task_timeout({}) == 600, "без from → 600с (безопасный дефолт)"))

# (2) преамбула v3: git push И restart сам (Q2), настоящее красное op=other + дисциплина
print("(2) преамбула v3:")
P = OD.APPROVAL_PREAMBLE
res.append(ok("git push" in P and "делай САМ" in P, "git push — делает САМ (не через кнопку)"))
res.append(ok("git_push — отправить коммиты" not in P, "устаревшая op-инструкция git_push УБРАНА"))
res.append(ok("systemctl restart splinter — тоже делай САМ" in P and "САМ НЕ делай" not in P,
              "Q2: restart splinter — CC делает САМ (обкаточный запрет снят)"))
res.append(ok("только при exit 0" in P and "чистого старта" in P and "нужен был restart" in P,
              "Q2: оранжевый цикл restart — гейт → restart → чистый старт → отчёт"))
res.append(ok("op=other" in P and "confirmed=true" in P and "delete_event" in P,
              "настоящее красное → op=other с карточкой"))
res.append(ok("cc_log" in P and "pulse" in P and "ОДНОЙ операцией" in P and "gate.py" in P,
              "дисциплина: cc_log+пульс одной операцией, гейт перед push"))
res.append(ok("400" in P and "бэкап" in P.lower(), "формат сводки ≤400 + бэкап перед правкой"))

# (3) NEEDS_APPROVAL-детект и parse_op не сломаны
print("(3) детект красной зоны:")
res.append(ok(OD._detect_needs_approval("строка\nNEEDS_APPROVAL: op=restart_splinter | после правки X")
              .startswith("op=restart_splinter"), "маркер op=restart_splinter ловится"))
res.append(ok(OD.parse_op("op=restart_splinter | x") == "restart_splinter"
              and OD.parse_op("op=other | Лист1") == "other"
              and OD.parse_op("op=set_fleet_oil | y") == "other", "parse_op: перечень НЕ расширен"))
res.append(ok(OD._detect_needs_approval("обычный отчёт, всё сделано") is None, "чистый done — без маркера"))
res.append(ok(OD.AUTO_OPS == ("git_push", "restart_splinter"), "AUTO_OPS не расширены (безопасность D)"))

# (4) run_task: таймаут прокидывается в subprocess, маркер → needs_approval
print("(4) run_task (мок subprocess):")
CALLS = []
class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc
_real_run = OD.subprocess.run
def fake_run(args, **kw):
    CALLS.append(kw)
    return FakeProc(fake_run.out)
OD.subprocess.run = fake_run
fake_run.out = "сводка: всё сделано"
st, r = OD.run_task(1, "проверь X", task_timeout=2700)
res.append(ok(st == "done" and CALLS[-1]["timeout"] == 2700, "dev-таймаут 2700 дошёл до subprocess"))
fake_run.out = "NEEDS_APPROVAL: op=restart_splinter | нужен рестарт после правки"
st2, r2 = OD.run_task(2, "поправь Y")
res.append(ok(st2 == "needs_approval" and "restart_splinter" in r2 and CALLS[-1]["timeout"] == 600,
              "маркер → needs_approval; дефолт-таймаут 600"))
OD.subprocess.run = _real_run

# (5) devbot: «тз:» → dev-метка, «задача:» → быстрая
print("(5) enqueue «тз:» vs «задача:»:")
ENQ = []
class FakeBridge:
    def enqueue_task(s, frm, txt): ENQ.append((frm, txt)); return {"ok": True, "id": 77}
    def _call(s, a, **k):
        return {"ok": True, "text": "2026-07-03 | 🟢 | тестовый пульс | ничего не жду | детали→нет"}
fb = FakeBridge()
m1 = DB._try_enqueue("тз: почини рендер", fb)
res.append(ok(ENQ[-1] == ("Filipp-328-dev", "почини рендер") and "45 мин" in m1,
              "«тз:» → from=Filipp-328-dev + ответ про дев-режим"))
m2 = DB._try_enqueue("задача: прочитай лог", fb)
res.append(ok(ENQ[-1] == ("Filipp-328", "прочитай лог"), "«задача:» → from=Filipp-328 (быстрый)"))
res.append(ok(DB._try_enqueue("тз:", fb).startswith("🤖 Пустое ТЗ"), "пустое «тз:» отклонено"))
res.append(ok(DB._try_enqueue("обычный текст", fb) is None, "не-префикс → None (идёт в allowlist)"))
res.append(ok(set(("Filipp-328", "Filipp-328-dev", "Filipp-328-dec",
                   "Filipp-pc", "Filipp-pc-dev", "Filipp-pc-dec",
                   "Filipp-pcloc-dec", "Filipp-curator")) == set(DB.QUEUE_FROMS),
              "фильтр отчётов включает все метки (вкл. dec часть C, полосу pc 04.07, "
              "pc-декомпозицию ПК-театра 07.07, локальный дирижёр ПК 11.07 "
              "и куратора целей 12.07)"))

# (6) новые зелёные команды B
print("(6) зелёные команды B:")
class BR:                                  # парк как в test_o3: NMAX просрочен (abs nobase+air+oil)
    def _call(s, a, **k):
        if a == "read_doc" and k.get("name") == "pulse":
            return {"ok": True, "text": "2026-07-03 | 🟢 | тестовый пульс"}
        return {"ok": False}
    def fleet(s): return {"data": {"bikes": [
        {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 30000,
         "oil_last_km": 24000, "gear_last_km": 27000, "abs_last_km": 0, "airfilter_last_km": 5000}]}}
    def service_list(s): return {"items": []}
out = DB._g_overdue(BR())
res.append(ok("Просрочки ТО: 1 байков" in out and "4255 NMAX 155CC PHUKET" in out,
              "«просрочки»: скан O3 переиспользован, байк в списке"))
res.append(ok("❗не делалось" in out and "+" in out, "«просрочки»: nobase и «+N км» помечены"))
class BR0(BR):
    def fleet(s): return {"data": {"bikes": []}}
res.append(ok(DB._g_overdue(BR0()) == "🔧 Просрочек ТО нет 👍", "«просрочки»: пустой парк → нет 👍"))
res.append(ok(DB._g_pulse(BR()).startswith("📟 2026-07-03"), "«статус»: строка пульса с 📟"))
res.append(ok(DB._match("просрочки") is not None and DB._match("статус") is not None
              and DB._match("гейт") is not None, "allowlist матчит просрочки/статус/гейт"))
res.append(ok("тз:" in DB._g_help() and "просрочки" in DB._g_help(), "help описывает «тз:» и новые команды"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
