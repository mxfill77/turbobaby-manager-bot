# Авто-проверка здоровья — установка systemd timer (🔴 системная служба, по «да»)

Файлы юнитов: `deploy/splinter-health.service` + `deploy/splinter-health.timer`.
Зовут `health.py --push` (пуш владельцу ТОЛЬКО при ❌). Интервал — каждые 4 часа.

## Установка (🔴 — выполнять по явному «да» Филиппа)
```
cp /root/turbobaby-manager-bot/deploy/splinter-health.service /etc/systemd/system/splinter-health.service
cp /root/turbobaby-manager-bot/deploy/splinter-health.timer   /etc/systemd/system/splinter-health.timer
systemctl daemon-reload
systemctl enable --now splinter-health.timer
```

## Проверка
```
systemctl list-timers splinter-health.timer
systemctl status splinter-health.timer
systemctl start splinter-health.service
journalctl -u splinter-health.service -n 20
```

## Откат
```
systemctl disable --now splinter-health.timer
rm /etc/systemd/system/splinter-health.timer /etc/systemd/system/splinter-health.service
systemctl daemon-reload
```

## Сменить интервал
Править `OnUnitActiveSec=` в `splinter-health.timer` (напр. `3h` / `6h`), затем
`cp` юнит заново → `systemctl daemon-reload` → `systemctl restart splinter-health.timer`.
