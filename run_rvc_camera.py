"""双击/命令行启动 RVC 相机独立服务（等价于 python -m rvc_service）。

启动前请：
1. 相机上电、网线直连，网卡与相机同网段（相机默认 169.254.10.202）；
2. 关闭 RVCManager（会抢占相机连接）。
"""
import sys

from rvc_service.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
