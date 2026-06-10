#!/usr/bin/env bash
# Usage: packaging/make_dmg.sh OUTPUT.dmg
# Ad-hoc signs the .app (required on Apple Silicon) and wraps it in a dmg.
set -euo pipefail

APP="dist/nlmclean.app"
OUT="${1:?usage: make_dmg.sh OUTPUT.dmg}"

codesign --force --deep -s - "$APP"
codesign -dv "$APP"
hdiutil create -volname "nlmclean" -srcfolder "$APP" -ov -format UDZO "$OUT"
echo "wrote $OUT"
