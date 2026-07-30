#!/usr/bin/env python3
"""ЗАМЕР ГАРДА: реплей боевых Bash-команд через классификатор pretool_guard. READ-ONLY.

Зачем инструмент, а не разведочный скрипт (правило R17): замер «сколько карточек владельцу было /
станет» требуется КАЖДОЙ правкой гарда — за 29–30.07.2026 он понадобился трижды (карточка-минимум,
единое правило полос, разбор шума). Разведка, которую зовут повторно, — уже код репо: имя без «_»,
файл отслеживаемый, поведение под тестом (tests/test_guard_replay.py).

ИСТОЧНИК = транскрипты сессий Claude Code (`~/.claude/projects/<repo>/*.jsonl`) — единственный
живой журнал ВСЕХ Bash-команд контура (Termux + headless). Журнал гарда (/tmp/cc_pretool_guard.log)
для замера не годится: он пишет ТОЛЬКО жёсткие блоки и card_skipped, то есть уже отфильтрованное.

ЧТО СЧИТАЕМ (порядок повторяет main() гарда, ничего не исполняя):
  hard    — kind=block (процессы/секреты) → deny, карточки владельцу НЕТ, но и команда НЕ пройдёт;
  entity  — red + живая сущность → deny (маркер blocktype=hard, задача закрывается failed);
  card    — red + card_gate() → КАРТОЧКА ВЛАДЕЛЬЦУ (пуш + маркер-конверт демону) ← главное число;
  journal — red без объекта → ask + строка card_skipped (владельцу молчим);
  defer   — green/ambiguous → штатные слои settings.

Запуск: venv/bin/python3 guard_replay.py [--hours 24] [--verbose] [--self-test]
Ничего не пишет, ничего не пушит (PRETOOL_NOPUSH=1 ставится себе же на всякий случай).
"""
import os, sys, json, glob, time, argparse, tempfile, shutil

PROJECT = "/root/turbobaby-manager-bot"
TRANSCRIPTS = "/root/.claude/projects/-root-turbobaby-manager-bot"
BUCKETS = ("hard", "entity", "card", "journal", "defer")

os.environ.setdefault("PRETOOL_NOPUSH", "1")
sys.path.insert(0, PROJECT)
import pretool_guard as G                                    # noqa: E402


def iter_commands(hours=24.0, root=TRANSCRIPTS, now=None):
    """Bash-команды из транскриптов за последние `hours` → (ts, session, cwd, cmd).
    Файлы, не менявшиеся раньше границы окна, не открываются вовсе (их записей в окне нет)."""
    now = time.time() if now is None else now
    cutoff = now - hours * 3600.0
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff))
    for path in sorted(glob.glob(os.path.join(root, "*.jsonl"))):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        session = os.path.basename(path)[:8]
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or '"Bash"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    ts = str(e.get("timestamp") or "")
                    if ts and ts[:19] < cutoff_iso:      # ISO-8601 UTC сравнивается лексикографически
                        continue
                    msg = e.get("message") or {}
                    content = msg.get("content")
                    if not isinstance(content, list):
                        continue
                    for it in content:
                        if not isinstance(it, dict) or it.get("type") != "tool_use":
                            continue
                        if it.get("name") != "Bash":
                            continue
                        cmd = ((it.get("input") or {}).get("command") or "")
                        if cmd.strip():
                            yield ts, session, (e.get("cwd") or PROJECT), cmd
        except OSError:
            continue


def verdict(cmd, cwd=PROJECT):
    """→ (bucket, hit). Повторяет порядок решений main() гарда, НИЧЕГО не исполняя и не записывая."""
    try:
        kind, hit, blob = G.classify(cmd, cwd)
    except Exception:
        return "defer", "classify_failed"                 # как main(): сбой анализа → defer
    if kind in ("green", "ambiguous"):
        return "defer", hit
    if not G.can_approve(kind, hit):
        return "hard", hit
    if G._entity_blocktype(hit, blob) == "hard":
        return "entity", hit
    obj, num = G.card_min(hit, blob)
    return ("card" if G.card_gate(hit, obj, num) else "journal"), hit


def replay(hours=24.0, root=TRANSCRIPTS, now=None):
    """→ (counts, rows): rows — только НЕ-defer (то, где гард вмешивается)."""
    counts = dict((b, 0) for b in BUCKETS)
    rows = []
    for ts, session, cwd, cmd in iter_commands(hours, root, now):
        b, hit = verdict(cmd, cwd)
        counts[b] += 1
        if b != "defer":
            rows.append((ts, session, b, hit, " ".join(cmd.split())[:150]))
    return counts, rows


def _self_test():
    """Проверяет САМ ИНСТРУМЕНТ (разбор транскрипта + раскладка по корзинам) на синтетике."""
    d = tempfile.mkdtemp(prefix="guard_replay_st_")
    fails = []
    try:
        red = os.path.join(d, "fx.py")
        with open(red, "w", encoding="utf-8") as f:                  # живой формат: объект+число
            f.write("bridge.set_fleet_" + "oil(number='6789', oil_km=27000)\n")
        cmds = [
            "grep -n foo /root/turbobaby-manager-bot/splinter.py",   # defer
            "%s/venv/bin/python3 %s" % (PROJECT, red),               # card
            "cat /root/turbobaby-manager-bot/.env",                  # hard (секреты)
        ]
        p = os.path.join(d, "sess1234.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for i, c in enumerate(cmds):
                f.write(json.dumps({
                    "timestamp": "2026-07-30T10:00:0%d.000Z" % i, "cwd": PROJECT,
                    "message": {"content": [{"type": "tool_use", "name": "Bash",
                                             "input": {"command": c}}]}}) + "\n")
            f.write(json.dumps({"timestamp": "2026-07-30T10:00:09.000Z", "cwd": PROJECT,
                                "message": {"content": [{"type": "tool_use", "name": "Read",
                                                         "input": {"file_path": "x"}}]}}) + "\n")
        # окно считаем от фиксированного «сейчас» синтетики, чтобы тест не зависел от даты прогона
        now = time.mktime(time.strptime("2026-07-30T10:30:00", "%Y-%m-%dT%H:%M:%S")) - time.timezone
        counts, rows = replay(hours=1.0, root=d, now=now)
        for label, got, want in (("defer", counts["defer"], 1), ("card", counts["card"], 1),
                                 ("hard", counts["hard"], 1), ("rows", len(rows), 2)):
            if got != want:
                fails.append("%s: %s != %s" % (label, got, want))
        # окно РЕЖЕТ: сдвигаем «сейчас» на сутки вперёд — записей в часовом окне нет
        counts2, _ = replay(hours=1.0, root=d, now=now + 86400)
        if sum(counts2.values()):
            fails.append("окно не отсекло старые записи: %s" % counts2)
        # не-Bash tool_use в корзины не попадает (проверено rows/defer выше), сессия видна в строке
        if rows and rows[0][1] != "sess1234":
            fails.append("session-метка потерялась: %s" % (rows[0][1],))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for f in fails:
        print("  FAIL " + f)
    print("guard_replay self-test: " + ("OK" if not fails else "КРАСНЫЙ (%d)" % len(fails)))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--verbose", action="store_true", help="печатать все не-defer строки")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    counts, rows = replay(a.hours)
    total = sum(counts.values())
    print("реплей: %d команд за %g ч (источник: транскрипты %s)" % (total, a.hours, TRANSCRIPTS))
    for b in BUCKETS:
        print("  %-8s %d" % (b, counts[b]))
    print("КАРТОЧЕК ВЛАДЕЛЬЦУ: %d | жёстких блоков: %d | в журнал: %d"
          % (counts["card"], counts["hard"], counts["journal"]))
    if a.verbose:
        print("--- не-defer построчно ---")
        for ts, session, b, hit, cmd in rows:
            print("%s %s %-7s %-16s %s" % (ts[:19], session, b, hit, cmd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
