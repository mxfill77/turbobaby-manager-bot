import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
import asyncio
from datetime import datetime, timezone

async def main():
    bc = BridgeClient()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    # Read cc_log
    result = await bc.read_doc('cc_log')
    if result.get('status') != 'ok':
        print(f"ERROR read cc_log: {result}")
        return

    content = result.get('content', '')

    # Find separator line (═-only line)
    lines = content.split('\n')
    sep_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped) and len(stripped) >= 5:
            sep_idx = i
            break

    new_entry = f"DONE {now}: задача «тест 1» выполнена — тестовая задача из оркестратора, проверка цепочки 328→демон→headless-CC; гейт не запускался (read-only задача)"

    if sep_idx is not None:
        lines.insert(sep_idx + 1, new_entry)
        new_content = '\n'.join(lines)
    else:
        new_content = new_entry + '\n' + content

    wr = await bc.write_doc('cc_log', new_content)
    print(f"cc_log write: {wr.get('status')}")

    # Update pulse
    pulse_line = f"{now} | 🟢 | задача «тест 1» выполнена — тест оркестратора прошёл | ничего не жду | детали→cc_log запись «тест 1 {now[:10]}»"
    pr = await bc.write_doc('pulse', pulse_line)
    print(f"pulse write: {pr.get('status')}")

asyncio.run(main())
