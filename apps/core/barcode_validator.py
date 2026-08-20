"""统一条码三维校验引擎 (Barcode 3-Way Validator)

提供针对「料框码」与「产品条码」的三维严密校验：
1. 空码校验 (EMPTY)：拦截空值、全空格、占位无效字符（0, NULL, EMPTY, N/A, - 等）；
2. 格式错误校验 (FORMAT_ERROR)：校验 ASCII 字符集、合法字符范围 [A-Za-z0-9_-]、长度合规性；
3. 重复码校验 (DUPLICATE)：校验是否在当前料框、其它活跃装箱料框中重复占用，或已被标记为残次品报废。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# 无效空码占位符集合（统一转大写比较）
INVALID_EMPTY_PLACEHOLDERS = {
    '', '0', '00', '000', 'NULL', 'NONE', 'EMPTY', 'N/A', 'NA',
    '-', '--', '——', 'UNDEFINED', 'VOID', 'BLANK', '?', '???',
}

# 字符集正则表达式：仅允许字母、数字、下划线、中划线
BARCODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


class BarcodeErrorType:
    NONE = 'NONE'
    EMPTY = 'EMPTY'
    FORMAT_ERROR = 'FORMAT_ERROR'
    DUPLICATE = 'DUPLICATE'


@dataclass
class BarcodeValidationResult:
    is_valid: bool
    error_type: str
    error_message: str
    cleaned_code: str

    def raise_if_invalid(self):
        if not self.is_valid:
            raise ValueError(self.error_message)
        return self.cleaned_code


def validate_rack_barcode(
    raw_code: Optional[str],
    *,
    current_rack_id: Optional[int] = None,
    check_db_duplicate: bool = False,
) -> BarcodeValidationResult:
    """
    料框码三维校验：
    1. 空码校验：非空、非占位符
    2. 格式校验：3~32 位 ASCII，字符集 [A-Za-z0-9_-]
    3. 重复码校验：如果 check_db_duplicate 为 True，检查是否有同名冲突
    """
    code = (str(raw_code or '')).strip()

    # 1. 空码校验
    if not code or code.upper() in INVALID_EMPTY_PLACEHOLDERS:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.EMPTY,
            error_message='料框码不能为空或无效占位符（如 0、NULL、EMPTY、N/A 等）',
            cleaned_code='',
        )

    # 2. 格式校验
    if len(code) < 3:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message=f'料框码格式错误：长度至少为 3 位字符（当前输入 "{code}" 长度为 {len(code)}）',
            cleaned_code=code,
        )

    if len(code) > 32:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message=f'料框码格式错误：长度不能超过 32 位字符（当前输入长度为 {len(code)}）',
            cleaned_code=code,
        )

    try:
        code.encode('ascii')
    except UnicodeEncodeError:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message=f'料框码格式错误：必须为 ASCII 字符，不可包含中文字符或全角符号',
            cleaned_code=code,
        )

    if any(ord(c) < 33 or ord(c) == 127 for c in code):
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message='料框码格式错误：不可包含空格或不可见控制字符',
            cleaned_code=code,
        )

    if not BARCODE_PATTERN.match(code):
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message='料框码格式错误：仅支持字母、数字、短横线(-)及下划线(_)',
            cleaned_code=code,
        )

    # 3. 重复码校验（如果启用）
    if check_db_duplicate:
        from apps.production.models import Rack
        qs = Rack.objects.filter(rack_code=code)
        if current_rack_id:
            qs = qs.exclude(pk=current_rack_id)
        conflict_rack = qs.filter(status='IN_USE').first()
        if conflict_rack:
            return BarcodeValidationResult(
                is_valid=False,
                error_type=BarcodeErrorType.DUPLICATE,
                error_message=f'料框码重复：料框 {code} 当前正处于装箱占用状态中',
                cleaned_code=code,
            )

    return BarcodeValidationResult(
        is_valid=True,
        error_type=BarcodeErrorType.NONE,
        error_message='',
        cleaned_code=code,
    )


def validate_product_barcode(
    raw_code: Optional[str],
    *,
    rack_code: Optional[str] = None,
    current_product_id: Optional[int] = None,
    check_db_duplicate: bool = True,
) -> BarcodeValidationResult:
    """
    产品条码三维校验：
    1. 空码校验：非空、非占位符
    2. 格式校验：3~64 位 ASCII，字符集 [A-Za-z0-9_-]
    3. 重复码校验：检查当前料框内重复、其它料框占用、已被标记为残次品报废
    """
    code = (str(raw_code or '')).strip()

    # 1. 空码校验
    if not code or code.upper() in INVALID_EMPTY_PLACEHOLDERS:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.EMPTY,
            error_message='产品条码不能为空或无效占位符（如 0、NULL、EMPTY、N/A 等）',
            cleaned_code='',
        )

    # 2. 格式校验
    if len(code) < 3:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message=f'产品条码格式错误：长度至少为 3 位字符（当前输入 "{code}" 长度为 {len(code)}）',
            cleaned_code=code,
        )

    if len(code) > 64:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message=f'产品条码格式错误：长度不能超过 64 位字符（当前输入长度为 {len(code)}）',
            cleaned_code=code,
        )

    try:
        code.encode('ascii')
    except UnicodeEncodeError:
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message='产品条码格式错误：必须为 ASCII 字符，不可包含中文字符或全角符号',
            cleaned_code=code,
        )

    if any(ord(c) < 33 or ord(c) == 127 for c in code):
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message='产品条码格式错误：不可包含空格或不可见控制字符',
            cleaned_code=code,
        )

    if not BARCODE_PATTERN.match(code):
        return BarcodeValidationResult(
            is_valid=False,
            error_type=BarcodeErrorType.FORMAT_ERROR,
            error_message='产品条码格式错误：仅支持字母、数字、短横线(-)及下划线(_)',
            cleaned_code=code,
        )

    # 3. 重复码校验（检查数据库记录与残次品状态）
    if check_db_duplicate:
        from apps.production.models import Product
        qs = Product.objects.filter(product_code=code)
        if current_product_id:
            qs = qs.exclude(pk=current_product_id)

        existing = qs.first()
        if existing:
            # 3.1 检查是否已被标记为残次品/报废
            if existing.is_defective:
                return BarcodeValidationResult(
                    is_valid=False,
                    error_type=BarcodeErrorType.DUPLICATE,
                    error_message=f'产品条码冲突：条码 {code} 已于 {existing.defect_at.strftime("%Y-%m-%d %H:%M") if existing.defect_at else "此前"} 被标记为残次品/报废（原因：{existing.defect_reason or "未注明"}），不可重复作为合格品使用',
                    cleaned_code=code,
                )

            # 3.2 检查是否已被其它料框绑定
            if existing.rack and (not rack_code or existing.rack.rack_code != rack_code):
                return BarcodeValidationResult(
                    is_valid=False,
                    error_type=BarcodeErrorType.DUPLICATE,
                    error_message=f'产品条码冲突：产品 {code} 已绑定在料框 {existing.rack.rack_code} 中，不可重复绑定',
                    cleaned_code=code,
                )

            # 3.3 检查是否已在当前料框存在重复
            if rack_code and existing.rack and existing.rack.rack_code == rack_code:
                return BarcodeValidationResult(
                    is_valid=False,
                    error_type=BarcodeErrorType.DUPLICATE,
                    error_message=f'产品条码重复：当前料框 {rack_code} 中已存在该产品条码 {code}',
                    cleaned_code=code,
                )

    return BarcodeValidationResult(
        is_valid=True,
        error_type=BarcodeErrorType.NONE,
        error_message='',
        cleaned_code=code,
    )
