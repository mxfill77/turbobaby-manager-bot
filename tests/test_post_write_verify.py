"""Пост-запись-верификация: обёртки записи в bridge_client проводят поля verify-ответа Bridge
(verify_failed / full_address / verified) НАВЕРХ без потери, и error=='verify_failed' трактуется
вызывающим кодом как ПРОВАЛ (не «done»). Заведено 05.07.2026 (шаг 4/5 родитель 68).

_post замокан (сети нет): проверяем, что обёртка НЕ теряет/не переписывает поля ответа и что
её ok-флаг совпадает с ok-флагом Bridge (на нём висит вся done/fail-логика вызывающего кода)."""
import os, sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

from bridge_client import BridgeClient


def _client(canned):
    """BridgeClient с замоканным _post: возвращает canned и запоминает (action, fields)."""
    c = BridgeClient(url="http://x", token="x")
    calls = []

    def fake_post(action, **fields):
        calls.append((action, fields))
        return dict(canned)

    c._post = fake_post
    c._calls = calls
    return c


# все пять обёрток записи + аргументы для боевого вызова
WRAPPERS = [
    ("set_caps",          lambda c: c.set_caps([{"model": "NMAX", "cap": 5000, "active": True}], confirmed=True)),
    ("toggle_cap",        lambda c: c.toggle_cap("NMAX", "off", confirmed=True)),
    ("set_fleet_oil",     lambda c: c.set_fleet_oil("1234", 12000, confirmed=True)),
    ("set_fleet_service", lambda c: c.set_fleet_service("1234", "gear", 12000, confirmed=True)),
    ("state_set",         lambda c: c.state_set(bike="NMAX 1234", status="в аренде")),
]


# ── (а) verify_failed + full_address → обёртка отдаёт ok=false и адрес ──
def test_verify_failed_passes_through_ok_false_and_address():
    for action, call in WRAPPERS:
        canned = {"ok": False, "error": "verify_failed", "full_address": "Лист1!I5"}
        c = _client(canned)
        res = call(c)
        assert res.get("ok") is False, f"{action}: verify_failed должен быть ok=false (ПРОВАЛ, не done)"
        assert res.get("error") == "verify_failed", f"{action}: error verify_failed потерян"
        assert res.get("full_address") == "Лист1!I5", f"{action}: full_address не проведён наверх"
        # обёртка должна была реально дёрнуть _post с этим экшеном
        assert c._calls and c._calls[0][0] == action, f"{action}: _post не вызван с нужным action"


# ── (б) ok + verified:true + full_address → success с адресом ──
def test_verified_true_passes_through_success_and_address():
    for action, call in WRAPPERS:
        canned = {"ok": True, "verified": True, "full_address": "Лист1!I5", "rows": 1}
        c = _client(canned)
        res = call(c)
        assert res.get("ok") is True, f"{action}: успех должен остаться ok=true"
        assert res.get("verified") is True, f"{action}: verified:true не проведён наверх"
        assert res.get("full_address") == "Лист1!I5", f"{action}: full_address не проведён наверх (успех)"


# ── verify_failed НЕ маскируется под done: ok-флаг = единственный критерий done у вызывающего ──
def test_verify_failed_is_not_treated_as_done():
    # вызывающий код (splinter) всюду делает `if res.get("ok"):` → done, иначе → провал/ретрай.
    c = _client({"ok": False, "error": "verify_failed", "full_address": "Лист1!I5"})
    res = c.set_fleet_oil("1234", 12000, confirmed=True)
    done = bool(res.get("ok"))
    assert done is False, "verify_failed НЕ должен проходить как выполненная запись"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов post_write_verify")
