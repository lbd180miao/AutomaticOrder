"""流程状态机：集中定义并校验主流程状态转换。

状态转换必须通过本模块校验，业务编排在 workflow.services 中完成。
"""
from apps.core.constants import WorkflowState as W


class WorkflowStateMachine:
    """Central place for validating workflow transitions."""

    # 正常的线性主流程 + 异常分支（任意非终止状态可进入 LOCKED / FAILED）。
    allowed_transitions = {
        W.CREATED: {W.INJECTION_PICKED},
        W.INJECTION_PICKED: {W.MARKING_READY},
        W.MARKING_READY: {W.MARKED},
        W.MARKED: {W.BARCODE_READ},
        W.BARCODE_READ: {W.MES_UPLOADED},
        W.MES_UPLOADED: {W.HANDOVER_WAITING},
        W.HANDOVER_WAITING: {W.HANDOVER_ROBOT_READY},
        W.HANDOVER_ROBOT_READY: {W.HANDOVER_GRIPPED},
        W.HANDOVER_GRIPPED: {W.INJECTION_RELEASED},
        W.INJECTION_RELEASED: {W.RACK_SCANNED},
        W.RACK_SCANNED: {W.RECIPE_LOADED},
        W.RECIPE_LOADED: {W.RACK_LOCATING},
        W.RACK_LOCATING: {W.RACK_LOCATED},
        W.RACK_LOCATED: {W.RECIPE_VERIFIED},
        W.RECIPE_VERIFIED: {W.BOXING},
        W.BOXING: {W.FOAM_PICKING},
        W.FOAM_PICKING: {W.FOAM_ATTACHING},
        W.FOAM_ATTACHING: {W.FOAM_INSPECTING},
        # 泡棉检测后：合格则完成，不合格则锁定；也可回到装箱进入下一循环。
        W.FOAM_INSPECTING: {W.COMPLETED, W.BOXING, W.LOCKED},
        # 锁定后人工解除可回到锁定前的处理，或判定失败。
        W.LOCKED: {W.FAILED},
        W.COMPLETED: set(),
        W.FAILED: set(),
    }

    # 这些异常目标状态可从任意非终止状态进入。
    universal_targets = {W.LOCKED, W.FAILED}

    def next_state(self, from_state):
        """返回正常流程的下一个主状态（取第一个非异常目标）。"""
        targets = self.allowed_transitions.get(from_state, set())
        normal = [t for t in targets if t not in self.universal_targets]
        return normal[0] if normal else None

    def can_transition(self, from_state, to_state):
        if from_state in (W.COMPLETED, W.FAILED):
            return False
        if to_state in self.universal_targets:
            return True
        return to_state in self.allowed_transitions.get(from_state, set())
