## 2026-11-16 G18 原生验收范围调整

用户更正交付平台为 Linux x86_64。当前候选 wheel 在该平台以 Python 3.12.3 通过真实 G02，退出码为 0，提交文本产物并确认进程清理。GitHub CI 的 Linux x86_64 回归与本次本机 OpenCode 验收分别记录。完整安装包回归仍待完成。

## 2026-11-15 G18 原生入口与安装包证据

Linux x64 的 Python 3.10–3.13 已完成针对配置、会话、权限、原期限及入口竞态的定向回归。独立安装包的 Kernel 和 Orchestrator 外部消费者重启、可观测性及卡滞监督示例通过。证据见 `/tmp/sdk-080-g18-entry.yqdWYt/current-candidate-acceptance.json`。

G02 在 Linux 保留原文件产物场景，Windows 改用受支持的文本产物，仍要求实际 OpenCode 模型调用、SDK 成功结果、产物及准确的原生清理回执。该改动只涉及验证器，Windows 上的 SDK 文件工具仍按现有合同拒绝。Linux ARM64、Windows x64 和 Windows ARM64 仍需在已授权的真实主机上运行。完整安装包回归含直接写入新建测试 SQLite 内部表的夹具，等待确认是否允许原样运行。主机与解释器要求见 `/tmp/sdk-080-g18-entry.yqdWYt/G18-platform-handoff.md`。

## 2026-11-15 修复包证据复审

当前逐项索引位于 `/tmp/sdk-080-g18-entry.yqdWYt/current-candidate-acceptance.json`。G01、G02、G04、G11、G13 链接到本轮安装包的直接报告；G03、G05–G10、G12、G14–G17 记录上一包原始报告、唯一产品变更涉及的入口检查以及当前补证的适用范围。索引保留旧包通过的状态，分别记录本包实际执行，避免把旧场景算作新包重跑。独立审查未发现入口变更的具体缺陷，指出逐项复用依据、制品与文档一致性及平台矩阵仍须核对。公开指南与中英文 Wiki 中过时的 G17 状态已按候选证据修正。

## 2026-11-15 G18 入口采样拒绝复现与修复

受控场景保留 30 秒启动窗口和真实 SQLite 采样、持久回执与控制锁。干净锁拒绝的对照组可继续；上一份已保留的采样恰由维护逻辑确认后，新一轮在控制锁准入前干净拒绝，旧包在剩余约 29.75 秒时提前退出。原 G11 短时拒绝符合该现象，原事故的进程内采样顺序未保留。新包验证准确回执、拒绝证明、租约与原期限，继续使用同一采样，未重新采样。

修复包 `/tmp/sdk-080-g18-entry.yqdWYt` 的 151 个产品文件与工作区内容相同，相对上一包只改 `execution_kernel/context.py`。相关安装包测试首批 40 项中 39 项通过，另 1 项报告继承期限到期及未决清理。旧包单项复现相同错误。旧夹具等待入口返回才让祖先提交采样，而入口现在会在原期限内重试；修正夹具，在已核对真实回滚之后释放祖先，测试通过，原期限及回执身份断言保留。原日志和独立复核后的单项结果见 `/tmp/sdk-080-g18-entry.yqdWYt/G18-affected-entry-regression.json`。

同包真实 G11 通过，103.39 秒，原配置与新配置各一次实际入口，监督退出 0、清理确认、零兜底信号。本轮普通原生 G11 的入口没有触发所修竞态；受控故障和真实 G11 的证据各自保留。源码包重建后在独立环境安装，151 个文件与 wheel 安装内容相同，25 页 Wiki 已本地导出。重建源码包的第一条 wheel 命令尝试写入只读 pip 缓存，改为禁用缓存后成功。未触发远程 CI 或发布。

同包 G04 图调度和受控重投分别用时 159.59 秒和 154.88 秒。输入未齐时无消费者，齐备后消费一次。实际宿主在原租约到期后以新租约和更高 generation 重领并确认同一事件，沿用原产物。重投驱动首次把 `controlled_redelivery_passed` 当成失败，漏启动图场景，保留首份结果后仅补跑图。图验证器本身仍以 1 退出，因为单跑图不验重投。结合两份原始报告和监督清理回执，八项条件全部成立，见 `/tmp/sdk-080-g18-entry.yqdWYt/G04-combined.json`。

另用真实 G02 OpenCode 入口注入同一采样竞态。原采样获确认后，新的真实 SQLite 控制锁拒绝发生时仍在原启动窗口。SDK 继续执行，原租约、attempt、fence 和模型期限一致，返回 DONE 并提交产物，原生操作和进程树清理均确认。身份审计见 `/tmp/sdk-080-g18-entry.yqdWYt/G18-native-entry-audit.json`。现有结果验证故障路径可恢复，历史 G11 现场的确切交错顺序仍无法还原。

## 2026-11-15 G17 通过，当前安装包 17/18

只补旧命令投递、结果交付、通知及便捷 API 模块，40 项通过，0 跳过，53.11 秒。同包旧 API 8 个模块共 107 项通过。合并已通过的实际 CLI 14 条命令、6 个类型消费者、原生监督 4 场、资源准入正反例，G17 验收通过。逐项原证据见 `/tmp/sdk-080-g04.UAOzl4/G17-consolidated-evidence.json`。G18 仍需发布级回归、Python／原生平台矩阵及独立审查。G11 历史入口拒绝后留在 running 的可靠性问题保持开放。

## 2026-11-15 G17 原生监督、资源准入和旧 Orchestrator 补验

当前包实际 OpenCode 监督 stable、stale、disabled、stop 全部通过，139.51 秒。真实 128 MiB 容量限制与关闭限制对照均通过，104.53 秒。96 MiB 父级存活且占用时，64 MiB 子级无 runtime effect 或原生操作，父级释放后才实际准入；关闭限制时父子重叠。两组进程树清理确认、零兜底信号。Orchestrator 和 OrchestratorHost 旧 API 24 项通过、零跳过，20.98 秒。外层汇总错误地要求监督器传递资源验证器设计上的退出码 1，导致批次退出 1；原执行证据中资源验证器 root_exit=1、监督器退出 0，两资源场景均通过。保留原汇总并用 `/tmp/sdk-080-g04.UAOzl4/G17-consolidated-evidence.json` 逐项更正，无重复模型调用。其余旧 API 投递、结果、通知和便捷入口单列。

## 2026-11-15 G16 停止、撤权和清理未知通过

同一独立安装包仅补宿主竞争、撤权和清理回执缺失三场，共 232.76 秒，分别通过 5、14、10 项。实际第二宿主无法取得已占用状态目录，原 lease 与操作身份保持；停止状态及请求重放在重开后保持。发送后撤权准确取消原执行，排队请求未启动，无关角色完成，恢复权限只允许未来请求。真实守卫完成进程树清理后扣留回执，原操作仍为 authorized，原效果保持 indeterminate，同键继任者跨两次重开仍未调度，异键会话完成。三组外层监督退出 0、进程树清理确认、零兜底信号。该竞争场景验证宿主锁排他；清理缺回执场景验证 SDK 对未知的保守处理。汇总和原报告见 `/tmp/sdk-080-g04.UAOzl4/G16-combined.json`。当前完整通过 G01–G16。

## 2026-11-15 G14 四个真实故障窗口和 G12 通过

沿用同一独立安装包窗口 A 的报告，只补窗口 B、C、D，共 239.14 秒，分别通过 9、16、13 项。窗口 B 在意图持久化后、SDK 接受前退出，重开沿用原 Run 与期限，只执行一次 producer。窗口 C 的原模型请求实际发送一次，重开后同 ID 保留 unknown 和会话隔离，无原请求或排队请求再次发送，异键会话完成。窗口 D 重投实际消费事件，沿用原后继及产物，确认 ACK，producer 未再次执行。四份原始报告及外层监督汇总见 `/tmp/sdk-080-g04.UAOzl4/G14-combined.json`。四次均退出 0、进程树清理确认、零兜底信号。

G12 从当前 G05、G08、G09、G15 和已通过的技术重试报告核对返工、业务阻塞、验证器错误以及发送后未知状态，见 `/tmp/sdk-080-g04.UAOzl4/G12-combined-current.json`。只补了默认并发下原 2 秒期限场景，耗时 3.48 秒，零跳过。期限前约 222 毫秒确认未启动，原适配器仅一次调用，期限到后原执行和效果进入 recovery_required / indeterminate，未重试。该用例未断言宿主清理，历史迟到确认保留，单次通过不推断时延保证。原日志和时序见 `/tmp/sdk-080-g04.UAOzl4/G12-default-short`。G12 通过，当前完整通过 15/18。

## 2026-11-15 G11 原生完成，G17/G18 定向补验

同一安装包只运行 G11 原场景，116.98 秒通过。旧执行保留旧 prompt 与配置，新执行读取新配置；知识版本 1 与 2 实际读取，未授权写入拒绝、过期版本冲突且未覆盖，两个产物和原生清理回执核对一致。入口跟踪保留原 30 秒启动和 240 秒工作预算。两次入口采样分别用 0.026 和 0.051 秒，入口采样本身未遇到控制锁拒绝；全轮其他阶段共记录 71 次。原失败和离线复现不撤销，G18 仍有可靠性缺口。

同包实际 CLI 14 命令、6 个类型消费文件通过。Python 3.10.21 Linux x64 使用从缓存镜像提取的独立解释器和本机库环境，原 wheel 的 G01/G13 加 22 项定向回归通过。Docker 原缓存快照失败日志仍保留。当前完整通过 G01–G11、G13、G15，共 13/18，证据见当前候选索引。

## 2026-11-15 G15 完整通过

只补额度耗尽 15 项（34.16 秒）和父子取消 12 项（72.88 秒），同一安装包，两组监督退出 0、清理确认、零兜底信号。与既有真实子调用、原会话 goal、队列到期、宿主重启和技术重试记账合并，见 `/tmp/sdk-080-g04.UAOzl4/G15-combined.json`。当前完整通过 G01–G10、G13、G15，共 12/18。

## 2026-11-15 当前包 G11 结算定位、G12 技术重试与 G15 队列到期

G11 原现场未进业务，入口拒绝被记录为待处理 `late_thread_fact`，业务返回时间校验结果为 `completion_clock_original_floor_unproven`。SDK 的恢复入口对该记录仅能报告 unknown。相同安装包的真实锁夹具复现未执行 handler 却保留 running，夹具使用 1.5 秒启动窗口，协调器报告与原现场不同。两份证据和限制见 `/tmp/sdk-080-g04.UAOzl4/G11-G12-gap-audit.json`，G11 仍失败。

G12 技术重试 12 项、非重试 EINVAL 11 项通过。完成真实暂态重试、EMFILE 耗尽和确定未启动的 EINVAL。只补 EINVAL 时在本地回环环境运行，无进程或模型启动，同 ID 不再执行，宿主完成关闭。保留受限沙箱初次探针的回执和退出错误。G12 仍有默认并发短窗口回归缺口。

G15 同包队列到期 6 项通过，保持原 120 秒截止，无排队项 SDK 或模型入口，异键真实成功，重开后的重放保留原到期状态。外层监督退出 0，清理确认。记录见同候选 `G15-queue-expiry/report.json`。当前完整验收 11/18。没有触发 CI。

## 2026-11-15 G10 通过，G11 新配置执行在入口失败

同一安装包 G10/G11 总计 263.58 秒。G10 22 项全部通过，包括真实独立客户端退出、三个 SDK Run、同会话续接、真实宿主重启、队列恢复、跨 Run 精确取消和原预算核对。G11 外层等待 150 秒超时。只读复核定位到新版本请求已被 Kernel 领取，worker_dispatch 后在 HandlerContext._capture_entry_budget → _sample_budget → _control_lock 抛出 _ControlAdmissionTimeout，无 handler_entered、无原生操作。进程结束后数据库仍记录该 execution running。旧版本已进入 wrapper gate，失败退出时效果为 indeterminate，也无真实原生操作。外层监督确认进程树清理、无兜底信号。未重跑 G11，未放宽原窗口。

原始报告在 `/tmp/sdk-080-g04.UAOzl4/G10-G11-native/acceptance.json`，入口轨迹在同候选的 `G11-entry-failure-audit.json`。当前 G01–G10、G13 共 11/18。G11 与旧的已发布采样 ACK 竞态不同，本次应先核对入口控制锁拒绝及后续结算归类。G12/G15 复用当前 G04–G10 已有场景，另补真实技术重试、原预算耗尽、队列到期和父子取消缺口。无产品改动或 CI。

## 2026-11-15 G07/G08 当前包真实验证通过

同一 Linux x86_64 / Python 3.12 独立 wheel，实际 OpenCode 两项共 311.33 秒。监督器和验证器退出 0，确认进程树清理、零兜底信号。原报告 `/tmp/sdk-080-g04.UAOzl4/G07-G08-native/acceptance.json`，同目录逐项证据保留。

- G07 实际 call-and-wait、send/wait、相同请求重放、权限拒绝、自等待环拒绝及 planner 实际消费双产物通过。3 次 Agent 调用、16 模型轮次；核对三个原生清理、committed effect、succeeded execution 和 released 资源见 `G07-terminal.json`。首次只读审计错用 G04 的四操作计数，修正为 G07 的三个，保留原审计脚本。
- G08 目标验证继续原会话，从 DRAFT_NATIVE 到 GOAL_NATIVE_FIXED；显式阻塞和验证器异常未进入成功或下游调度。主路径 1 次调用/6 模型轮次，两负例各 1 次调用/4 轮；四项原生操作清理身份正确。

当前 G01–G08、G13 共 9/18 通过。G09–G12、G14–G18 待关闭。本轮没有产品改动、CI、推送或发布。

## 2026-11-14 G05/G06 当前安装包原生验收通过

同一独立 wheel 本机实际执行一次共用 G05/G06 主链，545.83 秒，7 次主链调用/43 模型轮次，1 次隔离 Run 调用/5 轮。原 3600 秒、16 次调用、128 轮预算不变。两轮各两名 coder 的真实 adapter 执行区间重叠，group close、聚合、返工、跨 Run 拒绝及精确回执齐全。原逻辑 reviewer 通过 lineage 续接，使用新 invocation/session 实际消费 NEEDS_FIX 和两份修正产物。全部八项原生操作清理有效。正式 G05 passed。原联合验证器 exit 1 是 G06 单图缺少两项负例，外层 supervisor 确认树已退出、无兜底信号。

仅追加 G06 的 ambiguous_reference、group_required_output 两个实模型负例，实际 195.41 秒，共 4 次 Agent 调用、17 模型轮次。歧义作用域内消费者无 command/execution/effect/adapter 入口，必需产物缺失在组关闭后准确拒绝汇总消费者准入。两个 worker 与外层 supervisor 均确认退出和清理。补充结果与主链比较为同安装路径、版本和内容；最终合并 G06 passed。gate 辅助重叠只证明执行区间并发，历史约 64 秒领取延迟单独保留。

当前证据位于 `/tmp/sdk-080-g04.UAOzl4/current-candidate-acceptance.json`、`/tmp/sdk-080-g04.UAOzl4/G05-G06-native`、`/tmp/sdk-080-g04.UAOzl4/G06-combined.json` 和 `/tmp/sdk-080-g06-negatives-20261114.final-report.json`。当前 G01–G06、G13 通过。G07–G12、G14–G18 待关闭，下一步补真实 call/send 与 goal 续接。无产品代码改动、无 CI、无推送或发布。

## 2026-11-14 恢复 Goal，当前安装包 G01–G04、G13 通过

磁盘普通可用空间恢复至 142 GiB，Goal 已由用户恢复为 active。Linux x86_64 / Python 3.12.3 独立安装 dispatcher-sdk 0.8.0.dev1 wheel，离线安装 PyYAML 6.0.3，151 个 SDK 文件与冻结源码逐一匹配。候选和现行验收索引为 `/tmp/sdk-080-g04.UAOzl4` 与同目录的 `current-candidate-acceptance.json`。此前候选的 /tmp 原始目录本次不可访问，仓库内的现存记录保留历史用途。

- **G04** 两个真实 OpenCode 1.18.32 场景分别用时 142.41 秒和 139.26 秒，均执行 4 次 Agent 调用，分别使用 16 和 19 模型轮次。原每图 240 秒、8 次调用、48 轮预算保留。确认输入未齐时无消费者，齐备后消费者仅一次且读取两个产物，同 ID 同内容返回原调用，修改内容拒绝。受控 ACK 前失败后，宿主等原租约到期，以新租约和更高 generation 实际重领同一事件，沿用原消费结果并确认 ACK，无重复执行。两批进程树清理均已确认，零兜底信号。独立只读复核覆盖两份原始报告；`audit_g04.py` 逐项核对并生成 `G04-combined.json`。外层首次错误地期待重投报告为 passed，漏启动第二场景；保留首次脚本和返回值，只补跑图场景。图验证器单独仍返回 1 / not_run，因为它没有重复事件场景；按同包两场景合并判定 G04。
- **G02** 复用重投场景四个 OpenCode 会话的实际完成响应和工具记录，并关联同一安装包、SDK 操作及已清理回执。**G03** 复用图场景实际写文件、拒绝越界和链接、下游消费结果。只补 71 次真实路径替换竞争（500 次尝试全部拒绝，外部文件不变）及只读的四个已结束操作、已提交效果和已释放资源核对；允许写入由原生图证明。证据为 `G02-reused-G04.json`、`G03-reused-G04.json`，零额外模型调用。
- **G01/G13** 对重建包运行原正式入口，配置/默认值及不支持 strict 时在业务前拒绝均通过。**G18** 已重建同源 sdist，内容核对见 `G18-artifact-content.json`；独立 sdist 安装、完整平台矩阵和最终审查仍待完成。第一次在运行环境调用 setuptools 构建失败，改用本机离线构建环境成功，日志均保留。

剩余 G05–G12、G14–G18。优先合并 G05/G06 当前包的真实返工与动态组证据；先核对可恢复的历史原始证据和代码影响，再补受影响或从未覆盖的场景。G02–G04 已有当前包证据，避免为其他项重跑这些模型路径。此次无产品代码修改，无 CI、推送或发布。

## 2026-11-07 外部容量阻塞复核

连续多轮普通可用空间不足，当前约161MiB；原生G04及后续运行证据仍不能安全启动。已确认的入口缺陷已修复并在当前独立安装包41项通过；已有离线部分证据保持原适用范围，不继续刷同项测试代替原生验收。准确外部阻塞审计 `/tmp/sdk-retained-ack-candidate-20261107/external-blocker-audit.json`。G01/G13当前通过，G02–G12、G14–G18尚未全部当前验收。最低恢复条件：额外至少1GiB可用空间，或用户明确指定允许清理的目录；保留源码、会话、DB、原始日志和回执，不扩大此前仅npm下载缓存的清理范围。G18还需原合同Linux ARM、Windows x64/ARM及Python矩阵的原生执行条件，未获授权的CI不触发。整体Goal未完成；将Goal记录为blocked，等待外部条件改变，禁止以重复部分测试制造持续推进。

## 2026-11-07 保留采样重试的准确ACK竞态修复及新安装包验证

当前候选改为 `/tmp/sdk-retained-ack-candidate-20261107`。原安装包在retained-ack-investigation/installed-before.log真实复现：第一次调用保留原采样，第二次重试失败交付间维护线程真实提交准确ACK，但pending检查顺序仍拒绝该回执。只注入第二次publication admission超时，不写内部表；只有一个实际采样。context.py把准确ACK检查置于保留pending不符检查之前，并额外要求先前retained token及原captured对象身份准确对应，其他拒绝和原期限不变。

扩展模块6测试/23场景9.495秒通过，包括真实kernel.cancel(lease)后拒绝和独立工作预算到期、启动窗口仍活跃时拒绝。初次工作预算夹具只配置command timeout，未投影到入口envelope而失败，source-reviewed.log保留；修正为显式本地预算约束，不改产品断言。独立审查未发现具体阻塞。新wheel独立安装后41项全部通过、0跳过、33.421秒，149产品Python文件与冻结源码一致；准确installed-regression.json。新sdist已带MANIFEST/贡献/安全文档，151产品路径/内容与wheel一致、144文档/示例/脚本匹配，G18-distribution-content.json。G01/G13在新安装包重新通过，G13只为不支持strict时拒绝合同。

新权威current-candidate-acceptance.json未继承旧产品的运行时证据为passed；旧候选43项旧API、27项资源监督、sdist安装及文档运行证据全部保留历史，后续按影响重验，不冒充当前运行时。G04尚无新原生证据，约163MiB磁盘不足，最小条件仍额外至少1GiB或用户指定清理目录。无模型、无CI、无远程发布，整体Goal未完成。

## 2026-11-07 当前安装包监督/资源四个完整模块回归通过

当前安装包完整运行tests.test_agents_supervision、test_agents_resource_admission、test_agents_resource_ownership、test_agents_resource_recovery：27项全部通过、0跳过，149.650秒，准确结果 `/tmp/sdk-entry-cutoff-candidate-20261107/G17-supervision-resources-current/result.json`，逐项tests.log与supervision-resources-outer.log保留。覆盖默认关闭允许重叠、父级清理前保留内存、角色准入、未知归属恢复和迟到清理等；使用测试运行时，没有真实OpenCode调用，不能替代G17要求的真实资源准入/监督证据。无产品修改、无内部表直接修改、无模型、无CI或发布。检查候选生成入口后确认之前文档遗漏来自临时冻结复制，而非仓库MANIFEST.in；未将无关release_candidate.py改作冻结工具。整体Goal保持未完成。

## 2026-11-07 G18文档运行与双语Wiki本地导出通过

首次文档检查发现冻结目录漏带CONTRIBUTING.md和SECURITY.md，6处链接无目标，原G18-docs-check.log保留。新增独立sdist-complete-source补齐两个仓库文档，重建sdist-complete分发包；原产品151文件与wheel精确相等，144个文档/示例/脚本精确相等。补全包在既有独立环境离线重新安装成功，G18-sdist-installed/result-complete.json证明实际导入及全部151安装文件相等、配置入口通过（此轮是原独立环境重新安装，不冒充第二个全新环境）。candidate.json已指向补全包。

文档检查G18-docs-complete.log：580个本地链接、默认值注册表以及4个README实际示例通过，0跳过。25页Wiki（包括中英文Agent-Control）已本地导出G18-wiki-preview，ref=release/0.8.0，仅本地预览，未声称远程分支或链接已发布；G18-docs-result.json记录。产品未改、无模型、无推送发布。G18仍缺完整原生平台及最终完整验收审查，不能关闭；G04磁盘条件仍未解除。

## 2026-11-07 修正版sdist独立离线安装通过

`/tmp/sdk-entry-cutoff-candidate-20261107/sdist-repaired/dispatcher-sdk-0.8.0.dev1.tar.gz` 已在全新Python3.12环境G18-sdist-installed/env实际安装，无system-site-packages继承。构建依赖setuptools84.0.0、wheel0.45.1、packaging26.3从本机现有HTTP缓存取现成wheel，PyYAML6.0.3复用已有wheel；pip显式no-index/no-deps/no-build-isolation/no-cache-dir，无网络和模型调用。安装日志G18-sdist-installed/install.log，依赖日志build-tools.log。包外-I导入来自新环境，全部151产品文件路径集合及内容与修正版源码精确相等，YAML/Python等价、有效默认值与CLI配置入口通过。准确结果G18-sdist-installed/result.json。candidate.json已记录sdist_installation_verified=true。G18仍缺完整原生平台、文档运行/导出和最终审查，不提升为完整通过。

## 2026-11-07 G18 源码分发包漏文档问题确认并修正

原冻结构建目录漏带仓库 MANIFEST.in，原sdist未包含docs/wiki/examples/scripts；首个缺失项docs/SDK_RECOVERY.md。原制品与失败证据G18-original-sdist-failure.json保留。独立sdist-repaired-source恢复打包输入后重建替代sdist，未改产品。全部151产品文件路径集合与字节均与原wheel及冻结产品一致（含py.typed、Kernel README），144个冻结文档/示例/脚本文件逐项与替代sdist一致，顶层构建配置及许可证亦一致；G18-distribution-content-repaired.json记录。使用直接内容比较，不新增hash检查。candidate.json当前sdist指向替代包，同时保留原包路径。替代包尚未独立安装，不宣称G18通过或新平台通过。当前磁盘约348MiB，真实G04未启动，本轮无模型调用。

## 2026-11-07 当前安装包旧 Dispatcher/V2 运行时完整模块通过

当前 `/tmp/sdk-entry-cutoff-candidate-20261107` 安装包完整运行 tests.test_application 与 tests.test_execution_kernel_v2_runtime：43项全部通过、0错误、0跳过，94.794秒。包括真实子进程、重试、取消、超时进程树清理与持久效果身份；不调用模型。准确结果 G17-legacy-runtime-corrected/result.json，逐项日志 tests.log，外层日志 legacy-runtime-corrected-outer.log。第一次驱动缺少main入口保护，spawn子进程重复初始化，43项中21失败；原驱动 verify-legacy-runtime-first.py 和 G17-legacy-runtime-current 原结果保留，不将该轮解释为SDK缺陷或删除。纠正后保持原模块范围与测试超时，未修改产品或测试断言。G17仍缺完整其余旧API、监督/资源准入验收，未关闭；G04磁盘条件未解除。

## 2026-11-07 当前安装包 G17 CLI 与公共 API 类型消费补验通过

当前候选 `/tmp/sdk-entry-cutoff-candidate-20261107` 的实际 CLI 生命周期通过：14条命令全部成功，stop/resume 状态对应，宿主退出码0，端点移除，无兜底清理。证据 `G17-cli-current/report.json`。六个公共 API 类型消费文件针对该安装环境检查通过（Python3.10类型目标，2.865秒），证据 `G17-types-current/result.json`。未调用外部模型、未变更产品、未重跑已通过39项。G17仍未完整通过；资源/监督及其余旧API回归仍需有效证据，不能将本次部分验证提升为整Gate通过。磁盘普通可用仍约504MiB，真实G04未启动，解除条件仍为额外至少1GiB可用空间或用户指定可清理目录。

## 2026-11-07 新候选安装包入口回归39项通过，G01/G13重新验收通过

新冻结候选 /tmp/sdk-entry-cutoff-candidate-20261107：同源 wheel/sdist 已构建；独立无pip环境安装 wheel 与已有 PyYAML 6.0.3 制品，无网络安装。实际导入新安装目录，149个产品Python文件与冻结源码逐字节相等（未新增hash检查）。安装包39项全部通过、0跳过、31.380秒，包含原 BUSY 截止超时/零业务及协调错误断言、ACK竞态、采样拒绝、线程和进程原子结算、5种错误凭据身份；结果 installed-regression.json，原日志 installed-regression.log。独立源代码审查未发现必须修复的问题，审查范围和排程覆盖限制仍保留。

当前安装包正式 G01 配置/YAML/Python/默认值/双语Wiki验收通过；G13不支持强隔离时拒绝准入、tools模式只保证SDK文件工具、无真实隔离宣称，通过并补5项能力测试。范围Linux x86_64/Python3.12。对应新候选 G01-current 和 G13-current 保留原始事实与报告。旧候选8/18证据全部保留，不转算新包；新包完整重验收目前仅G01/G13，其他Gate没有因这些局部回归自动通过。

真实G04尚未重新启动：磁盘约507 MiB，旧四Agent图清除npm内容缓存后仍占292 MiB，加原456988412字节缓存合计约750 MiB，不能在当前余量下可靠运行。需额外释放至少1 GiB或指定可清理目录；已向用户说明，继续其他不依赖模型的验收。另仅清理已确认监督terminal/tree_reaped且原PID不存在的四个原G10 npm _cacache（420195338字节），其余会话/数据库/原日志全部保留，记录旧候选 native-G10-foreground/terminal-cache-cleanup.json。本轮无外部模型调用、CI、推送或发布，Goal未完成。

当前权威索引 /tmp/sdk-entry-cutoff-candidate-20261107/current-candidate-acceptance.json。G17仍缺完整旧API/CLI/监督/资源回归，G18仍缺完整原生平台与最终审查，不能以39项通过或构建成功关闭。历史G04根因没有因此被证明。

## 2026-11-07 入口截止结算修复已接通，源代码关联验证通过

运行时只接收采样生产者绑定原异常/owner/kernel/连接/执行的准确拒绝凭据，结合原预算的可信本地截止、未确认入口及未撤销权限，生成仅在该运行时内有效的拒绝；结果发布时绑定准确归一化对象，不信任用户字段、不新增截止后的返回采样。监控持有原有一次100毫秒控制窗口；Kernel 在同一事务重新核对原 pending attempt/fence、完整预算、原执行截止、租约、全局未知采样及任何效果，提交前再次核对。线程模式不伪造原生 supervisor 清理凭据，也不能替换已有原生义务。

原入口竞争/ACK/采样凭据13项全部通过（9.227秒），包括此前失败的 BUSY 截止项，原超时/零业务调用/原协调确认错误断言未弱化。新增线程结算12项及原进程结算12项全部通过（10.162秒）；拒绝身份不符5种真实入口场景及生产者6项测试通过（7项测试，7.169秒）。准确日志与独立审查 /tmp/sdk-entry-ack-race-review/{preentry-integration-regression.log,thread-preentry-atomic-first.log,preentry-gating-regression.log,preentry-independent-review.md}。初次接入的失败日志全部保留；最终使用Kernel授权时间并保留协调线程原确认错误。独立审查未发现必须修复的问题，不声称覆盖全部线程排程。

本节为源代码证据，尚未代表新安装包通过，更未关闭G04/G17。没有外部模型调用、内部表直接修改、CI、推送或发布。为继续验证，只删除已证明 cleaned、监督 terminal/tree_reaped 且两PID均不存在的原G04 seed npm _cacache（114247103字节）；全部会话/数据库/原日志保留，准确记录 native-G04-redelivery/terminal-seed-cache-cleanup.json。

## 2026-11-07 采样启动前拒绝凭据已实现，运行时超时修复尚未完成

采样生产者复用事务已有 _begin_failure 证据，仅在事务及外围控制清理均完成、原异常对象一致、准确闲置连接/owner/kernel/execution 相符、没有待确认样本或隐藏异常时，为真实 SQLite BEGIN BUSY 附加私有内存凭据。该凭据尚未由运行时消费，不改变超时提交权限，不关闭原 BUSY 截止失败。

独立检查并补充两类负例：真实事务体内 BUSY 不获得启动前凭据；真实采样标记提交后观察失败保留原 token/owner 和未知样本，关闭必须准确报告 budget_clock_cleanup_pending，绝不删除标记或授权完成。首次11项运行因该故意未知场景的清理异常而失败，原日志保留 producer-primary-regression.log；夹具明确断言这一预期拒绝后，同范围11项全部通过、0跳过、6.399秒，/tmp/sdk-entry-ack-race-review/producer-primary-regression-final.log。范围为5项拒绝凭据测试、4项 ACK 竞态测试、原缺表及 writer 释放2项；明确不包含仍失败的 BUSY 截止项。

产品修改位于 budget_capture.py 和 supervision.py；未构建新候选、未调用模型或运行CI。下一步仍需将准确原生截止、启动前拒绝凭据和运行时入口权限关联，并在同一结算事务复核原预算/租约/未进入业务及无未知效果，才可处理超时。完整 G17/G04 及 Goal 均未关闭，旧安装包8/18不证明当前工作区。

## 2026-11-07 入口回归分流：缺表错误结算验证通过，BUSY 截止失败仍保留

缺表错误场景原 run_once 返回 running，随后同一执行已准确结算 failed。仅修正该测试的观察方式：使用公开 recover_completions 有限等待，核对原 execution/attempt/fence、原确认 lease_id、唯一结算回执及完整错误结果；不重发业务、不延长工作期限、不修改内部数据库。独立执行和主代理复验均通过，主代理日志 /tmp/sdk-entry-ack-race-review/noncontention-primary-verification.log（1项，1.020秒）。这不是整个入口模块重新通过。

BUSY 截止原断言仍失败：作用域限定的线程追踪表明，监控取得结果门时 completion 已完成、尚未确认入口，worker 已发布 completion_time_known=false 的 handler_error；监控保留该事实。原始追踪 /tmp/sdk-entry-ack-race-review/busy-monitor-trace.json 与同名 .log。追踪会增加观察开销；只证明该次失败顺序，不证明所有竞争形态或历史 G04 根因。不得以晚到未知事实授权超时提交，产品修复尚待实现和验证。

真实重投验证器增加入口失败事件：捕获原入口异常后立即让 producer 等待失败，保留原异常和原预算，避免已知入口失败后继续等待120秒。无存储/模型专项验证确认事件通知、原异常对象保留和方法恢复，证据 /tmp/sdk-entry-ack-race-review/handler-entry-failfast-smoke.json。尚未再次运行原生 G04。

没有新候选包、模型调用或新增完整 Gate 通过；旧安装包8/18不能证明当前修改后工作区。前轮8项/2失败报告保留为历史，本次没有重跑完整8项，也不将单项通过折算为新的整体验收。

补充边界诊断 /tmp/sdk-entry-ack-race-review/preentry-cutoff-probe.json：原工作截止已到且 trusted，constraints/started_at 与原预算一致；直接原因 SQLITE_BUSY=5，无更深异常；owner 锁可取得、pending 为空、异常不带样本 token/envelope，保留的是较早 published token。该记录仅缩小范围，不能单靠事后 pending 为空证明 BEGIN 清理已确认；需要采样生产者提供准确的启动前拒绝凭据后才可授权超时。单项原断言仍失败，无产品修复声明。


## 2026-11-07 已确认并修复入口采样 ACK 竞态，扩大回归仍有失败

无模型、真实SQLite采样与另一维护线程复现：原100毫秒采样窗口耗尽后，原样本由维护线程准确发布/ACK；调用者却因pending已清除而抛旧TimeoutError。旧安装包准确正例失败，源代码修复后正例通过且只采样一次、原约束保持。仅接受准确owner/kernel/execution/token/已发布事实、无pending/entry publication、无隐藏cause/context，并重新检查真实租约、活动性、原启动/工作期限；不扩展采样上限或请求预算。不能据此断言历史G04就是此原因。

专项4测试/10场景全部通过、3.304秒：准确ACK、身份/内容不符、未知pending、entry publication、隐藏cause/context、取消和原期限到期。独立审查无安全阻塞。扩大到入口竞争模块共8测试有2失败；旧安装包该4项模块也有1失败。busy-cutoff两者均无业务调用、completion unknown/deferred；源代码缺表错误原样保留，run_once返回running后持久结果实际到failed。未证明新增分支导致这些失败，也不能将回归标绿。准确结果、原日志和候选到工作区的单文件差异 /tmp/sdk-entry-ack-race-review/{result.json,source-regression.log,old-contention.log,candidate-to-worktree-context.patch,independent-review.md}。

源代码修复尚未冻结/安装为新候选；旧安装包8/18证据保留，但不作为修改后工作区的完整验收证明。另一个“先前迭代已保留样本”的ACK竞态仍失败关闭，未被此窄修复解决。没有模型调用、SDK内部数据库直接写入、CI、推送或发布。下一步定位结果结算与run_once返回时序，再决定修复并重建候选，不能直接重跑付费G04来掩盖回归。

## 2026-11-07 G04 重投验收未到达故障窗口，原失败保留

当前安装包实际运行 native-G04-redelivery：seed 原生成功且操作 cleaned；fast/slow 已 submitted，slow 进入宿主门控，但 fast 在原120秒观察窗口内未完成，因此未进入 pre-ACK 注入或实际重投。监督 terminal/exit1/tree_reaped，不能关闭 G04，完整通过仍8/18。原结果、监督和只读核对见 /tmp/sdk-admission-callback-candidate-20261107/native-G04-redelivery/{redelivery-evidence/report.json,native-groups-supervisor.json,failure-triage.json}。关闭后的 slow PermissionError 不能证明最初阻塞原因，当前未确定根因。

验证器补充退出门控/关闭宿主前的线程栈元数据诊断（仅文件/函数/行号/线程ID，无局部变量或凭据），原预算/断言不变；语法通过，尚未再次运行。启动前仅清理已确认终态且PID不存在的上一轮四个 npm _cacache（456,988,412字节），原始证据全部保留；准确清理记录位于 native-G03-G04-graph/terminal-cache-cleanup.json。无产品修改、CI、推送或发布。

补充只读诊断：fast 已有 worker_dispatch，handler_outcome 记录入口预算采样 TimeoutError；失败发生于 HandlerContext._enter_handler → _capture_entry_budget → supervision._sample_budget，在已捕获样本而尚未完成发布时原100毫秒窗口耗尽，尚未进入 Agent adapter。未确定窗口耗尽原因，不将其误判为重投故障或模型失败。验证器进一步增加入口异常当时的帧元数据捕获；无模型/无SDK数据库操作的专项检查确认原异常对象保留、方法恢复和字段范围，记录 native-G04-redelivery/diagnostic-smoke.json。尚未带诊断重跑真实场景。


## 2026-11-07 G03 当前包完整适用范围通过，整体增至8/18

四个实际OpenCode Agent在同一原240秒预算内完成，计4次Agent调用、19模型轮次，约159秒。精确fast工作目录的允许result.txt工具写入及FAST_NATIVE真实文件/产物确认；../escape.txt遍历和linked.txt符号链接写入按原始拒绝原因失败，外部文件保持UNCHANGED；下游实际消费FAST_NATIVE|SLOW_NATIVE。真实路径替换竞争100次、允许2次/拒绝498次、0错误、外部文件不变、竞争线程已停止。

结束后只读核对四个原invocation/deadline/execution/lease/attempt/fence/effect身份、准确tree_cleanup=confirmed回执、committed效果、succeeded执行和released资源；共享root SDK Run/finish已成功。独立复核无剩余阻塞；更正审计复用的旧allowed=0说明为实际保留计数，未改原始场景结果。G03证据与复核 /tmp/sdk-admission-callback-candidate-20261107/native-G03-G04-graph/{evidence/G03.json,terminal-audit.json,independent-G03-review.md}。范围Linux x86_64/Python3.12 tools模式，要求宿主保护根及祖先路径，不宣称进程隔离。

G04只复用该图的真实依赖正例、输入未齐不启动、根请求重放和冲突证据；缺实际重复依赖事件重投，完整G04仍not_run。因此原批次exit1由G04未完成产生，不是G03失败；监督terminal/tree_reaped。当前完整通过G01/G02/G03/G07/G09/G10/G11/G13，共8/18，Goal未完成。没有产品修改、推送、发布或CI。

## 2026-11-07 G12 当前真实OpenCode启动前故障后重试成功

原150秒/4 Agent调用/8模型轮次预算未变：一次已确认未启动的EMFILE后，沿用同invocation/完整request/工作目录/租约权限/期限，用新工具token重试，真实OpenCode返回RETRY_OK；准确原生清理、SDK execution/effect/finish确认。实际只计1次Agent调用、2模型轮次；另一个原调用耗尽两次未启动操作后准确失败，重复request_id不重执行、模型用量0。12项检查全部true，宿主close成功，独立监督exit0/tree_reaped。原始结果 /tmp/sdk-admission-callback-candidate-20261107/native-G12-prelaunch/evidence/report.json；独立复核同目录independent-review.md。

完整G12仍not_run：本项不证明业务拒绝/显式返工/模型请求提交后未知效果，更不声称HTTP重试。当前完整通过仍7/18。为后续验收释放已确认终态且PID不存在的唯一85,772,567字节npm _cacache，保留会话、数据库、回执、原日志/源码；准确清理记录terminal-cache-cleanup.json。无推送、发布、CI或产品修改。

## 2026-11-07 重试模块原失败保留，未运行项与隔离期限夹具完成

当前安装包原17项模块failfast运行9项：8通过，原2秒场景失败，确认未启动返回比期限晚约47毫秒，无法证明到期发生在确认之后；原失败、时序和终态监督证据保留于G17-technical-retries-current，非SDK已修复声明。只补后续8项全部通过、0跳过、50.463秒，证据G17-technical-retries-unrun/result.json；涵盖goal不重置重试、陈旧操作不能授权重试、监督线程未确认退出/启动失败不再执行、未知预算拒绝重试等。

独立审查允许该单调用期限夹具通过公开配置显式concurrency.application=1隔离空闲工作线程竞争；原2秒/40秒期限及到期前准确abort/原身份/无重试断言全部保持。仅重跑两个受影响场景，全部通过、0跳过、46.060秒，证据G17-technical-retries-deadline-isolated/result.json；不是默认4线程短窗场景修复，也不证明其耗时原因。三轮监督均终态、子进程清理确认，无模型调用/产品变更。汇总 /tmp/sdk-admission-callback-candidate-20261107/G17-technical-retries-summary.json，不能称单轮完整模块通过或关闭G17。完整Gate仍7/18。

## 2026-11-07 G12 当前安装包启动前拒绝与重试耗尽实际路径通过

实际OpenCodeAdapter.execute经SDK调用：工作目录准备注入EMFILE，按原technical_retries=1执行两次后prelaunch_retries_exhausted；EINVAL仅一次后prelaunch_failure。两场景22项检查全部通过：准确not_launched操作回执绑定原invocation/deadline/effect/execution/lease/attempt/fence，SDK effect确定提交、失败finish准确绑定Run/command，原150秒/4调用/8模型轮次冻结预算保持，各只计一次Agent调用、模型消耗0，同request_id重放同结果且不再执行。宿主close均成功；Popen禁止哨兵未触发，独立宿主监督terminal/exit0/tree_reaped。

原始结果 /tmp/sdk-admission-callback-candidate-20261107/G12-prelaunch-no-model/evidence/report.json；冻结验证器、监督报告、独立复核位于同级目录。独立审查在运行前发现空输入导致未进入注入点，已修正为相同非空输入并强化身份/预算断言；最终无本范围证据阻塞。此为真实适配器启动前路径，未启动OpenCode进程、未请求模型，局部计量代理仍真实监听回环。没有读取宿主密钥、联网安装或CI。

按Goal规定的五种状态，完整G12仍为not_run，局部证据单独记录passed；不能以该证据关闭完整G12：仍需成功重试及完整技术失败/业务拒绝/返工/提交后未知效果的当前包证据。完整Gate通过数仍7/18，目标未完成；原准备的含真实成功模型调用脚本未启动。

## 2026-11-07 初始化错误保留经独立审查修复并验证

独立审查指出诊断save本身可能失败而盖住原初始化错误；已将普通诊断错误附在原异常fixture_diagnostic_error上，并仍抛同一个原异常。BaseException中断不被吞掉。测试补充诊断OSError路径并核对两个准确异常对象，移除不能证明调度的空文件断言。当前安装包两项全部通过、0跳过、3.351秒；最终结果和无剩余阻塞的独立复核位于 /tmp/sdk-admission-callback-candidate-20261107/G17-initialization-failfast-reviewed。前轮结果保留为历史，不替代本轮。未重跑整个结算模块，不将旧26项报告算作修改后整个模块证明。历史初始化耗时根因仍未定位，G17未关闭、7/18保持。

## 2026-11-07 初始化失败报告不再被业务等待掩盖

只读检查原现场：thread-error结算库当前0字节、sqlite_master无表；相邻成功库包含完整v4 schema。记录 /tmp/sdk-admission-callback-candidate-20261107/G17-initialization-failfast/historical-readonly-observation.json。仅证明失败库没有已提交schema，旧连接追踪缺失仍无法确定具体耗时阶段，不宣称历史故障修复。

测试open辅助入口在发现原settlement初始化异常时先保存完整现场、直接抛出同一异常，再进入业务构造/提交之前失败；清理仍注册，原0.1秒初始化和业务等待期限均未修改。注入预算异常验证准确异常对象保留，真实线程成功/失败结算专项也通过；当前安装包2项全部通过、0跳过、3.142秒，result.json位于同目录。该改动仅修正测试错误传播，不改变SDK。上一轮预算清理分类改动独立复核无权限弱化阻塞，review记录已落盘。G17及Goal仍未关闭，7/18不变；没有付费原生模型调用、CI或新子代理。

## 2026-11-07 预算清理失败已定位为旧分类预期，受影响三项通过

原失败 G17-init-budget-lifetime/result.json 保留。runtime 的 fact_only 路径在前台交出完成权限且没有已确认结果时明确使用 late_thread_fact，覆盖 completion_time_unknown；恢复不得据此授权提交。测试旧预期已修正，并增加清理后重开真实 Kernel 的断言：原执行仍 running、result=None、lease 不变；原 token 仅 ACK 一次、容量释放、无业务重放及原期限不扩展断言保持。

新增恢复报告断言曾错误放在第一次 close 之后；此时 runtime 已关闭，恢复入口不处理 pending，返回空列表，失败现场 G17-budget-lifetime-authority-fix 保留。移除该无效观察，改用上述重开后持久状态检查。最终当前安装包三项全部通过、0跳过、9.328秒：/tmp/sdk-admission-callback-candidate-20261107/G17-budget-lifetime-authority-fix-final/result.json。未改产品、未调用外部模型；独立审查待回。此项解决本次测试分类失败，不解决历史初始化超时，不关闭 G17，完整验收仍 7/18。

## 2026-11-07 G01当前包配置合同Python3.10–3.13通过

复用原正式配置验证入口，在新建的3.10/3.11/3.13隔离安装环境均passed；连同原3.12证据，配置层适用四版本通过。149产品Python文件分别与同一冻结来源逐字节相等，YAML/Python等价、非法配置/覆盖拒绝、有效CLI默认值、双语Wiki注册表及独立Goal默认值均由原验证器检查。新增三版本约各0.5秒，准确原命令/日志/结果 /tmp/sdk-admission-callback-candidate-20261107/G01-python-matrix/result.json。

G01原本已passed，本条扩展Python覆盖，不增加完整Gate数、不推断原生OS/架构矩阵或运行时验收。无模型调用、无产品变更、无CI。G01–G18整体仍未完成。

## 2026-11-07 独立审查第二批十模块四版本完成

10模块51项覆盖配置空值/校验、可写授权、调用组/返工存储、JSON流、执行预算、时钟采样、子等待退避及原生入口截止；独立预审与主审均未发现直接内部写表或模型/网络调用。Python3.11/3.12/3.13各单轮51项全部通过；3.10原50项通过、1项因未安装可选PyYAML跳过，原报告保持。找到本地缓存的对应wheel后离线安装，3.10仅补该1项通过，合计51唯一项通过，不伪装3.10原轮零跳过。

准确逐版本结果、安装日志、原测试日志及combined.json见 /tmp/sdk-admission-callback-candidate-20261107/G17-reviewed-batch02-python-matrix。原始安装第一次缓存wheel文件名恢复错误在pip参数校验时失败，修正文件名后安装成功；未改wheel内容/SDK/业务结果。无模型调用、无联网安装、无CI；不关闭G17/Goal。

## 2026-11-07 修复后预算模块组合回归四版本通过

独立复核后的11项预算测试在当前同一wheel的Python3.10–3.13环境全部通过、0跳过；包含历史容量公共API设置、缺表与归档缺总计读故障、未知用量、期限、并发、导入和归档重放。准确逐项/逐版本结果 /tmp/sdk-admission-callback-candidate-20261107/G17-budget-reviewed-python-matrix/result.json。唯一未运行的test_v2_migration_retains_usage仍直接改旧schema，明确保留，不称整个12项模块全部完成。

G17-current-regression-ledger/audit.py现在保留可复现的只读清单生成入口；当前3462个静态声明方法中132项匹配当前包通过且测试模块字节相同，3330项在该保守清单未匹配，不等于从未运行/失败。helper闭包与全矩阵不由匹配数量推断。独立审查下一批旧API模块进行中；无模型调用或CI，G17/Goal未完成。

## 2026-11-07 归档总计受限夹具修复并独立复审

test_missing_archive_total_fails_closed不再DELETE内部总计：真实SELECT后仅在读取返回处注入None，SDK实际拒绝新支出；底层实际读到('1',)，解除注入后spent/原总计保持1且没有new预留。当前安装包单项通过、0跳过、0.176秒，原始结果 /tmp/sdk-admission-callback-candidate-20261107/G17-budget-archive-read-fault/result.json。

独立复核预算历史公共API、缺表读注入、缺总计读注入三类改动均无阻塞，结论independent-budget-fixture-review.md；仅证明注入观察下失败关闭，不声称物理损坏恢复。预算模块现仅v2旧schema手写夹具仍受限；真实0.7.3 v3→v4迁移已有另项实际证据。无模型调用、无产品修改，G17/Goal仍未完成。

## 2026-11-07 两项预算缺表夹具移除直接DROP并通过

预算缺reservations/imports表测试改为真实schema查询结果的局部故障注入：实际SQLite查询和SDK拒绝路径执行，仅从观察结果隐藏指定表名，不DROP SDK内部表；断言底层查询确实看到该表、注入后磁盘表仍存在、正常SDK重开成功。当前安装包两项全部通过、0跳过，准确结果 /tmp/sdk-admission-callback-candidate-20261107/G17-budget-missing-table-read-fault/result.json。

证明schema发现结果缺项时拒绝，不冒充物理损坏库恢复。预算模块尚余归档总计缺失和v2迁移两项直接改表夹具未解除，仍不称模块全量通过。没有产品修改、模型调用或CI，G17/Goal未完成。

## 2026-11-07 真实0.7.3公共预算库升级验证通过

从本地main保留0.7.3的ApplicationBudget源码及准确commit来源，由旧SDK公共create/reserve/settle生成真实schema v3数据库，包含已结算和unknown记录；当前独立安装包实际打开后迁移到v4。原spent/reserved/deadline/allowance/unknown_count/available保持，unknown拒绝新支出、原已结算请求重放不授权、显式reconcile后archive及重开保持spent4/available16/deadline100，原请求仍不重复授权。

准确来源、旧实现、可复现verify.py、真实数据库及结果 /tmp/sdk-admission-callback-candidate-20261107/G17-budget-v073-upgrade/result.json。没有测试直接写内部表、无模型调用；这是实际0.7.3→当前迁移，不冒充未验证的v2迁移。原4项受限夹具及全量回归缺口保持，G17/Goal未完成。

## 2026-11-07 预算历史夹具改用公共API，八项预算合同四版本通过

修复test_reservation_history_limit_is_scoped_and_fails_closed：不再INSERT内部application_reservations；在较大历史限制下通过public reserve/settle持久化第三条记录，再恢复小限制并重开，验证history exceeds。原先容量/作用域拒绝断言保留。当前安装包单项先通过，随后符合无直接改表约束的8项在Python3.10–3.13均通过、0跳过，各约1.3–2.1秒。准确结果 /tmp/sdk-admission-callback-candidate-20261107/G17-budget-public-python-matrix/result.json。

另外4项缺表/归档缺失/旧schema夹具仍直接DROP/DELETE/UPDATE内部表，单独列出未执行；不计通过、不标不适用、不称预算模块完整验收。未改产品或调用模型，G17/整体Goal未完成。

## 2026-11-07 旧API状态转换与请求回执四版本通过

当前同一候选wheel的Python3.10/3.11/3.12/3.13隔离安装环境，两个旧API模块各18项通过，0跳过；各约3.4/3.3/3.8/4.3秒。涵盖状态转换合同、调用方收到与传输交付分离、重复/冲突、并发确认及真实生产者进程退出后读取结果。原始逐版本结果 /tmp/sdk-admission-callback-candidate-20261107/G17-legacy-contract-python-matrix/result.json；无模型调用或CI。

本轮补充18个唯一方法的四版本记录，不是全量旧API回归。仍有受限夹具需逐项修复，原生监督/资源及跨平台主机缺口保持；G17/Goal未完成。

## 2026-11-07 知识库受限夹具已修复并独立复核

移除test_unknown_or_foreign_schema_refused对SDK内部knowledge_schema的直接UPDATE，改为模块局部、读取结果层的未知版本故障注入；实际SQLite连接/事务/SELECT和SDK拒绝校验仍执行。两次底层真实读取与未注入读回均断言版本1，正常重开成功，真实外部无关数据库拒绝仍保留。知识库完整6项通过、0跳过、0.592秒，当前安装包原始结果 /tmp/sdk-admission-callback-candidate-20261107/G17-knowledge-schema-read-fault/result.json。

独立只读审查无阻塞，结论independent-review.md；本项证明注入式版本读取拒绝，不声称物理损坏库恢复。保留此前未执行记录为历史，当前受限夹具已解除，保守清单103个唯一方法有当前通过记录。无产品改动或模型调用，G17和整体Goal仍未完成。

## 2026-11-07 当前包Agent合同七模块43项通过，一项受限夹具保持待处理

配置/绑定/文件权限/目标完成/知识版本/能力/调用权限模块共43项通过，0失败/错误/跳过，51.088秒；使用当前安装包与合成模型，本地SDK通信真实，无外部模型。原始结果 /tmp/sdk-admission-callback-candidate-20261107/G17-agent-contract-batch/result.json。知识库test_unknown_or_foreign_schema_refused直接UPDATE内部knowledge_schema，按用户约束排除执行并单独保留待处理，不能计通过或不适用；因此不称七模块无缺项全量通过。

保守逐ID清单新增43项当前包通过记录，合计102个声明方法匹配；仍非全量/全Python/原生验收。G17及整体Goal未完成，7/18完整通过不变。

## 2026-11-07 当前回归证据清单与诊断独立复核

独立只读审查未发现SettlementConnection记录子类的正确性阻塞：保留原参与式初始化和串行物理关闭/参与退出协议；不记录cursor fetch/iteration，且记录开销不能作为无记录器的性能证明。结论保存在候选G17-init-diagnostic/independent-trace-review.md。

当前源码静态声明3462个顶层测试方法；仅按当前候选安装导入来源及测试模块逐字节相同筛选，59个唯一方法有候选通过记录，另3403个在本次收集范围未匹配。后者不等于从未执行或失败；本清单也不覆盖继承/动态实例、helper闭包和全平台矩阵。逐ID清单 /tmp/sdk-admission-callback-candidate-20261107/G17-current-regression-ledger/ledger.json，供完整回归分组而非挑选通过项目。G17仍未完成，不能以专项数量替代全量。无模型调用或新增业务测试。

## 2026-11-07 G17 回执/生命周期专项Python3.10–3.13通过

为3.10、3.11、3.13新建独立环境并离线安装相同当前wheel，逐环境149产品Python文件与候选冻结来源逐字节相等。各18项完整模块全部通过、0跳过，分别约11.7/10.3/9.9秒；连同当前3.12的18项通过，完成本专项四版本验证。原命令、独立安装日志、逐项结果和汇总位于 /tmp/sdk-admission-callback-candidate-20261107/G17-receipt-python-matrix/result.json。无模型调用、无联网安装、无CI。

仅此18项专项四版本通过，不是全量Python矩阵或Windows/ARM原生验收；G17/G18仍未完整关闭，当前整体7/18。已向用户询问可用跨平台授权主机，等待入口期间继续独立工作。

## 2026-11-07 G17 当前安装包回执/生命周期18项通过

当前独立Python3.12安装包运行两个与已审查版本逐字节相同的测试模块，18项全部通过，0失败/错误/跳过，9.753秒。范围包括预算采样原标记保留、提交前后准确恢复、未知交接、生命周期批量事务回滚、真实提交回放、丢失ACK响应的准确对账和runtime关闭批量交付。准确结果 /tmp/sdk-admission-callback-candidate-20261107/G17-receipt-lifecycle-current/result.json；无模型调用、无产品修改、无CI。

当前G17已具备CLI14命令、结算单轮26项、6个类型消费、资源/监督15项合成模型测试及回执/生命周期18项证据；仍不等于全量旧API/Python矩阵通过，真实原生监督/资源未完成，历史偶发初始化失败未解决。G17保持未关闭，整体7/18。

## 2026-11-07 G17 当前安装包资源/监督15项实现验证通过

7项监督规则测试通过；首次执行另8项因回环权限拒绝而跳过，原报告G17-resource-supervision-current/result.json保持。只补跑这8项，允许回环通信后全部通过，0跳过，82.780秒，原期限未改。合并15项准确ID/来源见 /tmp/sdk-admission-callback-candidate-20261107/G17-resource-supervision-combined.json。

覆盖128MiB容量下96MiB父级阻止64MiB子级直到清理、默认关闭限制允许重叠、角色并发限制、配置变更拒绝、监督停止后不提交/产物进度重置/原控制器预算等。适配器为合成模型，SDK与回环工具真实运行，无外部模型调用。不能替代G17真实OpenCode监督/资源场景或完整旧API矩阵，G17和整体Goal未关闭，当前完整通过7/18不变。

## 2026-11-07 G18 当前安装包文档检查与本地Wiki预览通过

当前独立安装包Python3.12执行scripts/check_docs.py退出0：592个本地链接、双语README四个实际示例全部通过且0跳过，三个文档中的完整默认值注册表与安装包ApplicationSpec相等。本地导出25个Wiki页面到 /tmp/sdk-admission-callback-candidate-20261107/G18-wiki-preview，引用本地release/0.8.0分支；分支未发布，预览不能作为已发布链接可达证据。准确结果G18-docs-current-result.json及G18-docs-current.log保留。无模型调用、推送、发布或产品改动。

G18仍缺最终候选制品/回归一致性、适用原生平台矩阵和最终独立审查，未关闭；当前7/18完整通过不变。

## 2026-11-07 G17 当前安装包类型消费与结算最新状态

旧API类型消费6个文件全部通过，3.422秒。复用现有mypy检查器，通过--python-executable明确选择当前候选Python3.12安装环境，目标类型语法Python3.10；无依赖安装、无模型调用。准确命令/结果位于 /tmp/sdk-admission-callback-candidate-20261107/G17-type-consumers-current/result.json。

当前结算完整模块已在单轮26/26通过、43.577秒、0跳过，准确结果G17-settlement-traced-current/result.json；此前初始化失败仍未解释。G17尚需监督和资源准入真实运行及其余旧API回归，不能用这两项部分结果关闭。当前7/18完整通过不变，整体目标未完成。

## 2026-11-07 G11 当前安装包原生配置冻结与知识版本通过

native-G11-knowledge/evidence/G11.json与independent-G11-review.md支持G11关闭：实际121.936秒，旧请求在配置更新前进入并保留原prompt/tags/config版本，新请求使用新版本；旧、新请求真实读取facts v1，新请求写v2并真实读取v2，旧无权限写拒绝、新请求过期版本写冲突拒绝。准确历史INITIAL v1/UPDATED v2及当前UPDATED v2保持。两独立Run、原240秒预算/原期限、adapter入口lease/effect与准确清理回执对应，均成功；监督器退出0、tree_reaped=true。

范围Linux x86_64/Python3.12，不推断其他平台。当前候选G01/G02/G07/G09/G10/G11/G13通过（7项），整体目标未完成。G17原初始化失败仍未定位，定向通过不覆盖原失败。

## 2026-11-07 G17 单次初始化诊断未复现；保持原失败

G17-init-diagnostic原句柄94081退出0，原test_real_thread_success_and_error_recover_original_results单项（成功/错误两个子场景）在原期限通过、2.969秒、0跳过；新取证保留初始化异常完整堆栈能力，但本次未发生异常，因此没有新的原失败根因证据，不继续重复。所有26个结算方法现有当前安装包单项通过记录，但来自保留的多轮，不称一次全绿，不抹除原磁盘/初始化失败，G17完整合同仍未关闭。

G11预审修正新请求实际知识v1读取及准确v1/v2历史断言后启动两个原生调用，原240秒预算。原监督sdk080-admission-G11-20261107.service已验证启动命令返回后活跃，按15:25检查；不追加重跑，整体Goal未完成。

## 2026-11-07 G10 当前安装包跨Run服务与真实重启恢复通过

新候选native-G10-foreground/evidence/G10.json中22项checks均true、missing_checks为空，实际123.875秒，原600秒各请求预算保留；监督器退出0、tree_reaped=true。独立客户端退出后serve存活，独立Run/预算共享原服务和会话，干净重启后实际消费上下文；真实exit27发生在原结果/effect已提交、后继已接受排队但无command窗口，重启后原请求ID/期限/sequence/session不变并消费QUARTZ。另取消排队Run准确finish且0调用消耗，owner与其他Run独立成功。7个原生成功执行准确清理回执和原SDK command/limits核对通过。

independent-G10-review.md支持Linux x86_64/Python3.12范围关闭。刻意崩溃宿主的descendant_cleanup保留unknown，不以外层最终清理和原生单操作回执伪造历史进程快照；本场景不证明模型请求中unknown效果崩溃恢复或全平台矩阵。当前G01/G02/G07/G09/G10/G13通过，整体未完成，无活跃G10任务。

G17另6个未运行结算项补验全通过、6.449秒，原句柄87971退出0；当前模块累计25项唯一通过、1项初始化期限失败未解决。准确汇总G17-settlement-combined-partial.json，不称整模块一次全绿；G17仍failed。

## 2026-11-07 磁盘空间恢复；G17结算出现独立初始化失败

第二批仅删除有terminal/tree_reaped且原记录进程均不存在的旧候选20个可再生成npm缓存，约2.28GB，清单older-terminal-cache-cleanup.json。普通可用恢复约1.36GB；数据库、会话、产物、日志、源码及活跃G10不变。原磁盘失败保留。

补验原失败/未运行19项的原句柄66053退出1：实际执行13项，12通过，1失败，33.581秒。失败test_real_thread_success_and_error_recover_original_results的failure=True子场景，原3秒等待未收到handler结果；准确原现场/tmp/sdk-runtime-settlement-pj14e6sw/outcome_wait_expired.json记录driver实际抛出_UnpersistedDiagnosticsError，thread-error runtime的settlement_error为SettlementBusyError: settlement journal operation budget elapsed，active_runs=0。这是结算存储初始化失败，不再是磁盘可用0，不能误归类为真实业务handler执行后失败。具体初始化帧未被旧取证保存，根因未确认，不延长期限、不盲目重跑。

两轮19个唯一测试通过，原磁盘失败及本次初始化失败均保留；G17-settlement-combined-partial.json汇总，不称整模块通过。tests/_storage_evidence.py补存SDK已保留的原初始化异常堆栈，语法检查通过，仅诊断改动、不改产品。G17仍failed，整体Goal未完成。

## 2026-11-07 当前包 G17 CLI通过；结算模块磁盘预检失败

新候选G17-cli-current/report.json中14个实际CLI命令通过、宿主退出0，无模型调用。G17-settlement-current/result.json原句柄46783退出1：执行8项后，在test_copy_upgrade_keeps_external_pending_outcome_with_original_owner发生OSError errno28，复制预检需要2051392bytes、报告available=0；18.932秒，后续项未执行，不记完整模块通过，不推断SDK产品缺陷。原始日志与失败保持。

主机342G文件系统可用空间0。仅清理有准确terminal/tree_reaped证明的30个已结束测试目录runtime/home/.npm/_cacache，删除约3.34GB可再生成下载缓存，清单completed-npm-cache-cleanup.json；保留数据库、产物、日志、源码和活跃G10所有目录。清理后包含保留区的实际空闲约14.63GB，但普通可用仍0，尚不满足复制预检；未重跑测试。当前G17=failed，最小解除条件为该文件系统普通可用空间恢复并留足运行余量，再补验原失败及未运行范围。G10继续按15:17检查，不重启；整体Goal未完成。

## 2026-11-07 当前安装包 G09 原生五场景通过并独立复审

新候选native-G09-mailbox/evidence/report.json中的fifo/reject/replace/prelaunch/unknown全部passed，各项checks成立、app_cleanup=closed；监督器退出0、tree_reaped=true。两个并发提交者、A同会话续接与FIFO、B独立会话/工作区、逐消息准确返回、真实queue full/busy准确拒绝、待处理替换和取消替换均验证；原300秒请求预算及准确原生清理身份保留。independent-G09-review.md支持当前Linux x86_64/Python3.12范围G09关闭。

未知效果保持indeterminate且后继在3秒观察期间未调度，不声称业务效果已提交/回滚或永远不调度，也不推断所有持久资源预留均已独立审计释放。当前候选G01/G02/G07/G09/G13通过，整体目标未完成。G10已完成预审并启动，按约15:17检查原宿主监督任务，不自动重跑。

## 2026-11-07 当前安装包 G01 配置与默认值复验通过

新候选G01-current/evidence/acceptance.json记录正式配置入口passed，独立Python3.12安装包、149产品文件与冻结来源一致；YAML/Python等价、非法配置拒绝、有效默认值和双语Wiki字段注册表及独立Goal默认值对照通过。仅安装声明PyYAML可选依赖后执行无模型配置验证，不推断运行时行为。当前候选G01/G02/G07/G13通过，整体目标未完成；G09按原14:55时点检查。

## 2026-11-07 当前候选 G02 复用 G07 原生证据通过

新候选G02-reused-G07/audit.py只读核对3个准确OpenCode会话数据库，均有完成且无错误的assistant消息、文本及工具记录；与SDK成功执行/产物/准确清理回执对应。独立环境无system-site继承，安装日志及实际导入来自新wheel；149产品Python文件与wheel/安装/冻结来源/工作树逐字节一致。独立复审支持Linux x86_64/Python3.12范围G02通过，无历史OS PID快照或全平台声明。本次复用原生执行，没有新增模型调用。当前候选G02/G07/G13通过；整体未完成。

## 2026-11-07 G07 当前安装包原生通过并独立复审

新准入修复候选 /tmp/sdk-admission-callback-candidate-20261107 的G07原生专项实际完成，162.604秒，原360秒预算未延长，agent_calls=3/8、model_turns=17/64。真实self-wait准确拒绝agent_wait_cycle、禁止调用准确拒绝agent_permission_denied；允许call成功，重复相同请求返回同一子任务，send/wait完成另一子任务，两个真实产物由planner消费得到CALL_NATIVE|SEND_NATIVE。controller及三执行全部succeeded。

native-G07/terminal-audit.json只读核对3个原生操作的准确原身份/原期限清理回执、committed效果、成功执行和released资源。监督器退出0、tree_reaped=true；independent-G07-review.md支持本范围G07关闭。当前索引G07及G13通过，其余不继承旧包passed。周期证据为self-loop，不宣称覆盖所有多Agent等待环/同会话递归；本次通过不证明历史间歇Kernel锁超时根因已解决。原失败证据保留，无追加重跑。整体Goal未完成。

## 2026-11-07 新准入修复候选 G13 能力合同复验通过

/tmp/sdk-admission-callback-candidate-20261107 的独立Python3.12安装包正式G13 integration入口passed，另5项能力/文件后端合同测试全通过、0跳过。严格模式在业务提交与运行时启动前拒绝（strict_backend_unavailable，request_admitted=false，runtime_launches=[]）；工具模式仅sdk_file_tools_only。当前候选索引G13=passed。无原生strict后端，不声称强隔离；无新增模型调用。准确报告位于候选G13-current目录。G07专项仍按原14:38检查安排，不提前轮询、不追加重跑，整体Goal未完成。

## 2026-11-07 准入锁修复：新安装包定向验证通过，整体验收未完成

修复 AdmissionPool 在共享条件锁内执行可阻塞权限/预算回调的问题：回调移出锁，重新获取锁后检查释放状态、原 monotonic 截止时间和当前容量。旧安装包的冻结复现用例确实出现两项失败（检查阻塞其他任务清理、回调越过期限仍准入），原始报告保留于 /tmp/sdk-admission-callback-fix-20261107/old-package-baseline.json。

新候选 /tmp/sdk-admission-callback-candidate-20261107 在全新独立 Python3.12 环境安装本地 wheel；10项定向测试全部通过，0失败/错误/跳过，19.636秒。覆盖上述复现、恢复期间清理防止重新激活、现有准入合同，以及真实SDK本地工具协调调用/发送/去重/预算链路（合成模型）。result.json/tests.log保留，实际从独立site-packages导入，149产品Python文件与冻结来源逐字节一致。无模型调用、无CI；不是G07原生通过，也未证明原Kernel控制锁超时根因已修复。

产品已有变更，上一候选8项通过证据保留为历史；新候选current-candidate-acceptance.json不直接继承为passed。G01–G18整体未完成，下一步须以原期限检查修复后的实际原生调用路径，不能用本轮定向结果替代。

## 2026-11-07 G08通过；G07实际允许调用失败，保留原现场

原监督终态exit1/tree_reaped=true，分Gate：G08正式passed，经独立复审关闭；同session目标验证DRAFT_NATIVE→GOAL_NATIVE_FIXED、版本历史、blocked与validator错误不成功/不下发、回放不重复均成立，4个原生操作准确清理及资源released由goal-terminal-audit.json补证。G07 failed：self_wait_cycle和permission_denied真实拒绝已观察，允许call的child创建1794031747.228、Kernel started1749.845但无原生session；原父deadline1794032022.793到期后cancelled，原结果为Kernel control lock admission timed out。与此前领取前64秒延迟不同，此次是成功claim之后未进入模型的约273秒缺口，原因继续定位，不宣称修复。无自动重跑或预算延长。

准确场景、原监督与复审 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-calls-goal-current-attempt；通用cleanup初版因错误假定失败G07全部succeeded而assert退出，原文件保留为audit-terminal-original.py，拆为goal-only审计成功，不改变产品/原场景。当前通过G01–G06/G08/G13（8项）；G07失败，其余未完整关闭，整体Goal未完成。所有本轮原生任务已终态。

## 2026-11-07 G04 当前输入依赖与真实事件重投组合验收通过

当前安装包原生图+受控重投组合独立复审通过，G04现passed：双生产者输入未齐不启动consumer，真实消费文件快照，重复请求不重调度、不同内容冲突；一次ACK写入前受控失败后，宿主真实租约到期将同一event/scope由generation1重投至2且lease不同，输入绑定/消费结果/effect身份保持、consumer仅1次adapter入口，最终ACK绑定generation2。原4次调用/16模型轮次，4份准确原生清理回执、资源released；上下文closed、监督退出0且tree_reaped=true。

准确报告、combined-audit.json及independent-G04-review.md位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-redelivery-isolated-attempt。此为ACK前故障及宿主实际重投，不冒充进程崩溃、已提交ACK响应不明或G14通过；只读冲突探针不直接写SDK表。早期启动预检失败及历史间歇故障均保留，不因本次成功抹去。当前G01–G06及G13通过（7项），G07–G12/G14–G18仍未完整关闭，整体Goal未完成；本轮所有原生测试已终态，无自动重跑。

## 2026-11-07 G03当前原生文件验收通过

独立只读复审支持当前Linux x86_64/Python3.11工具权限范围G03关闭：实际允许写入、越界/符号链接拒绝、并发路径替换拒绝和外部内容不变、真实命名文件产物下游消费；4次准确原生清理与资源释放已验证。竞态样本0允许/500拒绝如实保留，允许路径由另一真实图操作证明；宿主必须控制根/祖先目录，不宣称strict隔离。证据及 independent-G03-review.md 位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-graph-current-attempt。当前通过G01/G02/G03/G05/G06/G13，G04补充重投仍按其预估时间等待，不关闭整体Goal。

## 2026-11-07 G06 当前原生正反例组合验收通过

按预定13:51检查原单元，监督进程已退出0，外层及各worker均cleanup_confirmed=true。两个补充场景05:39:25Z–05:44:22Z完成：同范围两个coder引发implicit引用ambiguous，consumer无命令/执行/effect/adapter入口；组成员缺必需产物required_output_missing，close后group_call返回agent_group_upstream_failure且consumer/effect未创建。每个实际进入操作均有完整provider响应和准确原生清理，原预算保持。与既有两轮真实adapter重叠、组关闭/汇总、任务与轮次隔离、未关闭组拒绝组合，独立复审确认G06可关闭；原始partial/失败报告保留，不改写。

合并审计及复审见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G06-combined-current。补充原证据 /tmp/sdk-g06-current-negatives-20261107-repaired-evidence 及同名.final-report.json。范围Linux x86_64/Python3.13；gate辅助adapter重叠不等于同时推理，历史约64秒领取延迟仍未根治，不关闭相关可靠性与平台缺口。当前通过G01/G02/G05/G06/G13，整体Goal仍未完成。无活跃G06测试、无自动重跑。

# SDK 0.8.0 Agent 控制层：验收记录

当前候选统一结论见 [当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。下文为追加的历史证据，局部通过及旧候选结论不得合并成当前全部通过。

## 2026-11-07 G01 当前安装包配置验收通过

G01 已关闭：最新 G01-goal-defaults/evidence/acceptance.json 对 Goal §3.2 明文默认值新增42个独立预期断言并全部通过，避免仅由实现与Wiki互相一致得出结论。结合保留的当前包14项公共配置测试、两种加载器的继承/列表/null/非法覆盖边界、CLI有效配置输出及双语Wiki完整注册表比较，独立只读复审确认G01配置范围无具体缺口。复审见 G01-goal-defaults/independent-review.md；候选根目录 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/current-candidate-acceptance.json 的G01现为passed。

该结论仅适用于当前候选的G01，不证明这些字段的全部运行时行为，也不关闭G18文档/平台交付。前面的历史“G01待复核”记录已被本条结果取代，原始证据不改写。release/0.8.0分支保持；无模型调用、无CI、无推送。G06真实并发、G17完整回归、G18平台与交付一致性继续开放，整体Goal未完成。


## 2026-11-07 当前候选完整功能证据索引

G01–G16 功能最低合同的当前适用性已完成核对，G13 仍仅能力合同/拒绝路径。各 Gate 原来源、旧失败、当前支持证据及限制记录在 `/tmp/sdk-settlement-startup-candidate-20261107/functional-current-acceptance.json`；统一结论见[当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。这不是全部 native 在新包重跑的声明。G17 未完成，G18 仍缺完整平台和最终制品一致性；Goal 保持未完成。

## 2026-11-07 新增 39 项回归及双语 Wiki 检查

当前 settlement-startup 安装包新增结果投递、编排器、宿主与本地脚本选定 39 项全通过，40.053 秒，无失败/错误/跳过；准确 ID 与当前已执行范围去重，显式散列检查用例保留排除。指南和双语 Wiki 的当前状态已同步；三份默认值注册表与当前安装包一致，589 条本地链接通过，25 页 Wiki 重新导出至本地预览。原始结果和边界见[当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。G17/G18 仍未完成，未发布。

## 2026-11-07 新增旧 API 回归及故障证据适用性

当前 settlement-startup 安装包任务提交/通知选定 25 项通过，24.579 秒、无失败/错误/跳过；一项锁夹具保留排除。G14 原 A–D 故障证据按当前差异完成独立适用性确认，保留历史执行来源，不冒充新包重跑。准确报告及边界见[当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。G17 间歇失败和完整回归、G18 平台和最终制品一致性仍未闭合。

## 2026-11-07 最新 G06 组合证据结论

G06 最低合同已由当前 settlement-startup 安装包真实双轮图与保留适用负例共同通过独立复核。8 次原生操作的准确清理、效果、Kernel 代次及原期限逐一匹配，宿主关闭控制流核实。原 G06 not_run/进程退出 1 及旧歧义 failed 均保留；不冒充所有负例在当前包重跑。完整来源、复查命令和边界见[当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。G17、G18 仍未完成，Goal 未完成；以下均为历史冻结记录。

以下带 current-package-index 标记的索引为 return-admission 等历史候选的冻结记录，名称中的“当前”仅指记录当时；不可覆盖上方链接的最新候选验收总表。

<!-- current-package-index:start -->
## G02 当前候选复用已有完整原生安装证据通过（2026-11-06）

独立审查按Goal G02核对现有证据，无需重复模型请求：候选 `/tmp/sdk-return-admission-candidate-20261106` build.log/install.log有wheel构建及准确安装，env/pyvenv.cfg为新建Python3.12.3环境（include-system-site-packages=true，非依赖完全隔离）；G05准确report `/tmp/sdk-return-admission-rework-20261106/report.json` 有安装模块/解释器/版本/OpenCode路径、六实际入口、原生会话、SDK结果及32轮已结算模型活动，准确native tree cleanup/资源释放及host_close均已独立审查。符合新环境安装wheel并由AgentApp实际完成OpenCode模型调用与SDK结果的要求，G02在当前Linux x64/Python3.12.3通过。不声称每份provider响应EOF或其他平台通过。

当前整项已通过为G01、G02、G05；G13仅已声明的能力合同/业务前拒绝范围。G06及G17已有新增真实子范围证据但尚未整项关闭；G12原短预算间歇失败与历史回归缺陷、G18完整制品回归/平台缺口仍保留。

## G17资源正反例独立复核完成；G06完整组场景启动（2026-11-06）

独立只读核对G17两个Run的准确持久记录：parent created→deadline均360秒，child继承原deadline且command一致，各2次Agent/6轮已结算模型用量。有限场景128/96/64准确原生父调用等待send门控，子级无runtime effect/native，96 MiB资源的准确native-cleanup释放先于子级准入；默认关闭时子级进入、父原生仍authorized且门控未放。全部四原生cleaned且四资源行released、准确身份与回执匹配；持久结果OpenCode1.18.32/succeeded。此为真实门控send等待和逻辑预留，不测物理内存、不声称每份provider流完整或同步group wait。资源子范围通过，监督触发及完整旧API回归仍缺，G17未关闭。

预检无具体接口阻塞的冻结native_groups_rework以当前安装包公共验证入口启动：`/tmp/sdk-return-admission-g06-rounds-20261106`、句柄63337，--case G06 --layer native。预计6–12分钟、首次约6分钟后检查；保留原3600秒/16 Agent/128轮主请求预算，第二隔离root亦用其原配置。预期共8个实际执行，两个coder轮次各含最长180秒第二成员准入门控；真实adapter区间重叠不等于同时模型推理。脚本即便场景通过仍将整个G06标not_run，须与已完成负例组合并独立核对准确清理/范围。未验收，不关闭G06，不因观察超时重启。

## G17 当前包两个原生资源场景报告通过（2026-11-06）

首次预计检查时原句柄10107已退出1；`/tmp/sdk-return-admission-g17-resources-20261106/report.json` 的resources_limited/resources_disabled均passed，G17/supervision仍not_run，与脚本约定一致。两个environment均准确指向return-admission/env/site-packages与版本0.8.0.dev1。有限场景完成child_waited_under_reservation、parent_cleanup_before_child_resource_grant；默认关闭完成child_overlapped_without_memory_limit。两个场景均原360秒预算、actual_native_child_succeeded且run_completed，全部原始事实保留。准确持久清理及资源行独立审查待完成，不凭两个passed直接关闭整个G17。未重启、未扩大预算。

## G18 当前候选sdist构建、字节一致性及离线安装切片（2026-11-06）

未修改冻结候选，在独立拷贝 `/tmp/sdk-return-admission-sdist-source-20261106` 构建 `/tmp/sdk-return-admission-sdist-20261106/dispatcher-sdk-0.8.0.dev1.tar.gz`。`parity.json` 四项通过：sdist/wheel产品路径集合一致，151份产品文件与冻结source及当前installed逐字节一致，sdist的pyproject与冻结配置一致；无新增hash/checksum检查。构建日志 `/tmp/sdk-return-admission-sdist-build-tools-20261106.log`。

独立system-site-packages环境 `/tmp/sdk-return-admission-sdist-env-20261106` 使用--no-index/--no-deps/--no-build-isolation离线安装sdist。首次因pip默认cache指向只读/root/.cache失败，原install日志保留；加--no-cache-dir后实际构建安装成功，install-local日志保留。包外-I确认导入来自独立安装目录、版本0.8.0.dev1，公共ApplicationSpec展开默认trigger=inputs_ready/lifetime=task，`import.json`。依赖由宿主继承，不能称全新无依赖环境验收；此为sdist制品/安装切片，不替代完整回归及平台矩阵，G18保持未通过。

## G06 两负例独立复核完成；G17原生资源正反例启动（2026-11-06）

独立只读复核selected报告及准确持久记录：三份真实原生操作对应资源行全部released，native-cleanup proof与准确operation/invocation/execution/effect/lease/attempt/fence/deadline及回执匹配；每执行至少一份完整响应。缺失输入及组必需输出负例、原预算与监督清理均无具体缺口。另有一份不完整provider响应仍保持不完整，不称全部请求完整，原歧义failed报告不改写。G06其余范围仍开放。

已预检的当前候选冻结verify_agent_supervision_resources.py通过包外-I启动，输出 `/tmp/sdk-return-admission-g17-resources-20261106`，句柄10107；仅运行有限资源与默认关闭对照，预计4–8分钟，首次约5分钟后检查，每case原360秒预算不变。有限场景是父原生调用等待被门控的send响应，并非模型发起同步group wait；它检查128/96/64逻辑预留与准确释放，不测物理内存。该脚本即便两case通过也按wholeG17 not_run退出1，必须看各case及清理证据，不能只读退出码。尚无结果，不关闭G17。

## G06 两项当前包真实负例通过（2026-11-06）

首次预计检查时原句柄6361已退出0。`/tmp/sdk-return-admission-g06-selected-20261106.final-report.json` passed，精确requested_cases为missing_reference/group_required_output；外层及两case监督passed/cleanup_confirmed=true/root_exit0，04:12至04:13:59Z约两分钟完成。原300/600秒请求预算和900秒共享截止未改。

missing_reference：producer2a4cec7c73974c2a8ba4fb4b50bb39f4真实成功、未发布answer；consumer9064081957db43b1b529161852da7b47以missing_input失败且command/execution/runtime effect/adapter入口均不存在。group_required_output：真实planner7cfdf813ffe0425d8dcea9f5de99aa55创建、发送并关闭组e9b29591524d43d6a81ab877b47be418，真实member11b61857f1634fa5b9d05c904f7ee806以required_output_missing/answer失败；后续group消费准入效果不存在。两case均全部准确native/effect/Kernel及每执行完整provider响应守卫通过，组工具观察关闭后静止。准确资源回执独立复核另记；此处不是全G06通过。此前歧义现场及原失败保留，仍缺并发正例、未关闭组及跨任务/轮次隔离完整当前证据。

## G17 当前安装包六项公共类型消费检查通过（2026-11-06）

独立临时工具环境 `/tmp/sdk-g17-typecheck-tools-20261106` 安装mypy2.4.1，未改产品或项目依赖。按现有CI六个消费者冻结到 `/tmp/sdk-g17-typecheck-20261106`：orchestrator/capability/reliability/application/observability/agents。包外执行mypy，显式--python-executable指向return-admission/env/bin/python、--python-version3.10、--follow-imports=silent、--warn-unused-ignores，退出0，result.log为Success: no issues found in 6 source files；scope.json保留选择范围。此为旧/新公共API静态消费检查，不代表实际Python3.10执行或其他平台矩阵。未调用模型，不关闭G17/G18；完整旧API运行回归、真实资源及监督触发仍缺。

## G06 公共场景选择验证通过并补跑两项未执行负例（2026-11-06）

验证器新增可重复--case公共参数，默认仍为全部三项；外层验证非空/已知/唯一选择，传给受监督controller，最终报告只在准确选中集合全部通过且原身份/制品/期限/清理守卫成立时通过，并明确selected-only scope。内部worker启动权限未变。`/tmp/sdk-g06-selection-final-tests-20261106.log` 30项7.192秒通过，独立审查无具体阻塞，含默认/两项选择传播及非法选择拒绝。

冻结 `/tmp/sdk-g06-selected-verifier-20261106/scripts`，当前return-admission安装包通过公共入口仅补missing_reference、group_required_output；输出 `/tmp/sdk-return-admission-g06-selected-20261106`，句柄6361。预计3–8分钟，首次约4分钟后检查；900秒共享上限及原请求预算不变，不重复已执行歧义场景，不因观察超时重启。运行未验收，不关闭G06/G18，未改产品。

## G06 真实诊断及响应证据合同纠偏（2026-11-06）

句柄83180已退出1，原报告保持failed；04:03（本地12:03）启动至04:04:36Z结束，外层与case监督均cleanup_confirmed=true/root_exit1。准确case `/tmp/sdk-return-admission-g06-diagnostic-20261106/ambiguous_reference/ambiguous_reference/case.json`：root6响应完整；子ec3f443e33944948ae7ac050e9fd1b6d有2响应，其中1份EOF/DONE/choice结束/模型输出完整，另一份DONE/choice结束/模型输出为true但EOF=false，parse_failed=false。全部身份匹配、无活动读取、无丢失/记录失败、准确回执及代理清理有效；未确定另一份为何缺EOF，不称其辅助请求或推断无provider重试。

独立审查对照Goal G06确认所需是每准确执行至少一份完整真实模型响应，并非每份provider响应完整。工作区观察器从原all-complete改为all身份/活动读取守卫加any-complete，仍保留所有原记录失败/丢失、准入、准确回执与清理守卫；报告明确response_requirement=at_least_one_complete_response_per_exact_operation。这是放宽验证器原来额外的all-responses属性，未将不完整响应升级完整，未改变产品合同。新增完整+不完整、零完整、混合身份不符/活动读取测试，连同既有隐私/记录失败/回执/清理反例通过，日志 `/tmp/sdk-g06-response-contract-20261106.log`。

该准确保存现场可独立支持存在完整子响应的回溯事实：两个coder成功、组真实关闭汇总、consumer ambiguous失败且无command/execution/effect/adapter、准确原生清理和预算守卫均有记录。原验证器failed状态不改写，不宣称整套G06通过；缺失输入/组必需输出未执行，未关闭组及并发跨任务/轮次隔离仍缺本候选完整证据。下一次仅补未执行范围，避免为改验证器标签重复两个已执行coder。

## G17 当前包空闲CLI生命周期切片通过（2026-11-06）

`/tmp/sdk-g17-cli-20261106/report.json`，包外-I实际return-admission/site-packages来源。真实子进程执行validate、config show --effective、serve、status、stop --triggers、resume --triggers、stop宿主，全部退出0，serve最终退出0；原stdout/stderr和临时驱动 `/tmp/sdk-g17-cli-probe-20261106.py` 保留。离线核对6项成立：空闲status={}、触发暂停true/恢复false、stop={stopping:true}、有效worker触发模式call、宿主退出0。无任务提交或模型调用。

这是配置/空闲宿主CLI切片，不证明带任务resume、模型执行、监督触发、128/96/64资源准入、旧API回归或类型消费。G17仍未关闭。资源单元测试使用合成adapter，真实原生资源探针和监督探针已定位但未在本候选运行；当前安装环境无mypy，不能凭CI定义补判类型检查通过。

## G06 带完整有界诊断的补证启动（2026-11-06）

独立审查确认诊断不改通过谓词且无正文泄露。冻结验证器 `/tmp/sdk-g06-diagnostic-verifier-20261106/scripts`，同一return-admission安装包经公共监督入口启动，输出 `/tmp/sdk-return-admission-g06-diagnostic-20261106`，句柄83180。预计5–10分钟，首次约5分钟后检查；原900秒共享上限和各请求预算不变，不因观察超时重启。此次新增诊断，非无变更重复运行；尚无最终结果，不关闭G06。

## G06 响应流诊断本地验证（2026-11-06）

stream observer仅补固定EOF/解析失败/DONE/choice结束/模型输出布尔及字节/事件计数，proxy报告逐响应携带该有界诊断；未修改原完整响应、身份、回执和清理判定。`/tmp/sdk-g06-observer-stream-diagnostic-20261106.log` 三模块20项1.060秒通过，含真实SDK代理连接本地合成上游的完整/截断流，不涉及模型。源码流转发在第一次空读取后break，未发现重复EOF的确定缺陷；实际客户端提前断开等情形仍需下一真实诊断，不能推断上次失败根因。旧失败保留，G06未关闭。

## G12 当前包原两秒观察补强与间歇前提失败（2026-11-06）

新增测试内调度/flush/worker/claim分段计时后，源码单次3.536秒通过；准确abort时原预算剩约0.236秒，日志 `/tmp/sdk-g12-dispatch-timing-20261106.log`。当前return-admission安装包由包外-I启动确认site-packages来源，原两秒用例3.508秒通过，`/tmp/sdk-g12-installed-original-timed-20261106.log`、成功事实 `/tmp/sdk-confirmed-abort-expiry-1osi32ls`。独立审查指出两秒旧夹具未观察真实handler Future，调用次数仅断言时快照，因此这两次不直接关闭最终无重放或间歇故障。

测试现对两秒与40秒均透明观察实际executor Future，在原wait_seconds总体观察截止内等待退出（最多10秒且不超过原剩余观察窗口），完成/非取消后再核对准确一次调用、身份、abort、效果及预算；原seconds2/wait30和产品不变。补强后的当前安装包单次 `/tmp/sdk-g12-installed-original-quiescent-20261106.log` 3.791秒失败：handler已退出且调用一次，但abort_returned1793937640.66873晚于原deadline1793937640.5605981约0.108秒，原“abort必须先于deadline”断言正确拒绝。现场 `/tmp/sdk-prelaunch-deadline-failure-gs5li_jm` 保留。不把前次绿值作为稳定修复，G12/G18仍未关闭。本轮没有模型调用、产品改动或CI。

## G06 三项补证提前失败：歧义行为正确但响应观察未通过（2026-11-06）

到首次预计检查时，原句柄20193已退出1。实际03:51:00Z–03:52:34Z约95秒结束，未耗尽900秒上限；外层和case监督均cleanup_confirmed=true/root_exit1，无残留监督声明。最终 `/tmp/sdk-return-admission-g06-negatives-20261106.final-report.json` 为failed。

首项ambiguous_reference中两个coder均succeeded，准确native/effect/Kernel回执有效，组关闭后等待成功；consumer以ambiguous失败且无command/execution/effect/adapter入口，原预算保持。失败谓词是provider_response.all_entered_operations_have_model_response=false：root6份响应通过，子coder2份响应未通过。原报告只保留汇总，无法区分完整SSE、观察丢失、身份或回执谓词，不能据成功状态补判真实响应，也不能认定产品歧义功能故障。缺失输入/组必需输出两项未执行，G06仍未关闭。

工作区观察器新增固定布尔/计数诊断，保留原通过谓词，不写响应正文或身份内容；本地test_g06_proxy_observer通过，日志 `/tmp/sdk-g06-observer-diagnostic-20261106.log`。未改产品或重跑模型，旧失败保留。下一步先审查观察边界，确认需要新证据时只重跑受影响范围。

## G12 单次分段计时复现：进入适配器时仅余53毫秒（2026-11-06）

测试增加仅内存固定名称/线程/单调时钟起止/异常类型观察，透明转交参数与异常，结束后还原；独立只读审查无具体阻塞。未改产品、两秒预算、wait30或原断言。`/tmp/sdk-g12-entry-timing-20261106.log` 单次运行4.722秒失败，现场 `/tmp/sdk-prelaunch-deadline-failure-2yzw83rn/evidence.json` 保留。

与此前adapter0现场不同，本次adapter实际进入1次，但进入时原预算只余0.053秒，未到准确native abort前提，仍非post-abort通过。单调时钟显示accept约0.048秒、submit约0.332秒；submit返回至handler_admission开始约0.773秒；handler admission约0.105秒，handler budget entry约0.084秒；agent_execute开始距accept开始约1.533秒；runtime_setup后才进入adapter。各跨度包含且可能重叠，不能相加或断言同一根因。此证据将下一调查收窄为提交后调度等待及执行前准备成本，不能再统一报告“适配器从未进入”，也不据一次计时承诺性能修复。G12/G18保持未通过，不重复模型或同例。

## G06 当前包补充负例启动（2026-11-06）

使用 return-admission 安装候选及已独立审查的冻结验证器，通过公共监督入口启动三项真实负例：歧义引用、缺失输入、组成员缺失必需输出。输出 `/tmp/sdk-return-admission-g06-negatives-20261106`，日志同名 `.log`，执行句柄20193。总上限900秒为共享截止，未增加各请求预算；预计5–10分钟，首次检查在启动约5分钟后，不提前轮询或因观察超时重启。启动不等于通过，最终报告待检查。

此三项不单独关闭G06：未关闭组负例、并发正例以及跨任务/轮次隔离仍需有效证据。G12下一步为入口分段耗时定位，未重复运行已知失败用例；本轮未修改产品、运行CI或发布。

## 当前return-admission候选G05真实验收通过（2026-11-06）

`/tmp/sdk-return-admission-rework-20261106/report.json`，句柄26564退出0，9项检查全部true、host_close_completed=true、return_failure_files空。原600秒预算未改，实际6次Agent调用/32模型轮次。独立只读审查确认6个准确原生操作均cleaned、6份资源记录released且native_cleanup proof匹配invocation/execution/effect/lease/attempt/fence/deadline及准确回执；效果committed、SDK准入及原预算/版本绑定均匹配。

对照Goal G05原要求，真实root模型承担planner编排，调用两个coder→reviewer→显式指定成员返工→原逻辑reviewer消费准确新版本结果和原反馈；初始DRAFT_A/DRAFT_B、FIX_B绑定、返工FIXED_B、REVIEW_REPLAY_OK及根ROUTE_OK均实证。第二reviewer是新invocation及新原生session，logical_reviewer_id显式绑定原reviewer；不声称同原生会话续接。Goal仅在goal验证（第83行）要求同会话，G05无此要求。主代理复核及独立审查未发现G05原文的缺失谓词，因此此前脚本“仅route切片”标签及本页“仍需另跑planner”的保守判断收窄为：此证据足以关闭G05的逻辑reviewer返工合同，不覆盖G06负例/其他平台/G18，避免重复同等真实调用。原报告scope原样保留，不改写历史失败。

本候选当前G01、G05及限定G13通过；51项定向包外测试/文档检查通过。G02–G04、G06–G12、G14–G18尚无本候选完整适用证据，下面旧候选表不是本候选总览。G12原两秒失败仍保留，历史间歇故障亦未因本次成功消除。

## G12公共宿主预启动未解除两秒故障前提缺口（2026-11-06）

独立审查确认本负例目标是post-abort禁止重试，Goal G12未要求冷宿主在两秒内进入；可在创建原请求预算前通过公共app.start准备宿主，仍保持seconds2/wait30及全部准确abort/身份/预算断言，同时保留冷启动失败证据、不称其已修复。源码夹具仅增加该准备步骤后，`/tmp/sdk-g12-ready-host-original-20261106.log` 4.842秒仍boundary_reached=false/adapter未进入，原断言失败。因此“只需移出宿主冷启动”假设不足，G12未关闭，无模型请求/产品变更，下一步需要更细的入口耗时证据而非继续重复同例。

## 真实路由首次预计时间检查与G12只读收窄（2026-11-06）

return-admission返工句柄26564在启动256秒的预计窗口检查仍live，report未生成；下一检查预计约四分钟后，原600秒不变，无重启。存活不作业务推进。

G12两秒新现场只读核对：Agent created1793936227.911/deadline6229.911，Kernel started6228.734，adapter0，pending deferred为late_thread_fact/outcome timeout/completion_time_known=false，无保存的sampling拒绝。线程快照有Orchestrator投影连接的WAL检查，但不足以证明瓶颈或具体根因；不得据单张快照修改持久性配置、预算或断言。原失败保持。

## return-admission候选G12原两秒负例仍失败（2026-11-06）

在真实路由等待期间，仅运行同一安装包原test_original_deadline_expiry_after_abort_blocks_retry，保持seconds=2/wait30、原断言和本地原生守护通信，无模型。`/tmp/sdk-return-admission-g12-original-20261106.log`，4.874秒失败，adapter_calls=0/boundary_reached=false/无boundary timing，未到确认abort前提，不能称为post-abort验证。准确新现场 `/tmp/sdk-prelaunch-deadline-failure-60yxb4d3/evidence.json`、state-r2tlrp9b、threads-st3q4vta保持；不以40秒补充例替代或延长原预算。入口/完成修复未消除本两秒缺口，G12/G18仍未关闭；后续定位应针对启动前耗时，而非新增模型重跑。

## 完成准入修复候选真实路由复验启动（2026-11-06）

return-admission同一安装候选G01/限定G13通过，`/tmp/sdk-return-admission-config-20261106/{acceptance.json,G01.json,G13.json}`；冻结包外文档检查578链接/4README示例通过0跳过，`/tmp/sdk-return-admission-docs-20261106.log`。这些不等于全部Gate通过。

独立审查发现返回诊断按线程命名会覆盖原失败，已改UUID每次独立、O_EXCL/0600创建；新增同一线程两次失败保留两文件断言，5项测试通过 `/tmp/sdk-return-probe-observer-unique-20261106.log`，最终复审无阻塞。验证器冻结 `/tmp/sdk-return-admission-verifier-v2-20261106/scripts`（此前未使用版本保留）。真实显式返工路由现用return-admission安装包与该冻结验证器启动，输出 `/tmp/sdk-return-admission-rework-20261106`、句柄26564，原600秒预算；预估4–8分钟，首次约4分钟后检查，不延长/重启。尚无最终结果，不关闭G05/G06/G18。

## 完成准入修复新安装候选：51项受影响测试通过（2026-11-06）

产品冻结为 `/tmp/sdk-return-admission-candidate-20261106`，独立wheel安装，包外-I真实文件启动确认site-packages导入。完成控制准入、入口竞争、准确采样回执、关闭生命周期、串行采样5模块51项全部通过、0失败/错误/跳过、62.820秒，installed-file-result.json/installed-tests.log。此新包包含上一entry-admission候选缺失的pre-yield刷新修复；旧包Gate结果不自动升级。

为防止下一真实故障只保留类型，工作区返工验证器新增可撤销的准确_capture_owned_return观察，仅写SDK有界脱敏位置，不写异常正文/会话/凭据；参数、返回及异常身份不变，诊断写失败不覆盖原失败，最终报告列出证据文件名。观察测试模块5项通过（`/tmp/sdk-return-probe-observer-20261106.log`），包含准确参数透传、异常身份/隐私及写失败/恢复。验证器修订在候选冻结之后，尚未冻结使用；产品不变，无本轮模型调用，不关闭G05/G18。

## owned-return控制准入进入前到期：确定复现与源码修复（2026-11-06）

只读原返工coder准确错误匹配 `_ControlAdmissionTimeout: Kernel control admission budget elapsed`，不是lock acquisition timed out。新增test_pre_yield_check_expiry_uses_remaining_original_admission延迟首次真实连接可用性检查.12秒，原capture两秒不变；基线 `/tmp/sdk-owned-return-preyield-baseline-20261106.log`失败于_control_lock进入yield前，证明短.1秒切片即使原截止尚有余量也可提前拒绝。该确定边界与原真实故障消息一致，但原现场无栈，不能据此宣称已证明其完整因果链。

_control_lock现在仅在显式_retry_until存在且尚未SQL/yield、连接检查耗尽短窗口时，重新核对停止/authority并刷新短切片，仍取原retry_limit、caller及previous嵌套期限的最小值；最终截止检查与finally还原/释放及异常传播保留。原owned-return控制模块17项全部通过10.016秒，`/tmp/sdk-owned-return-preyield-fixed-20261106.log`，含原截止、继承截止、停止/撤权、body/cleanup异常不重试等既有范围。独立复审无具体阻塞，未另跑测试/模型。产品源码已变，entry-admission安装候选不含此修复，尚需新包验证，原真实失败保持，不关闭G05/G18。

## 准入修复候选真实返工仍失败：阻塞已转到返工coder完成结算（2026-11-06）

原600秒不变真实运行 `/tmp/sdk-entry-admission-rework-20261106/report.json`，句柄68711已退出1，failed/root_run/TimeoutError、checks空、host_close_completed=true，不报G05/G06通过。共5次adapter入口：root a94096fe28e14e6c867f37159253a947、两个初始coder、首次reviewer、返工coder683fc9b9890748609025fd75a9ca323b。只读准确settlement发现前三子执行result recorded，而返工coder于1793935303.046已留下pending deferred kind=late_thread_fact/outcome.kind=ok/completion_time_known=false，completion_time_error类型_ControlAdmissionTimeout，无proof/具体位置。root后来到期留下timeout/未知事实。本次不是已证明的第二reviewer入口采样拒绝；此前根据5次入口推断“第二reviewer依旧未进入”不能进一步推断已提交或故障相同。下一定位对象为返工coder的owned-return/完成结算准入，原现场保持、不重跑/延长预算、不改写内部状态。

## 准入修复候选配置及文档检查（2026-11-06）

entry-admission同一安装包包外G01与限定G13通过，`/tmp/sdk-entry-admission-config-20261106/{acceptance.json,G01.json,G13.json}`，Linux x64/Python3.12.3。G13仅能力合同和缺能力业务前拒绝，不声称原生强隔离后端。冻结候选source/scripts/check_docs.py使用候选env包外执行退出0，578本地链接/4个README可执行示例通过、0跳过，`/tmp/sdk-entry-admission-docs-20261106.log`；不是全G18通过。

真实返工链第二次预计时间核对：句柄68711仍live，启动约519秒，report尚未生成；原600秒预算不变，下一次预计约2分钟后包含收尾观察。仅存活不算业务进展，不重启、不延长预算。

## 关闭生命周期夹具按真实返回合同拆分并通过（2026-11-06）

独立调查确认原夹具在持有写锁时要求driver两秒返回，与serialized return在原四秒工作预算内等待准确pending采样的行为冲突。测试现拆分截止前释放与持锁跨原截止两种真实Runtime/SQLite时序；原四秒work/.05捕获/两秒join不增加。前者要求准确原token发布、业务一次成功、原预算约束保留、资源释放及重开日志准确身份；后者要求原截止后真实unknown/deferred、不得伪造completion proof、原准确样本/连接/容量在首次关闭失败时保留，释放写锁后同token清理、不重放、原约束/水位与持久日志不变。原失败现场保留。

源码两项通过9.576秒，`/tmp/sdk-close-contract-primary-20261106.log`。主代理审查补强成功分支重开日志精确execution/attempt/fence/lease断言后，测试冻结于 `/tmp/sdk-close-contract-installed-20261106/tests`；使用entry-admission候选env包外-I实际安装包运行，两项全部通过9.399秒、0跳过，result.log含安装来源。产品未改，本包前述32项与本两项分开记录，不冒充全回归。

同一安装包真实显式返工路由已启动：`/tmp/sdk-entry-admission-rework-20261106`，句柄68711，原600秒预算，预估4–8分钟；尚未到预计检查时间，未重启/延长或提前刷新。其范围仍为route切片，不能独自关闭完整G05/G06。

首次预计时间（启动约四分钟后）核对同一句柄68711仍live，report.json尚未生成，工具未报告退出；仅确认为在运行，不计为业务推进或通过。下一次检查预估再四分钟后，原600秒预算仍不变，未启动重复运行。

## 准入修复新安装包定向验证通过（2026-11-06）

最新入口修复冻结为 `/tmp/sdk-entry-admission-candidate-20261106`，从冻结source构建wheel并独立安装；包外-I真实文件启动器确认dispatcher_sdk来自该env/site-packages。入口竞争、准确采样回执、串行采样3个完整模块32项全部通过、0错误/失败/跳过、45.991秒，installed-file-result.json及installed-tests.log。包含前述安装失败的原startup截止负例、正常发布准入、锁退出异常拒绝、准确崩溃回执恢复及原采样所有权保护。关闭生命周期模块明确未纳入本次32项，旧夹具冲突修订另行进行；此结果不覆盖真实G05返工链或完整回归。旧cleanup-diagnostic候选各Gate证据不能自动升级到本候选，G05/G18未关闭，无模型/CI/发布。

## 关闭观察夹具参数错误已修正，真实关闭时序仍未通过（2026-11-06）

只读原w73ikune现场明确completion_time_error为测试observe_completion不接受serialized关键字的TypeError，并非已证明的产品漏写proof。包装器现接受并原样转交**options，原断言/2秒join/4秒work均未修改，独立复审无具体问题。真实函数恢复后四模块33项32通过1失败、45.244秒，`/tmp/sdk-entry-admission-source-final-20261106.log`，新现场 `/tmp/sdk-budget-capture-close-lifetime-hn3q4wds/evidence.json`：driver未在原join2内退出。Runtime的legacy返回路径当前显式调用serialized=True/work_deadline=原工作期限；夹具持有写锁使owned pending样本不能发布，因此当前行为与旧两秒返回假设需核对合同。不能把参数修订视为关闭用例已通过，也不能直接延长期限/删除断言刷绿。入口其余测试在本组合通过，产品源码尚未冻结为新安装包，无模型调用，G05/G18仍未关闭。

## 入口准入到期分类修复：源码通过，关闭回执仍失败（2026-11-06）

新增SDK私有_ControlAdmissionTimeout（仍继承TimeoutError），仅_control_lock在yield前的准入到期使用；finally清理正常返回后才可能被上层收到，清理异常仍替换并保留cause。_sample_budget仅在已有准确sampling拒绝、自身无token且该私有准入错误无cause时继续保留原拒绝；普通/锁退出TimeoutError仍附cause而拒绝重试。完成时钟两处原严格TimeoutError检查显式兼容该私有类型，原cause/owner/工作截止保护不变。独立复审两次无具体阻塞，未运行模型或测试。

入口原5项全部通过34.137秒，`/tmp/sdk-entry-admission-typed-20261106.log`；新增过期控制范围不得yield、不得保留锁且后续控制锁可正常使用的测试通过，`/tmp/sdk-control-admission-subtype-20261106.log`。完成时钟兼容修订后相关3模块27项26通过1失败、9.856秒，`/tmp/sdk-entry-admission-related-20261106.log`：关闭回执test_repeated_close_finishes_same_real_context_token_without_replaying_business仍return_proofs=0，现场 `/tmp/sdk-budget-capture-close-lifetime-w73ikune/evidence.json`。未改断言或期限，不把此失败视为修复完成。新修订尚未安装包验证，之前entry-window候选仍为失败候选，G05/G18不关闭。

## 入口修复新安装候选：受影响回归仍失败（2026-11-06）

独立复审撤回控制锁退出cause被隐藏的阻塞意见：现有cause保留及拒绝重试谓词和新增注入测试相符。新源码冻结为 `/tmp/sdk-entry-window-candidate-20261106`，wheel独立安装至env；尚无全Gate验收，本页下方cleanup-diagnostic表仅适用于旧候选。

首轮stdin启动器不适用于multiprocessing spawn，32项1失败5错误、45.134秒，installed-result.json/installed-tests.log保留；5错误实际为 `/tmp/<stdin>` 不存在，不是产品修复。更正为真实run_installed.py且main guard后，原4模块32项30通过2失败0错误0跳过、16.400秒，installed-file-result.json/installed-file-tests.log。入口未发布负例仍提前拒绝：`/tmp/sdk-runtime-entry-sampler-8anhkwvp/sampling-evidence.json` 显示cause TimeoutError来自_sqlite_base.py:444、supervision.py:453，即控制锁进入yield前短窗口到期，不是上一已修的进入后:465分支；原startup尚约28秒，业务0，自身无pending/token。因此源码修复不完整，不能声称问题已解决。另一失败为test_repeated_close_finishes_same_real_context_token_without_replaying_business，return_proofs为0而要求1，仍未定位，不能以其他30项覆盖。下一修复须精确区分控制锁正常清理后的准入到期与清理未知，保留锁退出注入负例；无真实模型、CI或发布。

## G05 入口短采样窗口源码修复与定向验证（2026-11-06）

supervision._sample_budget仅在持有控制锁、排空原采样者之后、尚未创建自身token且本次短检查窗口已到期的明确分支，直接保留此前sampling拒绝；不人为附加新的计时原因。其他TimeoutError仍沿用带cause传播，context入口仍拒绝带cause的不明采样错误。未改原startup/工作截止或放行未发布样本。

`/tmp/sdk-entry-live-sampler-fix-20261106.log` 原4项全部通过35.537秒，包括完整Runtime真实SQLite发布后准入、未发布直到原startup截止且业务0、owned/legacy拒绝。发布线程等待改为原startup剩余时间加2秒收尾观察，未改变业务期限。独立审查提出控制锁退出TimeoutError风险；新增真实控制锁包装注入第二次退出错误的测试，通过 `/tmp/sdk-entry-lock-exit-20261106.log`，证明原sampling异常身份和准确cleanup cause保留，仅两次锁准入，无业务入口/自身pending。复审待返回。产品源码已变，尚未构建安装候选或取得真实G05证据，旧候选已通过项不自动升级到新源码，G05/G18仍未关闭。

## G05 本地入口拒绝已定位异常来源（2026-11-06）

本地原4项测试补充SDK有界异常位置，断言、预算与产品均未修改；`/tmp/sdk-entry-live-sampler-cause-20261106.log`，4.790秒、3通过1失败。失败证据 `/tmp/sdk-runtime-entry-sampler-c3g8_hn7/sampling-evidence.json` 明确异常链为supervision.py:459本次采样短窗口到期TimeoutError，经:502的 `raise unresolved from exc` 附加到原sampling拒绝，再由budget_capture.py:197/context.py:342传播。自身无pending/owned token，业务0，观察1713069.024早于原startup1713098.097。此前事务清理ACK超时猜测不符合本次实际栈；不据此推断原真实G05现场具有完全相同因果链。下一修复必须区分已确认短窗口到期与未知清理/权限故障，不能普遍移除异常原因或放行sampling未知。未启动模型、CI或新候选，G05/G18仍未关闭。

## G05入口采样拒绝的本地复现与未决测试（2026-11-06）

继续只读原第二reviewer准确结算payload发现outcome.message是固定SDK原因 `budget_clock_sample_unresolved:sampling`，此前“具体预算未知原因未保存”应收窄为：已知采样未决原因，但原采样者/拒绝位置及因果链未保存。没有输出模型正文或凭据。

新增完整Runtime+真实SQLite的外部采样者竞争测试。首次4项通过7.927秒只证明拒绝/允许，未断言等到startup截止，不能支持“等到原启动截止”的解释。补充该断言后真实失败：`/tmp/sdk-entry-live-sampler-retained-20261106.log`；进一步保留诊断后 `/tmp/sdk-entry-live-sampler-diagnosed-20261106.log`，4项3通过/1失败、5.275秒。失败现场 `/tmp/sdk-runtime-entry-sampler-bn1_rkl0/sampling-evidence.json`：固定sampling拒绝带cause_type=TimeoutError，自身无pending样本/错误token，观察1712800.800早于startup1712829.230，业务0、execution running。不能把该结果说成到启动截止才拒绝，尚需判断清理ACK不明导致早拒绝是否是正确保守行为；未直接宣称产品缺陷或修复。

正例 `/tmp/sdk-runtime-entry-sampler-qddqt88l/sampling-evidence.json` 外部原token在真实碰撞后发布，业务1、execution succeeded。新增测试线程退出前现在核对publisher全部结束；未退出则保留runtime/activation所有权并报告失败，独立审查指出的提前关闭风险已修订。该范围无模型请求、无新产品候选，不关闭G05/G06/G18；新增负例的截止假设仍未通过，不能计入绿色回归。

## G05/G06 当前包返工路由定向补验（2026-11-06）

只读预检 `verify_agent_rework_route_native.py` 与当前cleanup-diagnostic安装包未发现具体过时接口或误通过阻塞。它核对实际root工具调用、两成员及reviewer身份、指定成员返工、反馈来源、关闭前后稳定返工重放、原预算/子级准入和准确清理；明确只是route切片，不覆盖完整planner及G06全部负例。3600秒为可配置默认，不是本切片验收要求。

冻结验证器 `/tmp/sdk-rework-current-verifier-20261106/scripts`，当前输出 `/tmp/sdk-cleanup-diagnostic-rework-route-20261106`、句柄82308已退出1。提交前声明600秒预算、保持不变；启动预计4–8分钟，到期失败不延长，不恢复此前失败Run。最终report failed/stage=root_run/error_type=TimeoutError/checks为空，host_close_completed=true；不宣称切片或G05/G06通过。

只读现场：root ec2f4e6539544d0da63d092a894e440b最终recovery_required，runtime effect indeterminate；两初始coder、首次reviewer05cde9d74de04b8a872890086117c606及返工coder58a76f06ca5a4abd8e76ada627799375 succeeded。第二reviewer edbdceabe588439092bce2cc3c2cb073最终cancelled，无runtime effect且未进入adapter（共5次adapter entry）。第二reviewer持久诊断为phase=child_wait/type=BudgetClockUnknownError，root同阶段TimeoutError，之后agent_group_call AdmissionCancelled。不能把排队/提交当作原reviewer已消费新结果；预算未知原因仍需独立追查。宿主关闭完成也不等于root不明业务效果被解决。

独立只读追查定位更早入口故障：第二reviewer于1793933146.065提交、3149.510领取/Kernel started，距原截止尚约141秒；entry_state仍pending/attempt1/fence1，无handler_entered。3150.855已捕获BudgetClockUnknownError，3151.288写入late_thread_fact/completion_time_known=false，距截止尚约136秒。后来到期才因Kernel control lock admission timed out被cancelled，child_wait诊断更晚于3287.613。不能归因为模型慢或600秒不够，也无证据归因为session准入；原始预算未知原因/入口位置未保存，尚不能证明具体修复。下一步应在新建本地并发入口复现中保留预算采样/入口的脱敏位置及准确未决采样状态，不恢复本现场、不放宽预算。

## G04 owned-decision故障定位准备（2026-11-06）

只读证据中候选completed_at=1793931898.550早于原deadline=1793931982.588及保存lease expiry=1793932018.208，候选effect集合与准确committed effect一致，准确admission/intent存在；这些不能证明决策时钟、内存owner或captured-return权限当时有效，不据此绕过StorageIsolationError。原始具体拒绝位置未保存。

重投验证器新增可撤销的结算观察包装，仅捕获最终 `_complete_live_owned_candidate` 异常的SDK有界脱敏类型/位置，不改调用参数、重试权限、截止、结果或异常身份；诊断写失败不遮蔽原异常。4项本地观察测试通过0.231秒。现有完整结算竞争模块13项通过26.751秒，`/tmp/sdk-owned-completion-current-20261106.log`，覆盖写锁/生命周期锁、原截止、停止、不明失败不重试及提交响应丢失；该源码局部回归未复现真实G04失败，不算修复或安装包验收。产品候选未变。

带观察的原场景冻结于 `/tmp/sdk-redelivery-diagnostic-verifier-20261106/scripts`，真实输出 `/tmp/sdk-cleanup-diagnostic-redelivery-observed-20261106`、句柄38723已退出0；报告controlled_redelivery_passed/stage=closed，4调用/16模型轮次，准确原生清理核对通过，未捕获completion-failure。启动预估2–4分钟，保持原240秒预算。新成功不诊断或关闭旧StorageIsolationError；旧失败仍是G18未解决回归。

独立只读审查确认，与cleanup-diagnostic-graph/G04.json组合足以覆盖Goal G04，范围为当前安装包Linux x64/Python3.12.3：原生双生产者/消费者、输入未齐禁止启动、实际租约到期generation1到2且lease不同、同消费结果/绑定/准确effect、消费者一次、第二回执确认；不同内容冲突负例在底层原语拒绝且原事件/回执未变。新场景四执行均Kernel succeeded/effect committed/准确cleaned回执/资源released，正常上下文关闭后才stage=closed。此为受控确认前故障及实际重投，不代替G14进程崩溃验收。G04当前场景通过与G18旧间歇缺陷阻塞分别记录。

## G04 当前包事件重投补跑未通过（2026-11-06）

`/tmp/sdk-cleanup-diagnostic-redelivery-20261106/report.json`，当前cleanup-diagnostic安装包、原240秒预算、句柄87955退出1。报告stage=failed/status=incomplete，run.wait抛AgentExecutionError，退出附带_ContextCloseError/cleanup_unconfirmed=true。不重启、不改预算、不以此前旧包通过关闭本候选G04。

实际SDK租约到期后generation1到2、lease不同、消费结果相同、第二次first_consumption=false、最终acknowledged=true、consumer_entries=1，均已记录；但任务链终态未完成。只读现场确认四份原生操作cleaned、四个runtime effect committed，前三执行succeeded，消费者 `6907122d2dae47278b06b172c41c577b` 仍Kernel running/Agent submitted。原生清理和effect提交不替代Kernel完成/Agent投影及宿主关闭；该失败需要继续定位结算阻塞，尚不归因于模型、重投或存储。原报告和存储保持。

独立只读追查进一步定位最早持久失败：准确消费者结算的 `_sdk_completion_decision_error` 为StorageIsolationError/phase=owned_decision。effect于1793931898.369提交、资源1898.445释放，attempt1/fence1于1898.569留下pending late_thread_fact/outcome=ok。runtime.py的恢复路径只把late_thread_fact作为事实，不据此授权终态CAS，因此等待/关闭未知有对应原因；原始StorageIsolationError底层原因和栈未保存，根因仍待定位。下一步为该owned-decision边界的脱敏因果诊断及并发结算确定复现，不能直接写终态或把事实提升为权限。

## G03 当前安装包真实验收通过（2026-11-06）

同一cleanup-diagnostic候选 `/tmp/sdk-cleanup-diagnostic-graph-20261106/{acceptance.json,G03.json,G04.json}`，02:19:16Z–02:21:45Z，约149秒。G03 passed、G04 partial，组合命令按partial退出1；不将组合描述为全部通过。四次真实Agent执行、4调用/19模型轮次，消费者在两输入齐备后才执行，实际消费命名文件快照得到FAST_NATIVE|SLOW_NATIVE。

独立只读审查确认：准确fast工作目录有允许result.txt写入、越界路径的_parts拒绝及预期符号链接的_open_beneath/ELOOP拒绝，外部内容未改；实际路径替换竞争210次替换、允许和拒绝均发生，worker停止、无错误、外部内容未改。四执行均succeeded、effect committed、准确身份匹配cleaned回执及资源released证明。G03范围为Linux x64/Python3.12.3及已声明的根目录/祖先由宿主管控的FileTools范围，不冒充强隔离。此前初始化失败未由此次成功诊断或修复。G04事件重投另以当前包真实探针核对，不凭本图场景关闭。

## 清理未知恢复宿主退出的诊断修订（2026-11-06）

对上一真实现场只读追查发现，验证器将worker stderr送入DEVNULL，无法从退出码1确定异常来源；产品host在停止时发现恢复必需/隔离工作会主动抛HostError（host.py的停止循环），但不能仅凭该分支将此前两次退出归因为预期行为。未新增模型请求、未改写或重启原现场。

验证器新增worker退出观察：仅持久化SDK有界脱敏异常类型及包内位置，不保存异常正文、凭据、会话内容；每进程独立文件，并在最终报告列出文件名。诊断失败仍原样传播原异常，不改变退出码或验收谓词。`tests.test_agent_cleanup_probe_exit` 三项通过，0.202秒，覆盖原异常身份/私密消息排除、诊断写失败不遮蔽、成功路径不写失败证据。此为验证器诊断修订，产品候选不变；尚未取得这两次退出原因的新真实证据，不关闭G12/G16/G18。

## G12 补证审查与下一真实故障窗口（2026-11-06）

独立只读审查确认 `/tmp/sdk-g12-native-retry-current-20261106/report.json` 的12项通过有冻结验证器及准确持久记录支持：一次身份匹配的 not_launched 后仅一次真实原生执行并取得 cleaned 回执；原请求、截止和计费不变；耗尽负例两次准确 abort、原失败提交、模型计费0，稳定请求重放不新增执行。此结论不关闭原两秒失败或整个G12。

清理回执缺失验证器预检未发现具体接口或误通过阻塞：仅在真实guard清理返回true后故意不出具回执，观察标记不作为清理权限；要求原准确操作与资源保留、两次重启后继续隔离且不重放，以及无关调用准确清理成功。当前候选补跑输出为 `/tmp/sdk-g12-cleanup-unknown-current-20261106/report.json`，运行句柄90749已退出0，报告passed且10项检查全部true。启动时预估3–6分钟，原观察上限600秒、原请求预算120秒不变。

原调用 `5d93de7addc548b7bdda7be00883102a` 的操作 `1e20d67c5dc34c589d14a0c5827bf787` 保持authorized/receipt=null，effect为indeterminate、执行为recovery_required，资源保留；同会话后继无执行，两次重启不新增原请求发送，原身份/配置/截止/已花预算未重置，无关会话成功并有准确清理。故障宿主退出32，独立监督报告cleanup_confirmed=true；这不授予SDK缺失的原生回执权限。

独立只读审查确认上述范围，另明确两处限制：恢复快照中后继已过原截止并cancelled，不能据此证明仍可运行的排队请求在整个重启期间持续保留；两个恢复监督均确认进程收容，但root_exit=1，不能描述为正常优雅退出。观察标记不替代准确清理回执。本补证不关闭整个G12/G16、原两秒失败或正常宿主退出要求。

## G12 当前安装包：安全技术重试补证，整体未通过（2026-11-06）

同一 cleanup-diagnostic 候选完整技术重试模块17项16通过/1失败、0错误/跳过，143.361秒，`/tmp/sdk-g12-current-tests-20261106/{technical-result.json,technical.log}`。原两秒用例未进入适配器（adapter_calls=0、boundary_reached=false），未达到post-abort前提；现场 `/tmp/sdk-prelaunch-deadline-failure-in4fb4ut/evidence.json`、`/tmp/sdk-prelaunch-deadline-state-trgr7i6q` 及线程记录目录 `sdk-prelaunch-deadline-threads-fvv2avol` 保留。原期限、断言不变，不能用独立40秒用例或其余16项覆盖本失败。

修正真实重试验证器的过时故障点：套接字获取异常现必须unknown，不能充当安全重试证明；注入改为 `_prepare_native_workdir`，发生于任何guard/socket/Popen之前，第一次EMFILE后调用原方法，耗尽负例保持两次准确abort。原始请求/预算/身份/工具代次/严格输出/清理及不重放检查全部保留。源码启动前4项预检通过0.871秒内；独立审查无具体阻塞，未运行模型或测试。

同候选真实探针 `/tmp/sdk-g12-native-retry-current-20261106/report.json` passed，12项检查全部true且host_close_completed=true。首次准确not_launched，随后实际OpenCode返回RETRY_OK、准确原生清理及普通效果提交；技术重试仅1次、原Agent计费1、首次模型计费0、请求/截止/工作目录/预算不变、工具权限刷新。独立耗尽调用原失败及SDK完成保存、模型用量0，稳定请求重放未新增执行。此报告只证明安全技术重试和耗尽负例，不代表HTTP/提交后重试或G12全项通过；真实unknown/业务返工及原间歇失败继续单独核对。

## 当前候选总览（2026-11-06，cleanup-diagnostic）

产品候选固定为 `/tmp/sdk-cleanup-diagnostic-candidate-20261106`。此表优先于下文旧候选历史，passed范围为Linux x64/Python3.12.3；其余平台不可据此通过。

| 验收ID | 当前候选状态 | 证据或剩余要求 |
| --- | --- | --- |
| G01 | passed | cleanup-diagnostic-config 的 G01.json |
| G02、G05–G08 | 本候选验收未齐 | 旧包真实通过记录保留，尚未升级为本候选全部适用场景证据；G05/G06缺口保留 |
| G03 | passed | cleanup-diagnostic-graph，真实文件拒绝/路径替换及下游消费，准确清理独立审查；历史初始化失败仍未诊断 |
| G04 | passed，历史回归仍阻塞G18 | graph + redelivery-observed当前组合及准确终态/清理独立审查；前次StorageIsolationError未根治 |
| G09 | passed | cleanup-diagnostic-g09-plain，17项及准确清理独立审查 |
| G10 | passed | cleanup-diagnostic-g10-fixed，22项、真实重启/队列恢复/跨Run取消及准确清理独立审查 |
| G11 | passed | cleanup-diagnostic-g11，冻结配置/知识权限及冲突、准确清理独立审查 |
| G12 | 未完成 | 原两秒post-abort前提间歇失败及完整失败分类/禁止重放证据仍需闭合 |
| G13 | passed，仅能力合同与拒绝 | cleanup-diagnostic-config 的 G13.json；原生强隔离后端未提供、真实隔离未验收 |
| G14–G17 | 本候选验收未齐 | 当前包完整故障窗口、原预算/硬token覆盖、停止撤权/竞争/未知清理、CLI/监督/资源/旧API范围仍需逐项核对 |
| G18 | 未通过 | 当前包全回归、sdist与全部适用平台矩阵、双语文档检查和未解决故障审查尚未齐备 |

不存在“整个目标只剩3项失败”的有效结论。已通过范围与未解决的历史间歇清理/服务等待/SIGSEGV分别记录；目标保持active，不宣称可发布。

## G11 当前安装包真实验收通过（2026-11-06）

`/tmp/sdk-cleanup-diagnostic-g11-20261106/{acceptance.json,G11.json}`，01:56:23Z–01:58:34Z，约132秒，当前候选Linux x64/Python3.12.3 passed。旧调用先进入门闩，配置更新后新调用使用新提示/tags/版本，旧调用释放后仍使用原提示/tags/版本；两个不同SDK Run均成功。准确调用诊断确认各自版本1读取、旧调用写入拒绝、新调用写入/读取版本2及过期版本冲突；历史INITIAL v1和当前UPDATED v2保持。

独立只读审查对照Goal G11无具体缺口；两次执行effect均committed，原生清理回执准确匹配execution/lease/attempt/fence，资源均released且证明包含相应回执。未重复测试/模型或恢复现场。此项不证明其他平台或此前unknown根因已解决。

## G10 当前安装包真实验收通过（2026-11-06）

同一候选 `/tmp/sdk-cleanup-diagnostic-candidate-20261106` 的真实 G10 passed，Linux x64/Python3.12.3，`/tmp/sdk-cleanup-diagnostic-g10-fixed-20261106/{acceptance.json,G10.json,foreground-crash-marker.json}`，01:51:00Z–01:52:52Z，约112秒。22项必需检查全部true，无缺项。独立serve进程、客户端退出后继续接收、正常宿主重启后同服务/原生会话续接、多个不同SDK Run的原预算、准确已提交效果后的宿主退出27及命令尚未创建的队列、重启续接原请求身份/期限/用量，以及跨Run取消隔离均有真实证据。

独立只读审查对照 Goal G10 与冻结验证器无具体缺口：7个成功调用分别具备准确effect/lease/attempt/fence匹配的cleaned回执、SDK完成回执，持久资源记录全部released且含原生清理证明；排队取消调用Agent/model用量均0，其他会话正常成功。故障宿主一般descendant_cleanup仍明确unknown，准确SDK回执只证明已记录原生操作，不宣称任意子进程清理或此前SIGSEGV根因已修复。审查未重复模型或测试。此前未转发观察结果的失败夹具现场保留；该修复仅涉及验证脚本，不改变本次产品安装包。

## G09 当前安装包真实验收通过（2026-11-06）

同候选首次真实G10失败报告 `/tmp/sdk-cleanup-diagnostic-g10-20261106/{acceptance.json,G10.json}`：普通三次请求、客户端退出后宿主存活、正常宿主重启、原服务/会话及独立 Run/预算等10项检查true；崩溃恢复及跨Run取消未到达。故障宿主第一条请求Kernel已succeeded、native cleaned而Agent仍submitted，第二条accepted，未产生crash marker。根因定位到内嵌故障包装器 `finish(identity,state,result)` 未兼容 AgentApp 在 terminal_hook 开启时传入的 `_observed_result`；包装器进入前即参数绑定失败，不能投影成功及触发预定崩溃。原预算不变、未重启；场景原620秒故障观察窗口后失败退出。第三个故障宿主最终SIGTERM退出，报告明确descendant_cleanup=unknown，不当作清理成功。

验证器现仅补包装器 **kwargs 并原样转交 original，成功/准确effect/待处理命令等崩溃前提全部保留。编译实际内嵌包装器的接口测试确认 `_observed_result` 对象原样传递，完整场景复用模块5项通过0.099秒，`/tmp/sdk-g10-fault-host-contract-20261106.log`。此为验收夹具修复，不是G10已通过；新的真实崩溃恢复证据仍需取得。旧报告/冻结脚本/现场保留不改写。

候选 `/tmp/sdk-cleanup-diagnostic-candidate-20261106` 的真实 G09 passed，Linux x64/Python3.12.3，`/tmp/sdk-cleanup-diagnostic-g09-plain-20261106/{acceptance.json,G09.json}`，01:33:15Z–01:35:57Z，约162秒。17个必需检查全部true，无缺项：两并发调用者、同键续接/FIFO、不同键重叠及私有目录隔离、独立 Run/预算、队列满、reject、replace_pending、cancel_and_replace 均有真实模型执行及严格输出证据。

独立只读审查对照 Goal G09 及冻结验证器未发现缺口。准确取消原调用具有同 lease/attempt/fence 的 not_launched 回执、committed effect、Kernel cancelled 与资源释放；原资源1793928937.867释放后，替代请求1793928940.405才取得资源，最终 succeeded、准确 cleaned 回执及资源 released，严格返回 REPLACEMENT。另六份原生操作同样核对准确回执/effect、提交成功结果与资源释放。审查未重复模型或测试。此结论仅关闭该候选该平台 G09，不诊断或消除之前的 NativeCleanupUnknownError/停止超时/SIGSEGV，不代表G18完整回归通过；失败现场全部保留。

后续 G10 使用同候选与独立冻结验证脚本 `/tmp/sdk-g10-current-verifier-20261106/scripts`。仅将固定词提示明确为无标点，严格断言及预算不变；既有验证器6项本地检查通过0.101秒，`/tmp/sdk-g10-verifier-preflight-20261106.log`。G10需以自己的真实终态报告判定，不能继承G09。

## 清理失败诊断缺口修订（2026-11-06）

诊断修订已冻结安装为 `/tmp/sdk-cleanup-diagnostic-candidate-20261106`。包外13项全部通过、0跳过、5.386秒，候选目录 diagnostic-result.json 与 `/tmp/sdk-cleanup-diagnostic-installed-20261106.log`；实际守护、宿主崩溃回收、回执负例、启动前故障及 AgentApp 诊断持久化均覆盖。G01及限定G13通过，`/tmp/sdk-cleanup-diagnostic-config-20261106/acceptance.json`。源码首次9项有3个错误，原因是简化 Context 缺新增取消检查要求的 cancelled 方法；补齐返回False后9项通过3.744秒，原未启动/unknown断言不变。源码实际守护四项通过1.318秒。独立复审在普通支持范围无阻塞，未独立运行测试。

本候选真实G09使用每25秒线程转储，验证进程以SIGSEGV/退出139终止，未生成 acceptance.json/G09.json；日志 `/tmp/sdk-cleanup-diagnostic-g09-20261106.log`，状态目录同名前缀无.log。该执行不构成任何G09通过证据。最后转储截断于其他线程 pathlib 位置，不足以定位原生崩溃原因，不能归因于SDK、CPython、诊断或环境。保持现场、不启动重复模型运行；后续需读取系统崩溃记录及确认原生守护清理，不能因进程消失推定资源已清理。

后续离线调试：系统 `/var/crash/_usr_bin_python3.12.0.crash` 确认 Python3.12.3/SIGSEGV，时间09:25:30。临时解包GDB及所需库（未系统安装、未修改项目依赖），禁自动加载/联网符号/参数打印后读取已有CoreDump，栈保存在 `/tmp/sdk-crash-debugger-20261106/native-stack.log`。实际故障线程 LWP526810 位于 `_Py_DumpTracebackThreads`，与主线程 LWP526809不同；这是观察到的故障位置，不证明此前内存损坏不存在。后续真实验证移除外加周期性 faulthandler，仅保留产品有界持久诊断；不将本轮崩溃算作业务通过。宿主命名空间只读进程检查无匹配本候选/guard/OpenCode进程，不替代准确清理回执。

对新失败的只读审查确认最早持久错误为 NativeCleanupUnknownError，随后 effect indeterminate/Kernel recovery_required，宿主停止超时为后续故障；现有记录不足以确定 socket/guard/process/回执中的具体失败。未恢复或改写该现场，未新增模型请求。

工作区新增 runtime failure_locations：记录有界异常图，包括 SDK 清理包装器并列的 body/cleanup 异常，只保留内置/SDK异常类型和SDK包内文件名/行号，不保存文本、源码、局部变量、外部动态文件名或函数名；外部异常类型归为 AdapterError。普通诊断读取失败回退为原错误类型，不改变原业务失败分类；保留 BaseException 中断传播策略。异常图最多16项、每项最多遍历16帧，清理错误最多读取16项。独立审查指出动态文件名/类型与辅助诊断遮蔽问题后补充防护；最新修订尚待复审及集成验证。

4项本地诊断测试通过、0跳过，`/tmp/sdk-runtime-failure-locations-20261106.log`：真实 native cleanup 包装器并列原因保留、循环/大量原因有界、异常属性读取失败回退、动态文件名及异常类型不泄漏。仅辅助诊断单元证据，不是实际清理缺陷修复；本修订未构建安装包，不能继承旧候选验收。

## 当前取消修复安装包（2026-11-06）

修正提示后的真实 G09 未通过且未到达取消替换：`/tmp/sdk-prelaunch-cancel-g09-exact-20261106/acceptance.json`，01:11:58Z–01:12:52Z，约54秒。首组服务场景退出时报 OrchestratorHostTimeoutError，位置 AgentApp._close_before → OrchestratorHost.stop；未生成 G09.json。没有取得当时线程/停止报告内容，不能推断只是标点问题或认定宿主已清理。原状态保留；只读提取的任务/效果/资源状态另存同目录 terminal-state-summary.json。未再次启动模型重跑。

此前153秒运行的独立只读审查核对了准确持久记录：原调用 attempt1/fence1 的 not_launched 回执与 lease/effect匹配、effect committed、Kernel cancelled、资源于1793927244.789释放；后继于1793927248.932获取资源，随后 succeeded 且原生清理回执/资源释放匹配。因此该次取消替换生命周期有实证，但整项 G09 仍因严格输出不符为 failed。此结论不覆盖上述新宿主停止失败。

本候选真实 G09 已执行结束，`/tmp/sdk-prelaunch-cancel-g09-20261106/{acceptance.json,G09.json}`，01:05:15Z–01:07:48Z，约153秒。17项检查16真/1假、无缺项，整体仍 failed。原调用 `1b268afff53b4ed0a3cde73aa483d3ad` 准确 cancelled，记录 cancelled_before_native_acquisition 及操作 `e577c85ab2994fd6ac4f6e85b9b31023`；后继 `2e50bec12876451fb89055e7832c2c9a` 实际进入原 SDK 适配器、独立 Run succeeded、会话最终无 owner/隔离。唯一失败为严格输出：实际 `REPLACEMENT.`，要求 `REPLACEMENT`。原提示 `Reply exactly REPLACEMENT.` 含尾部标点歧义；工作区仅将该提示改为明确单个 token、无标点，严格断言不变，尚未取得新提示真实证据。保留原 failed，不以局部修复或模型已响应改报 passed。

新候选 `/tmp/sdk-prelaunch-cancel-candidate-20261106` 已冻结构建并独立安装，包含协作取消及准确 OpenCode 启动前取消证明。G01 与限定 G13 通过，`/tmp/sdk-prelaunch-cancel-config-20261106/acceptance.json`；G13仅能力合同和拒绝范围，不代表提供原生强隔离后端。包外执行同32项组合全部通过、0跳过，130.822秒，候选目录 `installed-result.json` 与 `/tmp/sdk-prelaunch-cancel-installed-20261106.log`，导入来自候选 site-packages。原服务重启间歇失败保留，当前成功不作为根因修复。该候选不自动继承旧包 G02/G04/G07/G08 等真实验收；G09需本候选独立实际执行结果。

## 最新源码验证：启动前取消与服务重启失败（2026-11-06）

原32项组合另一次保持相同用例、预算与超时，新增每25秒全线程转储后全部通过，118.057秒，`/tmp/sdk-service-combination-stacks-20261106.log`。无产品修改、无模型调用；原失败仍保留，不能将本次成功视作根因修复。转储为整个组合固定周期采样，出现于其他用例及服务重启构造阶段，不能直接当作原失败时的锁所有者。报告末尾 G03/G04/G05/G06 failed/partial 为验证器负例用例预期输出，不是此次真实模型验收。

当前源码增加 OpenCode 启动前明确取消的准确未启动回执：仅 SDK 自身 OpenCodeAdapter 且绑定原始 execute 方法可使用；仍须原执行 lease/attempt/fence、原截止、显式取消及完整资源清理证明。自定义适配器和被替换 execute 的同类型实例不能据此证明未启动。启动后或清理不明的取消继续保留 unknown/隔离，不凭原生记录为空放行。此修订尚未构建安装包，不关闭 G09。

定向源码测试：真实 SDK 方法的启动前取消及自定义适配器拒绝，2项通过、7.347秒，`/tmp/sdk-prelaunch-cancel-bound-method-20261106.log`；替换 execute 拒绝，1项通过、3.602秒，`/tmp/sdk-prelaunch-cancel-overridden-20261106.log`。无模型请求。

受影响源码组合32项，31通过/1错误，155.569秒，`/tmp/sdk-prelaunch-cancel-source-group-20261106.log`。错误为 `test_restart_idle_session_stop_and_configuration_generation`：重新打开服务后第二次 Run.wait(30) 无法取得应用锁，退出另报告上下文清理失败。未获得当时线程栈，根因未知；不能因其他31项通过而关闭。保持原参数的单项诊断8.433秒通过，`/tmp/sdk-service-restart-stack-20261106.log`；20秒线程转储未触发，没有证明原组合故障消失，也不覆盖原失败。后续应在组合现场保留线程和锁所有者证据，而非重复单项刷绿。

## 当前安装包验收索引（2026-11-06）

工作区新增协作取消修复，尚未构建新的候选包：`recovery.cancel_grace_seconds`默认2、非负整数、0立即SDK取消；仅准确本地执行/attempt/fence/lease匹配且原请求未到期、未撤权、未关闭时，让处理线程在不重置的有界时间内结算。普通及协调器路径共用检查；不额外授予工具、模型或原生启动权限，不修改原预算、既有SDK取消或未知隔离规则。双语Wiki/default JSON及文档同步，默认JSON实际比对通过：`/tmp/sdk-cancel-grace-wiki-defaults-20261106.json`。

确定性门闩复现原回收竞态：修复前原Agent为recovery_required，`/tmp/sdk-cooperative-cancel-gated-baseline-20261106.log`；修复后普通/协调路径均能取消原Agent，并在准确已提交effect、原返回值保留、Kernel已有终态结果及本地资源释放后启动替代请求。原过严的Kernel=succeeded断言失败保留于`/tmp/sdk-cooperative-cancel-services-20261106.log`：取消可在effect提交后赢得Kernel终态cancelled，不能要求底层一定succeeded。修正断言仍要求原真实输出与终态结果。新增零宽限未知隔离、非默认7秒、不重置、撤权/原截止/变化fence负例；首版不一致测试快照被ContractValidationError拒绝，日志`/tmp/sdk-cooperative-cancel-boundaries-20261106.log`保留，修正为自洽的新lease/fence后通过。最终配置与服务两个完整源码模块20项全部通过、0跳过、94.582秒：`/tmp/sdk-cooperative-cancel-services-final-20261106.log`。独立静态复审无阻塞，未独立运行测试。本轮无模型请求、CI或发布。

该修复只证明合成适配器的确定返回，不证明真实OpenCode未提交/已清理取消可结算；G09依然失败，下一步需真实适配器的准确启动前取消证明及清理路径。新源码未安装包验收，下述wait-unknown候选不含该修复，不能继承为新源码全部G01–G18通过。一次错误地从源码运行G01被验证器正确拒绝（`/tmp/sdk-cancel-grace-config-20261106/G01.json`，reason=use an installed wheel outside checkout），不当作配置功能失败或有效安装包验收。

G09当前真实执行失败，原证据`/tmp/sdk-current-g09-20261106/acceptance.json`及G09.json保留。会话续接、不同键隔离/并发、FIFO、队列满、reject及replace_pending全部检查为true；cancel_and_replace的original_cancelled/cancel_replace_output为false，原调用recovery_required，替代请求隔离至原预算到期。独立只读定位：原effect runtime:6ff055eb430843b6a0062d2956b05b6a在1793924164.6199274为performing，取消在1793924165.2620423将其变为indeterminate（effect_outcome_uncertain/trigger=cancel），准确执行进入recovery_required且目标cancelled，无完成结果。同attempt/fence迟到事实为handler_failure_unknown，原StaleFenceError且失败观察出现StorageIsolationError。原生所有权记录为空，但不能据此推断清理成功或解除会话隔离。原始OpenCodeError原因和物理资源清理尚未知。修复应处理application._reconcile_one直接runtime.cancel与在途effect结算的协调，需准确未启动/清理证明及受支持的效果处理路径；不得直接修改内部数据库、跳过fence或自动重放。

G10执行前验证器修正：cross_run_cancellation的取消标志规范化为bool，所有false值判失败，并列出22个必需检查，缺失仍not_run。独立只读复核未发现阻塞；语法及既有6项验证器测试通过0.128秒，不代表G10业务验收。尚未执行新的G10模型调用。

G07现已由修正后的同一安装包真实执行闭合：`/tmp/sdk-current-g07-attributed-20261106/acceptance.json`及G07.json，00:10:03Z至00:13:22Z，约200秒，3次Agent调用/18模型轮次。根调用身份70bbc555791b4e2788401d8998c409ca逐次绑定self_wait/agent_wait_cycle及denied/agent_permission_denied；call、send和wait的返回身份均属于根调用，重复call复用同一子调用，两个子产物及组合产物准确，三个invocation及SDK Run成功，控制器父级限制和准入effect匹配。独立只读审查对照Goal G07及冻结验证器确认该行证据充分，无重跑；不扩展为其他ID通过。下段旧G07局部证据保留，不替代本次结果。

G09执行前审查修复两项验证器误判风险：取消标志0现按false处理；cancel_and_replace必须验证原调用cancelled、替代调用实际进入适配器、替代Run成功及准确REPLACEMENT输出，不能只凭排队/隔离状态通过。增加必需检查集合，缺失检查仍not_run。独立复审无新增阻塞；语法检查及已有6项场景复用/诊断/文件证据测试通过0.164秒，这6项不覆盖G09业务。尚未运行修正后的真实G09，不声明其验收通过。

G07当前真实执行为部分证据，不能按脚本passed直接关闭：`/tmp/sdk-current-g07-20261106/acceptance.json`和G07.json，2026-11-06T00:03:34Z至00:06:58Z，约204秒。3次Agent调用/17模型轮次，根及两个子调用均succeeded，call/send分别返回CALL_NATIVE/SEND_NATIVE、重复call复用同一invocation，父子归属、准入effect和控制器预算限制均匹配。根诊断有agent_wait_cycle及agent_permission_denied，但旧观察器仅全局记录self_wait/denied错误，未逐次绑定调用者及错误码；独立审查认为对应关系虽吻合仍不充分。工作区观察器现记录caller_invocation_id及ToolCallError.code，并将所有call/send/wait及指定负例限定根调用；独立复审无阻塞，语法检查通过。原运行快照/报告未改，修正后的真实负例尚待验证，不把本项报为完整G07通过。

补充原预算到期后的禁止重试证据：同一wait-unknown安装包在包外执行独立40秒声明用例，1项通过、41.683秒，`/tmp/sdk-post-abort-observed-installed-20261106/result.json`。原始证据 `/tmp/sdk-confirmed-abort-expiry-hm76y9wx/evidence.json`：abort在原截止前38.38秒确认，实际处理线程及重试循环结束后adapter仍仅调用一次；command、operation和两项预算scope均保留原deadline，Agent调用spent=1、模型轮次spent=0。Kernel为recovery_required、effect为indeterminate，未证明cleanup。此项不替换原2秒失败、不延长已接受请求、不关闭整个G12/G18。

G03后续诊断准备：工作区验证器透明观察真实SettlementJournal构造；失败时单独保留异常类型与调用位置，不保存异常文本/局部变量，不修改产品或初始化预算。新增异常身份及敏感文本不泄漏检查，与既有场景复用/文件证据合计5项通过0.088秒。尚未再次运行真实G03，原失败未解决。

最新等待路径候选为 `/tmp/sdk-wait-unknown-candidate-20261106`，由冻结源码构建 wheel 并独立安装。限定13项全部通过，0失败/错误/跳过，42.518秒；证据为该目录 `wait-result.json` 和 `/tmp/sdk-wait-unknown-installed-20261106.log`，SDK导入来自site-packages。范围为未知完成观察、完整AgentApp的Invocation/Run等待、原调用者等待期限及准备期间到期拒绝适配器入口。未知报告不改变持久状态、不授予重试或恢复权限，已观察终态/恢复状态优先；独立静态审查未发现本次修改的阻塞。未重跑原两秒abort失败，未完成技术重试整模块或完整回归，G12/G18仍未通过；下列79项属于上一候选。

同一候选真实OpenCode G02已通过，Linux x64/Python3.12.3，实际调用约29.65秒：`/tmp/sdk-current-g02-20261106/acceptance.json`及`G02.json`。模型经已授权本地反代实际完成SDK file_write/artifact_publish，产物为 `answer=SDK_AGENT_NATIVE_OK`，非空原生会话、底层SDK Run succeeded，8轮上限内实际计入5轮；准确execution/attempt/fence的原生所有权记录cleaned且tree_cleanup=confirmed。宿主凭据仅由资源文件消费，未输出。此项关闭当前候选G02缺口，不覆盖G03–G12或其他平台。

同一候选G01及限定G13复验通过：`/tmp/sdk-wait-current-config-20261106/acceptance.json`、G01.json、G13.json。G13仍只证明能力声明及缺能力时业务前拒绝，不声明原生强隔离。冻结候选source/scripts/check_docs.py由该候选独立环境在包外执行，退出0：578个本地链接、4个README可执行示例通过、0跳过，`/tmp/sdk-wait-current-docs-20261106.log`。此项补齐本候选文档检查证据，完整回归、其余真实验收和平台矩阵仍缺失。

同一候选G04已具备组合验收证据：`/tmp/sdk-current-g03-g04-native-20261106/G04.json`真实双生产者/消费者、输入齐备、稳定请求重放及冲突，与`/tmp/sdk-current-g04-redelivery-20261106/report.json`实际宿主租约到期重投。后者状态controlled_redelivery_passed、stage=closed；一次消费后确认前注入失败，原租约到期后generation从1变2且lease不同，复用同一消费结果、输入绑定、消费者命令及effect身份，消费者只进入一次。最终4个Agent均成功、4次调用/16轮模型请求、四份准确原生清理回执匹配。独立只读审查逐项对照Goal G04未发现缺口；事件内容冲突是独立底层原语负例，重投不是进程崩溃。此项不证明G14或首次初始化失败已修复，不改写上一轮原始G03失败和G04局部passed报告。

同一候选G08已通过，Linux x64/Python3.12.3：`/tmp/sdk-current-g08-20261106/acceptance.json`及G08.json，真实OpenCode场景94.019秒。writer第一次提交DRAFT_NATIVE，验证器返回continue，第二次请求续接验证器记录的原session；同invocation、deadline和state_dir，产物历史为version1/step0到version2/step1的GOAL_NATIVE_FIXED，Agent调用计费仍为一次。blocked及error分别以goal_blocked/validator_execution_failed退出，Agent与Run为failed，准确证据谓词通过，稳定重放不再执行、依赖下游未启动、验证器私有异常内容不进入结果。默认response由同候选G02真实证据覆盖。独立只读证据审查未发现G08缺口，未独立重跑，不扩展为G12/G14/G18通过。

本轮修正新增完整AgentApp测试中的RuntimeResult参数倒置及遗漏会话绑定。原失败 `/tmp/sdk-wait-unknown-source-20261106.log` 保留；修正后未允许本地通信的一次仍返回ToolCleanupUnknownError/recovery_required，记录 `/tmp/sdk-wait-unknown-fixture-fixed-20261106.log`，未将此状态改写为unknown。允许本地通信后单项通过6.181秒，`/tmp/sdk-wait-unknown-fixture-local-20261106.log`，随后上述独立安装包组合通过。此证据使用本地适配器和实际SDK，不替代真实OpenCode验收。

上一较广组合候选为 `/tmp/sdk-budget-batch-candidate-20261106`，包含预算初始化原子合批及提交前全部历史完整性检查。安装包组合79项77通过/1失败/1错误、0跳过，driver159.425秒，`/tmp/sdk-budget-batch-installed-result-20261106.json`及同名前缀日志。完整技术重试模块14/16，原两秒abort前提失败，以及准备期间到期用例等待锁超时；监督重试各项通过。不得把下列旧候选的通过数当作当前完整通过。G12/G18保持未通过。当前候选G01及G13已另行通过：`/tmp/sdk-budget-batch-config-20261106/acceptance.json`；G13仅能力声明/业务前拒绝，无原生强隔离后端或真实隔离验收。

上一影响验证候选：`/tmp/sdk-expiry-refusal-candidate-20261106`。已独立安装并通过受影响的10项取消/启动调度/真实队列恢复测试，0失败/错误/跳过；`/tmp/sdk-expiry-refusal-installed-result-20261106.json`及同名前缀日志，unittest3.912秒、driver4.100秒。SDK导入来自site-packages。此候选的G01–G18完整有效证据尚未齐备；原两秒失败/迟到挂起未关闭，未重跑刷绿。以下表格保留上一个较广验证候选的范围，不能直接作为最新候选全部通过。

### 上一冻结候选的分项证据

候选：`/tmp/sdk-child-entry-marker-candidate-20261106`。以下仅列本候选有效证据；旧候选的真实调用和故障报告保留为历史，不自动继承为本候选通过。已实现与已验收是不同状态。

| 验收 ID | 当前结论 | 原始证据与缺口 |
| --- | --- | --- |
| G01 | passed，Linux x64 / Python 3.12.3 | `/tmp/sdk-current-config-strict-20261106/G01.json`：配置等价、非法配置拒绝、默认值/Wiki及CLI有效配置 |
| G02–G11 | 当前真实执行验收未完成 | 实现和历史报告保留；尚未完成本候选对应的真实模型、下游消费、返工、服务跨Run/重启及其他指定正反例，不能用本地合成测试替代 |
| G12 | 未通过 | 当前完整技术重试模块15/16；原两秒用例未达到post-abort前提。原生业务拒绝、返工与unknown完整证据亦不得由此替代。`/tmp/sdk-child-entry-marker-installed-20261106/result.json`、check.log |
| G13 | passed，仅能力合同与拒绝范围 | `/tmp/sdk-current-config-strict-20261106/G13.json`：strict业务前拒绝，无请求准入/运行时启动。原生强隔离后端未提供、真实隔离未验收；此限定符合Goal第94行及G13 |
| G14–G16 | 当前真实执行验收未完成 | 本候选的崩溃窗口、原预算与取消、停止/竞争/准确清理证据尚未齐备；不得以旧包报告直接提升 |
| G17 | 部分验证，未整体通过 | 当前进程运行模块31/31；旧API/能力八个完整模块组合58项全通过，legacy-contract-result.json及legacy-contract.log。完整CLI/监督/资源准入及其余原API范围仍需完成 |
| G18 | 未通过 | 当前组合112项111通过/1失败，无跳过；sdist已构建并离线安装、G01/G13通过；完整回归、文档全检及Linux/Windows x64/ARM、Python3.10–3.13适用矩阵未齐。当前证据只覆盖Linux x64 / Python3.12.3 |

此表不表示未验收能力均未实现，也不把局部模块错误数当作剩余验收ID数。目标保持active，尚不能标记完成。
<!-- current-package-index:end -->

## 2026-11-06：重复事件验收及验证器异常后重复执行修复

上述当前G04重投由现有冻结候选的`verify_agent_dependency_redelivery_native.py`在独立环境以-I执行，消费真实OpenCode产物、使用SDK自身租约时间及宿主推进；无手工时钟、手工重新提交或直接SQL写入。冲突注入调用SDK put_event并要求拒绝回滚，保留原事件与回执；不把该底层负例当作模型调用。全部证据保留在`/tmp/sdk-current-g04-redelivery-20261106`。

修复工作区主验证器异常后意外重复执行：G03/G04以及G05/G06共用场景如抛出普通异常，现将类型/安全调用位置缓存为失败，第二个ID引用同一失败，不重新运行场景。BaseException中断不吞掉，异常消息/局部变量不进入该报告。图场景内部捕获的异常也补位置。G04只有图通过仍明确partial，完整结论需上述独立重投证据。`tests/test_agent_verifier_scenario_reuse.py`及文件观察证据组合4项通过0.023秒，`/tmp/sdk-verifier-scenario-reuse-20261106.log`；独立静态审查无阻塞，未运行模型或测试。此修复仅涉及验证器，不更换已验收产品安装包。

初始化一次定向探测未复现：`/tmp/sdk-settlement-startup-probe-282db_3r/probe.json`及`/tmp/sdk-settlement-startup-probe-20261106.log`，新AgentApp实际打开/关闭、completion存储available，原journal控制预算0.1秒未修改，观察到构造总耗时0.1141秒。无Agent/模型执行；该成功不证明原失败根因或已修复，未重复探测刷绿。G03首次初始化失败及G12/G18等缺口仍保留。

## 2026-11-06：当前安装包 G03/G04 真实图与精确文件拒绝

产品仍为wait-unknown候选，未修改产品代码。工作区验证器增加仅针对三个固定合成路径的真实FileTools.write观察，调用原方法并原样返回/抛出，不记录内容。路径穿越须实际经过_parts的ValueError；符号链接须在调用前后仍指向指定外部文件，并有_open_beneath返回ELOOP。审查首版指出任意权限/I/O失败误计问题，已修正，实际缺授权及无关EIO负例不会计作符号链接拒绝。`tests/test_graph_file_evidence.py`源码2项通过0.004秒，`/tmp/sdk-graph-file-evidence-final-20261106.log`；独立复审无剩余阻塞，审查者未运行测试。

首次验证快照放在/tmp下一层，来源检查把/tmp内安装包判为checkout范围，两个ID在请求前失败：`/tmp/sdk-current-g03-g04-20261106/acceptance.json`。随后一次相对路径复制在模型启动前失败，其日志 `/tmp/sdk-current-g03-g04-reviewed-20261106.log` 保留。改为正确层级和绝对复制后启动 `/tmp/sdk-graph-verifier-reviewed-20261106/scripts/verify_agent_control.py`，当前安装包SDK仍来自site-packages。

真实运行 `/tmp/sdk-current-g03-g04-native-20261106/acceptance.json` 保留G03初始化失败，异常位置为AgentApp.__init__:825（完成settlement存储不可用）。原始存储初始化原因未被该报告捕获，不能推断锁竞争或宣称已修复。G03异常后验证器因尚无graph_result，在G04分支再次尝试初始化，随后四个真实OpenCode会话成功；该后续成功不覆盖原失败。

成功图证据在同目录G04.json：seed/fast/slow/consumer同一底层Run，slow闸门未放行时consumer未启动，最终消费者实际发布FAST_NATIVE|SLOW_NATIVE。4次Agent调用、19轮模型请求，原240秒/8调用/48轮预算不变；稳定根请求重放未新增执行，内容冲突拒绝。精确fast工作目录中../escape.txt以traversal_validation拒绝、linked.txt以nofollow_symlink拒绝、result.txt允许且内容为FAST_NATIVE，外部文件未变。该次快照仍将G04标passed，但本合同G04重复依赖事件证据并未运行，因此仅算部分验收；工作区验证器现已把此场景G04改为partial，并记录duplicate_dependency_event_redelivery=not_run，未改写冻结脚本或原始结果。

单独补同一安装包的直接FileTools路径替换竞争，无模型重跑：`/tmp/sdk-current-path-race-20261106/report.json`，93次替换、500次拒绝、0允许、无错误、工作线程退出、外部文件未变。允许写入由上述真实图提供；该竞争不是模型工具桥并发竞争或进程级隔离。G03已有业务正反例及竞争证据，但首次初始化失败仍待定位，不将整个组合报绿。G04仍缺当前安装包的重复依赖事件实际重投验证；G12/G18等其余缺口保持未通过。

## 2026-11-06：Run 创建优化审查与工作区文档检查

未采用“根命令已存在则跳过 `_advance_run` 的 create_run”优化。基线探测确认两次推进会调用两次create_run，但当前create_run的重放路径本身是只读事务，仍验证原始创建记录；独立审查指出直接跳过会丢失该处内容/记录一致性检测。未保留产品修改或要求零次调用的实验断言。原基线日志 `/tmp/sdk-plan-create-baseline-20261106.log` 保留，其中另一新增夹具遗漏提示词初始化；修正提示词后又发现未初始化config_version，日志 `/tmp/sdk-plan-commandless-fixed-20261106.log` 保留。最终限定边界测试 `tests/test_agent_plan_run_creation.py` 使用公共AgentStore接口构造无command的已取消计划，确认实际SDK Run创建、取消及计划关闭；源码1项通过1.093秒，`/tmp/sdk-plan-commandless-final-20261106.log`。它不证明性能缺陷或原两秒用例已修复。

当前工作区文档检查器已完整退出0：578个本地链接、4个README可执行示例通过、0跳过。命令为 `.venv/bin/python scripts/check_docs.py --help`；检查器不解析该参数，实际执行了main全检查。此项来自工作区解释器，不冒充当前独立安装包或完整G18验收。

启动清理调度和取消截止拒绝修订现已打包为上述expiry-refusal候选；上表属于此前child-entry-marker候选，不覆盖这两处修订。最新单项诊断再次出现30秒等待超时，见文末“派发耗时诊断与启动扫描调度”；不能据此前四项通过推断全部挂起路径消失。


## 2026-11-06：旧API三模块当前安装包及G01复验

上一轮原7模块加载错误已有当前安装包62项全通过证据，本轮继续原剩余失败。test_execution_kernel_v2_sqlite的实际共存表/连接权限断言不变，仅将新库元数据期望的过时版本12改为KERNEL_STORAGE_SCHEMA_VERSION（当前19）；未改产品或历史库。独立包外快照 `/tmp/sdk-legacy-core-installed-20261106` 在当前 `/tmp/sdk-monitor-effect-candidate-20261106` 安装包运行三个完整模块：66项65通过/1失败/0错误/跳过，96.971秒，result.json/check.log。test_application完整12项、test_execution_kernel_v2_sqlite完整23项均通过；test_execution_kernel_v2_runtime完整31项30通过/1失败。各模块用例名和结果见同一check.log，不升级整个旧API或G18。

剩余失败 test_posix_deadline_cannot_be_caught_and_kills_child_process_group 的 catch-timeout 子测试返回running而非原期望timed_out；20毫秒预算不变，失败原证据 `/tmp/sdk-process-group-timeout-oy4539rk/evidence.json` 及 storage-evidence.json 保留。原生入口拒绝详情含20毫秒cutoff，但准确持久entry仍pending、预算无constraints/start；原始完成采样InspectionBudgetExceeded，cleanup确认不等于结果权限。独立只读审查及主代理核对支持当前未知，不支持从历史native_budget_cutoff字典补写超时或从清理后的观察制造原完成时间。原断言保留，未将该失败改为通过；需要活跃拒绝进入决定的准确租约/截止来源/预算时钟/未调用证明及有界原子提交，属于尚未实施的恢复能力，不是简单字段传播遗漏。

同一安装包通过公共验证器G01 unit：`/tmp/sdk-g01-monitor-effect-20261106/acceptance.json` 和G01.json。实际安装包YAML/Python等价、重复键/未知字段/非法构造和覆盖拒绝、双语Wiki默认JSON与字段默认注册表一致、真实CLI validate/effective均通过。仅本机Linux x64 Python3.12.3的G01，不覆盖其他ID/平台。无外部模型调用、CI、完整回归或发布；本轮测试进程均已退出。

## 2026-11-06：原两秒窗口的耗时诊断及脚本闭包复验

上一轮为实质进展：当前安装包锁竞争恢复定向通过；技术重试整模块仍有1项失败。没有因单次成功覆盖整模块失败。新增只记录函数起止的包外诊断 `/tmp/sdk-prelaunch-timing-20261106.py`；原两秒预算及wait(30)不变，未修改产品或测试，未调用外部模型。日志和耗时记录 `/tmp/sdk-prelaunch-timing-20261106.log`、`.json`。本次单项通过3.438秒，abort在原截止前约0.120秒返回；仅用于定位，不据此关闭间歇失败。

观测到 root提交约0.311秒、handler admission约0.082秒、三次cancelled检查各约0.069/0.087/0.088秒、native prepare约0.114秒、abort约0.120秒（含app锁等待）；这些阶段相互嵌套，不能直接全部累加。现有数据没有证明某项权限检查可安全删除或缓存，未为绿色结果扩大预算或改内存存储。原技术重试前提失败继续保留。

另行复验原完整回归7个无法加载模块：使用同一当前安装包和新的包外测试/脚本快照 `/tmp/sdk-script-closure-installed-20261106`。脚本来自候选冻结source/scripts，SDK导入要求site-packages，未将产品src加入PYTHONPATH；完整7模块62项全部通过、0失败/错误/跳过，17.734秒；result.json/check.log保存准确导入来源和完整用例名。该组原加载错误已在当前安装包下闭合，未覆盖其他尚未复验模块。此范围是本地证据谓词、观察器及故障夹具验证，不替代真实OpenCode G05/G06验收。

## 2026-11-06：未完成 effect 与返回锁竞争的定向修复

当前产品已冻结为 `/tmp/sdk-monitor-effect-candidate-20261106` 并独立安装 wheel。包外测试快照 `/tmp/sdk-monitor-effect-installed-20261106` 的 result.json/check.log：13项全部通过、0失败/错误/跳过，18.585秒；导入确认为该环境 site-packages。包括锁竞争真实复现1、权限/期限/SQL中断负例8、线程返回负例2、查询失败后原结果保留1、原技术重试失败单项1。后者本次在原截止前约0.231秒确认 abort；不是扩大预算后通过。补充负例验证调用者私加更紧期限不能使持久预算提前到期，合并时钟下限证明 lease 过期时拒绝停放，提交前实际长 SQL 被中断后回滚且连接可用。

同一安装包技术重试完整模块已退出：16项15通过/1失败/0错误/跳过，102.358秒，`/tmp/sdk-monitor-effect-installed-20261106/technical-result.json` 及 technical.log。原失败单项此次不是 wait 超时：真实 AgentExecutionError 已返回、准确 Kernel 已 recovery_required、adapter 仅执行一次；但 abort 返回在原截止之后约57毫秒，未达到用例要求的“先确认 abort，再等待原截止”前提，故保留失败，不关闭间歇问题。原现场 `/tmp/sdk-prelaunch-deadline-failure-7vj3pxh_/evidence.json` 与状态目录 `/tmp/sdk-prelaunch-deadline-state-_32iu0m2` 保留。该变化证明这次现场未再发生30秒收尾挂起，不证明所有挂起路径已消除。没有重跑覆盖或扩大两秒预算；完整回归仍未通过，当前无本轮后台测试进程。

新增真实 SQLite/SDK 复现，在处理器捕获实际 effect 失败后返回时，暂停于查询锁已释放、返回仲裁锁仍被占用的位置；保留原两秒预算。修复前任务到期仍 running，`/tmp/sdk-monitor-effect-gate-baseline-20261106.log`。新增恢复专用事务只允许活跃前台 monitor 将准确 lease/attempt/fence 的未完成 effect 停放，不提交成功/失败结果，不取消、不续期；仍保留物理线程和迟到结果义务。仅原到期分支且返回仲裁 pending 时使用；时钟未知分支不使用。

事务以持久预算约束及当前持久 Run 限制判定到期，只合并调用者时钟下限，不借调用者私加的截止制造到期；准确 handler admission、可信时间线、未过期 lease 和提交前活跃权限均检查。独立审查指出并修复合并时钟下限遗漏及大 effect 集合/提交前查询的控制时限问题；主体和提交前查询使用 SQLite 中断，逐 effect 检查，清理遵循已有 unknown 连接隔离路径。首版返回值 tuple 误用造成一次未通过，原日志 `/tmp/sdk-monitor-effect-gate-fixed-20261106.log` 保留。

源码定向9项通过、0失败/错误/跳过，15.177秒，`/tmp/sdk-monitor-effect-related-20261106.log`：竞争复现1、权限负例5、线程返回栅栏2、原技术重试失败单项1。技术重试本次 abort 在原截止前约0.336秒确认，未延长原期限。独立最终审查在本次修改范围未发现剩余明确阻塞。单次成功不证明间歇故障彻底消失；当前新安装包验证尚待完成。无外部模型调用、完整回归或CI；G01–G18仍未全部验收。

## 2026-11-06：绝对截止夹具与剩余核心模块安装包复验

本轮没有保留新的产品修改。技术重试探测只证明单次成功，原间歇失败仍待修复；拒绝用原始墙钟把根任务强制cancel替代monitor权限。撤回实验及原失败证据继续保留。

修正测试：test_agents_absolute_deadline改准确tests包导入；旧命令拒绝重开夹具不启动真实后台host，避免手工queued命令被提前执行。关闭后用真实Kernel验证准确原command仍queued且无result，再要求两次拒绝重开，未放松接受条件。独立只读分析指出原夹具后台竞争，未证明产品preflight绕过。test_execution_kernel_v3_managed_gate补齐v14→v19的已有升级链；test_copied_legacy_terminal_readback复制升级目标引用当前KERNEL_STORAGE_SCHEMA_VERSION，并验证目标未产生历史copied-legacy witness。首轮误用不存在的常量名造成加载错误，日志/sdk-remaining-core-fixtures-fixed-20261106.log保留，已纠正。

四个完整模块源码33项通过27.829秒，`/tmp/sdk-remaining-core-and-deadline-fixed-20261106.log`。同一最新产品包`/tmp/sdk-thread-return-candidate-20261106`配合新的包外测试快照`/tmp/sdk-core-deadline-fixtures-installed-20261106`复验：33项全通过、0失败／错误／跳过，30.877秒，result.json及check.log。范围包括原application_budget、managed_gate及copied_legacy_terminal_readback失败，不升级其他旧模块／全部G18。未重建产品、未改旧冻结测试、未调用模型、未运行CI或完整回归；所有本轮测试进程已退出。

## 2026-11-06：线程返回修复当前安装包结果

冻结当前产品并独立安装`/tmp/sdk-thread-return-candidate-20261106`，包外快照`/tmp/sdk-thread-return-tests-20261106`。26项25通过／1错误／0跳过，117.857秒，result.json及check.log：原child并发与storage contention两个整模块6项、legacy恢复权限负例4项、入口竞争及新增提交前超时等通过。唯一错误为原technical_retries截止后abort单项AgentRun.wait抛Orchestrator caller deadline elapsed；实际abort确认比原截止晚约6.6毫秒，不能宣称达到“截止前确认abort再耗尽”的正例。源码单次通过不覆盖此失败。

新tests/test_thread_return_fence.py源码2项通过7.583秒；同一安装包另行包外2项通过7.480秒，fence.log。真实SQLite写锁持有至原工作截止后不产成功；取消原generation后不被迟到回调覆盖。取消发生在真实采样返回unknown后、回调完成前，未覆盖所有并发取消／reclaim／停止窗口。测试监听包装仅记录和门闩，不替换采样／结果授权。两次执行分别报告，不合并成一次28项。

本候选不新增逐文件／hash检查，product_source_files只表示冻结源码数量，product_files_compared=false。所有测试进程已退出，没有后台回归、外部模型调用、CI或发布。G18及G01–G18仍未全部验收；下一步处理原技术重试窗口及尚未关闭的失败，不能以局部25项代替完整验收。

## 2026-11-06：线程返回采样修订及分离的安装包结果

修订非托管thread成功返回调用点，使用现有serialized完成采样及entered原工作截止：先经写者栅栏，再记录本次返回完成事实；不授予legacy恢复新权限。独立只读审查未发现预算续期或结果权限阻断；明确采样可能晚于业务返回、争用可消耗原窗口，未证明停止立即中断或所有竞态。

修改前同两模块6项3失败；修订后原两模块6项全通过、0跳过，39.209秒，`/tmp/sdk-child-serialized-return-20261106.log`。取消、预留到期和原child只调用一次检查保留。尚缺该修订安装包及新负例，不能宣称全部关闭。

此前冻结的`/tmp/sdk-entry-preparation-candidate-20261106`不含本修订，其包外16项14通过／2失败／0跳过、57.208秒：技术重试未到达adapter边界，以及入口控制锁释放后仍running。`/tmp/sdk-entry-preparation-tests-20261106/result.json`及check.log。该driver未执行产品逐文件比较；result误继承的product_files_compared计数已纠正为false，product_source_files仅表示冻结源文件数，不是比较证据。原失败保留，不以源码单次通过覆盖。

## 2026-11-06：准备阶段到期与取消移交补充证据

准备阶段提前返回的timeout现复用提交前活跃超时决策；仅在线程尚未提交、原冻结预算可信且耗尽时，经原lease及撤权检查处理。源码组合11项通过、0失败／错误／跳过，10.411秒，`/tmp/sdk-preparation-timeout-source-20261106.log`。原技术重试单项在原期限不变情况下实际进入adapter、确认prelaunch abort，随后验证截止后不重试；1项通过3.398秒，`/tmp/sdk-retry-after-preparation-fix-20261106.log`。取消回调先于移交的专门测试1项通过2.728秒，`/tmp/sdk-managed-entry-cancel-handoff.log`，检查原Future所有权及重复清理，无handler或业务结果。

以上为源码定向证据，尚未统一安装包复验或完成回归，不推算总体剩余失败数、不升级G18。无外部模型调用。

## 最新结果（2026-11-06，入口前超时的活跃决策）

源码修订提交线程前绝对截止到期的活跃monitor决策，并让启动等待／入口确认超时使用原monitor仲裁，未决／停止保持准确所有权移交；transfer_late正常及中断补登记均保留Future。独立审查发现的两处移交遗漏已修正，取消与锁竞争专门测试尚缺。新增真实SQLite managed测试用绝对deadline和禁止executor.submit断言证明提交前超时／停止撤权，不伪造业务入口。

更正此前证据推断：原相对时长探针不能证明线程未提交；首次.log仍保留，同名JSON已被重跑覆盖，不能引用为首次现场。新增夹具首轮相对截止错误触发submit断言，改绝对截止后通过。最终源码10项通过9.879秒，`/tmp/sdk-managed-entry-final-source-20261106.log`。技术重试原失败仍等待超时（7项整合中1错误），不宣称原post-abort目标完成。当前修订没有新安装包证据，不升级G18；无外部模型、CI或发布。

## 最新结果（2026-11-06，不确定效果恢复独立安装包）

新增效果查询TimeoutError／OSError注入测试，保留真实managed Kernel及原成功返回、attempt／fence检查；夹具首轮漏correlation_id后纠正，源码通过。新候选`/tmp/sdk-live-effect-recovery-candidate-20261106`独立安装，外部测试快照`/tmp/sdk-live-effect-recovery-tests-20261106`组合12项11通过／1错误／0跳过，62.305秒，result.json／check.log；149个产品Python文件与冻结source直接字节一致。完整控制重开模块、查询失败测试及入口边界通过，补齐本次恢复修复限定安装包证据。

技术重试原截止后中止单项仍因Orchestrator caller deadline elapsed错误，未宣称通过或post-abort完整覆盖。其余当前包验收／全回归仍缺，无后台测试、外部模型调用、CI、推送或发布；全目标未完成。

## 最新结果（2026-11-06，活跃worker不确定效果停车）

修订runtime线程受管理路径：处理器吞下工具失败仍返回成功时，检查本次attempt/fence未完成效果并请求恢复；Kernel在原子事务、精确代次、原截止与既有活跃／停止权限下停车。查询失败只保留有界异常类型并交原有完成检查，不授权成功。独立审查指出首版查询异常处理遗漏，已修正；错误注入分支尚待专门验证。

原控制重开失败单项源码通过11.302秒，整合后全模块2项通过26.429秒、0失败／错误／跳过，`/tmp/sdk-control-reopen-integrated-20261106.log`。测试原不明效果／不投递／恢复状态及重开断言不变。仅源码证据，新安装包及相关负例未验证，不标全部恢复或G18通过。无外部模型、完整回归／CI或发布。

## 最新结果（2026-11-06，原截止修复独立安装包）

已从当前工作区完整冻结构建并安装候选`/tmp/sdk-pre-capture-expiry-candidate-20261106`。包外-I执行native_entry_cutoff及handler_entry_contention，8项通过、0失败／错误／跳过，6.036秒；result.json及check.log。149个产品Python文件与冻结source直接字节一致。该范围补齐采样尝试前原截止耗尽修复的安装包证据，包含真实写者释放、原期限内拒绝业务入口及非争用错误不重试。其他旧候选范围不自动升级为本候选证据。

独立只读分析的Agent等待问题尚待修复／复验：技术重试原现场未达到adapter入口，需在新包重新取得post-abort事实；控制重开涉及不确定效果后成功candidate被拒但未及时转恢复状态，不能用修改wait异常或延长超时解决。未调用外部模型、未运行完整回归／CI、未发布；G01–G18仍未全部验收。

## 最新结果（2026-11-06，采样尝试前原截止耗尽）

原0.3秒入口竞争失败定位后，限定修复精确无采样截止哨兵的分类；所有原截止身份／可信域／经过时间检查保留，带cause、token、sample envelope或pending owner仍未知。保留先前实际争用诊断。独立predicate审查未发现授权阻断，并发现首版遗漏storage_error；修订后源码native_entry_cutoff及handler_entry_contention共8项通过4.272秒，`/tmp/sdk-entry-sentinel-integrated-20261106.log`。首次缺_sample合成夹具错误及真实路径缺storage_error日志保留，不覆盖历史失败。尚无该产品修订新安装包证据，不标G18通过。

先前本机端口补跑已结束，18项2错误0跳过，188.853秒，`/tmp/sdk-agent-child-remaining-20261106/socket-result.json`；控制重开和原截止后中止仍未解决。无外部模型、完整回归、CI或发布。

## 最新结果（2026-11-06，跨存储生命周期及日志投递）

历史跨存储测试原预期Kernel升级目标12，当前实际19；改引用Kernel／Orchestrator当前版本常量，保留v5／v4源库行不变、真实同Run进程生命周期及显式containment断言。当前安装包该完整模块两项通过；与日志交接原单项组合3项首次仍1失败，11.712秒，`/tmp/sdk-split-lifecycle-current-20261106/result.json`及check.log。

日志交接单项缺handler_outcome，代码核对该诊断以timeout_seconds=0非阻塞投递；测试此前在投递确认前打开接收日志。现仅在该单项使用现有_retry_diagnostic_notes有界1秒wait_for_writer并断言无该execution pending，再按原顺序／准确attempt及fence／登记来源／清理证据检查重开日志。未改通用reopen_notes或放松其他用例。

同一当前安装包3项通过、0失败／错误／跳过，10.299秒，`/tmp/sdk-lifecycle-journal-barrier-20261106/result.json`及check.log。只证明日志模块原失败单项，不宣称整个模块通过；未改产品、真实数据库或预算，没有外部模型、完整回归、CI或发布，G18及全目标仍未完成。

## 最新结果（2026-11-06，生命周期历史升级链）

原错误核对：control_takeover两项夹具只升级至v14便打开当前Kernel；kernel_pause升级链同样止于v14却按当前模式验证；lifecycle_generation_retirement逆构造v11时遗留v19回执表且正向链只到v18。仅补齐这些测试升级链至v19，逆构造移除回执表并显式validate_kernel_schema_v11。原历史receiver_note_id／空receiver_store_id、历史控制收据、多次接管及陈旧fence拒绝断言保留，未改产品或真实数据库。

当前独立安装包三个完整模块11项通过、0失败／错误／跳过，5.896秒；`/tmp/sdk-lifecycle-schema-fixtures-20261106/result.json`及check.log。覆盖原4条错误；split_store历史生命周期及journal_handoff原错误仍未解决。本轮无外部模型、完整回归、CI、推送或发布；G18及全目标仍未通过。

## 最新结果（2026-11-06，时钟发布与重启权限负例）

主代理核对Context.budget的SQLite分支始终调用_capture_budget，未配置guard_budget不意味着可隐藏保留样本。旧legacy测试现验证样本调用后水位已发布，墙钟回退时完成时间继承原发布下限并超出原10秒截止，原约束不变；不再错误期待已发布样本必为未知。仍保留同模块未发布样本／外部pending及入口中断负例。

独立只读审查及主代理核对runtime.recover_completions的completion_time_unknown分支：旧非托管运行留下的时钟proof仅为事实输入，无认证handler返回或host决策，不能生成失败结果。重启测试改为负例，要求原running完整快照及result=None不变，准确attempt／fence未知报告、完整deferred proof及待处理状态保留，重复恢复仍无结果／无再次handler调用；原真实spawn退出、重启、guard释放及取消优先场景保留。未将此作为受管理恢复正例，未更改产品授权。

当前独立安装包上述两模块9项通过、0失败／错误／跳过，5.749秒；`/tmp/sdk-clock-proof-recovery-fixed-20261106/result.json`及check.log。原11项4失败现场继续保留。未新增产品修改、外部模型调用、完整回归或CI；全目标仍未验收。

## 最新结果（2026-11-06，晚提交回执与快照写栅栏）

当前安装包四模块11项复现4失败，`/tmp/sdk-completion-recovery-current-20261106/result.json`及check.log。晚提交测试由独立任务限定修正：保持原Kernel连接身份，以SQLite trace_callback拦截实际COMMIT、显式保留callback异常，启用managed_delivery路径，提交返回后记录事务关闭；原monitor completion_handoff_pending、真实提交、结果及重启后的准确完整lease／settlement receipt检查保留。源码单项通过4.138秒，`/tmp/dispatcher-late-commit-receipt-final.log`。

快照测试原期待BEGIN IMMEDIATE读者持锁时另一写者提交采样，与当前防止未提交较早观察漏读的栅栏冲突。现明确验证原读者持锁期间新采样在0.01秒内被SQLite拒绝且无marker；释放原读者后才准入采样并完成原清理，原读者0.08秒门闩及0.1秒捕获预算不变。无SDK产品／真实数据库修改。

当前独立安装包上述两模块2项通过、0失败／错误／跳过，4.528秒；`/tmp/sdk-completion-fence-receipt-fixed-20261106/result.json`及check.log。global_pending_guard legacy时间相等及wrapped_restart原完成权限不确认两项仍待调查；没有模型调用、完整回归、CI或发布，G18仍未通过。

## 最新结果（2026-11-06，v16交付权限测试复验）

原30项当前源码复现2失败／1错误，日志`/tmp/sdk-v16-current-20261106.log`；历史v16夹具已先补移除v19回执表并显式validate_kernel_schema_v16。独立只读审查与主代理代码核对确认其余三项为旧探针／异常预期：序列化返回实际采样位于supervision.sample_clock，在写事务内且早于序列化及effect收集；独立连接属于legacy capture_completion_time路径，序列化路径使用Kernel原连接；取消后的不同结果被终态不可变检查以InvalidStateTransitionError拒绝。仅调整测试，保持精确采样顺序、实际独立连接物理关闭、取消状态及无交付事实断言；新增序列化采样时生命周期占用／事务内及完成后释放检查，不宣称Kernel连接被关闭。租约更新负例仍要求原StaleFenceError／StorageIsolationError。

同一当前独立安装包整个模块31项通过、0失败／错误／跳过，12.639秒，证据`/tmp/sdk-v16-fixture-installed-20261106/result.json`及check.log。未修改产品、未调用外部模型、未运行完整回归／CI／发布；原4条错误在失败追踪表中记为定向复验通过，不代表全部G18或G01–G18通过。

## 最新结果（2026-11-06，完成准入历史夹具）

原完整回归的完成准入两项失败由历史夹具遗留v19的kernel_budget_sample_receipts造成。仅修正测试：逆构造v14时移除该表，并在升级前显式validate_kernel_schema_v14；原运行中lease、intent保留及不得推断admission／delivery authority的断言不变。当前独立安装包整个test_completion_admission模块13项通过，0失败／错误／跳过，3.531秒；证据`/tmp/sdk-completion-admission-fixture-20261106/result.json`及check.log。未改产品、未调用外部模型、未启动完整回归或CI；G01–G18仍未全部验收。

## 最新结果（2026-11-06，子任务交付夹具与父完成采样边界）

原子任务手工夹具跳过执行预算准入，先手工构造HandlerContext再调用私有_enter_handler，触发budget sampling requires admitted execution limits。原单项已复现，`/tmp/sdk-child-direct-before-20261106.log`。独立核对确认真实Runtime先准备预算；夹具现调用prepare_execution_budget并传入返回envelope，产品采样权限检查不变。同一当前安装包整个子任务结果交付模块9项通过、0跳过、38.896秒，`/tmp/sdk-child-delivery-fixture-20261106/result.json`及check.log，包含原生成功／失败、持写锁交付及撤权／迟到／未知时钟负例。

另一父完成采样夹具错误期待持写锁时接受新的父返回时间；该新采样必须先取得写事务栅栏，原child已有事实不能证明另一写者没有未提交的更早观察。现保持原持锁child交付，明确验证父新采样在持锁时拒绝、原watermark及pending不变；释放writer后才取新的父完成样本，未将其宣称为原先返回时刻。身份／lease／context／登记对象及pending tuple错配负例在释放writer后验证，避免SQLite锁掩盖所测身份错误。源码4项通过10.095秒。

同一当前安装包联合父完成采样及原child持锁清理模块19项通过、0失败／错误／跳过、36.970秒，`/tmp/sdk-child-handoff-fence-installed-20261106/result.json`及check.log。149个冻结产品Python文件直接字节一致；修订测试另存快照，未改写原候选输入。本轮仅修正测试与取证，不新增产品改动或外部模型调用，未运行完整回归或CI。

新增[原回归失败追踪](SDK_0_8_0_REGRESSION_FAILURES.md)，按原77条即时错误分组保留待定位／定向复验状态，防止把局部绿项当作完整完成。完整G18及G01–G18目标仍未通过。

## 最新结果（2026-11-06，未推进检查点的入口超时）

保留原顺序及新增状态快照的88项安装包取证组合仍1失败，41.348秒，`/tmp/sdk-timeout-settlement-evidence-20261106/result.json`。本次序列化初次即timed_out，没有复现其原5秒恢复窗口失败；catch-timeout子场景失败现场`/tmp/sdk-process-group-timeout-8_z6uq28/evidence.json`确认采样在登记token前遇SQLite busy，token=None，原单调工作截止已过，但截止见证保留的原预算检查点尚有20毫秒。因此旧判断直接对该未推进检查点取view，错误保留budget_clock_unknown。

新增确定性回归实际调用_capture_budget_until，在原20毫秒内模拟采样登记前的准入失败；修复前失败，`/tmp/sdk-entry-unadvanced-before-20261106.log`，修复后三项边界测试通过，`/tmp/sdk-entry-unadvanced-after-20261106.log`。本次产品仅一行：以保留墙钟检查点配合当前本地经过时间投影预算；不新增墙钟观察，不写入／ACK采样，原独立截止比较、约束／start身份、可信域、底层异常和不确定token保留。限定独立审查未发现阻断。

清理测试此前要求自定义异常格式进入效果日志，与_effect_failure_details不执行任意异常格式化的合同冲突；现断言准确固定摘要，并分别从正常诊断记录或原清理异常验证prelaunch分类，原不重试／效果indeterminate／准确lease及敏感文本不泄露断言保留。此为测试修正。

新冻结候选`/tmp/sdk-entry-projection-candidate-20261106`独立安装，session23604验证相关组合，预计2分钟后首次检查；related-result.json及related.log为结果位置。仍未宣称序列化组合恢复失败已修复，不运行完整回归、模型或CI。

当前候选组合session23604退出0，94项／41.601秒，0失败／错误、2项本地端口权限跳过，即92项实际通过；related-result.json已补准确skips=2，以related.log为准，未将wasSuccessful当作无跳过证明。原先间歇失败的入口超时／进程组／序列化路径本次通过，但不覆盖旧失败或证明长期稳定。149个冻结产品Python文件与安装包直接字节一致。

同一安装包在允许本机端口的环境仅补跑上述两项清理联测，session90165退出0，2项通过／0跳过、8.370秒，tool-cleanup-result.json及tool-cleanup.log。验证原效果保持indeterminate、不重试、不提交、准确执行身份、正常诊断及诊断中断的prelaunch分类、效果摘要不执行自定义异常格式化及敏感文本不泄露。两次范围分别报告，不改写为单次94项无跳过。无外部模型调用、CI、发布或完整回归。

## 最新结果（2026-11-06，真实后代进程覆盖与剩余间歇失败）

原进程组单项取证session24107退出0，5.537秒，`/tmp/sdk-process-group-evidence-20261106.log`及三个保留证据目录。三个子场景均在入口确认前耗尽20毫秒，未实际执行handler；因此即使timed_out且无延迟文件，也不能作为后代清理验收。原期限及断言保留，未将单项通过覆盖上轮87项失败。

同一安装产品、保留原87项顺序并新增实际后代场景的88项诊断组合session74840退出1，47.171秒，1失败／0错误；`/tmp/sdk-process-timeout-followup-20261106/result.json`及check.log。原进程组三个子场景通过，但序列化超时在原有5秒回执恢复窗口结束后仍running。此前该用例已含恢复循环，本次没有新增或延长该窗口。该失败现场未保留原生原因，不能据此宣称共同根因或全部超时已修复。

新增test_timeout_contains_actually_started_detached_child单独使用5秒预算，明确要求handler实际入口、已创建独立会话后代身份、准确worker匹配、超时及独立on_cleanup_confirmed，释放子进程门闩后无延迟写入；旧20毫秒用例保持不变。最终断言版与新增序列化取证包装在同一独立安装包上限定2项通过、8.752秒：`/tmp/sdk-timeout-focused-evidence-20261106/result.json`及check.log。该次序列化未复现原组合失败，不能覆盖它。

实际后代证据`/tmp/sdk-started-detached-timeout-rhu81ye1/evidence.json`记录同一命名空间worker22／child24、新会话、on_entered与worker身份一致、最终timed_out／handler_timeout、独立on_cleanup_confirmed。storage-evidence.json显示closed、active_runs=0、original_pending为空且无关闭／settlement错误。此为Linux当前安装产品的真实Kernel路径，不推广为全部managed AgentApp／平台矩阵／G16通过。149个冻结产品Python文件与安装包直接字节一致，新增测试保存在外部测试快照，未改写候选source。

仍需取得序列化组合失败的准确入口、采样与结算证据；当前已增加initial_return及恢复后returned快照，尚未执行这两个新增字段的版本。未新增产品改动、模型调用、CI、发布或完整回归。

## 最新结果（2026-11-06，历史夹具及原生入口超时）

测试夹具修正：历史数据库改为真实KERNEL_SCHEMA_V12建库并验证，不再从当前模式删除表来模拟；显式升级补齐v18→v19，复制目标断言引用当前版本常量，保留源库／历史行不变检查。独立任务只改该测试文件，源码8项通过、2.421秒，`/tmp/sdk-authority-schema-fixture-20261106.log`。应用钩子Mock明确返回无可复用同步投影；合成运行时补齐_delivery_activation=None；不支持token预算断言更新为要求SDK-owned OpenCode proxy的实际合同。现有独立安装包上的这16项全部通过、5.538秒，`/tmp/sdk-regression-fixture-check-20261106/result.json`与check.log。它们是夹具修正，不计作产品缺陷修复。

真实原20毫秒进程超时仍失败的现场`/tmp/sdk-posix-late-timeout-kkkkw2ks/evidence.json`：worker_ready但未on_entered，入口确认期间采样超时被包装为BudgetClockUnknownError。补充异常记录后再次失败，`/tmp/sdk-posix-late-timeout-__w_sq4x/evidence.json`确认准确采样令牌、可信已过期原执行预算、_NativeBudgetCutoff原单调截止及实际超出观察点均存在。该现场不能证明入口确认或业务执行。

修复只在入口确认异常处理处，要求准确私有截止证据、原约束及started_at匹配、非hard截止、可信预算已过期、观察同时越过记录截止与函数入口建立的原工作截止、实际底层TimeoutError／SQLite竞争，才拒绝为execution_deadline_exhausted。保留采样token、截止及底层错误于details，不ACK、不确认入口、不增加预算。原真实用例通过，`/tmp/sdk-timeout-entry-fixed-20261106.log`；负例涵盖缺失、hard、不同约束、未观察越界、时钟错误，仍预算未知。新负例首次合成计时夹具与重新映射的截止不符，1失败；固定原计时映射后2项通过，原失败日志保留。限定独立静态审查未发现阻断，但不证明不确定token最终清理。

新冻结产品候选`/tmp/sdk-entry-timeout-candidate-20261106`独立安装，原生超时／退出、完成预算及上述夹具组合session74238运行中；related.log及related-result.json为结果位置，预计2分钟后首次检查，不启动完整回归或模型调用。原真实通过现场storage-evidence.json显示runtime closed、无original_pending及关闭／settlement错误，但不将其当作全部managed清理验收。

安装包组合已终止：session74238退出1，87项／37.010秒，1失败子场景、0错误，related-result.json及related.log；149个产品Python文件直接字节比较一致。原20毫秒真实超时、父调度停顿、JSON序列化超时、原生突然退出、完成预算及上述16项夹具均通过；唯一失败为进程组超时的child-timeout-new-session子场景，实际failed而非timed_out，尚无该准确失败的原生原因证据，不能宣称整个超时修复完成。原场景现增加与其他原生测试相同的保留证据包装，原期限／三个子场景／断言不变，尚未运行该新增取证版本。不原样重跑87项或完整回归。

## 最新结果（2026-11-06，真实进程退出分类）

原突然退出单项在当前源码复现：`/tmp/sdk-abrupt-process-exit-20261106.log`与`/tmp/sdk-abrupt-process-exit-lc5k_ufq/evidence.json`。监督进程已报告handler_process_exit，parent／supervisor预算checkpoint均confirmed；但预算归一化把该基础设施失败当成业务完成，因无原业务完成时间和视图而改写budget_clock_unknown。

修订仅在三个SDK监督进程生成的缺失／非法worker结果分支，以及父端监督进程缺失结果的后备分支，标注control_error。正常业务失败、成功、超时和撤权路径不扩大；未按错误码豁免预算验证，未伪造完成时间。新增同名handler_process_exit但无控制来源标记的负例，仍必须拒绝为预算未知。独立限定审查未发现阻断，提醒控制错误不代表清理确认；本次保留独立清理回调及关闭证据。

首轮源码65项通过、21.135秒。冻结产品候选`/tmp/sdk-abrupt-exit-candidate-20261106`独立安装，149个产品Python文件直接字节比较一致。首次临时安装包驱动漏写__main__保护，触发spawn重入，65项中1失败；`abrupt-unguarded-result.json`及`/tmp/sdk-abrupt-installed-20261106.log`保留，不能用于验收。纠正驱动后原65项全部通过、16.794秒：abrupt-result.json与`/tmp/sdk-abrupt-installed-guarded-20261106.log`。

实际原生证据`/tmp/sdk-abrupt-process-exit-cki7vblt/evidence.json`：准确attempt1／fence1入口confirmed，执行failed／handler_process_exit且不可重试，原5秒约束保留、时钟trusted，并收到独立on_cleanup_confirmed。storage-evidence.json显示runtime closed、active_runs=0、close_error及settlement_error为空、original_pending为空。该用例是原SQLite Kernel真实进程路径，不据此宣称已验证全部managed AgentApp交付或完整G18。无外部模型调用、CI、发布或完整回归重跑。

## 最新结果（2026-11-06，完整回归失败及首次打开竞争）

此前 session99894 已终止、退出1，不再等待：`/tmp/sdk-consumer-identity-candidate-20261106/full-result.json`记录外层5项、1失败、2766.697秒。原消费者全部场景与 managed-stall 示例通过；内层完整发现运行到原2700秒上限后超时，且已有多项错误，没有完整内层总结。下方原30分钟快照是历史记录，不代表当前仍运行。77条即时错误记录包含子测试，不能当作77个独立失败测试。完整G18仍未通过。

隔离测试入口此前只复制两个scripts文件，漏掉测试所导入的验证辅助脚本；现复制完整scripts目录并排除缓存，未引入src或删减测试。`/tmp/sdk-harness-script-closure-20261106/result.json`仅证明7项成功加载，不证明执行通过。

已确定首次空库并发初始化缺陷：两个调用者都在写入准入前观察空库，后者重复创建触发器。强化原并发用例，强制两方先观察空库；旧实现失败于kernel_events_no_replace重复创建（`/tmp/sdk-first-open-before-20261106.log`）。修复在BEGIN IMMEDIATE后重新读取表集合；赢家逐条执行SQLite完整语句，在同一事务中完成安装；后到者验证已有模式，异常回滚。未将触发器改为IF NOT EXISTS，保留严格校验。独立限定静态复核未发现阻断，审查者未运行测试。

源码首轮相关10项为9通过、1错误，1.267秒（`/tmp/sdk-first-open-related-20261106.log`）：新回滚测试漏设sqlite3.Row，恢复安装后的严格校验读取到tuple而报错。该夹具已纠正，保留原失败。新冻结产品候选`/tmp/sdk-first-open-candidate-20261106`已构建并独立安装；纠正后的测试另存corrected-tests，未改写冻结source，当前仅验证并发首次打开、失败回滚、不兼容模式拒绝、应用表共存及初始化清理。该范围不代表完整G18。

当前安装包限定验证完成：10项全部通过、0失败／错误，1.443秒；`/tmp/sdk-first-open-candidate-20261106/first-open-result.json`及`/tmp/sdk-first-open-installed-20261106.log`。149个冻结产品Python文件与安装包直接字节比较一致。覆盖强制并发空库观察及重新打开、建表中途失败完整回滚后重新安装、不兼容已有模式拒绝且不修补、应用数据共存、初始化失败清理。没有模型调用、完整回归重跑、CI或发布；其他已知失败仍待处理。

## 当前推进（2026-11-06，消费者顺序与静默取消关闭）

2026-11-05 19:28 UTC原30分钟检查点：session99894仍运行、无full-result.json。full.log显示打包4项通过，公开消费者证据`/tmp/sdk-observability-consumer-dpxaun80`已生成原all场景完成结果，随后进入内层installed-suite；只读宿主进程核对准确PID460094，父PID459786，命令`/tmp/tmpz3mciwfm/venv/bin/python -X faulthandler /tmp/tmpz3mciwfm/installed-suite/run_installed_tests.py`，内层已运行30:20、CPU19:37。该存活／CPU快照不证明测试通过或具体业务进展；原输出由subprocess.run保留，未抢读管道、重启或延长期限。内层原2700秒上限剩约15分钟，下次到该原期限检查。当前完整G18仍未完成。

包含修订消费者的新冻结完整输入候选`/tmp/sdk-consumer-identity-candidate-20261106`已构建并独立安装；原完整打包／隔离consumer入口session99894，full.log、full-observation.json及结果目标full-result.json，预计30分钟后首次检查。此段启动记录不表示已取得完整结果，原2700秒内部上限不变。

原消费者顺序诊断session99604退出1，`/tmp/sdk-consumer-sequence-diagnostic-evidence-20261106/silence/close-failure.json`确认仅runtime_close未完成，worker_drain／executor_shutdown／final_pump／notification_join均完成；pending_diagnostic_count=7，线程在_retry_close_cleanup/_drain_diagnostic_notes。补取投递错误的session25862亦退出1，`/tmp/sdk-consumer-delivery-diagnostic-evidence-20261106/silence/close-failure.json`：lifecycle append及peek均为StorageIsolationError／Kernel commit connection identity is unconfirmed; outcome may be committed。第一次执行因临时工作目录下相对cp路径不存在，在消费者启动前失败；已保留原日志并用准确绝对路径执行，未覆盖业务失败。

代码核对确认消费者取证钩子无锁替换Kernel._connection为ConnectionTrace并在恢复时再次交换对象；后台提交可能仍持有原对象，现有提交身份保护会正确隔离。现场没有交换准确时刻，故不把单次栈描述为完整发生顺序。当前仅移除连接替换和SQL代理，保留有界控制锁／取消／supervision跟踪及准确关闭失败报告／线程现场，不改产品连接身份检查。独立限定静态复核支持该纠正，未运行测试。

同一已安装产品、修订消费者、新进程及新存储，session70083退出0：原all顺序全部通过（success／failure／budget／silence／cleanup），`/tmp/sdk-consumer-identity-fixed-20261106.log`、`/tmp/sdk-consumer-identity-fixed-evidence-20261106/summary.json`及全部原始文件。原期限与业务断言保留；这是消费者取证修正，不计为产品停止缺陷修复。此前完整入口失败不覆盖、不改记通过；完整套件仍待新冻结候选实际运行。

按30分钟观察期限取得session69016结果：退出1，外层5项4通过／1失败，56.109秒，`/tmp/sdk-parent-entry-candidate-20261106/full-result.json`及full.log。打包边界检查通过，消费者先前父子成功路径已通过，当前在silence_cancel_case最终app.close出现OrchestratorHostTimeoutError，尚未进入内层完整测试发现。不将其记为内层全套测试失败数量，也不继承旧238项为本次完整通过。

现场`/tmp/sdk-observability-consumer-gop_8qg8/silence`保留原取消收据、准确取消结果、后代停止检查和cleanup-last-observation；用例已观察准确worker退出及cleanup confirmed，随后Host关闭仍超时。进程清理确认不是整个Host清理完成，不推定两者矛盾。原消费者未保存该异常的stop_report，当前补充失败时准确报告及线程堆栈的尽力记录，原异常、期限和断言不改。

同一安装产品的静默单项诊断session14568退出0，`/tmp/sdk-silence-close-diagnostic-20261106.log`及独立evidence目录；未触发异常，不能覆盖原顺序失败。当前只运行消费者原有顺序（不重建、不重新启动完整回归），session99604，`/tmp/sdk-consumer-sequence-diagnostic-20261106.log`，预计2分钟后首次检查，保留新增失败现场。冻结候选25页Wiki已本地导出wiki-preview、引用release/0.8.0，wiki-export.log，不发布。本轮无外部模型／远程CI／推送。

## 当前推进（2026-11-06，子任务入口与父采样竞争）

当前源码相关43项全部通过、47.796秒，`/tmp/sdk-child-entry-related-20261106.log`，session89821退出0。新完整输入候选`/tmp/sdk-parent-entry-candidate-20261106`已wheel独立安装，151产品文件直接字节比较通过；打包3项及新增父子入口3项全部通过，原公开消费者success场景亦退出0，总11.369秒。证据targeted-result.json、targeted.log、consumer-success.log及consumer-success/实际父子／工具交付文件。未改变原业务期限或用诊断脚本替代该原消费者。此为限定安装包验证，不将原整入口失败改记通过。

同一候选原打包／隔离consumer完整入口session69016已启动，full.log及full-observation.json记录，预计30分钟后首次检查，内部原2700秒上限不变，结果目标full-result.json；尚无完整结果，不判G18通过。独立审查建议的本地pending、撤权和finish拒绝边界继续由原入口权限／采样测试约束，当前新增明确覆盖父marker原期限及不确定token不重试；不宣称本次新增覆盖所有可能竞争。

新增实际SQLite父子用例：公共submit_child提交子任务并准备预算；父任务的准确_KernelBudgetCapture注册并保留真实采样事实；子任务guarded_entry首次准入时父marker仍在，随后父任务确认原事实。旧源码确定性失败，`/tmp/sdk-child-entry-parent-before-20261106.log`；修订后同一用例通过，`/tmp/sdk-child-entry-parent-fixed-20261106.log`。这证明原入口存在该竞争缺陷，但尚不能证明此前公开消费者失败必然由同一竞争导致。

guarded_entry仅在_begin_budget_sample准入阶段遇到准确BudgetClockUnknownError／budget_clock_sample_unresolved:sampling、无cause／非空不确定token且本地无pending时，按已有原startup/work截止等待。每次重试保留权限检查；不重新开始计时、不确认外国marker、不重复本地未确认采样，finish阶段重试不扩大。独立限定静态审查未发现具体阻断，未由审查者运行测试。

新增父marker持续至原截止仍拒绝、携带不确定token不得重试负例。相关父子预算／串行采样／入口权限模块session89821，日志`/tmp/sdk-child-entry-related-20261106.log`，按预计约1分钟后的首次检查取得上述结果；原失败记录保留，不调用外部模型、CI、推送或发布。

## 当前推进（2026-11-06，完整构建输入及完整安装回归）

按原观察期限检查：session97849已退出1；外层5项、2失败、32.697秒，尚未进入内部完整测试发现。full-result.json及full.log保留，不将本次称为内层全套已运行。第一失败是打包AST边界未允许settlement直接依赖maintenance；独立复核确认其参与既有存储维护合同，storage_connection也已间接使用同一模块。源码测试仅为准确settlement.py增加maintenance许可，其他模块边界、Orchestrator禁止及无第三方依赖校验保留；源码打包3项通过、2.254秒，`/tmp/sdk-packaging-boundary-20261106.log`，尚无此测试修订的新候选。

第二失败为公开消费者success场景等待原first-reported标记20秒超时，现场`/tmp/sdk-observability-consumer-96hw5apa`。只读检查保留数据库确认父处理器已调用、子执行在业务处理器入口前failed，原错误BudgetClockUnknownError／budget_clock_sample_unresolved:sampling；父处理器按原合同返回包含child_error的结果。不是工具已执行，也不是单纯标记读取错误。未改写原存储或输入；单独诊断session88340使用同一已安装产品和原success期限，只在消费者脚本捕获入口异常现场，日志`/tmp/sdk-observability-entry-diagnostic-20261106.log`及独立evidence目录，预计30秒后检查，不重复整个入口。

同一冻结候选87份Markdown的577个本地链接静态校验通过，docs-links.json；未据此宣称README示例执行或完整文档验收通过。

单独消费者诊断session88340退出0，原success场景实际通过，原期限未改；日志`/tmp/sdk-observability-entry-diagnostic-20261106.log`及`/tmp/sdk-observability-entry-diagnostic-evidence-20261106`。本次没有触发入口异常，因此没有异常堆栈；不覆盖原完整入口失败，不认定竞争已修复。另曾为正常外国采样者与guarded_entry增加直接检查，旧源码即通过，不能证明原失败机制，未据此修改产品或保留该无针对性测试。当前仍需取得原子任务入口采样失败的准确竞争证据；不原样重复完整入口，不放宽期限。

打包入口核对发现前一临时stop handoff候选仅复制LICENSE，未复制仓库既有NOTICE／MANIFEST.in等发行输入。151产品文件比较和238项实际代码行为结果保留，但该候选不能作为完整发行打包验收。未修改仓库既有发行文件或覆盖旧制品；新候选`/tmp/sdk-complete-input-candidate-20261106`完整复制原打包测试所列根文件、DocsforAgents与.github及原源码／测试／文档等，重新构建wheel并独立安装。启动前逐字节核对151产品文件，并检查wheel中LICENSE／NOTICE分别唯一且内容与冻结输入相同，无新增散列。

当前session97849已启动冻结安装环境的原入口`tests.test_packaging tests.test_execution_kernel_isolated_consumer`，日志`/tmp/sdk-complete-input-candidate-20261106/full.log`、外层结果目标full-result.json、观察期限full-observation.json。原隔离consumer测试自行构建sdist及wheel、安装到新环境，并执行完整测试发现；保留原内部2700秒期限，不削减测试或延长预算。历史完整回归约27分钟，本次估计30分钟后首次检查；此时尚无结果，不计为通过。本轮没有外部模型或远程CI调用，无推送／发布。

## 当前推进（2026-11-06，准确完成门锁停止交接）

当前安装包结果：session8847退出0，238项全部通过，0失败／错误／跳过，244.613秒。证据`/tmp/sdk-stop-handoff-candidate-20261106/expanded-result.json`及`expanded-authorized.log`，SDK实际来自该env的site-packages，151产品文件直接逐字节比较通过。范围为原199项（原顺序及期限保留）、新增5项串行采样、RuntimeHost／停止报告34项；包含此前3条安装包错误路径和本轮停止交接正反例。结果JSON的scope文字沿用旧驱动概述，未枚举新增的宿主模块，准确238项及逐项名称以原日志为准。此结果是当前安装包相关组合通过，不是完整G12、G16、G18或G01–G18通过。

同一安装包与冻结驱动的G01及G13限定合同通过：`config-contract/acceptance.json`、G01.json、G13.json；G13仍仅证明无后端时的能力协商／拒绝，原生强隔离后端未提供、真实隔离未验收。本轮无外部模型调用、CI、推送或发布；完整回归、最终候选实际OpenCode协作／恢复及适用平台矩阵等仍待验收。

新增真实运行时用例从活动线程注册表取得准确authority/gate，由另一线程持有该门锁，撤权后释放。旧源码稳定错误：`/tmp/sdk-stop-gate-before-20261106.log`，1项错误、2.542秒。原实现把瞬时门锁占用与进程撤销失败统一记录为永久清理失败，即使随后完成准确交接亦不能恢复。

当前request_stop仅在所有独立撤销及关闭操作成功后，将尚未观察交接的准确authority/gate作为独立私有异常交给Host原停止所有者。该所有者在运行时生命周期／注册锁之外等待准确门锁，取得后检查对应权限已撤销；不凭注册表删除、线程消失或异常文本确认。等待异常仍保留为停止错误；进程撤销失败、执行器或context关闭异常不进入此收敛分支。不重复执行失败的request_stop；后续runtime.close仍保留既有的正常request_stop调用，不能宣称整个关闭过程仅调用一次。

新增三项分别验证门锁在原stop(3)期限内释放后成功、原stop(.05)返回False且不提前关闭而后同一所有者续接、门锁占用同时进程撤销失败时保留termination_unconfirmed。负例首次错误预期在工作线程排空前立即抛异常；实际先限时返回False但已保留错误。修订为先验证False及原错误、释放工作线程后再验证原错误抛出，未修改产品错误处理。首次54项53通过／1失败日志`/tmp/sdk-stop-gate-reviewed-20261106.log`保留；最终宿主／停止报告／串行采样54项全部通过、22.035秒，`/tmp/sdk-stop-gate-reviewed-final-20261106.log`。独立限定静态复核未发现具体阻断，未由复核者运行测试。

新冻结源码、脚本、测试及文档的安装包目录`/tmp/sdk-stop-handoff-candidate-20261106`，原199项加5项采样与宿主／停止报告模块。初次驱动在测试前因本机socket权限拒绝退出，原日志expanded.log保留；随后在允许本机服务的环境启动同一冻结驱动，session8847，expanded-authorized.log，预计5分钟后首次检查，按时取得上述完成结果。驱动直接逐字节核对安装内容与冻结源码，不新增散列；原期限与断言保留。

## 当前推进（2026-11-06，慢轮询调度修订）

确定性fake-clock用例确认RuntimeHost运行中将三个通道的下次轮询从操作开始前的同一now计算；当全部到期通道耗时大于各自间隔，等待期限已过，立即开始下一轮。旧empty poll安装包同用例失败，`/tmp/sdk-slow-poll-installed-before-20261106.log`。当前源码仅对本轮实际尝试的sweep/pump/progress_hook，在本轮工作提交结束后以新的时间点安排各自下次轮询；未执行通道保留独立期限，原退避、显式唤醒和工作线程推进不变。不添加无条件sleep、不延长原请求预算。另一通道在本轮期间到期或明确唤醒仍可立即下一轮，不承诺所有循环均等待。

新慢轮询及原独立通道退避／提交退避3项通过，`/tmp/sdk-slow-poll-fixed2-20261106.log`；首次测试配置较长sweep周期导致未执行通道在本轮期间正常到期，失败日志保留，调整为相同周期以验证“全部到期通道已经执行”的明确前提，未修改产品来强制睡眠。独立限定源码复核无具体阻断，未由复核者运行测试。此修改不证明两个原30秒超时均由此导致。

源码真实宿主／原两条失败／采样修订验证session40211，日志`/tmp/sdk-slow-poll-real-host-20261106.log`，预计启动2分钟后检查；原2秒工作期限、30秒wait、关闭3秒及其他断言保留。无模型、CI或扩大199项。session40211退出1：50项49通过／1错误、25.136秒，未跳过。原2秒abort后过期和监督技术重试两条原失败均通过；原2秒adapter入口余0.445999秒、应用锁等待约3.4微秒、abort确认余0.236676秒，未改变原期限。串行20项和宿主相关测试通过，但test_stop_drains_workers_and_closes_runtime在原stop(3)出现_ProcessCleanupPendingError(thread_completion:authority_handoff_unconfirmed)，Host保留shutdown_error。现场`/tmp/sdk-runtime-host-stop-q8el7rcy`保留，实际线程完成门闩在request_stop时占用，不能以之后runtime关闭成功覆盖原错误；正独立核对其是否为暂态未收敛或保守合同。没有重跑同组。尚无包含采样和本轮调度修订的新安装包。

## 当前推进（2026-11-06，199项反证及事务准入错误归因）

session28579退出1：同empty poll安装包199项、276.912秒，196通过／3错误／0失败／跳过，expanded-result.json及expanded.log。原34项32通过／2错误：原2秒abort后过期未进入adapter，Agent wait lock admission timed out，现场`/tmp/sdk-prelaunch-deadline-failure-mcfrbs0u`及`/tmp/sdk-retry-matrix-wait-timeout-syfn51u0`；监督技术重试test_supervised_retry_joins_original_before_new_observer在snapshot读取耗尽原30秒，`/tmp/sdk-retry-matrix-wait-timeout-95gsjx9a`。两个采样栈分别在应用锁内的只读open_plans和控制意图pending事务的PRAGMA synchronous=FULL，不能凭单次栈断定完整30秒同一等待原因。49项通过未覆盖本次失败，空轮询优化没有闭合整条调用链。

第三个错误为test_close_retires_only_positively_unsampled_return_guard：真实_begin_budget_sample在严格截止已过时，_transaction尚未进入事务体即抛普通TimeoutError，原代码只为InspectionBudgetExceeded保留先前真实guard。新增私有TimeoutError子类仅标识这个严格截止前置拒绝，外层仅在原预算也确认耗尽、曾观察guard、无cause／不确定token、未采样且pending为空或准确本地未采样状态时保留原guard；不产生完成权限、不重新采样、不清除外国marker。普通TimeoutError仍保留。确定性新测试在旧安装包失败`/tmp/sdk-transaction-admission-before-20261106.log`；修订源码串行模块18项全部通过4.866秒，`/tmp/sdk-transaction-admission-guard-20261106.log`，含实际事务体前到期、普通超时和不确定标记原异常保留负例。独立复核发现新的私有TimeoutError子类不能命中原exact-type短窗口重试，已在仅_work_deadline存在的原重试条件中显式加入该私有类型；任意其他子类不扩大。新增实际首个事务短窗口已过、第二次事务在原工作期限内成功发布测试。修订后模块19项全部通过4.992秒，`/tmp/sdk-transaction-admission-guard-reviewed-20261106.log`。进一步独立复核要求工作期限仍有效时，新子类携带budget_sample_token也必须原样传播，已限定仅无该标记时重试该类型，并补实际准入异常附不确定标记、外层期限仍有效、只尝试一次且不采样／不发布负例。最终串行模块20项全通过5.245秒，`/tmp/sdk-transaction-admission-guard-final-20261106.log`。尚无包含本修订的安装包验证，最终独立限定静态复核未发现其他具体阻断，未由复核者运行测试。

没有重跑199项、模型或CI。两个应用等待问题仍未修复，G12/G18及完整目标保持未完成。

## 当前补证（2026-11-06，empty poll安装包配置与文档）

同一安装包、冻结脚本和双语Wiki输入，`/tmp/sdk-empty-poll-candidate-20261106/config-contract/`中的G01.json、G13.json及acceptance.json通过；实际解释器及agents导入均为该env的site-packages。G01仅配置等价／默认值及非法配置拒绝；G13仅无strict后端接纳前拒绝，原生强隔离后端未提供、真实隔离未验收。577链接、4个README示例、0跳过通过，docs.log；25页双语Wiki本地导出wiki-preview、引用release/0.8.0，wiki-export.log；没有远程发布。宿主/usr/bin当前仅Python3.12，不能代替3.10–3.13／其他OS与架构矩阵。199项仍按原5分钟安排检查，未提前读取结果。

## 当前推进（2026-11-06，空恢复轮询候选）

确认并修订next_pending_round_robin空队列仍需写锁的问题：先以只读事务执行原schema／绑定与写入配置检查（日志模式、FULL同步及只读检查器拒绝均保留），无pending/error立即返回；有记录则关闭读取事务，再用原写事务重新选择并推进游标。所有阶段及最终重读共用原绝对截止，不刷新预算、不缓存队列，不跳过新事实。读后新增记录在下次轮询观察，结算或新增发生于两阶段之间时仍由写阶段重新检查。

旧sync read安装包真实持有journal写锁且已提交空队列时超时，日志`/tmp/sdk-settlement-empty-before-20261106.log`；当前源码同一测试通过。新增6项覆盖空／非空写锁、两阶段结算／插入、原截止、只读拒绝及实际SQLite语句持久化配置核验。首次相关18项17通过／1错误为object.__new__ Runtime夹具缺_delivery_reconciler；补None明确未启用交付扫描，其他断言不变。修订后新增与游标19项全通过4.565秒，`/tmp/sdk-settlement-empty-cursor-fixed-20261106.log`，包括公平性、大小限制、VACUUM及竞争。独立限定静态复核无具体阻断。

原2秒场景及settlement journal模块24项全部通过7.639秒，`/tmp/sdk-settlement-empty-runtime-20261106.log`；原场景adapter进入余0.557563秒、abort确认余0.215846秒，保留原预算／等待／状态断言。不是完整G12通过，也不能推定所有此前超时同一根因。

新wheel独立安装于`/tmp/sdk-empty-poll-candidate-20261106/env`，冻结测试；session42102执行原34项原顺序及sync read／同步交接／空轮询15项，共49项，日志targeted.log、结果combined-result.json，预计启动3分钟后检查。驱动核对151产品文件直接字节一致及实际安装位置。session42102正常退出0：49项全部通过、0失败／错误／跳过，130.687秒，combined-result.json及targeted.log。原34项原顺序保留并通过，新增15项通过；这不是完整G12或完整G01–G18通过。同包扩大原184项及新增15项共199项，session28579，expanded.log及expanded-result.json，首次检查不早于expanded-observation.json所记启动5分钟后。没有模型、CI、推送或发布。

## 当前推进（2026-11-06，宿主路径反证与通知线程归属）

源码宿主组合11项、3.821秒，9通过／1失败／1错误，日志`/tmp/sdk-sync-handoff-host-20261106.log`。原2秒abort后过期场景仍未进入adapter，现场`/tmp/sdk-prelaunch-deadline-failure-130maxl7/evidence.json`及`/tmp/sdk-prelaunch-deadline-state-mysyp1b7`，Kernel recovery_required、effect indeterminate；同步交接修订不足以解决该失败。另一个通知线程start替身在启动前抛错的用例，后续stop错误为归属未确认，不能将生产代码观测不到的“替身确实没启动”推定为安全清理。

独立分析确认任意start覆盖可提交延迟启动后抛错，线程暂未存活／ident为空不能证明未启动；生产代码保持未知。测试现保留启动异常和runtime关闭断言，新增stop(0)必须明确超时、不伪报完成；随后通过原Thread.start真实启动同一个已登记线程，1秒内join后stop(1)成功，且回调未投递。源码宿主模块9项通过、0.163秒，`/tmp/sdk-handoff-notification-ownership-final-20261106.log`；未将本次夹具修订计为产品缺陷修复，原失败日志保留。

原2秒单项进一步分段采集通过、3.434秒，`/tmp/sdk-handoff-entry-profile-20261106.log`：adapter进入余0.487550秒，abort确认余0.197525秒，应用锁等待0.051667秒；资源预留36.309毫秒、ToolServer构造17.591毫秒、原生登记读取最大2.203毫秒。该次小项耗时不足以解释前一未进入adapter的失败，不推定它们为瓶颈，不用带采集单次通过替代正常执行失败。嵌套／并行统计不相加。尚无新安装包验证，无模型、CI或扩大回归；G12/G18及完整目标保持未完成。

## 当前推进（2026-11-06，同轮同步交接源码验证）

已实现桥接成功后向紧随进度回调交接准确同步投影，限定同一Orchestrator实例、完整命令及最新attempt快照匹配，回调内每execution最多消费一次；前台等待与未命中仍完整同步，显式取消同步不变。独立复审发现初版接受被覆盖sync_execution返回快照的来源漏洞；已改为真实同步实现成功退出事务及连接清理后才记录凭据，sync遍历不再据返回值自行生成凭据。

源码9项通过、6.543秒、正常退出0，日志`/tmp/sdk-sync-handoff-reviewed-20261106.log`：6项交接测试及3项原同步读事务测试。覆盖单次消费、回调异常清理、跨线程不继承、命令／投影／任务不匹配、同步后桥接失败、公共同步覆盖无凭据；调用真实AgentApp._reconcile_one配合真实SQLite Orchestrator确认回调复用、前台完整同步，该测试应用外围为合成对象，不宣称完整AgentApp宿主联测。初次夹具因通知收集未就绪而未注入预期异常，失败日志保留，修正仅强制该注入点就绪。

本次未运行扩大回归、模型调用或CI。新源码尚无当前安装包、真实宿主整轮及原2秒失败用例的有效验证；不将9项通过计为G12、G18或完整目标通过。修正后的独立静态复核确认来源问题已闭合，限定范围内未发现其他具体阻断；该复核未运行测试。

## 当前推进（2026-11-06，sync read 候选）

本轮没有据单次线程栈继续修改日志校验。实际源码检查：SettlementJournal._validate是有界schema／绑定校验，不扫描完整记录。当前安装包原2秒场景一次分段计时通过、3.506秒，`/tmp/sdk-dispatch-profile-20261106.log`；adapter进入剩0.489752秒，abort确认剩0.176518秒。日志校验75次合计110.489毫秒、最大7.433毫秒；next_pending40次合计278.503毫秒；recover_completions36次合计1818.823毫秒；sync_execution41次合计1075.010毫秒；应用pump26次合计1469.207毫秒。嵌套及跨线程并行耗时不能相加，这次单项通过不能覆盖原37项36通过／1错误。

独立只读分析确认host _Transport.pump先sync活跃execution，紧随应用progress hook可能再次sync同一execution；但两个通道的调度与backoff独立，桥接错误不阻止hook，新提交或inactive调用可能不在桥接同步集合，取消后的明确同步也不能省略。直接将host hook全部改成不sync会削弱恢复，故未实施。若做此优化，需要同一轮成功桥接的准确execution／command／attempt的一次性交接，未命中及前台等待仍完整同步；目前仅为必要条件分析，并非已实现或已验收。未启动新模型、重复整组或CI，目标仍未完成。

执行版本未变化时，sync_execution先在显式读取事务中执行原注册命令、已派发attempt及不可变版本校验；命中较低／同版本时保留before_commit故障注入和原调用方截止检查。较新版本释放读事务后，在原写事务中重新校验再保存，避免并发重复推进。没有跳过执行身份或终态校验。独立静态复审未发现此限定修改具体阻断。

真实独立Orchestrator写锁用例：旧inner timeout安装包超时失败，`/tmp/sdk-sync-read-before-20261106.log`；修订源码通过。同版本篡改、命令不符仍拒绝；真实另一同步者先写新版本时不重复推进，后来的旧观察不覆盖新状态；原失败注入及截止保留。源码3项1.666秒通过；含旧Orchestrator／managed／create replay／deadline共29项28.509秒通过，`/tmp/sdk-sync-read-related-20261106.log`。

新wheel独立安装`/tmp/sdk-sync-read-candidate-20261106/env`，151产品文件直接字节一致。原34项原顺序加新增3项，共37项：36通过／1错误／0跳过，159.296秒，session60332退出1，combined-result.json及targeted.log。新增3项通过；原2秒abort后过期仍未进入adapter，wait30耗尽，现场`/tmp/sdk-prelaunch-deadline-failure-4g_5tflf/evidence.json`、`/tmp/sdk-retry-matrix-wait-timeout-5wxuj7dn/threads.txt`。Kernel仍running/revision3、无结果。采样时一个工作线程处于settlement._validate，其他线程等待recover_completions锁，协调线程在Kernel读取；该快照不能证明全部30秒都停在同一位置。不将本次修订宣称为完整调用链修复，亦不继续原样扩大回归。当前配置合同及文档证据仍属上一inner timeout包，未继承为新包完整验收。无外部模型、CI、推送或发布。

## 当前推进（2026-11-05，inner timeout 候选）

当前安装包补证：带诊断的相关28项全部通过、8.562秒（`/tmp/sdk-inner-related-diagnostic-20261105.log`），没有据此覆盖先前27/28失败。扩大组合session73818退出1：184项／244.692秒，183通过、1失败、0错误／跳过（`/tmp/sdk-inner-timeout-candidate-20261105/expanded-result.json`、expanded.log）。串行采样和新增两项本轮通过，原2秒abort后过期场景再次未触达边界；现场`/tmp/sdk-prelaunch-deadline-failure-slead8k0/evidence.json`，adapter_calls=0、boundary_timings为空，调用已转recovery_required，测试约3.366秒后因boundary断言失败。此次不是wait30秒悬挂，不能归为相同等待错误，也不能认定该场景稳定通过。需分析原2秒内准备／调度耗时，不原样重跑。

当前inner timeout包G01及G13限定合同通过，独立冻结驱动`/tmp/sdk-inner-contract-20261105/source`、结果`result/acceptance.json`、G01.json、G13.json；G13仅无strict后端时接纳前拒绝。当前包解释器文档检查577链接／4 README示例／0跳过通过，docs.log；25页双语Wiki本地导出至wiki-preview、ref release/0.8.0，wiki-export.log，无远程发布。这些分项不代替完整G18或真实模型验收。

定位并修复串行采样错误原因丢失：内部_begin_budget_sample创建独立InspectionBudget，但与返回观察使用同一原截止；内部超时不设置外层stopped_reason。现在仅在外层budget.check也确认超时、之前已观察到同阶段guard、当前仍未采样且拥有准确pending状态、异常不带budget_sample_token不确定标记时，保留先前的guard拒绝；其余错误原样传播。不刷新截止、不授权新结果、不清除外国marker。独立静态复审未发现此限定分支具体阻断。

新实际采样guard测试在旧WAL安装包错误，`/tmp/sdk-inner-admission-timeout-before-20261105.log`，原InspectionBudgetExceeded；修订源码通过。另有异常对象及不确定标记保留负例。当前wheel独立安装于`/tmp/sdk-inner-timeout-candidate-20261105/env`，151产品文件直接字节一致，串行预算模块15项全部通过、4.066秒、0跳过，targeted-result.json及targeted.log，含原失败关闭用例和新增两项。该范围不是完整组合通过。

源码相关28项27通过／1失败、10.221秒（`/tmp/sdk-inner-admission-related-20261105.log`）：另一个foreign normal sampler race在原3秒截止以Kernel control admission超时，外国ACK已成功。独立分析未确认其与本次分支存在因果关系，现有调用前pending日志不足以判定锁饥饿。已为该单一竞争场景保存每次finish调用起止、失败类型／原因及ACK完成时刻（仅失败时输出），未增加数据库读或延长期限。当前安装包用现测试单独执行该场景通过、约0.64秒，`/tmp/sdk-inner-race-diagnostic-20261105.log`；不能覆盖源码组合失败或认定其原因已解决。未再启动整组回归，未调用外部模型、CI、推送或发布。G12、G18及完整G01–G18目标均未完成，旧候选证据保留。

## 当前推进（2026-11-05，WAL read 候选）

扩大组合已结束，session49429退出1：182项／223.234秒，181通过、0失败、1错误、0跳过；`/tmp/sdk-wal-read-candidate-20261105/expanded-result.json`及expanded.log。原34项全部通过；原2秒场景adapter进入剩0.508829秒，prepare应用锁等待0.066920秒，abort确认剩0.188668秒，确实触达目标窗口且原恢复／禁止重试断言通过。该场景在45项及182项中均通过，但不推广为完整G12。

唯一错误为`test_close_retires_only_positively_unsampled_return_guard`：调用串行完成观察，`_begin_budget_sample->_read_floor`在读取全局guard前InspectionBudget.check超出原检查期限，未返回测试期望的BudgetClockUnknownError。不能在尚未读取guard时伪造其拒绝原因，亦不放宽窗口；需检查事务准入与guard检查间的实际耗时及异常合同。该用例的finally仍尝试完成原other采样；完整输出保留。未启动新模型或原样重跑整组。

已有WAL连接先查询journal_mode，仅模式不符时协商WAL；仍逐连接配置并验证synchronous及busy_timeout，不降低持久化级别。独立静态复审未发现本次限定修改具体阻断。源码持久化及回执11项通过、1.480秒，`/tmp/sdk-wal-existing-profile-20261105.log`。真实写锁用例验证读取已提交数据、FULL同步且不重新设置模式；旧包同一测试仅在“未重复设置”断言失败（`/tmp/sdk-wal-before-20261105.log`），不据此声称已复现旧包30秒等待的原因。

新安装包`/tmp/sdk-wal-read-candidate-20261105/env`独立导入，151产品文件直接字节一致。原34项原顺序加持久化／创建回执11项，共45项全部通过、135.696秒、0跳过，`combined-result.json`及combined.log；原2秒abort后过期场景亦通过，原期限及断言不变。旧174项失败完整保留。当前扩大组合为原171项加创建回执3项、持久化8项，共182项，session49429，预计4–5分钟后检查；结果目标expanded-result.json及expanded.log。在扩大结果前不宣称整组稳定、G12通过或完整目标完成。无外部模型调用、CI、推送或发布。

## 当前推进（2026-11-05，create replay 候选）

本轮组合已结束，session28675退出1：174项／248.958秒，173通过、0失败、1错误、0跳过，`/tmp/sdk-create-replay-candidate-20261105/combined-result.json`。新增3项全部通过；原34项仍33通过、1错误，原2秒abort后过期场景在wait(30)的应用锁准入处超时。不得将本次create重放优化视为该场景已修复。失败现场`/tmp/sdk-prelaunch-deadline-failure-nwj8rupb/evidence.json`显示adapter_calls=0、boundary_reached=false；线程快照`/tmp/sdk-retry-matrix-wait-timeout-d63cr0mq/threads.txt`显示持应用锁的后台推进停在get_command_receipt->_connect->configure_sqlite_connection->_enable_wal的PRAGMA journal_mode=WAL；这是超时时刻的等待位置，尚不能仅凭单次栈证明全部30秒均花在此处。接下来应验证连接配置等待及后台推进持锁的期限，而非不改代码重跑174项。原现场保留，无新增真实模型调用。

计时定位到原2秒场景推进期间重复create_run的写事务准入。当前修订先在显式读取事务中执行原_replay（保留内容冲突、已释放Run及历史收据校验），命中时保留before_commit故障注入和调用方原截止检查；未命中则释放读取事务，再由原写事务重复校验并创建。不跳过Run身份校验、不延长预算。独立静态复审未发现本次范围内具体阻断。

源码20项相关测试全部通过、20.035秒，`/tmp/sdk-create-replay-related-20261105.log`，包括真实持有WAL写锁下读取原收据及拒绝冲突、读取未命中后另一Orchestrator实际创建的竞争、故障注入及截止时间。此结果不证明原Agent组合已修复。

新wheel独立安装于`/tmp/sdk-create-replay-candidate-20261105/env`，保留原recovery包和失败现场。安装包原171项加3项新增用例，session28675，结果目标`combined-result.json`、日志`combined.log`；预计4–5分钟后检查。原34项顺序及原期限保持；安装包产品逐字节对应为驱动前置检查。未调用外部模型，未运行CI、推送或发布。G05/G06及其余完整目标仍未通过，本条不是完成声明。

## 最新状态（2026-11-05，recovery 候选；历史候选证据保留）

当前recovery安装包原abort后过期场景单独复核通过：1项／3.481秒，original-deadline.log；adapter进入余0.641709秒、abort确认余0.300787秒，原2秒期限、原30秒等待、原重试和状态断言均不变。本轮真实触达目标窗口，不把之前abort晚于期限的失败追溯改成通过。当前解释器文档检查577链接／4个README示例／0跳过通过，docs.log；无模型调用。当前包171项组合复核进程12702，原34项顺序保持，新增恢复及入口边界在后续独立列入；进程12702退出1：171项／229.587秒，170通过／1失败／0错误／0跳过；combined-result.json及combined.log。原34项33通过／1失败，原abort边界仍未达到；135相关和新增两项通过。失败现场 `/tmp/sdk-prelaunch-deadline-failure-xas5_yg2/evidence.json`、状态 `/tmp/sdk-prelaunch-deadline-state-u0xbjyz7`：adapter实际上已在期限内进入（余0.276662秒），prepare等待应用锁0.252811秒，总prepare0.315713秒，随后未触达abort边界。不能把此失败描述为adapter入口被拒绝；已将原日志作为准确信息。单项通过仍不足以证明整组稳定。

当前recovery候选 `/tmp/sdk-recovery-candidate-20261105` 已包含managed recovery_required跳过legacy采样修订，wheel安装环境独立。安装包真实Runtime恢复／stop／原控制窗口竞争4测试全部通过、7.723秒，recovery.log；包括实际execute_once不确定结果、indeterminate副作用、无成功结果，未调用模型。独立冻结配置驱动 `/tmp/sdk-recovery-contract-20261105/source` 校验当前安装包：G01与G13均passed，`result/acceptance.json`、G01.json、G13.json记录准确site-packages及解释器。G01限定配置/YAML/Python/CLI/双语Wiki默认值一致及非法配置拒绝；G13仅当前无strict后端时启动前拒绝合同，不宣称提供真实严格隔离。旧entry包170项和原Agent失败仍保留，不继承为当前recovery包整组通过。打包复制README.en.md时发现该路径不存在（未修改仓库、wheel构建安装成功）；未把该复制失败列作完整文档导出成功。

组合170项剩余失败根因证据补充：`/tmp/sdk-prelaunch-deadline-failure-nza1d9gw/evidence.json`显示adapter进入剩0.407682秒、abort确认剩0.064769秒，确实触达原边界。随后未完成effect产生recovery_required结果，但managed Runtime的EffectRecoveryRequiredError不经过普通failure观察，在进入已有实时恢复授权检查前调用legacy完成时钟采样，留下floor_without_ack未知，前台撤权后保存late_thread_fact；该事实不能再取得CAS权限，Run保持submitted/running直到wait30秒超时。源码仅对managed recovery_required跳过legacy采样，标记完成时间未知，仍由现有active／stop／lifecycle／原lease／precommit授权检查决定是否转恢复；成功／普通错误／非托管路径不变。独立静态审查未发现该范围授权阻塞；不声称named effect已启用额外代次约束，不以时间未知授予成功或重试。新增实际execute_once抛错回归，要求恢复状态、indeterminate effect、原attempt/fence、无成功结果及legacy采样零调用，相关源码5项／39.063秒：4通过、原abort后过期1错误，`/tmp/sdk-recovery-no-legacy-clock-20261105.log`。新实际effect恢复测试、原monitor恢复／stop／锁期限测试通过；Agent场景本轮abort确认已晚于原期限0.369479秒（prepare耗时0.334901秒），因此本轮没有复现“abort确认在期限内”的目标窗口，不能算通过，也不能断言此修订已解决全部等待。现场 `/tmp/sdk-prelaunch-deadline-failure-81rqhe5e/evidence.json`、状态 `/tmp/sdk-prelaunch-deadline-state-yes6gaai`、等待超时 `/tmp/sdk-retry-matrix-wait-timeout-_jgens_q`保留。原2秒期限不变，未新增模型调用；该Runtime修订仍是源码证据，未安装包验证。

当前entry候选 `/tmp/sdk-entry-candidate-20261105` 已wheel独立安装（保留sampler旧包现场）。安装包2项／10.244秒、0失败／0错误／0跳过，`result.json`和targeted.log，验证新增准备阶段过期拒绝与原2秒abort后过期测试。原场景adapter进入剩0.484127秒、abort确认剩0.226055秒，随后原期限到期，边界和禁止重试断言全部通过；不扩大原预算。此为合成prelaunch故障的实际SDK路径，不替代真实模型G05/G06/G15。当前组合170项进程75719：原34项保持顺序，随后135相关与新增1项；冻结测试及安装包导入、151文件逐字节一致前置验证，日志combined.log，进程75719退出1：170项／253.876秒，169通过／0失败／1错误／0跳过，combined-result.json及combined.log。135相关及新增过期入口全部通过；原34项仍33通过／1错误，错误在原abort后过期场景 item.run.wait(30)：_pump -> _advance_run -> store.get -> Agent store caller deadline elapsed，原始TimeoutError未按测试预期形成AgentExecutionError。相关现场 `/tmp/sdk-retry-matrix-wait-timeout-h8ctztek`，不将其按预期失败计为通过，待检查推进期限与异常传播。

当前sampler包原34项进程6680退出1：33通过／1失败／0错误／0跳过，129.952秒，`/tmp/sdk-sampler-schema-check-20261105/original-result.json`及original-localcomm.log；151产品文件逐字节与源码核对（未使用hash）。本轮invocation/orchestrator writer等待竞争通过；剩余 original_deadline_expiry_after_abort_blocks_retry 未触达abort边界。失败现场 `/tmp/sdk-prelaunch-deadline-failure-us_0dv1c/evidence.json`、状态 `/tmp/sdk-prelaunch-deadline-state-g0fbld2p`：adapter首次进入时remaining=-0.196864秒，prepare时已-0.198110秒，adapter调用1次，native abort尚未确认。说明前置检查后准备工作能耗尽原期限，不能证明abort后过期路径。源码在 adapter.execute 前（工具服务、原生ownership读取和token支持检查后）新增原期限／取消再检查；未改变原期限。新增实际消耗原5秒期限的工具准备边界测试，要求adapter零调用。源码测试1项／6.540秒通过，`/tmp/sdk-adapter-entry-expiry-20261105.log`；同一测试在未含修复的sampler安装包1项／6.535秒明确失败（实际adapter.calls=1），`/tmp/sdk-entry-expiry-before-20261105/result.log`，构成修复前后实际路径对照。独立审查指出断言须在延迟处理线程有机会继续执行之后进行；测试已增加gate恢复确认，并移到AgentApp正常关闭之后检查零调用。加严版本源码1项／6.487秒通过，`/tmp/sdk-adapter-entry-expiry-reviewed-20261105.log`；旧安装包同一加严版本仍失败（calls=1），6.515秒，`/tmp/sdk-entry-expiry-before-20261105/reviewed-result.log`。该修正尚未进入sampler已安装wheel。

超大SQL标量验证证据修正：135项安装包失败现场 `/tmp/sdk-completion-clock-hldw0cit/evidence.json` 显示 parent_attempt/blob 仅一次调用便耗时0.910817秒（原调用0.1秒、夹具总重试窗0.5秒），因此正确传播超时，不能重试或放宽原窗口。另发现该测试自建数据库写死schema10，而当前schema19；过去正常子场景多数在schema校验即拒绝，不能证明目标字段实际被检查。已改用当前schema常量，并逐字段断言schema／watermark／execution identity／parent identity的准确拒绝原因，保留Python解码尺寸检查、原0.1秒调用和0.5秒总界限。修正后源码2测试／1.569秒通过，`/tmp/sdk-oversized-current-schema-20261105.log`；使用同一新wheel独立导入、另存当前测试夹具（不改冻结135项现场），安装包2测试／1.486秒通过，`/tmp/sdk-sampler-schema-check-20261105/result.log`，12个实际超大字段子场景记录 `/tmp/sdk-completion-clock-0aocy6xi/evidence.json`。这补强输入拒绝证据，不等于整个135项已通过，也未证明0.91秒耗时的根因。

09:48 UTC到期检查：真实session69734已退出1，`/tmp/sdk-owned-return-groups-rework-20261105/acceptance.json`确认G05失败（08:48:03.789至09:48:07.109），G06失败；G05异常类型见G05.json，G06为共享场景失败且仍缺真实工具歧义／缺少输入／完整原生清理收据检查。未重启或延长原预算。串行修正未包含在该冻结安装包中，不能用当前源码追溯为修复该失败。

相同前三个模块顺序的临时分段计时：26项／7.776秒全部通过，目标测试总65.794ms，步骤finish12.497／begin12.098／finish11.803／ACK11.839／begin16.359／finish12.571ms（嵌套ACK与finish不可重复求和），日志 `/tmp/sdk-serialized-suite-timing-20261105.log`。未确认此前整组超时的根因。当前源码已构建新的独立wheel和环境 `/tmp/sdk-sampler-candidate-20261105`，冻结复制tests并使用断言强制安装包导入；进程89962退出1：相关134项加完成存储启动测试共135项，134通过、1错误、0跳过，91.103秒；`result.json`及`regression.log`保留安装包导入路径。此前 retained monitor 测试本轮通过；此次错误为 test_actual_oversized_sql_scalars_are_rejected_before_python_decoding 的 parent_attempt/blob 子场景，在普通完成读取 _read_floor 首次 budget.check() 超时。错误位置改变，不能宣称此前所有超时已解决，亦不能将此包标记通过。该测试不发起模型请求。

短窗口诊断补充：保持原0.1秒控制窗口，对 retained monitor fact 测试连续10次计时，均通过；原始记录 `/tmp/sdk-serialized-retained-timing-20261105.log`。实际 begin/finish/ACK 分段为十余至数十毫秒，不足以认定固定逻辑错误或整组稳定。独立审查发现保存的 guard 异常可能跨越成功准入或其他失败，导致陈旧原因覆盖当前超时；已在成功准入后清空，并在非guard失败时清空。当前只允许同阶段最后的guard拒绝作为超时原因，不改期限、不清除未知采样、不新增模型调用。审查后原134项复核日志 `/tmp/sdk-serialized-reviewed-final-20261105.log`，进程90585退出1：134项／119.162秒，133通过、1错误；仍为 test_return_confirms_own_retained_monitor_fact_before_sampling 在最后 remaining() 检查超出原0.1秒窗口。与上一整组同路径，连续单独10次通过不能排除整组条件影响；尚未证明根因，不能宣称整组通过。

当前工作树串行返回采样修正（尚未形成新安装包）：为串行返回准入增加同事务全局采样保护检查，并仅在两个串行调用点启用内部临时异常信号；普通读取保留原始 BudgetClockUnknownError 精确类型，新增相应断言。当前源码首次相关回归134项／121.239秒，132通过、1失败、1错误，日志 `/tmp/sdk-serialized-final-compat-20261105.log`；两项均为等待采样超时后丢失原拒绝原因。修正超时原因保留后，相关74项／35.926秒，73通过、1错误，日志 `/tmp/sdk-serialized-guard-cause-20261105.log`；余下错误发生在另一个测试完成采样后最终 remaining() 超过原短控制窗口，不改期限。原两项及该新错误测试单独复核3项／1.709秒全部通过，日志 `/tmp/sdk-serialized-guard-focused-20261105.log`。单独通过不覆盖整组失败，不能视为整组稳定通过；仍需定位短控制窗口在整组下的超时，不构成G05/G06/G12验收。本轮没有新增模型调用，也没有修改正在运行的冻结候选或其数据库。

2026-11-05 09:27 UTC按计划确认真实session69734仍活跃、无acceptance.json；原预算不变，下一检查09:48 UTC（北京时间17:48，覆盖原期限及清理），不重启或新增模型场景。本次只读快照`/tmp/sdk-owned-return-groups-rework-20261105/observation-0927.json`：planner及第一轮两个coder均submitted，两个coder准确native operation已cleaned。只读settlement快照`settlement-observation-0927.json`：agent:b6509f35df3c455fa93777298fccff5b和agent:b58aa49004714ace8ad1c8da74d48520均attempt1/fence1，分别08:50左右留下pending late_thread_fact、outcome ok但completion_time_known=false，准确错误BudgetClockUnknownError: budget_clock_sample_unresolved:sampling。模型返回与原生清理不能建立完成权限，不宣称场景业务进展或通过。当前进入这两个采样归属的只读定位，尚未证明根因；不修改运行中冻结包或内部数据库。完成账本启动测试finally保留主异常并记录清理错误的狭窄修订已补语法检查，不将之前5项通过追溯为新增异常分支实际验证。

2026-11-05 09:18 UTC原34项结果session79972退出1：32通过／1失败／1错误／0跳过，237.157秒，`/tmp/sdk-reader-batch-20261105/original-result.json`及original.log。FAIL为invocation/orchestrator writer测试在holder.start之前entered.wait(5)失败；现场`/tmp/sdk-agent-wait-contention-crbqf_5s`，执行停在execution_claimed持久回执，完成账本文件为零字节，随后_UnpersistedDiagnosticsError，不证明写锁竞争断言成立。ERROR为原2秒期限测试caller过期，现场`/tmp/sdk-prelaunch-deadline-state-0f6461tc`及`/tmp/sdk-prelaunch-deadline-failure-qpg1zs1o`；预算采集在原期限后约14.8ms留下Kernel control admission budget elapsed，无adapter／effect调用，不能认定共同根因。

完成账本不可用仍允许创建AgentApp的独立缺陷已复现并修正于源码：真实Runtime初始化只注入SettlementJournal.__init__失败，修复前constructor不拒绝，before2日志1.931秒失败。AgentApp现在检查公开settlement_storage.available，在host注册／接纳前拒绝；底层Runtime旧降级行为保留。原有初始化失败清理路径负责资源所有权，未引入可选诊断业务审批门槛。独立审查无产品阻塞，但指出夹具可误把清理未知当通过，已补充cause检查、同目录实际重开、无请求／无adapter调用；只有两次关闭均确认才删除目录，异常保留。源码单项及宿主准入顺序共5项12.083秒通过，`/tmp/sdk-settlement-startup-related-20261105.log`，session99692退出0；双语Wiki同步。首次整类mock探针source_id错误仅夹具失败，before日志保留，不作为产品复现。该新修订尚未构建新包，不能继承reader-batch的G01/G13或文档检查为新修订通过；G12仍失败。验收脚本另补无异常正文／局部变量的异常链文件／行号／函数名，不改冻结执行。当前真实G05/G06仍按09:27 UTC检查，无新增模型调用或CI。

2026-11-05 09:13 UTC当前reader-batch独立venv的G01／G13通过，`/tmp/sdk-reader-batch-config-isolation-20261105/acceptance.json`及对应分项JSON，session1579退出0；YAML／Python／CLI与双语Wiki默认值一致，strict无能力时业务前拒绝，未提供或验证真实strict后端。原34项原顺序复验session79972于09:12 UTC启动，`/tmp/sdk-reader-batch-20261105/original.log`、最终original-result.json；原预算／断言／超时不变，151产品文件与安装包一致，当前尚无最终结论。预计4–6分钟，下一检查09:18:20 UTC（北京时间17:18:20）；不提前刷新。此组非完整G12，不是CI，无模型调用。旧候选真实G05/G06仍独立按09:27 UTC检查，不把其结果归给reader-batch。

2026-11-05 reader-batch文档检查：首次使用.venv及runpy仅修改父进程sys.path，README子进程实际导入工作区源码（readme-evidence.json有路径），README.md example2期望timed_out实得failed，`/tmp/sdk-reader-batch-20261105/docs.log`；该执行不是候选安装包证据，原始失败保留，不推断权限或产品根因。修正为独立venv安装同一wheel（system-site-packages提供PyYAML6.0.1），在/tmp用-I执行且先确认dispatcher_sdk导入env/site-packages。session96917退出0，`docs-installed.log`确认577本地链接及4个README真实示例通过、0跳过。本包151产品文件与源码直接字节一致，product-parity.json；之前26项影响范围结果不扩大为G12通过。09:08 UTC宿主/proc/pressure/io单次观察avg10 some15.60/full14.87，CPU0；此快照不证明先前超时根因，未据此改变2秒预算。原真实G05/G06仍按09:27 UTC计划检查，无新模型调用／CI。

2026-11-05 09:07 UTC按计划收取：期限诊断session87891终态exit1，单项4.881秒、boundary_reached断言失败；`/tmp/sdk-reader-batch-20261105/deadline-diagnostic.json`准确execution=agent:4819fbc60b5e442d9feb90639f8c4e6c／attempt1／fence1记录监控_complete_monitor_timeout在原strict_deadline内返回recovery_required（1648702.231133504至1648702.261913442，原strict_deadline1648702.26894933），没有采集到BudgetClockUnknownError构造。本次未复现30秒等待，不认定消除；依旧未触达abort边界，原合同未验证通过。真实G05/G06 session69734本次句柄确认仍活跃、acceptance.json尚不存在；不新增模型场景、不重启／延长原预算。下一检查09:27 UTC（北京时间17:27），最多仍受原08:47起3600秒预算及清理约束；不能把活跃当进展或通过。

2026-11-05 reader-batch wheel独立target安装目录验证完成：`/tmp/sdk-reader-batch-20261105/result.json`，26项12.909秒全部通过、0失败／错误／跳过，session93290退出0；149产品Python文件与当前源码直接字节一致，包外-I执行并断言导入来自installed目录。使用现有.venv解释器和依赖，不宣称全新依赖环境。覆盖caller期限9项、service store及service instance store17项；不代表原34项或完整G12。真实旧owned-return-lock候选G05/G06仍独立按09:07 UTC检查，不混用其原生结果。当前包新增一次期限定位session87891，仅包装BudgetClockUnknownError构造及_complete_monitor_timeout采集来源／准确身份／时间，原2秒／wait30秒不变，输出deadline-diagnostic.json及.log位于reader-batch目录；预计约45秒，下次不早于09:07 UTC检查。采集扰动时序，结果仅诊断，不替代无插桩验收。没有新增模型请求或CI。

2026-11-05 09:02 UTC定向期限检查session82060退出1，1项33.083秒错误，仍在适配器执行前耗尽caller期限。日志`/tmp/sdk-prelaunch-retention-targeted-20261105.log`，本次原状态目录实际保留`/tmp/sdk-prelaunch-deadline-state-39i6x3nr`，失败JSON`/tmp/sdk-prelaunch-deadline-failure-26t0cnzw`及线程`/tmp/sdk-prelaunch-deadline-threads-s2v49v17`，不能算期限／重试通过。

同类纯读取竞争批量修订：NativeOwnershipLedger.get及ServiceRegistry.pending／service_status／names改为只读事务，保留service_status多表读取的同一快照及后续写侧独立权限／代次核验。真实BEGIN IMMEDIATE下新增原生已准备身份读取、含session及fixed-instance服务快照、queued筛选及names测试；未提交accepting=0不能泄露，writer仍保持事务。修复前2项5错误1.055秒，`/tmp/sdk-reader-batch-before-20261105.log`；修复后完整caller-deadline模块9项2.221秒通过，`/tmp/sdk-reader-batch-after-20261105.log`。独立只读审查无具体权限阻塞；未证明上述修订是原期限错误根因，也未覆盖最终安装包或真实服务验收。服务存储及服务实例存储两模块17项10.544秒通过，`/tmp/sdk-reader-batch-services-20261105.log`，session47564退出0。G12仍未通过，不运行CI或新模型场景。

2026-11-05剩余期限用例留证修订：test_original_deadline_expiry_after_abort_blocks_retry改用失败保留状态目录，并在JSON记录state_directory；仅断言通过且app.close正常返回后删除目录。原2秒工作预算、30秒等待、3秒close及断言均不变。独立审查发现新增finally打印可能遮盖主异常，已将该打印设为普通异常下best-effort；语法检查通过。constructor失败仍保留目录但不保证报告路径，此项不作为完成权限修复。使用control-pending已安装包启动单项检查session82060，日志`/tmp/sdk-prelaunch-retention-targeted-20261105.log`，预计约45秒，下一次不早于09:02 UTC检查；无模型调用、未再跑整组。G12保持未通过。

2026-11-05 08:58 UTC收取control-pending安装包回归：session47596正常终态exit1，47项327.686秒，46通过／0失败／1错误／0跳过，证据`/tmp/sdk-control-pending-20261105/result.json`及run.log；151产品文件与构建时源码直接字节一致。范围是原34项原顺序及13项控制存储／工具／读取竞争检查，不代表完整G12。唯一错误为test_original_deadline_expiry_after_abort_blocks_retry，原wait30秒在Orchestrator.sync_execution写事务准入耗尽；`/tmp/sdk-prelaunch-deadline-failure-23ioi4y6/evidence.json`显示adapter_calls=0、boundary_reached=false、boundary_timings为空，不能用本轮证明中止后重试合同通过。关闭前线程现场`/tmp/sdk-prelaunch-deadline-threads-qw6roewh/threads.txt`及等待现场`/tmp/sdk-retry-matrix-wait-timeout-tgqsv7d9`保留；单次栈不能证明持续持锁者或统一根因。上一候选32/34结果保留，不能把跨候选通过项拼接为完整通过。ControlOperations.pending纯读取改用只读事务，新持写锁读取负例及12项控制权限／存储检查本轮通过；不宣称修复全部竞争。G12仍未通过。此次仅收取已有执行并诊断，未启动新测试、模型请求或CI。

2026-11-05 08:47 UTC按约检查：原legacy-close场景session45511已终态exit1；G05／G06均failed，07:46:33启动、08:46:36结束，原3600秒未完成，exception_type=TimeoutError。完整证据`/tmp/sdk-legacy-close-groups-rework-run1-20261105/acceptance.json`及G05.json／G06.json，先前第二轮完成权限unknown事实仍保留。未重启该执行或扩展其预算。随后当前owned-return-lock固定安装包的新G05/G06复验session69734启动，输出`/tmp/sdk-owned-return-groups-rework-20261105`，日志同名.log；保持验证器原3600秒／16 agent_calls／128 model_turns，无新增技术重试。预计成功15–20分钟、最坏原60分钟加清理，下一次09:07 UTC检查，安排`/tmp/sdk-owned-return-next-20261105/groups-observation-schedule.json`。该新候选尚无真实通过证据；G06专门真实负例和逐操作清理补证仍须单独执行，不能把共享场景成功当整项G06通过。没有并行新增模型场景、CI、推送或发布。

owned-return-lock当前包交付补证：旧API convenience／orchestrator／results／recovery四模块39项73.459秒全部通过，0失败／错误／跳过，session10433退出0，`/tmp/sdk-owned-return-next-20261105/legacy-result.json`及legacy.log。实际CLI生命周期14条命令均exit0、serve宿主exit0，`/tmp/sdk-owned-return-cli-lifecycle-20261105/report.json`，仅空闲宿主控制、不调用模型或代替服务业务验收。mypy按Python3.10目标且python-executable指向当前独立安装环境，六个公开消费文件通过，typing.log；不冒充原生Python3.10运行。完整已跟踪及未忽略工作区复制构建sdist，再从sdist重建wheel，151产品文件与源码及已安装包直接字节一致，`/tmp/sdk-owned-return-next-20261105/sdist-check/result.json`。这些补证不覆盖当前原34项失败、G17监督／资源的真实范围或G18平台缺项；没有新增模型调用、CI、推送或发布。

适配器末端期限准入探针未建立有效复现：三次新测试均未触达指定gate，原预算2秒保持；日志`/tmp/agent-control-080-evidence/agent-adapter-entry-deadline-before-01.log`至before-03.log仅为夹具失败，不证明产品缺陷或修复。未修改产品代码，已删除仅本次新建的无效测试草稿。第三次unittest已输出失败后进程未退出；精确核对PID411264／启动tick164669806／命令后保存process.json及状态`/tmp/sdk-adapter-entry-deadline-32ml1y5x`，仅向该进程SIGTERM，session88265退出143，明确受控终止而非正常清理。无Python栈或准确pending-close原因，不猜测。原真实session45511未受影响，仍按08:47 UTC检查。

监督join负例的最小留证夹具已补强：原40秒工作预算、wait30秒、注入及全部行为断言不变；失败时保留原状态目录、app／adapter／observer强引用和原始异常，关闭前后分别记录时间、adapter.calls、已明确拒绝join次数及活性；普通留证错误保留而不替换原异常，新的BaseException中断不吞掉，app在__enter__前即赋值以保留入口失败所有权。只在成功关闭且测试通过后删除目录。独立限定审查发现的留证遮盖及入口所有权问题已修正。当前安装包只运行该一项，session13679退出0、10.074秒通过，`/tmp/sdk-owned-return-next-20261105/observer-probe.log`；本次未再现整组原错误，不认定修复、不覆盖原32／34结果，也不连续重试。未修改产品代码或模型调用。

当前owned-return-lock安装包原34项未通过：`/tmp/sdk-owned-return-next-20261105/original-result.json`及original.log，32通过／1失败／1错误／0跳过，205.122秒，session85774退出1；151产品文件直接字节一致。原2秒用例adapter入口已晚于原期限8.609毫秒，未触达abort目标边界，原始现场`/tmp/sdk-prelaunch-deadline-failure-nva005di`及`/tmp/sdk-prelaunch-deadline-threads-ydoovdlr`；此后77.4毫秒app锁等待不能解释更早发生的迟到。SDK OpenCode原生prepare另有期限与权限检查，未证明原生过期启动。监督join负例在原wait30秒耗尽，Orchestrator caller deadline elapsed并伴随关闭异常；现场`/tmp/sdk-retry-matrix-wait-timeout-ikosdll2`显示调用staged、worker执行不存在、controller仍running，无结果／控制操作，尚无证据确定原因。原夹具已删除临时状态库，保留的facts及单次栈不能代替持久完成权限事实，不猜测统一根因。此前63项通过仍仅为限定影响范围，G12未通过；未重新运行整组或扩大期限。

当前包G01／G13配置与能力合同检查通过，`/tmp/sdk-owned-return-config-isolation-20261105/acceptance.json`：YAML／Python／CLI及双语Wiki默认一致，strict无后端业务前拒绝；不代表真实强隔离后端可用。25页Wiki本地导出至`/tmp/sdk-owned-return-next-20261105/wiki-preview`，未发布；同包G06原验证器候选与监督器预检通过，`g06-candidate-preflight.json`，无模型启动，不算G06通过。原真实session45511仍按08:47 UTC检查。

同一owned-return-lock安装包文档检查通过：577个本地链接、4个README示例、0跳过，session99169正常退出0；`/tmp/sdk-owned-return-next-20261105/docs.log`。无模型调用；不替代G01–G18其他完整范围或平台证据。

2026-11-05 owned-return-lock新安装包限定修复：真实外部线程持锁0.25秒、原工作期限仍余约2秒时，原实现首次0.1秒失败，修复仅在RLock明确未取得时利用原有限工作截止继续短准入。四处捕获入口受当前上下文收紧期限及继承caller期限限制；每轮失败及取得锁后重新核对停止／撤销与期限，锁内操作／清理异常不重试，原样本／事实／token不重做。独立审查先后发现并复现收紧期限等待越界（约0.3秒预算等待0.802秒）及最终成功取得锁前收紧仍发布，两处已修复；最终限定复核未发现具体阻断。新增16项测试11.925秒通过。独立干净venv安装新wheel，agents依赖为符合声明的PyYAML6.0.3；`/tmp/sdk-owned-return-next-20261105/result.json`与run.log记录151产品文件与源码直接字节一致、包外-I导入，63项全部通过，0失败／错误／跳过，65.909秒、session37665正常退出0。覆盖四处锁竞争、准确注册身份、不重复观察／能力发布、收紧／继承期限、停止撤销、已取得锁中断及清理所有权。旧包原生场景未替换或重启，当前包尚无G05/G06真实复验，不能据此闭合该原现场或完整G12。构建首次仅因只读pip缓存失败，使用no-cache-dir成功，两个日志保留；无模型调用、CI、推送或发布。

2026-11-05 08:08 UTC定时检查确认原session45511仍存活，无acceptance.json；没有新的完成证据。按原约08:46:35 UTC工作截止及清理安排08:47 UTC再检查，不延长预算或重启。锁准入修订的26项相邻完成路径检查20.180秒通过，`/tmp/sdk-owned-return-lock-combined-20261105.log`；独立复核发现已收紧预算期限未传入等待入口，修订仍须覆盖该边界后复审，未生成新安装包或宣称G05/G06通过。

2026-11-05 07:58 UTC原session45511定时观察：第一轮两名coder及reviewer均succeeded且准确完成权限已授权；第二轮一名coder成功，另一名coder返回DONE但完成权限unknown，原始completion_time_error为`TimeoutError: Kernel control lock admission timed out`。只读取证保留于`/tmp/sdk-legacy-close-20261105/g05-round1-unknown-observation.json`。这与旧现场无authority行的失败不同，尚不能确定四处控制锁准入中的具体失败位置。原场景无acceptance.json，不认定G05/G06通过，不重启或延长原3600秒期限；下一次检查不早于08:08 UTC。后续修复仅针对能够证明尚未取得锁的准入失败，必须保留原期限、撤销及唯一采样／发布约束；正在用确定性锁竞争测试验证，不修改运行中安装包。

G06补充验证器执行准备：启动／监督路径独立只读复核未发现新具体阻断，脚本头部过时的launch-authority review pending提示已更新，非业务验收通过。当前候选已准备source/src与source/scripts快照；实际隔离解释器调用验证器原有verify_candidate及_selected_supervisor预检，151产品文件在源码／已安装包／wheel间直接字节一致、实际导入位置与版本匹配、所选监督器与已审查脚本一致，`/tmp/sdk-legacy-close-20261105/g06-candidate-preflight.json`。相关31项无模型启动／监督／清理负例与复制入口合成联测8.516秒通过，0失败／错误／跳过，日志`/tmp/sdk-legacy-close-20261105/g06-entry-offline.log`；它们不证明真实SDK或模型验收。没有加载提供商资源或启动模型。补充负例仍须真实执行，不能把上述预检当G06或清理通过；G05/G06共享真实场景保持原session45511，不提前刷新或并行新增模型场景。

当前包G05/G06真实共享场景复验已启动session45511，输出`/tmp/sdk-legacy-close-groups-rework-run1-20261105`，日志同名.log；原3600秒业务期限、16 agent_calls和128 model_turns不变，无新增技术重试。预计顺利时10–15分钟，最坏原60分钟加清理；下次检查安排见`/tmp/sdk-legacy-close-20261105/groups-observation-schedule.json`。先前复制相对路径／预建输出目录入口错误均发生在原生模型入口前，原日志保留；没有真实旧Run迁移或模型执行超时重启。原G05失败只读取证明确：准确首coder已返回DONE、原生清理完成且completion_time_known=true，保留成功candidate但无kernel_completion_authority行，直到原期限才cancelled；当前修复不能凭159项直接宣称该原现场根因已闭合。独立限定审查支持当前包复验，未发现新的内部明确阻断。G06主验证器还显式缺真实歧义／缺输入／逐操作清理补证，不能把共享场景成功当G06整项通过。

同安装包文档补证：577个本地链接、4个README示例通过，0跳过，`/tmp/sdk-legacy-close-20261105/docs.log`；双语Wiki共25页本地导出至同目录wiki-preview，未发布。

旧API关闭兼容修复已获当前安装包定向证据：`/tmp/sdk-legacy-close-20261105/result.json`、`run.log`，151产品文件与当前源码直接字节一致，独立安装、包外-I导入；159项全部通过，0失败／错误／跳过，234.996秒，session86192正常退出0。原34项顺序在前，随后94项旧API关闭／完成所有权／时钟／权限及31项监控／预算。包含实际持有处理线程、关闭后延迟观察不得启动采集、原准确结果不变、未完成观察连接保留存储、托管完成所有权释放中断与重试、停止闸门拒绝、未知完成和预算清理。该范围闭合此前旧关闭失败，不代表完整G17或其他G项整体验收；G05/G06真实失败未重跑。双语Wiki已写明旧线程API与托管交付关闭差异。独立审查无本次限定修改具体阻断。无真实模型调用、CI、推送或发布。

旧API兼容修复候选：首次独立延后Kernel方案在审查中发现最后一次有界清理后可能丢失重试，且单测失败，已完整撤回，`/tmp/sdk-revoked-close-after-20261105.log`保留。最终修改把新增完成能力注册和两处预登记限定为交付机制；旧API回到原结算路径。关闭只对交付机制等待存活线程，但两种模式都继续阻塞于不明slot release、完成所有权、采样／读取器／结算／原生清理义务。旧活动线程观察用例1.073秒通过。相关94项87通过7失败、0错误／跳过，84.235秒，`/tmp/sdk-legacy-close-related-20261105.log`；七项均为新完成权限夹具未显式选择托管模式。六项现显式启用managed_delivery，原子完成停止一项仍保留旧API成功合同并拦截实际legacy完成，所有原结果断言保留；修订模块16项15.229秒通过，`/tmp/sdk-handler-authority-mode-fixed-20261105.log`。独立审查无限定产品修改具体阻断，并指出旧活动标志断言不能证明停止导致失效，测试名称已按实际生命周期顺序修正。当前新安装包位于`/tmp/sdk-legacy-close-20261105`，session86192执行159项：原34项在前、相关94项及监控预算31项；预计4–5分钟后检查，未新增模型调用。页内矩阵改用当前包未完成状态，保留历史证据，不再将旧包passed显示成当前验收通过。

旧API关闭兼容缺陷确认：原测试 `test_revoked_handler_cannot_start_observer_after_storage_cleanup` 单项仍失败，3.137秒，`/tmp/sdk-revoked-close-before-20261105.log`。处理器确实阻塞在release.wait，close先于release调用；不是陈旧线程记录。当前close检查_thread_authorities/_completion_owner_cleanup后抛出runtime thread ownership remains unconfirmed。HEAD基线close未包含该线程保护且原测试要求close成功并删除观察存储，因此不能以更新测试接受异常来声称旧API兼容。独立只读审查确认返回后的context.close仍可能完成已有预算采样，需要Kernel；直接移除所有权保护也缺安全依据。下一修复应分开已撤销观察记录器的存储清理与尚存活线程的Kernel所有权，并验证线程返回后的准确结果不变及最终资源释放。原测试／产品本轮未改；G17仍未通过，不作为外部阻塞。未新增真实模型调用或CI。

当前安装包原34项适配后整组通过：`/tmp/sdk-return-failure-observation-20261105/g12-adapted-result.json` 与 `g12-adapted.log`，34通过、0失败／错误／跳过，113.246秒；session47070正常退出0。151产品文件与当前源码直接字节一致，包外独立解释器导入。三项监控用例仅更新到实际事务拦截入口并补准确effect代次，原行为／期限断言保留；未更改产品、业务预算或重试次数。此前31/34失败和第一次错误夹具记录均保留。本结果闭合这组技术回归，不代表完整G12；G05/G06真实场景、线程归属关闭错误和其他G01–G18当前包证据缺口仍未完成。本轮没有真实模型调用、CI、推送或发布。

原34项本地通信权限修正执行已正常结束：`/tmp/sdk-return-failure-observation-20261105/g12-loopback-result.json`，31通过、3失败、0错误／跳过，117.243秒。三项失败均未命中新产品的活监控事务入口；测试拦截点从旧恢复入口更新为 `_complete_monitor_timeout`，保留原停止回滚、控制截止和effect状态断言，并核对effect准确执行代次。源码三项6.205秒通过，`/tmp/sdk-monitor-fixture-entry-final-20261105.log`。这不是安装包整组通过；当前同安装包、原34项原顺序复验session47070，日志g12-adapted.log、结果目标g12-adapted-result.json，预计2–3分钟后检查。原失败文件不覆盖；不新增模型调用。G12仍未通过，G01–G18仍未完整验收。


当前return-failure-observation安装包公开类型消费补证：使用mypy的--python-executable指向该独立安装解释器，按Python3.10检查orchestrator、capability、reliability、application、observability、agents六个公开消费文件，全部通过，`/tmp/sdk-return-failure-observation-20261105/typing.log`。该检查不运行模型、不证明真实运行时或完整Python/OS矩阵；G18仍未完成。原34项本地通信权限修正执行仍按07:15:09 UTC计划检查，未提前刷新。


原34项错误权限入口失败已保留：`/tmp/sdk-return-failure-observation-20261105/original-result.json`及g12.log记录34项125.424秒、10失败／15跳过／0错误，9项通过。15跳过均为Operation not permitted；10失败尚未逐项归因，不直接排除产品缺陷。suite已输出结果但session74150未退出；从宿主实际命名空间确认准确argv的pid397597残留43线程，核对结果已完成后仅终止该进程，最终exit143，permission-incomplete-stop.json明确受控终止，非正常完成。未因观察超时重启工作。

所需本地通信权限已补齐，先在127.0.0.1执行socket绑定预检，再同安装包、同34项原顺序启动独立执行session28199；保留原权限失败目录及数据，无改断言、预算、跳过条件或业务请求。新日志g12-loopback.log、目标结果g12-loopback-result.json；下一计划检查2026-11-05 07:15:09 UTC（北京时间15:15:09），预计4分钟，g12-loopback-observation-schedule.json保留。该执行仅本地模拟适配器／真实SDK技术回归，无外部模型调用或CI；在新结果前G12保持失败。


return-failure-observation文档与源码包补证：同一独立安装环境检查577个本地链接、4个README示例通过、0跳过，`/tmp/sdk-return-failure-observation-20261105/docs.log`；双语Wiki共25页本地导出至同目录wiki-preview，引用release/0.8.0，未发布。当前源码构建sdist，再从sdist无依赖重建wheel；151产品文件与当前源码及已安装包直接逐字节一致，`sdist-result.json`、`sdist-build.log`、`sdist-wheel.log`。未新增hash检查。该补证不代表完整回归或跨平台G18通过，G12原34项仍按记录的计划时间检查。


最新return-failure-observation安装包定向31项通过：`/tmp/sdk-return-failure-observation-20261105/result.json`，独立venv、包外-I导入、149产品Python文件直接字节一致；31通过、0失败／错误／跳过，41.327秒。覆盖Linux正常／异常首次返回观察、时钟域读取顺序及延迟、可信过期／较早返回后采集延迟、监控未完成effect／停止／响应丢失、跨原command截止禁止技术重试、未知共享采样拒绝、观察锁忙及预算检查。应用层原2秒effect准入延迟用例本次也通过；前包29项失败现场仍保留，不追溯取消。普通与异常源码时序6项12.734秒、应用单项3.462秒结果分别见`/tmp/sdk-return-failure-boundary-20261105.log`、`/tmp/sdk-return-failure-app-20261105.log`。

同一新包原G12技术34项原顺序已启动，session74150，日志`/tmp/sdk-return-failure-observation-20261105/g12.log`，最终结果目标同目录original-result.json；预计2–4分钟，下一次计划检查不早于2026-11-05 07:08:17 UTC（北京时间15:08:17），用户显式check可覆盖；同目录g12-observation-schedule.json保留安排。此组不等于完整G12，更不继承其他旧候选原生证据；原G12、G05/G06、关闭线程归属错误及G01–G18其余缺口仍按失败／未完成处理。没有新增真实模型调用或CI／发布。


返回／失败首次观察修复与安装包剩余失败：Linux普通返回回调在完成仲裁／存储前，使用原entered envelope、锚定wall值与同域boot elapsed保留首次SDK观察；只有该观察已可信过期，才在持久返回时间失败后保留预算视图，交给原活监控超时事务决定。不是后来监控采样替代返回时间；早观察但迟发布仍unknown。Linux sample_clock改为先采集CLOCK_BOOTTIME再读取boot_id，读取／验证失败仍使用原process回退；其他平台未启用此早期过期回退。准确Kernel回执额外校验execution_id/attempt/fence、与当前结果完整相等后才解除deferred义务，原completion_time_known保留诊断。独立审查分别发现并闭合读取boot_id导致时间平移的问题，未发现最终限定路径具体阻断，不扩大平台结论。

源码返回时序／监控权限7项通过15.665秒（`/tmp/sdk-return-monitor-authority-20261105.log`），预算15项通过0.155秒（`/tmp/sdk-return-budget-impact-20261105.log`），应用过期单项通过3.531秒（`/tmp/sdk-return-expired-app-20261105.log`）。独立安装包`/tmp/sdk-return-observation-20261105`从包外-I验证149产品Python文件直接字节一致，29项28通过1错误、0跳过、37.668秒，`result.json/check.log`；应用过期仍在wait(5)耗尽调用方期限。准确失败现场`/tmp/sdk-expired-effect-entry-4c7mpjv8`：adapter0、entries0、Kernel running，无决定；late_thread_fact实为handler_failure_unknown，原BudgetClockUnknownError的failure_observation因InspectionBudgetExceeded未确认。不是普通返回分支，未启动原34项整组。

随后源码补同样的通用异常边界首次观察，仅可信已过期且完成时间未知才走原监控决定；typed控制／恢复异常不改。独立复核无此限定新增路径具体阻断。新增较早／较晚异常边界加时钟域查询延迟等共6项通过12.734秒，`/tmp/sdk-return-failure-boundary-20261105.log`。此后源码早于尚未重建的新包，前述29项失败没有被覆盖；应用单项复验3.462秒通过（`/tmp/sdk-return-failure-app-20261105.log`），不覆盖安装包失败。中英文Wiki同步首次SDK观察合同，不宣称物理函数返回时刻可知。G12仍failed，关闭线程归属错误及其余G项缺口仍存在，没有真实模型调用、CI、推送或发布。


有限观察的实际锁等待缺陷修复：独立审查发现Runtime.observe在读取本地pending settlement identities时无界等待登记锁，不受观察timeout控制。新增真实跨线程持锁回归修复前失败：observe(timeout=.1)实际等待2.000345秒，`/tmp/sdk-observe-lock-before-20261105.log`。PendingSettlements现提供非阻塞try_identities，锁内只复制不可变entry、锁外映射identity；observe锁忙时明确complete=false、local_settlement_inspection=unknown，不报告空义务、不授予结果或重试权限。新回归及观察清理组合12项29.885秒，11通过1错误，`/tmp/sdk-observe-lock-after-20261105.log`：新回归通过，test_revoked_handler_cannot_start_observer_after_storage_cleanup在close时报_ObservationCleanupPendingError(runtime thread ownership remains unconfirmed)。该错误未排除、未重跑掩盖，不能宣称整组通过或当前包验收通过。独立审查无本次锁修复具体阻断，但未证明observe所有路径严格限时。中英文Wiki同步；拟议的Agent wait unknown异常行为全部撤回，application.py未保留本轮改动，需先解决现有协调取消与调用方非终态兼容合同。没有新安装包、真实模型调用、CI或发布；G12仍失败，完整G01–G18未完成。


监控测试语义分离（未修复原G12）：`tests/test_agents_expired_effect_entry.py::exercise_monitor` 原先通过sleep至deadline后返回，无法保证监控先于未知时间的返回取得权限，不能据此要求必定timed_out。现在仅在四个活监控场景中用Event保持处理器执行，直到实际 `_complete_monitor_timeout` 调用结束才释放；独立的early_unknown保持立即返回／采集失败，要求running且零timeout决定。五项源码检查全部通过13.889秒，`/tmp/sdk-held-handler-monitor-20261105.log`；现场按输出逐项保留。该夹具改动不撤销原安装包43项失败、原G12中止后过期失败，亦不证明应用层unknown报告已完成。独立审查确认Event同步有效，指出响应丢失未核对精确结果；已补Kernel持久结果及返回结果与原candidate JSON完整相等断言，单项复验通过3.168秒，`/tmp/sdk-monitor-exact-receipt-20261105.log`。early_unknown仍只覆盖立即返回采集失败，不声称精确发布时刻已被直接测量。旧真实G05/G06进程session52992本轮确认正常结束exit1：`/tmp/sdk-completion-groups-rework-20261105/acceptance.json`记录G05在2026-11-05T06:41:48Z结束failed，G06共用该场景同为failed；G05.json保留TimeoutError与partial_rows／partial_groups，无重新执行或预算延长。此为旧completion-final包，不属于本轮新产品。没有真实模型调用、CI或新包。


未知返回监控方案被独立审查否决并撤回：尝试将精确内存 unknown publication 交给活监控判断超时，四项源码检查3通过1失败，14.857秒，`/tmp/sdk-live-monitor-unknown-20261105.log`；原失败仍为running，现场`/tmp/sdk-monitor-no-effects-y_8v8goh`。审查指出可信预算耗尽只证明监控观察时已过期，不能证明未知时间的处理器返回已越期，可能将按时返回误判为持久超时。该产品改动已逐段撤回，未构建安装包。新增保留截止前完成时间采集失败不得授权timeout的回归，首次检查通过；撤回后单独复验1项通过2.390秒，`/tmp/sdk-unknown-return-no-timeout-20261105.log`，保留现场`/tmp/sdk-monitor-no-effects-22hcl8gg`。不得继续沿“unknown返回+后来预算耗尽=timeout”修补。准确原返回时间无法确认时须保持unknown，并通过有界公共诊断说明，而不是冒充G12超时结算通过。无真实模型调用或CI。


完成时间未知的只读取证补充：原失败 `/tmp/sdk-monitor-no-effects-19lkwfsw/kernel.settlements.sqlite3` 中，准确 `job/attempt=1/fence=1` 的 `late_thread_fact` 保存 `kind=ok`、`value=late`、`completion_time_known=false`，错误明确为 `InspectionBudgetExceeded: inspection timeout exceeded`。保留信封的 checkpoint.wall_at=1793860201.5585773，原 execution deadline_at=1793860201.5041466，相差约54.431ms；该信封不是获授权的完成时间。源码 `completion_clock.py` 的 owned return capture 将 inspection deadline 绑定原 work deadline；`runtime.py::monitor_published_outcome` 只为已发布 timeout 尝试活监控决定，因此该 ok/unknown 分支不进入新增决定。此证据确定了未覆盖的入口，但不足以证明采样全过程或授予迟到结果权限。另确认已有公共 `Runtime.observe(execution_id, attempt=..., fence=..., timeout=...)` 可有界读取 settlement_obligations，无需新增重复诊断API或调用会驱动维护的 recover_completions。下一修复须验证：仍具精确代次权限的活监控器能否基于可信预算独立确认耗尽；未知时钟／撤销／停止／外来采样仍不得决定，业务返回不能成为超时授权。仅让 wait 提前抛 unknown 不构成 G12 修复。此次未修改产品、运行测试或调用模型，验收状态不变。

monitor-timeout安装包定向验收失败：`/tmp/sdk-monitor-timeout-20261105/result.json`，43项41通过／1失败／1错误／0跳过，143.713秒，进程退出1，149产品Python文件直接字节一致。核心无effect超时仍running，证据`/tmp/sdk-monitor-no-effects-19lkwfsw`；只读核查精确代次entry_state=confirmed，迟到记录实际kind=ok、completion_time_known=false，无monitor决策调用。因此不是单纯timeout发布分支遗漏；不得把未确认返回事实直接授权为超时或成功。应用层测试`/tmp/sdk-expired-effect-entry-ib6sx4pf/evidence.json`未进入延迟边界、adapter0、submitted，wait(5)在Orchestrator提交准入期限耗尽，原错误保留。源码先行5项曾通过21.410秒不覆盖此安装失败；共享时钟未解决及effect准入竞争源码2项通过8.658秒，安装包也通过这两项。deadline/retry新补单项源码通过4.463秒，但代理报告更早一次running尚未归因且尚未给出保留路径，不据后一次通过取消。活监控分支已补准确发布对象、所有published返回入口、原预算／共享时钟、原command截止后不重试及响应丢失精确回执；本地已捕获采样只可在有界budget锁下finish_pending，不确认缺失或外来事实。中英文Wiki同步了限定行为，但实现尚未验收；不构造新包或盲重跑，G12保持失败，G05/G06未通过，本轮没有模型调用、CI或发布。下一必须核对未确认完成事实应如何通过支持的SDK接口向有限AgentRun报告阻塞／恢复状态，禁止将其提升为业务结果权限。

过期effect准入确定性复现与监控修订（源码未验收）：新增tests/test_agents_expired_effect_entry.py，原2秒请求预算，在实际HandlerEffects.execute_once体前延迟到原deadline后0.05秒，不调用模型。首次wait(5)错误，adapter_calls=0，保留`/tmp/sdk-expired-effect-entry-ntsrwwa9`和`/tmp/sdk-expired-effect-entry-before-20261105.log`；独立只读核查确认Kernel无effect、running，保留pending late_thread_fact timeout。live监控器无unfinished effect时原逻辑没有形成Kernel决定，随后fact_only将其降为无权限事实。源码新增活监控超时事务：精确fence／生命周期及仲裁锁／停止及precommit检查，共享预算信封与时钟检查，原command截止后不再排队重试，unfinished effect在同事务进入恢复；不授予迟到事实权限。初次候选用了预算started_at导致精确身份拒绝，已改Kernel started_at，原失败日志保留。新核心无effect超时检查通过4.014秒；最新两项组合1通过1错误11.818秒（`/tmp/sdk-monitor-timeout-budget-20261105.log`），应用层仍submitted，adapter0、延迟边界已到，但监控决策入口没有被调用，`/tmp/sdk-expired-effect-entry-wv57tlh6/evidence.json`。下一需处理：worker先发布timeout时，监控直接返回completion.result而未建立活监控决定；只能在仍存活的监控器与精确已发布timeout事实绑定下决定，不能让恢复器提升late_thread_fact。独立审查提出的时钟、原deadline及提交响应丢失保护已入源码，尚待完整边界审查／验证；无新安装包，不标G12修复或通过，已知缺陷未闭合，不运行CI。没有新增模型调用、推送或发布。

当前completion-diagnostic安装包G12原顺序34项已结束：33通过／1错误／0跳过，231.028秒，进程正常退出1，151产品文件直接字节一致；`/tmp/sdk-completion-diagnostic-20261105/g12/original-result.json`及check.log。唯一错误test_original_deadline_expiry_after_abort_blocks_retry在wait(30)抛Agent store caller deadline elapsed；保留现场`/tmp/sdk-prelaunch-deadline-failure-bu3gk2z9/evidence.json`与`/tmp/sdk-prelaunch-deadline-threads-u8yk0vux/threads.txt`。adapter_calls=0、boundary_reached=false、没有native操作，故没有触达中止后重试边界；effect prepared_at比原deadline晚约24ms，状态performing／Kernel running且无结果，保留完成权限未确认的迟到超时事实。独立只读核查确认这些事实，单点线程快照不能确定此前延迟原因，不能归因于本轮生命周期修订。下一步为effect准备前跨原期限的确定性复现，保留原期限；不通过重跑抹去此失败。当前G12不通过。相同安装包完成交付三模块36项及文档577链接／4README示例／0跳过通过。没有模型调用、CI或发布。

完成失败诊断与当前安装包补证：原G05现场只有捕获候选、没有准确提交回执，异常被吞掉，无法回溯确定失败原因；未声称与已复现生命周期锁竞争同因。源码现将失败阶段与异常类型保留到未确认完成的结果事实，不记录异常正文；准确已提交回执确认后不记录此故障，不授予额外重试或交付权限。定向未知错误持久化检查通过，独立复核未发现具体正确性或隐私问题。新包`/tmp/sdk-completion-diagnostic-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`于同目录env独立安装，包外-I执行，149产品Python文件直接字节相同；完成交付／真实锁竞争／跨执行采样三模块36项通过106.423秒，0失败／错误／跳过，`result.json`及check.log。中英文Wiki同步。原顺序G12技术34项在此同包运行中，原观察预计2–3分钟，session45511，不是完整G12验收；本轮未新增模型调用、CI、推送或发布。原生G05/G06仍未通过，旧包其余真实验收不自动升级为此包证据。

生命周期候选前竞争也已确定性复现并修订：原5秒预算内真实锁持有0.25秒，候选构造前非阻塞获取失败导致running；修订前日志`/tmp/sdk-pre-candidate-lifecycle-before-20261105.log`。结果候选构造现在不要求生命周期锁；构造仅使用捕获的完成时间，不授予结果权限，实际提交仍经生命周期锁／Kernel原权限检查。源码12项通过38.395秒，候选前停止与期限耗尽两项通过6.653秒；独立审查未发现具体权限或并发阻断。中英文Wiki同步。新独立安装包`/tmp/sdk-lifecycle-fixed-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，安装环境同目录env，从包外以-I验证，149个产品Python文件直接字节一致；14项通过44.947秒，0失败／错误／跳过，正常退出，`/tmp/sdk-lifecycle-fixed-20261105/result.json`及check.log。首次构建因只读pip缓存失败，原日志保留；关闭缓存后构建／安装成功。该安装包仅有本组定向证据，不继承completion-final其余真实验收；G05/G06原生结算现场尚未证明与此同因，不标通过。没有新增模型调用或CI／发布。

生命周期完成准入新增确定性缺陷与源码修订：真实生命周期锁占用0.25秒、原工作预算5秒时，已构造且按时返回的候选未能结算，返回running；修复前单项准确失败，证据`/tmp/sdk-lifecycle-admission-before-20261105.log`。源码现在仅在尚未获取生命周期锁、尚未进入决策或消费返回权限时，在原截止与停止检查下重新准入；不重试不明提交。原模块8项通过23.254秒（`/tmp/sdk-lifecycle-admission-after-20261105.log`），新增生命周期等待期间停止／原期限耗尽两项通过5.838秒（`/tmp/sdk-lifecycle-admission-boundaries-20261105.log`）。独立审查未发现该重试循环新的具体阻断，但指出候选构造前的非阻塞生命周期锁入口仍可能直接跳过完成，尚待独立复现与修复。因此此为源码局部进展，不是新安装包或G05/G06通过。原生协作执行session 52992本轮复查仍存活且无最终acceptance.json；不将其存活认定为进展，不重启。既有completion-final证据不升级为本次修订后的安装包证据。本轮未新增模型调用、CI、推送或发布。

G03/G04当前安装包真实组合通过：`/tmp/sdk-completion-files-dependencies-20261105/acceptance.json`，进程退出0。同一240秒原请求链实际执行seed、fast、slow、consumer四个OpenCode Agent，消费者在slow门闩未释放时不启动，齐备后仅执行一次并实际发布FAST_NATIVE|SLOW_NATIVE；四调用同Run、四独立会话、调用预算spent=4。稳定request_id重放无新增执行，同ID不同输入AgentConflictError。fast实际文件写FAST_NATIVE并快照供下游消费，越界及symlink写入原错误保留且外部文件不变。G03附加同包真实文件工具500次路径替换竞争：126次替换，2允许／498拒绝，0错误，外部不变且worker退出；宿主仍须保护root及祖先，不宣称strict／原子写。G03.json/G04.json保留配置、实际rows／session／产物及诊断。此为Linux x64/Python3.12当前包对应场景证据，不扩展到缺失平台；原生清理完整覆盖仍以各专门场景为准。下一缺口G05/G06当前包协作返工及真实工具负例，当前无本轮后台验证。

G16权限撤销同包复验通过：`/tmp/sdk-g16-completion-permissions-settled-20261105/report.json`，退出0，14项checks全true，两宿主host stopped／exit_code=0／app_close_returned=true。原180秒请求预算与600秒观察上限不变；真实撤销运行中／排队请求、准确回执和清理、原权限预算保持、排队从未dispatch、无关角色成功、撤销持久化、service resume不能绕过撤销、新工作拒绝、重启稳定unknown、restore仅未来请求、唯一entry/send归属、close无重启工作均成立。独立只读复核确认新增基准等待属于正常pump结算投影，未弱化后续完整相等／权限检查，未延长原期限。历史首次失败保留，不追溯改写。当前Linux x64/Python3.12已具有G16宿主独占／停止重启、模型取消后代、回执缺失隔离重启、权限撤销恢复四类真实报告；完整租约竞争覆盖及跨平台范围仍需核对，不以此标全部目标完成。下一当前包缺口为G03/G04真实文件／依赖消费及G05–G15其余真实验收，当前无本轮后台验证。

G16当前包权限撤销真实场景首次未通过：`/tmp/sdk-g16-completion-permissions-native-20261105/report.json`，进程退出1，13项checks中12通过、stable_unknown_after_restart=false；两宿主正常关闭，app_close_returned=true。撤销回执／准确权限、排队无执行、无关角色成功、拒绝持久化、恢复仅未来请求、准确adapter entry及send归属均通过。对照`state-differences.json`：重启前基准过早，原未知调用service.quarantined=0而重启后=1；同会话排队调用也从quarantined=0到1，且正常取消finish receipt从None到精确cancelled收据；重启后的两次观察之间无这些差异。验证器proof现等待正常隔离投影及排队取消精确finish receipt后固定基准，完整相等断言／原期限不变，尚未复验，不宣称G16通过，产品未改。cleanup unknown同包10项通过证据保留于后段。当前无本轮活跃原生验证。

G16当前包cleanup unknown真实故障场景通过：`/tmp/sdk-g16-completion-cleanup-unknown-20261105/report.json`，进程退出0，10项checks全true。真实guard清理返回后仅阻断签发清理回执，SDK保留原授权记录／资源预留／执行身份；后续同会话请求隔离而不执行，无关请求普通成功，原预算与恢复时钟权限保持；第二次重启仍保留隔离与预留。该测试观察不是SDK清理授权，未伪造回执或直接写数据库；不宣称模型远端结果已知。原120秒工作预算、600秒观察上限保留。权限撤销场景随后启动，当前结果待定，不标整个G16通过。

G16当前包真实后代取消场景通过：`/tmp/sdk-g16-completion-cancel-native-20261105/report.json`，退出0，13项checks全true，host_close_completed=true。真实controller经普通SDK发送后调用agent_cancel，worker取消前已运行并完成上游HTTP request write；准确后代范围、原冻结期限与预算、普通control receipt、controller结果、worker精确原生清理成立，无关独立服务正常完成。原180秒预算不变；本地请求写入不证明供应商执行／远端撤销，Run未知效果保守处理。第一次命令缺expected-site-packages在参数校验退出2，未启动；补齐参数后仅执行一次真实场景。G16撤销及cleanup unknown范围仍待当前包验证，不标整个G16通过。

G18源码包构建补证：`/tmp/sdk-completion-full-sdist-20261105/result.json`。将当前git已跟踪及未忽略文件的工作区内容（包含用户改动）复制到临时目录，setuptools构建sdist，再从sdist本地无依赖构建wheel；151个产品文件与completion-final安装包直接字节比较一致，无hash。sdist位于同目录sdist/，wheel位于wheel/，build.log保留。此前仅复制产品源／元数据的初步构建另存`/tmp/sdk-completion-sdist-20261105`，不将其当完整工作区源码包。新源码包构建不替代其安装回归或Python／OS／架构矩阵；无发布。当前本轮无活跃验证。

G16同包宿主竞争／停止重启复验通过：`/tmp/sdk-g16-completion-host-competition-settled-20261105/report.json`，进程退出0。原120秒请求预算及420秒观察上限不变，产品无修改。五项主检查全部true；原期限内ordinary_success／service_settled／owner_released四个取样条件均true；重启后服务保持停止、新请求拒绝、提交回执／调用status／完整settled snapshot不变、无新增adapter entry／model send七项全部true。三个supervisor均root_exit=0、cleanup_confirmed=true、kill_signals=0。独立复核提出等待结算可能依赖关闭；主代理查证application.py正常_pump_with_retirement_admitted每轮调用_settle_services，services.settle原子清空owner并置settled，故等待无需host close，并新增最后观测及谓词留存。本实际通过验证了关闭前结算可达，不追溯覆盖原失败。不代表撤销、取消、不明清理完整G16通过。

G01/G13当前安装包检查：`/tmp/sdk-completion-config-isolation-20261105/acceptance.json`首次G01因隔离driver目录漏带Wiki而FileNotFoundError，G13通过；补齐当前双语Wiki文件后，仅重验G01于`/tmp/sdk-completion-config-wiki-20261105/acceptance.json`通过。G01包含YAML/Python等价、四类配置拒绝、双语Wiki完整默认JSON一致与实际CLI有效配置等价。G13证明tools仅SDK工具保证，strict_backend_unavailable在调用入库／运行时execute之前拒绝，三个非法能力声明拒绝；无真实强隔离后端，不宣称其已实现或验收。当前本轮无活跃验证。

当前包G16宿主竞争真实场景失败记录：`/tmp/sdk-g16-completion-host-competition-20261105/report.json`。exclusive_host、original_success_and_authority、owner_closed、reopen_closed均true，stopped_and_stable_replay=false，三个supervisor收据cleanup_confirmed=true且kill_signals=0。已保存facts.original与state/reopen-snapshot.json逐字段对照，差异仅service.owner由原invocation变None、service.state由active变settled；其余完整快照相同。验证器success只等待ordinary_success，可能在服务结算前固定基准。源码验证器现额外等待同原期限内state=settled且owner=None，保持原完整快照相等，细分并保存七个reopen比较、前后status及重启快照。此为验证器改动，尚无重跑通过，不标G16修复／通过，产品未改。首次启动脚本复制因/tmp相对路径错误未执行，改绝对路径后才启动场景。

最新文档检查使用当前安装包解释器通过：577本地链接、4 README示例、0跳过，`/tmp/sdk-completion-g12-20261105/docs-current.log`。独立证据复核确认当前G17资源／监督成功调用同时提供G02本机Linux x64/Python3.12真实调用证据；无需为G02重复启动模型。其余平台及G03–G16对应当前包完整范围仍须逐项核对。

当前安装包CLI实际生命周期通过：`/tmp/sdk-completion-cli-lifecycle-20261105/report.json`。新增可复用`scripts/verify_agent_cli_lifecycle.py`，实际启动serve子进程，14个CLI命令全部退出0；validate/effective与Python一致，服务resume→status accepting true→stop→status false→resume→status true，trigger暂停及恢复状态吻合，最后宿主stop回执后实际退出0并撤销endpoint，未使用兜底terminate／kill。这是空闲宿主／控制操作证据，不提交模型任务，不代替跨Run服务实际续接。原生监督及资源对照、旧API39项、类型六consumer证据见后段；完整旧测试／平台及其余G验收仍未全部补齐。当前本轮无活跃验证进程。

G17当前安装包监督负例全部通过：`/tmp/sdk-g17-completion-supervision-negatives-20261105/report.json`，stale与disabled_and_stop=passed，进程退出0。stale在父真实产物版本变化后拒绝原incident，无admission effect、无子调用，父成功且清理确认；disabled真实父运行期间无监控／诊断子调用，父产物成功；stop在pending观察后取消，准确拒绝agent_supervision_stopped，无子调用、有限3秒观察无后续诊断，supervisor停止，原execution identity／deadline不变且精确清理收据通过。stop只证明本地代理请求入口、取消拒绝及清理，模型结果为unknown_or_cancelled，parent recovery_required，不宣称上游模型成功或任意长期无重启。与stable场景组成同包监督范围证据，不单独覆盖G16完整矩阵。

旧API定向四模块39项通过，80.100秒、0失败／错误／跳过：`/tmp/sdk-completion-g12-20261105/legacy-result.json`及legacy.log，涵盖sdk_convenience/orchestrator/results/recovery，当前site-packages导入。6个现有类型consumer在mypy 2.3.1、目标python-version 3.10、python-executable为当前安装环境下通过，typing.log；本机执行仍Python3.12，不冒充完整Python／平台矩阵。完整CLI端到端、其余旧API范围及G18平台证据仍缺，当前没有本轮活跃验证。

G17当前安装包真实监督stable场景通过：`/tmp/sdk-g17-completion-supervision-stable-20261105/report.json`，原240秒预算，进程退出0。真实父原生存活时无新产物触发诊断；诊断收到原observation并实际执行成功，exact回执重放仍是同一子调用，stable generation仅一个子调用，同Run／原controller预算成立，诊断原生cleaned，父guard清理通过。stale及disabled_and_stop未运行，本结果不代表全G17。

当前安装包补装本地缓存PyYAML 6.0.3后，配置／CLI三模块首次22项21通过1错误、0跳过（6.088秒），`/tmp/sdk-completion-g12-20261105/config-cli-result.json`和config-cli.log。唯一错误为本机socket权限拒绝，未到目标断言；仅该项在允许本机通信环境补验通过，cli-socket-permitted.log，未追溯改写首次22项结果。包含YAML/Python等价及重复键／非法配置拒绝、CLI setup与只读inspection；不替代serve/status/stop/resume端到端及旧API／类型消费者范围。当前本轮无活跃验证。

G12原失败技术回归原顺序34项现于completion-final安装包全部通过：127.490秒、0失败／错误／跳过、进程退出0。`/tmp/sdk-completion-g12-20261105/original-result.json`与`run.log`；151个产品文件直接字节一致。未追加依赖用例，未扩大预算／观察期限，未使用真实模型。此前失败的两秒原期限及监督启动异常场景本轮均通过；该结果关闭本组失败，但不追溯覆盖历史失败，不证明所有调度下必过，也不替代G12业务拒绝／返工／不明效果的其余证据。当前本轮无活跃验证进程。下一缺项为最终包监督、CLI／旧API及更广G01–G18矩阵，不标记整体完成。

同包resources_limited真实对照通过：`/tmp/sdk-g17-completion-limited-native-20261105/report.json`。128 MiB容量、父96 MiB及子64 MiB保持原240秒预算；记录child_waited_under_reservation，父精确原生清理及资源released先于child grant，子成功且精确原生清理确认，有限Run完成。与此前同包resources_disabled构成资源准入开关两组通过，不代表G17监督／CLI／旧API通过。脚本固定退出1的完整G17未运行语义与前段相同。下一步原顺序34项G12技术回归，范围不扩大。

同包真实失败路径复验已关闭本次失败：`/tmp/sdk-g17-completion-disabled-native-20261105/report.json`中resources_disabled=passed。原240秒预算不变；真实父Agent完成、有限Run完成、同Run子Agent成功，实际产物CHILD_NATIVE_OK，精确子原生清理确认；父仍存活且gate持有期间子可进入。使用当前独立安装包与已授权本地反代。验证器进程退出1是脚本固定返回值（本脚本尾部return 1，完整G17始终not_run），不是全G17通过，亦不应将退出码视为本场景失败。未运行resources_limited或监督场景，不覆盖G12/G16/G18。原失败证据保留。

当前安装包定向验证已结束：`/tmp/sdk-completion-final-20261105/result.json`，41通过、0失败、0错误、0跳过，77.831秒；导入来自独立环境site-packages，151个产品文件直接字节一致。日志为同目录`check.log`。范围为完成交付、监控恢复、严格期限、延迟首次决策、owned完成争用、pending确认与跨执行guard七模块；不能替代G12原34项或G17真实任务链。随后仅对原失败的resources_disabled真实OpenCode任务链启动同包复验，保留原240秒预算，输出目录`/tmp/sdk-g17-completion-disabled-native-20261105`，结果待定。以下各段为按倒序保留的历史记录，其“运行中／尚未构建”等描述不覆盖本段当前状态。

最终源码组合40项39通过／1失败70.211秒（sdk-owned-completion-final-source-20261105.log）；唯一失败为原中断保留测试要求诊断map最后值必须是原错误，实际后续lifecycle ack诊断覆盖。测试改为记录准确map写入，断言原错误确已记录，并保留原异常identity、Kernel无结果及持久captured_failure断言；未改变产品结果。该单项及跨执行回归2项通过4.095秒（sdk-owned-completion-diagnostic-fix-20261105.log），不追溯覆盖40项失败。新completion-final安装包构建／安装中，计划对最终包验证完整41项相同范围；整体G12/G17/G18及所有G验收仍未完成。

跨执行源码回归通过：新test_runtime_cross_execution_completion_guard共享真实Runtime／Kernel及activation，A返回捕获后B才建立真实未确认采样；A首次因全局guard拒绝，B原marker／owner保持，随后B原线程ACK同token及输入事实，A同candidate重试成功，两handler各一次。单项2.279秒，证据`/tmp/sdk-cross-execution-completion-qxcb715m/evidence.json`；有效运行在修复后，不宣称before。存储在准确guard拒绝处提供独立私有证据（不同于failed BEGIN），原拒绝异常／物理连接须完全退出事务后核验同异常、无cause、同连接可用空闲，才可在原期限内等待；独立复核确认该guard在结果／权限写入及return能力消费前，未确认或失败清理不通过核验。双语Wiki同步。最终同范围40项源码检查运行中，仍无新安装包／真实G17通过。

相邻31项源码检查29通过／2失败61.597秒（sdk-owned-completion-impact-20261105.log）：新期限拒绝了按时返回但效果列表收集晚于截止的首次决策，属于行为回退。现保留既有首次机会，仅竞争后的额外尝试受原工作截止约束；两原回归加七项检查9通过20.441秒（sdk-owned-completion-late-contract-20261105.log），不追溯覆盖31项失败。独立复核又发现已有context采样ACK只试一次；新增真实writer0.25秒／原3秒回归修复前准确失败，现同pending tuple/token/fact在原期限及权限检查下继续确认，两项通过0.713秒（sdk-pending-return-retry-after-20261105.log），包括uncaptured拒绝。最新源码尚待最终独立复核、完整同范围检查、新安装包及真实G17；另一执行全局采样竞争尚未验证。

owned-completion后续源码7项通过12.718秒（sdk-owned-completion-monitor-gate-20261105.log），尚无新安装包。已分离owned提交的原工作截止与短BEGIN准入；此前7项组合两失败的新诊断捕获到global budget sample is unresolved，而非继续推断短截止。监控现只在可非阻塞取得completion_gate时采样，返回提交占用时投影保留预算，避免在返回事实与提交间新增全局标记；无采样绕过。七项覆盖准确同candidate成功／普通失败、停止、原期限、无证据异常、提交成功响应丢失、已准入body延迟。相邻完成交付／监控／严格期限检查运行中，独立复核未终态；当前receipt-final真实G17失败仍不被本源码结果覆盖。

owned-completion源码修订进行中：新增确定性回归首次23项组合22通过1失败42.102秒（测试类导入带入原模块，已改为模块别名，原结果保留）；实际目标原5秒预算／writer0.25秒返回running。新增失败BEGIN准确异常与物理连接私有证据，runtime仅在完全退出且同连接可用空闲、无cause时重试同candidate／captured_return，并逐轮释放生命周期锁、检查停止／原期限。修订后单项通过1.870秒，六项边界通过11.154秒（sdk-owned-completion-boundaries-20261105.log）：成功、普通失败、停止、原期限、无证据错误、成功提交响应丢失；均非安装包验收。新独立审查发现短准入截止被施加到事务体，新增真实已准入body延迟0.12秒测试确认失败（sdk-owned-completion-body-before-20261105.log），正在分离短BEGIN窗口与原工作提交截止；未标记修订最终通过。

完成提交短时竞争已用真实SQLite确定性复现：`/tmp/sdk-completion-contention-transfer-20261105.log`、`/tmp/sdk-completion-commit-probe-b_5dhlfe/trace.json`。原5秒预算内，独立writer在准确owned completion调用前持锁0.25秒，实际0.1秒提交抛database is locked；处理器成功返回并有candidate，run_once却保留late_thread_fact、返回running，公共recover_completions返回unknown。调用跟踪未发生transfer_late；定位到runtime.py正常run_once结算也无条件fact_only=True（约4514行）。这修正前一段“late_thread_fact必来自监控放弃”的过强推断：真实G17具体分支仍未知，但短竞争可独立产生相同结果，且前段独立审查也漏看该正常入口。探针两次诊断API参数错误原日志保留，valid/transfer日志为参数修正后执行。下一修复应在原worker拥有准确authority时，对确定未应用的完成准入竞争重试同一candidate／captured_return，仍受原期限、停止及撤销约束，不在迟到恢复中授予权限。

receipt-final失败只读诊断进一步定位：子runtime effect于1793850934.499提交succeeded/DONE，artifact answer=CHILD_NATIVE_OK，两准确原生receipt cleaned；settlement-notes于0935.191记录handler_outcome=ok，0935.710记录driver_close。settlement-record保留原completed_at=0934.8838098、completion_time_known=true、准确succeeded候选，但payload_kind=deferred、late_thread_fact、没有Kernel committed result。原始SELECT证据execution-detail-observations.json、settlement-observations.json在同失败目录。独立源码核查确认late_thread_fact来自监控放弃后的事实交接，不授权恢复CAS；现有证据未保留触发交接的分支／完成提交异常，不能推断死锁。下一最小复现应针对真实短时完成准入失败与监控交接，禁止将迟到事实直接提升为成功权限。无新增模型调用或宽范围重跑。

receipt-final真实G17无上限场景已终态failed：`/tmp/sdk-g17-receipt-disabled-native-20261105/report.json`，同原240秒预算。父子真实重叠和父准确原生身份成立，父本次succeeded（control cancel_requested=0），未重复前包收据超时取消；但run.wait在原期限超时，子Kernel于截止后约0.075秒cancelled，错误Kernel control admission budget elapsed，controller仍running。原始只读终态terminal-observations.json及control-terminal-observations.json保留。不能将父完成视为整个场景通过，也不能仅从终态认定子取消根因；下一步须检查子运行／完成交付事实。进程正常退出1，当前无本轮活跃模型或回归。

receipt-final文档检查：当前独立安装解释器运行check_docs，577本地链接、4个README示例通过、0跳过，正常退出0；`/tmp/sdk-receipt-final-20261105/docs.log`。本地Wiki导出25页至同目录wiki-preview，引用release/0.8.0，仅预览未发布，wiki-export.log保留。此检查不证明G18平台或完整回归通过。

receipt-final当前安装包：`/tmp/sdk-receipt-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立venv、/tmp下-I，151产品文件直接字节一致。收据重试及结果交付相邻37项通过50.459秒，0跳过，正常退出0；result.json、check.log在同目录。该结果不覆盖此前原34项组合失败。真实G17仅resources_disabled复验已启动，原240秒预算，证据目标`/tmp/sdk-g17-receipt-disabled-native-20261105/report.json`，完成前不记通过；资源有限场景与其他G项仍按各自产物证据区分。

收据重试修订源码复验：37项通过47.361秒，`/tmp/sdk-child-receipt-reviewed-20261105.log`，正常退出0。前次37项唯一错误为旧测试要求忽略其他所有者未确认全局采样，与共享水位安全合同冲突；修正为保留原错误及BudgetClockUnknownError cause、不读取子结果、不完成其他所有者且保留原标记／事实。产品保护未放宽。独立审查确认该测试合同修正及收据准确超时分类无新增确定阻塞；清理cause负例只证明分类，不证明真实回滚失败恢复。双语Wiki已同步。新receipt-final包已构建，独立安装验收尚待结果，不覆盖empty-final原73项失败。

当前包G17真实资源执行已终态：`/tmp/sdk-g17-empty-final-native-run-20261105/report.json`，真实OpenCode1.18.32/local模型、本地授权反代、原240秒场景预算。resources_limited通过：128MiB容量下父96MiB保留时子64MiB无runtime effect及原生操作，父准确原生清理收据及持久资源释放先于子准入；子真实执行、产物和清理成立。resources_disabled失败：已证明父performing且准确原生操作仍authorized时子实际进入，之后child succeeded，但parent被cancelled，原原因`budget receipt exhausted its original window`，当时根期限仍余约25秒；只读原始终态另存同目录disabled-terminal-observations.json。无上界对照完整成功故仍缺，G17整体不通过。该证据属于empty-final包，不迁移为后续源码通过。

据此新增真实SQLite采样收据回归`tests/test_child_budget_receipt_retry.py`，实际编码窗口耗尽在修复前直接抛出同名TimeoutError（`/tmp/sdk-child-receipt-before-20261105.log`）。源码children控制重试新增准确超时分类，仍共用原工作期限、原token和输入事实；独立审查要求排除带cause的清理未知，已收紧。测试修正了“输出canonical floor与输入必须同对象”的错误断言，仅要求重试输入事实同对象且真实持久input_json准确匹配；两者不能混同。源码负例及影响检查进行中，尚无新安装包证据，也未认定此缺口解释先前监督取消。

有失败事实采集的原前序序列复验：同empty-final包原顺序至监督重试成功用例24项通过93.815秒，正常退出0，`/tmp/sdk-empty-final-20261105/supervised-prefix-result.json`及supervised-prefix.log。原2秒用例本次中止回调返回余0.081秒；未发生取消，未取得取消根因新证据。不覆盖原73项失败，也不继续无界重跑。转向独立G17真实资源场景；首次验证器与env嵌套导致隔离预检拒绝，未到模型调用，`/tmp/sdk-g17-empty-final-native-20261105/report.json`保留；脚本移至独立`/tmp/sdk-native-drivers-empty-20261105/scripts/`后启动同包两个真实场景，均保留240秒原预算。结果以新目录`/tmp/sdk-g17-empty-final-native-run-20261105/report.json`为准，在结果出现前不记通过。

最新安装包`/tmp/sdk-empty-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`已包含空队列只读修复；独立venv、/tmp下-I，151产品文件直接字节一致。原34项顺序后追加39项依赖交付检查，共73项71通过／1失败／1错误／0跳过，132.514秒，进程132.946秒正常退出1（同目录original-result.json、exit.json、run.log）。原期限用例中止回调返回晚约0.046秒；监督重试成功用例异常返回cancelled，原异常文本已保留，但当时夹具仅对TimeoutError采集记录，未保留取消来源的关闭前事实，不能补造根因。后续仅测试观察器扩充该成功用例AgentExecutionError的有界公共读取、控制记录和执行记录采集；原异常原样重抛，预算与断言不改。相同安装包两项监督重试定向15.022秒通过，supervised.log，不能覆盖73项失败。当前无本轮活跃回归；G12保持failed，G14–G18未完成状态不变。

空依赖轮询源码修复已通过独立审查和39项相关测试（8.580秒，退出0，`/tmp/sdk-empty-delivery-reviewed-20261105.log`）。新增只读预检共用原时钟／代际校验与受锁保护的进程内高水位；不写持久时钟，不缓存空结果，任意未确认回执均进入原新写事务领取。真实写锁下空轮询通过；空后新增真实产物事件下一轮准确投递一次，随后不重复；时钟缺失／损坏、回拨、stale epoch、非法参数均拒绝。领取回执丢失测试改为只在领取写事务提交后注入，预检不伪装成领取；旧失败日志保留`/tmp/sdk-empty-delivery-after-20261105.log`。双语Wiki同步边界。尚未新建包含此修复的安装包，也未证明它是先前30秒等待超时的根因；G12及最终验收不变。当前无本轮活跃测试。

当前安装包`/tmp/sdk-progress-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立venv、/tmp下-I导入，151产品文件直接字节一致。原34项顺序后追加25项回归，共59项57通过／1失败／1错误／0跳过，176.456秒，进程176.882秒正常退出1；同目录original-result.json、exit.json、run.log。原期限用例abort回调返回时已晚约0.291秒；监督重试用例原30秒wait到期。后者关闭前快照`/tmp/sdk-retry-matrix-wait-timeout-xeofcwif/threads.txt`显示pump持app锁处于dependency_host.deliver_one的COMMIT；单次快照不能证明持续阻塞或统一根因。所有新增采样及进展回归通过，不抵消原失败。后续确认空依赖队列每轮仍持久写时钟，新增真实SQLite写锁回归在修复前因原0.2秒准入耗尽而失败，`/tmp/sdk-empty-delivery-before-20261105.log`；相关源码修复正在验证，尚非新安装包接受证据。G12仍failed，没有完整回归或模型调用在运行。

进展误报修复（后续源码，尚未重建安装包）：真实调用在adapter等待期间，两次无状态变化的pump应返回False；新增`tests/test_agent_pump_progress.py`修复前在预期断言失败（`/tmp/sdk-pump-progress-before-20261105.log`）。_pump现只对新受理trigger或已确认dependency delivery报告进展，保留_submit显式wake及定期协调，不将pending/open-plan库存本身当作进展。修复后真实调用恰好完成一次，加资源退役／关闭竞争4项通过5.287秒（`/tmp/sdk-pump-progress-after-20261105.log`）；触发器、服务实例、依赖宿主12项通过92.939秒（`/tmp/sdk-pump-progress-liveness-20261105.log`），均正常退出0。独立审查未发现确定活性阻塞；未变化open-plan-only及主机轮询次数尚非新测试的直接断言范围。双语Wiki已同步。不宣称此修改解释或修复原2秒用例。当前安装包原34项仍33通过／1失败；G12保持failed，没有回归仍在执行，无模型调用、CI或发布。

保留前序负载的耗时诊断已结束：`/tmp/sdk-owned-return-final-20261105/diagnose-prefix.log`及diagnose-prefix.json，原顺序运行至目标用例共20项，19通过／1失败／0错误，68.442秒、正常退出1。目标本次进入adapter时余0.445秒，prepare等待app锁0.062秒、总计0.240秒，abort回调返回时已超原期限约0.05秒；故未满足“先确认中止、再耗尽原期限”的测试前提，不能算目标场景通过。实际失败与原34项calls=0的失败阶段不同。现场`/tmp/sdk-prelaunch-deadline-failure-jevdn4er/evidence.json`、`/tmp/sdk-prelaunch-deadline-threads-9jp1sp4_/threads.txt`保留；没有重试、期限扩大或模型调用。不把有记录的调度／存储耗时直接等同死锁或预算重置缺陷，尚无可据此直接实施的确定产品修复。

剩余原期限用例单次耗时诊断：同owned-return安装包、原2秒预算／断言不变，`/tmp/sdk-owned-return-final-20261105/diagnose.py`、diagnose.log、diagnose.json。方法包装仅收集时间、不重试；本次通过3.612秒，adapter进入仍余0.553秒，中止回执返回余0.252秒。与前述组合中calls=0失败不是同一执行，不覆盖失败。观测到16次pump（跨线程累计2.664秒，含锁等待及嵌套，不能当作串行总耗时）、13次reconcile、59次plan读取；纯读取单次大多低于10毫秒。独立源码核查确认pending/open-plan库存会被当作progress触发额外wake，但回调仍受周期约束，不是无界紧循环，亦未证明导致原2秒失败；未据此修改产品。当前没有本轮活跃测试，G12保持failed；下一证据应在实际失败期间记录耗时，不能用本次通过声明修复。

最新安装包复验：`/tmp/sdk-owned-return-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立venv、从/tmp以-I导入，151产品文件直接字节一致。原34项顺序不变，33通过／1失败／0错误／0跳过，测试141.877秒、进程142.207秒正常退出1；`original-result.json`、`exit.json`、`run.log`同目录。此前两项锁释放后恢复等待本轮通过；不宣称所有时序下已消除。剩余`test_original_deadline_expiry_after_abort_blocks_retry`没有进入adapter（calls=0，boundary_timings=[]），与此前进入adapter后耗尽期限的现场不同。原始证据`/tmp/sdk-prelaunch-deadline-failure-dbbuqug5/evidence.json`及`/tmp/sdk-prelaunch-deadline-threads-41rzgibi/threads.txt`：2秒链预算开始于1793847927.872589，Kernel started_at为1793847928.543857，handler预算started_at为1793847929.013609，runtime effect准备于1793847929.615979，随后原期限到期；没有原生操作或模型调用，保持recovery_required而不重试。已证明启动和前置操作消耗窗口，未证明哪一步持锁或耗时的根因。G12仍failed，不整组盲目重跑；此块优先于下文旧包状态。无CI、推送、发布。

后续源码修复（尚未建立新安装包证据）：托管线程成功／普通异常捕获传递入口保存的原work deadline，序列化捕获每次准入及重试后重查确切注册所有者、active、stop及revocation；原单次0.1秒上限及采样事实保留规则不变。独立源码审查未发现确定阻塞缺陷，但已经开始的存储操作不可瞬时抢占。真实SQLite写锁成功／异常恢复、停止中断成功／异常捕获、active撤销、截止耗尽及相邻原始收据／采样测试24项通过8.752秒，`/tmp/sdk-owned-return-boundaries-final-20261105.log`；完整Runtime v8交付／取消／重启模块22项通过47.488秒，`/tmp/sdk-owned-return-runtime-20261105.log`，两者正常退出0。中英文Wiki已同步源码边界。未运行CI或模型调用。以上不覆盖当前安装包原34项的失败；仍需新包复验，G12及整体目标保持未通过。

目标未完成。以下状态优先于后文按时间保留的历史记录；历史包通过不自动迁移到新包。

- 当前安装包：`/tmp/sdk-observation-reads-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`。本轮修订三项纯读取写锁竞争；源码相关19项及权限／原生资源24项通过，独立审查无本范围阻塞。
- 本轮安装包影响检查已结束：`/tmp/sdk-observation-reads-20261105/impact-result.json`，151产品文件逐字节一致；74项69通过／2失败／3错误／0跳过，268.576秒，退出1。原34项31通过／3等待错误；追加40项有2项测试子进程导入失败。两项导入已修复且同包从/tmp隔离定向通过1.182秒，不追溯覆盖74项失败。当前无回归在运行。
- G12仍failed。当前包app锁／orchestrator写锁释放后的恢复等待各超时，原期限用例也在30秒观察截止时超时。关闭前栈已保留，当前进程正常结束；快照只显示当时SQLite配置、准入及验证位置，未证明持续阻塞时长或统一根因。
- 后续同包13项时序诊断11通过／2错误（`/tmp/sdk-wait-timeline-20261105/result.json`）。两个失败均确认测试写锁已回滚、连接已关闭、holder已退出且适配器已返回；只读结算记录均为完成时间捕获的InspectionBudgetExceeded，结果未获交付权限（同目录settlement-snapshots.json）。这证明这两个现场的直接失败原因，不证明第三个超时同因。
- 新增真实SQLite确定性回归`test_owned_return_survives_writer_contention_within_original_work_budget`：在原2秒工作预算内，将独立连接写锁持有0.3秒；当前线程owned-return捕获在单次0.1秒窗口内因BEGIN IMMEDIATE竞争失败。原始失败栈`/tmp/sdk-owned-return-writer-before-20261105.log`。测试线程均已退出，未修改业务预算；这是已复现、尚未修复的产品缺陷。后续修复必须保留确切所有者和原期限，并验证停止／撤销不能因延长捕获等待而失效；不能仅扩大超时。
- G14四窗口仅对plan-read包的Linux x64／Python3.12范围通过；当前包实际调用及故障影响复验仍缺。
- G15缺宿主可信token计费上界合同及真实计量验收；G16缺最终包完整停止／撤销／竞争／未知清理矩阵；G17缺完整旧API／监督／资源验收；G18缺最终包完整回归及其他声明平台／Python版本证据。
- 本轮无模型调用、CI、推送或发布。各G01–G18完整合同仍按Goal文件执行，不以本摘要或局部绿灯降低标准。

## 历史证据与诊断记录

线程继续执行超时的有界诊断（2026-11-05）：仅原 test_run_wait_app_contention_returns_before_lock_release，原断言／20 秒等待不变，最多三次、遇错即停；保留全部临时目录并包装真实 _capture_owned_return 记录错误。三次均通过，9.379 秒，正常退出；三次捕获成功约 .035–.044 秒，无捕获错误。原始 `/tmp/sdk-wait-return-diagnostic-20261105.log`、events jsonl、result／roots json 均保留。这不能解释旧 54 项组合中的超时，也不证明稳定性，不继续无界重跑。独立只读核查指出线程捕获持有 completion_gate、预算锁及原所有权；单纯将 .1 秒扩为执行期限可能改变停止／撤销和待处理交接，故没有依据猜测延长它。

G15 token 链路核查确认：当前两个入口拒绝非空上限，代理只扣模型请求次数并原样转发响应，尚无 token 预留或 usage 提取。现有 ApplicationBudget 分组预留／结算已具备原子及未知语义，下一必要实现是可信计量合同与实际代理接入，不能仅放开配置校验或做请求结束后的累计。具体边界记录于 [token 预算设计](SDK_0_8_0_TOKEN_BUDGET_DESIGN.md)；该文档不是实现或验收证明。G12/G14/G15/G16/G18 状态不变。本轮无 CI、完整回归、真实模型调用或发布。

连接配置竞争修订后的当前包局部验证（2026-11-05）：AgentStore 的 synchronous 配置仅对真实 SQLite 竞争在调用者原截止内重试；作用域外沿用原策略，失败保留连接关闭证据。独立复核未发现该限定修订的新阻塞。之前两个原失败按原断言／期限在源码保留现场运行，均通过，8.400 秒、正常退出；日志 `/tmp/sdk-wait-orchestrator-retained-20261105.log`，现场列表及结果 `/tmp/sdk-wait-orchestrator-retained-result-20261105.json`。这不解释此前不同执行的 20 秒继续执行超时。

修订后 wheel `/tmp/sdk-wait-config-cutoff-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 独立安装，从 /tmp 以 -I 运行四模块测试快照，150 产品文件直接字节比较一致；17 项通过，0 失败／错误／跳过，27.204 秒、正常退出。证据 `/tmp/sdk-wait-config-cutoff-installed-result-20261105.json` 与 installed 日志。覆盖七种实际 Agent 等待锁竞争、状态库事务／提交门及 Kernel／Orchestrator 调用者期限隔离与恢复。双语 Wiki 已同步准入范围及未完成说明。此前 54 项组合的两个错误及非正常退出不被覆盖；其中继续执行超时仍待有失败现场的根因分析。G12/G14/G15/G16/G18 保持未完成，没有运行完整回归、CI或真实模型调用。

Orchestrator 原等待期限修订未验收（2026-11-05）：实际 AgentRun 写锁复现 wait(.03) 在锁释放后约 .210 秒才返回；Invocation 同组通过，原证据 `/tmp/sdk-wait-orchestrator-before-20261105.log`。当前源码将 per-instance／per-caller 原绝对截止传入连接配置、BEGIN 准入和已确认 BUSY 且事务仍有效的 COMMIT 重试；嵌套只能收紧，不重放事务内容，作用域外保留原策略。独立审查在限定准入／提交前范围未发现阻塞。源码 Agent／状态库 27 项通过，26.364 秒（`/tmp/sdk-wait-orchestrator-focused-20261105.log`）；Orchestrator 截止／公共兼容／初始化清理 21 项通过，19.171 秒（`/tmp/sdk-orchestrator-deadline-compat-20261105.log`）。

但是当前独立安装 wheel `/tmp/sdk-wait-orchestrator-cutoff-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 的 54 项组合出现 2 个错误，61.784 秒，0 跳过；150 产品文件直接字节比较一致。结果 `/tmp/sdk-wait-orchestrator-cutoff-installed-result-20261105.json` 及 installed 日志。错误均在解除锁后的原 run.wait(20) 继续执行检查：一项 AgentStore 配置 PRAGMA synchronous=FULL 直接 SQLITE_BUSY，一项 Orchestrator 检查发现原等待期限已耗尽。后者根因尚不明确，不得用后续不同执行通过抹去。结果写出后进程仍存活，核对确切 PID／启动 tick／命令、保存线程等待信息后 SIGTERM 仅该临时进程；证据 `/tmp/sdk-wait-orchestrator-cutoff-exit-20261105.json`，不记正常 SDK 退出。

状态库配置竞争已在源码补原期限内重试，当前未形成修订后安装包；仅复跑这两个原失败并保留现场。其他读取、协调锁、资源恢复路径及系统调用抢占仍未证明，G12/G14/G15/G16/G18 不关闭。本轮未进行完整回归、CI或真实模型请求，没有推送发布。

Agent 状态库等待期限的安装包验证（2026-11-05）：AgentStore 现按当前调用者／存储实例继承原绝对期限，取消该作用域内固定五秒 SQLite busy 等待；仅在原期限内重试 BEGIN IMMEDIATE 准入。事务内容不重放，提交前检查原期限。独立审查发现直接将 busy timeout 置零会使回滚日志模式下受读取者阻塞的提交过早失败，已修订为仅对 SQLITE_BUSY 且原事务仍有效的提交重试；明确未提交时到期回滚并结清 root owner，无法确认的提交／中断仍保留原未知围栏。复核未发现该限定范围的新阻塞问题。

当前 wheel `/tmp/sdk-wait-cutoff-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立安装环境 `/tmp/sdk-wait-cutoff-installed-20261105`。从 /tmp 以 -I 运行测试快照，150 个产品文件直接字节比较无差异；七模块 31 项通过，0 失败／错误／跳过，22.476 秒，正常退出。证据 `/tmp/sdk-wait-cutoff-installed-result-20261105.json` 与 `/tmp/sdk-wait-cutoff-installed-20261105.log`。覆盖真实 AgentRun／Invocation 的状态库写锁、应用／Kernel 锁，超时释放锁后同一执行成功且适配器仅调用一次；真实读事务阻塞普通及 RuntimeHost 提交门的提交，覆盖锁释放及原期限耗尽，内容只执行一次、回滚或提交结果准确、无多余未知围栏。原提交尝试身份、严格控制期限及中断锁清理测试保持通过。源码先行组合 25 项通过，18.405 秒（`/tmp/sdk-wait-store-focused-20261105.log`）。

同步中英文 Wiki，明确这只是调用者准入和提交前的有限保证，不是系统调用抢占或整个 wait 的最终验收。Orchestrator StoreMixin._connect 仍默认 SQLite timeout=30，其他协调锁／存储路径尚未逐项复现并传递期限；实际资源恢复到 Kernel 读取锁的完整路径亦未单独验收。当前 G12 原安装包失败已在矩阵改为 failed，不能继续仅标为 not_run；技术重试、token 配额、完整恢复／停止及平台矩阵仍未完成。本轮未运行完整回归、CI或真实模型服务调用，没有推送／发布。

等待期限修订（2026-11-05，源码局部验证，未形成当前安装包）：原持有 Kernel 锁的真实 AgentApp 复现中，wait(.03) 等待约 .487 秒才返回 TimeoutError（`/tmp/sdk-agent-wait-kernel-before-20261105.log`）。现应用锁准入及 Kernel 控制操作继承同一个调用者绝对截止时间，按线程／Kernel 隔离，嵌套只能收紧，退出恢复上下文；不延长业务预算、不取消或重提原执行。三种实际竞争覆盖 AgentRun／Invocation 的 Kernel 锁及 AgentRun 的应用锁，解除锁后同一执行成功且适配器只执行一次。连同上下文隔离、嵌套、锁所有权和原严格期限／中断测试共 12 项通过，11.435 秒（`/tmp/sdk-wait-admission-focused-20261105.log`）。

独立只读审查指出两个未覆盖入口：Kernel `_read_lock` 和 AgentStore 的固定 5 秒 SQLite 写锁等待。前者现复用调用者控制准入，新增真实读取锁竞争负例；4 项调用者期限检查通过（`/tmp/sdk-wait-read-deadline-20261105.log`）。该读取路径补丁尚需独立复核及实际资源协调路径测试。后者尚未修复，其他存储／协调锁也未完成逐路径核查，因此绝不声称整个 wait(timeout) 已有完整有限期限保证。G12／G15／G16／G18 保持未完成。本轮未运行完整回归、CI或真实模型服务调用。

当前预算／技术重试组合核对（2026-11-05，同 native-cutoff wheel）：六模块发现 64 项，49 通过、15 因本地 AF_INET bind 权限不足跳过，10.919 秒。原证据 `/tmp/sdk-current-budget-retry-installed-result-20261105.json` 与 installed 日志；runner 的 passed=true 仅表示 unittest 无失败，不能忽略日志中的 15 项跳过。通过范围含分组预算原子性、父子准入与原事实恢复；不证明 Agent 配置 token 上限执行。

随后仅用所需本地端口权限补跑原 15 项 technical_retries；无模型或外部服务。测试结果 224.887 秒，8 个 failure、6 个 error（包含 subtest），无跳过；结果 `/tmp/sdk-current-technical-retry-installed-result-20261105.json`、完整日志同前缀。具体包括 expected prelaunch retry 未发生（adapter.calls 1 而预期 3）、观察器未进入第二次重试、取消／预算故障注入未到达其目标分支。测试故障入口为不透明 socket 工厂；当前路径保留未知所有权，不生成可信 prelaunch 中止回执。不能靠 errno 或清除 pending 令其通过。G12 当前包确实失败，不再仅有历史失败说明。

原声明 wait(30) 的一次堆栈显示 AgentRun.wait -> _pump -> _reconcile_one -> sync_execution -> Kernel.get 在 _control_lock 等待；该单次堆栈和整套耗时不证明锁连续持有多久，但证明该等待路径未向 Kernel.get 显式传递调用者剩余期限。测试结果落盘后进程仍活着，核对准确 PID／启动 tick／命令后保存 82 条线程等待信息，以 SIGTERM 终止仅该临时测试进程；不得标记正常 SDK 退出。退出证据 `/tmp/sdk-current-technical-retry-exit-20261105.json`。主测试及业务超时未修改，未因观测超时重启。G12／G15／G16／G18 仍未完成，本轮无模型调用、完整回归、CI、推送或发布。

原生完成采样使用入口原期限的当前包验证（2026-11-05）：定位到 worker 在尚未注册自身采样时，被另一条同执行 sampling 标记挡在 _begin_budget_sample 的事务内检查（supervision.py:171）。诊断副本只包装异常记录，原预算与断言不变，5 项进程模块中 success 失败；原始 `/tmp/sdk-clock-owner-trace-run-20261105.log` 及按 PID 命名的 jsonl 保留。记录能证明阻塞发生于另一本地无所有者的 guard，尚不能归属具体生产进程。新逻辑仅在自身无标记、未采样时等待正常准入，不删除或借用外来标记；永久外来标记仍保持未知。

进一步当前包证据表明单个 .1 秒控制窗口不足以覆盖原工作预算内的短暂存储竞争。POSIX／Windows worker 现仅在入口通知成功后，保留同一确认包的 deadline_monotonic 并传入完成捕获；缺少有限确认期限则仍为原单窗口。每个存储／锁尝试保留 .1 秒或更小配置上限，全部尝试共用入口原截止；elapsed-only 原预算投影只收紧，不延长。采样前保留原 marker，采样后仅确认同一事实；返回已知完成前再次检查预算。独立审查指出入口通知失败和休眠期间经过时间两处边界，均修正。同步更新中英文 Wiki。系统在同步数据库操作内部休眠时无法承诺瞬时中断控制写入；过期后的事实发布本身不授予及时完成结果，外层／监督器／父进程仍各自检查。未声称该物理抢占能力。

当前 wheel `/tmp/sdk-clock-native-cutoff-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立环境 `/tmp/sdk-clock-native-cutoff-installed-20261105`。四模块 84 项全通过（34.178 秒），从 /tmp 以 -I 运行复制测试快照，150 个产品文件直接字节比较无差异。原失败进程树 success／exit／timeout／cancel 均满足原断言。新检查覆盖跨多个短控制窗口、真实 SQLite 写锁释放、保留外来 guard、不重复采样、异常因果链及两次操作间 elapsed 突然推进不再尝试。证据 `/tmp/sdk-clock-native-cutoff-installed-result-20261105.json`、对应 installed 日志和 provenance。此前源码 57 项中 oversized scalar 检查的一次 InspectionBudgetExceeded 原失败 `/tmp/sdk-clock-native-cutoff-source-20261105.log` 仍保留；最终安装组合包括该原测试并通过，不修改其原窗口。

同一安装包 G01 integration 通过（`/tmp/sdk-clock-native-cutoff-g01-20261105/G01.json`、acceptance.json），核对配置／CLI／双语 Wiki 默认值。文档检查退出 0：576 个本地链接、4 个 README 示例全部通过、0 跳过（`/tmp/sdk-clock-native-cutoff-docs-20261105.log`）；此前中文 README 第二例失败的两秒预算与断言未改。先前 foreign-sampler 包 82 项有 timeout 分类失败，以及中文 README next 仍 database is locked 的现场均保留；不覆盖旧失败。当前结果收敛上述具体完成采样／文档复现，未进行任意次数稳定性宣称；其他 G14 故障窗口、G15 完整预算能力、G16 全组合及 G18 平台／完整候选验收仍未闭合。本轮没有模型调用、CI、完整回归、推送或发布。

原期限内 SQLite 竞争重试修订（2026-11-05）：完成事实捕获仅对无显式异常原因链的 SQLite 竞争重试，未采样阶段保留原 token；采样后仅通过原事实 ACK，不重新采样，不重置期限。独立审查发现清理异常可能包装原权威错误，已同时修订 completion_clock 和 budget_capture 的重试判断，因果链不得重试。新增 begin／finish 竞争、原事实单次采样、清理异常因果链及真实 SQLite 写锁占用到原期限的未知检查。源码模块 54 项通过（15.027 秒），追加原事实因果链单项通过；最终安装包包含 55 项完成时钟检查。

当前新 wheel `/tmp/sdk-native-clock-contention-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 安装后四模块共 80 项，79 通过、1 失败（32.877 秒），150 产品文件直接字节比较无差异。证据 `/tmp/sdk-native-clock-contention-installed-result-20261105.json`、对应 installed 日志／provenance；进程树 success 仍为 running。保留现场 `/tmp/sdk-clock-suite-retained-83t8xvy3`，只读 settlement 确认为 completion_time_unknown／budget_clock_sample_unresolved:sampling；不是本次 OperationalError 分支。独立复核未发现有限重试的新具体缺陷，但未决采样冲突未修复，G14／G15／G18 不关闭。

修订前保留现场组合 75 项 2 失败（35.300 秒），原日志 `/tmp/sdk-native-return-clock-retained-suite-20261105.log`：tree 为 database is locked，good 为 sampling 未决；压缩只读证据 `/tmp/sdk-native-clock-contention-evidence-20261105.json`。两份库在 runtime.close 后 kernel_budget_samples 均为空，不能据此宣称关闭后残留标记；当前证据亦不足以归属冲突标记的具体所有者。原失败保留，不以后一轮部分通过取消。本轮未调用模型、未运行 CI／完整回归，没有推送发布。

完成时间序列化候选的当前安装包验证（2026-11-05）：POSIX／Windows worker 在原 invoke_handler 结果规范化后的采样位置改用已有序列化完成事实捕获；不提前成功边界，不增预算，失败仍未知。新增交错写入及采样前失败测试，源码 completion_clock 50 项通过（13.255 秒）。独立安装包 150 个产品文件直接字节比较无差异，四模块 75 项中 74 通过、1 失败（30.544 秒）；真实进程树 success 仍返回 running 而非 succeeded。证据 `/tmp/sdk-native-return-clock-result-20261105.json`、`/tmp/sdk-native-return-clock-installed-20261105.log`。原测试使用 TemporaryDirectory，失败数据库未保留，不能断言此次仍是 floor_above_ack。

随后只对同一进程树测试增加临时目录保留、原断言和期限不变，四个 outcome 通过（8.221 秒），现场及包路径见 `/tmp/sdk-native-return-clock-retained-20261105.json`；该后续通过不取消首次失败。原中文 README 第二示例在同一新安装环境独立运行一次，保持原两秒执行预算及断言，退出 0，现场 `/tmp/sdk-native-clock-readme-c_3ae_e9`，汇总 `/tmp/sdk-native-clock-readme-once-20261105.json`。单例通过不足以证明间歇性问题已修复，G14／G15／G18 不关闭；Windows 实际运行、采样期间终止、提交中断仍未验收。本轮未调用模型、未运行 CI 或完整回归。

完成时钟失败的当前包定位（2026-11-05）：使用 admission-retry 安装包、原两秒执行预算和原断言，仅增加 next 返回对象记录；最多三次诊断计划在第一次失败即停止，5.246 秒、退出码 1。现场 `/tmp/sdk-readme-current-bounded-_q8dg_v1/1/` 明确捕获 next=running、attempt=1、fence=1、result=None。只读 settlement_records 确认 deferred/pending，completion_clock_diagnostic 为 floor_above_ack／available：原样本及保留 floor 1793831668.612517，读到的 watermark 1793831668.6259913，本地 ACK floor 1793831668.5912714。该记录排除缺 ACK、错线程／连接作为此次最终拒绝分支；尚不能确定推进水位的具体写入者或其采样先后。原回执、数据库和进程身份不修改。

代码定位为 completion_clock._read_completion_time 的 floor_above_ack 拒绝；进程 _worker_entry 仍在 invoke_handler 后走读后验证完成时间，未使用已有序列化原返回事实路径。recover_completions 对 completion_time_unknown 不会自行授权成功，故不能用 README 等待循环、再次执行、放宽期限或将新水位当作原时间来修复。下一必要工作是在原进程返回边界建立与跨进程水位写入有序、准确 lease 绑定的原始事实，并证明父监督器只消费准确事实及清理证据；现有序列化捕获仅为候选机制，尚未证明可直接接入进程路径。该失败不再仅标记为 README 间歇问题，而是 G14/G15/G18 的当前包完成时钟取证缺口。

同一 admission-retry 安装包的 G01 integration 已实际通过，证据 `/tmp/sdk-host-admission-retry-g01-20261105/G01.json` 和 acceptance.json：YAML／Python 等价、默认值与双语 Wiki、未知／重复键及对象构造拒绝、CLI 验证／有效配置均核对。此补验无模型调用，不替代完成时钟缺口或完整平台验收。

单启动器限时准入与原所有者重试修订（2026-11-05）：launcher 新增 submit_until／retire_until，按原绝对期限获取准入锁，未获锁返回 False 且不提交任务／退役；已获锁保持原交接歧义规则。中断释放新增锁所有权，保留外层重入所有权。Host 使用唯一提交认领对象区分 pending、已认领、submitted 与准确失败；提交前超时回到 pending，后续调用重试原绑定 owner，队列交接异常不允许重复提交或换 owner。提交和退役位于 Host 锁之外，有限失败路径也转发原 deadline。退役未准入时 stop 返回 False，报告保留已确认运行时清理，后续只重试退役；双语 Wiki 已同步。

独立审查发现并修复两个并发缺口：认领之后进入异常保护之前中断留下永久认领；A 超时后 B 成功提交，A 的中断错误归属给 B。新增确定性跟踪用例验证唯一认领失败发布及准确异常归属，复核确认这两处缺口已消除。启动器 5 项、Host 7 项新测试与原相关组合共 78 项：源码 13.399 秒、最终独立安装包 13.800 秒，均无失败／错误／跳过。

当前 wheel `/tmp/sdk-host-admission-retry-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-admission-retry-installed-20261105`；从 /tmp 以 -I 使用复制快照，150 个产品文件直接字节比较一致。证据 `/tmp/sdk-host-admission-retry-result-20261105.json`、`/tmp/sdk-host-admission-retry-provenance-20261105.json`、`/tmp/sdk-host-admission-retry-installed-20261105.log`。原 .03 秒停止复现独立复验在 .030167892 秒返回 False，争用期间零关闭，释放后最终关闭一次且 launcher 退出；新证据 `/tmp/sdk-host-local-admission-fixed-20261105.json`，旧 .150382879 秒失败证据保留。本修订验证实际 SimpleQueue 非阻塞队列交接下的锁争用，不宣称任意外部替换的阻塞 queue.put 都可被中断。

G16 仍需最终原生停止／撤销／竞争／重启／未知清理组合验收；G18 仍缺完整最终包／平台证据及本轮新发现的 README 间歇失败根因。本轮无模型调用、完整回归或 CI；额外文档源码检查失败和单例安装包通过分开记录于下方。没有推送或发布。

当前源码文档检查失败（2026-11-05）：check_docs.py 不解析 --help，因此请求帮助时实际执行了链接与 README 示例检查；这是本轮额外启动的本地检查，不是完整回归或模型调用。运行在中文 README 第二个示例失败，现场 `/tmp/sdk-docs-README.zh-CN.md-example-2-ylv1d8aq/`，耗时 5.859 秒、退出码 1。超时处理器及子进程清理断言通过，但后续 next 调用的立即 succeeded 断言失败。只读原库快照显示 timeout=timed_out、next=running；原返回对象未捕获，不能推断具体返回状态或根因。两次提交原 timeout_seconds=2，不修改预算、不重跑掩盖原结果。压缩证据 `/tmp/sdk-docs-current-failure-20261105.json`。G18 文档示例仍有当前源码失败，历史文档通过不替代此结果；待单独定位交付完成状态与示例预期是否一致。

同预算观察补验 `/tmp/sdk-readme-next-result-5ticr95o/`：使用已有 direct-reraise 安装包，仅增加 next 返回对象记录，原两秒预算和断言不变；5.151 秒退出 0，next 确认为 succeeded、有普通成功结果和回收后的同一运行时复用。此为不同执行的通过，不解释首次源码现场的 running 状态，不据此取消失败或宣称文档整组通过。两次事件采样均截断到 2048 项；最高可见 commit 时长分别为 .092443 与 .050805 秒，仅为现场观测，不证明根因。

单启动器锁的当前安装包复现（2026-11-05）：`/tmp/sdk-host-local-admission-probe-20261105.py` 以 -I 使用 direct-reraise 安装环境运行。独立线程持有本 Host 的 launcher._admission_lock 时，stop(.03) 在 .15 秒观察窗末仍阻塞；释放锁后实际在 .150382879 秒返回 False。争用期间 runtime.close 为零，随后原 Host stop 完成、close 总数为一、launcher 退出。证据 `/tmp/sdk-host-local-admission-probe-20261105.json`。这把上一记录的内部交接“风险”确认为可复现缺陷；不能将 66 项局部通过解释为有限停止合同已兑现。

修复验收必须分别覆盖：清理所有者选择前锁超时（原所有者可继续接纳，不能留下永远无法提交的预留）；撤销所有者选择前超时（不虚构已请求撤销）；完成后的退役锁争用（原期限内返回，退役仍有准确后续所有者）；接纳后 queue.put 报错（保持原身份及未知，禁止换人重试业务）；现有重入退役和关闭标记重试不回归。有限锁等待应使用原绝对期限，不能引入 Host／launcher 相反获取次序或新的执行线程。当前仅复现及约束确认，尚未修改产品来解决本缺陷。

停止原异常直接重抛补验（2026-11-05）：stop 内启动清理失败、所有者提交失败／中断及诊断错误，以及撤销提交失败的两条传播分支，改为直接抛出选定异常对象，不调用异常自定义 with_traceback。显式保存启动 traceback 的其他启动接口未改动。既有两项并发测试使用自定义普通异常，新增有限 stop／撤销请求的自定义中断测试核对准确原对象及零 runtime.close。相关源码 29 项通过，1.369 秒；独立限定复核未发现回归。

当前 wheel `/tmp/sdk-host-direct-reraise-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-direct-reraise-installed-20261105`；/tmp 下 -I 运行复制测试快照，150 个产品文件直接字节比较一致。七模块 66 项通过，12.904 秒，无跳过。证据 `/tmp/sdk-host-direct-reraise-result-20261105.json`、`/tmp/sdk-host-direct-reraise-provenance-20261105.json`、`/tmp/sdk-host-direct-reraise-installed-20261105.log`。本结果关闭上一条记录的有限调用方重抛缺口；不证明单启动器交接可以限时返回或整个 G16/G18 完成。G16 汇总行已更新以免将已修复部分继续描述为未修复。无模型调用、完整回归、CI、推送或发布。

限时异常诊断安装包补验（2026-11-05）：有限 deadline 的 Host._record_error 使用固定摘要和 BaseException 类型，不同步调用异常属性、字符串方法或类名元类钩子；执行上下文省略，后台详细诊断语义保持。新增故障注入同时覆盖 execution_context、__str__ 和元类 __name__ 钩子。中英文 Wiki 已说明摘要及字段省略行为。源码相关两模块 24 项通过，0.843 秒。

当前 wheel `/tmp/sdk-host-bounded-diagnostics-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-bounded-diagnostics-installed-20261105`；/tmp 下 -I 运行独立测试快照，150 个产品文件直接字节比较一致，七模块 65 项通过，13.477 秒，无跳过。证据 `/tmp/sdk-host-bounded-diagnostics-result-20261105.json`、`/tmp/sdk-host-bounded-diagnostics-provenance-20261105.json`、`/tmp/sdk-host-bounded-diagnostics-installed-20261105.log`。独立复核确认此诊断分支已消除所报告钩子问题，但指出调用方四处启动失败重抛仍调用自定义 with_traceback，属于下一已确认修复项；因此不宣称所有有限调用均保留异常或 G16 完成。单启动器交接等待及完整真实故障／平台验收仍缺。本轮无模型、全量回归或 CI。

启动器隔离最终安装包补验（2026-11-05）：wheel `/tmp/sdk-host-launcher-final-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 安装到 `/tmp/sdk-host-launcher-final-installed-20261105`，从 /tmp 以 -I 运行独立复制测试快照；150 个产品文件直接字节比较一致。七个相关模块 64 项全部通过，13.659 秒，无跳过，包含注册表争用、重入退役、关闭标记失败重试、双异常优先级、自定义异常钩子、真实进程退出及原停止期限交接。独立复核确认本次双异常保留修订无剩余具体发现。证据 `/tmp/sdk-host-launcher-final-result-20261105.json`、`/tmp/sdk-host-launcher-final-provenance-20261105.json`、`/tmp/sdk-host-launcher-final-installed-20261105.log`。此前组合的测试夹具失败单独保留；本次是最终快照在最终 wheel 上的完整同范围通过。

本结果仅关闭启动器跨 Host 全局锁和该修订的交接／异常处理缺口，不代表 G16/G18 整体完成。Host 同步异常提取／格式化及单启动器内部交接的有限返回保证仍需处理；真实故障窗口及全量／平台验收缺口不变。本轮未启动模型、全量回归或 CI，未推送或发布。

最终异常保留修订限定复验：64 项源码组合在 12.271 秒结束，63 项通过、1 项失败，日志 `/tmp/sdk-host-launcher-errors-final-source-20261105.log`。唯一失败来自 unittest.assertRaises 自身调用自定义异常的 with_traceback，并非被测提交路径；改为直接捕获原对象后，该测试四种普通异常／中断组合通过，0.006 秒，日志 `/tmp/sdk-host-launcher-errors-fixture-final-20261105.log`。原失败保留，不将两次运行写成完整组合通过。独立复核确认先前两个异常覆盖问题已消除，限定范围无新增发现。当前最终源码仍待独立安装包验证。

启动器隔离修订进行中（2026-11-05）：复现注册表全局锁令 stop(.03) 超过 .15 秒未返回；源码现改用各启动器独立接纳锁，提交中的票据保证重入退役的关闭标记排在交接之后。关闭标记入队失败保留重试能力。独立审查发现提交与退役同时抛错时覆盖原错误，以及异常自定义方法／描述符可再次覆盖错误；当前源码将两个准确异常对象保留在启动器，由原提交错误优先、中断优先的规则选择直接抛出，不调用异常格式化或附加属性。新增对应故障注入测试。修订前相关 64 项源码检查通过（14.431 秒）；最终修订结果另记，不将此前结果或已构建的中间 wheel 归属最终源码。尚无最终修订的安装包验收，G16/G18 不变。本轮没有模型请求、完整回归或 CI。

撤销提交失败发布修订（2026-11-05）：有限 stop 向非等待撤销请求转发原期限，无法取得所有者预留／提交后检查锁时返回 False，已预留的准确所有者不被替换。提交抛错时先发布准确 (owner,error) 内存记录；无法限时合并到 Host 状态仍直接抛原异常。后续请求、已进入的后台等待者、错误选择和停止报告在锁内幂等合并失败，失败／启动解决状态写入后才清除记录。独立审查额外发现“入队后提交才失败”的竞态，新增独立 submission_resolved 状态，仅由原提交方在提交返回或失败记录已发布后设置；执行线程启动、进入或退出均不能替代提交解决。后台等待与线程结束后的最终检查均验证并合并失败，不因早到的执行完成放行关闭。两项新并发测试确认准确原异常、现有等待者可退出、原所有者不变且 runtime.close 未发生。独立复核未发现本次范围内其他具体竞态。失败记录发布前的异步中断仍不能宣称已恢复；启动器全局锁及同步异常属性／格式化等待仍未解决，G16 未完成。

当前 wheel `/tmp/sdk-host-revocation-publication-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-revocation-publication-installed-20261105`；从 /tmp 以 -I 使用复制测试快照，150 个产品文件直接字节比较一致。相关五模块 47 项通过，8.936 秒，无跳过；最终源码同范围通过 8.900 秒。证据 `/tmp/sdk-host-revocation-publication-result-20261105.json`、`/tmp/sdk-host-revocation-publication-provenance-20261105.json`、`/tmp/sdk-host-revocation-publication-installed-20261105.log`。测试中原私有 request_and_observe 包装同步转发 deadline 和返回值，保持原预算断言。本轮无模型、全量回归、CI、推送或发布；G01–G18 全部适用证据仍未完成。

Host 停止错误选择与诊断状态锁修订（2026-11-05）：有限 stop 的四处错误选择现在转发原截止时间；无法取得 Host 锁确认错误状态时返回 False，不把未确认状态当作成功。已保留错误仍抛出原包装及准确 cause。有限调用中的错误记录也把两处状态锁获取接入同一期限；记录未获锁不会替代直接抛给调用者的原等待／连接异常，清理所有者启动错误在记录前已保留。后台调用仍使用原无期限语义。新增错误选择／记录争用以及未确认选择不能报告成功的检查；独立复核无具体回归。错误属性提取和格式化仍同步；撤销所有者提交后的失败发布及启动器注册表锁仍未限时，因此 G16 不宣称完成。

新 wheel `/tmp/sdk-host-error-paths-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-error-paths-installed-20261105`；从 /tmp 以 -I 使用复制测试快照，150 个产品文件直接字节比较一致。相关四模块 43 项通过，8.702 秒，无跳过；最终源码同范围通过 8.533 秒。证据 `/tmp/sdk-host-error-paths-result-20261105.json`、`/tmp/sdk-host-error-paths-provenance-20261105.json`、`/tmp/sdk-host-error-paths-installed-20261105.log`。本轮无模型、全量回归、CI、推送或发布。当前 wheel 尚缺完整 G01–G18 适用验收；旧 wheel 证据不能替代本候选。

Host 停止后续状态锁修订（2026-11-05）：新增可复用的原绝对期限状态锁范围；除入口外，stop 的直接状态访问、构造确认等待、协调器启动／进入确认等待、最终报告更新均按同一期限尝试获取 Host 锁。失去锁获取机会返回 False，报告更新为 best effort，不覆盖原异常，不读取未获锁的状态；未选定所有者时不会虚构或替换清理线程。报告可能暂留 in_progress，缺少协调器时要由后续 stop 选定清理所有者；不宣称超时即已完成停止。新增四种准确争用场景（入口已接纳后的状态访问／报告／构造确认／协调器确认）均验证限时返回、未提前关闭及重试只关闭一次。原锁重入、TIMEOUT_MAX 分段和获取中断释放规则保持。独立审查在该范围内无新增问题。

新 wheel `/tmp/sdk-host-stop-state-lock-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，环境 `/tmp/sdk-host-stop-state-lock-installed-20261105`；从 /tmp 以 -I 启动并使用独立测试快照，150 个产品文件直接字节比较一致。prestart／stop report／notification／原停止期限交接共 42 项全部通过，8.380 秒，无跳过；源码前三模块 37 项通过 7.413 秒。证据 `/tmp/sdk-host-stop-state-lock-result-20261105.json`、`/tmp/sdk-host-stop-state-lock-provenance-20261105.json`、`/tmp/sdk-host-stop-state-lock-installed-20261105.log`。G16 仍未通过：撤销所有者预留后的失败发布、错误记录、错误选择以及启动器注册表锁仍可能阻挡有限调用，这些未被本修订伪装为已解决。无模型、全量回归、CI、推送或发布；此前 wheel 记录只代表各自时点。

Host 停止入口锁期限修订（2026-11-05）：旧安装包的准确复现 `/tmp/sdk-host-lock-probe-20261105.json` 表明 stop(timeout=.03) 在另一线程持有 Host 锁时超过 .15 秒仍未返回。现 `_begin_stop` 使用原绝对期限获取状态锁；无法进入时返回 False，不读取或修改受保护状态、不选择清理所有者、不伪造停止报告。锁释放后可再次 stop，准确运行时只关闭一次。原无期限协调器路径保持阻塞语义；已持锁的重入调用保持外层所有权，获取中断可释放新获锁。极大有限期限按 threading.TIMEOUT_MAX 分段等待，避免新引入 OverflowError。独立复核确认此限定入口修复，但 stop 后续的状态锁等待、报告及错误发布仍有无界路径，G16 不判完成。

新安装包 `/tmp/sdk-host-lock-admission-final-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立环境 `/tmp/sdk-host-lock-admission-installed-20261105`；从 /tmp 以 -I 启动，复制测试快照，150 个产品文件直接字节比较一致。受影响 prestart／stop report／notification 共 36 项全部通过，7.563 秒，无跳过；源码同范围通过 7.450 秒。证据 `/tmp/sdk-host-lock-admission-result-20261105.json`、`/tmp/sdk-host-lock-admission-provenance-20261105.json`、`/tmp/sdk-host-lock-admission-installed-20261105.log`。首次源码组合失败是私有 _begin_stop 故障注入包装函数未接收新增 deadline 及返回值，已同步转发；原失败日志保留，原断言不变。无模型、完整回归、CI、推送或发布。此前 wheel 的结果只代表各自修订；该 wheel 尚未全量验收。

同一恢复修订 wheel 的相关交接补验：24 项／38.259 秒，23 项通过、1 项测试收尾错误，原结果 `/tmp/sdk-effect-recovery-handoff-result-20261105.json`、日志 `/tmp/sdk-effect-recovery-handoff-20261105.log` 保留，不改写为全通过。真实子进程在已提交结果后退出 73，重开后核对原结果及交付证明、原处理器未重复执行，后续调用 succeeded；证据目录 `/tmp/sdk-managed-delivery-crash-kiun0x1h`，crash-import.json 和 recover-import.json 均确认导入独立安装环境。父运行采用 -I 和复制测试；本次工作目录为仓库，崩溃子进程的测试模块可从仓库导入，产品 SDK 仍由两份实际导入记录证明来自 site-packages，不能描述为全部从 /tmp 启动。

唯一错误是 ambiguous submit 测试清理：提交返回被刻意打断后，测试只把捕获的准确 Future 补给 late owner，未补给独立 completion-owner cleanup，运行时正确保留未知并拒绝关闭。仅修正测试收尾，把同一已完成 Future 补给两个准确所有者，保留未知期间不释放容量等原断言。独立复核确认不是产品自动恢复能力；生产仍不能自行找回丢失的 Future。该单例在原 wheel 上复验通过，2.718 秒，证据 `/tmp/sdk-effect-recovery-ambiguous-result-20261105.json`、`/tmp/sdk-effect-recovery-ambiguous-20261105.log`。未为此重跑整组；两次结果分开保留。G14／G16／G18 仍未整体完成，无模型调用、CI、推送或发布。

当前恢复状态修订（2026-11-05，独立安装包）：原 quiescent unknown 用例确认为产品缺陷：工具效果已 indeterminate，但 managed delivery 把恢复信号保留为非授权 late_thread_fact，上层继续 running。当前在仍活跃的调用中、completion gate／生命周期锁／delivery guard 内提交效果恢复，不授权业务成功；停止及迟到交接信号在事务入口和提交前重新检查，原 late fact 恢复规则不变。事务附加严格截止时间；不能把 SQLite 已进入的操作解释为可硬中断。独立审查发现并修复了停止信号选择、锁获取中断及迟到交接撤权检查。独立复核明确提交边界：提交前最终权限检查通过后，SQLite commit 仍可能与停止／迟到交接并发；此时 monitor 报 completion_handoff_pending，不能宣称已取消或已回滚。已接纳的效果停车只进入 recovery_required／indeterminate，不授权业务成功、重放或容量释放，因此该竞争不是已确认的缺陷。完整停止竞争验收仍需其他适用证据。

新 wheel `/tmp/sdk-effect-recovery-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 安装于 `/tmp/sdk-effect-recovery-installed-20261105`。由 `/tmp` 以 `-I` 启动，150 个产品文件直接字节比较一致；真实本地认证文件回调、清理未知、关闭后重开容量隔离及效果恢复权限组合共 6 项通过，13.968 秒，无跳过。新增提交前撤权回滚检查确认 execution 仍 running、effect 仍 prepared，随后合法调用可转恢复。证据 `/tmp/sdk-effect-recovery-installed-result-20261105.json`、`/tmp/sdk-effect-recovery-installed-provenance-20261105.json`、`/tmp/sdk-effect-recovery-installed-20261105.log`。受限环境首次源码检查因禁止本地端口而跳过，不算通过；宿主源码原失败用例通过 9.917 秒。仅限上述范围，G12／G14／G16／G18 未据此判定完成；本轮无模型调用或全量回归。下方旧 wheel 的“当前”字样均为各自记录时点，不能替代本 wheel 的最终验收。

当前独立安装包补验（2026-11-05，Linux x86_64／CPython 3.12.3）：预启动所有者修订已包含在 `/tmp/sdk-prestarted-host-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，安装到 `/tmp/sdk-prestarted-host-installed-20261105`。从 `/tmp` 以 `-I` 启动，使用独立复制的测试快照，子进程只添加该快照、不添加源码导入路径；SDK 和启动器均来自该环境 site-packages，150 个产品文件直接字节比较与当前源码一致，无新增散列检查。受影响的 74 项检查全部通过，8.099 秒，包括真实进程退出、fork、原限时停止和准确所有者断言。证据 `/tmp/sdk-prestarted-host-installed-result-20261105.json`、`/tmp/sdk-prestarted-host-installed-provenance-20261105.json`、`/tmp/sdk-prestarted-host-installed-tests-20261105.log`。此为当前 wheel 的限定 Host 验证，不能证明整个 G16 或 G18 已通过；下文较早记录所说“尚无此源码修订的安装包证据”仅描述当时状态。

同一 SDK wheel 补装本地 PyYAML 可选依赖后，G01 配置集成通过，0.247 秒：YAML／Python 等价、未知／重复键及任意对象构造拒绝、预算校验、有效配置 CLI 和双语 Wiki 默认值核对均通过，实际导入仍来自独立安装环境。原证据 `/tmp/sdk-prestarted-host-g01-20261105/G01.json` 与同目录 acceptance.json。构建环境缺少可运行 build 模块及默认 pip 缓存只读的两次失败日志均保留；最终通过现有 pip 的离线、禁缓存构建完成，没有联网安装构建依赖。本轮无模型调用、完整回归、CI、推送或发布。

G16 停止所有者预启动修订（2026-11-05，源码，尚非最终安装包）：清理及撤销两个准确执行线程现在在 Host 构造时启动并确认身份；停止和启动失败清理只向这些线程交接任务，不再在限时停止或已接受的清理交接中创建原生线程。异步交接和需要同步确认的启动失败交接均进入同一启动器队列；公开退出回调等待已接受的交接排空，再退役并等待已知身份的执行线程。启动失败交接的确认在 Host 锁外等待，保留原中断优先级、唯一所有者、预算和清理未知语义。正常空闲 Host 可回收；执行完毕清除回调引用，避免 finalizer 反向保留 Host；注册表使用重入锁，覆盖回收时在同线程重入注册表的情况。构造阶段启动异常仍保留准确所有者并排队退役，不把未成功构造的 Host 作为可用实例返回。

最终受影响源码组合 74 项全部通过，8.373 秒：`/tmp/sdk-host-prestarted-owners-final-20261105.log`。包含原限时停止、并发等待、错误和中断优先级、关闭屏障、实际 fork、构造晚到错误、Host 回收及真实进程退出。测试注入从原停止时 Thread.start 扩展到实际 HostOwner.begin 交接边界，旧协调器启动仍注入 Thread.start；原期限、唯一身份、不得提前关闭及后续确认断言保留。线程构造故障的停止路径现在注入预启动所有者的保留操作；身份断言相应改为已知线程身份、尚未接受操作。两个新增真实子进程场景分别延迟入队、入队后延迟报错；均在停止期间禁止 Thread.start，主线程限时返回 false 后，退出前仍取得实际关闭标记。针对退出／回收的 11 项先前通过记录为 `/tmp/sdk-host-prestarted-exit-window-20261105.log`。独立审查发现并修复构造失败退役、同步启动交接绕过退出队列等问题，最终限定复核未发现新的具体阻塞项；不扩大为全目标认可。

中间组合失败和停滞均保留原日志，未改记通过：`/tmp/sdk-host-prestarted-owners-expanded-20261105.log`、`/tmp/sdk-host-prestarted-owners-reviewed-20261105.log`、`/tmp/sdk-host-prestarted-owners-integrated-20261105.log`、`/tmp/sdk-host-prestarted-owners-reentrant-registry-20261105.log`。旧序列 `/tmp/sdk-host-prestarted-owners-queued-startup-fixed-20261105.log` 在 inline bookkeeping 用例处停止输出，原 session 34992 的准确合成测试进程已在宿主命名空间按原日志与命令识别后发送 SIGTERM，执行会话最终返回 143（Terminated）；处置记录 `/tmp/sdk-host-stalled-sequence-disposition-20261105.json`；该用例隔离通过不证明旧序列已完成，也未证明其停滞原因。重入注册表缺陷已由独立直接用例验证修复，不将其推定为旧序列的已证实根因。G16 仍需更广的锁准入／嵌套清理及当前安装制品证据，G18 仍缺完整回归与平台矩阵；本轮未调用模型、未运行完整回归或 CI、未推送发布。

G16 启动器修订及独立审查（2026-11-05，源码，非最终安装包）：构造时预启动启动器，限时 stop 只投递准确的关闭／撤销线程启动请求。原 `test_prestart_shutdown_owner_start_is_bounded`、`test_running_revocation_owner_start_is_bounded` 已通过，未修改其断言或时间限制。独立审查后修复空闲 Host 回收、启动／诊断双重失败的结果发布、投递失败后 join 无限等待，以及 start 前 root commit 的 fork 识别；真实 fork 子进程检查包含父进程持锁时拒绝旧 Host 操作。当前相关 46 项检查全部通过，4.142 秒，原输出 `/tmp/sdk-host-launcher-retained-owner-20261105.log`。此前 43 项通过及中间一项失败均保留，未改记结果；中间失败来自错误地要求启动未知所有者可回收，该要求还会丢失晚到线程身份，已撤回并改为验证准确未知所有者保留、启动器线程退出、未关闭 runtime。闲置且未提交工作的 Host 仍验证可回收。

该修订未闭合 G16：Thread.start 异常可能发生在原生线程已创建、身份尚未发布的窗口。此时保留原所有者与错误、不启动替代者；启动器守护线程可退出，但未决所有权图有意保留。独立审查确认公开退出回调仅采样一次身份，仍可能漏等随后发布身份的线程，不能把记录保留视为实际退出清理证明。其他宿主锁准入、嵌套清理和当前安装制品完整验证仍缺。本轮未调用模型、未运行完整回归或 CI、未构建新候选，G16／G18 均保持未通过。

G16 退出机制的实测纠偏（2026-11-05，仅设计前提，不是产品修复）：独立审查曾提出“Python 3.12 的公开 atexit 阶段不能再启动结算释放线程，因此预启动守护清理所有者必然失败”。当前解释器上的两个真实子进程检查不支持该判断：实际 managed Runtime 在公开 atexit 回调内关闭，activation=closed、无异常、退出 0（`/tmp/sdk-g16-public-exit-managed-v7dl3uwy/evidence.json`）；进一步预先启动守护线程、仅在公开 atexit 开始后投递关闭请求，记录 release_started 从 false 到 true，实际 activation=closed、线程已退出、无异常、退出 0（`/tmp/sdk-g16-daemon-exit-managed-gx8dvj37/evidence.json`）。两次均通过 SDK 工厂创建真实临时存储，无模型、无内部数据库直接写入；独立审查已撤回该当前平台上的必然失败结论。该结果仅说明 Linux x86_64／CPython 3.12.3 的此关闭路径可行；尚未接入宿主启动器，不能证明原 G16 两项限时停止已修复，也不能推广到其他 Python／平台。嵌套释放若超时仍须保留未知，不能凭宿主线程退出认定参与者已释放。后续实现必须保留既有 idle 进程退出、准确所有者、启动结果确认、fork 和中断边界，而不是以该两个探针替代整体验收。

G16 撤销启动的并发等待修订（2026-11-05，源码）：`RuntimeHost._request_runtime_stop_once` 先登记唯一撤销所有者，再在宿主锁外执行该所有者的 Thread.start，避免首次启动受阻时连带堵住后续限时 stop。新增显式启动结果发布状态；原启动调用尚未返回时，即使撤销线程已完成也不授权协调器关闭资源；启动失败后并发等待者重新检查保留错误，不再永久等入口。选取、登记与启动均在异常保护内，未知或中断不创建替代所有者。独立复核首次发现上述失败通知和晚到错误两处竞态，修正后在该有限范围内未发现具体新阻塞项。三个新增检查覆盖并发 stop 按时返回、入口前启动失败、线程完成后启动调用仍失败；定向 24 项通过（`/tmp/sdk-stop-start-resolution-20261105.log`）。最终完整相关组合 28 项中 26 通过、2 失败，2.682 秒（`/tmp/sdk-stop-start-resolution-combined-20261105.log`）；原 `test_prestart_shutdown_owner_start_is_bounded` 和 `test_running_revocation_owner_start_is_bounded` 仍失败，未更改其断言或期限。首次启动调用本身仍可能无界阻塞，其他宿主锁准入亦未闭合，G16 不通过。这次源码变化晚于上方／下方 managed-delivery wheel 的构建，尚无含此修订的安装包证据；未重建、未调用模型、未运行完整回归或 CI。

当前安装包 G01（2026-11-05）：给既有独立安装环境补装项目声明的 agents 可选依赖 PyYAML 6.0.3（使用本地既有 wheel，未联网、未改变 SDK wheel），从 `/tmp` 以 `-I` 运行原配置验证器，0.276 秒通过。YAML／Python 有效配置相等；重复键、未知字段、任意对象构造及无效预算四类输入拒绝；中英文 Wiki 的 JSON 默认值块均与当前包注册表相等；CLI validate 和 config show --effective 均退出 0，后者输出与 Python 配置相等。实际 SDK 导入来自独立环境 site-packages。证据 `/tmp/sdk-current-managed-g01-20261105/G01.json`、同目录 acceptance.json；没有模型调用，不扩大为 G15／G16 或最终制品验收。

当前安装包模型发送后崩溃窗口 C（2026-11-05）：`/tmp/sdk-current-managed-native-fault-c-fixed-20261105/report.json` 为 passed，16 个检查均为 true；Linux x86_64／Python 3.12.3，实际 SDK 导入来自 `/tmp/sdk-managed-recovery-installed-20261105/lib/python3.12/site-packages`。真实 outbound request 返回后原宿主以 32 退出，原 invocation `825c3e98887c4c569b41707f1249efc1` 仅记录一次发送；重启后期限前稳定 ID 重放不改变原身份、预算或未决效果，原期限及租约到期后转 recovery_required 并隔离同会话。另一 Run 的排队请求到期取消，未创建原生操作或 runtime effect，Agent 调用／模型轮次用量均为零；不同会话的第三个 Run 成功（两次发送），无未归属发送。原执行 attempt=1／fence=1 的原生进程树清理有匹配回执。恢复宿主最后由验证器以 SIGTERM 结束（exit=-15），host_processes 的 native_cleanup 仍为 unknown；故该通过只证明上述故障恢复检查，不证明恢复宿主完整关闭或 G16。A／B／D 本次未运行，G14 整项仍未完成；前两次失败／未运行记录保留。当前没有此验证器仍在等待结果。

当前模型发送故障窗口的验证器修订（2026-11-05）：首次启动遗漏验证器要求的 `-I`，在环境检查拒绝、未运行 case（`/tmp/sdk-current-managed-native-fault-c-20261105/report.json`）。补齐隔离参数的运行在 fault gate 前终止为 runtime_rejected／OpenCodeError，原现场 `/tmp/sdk-current-managed-native-fault-c-isolated-20261105/case-c` 保留，send-ready／send-go／发送记录和 fault 标记均不存在。OpenCode 原日志含 Bad Gateway；源码核对确认验证器 `tagged_wait_io(owner,function)` 不接受现代理调用提供的 `connection=`，发送前 TypeError 被本地代理转换为 502。现仅修订验证器转发全部关键字参数，并在原请求已终态而发送故障闸门未到达时记录 failed，避免等待不可能出现的标记；不改变原预算、故障注入或 unknown 验收条件。AST 提取实际包装函数、绑定当前安装包方法签名的无网络检查确认 connection 正确转发、调用归属正确且清理完成。原运行经受支持的 AgentClient.stop 正常结束，无强制杀进程。修订后已在新目录 `/tmp/sdk-current-managed-native-fault-c-fixed-20261105` 完成同一窗口，结果见上方；不将旧 not_run 记为通过。

当前 managed-delivery wheel 的真实 G02（2026-11-05）：在 `/tmp/sdk-managed-recovery-installed-20261105` 安装环境运行原 G02 验证器，经用户指定本地 CLIProxyAPI 调用真实 OpenCode，Linux x86_64／Python 3.12.3，31.593 秒通过。实际导入来自 site-packages，响应 DONE、命名文件产物精确为 SDK_AGENT_NATIVE_OK、SDK Run succeeded；模型预算 spent=5、reserved=0、unknown_count=0。原生清理账本为 cleaned／tree_cleanup confirmed，匹配 execution `agent:28cc3a8f76344767ad38d065b0f080df` 的 attempt=1／fence=1。证据 `/tmp/sdk-current-managed-native-g02-20261105/G02.json`、同目录 acceptance.json 及 `/tmp/sdk-current-managed-native-g02-20261105.log`。只读使用既有 OpenCode 可执行文件，未修改 ModPort；凭据不写入报告。此为当前局部 wheel 的 Linux x64 G02，通过不扩大到 G14、G15 或其他平台，尚非最终冻结候选。

修订后 wheel 的两窗口复验（2026-11-05）：重新构建 `/tmp/sdk-consumption-recovery-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，在独立临时 venv 强制重装，清除 PYTHONPATH 后运行 SDK 提交后回执前退出及应用 finish 后计划关闭前退出两项真实子进程测试，均通过（10.143 秒，`/tmp/sdk-consumption-recovery-installed-20261105.log`）。SDK 证据 `/tmp/sdk-managed-delivery-crash-vkks4arx`，应用证据 `/tmp/sdk-agent-consumption-crash-qo8luv8m`；应用两个进程实际加载的 SDK 与 application 均来自安装环境 site-packages，退出分别为 73／0，原调用一次，下一调用一次。完整完成回执、原计划、结果／产物、原截止与预算快照在重启后相等。原采样超时失败现场仍保留；这个通过支持修订后的两个明确故障窗口，不证明任意监控交错已消除，更不覆盖模型请求后的未知效果、真实 OpenCode、用户读取确认、完整回归或平台矩阵。G14／G15／G16 均未据此关闭。

锁交接审查补充（2026-11-05）：独立审查在新确认路径中复现 Kernel `_control_lock` 原先在进入清理保护前获取 RLock 的中断泄漏。现将保护覆盖到获取动作前，嵌套调用不额外获取或释放调用方已持有的锁，并保留最早期限及原连接 busy_timeout 的恢复。三个新锁交接检查和三个已有严格期限检查通过（1.285 秒，`/tmp/sdk-control-lock-interrupt-20261105.log`）；独立复核未发现本修订范围内具体新阻塞项。这不构成应用故障恢复或 G16 全部验收。

应用消费／完成回执后退出的新增检查（2026-11-05）：`test_agents_consumption_crash` 使用实际 AgentApp、本机 HTTP 文件／产物工具及 synthetic adapter，在真实 SDK finish 操作提交后、计划关闭前以 73 退出；随后独立进程重放原请求，核对完整完成回执、计划文档、Run／invocation、结果、产物、截止时间及 agent_calls／model_turns，原调用不重复，计划关闭，下一请求成功。源码第二次运行通过（7.411 秒，`/tmp/sdk-agents-consumption-crash-observed-20261105.log`，原始证据 `/tmp/sdk-agent-consumption-crash-zrt53x9n`）；首次运行在故障注入前按原 15 秒期限超时（`/tmp/sdk-agents-consumption-crash-20261105.log`，现场 `/tmp/sdk-agent-consumption-crash-c_ha5v1x`），实际工具效果已成功而执行仍 running，返回事实报告 `budget_clock_sample_unresolved:sampling`。后续通过不能覆盖该失败，也不证明用户读取确认或真实模型恢复。

针对监控／返回采样竞争的源码修订：返回捕获在原单一控制期限内按 Context budget → return → capture owner → Kernel 顺序串行化；只确认准确 Kernel／执行／注册所有者持有的非空原事实，随后再生成返回采样，不清除未知或外来 guard。独立审查发现并修正错误绑定 owner 可被借用及原 `_KernelBudgetCapture._run` 获取锁后中断可能泄漏 RLock 的问题。捕获与收据检查合计 18 项通过（3.998 秒，`/tmp/sdk-return-monitor-owner-reviewed-20261105.log`），覆盖保留监控事实确认、错误执行绑定、锁顺序拒绝和实际获取锁后中断。首次新增测试因缺少 sample_clock 导入失败，原日志 `/tmp/sdk-return-monitor-serialization-20261105.log` 保留，修正夹具后的前一轮 11 项通过（2.397 秒）。此修订尚不能单凭该局部测试确认首个应用超时的完整根因；正在重建 wheel 复验应用故障窗口。

当前 wheel 的同一故障窗口复验（2026-11-05）：从当前源码构建 `dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，在独立临时 venv 中以 `--no-index --no-deps` 安装，并清除 PYTHONPATH 后运行上述真实子进程故障／重启检查，通过（2.134 秒，`/tmp/sdk-runtime-managed-delivery-crash-installed-20261105.log`）。两子进程的实际导入均来自 `/tmp/sdk-managed-recovery-installed-20261105/lib/python3.12/site-packages/dispatcher_sdk/__init__.py`，原始记录及 SQLite 保留在 `/tmp/sdk-managed-delivery-crash-clvmljkq`；子进程退出分别为 73 和 0，调用记录为 original、next。wheel 及构建／安装日志分别在 `/tmp/sdk-managed-recovery-wheel-20261105`、`/tmp/sdk-managed-recovery-wheel-build-nocache-20261105.log`、`/tmp/sdk-managed-recovery-wheel-install-current-20261105.log`。首次构建因默认缓存只读失败的日志保留为 `/tmp/sdk-managed-recovery-wheel-build-20261105.log`，随后关闭缓存成功。该 wheel 是本次局部验证制品，尚非冻结候选；仅增加 G14 一个窗口的安装包证据，没有完整回归、CI 或发布。

真实进程提交后回执前恢复（2026-11-05，源码定向验证）：新增 `test_runtime_managed_delivery_crash`，以独立子进程开启实际 managed Runtime，在真实 owned Kernel 结果提交返回后立即以 73 退出，确认原执行 succeeded、准入意图及交付授权已持久化，而日志中尚无交付回执。另一个进程使用支持的 `recover_completions` 恢复，逐项核对原 intent／执行／attempt／fence、返回事实、决策预算与时钟、原结果及恢复回执；调用记录只有一次 original，随后独立 next 调用成功，原执行与结果不变。保留证据复验通过（2.091 秒，`/tmp/sdk-runtime-managed-delivery-crash-retained-20261105.log`），原始数据库、子进程输出和恢复报告位于 `/tmp/sdk-managed-delivery-crash-0bko07zp`。这是本地 SDK handler 的单一真实崩溃窗口，不是模型请求、应用消费或 G14 全部完成；正在补当前 wheel 安装验证。

本批复验结果（2026-11-05）：最终源码上连续两次原始 AgentApp 调用／产物／重放／重开用例通过（合计 15.092 秒，`/tmp/sdk-agent-managed-original-repeat-20261105.log`）；加上接入后的首次，共三次通过。未更改原断言和期限，均实际运行本机 HTTP 工具服务，非跳过。构造清理重试现采用非阻塞预约，且每次只尝试当前数据库的一位保留所有者；同库第二次打开恢复及不触碰其他数据库两项通过（1.803 秒，`/tmp/sdk-runtime-constructor-targeted-retry-20261105.log`）。这使普通调用路径具备当前源码的实际进展，仍不能取代安装包、故障重启与 OpenCode 验收。此前 66 项组合的一项失败、G15 token 上限和 G16 两项限时停止失败仍未消除；本批没有运行完整回归或 CI。

普通 AgentApp 接入（2026-11-05，当前源码）：AgentApp 现在显式开启 Runtime 的 `managed_delivery`，使用固定路径的新 v8 交付日志、实际 activation、准入意图及已绑定 handler 返回路径。旧 Runtime 默认不变；已有执行历史却缺失新日志时拒绝启动，不复制旧日志或虚构恢复权限。原始 `AgentApplicationTests.test_sdk_result_artifact_replay_and_reopen` 在允许本机回环的环境中通过（7.985 秒，`/tmp/sdk-agent-managed-original-20261105.log`），原断言和等待期限不变，涵盖两次调用、产物、请求重放、关闭后重开。适配器为 synthetic，单次通过也不足以消除先前偶发失败，不能计作真实 OpenCode 或最终安装包验收。

创建／重开与 Runtime 所有权组合的十项检查通过（4.332 秒，`/tmp/sdk-managed-delivery-fsync-20261105.log`）；独立审查发现重开未补目录同步，现已修正并验证同步失败不会报告成功。另发现构造失败后的清理重试没有生产入口，后续普通 managed 构造已会重试保留所有者，单项真实 SQLite 检查通过（0.539 秒，`/tmp/sdk-runtime-constructor-retry-20261105.log`）；该重试对其他数据库的阻塞范围正在收紧。空执行历史不能证明缺失日志从未使用，尚无独立持久绑定协议；不得将此实现扩大为任意删除日志后的恢复保证。G14／G15 保持未完成。

收据校验的撤销与全局未决标记补验：五项通过（1.407 秒，`/tmp/sdk-serialized-return-receipt-guards-20261105.log`），包括真实兄弟执行持有未决采样时，精确返回收据也不能绕过全局拒绝。此为 Kernel 定向检查，不是完整应用恢复验收。

迟到决策的精确收据校验（2026-11-05，源码定向验证）：原返回采样已原子确认后，其他执行推进共享水位不再单独导致原结果被拒绝；例外要求当前线程／进程中精确活跃 handler 的 capability、原返回采样所有者、原始事实及不可变收据完全匹配，并在同一决策事务提交前重复校验。原全局未决采样、租约、撤销、预算及准入检查继续生效，持久 v2／v3 返回格式未改变。独立只读审查未发现具体授权阻塞；四项真实 SQLite 定向测试通过（0.936 秒，`/tmp/sdk-serialized-return-receipt-revocation-20261105.log`），覆盖较晚水位成功、缺失绑定、外来令牌和 handler 撤销。测试直接登记合成 intent，不证明真实交付日志、Runtime 恢复或普通 AgentApp；当前正接入普通调用，G14／G15 仍未完成。

串行返回捕获接线（2026-11-05，后于以下存储基础记录）：新增 Context 持有的返回采样所有者和清理流程，分别保留原始 ClockCheckpoint、原输入事实及后续 ACK 输出；确认恢复或重试不会把后续水位变成原返回时间。`_capture_owned_return` 已采用新捕获，采样前和授予 capability 前均检查准确活跃 handler 所有者，仍要求原有版本化准入和交付意图才能授权结果。一次 Context 返回授权只允许一次尝试，首次序列化失败也不能让不同结果复用旧时间；先前未绑定观察亦不能升级成新结果。关闭在同一创建锁下确认所有者，已开始采样的未知标记不得清除；只有精确活跃所有者持锁且在原始墙钟调用之前设置的 started 标志仍为 false 时，才可退还未采样标记。此变化没有切换普通无 activation Runtime／AgentApp，也没有解决其迟到决策。

接线首轮相关 64 项通过（24.975 秒，`/tmp/sdk-serialized-owned-return-integration-20261105.log`）。独立审查发现并修正关闭／创建竞争、锁和 reader 预留中断窗口，以及不同结果重用旧时间的问题；后续针对边界绑定和清理的 11 项通过（2.381 秒，`/tmp/sdk-serialized-return-boundary-binding-20261105.log`）。最终相关 66 项为 65 通过、1 失败（29.640 秒，`/tmp/sdk-serialized-owned-return-final-20261105.log`）：`test_real_worker_entry_failure_keeps_its_original_error` 预期入口错误，实际收到 Kernel 控制期限错误；原断言／期限不变，单独复验通过（`/tmp/sdk-serialized-return-entry-error-recheck-20261105.log`），根因尚未确认，最终组合不能记为通过。真实线程 Runtime 的 `test_real_thread_claim_return_and_receipt` 在 2.450 秒通过（`/tmp/sdk-serialized-return-real-runtime-20261105.log`），检查真实调用、SDK 结果及准确交付收据；它使用本地 handler，不是模型调用或普通 AgentApp 验收。G14／G15 仍未完成，无完整回归正在等待。

串行采样与原子确认基础（2026-11-05）：`_finish_budget_sample` 新增仅内部使用的 `_capture_lease` 模式，要求准确 Kernel／执行绑定的采样所有者且调用方已持有 owner 锁；原已提交采样标记在整个过程保护未知窗口。新模式在同一 BEGIN IMMEDIATE 事务内验证水位、全局未决采样和原 lease，随后采样、保留事实，并复用精确收据／规范预算／全局水位的原子提交。没有跨采样等待主锁，也不删除水位检查。原 lease 检查针对先前提交水位，新采样可揭示过期并发布零剩余时间；这是事实观察，不是结果授权。

新增存储用例覆盖事务内采样、另一 Kernel 在时钟回退后仍看到已提交水位、采样保留后中断及不重采样恢复、错误 fence 采样前拒绝和到期观察。扩展原 spawn 进程崩溃测试，分别在新模式 COMMIT 前和 COMMIT 后退出，利用退出前实际交出的精确事实恢复；原有精确身份和拒绝断言保留。组合 10 项在 2.859 秒通过，日志 `/tmp/sdk-serialized-budget-capture-reviewed-20261105.log`。另一个真实进程在采样后、事实交出前直接退出，重启确认仅有原保护标记、无收据且继续拒绝未知采样，1 项通过，日志 `/tmp/sdk-serialized-budget-no-handoff-20261105.log`。不能把这个未知窗口称为可恢复精确事实。独立只读复核未发现该非授权存储原语范围内的新确定阻塞；现有普通 Runtime／AgentApp 尚未接入，原始返回、结果绑定、迟到决策和恢复生命周期仍需集成。未重跑完整安装包，G14／G15 未完成。

普通调用修复路径排除（2026-11-05）：新增正式回归 `test_owned_return_does_not_authorize_post_sample_watermark`，直接调用真实 SQLite 的 owned-return 捕获，在原采样后、读连接创建前通过测试闸门同步提交真实水位写入。捕获仍拒绝确认，未创建所有者 capability，执行保持 running；1 项在 0.195 秒通过，日志 `/tmp/sdk-owned-return-floor-boundary-20261105.log`，现场 `/tmp/sdk-completion-clock-iiwof1s1/evidence.json`。独立只读审查确认上述范围；这不是并发写入、Runtime 生命周期或真实模型验收，也不单独证明具体 floor_above_ack 分支。它排除了“只把普通调用接入现有 owned-return API 就能修复”的路径：该 API 在创建 capability 前仍调用相同采样检查。产品缺陷未修复，未新增整项通过；下一实现必须先提供共享存储序列上的原返回顺序证据，不能删除水位保护或伪造激活身份。具体前提已写入完成交付设计。

同 Kernel 返回快照锁试验已撤回（2026-11-05）：新增可控实际 SQLite 调度在原返回采样后、独立读取前启动同 Kernel 写入者，修订前复现原时间无法确认（`/tmp/sdk-completion-local-fence-before-20261105.log`）。尝试在采样到读取期间非阻塞获取主锁，独立审查指出它会阻止先前采样所有者完成 ACK，且覆盖连接关闭会干扰清理。实际 55 项组合出现 1 项失败、2 项错误（`/tmp/sdk-completion-local-fence-20261105.log`），包括原先能清除的未决采样和关闭时序。已精确撤回本轮的产品改动及实验测试，不撤回之前预算收据和旧接口修复；试验文本保留在 `/tmp/sdk-completion-local-fence-rejected-20261105.txt` 和 `/tmp/sdk-completion-local-fence-probe-20261105.txt`。撤回后的 53 项组合为 52 项通过、1 项关闭错误（22.626 秒，`/tmp/sdk-completion-fence-reverted-20261105.log`）；该关闭错误在撤回前后均出现，不能归因于已撤回的锁试验，也不能记作通过。其现场为 `/tmp/sdk-completion-reader-lifetime-iwfqd5n5/evidence.json`。本轮没有关闭新的验收项；仅排除了会阻塞确认和清理的局部锁方案。

当前 AgentApp 集成复验（2026-11-05）：旧接口修订后，以原测试、原等待期限复跑普通调用／重开和祖先限制组合，实际 119.629 秒后报告 3 个超时：普通第二次调用、agent_calls、call_depth（`/tmp/sdk-agent-chain-after-legacy-fix-authorized-20261105.log`）。先前受限环境下的同组执行全部因回环通信受禁跳过（`/tmp/sdk-agent-chain-after-legacy-fix-20261105.log`），不能计为通过。允许回环通信后才取得上述实际失败。

随后仅对普通调用保留测试临时目录：首次单次通过；限定三次复现中两次在第一个调用超时、一次通过，耗时 38.818 秒（`/tmp/sdk-agent-simple-retained-three-20261105.log`）。保留失败现场 `/tmp/tmpsil2sce3`、`/tmp/tmpy5atz9iw`，通过现场 `/tmp/tmpwaf2roc3`，只读摘要 `/tmp/sdk-agent-return-evidence-20261105.json`。两个失败的适配器均已产生成功输出，底层执行仍为 running，结算记录为 pending／completion_time_unknown，错误为 `completion_clock_original_floor_unproven`，诊断为 `floor_above_ack`；通过现场两个请求均 succeeded 且收据 recorded。这证明当前固定源码仍有真实完成时序失败，不能把旧接口负例通过扩大为 AgentApp 已修复，也不能凭后续单次通过抹去失败。没有修改原测试断言或延长等待，没有改动测试数据库。

旧式公开预算读取的原始负例修复（2026-11-05）：直接构造、未设置 `guard_budget` 的真实 SQLite `HandlerContext.budget` 现在在原始 `_sample` 之前登记持有者，并在返回前确认精确采样。中断后先确认保留的事实，再进行本次新观察；错误 attempt／fence 在采样前拒绝，已到期的观察仍发布实际水位并返回零剩余时间。读取返回的本地 elapsed 视图不再改写存储于上下文的原采样；派生约束使用已确认的检查点，关闭后的上下文只读取保留事实，不生成新的原始墙钟采样。自定义／进程代理内核继续原有路径，未据此声明其全局来源问题已解决。

此前 `tests.test_runtime_legacy_clock_order` 中的真实 Runtime 负例已在当前源码通过：旧上下文观察到高于原执行期限 30 秒的采样后，原执行不会再被错误判为成功；原期限、执行身份与采样值断言保持不变。原始负例、登记／ACK 中断恢复、到期和错误 fence、上下文观察、执行预算、持有者及收据共 36 项通过（5.421 秒，`/tmp/sdk-legacy-public-budget-confirmed-20261105.log`）。组合检查还揭示先前收据实现允许显式外来持有者冒领已提交 ACK，现已恢复精确活跃持有者／令牌／待确认事实校验，相关原测试通过。独立只读复核没有发现这两个局部路径的新阻塞项。该结果未验证最终安装包，也未关闭延迟结果收集、普通执行的持久返回见证、其他旧写入者或全局完成顺序问题；G14／G15 保持未完成。

精确预算确认收据（2026-11-05，源码验证，未形成最终安装包）：新增 v19 不可变收据，将令牌、执行、存储及原始输入／确认输出与采样标记删除、水位更新原子提交；没有收据时不再以较高水位推断旧令牌已确认。真实 spawn 进程在 COMMIT 前退出和 COMMIT 后退出均保留原采样供新连接恢复，重放拒绝未登记令牌、不同执行及不同采样。首轮组合 19 项中 18 项通过、1 项旧 v4 夹具错误（`/tmp/sdk-budget-receipt-recovery-20261105.log`）；夹具遗漏删除新增表，修正后原 v4 用例及两个收据 schema 用例通过（`/tmp/sdk-budget-receipt-migration-fix-20261105.log`，该组合另有新检查测试的断言错误）。独立审查发现公开结构检查器遗漏新触发器，已补齐；检查测试按 API 的结构检查合同修正后通过（`/tmp/sdk-budget-receipt-inspection-20261105.log`）。没有自动升级真实库，也没有为旧采样虚构收据。

收据序列化期限后续修订：编码前检查约束数量与标识符字符总量，逐块限制实际 UTF-8 字节，输入、规范预算、输出编码及锁／事务共用原绝对期限；规范预算读取亦先限制大小。独立审查发现空约束路径和提交前检查遗漏，现已修正，并向事务传入严格期限。相关进程恢复、精确身份和结构检查 7 项通过（2.668 秒，`/tmp/sdk-budget-receipt-strict-window-20261105.log`）；额外 SQLite 最后水位写入阻塞注入证明超时后收据回滚、原标记保留，原采样在后续窗口可恢复（`/tmp/sdk-budget-receipt-commit-deadline-20261105.log`）。这些限制约束 SDK 的编码和提交准入，并非 Python 调度、单次系统调用或 COMMIT 自身的实时硬保证。

这项修订仍未收口：每次采样永久保存两份信封，持续采样的存储增长尚无保留／回收协议。独立审查确认精确收据不证明外部输入来自原采样者，也不解决全局完成时钟来源问题。上述检查不能计为 G14／G15 完成，必须处理这些边界后再验证当前制品。

状态：实施中。候选 52 的 Linux x64 Python 3.12 完整安装回归在约 27 分钟后结束：内层 2419 项中 1 项失败、3 项错误、28 项跳过，外层 5 项中 1 项失败。终态取消错误已确认是测试夹具构造了不一致状态，修正后原测试定向通过；其余三个原始失败的根因尚未确认。候选 52 冻结后仍有源码变更，不能作为最终制品。线程完成授权正在按停止与提交的先后顺序重新实现，重启恢复、原始完成时间以及超时交接仍未完成；停止期限亦有两项已复现失败，详见文末。历史候选已有真实模型、跨 Run 服务、故障恢复和权限等分项证据，仍须核对其对最终候选的适用性；G03、G04、G06、G17 尚缺最终整项证据。Python 3.10／3.11／3.13 完整版本矩阵和原生 Windows／ARM 尚未通过。G13 仅验证合同和拒绝，真实强隔离未验收。完整 G01–G18 Goal 尚未完成。

活动预算采样所有者校验：真实 SQLite 定向负例证明，原接收路径在持有者保留的采样与接收信封不同时仍会确认采样；当前源码先在两个锁下核对 Kernel、执行 ID、令牌和完整采样，冲突时保留原持有者和标记，反序列化的相同信封仍可确认。原负例修复后通过，独立源码复核没有发现该局部修改的阻塞问题。独立组合 21 项中 18 项通过、2 项失败、1 项错误；包括收据状态与完成时钟授权的失败。运行时有并行工作进程源码试验，无法归因于此修改，完整工具输出未另存日志；其中一个现场为 `/tmp/sdk-received-budget-checkpoint-2ulmeqbq/evidence.json`。工作进程试验因缺少接收端保护已撤回，定向测试保留在 `/tmp/sdk-worker-budget-checkpoint-handoff-20261105.py`，其曾两次在事实文件产生前失败，也曾捕获原始事实并写入待处理收据；该试验不能证明确认、恢复或稳定性。

冷重放仍有独立缺口：隔离 SQLite 探针 `/tmp/sdk-unregistered-ack-replay-probe-20261105.py` 先正常发布真实预算采样，再以从未登记过的令牌和已有采样调用内部接收确认接口，当前实现因水位足够而接受（输出 `/tmp/sdk-unregistered-ack-replay-probe-20261105.log`）。该探针直接调用内部接口，并未证明生产 Runtime 收据可以生成任意令牌；它说明水位本身不证明特定令牌已被确认。处理该缺口需要精确且持久的令牌／采样确认、原子提交和迁移／旧写入者方案；现有冷重放不能据此视作已验收。

预算扣费修订：实际 `AgentApp._charge` 原先逐个祖先扣费，中间祖先额度已耗尽时请求虽被拒绝，应用及更上层祖先仍被扣除一次；使用真实 SQLite 的定向负例在修订前失败（`/tmp/sdk-agent-atomic-budget-charge-before-20261105.log`）。当前源码在一个预算存储事务内核对并记录全部祖先，兼容已归档及部分保留的旧逐范围记录；原负例、旧记录重放、未知拒绝、期限跨越、同请求并发及实际进程在提交前／后退出共 8 项通过（`/tmp/sdk-agent-atomic-charge-process-20261105.log`）；连同现有预算账本组合共 30 项通过（`/tmp/sdk-agent-atomic-charge-final-20261105.log`）。独立源码复核未发现该范围的阻塞缺陷。此修订不阻止仍在运行的旧代码继续使用原来的逐范围路径，不证明下游接纳与执行恰好一次，也不接通 token 预算。AgentApp 集成组合 2 项中 1 项通过，另一项在原有 35 秒等待内超时（`/tmp/sdk-agent-atomic-charge-integration-local-20261105.log`）；进一步诊断见下，不能把该组合记为通过或断定由该修订引起。

超时诊断保留三个独立现场 `/tmp/sdk-charge-diagnostic-8xe6mvz3/`、`/tmp/sdk-charge-diagnostic-3ku9_hlp/`、`/tmp/sdk-charge-diagnostic-v4p84ti5/` 及线程采样 `/tmp/sdk-charge-integration-diagnostic-20261105.log`。该次诊断与旧预算采样方案的源码编辑并行，代码加载版本未被冻结，不能作为当前固定制品的验收。只读核对表明三次中间调用的 effect 均记录实际合成成功，但完成事实为 `completion_time_unknown`，原因是 `completion_clock_original_floor_unproven`；随后子等待超时或租约失败，根调用进入 `recovery_required`。其中 agent_calls 场景拒绝的 leaf 在所有范围均无扣费记录，符合本次原子拒绝预期。该现象与已知完成时钟问题一致，但不能仅凭现场确定其根因或排除扣费改动对调度时序的影响。三个原超时均保留。

在撤回旧采样尝试、停止相关源码并行修改后，使用原断言和 35 秒等待复跑同一集成组合，耗时 100.439 秒：普通 AgentApp 执行／重开测试通过，祖先限制测试的 agent_calls 和 call_depth 子场景超时，model_turns 子场景没有报告错误（`/tmp/sdk-agent-atomic-charge-fixed-source-20261105.log`）。该次临时现场由测试自身清理，无法将其两个超时直接归因于前述诊断现场；整体仍失败，不是当前安装包验收。

旧版预算采样的局部修订已撤回。独立检查发现它引入新的持久未决采样，但 worker 关闭路径不能保证将精确事实交给完成恢复；另一个受保护采样路径和冷恢复入口也未遵守相同的较早采样检查（组件探针 `/tmp/sdk-budget-recovery-handoff-review-20261105.py`、`/tmp/sdk-budget-cold-recovery-review-20261105.py`、`/tmp/sdk-budget-guarded-sibling-pending-review-20261105.py`）。这些探针不能单独证明完整 Runtime 已发生对应恢复事件。单纯让所有较早登记阻塞也会让尚未采样即死亡的生产者无限阻塞其他采样；要修复须同时定义可认证的生产者生命周期、原始事实交接、跨进程恢复和旧写入者隔离。撤回后原始真实 Runtime 负例仍错误判定成功（`/tmp/sdk-legacy-clock-reverted-20261105.log`）；G14／G15 保持未完成。

最新定向进展：本地截止时间投影与可发布的预算采样分离；Windows 路径在采样所有者忙碌而无可见 token 时保留 unknown。主执行复验相关三个模块 16 项通过（Linux，0.490 秒；包含真实预启动调用、实际 SQLite 和 Windows 模拟）。真实 Runtime 交付组合仍为 22 项中 2 项失败，按时返回但效果收集延迟时可能保持 running（`/tmp/sdk-local-projection-runtime.log`）；在独立进程中恢复本轮采样入口改动后两项仍失败（`/tmp/sdk-local-projection-baseline-check.log`）。旧采样者及外部保留预算信封的全局时序缺陷仍未解决，上述定向通过不能代表 G14／G15 或原生 Windows 验收。

副作用失败诊断修订：外部操作抛错后，自定义异常的格式化代码原可能再次抛错，导致效果保留 performing，未立即记为 indeterminate（修订前真实 SQLite 失败：`/tmp/sdk-effect-failure-diagnostic-before.log`）。当前避免运行任意异常格式化或元类方法，保留安全的异常类型，成功记录后以原异常为 cause 报告需要恢复；四种精确内建异常在参数为有界普通字符串时保留消息，其他异常消息标为不可用。这会减少其他异常的诊断文本。真实 SQLite、线程 Runtime、并发防重、租约和超时相邻组合 8 项通过（`/tmp/sdk-effect-failure-diagnostics-related-20261105.log`）；单独的真实 Linux 进程 Runtime 检查通过（`/tmp/sdk-effect-failure-native-process-20261105.log`）。独立审查找出并复核修订了恶意元类类型比较和类型名读取问题。数据库记录本身失败或被中断时仍不可声称已标记，原生 Windows 未验证；该修订不代表 G12 整项通过。

本轮独立复验：原停止期限四项中两项仍失败（`/tmp/sdk-host-deadline-independent-20261105.log`）；真实 Runtime 的两个按时返回测试及旧采样错误成功测试共三项仍失败（`/tmp/sdk-delivery-clock-independent-20261105.log`）。另在允许本地网络的环境重现真实适配器 EMFILE 后获取状态 pending、账本 prepared，按 errno 单独判断无资源不安全。上述复验均未调整原期限或验收断言。

G17 验证器现于实际资源准入返回后保留原有资源释放顺序观察，即使场景后续失败仍随报告返回；取消或期限内未准入不发布该观察。真实资源池结合受控后续失败的定向测试和其他证明检查共 20 项通过（`/tmp/sdk-g17-verifier-grant-observation-independent-20261105.log`）。被模拟的是验证器场景后续失败及释放证明，不是原生 Agent 验收；原受限场景的完成时间 unknown 根因仍无法从旧记录确定，G17 未通过。

停止时限还存在独立锁阻塞：定向探针在另一线程持有宿主内部锁时观察到 `stop(.1)` 超过 0.35 秒后仍未返回，释放锁后返回 false（`/tmp/sdk-g16-lock-deadline-probe.py`）；该人工持锁证明机制，不证明实际生产持锁时长。普通 `atexit` 在非守护协调线程退出之后运行，不能负责启动该线程正等待的撤销（`/tmp/sdk-g16-public-atexit-probe.py`）。上述结果不排除其他生命周期设计。

Linux 控制端点另有原型：登记预先分配的原生描述符槽位后调用 libc socketpair，正常通信、真实 EMFILE 空槽、返回边界注入及独立原生 guard 收据检查分别得到预期结果（`/tmp/sdk-g12-raw-owner-linux-probe.py`、`/tmp/sdk-g12-raw-guard-probe.py`）。独立复核实测该原型两次并发获取可在第二次仍运行且持有真实描述符时错误报告 settled（`/tmp/sdk-g12-concurrent-owner-review.py`）；后续单次获取原型另被复现借用计数退还中断后重试可错误关闭另一持有者描述符（`/tmp/sdk-g12-one-shot-unpin-review.py`）。高编号描述符会使原型 select 失败，sendall 原型还未保持整体截止时间。这不是产品实现：并发获取、关闭未知、fork 继承、超时与中断等尚须完整解决。不得据此将 G12 标记通过。

后续原型用唯一借用令牌避免重试退还其他使用者，并在 fork 子进程中以原进程身份阻止该副本声称所有者关闭（`/tmp/sdk-g12-token-owner-probe.py`、`/tmp/sdk-g12-pid-token-fork-probe.py`）；丢失的借用令牌保守保持未知。真实 guard 握手与清理收据亦有独立原型检查，但 fork 出来的其他进程仍可持有端点副本，Popen 和进程流也需要独立所有权。复核发现 native 调用返回后至 Python 读取 `ctypes.get_errno()` 之前，回调可改变该线程的 errno，因此空槽和后读取的 errno 不足以认证失败原因；完整解决还需原生侧原子记录返回值与 errno 或采用不依赖该原因的合同。未将原型接入产品。

本机本次只确认 Linux x86_64 / CPython 3.12.3；PATH 中未发现 Python 3.10、3.11、3.13，`/dev/kvm` 不存在。未联系远程主机或运行 CI；其他平台及版本的当前制品证据仍缺，不能据此将它们视为不适用。

当前主要未完成项：

- G12：控制通道创建失败时的资源交接可能不明，不能凭报错直接认定清理完成并重试。
- G14／G15：已修复一个有登记采样保护的交错，但入口和旧版公开预算接口仍可复现实际返回时间误判；旧版恢复与只读兼容未闭合，非空 token 上限也尚不支持。
- G16：限时停止在关闭或撤销线程启动受阻时可能超时不返回；线程池构造受阻的部分场景已有修订和定向验证，但构造返回与所有权交接的全部边界尚未证明。启动、停止及清理所有权需要完整修复。
- G17：资源准入验证器已修订，较早候选的真实不限资源单场景通过；受限资源、完整监督及最终候选整体验收仍未通过。之前较早脚本的两场景失败保留为诊断证据，原因尚未全部确认。
- G18：已知缺陷修复后需冻结最终制品，按受影响范围复验并运行完整回归；其他 Python 版本及 Linux ARM、Windows x64／ARM 的当前制品证据仍缺。G03、G04、G06 等历史分项也须补齐最终候选证据。

原始 50 项旧效果恢复相关组合有 4 项失败、2 项错误；其中一项夹具已定向修复，其他结果尚未消除（`/tmp/sdk-legacy-effect-replay-focused-current.log`）。该组合不是上述 2419 项完整回归，不能把两者的失败数相加或作为完成比例。

## 当前候选与真实执行

- 分支：本地 `release/0.8.0`，开发版本 `0.8.0.dev1`。未推送、打 tag、发布或部署 ModPort。
- 第四候选（历史）wheel/sdist：`/tmp/agent-control-080-candidate04/dist/`；独立解释器：`/tmp/agent-control-080-candidate04/venv/bin/python`。构建通过本地 setuptools 后端，不触发 CI。后续 goal 循环及产物版本源码变化不属于此候选。
- 第四候选历史证据：`/tmp/agent-control-080-evidence/native-04/acceptance.json` 与同目录 `G01.json`、`G02.json`、`G03.json`、`G04.json`、`G11.json`。从 `/tmp` 运行，导入来源为独立环境的 `site-packages`，没有使用 checkout 的 PYTHONPATH。先前候选证据保留在 `native-01` 至 `native-03`。
- 第四候选 G02：Linux x86_64 / Python 3.12.3 / OpenCode 1.18.32；使用用户指定的本地 CLIProxyAPI。调用完成，文件产物为固定合成标记 `SDK_AGENT_NATIVE_OK`，记录 4 次推理请求，SDK Run 成功并清理进程。凭据只在宿主读取，不写入验收文件。
- 第四候选 G03/G04：seed → fast/slow → consumer 四个真实 OpenCode 会话，全部属于 `agent-run:de0a1473876844c7af83739b5ab77a6c`。slow 在宿主测试闸门等待时 consumer 未启动；放行后实际消费 `FAST_NATIVE` 文件快照和 `SLOW_NATIVE` 产物，提交 `FAST_NATIVE|SLOW_NATIVE`。计入 4 次 Agent 调用、15 次推理；同 ID 重放不新增执行，异内容重放拒绝。报告记录两次文件工具错误，但未记录实际请求路径，不能独立证明其分别对应越界和符号链接请求；宿主外部文件保持原值。直接文件工具目录替换竞争进行了 201 次替换，500 次操作均失败关闭，未发现外部改写。允许的真实文件写入由 fast 和 G02 正例分别证明。这里只覆盖 Linux x64；其他平台要求保留在 G18。
- 第四候选 G11：两个不同 SDK Run 并行使用冻结配置版本 `39e7249d629f41d58beaf01432d7875a`、`3637b267ff7a478d888fcfb8c0d1679e`。旧请求实际读到知识 v1，越权写入被拒绝；新请求读 v1、提交 v2，再次用旧版本写入被拒绝，最终 v1=`INITIAL`、v2=`UPDATED`，无覆盖。
- 第五候选 wheel/sdist：`/tmp/agent-control-080-candidate05/dist/`，隔离解释器：`/tmp/agent-control-080-candidate05/venv/bin/python`；Python 3.12.3、Linux x86_64、OpenCode 1.18.32。证据索引为 `/tmp/agent-control-080-evidence/native-05/acceptance.json`，同目录包含各 case JSON。G01 是配置检查；G02、G03、G04、G08、G11 使用真实模型；G13 是能力合同和拒绝检查。
- 第五候选 G03/G04：同一 SDK Run 内 4 次 Agent 调用、15 次推理；双生产者与 consumer、输入齐备、稳定 ID 重放和冲突拒绝通过。目录替换竞争发生 155 次替换，500 次操作均失败关闭，外部文件未变。
- 第五候选 G08：同一 invocation 和 session 的验证从 continue 到 passed，产物历史为第 0 步 `DRAFT_NATIVE`、第 1 步 `GOAL_NATIVE_FIXED`。blocked 和验证器异常均导致失败，不产生下游成功。
- 第五候选 G13：strict 请求在接纳前拒绝，未启动运行时；未提供原生 strict 后端，真实进程隔离没有验收。
- `admission.py` 在第五候选构建之后新增，现已接入当前源码的默认活动执行和 session 准入；它不属于第五候选；第七候选包含资源接线，但不构成 G17 验收证据。当前源码已接入进程内声明内存容量、预留和角色并发上限，默认内存准入关闭；等待父调用保留内存，不可能的等待返回 `agent_memory_deadlock`，已接纳子调用排队至父调用实际清理。宿主内存容量或角色上限变更须重开；持久资源所有权账本恢复所有先前清理未知的预留，包括已关闭计划；限制匹配的排队工作可以重开，不兼容原限制仍拒绝。对应原生清理确认且本地工具、代理、观察器和注册工作线程均停止后才释放容量；延迟清理可释放容量而不确定业务结果。
- 第六候选原生 G02、G08 通过，G07 因产物增加引号导致精确值不匹配而失败；该失败保留，不能改记为通过。
- 第七候选隔离安装的 G02、G07 通过：证据索引 `/tmp/agent-control-080-evidence/native-07/acceptance.json`，解释器 `/tmp/agent-control-080-candidate07/venv/bin/python`。G07 在一个有限 SDK Run 中执行 3 次真实模型 Agent 调用、16 次模型推理；call/send/wait、同请求重放、权限和等待环的原始拒绝代码、controller 活跃 lease 和约束、调用方接纳效果均有核对，实际产物为 `CALL_NATIVE|SEND_NATIVE`。第七候选包含资源接线与重开保护，但早于当前调用组源码。
- 当前源码另有实验性的 group open/send/close/wait/call/rework、SDK 回执、精确有序成员和消费者绑定。显式返工打开下一轮并冻结先前反馈，保留同一冻结 reviewer 角色和逻辑 reviewer ID，但使用新的 invocation 和原生 session，不宣称原生 session 连续。允许等待空组；空组消费者、空组返工、新迟到成员及第二个后继在相应 SDK effect 创建前拒绝。第七候选早于调用组源码；第八候选的原生 G05/G06 失败记录如下。
- 第八候选原生 G05/G06：证据索引 `/tmp/agent-control-080-evidence/native-08/acceptance.json`，各 case 为同目录 `G05.json`、`G06.json`。原始 600 秒期限内，第一位 reviewer 和四次 coder 均成功；第二次 reviewer 未在期限内完成，最终 reviewer 和 planner 为 `recovery_required`，G05/G06 均为 failed。候选 09 的 900 秒场景是新的独立尝试，不延长或改写原 Run 预算。
- 当前源码实现宿主提交的服务根请求、同代次单写者 FIFO、四种收件箱策略和持久状态 API。Agent 控制存储服务 schema 2 按角色配置切换递增 epoch；同 key、同 epoch 使用独立原生会话和稳定工作目录，配置返回旧值也不会复用旧代次。`trigger.mode: message` 仅对服务受支持；Agent 工具嵌套调用服务返回 `agent_service_session_required`。未知清理不释放活动所有权。前台 CLI 服务宿主已进入源码。候选 10 的 G09 已观察到精确输出、同 key 原生会话、FIFO、队列满、不同 key 并发、reject 和 replace_pending；cancel_and_replace 的活动所有者进入 `recovery_required`，代次隔离且替换请求仍排队，尚未观察到活动所有者清理，故 G09 整体仍为 not_run。候选 10 的 G10 真实 CLI／宿主场景通过，但候选 10 早于后续 guard、监督和保留服务停止修复，不能作为最终候选验收。
- 第一候选失败证据保留在 `/tmp/agent-control-080-evidence/native-01/`：火山方舟 HTTP 400 / `InvalidSubscription`，未产生所需产物。该失败未被改写为成功。之后由用户指定切换本地反代，新建独立测试请求和证据目录。

复现 G02（先在新环境安装当前候选 wheel；命令本身不会构建或安装包）：

```sh
/path/to/isolated/python -I /path/to/checkout/scripts/verify_agent_control.py \
  --case G02 --case G03 --case G04 --layer native --output /new/evidence/directory \
  --opencode /path/to/opencode \
  --provider-resources /path/to/host/AGENT_RESOURCES.md \
  --model local/gpt-6-luna
```

资源文件只在宿主进程内取用 `CLIProxyAPI` 段，不作为模型输入；其他宿主也可使用明确的 `--model anthropic/...` 或 `openai/...` 和宿主环境变量。测试不读取项目文件，工作区只授权固定输出文件。资源文件、密钥、模型可用性和未安装的依赖均不由验证器创建。

## 验收矩阵状态

下表逐项注明证据所属候选。历史候选的 passed 不代表页首最新安装包已完成该项；最新包只有明确列出的同包证据，不能将下表汇总为“只剩三项”。

下表保留各历史候选已验证的覆盖；候选编号表示实际执行来源，产品逐字节一致不改写执行来源。除明确注明当前产品外，不表示最新制品已整项通过。最终制品必须按变更影响补齐证据。

| ID | 状态 | 当前结论 |
| --- | --- | --- |
| G01 | passed（empty poll当前包限定合同） | `/tmp/sdk-empty-poll-candidate-20261106/config-contract/G01.json`，YAML／Python／CLI、双语Wiki默认值和非法配置拒绝一致；Linux x64／Python3.12。 |
| G02 | 未完成（保留历史候选通过证据，非当前包整项验收） | 当前局部 wheel 的真实 OpenCode 调用、精确文件产物、SDK 成功结果及对应 execution／attempt／fence 的原生清理回执通过，证据 `/tmp/sdk-current-managed-native-g02-20261105/G02.json`。尚非最终冻结候选，其他平台未覆盖。 |
| G03 | not_run（当前候选完整验收；历史分项已覆盖） | 候选 48 补充验证记录了真实工具请求路径及对应拒绝位置、允许写入和下游消费；直接文件工具目录替换竞争与已保存清理记录另有证据。工具响应未证明客户端接收，目录竞争不是模型桥接竞争；完整验收和原生强隔离仍未完成。 |
| G04 | not_run（当前候选完整验收；部分分项已覆盖） | 候选 33 覆盖真实双生产者、消费者及输入齐备闸门；候选 49 覆盖消费后确认前失败的真实事件重投，候选 51 覆盖消费后、SDK 准入前受控崩溃与重启。各自范围、身份和限制见后文；仍需最终候选的完整验收。 |
| G05 | failed（最新冻结真实场景已结束） | session69734退出1，`/tmp/sdk-owned-return-groups-rework-20261105/acceptance.json`及G05.json；原3600秒截止09:48 UTC，TimeoutError。最新sampler包尚未复验真实场景；源码修正不能追溯为通过。 |
| G06 | failed（最新共享真实场景已结束） | session69734共享场景失败，G06.json记录TimeoutError；真实歧义／缺输入／全部准确清理收据仍缺。没有新增模型请求。 |
| G07 | 未完成（保留历史候选通过证据，非当前包整项验收） | 真实模型 call/send/wait、稳定重放、权限和等待环拒绝、controller lease/约束及调用方接纳效果通过。 |
| G08 | 未完成（保留历史候选通过证据，非当前包整项验收） | 真实模型同 session continue → passed、产物版本历史，以及普通 SDK failed 的 blocked 和验证器异常负例通过。 |
| G09 | 未完成（保留历史候选通过证据，非当前包整项验收） | 两个实际并发宿主调用者、两条同键 FIFO、独立会话、队满与四种策略通过；启动前取消替换及发送后未知隔离均有精确 SDK／原生清理证据。 |
| G10 | 未完成（保留历史候选通过证据，非当前包整项验收） | 独立 CLI 宿主、客户端退出、跨 Run 会话续接、崩溃后队列恢复及准确取消通过；增强验证器核对原预算、SDK 绝对期限、故障前 effect 身份、finish 和认证原生清理。其他原生平台未验收。 |
| G11 | 未完成（保留历史候选通过证据，非当前包整项验收） | 配置切换、活动请求原配置冻结、实际知识读取、越权拒绝及版本冲突不覆盖通过。 |
| G12 | 未完成（当前安装包相关238项通过） | `/tmp/sdk-stop-handoff-candidate-20261106/expanded-result.json`及expanded-authorized.log：原199项、新增采样5项及宿主／停止报告34项全部通过、244.613秒，覆盖此前3条错误路径；此前失败证据保留。仍需完整失败分类与最终原生路径验收，不能以相关组合代替整项。 |
| G13 | passed（empty poll当前包能力拒绝合同） | `/tmp/sdk-empty-poll-candidate-20261106/config-contract/G13.json`；无strict后端时接纳前拒绝。原生强隔离后端未提供、真实隔离未验收。 |
| G14 | 未完成（保留历史候选通过证据，非当前包整项验收） | 四个指定真实崩溃窗口通过：B根意图已提交／SDK提交前8项；A SDK admission回执已存在／Agent尚未mark_submitted 8项；C实际上游写出后unknown、隔离及不重放16项；D准确消费后未确认、重启同outcome新代次确认及后继成功13项。证据目录分别 `/tmp/sdk-g14-plan-read-native-b-20261105/`、`/tmp/sdk-g14-current-a-20261105/`、`/tmp/sdk-g14-current-c-20261105/`、`/tmp/sdk-g14-d-receipt-20261105/`。151产品文件与安装包一致，独立审查无本范围阻塞；不证明任意外部副作用恰好一次、不代替G16停止或G18其他平台。 |
| G15 | not_run（当前候选完整验收；历史分项已覆盖） | 候选 34 的父子共享预算、耗尽与部分重启保留有历史证据。当前非空 token 预算已部分接入 SDK 自有 OpenCode 代理，当前安装包 47 项局部检查通过；宿主资源未提供总计费 token 上界合同，真实 token 验收仍缺，不能以合成提供方代替。native-cutoff 安装包已通过完成时钟相关 84 项和原文档示例，但技术重试原 15 项补跑失败，等待期限传播也未闭合，不能宣称完整预算合同通过。 |
| G16 | not_run（当前候选完整验收；历史分项已覆盖） | 候选 30 的多进程竞争及候选 34 的权限撤销、未知清理隔离保留历史证据；2026-11-05 已补预启动所有者、停止状态锁期限、撤销提交失败发布、启动器隔离和限时异常诊断的安装包定向证据（见页首），但不能据此认定完整停止合同通过；单启动器准入锁争用已由同一原期限与原所有者重试修订处理，当前安装包原复现已从约 .150 秒降到 .030168 秒（30 毫秒原期限）；当前 token-current 安装包的停止交接及真实子进程正常退出 9 项通过，3.797 秒，包含原两项启动阻塞失败，见 `/tmp/sdk-stop-current-installed-result-20261105.json`；这两项不再列为当前失败。最终原生竞争／重启／清理未知场景仍须用同一最终候选补验。 |
| G17 | 未完成（当前包CLI／旧API／类型范围已补） | owned-return-lock包旧API四模块39项、真实CLI14命令和正常宿主退出、六公开类型消费文件均通过；63项另含完成清理和默认控制期限。监督／资源的当前包完整真实范围仍缺，其他旧API完整回归未齐；不将历史159项标成当前包。 |
| G18 | 未通过（完整回归及平台证据未齐） | stop handoff包相关238项全部通过，同包G01/G13限定合同通过；完整套件、最终包文档及其他Python／OS／架构证据仍缺。empty poll旧包文档／导出和失败记录保留，不继承为新包验收；不推送、不发布。 |

## 定向验证与审查

配置、文件、代理、工具服务、真实 SDK 集成和打包边界的阶段定向套件通过；依赖图集成 7 项测试通过。来源测试适配器明确标记 synthetic，不冒充模型或原生验收。独立审查已发现并修复递归 YAML、嵌套默认值、长依赖链、提示词重放、确定性拒绝分类、工具及代理线程清理等问题。依赖图审查另外修复了失败节点提交窗口、缺失生产者、终态回执与取消冲突、无效预算覆盖；复审未发现这些改动的新 P1，未宣称完成真实崩溃验收。

Agent 源码测试 77 项全部通过且未跳过；goal 定向集成 9 项通过。此后另有独立 admission 5 项测试，不属于第五候选。当前源码 controller 定向 3 项（31 秒）、call/send 1 项（14 秒）、limits 4 项（76.6 秒）和 application 10 项（53.8 秒）通过；limits 先前的 fixture 就绪时序波动已修复。资源接线之前 Agent 测试 96 项通过；资源集成 3 项（37.061 秒）与配置更新 1 项（1.040 秒）通过。独立资源恢复修订测试 3 项（21.790 秒）通过，覆盖兼容配置拒绝重开及已关闭计划重开。调用组源码定向测试：运行时集成 2 项（80.297 秒）、生命周期 2 项（23.988 秒）、空组与非空组伪造审查权限 1 项（26.965 秒）、返工 1 项（43.354 秒）、存储组 6 项（主执行复测 5.481 秒）通过，均不代替原生模型验收。此前 103 项完整源码测试有 1 项取消测试失败；原测试隔离运行 17.823 秒通过，未确认框架缺陷；修订测试先建立实际运行与排队条件后通过（38.475 秒）。source-08 完整源码测试 115 项耗时 629.444 秒，1 项失败：group fan-out 第二个 Run B 超时；同一测试之后单独运行在 97.181 秒通过，但根因未确认，不能报告完整套件通过。日志 `/tmp/agent-control-080-evidence/source-08/tests.log`。独立审查在此前限定范围内未发现进一步 P1/P2；G14/G16 完整故障验收仍未完成。


服务源码合成集成测试曾有 4 项在 67.300 秒通过，但早于最新 epoch 和 controller 改动；后续复测当时仍在执行，不能把旧结果视作最终源码通过。服务存储定向测试 9 项在 6.129 秒通过。独立审查已修复未知效果或零计量时误判为确定失败，以及排队取消请求缺少 controller 的问题；仍需针对当前源码验证完整运行和恢复。组跨操作重放缺陷已修复：普通 SDK 回执与意图绑定精确操作、组、绑定和轮次；2 项真实 SDK 合成测试在 62.526 秒通过。

旧 child 相关完整套件运行到 104/208 项时，foreign-ancestor guard fixture 的 setup 耗尽原期限；已将该测试限定为原始 2 秒窗口、1 秒 setup，2 项定向测试在 7.159 秒通过。尚未确认框架回归，也未完成完整套件复跑。

`scripts/check_docs.py` 本轮检查 568 个本地链接、运行 4 个 README 示例，全部通过。Wiki 本地预览在 `/tmp/agent-control-080-wiki-preview/`；未发布远程 Wiki。中英文 Wiki 均已直接列出完整默认注册表并与代码逐项对照，后续代码变更必须同步文档。

历史验收运行均为 Linux；当前源码已包含 Windows 宿主锁和 Job guard，但尚无原生 Windows 验证。Windows 与其他适用平台不得因环境缺失或功能未完成改标不适用；G18 必须保留缺项直到获得有效证据。

候选 09 的原生 G05/G06 是独立场景：七个工作流调用及隔离调用成功，draft、返工、审查、反馈及绑定正确，唯一失败检查为 `coder_adapter_overlap`；整体仍为 failed。候选 10 G10 证据为 `/tmp/agent-control-080-evidence/native-10-host-b/acceptance.json` 和同目录 `G10.json`；重启后的队列恢复仅覆盖记录的崩溃窗口。G09 部分证据为 `/tmp/agent-control-080-evidence/native-10-service/G09.json`。

当前源码的 Linux subreaper guard／native ownership 有 4 项实际进程及合成协议测试在 3.994 秒通过，独立源码审查未发现 P1/P2；候选 11 的真实 OpenCode G02 通过，`ownership-readback.json` 记录对应 SDK 代次的认证清理；完整 guard 故障验收尚未完成。`ECHILD` 回执证明进程清理，不证明模型效果结果或 strict 隔离。监督账本和诊断准入已集成，真实 SDK／合成适配器对原始 effect 和共享 Run 预算的测试在 28.087 秒通过；原生监督尚未验收。宿主源码 6 项测试通过，已修复被移除服务的持久停止问题。source-09 全部 136 项 Agent 测试在 902.2536 秒通过，但其加载早于最新资源及清理修复，不代表最终候选；标准 legacy-child-12 的 104 项在 180.222 秒通过。legacy11 在 fixture setup 失败后以 139 退出，不能视为通过。

候选 11 的 native-11-faults：A 未捕获目标窗口，记为 not_run；C 整体 failed。C 观察到准确 guard 清理、原效果未知并隔离、无关原生调用成功，以及队列按原期限过期且零消耗；旧验证器要求总数为 2 的检查无效。新 helper 已修正但尚未重跑，不能把这些局部事实记为完整通过。资源恢复定向 6 项在 58.867 秒通过，账本／准入 11 项在 3.658 秒通过；这些结果不构成 G14、G16 或 G17 完整原生验收。下一候选仍待构建和验证。

候选 13 已独立安装在 `/tmp/agent-control-080-candidate13/venv/`，使用 Linux x64、Python 3.12.3、OpenCode 1.18.32 和本地反代。`native-13-basic/acceptance.json` 的 G01、G02、G13 通过。`native-13-faults/report.json` 的 A、C 通过：A 在实际 SDK 提交后回执保存前退出，重启沿用同一调用、SDK execution、原期限和一次 Agent 计量，最终具有一个准确代次的清理回执；C 在原调用第一次实际提供商发送后退出，重启保持原效果未知及会话隔离，原调用没有第二次发送，排队请求没有发送，无关会话真实成功。C 的进程清理确认不改变模型结果未知。

`native-13-commit-faults-b/report.json` 的 B、D 通过：B 在根意图已提交而 SDK Run／command 尚不存在时退出，重启实际完成原调用；D 在真实 producer 成功、结果及产物 v1 已消费且 consumer 意图已提交，但尚未提交 consumer SDK command 时退出。重启保留两个调用 ID、原期限、原版本绑定，producer 没有重跑，consumer 实际消费 `COMMIT_PRODUCER` 并成功，合计两次 Agent 计量。四窗口均使用明确记录的测试放置闸门，运行时和模型返回未被替换；宿主测试收尾的强制退出单独标记，不冒充业务清理。最初 `native-13-commit-faults` 因验证器参数名错误未启动，记录保留，修复后使用新目录重跑。

`native-13-resources/report.json` 的受限及默认关闭对照均通过。容量 128 MiB 下，已授权并实际处于工具请求的 96 MiB 父 OpenCode 存活时，64 MiB 子调用保持排队且没有 runtime effect 或原生操作；放行父调用后，父 runtime commit 和原生清理确认先于子运行时入口，子真实提交固定产物并成功。关闭内存准入时，子调用在父 SDK 执行仍 running、父清理尚未确认时进入。该结果只证明声明预留核算，不证明 OS 内存硬限制；整个 G17 仍未通过。

`native-13-supervision/report.json` 的稳定观察和过期观察场景通过：真实父 OpenCode 的提供商请求在宿主计量入口暂时等待，监督根据未新增产物生成一个稳定 incident，通过原父 effect 回执、原 controller 和原 Run 预算接纳真实 diagnostic Agent；重放返回同一调用，最终固定诊断产物正确。另一场景在暂存诊断后让父模型实际提交新产物，旧 incident 在创建 admission effect 之前被拒绝且没有派生子调用。闸门只定位观察窗口，不替换模型结果；`no_new_artifacts` 不表示业务没有进展。监督关闭／停止及整个 G17 仍为 not_run。

候选 13 的完整 Agent 回归日志为 `/tmp/agent-control-080-evidence/candidate13-agents-tests.log`：167 项耗时 1301.749 秒，2 failures、6 errors，不能报告通过。单独的 suspended-caller 测试保留原 20 秒等待也超时；线程采样显示 Kernel 控制锁在 SQLite commit 后排队，两个 I/O 快照间写入仍推进，尚不能证明死锁或把全部失败归因于负载。另确认关闭时存在子 waiter 仍访问已关闭 Kernel 的缺陷，当前源码新增有界 quiescence 检查，未知时保留宿主所有权；三个实际线程的定向测试通过，真实 SDK 关闭集成待验。独立审查还修复控制套接字创建失败时的资源预留泄漏：仅在尚未尝试 Popen 的活调用保存准确的 `not_launched` 证据，Popen 异常仍保留未知。该修复三个定向测试通过。上述新源码与只读共享根目录接线均晚于候选 13，最终候选须按影响范围重验。

本轮 `scripts/check_docs.py` 在 README.md 第 2 个原有示例超时后失败，不能沿用先前 568 链接／4 示例通过作为当前结果。失败证据由脚本保存在 `/tmp/sdk-docs-README.md-example-2-7l93w_0g/`；后续须保留原期限重验，不通过延长示例预算消除失败。

候选 13 的 `native-13-groups/G05.json`、`G06.json` 均为 failed。两轮真实 coder 重叠、两次 reviewer、显式反馈绑定、原始 admission/group 回执、稳定重放、相同 Run 与预算，以及隔离 Run 均通过了各自检查；只有未关闭组负例未命中：模型使用字面量 `group0`，返回 `agent_group_unknown`，没有实际测试返回 ID 所代表的未关闭组。不能以其他检查通过覆盖这一缺项。验证提示现已明确要求保存并使用真实 opaque ID，须在新目录、新 Run 中复验，原失败保留。

候选 14 的真实 SDK 关闭集成失败，发现 `host.stop()` 会先关闭 Kernel，之后才检查子等待线程并不安全。源码已改为设置关闭标记、拒绝新 dispatch、等待实际等待线程退出，再停止宿主；未在原有关闭期限内退出则保留 Kernel、routing 和 OS 锁。独立审查认可此顺序。原测试不改期限重跑通过，1 项耗时 27.723 秒；四项 coordination 线程测试和三项 prelaunch 测试的先前结果仍只属于源码。候选 15 已基于此顺序及公共类型注解构建 wheel/sdist，安装与定向验收尚在进行。

Python 3.10 设置的本地 mypy 检查通过全部六个公开 API 消费文件，包括新增 `tests/typing/agents_consumer.py`。检查覆盖 lazy 导出的 AgentApp/AgentHandle/Invocation/AgentRun、动态角色对象、上下文管理器与后继调用的准确类型，并用反例阻止静默退化为 Any。只修改本地 CI 检查入口，未运行或触发 CI。


候选 15 的独立 wheel/sdist 位于 `/tmp/agent-control-080-candidate15/dist/`，导入源为该候选 venv 的 `site-packages`。`native-15-shared/report.json` 的 11 项检查全部通过：真实 producer 读取和列出宿主授权只读共享根，写入被拒绝，发布文件产物；consumer 的原始绑定冻结后宿主修改源文件，真实 consumer 仍提交原始快照。两个调用同属原 SDK Run／期限，计量 2 次 Agent、15 次模型请求；普通 runtime effect、controller／SDK 代次和准确认证清理回执均匹配。该结果仅覆盖 Linux x64、Python 3.12.3、OpenCode 1.18.32，不替代全部文件竞争验收。

`native-15-supervision-stop/report.json` 的 disabled_and_stop 通过：关闭监督时实际 OpenCode 请求到达本地计量代理，记录窗口内无 monitor、诊断或子调用；放行后真实模型完成产物。停止场景在诊断接纳前撤销原调用，原 incident 被拒绝、无派生 effect 或调用，原 SDK 身份、期限、一次 Agent 计量及准确原生清理均核对。停止闸门位于上游发送之前，因此该场景只证明真实请求到达本地代理，不声称提供商已执行。稳定／过期场景在该报告为 not_run，完整 G17 仍为 not_run。

候选 15 定向复验 `candidate15-prior-failures.log` 的 14 项真实 SDK／synthetic 适配器测试在 183.705 秒全部通过，覆盖 call/send、两类后代取消与无关调用、等待环、祖先预算以及 goal 续接／异常／重放，原预算未延长。suspended-caller 原 20 秒等待先失败，保留 `candidate15-suspended.log`；增加诊断信息后原期限复验在 15.911 秒通过，保留 `candidate15-suspended-diagnostic.log`，不据此推断旧超时根因。关闭、协调和 prelaunch 定向测试通过；共享输入集成初次因测试辅助函数 name 参数冲突失败，原日志保留，修正为 tool_name 后 1 项在 12.596 秒通过。定向结果不覆盖完整回归失败。

当前源码新增并行 close 互斥及旧宿主条件移除，真实 SDK 竞争关闭／重开测试 1 项在 1.993 秒通过；候选 15 不含此修订。shell／本地 MCP 的宿主授权和 Agent 请求双重限制、配置版本／冻结计划中的 opaque 授权版本已进入源码，三项真实 SDK 接纳／重开测试在 5.828 秒通过，未运行模型。缺授权在接纳前拒绝，版本漂移在新调用／重放／runtime effect 前拒绝，不同版本无法重开未完成计划。同一版本却修改命令的情况明确按受信宿主责任处理，SDK 不比较秘密配置内容；该限制与待补真实进程树清理证据已写入双语 Wiki。新源码尚不属于候选 15 的原生证据。

当前文档检查已恢复通过：`docs-after-suite-15.log` 记录 568 个本地链接及 4 个 README 示例，无跳过。先前示例超时证据保留。之后 shell／MCP 文档修订仍须在最终候选重新检查。


候选 15 的 `native-15-groups/acceptance.json`、`G05.json`、`G06.json` 现在均为 passed：新 Run 保持其原 3600 秒预算，真实 planner／每轮两个重叠 coder／两次 reviewer 和隔离调用成功；显式返工、原逻辑 reviewer、产物版本和反馈绑定、调用组及 SDK 原始回执、权限、稳定重放和准确期限／预算核对通过。本次未关闭组负例使用实际返回的 opaque ID，命中原始拒绝。候选 13 的字面 ID 验证失败没有被改写。

候选 16 独立 wheel/sdist 位于 `/tmp/agent-control-080-candidate16/dist/`，导入位于该 venv 的 site-packages。权限、prelaunch、协调线程与关闭的 20 项定向测试通过：源码 28.616 秒，安装包 19.668 秒，无跳过；六个公共类型消费再次通过。`native-16-capabilities/report.json` 和 `native-16-capabilities-cancel/report.json` 分别通过 17 项检查，两个场景各使用新的 SDK Run／原始 300 秒预算。真实模型实际执行 shell 命令及本地 MCP 工具，固定测试后代进程记录存活；准确原生七字段认证回执及独立资源账本身份均核对。正常场景 runtime effect 提交并发布 `CAPABILITIES_OK`；取消场景保持原 SDK execution／attempt／fence、controller 和期限，effect 为 indeterminate、调用 recovery_required，但本地进程树清理已确认且 AgentApp 正常关闭。此证据不宣称提供商／外部效果清理、强隔离或未知业务已解决。宿主未授权 shell／MCP 的请求均在接纳前被拒绝。

## 候选 17：任务实例与邮箱复验

新增 Agent 自有任务实例账本并接入实际 SDK。固定实例和按输入键实例具有稳定身份及私有工作区；所有会话对同一工作区保持单写者，每个续接会话保存独立原生状态目录。默认每任务实例行为保留。排队从原请求接纳开始计时，尚未派发不消费 Agent／模型次数；子调用的替换或取消策略须等待精确普通 SDK 准入回执。未知结果隔离实例，不因本地清理确认而释放业务未知。配置代次在根计划事务中冻结，A→B→A 不复用旧实例。

独立源码审查发现并修复两处问题：已完成调用的重放不应被当前实例所有者的等待关系拒绝；准入未知的队首不应挡住后续独立请求的到期处理。后者仍保留派发屏障，未知请求自身不被改写。存储 9 项在 2.988 秒通过，源码实际 SDK／合成运行时 5 项在 108.915 秒通过，日志分别为 `source17-task-store-fixed.log`、`source17-task-instances-current.log`。这些测试检查公开 snapshot、agent_context 身份、A/B/A 会话、共享单写者、独立实例、精确重放、递归拒绝和未知结果重启隔离，不构成原生模型验收。

候选 17 wheel/sdist 位于 `/tmp/agent-control-080-candidate17/dist/`，独立解释器为 `/tmp/agent-control-080-candidate17/venv/bin/python`；已核对导入来自该 venv 的 site-packages，包含新的任务实例模块，PyYAML 为 6.0.3。安装包和原生结果分别记录于下，不混合计算通过状态。

候选 16 的 `native-16-mailbox/report.json` 五个场景均返回 passed，包含两个实际并发宿主调用者、两条同键 FIFO 消息、队满、reject、replace_pending、原生启动前取消替换，以及已发送请求取消后的未知隔离和精确进程清理。独立复审随后要求额外核对 runtime effect 的名称及精确请求；旧验证器未记录这两字段，因此此报告保留为较窄历史证据，G09 不据此升级。已补齐共享验证 helper，候选 17 使用新目录重新执行。任务实例验证器另补齐原生 session 和会话范围 ID 非空检查，避免仅相等就误报续接。复审未发现这些修订的新阻塞项；真实结果以新报告为准。

候选 17 的 `native-17-mailbox/report.json` 五个场景全部通过：FIFO 11 项、reject 8 项、replace_pending 9 项、启动前取消替换 12 项、发送后未知隔离 10 项。正常调用逐一核对精确 `agent.runtime` 名称及 invocation 请求、普通已提交且无恢复元数据的 effect、SDK execution／attempt／fence、最终 Run finish 回执及准确原生七字段认证清理；每个 AgentApp 均正常关闭。启动前被取消的所有者始终无 SDK execution、effect、原生操作或 Agent／模型消费。已发送请求的所有者保持 indeterminate／recovery_required，原执行与预算不变；精确本地清理后，继任请求继续隔离排队、零派发零消费，并持续观察三秒。宿主响应处理闸门只证明实际 HTTP 请求写出，不宣称提供商同时处理或未知业务已回滚。每场景使用新状态目录、独立原请求和原始 300 秒预算，Linux x64／Python 3.12.3／OpenCode 1.18.32；其他平台仍由 G18 保留。

候选 17 的 `native-17-task-instances/report.json` 固定实例 13 项及按键实例 11 项通过，实际模型执行声明文件读写和产物提交，核对 A/B/A 原生会话身份、单写者工作区、原始独立 Run、排队零消费、重开后稳定请求及第四次续接。该版本用会话身份与实际执行证明续接路径，不含对话内容回忆挑战。

补充的 `native-17-task-history/report.json` 固定实例 16 项通过：新生成的随机挑战只在首轮 A 输入出现，第三轮 A 及宿主重开后的第四轮 A 均实际返回精确挑战；中间 B 使用不同原生 session，所有 Run、原期限和预算独立保存。成功 SDK 工作区文件读写的字面内容均未包含挑战，声明产物保持固定历史值，不能仅靠共享文件通过检查。报告只保存比较结果；挑战仍必然保留在冻结输入及原生对话存储中，不宣称完全无磁盘记录、编码排除或信息隔离。各轮普通 runtime effect、最终 SDK finish、七字段认证原生清理及 AgentApp 关闭同时通过。

当前安装包 14 项任务测试在 125.321 秒结束，13 项通过、1 项错误：已完成目标重放场景的根调用失败；原日志 `candidate17-task-tests.log` 保留。源码影响套件 35 项在 431.224 秒结束，2 项错误：取消场景未在原等待窗口观察到 queued 准入；动态等待环的根调用超时。日志 `source17-affected.log` 保留。未将这些错误归因于负载或认定完整回归通过；已在失败前增加状态证据捕获，保持原期限和等待值，正在单独复现。六个公开类型消费检查再次通过，日志 `source17-typing.log`。

随后三项安装包定向诊断在 83.688 秒全部通过，原预算和等待值未变，日志 `candidate17-coordination-diagnostic.log`。60 秒线程快照记录到 Kernel 验证事务 commit、其他线程等待 Kernel 控制锁，以及调用方等待工具响应；该运行后来完成，单个快照不能证明死锁、事务持续时间或旧错误根因。没有产生新的失败前状态快照，保留原聚合失败，不用这次通过抹除未确认事项。候选 17 文档检查通过 568 个本地链接、4 个 README 示例、0 跳过，日志 `docs-candidate17.log`。


## 候选 19：推理档位与自动触发

候选 18 在最后校验修订之前构建，仅保留未使用制品，不归属任何验收结论。候选 19 的 wheel/sdist 位于 `/tmp/agent-control-080-candidate19/dist/`，隔离解释器为 `/tmp/agent-control-080-candidate19/venv/bin/python`。验证已断言导入来自其 site-packages，未通过 PYTHONPATH 指向源码。运行时源码包含宿主授权的推理档位、定时／根 Run 状态触发、持久暂停及 CLI 控制。

推理档位只接受宿主明确声明的 OpenAI-compatible `reasoningEffort: low|medium|high`，非空 immutable host_tools_revision 同时冻结模型选项；未知或不受支持的档位在原生启动前拒绝。`native-19-reasoning/report.json` 的三项检查全部通过：真实模型精确输出、两次实际提供商 POST 均传递 low、原始普通 runtime effect 及认证清理正确。原请求预算 180 秒，未延长。该结果仅证明 low 参数传递，不证明提供商内部推理行为，medium/high 尚未分别实测。

自动触发使用 Agent 自有 schema 1 事件账本，与根意图在同一事务绑定，SDK 提交继续使用原稳定 ID。状态触发只消费准确公开 finish 回执所确认的有限根 SDK Run 终态，不冒充任意子调用事件；新激活排除既有历史，激活时仍运行的来源在之后完成仍可触发。定时触发首次等待下一 UTC 时间边界，错过时间槽合并最新一个；每次事件是独立授权的根请求／预算。暂停持久保存，整宿主停止及重启不会自行解除，已接纳工作保留原身份与期限。独立审查发现并修复空历史基线重复初始化、遗漏激活前已运行来源、首次入口前激活及无法映射输入键目标等问题。

源码配置／存储／推理／能力 22 项在 0.936 秒通过；四项实际 SDK／合成运行时触发集成在 20.180 秒通过，检查去重、暂停重启续接、意图提交后中断恢复原调用及未来提示词丢失时恢复已有冻结命令。早期 `source18-triggers.log` 和 `source18-triggers-fixed.log` 保留两次测试夹具失败：夹具适配器未声明续接能力、上下文管理器先自动启动再植入时间槽；修正夹具后使用原预算复验，没有将旧失败改写为通过。

安装包 43 项配置、触发、宿主、应用测试在 125.208 秒全部通过，无跳过，日志 `candidate19-focused.log`；60 秒线程诊断仍保留，不把单个等待快照当成死锁或旧错误根因。候选 17 的另一轮串行任务／协调诊断 18 项在 158.187 秒全部通过，日志 `candidate17-task-limits-diagnostic2.log`；旧聚合失败继续保留，根因未确认。候选 19 文档检查通过 570 个本地链接及 4 个 README 示例、0 跳过，日志 `docs-candidate19.log`；Agent 公开类型消费检查通过，日志 `source19-typing.log`。本节后续文档变更须在最终候选重查。

首次 `native-19-triggers/report.json` 中定时场景 13 项通过，状态场景仅源模型精确输出断言失败，准确来源、目标执行及清理均通过。只读检查确认源响应为包含预期值的包裹字符串；源指令此前仅置于 JSON 字符串输入。夹具改为明确的源提示词文件和中性结构输入，保留精确输出断言、原 150 秒预算及失败报告。新目录 `native-19-triggers-rerun/report.json` 的状态 14 项与定时 13 项全部通过，两个宿主正常关闭，OpenCode 1.18.32。核对内容包括原始 SDK effect／generation、精确状态来源、独立 Run 与原预算、稳定事件绑定、重复扫描不重派发、持久暂停及重开后同身份同结果、准确七字段认证清理。该 Linux x64／Python 3.12.3 证据不替代完整 G18 和其他平台。


## 候选 20：本地模型回退与启动前技术重试

候选 20 wheel/sdist 位于 `/tmp/agent-control-080-candidate20/dist/`，隔离解释器为 `/tmp/agent-control-080-candidate20/venv/bin/python`。36 项安装包定向测试在 86.271 秒全部通过，无跳过，日志 `candidate20-runtime-focused.log`；导入来源已断言为该候选 site-packages。覆盖所有候选模型的配置校验、显式本地选择、跨提供商凭据隔离、重开与未知结果不重发、精确启动前证明、取消／原期限／预算阻断，以及配置和宿主版本约束。60 秒线程采样保留，不据其单独推断死锁。

`native-20-fallbacks/report.json` 整体 passed：主模型是宿主明确声明不可用的夹具别名，备选是真实本地反代模型；两次独立原 Run 保留各自 150 秒、4 次 Agent／8 次模型轮次预算，精确输出及所选模型正确。两次均核对普通 SDK effect 提交、execution／finish 回执和准确七字段身份的认证清理。宿主关闭重开后稳定重放保持原身份且不新增提供商请求；第二次调用继续同一非空原生 session、实例、工作区和状态目录。该场景证明显式本地选择与身份续接，不证明提供商健康探测或对话内容回忆。

`native-20-retries/report.json` 整体 passed，11 项检查通过：只在第一次 `socketpair`、尝试 Popen 之前注入 EMFILE，实际模型随后返回精确 `RETRY_OK`。两个 native operation 分别具有准确 `not_launched` 和认证 cleaned 回执；同一原 invocation、SDK effect／lease／attempt／fence、Run、完整运行请求、会话、目录和冻结预算均保持，第一次故障零模型消耗、总 Agent 消耗一次、工具凭证重新生成、成功重试计数为一。宿主正常关闭。该场景不覆盖任何可能已发送请求的重试，未知结果仍不重放。

上述原生环境为 Linux x64／Python 3.12.3／OpenCode 1.18.32。独立审查修复了陈旧上一 goal 轮次证明复用和同次执行混入其他 native operation 两个问题；新增负例检查必须仅有当前这一个新未启动操作。G17 完整旧 API／Agent 回归和 G18 平台矩阵仍未完成。候选 19 旧 API 完整回归正在运行，已记录取消时限与子调用并发失败及测试导入路径错误；原失败保留，定向诊断和修复不得代替完整通过。

候选 20 另通过 `native-20-budgets/report.json` 三个独立原生 Run：nested 的 12 项检查、goal 的 8 项检查、exhaustion 的 12 项检查全部通过。父子普通 SDK 结果及准确认证清理匹配，子执行绑定原 controller attempt/fence，根及祖先 Agent／模型用量一致；模型出口观察到 6 次请求尝试。goal 两轮共 3 次出口尝试，保持同一 invocation／effect、原期限、工作目录和非空续接 session，只消耗一次 Agent。上限为一次 Agent 的根请求产生一个明确失败的子意图，子级没有稳定 SDK execution、runtime effect、native operation 或出口请求；父级完成，有限 Run 按失败结算，宿主关闭重开后的稳定重放保持原身份／期限／用量且零新增出口尝试。每个 Run 原预算均为 240 秒；出口计数不等于提供商确认接收。此切片不覆盖 token 预算，也不足以将 G15 整体记为 passed。

## 候选 21：取消诊断准入边界修订（未完成验收）

候选 21 wheel/sdist 已构建于 `/tmp/agent-control-080-candidate21/dist/`。运行时新增逐次原期限检查，禁止诊断 drain、最终 producer 收尾及显式取消 journal 在过期后取得新写入窗口；未处理事实继续保留。准确 EffectRecoveryRequiredError 与证据写入失败同时发生时，保留原异常对象，以 cause 链报告后者。独立审查修复了批量 finish、reserve→append、receiver→ack 和旧事件 store identity 查询的遗漏；确定性测试验证队列在下一次 drain 仍可处理。

源码合并复验 `source21-cancel-deadline-final.log` 保留：28 个加载项中，一项 writer-release 的整体返回时间为 1.090258 秒，未满足原严格小于一秒检查；另一项 loader error 来自命令把实际 `test_cancel_telemetry_order` 写成了不存在的 `test_cancellation_telemetry_order`。因此此轮不得记为通过。此前 26 项源码定向通过及两项错误优先级定向通过不覆盖该失败。正在区分原控制准入期限与可选诊断持久化开销，原断言和预算未放宽。

旧隔离消费者的 0.7.3、单一 extra 和无 CLI 元数据断言已更新为授权的 0.8.0.dev1、两个可选 extra 与准确 Agent CLI；仍以无依赖安装验证核心，完整嵌套套件保留原 2700 秒预算。候选 20 的实际 wheel 元数据检查通过（`candidate20-consumer-metadata.log`），这只验证包内容，不替代完整隔离消费者执行。


## 候选 22 取消复验与控制工具接线

候选 22 位于 `/tmp/agent-control-080-candidate22/`，其构建输入为候选 21 sdist，加上最终共享可选诊断窗口的 runtime.py、取消测试和取消文档；`BUILD_INPUTS.txt` 记录具体路径。它不包含随后控制工具与服务 schema 3 接线。新共享窗口的源码定向 29 项通过（25.909 秒，工具输出留存，未另存日志）；持久写锁测试保留原一秒边界，观察 .44470 秒。候选 22 wheel 元数据及 133 个源码文件检查通过，未作为完整安装消费验收。

首次安装包取消／生命周期组 66 项失败：8 failure、3 error，125.127 秒，日志 `/tmp/agent-control-080-evidence/candidate22-cancel-lifecycle.log`。已确认该运行的 stdin 入口不支持 multiprocessing spawn，显式子进程也缺少 tests 导入路径。使用真实受保护脚本入口、根目录及 tests 导入路径后，第二次组运行 66 项，112.710 秒，仍有 1 failure、1 error，日志 `/tmp/agent-control-080-evidence/candidate22-cancel-lifecycle-guarded.log`。剩余分别为进程清理后旧取消日志的原一秒证据窗口到期，以及原两秒后继任务未达到 succeeded，尚未确认根因。首次 legacy retry 关闭时诊断未持久化的错误在单独原测试及第二组中通过，不能据此声明已定位。日志绑定测试现会在拒绝断言后还原故意损坏的 source_id，确保关闭阶段仍能持久化保留事实；没有删除拒绝断言。

当前源码新增 `agent_cancel`／`agent_resume` 与普通 SDK effect 接线，服务 schema 3 保存独立控制代次，取消子树标志与意图状态在同一 Agent 事务提交。独立审查发现并修复过期 lease 可投影、分拆事务、普通越权在 effect 回调内变成结果不明、claim conflict 被误报内容冲突，以及预算 checkpoint 推进导致正常重放冲突。实际 SDK／认证 loopback 工具链加存储定向 12 项在 57.076 秒通过（执行会话 95607，输出留存，未另存日志）；覆盖活动后代观察到取消、无关活动根请求继续成功、拒绝请求无控制 effect、effect revision 稳定重放、服务 resume 不解除之后的 host stop、会话隔离不变及原预算 envelope 不被新 checkpoint 替换。前两次工具链失败仍保留在执行记录中，未改写为通过。该组为合成运行时，不是原生 OpenCode 或崩溃重开验收。

候选 19 旧核心完整回归 1570 项在 1713.257 秒结束：6 failure、9 导入 error、18 skip；日志 `/tmp/agent-control-080-evidence/candidate19-core-regression.log`。导入错误涉及 sibling helper 路径，正在使用正确入口定向复验。18 个跳过均为真实 Windows 能力门槛（16 个 Job Objects、2 个文件共享行为），不作为 G18 通过。失败包括已记录的取消／child 并发、缺 setuptools 的隔离消费构建环境、停滞通知、进程最终 flush 顺序及硬编码旧版本断言；完整回归仍未通过。版本断言现改为核对独立 source version 常量，未新增指纹检查。


## 候选 23 安装包与原生服务控制

候选 23 是 `/tmp/agent-control-080-candidate23/source/` 的独立源码快照，含控制工具接线、服务 schema 3 和此前共享取消诊断窗口；它早于随后“进程清理／结果发布路径仅保留可选诊断”的源码修订。首次 `python -m build` 因未安装 build CLI 失败，未生成候选；之后使用现有 setuptools 后端在新源码快照成功构建 wheel 和 sdist。wheel 独立安装后，控制工具、控制存储、服务存储、服务集成及协调 28 项在 161.134 秒通过且无跳过，日志 `/tmp/agent-control-080-evidence/candidate23-control-services-installed.log`。元数据、可选依赖、入口、许可证与 134 个 Python 文件的源码对照通过，日志 `candidate23-consumer-metadata.log`；不是完整隔离消费套件通过。快照文档检查通过 570 个链接、4 个 README 示例、0 跳过，日志 `docs-candidate23.log`。

真实控制证据为 `/tmp/agent-control-080-evidence/native23controls/report.json`，执行解释器和 module 均明确核对候选 23 site-packages，OpenCode 1.18.32，Linux x64／Python 3.12.3。13 项检查全部通过，宿主关闭完成。模型实际调用自己的 agent_cancel，收到 agent_permission_denied，未创建对应控制 effect；实际发起两次相同 resume-once 和一次 resume-final。第一次投影后宿主 stop，重放保留 stop 和 effect revision；新 request_id 才重新开放服务接纳。两个服务请求同键同 session／工作目录，三个独立 Run 的原身份、deadline、冻结预算及运行时入口 deadline 均匹配；三个普通 runtime effect 成功提交，产物 CONTROL_OK 精确匹配，所有原生进程有匹配精确身份的认证清理回执。验证器不读取或输出密钥正文；私有测试运行状态可能含会话数据，未宣称其中没有原生转录。该场景不覆盖原生后代取消、任意崩溃窗口及完整 G16/G18。

候选 19 的九个导入错误模块经正确脚本及导入路径定向运行 145 项在 146.694 秒通过，日志 `candidate19-core-import-retry-all.log`；较早四模块另有 97 项通过记录，不相加为独立覆盖。父解释器已核对安装包来源，但没有独立断言每个子进程的 SDK 来源。原完整回归失败仍保留。候选 22 停滞通知原期限定向诊断通过 1 项（14.395 秒，`candidate22-stall-original-window-probe.log`），不能据此解释或改写原完整回归失败。

候选 22 取消两例首次定向复现均失败，证据 `candidate22-cancel-two-case-probe.log`；进一步定向两例在 8.842 秒通过，证据 `candidate22-cancel-two-refined-probe.log`。细化追踪确认可选 worker 清理／结果诊断同步写入发生在注册完成信号及结果结算之前，取消等待约 .4 秒；一次仅余约 6 ms 的已准入 SQLite 操作实际耗时约 57 ms，原期限检查不能中断已开始的事务。后继真实业务完成在原两秒预算内，状态发布晚于原测试等待。这些事实已用于源码修复：可选完成诊断保留到有所有权的队列，由现有后台和关闭路径落盘；接纳与启动前必需回执不变。独立审查未发现此范围阻塞项；真实进程的新回归在诊断 writer 被阻塞时仍发布原结果，释放后按原 producer 顺序落盘，源码单项 3.158 秒通过。尚无当前安装包复验，不报告两例全部修复通过。

## 候选 23 之后的源码验证（尚未形成最终候选）

控制重开源码两项实际 SDK／认证 loopback 在 26.214 秒通过，日志 `control-reopen-source-fixed.log`；提交不明场景增加明确 recovery_required 断言后单项 12.768 秒通过，日志 `control-reopen-indeterminate-final.log`。已提交原 effect 在正常宿主关闭／重开后只投影一次，之后的 host stop 不被第二次重开解除；控制提交不明时，原 effect 保持 indeterminate，意图保持 requested，服务不开放，原 Run、effect、期限和预算不变。旧夹具失败保留在 `control-reopen-source.log`。这是正常宿主重开证据，不能替代进程崩溃或真实模型恢复验收。

可选完成诊断修复后的源码组首次 92 项在 104.642 秒运行，2 failure，日志 `source-postprocess-affected.log`。一项为旧夹具在证据写入异常后立即要求可选 settlement note 已落盘；独立单项复现确认进程确已清理且取消已提交，但即时只读报告诚实返回 unknown（`postcommit-cancel-independent.log`）。夹具现在保留即时物理清理断言及报告状态，在已有 owned close/drain 后严格要求准确持久回执与只读重开，不创建新取消时间窗口。另一项 held final flush 夹具依赖 PYTHONPATH 中的 sitecustomize，但启动脚本的 `-I` 同时传播给子进程，屏蔽了观测钩子，因而未释放原 fixture gate。去掉此不适用的测试启动标志、保留导入来源断言后，原三秒预算单项在 2.416 秒通过，日志 `source-orphan-original-window-probe.log`。原失败均保留；修正入口的整组复验仍待结果。

修正入口的第二组源码 92 项在 133.364 秒结束，只有 legacy SQLite 错误分类夹具的关闭 error（`source-postprocess-affected-corrected.log`），取消原一秒日志窗口、后继原两秒任务和孤儿进程原三秒窗口均通过。只读诊断确认该夹具在一个未启动后台 settlement 服务的 Runtime 中累积六个独立合成探测；12 条 note 均已有准确 receiver receipt，最后一条 ACK 在已有 close 一秒窗口耗尽时未完成，未据此推断机器负载或锁根因。六个分类探测现各自使用独立 Runtime、保留原 close 窗口和错误检查，源码取消准入 33 项在 31.502 秒通过（`source-cancel-close-fix.log`）；这不把合成 running 快照当成真实取消证明。

独立审查另确认 close 完成条件遗漏已标记 finished 的 producer：事件送达后仍可能未执行 producer finish。当前源码增加仅用于 close/drain 的待完成条件，沿用原一秒窗口，保留未完成义务与显式 close 重试；不把结果不明的 producer 误标成 finished。真实 SQLite 两项回归验证原窗口内无法退役时报告错误并保留 Kernel、解除阻塞后的显式重试只退役原 finished producer，以及健康关闭仍保留 uncertain producer。与真实进程诊断阻塞回归合并 3 项在 3.836 秒通过（`source-diagnostic-close-postprocess.log`）。包含该修复的整组及安装包复验仍待结果。


### 当前源码诊断与返工复核

受影响源码组 `source-postprocess-close-final.log` 共 99 项，153.337 秒，仍有一项 close error。process provider-child 用例准确保留原始父子 provider_denied，但原关闭窗口内出现 `_UnpersistedDiagnosticsError`。`/tmp/sdk-provider-child-failure-process-mxvcfo9_/` 保留现场：18 条事件已送达、两条子调用事件未送达、两个 producer 仍开放，尚未解决，整组不算通过。

独立时序探测 `provider-child-close-timing.log`／`.json` 出现另一种较早失败：父调用 handler_error／database is locked，没有子结果，close 成功；不能用它解释原 close 失败。独立 process-only 探测 `/tmp/sdk-provider-probe-wqgd91tk/report.json` 保留 provider_denied，父调用 4.848 秒、close 0.233 秒通过，也不抹去旧失败。只读 SQL 确认暂时写锁竞争及同步提交开销，尚未识别原失败的子进程 SQL 和全部竞争写入者。未扩展执行或关闭期限、未自动重试 close 隐藏错误、未调用模型账户。

返工路由独立复核确认三个源码问题已修复：后继创建前检查确定性子准入、已关闭后继无新 effect 时提前拒绝、claimed effect 未知优先于内容冲突。关闭后准确重放的真实 SDK 单项在 72.949 秒通过（`rework-route-closed-replay-unsandboxed.log`），组／子身份、准确成员和子 effect revision 均不变。命令及沙箱启动失败日志保留。注入的策略拒绝不宣称为真实深度上限证据；安装包与原生路由验收仍待完成。

工作区所有权增加注册表写锁及本地 mutex 等待期间的原期限取消轮询后，八项测试通过，独立复核八项 2.658 秒无阻塞问题。FileTools 可写根目录扩展独立复核九项真实文件测试 0.158 秒通过。应用层已接入并通过源码审查，但模块结果不代替应用集成、安装包或原生验收。


## 候选 24：可写工作区与当前安装包验证

候选 24 是完整白名单源码快照，wheel/sdist 位于 `/tmp/agent-control-080-candidate24/dist/`，隔离安装导入来源明确核对其 site-packages。包含可选完成诊断、close producer 所有权、服务控制 schema 3、返工路由及可写工作区修订；不代表整体验收。无依赖基础环境与单独 `venv-yaml` 分开，后者离线安装同一 wheel 和 PyYAML 6.0.3，`candidate24-g01-yaml/acceptance.json` 的 G01 为 passed：YAML/Python 等价、双语 Wiki 默认值、四类拒绝及真实 CLI 通过。其他 G 项未因此升级。

源码工作区集成原四项在 29.769 秒通过；新增祖先冲突及取消未知保留分别在 9.638 秒、8.722 秒通过。38 项工作区／文件／应用／宿主相关回归使用具名 main 入口在 105.473 秒全部通过（`workspace-integration-baseline-file.log`）。较早 stdin 入口的两个 multiprocessing spawn 错误保留于 `workspace-integration-baseline.log`，未改写。模块／SDK 合成适配器证据不算模型验收。

`native24workspaces/report.json` 整体 passed，七项检查通过，宿主关闭完成。Linux x64／Python 3.12.3／OpenCode 1.18.32，候选 24 无依赖基础 venv 实际调用本地反代。四次实际运行时入口对应四个调用、三个有限 SDK Run；持久文件真实写入和产物提交、关闭重开后同请求零新增执行和新请求续读、共享写入及越界／状态写入拒绝均通过。生产者提交后宿主刻意改变共享文件，下游实际读到变化文件但消费原提交产物；原期限、冻结预算、普通 runtime effect 与准确七字段认证清理均核对。该测试不证明并发宿主或原生崩溃恢复。

`native24cancel/report.json` 为 failed，原报告和日志保留。十二项检查仅 `worker_running_before_cancel` 为 false：实际模型取消前，worker 已 recovery_required、runtime effect indeterminate、原生清理完成且尚未收到 cancel 标志。实际发送与取消工具、原身份和预算、后代范围、普通控制回执、准确清理、独立服务成功及 controller 输出检查通过；这些不能替代正在运行时的取消正例。正在区分夹具响应闸门与产品提前退出原因，未放宽断言或延长预算。

候选 24 安装包的工作区／返工路由／控制工具／重开和控制存储共 44 项在 259.101 秒全部通过，无跳过（`candidate24-workspace-route-installed.log`）。具名入口先断言 SDK 来自候选 site-packages，再仅加入快照测试目录；子进程使用快照测试路径，不指向当前 checkout/src。元数据、两个 optional extra、入口、许可证及 wheel 内 135 个 Python 文件逐字节源码对照通过（`candidate24-consumer-metadata.log`），未新增 hash 检查，未作为完整隔离消费者验收。

取消闸门独立诊断确认第一版只暂停首条 worker 请求，后续请求仍完成；真实取消前会话已结束，持有的代理回调继而触发 ProxyCleanupUnknownError。已修订验证器暂停所有 worker 出口写入，按原期限／取消解除；严格运行中断言保留。首次独立验证器 bundle 放在错误目录，使来源保护把整个 /tmp 误视为源码，模型调用前 not_run（`native24cancel-gated-all/report.json`）；修正为 source/scripts 布局后的新报告另行保留，不改写前两次结果。

源码原预算进程诊断 `/tmp/sdk-provider-drain-trace-j4mivhj0/` 保留 provider_denied；关闭 .399 秒通过，原一秒 drain 内处理十条 note 及两个 producer finish。此前记录瞬时 SQLite 竞争，关闭期间无观测到 SQL 错误；最佳努力 datagram 追踪可能丢事件并影响调度，不能解释原聚合 close 失败。

### 服务实例 schema 4（当前源码，未入候选 24）

新增服务显式 fixed／keyed 实例身份和实例级单写者 FIFO；默认服务按会话行为和原目录保持。会话仍独立续接；实例共享私有工作区。队列、配置 A/B/A、原期限与预算冻结；同会话替换不取消其他会话的实例所有者，业务未知隔离整个实例。schema 2／3 不再自动升级，提供 `upgrade_service_store` 和 CLI 显式事务升级，持相同宿主独占锁。源码新旧存储及控制存储 27 项在 17.039 秒通过（`source-service4-store.log`）；公开升级／实际 CLI 三项在 2.456 秒通过（`source-service4-upgrade.log`），含活动宿主拒绝、真实旧表启动前无写入、事务中断回滚与原身份／隔离保留。

独立源码审查指出：服务清理路径缺少本地及持久资源预留核对；旧服务 schema 拒绝之前可能先创建其他 Agent 表。已分别加入准确 execution／effect 与资源检查，以及宿主锁内初始化前只读预检，复审无此范围未解决阻塞项。真实 ToolServer 回调的存活会在 effect 内触发清理未知，因此不能声称该路径仍会提交普通 effect；另用受支持的注册 worker 路径验证已提交 effect 但资源未退场的边界。相关 SDK 集成、当前安装包和原生验证仍待结果。

修订后的候选 24 取消验证报告 `native24cancel-gated-all-layout/report.json` 为 passed，十三项检查全部通过，宿主关闭完成。验证器单独更新，SDK 仍从原候选 24 的 site-packages 导入。取消前 worker 确实处于 running、runtime effect 为 performing，实际模型发起取消；两个 worker 请求闸门均在原期限或取消下结清，准确后代范围、普通控制回执、原身份与冻结预算、原生清理及无关服务请求成功均核对。原请求链仍为 recovery_required，不把进程清理完成当作业务结果已确定；原失败和来源保护 not_run 报告均保留。此切片不证明提供商已回滚请求，也不替代完整 G16 或崩溃验收。

服务实例源码 SDK 集成十二项在 125.377 秒全部通过（`source-service4-integration.log`），使用具名受保护入口和实际 SDK／认证 loopback 工具。覆盖 fixed 跨会话 FIFO 与共享工作区、会话独立续接、keyed 并行隔离、未知结果在重开后隔离整个实例、配置 A/B/A 和停止恢复保留旧队列绑定，以及默认服务回归。存活 ToolServer 回调的 effect 不明时不释放实例；普通 effect 已提交但注册 worker 仍存活时，后继也没有 SDK command 或模型消耗，准确资源退场后才准入。适配器为合成运行时，不作为原生模型证据。当前文档检查通过 570 个链接和四个 README 示例，无跳过（`docs-source-service4.log`）；当前安装包及原生服务实例仍待验证。

新定向返工原生验证器的独立审查发现执行入口身份／预算、实际用量和 open 状态重放快照断言不足；修订与复审完成前不启动模型，不宣称该路径已验收。

## 候选 25：显式服务实例与返工路由复验

候选 25 是新的完整白名单快照，wheel/sdist 位于 `/tmp/agent-control-080-candidate25/dist/`，含服务 schema 4、公开锁内事务升级、服务资源退场核对及复审后的原生验证器。原核心 99 项中的 close 错误尚未定位，不代表最终候选。独立无依赖安装的 wheel 元数据与 135 个 Python 文件逐字节对照通过（`candidate25-consumer-metadata.log`）；单独离线安装 YAML extra 后，G01 passed（`candidate25-g01-yaml/acceptance.json`）。安装包 Agent 类型消费检查通过（`candidate25-agent-typing.log`）；快照文档 570 个链接、四个 README 示例通过，无跳过（`docs-candidate25.log`）。这些结果不代替完整消费者或 G17/G18。

受服务集成影响的源码 goal、任务实例及准入二十项在 95.193 秒全部通过（`source-service4-affected.log`）。候选 25 安装包的存储／升级／服务实例／资源清理／默认服务／goal／任务实例／工作区共 62 项在 401.461 秒全部通过，无跳过（`candidate25-service-installed.log`）。使用具名受保护入口，先核对 SDK 来自候选 site-packages，再仅加入快照测试路径；子进程使用快照测试路径，不指向 checkout/src。这不是完整旧 API 或隔离消费者回归通过。

`native25service-fixed/report.json` 整体 passed，五项检查全部通过，宿主关闭完成。SDK 导入来源为候选 25 的 site-packages，Linux x64／Python 3.12.3／OpenCode 1.18.32。三个实际调用对应三个不同有限 SDK Run，初始 180 秒／4 Agent／16 模型轮次上限、原身份／期限／冻结预算及实际用量均核对。A 占用 fixed 实例时，B 会话排队，无 SDK command、native operation 或消耗；B 的实际适配器入口再次核对 A 的准确普通 effect、成功 SDK finish 和七字段原生清理。两会话真实操作同一文件，原生 session 和运行时目录分别隔离；关闭重开后稳定重放保持准确 service／session／effect／清理／finish／用量，无新增入口，新 A 请求续接原 session。实例序列为 1、2、3，配置代次相同。宿主入口闸门只证明排队窗口，不声称提供商并发。此切片不覆盖原生 keyed、对话回忆、独立 serve 进程或崩溃恢复，不据此将 G09/G10/G16 整体记为通过。

定向返工验证器已修复入口身份与预算、实际用量、SDK envelope 原期限和非空开放组重放断言，独立复审无此范围具体阻塞项。当前候选 25 的真实模型路由验证已启动，保留一个原始有限 Run，不自动重试或扩展预算；结果待记录。

核心关闭的序列追踪另保留 `/tmp/sdk-provider-drain-trace-1ildumzk/`（`provider-child-drain-trace-seq.log`），再次出现 `_UnpersistedDiagnosticsError`，但业务路径与原失败不同：run_once 在 7.685 秒返回 publication pending，父包装器记录 TimeoutError，不能记为已确认 provider_denied。关闭共 1.196 秒，内部原一秒诊断 drain 在关闭后 .141 秒开始；九条待处理事件逐项 receiver receipt／ACK 后于 +1.137 秒清空，两项 producer finish 尚未完成。父 finish 已准入事务跨过截止，于 +1.192 秒完成；子 producer 仍开放。只读存储确认全部十四条事件已送达。实际 retry-lock 等待约 .2 毫秒；观察到的主要成本为顺序 receiver 提交约 59–95 毫秒、Kernel 提交约 26–50 毫秒，未识别单一外部阻塞写入者。此结果说明该探测中的顺序持久化耗尽窗口，不足以解释原 provider_denied 现场或确定底层存储原因。追踪可能丢失、重排及扰动调度；原执行与关闭预算未延长，未补调用 close 掩盖错误。独立评估拒绝仅重排 guard／ACK 的修补，因为不会减少两次必要持久提交，反会扩大接口与锁风险。

候选 25 定向返工 `native25rework-route/report.json` 最终为 failed：九项检查中的八项通过，`shape_and_original_budget` 失败。六个真实执行、32 次实际模型轮次、准确产物／反馈绑定、三次相同返工重放（含关闭后）、普通 SDK admission／group／runtime effect、准确原生清理及成功 SDK finish 均已核对。只读逐项诊断确认六项持久 SDK envelope 与实际入口的有效截止均为 1793662638.84146，而冻结根及调用期限为 1793662638.8413858，晚约 74 微秒；没有放宽断言、改写报告或延长预算。Agent 原生／代理／工具另持原期限，因此不据此推断实际业务越期。普通根调用和控制器的 SDK command 只有相对超时，排队到实际入口后可能平移截止；正实施显式绝对期限修复，仍待当前安装包与原生复验。

`native25service-keyed/report.json` 整体 passed，六项检查通过，宿主关闭完成。SDK 为候选 25 site-packages，Linux x64／Python 3.12.3／OpenCode 1.18.32；四次实际调用对应四个独立有限 Run，原始上限各为 180 秒／4 Agent／16 模型轮次。X 实例的 A、B 会话按实例 FIFO 共享文件，原生会话及运行时目录独立；X/A 保持入口闸门时，X/B 没有 SDK command、原生操作或消耗，Y 实例已独立实际完成并产生隔离文件。重开后 X/A 稳定请求准确重放不新增执行／消耗，新请求续接原生会话并读取 X 原文件；普通 runtime effect、成功 SDK finish 与准确七字段清理均核对。这证明当前脚本的实例／会话／文件／重放切片；脚本当时未核对 SDK envelope 的绝对期限，不能替代上项预算失败的修复验收。固定实例报告同样没有该项断言。两份服务验证不证明提供商并发、对话回忆、独立 serve、进程崩溃或完整 G09/G10/G15/G16。

### 冻结 SDK 绝对期限修复（候选 26 之前的源码）

SDK `ExecutionCommandV2` 与 `Runtime.command` 新增可选正有限 Unix 时间 `deadline_at`，默认 null，未设置时不输出字段，保留旧命令编码。命令和绝对截止同次提交，SDK 入口从准确持久命令组合 `command:<execution_id>` 的 tool 约束；实际 handler 相对超时、父级及 managed Run 的更短限制仍取最小值。Agent 根、控制器和子命令携带准确冻结期限，子准入另派生自身截止；没有改 SDK 表结构或直接写 SDK 数据。独立审查检查线程／进程入口、父子及 managed 组合，未发现新命令路径阻塞项。

旧实验 Agent 未完成计划若已持相对超时命令，在 SDK Runtime 创建前拒绝；闭合计划中的旧命令也必须在调度器／宿主注册前核对准确公开 SDK 命令及明确终态，否则拒绝。保留原命令、回执、冻结期限及预算。已完成准确旧请求允许重放，普通旧 SDK 命令继续兼容。该保守策略不提供未完成旧候选 Agent Run 的原位升级。独立复审无此范围具体阻塞项。

新 Agent 实际 SDK 回归四项在 21.245 秒通过，含普通根调用、控制器、更短子调用、关闭重开无新增执行／消耗、旧 staged Agent/controller、已闭合 Agent 投影但 SDK 仍 queued 的拒绝，以及准确旧 SDK 终态的重放（`source-agent-absolute-deadline-final2.log`）。前一测试版在旧宿主关闭之前保存基线，close 自身正常投影意图使两个断言失败；改为完整关闭后的升级边界再冻结基线，原失败 `source-agent-absolute-deadline-reviewed.log` 保留。测试导入位置错误另保留于 `source-agent-absolute-deadline-final.log`。

受影响核心合同／预算／子准入源码首次 38 项因完整字段枚举未包含新可选字段而一项失败（`source-absolute-deadline-affected.log`）；更新字段合同后，同组 38 项在 11.611 秒通过（`source-absolute-deadline-affected-final.log`）。新增直接线程／真实进程绝对截止模块六项定向通过，含实际进程已过期不进入业务及成功入口回传准确原截止；该组由实现者独立运行，仍待候选安装复验。文档 570 个链接、四个 README 示例通过，无跳过（`docs-source-absolute-deadline.log`）。原核心 provider-child close 失败没有因此解决，整套旧 API 回归仍未通过。


## 候选 26：准确冻结期限的安装包复验

候选 26 完整白名单快照、wheel/sdist 和独立环境位于 `/tmp/agent-control-080-candidate26/`。它包含上述绝对期限与旧实验命令准入修复，不包含随后仍在审查的关闭诊断批量提交。无依赖安装的元数据、两个 optional extra、CLI 入口、许可证及 135 个 Python 源文件逐字节对照通过（`candidate26-consumer-metadata.log`）；没有新增 hash 检查。

具名受保护入口先断言 SDK 来自候选 site-packages，再加入快照测试目录，子进程不指向 checkout/src。合同、执行预算、子准入、直接线程／真实进程绝对期限、Agent 绝对期限、goal 和服务共 59 项安装包测试在 202.468 秒全部通过，无跳过（`candidate26-deadline-installed.log`）。这是定向回归，不是完整旧 API 或隔离消费者验收。

独立 YAML extra 环境离线安装同一 wheel 与 PyYAML 6.0.3，G01 passed（`candidate26-g01-yaml/acceptance.json`）。安装包 Agent 类型消费检查通过（`candidate26-agent-typing.log`，mypy 的 Python 3.10 目标不构成 Python 3.10 原生运行证明）。快照文档 570 个本地链接与四个 README 示例通过，无跳过（`docs-candidate26.log`）；双语 Wiki 本地导出 25 页至 `/tmp/agent-control-080-candidate26-wiki-draft/`（`candidate26-wiki-export.log`）。导出使用本地 `release/0.8.0` 引用，不表示远程 Wiki 或该分支已经发布。

`native26rework-route/report.json` 为 passed，九项检查全部通过，宿主关闭完成。一个原始 3600 秒／8 Agent／96 模型轮次有限 Run 内有六次实际入口、33 次计量模型轮次。准确选中成员的产物和反馈绑定、同逻辑 reviewer 实际消费、普通 SDK admission／group／runtime effect、准确原生清理、成功 SDK finish，以及三次稳定返工重放（含关闭后）均通过。新增检查逐项核对控制器及子执行自身 SDK envelope 与实际入口截止，均未超过准确冻结期限；没有放宽约 74 微秒的原断言。该场景是模型显式定向返工切片，不证明崩溃或完整 G05/G06。

`native26service-keyed/report.json` 为 passed，七项检查全部通过，宿主关闭完成。四次实际入口对应四个原始独立有限 SDK Run，各自 180 秒／4 Agent／16 模型轮次。X/A 占用入口闸门时 X/B 排队且无 SDK command、原生操作或消耗，Y 已独立完成；同实例 FIFO、真实共享文件及不同实例隔离、会话分离、重开准确重放零新增执行／消耗和新请求续接均通过。各请求的普通 runtime effect、成功 SDK finish、准确七字段原生清理及新增持久 SDK／实际入口原截止检查均通过。两项原生验证均使用候选 26 site-packages、Linux x64／Python 3.12.3／OpenCode 1.18.32 与用户授权本地反代；不宣称提供商并发、对话回忆、独立 serve 或崩溃恢复。原核心 provider-child 关闭失败仍未解决。关闭批量提交的首次独立审查发现 ACK 授权跨过原截止后仍可提交，以及直接 receiver 批量 API 缺少字节上限两个问题，正在修复；未纳入候选 26，亦未凭单元通过宣称原关闭错误解决。


### 候选 26 之后：关闭回执批量提交复审与原失败定向复验

关闭 drain 使用同 execution 有序前缀，默认最多八条及 262144 编码后 payload 字节；合法单条大记录可推进至 1048576 字节。receiver 与 Kernel ACK 分别一次事务，仍保留逐事件准确证明、managed 准入／precommit 验证和覆盖 receiver commit 的 retirement guard，不宣称跨存储原子。单条与大记录同样使用有界批量路径；普通后台及优先级单条路径保留原合同。新 receiver 批量 API 拒绝循环、超过 64 层容器及超过相应字节上限数量的 JSON 值；不支持的事实保留待处理，不截断或删除。

首次独立审查发现授权回调越期后仍可 ACK、直接 receiver 输入缺少字节上限；第二轮发现单条回退绕过新期限检查。均已修复，最终复审在声明范围内无具体未解决阻塞项。原期限是新存储／授权准入边界；已准入事务回滚 ACK 后，只维护逻辑时钟水位的必要清理可以结束，符合既有关闭合同，不取得新窗口或新的 ACK 授权。未新增存储 schema 或关闭超时。实现者 25 项定向测试在 13.037 秒通过，覆盖真实 SQL 批次提交次数、内部拒绝回滚、初始及 precommit 授权跨截止、单条和大记录、receiver／ACK commit 后丢失响应的准确重放与本地所有权、时钟回退不复活授权。该结果不是原失败或原生模型验收。

原 provider-child 测试源码定向复验在 6.854 秒通过（`provider-child-batch-source-original2.log`），线程与真实进程均准确保留原始父子 `provider_denied`，原 parent 12 秒／child 5 秒和 close drain 一秒窗口未改，关闭返回成功。现场分别位于 `/tmp/sdk-provider-child-failure-thread-sa76wla8/` 与 `/tmp/sdk-provider-child-failure-process-cm_lh70a/`。最初入口漏加 tests 包搜索根目录，导入失败日志 `provider-child-batch-source-original.log` 保留；之后只修复验证入口，不改产品断言或预算。原 99 项聚合失败继续保留，受影响组和新安装包仍须复验，不凭这一次通过宣布完整回归解决。

G12 的三个原生验证器已补充技术重试耗尽、验证器明确阻塞／异常的准确普通 effect／cleanup／failed Run finish 和稳定失败重放；请求发出后崩溃场景增加原请求重放及原期限内两秒观察，核对准确身份／effect／admission／用量和零新增原请求发送。独立复审无此范围具体阻塞项，当前只有编译检查，尚未用新安装包执行，不将 G12 升级为 passed。


## 候选 27：关闭批量提交与 G12 分类复验

完整白名单快照、wheel/sdist、无依赖和 YAML extra 环境为 `/tmp/agent-control-080-candidate27/`。包含已复审的关闭批量提交、准确绝对期限和三个 G12 验证器增强，不含其后的进程清理顺序与角色权限撤销修复。元数据、extra、CLI、许可证和 135 个 Python 源文件逐字节对照通过；G01 YAML/Python/defaults/refusal、Agent 类型消费、572 个文档链接与四个 README 示例通过，无跳过。双语 Wiki 本地导出 25 页；均未发布远程。日志为 `candidate27-consumer-metadata.log`、`candidate27-agent-typing.log`、`docs-candidate27.log`、`candidate27-wiki-export.log`，G01 索引为 `candidate27-g01-yaml/acceptance.json`，位于 `/tmp/agent-control-080-evidence/`。

原受影响 99 项源码回归在 113.997 秒通过（`source-batch-close-affected.log`）；候选 27 安装包加入 12 项批量提交测试后，111 项在 141.260 秒有两项失败（`candidate27-close-affected-installed.log`），不能将单次或源码通过代替该组验收。其一保留了业务返回，却在预算重采样前尚未先停止后代，最终超时；现场 `/tmp/sdk-orphan-final-flush-hf0y4g2f/`。其二真实进程 provider-child 尚在入口 pending，原子调用期限已到，返回 `BudgetClockUnknownError`，未执行到提供商拒绝；现场 `/tmp/sdk-provider-child-failure-process-k5kwxi7y/`。该次没有报告关闭错误，但不能据此声明原提供商错误传播路径通过。原期限与原失败均保留。

`native27-retries-classification/report.json` passed，12 项检查全部通过、宿主关闭完成。一次真实 OpenCode 调用从准确已证实未启动的瞬时错误重试到成功；另一独立原调用耗尽两次预启动尝试，保存确定失败，普通未恢复 runtime effect 已提交，SDK execution 成功承载业务失败，有限 Run failed finish、零模型计费及稳定失败重放成立。`native27-goal-classification/acceptance.json` 的 G08 passed：原会话 continue → passed、明确 blocked 与验证器异常均核对实际入口、普通 effect、准确清理、原预算、失败 Run finish、稳定查询及下游不执行。两项均为 Linux x64／Python 3.12.3／OpenCode 1.18.32，通过授权本地反代，不覆盖其他平台。

`native27-unknown-classification/report.json` 的 C failed：准确原生清理、原身份／期限、未知业务效果、排队零发送、无关会话完成及宿主重启均成立，但要求原期限内的两秒稳定重放观察没有剩余窗口，`unknown_replay_unchanged` 为 false；未放宽预算，也未把该缺失改记 passed。SDK stale lease／验证器等待顺序仍在检查。完整 G12 保持未通过。

### 候选 27 后的源码修复与新增 G16 证据

进程 supervisor 已改为先验证原 `worker_returned` 完成时间，再实际停止后代，之后进行原 SDK 预算重采样及最终成功授权；没有省略原期限、最终清理或结果验证。真实 Linux 进程回归持有独立采样标记，确认停止发生在采样等待前，释放原采样后返回准确成功与 tree_reaped。两项定向测试 6.347 秒通过；最终增强断言单项 2.678 秒通过，独立复核未发现该范围阻塞项。另两个时钟／deadline 清理检查通过；独立 inherited-parent 检查在原三秒维护窗口内的最后读取失败，保留 `/tmp/sdk-inherited-parent-deadline-yal1lkat/`，不能宣称整组通过。现场显示最后约六毫秒时 settlement 线程正持控制锁提交 ACK；没有证据证明长期死锁或支持扩展窗口。

持久角色调用权撤销使用新增 Agent-owned 决定表，默认 allowed／generation 0，保留按代次幂等回执、准确委托子树、取消与未知原因。基础集成／存储／认证 CLI 共 11 项通过（27.295 秒，`source-permissions-integration2.log`），未冒充原生模型验收。首次两项错误保留于 `source-permissions-integration.log`：工具测试使用了错误 helper 参数；未开始且被撤销请求的 budget ledger 尚未初始化。已修复测试调用并确保仅初始化原预算、不增加消耗。独立审查另发现已完成子调用重放及预检／撤销竞态，正在修复，不声明撤销整体完成。追加 planless Agent 根行防御性撤销，五项实际 SQLite 存储测试通过；未迁移或改写旧 SDK 命令。

新增 `tests/test_agents_host_competition.py` 使用两个真实 spawn 进程与合成适配器，通过一项 6.659 秒检查：A 保持活动调用时 B 在打开 AgentStore／SDK 前拒绝，A descriptor、身份与行为保持；A 完整关闭后新的 B 取得状态目录并原样重放，零新增适配器执行。此为 Linux 本地宿主独占验证，不是 OpenCode 或其他平台验收。


候选 28 构建前，原 99 项组加入 12 项批量提交与一项真实进程采样等待回归，共 112 项源码测试在 111.042 秒通过（`source-orphan-close-affected-final.log`），原 orphan/provider-child 两路径均在各自原期限内通过，未放宽关闭窗口。此前候选 27 的两项失败与后续独立 inherited-parent 失败仍保留，不能据此声称完整旧 API 已通过。权限源码 17 项整合测试在 86.148 秒通过（`source-permissions-reviewed-suite.log`），该组早于后续 claimed-before-stage 修复；其后任务／服务原样重开释放的两子例、冲突原生记录拒绝释放、未知子接纳重开屏障另有定向通过及独立复核，仍需同一新候选整组验证。公共权限 API 和 client 类型消费检查通过（`source-permissions-typing-final.log`）。认证 HTTP 撤销拒绝使用 403／`agent_permissions_revoked`；client 保留为 `HostError` 消息，不伪装提供商错误。

候选 28 的 wheel/sdist 与白名单快照位于 `/tmp/agent-control-080-candidate28/`。无依赖安装的元数据及 136 个 Python 源文件逐字节对照通过（`candidate28-consumer-metadata.log`）；另建 YAML 环境离线安装同一 wheel 和 PyYAML 6.0.3，G01 为 passed（`candidate28-g01-yaml/acceptance.json`）。安装包公共 Agent 类型消费检查通过（`candidate28-agent-typing.log`），不代表 Python 3.10 原生运行。权限、协调、收件箱、认证宿主及双宿主竞争共 19 项在 88.015 秒通过（`candidate28-permissions-installed.log`），覆盖最终 claimed-before-stage 修复与 HTTP 403；使用实际 SDK、合成适配器和真实本地宿主进程，不替代 OpenCode 原生撤销验收。线程等待诊断保留，测试没有因诊断快照而扩大原期限。双语 Wiki 本地导出 25 页至 `/tmp/agent-control-080-candidate28-wiki-draft/`，未发布远程。

缺失清理回执的新私有原生验证器及 Linux 子进程监督器尚未纳入候选 28。监督器的真实脱离进程组子孙、持续观察失败和控制端关闭输出管道自检通过，并经独立只读复审；观察或报告异常进入保留所有权的清理循环，只有 ECHILD 解除责任，超过原清理窗口后即便随后清理成功也保留失败。它不保证监督器本身遭 SIGKILL 后的清理，不是业务恢复或原生验收通过证据。新验证器仍待独立复审后的真实执行。

候选 28 的受影响核心 112 项在 112.686 秒结束，110 通过、两项失败（`candidate28-close-affected-installed.log`）。两项失败均依赖 Linux `sitecustomize` 进程钩子；本轮以 `-I` 运行，子监督器继承隔离标志，钩子未加载，故没有 stop/release/returned_packet 证据。原 orphan 证据 `/tmp/sdk-orphan-final-flush-odrihqg1/evidence.json` 保留业务按时返回、最终 timed_out 和实际 tree_reaped，不据此把本轮标为通过。钩子原先还优先加入快照 src，无法证明安装包子进程来源；已改为当前实际导入包的父目录，记录并断言子进程完整包路径，隔离父解释器明确失败。原期限未改；候选 29 从 `/tmp` 使用来源已核对的非隔离测试解释器重验，不把测试钩子失效当作产品成功证据。

候选 28 真实 OpenCode 权限撤销验证通过全部 14 项检查（`native28-permissions/report.json`）：原生入口和 SDK 执行代次一致；真实提供商请求写出后撤销，原结果保持 unknown；准确原生清理回执匹配；同会话排队请求无 SDK 命令、效果、原生入口、模型发送或计量；无关角色普通成功。认证宿主排空并确认 AgentApp.close 返回后重启，服务恢复接受请求而权限仍拒绝，新请求明确报权限撤销，稳定原请求在原期限内观察不重发。显式恢复后新会话成功，旧 unknown 和原预算保持；最后关闭不产生新入口或发送。两次宿主退出均明确记为 recovery_required，不宣称业务已恢复。测试专用发送屏障不测量生产取消时延，也不证明提供商远程取消。

候选 29 新增已复审缺失回执验证器、监督器及安装包进程钩子；136 个产品 Python 文件与候选 28 逐字节相同，不包含新的产品修复。新制品仍需完成相应验证。完整核心测试另备只用于构建的测试解释器，使用现有 setuptools 68.1.2 和 wheel 0.42.0，防止把缺构建工具误记为 SDK 缺陷；无依赖消费者环境单独保留。


### 候选 29 核心与原生故障复验

候选 29 安装包受影响核心回归 112 项在 134.189 秒通过（`candidate29-close-affected-installed.log`），覆盖生命周期交付、取消、结算、宿主进程树、诊断关闭及期限。进程钩子核对实际子进程从同一候选 site-packages 导入；没有把候选 28 的失败改记为成功。完整核心套件仍在执行，已观察到子调用并发用例的 `BudgetClockUnknownError`；原证据保留在 `/tmp/sdk-child-concurrency-failure-1fpq90ze/evidence.json`，正在追踪原始采样路径。

候选 29 元数据与源文件逐字节对照通过 136 项，G01 YAML／Python／CLI 与双语默认值对照通过，六个类型消费文件以 Python 3.10 目标检查通过（不是原生 Python 3.10 执行）。文档检查通过 572 个链接、4 个可运行示例，跳过 0。分别见 `candidate29-consumer-metadata.log`、`candidate29-g01-yaml/acceptance.json`、`candidate29-all-typing.log` 和 `docs-candidate29.log`。

候选 28 原生分类 C 场景通过 16 项检查（`native28-unknown-classification/report.json`）：在原期限前核对准确未知请求稳定重放，在原 SDK 租约自然到期后分别确认隔离。原请求只发送一次，同会话后继无执行、发送或计量；无关会话实际成功，原预算未延长。该次只运行 C，不能覆盖其他分类场景。

候选 29 缺失可信清理回执场景通过 9 项检查（`native29-cleanup-unknown/report.json`）：真实 guard 清理后由测试钩子抑制回执写入，真实宿主在提供商发送后崩溃。Linux 外层 subreaper 保持进程树所有权并确认清理，未伪造认证回执，也未写 SDK 存储。两次宿主重启后原未知效果、准确执行／租约／代次、原预算和资源预留保持；同会话后继没有 SDK 命令、原生操作、模型发送或消耗，无关会话真实 OpenCode 成功。外层物理清理不替代 SDK 可信回执或解决业务未知。环境均为 Linux x64／Python 3.12.3／OpenCode 1.18.32，非平台矩阵验收。

### 候选 29 之后的启动与 Windows 源码

Windows 宿主锁与 Job guard 已独立审查，但尚未在 Windows 执行；Windows 私有空策略工作区可构造，文件工具仍失败关闭，不宣称 Windows OpenCode 已验收。

共享启动握手采用单一期限、部分 I/O 和取消观察。启动只读取消查询不再申请 Agent 写事务或采样 Kernel，SQLite 锁等待上限为 0.05 秒，错误失败关闭。实际启动仍须通过完整 SDK 执行、权限、租约与 effect 授权；这些参数不承诺整个启动／取消返回时延。真实 SQLite 启动观察 3 项和真实 socket 握手 9 项定向通过；宿主锁 Linux 3 项通过，Windows 专用项未执行。源码受影响套件首次运行 43 项，两个 prelaunch 测试错误、5 个 Windows 跳过，其余通过（`source-platform-startup-affected.log`）。错误为提前取取消回调，已修正为实际握手时解析；定向 prelaunch 3 项复验通过（`source-prelaunch-lazy-callback.log`），独立复审未发现阻塞项。


### 子调用采样竞争修复与下一候选

候选 29 完整核心回归在父 handler 顺序预提交第三个子调用时，遇到未发布的预算时钟 sampling 标记；尚未进入并发 wait。原错误保持未知且子提交事务回滚。它与先前候选 19 的 child0 控制锁超时、子任务未重叠是两个不同现场，不能据此声称旧故障同因。

当前 Runtime.submit_child／adopt_child 仅对准确 `budget_clock_sample_unresolved:sampling` 等待后重试，每次退出生命周期及 Kernel 锁后等待，再检查注册表、关闭状态、原父 lease／fence、托管权限和预算。重试只投影调用方原 checkpoint 的原生已用时，不重新采样权威 wall clock，不清除／接管其他采样者，不延长原工作或显式准入截止；持续未知在截止仍报原未知。首次成功及已准入操作可稍后完成的既有语义保留。独立审查未发现此范围具体阻塞项。

原并发 wait/run、子预算接纳／声明及期限相关 18 项源码测试在 20.479 秒通过（`source-child-sampling-affected.log`）。补强后的五项真实 Kernel／分类测试在 3.396 秒通过（`source-child-sampling-strengthened.log`），对 submit 和 adopt 分别核对活跃采样发布后接纳、从测试开始后才派生的原工作 cutoff、显式 timeout、等待中取消父任务，以及其他未知错误不重试。原失败断言的诊断格式也改为完整 snapshot，避免 result 缺失掩盖原 handler 错误。未覆盖运行时关闭竞争或注入回滚失败，不据此报告完整回归通过。

POSIX 工作区锁的 fcntl 导入移入实际加锁方法，使 Windows 导入模块可以到达原有不支持后端拒绝；Linux 工作区与文件测试 13 项在 2.512 秒通过（`source-workspace-lazy-fcntl.log`）。Windows 专用路径与构造负例尚未运行。候选 30 正在准备，以上源码变化尚不能借候选 29 的历史原生证据报告当前制品验收。


### 候选 30 当前验证

候选 30 完整白名单快照、wheel/sdist、无依赖与 YAML 环境位于 `/tmp/agent-control-080-candidate30/`；139 个产品 Python 文件元数据／逐字节源文件对照通过。受影响安装包回归运行 77 项，71 项通过，6 项 Windows 专用检查跳过，耗时 71.657 秒（`candidate30-affected-installed.log`）。包含真实子并发、原预算、宿主锁、启动取消、socket 握手、适配器、关闭、权限及工作区。Agent 完整回归仍在执行，不能报告完整通过。

`native30-basic/acceptance.json` 的 G02 passed：候选 30 site-packages／Linux x64／Python 3.12.3／OpenCode 1.18.32，真实文件产物 `SDK_AGENT_NATIVE_OK`、5 次模型推理计量、成功 SDK Run，以及匹配 execution／attempt／fence 的准确认证原生清理均核对。配置 G01、六个 Python 3.10 目标类型消费、572 个文档链接及四个 README 实例通过，文档跳过 0；双语 Wiki 本地导出 25 页，未发布。

候选 30 原 G10 脚本报告 passed（`native30-foreground/acceptance.json`），实际覆盖独立 CLI serve、客户端退出后继续接收、同会话重开、提交结果后故障与排队恢复，以及跨 Run 排队取消。独立审查确认旧脚本仅对照 Agent 截止和用量下界，缺少准确冻结预算／SDK 绝对期限／普通 effect／finish 与清理的一致性，不将此旧报告当作完整 G10 当前制品验收，不改写原报告。

增强 G10 验证器完成独立复审后，使用同一候选 30 安装包在原生 Linux x64／Python 3.12.3／OpenCode 1.18.32 重新执行，22 项检查全部通过（`native30-foreground-exact/acceptance.json`、`G10.json`）。准确核对七个成功请求和一个排队取消请求、原 600 秒／8 次 Agent／12 次模型轮次预算、SDK 命令与约束截止、故障前 execution／lease／attempt／fence、普通 effect 与 finish 以及匹配身份的认证原生清理；排队取消无命令、效果、原生操作或消耗。恢复宿主实际退出后才进行只读前置检查和公共 SDK 对照，不延长原预算，不改写 SDK 存储。验证器来自独立审阅脚本目录，产品导入仍为候选 30 site-packages；此证据不代表 Windows 或其他 Python 版本通过。

平台可移植预启动故障夹具另修为仅替换适配器自己的 socket 绑定，按平台选择 Linux socketpair 或 Windows listener，不更改全局网络模块。源码定向 14 项中 13 项通过，原始两秒截止用例未抵达 abort 边界，保持 failed（`prelaunch-portability-tests.log`）。一次原预算不变的单例诊断同样 failed：adapter 调用 0、无 effect／native operation、模型消耗 0，SDK entry 在原截止后被拒绝，未证明过期后重试（`/tmp/sdk-prelaunch-deadline-failure-oaxnlc1m/evidence.json`、`prelaunch-deadline-diagnostic.log`）。接纳耗时原因尚未确认，并发 I/O 负载只是待验证假设；没有延长预算或放宽原断言。候选 30 快照不包含这些后续夹具变化。

上述平台故障夹具及失败诊断经独立只读复审未发现阻塞项。当前候选 30 的真实 OpenCode 预启动技术重试分类在原 150 秒／4 次 Agent／8 次模型轮次预算下通过 12 项检查（`native30-retries-reviewed/report.json`）：第一次控制通道创建失败有准确 not_launched 回执和零模型消耗，第二次沿用同一 invocation／effect／lease／attempt／fence、完整请求、工作目录和原预算，更新工具授权后真实成功并准确清理；另一个独立原始请求耗尽技术重试后确定失败、不重放。它只证明 Popen 前的安全技术重试，不证明已发送模型请求可重试，也不替代两秒截止用例。

候选 30 完整 Agent 回归暴露旧协调关闭夹具缺少 store.get／真实 BudgetEnvelope，以及模型配置夹具仍模拟已替换的旧 guard 读取接口。仅修复这些测试夹具，保留原竞争闸门、断言和期限；来源已核对的候选 30 安装包下，协调关闭 4 项、模型配置／推理参数 7 项定向通过。模型配置夹具的 Windows 连接被模拟，不是原生 Windows 验证。旧快照全量失败记录保留，不能据定向通过声明完整回归成功。

新宿主竞争验证器经过独立复审，并在候选 30 原生 Linux x64 安装环境通过五项检查（`native30-host-competition/report.json`）。两个独立宿主进程争用同一状态目录，竞争者准确锁拒绝且没有派发；竞争者退出后、放行原宿主前，再确认原 performing effect、execution／lease／attempt／fence 和仍有效租约。原调用在冻结 120 秒／4 次 Agent／16 次模型轮次预算中成功，只有一次 adapter 进入，2 次真实提供商发送计为 2 次模型轮次；核对 SDK 原约束、普通 finish 和准确认证清理。停止服务并实际退出后，新宿主保持停止接纳，只允许原请求稳定重放，无新进入或发送；三个宿主监督器均正常退出、无强制信号、清理确认。仅证明该 Linux 闸门窗口，不声称远端效果恰好一次，也不代表完整 G16 或其他平台通过。

新排队过期验证器经独立复审，并在候选 30 原生 Linux x64 安装环境通过六项检查（`native30-queue-expiry/report.json`）。测试闸门只安排 claim 的观察窗口，过期终态由真实 ServiceRegistry.claim 和正常已启动宿主推进；不直接驱动私有 pump、不改 SDK 存储或预算。同键原排队请求保持原 120 秒／8 次 Agent／16 次模型轮次预算，原期限到达后取消，无 SDK 命令、effect、原生操作或计量，finish 准确归属原 Run；不同会话真实 OpenCode 成功，SDK 截止、约束和认证清理核对。通过公共生命周期干净关闭并在同一 OS 进程重新构造 AgentApp 后，原请求稳定重放仍过期，无新进入或发送。该检查不证明 OS 进程重启、生产排队时延或父子取消；OS 宿主重启另见 G10。

Python 次版本缺口可在本机继续验证：通过临时 uv 0.13.6 环境将 Astral python-build-standalone 的 CPython 3.10.22、3.11.18、3.13.18 安装至 `/tmp/agent-control-080-python-runtimes/`，未改系统解释器或 PATH。三个独立环境分别安装同一候选 30 wheel 和 PyYAML 6.0.3，实际版本、SQLite、SSL 与 SDK 导入路径见 `candidate30-python-runtime-environments.json`，安装日志见 `python-runtimes-install.log`。三个真实解释器的配置 G01 均 passed（`candidate30-py310-g01`、`candidate30-py311-g01`、`candidate30-py313-g01`）；不是类型检查模拟。尚不据此报告完整版本回归或原生平台矩阵通过，Windows／ARM 主机仍未获得。

候选 30 未知结果原生分类 C 通过 16 项检查（`native30-unknown-classification/report.json`，A／B／D 未运行）。真实提供商发送后宿主崩溃，原期限前核对稳定请求重放没有新增发送；随后等待原 SDK 租约自然到期，再核对准确 invocation／Run／effect／execution／lease／attempt／fence、原截止、认证清理、unknown 结果和会话隔离。同键排队后继没有执行或发送，无关会话真实成功；原未知调用只有一次提供商发送，没有不明归属发送。没有提前清除租约、改写 SDK 表或延长预算；该 C 场景不证明其他崩溃窗口。

完整 Agent 回归中的显式返工用例另报 error，定向运行复现 root recovery_required，并保留准确执行／effect 与调用前状态（`candidate30-rework-route-single-escalated.log`、`candidate30-rework-route-retained.log`，`/tmp/sdk-rework-route-failure-5hd3v1ot/evidence.json`）。源码确认测试替换的 preflight_admit 回调未接受实现传入的 check_permissions 关键字；仅修正回调参数透传后，同一用例在候选 30 安装包下 92.123 秒通过，原 120 秒 Run 和 115 秒等待未变（`candidate30-rework-route-fixture-fixed.log`）。测试保留全部返工、冲突、关闭后重放及 effect revision 断言，增加失败时只读诊断，不改产品；未据此将仍运行的原全量报告标为通过。首次沙箱拒绝套接字的运行另存 `candidate30-rework-route-single.log`，不视为原故障原因。


候选 30 同一 wheel 在真实 CPython 3.10.22、3.11.18、3.13.18 上的 G02 均 passed（`native30-py310-basic`、`native30-py311-basic`、`native30-py313-basic`），三项串行执行，不延长各自原 120 秒预算。实际命令、起止时间与退出码见 `candidate30-native-python-matrix.json`；每个目录保留实际文件产物、SDK 成功和准确认证清理核对。三个环境各自对照全部 139 个安装包产品文件并在对应解释器编译通过（`candidate30-python-runtime-provenance.json`）。这些是 Linux x64 上的配置、代码装载与真实模型基线，不是完整版本或 Windows／ARM 矩阵通过。

候选 30 完整 Agent 套件在 `SupervisionIntegrationTests.test_artifact_commit_supersedes_incident_and_monitor_retries` 期间以 139 退出；原日志 `candidate30-agents-suite.log` 保留。日志在周期性 faulthandler 栈输出中途截断，没有提供致错原生函数、地址或明确 fatal-signal 回溯。独立检查未能据此证明 SQLite close／commit 竞争；正在保持原闸门、断言和预算进行单例隔离诊断。此前已记录的夹具失败及未运行到的测试均不能记为通过。


修正后的协调关闭／模型配置夹具已补齐可保留证据：同一候选 30 安装包运行 11 项、跳过 0，0.085 秒通过（`candidate30-corrected-fixtures.log`）。单独监督用例在原闸门及期限下 23.678 秒通过（`candidate30-supervision-isolated-loopback-probe.log`）；首次受沙箱 loopback 限制的跳过另存 `candidate30-supervision-isolated-probe.log`。本机 core limit 为 0、gdb 不可用，没有取得原段错误的 core；该单例通过不解释或消除全量崩溃。


候选 30 的 G07／G08／G11 原生组合全部 passed（`native30-coordination-goal-knowledge/acceptance.json`）。G07 实际 call、send、wait 和稳定重放共 3 次 Agent、17 次模型轮次，最终产物精确为 `CALL_NATIVE|SEND_NATIVE`；保留 `agent_wait_cycle`、`agent_permission_denied`，controller 原 lease／约束与接纳 effect 一致。G08 同一 invocation／session 产物从 `DRAFT_NATIVE` 到 `GOAL_NATIVE_FIXED`、验证从 continue 到 passed；blocked 和异常负例均核对普通 SDK failed 及准确 effect／finish／清理证据。G11 活动请求使用旧配置，新请求使用新配置，知识 v1／v2 实际读取、越权写入拒绝和旧版本冲突不覆盖均通过。分别保留原 360 秒、240 秒、240 秒请求预算；Linux x64／Python 3.12.3／OpenCode 1.18.32，不代表完整平台矩阵。


解释器诊断也保留为未证实假设：[CPython #123967](https://github.com/python/cpython/issues/123967) 记录顶层 trampoline frame 的 faulthandler 崩溃及 3.12 回移；[#158200](https://github.com/python/cpython/issues/158200) 记录 main 调试构建的 watchdog 元数据竞争，不能据此推定本机 3.12 同因。本机实际 Ubuntu 包为 `3.12.3-1ubuntu0.17`，仅凭版本／changelog 不能确认补丁有无。一次不导入 SDK 的一秒代码 churn 探针正常退出（`candidate30-cpython-faulthandler-repro.log`），没有复现原崩溃。后续标准安装套件启用致命信号回溯；临时直接运行器默认不启用额外的周期性跨线程栈转储，并即时保留断言／异常回溯。此为诊断配置差异，不是 SDK 修复，不将原失败改记通过；测试及业务期限不变。


候选 30 四个核心崩溃窗口的当前安装包证据已补齐：A 通过 8 项（`native30-dispatch-window/report.json`），B 通过 8 项、D 通过 11 项（`native30-commit-windows/report.json`），C 另见本轮 16 项分类证据。A 保持同 invocation／SDK execution、原期限和一次 Agent 计量，准确原生操作与可信清理匹配。B 在根意图持久化、尚无 SDK 提交时崩溃，恢复原根和 Run 后真实成功。D 在 producer 已消费、新 consumer 意图已保存而尚未提交时崩溃，恢复保留原 consumer 身份及绑定，真实消费 `COMMIT_PRODUCER`，producer 不重跑。A／B／D 分别使用原始独立 300 秒请求预算和 600 秒场景界限，命令／起止时间见 `candidate30-remaining-crash-windows.json`；宿主测试 teardown 的信号及未知清理单独记录，不冒充业务结果或认证清理。此为 Linux x64／Python 3.12.3 核心窗口证据，不覆盖任意崩溃点。


候选 29 嵌套安装套件在原 2700 秒上限处超时，停在 managed-stall 用例，原命令、stdout／stderr 位于 `/tmp/sdk-observability-consumer-nokvgefc/installed-suite/`。未获得完整总结，不将已输出的 ok 行当作全量成功。其四个 child completion／receipt 模块的九个失败方法在外层同候选先前均通过，四个源码文件也无版本差异；这与负载敏感假设相容，但缺少原异常回溯，不能确定同因。外层已知失败的旧制品回归随后由准确 PID／启动身份校验后 SIGINT 中断，退出 130（`candidate29-core-interruption.json`）；不是完成或通过，不再与当前全量争用资源。

原两秒预启动截止用例在候选 30 安装包下以全部原断言通过，耗时 4.107 秒（`candidate30-original-deadline-probe.log`），未增加 start／warmup、预算、等待或改动故障边界；此前失败仍保留，原因不据此视为已解决。三个新 Python 次版本各自的配置／Agent-owned 存储／调用组／准入回归 35 项全部通过，跳过 0（`candidate30-py310-config-store.log`、`candidate30-py311-config-store.log`、`candidate30-py313-config-store.log`）；仍不是完整版本矩阵。

无依赖消费者中的 CLI provider 权限用例原先尚未加载可选 PyYAML 即期待后续 PermissionError，现明确仅在 YAML extra 已安装时执行；原 POSIX 限制及所有隐私／无泄漏断言保留，独立审查无阻塞。候选 30 YAML 环境该单例 0.023 秒通过；无 YAML 环境明确 skipped 1（`candidate30-cli-provider-permissions-yaml.log`、`candidate30-cli-provider-permissions-no-yaml.log`），不算该分支通过，也不将 Windows／ARM 缺项改标不适用。

候选 31 是包含后续验证器／夹具／文档的完整白名单快照。其 wheel 元数据及 139 个产品文件逐字节对照通过（`candidate31-consumer-metadata.log`），139 个产品 Python 文件与候选 30 及当前源码一致（`candidate31-product-source-parity.json`）；这证明产品代码一致，不冒充新的模型执行。两项旧生命周期 close 用例在候选 31 定向复现失败：预期未持久化异常未抛出、预期一次 close 失败实际为零（`candidate31-journal-close-diagnostic.log`）。确认测试只注入单条写故障，close 已改走批量写；仅将相同 outage 扩至包含原目标 phase 的原子 batch，原期限、身份、恢复开关和全部断言未变。两项随后 3.959 秒通过（`candidate31-journal-close-fixture-repair.log`），产品未改；主执行独立核对了 batch 事务路径和其余单条故障夹具，不将旧失败改记通过。

嵌套全量运行器现对错误、断言失败和失败子例即时输出并 flush 回溯，保持相同 discover／排除项、成功与跳过语义和原 2700 秒期限，经独立审查无阻塞；尚未用该修订完成全量。候选 31 不包含最后两项 close 夹具及此运行器修订，下一快照保留它们。


### 候选 32：单套完整隔离安装回归

候选 32 位于 `/tmp/agent-control-080-candidate32/`，包含两项 close 批量故障夹具和即时回溯运行器修订；wheel/sdist、无依赖环境及 YAML 环境均已构建，元数据／139 个安装产品文件对照通过（`candidate32-consumer-metadata.log`），G01 YAML 集成通过（`candidate32-g01-yaml/acceptance.json`）。候选 30／31／32／当前源码的 139 个产品 Python 文件逐字节一致，见 `candidate32-product-source-parity.json`；不以代码一致冒充新的原生执行。

2026-11-03 00:36:35 UTC 启动一套完整回归（`candidate32-complete-installed-regression.log`）：安装解释器先核对导入来源，运行隔离消费者和打包模块；消费者从 sdist 重建 wheel 并安装新环境，运行全部其余测试，再运行重启消费者。内层保留原 2700 秒期限，标准 fatal faulthandler 和即时失败回溯开启；没有并行启动另一套完整回归或真实模型批次。本轮现已结束：内层在原 2700 秒上限处超时，外层 5 项耗时 2763.739 秒、失败 1 项；不能报告完整通过。

后续只读文档审查确认指南及双语 Wiki 的三份完整默认注册表与代码一致，未发现所审范围 P1／P2。修复一处 P3 使用说明：三份文档现展示公开 `dispatcher_sdk.agents.opencode.OpenCodeAdapter` 导入及 `AgentApp(..., adapter=adapter)` 接线。文档和嵌套预算验证器的后续补强不在候选 32 快照中，最终源码制品仍需同步。


候选 32 G13 合同／拒绝检查 passed（`candidate32-g13-contract-bundle-layout/acceptance.json`）：公开 tools 保证为 sdk_file_tools_only；strict 在保存请求或进入运行时前拒绝，三类非法能力报告被拒绝，运行时进入次数 0。原生强隔离后端未提供、真实隔离未验收。首次脚本副本置于 `/tmp/<bundle>/verify_agent_control.py`，其来源保护按父目录 `/tmp` 判定，误将 `/tmp` 下安装包视为脚本源码而拒绝；原 failed 证据保留于 `candidate32-g13-contract/`。已改为独立 `<bundle>/scripts/` 结构，不更改来源保护、产品或断言；本检查不调用模型。

嵌套预算验证器现新增公开 SDK root／controller／child 准确命令、原绝对截止、可信 BudgetEnvelope、父执行代次、冻结预算，以及子调用普通 effect 元数据断言；执行前必须核对 `--expected-site-packages` 和开发版本。两轮独立只读复审未发现所审改动阻塞项，语法编译通过；未改变原 240 秒场景预算和等待。尚未真实执行这些新断言，不能据此标记 G15 通过。其与其余尚缺 Linux 场景的冻结脚本及串行命令清单为 `candidate32-remaining-native-plan-v2.json`，当前只准备，尚未运行；首版计划及目录布局错误均保留。


候选 32 后续环境已备齐：`candidate32-python-regression-environments.json` 记录真实 CPython 3.10.22／3.11.18／3.13.18、Linux x64、各自精确 site-packages、SQLite 3.53.1、PyYAML 6.0.3 及与当前构建一致的 setuptools 68.1.2／wheel 0.42.0。均在新的 `/tmp/agent-control-080-candidate32-py<minor>-tests/` 中安装候选 32，不修改历史原生环境或系统解释器；当前仅准备，完整版本回归未运行。

补充全文件对照见 `candidate32-full-product-test-parity.json`：除 139 个 Python 文件外，py.typed 和 Kernel README 也一致，共 141 个产品文件；候选 32 的 268 个测试文件与当前源码一致。此为直接字节比较，不作 hash 检查，不证明新的执行或平台验收。


候选 32 完整隔离消费者的前置五个公开观测场景 success／failure／silence／cleanup／budget 已分别保存 passed:true；索引 `candidate32-public-observability-consumers.json` 指向 `/tmp/sdk-observability-consumer-g0t9l_h8/` 的原始证据。此为部分旧 API 消费证据，不代表仍在执行的完整内层套件或随后重启消费者通过。managed-stall 示例另已输出业务 succeeded 和监督观察结果，原 stdout 保留，不用于替代 G17 完整验收。


候选 32 完整回归原始内层命令、stdout 和 stderr 保留在 `/tmp/sdk-observability-consumer-g0t9l_h8/installed-suite/`，外层为 `candidate32-complete-installed-regression.log`。内层停在 script output recovery，未产生最终总结；即时失败包括 context journal attachment、native controller crash/restart、输出压力取消、supervisor budget floor、large handoff retry 和 nested split pause。`test_parent_only_clock` 实际通过，不能将邻近的 supervisor budget floor 失败归入该模块。当前证据初步确认独立观测可能在 driver_close 尚未交付时过早报告 complete；崩溃夹具也错误地把原生清理返回等同日志交付完成。其余原因待准确状态探针确认，不以负载或一次孤立通过解释失败；未出现原段错误也不证明其原因已解决。剩余原生批次和完整 Python 矩阵保持未运行，先处理已知缺陷。


候选 32 失败的定向诊断及修复：原大结果重试用例在安装包下复现，业务及结算成功后仍有 handler_outcome／driver_close 等异步日志等待 ACK（`candidate32-large-retry-diagnostic.json`、`.log`）。批量交付单例探针通过，但完整模块仍失败（`candidate32-large-retry-final-batch-probe.*`），因此未将批量切换当成产品修复。测试改为在原 30 秒执行期限剩余内、最多 3 秒，真实交付日志后再断言重新准入；丢 ACK 的准确 unknown marker、显式恢复及字节上限仍单独检查，崩溃原 owner 只经准确已 join 子进程的宿主认证恢复 producer。安装包加当前夹具 10 项通过、27.331 秒（`candidate32-large-retry-fixture.log`）。

控制器崩溃正例改为在原 15 秒宿主场景界限内核实实际 supervisor_reap 落盘，再于业务结果持久化前退出；原 .8 秒工作期限不变，安装包单例 3.818 秒通过（`candidate32-crash-receipt-fixture.log`）。暂停恢复单例确认为测试先切接收权限后关闭旧 producer，现先关闭原 runtime 后切新代次；原业务权限和断言不变，安装包单例 23.631 秒通过（`candidate32-nested-pause-fixture-repair.log`）。主执行核对修订路径，独立复审未发现这些夹具改动的阻塞项。

源码独立观测已补充准确代次 driver_close 交付前保持不完整的保守规则，原始 collector 读取不变，不宣称全部并发生命周期已完成；缺失、错代次和真实迟到回执的回归及六项 handoff 检查通过，独立复审无阻塞。原输出压力的 deadline／cancel 两个子例和新回归在源码下 2 项、16.183 秒通过（`source-driver-close-pressure-regression.log`），原期限及断言未变；该产品改动尚未进入候选 32，不作其安装包新证据。

本轮临时定向运行器缺少 main guard，导致 spawn 导入重复执行测试；该轮 `candidate32-budget-floor-context-fixtures.log` 退出 1，不用于产品结论。已保留原运行器并加 main guard，后续用新日志验证。完整隔离套件的内层 run_installed_tests.py 本来具有 main guard，不能因此撤销其真实失败。context contention 原单例在安装包下 2.049 秒通过（`candidate32-context-attachment-diagnostic.*`），未复现原全量失败，也未证明负载同因；夹具现于失败时分别保留 bounded 诊断，读取失败不覆盖原断言。supervisor budget floor 原探针 2.408 秒通过，仍确认 None 可能是日志准入，现仅以实际 unresolved obligation 决定是否宿主认证，保留原截止与无额外原生调用断言；后续完整受影响模块正在验证。


### 候选 33：观测修复与异步回执边界

候选 33 wheel/sdist 位于 `/tmp/agent-control-080-candidate33/dist/`，独立无依赖、YAML 和构建测试环境已安装。141 个产品文件／139 个 Python 文件与当前源码及 wheel 逐字节一致；与候选 32 只有 `dispatcher_sdk/observability/journal.py` 产品文件不同，269 个测试文件与当前源码一致（`candidate33-product-test-parity.json`）。构建记录 `candidate33-build.log`，安装元数据／139 个 Python 文件核对通过。此前候选 30／31／32 的逐字节等价只在当时成立，不再宣称全部当前产品相同。

候选 33 受影响安装回归 61 项、158.724 秒全部通过，跳过 0（`candidate33-affected-installed-regression.log`）：真实压力的 5 项全部通过，另覆盖准确 handoff、新 driver_close、10 项大回执重试、暂停恢复、预算 floor、context attachment 及生命周期交付。原 context 全量失败的原因仍未复现，不将本次通过改写成旧失败已确定同因。另在旧候选 32 加当前夹具的预算／context 两模块 10 项、11.145 秒通过（`candidate32-budget-floor-context-guarded.log`），与先前错误临时运行器的失败日志分开。

候选 33 G01／G13 集成均 passed（`candidate33-g01-g13/acceptance.json`），G13 仍只为能力合同与 strict 拒绝，不证明真实强隔离。双语 Wiki 共 25 页本地导出 `/tmp/agent-control-080-candidate33-wiki/`，未发布。新上下文独立源码审查沿公开 invocation→持久请求→SDK root/controller/child→预算／权限→取消／撤销与重放，所审范围未发现确认的 P1／P2；未运行模型或完整故障矩阵，不用审查代替验收。完整单进程隔离消费者仍保留候选 32 的 2700 秒超时失败；仅分片覆盖不能自动满足该原测试合同。

候选 33 文档检查通过：572 个本地链接，4 个 README 实际示例通过、0 跳过（`candidate33-docs-check.log`）。剩余 10 个真实 OpenCode 场景已按冻结脚本串行启动，清单 `candidate33-remaining-native-plan-v2.json`、批次日志 `candidate33-remaining-native-batch.log`；每个场景保留原预算，首个失败即停止，未运行的仍为 not_run。

候选 33 的 G03／G04 原生补验通过：`native33-dependencies-files/acceptance.json` 及同目录逐项证据核对安装来源、原 SDK Run 和期限，双生产者输入齐备前消费者未执行，随后实际消费产物，稳定重放与冲突拒绝通过。原 240 秒／8 次 Agent／48 次模型请求预算内，实际计量 4 次 Agent、19 次模型请求。目录替换竞争 104 次替换、500 次拒绝、0 次允许、无错误，工作线程停止且外部文件未变；允许的工具写入另有正例。这仍仅证明声明文件工具边界，不宣称进程强隔离。

候选 33 精确安装发现清单 `candidate33-installed-discovery-v2.json` 按原内层复制规则和脚本夹具发现 2073 项、无 loader error，未执行测试，不计验收。首版清单遗漏两份脚本夹具，保留其错误结果。后续隔离消费者夹具仅增加每项测试开始及耗时的单调时钟日志，独立只读复审未发现阻塞；发现规则、断言、结果处理、main guard 与原 2700 秒截止均未修改。此改动尚未进入候选 33，也未执行，故上述 269 个测试文件一致仅指快照核对当时。

候选 33 G05／G06 原生补验通过，证据 `native33-groups-rework/acceptance.json` 与 `G05.json`、`G06.json`。两轮 coder 的真实适配器入口均发生重叠，调用组产物、精确绑定、返工反馈、稳定重放、SDK effect／回执及原执行限制全部核对。未关闭组、迟到成员、冲突返工、错误 reviewer 和跨 Run 组引用分别命中原始拒绝。原 3600 秒／16 次 Agent／128 次模型请求预算内，实际计量 7 次 Agent、42 次模型请求。reviewer 保持逻辑身份，两个返工轮次是不同 invocation／原生 session，不宣称同一原生会话。

候选 34 已构建 wheel/sdist 并完成元数据检查；`candidate34-product-test-parity.json` 记录 141 个产品文件与候选 33 及 checkout 直接字节一致，唯一测试差异是上述耗时诊断。Linux x64 Python 3.10.22／3.11.18／3.13.18 的独立候选 34 环境已准备，完整套件尚未启动；环境清单为 `candidate34-python-regression-environments.json`。不把候选 33 的已执行结果改名为候选 34 执行，也不把环境准备计为平台验收。

候选 33 显式返工路由 `native33-explicit-rework/report.json` passed，9 项原检查全部通过，宿主正常关闭。实际安装来源及 OpenCode 版本、原预算和执行限制、普通 runtime effect／准确原生清理、原始 admission／group 回执、选定成员反馈、同逻辑 reviewer 实际消费，以及关闭后公开路由和稳定重放均核对。原 3600 秒场景未延长；此为 G12 当前制品组合的一部分，权限及其他分类仍等待后续批次，不提前升级整项。

候选 33 邮箱 `native33-mailbox/report.json` 五个真实场景全部 passed：FIFO 11 项、reject 8 项、replace_pending 9 项、启动前取消替换 12 项、发送后未知隔离 10 项；原预算、精确清理、会话隔离及宿主正常关闭均核对。

候选 33 剩余批次在 budgets 退出 1，工具会话 72012 已确认终止；`candidate33-native-batch-process-exit.json` 保留实际退出，后五项未运行。`native33-budgets/report.json` 的 nested 和 goal 均通过；exhaustion 失败，不能升级 G15。原 OpenCode part 记录实际调用 dispatcher_agent_send，并返回 agent_permission_denied；场景本应调用 dispatcher_agent_call，而 worker 只授予 invoke，因此没有预算耗尽子意图，Run 成功是该实际输入的预期结果。独立源码及原生数据库检查与主执行结论一致，未确认产品预算缺陷。诊断 `native33-budget-failure-diagnosis.json` 保留失败检查与准确证据路径。

预算验证器仅明确工具全名／参数，并增加不替换返回值的实际工具调用及子结果记录与断言；原调用次数、240 秒期限、失败 Run、零子执行、准确 SDK 截止及重开断言全部保留。独立只读复审无阻塞。此改动晚于候选 34 快照，唯一变化的验证脚本明确冻结在 `candidate34-reviewed-native-bundle-v1/scripts/`；产品 141 文件仍与候选 33／34 一致。新六项串行批次 `candidate34-remaining-native-plan-v1.json` 已启动，首个失败即停止；结果尚未产生，完整回归与版本矩阵仍未启动。

候选 34 预算补验 `native34-budgets/report.json` passed：nested 16 项、goal 9 项、exhaustion 15 项全部通过，三个宿主均正常关闭。记录实际 agent_call 的准确 caller／参数与返回子 invocation；nested 返回 CHILD_OK，exhaustion 返回 failed／agent_call_budget_exhausted，后者无子 SDK command、effect、原生操作或提供商执行。三场景分别计量 2／1／1 次 Agent，5／3／4 次模型请求，与真实出站 POST 一致；原 240 秒截止、精确 root／controller／child SDK 命令、可信预算约束、原共享预算、goal 同会话续接及重开零新增执行均核对。候选 33 的错误工具尝试仍为 failed。父子取消和无关会话继续尚在后续场景验证，因此 G15 整体保持未完成。

候选 34 取消 `native34-cancel/report.json` passed，13 项检查及宿主正常关闭通过：实际模型先 send 子调用，再执行准确 cancel；被取消 worker 已实际发送请求并处于运行中，取消 SDK effect、准确后代范围、原始各请求截止与预算、入口唯一性、controller 普通 SDK 成功及输出、原 Run 取消结果均核对。worker 的本地原生清理确认，业务保持 recovery_required；独立服务普通完成。该结果不将本地清理提升为提供商副作用已知。G15 的历史排队／重试／宿主恢复与当前制品影响覆盖正在逐项复核，完整 G17／G18 回归尚未执行。

候选 34 资源 `native34-resources/report.json` 的 resources_limited／resources_disabled 均 passed。受限场景保持 128 MiB 容量、存活等待父级 96 MiB、子级 64 MiB，子级在父级保留资源时无 runtime effect／原生操作，父级提交且准确清理后才实际执行；默认关闭限制时子级与运行父级重叠。原 360 秒预算及共享 controller／产物／计量检查不变。该脚本为整个 G17 保留 not_run 并固定退出 1，原批次据此停止；这是批处理范围接线错误，不是资源检查失败，也不改记进程退出 0。实际退出证据 `candidate34-native-batch-process-exit-v1.json` 保留，不重跑已通过资源场景。三个未运行的监督／权限／清理未知场景改由 `candidate34-remaining-native-plan-v2.json` 串行执行，仍保持首个失败停止。

G15 独立证据复核区分了模型取消子调用和宿主取消父调用后向下传播，后者尚缺直接原生证据，正在补充专用验证器。历史权限场景有同一 Run 非零已花费预算在宿主正常重启后不变的证据；崩溃窗口的旧记录未直接保存崩溃前预算快照，因此不能将其描述为精确测得的非零用量崩溃前后等价。后续原生权限复验及最终影响复核仍保留各自来源，不以源码审查替代执行。


## 候选 34：监督、权限重启与清理未知复验

`candidate34-remaining-native-plan-v2.json` 中监督和权限均退出 0；随后清理未知场景退出 1，整批实际退出 1。工具终态单独保存在 `candidate34-native-batch-process-exit-v2.json`，没有根据计划状态或进程消失推定成功。

`native34-supervision/report.json` 的 stable、stale、disabled_and_stop 均通过。真实父级原生执行仍存活时，稳定无产物观察只接纳一个诊断子调用，实际消费原观察并在原 controller、Run 和截止内成功；旧观察在父级提交新产物后于接纳前拒绝。监督关闭和显式停止的对照均通过。原 360 秒预算保留；该报告明确不宣称整个 G17 完成。

`native34-permissions/report.json` 的 14 项检查通过：实际原生入口后撤销权限，原调用保持 recovery_required 且完成准确本地清理，同键排队请求没有启动；无关角色仍成功。真实停止及重启后，原 Run、截止、非零已消费次数和 unknown 结果保持，撤销持续有效；恢复权限仅影响未来工作，不重放原调用。此场景证明清洁停止／重启，不冒充崩溃前后预算快照。

`native34-cleanup-unknown/report.json` 保留失败：九项中八项通过，`original_frozen_budgets` 为 false。入口预算时钟为 trusted，故障恢复后的原执行时钟报告 unknown／`budget_clock_sample_unresolved:sampling`；验证器原先将恢复时钟也必须 trusted 与冻结预算绑定为一项。可重构的 120 秒／8 次 Agent／12 次模型限制、原绝对截止、SDK command 约束、执行代次和已消费次数均符合原限制；原清理回执仍缺失，资源保留、同键隔离、无后继执行及无关会话实际成功均通过。未据此认定产品预算缺陷，也未将 unknown 改记为 trusted。正在修正验证器对冻结限制与当前时钟授权的混淆；原失败不改写。


## 候选 35：安装快照与后续验收入口

候选 35 的独立 wheel/sdist 和白名单快照位于 `/tmp/agent-control-080-candidate35/`。无依赖环境、带 YAML 环境和构建测试环境均已安装；元数据及 139 个 Python 文件通过核对，产品全部 141 个文件与候选 34、当前产品源码及 wheel 逐字节一致（`candidate35-product-parity.json`）。没有新增散列检查。完整回归尚未启动，三个 Python 版本测试环境准备成功不等于测试通过。

候选 35 的 G01 和 G13 合同／拒绝检查通过（`candidate35-g01-g13/acceptance.json`）；没有原生强隔离后端或真实隔离验收。文档检查通过 572 个本地链接、4 个真实 README 示例、0 跳过；双语 Wiki 本地导出 25 页至 `/tmp/agent-control-080-candidate35-wiki`，未发布。

`native34-cleanup-unknown-v2/report.json` 复验十项通过，工具会话 85894 实际退出 0，退出记录 `candidate34-cleanup-unknown-process-exit-v2.json`。新增检查单独区分入口 trusted 时钟、冻结限制与故障恢复当前时钟，保留故障前和两次恢复快照；冻结预算及已消费次数未重置。两次重启后的原 invocation 和 SDK execution 都是 recovery_required、原 effect 是 indeterminate，缺失认证清理回执仍缺失，原资源预留保留，同键后继没有执行或发送，无关会话实际成功。本次两次恢复时钟都为 trusted；不声称本次实际走过 unknown-clock 分支，原第一轮的采样 unknown 失败记录仍保留。

父级取消验证器第一轮 `native34-parent-cancel/report.json` 实际传播取消、准确清理和无关活动服务继续成功均通过，但活动服务的预算时钟读数处在瞬时 sampling unknown，整项退出 1。第二轮 `native34-parent-cancel-v2/report.json` 在证据读取中抛 TimeoutError，整项退出 1，距原父请求截止仍约 97 秒；未保留具体读取调用／错误消息，不能断言预算耗尽、死锁或具体锁持有者。修正后的第三轮分别记录 SDK snapshot／显式有界 limits 读取，只有明确的只读锁准入超时或其他约束全部有效的准确 sampling unknown 才等待，仍使用原 180 秒／4 次 Agent／16 次模型预算，不重试实际执行。所有失败记录和退出记录保留。

后续串行入口为 `/tmp/run_agent35_full_regression.py`：先要求清理复验和父级取消第三轮的真实工具退出 0 记录，再运行原完整单进程隔离消费合同（内层 2700 秒不变），成功后才依次运行 Python 3.10.22、3.11.18、3.13.18 完整检查；首个失败停止。两个阶段都有相同的进程重叠检查；实际 Python 版本及安装包来源在矩阵开始前重新验证。临时编排已经独立审查；不根据待运行计划推定任何测试通过。


父级取消第三轮 `native34-parent-cancel-v3/report.json` 十二项全部通过，五个 SDK 截止检查全部为 true，宿主关闭成功，工具会话 54053 实际退出 0（`candidate34-parent-cancel-process-exit-v3.json`）。实际父级 send 接纳子级，子级已发送上游请求，无关 service 也已活动；调用宿主公共 `parent.cancel()` 后父子准确身份和清理回执成立，子级 SDK execution 保持 recovery_required、原 runtime effect 为 indeterminate，无关活动服务继续交付精确 `OTHER_OK`。原 180 秒、4 次 Agent、16 次模型限制不变，父子共享已消费 2 次 Agent，无关 Run 消费 1 次；没有原子级重启或后续发送。第三轮记录 controller 只读 limits 准入出现过明确锁超时，后续读数通过；这证实第三轮确实处理了该暂态，不倒推第二轮异常的具体调用。

候选 35 完整串行回归已启动，外层日志 `candidate35-sequential-regression.log`，当前执行记录 `candidate35-sequential-regression.json`。启动前验证了上述真实终态和产品逐字节关系；完整回归尚无通过结论。候选 35 快照后仅父级取消验证器增加只读分步诊断／准确暂态处理及验收台账变化，产品和回归测试没有变化；各实际验证器使用的冻结副本路径分别保留。


六个公共 API 类型消费文件已对候选 35 安装环境重新检查，Python 类型目标为 3.10，使用 mypy 的 `--python-executable` 指向候选 35 YAML 环境，从源码目录外执行；全部通过（`candidate35-all-typing.log`）。这不是原生 Python 3.10 执行或完整回归。

独立证据复核未发现 G12／G15／G16 当前 Linux x64 分项结论的最低合同缺口。清理未知第二轮保留的故障前、第一次和第二次恢复快照，实际同一 Run、截止及已消费 Agent／模型次数分别为 1／2 → 1／2 → 1／2，effect 从 performing 到 indeterminate；这是非零已消费计数跨该真实故障窗口保持的测量，不推及非零 reserved／unknown 计数或任意崩溃点。该审查没有执行模型或测试。

完整平台要求清单保存在 `candidate35-platform-requirements.json`，继续保留 Linux／Windows、x64／ARM、Python 3.10–3.13；Windows ARM 的 Python 3.10 保留已有 x64 兼容范围。缺少原生主机／授权的组合为 blocked，没有改为 not_applicable。当前 Linux x64 完整回归未结束。


当前紧凑证据索引为 `candidate35-acceptance-index.json`：逐项列出 G01–G18、真实执行候选、产品逐字节关系与影响依据、原报告及历史失败。主代理复核了各验收结论，G17 仍未完成，G18 仍受原生主机缺口阻塞；索引中的回归状态只是生成时快照，必须重读 `candidate35-sequential-regression.json` 后再报告结果。

候选 35 完整安装回归实际退出码为 1，内层按原 2700 秒超时：`/tmp/agent-control-080-evidence/candidate35-sequential-regression.json`、`/tmp/sdk-observability-consumer-jnqmyj98/installed-suite/command.json` 和 `stderr.log`。已完成 1722 项记录；最后一项开始时距内层截止约 2 秒，不能据此认定其卡住。此前记录三个即时失败：进程模式子调用未能在原截止前完成接纳并返回 `database is locked`；两次恢复/重试调用返回 `None`，具体准入阻因尚待确认。无最终套件摘要；Python 版本矩阵按首败停止，尚未启动。

候选 35 安装产品的两项失败诊断复现（原测试期限与断言不变，工具进程退出 1、2 errors）：进程重试和沙箱恢复的第二次 `run_once` 均返回 `None`。两者的返回后只读快照均观察到该执行被诊断回执排除，上一代 lifecycle producer 尚 open 且 `driver_close` 尚未投递；进程重试的 supervisor 清理已解决，沙箱记录还保存在 `/tmp/sdk-sandbox-runtime-4s3304d5/sandbox-before-cleanup.json`。快照位于调用返回之后，不能代替原子时刻的 claim 决策，也不证明两项原始失败的确切原因；须依据公开 `run_once` 合同处理并保留原截止及验证。进程 retry 复现的输出通过实际工具会话 2111 保留；本次复现不替代完整回归。

按公开合同，仅对 `run_once()` 返回 `None` 在持久化原 work budget 仍可信且未过期时重新调用，既有结果和准确代次清理断言不变。两个修正后的测试及原 5 秒子调用失败保真测试针对候选 35 安装包的定向执行均通过，真实进程退出 0，记录为 `/tmp/agent-control-080-evidence/candidate35-targeted-diagnostic-v2.log`。子调用先前 SQLite 锁来源仍未确认；新增异常时侧车可记录实际堆栈与 SQLite 错误码，该侧车在失败路径会影响时序，本次通过并不能反推原失败原因。

对超时末尾未完成项的首个补充诊断使用了未加 `__main__` 保护的脚本，真实 spawn 子进程重复运行测试，结果受污染；已核实并终止独立进程组，实际退出 143，原始日志 `/tmp/agent-control-080-evidence/candidate35-remaining-diagnostic.log` 保留。该脚本输出不能作为 SDK 成败证据。后续补充诊断必须修复隔离与多进程保护；任何后续通过也不替代完整单进程回归。

候选 35 中断位置起的补充诊断运行完 351 项（18 跳过）并以退出码 1 结束，唯一失败为 `test_close_retries_transient_diagnostic_delivery`：旧夹具只监测单条 `lifecycle_note`，实际关闭使用 `lifecycle_note_batch`。原日志 `/tmp/agent-control-080-evidence/candidate35-remaining-diagnostic-v2.log` 保留；已改为针对准确执行、代次与 `test_pending` 事件的批量投递注入一次暂态失败，保留原重试次数、关闭和唯一持久化断言。该修正针对候选 35 安装包的定向测试退出 0，见 `/tmp/agent-control-080-evidence/candidate35-storage-activation-diagnostic-v1.log`。补充运行耗时 232.437 秒，不能拼接为一次完整通过；原完整回归超时及三处即时失败仍须按新快照复验。

候选 37 构建 wheel/sdist，产品 141 文件与候选 35、当前产品源码及新 wheel 逐字节一致：`/tmp/agent-control-080-evidence/candidate37-product-parity.json`。已对候选 37 安装包、其冻结测试快照执行四项受影响测试，真实退出 0（`/tmp/agent-control-080-evidence/candidate37-four-targeted.log`）；完整回归及平台矩阵仍未通过。慢场景 profiling 通过（98.778 秒）；多线程/递归累计统计超过墙钟时间，不用于推算节省或宣称回归修复。

只读等待观察的隔离性能实验使用相同慢测试、安装环境和原测试期限交替执行四轮，结果保存在 `/tmp/agent-control-080-evidence/wait-observation-experiment/results.json`：基线 65.49／76.25 秒，实验 62.99／77.39 秒，四次均退出 0。波动范围重叠，未证明收益足以解决完整回归超时；实验修改仅在 `/tmp/sdk-wait-observation-experiment-TcZSa4/source`，未并入产品，且读写并发和取消语义尚未验收。

候选 37 修正四项受影响测试后，已启动原完整安装消费回归，原内层 2700 秒、原断言和串行顺序不变；记录 `/tmp/agent-control-080-evidence/candidate37-sequential-regression.json`。通过后才依次执行已准备的 Python 3.10.22／3.11.18／3.13.18；失败即停。附加采样 `/tmp/agent-control-080-evidence/candidate37-regression-monitor.jsonl` 以 15 秒间隔只读记录宿主压力、磁盘及进程树，采样有少量开销，不能将全机压力直接归因于测试；进程树快照可能遗漏短生命周期或已被重新归属的子进程。此前候选 35 超时和试验全部保留，不推定本轮结果。

候选 37 的 Python 3.12 完整安装消费回归最终退出 1：内层在原 2700 秒超时，记录见 `/tmp/sdk-observability-consumer-betu5cnc/installed-suite/command.json` 和 `stderr.log`，外层见 `/tmp/agent-control-080-evidence/candidate37-complete-py312-regression.log`。日志记录 1600 个测试开始、1599 个完成，未记录即时失败；最后的 nested cancellation 测试距首个测试开始约 2692.5 秒才开始，不能据此认定该测试卡住。未产生完整套件结果，其他 Python 版本按首败停止，未启动。候选 35 与 37 两次超时均保留，不能把已完成前缀与其他运行拼成通过。

候选 37 之后，当前源码调整了调度读取产物及版本的方式：同一调用的当前值、最新版本及历史值校验合并到一次事务，减少逐产物的事务；最新版本与当前值在同一事务快照内读取，旧记录仍以版本 1 回退。独立审查未发现具体缺陷。源码级多版本／旧记录／并发修订及绑定测试通过，修订值 NEW 与版本 2 实际进入下游绑定的集成测试所在文件 10 项通过；完整重做集成测试在此前版本的该优化上通过，耗时 63.707 秒。当时合并历史校验后的性能和完整重做路径仍须复验，也尚未构建新候选；候选 37 的产品逐字节一致关系不再覆盖当前源码，此处结果不替代新安装包或完整回归证据。

加入历史校验后的源码级完整重做用例实际通过，耗时 69.312 秒，记录 `/tmp/agent-control-080-evidence/artifact-read-current-rework.log`。候选 38 已构建（`/tmp/agent-control-080-candidate38/dist/`，构建日志 `candidate38-build.log`）；候选 37 与 38 安装包的交替重做对照正在串行运行，过程记录于 `agent38-artifact-benchmark/`，尚无完整对照结果。任何单次耗时不证明总体提速，也不替代完整回归或原生验收。

交替对照完成，四次均退出 0：候选 37 为 53.810／63.416 秒，候选 38 为 59.224／58.699 秒，原始结果与日志位于 `/tmp/agent-control-080-evidence/agent38-artifact-benchmark/`。这一小样本没有显示可辨认提速，不代表性能等价。产品试验已撤回；独立新增的下游修订产物绑定测试保留，撤回后实际通过（5.931 秒）；此前误用测试类名的命令以加载错误退出 1，随后以正确类名运行，不能将误调用算作测试通过。当前 139 个 Python 产品源码文件与候选 37 快照逐字节一致；没有由本对照推断完整回归通过。

环境对照：同一候选 37 安装包、原重做用例及断言，在 `/dev/shm` tmpfs 临时目录的 exact-member 用例退出 0、24.347 秒（`candidate37-tmpfs-rework.log`），此前 ext4 对照为 53.810／63.416 秒；closed-successor 用例 tmpfs 退出 0、12.183 秒（`candidate37-tmpfs-closed-rework.log`），随后 ext4 退出 0、35.215 秒（`candidate37-disk-closed-rework.log`）。均为小样本，不能外推完整套件一定通过。临时目录文件系统会改变 I/O 和断电持久性条件；tmpfs 的测试结果不得替代磁盘持久性或原生平台验收。实验后 `/dev/shm` 可用容量约 3.4 GiB；完整套件的峰值占用尚未验证。

候选 39 已构建，快照、当前源码、安装环境及 wheel 中 141 个产品文件与候选 37 源码逐字节一致；新增下游绑定测试包含在候选 39 快照。完整安装消费测试现以候选 39 运行，内层 2700 秒和原测试范围不变，主要消费证据直接写磁盘，`TMPDIR` 指向 tmpfs，记录为 `/tmp/agent-control-080-evidence/candidate39-tmpfs-regression.json`。启动检查发现实际获准运行命名空间的 `/dev/shm` 约 2 GiB，与普通命名空间显示的 3.4 GiB 不同；第一次以 2 GiB 精确阈值预检时测试尚未启动即退出 1，随后核实容量并以 1 GiB 预检启动，容量采样不能保证覆盖瞬时峰值。进程扫描和私有锁不提供跨启动器互斥；部分程序可能不使用 TMPDIR，复制文件只是事后快照，不能证明全部中间证据都被保留。运行结果尚待实际退出，tmpfs 不能证明磁盘断电持久性或其他原生平台验收。

候选 39 本轮实际退出 1，约 44 秒即在公开消费示例的 silence cancellation 场景失败，未到完整内层套件：`candidate39-tmpfs-regression.log` 记录 `worker containment not confirmed`。证据保存在 `/tmp/agent-control-080-evidence/candidate39-consumer-evidence/sdk-observability-consumer-710929y9/silence/`：业务结果为 cancelled、子进程输出在检查窗口稳定，但 `after-cancel.json` 的 worker 最后观测为 alive、supervisor exited 但 cleanup unknown；不得将稳定输出或业务取消等同于清理已确认。采样最低可用约 1.86 GiB，但采样不是完整峰值证据。原因正在调查；不据此声称磁盘或 tmpfs 导致失败，也不盲目重跑。

公开消费示例此前在 `task.wait` 返回后立即要求诊断确认，与取消证据文档所述的异步诊断发布时序不一致。现保留首次观察和原清理断言，并在原 15 秒等待窗口的剩余时间内，通过公开只读接口查询取消回执所指 execution、attempt 和 fence；身份不匹配或期限内未确认仍失败。该期限限制确认可被接受的时间，不保证示例整个调用的墙钟时间不超过 15 秒。对候选 39 已安装产品执行修订示例的 silence 场景退出 0（`candidate39-silence-bounded-v1`），首次观察已经确认，尚未实际覆盖延迟收敛分支，也不能改变候选 39 原失败结果。独立审查指出缺失身份的临时观察应继续等待，现已修正；本轮后续完整示例和新的完整回归结果均另记。

修订后的消费示例五个场景在候选 39 安装产品上全部退出 0（`candidate39-consumer-bounded-v1`）。另以临时诊断副本注入缺失身份的首次观察，后续通过公开接口读取实际清理证据，silence 场景退出 0（`candidate40-injected-missing-observation`）；该注入仅验证查询流程，不是完整回归或真实证据丢失恢复的证明。候选 40 包含本次示例修订，新安装套件记录 `candidate40-tmpfs-regression.json`，由执行会话运行，内层原 2700 秒和测试范围不变；结果以实际退出记录为准。一次 `nohup` 后台启动未产生进程或测试记录，随后使用受控执行会话启动，不把前者当作测试。

对候选 39 原失败保留的结算日志进行只读核对：与失败观察相同 execution、attempt、fence 的 `process_cleanup` 注记最终持久化，来源为 `runtime_supervisor_reaped`、状态 confirmed，创建时间比首次失败观察晚约 0.223 秒。结果和查询边界见 `candidate39-original-cleanup-note-followup.json`。这支持原失败存在证据发布时序差，但该追查不是失败后重新执行的公开观察，也不证明其他执行均会收敛；原失败结果保留。

候选 40 当前源码、冻结源码、安装环境及 wheel 中 139 个产品 Python 文件逐字节一致，记录为 `candidate40-product-parity.json`；仅覆盖 Python 文件，不代表测试执行或其他制品文件一致。历史验收保持各自实际候选来源，最终索引仍需依据完整回归、平台矩阵和变更影响更新。

为候选 40 准备 Linux x64 的 Python 3.10.22、3.11.18 和 3.13.18 安装环境，记录 `candidate40-python-regression-environments.json`：分别重新安装候选 40 wheel 并核对解释器版本与 SDK 导入路径。这只是环境准备，三套完整回归都尚未执行；候选 40 的 Python 3.12 完整回归通过前不启动版本矩阵。

三个版本环境的 139 个已安装产品 Python 文件分别与候选 40 冻结源码逐字节一致，结果见 `candidate40-matrix-python-parity.json`；该检查不涵盖非 Python 文件，也不是运行验证。版本矩阵脚本依据独立审查加强了前置回归身份、执行环境、并发锁和外层测试摘要检查，仍须以脚本复审及实际执行结果为准。

候选 40 内层套件的保留 fixture 标识当前测试为 `test_retained_admission_checkpoint_holds_slot_and_kernel_until_same_fact_commits`，同测试在候选 35／37 分别约 2.61／2.15 秒结束；本轮已停留数分钟。两次同一进程只读快照相隔约 56 秒，I/O 计数和线程身份均未改变（`candidate40-stall-snapshot-1.json`、`candidate40-stall-snapshot-2.json`）。这些快照不能确定具体 Python 调用点或原因；不会把活进程当成终止，不改动其数据库、测试现场或 2700 秒期限。此轮最终结果尚未产生。

只读查询停滞 fixture 的 Kernel 状态显示该执行结果为 succeeded，同时存在一条 `sampling` 预算标记；两者不能证明测试已进入特定的注入阶段，也不能识别等待线程。第一次独立复现脚本缺少多进程入口保护，子进程重复运行测试，输出 `candidate40-checkpoint-diagnostic.log` 无效，不能归咎于 SDK。修正入口保护后，候选 40 安装包的同一定向测试在 2.120 秒退出 0（`candidate40-checkpoint-diagnostic-v2.log`），未复现原回归停滞，不能据此认定原因已消除。

为后续安装套件 runner 增加逐测试的 120 秒周期性 faulthandler 全线程栈：不调整发现范围、业务断言或原 2700 秒时限。独立只读审查指出其不能覆盖测试发现、类级设置／清理间隙或子进程的栈，且新增计时线程与输出可能影响时序；无已知与其他测试的进程级定时器冲突。临时缩短计时器的合成检查分别覆盖正常通过、普通失败、子例失败、跳过、spawn 和堆栈输出（`candidate41-stack-instrumentation-smoke.log`、`candidate41-stack-instrumentation-cases.log`）；合成检查仅验证诊断机制，不能代替安装套件回归。该测试 runner 修订尚未进入候选 40 或其正在进行的执行。

候选 41 已冻结并构建 wheel/sdist，包含上述 runner 与公开消费示例的改动；产品的 141 个文件与候选 40 冻结源码、候选 41 安装环境及 wheel 逐字节一致（`candidate41-product-parity.json`），这不是执行或验收证明。针对候选 40 停滞现象启动独立监督测试模块诊断，使用候选 41 安装包、隔离证据目录及总 240 秒诊断期限；保留候选 40 原套件，模块诊断的结果另记。

候选 41 监督模块独立诊断实际退出 0，22 项、79.231 秒（`candidate41-managed-module.log`），其中包含候选 40 保留现场所标识的测试；该运行未复现停滞，不能代替原全量回归或证明原因已经修复。原套件保留并继续依其既定期限执行。

候选 41 快照使用其安装解释器检查 572 个本地文档链接并实际运行四个 README 示例，零跳过（`candidate41-docs-check.log`）。使用工作区 mypy、候选 41 安装解释器和冻结的六个类型消费示例执行 Python 3.10 类型检查，退出 0（`candidate41-all-typing.log`）。这些是局部检查，不代表当前制品的完整回归或跨平台验收。

候选 41 的完整回归启动脚本已准备并独立复审：明确要求候选 40 的结束状态和退出码，隔离 Python 环境，保持同一测试模块与内层期限。该脚本只在子进程退出后复制临时目录，未提供意外信号退出时的完整收集保证；进程扫描及其私有锁也不是所有启动器之间的全局互斥。候选 40 尚未结束时不得启动候选 41 完整回归。

候选 41 安装环境实际执行 G01／G13 integration，均返回 passed（`candidate41-g01-g13/acceptance.json`）。G13 明确只覆盖能力合同与不支持时启动前拒绝：未提供原生 strict 后端，也未验收真实强隔离。

候选 41 的 Linux x64 Python 3.10.22／3.11.18／3.13.18 环境已安装该候选 wheel，记录实际解释器、CPython 版本和 SDK 导入路径；三个环境各 139 个产品 Python 文件与候选 41 冻结源码逐字节一致（`candidate41-python-regression-environments.json`、`candidate41-matrix-python-parity.json`）。这只是执行准备，三个版本的完整测试尚未运行。

进一步检查同一 `after-cancel.json`：同 execution／attempt／fence 的 `worker_tree_cleanup_observed` 和 `process_cleanup` 活动阶段均报告 confirmed，分别标注 POSIX supervisor containment 与 runtime supervisor reaped；但 worker 列表仍由较早 `handler_entered` 合成 alive，且同一报告有 lifecycle append 的 `database is locked`。这是公开投影与阶段证据不一致；锁错误不能证明独立的 worker exited 写入失败。诊断注记投影只在 `process_cleanup` confirmed 注记存在时修正合成 worker 状态，本次快照没有该注记。尚不能区分短暂交付竞态与持续缺失，须按同一执行身份以公共观察和精确清理结算证据诊断，不把此前 unknown 解读为最终清理失败或直接改为通过。

候选 40 完整安装消费回归最终失败：内层达到 2700 秒期限，1117 项开始、1116 项结束，最后停留在上述监督测试；完整范围未完成。内层日志另记录三个工作区测试异常，均涉及 `same-state workspace owner not found`，见 `candidate40-consumer-evidence/sdk-observability-consumer-xxw65ziz/installed-suite/stderr.log`；外层结果为 `candidate40-tmpfs-regression.json`。已确认源码存在工作区所有权快照与本地清理之间的竞态，但日志不能独立证明每次失败的具体线程交错。候选 41 的局部通过不改变候选 40 的结果，也不构成完整回归通过。修复与复验须另记。

当前源码将工作区快照和协调纳入本地资源锁，避免与本地清理交错；保留旧所有者的精确清理证据要求。新增确定性测试在候选 41 旧源码复现同一异常，在修复后源码通过。工作区应用测试 6 项在实际回环环境通过，所有权测试 9 项通过；首次受限环境的工作区应用测试全部跳过，不计为通过。独立审查未发现明确死锁或新增竞态；协调旧所有者可能每项持锁等待最长约一秒。上述均为局部源码验证，新安装包与完整回归尚未执行。

对候选 39 原执行的原绑定存储进行公开只读查询，同 execution／attempt／fence 的 worker 后续显示 exited、cleanup confirmed，证据为 `candidate39-public-inspect-timestamp-fix.json`；整体报告仍因采集器不再新鲜而不完整。原失败与锁错误原因并未因此消除。查询另暴露清理状态沿用较早 handler-entry 持久化时间的问题；当前源码改为使用对应清理注记的持久化时间，独立审查无明确阻塞项，settlement journal 23 项测试通过，新增测试在修复前复现时间不一致。此修复尚未经过新安装包或完整回归。

曾尝试为安装套件转发实时日志；独立审查发现直接子进程退出时可能遗漏仍持有输出句柄的后代，改变原来的完成判定，因此该转发改动已撤回。原子进程输出捕获、2700 秒期限和逐测试超时堆栈诊断保留；不能声称已实现实时日志。

候选 42 已从当前源码构建 wheel 和 sdist（`/tmp/agent-control-080-candidate42/dist/`，构建日志 `candidate42-build.log`）。安装环境导入实际指向该候选，139 个产品 Python 文件与冻结源码内容一致；这不涵盖全部制品文件。安装版工作区应用、工作区所有权和 settlement journal 三模块共 38 项通过，无跳过（`candidate42-workspace-settlement.log`）。这些定向结果不能替代完整回归或其他平台验收。

候选 42 已启动原范围的 Python 3.12 安装消费回归，使用 tmpfs 临时目录，内层期限仍为 2700 秒；实时状态与环境局限记录在 `candidate42-tmpfs-regression.json`。启动和存活不代表通过；磁盘持久性和原生平台证据须另行验证。

候选 42 的 Linux x64 Python 3.10.22、3.11.18、3.13.18 安装环境已经准备并核对来源，三个环境的 139 个产品 Python 文件与冻结源码内容一致（`candidate42-python-regression-environments.json`）。三个版本的完整回归尚未启动，环境准备不代表测试通过。

候选 42 冻结源码的六个类型消费检查通过（`candidate42-all-typing.log`）。文档检查退出 1：首个 README 实例等待 `message-42` 在原 10 秒期限内超时，未完成后续示例，记录为 `candidate42-docs-check.log`，现场位于 `candidate42-doc-examples/sdk-docs-README.md-example-1-x7wkeh5d/`。检查与完整回归并发；目前不能据此确定超时原因或归咎资源竞争，待查明并复验。

该 README 现场的 handler 已返回值 42、worker tree 清理确认；kernel succeeded 提交时间按同进程墙钟／单调钟对照约晚于等待返回 0.20 秒。等待快照中应用 Run 和 kernel execution 尚为 running，保留库中结果 outbox 仍为 pending，不能声称应用已消费结果。线程停在 settlement journal 的 SQLite 提交路径；留存记录没有确立锁错误。全量回归和类型检查与文档示例在时间上有重叠，但没有足够负载证据证明其导致超时。原检查保持失败，后续应在全量回归结束后按原 10 秒期限复验，不放宽断言。

进一步只读对照：候选 42 等待前快照记录 14223 个带探针的存储操作（包含连接、执行和关闭等，并非等量 SQL 查询）；候选 41 成功对照平均操作频率反而更高。可见主线程和子协调器轮询频率与相应休眠间隔相符，留存证据不能证明忙循环；现场有慢提交记录，但不能据此确定超时根因。存储事件只保留最近 2048 项，不能据此排除此前慢操作。

候选 42 完整回归在 17:58 CST 的只读两次进程与夹具观察间有读写、CPU 时间和夹具推进，记录为 `candidate42-progress-observation.json`；该观察不能识别确切当前测试、排除先前慢测试或证明套件通过。回归仍以实际最终结果为准。

候选 42 完整安装消费回归实际结束并失败：内层 2076 项、1499.735 秒，7 项失败、11 项错误、28 项跳过；外层 5 项、1559.615 秒，1 项失败。结果与原始输出分别为 `candidate42-tmpfs-regression.json`、`candidate42-tmpfs-regression.log` 和 `candidate42-consumer-evidence/sdk-observability-consumer-42sc2_iq/installed-suite/stderr.log`。当前尚未确认各项失败根因，不能将其一概归因于负载或把定向通过当作全量通过。Python 3.10、3.11、3.13 完整矩阵未启动；后续须先拆分诊断、修复已确认缺陷并保留原失败证据。

候选 40 的三个工作区失败用例在候选 42 完整套件中均实际通过。候选 42 失败项涵盖预算关闭、采样、取消诊断和子调用等不同路径；多项在原 0.1 秒控制准入期间或目标测试场景之前已超时，不能据此证明它们有共同原因。取消用例的业务取消成功，但关闭时有诊断事实未确认，未验证首次关闭后的恢复。同一安装包按原期限串行复验其中五个代表性测试，全部通过（`candidate42-targeted-retest.log`，29.899 秒）；该结果不改变原完整回归失败，也不证明其余失败已修复。

全量回归结束后，候选 42 按原 10 秒等待期限单独复验文档：572 个本地链接、4 个 README 示例通过、零跳过（`candidate42-docs-serial.log`）；先前并发检查的失败保留，超时因果仍未确定。预算关闭测试的一个断言原将过期预算映射出的当前单调时间当作历史截止时间，现改为在共同样本下核验进入、保留和恢复预算的工作／硬截止与 `deadline_monotonic` 转换，包含模拟过期样本，保留令牌、结果、容量与清理断言。定向测试通过（`candidate42-close-native-projection-test.log`），独立复核无阻塞项；模拟过期不是实际过期运行。该测试修改发生在候选 42 冻结之后，尚未进入新候选或完整回归。

完整回归中 18 条失败／错误记录对应 17 个测试方法（其中一个方法有两个子例失败）。候选 42 安装包按原时限串行复验这 17 个原始测试方法，全部通过、未跳过，耗时 43.058 秒（`candidate42-all-failed-retest.log`）；使用的是候选 42 冻结测试，不包含之后修改的预算断言。此结果表明原问题未在该次串行复验中复现，不证明原因或修复，也不改变完整回归的失败。

原完整回归的 17 个失败方法开始时间集中在同一单调时钟区间 1478372.088–1478660.367，跨度约 288 秒；从日志中的测试起始时间只能确定时间聚集，无法确定共同根因。此前文档检查的等待失败发生在该区间之前，不能把它与后续全部失败归为同时发生或据此证明因果。

候选 42 真实 OpenCode 工作区验收退出 1（`native42-workspaces/report.json`）：持久工作区写入、重开／重放以及原预算和清理检查通过；共享工作区的产物快照消费检查失败，越界拒绝与原预算和清理检查通过。失败原因正在按实际绑定、模型操作及验证脚本分别核对，不计作完整原生通过。另一项时钟水位测试的固定 `<7` 秒断言已按实际记录的工具截止时间计算上限，并以同一时钟样本检查四秒水位及恢复不增加剩余时间；原候选失败现场中正确上限约 7.851 秒，实测 7.307 秒。调整后的定向测试通过（`candidate42-child-clock-fix-test.log`），独立审查无阻塞项；极慢运行至窗口过期时剩余时间比较可能失去区分力。该测试修改尚未进入候选 42 或完整回归。

对上述原生失败的只读核对确认：生产者发布的原始字符串已绑定到消费者输入 `source` 字段；宿主随后修改共享文件，消费者实际读取到修改后的文件，但将整个输入对象的 JSON 字符串发布为答复，而严格检查要求 `source` 字段的标量值。原提示语存在歧义，现明确要求发布该字段的字符串值；独立审查确认其余检查、预算及期限不变。原失败保持失败，采用明确提示语的候选 42 真实原生复验已启动，结果另记。

明确提示语后的候选 42 真实模型工作区复验退出 0，`native42-workspaces-clarified/report.json` 的持久写入／重开／重放、共享快照消费、越界拒绝、原预算及原生清理检查均报告通过，宿主关闭完成。原始 `native42-workspaces` 失败保持独立记录。此验证限于 Linux x64 的所列正常路径，不覆盖崩溃、跨宿主竞争、Windows 或整个目标。

独立只读复核确认该次四个调用实际成功，消费者输入绑定生产者第 1 版原始标量，消费者读取到宿主后改文件并仍发布原始标量；四次原生清理回执身份匹配，预算与所有权释放记录完整。重放未产生新入口的结论由验证器报告的检查支持，安全报告未单独保存重放快照，故该部分不是独立重建的结论。

候选 42 安装包的真实 `silence` 取消场景退出 0（`candidate42-silence-timestamp/`），但首次保留公开观察的 worker 缺少可关联的清理注记 ID；只读核对器因此报告 inconclusive（`candidate42-silence-timestamp-check.json`），不能据此声称清理注记时间戳已被真实场景验证。后续只读查询及结果另记。

使用候选 42 公共 API、原存储绑定和相同 execution／attempt／fence 后续只读查询，匹配 worker 的 `persisted_at` 与 `process_cleanup` 注记 `created_at` 相同，且诊断页完整（`candidate42-silence-public-followup.json` 和 `candidate42-silence-public-followup-analysis.json`）。整体报告仍因采集器不再新鲜标记不完整；首次观察仍为 inconclusive。该结果只验证此场景后续持久化投影，不证明及时送达或其他执行均已收敛。

候选 43 已构建 wheel 和 sdist（`candidate43-build.log`）；冻结源码、候选 42 冻结源码及候选 43 安装环境的 141 个产品文件内容一致，候选 43 包含两项测试断言修正及验收提示语澄清。此次逐文件比较不涵盖测试／文档制品一致性，也不代替候选 43 的实际安装回归及原生影响评估。

候选 43 冻结测试及安装包实际执行了修正后的预算关闭和子调用时钟水位两个测试，2 项通过、无跳过（`candidate43-fixed-tests.log`）。这不是完整回归。

候选 43 的完整安装消费回归已启动，使用原有测试范围与内层 2700 秒期限；运行记录为 `candidate43-tmpfs-regression.json`，日志为 `candidate43-tmpfs-regression.log`。结果尚未产生，先前候选 42 的失败仍然保留。新增的负载与资源压力采样仅供事后诊断，不能单独证明任何失败的原因。

只读对照候选 42 与 43 的冻结树，排除生成的 `__pycache__` 后，仅验收记录、工作区原生验证脚本及上述两个测试文件不同；产品源码、六个类型消费者、依赖配置、README 示例和文档检查脚本均相同。候选 42 的类型检查和 README 示例可作为未变部分的历史证据，但不是候选 43 的实际执行；文档检查会扫描已变化的验收记录，因此其完整链接检查结果不能直接沿用，需对最终内容重新检查。

候选 43 完整安装消费回归结束并失败：内层 2076 项，1 failure、28 skipped，1352.576 秒；外层 5 项，1 failure，1412.749 秒。唯一失败为结果提交后中断并重开重放测试未触发注入异常，原始日志 `candidate43-tmpfs-regression.log` 和独立 consumer 内层日志保留。原始现场保存了待处理的确定结果；测试未保存恢复调用返回值，不能断定其失败原因。

候选 43 安装包上的原测试单独复验通过（`candidate43-settlement-diagnostic.json`），不改变完整回归失败结论。另一次受控诊断仅在成功保存待提交结果后人为延迟 120 ms，原测试同样未触发注入，调用返回明确的 `TimeoutError: completion recovery operation window elapsed` 与 pending（`candidate43-settlement-delayed-diagnostic.json`）；该人为复现证明一种可能机制，不证明原现场的具体原因。测试现仅对 pending 进行有界重试，保留每次恢复和 SDK 操作原时限、必须触发中断、准确结果和重开重放及单次业务调用断言，并保存重试报告；独立复核通过。受控延迟下修正后的测试通过（`candidate43-settlement-delayed-fixed-v3.json`）；中间一次诊断因测试变量未绑定失败（`candidate43-settlement-delayed-fixed-v2.log`），修正并保留。候选 43 安装产品配合当前测试的整个结算测试模块 19 项通过（`candidate43-settlement-module-fixed.log`）。这些结果不等于新候选包完整回归通过。注入时确认结果已提交且日志 pending，但注入所在的重试不一定是首次提交该结果的调用。

候选 44 wheel/sdist 已构建，冻结产品源码、候选 43 产品源码和候选 44 安装产品的 141 个文件内容一致；候选 44 冻结测试与安装包的中断恢复定向测试 1 项通过（`candidate44-fixed-tests.log`）。安装消费完整回归已按原范围和 2700 秒内层期限启动，记录 `candidate44-tmpfs-regression.json`，尚待结果；候选 43 原失败不被替代。

历史候选 35 与候选 44 的 `src/dispatcher_sdk` 冻结树逐文件对照，文件集合相同，仅 `agents/application.py`（工作区所有权快照与本地退役互斥）及 `execution_kernel/settlement.py`（匹配清理注记的 worker 持久化时间）两处产品文件不同。旧 `candidate35-acceptance-index.json` 未覆盖这两处变化，不能直接作为候选 44 最终验收索引。已有候选 42 的真实工作区和清理注记后续观察提供有限 Linux x64 证据；仍需按具体场景评估对 G02、G03、G09、G10、G12、G14–G16 中工作区并发、恢复、取消和清理结论的影响，不能将历史执行改写为候选 44 实测，也不能用正常工作区场景证明并发退役或其他平台。

两处变化的补充证据映射：`candidate42-workspace-settlement.log` 中，工作区协调测试通过受控线程交错验证账本记录／本地所有权退役与快照互斥；它不是并发 OpenCode 进程验证。同一日志中的清理注记测试检查匹配和不匹配的 attempt／fence 以及持久化时间；候选 42 的真实 silence 后续公开查询另验证一个执行的注记与持久化时间相等，但不能证明实时送达或提供商清理。真实工作区四次调用验证正常持久与共享路径（`native42-workspaces-clarified/report.json`）；没有单独留存重放快照，也不能证明原生并发退役或崩溃加共享工作区的组合。

当前工作树的中英文 Agent Wiki 各有一个完整默认值 JSON 表；只读解析并逐值对照 `agents/defaults.py` 中 `_DEFAULTS`，两表均一致。独立源码审查亦核对 Goal 的明确默认值和 YAML／Python 共同配置路径；此为文档与源码对照，不替代候选安装包行为测试或最终文档链接检查。

候选 43 完整安装回归的 28 个跳过项中，24 项要求原生 Windows（18 项 Job Object、3 项路径、2 项文件共享、1 项锁文件），4 项要求可选 YAML 扩展（CLI 私有凭据文件拒绝和 3 项 YAML 解析／等价测试）。这些 Linux 跳过不构成 Windows 验收；无扩展环境的 YAML 跳过需由启用扩展的对应执行证据补齐，历史候选的配置等价通过不能冒称候选 43 的四项执行。

候选 44 完整安装消费回归最终失败：内层 2076 项，1 failure、1 error、28 skipped，1352.731 秒；外层 5 项，1 failure，1424.405 秒。之前修正的提交后中断／重放测试在该完整回归中通过。新错误为 oversized SQL scalar 的一个 `parent_attempt` blob 子例在读取检查中报 `InspectionBudgetExceeded`；新失败为真实后代停止与外部预算采样测试返回 running 而断言期待 succeeded。原始结果和日志 `candidate44-tmpfs-regression.json`、`candidate44-tmpfs-regression.log` 及对应 consumer 的 `installed-suite/stderr.log` 保留；两项原因正在独立诊断，尚不能判断是否同源或认定已修复。

候选 44 的 oversized scalar 测试按原预算单独复验通过，记录在 `candidate44-two-failed-retest.log`；该日志中另一个测试因隔离解释器禁用了其必需的进程观测而未进入目标场景，整次命令退出 1。后代停止测试随后使用所需的非隔离入口、同一安装包和冻结测试单独复验通过，记录为 `candidate44-foreign-sample-retest-nonisolated.log`。两次定向通过均不改变全量失败，也不能证明原失败原因已经消除。

在候选 44 安装环境启用 YAML 扩展，并允许本地回环后，原来跳过的 CLI 私有文件拒绝和三个 YAML 测试共 4 项通过（`candidate44-yaml-skipped-retest-loopback.log`）。此前受限环境的同一执行中 CLI 因回环不可用而跳过，记录 `candidate44-yaml-skipped-retest.log`，不计为四项通过。此定向执行不改变全量回归失败，也不补足原生 Windows 跳过项。

后代停止用例已增加原始返回、结果与清理证据的留存，并在返回 running 时尝试受原执行截止时间约束的公开结果恢复；仍要求准确 execution／attempt／fence、原结果、真实进程清理回执及无逃逸。修订用例和同一处理函数的相邻用例使用候选 44 安装产品通过（`candidate44-publication-fixture-revised-v2.log`），但该次原始返回已是 succeeded，没有覆盖 running 恢复分支。此前一次定向执行在布置外部采样前遇到已有 sampling，且另一个测试名称错误，见 `candidate44-publication-fixture-revised.log`；原因及是否需处理仍待核对。另一次诊断人为维持采样并等待原始返回，2 秒内未等到返回，诊断断言失败（`candidate44-publication-held-sample-diagnostic.log`），不能用于证明运行中结果的恢复。新测试修改尚未独立审查或完成新候选回归。

对候选 44 的 malformed scalar 检查，完整回归中实际超时发生在读取畸形值之前；修订测试保留真实捕获的每次 0.1 秒上限，只对带原租约证明、明确可重试且无关闭异常的时限耗尽重试，最多三次、独立夹具窗口 0.5 秒，仍须观察到实际 `StorageIsolationError`。控制例检查全部超时、关闭异常和真实有效输入均不能冒充拒绝。文本 guard 在解码前检查；二进制 guard 在 SQLite 转为 Python bytes 后、交给完成时钟读取代码前检查，不能据此宣称从未物化为 Python 对象。后代用例另对已存在的采样只在原执行期限及独立一秒夹具窗口内重试明确的、无本方令牌的采样准入拒绝，并原子写入观测标记；首次标记实现因读写竞争失败，保留 `candidate44-failure-fixtures-v3.log`。上述两项修订及相邻后代清理用例在候选 44 安装产品配合工作区测试的四项定向执行中通过（`candidate44-failure-fixtures-v4.log`）；该次后代原始返回仍是 succeeded，未覆盖 running 后恢复。独立审查发现的清理期间序列化错误可能覆盖主错误，之后已补充保护，须按当前版本复验。上述均不改变候选 44 完整回归失败。

补充清理诊断保护后的当前测试与候选 44 安装产品，四项定向检查再次通过（`candidate44-failure-fixtures-v5.log`）。另在临时诊断副本中只对首次真实结果提交注入 `TimeoutError`：原始返回为同一 execution／attempt／fence 的 running，原清理回执为 `tree_reaped`，在原执行及 0.5 秒维护期限内读取到同一真实结果 succeeded；记录 `candidate44-publication-deferred-commit-diagnostic.log` 和 `/tmp/sdk-return-foreign-sampling-jz6fl0rk/evidence.json`。该次恢复调用的报告为空，不能判断结果提交由该调用还是其他已有恢复活动完成；注入点也不同于原完整回归的未确定采样错误，不能把它当作原故障复现或原因证明。当前工作区与候选 44 冻结测试不同，仍需新候选完整回归。

候选 45 已构建 wheel／sdist；其 139 个产品 Python 文件与候选 44 产品及候选 45 安装环境对应文件内容一致，三份受影响测试与冻结源码一致（`candidate45-product-parity.json`）；这不涵盖完整制品一致性。五项安装包定向测试通过（`candidate45-fixed-tests.log`）。第一次完整回归启动后，外层 5 项中隔离消费测试因新环境缺少 setuptools，在构建 sdist 前失败，内层完整套件未启动（`candidate45-tmpfs-regression.json`、`candidate45-tmpfs-regression.log`）。已为该环境补齐构建依赖，并使用独立可写 pip 缓存分别成功构建 sdist 和 wheel；初次 wheel 预检因默认缓存目录只读失败也保留（`candidate45-build-dependencies.log`、`candidate45-build-preflight.log`、`candidate45-wheel-preflight.log`、`candidate45-wheel-preflight-v2.log`）。这些环境预检和定向测试不构成完整回归通过。

补齐环境后，结构化预检再次记录 sdist 和 wheel 构建均退出 0（`candidate45-build-preflight-structured.json`）。候选 45 的第二次完整安装回归已启动，原测试范围和内层 2700 秒期限不变，使用独立证据路径 `candidate45-retry1-tmpfs-regression.json`；启动记录显示 running，尚无结果。按前两次完成用时估计北京时间 21:12 左右检查；启动不代表通过。启动器等待退出，不周期性刷新测试状态，开始／结束时记录资源快照，进程扫描及锁仍非全局互斥。

对 G06–G16 的只读证据复核：`native33-groups-rework/G06.json` 的真实工具负例包含未关闭组，歧义结果来自直接绑定解析检查，报告未列缺失输入；候选 44 完整套件的 `test_wait_failure_and_missing` 和 `test_unclosed_wrong_review_scope_and_missing_bindings` 分别在绑定层和存储层通过，但采用构造数据，不能替代当前候选实际调用组入口负例。G09／G10／G12／G14–G16 与工作区所有权退役及清理注记变更的组合仍须逐项评估；正常工作区调用、受控线程测试和单次清理后续查询不能证明真实并发退役或所有崩溃组合。G15 的 `native34-cleanup-unknown-v2/report.json` 对同一原始调用在故障前和两次重启后实际记录非零已消耗 1 次 Agent 调用、2 次模型推理及原 deadline；该结论只覆盖该清理未知场景，不涵盖全部预算和恢复路径。以上历史结果均不改写为候选 45 实测。

候选 45 冻结源码的双语 Wiki 导出器本地导出 25 页（`candidate45-wiki-export.log`，`/tmp/agent-control-080-candidate45-wiki/`），导出过程中校验源码内本地文件链接。所填 `release/0.8.0` 是未发布的本地分支名，导出不是远程发布，也不代表链接已在远程可用；完整当前文档检查、示例及最终导出仍须与最后交付候选核对。

独立只读检查候选 44 后代用例的原始 settlement 库，确认同一 `held-flush` execution／attempt 1／fence 1 留有原成功值及 `completion_time_unknown` 延迟记录，直接错误为 `budget_clock_sample_unresolved:sampling`，原采样期限为 0.1 秒；该记录后来显示原结果 succeeded、状态 recorded，两个预算检查点已确认。库位于 `candidate44-consumer-evidence/sdk-return-foreign-sampling-b5pgg_fb/kernel.db.settlements.sqlite3`。这解释了原始返回为何可能仍为 running，但现有证据没有确认是哪一个采样所有者导致拒绝，也没有确认是哪一个恢复活动提交了后续结果；不能把它直接归因于夹具随后持有的外部采样。此前人工注入的 `TimeoutError` 是另一种故障，不能视为原故障复现。malformed scalar 原错误发生在首个预算检查、畸形值读取之前，留存夹具没有足够计时信息判断时间耗在哪里。两项原始异常仍须保留和追查，新候选通过也不能单独证明其成因。

候选 45 的 sdist 包含本验收记录与 Wiki 页面，wheel 不包含这些文档。由于候选 45 构建后验收记录继续更新，其 sdist 内的记录不是当前版本；最终交付须在证据收齐后重新冻结并构建，核对制品和文档的一致性，并根据变化范围重验，不能把当前 sdist 当作最终文档制品。

G10 历史证据的独立复核：`native30-foreground-exact/G10.json` 和 `foreground-crash-marker.json` 支持所记录的跨 Run 续接、排队请求取消以及一次提交后／后续请求仍排队的故障窗口；这些只属于候选 30 和相应场景。客户端退出及恢复后精确回复在报告中主要保留为验证器布尔检查。`acceptance.json` 所记的增强验证器执行路径 `/tmp/agent-control-080-g10-reviewed-bundle/source/scripts/verify_agent_control.py` 目前仍可读取；其中相应断言检查子客户端成功退出以及恢复输出精确值，但报告未分别保留客户端 PID／退出记录和恢复原始回复。故障宿主的后代清理也记录为 unknown，后续已有调用级精确清理凭据不能证明崩溃宿主的全部后代或提供商侧已清理。后续需找回完整原始观察，或在当前候选实测中补记客户端进程退出、恢复回复和必要身份证据；不能将排队取消扩展成活动父子取消的证明。

候选 45 第二次完整安装回归实际失败：内层 2077 项，1 failure、28 skipped，1331.380 秒；外层 5 项，1 failure，1390.409 秒。失败为 `test_retained_admission_checkpoint_holds_slot_and_kernel_until_same_fact_commits`，在 0.05 秒原捕获窗口内测试未观察到夹具写入锁建立，未进入其预期的持有采样事实和关闭／恢复断言。原日志为 `candidate45-retry1-consumer-evidence/sdk-observability-consumer-4yovi88o/installed-suite/stderr.log`，原结构化结果 `candidate45-retry1-tmpfs-regression.json`，现场 `sdk-managed-stalls-ur2m9cbh/retained-admission-checkpoint.json` 的 trace 为空；它只说明该次 `_begin_budget_sample` 没有成功返回，并不证明函数曾被调用或未提交采样标记。失败前捕获的异常类型和消息未写入现场，故采样开始阶段的具体原因未知。该完整回归保持失败，须诊断并验证，不能继续把 Python 版本矩阵当作通过后的下一步。

使用候选 45 安装产品和冻结测试，原期限单独复验该方法通过（`candidate45-retained-admission-original-retest.log`，2.034 秒）。此结果只表明该次未复现，不能改变原完整回归结论或证明原始原因。已准备带最小采样入口／异常诊断的独立测试副本并经独立审查：保留原 0.05 秒窗口、目标断言和安装产品；插桩本身会消耗部分窗口，且开始采样失败时未单独证明标记是否持久化，运行结果须按此范围解释。

独立诊断副本使用同一安装产品通过（`candidate45-retained-admission-diagnostic.log`，9.882 秒；现场 `candidate45-retained-admission-diagnostic/sdk-managed-stalls-bfvnvn6l/retained-admission-checkpoint.json`）。该次开始采样返回并持有写锁，捕获到同一 token 的采样事实；首次关闭因实际数据库锁定未提交，释放后第二次关闭提交原 token。它覆盖了预期验证分支，但并未复现原完整回归的准备阶段失败，也不证明原失败的异常类型或时序。

候选 44 完整回归中的 oversized scalar 和后代停止两个失败方法，在候选 45 完整回归内均记录为通过；测试代码已在两候选之间修改，且候选 45 完整回归因另一方法失败，故这两项通过不能改写候选 44 的历史失败，也不能单独确认当时的具体原因。

针对候选 45 的准备阶段失败，工作区测试现仅在确认为无采样 token、无待处理所有权、无已建立写锁、且控制锁内无活动事务／采样标记时，允许有限重试明确的准入超时；每次实际捕获仍为原 0.05 秒，最多三次，0.5 秒仅限制新尝试的启动，并非操作硬时限。其他错误和所有权不确定时保留原异常，原同 token、锁、关闭和恢复断言保留；每次尝试记录证据。独立审查后，重试边界及实际持锁恢复两项使用候选 45 安装产品和修改后的工作区测试通过（`candidate45-retained-admission-revised.log`，2.141 秒）；新测试尚未进入新安装包完整回归，且这些验证不能确定候选 45 原始失败原因。

受控注入一次前置超时后再进入真实采样的测试失败（`candidate45-retry-realpath-injected.log`）：检查采样标记的查询被既有 SQLite 授权器拒绝，夹具按未知状态保留原超时并停止，真实重试路径没有进入。先前两项通过未覆盖真实检查分支，不能证明该重试路径可用。正在核对已有的受控只读接口；禁止绕过 SDK 保护，若不能安全验证标记则应移除该重试方案。

初版重试已暂时移除，工作区该测试恢复为候选 45 冻结版本。独立审查指出 SDK 现有 `_read_budget_floor` 可在有界准入下检查当前执行及祖先的采样保护，并在不可确认时拒绝；其范围不是全局所有采样。正在评估能否结合所有权状态安全用于夹具，尚无新重试通过证据。

使用 `_read_budget_floor` 的新工作区方案经独立审查，定向的边界与真实持锁恢复两项通过（`candidate45-retained-admission-floorproof.log`）；尚须验证首次明确超时后的真实重试路径。新诊断副本首次运行因缺少测试辅助文件在导入时失败（`candidate45-retained-admission-injection-floorproof.log`），未进入被测场景；已补齐同一冻结辅助文件并另存重试记录，原失败保留。

补齐辅助文件后的受控诊断通过（`candidate45-retained-admission-injection-floorproof-retry1.log`；现场 `candidate45-retained-admission-injection-floorproof-retry1/sdk-managed-stalls-lnbjdh_o/retained-admission-checkpoint.json`）。第一次人为注入精确前置超时，SDK 预算下限读取与所有权检查确认当前执行及其祖先可重试；第二次实际进入采样，建立锁和原 token，首次关闭因锁定未提交，释放后使用同 token 提交。该诊断验证了重试与真实路径的衔接，不是对候选 45 原始错误的复现；新测试仍须进入下一候选的完整回归。

已启动候选 45 安装包的 G06 补充原生负例：同作用域引用歧义、缺失引用产物、组成员缺少必需产物后拒绝下游。独立临时验证器 `/tmp/verify_candidate45_g06_negatives.py` 经只读审查及语法解析，运行证据单独保存在 `native45-g06-supplementary/`；预计北京时间 21:37 检查，启动不代表通过。这些场景不包含未关闭组负例或新一轮完整并发正例；工具观察器会增加同步记录开销，状态目录含运行现场，须保持私有。

上述 G06 补充运行最终退出 1，三个场景均失败（`native45-g06-supplementary/report.json` 及各自 `case.json`）。各场景的异常记录都显示临时验证器在等待失败时引用不存在的 `agents.AgentExecutionError`，引发 `AttributeError` 并遮蔽了原始异常；不能据此判断三个场景的实际产品结果。须修正验证器并保留原失败，再用独立证据目录重验；原记录不改写为通过。

对该次 G06 私有现场进行只读核对，三个 Agent kernel execution 均显示 `recovery_required`；两个调用组场景的 controller execution 显示 `failed/handler_error`，三个场景均无调用组记录和原生所有权记录。该结果提示真实执行未正常完成，但不能证明模型或工具已进入，也不能单凭这些状态判断根因或认定产品缺陷；原始被遮蔽的等待异常仍未恢复。

修正 G06 验证器的异常类、原始／关闭异常分别留存和记录内容白名单后，独立复核无具体阻塞项；已用独立目录 `native45-g06-supplementary-retry1/` 重新运行，预计北京时间 22:03 检查。原受限环境中的三个场景可见运行时 `PermissionError` 类型，但没有原始消息或堆栈，不能提前推断其具体来源；新运行启动不代表通过。

G14 独立证据核对：候选 30 的四个故障标记与各报告中的故障事实一致，分别覆盖 Agent 意图提交后、SDK 提交后、模型请求写出后及生产者结果消费／下游意图之间的受控窗口。SDK 提交窗口发生故障时 SDK 接纳回执**已经存在**，只是 Agent 存储尚未标记提交；原生 worker 被刻意阻挡，不代表任意活跃领取竞争。模型请求写出不能证明提供商是否执行；初次重放仍可处于 submitted，租约到期后才记录 unknown／隔离。崩溃宿主的后代清理未确认，与调用级原生清理凭据分开。以上仍是候选 30 的 Linux x64 历史证据；后续须评估工作区退役锁和清理时间投影变化对各窗口的影响，并在有交互的路径上补当前安装包真实崩溃／重启与原身份证据。

候选 30 到候选 45 的产品冻结树独立对照有三处 Python 文件变化：除候选 35 到 45 已记的工作区锁和清理时间投影外，`observability/journal.py` 在候选 33 增加了缺少同代完整关闭注记时的观测不完整标记。候选 30 的 G10／G14 原生场景使用默认私有工作区，不直接进入共享／持久工作区所有权锁分支；清理时间和关闭注记变化影响公开诊断的身份、时间及完整性解释，不能把这些诊断等同实际清理凭据。此次源码对照不证明当前包已通过：仍需当前安装包下检查共享或持久工作区退役与恢复交错、竞争写入的排除，以及真实崩溃重启后同代与不同代关闭／清理注记的公开观测。G10 还需保留客户端退出和恢复回复等原始观察；不能仅凭源码变化断言旧的每个崩溃窗口都受影响。

公开观测的补证范围已进一步核实：候选 42 的一次真实取消后续查询记录了同代清理注记时间与 worker 投影一致，但整体观测仍因采集器状态不完整；它不是宿主崩溃重启证据。`test_observation_driver_close.py` 覆盖缺失和错误代次关闭注记，但使用受控线程；`test_observability_native_acceptance.py` 有真实控制进程退出和继任者，却未检查原代次公开观测的关闭完整性及清理时间。补验应保留真实崩溃与原 execution／attempt／fence，重启后读取公开诊断：缺失同代关闭或注记页不完整时不得报告完整；仅有实际同代已确认清理注记时核对时间投影。没有注记时保持 unknown，不人为生成凭据，也不将采集器新鲜度与原生清理混为一谈。

G06 修正验证器的补跑已结束，退出码 1，三个场景均 failed（`/tmp/agent-control-080-evidence/native45-g06-supplementary-retry1/report.json`）。三个根调用均为 `recovery_required`，观察器未记录适配器入口和实际工具调用；缺失引用场景记录下游未创建执行及效果，但其上游没有成功执行，所以不能把它当成该负例通过。当前保留的等待异常显示 `AgentExecutionError`，其上游精确触发原因仍在只读排查；不能仅凭前次的 `PermissionError` 类型认定原因，也不能宣称模型请求已发出。原始失败与本次失败分开保留。

对失败现场的独立只读核对：三个 Agent 首个已保存的诊断均为 runtime 阶段 `PermissionError` 类型；调用组的后续 `ChildExecutionError`、controller 的 `handler_error` 和 `recovery_required` 是后续状态。持久诊断没有异常消息或原始堆栈，因此无法定位发生点。另一次独立、无凭据的环境探测显示当前受限执行环境对 `AF_INET` 本地绑定返回 `PermissionError`／errno 1，但不能由此倒推历史异常的确切来源。已获准在可访问本地代理的宿主环境启动同一补充验证器，使用新目录 `native45-g06-supplementary-retry2-host/`，预计北京时间 22:30 查看；启动本身不是通过证据。

共享／持久工作区崩溃验证的可行性调查：现有原生工作区脚本明确只覆盖正常关闭及重开；真实宿主退出会触发原生 guard 自行清理并提交凭据，而同状态 AgentApp 重开会立即尝试协调。因此直接杀宿主后观察不到旧 owner，可能是正常清理已经完成，不能据此断言排斥或恢复失效；反之也不能以 PID 消失作为清理凭据。若要稳定命中“旧 owner 仍在且清理未知”的窗口，需要经过审查的外部受控故障与可靠自动恢复机制；目前未进行这种干预，真实并发退役与崩溃重开验收仍未完成。

候选 46 已由当前源码和修订后的测试冻结构建（`/tmp/agent-control-080-candidate46/`）；源码、wheel 和安装环境中的 141 个产品文件逐字节一致，独立 sdist／wheel 预构建成功（`candidate46-build-preflight-structured.json`、`candidate46-preflight-product-parity.json`）。原准入／保留 token 场景和重试边界两项定向测试通过；另一次受控注入先制造精确的准入超时、再进入真实采样和原持有写锁路径，保留证据（`candidate46-retained-admission-prerequisites.json`）。这些结果没有解释候选 45 全量失败的原始原因，也不能替代候选 46 的完整回归。原生 G06 运行结束前不并发启动完整套件；当前台账继续变化，最终交付时仍需重新冻结包含台账的 sdist 并核对其内容。

候选 45 内层无可选依赖环境曾跳过 4 个 YAML／CLI 权限用例；候选 46 的独立已安装 PyYAML 环境在宿主 loopback 可用条件下复测这四项，4 项通过、0 跳过，见 `candidate46-yaml-skipped-retest-host.log`。这不改变候选 45 的全量失败，也不预设候选 46 完整回归的跳过数量；Windows 相关用例仍须原生平台证据。候选 45 与 46 的 141 个产品源码文件额外逐字节一致（`candidate45-to46-product-parity.json`），但旧包的原生执行仍须按实际制品与场景标明，不能改称在候选 46 执行。

候选 46 安装包完成一项受控 Linux x64 原生控制进程崩溃／重启诊断（`candidate46-native-crash-observation.log`，1 项、3.863 秒，通过；验证器为 `/tmp/candidate45-native-crash-observation-trer9y1r/` 的测试覆盖副本）。在真实工作进程进入、同代清理已确认而业务结果尚未持久化的故障窗口退出并重启后，公开只读观测保留原 `execution_id=native-execution`、attempt 1、fence 1；注记页完整且没有更多记录，同代 `process_cleanup` 的时间与 worker 投影一致。原代次没有 `driver_close` 时整体报告 `complete=false`／`driver_close_unobserved`。随后原有恢复和原预算／业务调用断言也通过；该测试在崩溃前额外保存了存储绑定，在恢复前增加 2 秒上限的诊断读取，结论仅适用于这个受控窗口，不证明所有崩溃点或强制关闭回执。原始诊断保存在 `candidate46-native-crash-observation/sdk-observability-native-bdqba251/`。

候选 46 全量与多 Python 版本启动器经过独立审阅，新增执行前后产品、wheel、测试树和运行器的逐字节基线检查，以及外层、内层、消费者和原 2700 秒超时证据核验；零失败但有跳过的结果单独标为 `passed_with_skips`，允许继续验证其他 Python 版本，同时保留每个跳过项及未覆盖状态。跳过解析器用候选 45 原始内层日志验证可准确识别 28 项，并对构造的身份歧义失败关闭。基线不检测期间改动后又恢复的瞬态，也不把本地 Linux 结果扩展到 Windows／ARM；这些启动器尚未执行完整回归。

宿主 loopback 可用条件下，候选 45 补充 G06 原生负例 `native45-g06-supplementary-retry2-host/report.json` 及三个 `case.json` 全部 passed，实际耗时约 166 秒。真实 coder 父子均进入适配器并成功、组关闭和等待返回；同范围下游因 `ambiguous` 失败且无命令／执行／运行时 effect／适配器入口。缺失可选产物的 producer 真实成功，下游为 `missing_input` 且同样无执行；组成员真实执行但未提交必需 `answer` 后，组调用返回 `agent_group_upstream_failure`，下游未接纳。该验证器报告把 `agent-run:` 前缀身份脱敏为 null，因此准确 run／problem 身份须以保留的私有现场另行核对；上述检查不能替代未关闭组、完整正例、其他平台或最终候选的全部验收。与此前受限环境下两次失败分开记录；本次通过不能反向证明先前 PermissionError 的具体来源。

候选 46 完整安装回归已启动，启动器 `/tmp/run_agent46_tmpfs_regression.py`、实际输出 `/tmp/agent-control-080-evidence/candidate46-tmpfs-regression.log`，预计北京时间 23:02 检查。运行启动不是通过；跳过和原始内层日志必须按实际结果核验。仍沿用原 2700 秒内层期限与完整测试范围。

G06 宿主补跑的独立只读复核：保留的控制存储中，歧义场景后存活子调用和下游同属 `agent-run:94d4cf99a0824eef9e82094106f2c145`；缺失产物场景下游属 `agent-run:5f7d4f3b72fb4c74a7580b69c8e28b25`；组缺失产物成员属 `agent-run:c18e745524ef4bab954de3e2a74a4eac`。上述可读记录的 problem ID 与 run ID 一致、轮次为 0；根记录在关闭后不再保留，所以与根完全同范围的判断依赖验证器执行时对原始行的比较，不能仅凭后存记录复现。三个现场分别保留 2／1／2 条原生所有权记录，均有与持久身份（含 attempt、fence、lease、effect 和期限）匹配的 `tree_cleanup=confirmed` 凭据；这不等于再次独立观察所有 OS 进程。验证器未留存初始预算快照和使用量／上限的完整对照，因此这些补充场景不证明预算未延长；同步工具事件记录也会影响时序。

候选 46 冻结文档的只读本地链接检查覆盖 83 个 Markdown 文件和 572 个本地链接，无缺失（`candidate46-local-links-only.json`）。此次没有执行 README 示例，也未检查外部地址或文内锚点；不能将该结果当作完整文档／示例验收。

候选 46 冻结 Wiki 的 25 个文件与候选 35 冻结 Wiki 的文件集合和内容逐字节一致；这支持将候选 35 的 Wiki 本地导出作为同内容的历史参考，不改变其执行制品，也不单独证明默认值语义或最终发布材料已验收。

候选 46 安装解释器和冻结的六个公共类型消费文件已从源码目录外完成 mypy 检查，Python 类型目标为 3.10，六项均无问题（`candidate46-all-typing.log`）。这是静态类型检查，不代表 Python 3.10 原生运行或完整旧 API 回归。

文档示例的只读验收核对发现：现有真实模型证据覆盖相似的单 Agent 调用和多 Agent 依赖图，但没有执行候选 46 文档中的原样配置、指令和公开 API。最小 YAML／Python 调用及文档依赖图仍须使用候选安装包和真实模型复现，核对实际输出、原始作用域、产物绑定与原生清理。CLI 没有任务提交子命令，前台宿主示例须结合公开 `AgentClient` 使用，不能宣称 CLI 独立提交任务。已准备临时验证器并进行执行前审查，尚未运行；历史通过结果不改称候选 46 实测。

候选 46 完整安装回归实际失败：内层 2078 项、1 failure、1 error、28 skipped，1379.729 秒；外层 5 项、1 failure，1439.558 秒。沙箱处置恢复测试中 `runtime.run_once()` 返回 `None`，调用方读取 `state` 时触发 `AttributeError`；原生分段输出观测测试在原等待窗口末的快照中看到了 1 条工具响应但没有看到所需 progress，断言失败。两者的原因目前未知，不能仅凭现象归因于负载或认定产品缺陷。原始日志和结构化结果为 `candidate46-tmpfs-regression.log`、`candidate46-tmpfs-regression.json`；运行前后冻结基线对照一致。失败现场独立保留于 `candidate46-consumer-evidence/` 和 `candidate46-tmpfs-retained/`。后续需分别核对原始证据、确认原因并修复，保留本次失败，不以局部复测覆盖完整结果。

独立对照本次与候选 45 的内层 `Test began` 记录，候选 46 的 2078 条与历史 2077 条加新增的一项测试在身份多重集上一致（`/tmp/audit_candidate46_discovery.py`）。该相对对照不证明两次均未遗漏共同范围，也不改变本次失败结果。

原生观测失败的原始现场进一步显示：`candidate46-consumer-evidence/sdk-observability-native-7ol_k1rl/progress-authority-new.json` 中，同一原执行的首次进度确认在原 0.1 秒窗口内反复尝试 `BEGIN IMMEDIATE` 后返回 `SQLITE_BUSY`／`database is locked`；公开进度回执因此为 `unknown`／`progress_confirmation_failed`。未确认进度时观测计数不增加，与失败快照一致；只延长快照等待不能使这次调用变成已确认。此前是谁持有锁、该次竞争是否说明产品缺陷仍未知；失败清理后触发的重放不构成原测试重放通过。

沙箱恢复错误的独立只读复核：`candidate46-consumer-evidence/sdk-sandbox-runtime-g8i1mywr/sandbox-before-cleanup.json` 表明首次执行进入 `recovery_required`，原处置 effect 经明确 `not_applied` 处理后 execution 回到 queued，随后第一次 `run_once()` 在约 13.7 毫秒返回 None；没有第二次领取或成功执行记录。`run_once` 允许在没有可领取工作时返回 None，但该次具体走了哪条领取分支没有留存，不能推断原因。需补充首次空结果现场、在原可信工作期限内做有界诊断，并核对同一操作身份及业务脚本未重复执行；后续复验不能解释原始空领取的成因。

观测分段用例受现有 `docs/EXECUTION_OBSERVABILITY_GOAL.md` 合同约束：保留两次原进度调用，第一次为 unknown 必须失败，不以重试将其变成通过。沙箱测试的修订在原可信预算内只对空领取等待，并在恢复前后比较业务调用记录；已通过独立只读审查，首次空返回诊断是返回后的非原子快照，诊断本身也消耗原预算。两项定向复验已启动，结果另记；候选 46 全量失败继续保留。

候选 46 安装产品配合当前修订测试的两项定向复验通过，2 项、5.821 秒（`candidate46-focused-retest.log` 和 `candidate46-focused-retest/`）。观测用例的原两次真实调用分别返回 confirmed／advanced=true 和 confirmed／advanced=false，修订未改变该用例。沙箱用例本次没有出现空领取，因此未覆盖新增的空领取诊断及重试分支，也未解释完整回归的原始空领取。这两项定向通过不改变候选 46 完整回归失败。

另用临时测试副本，在第二次实际领取之前恰好注入一次合成 None，验证沙箱测试的空领取诊断与有界续接：1 项、3.783 秒通过（`candidate46-sandbox-none-diagnostic.log` 及对应证据目录）。原 10 秒预算内保留首次空返回现场、原 execution 和操作身份，随后实际成功，业务 start／collect 记录没有增加。该注入不进入 SDK 领取过程，不是原始空领取的复现或成因证明。

候选 47 已冻结当前源码及修订测试，产品源码与候选 46 一致，构建 sdist／wheel 和离线预检成功，源码、wheel、安装环境产品内容一致（`candidate47-build.log`、`candidate47-build-preflight-structured.json`）。使用原范围和内层 2700 秒期限启动完整安装回归（`/tmp/run_agent47_tmpfs_regression.py`），按候选 46 的实际耗时预计北京时间 23:48 检查；启动不等于通过。此前候选 46 的两项失败与锁持有者／空领取原因的不确定性均保留。预检并非全新环境构建或平台 CI，最终台账仍须在交付前重新冻结并核对制品。

为后续真实验收准备了候选 47 的文档示例验证器及 G06 三项补充负例验证器，均已做独立只读审查，尚未运行。G06 验证器要求根身份、声明预算与绝对截止一致，并对实际进入适配器的调用核对 runtime effect 与同身份原生清理；已消费计数只覆盖 Agent 调用和模型轮次，不证明预留／未知计数或子调用独立计量。现有工作区崩溃验证方案需要私有故障插桩及可验证的守护进程有界清理，尚无可执行方案，不能将正常重开与合成所有权测试合并冒称真实崩溃排他性通过。

G17 历史资源验证器的附加审查发现：其子调用入口主动调用 `native_ownership.complete()`，该调用可能持久化清理凭据；原断言只按返回凭据数量判断，不能单凭该断言证明每份凭据是同一原执行的 `tree_cleanup=confirmed`，也不能证明回调前已持久化。候选 34 两个资源场景仍保留原报告中的 passed，但上述清理顺序和身份结论须另行核实，不能据此宣布完整 G17 通过。候选 47 补验正在准备增强证据，尚未运行。

候选 47 的 Linux x64 Python 3.10／3.11／3.13 串行安装包回归启动器已准备并独立审查，尚未执行；它要求先取得当前候选完整回归的成功结果，保留每项原超时、失败和跳过。回归有跳过时允许收集其他版本证据，但跳过项仍未验收；Linux x64 不代表 Windows 或 ARM。候选 47 的 G17 资源补验脚本也已审查，分别保存验证器主动处理回执前后的状态，额外证据仍标为 incomplete，不能当成整个 G17 通过。

候选 47 Linux x64 Python 3.12 完整安装回归结果为 `passed_with_skips`：内层 2078 项，0 失败／错误、28 skipped；外层 5 项全部通过，1402.123 秒。运行前后冻结基线一致，五类安装消费者场景标记通过；结果 `candidate47-tmpfs-regression.json`，日志 `candidate47-tmpfs-regression.log`。28 项中 24 项需原生 Windows，另 4 项因该独立消费环境没有可选 YAML 依赖而跳过；须用安装 YAML 扩展的当前包补验后四项，不能把 Windows 跳过计为通过。该结果不证明原始候选 46 错误原因或其他平台验收，也不能单独证明测试发现不存在共同遗漏。

候选 47 安装包在有 YAML 依赖、宿主回环可用的环境中补跑上述 4 项，4 项通过、0 跳过（`candidate47-yaml-skipped-retest.log`）；这不把原完整回归改写成零跳过。六个冻结公共类型消费者以候选 47 安装解释器和 Python 3.10 类型目标检查通过（`candidate47-all-typing.log`），不代表原生 Python 3.10 运行。内层测试开始记录与候选 45 的 2077 项加已新增的一项在多重集上匹配（`candidate47-discovery-comparison.json`），但仍不能排除共同遗漏。

候选 47 的 Linux x64 Python 3.10.22／3.11.18／3.13.18 安装环境已离线准备并校验产品文件一致（`candidate47-python-regression-environments.json`，均为 prepared_only，不是测试通过）。已启动三版本串行完整回归 `/tmp/run_agent47_python_matrix.py`，原范围及每套内层 2700 秒期限不变，遇到失败停止；预计北京时间 11 月 4 日 01:25 查看结果。启动不代表通过，不在预计时间前轮询或宣称进度；该运行不能替代 Windows／ARM 验收。

再次核对 G03／G04 的历史验证范围：候选 03 和候选 33 图验证的模型输入要求两项越界写入，但保留的工具失败诊断没有具体路径，不能由失败数量反推每个请求均实际发出并被拒绝；目录替换竞争使用安装包 `FileTools` 直接调用，不是模型工具桥上的竞争。G04 的根请求稳定重放也不能直接替代重复依赖事件的证据。已准备针对候选 47 的临时工具观察方案：仅记录固定合成路径与对应拒绝、原调用身份及服务端响应写入；其内部插桩可能影响时序，不能证明模型实际读取了响应，须独立复审后才可运行。方案本身不是通过证据，重复依赖事件仍须单独核对。

G16 合同要求多进程竞争、停止后重启、准确取消与清理，未知保持未知；未知清理同时叠加跨状态共享／持久工作区竞争是额外增强覆盖，不能写成合同明确要求的同一组合。历史缺失回执验证在原生 guard 报告清理返回真后人为扣留回执，覆盖同一状态目录的两次恢复和隔离，不证明真实清理失败或外部状态工作区围栏。候选 47 的临时原路径验证包装已准备但未运行。独立审查发现其沿用的进程监督器在异常兜底时仅固定子进程身份、未固定完整父链，存在父进程 PID 复用导致误信号的风险；须先修复并核实有界清理和身份，再考虑运行，不能假设成功路径零信号足以消除异常路径风险。

工作区监督器已按独立审查改为只向存活监督器的直接子进程发送带 pidfd 的信号；更深后代等待 subreaper 接管后再处理，未知或超时仍保留监督责任。该修订依赖正常 Linux 进程亲缘与子收养语义，不保证处理特权干预或逃逸；它尚未进入候选 47 冻结脚本，尚需用多代收养、观测失败和原有监督器自测验证后，才能用于后续原生验证。七秒截止后的不完整监督可能继续存活，不能称整个清理有硬时限。

进一步审查发现，旧监督器在启动后才读取控制方 PID；若控制方在该读取之前退出，监督器可能把新父进程误认为控制方，未启动清理。工作区两处原生验证启动器现于启动前固定自身 pidfd 并传给监督器，监督器核对原父身份、启动前及运行中检查存活；自测的修复门目录也在监督器仍存活时保留。独立源码审查未发现新的信号目标问题，运行验证尚未执行。最后一次存活检查与启动子进程之间仍有不可避免的间隙；若控制方恰在此时退出，监督器启动后应经 pidfd 发现并清理，不能宣称子进程绝不启动。多代夹具须同步新接口，并补查启动前／运行中控制方退出；候选 47 旧冻结支持脚本并不包含上述修复。

按现有 CI 配置，G18 还需 Linux ARM、Windows x64、Windows ARM 各四个 Python 版本单元的当前包证据；Windows ARM 的 Python 3.10 按既有合同使用 x64 兼容运行。每个声明支持 OpenCode 的原生 OS／架构组合还须至少一次真实安装包核心场景。候选 35 的平台记录当时报告缺少已授权可用主机和远程 CI 授权；该记录为历史状态，本次没有重新探测主机可用性。中英文 Wiki 已修正历史监督结果、候选 47 带跳过回归和早期文件工具证据范围；文档更改尚未进入候选 47 的已构建 sdist，最终制品须重建并按变化范围复验。

G05–G12 验证器复核补充：调用组原生正例的并发断言只要求两轮中至少一轮重叠；历史报告如记录两轮均重叠，应以其实际时间事实为准，不能把脚本的布尔通过扩大为两轮必然重叠。G07 用诊断代码集合判断循环等待及权限拒绝，未将每项失败逐条对应调用参数和调用者；G11 断言旧读者读版本 1、新读者读版本 2，但不单独要求新读者也有版本 1 的实际读取记录。G10 历史增强报告中的客户端退出和恢复回复主要为布尔检查，崩溃宿主后代清理仍为 unknown。候选 47 的 G06 负例、G10 客户端证据及 G03／G04 补充验证器均已准备但尚未运行；验证器检查点和私有插桩的局限均须随实际结果记录。

G14 工作区交互补验的方案调查确认：使用两个独立状态目录和同一显式授权的持久工作区，可以观察真实持有者运行时对竞争者的排除；故障后原生 guard 可能先完成清理、重启宿主又立即恢复所有权，因此不能保证观察到“崩溃后且清理仍未知”的窗口。若未观察到必须记录窗口错过；不能通过杀死未经验证的 guard、伪造回执或修改 SDK 表制造结果。真实清理后、所有权退役前的定点故障也需要可靠的独立进程监督和 guard 身份／清理协议，目前尚无可安全执行的完整验证器；这项是对工作区变更交互的补充覆盖，不改写 G14 合同或历史候选 30 的四个受控故障窗口。

只读对照当前默认值注册表与中英文 Wiki：两份完整默认值块与注册表一致，所检查的最小 YAML／Python 结构对应。Wiki 已补充 `tools.network: true` 对 OpenCode `webfetch`／`websearch` 的权限含义，以及 instance 和任务 session 的 key／mode 准入约束；网络工具权限不代表操作系统网络隔离。这是源码与文档的静态对照，不是实际联网或当前候选完整 G01 验收；最终 sdist 和 Wiki 导出仍需包含并验证这些更新。

工作区后续审查发现并修改两处当前产品路径，均尚未运行验证：一是前台宿主若 HTTP 关闭成功但描述文件删除失败，仍应尝试关闭 AgentApp；HTTP 关闭失败时，socket／处理线程状态未知，保留应用与宿主锁，不伪称清理完成。异常聚合保留服务和关闭错误，描述文件仍在持锁时尝试撤回。二是新服务请求同时提供的显式 session key 与配置输入字段不一致时拒绝接纳；旧请求的精确重放仍按原绑定校验。该拒绝发生在请求接纳事务中，不证明此前未启动宿主或捕获配置。两项修改改变产品源码，不在候选 47 的冻结包及其正在进行的版本回归内；须独立审查、定向验证后重新冻结，并按影响范围完成安装包与原生复验，不能把候选 47 结果称为修改后产品通过。双语 Wiki 和源码文档中的依赖图示例也已补充独立文件名与导入，最终真实示例验收仍待执行。

前台宿主修复的独立审查还发现：失败的 HTTP 线程 join 不能靠第二次 `server_close()` 推定已完成；并发 serve、应用上下文自动 close，以及服务器绑定后至正式 serve 前的关闭竞争也须保留所有权。工作区修复正在扩展到完整所有权边界及未启动服务器的清理；异常优先级、原始错误链和线程退出均待复审及运行验证。不能把最初仅使用 HTTP 替身的检查当成真实处理线程的关闭证据。

后续只读审查又发现，直接关闭 HTTP 服务与已接受请求注册处理线程之间存在竞态：关闭线程可能确认清理后，服务线程才登记新处理线程。还需核对未启动服务经 `AgentApp.close(timeout=...)` 关闭时是否保留有界等待、HTTP 构造失败且自身清理失败时是否错误释放所有权，以及命令行安装信号处理器失败时已创建服务的清理。这些问题正在修复及复审，相关测试尚未执行；当前工作区不是可验收候选。文档示例验证器另已准备校验文档中 Python 调用的语法树和依赖图文件名，尚未绑定新候选或运行，不能当作示例已通过。

命令行信号安装修订经只读审查后，已在安装前记录旧处理器，并在关闭失败时保留原异常的既有原因；这些改动仍待运行验证。仍有明确限制：Python 异步异常若恰好发生在服务工厂返回之后、返回值赋给局部变量之前，辅助函数无法通过该变量关闭服务；进程捕获异常并继续运行时可能留下 socket 和所有权。现有测试覆盖的是进入受保护辅助函数之前的中断，并不覆盖这个赋值窗口；不能宣称任意异步中断均无泄漏。

处理线程启动失败存在更窄的未知窗口：本机 CPython 3.12 在线程已创建而启动事件尚未设置时可能收到异常，错误文字和事件状态不能证明线程没有启动。工作区当前选择封闭后续接纳并保留清理未知，避免后续线程登记时从标准库跟踪列表移除未知线程；该路径尚未运行验证。代价是即使真实原因是启动前的临时资源不足，也不能自动恢复接纳，故障恢复能力仍有缺项。独立审查发现标准库请求循环会吞下普通启动异常，工作区已补充传播原异常和撤回描述文件的路径，并准备真实连接的有界测试，尚未运行。清理未知时监听 socket、可能已接纳的 socket 和应用所有权均可能长期保留，即使处理线程随后完成也没有可靠的重试清理路径；测试夹具对已知注入场景的自行关闭不证明生产清理完成。其他 Python 版本和 Windows 的线程实现均尚未实测。

针对临时启动失败的恢复，正在研究隔离接纳线程与请求权限的交接方案：启动结果未知时，只有确认未授予请求权限才能安全撤销该请求；线程确已退出仍须另行证明。方案尚不是产品验证结果。另已准备可参数化的最终候选文档示例验证器 `/tmp/verify_selected_candidate_documented_examples.py`，并经只读复审：它核对准确包路径和示例文件名，但对外层回归报告只作所报告状态检查，不独立证明内层测试发现及结果。它尚未运行，不能代替完整回归或真实示例验收。

线程交接方案目前仅为 `/tmp/agent-host-gate-prototype/` 中的隔离草案，尚未合入产品或运行；多轮只读复审修正了请求所有权和错误链问题，但无法单凭取消请求权限证明异常启动的线程已退出，也未解决全部启动前资源不足的自动恢复。预启动线程池可以提高此情况下的可用性，仍不能把线程退出不明当成完整清理。当前产品另已修订前台宿主异常聚合，使被优先抛出的中断保留其原有 cause；该修订及配套测试尚未运行。

当前工作树的 Wiki 已重新本地导出 25 页至 `/tmp/agent-control-080-working-wiki-20261104/`，导出器同时检查 Wiki 内本地文件链接。按文档检查器相同的路径规则另做只读检查，覆盖 84 个 Markdown 文件和 572 个本地链接，未发现缺失。导出引用的 `release/0.8.0` 只是本地分支名，未发布到远程；这不是最终候选包的文档证据，也不检查外链、锚点或运行示例。最终冻结后须重新导出并核对。

G07／G11 最终候选原生补验脚本仍在准备和独立复审，均未运行。G07 历史原生场景的自等待只能证明单节点等待环；多 Agent 动态等待环目前有合成适配器测试，另有真实 OpenCode 双节点方案，尚无真实运行证据。G11 补充观察需严格区分 JSON 布尔和整数，并将调用参数、调用者、知识版本及错误逐项关联；观察 SDK 内部分发结果不等于证明客户端收到了响应。两份脚本均需在执行前绑定可信候选与验证器、保护私有数据并保留中断和清理错误；SDK 清理回执也不能替代独立操作系统进程树观察。

前台宿主另发现线程对象构造失败时，旧顺序已占用一个并发名额却没有归还。工作区现在线程构造及 daemon 配置完成后才获取名额；获取名额后的注册和启动异常仍按清理未知处理。该修改经局部源码独立审查，新增测试覆盖构造失败后的完整容量及后续处理，但测试尚未运行；它不解决线程已经尝试启动后的未知清理与自动恢复限制，也不在候选 47 内。

另确认宿主初始化先持有 AgentApp 锁、后生成令牌，若令牌生成失败，未返回的应用仍被注册并持锁。工作区已将令牌等准备移到应用分配之前，并在持有前台所有权及 HTTP 构造失败时尝试按原所有者清理；双重失败时保留两项异常及优先异常原有 cause／context。新增令牌失败、前台所有权已获取但调用报错，以及嵌套异常的测试，尚未运行；应用工厂返回与赋值之间的异步中断窗口仍需单独处理，不能据此宣称构造期间所有中断均安全。

本次只读环境检查显示当前命令环境为 Linux x86_64，PATH 中发现 Docker 客户端，未发现所查询的 QEMU、Wine 或 virsh 命令；只读 Docker 信息查询返回本地 socket permission denied，不能由此判断其他命名空间或授权主机的可用性。当前检查不能提供 Linux ARM、Windows x64 或 Windows ARM 的原生验收证据。

本轮源码审查还发现，AgentApp 已打开 Orchestrator 后若资源恢复等后续初始化失败，旧路径可能未关闭它就释放宿主锁；已打开的内核连接是确认风险，不能据此推断构造本身启动了工作线程。工作区现集中处理构造失败：先撤回已提交的同一宿主路由，再关闭已返回的 Orchestrator 和其他拥有的资源，最后释放锁；若打开过程或清理结果未知，未完成对象单独保留且不作为可运行宿主。当前保守处理会使所有没有返回 Orchestrator 的打开错误保留锁直到进程退出，即使其中有些错误实际发生在资源分配前；它不提供自动重试。该改动和前台 HTTP 的 pre-socket 准备失败处理已经局部源码复审，仍待运行测试；打开函数内部的部分失败、任意异步中断及进程终止后的恢复不由静态修改证明。

候选 47 的 Linux x64 Python 版本回归已结束并失败：3.10.22 的安装消费者内层测试超过原 2700 秒期限，外层 5 项中 1 项失败、耗时 2764.767 秒；3.11.18 和 3.13.18 按失败即停止的设置未执行。末尾记录的测试在超时前约 3 秒才开始，未产生结果，不能认定该项卡死；总耗时原因仍待分析。外层证据为 `/tmp/agent-control-080-evidence/candidate47-python-complete-regression.json` 和 `candidate47-py31022-complete-regression.log`，内层完整输出见下一段。此前 3.12 的结果仍只适用于候选 47，不能证明此后修改的当前工作树或最终包通过。

更正之前只找到尾部输出的报告：内层完整输出另外保存在 `candidate47-py31022-consumer-evidence/sdk-observability-consumer-a0oekxqn/installed-suite/stderr.log`、`stdout.log` 和 `command.json`。内层超时前已有 10 条即时测试失败或错误记录，并有一次 120 秒线程堆栈转储；因此这次不能仅描述为总时限超时。内层没有最终汇总，失败逐项原因与实际完成数量仍待核对；末尾刚开始的测试仍不能据此认定卡死。

完整日志中有 1201 条测试开始记录和 1200 条完成耗时记录；测试超时前已记录的 10 次失败／错误涉及控制工具、调用者容量、取消、返工、技术重试、工作区、取消证据、子结果及生命周期清理。多个用例耗时数十秒，最慢的组协作测试约 134 秒并产生了 120 秒线程堆栈，随后该项结束。相比候选 47 的 3.12 回归，3.10 运行中大量同名用例较慢，但前者使用默认文件系统、后者使用临时内存文件系统，Python 版本与文件系统均不同；现有证据不能将原因归结于任一因素。完成耗时记录数量不等于通过数量，最终汇总不存在。

其中三项非 Agent 失败已核对原始异常：取消权限已改变后，原 1 秒预算内未能持久确认取消阶段；子结果测试的准备阶段耗尽原 0.5 秒预算，未达到其目标断言；生命周期测试的处理器结果虽成功，清理交接却记录为 unknown 并缺少 `process_cleanup` 阶段。它们分别需要按原执行身份和期限诊断，不能把结果成功或取消状态替代清理确认，也不能仅凭超时推定系统负载或 Python 版本是原因。

工作区写锁失败已缩小范围：候选 47 的 Python 3.10 安装包在默认文件系统和 tmpfs 上分别单独复现原测试同一提前完成断言（`candidate47-py310-workspace-fs-{default,tmpfs}.log`），独立真实 SQLite 锁竞争显示异常为 `OperationalError: database is locked`、无 sqlite_errorcode；旧工作区分类为非竞争，已有通用分类识别为竞争（`candidate47-py310-real-busy.log`）。原始全量日志未保留该 worker 的异常，因此不能证明它与此复现完全相同。当前工作区已复用通用精确分类，沿用原 deadline 和只在事务开始前重试的策略；相同取消测试及分类负例在 3.10／3.12 均通过（`current-py310-workspace-busy-targeted-retry.log`、`current-py312-workspace-busy-targeted-retry.log`）。首次 3.10 新负例因该版本缺少 `sqlite3.SQLITE_CORRUPT` 常量而失败，已按 SQLite 代码数值修复测试并保留首次日志。这些均为源码或候选 47 定向证据，不代表最终安装包已验收。

对底层 `Orchestrator.open_sqlite` 的只读审查确认，当前异常没有携带所有资源清理完成的可靠凭据；Runtime 构造位于工厂的清理处理之外，部分构造失败并未确认 executor 清理；Runtime 返回后若编排器构造失败，工厂尝试关闭 Runtime，但关闭失败只在部分 Python 版本添加注释。不能按异常类型判定资源安全，也没有证据证明特定失败实际泄漏线程。需要定义分阶段所有权和清理确认、保留原始及清理错误，并据此恢复安全的初始化失败重试；即便资源关闭，已写入的数据库内容也可能保留。

当前源码的 AgentApp 构造清理定向测试运行了 5 项，均通过，日志 `/tmp/agent-control-080-evidence/current-initialization-cleanup.log`；覆盖真实已返回 Orchestrator 的关闭、失败时所有权保留、关闭中断的异常优先级、路由注册后失败和打开结果未知。该结果不覆盖未返回的底层部分构造资源，也不代表安装包或完整回归通过。

当前源码的宿主关闭、命令行信号和会话绑定定向测试在本机回环可用环境中运行 48 项，全部通过、无跳过，日志 `current-host-cli-session-targeted.log`。日志还包含两条未关闭 socket 的资源警告：其中一条连接信息与前面的故障注入测试一致，另一条的具体来源尚未证实；两处测试夹具已补充在确认处理线程退出或注入已知启动前失败后关闭对应请求，尚待独立复审和定向复验。不能因测试通过认定警告已解决，也不能据此改变产品在真正未知时保留 socket 的策略。

当前进程监督器自测通过，覆盖后代进程和观测错误时的处置（`current-supervisor-self-test.log`）。扩展的四场景模拟在首项失败（`current-supervisor-synthetic.log`）：日志记录的同一直接子进程在退出前收到重复 SIGKILL，夹具原先要求每个 PID 恰好一次、严格顺序，故拒绝结果；该假设需独立核对。记录的监督器结果为 cleanup_confirmed，但原夹具在执行后续独立 pidfd 退出断言之前失败，因此本次不算扩展场景通过，也不证明其他三个场景已运行。

独立审查确认，多次向尚未退出的同一直接子进程发送信号符合监督器当前循环，后代也可能同时被接管；修正夹具后保留对准确子进程集合、直接父关系、信号类型及各 pidfd 退出的检查。重新运行的多代接管、观测失败、工作前控制方退出和工作中控制方退出四个模拟场景均通过（`current-supervisor-synthetic-retry.log`）。这是 Linux pidfd 测试夹具的证据，不证明特权逃逸、跨平台或真实 Agent 故障恢复。

工作区另修订 `Orchestrator.open_sqlite` 中 Runtime 已返回并赋值后的失败路径：先保留确切 Runtime；编排器构造和关闭同时失败时保留所有权及两项异常，并兼容 Python 3.10 的错误证据。该修订不覆盖 Runtime 构造失败、返回值赋值前的中断或其他未返回资源，尚待定向测试和完整验收。

上述 Runtime 失败路径及既有便捷 API 的当前源码定向测试共 15 项通过，包含正常自有 Runtime 关闭、调用方注入 Runtime 的所有权以及异常优先级（`current-orchestrator-initialization-targeted.log`）；执行解释器是 Python 3.12，Python 3.10 的实际运行尚未验证。两处 socket 夹具修订经独立源码复查后分别定向复验通过，触发测试后垃圾回收未收集到 socket ResourceWarning（`current-host-socket-warning-diagnostic-retry.log`）；强引用仍存在的连接不会因此产生已收集对象警告，不能据此证明全部连接均已关闭。首次诊断因项目测试路径未设置而导入失败，日志 `current-host-socket-warning-diagnostic.log`，该次没有执行两个测试。

上述 Runtime 构造失败及关闭异常的 4 项定向测试随后用 Python 3.10.22 执行通过（`current-py310-orchestrator-targeted.log`）；它只覆盖合成失败路径，不改变此前候选 47 的 Python 3.10 完整安装回归超时结果。

已赋值的 SQLite 连接初始化失败现尝试关闭并在清理未知时保留确切连接；参与维护的连接在退出维护参与权时保留确切回执，退出结果未知时不自动重复退出。独立审查确认，回执对象仍在不代表被中断的释放操作一定保留了操作系统锁。连接关闭及既有存储兼容性定向测试在 Python 3.12 和 3.10 各 13 项通过（`current-storage-close-py312-targeted.log`、`current-storage-close-py310-targeted.log`），含真实文件的维护排斥和跨线程关闭失败。连接获取、参与权获取和返回赋值之间的未知窗口、未返回 Runtime 的所有权及完整回归仍未解决。

工作区写锁修复补充了真实 SQLite 竞争验证：持锁方在原期限前释放时允许原请求接纳，持续持锁至期限时拒绝且不创建所有权，观察到竞争后取消也拒绝且不创建所有权。当前源码在 Python 3.10 和 3.12 上各三项均通过、无跳过（`current-py310-workspace-writer-cases.log`、`current-py312-workspace-writer-cases.log`）。这仍是定向测试，不替代最终安装包回归。

候选 47 的 Python 3.10 技术重试历史失败保留了详细证据：执行在两秒原期限内未到达适配器或预启动故障边界，最终在 `entry_authority` 处超时；不能据此断定重试逻辑有错，也无法从现有记录确认启动耗时原因。取消子任务用例的捕获显示父任务和兄弟任务正在执行、子任务仍在队列中，采样时应用锁忙；一次采样不能证明锁饥饿、死锁或子任务未被领取的原因。生命周期用例的业务结果成功，但立即重新打开的日志缺少清理与处理结果阶段，同时有清理交接失败阶段；原临时数据库未保留，不能区分异步记录延迟、回调缺失和交接失败，也不能推定操作系统清理成功或失败。原始完整回归日志及其失败状态保持不变。

候选 47 已安装包在 Python 3.10 上按相同两秒预算单独复现技术重试用例，仍在 `boundary_reached` 断言失败（`current-py310-original-retry-reproduction.log`；该次运行 1 项、失败 1 项）。这次适配器已进入一次，但未到预启动故障边界；记录没有 native operation，执行截止后 runtime effect 为 indeterminate，不能假设操作已安全中止。与历史全量运行中的零次适配器进入不同：新记录里创建调用到创建 Kernel 命令约 0.97 秒，effect 准备时距原期限约 0.19 秒；这些时间点本身不证明单一慢点或重试实现正确。详细执行身份和时间保存在 `current-py310-original-retry-reproduction/sdk-prelaunch-deadline-failure-32vsy_x1/evidence.json`。需保持原期限和结果继续诊断。

源码审查发现 Runtime 服务启动在部分失败后再次调用可能覆盖先前的后台线程引用，或因子协调线程对象已赋值而误判启动成功。工作区加入一次启动尝试的保守状态：启动结果未知时拒绝再次启动，避免经该入口覆盖已记录的线程。注入真实线程先启动再抛错、以及协调线程启动前抛错的定向测试在 Python 3.10／3.12 上各两项通过（`current-py310-service-start-failure.log`、`current-py312-service-start-failure.log`）。前者验证原协调、采样及结算线程退出；后者的生产关闭路径因等待未启动线程而报错，测试保留原 Runtime、线程及目录，不能称为自动恢复或清理成功。线程返回赋值窗口、懒启动内部资源和独立的通知桥启动路径仍需处理；该保护不在候选 47 安装包内。上述通过使用的夹具随后按审查意见修改，修改后的夹具须重新运行。

对同一 Python 3.10 候选安装包的技术重试用例加时间标记后再次失败，适配器进入一次，`prepare_native` 抛出 `PermissionError`，未观察到预启动故障边界和 native operation，runtime effect 最终 indeterminate（`py310-retry-timeline-01/console.log`、`timeline.json` 及该目录下的 failure evidence）。该次调用创建至 Kernel 命令创建约 0.78 秒，effect 准备时距原期限约 0.22 秒；事件显示多个工作线程对 claim 的调用依次结束，但无足够信息将所有耗时归因于锁或某个线程。标记只记录异常类型而非内容，不能将该 `PermissionError` 指定为某一权限条件；进程内插桩会扰动调度，工作线程静止和时间线完整性均未证实。此次运行前以直接内容比较确认已安装的 141 个产品文件与候选 wheel 相同、两个相关测试文件与候选 sdist 相同；这不等于当前修改后产品的安装包验证。

修改后的服务启动故障夹具在 Python 3.10 和 3.12 各两项通过；另在 Python 3.12 运行既有采样／结算存储关闭测试一项通过（`current-py310-service-start-failure-retry.log`、`current-py312-service-start-failure-retry.log`）。测试用例只覆盖所注入的两种线程启动失败以及既有关闭场景，未知启动后的实际清理与安全重试仍未完成，不能据此扩大为完整 Runtime 生命周期或最终包回归通过。

当前源码进一步修订了子服务、监督器和结算线程的启动与关闭所有权，并处理直接先导入监督器模块时的循环依赖。首次监督器定向运行在 Python 3.10／3.12 均因该循环导入在加载阶段失败，未执行测试（`current-py310-stall-supervisor-ownership.log`、`current-py312-stall-supervisor-ownership.log`）；该导入顺序问题在原 HEAD 中也存在。修订后各运行 23 项定向用例，各有 1 个错误：子服务 revocation 分支的合成活动记录缺少 `action` 字段，关闭报告读取时抛出 `KeyError`（`current-py310-service-lifetime-targeted-01.log`、`current-py312-service-lifetime-targeted-01.log`）。其余记录为通过，包括全新解释器两种导入顺序、真实通知桥阻塞时的文件存储保留与释放后关闭，以及部分启动和线程池关闭故障；该结果不是整组通过，也不是最终安装包或完整回归证据。夹具错误及独立审查发现的失败路径清理问题正在修正。

补足合成记录字段并加强夹具清理后，重跑同一范围：Python 3.10／3.12 各 23 项通过（`current-py310-service-lifetime-targeted-02.log`、`current-py312-service-lifetime-targeted-02.log`），耗时分别约 13.2／12.7 秒。真实通知测试使用手工领取的执行及文件存储，不证明处理器分派或临时目录清理。独立审查随后发现，线程池回调中断夹具的失败分支仍可能漏查迟启动的工作线程；该夹具还需修订并复验。启动或关闭结果不明时，产品可能持续保留存储，不能声称必然自动恢复。

该夹具随后增加对已创建线程池工作线程的逐一退出确认；修订后的回调中断用例在 Python 3.10／3.12 各单独通过一次（`current-py310-interrupted-callback-fixture-retry.log`、`current-py312-interrupted-callback-fixture-retry.log`）。它不能证明所有故障或平台下清理均可恢复。

候选 47 的 Python 3.10 技术重试原用例另做了一次带插桩诊断：普通执行环境在测试准备阶段因本机回环绑定被拒绝而跳过（`py310-retry-timeline-02/observation.json`）；随后在允许本机回环的环境中运行一次，仍使用原两秒业务预算，结果 1 项失败、无跳过（`py310-retry-timeline-03/observation.json`，原始日志和失败记录保存在其仅当前用户可访问的 `raw/` 下）。该次适配器进入 1 次，异常来源定位至已安装候选 `application.py` 的原生启动授权结束检查；没有记录到 native ledger prepare，也没有到达预启动中止边界。按测试开始时的墙钟和单调钟对应估算，进入 prepare 时距原期限约 20 毫秒、进入授权检查时已超过约 132 毫秒；两次事件之间包含应用锁等待，但这些时点不能证明唯一慢点或精确墙钟比较结果。检查同时涵盖取消及剩余工作预算，保留行中的 `cancel_requested=0` 不能排除其他条件。原结果仍为 effect indeterminate、执行 recovery_required，不允许据此重放或声称技术重试已验证。插桩会扰动时序，测试自身忽略普通关闭异常，安装路径核对也不证明本次代码字节的可信来源。

中英文 Wiki 与源码指南已补充新服务请求同时提供显式 session key 和配置输入键时必须一致，以及 `new` 模式拒绝显式 session key；独立源码复核未发现与当前接纳及重放逻辑冲突。默认值注册表静态对照仍一致；这些文档变更尚未进入最终候选或完成导出验证。

当前源码的既有监督、观测关闭、结算及子服务关闭兼容测试在 Python 3.12 上运行 52 项、全部通过（`current-py312-lifecycle-compatibility-01.log`），约 74.5 秒；Python 3.10 同范围运行 52 项，1 项失败，约 86.9 秒（`current-py310-lifecycle-compatibility-01.log`）。失败发生在真实 SQLite 连接持有夹具准备阶段，预期业务结果为 `succeeded`，实际读取到 `running`，尚未进入目标关闭断言；原因待诊断。这些是所列模块的定向回归，不是最终安装包或整套回归。

该失败对应的原始存储记录为 `/tmp/sdk-runtime-observation-cleanup-6i0holgl/storage-evidence.json`：观测库和结算库分别出现锁竞争，保留的最终 Runtime 记录显示关闭、结算和服务清理完成，但没有记录 `run_once()` 返回 `running` 的直接原因。观测事务由夹具刻意持有；不能据此断定它导致了另一数据库的竞争或证明产品故障，目标关闭行为在该次并未运行。同一用例按原超时单独重跑通过，耗时 1.756 秒（`current-py310-observation-close-original-retry-01.log`）；单次通过不能覆盖先前整组失败或解释其根因。

G07 权限拒绝与调用者绑定的补充观察草稿位于 `/tmp/agent-control-080-evidence/prepared-g07-permission/verify_permission.py`，未运行。独立审查发现异步回调登记和异常处理仍无法证明观察透明与完整，当前草稿固定报告 incomplete，不能用作验收；真实权限调用的准确身份、参数及拒绝对应证据仍待安全取得。

进一步只读核对该次失败的原始结算记录，`original` 的第 1 次执行／fence 1 最终保存的是原处理器成功结果。SDK 合同允许完成发布尚未确认时返回 `running`，测试夹具原先直接要求该快照为终态，因此现改为在原观测事务十秒持有窗口内，借助完成维护读取同一执行代次，且仍要求原成功值和原关闭断言；不重新提交或调用处理器，未延长原窗口。修订经独立源码审查；原关闭用例与同代次读取检查在 Python 3.10／3.12 均通过。同一命令第三个测试名误写，导致加载错误（`current-py310-observation-fixture-02.log`、`current-py312-observation-fixture-02.log`）；按实际名称单独补跑的不同代次拒绝负例两版本均通过（`current-py310-observation-generation-negative.log`、`current-py312-observation-generation-negative.log`）。这些结果不说明原失败走了哪个返回分支；所涉模块重跑结果见下文。

Python 3.10 所涉模块重跑共 54 项：原观测关闭用例通过，另一项 `test_logical_watermark_rollback_cannot_restore_postexpiry_success` 失败，原结果记录为 `timed_out` 而断言要求 `succeeded`（`current-py310-lifecycle-compatibility-02.log`，约 83.9 秒）。重跑仍为失败，具体原因待结合该执行的原始证据诊断。

该失败对应 `/tmp/sdk-runtime-settlement-rr9cuhqo/storage-evidence.json` 及同目录保留的结算库。只读核对显示原执行第 1 次的结果为 `handler_timeout`，对应预算检查点已超过原期限，收据为 superseded；测试此前关于不能接受过期成功的断言已通过，但要求保留的原结果为成功这一条件未满足。夹具在恢复墙钟之后、释放处理器之前释放预算锁，理论上预算观察可能读到已持久化的较高逻辑水位；现有记录没有证明具体采样顺序，不能据此认定产品缺陷或将该失败归因于真实运行耗时。下一步需保持原时间预算记录实际采样和处理器返回顺序。

该用例的单次时序诊断首次因测试目录未加入导入路径而退出，未运行测试（`watermark-diagnostic-01/launcher.log`）；修正启动路径后按原预算运行 1 项并通过、无跳过（`watermark-diagnostic-01/run-44fxk9a6/trace.json`）。这次轨迹记录到预算监控返回后提交水位见证，随后处理器返回并捕获完成时间；插桩改变调度，且这是另一次执行，不能证明上次失败的采样顺序，也不能覆盖 54 项回归的失败。轨迹及原始诊断材料保存在私有目录中。

独立源码审查确认，延长测试持有预算锁并不能保证处理器先产生结果：监控获取锁超时后仍会读取和推算已有预算；真实期限也可能先到。可以在原有期限内增加交接观察，但它仍可能错过期望的真实结果，尚不能作为确定性修复。当前保留原断言和失败记录，不把单次通过称为修复。

候选 47 的 Python 3.10 返工测试 `test_exact_member_replay_feedback_and_second_round` 历史失败另经只读核对（`candidate47-py31022-consumer-evidence/sdk-rework-route-failure-pzzfcv9g/evidence.json`）：采集时根调用为 `recovery_required`，其第 1 次运行效果为 indeterminate；三个 coder 已成功，plain reviewer 的执行仍在运行，夹具 `seen` 为空，尚未记录到返工观察。根诊断中先记录 `ToolCleanupUnknownError`，之后记录 `ChildExecutionError`；候选工具服务在关闭时若线程、未完成调用、定时器或服务停止等任一条件未确认，可产生该清理未知。原证据没有标识具体未完成条件，也不能确认是否掩盖了更早的异常或操作系统清理最终失败；当前源码和最终安装包的表现不能由这次历史记录推定。

当前源码审查另发现工具服务关闭未知与适配器异常同时发生时，异常对象在内存中仍有原始上下文，但运行效果记录未保留其类别。工作区现保留清理未知作为主要错误、将固定的受限类别写入错误文本以供效果记录，不写原异常文本；诊断写入失败保留为内存错误并继续抛出清理未知，不能保证记录成功。该修订未证明历史返工测试发生了双重失败。Python 3.10／3.12 的三项上下文管理定向测试各通过（`current-py310-tool-cleanup-diagnostics-01.log`、`current-py312-tool-cleanup-diagnostics-01.log`），使用的是关闭替身；真实回调、运行效果和禁止重试的集成验证仍在准备。诊断写入期间的中断只保留在内存异常对象上，不保证立即传播或持久化。

G07 补充证据的只读研究发现，历史候选 30 保留的原生会话数据可提供具体调用参数、权限错误和对应根会话的 SDK 诊断；在已观察的数据中该错误调用唯一。历史原生库含未合并的 WAL，本次在内存重建可见数据且没有验证其完整性，因此此关联仅供设计验证器，不能当作最终候选验收。尚未找到候选 47 的该场景原生运行，最终候选仍须通过支持 WAL 的安全只读方式核验会话绑定、请求、错误响应和唯一性；原生会话内容可能包含敏感信息，不应直接输出。

补充集成测试在 Python 3.10 使用真实 AgentApp、工具服务和被阻塞的真实回调，注入合成 prelaunch 错误；两项通过（`current-py310-tool-cleanup-integration-01.log`，约 10.4 秒），确认该次回调未结束时只调用一次适配器、原执行代次的效果为 indeterminate，且诊断写入中断时保留清理未知。该测试没有真实原生 prelaunch 回执，不能代替 OpenCode 验收。独立审查发现该版夹具在自身清理失败时未保留准确异常对象，随后已修改夹具；修改后的运行结果须另记。

夹具修正并复审后，Python 3.10 和 3.12 各运行上述模块 5 项、全部通过（`current-py310-tool-cleanup-diagnostics-02.log`、`current-py312-tool-cleanup-diagnostics-02.log`，约 10.7／8.3 秒）。集成场景在释放回调后确认相应服务和应用关闭，诊断中断对象在内存中按身份保留，效果记录未包含合成异常的私有内容；结果仅覆盖受控的本机回调与源码，不证明所有清理失败可恢复、原始历史失败的原因或最终安装包行为。

后续独立审查发现，工具服务请求线程的 `start()` 抛异常时旧路径会丢弃该线程对象；但线程可能已启动或正处于启动交接中，不能以此确认清理。工作区现保留准确线程，且要求实际进入目标方法后才能结合线程退出状态撤销跟踪；如果未看到进入，保守保留未知，即使它实际上从未启动。该修改发生在上段测试之后，新增启动前／启动后异常的真实回环测试正在复审，尚未运行；不声称自动恢复未知启动或跨平台通过。工具服务和效果层对中断的传播仍有既有限制：当前优先保留清理未知／不明效果，中断未必向调用方立即传播。

进一步审查发现，连接尚未登记或关闭调用失败时也不能确认工具服务已清理。工作区现将接入交接记为待确认，登记准确连接后才解除交接，并在连接关闭成功后才撤销跟踪；启动和连接清理同时失败时尝试保留两个异常。该策略会在接入报错但无法确认是否已取得连接时长期保留清理未知，即使实际没有连接泄漏；这是一项可用性限制。修改已做源码复审，新增相关真实连接和故障注入测试仍未运行，异步中断和其他平台不能据此宣称通过。

上述五项故障注入在 Python 3.10 和 3.12 各运行一次，各 4 项通过、1 项清理错误（`current-py310-tool-worker-accept-01.log`、`current-py312-tool-worker-accept-01.log`，各约 6.1 秒）。失败发生于同时注入线程启动和连接关闭失败的场景：服务线程记录了第二次连接关闭异常，测试自身清理阶段的 `server.close()` 报清理未知。当前记录不足以确定具体哪个所有权条件未结束，也不能将该结果称为整组通过；正在按准确线程与连接状态诊断。

源码复核确认，服务停止信号可能早于服务线程真正退出；旧辅助线程只在停止操作返回时检查一次线程存活，可能因此永久保留未完成标记。该时序是前述失败的可能解释，原日志没有状态采样，无法证明实际原因。工作区改为分别检查停止操作与准确线程退出，并新增暂停真实服务线程退出的受控测试。修改后六项故障测试在 Python 3.10／3.12 各通过（`current-py310-tool-worker-accept-02.log`、`current-py312-tool-worker-accept-02.log`，各约 6.1 秒）；日志中的服务线程异常来自有意注入的连接关闭失败。未知接入场景按设计保留未确认所有权，不代表其自动恢复；这不是最终包或跨平台验收。

当前源码的工具协议和双重失败兼容模块在 Python 3.10／3.12 各 14 项通过（`current-py310-tool-server-compatibility-01.log`、`current-py312-tool-server-compatibility-01.log`，约 9.3／8.9 秒），包含真实回调和常规请求；这仍是本机定向回归，不替代全套旧 API、最终包或原生平台矩阵。

独立整体审查发现上述测试未覆盖两个额外所有权窗口：工具服务构造函数在返回前启动监听线程，若中途失败，应用尚未登记该服务；请求体读取计时器若启动后抛错，也可能在处理线程结束后继续存活。前者仍需修复和实际验证；后者工作区已在启动前登记准确计时器，并要求实际进入和退出后才能确认清理，相关测试正在复审。上述兼容测试均早于计时器修改，不能用于证明修改后的代码通过。

计时器启动前失败、启动后失败以及启动错误与清理中断同时发生的三项本地回环测试在 Python 3.10／3.12 各通过（`current-py310-tool-timer-start-01.log`、`current-py312-tool-timer-start-01.log`，各约 3 秒）。实际从未启动的注入对象仅由测试夹具按已知事实撤除；产品仍将无法确认的启动保留为清理未知。普通双重错误及启动后中断并未分别覆盖，工具服务构造所有权缺口仍存在。

针对服务构造交接，工作区现于创建服务前登记占位所有权；只有收到并绑定准确服务后，才可根据该服务的清理结果解除所有权。构造或返回交接不明时保留未知并阻止安全重试，即使实际没有创建资源也不能自动恢复。该修改尚待独立审查和故障注入测试；占位记录不持有构造函数内部未返回的准确监听器，不能据此宣称泄漏已清理。

构造交接的故障测试经过独立复审后，Python 3.10 和 3.12 各运行 1 项并通过（`current-py310-tool-startup-ownership-02.log`、`current-py312-tool-startup-ownership-02.log`，约 3.4／2.7 秒）。测试在真实本地服务完成构造后注入异常，确认创建前已经登记所有权、未进入适配器，原效果为 indeterminate；测试夹具仅在掌握准确服务对象的条件下完成清理，不代表产品能自动恢复未返回的对象。最初尝试使用错误解释器路径而未运行测试，失败输出保存在同名 `-01.log`。

独立审查还发现，应用当前先停止宿主并关闭运行时存储，再清理工具服务和模型代理；实际回调可能在宿主执行线程返回后继续访问存储。仅在应用层检查一次不能解决：仍在运行的执行线程可能随后登记资源，宿主协调线程异常退出也可能直接进入存储关闭路径。需要在宿主停止接收工作、排空执行线程之后、关闭存储之前确认所有相关资源的准确退出，并覆盖构造和线程启动交接不明；原关闭期限内无法确认时须保留宿主与存储。当前这项关闭顺序缺陷尚未修复或验证，前述构造测试不能证明整个关闭路径安全。

正在审查的宿主关闭屏障和线程交接修改尚未接入 AgentApp。独立执行的旧宿主测试有 4 项失败、1 项报错（`/tmp/runtime-host-legacy-review-20261104.log`），涉及启动或执行器关闭异常后的重试及清理预期；现有失败不能被新定向测试覆盖，也未修改原测试。注册工作线程的公开接口接受任意对象，不能在不知道调用方同步方式的情况下安全地统一插入线程入口证明；兼容合同及观察线程仍需设计和验证。模型代理的定向线程与连接故障测试通过，但构造交接仍未登记、关闭屏障未接通，不能声称整个关闭路径安全。

此后模型代理增加构造前登记；构造结果或交接不明确时保留占位所有权，纯配置校验仍在资源获取之前。执行异常与代理清理异常同时发生时保留两者，清理未知不被当作可重试的普通启动前失败。Python 3.10／3.12 分别运行 10 项代理定向测试并通过（`current-py310-proxy-ownership-01.log`、`current-py312-proxy-ownership-01.log`，各约 3 秒），包括真实回环代理、受控构造失败、线程启动故障、连接关闭故障及合成双重异常。这些测试不证明历史返工失败的原因、真实 OpenCode 的启动前回执、所有异步中断位置或最终安装包；宿主关闭顺序和既有回归失败仍待处理。

当前源码宿主相关四个模块在 Python 3.10／3.12 各运行 34 项，均为 4 项失败、1 项报错（`current-py310-runtime-host-review-01.log`、`current-py312-runtime-host-review-01.log`，约 10.2／9.4 秒），与前述旧行为冲突一致；新增的屏障与 join 定向项在两次运行中通过。四项旧断言依赖注入的线程启动失败确实没有启动，生产代码无法仅凭异常作此推断；另一项涉及协调线程尚未创建而执行器关闭失败，是否存在足够的未提交工作证明仍待核实。现阶段保留原断言和失败证据，不把任何一种判断替代完整兼容验收。

经独立复审后，相关测试现按启动结果未知保留准确线程、拒绝重复所有者和提前关闭进行断言，并保留线程构造失败后关闭也失败的独立覆盖。空执行器关闭失败场景目前同样保守保留运行时，属于可用性和异常恢复行为变化，不等同证明原先自动关闭合同仍然兼容。修订后的同四个模块在 Python 3.10／3.12 各运行 35 项通过（`current-py310-runtime-host-review-02.log`、`current-py312-runtime-host-review-02.log`，约 10.6／9.8 秒）。这是修改断言后的源码定向结果，不覆盖此前失败或证明旧 API 完整回归通过；宿主屏障尚未接入 AgentApp。

随后源码继续修改：调用所有权登记改为共同版本检查，生产者退出后重新检查资源；预启动重试额外检查观察线程和原预算；代理在构造时提前登记所有者，原生清理尝试保留多个错误。宿主在安装关闭屏障时，对协调线程创建前的启动失败改用保留的清理线程。以上新修改均发生在此前定向测试之后，尚未经修改后的定向回归或最终安装包验证。自定义适配器必须在获取资源或启动线程前登记，并保证已确认清理的资源不再重新产生作用；线程子类的退出目前不能按标准线程证明。监督观察线程仍在运行时，技术重试可能被保守拒绝。这些是当前实现边界，不能据此声称旧适配器兼容或 G16／G17 已通过。

后续复审发现并正在处理新的未决问题：Windows 监听器接收连接返回到登记准确对象之间，异步中断可能使已取得的端点未纳入清理证明；socket／socketpair 的获取交接也需核实。正常 Windows 轮询超时不能简单地一律视为永久清理未知，否则会破坏正常启动。宿主的有限停止等待在启动清理线程的 `Thread.start()` 返回后按期限等待，但若该启动调用本身阻塞，当前没有硬期限保证。以上是源码审查发现的限制，尚无最终包的跨平台验证。

当前源码的调用线程与资源所有权模块在 Python 3.10／3.12 各运行 15 项并通过（`current-py310-worker-ownership-02.log`、`current-py312-worker-ownership-02.log`，各约 1.1 秒），包括受控的生产者／子线程登记和真实本地套接字读取。最初受限环境运行均为 14 项通过、1 项因套接字发送 `PermissionError` 报错；原输出保存在同名 `-01.log`，随后使用允许本地通信的权限重跑。该结果只验证源码定向场景，不能证明屏障已接入、技术重试的完整真实执行、最终安装包或其他平台通过。

代理构造、网络线程和原生端点清理的四个源码定向模块在 Python 3.10／3.12 各运行 30 项并通过（`current-py310-proxy-ownership-02.log`、`current-py312-proxy-ownership-02.log`，各约 5.6 秒）。这些场景包含本地套接字与受控错误，Windows 接收交接仍未解决，不能由 Linux 或模拟 Windows 的结果代替。更新后的宿主四模块回归在 Python 3.10／3.12 各运行 44 项，均为 42 项通过、2 项报错（`current-py310-runtime-host-review-03.log`、`current-py312-runtime-host-review-03.log`，各约 12 秒）：一项测试夹具未传构造参数，另一项在宿主启动完成前停止而未满足其最终刷新断言的前提。正在修正夹具和同步条件，不能将该组称为通过。

修正上述两项测试夹具和启动同步后，同四个宿主模块在 Python 3.10／3.12 各运行 44 项并通过（`current-py310-runtime-host-review-04.log`、`current-py312-runtime-host-review-04.log`，约 15.8／16.2 秒）。该结果不替代此前失败记录，也不证明旧 API 全部兼容；关闭屏障仍未接入 AgentApp，启动调用本身可能阻塞的限制仍在。

Python 3.12 的监督及技术重试两模块运行 26 项，25 项通过、1 项失败（`current-py312-supervised-retry-01.log`，约 188 秒）。失败的原截止时间场景未到达测试要求的启动前中止边界：适配器调用一次、无原生操作记录，原效果在期限后变为不明确；保留证据 `/tmp/sdk-prelaunch-deadline-failure-mgc209fb`。调用效果开始时距原两秒期限仅约 0.33 秒，现有证据不足以确定调度负载或具体产品问题；不能据此证明中止后的重试约束。Python 3.10 同组达到原 200 秒进程限时并退出，未完成全组；输出 `current-py310-supervised-retry-01.log` 包含同一截止时间场景失败和一项监督场景失败，后者未输出完整错误栈。Python 3.10 的截止时间证据保存在 `/tmp/sdk-prelaunch-deadline-failure-zd9a8mni`，该次效果开始时距原期限约 0.20 秒。两组并行执行过，不能凭这一事实认定失败原因。

截止时间场景随后按相同两秒预算、相同断言隔离运行，Python 3.10／3.12 各 1 项通过（`current-py310-prelaunch-deadline-isolated-01.log`、`current-py312-prelaunch-deadline-isolated-01.log`，约 3.5／3.4 秒）。Python 3.10 的监督失败场景隔离重跑 1 项通过（`current-py310-supervision-isolated-01.log`，约 21.5 秒）。隔离通过不证明此前失败的具体原因，也不覆盖两模块完整回归；Python 3.10 原监督失败没有完整错误栈。

此后关闭屏障已接入当前源码 AgentApp，启动异常时也增加同步停止接纳；以上修改尚未运行验证。独立审查确认两个未解决问题：屏障只观察资源是否退出，而有些已登记资源需要主动调用关闭才能退出；另一方面，宿主健康检查和任务接纳之间仍有竞态。对已经尝试关闭或关闭结果不明的资源盲目再次关闭也不安全，需要建立明确的关闭所有权。现有定向测试不能证明这两项问题已解决，当前源码和最终安装包均不能据此通过关闭路径验收。

启动失败同步停止接纳的单项源码测试在 Python 3.12 通过（`current-py312-app-start-fence-01.log`，约 0.6 秒），覆盖保留原启动异常和不再次接纳；不能由此证明运行中的宿主异常与接纳之间不存在竞态，也不能证明资源主动关闭或真实回调屏障已通过。

此后工具服务增加由准确后台线程执行的一次关闭启动，AgentApp 屏障尝试关闭已登记的工具服务，但源码仍在修订。Python 3.12 定向运行 `current-py312-tool-server-barrier-01.log`，报告 10 项中 1 项失败、3 项报错，运行 113 秒后测试进程仍未退出，达到原 150 秒外层上限后退出码为 124。并发关闭的 4 项通过；真实回调释放后应用关闭超时，夹具清理也未确认；两项清理诊断集成场景在夹具关闭时超时。失败原因正在核实，不能用这次结果证明回调屏障或应用关闭通过。独立源码审查也发现构造失败后部分工具服务的处理仍可能永久保留资源和线程；正在处理，尚未验证。

随后源码把本地资源退出与业务效果不明的持久预留分开；仅在协作式适配器登记的本地资源已确认退出、效果身份精确匹配、无原生操作且预留仍存在时，允许关闭已停止接纳的应用，预留本身不释放。Python 3.12 真实回调定向测试 `current-py312-callback-quarantine-01.log` 通过 1 项（约 6.7 秒）：回调仍在运行时保留内核和宿主锁，回调退出后应用关闭。该结果不覆盖先前完整组合失败、不证明重开后容量或工作区隔离，也不证明非协作适配器或原生执行清理；源码随后只修改了工作区检查的说明。文件描述符与锁文件匹配不能单独证明系统锁仍然持有，持久工作区记录只约束遵守共享注册协议的宿主。

Python 3.12 的并发关闭与工具清理诊断组合 `current-py312-tool-cleanup-quarantine-01.log` 完成 9 项并通过（约 9.2 秒），包括原先报错的两项诊断场景。它不覆盖此前组合的真实回调夹具失败和进程超时，也不能证明当前安装包、其他平台或构造失败恢复。之后源码又补充了构造及关闭中断的异常因果证据，尚未复验。

重开隔离测试首次运行 `current-py312-quiescent-reopen-01.log` 失败（约 6.4 秒）：真实回调仍活跃时，首次关闭在 2 秒返回 `OrchestratorHostTimeoutError`，而测试错误地要求精确内建 `TimeoutError`；因此未进入重开和容量隔离检查。测试现改为检查该实际异常类型及停止报告，尚未重跑；原失败和子进程输出保留。

修正异常断言后，Python 3.12 定向组合 `current-py312-reopen-construction-02.log` 运行 5 项并通过（约 9.5 秒）：真实本地回调退出后关闭并重开，原效果仍为 indeterminate；同角色探针到达原准入等待但没有进入适配器，取消后退出。组合还覆盖构造前登记、计时器启动后抛错时保留准确部分构造对象、关闭线程中断及原有协议回调测试。这些场景使用源码和受控故障，准入等待通过内部观测点确认；不证明全部平台、安装包或部分构造资源可自动回收，也不覆盖之前完整组合中进程超时的原因。

Python 3.12 既有工具协议、请求线程及请求体计时器故障组合 `current-py312-tools-legacy-01.log` 运行 18 项并通过（约 9.7 秒）。其中服务线程的启动与连接关闭异常是测试明确注入的故障，保留在原日志中；该组覆盖本机源码路径，不代表其他平台或全部旧 API 已验收。

独立源码审查确认通用 `RuntimeContext.register_resource` 契约要求适配器登记资源和提供单调的清理完成证据，并未将关闭所有权转交给宿主；OpenCode 的部分资源还依赖适配器规定的清理顺序。因此宿主对通用资源只观察清理状态，对 SDK 自己的工具服务另行协调关闭。适配器遗留的未完成资源可能令宿主关闭超时，尚无通用自动恢复证明。此前新写的通用资源测试要求宿主自动调用所有资源的 `close()`，超出了已有契约，正在改成检查适配器负责关闭及宿主等待证据；该测试尚未运行。

上述测试后，工具服务继续增加监听器已获取、但服务线程确认尚未尝试启动时的一次部分清理，并修正清理启动中断的异常保留。独立审查又发现构造错误发布过程中中断的优先级问题，正在修订；此后的源码尚未经定向复验。不能用之前的通过结果证明这些新增路径。

修正发布中断优先级后，Python 3.12 定向组合 `current-py312-partial-listener-01.log` 运行 14 项并通过（约 13.4 秒）：覆盖精确监听器在服务启动前的一次清理、清理线程已启动后中断、构造错误发布前中断、并发关闭、真实回调结束后的重开和容量预留，以及合成适配器资源由适配器关闭、宿主等待证据。结果限于本机源码和所注入时点，不证明发布部分完成后中断、全部适配器、其他平台、最终安装包或完整回归。构造或清理结果不明时，部分资源仍可能需要人工恢复。

此前 10 项中有失败且进程达到外层限时的工具关闭、真实回调和诊断组合，按原模块及 150 秒外层限时重跑，Python 3.12 当前源码 10 项通过、进程正常退出（`current-py312-tool-server-barrier-02.log`，约 16.4 秒）。这不解释第一次超时的每个调度细节，也不替代其他平台和最终安装包回归。重开容量预留测试使用私有工作区，不能由其推出共享工作区预留仍有效；该场景待独立验证。

Python 3.10 在本机以两个独立进程串行执行相同原范围，以及构造、重开和资源契约补充组合，分别为 10／10 项通过、10／10 项通过（`current-py310-tool-server-barrier-02.log`、`current-py310-partial-listener-01.log`，约 17.6／12.4 秒）。两组均为当前源码的 Linux 定向验证，不代表完整回归或安装包验收。

针对宿主健康检查与接纳间竞态新增的真实状态切换测试 `current-py312-host-admission-race-01.log` 为 4 项中 2 项失败：直接调用在协调线程已发布失败后仍写入并提交了请求；触发器入口在同一时序下没有按测试要求拒绝。两项测试的现场清理亦未确认，错误及原始输出保留。失败前已经接纳的请求身份保留和启动顺序两项通过。还需验证停止与启动状态覆盖、锁内错误格式化的竞争；不得据此将宿主关闭和接纳完整性记为已通过。

曾尝试以宿主状态锁保护整个接纳事务，但只读审查确认数据库写锁等待或磁盘提交可使带期限的宿主停止超时失效；该方案已撤回，原接纳竞态仍未解决。当前宿主源码另行修正启动完成覆盖停止状态及部分错误格式化持锁问题，Python 3.12 两项定向测试通过（`current-py312-host-start-stop-races-01.log`）；它们不验证完整宿主兼容、存储繁忙时的关闭期限或接纳竞态。可行设计仍需区分立即围栏、在途提交所有权及最终失败发布，不得将未决提交视为完成。

随后独立审查发现关闭阶段错误格式化异常可能在资源实际关闭前中断关闭所有者，而后续停止只检查“尝试过关闭”，有误报成功的风险；协调线程的原始异常也可能因格式化失败而缺失。以上问题正在修复，先前两项通过不覆盖该故障。

当前源码为宿主关闭增加准确的运行时关闭完成证明，保留多个清理错误及中断优先级，并分别保留协调线程错误和诊断中断。Python 3.12 `current-py312-host-diagnostic-safety-01.log` 共 4 项通过（约 0.03 秒），覆盖启动与停止重叠、错误格式化的锁竞争、最终刷新诊断出错时不误报关闭，以及协调线程诊断中断传给停止调用者。仅覆盖注入时点和本机源码；旧 API、启动结果不明、接纳竞态及最终制品仍待验证。

随后的既有 44 项宿主回归在 Python 3.10／3.12 均于首项提前退出，未完成测试（`current-py310-runtime-host-review-05.log`、`current-py312-runtime-host-review-05.log`）。关闭屏障抛出的 `KeyboardInterrupt` 被新代码直接传到停止调用者；既有合同测试要求 `RuntimeError` 包装且原中断保留为原因。正在恢复该异步清理错误包装合同，原失败不可视作通过。

恢复包装后，原失败用例及新增故障组合在 Python 3.12 共 7 项通过（`current-py312-host-diagnostic-safety-02.log`）。同 44 项宿主回归随后在 Python 3.10／3.12 各完成但各有 5 项失败（`current-py310-runtime-host-review-06.log`、`current-py312-runtime-host-review-06.log`）：两项断言缺少关闭错误原消息，同一退避用例的三个子场景受启动状态检查影响。正在修复旧接口及原测试行为，不能把该范围记为通过。

恢复直接运行启动行为及单字符串清理错误消息后，Python 3.12 先前失败用例与新增安全组合共 9 项通过（`current-py312-host-diagnostic-safety-03.log`）。同 44 项宿主原范围串行重跑，Python 3.12／3.10 各 44 项通过（`current-py312-runtime-host-review-07.log`、`current-py310-runtime-host-review-07.log`，约 9.9／10.4 秒）。多参数或非字符串参数的自定义错误现使用通用包装信息，准确异常仍为 cause；对该兼容边界不可扩大声称。上述均为本机当前源码的定向测试，不覆盖未解决的接纳竞态或最终安装包。

共享持久工作区补充测试在 Python 3.12 当前源码通过 1 项（`current-py312-workspace-quarantine-reopen-01.log`，约 9.2 秒）：真实文件工具回调结束后关闭并重开原状态，不明效果的准确工作区所有者仍被保留；另一个独立状态目录的 AgentApp 实际进入同一注册表预留并因未解决所有者被拒绝，未进入其适配器或创建运行效果。两个应用位于同一子进程，此结果不证明跨进程排他、其他平台或最终制品验收。

宿主关闭代码更新后，原工具服务关闭和诊断 10 项与上述共享工作区测试组成的 11 项组合，在 Python 3.12／3.10 当前源码分别全部通过（`current-py312-agent-close-workspace-03.log`、`current-py310-agent-close-workspace-03.log`，各约 28.4 秒）。两个应用仍位于同一子进程；此结果不证明跨进程排他、所有关闭时序、未解决的宿主接纳竞态或最终安装包验收。

真实 SQLite 写事务阻塞应用调用时，新增测试首次到达关闭断言，发现 `AgentApp.close(timeout=0.15)` 超过一秒仍未返回（`current-py312-close-sqlite-writer-01.log`）。修正两处应用锁的限时获取后，受限环境重跑已越过该断言，但调用随后进入 `recovery_required`、进程达到 60 秒外层限时（`current-py312-close-sqlite-writer-02.log`）；现有日志不足以确认原因。允许本机通信后，同一测试通过（`current-py312-close-sqlite-writer-03.log`，约 3.4 秒）：超时保留原应用所有权，解除数据库阻塞后调用和关闭完成。独立审查指出测试夹具的异常清理尚需加固，且前台服务清理和协调锁仍可能超出总期限；此结果只覆盖首次获取应用锁的场景，不证明完整关闭期限或其他平台。

当前源码为根请求实际提交及提交已有请求增加宿主所有权与失败围栏，提交结果不明时保留准确所有者并拒绝继续接纳。此前 4 项宿主故障与接纳时序测试在 Python 3.12 重新通过（`current-py312-host-admission-race-02.log`，约 3.4 秒）；随后的原测试与实际 SQLite 提交边界组合共 7 项通过（`current-py312-host-admission-race-03.log`，约 8.3 秒），覆盖直接调用和触发器、提交中协调线程故障、准确已提交身份及绑定、提交受阻的限时停止和未知结果隔离。未知结果测试使用隔离子进程保留证据，不视为业务清理完成。以上为 Linux 本机源码定向结果；旧 API、其他 Python 版本、完整异常窗口和最终安装包回归仍待验证。

加固数据库占用关闭测试夹具后，Python 3.12 宿主、服务和任务存储及关闭组合共 63 项通过（`current-py312-host-store-close-01.log`，约 18.9 秒）。随后 Python 3.10 同范围加接纳竞争组合共 70 项通过（`current-py310-host-store-admission-01.log`，约 37.8 秒）；新增的隔离子进程还覆盖 SQLite 已提交后抛错，核对原请求及触发绑定不重复、围栏生效及运行时未提前物理关闭。Python 3.12 的上述 63 项不包含这次新增的提交后抛错场景。此前失败、未知效果目录和受限环境超时证据均保留；这些源码定向结果不证明完整旧 API、跨平台或最终制品通过。

Python 3.12 按原范围及 200 秒外层限时串行重跑完整监督与技术重试两模块（`current-py312-supervised-retry-02.log`）：26 项断言在约 125.4 秒输出 OK，先前未到达的原两秒启动前边界此次通过；但测试进程此后没有退出，达到原 200 秒上限，退出码 124。整组不能记为通过，也不能据此确定此前失败原因；进程未退出的准确所有者及现场仍待诊断。

接纳异常与连接清理定向组合最初在 Python 3.12 出现 3 项失败和 1 项报错（`current-py312-root-cleanup-01.log`）；修订后原 13 项均通过（`current-py312-root-cleanup-02.log`，约 1.3 秒）。覆盖初始化失败关闭连接、原异常因果链和交接中断后保留原所有者；它们仅验证受控注入的时点。随后增加的嵌套交接和字符串子类兼容代码仍需单独验证。

新增两项后在 Python 3.12 运行共 15 项，其中嵌套交接测试通过，字符串子类测试报错（`current-py312-root-cleanup-03.log`，约 2.8 秒）：既有权限校验要求精确的字符串类型，调用在到达新增门控前已被拒绝。此前把此场景描述为新门控引起的兼容缺陷缺乏依据；测试现改为核对既有拒绝行为，等待复验。嵌套测试限于所注入的交接时点，不证明任意异步中断都安全。

将上述监督与技术重试回归中一个包含三种子场景的测试单独运行，并在 20 秒采集线程栈（`current-py312-dirty-teardown-diagnostic-01.log`）：该项约 13.5 秒输出 OK，但宿主线程仍在应用关闭屏障等待，同时其他后台线程尚未退出；进程到达 40 秒诊断上限后退出码 124。该结果复现了测试完成后进程不退出，不足以确定具体子场景或证明它是完整组合超时的唯一原因。诊断运行期间宿主源码有并行改动，该进程已在改动前加载相关模块；后续必须在稳定源码上复验。

独立审查发现原测试的 invalid 夹具创建了从未尝试启动的原生操作但未提供清理证明；dirty 夹具登记不可哈希对象，导致登记报错并保留未知所有权，未到达预期故障边界。修正后的三个子场景分别在独立进程执行，在原有单次调用和效果未提交断言之后，仅为夹具自身从未尝试启动的准确操作提供证明、显式结束合成资源，并核实应用关闭。Python 3.12 定向测试报告通过（`technical-retries-fixture-focused.log`，约 11.2 秒）；但复审发现成功时子进程使用了强制退出，因此这次结果不能证明子进程的后台线程自然退出。原线程栈未标示各所有者与子场景的对应关系，不能据此断言它们是完整组合超时的全部原因。夹具现已改为成功时自然退出，等待复验。

包含修正后夹具、嵌套交接、故障围栏和实际 SQLite 提交边界的 Python 3.12 组合共 23 项断言通过、主测试进程正常退出（`current-py312-admission-fixture-01.log`，约 23.4 秒）；其中夹具子进程被强制退出，不能证明其后台线程自然退出。其后审查发现同线程相同身份的内层登记若在登记前中断，可能误将外层所有者标记为未知；当前源码正改用每次尝试的独立标识，上述通过结果不覆盖这一后续改动。未传独立标识的私有宿主调用仍无法区分同身份嵌套中断，SDK 集成入口正改用明确标识。

夹具改为成功时等待子进程自然退出后，Python 3.12 的原单项三子场景再次通过（`current-py312-retry-natural-exit-01.log`，约 9.3 秒），父进程和三个子进程均在测试期限内退出；这不替代监督与技术重试原 26 项完整回归。集成入口开始传递独立尝试标识后，Python 3.12 先前 22 项接纳与提交边界组合再次通过（`current-py312-admission-attempt-01.log`，约 13.6 秒）；针对同身份内层登记前中断的新用例仍待运行。

在同一源码上，新增的同身份嵌套尝试与接纳组合在 Python 3.12／3.10 各运行 25 项并通过（`current-py312-attempt-identity-01.log`、`current-py310-attempt-identity-01.log`，约 14.8／15.5 秒）。新增三项分别检查内层登记前中断不影响外层、登记后中断只将内层标为未知，以及已围栏拒绝内层时保留外层记录；仅证明这些注入时点和 Linux 源码路径。Python 3.12 监督与技术重试原 26 项组合已按原 200 秒外层限时重新启动，结果未出。

上述 Python 3.12 监督与技术重试原 26 项组合完成并自然退出（`current-py312-supervised-retry-03.log`，约 133.8 秒，退出码 0），但此前整组超时及线程栈证据不被覆盖。随后独立审查发现交接登记成功但错误处理本身在围栏前中断时仍可能继续接纳；当前源码正增加待确认交接，发生在本次完整组合之后，尚未由该组合验证。

另有只读审查确认 AgentApp 有限关闭期限仍有三个锁等待缺口：前台服务释放时重新获取应用锁、协调关闭开始时获取协调锁、等待协调静默时获取或重新获取协调锁均未使用剩余期限。后台关闭钩子自身无期限会导致宿主保留资源并等待，不单独证明关闭调用者超时失效。这些结论来自源码时序分析，定向复现和修复待完成。

接入待确认交接后的首次 Python 3.12 故障组合 `current-py312-pending-handoff-01.log` 共 19 项中 1 项失败，其他项目包括五个隔离交接场景通过。保留的子进程记录显示失败夹具在新协议下重复确认同一令牌，已修正夹具并等待原范围复验。独立源码复审尚未确认新的具体接入缺陷；未确认交接会保守地持续阻止新接纳和物理关闭，带期限的停止调用可返回，但这不是已完成清理的证明。

修正夹具后，包括上述原范围及接纳竞争的 26 项组合在 Python 3.12／3.10 分别通过（`current-py312-pending-handoff-02.log`、`current-py310-pending-handoff-02.log`，约 17.2／17.3 秒）。五个隔离故障场景包含交接处理受中断、确认前后中断、等待接纳时停止以及同线程重入；测试限于注入时点与本机源码，未确认交接仍可能要求人工恢复。此前的 26 项监督与技术重试全组通过发生在这次待确认交接代码之前，不能作为当前源码的完整回归证明。

关闭期限锁竞争的 Python 3.12 首次四项测试均失败（`current-py312-close-deadline-contention-01.log`）：三个协调锁场景均观察到 0.15 秒关闭调用在持锁超过 1 秒时没有返回，锁释放后清理完成；前台场景因夹具目录权限失败，未进入目标时序。修正夹具后该前台场景同样观察到超过 1 秒未返回（`current-py312-close-foreground-baseline-02.log`）。协调模块在前台单项运行前已修改，但前台应用锁路径尚未修改，结果仅证明该局部场景。上述原输出均保留，当前源码已开始修复，待复验。

首次修复后 Python 3.12 九项组合 `current-py312-close-deadline-contention-02.log` 有 1 项失败：新测试包装函数未返回协调关闭结果，导致提前报超时且夹具清理未确认。修正包装后原组合 9 项通过（`current-py312-close-deadline-contention-03.log`，约 7.1 秒），包含四个锁时序、既有协调关闭及真实 SQLite 写锁关闭场景；原失败证据保留。独立审查指出后续工作区锁与全局宿主注册锁等待仍不受期限约束，且部分关闭后的重试需要核实，不可将本结果扩大成整个关闭流程的硬期限证明。

同 9 项组合在 Python 3.10 当前源码通过（`current-py310-close-deadline-contention-03.log`，约 9.3 秒），仅覆盖相同的四个受控锁时序及既有关闭测试。后段资源关闭、其他平台和当前安装包仍未由这些测试验证。

关闭后段全局宿主注册锁的真实竞争也已复现：0.15 秒关闭调用在锁持续占用超过 1 秒时未返回，锁释放后才返回成功；单独探针与正式测试分别为 `current-py312-late-close-baseline-01.log` 和 `current-py312-late-close-baseline-02.log`，均保留失败及随后清理结果。现已接入单一后台清理所有者并记录阶段，超时后的重试观察同一所有者；源码尚未运行复验。线程启动调用本身仍可能阻塞，文件句柄关闭结果不明时也不能保证操作系统排他锁仍然持有。

接入单一后段清理所有者及实际线程退出等待后，相同注册锁探针在锁释放前返回 TimeoutError、保留宿主句柄，解锁后再次关闭成功（`current-py312-late-close-probe-02.log`）；协调关闭和 SQLite 写锁关闭 5 项通过（`current-py312-late-owner-legacy-01.log`，约 3.3 秒），前台宿主、清理错误和应用关闭 43 项通过且进程正常退出（`current-py312-late-owner-host-legacy-01.log`，约 81.4 秒）。这些均为 Python 3.12 Linux 源码测试；后段工作区锁、清理失败与线程返回尾部仍需故障测试，不能据此宣称所有关闭阶段或当前安装包已验收。
Python 3.12 后段关闭故障组合首次运行（`current-py312-late-owner-faults-01.log`）因命令误写两个不存在的模块名而报两个导入错误，前台场景在受限环境报 `PermissionError`；该次组合未通过。使用正确模块及允许本机通信的环境后，原关闭期限、协调与数据库占锁场景及新增后段测试共 13 项通过，测试进程正常退出（`current-py312-late-owner-faults-02.log`，约 11.7 秒）。新增场景检查注册锁和工作区锁竞争时调用按期限返回、解锁后继续观察同一清理所有者；工作区关闭抛错后再次关闭返回同一错误且不重复阶段；完成事件发出后线程仍活跃时不能提前返回成功。受控注入不能证明任意时点和所有平台的关闭行为；清理结果不明确时仍可能保留所有者并需要人工处理。

Python 3.10 同组首次运行有 2 项失败（`current-py310-late-owner-faults-02.log`），命令未设置源码路径，主进程加载了旧安装包，部分子进程自行添加了源码路径；因此该次结果不能用于判断当前源码或作为统一安装包验收。原输出及子进程证据保留，正在以明确指定当前源码的相同范围重跑。

明确指定当前源码后，Python 3.10 原范围 13 项通过、进程正常退出（`current-py310-late-owner-faults-03.log`，约 14.5 秒）。这是 Linux 定向源码结果，不代表已重建安装包、其他平台或完整回归通过。

接纳交接和后段关闭修订后，Python 3.12 监督与技术重试原两模块、原 200 秒外层期限再次运行，共 26 项通过且进程自然退出（`current-py312-supervised-retry-04.log`，约 135.5 秒）。这不覆盖此前其他版本原范围失败，也不替代最终安装包和平台回归。

同一范围使用明确加载当前源码的 Python 3.10 再次运行，26 项通过且进程自然退出（`current-py310-supervised-retry-04.log`，约 169.6 秒），原 200 秒期限不变。此前 Python 3.10 的失败与超时保留；结果仍不等于最终安装包或平台回归。

Python 3.10 当前源码的前台宿主、关闭错误和应用关闭原 43 项通过并自然退出（`current-py310-late-owner-host-legacy-01.log`，约 92 秒）。输出中线程启动失败堆栈由测试注入，原文保留；结果限于 Linux 源码，不代表最终安装包或所有关闭时序通过。

G04 补充验证入口 `scripts/verify_agent_dependency_observation_native.py` 已准备，使用公开 producer snapshot 重复观察已保存结果，同时核对消费者身份、绑定、预算及 SDK 清理回执；该范围不是外部事件重复投递，也不单独构成 G04 完整验收。只读审查指出并修正了回执身份、证据保留和清理错误分类的缺口，退出边界中断按不确定记录。两次不调用模型的缺失安装路径启动前负例均拒绝运行并保留报告（`g04-observation-preflight-01/`、`g04-observation-preflight-02/`）；首次错误类型笼统，修订后记录 `FileNotFoundError`。该脚本尚未针对当前安装包执行真实模型，路径和版本检查本身不证明安装包来源。

当前源码、测试、脚本及文档已复制到 `/tmp/agent-control-080-candidate48/source/` 并构建 wheel／sdist（`candidate48-build.log`）。这是本地构建快照，不等于独立安装、行为验证或完整平台验收；后续源码、脚本或文档变更需要重新核对候选一致性。

候选 48 wheel 和 PyYAML 6.0.3 已离线安装到新建 Python 3.12 虚拟环境，从隔离解释器确认加载路径在该环境中；冻结源码与已安装的 141 个产品文件逐文件内容一致（`candidate48-installed-parity.json`）。这不构成运行行为、测试发现完整性或平台通过证据。

候选 48 新安装包的真实 OpenCode 补充验证 `candidate48-g04-observation/report.json` 报告 `supplement_passed`，进程退出 0。慢生产者受控等待时两次重复观察已完成生产者，消费者均未创建；消费者实际进入适配器并等待时再重复观察两次，原调用、效果身份及两项产物版本绑定保持一致，适配器只进入一次。放行后消费者实际产出 `FAST_NATIVE|SLOW_NATIVE`，Agent 调用共 4 次、模型轮次 16 次，并核对各实际调用对应的 SDK 清理回执；应用关闭完成。该验证使用本机 Linux x64、本地模型及适配器闸门；清理结论依赖 SDK 已认证记录。它覆盖重复观察持久结果，不证明外部事件重复投递或整个 G04 当前候选验收通过。

完整安装回归预检通过（`candidate48-build-preflight-structured.json`）：复制候选 47 测试依赖环境和缓存，离线安装候选 48 wheel，检查产品文件一致并重建 sdist／wheel，保留冻结快照。复制的依赖和继承的环境不是独立配置或完全隔离的依赖来源；预检不代表完整安装回归已运行或通过。

候选 48 回归启动器经过只读复审并在隔离夹具中进行所有权自测（`/tmp/candidate48-owner-selftest-xmyvaepb/selftest-result.json`）：注入状态记录错误和 SIGINT 后，同一短命子进程完成且被等待回收，保留中断和原错误因果。该测试只覆盖提取的所有权代码，不覆盖完整启动器、等待反复失败、进程创建中断或进程丢失。启动器锁只协调使用同一路径的参与方，不能排除不遵守锁的进程。

G03 补充验证首次启动命令因在临时目录使用相对脚本路径而复制失败，验证器和模型均未启动；改为绝对路径后另行运行，结果待核对。补充验证脚本位于候选源码快照之外，使用候选快照内的原验证 helper 和候选安装包；原生清理回执仍需独立证据。

候选 48 G03 补充验证随后退出 0，报告 `candidate48-g03-file-denials/report.json` 为 `supplement_passed_cleanup_unverified`。真实 OpenCode 的同一 fast 调用分别提交 `../escape.txt` 和 `linked.txt` 的写入请求；服务器分别在路径遍历校验和符号链接安全打开环节拒绝，并完成通用错误响应写入。两个目标哨兵均未改变；允许的文件写入和下游实际读取通过。独立 FileTools 路径替换竞争记录 71 次替换、1 次允许及 499 次拒绝，外部文件未改变且竞争线程退出。应用上下文关闭正常，但原生清理回执未在此补充验证中核对；服务器写入响应不证明客户端收到响应，直接 FileTools 竞争也不等于模型桥接竞争。该结果不单独将完整 G03 改记 passed。

随后对该场景保留的控制与执行记录进行只读查询，四个成功调用各有一条 `cleaned` 操作，其已保存回执字段分别与调用身份、期限、执行效果及结果的代次一致（`candidate48-g03-readonly-cleanup.json`）。未修改数据库，没有重新认证回执，也未独立检查操作系统进程树；这补充已保存记录的对应关系，不改变原补充验证报告或将 G03 整体改记通过。

候选 48 冻结后，只读核对发现中文／英文 Wiki 及 Agent Control 指南中三处对候选 05 的 G03／G04 历史结果表述过于完整。当前工作树已明确其验证器报告与证据缺口，并链接本索引；三个默认值注册表与当前源码结构一致。上述文档修订和随后新增的 G03 验证脚本不在候选 48 冻结快照中，最终候选仍须重新同步及复验。

G04 重复事件的只读路径核对：依赖调度通过同步执行状态观察生产者事实，结果 outbox 的投递并不是该调度器的事件入口。现有 `tests/test_sdk_results.py` 的合成测试通过拦截确认并推进测试时钟覆盖结果重投，但没有真实 Agent 生产者；未找到受支持的托管故障接口可在确认前制造丢失。候选 48 的真实重复观察证据与该合成测试不能合并冒充真实重复事件验收。后续若使用受控插桩，须分别记录准确结果身份、两次投递及最终确认，并如实说明其与依赖调度入口的关系；G04 完整验收仍保留缺口。

另有状态触发事件按来源终态身份去重，可通过公开宿主入口调用真实来源和目标；它创建独立根 Run，自动触发入口不接受未解析的依赖，因而与 G04 的双生产者依赖调度是不同路径。旧的状态触发补充报告和候选 48 的真实重复观察不能单独冒充双生产者场景中的重复事件投递。

进一步只读架构核对：无协调能力的依赖图使用 Orchestrator 任务；配置协调或返工时，工作调用经 Kernel 子执行提交。现有 Orchestrator 任务 watch 依赖任务和 attempt，不能直接覆盖后者；通知队列也可能包含其他用途的消息。若将事件作为调度入口，须先明确两种执行路径、消息归属及持久接收／确认、重复投递、崩溃恢复和关闭语义，同时保留现有事实扫描；仅给一条路径加 watch 或在验证器中自行桥接，不能证明 SDK 管理的完整事件投递。当前未新增该机制，G04 的重复事件分项仍未验收。

G17 的资源顺序补充验证器已在 `/tmp/verify_candidate48_g17_resource_order_review.py` 准备并经过源码复审，尚未执行。计划在父调用实际持有 96 MiB 时观察子调用的 64 MiB 排队，再记录产品持久化对应父执行清理证明和子调用真正获得容量的先后；关闭限制的对照保留。验证器的私有观察钩子可能影响时序，产品凭据验证不等于独立认证或操作系统内存硬限制。此准备工作不构成 G17 验收通过。

候选 48 的 Python 3.12 完整安装回归已启动，保留原范围和内层 2700 秒限时；北京时间 08:09 的一次检查仍未得到最终结果，不能据此判断通过或失败。按当时剩余时限估计在 08:30 再检查，等待期间不因观察尚未结束而重启或缩短测试。多 Python 版本启动草稿仍有进程树所有权、证据完整性及环境来源问题，保持禁用，尚未运行。

北京时间 08:30 检查得到候选 48 完整安装回归失败：外层 5 项中 1 项失败，启动器退出码 1、实际耗时约 2760 秒；内层在约 1656.5 秒报告 2311 项、11 项失败、8 项错误和 28 项跳过，但收集输出的调用到原 2700 秒限时仍未结束。外层输出尾部截断了部分错误；完整内部日志保留在 `candidate48-consumer-evidence/sdk-observability-consumer-6lhay31b/installed-suite/stderr.log`，尚未完成诊断。候选冻结范围的回归前后内容对照匹配，复制的依赖及环境不是独立配置。原始外层日志为 `/tmp/agent-control-080-evidence/candidate48-tmpfs-regression.log`，结构化报告为同目录 `candidate48-tmpfs-regression.json`，保留现场位于 `candidate48-tmpfs-retained/`。调用使用 `subprocess.run` 收集管道输出：现有证据不能区分主测试进程未退出与后代持有输出管道，未记录内部 PID 或汇总后的线程栈，后代是否全部结束仍未知。不能将具体失败与等待超时归因于单一原因，也不能以历史候选通过覆盖。

针对该回归的三项错误，当前源码测试夹具已分别修订并定向验证：两项监督器保留测试手工创建运行时对象时补齐构造函数初始化的字段，两项原断言通过（`current-py312-native-retention-fixture-01.log`）；投影消费测试将模拟时钟限定在投影模块，保留回调后过期且游标不确认的断言，同文件 13 项通过（`current-py312-projection-consumer-01.log`）。另两项原生预启动错误已依据未确认清理合同修订测试，定向通过并检查原错误、原操作和未确认所有权；精确异常层级来自当前实现而非文档明确承诺。以上仅是当前源码和受控故障注入的定向证据，未重跑完整安装回归，其他失败及输出收集超时仍须分别诊断。

预启动测试文件在 Python 3.12 当前源码共 3 项通过（`current-py312-prelaunch-contract-01.log`）。两项宿主停止测试现分别建立模拟协调器已进入及实际启动已完成的前提，并保留原期限、报告和重试断言；生命周期批量测试只追踪当前线程的目标日志数据库，保留真实提交数量和重放断言；三项合并定向通过（`current-py312-lifecycle-host-fixtures-01.log`）。候选 48 失败的两个观测日志用例及一项沙箱恢复用例在当前源码各自定向通过（`current-py312-observation-regression-01.log`、`current-py312-sandbox-recovery-regression-01.log`），这不能确定原完整回归的失败原因，也不能代替原顺序复验。

修订后两个相关测试文件在 Python 3.12 当前源码分别完成：宿主停止报告 12 项通过（`current-py312-host-stop-report-01.log`），生命周期批量交付 12 项通过（`current-py312-lifecycle-delivery-batch-01.log`）。这仍不证明候选 48 的旧完整回归通过，亦不能排除其他顺序依赖。

工具服务构造后抛错测试现核对已挂接的准确服务所有者，并在先前清理发生错误时仍尝试关闭应用；代理线程启动后抛错测试现等待实际故障注入点，避免处理线程先进入时读取尚未记录的所有者。受限环境首次运行均因本机回环不可用而跳过，随后允许本机回环，两个用例在 Python 3.12 当前源码实际执行通过并正常退出（`current-py312-loopback-ownership-01.log`，2 项、约 4.4 秒）。前者的旧清理夹具异常可能留下非守护宿主线程，但现有证据不足以确认其是原完整回归输出收集超时的唯一原因。原生观测测试也在原三秒窗口内等待持久化的 worker_ready 和 handler_entered 两项事实；单项本机通过，模型门控前的快照为 `/tmp/sdk-observability-native-kpuc38b7/before-model.json`。这些都是源码定向结果，不等于最终安装包的完整回归。

代理线程测试进一步将处理线程进入和故障注入两次等待限制在同一个原有五秒期限内；允许本机回环后单项再次通过（`current-py312-proxy-ownership-deadline-02.log`）。

两项观测日志测试的 SQLite 探针现仅统计同步测试线程的连接，慢关闭只注入该线程的准确目标数据库；原有不提交、期限、事务结果和持久序列断言保留，Python 3.12 单项组合通过（`current-py312-observation-scoped-02.log`）。候选 48 日志未记录额外连接所属线程和数据库，因此无法确认当时的多次计数是否确由其他线程造成。

候选 48 中三个 fork 子进程未按期退出的用例，在当前源码各自隔离运行时均按原内部期限通过；检查各自进程组后未发现残留。此次输出仅保留在只读调查的工具记录中，没有单独日志文件。它们独立通过不能确定完整回归失败的原因；多线程父进程中 fork 后继承锁是可能性，尚无对应线程或锁证据。

为后续安装回归的结束阶段增加进程号记录及汇总后每 30 秒的线程栈诊断，不改变测试范围或原有超时。对提取出的同一生成测试运行器进行隔离验证：普通进程自然退出；人为保留非守护线程约 33 秒的进程在汇总之后记录线程栈并自然退出（`post-summary-watchdog-01.json` 及同名前缀日志）。此诊断仅覆盖测试主进程存活时的 Python 线程；若主进程已退出而后代仍持有输出管道，无法由该诊断区分，亦不证明进程树已清理。

候选 48 安装包中的 SQLite 竞争失败用例另行隔离执行，使用候选 48 冻结测试与脚本及其已安装 SDK，保留原配置和期限；两个准确工作进程在关闭对象前均记录不再存活、退出码为 0，测试及外层观察进程正常退出。此次输出仅保留在调查工具记录中，没有单独日志文件。候选 48 完整回归中的两个工作进程为何未报告仍未知；原始错误没有工作进程栈或退出码，隔离通过不能改写原失败。

对安装回归输出改用文件收集的方案进行了小型验证（`file-backed-capture-check-01.json`）：直接进程可先退出，而其后代随后仍可写入相同日志。独立复审指出，仅凭直接进程成功退出会削弱原有管道 EOF 收尾条件，且草案尚未完整保存直接进程身份、证据错误及后代所有权。因此该接入已撤回，实际回归仍使用原管道与原有期限；小型验证仅说明该方案的限制，不证明后代已全部清理或原回归失败原因。

G04 的 SDK 内部持久结果接收与显式存储升级方案记录于 `SDK_0_8_0_DEPENDENCY_DELIVERY_DESIGN.md`，目前仅为实施草案。G06 的阻塞验证器草案已补齐观察器异常收尾，并要求歧义场景中的组等待实际成功返回对应组及成员；仅经过语法和隔离合成检查，没有执行模型。原生清理回执核对、其他 G06 场景和最终安装包仍未完成，草案入口保持阻塞。

当前源码新增了尚未接入宿主的依赖事件存储原语，并将扫描规划改为逐目标控制事务；同一事务内读取候选、版本和写入后继，提交后才调用 SDK。独立审查指出逐目标重新取快照会比候选 48 更早发现当前歧义，该行为已有定向覆盖；还修复了根调用已取消但标志未置位时后继反复无法创建的问题。Python 3.12 的存储、规划及两项合成适配器 SDK 调度定向测试共 22 项通过，无跳过（`/tmp/agent-control-080-evidence/current-py312-atomic-delivery-05.log`，约 16.4 秒，本机回环可用）。此前受限环境的相同调度测试因回环被拒而跳过（`current-py312-atomic-delivery-02.log`）。

随后，源码补充了尚未接入宿主的终态事件生成和逐目标消费原语：事件冻结来源事实、计划和完整目标集合；合成双生产者场景覆盖了输入不足、消费事务失败回滚、确认丢失后的同事件重投以及绑定和配置冲突。独立审查指出无关调用不应阻塞目标、直接终态后继要与事件同事务，以及后继的实际配置和调用层级必须核对；已修正并增加定向检查。Python 3.12 下相关存储、生产者、消费者和规划测试共 30 项通过，无跳过（`/tmp/agent-control-080-evidence/current-py312-terminal-producer-07.log`，约 4 秒）。这些都是源码级定向检查，所用事实并非真实 OpenCode 执行。

旧状态升级原语现在为既有计划记录扫描模式，为新计划提供原子创建事件模式标记的接口，不回填历史事件；但宿主和 CLI 尚未启用该升级或按模式运行。终态写入、收件箱替换及撤销路径新增默认关闭的事务钩子；生产者钩子区分旧计划、事件计划和真正的独立调用，并拒绝补造缺失的历史事件。相关存储与消费测试 39 项通过（`current-py312-terminal-hook-modes-02.log`）；随后计划创建、重放和关闭的定向测试及既有存储测试 21 项通过（`current-py312-plan-hooks-01.log`）。服务／任务队列和 SDK 观察来源另有受控测试；SDK 结果观察测试使用模拟对象，不代表真实执行。

独立审查后，计划模式记录额外保存冻结文档，旧计划升级按原文保存，新计划与模式标记同事务创建；重放会检查根身份、原始文档和任务代次。公开调用的请求重放也经过模式检查。使用同一配置的不同任务代次替换、遗漏模式标记、角色配置冲突和无注册表情况下创建不受支持的任务计划均有定向负例。当前源码相关定向检查 71 项通过、无跳过（`/tmp/agent-control-080-evidence/current-py312-plan-hooks-05.log`，约 12.6 秒）；独立复审未再发现上述三个创建路径的问题。这个结果不覆盖宿主启用、真实模型或安装包。

源码兼容检查在受限环境执行 22 项，其中 20 项因回环权限跳过（`current-py312-terminal-hook-integration-01.log`）。允许本机回环后重跑，在第十项前已有 9 项通过，但整组达到 60 秒上限而中止（`current-py312-terminal-hook-integration-02.log`）。单独运行双生产者测试曾失败：根调用成功后 10 秒未观察到慢生产者启动（`terminal-hook-two-producers-diagnostic.log`）；之后两次带状态采集的近似场景及一次保留状态目录的同一测试通过（`terminal-hook-two-producers-retained.log`、`terminal-hook-exact-retained.log`）。首次失败没有保留内部状态，原因未明，后续通过不能将其视为已解决。

上述阶段的结果不证明 G04 通过：当时原语尚未接入公开宿主的终态处理、计划模式和实际投递循环；目标集合和单调租约仅在原语级测试。其后的宿主接入及仍有的限制见下方记录。候选 48 完整安装回归仍为失败，当前源码没有新的完整安装回归结果。

后续源码补充了全新控制存储的同事务初始化入口、旧核心表定义及触发器检查、可恢复的投递领取，以及尚未接入宿主的同步消费／提交／确认驱动。合成测试覆盖了初始化失败回滚、过期租约和新宿主代次接管、未封口事件不阻塞其他已封口事件、确认提交前失败后的重投，以及确认已提交但响应丢失后不再重复领取。消费后 SDK 提交仍需宿主独立对账未完成意图；测试中的提交使用替身，不证明 SDK 实际执行。相关当前源码定向测试共 78 项通过（`/tmp/agent-control-080-evidence/current-py312-host-primitives-01.log`，约 14.6 秒），这是随后继续修改旧计划校验前的结果。

独立审查发现公开升级入口在宿主维护计划模式之前并不安全，已撤回该入口，待宿主接入、旧计划关闭及新计划创建的真实重开测试完成后再开放。审查也发现旧计划的嵌套配置和根元数据仍可能不满足实际调度器要求，当前正收紧升级前验证；不能将结构检查通过当成真实旧计划可恢复的证明。事件计划对取消、期限和权限变化还需要可持久恢复的唤醒路径，宿主关闭也必须等待投递尾部。候选 48 的完整安装回归失败和双生产者单次失败原因仍未解决，G04 仍未通过。

随后旧计划预检增加了根元数据和活动计划的部分调度字段检查；实际 `AgentApp` 生成、没有任务代次字段的旧计划在临时存储中通过升级原语测试。没有根元数据的旧计划目前被保守拒绝，其兼容路径尚未完成；嵌套配置尚未全部验证。新增的控制唤醒原语仅在取消、期限或权限条件成立时事务化创建终态后继及事件；重复唤醒发现事件缺失或内容冲突时拒绝补造。它尚未由宿主调用。宿主泵等待锁后也会重新检查关闭标记，避免关闭开始后再进入新一轮泵；定向竞争测试经独立审查后修正了观察顺序。

上述修改期间，相关源码测试共 83 项通过（`/tmp/agent-control-080-evidence/current-py312-host-primitives-02.log`，约 22.4 秒）；之后对控制唤醒的缺失／冲突事件修正、关闭竞争测试和投递驱动重新执行了 10 项，全部通过。现有实际 `AgentApp` 并发关闭测试与新的泵关闭竞争测试也各通过一项。投递驱动的提交使用替身，尚未证明实际 SDK 的幂等提交、关闭等待和宿主重启。没有运行新一轮完整安装回归或 CI。

当前源码已将事件计划接入宿主：持有宿主锁时初始化或验证控制存储、提交宿主代次，再由宿主泵领取、消费及确认事件；旧计划保留扫描模式。新增显式停机升级和只读检查命令。临时旧存储升级测试覆盖旧计划扫描、关闭、新事件计划和重开，但以替身处理 SDK 提交及回执，不能证明实际旧计划完整执行。只读检查给出快照，不能单独证明宿主已停止或结果不确定的提交已经结束；默认日志模式之外的跨平台只读行为未验收。

损坏的最早事件原本可能阻塞其他事件；现先提交领取租约，再在消费事务内校验，失败保留未确认记录并记录事件身份及原因，其他可领取事件可以继续。定向宿主测试覆盖损坏事件与另一计划、重启接管、丢失确认和关闭竞争；故障事件仍需诊断处理，未封口事件可由只读检查计数，不代表已自动恢复。初次组合的一个测试因断言错误类型不符而失败（`/tmp/agent-control-080-evidence/current-py312-host-integration-01.log`），修正断言后相同 11 项通过且进程正常退出（`current-py312-host-integration-02.log`，约 14.7 秒，本机回环可用）。其中公开调用的双 Agent 场景经过真实 SDK 调度，但使用合成适配器；不是 OpenCode 或最终安装包验收。

先前曾失败的双生产者原测试在当前源码再次通过（`/tmp/agent-control-080-evidence/current-py312-two-producers-host-01.log`，约 13.7 秒）。首次失败缺少内部状态，根因仍未确认，不能因重跑通过就判定原问题已解决。当前修改尚未运行新的完整安装包回归或 CI；G04 的真实重复投递、OpenCode 执行、故障重启以及 G01–G18 的最终候选验收仍未完成。

随后补充了关闭屏障和只读检查的定向测试：已消费、未提交的投递受控阻塞时，限时关闭返回超时并保留独占所有权；释放后关闭及重开保留相同接收和后继身份。检查命令识别孤立记录、无效状态和封口集合冲突，但不检查全部事件内容或证明宿主停止。领取提交响应丢失的受控测试保留原始异常因果，换代后恢复同一记录；宿主错误状态只展示阶段、类型及事件身份，不展示底层异常文本。15 项组合通过（`/tmp/agent-control-080-evidence/current-py312-host-integration-04.log`，约 16.8 秒）；其中关闭测试使用合成终态和替身提交。上一轮 13 项组合运行时检查命令和测试正并发修改，因输出字段与测试断言不一致失败（`current-py312-host-integration-03.log`）；该失败保留，不作为最终稳定源码的结果。

为验证当前事件投递，新增真实 OpenCode 定向验证器 `scripts/verify_agent_dependency_redelivery_native.py`。它在已提交消费后、确认前注入一次受控失败，要求实际宿主在真实租约过期后重投相同接收，核对消费结果、调用绑定、效果身份及最终确认；同 ID 异内容冲突另作为存储原语负例。独立审查指出并修复脚本的变量遮蔽和证据对应缺口；隔离缺失安装路径预检及钩子的小型合成检查通过。这不是崩溃重启或已提交确认响应丢失的验证。源码冻结到 `/tmp/agent-control-080-candidate49-vb3gyqhi/source/`，wheel 离线安装于同目录 `venv/`，148 个产品文件与冻结源码逐文件内容一致。冻结后的文档变更未包含在该候选中，它不是最终候选。

候选 49 的真实 OpenCode 定向验证退出 0，报告 `/tmp/agent-control-080-evidence/candidate49-g04-redelivery/report.json` 为 `controlled_redelivery_passed`。消费者实际调用保持同一身份，受控确认前失败后，同一事件及作用域由宿主以新租约重投：消费先后为首次和重放、持久结果一致，代次从 1 增至 2，最终确认且消费者适配器仅进入一次；两个生产者的调用与产物版本绑定、下游最终结果和 SDK 清理回执均经检查。真实调用共 4 次、模型轮次 16 次；变更内容的同 ID 冲突属于单独的存储原语负例。验证输出目录从创建到最终报告约 159 秒，不含独立的等待与环境准备；实际领取时间依赖已安装宿主的租约逻辑，脚本记录的第二次时间是在确认边界。该结果限于 Linux x64／Python 3.12、本地反代和受控前确认故障；它不证明外部消息投递、进程崩溃重启、已提交确认响应丢失、完整 G04 或 G18 验收。候选 48 完整回归中的原始失败和输出收集超时仍需处理。

独立只读复核了候选 49 验证报告、冻结脚本和保留控制存储：四个调用及最终产物成功，一条消费者调用，慢生产者到消费者的记录以第 2 代租约确认，报告所列的版本绑定和四项 SDK 清理回执与保留证据对应。未发现与上述受控范围不符的成功结论；清理仍以 SDK 回执为依据，没有独立观察操作系统进程树。

候选 48 完整回归中三个子进程未按期限退出的原测试，使用冻结测试及安装包分别单独重跑，原测试内期限不变，三项均通过；记录位于 `/tmp/candidate48-child-exit-diag-1793759463-2/`。生命周期场景记录子进程按预期退出码 27 退出，两个监督场景各记录退出码 0；这些 PID 分属各自启动命名空间。测试附加了 fork 入口栈采集，可能影响时序；进程结束早于独立观察器取得 pidfd，没有取得存活时独立栈或孙进程退出状态。隔离通过不能解释原完整回归的失败，也不能将其改记通过。

新增 Linux 回归进程管道观察原语及五项定向测试，按指定 PID 和启动时间有限扫描描述符，只记录候选写端与未知原因，不读取管道内容或凭据。它未接入完整回归；描述符复用、进程变化、扫描范围和 proc 文件系统时延均限制结论，空结果不能证明 EOF。新增的真实崩溃验证器 `scripts/verify_agent_dependency_crash_native.py` 已经过独立源码审查和不调用模型的边界检查；候选 51 已冻结源码并复用与其 148 个产品文件内容一致的候选 50 wheel，在独立环境安装。它只针对消费者命令提交后、SDK 准入和事件确认之前的窗口，不能代表其他崩溃窗口或完整 G04。

候选 51 受控崩溃恢复验证退出 0，`/tmp/agent-control-080-evidence/candidate51-g04-crash/report.json` 为 `controlled_crash_passed`。消费者命令持久化后、SDK 准入和事件确认前，测试宿主以预期退出码 42 终止；原监督器确认进程树清理后才用相同状态启动新宿主。原事件以新宿主代次重放已消费结果并确认，消费者保留原命令、调用及绑定并实际成功一次，生产者事实不变；原 Run 截止时间和预算额度保留，模型轮次由 12 增至 16，调用额度消耗保持 4。恢复宿主正常退出，监督器也确认其进程树清理。输出目录创建至最终报告约 106 秒；测试使用本地反代、真实 OpenCode 与受控故障钩子。SDK 原生清理依赖认证回执，监督器进程树清理是独立的测试进程所有权证据；此结果不覆盖 SDK 准入之后的崩溃、已提交确认响应丢失、系统重启或完整 G04/G14/G18 验收。

独立只读复核候选 51 报告、冻结脚本和保留存储，确认故障前无消费者准入回执、Kernel 执行或 effect；旧宿主监督器确认清理后才开启恢复宿主，同一接收以新租约重放并确认。保留存储中四个 Agent 执行均成功，消费者仅一个调用，四项产物与 SDK 清理记录对应；未发现超出上述受控范围的错误成功结论。没有独立验证提供商侧会话记录，安装路径及版本检查也不是独立制品来源证明。

候选 48 的沙箱恢复失败找到了对应原始夹具现场：安装回归输出关联到 `/tmp/agent-control-080-evidence/candidate48-consumer-evidence/sdk-sandbox-runtime-j0f5y5ri/sandbox-before-cleanup.json`。首次执行进入 `recovery_required`，清理确认及效果解析返回后，首次立即重试的 `run_once` 返回 `None`，没有记录第二次原生调用。该次返回时记录的结算错误、观察错误和待结算项为空；断言失败触发运行时关闭后的快照中执行仍为 queued、效果已提交。后者不是取得执行时的原子快照，原夹具也没有为此用例记录首次空返回的完整准入与领取状态，因此不能确定未取得执行的具体原因；后续单项通过不改写原始失败。

G06 候选 48 补充验证草稿仍禁止运行：它固定了旧候选路径，候选 51 的 wheel 来自候选 50，不能直接沿用旧制品路径核对；三个用例共用未受外部监督的进程，现有通过条件未要求正数模型轮次及与原生操作身份逐项匹配的清理回执。候选 45 的历史负例通过不能替代当前候选。需先补齐制品对应、监督与清理、逐项断言和失败路径测试，并经独立审查后才能执行。

使用候选 48 冻结测试和安装包、保留原执行期限的带诊断复现中，两次通过，一次再次出现同一 `NoneType.result` 失败；现场见 `/tmp/sandbox-candidate48-diagnostic-20261104/run-3/`。该次在第二次领取之前两次观察到执行 `x` 位于排除集合，实际 `claim_and_start` 返回空；空返回后立即采集的快照中执行仍排队。诊断插桩改变了时序，且没有记录 `x` 属于哪一种待处理诊断集合，不能断言它解释了原始完整回归，也不能将未交付记录或开放 producer 单独认定为排除原因。一次更早的试验因诊断启动脚本缺少进程入口保护而无效，保留在同一目录的 `run-1`；修正后的 `run-2`、`run-3`、`run-4` 分别对应通过、失败、通过。

该沙箱测试现按公开的 `run_once()` 空返回合同，仅在可信的原执行工作预算内对空结果重试；非空结果仍立即核对原有完整结果、原操作身份及空历史。首次空返回会在下一次重试前保存只读诊断；该快照并非领取时的原子状态。独立审查确认重试截止不会延长原预算，但单次 SDK 调用或诊断读取不受此循环强制中断，不能称为整体硬超时。当前源码的修订用例及相邻用例通过，单独注入一次空返回的检查也通过：`/tmp/sandbox-candidate48-diagnostic-20261104/current-targeted.log`、`synthetic-first-none.log`。之后该用例改用记录实际入口的模拟提供方，并核对第一次仅有一次 start，恢复后的 start／collect 记录没有增加；单项在 Python 3.12 当前源码通过，现场 `/tmp/sdk-sandbox-runtime-g8gjwne1/`，独立审查确认该检查只覆盖断言前此模拟提供方记录的调用。另一次未设置源码导入路径的本机调用因找不到包而失败；使用候选 51 环境解释器和当前源码路径后单项通过。上述结果均非完整安装包回归，也不解释候选 48 原始失败。

新增的回归管道观察器已接入工作区的完整安装套件调用，保留原 2700 秒期限和标准库管道收集。隔离夹具覆盖真实子进程正常输出、管道继承、超时以及受控暂停标准库超时清理时的实时落盘；观察器保留原子进程调用的收集、信号和回收权，不复制管道，不读取输出内容。观察器和接入的组合定向测试在 Linux / Python 3.12 共 15 项通过，包括诊断初始化失败仍运行原命令及超时时保留部分输出。独立审查发现安装套件复制规则会排除外层测试却保留依赖它的诊断测试，已一并排除该诊断测试；按实际规则复制后，独立解释器可以发现其余 12 项管道诊断测试。复制检查首次因临时检查脚本漏导入 `sys` 而失败，修正后通过；独立复审确认该复制缺口已修复。记录数量和大小受限，文件尾部可能因 I/O 失败不完整；观察线程也可能在调用返回后延迟写入。进程身份、描述符复用与后代扫描仍有竞态，未观察到写端不证明 EOF；其他平台尚未验收。

候选 52 的 Linux x64 Python 3.12 完整安装回归于北京时间 2026-11-04 11:14 启动，预计 12:04 左右检查结果；启动不代表通过。候选 52 安装包的 G01 配置检查在本机 Python 3.10.22、3.11.18、3.12.3 和 3.13.18 均通过，各自证据为 `/tmp/agent-control-080-evidence/candidate52-g01-py310/`、`candidate52-g01-py311/`、`candidate52-g01-final-config/` 和 `candidate52-g01-py313/`；这不代替完整版本回归。G13 合同与拒绝检查通过，证据为 `candidate52-g13-contract/`，不表示真实强隔离已验收。六个公共类型消费者检查通过，工具结果转录为 `candidate52-all-typing-codex-capture.txt`；类型目标 3.10 不代表运行时验收。候选快照的 575 个本地文件链接存在（`candidate52-docs-local-links.json`，未检查锚点或外部链接），Wiki 的 25 页已本地导出，未发布。

候选 52 冻结后，详细指南修正了候选 03 的历史文件拒绝描述：原诊断未记录请求路径，不能独立证明两条特定请求分别被拒绝。该文档变更及本验收记录不在候选 52 冻结快照内；最终制品须重新同步并按变更影响复验，不能把此前候选的结果改写为最终候选证据。

对候选 52 源码的再次只读审查确认，Windows guard 的 `accept()` 返回与登记端点之间，以及 guard socket／socketpair 返回与登记之间，仍存在异步中断时无法确认端点清理的窗口；这不是已实证的原生 Windows 泄漏。工作区正在修改获取所有权和验证未知清理路径，尚未完成复审和测试。另一个未解决的合同缺口是 `RuntimeHost.stop(timeout)` 的清理或撤销线程启动，以及与并发启动共用的锁可能在期限内等待前阻塞；公开宿主也宣称有限停止期限。该问题仍需覆盖未启动、运行中和启动竞争路径，不能以单纯缩窄文档承诺或仅移动阻塞调用来宣称修复。上述源码改动将晚于候选 52 的冻结快照，最终候选须纳入并按影响范围重新验证。

后续工作区为端点获取增加待确认登记，在监听就绪后再开始 accept；返回的已登记端点交接失败时，关闭操作按精确身份记录，未登记或关闭失败保持未知。普通资源构造异常也可能被保守分类为清理未知，自动技术重试行为受到影响，尚需评估。新增测试涵盖就绪后取消／到期、获取后抛错、登记完成边界和关闭失败；这些修改只做过语法检查，尚未运行测试或在原生 Windows 上验证。独立审查曾发现未登记端点可能重复关闭，工作区已修正并补充并发与失败测试；复审在所查范围内没有发现新的明确问题，测试结果仍待取得。

候选 48 沙箱诊断的只读复核进一步确认，领取排除集合可能来自待交付诊断、无法保留的诊断，或监督结果交接未知；它们的恢复规则不同。原记录没有区分具体集合，不能将未交付事件单独确定为原因，也不能仅因重试获授权就清除未知状态。当前用例在原工作预算内处理 `run_once()` 的空返回，不改写历史失败结论。

工作区的 `verify_agent_control.py` 对 G06 保留原调用组场景结果及缺项；该部分场景即使通过也报告整项 `not_run`，失败仍报告失败。原生歧义引用、缺失输入和逐操作清理回执仍需补证；该修改不改变场景预算，尚未运行。停止期限另新增四个受控线程启动和锁竞争测试，均尚未执行；不能据此宣称问题已复现或修复。

对启动在协调器创建前失败且配置了关闭钩子的路径，工作区避免覆盖并发停止已登记的清理所有者；独立审查指出无钩子路径仍需统一所有权，且总体停止期限问题未修复。新增单所有者竞态测试尚未运行。候选 48 的取消测试曾在原 10 秒等待后没有观察到子进程退出；工作区保留相同等待和断言，补充精确子进程、运行时及目录的清理顺序。已发布进程句柄时会有界清理；句柄发布前中断仍保持未知，不能确认子进程或测试进程退出。该夹具修正只经过源码复审和语法检查，未证明历史超时原因或修复完整回归。

候选 52 的 Linux x64 / Python 3.12 安装回归于 11:41:04 结束，按约定在 12:04 检查：内层 2419 项，1 项失败、3 项错误、28 项跳过；外层 5 项中 1 项失败。内层失败为期限回拨结算测试，错误分别为提交边界最终 Bridge 刷新、已终态计划取消时模式不一致、子调用结果交付；原始报告在 `/tmp/agent-control-080-evidence/candidate52-tmpfs-regression.log`，索引为同目录 `candidate52-tmpfs-regression.json`。根因分别排查中，不能以历史通过覆盖；候选 52 也不含后续端点和宿主修改。

回归结束后，工作区端点所有权与 guard 握手定向组合在 Linux x64 / Python 3.12 运行 23 项全部通过，包含本机回环及新增的中断、失败和并发关闭场景。这只证明当前源码的上述组合，不代替独立安装包、原生 Windows 或完整回归。普通构造异常可能降低技术重试能力的限制仍需处理。

候选 52 的终态取消错误来自测试夹具只重新打开计划、却没有同时重置依赖模式的结束标记；正常关闭路径在同一事务中更新两项。夹具现于同一事务恢复两项，保留原断言和期限，原测试在本机回环可用时定向通过（1 项，3.911 秒，`candidate52-dependency-terminal-cancel-focused-02.log`）。启动失败与停止竞争的单所有者测试和生命周期子进程清理测试在当前源码组合通过（2 项，0.416 秒）；不证明无钩子路径或有限停止期限已经修复。

其余三个候选 52 原始失败仍未确定根因：最终 Bridge 刷新缺少底层错误记录，九次带诊断的原测试复现均通过；子调用证据显示检查窗口耗尽且另有数据库锁错误，但未确定锁持有者或两者因果；期限回拨结算的记录显示原执行超时，源码存在竞争可能，但未记录足够的实际顺序来认定原因。单独通过或代码推测均不能改写完整回归结果。

当前源码的四个停止期限受控测试均失败（4 项，3.270 秒）：停止前线程启动未返回，或停止与协调器启动竞争锁时，传入 0.12 秒的停止调用在 0.8 秒观察窗内仍未返回。四个场景分别为未启动宿主、运行中撤销、启动竞争及公共 OrchestratorHost 启动竞争；测试随后释放闸门并等待资源清理。这证实有限停止期限缺口，尚未修复。子调用结果测试现保留空结果而非在报告格式化时额外抛出 AttributeError；该用例与期限回拨用例按原预算单独重跑两项通过（27.738 秒，`child-settlement-focused-review.log`），不能确定或改写候选 52 原始失败的原因。

受控的真实宿主测试发现另一项独立缺陷：最终 Bridge 刷新成功期间，其他线程记录错误也可能令最终刷新误报失败。修复将判定限定到最终刷新所有者及其 pump／progress 错误，并在格式化前保留原错误。受控测试先失败后通过（`final-flush-attribution-03.log`、`final-flush-attribution-04.log`）；与实际最终刷新失败、诊断异常和提交边界组合共 6 项通过（8.320 秒）。独立审查在此范围未发现明确缺陷；尚不能确认该竞争就是候选 52 的原始失败原因，也不解决停止期限问题。

端点待确认登记的兼容性已有实际失败证据：允许本机回环后，原有技术重试用例在合成 socket 创建前 EMFILE 时进入 `recovery_required`，未完成预期重试（1 项错误，13.063 秒）。测试报告后进程没有退出，检查其五个线程仍在等待、没有直接子进程，临时目录已经由夹具删除；保留失败现场后结束该独立测试进程，退出码 143，不将其记为正常清理。单凭 OSError 或 errno 无法区分创建前错误与创建后交接失败，故不能简单清除待确认状态。需要可信的获取及失败证明，同时保留未确认资源不重试的保证；当前源码不满足该原有用例。

工作区继续修订启动失败后的清理交接：无关闭钩子时，启动调用和并发停止在同一锁内选择准确所有者；`join` 等待清理交接而非等待启动调用者线程结束。启动尚未选定所有者时也保留待确认状态，避免错误报告已完成。测试覆盖内联先取得所有权、停止先取得所有权、启动调用者继续存活、重入自等待及失败记账中断。相关源码组合 33 项通过（8.907 秒）；独立复审确认已处理所测普通竞争，同时指出中断后的未确认交接可能不能继续完成，且有限停止期限的四项失败仍未修复。最终刷新测试另覆盖不同线程报告同源错误及真实 progress hook 失败；仅为源码定向证据。

复审后进一步处理停止侧所有者构造或交接中断：保留失败与准确所有者，唤醒已等待的 `join`，不创建替代所有者；启动、所有者和通知的中断按首次中断优先，保留原有异常原因及其他原始错误。新增测试覆盖已有等待者、两种关闭钩子、所有者构造失败和多重异常。更新后的宿主定向组合 38 项通过（9.679 秒），独立审查在所审修订内未发现进一步明确缺陷。构造失败但没有可确认所有者时，后续停止会保守拒绝重试，这是相对于原先允许再尝试的可观察行为变化；中断后交接可能持续未知。四项有限停止期限缺口和技术重试回退仍未修复，不能开始最终完整回归或声称目标完成。

同一组当前源码测试在 Linux x64 的 Python 3.10 下也完成，38 项通过（10.173 秒，进程正常退出）。这是源码定向覆盖，不等于 Python 3.10 完整安装回归或其他原生平台通过。

有限停止期限的架构审查发现一个必须解决的约束冲突：对尚未启动的宿主，若停止时创建清理线程在真正启动前卡住，调用者按期限返回后尚无非守护清理者；提前常驻非守护线程则可能使空闲进程无法退出。现有协调器只在启动后存在且可能忙于排空，不能覆盖这一窗口；普通守护线程也不能单独保证进程退出时的清理所有权。可选方向包括由已运行的外部宿主监督者接管，或重新设计进程生命周期及明确其退出保证；目前没有已验收方案，也没有因此降低现有期限与清理合同。等待锁及公共 OrchestratorHost 报告还需一并设计。

G06 补验的历史脚本覆盖调度器歧义、成功生产者缺少可选产物及组必需产物缺失，但历史结果不能证明当前制品。直接调用需要绑定输入的组目标会被预检拒绝，不能把这种拒绝混称为调度器 `missing_input`。新的补验须区分工具参数拒绝与调度器负例，逐操作核对真实模型调用、原预算、执行身份和认证清理回执；测试监督进程树清理与 SDK 原生清理各自独立证明。

新的 G06 原生补验脚本目前由双重硬门禁禁止执行，未运行模型调用。独立审查发现：内部工作入口可以绕过监督；启动子进程后保存句柄前的中断窗口可能丢失清理所有权；异常退出时监督者身份和清理结果可能丢失；观察器收尾可能吞掉中断。此外，证据需要保存逐操作的原始可核对身份和清理回执，与场景声明的原始预算比较、核对各实际调用的模型用量，并检查未匹配的操作。上述缺口及独立复审完成前不得解除门禁或将脚本运行结果作为验收。

补验脚本的离线修订已保留核对过的操作及回执身份，检查未匹配操作、声明预算、命令期限和创建时间对应的期限；观察器收尾会记录经限制的错误类型并保留中断优先级。证据断言定向测试 6 项、观察器定向测试 7 项通过；观察器异常组合包括实际 AgentApp 关闭后注入的关闭异常，并非真实资源关闭失败。独立复审确认所提的期限、异常优先级问题已处理，但没有证明完整验证器可运行。调用级用量账本包含后代消耗，正数不能单独证明该调用自身产生模型推理；认证清理回执也不等于独立的操作系统进程树检查。进程监督和直接工作入口问题仍未解决，脚本继续保持禁用；普通入口、工作入口和帮助入口均验证返回失败，未调用模型。

对两项代码缺口的后续只读设计检查没有得出可直接应用的修复：共享后台清理监督者必须在宿主暴露前建立，并处理启动不明、关闭及进程退出，普通守护线程加退出钩子不等价于现有非守护清理所有者；端点重试需要可信的获取结果，能区分系统调用未取得句柄和返回交接不明，现有 guard 回执不覆盖 guard 启动之前的通道获取。原生获取原语或已建立的隔离所有者是待评估方向，均尚未实施或通过跨平台验证。英文文档和中英文 Wiki 已明确当前已知重试回退，不能将历史候选的成功描述为当前代码通过。

候选 52 的逻辑水位测试原先将“监视器先观察到期”和“处理器先返回”两种竞态都当成必然是后者。当前源码测试已分别控制这两种顺序，保留原预算、原始成功回执及过期结果不得被接受的断言，并核对执行代次与迟到线程结束；两项和清理辅助检查共 3 项定向通过。候选 52 原始失败的精确时序未记录，历史结果不变。另一个独立的真实线程受控场景观察到：处理器结果已发布，但监视器稍后返回到期时，结算回执记录了合成超时而非该原始结果；初步复现见 `published-outcome-monitor-race-04.log`，测试及其期限和清理证据仍在独立复核，当前源码尚未修复。

后续复核为上述受控场景核对了准确的执行身份、原期限和已发布结果，并补充了清理中断的上下文；定向重跑仍以原始结果被超时回执取代而失败（`/tmp/agent-control-080-evidence/published-outcome-monitor-race-08.log`）。该检查针对原始事实的保留，不主张过期后的成功应被业务接受。工作区新增了私有预算观察记录并保留原有调用接口，相关定向测试通过；这只是准备工作，尚未接入结果交接，也未修复竞态。独立审查指出投影观察的执行代次只标识观察者，不能证明读取的预算来源属于同一代次，因此不得将其作为代次权威证据。

预算观察现区分锁不可用、无记录和合并未核验记录；合并记录不意味着该记录提供了最终较强的时钟水位。测试还覆盖旧代次观察、新记录较弱及空值异常，独立复核未发现该范围内新的明确问题。当前源码连同相邻监视器、完成时钟和结算顺序检查共 15 项通过（2.467 秒）。这是源码定向验证，不是竞态修复或安装包验收。

另一条实际线程与 SQLite 的受控路径确认：完成时钟读取因待确认采样而产生原始恢复证明，随后处理器预算视图因受控时钟域不一致而包装为未知时，原代码没有把证明复制到外层，恢复无法使用它。保留完整原始证明后，真实结算恢复又暴露未知时钟错误缺少必需的 `retryable` 字段，导致结果误变为 `invalid_handler_result` 并丢失原始业务值（修复前日志 `completion-proof-wrap-recovery-01.log`）。当前源码保留该证明，并在处理器包装及监视器两条未知时钟路径填写非重试标记和合法细节；实际同代次恢复记录 `budget_clock_unknown` 失败，并保留原处理器结果作为事实，不把它当作成功（`completion-proof-wrap-recovery-02.log`）。后者未证明重启后恢复或解决前述监视器竞态。

工作区另暂存私有完成时钟观察，保留成功读取时原有的精确采样和经存储水位校验的完成时间；既有接口仍返回浮点时间，内存和自定义 Kernel 的不可比较采样明确为空。该记录尚未接入运行时交接或持久恢复。源码组合 52 项通过（15.215 秒，`completion-observation-and-proof-focused.log`）；针对随后加固的测试清理、两条未知时钟路径另作定向复验（`completion-proof-cleanup-final.log`）。上述均为本地源码证据，不代替当前安装包和平台验收。

监视器竞态的独立设计审查否定了一个简化修法：即便完成时钟读取先结束，也不能据此证明此后的监视器观察一定更新，因为另一个采样者可能在读取快照建立后提交保护并观察更强水位，而旧快照看不到它；监视器还可能复用先前提交的水位或无代次认证的投影。采样时间排序本身不证明 SQLite 提交顺序。解决此竞态仍需能覆盖该窗口的同步或版本／采样保护协议，再将原始结果与权威预算一并交接；当前未实现，不得据此声明竞态已修复。

进一步的受控实测在真实 SQLite 连接上先固定读快照，再通过 Kernel 提交独立的采样保护；原完成时间读取成功返回时，该保护仍在，但旧快照没有看到它（`completion-snapshot-guard-order.log`）。测试中的后续高水位使用受控时钟值，并未证明两个真实提交水位之间的顺序，也不替代原竞态复现。独立审查确认这一证据范围及测试的未确认所有权保留方式。

补充真实进程重启测试：生产进程优雅关闭后，新 Runtime 使用原租约与采样证明恢复，保留预算约束并记录不可重试的未知时钟失败；先取消时保持原取消结果，处理器均仅执行一次。时钟域故障由受控钩子注入，测试不代表突然崩溃或中断中的进程间交接已验收。宿主另补充空闲、未启动及已启动时清理的正常进程退出检查；标记仅证明关闭执行到该位置，进程启动返回前的句柄交接中断仍属未知。上述组合 6 项通过（`snapshot-restart-host-exit-focused.log`）。一次停止期限局部修订发现可能丢失停止信号或使清理无主，且原有并发用例失败，已撤回；四项有限期限缺陷依然存在。

应用配置的 `defaults` 现区分省略与显式空值：YAML、Python 映射和直接构造均要求提供时为映射，省略或空映射继承默认值；其他允许 null 的字段和 JSON 值保持原语义。独立审查发现首次修订会把私有省略标记传给子类构造器，已修正并补充测试。此修订改变了 0.8.0 开发版此前接受显式 `defaults=None` 的行为；`ApplicationSpec` 不存在于 main，不能据此声称旧版已有该 API。中英文 Wiki 及控制层文档已同步；Python 3.12 源码配置及验证定向 17 项通过（`null-default-parity-focused.log`），公开 Agent 类型消费检查通过。无第三方 site 包的同一 Python 运行中 3 项通过、YAML 测试按可选依赖跳过。以上不替代安装包或完整平台矩阵回归。独立复核在该配置修改范围未发现进一步明确缺陷。

再次核对预算范围时发现：配置注册表接受非空 `budget.tokens`，但 `AgentApp` 对所有适配器都在执行前拒绝，OpenCode 还有独立拒绝。此前文档仅称默认适配器拒绝，现已更正。Goal 明确默认不设 token 上限，并要求预算覆盖及字段真实生效，但未逐字写明必须支持配置 token 上限；按覆盖及只能收紧的较强解释，这仍是实现和 G15 验收缺口，不能用默认值或修改文档代替支持。

现有源码的自定义适配器预算拒绝测试再次通过（`unsupported-token-budget-current.log`，1 项）；文档检查在项目解释器和源码路径下通过 575 个本地链接、4 个 README 示例、零跳过（`docs-token-limits-focused.log`）。此前误以系统 Python 运行检查脚本并传入 `--help` 时，脚本实际执行了检查，README 示例因未配置 SDK 导入路径失败；该失败与后一次正确环境的通过分别保留，均不代表 token 上限已实现。

G06 调用级模型证据的只读核对确认：代理在连接提供商前计量模型轮次，连接失败或取消仍可能留下计量；调用预算账本包含后代消耗，不能证明某个原生操作收到模型响应。现有 SDK 记录没有可供该验证器只读核对、同时绑定调用、租约和原生操作的提供商响应事实。G06 补验脚本保持禁用，须先补充可信观察及其失败、收尾和身份语义；不能凭正数用量宣称真实调用成功。

监视器竞态曾尝试在既有结算 evidence 中分开保存真实结果和超时决定；独立审查发现旧调用可任意填写同名 evidence 字段，恢复时信任它可能改变旧回执的权威结果；另外收据未确认持久化时仍可能先提交超时，进程退出后丢失真实结果。该候选已撤回，原竞态尚未修复。可行方案须使用不与历史证据冲突的专用存储格式，原子保存并验证事实、决定、原预算和执行身份；确认准确持久化后才允许 Kernel 提交，并在恢复中执行同一规则。存储格式升级、旧版本兼容及实际崩溃窗口验证仍未完成。

现新增隔离的 v5 结算存储基础，显式复制 v4 并在专用回执中原子保存真实结果、超时决定、预算和租约；重放须精确匹配，旧版任意 evidence 不作为决定。当前运行时及原有访问入口拒绝 v5，新格式尚不能作为运行时存储启用；回执本身也不证明调用者提供的预算或决定具有权威性。复制依赖宿主持续隔离源写入者、目标主文件及 SQLite 旁文件与连接直至切换，授权回调本身不建立隔离；复制不自动切换。路径冲突、残留旁文件、真实 WAL 快照与检查点、发布后未确认、异常和中断优先级等经过定向测试与独立审查。Python 3 Linux 源码上的新旧结算及复制绑定组合 47 项通过（`/tmp/agent-control-080-evidence/settlement-v5-foundation-focused.log`）；独立复核 18 项通过，未发现所审存储基础内其他明确缺陷。第一次复制绑定测试因缺少测试目录导入路径而导入失败，补足路径后通过，不能将首次失败改记成功。上述不证明真实切换、旧在途写入者隔离、跨平台或故障窗口完整性，更不代表监视器竞态已修复。

v5 维护入口新增逐条有界扫描：同一 SQLite 快照内核对大小、身份、存储类型及内容，区分旧回执与分离回执，旧 evidence 只按严格 JSON 数据读取；决定与预算仍不因此具备权威性。独立审查发现的动态类型超大字段、旧记录身份不符和非有限 JSON 已分别补充测试并修正，所审范围未发现进一步明确缺陷。扫描游标仅是提示，不是领取或持久身份；该父记录扫描不检查所有孤立子回执。新旧格式及扫描组合 25 项通过（`/tmp/agent-control-080-evidence/settlement-split-pending-current.log`），不证明运行时恢复、升级隔离或崩溃验收。

协调线程启动时现保留单一已登记所有者，并在启动结果未决时允许并发停止按原期限返回；并发启动等待同一结果，启动失败会唤醒等待者，重入等待不会等待自己。公开宿主也新增启动和通知线程入口交接，停止期间保留待确认所有权；停止通知异常后继续尝试清理并保留错误。公开宿主停止围栏在信号发布前生效，针对信号发布前后中断的定向检查和独立复核通过。相关源码定向组合 53 项通过（`/tmp/agent-control-080-evidence/host-handoff-combined-fence.log`），包括两项协调线程启动竞争的有界停止场景。独立审查指出 RuntimeHost 的启动结果事件及入口事件若在受控注入下抛出，仍可能使所有者或等待者无法进入清理；这些异常边界尚未修复。启动对象构造在宿主锁内可能阻塞时，有限停止也未得到保证。

此前四项有限停止期限场景中，协调线程的直接及公开宿主竞争现有上述定向通过证据；未启动宿主的清理线程启动和运行中撤销线程启动两项仍失败（`/tmp/agent-control-080-evidence/host-stop-remaining-failures-current.log`）。另有旧宿主测试期望通知线程 `start()` 抛错后 `stop()` 返回成功，而当前候选保留无法确认的线程所有权并返回超时，该原测试目前报错（`/tmp/agent-control-080-evidence/orchestrator-legacy-notification-start-fence.log`）。这是可观察的兼容性差异，不能将旧 API 回归记为通过，也不能以测试注入证明生产代码知道线程没有启动。上述修改尚未成为最终安装候选。

v5 维护读取和精确重放复核发现：它们原先没有在完整读取前验证动态元数据，且允许非有限 JSON；独立复审还发现写入／精确读取的大小未计入执行 ID，而扫描计入，达到上限的回执会被扫描拒绝。当前源码在同一 SQLite 快照中先检查元数据和完整字节数，再读取回执；写入、读取、扫描统一计入执行 ID，采用严格 JSON 并拒绝重复键及非有限值。最大字节数边界、超大字段、真实 SQLite 孤儿／缺失子记录和 WAL 并发快照均有定向测试。修正前的受控失败保留于 `split-read-invalid-before.log`；独立复审发现上述边界缺口后复核最终修订，在所审范围未发现新的明确缺陷。源码与旧结算、复制绑定组合共 61 项通过（`/tmp/agent-control-080-evidence/split-read-bounded-combined-02.log`，19.488 秒）；此前组合首次运行因 `PYTHONPATH` 未包含测试目录导致一个测试模块导入失败，记录为 `split-read-bounded-combined-01.log`。这是尚未接入运行时的维护基础，既不证明回执决定具有权威性，也不证明升级隔离或监视器竞态已修复。由于 v5 尚未供运行时启用，新的大小规则对先前已按旧规则写入的超限维护记录会拒绝读取，需要维护者处理，不能静默截断。

监视器竞态的进一步设计核对发现：已有采样保护只覆盖执行及其祖先，但其他执行也可能推进共享时钟水位；仅给原执行增加保护不能证明返回前后的观察顺序。可供继续评估的方向是以 Kernel 内持久化的采样序列及原始返回采样建立权威决定，准确绑定租约、预算和原始结果，再与独立回执和取消 CAS 协同恢复；所有水位推进路径、历史保留、未知采样及崩溃窗口均需覆盖。这是设计方向，不是已实现或已验证的方案。

G15 的 token 配置复核确认当前预算账本仅对 Agent 调用数和模型轮次预先计量；适配器接口没有可信的逐请求 token 上限和使用量，OpenCode 代理只转发流，无法仅靠现有计数安全实施 token 上限。跨父子范围、取消、未知消耗和重启所需的权威使用量及预留／结算机制尚不存在；当前继续拒绝该配置而非宣称已生效。合成适配器的现有拒绝测试定向通过，不是 token 控制验收。

补充的受控采样测试使用两个真实 SQLite 执行：一个执行保留未确认采样保护时，另一个执行的完成时钟读取仍可成功；前者随后确认采样可推进共享水位。该测试与已有快照顺序检查共 2 项通过（`/tmp/agent-control-080-evidence/completion-global-scope-current.log`）；它只证明保护作用范围，不证明两次观察的实际先后，也不修复监视器竞态。

补充源码级文件桥接检查：合成适配器通过真实 AgentApp 带认证的 HTTP 工具入口请求写入，在路径授权解析后、实际打开前同步将目标目录替换为指向外部的符号链接。实际受约束打开返回 `ELOOP`，桥接返回通用拒绝，外部哨兵未变；恢复目录后同一路径允许写入。测试保留未确认的应用、回调和临时现场，清理补丁须先确认应用及服务退出。本机开放回环后通过（`/tmp/agent-control-080-evidence/file-bridge-path-race-host-final.log`）；最初受限环境为跳过，记录 `file-bridge-path-race-01.log`。这是同步控制的单一交错、源码及合成适配器证据，不是实际并发替换、真实 OpenCode、当前安装包或完整 G03 验收。

G06 补验草稿保留入口和 worker 硬门禁；当前监督者没有向 worker 传递可验证的监督授权。离线修订提前登记监督进程对象、拒绝未确认监督的 worker，并保留有界的异常和清理诊断；pidfd 获取或关闭交接中断仍可能导致所有权未知。普通清理异常不等于已认证的进程树清理，监督输出只在信任所选监督程序的前提下有意义。独立复核所审修订未发现新的明确缺陷，含受控中断和真实监督进程的 17 项检查通过（`/tmp/agent-control-080-evidence/g06-offline-supervisor-final.log`）；没有运行模型调用，逐操作提供商响应证据仍缺，G06 补验继续禁用。

启动与停止交接继续修订：协调器启动及入口以锁内发布状态为准，通知异常时保留异常和清理所有权；停止请求所有者在通知失败后仍尝试撤销，并单独记录请求是否完成。根提交在交接失败时先关闭准入，已有等待者通过有界重查识别围栏；停止报告也考虑尚未完成发布的协调器启动。相关源码组合 80 项通过（`/tmp/agent-control-080-evidence/host-notification-handoff-final2.log`，11.361 秒），涵盖停止报告、根提交和通知交接。此前一个使用合成时钟的中间组合运行卡住并被中断，退出码 130，后续修正后才有上述通过结果。该结果不代表整个停止合同通过：清理线程和撤销线程的启动仍可能阻塞有限期限的停止调用，四项期限测试中这两项失败（`/tmp/agent-control-080-evidence/host-stop-remaining-failures-latest.log`）；旧宿主通知启动异常测试的兼容性差异仍待处理。上述变更未进入最终安装候选。

独立复核在根提交等待和停止报告阶段判定的限定范围内未发现新的明确缺陷，相关模块 25 项通过。停止报告测试为收尾手动启动先前未启动的测试协调器，这不是生产恢复证据。对剩余有限期限缺口的设计核对确认，仅将线程启动移出锁无法防止启动调用本身阻塞；运行中若改由既有协调器撤销，必须验证其被启动或 Bridge 调用阻塞时的语义。未启动宿主则需要在有限停止前已有可承担清理的所有者，同时保留进程退出和准确所有权合同；这两种方案尚未实施或验收。

文件桥接受控检查进一步加入独立线程的目录／符号链接循环替换，并通过同一实际认证工具入口连续请求 30 次写入；至少一个调用者请求区间观察到替换计数增加，外部哨兵保持原值，替换线程和应用均确认退出。允许写入在竞争前单独检查了实际内容。该源码／合成适配器测试在本机回环环境通过（`/tmp/agent-control-080-evidence/file-bridge-concurrent-race-03.log`）；独立审查指出请求区间内发生替换不证明恰好与文件查找重叠，前述受控打开点检查与此并发检查分别提供证据。以上不替代真实 OpenCode、最终安装包或完整 G03 验收。

候选 52 子调用结果交付失败进一步核对：原始成功分支在进入受控响应发布点之前，子调用因检查窗口内 SQLite 锁冲突而取消，父调用随后记录 `database is locked`。当前源码一次复现也未到达受控发布点，子调用在第 0 次尝试取消，父调用仍处于运行状态；该次另一分支通过。两次均未识别持有写锁的所有者，不能归因于响应交付本身或视为已修复。复现现场分别保存在 `/tmp/sdk-child-completed-delivery-evidence-hnq265w1/success.json` 和同目录 `failure.json`。测试夹具现保留原断言及独立关闭异常，避免后者遮蔽前者；相关 3 项定向检查通过（`/tmp/agent-control-080-evidence/child-result-fixture-diagnostics.log`），不代替真实交付验收。另一次添加进程／线程和事务时间记录的原测试两分支在 27.150 秒通过（`/tmp/sdk-child-lock-trace/test.log`），同一 Kernel 文件上的预算采样事务区间有重叠，部分事务报告锁错误；跟踪可能改变时序或丢失事件，事务包装区间也不能证明 SQLite 实际持锁区间，因此该次结果既不证明历史持锁者，也不能覆盖上述失败。

OpenCode 私有运行目录创建现移至准确原生操作登记后、端点和进程获取前；暂时性创建错误只有在该操作的 `not_launched` 回执得到准确确认时才允许按原预算重试。实际 AgentApp、Linux 原生 guard 和本地合成服务器的故障注入验证了目录创建后抛错、重试、相同调用与租约、已提交 effect、认证清理及一次 Agent 计费；连同端点和 guard 定向检查共 16 项通过（`/tmp/agent-control-080-evidence/opencode-workdir-retry-focused-01.log`）。独立源码审查在此范围内未发现可操作缺陷。该测试未使用真实 OpenCode 或模型，不修复套接字获取失败后的未知所有权回归；G12 仍未完成。中英文 Wiki 和控制层文档已更正此前对当前套接字重试的过度表述。

平台能力与平台证据是两项不同缺口：当前 SDK 文件工具后端只支持带 `openat2` 的 Linux x86-64／ARM64；Windows 默认私有工作区可以构造，但文件读、写和列目录操作明确拒绝，非私有工作区注册表也不支持 Windows。上述事实来自当前源码及 Windows 专项测试定义，并非原生 Windows 验收。除补齐 Windows／ARM 运行环境和完整矩阵外，要满足适用的 Windows 文件工具／工作区能力还需相应实现和原生验证。

提交边界原测试在当前源码复测时，两种触发场景均因关闭调用重新抛出协调器工作阶段注入的 `SystemExit` 而失败，日志 `/tmp/agent-control-080-evidence/commit-boundary-current-recheck.log`。现已调整分类：停止信号前捕获的协调器工作中断保留为宿主失败；停止已发出后捕获的中断参与停止异常优先级，即使它来自并发中的工作。真实线程／子进程定向场景覆盖停止交接点注入、工作线程未退出时停止、准确中断传播与清理；独立审查确认该分类和并发停止的取舍。19 项定向检查通过（`/tmp/agent-control-080-evidence/commit-boundary-host-fix-final2.log`）。该修订不证明它是候选 52 原始最终刷新错误的根因，也未修复清理或撤销线程启动本身可能阻塞的期限问题。

再次复核技术重试缺口：同一个不透明 socket 工厂既可能在分配前抛出 EMFILE，也可能在分配后交接前抛出相同错误，现有观察无法区分；按 errno 清除待确认所有权会丢失后一种情况。未来实现需要可信的资源获取与清理证明，当前技术重试失败仍未修复。结果与超时交接也仍未解决：采样水位保存的事务回滚路径同样可能推进共享水位；简单二次检查 Future 或把结果写入旧 evidence 均不能确立预算和决定的权威性。

旧依赖计划升级新增源码级实际 SDK 后继执行检查：合成旧计划先保存生产者终态与预算消耗，经显式升级后核对 Run／根调用预算的额度、原期限和已用量；宿主启动后，通过真实 SDK 调度的后继读取原绑定并完成，Run 两项用量从 1 增至 2，原期限不放宽，计划关闭且旧计划未补造事件（`/tmp/agent-control-080-evidence/dependency-upgrade-real-sdk-04.log`）。首次版本在宿主启动后才注入预算，不能作为该断言的有效证据（`dependency-upgrade-real-sdk-01.log`）；第二版误把静态依赖后继当成根调用的子调用，根调用局部预算预期错误，原始失败保留为 `dependency-upgrade-real-sdk-02.log`。该测试的旧生产者事实、计划生成和适配器均为合成，预算对比是汇总值而非逐笔保留证明；仅证明所测源码场景，不是历史生产数据、真实模型、安装包或全部旧配置兼容验收。

共享时钟竞态补充受控时序：一个执行取得较高的模拟采样并保留未确认保护，墙钟被测试回拨后，另一执行的完成观察先返回较低值，前者随后确认并推进共享水位。新增异常清理检查保留未确认的采样令牌与 Kernel，不重复确认可能已提交的操作；后者的错误为合成注入。独立复核后，上述检查与原快照检查合计 5 项通过（`/tmp/agent-control-080-evidence/completion-global-scope-order-reviewed.log`）。这证明所测交错下返回观察可能早于更高水位确认，不是实际系统回拨记录，也未实现结果竞态修复。

Windows 文件后端准备工作：将普通文件工具能力与仅支持 Linux `openat2` 的共享根、工作区注册表准入分别检查，避免将来添加 Windows 文件后端时误开放依赖 POSIX 路径与锁定语义的注册表。Linux 能力边界的定向检查和 12 项工作区所有权检查通过；共享根检查 3 项通过、1 项因本机回环受限跳过，Windows 原生测试在 Linux 跳过。当前没有实现或启用 Windows 文件工具，该改动不构成 G03 或 G18 的 Windows 验收。

中英文 Wiki 和控制层文档补充名称调用说明：含连字符、以下划线开头或与 `AgentApp` 现有属性同名的合法 Agent 名称可通过 `app.agent(name)` 获取句柄。当前源码用实际 `AgentApp` 的 `coder`、`close`、`_private` 和 `data-reader` 名称检查了句柄选择；未运行模型，不属于 G01 当前安装包验收。

文件能力拆分后的源码定向组合共 26 项、耗时 91.095 秒，以 1 项失败退出：共享文件工具及下游快照测试中生产者仍处于 submitted，观察结果为空，退出上下文时还出现清理错误。原始日志为 `/tmp/agent-control-080-evidence/file-capability-split-focused.log`；本次与其他运行时源码修改并行，尚未查明原因，不能将其归因于文件能力拆分，也不能记为通过。

结果权威改动期间发现旧结算入口硬编码 Kernel schema 12，可阻止 schema 13 下生命周期交付；相关源码已改用当前版本常量。此后一个故意限定两秒的共享文件诊断观察到生产者的 SDK 执行正在运行且已进入适配器，读取和列目录成功，预期拒绝的写入及越界读取被拒绝；控制存储行仍可显示 submitted，不能单凭该字段判断未调度。诊断由人为超时结束，保存在 `/tmp/agent-control-080-evidence/shared-file-short-diagnostic.log`；它与此前零适配器观察不同，但不证明历史失败根因，也不验证下游快照或正常关闭。原测试须待运行时源码稳定后复验。

G06 补验草稿进一步在三个负例中显式要求逐操作提供商响应事实；目前观察器不可用时一律失败关闭，原两个执行门禁保留。离线证据谓词检查 18 项通过，没有运行真实模型，也不能据此将 G06 标记通过。

运行时源码暂时稳定后，按原 `run.wait(80)` 期限和本机回环能力复跑共享文件原测试，通过 1 项、耗时 9.566 秒（`/tmp/agent-control-080-evidence/shared-file-original-rerun-v13.log`）。该测试包括认证工具入口和下游文件快照；适配器仍为合成，不能替代真实 OpenCode 或最终安装包验收。此前 26 项失败和两秒诊断均原样保留，本次通过也不能证明此前失败的具体根因。

结果／超时竞态的线程路径新增 Kernel 权威回执并在原始竞态测试中取得局部通过；受控取消、重开和旧版 v2 存储经公开升级到当前版本的定向检查通过，组合 10 项记录于 `/tmp/sdk-handler-authority-focused-20261104.log`。独立审查发现成功写入与工作线程发布结果之间仍可能由监视器记录错误超时，停止撤销后工作线程也可能继续提交成功；实现者确认这两处需同一权威交接机制处理。提交前时限核查另须区分及时返回事实与存储提交延迟，不能简单将存储等待计入工作期限。当前仅为局部实现，进程模式、未证明事实、故障恢复和上述竞态仍未完成。

G06 验证器新增未接线的身份捕获与有界 OpenAI 兼容文本流解析组件；独立执行 7 项离线检查通过（`/tmp/agent-control-080-evidence/g06-observers-independent.log`）。组件尚未连接实际代理或原生回执，工具调用流及其他格式不视为已支持；未知清理和逐操作响应绑定仍需处理，两道原生执行门禁继续保留。

Windows 文件后端安全设计复核：不能仅靠持有目录句柄并拒绝写入／删除共享，推断重解析状态不会变化。[Microsoft CreateFile 文档](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea)说明共享方式不影响属性访问请求，[文件系统抽象协议](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/4aeefef8-92c3-4abc-af7a-a610caf8a165)允许持有 `FILE_WRITE_ATTRIBUTES` 的打开句柄设置重解析点。`OBJ_DONT_REPARSE` 的一般语义见 [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wudfwdm/ns-wudfwdm-_object_attributes)，但尚未确认用户态句柄相对查找与已有根句柄的完整支持合同及竞争保证。这些资料指出待验证风险，并非已经复现 Windows 逃逸。当前 Linux x86-64 环境也无法运行原生 Windows 正反例；Windows 文件后端继续关闭，未声称实现或验收。

线程结果交接新增受控检查：已提交结果延迟发布超过原期限时不再生成错误超时回执；停止与结果事务竞争时报告未确认并阻止已观察到撤销的提交。4 项源码定向检查通过（`/tmp/sdk-handler-authority-gate-races.log`）。独立复核进一步指出，提交及回滚均失败时同一连接可能读到未提交的自身数据，不能作为持久化证明；另一个等待交接的分支可能没有后续结算回执，交接锁的中断清理亦须核对。实现者确认前两个问题仍待修复；上述局部通过不能覆盖它们，也不表示进程模式或崩溃恢复已完成。

G06 观察器现已接入仍被硬门禁保护的草稿执行路径，按调用身份关联原生清理证据，并在应用关闭后检查代理收尾；尚未运行实际模型。相关离线检查与合成适配器下真实 AgentApp 收尾检查通过，后者 7 项日志为 `/tmp/g06-finalization-candidate51-source.log`。独立复核发现文本流观察器曾把无有效终止状态或错误终止的增量当作完整响应；纯工具调用响应还会被保守拒绝。两点仍须修复或明确支持范围；代理读取时的同步观察也可能影响运行时序。现有检查和门禁不能证明实际 OpenCode 响应及 G06 验收。

G06 观察器继续修订：只认可同一选择的正常终止文本或受限的单个完整函数调用，其他格式失败关闭；独立审查又指出不同响应的内容和终止块可能被错误拼接，已要求每个块包含相同的非空有界响应 ID。22 项离线检查通过（`/tmp/g06-proxy-observer-offline.log`），真实 SDK 代理及本地脚本上游的联合检查和修订后独立复审仍待完成。同步流解析有界但可能改变时序，观察的是上游字节而非客户端实际收到的内容；真实执行的门禁仍关闭。

结果权威与共享连接故障处理仍在修改：提交及回滚失败、事务建立及回滚失败的定向故障注入均已验证拒绝将不明事务视为已提交，并保留原连接所有权；具体实现正在独立审查。18 项组合中 17 项通过、1 项失败（`/tmp/sdk-authority-taint-final-focused.log`）：真实子进程处理器返回时遇到另一采样保护，完成时间判为未知，持久回执仍 pending、执行仍 running。恢复诊断记录了候选成功结果，但这本身不是已结算的权威成功事实；触发后续结算失败的确切原因尚未记录，现场为 `/tmp/sdk-native-entry-packet-clock-xubgr9rt/evidence.json`。以上失败不得以其他定向测试通过覆盖；事实交接与崩溃恢复仍未完成。

该进程场景的后续只读核查发现，测试采集快照之后后台恢复已将同一执行写为 succeeded、回执标记 recorded，但对应监督义务仍未解决；相关记录中的诊断注记不能替代权威清理／完成证明。现在已确认存在结果结算与监督义务不一致，具体恢复顺序及修复仍在排查；原始测试失败不变。共享连接独立审查还发现只读事务回滚失败遗漏隔离、嵌套 BEGIN 可能回滚外层事务、清理中断的异常优先级不一致；均为源码发现，须通过注入复现并修复后重审。

G06 的响应观察额外经过当前源码真实 `MeteredProxy` 和本地合成上游两项联测：正常完整流可观察到、截断流保持未知，记录 `/tmp/g06-metered-proxy-local-host-final.log`。首次受限环境因回环权限失败，首次宿主运行因测试上下文缺少 `cancelled()` 失败，均保留原日志。该测试的上下文与上游为合成，未调用 OpenCode、外部模型或真实原生清理回执；修订后独立审查进行中，门禁仍关闭。

响应 ID 修订和本地代理联测的独立源码复审确认：每个数据块均检查相同的非空有界 ID；联测覆盖真实代理转发、计量回调与关闭，但其身份和回执均为合成。本次所审范围未发现其他明确缺陷；复审未运行测试或模型。入口、worker 和监督授权仍有三个无条件禁止真实执行的门禁，G06 补验及当前候选验收尚未完成。

token 预算的独立代码调查：现有代理透传请求和响应，不具备已验证的输入加输出总 token 上界、可信逐请求用量及不明请求的提供商对账；单纯限制输出不能保证请求总量。现有应用预算账本也不能直接作为并发父子范围的 token 硬上限。可行实现至少需要供应商可验证的总量与结算合同、网络发送前跨全部祖先范围的原子预留、未知请求保留和权威对账。当前源码继续在执行前拒绝非空 token 配置；没有将此调查计为 G15 通过。Goal 的预算表明确要求秒数、调用数、模型轮次和局部收紧，未逐字指定必须提供 token 上限；注册表已公开该字段而行为拒绝的交付缺口仍需解决，不能据此擅自更改合同。

共享连接隔离复审后修正了只读事务和嵌套事务的所有权，以及操作、清理、回滚三重异常时的中断优先级。四项所有权注入、11 项运行时／竞态组合，以及单独的三重异常检查通过，日志分别为 `/tmp/sdk-authority-taint-ownership.log`、`/tmp/sdk-authority-taint-review-fixes.log`、`/tmp/sdk-authority-taint-interrupt.log`。另在真实参与式临时数据库中丢弃调用者引用并执行垃圾回收，验证未确认连接仍阻止独占维护；在受控回滚和关闭后维护才获准（`/tmp/sdk-authority-taint-lifetime.log`，2 项）。受控并发关闭定向检查验证取得锁后重新检查未知状态（`/tmp/sdk-authority-taint-concurrent-close.log`，1 项）。这些检查均限当前源码、临时库与所测交错，不解决进程恢复的权威事实缺口，也不代替安装包回归。

停止期限独立复验：原四项交接测试中，协调器启动竞争两项通过，未启动宿主的清理线程启动、运行中撤销线程启动两项仍失败，保留 `/tmp/host-stop-deadline-independent-source-20261104.log`。测试释放并等待其创建的准确所有者。预先建立守护线程需处理 fork 后线程消失及解释器退出顺序，普通 atexit 等待会晚于用户后注册的退出回调；目前尚无满足既有生命周期与有限期限合同的完整实现。

针对进程完成时间未知后被后台错误提升为成功的问题，工作区增加恢复防护：未认证旧记录不直接提交为 Kernel 结果；已提交的宿主裁决只有匹配当前存储身份、租约、结果、保留预算与清理证据才可关联。原有受控取消先胜出场景在不改变测试断言的情况下通过；新检查覆盖预算不匹配、缺少旧候选结果和错误存储／清理证据。独立审查发现较新尝试下仍有绕过分支，后续已加入拒绝和定向负例（五项，`/tmp/sdk-authority-unknown-catch-final.log`），修订后独立复核进行中。该防护使部分旧线程模式未知时钟重启恢复保持 pending，自动恢复与原测试兼容仍未解决；原真实进程测试也未宣布通过。

G06 验证器启动方案的只读调查确认现有 `agent_fault_supervisor.py` 已实现子收养和确认无子进程后的清理报告；实验性的额外交接原型不能替代这些证明，已移除未接入的原型与测试，仅保留本地测试日志和审查发现。现有监督器的合成自检通过（`/tmp/g06-existing-supervisor-selftest-python3.log`），覆盖脱离原进程组的后代和观察失败场景；没有证明整个 G06 控制器退出时的外层清理，也没有运行模型或当前候选 G06。验收门禁保持关闭。

补充的外层控制器监督路径使用同一现有监督器，19 项本地受控检查通过（`/tmp/g06-supervision-outer-route-v1.log`）；正常合成控制器成功，异常控制器的脱离后代退出后仍因需要信号清理而报告未确认。路径尚未接入被禁止的验收入口，独立审查进行中；它不证明真实 OpenCode 或 G06 验收通过。

线程未知完成事实新增真实执行线程的 Kernel 持久化和后续裁决：原 `test_completion_wrapped_restart` 两种不变断言通过（`/tmp/sdk-authority-owned-fact-automatic-rerun.log`）；首个失败尝试保留 `sdk-authority-owned-fact-automatic-restart.log`。相关 22 项源码定向测试以及实际处理器的跨执行采样保护、超过原期限保持未知检查通过，日志为 `/tmp/sdk-authority-owned-thread-focused.log`、`/tmp/sdk-authority-owned-thread-late-cross-sample.log`。该实现正在独立审查；实现者指出停止或撤销后仍可能保存事实，须核对后续是否会错误裁决成功。进程执行的同等事实生产、崩溃窗口和重复效果检查仍未完成，这些结果不改变完整回归结论。

G06 外层报告修订后，本地 22 项定向检查通过（`/tmp/g06-outer-review-fixes-v2.log`），暂定报告和最终报告已分开，控制器输出不再进入监督器报告管道，空命令在启动前拒绝。独立审查仍发现最终发布未充分绑定指定解释器、候选包和具体场景，也缺少独占发布及并发启动防护；本次尚不能用于验收。实际入口和 worker 禁止执行的门禁仍然保留。

线程完成事实的独立审查确认三个尚未修复的范围内问题：事实可能在运行时停止或撤销后保存而随后被错误授权；恢复的新采样只是完成时间的上界，不能直接作为 `ExecutionResultV2.completed_at`；读取与写事务在物化 JSON 前未对记录大小、恢复期限和数据库查询做完整有界检查。现有测试尚未覆盖带真实回执的撤销竞争、事实提交前后崩溃或原始完成时间证明，先前定向通过不能覆盖这些问题。`ExecutionResultV2` 的当前版本没有时间上界字段，现有消费者将 `completed_at` 作为实际完成时间使用；不能静默改变其语义。上述问题正在修复，进程事实生产仍未完成。

完成时间补充调查：原始处理器返回采样和预算在记录中保留，但重启后当前全局水位可能含返回后的其他采样，现有记录无法普遍还原当时顺序；将当前水位或恢复时新采样当作原始完成时间均缺少证明。只读分析提出一个可能可恢复的保守子集：相关采样全部确认后，若当前持久水位不大于原采样及原预算投影所得值，且时钟连续性和原执行权限均得到验证，可进一步核对使用原值；此方案尚未实现和验证。运行时停止发生在事实写入之后、恢复之前时，也需要持久化的裁决／撤销顺序，不能以重启后缺少内存标记当作未停止的证明。

审查后已撤回前述会错误提升未知事实的实验性裁决代码，包括未有界读取和用恢复时间充当完成时间的路径；目前只保存标记为 unknown 的事实，不以此自动发布结果。七项未知结果／取消防护定向检查通过（`/tmp/sdk-authority-unsafe-promotion-disabled.log`）。此前原线程重启测试的两项通过只适用于已撤回的修订；原测试按原断言重跑后失败，执行仍 running、原完成权威未确认（`/tmp/sdk-authority-owned-fact-known-unknown-original.log`），不能据此将原测试记为当前通过。持久停止顺序与可证明的原始时间仍需实现。

G06 外层发布器进一步改为自行构造候选控制器命令、核对候选和环境，并用独占预留及不覆盖方式发布报告；22 项离线检查通过（`/tmp/g06-outer-review-bind-v4.log`）。独立复审指出总等待不包含所有可能阻塞的启动／收尾，文件发布后中断的结果也需要核对，最终报告还须保留经过核验的候选及案例绑定；这些仍在处理，入口未接线且门禁关闭。

上述发布器随后将期限明确限定为决定与校验时点；阻塞的启动、收尾和发布本身不受该期限保证。发布前暂存中断会记录未尝试发布及临时文件、文件描述符清理是否确认，已存在的非本次暂存文件不覆盖。最终报告保留的案例摘要仍依赖可信控制器，引用的证据文件可变。22 项离线检查通过（`/tmp/g06-stage-review-v1.log`），独立复审确认上述范围；控制器入口尚未接线，真实模型和最终候选 G06 尚未重跑。

进一步审查发现线程完成结果的现有快速提交也存在停止事件与数据库提交无法原子排序的问题。为避免把撤销后的结果误认作权威成功，当前实验性快速授权已关闭；已撤回的恢复授权也保持关闭。这是临时安全回退，不是完整修复：原重启成功测试仍失败（`/tmp/sdk-authority-disabled-all-promotion.log`），另 15 项定向检查通过、6 项依赖快速授权的测试失败（`/tmp/sdk-authority-no-promotion-focused.log`）。取消已有持久事务，停止、关闭、监控超时和进程撤销仍须与结果提交建立可证明的顺序；重启恢复还须证明原始完成时间。

原始完成时间复核另以真实 SQLite 交错复现：采样后、读取前另一事务提交较晚水位时，首次捕获曾将该水位误报为处理器完成时间。当前源码对首次捕获及恢复读取均新增保护，要求无法证明原始水位时报告未知；两项真实交错检查见 `/tmp/sdk-completion-clock-later-floor.log`，恢复时钟模块 29 项检查见 `/tmp/sdk-completion-original-floor-module.log`。独立审查还发现线程在完成采样后再次检查预算，采样期间跨过期限可能把及时返回误判超时，正在修复；这些定向结果不证明重启恢复或安装回归通过。

上述保护尚不满足兼容要求：未修改的 `test_actual_committed_expiry_floor_survives_wall_rollback_without_mutation` 因合法的采样前已提交水位被拒绝而失败。独立审查确认标量水位不足以区分采样前和采样后的提交；采样前合法记录与采样后交错均须成立，不能通过永久返回未知代替修复。原结果和 44 项相关通过／1 项错误保留于 `/tmp/sdk-authority-sampling-lifecycle.log`。

G06 外层监督入口已接线，但实际控制器和 worker 的禁止门禁仍保留。26 项受控检查（`/tmp/g06-integrated-outer-v3.log`）覆盖模拟四级进程树与受阻真实入口；内部路由参数本身不能证明外层监督授权，当前候选与真实模型仍未执行。接线正在独立审查，三个原始案例窗口保持 650／350／650 秒，外层期限可能提前终止但不会延长案例预算。

后续为既有 Linux 监督器新增可选的启动关系验证，候选控制器和 worker 在执行切换前后核对存活进程身份与父子关系；旧调用默认不启用。29 项受控检查及既有监督器 3 项自检通过（`/tmp/g06-launch-authority-v2.log`、`/tmp/g06-launch-authority-legacy.log`）；这些只验证可信同用户环境中的存活关系，不证明最终进程树清理或真实模型结果。独立复审进行中，执行门禁仍关闭。

随后依据独立审查补充了直接 case-worker 无授权拒绝及业务入口未运行检查，并以已验证的监督关系取代三个无条件草稿门禁；选定候选中的监督器须与当前已审查脚本一致，加载模型配置之前即检查。30 项当前源码无模型检查和一项复制入口合成联测通过（`/tmp/g06-authorized-entry-v1.log`、`/tmp/g06-synthetic-authorized-entry-v1.log`）。复制入口只替换候选校验／环境和案例体，实际控制器、worker exec 及两层监督均参与；该联测不证明真实 SDK、提供商、候选包或 G06 通过。最新门禁替换正在独立复审，尚未启动真实模型。

上述门禁替换的独立最终复审在可信同用户控制器／监督器假设下未发现新的具体阻塞缺陷，确认案例期限及两层清理证据均保留；审查没有重跑测试。候选源文件路径仍可变，真实运行时必须使用包含匹配监督器的最终候选，并另行验证实际模型、SDK 清理和 G06 正例与隔离；目前源码和最终候选尚未稳定，尚未发起该真实运行。

线程完成与停止的生命周期顺序已有一版实现，受控数据库提交停顿与停止竞争、原停止竞争和取消先胜出三项定向检查通过（`/tmp/sdk-lifecycle-stop-races.log`）；停止请求使后续 handler effect 权限检查失败，但检查与实际操作开始之间仍有交错窗口，不能宣称所有停止后的外部效果均已阻断。直接 `request_stop` 可能等待持锁提交，宿主有限等待必须另行复核。线程预算判断改用原始完成样本，50 毫秒期限／70 毫秒读取延迟的边界检查通过（`/tmp/sdk-completion-budget-boundary.log`）；进程模式开始采用该视图，但完整原生期限交错和独立审查仍未完成，前述墙钟回退失败仍在。

候选 52 子调用交付原始现场进一步核对：父调用返回 running、result 为 null；该次子调用在开始执行前以 attempt/fence 0 取消，原因记录为原预算内检查点读取耗尽。父调用保存的原始异常为 SQLite `BEGIN IMMEDIATE` 报 `database is locked`，测试要求的成功结果发布闸门没有到达。原始文件为 `candidate52-consumer-evidence/sdk-child-completed-delivery-evidence-yff53v3u/success.json` 和同目录 `success/parent-exception.json`。这解释了该次错误的直接链路，但现场不足以确定持锁者或具体锁竞争根因，也不能视为当前源码已修复。

预算视图的浮点舍入边界经复审确认已修正；最新组合检查为 20 项通过、原墙钟回退测试 1 项错误（`/tmp/sdk-authority-latest-review-tests.log`）。进程路径仍接受完成时间与 worker 预算视图相互矛盾的中间分类；独立复现了截止 101、完成时间 102、视图时间 100 仍分类为 ok，尚未证明最终 Kernel 会错误提交。原生 worker 可能在发送首个返回数据包前耗尽工作期限，线程协调器先退出后的已提交回执也尚需恢复；这两项均未完成。

进程预算视图随后的源码修订要求原始完成时间、所提供的预算视图时间及入口约束一致，矛盾的已提供视图保持未知；中间分类负例、有效对照及实际原生成功／失败恢复检查通过（`/tmp/sdk-process-view-exact-timestamp.log`）。该视图来自 worker，只是待核对的事实，不能代替 Kernel 权威裁决；修订正在独立复审，原有墙钟回退、首个返回数据包和迟到回执缺口不变。

独立复审确认前述不一致视图被拒绝，但发现缺少视图仍会回退到旧入口检查点，可能错误地作出及时完成的中间分类；过大整数也可能使有限数检查抛出未处理异常。入口确认前的真实失败是否会被新的未知时钟分类掩盖尚待实际进程验证。以上均正在修复，尚未证明它们造成最终 Kernel 错误提交。

后续修订对缺失／空视图及过大整数保持未知，真实 fork worker 的入口失败仍保留原始 handler_error（`/tmp/sdk-process-view-real-entry-failure.log`）；八项组合定向检查通过（`/tmp/sdk-process-view-final-focused.log`）。旧 Windows 清理水位测试的合成成功输入补充了原始样本对应的完成时间与预算视图，原有清理水位断言未改；Windows worker 源码会调用相同的捕获函数，但这不构成原生 Windows 验证。独立复审进行中。

格式错误或时钟域不兼容的 worker 预算数据现也保持未知，受控入口错误仍保留；八项检查通过（`/tmp/sdk-process-view-malformed-final.log`）。独立复审确认异常处理限于 worker 数据，可信入口及宿主观察的异常未被静默吞掉；该范围没有发现新的明确问题，未验证原生 Windows。线程迟到回执调查确认 `completion_handoff_pending` 当前可以不产生 settlement 记录：协调器返回后 worker 才提交时，重启恢复无法仅靠现有待处理回执发现该结果；准确授权记录与持久交付义务仍须接通，不能靠盲目重放补救。

当前源码的提交边界原测试再次通过（`/tmp/sdk-current-commit-boundary-recheck.log`，1 项、1.750 秒），只说明所测两种触发情形本次通过；候选 52 的最终 Bridge 刷新错误没有原始底层异常，不能据此认定其根因或最终安装回归通过。停止期限原四项再次复现两项失败：清理和撤销所有者的 `Thread.start()` 可能阻塞；协调器启动竞争的两项通过。独立调查未找到同时覆盖解释器退出、迟到提交者和 fork 的可靠小型修复，未改断言。

完成时钟的独立审查确认：仅有当前持久水位不足以区分处理器返回前与返回后的提交。额外的提交确认可提供保守顺序证明，但不能延长原操作期限或把未知提交当作成功；Linux 同一 boot ID 下的不同时间命名空间也可能有不同的启动时钟偏移，跨进程比较需要验证时钟域。该方案尚未落地；此前墙钟回拨的原测试错误及自动恢复缺口仍然存在。

迟到提交缺口已通过真实 SQLite 提交闸门复现（`/tmp/dispatcher_commit_handoff_probe.py`、`/tmp/dispatcher_commit_handoff_probe.log`）：完成权限检查后、事务 COMMIT 前阻塞，监视器报告 `completion_handoff_pending`，释放后原事务真实提交成功；精确执行结果在关闭和重启后仍为成功，但结算回执为空、恢复扫描无记录。此次 `run_once` 实际在提交后才返回，因此不证明它在提交前返回。另一个在进入完成事务前阻塞的探针只观察到权限撤销、结果未知，没有成功提交；不得把两个场景混为一谈。

提交边界失败诊断已改为在最终 Bridge 刷新的通用错误下保留实际异常链；原异常仍按身份保留，中断优先级不变。定向三项通过（`/tmp/sdk-final-flush-cause-focused.log`），独立复审未发现此修改引入的具体问题；这不补回候选 52 未保存的原始异常，也不构成该回归根因修复。

实际提交闸门现有可重复回归 `tests/test_completion_late_commit_receipt.py`；当前原断言失败：真实提交及重启后结果存在，但准确回执为零。证据 `/tmp/sdk-late-commit-receipt-ninqm3bz/evidence.json` 显示驱动、工作线程退出且两个运行时关闭；故障仍待修复。

在允许本机回环的环境中，启动重试定向测试复现 `recovery_required` 错误，而未知创建交接负例通过（`/tmp/sdk-retry-loopback-independent.log`）。测试报告已输出后进程未退出，核对其无子进程后对本次启动的精确测试进程发送 SIGTERM，最终退出码 143；这不证明应用清理成功。不能将不透明的套接字创建异常一律认定为无资源，也不能将该重试记为通过。

同进程、同线程的已确认水位提交已增加局部证明，原墙钟回拨测试和提交后水位负例在定向测试中通过（`/tmp/sdk-clock-local-ack-ownership.log`）；该证明不覆盖跨线程、跨进程或重启。独立审查发现可变数据库路径可能指向具有相同存储身份的旧副本，路径绑定正在修正。时钟、全局采样和预算包装组合运行 48 项，47 项通过、1 项因包装结果缺少原测试要求的 `code` 而报错（`/tmp/sdk-completion-clock-combined-current.log`）；该组合仍未通过，也没有覆盖后续路径修订。

路径现绑定到原连接的规范路径，使用同存储身份的另一数据库副本进行的真实提交交错被拒绝，同目标符号链接仍可用（`/tmp/sdk-clock-canonical-path-binding.log`）；独立复审在遵守 SDK 存储维护协议的范围内未发现新的具体问题。完整时钟模块 45 项通过（`/tmp/sdk-completion-clock-path-v1.log`，12.984 秒）。上述组合中预算包装原测试的错误仍未解决：当前保留原始未知完成事实及证明，但没有按旧断言恢复为终态；不能通过改断言取消既有兼容要求。处理数据库路径时也修正了 `~` 展开后的父目录创建，使用临时数据库的实际打开、关闭检查通过。

迟到提交交付的持久化基础已加入源码：Kernel 可在精确租约下登记不可变意图，显式 v13 到 v14 复制升级保留旧数据而不猜测旧意图。14 项定向检查通过（`/tmp/sdk-intent-kernel-final-focused.log`），另有 7 项历史版本兼容检查通过（`/tmp/sdk-intent-historical-fixtures.log`）；独立审查没有发现该基础接口的具体阻塞问题。日志侧 v6 基础接口及 v4／v5 兼容测试分别通过 13 项和 40 项（`/tmp/sdk-v6-journal-compat.log` 为后者）。随后独立审查发现元数据可能无界解码、关闭错误可能掩盖中断，修订后的 15 项日志定向检查通过；修订仍需独立复核。以上接口尚未接入实际执行与恢复，真实迟到提交回执回归仍失败，设计及剩余验证见 [完成交付设计](SDK_0_8_0_COMPLETION_DELIVERY_DESIGN.md)。

停止期限的两个原测试再次失败（`/tmp/sdk-host-blocked-start-recheck.log`），新线程启动受阻时尚无同时满足有限返回和退出清理所有权的实现。技术重试的故障注入无法区分创建前失败与创建后资源交接未知，因此不能仅依据异常类型认定清理成功；该失败仍未修复。未启动新的完整回归或 CI。

对上述新基础接口的继续审查发现，Kernel 意图登记目前尚不能证明登记先于 handler 进入，既有权威行也不保存原始返回时预算；不能据此制作安全的交付证明。日志独立复审以真实临时数据库复现了超长 schema 名称进入 Python 解码，以及旧版打开入口在 v6 独占维护期间先访问数据库后才拒绝；尚未证明实际替换损坏。这些缺口正在修复，迟到提交恢复仍未接线。

本地原生环境盘点确认 Linux x86-64 上有 Python 3.10、3.11、3.12 和 3.13 解释器；前三个额外版本的旧候选环境不代表当前安装包通过。当前 PATH 未发现 Windows／ARM 原生执行环境或 Wine／QEMU；尚未检查远端或证明其他未列出的设备不存在，G18 的相应平台证据仍缺。

后续日志修订为所有打开入口增加维护参与，并在 SQLite 侧限制 schema 元数据；18 项 v6 定向测试及 49 项 v6／v5 测试通过。独立审查通过了超长 schema、旧入口在独占维护下拒绝、v4 到 v6 复制等三个实际数据库检查，但发现 v2／v3 复制升级在调用者已持有源维护锁时会被新参与检查拒绝；普通不持锁调用的旧测试通过。复制失败时目标连接关闭未知也须防止删除目标；源验证的关闭所有权仍待处理。调用者持有的维护锁不能只靠保留 Python 对象延长其物理寿命，这些兼容及所有权问题未解决，不能将日志修改视为最终完成。

Kernel 新增了未进入状态的登记检查，8 项定向测试通过（`/tmp/sdk-intent-pre-entry-focused.log`）；但独立检查确认旧运行和既有 v14 登记缺少可证明入场顺序的版本标记，仍不能作为安全交付证据。实际认领、入场门禁和原始预算事实的持久化都尚未接线。

后续 Kernel v15 基础支持在新认领事务中选择性创建入场标记与启动事件，并要求在两个 handler 入场点先完成对应登记；旧认领和历史 v14 记录不推断为已受保护。续租、损坏标记、替换写入和迁移等路径经定向测试及独立审查；登记与扫描现遵守较短的继承控制期限，包含真实提交前超时回滚和扫描超时后再次访问的 35 项组合通过（`/tmp/sdk-admission-deadline-20261104.log`）。这是当前源码的基础验证，不证明运行时跨存储接入、原始返回预算持久化或迟到提交恢复已经完成。

旧版日志升级的独立审查复现了目标路径在创建和打开之间被替换，导致其他数据库被覆盖；合作方维护锁和打开前身份检查仍有检查后替换窗口，不能作为完整修复。临时文件及安全发布方案正在实施，尚未完成审查和验证。

候选 52 中失败的终态取消用例，在允许本机回环的环境下针对当前源码单独重跑一次通过（`/tmp/sdk-dependency-cancel-loopback-20261104.log`，合成适配器，5.390 秒）；默认环境因禁止本机回环而跳过（`/tmp/sdk-dependency-cancel-recheck-20261104.log`）。这不能确定候选 52 的失败根因，也不能证明安装包全量回归通过。

预算包装已调整为：结果完成时间未知时，后续采样只用于识别时钟连续性未知，不用较晚的采样判定原业务结果超时；相关 12 项检查通过（`/tmp/sdk-budget-wrap-authority.log`）。原预算包装测试仍在重启恢复步骤失败（`/tmp/sdk-budget-wrap-focused.log`）：现有记录尚不足以证明原完成决定的授权。该修改正在独立审查。

复审发现监控采样结束后可能覆盖已发布的原始结果；修订后以未知和到期两种采样覆盖该顺序，并保留真实返回值与原始证明，4 项定向检查通过（`/tmp/sdk-monitor-order-focused.log`）。独立复审确认原竞态的修复；重启恢复仍未通过。

为迟到提交新增的 Kernel v16 完成权威基础在初版 9 项定向检查通过后，独立审查复现了两项阻塞：返回观察在序列化与锁等待之后采样，不能准确代表 handler 返回时刻；读取接口接受内容为空的规范 JSON，未验证与终态、登记及预算的完整关联。两项均未解决时不得据此生成交付回执。运行时尚未接线，初版测试记录为 `/tmp/sdk-completion-delivery-authority-v16-tests.log`。

v16 修改后的历史兼容组合首次运行 45 项，16 项失败、10 项错误（`/tmp/sdk-v16-history-before-fixtures-20261104.log`）；其中已定位的夹具问题包括从当前库构造旧版本时残留新表，以及目标版本断言和 v15 输入引用过时。正在修正夹具并重新检查全部错误，不能将首次结果记为通过。

上述五个历史兼容测试模块更新夹具后，45 项通过（`/tmp/sdk-v16-history-after-fixtures-20261104.log`）；旧版本升级后的新增完成权威表保持为空。v16 读取修订增加同一已提交快照中的执行、登记、原始观察、决定、预算、时钟和 Kernel 身份关联校验，10 项定向检查通过（`/tmp/sdk-completion-delivery-authority-v16-readback-tests.log`），仍待独立复审。handler 返回边界采样及运行时接线仍未解决。

旧版日志升级改用私有暂存、硬链接不覆盖发布，并持有公开目标的维护锁；当前源码的 35 项相关检查通过（`/tmp/sdk-legacy-staged-public-lock-20261104.log`）。独立审查另复现确定失败时暂存文件未清理，以及公开锁获取失败时异常未指明暂存路径（`/tmp/sdk-legacy-review-repro.log`），正在修复。`open_readonly` 现创建维护锁文件，与原有不创建存储的接口合同不同；目录不可写时的失败由打开方式推断，尚无实际权限复现。不得把该版本当成旧 API 已兼容。

后续复审确认前述两种确定失败的暂存遗留已修复（`/tmp/sdk-legacy-copy-rereview.log`，19 项），但又复现私有暂存锁释放后、协调文件删除前，另一协作参与者可持有共享锁（`/tmp/sdk-legacy-review-repro-v2.log`）；该竞争待修复。前述 35 项早于此次复审，不能证明这一场景通过。

v16 完成权威读取的复审确认空对象及已测关联错误会被拒绝，但修改原始返回预算并重算视图后，当前读取仍可能接受变更后的记录（`/tmp/authority_v16_review.log`）。这个探针从合法成功已提交的状态开始，证明返回证据的原始性缺口，不证明可以借此授权新的成功。正在设计同事务保留原始记录对照；不能用较晚收紧的预算倒推原始预算。返回采样还涉及监控、子调用、预算样本登记与进程边界，现有发布记录缺少足够的先后关系证明，正在梳理完整协议。

v17 基础以同一事务保存返回记录见证、决定和终态，14 项见证检查及 45 项历史兼容检查通过（`/tmp/sdk-v17-witness.log`、`/tmp/sdk-v17-migration.log`）；旧 v16 事实不会被补造见证。独立复审在临时数据库中修改持久预算截止时间后，复现决定预算比原始预算宽松仍被接受（`/tmp/sdk-authority-budget-extension-review.log`）；尚未发现受支持的 SDK 更新会放宽该约束。此基础仍未接入运行时，真实返回边界采样和完整预算校验均未完成。

两个真实运行时的受控探针验证了不能直接在结果提交前写普通待处理回执：第二个运行时可据此抢先将 running 执行改成 succeeded，原所有者随后提交失败，首个运行时关闭还报告未持久化结果（`/tmp/sdk-journal-first-probe-9yryr0g5/probe.json`）。对照中，原所有者先提交，第二个运行时随后记录相同结果，双方正常关闭（`/tmp/sdk-journal-first-probe-hhgf6mlw/probe.json`）。两者均为临时库上的线程交错，并非进程崩溃验收；新协议须使用不授予完成权限的候选记录，并核对准确的已提交权威。

旧版日志升级暂存清理改为在数据库清理后保留协调文件和目录，避免已有参与者失去锁命名空间；23 项定向检查通过（`/tmp/sdk-legacy-stage-retained-coordination.log`），但小型目录会累积，方案仍需独立复核。旧版只读接口的兼容问题未解决：尝试在受限环境降权复现不可写目录时，降权系统调用本身返回 `EINVAL`（`/tmp/sdk-readonly-permission-probe.log`），因此不能把目录权限失败当作已实测。只读打开创建协调文件这一接口行为差异已确认。

另以未配置协调文件的临时旧版日志实际打开，观察到只读接口额外创建 `.sdk-lock` 和 `.sdk-lock-anchor`（`/tmp/sdk-readonly-creates-lock-probe.log`）。先无锁读取 SQLite 版本再决定是否参与维护也不能直接修复：独立探针在 v6 独占维护期间成功无锁读取 schema（`/tmp/settlement_preflight_exclusion_probe.log`），违反现有「版本发现前参与维护」约定；复制升级、SQLite 日志文件和跨平台行为也不能只凭文件 inode 判断安全。

上述 v17 预算校验已补充写入和读取两侧检查：原约束不得消失、放宽截止时间或减少预留，合法收紧和新增约束保留；不兼容的时钟域拒绝。17 项定向检查通过（`/tmp/sdk-authority-lineage.log`），正在独立复审；未发现受支持的 SDK 写入路径触发此前临时库篡改场景。该基础仍不证明真实返回采样、运行时接线或故障恢复。

旧版暂存清理经另一位未参与实现的审查者复核，三个定向用例通过，未发现新的具体不安全删除（`/tmp/settlement_legacy_cleanup_independent_review.log`）。此结论限于协作参与者和本机 POSIX 受控场景；目录与协调文件无自动回收上限，发布或关闭结果未知时可能保留数据库及锁，Windows 和真实崩溃尚未验证。

真实 handler 返回边界的独立探针在限时内返回后，令副作用信息读取延迟 0.35 秒；现有采样发生在延迟后，预算剩余变成零（`/tmp/sdk-return-delay-repro.log`）。探针调用实际 handler 包装及采样函数，使用真实临时 Kernel，但没有驱动完整 Runtime；它证实后处理时间可能被算入执行时间。简单前移现有采样仍有读者生命周期登记及并发预算快照顺序问题；进程模式还须解决工作进程与监督者的真实返回交接，尚无经过验证的完整修复。

v17 预算谱系复审另以临时库中的直接故障注入构造较早的决定墙钟：即使两个时钟处于同一域，读取仍接受低于原返回预算水位的决定（`/tmp/sdk-lineage-clock-review.log`）。这是权威记录完整性检查缺口，尚无证据表明受支持的 SDK 更新会造成此状态；正在补充原始预算向决定时刻投影的校验。

完整线程 Runtime 的临时库探针进一步复现实际结果：handler 在执行截止前返回，副作用读取被闸门阻挡至截止后，释放后该执行终态为 `timed_out`；驱动退出且 Runtime 正常关闭（`/tmp/sdk-full-runtime-return-delay-tr_2vb3u/evidence.json`）。这是受控后处理延迟，证明现有完整调用路径会将该次执行判超时；不代表进程或 Windows 路径已经实测。

针对上述独立注入的决定时钟水位缺口，v17 写入先保守地将原返回预算水位投影并合入决定预算，读取校验也拒绝低于该水位的决定；19 项定向检查通过（`/tmp/sdk-authority-clock-floor.log`），仍需独立复审。这个修订不解决完整 Runtime 的返回采样缺陷。

独立复审确认先前注入的时钟回退现被拒绝，19 项权威测试通过；10 万组固定种子、同一时钟域的投影与合并未复现新的舍入错误（`/tmp/sdk-lineage-clock-review-after.log`、`/tmp/sdk-clock-floor-review-tests.log`、`/tmp/sdk-clock-floor-rounding-review.log`）。这些不是穷尽或跨平台证明。当前源码重跑真实迟到提交用例仍失败：提交成功后准确结算回执为零（`/tmp/sdk-late-commit-v17-current.log`），基础接口尚未接入实际恢复链路。

完整 Runtime 的限时返回缺陷已增加不修改原合同的回归测试 `tests/test_runtime_handler_return_before_effect_collection.py`。测试只在实际 handler 线程进入效果收集时阻挡，并确认该时刻早于截止时间；最终源码运行的前置条件、驱动退出和 Runtime 关闭均成立，但成功断言因实际 `timed_out` 而失败（`/tmp/sdk-handler-return-before-effect-final.log`）。此前一次测试自身存在首次观测竞争、前置条件失败（`/tmp/sdk-handler-return-before-effect-current.log`），已修正并保留该记录；最终失败是尚待修复的业务行为。

旧版只读不创建存储的合同也加入了 `tests/test_settlement_readonly_legacy_compat.py`；对没有协调文件的临时旧版日志，检查后目录多出两项锁文件，当前测试按原合同失败（`/tmp/sdk-readonly-legacy-compat-current.log`）。

运行时接入复核发现还缺少 v6 日志的持续激活所有者：当前每次日志连接分别参与维护，不能证明意图确认、Kernel 登记和 handler 入场之间始终绑定同一日志；现有入场流程还会在登记后新建超时期限。需要先明确激活句柄及其物理释放、维护竞争和失败所有权，再把同一个原始期限贯穿跨库登记和入场。当前未接线，旧版只读兼容问题也仍未修复。

日志激活审查发现更底层的 POSIX fork 竞争：父进程持有共享参与锁时，子进程退出继承的参与上下文会对同一打开文件描述执行解锁，使维护方在父进程仍处于上下文中时取得独占锁（`/tmp/sdk-participant-fork-review.log`）。这不仅影响拟议的长期句柄，也影响 fork 时存活的现有短操作和参与式 SQLite 连接；正在独立复核。仅阻止子进程解锁并不自动授权其继续使用继承的连接，完整的 fork 后所有权仍须处理。

针对只读兼容，直接在数据库描述符上增加锁不是现有协议的简单替代：同一路径替换后的不同 inode 可分别加锁，Linux 上 SQLite 也不自动遵守 `flock`（`/tmp/sdk-db-flock-probe.log`）；旧进程、锁顺序、只读源和 Windows 行为均需要独立协议及原生验证。当前未将此方案当作修复。

共享参与锁的清理现区分创建进程：fork 子进程关闭自己继承的描述符，不再向同一打开文件描述发送解锁。真实 fork 定向及维护锁／连接关闭回归分别通过 5、21、6 项（`/tmp/sdk-participant-fork-fix.log`、`/tmp/sdk-maintenance-fork-regression.log`、`/tmp/sdk-maintenance-connection-fork-regression.log`）。独立复审确认这修复了所测子进程清理路径，但又复现 fork 发生在加锁过程中时父子都进入参与上下文、父进程解锁后子进程仍以为持锁（`/tmp/sdk-fork-during-acquire-probe.log`）；该边界仍待修复。上述修改不证明继承的 SQLite 连接或长期激活句柄已具备完整 fork 安全，Windows 也未验证。

后续增加参与锁取得过程中的进程身份检查：受控 fork 发生在打开、加锁、身份校验及退休检查等位置时，子进程拒绝进入；独立实测子进程描述符已关闭，父进程的锁仍生效，维护租约旁路也有独立检查（`/tmp/sdk-fork-acquisition-close-review.log`、`/tmp/sdk-lease-bypass-fork-review.log`）。当前维护与连接组合 28 项通过（`/tmp/sdk-maintenance-fork-all-current.log`）。这并非任意时刻 fork 的原子屏障：信号处理器在最终 PID 检查与入场之间、或清理 PID 检查与解锁之间 fork 仍未解决；代码现明确禁止在取得、使用或释放参与上下文期间 fork，子进程须新建自己的参与者和连接。继承连接与长期激活的完整 fork 安全仍未证明。

POSIX 共享参与锁后来改为仅关闭描述符释放，不再显式解锁共享的打开文件描述；在所测本机 fork 交错中，父子任一方关闭均不解除另一方尚持有的锁。代价是 fork 或 dup 出的描述符未关闭时，维护锁会保守等待；关闭报错的物理结果保持未知，描述符不重试。独立审查的 25 项维护测试、4 项连接测试及描述符复用探针通过（`/tmp/sdk-close-only-independent.log`、`/tmp/sdk-connection-close-independent.log`、`/tmp/sdk-close-reuse-review.log`），当前源码维护、连接及激活 28 项检查通过。此变更不覆盖 Windows、独占租约的解锁窗口或继承 SQLite 连接的使用，也不构成长期日志激活的完整证明。

独立审查发现参与式连接在确认退出后、移除保留记录前被中断时，后续关闭会遗留该记录（`/tmp/sdk-connection-confirmed-interrupt-review.log`）。源码已允许确认退出后的重试只完成记录清理，不重复关闭或释放；未知退出继续保留并报告，6 项定向检查和 5 项初始化清理检查通过（`/tmp/sdk-connection-confirmed-interrupt-fixed.log`、`/tmp/sdk-connection-init-cleanup-fixed.log`），仍需独立复核。

日志绝对期限另有实际探针：将普通 note 的序列化延迟至约 120 毫秒后，以 30 毫秒调用期限执行仍成功，实际约 146 毫秒（`/tmp/sdk-journal-deadline-serialization-review.log`）。现有日志方法在序列化后才建立数据库期限，因此不能直接将其当成贯穿序列化、登记和处理器入场的原始期限。连续激活和按操作保留原始期限的接入仍在实施，不能据此报告 G14 已通过。

参与式连接的复审再现了一个更早的资源交接问题：`connect()` 中 SQLite 连接实际建立后、参与锁赋给连接前若被中断，异常路径释放锁，而异常栈仍可持有可查询的连接；独占维护因此可以在该连接存活时进入。只读连接帮助函数有同样的交接结构。该问题正在修复，不能把前述关闭清理检查当成连接创建的完整安全证明。另一个确认退出后的同线程重入可使外层关闭误报 `KeyError`；现已改为幂等删除并加入定向重入测试，与初始化清理共 12 项通过，仍待独立复审。

线程返回观察的试验性实现现将首次采样提前到成功处理器返回后、副作用列表读取前，并保留原样本；真实 Runtime 的两项定向检查覆盖成功结果、副作用 ID 和阻塞期间仍占用 worker 名额（`/tmp/sdk-thread-return-observation-evidence.log`）。独立复审确认主回归仍失败：读取效果跨越期限时，观察尚未发布，监控仍可能先裁决超时（`/tmp/sdk-thread-return-full-regression.log`）。进程模式仍在效果收集后采样；这是一处源码限制，尚未用同等进程探针复现。曾试验提前提交 Kernel 结果，但会扩大已知迟到回执缺口，故已撤回，不计为修复。

连接工厂试验修订在 SQLite 初始化前保留参与者与连接所有者，修复所测交接中断和关闭重入；独立审查又发现返回前中断且关闭失败时，强引用登记可能已移除，正在修复。实际探针中仍可访问的连接自己持有参与锁，维护未进入；尚未观察到该新窗口使存活连接提前解锁。另一个未解决的兼容性问题是普通 SQLite 初始化失败可能永久保留锁：真实 audit hook 可在 SQLite 安装句柄后抛出，而公开 `close()` 因初始化未完成而拒绝（`/tmp/sdk-sqlite-init-audit-review.log`）。只读目标事先不存在的预检查不能覆盖路径竞争或其他初始化失败，不能计为旧 API 完全兼容。

新增 v6 日志激活对象的首版提供连续共享参与、绑定身份和携带原始绝对期限的登记接口；它尚未接入 Runtime。独立审查以真实库确认，参数校验或绑定不符这类可确认的失败也会永久保留锁；正在以逐操作清理证据修复。线程启动与操作系统调用本身仍不受关闭期限硬限制，进程退出也不证明后台释放线程完成。这些基础检查不能替代 G14 故障恢复验收。

针对线程返回观察的再复核发现，首次修订将效果列表读取异常移出原有异常分类范围；现已恢复原分类，同时保留返回回调自身异常的独立边界。有无回调的单次效果读取异常负例、返回观察和监控顺序等 7 项检查通过（`/tmp/sdk-return-effect-classification.log`）；独立复核确认原始行为和成功结果对象身份。效果读取失败后的未知完成时间分支仍需完整 Runtime 负例，截止期跨越和进程路径均未解决。

连接返回前单次中断的独立复验：当关闭失败时，原 `KeyboardInterrupt` 保留附带的关闭错误，注册表强持有准确连接及原参与者，维护保持阻塞；在受控测试确认可关闭后维护才能进入。独立聚焦检查 17 项通过。登记恢复前的连续中断和普通初始化失败后长期占锁仍未解决。

v6 激活的确定性输入错误和错误绑定已能在确认资源释放后关闭或重试；含原有日志接口的 55 项组合通过（`/tmp/sdk-activation-cleanup-final4.log`）。独立复核再现操作准入计数增加后、中断清理范围开始前发生中断，会让 `_inflight` 遗留并阻止关闭，现正在修复。另一次 33 项组合有两项在原有 100 毫秒准备期限超时，单独重跑均通过；原组合不能记为全通过，也不能凭单次重跑推断超时原因。此激活仍未接入真实 Runtime。

上述激活准入改为在清理范围内登记可追踪票据。原真实中断探针重跑后没有遗留票据，关闭及后续维护成功；独立审查的 19 项激活检查通过，作者另以原期限运行激活和预登记 37 项通过（`/tmp/sdk-activation-interrupt-final.log`）。该结论限于所测交错：异步中断恰逢锁获取、进程 fork、线程启动和系统调用不受硬期限保障；未知关闭或提交仍保留所有者，暂无对账接口。尚未接入 Runtime 或验证 G14。

效果收集出错的真实线程 Runtime 新增负例：处理器已返回后首次采集成功，效果列表一次性抛错；原有错误分类保留，完成时间标为未知且不重新采集，日志保留待处理事实，工作任务结束后名额可再次获取且 Runtime 关闭返回。连同相关并发检查共 8 项通过（`/tmp/sdk-runtime-collection-failure.log`）；独立复核确认这些断言，但该测试未持有线程句柄，不能单独证明线程池的物理线程已终止。它不改变超时误判和迟到回执回归仍失败的结论。

返回观察相关扩展测试首次发现旧测试要求预算 envelope 对象身份不变；实际合法采样可能提高时钟水位并产生新对象。检查后将两个相关断言改为核对完整投影结果、原始样本和 guard，增加受控墙钟回退场景；53 项观察及时钟定向检查通过（`/tmp/sdk-observation-clock-test-after.log`）。独立复审确认原有语义不要求对象身份，并重跑观察模块 8 项通过；预期对象复用同一水位方法，另有独立水位、约束、样本和 guard 断言，不能将此测试视为该方法本身的独立证明。当前源码的返回观察、监控顺序及已发布结果竞争组合 6 项通过；上述跨期限和恢复失败仍保持原结论。

G14 真实接入调查确认：现有 Runtime 默认使用 v4 日志，尚未启用版本化 claim、v6 意图登记和 v17 已提交权威；默认日志不得静默升级。v6 激活目前仅提供预登记和检查，缺少将已提交 Kernel 原始授权、结果与不可变收据证明绑定的原子日志接口；普通待处理记录或可修改的 evidence 不可充当该证明。接入还须让原绝对期限覆盖登记及入场，并在实际完成所有者退出前持有激活。正在实现所缺日志能力；原 v4 迟到回执测试未改变，仍未通过。

显式 v7 日志的收据基础正在实现，初步组合检查曾通过 61 项，但独立审查随后发现私有暂存文件在发布前可被替换：即使已连续持有暂存协调锁，在主机验证回调中替换暂存路径后，发布仍可能成功并得到替换内容。该探针涉及直接操作暂存路径，协调锁只约束遵守协议的参与者；实现正在增加身份检查，完整竞态边界、清理以及实际 Runtime 接入仍待复核。以上基础检查不构成故障恢复验收。

后续暂存修订在发布前保持实际文件描述符，并比对路径及发布目标身份；作者报告 64 项组合检查通过，以及最终清理修订后的 8 项收据检查和发布竞争检查通过（`/tmp/sdk-delivery-proof-regression-final2.log`、`/tmp/sdk-delivery-proof-post-cleanup.log`、`/tmp/sdk-delivery-proof-publication-race.log`）。这些检查不覆盖可信宿主未阻止任意路径篡改的情况；发布后发现身份变化时结果需对账。独立复审还以真实 SQLite 复现：旧构造器可能成功打开 v7 却在后续操作拒绝；准确收据按正常流程记为 recorded 并附加证据后，v7 再次检查错误地报告冲突。两处均在修复，完整 Runtime 接入尚未开始。

实际 Runtime 仍未使用捕获返回的 Kernel 权限，v7 激活也未提供运行时所需的完整日志操作及恢复接口。普通待处理记录会触发既有恢复的 Kernel 完成动作，不能把 v7 未提交意图直接交给该路径。另有跨进程探针确认，在未配置协调文件的旧日志上保持 SQLite 只读事务时，现有维护方仍可取得独占维护锁；因此单纯跳过参与锁无法同时保留零创建读取和维护互斥。该旧 API 兼容问题仍未解决。

上述两个 v7 复审问题已修订：旧构造器拒绝 v7；记录的结算证据可在严格对象校验后保留，但不代替 Kernel 权威、准确结果或不可变证明。作者报告 14 项 v7 定向测试通过（`/tmp/sdk-delivery-proof-review-final.log`），其中一项把 v7 日志注入现有真实 Runtime 恢复入口，确认 Runtime 将空证据收据标为 recorded 后仍能读回和重放证明；该注入不是公开的 Runtime 接入。另一轮 69 项组合中 3 项在激活夹具准备期限内失败（`/tmp/sdk-delivery-review-fixes-regression.log`），三项原期限单独重跑通过（`/tmp/sdk-delivery-review-fixture-retry.log`）；原组合失败保留，根因未确定。修订正接受独立复审。

上述收据修订经未参与实现者复核，14 项 v7 检查通过，未发现所审范围内新的具体缺陷。recorded 的诊断文本本身不经 Kernel 认证；接受证明依赖另行读取的准确 Kernel 权威和绑定。内核中全部见证若被同时篡改不在该检查可识别范围内；上述真实 Runtime 测试仍为测试注入，不构成实际 v7 激活或 G14 验收。

v6／v7 激活增加受原始绝对期限约束的诊断记录及检查；写诊断要求调用方提供稳定 note ID，以便提交结果未知时准确重试。作者的 55 项组合检查通过，但发生在最后一项 note ID 限制之前；最后修订后的 4 项定向检查通过（`/tmp/sdk-activation-diagnostics-regression.log`、`/tmp/sdk-activation-diagnostics-final.log`）。独立复核在实际提交后阻挡返回至期限外，确认首次调用报超时但记录已存在，以同一 ID 重试仍只保留一条；另一次 23 项组合有 2 项在 100 毫秒初始化准备期限内失败，其余 21 项通过，失败项按原期限单独重跑通过，原组合不能记为全通过。生命周期操作还涉及两个 Kernel 连接，目前尚未纳入激活所有权；v7 激活中的生命周期和普通候选恢复入口仍未提供。

Kernel 增加 v2 返回事实采集：在效果清单读取及返回值序列化前保留一次时间样本，后续完成决策仍独立核对结果和 Kernel 效果；读取者准入锁被占用时返回未知，不能等待后将新样本冒认为原返回时间。独立复核发现 fork 后子进程可使用继承的 Kernel 和所有者完成 v2 结果；修订现检查原进程、原连接及所有者身份。原真实 fork 探针重跑时子进程被拒绝、父进程仍可提交；另有实际 fork、连接替换及旧 v1 捕获／提交检查通过。该检查不支持通用的继承 SDK 对象，采样也发生在非阻塞准入后，不能声称与处理器返回绝对同时；返回值序列化期间不得并发修改。接口尚未接入 Runtime，真实期限和 G14 失败仍未解决。

真实线程受控闸门探针进一步发现：让完成交接锁在返回采集期间保持占用后，监控可返回 `completion_handoff_pending`，驱动退出时没有保留待结算所有者；随后放行并确认工作任务退出，Kernel 仍为 running、结果为空，也没有结算收据或待结算所有者（`/tmp/dispatcher_pending_handoff_probe.py`、`/tmp/dispatcher_pending_handoff_probe.log`）。这是受控时序复现；不能简单将新增的返回捕获竞争交给该分支，必须先为迟到结果保留准确的消费与清理责任。

进程隔离路径也有真实受控复现：POSIX 工作进程中的处理器在原期限前约 1.37 秒返回可序列化值，SDK 随后序列化该值时被闸门阻挡，原 1.5 秒期限内未延长；最终 Runtime 返回 `timed_out/handler_timeout`，监督者确认进程收容及回收（`/tmp/sdk_process_return_probe.py`、`/tmp/sdk-real-process-return-ikt8y9c8/evidence.json`）。这证明所测序列化交错会误判，不证明原值已经通过 Kernel 验证。Windows 源码显示相似的序列化后上报和看门狗顺序，但尚未在 Windows 实测。

v6／v7 激活中的单条、批量生命周期记录和准确回读已实现，作者报告 9 项定向检查通过；旧生命周期与激活的 45 项组合有 2 项在夹具准备期限失败，其余通过，两项按原期限单独重跑通过（`/tmp/sdk-activated-lifecycle-final.log`、`/tmp/sdk-activated-lifecycle-regression.log`、`/tmp/sdk-activated-lifecycle-regression-retry.log`）。独立审查以 30 MB 证据复现 5 毫秒期限的调用在约 99 毫秒后才返回，原因是单条操作先序列化输入再检查期限；正在修订。该结果不证明硬实时上限，也不构成 Runtime 接入。

激活日志输入改为在编码期间检查原始期限并限制大小；独立审查以真实 v7 操作确认先前的 30 MB 输入迅速被拒绝，但该观察不是操作系统硬实时保证。复核随后发现，批量单条最多可提交 1 MiB，而单条重放和回执读取只接受 256 KiB；现统一生命周期事件的单条上限，普通诊断仍为 256 KiB。作者的真实数据库 300 KB 重放检查通过（`/tmp/sdk-lifecycle-large-final2.log`），旧生命周期及预登记组合 26 项通过（`/tmp/sdk-lifecycle-large-regression.log`）。独立复审在 v6、v7 两种激活方式下使用实际 Kernel outbox 验证恰好 1,048,576 编码字节的批量写入、单条重放、准确回执和错误代次拒绝（`/tmp/dispatcher_activation_large_boundary_review.log`），该范围未发现新的具体缺陷。

线程完成交接新增真实 Runtime 失败测试 `tests/test_runtime_pending_handoff_ownership.py`：监控返回交接待确认，实际工作任务退出后，记录、待结算所有者和 Kernel 结果均缺失（`/tmp/dispatcher_pending_handoff_test.log`）。Kernel 层另以真实时间复现：返回事实在原期限前采集，而决定在期限后、原租约仍有效时执行，现有 v2 完成接口错误地以决定时剩余工作时间为零拒绝（`/tmp/sdk-completion-late-decision-before.log`）。正在修订和独立复审两处；局部通过不代表 Runtime、崩溃恢复或最终候选验收通过。

Kernel 的 v2 返回决定现按原样本检查所有后来保留的截止条件，允许原租约仍有效时在工作期限后决定；旧版捕获的决定约束保持不变。独立复审发现事务验证期间租约可到期，修订后在同一写事务的最终授权检查处再次检查租约和时钟；先于期限及晚于期限开始的两种真实 SQLite 受控探针均拒绝所测过期决定（`/tmp/dispatcher_late_decision_lease_probe_after.log`、`/tmp/dispatcher_legacy_lineage_lease_probe_after.log`）。复审还发现收紧截止条件时一个浮点舍入边界会错误接受，现沿用保守上取整的时钟水位并加入确定性回归。期限后决定、验证中租约到期及舍入边界 3 项通过（`/tmp/sdk-completion-late-decision-guard2.log`）；现有权威检查另有 30 项通过（`/tmp/sdk-completion-authority-with-cancel.log`），包括新增 v2 取消胜出检查。此检查只证明同一写事务内的授权时点，不证明实际 SQLite COMMIT 在租约到期前完成；v2 尚未接入真实 Runtime。

新增 Kernel 登记优先的交付对账组件，仅核对已提交权威并重读准确证明，不会据未提交意图完成正在执行的任务。7 项真实 SQLite 检查通过；独立审查确认写事务未提交时保持未知，同时复现日志激活在取得参与锁后异常会遗留实际所有者，而组件无法持有该所有者，重复扫描可积累锁（`/tmp/dispatcher_reconcile_unknown_open_probe.log`）。该问题正在修复，组件尚未接入 Runtime，不构成 G14 验收。

对账组件现于参与锁取得前登记准确激活所有者，并以进程内、按日志路径的共享协调阻止其他组件重复打开同一未知所有者；不确认的退出继续保留。独立复测原失败打开和多个组件场景，不再累积参与锁；协调锁受原操作期限约束的竞争探针也通过（`/tmp/dispatcher_reconcile_unknown_open_probe_after.log`、`/tmp/dispatcher_reconcile_multi_owner_guard_after.log`、`/tmp/dispatcher_guard_deadline_probe_after.log`）。最终 9 项定向检查通过（`/tmp/dispatcher_guard_final_tests.log`）；该协调仅限本进程，协调器或激活操作期间不支持 fork。尚未接入 Runtime，也没有交付 ACK 或真实崩溃验收。

线程交接试验版保留迟到工作任务及原准入，未确认的迟到事实使用独立 deferred 类型；实际恢复探针保持 Kernel running 和 unknown，不把事实当成完成授权。对于已在 Kernel 准确提交的结果，另核对原结果后可补记录已有回执；真实 SQLite 原迟到提交测试通过，包括关闭并重新打开后的准确记录。作者的 19 项受控检查通过（`/tmp/sdk-late-handoff-final.log`），包含停止后的 worker 优先交接；独立复审进行中。此前扩大检查还有四项失败，分别涉及测试准备和拦截位置，正在在不放宽原期限的前提下核查。未解决一般真实崩溃窗口、进程模式或按时返回误判，不能据此标记 G14 通过。

上述扩大检查中，两个预算扫描夹具现初始化运行时停止事件；另外两个压力测试用真实 Kernel 控制锁使工作线程的提前完成尝试有界回退，再执行原有的日志写锁和生命周期锁竞争。原来的结果断言、2 秒返回要求和 5 秒业务期限未放宽；两个模块共 5 项通过（`/tmp/sdk-budget-contention-fixed.log`），修改前失败和线程栈保留在 `/tmp/sdk-budget-contention-rerun.log`、`/tmp/sdk_pending_contention_trace.log`。另一个单独的实际风险仍在处理：工作线程在完成门内等待生命周期锁时，可能让监控长时间拿不到结果。

Host 的有限停止检查当前 4 项中 2 项失败：启动前清理和运行中撤销会在持锁时同步启动线程，线程启动受阻可使 stop 超过期限（`/tmp/sdk-host-stop-deadline-before.log`）。启动过程中的另外两项通过。现有执行器按需启动线程，不能直接充当已经就绪的清理启动者；修复必须同时保留取消、清理以及启动结果不明时的所有权，尚未解决。

对当前源码再次运行两个原停止期限场景，均仍失败，分别卡在启动前清理及运行中撤销的线程启动；调用期限和观察窗未改（`/tmp/sdk-host-finite-stop-current-python3.log`）。这是定向失败复验，不是完整回归。

线程交接的独立复审又以真实 Runtime 复现停止丢结果：处理器已经返回，但效果收集仍被阻挡且尚未进入完成门时，请求停止使驱动退出；随后工作任务退出，Kernel 仍为 running，日志和迟到所有者均为空（`/tmp/dispatcher_late_stop_collection_probe.log`）。现有停止分支仅在完成门已锁住时转交所有权，覆盖不到该交错，仍待修复。另一真实探针确认工作线程提前提交期间等待生命周期锁可令 2 秒内的返回无法完成（`/tmp/dispatcher_late_lifecycle_block_probe.log`）；简单改为非阻塞曾引入两次构造不同结果 ID，试验已撤回，不能计为修复。

停止分支试验修订后，独立复测在上述效果收集交错中保留了原值作为 `late_thread_fact`，Kernel 保持 running，事实仍为未知完成结果（`/tmp/dispatcher_late_stop_collection_probe_after.log`）；工作线程尚使用存储时关闭会报告未完成结算并保留存储（`/tmp/dispatcher_late_stop_close_probe.log`）。生命周期竞争试验改为构造提前结果前非阻塞准入，未取得锁时由前台路径继续。相关 5 个模块共 26 项通过，保留了原有压力测试的期限及结果断言（`/tmp/sdk-lifecycle-stop-full.log`）。独立复审随后以实际 Runtime 复现：非阻塞获取生命周期锁成功后、释放保护生效前若发生异步中断，锁可能遗留，驱动无法结束（`/tmp/dispatcher_async_lifecycle_acquire_probe.log`）。该缺陷正在修复；上述局部通过不等于完整交接或异步中断安全。

上述生命周期锁问题的试验修订把释放保护放在获取之前；作者重跑原中断探针，驱动退出且锁可重新获取，4 项定向检查通过（`/tmp/dispatcher_async_lifecycle_acquire_probe_fixed.log`、`/tmp/sdk-async-lock-repair.log`）。独立复审重跑该探针并确认锁可再次获取，另有迟到所有者和竞争两个模块共 10 项通过（`/tmp/dispatcher_late_owner_review_stable.log`）；结论限于该获取边界，不证明清理中的连续中断安全。独立复审还在停止转交调用入口前注入中断，复现工作线程退出后没有迟到所有者或回执，Kernel 保持 running（`/tmp/dispatcher_stop_transfer_interrupt_probe.log`）；停止转交仍未完成，不能凭前述正常停止复测宣称一般中断安全。

停止监控的异常处理试验在调用转交入口之前补救不可取消的工作线程。独立重跑上述真实中断，原 `KeyboardInterrupt` 保留，原始返回值作为 `late_thread_fact` 留存且 Kernel 仍为 running（`/tmp/dispatcher_stop_transfer_interrupt_probe_review.log`）。该交错不证明所有提交与退出边界安全。独立复核又发现更早的线程回调登记窗口：在登记前中断后，执行线程退出但 Runtime 仍持有活动权限与容量，原关闭却返回（`/tmp/dispatcher_callback_registration_interrupt_probe_before.log`）。单一登记行的重试试验被更早一行中断复现绕过（`/tmp/dispatcher_callback_setup_interrupt_probe.log`）；线程提交结果不明及真正退出时的所有权正在重新设计，尚未修复。

停止转交修订经独立源码复核及 10 项相关测试通过（`/tmp/dispatcher_stop_transfer_independent.log`），结论仅限监控阶段。作者另一次较大组合中有一项在三秒准入等待及后续清理诊断失败，原期限单独重跑通过，原因未确认；失败日志保留在 `/tmp/sdk-interrupt-final.log`，不能将该组合记为通过。更早的提交及回调登记缺陷不包含在这一独立复核结论中。

工作线程提交后的另一个独立探针在转移容量所有权之前中断：实际线程仍被阻挡，运行时已经移除其权限并释放容量（`/tmp/dispatcher_submit_blocked_interrupt_probe.log`）。该探针尚未进入业务处理器，证明的是容量可过量准入，不能推断业务结果。此前 SQLite 初始化故障也进一步确认，audit hook 可保留尚未完成初始化但已有实际文件描述符的连接，公开 `close()` 拒绝该连接（`/tmp/sdk-audit-physical-handle-review.log`）。参与锁必须保留，避免维护与仍存活的句柄并发；现有 Python SQLite 接口未提供已确认的关闭方式，相关普通初始化失败后的长期占锁仍未解决。

线程提交所有权的结构性试验在提交前登记原容量及执行代次。独立真实线程池探针显示，提交已排队却未返回 Future 时，容量与 Kernel 存储保留至所测工作退出；返回的排队 Future 随后确认取消时则回收容量（`/tmp/dispatcher_ambiguous_enqueue_probe.log`、`/tmp/dispatcher_real_queued_cancel_interrupt_probe.log`）。当前源码相关组合 32 项通过（`/tmp/sdk-owner-current-focused.log`）。但独立复核又在工作线程调用完成清理后、实际 callable 返回前阻挡该线程，观察到容量与权限已提前释放（`/tmp/dispatcher_physical_exit_boundary_probe2.log`）；试验仍未完成，32 项通过不能覆盖这个真实交错。一般提交异常无法证明是否已排队时，目前保守保留所有者，可能持续阻止关闭；已确认未进入的上下文也尚未执行 `context.close()`，所测上下文没有活动观察线程或采样句柄。

后续试验改以已返回 Future 的完成状态作为 callable 已返回的证据；未返回 Future 的提交即使 callable 后来结束也继续保持未知。针对提交中断、确认取消、停止转交和迟到提交的 5 项测试通过（`/tmp/sdk-owner-future-evidence.log`）。独立的三个线程池交错检查有两项通过、严格容量检查失败：完成回调中 SDK 的 `_thread_finished` 已返回后，实际 executor 线程仍被闸门阻挡，容量和权限已释放（`/tmp/dispatcher_submit_interruption_future_candidate.log`）。该时刻处理函数及其上下文清理已返回，未观察到后续 Kernel 访问；证据说明线程池线程尚不可复用时仍可接纳新任务，不能据此推断其他结果丢失。已保留失败测试，完整修复仍需工作线程可用性的可信确认或明确的容量合同，不能将该组合记为通过。

清理试验随后改为以独立票据覆盖清理调用和最终容量释放，其他扫描不能绕过该票据；释放前登记 `unknown`，只有调用确认返回后才记为 `released`，其余清理按原所有者可重试。独立复核的线程池清理闸门、4 项所有权测试、16 项交接测试及 8 个并发扫描通过（`/tmp/dispatcher_release_state_independent_tests.log`、`/tmp/dispatcher_release_state_handoff_tests.log`、`/tmp/dispatcher_concurrent_sweeps_probe.log`）。当前源码受影响的 35 项组合通过（43.464 秒，`/tmp/sdk-release-accounting-current.log`），包含原迟到提交回执与上述清理闸门。此结果不保证容量释放后的任意后续中断；提交未返回 Future 或容量释放结果未知时仍保留所有者，可能无限期阻止关闭。之前一次组合中的诊断准入失败仅在单项重跑通过，根因仍未知（`/tmp/sdk-two-phase-claim-final.log`、`/tmp/sdk-g14-after-diagnostic-failure.log`）。

旧日志只读兼容仍存在可复现失败：未预先配置协调文件的 v4 日志经只读入口打开时创建锁文件（`/tmp/sdk-readonly-regression-review.log`）。独立跨进程检查确认旧式 SQLite 只读事务不能阻止现有维护租约（`/tmp/sdk-readonly-legacy-exclusion-proof.log`）；直接跳过锁会失去自动维护互斥。已配置锁文件也不能单独证明真正只读目录及 Windows 支持；当前没有完整兼容修订。

日志升级试验新增显式 v4→v8 副本：在宿主确认的源写入及目标命名排他范围内，将原有普通记录的完整原始内容写入不可变清单；之后添加的普通记录和既有 v7 不会被推断为旧记录。v8 激活可有界检查原始记录与当前租约／负载，结果对账器要求显式选择 v7 或 v8，版本不符保持未知。真实 SQLite 定向 3 项通过（`/tmp/sdk-v8-reconciliation-focused-python3.log`），包含登记后待决、已提交证明重放与版本不符；独立复核的相关模块 12 项通过（`/tmp/dispatcher_v8_provenance_independent_review.log`），在所审范围未发现新的明确缺陷。该方案依赖宿主兑现排他承诺，过大或损坏的旧记录失败关闭。首次误用不存在的 `python` 命令未运行测试，保留 `/tmp/sdk-v8-reconciliation-focused.log`。旧待处理记录枚举、普通结算接口和 Runtime 接入尚未实现，这不是旧记录完成授权或 G14 验收。

当前停止期限四项重测仍有两项失败（`/tmp/sdk-host-deadline-before-current.log`）。另一真实宿主探针阻挡协调线程的 Bridge 调用后，独立撤销线程仍能进入，停止返回 false，放行后清理成功（`/tmp/host_blocked_bridge_revocation_probe.log`）。因此仅把撤销转交现有协调线程会丢失所测的独立撤销行为；尚未实现同时保持该行为与有限停止期限的修复。

Kernel 对标记为新交付协议的执行增加统一成功门：公开完成、SDK 恢复及处理器入口都必须通过原所有者与返回事实的原子凭据；旧的未标记执行保留既有完成行为。复制旧记录的完成入口另在同一 Kernel 写事务中排除新登记，但调用方仍须独立核对原日志及清理证据，终态重读也必须独立验证。相关 38 项定向检查通过（`/tmp/sdk-marked-authority-v1.log`）。独立审查发现起始事件的 attempt／fence 使用 Python 相等比较时，布尔值或浮点数可以冒充整数；修订前的隔离库检查复现四处失败（`/tmp/sdk-admission-malformed-before.log`），现要求确切整数类型。修订后包含该负例、标记与旧完成路径、v14 结构的运行中副本迁移及迟到回执的 23 项检查通过（`/tmp/sdk-admission-and-legacy-migration-v2.log`）。v14 用例由测试夹具构造旧版结构，不是生产数据库样本；上述基础尚未接入完整 Runtime 或证明 G14 通过。

v8 旧记录扫描经独立复核发现遗漏：原始待处理记录对应的当前记录若丢失或被写为 recorded，旧扫描可能返回空；`recovery_required` 也可能被跳过（`/tmp/dispatcher_v8_scan_missing_probe.log`）。修订现遍历所有复制的原始记录，缺失或损坏返回带游标的错误，其余终态及 recovery_required 返回需独立核验的交接标记，不把可变日志状态当作 Kernel 凭据。原复现与 4 项定向检查经独立复审通过（`/tmp/sdk-v8-scan-original-regression.log`）；该扫描目前没有生产调用方，仍需接入实际恢复，并处理原期限、所有权与各类旧待处理记录。

标记门及整数校验经另一审查者复核，17 项完成／入场检查通过；审查确认上述迁移数据由当前 Kernel 建立后重建为 v14 结构，不能称为历史发行版生成的数据库。旧版只读失败也再次独立复现（`/tmp/sdk-v4-readonly-legacy-review.log`）：完全没有协调侧文件的目录会被创建锁文件。只读 SQLite 事务与直接绕过参与锁均不能阻止现有维护方替换原路径（`/tmp/sdk_readonly_legacy_exclusion_probe.log`）。预先准备协调文件并提供不创建的共享锁读取可支持部分只读目录，但不能自动解决未准备的旧目录；现有维护客户端与新协议的协商、跨平台锁和替换语义仍是完整兼容的前提。

旧结果的准确重读存在独立实证缺口：原租约变更 ID 或到期时间时，运行中 Kernel 拒绝旧记录完成；真实租约完成后，终态清除了租约 ID、所有者及到期时间，保留事件也不包含租约 ID。原始预算会被合并入现有预算，无法单凭合并结果还原提交参数（`/tmp/sdk-copied-terminal-readback-blocker.log`）。因此当前终态和相同结果不足以证明完整原租约或预算；正在设计与完成事务同时提交的不可变见证，历史未留独立凭据的终态继续为 unknown。新增损坏起始事件的 5 项完成权限检查通过（`/tmp/sdk-admission-damaged-event-v1.log`），均为隔离测试库，不改变真实存储。

返回超时的运行路径复核确认：返回回调只采集普通样本，效果读取完成之前工作线程尚未进入完成门；监控在截止时可先取得门并撤销该线程，最终产生超时。持有原 Future 的未确认交接能避免直接编造终态，但本身不能证明成功。v2 权限还要求先有标记 claim 与准确的日志／Kernel 预登记，当前 Runtime 均未接线；进程和 Windows 模式更不能复用绑定到父进程线程的能力。进程路径需要由监督者在原期限内接收并认证的代次绑定返回通知，以及结果、预算、进程树清理的原子决定；通知迟到或丢失仍为未知。以上为接入设计与范围，尚无相应端到端修复或原生 Windows 验收。

存储预检另发现旧接口兼容问题：轻量 schema 检查未计入合法的 Kernel 保护触发器，因而拒绝有效的当前数据库。修订后，正常数据库通过 schema、bindings、full 各自的 schema 检查；逐一移除或替换六个保护触发器时三种检查均发现损坏（`/tmp/sdk-storage-trigger-preflight-v18-v2.log`）。部分检查的 `compatible` 保持原有 unknown 语义，不将部分检查冒充完整兼容验收。此项不解决前述 v4 只读目录的协调文件问题。

复制旧记录的不可变见证已增加原租约、结果及预算信息的原子提交与重读，独立审查随后实际复现：fork 后的子进程仍可使用继承连接写入见证，父进程会接受（`/tmp/sdk_v18_witness_fork_write_probe.log`）。写入端的进程及连接所有权修复仍在进行，先前该组件的定向通过不能覆盖此缺陷，也不能作为 G14 验收。

在实际 Runtime 的旧结算重放中复现：携带 `recovery_required` 的旧记录可将已标记或已登记的新协议执行转入效果恢复（`/tmp/sdk-legacy-effect-replay-before.log`）。现把新旧排除与转移放在同一 Kernel 写事务；标记、登记或原始启动证据损坏时保留原记录并报告 unknown。合法旧执行仍可进入恢复，运行中处理器的正常恢复入口不受此旧记录限制；独立连接竞争与正反例通过（`/tmp/sdk-effect-authority-independent-review.log`）。独立审查还复现已停放执行被另一条错误效果 ID 的旧记录冒认；现将此类未经原租约证明的重放保留为 unknown，真实探针复测通过（`/tmp/sdk-effect-already-parked-after-review.log`）。这意味着提交成功但回执丢失的旧效果恢复目前还不能自动确认，仍需与原操作原子绑定的可验证见证，不能声称旧行为完整兼容。

包含旧效果恢复、Runtime 结算及日志的定向组合共 48 项，15 项失败、1 项错误（`/tmp/sdk-legacy-effect-replay-focused-final.log`）。多项在夹具保留的同一处理结果上出现两个不同 result_id；其他项涉及现有完成权威为 unknown 时的恢复期望。各失败的根因尚未全部确认，须保留原始失败并逐项诊断；这不是完整回归通过。

双重 result_id 的直接原因已定位：工作线程在尝试 Kernel 提交前构造了带 ID 的结果，提交未确认时未把这个原结果交给前台，前台再次生成结果 ID。试验修订保留第一个候选但不把它当成已提交证明；最初 3 项定向测试通过（`/tmp/sdk-runtime-result-identity-after.log`）。随后包含线程交接、取消和进程路径的 21 项组合中 2 项失败、1 项错误（`/tmp/sdk-runtime-result-identity-focused.log`），涉及中断时线程容量释放及清理所有权，尚未确认与试验修订的关系；原始组保持失败。候选字段与后续效果清单或其他结果内容不一致时也必须保留 unknown，不能复用相同 ID 宣称内容一致。

结果 ID 修订进一步对比完整标准化结果；值、状态或完成时间等变化会保留原候选并报告未知。最后修改后的 4 项定向测试通过（`/tmp/sdk-runtime-result-identity-final-focused.log`），包含实际写入阻挡后的原结果，以及伪造已提交回执的拒绝；还需独立复核和前述失败组合的根因排查。

上述三项线程所有权失败在当前源码单独组合重跑通过，4.790 秒（`/tmp/sdk-isolated-interruption-review.log`）；原 75 秒组合失败仍保留，失败成因未证明，不能用单独通过替代原组合结果。结果 ID 修订经独立源码复核，另有真实线程、进程成功及错误恢复等 4 项定向检查通过；这些检查不代表 G14 完成。

复制旧记录的 fork 写入修订现在会在使用继承锁及连接前、事务中和提交前校验原进程与原连接；真实 fork 及连接替换定向测试通过（`/tmp/sdk-v18-fork-write-guard.log`、`/tmp/sdk-copied-fork-independent-review.log`）。但独立复核又发现事务内替换连接后，原连接可能保留未提交事务（`/tmp/sdk_legacy_mid_transaction_swap_probe.log`）；修订将提交和回滚绑定实际事务连接，探针和独立定向检查通过（`/tmp/sdk_legacy_mid_transaction_swap_probe_fixed.log`、`/tmp/sdk-transaction-owner-independent.log`）。在提交调用内部替换私有连接的探针仍能令原提交完成而当前对象指向其他连接（`/tmp/sdk-kernel-commit-swap-review.log`）；提交结果应保持已提交或未知，不能以回滚掩盖，修复仍在进行。任意活跃事务中 fork 本身仍未提供安全保证。

只读快照的相同连接替换问题也曾留下原事务；修订绑定原句柄并在回滚未确认时保留所有者（`/tmp/sdk_kernel_read_swap_after.log`）。进一步复现读取时替换连接可能使原连接的超时回调未清除；针对受影响读取入口的修订与 64 项局部检查通过（`/tmp/sdk-read-progress-ownership-focused.log`），尚需独立复核。这些均为隔离测试和受控私有连接替换，不证明 G14 已完成。

独立审查进一步复现回调安装中断及移除失败可能使回调残留；修订后把安装纳入清理保护，移除未确认则保留原连接并阻止继续使用。相关 70 次测试调用通过，新增中断优先级检查另行通过（`/tmp/sdk-progress-install-final.log`、`/tmp/sdk-progress-install-priority.log`）；独立复核的 61 次调用通过，其中有重复收集（`/tmp/sdk-progress-owner-independent.log`）。另一个受控探针在回调移除时替换私有连接，原读取可错误返回；修订后报告未知并保留连接所有者（`/tmp/sdk-progress-clear-swap-focused.log`），正在复核。提交调用内部替换连接的修订保留原连接和替换连接，提交结果仍为已提交或未知，不尝试撤销已确认提交（`/tmp/sdk-commit-fence-final.log`）。瞬时替换后立即还原及所有可能的异步中断交错尚未证明。

回调移除时替换连接的原探针经独立重跑现报告未知；复核确认原回调已移除，两个实际连接均被保留，即便恢复属性也不能继续读或关闭（`/tmp/sdk-progress-clear-swap-fence-after.log`）。原有 6 项定向检查通过（`/tmp/sdk-progress-clear-ownership-after.log`）。

v4 只读兼容缺陷及维护替换交错再次实际复现（`/tmp/sdk-v4-readonly-review-current.log`、`/tmp/sdk-readonly-legacy-exclusion-current.log`）。Linux 目录共享／排他锁探针表明当前版本的双方可以无新增目录项地协调，但现有多存储维护可能在同一目录嵌套取得多个租约，需要统一持有者、锁顺序与期限；旧进程不参与新协议，混合版本切换仍需宿主确保旧参与方退出。Windows 目录锁语义尚无本项目实证。以上是设计调查，旧只读兼容仍未修复。

显式启用 v8 的线程 Runtime 已接入登记、返回观察和对账；6 项局部检查通过，包括实际处理函数成功、登记未确认时不进入、活动期间关闭保护以及正常关闭后重新打开并补回已提交回执（`/tmp/sdk-runtime-delivery-v8-limited.log`）。最后一项是正常重启，不是进程崩溃验收。处理函数报错目前保留为 unknown；进程模式、超时与完整默认路径仍未闭合。真实延迟效果收集检查仍失败：处理函数在原期限前返回，但后续全局时钟前沿推进，现有凭据不足以证明顺序，运行保持 running（`/tmp/sdk-v8-delayed-collection.log`）。简单在返回后取得 SQLite 写锁不能证明锁取得前的准确返回时间；相关次序和所有权协议仍待解决，G14 未通过。

G17 资源核验脚本此前自行写入清理回执，不能用作产品已完成清理的证据；现仅检查产品已持久化的准确回执。脚本也要求活动状态和原执行身份来自同一条记录，分属不同记录的负例已在局部检查中拒绝。子级入口时看到清理回执仍不能证明清理先于资源准入，因此受限资源场景维持 unknown。之前原生 guard 单项在建立场景前因 socket send 返回 `PermissionError: [Errno 1] Operation not permitted` 失败，未保存日志；不是原生验收通过。

上述旧效果恢复、Runtime 结算及日志组合在当前源码重跑，50 项耗时 45.086 秒，4 项失败、2 项错误（`/tmp/sdk-legacy-effect-replay-focused-current.log`）。此次与之前 48 项组合的源码和测试数量不同，不能直接按失败数量认定完成比例。失败中包括原权限为 unknown 时的预期差异，以及一项测试访问参与式连接不存在的 `evidence_id`；具体责任及其他失败成因尚在核对，原始结果保留。

预算时钟的排序调查发现，返回观察前的非阻塞 SQLite 写预约可排序受保护的写入与采样，但旧代码和部分外部传入预算可先采样、后写入；仅看到空的采样标记表不能排除旧进程或尚未提交的事实。要将此预约用于成功授权，需要证明所有采样遵循持久标记协议，或由宿主严格排除不参与协议的写入者并处理既有未决事实；现有实现尚无完整证明。G17 证据检查另已纳入 unittest 发现，并拒绝将布尔值当作整数身份字段；两项局部检查通过，不替代真实资源验收。

对上述 50 项结果的独立分类确认，归档前提交期限错误是测试夹具未追踪真实参与式连接，尚未执行到预期断言。另五项中，一项实际保留完成时间未知的原始事实；四项到达旧恢复分支后保持 unknown，导致旧版期限恢复、提交后重放或读取器关闭场景未被验证。旧版恢复是否满足原合同仍需解决，不能仅修改预期结果。限时停止的两个失败则要求在 `stop()` 之前已有独立、可追踪的启动所有者；直接在 stop 内创建线程或仅移动锁都不能证明调用有界，且不能依赖可能被 Bridge 阻挡的协调线程。安全的启动中断、废弃宿主退役与资源所有权方案尚未实现。

归档测试夹具现追踪实际参与式连接，保留原有更新、未提交及关闭断言；单项重跑通过（`/tmp/sdk-cancel-archive-fixture-trace.log`）。此结果不覆盖原 50 项组合的其余失败，也不替代完整回归。

G17 核验脚本的独立审查又发现，关闭资源限制的对照原先不能证明父级原生操作在子级进入时仍存活，且只检查子级清理状态而未校验实际回执。脚本现要求入口时原父操作与准入身份匹配且等待闸门仍保持，子级回执与其执行代次、租约及实际 effect 匹配，跨来源身份字段也使用严格类型比较。5 项局部 unittest 通过，均为构造数据；未重新执行真实模型对照，受限资源顺序仍为 unknown，G17 未通过。

复审进一步发现父级匹配还须包含实际 runtime effect 和截止时间；现将原生存活和清理回执均绑定调用、执行、租约、代次、effect 与期限，错误代次／effect／期限负例被拒绝，6 项局部 unittest 通过。这些检查仍是构造数据，不替代资源场景原生验收；入口早于观察闸门建立时可能保守判失败。

独立复核确认 G17 调用点所需父级字段与产品原生记录一致，6 项局部测试重跑通过（`/tmp/g17-resource-review-six.log`）。旧 Runtime 在工作线程退出前会尝试将 unknown 返回事实写入 Kernel，但现有事实未证明所带时钟采样来自原始捕获操作；不能仅凭这一记录授权结果恢复。可行方向是将原线程、租约、结果与可信采样能力绑定，旧记录或写入失败缺少证明时仍须保持 unknown；这只是待实现设计。

G17 验证器增加实际资源池授予前观察：在资源池锁内、子级转为 active 前，用同一只读数据库快照核对父级已提交的资源释放和精确原生清理回执。观察之后重新检查原准入期限及取消状态；只有对应的实际 acquire 返回后才发布授予证据。11 项局部检查覆盖未提交记录、期限、取消和取消后重新准入（`/tmp/sdk-g17-resource-before-grant-v4.log`）。使用真实 AgentApp 和资源池的单项集成测试通过（`/tmp/sdk-g17-grant-observer-integration.log`）：合成适配器生成普通运行时提交而无原生操作，观察器准确拒绝将其算作原生清理；这不是原生验收。独立复核未发现该观察交接的具体误报，观察本身会占用原期限并可能短暂阻挡其他准入。

已构建隔离安装包用于真实资源试验。首次试验因脚本与环境目录布局触发来源检查，在调用模型前失败（`/tmp/sdk-g17-resource-native-01.log`）；目录调整后启动了第二次真实试验，保留两场景各自 360 秒原预算及日志。第二次试验使用修订前复制的验证脚本，不含后来增加的“实际 acquire 返回后才发布”保护，其结果仅供诊断，不作为当前脚本的最终验收。

第二次试验已结束：受限和默认关闭场景均为 failed，监督和整项 G17 为 not_run（`/tmp/sdk-g17-resource-native-02/report.json`）。受限场景记录了父 OpenCode 存活、子调用准入及保留容量期间排队；父调用释放后子运行时入口观察到父清理，但此后出现 `AgentExecutionError`，未到完成检查。默认关闭场景外层报告 `RuntimeError`。当前报告未保存具体异常文本，失败原因正在核实；不得将局部观察或较早脚本的结果当作最终验收。

受限场景的临时数据库进一步显示：父资源释放记录早于子资源登记；父、子实际运行时均已提交效果，子已发布 answer，但子执行的待处理结果记录了 `BudgetClockUnknownError: completion_clock_original_floor_unproven` 和 `completion_time_unknown`。控制器随后到达继承期限，子调用因等待耗尽被取消，最终抛出 `AgentExecutionError`。原始事实可在该试验的 `resource-limited-state/execution.sqlite3.observations.sqlite3`、`execution.sqlite3` 和 `control.sqlite3` 中核对；尚未确定原始时钟水位无法确认的具体原因。这是 SDK 完成时间／交付路径的失败证据，不是已观察到的提供方失败；仍不能用旧验证器的时序观察代替当前脚本的最终验收。

默认关闭场景的临时状态显示 controller 已启动，但父 Agent 执行及原生操作均未出现；旧报告仅保留外层 `RuntimeError` 类型，不能判定异常发生位置或关闭时是否覆盖了更早错误。当前验证器增加阶段记录和有限异常类型链，在外层失败时保留已收集的事实，不记录异常正文。独立复核发现应用关闭失败会遮盖之前的 unknown 结果；后续修订保留关闭前的临时结论，14 项定向测试通过（`/tmp/sdk-g17-resource-diagnostics-final.log`），独立复核未发现新的具体问题。这一改动不改变场景期限或判定条件，不能补出旧试验丢失的信息。

资源验证器现可用 `--case resources_disabled` 或 `--case resources_limited` 单独执行诊断；默认仍执行两个场景，未选择的场景保留 not_run，整项 G17 不会因此标记通过。实际 CLI 选择与原始期限传递在 16 项定向检查中通过（`/tmp/sdk-g17-case-selection-final.log`）；独立检查也验证了两场景默认顺序与单场景选择。最终真实验收仍须使用包含最终源码的隔离安装包。

为定位上一次不限资源场景的启动失败，已单独启动该场景：记录为 `/tmp/sdk-g17-resource-native-03-disabled/` 及 `/tmp/sdk-g17-resource-native-03-disabled.log`，任务预算仍为 360 秒，预计约 7 分钟后检查。脚本快照位于 `/tmp/sdk-g17-resource-current/scripts/`，使用此前隔离候选 `/tmp/sdk-g17-resource-candidate/venv/`；限额场景和整项 G17 不在本次范围。结果确认前不得推断通过。

上述单场景运行已结束：`resources_disabled` 为 passed，父 OpenCode 仍存活且闸门保持时子 Agent 实际进入，随后子 Agent 成功提交 `CHILD_NATIVE_OK` 并留下与执行代次匹配的清理回执；父子共享预期 controller 和原截止，计费为 2 次 Agent 调用。限额、监督和整项 G17 均为 not_run，见 `/tmp/sdk-g17-resource-native-03-disabled/report.json`。这次成功不解释前次启动异常；候选包早于随后完成时钟修订，也不替代最终候选验收。

完成时间故障记录现在可以区分路径、时钟水位、确认来源及存储身份等拒绝分支，并保存有限的数值诊断；异常类型和原有拒绝、恢复授权不变。完成时钟与真实 Runtime 定向 47 项通过（`/tmp/sdk-clock-diagnostic-focused.log`），效果读取失败边界另有 5 项通过（`/tmp/sdk-clock-diagnostic-runtime-focused.log`）。独立复核确认所测线程 Runtime 中诊断进入待处理记录且不授权恢复；尚未覆盖真实提供方、新版日志激活或进程隔离。该诊断不会补出先前真实失败丢失的分支信息，也不构成完成时间问题的修复。

跨线程确认的试验性放宽经独立复核发现不安全并已撤回。真实临时 SQLite 复现进一步确认原有同线程路径也会受影响：另一执行已取得较高的受保护采样、其确认暂时未完成时，当前返回观察可能忽略该全局待处理保护并接受较低水位；后续确认才推进全局时钟。复现脚本与输出为 `/tmp/sdk-global-guard-return-repro.py`、`/tmp/sdk-global-guard-return-repro.log`，新增定向回归在修复前按预期失败（`/tmp/sdk-global-pending-regression-before.log`）。正在修复已证实的交错；这不证明所有旧版或无保护采样写入者的顺序均可确认。

返回读取现于同一 SQLite 快照检查全局预算采样保护；上述回归在保留原样本和期限的前提下通过，稍后较高水位提交也不能被当作原始返回时间（`/tmp/sdk-global-pending-regression-after.log`）。独立检查的四项兄弟执行场景通过，但另一真实入口交错仍失败：其他处理器在入口 pending 时已采样，却尚无预算采样保护，返回观察仍可能接受较低水位（`/tmp/sdk-global-pending-entry-regression-before.log`）。入口确认清除 pending 时还须原子发布原样本，单加 pending 查询不够；正在处理，不能宣称全局完成时钟已修复。

进一步的真实临时 SQLite 探针确认，即使另一入口已经 confirmed，公开兼容路径的 `HandlerContext` 在 `guard_budget=False` 时仍能先持有高时钟样本、后通过公开预算接口发布；此时没有全局采样保护或 pending 入口，返回观察仍可错误接受较低值（`/tmp/sdk-legacy-context-clock-repro.py`、`/tmp/sdk-legacy-context-clock-repro.log`）。因此检查保护记录和入口状态只能处理有记录的交错，完整修复还须覆盖该受支持的采样与发布路径，或有可执行的参与者隔离协议。

限时停止独立调查另复现：`RuntimeHost.start()` 在持锁构造线程池时若被阻塞，另一线程的 `stop(timeout=0.1)` 在 0.5 秒后仍未返回；释放闸门后启动和停止线程均结束（脚本 `/tmp/dispatcher-host-stop-constructor-repro.py`，日志 `/tmp/dispatcher-host-stop-constructor-repro.log`）。仅将关闭线程启动移出锁并不足以修复：停止前的选择通知中断须保留原未启动线程；而带关闭钩子的启动失败要求先尝试启动关闭线程并保留启动异常的优先级。若将线程池构造移出锁，还须持有未完成的启动所有者，防止停止提前关闭或丢失迟到返回的资源。双独立启动通道是待证明方案，并非已完成修复。

OpenCode 技术重试的独立调查确认：套接字创建抛错既可能发生在分配前，也可能发生在实际分配之后、资源交给调用方之前；现有测试 `test_unknown_creation_handoff_remains_pending` 覆盖后一种情况。仅凭错误类型或进程尚未启动无法确认清理，不能据此释放未知所有者并重试。资源取得并登记之后的部分绑定失败已有精确清理路径；创建调用本身仍需可追踪分配及交接协议。

入口路径复核还发现，外部监督器可以在确认入口时提交已有预算样本，而存储接口没有证明该外部生产者已停止采样的交接凭据；仅检查 pending 并在确认时发布收到的水位，不能排除它稍后提交更高样本。此外 `_prepare_execution_budget(..., pending=False)` 也可能将已有 pending 记录改为 confirmed。曾试验返回读取对同一快照中可见的 pending 入口保守返回 unknown，原入口交错与采样保护组合共六项通过（`/tmp/sdk-entry-pending-partial-01.log`）。独立复核发现：残留的 pending 入口可能在重启后一直存在，从而无限阻塞所有无关执行的完成和子结果交付；扫描全表也可能耗尽原检查期限。该试验已撤回，原入口回归重跑仍失败，而登记采样保护回归通过（`/tmp/sdk-entry-pending-reverted-01.log`）；确认后先采样后发布的路径也未修复，完整协议仍待解决。

旧预算接口的独立调查确认，调用方可以在 SQLite 之外保留构造或反序列化的预算样本，之后才调用 `record_execution_budget`。返回观察时，存在该未登记样本与不存在样本的数据库状态可以完全相同，因此单靠扫描数据库中的采样标记或入口状态无法区分。要证明原始返回时间，需要在采样前建立可验证的持久参与关系，并约束导入样本和旧参与者；是否能同时保持既有兼容合同仍待解决。已将真实 SQLite 的旧 `HandlerContext.budget` 交错加入回归，受控样本高于被错误接受的完成时间，当前定向失败（`/tmp/sdk-global-legacy-regression-final.log`）；独立复核确认公开预算读取与记录路径及其先后顺序，但该测试手工创建 context，非真实 Runtime 端到端。当前仅修复了已登记采样标记的交错，不能推广为所有公开接口均安全。

时钟协议迁移的只读调查指出：现有 SDK 连接持有维护参与锁，可作为升级期间排除配合的旧连接之基础；新 schema 标记可以拒绝旧客户端打开新库。但现有升级是复制，不会自动退役源库，维护锁释放后旧客户端可能重新打开源库，因此必须另行证明源库退役、目标激活及旧客户端的实际围栏。即使所有连接退出，旧调用方仍可能在库外保留早先的预算样本；新协议必须验证采样前持久登记、准确样本和身份，并贯穿入口、子调用、进程消息及恢复，不能将未认证导入样本当作已证明的全局时序。上述是设计约束和兼容性问题，尚无完整实现或验收。

进一步检查发现 v8 交付授权目前只支持持久线程 Runtime，AgentApp 也尚未启用它；仅为部分调用启用 v8 不能阻止同一 Kernel 的未标记调用或旧 API 推进共享水位。一条待实施方向是仅对新建 AgentApp 存储启用全库严格时钟协议，对每个采样者及导入入口统一落实凭据和旧客户端围栏，旧存储保持原有接口；进程模式仍需单独实现。严格库拒绝或保留未知的无凭据外部样本会收紧该库上的旧调用行为，不能称为对所有旧用法透明兼容。这是有待证明的设计方向，不是已经交付的兼容方案。

限时停止的复核补充：并发第二次 `start()` 等待协调线程启动结果，如果把线程池构造直接移出锁而构造失败，该结果可能永远不会发布。当前源码增加构造结果和所有者交接阶段，有限 stop／join 在构造未结束时按原期限返回；受控线程测试覆盖迟到成功、构造失败、通知失败、重入停止及并发启动。独立复核发现构造返回后、发布 executor 前中断会丢失该 executor（`/tmp/repro-host-executor-handoff.py`）；探针包装真实 executor 并预先启动受控线程，标准库普通构造函数本身不启动工作线程。现已保留已赋给局部变量的 executor，包含此交错的 14 项定向测试通过（`/tmp/sdk-host-construction-focused-02.log`），但未证明构造返回到局部变量赋值之间的交接。独立复核还复现另一中断点：发布 starting 后、进入构造异常保护前中断，导致构造结果永久未发布（`/tmp/repro-host-construction-boundary.py`）；后续修订及验证见下一段。关闭及撤销线程自身启动受阻的期限缺陷也未解决，G16 未通过。

随后复现构造已发布、协调线程尚未启动时中断导致永久等待（`/tmp/repro-host-post-construction.py`）。当前源码已用外层所有者保护覆盖启动预约、构造、协调线程启动及清理选择；实际启动前中断时保留 executor 并选择清理，启动尝试不明时保留原协调线程而不伪造清理。独立复核确认上述两个中断复现均能关闭 runtime，未发现此范围内其他具体回退；17 项定向及 30 项相邻检查分别通过（`/tmp/sdk-host-construction-focused-final.log`、`/tmp/sdk-host-construction-adjacent-final.log`）。构造调用返回到局部赋值之间的所有权、中断恢复本身的任意中断、关闭及撤销线程启动期限均未解决或未证明；G16 仍未通过。

旧版只读数据库的协调文件问题仍未解决：未预先配置协调文件时，打开会创建 `.sdk-lock` 和 `.sdk-lock-anchor`。旧维护进程依赖同一个锁文件进行互斥；改用数据库或其他锁不能保证与这些进程互斥。预先配置现有协调文件或在所有旧维护进程退出后协调升级协议，是已识别的条件，但都不等于当前透明只读兼容已通过。

非空 token 预算仍被接纳前拒绝。现有代理透传提供商请求和流，不能保证在发送前取得输入及输出 token 的可靠上界，断连或崩溃时最终用量也可能未知；已有预算账户亦未提供请求级、跨全部祖先的原子预留。仅解析响应或只限制输出不足以保证原预算。现有合成适配器拒绝用例定向通过，不是 token 预算实现或原生验收。

真实 Linux 描述符耗尽试验进一步确认 G12：`socketpair()` 实际返回 `EMFILE`，资源获取状态仍为 pending，未发布启动前中止回执（`/tmp/sdk-g12-real-emfile-repro.py`、`/tmp/sdk-g12-real-emfile-repro.log`）。试验在子进程内调整描述符上限并关闭测试描述符，未调用模型；不覆盖 Windows。相同错误也可能由获取成功后的交接中断产生，因此这不是仅按错误码允许重试的依据。

另一个独立时钟交错已由真实 SQLite 复现：第二个 Kernel 在写事务中先采集超过原工作截止的时间并暂停提交，第一个 Kernel 随后采集返回时间，当前只读快照仍将其判为已知，第二个事务之后才提交较高全局水位。原始采样、截止和事务先后均由 `tests/test_completion_inflight_writer_order.py` 保留；该回归当前失败（`/tmp/sdk-completion-inflight-writer-order.log`）。这是直接完成捕获与真实事务测试，不是完整 Runtime 或提供商验收；正在检查能否在原期限内可靠建立写入顺序。

后续源码在保留原始返回采样后取得 SQLite 写入预约，再以 query-only 模式检查；无法在原控制期限内取得预约时保留原样本并返回 unknown。真实 SQLite 事务交错及真实线程 Runtime 的两项定向检查曾一起通过，后者保留实际结果和原始未知时间；这只覆盖已有事务内的写入者，不证明未登记的旧预算样本或 pending 入口的全局时序。预约要求已有可写数据库，可能产生 WAL/SHM 文件，竞争时也会降低完成观察的可用性；独立检查未发现只读快照公共检查使用该路径，但不能称为只读文件系统操作。

预约修订后的完成时钟 46 项初次回归有三项报错（`/tmp/sdk-completion-reservation-tests.log`）：两项原测试在已有预约内部启动写入者，另一项的锁竞争观察位于原读取阶段。调整测试交错位置并保留原时间与结果断言后，原范围重跑 46 项通过（`/tmp/sdk-completion-reservation-tests-rerun.log`，13.399 秒）。此结果早于接下来的重试状态与关闭次序源码修正，不是最终候选回归。

独立复核以真实 SQLite 加受控回滚复现连接级 query_only 状态在事务回滚后保留，导致下一次预约错误地报只读；随后还复现重置过程中的 KeyboardInterrupt 被普通重试错误遮蔽。当前源码在重试前复位该状态并保留中断，两项定向检查通过（`/tmp/sdk-reservation-retry-interrupt-final.log`）；主动回滚为测试注入，尚未证明普通生产读取自然触发这一交错。复核另发现关闭重试在释放观察资源前采集线程所有权状态，可能使用过期状态；源码已在排空后重新核对，实际关闭场景仍在验证。

上述修订的组合检查 `/tmp/sdk-reservation-retry-close-focused.log` 已通过前四项，随后停在真实 Runtime 场景，启动会话仍未返回，不能计为通过；正在单独收集线程堆栈，保留原运行。旧 Runtime 结算测试期望对未经认证的旧 journal 记录重新读取完成时间并自动结算，但当前实现将这类记录保留为 unknown；直接恢复旧行为会使可构造记录取得完成权限。现有 v8 能恢复已提交结果的交付，不能恢复所有原始完成时间未知的真实结果，handler 异常也可能保留未知；四项定向测试确认这些局限。需要由真实 Runtime 生成并持久绑定带原采样、结果、租约和清理授权的可信事实，不能以旧测试期望或后来时间水位代替该协议。

独立复核在单独的有界重复诊断中复现卡住，线程堆栈显示测试直接查询 Runtime 正在使用的同一 SQLite 连接，同时运行线程在控制锁下设置该连接 authorizer（`/tmp/sdk-runtime-inflight-repeat-diagnostic.log`）；底层锁/GIL 循环是推断。原卡住会话的线程栈不可见，不能断定与诊断完全相同。测试已改用独立只读连接观察已提交水位，原样本、期限及结果断言保留。六次诊断无卡住、五次通过，另一次运行返回后尚未读到预期结算记录（`/tmp/sdk-runtime-writer-fixture-six.log`）；正在确认原始结果是尚未持久化还是丢失，不能将该负例改记通过。独立关闭重试原测试在当前源码单独通过（`/tmp/sdk-reader-close-retry-diagnostic.log`，1.072 秒），不证明所有关闭路径均已修复。

新增失败现场采集但不主动触发持久化后，12 次独立诊断均通过（`/tmp/sdk-runtime-writer-fixture-diagnostic.log`）；未再产生空记录现场，故仍无法判断上述失败时结果是否延迟、保留或丢失。源码对到达 `_commit_outcome` 的结果先保留内存待处理项再尝试写 journal，但不足以证明失败的那次执行已到达该位置。原六次的失败和原组合卡住记录保持不变。

当前源码再次执行完成时钟全局采样的三个原用例，已登记保护的场景通过，外部旧预算采样及 pending 入口采样两项仍错误接受较低返回时间（`tests/test_completion_global_pending_guard.py`，3 项、2 项失败）。写入预约只能约束已取得 SQLite 写锁的生产者，不能证明事务外的采样已全部登记。全库严格协议需要限定新库存储模式、拒绝旧客户端写入并覆盖每个采样与外部预算导入入口；保留旧库行为和新库收紧行为之间的兼容性仍须实现与验证。

限时停止四项与进程退出合同三项按原期限复跑（`/tmp/sdk-host-current-handoff-exit.log`）：关闭和撤销线程启动受阻两项仍失败，其余五项通过。独立生命周期试验（`/tmp/sdk-host-launcher-lifecycle-probe.log`）观察到守护启动通道可能在退出时丢弃清理、空闲非守护通道可能阻止退出、fork 后继承的线程通道不再存活；尚无覆盖这些条件和原异常优先级的已验证修复。

受控的真实线程 Runtime 场景验证了结果交接可以晚于 `run_once` 返回：返回时原租约及待交接所有者仍保留；放开工作线程后，原结果和未知的原始完成时间先进入待处理项，随后写入 journal（`/tmp/sdk-writer-late-regression-reviewed.log`）。该测试使用了明确的阻塞闸门，不能证明此前六次诊断中一次缺少记录的原因，也不能证明进程崩溃后的结果可恢复。

入口时钟补充修订：新建预算入口复用同一事务已观察并用于权限检查的时间，避免随后单独读取墙钟却不发布其水位；等待入口确认时的原始墙钟采样改用已有登记／确认机制。受控 SQLite 检查分别覆盖采样已提交及确认失败仍保留登记标记；入口准备、采样保护和线程入口门禁等 24 项定向检查通过（`/tmp/sdk-entry-boundary-final-focused.log`，14.001 秒）。独立复核未发现事务时间复用的具体回退；登记采样在入口增加了存储依赖，可能影响竞争时的可用性。

上述修订没有解决全部全库时钟次序：真实 SQLite 受控交错中，入口后续的本机经过时间投影仍可能超过已提交水位，另一执行却将较低完成时间认定为已知；新增 `test_foreign_pending_entry_elapsed_projection_keeps_return_unknown` 按原始事实失败（`/tmp/sdk-entry-elapsed-regression.log`）。旧公开预算接口在事务外保留样本的问题也仍然存在。此前试验过将入口完整时间投影直接提升为全库水位，但审查发现可能将过期租约写成待处理入口、且未证明继承样本的全库权限，该试验已撤回。一次单独模拟只推进入口一侧本机时间的探针不代表物理一致的跨执行时序，不作为该结论的证据。

线程入口门禁原测试中的回调观察器之前只认不带 `deadline` 参数的调用，而实际退出回调传入了 `deadline=None`；现改为观察实际回调路径，保留执行期限和结果断言。修订后一次七项检查有两项返回 running 而非预期终态，原结算记录后来持久化，现场及失败保留在 `/tmp/sdk-handler-entry-callback-fix.log` 和对应测试目录；独立复核确认存在 SQLite 写入竞争，但持锁事务的具体 Python 调用者未证明。之后当前源码的七项在上述 24 项中通过，不改写先前失败。另一次独立组合中预算采样关闭测试的预期结果为空，18 项中 1 项错误（`/tmp/sdk-entry-clock-publication-combined.log`）；原因尚未确认，这两组检查均不是完整回归。

该关闭测试的原始记录已核对：数据库写锁阻止原始完成时间确认，业务值保存在同一执行代次的 `completion_time_unknown` 待确认记录中，不能将其作为已授权终态。测试修订后核对实际处理器租约、原始完成采样及只读重开后的待确认记录，并继续检查关闭交接；加强后的单项运行通过（`/tmp/sdk-budget-capture-close-lifetime-strengthened-final.log`）。此结果不证明原始未知完成时间能够恢复，G14 仍未通过。

入口重准备修订：同一租约的入口已持久化截止时间但尚未确认时，重复调用 `prepare_execution_budget` 不再仅凭截止时间将其改为 confirmed，仍须显式确认。真实 SQLite 定向和相邻准入检查共 27 项通过（`/tmp/sdk-entry-reprepare-pending-focused.log`）；独立复核及租约过期、重新领取测试确认不同代次不会借此覆盖原待确认入口。这个收紧可能使在确认前失去租约的入口持续阻止后续尝试，当前没有已验证的自动退休路径；确认接口仍未证明外部采样者已停止，故不解决全局时钟排序，也不构成 G14/G15 验收。

G17 受限资源历史失败的只读调查补充：`/tmp/sdk-g17-resource-native-02/` 保留的子执行效果显示已提交成功输出，结算记录却因 `BudgetClockUnknownError: completion_clock_original_floor_unproven` 保留为完成时间未知；其后控制器达到原期限，子执行因等待耗尽而取消，控制诊断记录 `child_wait` 和 `ChildExecutionError`。外层报告只保存 `AgentExecutionError` 类型，没有正文或确切抛出位置；候选代码可能由多个分支产生该时钟错误，现场不能确定具体分支。这是历史候选的真实失败及待确认结果证据，不证明资源准入本身有缺陷，也不证明当前源码必然复现。

G17 验证器的失败证据现补充有限异常链类型和验证脚本内已知函数的行号，不记录异常正文、局部变量或外部文件路径；诊断遍历也不依赖异常对象的真假值。17 项验证器定向检查通过（`/tmp/sdk-g17-probe-error-location-final.log`）。这只能改善后续失败定位，不能补回历史现场或替代当前安装包的真实资源场景验收。

独立审查发现任意动态异常类名也可能包含敏感信息；现仅输出固定白名单标签，其他类统一记为 `ExternalException`。增加动态敏感类名负例后，18 项定向检查通过（`/tmp/sdk-g17-probe-error-location-sanitized.log`）。类名不是可认证身份，固定标签仅用于诊断分类。

复核还发现资源准入观察错误的单独字段曾直接记录异常类名；现使用相同固定分类，并通过实际准入池注入动态敏感类名验证输出不包含该名称。全部 19 项定向检查通过（`/tmp/sdk-g17-probe-error-location-grant-sanitized.log`），这不代表真实资源场景通过。

普通线程处理器异常增加 v3 原始失败观察：启用版本化交付时在效果收集前采样并绑定原异常；普通效果收集失败时保留原异常与采样作为不授予结算权限的证据。真实 SQLite 的普通失败交付、采样未知、控制异常排除、不可格式化异常、取消和重启续接六项通过（`/tmp/sdk-v8-ordinary-failure-final-independent.log`）；另六项涵盖捕获期间取消、错误所有者／内容／租约代次拒绝、旧模式异常传播及普通效果收集失败证据（`/tmp/dispatcher-v8-failure-final.log`）。这里的错误代次是篡改租约的负例，不是重新领取后的真实代次测试；SDK 控制异常未使用 v3 事实，不代表各类失败均可交付。

上述线程异常修改仍有明确缺口：效果收集在采样后被 `BaseException` 中断时，原始采样事实未能通过该路径持久保留，关闭激活亦曾超时（`/tmp/dispatcher-v8-failure-review-rerun.log`）；实际 SQLite 提交期间的取消竞争未验证。延迟收集时，普通失败和既有成功路径都可遇到 `return observation precedes the committed clock floor` 而无法交付。v3 同样继承全局未登记采样竞态，不能据局部测试认为 G14／G15 完成，也不能作为最终制品验收证据。

中断事实补充修订：若工作线程的限时写入成功，现能将精确租约的 v3 异常和原采样保存为 unknown，随后继续传播原中断；真实 SQLite 写入和关闭后只读回看已有定向证据（`/tmp/dispatcher-interrupted-failure-final.log`，5 项通过）。独立复核确认 Python 3.10 上也不依赖 `BaseException.add_note`。该修订并未闭合中断恢复：写入失败或提交结果不明时，退出流程仍释放持有原始捕获的所有者，缺少可重试交接；成功写入场景的 runtime 仍报告未持久化结算，交付激活关闭亦因待处理所有权超时。不得将前述局部成功理解为该路径已可靠恢复，实际 SQLite 提交期间取消与全局时钟竞态仍未解决。

结果发布中断补充修订：工作线程在 Future 已发布后不再再次发布异常；如 Kernel 已提交，则先核对精确租约及结果回执，避免再写一条 unknown 并误报保留失败。两个真实 SQLite 定向测试通过（`/tmp/dispatcher-v8-publish-interrupt.log`）；独立复核未发现该范围内新的具体回退。提交后中断仍可留下待处理交接并阻止激活关闭，不代表交付协调已完成；失败保留写入不明及全局时钟问题也仍未解决。

合并复查当前源码的上述中断、结果交付、采样期间取消及失败保留场景，7 项通过，耗时 22.580 秒（`/tmp/dispatcher-interrupted-failure-combined-final.log`）。其中写入失败测试只证明原中断未被替换，不证明写入失败后的事实可恢复；已知待处理交接及清理缺口保持未通过。

中断事实的提交回执补充修订：原工作线程在实际写入后丢失确认、再次保留同一条未知事实时，现会在写事务内核对精确租约、事实、时钟、unknown 状态及空决定；相同记录不重复插入，冲突事实拒绝。新增真实 SQLite 提交后模拟回执丢失的测试原先因唯一约束失败（`/tmp/sdk-interrupted-fact-idempotency-before.log`），修复后通过；独立复审未发现该范围内的具体错误。当前源码合并运行中断、取消及交付相关 8 项通过，耗时 25.836 秒（`/tmp/dispatcher-interrupted-fact-idempotency-combined.log`）。回读不验证原记录的完整预算字段，也不是独立线程重试接口。真实写锁超时探针仍发现事实只保留在原工作线程、退出时凭据被移除；写后回执丢失探针虽确认记录存在，交接仍未完成（`/tmp/dispatcher-interrupted-retry-probe-rerun.log`）。线程退出后的安全转交、提交结果不明时的自动核对、关闭清理与最终 G14 验收仍未完成。

同一执行代次已有授权结果时，后续尝试记录未知事实的真实 SQLite 负例已补充：拒绝改写且原失败结果保持有效；与同事实重试检查共 2 项通过（`/tmp/sdk-interrupted-fact-idempotency-authorized.log`）。

全局时钟协议的独立调查已列出待约束的样本生产者（`/tmp/sdk-clock-producer-inventory-review.txt`），覆盖公开准入、入口及父子预算投影、线程／进程返回采样和事务写入。单纯在数据库写事务内采样不能保留处理器返回时、效果收集前的原始时间；若预先登记每个潜在返回采样，则其他尚在运行的处理器会阻止并发完成确认，且只有证明生产者永久失权后才能退休登记。该保守方案尚未满足并发可用性要求，不作为已实施修复；G14／G15 的原始时钟竞态继续未通过。

G12 控制通道的独立调查确认：真实 `socketpair` 在描述符耗尽时返回 EMFILE，但 SDK 的获取令牌仍为 pending，因而未提交启动前中止回执。不能仅改用 CPython 的 `_socket.socketpair` 并根据捕获到的错误码断言系统调用失败：受控 Python profile 钩子在原生调用成功返回后、SDK 接手前注入同一 EMFILE，观察到当时已创建两个描述符（`/tmp/sdk-socketpair-native-profile.py` 与 `/tmp/sdk-socketpair-native-profile.log`）；本次异常展开后描述符数恢复，仅证明这一次的清理，不能泛化为所有平台和交接场景均有认证清理。原生函数属性也可能被替换。该方案未采用，G12 的重试与获取所有权仍未闭合。

对该历史 G17 现场的补充核对：子执行的效果和 `CHILD_NATIVE_OK` 产物已提交，原始完成采样对应的 authority 当时即为 unknown，随后才形成待处理结算和 `child_wait` 失败。原记录没有当前诊断字段，因此无法从中确定路径、共享水位或 ACK 检查中的具体失败分支；采样现场立即保留 unknown 的证据也不足以归因为后续恢复分支。历史 G17 使用独立的 `/tmp/sdk-g17-resource-candidate/venv/`，不能与候选 52 或当前源码混同。

G15 的非空 token 上限调查：当前 OpenCode 代理原样转发请求和流式响应，仅在出站前计入模型轮次；`AgentApp` 和 OpenCode 适配器均拒绝非空 token 上限，`AgentRun.usage` 只显示 Agent 调用和模型轮次。现有 `ApplicationBudget.reserve` 每次只在一个范围内提交，`_charge` 逐一处理根范围和祖先范围；已有未决预留会阻止新预留，`settle` 也没有把实际用量限制为预留量。因此不能直接把现有轮次计数改名为 token 计数并声称硬上限。

后续实现须先确定所计入的输入、输出及缓存／推理等项目，并为具体供应商、模型和请求形态核实可保证的上界：发送前在根及全部祖先范围原子预留该上界，并限制供应商侧输出；发送状态或最终用量未知时保留原请求身份和预留，不盲目重发。Anthropic 的[预先计数说明](https://platform.claude.com/docs/en/build-with-claude/token-counting)明确其计数是估算，不能单独作为严格上界；其[流式说明](https://platform.claude.com/docs/en/build-with-claude/streaming)中的累计用量也须按供应商协议解析，断流不能当作最终用量。任意 OpenAI 兼容接口不能仅凭接口形式假定具有这些保证。上述是实现与验证的待办方向，尚未证明现用供应商满足条件，也没有实现或验收 token 上限。

线程失败事实交接的局部修订：工作线程发布完成凭据前，在其预留的有界槽中保留绑定租约、存储及进程的原始失败采样；工作线程中断后，可将部分未授权事实以 `late_thread_fact` 写入独立结算日志。真实 SQLite 写锁、日志提交后回执丢失及重开读取等定向场景包含在 10 项检查中（`/tmp/dispatcher-handoff-focused-2.log`，12.884 秒）；独立复核的 5 项检查通过，主执行将交接、已授权结果、普通失败、取消及正常成功合并复验的 10 项也通过（`/tmp/dispatcher-handoff-independent-combined.log`，18.995 秒）。效果收集未确认时显式保留 unknown，不根据该事实授予完成权限。提交调用之前中断的另一项检查仅证明候选和事实仍在本进程内存中（`/tmp/dispatcher-handoff-decision.log`），不证明进程崩溃后可恢复。

上述修订仍有未闭合的边界：决策尝试不明时，尚无基于精确结果回执的自动对账。独立复核以 260,000 字符的实际失败探针确认，261,488 字节的捕获事实可写入结算日志，但完整记录需 262,181 字节，超过 262,144 字节的默认恢复读取额度，默认扫描只返回 oversized 且不解析该记录；可显式提高读取额度（`/tmp/dispatcher-failure-size-review/probe.py`、`/tmp/dispatcher-failure-size-review/output.txt`）。Kernel 原工作线程事实保留也有 256 KiB 上限。该结果是默认恢复可用性缺口，不表示日志写入失败或持久事实必然丢失。原始全局时钟竞态、进程崩溃恢复和 G14/G15 完整验收均未解决；本修订不得视为上述缺口完成。

当前源码重跑全局时钟的入口经过时间投影与旧预算读取两项受控回归，仍均失败（`/tmp/sdk-current-clock-interleavings-20261104.log`，0.867 秒）：两者均实际返回已知完成时间，而测试要求对无法确认的原始水位保留 unknown。两项使用真实 SQLite 与手工构造的 `HandlerContext`，不冒充完整 Runtime 或最终安装包证据。

提交尝试不明的后续核对须区分正反证据：`_owned_handler_result_committed` 的 false 同时涵盖无记录、不匹配和连接仍处于事务等情况，不能据此断言提交未发生；工作 Future 完成也不代表线程对象退出或完成凭据的撤销已成功。对已提交结果，须结合准确租约、原始候选、返回见证和存储／意图绑定进行 v8 权威快照核对，并单独确认交付与所有者清理；不能把普通待提交结果记录当作非授权事实。以上为源码调查出的约束，尚未实现完整对账。

独立真实 SQLite 探针注入完成所有者注销超时：工作 callable 结束后 Kernel 仍保留一个 active 所有者及其捕获凭据，原始 KeyboardInterrupt 和注销失败诊断均被保留；随后 Runtime 和交付激活的 close 均返回（`/tmp/dispatcher-owner-release-probe.py`、`/tmp/dispatcher-owner-release-probe-2.log`）。这证明所测注销失败场景的内存所有权尚未闭合，不证明凭据已被其他线程使用，也不能将正常关闭返回视为该所有者注销成功。该缺陷待修复。

完成所有者清理的后续试验在提交工作前登记准确所有者；工作 callable 退出时独立撤销其完成权限，注销未确认时保留清理义务，并阻止 Runtime 及交付激活正常关闭。独立复核指出事实保留的两个入口也须检查撤销状态，以及后台清理中断不能终止重试线程；修订后在单线程池复用同一工作线程验证旧权限被拒绝，作者及独立复核分别运行的 8 项检查通过（作者日志 `/tmp/dispatcher-owner-fence-final-3.log`；独立复核耗时 25.101 秒）。Event 清除失败用例后续加强为实际观察工作线程中的 `HandlerContext.close()` 成功返回，单项通过（`/tmp/dispatcher-owner-observation-close-20261105.log`）；它不证明所有观察资源均已物理关闭。提交已接受但 Future 未返回时，原清理义务仍可能持续无法确认；反复发生的异步中断也未全面证明安全。上述仅覆盖所测线程交错，不代表进程崩溃恢复或 G14／G16 验收通过。

当前源码把上述清理、失败事实交接、幂等重试、正常结果和取消合并复验，18 项通过，耗时 40.179 秒（`/tmp/dispatcher-owner-handoff-independent-final.log`）。这是源码定向检查，不是候选 52 的完整回归或最终安装包验收。

对两项全局时钟失败的进一步源码调查区分了两个生产者：受保护入口采样确认后，`_enter_handler` 仍可能在保护外推进经过时间投影；旧 `HandlerContext.budget` 可在数据库外采样，之后才登记。其他执行在读取返回时间时无法区分尚未登记的采样与不存在采样，因此仅在完成写事务时加锁不足以证明全局顺序。一个可能的局部改进是让受保护入口的登记覆盖实际采样及最终投影，并在退出登记前原子发布；它仍不覆盖旧客户端或外部预算，尚未实施或验证。

完整方案还须约束所有生产者及旧写入者，保留中断后的精确待确认登记，避免无凭据地过期清除；并为原始返回建立可信顺序凭据，区分返回前的其他采样与效果收集期间才发生的采样。建议端到端验收以真实 SQLite 和两个实际 Runtime 处理器控制交错，分别检查返回前待登记采样保持 unknown，以及返回后的新采样不会误拒原先按时完成的结果，再覆盖重启、跨进程和旧版导入。现有 v8 接线尚未提供上述完整凭据；这是一项待设计并实现的协议，不是已验证修复。

受保护入口的局部修复调查发现，现有采样接口在取样／投影与将结果交给登记所有者之间仍有中断窗口：登记可保留为 sampling，原始采样却只在已展开的调用栈上，既有重试无法还原。仅延长登记生命周期可以保守阻止错误确认，但不能保证恢复原始事实；没有采用把重采样当作原采样的补丁。要保证该边界的原事实可恢复，还需明确新的采样所有权及恢复接口；这是实现限制，并非已完成设计。

停止期限的后台启动试验中，四项原始截止时间检查通过；相邻生命周期定向运行共 21 项，仍有 2 项失败、1 项错误，涉及原有通知／启动的中断顺序，故该试验未通过。独立子进程探针在尚未启动的宿主上阻挡清理线程启动，`stop(.1)` 返回 false 后进程正常退出，清理调用次数仍为零（`/tmp/dispatcher-host-caretaker-review/process_exit.py` 及同目录 `.log`）。这一结果证明后台守护启动者不能单独保证进程退出前的清理；后续修订必须同时满足有限停止期限、正常退出和原通知顺序。另在 fork 前由其他线程持有宿主锁时，子进程调用 stop 会在进程检查之前阻塞；这不证明 SDK 承诺支持 fork 后复用宿主，但当前实现不得宣称完整的 fork 安全。

该后台启动试验现已从宿主源码撤回，恢复到试验前的 `/tmp/host-before-lanes.py`，不采用仅在本机 CPython 3.12 验证过的私有退出钩子。独立复核确认源码与该试验前副本一致，先前构造、通知和所有权逻辑仍在；因未保留完整试验前差异，不能独立证明 21:44 之后没有其他修改被覆盖。撤回后按原期限复验原 21 项，19 项通过，仍有两项既有停止期限失败，耗时 3.218 秒（`/tmp/dispatcher-host-restored-original-21.log`）；试验引入的通知顺序失败未在此组合重现。两项停止期限问题尚未修复。

受保护入口的采样与经过时间投影现由同一待确认登记覆盖，成功时先将准确投影写入共享水位再退休登记；投影期间其他返回仍保持 unknown。独立复核发现首次修订在投影后重置了提交等待时间，后续试验按新入口保护的控制窗口计算剩余时间，超时则保留原投影供有界重试；但该 0.1 秒窗口是否给原先的投影新增了限制正在核查，不能宣称与原行为等价。中断发生在投影和交接之间时，只能保留未解决登记，不能声称原采样可恢复。入口及重试相关 9 项合并通过（`/tmp/sdk-entry-guard-combined-20261105.log`，2.761 秒），实际线程正常完成、失败交付、取消和观察关闭 4 项通过（`/tmp/sdk-entry-normal-delivery-20261105.log`，6.875 秒）；独立复核三项通过（`/tmp/sdk-entry-guard-recheck-20261105.log`）。旧版未登记采样的原测试仍失败（`/tmp/sdk-entry-review-module-20261105.log`），全局生产者协议和进程崩溃恢复仍未完成。

应用预算账本新增同一 SQLite 事务内的多范围预留与结算基础：宿主显式提供全部范围，提交回执丢失后的重放不重新授权，未知结果保留预留，实际量超过预留量拒绝；与旧单范围记录共享核算。旧范围导入与分组请求 ID 冲突曾被独立复现，修订后在导入事务内拒绝，原分组仍可结算（`/tmp/sdk-group-collision-recheck-20261105.log`）。新旧账本合并 21 项通过（`/tmp/sdk-group-budget-combined-20261105.log`，2.996 秒），包含真实进程在提交前后退出和竞争预留；该测试使用独立测试库。分组记录尚不能归档，受每范围 10,000 条历史上限约束；若账本遭外部修改或损坏而缺失分组成员，单范围操作无法从当前 JSON 清单检测到缺失。宿主须保证账本完整性。此基础未连接 OpenCode，宿主仍须证明所有祖先范围、提供商可强制的上限和最终用量；非空 token 上限及 G15 仍未通过。

独立复核未在分组账本的正常运行路径发现其他具体缺陷，但指出 v1 升级尚缺测试。补充以隔离测试库构造的 v1 结构后，旧已消费量和未知预留均保留；未知预留阻止新分组，核对后才可预留。新旧账本及 v1／v2／v3 升级合并 22 项通过（`/tmp/sdk-group-budget-migrations-final-20261105.log`，3.469 秒）。这些结构由测试构造，不是生产账本样本。

入口保护修订的独立真实 SQLite 复核确认：在 10 秒工作预算内，入口投影耗时约 150 毫秒后仍可正常调用处理器一次（`/tmp/sdk-entry-slow-review-20261105.log`）；但投影后的存储确认只尝试一次，真实写锁持续超过 100 毫秒时，即使还有约 9.9 秒预算也返回不可重试的 handler_error（`/tmp/sdk-entry-storage-retry-review-20261105.log`）。另在 80 毫秒父级期限内阻塞投影约 150 毫秒时，处理器没有执行，但到期被错误分类为 handler_error／TimeoutError（`/tmp/sdk-entry-parent-expiry-review-20261105.log`）。这两项均为修复中缺陷，上述慢投影通过不代表入口协议完整通过。

G12 补充核对：AgentApp 在长期宿主进程的线程中创建控制 socket，原生 guard 是在控制通道创建后才启动；guard 的后代清理回执不能证明宿主 socket 已交接或关闭。既有 Kernel 进程监督器也没有为这次宿主内资源获取提供逐次认证回执。可探索由预先建立、独立持有资源的受管进程负责创建和清理，但其启动、通信和描述符交接本身仍需跨平台证明；目前没有采用该方案。重新执行的三个保守所有权用例通过；完整 socket 所有权测试模块因运行环境拒绝创建 AF_INET socket（PermissionError）而有 1 项失败、6 项错误，不能计为通过，也不能仅据此认定产品故障。

入口保护随后增加了对已捕获事实的原身份重试；入口准备、正常线程交付、失败和所有者清理合并 23 项通过（`/tmp/sdk-entry-guard-independent-combined-20261105.log`，40.334 秒）。独立复审仍复现三个测试未覆盖的缺陷：无父级期限的首次入口遇到新增登记写锁时失败，而按相同闸门重建的原入口能执行（`/tmp/sdk-entry-begin-final-review.log`、`/tmp/sdk-entry-begin-baseline-review.log`）；存储锁持续超过父级期限时仍被分类为数据库错误（`/tmp/sdk-entry-ack-expiry-final-review.log`）；提交确认后抛出的非瞬态异常被吞掉并执行处理器（`/tmp/sdk-entry-postack-error-final-review.log`）。这些问题尚未修复，前述 23 项通过不能覆盖它们。

允许本地回环后，原 socket 所有权测试模块 14 项通过（`/tmp/sdk-g12-socket-ownership-local-network-20261105.log`，0.019 秒），此前受限环境的失败仍保留。该测试是在 Linux 上模拟 Windows 相关控制路径，不是原生 Windows 验收，也未解决真实描述符耗尽时获取所有权未知的 G12 缺陷。

G16 预热线程池的可行性探针（`/tmp/sdk-host-executor-launcher-probe.py`、`/tmp/sdk-host-executor-blocked-start-probe.py`）在本机 CPython 3.12 观察到空闲池可退出、已排队清理可在退出前完成，以及被阻挡的清理线程启动不阻挡提交；fork 后继承的池无法执行新任务，解释器退出时也不接受后续提交。该探针使用简化清理，不证明真实 Runtime 和回调的退出行为。要覆盖从未启动的宿主，预热会改变构造及所有权交接；提交中断、通知顺序、重入等待、未知提交和跨平台行为均待解决。没有将该试验接入宿主，也没有宣称两项原期限失败已修复。

入口修订后，独立复核的五项定向检查通过（`/tmp/sdk-entry-stable-independent-review.log`，5.060 秒）；包括首次入口的真实线程 Runtime 锁竞争、父级期限到期、确认后异常传播及超过 100 毫秒的有效投影。原启动期限已接入线程、POSIX 和 Windows 工作入口；后两者此次仅审阅源码，没有原生 Windows 执行。确认后异常的真实线程 Runtime 仍未形成持久结果：内部结果保留原始 handler_error，处理器未运行，但 Run 保持 running；显式恢复报告 late-thread authority 未确认（`/tmp/sdk-entry-error-delivery-probe.log`）。当前入口异常在已认证失败采集回调之前返回，既有 Kernel 事实保留和完成路径要求入口已确认；不能只凭登记意图或晚到结果补造失败权限。后续须证明同代唯一所有者、未进入用户处理器、撤销及精确原始事实，并以原子收据处理，否则保持 unknown；此协议尚未实现。

当前源码对入口检查和候选 52 的三个原始失败组合复验：14 项中 1 项失败、1 项错误（`/tmp/sdk-entry-and-candidate52-original-failures-20261105.log`，25.818 秒）。提交边界场景通过；子调用成功场景在结果发布闸门前因 SQLite 数据库锁导致父调用失败，现场在 `/tmp/sdk-child-completed-delivery-evidence-jzx6yo4s/success/`；期限回拨测试未取得预期原始记录并出现 NoneType 错误。两者具体根因正在调查，不能仅根据相同报错断定与候选 52 的历史原因相同，也不能根据其他子场景通过覆盖失败。

复验现场进一步表明：子调用用例的原始执行在确认处理器入口前即失败，没有子请求或结果发布调用；现存证据不足以确定采样的确切调用点或持锁者。期限回拨现场 `/tmp/sdk-runtime-settlement-704y995c/` 中实际记录的是保留原成功值的 `completion_time_unknown`，不是可授权结果：采样线程与已记录的水位确认线程不同，完成时钟保护因此报 `completion_clock_original_floor_unproven`，Kernel 保持 running。候选 52 同名用例当时得到的是 timed_out 结果，两次现象不能等同；当前保护是否满足真实跨线程时序与原用例要求仍须核查。

随后对原子调用场景作了一次带诊断钩子的独立重跑（`/tmp/sdk-child-diagnostic-hooks/test.log`、`trace.log`，15.072 秒）：新入口保护中的首次 `_capture_budget` 在约 99 毫秒数据库锁等待后失败，子请求和发布闸门均未到达。附近多个进程执行过写事务，但无法证明哪一个在失败瞬间持锁；诊断本身也可能改变时序。这确认当前保护新增的采样窗口会影响真实进程执行，不证明先前原始失败具有相同堆栈或锁持有者。修订正在进行。

另一次双 Kernel、真实 SQLite 探针（`/tmp/sdk-unregistered-expired-projection-probe.py` 及同名日志）确认采样的到期快速路径可以返回高于持久水位的本机时间投影，而没有登记采样标记；该探针用局部 50 毫秒工具约束触发到期，没有更改原命令期限。另一 Kernel 的实际完成采样返回 `completion_clock_original_floor_unproven` 和 unknown，没有错误授权较低完成时间，因此此交错只证明未登记投影，不证明已发生错误完成。

首次入口采样的锁竞争修订在真实线程 Runtime 中通过三项检查（`/tmp/sdk-entry-first-capture-thread.log`）；真实 POSIX 进程检查确认处理器在写锁释放后进入，但第一次返回 running（`/tmp/sdk-entry-first-capture-process-3.log`），后一次保留现场的检查通过（`/tmp/sdk-entry-first-capture-process-retained.log`，现场 `/tmp/sdk-first-capture-process-aqltm3en`）。第一次的临时数据库已清理，缺少结算记录，不能确定两次结果差异的原因。首次进程测试还曾因错误地为进程 Runtime 配置仅支持线程的 v8 激活而在准备阶段失败（`/tmp/sdk-entry-first-capture-process.log`）；后续使用受支持的进程 Runtime，均不构成进程 v8 恢复验收。源码及独立复核尚在进行。

随后完整入口定向测试 16 项通过（`/tmp/sdk-entry-first-capture-focused-final.log`，11.332 秒）。独立复核的五项中，四项通过，POSIX 进程项再次返回 running（`/tmp/sdk-first-capture-independent-review.log`，现场 `/tmp/sdk-first-capture-process-q37l4mg0`）；该次入口已确认且处理器已执行，观察记录显示原结果以 `completion_time_unknown` 持久保留，诊断包含 SQLite 数据库锁。它不证明先前临时现场的确切原因，也不能计为进程成功或完整恢复验收。

该次进程现场进一步核实：处理器原始返回值为 `ok`，监督者记录其在原工作期限内返回，工作进程树及进程清理均已确认；原始完成采样及值保留在结算记录，但其时钟验证在 0.1 秒控制窗口内遇到 SQLite 写锁，不能作为已授权完成。之后数据库水位已推进，不能用后采样水位反推原返回时间。现有证据未识别当时持锁者，也不能确定入口重试是否造成后续竞争；这项检查仍失败。

独立源码复核未在本次入口首次采样重试范围内发现其他具体缺陷：重试沿用原启动与继承期限、同一个已捕获事实和令牌；未确认注册不重采，确认后返回不明也不重新授权。本次复核只覆盖所检查的源码和定向场景，不能证明任意中断交接；上面的进程完成时间未知、未登记生产者和入口失败交付问题仍在。

完成时序候选方案（尚未实施，独立审查中）：入口前绑定租约与代次保存基准水位／序号；所有生产者在实际采样前登记，并在发布水位的同一事务记录采样的时钟域、先后区间及被投影水位的来源；处理器返回时保留精确返回事实。恢复时只纳入能够证明在返回前的生产者事实，只有同时证明采样及投影来源均在返回后时才能排除；重叠、未知生产者、丢失历史、时钟域不兼容、登记未确认或提交不明保持 unknown。该设计需要有界历史、回滚后水位保留的原子记录、旧写入者隔离、可信进程返回事实和跨平台证明；不是现有返回见证已经提供的能力。运行期间持有数据库写锁会阻塞正常工作，给每个运行中的处理器长期保留全局采样标记又会阻塞其他完成，两者均不能单独作为修复。

该候选方案的独立设计复核强调，既有采样者可能先于基准登记、之后才发布；回滚时保留的水位也须原子保留其来源。已有旧客户端仅升级 schema 不能使其停止写入；不同原生时钟表示不可直接比较，重叠区间、提交不明、历史缺失及未认证的返回包均只能保持 unknown。方案尚未实施，也不保证所有未知结果均可恢复。

过期预算采样修订：双 Kernel 真实 SQLite 负例在本机时间回拨后暂停已过期局部预算的原始采样，修订前在该时刻没有全局采样标记（`/tmp/sdk-expiry-projection-guard-before.log`）。当前源码移除了登记前的过期投影提前返回，先登记采样，再原子发布原始事实并退休标记；新增定向负例验证期间另一执行无法确认完成、发布水位不低于该事实（`/tmp/sdk-expiry-projection-guard-after.log`）。这一修改意味着已过期预算遇数据库写锁时也可能返回 unknown 或限时错误，而不能保证立即返回过期视图。独立中断探针在登记后、采样前注入中断，确认原 token 与所有者保留、样本未知，关闭不会把它认作已清理（`/tmp/sdk-expired-interrupt-owner-review.py`）。它没有修复其他未登记的旧版公开采样路径或全部提交／撤销竞争。

缺失预算记录修订：原本对尚未建立执行预算记录的命令采样会先登记标记，之后因缺记录失败，却无法确认或清除该标记（`/tmp/sdk-missing-limits-before.log`）。当前登记事务先检查对应记录是否存在，再登记；两个真实 SQLite 定向测试通过（`/tmp/sdk-expiry-projection-and-missing-limits-after.log`）。并发清理和旧调用者的完整行为仍以独立复核和相邻测试为准。

旧版公开预算接口的实际缺口仍在：`test_foreign_legacy_sample_keeps_return_unknown_without_guard` 实测把完成时间判为可信，随后才发布的未登记采样水位更高；同类 `derive_budget` 探针亦复现（`/tmp/sdk-legacy-derive-probe.log`）。改变单一 Context 无法覆盖外部构造或留存的公开预算样本、关闭后的访问及旧进程写入，因此不能据局部登记修订宣称全局时序安全。

非空 token 预算依旧明确拒绝：OpenCode 适配器新增测试确认拒绝发生在启动代理、进程或计费之前；连同 AgentApp 现有检查两项通过。当前代理无法保证总输入及输出 token 上限、提供权威中断用量或完成重启后的预留对账；分组预算账本尚未接入实际 Agent 请求。G15 保持未完成。

上述两处采样修订的预算、入口、真实进程与采样者中止扩展组合共 57 项，在 22.063 秒内 56 项通过、1 项失败；失败仍是上面的旧版未登记采样（`/tmp/sdk-expiry-projection-related-final-20261105.log`）。进程首次采样锁竞争此次通过，但此前同一用例出现过完成时间未知，不能认定该问题已消失。缺失记录检查的独立源码复核及真实线程／进程相邻 8 项通过（`/tmp/sdk-sample-admitted-review.log`）；回滚失败及登记后外部删除预算记录未覆盖，不明事务仍须保守处理。

候选 52 原始子调用交付用例在当前源码及允许本机回环的环境下重跑，成功和原始失败两个子场景均通过（1 项，27.664 秒，`/tmp/sdk-child-original-current-20261105.log`，现场 `/tmp/sdk-child-completed-delivery-evidence-behoy3f7/`）。它保留原测试的父／子期限和发布闸门；此前数据库锁失败保留，现有证据不足以证明此次通过解释了先前持锁原因，也不能替代完整安装包回归。

候选 52 原始期限回拨用例在本轮修订后独立复验仍错误（`/tmp/sdk-watermark-original-current-20261105.log`），现场 `/tmp/sdk-runtime-settlement-yl4_neho/`。只读核对结算记录：原始成功值保存在 `completion_time_unknown` 待确认事实中，原因是来自另一线程的已提交水位没有原始返回先后顺序证明；测试要求的原结果记录为空。该结果不能表示此场景的完成已被正确授权，也不能与候选 52 当时的 timed_out 现象混为同一已证实根因。

跨线程提交回执的候选捷径经真实 SQLite 负例否定（`/tmp/sdk-cross-thread-ack-legacy-probe.py`、同名日志）：旧接口先保存未经登记的高水位，另一线程随后提交较低水位并获得真实回执，墙钟回拨后原实现正确返回 unknown；探针仅将该回执的线程字段改为采样线程，以模拟取消线程检查，结果错误认定较低完成时间可信，而先前高水位稍后才发布。因此在所有旧接口采样及外部导入受到可验证保护前，不可单独放宽该限制；既有跨线程 unknown 测试保持不变。

G16 独立两通道启动原型（`/tmp/sdk_host_two_lane_proto.py`）未接入产品：本机实验中一条通道启动受阻时另一条可执行，正常退出时已登记清理也能完成；但将任务入队和退出注册之间人为暂停，进程可在清理未启动时退出。原型还会在创建中断后留下后台线程、保留 idle 宿主，且拒绝了现有可工作的 fork 后 idle 宿主使用。该原型依赖 CPython 私有退出钩子，其他版本及平台未验证；以上负例使它不能作为限时停止修复。现有真实宿主退出测试 3 项通过，不代表限时停止通过。

旧版采样缺口已在真实线程 Runtime 和 SQLite 中进一步复现：受控墙钟下，旧上下文先采集 +30 秒但不登记，同一处理器线程提交 +2 秒的水位，再回拨至 +1 秒并返回；原预算 10 秒，SDK 将约 +2 秒的结果提交为成功，之后公开预算接口才发布先前的 +30 秒样本（`/tmp/sdk-runtime-external-clock-probe.py` 及同名日志）。启用 v8 交付时也得到已提交成功（`/tmp/sdk-runtime-v8-external-clock-probe.py` 及同名日志）。两项均为受控采样探针，不是原生时钟或崩溃验收；它们说明该缺口可能错误授权成功，不能只描述为结果保持未知。

上述 v8 交错已加入真实线程 Runtime／SQLite 回归 `tests/test_runtime_legacy_clock_order.py`；在当前源码执行时，该测试按预期因 SDK 返回 `succeeded` 而失败（`/tmp/sdk-runtime-legacy-clock-order-regression-final.log`）。独立探针通过只读连接比较同一数据库的逻辑内容，确认旧 Context 保留未登记样本前后数据库内容相同，且之后公开接口接受该样本（`/tmp/sdk-legacy-clock-indistinguishable.py` 及同名日志）。因此仅凭当前数据库快照无法区分这两种情况；该证据不排除引入经过验证的生产者协议，但新协议须同时处理旧写入者和外部持有样本，不能仅凭 schema 更新声称兼容。

控制通道资源修订：针对 socket 或 socketpair 已返回并完成赋值，但尚未登记所有权时发生中断，获取与赋值移入清理范围，清理准确的已返回资源；Windows accept 分支亦作对应修订。Linux 上保留异常回溯的真实 socket 中断及正常交接测试合并 17 项通过；Windows 分支仅为本机模拟，并非原生 Windows 验证。系统调用返回前后的交接、关闭不明及描述符耗尽的 pending 获取仍未解决，不得将此局部修订计为 G12 完成；该修订的独立复核仍在进行。

独立复核又发现两个尚待修复的交接遗漏：实际 POSIX socketpair 返回调用方后、进入内部关闭保护前中断，两个端点之一保持打开（`/tmp/sdk-opencode-return-boundary-review.py`）；模拟 Windows 已认证连接返回前中断，登记过的连接保持打开（`/tmp/sdk-opencode-windows-return-review.py`）。两个场景均保留清理未确认，没有错误生成清理成功回执。复核环境禁止部分本地 socket 操作，所执行的 17 项套件出现 1 项失败及 9 项错误，不能作为产品回归判断或通过证据；两个独立探针本身分别使用实际 socketpair 和模拟连接。

子进程启动诊断补充修订：真实 POSIX worker 反序列化异常时，如果异常的备注属性在格式化时抛出 `BaseException`，旧诊断路径无法发送失败包，接收方只得到 EOF。当前源码在格式化失败时保留异常类型、失败阶段及有界回退文本；真实 fork 子进程回归与相邻诊断测试共 6 项通过。单独令异常 `__str__` 抛出 `KeyboardInterrupt` 在本机 Python 3.12 并未复现丢包，实际负例还包含备注读取失败。上述检查不代表原生 Windows 或完整 supervisor 交付已验证，独立复核进行中。

针对复核发现的两处已返回 socket 泄漏，当前源码把控制 socket 与进程流分开登记；最终清理可关闭未完成交接的控制 socket，并保留未知关闭状态而不重复关闭。作者的 socket 所有权及原生清理两组共 33 项通过；主执行独立复核实际 socketpair 中断、Windows 模拟返回中断、进程流保护和失败关闭四项均通过（0.011 秒）。当前验证不覆盖原生 Windows，也不证明未返回的资源获取或所有异步中断均可清理，G12 保持未完成。

子进程启动诊断的独立复核另复现异常类型名称过长、类型名称读取自身失败导致丢包，以及 `setpgid` 失败被误报为反序列化失败。当前修订限制并标注类型名称、对读取失败保留 unavailable，区分进程准备阶段，并对深层堆栈及回退格式标注截断或完整性未知。复核又发现异常链或异常组内部的堆栈可能被格式化器截断，即使原始异常自身较浅；为保留原布尔字段兼容性，现另提供 `traceback_truncation_known`，未核对完整异常图时不将该状态记作已知；回退读取中断标为不完整，不凭中断推断发生了截断。主执行重跑新测试和相邻诊断测试 15 项通过（0.393 秒），含真实 fork worker 失败包；这些测试直接读取 worker 管道，没有覆盖完整 supervisor／Runtime 持久交付。输出字节及新增栈扫描受限，不代表用户定义的 `__str__` 或标准库异常图格式化本身受时间或内存硬限制。

完整 Runtime 启动失败路径的后续复核：首次测试实际进入了处理器，得到 `AssertionError`，因此不能作为反序列化失败交付证据；修正处理器的序列化状态后，真实 Linux 进程中的反序列化抛出原始异常，Runtime 返回失败并保留异常类型、阶段和堆栈，持久诊断包含 `worker_bootstrap_failed`，处理器入口标记未产生。主执行将该场景与 worker 诊断合并独立复验，13 项通过（1.347 秒，`/tmp/sdk-native-bootstrap-delivery-independent-20261105.log`，现场 `/tmp/sdk-bootstrap-error-delivery-pl7g2z9q/`）。修正后的较早运行曾在关闭时报告诊断持久化未确认（现场 `/tmp/sdk-bootstrap-error-delivery-xnyx6pen/`）。只读比较显示该次执行已失败，关闭事件在结算端已有接收记录，但 Kernel 发件箱中的关闭事件尚未标记交付，生产者仍为 open；对照的通过现场已标记交付并关闭生产者。现有现场不足以确认锁持有者、超时原因或事实丢失；后续通过不能抹去该现象，也不证明所有关闭交错或 Windows 路径已验收。

对该关闭现场的独立复核，在原 8 秒执行和 1 秒关闭清理限制内补充了 6 次真实进程测试，均正常关闭，实测关闭清理约 0.058–0.311 秒（`/tmp/sdk-bootstrap-close-timing-review.log`）。每次都曾留下先前某次诊断接收确认超时信息，但最终待处理及未知数量为零；时序采集可能改变调度，也不能据此推断上述原始关闭失败的原因。

预算采样来源的补充负例：隔离 SQLite 中先在登记前生成比原水位高 30 秒的外部信封，再把它传给当前受保护采样器，持久水位和返回信封均推进到该值（`/tmp/sdk-external-envelope-laundering-probe.py`、同名 `.log`）。登记和提交成功并不能证明传入信封是在登记后采样。维护租约在持有期间可排除同路径、遵守协议的活动连接，但不能认证已由进程或外部保存的信封；复制升级也不自动退役源库。该探针不是修复，全局时序问题仍在。

进程返回值序列化诊断修订：当自定义结果的 JSON 序列化抛出异常，而异常自身无法格式化时，不再调用任意异常的 `__str__`；保留异常类型并标明消息不可用，普通内建 JSON 错误仍保留有界消息。实际传输要求 UTF-8，现于返回前检查编码，使孤立代理字符被保留为无效结果而非进程退出；合法中文及 emoji 的真实进程传输通过。序列化发生在处理器完成采样之后，故该异常的原始完成时间仍是 unknown，不能据此授权普通失败；真实中断继续传播。主执行复验异常、中断、Unicode、启动及原一秒期限共 22 项通过（9.868 秒，`/tmp/sdk-result-serialization-unicode-independent-20261105.log`）；独立审查亦通过 8 项。审查确认，若回退中复制的预算字段或 effect ID 自身包含不可编码字符，回退仍可能无法传输；尚未证明真实 Kernel／存储允许这种元数据进入该路径。额外 UTF-8 编码也会有一次完整结果的内存分配。没有进行原生 Windows 验证，也不能将此修订等同于 G12 或 G14 完整验收。


2026-11-05 token 结算局部修订：独立审查发现非流式 HTTP 200 错误响应可携带合法 usage，导致预留被错误释放。当前源码拒绝提供方 error，并要求受支持的成功响应格式。真实本机代理与 ApplicationBudget 账本检查确认：错误响应保留全部 10 token 未知预留，下一次请求被拒绝且上游仅收到一次请求；成功响应仍按实际用量结算。相关 14 项测试通过，19.116 秒，进程正常退出；原始日志 `/tmp/sdk-token-error-settlement-20261105.log`。这是源码与合成提供方的局部证据，没有调用真实模型，也不是当前安装包、G15 或完整回归通过。设计记录已同步当前接入状态及共享有限额祖先的并发准入限制。


2026-11-05 token 并发预留局部修订：reserve_group 新增默认关闭的 allow_pending，token 代理显式启用。仅完整、规范且金额一致的分组 pending 可按完整上界计入容量；旧单范围 pending 和 unknown 仍阻止准入，身份重放不获得发送授权。独立源码复核未发现本次范围内的新阻塞项。相关账本及真实本机代理 26 项通过，21.382 秒（`/tmp/sdk-token-pending-bounds-20261105.log`）；新增真实 spawn 三进程争抢单项通过（`/tmp/sdk-token-pending-process-race-20261105.log`）：额度 10、三个各 4 的预留恰好两个获得授权，各祖先预留总额 8。两次进程均正常退出。双语 Wiki 与设计边界已同步。以上仅为源码局部验证，尚无当前安装包的真实 OpenCode 并发计量证据，G15 保持未完成。


2026-11-05 当前安装包 token 定向验证：wheel `/tmp/sdk-token-current-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 安装至独立环境，以 `-I` 从 `/tmp` 执行复制的测试。151 个产品文件与当前源码逐字节直接比较一致，未新增摘要检查。47 项通过，28.547 秒，0 失败／错误／跳过，进程正常退出；结果 `/tmp/sdk-token-current-installed-guarded-result-20261105.json`，日志 `/tmp/sdk-token-current-installed-guarded-20261105.log`。覆盖 token 用量解析、本机代理及账本、分组预留与真实多进程争抢、OpenCode 配置和推理变体兼容，不含真实模型调用。首次 runner 缺少 main 保护导致 spawn 子进程重复执行测试，记录为 4 错误并停止该批进程；原结果与日志保留在 `/tmp/sdk-token-current-installed-result-20261105.json` 和 `/tmp/sdk-token-current-installed-20261105.log`，进程身份在 `/tmp/sdk-token-current-runner-failed-processes-20261105.json`。仅修复 runner 入口后重跑，未改变产品代码或测试断言。此结果不能替代 G12 原失败组、G14 故障窗口、G15 真实计量与恢复、G16 生命周期或 G18 平台验收，目标保持未完成。


2026-11-05 G16 原失败核对：保留原期限执行 prestart_shutdown_owner_start_is_bounded 与 running_revocation_owner_start_is_bounded，源码两项均通过（0.258 秒）。随后同一当前安装包完整停止交接模块及正常进程退出模块 9 项通过，3.797 秒，0 失败／错误／跳过，进程正常退出；151 产品文件逐字节一致。日志 `/tmp/sdk-stop-current-installed-20261105.log`。此前两项失败仍作为历史记录保留，不再作为当前未修复缺陷汇报。G16 整体仍需原生竞争、撤销及清理未知的最终候选证据。宿主 `/root/AGENT_RESOURCES.md` 已核对无 token_budget/request_limit/output_limit 字段，未打印内容或调用模型；可信总计费上界合同是 G15 真实 token 验收的外部缺项，已向用户请求配置路径。


2026-11-05 G12 验证边界修正：技术重试矩阵此前用不透明 FaultSocket 工厂抛错推断无资源，而 socket 所有权负例要求同类获取异常保留 pending，两者预期冲突。独立源码复核确认，工作目录准备发生在端点获取和进程启动之前，可走准确 not_launched 回执及相同 errno 分类。因此仅将重试分类矩阵注入点改为 `_prepare_native_workdir`，原断言、预算与期限不变；没有修改产品以信任不透明工厂，也没有放宽未知保护。当前安装包的成功重试、耗尽／非瞬态失败、未知预算拒绝及 socket 获取 pending／已分配后抛错五项通过，17.465 秒，0 失败／错误／跳过，正常退出；151 文件与源码一致，结果 `/tmp/sdk-retry-known-boundary-installed-result-20261105.json`，日志 `/tmp/sdk-retry-known-boundary-installed-20261105.log`。本次不是原故障注入点通过，更不证明真实描述符耗尽可自动恢复。此前 15 项、8 失败 6 错误的记录保留；其余分类用例仍待复验，G12 不标记通过。


2026-11-05 G12 完整分类矩阵未通过：当前安装包 15 项，115.820 秒，0 断言失败、2 错误，进程正常退出；`/tmp/sdk-retry-matrix-current-installed-result-20261105.json` 及同名前缀日志。辅助文件 `_acceptance_evidence.py` 漏复制已修复；仅重跑两项时，成功重试通过，但原期限处理仍超过 30 秒；两项 35.600 秒、1 错误，`/tmp/sdk-retry-two-errors-installed-result-20261105.json`。增加不改原期限的线程现场留存后，仅原期限用例再次错误，31.436 秒，`/tmp/sdk-retry-deadline-thread-installed-result-20261105.json`；现场 `/tmp/sdk-prelaunch-deadline-failure-b0hvmfzp/evidence.json` 及 `/tmp/sdk-prelaunch-deadline-threads-0i0j4vf7/threads.txt`。观察到 adapter_calls=1、boundary_reached=true、准确 not_launched 回执存在，Kernel running、effect performing，执行池线程已空闲；该证据定位到失败返回后尚未完成结算／恢复的路径，不足以确认具体根因。成功重试的整组等待超时也未被单项通过抹去。没有增加真实模型调用、修改产品或放宽断言与期限。


2026-11-05 G12 超时停留根因现场：仅原用例、原 2 秒工作预算及 30 秒等待再次复现，`/tmp/sdk-retry-deadline-settlement-installed-20261105.log`。现场 `/tmp/sdk-prelaunch-deadline-failure-ynn47g38/evidence.json` 明确显示同代 pending 结算记录 `deferred.kind=late_thread_fact`、`outcome.kind=timeout`、准确 runtime effect ID；恢复诊断为 late thread completion authority is unconfirmed，迟到线程所有者为空。源码 Runtime managed delivery 将无已提交结果的监控超时交给 fact_only，恢复逻辑仅报告 unknown，不推进 Kernel；因此 Agent 持续等待 running。独立复核确认不能仅凭 timeout 字段或日志事实授权转换。安全修复需在原监控仲裁确认未发布结果并撤销准确线程的边界绑定权限，随后以原租约、准确效果代次及有界控制窗口登记恢复状态，并处理停止／完成竞争；不延长工作预算、不制造完成结果、不声明清理已完成。该修复尚未实施；本次仅新增失败现场诊断，无模型调用。


2026-11-05 G12 实时监控超时恢复修订：仅在原监控器持有 completion gate 与生命周期锁、确认无已发布结果并撤销本线程的超时分支，尝试在独立 100 毫秒控制期限内登记效果恢复。交付激活保护、原租约和所有未完成效果的 lease_id／attempt／fence 在事务中核对；核对或争用失败保持未知，不赋予重放、完成或清理确认。事务准入使用原控制期限剩余时间，避免重新计时。首次版本的原测试仍失败（`/tmp/sdk-monitor-timeout-recovery-first-20261105.log`）；修正剩余时间后原用例通过3.580秒（`/tmp/sdk-monitor-timeout-recovery-diagnostic-20261105.log`）。新增明确 indeterminate／recovery_required 状态断言后，原用例与完成发布竞争、返回事实及 managed delivery 相关12项通过16.094秒，进程正常退出（`/tmp/sdk-monitor-timeout-recovery-scoped-20261105.log`）。独立源码复核未发现需要回滚的具体阻塞，但尚缺锁／停止／旧代次等指定竞争验证以及新安装包验证；此前安装包证据不覆盖这两处产品修改。G12 尚未通过。


2026-11-05 超时恢复竞争检查补强：新增真实 SQLite managed Runtime 的正常效果停放、提交前停止回滚、Kernel 锁争用三个测试，初版3项6.271秒通过。但独立复核指出原停止断言可能在事务提前失败时误过，原锁等待阈值也不能区分重新获得完整窗口，故初版不作为这两项强结论。修订后在第二次权限检查读取未提交 recovery_required／indeterminate，再设置停止信号，返回后验证 running／performing 回滚；锁竞争先消耗原100毫秒的60毫秒，再要求恢复尝试在原截止时间后25毫秒容差内返回。Kernel `_transaction` 在进入 `_control_lock` 前直接按 strict_deadline 重算剩余时间，覆盖调用前调度延迟。补强的3项加既有 strict_control_deadline 3项全部通过7.284秒，正常退出，日志 `/tmp/sdk-monitor-recovery-strict-races-20261105.log`。在补强前构建的 `/tmp/sdk-monitor-recovery-wheel-20261105/` 已落后当前源码，未作为新修订安装包证据运行，最终安装包验证仍待完成。


2026-11-05 最新监控恢复安装包证据：`/tmp/sdk-monitor-recovery-final-wheel-20261105/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 独立安装后以 -I 执行22项，22.722秒全部通过、0失败／错误／跳过，进程正常退出；151产品文件直接字节比较一致。结果 `/tmp/sdk-monitor-recovery-final-installed-result-20261105.json`，日志 `/tmp/sdk-monitor-recovery-final-installed-20261105.log`。覆盖原期限用例及明确恢复状态、停止前提交回滚、原截止时间锁争用、完成竞争、返回观察、managed delivery及caller deadline。独立复核未发现截止时间合并的具体阻塞。本包不包含全部G12或平台验收结论；技术重试整组仍另行验证。首次生成该整组runner时，在/tmp误用相对.venv解释器，未运行测试，保留 `/tmp/sdk-retry-final-installed-20261105.log`；更正为绝对路径后才启动实际整组，日志另存 `/tmp/sdk-retry-final-installed-actual-20261105.log`，没有重启正在运行的测试。


2026-11-05 最新安装包技术重试完整矩阵：15项、103.320秒，14通过／1断言失败／0错误，进程正常退出；`/tmp/sdk-retry-final-installed-result-20261105.json`，日志 `/tmp/sdk-retry-final-installed-actual-20261105.log`。失败仍为原期限用例，但本次原因与原running挂起不同：adapter_calls=1，boundary_reached=false，native_operations为空；Kernel已recovery_required，效果indeterminate，monitor_recovery_error=null。现场 `/tmp/sdk-prelaunch-deadline-failure-hpcfrv70/evidence.json` 证明两秒原工作预算在测试设定的not_launched回执边界前耗尽，不能据此证明“回执后到期”场景。未放宽原期限或断言，没有将未进入边界视为通过。此前同包22项定向验证包含原边界成功的证据，但不能代替完整矩阵通过；G12保持未通过，下一步须定位进入该边界前的耗时，不盲目重跑。


2026-11-05 原期限边界耗时定位：保持2秒原预算、30秒等待与全部状态断言，新增仅测试内的单调时钟阶段记录。首次单项通过3.588秒：适配器入口只剩0.554483秒，原生prepare耗时0.214844秒（`/tmp/sdk-prelaunch-boundary-timing-20261105.log`）。再拆分一次同一原用例，通过3.668秒：入口剩0.625465秒，prepare前剩0.623144秒；等待现有app RLock为0.206010秒，取得锁后到prepare返回约0.095403秒，总0.301414秒（`/tmp/sdk-prelaunch-lock-timing-20261105.log`）。说明原生登记前已有约1.37秒启动消耗，且应用锁等待占该次登记耗时主要部分；两次仅单项，不代表整组失败已消失或证明所有调度下可在预算内进入注入边界。未延长预算、未改变产品锁或直接操作数据库。


2026-11-05 轮询写锁准入修订：确认 AgentStore.pending 及其元数据路径只有读取后，pending 改用强制 query_only 的一致快照事务，不再申请 BEGIN IMMEDIATE。事务默认及根提交路径不变，只读模式拒绝根提交 gate。初轮存储／等待12项通过22.819秒（`/tmp/sdk-agent-pending-readonly-20261105.log`）；独立复核发现 deferred BEGIN 的首个读在排他锁下可能直接SQLITE_BUSY，已将快照读准入移至原期限重试范围，并在确认争用时回滚后重新准入，不重放调用体。补充真实未提交写入不阻塞pending、只读写入拒绝和排他锁释放后读取的检查；修订后存储模块6项通过0.799秒，原始结果见 `/tmp/sdk-agent-pending-readonly-exclusive-20261105.log`。该源码修订尚缺新安装包证据，也不保证任意调度／存储延迟下两秒内到达测试边界。


2026-11-05 pending只读修订当前安装包复验：`/tmp/sdk-pending-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl` 独立安装，151个产品文件直接字节比较一致。允许本机通信后34项175.895秒，33通过、1错误、0跳过，进程正常退出；结果 `/tmp/sdk-pending-final-20261105/permitted-result.json`，日志 `permitted-run.log`。存储期限6项、等待期限7项、监控恢复3项、严格控制期限3项全部通过；技术重试矩阵14/15通过，本轮原期限边界用例通过，失败变为 exhausted/nontransient 的 prelaunch_retries_exhausted 子场景等待30秒后 Agent wait lock admission timed out。不能将前次边界失败消失视为G12通过，下一步需保留该等待超时的持锁线程现场。首次构建因默认pip缓存只读失败，禁用缓存后构建成功；首次受限执行34项有7错误及15跳过，不作为通过证据，记录在 result.json/run.log，已核对精确进程命令后终止残留runner，身份保存在failed-process.json。同包重新执行未改变产品、断言或期限，未调用真实模型。


2026-11-05 G12上下文诊断：同一当前安装包、原期限，重试耗尽单项10.085秒通过；已在耗尽异常分支增加关闭前全线程现场及调用身份留存。随后保留34项顺序运行，140.708秒、33通过／1失败／0错误／0跳过、进程正常退出；结果 `/tmp/sdk-pending-final-20261105/diagnostic-matrix-result.json`，日志 `diagnostic-matrix.log`。原期限和耗尽本次均通过，失败转为监督线程第二次start抛错场景 adapter.calls=0（预期1），故未获得耗尽持锁根因，不用跨批次通过拼接验收。该监督负例已补充调用次数断言的实际失败结果、监督线程数量及存活状态，产品未修改；G12仍失败。本轮不再重复整组。


2026-11-05 G12监督失败诊断：同一安装包监督start异常单项8.729秒通过；四种监督所有权场景合组36.735秒、4通过、0失败／错误／跳过、进程正常退出。实际范围以 `/tmp/sdk-pending-final-20261105/observer-group.log` 的四个测试名为准，结果 `observer-group-result.json` 仍沿用父runner较宽scope文字，不能据此声称覆盖34项。151产品文件直接字节比较一致，无产品改动。独立只读锁顺序审查未建立app／Kernel／orchestrator循环等待：execute_once在调用perform前已退出效果登记事务；现有整组失败日志缺持锁者现场，无法确认根因。监督失败断言已补充实际result及owner数量／存活状态，耗尽等待失败已补充关闭前线程现场。当前定向通过不抹去整组失败，G12保持failed；本轮不再重复整组，无真实模型调用。


2026-11-05 G12慢调用现场：同一安装包原34项顺序，测试runner在单项10／20／30秒留存全线程栈。154.747秒、32通过／1断言失败／1错误／0跳过、正常退出；`/tmp/sdk-pending-final-20261105/stack-matrix-result.json` 与 stack-matrix.log。失败为原期限未进入注入边界；错误为 transient 成功重试等待原30秒到期（Orchestrator caller deadline elapsed），adapter_calls=2，身份和关闭前栈在 `/tmp/sdk-technical-retry-wait-2bxgrlgt/`。三次慢调用快照在安装包证据目录slow-*文件中。独立复核确认第三次采样时coordinator已经推进到传输路径，故不能宣称连续持锁、死锁或饥饿；执行池空闲也不证明结果已投递。下一步需要对准确执行记录事务阶段、结果发布及传输时序，而非重复测试数量。测试异常分支补充每次200毫秒调用准入期限的公开invocation／Run观察，观察失败只记unknown类型，不授权完成；仅语法编译验证，尚未执行该新诊断分支，不声称系统调用硬期限。原state_dir可能随后被fixture删除，因此旧identity路径不是可恢复数据副本。产品未修改，G12保持failed。


2026-11-05 计划读取写锁修订：慢调用现场出现plan/open_plans，确认两者只有单次SELECT和独立JSON解码，却申请BEGIN IMMEDIATE；改用与pending相同的强制query_only、原期限准入、一致已提交快照。实际未提交写事务保持期间，pending可读但旧plan在原100毫秒期限超时，前置复现 `/tmp/sdk-plan-read-before-20261105.log`；两方法改动后存储6项0.807秒通过，`/tmp/sdk-plan-read-after-20261105.log`。独立审查未发现隐藏写入依赖，原方法也未提供跨调用读写原子性；新读取可看到未提交写入前的已提交状态，不读取未提交内容。新wheel `/tmp/sdk-plan-read-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`独立安装后25项25.122秒全通过、0失败／错误／跳过、正常退出，151产品文件直接字节比较一致；结果 `/tmp/sdk-plan-read-final-20261105/result.json`，日志run.log。范围为存储期限6项、AgentStore不变量9项、原子计划3项、等待期限7项。该证据证明消除了两处不必要写锁及相关兼容性，不证明全部30秒等待根因或G12完整通过；旧包34项失败继续保留。未实施可能改变取消投影顺序的非阻塞宿主回调方案，未调用模型或运行CI，整体目标保持未完成。


2026-11-05 计划只读修订后原序列复验：当前安装包151文件直接一致。带有界内存调用耗时采集的原34项134.742秒全部通过、0失败／错误／跳过、正常退出；trace-result.json、trace-run.log、timing-events.json及timing-summary.json位于 `/tmp/sdk-plan-read-final-20261105/`。29,482事件未达到100,000上限；单次AgentStore事务最大0.1444秒，app pump最大1.1178秒，统计总和包含嵌套／并发时间，不能当作串行耗时或证明历史根因。随后同包关闭采集、原序列与期限不变，139.246秒33通过／1失败／0错误／0跳过、正常退出；original-matrix-result.json和original-matrix.log。本次唯一失败仍为原2秒期限未到指定abort边界：adapter入口余0.257107秒，等待app锁0.120123秒、prepare共0.241392秒；不得以采集版本全通过替代正常版本。两次均未出现30秒等待超时，但不能推断偶发超时根因已消除。G12完整验收保持未通过，原模型业务／返工／发送后unknown最终制品证据亦未补齐。无模型调用，未运行CI。


2026-11-05 G14当前计划只读安装包真实窗口B：`/tmp/sdk-g14-plan-read-native-b-20261105/report.json`，Linux x64／Python3.12.3，安装模块位于 `/tmp/sdk-plan-read-final-20261105/env/`。真实OpenCode使用已授权本地反代；故障进程在根意图已持久化、SDK Run／命令／效果／原生操作均不存在时exit41。独立恢复进程重投同request ID，8项检查通过：同根invocation及Run、原deadline不变、只有1个agent call和1个准确效果、COMMIT_PRODUCER原始产物，以及匹配lease／attempt／fence的原生树清理回执。恢复时Run succeeded，宿主存活；验证器随后SIGTERM退出宿主（-15），没有证明宿主完整优雅关闭，remaining_native_cleanup仍标unknown，不能扩张为G16通过。窗口D未运行。验证器新增可选--model-turns（默认32保持原行为）并向恢复子进程透传，本次原工作预算120秒、模型轮次上限4、观察180秒，重启不重置；非法0在启动前exit2，日志 `/tmp/sdk-g14-invalid-limit-20261105.log`。本证据不是token计量上界验收，不补G15缺失宿主合同。G14整体仍未完成，历史失败不删除。


2026-11-05 G14窗口D验证器修正：旧钩子包装AgentStore.node，但当前_stage_ready_node以_db参与消费事务；node返回时后继意图尚未提交，旧脚本在另一连接读取后继行，不能证明后提交窗口。发现后核对精确driver命令及/proc身份并SIGINT，原driver正常进入finally清理后exit130；`/tmp/sdk-g14-plan-read-native-d-20261105/interrupted-driver.json`及interrupted-verifier.json保留，不作为接受证据，不删除该状态目录。修正为拦截app._submit，独立读取后继意图后再exit42；独立审查确认现有_submit调用位于暂存／消费事务提交之后，原生产者、绑定、效果、清理和恢复断言保持。仅可证明后继意图提交后、SDK提交前窗口，不能仅凭通用_submit钩子宣称准确消费回执或调用来源已获验证。SDK产品未修改。修正后的真实运行在独立证据目录 `/tmp/sdk-g14-plan-read-native-d-fixed-20261105/`，最终结果另行记录。


2026-11-05 G14窗口D最终结果及预算定位：`/tmp/sdk-g14-plan-read-native-d-fixed-20261105/report.json` 正常退出1，原11项检查9通过、2失败（run_succeeded、successor_result），不得作为G14通过。exit42准确命中后继意图提交后、SDK提交前窗口；恢复身份、绑定、原期限、生产者未重跑及准确原生清理成立，但消费者 runtime_rejected/OpenCodeError、无产物。对该现场budget.sqlite3只读按owner聚合，agents/model_turns已settled 4轮，全部属于producer，consumer没有model_turns reservation；本次最初设定总上限4被生产者耗尽。SDK代理charge_turn失败会返回429，因此原生Too Many Requests不能直接归因外部提供方限流。失败Run预算不修改、不续期、不覆盖证据。消费者在agent_nodes而非根请求agent_requests，最初只查根表导致的“记录丢失”判断已撤回，无丢失证据。

验证器后续修订：恢复快照通过公开run.usage保存各预算spent/reserved/unknown/allowance/deadline，新增原模型额度和原期限保持检查；每个invocation仅输出结构化failure code/type，不输出提供方错误正文。语法编译及离线失败标识提取检查通过，未调用模型；该修订尚无新的真实运行证据，不追溯修改旧报告。下次D应在新Run启动前设置足以覆盖双Agent的有界轮次，保留每次原预算，不通过扩大旧Run预算换取通过。当前不启动重复回归或真实模型请求。


2026-11-05 G12原期限用例因果补强：独立只读审查确认2秒预算从提交开始，启动及原生登记可能先耗尽，不能据boundary_reached=false认定abort后重试缺陷。保留原2秒预算和30秒等待，未修改产品或使用虚拟时钟。测试新增准确not_launched持久回执身份、请求／存储／SDK命令原deadline一致，以及abort_native_prelaunch实际返回时刻早于原deadline的断言；确认回执后才等待原期限耗尽。第一轮仅回执补强4.140秒通过，但回执读取完成时已晚于期限1.005秒，故不足以证明abort早于期限。进一步记录准确abort返回时刻并增加时序断言后，当前安装包单项3.645秒通过，0失败／错误／跳过，正常退出；回执读取完成仍余0.094716秒，原期限不变，adapter只调用一次，effect indeterminate、Kernel recovery_required。日志 `/tmp/sdk-g12-abort-proof-20261105/timing-run.log`，用例副本同目录tests。该单项证明本次准确场景成立，不消除正常34项序列失败或历史偶发等待，G12仍failed。无真实模型调用、未运行CI。


2026-11-05 G14真实D窗口当前安装包通过：`/tmp/sdk-g14-d-budget8-20261105/report.json`，driver正常退出0，12项全部成立。独立新Run初始seconds=120、model_turns=8、observer_timeout=180；保留此前4轮耗尽失败现场，未修改旧Run预算。真实OpenCode生产者提交COMMIT_PRODUCER后，在后继意图已持久化、SDK提交前exit42；恢复同根请求／Run／后继身份及原绑定、deadline，消费者正确发布同一产物，生产者没有重跑，准确效果及原生树清理检查成立。最终agent_calls spent=2、model_turns spent=8、reserved=0、unknown_count=0，allowance与deadline保持。宿主在检查时存活，但验证器最终SIGTERM关闭，不能作为完整优雅停止或G16验收。G14仍partial，其余当前包窗口及完整故障矩阵尚缺；不宣称任意外部副作用恰好一次。

同轮双语Wiki修订：将控制通道句柄获取不明时的保守拒绝与真正未闭合的G12区分，保留当前正常矩阵33/34及偶发等待未证消除的说明。默认JSON注册表与当前安装包逐项相等，证据 `/tmp/sdk-g14-wiki-defaults-20261105.json`。这是默认值一致性检查，不是全篇文档／平台／真实功能验收。


2026-11-05 当前plan-read安装包G01复验：原configuration_case通过，包含YAML/Python配置等价、四类非法配置拒绝、validate/config show实际CLI、双语默认注册表与安装包相等；`/tmp/sdk-current-g01-20261105/report.json`。不调用模型。更新后的Wiki本地导出25页至 `/tmp/sdk-current-wiki-preview-20261105/`，导出器校验本地文件链接；ref release/0.8.0仅作本地预览，不代表远程已发布，不替代最终候选完整文档／示例检查。


2026-11-05 G14当前plan-read安装包真实发送后窗口C通过：`/tmp/sdk-g14-current-c-20261105/report.json`，driver正常退出0，16项检查全部成立，Linux x64／Python3.12.3／OpenCode1.18.32。原工作预算120秒、模型轮次上限12、观察上限240秒。真实代理完成归属明确的请求写出后故障；重启前后准确execution／lease／attempt／fence／effect与原deadline保持，原生进程树清理有准确回执。原期限前稳定重放不改变状态／消耗／准入、不新增原请求或同键排队项发送；期限后原请求保持recovery_required及不明效果、会话隔离，同键排队项不执行（允许按其原期限过期），不同键新Run成功。发送计数原请求恰好1、排队项0，无未归属发送。该计数证明本地请求写出及未重发，不证明远程提供方业务完成或任意外部副作用恰好一次。当前B／C／D已有分别范围证据，A窗口及完整故障矩阵尚缺，G14保持partial；G12／G15／G16等完整要求未据此宣称通过。


2026-11-05 G14当前plan-read安装包真实A窗口通过：`/tmp/sdk-g14-current-a-20261105/report.json`，正常退出0，8项检查成立。原预算90秒、模型轮次12、观察150秒。准确故障点是SDK admission回执已经存在、Agent尚未mark_submitted；为固定窗口暂时阻止worker启动，不代表自然并发或SDK回执尚不存在的更早窗口。恢复同invocation／Run／execution与原deadline，1次agent call、1个匹配原生操作、实际计量发送及成功结果。当前151产品文件与已安装包逐字节一致，无差异，`/tmp/sdk-current-g14-package-parity-20261105.json`。

独立审查指出D旧报告只记录后继意图与绑定，没有记录具体消费回执，不能宣称精确的消费后／确认前崩溃窗口。因此G14仍partial。验证器已补只读inspect_receipt：故障前要求准确producer事件／consumer scope已consumed、未acknowledged，保存outcome与generation；恢复后要求同outcome、更新generation并acknowledged，仍核对后继身份／绑定与未重复生产者。编译通过，尚未重新真实运行，旧D通过仅保留其原有范围。不以验收器源码改进代替真实消费回执证据。


2026-11-05 G14消费回执窗口及范围收口：`/tmp/sdk-g14-d-receipt-20261105/report.json` 正常退出0，13项通过。准确producer终态事件及consumer Run/role scope，故障前consumed=true、acknowledged=false、generation=1；重启后同event/scope/outcome，generation=2且acknowledged=true，后继身份及绑定不变、消费者正确产出、生产者未重跑、原预算不变。A保留报告的清理回执离线逐字段补核通过，`/tmp/sdk-g14-current-a-20261105/receipt-supplement.json`；未增加模型请求。独立审查确认当前安装包四个指定崩溃窗口的Linux x64／Python3.12范围无具体剩余阻塞，G14更新为该范围passed；G16和G18平台覆盖单独保留。历史失败与证据均不删除。

同轮当前安装包文档／README检查失败：`/tmp/sdk-current-docs-check-20261105.log`。README.md第二个进程隔离示例已确认超时handler和子进程消失，但随后echo执行next失败，handler_error／BudgetClockUnknownError／budget_clock_sample_unresolved:sampling。原始保留目录 `/tmp/sdk-docs-README.md-example-2-nag2tq7m/`，含checker.json、readme-evidence.json、原示例与SQLite现场；未更改原2秒预算、未重跑。独立审查确认入口包装异常可能来源于_enter_handler／on_entered，不是echo业务逻辑；完成时间未知走另一条记录路径。只读现场kernel_budget_samples当前为空，不能据此断定前一timeout遗留或并发采样根因。下一步须在异常发生时保留准确入口栈及采样归属。该失败阻碍G17旧API／G18完整文档验收，不能用G01或Wiki导出通过代替，已知缺陷解决前不运行CI。


2026-11-05 README入口诊断补充：tests/_readme_evidence.py新增仅异常时的HandlerContext._enter_handler观察，记录原BudgetClockUnknownError栈、execution／attempt／fence和本地pending token／是否已采样；原异常原样抛出，不重试、不清除标记、不改变期限。check_docs生成脚本在父及spawn子进程均安装入口诊断，父级既有现场保留逻辑不变。编译通过；离线异常分支验证同一异常对象、调用一次、准确pending身份与栈留存，`/tmp/sdk-readme-entry-diagnostic-branch-20261105/`。当前安装包原README第二示例仅执行一次，保留2秒原期限，正常退出0、两条预期输出均成立；`/tmp/sdk-readme-entry-diagnostic-20261105/run.log`。本轮未再现时钟采样错误，因此没有新的错误现场，不能据此宣称修复或整套README通过；原失败继续作为G17／G18未闭合项。入口观察只覆盖_enter_handler，不声称覆盖单独on_entered回调的全部异常来源。无模型请求、未修改产品代码、未运行CI。


2026-11-05 入口预采样竞争修订及当前安装包：真实Kernel同执行采样所有者持有未发布事实时，_sample_budget每次原100毫秒准入耗尽后返回sampling，_capture_entry_budget原先立即失败，未利用剩余原启动窗口；确定性失败栈 `/tmp/sdk-entry-sampling-before-confirmed-20261105.log`。修订仅在入口尚未建立本地pending／retained且未发生发布代次变化、原无cause的准确sampling拒绝时，等待并重读；共用原启动／工作截止时间，每轮检查权限。不清除或接管其他标记，不重采样本地未取得事实或确认不明的样本，legacy保持立即拒绝。原所有者确认后继续，标记未决耗尽原启动期限、own_uncaptured及legacy负例均不放行。

源码24项相关测试通过13.329秒。独立审查修正测试事件先后及线程未退出时的目录保留问题，最终夹具源码2项1.060秒通过。新wheel `/tmp/sdk-entry-sampling-final-20261105/wheel/dispatcher_sdk-0.8.0.dev1-py3-none-any.whl`，独立venv、-I、151产品文件直接字节相等；24项13.742秒全部通过，无失败／错误／跳过、正常退出，`result.json`及run.log同目录。最终保留目录夹具安装包补跑2项1.021秒通过，final-fixture.log；其差异仅测试目录保留，不影响产品。当前安装包完整文档检查577链接、4个README示例全部通过、0跳过、正常退出，docs.log；双语Wiki补充入口等待边界，默认值无变化。

此修订确定修复了独立复现的预采样竞争；原README偶发异常尚无当时入口栈，不能宣称其根因已被证明或永不再现。历史README失败保留，当前原示例已通过。G17完整旧API／监督／资源准入及G18平台矩阵仍未完成；G14四窗口证据明确属于前一plan-read包，新包入口修订后的真实调用／故障路径影响复验仍需完成，不能用旧包报告冒充新包最终验收。无模型请求、未运行CI、未发布。


2026-11-05 当前entry-sampling安装包原34项完整技术序列失败：180.700秒，32通过／1失败／1错误／0跳过，runner退出1；original-matrix-result.json及original-matrix.log位于 `/tmp/sdk-entry-sampling-final-20261105/`。151产品文件直接字节一致，无耗时采集插桩。原期限adapter入口仅余0.153595秒，app锁等待0.413102秒，未触达目标中止边界；关闭前证据 `/tmp/sdk-prelaunch-deadline-failure-rwi0go3w/` 和 `/tmp/sdk-prelaunch-deadline-threads-mclhv1ec/`。新增错误为test_supervised_retry_rejects_unconfirmed_observer_join等待原30秒后Agent wait lock admission timed out，本用例之前没有关闭前栈采集，不能据此断定持锁者或根因。入口采样修订不宣称修复这两个问题；G12保持failed，未再次整组重跑。

为避免失败换用例后再次缺现场，技术矩阵setUp已统一观察AgentRun.wait的未预期TimeoutError，在fixture关闭前保存全部线程栈、准确Run／invocation／测试身份和时刻，原异常重抛，不改调用期限、不额外重试或观察业务状态。编译通过，新增通用异常分支尚未实跑，不能声称已捕获上述失败现场。

原生验证器接口修复：host_competition、permissions、cancel、parent_cancel、mailbox、queue_expiry六个脚本的wait_io观察器仍是旧签名，当前代理必传connection关键字会产生TypeError；现显式接受并原样向原wait_io转发connection，保留既有门闩和归属观察。直接抽取并执行六个实际定义的离线检查确认同一connection对象、仅一次I/O调用和返回值保持，`/tmp/sdk-native-observer-interface-20261105.json`，全部编译通过，无网络或模型；不是上述六个真实场景的接受证据。修订仅验证器，未重建产品包，原生G15／G16仍待真实复验。


2026-11-05 空恢复集合写锁竞争修复：最新entry-sampling安装包诊断34项为33通过／1失败／0错误／0跳过，148.015秒，diagnostic-matrix-result.json及diagnostic-matrix.log同前述包目录。observer join等待错误本轮未出现，不认定已修复；原期限用例仍未触达abort边界，adapter入口仅余0.050534秒，app锁等待0.320851秒。关闭前线程栈确认pump持app锁等待resources锁，清理线程持resources及workers锁进行资源账本数据库操作；没有证明锁反转或死锁。

另已确定ResourceOwnershipLedger.reconcile在_restored为空时仍每次开启写事务，但其后逐行逻辑只能处理_restored成员，因此不可能产生有效工作。新增真实BEGIN IMMEDIATE竞争用例，修复前原0.1秒caller期限耗尽，修复后在初始化检查之后、同一ledger锁内直接返回空列表；未修改非空恢复、身份核验、持久化释放或容量释放顺序。源码4项通过0.728秒至0.765秒量级（准确日志以 /tmp/sdk-empty-resource-reconcile-20261105.log 为准），独立只读审查无具体阻塞。该修订尚未构建新安装包，不作为G12通过证据，不宣称解决全部资源锁等待。没有新模型调用或CI。


2026-11-05 pump与资源退役竞争修订：新增应用内resource retirement RLock。退役在资源注册表及workers锁之前取得它，保持原有清理证据、持久化及容量释放顺序；pump先取得app锁，再非阻塞尝试retirement锁，竞争时立即返回False，整轮维护延至后续pump，不在app锁内等待另一线程退役。取得后覆盖整个原pump，finally释放。独立审查发现并已修正关闭快速拒绝／锁内二次检查回退；保留关闭已开始时不再进入维护的原行为。

新增真实AgentApp／资源账本释放事件门闩验证：退役I/O门闩未释放时pump及时返回、不投影控制，准确本地／持久化／容量占用仍保留；释放后退役一次、容量释放、下一pump恢复控制投影；BaseException后其他线程可取得gate。2项通过1.947秒。相关关闭、资源屏障、worker归属20项在支持本地套接字环境下通过5.522秒，`/tmp/sdk-pump-retirement-related-fixed-20261105.log`。首次20项保留失败日志`/tmp/sdk-pump-retirement-related-20261105.log`：关闭二次检查回退及受限环境socket PermissionError；不冒充通过。该机制只解决已观察到的pump等待另一线程退役方向，不宣称全部app／resources等待消失，也不证明真实控制取消／恢复完整验收通过。新候选包及原34项影响验证随后进行；G12仍failed，G14/G15/G16/G17/G18等最终包要求不由本局部检查替代。


2026-11-05 retirement-gate新安装包原34项：`/tmp/sdk-retirement-gate-20261105/original-matrix-result.json`及original-matrix.log，151产品文件直接字节一致，33通过／0失败／1错误／0跳过，167.899秒。原2秒deadline用例此次在原期限前完成准确abort（返回仍余0.074989秒），通过不重试断言；不是所有调度条件下的确定保证。新错误为run/orchestrator writer用例释放阻塞后的run.wait(20)到期，随后夹具跳过app.close并由TemporaryDirectory删除错误遮盖原异常。测试结束后准确Python进程仍12线程，`post-tests-process.json`保留；确认34项结果已终态后按完整cmdline核实PID356992并SIGTERM，session退出143，`post-tests-termination.json`，不得记正常退出或原生清理验收。

等待夹具改为失败保留目录，恢复等待异常时关闭前保存全线程栈，仍尝试app.close；独立审查进一步要求保留更早主体异常、记录其他清理错误并核实holder/waiter退出，已补。未改观察期限、工作预算、断言或自动重试。原失败用例与新gate检查的当前安装包定向验证进行中，不再次启动34项。G12仍failed，其他最终包范围不据此变更通过。


2026-11-05 retirement-gate安装包定向5项通过：`/tmp/sdk-retirement-gate-20261105/targeted-fixture.log`，5.079秒、正常退出0。包含此前run/orchestrator writer错误用例、新pump门闩两项、关闭竞争及空恢复集合竞争；使用首次修订的保留夹具，不宣称34项原错误已消除。后续夹具补强通过编译及独立审查；真实AgentApp注入原run.wait(20)异常，确认同一异常对象传播、关闭前线程栈保存、实际app._closed=True、失败目录保留，`/tmp/sdk-agent-wait-fixture-error-branch-20261105.json`及`/tmp/sdk-agent-wait-contention-z3k24vux/`。未增加观察期限、预算或业务重试，不调用模型。当前无本轮仍在执行的回归。G12整体验收仍未通过。


2026-11-05 高频观察接口写锁竞争修复：AgentStore.get、run_rows和NativeOwnershipLedger.for_invocation的纯SELECT事务改为_read_only=True，保持每次方法调用一个一致快照；原权限／服务／任务元数据辅助函数独立审查均为只读。写侧准入、撤销、原生authorize/abort/complete和条件更新未改。新增真实BEGIN IMMEDIATE持锁负载，三个方法修复前分别在原0.1秒caller期限耗尽，`/tmp/sdk-observation-reads-before-20261105.log`；修复后连同store及atomic planner共19项通过2.932秒，`/tmp/sdk-observation-reads-after-20261105.log`。本证据证明不必要写锁竞争已消除，不证明之前偶发等待根因全部消除。

权限／原生影响检查首次失败日志`/tmp/sdk-observation-reads-authority-20261105.log`保留：包方式运行permissions的裸helper导入失败，及旧prelaunch用例错误地期待套接字获取异常可证明无遗留端点。修正包限定导入；将确定未获取资源的abort及abort持久化失败检查移至工作目录准备错误，保留原异常／精确身份／Popen不调用断言；新增独立socket获取不明负例，要求不abort、不Popen、原异常保留、端点pending且cleanup_complete=false、账本保持prepared且complete拒绝。未放宽产品保守清理合同。独立审查认可故障点区分，修订后同范围24项通过40.184秒、退出0，`/tmp/sdk-observation-reads-authority-fixed-20261105.log`，含真实本地guard/host崩溃资源恢复；无真实模型调用、未运行CI。新独立安装包随后复验原34项顺序及受影响范围；当前G12仍未通过，不能以源码43项代替最终包完整验收。


2026-11-05 observation-reads安装包74项结果及后续修正：原34项顺序保留在前，追加40项；151产品文件直接字节一致。69通过／2失败／3错误／0跳过，268.576秒、退出1。当前等待夹具确已在两次恢复等待失败时保存关闭前栈并关闭应用，未再由rmtree遮盖；现场 `/tmp/sdk-agent-wait-contention-bqv95vw3/`、`/tmp/sdk-agent-wait-contention-zy4flnyj/`。技术原期限用例等待超时，原始 `/tmp/sdk-retry-matrix-wait-timeout-50zbjpcp/`、`/tmp/sdk-prelaunch-deadline-threads-k494_2d_/`。独立审查确认这些单次快照不足证明持锁时长、统一根因或死锁，不能据此继续猜测产品修复。

两项实际guard恢复失败为夹具子进程相对tests路径在/tmp隔离环境下无法导入。修订仅传入Path(__file__).resolve().parent及根目录两个参数，未改故障或清理断言；同安装包、相同/tmp隔离运行两项通过1.182秒、退出0，`/tmp/sdk-observation-reads-20261105/native-import-fixed.log`。不把这两项补验合并成74项全通过。安装包读取竞争用例、权限、原生prelaunch保守负例及退役门闩均通过，G12原34项仍31/34，整体验收未通过。下一诊断需在原等待期间保留多时刻栈与真实写锁rollback／close完成事件，区分遗留测试锁、单次慢I/O和多次竞争；不加观察时间或业务重试。当前无本轮活跃回归。

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

## 2026-11-06：当前包配置/能力及剩余旧API模块

同一child-entry-marker wheel安装环境：G01和G13验证器均passed，`/tmp/sdk-current-config-strict-20261106/acceptance.json`及G01.json/G13.json。G01包含YAML/Python等价、非法配置拒绝、默认值与双语Wiki及CLI有效配置；G13明确native_strict_backend_provided=false、real_strict_isolation_accepted=false，strict_backend_unavailable在请求准入前拒绝，runtime_launches=[]。不宣称真实原生隔离可用。

包外八个完整模块58项通过、0失败/错误/跳过，155.893秒：`/tmp/sdk-child-entry-marker-installed-20261106/legacy-contract-result.json`、legacy-contract.log。范围为application、v2_sqlite、child_call_concurrency、child_storage_contention、agents_application、agents_control_reopen、agent_file_backend_capability及agents_native_capabilities。两个实际生产者/消费者用例为本地合成适配器，不替代G04真实模型消费要求或全部G17。原112项中的两秒失败仍保留，不与58项合并成一次全通过。无外部模型调用/CI/发布。

## 2026-11-06：当前候选sdist构建与离线消费

从同一child-entry-marker冻结源副本构建 `/tmp/sdk-child-entry-marker-sdist-20261106/dist/dispatcher-sdk-0.8.0.dev1.tar.gz`。首次离线安装因受限主机用户pip缓存目录只读失败，install.log及原driver退出1保留；不是产品构建错误。随后同一sdist使用--no-cache-dir、--no-index、--no-deps、--no-build-isolation在独立system-site-packages venv离线安装成功，install-no-cache.log。包外验证G01/G13均passed，来源为该独立安装site-packages，`acceptance/acceptance.json`及verify.log；汇总result-no-cache.json明确保留首次失败。此为sdist安装/配置/能力合同证据，不把wheel的完整模块结果直接当作sdist完整回归，也不是各平台安装矩阵通过。

当前验收索引已置于本文开头，区分当前包证据和历史报告。没有修改产品代码或调用外部模型，没有CI/推送/发布；本轮进程已全部退出，G01–G18仍未全部验收。


## 2026-11-06：派发耗时诊断与启动扫描调度

同一冻结安装包的原两秒单项仅增加方法起止记录，未改期限/断言。`/tmp/sdk-prelaunch-current-timing-20261106.log`及json：3.599秒，1失败；adapter进入剩余0.1866秒，abort返回晚于原截止约0.0809秒，未满足post-abort正例。

进一步派发记录 `/tmp/sdk-dispatch-gap-timing-20261106.log`及json：31.991秒，1错误，Agent store caller deadline elapsed，adapter未进入；现场 `/tmp/sdk-prelaunch-deadline-failure-qvibubbz/evidence.json`、`/tmp/sdk-retry-matrix-wait-timeout-7k9uxwvz/facts.json`。准确执行仍未发布结果，pending settlement含handler_failure_unknown/BudgetClockUnknownError及late thread completion authority is unconfirmed。此前局部超时修复和四项通过不能证明所有等待挂起消除，本轮不覆盖该错误为通过。

耗时记录确认启动reap+sweep后立即再次reap+sweep（约0.0809秒）；控制流原因是周期next_sweep在启动前初始化，成功启动后仍已到期。源码现在用成功启动实际_last_sweep_at调度下一周期，保留立即队列pump、首次worker派发、各通道退避及所有权限/预算检查。此修订只消除已证明的重复维护，不能证明两秒用例或挂起修复。新增实际startup控制流调度用例检查立即投递及下一周期恢复；原慢周期与退避检查保持不变，三项通过0.020秒（实际详情见`/tmp/sdk-startup-sweep-scheduling-final-20261106.log`）。最初两次调度测试调整失败日志保留，最终使用实际成功扫描时间作为依据，未放宽原慢周期断言。新修订尚未安装包验收，完整目标保持未完成。无外部模型调用、CI、发布。

独立只读审查未发现该调度修订的阻断问题；指出调度夹具不证明真实领取或两秒性能。随后原test_startup_recovery_reaps_expired_execution_and_keeps_pumping源码用例通过3.137秒，`/tmp/sdk-startup-sweep-real-recovery-20261106.log`：真实SQLite过期租约恢复、原队列继续执行和关闭，原3秒等待/停止不变。不替代安装包验证或两秒失败修复。


## 2026-11-06：取消检查的截止拒绝与未解决的无效果迟到结算

核对最新等待超时现场：准确执行running、result=null、sample_owners=[]，未进入adapter；迟到结算包含handler_failure_unknown及BudgetClockUnknownError。现有恢复明确不把late_thread_fact提升为结果权限。无未完成effect时，monitor效果停放函数返回None；不能仅凭这份晚到记录补写recovery_required或timeout。现场未记录全部monitor分支，因此该路径与本次挂起的准确关联仍待证明。

独立代码审查发现cancelled在原宿主截止已到期时仍可能读取存储/验证租约/启动预算采样；现在在读取前及租约验证后检查不可变宿主截止，仅返回拒绝，绝不将墙钟观察用作Kernel结果、预算连续性或清理权限。未过期路径保留全部权限和预算检查，未知错误仍传播。完整startup_cancellation模块6项通过，`/tmp/sdk-cancel-expiry-refusal-20261106.log`；包括到期不读、租约验证期间到期不再采样，以及未过期的租约/预算错误传播。独立审查未发现调用方仅凭此拒绝提交结果或确认清理。该修订不能阻止在采样期间到期，不能证明原两秒用例或等待挂起解决。

两处修订的最新安装包影响验证10项全部通过，详见文首。未调用外部模型，未运行CI/完整回归或发布；不将该局部结果升级为任何尚缺完整证据的验收ID通过。


## 2026-11-06：预算初始化原子合批及当前安装包未通过记录

Agent提交原先对4–6个scope逐个create并inspect，现在由私有_ensure_scopes在单个BEGIN IMMEDIATE事务中校验全部不可变条款、建立缺失scope并执行原有预算历史/归档完整性检查。公开create和inspect行为不变，既有消费、unknown预留、observed_at及期限不重置。独立审查首版发现省略inspect允许损坏model_turns/tokens历史下先启动native的阻塞，已在合批事务内补齐；独立复核确认该阻塞解决。新增真实AgentApp路径注入损坏model_turns读取，原BudgetError在orchestrator.create_run/runtime.command前抛出，1.385秒通过；无直接SDK表写入。

首版源码52项通过28.297秒（含原两秒单项，abort当次提前0.565秒）；此结果发生于完整性审查修复前，不是最终候选验收。补齐检查后源码52项中5个令牌代理用例因运行环境不允许本地socket返回PermissionError，日志`/tmp/sdk-budget-batch-fixed-source-20261106.log`保留，不能计为通过。

最终冻结/独立安装候选 `/tmp/sdk-budget-batch-candidate-20261106`，在已授权本地端口环境运行五个完整预算相关模块、完整技术重试模块、完整startup_cancellation及四个host调度/真实恢复用例；79项77通过、1断言失败、1错误、0跳过，unittest159.218秒，driver159.425秒。五个预算相关模块全部通过，前述5个本地代理测试在该环境通过。完整technical_retries14/16：test_original_deadline_expiry_after_abort_blocks_retry的adapter_calls=0/boundary_reached=false，现场`/tmp/sdk-prelaunch-deadline-failure-92aj_90i/evidence.json`，kernel未决迟到结算；另test_deadline_expiry_during_runtime_setup_blocks_adapter_entry发生Agent wait lock admission timed out，准确running/result=null、sample_owners=[]，现场`/tmp/sdk-retry-matrix-wait-timeout-2wtjjdv3/facts.json`及threads.txt。监督重试用例均通过，不能把准备到期错误误报为监督重试错误，也不能把无adapter调用当作post-abort正例。此前单项通过不覆盖当前完整模块失败。事务次数减少已实现，原间歇期限/等待问题未证明修复。无外部模型调用、CI或发布。


## sampling-cause G16最低合同通过，历史失败仍开放（2026-11-06）

当前组合报告`/tmp/sdk-sampling-cause-G16-cleanup-observed-20261106/G16-combined-minimum.json`映射competition、permissions及cleanup-observed三个真实报告。主审和独立终审通过限定G16最低合同；先前cleanup-unknown报告failed与代理清理根因缺失均保留。详细身份/预算/清理、恢复宿主exit1及成本边界见[当前验收总表](SDK_0_8_0_CURRENT_ACCEPTANCE.md)。完整Goal尚未完成。

## entry-publication 最新候选增量索引（2026-11-06）

候选 `/tmp/sdk-entry-publication-candidate-20261106`；151产品文件冻结及安装来源见parity.json。安装包33项定向回归result.json通过；66项准确旧API范围remaining-66-diagnostic-result.json通过，首次remaining-66-result.json的失败未解释、保持开放。不得合并称完整旧API回归通过。

真实监督 `/tmp/sdk-entry-publication-G17-stable-20261106/report.json` stable通过独立终审：父/子/controller成功、两个效果committed、原租约/预算/准确native清理回执一致。仅G17稳定切片；G01/G13无模型结果见 `/tmp/sdk-entry-publication-G01-G13-20261106/acceptance.json`，G13仍仅能力合同。

G06歧义历史负例补充评估：执行 `python3 /tmp/sdk-entry-publication-candidate-20261106/verify-G06-retained-ambiguity.py`，输出G06-ambiguity-retained-supplement.json。证明真实root模型工具创建同范围多候选后consumer拒绝，准确清理及原预算通过；child模型返回未证实、原failed保留、不是当前wheel执行。原始case及独立审查边界见当前总表。当前wheel完整多轮图 `/tmp/sdk-entry-publication-G05-G06-native-20261106` 尚在运行，整项G06不改判。

## owned-decision 候选安装及交付切片（2026-11-07）

最新冻结 `/tmp/sdk-owned-decision-candidate-20261107`：parity.json记录151产品文件一致，相对上一候选只变更_sqlite_base.py/runtime.py；result.json与manifest.json为隔离安装包78项定向测试全部通过、120.711秒、0skip。sdist-result.json记录同产品源码包的离线安装与wheel产品/安装元数据一致，sdist-env继承宿主依赖。

文档入口docs-check.log仍failed：中文第1例原10秒wait/30秒外层超时，原现场 `/tmp/sdk-docs-README.zh-CN.md-example-1-x4geldmb` 保留。增加诊断的单例 `/tmp/sdk-owned-decision-readme-diagnostic-20261107` 3.977秒通过，不解释首发失败。582链接单独检查通过，25页Wiki本地导出完成；不是README四例或完整G18通过。原生G06尚无新包结果，完整目标保持开放。
