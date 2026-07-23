# -*- coding: utf-8 -*-
# Журнал-ритуал шага 7/7 родителя 185 в cowork_log (журнал ПК-репо, Brain): препенд сверху,
# пишем ТОЛЬКО если read вернул ok (защита от затирки). Зона 🟢 (журнал Brain).
# Текст строки передаётся первым аргументом (итог самотеста подставляется по факту).
import datetime
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

if len(sys.argv) < 2:
    print("usage: _pcloc7_cowork.py '<строка итога>'")
    sys.exit(2)

LINE = ("DONE Orchestrator-port (VPS, шаг 7/7 родитель 185) "
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        + ": " + sys.argv[1])


def main():
    c = BridgeClient()
    r = c._call("read_doc", name="cowork_log")
    if not (isinstance(r, dict) and r.get("ok")):
        print("FAIL read:", str(r)[:200])
        return 1
    old = None
    for key in ("text", "content", "fileContent", "body"):
        if isinstance(r.get(key), str):
            old = r[key]
            break
    if old is None:
        print("FAIL: read ok, но текста нет — не пишу (защита от затирки)")
        return 1
    w = c.write_doc(LINE + "  \n" + old, name="cowork_log")
    if not (isinstance(w, dict) and w.get("ok")):
        print("FAIL write:", str(w)[:200])
        return 1
    print("OK cowork_log, chars:", w.get("chars", "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
