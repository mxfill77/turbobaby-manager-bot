#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СЧЁТ СЕРИИ ЦЕПОЧЕК: пересчёт снимком очереди — РУКИ к чистому решению `chain_series`.

ЗАЧЕМ ОТДЕЛЬНО ОТ ДЕМОНА. Живой счёт ведёт демон: исход ему известен в момент терминала, там он
и пишет — в свой файл `chain_series.json`, ВНЕ очереди (рамка §8г, «где считать»). Пересчёт по
снимку очереди оставлен ТОЛЬКО для сверки и для замера задним числом, и вот почему он не может
быть основным: очередь ЗАТИРАЕТ тело карточки её же вердиктом. У задачи, дошедшей до владельца
обычной красной карточкой, `result` на момент `needs_approval` держал карточку, а после ответа
там лежит финальный отчёт («отклонено Филиппом» / рапорт конверта). Значит вопрос «какая
операция стояла за карточкой» из снимка ВОССТАНОВИМ НЕ ВСЕГДА — и ровно этот пробел закрывает
живая запись демона, у которой тело карточки есть в руках в момент события.

Что делает: снимок очереди (или файл) + журнал systemd (старты юнитов) + origin/main (коммиты)
→ вердикт каждой цепочки → серия, обрывы, вес, недельная доля шума. READ-ONLY: ни очередь, ни
таблицы, ни процессы не трогает — только читает.

    venv/bin/python3 chain_series_report.py                     # живой снимок очереди
    venv/bin/python3 chain_series_report.py --snapshot f.json   # из файла
    venv/bin/python3 chain_series_report.py --verify            # сверка с файлом демона
    venv/bin/python3 chain_series_report.py --verify --state s.json   # сверка с указанным файлом
    venv/bin/python3 chain_series_report.py --weeks             # доля шума по неделям

СВЕРКА (`--verify`) возвращает ТРИ исхода кодом: 0 сходится · 1 РАСХОЖДЕНИЕ (красное, названо
поимённо) · 2 НЕ СВЕРЕНО (файла нет · файл пуст · факты мира не прочитаны · общая почва пуста).
Файл она НЕ ПРАВИТ ни при каком исходе — см. блок «СВЕРКА» ниже и страж в tests/.
"""
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import chain_series as cs                      # noqa: E402  чистое решение
import curator_ops                             # noqa: E402  словарь операций (тот же, что у машины)

UNITS = ("splinter", "orchestrator-daemon", "wa-webhook")
DAEMON_LOG = os.path.join(REPO, "orchestrator_daemon.log")
STATE_FILE = os.path.join(REPO, "chain_series.json")
# Хвост после конца задачи, в который её отложенный рестарт (`systemd-run --on-active=10s`,
# правило самомодификации) ещё считается СВОИМ. Без хвоста плановый самрестарт демона выглядел
# бы ремонтом руками — то есть система штрафовала бы себя за собственное правило.
OWN_RESTART_GRACE = 180
_SHA = re.compile(r"\b([0-9a-f]{7,40})\b")
_MANUAL_CARD = re.compile(r"✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ|✋ одобрено, но шаг снова упирается")
_REJECTED = re.compile(r"отклонено Филиппом")
_EXPIRED = re.compile(r"причина=approval_timeout|подтверждение не получено")
_CARD_BODY = re.compile(r"op=\w+\s*\||NEEDS_APPROVAL")
_OWNER_MARK = re.compile(r"^\s*\[куратор владельцу цель \d+(?:, операция [^\]]*)?\]\s*")
_ENV_MARK = re.compile(r"^\s*\[конверт одобренной заявки \d+\][^\n]*\n?")


# ── факты мира (руки) ───────────────────────────────────────────────────────────────────────
def _run(args):
    """Вывод команды или None — «НЕ ПРОЧИТАНО». Пустая строка тут была бы слепой: она же значит
    честное «команда ничего не вывела», и промах стал бы неотличим от факта (класс «нуль по
    неразбору», `blind_readers` в гейте)."""
    try:
        p = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=120)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


def unit_starts(since):
    """({'family','at','unit'}-старты, [юниты, чей журнал не прочитан]). Журнал systemd
    авторитетен: это факт ядра, а не пересказ чьего-то отчёта. Непрочитанный журнал НАЗВАН —
    без него нельзя судить, был ли перезапуск ремонтом руками."""
    out, unread = [], []
    for u in UNITS:
        txt = _run(["journalctl", "-u", u, "--since", since, "--utc", "-o", "short-iso",
                    "--no-pager"])
        if txt is None:
            unread.append(u)
            continue
        for line in txt.splitlines():
            if ": Started " not in line:
                continue
            at = cs.stamp(line.split(" ", 1)[0])
            if at:
                out.append({"family": "service:" + u, "at": at, "unit": u})
    return sorted(out, key=lambda x: x["at"]), unread


def origin_commits():
    """{полный sha: метка коммита} по origin/main — или None, если git не прочитан. None ≠ «нет
    коммитов»: во втором случае вес доказуемо нулевой, в первом он просто НЕ НАБЛЮДАЕМ."""
    txt = _run(["git", "log", "origin/main", "--format=%H|%cI"])
    if txt is None:
        return None
    out = {}
    for line in txt.splitlines():
        sha, _, iso = line.partition("|")
        if len(sha) == 40:
            out[sha] = cs.stamp(iso)
    return out


def metrics_windows():
    """{id задачи: (начало, конец)} из строк METRICS боевого демона (mode=prod) — или None, если
    журнал не прочитан. Различение здесь решает: без окон ЛЮБОЙ перезапуск выглядел бы ремонтом
    руками, то есть слепота стала бы обвинением."""
    win = {}
    try:
        with open(DAEMON_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "METRICS task=" not in line or "mode=prod" not in line:
                    continue
                d = dict(p.split("=", 1) for p in line.split() if "=" in p)
                try:
                    win[int(d.get("task"))] = (cs.stamp(d.get("start")), cs.stamp(d.get("end")))
                except (TypeError, ValueError):
                    continue
    except OSError as e:
        print("ВНИМАНИЕ: журнал демона не прочитан (%s) — окна исполнения неизвестны, "
              "ремонт руками не считаю" % e)
        return None
    return win


def snapshot_live():
    import bridge_client
    bc = bridge_client.BridgeClient()
    rows = {}
    for st in ("new", "in_progress", "needs_approval", "approved", "done", "failed", "rejected"):
        r = bc.get_pending(st, lane="all")
        for it in (r.get("items") or []):
            if isinstance(it, dict):
                it.setdefault("status", st)
                rows[int(it.get("id"))] = it
    return [rows[k] for k in sorted(rows)]


# ── разбор одной записи ─────────────────────────────────────────────────────────────────────
def card_body(entry, kind, envelopes):
    """(тело карточки, которую видел владелец; откуда взято) — или ('', '') если тело затёрто.

    ТЕЛО НЕ УГАДЫВАЕТСЯ. Пустое тело НИКОГДА не выдаётся за «операции не названо»: сказать
    «карточка ложная» можно только увидев, чего в ней нет, а не не увидев ничего. Источники по
    убыванию надёжности: сводная карточка владельцу (тело живёт в task_text, вердиктом не
    затирается) → конверт, цитирующий пункт ДОСЛОВНО → уцелевший `result` карточки. Заглушка
    ревизора («сводная карточка находок ревизора» + вердикт вместо находок) телом НЕ считается."""
    text, res = str(entry.get("task_text") or ""), str(entry.get("result") or "")
    if kind == "owner_card":
        body = _OWNER_MARK.sub("", text).strip()
        return (body, "карточка владельцу") if body else ("", "")
    env = envelopes.get(int(entry.get("id")))
    if env:
        body = _ENV_MARK.sub("", str(env.get("task_text") or "")).strip()
        if body:
            return body, "конверт %s" % env.get("id")
    if _CARD_BODY.search(res):
        return res, "уцелевший result"
    if kind == "revizor_card" and len(res) > 200 and not _REJECTED.search(res):
        return res, "находки ревизора"
    return "", ""


def ops_of(body):
    return [o["key"] for o in curator_ops.operations(body or "")]


def build(entries, starts, commits, windows):
    """Записи очереди + факты мира → упорядоченные вердикты цепочек."""
    roots = cs.resolve_roots([{"id": e.get("id"), "text": e.get("task_text")} for e in entries])
    by_id = {int(e["id"]): e for e in entries}
    envelopes = {}
    for e in entries:
        kind, par = cs.parent_of(e.get("task_text"))
        if kind == "envelope" and par is not None:
            envelopes[par] = e

    chains, order = {}, []
    for e in entries:
        i = int(e["id"])
        root, kind = roots.get(i, (i, "root"))
        ch = chains.get(root)
        if ch is None:
            r = by_id.get(root, e)
            ch = chains[root] = {"root": root, "lane": r.get("lane"),
                                 "created": cs.stamp(r.get("created")), "closed_at": "",
                                 "cards": [], "refusals": [], "ids": [], "statuses": [],
                                 # ВЕС ПОЛОСЫ pc ОТСЮДА НЕ НАБЛЮДАЕМ: её задачи коммитят в
                                 # ПК-репозиторий, которого на этой машине нет. Это «неизвестно»,
                                 # а не «нуля веса» — иначе слепота стала бы обвинением. Та же
                                 # причина закрывает вес ЦЕЛИКОМ, если git не прочитан.
                                 "weight": {"commits": [], "restarts": 0,
                                            "known": (commits is not None
                                                      and str(r.get("lane") or "vps") != "pc")}}
            order.append(root)
        ch["ids"].append(i)
        ch["statuses"].append(e.get("status"))
        ch["closed_at"] = max(ch["closed_at"], cs.stamp(e.get("updated")))

        status, res = str(e.get("status") or ""), str(e.get("result") or "")
        opened, closed = cs.stamp(e.get("created")), cs.stamp(e.get("updated"))

        # --- вмешательство: карточка дошла до владельца? ---
        answered = bool(str(e.get("approved_by") or "").strip()) or bool(_REJECTED.search(res))
        reached = answered or kind in ("owner_card", "revizor_card") or bool(_EXPIRED.search(res))
        if _MANUAL_CARD.search(res):
            v = cs.sort_manual_card(ops_of(res))
            ch["cards"].append({"id": i, "sort": v["sort"], "why": v["why"], "at": closed})
        elif reached:
            body, src = card_body(e, kind, envelopes)
            if body:
                v = cs.sort_card(ops_of(body), starts, opened, closed)
                v["why"] += " [тело: %s]" % src
            else:
                v = {"sort": cs.UNKNOWN, "why": "тело карточки затёрто вердиктом очереди — "
                                                "операция из снимка не восстановима"}
            ch["cards"].append({"id": i, "sort": v["sort"], "why": v["why"], "at": closed})

        # --- необъяснённый отказ ---
        why = cs.refusal(status, res)
        if why:
            ch["refusals"].append({"id": i, "reason": why, "at": closed})

        # --- вес: коммит, доехавший в origin/main внутри окна цепочки ---
        for tok in (set(_SHA.findall(res.lower())) if commits else set()):
            for sha, at in commits.items():
                if sha.startswith(tok) and opened <= at <= (closed or "9999"):
                    if sha[:7] not in ch["weight"]["commits"]:
                        ch["weight"]["commits"].append(sha[:7])
                    break

    # --- старты юнитов: свой (внутри ОКНА ИСПОЛНЕНИЯ задачи) или ремонт руками ---
    # ОКНО БЕРЁТСЯ ИЗ METRICS, А НЕ ИЗ ОЧЕРЕДИ, и это не мелочь: `created` очереди — момент
    # ПОСТАНОВКИ, задача может простоять в new часами, и по такому окну «своей» оказывалась бы
    # любая перезагрузка мира (в первом прогоне так и вышло — ремонтов руками нашлось 0 из 46).
    # Полоса pc сюда не входит вовсе: юниты VPS перезапускает VPS, приписывать их ПК-задаче
    # значит выдумать исполнителя.
    spans = []
    for e in entries:
        i = int(e["id"])
        w = (windows or {}).get(i)
        if w and w[0] and w[1]:
            spans.append((w[0], _plus(w[1], OWN_RESTART_GRACE), roots.get(i, (i, ""))[0], i))
    reboots = _reboots(starts)
    stats = {"own": 0, "reboot": 0, "manual": 0, "unattributable": 0}
    for st in (starts if windows is not None else []):     # окон нет → не обвиняем вовсе
        if st["at"] in reboots:
            stats["reboot"] += 1              # мир перезагрузился целиком — это не ремонт
            continue
        owner = next((r for lo, hi, r, _ in spans if lo <= st["at"] <= hi), None)
        if owner is not None and owner in chains:
            chains[owner]["weight"]["restarts"] += 1
            stats["own"] += 1
            continue
        host = _chain_at(chains, order, st["at"])
        stats["manual"] += 1
        if host is not None:
            chains[host]["cards"].append(
                {"id": None, "sort": cs.MANUAL, "at": st["at"],
                 "why": "перезапуск %s в %s не попадает ни в одно окно исполнения — сделано "
                        "руками" % (st["unit"], st["at"])})
    return [cs.chain_verdict(chains[r]) for r in order], chains, order, stats


def _reboots(starts, window=90):
    """Метки стартов, попавших в перезагрузку МАШИНЫ: два и более РАЗНЫХ юнита поднялись в окне
    в полторы минуты. Перезагрузка — не ремонт за систему и не её работа; считаем отдельно."""
    out = set()
    for i, a in enumerate(starts):
        near = {a["unit"]}
        for b in starts:
            if abs(_secs(b["at"]) - _secs(a["at"])) <= window:
                near.add(b["unit"])
        if len(near) >= 2:
            out.add(a["at"])
    return out


def _secs(ts):
    """Метка → секунды абсолютной шкалы (день × 86400 + время). Только для расстояний."""
    try:
        y, m, d = int(ts[:4]), int(ts[5:7]), int(ts[8:10])
        h, mi, s = int(ts[11:13]), int(ts[14:16]), int(ts[17:19])
        return ((y * 12 + m) * 31 + d) * 86400 + h * 3600 + mi * 60 + s
    except (ValueError, IndexError):
        return 0


def _plus(ts, sec):
    """Метка + секунды, без импорта времени в чистом модуле: считаем в его же строковом виде."""
    try:
        h, m, s = (int(x) for x in ts[11:].split(":"))
    except (ValueError, IndexError):
        return ts
    t = h * 3600 + m * 60 + s + int(sec)
    if t >= 86400:                       # переход через полночь — граница суток, не двигаем дату
        return ts[:11] + "23:59:59"
    return "%s%02d:%02d:%02d" % (ts[:11], t // 3600, (t % 3600) // 60, t % 60)


def _chain_at(chains, order, at):
    """Кому приписан ремонт руками: цепочке ПОЛОСЫ VPS, открытой в этот момент; открытой нет —
    той, что началась последней до него (ремонт случился в её след). Полоса важна: перезапускают
    юниты VPS, и вешать это на ПК-цепочку значило бы назвать чужого виновника. Выбор назван
    прямо: ремонт руками — событие мира, своего номера в очереди у него нет, приписка условна."""
    own = [r for r in order if str(chains[r].get("lane") or "vps") != "pc"
           and chains[r]["created"] and chains[r]["created"] <= at]
    live = [r for r in own if (chains[r]["closed_at"] or "9999") >= at]
    if live:
        return live[-1]
    return own[-1] if own else None


# ── печать ──────────────────────────────────────────────────────────────────────────────────
def weeks_table(verdicts):
    """Доля шума на цепочку по неделям (понедельные корзины по дате корня)."""
    buckets = {}
    for v in verdicts:
        d = str(v.get("created") or "")[:10]
        if not d or not v.get("closed", True):
            continue
        b = buckets.setdefault(_week(d), {"chains": 0, "noise": 0, "manual": 0, "will": 0,
                                          "unknown": 0, "refusal": 0, "weight": 0})
        b["chains"] += 1
        if v.get("weight_known", True):
            b["wknown"] = b.get("wknown", 0) + 1
            b["weight"] += 1 if v.get("weight") else 0
        c = v.get("counts") or {}
        b["noise"] += c.get(cs.NOISE, 0)
        b["manual"] += c.get(cs.MANUAL, 0)
        b["will"] += c.get(cs.WILL, 0)
        b["unknown"] += c.get(cs.UNKNOWN, 0)
        if v.get("cause") == "отказ":
            b["refusal"] += 1
    return buckets


def _week(day):
    """Начало недели (понедельник) для 'YYYY-MM-DD'. Григорианский счёт дней — без импортов."""
    y, m, d = int(day[:4]), int(day[5:7]), int(day[8:10])
    yy = y - (1 if m <= 2 else 0)
    era = yy // 400
    yoe = yy - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468           # дней от 1970-01-01 (четверг)
    mon = days - ((days + 3) % 7)
    return _from_days(mon)


def _from_days(days):
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return "%04d-%02d-%02d" % (y + (1 if m <= 2 else 0), m, d)


# ── СВЕРКА: реплей против файла демона ──────────────────────────────────────────────────────
# ЗАЧЕМ ОНА ВООБЩЕ. Живой счёт демона — единственный источник числа, а число без сверки есть
# ощущение с точностью до знака. Сверка отвечает на один вопрос: не противоречит ли файл тому,
# что о тех же цепочках всё ещё говорит очередь. Она НИЧЕГО НЕ ЧИНИТ — расхождение обязано быть
# КРАСНЫМ, а не тихой правкой файла: молча подогнанный счётчик перестаёт быть свидетелем, и
# следующий раз соврёт уже без свидетелей вовсе (тот же довод, по которому гейт не правит тест).
#
# ИСХОДОВ ТРИ, А НЕ ДВА (замок против ложного зелёного — приём О3/О4/О5):
#   0 СХОДИТСЯ      — на общей почве ни одного противоречия, и почва не пуста;
#   1 РАСХОЖДЕНИЕ   — противоречие названо поимённо: цепочка, что говорит файл, что реплей;
#   2 НЕ СВЕРЕНО    — сверять нечем или не с чем (файла нет · файл пуст · факты мира не
#                     прочитаны · общая почва пуста). Это НЕ «сходится»: пустое пересечение
#                     сходимостью объявить нельзя, иначе чистая установка выдавала бы зелёное
#                     ровно там, где не проверено ничего.
#
# АСИММЕТРИЯ СЛЕПОТЫ НАЗВАНА ПРЯМО И СЧИТАЕТСЯ ОТДЕЛЬНО. Реплей структурно слеп там, где очередь
# затёрла тело карточки её же вердиктом (замер 10.08: тело восстановимо у 46 вмешательств из 106).
# Поэтому «файл говорит ОБРЫВ, реплей молчит, и тело у реплея затёрто» — не противоречие, а ровно
# та причина, по которой файл и заведён; такие цепочки считаются числом. А вот обратное — «реплей
# доказывает обрыв, файл его не знает» — КРАСНОЕ ВСЕГДА: это направление, в котором счёт надувает
# серию, и слепотой оно не оправдывается ничем.
def _file_verdicts(live):
    """Вердикты цепочек ИЗ ФАЙЛА — теми же чистыми функциями, какими их считает демон
    (`_series_derive`): статусы записей → список, открытые карточки в вердикт не входят."""
    out = {}
    for r, ch in ((live or {}).get("chains") or {}).items():
        c = dict(ch)
        c["statuses"] = list((ch.get("statuses") or {}).values())
        c["cards"] = [x for x in (ch.get("cards") or []) if not x.get("open")]
        try:
            out[int(r)] = cs.chain_verdict(c)
        except (TypeError, ValueError):
            continue
    return out


def _cause_ids(chain, cause):
    """Номера ЗАПИСЕЙ, на которых стоит обрыв этой цепочки. `chain_verdict` называет причину, а
    сверке нужно знать, ЧЕМ она доказана: сверять две картины можно только по одной и той же
    записи очереди."""
    cards = [c for c in (chain.get("cards") or []) if not c.get("open")]
    if cause in (cs.NOISE, cs.MANUAL):
        return [c.get("id") for c in cards if c.get("sort") == cause]
    if cause == "отказ":
        return [r.get("id") for r in (chain.get("refusals") or [])]
    return []


def _replay_saw(chain, ids):
    """Разобрал ли РЕПЛЕЙ хоть одну из этих записей как вмешательство. `неизвестно` разбором не
    считается: это и есть его слепота (тело затёрто вердиктом очереди)."""
    for i in ids:
        if i is None:
            continue
        if any(c.get("id") == i and c.get("sort") != cs.UNKNOWN
               for c in (chain.get("cards") or [])):
            return True
        if any(r.get("id") == i for r in (chain.get("refusals") or [])):
            return True
    return False


def _attributed(chain, verdict):
    """Стоит ли обрыв на ПРИПИСАННОМ ремонте — перезапуске юнита, у которого своего номера в
    очереди нет вовсе. Приписка условна у ОБЕИХ сторон, и обе говорят это прямо в коде: демон
    вешает такой старт на последнюю свою цепочку, реплей — на цепочку, живую в ту минуту. Значит
    хозяин у него может разойтись законно, и по цепочке он не сверяется — сверяется его ЧИСЛО."""
    if not verdict.get("break") or verdict.get("cause") != cs.MANUAL:
        return False
    ids = _cause_ids(chain, cs.MANUAL)
    return bool(ids) and all(i is None for i in ids)


def verify(live, replay_chains, unread=(), windows_read=True):
    """(код возврата, строки отчёта). Ничего не пишет и не правит — только судит."""
    # `blocking` — то, из-за чего сверка НЕВОЗМОЖНА (код 2); `notes` — оговорки, которые её не
    # отменяют. Разделять обязательно: файл всегда знает цепочки, закрывшиеся ПОСЛЕ снимка, и
    # считать это «не сверено» значило бы никогда не сверить ничего — то есть выключить сверку
    # молчанием. Она проверяет проверяемое и ПРЯМО НАЗЫВАЕТ, чего не касалась.
    out, red, blocking, notes = [], [], [], []
    if not live:
        return 2, ["СВЕРКА: НЕ СВЕРЕНО — файла демона нет или он не прочитан "
                   "(живой счёт ещё не писал состояния)"]
    fv = _file_verdicts(live)
    if not fv:
        return 2, ["СВЕРКА: НЕ СВЕРЕНО — в файле ноль цепочек: счёт установлен, но ещё не считал. "
                   "Сходимостью пустое пересечение не объявляем"]
    if unread:
        blocking.append("журнал юнитов не прочитан (%s) — реплей не судит ремонт руками"
                        % ", ".join(unread))
    if not windows_read:
        blocking.append("окна исполнения не прочитаны — реплей не отличит свой рестарт от ремонта")

    rch = {int(r): ch for r, ch in (replay_chains or {}).items()}   # ключи бывают и строками
    rv = {r: cs.chain_verdict(ch) for r, ch in rch.items()}
    rmax = max(rv) if rv else 0
    # ЦЕПОЧКА ФАЙЛА, КОТОРОЙ В СНИМКЕ НЕТ. Внутри охвата снимка это красное (файл говорит о том,
    # чего очередь не знает); новее снимка — просто «снимок старше файла», и обвинять тут нечего.
    for r in sorted(set(fv) - set(rv)):
        if r <= rmax:
            red.append("цепочка %s: файл её знает, а в снимке очереди её НЕТ" % r)
        else:
            notes.append("цепочка %s новее снимка — в сверку не входит" % r)
    outside = sorted(set(rv) - set(fv))

    fch = {int(r): ch for r, ch in ((live or {}).get("chains") or {}).items()}
    # ФОРМА ЗАПИСИ — ЧЕЙ ЭТО СЛЕД. Сверка по исходу ловит спор о мире, но не ловит подделку,
    # СЛУЧАЙНО совпавшую с миром: 10.08.2026 боевой файл держал синтетическую цепочку 101 от
    # пробы, и по исходу («done, обрывов нет») она сошлась с настоящей цепочкой 101 из очереди —
    # сверка вернула зелёное на состоянии, которого демон не писал НИ ОДНОЙ строкой. Дату рождения
    # цепочке даёт запись очереди (`created` задачи), и у настоящего счёта она есть всегда:
    # пустая — след писавшего БЕЗ задачи в руках, то есть правка файла не демоном.
    for r in sorted(fv):
        if not str((fch.get(r) or {}).get("created") or "").strip():
            red.append("цепочка %s в файле БЕЗ ДАТЫ РОЖДЕНИЯ — живой счёт так не пишет: "
                       "состояние правлено не демоном" % r)
    common, blind, uncomparable, attributed = [], [], [], []
    for r in sorted(set(fv) & set(rv)):
        f, p = fv[r], rv[r]
        if not (f.get("closed") and p.get("closed")):
            uncomparable.append(r)          # исход есть не в обеих картинах — сравнивать нечего
            continue
        common.append(r)
        if f.get("break") == p.get("break") and f.get("cause") == p.get("cause"):
            continue
        if _attributed(fch[r], f) or _attributed(rch[r], p):
            attributed.append(r)            # хозяин приписанного ремонта расходится законно
            continue
        if f.get("break") and not p.get("break") \
                and not _replay_saw(rch[r], _cause_ids(fch[r], f.get("cause"))):
            blind.append(r)                 # ровно та слепота, ради которой файл и заведён
            continue
        red.append("цепочка %s: файл — %s, реплей — %s%s"
                   % (r, ("обрыв «%s»" % f.get("cause")) if f.get("break") else "без обрыва",
                      ("обрыв «%s»" % p.get("cause")) if p.get("break") else "без обрыва",
                      " (запись %s реплей разобрал сам — оба видели одно и то же)"
                      % _cause_ids(fch[r], f.get("cause"))
                      if f.get("break") and not p.get("break") else ""))
    if attributed:
        fman = sum(1 for r in common if fv[r].get("cause") == cs.MANUAL)
        pman = sum(1 for r in common if rv[r].get("cause") == cs.MANUAL)
        notes.append("ремонт руками на общей почве: файл %d · реплей %d (приписка условна у обеих "
                     "сторон — сверяется число, не хозяин; расходятся цепочки %s)"
                     % (fman, pman, attributed[:8]))

    # (а) ФАЙЛ САМ СЕБЕ: выводится ли его `derived` из его же цепочек. Ловит правку файла руками
    # и расхождение самого счёта с решением — то есть ту самую «тихую правку», которая запрещена.
    d = live.get("derived") or {}
    own = cs.series([fv[r] for r in sorted(fv)])
    if d.get("current") is not None and (d.get("current") != own["current"]
                                         or d.get("best") != own["best"]
                                         or d.get("chains") != own["chains"]):
        red.append("файл сам себе противоречит: заявлено current=%s best=%s цепочек=%s, а из его "
                   "же цепочек выводится current=%s best=%s цепочек=%s"
                   % (d.get("current"), d.get("best"), d.get("chains"),
                      own["current"], own["best"], own["chains"]))
    out.append("СВЕРКА: цепочек в файле %d · в снимке %d · общая почва %d "
               "(вне окна файла %d · не сравнимы %d · слепота реплея %d · приписка ремонта %d)"
               % (len(fv), len(rv), len(common), len(outside), len(uncomparable), len(blind),
                  len(attributed)))
    out.append("  файл: %s" % (d.get("line") or "строки нет"))
    out.append("  рекорд файла best_ever=%s (реплеем не проверяется — файл помнит дольше своего "
               "окна) · последний обрыв: %s"
               % (d.get("best_ever"), _last_break_line(d.get("last_break"))))

    # (б) ЧИСЛА НА ОБЩЕЙ ПОЧВЕ — обе стороны считаются ОДНОЙ чистой функцией по ОДНОМУ набору
    # корней. Красное только при нулевой слепоте: где реплей ослеп, числа обязаны разойтись, и
    # объявлять это расхождением значило бы наказывать файл за то, ради чего он существует.
    if common:
        fs = cs.series([fv[r] for r in common])
        ps = cs.series([rv[r] for r in common])
        out.append("  на общей почве: файл current=%d best=%d обрывов=%d | реплей current=%d "
                   "best=%d обрывов=%d"
                   % (fs["current"], fs["best"], len(fs["breaks"]),
                      ps["current"], ps["best"], len(ps["breaks"])))
        if not blind and not attributed \
                and (fs["current"] != ps["current"] or fs["best"] != ps["best"]):
            red.append("числа на общей почве разошлись при нулевой слепоте реплея: "
                       "файл current=%d best=%d, реплей current=%d best=%d"
                       % (fs["current"], fs["best"], ps["current"], ps["best"]))
    else:
        blocking.append("общая почва пуста — сверять нечего")

    for line in notes:
        out.append("  ОГОВОРКА: " + line)
    for line in blocking:
        out.append("  НЕ СВЕРЕНО: " + line)
    for line in red:
        out.append("  РАСХОЖДЕНИЕ: " + line)
    if red:
        out.append("ИТОГ СВЕРКИ: РАСХОЖДЕНИЕ (%d) — красное. Файл НЕ правим: расходится счёт с "
                   "миром, а не файл с ожиданием" % len(red))
        return 1, out
    if blocking:
        out.append("ИТОГ СВЕРКИ: НЕ СВЕРЕНО — о сходимости не заявляем")
        return 2, out
    out.append("ИТОГ СВЕРКИ: СХОДИТСЯ на %d цепочках (слепота реплея %d — не расхождение)"
               % (len(common), len(blind)))
    return 0, out


def _last_break_line(b):
    """Дата последнего обрыва и его сорт — то, что файл обязан отвечать по рамке §8г."""
    if not b:
        return "не было ни одного"
    return "%s · %s · цепочка %s" % (str(b.get("at") or "без даты")[:16], b.get("cause"),
                                     b.get("root"))


def main(argv):
    snap = None
    if "--snapshot" in argv:
        snap = json.load(open(argv[argv.index("--snapshot") + 1], encoding="utf-8"))
    entries = snap if snap is not None else snapshot_live()
    entries = [e for e in entries if str(e.get("id") or "").strip()]
    entries.sort(key=lambda e: int(e["id"]))
    since = (entries[0].get("created") or "")[:10] if entries else "2026-07-01"
    starts, unread = unit_starts(since)
    commits, windows = origin_commits(), metrics_windows()
    verdicts, chains, order, rst = build(entries, starts, commits, windows)
    st = cs.series(verdicts)
    if unread:
        print("ВНИМАНИЕ: журнал не прочитан у юнитов %s — их перезапуски в счёт не вошли ВОВСЕ"
              % ", ".join(unread))
    if commits is None:
        print("ВНИМАНИЕ: origin/main не прочитан — вес НЕ НАБЛЮДАЕМ ни у одной цепочки")

    print("ЗАПИСЕЙ ОЧЕРЕДИ: %d   ЦЕПОЧЕК: %d   окно: %s → %s"
          % (len(entries), st["chains"], entries[0].get("created", "")[:16],
             entries[-1].get("updated", "")[:16]))
    print("СТАРТОВ ЮНИТОВ в окне: %d (своих %d · перезагрузка машины %d · РУКАМИ %d)   "
          "КОММИТОВ origin/main: %s   окон METRICS: %s"
          % (len(starts), rst["own"], rst["reboot"], rst["manual"],
             "не прочитан" if commits is None else len(commits),
             "НЕ ПРОЧИТАНЫ" if windows is None else len(windows)))
    print(cs.render(st))
    print("\nСЕРИЯ ИДЁТ: %d цепочек %s   ВЕС В НЕЙ: %d из %d наблюдаемых (%.1f%%)   "
          "ЗАЧЁТНАЯ: %s (порог %d/%.0f%%)"
          % (st["current"], st["current_span"][:12], st["current_weight"], st["current_known"],
             100 * st["current_weight_share"], "да" if st["qualified"] else "НЕТ",
             cs.SERIES_TARGET, 100 * cs.WEIGHT_MIN_SHARE))
    print("ЛУЧШАЯ СЕРИЯ: %d %s" % (st["best"], st["best_span"][:12]))

    print("\nОБРЫВЫ (%d) — по сортам:" % len(st["breaks"]))
    for name in (cs.NOISE, cs.MANUAL, "отказ"):
        sel = [b for b in st["breaks"] if b["cause"] == name]
        print("  %-10s %d" % (name, len(sel)))
        for b in sel:
            print("     цепочка %-4s %s %-4s рвала серию длиной %-2d — %s"
                  % (b["root"], (b["at"] or "")[:16], b["lane"], b["broke_len"], b["why"][:96]))

    tot = {s: 0 for s in cs.SORTS}
    for v in verdicts:
        for s in cs.SORTS:
            tot[s] += (v.get("counts") or {}).get(s, 0)
    print("\nВМЕШАТЕЛЬСТВА ВСЕГО: " + " · ".join("%s %d" % (s, tot[s]) for s in cs.SORTS))
    sub = {}
    for r in order:
        for c in chains[r]["cards"]:
            key = (c["sort"], "тело затёрто" if "затёрто" in c["why"] else
                   ("решение без операции" if "просит решение" in c["why"] else
                    ("операция опоздала" if "ДО ответа" in c["why"] else
                     ("не наблюдается" if "не наблюдается" in c["why"] else "прочее"))))
            sub[key] = sub.get(key, 0) + 1
    print("РАЗБОРКА ПО ПРИЧИНЕ: " + " · ".join("%s/%s %d" % (k[0], k[1], v)
                                               for k, v in sorted(sub.items())))
    print("ЦЕПОЧЕК С ВЕСОМ: %d из %d НАБЛЮДАЕМЫХ = %.1f%%   (закрытых всего %d, вес не "
          "наблюдаем у %d — полоса pc коммитит в чужой репозиторий; открытых вне счёта %d)"
          % (st["weight_chains"], st["weight_known"], 100 * st["weight_share"], st["chains"],
             st["chains"] - st["weight_known"], st["open"]))
    w = cs.weight_windows(verdicts)
    if w:
        def q(p):
            return w[min(len(w) - 1, int(p * (len(w) - 1)))]
        print("ВЕС В СКОЛЬЗЯЩЕМ ОКНЕ %d НАБЛЮДАЕМЫХ ЦЕПОЧЕК (%d окон): min %.1f%% · p10 %.1f%% · "
              "медиана %.1f%% · p90 %.1f%% · max %.1f%%  — окон ниже порога %.0f%%: %d"
              % (cs.SERIES_TARGET, len(w), 100 * w[0], 100 * q(0.10), 100 * q(0.50),
                 100 * q(0.90), 100 * w[-1], 100 * cs.WEIGHT_MIN_SHARE,
                 sum(1 for x in w if x < cs.WEIGHT_MIN_SHARE)))

    print("\nПО НЕДЕЛЯМ (доля шума на цепочку; «шум/разобр.» — среди карточек, чьё тело уцелело):")
    print("  %-12s %6s %6s %8s %7s %6s %7s %10s %6s"
          % ("неделя с", "цепей", "шум", "шум/цеп", "ремонт", "воля", "неизв.", "шум/разобр.",
             "вес%"))
    wt = weeks_table(verdicts)
    for wk in sorted(wt):
        b = wt[wk]
        known = b["noise"] + b["manual"] + b["will"]
        print("  %-12s %6d %6d %8.3f %7d %6d %7d %10s %5.0f%%"
              % (wk, b["chains"], b["noise"], b["noise"] / b["chains"] if b["chains"] else 0,
                 b["manual"], b["will"], b["unknown"],
                 ("%.2f" % (b["noise"] / known)) if known else "—",
                 100.0 * b["weight"] / b.get("wknown", 0) if b.get("wknown") else 0))

    if "--verify" in argv:
        path = argv[argv.index("--state") + 1] if "--state" in argv else STATE_FILE
        live = None
        try:
            with open(path, encoding="utf-8") as f:
                live = json.load(f)
        except (OSError, ValueError) as e:
            # Код 2 — «НЕ СВЕРЕНО», а не 0: успех и невозможность сверки обязаны различаться
            # кодом возврата (тот же приём, что у deploy/bridge_prod_diff.py).
            print("\nСВЕРКА: файл демона не прочитан (%s)" % e)
        code, lines = verify(live, chains, unread, windows is not None)
        print("")
        for line in lines:
            print(line)
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
