#!/usr/bin/env python3
"""Персистентный кэш баланса кошельков — fallback при недоступности Bridge.

Проблема-класс: Bridge.get_balance() при таймауте/ошибке возвращает {} →
_record_transaction показывает «Баланс: 0 ฿», хотя реальный баланс в Bot Data корректен.
Та же дыра при bridge_set: если Bridge недоступен в момент «Баланс считаем отсюда» —
транзакция-якорь молча теряется.

Фикс: после каждого успешного ответа Bridge (get_balance / add_transaction / balance_set)
обновляем JSON-кэш (атомарно, tmp + os.replace). При пустом/ошибочном ответе Bridge —
возвращаем кэш. Рестарт splinter кэш не трогает — он на диске.

Структура файла: {"Money Cashflow": {"THB": 25067.0, "EUR": 150.0}, ..., "__at__": {"<кошелёк>": 1755087000.0}}

МЕТКА ВРЕМЕНИ ДОПИСАНА СБОКУ, А НЕ ВМЕСТО (13.08.2026). «Не сверено» без даты неотличимо от «не
сверено пять минут назад» — а решение Пыма зависит именно от неё (см. `balance_fact`). Метки живут
под отдельным ключом `__at__`, а кошельки остаются НА ВЕРХНЕМ УРОВНЕ, как лежали: старый код читает
такой файл без единой правки, и откат не превращает баланс в ноль. Кошелёк с именем `__at__`
метки не получает вовсе — иначе он затёр бы карту времён (единственное столкновение имён, и оно
закрыто здесь, а не оставлено на удачу).
"""
import os
import json
import time
import fcntl
import logging

import balance_fact

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.environ.get("WALLET_CACHE_FILE") or os.path.join(ROOT, "wallet_cache.json")

#: Карта «кошелёк → когда это число было сверено». Имя намеренно непохоже на ярлык группы.
_AT_KEY = "__at__"


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


def save_wallet_balance(wallet: str, balance: dict, at: float = None):
    """Сохранить баланс кошелька (после успешного ответа Bridge).
    balance = {"THB": 25067, "EUR": 150, ...}  — пустой dict игнорируется (не перезаписываем).
    at — когда это число было верно (эпоха UTC); по умолчанию «сейчас»."""
    if not wallet or not balance:
        return
    try:
        with _Lock():
            data = _load()
            data[wallet] = {k: float(v) for k, v in balance.items() if v is not None}
            if wallet != _AT_KEY:
                stamps = data.get(_AT_KEY)
                data[_AT_KEY] = stamps if isinstance(stamps, dict) else {}
                data[_AT_KEY][wallet] = float(time.time() if at is None else at)
            _save(data)
    except Exception:
        log.exception("wallet_cache: не удалось сохранить баланс (не критично)")


def load_wallet_balance(wallet: str) -> dict:
    """Прочитать кэш баланса кошелька. Возвращает dict (может быть {} если нет данных)."""
    if not wallet or wallet == _AT_KEY:
        return {}
    try:
        data = _load()
        got = data.get(wallet, {})
        return got if isinstance(got, dict) else {}
    except Exception:
        return {}


def load_wallet_at(wallet: str):
    """Когда баланс кошелька был сверён (эпоха UTC), либо None — метки нет.

    None — законный и ЧАСТЫЙ ответ: файл, легший прежним кодом, меток не содержит вовсе. Выдумывать
    вместо него «наверное, недавно» нельзя — это ровно та подмена, против которой стоит весь класс.
    """
    if not wallet or wallet == _AT_KEY:
        return None
    try:
        stamps = _load().get(_AT_KEY)
        if not isinstance(stamps, dict):
            return None
        v = stamps.get(wallet)
        return None if isinstance(v, bool) or v is None else float(v)
    except (OSError, TypeError, ValueError):
        return None


def answer(wallet: str, reply: dict):
    """ЦЕЛЫЙ ответ моста `get_balance` → вердикт `balance_fact.Balance` (свежее / не сверено / нет).

    Единственная дверь кассы к числу баланса. Судит ОТВЕТ, а не истинность словаря: `ok` с пустым
    балансом — это честный ноль пустого кошелька, и кэш ему не нужен (BotData.js:881). Кэш
    обновляется ТОЛЬКО свежим числом и вместе с меткой времени."""
    v = balance_fact.balance_verdict(reply, load_wallet_balance(wallet), load_wallet_at(wallet))
    if v.fresh:
        save_wallet_balance(wallet, v.value)
    else:
        log.warning(f"wallet_cache: «{wallet}» — {v.say()}")
    return v


def get_balance_with_fallback(wallet: str, bridge_balance: dict) -> dict:
    """СТАРАЯ ДВЕРЬ: на входе только поле `balance`, без `ok` — различить «мост молчит» и «кошелёк
    пуст» ей НЕЧЕМ по устройству, и поведение остаётся прежним байт-в-байт (истинность словаря).
    Решение при этом одно на обе двери — `balance_fact`, второй реализации тут не заводится.
    Новый код зовёт `answer(wallet, reply)`; эта дверь жива ради путей, где ответ моста уже
    потерян вызывающим (фиксация баланса)."""
    v = balance_fact.balance_verdict(
        {"ok": bool(bridge_balance), "balance": bridge_balance},
        load_wallet_balance(wallet), load_wallet_at(wallet))
    if v.fresh:
        save_wallet_balance(wallet, v.value)
    elif v.value:
        log.warning(f"wallet_cache: Bridge вернул пустой баланс для «{wallet}» — "
                    f"используем кэш {v.value}")
    return v.value
