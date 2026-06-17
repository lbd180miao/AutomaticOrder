from django.db import models


class WorkflowState(models.TextChoices):
    CREATED = 'CREATED', '已创建'
    INJECTION_PICKED = 'INJECTION_PICKED', '注塑已取件'
    MARKING_READY = 'MARKING_READY', '已到打标位'
    MARKED = 'MARKED', '已打标'
    BARCODE_READ = 'BARCODE_READ', '条码已读取'
    MES_UPLOADED = 'MES_UPLOADED', 'MES已上传'
    HANDOVER_WAITING = 'HANDOVER_WAITING', '待交接'
    HANDOVER_ROBOT_READY = 'HANDOVER_ROBOT_READY', '装箱机器人已就绪'
    HANDOVER_GRIPPED = 'HANDOVER_GRIPPED', '装箱机器人已抓牢'
    INJECTION_RELEASED = 'INJECTION_RELEASED', '注塑机器人已释放'
    RACK_SCANNED = 'RACK_SCANNED', '料框已扫码'
    RECIPE_LOADED = 'RECIPE_LOADED', '配方已加载'
    RACK_LOCATING = 'RACK_LOCATING', '料架定位中'
    RACK_LOCATED = 'RACK_LOCATED', '料架定位完成'
    RECIPE_VERIFIED = 'RECIPE_VERIFIED', '配方校验通过'
    BOXING = 'BOXING', '装箱中'
    FOAM_PICKING = 'FOAM_PICKING', '泡棉抓取中'
    FOAM_ATTACHING = 'FOAM_ATTACHING', '泡棉贴附中'
    FOAM_INSPECTING = 'FOAM_INSPECTING', '泡棉检测中'
    COMPLETED = 'COMPLETED', '工序完成'
    LOCKED = 'LOCKED', '异常锁定'
    FAILED = 'FAILED', '流程失败'


class ResultStatus(models.TextChoices):
    PENDING = 'PENDING', '待处理'
    RUNNING = 'RUNNING', '执行中'
    SUCCESS = 'SUCCESS', '成功'
    FAILED = 'FAILED', '失败'


class Stage(models.TextChoices):
    """主流程的三个阶段。"""

    STAGE_ONE = 'STAGE_ONE', '阶段一-注塑下线与打标'
    STAGE_TWO = 'STAGE_TWO', '阶段二-空中交接'
    STAGE_THREE = 'STAGE_THREE', '阶段三-视觉装箱与泡棉'
    DONE = 'DONE', '已完成'


class EventSource(models.TextChoices):
    """流程事件来源。"""

    PLC = 'PLC', 'PLC'
    MES = 'MES', 'MES'
    VISION = 'VISION', '视觉'
    OPERATOR = 'OPERATOR', '人工'
    SYSTEM = 'SYSTEM', '系统'


class MarkStatus(models.TextChoices):
    PENDING = 'PENDING', '待打标'
    MARKED = 'MARKED', '已打标'
    FAILED = 'FAILED', '打标失败'


class MesUploadStatus(models.TextChoices):
    PENDING = 'PENDING', '待上传'
    UPLOADED = 'UPLOADED', '已上传'
    FAILED = 'FAILED', '上传失败'


class DeviceStatus(models.TextChoices):
    ONLINE = 'ONLINE', '在线'
    OFFLINE = 'OFFLINE', '离线'
    ALARM = 'ALARM', '报警'
    DISABLED = 'DISABLED', '禁用'
    UNKNOWN = 'UNKNOWN', '未知'


class DeviceType(models.TextChoices):
    PLC = 'PLC', 'PLC'
    INJECTION_ROBOT = 'INJECTION_ROBOT', '注塑取件机器人'
    BOXING_ROBOT = 'BOXING_ROBOT', '装箱机器人'
    SCANNER = 'SCANNER', '扫码枪'
    DEPTH_CAMERA = 'DEPTH_CAMERA', '深度相机'
    INSPECT_CAMERA = 'INSPECT_CAMERA', '固定检测相机'
    LASER_MARKER = 'LASER_MARKER', '激光打标机'
    FOAM_SENSOR = 'FOAM_SENSOR', '泡棉距离传感器'


class SignalDirection(models.TextChoices):
    IN = 'IN', '输入'
    OUT = 'OUT', '输出'


class AlarmLevel(models.TextChoices):
    INFO = 'INFO', '提示'
    WARNING = 'WARNING', '警告'
    ERROR = 'ERROR', '错误'
    CRITICAL = 'CRITICAL', '严重'


class AlarmStatus(models.TextChoices):
    OPEN = 'OPEN', '新建'
    ACKNOWLEDGED = 'ACKNOWLEDGED', '已确认'
    CLOSED = 'CLOSED', '已关闭'


class AlarmSource(models.TextChoices):
    DEVICE = 'DEVICE', '设备通讯'
    SCANNER = 'SCANNER', '扫码'
    MES = 'MES', 'MES'
    VISION = 'VISION', '视觉检测'
    WORKFLOW = 'WORKFLOW', '流程超时'
    RECIPE = 'RECIPE', '配置校验'
    OPERATOR = 'OPERATOR', '人工'


class VisionTaskType(models.TextChoices):
    RACK_LOCATING = 'RACK_LOCATING', '料架定位'
    FOAM_INSPECTION = 'FOAM_INSPECTION', '泡棉检测'
    SCAN_ASSIST = 'SCAN_ASSIST', '扫码辅助'


class RackSide(models.TextChoices):
    LEFT = 'LEFT', '左侧'
    RIGHT = 'RIGHT', '右侧'
    BOTH = 'BOTH', '双侧'


class MesAction(models.TextChoices):
    GET_RACK_RECIPE = 'GET_RACK_RECIPE', '获取料架配方'
    UPLOAD_PRODUCT_BARCODE = 'UPLOAD_PRODUCT_BARCODE', '上传产品条码'
    UPLOAD_BOXING_RESULT = 'UPLOAD_BOXING_RESULT', '上传装箱结果'
    UPLOAD_VISION_RESULT = 'UPLOAD_VISION_RESULT', '上传视觉结果'
    UPLOAD_ALARM = 'UPLOAD_ALARM', '上传报警'


class VisionImageType(models.TextChoices):
    ORIGINAL = 'ORIGINAL', '原图'
    DEPTH = 'DEPTH', '深度图'
    RESULT = 'RESULT', '结果图'


# 阶段一各状态归属阶段映射，供 dashboard / 流程页展示阶段进度使用。
STATE_STAGE_MAP = {
    WorkflowState.CREATED: Stage.STAGE_ONE,
    WorkflowState.INJECTION_PICKED: Stage.STAGE_ONE,
    WorkflowState.MARKING_READY: Stage.STAGE_ONE,
    WorkflowState.MARKED: Stage.STAGE_ONE,
    WorkflowState.BARCODE_READ: Stage.STAGE_ONE,
    WorkflowState.MES_UPLOADED: Stage.STAGE_ONE,
    WorkflowState.HANDOVER_WAITING: Stage.STAGE_TWO,
    WorkflowState.HANDOVER_ROBOT_READY: Stage.STAGE_TWO,
    WorkflowState.HANDOVER_GRIPPED: Stage.STAGE_TWO,
    WorkflowState.INJECTION_RELEASED: Stage.STAGE_TWO,
    WorkflowState.RACK_SCANNED: Stage.STAGE_THREE,
    WorkflowState.RECIPE_LOADED: Stage.STAGE_THREE,
    WorkflowState.RACK_LOCATING: Stage.STAGE_THREE,
    WorkflowState.RACK_LOCATED: Stage.STAGE_THREE,
    WorkflowState.RECIPE_VERIFIED: Stage.STAGE_THREE,
    WorkflowState.BOXING: Stage.STAGE_THREE,
    WorkflowState.FOAM_PICKING: Stage.STAGE_THREE,
    WorkflowState.FOAM_ATTACHING: Stage.STAGE_THREE,
    WorkflowState.FOAM_INSPECTING: Stage.STAGE_THREE,
    WorkflowState.COMPLETED: Stage.DONE,
}

# 终止状态，不可再正常推进。
TERMINAL_STATES = {WorkflowState.COMPLETED, WorkflowState.FAILED}
