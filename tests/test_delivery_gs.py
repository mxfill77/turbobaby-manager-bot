"""Зоны доставки: delivery_zones_init / delivery_zones_get в Delivery.js.
Node-харнесс tests/delivery_gs_harness.js гоняет реальный .js с мок-SpreadsheetApp.
Покрытие: константы, init (создание листа: 21 строка), идемпотентность (лист существует →
не перезаписывает), get при отсутствии листа, get после init (16 зон + 3 конфига), get
пустого листа."""
import json
import os
import subprocess

# .js берём из ЗЕРКАЛА ПРОДА `bridge_prod/` (задеплоенная версия, паспорт MIRROR.json), а не из
# рабочей папки выкладки: она обезврежена 10.08.2026 и отстаёт от прода.
DELIVERY_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge_prod", "Delivery.js")
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delivery_gs_harness.js")

_harness_cache = {}


def run_harness():
    if "res" not in _harness_cache:
        proc = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=60)
        _harness_cache["res"] = (proc.returncode, proc.stdout, proc.stderr)
    return _harness_cache["res"]


def test_delivery_js_syntax():
    proc = subprocess.run(["node", "--check", DELIVERY_JS], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_harness_all_green():
    code, out, err = run_harness()
    assert code == 0, f"харнесс красный:\nstdout={out}\nstderr={err}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 30


def test_harness_covers_key_cases():
    _code, out, _err = run_harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    required = {
        "const.zones.count",
        "init.ok",
        "init.created",
        "init.total_rows",
        "init.z1.name",
        "init.z16.name",
        "init.cfg.belt_km",
        "init.cfg.beyond",
        "idempotent.not_created",
        "idempotent.rows_untouched",
        "get.not_found.ok",
        "get.zones.count",
        "get.config.count",
        "get.cfg.belt_price",
        "get.empty.zones",
    }
    missing = required - names
    assert not missing, f"харнесс не покрывает: {missing}"
