"""test_bridge_deploy_gate_timeout.py — потолок полного гейта в оранжевом цикле (RC2010, 20.10.2026).

ПОВОД. `bridge_deploy.py` гнал `gate.py --for clasp` с потолком 180 с, а полный гейт 19.10 шёл 977.9 с (389 пунктов).
`subprocess.TimeoutExpired` не ловился (`sys.exit(deploy())`): маршрут падал трассировкой на шаге [2/6] — до выкладки,
то есть безопасно, но не работал вовсе. Теперь потолок взят от замера с запасом и задаётся ручкой
`BRIDGE_GATE_TIMEOUT_S`; не уложившийся (или не запустившийся) гейт — это исход НЕИЗВЕСТЕН: код 5, словами, и ДО
любого шага выкладки (ни Node-харнессов, ни clasp, ни клиента моста, ни алерта о выкладке).

Покрывает:
  (T1) умолчание потолка ≥ 1800 с и ≥ 1.8 × замера 977.9 с; именно оно уходит в subprocess.run гейта;
  (T2) гейт не уложился → код 5, ни одного вызова clasp / node / клиента моста; сообщение называет потолок и ручку;
       хвост частичного вывода (байтами, как на POSIX) печатается;
  (T3) гейт не запустился (нет интерпретатора) → код 5, тоже до выкладки;
  (T4) ручка: целое > 0 → этот потолок; мусор / ноль / минус → умолчание и пояснение вслух;
  (T5) Node-харнесс не уложился в свой потолок или нет node → код 2 (красный), clasp не вызывается;
  (T6) гейт зелёный с новым потолком → цикл идёт дальше, как прежде (код 0 при MIRROR_SYNC=0).
Ничего живого: subprocess.run, клиент моста, алерт и cc_log замоканы во ВСЕХ проверках — настоящий gate.py (он шлёт
алерты и пишет боевой журнал) здесь не запускается никогда.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ["MIRROR_SYNC"] = "0"          # предмет — шаг [2/6]; сведение зеркала судит tests/test_mirror_sync.py
os.environ.pop("BRIDGE_GATE_TIMEOUT_S", None)

import bridge_deploy  # noqa: E402
PROD_ID = bridge_deploy.PROD_ID


@contextlib.contextmanager
def _build_dir():
    with tempfile.TemporaryDirectory(prefix="tb_bridge_build_t_") as d:
        with open(os.path.join(d, bridge_deploy.CLASP_SETTINGS), "w") as fh:
            fh.write('{"scriptId":"test"}')
        yield d


@contextlib.contextmanager
def _env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _client_ok():
    c = MagicMock()
    c.ping.return_value = {"ok": True}
    c.delivery_zones_get.return_value = {"ok": True, "data": {"zones": [{"name": "z1"}]}}
    return c


class _Runner:
    """Подмена subprocess.run: гейт ведёт себя как задано, остальное записывается."""

    def __init__(self, gate="ok", harness="ok"):
        self.gate, self.harness = gate, harness
        self.calls, self.gate_timeouts = [], []

    def __call__(self, args, **kw):
        args = list(args)
        self.calls.append(args)
        s = str(args)
        if "gate.py" in s:
            self.gate_timeouts.append(kw.get("timeout"))
            if self.gate == "timeout":
                raise subprocess.TimeoutExpired(args, kw.get("timeout"), output=b"[run] test_a.py ok\n[run] test_b.py",
                                                stderr=None)
            if self.gate == "missing":
                raise FileNotFoundError(2, "No such file or directory", args[0])
            return MagicMock(returncode=0, stdout="✅ ГЕЙТ (полный): 394 тестов зелёные", stderr="")
        if args and args[0] == "node":
            if self.harness == "timeout":
                raise subprocess.TimeoutExpired(args, kw.get("timeout"))
            if self.harness == "missing":
                raise FileNotFoundError(2, "No such file or directory", "node")
            return MagicMock(returncode=0, stdout="", stderr="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout=f"- {PROD_ID} @88 - Bridge\n", stderr="")
        if args == ["clasp", "redeploy", PROD_ID]:
            return MagicMock(returncode=0, stdout="Updated.", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    def clasp(self):
        return [a for a in self.calls if a and a[0] == "clasp"]

    def node(self):
        return [a for a in self.calls if a and a[0] == "node"]


def _run(runner):
    out = io.StringIO()
    with _build_dir() as target, \
         patch("bridge_deploy.subprocess.run", side_effect=runner), \
         patch("bridge_deploy._make_bridge_client", return_value=_client_ok()) as mk, \
         patch("bridge_deploy.time.sleep"), \
         patch("bridge_deploy._alert") as al, \
         patch("bridge_deploy._log_cc") as lg, \
         contextlib.redirect_stdout(out):
        code = bridge_deploy.deploy(target=target)
    return code, out.getvalue(), mk, al, lg


def test_t1_default_covers_measured_gate():
    """(T1) Умолчание ≥ 1800 с и с запасом над замером; оно и уходит в subprocess.run гейта."""
    assert bridge_deploy.GATE_TIMEOUT_MEASURED_S == 977.9
    assert bridge_deploy.GATE_TIMEOUT_DEFAULT_S >= 1800
    assert bridge_deploy.GATE_TIMEOUT_DEFAULT_S >= 1.8 * bridge_deploy.GATE_TIMEOUT_MEASURED_S
    with _env(BRIDGE_GATE_TIMEOUT_S=None):
        assert bridge_deploy.gate_timeout() == (bridge_deploy.GATE_TIMEOUT_DEFAULT_S, None)
        r = _Runner()
        code, _, _, _, _ = _run(r)
    assert code == 0, code
    assert r.gate_timeouts == [bridge_deploy.GATE_TIMEOUT_DEFAULT_S], r.gate_timeouts


def test_t2_gate_timeout_aborts_before_any_deploy_step():
    """(T2) Гейт не уложился → код 5, ни node, ни clasp, ни клиента моста, ни алерта/журнала о выкладке."""
    with _env(BRIDGE_GATE_TIMEOUT_S=None):
        r = _Runner(gate="timeout")
        code, out, mk, al, lg = _run(r)
    assert code == 5, (code, out)
    assert r.clasp() == [], r.clasp()
    assert r.node() == [], r.node()
    assert not mk.called and not al.called and not lg.called
    assert "ИСХОД ГЕЙТА НЕИЗВЕСТЕН" in out and "выкладка НЕ начата" in out, out
    assert "%d с" % bridge_deploy.GATE_TIMEOUT_DEFAULT_S in out and "BRIDGE_GATE_TIMEOUT_S" in out, out
    assert "977.9" in out, out
    assert "test_b.py" in out, "хвост частичного вывода (байтами) обязан попасть в сообщение"
    assert "Traceback" not in out
    assert "ГЕЙТ КРАСНЫЙ" not in out and "Гейт зелёный" not in out, "неизвестный исход не зовётся ни красным, ни зелёным"


def test_t3_gate_missing_aborts_before_any_deploy_step():
    """(T3) Гейт не запустился (нет интерпретатора) → код 5 до выкладки."""
    r = _Runner(gate="missing")
    code, out, mk, _, _ = _run(r)
    assert code == 5, (code, out)
    assert r.clasp() == [] and r.node() == [] and not mk.called
    assert "гейт не запустился" in out and "FileNotFoundError" in out, out


def test_t4_knob_and_garbage():
    """(T4) Ручка: целое > 0 → этот потолок; мусор, ноль, минус → умолчание и пояснение вслух."""
    with _env(BRIDGE_GATE_TIMEOUT_S="3000"):
        assert bridge_deploy.gate_timeout() == (3000, None)
        r = _Runner()
        code, _, _, _, _ = _run(r)
        assert code == 0 and r.gate_timeouts == [3000], (code, r.gate_timeouts)
    for bad in ("abc", "0", "-5", "12.5", " "):
        with _env(BRIDGE_GATE_TIMEOUT_S=bad):
            sec, note = bridge_deploy.gate_timeout()
            assert sec == bridge_deploy.GATE_TIMEOUT_DEFAULT_S, (bad, sec)
            if bad.strip():
                assert note and "BRIDGE_GATE_TIMEOUT_S" in note, (bad, note)
                r = _Runner()
                code, out, _, _, _ = _run(r)
                assert code == 0 and r.gate_timeouts == [bridge_deploy.GATE_TIMEOUT_DEFAULT_S], (bad, code)
                assert "умолчание %d с" % bridge_deploy.GATE_TIMEOUT_DEFAULT_S in out, (bad, out)
            else:
                assert note is None, (bad, note)
    with _env(BRIDGE_GATE_TIMEOUT_S="5"):
        r = _Runner(gate="timeout")
        code, out, _, _, _ = _run(r)
        assert code == 5 and r.gate_timeouts == [5] and r.clasp() == [], (code, r.gate_timeouts)


def test_t5_harness_timeout_or_missing_node_is_red():
    """(T5) Node-харнесс не уложился / нет node → код 2, clasp не вызывается, трассировки нет."""
    for mode, word in (("timeout", "не уложился в %d с" % bridge_deploy.HARNESS_TIMEOUT_S), ("missing", "не запустился")):
        r = _Runner(harness=mode)
        code, out, mk, _, _ = _run(r)
        assert code == 2, (mode, code, out)
        assert r.clasp() == [] and not mk.called, mode
        assert word in out and "Traceback" not in out, (mode, out)


def test_t6_green_gate_continues_as_before():
    """(T6) Зелёный гейт с новым потолком — цикл прежний: харнессы, версия, redeploy, смок; код 0 (MIRROR_SYNC=0)."""
    r = _Runner()
    code, out, mk, _, _ = _run(r)
    assert code == 0, (code, out)
    assert ["clasp", "redeploy", PROD_ID] in r.calls and mk.called
    assert "потолок %d с" % bridge_deploy.GATE_TIMEOUT_DEFAULT_S in out, out


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
