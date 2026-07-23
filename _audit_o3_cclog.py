import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

cc_text = """DONE 2026-07-14 10:10 UTC: [куратор цели 357 шаг 1] Аудит адопции O3 за 08-14.07.2026 (read-only). ФАКТЫ: (1) 5 handover/return событий тайской команды в Обслуживание — 3×return (10.07: X MAX 300 4724 + NMAX 155 5960; 14.07: NINJA 400 6334) + 1×intake + 1×handover (14.07 NINJA 400); итого 12 repair + 32 photo, 79 сообщений в группе. (2) Карточек во Входящих: 1 (ВЫДАЧА NINJA 400 14.07 09:38 → бронь не найдена → ⚠️ активация руками); "да" через кнопку в логе НЕ найдено — row 1270 Siments В аренде появился, но через лист вручную. ПРИЁМ-карточки не генерировались (все 3 return ушли в идемпотентный путь). (3) CRM: NINJA 400 row 1270 "В аренде" (14-17 Jul, новый). GAP: NMAX 155 GREY 5960 row 703 (Sostrand, due 11.07) ещё "В аренде" — return 10.07 нашёл OLD row 1204 (Завершена 2025) вместо актуальной → дыра закрытия. NINJA 400 row 1262 (Gladkov, end 21.07) — закрыта досрочно вручную до return. (4) Вердикт: круг живёт базово (Пым/команда ежедневно пишет, события парсятся), критический баг — closing_get матчит старую завершённую строку вместо текущей активной. Хвост: row 703 не закрыт, кнопка activate не нажималась."""

pulse_text = "2026-07-14 10:10 UTC | 🟡 | Аудит O3 08-14.07 завершён: 5 handover/return событий, 1 ВЫДАЧА-карточка (активация вручную), CRM-баг (close_booking старый row) — NMAX 155 row 703 не закрыт | ничего не жду | детали→cc_log DONE 14.07 аудит O3"

# Read cc_log first
cc_result = bc.read_doc(name='cc_log')
if not cc_result.get('ok'):
    print('ERROR: cannot read cc_log:', cc_result)
    sys.exit(1)

content = cc_result.get('content', '')

# Find the separator line (═══) to insert below it
lines = content.split('\n')
insert_pos = 0
for i, line in enumerate(lines):
    if line and all(c == '═' for c in line.strip()) and i > 0:
        insert_pos = i + 1
        break

if insert_pos == 0:
    # No header found, prepend
    new_content = cc_text + '\n\n' + content
else:
    new_content = '\n'.join(lines[:insert_pos]) + '\n' + cc_text + '\n' + '\n'.join(lines[insert_pos:])

# Write cc_log
write_result = bc.write_doc(name='cc_log', content=new_content)
print('cc_log write:', write_result.get('ok'), write_result.get('error', ''))

# Write pulse
pulse_result = bc.write_doc(name='pulse', content=pulse_text)
print('pulse write:', pulse_result.get('ok'), pulse_result.get('error', ''))
