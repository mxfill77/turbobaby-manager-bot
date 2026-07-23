"""Read-only живой прогон нового рендера «статус» (реальная очередь + cowork_log)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient
import devbot as DB

b = BridgeClient()
print(DB._g_pulse(b))
