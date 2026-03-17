#!/usr/bin/env bash
# Run pytest with cv2 loadable: temporarily restore opencv's libSDL2 so tests don't skip,
# run pytest, then re-apply the duplicate-SDL fix so the app still runs without warnings.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
DYLIBS=""
for d in venv/lib/python3.*/site-packages/cv2/.dylibs; do
  [ -d "$d" ] || continue
  DYLIBS="$d"
  break
done
RESTORED=""
if [ -n "$DYLIBS" ] && [ -f "$DYLIBS/libSDL2-2.0.0.dylib.bak" ]; then
  mv "$DYLIBS/libSDL2-2.0.0.dylib.bak" "$DYLIBS/libSDL2-2.0.0.dylib"
  RESTORED=1
  echo "[run_tests] Temporarily restored cv2 libSDL2 for pytest."
fi
cleanup() {
  if [ -n "$RESTORED" ] && [ -n "$DYLIBS" ] && [ -f "$DYLIBS/libSDL2-2.0.0.dylib" ]; then
    mv "$DYLIBS/libSDL2-2.0.0.dylib" "$DYLIBS/libSDL2-2.0.0.dylib.bak"
    echo "[run_tests] Re-applied SDL fix (renamed cv2 libSDL2 to .bak)."
  fi
}
trap cleanup EXIT
source venv/bin/activate
python -m pytest tests/ -v "$@"
