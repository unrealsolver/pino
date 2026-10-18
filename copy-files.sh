#!/usr/bin/bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Upload normalized event covers using ops' existing group write access.
# -O skips directory timestamps: ops can write here without owning directories.
# Inherit the server directory's group; no sudo, chown, or live-file deletion.
rsync -rtO --info=progress2 --stats \
  --chmod=D2775,F664 \
  --include='*/' --include='*.webp' --exclude='*' \
  -e 'ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10' \
  "$repo_dir/.pino/media/" ops@204.168.143.13:/var/lib/pino/media/
