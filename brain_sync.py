#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Синк базы знаний в Brain одной командой: `venv/bin/python3 brain_sync.py <ключ> [...]`.

ЗАЧЕМ ФАЙЛ В РЕПО, А НЕ ЧЕРНОВИК. Правило авто-синка (CLAUDE.md, «ПРАВИЛО ОБНОВЛЕНИЯ БАЗЫ»)
требует зеркалить base-док в Brain по КАЖДОМУ его изменению, молча и без вопросов владельцу —
то есть операция повторяется в каждой задаче, которая трогает `docs/*.md`. Инструмента для неё
на VPS не было, и каждый исполнитель писал свой одноразовый `_*.py` в корне: такие файлы
невидимы для `git status` (маска `_*.py` в .gitignore), копятся молча и обходят проверки. По
правилу R17 «скрипт нужен повторно → это уже не разведка, место в репо осознанное» — вот оно.

ИСТИНА = git (`docs/<ключ>.md`), Drive (KB_*) — ЗЕРКАЛО; откат = повторный синк из git.
Поэтому операция зелёная, несмотря на то что `write_doc` перезаписывает док целиком.

Защита от порчи зеркала: пишем ТОЛЬКО если исходник непустой; после записи ПЕРЕЧИТЫВАЕМ док и
сверяем длину в CODE POINTS (не в байтах — иначе кириллица даёт ложную дельту). Расхождение —
это не «ошибка сети», а расхождение зеркала с истиной, поэтому выход ненулевой и вызывающий код
обязан его увидеть, а не проглотить.

Ключи базы: knowledge_base / project_state / faq / park_list (у FAQ направление синка ОБРАТНОЕ —
канон в Brain; поэтому faq здесь требует явного --force и по умолчанию отказывает).
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")

#: ключ манифеста Brain → файл-истина в git
BASE_DOCS = {
    "knowledge_base": "knowledge_base.md",
    "project_state": "project_state.md",
    "park_list": "park_list.md",
    # ВНИМАНИЕ: у FAQ канон живёт в Brain (KB_faq), а docs/*.md — зеркало. Синк отсюда затёр бы
    # правки, внесённые в канон. Разрешаем только явным --force, чтобы это было решением, а не
    # побочным эффектом «синкнём всё».
    "faq": "turbobaby_faq_v1.md",
}
REVERSE_SYNC = {"faq"}


def check(key: str) -> int:
    """READ-ONLY: сошлось ли зеркало с истиной. 0 — сошлось, 1 — разошлось, 2 — не смог сверить.

    Нужен не «на всякий случай», а по прямому требованию клиента моста: write-POST может
    вернуть `receipt_unknown` (расписка не доехала, а запись — могла), и повторять запрос
    ВСЛЕПУЮ запрещено — вторая отправка положила бы вторую запись. Единственный законный ход в
    этом состоянии — перечитать факт, чем это и является."""
    if key not in BASE_DOCS:
        print(f"❌ {key}: неизвестный ключ базы (знаю: {', '.join(sorted(BASE_DOCS))})")
        return 2
    path = os.path.join(DOCS, BASE_DOCS[key])
    if not os.path.exists(path):
        print(f"❌ {key}: нет исходника {path}")
        return 2
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    from bridge_client import BridgeClient
    # чтение дока идёт через _call («read_doc» — GET-действие, своего метода-обёртки нет;
    # тот же путь, что у cclog.py — единый живой формат ответа {ok, text})
    back = BridgeClient()._call("read_doc", name=key)
    if not isinstance(back, dict) or not back.get("ok"):
        print(f"❌ {key}: перечитать не смог → {back}")
        return 2
    got = back.get("text") or back.get("content") or ""
    delta = len(got) - len(text)
    if delta == 0:
        print(f"✅ {key}: зеркало сошлось с истиной, {len(text)} code points, delta 0")
        print(f"   read back: {got[:200]}".replace("\n", " ⏎ "))
        return 0
    print(f"⚠️ {key}: зеркало РАЗОШЛОСЬ — git {len(text)} ⇄ drive {len(got)} (delta {delta:+d})")
    return 1


def sync(key: str, force: bool = False) -> int:
    """Один док: git → Brain + сверка перечитыванием. 0 — сошлось, иначе ненулевой код."""
    if key not in BASE_DOCS:
        print(f"❌ {key}: неизвестный ключ базы (знаю: {', '.join(sorted(BASE_DOCS))})")
        return 2
    if key in REVERSE_SYNC and not force:
        print(f"⏭ {key}: канон живёт в Brain, направление синка ОБРАТНОЕ — пропускаю "
              f"(нужен --force, если правда хочешь затереть канон зеркалом)")
        return 0

    path = os.path.join(DOCS, BASE_DOCS[key])
    if not os.path.exists(path):
        print(f"❌ {key}: нет исходника {path}")
        return 2
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        print(f"❌ {key}: исходник пуст — зеркало не трогаю")
        return 2

    from bridge_client import BridgeClient
    client = BridgeClient()

    res = client.write_doc(name=key, text=text)
    if not isinstance(res, dict) or not res.get("ok"):
        print(f"❌ {key}: запись не прошла → {res}")
        return 1

    back = client._call("read_doc", name=key)
    if not isinstance(back, dict) or not back.get("ok"):
        print(f"⚠️ {key}: записал, но перечитать не смог → {back}")
        return 1
    got = back.get("text") or back.get("content") or ""
    delta = len(got) - len(text)
    head = got[:200].replace("\n", " ⏎ ")
    if delta != 0:
        print(f"❌ {key}: зеркало разошлось с истиной — git {len(text)} ⇄ drive {len(got)} "
              f"(delta {delta:+d} code points)")
        return 1
    print(f"✅ {key}: Brain synced, {len(text)} code points, delta 0")
    print(f"   read back: {head}")
    return 0


def main(argv) -> int:
    force = "--force" in argv
    only_check = "--check" in argv
    keys = [a for a in argv if not a.startswith("-")]
    if not keys:
        print(__doc__)
        print("ключи:", ", ".join(sorted(BASE_DOCS)))
        return 2
    rc = 0
    for key in keys:
        rc = (check(key) if only_check else sync(key, force=force)) or rc
    return rc


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
