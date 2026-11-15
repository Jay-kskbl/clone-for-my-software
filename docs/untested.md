# 未测试清单（Not Tested）

更新日期：2026-11-15（T19 完成后）

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
| T13 文本索引 | `backend/tests/opensearch/test_text_index_live.py` | 13 | 本机没有 OpenSearch（没有 Docker 和 Java） | 已复核，未发现问题；有两处需要注意的性质，见第 4 节 |
| T14 解析流水线 | `backend/tests/integration/test_pipeline_db.py` | 23 | 本机没有 PostgreSQL；其中 2 项端到端测试还需要 OpenSearch | 已复核，未发现问题 |
| T15 检索 v1 | `backend/tests/integration/test_search_db.py` | 20 | 本机没有 PostgreSQL；其中 1 项还需要 OpenSearch | 已复核，未发现阻塞问题；局限见 `decisions.md` D28 |
| T16 抽取文本接口 | `backend/tests/integration/test_document_text.py` | 11 | 本机没有 PostgreSQL | 已复核，未发现问题 |
| T17 OCR Worker 读写数据库 | `backend/tests/integration/test_ocr_worker_db.py` | 10 | 本机没有 PostgreSQL | 已复核，未发现问题 |
| T18 一致性检查 | `backend/tests/integration/test_consistency_db.py` | 12 | 本机没有 PostgreSQL | 已复核；首轮发现的误删问题已修复，见 `decisions.md` D31 |
| T19 实验框架 | `backend/tests/integration/test_experiments_db.py` | 8 | 本机没有 PostgreSQL | 已复核；首轮发现的结果目录重名、P@K 口径问题已修复，见 `decisions.md` D32 |
| **合计** | | **188** | | |

T05（存储）、T09（PDF 解析器）、T11（Word、Excel、图片解析器）和 T12（切分）不需要数据库，它们的测试全部在本机执行并通过，没有未测试项。

对照：当前能在本机执行的测试，`backend/` 540 项、`shared/` 105 项、`services/ocr_worker/` 63 项（main 环境；另有 4 项真实识别测试在 ocr 环境里运行并通过）、`frontend/` 48 项，全部通过。

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
| T13 | 重复索引不产生重复数据 | `test_text_index_live.py::test_indexing_the_same_document_twice_does_not_duplicate`、`test_reindexing_with_a_new_parse_version_replaces_the_old_chunks` | 未测试（用模拟应答验证请求内容的版本已通过，见 `tests/unit/test_text_index.py`） |
| T13 | 删除后查不到 | `test_text_index_live.py::test_deleted_document_cannot_be_found_in_either_index` | 未测试（同上） |
| T14 | 端到端：上传 PDF → 等任务完成 → chunks 索引中有该文档的数据 | `test_pipeline_db.py::test_upload_parse_index_then_delete_and_cleanup` | 未测试（需要 PostgreSQL 和 OpenSearch；处理函数用假数据库和假检索服务的版本已通过，见 `tests/unit/test_pipeline.py`） |
| T15 | 删除后立即查不到 | `test_search_db.py::test_deleted_document_disappears_from_search_immediately`、`test_deleted_document_is_hidden_from_admin_too` | 未测试（检索编排把数据库访问换成替身的版本已通过，见 `tests/unit/test_search_service.py`） |
| T15 | 取消共享后立即查不到 | `test_search_db.py::test_unsharing_removes_the_document_from_search_immediately` | 未测试（同上） |
| T15 | 同一文件不重复出现 | `test_search_db.py::test_document_hit_by_both_channels_appears_once_with_both_ranks` | 未测试（RRF 的合并已由 `tests/unit/test_search_rrf.py` 验证） |
| T15 | 服务故障与“无结果”可以区分 | `test_search_db.py::test_no_match_is_200_with_an_empty_list`、`test_search_service_down_is_503_search_unavailable` | 未测试（同上，`test_search_service.py`） |

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

### T13 `test_text_index_live.py`（13）

- 创建索引：`test_ensure_indices_is_idempotent`
- 重复索引与版本替换：`test_indexing_the_same_document_twice_does_not_duplicate`、`test_reindexing_with_a_new_parse_version_replaces_the_old_chunks`、`test_reindexing_one_document_leaves_other_documents_alone`、`test_doc_meta_written_twice_is_one_record_with_the_latest_values`、`test_body_chunks_survive_a_later_write_of_ocr_chunks_in_the_same_version`
- 删除：`test_deleted_document_cannot_be_found_in_either_index`、`test_deleting_twice_or_deleting_an_unknown_document_is_fine`
- 分词与检索：`test_chinese_text_is_searchable_by_word`、`test_analyzer_is_smartcn_and_splits_chinese_into_words`、`test_file_name_and_tags_are_searchable`、`test_source_type_filter_separates_body_from_ocr`
- mapping：`test_strict_mapping_rejects_unknown_fields`

特别说明：`tests/unit/test_text_index.py` 的 41 项用替换掉的网络应答验证了“发出去的请求长什么样、收到各种应答时怎么处理”，但应答是按文档写的，OpenSearch 实际是否这样应答没有验证过。

### T14 `test_pipeline_db.py`（23）

需要 PostgreSQL（21 项）：

- 文档状态跟随 parse 任务：`test_non_retryable_parse_failure_marks_the_document_failed`、`test_retryable_failure_with_attempts_left_does_not_mark_the_document_failed`、`test_last_allowed_attempt_failing_marks_the_document_failed`、`test_task_of_a_crashed_worker_running_out_of_attempts_marks_the_document_failed`、`test_reclaimed_task_with_attempts_left_leaves_the_document_alone`、`test_failure_of_other_task_types_does_not_change_the_document`、`test_a_failed_parse_task_does_not_overwrite_a_succeeded_document`、`test_only_the_document_of_the_failed_task_is_touched`、`test_retrying_a_failed_parse_task_puts_the_document_back_to_pending`、`test_retrying_a_failed_ocr_task_does_not_change_the_document`
- parse 处理函数（检索服务是假的）：`test_parse_writes_chunks_status_and_parse_version`、`test_parsing_twice_does_not_duplicate_chunks`、`test_reparsing_with_new_parameters_replaces_the_old_version`、`test_ocr_chunks_of_the_current_version_survive_a_reparse`、`test_scanned_pdf_creates_ocr_tasks_once`、`test_image_asset_is_written_once`、`test_tags_from_the_database_reach_doc_meta`、`test_soft_deleted_document_is_not_parsed`
- cleanup 处理函数：`test_cleanup_removes_record_dependents_and_file`、`test_cleanup_twice_is_harmless`、`test_cleanup_refuses_a_live_document`

另外需要 OpenSearch（2 项，真实 Worker 主循环 + 真实子进程）：

- 🧪 `test_upload_parse_index_then_delete_and_cleanup`：上传 → Worker 处理 → 两个索引里有数据 → 删除 → 立即 404 → 清理后索引、文件、记录都没了
- `test_corrupt_upload_ends_as_failed_document_with_reason`：坏文件上传成功、解析失败不重试、文档显示 failed、文件保留、仍能按文件名检索

特别说明：`tests/unit/test_pipeline.py` 的 30 项用假的数据库会话和假的检索服务验证了处理函数的步骤顺序和分支，但真实数据库上的约束、级联删除和 SQL 都没有执行过。

### T15 `test_search_db.py`（20）

OpenSearch 用假的网络层代替（替换 `app.state.text_index`），专门检验数据库这一侧的保证。需要 PostgreSQL（19 项）：

- 🧪 删除与共享：`test_deleted_document_disappears_from_search_immediately`、`test_deleted_document_is_hidden_from_admin_too`、`test_unsharing_removes_the_document_from_search_immediately`
- 权限：`test_other_peoples_documents_never_appear_even_if_the_index_leaks_them`、`test_permission_prefilter_is_sent_to_the_index`、`test_admin_sees_everyone_s_documents`、`test_document_whose_record_is_gone_is_dropped`
- 🧪 文件级去重：`test_document_hit_by_both_channels_appears_once_with_both_ranks`
- 🧪 无结果与故障：`test_no_match_is_200_with_an_empty_list`、`test_search_service_down_is_503_search_unavailable`
- 检索日志：`test_every_search_is_logged_including_failures`、`test_successful_search_log_lists_the_results`、`test_invalid_request_is_not_logged`
- 请求校验：`test_search_requires_login`、`test_malformed_requests_are_422`（5）

另外需要 OpenSearch（1 项）：

- `test_full_text_search_against_a_real_index`：真实索引上检索命中、摘要带 `<em>`、只开 meta 通道（B0）、删除后立即查不到

### T16 `test_document_text.py`（11）

需要 PostgreSQL：

- `test_returns_chunks_of_the_current_version_in_order`、`test_pagination`、`test_filter_by_source_type`
- 跳转：`test_chunk_id_jumps_to_the_page_containing_it`、`test_stale_chunk_id_falls_back_to_the_first_page`、`test_invalid_or_foreign_chunk_id_is_422`（2）
- 其他：`test_unparsed_document_returns_an_empty_list`、`test_permissions`、`test_deleted_or_unknown_document_is_404`、`test_invalid_source_type_is_422`

### T17 `test_ocr_worker_db.py`（10）

需要 PostgreSQL。用 OCR Worker 自己的 `PgStore`（psycopg 直接写 SQL）对真实表结构读写：

- `test_document_state_is_read`、`test_save_writes_result_and_chunks`、`test_saving_the_same_page_twice_replaces_instead_of_adding`、`test_other_pages_and_body_chunks_are_untouched`、`test_empty_result_still_replaces_the_old_one`、`test_failure_inside_the_transaction_leaves_the_old_data`、`test_hard_deleting_the_document_removes_ocr_rows`
- 竞争：`test_save_refuses_when_the_document_was_reparsed`、`test_save_refuses_when_the_document_was_deleted`
- `test_ping`

### T18 `test_consistency_db.py`（12）

需要 PostgreSQL。OpenSearch 用假的网络层代替：

- `test_consistent_database_has_no_issues`、`test_collect_db_reads_tags_cleanup_tasks_and_ocr_targets`
- 三类人为制造的不一致（DEVPLAN 的 🧪）：`test_file_deleted_from_disk_is_detected`（磁盘）、`test_record_deleted_behind_the_index_is_detected_and_repaired`（索引）、`test_old_version_chunks_are_detected_and_repaired`（数据库）
- 修复：`test_stale_ocr_results_are_removed`、`test_deleted_document_without_cleanup_gets_a_cleanup_task`、`test_orphan_file_is_deleted_but_a_referenced_file_never_is`、`test_reindex_rebuilds_a_document_from_the_database`、`test_rebuild_indices_recreates_both_and_reindexes_live_documents`、`test_index_repairs_are_skipped_when_the_search_service_is_down`
- 误删防护：`test_chunks_of_a_document_being_parsed_are_never_deleted`

### T19 `test_experiments_db.py`（8）

需要 PostgreSQL，检索服务用假的：

- `test_experiment_user_is_created_once_as_admin`
- 运行前检查：`test_preflight_passes_on_a_clean_dataset`、`test_preflight_reports_every_problem`
- `test_version_snapshot_lists_parse_versions_and_ocr_models`
- `test_import_uploads_once_and_records_the_mapping`
- `test_full_run_writes_results_metrics_and_an_experiment_row`、`test_run_refuses_when_preflight_fails`、`test_run_with_search_service_down_is_incomplete`

## 4. 不是测试、但同样没有验证过的性质

| 项目 | 说明 | 记录位置 |
|---|---|---|
| Worker 子进程的内存上限 | 用 `RLIMIT_AS` 实现，只在 Linux 上有效；开发机是 macOS，内核基本不执行这个限制 | `decisions.md` D16 |
| 后端连上真实数据库后的整体运行 | 没有在本机启动过“后端 + PostgreSQL”，注册、上传、下载等接口没有人工点过一遍 | — |
| `deploy/docker-compose.yml` | 只校验过语法，容器从未启动 | DEVPLAN §5 T01 |
| 前端与真实后端的联调 | **未测试。** 本机没有 PostgreSQL，真实后端的登录、上传等接口跑不起来。T10 的页面是对着一个临时写的模拟接口在浏览器里检查的（模拟接口按 `api.md` 的结构应答，不是项目代码，没有提交）。前端与真实后端之间的不一致——字段名、状态码、multipart 的细节——这种检查发现不了。T16 的检索页、预览页和抽取文本接口同样只对着模拟接口检查过（检索、PDF 跳页、Word 跳到命中段、图片、503 与空结果的区分），从未与真实后端和真实 OpenSearch 联调 | DEVPLAN §5 T10、T16 |
| 前端页面组件的自动化测试 | 没有写，项目里也没有组件测试工具（加装需要 Barry 同意）。48 项前端单元测试只覆盖接口封装、格式化、摘要清洗和位置格式；登录页、文件列表、共享对话框、检索页、预览页、PDF 查看器只做过人工浏览器检查 | DEVPLAN §5 T10、T16 |
| PDF 预览在真实文件上的表现 | 只用模拟接口返回的一份 5 页、纯英文、PyMuPDF 现场生成的测试 PDF 验证过跳页、翻页、缩放。没有用中文、扫描件、大文件（接近 50 MB）或加密的 PDF 试过 | `decisions.md` D29 |
| 真实后端经开发代理的访问 | **部分验证。** T05–T10 核查时启动了真实后端（数据库地址指向不存在的端口）和真实的前端开发代理，用 curl 验证了不需要数据库的路径：健康检查、数据库不可用返回 503、未登录 401、参数校验 422、未登录上传（multipart 经代理）401、超大上传 413。需要数据库的路径（登录成功之后的一切）仍未验证 | DEVPLAN §5 核查记录 |
| Windows 上的运行 | 存储模块和 Worker 加了两处兼容处理（`O_NOFOLLOW`、`resource` 模块在 Windows 上不存在），但从未在 Windows 上运行过任何代码或测试 | — |
| 管理员视角的前端 | 模拟接口里没有管理员账号，页面上“管理员”标记和“管理员可见”来源没有实际显示过 | — |
| PDF 解析器在真实文件上的表现 | T09 的测试用 PyMuPDF 现场生成的 PDF；没有用真实的扫描件、多栏排版、带表格或带水印的 PDF 验证过，阈值 20 也没有实验依据 | `decisions.md` D20 |
| Word、Excel、图片解析器在真实文件上的表现 | T11 的测试文件是用 python-docx、openpyxl、PyMuPDF 现场生成的；没有用 Microsoft Word / Excel / WPS 实际保存的文件、手机或相机拍的照片验证过。尤其是 Excel 公式的缓存值，测试里是手工改 XML 模拟的 | `decisions.md` D24 |
| 解析超时对真实解析器的作用 | 超时在 Worker 子进程边界执行，机制本身有测试（`test_worker_runner.py`）；但解析器要到 T14 才接入 Worker，“一个真的卡住的解析被杀掉”还没有端到端跑过 | `decisions.md` D24 |
| 两个 mapping 文件能否被 OpenSearch 接受 | `doc_meta.json`、`chunks.json` 从未被任何 OpenSearch 接受过：分析器 `docmgr_text` 的定义 `{"type": "smartcn"}`（依赖插件注册的 smartcn 分析器类型）、在 index 设置里改写默认相似度为 BM25 的写法、`dynamic: strict`、`locator` 的 `enabled: false`。任何一处不被 2.19.1 接受，创建索引就整体失败 | `decisions.md` D26 |
| mapping 文件随安装包发布 | T17 起 mapping 在 `shared/text_index/mappings/`，`shared/pyproject.toml` 声明了 package-data（`shared.text_index` 下的 `mappings/*.json`）。两个环境都是 editable 安装，没有做过普通安装来验证文件确实被打包。验证方法：在一个临时虚拟环境里 `pip install ./shared`（会联网下载依赖，按规则先征得同意），然后确认 `site-packages/shared/text_index/mappings/` 下有两个 JSON 文件 | `decisions.md` D26、D30 |
| B0–B2 实验 | 从未在真实数据上运行过：现在没有评测数据集和标注；也从未连真实 PostgreSQL 和 OpenSearch 跑过导入和运行。指标计算本身已用手算样例验证（单元测试） | `decisions.md` D32 |
| 一致性检查对真实 OpenSearch 的操作 | 索引扫描（`search_after` 分页）、结构检查（`_mapping`、`_settings` 的返回结构）、单个文档重建和 `rebuild-indices` 全部重建都从未在真实 OpenSearch 上运行过；单元测试和集成测试里的应答是按文档写的 | `decisions.md` D31 |
| 一致性检查在真实数据上的运行 | 从未对一个真实使用过的系统跑过 `check` 和 `repair`，误报率、耗时和内存占用都没有数据 | `decisions.md` D31 |
| OCR Worker 的完整链路 | 从未连过真实的 PostgreSQL 和 OpenSearch：领取 ocr 任务 → 识别 → 写 OCRResult 和 DocumentChunk → 写 chunks 索引 → 复查。主循环、续约、超时杀子进程只用假队列和假数据库测过（`services/ocr_worker/tests/`）；识别本身在 ocr 环境里用真实模型测过（4 项通过） | `decisions.md` D30 |
| OCR 在真实文件上的表现 | 只用 PyMuPDF 现场生成的扫描版 PDF 页、图片和空白图验证过；没有真实扫描件、手机照片、多栏排版、竖排或手写文字 | `decisions.md` D30 |
| OCR 子进程的内存上限 | `OCR_WORKER_MEMORY_LIMIT_MB` 用 `RLIMIT_AS` 实现，只在 Linux 上有效；本机（macOS）启动时打印“无法设置识别子进程的内存上限”，只受超时保护。没有在 Linux 上验证过 | `decisions.md` D16、D30 |
| `deploy/opensearch/Dockerfile` | 从未构建过。安装 analysis-smartcn 需要联网 | `decisions.md` D26 |
| `deploy/docker-compose.yml` 的语法 | 只用 macOS 自带的 Ruby 读过一遍 YAML，确认结构和 `build`、`image` 两项能读出来；没有用 `docker compose config` 校验过（本机没有 Docker），compose 自己的规则没有检查 | — |
| smartcn 的切分效果 | A13 选定时没有任何实测数据，切分是否合理、对 B0–B2 的影响要到阶段五 | `decisions.md` A13 |
| `shared/tasks.py` 新增的 SQL | T14 给 `fail` / `reclaim_expired` 加的 `RETURNING status, task_type, document_id` 和更新文档状态的 `_MARK_DOCUMENTS_FAILED_SQL` 从未在任何数据库上执行过。已人工核对：psycopg 把 uuid 列表适配成数组、`documents.updated_at` 列确实存在、加锁顺序与重试接口一致 | `decisions.md` D27 |
| 真实子进程里的处理函数 | `handle_parse`、`handle_cleanup` 和 `worker/context.py` 的 `task_context` 从未在真实的 Worker 子进程里运行过。子进程按环境变量和 `.env` 读配置、自己连数据库和 OpenSearch，这条路径只有端到端测试覆盖 | `decisions.md` D27 |
| `action.auto_create_index: "false"` | 只写进了 `deploy/docker-compose.yml`，没有在真实 OpenSearch 上确认它生效、也没有确认它不影响 `ensure_indices` 显式建索引 | `decisions.md` D27 |
| cleanup 硬删除与续租的配合 | 硬删除后任务记录被级联删除，父进程的下一次续租会把子进程按“租约丢失”终止。代码把硬删除放在最后一步来规避，但真实时序没有观察过 | `decisions.md` D27 |
| 切分参数对检索效果的影响 | 默认 500 字、重叠 50 字是经验值。“片段长度、重叠、是否给 Excel 片段补表头”对 B1、B2 的影响要到阶段五才有数据 | `decisions.md` D25 |
| zip 与像素上限的默认值 | 200 MB、5000 个条目、1 亿像素都是经验值；没有用接近上限的真实大文件测过解析时的内存和耗时 | `decisions.md` D24 |
| 检索查询能否被 OpenSearch 接受 | T15 的两个查询体从未被真实 OpenSearch 接受过：`chunks` 查询同时使用 `collapse`（按 `document_id`）、`sort`（`_score` 后接 `document_id`）和 `highlight`（`encoder=html`、`number_of_fragments=1`、`no_match_size`）；`doc_meta` 查询用 `multi_match` 带小数权重。已人工核对这几项在 2.19 上可以同时使用，分数从 `hit.sort[0]` 取 | `decisions.md` D28 |
| smartcn 下的高亮效果 | 摘要是否落在命中词附近、长度是否接近 `SEARCH_SNIPPET_CHARS`，没有实际看过 | `decisions.md` D28 |
| 高亮摘要的 HTML 转义 | 原文含 `<script>` 等标签时，命中片段和 `no_match_size` 截取的片段是否都被转义，需要在 OpenSearch 上实测（第 5 节 OpenSearch 测试第 7 步）。前端（T16）用 `v-html` 显示摘要之前必须确认 | `decisions.md` D28 |
| OpenSearch、中文分词、并发内存 | T00 环境实测中未完成的部分。补测步骤见第 6 节 | `env_check/未测试/清单.md` |

## 5. 补测方法

需要一个 PostgreSQL 16 实例和一个**空的**专用测试库（库里已有表时测试会直接失败，不会清库）。

1. 建库 `docmgr_test`，把连接串写进 `.env` 的 `TEST_DATABASE_URL`（格式见 `.env.example`）。
2. 在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && ../.venv-main/bin/pytest
   ```

3. 预期结果：除 `tests/opensearch/` 的 13 项、`test_pipeline_db.py` 的 2 项端到端测试和 `test_search_db.py` 的 1 项真实索引测试外全部运行。两类都补测时的预期见下面的“OpenSearch 测试”。
4. 有失败的话先修；全部通过后更新本文件和 DEVPLAN §5。

在另一台机器上补测时，把那台机器的系统和 PostgreSQL 版本一起记下来。

**OpenSearch 测试（T13 的 13 项、T14 的 2 项端到端、T15 的 1 项）**

需要一个装了 analysis-smartcn 插件的 OpenSearch 2.19.1。最简单的办法是用项目自己的 `deploy/docker-compose.yml` 启动（第 6 节第 6 步），它会构建带插件的镜像。

1. 确认插件已装：`curl -s "http://127.0.0.1:9200/_cat/plugins?v"` 的输出里有 `analysis-smartcn`。
2. 在 `backend/` 目录执行：

   ```bash
   TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/opensearch -v
   ```

3. 测试只使用形如 `test_xxxxxxxxxx_doc_meta` 的独立索引，结束时只删除自己建的索引，不碰 `doc_meta`、`chunks` 正式索引。即使这样，也不要对着有真实数据的 OpenSearch 运行。
4. 预期结果：13 项全部通过。最先可能失败的是创建索引（mapping 写法不被接受），报错会写明是哪个字段或设置。
5. T14 的 2 项端到端测试同时需要数据库和 OpenSearch，并且会启动真实的 Worker 子进程。在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/integration/test_pipeline_db.py -v
   ```

   测试会把配置写进环境变量，交给子进程读取（环境变量优先于 `.env`）；索引同样使用带随机前缀的独立索引。
6. T15 的 1 项真实索引测试同样需要两者，在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/integration/test_search_db.py -v
   ```

   预期 20 项全部通过。
7. 高亮摘要的转义（没有自动化测试，手工做一次）：用一个带随机前缀的测试索引，写入一条 `text` 为 `<script>alert(1)</script> 报销标准` 的片段，分别查“报销”（有命中词）和只靠词干匹配、没有可高亮词的查询，确认返回的 `evidence.snippet` 里 `<script>` 显示为 `&lt;script&gt;`，只有 `<em>` 是标签。结果记到本文件第 4 节对应的行。
8. 同时设置 `TEST_DATABASE_URL` 和 `TEST_OPENSEARCH_URL` 运行整个 `pytest`，预期 728 项全部运行，0 项跳过（backend 目录）。

## 6. OpenSearch 相关的未测试项与补测步骤

更新日期：2026-11-14（T13 开始前）

### 6.1 为什么没测

本机（Apple M4，24 GB 内存，macOS 26.6.2）上没有能运行 OpenSearch 的环境：

- Barry 决定不在本机安装和运行 Docker；
- 本机没有 Java 运行时（`/usr/bin/java` 只是系统占位程序，执行时提示找不到 Java）；
- OpenSearch 官方没有发布 macOS 的正式安装包（2026-11-14 查询，只找到面向开发者的快照构建）。

按 GLOBAL.md“测试执行限制”，这些测试不在本机强行执行，也不为它们安装任何东西，统一登记在这里。

### 6.2 未测试项

| 编号 | 项目 | 用什么测 | 要回答的问题 | 影响 |
|---|---|---|---|---|
| OS-1 | OpenSearch 能否启动，版本、插件列表 | `env_check/01_check_opensearch.py` | OpenSearch 2.19.1 能否稳定运行 | T13、T21 |
| OS-2 | 中文分词对比：standard / smartcn / IK | 同上 | 附录 A13 选哪个分词器 | T13 的 mapping，`deploy/docker-compose.yml` 的镜像 |
| OS-3 | BM25 查询结果与延迟 | 同上 | 基线延迟量级 | T15 |
| OS-4 | 带权限过滤的精确向量检索（`script_score`） | 同上 | 附录 A12 的做法在 2.19.1 上能否运行 | T21 |
| OS-5 | JVM 堆（1g，必要时 2g）与内存占用 | 同上 | 堆大小；附录 A14 是否启用降级预案 | T13、T21 |
| OS-6 | 四个组件同时运行时的总内存与 swap | `env_check/04_mem_snapshot.py` | 一台机器能否同时运行全部组件 | 开发时是否按需启停 CLIP |
| OS-7 | 项目自己的 `deploy/docker-compose.yml` 能否启动，`/health` 是否报告 OpenSearch 为 ok | Docker + 后端 | T01 的 compose 文件和健康检查在真实容器上是否正确 | T01 |
| OS-8 | T13 文本索引的集成测试（13 项，含重复索引不产生重复数据、删除后查不到） | `backend/tests/opensearch/test_text_index_live.py` | T13 的 🧪；两个 mapping 能否被接受 | T13，T14 起所有依赖索引的任务 |
| OS-9 | T14 端到端测试（2 项，另需 PostgreSQL） | `backend/tests/integration/test_pipeline_db.py` 的 `test_upload_parse_index_then_delete_and_cleanup`、`test_corrupt_upload_ends_as_failed_document_with_reason` | T14 的 🧪；真实子进程里的处理函数；`action.auto_create_index` | T14 起的整条写入链路 |
| OS-10 | T15 真实索引检索（1 项，另需 PostgreSQL）与高亮转义手工检查 | `backend/tests/integration/test_search_db.py` 的 `test_full_text_search_against_a_real_index`；第 5 节 OpenSearch 测试第 7 步 | T15 的查询体能否被接受；摘要转义 | T16 前端显示摘要 |

OS-1 至 OS-6 与 `env_check/未测试/清单.md` 的 1–6 项一一对应。

### 6.3 测试机器要求

- 能运行 Docker 的电脑：Docker Desktop（macOS / Windows）或 Docker Engine（Linux）都可以。不必是本机——Barry 决定本机不装 Docker。
- 内存至少 8 GB，Docker 可用内存设为 4 GB 以上（Docker Desktop：Settings → Resources → Memory）。
- 能访问 Docker Hub（拉取 `opensearchproject/opensearch:2.19.1`）。构建实测镜像时，容器内要能从 OpenSearch 官方地址下载 analysis-smartcn 插件。
- Python 3.11。
- **下载提醒：** 下面的步骤会下载 Docker 镜像（OpenSearch 官方镜像 1 GB 左右）、smartcn 插件和 Python 包 psutil。按 CLAUDE.md，下载前先确认，下载后登记到 `docs/downloads.md`，并写明是在哪台机器上装的。

### 6.4 详细步骤

以下命令都在**测试机器**上执行。`<项目目录>` 指测试机器上本仓库的根目录（用 `git clone` 或直接拷贝整个目录都可以）。

**第 0 步：记录测试机器**

```bash
cd <项目目录>/env_check
python3.11 -m venv .venv-main
.venv-main/bin/pip install -r requirements-main.txt
.venv-main/bin/python 00_sysinfo.py
```

```bash
mv results/00_sysinfo.json results/00_sysinfo.testbox.json
git checkout -- results/00_sysinfo.json   # 恢复仓库里开发机的那份；不是 git 克隆的，就从开发机拷一份回来
```

`00_sysinfo.py` 记下测试机器的 CPU、内存和系统版本，但它固定写到 `results/00_sysinfo.json`，会盖掉仓库里开发机的那份，所以运行后立刻改名，再把开发机的恢复回来。在另一台机器上测得的延迟和内存不代表开发机，写进论文时要注明是哪台机器。

**第 1 步（可选）：决定是否同时测 IK**

1. 到 IK 插件的发布页查找与 OpenSearch **2.19.1 完全一致**的发行包（zip 文件名或说明里写明 2.19.1）。
2. 找到了：打开 `env_check/opensearch/Dockerfile`，取消最后两行的注释，把 `IK_URL=` 填成那个 zip 的地址。
3. 找不到：不装 IK，在结果里写明“IK 没有与 2.19.1 匹配的版本”。这本身就是一条结论：选 IK 就要更换 OpenSearch 版本。

**第 2 步：构建并启动实测用的 OpenSearch（OS-1）**

```bash
cd <项目目录>/env_check/opensearch
docker compose up -d --build
```

等它启动。正常情况下一分钟以内，下面的命令会返回带 `"status"` 的 JSON：

```bash
curl -s http://127.0.0.1:9200/_cluster/health
```

- 返回的 `status` 为 `green` 或 `yellow`：启动成功。单节点时 `yellow` 是正常的。
- 两分钟后仍然连不上：执行 `docker compose logs --tail 100`，把输出保存下来，记为 OS-1 失败，不要往下做。

确认插件已安装（输出里应有 `analysis-smartcn`，装了 IK 的话还有 IK）：

```bash
curl -s "http://127.0.0.1:9200/_cat/plugins?v"
```

**第 3 步：运行实测脚本（OS-1 至 OS-5）**

```bash
cd <项目目录>/env_check
.venv-main/bin/python 01_check_opensearch.py
```

结果写入 `results/01_opensearch.json`。脚本依次做这些事：读版本和插件；用每个候选分词器切分同一句中文；用最好的可用分词器建测试索引，跑 6 个查询；测 BM25 和向量检索的延迟；读 JVM 堆。

**第 4 步：换 2g 堆再测一次（OS-5，只在需要时做）**

满足任意一条才需要做：第 3 步出现内存不足错误、查询明显卡顿、JVM 堆用量接近上限。

```bash
cd <项目目录>/env_check
cp results/01_opensearch.json results/01_opensearch_1g.json
OS_HEAP=2g docker compose -f opensearch/docker-compose.yml up -d --force-recreate
# 等第 2 步的 curl 恢复返回后：
.venv-main/bin/python 01_check_opensearch.py
cp results/01_opensearch.json results/01_opensearch_2g.json
```

**第 5 步：并发内存（OS-6）**

这一步要求测试机器上已经按 `env_check/README.md` 第 1 步建好 ocr 和 clip 两个环境，并下载了模型。做不到就跳过，记为“OS-6 未测试”。

保持 OpenSearch 运行，开三个终端，都先 `cd <项目目录>/env_check`：

```bash
# 终端 B
.venv-ocr/bin/python 02_check_ocr.py --mobile --hold
```

```bash
# 终端 C
.venv-clip/bin/python 03_check_clip.py --hold
```

```bash
# 终端 D（等 B、C 都显示模型已加载后再运行）
.venv-main/bin/python 04_mem_snapshot.py
```

完成后在终端 B、C 按 Ctrl+C。结果写入 `results/04_mem_snapshot.json`。

**第 6 步：项目自己的 compose 与健康检查（OS-7）**

先关掉实测用的 OpenSearch，它和项目的 OpenSearch 都占用 9200 端口：

```bash
cd <项目目录>/env_check/opensearch && docker compose down
```

```bash
cd <项目目录>
cp .env.example .env
```

编辑 `.env`：

- 把 `POSTGRES_PASSWORD` 改成自己的密码，`DATABASE_URL` 里的密码要与它一致；
- `JWT_SECRET` 换成一个随机值，可以用 `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成。

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

```bash
python3.11 -m venv .venv-main
.venv-main/bin/pip install -e "shared[dev]" -e "backend[dev]"
```

```bash
cd backend && ../.venv-main/bin/alembic upgrade head
```

```bash
cd backend && ../.venv-main/bin/uvicorn app.main:create_app --factory
```

在另一个终端执行：

```bash
curl -s http://127.0.0.1:8000/health
```

预期：`database` 和 `opensearch` 都是 `"ok"`；`clip_service` 是 `"unavailable"`（CLIP 服务还没写，属于正常）；整体 `status` 为 `"degraded"`。

这一步顺带让第 5 节的 91 项数据库集成测试有了 PostgreSQL，可以接着按第 5 节补测。

**第 7 步：T13 集成测试（OS-8）**

在第 6 步启动的 OpenSearch 上运行（项目的镜像已装 analysis-smartcn）：

```bash
cd <项目目录>/backend && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/opensearch -v
```

预期 13 项全部通过。测试只操作带随机前缀的索引，结束时自行删除。

**第 8 步：收尾**

```bash
cd <项目目录> && docker compose --env-file .env -f deploy/docker-compose.yml down
```

`down` 不加 `-v`，数据卷保留。

### 6.5 结果怎么读、怎么用来定 A13 和 A14

**A13（选哪个分词器），看 `results/01_opensearch.json` 的 `analyzers`：**

| 现象 | 结论 |
|---|---|
| `standard` 把中文逐字切开 | 正常现象，证明必须装中文分词插件 |
| `smartcn` 把“文档管理”“信息检索”“跨模态”这类词切成完整的词或合理的两字词 | smartcn 可用 |
| 装了 IK，`ik_max_word` 切得明显更合理（专业词完整、没有错切） | 可以考虑 IK，但要接受“版本必须严格匹配”的维护代价 |
| 两者差别不大 | 选 smartcn：官方插件，与 OpenSearch 同版本发布，以后升级不会卡在插件上 |

另外看 `bm25_hits`：脚本用选出的分词器建了一个 6 条记录的测试索引，跑 6 个查询。按测试数据，排第一的应当分别是：财务报告 → d1，发票 → d2，路由协议 → d3，检索模块 → d4，图文模型 → d5，预算 → d1。排第一的不对，或者没有命中，要记下来。注意：脚本只用选出的那一个分词器建索引（装了 IK 时优先用 `ik_max_word`，否则用 `smartcn`），要比较两者的检索结果，需要改脚本第 112 行的选择顺序后再跑一次。

**A14（是否启用降级预案）：同时满足下面三条就不启用，继续用 OpenSearch。**

1. 第 2 步启动成功，集群状态为 `green` 或 `yellow`；
2. 1g 堆（或第 4 步的 2g 堆）下没有内存不足错误，查询延迟在几十毫秒以内；
3. 第 5 步的 `system_available_gb` 不低于 1.5 GB，`swap_used_gb` 没有持续增长。

任何一条不满足，就把数据交给 Barry，由 Barry 决定是否启用降级预案（GLOBAL §11.4，必须 Barry 同意）。

### 6.6 测完之后要做的事

1. 把测试机器上 `env_check/results/` 里的这些文件拷回开发机的同一目录：`00_sysinfo.testbox.json`、`01_opensearch.json`（做了第 4 步的，还有 `01_opensearch_1g.json`、`01_opensearch_2g.json`）、`04_mem_snapshot.json`，以及 `history/` 下新增的带时间戳的文件。不要拷 `00_sysinfo.json`。
2. 在开发机上运行 `cd env_check && .venv-main/bin/python 05_make_report.py`，重新生成 `env_check/env_report.md`。报告的第 1 节仍是开发机，第 2 节（OpenSearch）和第 5 节（并发内存）来自测试机器，要在这两节开头手工注明“测于另一台机器”，并引用 `00_sysinfo.testbox.json` 里的配置。
3. 在 `docs/decisions.md` §2 填写 A13、A14、JVM 堆大小的结论，并写明测试机器。
4. A13 选定后修改 `deploy/docker-compose.yml`：改用装了所选插件的镜像。插件版本必须与 OpenSearch 版本完全一致。
5. 把通过的项从本节删除；失败的项留在这里，写明失败现象，并附上日志。
6. 在 `docs/downloads.md` 登记测试机器上下载的内容。
