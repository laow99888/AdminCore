// 自动生成，请运行 npm run sdk:generate，勿手工修改。
import type { operations } from './schema'

export const sdkRoutes = {
  "api_credentials_credentials_list": [
    "get",
    "/api/v1/api-credentials/credentials/"
  ],
  "api_credentials_credentials_create": [
    "post",
    "/api/v1/api-credentials/credentials/"
  ],
  "api_credentials_credentials_scopes_retrieve": [
    "get",
    "/api/v1/api-credentials/credentials/scopes/"
  ],
  "api_credentials_credentials_revoke_create": [
    "post",
    "/api/v1/api-credentials/credentials/{id}/revoke/"
  ],
  "api_credentials_tasks_list": [
    "get",
    "/api/v1/api-credentials/tasks/"
  ],
  "api_credentials_tasks_retrieve": [
    "get",
    "/api/v1/api-credentials/tasks/{id}/"
  ],
  "api_credentials_work_items_list": [
    "get",
    "/api/v1/api-credentials/work-items/"
  ],
  "api_credentials_work_items_retrieve": [
    "get",
    "/api/v1/api-credentials/work-items/{id}/"
  ],
  "approvals_list": [
    "get",
    "/api/v1/approvals/"
  ],
  "approvals_create": [
    "post",
    "/api/v1/approvals/"
  ],
  "approvals_assignee_departments_retrieve": [
    "get",
    "/api/v1/approvals/assignee-departments/"
  ],
  "approvals_assignees_retrieve": [
    "get",
    "/api/v1/approvals/assignees/"
  ],
  "approvals_retrieve": [
    "get",
    "/api/v1/approvals/{id}/"
  ],
  "approvals_approve_create": [
    "post",
    "/api/v1/approvals/{id}/approve/"
  ],
  "approvals_cancel_create": [
    "post",
    "/api/v1/approvals/{id}/cancel/"
  ],
  "approvals_reject_create": [
    "post",
    "/api/v1/approvals/{id}/reject/"
  ],
  "auth_avatar_destroy": [
    "delete",
    "/api/v1/auth/avatar/"
  ],
  "auth_avatar_retrieve": [
    "get",
    "/api/v1/auth/avatar/"
  ],
  "auth_avatar_create": [
    "post",
    "/api/v1/auth/avatar/"
  ],
  "auth_change_password_create": [
    "post",
    "/api/v1/auth/change_password/"
  ],
  "auth_email_verification_confirm_create": [
    "post",
    "/api/v1/auth/email-verification/confirm/"
  ],
  "auth_email_verification_request_create": [
    "post",
    "/api/v1/auth/email-verification/request/"
  ],
  "auth_login_captcha_create": [
    "post",
    "/api/v1/auth/login-captcha/"
  ],
  "auth_login_create": [
    "post",
    "/api/v1/auth/login/"
  ],
  "auth_logout_create": [
    "post",
    "/api/v1/auth/logout/"
  ],
  "auth_me_retrieve": [
    "get",
    "/api/v1/auth/me/"
  ],
  "auth_online_users_list": [
    "get",
    "/api/v1/auth/online-users/"
  ],
  "auth_online_users_revoke_create": [
    "post",
    "/api/v1/auth/online-users/{id}/revoke/"
  ],
  "auth_profile_retrieve": [
    "get",
    "/api/v1/auth/profile/"
  ],
  "auth_profile_partial_update": [
    "patch",
    "/api/v1/auth/profile/"
  ],
  "auth_recovery_config_retrieve": [
    "get",
    "/api/v1/auth/recovery/config/"
  ],
  "auth_recovery_request_create": [
    "post",
    "/api/v1/auth/recovery/request/"
  ],
  "auth_recovery_reset_create": [
    "post",
    "/api/v1/auth/recovery/reset/"
  ],
  "auth_refresh_create": [
    "post",
    "/api/v1/auth/refresh/"
  ],
  "auth_register_create": [
    "post",
    "/api/v1/auth/register/"
  ],
  "auth_sessions_list": [
    "get",
    "/api/v1/auth/sessions/"
  ],
  "auth_sessions_destroy": [
    "delete",
    "/api/v1/auth/sessions/{id}/"
  ],
  "auth_totp_retrieve": [
    "get",
    "/api/v1/auth/totp/"
  ],
  "auth_totp_disable_retrieve": [
    "get",
    "/api/v1/auth/totp/disable/"
  ],
  "auth_totp_disable_create": [
    "post",
    "/api/v1/auth/totp/disable/"
  ],
  "auth_totp_enable_retrieve": [
    "get",
    "/api/v1/auth/totp/enable/"
  ],
  "auth_totp_enable_create": [
    "post",
    "/api/v1/auth/totp/enable/"
  ],
  "auth_totp_recovery_codes_retrieve": [
    "get",
    "/api/v1/auth/totp/recovery-codes/"
  ],
  "auth_totp_recovery_codes_create": [
    "post",
    "/api/v1/auth/totp/recovery-codes/"
  ],
  "auth_totp_setup_retrieve": [
    "get",
    "/api/v1/auth/totp/setup/"
  ],
  "auth_totp_setup_create": [
    "post",
    "/api/v1/auth/totp/setup/"
  ],
  "brand_retrieve": [
    "get",
    "/api/v1/brand/"
  ],
  "dashboard_stats_retrieve": [
    "get",
    "/api/v1/dashboard/stats/"
  ],
  "data_io_export_retrieve": [
    "get",
    "/api/v1/data-io/export/"
  ],
  "data_io_import_create": [
    "post",
    "/api/v1/data-io/import/"
  ],
  "data_io_import_retrieve": [
    "get",
    "/api/v1/data-io/import/{task_id}/"
  ],
  "data_io_import_retry": [
    "post",
    "/api/v1/data-io/import/{task_id}/"
  ],
  "data_io_resources_retrieve": [
    "get",
    "/api/v1/data-io/resources/"
  ],
  "data_io_template_retrieve": [
    "get",
    "/api/v1/data-io/template/"
  ],
  "example_items_list": [
    "get",
    "/api/v1/example/items/"
  ],
  "example_items_create": [
    "post",
    "/api/v1/example/items/"
  ],
  "example_items_destroy": [
    "delete",
    "/api/v1/example/items/{id}/"
  ],
  "example_items_retrieve": [
    "get",
    "/api/v1/example/items/{id}/"
  ],
  "example_items_partial_update": [
    "patch",
    "/api/v1/example/items/{id}/"
  ],
  "example_items_update": [
    "put",
    "/api/v1/example/items/{id}/"
  ],
  "feature_flags_evaluate_create": [
    "post",
    "/api/v1/feature-flags/evaluate/"
  ],
  "feature_flags_flags_list": [
    "get",
    "/api/v1/feature-flags/flags/"
  ],
  "feature_flags_flags_create": [
    "post",
    "/api/v1/feature-flags/flags/"
  ],
  "feature_flags_flags_destroy": [
    "delete",
    "/api/v1/feature-flags/flags/{id}/"
  ],
  "feature_flags_flags_retrieve": [
    "get",
    "/api/v1/feature-flags/flags/{id}/"
  ],
  "feature_flags_flags_partial_update": [
    "patch",
    "/api/v1/feature-flags/flags/{id}/"
  ],
  "feature_flags_targets_retrieve": [
    "get",
    "/api/v1/feature-flags/targets/"
  ],
  "files_list": [
    "get",
    "/api/v1/files/"
  ],
  "files_create": [
    "post",
    "/api/v1/files/"
  ],
  "files_office_preview_config_retrieve": [
    "get",
    "/api/v1/files/office-preview/config/"
  ],
  "files_office_preview_jobs_destroy": [
    "delete",
    "/api/v1/files/office-preview/jobs/{job_id}/"
  ],
  "files_office_preview_jobs_retrieve": [
    "get",
    "/api/v1/files/office-preview/jobs/{job_id}/"
  ],
  "files_office_preview_jobs_pdf_retrieve": [
    "get",
    "/api/v1/files/office-preview/jobs/{job_id}/pdf/"
  ],
  "files_processing_config_retrieve": [
    "get",
    "/api/v1/files/processing_config/"
  ],
  "files_recycle_list": [
    "get",
    "/api/v1/files/recycle/"
  ],
  "files_recycle_action_create": [
    "post",
    "/api/v1/files/recycle_action/"
  ],
  "files_recycle_policy_retrieve": [
    "get",
    "/api/v1/files/recycle_policy/"
  ],
  "files_office_preview_create": [
    "post",
    "/api/v1/files/{file_id}/office-preview/"
  ],
  "files_destroy": [
    "delete",
    "/api/v1/files/{id}/"
  ],
  "files_retrieve": [
    "get",
    "/api/v1/files/{id}/"
  ],
  "files_download_retrieve": [
    "get",
    "/api/v1/files/{id}/download/"
  ],
  "files_preview_retrieve": [
    "get",
    "/api/v1/files/{id}/preview/"
  ],
  "files_purge_destroy": [
    "delete",
    "/api/v1/files/{id}/purge/"
  ],
  "files_restore_create": [
    "post",
    "/api/v1/files/{id}/restore/"
  ],
  "files_transform_create": [
    "post",
    "/api/v1/files/{id}/transform/"
  ],
  "ip_policy_retrieve": [
    "get",
    "/api/v1/ip-policy/"
  ],
  "ip_policy_update": [
    "put",
    "/api/v1/ip-policy/"
  ],
  "ip_policy_preview_create": [
    "post",
    "/api/v1/ip-policy/preview/"
  ],
  "logs_exception_list": [
    "get",
    "/api/v1/logs/exception/"
  ],
  "logs_exception_retrieve": [
    "get",
    "/api/v1/logs/exception/{id}/"
  ],
  "logs_login_list": [
    "get",
    "/api/v1/logs/login/"
  ],
  "logs_login_retrieve": [
    "get",
    "/api/v1/logs/login/{id}/"
  ],
  "logs_operation_list": [
    "get",
    "/api/v1/logs/operation/"
  ],
  "logs_operation_retrieve": [
    "get",
    "/api/v1/logs/operation/{id}/"
  ],
  "modules_retrieve": [
    "get",
    "/api/v1/modules/"
  ],
  "notifications_list": [
    "get",
    "/api/v1/notifications/"
  ],
  "notifications_create": [
    "post",
    "/api/v1/notifications/"
  ],
  "notifications_announcements_list": [
    "get",
    "/api/v1/notifications/announcements/"
  ],
  "notifications_announcements_manage_list": [
    "get",
    "/api/v1/notifications/announcements/manage/"
  ],
  "notifications_announcements_manage_create": [
    "post",
    "/api/v1/notifications/announcements/manage/"
  ],
  "notifications_announcements_manage_retrieve": [
    "get",
    "/api/v1/notifications/announcements/manage/{id}/"
  ],
  "notifications_announcements_manage_partial_update": [
    "patch",
    "/api/v1/notifications/announcements/manage/{id}/"
  ],
  "notifications_announcements_manage_publish_create": [
    "post",
    "/api/v1/notifications/announcements/manage/{id}/publish/"
  ],
  "notifications_announcements_manage_withdraw_create": [
    "post",
    "/api/v1/notifications/announcements/manage/{id}/withdraw/"
  ],
  "notifications_announcements_retrieve": [
    "get",
    "/api/v1/notifications/announcements/{id}/"
  ],
  "notifications_deliveries_list": [
    "get",
    "/api/v1/notifications/deliveries/"
  ],
  "notifications_deliveries_create": [
    "post",
    "/api/v1/notifications/deliveries/"
  ],
  "notifications_deliveries_destroy": [
    "delete",
    "/api/v1/notifications/deliveries/{id}/"
  ],
  "notifications_deliveries_retrieve": [
    "get",
    "/api/v1/notifications/deliveries/{id}/"
  ],
  "notifications_deliveries_update": [
    "put",
    "/api/v1/notifications/deliveries/{id}/"
  ],
  "notifications_deliveries_retry_create": [
    "post",
    "/api/v1/notifications/deliveries/{id}/retry/"
  ],
  "notifications_mark_all_read_create": [
    "post",
    "/api/v1/notifications/mark_all_read/"
  ],
  "notifications_templates_list": [
    "get",
    "/api/v1/notifications/templates/"
  ],
  "notifications_templates_create": [
    "post",
    "/api/v1/notifications/templates/"
  ],
  "notifications_templates_channels_retrieve": [
    "get",
    "/api/v1/notifications/templates/channels/"
  ],
  "notifications_templates_recipient_departments_retrieve": [
    "get",
    "/api/v1/notifications/templates/recipient-departments/"
  ],
  "notifications_templates_recipients_retrieve": [
    "get",
    "/api/v1/notifications/templates/recipients/"
  ],
  "notifications_templates_retrieve": [
    "get",
    "/api/v1/notifications/templates/{id}/"
  ],
  "notifications_templates_partial_update": [
    "patch",
    "/api/v1/notifications/templates/{id}/"
  ],
  "notifications_templates_preview_create": [
    "post",
    "/api/v1/notifications/templates/{id}/preview/"
  ],
  "notifications_templates_send_create": [
    "post",
    "/api/v1/notifications/templates/{id}/send/"
  ],
  "notifications_templates_versions_retrieve": [
    "get",
    "/api/v1/notifications/templates/{id}/versions/"
  ],
  "notifications_unread_count_retrieve": [
    "get",
    "/api/v1/notifications/unread_count/"
  ],
  "notifications_retrieve": [
    "get",
    "/api/v1/notifications/{id}/"
  ],
  "notifications_mark_read_create": [
    "post",
    "/api/v1/notifications/{id}/mark_read/"
  ],
  "organization_departments_list": [
    "get",
    "/api/v1/organization/departments/"
  ],
  "organization_departments_create": [
    "post",
    "/api/v1/organization/departments/"
  ],
  "organization_departments_destroy": [
    "delete",
    "/api/v1/organization/departments/{id}/"
  ],
  "organization_departments_retrieve": [
    "get",
    "/api/v1/organization/departments/{id}/"
  ],
  "organization_departments_partial_update": [
    "patch",
    "/api/v1/organization/departments/{id}/"
  ],
  "organization_departments_update": [
    "put",
    "/api/v1/organization/departments/{id}/"
  ],
  "organization_memberships_list": [
    "get",
    "/api/v1/organization/memberships/"
  ],
  "organization_memberships_create": [
    "post",
    "/api/v1/organization/memberships/"
  ],
  "organization_memberships_destroy": [
    "delete",
    "/api/v1/organization/memberships/{id}/"
  ],
  "organization_memberships_retrieve": [
    "get",
    "/api/v1/organization/memberships/{id}/"
  ],
  "organization_memberships_partial_update": [
    "patch",
    "/api/v1/organization/memberships/{id}/"
  ],
  "organization_memberships_update": [
    "put",
    "/api/v1/organization/memberships/{id}/"
  ],
  "organization_people_retrieve": [
    "get",
    "/api/v1/organization/people/"
  ],
  "organization_people_departments_retrieve": [
    "get",
    "/api/v1/organization/people/departments/"
  ],
  "organization_posts_list": [
    "get",
    "/api/v1/organization/posts/"
  ],
  "organization_posts_create": [
    "post",
    "/api/v1/organization/posts/"
  ],
  "organization_posts_choices_retrieve": [
    "get",
    "/api/v1/organization/posts/choices/"
  ],
  "organization_posts_destroy": [
    "delete",
    "/api/v1/organization/posts/{id}/"
  ],
  "organization_posts_retrieve": [
    "get",
    "/api/v1/organization/posts/{id}/"
  ],
  "organization_posts_partial_update": [
    "patch",
    "/api/v1/organization/posts/{id}/"
  ],
  "organization_posts_update": [
    "put",
    "/api/v1/organization/posts/{id}/"
  ],
  "organization_scopes_list": [
    "get",
    "/api/v1/organization/scopes/"
  ],
  "organization_scopes_create": [
    "post",
    "/api/v1/organization/scopes/"
  ],
  "organization_scopes_retrieve": [
    "get",
    "/api/v1/organization/scopes/{id}/"
  ],
  "organization_scopes_partial_update": [
    "patch",
    "/api/v1/organization/scopes/{id}/"
  ],
  "organization_scopes_update": [
    "put",
    "/api/v1/organization/scopes/{id}/"
  ],
  "organization_user_posts_list": [
    "get",
    "/api/v1/organization/user-posts/"
  ],
  "organization_user_posts_create": [
    "post",
    "/api/v1/organization/user-posts/"
  ],
  "organization_user_posts_destroy": [
    "delete",
    "/api/v1/organization/user-posts/{id}/"
  ],
  "organization_user_posts_retrieve": [
    "get",
    "/api/v1/organization/user-posts/{id}/"
  ],
  "permissions_menus_list": [
    "get",
    "/api/v1/permissions/menus/"
  ],
  "permissions_menus_create": [
    "post",
    "/api/v1/permissions/menus/"
  ],
  "permissions_menus_my_menu_retrieve": [
    "get",
    "/api/v1/permissions/menus/my_menu/"
  ],
  "permissions_menus_destroy": [
    "delete",
    "/api/v1/permissions/menus/{id}/"
  ],
  "permissions_menus_retrieve": [
    "get",
    "/api/v1/permissions/menus/{id}/"
  ],
  "permissions_menus_partial_update": [
    "patch",
    "/api/v1/permissions/menus/{id}/"
  ],
  "permissions_menus_update": [
    "put",
    "/api/v1/permissions/menus/{id}/"
  ],
  "permissions_permissions_list": [
    "get",
    "/api/v1/permissions/permissions/"
  ],
  "permissions_permissions_create": [
    "post",
    "/api/v1/permissions/permissions/"
  ],
  "permissions_permissions_destroy": [
    "delete",
    "/api/v1/permissions/permissions/{id}/"
  ],
  "permissions_permissions_retrieve": [
    "get",
    "/api/v1/permissions/permissions/{id}/"
  ],
  "permissions_permissions_update": [
    "put",
    "/api/v1/permissions/permissions/{id}/"
  ],
  "permissions_roles_list": [
    "get",
    "/api/v1/permissions/roles/"
  ],
  "permissions_roles_create": [
    "post",
    "/api/v1/permissions/roles/"
  ],
  "permissions_roles_destroy": [
    "delete",
    "/api/v1/permissions/roles/{id}/"
  ],
  "permissions_roles_retrieve": [
    "get",
    "/api/v1/permissions/roles/{id}/"
  ],
  "permissions_roles_partial_update": [
    "patch",
    "/api/v1/permissions/roles/{id}/"
  ],
  "permissions_roles_update": [
    "put",
    "/api/v1/permissions/roles/{id}/"
  ],
  "reliability_events_list": [
    "get",
    "/api/v1/reliability/events/"
  ],
  "reliability_events_create": [
    "post",
    "/api/v1/reliability/events/"
  ],
  "reliability_events_destroy": [
    "delete",
    "/api/v1/reliability/events/{id}/"
  ],
  "reliability_events_retrieve": [
    "get",
    "/api/v1/reliability/events/{id}/"
  ],
  "reliability_events_update": [
    "put",
    "/api/v1/reliability/events/{id}/"
  ],
  "reliability_events_retry_create": [
    "post",
    "/api/v1/reliability/events/{id}/retry/"
  ],
  "schema_retrieve": [
    "get",
    "/api/v1/schema/"
  ],
  "sso_callback_retrieve": [
    "get",
    "/api/v1/sso/callback/"
  ],
  "sso_cancel_create": [
    "post",
    "/api/v1/sso/cancel/"
  ],
  "sso_complete_create": [
    "post",
    "/api/v1/sso/complete/"
  ],
  "sso_config_retrieve": [
    "get",
    "/api/v1/sso/config/"
  ],
  "sso_identities_list": [
    "get",
    "/api/v1/sso/identities/"
  ],
  "sso_identities_create": [
    "post",
    "/api/v1/sso/identities/"
  ],
  "sso_identities_unbind_create": [
    "post",
    "/api/v1/sso/identities/{id}/unbind/"
  ],
  "sso_start_create": [
    "post",
    "/api/v1/sso/start/"
  ],
  "sso_status_retrieve": [
    "get",
    "/api/v1/sso/status/"
  ],
  "system_cache_retrieve": [
    "get",
    "/api/v1/system/cache/"
  ],
  "system_cache_clear_create": [
    "post",
    "/api/v1/system/cache/clear/"
  ],
  "system_cache_preview_create": [
    "post",
    "/api/v1/system/cache/preview/"
  ],
  "system_config_list": [
    "get",
    "/api/v1/system/config/"
  ],
  "system_config_detail": [
    "get",
    "/api/v1/system/config/{key}/"
  ],
  "system_config_write": [
    "patch",
    "/api/v1/system/config/{key}/"
  ],
  "system_dictionaries_list": [
    "get",
    "/api/v1/system/dictionaries/"
  ],
  "system_dictionaries_create": [
    "post",
    "/api/v1/system/dictionaries/"
  ],
  "system_dictionaries_options_retrieve": [
    "get",
    "/api/v1/system/dictionaries/options/{code}/"
  ],
  "system_dictionaries_retrieve": [
    "get",
    "/api/v1/system/dictionaries/{id}/"
  ],
  "system_dictionaries_partial_update": [
    "patch",
    "/api/v1/system/dictionaries/{id}/"
  ],
  "system_dictionaries_update": [
    "put",
    "/api/v1/system/dictionaries/{id}/"
  ],
  "system_information_retrieve": [
    "get",
    "/api/v1/system/information/"
  ],
  "system_monitor_retrieve": [
    "get",
    "/api/v1/system/monitor/"
  ],
  "tasks_list": [
    "get",
    "/api/v1/tasks/"
  ],
  "tasks_backups_retrieve": [
    "get",
    "/api/v1/tasks/backups/"
  ],
  "tasks_backups_restore_requests_retrieve": [
    "get",
    "/api/v1/tasks/backups/restore-requests/{request_id}/"
  ],
  "tasks_backups_preflight_create": [
    "post",
    "/api/v1/tasks/backups/{timestamp}/preflight/"
  ],
  "tasks_backups_restore_create": [
    "post",
    "/api/v1/tasks/backups/{timestamp}/restore/"
  ],
  "tasks_cleanup_create": [
    "post",
    "/api/v1/tasks/cleanup/"
  ],
  "tasks_schedules_retrieve": [
    "get",
    "/api/v1/tasks/schedules/"
  ],
  "tasks_schedules_partial_update": [
    "patch",
    "/api/v1/tasks/schedules/{key}/"
  ],
  "tasks_schedules_run_create": [
    "post",
    "/api/v1/tasks/schedules/{key}/run/"
  ],
  "tasks_retrieve": [
    "get",
    "/api/v1/tasks/{id}/"
  ],
  "tasks_cancel_create": [
    "post",
    "/api/v1/tasks/{id}/cancel/"
  ],
  "tasks_resume_create": [
    "post",
    "/api/v1/tasks/{id}/resume/"
  ],
  "users_list": [
    "get",
    "/api/v1/users/"
  ],
  "users_create": [
    "post",
    "/api/v1/users/"
  ],
  "users_bulk_action_create": [
    "post",
    "/api/v1/users/bulk_action/"
  ],
  "users_destroy": [
    "delete",
    "/api/v1/users/{id}/"
  ],
  "users_retrieve": [
    "get",
    "/api/v1/users/{id}/"
  ],
  "users_partial_update": [
    "patch",
    "/api/v1/users/{id}/"
  ],
  "users_update": [
    "put",
    "/api/v1/users/{id}/"
  ],
  "users_reset_password_create": [
    "post",
    "/api/v1/users/{id}/reset_password/"
  ],
  "users_sensitive_create": [
    "post",
    "/api/v1/users/{id}/sensitive/"
  ]
} as const satisfies Record<keyof operations, readonly [string, string]>
