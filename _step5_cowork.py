"""Разовый ритуал ПК-репо: DONE-строка в cowork_log (журнал Brain, зона 🟢) — read→prepend→write,
пишем ТОЛЬКО если read вернул ok (защита от затирки; зеркало cowork_log_append из ПК-репо,
но через .env manager-bot: в клоне _pcport185 своего .env нет)."""
import datetime
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

MSG = ("DONE VPS-headless (шаг 5/7 родитель 185): красная механика локальной цепи pcloc-dec — "
       "кнопка/ожидание/approve-продолжение/reject-и-таймаут-halt без думателя, коммит 2d58e9f; "
       "парный коммит manager-bot вносит Filipp-pcloc-dec в devbot QUEUE_FROMS_PC (карточки в "
       "инбокс 1160). Тесты TestLocalDecRed 8/8, сьют 222.")

c = BridgeClient()
r = c._call("read_doc", name="cowork_log")
if not (isinstance(r, dict) and r.get("ok")):
    raise SystemExit(f"read_doc cowork_log не ok — НЕ пишу: {r}")
old = None
for key in ("text", "content", "fileContent", "body"):
    if isinstance(r.get(key), str):
        old = r[key]
        break
if old is None:
    raise SystemExit("read_doc ok, но текста нет — НЕ пишу, чтобы не затереть")
w = c.write_doc(MSG + "  \n" + old, name="cowork_log")
print("write_doc:", w.get("ok"), w.get("chars"))
