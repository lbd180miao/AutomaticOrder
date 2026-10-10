# -*- mode: python ; coding: utf-8 -*-
# PLC + 3D 联调必须包含视觉算法、相机服务及 SDK；统一使用完整打包定义。
from pathlib import Path
full_spec = Path(SPECPATH) / 'AutomaticOrderFull.spec'
exec(compile(full_spec.read_text(encoding='utf-8'), str(full_spec), 'exec'))
