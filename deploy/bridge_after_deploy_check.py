"""ПРОВЕРКА МОСТА ПОСЛЕ ДЕПЛОЯ — read-only, в рабочие листы не пишет.

Запуск:  venv/bin/python3 deploy/bridge_after_deploy_check.py <имя-нового-маршрута>
Без аргумента имя вычисляется как разница «папка слияния минус снимок HEAD» (если они на месте).

Три факта:
  1) ping — жив ли прод-URL после redeploy;
  2) отпечаток: список действий из ветки unknown_action (справочно — echo-слой моста иногда
     теряет ответ на POST, поэтому решает пункт 3);
  3) РЕШАЮЩИЙ: зовём новый маршрут с origin=agent и БЕЗ билета. Токен-замок 4.2 такую запись
     отбивает 403 `no_ticket` ДО обработчика — в лист не пишется ничего, а ответ отличает
     «маршрут в проде есть» от `unknown_action`. Проба различает состояния, а не подтверждает себя.
"""
import os
import re
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.chdir("/root/turbobaby-manager-bot")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/root/turbobaby-manager-bot/.env")

from bridge_client import BridgeClient, WRITE_ORIGIN  # noqa: E402

MERGE = "/root/turbobaby-bridge-merge-20260804/Bridge.js"
HEAD = "/root/_bridge_prod_snapshot_20260804/head/Bridge.js"
PROBE = "zzz_probe_not_a_real_action"
CASE = re.compile(r"case\s+'([a-z0-9_]+)'\s*:")


def route_from_args():
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    if not (os.path.exists(MERGE) and os.path.exists(HEAD)):
        raise SystemExit("укажи имя маршрута аргументом: снимков для вычисления нет")
    a = set(CASE.findall(open(MERGE, encoding="utf-8").read()))
    b = set(CASE.findall(open(HEAD, encoding="utf-8").read()))
    d = sorted(a - b)
    if len(d) != 1:
        raise SystemExit("ожидался ровно один новый маршрут, вижу: %s" % d)
    return d[0]


def main():
    route = route_from_args()
    c = BridgeClient()

    p = c.ping()
    print("1) ping: ok=%s version=%s status=%s" % (p.get("ok"), p.get("version"), p.get("status")))

    lst = []
    for _ in range(2):
        lst = (c._post(PROBE) or {}).get("actions") or []
        if lst:
            break
    print("2) действий в проде: %d ; маршрут %r перечислен: %s%s"
          % (len(lst), route, route in lst,
             "" if lst else "  (ответ потерян echo-слоем, см. п.3)"))

    WRITE_ORIGIN.set("agent")
    r = c._post(route) or {}
    err = r.get("error")
    print("3) вызов маршрута (origin=agent, без билета): error=%r" % err)
    if err == "unknown_action":
        print("   ВЕРДИКТ: маршрута в проде НЕТ — деплой не доехал.")
    elif err == "no_ticket":
        print("   ВЕРДИКТ: маршрут в проде ЕСТЬ, запись отбита замком 4.2 (в лист не писали).")
    else:
        print("   ВЕРДИКТ: неожиданный ответ, разбирать руками: %s" % r)


main()
