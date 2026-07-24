# -*- coding: utf-8 -*-
"""Метрики задачи: единый формат строки METRICS (наблюдаемость обеих полос) + norm_effort /
extract_tokens / selfheal_count. Чистые функции, без сети/claude — детерминированный юнит.
Стиль/раннер как у tests/test_executor_model.py (standalone: python3 tests/test_metrics_line.py)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
import task_metrics as M


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

line = M.metrics_line(task=42, lane="vps", model="claude-fable-5", effort="xhigh",
                      start_iso="2026-07-24T14:00:00+00:00", end_iso="2026-07-24T14:00:37+00:00",
                      dur_s=37.4, outcome="done", attempts=1, selfheals=0,
                      tokens_in=1200, tokens_out=340)
exp = ("METRICS task=42 lane=vps model=claude-fable-5 effort=xhigh "
       "start=2026-07-24T14:00:00+00:00 end=2026-07-24T14:00:37+00:00 dur_s=37 "
       "outcome=done attempts=1 selfheals=0 tokens_in=1200 tokens_out=340")
res.append(ok(line == exp, "формат строки METRICS дословно (голден)"))

res.append(ok(M.metrics_line(task=1, lane="vps", model=None, effort="xhigh", start_iso="s",
              end_iso="e", dur_s=0, outcome="failed", attempts=1, selfheals=0).endswith(
              "tokens_in=na tokens_out=na"), "нет токенов / model None -> na"))

res.append(ok(M.norm_effort("XHIGH") == "xhigh" and M.norm_effort("bogus") == "xhigh"
              and M.norm_effort("") == "xhigh" and M.norm_effort(None) == "xhigh"
              and M.norm_effort("max") == "max",
              "norm_effort: регистр/дефолт xhigh/валид"))

res.append(ok(M.extract_tokens({"usage": {"input_tokens": 12, "output_tokens": 3}}) == (12, 3),
              "extract_tokens: usage.input/output_tokens"))
res.append(ok(M.extract_tokens({"modelUsage": {"claude-fable-5": {"inputTokens": 5, "outputTokens": 7}}}) == (5, 7),
              "extract_tokens: сумма modelUsage[*].inputTokens/outputTokens"))
res.append(ok(M.extract_tokens({"modelUsage": {"claude-sonnet-4-6": {
                  "inputTokens": 2, "cacheReadInputTokens": 29339,
                  "cacheCreationInputTokens": 16329, "outputTokens": 8}}}) == (45670, 8),
              "extract_tokens: ПОЛНЫЙ вход input+cacheRead+cacheCreation (живой формат с кэшем)"))
res.append(ok(M.extract_tokens({"usage": {"input_tokens": 2, "cache_read_input_tokens": 100,
                  "cache_creation_input_tokens": 50, "output_tokens": 9}}) == (152, 9),
              "extract_tokens: usage полный вход с кэшем"))
res.append(ok(M.extract_tokens("x") == (None, None) and M.extract_tokens({}) == (None, None),
              "extract_tokens: не-json / пусто -> (None, None)"))

res.append(ok(M.selfheal_count("обычная") == 0
              and M.selfheal_count("[самопочинка задачи 3, попытка 1]") == 1
              and M.selfheal_count("[самопочинка шага 2, попытка 2]") == 2,
              "selfheal_count по маркеру «[самопочинка … попытка N]»"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
