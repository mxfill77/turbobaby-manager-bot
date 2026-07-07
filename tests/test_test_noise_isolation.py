"""§12 (06.07.2026): тест-шум ФИЗИЧЕСКИ не дотягивается до живого лога и лички Splinter.
Три корня recon 12:10 закрыты:
  (а) import orchestrator_daemon под тестом НЕ конфигурирует FileHandler на ЖИВОЙ
      orchestrator_daemon.log (логгер → NullHandler);
  (б) прямой прогон теста (МИМО gate.py, без ручного PRETOOL_NOPUSH) НЕ шлёт карточку в личку —
      notify на импорте сам поднимает PRETOOL_NOPUSH по тест-entry-point → notify замьючен;
  (в) сырой stdout claude -p НЕ релеится как карточка (_fail_card = чистая суть), а
      громкий-провал ДЕНЕГ (splinter._note_llm_loss money=True) ШЛЁТ пуш — границу не сломали.
Сети/Telegram/claude НЕТ — всё мокнуто/проверяется чистыми функциями."""
import os
import sys
import logging

ROOT = "/root/turbobaby-manager-bot"
# снимаем флаги гейта — проверяем, что защитные слои ставят их САМИ (мимо gate.py)
os.environ.pop("PRETOOL_NOPUSH", None)
os.environ.pop("NOTIFY_COUNT_FILE", None)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (кусок 2)
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
sys.path.insert(0, ROOT)

res = []
def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label); res.append(bool(c)); return c


# ─────────────────────────── (б) notify: тест-entry-point → авто-мут ───────────────────────────
# notify импортируется ПЕРВЫМ (флаг PRETOOL_NOPUSH снят выше) → его импорт-guard должен поднять флаг
import notify as N
print("(б) прямой прогон теста не шлёт карточку в личку:")
ok(N._is_test_entrypoint() is True, "_is_test_entrypoint() True (entry-point = tests/test_*.py)")
ok(os.environ.get("PRETOOL_NOPUSH") == "1", "notify на импорте сам поднял PRETOOL_NOPUSH=1 (мимо гейта)")

_SENT = []
N._send_message = lambda tok, txt: (_SENT.append(txt), (True, 1))[-1]
N._get_token = lambda: "TKN"
_SENT.clear()
r = N.notify("🔴 тестовая красная карточка фикстуры")   # force=False (как фикстуры/тесты)
ok(r is True and _SENT == [], "notify(non-force) в тест-прогоне ЗАМЬЮЧЕН — сеть НЕ дёрнута (0 карточек)")


# ─────────────────────── (а) orchestrator_daemon: логгер не пишет в живой лог ───────────────────
import orchestrator_daemon as OD
print("(а) import orchestrator_daemon не пишет в живой orchestrator_daemon.log:")
ok(getattr(OD, "_UNDER_TEST", False) is True, "OD._UNDER_TEST True (тест-прогон распознан)")
_livepath = os.path.abspath(OD.LOG_PATH)
_bad = [h for h in logging.getLogger().handlers
        if isinstance(h, logging.FileHandler)
        and os.path.abspath(getattr(h, "baseFilename", "")) == _livepath]
ok(not _bad, "нет FileHandler на живой orchestrator_daemon.log (логгер → NullHandler)")
# дёрнём логирующую функцию демона — строка НЕ должна уйти в живой файл (проверяем размер до/после)
_before = os.path.getsize(_livepath) if os.path.exists(_livepath) else 0
OD.log.info("ФИКСТУРА test_test_noise_isolation — эта строка НЕ должна попасть в живой лог")
for h in logging.getLogger().handlers:
    try: h.flush()
    except Exception: pass
_after = os.path.getsize(_livepath) if os.path.exists(_livepath) else 0
ok(_after == _before, "живой лог НЕ вырос после log.info фикстуры (не засран)")


# ─────────────────── (в) сырой stdout НЕ карточка; громкий провал денег ШЛЁТ пуш ────────────────
print("(в) сырой stdout claude -p не релеится, а громкий провал денег шлёт пуш:")
raw = "СВОДКА: задача не собралась (первая строка = контрактная сводка)\n" + \
      "\n".join(f"debug шумиха строка {i} — куча сырого вывода claude -p" for i in range(40))
err = "Traceback (most recent call last):\n  ...\nRuntimeError: конкретная-ошибка-XYZ"
card = OD._fail_card(raw, err, 1)
ok(len(card) <= 600, f"карточка провала капнута (<=600, факт={len(card)})")
ok(len(card) < len(raw), "карточка КОРОЧЕ сырого stdout (сырой поток не релеится целиком)")
ok("debug шумиха строка 20" not in card, "средний сырой шум НЕ попал в карточку")
ok("СВОДКА" in card, "контрактная сводка (первая строка stdout) сохранена")
ok("конкретная-ошибка-XYZ" in card, "хвост реальной ошибки (stderr) сохранён")

# граница: громкий провал ДЕНЕГ отдельным механизмом (splinter._note_llm_loss) — ПУШ идёт
import splinter as S
_PUSH = []
N.notify = lambda text, *a, **k: (_PUSH.append(text), True)[-1]
import notify as _n_mod
_n_mod.notify = N.notify
S._llm_loss.update({"loud_ts": 0.0, "collapsed": 0, "quiet": 0})
_PUSH.clear()
pushed_money = S._note_llm_loss(money=True, wallet="Money Cashflow", lost_text="перевод 500")
ok(pushed_money is True and len(_PUSH) == 1, "громкий провал ДЕНЕГ → пуш владельцу (граница цела)")
S._llm_loss.update({"loud_ts": 0.0, "collapsed": 0, "quiet": 0})
_PUSH.clear()
pushed_nonmoney = S._note_llm_loss(money=False, kind="vision-байк", detail="фото")
ok(pushed_nonmoney is False and _PUSH == [], "НЕ-деньги (сырой/vision) → без пуша (шум приглушён)")


print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
