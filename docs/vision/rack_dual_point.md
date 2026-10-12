# M2600 四 ROI 双交点定位改造（2026-10-11）

本次增加四 ROI 绘制/保存/二维测试和独立双交点算法。保留现有相机、PLC、MES、条码、装箱流程及三平面算法。**尚未完成现场三维测量验收，不自动替换现有生产算法，不启用新的 PLC 六值写入。**

## 现在怎样画四个框

1. 打开原来的「3D 料架定位工作台」，选定配方。
2. 使用原来的「采集点云」或「数据包管理 → 加载」。
3. 默认进入「四 ROI · P1 / P2 双交点」主流程。先点击「检查当前点云」，再点击「载入原图与四 ROI」。读取相机原图，缺少原图时报错，不使用深度伪彩图测边。
4. 分别选择 ROI1（P1 横杆）、ROI2（P1 立柱）、ROI3（P2 横杆）、ROI4（P2 立柱），在新增画布上拖动框选。框内拖动移动，右下角调整大小；「重画选中 ROI」仅清除当前框。缩放滑块和画布滚动不改变保存的原图坐标。
5. 选择 Projection 或 CaliperFit；每个 ROI 可以覆盖默认算法。设置极性、单边/双边中心、具体边缘身份。横杆的 `expectedPosition` 是原图 Y，立柱是原图 X。先验斜率分别为 dy/dx 和 dx/dy；搜索半宽限制在该先验位置附近测边。
6. 点击「测试二维定位」，显示四条直线、边缘点、两个交点和各线内点比例、残差、角度。可勾选双算法对比。初始阈值仅供调试，应按实际图像调整。
7. 点击「保存定位配置」，写入原有 `roi_config` 的 `dual_point` 子字段。再次载入可回显。该动作保存配置，**不是保存 XYZ 示教**。

换配方或换采集帧后需重新载入，避免把旧图的结果用于新帧。不同图像尺寸不自动缩放旧 ROI，而是提示重新框选。高级 JSON 可配置交点允许范围、质量阈值及后续三维参数；现阶段不提供无效标定下的“保存三维示教”按钮。

## 已检查的架构与数据

| 范围 | 现有实现与核实结果 |
|---|---|
| SDK 采集 | `rvc_service/camera_controller.py` 同次 Capture 后读取 PointMap 和 Image；PointMap 默认从 m 缩放到 mm，支持配置覆盖；X2 按 Extra/Left 选择相机坐标及图像通道。当前实现不能证明历史数据也使用相同选项。 |
| 相机服务 | `apps/rvc_camera/services.py`、`RVCCameraRackFrameProvider` 提供图像与组织化点云。此次未修改。 |
| 原工作台 | `rack_location.py` 持久化点云、原图与单位文件；JS 已有 `rackLocatorOfflineBridge.snapshot()`，新增编辑器直接复用该接口，没有修改原 JS。 |
| 配方与三平面 | `rack_spatial.py`、`rack_spatial_service.py`、`local_template_3d.py`；保留已有逻辑及用户原有修改。 |
| 标定方向 | `CoordinateTransformService.camera_to_robot_base()` 明确定义 `T_base_flange @ T_flange_camera`。新算法使用相同顺序，但要求逐帧确认矩阵方向和同步关系。 |
| 旧 PLC 写入 | `rack_location.py::PlcVisionResultWriter` 与现有 device adapter；没有修改 DB 地址、握手、层号或业务发布逻辑。 |

已读取 `3d_SDK/pic/2026-10-08_POS1_L1_055629` 与 `2026-10-08_POS1_L1_060004`：

- 原图 `(1080,1440,3)`，点云 `(1080,1440,3)`、float32；metadata 标注 **m**。
- 有限且非全零点分别 510741、515803；这只是原始数据数量，不是有效横杆内点数量。
- 两个 hand_eye_matrix 都为单位阵；robot_pose 平移均为 `[900.68,530.53,271.4]`，旋转为单位阵。
- `camera.frame_index=null`，缺少可核验的同步位姿/像素配准说明、内参和标定版本。
- 配置是旧三平面 ROI；不自动推断四 ROI 或将旧框解释为两个横杆参考面。
- 原图有产品/包覆物遮挡；需要人工确认两处横杆及其指定边缘、可见表面。相同分辨率不能证明像素配准，更不能证明前缘一定是可拟合平面。

双帧离线审计输出在 `media/vision/dual_point_validation/20261011/report.json`，两帧均因缺少四 ROI 等前提停止，没有生成虚假 XYZ 或补偿值。输出目录还保存各帧预览。原始数据包未修改。

## 本次文件清单

| 文件 | 作用 |
|---|---|
| `apps/vision/algorithms/rack_dual_point.py` | 独立二维、三维、坐标变换、示教差分及质量检查，无数据库/硬件 I/O |
| `apps/vision/rack_positioning_algorithm.py` | 仅新增 `RackPositioningAlgorithm.locate_dual_points(...)` 方法；旧调用不变 |
| `apps/vision/rack_dual_point_offline.py` | 单帧/双帧离线 CLI，原子写 JSON，保存标注预览 |
| `apps/vision/rack_dual_point_views.py` | 原图读取、点云取证、二维/三维校验、配置与签名 XYZ 示教 API |
| `apps/vision/urls.py` | 增加四个独立 API 路由 |
| `templates/vision/rack_dual_point_panel.html` | 默认主流程：原图四 ROI、P1/P2 结果、质量检查、分层传递与验收表格 |
| `templates/vision/rack_locator_panel.html` | 引入面板及 JS，不改原操作流程 |
| `static/vision/js/rack_dual_point.js` | 独立绘图状态、缩放、拖动/调整、原图坐标、参数和结果显示 |
| `apps/vision/tests_dual_point.py`、`tests_dual_point_ui.py` | 算法与接口集成测试 |

无需数据库迁移，无新增第三方依赖。工作区中本来存在的其他修改/删除未回滚，不能把整个 `git diff` 当作此次修改范围。

## 核心算法和接口

- Projection 与 CaliperFit 共用 `sample_profile → measure_profile` 内核：沿法线取剖面、切向平均、中心差分梯度、极性筛选、亚像素峰值和双边宽度检查。仅采样布局不同：前者等分长度、使用整段宽卡尺，后者使用配置的窄卡尺。边界外采样不产生伪峰。算法版本升级为 v2，旧示教需要重验。
- 双边中心必须同时找到两侧并通过宽度检查；不会缺一边时退化成单边。两算法同源灰度，比较仅用于调试，超差/备用算法失败只记录告警，不改变主算法成败，也不自动切换。调试开关/像素差阈值不纳入测量身份摘要；测边算法和参数仍纳入。
- 两组拟合线求浮点交点，检查夹角、交点范围、点数、有效率、内点率、残差和倾斜。
- 对每个交点，沿对应横杆边缘内侧的配置采样带取点，排除交叉遮挡邻域；过滤 NaN/Inf、零深度、目标深度/空间范围外点；复用 `robust_plane()`，检查内点率、残差和平整度，然后求成像射线与平面的交点，并限制外推距离。
- 新增 `VisionResultValidator` 独立门控：从完整相机点云中按经过示教的三维包围盒提取横杆正面及相邻表面，各自拟合后求实体棱边，投回图像与二维拟合线比较 RMS/最大距离/角度，同时检查恢复点到独立正面的距离和法向一致性。该拟合不以二维线、采样带或射线交点作为输入；单个正面平面不足以自证一致。中心线需要两条不同实体棱边，比较两条投影在相同 X 下的中心及宽度。当前实现只支持可观测的相邻平面实体棱边，圆管/单可见面的替代独立特征仍需现场取证后设计。
- 曲面/细杆/退化点云失败时明确报错，**不自动换成单像素深度或另一个物理表面**。若实拍证实为圆管，应另行验证“管轴 + 已知半径”的参考定义；当前未凭空实现并启用这种模式。
- 支持已验证的 H×W×3 对应关系，或 N×3 + H×W 的 SDK 索引表（-1 无效）；不猜测 reshape 对应关系。
- 支持眼在手上、固定相机和 SDK 已转机器人基坐标三种显式模式。示教与生产各用自己的采集位姿；后者为射线几何暂转回相机系，再输出机器人系，避免重复变换。
- `teach_reference(result)` 只接受完整双点成功结果；离线工具用临时文件 + fsync + replace 保存。`compensation(current, reference, config, now=...)` 保留当前减示教的横杆实测位移，再按经过加载标定的分层传递比和轴向映射生成放置面偏移，第三层不补偿。检查算法/配置/标定摘要、机器人坐标系、点身份、独立一致性、有限值、映射前后工艺限值和可选在线时效。
- `success` 代表该接口的计算成功；二维 API 另外明确返回 `three_d_success=false`。新增路径始终 `plc_publish_allowed=false`，离线 `compensation_valid` 也不得当作 PLC 发布许可。

新增 API 均位于 `/vision/api/rack-location/dual-point/`：

| URL | 方法 | 输入/输出 |
|---|---|---|
| `prepare/` | POST | 输入原工作台 snapshot + recipe_id，返回签名图像 token、原图尺寸、配方 `dual_point` 或新草稿 |
| `image/` | GET | 带签名 token 的原图；签名有效期 1 小时，文件变化需重载 |
| `test/` | POST | image_token + config，返回四线/双交点/质量与明确的三维未验证状态 |
| `save/` | POST | image_token + recipe_id + config，事务内仅合并 `roi_config.dual_point` |

失败包含 `errorCode`、`errorMessage`、`stage`。原有端点、返回结构和数据库模型不变。

## 三维数据契约

离线输入仍为原需求的文件集合。仅在采集及标定事实已经核验后，由采集/标定数据提供者在 `metadata.json` 的 `dual_point_contract` 下记录：

| 字段 | 含义 |
|---|---|
| `frame_id`, `image_frame_id`, `cloud_frame_id` | 同一次采集标识，三者必须一致 |
| `captured_at` | 带时区的 ISO 时间 |
| `sensor_id`, `sensor_config_version` | 相机及采集配置身份 |
| `calibration_version`, `calibration_verified` | 经验证的标定版本及确认；不能为了绕过报错改成 true |
| `robot_frame` | 示教/生产共同使用的机器人基坐标系身份 |
| `unit`, `matrix_unit` | 点云 m/mm，矩阵平移 mm；与原 camera.pointcloud_unit 一致 |
| `mapping_verified`, `mapping_evidence` | SDK/标定对应关系确认及验证记录标识 |
| `mapping_mode` | `organized_registered` 或 `pixel_index_map`；后者另外提供 pixel_index_map.npy |
| `camera_model` | `type=pinhole` + `K` + `rectified=true`，或 `type=opencv` + `K` + `distortion`；必须与该原图通道/坐标系对应 |
| `transform_mode`, `cloud_frame` | `eye_in_hand`/`fixed_camera` 配 `camera`，或 `robot_base` 配 `robot_base` |
| 眼在手上额外项 | `hand_eye_direction=T_flange_camera`, `pose_direction=T_base_flange`, `pose_frame_id=frame_id`, `pose_synchronized=true` |
| 固定相机额外项 | `hand_eye_direction=T_base_camera`，hand_eye_matrix.npy 存该外参 |
| 点云已在机器人系 | `T_base_camera` 提供当前成像几何所需相机外参 |

UI 保存/高级 JSON 可导出四 ROI 配置。完整三维计算还需要配置：

- `geometry.P1`、`geometry.P2`：`model=beam_plane_ray`，`surfaceBandPx`（相对横杆线，图像 Y 正方向；上边必须为正、下边必须为负）、`intersectionExclusionPx`、`depthRangeMm`、可选 `boundsMm`（两行 XYZ 上下界），`min_points`、`ransac_mm`、`iterations`、`min_inlier_ratio`、`max_residual_mm`、`max_eigenvalue_ratio`、`min_ray_cosine`、`max_extrapolation_mm`。
- `maxOffsetMm`：2×3 数组，P1/P2 的 XYZ 工艺限值，必须为正有限数值。
- `maxResultAgeSeconds`：在线调用差分时的时效上限；在线必须传 `now`。离线比较不假装历史数据是实时数据，始终禁止发布。

这些数值必须依据真实料架和相机验证，不内置伪造的现场安全阈值。当前 UI 草稿只有二维参数，缺少三维参数时三维入口会失败。

## 运行与验证

项目根目录执行：

```powershell
.venv/Scripts/python.exe -m unittest apps.vision.tests_dual_point -v
.venv/Scripts/python.exe manage.py test apps.vision.tests_dual_point_ui --noinput
.venv/Scripts/python.exe manage.py test apps.vision.tests_rack_stability apps.vision.tests_rack_input apps.vision.tests_standard_reference --noinput
node --check static/vision/js/rack_dual_point.js
.venv/Scripts/python.exe manage.py check

# 单帧审计；有完整契约/参数时同时执行定位
.venv/Scripts/python.exe -m apps.vision.rack_dual_point_offline 3d_SDK/pic/2026-10-08_POS1_L1_055629 --output media/vision/dual_point_single

# 双帧审计/差分；--config 可传 UI 导出的独立 JSON，或包含 dual_point 的 roi_config.json
.venv/Scripts/python.exe -m apps.vision.rack_dual_point_offline 3d_SDK/pic/2026-10-08_POS1_L1_055629 --run 3d_SDK/pic/2026-10-08_POS1_L1_060004 --output media/vision/dual_point_pair
```

CLI 成功返回 0，前提/定位失败返回 2。成功帧保存 `teach_reference.json`；结果与双帧报告分别为 `result.json`、`report.json`，预览为 `preview.png`。输出必须在原始数据包以外。

第二轮验证加入独立棱边、映射、点云取证和统计测试。合成数据只证明计算和失败处理，不代表真实 M2600 重复精度。当前执行环境缺少 requirements.txt 已列出的 whitenoise；接口及临时浏览器测试服务隔离了该静态文件中间件，未修改部署配置。浏览器使用临时数据库与合成数据包，验证了 ROI 回显、二维/三维结果、配置保存、签名示教、同帧补偿拦截和修改后清空结果，不代表生产启动或现场精度验收。

## 仍待完成

1. **先点云取证**：建议先安排半天现场摸底（不是已经完成半天实验）。固定料架、原曝光/替代曝光、空载/加载各留独立帧。圈定目标横杆三维区域，统计有效点数、孔洞、平面及三维线的内点率/残差/跨度和跨帧稳定性。黑色反光/稀疏无法稳定拟合时，先调整采集、补光或参考几何，不能用更精细二维结果补救缺失的深度证据。
2. 通过可测性摸底后，再利用四 ROI 实拍验证二维物理边缘身份，补齐配准/内参、真实标定和同帧位姿，完成独立 2D–3D 棱边校验、双帧 XYZ 与连续采集重复性。
3. 页面已接通完整数据包的三维校验、XYZ 示教保存和六值偏移显示。现场在线采集仍需提供完整帧契约：当前采集 token 的单位记录不含经验证的配准、内参和同步标定，界面会拒绝三维结果，不能把旧单位阵视作有效标定。
4. 按现场 DB 定义确认六值顺序、单位/符号、有效/完成/失败握手、超时、节拍号、失效清除与原子发布，再接入现有 PLC adapter；不改装箱层号和其他业务。

未执行真实机器人运动、PLC 写入或现场装箱验收。

## 第二轮配置与量化验收

新增 `apps/vision/vision_result_validator.py` 与 `rack_dual_point_quality.py`、`tests_dual_point_quality.py`。其他业务模块仍不修改。

**独立三维门控配置**：每个 `geometry.P1/P2.consistency` 必须包括 `model=two_face_edge`、`edgeSide`、`frontFace`、`sideFaces`。每个面包含 `boundsMm`（两行相机 XYZ 毫米上下界）、`normal`（示教法向量）、`normalToleranceDeg`。`sideFaces` 单边为一个面、中心为两个面。`fit` 包含 `ransac_mm/min_points/iterations/min_inlier_ratio/max_residual_mm/max_eigenvalue_ratio`。门控参数包括 `minPlaneSine/minSpanMm/maxSupportGapMm/minSpanPx/maxRmsPx/maxDistancePx/maxAngleDeg/maxSurfaceDistanceMm/maxSurfaceAngleDeg`。所有参数需由真实横杆验证后填写；当前没有假定现场相邻面一定可见。

**传递关系配置**（高级 JSON 的 `placementTransfer`）：

```json
{
  "verified": false,
  "calibrationVersion": "",
  "evidence": "",
  "inputFrame": "robot_base",
  "outputFrame": "",
  "layers": {
    "1": {"k_layer": null, "axisMap": null, "maxPlacementOffsetMm": null},
    "2": {"k_layer": null, "axisMap": null, "maxPlacementOffsetMm": null}
  }
}
```

`Δplacement = k_layer × axisMap × Δbeam`，axisMap 为带符号的 3×3 轴排列矩阵，行表示输出轴、列表示输入轴。例如 `[[0,-1,0],[1,0,0],[0,0,1]]` 表示输出 X=-输入 Y，输出 Y=输入 X，输出 Z=输入 Z；这只是格式示例，不能直接当现场映射。`k_layer` 为非负有限标量，按每层多载荷实测回归填写。若发现轴间耦合、非线性或不同轴传递不同，应另行扩展验证模型，不能强行使用一个 k。

横杆实测位移仍在 `offsets/measured_six_values`；`placement_offsets/layer_offsets/six_values` 是映射后的放置面值。映射版本变更需要重新验证示教；未标定或映射后超限均不输出六值结果。新路径始终禁止 PLC 发布。

| 指标 | 数值定义 | 配置/判定 |
|---|---|---|
| 固定架重复性 | 每个 P1/P2、XYZ 分别计算样本标准差 s（ddof=1）、3s、峰峰值；3σ 表示均值两侧的半宽 | 摸底目标 `exploratoryThreeSigmaMm=0.5` mm，即 ±0.5 mm；建议至少 30 独立帧。正式 `maxThreeSigmaMm` 默认 null |
| 横杆各轴位移上限 | abs(当前机器人 XYZ - 示教 XYZ) | `maxOffsetMm` 为 2×3 正数，默认 null；根据机械行程/装箱容差及加载实测填写 |
| 放置面各轴上限 | abs(k × axisMap × Δbeam) | 每层 `maxPlacementOffsetMm` 为 XYZ 正数，默认 null；不能仅检查映射前的位移 |
| GR&R | 均衡交叉 ANOVA，保留操作者×零件交互项，负方差分量截零；%Tolerance = 100 × 6σ_GRR / (USL-LSL) | `toleranceWidthMm` 是全宽；`maxGrrPercentTolerance` 默认 null，不擅自套用 10%/30% 为现场标准 |
| 双二维算法差异 | 两交点各自的欧氏像素差 | `maxAlgorithmDifferencePx` 默认 null；用实测分布设定，仅调试，不替代独立门控 |
| 2D–3D 投影一致性 | 独立实体棱边投影到二维线的 RMS、最大距离、夹角 | 使用上述 consistency 配置，经真实点云和边缘身份核验后填写 |
| 失败率 | 失败采集帧数 / 总采集帧数 | `maxFailureRate` 默认 null；失败帧保留统计，不通过丢弃失败帧美化重复性 |

GR&R 的计算口径参考 [Minitab：交叉 GR&R 方差分量及公差百分比](https://support.minitab.com/en-us/minitab/help-and-how-to/quality-and-process-improvement/measurement-system-analysis/how-to/gage-study/crossed-gage-r-r-study/methods-and-formulas/gage-r-r-table/)。实现固定保留交互项，不执行自动模型筛选、不提供置信区间；现场正式 MSA 还需确认试验设计。不能把单组固定架连拍统计称为 GR&R。

验收阈值的 `acceptance.verified/evidence` 未经现场确认、缺少 GR&R 或阈值为空时，报告不会给出统计通过结论。即使 `statistical_limits_passed=true`，`production_accepted` 仍为 false：还需要物理身份、偏倚/准确度、机器人方向和装箱实证，统计通过不是 PLC 发布许可。

```powershell
# 先取证，完全不运行二维算法。可以没有 roi_config.json 或 metadata.json；缺单位时只输出原始有效率。
.venv/Scripts/python.exe -m apps.vision.rack_dual_point_offline 3d_SDK/pic/2026-10-08_POS1_L1_055629 --forensics-only --output media/vision/depth_first

# 固定架和 GR&R 实测统计（无需相机/PLC）
.venv/Scripts/python.exe -m apps.vision.rack_dual_point_offline --study study.json --output media/vision/acceptance
```

取证还可通过 `--config` 的 `forensics.regions` 给出三维包围盒，每区配置 `boundsMm/planeRansacMm/lineRansacMm/min_points/iterations`，输出平面和三维线的可拟合性与失败原因。取证网格是数组索引分区，不冒充已配准图像区域；区域坐标为点云原坐标系按已确认单位转成 mm，不擅自认定是机器人系。没有横杆三维区域时不做全场景拟合来证明横杆可测。

`study.json` 包含：`acceptance`（上述现场限值）、`repeatability_records`（每帧 `frame_id/success/robot_points`，robot_points 为 2×3；另有共同 `condition_id/config_digest/calibration_digest/robot_frame`），可选 `grr_values`（零件×操作者或独立重装×重复×2×3 的完整数组）。重复 frame_id、混载荷/配置/标定及缺失 GR&R 单元会明确拒绝；条件和公差必须由现场确认，不从结果反推。

本次实际生成 `media/vision/dual_point_forensics/20261011/report.json`。两组点云全场景有效率分别 **32.8409% / 33.1663%**；未提供目标横杆三维取证区域，因此**尚未证明横杆平面或三维线可稳定拟合**。两张静态数据不能得出连续拍照 3σ 或 GR&R，本次未捏造这些实测指标。

## 同步后的工作台主流程

默认展示四 ROI 页面；顶部「定位流程」可切换旧版三平面兼容界面。旧三平面 ROI、A/B 六轴、局部模板和平面交点表只在兼容模式显示，不与新 P1/P2 结果混排。采集、配方选择和数据包管理共用原入口。

1. 采集或加载数据包 → 检查当前点云（不需要先画四 ROI）。
2. 载入原图与四 ROI → 画框 / 移动 / 调整大小 → 测试二维定位。
3. 填写分层传递与验收表格，保存定位配置。空间取证区域、独立三维表面和详细质量门限在高级配置中填写。
4. 校验三维 / 计算偏移：先点云取证，再测边与独立 2D–3D 校验。完整数据包按原始单位及帧契约计算；缺项给出原因，XYZ 与补偿不填零。
5. 两点校验通过后保存 XYZ 示教。后端验证签名测量结果、配方身份和已保存配置摘要；配置未保存或发生变化则拒绝。示教写入 `roi_config.dual_point_reference`，不覆盖旧标准模板。
6. 换新采集帧再校验，显示示教 / 当前机器人 XYZ、横杆实测 ΔXYZ、放置面 ΔXYZ、独立回投误差。第 3 层不补偿。所有新路径均不写 PLC。

新增 API（前缀 `/vision/api/rack-location/dual-point/`）：`forensics/` 读取当前点云；`evaluate/` 返回三维结果、补偿、取证和仅成功测量可用的示教签名；`teach/` 只接受服务端签名及同配方已保存配置。旧接口不变。

切换配方、采集/加载新帧或修改参数会清除旧结果和待保存示教，避免旧 XYZ 被误认为当前结果。保存数据包时，新模式导出四 ROI 配置和新三维诊断结果，不复用旧 A/B 结果。
