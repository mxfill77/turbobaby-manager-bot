"""Регресс 05.07: боевые уведомления ожидания/CLI НЕ глушатся тест-мутом PRETOOL_NOPUSH, тестовые — глушатся.
Контекст: NOPUSH-фикс 20762b6 сделал мут в notify() слишком широким — под PRETOOL_NOPUSH заглох ЛЮБОЙ пуш,
включая живое уведомление ожидания (хук Notification) и явный `notify.py --done`. Фикс: force=True у боевых
отправителей (CLI/notify_hook/health/gate/splinter) проходит мут; force=False (тесты/фикстуры) — мьютится.
Сеть НЕ дёргаем: _send_message замокан."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
# снять тест-env у себя — проверяем ЛОГИКУ notify изнутри; сеть замокана
os.environ.pop("PRETOOL_NOPUSH", None)
os.environ.pop("NOTIFY_COUNT_FILE", None)
import notify as N

SENT = []; DELETED = []; _mid = [200]
N._send_message = lambda tok, txt: (_mid.__setitem__(0, _mid[0] + 1), SENT.append(txt), (True, _mid[0]))[-1]
N._delete_message = lambda tok, mid: (DELETED.append(int(mid)), True)[-1]
N._get_token = lambda: "TKN"
N._save_ids([])

res = []
def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l); res.append(bool(c)); return c

# ── (A) под тест-мутом PRETOOL_NOPUSH: боевой (force) проходит, тестовый (не-force) молчит ──
os.environ["PRETOOL_NOPUSH"] = "1"
print("(A) PRETOOL_NOPUSH=1 — force vs не-force:")
SENT.clear()
r_force = N.notify("🔔 боевое уведомление ожидания", force=True)
ok(r_force is True and SENT == ["🔔 боевое уведомление ожидания"], "боевой пуш (force=True) ПРОШЁЛ")
SENT.clear()
r_mute = N.notify("🔴 тестовая карточка фикстуры")   # force=False по умолчанию
ok(r_mute is True and SENT == [], "тестовый пуш (force=False) ЗАМЬЮЧЕН (сеть не дёрнута)")

# ── (B) CLI-обёртка _cli всегда боевая (force) — явный notify.py не глушится ──
print("(B) _cli (== запуск notify.py) под мутом:")
SENT.clear()
r_cli = N._cli(["--done", "задача"])
ok(r_cli is True and SENT == ["✅ задача готова"], "notify.py --done ПРОШЁЛ под PRETOOL_NOPUSH")

# ── (C) clear_notifications: force чистит под мутом, не-force молчит ──
print("(C) clear_notifications force vs не-force:")
N._save_ids([501])
DELETED.clear()
N.clear_notifications()            # force=False → тест-мут: сеть не дёргаем
ok(DELETED == [], "clear (force=False) под мутом — удаления НЕТ")
N._save_ids([501])
DELETED.clear()
N.clear_notifications(force=True)  # боевая чистка (notify_clear_hook)
ok(501 in DELETED, "clear (force=True) под мутом — удаление ПРОШЛО")

# ── (D) мок-счётчик NOTIFY_COUNT_FILE перекрывает даже force (сеть в тестах не дёргаем никогда) ──
print("(D) NOTIFY_COUNT_FILE перекрывает force:")
import tempfile
cnt = os.path.join(tempfile.mkdtemp(prefix="notifyforce_"), "cnt.txt")
os.environ["NOTIFY_COUNT_FILE"] = cnt
SENT.clear()
N.notify("боевой но в тесте", force=True)
os.environ.pop("NOTIFY_COUNT_FILE", None)
lines = 0
try:
    with open(cnt, encoding="utf-8") as f: lines = len([x for x in f if x.strip()])
except OSError: pass
ok(SENT == [] and lines == 1, "force+COUNT_FILE: сети НЕТ, попытка учтена счётчиком")

# ── (E) без тест-env (боевой контур): обычный notify отправляет ──
os.environ.pop("PRETOOL_NOPUSH", None)
print("(E) без тест-env — обычный notify шлёт:")
SENT.clear()
N.notify("⚠️ health алерт")   # force=False, но мута нет → шлёт
ok(SENT == ["⚠️ health алерт"], "вне тестов пуш идёт и без force")

# ── (F) боевые отправители реально передают force=True (защита от регресса плумбинга) ──
print("(F) плумбинг force у боевых отправителей:")
import inspect
hook_src = inspect.getsource  # noqa
with open("/root/turbobaby-manager-bot/notify_hook.py", encoding="utf-8") as f:
    ok("force=True" in f.read(), "notify_hook передаёт force=True")
with open("/root/turbobaby-manager-bot/notify_clear_hook.py", encoding="utf-8") as f:
    ok("force=True" in f.read(), "notify_clear_hook передаёт force=True")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
