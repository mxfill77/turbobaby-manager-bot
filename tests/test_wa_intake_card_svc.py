#!/usr/bin/env python3
"""A2INTAKE2210 (22.10.2026): флаг службы WA_AGENT_INTAKE_CARD — настоящая `wa_agent_svc.intake_card_of` (в пакете A2
проверялась вырезка с заглушкой). Не запрошен — ничего; запрошен без журнала/транспорта — «не засчитан»; оба есть —
«вкл». Сети, моделей и отправок нет."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wa_agent_svc as S  # noqa: E402


def main():
    bad = 0
    cases = [
        ("не запрошен", S.intake_card_of({}), (None, None)),
        ("«0»", S.intake_card_of({S.F_INTAKE_CARD: "0"}), (None, None)),
    ]
    for name, got, want in cases:
        ok = got == want
        bad += not ok
        print(("PASS " if ok else "FAIL ") + name, got)
    ok, words = S.intake_card_of({S.F_INTAKE_CARD: "1"})
    good = ok is False and "не засчитан" in words
    bad += not good
    print(("PASS " if good else "FAIL ") + "флаг без журнала и транспорта", ok, words[:60])
    ok, words = S.intake_card_of({S.F_INTAKE_CARD: "1"}, journal=object(), transport=object())
    good = ok is True and words.startswith("вкл")
    bad += not good
    print(("PASS " if good else "FAIL ") + "журнал и транспорт есть", ok, words[:60])
    good = S.F_INTAKE_CARD == "WA_AGENT_INTAKE_CARD" and S.F_INTAKE_CARD not in getattr(S, "FLAGS", ())
    bad += not good
    print(("PASS " if good else "FAIL ") + "имя флага, вне FLAGS")
    print("ИТОГ %d/5" % (5 - bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
