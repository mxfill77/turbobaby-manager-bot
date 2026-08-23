#!/usr/bin/env python3
"""РЕШЕНИЕ «сводить ли зеркало прод-моста к свежему отпечатку» (23.08.2026).

ЗАЧЕМ. Пункт «после выкладки обновить зеркало» жил ПРОЗОЙ и за всю жизнь не получил ни одной
машины: `bridge_deploy.py` называл зеркало один раз строкой-подсказкой и обновлять его не умел,
у `bridge_prod/MIRROR.json` за всю жизнь РОВНО ОДИН коммит — тот, которым зеркало заведено
(`7e348d4`, 10.08), а паспортный сторож ловить этот класс не может по устройству: он судит
согласованность зеркала с САМИМ СОБОЙ. Цена измерена живым случаем: прод уехал @79 → @83
выкладкой 23.08 06:40, зеркало сведено только 23.08 12:20 отдельным заходом — 5 ч 40 мин прод и
зеркало расходились, и сборка «поверх зеркала» стёрла бы дверь `service_undo` МОЛЧА.

ЧТО ЗДЕСЬ, А ЧЕГО НЕТ. Здесь — РЕШЕНИЕ: принесли факты о свежем отпечатке → сказано, сводить
зеркало или отказать и почему. Руки (снять отпечаток, скопировать файлы, записать паспорт,
перечитать написанное) живут отдельно, в `bridge_deploy._mirror_*`. Импортов НОЛЬ, и это замок:
появись у решения сеть — оно спросило бы Apps Script САМО, и «отпечаток снят» перестало бы
зависеть от того, снят ли он на самом деле; появись файл — оно переписало бы зеркало мимо
единственной двери записи; появись время — «снято в …» стало бы временем РЕНДЕРА, а не СНЯТИЯ,
то есть паспорт начал бы врать свежестью ровно тем способом, против которого написан.
Страж чистоты — `MIRROR_SYNC_PURE` в `invariants_check.py` (ast, в гейте).

ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО (тот же, что у О3 и `write_fact`). «Сводить» возвращается РОВНО
ОДНИМ путём: отпечаток снят с кодом 0 · снимок называет версию прода ЧИСЛОМ · исходники
задеплоенной версии прочитаны и их не ноль · HEAD прочитан (иначе утверждение о HEAD в паспорте
нечем заполнить) · нынешнее зеркало прочитано · снимок назвал script_id и он тот же · версия не
младше той, что уже в зеркале. Всё прочее — отказ с НАЗВАННОЙ причиной, и отказ этот громкий:
зеркало, оставшееся отставшим молча, и есть та самая мина.

МАШИНА НЕ УДАЛЯЕТ. Файл, который есть в зеркале и которого больше нет у прода, — событие редкое
и значимое, а свести зеркало значило бы УДАЛИТЬ файл в репозитории вне временных каталогов, то
есть красную зону владельца. Поэтому такой случай — отказ с именем файла, а не тихое удаление:
власть машины строго добавляющая (положить то, что у прода есть), и это названный предел.
"""

PASSPORT_NAME = "MIRROR.json"
CLASP_SETTINGS = ".clasp.json"
WHAT_IS = "ЗЕРКАЛО задеплоенного Apps Script Bridge. Истина — Google, здесь снимок под git."


def is_local_only(name):
    """Местный файл зеркала — паспорт и документация; у Apps Script таких не бывает по устройству.

    ОДИН дом у правила намеренно: этим же различителем живёт `deploy/bridge_prod_diff._local_only`
    (он зовёт эту функцию). Две реализации одного правила разошлись бы молча и в обе стороны —
    сверка перестала бы видеть расхождение, а запись снесла бы README зеркала.
    """
    n = (name or "").strip()
    return n == PASSPORT_NAME or n.lower().endswith(".md")


def name_is_safe(name):
    """Имя из снимка годится для записи в зеркало: без путей, без «..», без скрытых файлов."""
    n = name or ""
    if not n or n != n.strip():
        return False
    if "/" in n or "\\" in n or n.startswith("."):
        return False
    if n in (".", ".."):
        return False
    return True


def _no(reason):
    """Отказ с названной причиной. Пустого отказа не бывает: молчание и есть болезнь."""
    return {"ok": False, "reason": reason, "version": None,
            "write": [], "same": [], "remove": [], "files_sha256": {},
            "head_equals_prod": None, "head_diff_files": [], "script_id": ""}


def _is_num(v):
    return isinstance(v, int) and not isinstance(v, bool)


def plan(facts):
    """Факты о свежем отпечатке → «сводить зеркало» либо отказ с причиной.

    facts (готовит `bridge_deploy._mirror_facts`, ничего не додумывая):
      recon_rc   int|None  — код возврата отпечатка; None = отпечаток не снимали ВОВСЕ
      recon_tail str       — хвост вывода отпечатка (в текст отказа)
      meta       dict|None — meta.json снимка (prod_version, script_id)
      live       dict|None — {имя: sha256} файлов ЗАДЕПЛОЕННОЙ версии из снимка
      head       dict|None — {имя: sha256} HEAD проекта из того же снимка
      mirror     dict|None — {имя: sha256} нынешнего зеркала БЕЗ местных файлов
      mirror_meta dict|None — нынешний паспорт зеркала (с чем сверяем проект и версию)

    Возвращает {'ok', 'reason', 'version', 'write', 'same', 'remove', 'files_sha256',
                'head_equals_prod', 'head_diff_files', 'script_id'}.
    """
    f = facts if isinstance(facts, dict) else {}

    rc = f.get("recon_rc")
    if rc is None:
        return _no("отпечаток прода не снимали вовсе — сводить зеркало не к чему")
    if rc != 0:
        tail = " ".join((f.get("recon_tail") or "").split())[:200]
        return _no("ОТПЕЧАТОК НЕ СНЯТ (код %s)%s — о состоянии прода не заявляем и зеркало не трогаем"
                   % (rc, (": " + tail) if tail else ""))

    meta = f.get("meta")
    if not isinstance(meta, dict):
        return _no("снимок без meta.json — версия прода не названа, писать в паспорт нечего")

    ver = meta.get("prod_version")
    if not _is_num(ver) or ver <= 0:
        return _no("снимок не называет версию прода числом (%r) — паспорт без версии ничего не стережёт"
                   % (ver,))

    sid = (meta.get("script_id") or "").strip()
    if not sid:
        return _no("снимок не называет script_id проекта — чей это мост, из отпечатка не следует")

    live = f.get("live")
    if live is None:
        return _no("исходники задеплоенной версии @%d из снимка не прочитаны" % ver)
    if not live:
        return _no("снимок задеплоенной версии @%d пуст — зеркало таким не переписывают" % ver)

    head = f.get("head")
    if head is None:
        return _no("HEAD проекта в снимке не прочитан — утверждение «HEAD == прод» в паспорте "
                   "нечем заполнить, а выдумывать его нельзя: им судят, что сотрёт заливка")

    mirror = f.get("mirror")
    if mirror is None:
        return _no("нынешнее зеркало не прочитано — с чем сводить и что расходится, неизвестно")

    was = f.get("mirror_meta") if isinstance(f.get("mirror_meta"), dict) else {}
    old_sid = (was.get("script_id") or "").strip()
    if old_sid and old_sid != sid:
        return _no("отпечаток снят с ДРУГОГО проекта Apps Script (%s ≠ %s в паспорте зеркала)"
                   % (sid, old_sid))
    old_ver = was.get("prod_version")
    if _is_num(old_ver) and ver < old_ver:
        return _no("отпечаток описывает @%d, а зеркало уже описывает @%d — прод назад сам не едет; "
                   "разбирается руками, машина такое не сводит" % (ver, old_ver))

    for name in sorted(live):
        if name == CLASP_SETTINGS:
            return _no("снимок несёт настройки проекта %s — зеркало не станет вторым заряженным "
                       "стволом" % CLASP_SETTINGS)
        if is_local_only(name):
            return _no("снимок несёт местное имя «%s» — оно столкнулось бы с документацией зеркала"
                       % name)
        if not name_is_safe(name):
            return _no("снимок несёт негодное имя файла «%s» — в зеркало пишем только простые имена"
                       % name)

    gone = sorted(n for n in mirror if n not in live and not is_local_only(n))
    if gone:
        return _no("прод @%d больше не несёт %s, а зеркало держит — сведение потребовало бы "
                   "УДАЛЕНИЯ файла в репозитории вне временных каталогов, это решение владельца; "
                   "машина такого не принимает" % (ver, ", ".join(gone)))

    write = sorted(n for n in live if mirror.get(n) != live[n])
    same = sorted(n for n in live if mirror.get(n) == live[n])
    head_diff = sorted(n for n in set(head) | set(live) if head.get(n) != live.get(n))

    return {"ok": True, "reason": "", "version": ver,
            "write": write, "same": same, "remove": [],
            "files_sha256": dict(live),
            "head_equals_prod": not head_diff, "head_diff_files": head_diff,
            "script_id": sid}


def passport(pl, pulled_utc, pulled_by):
    """План + ВРЕМЯ СНЯТИЯ → паспорт зеркала. None — паспорт собирать не из чего.

    Время приносят руки и оно обязательно: паспорт без него врал бы свежестью, а это тот самый
    класс, ради которого зеркало вообще заведено под версиями. Форма — та же, что у живого
    `bridge_prod/MIRROR.json` (её стережёт tests/test_bridge_prod_mirror.py).
    """
    if not (isinstance(pl, dict) and pl.get("ok")):
        return None
    when = (pulled_utc or "").strip()
    if not when:
        return None
    who = (pulled_by or "").strip()
    if not who:
        return None
    return {
        "files_sha256": dict(pl.get("files_sha256") or {}),
        "head_diff_files": list(pl.get("head_diff_files") or []),
        "head_equals_prod": bool(pl.get("head_equals_prod")),
        "prod_version": int(pl.get("version")),
        "pulled_by": who,
        "pulled_utc": when,
        "script_id": pl.get("script_id"),
        "что_это": WHAT_IS,
    }


def verify(pl, after):
    """ОБРАТНОЕ ЧТЕНИЕ: что легло в зеркало, а не что мы собирались положить.

    `after` — {имя: sha256}, перечитанное с диска ПОСЛЕ записи (без местных файлов). Расписка
    записи здесь не в счёт: класс «нет ответа прочитано как ответ» закрывают перечитыванием
    факта, а не успешным возвратом функции записи.
    """
    if not (isinstance(pl, dict) and pl.get("ok")):
        return {"ok": False, "reason": "проверять нечего: сведения не было"}
    if after is None:
        return {"ok": False, "reason": "зеркало после записи не перечитано — что легло, неизвестно"}
    expect = pl.get("files_sha256") or {}
    missing = [n for n in sorted(expect) if n not in after]
    wrong = [n for n in sorted(expect) if n in after and after[n] != expect[n]]
    extra = [n for n in sorted(after) if n not in expect]
    if missing or wrong or extra:
        parts = []
        if missing:
            parts.append("не легли: " + ", ".join(missing))
        if wrong:
            parts.append("легли иначе: " + ", ".join(wrong))
        if extra:
            parts.append("лишние в зеркале: " + ", ".join(extra))
        return {"ok": False, "reason": "зеркало после записи не совпало с паспортом (%s)"
                                       % "; ".join(parts)}
    return {"ok": True, "reason": ""}
