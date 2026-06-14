#!/usr/bin/env bash
# Usage: packaging/make_dmg.sh OUTPUT.dmg
# Ad-hoc signs the .app (required on Apple Silicon) and wraps it in a dmg.
# No `pipefail` (no pipelines here) so the script also survives `sh make_dmg.sh`.
set -eu

APP="dist/nlmclean.app"
OUT="${1:?usage: make_dmg.sh OUTPUT.dmg}"

# The bundled ffmpeg is a data file and can lose its executable bit during
# collection; restore it before signing so the signed binary is runnable.
# Search by name to stay agnostic to the .app's internal layout.
find "$APP" -name ffmpeg -type f -exec chmod +x {} +

# Strip extended attributes (resource forks, com.apple.FinderInfo, quarantine)
# before signing. Source trees staged from Windows/iCloud or a macOS-formatted
# external drive carry this metadata, and codesign rejects it with
# "resource fork, Finder information, or similar detritus not allowed".
# Also delete AppleDouble (._*) sidecars that such drives scatter into the tree.
find "$APP" -name '._*' -delete
xattr -cr "$APP"

codesign --force --deep -s - "$APP"
codesign -dv "$APP"
hdiutil create -volname "nlmclean" -srcfolder "$APP" -ov -format UDZO "$OUT"
echo "wrote $OUT"
