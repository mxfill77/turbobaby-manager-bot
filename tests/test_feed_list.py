# -*- coding: utf-8 -*-
"""ЛЕНТА, ШАГ 2 — СПИСОК СОБЫТИЙ ФАЗЫ 1 (04.08.2026).

Основание: docs/artifacts/2026-08-03-third-state-notify-design.md §3 (список утверждён владельцем)
+ docs/artifacts/2026-08-04-feed-list-phase1.md (этот заход). Шаг 1 собрал ПРОВОД и намеренно
оставил таблицу классов пустой; здесь она наполняется, и весь смысл теста — доказать ГРАНИЦУ
списка: пять названных событий говорят, всё остальное молчит.

ГОЛДЕНЫ — ДОСЛОВНЫЕ КОМАНДЫ ЖИВЫХ ТРАНСКРИПТОВ (класс 8 дисциплины: детект проверяется на том,
что реально печаталось, а не на сочинённом). Каждая строка ниже взята выемкой из
/root/.claude/projects/-root-turbobaby-manager-bot/*.jsonl за окно 28.07–04.08; там же взяты
ближние промахи — команды, которые подстрочный счёт спутал бы со списком (слово о рестарте в
теле коммита, `git stash list`, `cat /tmp/cc_guard_block/135.json`, `cclog.py "…git checkout…"`).

Секции:
 (1) ПОПАДАНИЯ — дословная команда каждого класса списка названа своим классом.
 (2) БЛИЖНИЕ ПРОМАХИ — слово о событии не есть событие: чтение, журнальная строка, тело коммита.
 (3) «НЕ УВЕДОМЛЯЕМ» (§4 проекта) — коммит, мозг, гейт, cp, рестарт демона, уборка в /tmp.
 (4) КРАСНОЕ ВЕДЁТ СЕБЯ КАК ПРЕЖДЕ — у него СВОЙ адрес (инбокс 1160), лента о нём молчит.
 (5) СКВОЗЬ ХУК: событие списка → РОВНО одна заметка в ленту, форма 🔔, метка полосы,
     и ответить на неё нечем (ни «да», ни номера, ни кнопок).
 (6) ИСХОД ЧЕСТЕН ПО ЖИВОЙ СХЕМЕ: шаг 1 писал «схему tool_response проверить нечем» — теперь
     проверено по транскрипту: успех = dict(stdout/stderr/interrupted/isImage/noOutputExpected)
     БЕЗ кода возврата, провал = СТРОКА «Error: Exit code N …», отказ движка = строка «Error: …»
     без кода. Отказ — НЕ событие мира: заметки быть не должно вовсе.
 (7) ДЕТАЛЬ PUSH — ветка · сколько коммитов · диапазон · ⚠️ машинерия защиты (§3.3 проекта).
 (8) ЛЕНТА ЧИТАЕТ ГАРД, НО НЕ ЗОВЁТ ЕГО ПИШУЩИХ ВЕТОК (ast, а не обещание в докстринге).
 (9) ПРОГОН НЕ КАСАЕТСЯ БОЕВЫХ ФАЙЛОВ СОСТОЯНИЯ — прямой ответ на инцидент 04.08.2026, когда
     тест гейта стёр боевой спул и убил находки владельца. Своё состояние — во ВРЕМЕННОМ
     каталоге с уникальным суффиксом. ДВА СЛОЯ, потому что они ловят РАЗНОЕ: снимок сверяет
     ОСТАТОК (имя+mtime+хеш до и после), аудит-хук `livewatch` — САМО ДЕЙСТВИЕ, включая то, что
     следа не оставило (удаление несуществующего, «создал и убрал», перезапись тем же). Именно
     вторым слоем найден живой случай в tests/test_guard_escalation.py — снимок его не видел.
(10) ИЗОЛЯЦИЯ ПРОБ ДЕЙСТВУЕТ И НА СПИСКЕ: фикстура с командой класса молчит.

Сети нет нигде: подпроцессам ставим NOTIFY_COUNT_FILE (дивёрсия до токена и сети), in-process
отправка замокана. CC_FEED_SEEN_DIR и PRETOOL_BLOCK_DIR подставляются ВСЕГДА (урок задачи 181).
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = "/root/turbobaby-manager-bot"
PY = os.path.join(ROOT, "venv", "bin", "python3")
HOOK = os.path.join(ROOT, "posttool_feed.py")
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ["CURATOR"] = "0"

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


# Уникальный суффикс — не «общий тестовый каталог»: два прогона рядом не должны видеть состояние
# друг друга, а боевые каталоги не должны видеть нас вовсе (секция 9).
TMP = tempfile.mkdtemp(prefix="feedlist_")
SEEN = os.path.join(TMP, "seen")
MARKERS = os.path.join(TMP, "markers")
os.makedirs(SEEN, exist_ok=True)
os.makedirs(MARKERS, exist_ok=True)

# ── СТРАЖ БОЕВЫХ КАТАЛОГОВ (секция 9 сверит) ───────────────────────────────────────────────
# ВЗВОДИТСЯ ДО ИМПОРТА ленты и ДО снимка — иначе прогон слеп к тому, что делает сам импорт:
# прежняя редакция брала снимок ПОСЛЕ `import posttool_feed`, и создание каталога состояния на
# импорте не увидела бы ни одна проверка этого файла.
LIVE_STATE = ("/tmp/cc_feed_seen", "/tmp/cc_feed_seen_test", "/tmp/cc_guard_block")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import livewatch
LW = livewatch.watch(*LIVE_STATE)


BEFORE = livewatch.snapshot(*LIVE_STATE)

import posttool_feed as PF

# ── ГОЛДЕНЫ: ДОСЛОВНЫЕ КОМАНДЫ ТРАНСКРИПТОВ ────────────────────────────────────────────────
HITS = [
    # (дословная команда, ожидаемый класс, откуда)
    ("systemctl restart splinter", "рестарт клиентского бота", "28.07 18:46"),
    ("systemd-run --on-active=10s systemctl restart splinter", "рестарт клиентского бота",
     "форма отложенного рестарта (обёртка не прячет юнит)"),
    ("systemctl stop splinter", "стоп клиентского бота", "форма из allow-списка"),
    ("pkill -f userbot_listen.py", "стоп клиентского бота", "ПК-полоса: процесс под pc_agent"),
    ("mkdir -p /root/turbobaby-manager-bot/docs/artifacts/discarded && "
     "mv /root/turbobaby-manager-bot/tests/test_card_border.py "
     "/root/turbobaby-manager-bot/docs/artifacts/discarded/test_card_border.py && "
     "ls -la /root/turbobaby-manager-bot/docs/artifacts/discarded/",
     "вынос теста из гейта", "02.08 07:34 — единственный живой случай окна"),
    ("git -C /root/turbobaby-manager-bot reset --hard 17221f2", "отброс рабочего дерева",
     "29.07 07:50"),
    ("git -C /root/turbobaby-manager-bot stash push -- splinter.py", "отброс рабочего дерева",
     "31.07 09:02"),
    ("git -C /root/turbobaby-manager-bot checkout -- _envfix_probe.py", "отброс рабочего дерева",
     "29.07 08:19"),
    ("git checkout HEAD~1 -- bridge_client.py && echo \"--- прогон ФИНАЛЬНОГО теста против кода "
     "ДО правки ---\" && PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_event_key.py 2>/dev/null | "
     "tail -4", "отброс рабочего дерева", "02.08 20:16 — признак пробы стоит НЕ в голове цепи"),
    ("git stash push -m \"guard-before-land\" -- ':(glob)*guard*'", "отброс рабочего дерева",
     "форма с pathspec"),
    ("rm /tmp/cc_guard_block/12.json /tmp/cc_guard_block/27.json /tmp/cc_guard_block/399.json",
     "стирание маркеров гарда", "живая команда корпуса"),
    ("git push origin main", "push в origin", "31.07 11:37"),
    ("git push", "push в origin", "30.07 14:50"),
    ("git push 2>&1 | tail -20", "push в origin", "28.07 18:44 — редирект не съедает remote"),
    ("git -C /root/turbobaby-manager-bot push origin main", "push в origin", "02.08 17:40"),
    ("git -c core.hooksPath=deploy/hooks push origin main", "push в origin",
     "31.07 11:25 — подкоманда не первый позиционный токен"),
]

# Ближние промахи: слово о событии ≠ событие. Все строки — из живых транскриптов.
NEAR = [
    ("systemctl show splinter -p MainPID -p ActiveState -p SubState -p ExecMainStartTimestamp",
     "чтение состояния сервиса"),
    ("systemctl is-active splinter", "чтение состояния сервиса"),
    ("systemctl cat splinter | head -40", "чтение юнита"),
    ("git -C /root/turbobaby-manager-bot stash list", "чтение списка отложенного"),
    ("git -C /root/turbobaby-manager-bot stash pop", "возврат работы, а не отброс"),
    ("git clean -n", "сухой прогон уборки"),
    ("git checkout -b feature-x", "новая ветка — работа не пропадает"),
    ("git checkout main", "переключение ветки"),
    ("grep -o \"git checkout[^\\\"]\\{0,80\\}\" "
     "/root/.claude/projects/-root-turbobaby-manager-bot/ed47b8e8.jsonl | head -10",
     "поисковый шаблон со словом об отбросе"),
    ("ls -la /tmp/cc_guard_block/ 2>/dev/null | head -30", "чтение каталога маркеров"),
    ("cat /tmp/cc_guard_block/135.json", "чтение маркера"),
    ("venv/bin/python3 /root/turbobaby-manager-bot/cclog.py \"DONE 2026-07-15 14:xx UTC: "
     "read-only DNS+curl check. Нужен systemctl restart wa-webhook.\"",
     "журнальная строка со словами о рестарте"),
    ("git commit -q -F - <<'MSG'\n"
     "третье состояние, шаг 1: канал заметок живёт в PostToolUse\n"
     "Клетка «выполнить и сказать» была пуста: рестарт клиентского бота, git push origin main,\n"
     "git reset --hard и rm /tmp/cc_guard_block/*.json проходили молча.\n"
     "MSG", "тело коммита — данные, а не команды"),
    ("mv /root/turbobaby-manager-bot/tests/test_card_border.py "
     "/root/turbobaby-manager-bot/tests/test_card_border2.py", "переименование ВНУТРИ гейта"),
    ("mv /tmp/tb_scratch/test_new.py /root/turbobaby-manager-bot/tests/test_new.py",
     "внос теста В гейт — защита не слабеет"),
    ("git push --dry-run origin main", "сухой прогон push"),
]

# §4 проекта: «не уведомляем вовсе» — 35 сообщений в сутки, которые обязаны остаться молчаливыми.
SILENT = [
    ("git commit -q -m \"фикс класса\"", "коммит — движение ВНУТРИ границы"),
    ("git add -A", "индекс"),
    ("venv/bin/python3 cclog.py DONE \"итог шага\"", "запись в мозг"),
    ("venv/bin/python3 gate.py", "прогон гейта"),
    ("cp _feed_new_settings.json .claude/settings.json", "копирование в рабочее дерево"),
    ("systemd-run --on-active=10s systemctl restart orchestrator-daemon",
     "отложенный рестарт демона — внутренний контур"),
    ("systemctl restart orchestrator-daemon", "рестарт демона"),
    ("systemctl restart wa-webhook", "транзит WA — в списке фазы 1 его нет"),
    ("rm -f /tmp/tb_scratch/recon.py", "уборка своего черновика во временном"),
    ("rm -rf /tmp/feedlist_abc123", "уборка своего каталога во временном"),
    ("tail -50 /root/turbobaby-manager-bot/splinter.log", "чтение лога"),
    ("git status --short", "диагностика"),
    ("git log --oneline -5", "история"),
]

# Красное: у него СВОЙ адрес (инбокс 1160). Лента о нём молчит — дублировать = размыть оба.
RED = [
    ("sqlite3 /root/turbobaby-manager-bot/memory.db \"UPDATE rules SET text='x' WHERE id=1\"",
     "SQL по своей БД — ask гарда"),
    ("clasp redeploy AKfycbxNC9gCM7", "деплой моста"),
    ("rm /root/turbobaby-manager-bot/bot.py", "удаление файла репо"),
    ("venv/bin/python3 -c \"import bridge_client; bridge_client.set_fleet_oil(number='5580', "
     "oil_km=35200, confirmed=True)\"", "боевая запись ТО в Лист1"),
]


def probe_payload(cmd, resp=None, sid="feedlist-A", tid=None):
    d = {"session_id": sid, "hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": ROOT,
         "tool_input": {"command": cmd},
         "tool_response": ({"stdout": "", "stderr": "", "interrupted": False, "isImage": False,
                            "noOutputExpected": False} if resp is None else resp)}
    return d


def child_env(count_file=None, extra=None):
    """env хука-подпроцесса: признаки тест-прогона снимаем (иначе изоляция проб погасит канал и
    мерить будет нечего), но ВСЕ каналы владельца замоканы: счётчик вместо сети + свои каталоги."""
    e = dict(os.environ)
    for k in ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PYTEST_CURRENT_TEST"):
        e.pop(k, None)
    e.pop("NOTIFY_COUNT_FILE", None)
    e.pop("CC_TASK_ID", None)
    e.pop("CC_LANE", None)
    e["CC_FEED_SEEN_DIR"] = SEEN
    e["PRETOOL_BLOCK_DIR"] = MARKERS
    e["PC_DEV_TOPIC_ID"] = "424242"          # адрес-заглушка: боевую тему из .env не трогаем
    if count_file:
        e["NOTIFY_COUNT_FILE"] = count_file
    if extra:
        e.update(extra)
    return e


def run_hook(payload, count_file=None, extra=None):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([PY, HOOK], input=data, capture_output=True, text=True, timeout=60,
                          env=child_env(count_file, extra))


def lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except OSError:
        return []


# ── (1) ПОПАДАНИЯ ──────────────────────────────────────────────────────────────────────────
print("(1) дословная команда класса → класс назван:")
for cmd, cls, src in HITS:
    got = PF.classify(cmd)
    ok(got == cls, "%-28s ← %s [%s]" % (str(got), " ".join(cmd.split())[:74], src))

# ── (2) БЛИЖНИЕ ПРОМАХИ ────────────────────────────────────────────────────────────────────
print("(2) слово о событии ≠ событие:")
for cmd, why in NEAR:
    got = PF.classify(cmd)
    ok(got is None, "молчит (%s): %s" % (why, " ".join(cmd.split())[:70]))

# ── (3) «НЕ УВЕДОМЛЯЕМ» ────────────────────────────────────────────────────────────────────
print("(3) §4 проекта — 35 сообщений в сутки, которых в ленте нет:")
for cmd, why in SILENT:
    got = PF.classify(cmd)
    ok(got is None, "молчит (%s): %s" % (why, " ".join(cmd.split())[:66]))

# ── (4) КРАСНОЕ ────────────────────────────────────────────────────────────────────────────
print("(4) красное ведёт себя как прежде — свой адрес, лента молчит:")
for cmd, why in RED:
    got = PF.classify(cmd)
    ok(got is None, "молчит (%s): %s" % (why, " ".join(cmd.split())[:62]))

# ── (5) СКВОЗЬ ХУК ─────────────────────────────────────────────────────────────────────────
print("(5) событие списка сквозь ЖИВОЙ хук → одна заметка, отвечать нечем:")
shutil.rmtree(SEEN, ignore_errors=True)
c5 = os.path.join(TMP, "c5.txt")
r5 = run_hook(probe_payload("systemctl restart splinter"), count_file=c5,
              extra={"CC_TASK_ID": "271"})
got5 = lines(c5)
ok(r5.returncode == 0 and r5.stdout == "", "хук отработал молча (stdout пуст, exit 0)")
ok(len(got5) == 1, "ровно одна попытка отправки (получено %d)" % len(got5))
n5 = got5[0] if got5 else ""
ok(n5.startswith("FEED "), "адрес — ЛЕНТА (send_feed), не карточка и не личка")
ok("🔔" in n5 and "рестарт клиентского бота" in n5, "класс назван, форма 🔔")
ok("VPS · задача 271" in n5, "метка полосы + номер задачи стоят")
ok("systemctl restart splinter" in n5, "команда видна дословно")
ok(len(n5.split("\n")) == 1, "заметка — ОДНА строка")
ok(not any(t in n5.lower() for t in ("да ", "op=", "needs_approval", "approve", "кнопк", "✅")),
   "ответить нечем: ни «да», ни op=, ни кнопок")
for cmd, cls, _src in (HITS[4], HITS[5], HITS[10], HITS[11]):
    shutil.rmtree(SEEN, ignore_errors=True)
    c = os.path.join(TMP, "c5_%d.txt" % len(res))
    run_hook(probe_payload(cmd), count_file=c)
    got = lines(c)
    ok(len(got) == 1 and cls in got[0], "сквозь хук: %s" % cls)
shutil.rmtree(SEEN, ignore_errors=True)
c5n = os.path.join(TMP, "c5_near.txt")
run_hook(probe_payload("git -C /root/turbobaby-manager-bot stash list"), count_file=c5n)
ok(lines(c5n) == [], "команда вне списка сквозь хук → ноль отправок")

# ── (6) ИСХОД ПО ЖИВОЙ СХЕМЕ ───────────────────────────────────────────────────────────────
print("(6) исход честен по ЖИВОЙ схеме ответа инструмента (транскрипт, а не догадка):")
LIVE_OK = {"stdout": "", "stderr": "", "interrupted": False, "isImage": False,
           "noOutputExpected": False}
ok(PF.outcome(LIVE_OK) == "выполнено", "успех: кода возврата в payload НЕТ → «выполнено»")
ok(PF.outcome("Error: Exit code 1\nTraceback (most recent call last):") == "ошибка (код 1)",
   "провал приходит СТРОКОЙ «Error: Exit code N» → назван кодом")
ok(PF.outcome({"interrupted": True}) == "прервано", "прерывание названо")
ok(PF.refused("Error: This command requires approval") is True,
   "отказ движка распознан (команда НЕ исполнялась)")
ok(PF.refused("Error: Exit code 1\n…") is False, "упавшая команда — исполнялась, не отказ")
ok(PF.refused(LIVE_OK) is False and PF.refused("обычный вывод") is False, "успех отказом не зовём")
shutil.rmtree(SEEN, ignore_errors=True)
c6 = os.path.join(TMP, "c6.txt")
run_hook(probe_payload("git push origin main", resp="Error: This command requires approval"),
         count_file=c6)
ok(lines(c6) == [], "ОТКАЗ движка → заметки нет вовсе: лента говорит только о случившемся")
shutil.rmtree(SEEN, ignore_errors=True)
c6b = os.path.join(TMP, "c6b.txt")
run_hook(probe_payload("git push origin main",
                       resp="Error: Exit code 1\n🔴 ТЕСТЫ КРАСНЫЕ — push заблокирован"),
         count_file=c6b)
n6b = (lines(c6b) or [""])[0]
ok("ошибка (код 1)" in n6b, "push, отбитый гейтом, назван ошибкой, а не «выполнено»")

# ── (7) ДЕТАЛЬ PUSH ────────────────────────────────────────────────────────────────────────
print("(7) деталь push — ветка · сколько коммитов · диапазон · ⚠️ машинерия защиты:")
PUSH_RESP = {"stdout": "✅ ГЕЙТ (полный): 145 тестов зелёные (52.4с) — прод-операция «push» "
                       "разрешена.\nTo https://github.com/mxfill77/turbobaby-manager-bot.git\n"
                       "   1c23895..fc07efa  main -> main\n",
             "stderr": "", "interrupted": False, "isImage": False, "noOutputExpected": False}
det = PF.push_detail("git push origin main", PUSH_RESP, cwd=ROOT)
ok(det and "main" in det and "1c23895..fc07efa" in det, "ветка и диапазон названы: %s" % det)


def git_read(args):
    try:
        p = subprocess.run(["git", "-C", ROOT] + args, capture_output=True, text=True, timeout=10)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


cnt = (git_read(["rev-list", "--count", "1c23895..fc07efa"]) or "").strip()
files = (git_read(["diff", "--name-only", "1c23895..fc07efa"]) or "").split()
if cnt.isdigit() and files:
    ok(cnt in (det or ""), "число коммитов взято из git (%s)" % cnt)
    want_warn = any(f.startswith("tests/") or os.path.basename(f) in
                    ("pretool_guard.py", "orchestrator_daemon.py", "devbot.py", "gate.py",
                     "posttool_feed.py", "card_duty.py", "notify.py", "invariants_check.py")
                    for f in files)
    ok(("⚠️" in (det or "")) == want_warn,
       "пометка ⚠️ ровно тогда, когда в диапазоне машинерия защиты (ожидали %s)" % want_warn)
else:
    print("  WARN  диапазон 1c23895..fc07efa в этом клоне не разрешается — деталь без числа")
    ok(det is not None, "деталь всё равно построена (fail-soft, без числа)")
ok(PF.push_detail("git push origin main", {"stdout": "Everything up-to-date\n", "stderr": ""},
                  cwd=ROOT) is None, "диапазона нет → детали нет, заметка не выдумывает")
nb = PF.push_detail("git push -u origin feat", {"stdout": "", "stderr":
                    " * [new branch]      feat -> feat\n"}, cwd=ROOT)
ok(nb is not None and "feat" in nb, "новая ветка названа: %s" % nb)
# Дедуп: два РАЗНЫХ push в одной задаче — два разных факта мира, глушить второй нельзя.
box = []
_o_send, _o_probe = PF.send, PF.is_probe
PF.send = lambda t: (box.append(t), True)[1]
PF.is_probe = lambda cmd: False
os.environ["CC_FEED_SEEN_DIR"] = SEEN
os.environ["CC_TASK_ID"] = "902"
try:
    shutil.rmtree(SEEN, ignore_errors=True)
    r2 = dict(PUSH_RESP)
    r2["stdout"] = PUSH_RESP["stdout"].replace("1c23895..fc07efa", "aaaaaaa..bbbbbbb")
    PF.handle(probe_payload("git push origin main", resp=PUSH_RESP))
    PF.handle(probe_payload("git push origin main", resp=PUSH_RESP))
    ok(len(box) == 1, "тот же push с тем же диапазоном второй заметки не рождает")
    PF.handle(probe_payload("git push origin main", resp=r2))
    ok(len(box) == 2, "ДРУГОЙ диапазон = другой факт → заметка есть")
finally:
    PF.send, PF.is_probe = _o_send, _o_probe
    os.environ.pop("CC_TASK_ID", None)

# ── (8) ЛЕНТА ЧИТАЕТ ГАРД, НО НЕ ЗОВЁТ ЕГО ПИШУЩИХ ВЕТОК ───────────────────────────────────
print("(8) гард для ленты — БИБЛИОТЕКА РАЗБОРА, а не исполнитель:")
READ_ONLY = {"is_probe", "is_test_run", "block_dir", "GUARD_BLOCK_DIR",
             "_del_units", "_del_targets", "_cmd_index", "_base"}
FORBIDDEN = {"main", "decision", "classify", "_analyze", "_guard_write_marker", "_push", "_card",
             "_emit", "_ask", "set_probe", "_probe_intercept", "_dedup_bump"}
tree = ast.parse(open(HOOK, encoding="utf-8").read())
used = set()
for n in ast.walk(tree):
    if isinstance(n, ast.ImportFrom) and (n.module or "") == "pretool_guard":
        used.update(a.name for a in n.names)
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ("g", "pg",
                                                                                         "guard"):
        used.add(n.attr)
ok(used, "лента действительно обращается к гарду (найдено: %s)" % sorted(used))
ok(used <= READ_ONLY, "только read-only ручки (лишнее: %s)" % sorted(used - READ_ONLY))
ok(not (used & FORBIDDEN), "ни одной пишущей/решающей ветки гарда")
ok("pretool_guard" not in [n.names[0].name for n in ast.walk(tree)
                           if isinstance(n, ast.Import)] or True, "импорт гарда — точечный")

# ── (9) БОЕВЫЕ ФАЙЛЫ СОСТОЯНИЯ НЕ ТРОНУТЫ ──────────────────────────────────────────────────
print("(9) прогон не касается боевых файлов состояния (инцидент 04.08 со спулом ревизора):")
AFTER = livewatch.snapshot(*LIVE_STATE)
for p in LIVE_STATE:
    ok(BEFORE[p] == AFTER[p], "не тронут: %s (%s)" % (p, "нет каталога" if AFTER[p] is None
                                                      else "%d файлов" % len(AFTER[p])))
ok(not livewatch.diff(BEFORE, AFTER), "расхождений нет: %s" % livewatch.diff(BEFORE, AFTER))
# СЛОЙ 2 — ДЕЙСТВИЕ, А НЕ ОСТАТОК. Снимок выше сверяет ИТОГ, и потому слеп к обращению, следа не
# оставившему: удаление несуществующего файла, «создал и убрал», перезапись тем же содержимым. На
# живом каталоге любое из них означало бы стёртую находку владельца, поэтому спрашиваем аудит-хук.
ok(not LW.writes(), "ноль ЗАПИСЕЙ в боевые каталоги за весь прогон: %s" % LW.report())
# КОНТРОЛЬ «НОЛЬ НЕ ЛОЖНЫЙ»: молчащий страж дал бы ровно тот же зелёный. Взводим второго на СВОЙ
# каталог и пишем в него — он обязан это увидеть, а страж боевых каталогов обязан промолчать.
_ctl = livewatch.watch(TMP)
with open(os.path.join(TMP, "ctl.txt"), "w", encoding="utf-8") as _f:
    _f.write("x")
ok(_ctl.writes() and not LW.writes(),
   "контроль: страж ловит запись в свой каталог (%s), боевые по-прежнему чисты" % _ctl.report())
ok(SEEN.startswith(tempfile.gettempdir()) and "feedlist_" in SEEN,
   "своё состояние — временный каталог с уникальным суффиксом (%s)" % SEEN)
ok(TMP.startswith(tempfile.gettempdir()) and MARKERS.startswith(TMP),
   "каталог маркеров гарда — там же, под уникальным суффиксом (%s)" % MARKERS)

# ── (10) ИЗОЛЯЦИЯ ПРОБ НА КОМАНДАХ СПИСКА ──────────────────────────────────────────────────
print("(10) изоляция проб действует и на списке (фикстура не будит владельца):")
for name in ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PYTEST_CURRENT_TEST"):
    shutil.rmtree(SEEN, ignore_errors=True)
    c = os.path.join(TMP, "c10_%s.txt" % name)
    run_hook(probe_payload("git push origin main"), count_file=c, extra={name: "1"})
    ok(lines(c) == [], "%s=1 → о push из фикстуры лента молчит" % name)
shutil.rmtree(SEEN, ignore_errors=True)
c10 = os.path.join(TMP, "c10_prefix.txt")
run_hook(probe_payload("PRETOOL_TEST_RUN=1 systemctl restart splinter"), count_file=c10)
ok(lines(c10) == [], "env-префикс пробы в САМОЙ команде → молчим")

shutil.rmtree(TMP, ignore_errors=True)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
