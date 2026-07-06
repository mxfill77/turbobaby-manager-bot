"""registry_check.py проверка #4 — РЕГИСТРАЦИЯ НОВОГО (Слой роста, READ-ONLY).
Сеть/git НЕ дёргаем: мир = FakeWorld (живой манифест + реестр в памяти).
Проверяем: реестр=мозг → тихо; лишний живой ключ → 🆕 НОВОЕ; active-фантом реестра → ⚠️ ПРОПАЛО;
_/tmp и status=archive не шумят; деградация (реестр/манифест None) = note, не расхождение;
плюс СТАТИКА самого registry_manifest.json в репо (парсится, структура, без дублей имён)."""
import os, sys, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
import registry_check as R

res = []
def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l); res.append(bool(c)); return c


def growth(world):
    return {r.name: r for r in R.run_all(world)}["РЕГИСТРАЦИЯ НОВОГО"]


# (1) реестр знает ровно живой мозг → 0 расхождений
ok(len(growth(R._healthy_world()).findings) == 0, "реестр = живой мозг → тихо")

# (2) лишний живой ключ (новая вещь в бизнесе) → 🆕 НОВОЕ
w = R._healthy_world(); w._man["new_biz_doc"] = "idnew"
g = growth(w)
ok(len(g.findings) == 1 and "НОВОЕ" in g.findings[0][1] and "new_biz_doc" in g.findings[0][1],
   "лишний живой ключ → 🆕 НОВОЕ (адресно назван)")

# (3) active-фантом в реестре, нет в живом мозге → ⚠️ ПРОПАЛО
w = R._healthy_world(); w._reg["docs"].append({"name": "phantom_active", "status": "active"})
g = growth(w)
ok(len(g.findings) == 1 and "ПРОПАЛО" in g.findings[0][1] and "phantom_active" in g.findings[0][1],
   "active-фантом реестра → ⚠️ ПРОПАЛО")

# (4) переименование = ПРОПАЛО + НОВОЕ (честно, калибровка «лучше словить оба»)
w = R._healthy_world()
w._man["cc_log_renamed"] = w._man.pop("cc_log")   # переименовали живой ключ
g = growth(w)
reality = " ".join(f[1] for f in g.findings)
ok(len(g.findings) == 2 and "НОВОЕ" in reality and "ПРОПАЛО" in reality,
   "переименование ловится как ПРОПАЛО+НОВОЕ")

# (5) временные (_/tmp) не шумят
w = R._healthy_world(); w._man["_scratch"] = "x"; w._man["mytmpdoc"] = "y"
ok(len(growth(w).findings) == 0, "_/tmp живые ключи → не НОВОЕ")

# (6) status=archive в реестре, нет в мозге → НЕ ПРОПАЛО (архив вне манифеста — норма)
w = R._healthy_world(); w._reg["docs"].append({"name": "old_merged", "status": "archive"})
ok(len(growth(w).findings) == 0, "archive-док реестра без живого ключа → не ПРОПАЛО")

# (6b) archive отдельным списком reg["archive"] тоже «известно» — не НОВОЕ, если вдруг оживёт
w = R._healthy_world(); w._man["resurrected"] = "z"; w._reg["archive"] = [{"name": "resurrected"}]
ok(len(growth(w).findings) == 0, "ключ из reg['archive'] не считается НОВЫМ")

# (7) деградация: реестр не прочитан (None) → note, НЕ расхождение
w = R._healthy_world(); w._reg = None
g = growth(w)
ok(len(g.findings) == 0 and len(g.notes) == 1, "реестр None → note, ноль ложных")

# (8) деградация: живой манифест не прочитан → note, НЕ расхождение
w = R._healthy_world(); w._man = None
g = growth(w)
ok(len(g.findings) == 0 and len(g.notes) == 1, "манифест None → note, ноль ложных")

# (9) проверка попала в общий прогон (4-я)
ok("РЕГИСТРАЦИЯ НОВОГО" in [r.name for r in R.run_all(R._healthy_world())],
   "проверка #4 в общем списке CHECKS")

# --- СТАТИКА registry_manifest.json (git-файл, гейт его защищает) ---
data = R.load_registry_manifest()
ok(isinstance(data, dict) and isinstance(data.get("docs"), list) and len(data["docs"]) >= 20,
   "registry_manifest.json парсится, ≥20 доков")
names = [d.get("name") for d in data["docs"]]
ok(all(d.get("name") and d.get("status") in ("active", "archive") for d in data["docs"]),
   "каждый док: непустое имя + status active|archive")
ok(len(names) == len(set(names)), "нет дублей имён в реестре")
ok(all(d.get("purpose") for d in data["docs"]), "у каждого дока есть назначение (purpose)")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
