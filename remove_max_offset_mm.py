import sys

file_path = "apps/vision/algorithms/foam_inspector.py"
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "max_offset_mm" in line:
        if "offset_distance_mm" in line or "offset_x_mm" in line or "offset_y_mm" in line:
            # Not max_offset_mm, keep it, wait, just string match
            pass
        if "max_offset_mm=" in line or "'max_offset_mm':" in line or "max_offset_mm = float" in line:
            continue # drop it
        if "coverage_threshold, max_offset_mm):" in line:
            new_lines.append(line.replace(", max_offset_mm", ""))
            continue
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Done")
