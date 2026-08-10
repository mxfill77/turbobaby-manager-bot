#!/usr/bin/env python3
"""
bridge_deploy.py — Оранжевый цикл clasp redeploy (§7 шаг 2, 15.07.2026).

ЖЁСТКИЕ УСЛОВИЯ (все или деплой не стартует):
  0. Цель выкладки названа явно и годится (см. `target_refusal`) — проверяется ПЕРВОЙ,
     до гейта и до любого обращения к clasp
  1. Только redeploy PROD_ID (hardcoded; другой deployment, create, удаление — красные навсегда)
  2. Полный гейт (gate.py) + Node-харнессы (tests/*_harness.js) зелёные
  3. После redeploy — read-only смок: ping alive + delivery_zones_get непустой
  4. Смок упал → автооткат к prev_version (-V N) + алерт Филиппу
  5. Отчёт постфактум в cc_log + пульс

ЦЕЛИ ПО УМОЛЧАНИЮ НЕТ (10.08.2026). Прежде скрипт был намертво нацелен на долгоживущую папку
`/root/turbobaby-bridge-gs`, а она 10.08.2026 обезврежена как источник выкладки: на свежем
отпечатке прод стоял @79, а папка отставала на 4 файла из 17 — заливка стёрла бы 18 функций и
5 маршрутов живого моста. Теперь каталог называется явно, а долгоживущая папка запрещена
БЕЗУСЛОВНО: запрет судит ПУТЬ, а не состояние папки, поэтому возврат в неё `.clasp.json`
(«зарядка») отказ не снимает.

delivery_zones_init и любые боевые записи — КРАСНАЯ ЗОНА, вне этого скрипта.

Запуск (из репо), каталогом сборки ЗАХОДА:
  venv/bin/python3 bridge_deploy.py /root/<каталог-сборки-захода>
  (то же можно задать переменной окружения BRIDGE_BUILD_DIR)
"""
import glob
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.join(ROOT, "tests")
PY = os.path.join(ROOT, "venv", "bin", "python3")

PROD_ID = "AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw"

# Долгоживущая папка моста. Здесь она НЕ цель выкладки, а ЗАПРЕЩЁННАЯ цель — имя нужно
# ровно для того, чтобы отказ назвал её вслух. Обезврежена 10.08.2026 (см. CLAUDE.md).
LEGACY_GS_ROOT = "/root/turbobaby-bridge-gs"
CLASP_SETTINGS = ".clasp.json"
BUILD_DIR_ENV = "BRIDGE_BUILD_DIR"

POINTER = ("выкладка только из каталога сборки захода; истина прода — bridge_prod/, "
           "см. CLAUDE.md")


# ────────────────────────── цель выкладки: годна или нет ──────────────────────

def _cli_target(argv=None, env=None):
    """Каталог сборки захода из argv[1] или BRIDGE_BUILD_DIR. None — цель не названа."""
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip()
    return (env.get(BUILD_DIR_ENV) or "").strip() or None


def target_refusal(target):
    """Причина отказа выкладывать из `target` (строка) либо None, если каталог годится.

    Fail-closed: годится ТОЛЬКО названный существующий каталог с настройками проекта,
    не лежащий в долгоживущей папке. Всё остальное — отказ.

    Запрет папки судит ПУТЬ, а не её состояние: «разряжена» она или кто-то вернул в неё
    `.clasp.json` — выкладка из долгоживущей папки запрещена одинаково. Проверка пути идёт
    ПЕРЕД проверкой существования, иначе подкаталог запрещённой папки получил бы мягкий
    отказ «не существует» и выглядел бы починимым созданием каталога.
    """
    target = (target or "").strip()
    if not target:
        return ("каталог сборки захода не назван (аргумент команды или %s) — "
                "цели по умолчанию у выкладки нет" % BUILD_DIR_ENV)

    real = os.path.realpath(target)
    legacy = os.path.realpath(LEGACY_GS_ROOT)
    if real == legacy or real.startswith(legacy + os.sep):
        return ("цель лежит в долгоживущей папке %s — она обезврежена как источник выкладки "
                "10.08.2026 (замер того дня: прод @79, папка позади на 4 файла из 17 — "
                "заливка стёрла бы 18 функций и 5 маршрутов живого моста)" % LEGACY_GS_ROOT)

    if not os.path.isdir(real):
        return "цель %s не существует или не каталог" % target
    if not os.path.isfile(os.path.join(real, CLASP_SETTINGS)):
        return ("в цели %s нет настроек проекта %s — это не каталог сборки захода"
                % (target, CLASP_SETTINGS))
    return None


# ─────────────────────────── шаги оранжевого цикла ───────────────────────────

def _gate_ok():
    """Полный прогон gate.py (не селективный). Возвращает (ok, out_str)."""
    r = subprocess.run(
        [PY, os.path.join(ROOT, "gate.py"), "--for", "clasp"],
        capture_output=True, text=True, timeout=180, cwd=ROOT,
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _node_harnesses_ok():
    """Прогнать все tests/*_harness.js. Возвращает (ok, list_of_failed)."""
    harnesses = sorted(glob.glob(os.path.join(TESTS_DIR, "*_harness.js")))
    fails = []
    for h in harnesses:
        r = subprocess.run(
            ["node", h], capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        if r.returncode != 0:
            fails.append(os.path.basename(h) + ": " + (r.stderr or r.stdout)[:120])
    return not fails, fails


def _get_current_version(target):
    """Текущая версия @N для PROD_ID через 'clasp deployments'. None если не удалось.

    `target` обязателен и без значения по умолчанию НАМЕРЕННО: у clasp-вызовов не должно
    быть каталога «по привычке» — иначе запрет папки обходится прямым зовом этой функции.
    """
    r = subprocess.run(
        ["clasp", "deployments"],
        capture_output=True, text=True, timeout=30, cwd=target,
    )
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if PROD_ID in line:
            m = re.search(r"@(\d+)", line)
            if m:
                return int(m.group(1))
    return None


def _do_redeploy(target):
    """clasp redeploy PROD_ID из каталога `target`. Возвращает (ok, out_str)."""
    r = subprocess.run(
        ["clasp", "redeploy", PROD_ID],
        capture_output=True, text=True, timeout=90, cwd=target,
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _make_bridge_client():
    """Создать BridgeClient (загружает .env). Хук-точка для тестов."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    sys.path.insert(0, ROOT)
    from bridge_client import BridgeClient
    return BridgeClient(timeout=30)


def _smoke_ok():
    """Read-only смок: ping alive + delivery_zones_get непустой. Возвращает (ok, detail)."""
    try:
        c = _make_bridge_client()
        p = c.ping()
        if not p.get("ok"):
            return False, f"ping не ok: {p.get('error', str(p))}"
        z = c.delivery_zones_get()
        if not z.get("ok"):
            return False, f"delivery_zones_get не ok: {z.get('error', str(z))}"
        zones = z.get("data", {}).get("zones", [])
        if not zones:
            return False, "delivery_zones_get: пустой список зон"
        return True, f"ping ok, {len(zones)} зон"
    except Exception as e:
        return False, f"смок-исключение: {e}"


def _do_rollback(prev_version, target):
    """Откат: clasp redeploy PROD_ID -V prev_version из каталога `target`. (ok, out_str)."""
    r = subprocess.run(
        ["clasp", "redeploy", PROD_ID, "-V", str(prev_version)],
        capture_output=True, text=True, timeout=90, cwd=target,
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


# ──────────────────────────── вспомогательные ────────────────────────────────

def _alert(text):
    """Пуш Филиппу (best-effort, не ронять основную логику)."""
    try:
        sys.path.insert(0, ROOT)
        from notify import notify
        notify(text, force=True)
    except Exception as e:
        print(f"[bridge_deploy] alert fail: {e}")


def _log_cc(text, pulse=None):
    """Запись итога в cc_log через cclog.py (best-effort)."""
    args = [PY, os.path.join(ROOT, "cclog.py"), "DONE", text]
    if pulse:
        args += ["--pulse", pulse]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=ROOT)
    except Exception as e:
        print(f"[bridge_deploy] cclog fail: {e}")


# ──────────────────────────── главный цикл ───────────────────────────────────

def deploy(target=None):
    """
    Оранжевый цикл redeploy. Возвращает exit-код:
      0 — успех (redeploy + смок пройдены)
      1 — ошибка деплоя или смока (с возможным откатом)
      2 — предварительный блок (гейт или Node-харнессы красные)
      3 — цель выкладки не годится (проверяется ПЕРВОЙ, до гейта и до clasp)
    """
    print("=== bridge_deploy: оранжевый цикл clasp redeploy ===")

    # [1/6] Цель выкладки — раньше всего: отказ не должен стоить 3 минут гейта,
    # а тем более доходить до сети. Ни одного обращения к clasp по этой ветке нет.
    if target is None:
        target = _cli_target()
    reason = target_refusal(target)
    if reason:
        print(f"⛔ ВЫКЛАДКА НЕ НАЧАТА: {reason}")
        print(f"   {POINTER}")
        return 3
    print(f"[1/6] Цель выкладки: {target} ✅")

    # [2/6] Полный гейт
    print("[2/6] gate.py (полный сьют)…")
    ok, out = _gate_ok()
    if not ok:
        print(f"❌ ГЕЙТ КРАСНЫЙ — деплой заблокирован.\n{out}")
        return 2
    print(f"✅ Гейт зелёный.\n{out}")

    # [3/6] Node-харнессы
    print("[3/6] Node-харнессы…")
    ok, fails = _node_harnesses_ok()
    if not ok:
        print(f"❌ Node-харнессы КРАСНЫЕ: {fails} — деплой заблокирован.")
        return 2
    print("✅ Node-харнессы зелёные.")

    # [4/6] Текущая версия (бэкап-точка для возможного отката)
    print("[4/6] Текущая версия деплоя…")
    prev_ver = _get_current_version(target)
    if prev_ver is None:
        print("⚠️ Не удалось определить текущую версию — продолжаю, откат ограничен.")
    else:
        print(f"📌 Текущая версия: @{prev_ver}")

    # [5/6] clasp redeploy
    print("[5/6] clasp redeploy…")
    ok, out = _do_redeploy(target)
    if not ok:
        msg = f"bridge_deploy: clasp redeploy упал — {out[:200]}"
        print(f"❌ {msg}")
        _alert(f"🔴 {msg}. Проверь Bridge вручную.")
        _log_cc(msg)
        return 1
    print(f"✅ redeploy выполнен: {out[:120]}")

    # [6/6] Смок-тест
    print("[6/6] Смок (ping + delivery_zones_get)…")
    time.sleep(3)   # GAS прогревается после деплоя
    ok, detail = _smoke_ok()
    if ok:
        _log_cc(
            f"bridge_deploy: redeploy ok, смок ok ({detail}), прежняя @{prev_ver}",
            pulse=f"🟢 bridge_deploy done, смок ok, @{prev_ver}→новая",
        )
        print(f"✅ Смок пройден: {detail}")
        print("🟢 ДЕПЛОЙ УСПЕШЕН.")
        return 0

    # Смок упал → откат
    print(f"❌ Смок УПАЛ: {detail}")
    if prev_ver is None:
        msg = f"bridge_deploy: смок упал ({detail}), версия неизвестна — ОТКАТ НЕВОЗМОЖЕН"
        _alert(f"🔴 {msg}. Ручная проверка Bridge!")
        _log_cc(msg, pulse="🔴 bridge_deploy: смок упал, ОТКАТ НЕВОЗМОЖЕН — ручная проверка")
        return 1

    print(f"🔄 Откат к @{prev_ver}…")
    _alert(f"🟡 bridge_deploy: смок упал ({detail}), откат к @{prev_ver}…")
    rok, rout = _do_rollback(prev_ver, target)
    if rok:
        msg = f"bridge_deploy: смок упал ({detail}), откат к @{prev_ver} — OK"
        print(f"✅ Откат выполнен: {rout[:80]}")
        _alert(f"🟡 {msg}. Проверь Bridge.")
        _log_cc(msg, pulse=f"🟡 bridge_deploy: откат к @{prev_ver} выполнен")
    else:
        msg = f"bridge_deploy: КРИТИЧНО — смок упал ({detail}), откат к @{prev_ver} ТОЖЕ УПАЛ"
        print(f"❌ Откат тоже упал: {rout[:80]}")
        _alert(f"🔴 {msg}. Bridge в неопределённом состоянии! РУЧНАЯ ПРОВЕРКА НЕМЕДЛЕННО.")
        _log_cc(msg, pulse="🔴 bridge_deploy: смок+откат оба упали — РУЧНАЯ ПРОВЕРКА")
    return 1


def main():
    sys.exit(deploy())


if __name__ == "__main__":
    main()
