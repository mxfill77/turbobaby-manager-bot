"""§12: локальный ЛЕДЖЕР ТРАТ платного API (spend_ledger).
Проверяет:
(а) usage накапливается в spend и переживает «рестарт» (перечитать персист / reload модуля);
(б) команда пополнения обнуляет spend и ставит topup (remaining = topup);
(в) remaining ≤ порог → РОВНО 1 warning+пуш; повтор не спамит (дедуп 1/эпизод);
(г) remaining > порог → тихо (ни warn, ни пуш);
(д) цена per-model из конфига (haiku≠sonnet≠opus, префикс-матч дата-суффикса, дефолт неизвестной);
(е) громкий-провал денег (splinter._note_llm_loss) и health.check_api_credit НЕ задеты.
Сеть НЕ дёргаем: пуши считаем мок-счётчиком NOTIFY_COUNT_FILE; персист во временном файле."""
import os, sys, json, tempfile, importlib

sys.path.insert(0, "/root/turbobaby-manager-bot")

_tmp = tempfile.mkdtemp(prefix="spend_ledger_")
os.environ["SPEND_LEDGER_FILE"] = os.path.join(_tmp, "spend_ledger.json")
os.environ["NOTIFY_COUNT_FILE"] = os.path.join(_tmp, "pushes.log")   # мок-счётчик пушей (сеть не трогаем)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")

import spend_ledger as L

results = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    results.append(bool(cond))


def _reset_ledger():
    try:
        os.remove(os.environ["SPEND_LEDGER_FILE"])
    except Exception:
        pass


def _push_count():
    try:
        with open(os.environ["NOTIFY_COUNT_FILE"], encoding="utf-8") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _reset_pushes():
    try:
        os.remove(os.environ["NOTIFY_COUNT_FILE"])
    except Exception:
        pass


class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


# ================= (д) цена per-model из конфига =================
ok(abs(L.cost_usd("claude-haiku-4-5", 1_000_000, 0) - 1.0) < 1e-9, "(д) haiku input 1M = $1.00")
ok(abs(L.cost_usd("claude-haiku-4-5", 0, 1_000_000) - 5.0) < 1e-9, "(д) haiku output 1M = $5.00")
ok(abs(L.cost_usd("claude-sonnet-4-5", 1_000_000, 0) - 3.0) < 1e-9, "(д) sonnet input 1M = $3.00")
ok(abs(L.cost_usd("claude-opus-4-8", 1_000_000, 0) - 5.0) < 1e-9, "(д) opus-4-8 input 1M = $5.00")
# префикс-матч дата-суффикса модели
ok(abs(L.cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0) - 1.0) < 1e-9,
   "(д) haiku с дата-суффиксом → та же цена (префикс-матч)")
# неизвестная модель → дефолт sonnet-tier (3,15)
ok(abs(L.cost_usd("claude-unknown-9", 1_000_000, 1_000_000) - 18.0) < 1e-9,
   "(д) неизвестная модель → дефолт (3+15 за 1M+1M)")

# ================= (а) накопление + переживание рестарта =================
_reset_ledger()
d1 = L.cost_usd("claude-sonnet-4-5", 100_000, 20_000)
L.record_usage("claude-sonnet-4-5", 100_000, 20_000)
L.record_usage("claude-sonnet-4-5", 100_000, 20_000)
st = L.status()
ok(abs(st["spent"] - 2 * d1) < 1e-6, "(а) usage накапливается (2 вызова = 2×стоимость)")
# «рестарт»: reload модуля — состояние читается из персиста, не из памяти
importlib.reload(L)
st2 = L.status()
ok(abs(st2["spent"] - 2 * d1) < 1e-6, "(а) spend переживает reload/рестарт (читается с диска)")
# и сырой файл на диске содержит spend
with open(os.environ["SPEND_LEDGER_FILE"], encoding="utf-8") as f:
    raw = json.load(f)
ok(abs(float(raw["spend"]) - 2 * d1) < 1e-6, "(а) spend лежит в персист-файле")

# ================= (б) пополнение обнуляет spend, ставит topup =================
new = L.set_topup(50)
st = L.status()
ok(new == 50.0 and st["topup"] == 50.0, "(б) topup установлен = $50")
ok(st["spent"] == 0.0, "(б) spend обнулён при пополнении")
ok(abs(st["remaining"] - 50.0) < 1e-9, "(б) remaining = topup − spend = $50")
ok(st["warned"] is False, "(б) warned снят (новый эпизод)")

# ================= (в) remaining ≤ порог → ровно 1 warn + 1 пуш, повтор тихо =================
_reset_ledger(); _reset_pushes()
L.set_topup(3.0)   # порог по умолчанию $2
# крупная трата: output 100k у sonnet = $1.5 → remaining = 3 − 1.5 = 1.5 ≤ 2
w1, rem1 = L.record_usage("claude-sonnet-4-5", 0, 100_000)
ok(w1 is True, "(в) первый пересек порога → should_warn True")
ok(rem1 <= L.THRESHOLD_USD, "(в) remaining действительно ≤ порога")
w2, rem2 = L.record_usage("claude-sonnet-4-5", 0, 1_000)   # ещё немного
ok(w2 is False, "(в) повтор в том же эпизоде → should_warn False (не спамим)")

# пуш через meter(): ровно ОДИН физический пуш на эпизод
_reset_ledger(); _reset_pushes()
L.set_topup(3.0)
L.meter("claude-sonnet-4-5", _Usage(0, 100_000))   # пересечение → 1 пуш
L.meter("claude-sonnet-4-5", _Usage(0, 5_000))     # уже warned → без пуша
ok(_push_count() == 1, "(в) meter шлёт РОВНО 1 пуш на эпизод (дедуп)")

# ================= (г) remaining > порог → тихо =================
_reset_ledger(); _reset_pushes()
L.set_topup(10.0)
w, rem = L.record_usage("claude-sonnet-4-5", 0, 100_000)   # $1.5 → remaining 8.5 > 2
ok(w is False and rem > L.THRESHOLD_USD, "(г) remaining > порога → should_warn False")
L.meter("claude-sonnet-4-5", _Usage(0, 100_000))
ok(_push_count() == 0, "(г) remaining > порога → ноль пушей")

# пополнение снимает warned → новый эпизод снова может предупредить
_reset_ledger(); _reset_pushes()
L.set_topup(3.0)
L.meter("claude-sonnet-4-5", _Usage(0, 100_000))   # эпизод 1: 1 пуш
L.set_topup(3.0)                                    # пополнили → warned снят
L.meter("claude-sonnet-4-5", _Usage(0, 100_000))   # эпизод 2: снова 1 пуш
ok(_push_count() == 2, "(в/б) пополнение открывает новый эпизод → снова предупреждает")

# ================= (е) громкий-провал денег и check_api_credit НЕ задеты =================
import health as H
ok(callable(getattr(H, "check_api_credit", None)), "(е) health.check_api_credit на месте")
w, d = H.check_api_credit(_probe=lambda: {"ok": True})
ok(w is False, "(е) check_api_credit happy-путь → тихо (не сломан импортом леджера)")

import splinter as S
ok(callable(getattr(S, "_note_llm_loss", None)), "(е) splinter._note_llm_loss на месте")
# money=False путь: лог+тихий счётчик, БЕЗ пуша, возврат False — доказывает, что тракт цел
before = _push_count()
r = S._note_llm_loss(money=False, kind="vision", detail="probe")
ok(r is False and _push_count() == before, "(е) _note_llm_loss(money=False) → тихо, тракт не задет")


if __name__ == "__main__":
    print(f"OK — {sum(results)}/{len(results)} проверок test_spend_ledger")
    sys.exit(0 if all(results) else 1)
