"""wallet_cache.py — персистентный кэш баланса кошелька.

Тесты: сохранение, перезагрузка (имитация рестарта), fallback при Bridge-сбое,
golden-тест якоря, изоляция кошельков.
"""
import sys
import os
import json
import importlib
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")

res = []


def ok(c, label):
    status = "  PASS " if c else "  FAIL "
    print(status + label)
    res.append(bool(c))


def _reload_wc(tmp_path):
    """Установить WALLET_CACHE_FILE в tmp и перезагрузить модуль."""
    path = os.path.join(tmp_path, "wallet_cache.json")
    os.environ["WALLET_CACHE_FILE"] = path
    import wallet_cache as wc
    importlib.reload(wc)
    return wc, path


# ── (a) сохранение и загрузка ────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 25067.0, "EUR": 150.0})
    r = wc.load_wallet_balance("Money Cashflow")
    ok(r.get("THB") == 25067.0, "save→load: THB корректен")
    ok(r.get("EUR") == 150.0, "save→load: EUR корректен")

# ── (b) golden: запись → «рестарт» → баланс жив ─────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, path = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 31067.0, "EUR": 150.0})
    # эмулируем рестарт: перезагружаем модуль (файл на диске остаётся)
    importlib.reload(wc)
    r = wc.load_wallet_balance("Money Cashflow")
    ok(r.get("THB") == 31067.0, "golden restart: THB жив после перезагрузки")
    ok(r.get("EUR") == 150.0,   "golden restart: EUR жив после перезагрузки")

# ── (c) fallback при Bridge-сбое ─────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 5000.0})
    r = wc.get_balance_with_fallback("Money Cashflow", {})
    ok(r.get("THB") == 5000.0, "fallback: Bridge {} → возвращает кэш")

# ── (d) Bridge приоритетен и обновляет кэш ───────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 100.0})
    live = {"THB": 999.0, "EUR": 50.0}
    r = wc.get_balance_with_fallback("Money Cashflow", live)
    ok(r.get("THB") == 999.0, "Bridge приоритет: возвращает live")
    cached = wc.load_wallet_balance("Money Cashflow")
    ok(cached.get("THB") == 999.0, "Bridge приоритет: кэш обновился")

# ── (e) пустой dict не затирает кэш ──────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 777.0})
    wc.save_wallet_balance("Money Cashflow", {})
    r = wc.load_wallet_balance("Money Cashflow")
    ok(r.get("THB") == 777.0, "пустой dict не затирает кэш")

# ── (f) неизвестный кошелёк → пустой dict ────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    r = wc.load_wallet_balance("Unknown Wallet")
    ok(r == {}, "неизвестный кошелёк → {}")

# ── (g) якорь balance_set выживает при Bridge-сбое ───────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    anchor = {"THB": 25067.0, "EUR": 150.0}
    wc.save_wallet_balance("Money Cashflow", anchor)
    r = wc.get_balance_with_fallback("Money Cashflow", {})
    ok(r == {"THB": 25067.0, "EUR": 150.0}, "якорь anchor: Bridge {} → кэш отдаёт anchor")

# ── (h) несколько кошельков изолированы ──────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, _ = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 1000.0})
    wc.save_wallet_balance("Other", {"EUR": 200.0})
    ok(wc.load_wallet_balance("Money Cashflow") == {"THB": 1000.0}, "изоляция: Money Cashflow не портит Other")
    ok(wc.load_wallet_balance("Other") == {"EUR": 200.0}, "изоляция: Other корректен")

# ── (i) файл содержит валидный JSON ──────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    wc, path = _reload_wc(td)
    wc.save_wallet_balance("Money Cashflow", {"THB": 42.0})
    with open(path) as f:
        data = json.load(f)
    ok("Money Cashflow" in data, "JSON-файл создан и содержит кошелёк")

# ─────────────────────────────────────────────────────────────────────────────
os.environ.pop("WALLET_CACHE_FILE", None)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
