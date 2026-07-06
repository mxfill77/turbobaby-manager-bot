"""Автоудаление 🔔 Claude Code: трек id + удаление-при-следующем + UserPromptSubmit; ✅/🔧 не трогаются;
стор атомарен; deleteMessage на мёртвом id не валит. Сеть НЕ дёргаем — _send_message/_delete_message мокнуты."""
import os, sys, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
# Снимаем тест-мут (гейт ставит PRETOOL_NOPUSH=1 подпроцессам тестов): этот тест проверяет ЛОГИКУ
# notify изнутри, сеть замокана (_send_message/_delete_message/_get_token) — мут тут не нужен.
os.environ.pop("PRETOOL_NOPUSH", None)
os.environ.pop("NOTIFY_COUNT_FILE", None)
import notify as N
# notify на импорте авто-поднимает PRETOOL_NOPUSH по тест-entry-point (§12 корень 2, 06.07) —
# снимаем ЕЩЁ РАЗ ПОСЛЕ импорта: тест проверяет реальный send-путь notify, сеть замокана
# (_send_message/_delete_message), поэтому мут тут не нужен и утечки нет.
os.environ.pop("PRETOOL_NOPUSH", None)

TMP = "/tmp/claude-0/-root-turbobaby-manager-bot/de0bcc53-2bb9-43ea-8f40-d32c5dc0212b/scratchpad/cc_notif_test.json"
N._STORE = TMP
for p in (TMP, TMP + ".tmp", TMP + ".lock"):
    try: os.remove(p)
    except OSError: pass

_REAL_DELETE = N._delete_message   # для теста устойчивости (реальный, до мока)
SENT = []; DELETED = []; _mid = [100]
def fake_send(token, text): _mid[0] += 1; SENT.append((text, _mid[0])); return True, _mid[0]
def fake_del(token, mid): DELETED.append(int(mid)); return True
N._send_message = fake_send
N._delete_message = fake_del
N._get_token = lambda: "TKN"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# (a) 🔔 #1 (track) → сохранён id
N._save_ids([])
N.notify("🔔 Claude Code: #1", track=True)
id1 = _mid[0]
print("(a) 🔔 #1:")
res.append(ok(N._load_ids() == [id1], f"id первого 🔔 сохранён в стор ({id1})"))
res.append(ok(SENT[-1][0] == "🔔 Claude Code: #1", "🔔 #1 отправлен"))

# (b) 🔔 #2 → #1 удалён, висит только #2
DELETED.clear()
N.notify("🔔 Claude Code: #2", track=True)
id2 = _mid[0]
print("(b) 🔔 #2 → #1 удалён:")
res.append(ok(id1 in DELETED, "прошлый 🔔 #1 удалён (deleteMessage)"))
res.append(ok(N._load_ids() == [id2], "в сторе только #2 (макс одно уведомление)"))

# (c) --done после 🔔 → 🔔 удалён, ✅ остаётся (и НЕ трекается)
DELETED.clear(); SENT.clear()
N.notify("✅ задача готова", clear_first=True)
print("(c) --done после 🔔:")
res.append(ok(id2 in DELETED, "висящий 🔔 #2 удалён при --done"))
res.append(ok(N._load_ids() == [], "стор пуст (✅ не трекается)"))
res.append(ok(SENT and SENT[-1][0] == "✅ задача готова", "✅ отправлено и остаётся (id не в сторе)"))

# (d) clear_notifications (UserPromptSubmit) → удаляет накопленный 🔔 + чистит стор
N.notify("🔔 Claude Code: #3", track=True)
id3 = _mid[0]
DELETED.clear()
N.clear_notifications()
print("(d) clear_notifications (новое задание):")
res.append(ok(id3 in DELETED and N._load_ids() == [], "🔔 удалён и стор очищен при новом задании"))

# (e) health-style notify (дефолт) НЕ трогает висящий 🔔 и НЕ трекается
N._save_ids([])
N.notify("🔔 Claude Code: pending", track=True)
idp = _mid[0]
DELETED.clear()
N.notify("⚠️ health: Brain latency")     # defaults: track=False, clear_first=False
print("(e) health-алерт не трогает 🔔:")
res.append(ok(idp not in DELETED, "висящий 🔔 НЕ удалён health-алертом"))
res.append(ok(N._load_ids() == [idp], "стор не изменён (health не трекается, не чистит)"))

# (f) _delete_message на мёртвом id / сети нет → False, НЕ кидает (реальная функция)
import urllib.request
_orig = urllib.request.urlopen
def _boom(*a, **k): raise RuntimeError("net down")
urllib.request.urlopen = _boom
r = _REAL_DELETE("TKN", 999999)
urllib.request.urlopen = _orig
print("(f) deleteMessage устойчив:")
res.append(ok(r is False, "deleteMessage на ошибке → False, без исключения (хук не валится)"))

# (g) стор: атомарная запись + чтение, tmp не остаётся
N._save_ids([11, 22, 33])
print("(g) стор атомарен:")
res.append(ok(N._load_ids() == [11, 22, 33], "save→load round-trip"))
res.append(ok(not os.path.exists(TMP + ".tmp"), "tmp-файл убран (os.replace атомарно)"))

for p in (TMP, TMP + ".tmp", TMP + ".lock"):
    try: os.remove(p)
    except OSError: pass

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
