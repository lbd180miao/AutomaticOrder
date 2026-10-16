| **名称**              | **数据类型** | **偏移量** | **起始值** |
| --------------------- | ------------ | ---------- | ---------- |
| Static                | Struct       | 0.0        |            |
| ▶ PLC-CCD             | Struct       |            |            |
| ▶ CCD-PLC             | Struct       | 48.0       |            |
| 心跳信号              | Bool         | 48.0       | false      |
| 产品条码处理完成确认  | Bool         | 48.1       | false      |
| 产品条码校验结果      | Bool         | 48.2       | false      |
| 单件 MES 上传完成确认 | Bool         | 48.3       | false      |
| 单件 MES 上传结果     | Bool         | 48.4       | false      |
| 料框处理完成确认      | Bool         | 48.5       | false      |
| 料框处理结果          | Bool         | 48.6       | false      |
| 配方校验完成确认      | Bool         | 48.7       | false      |
| 可装箱结果            | Bool         | 49.0       | false      |
| 3D 定位完成确认       | Bool         | 49.1       | false      |
| 3D 定位结果           | Bool         | 49.2       | false      |
| 当前层视觉补偿 ΔX1    | Real         | 50.0       | 0.0        |
| 当前层视觉补偿 ΔY1    | Real         | 54.0       | 0.0        |
| 当前层视觉补偿 ΔZ1    | Real         | 58.0       | 0.0        |
| 当前层视觉补偿 ΔX2    | Real         | 62.0       | 0.0        |
| 当前层视觉补偿 ΔY2    | Real         | 66.0       | 0.0        |
| 当前层视觉补偿 ΔZ3    | Real         | 70.0       | 0.0        |
| 泡棉检测完成确认      | Bool         | 74.0       | false      |
| 泡棉检测结果          | Bool         | 74.1       | false      |
| MES 封箱上传完成确认  | Bool         | 74.2       | false      |
| MES 封箱上传结果      | Bool         | 74.3       | false      |
| 工位锁定              | Bool         | 74.4       | false      |

通讯约定：

- 74.0 为泡棉检测完成确认，检查结束后置 True，与 OK/NG 无关。
- 74.1 为泡棉检测结果，OK 为 True，NG 为 False；拍照或检测异常也回写 False。
- PLC 撤销泡棉触发后，上位机将 74.0、74.1 复位为 False。
- 70.0 按此表地址写入第二组 Z 补偿；表内 ΔZ3 与程序内 ΔZ2 指向同一个 REAL 地址。
