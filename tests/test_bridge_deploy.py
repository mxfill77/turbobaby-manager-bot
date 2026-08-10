"""test_bridge_deploy.py — Golden-тесты оранжевого цикла clasp redeploy (§7 шаг 2, 15.07.2026).

Покрывает:
  - happy path: гейт+харнессы+redeploy+смок зелёные → exit 0, DONE в лог
  - блок на гейте → exit 2, clasp не вызывается
  - блок на Node-харнессе → exit 2, clasp не вызывается
  - сбой redeploy → exit 1, алерт, смок не вызывается
  - GOLDEN автооткат:
      ping упал → rollback с точными args ["clasp", "redeploy", PROD_ID, "-V", "66"]
      delivery_zones_get упал → rollback с -V
      пустые зоны → rollback
      rollback выполнен → exit 1, алерт 🟡 с номером версии
      rollback тоже упал → exit 1, алерт 🔴 «КРИТИЧНО»
      версия неизвестна → rollback НЕ вызывается, алерт «ОТКАТ НЕВОЗМОЖЕН»
  - rollback всегда использует только PROD_ID
  - time.sleep вызывается после redeploy (прогрев GAS)
  - PROD_ID не мутирован (соответствует CLAUDE.md)

PRETOOL_NOPUSH: _alert мокируется → нет живых пушей Филиппу.
"""
import contextlib
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import bridge_deploy
PROD_ID = bridge_deploy.PROD_ID


# ──────────────────────────── вспомогательные ────────────────────────────────

@contextlib.contextmanager
def _build_dir():
    """Годный каталог сборки захода: существует и несёт настройки проекта.

    Цели по умолчанию у выкладки нет (10.08.2026), поэтому каждый прогон цикла называет
    каталог явно. Каталог НАСТОЯЩИЙ, не мок: годность судится живыми os-вызовами.
    """
    with tempfile.TemporaryDirectory(prefix="tb_bridge_build_") as d:
        with open(os.path.join(d, bridge_deploy.CLASP_SETTINGS), "w") as fh:
            fh.write('{"scriptId":"test"}')
        yield d

def _client_ok(zones=16):
    c = MagicMock()
    c.ping.return_value = {"ok": True}
    c.delivery_zones_get.return_value = {
        "ok": True, "data": {"zones": [{"name": f"z{i}"} for i in range(1, zones + 1)]},
    }
    return c


def _client_ping_fail():
    c = MagicMock()
    c.ping.return_value = {"ok": False, "error": "smoke_test_forced_fail"}
    return c


def _client_zones_fail():
    c = MagicMock()
    c.ping.return_value = {"ok": True}
    c.delivery_zones_get.return_value = {"ok": False, "error": "zones_test_fail"}
    return c


def _client_zones_empty():
    c = MagicMock()
    c.ping.return_value = {"ok": True}
    c.delivery_zones_get.return_value = {"ok": True, "data": {"zones": []}}
    return c


def _base_runner(gate_rc=0, harness_rc=0, version=66, redeploy_rc=0, rollback_rc=0,
                 version_in_output=True):
    """Базовый runner: конфигурируемые коды возврата для каждого шага."""
    def fake_run(args, **kw):
        args = list(args)
        if "gate.py" in str(args):
            return MagicMock(returncode=gate_rc,
                             stdout="✅ ГЕЙТ полный" if gate_rc == 0 else "❌ ТЕСТЫ КРАСНЫЕ",
                             stderr="")
        if "node" in str(args) and "harness" in str(args).lower():
            return MagicMock(returncode=harness_rc, stdout="", stderr="FAIL" if harness_rc else "")
        if args == ["clasp", "deployments"]:
            if version_in_output:
                out = f"2 Deployments.\n- {PROD_ID} @{version} - Splinter Bridge\n- AKother @HEAD\n"
            else:
                out = "- AKother @55\n"
            return MagicMock(returncode=0, stdout=out, stderr="")
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=redeploy_rc,
                             stdout="Updated." if redeploy_rc == 0 else "",
                             stderr="" if redeploy_rc == 0 else "Error: redeploy failed")
        if args[:4] == ["clasp", "redeploy", PROD_ID, "-V"]:
            return MagicMock(returncode=rollback_rc,
                             stdout=f"Rolled back to @{version}." if rollback_rc == 0 else "",
                             stderr="" if rollback_rc == 0 else "Error: rollback failed")
        return MagicMock(returncode=0, stdout="", stderr="")
    return fake_run


def _run(runner, client):
    """Запустить deploy() с моками. Возвращает (code, alert_mock, log_mock)."""
    with _build_dir() as target, \
         patch("bridge_deploy.subprocess.run", side_effect=runner), \
         patch("bridge_deploy._make_bridge_client", return_value=client), \
         patch("bridge_deploy.time.sleep"), \
         patch("bridge_deploy._alert") as mock_alert, \
         patch("bridge_deploy._log_cc") as mock_log:
        code = bridge_deploy.deploy(target=target)
    return code, mock_alert, mock_log


def _alert_texts(mock_alert):
    return [str(c) for c in mock_alert.call_args_list]


def _log_texts(mock_log):
    return [str(c) for c in mock_log.call_args_list]


# ──────────────────────────── тесты ──────────────────────────────────────────

def test_happy_path():
    """Все шаги зелёные → exit 0, DONE-лог со смок-деталью, ноль алертов."""
    code, mock_alert, mock_log = _run(_base_runner(version=66), _client_ok())
    assert code == 0, f"ожидали 0, получили {code}"
    assert mock_alert.call_count == 0, "алертов быть не должно"
    assert mock_log.call_count == 1
    log_text = mock_log.call_args[0][0]
    assert "смок ok" in log_text, f"лог: 'смок ok' не найден: {log_text}"
    assert "@66" in log_text, f"лог: '@66' не найден: {log_text}"


def test_gate_fails_blocks_deploy():
    """Гейт красный → exit 2, clasp НЕ вызывается."""
    clasp_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args):
            return MagicMock(returncode=1, stdout="❌ ТЕСТЫ КРАСНЫЕ", stderr="")
        if "clasp" in str(args):
            clasp_calls.append(args)
        return MagicMock(returncode=0, stdout="", stderr="")

    code, _, _ = _run(runner, _client_ok())
    assert code == 2, f"ожидали 2, получили {code}"
    assert not clasp_calls, f"clasp НЕ должен вызываться при красном гейте: {clasp_calls}"


def test_node_harness_fails_blocks_deploy():
    """Node-харнессы красные → exit 2, clasp НЕ вызывается."""
    clasp_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args):
            return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args):
            return MagicMock(returncode=1, stdout="", stderr="FAIL harness")
        if "clasp" in str(args):
            clasp_calls.append(args)
        return MagicMock(returncode=0, stdout="", stderr="")

    code, _, _ = _run(runner, _client_ok())
    assert code == 2, f"ожидали 2, получили {code}"
    assert not clasp_calls, f"clasp НЕ должен вызываться при красном харнессе: {clasp_calls}"


def test_redeploy_fails_no_smoke():
    """clasp redeploy упал → exit 1, алерт, смок НЕ вызывается."""
    smoke_called = []

    def runner(args, **kw):
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if list(args) == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @66\n")
        if list(args) == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=1, stdout="", stderr="Error.")
        return MagicMock(returncode=0, stdout="")

    mock_client = MagicMock()
    mock_client.ping.side_effect = lambda: smoke_called.append("ping") or {"ok": True}

    code, mock_alert, _ = _run(runner, mock_client)
    assert code == 1
    assert mock_alert.call_count >= 1, "алерт должен быть при сбое redeploy"
    assert not smoke_called, "смок не должен вызываться после сбоя redeploy"


# ═══════════════════════ GOLDEN-ТЕСТЫ АВТООТКАТ ═══════════════════════════════

def test_golden_rollback_ping_fail_exact_args():
    """GOLDEN: ping упал → rollback вызван с ТОЧНЫМИ args ["clasp","redeploy",PROD_ID,"-V","66"]."""
    rollback_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0,
                             stdout=f"2 Deployments.\n- {PROD_ID} @66 - Splinter Bridge\n")
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=0, stdout="Updated.")
        if args == ["clasp", "redeploy", PROD_ID, "-V", "66"]:
            rollback_calls.append(args[:])
            return MagicMock(returncode=0, stdout="Rolled back.")
        return MagicMock(returncode=0, stdout="")

    code, mock_alert, _ = _run(runner, _client_ping_fail())

    assert code == 1, f"exit 1 ожидался, получили {code}"
    assert rollback_calls == [["clasp", "redeploy", PROD_ID, "-V", "66"]], \
        f"GOLDEN rollback args: ожидали [... -V 66], получили {rollback_calls}"
    assert mock_alert.call_count >= 2, f"≥2 алертов (смок упал + после отката): {mock_alert.call_count}"


def test_golden_rollback_zones_get_fail():
    """GOLDEN: delivery_zones_get упал → rollback вызван с -V 66."""
    rollback_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @66\n")
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=0, stdout="Updated.")
        if args[:4] == ["clasp", "redeploy", PROD_ID, "-V"]:
            rollback_calls.append(args[:])
            return MagicMock(returncode=0, stdout="Rolled back.")
        return MagicMock(returncode=0, stdout="")

    code, _, _ = _run(runner, _client_zones_fail())

    assert code == 1
    assert len(rollback_calls) == 1, f"rollback ровно 1 раз: {rollback_calls}"
    assert rollback_calls[0] == ["clasp", "redeploy", PROD_ID, "-V", "66"], \
        f"GOLDEN rollback args: {rollback_calls[0]}"


def test_golden_rollback_zones_empty():
    """GOLDEN: delivery_zones_get вернул пустые зоны → rollback к @99."""
    rollback_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @99\n")
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=0, stdout="Updated.")
        if args[:4] == ["clasp", "redeploy", PROD_ID, "-V"]:
            rollback_calls.append(args[:])
            return MagicMock(returncode=0, stdout="Rolled back.")
        return MagicMock(returncode=0, stdout="")

    code, _, _ = _run(runner, _client_zones_empty())

    assert code == 1
    assert rollback_calls == [["clasp", "redeploy", PROD_ID, "-V", "99"]], \
        f"GOLDEN rollback к @99: {rollback_calls}"


def test_golden_rollback_success_alert_content():
    """GOLDEN: rollback выполнен → алерт содержит '🟡' и '@66'."""
    code, mock_alert, mock_log = _run(_base_runner(version=66), _client_ping_fail())

    assert code == 1
    alerts = _alert_texts(mock_alert)
    logs = _log_texts(mock_log)
    assert any("🟡" in t for t in alerts), f"GOLDEN: алерт '🟡' при успешном откате: {alerts}"
    assert any("@66" in t for t in alerts), f"GOLDEN: алерт должен содержать '@66': {alerts}"
    assert any("откат" in t.lower() and "@66" in t for t in logs), \
        f"GOLDEN: лог должен содержать 'откат' и '@66': {logs}"


def test_golden_rollback_fail_critical_alert():
    """GOLDEN: смок упал И rollback упал → алерт и лог содержат 'КРИТИЧНО'."""
    code, mock_alert, mock_log = _run(_base_runner(version=66, rollback_rc=1), _client_ping_fail())

    assert code == 1
    alerts = _alert_texts(mock_alert)
    logs = _log_texts(mock_log)
    assert any("КРИТИЧНО" in t for t in alerts), \
        f"GOLDEN: критический алерт при двойном провале: {alerts}"
    assert any("КРИТИЧНО" in t for t in logs), \
        f"GOLDEN: критический лог при двойном провале: {logs}"


def test_golden_rollback_no_prev_version():
    """GOLDEN: версия неизвестна → rollback НЕ вызывается, алерт 'ОТКАТ НЕВОЗМОЖЕН'."""
    rollback_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout="- AKother @55\n")  # PROD_ID отсутствует
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=0, stdout="Updated.")
        if args[:4] == ["clasp", "redeploy", PROD_ID, "-V"]:
            rollback_calls.append(args[:])
        return MagicMock(returncode=0, stdout="")

    code, mock_alert, _ = _run(runner, _client_ping_fail())

    assert code == 1
    assert not rollback_calls, \
        f"GOLDEN: rollback НЕ должен вызываться при неизвестной версии: {rollback_calls}"
    alerts = _alert_texts(mock_alert)
    assert any("ОТКАТ НЕВОЗМОЖЕН" in t for t in alerts), \
        f"GOLDEN: алерт должен содержать 'ОТКАТ НЕВОЗМОЖЕН': {alerts}"


def test_golden_rollback_only_prod_id():
    """GOLDEN: все redeploy-вызовы (включая rollback) используют только PROD_ID."""
    redeploy_id_calls = []

    def runner(args, **kw):
        args = list(args)
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @66\n")
        if len(args) >= 3 and args[:2] == ["clasp", "redeploy"]:
            redeploy_id_calls.append(args[2])
            return MagicMock(returncode=0, stdout="ok")
        return MagicMock(returncode=0, stdout="")

    _run(runner, _client_ping_fail())

    for dep_id in redeploy_id_calls:
        assert dep_id == PROD_ID, \
            f"GOLDEN: redeploy должен использовать только PROD_ID, получили '{dep_id}'"


def test_sleep_after_redeploy():
    """time.sleep вызывается после redeploy (прогрев GAS)."""
    sleep_calls = []

    def runner(args, **kw):
        if "gate.py" in str(args): return MagicMock(returncode=0, stdout="✅")
        if "node" in str(args): return MagicMock(returncode=0, stdout="")
        if list(args) == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @66\n")
        return MagicMock(returncode=0, stdout="")

    with _build_dir() as target, \
         patch("bridge_deploy.subprocess.run", side_effect=runner), \
         patch("bridge_deploy._make_bridge_client", return_value=_client_ok()), \
         patch("bridge_deploy.time.sleep", side_effect=lambda t: sleep_calls.append(t)), \
         patch("bridge_deploy._alert"), \
         patch("bridge_deploy._log_cc"):
        bridge_deploy.deploy(target=target)

    assert sleep_calls, "time.sleep должен вызываться после redeploy"
    assert all(s > 0 for s in sleep_calls), f"sleep > 0с: {sleep_calls}"


def test_prod_id_matches_claude_md():
    """PROD_ID совпадает с константой из CLAUDE.md (не мутирован случайной правкой)."""
    assert PROD_ID == "AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw", \
        f"PROD_ID изменён: {PROD_ID}"


def test_happy_path_log_contains_pulse():
    """Happy path: _log_cc вызывается с pulse (содержит 🟢)."""
    code, _, mock_log = _run(_base_runner(version=71), _client_ok(zones=14))
    assert code == 0
    call_kwargs = mock_log.call_args[1] if mock_log.call_args[1] else {}
    pulse_arg = call_kwargs.get("pulse") or (
        mock_log.call_args[0][1] if len(mock_log.call_args[0]) > 1 else "")
    assert "🟢" in pulse_arg, f"pulse должен содержать '🟢': {pulse_arg}"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            import traceback; traceback.print_exc()
            failed.append(name)
    print(f"\n{'ВСЕ PASS' if not failed else 'FAIL: ' + str(failed)}")
    sys.exit(0 if not failed else 1)
