#!/usr/bin/env bash
#
# Remote half of the deploy pipeline. Copied to the GCP VM and executed there
# by .github/workflows/deploy.yml — not meant to be run from a laptop.
#
# Contract (all supplied by the workflow via the ssh environment):
#   DEPLOY_DIR        directory on the VM holding compose + .env  (default /opt/ai-second-brain)
#   IMAGE_TAG         commit SHA to deploy
#   BACKEND_IMAGE     ghcr.io/<owner>/<repo>/backend
#   FRONTEND_IMAGE    ghcr.io/<owner>/<repo>/frontend
#   HEALTH_CHECK_URL  URL that must return 200 with {"status":"ok"}
#   TRIGGERED_BY      GitHub actor, for the deploy log
#
# Secrets arrive out of band in $DEPLOY_DIR/.env, which the workflow writes
# over ssh. Nothing secret is passed as an argument or echoed here.

set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ai-second-brain}"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.prod.yml"
STATE_FILE="${DEPLOY_DIR}/.deployed_tag"
LOG_FILE="${DEPLOY_DIR}/deploy.log"
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://localhost/api/v1/health/}"
HEALTH_RETRIES="${HEALTH_RETRIES:-24}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"

: "${IMAGE_TAG:?IMAGE_TAG is required}"

cd "$DEPLOY_DIR"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "${DEPLOY_DIR}/.env" "$@"
}

log_event() {
  # timestamp \t result \t tag \t actor
  printf '%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${TRIGGERED_BY:-unknown}" >> "$LOG_FILE"
}

# Rewrite only the IMAGE_TAG line in .env, leaving secrets untouched.
set_tag() {
  local tag="$1"
  if grep -q '^IMAGE_TAG=' .env; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${tag}|" .env
  else
    echo "IMAGE_TAG=${tag}" >> .env
  fi
}

health_check() {
  local i body
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    # -f fails on non-2xx, -L follows FastAPI's trailing-slash redirect.
    if body="$(curl -fsSL --max-time 10 "$HEALTH_CHECK_URL" 2>/dev/null)"; then
      if printf '%s' "$body" | grep -qE '"status" *: *"ok"'; then
        echo "Health check passed on attempt ${i}."
        return 0
      fi
      echo "Attempt ${i}/${HEALTH_RETRIES}: 200 but not healthy yet: ${body:0:200}"
    else
      echo "Attempt ${i}/${HEALTH_RETRIES}: no 200 from ${HEALTH_CHECK_URL} yet."
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

bring_up() {
  local tag="$1"
  set_tag "$tag"
  echo "--- Pulling images for tag ${tag}"
  compose pull

  echo "--- Starting data services"
  compose up -d postgres redis qdrant

  echo "--- Running database migrations (alembic upgrade head)"
  # Run migrations with the *new* backend image before the app serves traffic.
  compose run --rm --no-deps backend alembic upgrade head

  echo "--- Starting application services"
  compose up -d --remove-orphans
}

PREVIOUS_TAG=""
if [[ -f "$STATE_FILE" ]]; then
  PREVIOUS_TAG="$(cat "$STATE_FILE")"
fi

echo "=== Deploying ${IMAGE_TAG} (previous: ${PREVIOUS_TAG:-none}) ==="

if bring_up "$IMAGE_TAG" && health_check; then
  echo "$IMAGE_TAG" > "$STATE_FILE"
  log_event "success" "$IMAGE_TAG"
  echo "=== Deploy of ${IMAGE_TAG} succeeded ==="
  exit 0
fi

echo "!!! Deploy of ${IMAGE_TAG} failed its health check." >&2
compose ps || true
compose logs --tail 100 backend || true

if [[ -z "$PREVIOUS_TAG" ]]; then
  log_event "failed-no-rollback" "$IMAGE_TAG"
  echo "!!! No previous tag recorded — cannot roll back automatically." >&2
  echo "!!! The stack is left running so you can inspect it." >&2
  exit 1
fi

echo "=== Rolling back to ${PREVIOUS_TAG} ==="
# NOTE: this rolls back application code only. Alembic migrations already
# applied are NOT reverted — if the new revision was destructive you must run
# `alembic downgrade` by hand (see docs/deployment.md).
if bring_up "$PREVIOUS_TAG" && health_check; then
  echo "$PREVIOUS_TAG" > "$STATE_FILE"
  log_event "rolled-back-to-${PREVIOUS_TAG}" "$IMAGE_TAG"
  echo "=== Rolled back to ${PREVIOUS_TAG}; deploy of ${IMAGE_TAG} is marked failed ==="
  exit 1
fi

log_event "rollback-failed" "$IMAGE_TAG"
echo "!!! Rollback to ${PREVIOUS_TAG} also failed health checks. Manual intervention required." >&2
exit 2
