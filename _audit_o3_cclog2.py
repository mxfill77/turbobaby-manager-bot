import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

cc_entry = ("DONE 2026-07-14 14:10 UTC: [куратор цели 357, шаг 2] Аудит адопции O3 08-14.07.2026. "
"(1) Handover/return тайская команда Обслуживание: 4 события — "
"2 return saved (10.07 X MAX 300 4724 06:14, NMAX 155 5960 08:57) + "
"1 return-ctx/repair (14.07 NINJA 400 6334 08:49) + 1 handover (14.07 NINJA 400 09:38); "
"всего 48 events saved (12 repair + 32 photo + 2 return + 1 intake + 1 handover), "
"79 сообщений за неделю. "
"(2) Карточки Входящих: 1 — 🏍 ВЫДАЧА NINJA 400 14.07 09:38 (бронь не найдена); "
"кнопки «да» в логе НЕТ; row 1270 Siments добавлен вручную + 23021 THB money-чат 11:27. "
"📥 ПРИЁМ-карточки: 0 — все 3 return пошли идемпотентным путём (строка уже Завершена). "
"(3) CRM: closing_get матчит старые Завершённые строки вместо текущей аренды. "
"NMAX 155 5960 row 703 (Sostrand, старт 11.06, дедлайн 11.07) НЕ закрыта — "
"return 10.07 нашёл old row 1204 (Kutuzov 2025-07). "
"NINJA 400 row 1262 (Gladkov) закрыта вручную ДО return (14.07 08:49); "
"row 1270 (Siments) добавлен вручную. "
"Кнопка активации в Входящих не нажималась ни разу. "
"(4) Вердикт: команда активна (79 сообщений/неделю, события парсятся); "
"критический баг: поиск текущей аренды возвращает old Завершённую строку → не закрывает. "
"Хвост: row 703 открыт (просрочена ~3 дня).")

pulse_text = ("2026-07-14 14:10 UTC | 🟡 | Аудит O3 08-14.07: 4 return/handover, "
"1 ВЫДАЧА-карточка вручную, closing_get-баг → row 703 NMAX 155 не закрыт | "
"ничего не жду | детали→cc_log DONE 14.07 аудит O3 шаг2")

# Read cc_log
r = bc._call("read_doc", name="cc_log")
if not r.get('ok'):
    print('ERROR read cc_log:', r)
    sys.exit(1)
content = r.get('text', r.get('content', ''))
print(f'cc_log read ok, length={len(content)}')

# Find header separator (═-only line)
lines = content.split('\n')
insert_pos = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped and all(c == '═' for c in stripped) and i > 0:
        insert_pos = i + 1
        break

if insert_pos == 0:
    new_content = cc_entry + '\n\n' + content
else:
    new_content = '\n'.join(lines[:insert_pos]) + '\n' + cc_entry + '\n' + '\n'.join(lines[insert_pos:])

# Write cc_log
wr = bc.write_doc(text=new_content, name='cc_log')
print('cc_log write:', wr.get('ok'), wr.get('error', ''))

# Write pulse
pr = bc.write_doc(text=pulse_text, name='pulse')
print('pulse write:', pr.get('ok'), pr.get('error', ''))
