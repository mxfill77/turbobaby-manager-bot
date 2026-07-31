"""Проба ПАМЯТИ живого процесса: какой код процесс РЕАЛЬНО держит, а не какой лежит на диске.

ЗАЧЕМ ЖИВЁТ В РЕПО (а не разовой разведкой в /tmp, класс R17). За 31.07.2026 эта проба дважды
дала доказательство выкатки, которого не даёт больше ничто: совпадение времени старта сервиса с
временем коммита доказательством НЕ является (процесс мог стартовать до/после, юнит мог быть
перезапущен по другой причине, зеркало на диске мог обновить кто угодно), а импортированный
модуль на диске — тем более. Здесь читаются САМИ БАЙТЫ процесса: если имя функции из нового
коммита найдено в его памяти, новый код в нём есть; если найдено имя, оставшееся только в
старой версии, — процесс держит старый код. Это единственная проверка «выкатка доехала», которая
не опирается на чужие обещания.

ЗАПУСК (read-only, процесс не останавливается, сигналов не шлём):
    venv/bin/python3 mem_probe.py <pid> <зонд1> [зонд2 ...]
    venv/bin/python3 mem_probe.py 1234 _rollback_km_events _km_conf_ok _write_info_works

КАК ВЫБИРАТЬ ЗОНДЫ (иначе проба соврёт):
  · зонд — ASCII-идентификатор из кода (имя функции/переменной). В CPython такие строки лежат
    в памяти дословными байтами (kind=UCS1); кириллица лежит как UCS2 и по байтам не совпадёт;
  · нужен КОНТРОЛЬ — имя, которое есть и в старой, и в новой версии: если контроль не найден,
    проба ничего не доказала (не тот pid, регионы не прочитались), а не «кода нет»;
  · нужны имена, РАЗЛИЧАЮЩИЕ версии: одно только-старое, одно только-новое. Сверять по git ДО
    прогона;
  · ЗАГРЯЗНЕНИЕ ТЕКСТОМ: если имя зонда процитировано в отчёте/логе/задаче, которую процесс
    держит в памяти, оно найдётся и БЕЗ этого кода. Берите имена, которые нигде не цитировались,
    и не считайте одно вхождение доказательством.

МЕХАНИКА: обычный pread по /proc/<pid>/mem в границах читаемых регионов /proc/<pid>/maps.
Без ptrace-attach, без остановки, без записи. Нужны права на процесс (свой uid либо root; при
ptrace_scope=1 чужой процесс читается только от root или из процесса-родителя).
"""
import os
import sys

CHUNK = 4 << 20          # 4 МиБ за чтение
OVERLAP = 64             # склейка на стыке кусков: зонд не потеряется на границе
# Псевдо-файлы, читать которые бессмысленно или вредно (vvar/vsyscall дают EIO, /dev/* — устройства)
SKIP_PATHS = ("[vvar]", "[vsyscall]", "[vvar_vclock]")


def read_regions(pid):
    """Читаемые регионы памяти процесса: [(lo, hi, perms, path), …]."""
    regions = []
    with open(f"/proc/{pid}/maps", "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5:
                continue
            addr, perms = parts[0], parts[1]
            path = parts[5] if len(parts) > 5 else ""
            if "r" not in perms:
                continue
            if path in SKIP_PATHS or path.startswith("/dev/"):
                continue
            lo, hi = (int(x, 16) for x in addr.split("-"))
            regions.append((lo, hi, perms, path))
    return regions


def probe(pid, names):
    """Сосчитать вхождения каждого зонда в памяти процесса.
    Возврат: (hits {зонд: число}, stats {scanned_bytes, regions, unreadable}).
    Нечитаемый регион пропускаем и считаем в unreadable — это норма (страницы уезжают под нами),
    но если unreadable велик, а контрольный зонд не найден, проба НИЧЕГО не доказала."""
    pats = {n: n.encode("ascii", "strict") for n in names}
    hits = {n: 0 for n in names}
    regions = read_regions(pid)
    scanned = unreadable = 0
    with open(f"/proc/{pid}/mem", "rb", buffering=0) as mem:
        for lo, hi, _perms, _path in regions:
            pos, tail = lo, b""
            while pos < hi:
                n = min(CHUNK, hi - pos)
                try:
                    mem.seek(pos)
                    buf = mem.read(n)
                except (OSError, ValueError, OverflowError):
                    unreadable += 1
                    break
                if not buf:
                    break
                scanned += len(buf)
                hay = tail + buf
                for name, pat in pats.items():
                    hits[name] += hay.count(pat)
                tail = buf[-OVERLAP:]
                pos += len(buf)
    return hits, {"scanned_bytes": scanned, "regions": len(regions), "unreadable": unreadable}


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[0])
        print("использование: mem_probe.py <pid> <зонд1> [зонд2 ...]")
        return 2
    try:
        pid = int(argv[1])
    except ValueError:
        print(f"pid должен быть числом, получено: {argv[1]!r}")
        return 2
    names = argv[2:]
    try:
        hits, st = probe(pid, names)
    except FileNotFoundError:
        print(f"процесса {pid} нет (или /proc недоступен)")
        return 1
    except PermissionError:
        print(f"нет прав читать память процесса {pid} — нужен root либо свой процесс")
        return 1
    except UnicodeEncodeError:
        print("зонды должны быть ASCII: имена функций/переменных, не кириллица (см. шапку файла)")
        return 2
    print(f"PID={pid}  прочитано={st['scanned_bytes'] / 1048576:.1f} МиБ  "
          f"регионов={st['regions']}  недоступных={st['unreadable']}")
    print()
    width = max(len(n) for n in names)
    for n in names:
        mark = "НАЙДЕН" if hits[n] else "не найден"
        print(f"  {n:{width}s}  вхождений={hits[n]:<6d} {mark}")
    print()
    print("напоминание: без контрольного зонда (есть в обеих версиях) результат ничего не "
          "доказывает; процитированное в отчётах имя может найтись и без своего кода.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
