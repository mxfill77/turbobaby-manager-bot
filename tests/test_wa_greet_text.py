#!/usr/bin/env python3
"""GREETTEXT2210 (22.10.2026, Codex TB-AGENT-CRITERIA-2210-OWNER-REVIEW): текст отправленного автоприветствия в строке
модели — только при ручке WA_AGENT_GREET_TEXT, с происхождением «рекламный автотекст, не обещание»; без ручки строка
прежняя байт-в-байт. Синтетика: ни баз, ни сети, ни модели."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wa_history as H  # noqa: E402

GREET = "Здравствуйте!  Аренда SYN-150, SYN-900\n и SYN-7 от 199 ฿/сутки."
ITEMS = [{"key": "wamid.SYN1", "ts": 1_800_000_000, "who": "мы", "text": GREET, "word": None, "file": None},
         {"key": "wamid.SYN2", "ts": 1_800_000_050, "who": "клиент", "text": "есть ли SYN-900?", "word": None,
          "file": None}]
GREETS = [(1, "wamid.SYN1", 1_800_000_000), (2, "wamid.SYN9", 1_800_000_100)]


def main():
    bad = 0

    def check(name, ok, got=""):
        nonlocal bad
        bad += not ok
        print(("PASS " if ok else "FAIL ") + name, "" if ok else repr(got)[:300])

    os.environ.pop(H.F_GREET_TEXT, None)
    out = H.with_greets(ITEMS, GREETS)
    auto = [it for it in out if it.get("auto")]
    check("две строки автоприветствия, текст очереди сохранён отдельно", len(auto) == 2
          and auto[0]["text"] == H.GREET_WORDS and auto[0]["auto_text"] == GREET and "auto_text" not in auto[1], auto)
    old = "%s · мы · %s" % (H.pk_full(ITEMS[0]["ts"]), H.GREET_WORDS)
    check("ручка не задана — строка прежняя", H.model_line(auto[0]) == old, H.model_line(auto[0]))
    os.environ[H.F_GREET_TEXT] = "0"
    check("ручка 0 — строка прежняя", H.model_line(auto[0]) == old)
    os.environ[H.F_GREET_TEXT] = "1"
    line = H.model_line(auto[0])
    check("ручка 1 — текст с происхождением, пробелы свёрнуты",
          line == "%s · мы · %sЗдравствуйте! Аренда SYN-150, SYN-900 и SYN-7 от 199 ฿/сутки." % (
              H.pk_full(ITEMS[0]["ts"]), H.GREET_TEXT_HEAD), line)
    check("происхождение: не обещание, наличие по парку", "не персональное обещание" in line and "парку" in line)
    check("строка без текста (только запись autogreet) — прежняя", H.model_line(auto[1]).endswith("· мы · " + H.GREET_WORDS))
    long_it = dict(auto[0], auto_text="x" * 5000)
    check("потолок длины", len(H.model_line(long_it)) <= len(old) + len(H.GREET_TEXT_HEAD) + H.GREET_TEXT_MAX + 5)
    check("ответ клиента не тронут", H.model_line(out[1]).endswith("клиент: есть ли SYN-900?"))
    os.environ.pop(H.F_GREET_TEXT, None)
    print("ИТОГ %d/8" % (8 - bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
