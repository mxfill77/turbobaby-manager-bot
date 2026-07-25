# -*- coding: utf-8 -*-
"""Лестница моделей Splinter (25.07.2026): касса всегда на тяжёлой; лёгкая поднимается на
пустом/нечитаемом ответе РОВНО один раз; отказ канала модель НЕ меняет. Сети нет — клиент
собирается без __init__, messages.create подменён."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["SPLINTER_LLM_VIA_CLI"] = "0"
os.environ["SPLINTER_MODEL_LIGHT"] = "M-LIGHT"
os.environ["SPLINTER_MODEL_MAIN"] = "M-MAIN"
os.environ["SPLINTER_MODEL_HEAVY"] = "M-HEAVY"

import claude_client as cc
cc._meter_spend = lambda *a, **k: None


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []


class _Blk:
    type = "text"
    def __init__(s, t): s.text = t


class _Usage:
    input_tokens = 11
    output_tokens = 7


class _Resp:
    def __init__(s, txt, model): s.content = [_Blk(txt)]; s.model = model; s.usage = _Usage()


class _Msgs:
    def __init__(s, script): s.script = script; s.calls = []
    def create(s, **kw):
        s.calls.append(kw["model"])
        v = s.script.get(kw["model"], "ответ")
        if isinstance(v, Exception): raise v
        return _Resp(v, kw["model"])


class _Fake:
    def __init__(s, script): s.messages = _Msgs(script)


def client(script):
    c = object.__new__(cc.ClaudeClient)
    c.model = "M-DEFAULT"
    c.client = _Fake(script)
    return c


print("(1) ступени разрешаются из окружения:")
res.append(ok(cc._resolve_tier("LIGHT", "D") == "M-LIGHT", "LIGHT → M-LIGHT"))
res.append(ok(cc._resolve_tier("HEAVY", "D") == "M-HEAVY", "HEAVY → M-HEAVY"))
res.append(ok(cc._resolve_tier(None, "D") == "D", "без ступени → модель клиента"))
res.append(ok(cc._resolve_tier("claude-opus-5", "D") == "claude-opus-5", "прямое имя как есть"))

print("(2) КАССА всегда на тяжёлой и БЕЗ подъёма:")
c = client({})
c.quick("sys", "текст траты", max_tokens=400, raise_on_upstream=True, model="HEAVY", tag="money")
res.append(ok(c.client.messages.calls == ["M-HEAVY"], "касса ушла на M-HEAVY: %s" % c.client.messages.calls))
src = open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read()
m = re.search(r"claude\.quick\(MONEY_SYSTEM[^)]*\)", src, re.S)
res.append(ok(bool(m) and 'model="HEAVY"' in m.group(0), "точка вызова кассы прошита на HEAVY"))
res.append(ok(bool(m) and "escalate_to" not in m.group(0), "у кассы НЕТ подъёма"))
res.append(ok("claude.HEAVY" not in src and "claude.MAIN" not in src and "claude.LIGHT" not in src,
              "ступени строками: обращений к атрибутам клиента нет"))

print("(3) лёгкая поднимается на пустом ответе РОВНО один раз:")
c = client({"M-LIGHT": "   ", "M-MAIN": "готово"})
out = c.quick("sys", "usr", model="LIGHT", tag="translate", escalate_to="MAIN")
res.append(ok(c.client.messages.calls == ["M-LIGHT", "M-MAIN"], "ступени: %s" % c.client.messages.calls))
res.append(ok(out == "готово", "вернулся ответ верхней ступени"))

print("(4) нечитаемый JSON тоже поднимает:")
c = client({"M-LIGHT": "не json", "M-MAIN": '{"a":1}'})
c.quick("sys", "usr", model="LIGHT", escalate_to="MAIN", expect_json=True, tag="intake")
res.append(ok(c.client.messages.calls == ["M-LIGHT", "M-MAIN"], "подъём по JSON: %s" % c.client.messages.calls))

print("(5) хороший ответ подъёма НЕ вызывает:")
c = client({"M-LIGHT": "ок"})
c.quick("sys", "usr", model="LIGHT", escalate_to="MAIN", tag="translate")
res.append(ok(c.client.messages.calls == ["M-LIGHT"], "одна попытка: %s" % c.client.messages.calls))

print("(6) ОТКАЗ КАНАЛА модель НЕ меняет:")
err = cc.AnthropicError("upstream") if hasattr(cc, "AnthropicError") else Exception("upstream")
c = client({"M-LIGHT": err})
out = c.quick("sys", "usr", model="LIGHT", escalate_to="MAIN", tag="translate")
res.append(ok(c.client.messages.calls == ["M-LIGHT"], "вторая ступень НЕ пробовалась: %s" % c.client.messages.calls))
res.append(ok(out == "", "отказ канала деградирует в пустую строку"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
