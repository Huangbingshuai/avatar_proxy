#!/bin/sh
set -eu

docker rm -f api-certbot-challenge >/dev/null 2>&1 || true
docker run --rm --name api-certbot-challenge --network lens-rhyme_default \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  docker.m.daocloud.io/certbot/certbot:latest renew \
  --standalone --non-interactive "$@"

cd /opt/avatar-proxy/current/deploy/volcengine
docker compose -p avatar-proxy exec -T api-gateway nginx -s reload
