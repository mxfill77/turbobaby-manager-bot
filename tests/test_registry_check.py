"""registry_check.py — детектор расхождений карта↔реальность (READ-ONLY).
Сеть/git НЕ дёргаем: весь мир — FakeWorld (доки/манифест/git-множество в памяти).
Проверяем: чистый мир = СХОДИТСЯ; каждая проверка ловит своё синтетическое расхождение;
изоляция §4 (клиентский фантом НЕ ловим); деградация (Bridge молчит) = note, не расхождение;
растяжимость (новая @register-проверка попадает в прогон)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
import registry_check as R

res = []
def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l); res.append(bool(c)); return c


def runs_by_name(world):
    return {r.name: r for r in R.run_all(world)}


# --- чистый мир (как в самотесте) ---
def healthy():
    return R._healthy_world()


# (1) чистый мир → 0 расхождений, отчёт «СХОДИТСЯ»
runs = R.run_all(healthy())
total = sum(len(r.findings) for r in runs)
ok(total == 0, "чистый мир: 0 расхождений во всех проверках")
rep = R.format_report(runs, head="abc1234")
ok("СХОДИТСЯ" in rep and "abc1234" in rep, "отчёт чистого мира = СХОДИТСЯ + HEAD")

# (2) КАРТА↔GIT: внутренний фантомный коммит → ловим
w = healthy()
w._docs["index"] += "- оркестратор headless commit ccccccc9 в проде\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 1, "внутр. фантомный коммит пойман")

# (3) КАРТА↔GIT: клиентский фантом → НЕ ловим (§4 изоляция)
w = healthy()
w._docs["index"] += "- userbot suggest.py commit ddddddd8 (нет в manager-bot)\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 0, "клиентский фантом пропущен (§4 изоляция контуров)")

# (4) КАРТА↔GIT: резолвящийся внутр. коммит → тихо
w = healthy()
w._git.add("ccccccc9")
w._docs["index"] += "- splinter commit ccccccc9 в проде\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 0, "существующий внутр. коммит не сигналит")

# (4a) КАРТА↔GIT: коммит, ЯВНО приписанный чужому репо → НЕ ловим (фикс родителя 113 шаг 2:
#      pc_orchestrator содержит «orchestrator» = INTERNAL_MARK, раньше давал ложное расхождение)
w = healthy()
w._docs["index"] += "- ПК-полоса — кондуктор pc_orchestrator (eeeeee7, ПК-репо)\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 0, "хеш с маркером чужого репо (ПК-репо/pc_orchestrator) не сигналит")

# (4b) КАРТА↔GIT: маркер «ПК-репо» сам по себе (без pc_orchestrator) → НЕ ловим
w = healthy()
w._docs["index"] += "- оркестратор ПК фикс eeeeee8 (ПК-репо)\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 0, "маркер «ПК-репо» рядом с хешем гасит проверку резолва")

# (4c) КАРТА↔GIT: детектор НЕ ослаб — внутренний фантом БЕЗ маркеров чужого репо по-прежнему пойман
w = healthy()
w._docs["index"] += "- оркестратор headless commit ffffff1 в проде\n"
ok(len(runs_by_name(w)["КАРТА↔GIT"].findings) == 1, "внутр. фантом без чужих маркеров ПОЙМАН (детектор не ослаб)")

# (5) КАРТА↔ПУЛЬС: §99 нет в карте → ловим
w = healthy()
w._docs["pulse"] = "... | детали→KB_MASTER §99 про что-то"
ok(len(runs_by_name(w)["КАРТА↔ПУЛЬС"].findings) == 1, "битый §-указатель пульса пойман")

# (6) КАРТА↔ПУЛЬС: KB-док не в манифесте → ловим
w = healthy()
w._docs["pulse"] = "... | детали→KB_PHANTOM запись"
ok(len(runs_by_name(w)["КАРТА↔ПУЛЬС"].findings) == 1, "ссылка пульса на незарегистрированный KB-док поймана")

# (7) КАРТА↔ПУЛЬС: ссылка на cc_log (есть в манифесте) → тихо
w = healthy()
w._docs["pulse"] = "... | детали→cc_log запись про инбокс"
ok(len(runs_by_name(w)["КАРТА↔ПУЛЬС"].findings) == 0, "валидная ссылка пульса на cc_log не сигналит")

# (8) СЧЁТ BRAIN: засорение → ловим
w = healthy()
for i in range(10):
    w._man[f"junk{i}"] = f"jid{i}"
ok(len(runs_by_name(w)["СЧЁТ BRAIN"].findings) == 1, "засорение манифеста (≥CLUTTER_AT) поймано")

# (9) СЧЁТ BRAIN: усушка/порча → ловим
w = healthy()
w._man = {"a": "1", "b": "2", "folder_id": "F"}   # 2 distinct дока < FLOOR
ok(len(runs_by_name(w)["СЧЁТ BRAIN"].findings) == 1, "усушка манифеста (<FLOOR) поймана")

# (10) деградация: Bridge молчит (read_doc/manifest = None) → NOTE, НЕ расхождение
class Silent(R.FakeWorld):
    def read_doc(self, name): return None
    def manifest(self): return None
w = Silent()
runs = runs_by_name(w)
findings = sum(len(r.findings) for r in runs.values())
notes = sum(len(r.notes) for r in runs.values())
ok(findings == 0 and notes >= 3, "Bridge молчит → пропуски (note), НОЛЬ ложных расхождений")

# (11) растяжимость: новая @register-проверка попадает в прогон
_before = len(R.CHECKS)
@R.register("ВРЕМЕННАЯ")
def _tmp(world, run):
    run.flag("тест", "расширение работает")
try:
    names = [r.name for r in R.run_all(healthy())]
    ok("ВРЕМЕННАЯ" in names and len(R.CHECKS) == _before + 1,
       "новая проверка добавлена в СПИСОК и прогналась (растяжимость)")
finally:
    R.CHECKS[:] = [c for c in R.CHECKS if c[0] != "ВРЕМЕННАЯ"]   # чистим глобал

# (12) отчёт с расхождениями — компактный, содержит блок «карта:/реальность:»
w = healthy()
w._docs["index"] += "- оркестратор headless commit ccccccc9 в проде\n"
rep = R.format_report(R.run_all(w), head="e007447")
ok("РАСХОЖДЕНИ" in rep and "карта:" in rep and "реальность:" in rep, "отчёт расхождений компактный и адресный")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
