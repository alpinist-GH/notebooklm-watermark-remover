# Changelog

## 0.2.0 (unreleased)

### GUI overhaul

- Menu bar (File / Process / Settings / Help) with About and About Qt dialogs;
  every action now has an icon, a keyboard shortcut and a status-bar hint
- New **Output window**: finished files appear in their own window with a
  built-in preview - videos play with audio (QtMultimedia), images, PDF pages
  and PPTX slides render inline; Open / Show in Folder / Clear List actions.
  It opens docked side by side with the input window and follows it around;
  drag it away to detach it
- **Remove Selected** (toolbar, menu, right-click, Del key) and **Exit** actions
- Settings dialog: video mode, output folder, metadata stripping, detection
  mode (replaces the old toolbar combos)
- Richer drop-zone help text
- Bundle: QtMultimedia is now included for the preview player (bigger download)

### New removal capabilities

- **Gemini sparkle watermark** on AI-generated images and infographics:
  detected and removed stroke-precisely via a new watermark-profile system
  (images try both the NotebookLM wordmark and the Gemini sparkle)
- **Universal video mode** (`--detect universal` / Settings > Detection): finds
  *any* static burned-in watermark by comparing frames over time - no template
  needed. Needs moving footage; still slideshows are refused with a clear
  message and the manual region selector remains the fallback
- **Metadata stripping** (`--strip-metadata` / Settings checkbox, off by
  default): EXIF (images), Info + XMP (PDF), document properties (PPTX),
  container tags (video)

## 0.1.1

- macOS: locate bundled ffmpeg via sys._MEIPASS (fixes video processing in the
  .app bundle); single Intel dmg that runs on all Macs via Rosetta

## 0.1.0

- Initial release: watermark removal for MP4 video (fast delogo + quality
  inpaint modes), PDF, PPTX, and PNG/JPG images. Desktop GUI with
  drag-and-drop batch processing.
