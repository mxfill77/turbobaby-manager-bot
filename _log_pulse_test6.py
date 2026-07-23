import sys, os
# Allow network even if ORCH_TEST_MODE is set
os.environ['BRIDGE_ALLOW_NETWORK'] = '1'
sys.path.insert(0, '/root/turbobaby-manager-bot')
os.chdir('/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

c = BridgeClient()
pulse = "2026-07-17 UTC | \U0001f7e2 | тест 6 выполнен — контур headless работает | ничего не жду | детали→cc_log запись «тест 6 17.07»"
result = c.write_doc(text=pulse, name="pulse")
print(f"pulse write: {result}")
