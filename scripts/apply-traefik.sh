#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${1:?Indique el servicio Swarm de SIGREP}"
DOMAIN="${2:?Indique el dominio de SIGREP}"
NETWORK_NAME="dokploy-network"
NETWORK_ID="$(docker network inspect "$NETWORK_NAME" --format '{{.Id}}')"
NETWORKS="$(docker service inspect "$SERVICE_NAME" --format '{{range .Spec.TaskTemplate.Networks}}{{println .Target}}{{end}}')"
NETWORK_ARGS=()
if ! grep -Fxq "$NETWORK_ID" <<< "$NETWORKS"; then
  NETWORK_ARGS=(--network-add "$NETWORK_NAME")
fi

docker service update --detach=false \
  "${NETWORK_ARGS[@]}" \
  --label-add 'traefik.enable=true' \
  --label-add "traefik.docker.network=$NETWORK_NAME" \
  --label-add "traefik.http.routers.sigrep.rule=Host(\`$DOMAIN\`)" \
  --label-add 'traefik.http.routers.sigrep.entrypoints=websecure' \
  --label-add 'traefik.http.routers.sigrep.tls=true' \
  --label-add 'traefik.http.routers.sigrep.tls.certresolver=letsencrypt' \
  --label-add 'traefik.http.routers.sigrep.service=sigrep' \
  --label-add 'traefik.http.services.sigrep.loadbalancer.server.port=8080' \
  --label-add "traefik.http.routers.sigrep-http.rule=Host(\`$DOMAIN\`)" \
  --label-add 'traefik.http.routers.sigrep-http.entrypoints=web' \
  --label-add 'traefik.http.routers.sigrep-http.service=sigrep' \
  --label-add 'traefik.http.routers.sigrep-http.middlewares=sigrep-redirect-https' \
  --label-add 'traefik.http.middlewares.sigrep-redirect-https.redirectscheme.scheme=https' \
  --label-add 'traefik.http.middlewares.sigrep-redirect-https.redirectscheme.permanent=true' \
  "$SERVICE_NAME"

RULE="$(docker service inspect "$SERVICE_NAME" --format '{{index .Spec.Labels "traefik.http.routers.sigrep.rule"}}')"
PORT="$(docker service inspect "$SERVICE_NAME" --format '{{index .Spec.Labels "traefik.http.services.sigrep.loadbalancer.server.port"}}')"
[[ "$RULE" == "Host(\`$DOMAIN\`)" && "$PORT" == "8080" ]] || exit 1
printf 'Labels SIGREP verificados: https://%s\n' "$DOMAIN"