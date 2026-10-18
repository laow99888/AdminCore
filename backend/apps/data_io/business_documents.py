"""有界单工作表的整单协议；不猜测主值，不隐式创建关联对象。"""
from rest_framework.exceptions import PermissionDenied, ValidationError


def detail_catalog(schema, readable, writable):
    result = []
    for group in schema['details']:
        names = {group['name'], *(group['name'] + '.' + field['name'] for field in group['fields'])}
        # 整组替换不能抹掉隐藏字段，因此所有子字段均须可读可写，包括非表单字段。
        if names - (readable & writable):
            raise PermissionDenied('整单导入需要所有明细字段的读取和写入权限')
        result.extend({'name': group['name'] + '.' + field['name'],
                       'label': group['label'] + ' / ' + field['label'], 'kind': field['kind'],
                       'required': bool(group['min_rows'] and field['required']), 'key': False}
                      for field in group['fields'] if field['form'])
    return result


def validate_mapping(schema, mapping):
    targets = set(mapping.values())
    for group in schema['details']:
        prefix = group['name'] + '.'
        if group['min_rows'] or any(target.startswith(prefix) for target in targets):
            required = {prefix + field['name'] for field in group['fields'] if field['form'] and field['required']}
            if required - targets:
                raise ValidationError('缺少明细必填字段映射')


def group_rows(schema, rows, options):
    inverse = {target: column for column, target in options['mapping'].items()}
    key_column = inverse[options['key']]
    main_columns = [column for target, column in inverse.items() if '.' not in target]
    groups = {}
    for number, row in enumerate(rows, 2):
        key = row[key_column]
        # 空业务键不合并，以保留每一行可修正的证据。
        identity = ('key', key) if key else ('empty', number)
        if identity not in groups:
            groups[identity] = {'source_rows': [], 'source': [], 'error': ''}
        group = groups[identity]
        if group['source'] and any(row[column] != group['source'][0][column] for column in main_columns):
            group['error'] = 'inconsistent_document_fields'
        group['source_rows'].append(number)
        group['source'].append(row)
    return list(groups.values())


def document_values(schema, rows, options):
    from .business import cell_value
    inverse = {target: column for column, target in options['mapping'].items()}
    result = {field['name']: cell_value(field, rows[0][inverse[field['name']]])
              for field in schema['fields'] if field['name'] in inverse}
    for group in schema['details']:
        mapped = [(field, inverse[group['name'] + '.' + field['name']])
                  for field in group['fields'] if group['name'] + '.' + field['name'] in inverse]
        children = []
        for row in rows:
            if any(row[column] != '' for _, column in mapped):
                children.append({field['name']: cell_value(field, row[column]) for field, column in mapped})
        result[group['name']] = children
    return result
