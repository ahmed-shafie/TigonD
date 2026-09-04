#!/usr/bin/env bash
# Start the whole TigonD stack locally: services, migrations, backend and Studio.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

if [ ! -f backend/compose.yaml ] || [ ! -f package.json ]; then
  echo "Run this script from inside the TigonD project: cd <project> && bash scripts/run-local.sh" >&2
  exit 1
fi

missing=""
for tool in docker python3 node npm curl; do
  command -v "$tool" >/dev/null 2>&1 || missing="${missing} ${tool}"
done
if [ -n "${missing}" ]; then
  echo "Install first:${missing}" >&2
  echo "  docker -> https://docs.docker.com/get-docker" >&2
  echo "  node/npm -> https://nodejs.org (LTS) or: brew install node" >&2
  exit 1
fi

export TIGOND_METADATA_DATABASE_URL=postgresql://tigond_meta:tigond_meta@localhost:55432/tigond_metadata
export TIGOND_VAULT_URL=http://localhost:8200
export TIGOND_VAULT_TOKEN=tigond-dev-root
export TIGOND_VAULT_MOUNT=tigond
export TIGOND_KEYCLOAK_URL=http://localhost:8080
export TIGOND_KEYCLOAK_REALM=tigond
export TIGOND_KEYCLOAK_CLIENT_ID=tigond-ui
export TIGOND_ALLOWED_ORIGINS=http://localhost:3000
export TIGOND_OLLAMA_ENABLED=false

echo "==> starting metadata-db, source-postgres, vault and keycloak"
docker compose -f backend/compose.yaml up -d metadata-db source-postgres vault keycloak

echo "==> waiting for Vault and the metadata database"
until curl -sf http://localhost:8200/v1/sys/health >/dev/null; do sleep 2; done
until docker compose -f backend/compose.yaml exec -T metadata-db pg_isready -U tigond_meta -d tigond_metadata >/dev/null 2>&1; do sleep 2; done

echo "==> ensuring the Vault KV mount exists"
curl -sf -X POST -H "X-Vault-Token: ${TIGOND_VAULT_TOKEN}" \
  -d '{"type":"kv","options":{"version":"2"}}' \
  "${TIGOND_VAULT_URL}/v1/sys/mounts/${TIGOND_VAULT_MOUNT}" >/dev/null || true

if [ ! -d .venv ]; then
  echo "==> creating the Python environment"
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -f .credential-key ]; then
  ./.venv/bin/python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())" > .credential-key
fi
export TIGOND_CREDENTIAL_KEY=$(cat .credential-key)

echo "==> applying database migrations"
(cd backend && TIGOND_METADATA_DATABASE_URL="postgresql+psycopg://tigond_meta:tigond_meta@localhost:55432/tigond_metadata" "${ROOT}/.venv/bin/python" -m alembic upgrade head)

if [ ! -f .env.local ]; then
  printf 'NEXT_PUBLIC_TIGOND_API_URL=http://localhost:8000\nNEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8080\n' > .env.local
fi

if [ ! -d node_modules ]; then
  echo "==> installing frontend dependencies"
  npm ci
fi

echo "==> starting the backend on :8000"
(cd backend && "${ROOT}/.venv/bin/python" -m uvicorn app.main:app --port 8000 > "${ROOT}/backend.log" 2>&1 &)
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do sleep 2; done

echo "==> Studio on http://localhost:3000 (login admin / ChangeMe123!)"
npx vite --port 3000 --strictPort
