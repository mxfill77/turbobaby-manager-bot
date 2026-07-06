#!/usr/bin/env python3
"""§12: ЛОКАЛЬНЫЙ ЛЕДЖЕР ТРАТ платного API — ранний порог остатка.

Зачем: платный Anthropic API остаток по ключу НЕ отдаёт (recon 06.07 11:08). Чтобы
предупредить ЗАРАНЕЕ (при остатке ≤ порога), а не постфактум на нуле, копим ОЦЕНКУ трат:
на каждый ответ платного API читаем usage.input_tokens/output_tokens → умножаем на цену
модели → инкрементим персистентный счётчик spend (переживает рестарт splinter). Владелец
командой «баланс api пополнен на $N» ставит topup и обнуляет spend; remaining = topup − spend.
При remaining ≤ порога → ОДИН ранний warning+пуш (дедуп: 1/эпизод, снимается пополнением).

ГРАНИЦЫ: это РАННИЙ слой. Оценка приблизительная (токены×цена) — ОК для сигнала «пора
пополнять», НЕ бухгалтерия. Последний рубеж — health.check_api_credit (ловля 400 постфактум) —
ОСТАЁТСЯ независимо: если леджер разошёлся с реальностью, 400 всё равно поймается. Громкий
провал денег (splinter._note_llm_loss, d946f92) — тоже независим, НЕ задет.

Персист: JSON-файл spend_ledger.json в корне репо (атомарная запись tmp+os.replace, flock —
не теряется/не бьётся при рестарте или параллельном доступе). Ключи: topup, spend, warned.
"""
import os
import json
import fcntl
import logging

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))
# Путь персиста (env override — для тестов во временном каталоге).
_LEDGER_FILE = os.environ.get("SPEND_LEDGER_FILE") or os.path.join(ROOT, "spend_ledger.json")

# Ранний порог предупреждения, USD. Легко менять (env SPEND_LEDGER_THRESHOLD или тут).
THRESHOLD_USD = float(os.environ.get("SPEND_LEDGER_THRESHOLD", "2") or "2")

# ЦЕНЫ per-model, USD за 1M токенов: (input, output). КОНФИГ — легко правится.
# Источник — прайс Anthropic (claude-api skill, кэш 2026-06-24). Приблизительно (для сигнала).
# Ключи матчатся по ПРЕФИКСУ (модель может нести дату-суффикс: claude-haiku-4-5-20251001).
PRICE_PER_MTOK = {
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-sonnet-5":   (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),  # дефолтная модель splinter (CLAUDE_MODEL)
    "claude-haiku-4-5":  (1.0, 5.0),   # judge() аудитора — отдельная дешёвая модель
}
# Неизвестная модель → как sonnet-tier (консервативно, чтоб недооценка не проспала порог).
DEFAULT_PRICE = (3.0, 15.0)


def _price_for(model: str):
    """Цена (in,out) per-1M по имени модели. Матч по ПРЕФИКСУ (самый длинный ключ-префикс)."""
    m = (model or "").strip().lower()
    best = None
    for key, price in PRICE_PER_MTOK.items():
        if m.startswith(key) and (best is None or len(key) > len(best[0])):
            best = (key, price)
    return best[1] if best else DEFAULT_PRICE


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Оценка стоимости одного вызова: токены×цена/1M. Приблизительно (для сигнала)."""
    pin, pout = _price_for(model)
    it = max(0, int(input_tokens or 0))
    ot = max(0, int(output_tokens or 0))
    return (it / 1_000_000.0) * pin + (ot / 1_000_000.0) * pout


class _Lock:
    """flock на lock-файле — атомарность read-modify-write при параллельном доступе/рестарте."""
    def __enter__(self):
        try:
            self.f = open(_LEDGER_FILE + ".lock", "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except Exception:
            self.f = None
        return self

    def __exit__(self, *a):
        try:
            if self.f:
                fcntl.flock(self.f, fcntl.LOCK_UN)
                self.f.close()
        except Exception:
            pass


def _default_state():
    return {"topup": 0.0, "spend": 0.0, "warned": False}


def _load():
    """Прочитать персист. Битый/отсутствующий файл → дефолт (не роняем LLM-путь)."""
    try:
        with open(_LEDGER_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return {
            "topup": float(d.get("topup", 0.0) or 0.0),
            "spend": float(d.get("spend", 0.0) or 0.0),
            "warned": bool(d.get("warned", False)),
        }
    except Exception:
        return _default_state()


def _save(state):
    """Атомарная перезапись (tmp + os.replace) — параллельный читатель не увидит полу-файл."""
    tmp = _LEDGER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _LEDGER_FILE)


def record_usage(model, input_tokens, output_tokens):
    """Инкремент spend на оценку стоимости вызова (атомарно, переживает рестарт).
    Возврат: (should_warn:bool, remaining:float). should_warn=True РОВНО ОДИН раз за эпизод —
    когда remaining впервые пересекает порог вниз (topup задан). Пока не пополнят — тихо."""
    delta = cost_usd(model, input_tokens, output_tokens)
    with _Lock():
        st = _load()
        st["spend"] = round(st["spend"] + delta, 8)
        remaining = round(st["topup"] - st["spend"], 6)
        should_warn = False
        # Порог осмыслен ТОЛЬКО когда владелец задал topup (иначе remaining неизвестен).
        if st["topup"] > 0 and remaining <= THRESHOLD_USD and not st["warned"]:
            st["warned"] = True
            should_warn = True
        _save(st)
    return should_warn, remaining


def set_topup(amount):
    """Владелец пополнил: topup=amount, обнулить spend_since_topup, снять warned (новый эпизод).
    remaining считается с этой точки. Возврат: новый topup."""
    with _Lock():
        st = _load()
        st["topup"] = round(float(amount), 6)
        st["spend"] = 0.0
        st["warned"] = False
        _save(st)
        return st["topup"]


def status():
    """Снимок: {topup, spent, remaining, warned}. spent = потрачено с пополнения."""
    st = _load()
    return {
        "topup": st["topup"],
        "spent": round(st["spend"], 6),
        "remaining": round(st["topup"] - st["spend"], 6),
        "warned": st["warned"],
    }


def remaining():
    """Остаток = topup − spend_since_topup."""
    return status()["remaining"]


def _push_low(rem):
    """ОДИН ранний пуш владельцу при пересечении порога. force=True — боевой алерт (как касса)."""
    try:
        import notify
        notify.notify(
            f"⚠️ баланс API ~${THRESHOLD_USD:.0f} (осталось ~${rem:.2f}) — пополни.\n"
            f"Когда пополнишь: напиши Splinter «баланс api пополнен на $N».",
            force=True)
    except Exception:
        log.exception("spend_ledger: низкий-баланс пуш упал")


def meter(model, usage):
    """Учесть usage платного вызова + при пересечении порога — ОДИН пуш. Обёртка вокруг
    record_usage: БЕЗОПАСНА (любая ошибка проглатывается — учёт НЕ роняет LLM-путь). Зовётся
    из claude_client после resp = messages.create (только API-путь; CLI-подписка usage не даёт)."""
    if usage is None:
        return
    try:
        it = int(getattr(usage, "input_tokens", 0) or 0)
        ot = int(getattr(usage, "output_tokens", 0) or 0)
    except Exception:
        return
    try:
        should_warn, rem = record_usage(model, it, ot)
    except Exception:
        log.exception("spend_ledger.record_usage упал (учёт пропущен, LLM-путь цел)")
        return
    if should_warn:
        _push_low(rem)


# ---- разбор владельческих команд (чистые функции — тестируемы) --------------------------------
import re as _re

# Маркер, что речь про API-баланс (а НЕ наличную кассу THB): "api"/"апи"/"credit"/"кредит"/"$".
_API_MARKER = _re.compile(r"(api|апи|credit|кредит|\$)", _re.IGNORECASE)
# Пополнение: "...пополн... [на] $N" (число с . или ,). Требует и «пополн», и API-маркер.
_TOPUP_AMT = _re.compile(r"пополн\w*.{0,20}?([0-9]+(?:[.,][0-9]+)?)", _re.IGNORECASE | _re.DOTALL)
# Запрос остатка: "сколько осталось" / "остаток" / "баланс" + API-маркер.
_QUERY = _re.compile(r"(сколько\s+осталось|остат\w*|баланс|balance|сколько)", _re.IGNORECASE)


def parse_topup(text):
    """Если текст = команда пополнения API-баланса → сумма (float); иначе None.
    Требует и слово «пополн...», и API-маркер (api/апи/credit/$) — чтобы НЕ путать с кассой THB."""
    t = text or ""
    if "пополн" not in t.lower():
        return None
    if not _API_MARKER.search(t):
        return None
    m = _TOPUP_AMT.search(t)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def is_balance_query(text):
    """Текст = запрос остатка API-баланса? Требует API-маркер + слово запроса (остаток/баланс/
    сколько осталось). Пополнение сюда НЕ относим (его ловит parse_topup)."""
    t = text or ""
    if "пополн" in t.lower():
        return False
    if not _API_MARKER.search(t):
        return False
    return bool(_QUERY.search(t))


def is_api_ledger_cmd(text):
    """Быстрый гейт: текст относится к леджеру API (пополнение ИЛИ запрос)?"""
    return parse_topup(text) is not None or is_balance_query(text)
