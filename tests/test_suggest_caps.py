"""Кап-подстановка в черновике userbot (suggest.py) — код-тест вместо живого @samhold (05.07.2026).

suggest.py живёт на userbot (ПК, тема 205) и в ЭТОТ репо не входит — как QuotePrice.js в Bridge.
Поэтому здесь ЗЕРКАЛО контракта кап-подстановки по спеке KB «Правила цен v2» п.3–4
(knowledge_base.md): quote_price отдаёт cap_price/cap_active (только данные), а подмена цены на
оффер низкого сезона — на стороне userbot. Тест фиксирует именно этот контракт черновика:
активный кап + J-цена выше капа → в черновике оффер «аренда от <кап> ฿/мес — предложение низкого
сезона» и БАЗОВОЙ цены (6572) там НЕТ; кап неактивен → обычная J-цена дословно.

Зеркало 1-в-1: если формат оффера/условие срабатывания на userbot изменят — правится и этот тест."""
import re


def format_baht(n):
    """Разряды тысяч через пробел (RU): 5000 → «5 000», 6572 → «6 572»."""
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", " ", str(int(n)))


def build_price_line(quote):
    """Зеркало кап-подстановки suggest.py. quote — ответ Bridge quote_price
    (total = J-цена за запрошенный срок дословно, cap_price/cap_active — данные капа).

    Спека KB п.4: кап срабатывает, если он активен, есть число капа И J-цена ВЫШЕ капа →
    клиенту оффер «аренда от <кап> ฿/мес — предложение низкого сезона». Иначе — J-текст дословно."""
    cap_price = quote.get("cap_price")
    cap_active = quote.get("cap_active")
    total = quote.get("total")
    if cap_active and cap_price and total and total > cap_price:
        return f"аренда от {format_baht(cap_price)} ฿/мес — предложение низкого сезона"
    # обычный случай — цена по колонке J Календаря дословно (бот число не пересчитывает)
    return quote.get("text") or f"{format_baht(total)} ฿"


# ── фикстуры: NMAX на месяц (30 дней), J-цена месяца = 6572 ────────────────────────
def nmax_month(cap_active, cap_price=5000):
    return {
        "action": "quote_price",
        "bike": "NMAX 155CC BLACK GOLD PHUKET 4255",
        "model": "YAMAHA NMAX 155",
        "days": 30,
        "day_price": 219,
        "total": 6572,                         # J-цена за месяц дословно
        "deposit": 3000,
        "available": True,
        "season": {"label": "low", "global_discount": 0.25},
        "cap_price": cap_price,
        "cap_active": cap_active,
        "text": "6 572 ฿ за месяц (30 дней)",   # J-текст дословно
    }


# ── тесты ──
def test_format_baht():
    assert format_baht(5000) == "5 000"
    assert format_baht(6572) == "6 572"
    assert format_baht(900) == "900"
    assert format_baht(18900) == "18 900"


def test_cap_active_substitutes_offer():
    """cap_active=true, cap_price=5000, J=6572 → оффер низкого сезона, БЕЗ базовой 6572."""
    line = build_price_line(nmax_month(cap_active=True, cap_price=5000))
    assert line == "аренда от 5 000 ฿/мес — предложение низкого сезона", line
    # базовая цена НЕ утекает в черновик ни в каком написании
    assert "6572" not in line and "6 572" not in line, f"базовая цена утекла: {line}"


def test_cap_inactive_keeps_j_price():
    """cap_active=false → обычная J-цена дословно, без оффера низкого сезона."""
    line = build_price_line(nmax_month(cap_active=False))
    assert "6 572" in line, f"нет базовой J-цены: {line}"
    assert "низкого сезона" not in line, f"оффер утёк при неактивном капе: {line}"


def test_cap_active_but_j_below_cap_keeps_j_price():
    """Кап активен, но J-цена НИЖЕ капа (короткий срок) → оффер не навязываем, J дословно.
    Спека п.4: подмена только если J > капа."""
    q = nmax_month(cap_active=True, cap_price=5000)
    q["total"] = 4000
    q["text"] = "4 000 ฿"
    line = build_price_line(q)
    assert line == "4 000 ฿" and "низкого сезона" not in line, line


def test_no_cap_fields_old_bridge():
    """Старый Bridge без cap-полей → обычная J-цена, без падения."""
    q = nmax_month(cap_active=None)
    q.pop("cap_price"); q.pop("cap_active")
    line = build_price_line(q)
    assert "6 572" in line and "низкого сезона" not in line, line


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов suggest_caps")
