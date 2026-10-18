"""有限十进制运算协议。只处理规范化数据；不解析/执行代码或表达式文本。"""
import re
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext

from rest_framework.exceptions import ValidationError


def invalid():
    raise ValidationError('计算配置无效，请使用先前的金额字段或明细金额列')


def normalize_computation(value, previous):
    if not isinstance(value, dict) or not isinstance(value.get('op'), str):
        invalid()
    if value['op'] == 'sum':
        if set(value) != {'op', 'detail', 'field'} or not all(isinstance(value[key], str) for key in ('detail', 'field')):
            invalid()
        detail = previous.get(value['detail'])
        if not detail or detail['type'] != 'detail' or not any(field['key'] == value['field'] and field['type'] == 'decimal' for field in detail['fields']):
            invalid()
        return {'op': 'sum', 'detail': value['detail'], 'field': value['field']}
    if set(value) != {'op', 'operands'} or value['op'] not in {'add', 'subtract', 'multiply', 'divide'} or not isinstance(value['operands'], list) or len(value['operands']) != 2:
        invalid()
    operands = []
    for operand in value['operands']:
        if not isinstance(operand, dict):
            invalid()
        if set(operand) == {'field'}:
            key = operand['field']
            if not isinstance(key, str) or key not in previous or previous[key]['type'] != 'decimal':
                invalid()
            operands.append({'field': key})
        elif set(operand) == {'literal'}:
            raw = operand['literal']
            if not isinstance(raw, str) or not re.fullmatch(r'-?[0-9]{1,18}(?:\.[0-9]{1,8})?', raw) or len(Decimal(raw).as_tuple().digits) > 18:
                invalid()
            operands.append({'literal': raw})
        else:
            invalid()
    return {'op': value['op'], 'operands': operands}


def calculate(computation, data, scale):
    """来源缺失不补零。非空明细逐行缺列也不能悄悄低估汇总。"""
    with localcontext() as context:
        context.prec = 64
        try:
            if computation['op'] == 'sum':
                rows = data.get(computation['detail'])
                if not rows or any(computation['field'] not in row for row in rows):
                    return None
                result = sum((Decimal(row[computation['field']]) for row in rows), Decimal(0))
            else:
                operands = [data.get(operand['field']) if 'field' in operand else operand['literal'] for operand in computation['operands']]
                if any(value is None for value in operands):
                    return None
                left, right = map(Decimal, operands)
                op = computation['op']
                if op == 'divide' and right == 0:
                    raise ValidationError('计算字段不能除以零')
                if op == 'add':
                    result = left + right
                elif op == 'subtract':
                    result = left - right
                elif op == 'multiply':
                    result = left * right
                else:
                    result = left / right
            result = result.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
            if not result.is_finite() or len(result.as_tuple().digits) > 18:
                raise ValidationError('计算结果超出金额精度限制')
            return format(abs(result) if result == 0 else result, f'.{scale}f')
        except DecimalException:
            raise ValidationError('计算结果超出金额精度限制') from None
