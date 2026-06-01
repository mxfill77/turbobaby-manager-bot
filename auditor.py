"""
Auditor — надзорный модуль за Splinter.
Логически независим: проверяет работу бота, опираясь на ФАКТЫ
(Bot Data, Лист1 Байки, memory.db), а не на мнение самой модели.

Три слоя:
1) Детерминированные проверки (факт vs факт) — ловят галлюцинации и нарушения правил.
2) Сверка требование→результат (формулы там где есть: ТО, депозит).
3) LLM-аудитор — только на сложное, в суточном отчёте.

При находке: пишет в журнал `аудит` (Bridge) verdict/severity/suggested_fix
и раз в день шлёт Филиппу сводку в HQ. Сам ничего не правит — только флаги и
предложения. Правки применяются после апрува Филиппа.
"""

import json
import logging
import re

log = logging.getLogger("auditor")


# Диапазоны символов для детекции смешения языков
_CYR = re.compile(r"[А-Яа-яЁё]")
_THAI = re.compile(r"[\u0E00-\u0E7F]")
_LAT = re.compile(r"[A-Za-z]")


def _strip_allowed(s: str) -> str:
    """Убирает то, что допустимо в любом языковом блоке: числа, латинские
    названия моделей/номеров (NMAX, XMAX 4957), валюты, ссылки, пунктуацию."""
    s = re.sub(r"https?://\S+", " ", s)            # ссылки
    s = re.sub(r"[A-Z]{2,}[A-Z0-9\-]*", " ", s)     # NMAX, XMAX, ADV, CB, PHUKET
    s = re.sub(r"\d[\d\s,\.]*", " ", s)             # числа, км, суммы
    s = re.sub(r"[@#][\w]+", " ", s)                # @ники
    s = re.sub(r"[🇹🇭🇷🇺]", " ", s)                  # флаги-маркеры
    return s


def oil_interval_for(bike_name: str) -> int:
    """Дубль правила интервала (чтобы аудитор считал НЕЗАВИСИМО от claude_client)."""
    n = str(bike_name).lower().replace("-", "").replace(" ", "")
    if "xadv" in n:
        return 5000
    if "nmax" in n or "xmax" in n or "adv" in n or "forza" in n or "pcx" in n or "click" in n:
        return 4000
    return 5000


class Auditor:
    """Надзор за действиями Splinter. Использует bridge (факты), memory (правила/память)."""

    def __init__(self, bridge, memory=None, claude=None):
        self.bridge = bridge
        self.memory = memory
        self.claude = claude  # для LLM-слоя (опц.)

    # ── Слой 1+2: проверка ОДНОГО действия сразу после выполнения ──
    def check_action(self, *, tool: str, args: dict, claimed: str,
                     user_request: str = "", group: str = "", topic_id=None) -> dict:
        """Детерминированная проверка одного действия бота.
        Возвращает вердикт. Если найдено расхождение — логирует в журнал аудита.
        verdict: 'ok' | 'hallucination' | 'rule_violation' | 'logic_error' | 'suspect'
        """
        verdict, severity, detail, fix = "ok", "", "", ""
        args = args or {}

        try:
            # 1) Галлюцинация: сказал что записал правило — а в памяти нет
            if tool == "remember_rule":
                rule = (args.get("rule") or "").strip()
                if rule and self.memory:
                    rules = [r.get("rule", "") for r in self.memory.active_rules()]
                    if not any(rule[:40].lower() in (x or "").lower() for x in rules):
                        verdict, severity = "hallucination", "high"
                        detail = f"Заявил что запомнил правило, но в memory.db его нет: «{rule[:80]}»"
                        fix = "Перепроверить запись в память; повторить remember_rule."

            # 2) flag_important: запись в лист идёт ОТЛОЖЕННО (bot.py после ответа),
            #    поэтому проверять лист сразу нельзя — будет ложная тревога.
            #    Проверяем только что мозг передал непустой pin_text/summary.
            elif tool == "flag_important":
                if not (args.get("summary") or args.get("pin_text")):
                    verdict, severity = "suspect", "low"
                    detail = "flag_important вызван без summary/pin_text"
                    fix = "Передавать суть и текст закрепа."

            # 3) ТО: пересчёт по формуле (Лист1 кол.I + интервал по типу)
            elif tool == "set_service" and args.get("current_km"):
                bike = args.get("bike", "")
                fb = self.bridge.find_bike(bike) if bike else {}
                if fb:
                    oil_last = fb.get("oil_last_km")
                    interval = oil_interval_for(fb.get("name", bike))
                    cur = int(str(args.get("current_km")).replace(" ", "").replace(",", ""))
                    if oil_last:
                        next_km = oil_last + interval
                        left = next_km - cur
                        # Если в заявленном результате есть число просрочки — сверим
                        claimed_l = (claimed or "").lower()
                        # ищем расхождение интервала: упоминание 6000 — старая ошибка
                        if "6000" in claimed_l or "6 000" in claimed_l:
                            verdict, severity = "logic_error", "high"
                            detail = (f"{fb.get('name')}: в ответе фигурирует интервал 6000, "
                                      f"по правилу должно быть {interval}. Следующее ТО={next_km}, "
                                      f"осталось {left}.")
                            fix = f"Интервал для этого байка = {interval} км (правило по типу)."

            # 4) Пробег с фото записан без подтверждения (нарушение правила confirmed)
            #    Это детектится по claimed: если есть «записал пробег» но не было «подтвержд»
            elif tool == "set_service" and args.get("current_km") and not args.get("confirmed"):
                # мягкий флаг — пробег мог прийти не с фото; помечаем как suspect
                verdict = verdict if verdict != "ok" else "suspect"
                if verdict == "suspect" and not detail:
                    severity = "low"
                    detail = "Записан current_km без confirmed — если это число с ФОТО, нужно было подтверждение."
                    fix = "Для пробега с фото вызывать set_service только после подтверждения человеком."

        except Exception as e:
            log.warning(f"auditor.check_action error: {e}")

        # Лог в журнал (всё, не только ошибки — для статистики; вердикт ok тоже)
        try:
            self.bridge.audit_log(
                group=group, topic_id=topic_id or "",
                user_request=user_request, tool=tool,
                tool_args=json.dumps(args, ensure_ascii=False),
                claimed_result=claimed, verdict=verdict,
                severity=severity, detail=detail, suggested_fix=fix,
                status="new" if verdict != "ok" else "ok",
            )
        except Exception as e:
            log.warning(f"auditor.audit_log error: {e}")

        return {"verdict": verdict, "severity": severity, "detail": detail, "fix": fix}

    # ── Проверка КАЧЕСТВА ОТВЕТА: стиль, перевод, смешение языков ──
    def check_response_text(self, *, answer: str, bilingual: bool,
                            user_request: str = "", group: str = "", topic_id=None) -> dict:
        """Детерминированно проверяет текст ответа бота:
        - смешение языков (кириллица в тайском блоке и наоборот)
        - структура двуязычного ответа (есть оба блока, не пустые)
        - эмодзи вместо слов (запрещено правилом KB)
        Логирует находки в журнал аудита. LLM не используется (дёшево, точно)."""
        verdict, severity, detail, fix = "ok", "", "", ""
        problems = []
        a = answer or ""

        try:
            if bilingual:
                # Разбиваем по строкам-флагам на тайские и русские блоки
                thai_lines, ru_lines = [], []
                for line in a.split("\n"):
                    if "🇹🇭" in line:
                        thai_lines.append(line)
                    elif "🇷🇺" in line:
                        ru_lines.append(line)
                # Если флагов нет вообще — структура нарушена
                if not thai_lines and not ru_lines:
                    # возможно мозг разнёс блоки без флагов в строках — мягкий флаг
                    if _THAI.search(a) and _CYR.search(a):
                        pass  # оба языка есть, просто без флагов — не критично
                    else:
                        problems.append("двуязычный ответ без тайского/русского блока")
                else:
                    # Тайский блок не должен содержать кириллицу
                    for ln in thai_lines:
                        cleaned = _strip_allowed(ln.replace("🇹🇭", ""))
                        if _CYR.search(cleaned):
                            problems.append(f"кириллица в тайском блоке: «{ln.strip()[:60]}»")
                            break
                    # Проверка: есть ли вообще тайские символы в тайских строках
                    thai_text = _strip_allowed(" ".join(thai_lines))
                    if thai_lines and not _THAI.search(" ".join(thai_lines)) and _CYR.search(thai_text):
                        problems.append("в тайском блоке нет тайского текста (вместо перевода — кириллица)")
                    # Один из блоков пустой
                    if thai_lines and not ru_lines:
                        problems.append("есть тайский блок, но нет русского")
                    if ru_lines and not thai_lines:
                        problems.append("есть русский блок, но нет тайского")

            # Эмодзи вместо слов (правило KB: паспорт/доллар — словами)
            # ловим явные подмены: 🛂 (паспорт), 💵/💲/💰 (деньги) в тексте
            for emo, word in [("🛂", "паспорт"), ("💵", "деньги/доллар"),
                              ("💲", "доллар"), ("🛵", "скутер"), ("🏍", "мотоцикл")]:
                if emo in a:
                    problems.append(f"эмодзи {emo} вместо слова «{word}»")
                    break

            if problems:
                verdict = "style_issue"
                severity = "low"
                detail = "; ".join(problems[:3])
                fix = ("Тайский блок — только тайский (без кириллицы), оба блока заполнены, "
                       "паспорт/деньги — словами, не эмодзи.")
        except Exception as e:
            log.warning(f"check_response_text error: {e}")

        if verdict != "ok":
            try:
                self.bridge.audit_log(
                    group=group, topic_id=topic_id or "",
                    user_request=user_request, tool="response_text",
                    tool_args="", claimed_result=a[:500],
                    verdict=verdict, severity=severity, detail=detail,
                    suggested_fix=fix, status="new",
                )
            except Exception as e:
                log.warning(f"audit_log(style) error: {e}")

        return {"verdict": verdict, "severity": severity, "detail": detail, "fix": fix}

    # ── Слой 3: суточная сводка (детерминир. находки + LLM на сложное) ──
    def daily_report(self, since_iso: str = "") -> str:
        """Собирает находки за период, формирует текст отчёта для HQ.
        LLM используется ТОЛЬКО для краткого человекочитаемого резюме находок,
        не для вынесения вердиктов (вердикты уже посчитаны детерминированно)."""
        try:
            res = self.bridge.audit_list(since=since_iso)
            items = res.get("items", []) if isinstance(res, dict) else []
        except Exception as e:
            return f"🐀 Аудит: не смог прочитать журнал ({e})"

        flagged = [it for it in items if str(it.get("verdict")) not in ("ok", "")]
        total = len(items)
        if not flagged:
            return f"🐀 Аудит за период: проверено действий {total}, расхождений нет ✅"

        lines = [f"🐀 АУДИТ за период: действий {total}, расхождений {len(flagged)}", ""]
        # группировка по severity
        order = {"high": 0, "med": 1, "low": 2, "": 3}
        flagged.sort(key=lambda it: order.get(str(it.get("severity", "")), 9))
        for it in flagged[:20]:
            sev = str(it.get("severity", "")).upper() or "—"
            v = str(it.get("verdict", ""))
            vmap = {"hallucination": "галлюцинация", "rule_violation": "нарушение правила",
                    "logic_error": "ошибка логики", "suspect": "подозрительно",
                    "style_issue": "стиль/перевод"}
            lines.append(f"[{sev}] {vmap.get(v, v)} (тема {it.get('topic_id') or '—'})")
            if it.get("detail"):
                lines.append(f"   {it.get('detail')}")
            if it.get("suggested_fix"):
                lines.append(f"   → предложение: {it.get('suggested_fix')}")
            lines.append("")
        lines.append("Ответь номером/опиши — какие правки внести (я применю после твоего ОК).")
        return "\n".join(lines)
