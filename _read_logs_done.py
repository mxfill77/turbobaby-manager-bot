import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
import asyncio, datetime

UTC = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

LOG_LINE = (
    f"DONE {UTC}: [read logs] splinter active 17h, 0 errors. "
    "1 WARNING max_tokens при декомпозиции родитель 185 (02:34 UTC). "
    "Memory: free 250MB, swap 1506/2047MB (73%) — много claude-процессов в демоне."
)

PULSE_LINE = (
    f"{UTC} | 🟡 | Логи прочитаны: splinter ok, swap 73%, 1 max_tokens warning | "
    "ничего не жду | детали→cc_log DONE read logs"
)

async def main():
    bc = BridgeClient()
    # read cc_log
    res = await bc.read_doc(name='cc_log')
    if not res or res.get('status') != 'ok':
        print('ERROR: cc_log read failed', res)
        return
    old = res.get('content', '')
    # find header boundary (═-only line)
    lines = old.split('\n')
    boundary = -1
    for i, l in enumerate(lines):
        if l and all(c == '═' for c in l.strip()) and i > 0:
            boundary = i
            break
    if boundary >= 0:
        new_content = '\n'.join(lines[:boundary+1]) + '\n' + LOG_LINE + '\n' + '\n'.join(lines[boundary+1:])
    else:
        new_content = LOG_LINE + '\n' + old

    res2 = await bc.write_doc(name='cc_log', content=new_content)
    print('cc_log write:', res2.get('status') if res2 else 'FAIL')

    res3 = await bc.write_doc(name='pulse', content=PULSE_LINE)
    print('pulse write:', res3.get('status') if res3 else 'FAIL')

asyncio.run(main())
