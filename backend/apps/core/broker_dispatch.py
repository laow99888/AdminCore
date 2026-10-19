"""维护/导入/导出任务入队；由 Outbox 租约及任务自身领取状态去重。"""
from apps.core.modules import module_enabled
from apps.tasks.reliability import policy

TOPICS = ('maintenance.requested', 'import.requested', 'export.requested')


def execution_for(event):
    from apps.tasks.models import MaintenanceRequest, ImportExecution
    from apps.data_io.models import BusinessExportRequest
    model = {'maintenance.requested': MaintenanceRequest, 'import.requested': ImportExecution,
             'export.requested': BusinessExportRequest}[event.topic]
    return model.objects.select_related('record').filter(pk=event.payload.get('record_id')).first()


def dispatch_policy(event, execution):
    return (execution.policy if execution else None) or policy('maintenance' if event.topic == 'maintenance.requested' else 'import')


def publish(event):
    module = 'tasks' if event.topic == 'maintenance.requested' else 'data_io'
    if not module_enabled(module):
        raise ValueError(module + '_disabled')
    execution = execution_for(event)
    if execution is None:
        raise ValueError('task_request_missing')
    if execution.record.status != 'pending':
        return
    from apps.tasks.tasks import run_maintenance
    from apps.data_io.tasks import run_data_import
    from apps.data_io.business_export import run_business_export
    task = {'maintenance.requested': run_maintenance, 'import.requested': run_data_import,
            'export.requested': run_business_export}[event.topic]
    limits = dispatch_policy(event, execution)
    task.apply_async(args=[str(execution.pk)], task_id=str(execution.pk), headers={'request_id': event.request_id},
                     soft_time_limit=limits['soft_timeout'], time_limit=limits['hard_timeout'])
