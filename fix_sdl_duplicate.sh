#!/usr/bin/env bash
# Fix duplicate libSDL2 between pygame and opencv (macOS): rename opencv's copy
# so only one SDL loads and the "Class X is implemented in both" warnings go away.
# Run once after: pip install -r requirements.txt
# Re-run if you reinstall opencv or pygame.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
CV2_DYLIBS=""
for d in venv/lib/python3.*/site-packages/cv2/.dylibs; do
  [ -d "$d" ] || continue
  if [ -f "$d/libSDL2-2.0.0.dylib" ]; then
    CV2_DYLIBS="$d"
    break
  fi
done

if [ -n "$CV2_DYLIBS" ] && [ -f "$CV2_DYLIBS/libSDL2-2.0.0.dylib" ]; then
  if [ ! -f "$CV2_DYLIBS/libSDL2-2.0.0.dylib.bak" ]; then
    mv "$CV2_DYLIBS/libSDL2-2.0.0.dylib" "$CV2_DYLIBS/libSDL2-2.0.0.dylib.bak"
    echo "Renamed opencv's libSDL2-2.0.0.dylib to .bak (duplicate SDL fix applied)."
  else
    echo "Fix already applied (libSDL2-2.0.0.dylib.bak exists)."
  fi
else
  echo "Could not find cv2 .dylibs/libSDL2-2.0.0.dylib. Run from project root with venv present."
  exit 1
fi
