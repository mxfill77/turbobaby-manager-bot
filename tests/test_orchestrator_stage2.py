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
res.append(ok("делай САМ" in P and "wa-webhook" in P and "orchestrator-daemon" in P
              and "NEEDS_APPROVAL НЕ объявлять" in P,
              "Q2/16.07: рестарт/старт всех трёх сервисов — CC делает САМ, NEEDS_APPROVAL не объявлять"))
res.append(ok("только exit 0" in P and "старт чистый" in P,
              "Q2: оранжевый цикл restart — гейт → restart → чистый старт → отчёт"))
res.append(ok("op=other" in P and "подтверждённая запись" in P and "удаление событий" in P,
              "настоящее красное → op=other с карточкой"))
res.append(ok("cc_log" in P and "pulse" in P and "cclog.py" in P and "gate.py" in P,
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

# (4) run_task: таймаут прокидывается в communicate(), маркер → needs_approval
print("(4) run_task (мок _POPEN):")
CALLS = []
class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc
class _FakePopen4:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        CALLS.append({"timeout": timeout})
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode
class _MinFakeBC4:
    def task_heartbeat(s, tid): return {"ok": True}
_real_run = OD.subprocess.run
_real_POPEN4 = OD._POPEN
def fake_run(args, **kw):
    CALLS.append(kw)
    return FakeProc(fake_run.out)
def fake_popen4(args, **kw):
    return _FakePopen4(fake_run.out)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen4
OD.bc = _MinFakeBC4()
fake_run.out = "сводка: всё сделано"
st, r = OD.run_task(1, "проверь X", task_timeout=2700)
res.append(ok(st == "done" and CALLS[-1]["timeout"] == 2700, "dev-таймаут 2700 дошёл до communicate"))
fake_run.out = "NEEDS_APPROVAL: op=restart_splinter | нужен рестарт после правки"
st2, r2 = OD.run_task(2, "поправь Y")
res.append(ok(st2 == "needs_approval" and "restart_splinter" in r2 and CALLS[-1]["timeout"] == 600,
              "маркер → needs_approval; дефолт-таймаут 600"))
OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN4

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
                   "Filipp-pcloc-dec", "Filipp-curator",
                   "Filipp-revizor", "Filipp")) == set(DB.QUEUE_FROMS),
              "фильтр отчётов включает все метки (вкл. dec часть C, полосу pc 04.07, "
              "pc-декомпозицию ПК-театра 07.07, локальный дирижёр ПК 11.07, "
              "куратора целей 12.07, ревизора и ручные пробы владельца 06.08)"))

# (6) новые зелёные команды B
print("(6) зелёные команды B:")
class BR:                                  # парк как в test_o3: NMAX просрочен (abs+air+oil по значению)
    # РАЗМЕТКА КЛЕТОК (мост @79, 10.08.2026): скан зовёт fleet(cells=True) и различает пустую
    # клетку, прочерк и число. Без разметки живой скан честно скажет «не удалось проверить» —
    # поэтому мок повторяет живой формат. ABS здесь ЗНАЧЕНИЕ 5000 (было 0 = пустая клетка):
    # предмет этого файла — зелёные команды devbot, и парк должен остаться просроченным
    # по-настоящему. Смысл трёх состояний закреплён в tests/test_overdue_cells.py.
    def _call(s, a, **k):
        if a == "read_doc" and k.get("name") == "pulse":
            return {"ok": True, "text": "2026-07-03 | 🟢 | тестовый пульс"}
        return {"ok": False}
    def fleet(s, cells=False):
        row = {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 30000,
               "oil_last_km": 24000, "gear_last_km": 27000, "abs_last_km": 5000,
               "airfilter_last_km": 5000}
        if cells:
            row = dict(row, cells={f: {"state": "value", "num": row[f], "raw": str(row[f])}
                                   for f in ("mileage", "oil_last_km", "gear_last_km",
                                             "abs_last_km", "airfilter_last_km")})
        return {"data": {"bikes": [row]}}
    def service_list(s): return {"items": []}
out = DB._g_overdue(BR())
res.append(ok("просрочено 1 байков" in out and "4255 NMAX 155CC PHUKET" in out,
              "«просрочки»: скан O3 переиспользован, байк в списке"))
res.append(ok("+" in out and "не измерено 0 клеток" in out,
              "«просрочки»: «+N км» на месте, второе число названо отдельно (10.08.2026)"))
class BR0(BR):
    def fleet(s, cells=False): return {"data": {"bikes": []}}
# БЫЛО (до 08.08.2026): пустой парк → «🔧 Просрочек ТО нет 👍» — БУКВА В БУКВУ та же строка, что и
# на упавшем мосту, и на парке из 38 байков, у которого никто ничего не смотрел. СТАЛО: нуль без
# знаменателя не отдаётся (контракт читателя, scan_result; регресс — tests/test_scan_contract.py).
_out0 = DB._g_overdue(BR0())
res.append(ok("ПРОВЕРИТЬ НЕ УДАЛОСЬ" in _out0 and "осмотрено 0" in _out0,
              f"«просрочки»: пустой парк → не «нет 👍», а знаменатель: {_out0.splitlines()[0]}"))
res.append(ok(DB._g_pulse(BR()).startswith("📟 2026-07-03"), "«статус»: строка пульса с 📟"))
res.append(ok(DB._match("просрочки") is not None and DB._match("статус") is not None
              and DB._match("гейт") is not None, "allowlist матчит просрочки/статус/гейт"))
res.append(ok("тз:" in DB._g_help() and "просрочки" in DB._g_help(), "help описывает «тз:» и новые команды"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
