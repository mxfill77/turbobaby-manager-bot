"""
Claude API клиент.
Обёртка с поддержкой инструментов (tool use):
- ЧТЕНИЕ данных через Bridge
- ЗАПИСЬ в память (remember_rule, save_note)
"""

import os
import json
import logging
from typing import Optional, List, Dict
from anthropic import Anthropic

log = logging.getLogger(__name__)


def oil_interval_for(bike_name: str) -> int:
    """Интервал замены масла (км) по типу байка:
    - Скутеры NMAX / XMAX / ADV → 4000
    - XADV и мотоциклы → 5000
    """
    n = str(bike_name).lower().replace("-", "").replace(" ", "")
    # XADV — это макси-скутер, но интервал как у крупной техники → 5000
    if "xadv" in n:
        return 5000
    # обычные скутеры
    if "nmax" in n or "xmax" in n or "adv" in n or "forza" in n or "pcx" in n or "click" in n:
        return 4000
    # всё остальное (мотоциклы: XSR, CB, CBR, MT, NINJA, VULCAN, R7, REBEL...) → 5000
    return 5000


# Описание инструментов которые Claude может вызывать
BRIDGE_TOOLS = [
    {
        "name": "get_fleet",
        "description": "Получить статус парка — все 38 байков: ДОМА/В аренде/В ремонте, кому сданы и до какой даты. Используй когда Филипп спрашивает про парк, занятость, статусы байков.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_clients",
        "description": "Получить активные аренды клиентов. По умолчанию фильтр 'active' (свежие активные < 12 месяцев). Используй когда Филипп спрашивает про текущих арендаторов, должников.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Фильтр: 'active' (по умолчанию, свежие активные), 'overdue' (просрочки), 'recent' (все свежие), 'all_active' (активные включая старые висяки)",
                    "enum": ["active", "overdue", "recent", "all_active"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_anomalies",
        "description": "Получить список аномалий — просрочки, большие долги, скорые возвраты. Используй когда Филипп спрашивает 'что не так', 'что заметил', 'есть проблемы'.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_client_history",
        "description": "История клиента по телефону или имени. Используй когда Филипп спрашивает 'кто такой X', 'арендовал ли Y раньше', 'история клиента Z'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Телефон клиента"},
                "name": {"type": "string", "description": "Имя клиента"}
            },
            "required": []
        }
    },
    {
        "name": "get_finance",
        "description": "Финансовая сводка за период: доход, количество аренд, топ байков. Используй когда Филипп спрашивает 'сколько заработали', 'доход за месяц'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Период: today, week, month, year, all",
                    "enum": ["today", "week", "month", "year", "all"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_returns_soon",
        "description": "Возвраты в ближайшие N дней. Используй когда нужно узнать кого ждём вернуть байки.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Сколько дней вперёд смотреть (по умолчанию 3)"}
            },
            "required": []
        }
    },
    {
        "name": "get_daily_pulse",
        "description": "Утренняя полная сводка одним запросом: парк + клиенты + аномалии + возвраты + финансы. Используй когда Филипп просит 'дай сводку', 'что происходит', 'что нового'.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "remember_rule",
        "description": "Сохранить НОВОЕ правило в долговременную память (SQLite). Используй ВСЕГДА когда Филипп говорит 'запомни', 'учти на будущее', 'добавь правило', или объясняет как ты должен себя вести. Правило будет загружаться перед каждым твоим ответом навсегда. НЕ подтверждай что запомнил, пока реально не вызовешь этот инструмент.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "Само правило, кратко и чётко. Например: 'jack — друг, для него CLICK 125 это исключение, не паниковать про модель'"},
                "context": {"type": "string", "description": "Контекст: когда и почему установлено. Например: 'Установлено Филиппом 28.05.2026'"}
            },
            "required": ["rule"]
        }
    },
    {
        "name": "save_note",
        "description": "Сохранить заметку о конкретном клиенте, байке или аренде. Используй когда Филипп даёт информацию про конкретную сущность (клиент хороший/плохой, байк проблемный и т.п.). Заметка всплывёт когда речь зайдёт об этой сущности.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": "Тип сущности", "enum": ["client", "bike", "rental"]},
                "entity_key": {"type": "string", "description": "Ключ: имя клиента, название байка и т.п. Например 'jack' или 'CLICK 125 PHUKET 5580'"},
                "note": {"type": "string", "description": "Текст заметки"}
            },
            "required": ["entity_type", "entity_key", "note"]
        }
    },
    {
        "name": "get_wallet_balance",
        "description": "Получить НАЛИЧНЫЙ баланс кошельков (живые деньги на руках у команды/Пыма) из Bot Data: 'Money Cashflow' и 'Самоорганизация' (мелкая касса). ⚠️ Это НЕ финансы бизнеса (доход/ROI/окупаемость) — для бизнес-финансов есть отдельный get_finance. Используй этот инструмент когда спрашивают 'баланс', 'сколько денег', 'касса', 'наличные', 'остаток'. Можно указать конкретный кошелёк или оставить пусто (все).",
        "input_schema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Имя кошелька: 'Money Cashflow' или 'Самоорганизация'. Пусто = все кошельки + итог."}
            },
            "required": []
        }
    },
    {
        "name": "get_service",
        "description": "Узнать актуальный статус ТО байка (когда последняя замена масла, когда следующая, просрочка). Данные берутся из Листа1 Байки (колонка I = пробег последней замены масла) + текущий пробег из фото темы. Используй на вопросы 'дай актуальность', 'когда ТО', 'нужно ли менять масло', 'статус обслуживания'. НЕ выдумывай цифры — этот инструмент даёт реальные.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bike": {"type": "string", "description": "Название/номер байка (из названия темы или Листа1)"}
            },
            "required": ["bike"]
        }
    },
    {
        "name": "flag_important",
        "description": "Зафиксировать ВАЖНОЕ событие (ДТП/авария, серьёзный ремонт, просрочка ТО, потеря ключа, течь, проблема с тормозами и т.п.) и закрепить напоминание в текущей теме. ВЫЗЫВАЙ ТОЛЬКО ПОСЛЕ подтверждения от Пыма/владельца ('да, закрепляй'). До подтверждения — просто спроси в чате 'это важное, закрепить? @Pleummmm подтверди'. Текст закрепа сделай коротким, ТОЛЬКО НА РУССКОМ (код сам переведёт в тайский), начни с ⚠️. Техника — байк/мотоцикл/скутер, НЕ автомобиль.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "Тип: 'accident' (ДТП), 'repair' (ремонт), 'service_overdue' (просрочка ТО), 'key_lost' (потеря ключа), 'other'"},
                "summary": {"type": "string", "description": "Краткая суть важного (1 строка), напр. 'ДТП, разбит передний фонарь'"},
                "pin_text": {"type": "string", "description": "Текст для закрепа — короткий, ТОЛЬКО НА РУССКОМ (код переведёт в тайский сам), с ⚠️ в начале. Техника = байк, не автомобиль."}
            },
            "required": ["kind", "summary", "pin_text"]
        }
    },
    {
        "name": "close_important",
        "description": "Закрыть важный пункт (выполнено) и открепить напоминание. ВЫЗЫВАЙ ТОЛЬКО ПОСЛЕ подтверждения от Пыма/владельца что это решено. Сначала спроси 'похоже решено, открепить? @Pleummmm подтверди'. row берётся из списка важного текущей темы (тебе его передадут в контексте).",
        "input_schema": {
            "type": "object",
            "properties": {
                "row": {"type": "number", "description": "Номер строки важного пункта (из контекста/списка)"},
                "confirmed_by": {"type": "string", "description": "Кто подтвердил (@username)"}
            },
            "required": ["row"]
        }
    },
    {
        "name": "set_service",
        "description": "Отметить регламент ТО байка / обновить текущий пробег в ТО-трекере. Пробег последней замены масла и интервал система берёт САМА из Листа1 Байки (колонка I) — НЕ указывай их сам, не выдумывай. Ты указываешь только байк и (если знаешь из фото/текста) текущий пробег. ВАЖНО: если current_km взят С ФОТО — сначала покажи цифру человеку и спроси подтверждение, и вызывай set_service с confirmed=true ТОЛЬКО после 'да' или после того как человек назвал верное число. Используй когда обсуждается ТО конкретного байка.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bike": {"type": "string", "description": "Название/номер байка (как в названии темы или Листе1)"},
                "service_type": {"type": "string", "description": "'oil' (масло) или 'tire' (резина). По умолчанию oil."},
                "current_km": {"type": "number", "description": "Текущий пробег ТОЛЬКО если точно известен из фото одометра или текста. Не выдумывай."},
                "confirmed": {"type": "boolean", "description": "true — пробег подтверждён человеком (сказал 'да' или назвал число). Для пробега С ФОТО без подтверждения НЕ ставь true."}
            },
            "required": ["bike"]
        }
    },
    {
        "name": "pin_reminder",
        "description": "Закрепить важное напоминание в текущей теме (например регламент ТО, просрочка масла). Используй когда Филипп/Пым просят «закрепи», или когда видишь критичную просрочку ТО которую нужно держать на виду. Текст составь ТОЛЬКО НА РУССКОМ (код сам переведёт в тайский), коротким. Техника — байк, не автомобиль.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст напоминания для закрепа — ТОЛЬКО НА РУССКОМ (код переведёт в тайский), коротко. Техника = байк, не автомобиль."}
            },
            "required": ["text"]
        }
    },
]


class ClaudeClient:
    """Обёртка над Anthropic Claude API с tool use."""

    def __init__(self, api_key: str = None, model: str = None, bridge=None, memory=None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
        self.bridge = bridge   # экземпляр BridgeClient
        self.memory = memory   # экземпляр Memory

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY не задан (см. .env)")

        self.client = Anthropic(api_key=self.api_key)

    # Защищённый список для крит-флага чёрного ящика (4.1): правило/заметка задевает trust-авторов,
    # интервалы ТО, сторож одометра, денежные правила → пометка «критичное правило» (best-effort).
    _CRIT_KEYWORDS = (
        "довер", "trust", "@pleummmm", "@turbophuket", "пым",
        "интервал", "oil_interval", " то ", "тех обслуж", "5000",
        "одометр", "сторож", "пробег не убыв", "km_decreas",
        "валют", "касс", "деньг", "usd", "usdt", "баланс", "депозит",
    )

    def _agent_gate(self, action: str) -> bool:
        """Токен-замок 4.2 для ПАМЯТИ (memory.db локальна, Bridge-гейта нет → проверка client-side).
        human → True (замок спит). agent → нужен валидный одноразовый билет (через Bridge), иначе
        False + лог rejected + пуш. Сегодня origin всегда human → всегда True."""
        try:
            import bridge_client as _bc
            if _bc.WRITE_ORIGIN.get() != "agent":
                return True
            tok = _bc.WRITE_TICKET.get()
            try:
                ok = bool(tok and self.bridge and self.bridge.consume_write_ticket(tok).get("ok"))
            except Exception:
                ok = False
            if not ok and self.bridge:
                try:
                    self.bridge.log_write(initiator="agent", act=action,
                                          args="origin=agent, ticket=" + ("invalid/expired" if tok else "none"),
                                          result="rejected", critical="токен-замок 4.2")
                    self.bridge._push_blackbox(f"🔴 ОТКЛОНЕНО (токен-замок 4.2): agent-память «{action}» без билета.")
                except Exception:
                    pass
            return ok
        except Exception:
            # сбой гейта: human (дефолт) не должен страдать; agent без явного контекста сюда не попадёт
            return True

    def _blackbox_mem(self, action: str, text: str, key: str = "") -> None:
        """Чёрный ящик (4.1): лог memory-записи (remember_rule/save_note) в боевой_лог.
        НИКОГДА не бросает — если лог упал, запись правила всё равно прошла."""
        try:
            if not self.bridge:
                return
            low = (str(text) or "").lower()
            crit = "критичное правило" if any(k in low for k in self._CRIT_KEYWORDS) else ""
            args = (("[" + key + "] ") if key else "") + str(text)[:400]
            self.bridge.log_write(initiator="memory(claude)", act=action,
                                  args=args, result="ok", critical=crit)
        except Exception as e:
            log.warning(f"  → чёрный ящик memory: лог не записан ({e}) — запись не затронута")

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Выполняет вызов инструмента и возвращает результат как строку."""
        log.info(f"Tool call: {tool_name}({tool_input})")

        try:
            # === READ через Bridge ===
            if tool_name == "get_fleet":
                result = self.bridge.fleet()
            elif tool_name == "get_clients":
                result = self.bridge.clients(filter=tool_input.get("filter", "active"))
            elif tool_name == "get_anomalies":
                result = self.bridge.anomalies()
            elif tool_name == "get_client_history":
                result = self.bridge.client_history(
                    phone=tool_input.get("phone"),
                    name=tool_input.get("name"),
                )
            elif tool_name == "get_finance":
                result = self.bridge.finance(period=tool_input.get("period", "month"))
            elif tool_name == "get_returns_soon":
                result = self.bridge.returns_soon(days=tool_input.get("days", 3))
            elif tool_name == "get_daily_pulse":
                result = self.bridge.daily_pulse()

            elif tool_name == "get_wallet_balance":
                _w = tool_input.get("wallet", "")
                if not _w:
                    result = {"ok": True, "note": "Укажи конкретный кошелёк (Money Cashflow или Самоорганизация). Общий баланс всех касс — только в Money Cashflow / HQ."}
                else:
                    result = self.bridge.get_balance(group=_w)

            elif tool_name == "pin_reminder":
                _txt = tool_input.get("text", "")
                if _txt:
                    self.pending_pins.append(_txt)
                    result = {"ok": True, "queued": True, "note": "Напоминание будет закреплено в теме."}
                else:
                    result = {"ok": False, "error": "empty text"}

            elif tool_name == "get_service":
                _bike = tool_input.get("bike", "")
                _forced = getattr(self, "_force_bike", "")
                if _forced:
                    _bike = _forced
                fb = self.bridge.find_bike(_bike) if _bike else {}
                if not fb:
                    result = {"ok": False, "error": "не нашёл байк в Листе1", "bike": _bike}
                else:
                    name = fb.get("name", _bike)
                    oil_last = fb.get("oil_last_km")
                    interval = oil_interval_for(name)
                    # текущий пробег: из фото темы (force_mileage) если есть
                    cur = getattr(self, "_force_mileage", None)
                    cur_conf = getattr(self, "_force_mileage_conf", "")
                    cur_src = "фото темы"
                    # Если фото нет в буфере (напр. после перезапуска бота) — берём
                    # последний записанный пробег из листа обслуживания
                    if not cur:
                        try:
                            sl = self.bridge.service_list()
                            items = sl.get("items", []) if isinstance(sl, dict) else []
                            best = None
                            for it in items:
                                if str(it.get("bike", "")).lower() == str(name).lower() and it.get("current_km"):
                                    best = it
                            if best:
                                cur = int(str(best["current_km"]).replace(" ", "").replace(",", ""))
                                cur_src = "последняя запись в обслуживании (фото не было в этой сессии)"
                        except Exception:
                            pass
                    next_km = (oil_last + interval) if oil_last else None
                    status = "неизвестно"
                    left = None
                    if next_km and cur:
                        left = next_km - cur
                        status = "просрочено" if left < 0 else ("скоро" if left <= 300 else "ок")
                    result = {
                        "ok": True, "bike": name,
                        "oil_last_km": oil_last, "interval_km": interval,
                        "next_oil_km": next_km, "current_km": cur,
                        "km_left": left, "status": status,
                        "note": (f"current_km из: {cur_src}" + (" — РАСПОЗНАН НЕТОЧНО (low), предупреди и попроси переснять одометр крупно" if cur_conf == "low" else "")) if cur else "текущий пробег неизвестен — нужно фото одометра в этой теме",
                    }
                    # Просрочка ТО — это ВАЖНОЕ. Готовим текст закрепа и порядок действий.
                    if status == "просрочено":
                        over = abs(left) if left is not None else "?"
                        pin_text = (
                            f"⚠️ น้ำมันเครื่องเกินกำหนด / Просрочка замены масла\n"
                            f"{name}\n"
                            f"🇹🇭 ครบกำหนด {next_km} กม. / ปัจจุบัน {cur} กม. — เกิน {over} กม. ต้องเปลี่ยนน้ำมัน\n"
                            f"🇷🇺 Плановая {next_km} км / текущий {cur} км — просрочка {over} км, нужна замена масла"
                        )
                        result["pin_text_ready"] = pin_text
                        result["ОБЯЗАТЕЛЬНЫЙ_ПОРЯДОК"] = (
                            f"ТО масла просрочено на {over} км. Сделай в ЭТОМ ответе строго по порядку: "
                            f"1) короткий расчёт (уже есть выше); "
                            f"2) покажи ГОТОВЫЙ текст закрепа дословно, начни с 'Вот что закреплю / นี่คือข้อความที่จะปักหมุด:' и приведи pin_text_ready как есть; "
                            f"3) спроси ОДИН раз 'Закрепить? @Pleummmm подтверди / ปักหมุดไหม'. "
                            f"Как ТОЛЬКО человек ответил 'да' (или 'закрепи') — СРАЗУ вызывай flag_important с pin_text_ready, "
                            f"БЕЗ повторного переспроса. Не задавай второй вопрос про закреп. "
                            f"Если по этому ТО уже есть открытое важное — не предлагай повторно."
                        )
                        log.info(f"  get_service: просрочка {over} км → отдан готовый pin_text, мозг предложит закреп")

            elif tool_name == "flag_important":
                # Кладём в очередь: bot.py закрепит и запишет в лист важного с msg_id
                self.pending_important.append({
                    "kind": tool_input.get("kind", "other"),
                    "summary": tool_input.get("summary", ""),
                    "pin_text": tool_input.get("pin_text", ""),
                })
                result = {"ok": True, "queued": True, "note": "Закреплю как важное и буду напоминать раз в 3 дня."}

            elif tool_name == "close_important":
                _row = tool_input.get("row")
                if not _row:
                    result = {"ok": False, "error": "no row"}
                else:
                    result = self.bridge.important_close(row=int(_row), confirmed_by=tool_input.get("confirmed_by", ""))
                    # пометим что надо открепить — bot.py обработает
                    self.pending_unpin.append(int(_row))

            elif tool_name == "set_service":
                # E2b [гейт]: в servicing-теме (_force_bike задан) мозг НЕ пишет ТО/обслуживание —
                # запись регламента ТОЛЬКО через кнопку подтверждения Пыма (двухфазный флоу). Закрывает
                # путь «Да»→мозг→set_service(oil) мимо гейта (каскад 4255).
                if getattr(self, "_force_bike", ""):
                    log.info("  set_service: ЗАБЛОКИРОВАН в servicing-теме (E2b) — запись ТО только кнопкой Пыма")
                    return json.dumps({
                        "ok": False, "blocked": "service_gate",
                        "ОБЯЗАТЕЛЬНО": ("Запись ТО/пробега в servicing-теме оформляется ТОЛЬКО кнопкой подтверждения "
                                        "@Pleummmm (двухфазный сервисный флоу), НЕ диалогом. НЕ вызывай set_service здесь. "
                                        "Ответь механику: результат ТО зафиксирует @Pleummmm кнопкой подтверждения."),
                    }, ensure_ascii=False)
                _bike = tool_input.get("bike", "")
                # ЗАЩИТА: в теме обслуживания байк ВСЕГДА из темы, не из выбора модели
                _forced = getattr(self, "_force_bike", "")
                if _forced and _forced != _bike:
                    log.info(f"  set_service: подменяю байк модели '{_bike}' → байк темы '{_forced}'")
                    _bike = _forced
                # Источник правды — Лист1 Байки (колонка I = oil_last_km), НЕ выдумки модели.
                fb = self.bridge.find_bike(_bike) if _bike else {}
                oil_last = fb.get("oil_last_km") if fb else None
                name_l = str(fb.get("name", _bike)).lower() if fb else str(_bike).lower()
                interval = oil_interval_for(name_l)
                kwargs = dict(
                    bike=fb.get("name", _bike) if fb else _bike,
                    service_type=tool_input.get("service_type", "oil"),
                    interval_km=interval,
                )
                # last_service_km — ТОЛЬКО из Листа1, не из аргументов модели
                if oil_last:
                    kwargs["last_service_km"] = oil_last
                # current_km: приоритет — пробег из фото ТЕКУЩЕЙ темы (force_mileage),
                # иначе то что дала модель. Защита от пробега из истории/другого байка.
                _fm = getattr(self, "_force_mileage", None)
                _fm_conf = getattr(self, "_force_mileage_conf", "")
                _confirmed = bool(tool_input.get("confirmed"))
                if _fm is not None:
                    # Пробег с ФОТО — записываем ТОЛЬКО после подтверждения человеком.
                    if not _confirmed:
                        result = {
                            "ok": False, "needs_confirmation": True,
                            "recognized_km": _fm,
                            "ОБЯЗАТЕЛЬНО": (
                                f"Пробег {_fm} км распознан с ФОТО"
                                + (" (НЕТОЧНО, low)" if _fm_conf == "low" else "")
                                + ". НЕ записан. Сначала покажи цифру и спроси: "
                                f"'📸 Вижу на фото пробег {_fm} км. Верно? Если нет — напиши правильное число / "
                                f"เห็นเลขไมล์ {_fm} กม. ถูกไหม'. После 'да' вызови set_service снова с confirmed=true. "
                                f"Если человек назвал ДРУГОЕ число — вызови set_service с current_km=<его число> и confirmed=true."
                            ),
                        }
                        log.info(f"  set_service: пробег с фото {_fm} НЕ записан — жду подтверждения человека")
                        return json.dumps(result, ensure_ascii=False)
                    if tool_input.get("current_km") not in (None, _fm):
                        # человек назвал своё число — оно в приоритете над фото
                        kwargs["current_km"] = tool_input.get("current_km")
                        log.info(f"  set_service: записываю подтверждённый пробег человека '{tool_input.get('current_km')}' (фото было '{_fm}')")
                    else:
                        kwargs["current_km"] = _fm
                        log.info(f"  set_service: записываю подтверждённый пробег с фото '{_fm}'")
                elif tool_input.get("current_km") is not None:
                    kwargs["current_km"] = tool_input.get("current_km")
                result = self.bridge.service_upsert(**kwargs)
                if not oil_last:
                    result = dict(result or {}, warning="last_service_km не найден в Листе1 (колонка I) — проверь название байка/номер")

            # === WRITE в память ===
            elif tool_name == "remember_rule":
                if not self.memory:
                    result = {"ok": False, "error": "memory not configured"}
                elif not self._agent_gate("remember_rule"):
                    result = {"ok": False, "error": "no_ticket",
                              "message": "agent-запись в память без валидного билета отклонена (токен-замок 4.2)"}
                else:
                    rule_id = self.memory.add_rule(
                        rule=tool_input["rule"],
                        context=tool_input.get("context", ""),
                        source="user",
                    )
                    result = {"ok": True, "saved": True, "rule_id": rule_id, "rule": tool_input["rule"]}
                    log.info(f"💾 Rule saved (#{rule_id}): {tool_input['rule']}")
                    self._blackbox_mem("remember_rule", tool_input["rule"])   # 4.1 чёрный ящик

            elif tool_name == "save_note":
                if not self.memory:
                    result = {"ok": False, "error": "memory not configured"}
                elif not self._agent_gate("save_note"):
                    result = {"ok": False, "error": "no_ticket",
                              "message": "agent-запись в память без валидного билета отклонена (токен-замок 4.2)"}
                else:
                    self.memory.add_note(
                        entity_type=tool_input["entity_type"],
                        entity_key=tool_input["entity_key"],
                        note=tool_input["note"],
                    )
                    result = {"ok": True, "saved": True, "entity": tool_input["entity_key"]}
                    log.info(f"💾 Note saved for {tool_input['entity_key']}: {tool_input['note']}")
                    self._blackbox_mem("save_note", tool_input["note"],
                                       key=tool_input.get("entity_key", ""))   # 4.1 чёрный ящик

            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            # Ограничиваем размер ответа для Claude
            text = json.dumps(result, ensure_ascii=False)
            if len(text) > 50_000:
                text = text[:50_000] + "\n... (truncated)"
            return text

        except Exception as e:
            log.exception(f"Tool execution error: {tool_name}")
            return json.dumps({"error": str(e)})

    def ask(
        self,
        user_message: str,
        system_prompt: str,
        history: List[Dict] = None,
        max_iterations: int = 6,
        force_bike: str = "",
        force_mileage=None,
        force_mileage_conf: str = "",
    ) -> str:
        """
        Полный цикл общения с Claude: пользователь -> ответ.
        Поддерживает tool use в несколько итераций.
        force_bike — если задан (байк текущей темы), любой set_service ПРИНУДИТЕЛЬНО
        использует этот байк, игнорируя выбор модели (защита от взятия байка из истории).
        force_mileage — если задан (пробег из фото текущей темы), подставляется в current_km.
        force_mileage_conf — 'high'/'low': уверенность распознавания пробега.
        """
        messages = (history or []) + [{"role": "user", "content": user_message}]
        self.pending_pins = []   # запросы на закреп, которые исполнит bot.py после ответа
        self.pending_important = []  # важное к закрепу+записи (bot.py исполнит)
        self.pending_unpin = []      # row важного к откреплению
        self._force_bike = force_bike or ""
        self._force_mileage = force_mileage
        self._force_mileage_conf = force_mileage_conf or ""
        self.last_actions = []   # для аудитора: [{tool,args,claimed}]

        for iteration in range(max_iterations):
            log.debug(f"Claude iteration {iteration + 1}, messages count: {len(messages)}")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                tools=BRIDGE_TOOLS,
                messages=messages,
            )

            log.debug(f"Stop reason: {response.stop_reason}")

            if response.stop_reason == "end_turn":
                text_parts = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_parts).strip()

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        # для аудитора: запоминаем что за инструмент и с чем вызван
                        try:
                            self.last_actions.append({
                                "tool": block.name,
                                "args": dict(block.input or {}),
                                "claimed": str(result)[:800],
                            })
                        except Exception:
                            pass
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            log.warning(f"Unexpected stop_reason: {response.stop_reason}")
            text_parts = [b.text for b in response.content if b.type == "text"]
            return "\n".join(text_parts).strip() or "Что-то пошло не так, попробуй ещё раз."

        return "Слишком много шагов в обработке. Попробуй переформулировать."

    def quick(self, system: str, user: str, max_tokens: int = 600) -> str:
        """
        Одноразовый вызов Claude БЕЗ инструментов — для классификации/парсинга.
        Используется Splinter'ом чтобы разобрать сообщение Пыма в строгий JSON.
        Возвращает чистый текст ответа модели.
        """
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = [b.text for b in resp.content if b.type == "text"]
            return "\n".join(parts).strip()
        except Exception as e:
            log.error(f"Claude quick() error: {e}")
            return ""

    def judge(self, system: str, user: str, max_tokens: int = 400,
              model: str = "claude-haiku-4-5") -> dict:
        """Дешёвый LLM-судья для аудитора. Отдельная МОДЕЛЬ (Haiku 4.5), НЕ self.model.
        Просит строгий JSON, парсит в dict. При любой ошибке/мусоре — пустой dict (мягко,
        аудит не должен ронять основной поток). thinking off, без инструментов."""
        import json as _json
        import re as _re
        try:
            resp = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
            m = _re.search(r"\{.*\}", text, _re.DOTALL)   # вытащить JSON-объект
            if not m:
                return {}
            return _json.loads(m.group(0))
        except Exception as e:
            log.error(f"Claude judge() error: {e}")
            return {}

    def vision(self, system: str, image_bytes: bytes, prompt: str = "",
               media_type: str = "image/jpeg", max_tokens: int = 500) -> str:
        """
        Анализ изображения через Claude vision (чеки, фото байков: топливо/пробег).
        Возвращает текст ответа (обычно строгий JSON по заданию из system).
        """
        import base64
        try:
            b64 = base64.standard_b64encode(image_bytes).decode("ascii")
            content = [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
            ]
            if prompt:
                content.append({"type": "text", "text": prompt})
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            parts = [b.text for b in resp.content if b.type == "text"]
            return "\n".join(parts).strip()
        except Exception as e:
            log.error(f"Claude vision() error: {e}")
            return ""
