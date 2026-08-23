"""ПУНКТ «ПОСЛЕ ВЫКЛАДКИ ОБНОВИТЬ ЗЕРКАЛО» ПОЛУЧИЛ МАШИНУ (23.08.2026).

ПОВОД, ИЗМЕРЕННЫЙ ЖИВЫМ СЛУЧАЕМ. Прод уехал @79 → @83 выкладкой 23.08 06:40:54 UTC, зеркало
`bridge_prod/` осталось @79 и было сведено только в 12:20:53 отдельным заходом — 5 ч 40 мин прод
и зеркало расходились, и сборка «поверх зеркала» стёрла бы дверь `service_undo` МОЛЧА. Это не
забывчивость одного человека, а дыра по устройству, и вот чем она доказана: у
`bridge_prod/MIRROR.json` за всю жизнь РОВНО ОДИН коммит (`7e348d4`, 10.08), `bridge_deploy.py`
называл зеркало единственный раз строкой-подсказкой и обновлять его не умел, а паспортный сторож
этот класс поймать не может по устройству — он судит согласованность зеркала с САМИМ СОБОЙ
(проверено 23.08: сторожа натравили на старое зеркало @79 целиком — ПРОШЁЛ).

ЧТО ЗАВЕДЕНО. После УДАЧНОГО redeploy шаг [7/7] снимает свежий отпечаток
(`deploy/bridge_prod_recon.py`, read-only GET'ы к Apps Script API — clasp тут не участвует),
чистая функция `mirror_sync.plan` решает, сводить ли зеркало, руки кладут файлы и ПЕРЕЧИТЫВАЮТ
написанное. Отпечаток не снят → ГРОМКИЙ отказ: код 4 «прод выложен, зеркало НЕ сведено» + алерт
+ строка в cc_log. Нулём такое звать нельзя — молча отставшее зеркало и есть мина.

Проверки:
 (1) ЧИСТОЕ РЕШЕНИЕ: импортов НОЛЬ, ни open/exec/eval, страж MIRROR_SYNC_PURE зелёный на боевом
     файле и КРАСНЕЕТ на грязном;
 (2) ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО: каждая дырка в фактах — отказ с НАЗВАННОЙ причиной, и у
     каждого отрицательного случая есть близнец «то же без порчи — сводим»;
 (3) МАШИНА НЕ УДАЛЯЕТ: прод уронил файл → отказ с именем файла, а не тихое удаление в репо;
 (4) ПЛАН И ПАСПОРТ: форма паспорта совпадает с ЖИВЫМ bridge_prod/MIRROR.json ключ в ключ и
     проходит те же проверки, что замок tests/test_bridge_prod_mirror.py; без времени снятия
     паспорт не собирается вовсе;
 (5) ОБРАТНОЕ ЧТЕНИЕ: verify ловит недоложенный, изменённый и лишний файл;
 (6) РУКИ НА МОКАХ: sync_mirror кладёт файлы прода во ВРЕМЕННОЕ зеркало, переписывает паспорт
     даже при совпавших байтах (версия — тоже утверждение), местные файлы (README.md, паспорт)
     не трогает;
 (7) ГРОМКИЙ ОТКАЗ В ЦИКЛЕ: redeploy ok + смок ok + отпечаток НЕ снят → код 4, алерт, cc_log
     говорит «ЗЕРКАЛО НЕ СВЕДЕНО», зеркало не тронуто;
 (8) УСПЕШНЫЙ ЦИКЛ ЦЕЛИКОМ: код 0, зеркало сведено, лог называет версию;
 (9) ОТКАТ РУЧКОЙ MIRROR_SYNC=0: код 0, зеркала не касались, лог честно говорит «НЕ сведено»;
(10) ГРАНИЦЫ: clasp в ветке сведения не звался НИ РАЗУ; при упавшем смоке сведение не зовётся
     вовсе; БОЕВОЕ зеркало не тронуто за весь прогон (sha256 до и после); настройки проекта в
     зеркале не появляются;
(11) ОДИН ДОМ У ПРАВИЛА местных файлов: `bridge_prod_diff._local_only` и
     `mirror_sync.is_local_only` согласны на таблице имён;
(12) ОТПЕЧАТОК НАЗЫВАЕТ ПРОЕКТ: recon пишет script_id в meta.json — иначе решение отказывало бы
     всегда, и машина была бы декорацией.

Живой прод НЕ ТРОГАЕТСЯ: всё на моках, ни одного clasp-вызова, ни одного обращения к сети.
"""
import ast
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ["MIRROR_SYNC"] = "1"

import bridge_deploy                     # noqa: E402
import invariants_check                  # noqa: E402
import mirror_sync                       # noqa: E402

MIRROR = os.path.join(REPO, "bridge_prod")
PASSPORT = os.path.join(MIRROR, "MIRROR.json")
SCRIPT_ID = "12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ"
PROD_ID = bridge_deploy.PROD_ID


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []


def _sha_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _sha_file(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _live_mirror_state():
    """sha256 КАЖДОГО файла боевого зеркала — им доказывается, что сьют его не тронул."""
    return {n: _sha_file(os.path.join(MIRROR, n))
            for n in sorted(os.listdir(MIRROR)) if os.path.isfile(os.path.join(MIRROR, n))}


LIVE_BEFORE = _live_mirror_state()

# ── фикстуры: снимок отпечатка и временное зеркало ──────────────────────────────────────────
PROD_FILES = {"Bridge.js": "function doPost(){/* @84 */}\n",
              "ReadFleet.js": "function fleet(){/* @84 */}\n",
              "appsscript.json": '{"timeZone":"Asia/Bangkok"}\n'}


def _write(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _make_snapshot(base, version=84, files=None, head=None, script_id=SCRIPT_ID, meta=True):
    """Снимок в форме, которую кладёт живой deploy/bridge_prod_recon.py."""
    files = PROD_FILES if files is None else files
    head = files if head is None else head
    for n, t in files.items():
        _write(os.path.join(base, "prod_v%d" % version), n, t)
    for n, t in head.items():
        _write(os.path.join(base, "head"), n, t)
    if meta:
        _write(base, "meta.json", json.dumps(
            {"prod_version": version, "script_id": script_id,
             "head_files": sorted(head), "prod_files": sorted(files)}, ensure_ascii=False))
    return base


def _make_mirror(dirpath, files=None, version=83, script_id=SCRIPT_ID):
    """Временное зеркало: файлы прода + местные (паспорт и документация)."""
    files = {"Bridge.js": "function doPost(){/* @83 */}\n",
             "ReadFleet.js": "function fleet(){/* @84 */}\n",
             "appsscript.json": '{"timeZone":"Asia/Bangkok"}\n'} if files is None else files
    for n, t in files.items():
        _write(dirpath, n, t)
    _write(dirpath, "README.md", "местная документация зеркала\n")
    _write(dirpath, "MIRROR.json", json.dumps(
        {"files_sha256": {n: _sha_text(t) for n, t in files.items()},
         "head_diff_files": [], "head_equals_prod": True, "prod_version": version,
         "pulled_by": "тест", "pulled_utc": "2026-08-23 00:00:00 UTC",
         "script_id": script_id, "что_это": mirror_sync.WHAT_IS}, ensure_ascii=False))
    return dirpath


def _facts(snap, mirror_dir, rc=0, tail=""):
    return bridge_deploy._mirror_facts(snap, mirror_dir, rc, tail)


def _healthy(tmp):
    """Здоровые факты: снимок @84 + зеркало @83, где один файл уже совпадает."""
    snap = _make_snapshot(os.path.join(tmp, "snap"))
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    return snap, mir, _facts(snap, mir)


# ═══════════════════ (1) ЧИСТОЕ РЕШЕНИЕ: рук нет ФИЗИЧЕСКИ ═══════════════════════════════
print("(1) ЧИСТОЕ РЕШЕНИЕ — импортов ноль, страж краснеет на грязном:")
src = open(os.path.join(REPO, "mirror_sync.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
res.append(ok(len(imports) == 0, "импортов в mirror_sync.py: %d (ждём 0)" % len(imports)))
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
res.append(ok(not ({"open", "exec", "eval", "__import__", "compile"} & names),
              "ни open, ни exec, ни eval — зеркало пишут РУКИ, не решение"))


class _Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


r = _Run()
invariants_check.check_mirror_sync_pure(None, r)
res.append(ok(not r.flags, "страж MIRROR_SYNC_PURE на боевом файле: нарушений %d" % len(r.flags)))
DIRTY = "/tmp/cc_mirror_sync_dirty_probe.py"
with open(DIRTY, "w", encoding="utf-8") as f:
    f.write("import shutil\n\n\ndef plan(facts):\n    return shutil.copyfile('a', 'b')\n")
_keep = invariants_check._MIRROR_SYNC_PATH
invariants_check._MIRROR_SYNC_PATH = DIRTY
r2 = _Run()
invariants_check.check_mirror_sync_pure(None, r2)
invariants_check._MIRROR_SYNC_PATH = _keep
res.append(ok(bool(r2.flags), "страж КРАСНЕЕТ на модуле с импортом: нарушений %d" % len(r2.flags)))
os.remove(DIRTY)

# ═════════ (2) ЗАМОК: КАЖДАЯ ДЫРКА В ФАКТАХ — ОТКАЗ С НАЗВАННОЙ ПРИЧИНОЙ ═════════════════
print("\n(2) ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО — у каждого отказа близнец «то же без порчи»:")
with tempfile.TemporaryDirectory() as tmp:
    snap, mir, good = _healthy(tmp)

    base = mirror_sync.plan(good)
    res.append(ok(base["ok"] and base["version"] == 84,
                  "БЛИЗНЕЦ: здоровые факты → сводим, версия @%s" % base["version"]))

    def broke(label, **over):
        f = dict(good)
        f.update(over)
        p = mirror_sync.plan(f)
        return ok(not p["ok"] and p["reason"], "%s → отказ: %s" % (label, p["reason"][:88]))

    res.append(broke("отпечаток не снимали вовсе", recon_rc=None))
    res.append(broke("отпечаток упал (код 2)", recon_rc=2, recon_tail="HTTP Error 403: Forbidden"))
    res.append(broke("снимка без meta.json", meta=None))
    res.append(broke("версия прода не число", meta={"prod_version": "84", "script_id": SCRIPT_ID}))
    res.append(broke("версия прода нулевая", meta={"prod_version": 0, "script_id": SCRIPT_ID}))
    res.append(broke("снимок молчит о проекте", meta={"prod_version": 84, "script_id": ""}))
    res.append(broke("исходники версии не прочитаны", live=None))
    res.append(broke("снимок задеплоенной версии пуст", live={}))
    res.append(broke("HEAD в снимке не прочитан", head=None))
    res.append(broke("нынешнее зеркало не прочитано", mirror=None))
    res.append(broke("отпечаток с ДРУГОГО проекта",
                     meta={"prod_version": 84, "script_id": "ЧУЖОЙ_ПРОЕКТ"}))
    res.append(broke("прод «поехал назад» (@84 → зеркало @99)",
                     mirror_meta={"prod_version": 99, "script_id": SCRIPT_ID}))
    res.append(broke("снимок несёт настройки проекта",
                     live=dict(good["live"], **{".clasp.json": "x"})))
    res.append(broke("снимок несёт местное имя", live=dict(good["live"], **{"README.md": "x"})))
    res.append(broke("снимок несёт имя с путём",
                     live=dict(good["live"], **{"../Bridge.js": "x"})))

    # два FAIL-SAFE, где отказ НЕ обязан быть: паспорта зеркала нет вовсе (первое сведение)
    p_first = mirror_sync.plan(dict(good, mirror_meta=None, mirror={}))
    res.append(ok(p_first["ok"] and sorted(p_first["write"]) == sorted(PROD_FILES),
                  "БЛИЗНЕЦ: зеркало пустое и без паспорта → сводим всё (%d файлов)"
                  % len(p_first["write"])))
    p_same = mirror_sync.plan(dict(good, mirror_meta={"prod_version": 84, "script_id": SCRIPT_ID}))
    res.append(ok(p_same["ok"], "БЛИЗНЕЦ: та же версия @84 в паспорте → сводим (не отказ)"))

# ═══════════════ (3) МАШИНА НЕ УДАЛЯЕТ: прод уронил файл — ход владельца ══════════════════
print("\n(3) МАШИНА НЕ УДАЛЯЕТ — исчезнувший у прода файл называется, а не стирается:")
with tempfile.TemporaryDirectory() as tmp:
    snap, mir, good = _healthy(tmp)
    _write(mir, "Legacy.js", "у прода такого больше нет\n")
    f2 = _facts(snap, mir)
    p = mirror_sync.plan(f2)
    res.append(ok(not p["ok"] and "Legacy.js" in p["reason"] and "УДАЛЕНИЯ" in p["reason"],
                  "лишний в зеркале файл → отказ с именем: %s" % p["reason"][:96]))
    res.append(ok(os.path.exists(os.path.join(mir, "Legacy.js")),
                  "и сам файл на месте: решение его не трогало"))
    res.append(ok(all(not isinstance(n.func, ast.Attribute) or n.func.attr not in
                      ("remove", "unlink", "rmtree", "rmdir")
                      for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)),
                  "в решении нет ни одного вызова удаления"))
    hands = open(os.path.join(REPO, "bridge_deploy.py"), encoding="utf-8").read()
    hands_calls = [n for n in ast.walk(ast.parse(hands)) if isinstance(n, ast.Call)]
    res.append(ok(all(not isinstance(n.func, ast.Attribute) or n.func.attr not in
                      ("remove", "unlink", "rmtree", "rmdir") for n in hands_calls),
                  "и в руках выкладки — тоже ни одного: удалять зеркало нечем"))

    # близнец: местные файлы зеркала исчезнувшими НЕ считаются
    p_local = mirror_sync.plan(dict(good, mirror=dict(good["mirror"], **{"README.md": "x"})))
    res.append(ok(p_local["ok"], "БЛИЗНЕЦ: местный README.md отказа не рождает"))

# ═══════════════════ (4) ПЛАН И ПАСПОРТ: форма голденом ЖИВОГО паспорта ══════════════════
print("\n(4) ПЛАН И ПАСПОРТ — форма сверена с живым bridge_prod/MIRROR.json:")
with tempfile.TemporaryDirectory() as tmp:
    snap, mir, good = _healthy(tmp)
    p = mirror_sync.plan(good)
    res.append(ok(p["write"] == ["Bridge.js"] and p["same"] == ["ReadFleet.js", "appsscript.json"],
                  "план: класть %s, совпадало %s" % (p["write"], p["same"])))
    res.append(ok(p["head_equals_prod"] is True and p["head_diff_files"] == [],
                  "HEAD == прод, расхождений нет"))

    snap2 = _make_snapshot(os.path.join(tmp, "snap2"),
                           head=dict(PROD_FILES, **{"Bridge.js": "чужая незадеплоенная работа\n"}))
    p2 = mirror_sync.plan(_facts(snap2, mir))
    res.append(ok(p2["head_equals_prod"] is False and p2["head_diff_files"] == ["Bridge.js"],
                  "HEAD впереди прода — назван поимённо: %s" % p2["head_diff_files"]))

    pp = mirror_sync.passport(p, "2026-08-23 14:00:00 UTC", "тест")
    live_pp = json.load(open(PASSPORT, encoding="utf-8"))
    res.append(ok(set(pp) == set(live_pp),
                  "ключи паспорта == ключи ЖИВОГО MIRROR.json: %s" % sorted(pp)))
    res.append(ok(isinstance(pp["prod_version"], int) and pp["prod_version"] == 84
                  and pp["script_id"] == SCRIPT_ID and isinstance(pp["head_equals_prod"], bool)
                  and pp["files_sha256"],
                  "паспорт проходит те же проверки, что замок test_bridge_prod_mirror"))
    res.append(ok(pp["pulled_utc"] == "2026-08-23 14:00:00 UTC",
                  "время снятия — то, что принесли РУКИ (решение своих часов не имеет)"))
    res.append(ok(mirror_sync.passport(p, "", "тест") is None
                  and mirror_sync.passport(p, "2026-08-23 14:00:00 UTC", "") is None,
                  "без времени снятия и без имени снявшего паспорт НЕ собирается"))
    res.append(ok(mirror_sync.passport(mirror_sync.plan({}), "2026-08-23 14:00:00 UTC", "т") is None,
                  "по отказу паспорта не бывает вовсе"))

# ═══════════════════════ (5) ОБРАТНОЕ ЧТЕНИЕ ═════════════════════════════════════════════
print("\n(5) ОБРАТНОЕ ЧТЕНИЕ — расписке записи не верим:")
with tempfile.TemporaryDirectory() as tmp:
    snap, mir, good = _healthy(tmp)
    p = mirror_sync.plan(good)
    exp = dict(p["files_sha256"])
    res.append(ok(mirror_sync.verify(p, exp)["ok"], "БЛИЗНЕЦ: легло ровно то, что в паспорте"))
    v_missing = mirror_sync.verify(p, {k: v for k, v in exp.items() if k != "Bridge.js"})
    res.append(ok(not v_missing["ok"] and "Bridge.js" in v_missing["reason"],
                  "недоложенный файл назван: %s" % v_missing["reason"][:80]))
    v_wrong = mirror_sync.verify(p, dict(exp, **{"Bridge.js": "0" * 64}))
    res.append(ok(not v_wrong["ok"] and "иначе" in v_wrong["reason"],
                  "легло ИНОЕ содержимое — поймано: %s" % v_wrong["reason"][:80]))
    v_extra = mirror_sync.verify(p, dict(exp, **{"Stranger.js": "1" * 64}))
    res.append(ok(not v_extra["ok"] and "Stranger.js" in v_extra["reason"],
                  "лишний файл в зеркале назван: %s" % v_extra["reason"][:80]))
    res.append(ok(not mirror_sync.verify(p, None)["ok"],
                  "зеркало не перечитано → НЕ «ок», а «что легло, неизвестно»"))

# ═══════════════════ (6) РУКИ НА МОКАХ: sync_mirror пишет во ВРЕМЕННОЕ зеркало ═══════════
print("\n(6) РУКИ — sync_mirror кладёт прод в зеркало и перечитывает написанное:")


def _recon_fake(version=84, rc=0, files=None, head=None, script_id=SCRIPT_ID, meta=True):
    """Мок отпечатка: наполняет каталог снимка так же, как живой recon. Сети нет."""
    def go(snap_dir):
        if rc == 0:
            _make_snapshot(snap_dir, version=version, files=files, head=head,
                           script_id=script_id, meta=meta)
            return 0, "прод обслуживает версию: %d" % version
        return rc, "HTTP Error 403: Forbidden"
    return go


with tempfile.TemporaryDirectory() as tmp:
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    snap = os.path.join(tmp, "snap")
    before_readme = _sha_file(os.path.join(mir, "README.md"))
    with patch("bridge_deploy._recon", side_effect=_recon_fake()):
        mok, mdetail, mver = bridge_deploy.sync_mirror(mirror_dir=mir, snap_dir=snap)
    res.append(ok(mok and mver == 84, "сведено: %s (версия @%s)" % (mdetail, mver)))
    res.append(ok(_sha_file(os.path.join(mir, "Bridge.js")) == _sha_text(PROD_FILES["Bridge.js"]),
                  "файл прода лёг в зеркало побайтно"))
    pp = json.load(open(os.path.join(mir, "MIRROR.json"), encoding="utf-8"))
    res.append(ok(pp["prod_version"] == 84 and pp["script_id"] == SCRIPT_ID,
                  "паспорт переписан: @%s" % pp["prod_version"]))
    res.append(ok(pp["files_sha256"] == {n: _sha_text(t) for n, t in PROD_FILES.items()},
                  "паспорт называет РОВНО то, что лежит на диске"))
    res.append(ok(_sha_file(os.path.join(mir, "README.md")) == before_readme,
                  "местная документация зеркала не тронута"))
    res.append(ok(not os.path.exists(os.path.join(mir, ".clasp.json")),
                  "настроек проекта в зеркале не появилось — вторым стволом оно не стало"))

    # ПАСПОРТ ПЕРЕПИСЫВАЕТСЯ ДАЖЕ ПРИ СОВПАВШИХ БАЙТАХ: версия — тоже утверждение о проде
    with patch("bridge_deploy._recon", side_effect=_recon_fake(version=85)):
        mok2, mdetail2, mver2 = bridge_deploy.sync_mirror(mirror_dir=mir,
                                                          snap_dir=os.path.join(tmp, "snap85"))
    pp2 = json.load(open(os.path.join(mir, "MIRROR.json"), encoding="utf-8"))
    res.append(ok(mok2 and pp2["prod_version"] == 85,
                  "байты те же, версия @84 → @85: паспорт всё равно сведён (%s)" % mdetail2))

    # ОТКАЗ: отпечаток не снят — зеркало не тронуто НИ НА БАЙТ
    state_before = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    with patch("bridge_deploy._recon", side_effect=_recon_fake(rc=2)):
        bok, bdetail, bver = bridge_deploy.sync_mirror(mirror_dir=mir,
                                                       snap_dir=os.path.join(tmp, "snapbad"))
    state_after = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    res.append(ok(not bok and bver is None and "ОТПЕЧАТОК НЕ СНЯТ" in bdetail,
                  "отпечаток не снят → отказ громкий: %s" % bdetail[:80]))
    res.append(ok(state_before == state_after, "и зеркало при отказе не тронуто ни на байт"))

    # ОТКАЗ: снимок без meta.json (отпечаток «вроде снят», а версии нет)
    with patch("bridge_deploy._recon", side_effect=_recon_fake(meta=False)):
        nok, ndetail, _ = bridge_deploy.sync_mirror(mirror_dir=mir,
                                                    snap_dir=os.path.join(tmp, "snapnometa"))
    res.append(ok(not nok and "meta.json" in ndetail,
                  "снимок без meta.json → отказ: %s" % ndetail[:80]))

# ═════════ (7) ГРОМКИЙ ОТКАЗ В ЦИКЛЕ: прод выложен, а зеркало НЕ сведено → код 4 ═════════
print("\n(7) ГРОМКИЙ ОТКАЗ В ЦИКЛЕ — ноль значит «прод выложен И зеркало ему соответствует»:")


def _client_ok(zones=16):
    c = MagicMock()
    c.ping.return_value = {"ok": True}
    c.delivery_zones_get.return_value = {
        "ok": True, "data": {"zones": [{"name": "z%d" % i} for i in range(zones)]}}
    return c


def _client_ping_fail():
    c = MagicMock()
    c.ping.return_value = {"ok": False, "error": "smoke_test_forced_fail"}
    return c


def _runner(recon_rc=0, version=84, snap_files=None, calls=None):
    """Мок всех подпроцессов цикла. Отпечаток НАПОЛНЯЕТ каталог снимка, как живой recon."""
    def fake_run(args, **kw):
        args = list(args)
        if calls is not None:
            calls.append(args)
        if "gate.py" in str(args):
            return MagicMock(returncode=0, stdout="✅ ГЕЙТ полный", stderr="")
        if args and args[0] == "node":
            return MagicMock(returncode=0, stdout="", stderr="")
        if args == ["clasp", "deployments"]:
            return MagicMock(returncode=0, stdout="- %s @83 - Splinter Bridge\n" % PROD_ID,
                             stderr="")
        if args[:2] == ["clasp", "redeploy"]:
            return MagicMock(returncode=0, stdout="Updated.", stderr="")
        if bridge_deploy.RECON in args:
            if recon_rc == 0:
                _make_snapshot(args[-1], version=version, files=snap_files)
                return MagicMock(returncode=0, stdout="прод обслуживает версию: %d" % version,
                                 stderr="")
            return MagicMock(returncode=recon_rc, stdout="", stderr="HTTP Error 403")
        return MagicMock(returncode=0, stdout="", stderr="")
    return fake_run


def _cycle(runner, client, mirror_dir):
    with tempfile.TemporaryDirectory(prefix="tb_bridge_build_") as target:
        with open(os.path.join(target, bridge_deploy.CLASP_SETTINGS), "w") as fh:
            fh.write('{"scriptId":"test"}')
        with patch("bridge_deploy.subprocess.run", side_effect=runner), \
             patch("bridge_deploy._make_bridge_client", return_value=client), \
             patch("bridge_deploy.time.sleep"), \
             patch("bridge_deploy._alert") as al, \
             patch("bridge_deploy._log_cc") as lg:
            code = bridge_deploy.deploy(target=target, mirror_dir=mirror_dir)
    return code, al, lg


with tempfile.TemporaryDirectory() as tmp:
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    before = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    code, al, lg = _cycle(_runner(recon_rc=2), _client_ok(), mir)
    after = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    logs = " ".join(str(c) for c in lg.call_args_list)
    alerts = " ".join(str(c) for c in al.call_args_list)
    res.append(ok(code == 4, "код возврата 4 «прод выложен, зеркало НЕ сведено» (получили %s)"
                  % code))
    res.append(ok("ЗЕРКАЛО НЕ СВЕДЕНО" in logs, "cc_log говорит это ДОСЛОВНО"))
    res.append(ok(al.call_count >= 1 and "зеркало" in alerts.lower(),
                  "владельцу ушёл алерт: %s" % alerts[:90]))
    res.append(ok(before == after, "зеркало при этом не тронуто ни на байт"))

# ═════════════════════ (8) УСПЕШНЫЙ ЦИКЛ ЦЕЛИКОМ ═════════════════════════════════════════
print("\n(8) УСПЕШНЫЙ ЦИКЛ — код 0 только вместе со сведённым зеркалом:")
with tempfile.TemporaryDirectory() as tmp:
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    calls = []
    code, al, lg = _cycle(_runner(calls=calls), _client_ok(), mir)
    logs = " ".join(str(c) for c in lg.call_args_list)
    pp = json.load(open(os.path.join(mir, "MIRROR.json"), encoding="utf-8"))
    res.append(ok(code == 0, "код 0 (получили %s)" % code))
    res.append(ok(pp["prod_version"] == 84, "зеркало сведено к @%s" % pp["prod_version"]))
    res.append(ok("зеркало сведено" in logs and "@84" in logs,
                  "cc_log называет сведение и версию"))
    res.append(ok(al.call_count == 0, "алертов на успешном цикле нет: %d" % al.call_count))
    res.append(ok(lg.call_count == 1, "одна запись в cc_log, а не две: %d" % lg.call_count))
    # ГРАНИЦА: отпечаток снят НЕ clasp'ом, а read-only скриптом
    recon_calls = [c for c in calls if bridge_deploy.RECON in c]
    res.append(ok(len(recon_calls) == 1 and recon_calls[0][0] == bridge_deploy.PY,
                  "отпечаток снят РОВНО раз и python-скриптом: %s" % (recon_calls[0][:2],)))
    res.append(ok(not any(c[:1] == ["clasp"] and bridge_deploy.RECON in c for c in calls),
                  "clasp в ветке сведения не участвует НИ РАЗУ"))
    clasp_calls = [c for c in calls if c and c[0] == "clasp"]
    res.append(ok([c[1] for c in clasp_calls] == ["deployments", "redeploy"],
                  "clasp звался только для версии и redeploy: %s" % [c[1] for c in clasp_calls]))

# ═══════════════ (9) ОТКАТ РУЧКОЙ MIRROR_SYNC=0 — прежнее поведение ══════════════════════
print("\n(9) ОТКАТ — MIRROR_SYNC=0 гасит ветку ДО отпечатка:")
with tempfile.TemporaryDirectory() as tmp:
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    before = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    calls = []
    os.environ["MIRROR_SYNC"] = "0"
    try:
        code, al, lg = _cycle(_runner(calls=calls), _client_ok(), mir)
    finally:
        os.environ["MIRROR_SYNC"] = "1"
    after = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    logs = " ".join(str(c) for c in lg.call_args_list)
    res.append(ok(code == 0 and before == after, "код 0, зеркало не тронуто (как до 23.08)"))
    res.append(ok(not any(bridge_deploy.RECON in c for c in calls),
                  "отпечаток не снимался вовсе — ветка мертва ДО обращения к миру"))
    res.append(ok("НЕ сведено" in logs and "MIRROR_SYNC=0" in logs,
                  "но cc_log честно называет и состояние, и ручку"))
    res.append(ok(bridge_deploy._mirror_enabled({"MIRROR_SYNC": "0"}) is False
                  and bridge_deploy._mirror_enabled({}) is True,
                  "ручка читается: «0» — выкл, умолчание — вкл"))

# ═══════════════════════════ (10) ГРАНИЦЫ ════════════════════════════════════════════════
print("\n(10) ГРАНИЦЫ — упавший смок зеркала не касается, боевое зеркало не тронуто:")
with tempfile.TemporaryDirectory() as tmp:
    mir = _make_mirror(os.path.join(tmp, "mirror"))
    before = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    calls = []
    code, al, lg = _cycle(_runner(calls=calls), _client_ping_fail(), mir)
    after = {n: _sha_file(os.path.join(mir, n)) for n in sorted(os.listdir(mir))}
    res.append(ok(code == 1, "смок упал → прежний код 1 (получили %s)" % code))
    res.append(ok(not any(bridge_deploy.RECON in c for c in calls),
                  "отпечаток НЕ снимался: состояние прода определяет откат, а не мы"))
    res.append(ok(before == after, "зеркало не тронуто на пути отката"))

res.append(ok(_live_mirror_state() == LIVE_BEFORE,
              "БОЕВОЕ зеркало bridge_prod/ не изменено за весь прогон (%d файлов)"
              % len(LIVE_BEFORE)))
res.append(ok(bridge_deploy.MIRROR_DIR == MIRROR,
              "по умолчанию руки метят в боевое зеркало (тесты подменяют его явно)"))
guard_src = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("mirror_sync" not in guard_src,
              "pretool_guard.py о сведении зеркала не знает ничего — он не изменён"))

# ══════════ (11) ОДИН ДОМ У ПРАВИЛА МЕСТНЫХ ФАЙЛОВ ══════════════════════════════════════
print("\n(11) ОДИН ДОМ У ПРАВИЛА — сверка и запись судят местные файлы ОДИНАКОВО:")
_spec = importlib.util.spec_from_file_location(
    "bridge_prod_diff_probe", os.path.join(REPO, "deploy", "bridge_prod_diff.py"))
_diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diff)
table = ["MIRROR.json", "README.md", "ЧИТАЙ.MD", "Bridge.js", "appsscript.json", "ReadFleet.js"]
disagree = [n for n in table if _diff._local_only(n) != mirror_sync.is_local_only(n)]
res.append(ok(not disagree, "оба читателя согласны на таблице имён (расхождений %d)"
              % len(disagree)))
res.append(ok(mirror_sync.is_local_only("MIRROR.json") and mirror_sync.is_local_only("README.md")
              and not mirror_sync.is_local_only("Bridge.js"),
              "правило по существу: паспорт и .md — местные, .js — прод"))

# ══════════ (12) ОТПЕЧАТОК НАЗЫВАЕТ ПРОЕКТ ══════════════════════════════════════════════
print("\n(12) ОТПЕЧАТОК НАЗЫВАЕТ ПРОЕКТ — иначе решение отказывало бы всегда:")
recon_src = open(os.path.join(REPO, "deploy", "bridge_prod_recon.py"), encoding="utf-8").read()
res.append(ok('"script_id": SCRIPT_ID' in recon_src,
              "recon пишет script_id в meta.json снимка"))
res.append(ok('SCRIPT_ID = "%s"' % SCRIPT_ID in recon_src,
              "и это ТОТ проект, что в CLAUDE.md"))

print("\n%s / total %d" % ("ALL PASS ✅" if all(res) else "‼️ ЕСТЬ ПАДЕНИЯ", len(res)))
sys.exit(0 if all(res) else 1)
