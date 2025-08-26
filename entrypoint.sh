#!/bin/sh
set -e

# Heuristically find project root that contains manage.py or fidden/__init__.py
find_project_root() {
  for base in /app /workspace /code /srv/app /var/www; do
    if [ -d "$base" ]; then
      if [ -f "$base/manage.py" ] || [ -f "$base/fidden/__init__.py" ]; then
        echo "$base"; return 0
      fi
      # shallow search to depth 3
      found=$(find "$base" -maxdepth 3 -type f \( -name manage.py -o -path "*/fidden/__init__.py" \) 2>/dev/null | head -n 1 || true)
      if [ -n "$found" ]; then
        echo "$(dirname "$(dirname "$found")")"; return 0
      fi
    fi
  done
  echo "/app"
}

PROJECT_ROOT=$(find_project_root)
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$PROJECT_ROOT"

echo "[entrypoint] Project root: $PROJECT_ROOT"
echo "[entrypoint] Listing $PROJECT_ROOT contents"
ls -la "$PROJECT_ROOT" || true

echo "[entrypoint] Python sys.path"
python - <<'PY'
import sys
print("sys.path=", sys.path)
try:
    import fidden
    print("Imported fidden OK from:", getattr(fidden, "__file__", "<pkg>"))
except Exception as e:
    print("Failed to import fidden:", e)
    raise
PY

exec "$@"


