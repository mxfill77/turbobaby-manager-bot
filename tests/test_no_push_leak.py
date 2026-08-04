"""Регресс утечек пушей (01–05.07): тестовые красные карточки НЕ летят Филиппу в личку.
Слои: (A) gate.py ставит PRETOOL_NOPUSH=1 подпроцессам тестов; (B/C) notify.notify мутится по
PRETOOL_NOPUSH=1 и диверсится в мок-счётчик NOTIFY_COUNT_FILE (до токена/сети); (D) pretool_guard
🧪-карточку (scratchpad/_test/_dryrun) НЕ пушит вовсе, боевую — пушит (счётчик ловит = канал жив);
(E) ПОЛНЫЙ гейт (gate.py → фейк-тест → pretool_guard на красной фикстуре) → НОЛЬ исходящих пушей;
(F) ЛЕНТА (posttool_feed, третий канал к владельцу с 03.08.2026) под теми же признаками — ноль.
(G) БОЕВЫЕ КАТАЛОГИ СОСТОЯНИЯ не тронуты (04.08.2026): аудит-хук ловит действие, снимок — остаток;
    состояние фикстур живёт во временных каталогах с уникальным суффиксом и убирается за собой.
Сеть НЕ дёргается нигде: все subprocess-дети получают NOTIFY_COUNT_FILE (дивёрсия вместо отправки)."""
import os
import sys
import json
import shutil
import tempfile
import subprocess

ROOT = "/root/turbobaby-manager-bot"
PY = os.path.join(ROOT, "venv", "bin", "python3")
GATE = os.path.join(ROOT, "gate.py")
PRETOOL = os.path.join(ROOT, "pretool_guard.py")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

# Страж боевых каталогов состояния (04.08.2026): секция (G) сверяет, что за прогон в них ничего
# не записано и не стёрто. Взводится ДО импортов, снимок — вторым слоем (подпроцессы).
LIVE_STATE = ("/tmp/cc_feed_seen", "/tmp/cc_feed_seen_test", "/tmp/cc_guard_block")
import livewatch
LW = livewatch.watch(*LIVE_STATE)
BEFORE_LIVE = livewatch.snapshot(*LIVE_STATE)

res = []
def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c

_MARKERS = tempfile.mkdtemp(prefix="nopushleak_mk_")   # канал 2 (маркер демону) — всегда сюда
# Номер задачи в фикстуре — ЗАВЕДОМО НЕ ЖИВОЙ. Каталог подменён, и этого довольно для изоляции,
# но имя файла маркера строится из CC_TASK_ID, а прогон наследует его от ЖИВОЙ задачи демона:
# артефакт фикстуры не должен называться её номером — так его нельзя спутать с настоящим.
_FIXTURE_TID = "999404"

def child_env(count_file=None, keep_nopush=False):
    """env для подпроцессов: NOTIFY_COUNT_FILE = мок-счётчик (никакой сети даже при регрессии);
    признаки тест-прогона убираем (проверяем, что защищаемый слой ставит их САМ), keep_nopush —
    оставить PRETOOL_NOPUSH.

    Убираем ВСЕ ЧЕТЫРЕ имени, а не одно: с 01.08.2026 пуш глушит единый isolated(), который читает
    их все, — оставшийся ORCH_TEST_MODE (его ставит подпроцессам сам гейт) делал «боевую фикстуру»
    тестовой, и слой (D) мерил не то, что называл.

    PRETOOL_BLOCK_DIR ставится ВСЕГДА: канал владельца не один. Урок 02.08.2026 (задача 181) —
    снятый признак открывал не только пуш, но и МАРКЕР: хук писал боевой
    /tmp/cc_guard_block/<CC_TASK_ID>.json с номером ЖИВОЙ задачи, демон делал из фикстуры красную
    карточку владельцу. Мок канала 1 (счётчик) без мока канала 2 неполон."""
    e = dict(os.environ)
    for k in ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PYTEST_CURRENT_TEST"):
        e.pop(k, None)
    if not keep_nopush:
        e.pop("PRETOOL_NOPUSH", None)
    e.pop("NOTIFY_COUNT_FILE", None)
    e["PRETOOL_BLOCK_DIR"] = _MARKERS
    e["CC_TASK_ID"] = _FIXTURE_TID         # см. выше: артефакт фикстуры не носит живого номера
    if count_file:
        e["NOTIFY_COUNT_FILE"] = count_file
    return e

def count_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return len([ln for ln in f if ln.strip()])
    except OSError:
        return 0

TMP = tempfile.mkdtemp(prefix="nopushleak_")

# ── (A) gate.run_tests подсовывает подпроцессам тестов PRETOOL_NOPUSH=1 ──
import gate
print("(A) gate.run_tests → env тестов:")
captured = {}
class _R:
    returncode = 0
_orig_run, _orig_glob = gate.subprocess.run, gate.glob.glob
gate.subprocess.run = lambda args, **kw: (captured.update(env=kw.get("env") or {}), _R())[1]
gate.glob.glob = lambda pat: [os.path.join(TMP, "test_x.py")]
try:
    failed, total, _dt = gate.run_tests()
finally:
    gate.subprocess.run, gate.glob.glob = _orig_run, _orig_glob
ok(total == 1 and not failed, "мок-прогон: 1 тест, зелёный")
ok(captured.get("env", {}).get("PRETOOL_NOPUSH") == "1", "env подпроцесса теста несёт PRETOOL_NOPUSH=1")
# PYTHONPATH с 04.08.2026 СОБИРАЕТСЯ (ROOT + tests/ + унаследованное), а не равен ROOT: прежнее
# равенство роняло наблюдатель вызывающего. Договор тот же и проверяется по СУЩЕСТВУ — ROOT первым.
_pp = (captured.get("env", {}).get("PYTHONPATH") or "").split(os.pathsep)
ok(_pp[:1] == [ROOT], "PYTHONPATH сохранён (import splinter из tests/ — ROOT первым): %r" % (_pp[:2],))

# ── (B) notify: PRETOOL_NOPUSH=1 → мут, сеть/токен не трогаются ──
import notify as N
print("(B) notify мутится по PRETOOL_NOPUSH=1:")
sent = []
N._send_message = lambda tok, txt: (sent.append(txt), (True, 1))[1]
N._get_token = lambda: "TKN"
_saved = {k: os.environ.pop(k, None) for k in ("PRETOOL_NOPUSH", "NOTIFY_COUNT_FILE")}
os.environ["PRETOOL_NOPUSH"] = "1"
r = N.notify("🔴 тестовая карточка")
ok(r is True and sent == [], "notify() под мутом: True, отправки НЕТ")
N.clear_notifications()
ok(sent == [], "clear_notifications под мутом: сеть не дёрнута")
os.environ.pop("PRETOOL_NOPUSH", None)

# ── (C) notify: NOTIFY_COUNT_FILE → попытка учтена в счётчик, отправки нет ──
print("(C) notify диверсится в мок-счётчик:")
cnt_c = os.path.join(TMP, "cnt_c.txt")
os.environ["NOTIFY_COUNT_FILE"] = cnt_c
r = N.notify("🔴 попытка пуша")
os.environ.pop("NOTIFY_COUNT_FILE", None)
ok(r is True and sent == [], "отправки НЕТ (дивёрсия до токена/сети)")
ok(count_lines(cnt_c) == 1, "попытка учтена в счётчике (1 строка)")

# ── (D) pretool_guard: 🧪-карточка не пушится, боевая — пушится (счётчик жив) ──
print("(D) pretool_guard: 🧪 скип пуша / боевой пуш ловится счётчиком:")
fx_test = os.path.join(TMP, "fx_red_test.py")      # _test в имени → 🧪-карточка
fx_live = os.path.join(TMP, "fx_red_live.py")      # боевое имя → карточка с пушем
# Фикстура несёт ЖИВОЙ вызов Bridge с ОБЪЕКТОМ и ЧИСЛОМ: с 28.07.2026 карточка без них не
# рождается вовсе (минимум карточки, tests/test_guard_card_min.py), и «пуш пойман счётчиком»
# проверялся бы на несуществующей карточке. Литерал операции — конкатенацией (иначе гард
# краснеет на самом файле теста).
# СМЕНА ВЕЗУЩЕЙ ФИКСТУРЫ (01.08.2026): тест про УТЕЧКУ ПУШЕЙ, а не про доктрину живых таблиц, и
# ему нужна карточка С КНОПКОЙ (у жёсткого блока пуша нет по построению — мерить было бы нечего).
# Прежний носитель `set_fleet_oil(number='6789', oil_km=27000)` с 01.08 даёт жёсткий блок (запись
# в живые таблицы по сущности без пометки ТЕСТ), см. tests/test_probe_isolation.py. Денежная
# проводка несёт объект и число, карточка живёт, ужесточению деньги намеренно не подлежат.
MONEY_CALL = "add_trans" + "action(group='Наличка', amount=-500)"
RED_BODY = "# фикстура регресса\nbridge." + MONEY_CALL + "\n"
for p in (fx_test, fx_live):
    with open(p, "w", encoding="utf-8") as f:
        f.write(RED_BODY)

def run_pretool(script, count_file):
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": PY + " " + script}, "cwd": ROOT})
    return subprocess.run([PY, PRETOOL], input=payload, capture_output=True, text=True,
                          timeout=60, env=child_env(count_file=count_file))

cnt_d1 = os.path.join(TMP, "cnt_d1.txt")
r1 = run_pretool(fx_test, cnt_d1)
ok(r1.returncode == 0 and '"ask"' in r1.stdout, "🧪-фикстура: решение ask (классификация не изменилась)")
ok("🧪" in r1.stdout, "карточка помечена 🧪")
ok(count_lines(cnt_d1) == 0, "🧪-карточка: НОЛЬ попыток пуша (скип до notify)")

cnt_d2 = os.path.join(TMP, "cnt_d2.txt")
r2 = run_pretool(fx_live, cnt_d2)
ok(r2.returncode == 0 and '"ask"' in r2.stdout and "🧪" not in r2.stdout,
   "боевая фикстура: ask без 🧪-пометки")
ok(count_lines(cnt_d2) == 1, "боевой пуш ПОЙМАН счётчиком (канал мок-счётчика жив, ноль — не ложный)")

# ── (E) ПОЛНЫЙ ГЕЙТ → ноль исходящих пушей ──
print("(E) полный гейт (gate.py → фейк-тест → pretool_guard на красной фикстуре) → 0 пушей:")
fake_tests = os.path.join(TMP, "faketests")
os.makedirs(fake_tests, exist_ok=True)
with open(os.path.join(fake_tests, "test_fake_leak.py"), "w", encoding="utf-8") as f:
    f.write(
        "import json, os, subprocess, sys\n"
        "if os.environ.get('PRETOOL_NOPUSH') != '1':\n"
        "    print('FAIL: гейт не проставил PRETOOL_NOPUSH=1'); sys.exit(1)\n"
        "payload = json.dumps({'tool_name': 'Bash',\n"
        "    'tool_input': {'command': %r + ' ' + %r}, 'cwd': %r})\n"
        "r = subprocess.run([%r, %r], input=payload, capture_output=True, text=True, timeout=60)\n"
        "sys.exit(0 if r.returncode == 0 else 1)\n" % (PY, fx_test, ROOT, PY, PRETOOL))
cnt_e = os.path.join(TMP, "cnt_e.txt")
env_e = child_env(count_file=cnt_e)
env_e["GATE_TESTS_DIR"] = fake_tests
rg = subprocess.run([PY, GATE], cwd=ROOT, capture_output=True, text=True, timeout=180, env=env_e)
ok(rg.returncode == 0 and "разрешена" in rg.stdout, "гейт зелёный на фейк-наборе (exit 0)")
ok(count_lines(cnt_e) == 0, "ПОЛНЫЙ ГЕЙТ: ноль исходящих пушей (мок-счётчик пуст)")

# ── (F) ЛЕНТА (третье состояние, 03.08.2026) — третий канал к владельцу, та же изоляция ──
# Заметка PostToolUse не может дать прав (у события нет поля разрешения), но УТЕЧЬ она может ровно
# как карточка: фикстура, рождающая событие ленты под гейтом, писала бы владельцу в канал «Лента».
# Ручка изоляции ОБЩАЯ с гардом (pretool_guard.is_probe), отправка — общая ветка мута notify.
print("(F) канал ленты: под признаками тест-прогона — ноль исходящих:")
FEED = os.path.join(ROOT, "posttool_feed.py")
FEED_PAYLOAD = json.dumps({"tool_name": "Bash", "cwd": ROOT,
                           "tool_input": {"command": "CC_FEED_PROBE=1 echo фикстура ленты"},
                           "tool_response": {"stdout": ""}})

def run_feed(count_file, seen, keep_nopush):
    e = child_env(count_file=count_file, keep_nopush=keep_nopush)
    if keep_nopush:
        e["ORCH_TEST_MODE"] = "1"          # ровно то, что ставит gate.run_tests подпроцессам
    e["CC_FEED_SEEN_DIR"] = seen           # каталог ленты подставляем ВСЕГДА (урок задачи 181)
    e["PC_DEV_TOPIC_ID"] = "424242"        # адрес-заглушка ленты: боевую тему из .env не трогаем
    return subprocess.run([PY, FEED], input=FEED_PAYLOAD, capture_output=True, text=True,
                          timeout=60, env=e)

cnt_f = os.path.join(TMP, "cnt_f.txt")
rf = run_feed(cnt_f, os.path.join(TMP, "seen_gate"), keep_nopush=True)
ok(rf.returncode == 0 and rf.stdout == "", "хук ленты: exit 0 и ни байта в stdout")
ok(count_lines(cnt_f) == 0, "ЛЕНТА под гейтом: ноль исходящих")
cnt_f2 = os.path.join(TMP, "cnt_f2.txt")
run_feed(cnt_f2, os.path.join(TMP, "seen_live"), keep_nopush=False)
ok(count_lines(cnt_f2) == 1, "контроль: без признаков теста заметка уходит (ноль выше не ложный)")

# ── (G) БОЕВЫЕ КАТАЛОГИ СОСТОЯНИЯ НЕ ТРОНУТЫ ──
# Тест про утечку к владельцу, и каталоги состояния — тот же адрес: стёртый маркер = карточка,
# которой владелец не увидит (инцидент 04.08.2026 со спулом). Аудит-хук ловит ДЕЙСТВИЕ в этом
# процессе, снимок — ОСТАТОК, включая след подпроцессов (гард, лента, гейт).
print("(G) боевые каталоги состояния за прогон не изменены:")
ok(not LW.writes(), "ноль записей/удалений в боевых каталогах: %s" % LW.report())
_dlive = livewatch.diff(BEFORE_LIVE, livewatch.snapshot(*LIVE_STATE))
ok(not _dlive, "снимок до/после совпал (подпроцессы тоже): %s" % _dlive)
ok(_MARKERS.startswith(tempfile.gettempdir()) and "nopushleak_mk_" in _MARKERS,
   "каталог маркеров фикстур — временный, с уникальным суффиксом (%s)" % _MARKERS)

for k, v in _saved.items():
    if v is not None:
        os.environ[k] = v
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(_MARKERS, ignore_errors=True)   # прежде оставался в /tmp после КАЖДОГО прогона гейта

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
