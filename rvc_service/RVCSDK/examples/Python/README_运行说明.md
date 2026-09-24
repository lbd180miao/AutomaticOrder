# RVC Python 示例运行说明

## 1. 安装 Python 解释器（必做）

您当前只有「Python 3.7 Manuals」——那是**文档**，不是可执行环境。要运行本项目的 Python 示例，需要先安装 **Python 解释器**。

### 推荐步骤

1. **下载 Python（64 位）**  
   - 打开：https://www.python.org/downloads/  
   - 下载 **Python 3.7～3.11** 的 **64-bit** 安装包（与项目 C++ 构建一致）。

2. **安装时务必勾选**  
   - ✅ **Add Python to PATH**  
   这样在命令行可直接使用 `python`、`pip`。

3. **验证安装**  
   打开新的「命令提示符」或 PowerShell，执行：
   ```bat
   python --version
   pip --version
   ```
   能输出版本号即表示安装成功。

---

## 2. 安装 Python 依赖

在项目根目录或任意目录下执行：

```bat
pip install numpy opencv-python
```

（部分示例还会用到其他库，运行报错时再按提示用 `pip install` 安装即可。）

---

## 3. 构建含 Python 绑定的 RVC 工程

本仓库的 Python 示例依赖 **PyRVC** 模块（由项目内的 C++ 用 pybind11 编译得到），因此需要先**用 CMake 构建整个解决方案**，并**启用 Python 绑定**。

- 使用 CMake 配置时请保证 **RVC_WITH_PYTHON=ON**（默认一般为 ON）。  
- 用 Visual Studio 打开生成的 `.sln`，编译 **PyRVC** 以及其依赖（如 RVC、IDevice 等）。  
- 构建完成后，会生成 **PyRVC.pyd**（或对应平台的模块），通常在类似：
  - `bin\Modules\PyRVC\Debug\` 或  
  - `bin\Modules\PyRVC\Release\`  
  的目录下（具体以你 CMake 配置的输出目录为准）。

若你尚未用本仓库成功构建过 C++/RVC，需要先按项目主文档完成 CMake 配置与编译。

---

## 4. 运行示例的方式

### 方式 A：设置 PYTHONPATH 后运行（推荐）

1. 打开「命令提示符」或 PowerShell。  
2. 进入**示例所在目录**（这样 `from Utils.Tools` 等才能找到同级的 `Utils` 包）：
   ```bat
   cd D:\program\RVC\RVC0\Examples\Python
   ```
3. 把 **PyRVC 所在目录**加入 `PYTHONPATH`（请按实际路径替换，例如 Debug 或 Release）：
   ```bat
   set PYTHONPATH=D:\program\RVC\RVC0\bin\Modules\PyRVC\Debug;%PYTHONPATH%
   ```
   若构建的是 Release，把 `Debug` 改为 `Release`。  
4. 运行某个示例，例如：
   ```bat
   python GetCameraResolution.py
   ```
   或：
   ```bat
   python QuickCaptureX2.py
   ```

### 方式 B：不设 PYTHONPATH，把 PyRVC 放到示例目录

- 将构建得到的 **PyRVC.pyd** 以及同目录下依赖的 **RVC.dll** 等复制到 `Examples\Python`。  
- 在「命令提示符」中：
  ```bat
  cd D:\program\RVC\RVC0\Examples\Python
  python GetCameraResolution.py
  ```
  这样 Python 会在当前目录找到 `PyRVC`。

---

## 5. 常见问题

| 现象 | 处理 |
|------|------|
| 提示「Python 不是内部或外部命令」 | 未正确安装 Python 或未勾选「Add Python to PATH」。重新安装并勾选，或使用「 py -3 」等完整路径。 |
| `ModuleNotFoundError: No module named 'PyRVC'` | 未设置 `PYTHONPATH` 或未把 `PyRVC.pyd` 放到 Python 能搜到的目录；或尚未成功构建 PyRVC。 |
| `ModuleNotFoundError: No module named 'Utils'` | 未在 `Examples\Python` 下执行脚本，请先 `cd` 到该目录再运行。 |
| `ImportError: DLL load failed` / 找不到 RVC.dll | 将 RVC 相关 DLL（如 RVC.dll）放到与 PyRVC.pyd 同一目录，或放到系统 PATH 中的目录。 |

---

## 总结

1. **安装真正的 Python 解释器**（从 python.org 下载 64 位安装包），并勾选加入 PATH。  
2. **用本仓库构建出 PyRVC**（RVC_WITH_PYTHON=ON，并编译 PyRVC 及依赖）。  
3. **在 `Examples\Python` 下运行脚本**，并通过 **PYTHONPATH** 或**复制 PyRVC.pyd 与 DLL** 让 Python 能找到 PyRVC 和 RVC 运行时库。

按以上步骤即可在本机运行项目中的 Python 示例。
