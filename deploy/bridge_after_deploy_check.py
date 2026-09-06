# -*- coding: utf-8 -*-
"""ПРОВЕРКА МОСТА ПОСЛЕ ДЕПЛОЯ — read-only, в рабочие листы не пишет.

Запуск:  venv/bin/python3 deploy/bridge_after_deploy_check.py [имя-маршрута]
Имя не названо — вычисляется как «каталог сборки МИНУС зеркало».

ПЕРЕНАЦЕЛЕНО НА ЗЕРКАЛО (23.08.2026, шаг 2 цели 102). Прежде скрипт судил прод ДВУМЯ
ЗАХАРДКОЖЕННЫМИ снимками 04.08.2026 — папкой слияния `/root/turbobaby-bridge-merge-*` и
снимком HEAD `/root/_bridge_prod_snapshot_*`. К 23.08 прод уехал @79 → @83, снимок отстал на
четыре версии, и «новый маршрут» вычислялся по мёртвому дереву: ответ был бы не о проде, а о
том, каким прод был три недели назад. Истина о ЗАДЕПЛОЕННОЙ версии живёт в зеркале
`bridge_prod/` под паспортом `MIRROR.json`, поэтому путь считается ОТ КАТАЛОГА ЭТОГО ФАЙЛА
(идиома `deploy/bridge_prod_diff.py`), а не от «/root/…»: репозиторий переносим, снимок — нет.

ТРИ ФАКТА:
  1) ping — жив ли прод-URL после redeploy;
  2) отпечаток: список действий, которым прод ОБЪЯВЛЯЕТ СЕБЯ, против того же списка зеркала —
     разошлись, значит зеркало отстало от прода (или прод от зеркала), и об этом сказано;
  3) РЕШАЮЩИЙ: зовём маршрут с origin=agent и БЕЗ билета. Токен-замок 4.2 такую запись отбивает
     403 `no_ticket` ДО обработчика — в лист не пишется ничего, а ответ отличает «маршрут в
     проде есть» от `unknown_action`. Проба различает состояния, а не подтверждает себя.

ДВА СЛОВАРЯ, И ОНИ РАЗНЫЕ — не путать, иначе привидится расхождение:
  * `case '<имя>':` в `Bridge.js` — МАРШРУТИЗАЦИЯ (на @83 таких меток 89), сюда входят и
    GET-действия; этим словарём выбирается проверяемый маршрут («сборка минус зеркало»);
  * `actions: [...]` в ветке unknown_action — САМООБЪЯВЛЕНИЕ моста, и списков таких в роутере
    ДВА (GET-ветка 9 имён, POST-ветка 67 на @83); с ним сравнивается ответ пробы.
  Каждое сравнивается с себе подобным: 89 против 67 — не расхождение, а разные списки.

FAIL-CLOSED. «Прод судить можно» возвращается РОВНО ОДНИМ путём: зеркало на месте · паспорт
читается · называет версию ЧИСЛОМ · роутер зеркала прочитан · маршруты из него разобраны и их
не ноль · роутер побайтно равен своей записи в паспорте. Всё прочее — ОТКАЗ с НАЗВАННОЙ
причиной и ненулевым кодом: о состоянии прода НЕ заявляем. Прежняя редакция возвращала 0
ВСЕГДА — даже строка «ВЕРДИКТ: маршрута в проде НЕТ» уходила наружу кодом успеха; теперь код
несёт вердикт, потому что вызывающий читает код, а не прозу.

КОДЫ ВЫХОДА: 0 — маршрут в проде ЕСТЬ (подтверждено пробой);
             1 — маршрута в проде НЕТ (прод ответил `unknown_action`);
             2 — судить не на чем (зеркало · паспорт · сборка · сеть · неожиданный ответ).

Ничего не пишет: ни в Google, ни в зеркало, ни в каталог сборки. `clasp` не зовётся вовсе.
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mirror_sync                       # noqa: E402  (чистое решение, импортов у него НОЛЬ)

MIRROR = os.path.join(ROOT, "bridge_prod")     # зеркало = истина о задеплоенной версии
BUILD = os.path.join(ROOT, "bridge_build")     # каталог сборки захода (что предлагали выложить)
PASSPORT = mirror_sync.PASSPORT_NAME           # дом имени паспорта один, у зеркала
ROUTER = "Bridge.js"                           # роутер моста: в нём живут метки маршрутов
PROBE = "zzz_probe_not_a_real_action"

CASE = re.compile(r"case\s+'([a-z0-9_]+)'\s*:")
DECLARED = re.compile(r"actions:\s*\[(.*?)\]", re.S)
NAME = re.compile(r"'([a-z0-9_]+)'")

OK, ROUTE_MISSING, UNVERIFIED = 0, 1, 2


# ─────────────────────────── чистый разбор (без мира) ────────────────────────

def routes_in(text):
    """Метки маршрутизации `case '<имя>':` — словарь РОУТЕРА."""
    return sorted(set(CASE.findall(text)))


def declared_lists(text):
    """Все списки `actions: [...]`, которыми мост объявляет себя в ветке unknown_action.

    Их в роутере ДВА (GET-ветка и POST-ветка), и какая ответит пробе — свойство ПРОБЫ, а не
    файла. Поэтому здесь не угадывается ни одна: наружу идут ОБА, а сравнение ищет тот список,
    с которым живой ответ сошёлся (см. `compare_declared`).
    """
    out = []
    for m in DECLARED.finditer(text):
        names = sorted(set(NAME.findall(m.group(1))))
        if names:
            out.append(names)
    return out


def compare_declared(live, lists):
    """Живой список действий против списков зеркала → (сошёлся, лишние_у_прода, недостающие).

    «Сошёлся» — живой набор РАВЕН какому-нибудь списку зеркала. Не сошёлся — разница считается
    с БЛИЖАЙШИМ (наибольшее пересечение): называть расхождение с заведомо чужой веткой значило
    бы кричать о нём всегда. Зеркало не объявляет ничего → `None`, то есть «сравнивать не с
    чем», а не «сошлось»: третий исход, как везде в этом файле.
    """
    live = sorted(set(live))
    if not lists:
        return None, [], []
    for names in lists:
        if names == live:
            return True, [], []
    best = max(lists, key=lambda n: len(set(n) & set(live)))
    return False, sorted(set(live) - set(best)), sorted(set(best) - set(live))


def pick_route(want, mirror_routes, build_routes, build_why=""):
    """Что проверяем: имя из аргумента либо НОВЫЙ маршрут сборки («сборка минус зеркало»).

    С обеих сторон словарь ОДНОГО рода — метки `case`, поэтому разница означает ровно «этого
    маршрута у задеплоенной версии ещё нет». Возвращает (маршрут, пояснение) либо
    (None, причина отказа) — гадать, какой из нескольких новых проверять, нечем.
    """
    if want:
        return want, "назван аргументом"
    if build_routes is None:
        return None, build_why or "каталога сборки нет — назови имя маршрута аргументом"
    new = sorted(set(build_routes) - set(mirror_routes))
    if len(new) == 1:
        return new[0], "вычислен как «сборка минус зеркало»"
    if not new:
        return None, ("сборка и зеркало называют одни и те же маршруты — нового маршрута нет "
                      "(похоже, зеркало уже сведено после выкладки); назови имя аргументом")
    return None, ("новых маршрутов в сборке %d, а не один: %s; назови имя аргументом"
                  % (len(new), ", ".join(new)))


def verdict(err):
    """Ответ пробы → (код возврата, строка вердикта). Единственное место, где решается исход."""
    if err == "no_ticket":
        return OK, "маршрут в проде ЕСТЬ, запись отбита замком 4.2 (в лист не писали)."
    if err == "unknown_action":
        return ROUTE_MISSING, "маршрута в проде НЕТ — деплой не доехал."
    return UNVERIFIED, ("ответ неожиданный (error=%r) — о маршруте НЕ заявляю, разбирать руками."
                        % (err,))


# ──────────────────────────── руки: чтение с диска ───────────────────────────

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def mirror_facts(mirror_dir=None):
    """Зеркало → факты о задеплоенной версии. Ни одного обращения к сети.

    `ok=True` приходит РОВНО ОДНИМ путём (см. шапку); при отказе `why` называет ПРИЧИНУ —
    тем же приёмом, что `mirror_sync.plan`: молчаливого «ну ладно» здесь не бывает.

    КАТАЛОГ РЕШАЕТСЯ В МОМЕНТ ЗОВА, А НЕ В МОМЕНТ ОБЪЯВЛЕНИЯ (06.09.2026). Прежде умолчание
    было `mirror_dir=MIRROR`, то есть путь связывался при импорте — и подмена `MIRROR` (у
    зовущего, в проверке) на `main()` МОЛЧА не действовала: инструмент судил ЖИВОЕ зеркало,
    думая, что судит названное. Стоило это ложного зелёного и ложного красного сразу: близнец
    «здоровое зеркало доводит до пробы» держался на том, что живое зеркало случайно совпало с
    фикстурой по номеру версии (@83), и покраснел, как только прод уехал на @84, а близнец
    «любая порча даёт ненулевой код» проходил ПО ДРУГОЙ причине (у живого дерева не было нового
    маршрута) — мок, переставший задевать ветку, хуже отсутствующего.
    """
    mirror_dir = MIRROR if mirror_dir is None else mirror_dir
    f = {"ok": False, "why": "", "dir": mirror_dir, "version": None,
         "pulled_utc": None, "routes": [], "declared": []}
    meta_path = os.path.join(mirror_dir, PASSPORT)
    router_path = os.path.join(mirror_dir, ROUTER)

    if not os.path.isdir(mirror_dir):
        f["why"] = "зеркала нет: %s" % mirror_dir
        return f
    try:
        meta = json.loads(_read(meta_path))
    except FileNotFoundError:
        f["why"] = "паспорта зеркала нет: %s" % meta_path
        return f
    except Exception as e:
        f["why"] = "паспорт зеркала не читается (%s: %s)" % (type(e).__name__, e)
        return f
    if not isinstance(meta, dict):
        f["why"] = "паспорт зеркала не объект: %s" % meta_path
        return f

    ver = meta.get("prod_version")
    # тот же различитель, что у `mirror_sync._is_num`: строка «83» версией не считается —
    # зеркало, не умеющее назвать себя числом, судить прод не вправе.
    if not isinstance(ver, int) or isinstance(ver, bool):
        f["why"] = "паспорт не называет версию прода ЧИСЛОМ: %r" % (ver,)
        return f

    try:
        router = _read(router_path)
    except FileNotFoundError:
        f["why"] = "в зеркале нет роутера %s: %s" % (ROUTER, router_path)
        return f
    except Exception as e:
        f["why"] = "роутер зеркала не читается (%s: %s)" % (type(e).__name__, e)
        return f

    # Паспорт против байтов: разошлись — зеркало врёт О СЕБЕ, и списки маршрутов из него
    # недостоверны. Гейт этот замок держит (`tests/test_bridge_prod_mirror.py`), но инструмент
    # не вправе ПРЕДПОЛАГАТЬ, что гейт гоняли: тихо взять правленый роутер за истину о проде —
    # ровно то ложное зелёное, против которого заведён паспорт.
    want_sha = (meta.get("files_sha256") or {}).get(ROUTER)
    if not want_sha:
        f["why"] = "паспорт не называет sha256 для %s — сверить роутер не с чем" % ROUTER
        return f
    got_sha = hashlib.sha256(router.encode("utf-8")).hexdigest()
    if got_sha != want_sha:
        f["why"] = ("роутер зеркала разошёлся с паспортом (%s: %s вместо %s) — зеркало не "
                    "истина о проде, сведи его" % (ROUTER, got_sha[:12], want_sha[:12]))
        return f

    routes = routes_in(router)
    if not routes:
        f["why"] = "в роутере зеркала не разобрано ни одного маршрута: %s" % router_path
        return f

    f.update(ok=True, version=ver, pulled_utc=meta.get("pulled_utc"),
             routes=routes, declared=declared_lists(router))
    return f


def build_routes(build_dir=BUILD):
    """Маршруты каталога сборки захода → (маршруты, "") либо (None, причина).

    Пустого списка отсюда не бывает намеренно: он читался бы как «сборка не знает ни одного
    маршрута», и тогда НОВЫМ оказался бы каждый маршрут зеркала.
    """
    path = os.path.join(build_dir, ROUTER)
    if not os.path.isfile(path):
        return None, "в каталоге сборки нет роутера: %s" % path
    try:
        r = routes_in(_read(path))
    except Exception as e:
        return None, "роутер сборки не читается (%s: %s)" % (type(e).__name__, e)
    if not r:
        return None, "в роутере сборки не разобрано ни одного маршрута: %s" % path
    return r, ""


# ──────────────────────────────── прогон ─────────────────────────────────────

def _probe(route, mirror):
    """Три живых факта. Сеть трогается ТОЛЬКО отсюда; импорт клиента ленивый — чтобы модуль
    можно было прочитать и проверить на моках, не заводя ни .env, ни соединения."""
    os.chdir(ROOT)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from bridge_client import BridgeClient, WRITE_ORIGIN

    c = BridgeClient()

    p = c.ping() or {}
    print("1) ping: ok=%s version=%s status=%s" % (p.get("ok"), p.get("version"), p.get("status")))

    live = []
    for _ in range(2):
        live = (c._post(PROBE) or {}).get("actions") or []
        if live:
            break
    if not live:
        print("2) отпечаток не пришёл (echo-слой моста теряет ответ на POST) — решает пункт 3")
    else:
        same, extra, missing = compare_declared(live, mirror["declared"])
        print("2) прод объявляет действий: %d ; маршрут %r среди них: %s"
              % (len(live), route, route in live))
        if same is None:
            print("   зеркало себя не объявляет — сравнивать не с чем")
        elif same:
            print("   список сошёлся со списком зеркала @%s — прод и зеркало об одном"
                  % mirror["version"])
        else:
            print("   РАСХОЖДЕНИЕ со списком зеркала @%s: у прода сверх зеркала %d (%s); "
                  "в зеркале нет у прода %d (%s)"
                  % (mirror["version"], len(extra), ", ".join(extra) or "—",
                     len(missing), ", ".join(missing) or "—"))
            print("   зеркало отстало — сведи его: venv/bin/python3 deploy/bridge_prod_diff.py")

    WRITE_ORIGIN.set("agent")
    r = c._post(route) or {}
    err = r.get("error")
    print("3) вызов маршрута (origin=agent, без билета): error=%r" % err)
    code, say = verdict(err)
    print("   ВЕРДИКТ: %s" % say)
    if code == UNVERIFIED:
        print("   ответ целиком: %s" % (r,))
    return code


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    want = argv[0].strip() if argv else ""

    m = mirror_facts()
    if not m["ok"]:
        print("ОТКАЗ: %s" % m["why"])
        print("       судить прод нечем: истина о задеплоенной версии — зеркало %s" % MIRROR)
        print("       (паспорт %s). Сведи его и повтори: venv/bin/python3 deploy/bridge_prod_diff.py"
              % PASSPORT)
        return UNVERIFIED
    print("зеркало: версия @%s, снято %s, маршрутов %d"
          % (m["version"], m["pulled_utc"], len(m["routes"])))

    br, why = build_routes()
    route, note = pick_route(want, m["routes"], br, why)
    if not route:
        print("ОТКАЗ: %s" % note)
        return UNVERIFIED
    print("маршрут под проверку: %r (%s); зеркало @%s его знает: %s"
          % (route, note, m["version"], route in m["routes"]))

    try:
        return _probe(route, m)
    except Exception as e:
        print("ОТКАЗ: живой факт не снят (%s: %s) — о состоянии прода НЕ заявляю"
              % (type(e).__name__, e))
        return UNVERIFIED


if __name__ == "__main__":
    sys.exit(main())
