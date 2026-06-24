"""Мок ПАКЕТ регистрации план-листов: семантика registerBrainDoc_ (мерж, не затирать) +
форма вызова bridge_client.register_brain_doc. Apps Script локально не исполняется →
тут ЗЕРКАЛО логики Bridge (мерж/overwrite/имя/in-brain) + smoke враппера. Синтаксис .gs — node --check."""
import os, sys, re, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

# ── ЗЕРКАЛО registerBrainDoc_ (ReadDocs.js) — та же логика, для проверки семантики мержа ──
NAME_RE = re.compile(r"^[a-z0-9_]+$")
def register_mirror(manifest, name, id, in_brain=True, overwrite=False):
    name = (name or "").strip(); id = (id or "").strip()
    if not name or not id: return {"ok": False, "error": "need_name_id"}
    if not NAME_RE.match(name): return {"ok": False, "error": "bad_name"}
    if manifest.get(name) and manifest[name] != id and not overwrite:
        return {"ok": False, "error": "exists", "current_id": manifest[name]}
    if not in_brain: return {"ok": False, "error": "not_in_brain"}
    if manifest.get(name) == id: return {"ok": True, "already": True, "total": len(manifest)}
    manifest[name] = id   # МЕРЖ
    return {"ok": True, "registered": True, "total": len(manifest)}

BASE = {"folder_id": "F", "knowledge_base": "k", "cc_log": "c", "review": "r"}  # «существующие» ключи

def test_merge_adds_without_touching_existing():
    man = dict(BASE)
    r = register_mirror(man, "roadmap_master", "1Z70", in_brain=True)
    assert r["ok"] and r["registered"]
    assert man["roadmap_master"] == "1Z70"
    # существующие НЕ тронуты
    assert man["knowledge_base"] == "k" and man["cc_log"] == "c" and man["review"] == "r"
    assert man["folder_id"] == "F"

def test_existing_key_not_overwritten():
    man = dict(BASE)
    r = register_mirror(man, "cc_log", "DIFFERENT", in_brain=True)
    assert r["ok"] is False and r["error"] == "exists", r
    assert man["cc_log"] == "c", "существующий id НЕ должен меняться без overwrite"

def test_overwrite_explicit():
    man = dict(BASE)
    r = register_mirror(man, "cc_log", "NEW", in_brain=True, overwrite=True)
    assert r["ok"] and man["cc_log"] == "NEW"

def test_idempotent_same_id():
    man = dict(BASE); man["roadmap_master"] = "1Z70"
    r = register_mirror(man, "roadmap_master", "1Z70", in_brain=True)
    assert r["ok"] and r.get("already") is True

def test_bad_name_and_not_in_brain():
    man = dict(BASE)
    assert register_mirror(man, "Roadmap Master", "x", in_brain=True)["error"] == "bad_name"
    assert register_mirror(man, "x", "", in_brain=True)["error"] == "need_name_id"
    assert register_mirror(man, "foreign", "z", in_brain=False)["error"] == "not_in_brain"

def test_all_five_planlists_register():
    man = dict(BASE)
    pairs = {
        "roadmap_master": "1Z70EpgGZmaYMaZ064sXQlCCP8z8sFyZWfzVPvRB4jWE",
        "executors_map": "1NyfcErxNt09CH8JB-V0in9e-UQB-K4_uJrwZ-FG3Za8",
        "orchestrator_plan": "1_ogUGFim24Ifw60mSsfcONFc8hXMPzw539oXTbhGggo",
        "orchestrator_safety": "1UB1MWs8ZQWDkwHYBqNgK7UyVD4dkPKYdEVYo3IM2-Zs",
        "payments_plan": "13WtxQaDLdixR4EsjUFimtNhESn9nFDtk",
    }
    for k, v in pairs.items():
        assert register_mirror(man, k, v, in_brain=True)["ok"]
    assert all(man[k] == v for k, v in pairs.items())
    assert len(man) == len(BASE) + 5  # 4+folder_id + 5 новых

def test_wrapper_builds_post():
    import bridge_client as BC
    captured = {}
    bc = BC.BridgeClient(url="http://x", token="t")
    bc._post = lambda action, **f: captured.update({"action": action, **f}) or {"ok": True}
    bc.register_brain_doc("roadmap_master", "1Z70", overwrite=False)
    assert captured["action"] == "register_brain_doc"
    assert captured["name"] == "roadmap_master" and captured["id"] == "1Z70" and captured["overwrite"] is False

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов register_brain_doc (зеркало семантики + враппер)")
