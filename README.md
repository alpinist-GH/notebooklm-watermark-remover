# nlmclean - NotebookLM Watermark Remover

Remove the NotebookLM watermark from exported **MP4 videos**, **PDFs**, **PPTX slide decks**,
and **PNG/JPG images** - fully locally, nothing is uploaded anywhere.

> **Disclaimer:** This project is not affiliated with or endorsed by Google.
> NotebookLM is a trademark of Google LLC. Only use this tool on content you have
> the right to modify.

## Features

- **Video** (the bit other tools don't do): two modes -
  *Fast* (ffmpeg `delogo`, near-instant) and *Quality* (per-frame OpenCV inpainting
  with a static-slide cache, audio preserved)
- **PDF**: removes the watermark object or inpaints it out of the page image
- **PPTX**: cleans the slide images in place; nothing else in the deck is touched
- **Images**: PNG / JPG / WEBP
- Desktop GUI with drag-and-drop batch processing, plus a full CLI
- Automatic watermark detection with manual region override

## Install

Prebuilt Windows and macOS bundles: see the GitHub Releases page (no Python or
ffmpeg install required).

From source:

```sh
pip install -e .
nlmclean --help        # CLI
nlmclean-gui           # GUI
```

ffmpeg is bundled in releases; from source it is picked up from `imageio-ffmpeg`
or your PATH.

## CLI usage

```sh
nlmclean video.mp4                       # fast mode, writes video_clean.mp4
nlmclean video.mp4 --mode quality        # per-frame inpainting
nlmclean deck.pdf slides.pptx img.png    # batch, any mix of formats
nlmclean video.mp4 --region 1240,850,200,60   # explicit watermark rect
```

## License

MIT. Release bundles include a GPL build of ffmpeg invoked as a separate
process - see `LICENSE.ffmpeg.txt` in the bundle for its license and source link.
