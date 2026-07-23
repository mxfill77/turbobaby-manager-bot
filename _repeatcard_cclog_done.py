import sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

done = (f"DONE {utc} UTC: два VPS-микрохвоста §7 одной задачей (commit 3a4a300, push ok, гейт 83/83). "
        "(1) «(повтор)» на клон-карточках (класс 7ff92fb/инцидент 156): _requeue_foreign_restart дописывает "
        "маркер «[повтор задачи N]» строго В КОНЕЦ текста клона (стартовые [шаг i/N]/[конверт…] целы, "
        "клон клона маркер не дублирует, enqueue-fail-ветка прежняя); devbot по маркеру ставит «(повтор)» "
        "в заголовок done/failed-рапорта и анонса «в работе» (константа REPEAT_MARK продублирована, "
        "тест сверяет равенство). (2) pretool_guard: _strip_git_msg вырезает payload -m/-am/--message[=]/"
        "приклеенное -m из СКАН-представления git-команды → слово-интерпретатор в тексте git commit -m "
        "(«фикс python скрипта») больше не даёт ложную ambiguous-карточку (нюанс bd5d516); классификация "
        "git не менялась, компаунд git…&&python ловится, red/ambiguous/green настоящих python-команд "
        "нетронуты, fail-safe на не-git/кривом квотировании. Тесты: test_repeat_card (16) + "
        "test_pretool_commit_msg (20) в гейте; легаси-ассерты дословности клона в test_foreign_restart "
        "обновлены под контракт «дословно + маркер в конце». Нужен был restart splinter (devbot в его "
        "процессе) — сделал оранжевым циклом: гейт зелёный → restart → active, старт-лог чистый (Bridge "
        "alive, scheduler started). Демон: отложенный systemd-run --on-active=10s рестарт (самомод). "
        "Статус: технически готово + гейт; функциональное подтверждение «(повтор)»-карточки — при "
        "следующем живом возврате из-под чужого рестарта. Бэкапы: *.bak-repeatcard-20260712, "
        "pretool_guard.py.bak-commitmsg-20260712; откат = git revert 3a4a300 + restart. Хвостов новых нет.")

pulse = (f"{utc} | \U0001F7E2 | микрохвосты §7 закрыты: «(повтор)» на клон-карточках (156) + git commit -m "
         "без ложной карточки (bd5d516), commit 3a4a300, гейт 83/83, splinter рестартнут чисто, демон — "
         "отложенный рестарт | ничего не жду | детали→cc_log DONE «два VPS-микрохвоста §7»")

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r.get("error")); sys.exit(1)
text = r.get("text") or r.get("content") or ""
lines = text.split("\n")
# вставка ПОД врезкой: ищем закрывающую ═-only строку старт-блока
ins = 0
bars = [i for i, ln in enumerate(lines[:80]) if ln.strip() and set(ln.strip()) == {"═"}]
if len(bars) >= 2:
    ins = bars[1] + 1
new = "\n".join(lines[:ins] + ["", done, ""] + lines[ins:]) if ins else done + "\n\n" + text
w = c.write_doc(text=new, name="cc_log")
print("cc_log write:", w.get("ok"), w.get("error"))
wp = c.write_doc(text=pulse, name="pulse")
print("pulse write:", wp.get("ok"), wp.get("error"))
sys.exit(0 if (w.get("ok") and wp.get("ok")) else 1)
