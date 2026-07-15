#!/usr/bin/env python3
"""Персистентный кэш баланса кошельков — fallback при недоступности Bridge.

Проблема-класс: Bridge.get_balance() при таймауте/ошибке возвращает {} →
_record_transaction показывает «Баланс: 0 ฿», хотя реальный баланс в Bot Data корректен.
Та же дыра при bridge_set: если Bridge недоступен в момент «Баланс считаем отсюда» —
транзакция-якорь молча теряется.

Фикс: после каждого успешного ответа Bridge (get_balance / add_transaction / balance_set)
обновляем JSON-кэш (атомарно, tmp + os.replace). При пустом/ошибочном ответе Bridge —
возвращаем кэш. Рестарт splinter кэш не трогает — он на диске.

Структура файла: {"Money Cashflow": {"THB": 25067.0, "EUR": 150.0}, ...}
"""
import os
import json
import fcntl
import logging

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.environ.get("WALLET_CACHE_FILE") or os.path.join(ROOT, "wallet_cache.json")


class _Lock:
    def __enter__(self):
        try:
            self.f = open(_CACHE_FILE + ".lock", "w")
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


def _load() -> dict:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict):
    tmp = _CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _CACHE_FILE)


def save_wallet_balance(wallet: str, balance: dict):
    """Сохранить баланс кошелька (после успешного ответа Bridge).
    balance = {"THB": 25067, "EUR": 150, ...}  — пустой dict игнорируется (не перезаписываем)."""
    if not wallet or not balance:
        return
    try:
        with _Lock():
            data = _load()
            data[wallet] = {k: float(v) for k, v in balance.items() if v is not None}
            _save(data)
    except Exception:
        log.exception("wallet_cache: не удалось сохранить баланс (не критично)")


def load_wallet_balance(wallet: str) -> dict:
    """Прочитать кэш баланса кошелька. Возвращает dict (может быть {} если нет данных)."""
    if not wallet:
        return {}
    try:
        data = _load()
        return data.get(wallet, {})
    except Exception:
        return {}


def get_balance_with_fallback(wallet: str, bridge_balance: dict) -> dict:
    """Выбрать актуальный баланс: если Bridge вернул непустой dict — он приоритетен и обновляет
    кэш; иначе — кэш (последнее известное значение). Возвращает dict баланса."""
    if bridge_balance:
        save_wallet_balance(wallet, bridge_balance)
        return bridge_balance
    cached = load_wallet_balance(wallet)
    if cached:
        log.warning(f"wallet_cache: Bridge вернул пустой баланс для «{wallet}» — "
                    f"используем кэш {cached}")
    return cached
