# -*- coding: utf-8 -*-
"""Снимки ответов двери договоров (AGENTFIX0410): `contractFind` исполняется харнессом самой двери
(tests/contract_door_gs_harness.js --snap) на её же мок-реестре — подмены агента берут ответ, который вернул код двери,
без правок и без выдуманных полей. `override` — исходники моста вместо файлов (мутант двери), как `--stdin` харнесса.

Node нет или харнесс упал — исключение, а не пустой словарь: тест без снимка не может стать зелёным."""

import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "contract_door_gs_harness.js")
_CACHE = {}


def snaps(override=None):
    key = json.dumps(override, sort_keys=True) if override is not None else ""
    if key not in _CACHE:
        args = ["node", HARNESS, "--snap"] + (["--stdin"] if override is not None else [])
        proc = subprocess.run(args, input=key if override is not None else None, capture_output=True,
                              text=True, encoding="utf-8", timeout=60, cwd=os.path.dirname(HERE))
        if proc.returncode != 0:
            raise RuntimeError("харнесс двери договоров упал: %s" % (proc.stderr or proc.stdout)[-400:])
        _CACHE[key] = json.loads(proc.stdout)["snaps"]
    return json.loads(json.dumps(_CACHE[key]))            # копия: тест не портит общий снимок


def snap(name, override=None):
    return snaps(override)[name]


def source(name):
    """Исходник моста так, как его берёт харнесс (srcOf): сборка bridge_build_contract/, иначе зеркало bridge_prod/."""
    root = os.path.dirname(HERE)
    p = os.path.join(root, "bridge_build_contract", name)
    if not os.path.exists(p):
        p = os.path.join(root, "bridge_prod", name)
    with open(p, encoding="utf-8") as fh:
        return fh.read()
