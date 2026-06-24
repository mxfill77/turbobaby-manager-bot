"""Мок serviceDelete_ — зеркало логики Bridge (Apps Script локально не исполнить; .gs синтаксис — node --check).
Проверяет: need_params, not_found(0), ambiguous(>1 не удаляет), ровно-1 удаляет; якорь updated_at
отличает дубль 4724 (05-31) от рабочей (06-20). + smoke враппера bridge_client.service_delete."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

CC = {"125","150","155","300","350","400","500","650","700","750","900"}
def plate(name):
    nums = [n for n in re.findall(r"\d{3,}", str(name).lower()) if n not in CC]
    return nums[-1] if nums else None

# ── ЗЕРКАЛО serviceDelete_ (BotData.js) ──
def service_delete_mirror(rows, bike, stype, anchor):
    bike = (bike or "").strip(); stype = (stype or "").strip(); anchor = (anchor or "").strip()
    if not bike or not stype or not anchor:
        return {"ok": False, "error": "need_params"}, rows
    inp = plate(bike)
    matches = []
    for i, r in enumerate(rows):
        if str(r["service_type"]).strip() != stype: continue
        same = (plate(r["bike"]) == inp) if inp else (r["bike"].lower() == bike.lower())
        if not same: continue
        if str(r["updated_at"]) == anchor:
            matches.append(i)
    if len(matches) == 0: return {"ok": False, "error": "not_found"}, rows
    if len(matches) > 1:
        return {"ok": False, "error": "ambiguous", "count": len(matches),
                "candidates": [rows[i] for i in matches]}, rows
    i = matches[0]
    snap = rows[i]
    rows2 = [r for j, r in enumerate(rows) if j != i]
    return {"ok": True, "deleted": True, "snapshot": snap}, rows2

def rows_4724():
    return [
        {"bike": "XMAX 300CC NEW BLUE-3 PHUKET 4724", "service_type": "oil", "current_km": 20316,
         "last_service_km": 20316, "next_km": 24316, "status": "ok", "updated_at": "2026-06-20T14:57:42.449Z"},
        {"bike": "XMAX 300CC NEW BLUE-3 PHUKET 4724", "service_type": "oil", "current_km": 19705,
         "last_service_km": 14900, "next_km": 18900, "status": "overdue", "updated_at": "2026-05-31T18:11:08.442Z"},
    ]

def test_need_params():
    r, _ = service_delete_mirror(rows_4724(), "4724", "oil", "")
    assert r["error"] == "need_params"
    r2, _ = service_delete_mirror(rows_4724(), "", "oil", "x")
    assert r2["error"] == "need_params"

def test_not_found():
    r, rows = service_delete_mirror(rows_4724(), "4724", "oil", "2099-01-01T00:00:00.000Z")
    assert r["error"] == "not_found"
    assert len(rows) == 2, "ничего не удалено"

def test_ambiguous_does_not_delete():
    # две строки с ОДИНАКОВЫМ updated_at → ambiguous, удаления нет
    dup = rows_4724()
    dup[1]["updated_at"] = dup[0]["updated_at"]
    r, rows = service_delete_mirror(dup, "4724", "oil", dup[0]["updated_at"])
    assert r["error"] == "ambiguous" and r["count"] == 2
    assert len(rows) == 2, "при ambiguous НЕ удаляем"

def test_exactly_one_deletes_dubl():
    r, rows = service_delete_mirror(rows_4724(), "4724", "oil", "2026-05-31T18:11:08.442Z")
    assert r["ok"] and r["deleted"]
    assert r["snapshot"]["current_km"] == 19705, "удалён именно дубль"
    assert len(rows) == 1 and rows[0]["updated_at"] == "2026-06-20T14:57:42.449Z", "рабочая цела"
    assert rows[0]["status"] == "ok"

def test_anchor_protects_working_row():
    # запрос рабочей по её якорю удалит рабочую (якорь точный); проверяем что дубль при этом остаётся
    r, rows = service_delete_mirror(rows_4724(), "4724", "oil", "2026-06-20T14:57:42.449Z")
    assert r["ok"] and r["snapshot"]["current_km"] == 20316
    assert len(rows) == 1 and rows[0]["current_km"] == 19705, "якорь бьёт ровно по одной строке"

def test_wrapper_builds_post():
    import bridge_client as BC
    cap = {}
    bc = BC.BridgeClient(url="http://x", token="t")
    bc._post = lambda action, **f: cap.update({"action": action, **f}) or {"ok": True}
    bc.service_delete("4724", "oil", "2026-05-31T18:11:08.442Z")
    assert cap["action"] == "service_delete"
    assert cap["bike"] == "4724" and cap["service_type"] == "oil" and cap["updated_at"] == "2026-05-31T18:11:08.442Z"

def test_redzone_audit():
    import bridge_client as BC
    assert "service_delete" in BC.BridgeClient._REDZONE_ACTIONS, "удаление должно логироваться в 4.1"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов service_delete")
