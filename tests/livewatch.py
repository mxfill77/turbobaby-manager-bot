# -*- coding: utf-8 -*-
"""СТРАЖ БОЕВЫХ КАТАЛОГОВ СОСТОЯНИЯ — общий инструмент тестов (04.08.2026).

ПОЧЕМУ КЛАСС, А НЕ ЧАСТНОСТЬ. Тест — это фикстура, и её файлы обязаны жить в СВОЁМ временном
каталоге с уникальным суффиксом. Каждый раз, когда тест дотягивался до боевого каталога, платил
владелец: 04.08.2026 тест гейта стёр боевой спул и убил находки; 02.08.2026 (задача 181) фикстура
писала боевой /tmp/cc_guard_block/<живая задача>.json — и владелец получал красную карточку из
фикстуры. Оба раза дефект был НЕВИДИМ: гейт зелёный, а мир изменился.

ПОЧЕМУ СНИМОК «ДО/ПОСЛЕ» НЕ ГОДИТСЯ В ОДИНОЧКУ. Он видит ОСТАТОК, а не ДЕЙСТВИЕ: удаление
несуществующего файла, создание-и-уборка внутри прогона, повторная запись того же содержимого —
всё это снимок пропускает, хотя каждое из них на живом каталоге означало бы стёртую находку.
Поэтому здесь sys.addaudithook: он ловит САМО ОБРАЩЕНИЕ, в момент вызова, включая тот, что не
оставил следа. Именно так и был найден живой случай в tests/test_guard_escalation.py (run_task(88)
чистил боевой /tmp/cc_guard_block/88.json), которого снимок не показывал.

ГРАНИЦА ЧЕСТНО: хук живёт в ЭТОМ процессе. Подпроцессы (хук-фикстуры, гейт) им не покрыты — там
работает прежний приём: подстановка каталога через env + проверка «в боевом ничего не появилось».

Применение:
    import livewatch
    LW = livewatch.watch("/tmp/cc_feed_seen", "/tmp/cc_guard_block")   # ДО импорта модулей!
    ...
    ok(not LW.writes(), "боевых записей нет: %s" % LW.report())
"""
import os
import sys

# Событие open несёт (path, mode, flags): mode — строка builtins.open, None — для os.open.
_WRITE_EVENTS = ("os.mkdir", "os.rmdir", "os.remove", "os.unlink", "os.rename", "os.replace",
                 "os.truncate", "os.chmod", "shutil.rmtree", "shutil.copyfile", "shutil.move")
_ALL_EVENTS = _WRITE_EVENTS + ("open",)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def _is_write(event, args):
    if event != "open":
        return True
    mode = args[1] if len(args) > 1 else None
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    flags = args[2] if len(args) > 2 else None
    if isinstance(flags, int):
        return bool(flags & _WRITE_FLAGS)
    return True                      # не разобрали намерение → считаем записью (fail-closed)


class _Watch(object):
    """Журнал обращений к названным каталогам. Записи копятся, читаются через writes()/report()."""

    def __init__(self, dirs):
        self.dirs = tuple(d.rstrip("/") for d in dirs)
        self.hits = []               # [(event, path, is_write)]
        self._busy = False

    def _match(self, path):
        for d in self.dirs:
            if path == d or path.startswith(d + os.sep):
                return True
        return False

    def __call__(self, event, args):
        if self._busy or event not in _ALL_EVENTS:
            return
        try:
            self._busy = True
            paths = []
            for a in args:
                if isinstance(a, bytes):
                    paths.append(a.decode("utf-8", "replace"))
                elif isinstance(a, str):
                    paths.append(a)
                elif isinstance(a, os.PathLike):
                    paths.append(os.fspath(a))
            for p in paths:
                if self._match(p):
                    self.hits.append((event, p, _is_write(event, args)))
                    break
        except Exception:
            pass
        finally:
            self._busy = False

    def writes(self):
        """Обращения, ИЗМЕНЯЮЩИЕ боевой каталог (создание, запись, удаление, переименование)."""
        return [(e, p) for e, p, w in self.hits if w]

    def reads(self):
        return [(e, p) for e, p, w in self.hits if not w]

    def report(self):
        w = self.writes()
        if not w:
            return "ноль записей (чтений %d)" % len(self.reads())
        return "; ".join("%s → %s" % (e, p) for e, p in w[:8])


def watch(*dirs):
    """Взвести стража. Аудит-хук снять нельзя — поэтому зовём ОДИН раз, в шапке теста."""
    w = _Watch(dirs)
    sys.addaudithook(w)
    return w


# ── СЛОЙ 2: СНИМОК ОСТАТКА ──────────────────────────────────────────────────────────────────
# Нужен рядом с хуком, а не вместо: хук живёт в СВОЁМ процессе и не видит подпроцессов (хук-
# фикстуры, гейт), снимок видит их след. Вместе они закрывают обе стороны.
def snapshot(*dirs):
    """{каталог: [(имя, mtime, sha1-12)] | None}. Хеш обязателен: перезапись тем же размером в ту
    же секунду по одному mtime неотличима от «не трогали»."""
    import hashlib
    out = {}
    for p in dirs:
        try:
            names = sorted(os.listdir(p))
        except OSError:
            out[p] = None                    # каталога нет — тоже факт, и он обязан не измениться
            continue
        items = []
        for n in names:
            f = os.path.join(p, n)
            try:
                with open(f, "rb") as fh:
                    items.append((n, round(os.path.getmtime(f), 3),
                                  hashlib.sha1(fh.read()).hexdigest()[:12]))
            except OSError:
                items.append((n, None, None))
        out[p] = items
    return out


def diff(before, after):
    """Список человекочитаемых расхождений; пустой — каталоги те же."""
    out = []
    for p in sorted(set(before) | set(after)):
        if before.get(p) != after.get(p):
            out.append("%s: %r → %r" % (p, before.get(p), after.get(p)))
    return out
