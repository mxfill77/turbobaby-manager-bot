#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФИКС B (20.07.2026): тихая потеря TG-карточек needs_approval.

Класс бага: _asked.add(qid) стоял ДО context.bot.send_message → при Telegram-
исключении карточка молча терялась (qid уже «задан», след. тик пропускал его).
Фикс: пометка «отправлено» СТРОГО ПОСЛЕ успешной доставки + ретрай с backoff
(до 3 попыток); провал всех → qid НЕ помечен, уходит на следующий тик. Дублей нет.

Мок ошибки Telegram; НИ сети, НИ реального бота. Запуск: venv/bin/python3 tests/test_devbot_tg_retry.py
"""
import os, sys, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import devbot
devbot._TG_SEND_BACKOFF = 0.0          # без реальных задержек в тесте

TOPIC = 829
MARKUP = object()                       # заглушка reply_markup (kb_approval)


class FakeBot:
    """Бот с расписанием отказов. fail_on_calls — номера вызовов (1-based), которые бросают."""
    def __init__(self, fail_first=0, fail_on_calls=None):
        self.fail_first = fail_first
        self.fail_on_calls = set(fail_on_calls or ())
        self.calls = 0
        self.delivered = []             # успешно доставленные (text, has_markup)

    async def send_message(self, **kw):
        self.calls += 1
        if self.calls <= self.fail_first or self.calls in self.fail_on_calls:
            raise RuntimeError(f"TG hiccup on call {self.calls}")
        self.delivered.append((kw.get("text"), "reply_markup" in kw))
        return object()


class FakeCtx:
    def __init__(self, bot):
        self.bot = bot


_res = []


def ok(cond, msg):
    _res.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'} - {msg}")


async def main():
    print("(A) транзиентный сбой: карточка доезжает СО ВТОРОЙ попытки, без дублей:")
    bot = FakeBot(fail_first=1)
    ctx = FakeCtx(bot)
    r = await devbot._send_card_with_retry(ctx, 99, ["карточка-текст"], TOPIC, MARKUP, "тест")
    ok(r is True, "helper вернул True (доставлено)")
    ok(bot.calls == 2, f"send_message вызван 2x (1 сбой + 1 успех), факт {bot.calls}")
    ok(len(bot.delivered) == 1, f"доставлено РОВНО 1 (нет дублей), факт {len(bot.delivered)}")
    ok(bool(bot.delivered) and bot.delivered[0][1] is True, "reply_markup на единственном чанке")

    print("(B) все попытки падают: helper=False, qid НЕ помечается:")
    bot = FakeBot(fail_first=99)
    ctx = FakeCtx(bot)
    r = await devbot._send_card_with_retry(ctx, 100, ["x"], TOPIC, MARKUP, "тест")
    ok(r is False, "helper вернул False (не доставлено)")
    ok(bot.calls == devbot._TG_SEND_RETRIES, f"ровно {devbot._TG_SEND_RETRIES} попыток, факт {bot.calls}")
    ok(len(bot.delivered) == 0, "ничего не доставлено")

    print("(C) мультичанк: сбой на 2-м чанке -> ретрай ПРОДОЛЖАЕТ с него, чанк0 НЕ дублируется:")
    bot = FakeBot(fail_on_calls={2})    # call1=chunk0 ok, call2=chunk1 fail, call3=chunk1 ok
    ctx = FakeCtx(bot)
    r = await devbot._send_card_with_retry(ctx, 101, ["chunk-0", "chunk-1"], TOPIC, MARKUP, "тест")
    ok(r is True, "helper вернул True")
    ok(bot.calls == 3, f"3 вызова (c0 ok, c1 fail, c1 ok), факт {bot.calls}")
    texts = [t for t, _ in bot.delivered]
    ok(texts == ["chunk-0", "chunk-1"], f"каждый чанк доставлен по 1 разу, факт {texts}")

    print("(D) тик-к-тику: провал -> не помечен -> 2-й тик доставляет -> 3-й тик НЕ дублирует:")
    devbot._asked.discard(42)
    # тик1: постоянный сбой
    bot1 = FakeBot(fail_first=99)
    ctx1 = FakeCtx(bot1)
    if 42 not in devbot._asked:
        if await devbot._send_card_with_retry(ctx1, 42, ["карта"], TOPIC, MARKUP, "тест"):
            devbot._asked.add(42)
    ok(42 not in devbot._asked, "после провала qid НЕ в _asked (уйдёт на след. тик)")
    # тик2: успех
    bot2 = FakeBot(fail_first=0)
    ctx2 = FakeCtx(bot2)
    if 42 not in devbot._asked:
        if await devbot._send_card_with_retry(ctx2, 42, ["карта"], TOPIC, MARKUP, "тест"):
            devbot._asked.add(42)
    ok(42 in devbot._asked, "после успеха qid помечен")
    ok(len(bot2.delivered) == 1, "во 2-м тике доставлено 1")
    # тик3: уже помечен → не шлём (нет дубля)
    sent_third_tick = (42 not in devbot._asked)
    ok(sent_third_tick is False, "3-й тик НЕ шлёт повтор (нет дубля)")
    devbot._asked.discard(42)

    fails = _res.count(False)
    verdict = "ВСЕ PASS" if fails == 0 else f"ЕСТЬ FAIL ({fails}/{len(_res)})"
    print(f"\nИТОГ: {verdict}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
