#!/usr/bin/env bash
set -euo pipefail

OPTIONS="/data/options.json"

# PIN protection needs an AES-256 key. Auto-generate and persist it in /data
# on first run so it survives restarts/updates — an explicitly-set
# ENCRYPTION_KEY env var always wins, for advanced/standalone setups that
# manage their own secrets.
mkdir -p /data
if [ -z "${ENCRYPTION_KEY:-}" ]; then
    KEY_FILE="/data/encryption_key"
    if [ ! -f "$KEY_FILE" ]; then
        python -c "import secrets; print(secrets.token_hex(32))" > "$KEY_FILE"
        chmod 600 "$KEY_FILE"
    fi
    export ENCRYPTION_KEY
    ENCRYPTION_KEY="$(cat "$KEY_FILE")"
fi

if [ -f "$OPTIONS" ] && [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    echo "[run.sh] Add-on mode — reading options"
    eval "$(python -c "
import json, shlex
opts = json.load(open('$OPTIONS'))
mapping = {
    'admin_username': 'ADMIN_USERNAME',
    'admin_password': 'ADMIN_PASSWORD',
    'app_name': 'APP_NAME',
    'contact_message': 'CONTACT_MESSAGE',
    'brand_bg': 'BRAND_BG',
    'brand_primary': 'BRAND_PRIMARY',
    'guest_url': 'GUEST_URL',
}
for key, env in mapping.items():
    val = opts.get(key, '')
    if val:
        print(f'export {env}={shlex.quote(str(val))}')
")"

    export HA_BASE_URL="http://supervisor/core"
    export HA_TOKEN="${SUPERVISOR_TOKEN}"
    export DB_PATH="/data/db.sqlite"
else
    echo "[run.sh] Standalone mode — using environment variables"
fi

exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-5880}" --workers 1
