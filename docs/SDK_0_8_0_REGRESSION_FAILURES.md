# 0.8.0 原完整回归失败追踪

原始来源：`/tmp/sdk-consumer-identity-candidate-20261106/partial-failures.json`。原内层在2700秒截止前记录77条即时错误，包含子测试和加载错误，不是77个独立测试，也不是完整套件错误总数。

此表只追踪该原始快照，不替代G01–G18或当前完整回归。定向通过不改写原失败；尚未复验的条目继续保留。

历史定向产品：`/tmp/sdk-entry-projection-candidate-20261106`，149个冻结产品Python文件与独立安装包直接字节一致。相关组合：`related-result.json`、`related.log`（92通过、2权限跳过）；两项补跑：`tool-cleanup-result.json`（2通过、0跳过）。子任务交付：`/tmp/sdk-child-delivery-fixture-20261106/result.json`（9通过、0跳过）。

| 原始模块分组 | 即时错误条目 | 当前证据状态 |
| --- | ---: | --- |
| `unittest` | 7 | 当前安装包原7模块62项全通过、0跳过；/tmp/sdk-script-closure-installed-20261106/result.json |
| `test_agents_application` | 1 | 最新child-entry-marker安装包完整模块通过；legacy-contract-result.json/legacy-contract.log，组合58项0跳过 |
| `test_agents_control_reopen` | 1 | 最新child-entry-marker安装包完整模块通过；legacy-contract-result.json/legacy-contract.log，原不明准入与重开断言保留 |
| `test_agents_dependency_app_hooks` | 2 | 整个模块已通过；相关组合 related.log |
| `test_agents_technical_retries` | 1 | 最新child-entry-marker安装包完整15/16，原两秒post-abort前提未达到；四个监督重试等待错误已通过；原失败保留 |
| `test_agents_tool_cleanup_diagnostics` | 2 | 原失败两项已补跑通过，无跳过；tool-cleanup-result.json |
| `test_application` | 1 | 当前安装包完整12项通过；legacy-core-installed result.json/check.log |
| `test_budget_scan_runtime_handoff` | 2 | 整个模块已通过；相关组合 related.log |
| `test_child_call_concurrency` | 1 | 最新child-entry-marker安装包完整模块通过；legacy-contract-result.json/legacy-contract.log，原并发与取消断言保留 |
| `test_child_completed_result_delivery` | 11 | 整个模块9项通过，无跳过；child-delivery result.json |
| `test_child_completion_handoff` | 7 | 夹具修正；整个模块及child持锁清理联合19项通过，无跳过 |
| `test_child_storage_contention` | 2 | 最新child-entry-marker安装包完整模块通过；legacy-contract-result.json/legacy-contract.log，原持锁/到期/取消断言保留 |
| `test_completion_admission` | 2 | v14夹具补移除v19回执表并显式校验；整个模块13项通过、0跳过；/tmp/sdk-completion-admission-fixture-20261106/result.json |
| `test_completion_authority_schema` | 6 | 整个模块已通过；相关组合 related.log |
| `test_completion_delivery_authority_v16` | 4 | 历史模式、采样探针／读取路径及取消异常预期修正；整个模块31项通过、0跳过；/tmp/sdk-v16-fixture-installed-20261106/result.json |
| `test_completion_global_pending_guard` | 1 | 旧合同预期修正；当前安装包两模块9项通过、0跳过；/tmp/sdk-clock-proof-recovery-fixed-20261106/result.json |
| `test_completion_late_commit_receipt` | 1 | 当前安装包复验通过；/tmp/sdk-completion-fence-receipt-fixed-20261106/result.json（两模块2项、0跳过） |
| `test_completion_snapshot_guard_order` | 1 | 当前安装包复验通过；/tmp/sdk-completion-fence-receipt-fixed-20261106/result.json（两模块2项、0跳过） |
| `test_completion_wrapped_restart` | 1 | 旧合同预期修正；当前安装包两模块9项通过、0跳过；/tmp/sdk-clock-proof-recovery-fixed-20261106/result.json |
| `test_control_takeover_foundation` | 2 | 历史夹具升级链补齐至v19；三模块11项当前安装包通过、0跳过；/tmp/sdk-lifecycle-schema-fixtures-20261106/result.json |
| `test_copied_legacy_terminal_readback` | 1 | 整个模块当前安装包通过，包含于四模块33项／0跳过；core-deadline-fixtures-installed result.json |
| `test_execution_kernel_v2_runtime` | 10 | 最新preentry-monitor安装包完整31/31通过，0跳过；preentry-monitor-installed result.json/check.log；此前失败现场保留 |
| `test_execution_kernel_v2_sqlite` | 2 | 新库元数据引用当前schema常量，完整23项当前安装包通过；legacy-core-installed result.json/check.log |
| `test_execution_kernel_v3_managed_gate` | 1 | 整个模块当前安装包通过，包含于四模块33项／0跳过；core-deadline-fixtures-installed result.json |
| `test_g06_synthetic_entry` | 1 | 待定位或复验；不继承旧通过记录 |
| `test_handler_entry_contention` | 1 | 待定位或复验；不继承旧通过记录 |
| `test_kernel_pause_schema` | 1 | 历史夹具升级链补齐至v19；三模块11项当前安装包通过、0跳过；/tmp/sdk-lifecycle-schema-fixtures-20261106/result.json |
| `tests` | 1 | 待定位或复验；不继承旧通过记录 |
| `test_legacy_schema_split_store_lifecycle` | 1 | 整模块2项当前安装包通过；升级目标改用当前版本常量；/tmp/sdk-lifecycle-journal-barrier-20261106/result.json |
| `test_lifecycle_generation_retirement` | 1 | 历史夹具升级链补齐至v19；三模块11项当前安装包通过、0跳过；/tmp/sdk-lifecycle-schema-fixtures-20261106/result.json |
| `test_lifecycle_journal_handoff` | 1 | 原失败单项在有界诊断投递后通过；模块其余未全量复验；/tmp/sdk-lifecycle-journal-barrier-20261106/result.json |

后续优先处理尚未证明收敛的真实执行、交付和恢复路径。原加载错误与历史模式夹具分别修正；不得因缺环境、超时或夹具问题删减测试或把G18标为通过。

父完成采样／child持锁清理证据：`/tmp/sdk-child-handoff-fence-installed-20261106/result.json`及check.log（19项通过、0跳过）。

竞争／恢复当前复现：`/tmp/sdk-completion-recovery-current-20261106/result.json`，11项4失败；late_commit与snapshot后续已定向通过。global_pending_guard的legacy时间相等断言、wrapped_restart的original completion authority is unconfirmed仍未解决，不继承其他通过。

后续更新：上述global_pending_guard及wrapped_restart已完成代码／独立审查及测试前提修正，两模块9项当前安装包通过。原四项失败日志保留，不将时钟证明提升为完成授权；不是新的真实受管理恢复正例。

## 2026-11-06：Agent／child剩余组当前复现

`/tmp/sdk-agent-child-remaining-20261106/result.json`：29项、5失败／2错误／16权限跳过，55.451秒。注意临时driver将冻结source置于tests快照前，实际测试来自冻结source；本次没有对应新测试修改，不能以此验证后续测试改动。child并发、storage contention及入口截止仍失败；G06脚本闭包用例本次通过，尚未单独核验其完整证据范围。

本地端口获准补跑driver已修正tests路径优先级：`/tmp/sdk-agent-child-remaining-20261106/verify-sockets.py`，仅control_reopen与technical_retries。session80087仍在运行，结果目标socket-result.json，日志socket-check.log；原1分钟后复查仍运行、随后再1分钟仍运行，出现control_reopen及技术重试错误，不能记通过。下一次预计2分钟后检查同一handle，不重启、不延长原测试超时。

入口截止当前准确现场为原0.3秒窗口过期，底层来自_capture_budget_until的无采样尝试截止哨兵budget_clock_capture_deadline_elapsed，携准确非hard原cutoff，_confirm_handler_entry只接受TimeoutError／SQLite cause因而未分类为timed_out。独立只读审查确认需限定修复；尚未修改产品，不扩大未知采样的授权。

## 2026-11-06：原截止前无采样尝试分支修复

本地端口补跑session80087已退出1：socket-result.json记录18项、2错误、0失败／跳过，188.853秒。control_reopen不明准入及technical_retries原截止后中止仍报错，原日志socket-check.log保留；不再等待该session。

源码限定修复_confirm_handler_entry：仅精确budget_clock_capture_deadline_elapsed且无cause／token／captured envelope／context pending sample，才可在原有可信、同约束及started_at、非hard、准确原截止均已过的检查下拒绝为execution_deadline_exhausted；不ACK／清理采样、不确认入口。保留先前last_error为storage_error。测试按实际争用记录精确比对错误，不假造database is locked。独立审查对原predicate未发现权限阻断，并指出缺storage_error；该字段已修复，整合后源码8项通过4.272秒，/tmp/sdk-entry-sentinel-integrated-20261106.log。首轮缺字段失败保留/sdk-entry-contention-sentinel日志（准确路径/tmp/sdk-entry-contention-sentinel-20261106.log）。新增合成测试首轮漏_sample错误保留，纠正后四项通过。当前产品已变化，旧安装候选不能证明此修订；新包构建／验证尚待完成。其他child结算及Agent wait问题未解决。

## 2026-11-06：入口截止新安装包验证

新冻结候选`/tmp/sdk-pre-capture-expiry-candidate-20261106`已构建并独立安装。8项native_entry_cutoff／handler_entry_contention全部通过、0跳过，6.036秒，result.json及check.log；149个产品Python文件与该候选source直接字节一致。该新候选尚无其他完整范围证据，不继承旧候选结果为当前包全量通过。原handler_entry_contention错误已有新包对应复验。

独立只读调查Agent wait：原30／45秒到期后store deadline为未达到终态的表现，不应改异常来掩盖。technical_retries retained现场adapter调用0、入口未达，late_thread_fact为原截止哨兵，应在本修订后复验且仍需真正post-abort证据。control_reopen retained现场indeterminate control-admit effect伴随成功candidate，被未完成effects检查拒绝，执行直到父撤销才转recovery_required；需核实活跃worker准确lease/fence下的恢复状态转换，未修改该产品路径。

## 2026-11-06：活跃执行不确定效果恢复修订

源码runtime线程受管理路径在成功返回后查询同attempt/fence未完成效果，若存在则仅请求recovery_required，不提交成功。既有活跃权限／stop／lifecycle检查后，由Kernel原子核对lease及exact_effect_generation，严格截止限制在原预算和0.1秒操作窗。独立审查发现新增查询异常会越过原保留路径，已补捕获异常及仅类型诊断，继续原子完成检查而不以查询失败推断无效果。

源码原control_reopen不明准入失败单项通过11.302秒，/tmp/sdk-control-reopen-live-recovery-20261106.log；加入查询异常保留后整模块2项通过26.429秒，/tmp/sdk-control-reopen-integrated-20261106.log，0失败／错误／跳过。实际效果indeterminate、请求intent不投递、recovery_required及重开保持的原断言未改。该修订尚无新安装包验证，查询争用／错误注入负例及关联运行时恢复组合仍需补验；不升级当前安装候选证据。未调用外部模型。

## 2026-11-06：不确定效果恢复新包组合

新增test_live_effect_inspection：注入TimeoutError及OSError，证明效果预检查不可用时原认证返回保留，由原子完成检查决定；源码通过2.480秒，/tmp/sdk-live-effect-inspection-fixed-20261106.log。首轮夹具漏correlation_id，原失败日志保留。

新完整冻结／独立安装候选`/tmp/sdk-live-effect-recovery-candidate-20261106`；纠正测试另存`/tmp/sdk-live-effect-recovery-tests-20261106`，不改冻结source。当前组合12项、11通过／1错误／0跳过，62.305秒，result.json及check.log，149产品Python文件与该冻结source直接字节一致。查询失败用例、control_reopen完整2项及原入口截止8项通过。technical_retries.test_original_deadline_expiry_after_abort_blocks_retry仍Orchestrator caller deadline elapsed，未关闭；当前没有后台测试。该新候选其余范围未复验，不继承旧候选为完整通过。

## 2026-11-06：managed入口前到期最小复现

最新技术重试现场`/tmp/sdk-prelaunch-deadline-failure-ritvg4fa/evidence.json`：adapter_calls=0、boundary_reached=false、无runtime effect或native operation，执行仍running；pending为timeout/entry_authority的late_thread_fact，预算started_at=None。故原测试未覆盖post-abort，不能改期待或加时来标通过。

独立实际SQLite managed Kernel探针`/tmp/sdk-managed-preentry-expiry-probe-20261106.py`／.json／.log：保留原0.1秒预算，仅在_prepare_handler_admission返回后延迟0.2秒，使调用确定落在executor.submit之前的admission-expired分支；结果running，business_calls=[]，pending_kind=late_thread_fact。未修改任何SDK表，临时库由公开Kernel建立与关闭。此为产品缺陷的更小执行证据，不是验收通过。

独立审查与代码核对：早期admission-expired及started.wait截止出口直接返回超时，run_once的fact_only路径保留晚事实却无活跃monitor决策；已有monitor_published_outcome只覆盖已发布worker outcome。需要在活跃权限下分开处理确定未提交与已提交可能仍活跃worker，复用原Kernel _complete_monitor_timeout、原预算与准确lease/precommit检查；不允许由late_thread_fact回放取得权限。该修复尚未实施；技术重试原现场无法仅从持久字段区分两个入口分支，不虚称本探针已证明原现场准确分支。当前无后台测试或模型调用。

## 2026-11-06：入口前到期修订及证据更正

更正上节探针结论：原探针只有相对timeout_seconds，没有绝对deadline；延迟_prepare_handler_admission并不能证明executor未提交。其running／零业务调用是真实结果，但“确定未提交”推断无效。重跑同脚本也覆盖了原同名JSON，原首次.log仍保留；不将该JSON当首次现场。新增test_managed_unsubmitted_timeout使用冻结deadline_at与executor.submit禁止断言，真实证明提交前到期及停止撤权。

产品源码新增提交前活跃monitor超时决策，使用原预算、精确lease、lifecycle／delivery guard及Kernel precommit权限检查；未确认提交仍未知。启动等待及确认入口到期出口使用既有revoke_for_monitor，分别处理published／pending／stopped／revoked，不从晚事实授权。独立审查先发现pending／stopped漏分支，再发现成功取消Future未保留；均已修正，transfer_late正常及中断补登记保留原Future。对应取消+竞争专门测试尚待补齐，不宣称其竞态完整通过。

首轮新增测试错误地使用相对截止，executor禁止断言实际触发；/tmp/sdk-managed-unsubmitted-tests-20261106.log保留。改绝对截止两项通过4.095秒。随后整合7项6通过／1错误，技术重试仍Agent wait超时，/tmp/sdk-managed-entry-timeout-integrated-20261106.log。最终源码10项通过9.879秒，/tmp/sdk-managed-entry-final-source-20261106.log（提交前两项+原入口竞争4项+截止4项），0失败／错误／跳过。当前修订尚无安装包验证；技术重试仍未解决，其他入口前准备失败出口需继续核对，无模型调用或后台测试。

## 2026-11-06：准备阶段到期与取消移交补充证据

准备阶段提前返回的timeout现复用提交前活跃超时决策；仅在线程尚未提交、原冻结预算可信且耗尽时，经原lease及撤权检查处理。源码组合11项通过、0失败／错误／跳过，10.411秒，`/tmp/sdk-preparation-timeout-source-20261106.log`。原技术重试单项在原期限不变情况下实际进入adapter、确认prelaunch abort，随后验证截止后不重试；1项通过3.398秒，`/tmp/sdk-retry-after-preparation-fix-20261106.log`。取消回调先于移交的专门测试1项通过2.728秒，`/tmp/sdk-managed-entry-cancel-handoff.log`，检查原Future所有权及重复清理，无handler或业务结果。

以上为源码定向证据，尚未统一安装包复验或完成回归，不推算总体剩余失败数、不升级G18。无外部模型调用。


## 2026-11-06：剩余child失败重新复现

当前源码原两模块6项，3通过／3失败，47.109秒，`/tmp/sdk-child-current-followup-20261106.log`。并发用例及两项父完成恢复仍失败；取消用例本次通过，不据此证明间歇问题已关闭。只读检查保留库确认子结果成功，父结果分别为completion_time_unknown（writer busy及floor_above_ack）。现有legacy恢复拒绝提升这些事实的权限检查保留。并发独立线程探测没有证明死锁／锁泄漏：另一次两个child均成功，parent仍等待，尚需定位交付登记。

新增提交前超时helper独立只读审查无具体阻断，范围限两个提交前调用点；缺并发取消／reclaim、stale lease、未知时钟及lease expiry专项覆盖。没有将其当全局授权证明。当前完整G18仍未通过，无外部模型。


## 2026-11-06：线程返回采样修订及分离的安装包结果

修订非托管thread成功返回调用点，使用现有serialized完成采样及entered原工作截止：先经写者栅栏，再记录本次返回完成事实；不授予legacy恢复新权限。独立只读审查未发现预算续期或结果权限阻断；明确采样可能晚于业务返回、争用可消耗原窗口，未证明停止立即中断或所有竞态。

修改前同两模块6项3失败；修订后原两模块6项全通过、0跳过，39.209秒，`/tmp/sdk-child-serialized-return-20261106.log`。取消、预留到期和原child只调用一次检查保留。尚缺该修订安装包及新负例，不能宣称全部关闭。

此前冻结的`/tmp/sdk-entry-preparation-candidate-20261106`不含本修订，其包外16项14通过／2失败／0跳过、57.208秒：技术重试未到达adapter边界，以及入口控制锁释放后仍running。`/tmp/sdk-entry-preparation-tests-20261106/result.json`及check.log。该driver未执行产品逐文件比较；result误继承的product_files_compared计数已纠正为false，product_source_files仅表示冻结源文件数，不是比较证据。原失败保留，不以源码单次通过覆盖。


## 2026-11-06：线程返回修复当前安装包结果

冻结当前产品并独立安装`/tmp/sdk-thread-return-candidate-20261106`，包外快照`/tmp/sdk-thread-return-tests-20261106`。26项25通过／1错误／0跳过，117.857秒，result.json及check.log：原child并发与storage contention两个整模块6项、legacy恢复权限负例4项、入口竞争及新增提交前超时等通过。唯一错误为原technical_retries截止后abort单项AgentRun.wait抛Orchestrator caller deadline elapsed；实际abort确认比原截止晚约6.6毫秒，不能宣称达到“截止前确认abort再耗尽”的正例。源码单次通过不覆盖此失败。

新tests/test_thread_return_fence.py源码2项通过7.583秒；同一安装包另行包外2项通过7.480秒，fence.log。真实SQLite写锁持有至原工作截止后不产成功；取消原generation后不被迟到回调覆盖。取消发生在真实采样返回unknown后、回调完成前，未覆盖所有并发取消／reclaim／停止窗口。测试监听包装仅记录和门闩，不替换采样／结果授权。两次执行分别报告，不合并成一次28项。

本候选不新增逐文件／hash检查，product_source_files只表示冻结源码数量，product_files_compared=false。所有测试进程已退出，没有后台回归、外部模型调用、CI或发布。G18及G01–G18仍未全部验收；下一步处理原技术重试窗口及尚未关闭的失败，不能以局部25项代替完整验收。


## 2026-11-06：技术重试失败分支调查及撤回实验

只读审查确认旧失败的原attempt/fence=1/1仍running、runtime效果indeterminate、精确not_launched记录及late_thread_fact存在；后者不能授权完成。未从事后记录推断具体monitor丢失权限分支。本轮曾试将根任务到期接入runtime.cancel，审查指出原始墙钟不足以证明可信预算到期且cancel可能覆盖及时结果，已完整撤回该修改。实验组合`/tmp/sdk-root-expiry-revoke-20261106.log`8项7通过／1加载错误，21.247秒；不作为当前产品证据。

仅记录既有函数返回的profiling探测未改变原2秒预算及30秒wait：原单项通过3.403秒，`/tmp/sdk-retry-monitor-branch-20261106.log`及.json，记录_complete_monitor_timeout后revoke_for_monitor=revoked。实际确认abort尚余约73毫秒。只证明本次成功分支，不覆盖既有安装包间歇失败，不能记问题关闭。无外部模型调用。

本轮加载错误为test_agents_absolute_deadline顶层导入test_agents_coordination_limits；改为tests包内准确路径，断言及产品不变，原模块复验另记。


## 2026-11-06：绝对截止夹具与剩余核心模块安装包复验

本轮没有保留新的产品修改。技术重试探测只证明单次成功，原间歇失败仍待修复；拒绝用原始墙钟把根任务强制cancel替代monitor权限。撤回实验及原失败证据继续保留。

修正测试：test_agents_absolute_deadline改准确tests包导入；旧命令拒绝重开夹具不启动真实后台host，避免手工queued命令被提前执行。关闭后用真实Kernel验证准确原command仍queued且无result，再要求两次拒绝重开，未放松接受条件。独立只读分析指出原夹具后台竞争，未证明产品preflight绕过。test_execution_kernel_v3_managed_gate补齐v14→v19的已有升级链；test_copied_legacy_terminal_readback复制升级目标引用当前KERNEL_STORAGE_SCHEMA_VERSION，并验证目标未产生历史copied-legacy witness。首轮误用不存在的常量名造成加载错误，日志/sdk-remaining-core-fixtures-fixed-20261106.log保留，已纠正。

四个完整模块源码33项通过27.829秒，`/tmp/sdk-remaining-core-and-deadline-fixed-20261106.log`。同一最新产品包`/tmp/sdk-thread-return-candidate-20261106`配合新的包外测试快照`/tmp/sdk-core-deadline-fixtures-installed-20261106`复验：33项全通过、0失败／错误／跳过，30.877秒，result.json及check.log。范围包括原application_budget、managed_gate及copied_legacy_terminal_readback失败，不升级其他旧模块／全部G18。未重建产品、未改旧冻结测试、未调用模型、未运行CI或完整回归；所有本轮测试进程已退出。


## 2026-11-06：effect 返回锁竞争恢复

原两秒预算真实定向复现由 running 修复为 recovery_required，同时保留工作线程及迟到结果责任；源码相关9项通过15.177秒，/tmp/sdk-monitor-effect-related-20261106.log。新恢复路径只停放未完成 effect，不制造结果，不延长预算。原技术重试单项本次通过，但尚不能将原间歇失败关闭；需当前安装包证据及其余原失败复验。详细审查、失败基线及控制时限修复见验收记录同名章节。

同一新安装包定向13项全通过（18.585秒），但技术重试整模块16项15通过/1失败（102.358秒），证据 /tmp/sdk-monitor-effect-installed-20261106/technical-result.json。失败是 abort 返回晚于原截止约57毫秒的正例前提断言；本次实际 wait 已返回 AgentExecutionError，Kernel recovery_required、adapter 只执行一次。保留原两秒预算和失败，不把与先前 wait 超时不同的现场表述为全部收敛。原证据 /tmp/sdk-prelaunch-deadline-failure-7vj3pxh_/evidence.json。

## 2026-11-06：原7个加载错误当前安装包闭合

当前产品 /tmp/sdk-monitor-effect-candidate-20261106；独立包外测试与冻结scripts闭包 /tmp/sdk-script-closure-installed-20261106。原7个无法加载模块完整62项全通过、0错误/失败/跳过，17.734秒。result.json/check.log保留site-packages导入及用例名，不使用产品src的PYTHONPATH。只关闭该组加载/本地谓词验证，不替代真实OpenCode或G18完整回归。两秒技术重试前提失败仍未关闭；本轮无外部模型调用、CI或发布。

## 2026-11-06：旧API三模块完整复验

/tmp/sdk-legacy-core-installed-20261106/result.json/check.log：66项65通过/1失败，96.971秒，0错误/跳过。application12项及v2_sqlite23项全部通过；v2_runtime31项30通过/1失败，不能关闭整模块。失败原现场 /tmp/sdk-process-group-timeout-oy4539rk/evidence.json：处理器入口拒绝，持久预算仍pending且无execution cutoff，原始完成采样失败；不能仅靠cleanup确认或历史错误详情授权timeout。原20毫秒预算、timed_out断言及失败保留。后续需安全的活跃入口拒绝决策，不授予未知事实结果权限。

## 2026-11-06：入口预算原子发布安装包验证

冻结候选 `/tmp/sdk-entry-atomic-reviewed-candidate-20261106` 独立安装后，包外测试 `/tmp/sdk-entry-atomic-installed-20261106/result.json`、check.log：72项71通过、1失败、0错误/跳过，84.233秒。入口原子发布7项、序列化采样/所有权及入口竞争相关34项通过；完整v2_runtime仍30/31，不能标G18通过。新代码使原入口截止与采样回执同事务持久化，入口仍pending；补交保留原租约和操作类型。独立审查未发现放宽预算，但同来源Run约束收紧时finish_pending精确比较会保守拒绝，恢复可用性尚待处理。

此前catch-timeout用例本次通过，但另一原20毫秒用例 `test_posix_timeout_kills_late_execution` 返回running：`/tmp/sdk-posix-late-timeout-bzjfd6ii/evidence.json`。没有on_entered，有独立树清理确认；原生outcome为execution_deadline_exhausted，completion_time_known=false，InspectionBudgetExceeded，入口预算采样出现Kernel control admission budget elapsed。不得用清理后的时间伪造完成时间，不能因原失败本次通过就关闭整个间歇故障。下一步必须处理准确未入场的活跃拒绝决策与未决采样权限，不能放宽20毫秒或直接相信outcome中的native_budget_cutoff。没有外部模型调用、完整回归、CI或发布；本测试进程已退出1。

## 2026-11-06：活跃入口拒绝超时收尾当前安装包通过

当前候选 `/tmp/sdk-preentry-monitor-candidate-20261106` 独立安装；包外快照 `/tmp/sdk-preentry-monitor-installed-20261106/result.json`、check.log：91项全部通过，0失败/错误/跳过，90.134秒。其中完整 `test_execution_kernel_v2_runtime` 31/31，原两个20毫秒用例均保留原期限/断言；另外包含入口原子发布8项、新收尾权限矩阵10项及既有采样/所有权/入口竞争/monitor效果权限负例。当前通过支持该模块原失败已在此包收敛，不证明全回归或所有调度下永不复发。

新收尾只由本次POSIX监督器在首个入口包为worker_completed并完成树清理后发出私有活跃观察；缺少on_entered本身不提供权限。Runtime持有生命周期和投递守卫，共用原0.1秒控制窗。Kernel同事务验证原始持久execution截止、准确pending attempt/fence/lease、全部未决采样为空、可信时钟、无effect及未解决准确监督义务，提交前复核；结果时间为本次串行拒绝决定而非未知handler完成时间。结果和监督义务原子提交；已耗尽原execution预算不重新排队，停机/撤权/不确定时保留原未知路径。首次审查发现重试及全局时钟问题均已修正；进度处理中途清除和分段锁时限问题也已修正。SQL主体及提交前查询有中断和清理，物理COMMIT/rollback延迟不由SQLite进度回调保证。独立最终审查在该范围无明确阻塞。

源码两个原用例先通过， `/tmp/sdk-preentry-monitor-original-20261106.log`，四个保留子现场明确记录live_preentry_refusal，未宣称这些入口前拒绝现场实际调用过handler。新增SQLite矩阵含原始期限未到/入口已确认/过期fence/取消/effect/本执行及无关执行未决采样/提交前撤权和实际递归SQL中断回滚。Run收紧后恢复确认可保留同来源更严格约束，不能丢弃调用者私加或更紧约束；入口发布8项验证。技术重试完整模块另行验证，不以该91项覆盖。没有外部模型调用、CI、推送或发布；G01–G18保持未全部验收。

同包技术重试完整模块已结束退出1：`/tmp/sdk-preentry-monitor-installed-20261106/technical-result.json`、technical.log，16项12通过/4错误/0失败/跳过，228.047秒。原两秒post-abort用例通过，abort在原截止前约0.236秒；四个错误为supervised_retry_does_not_execute_after_observer_start_raises、supervised_retry_joins_original_before_new_observer、supervised_retry_rejects_unconfirmed_observer_join及unentered_observer_start_retains_exact_owner_and_blocks_adapter的原等待超时。不能以原两秒单项通过关闭整个技术重试或回归。独立只读核对前三个现场均未证明共同根因，不能断言最新修订导致或仅主机慢；其中第三个现场adapter/目标observer分支未触达，保留post-close库有无匹配ACK的未决child采样，不能据清理后状态重建活跃权限。现场分别 `/tmp/sdk-retry-matrix-wait-timeout-ov4e569l`、`u2xcb5ht`、`eig2f38w`（后两完整目录使用相同前缀）。

未立即重跑整组。测试诊断补充：两个原自动删除目录改为仅失败保留、成功清理；等待异常记录state_dir及有界采样owner状态，忙锁明确busy，不改预算/断言/采样或结果。编译及独立注入异常验证保留原异常和失败目录、成功目录清理通过；尚未执行下一次业务复现，不能当修复证据。

同一当前安装包12项入口收尾权限矩阵补验全部通过、0跳过，7.101秒：`/tmp/sdk-preentry-monitor-guards-supplement-20261106/result.json`、check.log。增加时钟连续性未知拒绝与提交前原租约到期回滚，两者均不提交结果/监督义务；不与此前91项合并为一次103项。当前没有本轮仍运行的回归，G18/整体目标保持未完成。

## 2026-11-06：监督子执行入口采样自阻塞定位与修复

原失败单项保留现场复现：`/tmp/sdk-supervised-retry-retained-20261106.log`，原30秒wait未改，41.342秒后退出1。现场 `/tmp/sdk-retry-matrix-wait-timeout-esw3c1_s` 记录准确活跃owner、captured=true、原entry_lease及BudgetClockUnknownError；状态库 `/tmp/sdk-supervised-retry-state-4e49puyf` 保留。确认控制流缺陷：入口ACK中的_assert_child_claim在删除本次准确采样标记之前调用_assert_budget_clock(child)，把自身sampling标记作为阻塞。修复将该检查移至同一事务内准确receipt/marker操作之后；父撤权、祖先/其他采样检查保留，失败整体回滚，不以删除标记跳过权限。原失败单项源码通过9.033秒，`/tmp/sdk-child-entry-own-marker-fixed-20261106.log`。

新增父子SQLite验证也发现原入口前child envelope带继承父started_at，补交ACK后会被入口结果检查拒绝。现在同一活跃owner保留不可变原入口输入，并在ACK后允许该准确继承开始时间；返回仍为实际child started_at，同来源约束只能保持或更严，不接受无关开始时间。完整入口发布模块11项源码通过，2.487秒，包括父取消回滚、祖先未决采样回滚、祖先ACK后用原child输入补交及重复读取仅一条receipt。两处修改独立审查未发现明确阻塞；不是全部目标或间歇故障最终验收。新冻结候选 `/tmp/sdk-child-entry-marker-candidate-20261106` 安装包组合验证另报，原失败包和日志不改写。无外部模型、CI或发布。

范围核对：Goal第94行及G13明确允许未声明真实strict后端时，仅验收能力合同和业务前拒绝；报告必须注明原生强隔离未提供/真实隔离未验收。因此缺真实strict后端本身不构成额外必做后端开发，不扩大已确认范围。当前安装包仍需有效的相应合同/拒绝证据。

## 2026-11-06：子入口自阻塞修复当前安装包结果

新冻结独立安装候选 `/tmp/sdk-child-entry-marker-candidate-20261106`，包外快照 `/tmp/sdk-child-entry-marker-installed-20261106/result.json`、check.log：112项111通过/1失败/0错误/跳过，196.433秒。技术重试完整模块15/16：此前四个监督器重试等待超时均通过；完整进程运行模块31/31，入口原子发布11项、入口拒绝权限12项及既有采样/所有权/入口争用/效果权限等组通过。不把不同候选证据合并，不声明完整G12/G18通过。

唯一失败仍是原两秒 `test_original_deadline_expiry_after_abort_blocks_retry`，但不是原30秒wait超时：AgentExecutionError已返回，Kernel准确execution recovery_required，runtime effect indeterminate，adapter_calls=1、native_operations=[]。适配器实际进入时余约6.235毫秒，prepare进入时余2.805毫秒，准备17.159毫秒后到期，未到测试要求的abort边界（boundary_reached=false）。现场 `/tmp/sdk-prelaunch-deadline-failure-34ravwdq/evidence.json`，原状态目录 `/tmp/sdk-prelaunch-deadline-state-7qnnk7kd`。当前现场不能证明post-abort正例，也不能误报adapter完全未进入；未增加两秒预算或重跑刷绿。四个监督器错误在当前完整模块对应复验已收敛，但该模块整体验收仍未通过。

原子发布对子执行自有采样标记的检查顺序及继承开始时间恢复已由独立审查确认限定正确；此次安装包覆盖新增父取消/祖先未决/原输入恢复与无关开始时间拒绝。所有本轮测试已退出，没有后台回归/外部模型调用/CI/发布。
