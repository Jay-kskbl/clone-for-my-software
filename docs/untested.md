# 未测试清单（Not Tested）

更新日期：2026-11-14（T11 完成后）

这里列出**已经写好但从未实际执行过**的测试，以及其他没有经过验证的性质。
规则来自 GLOBAL.md“测试执行限制与代码验证要求”：跑不了的测试不强行执行、不安装工具，
在这里如实登记，并对相关代码做人工复核。

**复核不等于测试通过。** 本文件中的任何一项，在实际运行通过之前，都不能在论文、测试报告或答辩中写成“已验证”。

维护方式：每完成一个任务，把新增的未测试项加进来；某一项实际运行通过后，从这里删除，并在 DEVPLAN §5 对应任务的备注里写明运行环境和结果。

## 1. 汇总

| 任务 | 测试文件 | 未测试项数 | 原因 | 代码复核 |
|---|---|---|---|---|
| T03 数据库迁移 | `backend/tests/integration/test_migrations.py` | 13 | 本机没有 PostgreSQL | 未复核（T03 的记录写的是曾在本地 PostgreSQL 16.15 上通过；当前这台机器上无法重跑） |
| T06 认证与权限 | `backend/tests/integration/test_auth.py` | 19 | 本机没有 PostgreSQL | 已复核，未发现问题 |
| T07 任务框架 | `backend/tests/integration/test_task_queue.py` | 18 | 本机没有 PostgreSQL | 已复核，未发现问题 |
| T08 文档管理 | `backend/tests/integration/test_documents.py` | 41 | 本机没有 PostgreSQL | 已复核，改了 1 处测试断言 |
| **合计** | | **91** | | |

T05（存储）、T09（PDF 解析器）和 T11（Word、Excel、图片解析器）不需要数据库，它们的测试全部在本机执行并通过，没有未测试项。

对照：当前能在本机执行的测试，`backend/` 288 项、`shared/` 93 项、`frontend/` 30 项，全部通过。

## 2. 影响最大的几项

下面这些是 DEVPLAN 用 🧪 标出的“必须包含的测试”，目前只有代码，没有运行结果：

| 任务 | DEVPLAN 要求 | 对应测试 | 状态 |
|---|---|---|---|
| T06 | 访问他人文档 403 | `test_auth.py::test_document_access_over_http` | 未测试 |
| T06 | 管理员可见全部 | `test_auth.py::test_admin_sees_all_documents` | 未测试 |
| T06 | 共享后可见、取消共享后不可见 | `test_auth.py::test_share_grants_access_and_unshare_revokes_it_immediately` | 未测试 |
| T07 | 崩溃恢复 | `test_task_queue.py::test_task_of_killed_worker_is_reclaimed_after_lease_expires` | 未测试 |
| T07 | 并发：两个 Worker 不会领到同一任务 | `test_task_queue.py::test_uncommitted_claim_is_skipped_not_waited_for`、`test_many_workers_never_claim_the_same_task` | 未测试 |
| T07 | 幂等 | `test_task_queue.py::test_task_executed_twice_does_not_duplicate_results` | 未测试 |
| T07 | 超过最大重试次数后标记 failed | `test_task_queue.py::test_failing_task_is_retried_up_to_max_attempts_then_failed`、`test_crashing_task_is_failed_after_max_attempts_with_reason` | 未测试 |
| T08 | 上传中途失败不留半成品 | `test_documents.py::test_failure_while_moving_file_leaves_no_record_and_no_file`、`test_failure_at_database_commit_removes_the_already_moved_file` | 未测试（用假数据库会话模拟的版本已通过，见 `tests/unit/test_documents_unit.py`） |
| T08 | 删除后列表和下载都不可见 | `test_documents.py::test_deleted_document_disappears_everywhere_immediately` | 未测试 |
| T08 | 非法类型被拒绝 | `test_documents.py::test_unsupported_content_is_415_and_leaves_nothing` | 未测试（存储层的类型识别已通过，见 `tests/unit/test_storage.py`） |

**里程碑“基础系统”要求“T07 的四项测试全部通过”，目前不满足。**

## 3. 逐项清单

括号里的数字是该测试的参数化用例数，未标注的为 1。

### T03 `test_migrations.py`（13）

- `test_upgrade_downgrade_upgrade_on_empty_database`
- `test_migration_matches_models`
- `test_defaults_are_applied`
- `test_constraints_reject_bad_rows`（6）
- `test_invalid_document_status_rejected`
- `test_hard_deleting_document_removes_dependent_rows`
- `test_user_with_documents_cannot_be_deleted`
- `test_same_image_content_embedded_once_per_model`

### T06 `test_auth.py`（19）

- 注册、登录、me：`test_register_login_me_flow`、`test_password_is_stored_hashed`、`test_register_duplicate_username_is_409`、`test_create_user_duplicate_raises_and_session_still_usable`、`test_login_failure_is_401_and_does_not_say_which_part_was_wrong`（3）、`test_authenticate_returns_user_or_raises`、`test_register_cannot_create_admin`
- 令牌：`test_token_of_deleted_user_is_401`、`test_expired_token_is_401`
- 管理员命令：`test_create_admin_command`
- 权限函数：`test_owner_can_access_own_document_only`、`test_admin_sees_all_documents`、`test_share_grants_access_and_unshare_revokes_it_immediately`、`test_share_is_per_user`、`test_soft_deleted_document_is_invisible_to_everyone`、`test_get_accessible_document_distinguishes_403_and_404`
- 经 HTTP 的完整链路：`test_document_access_over_http`

### T07 `test_task_queue.py`（18）

- 领取：`test_claim_marks_task_processing_with_lease`、`test_claim_returns_oldest_first_and_none_when_empty`、`test_claim_only_takes_requested_types`
- 并发：`test_uncommitted_claim_is_skipped_not_waited_for`、`test_many_workers_never_claim_the_same_task`
- 崩溃恢复与租约：`test_task_of_killed_worker_is_reclaimed_after_lease_expires`、`test_reclaim_expired_returns_task_to_pending`、`test_renew_keeps_the_task_from_being_reclaimed`、`test_late_write_back_from_previous_owner_is_rejected`、`test_write_back_after_reclaim_to_pending_is_rejected`
- 完成与失败：`test_complete_marks_succeeded_and_clears_previous_error`、`test_failing_task_is_retried_up_to_max_attempts_then_failed`、`test_crashing_task_is_failed_after_max_attempts_with_reason`、`test_non_retryable_failure_goes_straight_to_failed`、`test_very_long_error_is_truncated`
- 幂等：`test_task_executed_twice_does_not_duplicate_results`
- 主循环 + 真实队列 + 真实子进程：`test_worker_loop_end_to_end_success`、`test_worker_loop_end_to_end_failure_until_max_attempts`

特别说明：`shared/tasks.py` 里的全部 SQL 语句从未在任何数据库上执行过。语法错误、参数类型不匹配这类问题，人工复核不一定能发现。

### T08 `test_documents.py`（41）

- 上传：`test_upload_stores_file_record_and_parse_task`、`test_mime_type_comes_from_content_not_from_extension_or_header`、`test_unsupported_content_is_415_and_leaves_nothing`（4）、`test_too_large_is_413_and_leaves_nothing`、`test_invalid_upload_is_422_and_leaves_nothing`（4）、`test_upload_without_file_field_is_422`
- 上传失败不留半成品：`test_failure_while_moving_file_leaves_no_record_and_no_file`、`test_failure_at_database_commit_removes_the_already_moved_file`
- 列表与详情：`test_list_shows_only_accessible_documents_newest_first`、`test_list_pagination`、`test_list_rejects_invalid_parameters`（5）、`test_list_filters_by_scope_status_and_tag`、`test_detail_distinguishes_403_and_404`、`test_response_never_exposes_internal_fields`
- 下载：`test_download_returns_original_bytes_with_headers`、`test_download_permissions`、`test_download_when_file_is_missing_on_disk_is_500_not_404`
- 删除：`test_deleted_document_disappears_everywhere_immediately`、`test_delete_is_soft_and_creates_cleanup_task`、`test_only_owner_or_admin_can_delete`
- 共享：`test_share_lifecycle`、`test_share_errors`、`test_shared_user_cannot_manage_shares_or_tags`
- 标签：`test_put_tags_replaces_the_whole_set`、`test_same_tag_on_two_documents_is_one_tag_row`、`test_tag_list_only_contains_tags_of_accessible_documents`
- 任务：`test_document_tasks_listing`、`test_retry_puts_failed_task_back_in_queue`、`test_retry_permissions`、`test_tasks_of_deleted_document_are_only_retryable_by_admin`、`test_admin_task_listing`

## 4. 不是测试、但同样没有验证过的性质

| 项目 | 说明 | 记录位置 |
|---|---|---|
| Worker 子进程的内存上限 | 用 `RLIMIT_AS` 实现，只在 Linux 上有效；开发机是 macOS，内核基本不执行这个限制 | `decisions.md` D16 |
| 后端连上真实数据库后的整体运行 | 没有在本机启动过“后端 + PostgreSQL”，注册、上传、下载等接口没有人工点过一遍 | — |
| `deploy/docker-compose.yml` | 只校验过语法，容器从未启动 | DEVPLAN §5 T01 |
| 前端与真实后端的联调 | **未测试。** 本机没有 PostgreSQL，真实后端的登录、上传等接口跑不起来。T10 的页面是对着一个临时写的模拟接口在浏览器里检查的（模拟接口按 `api.md` 的结构应答，不是项目代码，没有提交）。前端与真实后端之间的不一致——字段名、状态码、multipart 的细节——这种检查发现不了 | DEVPLAN §5 T10 |
| 前端页面组件的自动化测试 | 没有写。30 项前端单元测试只覆盖接口封装和格式化函数；登录页、文件列表、共享对话框只做过上面那次人工浏览器检查 | DEVPLAN §5 T10 |
| 真实后端经开发代理的访问 | **部分验证。** T05–T10 核查时启动了真实后端（数据库地址指向不存在的端口）和真实的前端开发代理，用 curl 验证了不需要数据库的路径：健康检查、数据库不可用返回 503、未登录 401、参数校验 422、未登录上传（multipart 经代理）401、超大上传 413。需要数据库的路径（登录成功之后的一切）仍未验证 | DEVPLAN §5 核查记录 |
| Windows 上的运行 | 存储模块和 Worker 加了两处兼容处理（`O_NOFOLLOW`、`resource` 模块在 Windows 上不存在），但从未在 Windows 上运行过任何代码或测试 | — |
| 管理员视角的前端 | 模拟接口里没有管理员账号，页面上“管理员”标记和“管理员可见”来源没有实际显示过 | — |
| PDF 解析器在真实文件上的表现 | T09 的测试用 PyMuPDF 现场生成的 PDF；没有用真实的扫描件、多栏排版、带表格或带水印的 PDF 验证过，阈值 20 也没有实验依据 | `decisions.md` D20 |
| Word、Excel、图片解析器在真实文件上的表现 | T11 的测试文件是用 python-docx、openpyxl、PyMuPDF 现场生成的；没有用 Microsoft Word / Excel / WPS 实际保存的文件、手机或相机拍的照片验证过。尤其是 Excel 公式的缓存值，测试里是手工改 XML 模拟的 | `decisions.md` D24 |
| 解析超时对真实解析器的作用 | 超时在 Worker 子进程边界执行，机制本身有测试（`test_worker_runner.py`）；但解析器要到 T14 才接入 Worker，“一个真的卡住的解析被杀掉”还没有端到端跑过 | `decisions.md` D24 |
| zip 与像素上限的默认值 | 200 MB、5000 个条目、1 亿像素都是经验值；没有用接近上限的真实大文件测过解析时的内存和耗时 | `decisions.md` D24 |
| OpenSearch、中文分词、并发内存 | T00 环境实测中未完成的部分 | `env_check/未测试/清单.md` |

## 5. 补测方法

需要一个 PostgreSQL 16 实例和一个**空的**专用测试库（库里已有表时测试会直接失败，不会清库）。

1. 建库 `docmgr_test`，把连接串写进 `.env` 的 `TEST_DATABASE_URL`（格式见 `.env.example`）。
2. 在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && ../.venv-main/bin/pytest
   ```

3. 预期结果：379 项全部运行，0 项跳过。
4. 有失败的话先修；全部通过后更新本文件和 DEVPLAN §5。

在另一台机器上补测时，把那台机器的系统和 PostgreSQL 版本一起记下来。
