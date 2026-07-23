import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
os.chdir('/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
import asyncio

DONE_LINE = "DONE 2026-07-17 UTC (headless): задача «задача мусор» — нет actionable содержимого, пропущена как мусор."
PULSE_LINE = "2026-07-17 | 🟢 | задача «задача мусор» получена и пропущена (нет содержимого) | ничего не жду | детали→cc_log"

async def main():
    client = BridgeClient()

    # Step 1: Read cc_log
    result = await client.read_doc(name='cc_log')
    if not result:
        print("error: read_doc returned empty/None")
        return

    content = result if isinstance(result, str) else str(result)

    # Step 2: Find the closing ═-only line of the header block
    lines = content.split('\n')
    header_close_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped):
            header_close_idx = i
            break

    if header_close_idx is None:
        # No header found, just prepend
        new_content = DONE_LINE + '\n' + content
    else:
        # Insert DONE line right after the closing ═-only line
        before = lines[:header_close_idx + 1]
        after = lines[header_close_idx + 1:]
        new_lines = before + [DONE_LINE] + after
        new_content = '\n'.join(new_lines)

    # Step 3: Write cc_log back
    write_result = await client.write_doc(name='cc_log', content=new_content)
    if not write_result:
        print("error: write_doc cc_log returned empty/None")
        return

    # Step 4: Write pulse
    pulse_result = await client.write_doc(name='pulse', content=PULSE_LINE)
    if not pulse_result:
        print("error: write_doc pulse returned empty/None")
        return

    print("logged")

asyncio.run(main())
