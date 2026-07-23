"""Билд подготовленных настроек роль-развода permissions (08.07.2026, задача claspsplit).

Читает живые .claude/settings.json и .claude/settings.local.json, детерминированно строит:
  _claspsplit_new_settings.json        — будущий .claude/settings.json (project, git-истина):
      из ask УБРАНЫ Bash(clasp push*) / Bash(clasp redeploy*) — иначе ask бьёт allow local
      и владелец продолжает ловить промпты; Bash(clasp deploy*) СУЖЕН до двух форм
      Bash(clasp deploy) + Bash(clasp deploy *), чтобы НЕ матчить безопасный clasp deployments;
      clasp run*/sqlite3/systemctl stop/sudo — на месте. Остальное байт-в-байт.
  _claspsplit_new_settings.local.json  — будущий .claude/settings.local.json (владелец,
      игнорится git глобально: /root/.config/git/ignore): прежние локальные allow-записи +
      clasp push/redeploy/deployments/version(s)/create-version в allow.
Применение — разовые cp владельцем в интерактивной сессии (headless в .claude/ писать не может — гейт движка):
  cp _claspsplit_new_settings.json .claude/settings.json
  cp _claspsplit_new_settings.local.json .claude/settings.local.json
Забор headless при этом держит headless_settings.json (демон передаёт его через --settings;
ask там бьёт allow local по precedence deny>ask>allow).
"""
import json

ROOT = "/root/turbobaby-manager-bot"

DROP_ASK = ["Bash(clasp push*)", "Bash(clasp redeploy*)", "Bash(clasp deploy*)"]
NARROW_DEPLOY = ["Bash(clasp deploy)", "Bash(clasp deploy *)"]
OWNER_CLASP_ALLOW = [
    "Bash(clasp push*)",
    "Bash(clasp redeploy*)",
    "Bash(clasp deployments*)",
    "Bash(clasp version*)",
    "Bash(clasp versions*)",
    "Bash(clasp create-version*)",
]

with open(ROOT + "/.claude/settings.json") as f:
    proj = json.load(f)

ask = proj["permissions"]["ask"]
new_ask = []
for rule in ask:
    if rule == "Bash(clasp deploy*)":
        new_ask.extend(NARROW_DEPLOY)
    elif rule in DROP_ASK:
        continue
    else:
        new_ask.append(rule)
proj["permissions"]["ask"] = new_ask

with open(ROOT + "/_claspsplit_new_settings.json", "w") as f:
    json.dump(proj, f, ensure_ascii=False, indent=2)
    f.write("\n")

with open(ROOT + "/.claude/settings.local.json") as f:
    local = json.load(f)

allow = local.setdefault("permissions", {}).setdefault("allow", [])
for rule in OWNER_CLASP_ALLOW:
    if rule not in allow:
        allow.append(rule)

with open(ROOT + "/_claspsplit_new_settings.local.json", "w") as f:
    json.dump(local, f, ensure_ascii=False, indent=2)
    f.write("\n")

print("OK: _claspsplit_new_settings.json ask:", len(new_ask), "правил (было", len(ask), ")")
print("OK: _claspsplit_new_settings.local.json allow:", len(allow), "правил")
