# -*- coding: utf-8 -*-
"""ТРИ СОСТОЯНИЯ КАТАЛОГА СБОРКИ МОСТА — одно правило для всех каталогов сборки (MIRROR88, 13.10.2026).

Правило заведено 06.09.2026 в `tests/test_undo_door.py::test_build_passport_matches_the_mirror_base`
(ветки а/б/в) для `bridge_build/`. Каталоги `bridge_build_contract/` и `bridge_build_tx_find/` знали ОДНО
состояние — «не выложено, база == зеркалу» — и 13.10.2026 на сведении зеркала @84 → @88 покраснели
оба ДОСЛОВНО «зеркало ушло на @88, сборка на @84 — пересобрать», хотя пересобирать нечего: обе двери в
проде с @85. Это тот же ложный красный, который 06.09 лечили для двери отмены; второй копией правила его
не лечим — оно живёт здесь, и оба теста зовут его.

  (а) НЕ ВЫЛОЖЕНА (`delivered_as_version` нет): база сборки — тот самый прод @N, что лежит в зеркале
      (`base_prod_version` == версии зеркала, каждый `base_sha256` == записи зеркала == байтам зеркала),
      добавленных файлов в зеркале нет, файлы сборки == своему `build_sha256`, состав каталога ==
      `changed + added + unchanged` (+ BUILD.json).
  (б) ВЫЛОЖЕНА, зеркало описывает ТУ ЖЕ версию: каждый файл сборки побайтно == своему `build_sha256`
      И записи зеркала И байтам зеркала («в проде ровно то, что здесь лежит»).
  (в) ВЫЛОЖЕНА, прод С ТЕХ ПОР уехал дальше: файлы сборки == своему `build_sha256` (сборка не тронута);
      текущим зеркалом выкладку не сверить — состояние ушло в историю git, и зелёное здесь значит ровно
      это, а не «выкладка сверена».

Направление сомнения — в красное: версия названа не числом (различитель `mirror_sync._is_num` — тот же,
что у машины сведения) · зеркало МЛАДШЕ выкладки · незаявленный файл в каталоге · настройки проекта
(`.clasp.json`) в каталоге · другой script_id. Пишущих вызовов здесь нет: только чтение файлов.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from mirror_sync import _is_num  # noqa: E402  (импортов у mirror_sync ноль)

PASSPORT = "BUILD.json"
MIRROR_PASSPORT = "MIRROR.json"
CLASP = ".clasp.json"


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def judge(build_dir, mirror_dir):
    """→ {'state': 'a'|'b'|'c'|None, 'problems': [...], 'delivered': N|None, 'prod': N}.

    Пустой список problems — каталог согласован с зеркалом в своём состоянии. state None — судить не
    на чем (версия не числом и т.п.), problems тогда не пуст никогда.
    """
    meta = _load(os.path.join(build_dir, PASSPORT))
    mirror = _load(os.path.join(mirror_dir, MIRROR_PASSPORT))
    prob = []
    if os.path.exists(os.path.join(build_dir, CLASP)):
        prob.append("в каталоге сборки настройки проекта %s — из репозитория стало можно залить прод" % CLASP)
    if meta.get("script_id") != mirror.get("script_id"):
        prob.append("script_id сборки %r ≠ зеркала %r" % (meta.get("script_id"), mirror.get("script_id")))
    files = sorted(n for n in os.listdir(build_dir)
                   if os.path.isfile(os.path.join(build_dir, n)) and n != PASSPORT)
    built = meta.get("build_sha256") or {}
    if set(files) != set(built):
        prob.append("каталог и паспорт называют разные файлы: %s" % sorted(set(files) ^ set(built)))
    for n in files:
        if n in built and _sha(os.path.join(build_dir, n)) != built[n]:
            prob.append("%s: файл сборки разошёлся со своим build_sha256" % n)
    prod = mirror.get("prod_version")
    delivered = meta.get("delivered_as_version")

    if delivered is None:                                            # (а)
        if meta.get("base_prod_version") != prod:
            prob.append("зеркало ушло на @%s, сборка на @%s — пересобрать"
                        % (prod, meta.get("base_prod_version")))
        listed = list(meta.get("changed") or []) + list(meta.get("added") or []) \
            + list(meta.get("unchanged") or [])
        if sorted(listed) != files:
            prob.append("состав каталога %s ≠ changed+added+unchanged %s" % (files, sorted(listed)))
        for n, base in sorted((meta.get("base_sha256") or {}).items()):
            mp = os.path.join(mirror_dir, n)
            if base != (mirror.get("files_sha256") or {}).get(n) or not os.path.exists(mp) or _sha(mp) != base:
                prob.append("%s: база сборки разошлась с зеркалом — собери заново поверх свежего прода" % n)
        for n in meta.get("added") or []:
            if os.path.exists(os.path.join(mirror_dir, n)):
                prob.append("%s объявлен новым, а он уже в зеркале" % n)
        return {"state": "a", "problems": prob, "delivered": None, "prod": prod}

    if not (_is_num(delivered) and _is_num(prod)):
        prob.append("версия названа не числом (сборка @%r, зеркало @%r) — судить не на чем" % (delivered, prod))
        return {"state": None, "problems": prob, "delivered": delivered, "prod": prod}
    if prod < delivered:
        prob.append("сборка выложена как @%s, а зеркало описывает @%s — зеркало ОТСТАЛО (или прод откатили)"
                    % (delivered, prod))
        return {"state": None, "problems": prob, "delivered": delivered, "prod": prod}
    if prod == delivered:                                            # (б)
        for n, sha in sorted(built.items()):
            mp = os.path.join(mirror_dir, n)
            if (mirror.get("files_sha256") or {}).get(n) != sha or not os.path.exists(mp) or _sha(mp) != sha:
                prob.append("%s: выложенная сборка разошлась с зеркалом @%s — в проде НЕ то, что здесь" % (n, prod))
        return {"state": "b", "problems": prob, "delivered": delivered, "prod": prod}
    return {"state": "c", "problems": prob, "delivered": delivered, "prod": prod}   # (в)
