#!/usr/bin/env python3
"""
bridge_deploy.py — Оранжевый цикл clasp redeploy (§7 шаг 2, 15.07.2026).

ЖЁСТКИЕ УСЛОВИЯ (все или деплой не стартует):
  1. Только redeploy PROD_ID (hardcoded; другой deployment, create, удаление — красные навсегда)
  2. Полный гейт (gate.py) + Node-харнессы (tests/*_harness.js) зелёные
  3. После redeploy — read-only смок: ping alive + delivery_zones_get непустой
  4. Смок упал → автооткат к prev_version (-V N) + алерт Филиппу
  5. Отчёт постфактум в cc_log + пульс

delivery_zones_init и любые боевые записи — КРАСНАЯ ЗОНА, вне этого скрипта.

Запуск (из репо):
  venv/bin/python3 bridge_deploy.py
"""
import glob
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIDGE_ROOT = "/root/turbobaby-bridge-gs"
TESTS_DIR = os.path.join(ROOT, "tests")
PY = os.path.join(ROOT, "venv", "bin", "python3")

PROD_ID = "AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw"


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


def _get_current_version():
    """Текущая версия @N для PROD_ID через 'clasp deployments'. None если не удалось."""
    r = subprocess.run(
        ["clasp", "deployments"],
        capture_output=True, text=True, timeout=30, cwd=BRIDGE_ROOT,
    )
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if PROD_ID in line:
            m = re.search(r"@(\d+)", line)
            if m:
                return int(m.group(1))
    return None


def _do_redeploy():
    """clasp redeploy PROD_ID. Возвращает (ok, out_str)."""
    r = subprocess.run(
        ["clasp", "redeploy", PROD_ID],
        capture_output=True, text=True, timeout=90, cwd=BRIDGE_ROOT,
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


def _do_rollback(prev_version):
    """Откат: clasp redeploy PROD_ID -V prev_version. Возвращает (ok, out_str)."""
    r = subprocess.run(
        ["clasp", "redeploy", PROD_ID, "-V", str(prev_version)],
        capture_output=True, text=True, timeout=90, cwd=BRIDGE_ROOT,
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

def deploy():
    """
    Оранжевый цикл redeploy. Возвращает exit-код:
      0 — успех (redeploy + смок пройдены)
      1 — ошибка деплоя или смока (с возможным откатом)
      2 — предварительный блок (гейт или Node-харнессы красные)
    """
    print("=== bridge_deploy: оранжевый цикл clasp redeploy ===")

    # [1/5] Полный гейт
    print("[1/5] gate.py (полный сьют)…")
    ok, out = _gate_ok()
    if not ok:
        print(f"❌ ГЕЙТ КРАСНЫЙ — деплой заблокирован.\n{out}")
        return 2
    print(f"✅ Гейт зелёный.\n{out}")

    # [2/5] Node-харнессы
    print("[2/5] Node-харнессы…")
    ok, fails = _node_harnesses_ok()
    if not ok:
        print(f"❌ Node-харнессы КРАСНЫЕ: {fails} — деплой заблокирован.")
        return 2
    print("✅ Node-харнессы зелёные.")

    # [3/5] Текущая версия (бэкап-точка для возможного отката)
    print("[3/5] Текущая версия деплоя…")
    prev_ver = _get_current_version()
    if prev_ver is None:
        print("⚠️ Не удалось определить текущую версию — продолжаю, откат ограничен.")
    else:
        print(f"📌 Текущая версия: @{prev_ver}")

    # [4/5] clasp redeploy
    print("[4/5] clasp redeploy…")
    ok, out = _do_redeploy()
    if not ok:
        msg = f"bridge_deploy: clasp redeploy упал — {out[:200]}"
        print(f"❌ {msg}")
        _alert(f"🔴 {msg}. Проверь Bridge вручную.")
        _log_cc(msg)
        return 1
    print(f"✅ redeploy выполнен: {out[:120]}")

    # [5/5] Смок-тест
    print("[5/5] Смок (ping + delivery_zones_get)…")
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
    rok, rout = _do_rollback(prev_ver)
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
