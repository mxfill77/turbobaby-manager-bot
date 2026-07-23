"""Read-only: искать построчную рамку/инструкции приложения (30.06) в архиве и cc_log."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
for name in ("cc_log_archive", "cc_log"):
    r = c._call("read_doc", name=name)
    lines = r.get("text", "").split("\n")
    print(f"===== {name} ({len(lines)} lines) =====")
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(k in low for k in ("построчн", "строка-в-строку", "инструкции проекта", "приложении claude",
                                  "приложение claude", "сверка рамки", "сверку рамки", "рамка владельца",
                                  "рамку владельца")):
            print(f"{i:5} | {ln[:170]}")
