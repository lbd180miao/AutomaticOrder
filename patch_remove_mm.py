import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace block 1: HTML inputs
target1 = '''            <label>最低 IoU<input id="foam-min-iou" type="number" min="0" max="1" step="0.01" value="0.7"></label>
            <label>最大偏移(mm)<input id="foam-max-offset-mm" type="number" min="0" step="0.1" value="2"></label>
            <label>X像素/毫米<input id="foam-pixels-per-mm-x" type="number" min="0" step="0.1" value="0"></label>'''

replace1 = '''            <label>最低 IoU<input id="foam-min-iou" type="number" min="0" max="1" step="0.01" value="0.7"></label>
            <label>X像素/毫米<input id="foam-pixels-per-mm-x" type="number" min="0" step="0.1" value="0"></label>'''

# Replace block 2: loadThresholds
target2 = '''  document.getElementById('foam-min-score').value = minScore;
  document.getElementById('foam-min-iou').value = minIoU;
  document.getElementById('foam-max-offset-mm').value = maxOffsetMm;
  
  let pxPerMmX = thresh.pixels_per_mm_x ?? 0;'''

replace2 = '''  document.getElementById('foam-min-score').value = minScore;
  document.getElementById('foam-min-iou').value = minIoU;
  
  let pxPerMmX = thresh.pixels_per_mm_x ?? 0;'''

# Replace block 3: saveRecipe
target3 = '''    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),
    maxOffsetMm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    max_offset_mm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    pixels_per_mm_x: Number(document.getElementById('foam-pixels-per-mm-x').value || 0),'''

replace3 = '''    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),
    pixels_per_mm_x: Number(document.getElementById('foam-pixels-per-mm-x').value || 0),'''

for t, r in [(target1, replace1), (target2, replace2), (target3, replace3)]:
    if t in content:
        content = content.replace(t, r)
        print("Patched one block")
    else:
        print(f"Target not found: {t[:50]}...")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
