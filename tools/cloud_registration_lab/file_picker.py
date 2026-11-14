"""Isolated native file picker; no Open3D import or shared GUI event loop."""
import json
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    config = json.load(sys.stdin)
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        ext = config['extension']
        types = [(ext + ' 文件', '*' + ext)] if ext else [
            ('点云文件', '*.ply *.pcd *.npy *.xyz *.txt *.asc *.csv *.pts *.xyzn *.xyzrgb')]
        types.append(('全部文件', '*.*'))
        initial = Path(config['initial_path']) if config['initial_path'] else None
        options = dict(parent=root, title=config['title'], filetypes=types,
                       initialdir=str(initial.parent) if initial else config['directory'])
        if config['save']:
            options.update(defaultextension=ext, confirmoverwrite=False)
            if initial:
                options['initialfile'] = initial.name
            path = filedialog.asksaveasfilename(**options)
        else:
            path = filedialog.askopenfilename(**options)
        print(json.dumps({'path': path}, ensure_ascii=False))
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
