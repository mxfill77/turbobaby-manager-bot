#!/usr/bin/env python3
"""Разовый хелпер (кусок 2 PLAN_ADAPT): изоляция легаси-тестов демона от боевого .env.
Демон при import делает load_dotenv(.env) → PLAN_ADAPT=1 протёк бы в тесты цепей и их моки
поехали бы (лишние вызовы думателя адаптации). setdefault ДО импорта перекрывает load_dotenv
(он существующие env не трогает). Идемпотентно."""
import io

FILES = [
    "tests/test_convert_loop_break.py",
    "tests/test_heartbeat.py",
    "tests/test_lane_pc.py",
    "tests/test_orchestrator_dec.py",
    "tests/test_orchestrator_other.py",
    "tests/test_orchestrator_model.py",
    "tests/test_orchestrator_stage2.py",
    "tests/test_planned_restart.py",
    "tests/test_step_selfheal.py",
]
OLD = 'os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")\n'
NEW = ('os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")\n'
       'os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)\n')

ROOT = "/root/turbobaby-manager-bot/"
for f in FILES:
    p = ROOT + f
    with io.open(p, encoding="utf-8") as fh:
        src = fh.read()
    if 'PLAN_ADAPT' in src:
        print(f"skip (уже есть): {f}")
        continue
    if OLD not in src:
        print(f"FAIL (паттерн не найден): {f}")
        continue
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(src.replace(OLD, NEW, 1))
    print(f"patched: {f}")

# test_test_noise_isolation.py — своя шапка (без BRIDGE_URL-строки)
p = ROOT + "tests/test_test_noise_isolation.py"
with io.open(p, encoding="utf-8") as fh:
    src = fh.read()
if 'PLAN_ADAPT' not in src:
    old = 'os.environ.setdefault("BRIDGE_TOKEN", "x")\n'
    if old in src:
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(src.replace(
                old,
                old + 'os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (кусок 2)\n', 1))
        print("patched: tests/test_test_noise_isolation.py")
    else:
        print("FAIL (паттерн не найден): tests/test_test_noise_isolation.py")
else:
    print("skip (уже есть): tests/test_test_noise_isolation.py")
