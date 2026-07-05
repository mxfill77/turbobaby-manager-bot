"""Регресс утечек пушей (01–05.07): тестовые красные карточки НЕ летят Филиппу в личку.
Слои: (A) gate.py ставит PRETOOL_NOPUSH=1 подпроцессам тестов; (B/C) notify.notify мутится по
PRETOOL_NOPUSH=1 и диверсится в мок-счётчик NOTIFY_COUNT_FILE (до токена/сети); (D) pretool_guard
🧪-карточку (scratchpad/_test/_dryrun) НЕ пушит вовсе, боевую — пушит (счётчик ловит = канал жив);
(E) ПОЛНЫЙ гейт (gate.py → фейк-тест → pretool_guard на красной фикстуре) → НОЛЬ исходящих пушей.
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

res = []
def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c

def child_env(count_file=None, keep_nopush=False):
    """env для подпроцессов: NOTIFY_COUNT_FILE = мок-счётчик (никакой сети даже при регрессии);
    PRETOOL_NOPUSH убираем (проверяем, что защищаемый слой ставит его САМ), keep_nopush — оставить."""
    e = dict(os.environ)
    if not keep_nopush:
        e.pop("PRETOOL_NOPUSH", None)
    e.pop("NOTIFY_COUNT_FILE", None)
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
ok(captured.get("env", {}).get("PYTHONPATH") == ROOT, "PYTHONPATH сохранён (import splinter из tests/)")

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
for p in (fx_test, fx_live):
    with open(p, "w", encoding="utf-8") as f:
        f.write("# фикстура регресса\nprint('set_fleet_oil')\n")

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

for k, v in _saved.items():
    if v is not None:
        os.environ[k] = v
shutil.rmtree(TMP, ignore_errors=True)

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
