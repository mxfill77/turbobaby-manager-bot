# -*- coding: utf-8 -*-
"""«ПРОД ВПЕРЕДИ?» — ОТВЕЧАЕТ КОМАНДА, А НЕ ГЛАЗ (заведено 10.08.2026).

Зачем: до сегодняшнего дня расхождение «локальная папка vs прод» ловилось вручную — сверкой
mtime, .bak-снимков и памяти исполнителя. Так уже терялась работа (класс 04.08: папка выглядела
готовой к выкладке, а была ПОЗАДИ прода на трёх действиях). Теперь содержимое моста лежит под
git в `bridge_prod/`, и вопрос закрывается одной командой.

    venv/bin/python3 deploy/bridge_prod_diff.py [каталог-снимков]

Что делает: снимает read-only отпечаток моста (`bridge_prod_recon.py` — только GET'ы) и сравнивает
ДВА живых состояния с зеркалом в git:
  * задеплоенная версия @N  — что сейчас обслуживает BRIDGE_URL;
  * HEAD проекта            — то, что перезаписал бы push и чего по URL не видно вовсе.

Коды выхода: 0 — зеркало == прод == HEAD (расхождений нет); 1 — расхождение, названо поимённо;
2 — отпечаток снять не удалось (о состоянии прода НЕ заявляем).

Read-only: ничего не пишет ни в Google, ни в зеркало.
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "bridge_prod")
RECON = os.path.join(ROOT, "deploy", "bridge_prod_recon.py")
PY = os.path.join(ROOT, "venv", "bin", "python3")
DEFAULT_SNAP = "/root/_bridge_prod_snapshot"
META = "MIRROR.json"          # паспорт зеркала, у прода такого файла нет по устройству


def _local_only(name):
    """Местные файлы зеркала, которых у моста не бывает ПО УСТРОЙСТВУ — из сверки вон.

    Apps Script знает три вида файлов: SERVER_JS (.js), HTML и JSON — документации (.md) в
    проекте не бывает вовсе, паспорт зеркала тоже наш. Не исключи их — команда кричала бы о
    расхождении ВСЕГДА и перестала бы что-либо значить (поймано живым прогоном 10.08.2026:
    README зеркала выдавал себя за «прод впереди»).
    """
    return name == META or name.lower().endswith(".md")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _hashes(folder):
    out = {}
    for n in sorted(os.listdir(folder)):
        p = os.path.join(folder, n)
        if os.path.isfile(p) and not _local_only(n):
            out[n] = _sha(p)
    return out


def compare(mirror_dir, live_dir):
    """Чистое сравнение двух каталогов по содержимому. Ничего не читает сверх них.

    Возвращает {'same': [...], 'changed': [...], 'only_mirror': [...], 'only_live': [...]}.
    'only_live' = у живого моста есть файл, которого нет в зеркале — прод ВПЕРЕДИ.
    """
    m = _hashes(mirror_dir)
    l = _hashes(live_dir)
    same, changed = [], []
    for n in sorted(set(m) & set(l)):
        (same if m[n] == l[n] else changed).append(n)
    return {
        "same": same,
        "changed": changed,
        "only_mirror": sorted(set(m) - set(l)),
        "only_live": sorted(set(l) - set(m)),
    }


def is_clean(res):
    """Расхождений нет ровно тогда, когда нет ни изменённых, ни односторонних файлов."""
    return not (res["changed"] or res["only_mirror"] or res["only_live"])


def _say(title, res):
    print("--- %s ---" % title)
    print("  совпадает: %d" % len(res["same"]))
    for k, label in (("changed", "РАЗЛИЧАЕТСЯ"),
                     ("only_live", "ЕСТЬ У МОСТА, НЕТ В ЗЕРКАЛЕ (прод впереди)"),
                     ("only_mirror", "ЕСТЬ В ЗЕРКАЛЕ, НЕТ У МОСТА")):
        if res[k]:
            print("  %s: %d — %s" % (label, len(res[k]), ", ".join(res[k])))
    print("  вердикт: %s" % ("совпадает" if is_clean(res) else "РАСХОЖДЕНИЕ"))


def main():
    snap = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SNAP
    if not os.path.isdir(MIRROR):
        print("зеркала нет: %s — сначала заведи его отпечатком прода" % MIRROR)
        return 2

    mine = json.load(open(os.path.join(MIRROR, META), encoding="utf-8"))
    print("зеркало в git: версия @%s, снято %s" % (mine.get("prod_version"), mine.get("pulled_utc")))

    print("снимаю отпечаток моста (read-only)…")
    r = subprocess.run([PY, RECON, snap], capture_output=True, text=True, timeout=600)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        print("ОТПЕЧАТОК НЕ СНЯТ (код %d) — о состоянии прода не заявляю" % r.returncode)
        return 2

    meta = json.load(open(os.path.join(snap, "meta.json"), encoding="utf-8"))
    ver = meta.get("prod_version")
    print()
    print("прод обслуживает версию @%s; в зеркале @%s" % (ver, mine.get("prod_version")))

    live_prod = os.path.join(snap, "prod_v%s" % ver)
    live_head = os.path.join(snap, "head")
    rp = compare(MIRROR, live_prod)
    _say("зеркало против задеплоенной версии @%s" % ver, rp)
    rh = compare(MIRROR, live_head)
    _say("зеркало против HEAD проекта (его перезаписал бы push)", rh)

    ok = is_clean(rp) and is_clean(rh) and str(ver) == str(mine.get("prod_version"))
    print()
    if ok:
        print("ИТОГ: зеркало == прод == HEAD. Выкладка ничего чужого не сотрёт.")
        return 0
    print("ИТОГ: РАСХОЖДЕНИЕ. Прод/HEAD ушли вперёд зеркала — обнови зеркало ДО любой сборки,")
    print("      иначе заливка сотрёт названное выше молча.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
