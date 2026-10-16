// 自动生成，请运行 npm run sdk:generate，勿手工修改。
export interface paths {
    "/api/v1/api-credentials/credentials/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_credentials_list"];
        put?: never;
        post: operations["api_credentials_credentials_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/credentials/{id}/revoke/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["api_credentials_credentials_revoke_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/credentials/scopes/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_credentials_scopes_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/tasks/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_tasks_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/tasks/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_tasks_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/work-items/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_work_items_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-credentials/work-items/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["api_credentials_work_items_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        get: operations["approvals_list"];
        put?: never;
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        post: operations["approvals_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        get: operations["approvals_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/add-sign/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        post: operations["approvals_add_sign_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/approve/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 通过申请 */
        post: operations["approvals_approve_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/cancel/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 撤回自己的待审批申请 */
        post: operations["approvals_cancel_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/cc/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        post: operations["approvals_cc_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/delegate/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        post: operations["approvals_delegate_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/reject/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 驳回申请 */
        post: operations["approvals_reject_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{id}/transfer/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        post: operations["approvals_transfer_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/assignee-departments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        get: operations["approvals_assignee_departments_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/assignees/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策 */
        get: operations["approvals_assignees_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/flows/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["approvals_flows_list"];
        put?: never;
        post: operations["approvals_flows_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/flows/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["approvals_flows_retrieve"];
        put: operations["approvals_flows_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/flows/{id}/archive/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["approvals_flows_archive_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/flows/{id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["approvals_flows_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/avatar/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 认证相关端点 */
        get: operations["auth_avatar_retrieve"];
        put?: never;
        /** @description 认证相关端点 */
        post: operations["auth_avatar_create"];
        /** @description 认证相关端点 */
        delete: operations["auth_avatar_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/change_password/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 修改密码 */
        post: operations["auth_change_password_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/email-verification/confirm/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_email_verification_confirm_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/email-verification/request/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_email_verification_request_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login-captcha/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_login_captcha_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 自定义登录视图 */
        post: operations["auth_login_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 登出 */
        post: operations["auth_logout_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 获取当前用户信息 */
        get: operations["auth_me_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/online-users/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_online_users_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/online-users/{id}/revoke/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_online_users_revoke_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/profile/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 认证相关端点 */
        get: operations["auth_profile_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** @description 认证相关端点 */
        patch: operations["auth_profile_partial_update"];
        trace?: never;
    };
    "/api/v1/auth/recovery/config/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_recovery_config_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/recovery/request/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_recovery_request_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/recovery/reset/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_recovery_reset_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 刷新 Token
         *
         *     注意保持 AllowAny（类默认）：调用时机是 access 已过期，
         *     请求头里没有有效 Bearer，鉴权只依赖 body 中的 refresh token。
         */
        post: operations["auth_refresh_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 用户注册 */
        post: operations["auth_register_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sessions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_sessions_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sessions/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete: operations["auth_sessions_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_totp_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/disable/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_totp_disable_retrieve"];
        put?: never;
        post: operations["auth_totp_disable_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/enable/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_totp_enable_retrieve"];
        put?: never;
        post: operations["auth_totp_enable_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/recovery-codes/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_totp_recovery_codes_retrieve"];
        put?: never;
        post: operations["auth_totp_recovery_codes_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/totp/setup/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_totp_setup_retrieve"];
        put?: never;
        post: operations["auth_totp_setup_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/brand/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["brand_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboard/stats/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 仪表盘统计：总量指标 + 7 日登录趋势 + 任务状态分布 */
        get: operations["dashboard_stats_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-io/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 导出数据（csv / xlsx） */
        get: operations["data_io_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-io/import/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 上传导入文件，创建导入任务 */
        post: operations["data_io_import_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-io/import/{task_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 查看自己发起的导入任务结果 */
        get: operations["data_io_import_retrieve"];
        put?: never;
        /** @description 人工接续：不再从头执行已提交的行。 */
        post: operations["data_io_import_retry"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-io/resources/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 只展示当前用户可访问的能力，导出与导入资格独立。 */
        get: operations["data_io_resources_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-io/template/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 下载导入模板（xlsx，含表头与示例行） */
        get: operations["data_io_template_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/example/items/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["example_items_list"];
        put?: never;
        post: operations["example_items_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/example/items/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["example_items_retrieve"];
        put: operations["example_items_update"];
        post?: never;
        delete: operations["example_items_destroy"];
        options?: never;
        head?: never;
        patch: operations["example_items_partial_update"];
        trace?: never;
    };
    "/api/v1/feature-flags/evaluate/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["feature_flags_evaluate_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/feature-flags/flags/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["feature_flags_flags_list"];
        put?: never;
        post: operations["feature_flags_flags_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/feature-flags/flags/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["feature_flags_flags_retrieve"];
        put?: never;
        post?: never;
        delete: operations["feature_flags_flags_destroy"];
        options?: never;
        head?: never;
        patch: operations["feature_flags_flags_partial_update"];
        trace?: never;
    };
    "/api/v1/feature-flags/targets/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["feature_flags_targets_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        get: operations["files_list"];
        put?: never;
        /** @description 上传返回统一 code/message/data；v1 兼容期保留顶层文件字段，新调用方只读取 data。 */
        post: operations["files_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}/office-preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["files_office_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        get: operations["files_retrieve"];
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        put: operations["files_update"];
        post?: never;
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        delete: operations["files_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/acl/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 读取或替换单个文件的用户/角色授权。文件所有者和管理员可管理。 */
        get: operations["files_acl_retrieve"];
        /** @description 读取或替换单个文件的用户/角色授权。文件所有者和管理员可管理。 */
        put: operations["files_acl_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/download/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 下载文件（记录下载次数） */
        get: operations["files_download_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        get: operations["files_preview_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/purge/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** @description 物理删除文件：用户/设备先于文件锁，锁内重新判断权限和范围。 */
        delete: operations["files_purge_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/restore/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        post: operations["files_restore_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{id}/transform/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        post: operations["files_transform_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/office-preview/config/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["files_office_preview_config_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/office-preview/jobs/{job_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["files_office_preview_jobs_retrieve"];
        put?: never;
        post?: never;
        delete: operations["files_office_preview_jobs_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/office-preview/jobs/{job_id}/pdf/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["files_office_preview_jobs_pdf_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/processing_config/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        get: operations["files_processing_config_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/recycle_action/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 最多 100 项；逐项复核范围/版本。部分成功有明确逐项结果，不承诺整批原子性。 */
        post: operations["files_recycle_action_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/recycle_policy/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 文件管理：上传 / 列表 / 下载 / 软删除 */
        get: operations["files_recycle_policy_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/recycle/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 同一数据范围的已删除文件，支持分页、筛选和搜索。 */
        get: operations["files_recycle_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/uploads/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["files_uploads_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/uploads/{upload_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["files_uploads_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/uploads/{upload_id}/chunks/{index}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put: operations["files_uploads_chunks_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/uploads/{upload_id}/complete/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["files_uploads_complete_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ip-policy/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["ip_policy_retrieve"];
        put: operations["ip_policy_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ip-policy/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["ip_policy_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/exception/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 异常日志查看 */
        get: operations["logs_exception_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/exception/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 异常日志查看 */
        get: operations["logs_exception_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/login/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 登录日志查看 */
        get: operations["logs_login_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/login/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 登录日志查看 */
        get: operations["logs_login_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/operation/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 操作日志查看 */
        get: operations["logs_operation_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/logs/operation/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 操作日志查看 */
        get: operations["logs_operation_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/modules/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["modules_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 通知中心：我的通知列表 / 标记已读 / 未读数；管理员可发送通知 */
        get: operations["notifications_list"];
        put?: never;
        /** @description 发送通知（仅管理员） */
        post: operations["notifications_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 查看详情时自动标记为已读 */
        get: operations["notifications_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/{id}/mark_read/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 标记单条通知为已读 */
        post: operations["notifications_mark_read_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/announcements/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_announcements_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/announcements/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_announcements_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/announcements/manage/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_announcements_manage_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_announcements_manage_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/announcements/manage/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_announcements_manage_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["notifications_announcements_manage_partial_update"];
        trace?: never;
    };
    "/api/v1/notifications/announcements/manage/{id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_announcements_manage_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/announcements/manage/{id}/withdraw/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_announcements_manage_withdraw_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/deliveries/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_deliveries_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_deliveries_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/deliveries/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_deliveries_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["notifications_deliveries_update"];
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["notifications_deliveries_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/deliveries/{id}/retry/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_deliveries_retry_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/mark_all_read/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 标记全部通知为已读 */
        post: operations["notifications_mark_all_read_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_templates_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["notifications_templates_partial_update"];
        trace?: never;
    };
    "/api/v1/notifications/templates/{id}/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_templates_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/{id}/send/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["notifications_templates_send_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/{id}/versions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_versions_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/channels/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_channels_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/recipient-departments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_recipient_departments_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/templates/recipients/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["notifications_templates_recipients_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/unread_count/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 未读通知数量 */
        get: operations["notifications_unread_count_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/departments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_departments_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["organization_departments_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/departments/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_departments_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["organization_departments_update"];
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["organization_departments_destroy"];
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["organization_departments_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/memberships/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_memberships_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["organization_memberships_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/memberships/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_memberships_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["organization_memberships_update"];
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["organization_memberships_destroy"];
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["organization_memberships_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/my-tenants/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_my_tenants_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/people/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_people_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/people/departments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_people_departments_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/posts/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_posts_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["organization_posts_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/posts/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_posts_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["organization_posts_update"];
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["organization_posts_destroy"];
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["organization_posts_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/posts/choices/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_posts_choices_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/scopes/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_scopes_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["organization_scopes_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/scopes/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_scopes_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["organization_scopes_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["organization_scopes_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/tenant-memberships/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_tenant_memberships_list"];
        put?: never;
        post: operations["organization_tenant_memberships_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/tenant-memberships/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_tenant_memberships_retrieve"];
        put: operations["organization_tenant_memberships_update"];
        post?: never;
        delete: operations["organization_tenant_memberships_destroy"];
        options?: never;
        head?: never;
        patch: operations["organization_tenant_memberships_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/tenants/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_tenants_list"];
        put?: never;
        post: operations["organization_tenants_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/tenants/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["organization_tenants_retrieve"];
        put: operations["organization_tenants_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["organization_tenants_partial_update"];
        trace?: never;
    };
    "/api/v1/organization/user-posts/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_user_posts_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["organization_user_posts_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organization/user-posts/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["organization_user_posts_retrieve"];
        put?: never;
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["organization_user_posts_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/menus/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 菜单维护及按权限过滤的导航树。 */
        get: operations["permissions_menus_list"];
        put?: never;
        /** @description 菜单维护及按权限过滤的导航树。 */
        post: operations["permissions_menus_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/menus/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 菜单维护及按权限过滤的导航树。 */
        get: operations["permissions_menus_retrieve"];
        /** @description 菜单维护及按权限过滤的导航树。 */
        put: operations["permissions_menus_update"];
        post?: never;
        /** @description 菜单维护及按权限过滤的导航树。 */
        delete: operations["permissions_menus_destroy"];
        options?: never;
        head?: never;
        /** @description 菜单维护及按权限过滤的导航树。 */
        patch: operations["permissions_menus_partial_update"];
        trace?: never;
    };
    "/api/v1/permissions/menus/my_menu/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 获取当前用户可访问的菜单 */
        get: operations["permissions_menus_my_menu_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/permissions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 权限管理（只读） */
        get: operations["permissions_permissions_list"];
        put?: never;
        /** @description 权限管理（只读） */
        post: operations["permissions_permissions_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/permissions/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 权限管理（只读） */
        get: operations["permissions_permissions_retrieve"];
        /** @description 权限管理（只读） */
        put: operations["permissions_permissions_update"];
        post?: never;
        /** @description 权限管理（只读） */
        delete: operations["permissions_permissions_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/roles/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 角色管理 */
        get: operations["permissions_roles_list"];
        put?: never;
        /** @description 角色管理 */
        post: operations["permissions_roles_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/permissions/roles/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 角色管理 */
        get: operations["permissions_roles_retrieve"];
        /** @description 角色管理 */
        put: operations["permissions_roles_update"];
        post?: never;
        /** @description 角色管理 */
        delete: operations["permissions_roles_destroy"];
        options?: never;
        head?: never;
        /** @description 角色管理 */
        patch: operations["permissions_roles_partial_update"];
        trace?: never;
    };
    "/api/v1/reliability/events/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["reliability_events_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["reliability_events_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reliability/events/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["reliability_events_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["reliability_events_update"];
        post?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        delete: operations["reliability_events_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reliability/events/{id}/retry/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["reliability_events_retry_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/schema/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description OpenApi3 schema for this API. Format can be selected via content negotiation.
         *
         *     - YAML: application/vnd.oai.openapi
         *     - JSON: application/vnd.oai.openapi+json
         */
        get: operations["schema_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/callback/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["sso_callback_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/cancel/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["sso_cancel_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/complete/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["sso_complete_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/config/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["sso_config_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/identities/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["sso_identities_list"];
        put?: never;
        post: operations["sso_identities_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/identities/{id}/unbind/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["sso_identities_unbind_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/start/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["sso_start_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sso/status/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["sso_status_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/cache/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["system_cache_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/cache/clear/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["system_cache_clear_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/cache/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["system_cache_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/config/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["system_config_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/config/{key}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["system_config_detail"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["system_config_write"];
        trace?: never;
    };
    "/api/v1/system/dictionaries/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["system_dictionaries_list"];
        put?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        post: operations["system_dictionaries_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/dictionaries/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["system_dictionaries_retrieve"];
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        put: operations["system_dictionaries_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        patch: operations["system_dictionaries_partial_update"];
        trace?: never;
    };
    "/api/v1/system/dictionaries/options/{code}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description 把 ViewSet 的写操作/详情响应包成统一格式 {code, message, data}
         *
         *     list 已由 StandardPagination.get_paginated_response 统一包装；
         *     自定义 action 自行构造 Response 的不受影响。
         */
        get: operations["system_dictionaries_options_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/information/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["system_information_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/monitor/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["system_monitor_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 任务中心：查看任务记录、取消任务、清理历史 */
        get: operations["tasks_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 任务中心：查看任务记录、取消任务、清理历史 */
        get: operations["tasks_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{id}/cancel/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 取消执行中的任务（尽力撤销 Celery 任务并标记记录） */
        post: operations["tasks_cancel_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{id}/resume/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 任务中心：查看任务记录、取消任务、清理历史 */
        post: operations["tasks_resume_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/backups/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["tasks_backups_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/backups/{timestamp}/preflight/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["tasks_backups_preflight_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/backups/{timestamp}/restore/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["tasks_backups_restore_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/backups/restore-requests/{request_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["tasks_backups_restore_requests_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/cleanup/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 默认只预览；实际执行绑定15分钟内的范围/设备/记录快照，最多100项。 */
        post: operations["tasks_cleanup_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/schedules/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["tasks_schedules_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/schedules/{key}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["tasks_schedules_partial_update"];
        trace?: never;
    };
    "/api/v1/tasks/schedules/{key}/run/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["tasks_schedules_run_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 用户管理 */
        get: operations["users_list"];
        put?: never;
        /** @description 用户管理 */
        post: operations["users_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description 用户管理 */
        get: operations["users_retrieve"];
        /** @description 用户管理 */
        put: operations["users_update"];
        post?: never;
        /** @description 用户管理 */
        delete: operations["users_destroy"];
        options?: never;
        head?: never;
        /** @description 用户管理 */
        patch: operations["users_partial_update"];
        trace?: never;
    };
    "/api/v1/users/{id}/reset_password/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 重置用户密码 */
        post: operations["users_reset_password_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/{id}/sensitive/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 单次查看联系方式：权限、数据范围、会话与密码共同约束。 */
        post: operations["users_sensitive_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/bulk_action/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** @description 批量操作用户 */
        post: operations["users_bulk_action_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * @description * `read` - 读取
         *     * `manage` - 管理
         * @enum {string}
         */
        AccessLevelEnum: "read" | "manage";
        Announcement: {
            readonly content: string;
            readonly content_format: components["schemas"]["ContentFormatEnum"];
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            /** Format: date-time */
            readonly published_at: string | null;
            readonly status: components["schemas"]["AnnouncementStatusEnum"];
            readonly title: string;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            readonly version: number;
        };
        AnnouncementCreatedResponse: {
            code: number;
            data: components["schemas"]["Announcement"];
            message: string;
        };
        AnnouncementDetailResponse: {
            code: number;
            data: components["schemas"]["Announcement"];
            message: string;
        };
        AnnouncementPublishedResponse: {
            code: number;
            data: components["schemas"]["Announcement"];
            message: string;
        };
        /**
         * @description * `draft` - 草稿
         *     * `published` - 已发布
         *     * `withdrawn` - 已撤回
         * @enum {string}
         */
        AnnouncementStatusEnum: "draft" | "published" | "withdrawn";
        AnnouncementTransitionRequest: {
            version: number;
        };
        AnnouncementUpdatedResponse: {
            code: number;
            data: components["schemas"]["Announcement"];
            message: string;
        };
        AnnouncementWithdrawnResponse: {
            code: number;
            data: components["schemas"]["Announcement"];
            message: string;
        };
        AnnouncementWriteRequest: {
            content: string;
            /**
             * @description plain 为纯文本（创建默认值）；html 为服务端消毒后的受控 HTML。编辑未传时保持现有格式。
             *
             *     * `plain` - 纯文本
             *     * `html` - HTML
             */
            content_format?: components["schemas"]["ContentFormatEnum"];
            title: string;
            version: number;
        };
        ApprovalApprovedResponse: {
            code: number;
            data: components["schemas"]["ApprovalRequest"];
            message: string;
        };
        ApprovalAssigneesResponse: {
            code: number;
            data: components["schemas"]["PeoplePage"];
            message: string;
        };
        ApprovalCancelledResponse: {
            code: number;
            data: components["schemas"]["ApprovalRequest"];
            message: string;
        };
        ApprovalCreatedResponse: {
            code: number;
            data: components["schemas"]["ApprovalRequest"];
            message: string;
        };
        /** @description 发起审批申请 */
        ApprovalCreateRequest: {
            /** Format: uuid */
            assignee_id?: string;
            assignee_username?: string;
            content: string;
            extra_data?: unknown;
            /** Format: uuid */
            flow_id?: string;
            /** @default other */
            request_type: components["schemas"]["RequestTypeEnum"];
            title: string;
        };
        /** @description 审批决策 */
        ApprovalDecisionRequest: {
            /** @default  */
            comment: string;
        };
        ApprovalFlow: {
            code: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly created_by: string;
            readonly created_by_name: string;
            definition?: unknown;
            /** Format: uuid */
            readonly id: string;
            name: string;
            /** Format: date-time */
            readonly published_at: string | null;
            /** Format: uuid */
            readonly published_by: string | null;
            readonly published_by_name: string;
            readonly status: components["schemas"]["ApprovalFlowStatusEnum"];
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            readonly version: number;
        };
        ApprovalFlowDesign: {
            code: string;
            definition?: unknown;
            name: string;
        };
        ApprovalFlowDesignRequest: {
            code: string;
            definition?: unknown;
            name: string;
        };
        ApprovalFlowRequest: {
            code: string;
            definition?: unknown;
            name: string;
        };
        /**
         * @description * `draft` - 草稿
         *     * `published` - 已发布
         *     * `archived` - 已归档
         * @enum {string}
         */
        ApprovalFlowStatusEnum: "draft" | "published" | "archived";
        ApprovalPickerDepartmentsResponse: {
            code: number;
            data: components["schemas"]["PickerDepartments"];
            message: string;
        };
        ApprovalRejectedResponse: {
            code: number;
            data: components["schemas"]["ApprovalRequest"];
            message: string;
        };
        /** @description 审批申请序列化（读取） */
        ApprovalRequest: {
            /**
             * 申请人
             * Format: uuid
             */
            readonly applicant: string;
            readonly applicant_name: string;
            /**
             * 当前审批人
             * Format: uuid
             */
            readonly assignee: string;
            readonly assignee_name: string;
            readonly cc_recipients: {
                [key: string]: unknown;
            }[];
            /** 申请内容 */
            readonly content: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            readonly current_node: string;
            /**
             * 处理时间
             * Format: date-time
             */
            readonly decided_at: string | null;
            /**
             * 处理人
             * Format: uuid
             */
            readonly decided_by: string | null;
            readonly decided_by_name: string;
            /** 审批意见 */
            readonly decision_comment: string;
            /** 附加数据 */
            readonly extra_data: unknown;
            /** Format: uuid */
            readonly flow: string | null;
            readonly flow_name: string;
            readonly flow_version: number | null;
            /** Format: uuid */
            readonly id: string;
            /** 申请类型 */
            readonly request_type: components["schemas"]["RequestTypeEnum"];
            /** 状态 */
            readonly status: components["schemas"]["ApprovalStatusEnum"];
            readonly steps: {
                [key: string]: unknown;
            }[];
            /** 标题 */
            readonly title: string;
            readonly workflow_version: number;
        };
        /**
         * @description * `pending` - 待审批
         *     * `approved` - 已通过
         *     * `rejected` - 已驳回
         *     * `cancelled` - 已撤回
         * @enum {string}
         */
        ApprovalStatusEnum: "pending" | "approved" | "rejected" | "cancelled";
        Authorization: {
            /** Format: uri */
            authorization_url: string;
        };
        AvailableScope: {
            code: string;
            label: string;
        };
        AvatarUpdatedResponse: {
            code: number;
            data: components["schemas"]["ProfileRead"];
            message: string;
        };
        AvatarUploadRequest: {
            /** Format: binary */
            file: Blob;
            profile_version: number;
        };
        /**
         * @description * `shared` - shared
         *     * `in_process` - in_process
         *     * `unsupported` - unsupported
         * @enum {string}
         */
        BackendEnum: "shared" | "in_process" | "unsupported";
        BackupArtifact: {
            artifacts: components["schemas"]["BackupArtifactFile"][];
            created_at: string;
            remote_copy: boolean;
            timestamp: string;
        };
        BackupArtifactFile: {
            bytes: number;
            name: string;
            sha256: string;
        };
        BackupPreflight: {
            artifacts: components["schemas"]["BackupArtifactFile"][];
            /** Format: uuid */
            preflight_id: string;
            remote_copy: boolean;
            requires_confirmation: boolean;
            runner_state: string;
            timestamp: string;
        };
        BackupPreflightResponse: {
            code: number;
            data: components["schemas"]["BackupPreflight"];
            message: string;
        };
        BackupRestoreAcceptedResponse: {
            code: number;
            data: components["schemas"]["BackupRestoreResult"];
            message: string;
        };
        BackupRestoreHistory: {
            /** Format: date-time */
            completed_at: string | null;
            /** Format: date-time */
            created_at: string;
            error: string;
            /** Format: uuid */
            id: string;
            status: string;
            timestamp: string;
        };
        BackupRestoreRequest: {
            confirmation: string;
            current_password: string;
            /** Format: uuid */
            preflight_id: string;
        };
        BackupRestoreRequestResponse: {
            code: number;
            data: components["schemas"]["BackupRestoreResult"];
            message: string;
        };
        BackupRestoreResult: {
            /** Format: date-time */
            completed_at?: string | null;
            /** Format: date-time */
            created_at?: string;
            error?: string;
            /** Format: uuid */
            id: string;
            status: string;
            timestamp: string;
        };
        BackupStatus: {
            artifacts: components["schemas"]["BackupArtifact"][];
            directory_label: string;
            enabled: boolean;
            last_error: string;
            /** Format: date-time */
            last_seen_at: string | null;
            restore_requests: components["schemas"]["BackupRestoreHistory"][];
            stage: string;
            state: string;
        };
        BackupStatusResponse: {
            code: number;
            data: components["schemas"]["BackupStatus"];
            message: string;
        };
        BindRequest: {
            current_password: string;
            subject: string;
            /** Format: uuid */
            user_id: string;
        };
        Brand: {
            logo: string;
            name: string;
            tagline: string;
        };
        BrandResponse: {
            code: number;
            data: components["schemas"]["Brand"];
            message: string;
        };
        BrokerMetric: {
            ready: number | null;
            status: components["schemas"]["QueueMetricStatusEnum"];
        };
        /**
         * @description * `activate` - activate
         *     * `deactivate` - deactivate
         *     * `delete` - delete
         * @enum {string}
         */
        BulkUserActionActionEnum: "activate" | "deactivate" | "delete";
        /** @description 批量用户操作序列化器 */
        BulkUserActionRequest: {
            action: components["schemas"]["BulkUserActionActionEnum"];
            user_ids: string[];
        };
        BulkUserActionResponse: {
            code: number;
            data: components["schemas"]["BulkUserActionResult"] | null;
            message: string;
        };
        BulkUserActionResult: {
            atomic: boolean;
            failed: number;
            results: components["schemas"]["BulkUserItemResult"][];
            succeeded: number;
        };
        BulkUserItemResult: {
            /** Format: uuid */
            id: string;
            status: number;
        };
        CacheCatalogResponse: {
            code: number;
            data: components["schemas"]["Catalog"];
            message: string;
        };
        CacheClearResponse: {
            code: number;
            data: components["schemas"]["ClearResult"];
            message: string;
        };
        CachePreviewResponse: {
            code: number;
            data: components["schemas"]["PreviewResult"];
            message: string;
        };
        Catalog: {
            backend: components["schemas"]["BackendEnum"];
            limit: number;
            namespaces: components["schemas"]["Namespace"][];
            ttl_seconds: number;
        };
        /** @description 修改密码序列化器 */
        ChangePasswordRequest: {
            new_password: string;
            new_password2: string;
            old_password: string;
        };
        ChannelsResult: {
            enabled: boolean;
            key: string;
        };
        CleanupRequestRequest: {
            /** @default 100 */
            batch_size: number;
            confirmation?: string;
            /** @default 30 */
            days: number;
            /** @default true */
            dry_run: boolean;
            preview_token?: string;
        };
        ClearRequestRequest: {
            namespace: components["schemas"]["NamespaceEnum"];
            token: string;
        };
        ClearResult: {
            backend: string;
            candidate_count: number;
            namespace: string;
            outcome: string;
        };
        CodeRequest: {
            code: string;
        };
        Completed: {
            access: string;
            refresh: string;
            user: components["schemas"]["SSOLoginUser"];
        };
        CompleteRequest: {
            captcha_code?: string;
            /** Format: uuid */
            captcha_id?: string;
            otp_code?: string;
        };
        Config: {
            enabled: boolean;
            label?: string;
        };
        ConfigRow: {
            default: unknown;
            effective: string;
            key: string;
            kind: string;
            label: string;
            maximum: number;
            minimum: number;
            value: unknown;
            version: number;
        };
        /**
         * @description * `plain` - 纯文本
         *     * `html` - HTML
         * @enum {string}
         */
        ContentFormatEnum: "plain" | "html";
        CorrelationMetric: {
            notification_request_linked: number | null;
            outbox_request_linked: number | null;
            task_request_linked: number | null;
        };
        Cpu: {
            /** Format: double */
            capacity_cores: number | null;
            /** Format: double */
            percent: number | null;
            /** Format: double */
            sample_seconds: number | null;
        };
        Credential: {
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly expires_at: string;
            /** Format: uuid */
            readonly id: string;
            /** Format: date-time */
            readonly last_used_at: string | null;
            readonly name: string;
            /** Format: date-time */
            readonly revoked_at: string | null;
            readonly scopes: unknown;
        };
        CredentialCreateRequest: {
            current_password: string;
            /** Format: date-time */
            expires_at: string;
            name: string;
            scopes: string[];
        };
        CredentialIssued: {
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly expires_at: string;
            /** Format: uuid */
            readonly id: string;
            /** Format: date-time */
            readonly last_used_at: string | null;
            readonly name: string;
            /** Format: date-time */
            readonly revoked_at: string | null;
            readonly scopes: unknown;
            readonly token: string;
        };
        CredentialIssuedResponse: {
            code: number;
            data: components["schemas"]["CredentialIssued"];
            message: string;
        };
        CredentialScopes: {
            code: number;
            data: components["schemas"]["AvailableScope"][];
            message: string;
        };
        CurrentUserResponse: {
            code: number;
            data: components["schemas"]["User"];
            message: string;
        };
        Dashboard: {
            login_trend: components["schemas"]["LoginTrend"][];
            task_status: {
                [key: string]: number;
            };
            totals: components["schemas"]["DashboardTotals"];
        };
        DashboardResponse: {
            code: number;
            data: components["schemas"]["Dashboard"];
            message: string;
        };
        DashboardTotals: {
            files: number;
            pending_approvals: number;
            today_logins: number;
            today_operations: number;
            unread_notifications: number;
            users: number;
        };
        /** @description 数据导入请求 */
        DataImportRequest: {
            /** Format: binary */
            file: Blob;
            resource: components["schemas"]["DataImportResourceEnum"];
        };
        /**
         * @description * `users` - 用户
         *     * `roles` - 角色
         *     * `posts` - 岗位
         * @enum {string}
         */
        DataImportResourceEnum: "users" | "roles" | "posts";
        DataResource: {
            exportable: boolean;
            importable: boolean;
            label: string;
            resource: string;
        };
        DataResourceDirectory: {
            max_bytes: number;
            max_rows: number;
            resources: components["schemas"]["DataResource"][];
        };
        DataResourceDirectoryResponse: {
            code: number;
            data: components["schemas"]["DataResourceDirectory"];
            message: string;
        };
        Department: {
            /** Format: uuid */
            readonly id: string;
            is_active?: boolean;
            name: string;
            /** Format: int64 */
            order?: number;
            /** Format: uuid */
            parent?: string | null;
            version: number;
        };
        DepartmentCreatedResponse: {
            code: number;
            data: components["schemas"]["Department"];
            message: string;
        };
        DepartmentDetailResponse: {
            code: number;
            data: components["schemas"]["Department"];
            message: string;
        };
        DepartmentPatchedResponse: {
            code: number;
            data: components["schemas"]["Department"];
            message: string;
        };
        DepartmentRequest: {
            is_active?: boolean;
            name: string;
            /** Format: int64 */
            order?: number;
            /** Format: uuid */
            parent?: string | null;
            version: number;
        };
        DepartmentUpdatedResponse: {
            code: number;
            data: components["schemas"]["Department"];
            message: string;
        };
        Dependency: {
            name: string;
            version: string | null;
        };
        Dictionary: {
            code: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            description?: string;
            /** Format: uuid */
            readonly id: string;
            is_active?: boolean;
            items?: unknown;
            name: string;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            version: number;
        };
        DictionaryCreatedResponse: {
            code: number;
            data: components["schemas"]["Dictionary"];
            message: string;
        };
        DictionaryDetailResponse: {
            code: number;
            data: components["schemas"]["Dictionary"];
            message: string;
        };
        DictionaryOptions: {
            code: string;
            items: unknown;
            version: number;
        };
        DictionaryOptionsResponse: {
            code: number;
            data: components["schemas"]["DictionaryOptions"];
            message: string;
        };
        DictionaryPatchedResponse: {
            code: number;
            data: components["schemas"]["Dictionary"];
            message: string;
        };
        DictionaryRequest: {
            code: string;
            description?: string;
            is_active?: boolean;
            items?: unknown;
            name: string;
            version: number;
        };
        DictionaryUpdatedResponse: {
            code: number;
            data: components["schemas"]["Dictionary"];
            message: string;
        };
        Disk: {
            free_bytes: number | null;
            name: string;
            /** Format: double */
            percent: number | null;
            status: components["schemas"]["DiskStatusEnum"];
            total_bytes: number | null;
            used_bytes: number | null;
        };
        /**
         * @description * `ok` - ok
         *     * `unavailable` - unavailable
         * @enum {string}
         */
        DiskStatusEnum: "ok" | "unavailable";
        DurationMetric: {
            /** Format: double */
            average: number | null;
            count: number;
            /** Format: double */
            max: number | null;
            /** Format: double */
            p95: number | null;
        };
        EmailVerificationProfileResponse: {
            code: number;
            data: components["schemas"]["ProfileRead"];
            message: string;
        };
        Evaluation: {
            enabled: boolean;
            key: string;
        };
        EvaluationRequestRequest: {
            keys: string[];
        };
        ExampleCreatedResponse: {
            code: number;
            data: components["schemas"]["WorkItem"];
            message: string;
        };
        ExampleDetailResponse: {
            code: number;
            data: components["schemas"]["WorkItem"];
            message: string;
        };
        ExamplePatchedResponse: {
            code: number;
            data: components["schemas"]["WorkItem"];
            message: string;
        };
        ExampleUpdatedResponse: {
            code: number;
            data: components["schemas"]["WorkItem"];
            message: string;
        };
        /** @description 异常日志序列化器 */
        ExceptionLog: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            /** IP 地址 */
            ip_address?: string | null;
            /** 日志级别 */
            level: components["schemas"]["LevelEnum"];
            /** 错误信息 */
            message: string;
            /** 请求方法 */
            request_method?: string;
            /** 请求路径 */
            request_path?: string;
            readonly username: string | null;
        };
        FeatureFlag: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            description?: string;
            enabled?: boolean;
            excluded_users?: string[];
            /** Format: uuid */
            readonly id: string;
            included_users?: string[];
            key: string;
            name: string;
            roles?: string[];
            rollout?: number;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            version: number;
        };
        FeatureFlagCreatedResponse: {
            code: number;
            data: components["schemas"]["FeatureFlag"];
            message: string;
        };
        FeatureFlagDetailResponse: {
            code: number;
            data: components["schemas"]["FeatureFlag"];
            message: string;
        };
        FeatureFlagEvaluationResponse: {
            code: number;
            data: components["schemas"]["Evaluation"][];
            message: string;
        };
        FeatureFlagRequest: {
            description?: string;
            enabled?: boolean;
            excluded_users?: string[];
            included_users?: string[];
            key: string;
            name: string;
            roles?: string[];
            rollout?: number;
            version: number;
        };
        FeatureFlagTargetsResponse: {
            code: number;
            data: components["schemas"]["Target"][];
            message: string;
        };
        FeatureFlagUpdatedResponse: {
            code: number;
            data: components["schemas"]["FeatureFlag"];
            message: string;
        };
        /** @description 文件信息序列化（读取） */
        File: {
            /** MIME 类型 */
            readonly content_type: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /**
             * 删除时间
             * Format: date-time
             */
            readonly deleted_at: string | null;
            /**
             * 删除操作者
             * Format: uuid
             */
            readonly deleted_by: string | null;
            /** 描述 */
            readonly description: string;
            /** 下载次数 */
            readonly download_count: number;
            readonly file: string;
            /** 文件类型（扩展名） */
            readonly file_type: string;
            /** Format: uuid */
            readonly id: string;
            /** 是否删除（软删除） */
            readonly is_deleted: boolean;
            /** 生命周期版本 */
            readonly lifecycle_version: number;
            /** MD5 摘要 */
            readonly md5: string;
            /** 原始文件名 */
            readonly original_name: string;
            /** 文件大小（字节） */
            readonly size: number;
            /** @description 人类可读的文件大小 */
            readonly size_display: string;
            /**
             * 上传者
             * Format: uuid
             */
            readonly uploader: string | null;
            readonly uploader_name: string;
        };
        FileACL: {
            grants: components["schemas"]["FileACLGrant"][];
        };
        FileACLGrant: {
            access_level: components["schemas"]["AccessLevelEnum"];
            /** @default true */
            inherit_to_derivatives: boolean;
            /** Format: uuid */
            role_id?: string | null;
            /** Format: uuid */
            user_id?: string | null;
        };
        FileACLGrantRequest: {
            access_level: components["schemas"]["AccessLevelEnum"];
            /** @default true */
            inherit_to_derivatives: boolean;
            /** Format: uuid */
            role_id?: string | null;
            /** Format: uuid */
            user_id?: string | null;
        };
        FileACLRequest: {
            grants: components["schemas"]["FileACLGrantRequest"][];
        };
        FileACLResponse: {
            code: number;
            data: components["schemas"]["FileACL"];
            message: string;
        };
        FileRecycleActionResponse: {
            code: number;
            data: components["schemas"]["RecycleResult"];
            message: string;
        };
        FileRecyclePolicyResponse: {
            code: number;
            data: components["schemas"]["RecyclePolicy"];
            message: string;
        };
        FileRestoreResponse: {
            code: number;
            data: components["schemas"]["File"];
            message: string;
        };
        FileUploadedResponse: {
            code: number;
            data: components["schemas"]["File"];
            message: string;
        };
        /** @description 文件上传序列化（校验白名单和大小限制） */
        FileUploadRequest: {
            /** 描述 */
            description?: string;
            /** Format: binary */
            file: Blob;
        };
        /**
         * @description * `png` - png
         *     * `jpeg` - jpeg
         *     * `webp` - webp
         * @enum {string}
         */
        FormatEnum: "png" | "jpeg" | "webp";
        GatewayTaskDetail: {
            code: number;
            data: components["schemas"]["TaskSummary"];
            message: string;
        };
        GatewayWorkItemDetail: {
            code: number;
            data: components["schemas"]["WorkItemSummary"];
            message: string;
        };
        Identity: {
            /** Format: date-time */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly issuer: string;
            /** Format: date-time */
            readonly revoked_at: string | null;
            readonly subject: string;
            /** Format: uuid */
            readonly user_id: string;
            readonly username: string;
        };
        ImageProcessingConfig: {
            enabled: boolean;
            formats: string[];
            max_bytes: number;
            max_dimension: number;
            max_pixels: number;
            watermark_max_bytes: number;
        };
        ImageProcessingConfigResponse: {
            code: number;
            data: components["schemas"]["ImageProcessingConfig"];
            message: string;
        };
        ImageTransformRequest: {
            /** @default webp */
            format: components["schemas"]["FormatEnum"];
            /** @default 1280 */
            height: number;
            lifecycle_version: number;
            /** @default 60 */
            opacity: number;
            /** @default bottom-right */
            position: components["schemas"]["PositionEnum"];
            /** @default 80 */
            quality: number;
            /** Format: binary */
            watermark?: Blob;
            /** @default 1280 */
            width: number;
        };
        ImportResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        ImportRetryResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        ImportStatusResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        Information: {
            architecture: string;
            base_version: string;
            database: string;
            debug: boolean;
            dependencies: components["schemas"]["Dependency"][];
            environment: string;
            modules: string[];
            os: string;
            preset: string;
            python: string;
            /** Format: date-time */
            sampled_at: string;
            services: components["schemas"]["Service"][];
            storage: string;
            task_metrics: components["schemas"]["TaskMetric"];
            timezone: string;
        };
        IPPolicy: {
            allow: string[];
            deny: string[];
            enabled: boolean;
            /** Format: date-time */
            readonly updated_at: string;
            version: number;
        };
        IPPolicyDetail: {
            code: number;
            data: components["schemas"]["IPPolicy"];
            message: string;
        };
        IPPolicyPreview: {
            code: number;
            data: components["schemas"]["IPPolicyPreviewResult"];
            message: string;
        };
        IPPolicyPreviewResult: {
            allowed: boolean;
            source_ip: string | null;
        };
        IPPolicyRequest: {
            allow: string[];
            current_password: string;
            deny: string[];
            enabled: boolean;
            version: number;
        };
        IPPolicyUpdated: {
            code: number;
            data: components["schemas"]["IPPolicy"];
            message: string;
        };
        /**
         * @description * `python` - python
         *     * `other` - other
         * @enum {string}
         */
        KindEnum: "python" | "other";
        /**
         * @description * `debug` - DEBUG
         *     * `info` - INFO
         *     * `warning` - WARNING
         *     * `error` - ERROR
         *     * `critical` - CRITICAL
         * @enum {string}
         */
        LevelEnum: "debug" | "info" | "warning" | "error" | "critical";
        LoginCaptchaEnvelope: {
            code: number;
            data: components["schemas"]["LoginCaptchaResponse"];
            message: string;
        };
        LoginCaptchaRequestRequest: {
            username: string;
        };
        LoginCaptchaResponse: {
            /** Format: uuid */
            challenge_id?: string;
            expires_in?: number;
            image?: string;
            required: boolean;
        };
        /** @description 登录日志序列化器 */
        LoginLog: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 错误信息 */
            error_message?: string;
            /** Format: uuid */
            readonly id: string;
            /** IP 地址 */
            ip_address: string;
            /** 登录状态 */
            status: components["schemas"]["LoginLogStatusEnum"];
            /** 用户名 */
            username: string;
        };
        /**
         * @description * `success` - 成功
         *     * `failed` - 失败
         *     * `locked` - 被锁定
         * @enum {string}
         */
        LoginLogStatusEnum: "success" | "failed" | "locked";
        LoginRequestRequest: {
            captcha_code?: string;
            /** Format: uuid */
            captcha_id?: string;
            otp_code?: string;
            password: string;
            username: string;
        };
        LoginResponse: {
            access: string;
            refresh: string;
            user: components["schemas"]["LoginUser"];
        };
        LoginTrend: {
            /** Format: date */
            date: string;
            failed: number;
            success: number;
        };
        LoginUser: {
            avatar: string;
            email: string;
            id: string;
            must_change_password: boolean;
            username: string;
        };
        LostCandidate: {
            pending: number;
            running: number;
            sampled: number;
            truncated: boolean;
            unclassified: number;
        };
        MaintenanceAcceptedResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        MaintenanceSchedulesResponse: {
            code: number;
            data: components["schemas"]["ScheduleRow"][];
            message: string;
        };
        MaintenanceScheduleUpdatedResponse: {
            code: number;
            data: components["schemas"]["ScheduleRow"];
            message: string;
        };
        Membership: {
            /** Format: uuid */
            department: string;
            readonly department_name: string;
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            user: string;
            readonly username: string;
            version: number;
        };
        MembershipCreatedResponse: {
            code: number;
            data: components["schemas"]["Membership"];
            message: string;
        };
        MembershipDetailResponse: {
            code: number;
            data: components["schemas"]["Membership"];
            message: string;
        };
        MembershipPatchedResponse: {
            code: number;
            data: components["schemas"]["Membership"];
            message: string;
        };
        MembershipRequest: {
            /** Format: uuid */
            department: string;
            /** Format: uuid */
            user: string;
            version: number;
        };
        MembershipUpdatedResponse: {
            code: number;
            data: components["schemas"]["Membership"];
            message: string;
        };
        Memory: {
            /** Format: double */
            percent: number | null;
            total_bytes: number | null;
            used_bytes: number | null;
        };
        /** @description 菜单序列化器 */
        Menu: {
            readonly children: components["schemas"]["Menu"][];
            /** 图标 */
            icon?: string;
            /** Format: uuid */
            readonly id: string;
            /** 是否可见 */
            is_visible?: boolean;
            /** 菜单名 */
            name: string;
            /**
             * 排序
             * Format: int64
             */
            order?: number;
            /**
             * 父菜单
             * Format: uuid
             */
            parent?: string | null;
            /** 路由路径 */
            path: string;
            /**
             * 所需权限
             * Format: uuid
             */
            permission?: string | null;
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        MenuCreatedResponse: {
            code: number;
            data: components["schemas"]["Menu"];
            message: string;
        };
        MenuDetailResponse: {
            code: number;
            data: components["schemas"]["Menu"];
            message: string;
        };
        MenuPatchedResponse: {
            code: number;
            data: components["schemas"]["Menu"];
            message: string;
        };
        /** @description 菜单序列化器 */
        MenuRequest: {
            /** 图标 */
            icon?: string;
            /** 是否可见 */
            is_visible?: boolean;
            /** 菜单名 */
            name: string;
            /**
             * 排序
             * Format: int64
             */
            order?: number;
            /**
             * 父菜单
             * Format: uuid
             */
            parent?: string | null;
            /** 路由路径 */
            path: string;
            /**
             * 所需权限
             * Format: uuid
             */
            permission?: string | null;
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        MenuUpdatedResponse: {
            code: number;
            data: components["schemas"]["Menu"];
            message: string;
        };
        /**
         * @description * `inapp` - 站内通知
         *     * `email` - SMTP 邮件
         *     * `webhook` - Webhook
         *     * `sms` - Twilio 短信
         * @enum {string}
         */
        MessageChannelEnum: "inapp" | "email" | "webhook" | "sms";
        MessageChannelsResponse: {
            code: number;
            data: components["schemas"]["ChannelsResult"][];
            message: string;
        };
        MessageDelivery: {
            readonly attempts: number;
            readonly channel: components["schemas"]["MessageChannelEnum"];
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly creator: string | null;
            /** Format: date-time */
            readonly expires_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly last_error: string;
            /** Format: uuid */
            readonly recipient: string | null;
            readonly request_id: string;
            /** Format: date-time */
            readonly sent_at: string | null;
            readonly status: components["schemas"]["MessageDeliveryStatusEnum"];
            readonly template_code: string;
            readonly version_number: number;
        };
        MessageDeliveryDetailResponse: {
            code: number;
            data: components["schemas"]["MessageDelivery"];
            message: string;
        };
        MessageDeliveryRetryResponse: {
            code: number;
            data: components["schemas"]["MessageDelivery"];
            message: string;
        };
        /**
         * @description * `pending` - 待发送
         *     * `sending` - 发送中
         *     * `succeeded` - 成功
         *     * `failed` - 失败
         *     * `terminated` - 已终止
         * @enum {string}
         */
        MessageDeliveryStatusEnum: "pending" | "sending" | "succeeded" | "failed" | "terminated";
        MessagePreviewResponse: {
            code: number;
            data: components["schemas"]["MessagePreviewResult"];
            message: string;
        };
        MessagePreviewResult: {
            body: string;
            subject: string;
        };
        MessageRecipientDepartmentsResponse: {
            code: number;
            data: components["schemas"]["PickerDepartments"];
            message: string;
        };
        MessageRecipientsResponse: {
            code: number;
            data: components["schemas"]["PeoplePage"];
            message: string;
        };
        MessageResponse: {
            code: number;
            data: unknown;
            message: string;
        };
        MessageSendResponse: {
            code: number;
            data: components["schemas"]["SentDeliveries"];
            message: string;
        };
        MessageTemplate: {
            readonly code: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            readonly current: components["schemas"]["TemplateVersion"];
            readonly enabled: boolean;
            /** Format: uuid */
            readonly id: string;
            readonly name: string;
            readonly revision: number;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
        };
        MessageTemplateCreatedResponse: {
            code: number;
            data: components["schemas"]["MessageTemplate"];
            message: string;
        };
        MessageTemplateDetailResponse: {
            code: number;
            data: components["schemas"]["MessageTemplate"];
            message: string;
        };
        MessageTemplateUpdatedResponse: {
            code: number;
            data: components["schemas"]["MessageTemplate"];
            message: string;
        };
        MessageVersionPage: {
            items: components["schemas"]["TemplateVersion"][];
            pagination: components["schemas"]["PeoplePagination"];
        };
        MessageVersionsResponse: {
            code: number;
            data: components["schemas"]["MessageVersionPage"];
            message: string;
        };
        ModuleCapabilities: {
            contract_version: number;
            modules: components["schemas"]["ModuleDescriptor"][];
            preset: string;
            scope_resources?: components["schemas"]["ScopeResource"][];
        };
        ModuleCapabilitiesResponse: {
            code: number;
            data: components["schemas"]["ModuleCapabilities"];
            message: string;
        };
        ModuleDescriptor: {
            dependencies: string[];
            enabled: boolean;
            key: string;
            page_permissions?: {
                [key: string]: string;
            };
            paths: string[];
            title: string;
        };
        Monitor: {
            cpu: components["schemas"]["Cpu"];
            disks: components["schemas"]["Disk"][];
            memory: components["schemas"]["Memory"];
            processes: components["schemas"]["Process"][];
            processes_supported: boolean;
            processes_truncated: boolean;
            /** Format: date-time */
            sampled_at: string;
            scope: components["schemas"]["MonitorScopeEnum"];
        };
        /**
         * @description * `container` - container
         *     * `host` - host
         * @enum {string}
         */
        MonitorScopeEnum: "container" | "host";
        MyMenuResponse: {
            code: number;
            data: components["schemas"]["Menu"][];
            message: string;
        };
        MyTenant: {
            /** Format: uuid */
            id: string;
            name: string;
            role: string;
            slug: string;
        };
        Namespace: {
            candidate_count: number;
            module: string;
            namespace: components["schemas"]["NamespaceEnum"];
            over_limit: boolean;
        };
        /**
         * @description * `configuration` - configuration
         *     * `dictionaries` - dictionaries
         * @enum {string}
         */
        NamespaceEnum: "configuration" | "dictionaries";
        /** @description 通知序列化 */
        Notification: {
            /** 内容 */
            readonly content: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 附加数据 */
            readonly data: unknown;
            /** Format: uuid */
            readonly id: string;
            /** 是否已读 */
            readonly is_read: boolean;
            /** 跳转链接（前端路由） */
            readonly link: string;
            /** 通知类型 */
            readonly notification_type: components["schemas"]["NotificationTypeEnum"];
            /**
             * 已读时间
             * Format: date-time
             */
            readonly read_at: string | null;
            /**
             * 接收者
             * Format: uuid
             */
            readonly recipient: string;
            /**
             * 发送者（系统通知为空）
             * Format: uuid
             */
            readonly sender: string | null;
            readonly sender_name: string;
            /** 标题 */
            readonly title: string;
        };
        /** @description 发送通知（管理员） */
        NotificationCreateRequest: {
            /** @default  */
            content: string;
            data?: unknown;
            /** @default  */
            link: string;
            /** @default system */
            notification_type: components["schemas"]["NotificationTypeEnum"];
            recipient_ids: string[];
            title: string;
        };
        NotificationDetailResponse: {
            code: number;
            data: components["schemas"]["Notification"];
            message: string;
        };
        NotificationMetric: {
            counts: {
                [key: string]: number;
            } | null;
            /** Format: double */
            oldest_failed_seconds: number | null;
            /** Format: double */
            oldest_pending_seconds: number | null;
            status: components["schemas"]["QueueMetricStatusEnum"];
        };
        NotificationReadResponse: {
            code: number;
            data: components["schemas"]["Notification"];
            message: string;
        };
        NotificationSentResponse: {
            code: number;
            data: components["schemas"]["SentCount"];
            message: string;
        };
        NotificationsReadResponse: {
            code: number;
            data: components["schemas"]["UpdatedCount"];
            message: string;
        };
        /**
         * @description * `system` - 系统通知
         *     * `approval` - 审批通知
         *     * `task` - 任务通知
         *     * `announcement` - 公告
         * @enum {string}
         */
        NotificationTypeEnum: "system" | "approval" | "task" | "announcement";
        OfficePreviewConfiguration: {
            code: number;
            data: unknown;
            message: string;
        };
        OfficePreviewStatus: {
            code: number;
            data: components["schemas"]["OfficeStatus"];
            message: string;
        };
        OfficePreviewSubmitted: {
            code: number;
            data: components["schemas"]["OfficeStatus"];
            message: string;
        };
        OfficeStatus: {
            error: string;
            /** Format: date-time */
            expires_at: string;
            /** Format: uuid */
            id: string;
            status: string;
        };
        OfficeSubmitRequest: {
            lifecycle_version: number;
        };
        OnlineUser: {
            /** 名字 */
            readonly first_name: string;
            /** Format: uuid */
            readonly id: string;
            readonly is_current_user: boolean;
            /** 姓氏 */
            readonly last_name: string;
            /** Format: date-time */
            readonly last_seen_at: string;
            readonly session_count: number;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            readonly username: string;
        };
        OnlineUserRevoked: {
            code: number;
            data: components["schemas"]["SessionRevokeResult"];
            message: string;
        };
        /**
         * @description * `create` - 创建
         *     * `read` - 查看
         *     * `update` - 修改
         *     * `delete` - 删除
         *     * `export` - 导出
         *     * `import` - 导入
         *     * `download` - 下载
         *     * `upload` - 上传
         *     * `login` - 登录
         *     * `logout` - 登出
         *     * `other` - 其他
         * @enum {string}
         */
        OperationActionEnum: "create" | "read" | "update" | "delete" | "export" | "import" | "download" | "upload" | "login" | "logout" | "other";
        /** @description 操作日志序列化器 */
        OperationLog: {
            /** 操作类型 */
            readonly action: components["schemas"]["OperationActionEnum"];
            readonly actor_identifier: string;
            readonly after_values: unknown;
            readonly audit_version: number;
            readonly batch_results: unknown;
            readonly before_values: unknown;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 描述 */
            readonly description: string;
            /** Format: uuid */
            readonly id: string;
            /** IP 地址 */
            readonly ip_address: string;
            readonly request_id: string;
            /** 资源类型 */
            readonly resource: string;
            /** 资源 ID */
            readonly resource_id: string;
            /** 状态码 */
            readonly status: number;
            readonly task_id: string;
            /** Format: uuid */
            readonly task_record_id: string | null;
            readonly username: string;
        };
        /** @description 结构化大字段按需在详情读取，避免分页响应重复携带。 */
        OperationLogList: {
            /** 操作类型 */
            readonly action: components["schemas"]["OperationActionEnum"];
            readonly actor_identifier: string;
            readonly audit_version: number;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 描述 */
            readonly description: string;
            /** Format: uuid */
            readonly id: string;
            /** IP 地址 */
            readonly ip_address: string;
            readonly request_id: string;
            /** 资源类型 */
            readonly resource: string;
            /** 资源 ID */
            readonly resource_id: string;
            /** 状态码 */
            readonly status: number;
            readonly task_id: string;
            /** Format: uuid */
            readonly task_record_id: string | null;
            readonly username: string;
        };
        OutboxDetailResponse: {
            code: number;
            data: components["schemas"]["OutboxEvent"];
            message: string;
        };
        OutboxEvent: {
            readonly attempts: number;
            /** Format: date-time */
            readonly available_at: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly last_error: string;
            /** Format: date-time */
            readonly published_at: string | null;
            readonly request_id: string;
            readonly status: components["schemas"]["OutboxEventStatusEnum"];
            readonly topic: string;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
        };
        /**
         * @description * `pending` - 待派发
         *     * `processing` - 派发中
         *     * `succeeded` - 已完成
         *     * `failed` - 失败
         * @enum {string}
         */
        OutboxEventStatusEnum: "pending" | "processing" | "succeeded" | "failed";
        OutboxRetryResponse: {
            code: number;
            data: components["schemas"]["OutboxEvent"];
            message: string;
        };
        PaginatedAnnouncementList: {
            code: number;
            data: {
                items: components["schemas"]["Announcement"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedApprovalFlowList: {
            code: number;
            data: {
                items: components["schemas"]["ApprovalFlow"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedApprovalRequestList: {
            code: number;
            data: {
                items: components["schemas"]["ApprovalRequest"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedCredentialList: {
            code: number;
            data: {
                items: components["schemas"]["Credential"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedDepartmentList: {
            code: number;
            data: {
                items: components["schemas"]["Department"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedDictionaryList: {
            code: number;
            data: {
                items: components["schemas"]["Dictionary"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedExceptionLogList: {
            code: number;
            data: {
                items: components["schemas"]["ExceptionLog"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedFeatureFlagList: {
            code: number;
            data: {
                items: components["schemas"]["FeatureFlag"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedFileList: {
            code: number;
            data: {
                items: components["schemas"]["File"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedIdentityList: {
            code: number;
            data: {
                items: components["schemas"]["Identity"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedLoginLogList: {
            code: number;
            data: {
                items: components["schemas"]["LoginLog"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedMembershipList: {
            code: number;
            data: {
                items: components["schemas"]["Membership"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedMenuList: {
            code: number;
            data: {
                items: components["schemas"]["Menu"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedMessageDeliveryList: {
            code: number;
            data: {
                items: components["schemas"]["MessageDelivery"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedMessageTemplateList: {
            code: number;
            data: {
                items: components["schemas"]["MessageTemplate"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedNotificationList: {
            code: number;
            data: {
                items: components["schemas"]["Notification"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedOnlineUserList: {
            code: number;
            data: {
                items: components["schemas"]["OnlineUser"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedOperationLogListList: {
            code: number;
            data: {
                items: components["schemas"]["OperationLogList"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedOutboxEventList: {
            code: number;
            data: {
                items: components["schemas"]["OutboxEvent"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedPermissionList: {
            code: number;
            data: {
                items: components["schemas"]["Permission"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedPersonalSessionList: {
            code: number;
            data: {
                items: components["schemas"]["PersonalSession"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedPostList: {
            code: number;
            data: {
                items: components["schemas"]["Post"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedRoleList: {
            code: number;
            data: {
                items: components["schemas"]["Role"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedScopeGrantList: {
            code: number;
            data: {
                items: components["schemas"]["ScopeGrant"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedTaskRecordList: {
            code: number;
            data: {
                items: components["schemas"]["TaskRecord"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedTaskSummaryList: {
            code: number;
            data: {
                items: components["schemas"]["TaskSummary"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedTenantList: {
            code: number;
            data: {
                items: components["schemas"]["Tenant"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedTenantMembershipList: {
            code: number;
            data: {
                items: components["schemas"]["TenantMembership"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedUserListList: {
            code: number;
            data: {
                items: components["schemas"]["UserList"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedUserPostList: {
            code: number;
            data: {
                items: components["schemas"]["UserPost"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedWorkItemList: {
            code: number;
            data: {
                items: components["schemas"]["WorkItem"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PaginatedWorkItemSummaryList: {
            code: number;
            data: {
                items: components["schemas"]["WorkItemSummary"][];
                pagination: {
                    page?: number;
                    page_size?: number;
                    total?: number;
                    total_pages?: number;
                };
            };
            message: string;
        };
        PasswordConfirmationRequest: {
            current_password: string;
        };
        PatchedAnnouncementWriteRequest: {
            content?: string;
            /**
             * @description plain 为纯文本（创建默认值）；html 为服务端消毒后的受控 HTML。编辑未传时保持现有格式。
             *
             *     * `plain` - 纯文本
             *     * `html` - HTML
             */
            content_format?: components["schemas"]["ContentFormatEnum"];
            title?: string;
            version?: number;
        };
        PatchedConfigWriteRequest: {
            value?: unknown;
            version?: number;
        };
        PatchedDepartmentRequest: {
            is_active?: boolean;
            name?: string;
            /** Format: int64 */
            order?: number;
            /** Format: uuid */
            parent?: string | null;
            version?: number;
        };
        PatchedDictionaryRequest: {
            code?: string;
            description?: string;
            is_active?: boolean;
            items?: unknown;
            name?: string;
            version?: number;
        };
        PatchedFeatureFlagRequest: {
            description?: string;
            enabled?: boolean;
            excluded_users?: string[];
            included_users?: string[];
            key?: string;
            name?: string;
            roles?: string[];
            rollout?: number;
            version?: number;
        };
        PatchedMembershipRequest: {
            /** Format: uuid */
            department?: string;
            /** Format: uuid */
            user?: string;
            version?: number;
        };
        /** @description 菜单序列化器 */
        PatchedMenuRequest: {
            /** 图标 */
            icon?: string;
            /** 是否可见 */
            is_visible?: boolean;
            /** 菜单名 */
            name?: string;
            /**
             * 排序
             * Format: int64
             */
            order?: number;
            /**
             * 父菜单
             * Format: uuid
             */
            parent?: string | null;
            /** 路由路径 */
            path?: string;
            /**
             * 所需权限
             * Format: uuid
             */
            permission?: string | null;
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        PatchedPostRequest: {
            code?: string;
            description?: string;
            is_active?: boolean;
            name?: string;
            /** Format: int64 */
            order?: number;
            version?: number;
        };
        PatchedProfileWriteRequest: {
            bio?: string;
            email?: string;
            first_name?: string;
            last_name?: string;
            phone?: string;
            profile_version?: number;
        };
        /** @description 角色序列化器 */
        PatchedRoleRequest: {
            /** 描述 */
            description?: string;
            field_permissions?: unknown;
            /** 是否激活 */
            is_active?: boolean;
            /** 角色名 */
            name?: string;
            permission_ids?: string[];
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        PatchedScheduleWriteRequest: {
            day_of_month?: string;
            day_of_week?: string;
            enabled?: boolean;
            hour?: string;
            minute?: string;
            month_of_year?: string;
            options?: unknown;
            revision?: string;
            timezone?: string;
        };
        PatchedScopeGrantRequest: {
            departments?: string[];
            resource?: components["schemas"]["ScopeGrantResourceEnum"];
            /** Format: uuid */
            role?: string;
            scope?: components["schemas"]["ScopeGrantScopeEnum"];
            version?: number;
        };
        PatchedTemplateWriteRequest: {
            body?: string;
            code?: string;
            /** @default true */
            enabled: boolean;
            name?: string;
            revision?: number;
            subject?: string;
            variables?: string[];
        };
        PatchedTenantMembershipRequest: {
            is_active?: boolean;
            role?: components["schemas"]["RoleEnum"];
            /** Format: uuid */
            tenant?: string;
            /** Format: uuid */
            user?: string;
        };
        PatchedTenantRequest: {
            name?: string;
            slug?: string;
            status?: components["schemas"]["TenantStatusEnum"];
        };
        /** @description 用户修改序列化器 */
        PatchedUserUpdateRequest: {
            /** 头像 */
            avatar?: string;
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            phone?: string;
            role_ids?: string[];
            /** @description 更新时必填：读取详情返回的 version；版本过期返回 409 且不写入。 */
            version?: number;
        };
        PatchedWorkItemRequest: {
            notes?: string;
            priority?: components["schemas"]["PriorityEnum"];
            status?: components["schemas"]["WorkItemStatusEnum"];
            title?: string;
            version?: number;
        };
        PeoplePage: {
            items: components["schemas"]["Person"][];
            pagination: components["schemas"]["PeoplePagination"];
        };
        PeoplePagination: {
            page: number;
            page_size: number;
            total: number;
            total_pages: number;
        };
        /** @description 权限序列化器 */
        Permission: {
            /** 操作 */
            action: string;
            /** 权限代码 */
            code: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 描述 */
            description?: string;
            /** Format: uuid */
            readonly id: string;
            /** 权限名 */
            name: string;
            /** 资源 */
            resource: string;
        };
        PermissionDetailResponse: {
            code: number;
            data: components["schemas"]["Permission"];
            message: string;
        };
        /** @description 权限序列化器 */
        PermissionRequest: {
            /** 操作 */
            action: string;
            /** 权限代码 */
            code: string;
            /** 描述 */
            description?: string;
            /** 权限名 */
            name: string;
            /** 资源 */
            resource: string;
        };
        Person: {
            /** Format: uuid */
            readonly department: string | null;
            readonly department_name: string | null;
            readonly display_name: string;
            /** Format: uuid */
            readonly id: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        PersonalProfileResponse: {
            code: number;
            data: components["schemas"]["ProfileRead"];
            message: string;
        };
        PersonalProfileUpdatedResponse: {
            code: number;
            data: components["schemas"]["ProfileRead"];
            message: string;
        };
        PersonalSession: {
            readonly active: boolean;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly expires_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly ip_address: string | null;
            readonly is_current: boolean;
            /** Format: date-time */
            readonly last_seen_at: string;
            readonly user_agent: string;
        };
        PersonnelPageResponse: {
            code: number;
            data: components["schemas"]["PeoplePage"];
            message: string;
        };
        PickerDepartment: {
            /** Format: uuid */
            id: string;
            name: string;
            /** Format: uuid */
            parent: string | null;
        };
        PickerDepartments: {
            enabled: boolean;
            items: components["schemas"]["PickerDepartment"][];
            truncated: boolean;
        };
        PolicyPreviewRequest: {
            allow: string[];
            deny: string[];
            enabled: boolean;
        };
        /**
         * @description * `bottom-right` - bottom-right
         *     * `center` - center
         * @enum {string}
         */
        PositionEnum: "bottom-right" | "center";
        Post: {
            code: string;
            description?: string;
            /** Format: uuid */
            readonly id: string;
            is_active?: boolean;
            name: string;
            /** Format: int64 */
            order?: number;
            version: number;
        };
        PostChoicesResponse: {
            code: number;
            data: components["schemas"]["Post"][];
            message: string;
        };
        PostCreatedResponse: {
            code: number;
            data: components["schemas"]["Post"];
            message: string;
        };
        PostDetailResponse: {
            code: number;
            data: components["schemas"]["Post"];
            message: string;
        };
        PostPatchedResponse: {
            code: number;
            data: components["schemas"]["Post"];
            message: string;
        };
        PostPersonnelDepartmentsResponse: {
            code: number;
            data: components["schemas"]["PickerDepartments"];
            message: string;
        };
        PostRequest: {
            code: string;
            description?: string;
            is_active?: boolean;
            name: string;
            /** Format: int64 */
            order?: number;
            version: number;
        };
        PostUpdatedResponse: {
            code: number;
            data: components["schemas"]["Post"];
            message: string;
        };
        PreviewRequestRequest: {
            namespace: components["schemas"]["NamespaceEnum"];
        };
        PreviewResult: {
            backend: string;
            candidate_count: number;
            expires_in: number;
            namespace: string;
            token: string;
        };
        /**
         * @description * `normal` - 普通
         *     * `high` - 高
         * @enum {string}
         */
        PriorityEnum: "normal" | "high";
        Process: {
            /** Format: double */
            cpu_seconds: number;
            kind: components["schemas"]["KindEnum"];
            pid: number;
            rss_bytes: number;
            state: string;
            /** Format: double */
            uptime_seconds: number;
        };
        /** @description 用户序列化器 */
        ProfileRead: {
            /** 头像 */
            avatar?: string;
            readonly avatar_enabled: boolean;
            readonly bio: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 电子邮件地址 */
            email?: string;
            readonly email_verified: boolean;
            /** 名字 */
            first_name?: string;
            readonly has_avatar: boolean;
            /** Format: uuid */
            readonly id: string;
            /** 是否激活 */
            is_active?: boolean;
            /**
             * 工作人员状态
             * @description 指明用户是否可以登录到这个管理站点。
             */
            is_staff?: boolean;
            /**
             * 超级用户状态
             * @description 指明该用户缺省拥有所有权限。
             */
            is_superuser?: boolean;
            /** 姓氏 */
            last_name?: string;
            /** 下次登录必须修改密码 */
            must_change_password?: boolean;
            readonly permissions: string[];
            /** 电话 */
            phone?: string;
            /**
             * 个人资料版本
             * Format: int64
             */
            profile_version?: number;
            readonly recovery_enabled: boolean;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        QueueMetric: {
            counts: {
                [key: string]: number;
            } | null;
            /** Format: double */
            oldest_failed_seconds: number | null;
            /** Format: double */
            oldest_pending_seconds: number | null;
        };
        /**
         * @description * `ok` - ok
         *     * `unavailable` - unavailable
         *     * `disabled` - disabled
         * @enum {string}
         */
        QueueMetricStatusEnum: "ok" | "unavailable" | "disabled";
        RecoveryConfig: {
            enabled: boolean;
        };
        RecoveryConfigResponse: {
            code: number;
            data: components["schemas"]["RecoveryConfig"];
            message: string;
        };
        RecoveryRequestRequest: {
            /** Format: email */
            email: string;
            username: string;
        };
        RecoveryResetRequest: {
            code: string;
            new_password: string;
            new_password2: string;
        };
        /**
         * @description * `restore` - restore
         *     * `purge` - purge
         * @enum {string}
         */
        RecycleActionActionEnum: "restore" | "purge";
        RecycleActionRequest: {
            action: components["schemas"]["RecycleActionActionEnum"];
            confirmation?: string;
            /** @default false */
            dry_run: boolean;
            items: components["schemas"]["RecycleItemRequest"][];
        };
        RecycleItemRequest: {
            /** Format: uuid */
            id: string;
            lifecycle_version: number;
        };
        RecyclePolicy: {
            cleanup_enabled: boolean;
            retention_days: number;
        };
        RecycleResult: {
            dry_run: boolean;
            failed: number;
            results: components["schemas"]["RecycleResultItem"][];
            succeeded: number;
        };
        RecycleResultItem: {
            /** Format: uuid */
            id: string;
            message: string;
            original_name?: string;
            size?: number;
            status: number;
        };
        RefreshRequestRequest: {
            refresh: string;
        };
        RefreshResponse: {
            code: number;
            data: components["schemas"]["TokenPair"];
            message: string;
        };
        RegisteredSession: {
            access: string;
            refresh: string;
            user: components["schemas"]["User"];
        };
        RegisterResponse: {
            code: number;
            data: components["schemas"]["RegisteredSession"];
            message: string;
        };
        /**
         * @description * `leave` - 请假
         *     * `purchase` - 采购
         *     * `permission` - 权限申请
         *     * `other` - 其他
         * @enum {string}
         */
        RequestTypeEnum: "leave" | "purchase" | "permission" | "other";
        ResetPasswordRequestRequest: {
            /** @default true */
            must_change_password: boolean;
            password: string;
        };
        RestoreRequest: {
            lifecycle_version: number;
        };
        ResumableUploadCompleteResponse: {
            code: number;
            data: components["schemas"]["File"];
            message: string;
        };
        /** @description 角色序列化器 */
        Role: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 描述 */
            description?: string;
            field_permissions?: unknown;
            /** Format: uuid */
            readonly id: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 角色名 */
            name: string;
            readonly permissions: components["schemas"]["Permission"][];
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        RoleCreatedResponse: {
            code: number;
            data: components["schemas"]["Role"];
            message: string;
        };
        RoleDetailResponse: {
            code: number;
            data: components["schemas"]["Role"];
            message: string;
        };
        /**
         * @description * `owner` - 所有者
         *     * `admin` - 管理员
         *     * `member` - 成员
         * @enum {string}
         */
        RoleEnum: "owner" | "admin" | "member";
        RolePatchedResponse: {
            code: number;
            data: components["schemas"]["Role"];
            message: string;
        };
        /** @description 角色序列化器 */
        RoleRequest: {
            /** 描述 */
            description?: string;
            field_permissions?: unknown;
            /** 是否激活 */
            is_active?: boolean;
            /** 角色名 */
            name: string;
            permission_ids?: string[];
            /** @description 更新时必须传当前 version；新建省略或传 0；版本过期返回 409 且不写入。 */
            version?: number;
        };
        RoleUpdatedResponse: {
            code: number;
            data: components["schemas"]["Role"];
            message: string;
        };
        ScheduleRow: {
            confirmation: string;
            cron: unknown;
            enabled: boolean;
            key: string;
            last_run: components["schemas"]["TaskRecord"] | null;
            missing: boolean;
            module_enabled: boolean;
            name: string;
            options: unknown;
            overlap: string;
            preview: unknown;
            requires_preview: boolean;
            revision: string;
            supported: boolean;
            task: string;
            time_limit_seconds: number;
        };
        ScheduleRunRequest: {
            confirmation?: string;
            options: unknown;
            /** Format: uuid */
            preview_id?: string | null;
            revision: string;
        };
        ScopeCreatedResponse: {
            code: number;
            data: components["schemas"]["ScopeGrant"];
            message: string;
        };
        ScopeDetailResponse: {
            code: number;
            data: components["schemas"]["ScopeGrant"];
            message: string;
        };
        ScopeGrant: {
            departments?: string[];
            /** Format: uuid */
            readonly id: string;
            resource: components["schemas"]["ScopeGrantResourceEnum"];
            /** Format: uuid */
            role: string;
            readonly role_name: string;
            scope?: components["schemas"]["ScopeGrantScopeEnum"];
            version: number;
        };
        ScopeGrantRequest: {
            departments?: string[];
            resource: components["schemas"]["ScopeGrantResourceEnum"];
            /** Format: uuid */
            role: string;
            scope?: components["schemas"]["ScopeGrantScopeEnum"];
            version: number;
        };
        /**
         * @description * `user` - 用户
         *     * `file` - 文件
         *     * `task` - 任务
         *     * `log` - 日志
         *     * `example` - 示例工单
         * @enum {string}
         */
        ScopeGrantResourceEnum: "user" | "file" | "task" | "log" | "example";
        /**
         * @description * `self` - 本人
         *     * `department` - 本部门
         *     * `department_tree` - 部门及下级
         *     * `custom` - 自定义部门
         *     * `all` - 全部
         * @enum {string}
         */
        ScopeGrantScopeEnum: "self" | "department" | "department_tree" | "custom" | "all";
        ScopePatchedResponse: {
            code: number;
            data: components["schemas"]["ScopeGrant"];
            message: string;
        };
        ScopeResource: {
            key: string;
            title: string;
        };
        ScopeUpdatedResponse: {
            code: number;
            data: components["schemas"]["ScopeGrant"];
            message: string;
        };
        SensitiveContact: {
            readonly email: string;
            readonly phone: string;
        };
        SensitiveContactRequestRequest: {
            current_password: string;
        };
        SensitiveContactResponse: {
            code: number;
            data: components["schemas"]["SensitiveContact"];
            message: string;
        };
        SentCount: {
            sent_count: number;
        };
        SentDeliveries: {
            count: number;
            delivery_ids: string[];
        };
        Service: {
            /** Format: double */
            latency_ms: number | null;
            name: string;
            status: components["schemas"]["ServiceStatusEnum"];
            version: string | null;
        };
        /**
         * @description * `ok` - ok
         *     * `unavailable` - unavailable
         *     * `in_process` - in_process
         *     * `disabled` - disabled
         * @enum {string}
         */
        ServiceStatusEnum: "ok" | "unavailable" | "in_process" | "disabled";
        SessionRevokeResult: {
            revoked_count: number;
        };
        SSOAuthorizationResponse: {
            code: number;
            data: components["schemas"]["Authorization"];
            message: string;
        };
        SSOBoundResponse: {
            code: number;
            data: components["schemas"]["Identity"];
            message: string;
        };
        SSOCompletedResponse: {
            code: number;
            data: components["schemas"]["Completed"];
            message: string;
        };
        SSOConfigResponse: {
            code: number;
            data: components["schemas"]["Config"];
            message: string;
        };
        SSOLoginUser: {
            avatar: string;
            email: string;
            /** Format: uuid */
            id: string;
            must_change_password: boolean;
            username: string;
        };
        SSOStatusResponse: {
            code: number;
            data: components["schemas"]["Status"];
            message: string;
        };
        StartRequest: {
            captcha_code?: string;
            /** Format: uuid */
            captcha_id?: string;
        };
        Status: {
            captcha: unknown;
            mfa_required: boolean;
            ready: boolean;
        };
        SystemConfigDetailResponse: {
            code: number;
            data: components["schemas"]["ConfigRow"][];
            message: string;
        };
        SystemConfigListResponse: {
            code: number;
            data: components["schemas"]["ConfigRow"][];
            message: string;
        };
        SystemConfigWriteResponse: {
            code: number;
            data: components["schemas"]["ConfigRow"][];
            message: string;
        };
        SystemInformationResponse: {
            code: number;
            data: components["schemas"]["Information"];
            message: string;
        };
        SystemMonitorResponse: {
            code: number;
            data: components["schemas"]["Monitor"];
            message: string;
        };
        Target: {
            /** Format: uuid */
            id: string;
            label: string;
        };
        TaskCancelledResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        TaskHistoryCleanupResponse: {
            code: number;
            data: unknown;
            message: string;
        };
        TaskMetric: {
            broker: components["schemas"]["BrokerMetric"];
            correlation: components["schemas"]["CorrelationMetric"];
            notifications: components["schemas"]["NotificationMetric"];
            outbox: components["schemas"]["QueueMetric"];
            status: components["schemas"]["TaskMetricStatusEnum"];
            task_records: components["schemas"]["TaskRecordMetric"];
        };
        /**
         * @description * `ok` - ok
         *     * `degraded` - degraded
         *     * `disabled` - disabled
         * @enum {string}
         */
        TaskMetricStatusEnum: "ok" | "degraded" | "disabled";
        /** @description 任务记录序列化 */
        TaskRecord: {
            /** Celery 任务 ID */
            readonly celery_task_id: string;
            /**
             * 完成时间
             * Format: date-time
             */
            readonly completed_at: string | null;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /**
             * 创建者
             * Format: uuid
             */
            readonly creator: string | null;
            readonly creator_name: string;
            /**
             * Format: double
             * @description 执行耗时（秒），未完成任务返回 None
             */
            readonly duration: number | null;
            /** 错误信息 */
            readonly error: string;
            readonly execution: {
                [key: string]: unknown;
            } | null;
            /** Format: uuid */
            readonly id: string;
            /** 任务名称 */
            readonly name: string;
            /** 进度（0-100） */
            readonly progress: number;
            /**
             * 关联资源
             * @default
             */
            readonly related_resource: string;
            readonly request_id: string;
            /** 执行结果 */
            readonly result: unknown;
            /**
             * 开始时间
             * Format: date-time
             */
            readonly started_at: string | null;
            /**
             * 状态
             * @default pending
             */
            readonly status: components["schemas"]["TaskRecordStatusEnum"];
            /** 任务类型 */
            readonly task_type: components["schemas"]["TaskTypeEnum"];
        };
        TaskRecordMetric: {
            counts: {
                [key: string]: number;
            } | null;
            duration_seconds: components["schemas"]["DurationMetric"] | null;
            lost_candidates: components["schemas"]["LostCandidate"] | null;
        };
        /**
         * @description * `pending` - 等待执行
         *     * `running` - 执行中
         *     * `success` - 成功
         *     * `failed` - 失败
         *     * `cancelled` - 已取消
         * @enum {string}
         */
        TaskRecordStatusEnum: "pending" | "running" | "success" | "failed" | "cancelled";
        TaskResumedResponse: {
            code: number;
            data: components["schemas"]["TaskRecord"];
            message: string;
        };
        TaskSummary: {
            /**
             * 完成时间
             * Format: date-time
             */
            readonly completed_at: string | null;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            /** 任务名称 */
            readonly name: string;
            /** 进度（0-100） */
            readonly progress: number;
            /**
             * 开始时间
             * Format: date-time
             */
            readonly started_at: string | null;
            /** 状态 */
            readonly status: components["schemas"]["TaskRecordStatusEnum"];
            /** 任务类型 */
            readonly task_type: components["schemas"]["TaskTypeEnum"];
        };
        /**
         * @description * `import` - 数据导入
         *     * `export` - 数据导出
         *     * `backup` - 数据备份
         *     * `cleanup` - 数据清理
         *     * `notification` - 通知发送
         *     * `other` - 其他
         * @enum {string}
         */
        TaskTypeEnum: "import" | "export" | "backup" | "cleanup" | "notification" | "other";
        TemplatePreviewRequest: {
            revision: number;
            values: {
                [key: string]: string;
            };
        };
        TemplateSendRequest: {
            channels: components["schemas"]["MessageChannelEnum"][];
            recipient_ids: string[];
            revision: number;
            values: {
                [key: string]: string;
            };
        };
        TemplateVersion: {
            readonly body: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly number: number;
            readonly subject: string;
            readonly variables: unknown;
        };
        TemplateWriteRequest: {
            body: string;
            code: string;
            /** @default true */
            enabled: boolean;
            name: string;
            revision: number;
            subject: string;
            variables: string[];
        };
        Tenant: {
            /** Format: date-time */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            name: string;
            slug: string;
            status?: components["schemas"]["TenantStatusEnum"];
            /** Format: date-time */
            readonly updated_at: string;
        };
        TenantMembership: {
            /** Format: date-time */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            is_active?: boolean;
            role?: components["schemas"]["RoleEnum"];
            /** Format: uuid */
            tenant: string;
            readonly tenant_name: string;
            /** Format: date-time */
            readonly updated_at: string;
            /** Format: uuid */
            user: string;
            readonly username: string;
        };
        TenantMembershipRequest: {
            is_active?: boolean;
            role?: components["schemas"]["RoleEnum"];
            /** Format: uuid */
            tenant: string;
            /** Format: uuid */
            user: string;
        };
        TenantRequest: {
            name: string;
            slug: string;
            status?: components["schemas"]["TenantStatusEnum"];
        };
        /**
         * @description * `active` - 正常
         *     * `suspended` - 暂停
         *     * `closed` - 已关闭
         * @enum {string}
         */
        TenantStatusEnum: "active" | "suspended" | "closed";
        TokenPair: {
            access: string;
            refresh: string;
        };
        TOTPChangeResponse: {
            code: number;
            data: components["schemas"]["TOTPResult"];
            message: string;
        };
        TOTPPasswordRequestRequest: {
            current_password: string;
        };
        TOTPProofRequestRequest: {
            current_password: string;
            otp_code: string;
        };
        TOTPResult: {
            access: string;
            recovery_codes?: string[];
            refresh: string;
            user: components["schemas"]["User"];
        };
        TOTPSetup: {
            /** Format: date-time */
            expires_at: string;
            otpauth_uri: string;
            secret: string;
        };
        TOTPSetupResponse: {
            code: number;
            data: components["schemas"]["TOTPSetup"];
            message: string;
        };
        TOTPStatus: {
            available: boolean;
            enabled: boolean;
            recovery_codes_remaining: number;
        };
        TOTPStatusResponse: {
            code: number;
            data: components["schemas"]["TOTPStatus"];
            message: string;
        };
        UnbindRequest: {
            current_password: string;
        };
        UnreadCount: {
            count: number;
        };
        UnreadCountResponse: {
            code: number;
            data: components["schemas"]["UnreadCount"];
            message: string;
        };
        UpdatedCount: {
            updated: number;
        };
        /** @description 用户序列化器 */
        User: {
            /** 头像 */
            avatar?: string;
            readonly avatar_enabled: boolean;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 电子邮件地址 */
            email?: string;
            readonly email_verified: boolean;
            /** 名字 */
            first_name?: string;
            readonly has_avatar: boolean;
            /** Format: uuid */
            readonly id: string;
            /** 是否激活 */
            is_active?: boolean;
            /**
             * 工作人员状态
             * @description 指明用户是否可以登录到这个管理站点。
             */
            is_staff?: boolean;
            /**
             * 超级用户状态
             * @description 指明该用户缺省拥有所有权限。
             */
            is_superuser?: boolean;
            /** 姓氏 */
            last_name?: string;
            /** 下次登录必须修改密码 */
            must_change_password?: boolean;
            readonly permissions: string[];
            /** 电话 */
            phone?: string;
            /**
             * 个人资料版本
             * Format: int64
             */
            profile_version?: number;
            readonly recovery_enabled: boolean;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        /** @description 用户创建序列化器 */
        UserCreate: {
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            /**
             * 下次登录必须修改密码
             * @default true
             */
            must_change_password: boolean;
            phone?: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        UserCreatedResponse: {
            code: number;
            data: components["schemas"]["UserCreate"];
            message: string;
        };
        /** @description 用户创建序列化器 */
        UserCreateRequest: {
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            /**
             * 下次登录必须修改密码
             * @default true
             */
            must_change_password: boolean;
            password: string;
            phone?: string;
            role_ids?: string[];
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        /** @description 用户详细序列化器 */
        UserDetail: {
            /** 头像 */
            avatar?: string;
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** Format: uuid */
            readonly id: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            /** 登录次数 */
            readonly login_count: number;
            /** 电话 */
            phone?: string;
            readonly profile: components["schemas"]["UserProfile"];
            /** @description 获取用户角色 */
            readonly roles: {
                [key: string]: unknown;
            }[];
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
            readonly version: number;
        };
        UserDetailResponse: {
            code: number;
            data: components["schemas"]["UserDetail"];
            message: string;
        };
        /** @description 用户列表序列化器 */
        UserList: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** Format: uuid */
            readonly id: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            /**
             * 登录次数
             * Format: int64
             */
            login_count?: number;
            /** 电话 */
            phone?: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
            readonly version: number;
        };
        UserPatchedResponse: {
            code: number;
            data: components["schemas"]["UserUpdate"];
            message: string;
        };
        UserPost: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            post: string;
            readonly post_active: boolean;
            readonly post_name: string;
            /** Format: uuid */
            user: string;
            readonly user_active: boolean;
            readonly username: string;
            version: number;
        };
        UserPostCreatedResponse: {
            code: number;
            data: components["schemas"]["UserPost"];
            message: string;
        };
        UserPostDetailResponse: {
            code: number;
            data: components["schemas"]["UserPost"];
            message: string;
        };
        UserPostRequest: {
            /** Format: uuid */
            post: string;
            /** Format: uuid */
            user: string;
            version: number;
        };
        /** @description 用户资料序列化器 */
        UserProfile: {
            /** 个人简介 */
            bio?: string;
            /** 部门 */
            department?: string;
            /** 电话 */
            phone?: string;
            /** 职位 */
            position?: string;
        };
        /** @description 用户注册序列化器 */
        UserRegistrationRequest: {
            /** 电子邮件地址 */
            email?: string;
            password: string;
            password2: string;
            /**
             * 用户名
             * @description 必填；长度为150个字符或以下；只能包含字母、数字、特殊字符“@”、“.”、“-”和“_”。
             */
            username: string;
        };
        /** @description 用户修改序列化器 */
        UserUpdate: {
            /** 头像 */
            avatar?: string;
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            phone?: string;
            /** @description 更新时必填：读取详情返回的 version；版本过期返回 409 且不写入。 */
            version?: number;
        };
        UserUpdatedResponse: {
            code: number;
            data: components["schemas"]["UserUpdate"];
            message: string;
        };
        /** @description 用户修改序列化器 */
        UserUpdateRequest: {
            /** 头像 */
            avatar?: string;
            /** 电子邮件地址 */
            email?: string;
            /** 名字 */
            first_name?: string;
            /** 是否激活 */
            is_active?: boolean;
            /** 姓氏 */
            last_name?: string;
            phone?: string;
            role_ids?: string[];
            /** @description 更新时必填：读取详情返回的 version；版本过期返回 409 且不写入。 */
            version?: number;
        };
        VerificationRequestRequest: {
            current_password: string;
        };
        WorkItem: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly creator: string;
            readonly creator_name: string;
            /** Format: uuid */
            readonly id: string;
            notes?: string;
            priority?: components["schemas"]["PriorityEnum"];
            status?: components["schemas"]["WorkItemStatusEnum"];
            title: string;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            version: number;
        };
        WorkItemRequest: {
            notes?: string;
            priority?: components["schemas"]["PriorityEnum"];
            status?: components["schemas"]["WorkItemStatusEnum"];
            title: string;
            version: number;
        };
        /**
         * @description * `open` - 待处理
         *     * `done` - 已完成
         * @enum {string}
         */
        WorkItemStatusEnum: "open" | "done";
        WorkItemSummary: {
            /**
             * 创建时间
             * Format: date-time
             */
            readonly created_at: string;
            /** Format: uuid */
            readonly id: string;
            readonly priority: components["schemas"]["PriorityEnum"];
            readonly status: components["schemas"]["WorkItemStatusEnum"];
            readonly title: string;
            /**
             * 更新时间
             * Format: date-time
             */
            readonly updated_at: string;
            readonly version: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    api_credentials_credentials_list: {
        parameters: {
            query?: {
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedCredentialList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    api_credentials_credentials_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CredentialCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CredentialCreateRequest"];
                "multipart/form-data": components["schemas"]["CredentialCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CredentialIssuedResponse"];
                };
            };
        };
    };
    api_credentials_credentials_revoke_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordConfirmationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PasswordConfirmationRequest"];
                "multipart/form-data": components["schemas"]["PasswordConfirmationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    api_credentials_credentials_scopes_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CredentialScopes"];
                };
            };
        };
    };
    api_credentials_tasks_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, started_at, completed_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `pending` - 等待执行
                 *     * `running` - 执行中
                 *     * `success` - 成功
                 *     * `failed` - 失败
                 *     * `cancelled` - 已取消
                 */
                status?: "cancelled" | "failed" | "pending" | "running" | "success";
                /**
                 * @description * `import` - 数据导入
                 *     * `export` - 数据导出
                 *     * `backup` - 数据备份
                 *     * `cleanup` - 数据清理
                 *     * `notification` - 通知发送
                 *     * `other` - 其他
                 */
                task_type?: "backup" | "cleanup" | "export" | "import" | "notification" | "other";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedTaskSummaryList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    api_credentials_tasks_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayTaskDetail"];
                };
            };
        };
    };
    api_credentials_work_items_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, updated_at, priority。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /**
                 * @description * `normal` - 普通
                 *     * `high` - 高
                 */
                priority?: "high" | "normal";
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `open` - 待处理
                 *     * `done` - 已完成
                 */
                status?: "done" | "open";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedWorkItemSummaryList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    api_credentials_work_items_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayWorkItemDetail"];
                };
            };
        };
    };
    approvals_list: {
        parameters: {
            query?: {
                /** @description 资源查询视角；无此参数时使用默认范围。 */
                box?: "" | "todo" | "done" | "sent";
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, decided_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /**
                 * @description * `leave` - 请假
                 *     * `purchase` - 采购
                 *     * `permission` - 权限申请
                 *     * `other` - 其他
                 */
                request_type?: "leave" | "other" | "permission" | "purchase";
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `pending` - 待审批
                 *     * `approved` - 已通过
                 *     * `rejected` - 已驳回
                 *     * `cancelled` - 已撤回
                 */
                status?: "approved" | "cancelled" | "pending" | "rejected";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedApprovalRequestList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    approvals_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalCreateRequest"];
                "multipart/form-data": components["schemas"]["ApprovalCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalCreatedResponse"];
                };
            };
        };
    };
    approvals_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRequest"];
                };
            };
        };
    };
    approvals_add_sign_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRequest"];
                };
            };
        };
    };
    approvals_approve_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ApprovalDecisionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalDecisionRequest"];
                "multipart/form-data": components["schemas"]["ApprovalDecisionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalApprovedResponse"];
                };
            };
        };
    };
    approvals_cancel_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalCancelledResponse"];
                };
            };
        };
    };
    approvals_cc_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRequest"];
                };
            };
        };
    };
    approvals_delegate_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRequest"];
                };
            };
        };
    };
    approvals_reject_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ApprovalDecisionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalDecisionRequest"];
                "multipart/form-data": components["schemas"]["ApprovalDecisionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRejectedResponse"];
                };
            };
        };
    };
    approvals_transfer_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 审批申请 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalRequest"];
                };
            };
        };
    };
    approvals_assignee_departments_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalPickerDepartmentsResponse"];
                };
            };
        };
    };
    approvals_assignees_retrieve: {
        parameters: {
            query?: {
                department?: string;
                page?: number;
                page_size?: number;
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalAssigneesResponse"];
                };
            };
        };
    };
    approvals_flows_list: {
        parameters: {
            query?: {
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedApprovalFlowList"];
                };
            };
        };
    };
    approvals_flows_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalFlowDesignRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalFlowDesignRequest"];
                "multipart/form-data": components["schemas"]["ApprovalFlowDesignRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlowDesign"];
                };
            };
        };
    };
    approvals_flows_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 approval flow 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlow"];
                };
            };
        };
    };
    approvals_flows_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 approval flow 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalFlowDesignRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalFlowDesignRequest"];
                "multipart/form-data": components["schemas"]["ApprovalFlowDesignRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlowDesign"];
                };
            };
        };
    };
    approvals_flows_archive_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 approval flow 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalFlowRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalFlowRequest"];
                "multipart/form-data": components["schemas"]["ApprovalFlowRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlow"];
                };
            };
        };
    };
    approvals_flows_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 approval flow 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalFlowRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ApprovalFlowRequest"];
                "multipart/form-data": components["schemas"]["ApprovalFlowRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalFlow"];
                };
            };
        };
    };
    auth_avatar_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "image/png": Blob;
                };
            };
        };
    };
    auth_avatar_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["AvatarUploadRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AvatarUpdatedResponse"];
                };
            };
        };
    };
    auth_avatar_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    auth_change_password_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ChangePasswordRequest"];
                "multipart/form-data": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_email_verification_confirm_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CodeRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EmailVerificationProfileResponse"];
                };
            };
        };
    };
    auth_email_verification_request_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerificationRequestRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_login_captcha_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginCaptchaRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginCaptchaEnvelope"];
                };
            };
        };
    };
    auth_login_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["LoginRequestRequest"];
                "multipart/form-data": components["schemas"]["LoginRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
        };
    };
    auth_logout_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_me_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentUserResponse"];
                };
            };
        };
    };
    auth_online_users_list: {
        parameters: {
            query?: {
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedOnlineUserList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_online_users_revoke_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordConfirmationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PasswordConfirmationRequest"];
                "multipart/form-data": components["schemas"]["PasswordConfirmationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OnlineUserRevoked"];
                };
            };
        };
    };
    auth_profile_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonalProfileResponse"];
                };
            };
        };
    };
    auth_profile_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedProfileWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedProfileWriteRequest"];
                "multipart/form-data": components["schemas"]["PatchedProfileWriteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonalProfileUpdatedResponse"];
                };
            };
        };
    };
    auth_recovery_config_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryConfigResponse"];
                };
            };
        };
    };
    auth_recovery_request_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecoveryRequestRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_recovery_reset_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecoveryResetRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_refresh_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RefreshRequestRequest"];
                "multipart/form-data": components["schemas"]["RefreshRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RefreshResponse"];
                };
            };
        };
    };
    auth_register_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserRegistrationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UserRegistrationRequest"];
                "multipart/form-data": components["schemas"]["UserRegistrationRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RegisterResponse"];
                };
            };
        };
    };
    auth_sessions_list: {
        parameters: {
            query?: {
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedPersonalSessionList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    auth_sessions_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    auth_totp_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPStatusResponse"];
                };
            };
        };
    };
    auth_totp_disable_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPStatusResponse"];
                };
            };
        };
    };
    auth_totp_disable_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPProofRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPChangeResponse"];
                };
            };
        };
    };
    auth_totp_enable_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPStatusResponse"];
                };
            };
        };
    };
    auth_totp_enable_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPProofRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPChangeResponse"];
                };
            };
        };
    };
    auth_totp_recovery_codes_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPStatusResponse"];
                };
            };
        };
    };
    auth_totp_recovery_codes_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPProofRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPChangeResponse"];
                };
            };
        };
    };
    auth_totp_setup_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPStatusResponse"];
                };
            };
        };
    };
    auth_totp_setup_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPPasswordRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPSetupResponse"];
                };
            };
        };
    };
    brand_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BrandResponse"];
                };
            };
        };
    };
    dashboard_stats_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardResponse"];
                };
            };
        };
    };
    data_io_export_retrieve: {
        parameters: {
            query?: {
                export_format?: "csv" | "xlsx";
                resource?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Blob;
                    "text/csv": Blob;
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    data_io_import_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DataImportRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DataImportRequest"];
                "multipart/form-data": components["schemas"]["DataImportRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportResponse"];
                };
            };
        };
    };
    data_io_import_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportStatusResponse"];
                };
            };
        };
    };
    data_io_import_retry: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportRetryResponse"];
                };
            };
        };
    };
    data_io_resources_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataResourceDirectoryResponse"];
                };
            };
        };
    };
    data_io_template_retrieve: {
        parameters: {
            query?: {
                resource?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Blob;
                };
            };
        };
    };
    example_items_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, updated_at, priority。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /**
                 * @description * `normal` - 普通
                 *     * `high` - 高
                 */
                priority?: "high" | "normal";
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `open` - 待处理
                 *     * `done` - 已完成
                 */
                status?: "done" | "open";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedWorkItemList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    example_items_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkItemRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["WorkItemRequest"];
                "multipart/form-data": components["schemas"]["WorkItemRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExampleCreatedResponse"];
                };
            };
        };
    };
    example_items_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 work item 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExampleDetailResponse"];
                };
            };
        };
    };
    example_items_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 work item 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkItemRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["WorkItemRequest"];
                "multipart/form-data": components["schemas"]["WorkItemRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExampleUpdatedResponse"];
                };
            };
        };
    };
    example_items_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 work item 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    example_items_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 work item 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedWorkItemRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedWorkItemRequest"];
                "multipart/form-data": components["schemas"]["PatchedWorkItemRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExamplePatchedResponse"];
                };
            };
        };
    };
    feature_flags_evaluate_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvaluationRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EvaluationRequestRequest"];
                "multipart/form-data": components["schemas"]["EvaluationRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureFlagEvaluationResponse"];
                };
            };
        };
    };
    feature_flags_flags_list: {
        parameters: {
            query?: {
                enabled?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：key, created_at, updated_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedFeatureFlagList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    feature_flags_flags_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeatureFlagRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["FeatureFlagRequest"];
                "multipart/form-data": components["schemas"]["FeatureFlagRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureFlagCreatedResponse"];
                };
            };
        };
    };
    feature_flags_flags_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 feature flag 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureFlagDetailResponse"];
                };
            };
        };
    };
    feature_flags_flags_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 feature flag 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    feature_flags_flags_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 feature flag 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedFeatureFlagRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedFeatureFlagRequest"];
                "multipart/form-data": components["schemas"]["PatchedFeatureFlagRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureFlagUpdatedResponse"];
                };
            };
        };
    };
    feature_flags_targets_retrieve: {
        parameters: {
            query: {
                /**
                 * @description * `users` - users
                 *     * `roles` - roles
                 */
                kind: "users" | "roles";
                search?: string;
                selected?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureFlagTargetsResponse"];
                };
            };
        };
    };
    files_list: {
        parameters: {
            query?: {
                file_type?: string;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, size, download_count。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                uploader?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedFileList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FileUploadRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["FileUploadRequest"];
                "multipart/form-data": components["schemas"]["FileUploadRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileUploadedResponse"];
                };
            };
        };
    };
    files_office_preview_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfficeSubmitRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["OfficeSubmitRequest"];
                "multipart/form-data": components["schemas"]["OfficeSubmitRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfficePreviewSubmitted"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["File"];
                };
            };
        };
    };
    files_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["File"];
                };
            };
        };
    };
    files_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    files_acl_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileACLResponse"];
                };
            };
        };
    };
    files_acl_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FileACLRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["FileACLRequest"];
                "multipart/form-data": components["schemas"]["FileACLRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileACLResponse"];
                };
            };
        };
    };
    files_download_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": Blob;
                };
            };
        };
    };
    files_preview_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": Blob;
                    "image/png": Blob;
                };
            };
            413: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            415: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            422: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_purge_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_restore_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestoreRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RestoreRequest"];
                "multipart/form-data": components["schemas"]["RestoreRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileRestoreResponse"];
                };
            };
        };
    };
    files_transform_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 文件 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImageTransformRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ImageTransformRequest"];
                "multipart/form-data": components["schemas"]["ImageTransformRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "image/jpeg": Blob;
                    "image/png": Blob;
                    "image/webp": Blob;
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            413: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            415: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            422: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_office_preview_config_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfficePreviewConfiguration"];
                };
            };
        };
    };
    files_office_preview_jobs_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfficePreviewStatus"];
                };
            };
        };
    };
    files_office_preview_jobs_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    files_office_preview_jobs_pdf_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": Blob;
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            410: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_processing_config_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImageProcessingConfigResponse"];
                };
            };
        };
    };
    files_recycle_action_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecycleActionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RecycleActionRequest"];
                "multipart/form-data": components["schemas"]["RecycleActionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileRecycleActionResponse"];
                };
            };
        };
    };
    files_recycle_policy_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileRecyclePolicyResponse"];
                };
            };
        };
    };
    files_recycle_list: {
        parameters: {
            query?: {
                file_type?: string;
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                uploader?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedFileList"];
                };
            };
        };
    };
    files_uploads_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
                "application/x-www-form-urlencoded": {
                    [key: string]: unknown;
                };
                "multipart/form-data": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_uploads_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            410: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_uploads_chunks_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index: number;
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": Blob;
                "application/x-www-form-urlencoded": Blob;
                "multipart/form-data": Blob;
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            422: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    files_uploads_complete_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResumableUploadCompleteResponse"];
                };
            };
            422: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    ip_policy_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IPPolicyDetail"];
                };
            };
        };
    };
    ip_policy_update: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IPPolicyRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["IPPolicyRequest"];
                "multipart/form-data": components["schemas"]["IPPolicyRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IPPolicyUpdated"];
                };
            };
        };
    };
    ip_policy_preview_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PolicyPreviewRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PolicyPreviewRequest"];
                "multipart/form-data": components["schemas"]["PolicyPreviewRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IPPolicyPreview"];
                };
            };
        };
    };
    logs_exception_list: {
        parameters: {
            query?: {
                /**
                 * @description * `debug` - DEBUG
                 *     * `info` - INFO
                 *     * `warning` - WARNING
                 *     * `error` - ERROR
                 *     * `critical` - CRITICAL
                 */
                level?: "critical" | "debug" | "error" | "info" | "warning";
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                request_method?: string;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedExceptionLogList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    logs_exception_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 异常日志 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExceptionLog"];
                };
            };
        };
    };
    logs_login_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `success` - 成功
                 *     * `failed` - 失败
                 *     * `locked` - 被锁定
                 */
                status?: "failed" | "locked" | "success";
                username?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedLoginLogList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    logs_login_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 登录日志 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginLog"];
                };
            };
        };
    };
    logs_operation_list: {
        parameters: {
            query?: {
                /**
                 * @description * `create` - 创建
                 *     * `read` - 查看
                 *     * `update` - 修改
                 *     * `delete` - 删除
                 *     * `export` - 导出
                 *     * `import` - 导入
                 *     * `download` - 下载
                 *     * `upload` - 上传
                 *     * `login` - 登录
                 *     * `logout` - 登出
                 *     * `other` - 其他
                 */
                action?: "create" | "delete" | "download" | "export" | "import" | "login" | "logout" | "other" | "read" | "update" | "upload";
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                request_id?: string;
                resource?: string;
                /** @description 搜索关键词。 */
                search?: string;
                task_id?: string;
                task_record_id?: string;
                user?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedOperationLogListList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    logs_operation_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 操作日志 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperationLog"];
                };
            };
        };
    };
    modules_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModuleCapabilitiesResponse"];
                };
            };
        };
    };
    notifications_list: {
        parameters: {
            query?: {
                is_read?: boolean;
                /**
                 * @description * `system` - 系统通知
                 *     * `approval` - 审批通知
                 *     * `task` - 任务通知
                 *     * `announcement` - 公告
                 */
                notification_type?: "announcement" | "approval" | "system" | "task";
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, read_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 资源查询视角；无此参数时使用默认范围。 */
                scope?: "" | "all";
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedNotificationList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    notifications_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NotificationCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["NotificationCreateRequest"];
                "multipart/form-data": components["schemas"]["NotificationCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationSentResponse"];
                };
            };
        };
    };
    notifications_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 通知 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationDetailResponse"];
                };
            };
        };
    };
    notifications_mark_read_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 通知 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationReadResponse"];
                };
            };
        };
    };
    notifications_announcements_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：published_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedAnnouncementList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    notifications_announcements_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 announcement 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementDetailResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, updated_at, published_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `draft` - 草稿
                 *     * `published` - 已发布
                 *     * `withdrawn` - 已撤回
                 */
                status?: "draft" | "published" | "withdrawn";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedAnnouncementList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnouncementWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnnouncementWriteRequest"];
                "multipart/form-data": components["schemas"]["AnnouncementWriteRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementCreatedResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 announcement 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementDetailResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 announcement 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedAnnouncementWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedAnnouncementWriteRequest"];
                "multipart/form-data": components["schemas"]["PatchedAnnouncementWriteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementUpdatedResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 announcement 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnouncementTransitionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnnouncementTransitionRequest"];
                "multipart/form-data": components["schemas"]["AnnouncementTransitionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementPublishedResponse"];
                };
            };
        };
    };
    notifications_announcements_manage_withdraw_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 announcement 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnouncementTransitionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnnouncementTransitionRequest"];
                "multipart/form-data": components["schemas"]["AnnouncementTransitionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementWithdrawnResponse"];
                };
            };
        };
    };
    notifications_deliveries_list: {
        parameters: {
            query?: {
                /**
                 * @description * `inapp` - 站内通知
                 *     * `email` - SMTP 邮件
                 *     * `webhook` - Webhook
                 *     * `sms` - Twilio 短信
                 */
                channel?: "email" | "inapp" | "sms" | "webhook";
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, updated_at, status, channel。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                recipient?: string;
                /**
                 * @description * `pending` - 待发送
                 *     * `sending` - 发送中
                 *     * `succeeded` - 成功
                 *     * `failed` - 失败
                 *     * `terminated` - 已终止
                 */
                status?: "failed" | "pending" | "sending" | "succeeded" | "terminated";
                version__template?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedMessageDeliveryList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    notifications_deliveries_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageDelivery"];
                };
            };
        };
    };
    notifications_deliveries_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message delivery 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageDeliveryDetailResponse"];
                };
            };
        };
    };
    notifications_deliveries_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message delivery 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageDelivery"];
                };
            };
        };
    };
    notifications_deliveries_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message delivery 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    notifications_deliveries_retry_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message delivery 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageDeliveryRetryResponse"];
                };
            };
        };
    };
    notifications_mark_all_read_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationsReadResponse"];
                };
            };
        };
    };
    notifications_templates_list: {
        parameters: {
            query?: {
                enabled?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：code, name, created_at, updated_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedMessageTemplateList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    notifications_templates_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TemplateWriteRequest"];
                "multipart/form-data": components["schemas"]["TemplateWriteRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageTemplateCreatedResponse"];
                };
            };
        };
    };
    notifications_templates_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message template 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageTemplateDetailResponse"];
                };
            };
        };
    };
    notifications_templates_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message template 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedTemplateWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedTemplateWriteRequest"];
                "multipart/form-data": components["schemas"]["PatchedTemplateWriteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageTemplateUpdatedResponse"];
                };
            };
        };
    };
    notifications_templates_preview_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message template 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplatePreviewRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TemplatePreviewRequest"];
                "multipart/form-data": components["schemas"]["TemplatePreviewRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessagePreviewResponse"];
                };
            };
        };
    };
    notifications_templates_send_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message template 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateSendRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TemplateSendRequest"];
                "multipart/form-data": components["schemas"]["TemplateSendRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageSendResponse"];
                };
            };
        };
    };
    notifications_templates_versions_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 message template 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageVersionsResponse"];
                };
            };
        };
    };
    notifications_templates_channels_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageChannelsResponse"];
                };
            };
        };
    };
    notifications_templates_recipient_departments_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageRecipientDepartmentsResponse"];
                };
            };
        };
    };
    notifications_templates_recipients_retrieve: {
        parameters: {
            query?: {
                department?: string;
                page?: number;
                page_size?: number;
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageRecipientsResponse"];
                };
            };
        };
    };
    notifications_unread_count_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnreadCountResponse"];
                };
            };
        };
    };
    organization_departments_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：order, name, created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedDepartmentList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    organization_departments_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DepartmentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DepartmentRequest"];
                "multipart/form-data": components["schemas"]["DepartmentRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentCreatedResponse"];
                };
            };
        };
    };
    organization_departments_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 department 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentDetailResponse"];
                };
            };
        };
    };
    organization_departments_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 department 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DepartmentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DepartmentRequest"];
                "multipart/form-data": components["schemas"]["DepartmentRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentUpdatedResponse"];
                };
            };
        };
    };
    organization_departments_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 department 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    organization_departments_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 department 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedDepartmentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedDepartmentRequest"];
                "multipart/form-data": components["schemas"]["PatchedDepartmentRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentPatchedResponse"];
                };
            };
        };
    };
    organization_memberships_list: {
        parameters: {
            query?: {
                department?: string;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, user__username, department__name。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                user?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedMembershipList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    organization_memberships_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MembershipRequest"];
                "multipart/form-data": components["schemas"]["MembershipRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipCreatedResponse"];
                };
            };
        };
    };
    organization_memberships_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 organization membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipDetailResponse"];
                };
            };
        };
    };
    organization_memberships_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 organization membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MembershipRequest"];
                "multipart/form-data": components["schemas"]["MembershipRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipUpdatedResponse"];
                };
            };
        };
    };
    organization_memberships_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 organization membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    organization_memberships_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 organization membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMembershipRequest"];
                "multipart/form-data": components["schemas"]["PatchedMembershipRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipPatchedResponse"];
                };
            };
        };
    };
    organization_my_tenants_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MyTenant"][];
                };
            };
        };
    };
    organization_people_retrieve: {
        parameters: {
            query?: {
                department?: string;
                page?: number;
                page_size?: number;
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonnelPageResponse"];
                };
            };
        };
    };
    organization_people_departments_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostPersonnelDepartmentsResponse"];
                };
            };
        };
    };
    organization_posts_list: {
        parameters: {
            query?: {
                is_active?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：order, name, code。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedPostList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    organization_posts_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PostRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PostRequest"];
                "multipart/form-data": components["schemas"]["PostRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostCreatedResponse"];
                };
            };
        };
    };
    organization_posts_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostDetailResponse"];
                };
            };
        };
    };
    organization_posts_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PostRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PostRequest"];
                "multipart/form-data": components["schemas"]["PostRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostUpdatedResponse"];
                };
            };
        };
    };
    organization_posts_destroy: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                /** @description 标识此 post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    organization_posts_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedPostRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedPostRequest"];
                "multipart/form-data": components["schemas"]["PatchedPostRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostPatchedResponse"];
                };
            };
        };
    };
    organization_posts_choices_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostChoicesResponse"];
                };
            };
        };
    };
    organization_scopes_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, resource, role__name。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /**
                 * @description * `user` - 用户
                 *     * `file` - 文件
                 *     * `task` - 任务
                 *     * `log` - 日志
                 *     * `example` - 示例工单
                 */
                resource?: "example" | "file" | "log" | "task" | "user";
                role?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedScopeGrantList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    organization_scopes_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScopeGrantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScopeGrantRequest"];
                "multipart/form-data": components["schemas"]["ScopeGrantRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScopeCreatedResponse"];
                };
            };
        };
    };
    organization_scopes_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data scope grant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScopeDetailResponse"];
                };
            };
        };
    };
    organization_scopes_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data scope grant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScopeGrantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScopeGrantRequest"];
                "multipart/form-data": components["schemas"]["ScopeGrantRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScopeUpdatedResponse"];
                };
            };
        };
    };
    organization_scopes_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data scope grant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedScopeGrantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedScopeGrantRequest"];
                "multipart/form-data": components["schemas"]["PatchedScopeGrantRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScopePatchedResponse"];
                };
            };
        };
    };
    organization_tenant_memberships_list: {
        parameters: {
            query?: {
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedTenantMembershipList"];
                };
            };
        };
    };
    organization_tenant_memberships_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantMembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TenantMembershipRequest"];
                "multipart/form-data": components["schemas"]["TenantMembershipRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantMembership"];
                };
            };
        };
    };
    organization_tenant_memberships_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantMembership"];
                };
            };
        };
    };
    organization_tenant_memberships_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantMembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TenantMembershipRequest"];
                "multipart/form-data": components["schemas"]["TenantMembershipRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantMembership"];
                };
            };
        };
    };
    organization_tenant_memberships_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    organization_tenant_memberships_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant membership 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedTenantMembershipRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedTenantMembershipRequest"];
                "multipart/form-data": components["schemas"]["PatchedTenantMembershipRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantMembership"];
                };
            };
        };
    };
    organization_tenants_list: {
        parameters: {
            query?: {
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedTenantList"];
                };
            };
        };
    };
    organization_tenants_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TenantRequest"];
                "multipart/form-data": components["schemas"]["TenantRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Tenant"];
                };
            };
        };
    };
    organization_tenants_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Tenant"];
                };
            };
        };
    };
    organization_tenants_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TenantRequest"];
                "multipart/form-data": components["schemas"]["TenantRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Tenant"];
                };
            };
        };
    };
    organization_tenants_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 tenant 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedTenantRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedTenantRequest"];
                "multipart/form-data": components["schemas"]["PatchedTenantRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Tenant"];
                };
            };
        };
    };
    organization_user_posts_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, user__username, post__code, post__order。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                post?: string;
                /** @description 搜索关键词。 */
                search?: string;
                user?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedUserPostList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    organization_user_posts_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserPostRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UserPostRequest"];
                "multipart/form-data": components["schemas"]["UserPostRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserPostCreatedResponse"];
                };
            };
        };
    };
    organization_user_posts_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 user post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserPostDetailResponse"];
                };
            };
        };
    };
    organization_user_posts_destroy: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                /** @description 标识此 user post 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    permissions_menus_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：order, name, created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedMenuList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_menus_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MenuRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MenuRequest"];
                "multipart/form-data": components["schemas"]["MenuRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MenuCreatedResponse"];
                };
            };
        };
    };
    permissions_menus_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 菜单 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MenuDetailResponse"];
                };
            };
        };
    };
    permissions_menus_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 菜单 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MenuRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MenuRequest"];
                "multipart/form-data": components["schemas"]["MenuRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MenuUpdatedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_menus_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 菜单 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_menus_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 菜单 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMenuRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMenuRequest"];
                "multipart/form-data": components["schemas"]["PatchedMenuRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MenuPatchedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_menus_my_menu_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MyMenuResponse"];
                };
            };
        };
    };
    permissions_permissions_list: {
        parameters: {
            query?: {
                action?: string;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：code, name, resource, action, created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                resource?: string;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedPermissionList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_permissions_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PermissionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PermissionRequest"];
                "multipart/form-data": components["schemas"]["PermissionRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Permission"];
                };
            };
        };
    };
    permissions_permissions_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 权限 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PermissionDetailResponse"];
                };
            };
        };
    };
    permissions_permissions_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 权限 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PermissionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PermissionRequest"];
                "multipart/form-data": components["schemas"]["PermissionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Permission"];
                };
            };
        };
    };
    permissions_permissions_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 权限 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    permissions_roles_list: {
        parameters: {
            query?: {
                is_active?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, name。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedRoleList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_roles_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RoleRequest"];
                "multipart/form-data": components["schemas"]["RoleRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleCreatedResponse"];
                };
            };
        };
    };
    permissions_roles_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 角色 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleDetailResponse"];
                };
            };
        };
    };
    permissions_roles_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 角色 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RoleRequest"];
                "multipart/form-data": components["schemas"]["RoleRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleUpdatedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_roles_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 角色 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    permissions_roles_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 角色 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedRoleRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedRoleRequest"];
                "multipart/form-data": components["schemas"]["PatchedRoleRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RolePatchedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    reliability_events_list: {
        parameters: {
            query?: {
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, available_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /**
                 * @description * `pending` - 待派发
                 *     * `processing` - 派发中
                 *     * `succeeded` - 已完成
                 *     * `failed` - 失败
                 */
                status?: "failed" | "pending" | "processing" | "succeeded";
                topic?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedOutboxEventList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    reliability_events_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboxEvent"];
                };
            };
        };
    };
    reliability_events_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 outbox event 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboxDetailResponse"];
                };
            };
        };
    };
    reliability_events_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 outbox event 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboxEvent"];
                };
            };
        };
    };
    reliability_events_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 outbox event 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reliability_events_retry_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 outbox event 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboxRetryResponse"];
                };
            };
        };
    };
    schema_retrieve: {
        parameters: {
            query?: {
                format?: "json" | "yaml";
                lang?: "en" | "zh-hans";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                    "application/vnd.oai.openapi": {
                        [key: string]: unknown;
                    };
                    "application/vnd.oai.openapi+json": {
                        [key: string]: unknown;
                    };
                    "application/yaml": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    sso_callback_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            302: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string;
                };
            };
        };
    };
    sso_cancel_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["StartRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["StartRequest"];
                "multipart/form-data": components["schemas"]["StartRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    sso_complete_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CompleteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CompleteRequest"];
                "multipart/form-data": components["schemas"]["CompleteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SSOCompletedResponse"];
                };
            };
        };
    };
    sso_config_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SSOConfigResponse"];
                };
            };
        };
    };
    sso_identities_list: {
        parameters: {
            query?: {
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedIdentityList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    sso_identities_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BindRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BindRequest"];
                "multipart/form-data": components["schemas"]["BindRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SSOBoundResponse"];
                };
            };
        };
    };
    sso_identities_unbind_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnbindRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UnbindRequest"];
                "multipart/form-data": components["schemas"]["UnbindRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    sso_start_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["StartRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["StartRequest"];
                "multipart/form-data": components["schemas"]["StartRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SSOAuthorizationResponse"];
                };
            };
        };
    };
    sso_status_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SSOStatusResponse"];
                };
            };
        };
    };
    system_cache_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CacheCatalogResponse"];
                };
            };
        };
    };
    system_cache_clear_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClearRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ClearRequestRequest"];
                "multipart/form-data": components["schemas"]["ClearRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CacheClearResponse"];
                };
            };
        };
    };
    system_cache_preview_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreviewRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PreviewRequestRequest"];
                "multipart/form-data": components["schemas"]["PreviewRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CachePreviewResponse"];
                };
            };
        };
    };
    system_config_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemConfigListResponse"];
                };
            };
        };
    };
    system_config_detail: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemConfigDetailResponse"];
                };
            };
        };
    };
    system_config_write: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedConfigWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedConfigWriteRequest"];
                "multipart/form-data": components["schemas"]["PatchedConfigWriteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemConfigWriteResponse"];
                };
            };
        };
    };
    system_dictionaries_list: {
        parameters: {
            query?: {
                is_active?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：code, created_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedDictionaryList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    system_dictionaries_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictionaryRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DictionaryRequest"];
                "multipart/form-data": components["schemas"]["DictionaryRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DictionaryCreatedResponse"];
                };
            };
        };
    };
    system_dictionaries_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data dictionary 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DictionaryDetailResponse"];
                };
            };
        };
    };
    system_dictionaries_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data dictionary 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DictionaryRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DictionaryRequest"];
                "multipart/form-data": components["schemas"]["DictionaryRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DictionaryUpdatedResponse"];
                };
            };
        };
    };
    system_dictionaries_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 data dictionary 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedDictionaryRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedDictionaryRequest"];
                "multipart/form-data": components["schemas"]["PatchedDictionaryRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DictionaryPatchedResponse"];
                };
            };
        };
    };
    system_dictionaries_options_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DictionaryOptionsResponse"];
                };
            };
        };
    };
    system_information_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemInformationResponse"];
                };
            };
        };
    };
    system_monitor_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemMonitorResponse"];
                };
            };
        };
    };
    tasks_list: {
        parameters: {
            query?: {
                creator?: string;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, started_at, completed_at。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `pending` - 等待执行
                 *     * `running` - 执行中
                 *     * `success` - 成功
                 *     * `failed` - 失败
                 *     * `cancelled` - 已取消
                 */
                status?: "cancelled" | "failed" | "pending" | "running" | "success";
                /**
                 * @description * `import` - 数据导入
                 *     * `export` - 数据导出
                 *     * `backup` - 数据备份
                 *     * `cleanup` - 数据清理
                 *     * `notification` - 通知发送
                 *     * `other` - 其他
                 */
                task_type?: "backup" | "cleanup" | "export" | "import" | "notification" | "other";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedTaskRecordList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    tasks_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 任务记录 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskRecord"];
                };
            };
        };
    };
    tasks_cancel_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 任务记录 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskCancelledResponse"];
                };
            };
        };
    };
    tasks_resume_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 任务记录 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskResumedResponse"];
                };
            };
        };
    };
    tasks_backups_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupStatusResponse"];
                };
            };
        };
    };
    tasks_backups_preflight_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                timestamp: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupPreflightResponse"];
                };
            };
        };
    };
    tasks_backups_restore_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                timestamp: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BackupRestoreRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BackupRestoreRequest"];
                "multipart/form-data": components["schemas"]["BackupRestoreRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupRestoreAcceptedResponse"];
                };
            };
        };
    };
    tasks_backups_restore_requests_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupRestoreRequestResponse"];
                };
            };
        };
    };
    tasks_cleanup_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CleanupRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CleanupRequestRequest"];
                "multipart/form-data": components["schemas"]["CleanupRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskHistoryCleanupResponse"];
                };
            };
        };
    };
    tasks_schedules_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceSchedulesResponse"];
                };
            };
        };
    };
    tasks_schedules_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedScheduleWriteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedScheduleWriteRequest"];
                "multipart/form-data": components["schemas"]["PatchedScheduleWriteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceScheduleUpdatedResponse"];
                };
            };
        };
    };
    tasks_schedules_run_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScheduleRunRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScheduleRunRequest"];
                "multipart/form-data": components["schemas"]["ScheduleRunRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceAcceptedResponse"];
                };
            };
        };
    };
    users_list: {
        parameters: {
            query?: {
                is_active?: boolean;
                /** @description 逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：created_at, username, login_count。同值记录追加主键排序。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 每页条数 */
                page_size?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedUserListList"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            503: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    users_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UserCreateRequest"];
                "multipart/form-data": components["schemas"]["UserCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserCreatedResponse"];
                };
            };
        };
    };
    users_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetailResponse"];
                };
            };
        };
    };
    users_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["UserUpdateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UserUpdateRequest"];
                "multipart/form-data": components["schemas"]["UserUpdateRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserUpdatedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    users_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    users_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedUserUpdateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedUserUpdateRequest"];
                "multipart/form-data": components["schemas"]["PatchedUserUpdateRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserPatchedResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    users_reset_password_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResetPasswordRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ResetPasswordRequestRequest"];
                "multipart/form-data": components["schemas"]["ResetPasswordRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
        };
    };
    users_sensitive_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 用户 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SensitiveContactRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["SensitiveContactRequestRequest"];
                "multipart/form-data": components["schemas"]["SensitiveContactRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SensitiveContactResponse"];
                };
            };
        };
    };
    users_bulk_action_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkUserActionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BulkUserActionRequest"];
                "multipart/form-data": components["schemas"]["BulkUserActionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkUserActionResponse"];
                };
            };
            400: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            403: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkUserActionResponse"];
                };
            };
            409: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkUserActionResponse"];
                };
            };
            500: {
                headers: {
                    /**
                     * @description API lifecycle; see /api/versions/. Does not change authentication, caching or response body.
                     * @example v1
                     */
                    "X-API-Version"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkUserActionResponse"];
                };
            };
        };
    };
}
