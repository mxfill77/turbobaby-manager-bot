"""O3-3c часть А: col N booking_id в листе транзакций Bot Data (зеркало = bridge-gs/BotData.js).
Реальный .js гоняется node-харнессом tests/botdata_gs_harness.js с мок-листом (схема
booking_gs_harness.js). Покрытие: TX_HEADERS 14 колонок (booking_id последней, msg_id на месте —
dedup цел), appendRow с booking_id → col N заполнен, БЕЗ booking_id (старые вызовы) → col N пуст,
дострой заголовка N1 на живом 13-колоночном листе, регресс dedup/computeBalance_/voidLastTransaction."""
import json
import os
import subprocess

BOTDATA_JS = "/root/turbobaby-bridge-gs/BotData.js"
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "botdata_gs_harness.js")

_harness_cache = {}


def run_harness():
    if "res" not in _harness_cache:
        proc = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=60)
        _harness_cache["res"] = (proc.returncode, proc.stdout, proc.stderr)
    return _harness_cache["res"]


def test_botdata_js_syntax():
    proc = subprocess.run(["node", "--check", BOTDATA_JS], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_harness_all_green():
    code, out, err = run_harness()
    assert code == 0, f"харнесс красный:\nstdout={out}\nstderr={err}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 14


def test_harness_covers_key_cases():
    code, out, err = run_harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    for need in ("headers.colN", "with-id.colN", "no-id.colN-empty",
                 "header-n1.built", "dedup.duplicate", "void.ok"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


if __name__ == "__main__":
    test_botdata_js_syntax()
    print("OK: node --check BotData.js")
    test_harness_all_green()
    print("OK: харнесс — реальный BotData.js, все кейсы зелёные")
    test_harness_covers_key_cases()
    print("ВСЕ ТЕСТЫ botdata_gs ПРОШЛИ (O3-3c часть А, col N booking_id)")
