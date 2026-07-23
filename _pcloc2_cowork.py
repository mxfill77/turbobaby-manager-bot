# -*- coding: utf-8 -*-
# Разовая журнальная строка в cowork_log (журнал ПК-репо, Brain) — ритуал turbobaby-userbot:
# правка в ПК-репо завершается записью в его журнал. Препенд сверху, как в cowork_log_append
# на ПК; пишем ТОЛЬКО если read вернул ok (защита от затирки). Зона 🟢 (журнал Brain).
import datetime
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

LINE = ("NOTE Orchestrator-port (VPS, шаг 2/7 родитель 185) "
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        + ": pc_orchestrator — локальный дирижёр-декомпозер кусок 1 (мозг-планировщик) под флагом "
          "PC_LOCAL_DEC (дефолт 0 = поведение прежнее); коммит db4cce3 запушен в main с VPS "
          "git-каналом. На ПК: git pull подтянет, self-update демона прогонит гейт "
          "(сьют 171, новых тестов 17). Релиз шагов цепи — следующие куски порта.")


def main():
    c = BridgeClient()
    r = c._call("read_doc", name="cowork_log")
    if not (isinstance(r, dict) and r.get("ok")):
        print("FAIL read:", str(r)[:200])
        return 1
    old = None
    for key in ("text", "content", "fileContent", "body"):
        if isinstance(r.get(key), str):
            old = r[key]
            break
    if old is None:
        print("FAIL: read ok, но текста нет — не пишу (защита от затирки)")
        return 1
    w = c.write_doc(LINE + "  \n" + old, name="cowork_log")
    if not (isinstance(w, dict) and w.get("ok")):
        print("FAIL write:", str(w)[:200])
        return 1
    print("OK cowork_log, chars:", w.get("chars", "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
