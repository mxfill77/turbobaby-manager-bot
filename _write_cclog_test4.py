import sys
import asyncio
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

DONE_LINE = "DONE 2026-07-17 UTC (headless): тест 4 — задача получена и выполнена успешно | детали→нет"
PULSE_LINE = "2026-07-17 | 🟢 | тест 4 выполнен | ничего не жду | детали→нет"

async def main():
    client = BridgeClient()

    print("Reading cc_log...")
    result = await client.read_doc(name="cc_log")
    if not result or result.get("status") != "ok":
        print(f"ERROR reading cc_log: {result}")
        return

    content = result.get("content", "")
    print(f"cc_log read ok, length={len(content)}")

    lines = content.split("\n")
    insert_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped):
            insert_idx = i + 1
            break

    if insert_idx is None:
        print("No separator found, prepending at top")
        new_content = DONE_LINE + "\n" + content
    else:
        print(f"Found separator at line {insert_idx - 1}, inserting DONE after it")
        lines.insert(insert_idx, DONE_LINE)
        new_content = "\n".join(lines)

    print("Writing cc_log...")
    write_result = await client.write_doc(name="cc_log", content=new_content)
    if not write_result or write_result.get("status") != "ok":
        print(f"ERROR writing cc_log: {write_result}")
        return
    print(f"cc_log write ok: {write_result}")

    print("Writing pulse...")
    pulse_result = await client.write_doc(name="pulse", content=PULSE_LINE)
    if not pulse_result or pulse_result.get("status") != "ok":
        print(f"ERROR writing pulse: {pulse_result}")
        return
    print(f"pulse write ok: {pulse_result}")

    print("Done.")

asyncio.run(main())
