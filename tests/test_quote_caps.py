"""Капы-акции low season в quote_price (зеркало QuotePrice.js, 05.07.2026).
Apps Script локально не исполнить — логика quoteReadCaps_/резолва капа отзеркалена в Python
1-в-1, синтаксис .gs проверяется node --check, дрейф cap-ключей в QUOTE_MODELS ловится
парсом реального QuotePrice.js. Плюс: обёртка bridge_client.quote_price прокидывает
cap_price/cap_active как есть (и не падает на старом Bridge без этих полей)."""
import os, sys, re, json, subprocess
from unittest import mock

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

# .js берём из ЗЕРКАЛА ПРОДА `bridge_prod/` (задеплоенная версия, паспорт MIRROR.json), а не из
# рабочей папки выкладки: она обезврежена 10.08.2026 и отстаёт от прода.
QP_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge_prod", "QuotePrice.js")

# 12 строк блока капов — ровно то, что заносится в «Календарь бронирования» (карточка 05.07)
CAP_BLOCK = [
    ["NMAX",           "5000",  "да"],
    ["XMAX OLD",       "8900",  "да"],
    ["XMAX NEW",       "9900",  "да"],
    ["ADV350",         "10900", "да"],
    ["Forza300",       "7900",  "да"],
    ["XSR155",         "7490",  "да"],
    ["CB300R",         "9900",  "да"],
    ["MT-03",          "10990", "да"],
    ["Ninja400",       "11900", "да"],
    ["CB650R/CBR650R", "18900", "да"],
    ["Vulcan",         "18900", "да"],
    ["XADV750",        "33900", "да"],
]

# Ожидаемые cap-ключи QUOTE_MODELS (model → normalized-имя строки капа; None = капа нет)
EXPECTED_CAPS = {
    "YAMAHA XSR 155": "xsr155",
    "HONDA CB 300R": "cb300r",
    "HONDA REBEL 300": None,
    "YAMAHA MT-03 300": "mt-03",
    "KAWASAKI NINJA 400": "ninja400",
    "KAWA VULCAN 650S": "vulcan",
    "HONDA CBR 650R": "cb650r/cbr650r",
    "HONDA CB 650R": "cb650r/cbr650r",
    "YAMAHA XSR 900": None,
    "YAMAHA R7": None,
    "HONDA CLICK 125": None,
    "HONDA PCX150": None,
    "HONDA ADV 150": None,
    "YAMAHA NMAX 155": "nmax",
    "HONDA PCX 160": None,
    "HONDA ADV 160": None,
    "HONDA FORZA 300": "forza300",
    "YAMAHA XMAX 300 NEW 2023-": "xmax new",
    "YAMAHA XMAX300 2020-2022": "xmax old",
    "HONDA ADV 350": "adv350",
    "HONDA XADV 750": "xadv750",
}


# Адрес блока капов — зеркало CAPS_ANCHOR (QuotePrice.js): шапка Z3, данные Z4:AB15 (12 строк)
CAPS_ANCHOR = {"col": 26, "header_row": 3, "data_rows": 12}


# ── ЗЕРКАЛО quoteNormCap_/quoteReadCaps_ (QuotePrice.js) ──
def norm_cap(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def read_caps_mirror(head, data_rows):
    """От CAPS_ANCHOR: head — 3 ячейки Z3:AB3; data_rows — строки Z4:AB.. (3-широкие).
    Шапка не «Модель» → None (блока по адресу нет). Данные до первой пустой «Модели»."""
    if norm_cap(head[0] if head else "") != "модель":
        return None
    caps = {}
    for r in data_rows:
        name = norm_cap(r[0] if r else "")
        if not name:
            break
        cap_num = float(re.sub(r"[^\d.]", "", str(r[1] if len(r) > 1 else "")) or 0)
        act = norm_cap(r[2] if len(r) > 2 else "")
        caps[name] = {
            "cap": cap_num if cap_num else None,
            "active": act in ("да", "yes", "true", "1"),
        }
    return caps


def resolve_cap_mirror(caps, cap_key):
    """Зеркало cap-блока quotePrice(): (cap_price, cap_active)."""
    cap_price, cap_active = None, False
    entry = caps.get(cap_key) if (caps and cap_key) else None
    if entry:
        cap_price = entry["cap"]
        cap_active = bool(entry["active"] and entry["cap"])
    return cap_price, cap_active


def block_as_sheet():
    """Блок капов как регион CAPS_ANCHOR (Z3:AB..): шапка Z3:AB3 + данные Z4.. + пустая строка-конец."""
    head = ["Модель", "Кап ฿/мес", "Активен"]
    rows = [[m, c, a] for m, c, a in CAP_BLOCK]
    rows.append(["", "", ""])  # конец блока
    return head, rows


# ── тесты ──
def test_js_syntax_node_check():
    r = subprocess.run(["node", "--check", QP_JS], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"node --check упал: {r.stderr}"


def test_js_has_cap_fields_and_reader():
    src = open(QP_JS, encoding="utf-8").read()
    for token in ("cap_price", "cap_active", "quoteReadCaps_", "quoteNormCap_"):
        assert token in src, f"в QuotePrice.js нет {token}"


def test_js_cap_keys_match_expected():
    """Дрейф-guard: cap-ключи в реальном QUOTE_MODELS == ожидаемой карте (12 моделей с капом)."""
    src = open(QP_JS, encoding="utf-8").read()
    body = src.split("var QUOTE_MODELS")[1].split("];")[0]
    got = {}
    for m in re.finditer(r"model:\s*'([^']+)'.*?cap:\s*(null|'([^']*)')", body):
        got[m.group(1)] = m.group(3) if m.group(2) != "null" else None
    assert got == EXPECTED_CAPS, f"дрейф cap-ключей: {got}"
    with_cap = [k for k, v in got.items() if v]
    assert len(with_cap) == 13  # 12 капов, CB650R и CBR650R делят один
    assert len(set(v for v in got.values() if v)) == 12


def test_cap_block_names_cover_all_keys():
    """Каждый cap-ключ из QUOTE_MODELS находит строку в блоке капов (нет сироты-ключа)."""
    head, rows = block_as_sheet()
    caps = read_caps_mirror(head, rows)
    for cap_key in set(v for v in EXPECTED_CAPS.values() if v):
        assert cap_key in caps, f"cap-ключ {cap_key} не находит строку блока"


def test_read_caps_parses_block():
    head, rows = block_as_sheet()
    caps = read_caps_mirror(head, rows)
    assert len(caps) == 12
    assert caps["nmax"] == {"cap": 5000, "active": True}
    assert caps["xadv750"] == {"cap": 33900, "active": True}
    assert caps["cb650r/cbr650r"]["cap"] == 18900


def test_caps_anchor_matches_js():
    """Дрейф-guard адреса: CAPS_ANCHOR в реальном QuotePrice.js == Z3, данные Z4:AB15 (12 строк).
    Читатель И писатель берут адрес из ОДНОЙ константы — старого скана K..T больше нет."""
    src = open(QP_JS, encoding="utf-8").read()
    body = src.split("var CAPS_ANCHOR = {")[1].split("};")[0]
    col = int(re.search(r"col:\s*(\d+)", body).group(1))
    hr = int(re.search(r"headerRow:\s*(\d+)", body).group(1))
    dr = int(re.search(r"dataRows:\s*(\d+)", body).group(1))
    assert (col, hr, dr) == (26, 3, 12), f"адрес капов уехал: col={col} row={hr} rows={dr}"
    assert col == CAPS_ANCHOR["col"] and hr == CAPS_ANCHOR["header_row"] and dr == CAPS_ANCHOR["data_rows"]
    # старые скан-константы и сканирующий поиск колонки удалены — адрес теперь единый
    for gone in ("QUOTE_CAP_SCAN_FROM", "QUOTE_CAP_SCAN_TO", "QUOTE_CAP_MAX_ROWS", "quoteFindCapCol_"):
        assert gone not in src, f"остался рудимент старого скан-адреса: {gone}"
    # оба потока (чтение и запись) ссылаются на единый CAPS_ANCHOR
    assert src.count("CAPS_ANCHOR") >= 6, "CAPS_ANCHOR должен использоваться в чтении и записи"


def test_no_block_returns_none():
    caps = read_caps_mirror(["", "", ""], [])
    assert caps is None  # шапки по адресу нет → quote_price отдаёт null/false, не ошибку


def test_resolution_shared_and_missing():
    head, rows = block_as_sheet()
    caps = read_caps_mirror(head, rows)
    # CB650R и CBR650R → один кап 18900
    for key in ("cb650r/cbr650r",):
        price, active = resolve_cap_mirror(caps, key)
        assert price == 18900 and active is True
    # модель без капа (REBEL/XSR900/R7/PCX/ADV150-160/CLICK) → null/false
    price, active = resolve_cap_mirror(caps, None)
    assert price is None and active is False


def test_inactive_and_formats():
    head, rows = block_as_sheet()
    rows[0][2] = "нет"          # NMAX «Активен» = нет (AB, третья колонка региона)
    rows[1][1] = "8 900 ฿"      # XMAX OLD кап с пробелом и ฿ (AA, вторая колонка)
    caps = read_caps_mirror(head, rows)
    price, active = resolve_cap_mirror(caps, "nmax")
    assert price == 5000 and active is False, "кап виден, но неактивен"
    assert caps["xmax old"]["cap"] == 8900, "число парсится из «8 900 ฿»"


def test_wrapper_passes_cap_fields():
    import requests  # noqa: F401
    from bridge_client import BridgeClient

    payload = {"ok": True, "action": "quote_price", "bike": "NMAX 155CC GREEN-B PHUKET 4957",
               "model": "YAMAHA NMAX 155", "days": 30, "day_price": 200, "total": 6000,
               "deposit": 3000, "available": True, "conflicts": 0,
               "season": {"label": "low", "global_discount": 0.25},
               "cap_price": 5000, "cap_active": True, "text": "..."}
    resp = mock.Mock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json = lambda: payload
    with mock.patch("bridge_client.requests.Session.get", return_value=resp):
        res = BridgeClient(url="http://x", token="x", timeout=1).quote_price(
            "4957", "08.07.2026", "07.08.2026")
    assert res["cap_price"] == 5000 and res["cap_active"] is True


def test_wrapper_old_bridge_without_caps():
    """Старый Bridge (до капов) полей не шлёт — обёртка отдаёт dict, .get() даёт None."""
    from bridge_client import BridgeClient
    payload = {"ok": True, "day_price": 317, "total": 2217, "deposit": 3000,
               "available": True, "conflicts": 0, "season": {"label": "low"}, "text": "..."}
    resp = mock.Mock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json = lambda: payload
    with mock.patch("bridge_client.requests.Session.get", return_value=resp):
        res = BridgeClient(url="http://x", token="x", timeout=1).quote_price(
            "4957", "08.07.2026", "15.07.2026")
    assert isinstance(res, dict) and res.get("cap_price") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов quote_caps")
