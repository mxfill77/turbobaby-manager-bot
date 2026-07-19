#!/usr/bin/env python3
"""tools/token_audit.py — in-process аудит красных токенов в файлах проекта.

Закрывает класс «аудит токенов сам себя подрывает» (ложные красные 221, 225):
grep-команды для поиска токенов несли сами токены в тексте аргументов —
pretool_guard их перехватывал как красные Python-скрипты.

Решение:
  1. Списки токенов импортируются из pretool_guard в рантайме — ни одного литерала в исходнике.
  2. Сканирование строго in-process (os.walk + file.read), без subprocess/grep/rg.
  3. Токены в отчёте маскируются (первые 4 символа + звёздочки).

Зоны сканирования (--zone):
  preambles  — orchestrator_daemon.py, devbot.py, prompts.py (преамбулы/промпты обоих театров)
  tests      — tests/*.py
  scratchpad — _*.py в корне репо
  configs    — .claude/settings*.json, headless_settings.json
  all        — все зоны (дефолт)

Команда запуска (чистая от красных литералов):
  python3 tools/token_audit.py [--zone <зона>]
"""
import os
import sys
import argparse

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ZONES = ("preambles", "tests", "scratchpad", "configs", "all")


def _load_tokens():
    """Импортировать списки токенов из pretool_guard в рантайме.

    Нет ни одного красного литерала в этом файле — токены живут в pretool_guard.
    Возвращает объединённый дедуплицированный список (RED_TOKENS + _RED_PY_TOKENS).
    Fail-safe: недоступен pretool_guard → пустой список + предупреждение в stderr.
    """
    sys.path.insert(0, PROJECT)
    try:
        import pretool_guard as _g
    except ImportError as exc:
        print(f"⚠️ pretool_guard недоступен: {exc}", file=sys.stderr)
        return []
    seen, result = set(), []
    for tok in list(getattr(_g, "RED_TOKENS", ())) + list(getattr(_g, "_RED_PY_TOKENS", ())):
        if tok and tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


def _mask(tok):
    """Первые 4 символа + звёздочки вместо остального.

    Гарантирует: отчёт не содержит боевых токенов в открытом виде при пересылке в чат.
    Сохраняет длину токена (len(mask) == len(tok)).
    """
    n = 4 if len(tok) >= 6 else max(1, len(tok) // 2)
    return tok[:n] + "*" * (len(tok) - n)


def _scan_file(path, tokens):
    """In-process сканирование одного файла.

    Возвращает list[(lineno, masked_tok, line_preview)].
    Первый хит на строку (остальные той же строки не дублируются).
    """
    hits = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                for tok in tokens:
                    if tok in line:
                        hits.append((lineno, _mask(tok), line.rstrip()[:120]))
                        break
    except OSError:
        pass
    return hits


def _zone_files(zone, project=None):
    """Список файлов для заданной зоны.

    project — корень репо; можно переопределить в тестах.
    """
    root = project or PROJECT
    files = []

    if zone in ("preambles", "all"):
        for name in ("orchestrator_daemon.py", "devbot.py", "prompts.py"):
            p = os.path.join(root, name)
            if os.path.isfile(p):
                files.append(p)

    if zone in ("tests", "all"):
        tests_dir = os.path.join(root, "tests")
        if os.path.isdir(tests_dir):
            try:
                for fn in sorted(os.listdir(tests_dir)):
                    if fn.endswith(".py"):
                        files.append(os.path.join(tests_dir, fn))
            except OSError:
                pass

    if zone in ("scratchpad", "all"):
        try:
            for fn in sorted(os.listdir(root)):
                p = os.path.join(root, fn)
                if fn.startswith("_") and fn.endswith(".py") and os.path.isfile(p):
                    files.append(p)
        except OSError:
            pass

    if zone in ("configs", "all"):
        for rel in (
            ".claude/settings.json",
            ".claude/settings.local.json",
            "headless_settings.json",
        ):
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                files.append(p)

    return files


def run_audit(zone="all", project=None):
    """Выполнить аудит одной зоны.

    Возвращает (report_text: str, total_hits: int, total_files: int).
    """
    tokens = _load_tokens()
    if not tokens:
        return "⚠️ нет токенов (pretool_guard не импортировался?)", 0, 0

    files = _zone_files(zone, project)
    root = project or PROJECT

    header = (
        f"🔍 АУДИТ ТОКЕНОВ — зона: {zone} "
        f"| {len(tokens)} токенов | {len(files)} файлов"
    )
    report_lines = [header]
    total_hits = 0

    for path in files:
        hits = _scan_file(path, tokens)
        if hits:
            total_hits += len(hits)
            rel = os.path.relpath(path, root)
            for lineno, masked, _preview in hits:
                report_lines.append(f"  {rel}:{lineno} → {masked}")

    if total_hits == 0:
        report_lines.append("✅ чисто — токены не найдены")
    else:
        report_lines.append(f"⚠️ итого хитов: {total_hits} в {len(files)} файлах")

    return "\n".join(report_lines), total_hits, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="in-process token audit")
    parser.add_argument("--zone", choices=_ZONES, default="all",
                        help="зона сканирования (дефолт: all)")
    args = parser.parse_args(argv)
    report, _hits, _files = run_audit(args.zone)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
