#!/usr/bin/env python3
"""РЕЕСТР ЗНАНИЯ — авто-сверка карта↔реальность (первый камень, READ-ONLY детектор).

Зачем: система должна САМА ловить расхождения между записанным знанием (мозг: KB_MASTER/KB_PULSE/
манифест Brain) и живой реальностью (git manager-bot), а не ждать ручной ревизии. Это фундамент под
мета-дирижёр (агент читает мозг → мозг должен быть цел). Начато скромно и РАСТЯЖИМО.

ГРАНИЦЫ (священны):
- READ-ONLY ПОЛНОСТЬЮ. Ничего не пишет в таблицы/деньги/CRM/Лист1. Только читает мозг+git → отчёт.
- ТОЛЬКО ВНУТРЕННИЙ КОНТУР. Клиентские (userbot/PC/moderation/suggest/draft) коммиты в KB_MASTER
  сознательно НЕ проверяются (§4 изоляция контуров — сверка контуров = отдельный будущий камень).
- Отдельный модуль-детектор: ничего существующего (splinter/оркестратор/инбокс) не трогает.

РАСТЯЖИМАЯ АРХИТЕКТУРА: проверка = функция `fn(world, run)`, зарегистрированная @register("ИМЯ").
Добавить новую проверку = дописать одну функцию в СПИСОК CHECKS, каркас не переписывать (см. точку
расширения «БУДУЩИЕ КАМНИ» внизу).

КАЛИБРОВКА (не шуметь ложно): сигналить только НАСТОЯЩЕЕ расхождение, не дрейф формулировок. Порог
консервативный — лучше пропустить сомнительное, чем завалить ложными (урок тест-шума).

ЗАПУСК:
  venv/bin/python3 registry_check.py            # живой прогон на текущем мозге → отчёт
  venv/bin/python3 registry_check.py --self-test # самотест: синтетические расхождения → PASS/FAIL
  venv/bin/python3 registry_check.py --json      # машинный вывод (для будущей команды 328)
"""
import os
import re
import sys
import json
import subprocess
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.abspath(__file__))

# --- Маркеры контуров (для проверки КАРТА↔GIT) -------------------------------------------------
# Клиентский контур: коммиты userbot/PC/модерации/подсказок/черновиков — НЕ наш камень (§4).
CLIENT_MARK = re.compile(
    r"userbot|юзербот|cowork|pc_agent|pc-agent|dispatch|диспатч|suggest|collect_booking|"
    r"moderation|модерац|клиент|черновик|draft|playbook|приветств|@turbophuket|@samhold|"
    r"suggest_llm|интейк|intake|промпт|greeting|нет в парке|модел|_cli_llm|язык",
    re.I)
# Внутренний контур: splinter/оркестратор/bridge/gate/devbot/инбокс/конверты и пр.
INTERNAL_MARK = re.compile(
    r"splinter|orchestrator|оркестратор|дирижёр|devbot|дев-бот|headless|gate\.py|bridge|бридж|"
    r"bot\.py|claude_client|claude code|termux|термукс|orchestrator_daemon|инбокс|inbox|"
    r"конверт|envelope|очеред",
    re.I)

HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")   # commit-подобный токен (короткий/полный hex)


def _hashes(text):
    """Хеш-подобные токены (7-40 hex, минимум одна буква a-f — иначе год/число, не коммит)."""
    return [h for h in set(HASH_RE.findall(text or "")) if re.search(r"[a-f]", h)]


# --- Пороги проверки СЧЁТ BRAIN ----------------------------------------------------------------
BRAIN_DOC_NORM = 22          # база на 06.07.2026 (24 ключа манифеста − folder_id − дубль turbobaby_faq)
BRAIN_DOC_CLUTTER_AT = 28    # засорение §6: сигнал при ≥ этого (норма +6 зарегистрированных доков)
BRAIN_DOC_FLOOR = 15         # усушка/порча манифеста: сигнал при < этого

# Алиасы KB_-имён → ключи манифеста (для проверки КАРТА↔ПУЛЬС, ссылки на доки в пульсе)
KB_ALIAS = {
    "master": "index", "pulse": "pulse", "faq": "faq", "rules": "rules", "infra": "infra",
    "state_model": "state_model", "claude_code_log": "cc_log", "claude_review": "review",
    "executors_map": "executors_map", "orchestrator_plan": "orchestrator_plan",
    "orchestrator_safety": "orchestrator_safety", "roadmap_master": "roadmap_master",
    "north_star": "roadmap_master", "roadmap_v2": "roadmap_master",
}


# ============================================================================================
#  МИР (World) — то, что детектор ЧИТАЕТ. Живой = Bridge+git; фейковый = мок для тестов/самотеста.
# ============================================================================================
class World:
    """Интерфейс источника правды. read_doc(name)->str|None, manifest()->dict, git_resolves(h)->bool."""
    def read_doc(self, name):
        raise NotImplementedError
    def manifest(self):
        raise NotImplementedError
    def git_resolves(self, short_hash):
        raise NotImplementedError
    def git_head(self):
        raise NotImplementedError


class LiveWorld(World):
    """Живой мир: KB_* через Bridge (read-only _call), коммиты через git manager-bot."""
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO, ".env"))
        from bridge_client import BridgeClient
        self._c = BridgeClient(timeout=45)
        self._doc_cache = {}
        self._git_cache = {}
        self._man = None

    def read_doc(self, name):
        if name not in self._doc_cache:
            r = self._c._call("read_doc", name=name)
            self._doc_cache[name] = (r.get("text", "") or "") if r.get("ok") else None
        return self._doc_cache[name]

    def manifest(self):
        if self._man is None:
            r = self._c._call("list_brain")
            self._man = r.get("manifest", {}) if r.get("ok") else None
        return self._man

    def git_resolves(self, short_hash):
        if short_hash not in self._git_cache:
            r = subprocess.run(["git", "-C", REPO, "cat-file", "-e", short_hash + "^{commit}"],
                               capture_output=True)
            self._git_cache[short_hash] = (r.returncode == 0)
        return self._git_cache[short_hash]

    def git_head(self):
        try:
            r = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                               capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else "?"
        except Exception:
            return "?"


# ============================================================================================
#  КАРКАС ПРОВЕРОК (растяжимый список)
# ============================================================================================
class CheckRun:
    """Результат одной проверки: расхождения (flag) + служебные заметки/пропуски (note)."""
    def __init__(self, name):
        self.name = name
        self.findings = []   # список (says, reality)
        self.notes = []      # список str (пропуск/деградация — НЕ расхождение)

    def flag(self, says, reality):
        self.findings.append((says, reality))

    def note(self, text):
        self.notes.append(text)


CHECKS = []   # [(имя, fn(world, run))] — ДОБАВИТЬ проверку = дописать сюда через @register


def register(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


# --------------------------------------------------------------------------------------------
#  ПРОВЕРКА 1 — КАРТА↔GIT (внутренний контур)
# --------------------------------------------------------------------------------------------
@register("КАРТА↔GIT")
def check_map_vs_git(world, run):
    """KB_MASTER цитирует коммиты как якоря вех. Сигнал — если хеш ЯВНО заявлен как ВНУТРЕННИЙ
    (splinter/оркестратор/инбокс…) и НЕ клиентский, но такого коммита нет в git manager-bot.
    Клиентские (userbot) коммиты сознательно пропускаем (§4: репо userbot на VPS нет, отдельный камень)."""
    txt = world.read_doc("index")
    if txt is None:
        run.note("KB_MASTER (name=index) не прочитан через Bridge — проверка пропущена")
        return
    lines = txt.split("\n")
    for h in _hashes(txt):
        if world.git_resolves(h):
            continue   # реальный коммит manager-bot — якорь цел
        # не резолвится: userbot-репо (ожидаемо) ИЛИ настоящий фантом. Сигналим ТОЛЬКО при
        # позитивном внутреннем маркере И отсутствии клиентского — консервативно (0 ложных на живом).
        internal_line = None
        for ln in lines:
            if h in ln and INTERNAL_MARK.search(ln) and not CLIENT_MARK.search(ln):
                internal_line = ln.strip()
                break
        if internal_line:
            run.flag(f"карта называет ВНУТРЕННИЙ коммит {h} («{internal_line[:70]}…»)",
                     f"такого коммита нет в git manager-bot (HEAD={world.git_head()})")


# --------------------------------------------------------------------------------------------
#  ПРОВЕРКА 2 — КАРТА↔ПУЛЬС
# --------------------------------------------------------------------------------------------
@register("КАРТА↔ПУЛЬС")
def check_pulse_vs_map(world, run):
    """KB_PULSE (свежий статус) не должен ссылаться на несуществующую веху/док карты.
    Консервативно ловим ДВА точных сигнала (без нечёткой семантики — чтобы не шуметь):
    (2a) §N, упомянутый в пульсе, отсутствует в KB_MASTER (сломанный указатель раздела);
    (2b) явный KB_-док в пульсе не зарегистрирован в манифесте мозга (ссылка в никуда)."""
    pulse = world.read_doc("pulse")
    if pulse is None:
        run.note("KB_PULSE (name=pulse) не прочитан через Bridge — проверка пропущена")
        return
    master = world.read_doc("index")
    man = world.manifest()

    # (2a) §N в пульсе → должен быть в KB_MASTER
    if master is not None:
        for sec in set(re.findall(r"§\s?\d+", pulse)):
            norm = sec.replace(" ", "")
            if norm not in master.replace(" ", ""):
                run.flag(f"пульс ссылается на раздел {norm}",
                         "в KB_MASTER такого раздела нет (сломанный указатель)")
    else:
        run.note("KB_MASTER не прочитан — под-проверку §-указателей пропустил")

    # (2b) явный KB_<имя> в пульсе → должен резолвиться в манифест
    if man is not None:
        keys = set(man.keys())
        for tok in set(re.findall(r"KB_[A-Za-z_]+", pulse)):
            base = tok[3:].lower()          # снять префикс KB_
            resolved = base in keys or KB_ALIAS.get(base) in keys
            if not resolved:
                run.flag(f"пульс ссылается на {tok}",
                         "такого дока нет в манифесте мозга (list_brain)")
    else:
        run.note("манифест мозга не прочитан — под-проверку KB-ссылок пропустил")


# --------------------------------------------------------------------------------------------
#  ПРОВЕРКА 3 — СЧЁТ ФАЙЛОВ BRAIN
# --------------------------------------------------------------------------------------------
@register("СЧЁТ BRAIN")
def check_brain_count(world, run):
    """Число активных доков мозга (манифест list_brain, distinct id без folder_id). Норма ~22.
    Сигнал при засорении (≥ CLUTTER_AT, триггер §6) или усушке/порче (< FLOOR).
    Считаем ЗАРЕГИСТРИРОВАННЫЕ доки (манифест) — read-only endpoint сырого списка папки нет;
    MCP-Drive авторизуемый/хрупок в headless, поэтому опора на манифест (всегда доступен)."""
    man = world.manifest()
    if man is None:
        run.note("манифест мозга (list_brain) не прочитан — проверка пропущена")
        return
    ids = {v for k, v in man.items() if k != "folder_id"}   # distinct doc-id, без папки
    n = len(ids)
    if n >= BRAIN_DOC_CLUTTER_AT:
        run.flag(f"норма ~{BRAIN_DOC_NORM} доков мозга",
                 f"в манифесте {n} distinct доков — засорение (триггер §6, чистка/архив)")
    elif n < BRAIN_DOC_FLOOR:
        run.flag(f"норма ~{BRAIN_DOC_NORM} доков мозга",
                 f"в манифесте всего {n} distinct доков — усушка/порча манифеста")


# ============================================================================================
#  БУДУЩИЕ КАМНИ (точка расширения) — НЕ реализуем сейчас, каркас готов принять:
#    @register("КАРТА↔ТАБЛИЦЫ")  — сверка описания листов в мозге со схемой Sheets через Bridge.
#    @register("СВЕРКА КОНТУРОВ") — внутренний↔клиентский (userbot-репо), когда появится доступ.
#    @register("РЕГИСТРАЦИЯ НОВОГО") — новый компонент в проде без записи в KB_MASTER.
#  Каждый — одна @register-функция fn(world, run); список выше не переписывать.
# ============================================================================================


def run_all(world):
    """Прогнать ВСЕ зарегистрированные проверки. → список CheckRun."""
    runs = []
    for name, fn in CHECKS:
        r = CheckRun(name)
        try:
            fn(world, r)
        except Exception as e:                       # проверка не должна ронять весь детектор
            r.note(f"проверка упала: {e!r}")
        runs.append(r)
    return runs


def format_report(runs, head=None):
    """Сжатый отчёт для телефона."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    findings = [(r.name, s, rl) for r in runs for (s, rl) in r.findings]
    notes = [(r.name, t) for r in runs for t in r.notes]
    out = [f"🧭 РЕЕСТР ЗНАНИЯ — сверка карта↔реальность  ({ts} UTC)"]
    if head:
        out.append(f"   git HEAD manager-bot: {head}")
    if not findings:
        out.append(f"✅ СХОДИТСЯ — {len(runs)} проверки, 0 расхождений")
    else:
        out.append(f"⚠️ {len(findings)} РАСХОЖДЕНИЙ ({len(runs)} проверки):")
        for i, (name, says, reality) in enumerate(findings, 1):
            out.append(f"{i}. [{name}] карта: {says}")
            out.append(f"     реальность: {reality}")
    for name, t in notes:
        out.append(f"· пропуск [{name}]: {t}")
    return "\n".join(out)


# ============================================================================================
#  САМОТЕСТ — синтетические заведомые расхождения (обкатка для владельца, standalone без pytest)
# ============================================================================================
class FakeWorld(World):
    def __init__(self, docs=None, man=None, git=None, head="deadbee"):
        self._docs = docs or {}
        self._man = man if man is not None else {}
        self._git = set(git or [])
        self._head = head

    def read_doc(self, name):
        return self._docs.get(name)

    def manifest(self):
        return self._man

    def git_resolves(self, short_hash):
        return short_hash in self._git

    def git_head(self):
        return self._head


def _healthy_world():
    """Чистый синтетический мозг: всё сходится."""
    man = {f"doc{i}": f"id{i}" for i in range(BRAIN_DOC_NORM)}
    man["folder_id"] = "FOLDER"
    master = ("KB_MASTER РАЗДЕЛ 5\n"
              "- инбокс подтверждений splinter commit aaaaaa1 в проде\n"
              "- userbot черновики commit bbbbbb2 (клиентский контур)\n")
    pulse = "2026-07-06 12:00 | 🟢 | всё ок | ничего не жду | детали→cc_log запись X"
    man["cc_log"] = "idcc"
    man["index"] = "idmaster"   # KB_MASTER зарегистрирован (как в живом манифесте)
    return FakeWorld(docs={"index": master, "pulse": pulse}, man=man,
                     git={"aaaaaa1"}, head="aaaaaa1")


def _self_test():
    cases = []   # (имя кейса, ожидаем-расхождений-в-этой-проверке, фабрика-мира, имя-проверки)

    # --- КАРТА↔GIT ---
    cases.append(("КАРТА↔GIT чистый (внутр.якорь есть, клиентский пропущен)", 0, _healthy_world, "КАРТА↔GIT"))
    dirty_git = _healthy_world()
    dirty_git._docs["index"] += "- оркестратор headless commit ccccccc9 в проде\n"   # внутр. + фантом
    cases.append(("КАРТА↔GIT грязный (внутр. фантомный коммит)", 1, lambda w=dirty_git: w, "КАРТА↔GIT"))
    iso_git = _healthy_world()
    iso_git._docs["index"] += "- userbot suggest.py commit ddddddd8 (нет в manager-bot)\n"  # клиентский фантом
    cases.append(("КАРТА↔GIT изоляция (клиентский фантом НЕ ловим, §4)", 0, lambda w=iso_git: w, "КАРТА↔GIT"))

    # --- КАРТА↔ПУЛЬС ---
    cases.append(("КАРТА↔ПУЛЬС чистый", 0, _healthy_world, "КАРТА↔ПУЛЬС"))
    dirty_sec = _healthy_world()
    dirty_sec._docs["pulse"] = "... | детали→KB_MASTER §99 про что-то"   # §99 нет в карте
    cases.append(("КАРТА↔ПУЛЬС грязный (§99 нет в карте)", 1, lambda w=dirty_sec: w, "КАРТА↔ПУЛЬС"))
    dirty_doc = _healthy_world()
    dirty_doc._docs["pulse"] = "... | детали→KB_PHANTOM запись"          # KB-док не в манифесте
    cases.append(("КАРТА↔ПУЛЬС грязный (KB_PHANTOM не в манифесте)", 1, lambda w=dirty_doc: w, "КАРТА↔ПУЛЬС"))

    # --- СЧЁТ BRAIN ---
    cases.append(("СЧЁТ BRAIN чистый (норма)", 0, _healthy_world, "СЧЁТ BRAIN"))
    clutter = _healthy_world()
    for i in range(10):
        clutter._man[f"junk{i}"] = f"jid{i}"    # раздуваем манифест
    cases.append(("СЧЁТ BRAIN грязный (засорение)", 1, lambda w=clutter: w, "СЧЁТ BRAIN"))

    print("=== САМОТЕСТ РЕЕСТРА ===")
    allpass = True
    for title, expect, factory, cname in cases:
        w = factory()
        runs = {r.name: r for r in run_all(w)}
        got = len(runs[cname].findings)
        ok = (got == expect)
        allpass &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  [{cname}] {title}: ждали {expect}, поймали {got}")
    print("ИТОГ:", "ВСЕ PASS ✅" if allpass else "ЕСТЬ FAIL ❌")
    return 0 if allpass else 1


def main(argv):
    if "--self-test" in argv:
        return _self_test()
    world = LiveWorld()
    runs = run_all(world)
    if "--json" in argv:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "head": world.git_head(),
            "checks": [{"name": r.name,
                        "findings": [{"says": s, "reality": rl} for s, rl in r.findings],
                        "notes": r.notes} for r in runs],
            "total_findings": sum(len(r.findings) for r in runs),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(format_report(runs, head=world.git_head()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
