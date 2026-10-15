"""不属于可选模块的安全/可靠事件维护任务。"""
CORE_TASKS = {
    'core.dispatch_outbox': (),
    'core.cleanup_expired_idempotency': (),
    'core.cleanup_expired_sessions': (),
}
