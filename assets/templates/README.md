# Watermark templates

Drop grayscale crops of the real NotebookLM watermark here to enable
template-based detection (more accurate than the geometry heuristic):

- `wm_video.png` - cropped from a Video Overview frame
- `wm_doc.png` - cropped from a PDF/PPTX slide export

Crop tightly around the logo + "NotebookLM" text and convert to grayscale.
`nlmclean.detect.template` picks these up automatically; without them the
geometry heuristic and the GUI's manual region adjustment are used.
