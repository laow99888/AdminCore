from apps.core.modules import module_enabled

# Closed server registry. Adding a scope requires a separately reviewed route and DTO.
SCOPES = {'task:read': ('tasks', '读取任务摘要'), 'example:read': ('example', '读取示例工单')}
MAX_ACTIVE_CREDENTIALS = 20
REQUESTS_PER_MINUTE = 60


def available_scopes():
    return {code: label for code, (module, label) in SCOPES.items() if module_enabled(module)}
