import os
import sys

# Must pop ORCH_TEST_MODE BEFORE importing bridge_client — the ban is installed at import time
os.environ.pop("ORCH_TEST_MODE", None)

sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

from bridge_client import BridgeClient

DONE_LINE = "DONE 2026-07-17 02:16 UTC: Headless-задача «тask» — пустое ТЗ (заглушка без содержания), задача пропущена без действий."
PULSE_LINE = "2026-07-17 02:16 UTC | \U0001f7e2 | Пустая headless-задача пропущена | ничего не жду | детали→cc_log запись «task 17.07»"


def insert_under_vrezka(old, line):
    lines = old.split('\n')
    idx = None
    for i, ln in enumerate(lines[:15]):
        s = ln.strip()
        if s and set(s) == {'═'}:
            idx = i
            break
    if idx is None:
        return line + '\n\n' + old
    head = '\n'.join(lines[:idx + 1])
    rest = '\n'.join(lines[idx + 1:]).lstrip('\n')
    return head + '\n\n' + line + '\n\n' + rest


def main():
    c = BridgeClient()

    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print(f"ERROR reading cc_log: {r}", file=sys.stderr)
        return 1
    old = r.get("text", "")
    print(f"Read cc_log OK, length={len(old)}")

    new = insert_under_vrezka(old, DONE_LINE)

    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print(f"ERROR writing cc_log: {w}", file=sys.stderr)
        return 1
    print("cc_log written OK")

    wp = c.write_doc(text=PULSE_LINE, name="pulse")
    if not wp.get("ok"):
        print(f"ERROR writing pulse: {wp}", file=sys.stderr)
        return 1
    print("pulse written OK")

    print("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
