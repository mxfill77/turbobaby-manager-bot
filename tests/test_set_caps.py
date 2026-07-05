"""set_caps / toggle_cap — запись блока капов в «Календарь бронирования» (зеркало QuotePrice.js, 05.07.2026).
Apps Script локально не исполнить — логика setCaps/toggleCap отзеркалена в Python 1-в-1 над
фейковой сеткой K..T; синтаксис .gs проверяется node --check; роутинг/REDZONE_LOCK/confirmed-гейт
ловятся парсом реальных Bridge.js и QuotePrice.js. Round-trip: что set_caps записал —
quoteReadCaps_ (зеркало из test_quote_caps) читает обратно."""
import os, re, subprocess, sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

from test_quote_caps import CAP_BLOCK, EXPECTED_CAPS, norm_cap, read_caps_mirror

QP_JS = "/root/turbobaby-bridge-gs/QuotePrice.js"
BRIDGE_JS = "/root/turbobaby-bridge-gs/Bridge.js"

CAP_HEADER_ROW = 3      # QUOTE_CAP_HEADER_ROW
CAP_SCAN_FROM = 11      # K
CAP_SCAN_TO = 20        # T
CAP_MAX_ROWS = 20       # QUOTE_CAP_MAX_ROWS
WIDTH = 14              # ширина фейковой сетки: K..T (10) + запас справа под блок у края

# payload для боевого вызова set_caps после деплоя — ровно финальная таблица (те же 12 строк)
SET_CAPS_PAYLOAD = [{"model": m, "cap": int(c), "active": True} for m, c, a in CAP_BLOCK]

_UNSET = object()


# ── ЗЕРКАЛО quoteParseOnOff_/quoteFindCapCol_/setCaps/toggleCap (QuotePrice.js) ──
def parse_on_off(v):
    if v is True:
        return True
    if v is False:
        return False
    s = norm_cap(v)
    if s in ("on", "да", "yes", "true", "1"):
        return True
    if s in ("off", "нет", "no", "false", "0"):
        return False
    return None


def blank_grid(data_rows=CAP_MAX_ROWS + 2):
    """Сетка региона капов: head = строка 3 (K..), data = строки 4.. той же ширины."""
    return [""] * WIDTH, [[""] * WIDTH for _ in range(data_rows)]


def find_cap_col(head):
    """Зеркало quoteFindCapCol_: индекс шапки «Модель» ВНУТРИ региона K..T, либо -1."""
    for i in range(CAP_SCAN_TO - CAP_SCAN_FROM + 1):
        if norm_cap(head[i]) == "модель":
            return i
    return -1


def set_caps_mirror(head, data, body):
    p = body or {}
    if p.get("confirmed") is not True:
        return {"ok": False, "error": "not_confirmed"}
    caps = p.get("caps")
    if not caps:
        return {"ok": False, "error": "missing_caps"}
    if len(caps) > CAP_MAX_ROWS:
        return {"ok": False, "error": "too_many_caps"}
    rows = []
    for i, c in enumerate(caps):
        name = str(c.get("model") or "").strip()
        try:
            cap_num = float(c.get("cap"))
        except (TypeError, ValueError):
            cap_num = float("nan")
        act = parse_on_off(True if c.get("active", _UNSET) is _UNSET else c["active"])
        if not name:
            return {"ok": False, "error": "bad_cap_row", "row": i + 1}
        if not cap_num or cap_num != cap_num or cap_num <= 0:
            return {"ok": False, "error": "bad_cap_row", "row": i + 1}
        if act is None:
            return {"ok": False, "error": "bad_cap_row", "row": i + 1}
        rows.append([name, cap_num, "да" if act else "нет"])
    col = find_cap_col(head)
    if col < 0:
        col = 0  # = QUOTE_CAP_SCAN_FROM (K)
    head[col], head[col + 1], head[col + 2] = "Модель", "Кап ฿/мес", "Активен"
    for j, r in enumerate(rows):
        data[j][col], data[j][col + 1], data[j][col + 2] = r[0], r[1], r[2]
    for j in range(len(rows), CAP_MAX_ROWS):  # дочистка хвоста старого блока
        data[j][col] = data[j][col + 1] = data[j][col + 2] = ""
    return {"ok": True, "header_cell": chr(64 + CAP_SCAN_FROM + col) + str(CAP_HEADER_ROW),
            "rows": len(rows), "models": [r[0] for r in rows]}


def toggle_cap_mirror(head, data, body):
    p = body or {}
    if p.get("confirmed") is not True:
        return {"ok": False, "error": "not_confirmed"}
    want = norm_cap(p.get("model"))
    if not want:
        return {"ok": False, "error": "missing_model"}
    on = parse_on_off(p.get("on"))
    if on is None:
        return {"ok": False, "error": "bad_on"}
    col = find_cap_col(head)
    if col < 0:
        return {"ok": False, "error": "no_cap_block"}
    for j in range(CAP_MAX_ROWS):
        name = norm_cap(data[j][col])
        if not name:
            break
        if name == want:
            data[j][col + 2] = "да" if on else "нет"
            cap_num = float(re.sub(r"[^\d.]", "", str(data[j][col + 1])) or 0)
            return {"ok": True, "model": str(data[j][col]),
                    "cap_price": cap_num if cap_num else None, "cap_active": on}
    return {"ok": False, "error": "model_not_found"}


# ── тесты: синтаксис и структура реальных .js ──
def test_js_syntax_node_check():
    for f in (QP_JS, BRIDGE_JS):
        r = subprocess.run(["node", "--check", f], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, f"node --check {f} упал: {r.stderr}"


def test_bridge_routes_and_redzone():
    src = open(BRIDGE_JS, encoding="utf-8").read()
    assert "case 'set_caps'" in src and "setCaps(body)" in src, "нет роутинга set_caps"
    assert "case 'toggle_cap'" in src and "toggleCap(body)" in src, "нет роутинга toggle_cap"
    lock = src.split("REDZONE_LOCK = {")[1].split("};")[0]
    assert "set_caps: 1" in lock and "toggle_cap: 1" in lock, "set_caps/toggle_cap не в REDZONE_LOCK"


def test_js_confirmed_gate_and_readonly_quote():
    src = open(QP_JS, encoding="utf-8").read()
    assert src.count("not_confirmed") >= 2, "confirmed-гейт должен стоять в ОБОИХ экшенах"
    for fn in ("function setCaps(", "function toggleCap(", "function quoteParseOnOff_(",
               "function quoteFindCapCol_("):
        assert fn in src, f"в QuotePrice.js нет {fn}"
    # quote_price остаётся read-only: до блока setCaps ни одного setValue/clearContent
    read_part = src.split("function setCaps(")[0]
    assert "setValue" not in read_part and "clearContent" not in read_part, \
        "read-only часть QuotePrice.js не должна писать в лист"


# ── тесты: логика (зеркало) ──
def test_not_confirmed_refused():
    head, data = blank_grid()
    assert set_caps_mirror(head, data, {"caps": SET_CAPS_PAYLOAD})["error"] == "not_confirmed"
    assert toggle_cap_mirror(head, data, {"model": "NMAX", "on": "off"})["error"] == "not_confirmed"
    assert head == blank_grid()[0], "рефьюз не должен трогать лист"


def test_set_caps_creates_block_roundtrip():
    head, data = blank_grid()
    r = set_caps_mirror(head, data, {"confirmed": True, "caps": SET_CAPS_PAYLOAD})
    assert r["ok"] and r["rows"] == 12 and r["header_cell"] == "K3"
    caps = read_caps_mirror(head, data)  # что записали — quoteReadCaps_ читает обратно
    assert len(caps) == 12
    assert caps["nmax"] == {"cap": 5000, "active": True}
    assert caps["xadv750"] == {"cap": 33900, "active": True}
    assert caps["cb650r/cbr650r"]["cap"] == 18900
    # все cap-ключи QUOTE_MODELS находят строку нового блока
    for cap_key in set(v for v in EXPECTED_CAPS.values() if v):
        assert cap_key in caps, f"cap-ключ {cap_key} не находит строку после set_caps"


def test_set_caps_updates_in_place_and_clears_tail():
    # старый блок: шапка со смещением (N вместо K) и 15 строк
    head, data = blank_grid()
    head[3], head[4], head[5] = "Модель", "Кап ฿/мес", "Активен"
    for i in range(15):
        data[i][3], data[i][4], data[i][5] = f"OLD{i}", 100 + i, "да"
    r = set_caps_mirror(head, data, {"confirmed": True, "caps": SET_CAPS_PAYLOAD})
    assert r["ok"] and r["header_cell"] == "N3", "блок обновляется НА МЕСТЕ найденной шапки"
    caps = read_caps_mirror(head, data)
    assert len(caps) == 12 and "old12" not in caps, "хвост старого блока (13..15) дочищен"
    assert caps["nmax"]["cap"] == 5000


def test_set_caps_validation():
    head, data = blank_grid()
    assert set_caps_mirror(head, data, {"confirmed": True})["error"] == "missing_caps"
    assert set_caps_mirror(head, data, {"confirmed": True, "caps": []})["error"] == "missing_caps"
    too_many = [{"model": f"m{i}", "cap": 1000} for i in range(CAP_MAX_ROWS + 1)]
    assert set_caps_mirror(head, data, {"confirmed": True, "caps": too_many})["error"] == "too_many_caps"
    for bad in ({"model": "", "cap": 5000}, {"model": "NMAX", "cap": 0},
                {"model": "NMAX", "cap": "дорого"}, {"model": "NMAX", "cap": -5},
                {"model": "NMAX", "cap": 5000, "active": "может быть"}):
        r = set_caps_mirror(head, data, {"confirmed": True, "caps": [bad]})
        assert r["error"] == "bad_cap_row", f"пропущена кривая строка: {bad}"
    assert find_cap_col(head) == -1, "ошибки валидации не должны трогать лист"


def test_toggle_cap_roundtrip():
    head, data = blank_grid()
    set_caps_mirror(head, data, {"confirmed": True, "caps": SET_CAPS_PAYLOAD})
    r = toggle_cap_mirror(head, data, {"confirmed": True, "model": "nmax", "on": "off"})
    assert r["ok"] and r["model"] == "NMAX" and r["cap_price"] == 5000 and r["cap_active"] is False
    caps = read_caps_mirror(head, data)
    assert caps["nmax"] == {"cap": 5000, "active": False}, "quote_price увидит кап неактивным"
    r2 = toggle_cap_mirror(head, data, {"confirmed": True, "model": "NMAX", "on": "да"})
    assert r2["ok"] and r2["cap_active"] is True
    assert read_caps_mirror(head, data)["nmax"]["active"] is True


def test_toggle_cap_errors():
    head, data = blank_grid()
    assert toggle_cap_mirror(head, data, {"confirmed": True, "model": "NMAX", "on": "on"})["error"] == "no_cap_block"
    set_caps_mirror(head, data, {"confirmed": True, "caps": SET_CAPS_PAYLOAD})
    assert toggle_cap_mirror(head, data, {"confirmed": True, "model": "", "on": "on"})["error"] == "missing_model"
    assert toggle_cap_mirror(head, data, {"confirmed": True, "model": "R7", "on": "on"})["error"] == "model_not_found"
    assert toggle_cap_mirror(head, data, {"confirmed": True, "model": "NMAX", "on": "xx"})["error"] == "bad_on"


def test_parse_on_off_variants():
    for v in (True, "on", "да", "yes", "true", "1", "ДА", " On "):
        assert parse_on_off(v) is True, f"{v!r} должен быть True"
    for v in (False, "off", "нет", "no", "false", "0", "НЕТ"):
        assert parse_on_off(v) is False, f"{v!r} должен быть False"
    for v in (None, "", "вкл?", 2):
        assert parse_on_off(v) is None, f"{v!r} должен быть None (не понят)"


def test_payload_matches_final_table():
    """Боевой payload = финальная таблица карточки 05.07 (дрейф-guard сумм)."""
    want = {"nmax": 5000, "xmax old": 8900, "xmax new": 9900, "adv350": 10900,
            "forza300": 7900, "xsr155": 7490, "cb300r": 9900, "mt-03": 10990,
            "ninja400": 11900, "cb650r/cbr650r": 18900, "vulcan": 18900, "xadv750": 33900}
    got = {norm_cap(c["model"]): c["cap"] for c in SET_CAPS_PAYLOAD}
    assert got == want and all(c["active"] for c in SET_CAPS_PAYLOAD)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов set_caps")
