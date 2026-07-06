"""§12: ранний детектор «кредит платного ключа на нуле» (health.check_api_credit).
Проверяет:
- 400 credit-too-low → warn + классификация; 401/отзыв ключа → warn;
- happy (проба прошла) → тихо (warn=False);
- прочая ошибка (сеть/5xx) → НЕ warn (ранний детектор не паникует);
- дедуп эпизода (Поправка А): warn → 1 пуш, повтор warn → тихо, восстановление → закрытие эпизода.
Реальных сетевых вызовов НЕТ — проба инжектится (_probe), файл-маркер эпизода во временном пути."""
import os, sys, tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ["ANTHROPIC_API_KEY"] = "x"   # чтобы проба НЕ пропускалась «нет ключа»
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import health as H

results = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    results.append(cond)


# ---- подставные исключения (имена как у anthropic, реальные не конструируем) ----
class BadRequestError(Exception): pass
class AuthenticationError(Exception): pass
class APIConnectionError(Exception): pass


# ---- (1) классификация ----
w, d = H._classify_credit_error(BadRequestError("Your credit balance is too low to access the API"))
ok(w, "(1) 400 credit-too-low → warn")
w, d = H._classify_credit_error(AuthenticationError("invalid x-api-key"))
ok(w, "(1) 401/отзыв ключа → warn")
w, d = H._classify_credit_error(APIConnectionError("connection reset"))
ok(not w, "(1) сеть/5xx (не кредит) → НЕ warn (ранний детектор не паникует)")

# ---- (2) check_api_credit с инжектом пробы ----
def _probe_credit():
    raise BadRequestError("Your credit balance is too low")
def _probe_ok():
    return {"ok": True}

w, d = H.check_api_credit(_probe=_probe_credit)
ok(w and "кредит" in d.lower(), "(2) проба ловит кредит-на-нуле → warn+detail")
w, d = H.check_api_credit(_probe=_probe_ok)
ok(not w, "(2) happy (проба прошла) → тихо (warn=False)")

# нет ключа → проба пропускается (не warn, не паникуем). Пустая строка = «нет ключа»;
# load_dotenv(override=False) не перезатрёт уже установленное значение реальным ключом из .env.
_saved = os.environ.get("ANTHROPIC_API_KEY")
os.environ["ANTHROPIC_API_KEY"] = ""
w, d = H.check_api_credit(_probe=_probe_credit)
ok(not w and "проба пропущена" in d, "(2) нет ANTHROPIC_API_KEY → проба пропущена, не warn")
os.environ["ANTHROPIC_API_KEY"] = _saved if _saved else "x"

# ---- (3) дедуп эпизода: 1 пуш на эпизод, восстановление закрывает ----
tmp = tempfile.mkdtemp(prefix="credit_ep_")
H._CREDIT_EPISODE_FILE = os.path.join(tmp, ".api_credit_episode")

ok(H._credit_episode_should_push(True) is True, "(3) первый warn эпизода → пуш (True)")
ok(H._credit_episode_should_push(True) is False, "(3) повтор warn того же эпизода → тихо (False)")
ok(os.path.exists(H._CREDIT_EPISODE_FILE), "(3) маркер эпизода создан")
ok(H._credit_episode_should_push(False) is False, "(3) восстановление → пуша нет")
ok(not os.path.exists(H._CREDIT_EPISODE_FILE), "(3) маркер эпизода снят при восстановлении")
ok(H._credit_episode_should_push(True) is True, "(3) новый эпизод после восстановления → снова пуш")


if __name__ == "__main__":
    print(f"OK — {sum(results)}/{len(results)} проверок test_api_credit_probe")
    sys.exit(0 if all(results) else 1)
