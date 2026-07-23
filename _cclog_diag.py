import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')
import cclog
cclog.log("DONE", """Диагностика Bridge/очередь/касса 14-15.07 (read-only, задача оркестратора):
(1) Bridge: v1.0.0, пинг ОК 2026-07-15T06:28:54Z. Деплой 14.07 ~13:35 UTC — delivery zones (Bridge.js+Delivery.js). Commit 1caaab5 (15.07) = bridge_deploy.py инструмент, Bridge.js НЕ менял.
(2) «Очередь недоступна» = Bridge timeout на get_pending (error='timeout', bridge_client._one_exchange L157). Окно: 14.07 01:16–08:16 UTC (_poll_bridge 15s таймаут, 3 ретрая подряд). _queue_snapshot→None→'⚠️ очередь не опросилась'; build_inbox→'📥 Инбокс: очередь недоступна (timeout)'. В 08:36 splinter перезапустился — Bridge восстановился.
(3) Счётчик 23→36: СБРОСА НЕТ. Текущий снимок очереди ID 1–42, 0 пропусков (42 items, no gaps). Задачи 24–35 = synthetic Filipp-pcloc-dec шаги (в очереди 26 из 42 pcloc-dec), быстро processed без Telegram-уведомлений. Лист не пересоздавался.
(4) Col N / касса: computeBalance_ читает col 3–12, col 14 (booking_id) не трогает. Self-heal заголовка безвреден. Обнуление баланса (15.07 04:31 UTC, Pleummmm -6000) = Bridge.get_balance()→{} при Bridge-лаге (devbot_report missed ×3 в том же окне). ОБЩИЙ КОРЕНЬ: Bridge timeouts. Delivery deploy (13:35 UTC) НЕ причина утренних таймаутов (01:16 UTC — за 12 ч до деплоя).""")
