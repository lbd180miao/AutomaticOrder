"""RVC 3D 相机独立服务进程。

该包**不依赖 Django**，运行在独立 Python 进程中，独占 PyRVC SDK：

    python -m rvc_service

Django（apps.rvc_camera）通过本机 HTTP（默认 127.0.0.1:8001）下发指令，
避免 Django 多线程/多进程直接调用 PyRVC 导致 SDK 崩溃。
"""

__version__ = "1.0.0"
