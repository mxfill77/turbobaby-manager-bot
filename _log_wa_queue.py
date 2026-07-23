import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
import asyncio, datetime

async def main():
    bc = BridgeClient()

    # Read cc_log first
    result = await bc.read_doc(name='cc_log')
    if not result or result.get('status') != 'ok':
        print("ERROR: cannot read cc_log:", result)
        return

    content = result.get('content', '')

    # Find the header block (line of ═ characters)
    lines = content.split('\n')
    header_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped) and i > 0:
            header_end = i
            break

    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    new_entry = f"DONE {now}: [read-only] wa_queue.db проверен — таблица wa_inbox, 0 строк (очередь пуста), размер 20 КБ, последнее изменение 2026-07-16 08:17 UTC. Схема: id/ts_queued/channel/from_number/name/msg_type/text/media_id/ts_msg/echo/history/status/raw/wamid."

    if header_end > 0:
        before = '\n'.join(lines[:header_end+1])
        after = '\n'.join(lines[header_end+1:])
        new_content = before + '\n' + new_entry + ('\n' + after if after.strip() else '')
    else:
        new_content = new_entry + '\n' + content

    write_result = await bc.write_doc(name='cc_log', content=new_content)
    print("cc_log write:", write_result)

    # Update pulse
    pulse_line = f"{now} | 🟢 | wa_queue.db проверен: wa_inbox 0 строк, очередь пуста, 20КБ, mtime 2026-07-16 08:17 UTC | ничего не жду | детали→cc_log запись {now}"
    pulse_result = await bc.write_doc(name='pulse', content=pulse_line)
    print("pulse write:", pulse_result)

asyncio.run(main())
