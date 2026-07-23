#!/usr/bin/env python3
"""Диагностика RSS-гейта: текущий RSS claude-процессов vs порог."""
import os, sys, glob

# Считаем суммарный RSS всех claude-процессов (как _live_claude_rss_mb в демоне)
total_rss_kb = 0
procs = []
for status_path in glob.glob("/proc/*/status"):
    try:
        pid = int(status_path.split("/")[2])
        cmdline_path = f"/proc/{pid}/cmdline"
        with open(cmdline_path, "rb") as f:
            cmdline = f.read().decode(errors="replace").replace("\x00", " ").strip()
        if "claude" not in cmdline:
            continue
        # Пропускаем наш же процесс
        if pid == os.getpid():
            continue
        rss_kb = 0
        with open(status_path) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
        total_rss_kb += rss_kb
        # Короткая команда
        cmd_short = cmdline[:80]
        procs.append((pid, rss_kb, cmd_short))
    except Exception:
        continue

total_mb = total_rss_kb // 1024

# Читаем MemAvailable из /proc/meminfo
mem_avail_mb = 0
try:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                mem_avail_mb = int(line.split()[1]) // 1024
                break
except Exception:
    pass

# Пороги из .env (дефолты как в демоне)
claude_rss_total_mb = int(os.environ.get("CLAUDE_RSS_TOTAL_MB", 1200))
mem_min_mb = int(os.environ.get("MEM_MIN_MB", 500))
max_procs = int(os.environ.get("MAX_CLAUDE_PROCS", 2))

print(f"=== RSS-гейт диагностика ===")
print(f"Claude-процессов: {len(procs)} (лимит MAX_CLAUDE_PROCS={max_procs})")
for pid, rss_kb, cmd in sorted(procs, key=lambda x: -x[1]):
    print(f"  PID {pid}: {rss_kb//1024}МБ — {cmd}")
print(f"Суммарный RSS claude: {total_mb}МБ (порог CLAUDE_RSS_TOTAL_MB={claude_rss_total_mb}МБ)")
print(f"MemAvailable: {mem_avail_mb}МБ (порог MEM_MIN_MB={mem_min_mb}МБ)")
print()

# Оценка состояния гейтов
rss_blocked = claude_rss_total_mb > 0 and total_mb >= claude_rss_total_mb
mem_blocked = mem_avail_mb > 0 and mem_avail_mb < mem_min_mb
proc_blocked = len(procs) >= max_procs

print(f"RSS-гейт: {'🔴 БЛОК' if rss_blocked else '🟢 ОК'}")
print(f"Mem-гейт: {'🔴 БЛОК' if mem_blocked else '🟢 ОК'}")
print(f"Proc-гейт: {'🔴 БЛОК' if proc_blocked else '🟢 ОК'} ({len(procs)}/{max_procs})")
