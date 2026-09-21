"""Прогон сьютов, затронутых заходом «ноль не от хранилища» — ВНЕ гейта, перед push.

Не тест: служебный прогонщик (имя с `_` — gate его не цепляет, глоб `tests/test_*.py`).
Каждый сьют — отдельным процессом, как его гоняет гейт, с `PRETOOL_NOPUSH=1`.
"""
import os
import sys
import subprocess

REPO = "/root/turbobaby-manager-bot"
SUITES = [
    "test_money_amount", "test_money_amount_mutants",      # свои
    "test_balance_set_fact", "test_cash_balance_fact",     # соседи по классу кассы
    "test_deposit_link", "test_llm_loud_fail",             # соседи по _record_transaction
    "test_post_receipt_no_resend", "test_undo_last",
    "test_invariants_check",                               # страж чистоты нового модуля
]

env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
bad = []
for name in SUITES:
    p = subprocess.run([os.path.join(REPO, "venv/bin/python3"),
                        os.path.join(REPO, "tests", name + ".py")],
                       capture_output=True, text=True, env=env, cwd=REPO)
    tail = [l for l in p.stdout.strip().splitlines() if l.strip()]
    print(f"{name:32s} exit={p.returncode}  {tail[-1] if tail else '(нет вывода)'}")
    if p.returncode != 0:
        bad.append(name)
        print("\n".join(l for l in p.stdout.splitlines() if "FAIL" in l)[:2000])
        print(p.stderr[-1500:])

print("\nКРАСНЫХ: %d из %d" % (len(bad), len(SUITES)))
sys.exit(1 if bad else 0)
