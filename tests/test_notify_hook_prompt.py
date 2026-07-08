"""Регресс UX-фикса висящего промпта (08.07.2026): хук Notification на permission-ожидании
шлёт «⏳ Termux ждёт подтверждения: <команда>» — команда достаётся из транскрипта сессии.

Проверяем subprocess-запуском notify_hook (как его зовёт движок: JSON в stdin) с мок-транскриптом.
Сеть НЕ дёргается: NOTIFY_COUNT_FILE (мок-счётчик notify, срабатывает ДО токена/сети, перекрывает
даже force=True) пишет текст попытки в файл — по нему и сверяем содержимое пуша.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = "/root/turbobaby-manager-bot"
HOOK = os.path.join(ROOT, "notify_hook.py")
PY = os.path.join(ROOT, "venv", "bin", "python3")

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


def run_hook(event, transcript_lines=None):
    """Запустить хук как движок: JSON события в stdin, NOTIFY_COUNT_FILE → текст пуша."""
    with tempfile.TemporaryDirectory() as td:
        count = os.path.join(td, "count.txt")
        if transcript_lines is not None:
            tp = os.path.join(td, "transcript.jsonl")
            with open(tp, "w", encoding="utf-8") as f:
                f.write("\n".join(transcript_lines) + "\n")
            event = dict(event, transcript_path=tp)
        env = dict(os.environ, NOTIFY_COUNT_FILE=count, PRETOOL_NOPUSH="1")
        p = subprocess.run([PY, HOOK], input=json.dumps(event), text=True,
                           capture_output=True, timeout=60, env=env)
        sent = open(count, encoding="utf-8").read() if os.path.exists(count) else ""
        return p.returncode, sent


def tool_use_line(name, inp):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu1", "name": name, "input": inp}]}}, ensure_ascii=False)


print("Permission-ожидание + Bash в транскрипте → ⏳ с командой:")
rc, sent = run_hook(
    {"hook_event_name": "Notification", "message": "Claude needs your permission to use Bash"},
    transcript_lines=[
        json.dumps({"type": "user", "message": {"content": "сделай деплой"}}),
        tool_use_line("Bash", {"command": "clasp redeploy AKfycbxNC9 --versionNumber 67"}),
    ])
res.append(ok(rc == 0, "хук отработал (exit 0)"))
res.append(ok("⏳ Termux ждёт подтверждения:" in sent, "пуш начинается с ⏳-префикса"))
res.append(ok("clasp redeploy AKfycbxNC9" in sent, "в пуше видна САМА команда"))

print("Permission-ожидание, последний tool_use = Edit → имя файла:")
rc, sent = run_hook(
    {"hook_event_name": "Notification", "message": "Claude needs your permission to use Edit"},
    transcript_lines=[
        tool_use_line("Bash", {"command": "echo старьё"}),
        tool_use_line("Edit", {"file_path": "/root/turbobaby-manager-bot/splinter.py"}),
    ])
res.append(ok("⏳" in sent and "Edit /root/turbobaby-manager-bot/splinter.py" in sent,
              "Edit-промпт показывает файл"))

print("Permission-ожидание БЕЗ читаемого транскрипта → ⏳ + исходный message (fallback, не хуже старого):")
rc, sent = run_hook({"hook_event_name": "Notification",
                     "message": "Claude needs your permission to use Bash",
                     "transcript_path": "/nonexistent/т.jsonl"})
res.append(ok("⏳ Termux ждёт подтверждения: Claude needs your permission" in sent,
              "fallback на текст события"))

print("НЕ-permission событие (простой ~60с) → прежний формат 🔔:")
rc, sent = run_hook({"hook_event_name": "Notification", "message": "Claude is waiting for your input"})
res.append(ok(sent.startswith("🔔 Claude Code: Claude is waiting"), "🔔-формат не сломан"))

print("Пустой/битый stdin → хук не падает, пуш уходит:")
with tempfile.TemporaryDirectory() as td:
    count = os.path.join(td, "count.txt")
    env = dict(os.environ, NOTIFY_COUNT_FILE=count, PRETOOL_NOPUSH="1")
    p = subprocess.run([PY, HOOK], input="не json", text=True, capture_output=True,
                       timeout=60, env=env)
    sent = open(count, encoding="utf-8").read() if os.path.exists(count) else ""
res.append(ok(p.returncode == 0 and "🔔 Claude Code: ждёт тебя в Termux" in sent,
              "битый stdin → дефолтный 🔔"))

print("Обрезка длинной команды (пуш ≤ вменяемой длины):")
rc, sent = run_hook(
    {"hook_event_name": "Notification", "message": "needs your permission to use Bash"},
    transcript_lines=[tool_use_line("Bash", {"command": "x" * 900})])
res.append(ok("⏳" in sent and len(sent.strip()) <= 210, "команда обрезана (счётчик режет 200)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
