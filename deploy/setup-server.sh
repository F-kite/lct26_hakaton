#!/usr/bin/env bash
# Разовая настройка сервера (Ubuntu): nginx + firewall + запуск сервисов.
# Запуск из корня репозитория: sudo bash deploy/setup-server.sh
set -euo pipefail
cd "$(dirname "$0")/.."

apt-get update
apt-get install -y nginx

install -m 644 deploy/nginx/signals.conf /etc/nginx/sites-available/signals.conf
ln -sf /etc/nginx/sites-available/signals.conf /etc/nginx/sites-enabled/signals.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# SSH разрешаем ДО включения firewall, иначе потеряем доступ
if command -v ufw >/dev/null; then
  ufw allow OpenSSH
  ufw allow 'Nginx Full'
  ufw --force enable
fi

[ -f .env ] || cp .env.production.example .env
docker compose up -d --build
docker compose ps

# HTTPS: только если домен уже указывает на этот сервер.
# certbot сам допишет в конфиг nginx блок 443 и редирект с http.
# бесплатное имя, всегда резолвится в IP сервера; заменить на свой домен, когда появится
DOMAIN=155-212-219-107.sslip.io
apt-get install -y certbot python3-certbot-nginx
if [ "$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')" = "$(curl -s -4 ifconfig.me)" ]; then
  certbot --nginx -d "$DOMAIN" --redirect --agree-tos --register-unsafely-without-email --non-interactive
else
  echo "DNS $DOMAIN ещё не указывает на этот сервер — HTTPS пропущен."
  echo "После смены A-записи: sudo certbot --nginx -d $DOMAIN --redirect"
fi
