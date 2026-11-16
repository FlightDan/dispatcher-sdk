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

## 2026-11-15 G14 回执前崩溃窗口通过，G17 旧入口补验

同一安装包仅运行 G14 窗口 A。实际故障进程在 SDK admission 回执已持久化、调用方尚未收到返回时退出。真实宿主重开后，同 ID 重放沿用同一 Run、execution 及原 deadline，只执行一次原生操作，准确清理及一次 Agent 扣费成立。9 项通过，外层监督退出 0、清理确认、零兜底信号。见 `/tmp/sdk-080-g04.UAOzl4/G14-window-a/report.json`。原意图、已发送模型请求及消费结果窗口仍待当前证据。

G17 同包 Application 和 Kernel Runtime 两个旧 API 模块运行 94.28 秒，43 项全部通过，0 跳过。覆盖持久回执、原生进程取消与实际子树清理。见 `/tmp/sdk-080-g04.UAOzl4/G17-legacy-api-gap.json`。G14 和 G17 均为部分通过，当前完整通过仍为 13/18。

## 2026-11-15 G11 原生验收通过，Python 3.10 定向补验

只重跑 G11，保留原 240 秒工作预算、30 秒启动窗口和验证器原等待。原生场景 116.98 秒通过，旧执行保留原 prompt 与配置，新执行用新版本，分别核实真实知识读取、拒绝未授权写入、写入版本 2、冲突不覆盖和准确产物。安装包与原候选相同。入口跟踪中两次实际采样进入时还剩 29.920 和 29.869 秒启动时间，原工作预算仍约 239 秒。整轮包括业务执行中的采样在内共捕获 71 次锁拒绝，两次入口采样完成。原现场短时退出和遗留 running 未复现，原失败及离线受控复现继续保留为 G18 可靠性缺口。证据 `/tmp/sdk-080-g04.UAOzl4/G11-native-traced/G11.json`、`G11-native-admission-trace.json`，外层监督退出 0、清理确认、零兜底信号。当前 13/18。

Python 3.10.21 x86_64 独立安装同一 wheel 与 PyYAML 6.0.3，G01/G13 及规格、知识库、预算采样拒绝 22 项通过，零跳过。Docker 因本机缺少父快照未启动，保留错误，从缓存镜像导出并在本机直接运行其独立解释器及动态库。见候选内 `G18-python310/host-run.log` 与 `tests.json`。完整 Python 和原生平台矩阵仍开放。

## 2026-11-15 当前包 G17 CLI 与类型补验

用同一独立安装包实际执行 14 条 CLI 命令，验证生效配置、宿主及服务状态、暂停与恢复、正常关停和端点移除。所有命令退出 0，宿主退出 0，无兜底清理。包外类型消费检查的 6 个公共 API 文件全部通过，检查器指向同一安装环境，类型目标 Python 3.10。原始报告为 `/tmp/sdk-080-g04.UAOzl4/G17-current-cli/report.json` 与 `G17-current-types.log`。原生监督、资源准入和旧 API 其余回归仍待验收。

## 2026-11-15 G15 完整通过

当前安装包只补了额度耗尽和父子取消两个原生场景。额度耗尽 15 项通过（34.16 秒），真实父级工具调用耗尽原 Agent 调用额度，子级被拒绝，原期限、消费和重放保持。父子取消 12 项通过（72.88 秒），确认实际发送、原父子取消作用域、准确清理、发送后效果未知、异键服务继续及无后续重启。两次监督均退出 0，清理确认，零兜底信号。与当前同包的 G07–G10、G12 重试及 G15 队列到期合并，证据 `/tmp/sdk-080-g04.UAOzl4/G15-combined.json`。当前完整通过 G01–G10、G13、G15，共 12/18。

## 2026-11-15 G11 结算定位与 G12 技术重试补验

- G11 原执行未进入业务。后续把入口错误当作业务返回来校验时间，得到 `completion_clock_original_floor_unproven`，最终保留待处理 `late_thread_fact`。恢复入口将这种记录报告为 unknown，原记录没有提交终态的权限。同包通过真实控制锁复现了未进入 handler 且仍为 `running` 的结果。离线夹具将启动窗口设为 1.5 秒，触发了协调器的 `handler_thread_start_failure`，原现场的持锁者和实际等待时长仍待定位。原现场和夹具分别保留，G11 仍失败。
- G12 同包通过真实 OpenCode 技术重试 12 项。暂态 EMFILE 后在原身份和预算内成功，重试耗尽也留下准确的两次未启动回执，重放未执行。首次补充探针在受限沙箱内进入 `recovery_required`，验证器读取空结果报错，未进入 EINVAL 场景。沙箱独立探测确认禁止 IPv4 回环端口绑定，原探针留存的 `ToolCleanupUnknownError` 缺少底层异常，因果仍未确认。随后在支持本地回环的环境只补 EINVAL，11 项全部通过，原 150 秒期限保留；一次未启动、无进程或模型调用、同 ID 重放无执行，宿主关闭完成。默认并发短期限可靠性仍开放。

审计见 `/tmp/sdk-080-g04.UAOzl4/G11-G12-gap-audit.json`，真实重试与 EINVAL 证据分别见同候选的 `G12-retry/report.json` 和 `G12-nonretryable/report.json`。

G15 复用此次重试记账及 G07–G10 已有证据。只补队列到期场景，6 项通过。同键等待项在原 120 秒期限到期，未进入 Kernel 或原生执行；异键请求用真实 OpenCode 完成；重开宿主后原请求重放仍返回到期状态，两次宿主关闭均完成。证据 `/tmp/sdk-080-g04.UAOzl4/G15-queue-expiry/report.json`，监督退出 0、清理确认、零兜底信号。G15 仍缺实际工作预算耗尽与父子取消。当前完整通过仍为 11/18。

## 2026-11-15 G10 通过，G11 新配置执行在入口失败

同一安装包 G10/G11 总计 263.58 秒。G10 22 项全部通过，包括真实独立客户端退出、三个 SDK Run、同会话续接、真实宿主重启、队列恢复、跨 Run 精确取消和原预算核对。G11 外层等待 150 秒超时。只读复核定位到新版本请求已被 Kernel 领取，worker_dispatch 后在 HandlerContext._capture_entry_budget → _sample_budget → _control_lock 抛出 _ControlAdmissionTimeout，无 handler_entered、无原生操作。进程结束后数据库仍记录该 execution running。旧版本已进入 wrapper gate，失败退出时效果为 indeterminate，也无真实原生操作。外层监督确认进程树清理、无兜底信号。未重跑 G11，未放宽原窗口。

原始报告在 `/tmp/sdk-080-g04.UAOzl4/G10-G11-native/acceptance.json`，入口轨迹在同候选的 `G11-entry-failure-audit.json`。当前 G01–G10、G13 共 11/18。G11 与旧的已发布采样 ACK 竞态不同，本次应先核对入口控制锁拒绝及后续结算归类。G12/G15 复用当前 G04–G10 已有场景，另补真实技术重试、原预算耗尽、队列到期和父子取消缺口。无产品改动或 CI。

## 2026-11-15 G09 当前包会话与队列通过

真实 OpenCode 五场景（FIFO、reject、replace_pending、启动前 cancel_and_replace、未知效果 cancel_and_replace）均通过，用时 213.80 秒。两个并发发送者实际提交，同键续接、异键隔离、消息与输出准确对应；队列满和忙碌拒绝、替换、预算与截止保持均成立。未知效果保持隔离，后继在原三秒观察窗未调度。独立包路径和版本与当前验收索引一致，五个应用均关闭，监督退出 0、进程树清理确认、无兜底信号。原始证据 `/tmp/sdk-080-g04.UAOzl4/G09-native/report.json` 和同候选的 `mailbox-supervisor.log`。

## 2026-11-15 G07/G08 当前包真实验证通过

同一 Linux x86_64 / Python 3.12 独立 wheel，实际 OpenCode 两项共 311.33 秒。监督器和验证器退出 0，确认进程树清理、零兜底信号。原报告 `/tmp/sdk-080-g04.UAOzl4/G07-G08-native/acceptance.json`，同目录逐项证据保留。

- G07 实际 call-and-wait、send/wait、相同请求重放、权限拒绝、自等待环拒绝及 planner 实际消费双产物通过。3 次 Agent 调用、16 模型轮次；核对三个原生清理、committed effect、succeeded execution 和 released 资源见 `G07-terminal.json`。首次只读审计错用 G04 的四操作计数，修正为 G07 的三个，保留原审计脚本。
- G08 目标验证继续原会话，从 DRAFT_NATIVE 到 GOAL_NATIVE_FIXED；显式阻塞和验证器异常未进入成功或下游调度。主路径 1 次调用/6 模型轮次，两负例各 1 次调用/4 轮；四项原生操作清理身份正确。

当前 G01–G08、G13 共 9/18 通过。G09–G12、G14–G18 待关闭。本轮没有产品改动、CI、推送或发布。

## 2026-11-14 G05/G06 当前安装包原生验收通过

同一独立 wheel 本机实际执行一次共用 G05/G06 主链，545.83 秒，7 次主链调用/43 模型轮次，1 次隔离 Run 调用/5 轮。原 3600 秒、16 次调用、128 轮预算不变。两轮各两名 coder 的真实 adapter 执行区间重叠，group close、聚合、返工、跨 Run 拒绝及精确回执齐全。原逻辑 reviewer 通过 lineage 续接，使用新 invocation/session 实际消费 NEEDS_FIX 和两份修正产物。全部八项原生操作清理有效。正式 G05 passed。原联合验证器 exit 1 是 G06 单图缺少两项负例，外层 supervisor 确认树已退出、无兜底信号。

仅追加 G06 的 ambiguous_reference、group_required_output 两个实模型负例，实际 195.41 秒，共 4 次 Agent 调用、17 模型轮次。歧义作用域内消费者无 command/execution/effect/adapter 入口，必需产物缺失在组关闭后准确拒绝汇总消费者准入。两个 worker 与外层 supervisor 均确认退出和清理。补充结果与主链比较为同安装路径、版本和内容；最终合并 G06 passed。gate 辅助重叠只证明执行区间并发，历史约 64 秒领取延迟单独保留。

当前证据位于 `/tmp/sdk-080-g04.UAOzl4/current-candidate-acceptance.json`、`/tmp/sdk-080-g04.UAOzl4/G05-G06-native`、`/tmp/sdk-080-g04.UAOzl4/G06-combined.json` 和 `/tmp/sdk-080-g06-negatives-20261114.final-report.json`。当前 G01–G06、G13 通过。G07–G12、G14–G18 待关闭，下一步补真实 call/send 与 goal 续接。无产品代码改动、无 CI、无推送或发布。

## 2026-11-14 G18 完整 sdist 安装与双语文档检查

完整候选 sdist 为 `/tmp/sdk-080-g04.UAOzl4/full-sdist/dispatcher-sdk-0.8.0.dev1.tar.gz`，补入首版冻结副本缺少的双语 README、测试支撑模块及发布资料。源码包离线构建并安装至新的独立环境，151 个 SDK 文件与真 G04 所用的 wheel 安装内容一致。直接从解包文档运行检查，592 个本地链接、双语默认值注册表、4 个 README 示例通过，0 跳过。25 页 Wiki 已导出本地预览，引用本地 release/0.8.0，尚未发布。原始安装、内容核对、文档和导出记录见当前验收索引的 G18.partial_evidence。G18 仍缺原生平台矩阵、其余回归和最终审查。

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

## 2026-11-07 G17 当前安装包结算模块单轮26项通过

修正参与式连接记录后，仅运行一次完整 tests.test_runtime_settlement，原期限不变：26项全部通过，0失败/错误/跳过，43.577秒；准确当前安装包路径与逐项结果保存在 /tmp/sdk-admission-callback-candidate-20261107/G17-settlement-traced-current/result.json，原日志 tests.log 保留。与此前跨多轮拼接不同，本次确为单轮完整模块通过，但不推断原偶发初始化超时已修复；原失败现场保留。G17尚缺其他完整合同证据，仍未关闭，整体验收7/18不变。本轮无模型调用、无产品改动、无CI。

## 2026-11-07 G17 诊断盲区修复，原初始化失败仍未关闭

只读检查原 outcome_wait_expired.json：thread-error 的 settlement 数据库没有任何连接/SQL事件，只有 observation 数据库事件。代码确认 SettlementJournal 显式传入 _ParticipatingConnection，绕过 StorageEvidence.connect 的默认记录 factory。因此原报告不能用“未记录到 SQLite 错误”排除结算数据库操作；不能从该报告确定原始超时阶段。

仅修正 tests/_storage_evidence.py：为 settlement 的参与式连接增加记录子类，保留原维护锁与 close 行为。当前独立安装包实际创建 SettlementJournal 的无模型检查通过，记录28项 connect/execute/commit/close 事件、无异常；准确报告 /tmp/sdk-admission-callback-candidate-20261107/G17-init-diagnostic/trace-coverage-check.json。本轮未重跑业务回归、未调用模型、未改产品或期限；G17仍未关闭，当前7/18完整通过不变。

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

## 2026-11-07 G07失败定位边界补充

原现场只读整理G07-failure-triage.json（native-calls-goal-current-attempt），独立架构复核确认固定错误指向Kernel控制锁准入，但不能据此确认锁持有者、连续持锁273秒或死锁。Kernel claimed/started也不等于Agent handler已进入；必须保持该未知。下一判别证据为准确child代际的阶段及控制锁waiter/owner有界栈，不扩大期限、不盲目重复模型调用。产品未改，无新测试。

## 2026-11-07 G08通过；G07实际允许调用失败，保留原现场

原监督终态exit1/tree_reaped=true，分Gate：G08正式passed，经独立复审关闭；同session目标验证DRAFT_NATIVE→GOAL_NATIVE_FIXED、版本历史、blocked与validator错误不成功/不下发、回放不重复均成立，4个原生操作准确清理及资源released由goal-terminal-audit.json补证。G07 failed：self_wait_cycle和permission_denied真实拒绝已观察，允许call的child创建1794031747.228、Kernel started1749.845但无原生session；原父deadline1794032022.793到期后cancelled，原结果为Kernel control lock admission timed out。与此前领取前64秒延迟不同，此次是成功claim之后未进入模型的约273秒缺口，原因继续定位，不宣称修复。无自动重跑或预算延长。

准确场景、原监督与复审 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-calls-goal-current-attempt；通用cleanup初版因错误假定失败G07全部succeeded而assert退出，原文件保留为audit-terminal-original.py，拆为goal-only审计成功，不改变产品/原场景。当前通过G01–G06/G08/G13（8项）；G07失败，其余未完整关闭，整体Goal未完成。所有本轮原生任务已终态。

## 2026-11-07 G07/G08 当前包串行原生验收启动

独立预检确认现有真实调用/目标验证路径无直接SDK表修改或具体启动阻塞。当前env Python3.11，149产品Python文件与当前/冻结/wheel一致；所有scripts快照及隔离子解释器启动参数已核对。单元sdk080-native-calls-goal-current-20261107.service启动命令退出后active，监督PID725990；依次执行G07/G08，原各自预算与期限不变，无自动重启。预计合计6–15分钟，首次14:15:31北京时间检查，准确日程 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-calls-goal-current-attempt/scheduled-check.json。G07后续原生清理只读审计已准备但未对活跃现场执行。当前不提升任何Gate。

## 2026-11-07 G04 当前输入依赖与真实事件重投组合验收通过

当前安装包原生图+受控重投组合独立复审通过，G04现passed：双生产者输入未齐不启动consumer，真实消费文件快照，重复请求不重调度、不同内容冲突；一次ACK写入前受控失败后，宿主真实租约到期将同一event/scope由generation1重投至2且lease不同，输入绑定/消费结果/effect身份保持、consumer仅1次adapter入口，最终ACK绑定generation2。原4次调用/16模型轮次，4份准确原生清理回执、资源released；上下文closed、监督退出0且tree_reaped=true。

准确报告、combined-audit.json及independent-G04-review.md位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-redelivery-isolated-attempt。此为ACK前故障及宿主实际重投，不冒充进程崩溃、已提交ACK响应不明或G14通过；只读冲突探针不直接写SDK表。早期启动预检失败及历史间歇故障均保留，不因本次成功抹去。当前G01–G06及G13通过（7项），G07–G12/G14–G18仍未完整关闭，整体Goal未完成；本轮所有原生测试已终态，无自动重跑。

## 2026-11-07 G03当前原生文件验收通过

独立只读复审支持当前Linux x86_64/Python3.11工具权限范围G03关闭：实际允许写入、越界/符号链接拒绝、并发路径替换拒绝和外部内容不变、真实命名文件产物下游消费；4次准确原生清理与资源释放已验证。竞态样本0允许/500拒绝如实保留，允许路径由另一真实图操作证明；宿主必须控制根/祖先目录，不宣称strict隔离。证据及 independent-G03-review.md 位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-graph-current-attempt。当前通过G01/G02/G03/G05/G06/G13，G04补充重投仍按其预估时间等待，不关闭整体Goal。

## 2026-11-07 G03原生图终态与G04重投专项启动

G03正式passed、G04正向场景passed但事件重投not_run，整体退出1，原监督树tree_reaped=true。终态只读审计验证4次原生执行均succeeded、effect committed、原始准确cleaned回执与资源released；真实允许文件写入及下游FAST_NATIVE|SLOW_NATIVE消费、越界/符号链接拒绝成立。路径替换288次、500拒绝、0允许、外部不变且无错误；单独允许写入由真实图证明，不改写race计数。G03独立复审中，证据 native-graph-current-attempt/terminal-audit.json。

G04重投验证器冲突探针已改SDK只读事务并核对query_only=1，独立审查确认意外缺事件也不能插入。首次启动缺少-I在预检失败且无Agent/model入口，原native-redelivery-current-attempt保留且树清理确认；修正子解释器启动参数并离线检查后，native-redelivery-isolated-attempt正常active，宿主单元sdk080-native-redelivery-isolated-20261107.service，PID725029。原240秒预算不变，无自动重启；预计3–6分钟，首次4分钟后检查，精确时间见该目录scheduled-check.json。尚不关闭G04或整体Goal。

## 2026-11-07 G03/G04 当前候选共享原生图启动

只运行一次四Agent图，补当前包文件正反例、真实产物消费及输入到齐后启动证据，不重跑G05/G06。宿主单元sdk080-native-graph-current-20261107.service启动命令退出后已确认active，监督PID724070。原240秒请求预算及各等待期限不变，无自动重启；预计3–8分钟、首次5分钟后检查，准确时间见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-graph-current-attempt/scheduled-check.json。149产品Python文件当前/冻结/安装/wheel逐字节一致。G04事件重投另项，暂不关闭任何Gate。

## 2026-11-07 G06 当前原生正反例组合验收通过

按预定13:51检查原单元，监督进程已退出0，外层及各worker均cleanup_confirmed=true。两个补充场景05:39:25Z–05:44:22Z完成：同范围两个coder引发implicit引用ambiguous，consumer无命令/执行/effect/adapter入口；组成员缺必需产物required_output_missing，close后group_call返回agent_group_upstream_failure且consumer/effect未创建。每个实际进入操作均有完整provider响应和准确原生清理，原预算保持。与既有两轮真实adapter重叠、组关闭/汇总、任务与轮次隔离、未关闭组拒绝组合，独立复审确认G06可关闭；原始partial/失败报告保留，不改写。

合并审计及复审见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G06-combined-current。补充原证据 /tmp/sdk-g06-current-negatives-20261107-repaired-evidence 及同名.final-report.json。范围Linux x86_64/Python3.13；gate辅助adapter重叠不等于同时推理，历史约64秒领取延迟仍未根治，不关闭相关可靠性与平台缺口。当前通过G01/G02/G05/G06/G13，整体Goal仍未完成。无活跃G06测试、无自动重跑。

## 2026-11-07 G17 当前安装包实际CLI生命周期通过

原句柄50826退出0，当前独立Python3.11安装包执行validate、有效配置、实际serve子进程、服务stop/resume/status、触发器stop/resume/status及宿主stop全部成功；宿主PID723305退出0。准确报告 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G17-cli-current/report.json，冻结验证器 verify-agent-cli-current.py 保留。未调用模型、未运行CI；只关闭G17实际CLI子范围，监督/资源及完整旧API回归要求不因本条通过。G06仍按13:51首次检查。

## 2026-11-07 G02 复用当前候选真实执行证据通过

只读复核既有G05现场，确认新建独立Python3.13环境关闭system-site-packages并实际安装当前wheel；原报告记录实际安装导入路径。8份OpenCode1.18.32原会话数据库以mode=ro读取，session ID与SDK一致，均有完成的assistant模型响应、真实工具活动及SDK成功产物；原精确guard清理回执和实际授权Popen路径共同证明原生执行。149产品Python文件在当前工作树、冻结来源、安装目录和wheel逐字节一致。独立复审无G02具体缺口，G02现passed，范围仅Linux x86_64/Python3.13。未保留历史OS PID快照的限制明列，不宣称新增执行或完整平台矩阵。

审计脚本、result.json、independent-review.md见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G02-retained-native-audit。未新增模型、未运行测试或CI。当前完整通过G01/G02/G05/G13；其余Gate与整体Goal保持未完成。G06专项按原定13:51再检查。

## 2026-11-07 G06 两项专项负例启动

独立审查确认复用 ambiguous_reference 与 group_required_output，覆盖真实调用组创建后的歧义依赖拒绝、必需成员产物缺失后汇总拒绝；不是工具参数格式负例。修正验证器缺口描述，不改变合同或判定。首次启动副本遗漏两个观察器依赖，在进入Agent/模型前失败，原证据保留且监督器确认清理；补齐并离线加载验证后，新宿主单元 sdk080-g06-negatives-repaired-20261107.service 已确认 active，PID 722431。无自动重启，原每项预算不变，外层1400秒；预计5–23分钟，12分钟后首次检查，精确时间见 /tmp/sdk-g06-current-negatives-20261107-launch/schedule.json。新证据 /tmp/sdk-g06-current-negatives-20261107-repaired-evidence。尚无验收通过结论，G06与整体Goal保持未完成。

## 2026-11-07 G05 当前原生两轮返工链通过；G06仍缺两个原生负例

原监督单元终态退出1且tree_reaped=true；必须按Gate分开解释：正式acceptance.json中G05=passed/exit0，G06=not_run/exit1（两个负例未执行），并非本轮G05失败。全部8次真实调用、两轮coder实际adapter区间重叠、准确输入/产物/反馈绑定、显式返工、reviewer读取修正结果和每次原生清理回执均通过；独立只读审查支持当前Linux x86_64/Python3.13安装包G05关闭。reviewer延续是逻辑lineage，两轮原生session不同，不宣称同会话。

G06还缺真实工具路径歧义引用、调用组缺失输入负例，不提升passed；历史失败保留。此次560事件无丢失，第二轮一个coder从服务submit至claim仍等待63.965秒：已直接定位到run_once/claim重试，存在控制锁准入超时、lifecycle短窗口超时和预算采样超时，非工作线程未分配；尚未确认锁持有者或安全修复，不宣称延迟已解决。原始事件及错误代码位置见slow-child-evidence.json。

完整准确报告、terminal-stage-audit.json、slow-child-evidence.json、independent-G05-review.md位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-filtered-dispatch-attempt。当前索引G01/G05/G13通过；目标未完成、无活跃测试、不自动重跑。

## 2026-11-07 过滤后原生取证首次检查：第一组已实际结算

到约定时间检查同一systemd原单元仍active/running。只读Kernel证据显示第一组两个coder与reviewer均已succeeded，两个coder的leased至succeeded区间重叠；这不是实际adapter区间或最终G06通过。中间原始事件在 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-filtered-dispatch-attempt/first-check-evidence.json。完整两轮流程仍在运行，预计再10–20分钟，15分钟后检查，准确时间见scheduled-check.json。不重启、不提升Gate，不由本轮进展宣称历史间歇延迟已修复。

## 2026-11-07 过滤后原生调度取证已启动

单次原G05/G06路径取证由 sdk080-filtered-dispatch-20261107.service 持久监督，Restart=no；启动命令返回后确认active/running，监督器719169、测试719170。使用相同当前Python3.13安装包与原业务预算/断言，冻结验证脚本；只修正观察器空闲过滤，新增固定256事件尾部及最多64步/8帧原始异常位置读取，不加载源码、不记录消息/局部变量。独立审查发现的traceback.extract_tb异常遮蔽风险已改为guarded原始帧读取；10000空闲调用及目标返回/异常/还原探针通过。

本轮只为补足上次丢失的第二child阶段，尚无验收结果，不提升G05/G06。预计5–35分钟，首次检查北京时间13:15:53，准确记录 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-filtered-dispatch-attempt/scheduled-check.json。旧失败保留，不自动重试。

## 2026-11-07 双路取消检查对照未复现原生延迟

在独立85秒提交间隔夹具中增加planner .2秒、coder .05秒等待循环的实际context.cancelled调用（包含真实SDK租约/预算读取），其余该探针门控/预算保持。当前Python3.13安装包原句柄33796退出0，135.667秒、单Run受控业务断言通过；87调度事件无丢失。逐child提交至claim准确时长保留于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/dispatch-dual-cancel-probe/summary.json；完整fixture/驱动/原日志/result及状态保留。

检查周期是等待间隔，不是测得固定调用频率。该对照仍未复现原生105秒延迟，不能排除所有原生进程/模型交互；不再继续同类取消频率变体，不改产品、不提升G06，无模型/CI，目前无活跃测试。下一步须针对尚未观测到的原生子任务阶段收集直接证据，不能仅凭此类探针成功推导根因。

## 2026-11-07 长提交间隔无模型对照未复现原生延迟

独立诊断夹具仅单Run，将第二send延迟85秒、coder门控180秒、业务预算3600秒；明确不是原测试或原生验收。当前Python3.13安装包149份产品源码与冻结来源一致，原句柄71560退出0，135.572秒，两个coder并发/结果消费断言通过。过滤后的观察器85事件无丢失，4个子任务submit至成功claim分别为0.588、0.631、2.810、2.341秒。准确逐任务时间以 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/dispatch-long-admission-probe/summary.json 为准；原夹具、驱动、result.json、tests.log及完整状态目录保留。

仅说明85秒提交间隔本身不足以在该受控路径重现原生105秒领取延迟，不排除原生交互，不提升G06，不据此修改SDK。没有模型调用或CI，没有活跃测试。

## 2026-11-07 回执恢复与生命周期批量投递当前包补验通过

审查确认test_budget_sample_receipts与test_lifecycle_delivery_batch两模块命中的SQL为trace/断言，而非测试直接写表；实际使用的ChildBudgetAdmissionsTests.setUp走SDK提交/准入。当前独立Python3.11安装包完整执行两模块18项，9.579秒、0失败/错误/跳过，原句柄14470退出0。原驱动、冻结fixtures、result.json和tests.log在 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G17-receipt-lifecycle-current。包含真实spawn故障前后回执恢复与unknown保留、批量提交/回滚、丢ACK重放；不替代G14完整场景或G17全量回归。

独立源码复核认为claim成功采样后耗尽短准入窗口的重复采样现象存在，但已有旧无模型探针仅证明该机制，不能证明原生105秒延迟同因，也不能授权复用旧floor或放宽100ms限制。无产品修改、模型调用或CI；G05/G06保持当前原生failed，整体Goal未完成。

## 2026-11-07 修正门控后原生验证终态失败，第二coder排队105秒

按12:51约定检查：sdk080-native-entry-gate-20261107.service已failed，测试/监督退出1、tree_reaped=true，没有自动重试。当前独立Python3.13安装包149份产品Python文件与冻结来源和工作树逐字节一致。正式G05/G06原始报告均failed，当前候选机器索引如实更新为failed。

第一coder在第二同轮适配器未进入时门控超时；第二coder实际已提交，submitted=1794025722.8083825，leased=1794025827.9966016，相差105.188219秒。没有coder真实调用区间，不得提升并发或返工验收。部分记录捕获到claim的_ControlAdmissionTimeout/TimeoutError，但不能据此确定第二coder同因。

本轮观察器2048槽被大量非目标后台run_once/claim调用耗尽，丢2340事件，缺失第二coder调度阶段，不能从缺失推断未提交/未进入。此为取证设计缺陷。仅修正验收观察器：无目标且无child归属的空闲run/claim直接原样委托，非child的慢采样不记录；不修改SDK或期限。独立探针验证10000空闲调用不消耗槽，目标调用返回/异常与退出还原保持。无新模型重跑。

准确原报告、只读审计驱动及terminal-audit.json位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-entry-gate-attempt；过滤探针在 /tmp/sdk-g06-entry-gate-20261107/observer-filter-verify.py、observer-filter-result.json。原失败及丢失标记保留；整体Goal未完成。

## 2026-11-07 G17 当前测试库存更新，直接SQL夹具须先审查

等待原生验证期间仅静态解析当前tests：3459个显式声明test方法；旧3395数字不再代表当前库存。72个模块含疑似直接写kernel_/sdk_表的SQL字面量，不能未经审查直接启动全量测试，避免违反“不直接改SDK内部数据库”的执行约束。该筛查会包含断言字符串/旧库构造等误报，也不覆盖动态SQL、继承或生成测试，绝不等同于3459个运行用例或72个确认违规模块。

可复现审计与逐方法/逐SQL行清单：/tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G17-current-inventory/audit.py、inventory.json。未打开SDK数据库、未运行测试、不提升G17。下步全回归计划须以当前库存、运行时发现及夹具审查为依据，不能继续沿用旧静态计数或把未索引直接当作从未运行。原生G05/G06保持原计划，未提前刷新。

## 2026-11-07 修正入口门控后的单次原生 G05/G06 已启动

使用当前候选独立 Python3.13 安装包，冻结本轮验证脚本，真实 local/gpt-6-luna/OpenCode 场景已由 systemd 单元 sdk080-native-entry-gate-20261107.service 接管，Restart=no；启动命令返回后确认 active/running，监督器716681、测试716682。原业务预算/调用数/轮次及180秒门控不变，第二实际 coder 入口才释放第一，保留 dispatch-milestones。预计20–35分钟，准确下次检查时间见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-entry-gate-attempt/scheduled-check.json。当前仅证明启动及监督，不提升G05/G06；不自动重试，原失败保留。

## 2026-11-07 G06 验证器门控改为第二适配器实际进入

修正 scripts/verify_agent_control.py 的 native_groups_rework：同轮第二 coder 实际进入 ObservedAdapter.execute 时才释放第一 coder，移除第二 group-send 返回时的提前释放。原180秒 gate 上限、请求预算、真实适配器调用及调用区间重叠断言不变。该修改修复验收门控不足，不是 SDK 调度根因修复，不提升 G06。

无模型隔离验证直接提取当前脚本的实际 ObservedAdapter 类，确认第一执行停在适配器调用前、其他轮次不能放行、同轮第二执行能够放行，并通过 AST 确认提交观察器不再释放 gate。驱动与结果：/tmp/sdk-g06-entry-gate-20261107/verify.py、result.json。未运行真实 OpenCode、完整回归或 CI；历史约70秒领取延迟仍未解释。下一次原生验证现在可区分第二 handler 未进入与进入后真实调用无重叠；尚无原生结果。

## 2026-11-07 G13 当前安装包能力合同与拒绝路径通过

正式verify_agent_control.py --case G13 --layer integration在当前独立Python3.11安装包退出0：strict_backend_unavailable、request_admitted=false、runtime_launches=[]，tools仅授予sdk_file_tools_only；缺失/未知版本/伪造strict能力全部拒绝。另当前安装包5项能力与文件后端合同测试全部通过、0跳过，1.189秒，包括宿主和直接OpenCode适配器在Popen前拒绝。准确报告和原日志位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G13-current-contract 与G13-current-unit-evidence。

独立只读复审确认符合Goal §3.4显式允许的“能力合同/拒绝路径”范围，无具体G13缺口；G13机器索引现为passed。英文Wiki第98行与中文第112行均明确未提供原生strict后端、未验收真实强隔离。该结论不表示strict真实执行可用，不替代G03路径保证或G18平台验收。G01/G13通过，整体Goal未完成；本轮无模型、无CI、无产品修改。

## 2026-11-07 G17 结算模块完成Python3.10–3.13当前包验证

未重复已通过的Python3.11，原句柄25783串行补验3.10/3.12/3.13并退出0：每版26项全部通过，分别48.744/51.469/48.610秒，0失败/错误/跳过。结合3.11原26项46.431秒，当前包同一完整结算模块已覆盖四个既定Python版本。每版149产品Python文件与冻结来源逐字节一致，实际导入均来自对应独立env/site-packages，原测试断言及期限不变。

准确驱动、fixture、每版原日志和result.json保存于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G17-settlement-python-matrix；本条仅关闭结算模块四Python范围，不是完整G17或G18平台通过，不覆盖G06真实并发与R1/R2历史间歇缺项。无模型、无CI、无产品修改。

## 2026-11-07 G06领取前独立审查与验收状态格式修正

独立只读审查确认应用session/resource准入发生在Kernel handler启动后，不能直接解释第二coder未leased；原生验证门控仅证明第二send返回，不证明第二child已进入。另核实原失败安装包application.py明确child_capacity=64，不仅是当前源码。仍只有“原生负载下反复短暂领取前拒绝”的未证实假设；没有因果证据支持产品修改或重复模型调用。审查记录 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G06-preclaim-independent-review.md 保留。

修正同目录current-candidate-acceptance.json的非合同状态incomplete_current_candidate为not_run，解释为完整当前Gate证据尚未齐备，保留所有部分/历史证据、旧标签和修正前索引备份。G01维持passed，其余Gate不得因合成探针或局部回归提升；所有状态现属于Goal允许的passed/failed/blocked/not_run/not_applicable。此为报告格式修正，不是新增Gate通过。无测试、模型或CI；整体Goal保持未完成。

## 2026-11-07 G18 全新环境sdist安装与配置入口通过

刚生成的当前sdist已在新建独立Python3.11 venv（无system-site-packages继承）通过pip --no-index --no-deps --no-build-isolation --no-cache-dir实际安装；构建工具与声明的PyYAML先独立安装，build-tools-install.log与sdist-install.log保留。安装原句柄13009退出0。包外-I导入来自G18-sdist-current/install-env/lib/python3.11/site-packages，149产品Python文件与冻结sdist来源逐字节相同。

同一新环境完整configuration_case通过：YAML/Python、继承/列表/null/非法配置、42个Goal明文默认值、双语Wiki注册表及实际CLI有效配置检查。准确事实与驱动见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G18-sdist-current/install-evidence/result.json 和install-verify.py。由sdist安装生成wheel是pip正常构建路径，并非改用原候选wheel安装。本条关闭该sdist的本地安装/配置检查，不替代完整制品回归和Linux/Windows x64/ARM原生矩阵，G18与整体Goal保持未完成。无模型、无CI、无发布。

## 2026-11-07 G18 当前sdist构建与内容一致性通过

当前候选新增 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G18-sdist-current/dist/dispatcher-sdk-0.8.0.dev1.tar.gz，原构建句柄38214退出0、build.log保留。result.json证明sdist与既有当前wheel产品Python路径集合一致，149份产品Python文件与冻结source/wheel逐字节相同；138份文档/Wiki/示例/验证脚本与本次source快照逐字节相同，类型标记py.typed存在，双语README、pyproject及MANIFEST存在且内容一致。没有新增散列检查。

本条仅证明本地sdist构建及内容，尚不证明从sdist安装、完整制品回归或原生平台；不关闭G18或整体Goal。文档快照形成后的验收日志追加不冒充已进入该归档，最终交付仍须冻结一致版本。无模型、无CI、无发布。

## 2026-11-07 G18 当前安装包文档示例与Wiki本地交付检查通过

包外-I运行当前文档快照的check_docs.py：592条本地链接、4个中英文README示例全部通过、0跳过；指南及双语Wiki三份完整默认注册表与当前安装包一致。原句柄97896退出0，17.487秒；/tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G18-docs-complete-snapshot/result.json / stdout.log / stderr.log及完整快照保留。首次G18-docs-current快照遗漏隐藏.github目录，仅链接检查失败、未执行示例；该原报告保留，修正的是验证快照而非产品或项目链接。

同一快照导出25页Wiki到G18-wiki-local-preview，中英文Agent-Control页均存在，wiki-export.json保留。ref=release/0.8.0仅本地预览，未验证远程链接、未发布。新增证据已入当前候选G18索引；不关闭G18平台矩阵、制品完整回归或独立审查，也不关闭G06/G17。无模型调用、无CI、无推送。

## 2026-11-07 G17 当前安装包6个公共类型消费检查通过

在候选独立Python3.11环境安装既有mypy工具，包外-I执行项目CI既有6个消费者检查，目标Python3.10、--follow-imports=silent、--warn-unused-ignores，全部通过，exit0、Success: no issues found in 6 source files。覆盖orchestrator、capability、reliability、application、observability、agents消费者。运行目录仅有冻结消费者，无src目录；移除MYPYPATH/PYTHONPATH/PYTHONHOME，实际SDK导入断言为候选env/site-packages。准确命令、版本范围和时间在 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G17-type-consumers/result.json，原输出stdout.log/stderr.log、消费者及驱动保留，工具安装日志mypy-install.log保留。

该结果关闭当前包公共类型消费这一检查，不是完整G17、Python原生运行矩阵或G18通过。未触发CI、无模型调用、无产品修改。整体Goal保持未完成。

## 2026-11-07 G17 当前包完整结算模块26项通过

核对旧回归索引发现其存储超时待验项已改名且有历史通过，另GateCleanup单项在整体失败批次的原始log中明确ok，故旧“24项/剩1项”库存不能继续作为现状。当前方法与历史证据关联见 runtime-settlement-current-method-audit.json；历史包与当前产品有9个Python模块差异，不据此直接沿用通过。

首次当前包入口缺少__main__保护，spawn子进程重新执行suite；原log可见重复测试，原句柄3937退出1、19项中1失败，39.705秒，G17-runtime-settlement-current/result.json/tests.log保留。该次不能归因SDK进程启动缺陷。仅修正测试驱动入口保护后，原26项完整模块在当前独立Python3.11安装包全部通过，0失败/错误/跳过，46.431秒，原句柄82624退出0。G17-runtime-settlement-guarded/verify.py / result.json / tests.log及完整fixture保留；SDK、原测试断言及期限未改，无模型、无CI。

本条仅关闭当前包Python3.11结算模块范围，不关闭G17完整旧API/类型消费或G18平台矩阵，不覆盖原生G06失败及R1/R2历史间歇缺项。候选根目录 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107；机器索引已追加准确结果，整体Goal保持未完成。

## 2026-11-07 G06 取消检查竞争对照终态：未复现原生延迟

原句柄61637退出0，当前安装包Python3.13无模型单项通过107.369秒、无失败/错误/跳过。独立fixture在原30秒gate等待上限内配置每0.1秒调用context.cancelled，其他原期限不变；准确fixture、驱动、原日志及result.json保留在 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/dispatch-probe-py313-cancel-poll。1561事件无丢失，8子任务完整归属，worker至成功claim最大1.997秒，执行槽/结算槽拒绝0次。单独取消检查调用次数未计数，不宣称完整复刻原生负载；只说明此受控变体没有复现约70秒延迟，不能排除原生交互。summary.json/milestones.json保留。

不再追加同类合成重复运行，不据此改产品、放宽期限或提升G06。只读原生G05四条coder记录的native session_id均不同，但原现场agent_task_sessions为空，单凭终态会话ID不能证明领取前的会话/实例准入情况，不能把这一观察当根因排除。原生每child领取前阶段的历史记录仍缺失，新增观察器可覆盖下一次有依据的执行；未新增模型调用、未运行CI。G01保持passed，G06/G17/G18及整体Goal保持未完成。

## 2026-11-07 G06 Python3.13无模型调度对照终态

原句柄37271退出0；当前安装包Python3.13单项通过106.837秒，无失败/错误/跳过。dispatch-probe-py313/result.json / tests.log / milestones.json 保存1579事件且无丢失、8个child完整submit/worker/adopt/claim归属；submit至worker为0.075–0.298毫秒，worker至首次成功claim为0.455–2.978秒，最多6次claim尝试，未记录执行槽或结算槽拒绝。本轮未复现原生约70秒延迟；不能据此排除Python3.13与原生负载的交互，也不关闭G06。

源码发现原生OpenCode等待时反复context.cancelled，其中包含实际SDK预算读取；原合成coder仅Event.wait。下一次仅无模型受控对照在原30秒gate期限内加入每0.1秒取消检查，原请求120秒预算/100秒等待/20秒入口期限均保留；独立fixture不改产品，不作为原测试或原生验收。准确句柄61637及下次检查时间见 dispatch-probe-py313-cancel-poll/scheduled-check.json；不在预计时间前刷新、不重启、不新增模型调用。

## 2026-11-07 G01 当前安装包配置验收通过

G01 已关闭：最新 G01-goal-defaults/evidence/acceptance.json 对 Goal §3.2 明文默认值新增42个独立预期断言并全部通过，避免仅由实现与Wiki互相一致得出结论。结合保留的当前包14项公共配置测试、两种加载器的继承/列表/null/非法覆盖边界、CLI有效配置输出及双语Wiki完整注册表比较，独立只读复审确认G01配置范围无具体缺口。复审见 G01-goal-defaults/independent-review.md；候选根目录 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/current-candidate-acceptance.json 的G01现为passed。

该结论仅适用于当前候选的G01，不证明这些字段的全部运行时行为，也不关闭G18文档/平台交付。前面的历史“G01待复核”记录已被本条结果取代，原始证据不改写。release/0.8.0分支保持；无模型调用、无CI、无推送。G06真实并发、G17完整回归、G18平台与交付一致性继续开放，整体Goal未完成。

## 2026-11-07 G01 当前包配置证据补齐，仍待完整默认合同复核

当前 supervisor-parent-diagnostic 独立安装环境补装声明范围内 PyYAML 6.0.3。原受限网络安装失败已终止，授权网络安装成功。包外 -I 配置验证通过，精确报告 G01-configuration-expanded/evidence/acceptance.json：YAML/Python 等价、四类非法输入拒绝、双语 Wiki 完整 JSON 默认注册表相同、CLI validate 与 config show --effective 相同。149 产品 Python 文件在当前工作树、冻结来源与安装包之间逐字节一致。

独立复核发现原验收器缺少继承/列表/null 边界，现扩展 configuration_case 同时通过 YAML 和 Python 公共加载器验证嵌套映射继承、列表替换和清空、预算字段合并、允许的 null，以及两种加载器拒绝 null defaults/null tags/零预算。有效配置和各断言保留。另原配置与 null 合同两个模块在当前安装包执行14项全部通过、无跳过，G01-configuration-current/evidence/boundaries.json 与 boundaries.log 留档。未使用模型、未运行 CI，不改产品行为。

G01 尚未最终关闭：仍需完整 Goal 默认行为与字段注册表的独立逐项复核，以及扩展验收器复审；不能将 Wiki 与实现一致等同于它们都符合 Goal。G06真实并发、G17完整回归、G18原生平台及交付一致性继续开放，Goal 未完成。

## 2026-11-07 领取前容量拒绝取证补缺（不提升验收）

源码核对确认 application.py 显式 child_capacity=64，runtime.py 为子池建立独立信号量；不能用 InProcessRuntime 默认 child_capacity=1 解释原生现场。该源码配置不证明历史现场没有槽位耗尽。run_once 在 PendingSettlements.acquire 返回 None 或 _acquire_thread_slot 返回 False 时可不调用 claim_and_start，原调度观察器不能区分这些静默返回。

scripts/g06_dispatch_observer.py 新增仅拒绝时记录 thread_slot.denied / settlement_admission.denied，保留当前线程 child 归属，不读取内部数据库、不修改容量/期限或返回值。当前候选安装包的无模型隔离探针 /tmp/sdk-g06-preclaim-admission-probe-20261107.json 通过：原方法参数及拒绝返回保持、真实 PendingSettlements 容量拒绝与释放后重用保持、两个拒绝事件正确归属、退出后补丁准确还原。该探针不是完整 SDK 并发或 G06 验收；原生延迟根因仍未知，本轮无模型调用、无 CI。下一次因果取证可区分执行槽拒绝、结算槽拒绝和实际 claim 调用，不能从旧日志缺少这些事件推断旧现场无拒绝。

## 2026-11-07 R1/R2 当前安装包定向证据及宿主采样尾部修正

同一supervisor-parent-diagnostic包外独立Python3.11环境，原三级进程暂停换代续接单项通过25.689秒（nested-pause-probe/result.json/tests.log，句柄53355退出0）。原15秒driver.join及其他业务期限未改。既往同项已存在通过和失败，本轮不能解释旧线程超时、不宣称间歇缺陷已修复，不继续无新假设重复单例。

R1历史取证的宿主首1024采样记录可在子入口前耗尽。仅修正tests/_worker_entry_evidence.py：宿主额外用deque保留最后1024个采样事件，在observe_all清理时写sidecar；热路径不新增文件写入、不改SDK或期限。PID检查先于继承锁；清理顺序先还原supervisor补丁、写原宿主tail、还原flush/PID及方法。独立审查未发现阻塞；异常退出或写入失败仍可能丢tail。独立惰性采样函数探针 /tmp/sdk-host-entry-tail-probe-20261107/result.json 验证1400事件准确保留377..1400共1024条，并还原全部方法/PID/flush；没有访问SDK存储，不计业务验收。

带修正取证的R1原单项在同一当前安装包通过8.508秒，inherited-entry-probe/result.json/tests.log，句柄30134退出0；原5秒parent/30秒child/6秒sleep/12秒elapsed上限/3秒settlement等待均未改。准确现场 sdk-inherited-parent-deadline-t6o8fl3b/evidence.json 及summary.json保留：父、子均触发on_entered，父run_once6.320秒，原超时/禁止escape断言通过；宿主tail854事件。本轮并未触发tail溢出，溢出能力仅由上述独立探针证明。原先ready后未进入的失败及其根因继续开放，不能用单次成功推断旧问题同因修复。G17/G18和G06真实并发未完成，无模型/CI，无等待中的测试。

## 2026-11-07 G06 逐子任务调度取证：当前安装包无模型验证通过

新增仅验收器使用的 scripts/g06_dispatch_observer.py，记录ChildService提交/工作线程入口、adopt起止、run_once起止、claim起止及同线程所属child的慢/失败父采样；2048事件上限、非阻塞记录、丢失标记，不记录参数、模型内容、凭据或异常消息，不授予权限。包装保留参数/返回/异常，独立审查发现并修正方法改名导致漏记submit及合法关键字调用被误拒绝的问题，复审无上述阻塞。仅支持单个不重叠观察上下文；记录本身可能扰动调度，不能由缺失事件证明无调用。

当前supervisor-parent-diagnostic安装包Python3.11独立环境执行原GroupIntegrationTests.test_group_fanout_replay_bindings_and_run_isolation，第二send仅诊断延迟2秒，原120秒预算/100秒等待/20秒入口及30秒gate均未改。原句柄83517退出0，1项通过、0失败/错误/跳过、106.470秒。dispatch-probe/result.json记录1513事件、recording_lost=false；milestones.json完整归属8个child的submit/entry/adopt/成功claim，worker入口延迟0.084–0.565毫秒，入口至成功claim0.338–1.931秒，最多3次claim尝试。本轮未复现原生70秒延迟；只验证取证可用，非G06真实通过。149产品文件逐字节一致，无模型/CI，完整现场/tmp/tmpdajgkt26保留。

已将该观察上下文接入verify_agent_control.py的原G05/G06入口，在app退出后写dispatch-milestones.json，facts保留文件位置；写入失败保留原SDK错误，缺失诊断为unknown。集成审查另发现外层异常报告会覆盖facts，现已在失败报告中补上准确诊断预期路径，并明确文件缺失为unknown；集成语法检查通过，未运行原生模型图。G06及整体目标继续未完成；已有源码修复不因本诊断新增触发盲目模型重验。

## 2026-11-07 G06 原现场只读排除：无observe堵塞、无贯穿全延迟的单一采样令牌

可重现审计 native-guard-attempt/audit-parent-sampling.py 及 parent-sampling-audit.json 已保存于 /tmp/sdk-delivery-guard-candidate-20261107。两轮第二coder从adopt请求到leased分别71.188/66.758秒；准确同一controller的预算sample receipts在各区间有396/354个output checkpoint，各10秒分桶均非空。独立审查与本地重算一致。它们是采样时钟事实而非提交时间或具体worker归属，只能排除“一个未确认marker贯穿整个延迟”的解释，不能证明没有反复短争用/饥饿，不能由当前samples空表推断历史无marker。

观察库8条请求全部action=adopt，无observe，故ChildService.tick先执行_observe_waits的同步路径不能解释本次现场；capacity=64的线程池也无源码证据表明有意串行整个handler。G06根因仍未确定，不修改超时/采样权限，不提升Gate。本轮只读数据库，无模型、测试或CI。

下一次有因果价值的执行必须同时留存每个child的协调领取、_execute入口、adopt起止、run_once入口、claim起止及父采样等待所属child，才能区分调度未分配、adopt等待和claim反复拒绝。现有历史更新时间被完成覆盖，不能补造这些事实；仅重新跑原模型图不能解除缺项。

## 2026-11-07 本次恢复修复跨Python补验终态

同一supervisor-parent-diagnostic安装包，Python3.10/3.11/3.12各12项全部通过，分别24.639/28.470/26.727秒。Python3.13原12项中11通过、1失败（26.948秒）；准确原矩阵 python-matrix/result.json 保持失败，原句柄15587退出1，不改写原报告。本次监督器检查点恢复项在四版本均通过，但此前缺失检查点的时序失败仍须保留，不能宣称稳定性已证明。

3.13唯一失败为夹具断言deferred_originals只能一次；原日志记录两个完整相同result_id及内容的结果。SettlementJournal.record的2028行起明确允许相同lease/payload重放且保留首次证据，因此修正夹具为非空且每次完整结果相同，原deferred/resolved_result绑定、重开后running/no result/unresolved obligation及准确checkpoint断言保留；失败目录改为保留，增加所有原结果及收据留档。独立审查未发现该修正削弱上述业务断言。不是产品新修复，不重建产品包。

使用同一3.13安装包及独立保存的修正测试，单项补验通过2.419秒（句柄27003退出0），deferred-replay-verification/result.json/tests.log保留，149产品文件仍逐字节一致。不能将原失败矩阵改称一次全绿或完整G17；当前相关范围为三版本12/12、3.13原11项通过加修正后单项通过。无模型/CI，无正在等待测试。G06真实原生并发、完整旧API回归和原生平台证据仍未完成。

## 2026-11-07 父采样诊断修正：新安装包 Python3.11 相关12项通过

新候选 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107 在全新独立Python3.11.18环境安装本地wheel后，原检查点恢复模块11项与作用域跨进程生命周期1项全部通过，0失败/错误/跳过，28.470秒；原句柄74574退出0。result.json、tests.log、安装与环境创建日志保留；149个产品Python文件与冻结来源逐字节一致，无hash、模型或CI。独立复审未发现收紧后的诊断归类存在明确权限绕过。

本轮新增注入/收据留档后单项源码检查也通过，2.397秒，/tmp/sdk-supervisor-injection-diagnostic.log；准确现场 /tmp/sdk-supervisor-checkpoint-reopen-m2xr4djm 包含原注入token与receipt。此前未收到检查点的失败仍保留，尚不能解释其时序，不以本轮通过抹除。监督器budget_clock_cleanup_pending堆栈为故意保留原采样token的故障注入结果，测试仍须实际reopen/ACK/恢复原结果/结算义务才通过。

同一包Python3.10/3.12/3.13相关范围串行补验原句柄15587进行中，预计2分钟，失败即停；不是完整G17或G18。G06真实并发根因及其他完整验收缺项保持开放。

## 2026-11-07 supervisor 检查点修复：部分验证通过，当前仍未验收

此前“尚未修改产品”的记录为历史状态：现已修改 _process_runtime.py 的 supervisor 捕获检查点恢复识别，并新增对应恢复和拒绝测试。原安装包可复现缺失 pending 标记；新候选 /tmp/sdk-supervisor-checkpoint-candidate-20261107 的独立 Python3.10 环境相关12项通过（result.json），另2项错误/缺失令牌边界通过（received-boundaries-result.json）。不等于完整G17通过。

同一新候选 Python3.11 矩阵原句柄27268退出1：12项中1失败，错误为 supervisor_completion_pending_checkpoint 缺失；3.12/3.13未运行。原 tests.log 显示父采样临时 database locked 已降为 budget_capture_diagnostic，父 checkpoint confirmed，但后续恢复识别仍使用原 tracker.capture_error 拒绝。该不一致现已补充处理：仅父错误未留在 errors 中、原父检查点已确认、无pending，且为无异常链的直接临时错误或 _capture_budget_floor 的准确单层包装，才视作已退休诊断；任意清理错误包装及独立context拒绝。新增针对性单元断言通过；独立复审未发现明确权限绕过，但明确进程级验证仍未通过。

本轮 Python3.11 源码模块测试 /tmp/sdk-supervisor-parent-diagnostic-source.log：11项，1失败1错误，20.462秒；监督器检查点为None及另一恢复操作超时，尚未定位，不得以该轮宣称恢复路径通过。该源码增量尚未生成新安装包。保留所有旧失败现场，不放宽期限、不启动模型、不运行CI。G06真实并发根因仍未知，G17/G18及整体目标继续开放。

## 2026-11-07 G17 当前包 Python3.10：确认 supervisor 检查点结算缺口

原句柄75777退出1；scoped-public-matrix/result.json记录Python3.10单项失败6.360秒，矩阵立即停止，3.11/3.12未执行。原20秒participant join、5秒handler及300秒宿主期限未改，不调用模型/CI。完整失败目录/tmp/sdk-scoped-process-lifecycle-oymq0e30保留，准确只读汇总/tmp/sdk-delivery-guard-candidate-20261107/scoped-public-matrix/failure-audit.json。

原execution sdk-managed:legacy:new attempt1/fence1已succeeded，settlement recorded匹配result_id；worker_tree_cleanup及runtime_supervisor_reaped进程清理均confirmed，但原supervisor obligation在runtime.close后仍无resolution，采样表已空。这是持久恢复交接缺口，非仅即时断言太早。原证据parent checkpoint confirmed，supervisor checkpoint因database locked保留unknown/token/captured_envelope/owned_transient，另外parent有unresolved sampling错误。_process_runtime在2229附近仅识别parent checkpoint的待确认结果，故未保留native pending确认标记；runtime虽补ACK并提交result，仍未结算supervisor义务，recorded收据又不进入pending扫描。独立审查确认该链，不由进程清理事实冒充结果权限。

修复边界：先验证并ACK准确执行/代次的原supervisor捕获事实，再由原结果/清理/时钟权限完成原子结算；错误token、跨执行、未捕获、撤权、清理不确定或原业务采样错误均不得放行。尚未修改产品，G17/R2仍开放，不以3.13历史通过覆盖。Native G06串行原因独立保持未知。

另claim-resampling-result.json的0.660秒受控无模型探针确认：两次成功采样后人为延迟超出原.1秒窗口，子任务仍queued，第三次重新采样只领取一次。只证明重复采样机制，不证明Native延迟同因，不更改.1秒上限或预算。

## 2026-11-07 G02 当前包证据独立审计：真实调用成立，严格验收仍缺项

独立审查与只读Kernel原始结果核对确认，当前delivery-guard安装包coder 865f6d9e16624709b1aa0764fdce5067实际调用OpenCode，准确execution agent:865f6d9e16624709b1aa0764fdce5067成功；原结果outcome=succeeded/output=DONE/session=ses_e4c3b9453ffeMINGPfCMzxhlTH，metadata含OpenCode 1.18.32、local/gpt-6-luna及process_cleanup=completed；G05原始产物为A_DRAFT。准确operation ee5cff4d1429400e8a95e099def512c5的receipt对应原execution/attempt1/fence1及confirmed进程树清理，导入位于当前候选env/site-packages。

G02不依赖G06并发，但仍不改passed：install.log明确卸载了已存在的同版本SDK，尚无新环境创建来源证据；配置executable路径不单独证明实际子进程PID/executable。已将上述当前包部分证据及严格缺项写入current-candidate-acceptance.json，原G05/G06失败保持。无新模型调用或测试，不降低验收合同。

## 2026-11-07 修正诊断后：延迟兄弟任务原合同通过

无模型v3诊断原句柄63806退出0，98.529秒、1项通过、无失败/错误/跳过，delayed-sibling-v3-result.json及日志保留于/tmp/sdk-delivery-guard-candidate-20261107；实际安装包导入路径已断言。第二send延迟2秒仅是探针，原120秒预算/100秒等待/20秒双coder入口/30秒gate未改。原测试两Run的双coder并发、reviewer消费、重放关闭及隔离断言全部通过，不提升为真实G06。期间有可重试的控制/领取/生命周期超时，准确异常位置已保留，不能从存在拒绝推断原生串行同因。成功现场亦保留/tmp/tmpsuo1_2uu。

独立只读审查原生失败库：child request完成会覆盖接管/运行更新时间；execution limits无adopt时间，预算checkpoint已推进，第一条子任务预算/观察记录均在lease后，当前采样表为空不证明历史状态。现有证据不能定位第二coder卡在调度、adopt或claim前哪个环节，不据此修改产品或重跑模型。G06仍未通过，整体目标仍未完成。

## 2026-11-07 更正：延迟兄弟诊断的 recovery_required 来自取证包装缺陷

v2原句柄46188退出1，43.798秒，失败数据库完整保留/tmp/tmpx_aj2jz9。只读agent_diagnostics显示两个coder均在adapter入口报告TypeError；核对诊断脚本确认delayed(context,name,**args)与artifact_publish(name=...)冲突，原测试call签名为tool_name。故此前v1/v2的recovery_required不能归因SDK，不能作为产品结算缺陷或修复证据。原报告不覆盖，原始诊断和更正保存/tmp/sdk-delivery-guard-candidate-20261107/delayed-sibling-probe-defect.json。

v3仅把包装形参恢复tool_name，保留阶段和失败目录，原预算/等待不变；原句柄63806重验中，不调用模型、不运行CI。此前Native真实并发失败独立存在，原因仍未知，验收状态不提升。

## 2026-11-07 无模型延迟兄弟任务诊断：并发入口通过，根结算失败

当前安装包独立诊断 /tmp/sdk-delivery-guard-candidate-20261107/probe-delayed-sibling.py 在原 group integration test 的第二次 send 前增加仅用于诊断的2秒延迟，原120秒预算、100秒等待、20秒双coder入口及30秒gate均未放宽。原句柄86587退出1；delayed-sibling-result.json / delayed-sibling-tests.log 保留，35.438秒，1项失败。日志已到after_close，证明原测试两个coder都在释放gate之前进入，未复现原生串行；随后root wait报告recovery_required，不计通过。阶段记录显示ChildService启动多个worker，adopt和run_once有TimeoutError/_ControlAdmissionTimeout/BudgetClockUnknownError拒绝，尚无因果归属。此为synthetic模型下实际SDK，不替代G06真实并发。

原测试TemporaryDirectory会删除失败数据库；本次只保留导出的阶段及异常类型和原日志，缺少原失败DB，不宣称现场完整。v2诊断入口另行保存（未执行），增加12帧异常位置及失败临时目录保留，不改产品、不改原报告/期限，不启动模型或CI。原生串行原因仍未查明，G05/G06及整体目标状态不提升。

# 0.8.0 当前候选验收总表

## 2026-11-07 10:27 按期检查：真实两轮完成，原生并发未通过

同一unit已failed/terminal，MainPID=0，原监督器701307/测试701308均exit1，tree_reaped=true。无需继续等待11:09，不重启，不新增模型调用。原G05.json/G06.json及supervisor报告保持失败；准确有界只读汇总native-guard-attempt/terminal-claim-delay.json和可复现audit-terminal-claim-delay.py保留。

本轮八个Agent（主链7、独立Run1）均succeeded：两轮coder产物、同逻辑reviewer返工反馈及再次消费、绑定/重放/准入效果/期限/负例检查均成功，八次native操作的准确清理关联all_valid=true。主链实际7calls/43turns，独立Run1call/4turns。唯一失败检查为coder_adapter_overlap，两轮均无重叠。原caller结算卡住未在此轮出现，不由单次成功断言历史故障已同因修复。

只读Kernel事件/原child请求显示，第二coder已入队但第一coder完成后才领取：首轮请求created1794017351.447、lease1794017422.635，第一coder成功1794017420.811；返工轮请求created1794017886.282、lease1794017953.040，第一coder成功1794017949.765。此确定延迟在领取之前，但不能判断ChildService分配、父入口、adopt、完成恢复或具体锁的责任。独立源码审查确认claim后生命周期锁会在handler执行前释放，没有证据支持“整段模型执行持锁”结论。后续只做因果定位/无模型受控复现，不无修改重跑真实图。G06并发要求明确保持开放；共享验证器还把它与G05业务链状态绑定，正在核对Goal独立Gate合同，不修改原失败或降低总体并发要求。

等待结束后串行执行改造的作用域预算跨进程回归：scoped-public-result.json记录1项通过、无失败/错误/跳过、6.157秒，原句柄57146退出0。产品来自当前安装包，测试来自scoped-public-source；原模拟隔离、记账和历史事件不等价限制继续保留。本项补当前R2范围，不关闭完整G17/G18，无CI。


## 2026-11-07 R2 作用域预算跨进程夹具改造，尚未执行

仅tests/test_split_store_scoped_process_lifecycle.py的初始Run改用create_run/apply_operations；公开创建与决策后source_revision=1通过可spawn的partial传入原adopt/revise helper，激活读取准确decision.source_revision；原作用域拒绝/放行、Runtime结算、预算/调用数/期限及独立进程断言保留。历史事件断言改为保留实际run.created/application.decided完整前缀，明确不等价于旧人工legacy.waiting事件。失败目录原位保留，不复制运行数据库；既有外部tokens/fixture-host数据库记账保持原样，不直接修改SDK表，不新增hash检查。产品源码未变。

独立只读审查未发现具体阻断，可达SDK SQL为SELECT-only，公共写入交给SDK；保留模拟宿主证明/记账不证明真实隔离的限制。仅AST语法检查，不在当前真实协作期间运行，故不计通过、不关闭R2/G17/G18。修正测试及原helper快照scoped-public-source、逐项范围scoped-public-pending.json位于当前delivery-guard候选，待真实运行终态后再串行执行，原300秒宿主期限、20秒participant join、2秒queue等待及5秒handler窗口均未放宽。


## 2026-11-07 10:07 delivery-guard 修正包单次真实重验

新候选/tmp/sdk-delivery-guard-candidate-20261107/native-guard-attempt已冻结当前验证器，原预算3600秒/16calls/128turns不变，local/gpt-6-luna通过原宿主本地反代配置执行。仅本次一轮，不自动重启、不覆盖旧失败，不同时运行其他SDK测试。systemd unit sdk-080-native-guard-20261107.service在启动命令退出后由宿主确认active/running，监督器701307、原测试701308，启动北京时间10:07:01；这是持久启动证据，尚非协作进展或验收通过。launch-scope.json / scheduled-check.json / native-groups-supervisor.json保留准确身份及范围。

首次检查预计北京时间10:27:01；若仍未结束，依原3600秒截止预计11:09检查终态，不重启原句柄、不延长预算。G05/G06状态仍未通过。该轮前提为guard拒绝修复经独立审查、四Python版本28项边界和当前包实际无模型组路径通过，不因仅新增取证而重跑。

新增仅用于本原生G05/G06的observe_owned_completion_failures，保存最多8条准确execution/attempt/fence及异常类型/位置，避免再次只留下吞掉的owned_decision类型；不存消息、局部变量或模型内容。位置链8层、每层保留16帧，诊断异常不覆盖原SDK异常；现有operation observer另保留独立unknown容量。12项观察器及清理关联测试通过（/tmp/sdk-delivery-guard-native-verifier-tests.log），独立审查无具体阻断。限制：同步诊断写入可能影响时序，ID/类型名无显式长度上限，故不宣称严格字节有界或无损取证。无产品改动、不运行CI。


## 2026-11-07 delivery-guard 候选：两轮组消费通过

/tmp/sdk-delivery-guard-candidate-20261107安装包在原始test_group_fanout_replay_bindings_and_run_isolation中通过，93.098秒、无失败/错误/跳过，原句柄42101退出0；group-result.json及group-tests.log保留。范围为显式synthetic适配器下实际SDK的两个并发coder、reviewer消费、重放/关闭组及两Run隔离，不等同真实OpenCode、显式返工或G05/G06完整通过。未增加send延迟、未调整原120秒预算/100秒等待。

当前新候选包外G01配置/CLI与双语默认值检查亦通过，G01-current-evidence/result.json保留；逐Gate索引current-candidate-acceptance.json仅G01完整passed，其余保留缺项，不把上述合成组或28项边界检查提升为完整Gate。修复相关28项已在Python3.10/3.11/3.12各全部通过，分别52.659/52.229/55.645秒，无失败/错误/跳过；原句柄19267退出0，准确结果python-matrix/result.json及每个解释器tests.log保留。结合此前3.13的28项，仅证明本修复边界的四Python版本，不代表完整Python回归或原生平台矩阵。不启动模型或CI。


## 2026-11-07 交付保护锁拒绝：原包复现及源码修复

真实协作原监督器695074/测试695086已终态失败，native-observed-attempt/native-groups-supervisor.json记录双方exit=1、state=terminal、tree_reaped=true；G05/G06未关闭。第二名coder处理函数正常返回，其保留结果记录owned_decision阶段TimeoutError；原异常堆栈不足，不能证明与下述复现同因。此前09:08运行中状态已由此终态取代。

当前commit-ack安装包三项无模型拒绝路径已通过，negative-current-paths-result.json记录3项、0失败/错误/跳过、42.578秒；仅补当前SDK拒绝边界，不提升完整G06。原历史真实负例保留来源。

原commit-ack安装包在实际activation condition被另一线程持有0.3秒时，可复现处理函数已返回但execution仍running：/tmp/sdk-delivery-guard-old-candidate.log，1项失败，1.660秒。源码修复仅记录condition.acquire明确返回false的原异常身份；只有该次尚未进入保护区的拒绝可以重试。每次释放生命周期锁后重新检查停止、撤权及原deadline；不重试保护区内异常或未知写入。保护锁按本次明确获取情况释放，不释放调用者已有层级。独立只读审查未发现具体阻断。

源码完整owned-completion竞争模块25项通过，49.241秒（/tmp/sdk-delivery-guard-source-tests.log）；另保护区内TimeoutError、已关闭activation、嵌套锁所有权3项通过（/tmp/sdk-delivery-guard-boundaries.log）。新候选/tmp/sdk-delivery-guard-candidate-20261107已冻结源码并生成wheel/sdist，包外-I入口verify.py已完成这28项安装包验证：全部通过、0失败/错误/跳过、53.419秒，原句柄39614退出0；准确结果result.json及tests.log保留于候选。安装包全部149个Python产品文件与冻结来源直接逐字节一致，product-source-comparison.json记录范围；不使用hash。旧包和旧失败均未覆盖。本次不调用模型、不运行CI、不提升Gate；原真实链路、完整回归及平台证据仍开放。


## 2026-11-07 当前安装包 G01 配置最低合同补验通过

包外-I导入当前commit-ack安装包执行configuration_case及实际CLI validate/config show --effective，G01-current-evidence/result.json为passed；YAML与Python有效配置等价，四类非法配置（重复键、未知字段、不安全构造、非法覆盖）均拒绝，中英文Wiki完整默认值注册表与安装包一致。入口verify-G01-current.py、独立只读验证器/Wiki副本G01-current-verifier及原日志G01-current.log保留于当前候选。不启动Agent、不调用模型、不访问运行中SDK数据库。current-candidate-acceptance.json仅G01更新为当前安装包最低合同passed；其余Gate不因本项通过改判，G18最终文档/制品一致性仍开放。

取证源码另为首次unknown观察预留独立8条容量，普通16条期限失败不再占其名额；五项取证单元边界通过/tmp/sdk-operation-observer-reserved-capacity.log。正在运行的冻结验证器未改动。该记录仍为best effort：若连续8次未知记录写入均失败，后续不会自动重试发布；并发状态观察也不单独证明转换责任。独立审查确认容量独立及原异常保持，并指出此写入恢复限制；不宣称无损取证，不以本取证改进触发新模型重跑。


## 2026-11-07 09:08 原真实重验首次按期检查

宿主systemd确认同一监督器695074及原测试695086仍active/running，无最终报告，不重启。准确只读快照native-observed-attempt/first-scheduled-check.json：一个coder的Kernel execution和Agent node succeeded；另一个Kernel running、node submitted；root/controller仍running；已有两项产物。此为实际局部推进，不证明完整G05/G06或修复因果。16条取证记录已被普通期限/争用失败占满，保存记录内前后activation均open；不能以缺少后续记录证明activation始终open，也不能保证捕获之后的首次unknown。原3600秒截止约09:48，下一检查预计09:50核对原终态及清理，无预算延长或新模型调用。当前无模型负例探针继续暂缓，避免增加同机SDK竞争。


## 2026-11-07 G06 保留负例重新核对，避免重复模型调用

读取原始missing_reference及group_required_output case.json确认两项原status=passed、准确native回执、真实provider响应及consumer未执行/未准入事实；保留报告来源，不改写成当前安装包执行。准确复查入口/tmp/sdk-commit-ack-candidate-20261107/audit-retained-g06-negatives.py，产物G06-retained-negative-facts.json。与此前已组合验收的settlement-startup安装目录逐文件比较，44个Agent产品文件中仅application.py/store.py改变，AST变化为AgentApp._wait_iteration和AgentStore._transaction；完整Kernel/maintenance差异另存G06-retained-negative-product-delta.json。早期候选source/src路径不完整，未把缺文件误计为全部产品变更；最终比较使用各原安装目录。

独立审查确认两处Agent变化不直接改变绑定/组拒绝条件，但改变争用/到期时异常传播，故历史事实不能单独证明当前拒绝路径。新增tests/test_agents_negative_current_paths.py三项确定性实际SDK路径探针：缺引用、真实组工具后歧义、缺必需组产物；同时检查consumer无command/Kernel execution/runtime effect/adapter入口，组负例检查无consumer行及准确admission effect。使用显式synthetic模型，不替代历史真实响应；沿用原300/600秒预算、5/8calls、24/48turns及310/610秒等待，不放宽截止。初审要求精确解析error.code并恢复原预算，均已修正；失败现场保留，成功关闭后才删除。仅语法检查，尚未执行，避免给当前真实图增加SDK争用。没有新模型调用或Gate改判，原真实图仍按09:08首次检查计划。


## 2026-11-07 修正包单次真实重验已持久启动

基于已验证的参与锁拒绝清理/COMMIT不确定性修复及当前包原始离线双coder图通过，单次真实G05/G06共用图在北京时间08:48:18启动。目录/tmp/sdk-commit-ack-candidate-20261107/native-observed-attempt保留冻结验证器、launch-scope.json及scheduled-check.json；149个产品Python文件逐字节等于当前源码及原安装包，没有重建或覆盖旧候选报告。预算仍3600秒/16calls/128turns，无自动重启。systemd unit sdk-080-native-observed-20261107.service启动命令退出后经宿主确认active/running，MainPID695074、原测试PID695086；这仅证明启动存活，不证明协作进展。首次结果检查预计北京时间09:08:18，此前不反复检查。

本次增加activation._operation失败取证：保存最多16条原异常类型/位置、原操作、进程内owner身份、时间和前后状态；不保存消息/参数/模型内容。并发前后状态不能单独确定首次转换责任。诊断自身的Exception/BaseException不覆盖正在传播的原SDK异常，最终保存的帧/字符串有界，提取时仍暂时读取原完整堆栈。13项针对性验证器测试通过，日志/tmp/sdk-native-observer-verifier-tests.log；独立审查发现的诊断中断覆盖原异常及保存帧无上限问题已修正并复审，无进一步阻断。真实协作通过条件含准确native清理回执，但G06真实工具歧义/缺输入补证仍单独开放；本次即使主图通过也不能自动关闭完整G06。旧失败保持failed，不把本次启动或诊断测试当成Gate通过。


## 2026-11-07 原生协作验证器补齐逐操作清理核验

scripts/verify_agent_control.py新增group_native_cleanup_evidence并接入原G05/G06主协作图的通过条件：每个实际invocation必须恰好一个独立native operation，原command deadline/execution、committed runtime effect的lease/attempt/fence、当前succeeded Kernel execution及cleaned receipt逐字段一致；树清理必须confirmed。重复operation、缺回执、未知清理和身份错配拒绝，导出仅白名单身份字段，不导出认证能力。attempt/fence严格整数，拒绝布尔值等价冒充。G06仍明确缺真实工具歧义及缺输入负例；只有实际核验all_valid时才不再列清理回执缺项，协作局部成功仍为not_run，不自动通过G06。

针对性验证器测试9项通过、0错误/跳过，0.100秒，原log /tmp/sdk-group-cleanup-verifier-tests.log；其中包含既有共享失败场景不重复执行的检查，日志中的G03/G04/G05/G06失败文字属于这些预期反例，不是真实模型运行。独立只读审查核对生产ledger.complete的认证/身份路径、白名单输出及G06保守状态，无具体阻断。该改动为验证器源码及单元边界证据，尚未进入冻结候选或真实OpenCode执行，不修改旧失败报告，不声称真实清理缺项已验收通过。无产品改动、无新模型调用、无CI。


## 2026-11-07 当前安装包无模型原始双 coder 图

当前commit-ack安装包执行未加send延迟的原始test_group_fanout_replay_bindings_and_run_isolation，1项通过、0错误/失败/跳过，93.104秒。准确导入settlement来自原隔离site-packages并与冻结源码逐字节一致；first-unknown-result.json和first-unknown.log位于/tmp/sdk-commit-ack-candidate-20261107。诊断只包装activation._operation记录open→unknown观察及原异常，保留原返回/异常和期限；本次未观察到该转换。该包装在并发下不能独立确定首次转换的责任操作，因此不可据此证明历史原生故障根因。受限环境首轮因loopback拒绝skip，另存first-unknown-restricted-result.json/log，不计通过；宿主实际执行无skip。

源码与独立只读审查均排除“操作ticket准入后、存储调用前到期就会毒化activation”的假设：操作evidence默认clean=True，_open_intent_connection也先检查期限再标记dirty。未为该假设修改产品。没有新模型调用，没有重复该通过用例；真实G05/G06失败和首次activation未知原因仍开放。此结果补充当前修正安装包的原始离线双coder/两Run隔离范围，不提升为真实运行时Gate通过。


## 2026-11-07 本次状态核对：没有新增完整 Gate 通过

原真实模型会话64270已终止，native-groups-supervisor.json记录test_exit_code=1、supervisor_exit_code=1、state=terminal、tree_reaped=true。G05/G06失败保留，没有继续等待的这次模型运行，也未重启。监督器清理记录不替代逐操作native回执验收。

当前commit-ack安装包原29项批次仍为27通过、2项setup错误。仅补跑此前未进入主体的准确两项，setup-followup-result.json记录2通过、0失败/错误/跳过，0.867秒；产品来自原隔离site-packages，无模型调用。原初始化期限失败原因仍未解释，不把补跑写成原29项整批通过。

近阶段确认并修复了参与锁正常拒绝的清理记账，以及COMMIT实际尝试/确认丢失的未知状态边界；局部反例和安装包检查不能证明原真实activation故障同因。完整Gate关闭数没有增加。后续不应继续无新因果证据的模型重跑或重复全量回归。


## 2026-11-07 参与锁拒绝的清理确认修复

两项原setUp失败的源夹具已补失败现场保留：不改SettlementJournal默认初始化窗口、5秒upgrade或各测试主体期限；记录失败stage、总耗时、已完成阶段耗时、准确异常/traceback及Python来源，保留原临时目录和WAL。成功setup仍沿原清理路径，setup失败重新抛出原异常。该夹具修改仅AST语法核对，尚未重跑；不把取证改进当成业务或回归通过。下一次只补这两个测试主体，并检查如有新失败的准确现场；不会无假设重复29项。


另确认COMMIT尚未调用时的期限拒绝缺陷：_connection原先在admit之前设置commit_uncertain；retry_sqlite_admission会先检查期限，可能没有实际COMMIT就拒绝。已将标记移动到实际connection.commit调用之前，仅成功返回后清除；失败/中断尝试仍保留未知。旧receipt候选的实际事务检查1.194秒复现unknown及close错误，原log为/tmp/sdk-commit-admission-old-candidate.log。源码同检查1.050秒通过，真实native commit成功返回后注入KeyboardInterrupt的独立子进程检查1.193秒通过并保持unknown、拒绝close。子进程另断言导入模块与父进程准确来源一致，未新增重放/放宽截止。

候选/tmp/sdk-commit-admission-candidate-20261107的原会话66951已退出1，29项中28通过、1失败（21.513秒）：原test_ambiguous_commit_keeps_owner_and_exclusion在实际commit成功后模拟admission确认丢失，发现marker在包装器内部清除过早。保留原result.json/verification.log，不改原断言。已修正为包装器仅在实际commit前置True，整个admit成功返回后才清除；既保持未调用commit的期限拒绝为False，也保留确认丢失的未知。复审认可，原审查遗漏此边界一并保留。修正候选/tmp/sdk-commit-ack-candidate-20261107已安装，149个Python产品文件与当前源码/冻结来源一致。原会话56666退出1，29项中27通过、两项setUp错误、无skip，20.384秒。原ambiguous_commit检查及新增正常拒绝/未尝试commit/真实commit后中断边界通过；test_delayed_close_worker_start_is_not_a_hard_timeout和test_interrupt_after_condition_acquisition_releases_condition在构造SettlementJournal的原初始化期限内失败（分别SQLite interrupted、operation budget elapsed），测试主体未执行。不调整默认窗口、不重标通过、不立即重复；保留准确result.json/verification.log，待原真实运行终态后定位设置阶段耗时，不能归因于提交修复或宿主负载而无新证据。独立审查认可此限定修改及反例。18项完整合同保留在该候选current-candidate-acceptance.json，全部保持当前候选未完成；旧真实失败和原有G17/G18缺项没有被局部通过覆盖。


maintenance.storage_participant新增仅内部使用的逐操作清理回执：只捕获_acquire明确返回的准确MaintenanceBusyError，并在原descriptor的os.close成功返回之后记录同一异常对象；中断、close失败及普通未确认异常不获回执。settlement的journal与Kernel lifecycle连接只接受这一准确回执为clean，不重置已有unknown activation，不改commit未知处理。独立审查发现无evidence时误保留已关闭owner的边界，已修正并增加检查；复审无阻断项。

旧W安装包运行同一“正常拒绝后owner仍可用”检查，1.048秒实际复现owner.state从open变unknown，另有unknown状态的close清理错误；原始log为/tmp/sdk-participation-cleanup-old-candidate.log。这证明本记账缺陷存在，不证明它导致此前真实coder故障。首轮新增检查还有三处夹具错误（未创建普通测试文件、close注入过早、缺note_id），原log保留/tmp/sdk-participation-cleanup-first.log；修正后源码五项通过2.252秒，并补上无evidence边界。

新候选/tmp/sdk-participation-receipt-candidate-20261107从W冻结来源只覆盖maintenance.py、settlement.py、新增测试及三份当前控制层文档，wheel安装至独立环境。原会话12176退出0，当前安装包27项通过19.678秒，无skip，准确模块来源/字节及原有activation中断和截止边界均记录在result.json及verification.log。无模型调用、不改原真实场景现场，也未关闭G05/G06或整体目标。


## 2026-11-07 等待退避正式改动及安装包边界验证

北京时间07:54首次按期检查：原会话64270和宿主监督器/子进程仍存活，未重启。真实场景已被两个coder取消所否定，G05/G06保持失败/未完成，不能称仍等模型成功。只读settlement_notes证明两名coder均在claimed_setup、尚无handler_entered时遇到SettlementBusyError“settlement activation is not open”；第二名最终取消原因另记录Kernel事务控制期限耗尽。planner模型已返回但缺answer，其运行时effect已提交失败值，Kernel执行仍running且有pending结算。完整准确状态见native-first-scheduled-check.json，不提前伪造进程终态。原3600秒期限约北京时间08:33:34，下一次计划08:35按原句柄检查，未延长预算，不再调用新模型。

独立源码审查发现另一条已确认的记账缺陷：storage_participant在正常锁拒绝并关闭descriptor之后传播MaintenanceBusyError，而settlement的_intent_connection及Kernel lifecycle连接路径缺少准确关闭回执，可能将明确未开始的操作误记为unknown并毒化activation。不能用此推断它就是本次真实故障的最初原因；现场没有首次毒化操作及准确cleanup身份。修复必须增加准确的清理确认回执，真实中断、close失败和commit未知仍保持unknown；不得直接把activation重置open。


当前wheel真实G05/G06共用链路已在原3600秒/16调用/128轮预算下启动，原会话64270。宿主ps核对监督器689914与子进程689916均存在；限制环境的kill(0)看不到宿主PID，不作为退出证据。准确20分钟后检查时间见候选native-groups-launch.json。不声明通过或后续仍存活，按原句柄检查，不因观察超时重启。

当前源码仅在HandlerChildren._await_window的pending轮询加入50/100/200/400/500毫秒退避；状态/响应/诊断变化重置50毫秒。保留pending token恢复、权限检查、先读取已有结果、每轮pending重新采样及原期限限制。不同于临时对照，不将采样移到结果读取之前，避免改变已有无writer结果交付。新增三项确定性检查通过；独立审查未发现阻断缺陷，要求实际pending/祖先guard、截止交付和双coder路径验证。中英文文档明确最长500毫秒观察延迟及非新增执行预算。

候选`/tmp/sdk-wait-backoff-candidate-20261107`从N冻结源码仅覆盖children.py与新增测试，构建wheel并安装到独立复制环境；verify.py确认使用该安装包且children.py与冻结源码逐字节相同。首次构建因本地缺少build入口失败，保留build.log，之后使用setuptools构建成功（build-retry.log）。原句柄45541退出0，12项全部通过、无skip，122.575秒，准确范围见result.json；包括带3秒send间隔的双coder两轮协作、真实取消、墙钟回退水位、父/祖先采样guard、准确pending owner恢复及晚结果/未知时钟拒绝。另原句柄97963退出0，两项原截止后实际writer锁下事实交付通过，7.018秒，日志cutoff-delivery.log。所有149个当前Python产品文件与冻结源码逐字节一致。该14项是当前wheel的离线证据，不关闭真实模型Gate。

剩余要求、原失败证据及关闭条件统一见 [剩余验收清单](SDK_0_8_0_REMAINING_ACCEPTANCE.md)。新增通过数量不等于关闭 Gate；没有可靠依据时不提供整体完成时间。

## 2026-11-07 当前真实协作终态及串行定位

### 诊断自身错误及等待对照的证据边界

修正参数名后，adaptive-corrected对照106.547秒通过原方法全部断言（两轮Run的双coder同时入口、发布产物、reviewer消费、绑定与Run隔离），无skip。会话36735退出0。仅第二次send前增加3秒宿主延迟，原20秒双入口/30秒gate/120秒预算和断言保留；SDK使用当前N安装包，但临时替换等待函数，因此不是未修改产品验收。保留现场`/tmp/tmpi_qdekab`，只读执行状态及准确结果索引见候选`adaptive-corrected-readonly-summary.json`。该对照支持进一步验证自适应观察退避，未关闭G05/G06、历史期限失败或整体回归；产品变更前还需验证截止前已提交结果的交付、时钟前跳、取消/撤销和pending采样边界。


提交计时对照2461次commit的跨线程耗时合计34.637秒，单次最大0.097秒；该合计不是Kernel独占持锁时间。固定等待间隔50毫秒改200毫秒的诊断仍未通过并发断言，因此不能据此声明调整轮询即可修复。

自适应等待对照（上限500毫秒，每次读取前仍重新采样）29.733秒失败，但失败边界已越过双coder入口与关组。保留现场的同配置复查31.474秒失败；原Kernel只读记录确认两个coder的runtime effect均为TypeError：`slow_call() got multiple values for argument 'name'`。这是临时诊断包装函数与artifact_publish(name=...)发生参数冲突，不是SDK产物发布缺陷；原失败保留，不计完整通过，也不能当作自适应方案仍未满足并发入口的证据。现场为`/tmp/tmpwz1cccuz`，候选目录保留adaptive-control及adaptive-retained脚本、日志、JSON。参数冲突已在新的adaptive-corrected诊断中改为tool_name；产品源码未应用轮询变更，后续结果须另行记录。


第二名coder专用诊断v3在同一安装包与执行条件下41.040秒失败，原始local-group-scheduling-diagnostic-v3.json保留三份准确异常及同期线程栈：第二名run_once遇到_ControlAdmissionTimeout时，agent-wait线程分别处于预算采样_finish_budget_sample的事务commit，其他monitor/verify等待相同Kernel锁。这证明准确竞争位置，不证明单次commit耗时或全部历史延迟根因。未调用模型，进程已退出1。独立设计审查否决将_RetryWindow.remaining整体替换为读取其他观察者的新floor：它参与业务准入，不能以无新wall观测的读取代替独立采样；产品未应用该方案。后续须检查同一调用自身已确认采样是否在claim前重复，而非放宽采样上限或跳过权限/期限验证。

更窄的“queued子任务省略service预采样、交由run_once采样”方案同样未应用：run_once可能因diagnostic exclusion、settlement/thread容量或关闭而在claim之前返回，不能假设每次调用均有新采样；还须处理原pending sample及on_advance传播，且wait工具自身期限可能早于子任务执行期限。当前未找到同时满足这些条件的简化实现，不把相邻两次采样直接认定为可安全删除的重复。后续因果实验应区分等待观察线程的采样负载与单次事务延迟，保留原业务截止和并发断言。

补充无模型定位：当前安装包执行原test_group_fanout_replay_bindings_and_run_isolation，仅在第二次group-send之前加入3秒宿主延迟，原20秒双coder入口断言、30秒coder gate、120秒预算不变。两次分别40.091秒、43.291秒失败，均未满足并发入口；不冒充原测试未改动执行或原生验收。脚本及输出保留于同一候选目录diagnose-local-group-scheduling.py、diagnose-local-group-scheduling-v2.py、local-group-scheduling*.log/json。第一次测试导入路径错误另存import-failure.log，不计执行。

边界记录明确第二名coder已进入ChildService._execute并完成_wait_parent_entry，随后在Runtime.run_once中反复遭遇_ControlAdmissionTimeout、_BudgetSamplingAdmissionTimeout及claim_and_start的Kernel control admission budget elapsed；第一名释放后才推进。第二次至多三份线程栈在第一名coder早期重试时已用尽，不能当作第二名阻塞时准确锁持有者证据。通用host误领child假设已由_next_claim_row的既有过滤排除，不据此改产品。下一诊断应仅记录第二名的claim/采样期限与准确锁竞争，不扩大模型回归或放宽0.1秒单次准入上限。

native-admission候选原句柄14927已退出1，22:51:33 UTC结束，监督器确认tree_reaped=true；没有仍待刷新的模型进程。原native-groups-evidence/G05.json、G06.json和acceptance.json均保留failed。两轮coder产物、reviewer消费、原逻辑reviewer关联及返工反馈绑定完成；所有报告内检查除coder_adapter_overlap外为true，但两轮均未出现适配器重叠。不能把这些局部事实提升为G05/G06通过。G06仍缺真实工具歧义/缺输入负例及逐操作清理证据的完整关联核验。独立复核确认此边界。

只读原Kernel和观测日志生成 `/tmp/sdk-native-admission-candidate-20261107/coder-queue-audit.json`，脚本audit-coder-queue.py可复现：第二名coder分别在Kernel队列等待83.325和88.073秒，adopt等待请求在入队后约0.851和0.939秒已持久化。串行现象在handler dispatch之前已经出现；不是仅有模型推理或适配器内部串行的证据。默认应用容量4、同角色无限额；尚无准确调度/领取等待栈，不能认定根因或修改权限/预算绕过。下一定位范围收窄到child调度、原父权限/预算采样及claim之前的等待，不重跑整条模型图。

## 2026-11-07 当前候选默认值、链接及NOTICE静态核对

native-admission安装包ApplicationSpec默认值与docs/AGENT_CONTROL.md、wiki/Agent-Control.md、wiki/Agent-Control-zh-CN.md的三份完整JSON注册表一致，三文档字节等于冻结来源；592个本地链接均存在。docs-defaults-links.json及verify-static-defaults.py明确仅检查默认值和路径存在，不执行README示例、不核验远端链接或全部正文语义。sdist和wheel中各自唯一NOTICE与仓库原文相同，delivery-validation.json保存准确包内路径；无摘要检查。

这是当前候选G01/G18局部证据，不提升完整Gate状态。未并行启动回归或模型请求，真实graph继续等约定22:45 UTC检查原句柄14927；此处不依据启动记录断言仍然存活。静态报告编辑不为此重复构建。

## 2026-11-07 完整修复候选50项安装包验证通过，真实协作重验启动

/tmp/sdk-native-admission-candidate-20261107完整sdist→wheel→独立既有依赖环境安装，151产品文件与冻结源码/工作树相同；相对完整clock-pairing候选仅execution_kernel/completion_clock.py和children.py变化，previous-candidate-delta.json保存字节比较范围。不是全新依赖解析或最终归档。

准确50项全部通过33.247秒，无failure/error/skip；句柄12952及监督器退出0、tree_reaped=true。范围19项采样检查、21项owned-return权限/期限、6项窄子准入、3项既有子检查及原下游goal图；manifest/result/log/supervisor和verification-scope.json明确合成adapter/真实本机Runtime边界，不冒充模型验收。两处改动独立审查要求已落实；原下游超时、历史期限和暂停退出原失败不因本次通过改判。

同一安装包真实G05/G06共用graph已启动，句柄14927；原3600秒/16 Agent调用/128轮预算、断言及原返工链不变。预计10–15分钟，首次检查22:45 UTC（北京时间06:45），native-groups-launch.json记录原句柄/预计时间。无其他回归并行；额外诊断只限每进程至多32次私有准入错误的frames/identity，分类结果不变，记录非穷尽。不以启动证明仍然存活或通过。18项索引为新候选current-candidate-acceptance.json，真实协作结果待查，其他缺项保持开放。

## 2026-11-07 原核心回归未执行尾部100项全部通过

按修订预计时间检查原句柄60799：退出0，100项全部通过，无failure/error/skip，653.853秒；监督器terminal、tree_reaped=true。实际已覆盖原113项中此前未执行的100项，保持原期限、没有模型调用或通过前缀重跑。准确agent-tail-manifest/result/progress/log/supervisor和tail-scope.json保存在presample-inspection候选。runner通用Agent-state描述由精确manifest范围替代。

这些结果属于原presample冻结安装包，不代表其后两阶段完成时钟及窄子准入分类的新候选整批通过；需按变更影响核对，不抹除原下游消费超时或历史两个期限/暂停退出失败。完整回归、G05/G06及平台要求仍未关闭。

## 2026-11-07 子准入重试收紧到运行时明确未认领阶段

独立审查阻止将_TransactionAdmissionDeadlineExceeded整体分类为可重试：外层runtime.run_once可能在已认领后发生另一笔未开始的事务失败，不能据单笔事务推断整个调用无效果。当前children.py仅允许准确私有类型、无cause/采样token、准确dict execution_context声明execution_assignment=execution_unassigned且phase=claim、并且无execution_id/attempt/fence字段；缺失/未知/已认领上下文均原样返回，非运行时复合调用保持不重试。

新真实Runtime测试在claim前触发实际事务截止，由Runtime自身附加未认领上下文，原窗口重试后业务仅一次，1.951秒通过；另在真实claim后、claimed_setup阶段触发实际事务截止，1.038秒通过，确认原异常/真实ID/attempt/fence保留且整个调用仅一次、业务未执行。后者夹具初稿漏收timeout_seconds造成TypeError，原日志保留，修正为接受并转发后才完成预定负例。普通无上下文、未知上下文和已认领上下文也有明确拒绝测试。独立审查确认代码收紧解决前述阻塞，不把它当作历史native因果证明。日志/tmp/sdk-child-admission-scoped.log、sdk-child-admission-real-runtime.log、sdk-child-admission-real-claimed{,-v2}.log保留边界及修正。

最终待验新候选/tmp/sdk-native-admission-candidate-20261107构建中，包含完成时钟两阶段和上述窄子准入分类；尚未运行安装包验证，不宣称G05/G06或其他Gate已通过。

## 2026-11-07 两个短准入阶段补齐，子等待分类缺口实际复现

完成时钟的同类短检查也可在_begin_budget_sample尚未创建marker时到期。新test_pre_marker_inspection_cutoff_retries_without_arming_twice先在原实现失败；修复后保留token=None/pending=None/no budget_sample_token的明确未准入分支，既有cause、未知连接、采样已开始、原期限和权限检查保留。十九项源码测试通过15.737秒；增强正例确认仅一次成功arm及一次raw sample，单独通过0.556秒。八个独立pre-marker负例覆盖不确定marker/pending、sample开始、cleanup cause、transaction/commit未知、原cutoff及撤销，独立审查无阻塞。source日志在/tmp/sdk-pre-sample-inspection-boundaries-v4.log及/tmp/sdk-pre-marker-single-sample.log。

另沿native child_wait诊断追查children._transient_control_error，确认未分类私有_TransactionAdmissionDeadlineExceeded；它仅由Kernel事务在进入body前的strict cutoff检查产生。新增test_child_transaction_admission_retry通过实际SQLiteKernel._transaction复现：旧实现第一次未进入body便退出；修复只对准确私有类型、无cause、无采样token的未准入异常在原RetryWindow内续试。三个源码测试0.750秒通过，含实际body仅一次、原cutoff保持及cleanup cause/tagged obligation/普通body TimeoutError不重试。pre/post日志/tmp/sdk-child-admission-{pre,post}-fix.log保留；未直接写SDK表。独立审查待结论，不将类型吻合当作历史原场景因果证明。

/tmp/sdk-serialized-inspection-candidate-20261107是在子等待修复前生成的中间完整制品，superseded-before-runtime-verification.json明确不作最终候选验收。原100-ID回归仍使用原presample冻结安装包，按原预计时间检查，不因源码修改重启。

## 2026-11-07 新安装包修复范围32项通过，续跑未执行100项

presample-inspection候选准确32项安装包验证全部通过、无failure/error/skip，28.235秒；原句柄33577退出0、supervisor tree_reaped=true。准确范围为十项采样检查、21项既有owned-return权限/期限检查及原下游goal产物消费失败项；agent-core-manifest/result/log/supervisor和verification-scope.json保留来源。通用runner的Agent-state描述不作为范围，以manifest为准。修复经独立审查无阻塞，源码和安装包均有同token重试及拒绝边界证据。原下游15秒超时本次未复现，不归因为完成检查缺陷，不将原失败因果关闭；G05真实链路尚未重验。

从旧113-ID清单精确排除已执行13项，余100项现用新安装包单独续跑，句柄60799，agent-tail-manifest.json保留精确ID；无模型、原期限不变，不重跑原通过前缀。预计8–10分钟，首次检查22:26:29 UTC（北京时间06:26:29），tail-launch.json保留原句柄和计划。仅启动事实，不声明通过或仍然存活；尚未关闭完整回归、G17或G18。

## 2026-11-07 返回检查修复边界完成源码验证，新安装包验证启动

源码test_serialized_return_sampler_admission准确十项通过3.997秒：同一未采样marker续试、竞争采样者、因果链异常拒绝、已采样拒绝、owner/pending变化拒绝、transaction/commit未知拒绝及原工作期限耗尽。新增拒绝夹具初稿复用同一返回边界失败，日志/tmp/sdk-pre-sample-inspection-boundaries.log保留；改为各自独立fixture、仅恢复注入的内存故障并通过正常SDK完成清理，不重置返回边界或写SDK表，v2日志保存十项通过。独立审查无阻塞；不视为真实G05验收。

完整新候选/tmp/sdk-presample-inspection-candidate-20261107从当前工作树冻结源码生成sdist→wheel、安装至独立既有依赖环境，151产品文件与冻结源码及当前工作树逐字节相同，非全新依赖解析。准确32项安装包验证已启动，句柄33577，预计22:17:42 UTC检查；十项采样检查、既有返回权限/期限检查及原下游消费失败项。不追加模型，原超时不变；失败保留原目录和wait清理前线程栈。尚无结果，不称通过。

## 2026-11-07 短检查超时缺陷复现及源码修复；核心回归另有失败

当前完整安装包定向复现：原生返回在_finish_budget_sample的_read_floor尚未采样时耗尽一次短检查，InspectionBudgetExceeded直接逃逸，准确pending token保留、serialized_sample_started=false，原工作期限尚存。新增test_pre_sample_inspection_cutoff_retries_the_same_owned_marker在旧安装包失败。源码completion_clock.py仅允许无cause的准确InspectionBudgetExceeded在原native期限内、同一未采样marker及owner、无事务/commit未知时重试；原权限/期限检查及0.1秒单次上限保留。源码五项sampler测试通过1.707秒，包括同token续试、有cause拒绝及已采样拒绝。日志/tmp/sdk-pre-sample-inspection-fix.log。独立审查要求补齐ownership/cleanup未知及原期限耗尽负例；尚未完成安装包验证，不将源码测试视为真实G05通过。当前工作树产品已不同于完整候选，旧证据保持其原来源。

按预计时间检查核心回归原句柄30001：退出1，supervisor tree_reaped=true。113项清单仅实际执行13项，12通过、1错误、100未执行，36.795秒；失败为test_agents_goal.GoalIntegrationTests.test_downstream_binding_uses_revised_goal_artifact_and_version，原wait(15)在orchestrator.store._check_caller_deadline抛出TimeoutError。准确agent-core-result/log/supervisor保留于完整候选。未延长期限、未重跑前缀，也未将其归因为上述独立完成检查缺陷。两原句柄均已终止，不再报告为等待中。

## 2026-11-07 当前真实G05/G06链路失败，保留原现场

按原预计时间检查句柄83616，进程及监督器退出1、state=terminal、tree_reaped=true；未重启。完整候选native-groups-evidence/G05.json记录真实planner开组、两次coder准入及关组，但group wait返回failed，reviewer调用被agent_group_upstream_failure拒绝，没有完成review/rework合同。G06共用场景同样失败，不能将已观察局部工具调用标为整项通过。

原现场return-failure-d3097d782ec04947898f5931fd0a415c.json记录InspectionBudgetExceeded：_sqlite_completion.py→completion_clock.py→supervision.py的_finish_budget_sample→_read_floor→InspectionBudget.check；original_work_seconds_remaining约3260.501秒。coder另有child_wait/_TransactionAdmissionDeadlineExceeded诊断。尚不能把两者认定为同一根因，当前先核对短存储检查窗口和原工作期限的错误传播，不追加模型调用。原报告、预算及清理证据保留，不降低合同或改判通过。

## 2026-11-07 配置及能力拒绝22项完成四Python版本

完整sdist构建的同一wheel在Python3.10/3.11/3.12的既有隔离环境离线强制安装，准确22-ID配置/默认值/非法YAML/能力拒绝清单分别2.629/2.702/2.303秒全部通过，无failure/error/skip。原句柄89501退出0，各专属子树tree_reaped=true；151个产品文件逐字节等于完整wheel。加上完整制品Python3.13既有22项证据，该局部范围四版本完成。准确结果、来源和边界见/tmp/sdk-clock-pairing-python-matrix-20261107/config-matrix-scope.json及逐版本config-current系列，不把版本重复计成新增ID或完整旧API回归。

真实G05/G06共用链路已用完整安装包启动；句柄83616、native-groups-launch.json记录原预算和北京时间06:09后的计划检查。此段只记录启动，不声明模型结果、业务成功或仍然存活；到预计时间再用原句柄核实，不重新启动。

## 2026-11-07 完整sdist/wheel补齐NOTICE，当前G01/G13本机功能证据完成

完整制品快照 `/tmp/sdk-full-clock-pairing-delivery-20261107` 从当前release/0.8.0的811个tracked及非ignored untracked常规文件顺序复制；保留工作树改动，不是原子commit快照。生成sdist，从解包sdist构建wheel，再向独立既有依赖环境离线强制安装。NOTICE在sdist和wheel内与仓库相同；151个产品文件在新wheel、新安装及已验clock-pairing候选间逐字节一致，因此不为纯打包补件重跑全部产品测试。delivery-validation.json/source-files.json/build.log/install.log保留来源。非全新依赖解析验收，未发布。此前最小wheel缺NOTICE的限制已在此完整制品修复，旧制品不改写。

新完整安装包22项配置/默认继承/非法及重复YAML/能力拒绝测试全部通过，1.761秒，无failure/error/skip，原句柄52117退出0、tree_reaped=true。冻结来源和精确config-current清单保留；G01及G13不支持strict业务前拒绝的本机最低功能合同已有当前证据，G13仍无已验原生strict后端。它们不替代完整Python/原生平台矩阵。

source/scripts/check_docs.py在此安装包实际执行：592个本地链接、4个中英文README示例全部通过，0skip，20.047秒；三份完整默认值JSON注册表一致。原句柄50273退出0、tree_reaped=true。六个冻结公开类型消费者按Python3.10目标通过mypy，mypy-current.log保留结果；最初系统Python无mypy的失败保留mypy.log，改用项目既有工具环境后通过，未修改产品掩盖失败。

current-candidate-acceptance.json为此完整制品的18项统一索引，明确本机G01/G13功能证据及其他缺项。G17历史失败/完整回归、受公共时钟差异影响的真实执行证据和G18原生平台仍未完成；此后验收报告编辑不在该811文件快照内，尚非最终交付归档。不因报告编辑立即重复构建，无模型、CI、推送或发布。

## 2026-11-07 两项修复完成相关Python矩阵，统一当前候选索引

`/tmp/sdk-clock-pairing-python-matrix-20261107` 在Python3.10/3.11/3.12各完成20项时钟/预算/wait回归，分别0.933/1.083/0.979秒，均无failure/error/skip，监督器退出0、tree_reaped=true。原句柄18864退出0。scope-and-parity.json核对各环境149个Python产品文件等于clock-pairing冻结来源，准确manifest/result/log保留；加上已有3.13相同18+2测试，两个修复的直接相关范围四版本已验证，不等于完整Python回归。

独立三文件差异复核确认：旧G01–G16报告保留为原产品实际观察；配置/默认值及不支持能力拒绝的非计时事实可在路径不变得到核对后复用，公共时钟和依赖wait影响的真实执行、恢复、预算、取消等不能整体升级。此前统一表明确属于settlement-startup历史候选，不能当作新候选通过表。当前候选current-candidate-acceptance.json逐项保存Goal §7的18个要求、原证据指针、当前局部证据及缺项，不把缺证据改标不适用。G17原失败和G18平台缺项保留。

制品核对另确认：当前候选是最小测试构建快照，wheel未包含仓库已有NOTICE；不得作为最终发布制品。仓库pyproject/MANIFEST已声明NOTICE，缺失来自测试快照未复制该文件，不是新增产品源缺陷。最终完整sdist→wheel必须包含它并核对包内产品与已验产品一致。当前未发布、未推送、未触发模型或CI。

## 2026-11-07 当前候选Agent状态48项完成，默认值及链接复核

clock-pairing候选的独立Python3.13安装环境完成原46-ID Agent状态范围，加两项wait期限分类回归，准确48项全部通过、无failure/error/skip，163.802秒。覆盖状态、提示冻结/配置版本、双生产者图、知识取消竞态、会话冲突、邮箱权限/恢复及宿主锁；原3.13错误导致未执行的尾部本次已实际执行。agent-current-manifest/result/progress/log/supervisor及冻结source保存准确来源，agent-current-scope.json核对九个测试模块与当前源一致。原句柄21015退出0、专属子树tree_reaped=true。原3.13错误保留，不将其准确根因提升为已证明；两项历史间歇失败保持开放。其他Python版本仍需对当前候选核对，不能沿用旧产品结果称完整矩阵通过。

同一安装包的ApplicationSpec默认值与docs/AGENT_CONTROL.md、wiki/Agent-Control.md、wiki/Agent-Control-zh-CN.md三份JSON字段注册表完全相同；592个当前本地文档链接无缺失。docs-defaults-links.json明确只验证字段表及本地路径存在，未重跑README示例、未核验远端链接或全部正文语义，非最终交付归档。无产品改动、模型、CI或发布；G17/G18仍未完成。

## 2026-11-07 修复时钟发现与采样错配，新候选19项通过

新候选 `/tmp/sdk-clock-pairing-candidate-20261107` 包含 budget.sample_clock 的最小修复：Linux先读取并验证boot ID，再读取BOOTTIME并紧邻读取墙钟；发现失败后的process fallback也重新采样monotonic。原代码将发现前elapsed与发现后wall配对，发现耗时可形成虚假的前移水位。确定性无sleep测试模拟0.75秒发现延迟：旧安装包六个子场景失败，正常墙钟路径下一次投影多扣0.75秒；新实现只计一次。wall_time历史floor不改写、发现实际耗时仍消费原预算；Windows成功路径已有GUID后ticks采样，未改其原生实现。不同采样延迟可能保留最大偏差，不能称每次延迟都会累加。

独立审查无阻塞。源码18项通过后，新wheel独立Python3.13环境准确19项通过，8.667秒：三项发现/回退测试、15项既有预算合同及原父子期限真实进程场景（8.417秒）。原父5秒/子30秒/实际进入/停止及清理断言保留。supervisor退出0、tree_reaped=true。149个Python产品文件与安装文件及当前工作树逐字节相同。pre-fix-reproduction.log/json、clock-regression-manifest/result/log/supervisor、source-applicability.json保留旧包失败、新包通过、安装来源及范围。原runner复用的Agent-state文字不准确，以精确manifest及source-applicability为准。

该修复证明一个实际预算时钟缺陷已消除，不证明原两个继承期限失败由它导致：原现场没有boot-ID发现耗时。因此R1历史失败仍开放，不用本次通过替代因果证据。Windows测试使用假provider，不是原生平台验收。前一候选及更早证据须按本次产品差异复核，不整体升级；G17/G18仍未完成。无模型、CI、推送或发布。

## 2026-11-07 新候选3.11暂停续接：一次诊断通过，历史失败未关闭

`/tmp/sdk-nested-pause-current-py311-20261107` 使用 wait-delivery-cutoff 新 wheel 的独立Python3.11安装环境。149个Python产品文件逐字节等于新候选冻结来源；测试源与当前工作树一致，见source-applicability.json。仅执行原三级进程暂停/修订/续接项，保持所有原期限及断言，40.010秒通过，无failure/error/skip；原句柄60640退出0，监督器tree_reaped=true。保留实际A→B→C进程、旧代次拒绝、原预算和新代次执行；宿主授权仍为模拟。

失败前线程栈和原数据库就地保留诊断未触发。因此没有取得历史15秒join失败的根因证据，原失败仍开放，不因本次通过改判。结果/日志/冻结源/监督报告保存在上述目录。不得无新因果假设继续重复这一单项；该次结果只补充新候选的准确路径证据，不关闭G17或完整Python矩阵。无模型、CI或发布。

## 2026-11-07 等待期限修复：新候选局部验证，旧证据不自动升级

新候选 `/tmp/sdk-wait-delivery-cutoff-20261107` 已由冻结产品源码构建 wheel 并安装到独立 Python 3.13 环境。`product-source-parity.json` 核对149个 Python 产品文件：冻结源码、安装文件、当前工作树逐字节相同；此范围不等于此前151个全部打包文件核验。

修复 Agent wait 的调用者期限在依赖投递阶段被包装为 DependencyDeliveryAttemptError 的异常分类问题。仅当直接原因是存储自身期限异常、且未携带未知清理证据时转为公开 TimeoutError；业务 TimeoutError、事务清理异常及投递阶段/事件身份的 cause 链保留。产品改动及针对性测试已独立审查。新增两项测试包含双方 wait 入口、四个投递阶段以及业务超时/清理异常边界；它们验证分类，不证明历史竞态根因。

新安装包准确4项通过、0 failure/error/skip，28.339秒：两项新增分类测试、此前 Python 3.13 失败的双生产者消费图、结果产物重放与重开。`cutoff-regression-result.json` 保存准确ID和安装来源，`cutoff-regression-supervisor.json` 确认退出0、专属子树清理。原3.13失败日志保留；本次通过不证明其原 TimeoutError 的准确来源，也不关闭完整矩阵。

此前 settlement-startup/delivery-snapshot 的回归证据属于修复前产品，不能整体称为当前新候选通过；须按变更影响复核。新增测试后旧480模块/3450不同ID发现计数也不再是当前完整范围。G17/G18仍未完成：父子继承期限原失败、3.11暂停退出原失败、其余适用回归、原生平台及最终交付缺口保持开放。未启动CI、模型或发布。

## 2026-11-07 离线协议91项完成Python3.10–3.13验证

原句柄48456退出0、专属监督器tree_reaped=true。相同91-ID冻结清单在现有独立安装环境Python3.10/3.11/3.13各91项通过，分别15.902/16.151/17.523秒，均无failure/error/skip；加上既有Python3.12的16.618秒证据，完成本子集四版本验证。产品期间未改，适用性沿用三个环境与当前候选151文件一致性证据。protocol-python-matrix的逐版本结果/日志、supervisor及protocol-python-matrix-scope.json保留准确ID、来源和解释器路径。

不把跨版本重复计为不同ID，不提升为完整Python或原生平台验收；91项范围及23项排除仍见protocol-regression-manifest.json。原父期限、3.11三级暂停退出失败及其他回归/平台缺口保持开放，无模型调用、产品修改、CI或发布。

## 2026-11-07 离线协议与收件箱回归91项通过

五模块114项独立审查后选91个缺证据ID，当前Python3.12安装包全部通过、0 failure/error/skip，16.618秒；原句柄22898及监督器退出0、tree_reaped=true。覆盖真实本地监督进程/清理证据校验、收件箱SDK事务与应用自有表原子性、OpenSandbox假客户端边界以及两个零期限identity查询；没有连接外部沙箱或模型。23项因测试直接改SDK表/保护尝试、构造SDK形状的测试库或专门摘要验证而排除，不能标通过。SDK内部正常标识生成不属于新增摘要检查。

原来源/manifest/result/supervisor保存protocol-regression系列；protocol-regression-scope.json补充准确范围，原runner复用的Agent状态描述不准确，原结果不改写，适用性按准确ID/来源及补充范围判断。产品和测试断言未改。三分钟预估偏保守，同类后续本机批次应按本次16.6秒而非固定分钟数校准。静态索引1119/3395，动态1141/3450，2309项无索引证据不等于从未运行；Python其他版本仍需适用范围补验。原期限及3.11暂停退出失败仍开放，不关闭G17/G18。

## 2026-11-07 Agent状态与取消回归46项完成逐项补验

八模块经独立审查，46个尚缺证据ID完成Python3.12安装包补验；三个直接写内部表的方法及Windows专用锁用例保留排除原因。原受限批31项通过、8项通信权限skip、1项错误、6项未执行；结果写出后解释器仍未退出，显式SIGTERM原监督器，exit143且tree_reaped=true，不冒充正常退出。允许本地通信的续批5项通过后，在知识写入/宿主取消竞态遇到旧预期失败，原日志保留。

独立审查确认原默认协作取消窗口允许原本地执行收尾；不能一律要求recovery_required。仅修正该夹具：host cancelled分支必须验证原execution/attempt/fence/lease、准确runtime效果请求、committed及settled响应、真实Kernel终态和结果；其余分支仍要求indeterminate、准确recovery_effect_id及recovery_required。外部Kernel取消、知识已提交/CAS拒绝重放断言均保留。无产品或超时修改。剩余10项通过66.986秒，原句柄80545退出0、tree_reaped=true；包括原权限环境错误项，原错误不抹除、不推定单一根因。

当前候选agent-state-scope-resolution.json逐ID映射三批结果及排除项；冻结source/manifest/日志/supervisor保留。合成适配器及本地SDK/回环通信不计真实模型验收。静态1028/3395、动态1050/3450已有索引通过证据，2400个无索引证据不等于从未执行。仅闭合该46-ID范围，原期限、3.11暂停退出失败及完整回归/平台Gate仍开放。

### 恢复路径矩阵后续结果：原3.11失败仍开放

仅对3.11失败项增加失败清理前线程栈后单项执行，34.821秒通过，原句柄36607退出0；没有触发栈记录，不能解释或修复原15秒join失败，不继续重复该单例。之前未执行的3.13两项续测通过38.658秒，原句柄65623退出0。两监督器tree_reaped=true，原超时及产品均未修改。当前各版本至少各有所选路径通过证据，但3.11原失败仍开放，不将矩阵标为稳定通过。候选split-recovery-python-resolution.json保留原失败、重验与各版准确来源；不新增ID计数，不关闭G17/G18，无模型调用。


## 2026-11-07 恢复路径Python矩阵发现未解决失败

原句柄16553退出1。Python3.10两项通过40.465秒；Python3.11接管项通过，三级进程暂停续接项在原driver.join(15)后线程仍存活，版本总55.422秒。Python3.13未执行。监督器确认专属进程树清理。准确原结果与日志见当前候选split-recovery-python-matrix；保留Python3.12既有通过，但不宣称矩阵通过。已补失败清理前线程栈取证，未改产品及原超时，尚未执行取证版本。R2新增该原始失败，G17/G18仍未完成。

## 2026-11-07 接管与三级进程暂停续接两项补验通过

当前安装包Python3.12的split-recovery-public两项通过，31.585秒，0 failure/error/skip；监督器退出0、tree_reaped=true。覆盖activation lost ACK后接管恢复，以及A→B→C真实进程链暂停、修订、续接和新代次执行。初始状态改用create_run/apply_operations，source_revision=1经共享辅助函数传递；保留原预算、期限、旧权限拒绝和历史事件前缀断言。未修改产品及原等待上限。共享辅助函数默认revision0保持其他消费者行为，独立审查通过。

旧Runtime关闭后再启动新Runtime为本轮之前已有夹具行为，不证明两代重叠存活；宿主授权为模拟，不证明真实writer isolation或OpenCode。两项尚未补齐其他Python版本。准确证据为当前候选split-recovery-public的manifest/result/supervisor、日志及冻结source。动态索引1004/3450、2446个无索引证据；静态982/3395。原始失败不改判，R1、完整R2及G18仍开放。

## 2026-11-07 跨进程接管恢复夹具改用SDK操作，四版本通过

test_split_store_process_adoption 的单个完整路径移除测试直接INSERT及_save/_event：通过create_run、apply_operations建立待决应用状态，保留真实创建/决策事件并核对接管后的完整原事件前缀。源Run由人工revision0改为正常决策后的revision1，adopt/commit/Kernel安装凭据一致传递；旧人工legacy.waiting事件不是本次覆盖对象。共享辅助函数新增keyword-only source_revision=0，本夹具五次Process显式传1，其余调用方默认行为保留；三辅助函数将参数替换回默认0后的AST与原冻结来源一致，不据此声称其他调用方已重跑。独立审查发现并修正了初稿硬编码1会影响其他调用方的问题。

当前安装包Python3.12单项通过6.720秒，Python3.10/3.11/3.13分别7.301/6.634/7.009秒通过，均0 failure/error/skip。原句柄60948/40183退出0、专属子树tree_reaped=true。保留两个原真实进程退出点73/74、丢失ACK后重放、旧worker拒绝、原claims_used/max_claims/deadline、事件/应用状态保留、修订安装及最终独立进程handler执行；不改变原每子进程20秒门限。宿主授权为模拟，不证明真实writer isolation或OpenCode。证据为当前候选process-adoption-public与process-adoption-python-matrix系列、冻结来源及process-adoption-helper-compatibility.json。所用既有环境产品一致性沿用刚核实的151文件证据，期间无产品修改。

此项不替代那33个继承写表夹具，也不关闭原期限间歇失败或G17/G18。动态发现归并现1002/3450个ID有索引通过证据，2448个无该索引证据，不等于从未执行；静态声明索引980/3395。

## 2026-11-07 继承用例22项完成四版本补验

此前实际发现补出的55个继承ID中，两个dispatch-permit子类继承的22项现有当前安装包证据：Python3.12先20项11.662秒通过，再补两项既有脱敏断言0.644秒通过；Python3.10/3.11/3.13各22项，分别11.100/14.274/15.557秒通过，均0 failure/error/skip。原句柄90346、44569、10033退出0，专属监督器tree_reaped=true。其余33项继承直接写SDK表的setup，仍保留未执行，不标不适用。原先因command_digest字段存在性断言排除两项过严：它们没有新增摘要计算或检查，本轮按原测试补验，没有改断言。

当前候选inherited-api/inherited-diagnostic结果、inherited-complete-manifest.json及inherited-python-matrix保存准确ID和逐版本证据。所选模块及基类源与冻结来源一致，三个既有环境的151产品文件逐字节等于当前wheel。现完整发现3450个不同ID中1001个有索引通过证据，2449个无该索引证据；静态声明索引仍979/3395，新增22为继承ID，不能混算。current-discovered-evidence-join.json保留归并，不把未索引解释成从未运行。此为真实SDK控制操作/合成结果，未执行新模型或业务handler；不关闭原期限故障、全量回归或平台Gate。

## 2026-11-07 完整测试发现范围已核实，补出55个继承用例

对当前冻结480个测试模块完成实际 unittest 收集，只枚举、不运行任何测试生命周期。初次13个模块因旧式短名称导入失败，原清单保留 full-current-discovery-initial.json；修正收集器路径后再次收集，0 loader errors，3509个实例、3450个不同ID，59个重复导入实例明确计数。所有3395个AST声明均被找到，另有55个继承用例，涉及CancelResumeRaceTests、CrossStorePauseTests、DispatchPermitTests、RealKernelProjectionIntegrationTests、TakeoverTests，不能继续以静态3395作为完整回归范围。

完整ID、重复数、继承差异、无索引证据ID及来源见当前候选 full-current-discovery.json，入口 collect-current-suite.py、冻结 full-discovery-source（tests/scripts无src）。短模块ID统一tests.前缀以归并同源导入，不合并不同继承类。现979个不同ID有原始索引通过证据，2471个无该索引证据；后者不是从未执行。该收集结果不是安全执行许可、原有测试通过或完整Python矩阵，执行验收测试数为0。导入及构造副作用经独立静态审查后才收集；未调用真实模型、未修改产品或内部表。G17/G18仍未完成。

## 2026-11-07 依赖投递 77 项完成执行范围审查，33 项四版本通过

十个依赖模块的准确 77 项经独立审查：33 项可按目标约束执行，44 项因测试或 helper 直接 DML/DDL（另有一个锁事务 commit 而非 rollback）保留未执行，不能改称通过或不适用。逐 ID selected/excluded 见 /tmp/sdk-delivery-snapshot-20261107/dependency-api-manifest.json；无测试断言或产品修改。33/33 在当前安装包 Python 3.12 通过，6.787 秒，无 failure/error/skip，原句柄 8495 退出 0，专属子树 tree_reaped=true。覆盖真实 SDK 初始化、投递/回执丢失恢复、代次隔离、启动原子性及 mailbox 回滚；host/app 适配器合成，不计新真实模型验收。

同一33-ID 清单在现有隔离安装环境 Python 3.10、3.11、3.13 顺序补验，分别10.033、10.984、10.338秒，全通过，无 failure/error/skip，原句柄54339退出0。三个环境均重新逐字节核对当前 wheel 的151个产品文件；所选七个测试模块执行后与当前源文件相同。dependency-python-matrix/result.json、逐版本 tests.log/result，及 dependency-api-review.json 保存准确来源。没有把跨版本执行重复计为不同用例，也不宣称完整 Python/原生平台矩阵。原父子期限失败、完整回归/44项权限范围和 Windows/ARM 仍开放。

## 2026-11-07 结算夹具差异完成逐项合同处置

独立审查确认旧 later_watermark 夹具手工生成 completion_time_unknown，没有认证监督器决定；后续水位不能授权新的 timed_out Kernel 结果。Goal §99 的底层结算权威及 §103/G16 的 unknown 要求支持保留未知；旧特定终态预期无效，其旧行为仍记未证实，不泛化为所有旧 API 超时路径不适用。已有 runtime-authority-final 三项安装包通过证据及相关 target/helper AST 未变核验，当前 runtime.py 与安装文件逐字节一致，不重复执行。

runtime-settlement-gap-disposition.json 统一处置：实际串行 WAL 超时已补验、真实触发器异常传播已补验、禁止的 Kernel DELETE 修改不列支持构造必测、未认证旧记录不能提升终态。原实际 SDK-table trigger 事务语义及 Kernel DELETE 行为仍未测，不称原整个模块原样等价通过。R3 夹具差异清单完成处置；G17 的一般旧 API/真实认证超时适用范围及原期限间歇失败仍开放。当前静态索引 3395 声明方法、946 个不同 raw pass，非完整动态验收。G18 平台/交付仍缺，无新测试、模型或产品修改。

## 2026-11-07 归档触发器错误传播通过，旧 Kernel DELETE 夹具完成合同处置

当前安装包新增单项 test_cancel_archive_trigger_error_preserves_rejection_cause 通过，1.681 秒，0 failure/error/skip；原句柄 90596 退出 0，supervisor tree_reaped=true。独立内存测试库的真实 UPDATE trigger 生成 SQLite IntegrityError / SQLITE_CONSTRAINT_TRIGGER=1811，归档 UPDATE 代理转发同一个异常对象；原 cancelled→succeeded 拒绝 cause、准确原 receipt 和胜者、业务一次执行均保留，解除故障后正常归档通过。没有修改 SDK schema/行、authorizer 或 journal mode。此覆盖真实触发器异常在归档边界的传播，不覆盖实际安装在 SDK 表上的触发器或其事务行为。冻结来源、入口、result/supervisor 与独立审查为当前候选 trigger-error 系列。

独立合同审查确认：文件型 SQLiteKernel 构造无条件配置并验证 WAL（_sqlite_base.py:152–158，durability.py:70–87），各 durability profile 均如此，只有 :memory: 是 memory journal。原夹具绕过 authorizer 改 Kernel journal_mode=DELETE，不是受支持构造选项，且违反本 Goal 禁止直接改内部数据库的范围，因此不作为必须执行的发布验收项。其 DELETE EXCLUSIVE 读阻塞行为仍明确未测。此结论只适用于 Kernel，不推广到支持其他模式的独立 settlement journal。

R3 的真实串行 WAL 超时已通过；触发器异常传播现通过；原 Kernel DELETE 夹具已作禁止/不适用处置。旧未知完成时间终态预期的合同处置仍待闭合，不据此关闭 G17/G18。

## 2026-11-07 补回真实 Runtime 串行完成采样存储竞争覆盖

新增 test_live_serialized_clock_writer_timeout_cannot_authorize_success，经独立审查后在当前安装包单项通过，6.039 秒，0 failure/error/skip；原句柄 27965 退出 0，supervisor tree_reaped=true。真实 gated handler 经 run_once 返回，原调用参数 serialized=True 和原 work_deadline 完整转发；外部 WAL BEGIN IMMEDIATE 仅持锁并回滚，不修改 SDK 行、保护或 journal mode。实际 SQLite locked 尝试及传入 timeout<=.1 已核验，整个重试消费原工作期限，不把每次 .1 秒误当总期限。原实际 handler 仅一次。

完成时间未知后，通过 public submit 提交 expiry witness 并确认 durable current_time 超过原 lease.expires_at；恢复仍报告准确 identity 的 unknown，原 running/attempt/fence/redelivery=0、pending receipt、原 lease、业务值与原错误保留，无 result/resolved_result，不获得成功结算权。实际证据、冻结测试、结果及监督入口为当前候选 live-serialized-clock 系列，review.json 指向原现场。

R3 中 live serialized WAL writer timeout 覆盖已补回。DELETE rollback-journal EXCLUSIVE 读阻塞、trigger 特定错误及旧终态合同处置仍未闭合；不声称恢复原整个测试等价范围，不关闭 G17/G18。

## 2026-11-07 入口采样竞争已在真实子进程观测，未重现原失败

仅一次原 5 秒父期限诊断，当前安装包 1/1 passed，8.385 秒，0 failure/error/skip，原句柄 53710 退出 0；专属 supervisor 收尾 tree_reaped=true。新增取证只包装测试 worker 内的采样 begin/finish/ack 与 guarded_entry，并将准确 BudgetClockUnknownError.args 分类为 sampling refusal，不调用任意异常的 str，诊断构造/写入错误不替换原异常。独立审查允许一次，原产品/期限/实际 handler 入口断言不变。

现场 /tmp/sdk-inherited-parent-deadline-ttqj0fnk：child worker 663160 共 69 条记录、未达 128 上限，实际观测 6 次 sampling refusal，guarded_entry 最终约 0.151 秒成功，入口预算捕获约 0.140 秒、持久确认约 0.154 秒（嵌套区间不能相加）。这证明采样竞争在该真实父子路径实际发生且本次重试可恢复，不证明它导致原两个失败。parent worker 663151 达到 128 条上限，不能据未记录拒绝排除后续竞争或认定 token 所有者。

结果、逐阶段分析、冻结测试、入口及监督报告保存当前候选 deadline-sampling-stage 系列。本轮不继续重复同一单例；原失败仍开放，尚需失败时的阶段/采样所有者区间才能决定修复点。G17/G18 不关闭，无模型、CI 或产品修改。

## 2026-11-07 原生资源 61-ID 范围续测完成

原 61 项准确清单现各有当前安装包通过证据。原批 45 passed、1 failed、15 未执行；共享期限辅助方法经独立审查修正后，仅执行失败项、15 项未执行及受影响的短期限用例共 17 项。受限环境中 12 passed、5 因 Operation not permitted 跳过，3.063 秒；只为这五项换到允许本地通信的环境补验，5/5 passed，61.612 秒，0 failure/error/skip，原句柄 86491 退出 0，专属子树 tree_reaped=true。没有重跑前 45 项整批。

修正不修改产品：物理 handler 返回仍可能没有结算权。未知分支严格核对原生 abort 操作/receipt 与 invocation、execution、lease、effect、原期限及 attempt/fence=1/1、redelivery=0，并验证待决 late_thread_fact 的完成时间未知、实际恢复报告 unknown、执行状态/结果及身份不变，effect 与待决事实不变；已知分支仍要求实际 recovery_required。原预算、期限、adapter/handler 仅一次及不得重试要求保留。不比较可由独立续租改变的 revision/updated_at/lease expiry。两个共享辅助方法调用均已补验通过，不能称原 61 项全部原样通过。

准确逐 ID 映射及原失败保留边界见 /tmp/sdk-delivery-snapshot-20261107/native-resource-scope-resolution.json；原批、tail、permitted 的 manifest/result/progress/supervisor 及冻结来源同目录。原父子期限间歇失败仍未解释，完整回归与 Windows/ARM 原生矩阵仍缺；G17/G18 不关闭。

## 2026-11-07 原生资源 61 项批次部分完成，修正仍待验证

准确 61 项清单执行 46 项：45 passed、1 failed、15 未执行，273.216 秒，0 error/skip。原失败为 TechnicalRetryTests.test_declared_deadline_expires_after_confirmed_abort_without_retry；现场 handler 已退出，但 late_thread_fact 的 completion_time_known=false，执行仍 running、effect 为 indeterminate。物理退出不授予结算权，不能仅据此要求 recovery_required。独立审查要求未知分支保留准确 execution/lease/attempt/fence、待决事实及恢复 unknown，并绑定原生 abort 操作与原始代次，禁止重试。测试修正尚未完成复验，不计通过，也不称产品已修复。

原结果、逐项记录、冻结测试及 supervisor 报告为 /tmp/sdk-delivery-snapshot-20261107/native-resource-{manifest.json,result.json,progress.jsonl,source,supervisor.json}。监督进程退出 1，原测试后遗留的三个子进程已由其专属子树清理，tree_reaped=true；清理成功不改变失败判定。当前准确索引为 928 个不同 raw pass，不代表全量回归。准备的 17 项续测仅含原失败、15 项未执行及受共享辅助方法修改影响的 2 秒用例；尚未启动。G17/G18 不变。

## 2026-11-07 异常初始化及宿主/工具/服务清理 47 项完成

当前交付快照安装包的准确 47 项、五个完整模块全部通过，80.352 秒，0 failure/error/skip，原句柄 33038 退出 0。范围为 host_teardown_errors 34、initialization_cleanup 5、tool_cleanup_diagnostics 5、tool_startup_ownership 1、service_cleanup 2。覆盖真实本机 socket/HTTP、初始化或注册后失败、关闭错误/中断保留、仍存活 callback/worker 的所有权、固定服务实例占用和释放。适配器为合成，不能计作新增真实 OpenCode 验收。

准确清单、逐项结果/原始输出、独立审查及冻结来源为 /tmp/sdk-delivery-snapshot-20261107/ownership-cleanup-{manifest.json,result.json,progress.jsonl,review.json,source}、ownership-cleanup.log 和 verify-ownership-cleanup.py。独立审查无方法排除：无 SDK 内部表直接 DML/DDL、显式 hash 检查、外部真实模型或嵌套套件。service_cleanup 的内部查询只有 SELECT；实际 openat2/loopback 路径无 skip。构造清理原夹具没有硬超时，未虚构整个批次硬截止。执行后五个模块与当前源码逐文件一致；无产品或断言修改。

两个当前候选目录的成功结果清单已做有界遗漏审计：unindexed-current-results-audit.json / audit-unindexed-current-results.py，仅扫描顶层 *result.json 的 selected 字段，不递归历史、不代替来源有效性审查。新增结果归并后无遗漏 ID；全静态索引为 883 个不同当前 raw pass，3393 声明方法中另有 2510 个无该索引证据。此不等于还有 2510 项确定未运行，不是完整动态发现或 Python/原生平台矩阵。G17 原期限失败及完整范围、G18 平台/最终交付仍未完成；无模型、CI 或发布。

## 2026-11-07 关闭与资源回收 39-ID 范围完成，保留原测试失败及修正边界

当前交付快照安装环境执行 shutdown-api 原准确 39 项清单：27 passed，随后 1 failure，11 未执行，94.689 秒；原结果和日志保留。失败为等待锁竞争测试仅比较异常具体类名，实际 _ControlAdmissionTimeout 是 TimeoutError 子类（errors.py:136）。仅修正测试保存原异常并检查 isinstance TimeoutError，未改产品、.03 等待期限、锁释放前返回、.15 耗时上限、执行一次及恢复清理要求。独立审查认可合同及准确差异；同一辅助方法影响七项测试，显式列为修正夹具范围，不能称 39 项全部原样通过。

仅执行该失败项和原 11 项未执行部分，shutdown-tail 准确 12/12 passed，33.881 秒，0 failure/error/skip，原句柄 19629 已退出 0；没有重复前 27 项。两批合计原 39 个不同 ID 各有通过证据，其中 32 项测试源未改、7 项采用上述审查后的异常继承判断。准确映射、来源限制及原失败路径见 /tmp/sdk-delivery-snapshot-20261107/shutdown-scope-resolution.json；manifest、progress、结果、日志及冻结源码同目录 shutdown-api / shutdown-tail 系列。

父进程导入当前安装包；测试专用冻结根只有 tests/scripts、没有 src，启动清除继承 PYTHONPATH 并使用干净工作目录，避免子进程夹具 prepend 源码目录时导入产品源码。此不冒充对每个子进程 import origin 的单独断言。所选路径为真实本地 SDK、锁及合成适配器，不是新真实模型验收；未直接写 SDK 内部表、未启动 CI。完整回归及原父子期限间歇失败仍开放。

另修复证据索引解析错误：原 unittest FAIL 括号已含完整方法名，旧解析重复追加方法名；现在准确排除原 arbitration 批失败 ID，后续独立前缀通过仍按其来源保留。failure-index-correction.json 证明失败未被关闭。完整静态索引现为 480 模块、3393 声明方法中 836 个不同当前 raw pass；这仍非全量动态发现或完整矩阵。

## 2026-11-07 子进程入口阶段取证已实际接通，未关闭间歇失败

新增测试专用、默认关闭的 DISPATCHER_TEST_WORKER_ENTRY_EVIDENCE=1 入口。ProbedHandler 仅在真实 POSIX worker 反序列化时安装阶段包装，然后返回原 handler；不修改 SDK 产品、期限或断言，不使用宿主继承锁，不访问 SDK 内部表。独立只读审查允许一次诊断，并明确同步旁路文件 I/O 会增加开销，128 条上限、部分写入或丢失事件只能判 unknown。

当前安装包准确单项执行 1/1 passed，8.769 秒，0 error/skip；原句柄 54573 已退出 0。结果 deadline-worker-stage-result.json、分析 deadline-worker-stage-analysis.json、冻结测试 deadline-worker-stage-source 和入口 verify-deadline-worker-stage.py 位于 settlement-startup 候选目录。现场 /tmp/sdk-inherited-parent-deadline-sfj0z3ft/evidence.json；两个 worker 各保留 15 条连续阶段记录、未到上限，已记录 begin 均有 end，且原 actual-entry、继承期限和清理断言通过。child worker 的观测初始化约 0.00076 秒，入口预算捕获约 0.165 秒，_enter_handler 约 0.233 秒，随后持久入口确认约 0.083 秒。嵌套区间不能相加当作总耗时。

这证明跨 spawn/反序列化的 worker 取证实际可用，不证明历史失败发生在这些阶段，也不证明已修复；原失败与 G17/G18 状态不变。不继续无新假设重复此单项。原失败 ready 宿主回调不足 1 毫秒的只读排除证据另见 original-ready-callback-audit.json。

## 当前统一判定（settlement-startup 候选）

当前产品候选为 `/tmp/sdk-settlement-startup-candidate-20261107`，版本 0.8.0.dev1。工作树的 151 个打包产品文件与该 wheel 逐字节相同；当前源码/测试/文档的本机交付快照为 `/tmp/sdk-delivery-snapshot-20261107`：sdist 构建 wheel、干净环境离线安装、151 产品文件及元数据与原候选一致；完整回归和平台缺项尚未闭合，不能称最终交付。机器可读证据索引为同目录 `functional-current-acceptance.json`，复查组装入口 `assemble-functional-acceptance.py`。该索引只组装已核对的事实和影响评估，不执行或冒充新的 native 场景。

| 范围 | 当前判定 | 证明边界 |
| --- | --- | --- |
| G01–G16（G13 例外见下一行） | passed，功能最低合同 | 当前 G05 图、G06 组合及按 Goal §5 保留的适用历史报告；来源、原始状态与限制逐 Gate 写入 JSON 索引。 |
| G13 | passed，能力合同及拒绝路径 | 未提供原生 strict 后端，真实强隔离未验收。 |
| G17 | failed / 未完成 | 期限间歇失败保留；完整旧 API 范围尚未闭合，remaining-api 范围已核对：327 个原用例通过，1 个旧权限预期经审查替换并通过；父子期限间歇失败及完整回归缺口仍在。 |
| G18 | blocked / 未完成 | 缺完整 Windows/ARM 原生平台证据；最终归档、文档及全量回归一致性尚待完成。 |

独立 reviewer `legacy_expiry_review` 对 G02/03/04/07/09/11/12/16 及 v2 的 G08/10/15 完成有限产品差异适用性复核。sampling-cause 至当前全部 44 个 Agent 产品文件相同；v2 至当前仅四个 Kernel 文件变化，范围为已认证入口发布、已捕获完成事实的竞争准入和初始化失败拒绝。当前真实图与变更分支安装包测试作为相应差异的支持证据，不取代各历史负例。G14 与 G06 已分别独立复核；G01 配置矩阵及当前默认值另有核验。

v2 原生报告实际使用 `/tmp/sdk-entry-retry-candidate-20261106/env`，不是 v2 命名目录中的解释器；原 v2/parity.json 明确指向该 alias wheel，原组合验证器也核对该路径。现回读再次确认 v2 wheel、alias wheel 及其安装的 151 产品文件逐字节相同；这不是不可变历史来源证明。G10 准确文件是 `.../sdk-entry-wrapped-admission-v2-G10-native-20261106/G10.json` 与 acceptance.json，没有 report.json。原 G09 错误断言、G06 not_run/旧歧义 failed、代理清理失败及 G17 间歇失败均保留，未被此表抹除。

整体 Goal 未完成、未推送、未发布。后续记录保留各阶段原始时间和候选边界，不应把其中“当前”一词当作覆盖本表的新判定。



## 2026-11-07 新增 174 个不同用例通过，155 项覆盖四个 Python 版本

当前源码归档安装包 `/tmp/sdk-delivery-snapshot-20261107`：portable-api-result.json 证明准确 155 个经审查 ID 全部通过、0 failure/error/skip，26.745 秒；linux-native-api-result.json 另证明准确 19 个 Linux 特有 ID 全部通过、0 skip，1.092 秒。后者包括 openat2、真实 fork、维护锁参与及本地 bootstrap 诊断，不是 OpenCode 模型验收。portable-api-safety-review.json 保存独立审查边界：无直接内部库写入、显式 hash 检查、外部真实模型或嵌套套件。测试的模拟验证器故意打印 G03/G04/G05/G06 failed/not_run，不改变真实 Gate 报告。执行后逐模块核对当前测试与冻结源码一致。

同一 155-ID 清单在三个独立干净 venv、当前 wheel 和本地各版本 PyYAML 6.0.3 下继续顺序执行：Python 3.10.22 全通过 28.427 秒，3.11.18 全通过 29.385 秒，3.13.18 全通过 28.893 秒；结合 3.12.3 原批，各版本无 failure/error/skip。portable-python-matrix/result.json / validation.json、逐版本 tests.log/install.log、verify-portable-python-matrix.py 可复查。三版本逐一核对 151 安装产品文件与冻结源码一致、venv 不继承系统包、用户 site 禁用。安装使用 --no-index/本地 find-links 的 wheel[agents] 正常解析，没有 --no-deps，因此证明该本地依赖集合的离线解析安装；不推断外网安装或其他 extras。

本轮新增 174 个不同 raw pass ID（同一用例跨 Python 不重复计数），整体索引为 797 个。此仅是 3393 声明方法中已索引的部分，不代表完整测试数或整个 G17/G18 已通过。完整回归、原期限间歇失败、临时库夹具范围澄清以及 Windows/ARM 原生矩阵仍未闭合；没有模型、CI、产品变更或发布。

## 2026-11-07 期限原前序上下文未重现；当前启动夹具补验通过

当前安装包按原 arbitration 清单顺序执行到继承父期限用例的准确 31-ID 前缀，全部通过、0 error/skip，49.368 秒。deadline-original-prefix-{manifest,result,analysis}.json、日志、冻结 source 和 verify-deadline-original-prefix.py 保存于 settlement-startup 候选目录。目标现场 `/tmp/sdk-inherited-parent-deadline-q_2_ao97/evidence.json` 保留 55 条宿主阶段事件、0 截断；前 30 项结果边界观察到的本进程线程均仅 MainThread。此仅说明本次原前序序列不足以触发失败，不排除间歇顺序影响、未观测 worker/process 遗留、宿主资源或 ready 至 entry 的等待；原两个失败不关闭。不继续无变化重复前缀或单例。

当前源码归档安装包的 startup-current-result.json 另证明改过的 RuntimeSettlementInitializationTests 单项通过，真实验证缺结算存储时 claim 未被调用、原初始化异常 cause 保留、状态/attempt/fence 不变；关闭并重开后同一任务执行一次成功。使用当前 fixture 在原 30 秒内观察同一结果，没有再次调用 handler；此前该 fixture 与原冻结测试不同，未借旧 pass 填数。准确日志与 verify-startup-current.py 在 `/tmp/sdk-delivery-snapshot-20261107`。

G17 的期限失败原因及完整回归、G18 原生平台/最终审查仍未完成。有关原有一次性测试库夹具的范围澄清仍无回复；未执行那些内部表直接写入用例。无产品修改、模型、CI 或发布。

## 2026-11-07 新增 Agent API 回归 117 项通过，保留平台和夹具边界

`/tmp/sdk-delivery-snapshot-20261107/agents-api-result.json`：18 个模块、117 项准确 ID 全部通过，0 failure/error/skip，518.128 秒。实际来源为新源码归档构建的 wheel 在干净环境中的安装；151 产品文件与原 settlement-startup 候选一致。selected 模块结束后与冻结源码逐文件比较仍一致；manifest、逐项 progress.jsonl、日志、verify-agents-api.py 及 agents-api-review.json 保存同目录。覆盖绑定、文件权限、goal、OpenCode 协议、reasoning/fallback、工具入口、工作区、服务/实例、任务实例、触发器、监督和资源准入。部分使用真实 SDK/loopback，模型适配器或上游协议为合成/模拟，不计新增真实 OpenCode 验收，也不替代 G01–G16 的真实来源。

独立安全审查未发现所选调用路径直接修改内部数据库、运行 hash 检查、外部模型/服务或嵌套测试套件。三个 WindowsWorkspaceTests 留待 Windows 原生，未在 Linux 靠 skip 填数。knowledge 模块以及其他原始内部库直接写入夹具未执行；已询问用户原有一次性临时库夹具是否属于“不直接改 SDK 内部数据库”的禁止范围，尚无回复，不推断许可。

另外原已成功批次有 8 个当前测试源与执行时冻结源完全一致的 ID，此轮只补索引、不重跑；启动初始化测试的当前 fixture 不同，保留待执行，不借旧报告填数。全部 480 模块/3393 声明方法的准确当前 raw pass 索引现为 622 个；这不代表只运行过 622 个、不等于完整动态发现，更不关闭原间歇失败。G17 的完整回归/期限原因、G18 的 Windows/ARM 原生矩阵及最终审查仍开放，无 CI、模型或发布操作。

## 2026-11-07 当前本机交付快照与双语示例验证通过

`/tmp/sdk-delivery-snapshot-20261107/delivery-validation.json` 汇总本轮实际结果。807 个 tracked / nonignored untracked 常规工作树文件复制到独立 source；从该源码归档构建 wheel，在不继承 system-site-packages 的 Python 3.12 venv 中 --no-index/--no-deps 安装该 wheel 及本地 PyYAML 6.0.3。151 产品文件在快照、新 wheel、原 settlement-startup wheel 及新安装目录逐字节一致；METADATA / entry_points 与原 wheel、新安装一致。归档中的 docs/tests/examples/wiki/scripts 与快照一致；verify-snapshot-provenance.py 在本报告更新前核对全部 807 文件及文件清单与工作树相等。此为逐文件工作树快照，不是原子 commit；本节验收记录更新发生在快照之后，最终交付仍需检查报告与制品边界，不循环假称它已包含自身报告。

新环境运行冻结 scripts/check_docs.py 退出 0：591 本地链接有效、双语 README 四个真实示例全部通过且无跳过，详细指南及中英文 Wiki 三份完整默认值注册表与实际安装 ApplicationSpec 一致。typing-check.log 证明通过 --python-executable 指向新环境、Python 3.10 类型合同的六份公开消费者全部通过。25 页 Wiki 从冻结来源导出至同目录 wiki-export；ref release/0.8.0 仅本地引用，未验证远程可访问、未推送。

独立只读制品审查认可本机范围，且明确 --no-deps 离线安装不证明依赖解析，不证明完整 SDK / Python / OS / 架构矩阵。原 README 间歇失败仍保留；本次通过不能解释其历史原因。G17 期限间歇失败/完整回归与 G18 Windows/ARM 原生矩阵、最终审查和交付仍未完成。本轮没有产品修改、真实模型请求或 CI。

## 2026-11-07 父子期限：增加有界宿主调用阶段证据，根因仍未确认

仅测试辅助代码新增 ChildService 执行/attach/等待父入口、Runtime 子提交/run_once/recover/诊断/准入以及 Kernel claim 的内存 begin/end 记录，最多 512 条，包含线程、进程、execution identity 和截断计数。不持证据锁调用 SDK，不在执行途中写文件；原 5 秒父期限、30 秒子期限、12 秒返回门限及全部入口/结果/清理断言不变。独立审查指出初稿 class patch 在 fork worker 中可能获取继承锁，已修正为非宿主 PID 在任何事件分配或取锁前直接调用原方法；初稿通过仅作为历史证据保留，不据此排除此风险。

修正后当前安装包单项通过 8.804 秒，deadline-host-boundary-result.json；真实 child 进入，保留 56 条宿主事件、0 截断，原始现场 `/tmp/sdk-inherited-parent-deadline-7km0ly6a/evidence.json`。冻结入口 verify-deadline-host-boundary.py / deadline-host-boundary-source/tests。独立审查确认 PID guard 和截断报告修正，无该取证范围阻塞。只读可复查分析 analyze-deadline-host-boundaries.py / deadline-host-boundary-analysis.json 同时保留前一草稿 probe 8.552 秒，其有两次真实 child claim 失败后重试及多段诊断等待。

这些通过仅证明新取证入口可用，不能解释原两个失败。仍缺失败当次宿主调用边界及 parent worker enqueue、service pickup 和 native worker ready 至实际 entry 的内部等待归因；计时辅助有宿主开销，不宣称零扰动。没有产品补丁、不重跑无变化的单例、不将原失败关闭；G17 failed、G18 blocked 仍保持。本轮无模型、CI、SDK 内部行直接写入或发布。

## 2026-11-07 结算存储竞争夹具纠正：窄范围通过，原实时路径缺口保留

当前安装包单项 `test_unprotected_clock_storage_timeout_cannot_authorize_expired_success` 通过，0.591 秒，结果及冻结入口为当前候选 runtime-storage-timeout-result.json / verify-runtime-storage-timeout.py / runtime-storage-timeout-source/tests。真实 handler 仅执行一次；外部 WAL BEGIN IMMEDIATE 只制造锁竞争并回滚，不修改 SDK 行、authorizer 或 journal mode。原捕获 .25 秒上限与 proof .1 秒不变。原始数据库锁错误及 proof 保留；通过正常 submit 提交超出租约的时钟 witness 后，实际恢复仍为 unknown，原 attempt/fence、pending、业务值与预算不变，无 result/resolved_result。

独立只读审查无该窄范围阻塞，runtime-storage-timeout-review.json。此用例替换的是不符合当前权限合同及数据库保护的旧夹具；不证明原 gated live serialized adapter 在存储超时下的行为，不覆盖 DELETE rollback-journal 的 EXCLUSIVE 读阻塞，也不恢复旧 superseded/timed_out 终态断言。这些差异显式保留为覆盖缺口。因此当前 24 个声明用例虽各有当前包单项或分批通过证据，不能声称原模块范围完整等价通过，更不能关闭 G17。原触发器专属覆盖缺口也仍在。

另一次只读期限路径审查确认两个历史失败均到 worker_ready、未到真实 handler entry，结果为继承原期限的 admission timeout；保留证据不能定位提交/领取/启动及 ready 至 entry 的耗时原因。没有新增产品修复或重跑该间歇用例。本轮无模型或 CI，G17/G18 未完成。

## 2026-11-07 结算模块范围审查及原门控自锁纠正

当前源码静态清单已扩展为全部 480 个顶层 test 模块、3393 个声明方法，不冒充动态发现或完整执行。all-current-regression-coverage.json / index-all-current-regression.py 将准确当前安装包原始通过证据按 ID 索引，未索引不等于从未运行；原 184 模块只是一份旧基线范围，不能代替全部当前测试。

runtime_settlement 的 18 项经独立审查安全范围，首批在第 2 项 wrote=0 停止；GateCleanup 已通过，原报告保留。余下 16 项在同一安装包全部通过（31.782 秒），runtime-settlement-safe-tail-result.json，不重新执行 GateCleanup。原诊断的 _read_floor 注入已不属于实时 serialized 返回入口，改为明确未保护的真实 handler/lease/Context 捕获负例；首个迁移草稿在读连接 BEGIN IMMEDIATE 后插入竞争写导致等待 30 秒而 wrote=0，原错误保留，改在 _connect_reservation 前、原 sample 后提交真实时钟 witness，避免夹具自锁，不改产品锁或预算。

watermark rollback 旧包装器未接受 serialized 参数，先产生 TypeError；修正透传后发现旧 park_monitor 在持有 completion_gate 时等待需要同一把锁的完成发布，必定等满原 3 秒。这是夹具自锁，不是产品死锁。暂停点改为仅 driver 线程的精确运行时代码 call trace：retain_live_handler_expiry 入口在 gate 释放后，检查实际 context/view 身份及 gate 未持有；原 trace finally 恢复、原门限不变。实际返回由 serialized 捕获准确拒绝为 StaleFenceError: lease has expired，保留 pending/unknown、同代次、无结果和一次业务调用，不误报 original-floor-unproven。最终两项 2/2 通过、1.623 秒，runtime-monitor-final-result.json，独立审查无具体阻塞。

永久 SQLite 错误夹具移除直接创建 SDK 表 TEMP trigger，改为在 SDK archive UPDATE 调用点用只读 SELECT 整数溢出产生真实永久 SQLite 错误，验证原拒绝 cause、原回执及取消胜出者保持、之后正常归档；单项通过 1.599 秒，runtime-permanent-error-readonly-result.json。这不覆盖原 trigger-specific IntegrityError，也不证明 UPDATE 本体被执行，该覆盖缺口明确保留。

组合 runtime-settlement-current-coverage.json 核对当前 24 个声明用例中 23 个有当前安装包通过证据；另 1 个 storage-timeout 用例仍因解除 authorizer/修改 journal mode 及旧 unknown 预期待纠正，未执行。不能称整个模块或 G17 全部通过。本轮无产品代码修改、内部表直接修改、真实模型或 CI；G17 父子期限间歇失败及完整剩余范围、G18 平台/最终交付仍开放。

## 2026-11-07 父子期限失败：确认早期取证缺失，补齐有界前缀

只读对照两个原失败：子任务 submitted 至 leased 分别 1.894/1.083 秒；parent native 至 child native 为 4.209/3.779 秒；child 原启动窗口仅余 1.207/1.649 秒，均无实际 child entry。原 SQL ring 仅 2048 条，原返回快照起点均晚于关键早期阶段，没有完整调用/等待归因，不能以已保留的短 SQL 耗时宣称存储或控制锁无问题。

测试辅助 StorageEvidence 增加最多 4096 条 early_sql_operations，与原 tail/slow 记录并存，不在捕获时写文件、不改预算/时限/断言。仅补证一次原用例，当前安装包 1/1 通过，8.218 秒，真实 child 已进入；证据 `/tmp/sdk-inherited-parent-deadline-w6u2hld0`，可复查 deadline-early-prefix-{result,analysis}.json 及 verify-deadline-early-prefix.py、冻结 deadline-early-source/tests。此次 submit 至 lease 0.561 秒、native 间隔 1.726 秒、启动余量 3.671 秒；不能由单次通过解释历史失败或宣布修复。原失败、准确原期限不变；不继续无变化重复探测。后续真正失败仍需有界前缀和领取/提交边界或阻塞线程栈，当前 G17 失败仍在，G18 仍缺平台/最终交付证据。本轮无产品代码、真实模型或 CI 调用。

## 2026-11-07 三个旧恢复夹具按当前权限合同纠正

独立审查定位 runtime_settlement 的三个消费者仍期待 journal-only completion_time_unknown 被恢复成业务决策。保留其真实执行和原不变量，分别纠正：后续 watermark 只能保留原错误/原 proof/原预算为 unknown，不能补造完成时间；日志丢失 ACK 的 reopen 正例改用实际线程 handler 和实际 Kernel 已提交结果，再关闭/重开核对同一结果与一次业务执行；读连接物理 close 失败用原 proof 直接调用 resolver、Runtime 作 owner，验证保留唯一连接、拒绝第二连接、无关 Context 清理不能抹除 owner、Runtime 关闭必须重试，物理关闭后 SQLite 实际不可用。后者不再声称当前恢复器会为未认证旧记录创建读连接，原 journal 仍 pending/unknown。

当前安装包三个最终用例同批 3/3 通过、2.388 秒，runtime-authority-final-result.json；冻结测试、复查入口和独立审查映射分别为 runtime-unknown-source/tests、verify-runtime-authority-final.py、runtime-authority-review.json。首个 reopen 草稿仍 patch 已移除 runtime.resolve_completion_time 导致 AttributeError，原报告保留，已修正到实际模块；导出函数 patch 不能单独证明所有时钟采样路径都不存在。线程已提交结果恢复与前段 supervisor pre_spawn 重试正例分别成立，不相互冒充。本轮没有产品代码变更、内部数据库直接修改、hash 检查、真实模型或 CI 调用。G17/G18 仍未完成。

## 2026-11-07 01:44 CST 恢复权限用例纠正与剩余范围闭合

独立审查确认原 unknown-time 用例不具备可信完成时间或已提交宿主决策，ACK budget sample 和 journal pre_spawn 标记不能授权 queued 重试。仅修改测试为同一 running attempt/fence、pending 证据、无 resolved_result、unresolved obligation 和明确 unknown 报告；产品权限逻辑未改变。另增真实 native pre_spawn 已知时间路径的正例：Kernel 实际提交后丢失 journal recorded ACK，核对原 identity、无 deferred、准确结果 ID 和 sdk_supervisor_not_invoked 来源，恢复日志后再领取下一 attempt，后续恢复不改变新代次。此正例不证明“新代次已经运行时恢复仍 pending 的旧回执”。最终三个相关用例在当前安装包全部通过，3.085 秒，cleanup-authority-final-result.json；早期正例草稿错误保留。

最后 11 项入口首次缺 __main__ 保护，真实 spawn 子进程重复执行测试，导致第 5 项清理检查失败；原日志和结果 remaining-api-last11-* 保留。纠正入口只补该受影响项与余下 6 项，remaining-api-last7-fixed-result.json 为 7/7 通过、7.355 秒。连同该入口前四个通过和原 316 项，共 327 个原 ID 通过；另一个原 ID 为上述审查后替换的旧断言，不能说原 328 项原样全绿。准确组合索引 remaining-api-scope-resolution.json。全部产品仍为同一安装包，无模型或 CI 调用。

G17 仍未完成：继承父期限的间歇失败、其他旧 API 范围及审查指出的其他旧 completion_time_unknown fixture 适用性尚须处理；本批范围闭合不代表全套通过。G18 平台及最终交付证据仍缺。

## 2026-11-07 01:37 CST 按时检查：恢复证明失败，停止无修改重跑

原句柄 75782 已退出 1。211 项续跑清单实际执行 200 项：199 通过、1 failure、0 error/skip，254.811 秒；与原首批 117 个准确 passed ID 合并为 316 项通过、1 项失败、11 项未执行。原 loader error 仍保留。失败为 `tests.test_supervisor_cleanup_scan.SupervisorCleanupScanTests.test_unknown_completion_time_retains_pre_spawn_proof_for_replay`，第 133 行预期 queued，实际 running；恢复报告反复为 `original completion authority is unconfirmed`。原完整日志、结果与准确待执行 ID 见当前候选 remaining-api-tail-* 及 remaining-api-combined-progress.json。不以重跑单次成功关闭此失败。

独立于该批次，ApplicationBudget 12 项经逐方法审查，5 项直接修改内部表未执行，7 项公共接口/SELECT-only 测试在当前安装包全部通过（1.807 秒）。选择理由、冻结测试及复查入口为 application-budget-safe-scope-review.json、budget-safe-source、verify-budget-safe.py；结果 budget-safe-result.json。未调用模型或 CI。G17 仍失败，G18 仍阻塞。

## 2026-11-07 首批剩余回归 117 通过；加载路径修正后续跑

按原计划 17:30:48 UTC 后检查，原句柄 78426 已退出 1。原 328 项选择中执行 118 项：117 通过、0 failure、1 loader error、0 skip，122.875 秒。准确错误为 test_lifecycle_outbox_multiprocess 的非限定 helper 导入 `test_execution_kernel_v2_sqlite` 找不到；不是 SDK 业务失败。原 remaining-api-result.json/log/progress.jsonl 保留，不改判整批通过。

新入口 verify-remaining-api-tail.py 同时加入冻结 tests 目录和包根路径，先检查全量 loader 错误，再执行原清单扣除 117 个准确 passed ID 后的部分；不重新执行已通过项目。续跑句柄 75782，remaining-api-tail-{manifest.json,log,result.json,progress.jsonl}。预计 4–7 分钟，首查五分钟后；准确 UTC 检查时间见 remaining-api-tail-observation-schedule.json，不提前刷新或因观察超时重启。

packaging 的三项源码边界测试已解除夹具缺项：151 个产品文件直接从当前 wheel 提取，metadata 使用原候选 pyproject 且与工作树一致，测试在对应冻结根目录扫描实际包内容；SDK 导入保持 installed 路径。三项原测试全通过 2.414 秒，独立复核认可该静态范围，packaging-source-provenance.json 及 packaging-source-result.json 保留。不是运行时、依赖解析或平台验收。

## 2026-11-07 剩余旧 API 清单化执行与 G01 配置矩阵适用性

当前回归范围已按基线 184 模块的静态方法 ID 整理并与当前已执行 ID 去重：`/tmp/sdk-settlement-startup-candidate-20261107/legacy-remaining-triage.json`。独立审查批准其中 54 个无初筛标记模块的准确 ID，另明确排除 packaging（需要来源正确的源码夹具）、sqlite_contention（benchmark 计算实现 SHA256，容量夹具绕过 authorizer）及 storage_snapshots（实际快照/HMAC/SHA256 验证）；这三组保留待验收，不能标 passed 或 N/A。达到的 helper 路径已审查；允许仅回滚的锁事务，不允许直接 SDK 表 SQL 修改。Windows 专属预算用例留待原生 Windows，不在 Linux 上靠 skip 填数。

按上述准确选择启动同一当前安装包的 remaining-api 批次，句柄 78426，入口 `/tmp/sdk-settlement-startup-candidate-20261107/verify-remaining-api.py`，清单/日志/最终结果同目录 remaining-api-{manifest.json,log,result.json}。首个失败停止，不改原断言和期限，不调用模型。预计 8–12 分钟；首次检查不早于 2026-11-06 17:30:48 UTC（北京时间 11 月 7 日 01:30:48），计划保存在 remaining-api-observation-schedule.json。未到检查点不刷新、不重启。此为执行中记录，不计通过。

G01 原配置矩阵证据已核实可保留用于当前候选：sampling-cause 与当前 44 个 Agent 产品 Python 文件完全相同；Python 3.10/3.11/3.12/3.13 各 18 项 spec/null/default/validation 测试原报告全部通过，当前安装包三份文档默认值另已对照一致。准确来源及局限见 `/tmp/sdk-settlement-startup-candidate-20261107/G01-current-applicability.json`。这些是保留原包来源的配置层证据，不是完整 SDK 或 Windows/ARM 矩阵，不重新运行无变化的配置用例。

## 2026-11-07 新增 39 项投递/编排/脚本回归；双语状态同步

同一 settlement-startup 安装包新增 39 项选定回归全部通过，40.053 秒，0 failure/error/skip，准确安装来源及完整范围见 `/tmp/sdk-settlement-startup-candidate-20261107/delivery-api-{result,manifest}.json`，原始输出 delivery-api.log、包外复查入口 verify-delivery-api.py，冻结测试与支持文件位于 delivery-source/tests。覆盖结果投递、编排器、宿主以及由 SDK 实际监督的本地 Python 脚本；宿主部分用例为合成对象的旧 API 单元测试，不计真实 Agent 宿主证据。与当前 73 项和前批 25 项按准确 ID 去重，未重复计入。显式 sha256 断言用例仍保守排除并列在 manifest，不算通过或不适用。主审和独立安全审查确认该选择无直接 SDK 内部 SQL 修改、无嵌套全套/构建/模型调用。

英文指南及中英文 Wiki 首段已同步当前实验状态，去除将早期“完整多 Agent 功能未实现”继续写成当前能力的陈旧描述；observation-reads 的 69/74 记录明确标为历史，原失败证据保留。使用当前安装包 ApplicationSpec 对照三份完整默认值 JSON 一致；89 份本地文档 589 条链接无缺失，`/tmp/sdk-settlement-startup-candidate-20261107/doc-links-defaults-result.json`。该检查不重跑 README 示例或检查远程 URL。25 页 Wiki 本地导出 `/tmp/sdk-settlement-startup-wiki-20261107`；ref 为本地 release/0.8.0，未验证远程链接存在，未推送或发布。

期限测试取证代码的 SQLite 包装仅围绕原操作记录时间；栈采样及文件快照在 run_once 返回后进行。静态检查未发现足以证明启动超时根因的新增等待，不能据此关闭间歇失败。G17 完整回归与该原因、G18 平台矩阵及最终候选归档仍未完成，当前无活动测试或模型进程。

## 2026-11-07 当前安装包新增 25 项旧 API 回归通过；G14 适用性确认

当前 settlement-startup 安装包的任务提交/通知选定 25 项全部通过，24.579 秒，0 failure/error/skip；准确安装来源、选择范围、原始日志分别为 `/tmp/sdk-settlement-startup-candidate-20261107/public-api-{result,manifest}.json` 和 public-api.log，可复查入口 verify-public-api.py。测试文件冻结在 public-api-source/tests；独立安全审查与主审确认无直接 SDK 表 SQL 写入、新增制品散列检查、嵌套全套测试/构建/模型请求。通知模块的一项 BEGIN IMMEDIATE 夹具保守排除，仍属待验收范围，不标不适用。该 25 项不是完整旧 API 回归。

G14 的 A/B/C/D 原故障窗口已按当前产品差异完成独立适用性复核；`/tmp/sdk-settlement-startup-candidate-20261107/G14-current-applicability.json` 记录当前功能最低合同可保留原 passed 证据。原窗口不在新的入口发布/完成决定竞争内部，当前安装包完整协作图、变更分支回归及初始化保护测试满足前次影响评估条件。原候选来源及原报告不变，不声称在当前包重跑真实崩溃，不覆盖新竞争点内部崩溃或独立 OS 清理证明。Goal §5 允许此类未受影响证据复用。

G17、G18 仍未完成，当前无活动回归或模型进程。

## 2026-11-07 G17 期限诊断与回归覆盖整理

对当前安装包补采原 5 秒父期限的两个单例均通过，原始记录为 `/tmp/sdk-settlement-startup-candidate-20261107/child-diagnostic-{target,claims}-result.json`。实际类名为 InProcessRuntime；按方法后缀读取原始事件可关联领取记录的 append、journal durable note、ACK 与返回。两个 child 领取记录耗时分别约 0.133/0.206 秒，ACK 后尾部均不足 1 毫秒，不支持“目标已确认后继续排空造成显著延迟”的推测。没有据此修改产品；原 73 项中的失败及此前失败现场仍开放。这两次通过不是修复证明，不继续无修改重复该单例。

可复查因果摘要：`/tmp/sdk-settlement-startup-candidate-20261107/child-diagnostic-causal-review.json`。仅两组旧回归目录的显式 unittest 日志索引，`legacy-historical-outcome-index.json`，在基线 184 模块/1692 个静态声明方法中找到 746 个历史显式 ok；其余 946 项仅表示这两个目录没有显式 ok，不表示从未执行，也不表示当前包已有 746 项有效验收。后续定向批次另计，保留原包来源和当前适用性审查要求。该索引用于避免重复运行和确定缺项，不改变验收标准。

## 2026-11-07 G06 最低合同完成核验

当前候选 `/tmp/sdk-settlement-startup-candidate-20261107` 的 G06 最低合同通过独立复核。结论来自当前安装包真实多轮图及按 Goal §5 保留的适用负例，不表示所有负例在新包重新执行。当前仍未完成的整项为 G17、G18；其他 Gate 的最终制品适用性和最终交付一致性仍须完成汇总，不能据此宣布 Goal 完成。

- 当前真实图：`/tmp/sdk-settlement-startup-G05-G06-native-20261107`。两轮各两个 coder、reviewer 实际消费新结果、关闭组、另一个 Run 的结果隔离及未关闭组拒绝均通过；8 个 Agent 全部 succeeded。主 Run 7 次 Agent/43 次模型轮次，独立 Run 1 次/5 次；原预算未更改。adapter 执行区间重叠不证明同时模型推理。
- 准确清理：只读关联 8 个原生 operation 的 invocation/execution/lease/attempt/fence/effect/deadline，均匹配 cleaned 收据、tree_cleanup=confirmed、committed runtime effect 和 succeeded Kernel generation。期限与原约束一致。宿主关闭由成功返回经过 AgentApp.__exit__/close 的控制流证明；不声称独立 OS 进程树检查。
- 保留负例：`/tmp/sdk-return-admission-g06-selected-20261106/report.json` 及 missing_reference、group_required_output 的原始 case.json 两项通过；歧义使用 `/tmp/sdk-entry-publication-candidate-20261106/G06-ambiguity-retained-supplement.json` 的限定拒绝事实。原歧义 failed 保留，子模型响应未证明；不是当前 wheel 的负例重跑。
- 适用性：entry-publication 至当前候选 44 个 Agent 产品文件逐字节相同；更早 return-admission 差异仅 token_budget.py，所保留负例无 token 上限。Kernel 修改另由当前完整图及变更路径测试覆盖，不据 Agent 文件相同宣称 Kernel 无变更。
- 可复查组合报告：`/tmp/sdk-settlement-startup-G05-G06-native-20261107/G06-combined-minimum.json`；只读重算命令 `python3 /tmp/verify-g06-combined-20261107.py`。独立 reviewer `legacy_expiry_review` 确认该限定最低范围无具体阻塞。原 G06.json/acceptance.json 的 not_run、原进程退出码 1 均保持，不改写为单次完整通过。

G17：最新安装包选定 73 项回归为 72 passed/1 failed；继承父期限的真实 child 未进入处理器，后续相同原预算的诊断单例虽通过，原间歇失败原因仍未解释，不关闭该缺口。完整旧 API 回归覆盖尚未汇总闭合。

G18：完整 Python/OS/架构矩阵仍缺 Windows 和 ARM 原生证据；六项启动保护的局部 Python 矩阵不是完整平台验收。最终 sdist/文档快照须在代码与文档稳定后统一刷新，未推送、发布或运行 CI。本轮核验无模型调用、无 SDK 数据库写入。

## 2026-11-07 初始化失败保护补丁

00:54 CST按约首查新图句柄90082仍live、无最终报告。只读progress-0054.json确认planner/isolated、首轮2coder/reviewer、第二轮2coder/reviewer共8个Agent行全部succeeded，两个group均closed。已实际越过旧图第二轮成功candidate未提交的位置；仍须等待验证器完整断言、准确native清理及退出，不据中间状态宣布G06通过。下一预计2–3分钟后检查，不重启或修改原3600秒预算。

3.11修正异步观察断言的单项重验句柄57609退出0，1项通过2.469秒、0error/skip，py311/corrected-result.json；原六项5/6失败原样保留，不混称同批六项通过。原保留数据库已确认首次实际结果succeeded/recorded。后续源码另加remaining<=0提前退出，避免while检查与计算之间的微小时差产生负timeout；此守卫没有单独执行，不把其源码当作已运行冻结夹具。

新保护及相邻启动的跨版本验证原句柄37127退出1：CPython3.10.22六项通过7.361秒、3.13.18六项通过7.614秒；3.11.18六项5通过1失败7.380秒，原result/log全部保留。准确失败新夹具断言run_once立即succeeded、实际返回running；只读保留现场`/tmp/sdk-settlement-initialization-wiy4sohv`确认同一job最终succeeded/value=done、结算recorded、completion_time_known=true。不能归因为3.11产品不兼容；run_once公开合同允许异步结算。仅修正此新测试在提交前固定原30秒观察窗口，running时只recover_completions及读取原job，不再run_once/调用handler、不重置deadline；原cause/零claim/同代际/仅一次handler断言不变。单项修正结果另列，不将原六项改写全通过。未改变产品wheel或新原生图。

G18环境盘点保存platform-environment-inventory.json：本机Linux x86_64，实际可用CPython3.10.22/3.11.18/3.12.3/3.13.18；没有配置SSH alias，不据此断言不存在其他可用主机，也不推定任何远程授权。Windows x64、Windows ARM既有兼容范围及Linux ARM原生入口仍未提供，已询问授权主机的连接配置/说明路径，不索取密钥正文。新保护补丁的六项定向测试在另外三个Python干净环境顺序执行，句柄37127，证据目录`/tmp/sdk-settlement-startup-python-matrix-20261107`，预计约2分钟；3.12沿用当前候选6项实际证据。不代表全部SDK/原生OS矩阵，期间不触发CI或刷新新模型图。

G17范围审查补充：184个基线模块的当前源码静态声明1692个test方法（不等于动态发现/原基线精确数量），legacy-coverage-inventory.json保留逐模块ID及已知73/66范围，不能把范围外1586个方法直接称为“从未运行”，历史其他批次仍有独立证据。发现旧407条SQL清单按表名前缀遗漏application_reservations等SDK内部表。以源码字面CREATE TABLE识别193个表名重新扫描，legacy-schema-aware-sql-inventory.json列492个潜在直接写调用、73模块；包括test_application_budget_status.test_malformed_facts_unknown_preserve_deadline_watermark直接INSERT/DELETE，以及application_budget两例。静态候选仍需检查夹具、拒绝断言、helper、动态SQL/trigger，不能自动标执行写入或safe。selected-sql-scope-crosscheck.json确认当前73及历史66的准确方法ID无该清单直接命中，但不替代已有helper审查。没有运行新测试/模型或内部SQL写入；原184 runner继续禁止直接复用。

00:42 CST按约核对旧图句柄42623已退出1，原报告`/tmp/sdk-entry-publication-G05-G06-native-20261106/{G05,G06,acceptance}.json`均保留failed；实际15:41:18–16:41:21 UTC。第二轮一coder最终cancelled、planner recovery_required，原成功candidate提交准入问题未在旧wheel修复，不能改判。只读最终control.sqlite3生成terminal-native-cleanup-readback.json，6个native operation全部cleaned，原identity/operation_id准确匹配且tree_cleanup=confirmed。清理不代表业务成功。

在旧图终态及准确清理确认后，仅新初始化保护候选完整G05/G06图启动一次，句柄90082，输出`/tmp/sdk-settlement-startup-G05-G06-native-20261107`及同前缀log；原3600秒/16Agent/128轮不变。使用准确独立安装环境及已授权本地反代，首次预计5–10分钟检查，不提前轮询或并发第二张图。新图未通过前G06保持开放。

新候选sdist已构建并实际no-deps离线安装；sdist-parity.json及sdist-install-parity.json分别证明151产品文件归档/wheel/安装一致，METADATA一致。首次安装因默认pip缓存目录只读失败，sdist-install.log保留；仅用no-cache-dir重试成功，sdist-install-no-cache.log保留。sdist-env继承system-site-packages，不冒充干净依赖解析或完整平台矩阵。previous-candidate-delta.json证明相对owned-decision仅runtime.py初始化失败保护改变；原78项证据仍保持原包来源。

分段取证单例原句柄58608退出0，1项通过、0error/skip、8.717秒，`child-stages-result.json`与`child-stages.log`。原5秒parent/30秒child及全部实际入口/期限/清理断言保持；仅新增有界256条monotonic阶段事件和分阶段累计calls/time/exception类型。此次wait_parent_entry=0.339秒、submit_child=0.030秒、child claim=0.077秒，mark_running对应store transaction先一次OperationalError约0.100秒再一次成功约0.064秒；claim后首个diagnostic_note约0.470秒。原处理函数与期限断言均通过。此结果未复现两次失败，不证明唯一根因或已修复，不再无修改重复；两个原失败继续保留。阶段累积存在嵌套，禁止简单相加为关键路径；无模型调用、无产品修改。

上述child期限失败的定向取证重验退出1，1failure/0error/skip，7.777秒；`child-deadline-diagnostic-result.json`、日志及现场 `/tmp/sdk-inherited-parent-deadline-caeh8a9q` 保留。唯一夹具变化是StorageEvidence额外保留最多128条耗时>=20ms的SQL操作，避免2048条尾部覆盖早期慢操作；产品包、业务断言及原期限不变。原现场请求created_at=1793982551.8396215，SDK child created_at=1793982552.3987732，claimed started_at=1793982554.2928421，显示请求创建到claim约2.453秒。新现场child原生启动余1.649秒仍仅到worker_ready/admission timeout，parent实际进入handler、两个原生cleanup仍tree_reaped。新慢操作中MainThread Kernel commit45次合计1.537秒，child线程28次合计0.914秒，process observer observation commit23次合计1.228秒；这些跨线程总和不能作为顺序关键路径时长。未发现单次超长SQL，尚不能从聚合量断言唯一根因。没有提高预算、删除实际入口要求或据清理成功改判业务通过；独立定向因果复核中。

73项原范围安装包回归已退出1：72通过、1失败、0error/skip，153.713秒，`arbitration-result.json`及`arbitration.log`。失败为test_real_child_stops_at_inherited_parent_deadline，原5秒parent/30秒child/6秒child sleep/12秒返回上限均未更改，child未到实际handler入口。准确现场 `/tmp/sdk-inherited-parent-deadline-9u_xzf9m/evidence.json` 保留：parent process实际入handler，child原生调用直到parent入口后约3.55秒才启动，剩余准入窗口1.207秒；child worker_ready但无on_entered，原生结果timeout/admission、继承parent原deadline。parent timeout/execution，两个准确cleanup receipt均tree_reaped、Runtime.close返回，settlement_error=null。说明此次失败不是结算初始化保护分支触发；未证明是哪一步消耗了子准入前时间，不能凭负载猜测关闭，也不能据安全按期拒绝冒充真实子业务已执行。未重跑整批、未延长期限；该回归缺口继续开放。

后续准确范围回归已启动：`/tmp/sdk-settlement-startup-candidate-20261107/verify-arbitration.py`，原冻结76项中排除3项直接 BEGIN IMMEDIATE 的锁竞争夹具，余73项原顺序/源码/期限不变。独立只读审查确认所选模块及实际helper未直接改写SDK表；原runner绑定旧环境且覆盖旧结果，因此使用独立新runner/manifest/log。该测试不新增制品hash检查；SDK已有的handler registry计算属于正常运行行为，不能描述为完全不发生hash计算。会话56406，预计约3分钟后检查，不提前轮询，不声称覆盖被排除三项或全量旧API。

G14历史证据影响核对：`G14-historical-impact.json`记录sampling-cause到新包的累计6个Kernel文件变化，Agent文件全部相同。准确A为queued/0/0且worker未启动，B无SDK execution，C实际请求返回且effect=performing、handler尚未返回，D生产者结果/effect已提交且继任者尚无SDK execution。独立复核确认四个故障放置点均不在本轮入口采样发布或完成准入窗口内，delta本身不要求机械重跑四次原生故障。旧报告仍保持原制品来源，须结合新包真实多轮图和改变分支回归才可作组合适用性判断；当前条件未齐，未将G14改判为新包运行通过。核对脚本初次误读native报告未运行占位项，随后又假设C状态pending，均由断言拒绝且未生成成功产物；最终仅选各报告实际场景并核对准确performing事实。

安装包验证已退出0：隔离venv准确site-packages来源，三个模块6项全部通过、0失败/错误/跳过，5.940秒，`/tmp/sdk-settlement-startup-candidate-20261107/result.json`。151产品文件 source/wheel/installed 直接字节比较一致。未调用模型或触发CI；不是完整旧API/原生平台回归。

新候选 `/tmp/sdk-settlement-startup-candidate-20261107` 增加 persistent Runtime 的结算存储初始化失败保护；在 run_once 启动服务或 claim 前拒绝，并保留原始异常 cause。只针对构造阶段捕获失败且 journal 不可用；成功构造及 :memory: 路径不变。不自动重试初始化、不领取任务、不重置预算。无模型复现修复前在 claim 陷阱失败，`/tmp/sdk-settlement-initialization-baseline-20261107.log`；修复后 Runtime 与 AgentApp 两例通过3.654秒，`/tmp/sdk-settlement-initialization-fixed-20261107.log`；相邻服务启动四例通过2.106秒，`/tmp/sdk-settlement-initialization-services-20261107.log`。独立审查未发现限定修改的具体阻塞。构造注入发生在资源获取前，同目录重开成功仅证明该夹具清理，不证明真实部分初始化后的资源清理，也不解释此前 README 偶发失败。新包的安装来源/产品字节比较见 parity.json，安装包定向验证结果另列；上一包78项通过不是该新包完整回归。

上一 owned-decision 安装包的附加初始化取证文档检查原句柄50752退出0：582链接、4个README示例全通过、0跳过，日志 `/tmp/sdk-owned-decision-candidate-20261107/docs-initialization-diagnostic.log`。原失败现场及未解释偶发失败保留，不据此次通过声明已修复。G06/G17/G18仍开放；旧原生图按原00:42 CST预计终态时间检查，未提前刷新或重启。

## owned-decision 候选交付状态（初始化保护补丁前）

最新冻结候选为 `/tmp/sdk-owned-decision-candidate-20261107`：补齐已知完成事实的控制锁准入拒绝证据及原期限内连接核验；151产品文件source/wheel/installed一致，相对entry-publication仅`_sqlite_base.py`及`runtime.py`改变。隔离安装包78项定向回归全通过（120.711秒、0失败/错误/跳过）；尚无此包原生图验收，不自动继承旧包Gate通过。G06/G17/G18完整合同仍开放。

上一冻结候选为 `/tmp/sdk-entry-publication-candidate-20261106`（入口发布竞争修复，budget_capture.py、supervision.py）；已打包；安装包33项定向回归通过，真实稳定监督切片通过独立终审，G01/G13能力合同通过。66项旧API范围带失败取证整批通过，但首次失败未解释。G05/G06原多轮图正在运行，完整G06/G17/G18仍未闭合。下述v2候选仍是其冻结时的证据，不能视为新包全部通过；新修复的复现、审查和定向回归见文末。

最新入口修复候选：`/tmp/sdk-entry-wrapped-admission-v2-20261106`；相对下述sampling-cause基线仅context.py、errors.py、supervision.py三产品文件变化，151产品文件source/wheel/installed逐字节一致。入口8项、相邻22项及最终夹具单项通过；当前包G08、G10、G15最低合同已具原生证据并通过独立复核。下述其余Gate仍是前一候选的有效证据索引，不自动视为新包全量通过。

前一验收基线为 `/tmp/sdk-sampling-cause-candidate-20261106`；本地分支 `release/0.8.0`，main 基线 `5833613ab89f54f5fa83b2444d9c20caac26d8a5`。本节取代下文历史时间记录中的旧状态；历史临时目录误复用的例外及影响见文末执行失误记录。

- 验收基线已完成G01–G05、G07–G12、G14、G16；G13仅能力合同及拒绝路径。最新包另已完成G08、G10、G15最低合同。G06、G17、G18三项仍缺完整验收，其余基线Gate对入口修复包的适用性亦须逐项完成审查。先前无关会话代理清理失败仍开放，不能据一次成功宣称修复或完整稳健性通过。
- 当前开放回归：76项批次75通过、1error。首发是线程暂停点未在原3秒内到达，随后关闭出现未持久诊断错误。加入失败取证后单方法四组合通过，不能解释或关闭原失败。见候选result.json、output.log、arbitration-boundary-diagnostic/output.log。
- 原93项范围两个不重叠批次92通过；剩余沙箱测试依照run_once允许返回空值的公开合同修正，在原预算内等待后单独通过。不是同一冻结93项整批通过。45项显式暂缓及其他旧API范围仍缺证据。
- G12当前真实技术重试/耗尽、G05显式返工及完整六实例准入账目、G09效果不明隔离合并通过最低合同；原两秒例及15项分类证据保留，不解释历史晚abort或关闭全部回归。
- G06完整多轮真实场景历史失败，原进程已退出；完成时间未知与数据库准入失败尚无唯一因果解释，不继续等待或无修改重复模型图。
- 外部缺口：G18缺完整Python/OS/架构原生矩阵及完整回归；实验性非空token真实上限另缺可信版本化模型目录、总计费请求上界及输出上界，这不是Goal明文规定的G15默认路径无条件前置要求；配置层四版本隔离环境、Linux x64 Python3.12的G07/G08真实运行时隔离安装证据已补齐，见文末。默认tokens=null可继续验证。G13不提供原生strict后端属于合同明确允许范围，不是必须另开发后端的缺陷。

## 当前候选已重新核实的 Gate

以下仅对应 sampling-cause 当前安装包；历史基线表不代表当前包结论。

| ID | 当前结论 | 当前证据及边界 |
| --- | --- | --- |
| G01 | passed | /tmp/sdk-sampling-cause-G01-20261106/acceptance.json、G01.json、public-api-tests/result.json；配置/默认值/双语Wiki/CLI及18公共API测试。Linux x64 Python3.12；配置层3.10–3.13独立隔离环境各18项通过（文末矩阵），完整平台矩阵另列G18。 |
| G02 | passed | /tmp/sdk-sampling-cause-G12-native-20261106/G02-reused-evidence.json及原report.json；安装包真实OpenCode会话、RETRY_OK结果、实际模型轮次、准确清理和宿主关闭。新venv继承系统依赖，不证明依赖隔离。 |
| G03 | passed | /tmp/sdk-sampling-cause-G03-G04-native-20261106/G03.json及acceptance.json；真实四Agent产物消费、越界/符号链接拒绝、路径替换竞争，限Linux SDK文件工具模式；不声称强隔离。 |
| G04 | passed | 前述真实依赖图与/tmp/sdk-sampling-cause-G04-redelivery-20261106/report.json合并；输入齐备、一次启动、真实租约重投不重复消费、同ID内容冲突。事件冲突负例为存储原语层，崩溃窗口与OS清理另列G14/G16。 |
| G05 | passed | /tmp/sdk-sampling-cause-G05-rework-20261106/G05-minimum-acceptance.json及report.json；真实模型编排两个coder、指定成员显式返工、原逻辑reviewer绑定并消费新结果；独立审查通过最低合同。6 Agent/32模型轮次、原600秒预算、准确SDK清理及宿主关闭；不覆盖G06或崩溃恢复。 |
| G07 | passed | /tmp/sdk-sampling-cause-G07-native-20261106/acceptance.json及G07.json；完全隔离Python3.12当前wheel，真实call/send/wait、原调用者、幂等重放、权限拒绝、自等待环有限拒绝；3 Agent/18模型轮次，独立审查通过最低合同。不扩张为所有等待图或独立OS清理。 |
| G08 | passed | /tmp/sdk-sampling-cause-G08-native-20261106/acceptance.json及G08.json；同一调用/原deadline下原生会话续接，draft→fixed两次验证，两个准确清理回执；blocked及validator异常均失败并保持下游未启动。独立审查通过，response模式复用同包G07。限Linux/Python3.12。 |
| G13 | passed (capability contract only) | /tmp/sdk-sampling-cause-G13-20261106/acceptance.json、G13.json；tools授权，strict业务前拒绝，未入队且runtime_launches为空。/tmp/sdk-sampling-cause-G13-tests-20261106/result.json另有5测试全通过。当前适配器无原生strict后端，real_strict_isolation_accepted=false；未声称真实强隔离已验收。 |
| G11 | passed | /tmp/sdk-sampling-cause-G11-native-20261106/acceptance.json及G11.json；活动旧请求保留原配置/prompt，新请求新版本；实际版本化知识读取、未授权写入拒绝、旧版本冲突不覆盖。2 Agent/14模型轮次，原预算/准确身份/清理回执匹配，独立终审通过；限隔离Linux x64 Python3.12。 |
| G09 | passed (retained native evidence + explicit supplementary evaluation) | /tmp/sdk-sampling-cause-G09-mailbox-20261106/report.json原四场景通过/unknown失败/退出1保留；G09-minimum-supplement.json纠正已用量冻结的错误断言，准确身份、原预算、清理及unknown隔离保持。五种场景覆盖全部邮箱策略/双会话/FIFO/满队列，独立终审认可最低合同，不重跑模型。 |
| G12 | passed (combined retained native evidence) | /tmp/sdk-sampling-cause-G12-native-20261106/G12-combined-minimum.json；真实预启动重试/耗尽、G05业务反馈与显式返工/全六实例准入、G09不明效果保持隔离合并。原报告/失败保留，无新模型；独立审查及主审认可限定最低合同，不替代完整回归。 |
| G10 | passed | /tmp/sdk-sampling-cause-G10-native-20261106/acceptance.json及G10.json；独立客户端/serve、跨Run原预算、同session、真实重启/排队恢复、跨Run取消，22项检查及准确SDK清理通过；独立终审认可。7Agent/14轮，限Linux x64 Python3.12；故障宿主独立OS树清理仍unknown，不扩张为G14/G16。 |
| G14 | passed | /tmp/sdk-sampling-cause-G14-native-20261106/G14-combined-minimum.json合并同包commit/native两报告；四个真实崩溃/重启窗口分别原身份恢复或准确unknown，独立终审通过。6Agent/21轮计量；本地发送不证明远端完成，故障宿主独立OS树清理仍unknown。 |
| G16 | passed | /tmp/sdk-sampling-cause-G16-cleanup-observed-20261106/G16-combined-minimum.json；真实OS宿主竞争/持久停止、准确撤权取消、缺回执跨两次恢复保持隔离，另会话成功；主审及独立复核通过最低合同。恢复宿主均exit1拒绝未解决所有权，监督清理确认；先前代理清理失败未解释，见文末。 |
| G15（入口修复v2包） | passed (minimum) | /tmp/sdk-entry-wrapped-admission-v2-20261106/G15-combined-minimum.json；五份同包真实报告直接核对预算、取消、goal、到期、重试与跨进程恢复，独立终审通过。边界见文末。 |
| 其余 G06、G17、G18 | incomplete | 历史证据与当前缺项见下表及后续记录，不将历史通过自动转移；G06/G12失败现场保留。 |

## 历史验收基线

核对日期：2026-11-06。合同：[实施 Goal](SDK_0_8_0_AGENT_CONTROL_GOAL.md)。本表仅对应 `/tmp/sdk-return-admission-candidate-20261106`；历史记录见[证据索引](SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md)。旧候选的通过不能自动计入本表。没有完整证据的项目按未通过处理。

新增修复候选 `/tmp/sdk-token-envelope-candidate-20261106`：与上述基线相比，151 个产品文件中仅 `agents/token_budget.py` 改变；source/wheel/installed 逐字节一致，见 product-delta.json。下表仍是基线索引；新候选仅完成下面声明的 token 定向安装包验证，不能自动视为所有 Gate 完整通过。默认 tokens=null 的既有执行不进入此解析路径；后续验收按实际影响复用准确证据。

| ID | 当前结论 | 证据与未满足要求 |
| --- | --- | --- |
| G01 | passed | return-admission-config-20261106/G01.json；配置、默认值及拒绝路径。 |
| G02 | passed | 当前 wheel 构建/安装日志与 rework-20261106/report.json；真实 OpenCode 执行及结果。环境继承系统依赖。 |
| G03 | not_run | 尚缺当前包完整文件允许/逃逸拒绝及下游真实读取证据。 |
| G04 | not_run | 尚缺当前包完整双生产者消费、重复与冲突证据；历史结算异常不能凭后续通过消除。 |
| G05 | passed | return-admission-rework-20261106/report.json；真实编排、指定成员返工及原逻辑 reviewer 消费，准确清理已复核。 |
| G06 | failed | 两项真实输入负例通过；歧义现场有独立支持事实，原 failed 保留。完整组/轮次原句柄 63337 已退出 1，G06.json 为 failed/TimeoutError；完整范围未通过。 |
| G07 | not_run | 当前包完整工具授权、send/call-and-wait、等待环证据未齐。 |
| G08 | not_run | 当前包 goal 同会话反馈、阻塞及验证器异常证据未齐。 |
| G09 | not_run | 当前包双会话、FIFO、满队列及替换策略完整证据未齐。 |
| G10 | not_run | 当前包独立宿主、跨 SDK Run、客户端退出与重启续接完整证据未齐。 |
| G11 | not_run | 当前包配置版本及知识授权/冲突完整证据未齐。 |
| G12 | failed | sdk-g12-installed-original-quiescent-20261106.log：原两秒用例 abort 晚于截止约 0.108 秒。不得用四十秒补充例替代。 |
| G13 | passed | return-admission-config-20261106/G13.json；仅能力合同及业务前拒绝。原生强隔离后端未提供、真实隔离未验收。 |
| G14 | not_run | 当前包四类崩溃窗口完整证据未齐。 |
| G15 | not_run | 当前包预算连续性、取消范围及重启完整证据未齐；已知 token 上界问题仍需闭合。 |
| G16 | not_run | 当前包停止/撤销/竞争/清理未知完整证据未齐。 |
| G17 | not_run | 资源限制正反例、空闲 CLI 与六项静态类型消费有基线证据；owner-registration 安装包的 stable/stale/disabled/stop 四个原生监督场景已通过并核对准确清理；完整旧 API 回归尚未齐，整项未通过。 |
| G18 | not_run | wheel/sdist 产品文件一致、sdist 离线安装、578 链接及四个 README 示例有证据；完整回归、平台矩阵、双语导出及最终独立审查未齐。 |

以上 `/tmp` 证据路径的完整前缀及限制在证据索引中保留。not_run 表示整项尚无充分当前证据，不表示其所有子项从未执行；历史 failed 不被覆盖。

## 制品依赖元数据核对

`/tmp/sdk-return-admission-sdist-20261106/dependency-metadata.json`：sdist 顶层 PKG-INFO 使用 Metadata-Version 2.1，未列 Requires-Dist，但 egg-info/requires.txt 保留两个 extras；由 sdist 实际安装后的 Name、Version、Requires-Python、Requires-Dist、Provides-Extra 与当前 wheel 安装结果一致。此前直接比较顶层元数据的断言失败不能据此判定依赖丢失；也不能声称顶层元数据逐字段相同。离线 no-deps 安装不证明联网依赖解析。

## 下一步顺序

1. 定位76项中的线程暂停点及诊断持久化失败；保留原1.5秒业务窗口、3秒屏障和首发证据，不以单例通过关闭，不启动CI。
2. 按G05–G12、G14–G18逐项核对历史报告与最低合同，明确可复用证据、需补跑部分和确认缺陷；按实际产品影响决定重验范围。
3. 新模型调用前明确所补的最低证据和预计耗时。先完成独立可做工作，保留外部矩阵与计量合同缺口。

G06 12:36 预计检查：原句柄 63337 仍 live，无最终报告。只读控制投影显示首轮两个 coder 和 reviewer succeeded，轮次 0/1 两组均 closed，第二轮两 coder 仍 submitted；native 状态汇总为 4 cleaned/1 authorized。原始快照 `/tmp/sdk-g06-rounds-observation-20261106-1236.json`，仅说明已产生的投影，不证明第二轮已完成或当前模型仍有活动。未重启或改变原 3600 秒预算；下一预计检查约 12:42。

12:42 同一句柄仍 live，未有最终报告，但出现可调查变化：第二轮 coder `074a51172bf84f7fa68c854fd49f7e9e` 已 cancelled，未创建 runtime effect；另一个 coder `291626cd19eb4cb59b0e6e621ef0b258` 控制投影仍 submitted，对应 Kernel execution running、agent.runtime effect committed、native cleaned。快照 `/tmp/sdk-g06-rounds-observation-20261106-1242.json`；Kernel 状态为同期只读查询。不能把 committed/cleaned 单独当作结果已交付，也不能从进程存活推断正常推进。下一动作是定位准确执行的结算/取消原因，原进程和预算保留；在没有新原因前不重跑模型。最终报告观察暂估再 6 分钟，原总截止不变。

只读结算核对：291626 的 late_thread_fact 为 outcome ok，但 completion_time_known=false，错误为 _ControlAdmissionTimeout/Kernel control admission budget elapsed；074a511 的错误为 OperationalError/database is locked，取消原因 Kernel transaction control deadline elapsed，亦保留未知完成事实。准确有界摘要 `/tmp/sdk-g06-rounds-settlement-diagnosis-20261106.json`。错误现场没有准确捕获栈，不能从同名超时推定唯一调用点。下面候选读取修复发生在 completion_time_known=true 之后，不能解释本次未知采样或据此宣布 G06 修复。

## G12 有界控制准入诊断

原两秒用例仅增加测试内 `_control_lock` 上下文的进入、准入及退出时间观察，保持原参数、返回值、异常传播和结束后还原；产品未变。当前安装包单次运行 `/tmp/sdk-g12-control-lock-diagnostic-20261106.log` 4.993 秒失败，现场 `/tmp/sdk-prelaunch-deadline-failure-1j46fl31/evidence.json`。此次 adapter 未进入，runtime_setup 返回 StaleFenceError，不能称为 abort 后重试验证。201 个准入上下文中记录了实际等待及超时；部分已准入上下文持续约 76–126 毫秒。此时间包括上下文内工作与退出清理，不等于原始互斥锁连续占用时间；与多线程轮询重叠不能独立证明无用轮询造成故障。下一定位应辨认这些长区间的准确调用路径，不按本观察直接削减轮询、延长预算或修改拒绝断言。

独立复核未发现观察器改变原上下文异常/返回行为的具体问题；最长区间与另一失败准入虽重叠，但发生在 runtime_setup 失败之后，不能作为入口失败根因。随后只补充固定代码函数名，单次日志 `/tmp/sdk-g12-control-caller-diagnostic-20261106.log` 5.079 秒仍失败、adapter0，现场 `/tmp/sdk-prelaunch-deadline-failure-2ks_l33z`。原截止前较长区间定位到 `_sample_budget`（约 80/71 毫秒）、其内 `_finish_budget_sample`/事务，存在嵌套不得相加。runtime_setup 开始时原两秒只余约 76 毫秒。压缩证据 `/tmp/sdk-g12-control-caller-summary-20261106.json`。这收窄到调度和预算采样开销，尚不证明采样可删除或历史 abort 延迟同因；不继续无修改重复测试。

## G15 流式用量错误结算修复

旧安装包确定复现：只有 usage 与 DONE、没有任何完成结果的 HTTP 成功流仍结算 8 tokens，`/tmp/sdk-token-stream-envelope-baseline-20261106.log`。代理只有传输完整/2xx 守卫，未补足结果完整性。现要求合法 chat.completion.chunk、单一 index-0 choice 明确结束，以及所有分块一致的非空响应 ID；允许同响应的最终空 choices 用量分块和仅工具调用/空文本结果。缺完成、混合/缺失 ID、畸形或截断响应保持 unknown，不释放预留。

独立审查指出的跨响应 ID 混合缺口已修复，最终复核在该范围内无具体阻塞。源码最终 17 项通过 26.943 秒；独立新 wheel 安装包 17 项通过、0失败/错误/跳过，26.895 秒，`/tmp/sdk-token-envelope-candidate-20261106/{result.json,installed-tests.log,product-delta.json}`。真实本地 HTTP 代理负例验证三祖先均 spent=0/reserved=10/unknown_count=1，下一请求在上游前拒绝。测试提供方为本地合成响应，不算真实 OpenCode G15 验收；G15 整项仍未通过。中英文 Wiki 与 token 设计边界已同步，无模型调用或 CI。

## 已捕获结果的候选读取准入修复

确定复现：真实 Runtime 已成功捕获完成时间后，持有 Kernel 控制锁 0.4 秒再释放，原五秒预算未耗尽，但单次 0.1 秒候选读取拒绝后返回 running，`/tmp/sdk-candidate-read-control-baseline-20261106.log`。这是独立缺陷，不能解释上述 G06 completion_time_known=false 的捕获故障。

修复仅让尚未 yield 的候选读取准入在原 entered deadline 内续等，持续检查 active/stop 和继承期限；不重放读取 body、业务或效果。已按时捕获但进入读取时已过截止的情况保留原来一次短读取机会，不新建重试窗口；最终结果权威仍由原 owned decision 核对。新增实际锁释放、停止和到期用例；源码结算竞争模块 16 项通过 49.234 秒，`/tmp/sdk-candidate-read-control-fixed-20261106.log`，独立复核无本修复范围内具体阻塞。

新候选 `/tmp/sdk-candidate-read-candidate-20261106` 相对 return-admission 基线仅 token_budget.py 与 execution_kernel/runtime.py 两个产品文件变化，151 文件的 source/wheel/installed 逐字节一致，product-delta.json。原句柄 77628 已退出 0；安装包 33 项组合验证全部通过，0失败/错误/跳过，result.json 保留准确安装来源，installed-tests.log 保留输出。这是两项修复的定向安装包验证，不是完整回归，也不关闭 G06/G12/G15/G18。

12:48 G06 原句柄 63337 仍 live、无最终报告。鉴于已出现未知结算，预计可能需原请求截止（约 13:24）后收尾，下一检查约 13:26；不再每六分钟刷新，不因观察超时重启或延长原预算。

## G06 后续故障证据补全

当前只读 Kernel 查询无 pending budget sample；这不能恢复历史缺失的完成事实，不能据此清除 unknown 或补判成功。当前源码的 owned return 已在原工作期限内重试多处准入；已保留的异常缺栈，仍不足以定位提前退出点，不在此基础上修改采样规则。

公共 native_groups_rework 验证入口现复用既有 observe_return_failure：观察先于 AgentApp 上下文进入，晚于宿主关闭退出；原方法、参数、返回和异常保持，证据独立 UUID/O_EXCL/0600，仅保留有界 SDK 抛出位置和有限数值 original_work_seconds_remaining，无消息/会话/凭据正文。5 项诊断测试通过 `/tmp/sdk-group-return-diagnostic-final-20261106.log`；独立复核无具体阻塞。这只改后续验证器，不改变正在运行的原 G06 进程，也不补回已丢失的历史栈。未重跑模型，G06 仍未验收。

G15 真实非空 token 限额还需要宿主提供可信且版本固定的模型目录、单请求总计费上界和输出上界。当前 native_environment 的资源入口只构造连接配置，没有这些计量合同；不能自行编造额度来冒充真实上限证明。默认 tokens=null 的原生测试不受此限制；非空 token 真实验收缺口继续保留。

## G17 验证入口误拒绝修复

12:55 的 `/tmp/sdk-current-supervision-stable-20261106/report.json` 在创建 AgentApp 前即失败，目录只有 report.json，没有原生执行现场。确定原因：复制到 `/tmp` 平铺目录的验证器以其父目录 `/tmp` 为源码根，误把 `/tmp` 下真正 site-packages 安装包拒绝为源码。入口判断现精确限定到源码根的 `src/dispatcher_sdk`，保留源码拒绝。

无模型预检分别确认独立安装包接受、当前源码拒绝；安装来源及零模型调用记录 `/tmp/sdk-supervision-import-preflight-20261106.json`。此修复只恢复验证入口，不证明监督行为通过；原失败报告保留，未重跑真实场景，也未改变产品候选。G17 仍未验收。

入口修复后，G17 stable 单场景原生验证已在原 candidate-read 安装包启动，句柄 27189，输出 `/tmp/sdk-current-supervision-stable-fixed-20261106`；原 360 秒预算不变，预计约 13:04 首次检查。验证器现保留有界 SDK/验证器异常位置，不记录异常消息、局部变量或模型内容；无模型诊断检查确认私有消息不进入记录。

## 成功取得锁后的短等待片过期

确定复现 `/tmp/sdk-acquired-slice-baseline-20261106.log`：真实 RLock 成功取得后，模拟线程调度停顿 40 毫秒；短等待片为 10 毫秒、原工作窗口为两秒。旧代码在尚未执行 body/SQL 时直接拒绝，未使用原有剩余准入窗口。修复只在原 retry_limit 未到期且停止检查通过时续开短片；调用方及嵌套截止继续约束，不重放 body。新用例覆盖成功、调用方截止和停止异常原样传播；独立复核未发现明确阻塞。该确定性缺陷没有历史 G06 捕获栈支持，不能据此宣布 G06 根因已确认。

源码相关 22 项通过 18.084 秒（尚不含随后增加的停止用例）。冻结新安装候选 `/tmp/sdk-acquired-slice-candidate-20261106` 相对 candidate-read 仅 `_sqlite_base.py` 产品文件改变；151 个产品文件 source/wheel/installed 逐字节一致。安装包组合句柄 1361 已退出 1：39 项中 34 通过、5 错误，72.331 秒，0 断言失败/跳过。控制准入与 owned-return 两个完整模块共 23 项全部通过，包含新增停止用例；Runtime 竞争模块 11 通过、5 项在夹具 SettlementJournal 初始化、首次 PRAGMA trusted_schema=OFF 之前即发生 SettlementBusyError，未到达目标竞争边界。结果及原堆栈保留 result.json/installed-tests.log，不能合并为完整通过或断言环境原因；不无修改重复运行。原 G06/G17 运行不换包、不重启。

13:04 G17 同一句柄 27189 仍 live、未有最终报告，不据此推断业务推进。按原 360 秒截止下一检查约 13:06，不重启、不延长原预算。

13:06 同一句柄已退出 1，stable failed；report.json 显示真实父执行观察、诊断子 Agent 成功、准确原控制器预算绑定、稳定代际仅一个子调用及 replay 同子全部成立，随后父等待超时。父/子原生清理收据均 confirmed，两个资源所有权均 released。只读原始数据库显示父 agent.runtime effect 于 1793941224.015053 提交 succeeded、资源于 1793941224.0284293 释放，早于原截止 1793941521.0040362 约 297 秒；父 Kernel 执行最终 cancelled，不能将运行时 effect 成功当作最终交付成功。

return-failure-e3c9bc0b3318402ebb59d712837d29f1.json 捕获 `_sqlite_completion.py:729` → `_sqlite_base.py:399`、剩余工作时间 -0.511 秒。观察文件本身未记录执行 ID；Kernel completion_authority 中匹配的错误属于 controller 的 unknown timeout，而非已证明的父 Agent 返回捕获。不得从此栈归因父执行阻塞点。父运行时已经完成这一事实将下一定位收窄到运行时之后的结果交付；没有新模型重跑。

随后只运行不调用模型的现有监督集成用例：新 acquired-slice 安装包 1 项通过 19.774 秒，`/tmp/sdk-g17-synthetic-handoff-20261106.log`。将同一用例的观察顺序改为先 Invocation.wait、再 AgentRun.wait，并共享原 25 秒观察窗口，1 项通过 18.519 秒，`/tmp/sdk-g17-invocation-wait-order-20261106.log`。两次均未跳过、本地端口实际可用，未触发 20 秒线程栈计时器。它们没有复现原生现场，不能证明原生父结果交付已修复，也不支持将失败归因于两种公共等待 API 的顺序。不无修改重跑真实场景。

## 完成所有者登记准入

13:26 检查原 G06 句柄 63337 已终止、退出 1，原目录 `G06.json` 已生成，group_scenario_status=failed、exception_type=TimeoutError。异常位置包含公共 Invocation.wait → application._pump/_reconcile_one → store.get/transaction。原 3600 秒范围及失败证据保留，未重启或延长；该栈不证明此前两个 coder 的未知完成故障由同一调用点产生。

G17 原 stable 父执行的只读 settlement 记录显示 deferred/pending、outcome.kind=ok、completion_time_known=false，错误为 `StorageIsolationError: completion owner unavailable`。Runtime 登记原先仅等待一次 100 毫秒，普通异常被吞掉后继续业务；历史吞掉的异常类型无法从现场恢复，不能断定就是锁竞争。

新增实际 managed Runtime 复现：登记时真实控制锁被另一线程持有 250 毫秒。仅移除重试参数以恢复原单次等待行为时，用例失败为 running != succeeded（1.684 秒），`/tmp/sdk-owner-registration-runtime-baseline-20261106.log`。修复让登记前的准入等待受原 startup/work/caller 截止及 active/stop 检查约束，不重试登记 body；预分配所有者与中断清理保留。登记异常仅额外保留类型，不保存消息。修复后同一用例业务与登记各一次、成功交付、所有者清理通过（1.739 秒），`/tmp/sdk-owner-registration-runtime-20261106.log`。此前两个完整源码模块 28 项通过（38.805 秒），`/tmp/sdk-owner-registration-focused-20261106.log`；新增调用方截止用例另随安装包验证。独立审查未发现本次修改的具体阻塞。此证据不等于原生 G17 已通过，也不关闭 G06/G12/G18。

新安装包 `/tmp/sdk-owner-registration-candidate-20261106` 的原句柄 9005 已退出 0：36 项全部通过、0 失败/错误/跳过，40.004 秒。覆盖三个完整模块：控制锁取得中断、owned-return 准入、Runtime 所有者清理（含新竞争用例）。151 个产品文件 source/wheel/installed 逐字节相同，result.json/installed-tests.log 保留来源和结果；相对 acquired-slice 产品仅 runtime.py 与 _sqlite_completion.py 改变，product-delta.json。依赖仍继承系统环境，不声称独立依赖解析。无真实模型调用、无 CI。登记异常类型的新增诊断覆盖保留原返回结果的分支；预算规范化替换整个结果时仍可能丢弃该字段，不能声称所有失败类型都有该诊断。

## 新候选后续核对

G17 stable 原生定向场景以 owner-registration 安装包启动，句柄 30268，输出 `/tmp/sdk-owner-registration-supervision-native-20261106`，仍为原 360 秒、5 agent_calls/32 model_turns；预计约 13:35 检查。不改变运行中候选，不扩大为整套回归。

当前安装包执行文档检查 `/tmp/sdk-owner-registration-docs-20261106.log`：581 本地链接有效、4 README 示例通过、0 跳过。`/tmp/sdk-owner-registration-wiki-preview-20261106` 已导出 25 页含双语 Agent Control 的本地 Wiki 预览，日志 `/tmp/sdk-owner-registration-wiki-export-20261106.log`。ref 为本地 release/0.8.0，不表示该修订已发布或允许远程推送。

G12 原两秒用例在当前安装包的首次受限执行因本地端口权限跳过，保留 `/tmp/sdk-owner-registration-g12-original-20261106.log`，不计通过。改在已授权宿主执行相同用例，原句柄 71502 退出 0：1 项通过、0 跳过、3.580 秒，`/tmp/sdk-owner-registration-g12-original-host-20261106.log`；准确证据 `/tmp/sdk-confirmed-abort-expiry-98s_owpo/evidence.json`。原 seconds=2/wait_seconds=30 与断言不变；adapter 实际进入、abort 在原截止前确认，执行一次、无技术重试，后续保持 recovery_required/indeterminate。此为该精确用例的新通过，不证明历史失败的原因已修复或性能已稳定，也不关闭完整 G12；原失败证据保留。

13:35 G17 原生 stable 的同一句柄 30268 已退出 0，report.json 的 stable=passed。实际父调用 `2088179d327643b48756e2e2488a8814`、诊断子调用 `9b3b646c168649ebb0d74df81ea0ab21` 在原 Run `agent-run:896d5928540046f499b8bb7ea5c59984` 下完成；准确入场收据、同 Run、截止不增、原控制器预算、同代际一个子调用、replay 同子、实际原生诊断及固定产物均为 true。父 Invocation.wait 与 AgentRun.wait 均返回，usage.agent_calls.spent=2。只读关闭后核对 `post-close-exact-receipts.json`：父/子两项 native 均 cleaned，持久收据与 operation_id/execution_id/lease_id/attempt/fence/effect_id/invocation_id/deadline 完整匹配并 tree_cleanup=confirmed；两个资源所有者均 released。初版 post-close-ownership.json 的预期对象遗漏 operation_id 导致比较 false，原文件保留并由新文件明确说明，不是 SDK 清理失败。旧 stable 失败仍保留，单次新通过不证明历史唯一根因；G17 尚缺 stale、disabled_and_stop 和完整旧 API 回归，整项不计通过。

13:43 同候选 G17 stale 原句柄 20351 退出 0，`/tmp/sdk-owner-registration-supervision-stale-20261106/report.json` 的 stale=passed。实际父调用 `612d06128a0d4b29bcf907c592d4ec41` 提交 answer 版本 1 后，旧监督请求被 `agent_supervision_stale` 拒绝，旧请求无准入效果或子调用，父 Invocation.wait/AgentRun.wait 成功。只读 `post-close-generations.json` 区分：generation=1/versions={} 为 superseded、target=null；generation=2/versions={answer:1} 合法 dispatched 至 `cde529452d3a429e889a58f5cfdba9a2`，该 reviewer succeeded。因此不能声称整个运行没有诊断子调用。`post-close-exact-receipts.json` 确认这两项原生操作均有完整身份匹配的 confirmed 清理收据，两个资源所有者 released。独立审查指出的父清理状态不足已用关闭后准确收据补足；未将旧代拒绝等同于无限期禁止新代监督。

13:44 同候选 disabled_and_stop 启动，原句柄 53131，输出 `/tmp/sdk-owner-registration-supervision-disabled-stop-20261106`；每场景原 360 秒预算不变，按前两场时长预计约三分钟后检查。停止场景仅证明撤销监督准入及有限观察期不再诊断，不将未知/取消的模型结果当作成功；结束后另核对准确清理与资源释放。

13:48 同句柄 53131 已退出 0，disabled_and_stop=passed。disabled 场景在实际原生父存活窗口没有 monitor/observe/diagnose、待处理 incident 或子调用；父实际发布固定产物并 succeeded。stop 场景在待诊断准入窗口取消，收到 `agent_supervision_stopped`，对应准入效果及子调用不存在，三秒观察期没有后续诊断；不扩大为永久保证，不宣称模型成功。两场各一个原 Agent 调用、原 execution/attempt/fence 及截止不变；验证器核对准确原生清理收据，宿主上下文关闭成功。关闭后只读 `disabled-state/post-close-exact-receipts.json` 与 `stop-state/post-close-exact-receipts.json` 分别确认一个完整身份匹配的 confirmed 清理收据和一个 released 资源所有者。至此当前安装包四个原生监督场景均通过；完整 G17 仍缺旧 API 回归，不凭监督子集关闭整项。

## 旧 API 回归范围

基线 main=`5833613ab89f54f5fa83b2444d9c20caac26d8a5`，共有 184 个 tests/test_*.py 模块。`/tmp/sdk-owner-registration-legacy-regression-20261106/scope.json` 冻结完整模块清单与支持文件；执行当前 owner-registration 安装包，原个别测试断言与超时保留，Linux/Python3.12 的平台跳过不证明其他平台。依用户禁止未要求的 hash/checksum/fingerprint 验证，独立范围核对将 19 个明确的肯定性校验用例列入 deferred.json；它们不计通过，也不能被从完整验收要求中悄悄删除。日常 SDK 内部身份计算及禁止散列的负向守卫，不当作新增校验流程。

首批 20 模块原句柄 22486，batch-0.manifest.json/batch-0.progress.jsonl/batch-0.log 留存完整选择、单用例开始/结束及原输出；预计约五分钟核对，失败即停。无模型请求、无 CI。后续批次与整体结论须以相同冻结候选实际结果为准，不将批次成功代替完整旧 API 回归。

该首轮入口缺少 multiprocessing 的 `__main__` 保护，子进程重入整套测试，执行 11 项后 process_default 用例超时；不能归因 SDK。原入口与输出保留为 run_batch.original.py、batch-0-entry-failed.*。修复包外入口保护后，仅原触发用例通过 2.444 秒、0 跳过，entry-fixed-single.log；只读进程核对没有遗留该测试进程。14:00 使用修正入口恢复同一 20 模块/175 项范围，原句柄 35310，预计约 14:06 检查；不改产品、断言或个别测试超时，旧错误不覆盖。

14:06 同句柄 35310 已退出 1：175 项中执行 159 项、158 通过、1 错误、0 跳过，191.818 秒；16 个完整模块通过。错误为 ChildCompletionReadonlyTests.test_real_writer_held_beyond_original_cutoff_allows_readonly_delivery_without_clock_write 在 completed_child 准备阶段，尚未启动目标 writer，claim_and_start 的预算采样已超出原半秒窗口；现场 `/tmp/sdk-child-completion-readonly-v3hcildz/evidence.json` records 为空，不能归因于目标只读交付逻辑。独立只读核对确认现场没有足够阶段时间可定位唯一原因，不延长半秒或删除权限采样。

一次包外定向阶段观察 `run_readonly_diagnostic.py` 保留原用例，readonly-diagnostic.log/readonly-phases.json：1 项通过、0 跳过，原 writer 路径执行成功；两次采样分别约 25.4/27.2 毫秒，原失败未复现。只记录单调时间、代码阶段、异常类型和匿名采样序号，不改预算权威，不以相互重叠阶段相加归因；原批次失败仍开放。不无修改重复同例。源码夹具新增准备开始/提交/认领结束及失败时 pending/captured 状态记录，保持原断言、半秒窗口与控制片，不写入 SDK 存储；本次冻结批次不换文件。

14:10 下一批独立模块（清单索引 20..39）启动，原句柄 12861，仍用同一安装包与原冻结测试，预计约 14:16 核对；首批未执行尾项和失败模块不被跳过后计为通过。

14:16 同句柄 12861 已退出 1：171 项中执行 97 项、96 通过、1 失败、0 跳过，91.699 秒。失败为 CompletionReaderLifetimeTests.test_admitted_actual_snapshot_retains_storage_until_body_and_physical_close_finish 的 held.wait(1)，原现场 `/tmp/sdk-completion-reader-lifetime-pyc_h8m1/evidence.json` 记录 runtime_wall_samples=[]、completion_receipts=[]。夹具 observed_capture(outcome,context) 未接收 Runtime 已传递的 serialized/work_deadline 关键字，TypeError 在观察函数执行前发生；源码夹具现原样转发 **options，未改变产品。另一个未解决前提是现代线程返回采用 serialized capture，该夹具仍等待旧 _connect_reservation/_read_floor 路径。仅修正参数转发不能宣称此模块通过；正在独立核对如何以实际消费者保留原 Context/Runtime 物理读者生命周期断言，不恢复废弃产品路径、不删断言、不延长超时。当前未执行新一轮完整回归或 CI。

## 读取生命周期夹具修复及范围控制纠正

当前 owner-registration 安装包未改变。`tests/test_completion_reader_lifetime.py` 将真实处理器中的公共 `capture_completion_time` 与 Runtime 的 serialized 返回采样分别记录，观察回调原样转发关键字。第一次尝试在持有真实 BEGIN IMMEDIATE 时等待超时结算，导致 driver 在原两秒观察期仍存活；该夹具顺序失败保留于 `/tmp/sdk-reader-fixture-repair-20261106/{test_completion_reader_lifetime.first.py,result.log}`。最终恢复先结算原 timeout、再由仍存活处理器打开公共读者的顺序，不改原五秒预算、物理连接、容量、close-only 重试断言。三项定向测试全部通过 5.278 秒，随后完整七项模块全部通过、零跳过，10.575 秒，`result-second.log`、`module.log`。这是测试入口修复，不计产品修复或完整 Gate 新通过。

旧 API 清单索引 40..59 的原句柄 15679 启动后发现首个消费者模块会再次 discovery 整套内层测试（原内层上限 2700 秒），不继承外层 deferred 清单。此前 4–6 分钟估计及范围审查不足。已准确停止该批次及子进程，`/tmp/sdk-owner-registration-legacy-regression-20261106/batch-40-stopped.json` 保留原因和 PID；原日志保留，不计通过。尚未核实内层停止前执行到的全部范围，不能声称禁止校验未执行。后续必须在启动前审查嵌套执行范围；内层未继承排除规则前不重跑该测试。无真实模型调用、无 CI。完整 G17 仍未通过。


读取生命周期夹具已独立复核：公共消费采样与 Runtime serialized 采样分离，原 timeout、读者/连接、容量及 close-only 断言保留；复核未发现本范围的新阻塞，未重复运行七项模块。

后续范围审查新增四项肯定性 digest/revision 比较及一个未过滤内层 discovery 外层用例，列入 `deferred-v2.json`（总 24 项，其中 23 项校验及一个内层范围未隔离）；原 deferred.json 和运行记录不改写。`run_batch_safe.py` 后续采用新清单，并在执行前拒绝该未过滤 discovery 用例。审查结果到达前，索引 41..59 批次已执行其中两个 revision 比较用例，这是范围控制遗漏；`additional-deferred-audit.json` 保留准确 ID/开始时间，它们不计有效验收证据。新清单阻止后续重复，不能撤销已经发生的执行，也不证明所有语义隐含校验都已穷尽。

索引 41..59 原句柄 82696 退出 1：224 项选择中执行 157 项、156 通过、1 失败、0 跳过，172.338 秒，`batch-41.result.json`。其中两个通过用例随后被范围审查排除，不计有效验收。失败现场 `/tmp/sdk-entry-contention-keuwlq_r/evidence.json` 显示原预算未变、准入重试成功、业务一次且最终 succeeded；断言失败为异常精确类名从 TimeoutError 变为其子类 `_ControlAdmissionTimeout`。源码测试保留原异常类名诊断，新增实际 `isinstance(exc, TimeoutError)` 记录并断言该语义，原消息和业务断言不变。完整四项模块对当前安装包通过、0 跳过，5.772 秒，`/tmp/sdk-entry-fixture-repair-20261106/{test_handler_entry_contention.py,module.log}`。产品未变；原失败记录不覆盖。

`/tmp/sdk-owner-registration-legacy-regression-20261106/regression-status.json` 按准确测试 ID 合并终态批次与两份冻结夹具覆盖证据，保留历史失败、明确后审排除，不将中断批次或未运行尾项推定通过。索引 53..79 使用 run_batch_safe.py 与 deferred-v2.json 继续，原句柄 66687，预计启动后 4–8 分钟首次检查。完整 Gate 结论未变。

索引 53..79 原句柄 66687 退出 1：执行 72 项、71 通过、1 导入错误、0 跳过，31.954 秒。`test_lifecycle_generation_retirement` 通过顶层模块名引用测试辅助文件，包外入口未将冻结 tests 目录加入搜索路径；已只修正包外 run_batch_safe.py 的支持路径，产品和冻结测试未变。原错误保留 `batch-53.*`。

索引 61..79 原句柄 96491 退出 1：执行 15 项、14 通过、1 错误、0 跳过，13.492 秒。原导入失败模块两项均通过；随后 `test_failed_claim_receipt_prevents_handler_invocation_and_can_retry` 在读取 None 的 settlement_journal 时失败。Runtime 已将自动日志创建异常保存在 `_settlement_error`，但该原现场临时目录已删除，原始创建原因未知。独立只读审查未发现确定初始化缺陷，不能推定环境原因或扩大期限。一次透明构造/打开阶段观察 `/tmp/sdk-journal-init-diagnostic-20261106/{run.py,result.log,phases.json}` 保留原调用/异常/期限：原用例通过 30.625 秒、0 跳过；初始化 65.4 毫秒、日志可用、settlement_error=null。该次未复现原失败，不关闭其可靠性问题。源码 fixture setUp 新增所需日志非空断言，失败时保留现有初始化错误和存储状态，避免以后仅留下二次 NoneType；未重试初始化、不扩大原 100 毫秒期限、不改产品。

## 后续旧 API 回归与完整模块复核

索引 63..79 原句柄 31200 退出 1：执行 70 项、69 通过、1 失败、0 跳过，43.419 秒，`batch-63.result.json`。失败为 managed legacy policy 用例在 Runtime 关闭前立即扫描异步诊断收据：业务 succeeded、准确 supervisor obligation resolved、worker_tree_cleanup confirmed、outcome durable，但父 process_cleanup 诊断暂为 unknown。测试将原本 finally 中已有的正常 runtime.close 提前到持久收据断言前，保留原准确身份/工作树/父清理/持久结果断言；关闭不成功仍失败。当前安装包完整一项模块通过、0 跳过，7.809 秒，`/tmp/sdk-policy-cleanup-fixture-20261106/{test_managed_legacy_policy_integration.py,module.log}`。不直接写入或伪造收据，产品未变。

完整 lifecycle journal handoff 模块以冻结诊断夹具对当前安装包通过 28 项、0 跳过，53.579 秒，原句柄 53782 退出 0。`/tmp/sdk-journal-module-diagnostic-20261106/{run.py,test_lifecycle_journal_handoff.py,module.log,result.json,phases.json}` 保留原初始化 100 毫秒期限、真实日志构造/打开、错误类型与有限栈位置；观察只在初始化期间收集，最多 512 条，本次无丢弃，无初始化错误或 unavailable。此为完整模块的新通过，不证明原 NoneType 现场的创建原因或不存在偶发问题。

完整 child completion readonly 模块通过 22 项、0 跳过，15.512 秒，原句柄 24535 退出 0，`/tmp/sdk-child-readonly-module-20261106/{test_child_completion_readonly.py,module.log}`。夹具仅补充原准备阶段记录，原半秒窗口、采样权限和断言不变。原失败用例实际走完 writer/只读结果路径；新通过不恢复原丢失时序，也不说明历史采样超时有唯一已修复根因。当前产品候选始终未变，未调用模型、未跑 CI；完整 G17/G18 仍缺其余回归和平台范围。

索引 17..19 原句柄 54628 退出 0，完整三模块 12 项全部通过、0 跳过，6.112 秒，`batch-17.result.json`。索引 27..39 原句柄 73790 退出 0，13 模块的 161 项已选测试全部通过、0 跳过，99.706 秒，`batch-27.result.json`；ContentCodecTests.test_digest_and_length_metadata_are_verified 仍显式暂缓，不能把已选范围通过写成全部原用例通过。

索引 72..93 已用同一安装包和安全入口启动，原句柄 64040，首次预计启动后 3–6 分钟核对；仍有后续索引 94..183、显式暂缓项和历史偶发失败原因等缺口。上述均为旧 API 回归进展，不新增完整通过的 Gate，不关闭 G17/G18。所有真实模型请求保持未运行；产品未改，无 CI。

索引 72..93 原句柄 64040 退出 1：执行 43 项、42 通过、1 失败、0 跳过，99.993 秒，`batch-72.result.json`。失败仅为 migration foreign key 测试仍断言目标 schema=13，实际已为当前 19；测试改为核对 SDK 的 KERNEL_STORAGE_SCHEMA_VERSION，原有效成员不变、孤立成员拒绝、源库保留及目标不覆盖断言均保留。当前安装包完整三项模块全部通过、0 跳过，1.944 秒，`/tmp/sdk-migration-version-fixture-20261106/{test_migration_foreign_keys.py,module.log}`。仅使用测试新建的临时库，未迁移任何真实旧 Run，产品未改。

索引 77..93 原句柄 96748 退出 1：174 项选择中执行 9 项、8 通过、1 错误、0 跳过，3.269 秒，`batch-77.result.json`。错误为 NativeSupervisorRetentionTests 的 `__new__` 合成 Runtime 夹具缺少当前构造函数的 `_stop_requested`，未到达目标异常传播。独立修正仅该测试文件，补齐停止信号、交付所有权、空线程/完成所有权及 Kernel 关闭状态；原故障注入、原异常身份、准确代次句柄保留和其他义务清理断言均保留。当前安装包完整九项模块通过、0 跳过，0.007 秒，`/tmp/sdk-retention-fixture-repair-20261106/{test_native_supervisor_retention.py,module.log}`。其中 Windows 路径为句柄替身验证，不构成 Windows 原生验收，产品未变。

索引 80..93 原句柄 41014 继续未执行尾项，首次预计启动后 3–6 分钟核对；不重复已通过的 native budget/admission 范围。完整 Gate 结论未变，无真实模型调用或 CI。

## 旧线程返回已过期但结算持续未知：修复及安装包验证

索引 80..93 原句柄 41014 退出 1：执行 45 项、44 通过、1 失败，42.340 秒。`test_thread_wall_forward_exhaustion_does_not_commit_success` 在原两秒预算内由处理器把注入墙钟前拨三秒，并通过 context.budget 确认剩余零；原十秒恢复期后仍无结果。安装包一次保留现场复现失败，11.119 秒，`/tmp/sdk-wall-forward-diagnostic-20261106/result.log`、`/tmp/sdk-wall-forward-exhaustion-wrp49_l9/evidence.json`：原完成采样 InspectionBudgetExceeded，completion_time_known=false，已确认过期 checkpoint 存在，但结算一直 pending。此前安装包保持该故障，不能计通过。

修复只涉及 execution_kernel/runtime.py。旧线程在实际返回回调入口保留已接受预算的可信过期观察，不重新采墙钟；完成时间采样函数会内部记录失败而非抛出，故同时处理该未知返回。只有这条回调路径能产生内部过期证据，后续 bookkeeping 投影不能生成。当前活监控器消费准确同一个内存发布对象，并通过原 completion/lifecycle/stop 权限及 Kernel 的原 lease/attempt/fence、预算和效果检查提交超时；完成时间未知仍保持未知，只有核对准确 Kernel 提交收据才解除结算暂缓。沿用原预算，不给业务新窗口；不允许持久化旧事实自行获得提交权。managed 原返回采样分支保留。独立审查发现并修正最初泛化标记来源的问题，最终限定审查未发现本范围其他阻塞。

初版源码定向运行仍失败，`/tmp/sdk-wall-forward-source-fix.log` 保留；不能把后续通过当作历史失败原因全部消失。最终源码完整 observability_application、completion_return_late_decision、completion_unknown_authority_recovery 三模块共 17 项通过、0 跳过，21.140 秒，`/tmp/sdk-wall-forward-final-source.log`。新增负例强制返回入口尚未过期、随后采样失败并接受前拨后的过期 floor，结果仍未知，不能倒算原返回超时。

新候选 `/tmp/sdk-legacy-expiry-candidate-20261106` 安装包同一冻结三模块 17 项全部通过，0 失败/错误/跳过，21.844 秒；`result.json`、`installed-tests.log`、冻结测试和 verify.py 保留安装来源。149 个 Python 产品文件 source/wheel/installed 直接逐字节比较一致，相对 owner-registration 仅 runtime.py 改变，`product-delta.json`；此比较没有新增散列校验。首次构建因默认 pip 缓存只读失败，build.log 保留，改用 no-cache-dir 后构建/安装成功。该候选仅完成本定向范围，旧候选的真实监督等结果不自动升级为当前全项通过。下一步补 managed 返回/监督影响验证，再接续尚未执行的旧 API 范围；G01–G18 完成合同不变，无新增整项验收通过，无真实模型请求、无 CI。

legacy-expiry 安装包追加托管返回/锁准入/完成所有者清理三模块验证：36 项全部通过、0 失败/错误/跳过，38.438 秒，`/tmp/sdk-legacy-expiry-candidate-20261106/{managed-result.json,managed-tests.log,verify_managed.py}`，测试文件单独冻结，实际 SDK 导入来自该 env。此为变更影响范围验证，不能替代真实 OpenCode 监督场景或关闭 G17。

未执行旧 API 清单索引 84..93 已在同一新安装包启动，原句柄 19811，预计启动后六分钟首次检查。独立范围审查确认本批 subprocess 为逐用例工作进程，不嵌套全套测试、不构建/重装 SDK、不访问模型；opensandbox 的原 deferred 用例继续排除。包外入口和 scope/deferred 冻结在 `/tmp/sdk-legacy-expiry-regression-20261106`，测试支持闭包仍引用原冻结 `/tmp/sdk-owner-registration-legacy-regression-20261106/source`；新输出不覆盖旧失败。剩余索引 94..183 和所有暂缓项不推定通过。

legacy-expiry 原句柄 19811 退出 0：索引 84..93 十模块已选 112 项全部通过、0 跳过，137.170 秒，`/tmp/sdk-legacy-expiry-regression-20261106/batch-84.{result.json,log,manifest.json,progress.jsonl}`。一项已列明 OpenSandbox revision 验证仍暂缓，不计通过；适配器用例的合成提供方不构成真实后端隔离证明。索引 94..104 已经独立范围审查，无嵌套全套测试/SDK 重装/模型调用及新增散列验证；Linux clone 用例会编译测试临时 C 辅助程序，不是 SDK 构建。后续按同一新安装包串行执行，原超时和断言不变，首次预计四分钟后检查。完整 G17/G18 仍未通过。

索引 94..104 原句柄 33691 退出 1：73 项选择中执行 38 项、37 通过、1 失败、0 跳过，46.235 秒，`batch-94.result.json`。失败在 pending settlement 夹具的 ready.wait(3)，原现场 `/tmp/sdk-double-settlement-contention-bc9fpa8o/evidence.json` cases 为空。夹具持有 Kernel control 锁后放行 handler，并等待 `_outcome_result`；当前旧线程的 serialized 返回采样也需此锁，先变未知因而不会构造已知结果。测试改为在 capture 原结果已构造后再施加原独立 journal writer 和 lifecycle 锁，capture 仍等 admitted 才返回。原五秒预算、三秒等待、精确原结果/单次业务/下一请求排队/恢复/关闭重启断言不变。独立审查确认该夹具目标为已知结果双重结算竞争，不需同时阻止原始时钟采样。

产品未改；新安装包冻结修正测试完整模块两项通过、0 跳过，8.366 秒，`/tmp/sdk-legacy-expiry-candidate-20261106/{pending-result.json,pending-tests.log,verify_pending.py}`。历史失败保留，不以此推定其他未知采样问题解决。尚未执行的索引 99..104 串行继续，首次预计两分钟后核对；仍未关闭完整 Gate，无模型请求、无 CI。

索引 99..104 原句柄 99338 退出 0：六模块 34 项全部通过、0 跳过，34.618 秒，`/tmp/sdk-legacy-expiry-regression-20261106/batch-99.result.json` 及原日志。当前本轮无存活测试句柄。后续索引 105..183 尚未完成，不将此前其他候选通过自动合并为当前结果。

下一范围 105..124 的只读审查提醒：`test_request_results.RequestResultTests.test_late_result_survives_producer_process_exit` 将子进程 PYTHONPATH 设为冻结 source/src，需在测试中保留实际安装来源后才能作为安装包证据，不直接执行再冒充安装包。provenance 的 corrupt_registry/disposal_tombstone/stale_tampered_plans、request_results 的 result_digest 变更用例、retention 的 tampered_plans 及 runtime_bindings 前两项显式 binding 校验还需逐项按禁止新增 hash/checksum/fingerprint 验证的范围判定，在执行前写入明确范围记录；原 deferred-v2 不覆盖它们。纯业务身份拒绝及禁止调用 hash 的负向守卫不应仅因底层使用身份计算就排除。此处为审查提醒，不表示这些测试已执行或通过；没有启动下一批。

索引 105..124 执行前范围收敛：`deferred-v3.json` 在原 24 项基础上新增七个明确的 digest/authentication/revision binding 验证，合计 31 项全局暂缓，不计通过或不适用。准确 ID 位于 `/tmp/sdk-legacy-expiry-regression-20261106/deferred-v3.json`。request_results 子进程测试已修改为继承父进程实际 dispatcher_sdk 导入根，并在子进程断言精确模块路径与父进程一致，保留原进程退出及持久结果断言、20 秒超时。源码测试和单独冻结 overlay 都保留此修正；未改产品。包外 `run_batch_v3.py` 显式加载 overlay，manifest 标明路径；其他测试继续引用原冻结闭包。原句柄 61115 启动，预计六分钟后首次核对，无模型请求、无 CI；本批结果未出前不推定通过。

索引 105..124 原句柄 61115 退出 1：选择 157 项中执行 17 项、16 通过、1 失败、0 跳过，8.546 秒，`batch-105.result.json`。失败为 received checkpoint 的不存在 token 负例仍期待旧 clock floor 错误；当前 supervision 的 marker-none 分支先要求 exact token/execution/store/input acknowledgement receipt。测试更名为 `test_missing_token_replay_requires_exact_acknowledgement_receipt`，核对新错误，保留 guards/limits/watermark/owners 原样不变断言；不能把这两个输入写成独立 floor/domain 合并验证。

完整模块初次修正运行 12 项中 11 通过、1 失败，10.941 秒，`/tmp/sdk-legacy-expiry-candidate-20261106/{received-tests.log,received-first-result.json,test_received_budget_checkpoint.first.py}`：positive_fact_ack 用例仍断言收据 error，而当前 completion_time_unknown 的原权限未确认分支明确保留 pending 并报告 unknown。测试更新为准确 pending 且恢复报告原完成权限未确认，仍检查没有业务结果、原时间错误保留和 budget fact ACK，不放宽为任意状态。独立审查确认两个测试调整均对应现协议，产品未改。最终完整模块 12 项全部通过、0 跳过，11.139 秒，received-final-tests.log/received-result.json。

原 batch105 的 manifest 另含 request_results 的 loader 错误（因 failfast 尚未执行，不计SDK失败）：包外显式 overlay 仅注册 sys.modules，没有给 tests 包设置对应模块属性；`run_batch_v3_fixed.py` 补齐父包注册，未改 SDK。原输出不覆盖。索引 108..124 在修正入口继续，原句柄 50880，首次预计六分钟后检查，无模型请求/CI。完整 Gate 未关闭。

索引 108..124 原句柄 50880 退出 1：139 项选择中执行 9 项、8 通过、1 错误、0 跳过，3.031 秒，`batch-108.result.json`。八项 supervisor diagnostics 完整模块通过；分页夹具 `_begin_budget_sample` 尚无 admitted execution limits，准备失败。该夹具还建立 52 个实际 unresolved sampling marker，再期望 later 结果成功；这可能与当前全局采样权威冲突。未延长期限、未直接写库补预算、未把准备步骤报为分页产品缺陷，也未将该模块计通过；独立审查继续核对忠实的公平性验证路径。

与该失败独立的索引 110..124 使用同一安装包和 run_batch_v3_fixed 继续，原句柄 49584，预计六分钟后首次检查。先前 request_results loader 错误已从本次完整选择清单消失，显式 digest 用例出现在 deferred，修正的真实子进程导入路径待实际执行结果核对。当前仍有未完成分页模块和后续125..183，完整 Gate未通过。

分页夹具经独立审查改为 52 条真实持久的 completion_time_unknown 收据，不创建全局采样标记；名称改为 unconfirmed first page，避免宣称仍覆盖原 clock-unknown 采样场景。真实 journal.record 和 Runtime.recover_completions 推动游标，不再直接 UPDATE cursor；保留每页50上限、120次有界扫描、在途行跳过/随后重访、后来准确结果提交、原未决 payload/监督义务不变、重启游标和未知报告断言，首页明确核对原完成权限未确认错误。合成 cleanup 仅是 fixture，不能作为宿主清理证明。该新安装包冻结模块通过1项、0跳过，11.674秒，`/tmp/sdk-legacy-expiry-candidate-20261106/{pagination-result.json,pagination-tests.log,verify_pagination.py,test_recovery_pending_fair_pagination.py}`。产品未改；原采样准备失败仍保留，不能凭此声明全局未知采样不阻塞其他提交。

索引110..124 原句柄49584退出1：130选择项中执行62项、61通过、1失败、0跳过，31.755秒，batch-110.result.json。request_results 同安装来源子进程退出用例实际通过；显式digest用例保持排除。失败为 runtime_budget_outcomes 原生rawfailure路径，`/tmp/sdk-terminal-budget-outcome-er3u7iie/evidence.json` 保留第一原生packet可信按时返回、宿主归一化阶段才注入预算到期；第一准确收据为原始失败、监督已接受、进入queued，第二attempt在入口期限不足变dead，处理器调用日志仅attempt1。旧fixture期待先None再host决策，且假定原结果被迟到归一化为timeout；该预期是否已过时正在独立核对，不能将其直接报告成模型/业务重放或未修复产品缺陷。未修改该产品路径或放宽断言；该模块和119..124尾项未计通过。当前所有测试句柄已终态，完整Gate仍未通过，无真实模型请求/CI。

runtime_budget_outcomes 的过程假设进一步核对后，曾尝试只对 process 分支保留按时原结果、去除旧 host-retry 门槛，并保留未来入口预算/单次处理器/原收据断言。该尝试未通过：完整5项仅1通过、4错误，10.788秒，`/tmp/sdk-legacy-expiry-candidate-20261106/{outcomes-tests.log,outcomes-result.json,test_runtime_budget_outcomes.py}` 保存原冻结尝试。其中原生rawfailure本次第二run返回None，与原batch110场景不同，不能推广固定结算时序；三项线程相关用例缺 observed-after-rollback.json，原因尚未定位。已仅撤回本轮该 run_expired_completion 函数的尝试性改动（恢复原冻结对应函数，文件其他既有改动保留），不将未验证改写留作修复成果。原生已知按时结果应保留、未来不得越过原预算这两个约束不变；该模块保持未通过，需要准确事件/异常诊断而非再次盲目修改断言。产品候选未改，未重跑真实模型或CI。

预算结果模块继续诊断：线程处理器在已接受预算过期后再次调用 context.budget 会触发新的采样并失败；改为对已接受 envelope 作只读投影，仍验证回拨不恢复预算。原生已知按时返回保留原结果；到期后的重试按原 next_attempt_at 固定时钟执行。单次 run_once 可因诊断所有权暂时返回 None，测试改为一秒内允许开始有界恢复/准入尝试，逐次保留排除/恢复/快照证据；单次调用不保证在该一秒内返回，不宣称严格一秒端到端控制。独立审查无本范围阻塞，原工作预算/约束及单次处理器断言不变。

安装包 outcomes-repaired-result.json 为5项4通过1错误（11.020秒），旧单次原生准入失败保留。修正后的 outcomes-bounded-result.json 仍为5项4通过1失败（12.158秒）：原生失败用例通过，但关闭重开用例三秒屏障未达；不能据此关闭模块。只为该屏障增加失败现场线程栈和 driver 结果采集，没有改三秒超时。定向 outcomes-barrier-result.json 为1项通过、0跳过、2.706秒；这次通过不解释前次间歇失败，不将两次结果拼作完整模块通过。所有文件位于 /tmp/sdk-legacy-expiry-candidate-20261106，原日志/冻结测试保留。产品未改变，无模型请求、无CI、无新增完整Gate通过。

索引119..124原句柄72959退出1：64项选择中执行32项，31通过、1失败、0跳过，19.801秒，/tmp/sdk-legacy-expiry-regression-20261106/batch-119.result.json及原日志。失败为 test_reopen_acknowledges_original_sample_and_settles_original_result 的第二次两秒 recover_completions 返回 pending / completion recovery operation window elapsed；尚不能判定为夹具还是产品缺陷，不延长超时或改为接受pending。后三模块及该失败后的用例未执行。源码检查发现同模块另一个已执行fixture通过journal._connection直接DELETE临时settlement_records，原范围审查未拦截；不把该用例计作符合禁止直接改内部数据库约束的有效证据，后续须先替换为受支持准备接口才可重跑。没有修改真实Run。该批终态，无存活测试句柄，无模型请求或CI。

检查点恢复fixture修正：移除 deferred_resolved_result 用例的 settlement_records DELETE；在崩溃子进程首次 journal.record 时选择性构造 exact completion_time_unknown mapping，保存真实原始 ExecutionResultV2 于 resolved_result，仅匹配目标执行，断言恰好一个原始插入及准确保留。真实 lease/未采集checkpoint/无业务结果/监督未决/重启断言不变。这是明确合成收据，不宣称真实运行时产生该返回权限。独立审查无阻塞。当前安装包单项1通过、0跳过、2.271秒，checkpoint-deferred-result.json。

第二次恢复超时的窗口核对：timeout_seconds=2是总窗口，普通收据每次仍有100ms operation_deadline，因此旧错误不能解释成两秒总时限耗尽。测试只增加耗时与最终结果/监督义务/准确收据的保留现场，不增加恢复次数或窗口；checkpoint-reopen-result.json单项通过2.318秒，未复现原失败，不宣布根因修复。最终冻结该模块8项全部通过、0失败/错误/跳过、15.806秒，checkpoint-module-result.json/checkpoint-module.log/verify_checkpoint_module.py，实际导入当前env，冻结 test_runtime_captured_checkpoint_recovery.diagnostic.py。全部文件在 /tmp/sdk-legacy-expiry-candidate-20261106。原batch119失败保留为间歇风险，原业务预算不变；未运行后三个模块、不新增整Gate通过、不调用模型或CI。

索引122..124原句柄70714退出1：31项选择中执行5项，4通过、1失败、0跳过，2.023秒，/tmp/sdk-legacy-expiry-regression-20261106/batch-122.result.json。child admission deadline完整四项通过。失败为直接invoke_process_handler fixture只读取admission_budget而未持久准备，worker报budget sampling requires admitted execution limits。两处直接原生调用补现有prepare_execution_budget，不直接写库，不提前启动执行期限；独立审查确认准备接口及父约束参数仍保留。当前安装包冻结两用例通过、0跳过、2.493秒，deadline-prepared-result.json；父期限用例实际验证运行中worker被原父约束终止。

随后完整deadline及原生durable retry两模块27项，24通过、3失败、0跳过，41.316秒，/tmp/sdk-legacy-expiry-candidate-20261106/deadline-module-result.json及deadline-module.log。原生durable retry用例通过。失败为 uncaught_child_failure 的thread子例原父结果暂不可得，以及fail/crash入口确认两用例仍期待pending envelope约束为空、实际保留execution:probe约束；尚未核对其协议差异，不放宽或删除断言，不将整个模块计通过。原失败日志保留；本轮无产品修改、模型调用或CI。

后续modules[125:145]增加内部SQL准备审查：13项发现直接内部表DDL/INSERT/UPDATE，准确ID和原因在 /tmp/sdk-legacy-expiry-regression-20261106/scope-internal-sql-125-144.json；暂缓待受支持准备替换或准确范围判定，不计通过/不适用。deferred-v5.json合并后45项，run_batch_v5.py使用该清单；新批尚未启动。原始大记录变更和脚本产物未改写。

父子拒绝交付现场 /tmp/sdk-provider-child-failure-thread-w0i_6mf0/evidence.json：子结果完成时间已知、父保留相同provider_denied原异常，但父非序列化采样出现completion_clock_original_floor_unproven，bounded诊断为floor_without_ack/ack_state=thread，后续恢复明确original completion authority is unconfirmed。这不是增加维护等待能解决的证据。runtime.py旧异常fallback改用既有序列化采样，限定非managed、kind=error且入口回调已写started_at，沿用entered deadline；其他结果保持旧路径。started_at仅证明入口回调发生，可能仍在握手，不能声称所有都已执行业务。独立审查无窄范围阻塞，原租约/结果CAS/未知失败权限不改变。

入口确认fail/crash测试此前假定pending envelope必须为空；实际worker在确认前已采集入口cutoff。fixture记录实际尝试确认的envelope，仍断言pending、业务未执行，并严格比较原constraints/started_at及execution:probe deadline=started_at+3，不删除已接受期限。源码定向父子和crash通过，但一个写错测试方法名产生loader error，/tmp/sdk-legacy-failure-source-20261106.log保留，不称三项全部通过。

当前候选 /tmp/sdk-legacy-failure-candidate-20261106；初次较宽条件构建保留wheel-initial/build.log，收窄后build-scoped.log/install-scoped.log，149个Python产品文件冻结source/wheel/installed直接字节相同，相对legacy-expiry只runtime.py改变，product-delta.json；无新增散列检查。安装包四模块38项，36通过、2失败、0跳过，54.014秒，result.json/installed-tests.log/verify.py。父子原始拒绝交付包含thread/process子例通过。剩余失败：worker_confirmation_failure的首生成result与准确提交result不同；thread_return_preserves_expired_floor仍running并保留late_thread_fact而非queued。原始结果不丢、未知权限不擅自补齐；未放宽断言或宣称整模块通过。新失败保留，完整Gate未关闭，无真实模型请求/CI；当前测试句柄38190终态退出1。

入口确认结果差异核对：/tmp/sdk-worker-entry-fail-o3t38h9a/evidence.json 首生成4058…是live_preentry_refusal临时timeout，outcome保留_sdk_completion_decision_error={phase:preentry_refusal,exception_type:StorageIsolationError}，未提交；第二个f38…是实际entry_confirmation_unknown原始失败并与Kernel终态一致。fixture不再把每个_outcome_result候选都视为接受的原结果：在真实_settle_outcome消费范围以线程局部标记记录settlement_results，保留全部original_results，仍逐字段比较同代准确生成结果与最终收据；fail场景出现额外候选时须保留明确失败决策。当前安装包冻结test_runtime_deadline_envelopes.selection.py单项通过、0跳过、1.927秒，entry-selection-result.json/entry-selection.log/verify_entry_selection.py，产品未变。源码首次定向同用例通过1.944秒，/tmp/sdk-entry-failure-selection-source-20261106.log。原整组失败不被覆盖。

旧线程预算到期的下一阻塞已定位到实际竞争边界：监控可在durable过期floor已可见、completion尚未发布时先进入revoke_for_monitor；legacy且published_timeout=None会清active但不提交监控timeout，随后只能late_thread_fact。不能简单把park_timeout条件扩展到所有legacy：返回回调和旧异常归一化目前没有被completion_gate完整隔离，按时返回但采集尚未发布时可能被错误改成超时。独立审查明确反对此直接扩展，未实施该改动。后续修复需先隔离返回/失败边界与监控撤权，再验证“尚未返回即过期可判timeout”和“按时返回采集暂停后过期仍保留准确结果或unknown”两种确定性顺序，兼顾停止、旧租约、未决/其他代效果；不能给业务新时间或把持久late事实当新提交权。该风险仍未解决，未新增整项Gate通过。


## 最新 legacy arbitration 候选：未完成验收

安装包证据 `/tmp/sdk-legacy-arbitration-candidate-20261106/{result.json,installed-tests.log,product-delta.json}`：46 项测试，4 个失败断言，0 error/skip，82.567 秒；不是完整回归，未新增关闭任何完整 Gate。产品新增的调用区间标记与 handler 自身过期观察，仅允许真实 handler 线程在实际调用区间内取得的可信过期观察支持未发布的旧线程超时决定。新增仲裁模块三项通过；不得把这些结果扩大成 G06/G12/G17/G18 已通过。

四个失败及下一动作：

- 重开预算收据比较：原始现场 `/tmp/sdk-runtime-budget-reopen-7jcit7zu/evidence.json`。`originals[0]` 是缺少 budget_envelope 的监控临时候选；持久收据对应 `originals[1]`，具有原 handler 观察的预算。不能只凭首次 normalization 判断丢失原结果。
- 针对该测试尝试以线程局部 settlement 标记排除临时候选，独立安装包运行 `/tmp/sdk-reopen-selection-20261106/output.log` 在原三秒 barrier 失败（3.353 秒），现场 `/tmp/sdk-runtime-budget-reopen-81w1h1pp/evidence.json`。监控已提交结果时 settlement 会复用结果而不重新 normalization，因此该观察方案不完整，已撤回，原断言和超时保留。下一步须在实际收据接收边界观察结果，同时保留写锁阻止完成的原验证目的，不能仅挑选与收据相同的结果。
- unknown completion 顺序测试两个子例：测试在 `_monitor_budget` 内等待发布，但实际调用持有 completion_gate，新返回路径也必须取得同一 gate；另 capture wrapper 未接收实际调用的新关键字参数。这两处需重构忠实的并发顺序夹具；当前没有通过证据。
- managed 命令截止重试测试：返回 running，monitor decision 回调未进入；尚未确认根因。不得改成接受 running，也不得延长截止掩盖失败。

本轮只运行上述一个有界重开测试，没有模型调用、子代理或 CI。全量合同和平台缺口仍按本表保留。


### 顺序夹具修正与命令截止诊断

`/tmp/sdk-monitor-deadline-diagnostic-20261106/{output.log,evidence.json}`：同一安装包的命令截止原单项通过，3.071 秒；观察器仅记录并转发原调用。捕获一处 `_monitor_budget` → `_capture_budget` → `_sample_budget` 的 Kernel control admission 超时，随后真实 monitor 决定 timed_out，attempt=1，无第二次 handler 入口。该单次通过不能解释原 decisions=[] 的失败，也不能关闭 G17。

`tests/test_runtime_unknown_completion_monitor_order.py` 已修正旧夹具：等待移到采样锁释放后的视图消费处，capture wrapper 转发关键字参数；串行采样不产生旧的重试 proof，改为核对实际 unknown 原因在发布和持久 deferred 中保持一致，继续要求 completion_time_unknown、原业务值、单次真实 handler 调用和两个监控失败子例。因为新的串行采样会在原工作窗口内等待 guard，而夹具由自身持有 guard，故显式将这一次故障注入采样限制为至多 0.1 秒；业务十秒期限、原三/四秒协调等待不变。此证据证明发布优先顺序，不证明十秒采样故障恢复或旧 proof 恢复语义。

保留初次修正及第二次失败 `/tmp/sdk-monitor-order-fixture-20261106/output{,-v2}.log`；最终冻结输入 `test_runtime_unknown_completion_monitor_order-v3.py` 和 `verify-v3.py`，安装包测试 `output-v3.log`：1 方法、两个子例通过，2.311 秒。未修改产品，未重跑全量46项，不得将历史四个失败直接改写成当前整组只剩两项。重开预算收据观察仍待修复，命令截止间歇失败仍待解释。


### 重开夹具确定顺序与组合验证

`tests/test_runtime_budget_outcomes.py` 的重开测试保留原 normalization→外部 SQLite writer 屏障，另用线程局部标记识别真实 settlement normalization。真实 handler 在自身读取可信过期预算后，保持调用活跃至 live monitor 开始 normalization，明确选择超时收据恢复路径；不以回调先占 gate 的未知完成路径替代。原三秒屏障、十秒执行预算、九十秒租约、收据逐字段比较、重开预算不回退及不重复调用断言保留。

第二次尝试仍因未选择确定顺序而未触达屏障，`/tmp/sdk-reopen-selection-20261106/output-v2.log`（3.357 秒）；最终单项 `output-v3.log` 通过2.679秒，现场 `/tmp/sdk-runtime-budget-reopen-d0oh9myo/evidence.json`。独立只读复核在重开和顺序两处夹具限定范围内未发现具体阻塞，不是整体验收。

同一安装包实际组合验证 `/tmp/sdk-arbitration-affected-regression-20261106/{verify.py,result.json,output.log}`：12项，11通过、1失败、0 error/skip，35.740秒。重开测试再次通过，顺序两个子例、监控超时模块和仲裁模块通过；失败为 `test_thread_return_preserves_expired_floor`，现场 `/tmp/sdk-terminal-budget-outcome-zacpb8gf/evidence.json`。实际 handler 已观察过期，保留 `_sdk_return_expiry_observation` 的 timeout 最终仍进入 late_thread_fact，Kernel 无最终结果。该失败与此前旧线程待结算问题等价，产品尚未稳定闭合，不能用新增夹具通过代替。原命令截止间歇失败也尚无完整解释。下一步只诊断该原始路径，不盲目重跑组合或模型请求。


## 旧线程发布锁竞争：新安装包48项通过

候选 `/tmp/sdk-legacy-gate-window-candidate-20261106`，相对 arbitration 候选仅 `execution_kernel/runtime.py` 改变；149个 Python 产品文件 source/wheel/installed 逐字节一致，见 `product-delta.json`。构建和安装日志保留；环境仍继承系统依赖，不声称隔离依赖解析。

确定性新增 `tests/test_legacy_published_timeout_gate.py`：真实 handler 在实际调用区间内读取可信过期预算，真实发布 timeout 时保持 completion_gate；测试 gate 观察第一次非阻塞获取失败后，分别释放锁或一直持有至前台返回。原源码基线 `/tmp/sdk-published-gate-baseline-20261106.log`：2项1失败，正例返回 running，持续占锁反例通过（2.214秒）。这是发布窗口的直接复现，不声称已经还原所有历史失败的唯一调度顺序。

修复仅在 invocation-local handler-owned expiry proof 存在时，让仍有权限的前台监控器将锁准入和 Kernel timeout CAS 共用一次0.1秒控制期限；消费已发布结果时复用同一期限，不重新计时。没有该过期证据时仍不等待，无法准入或已转交则保持未知。移除仅凭 legacy_boundary_started 排除已证明过期调用的条件；停止、准确发布对象、租约、代次、时钟、副作用和生命周期检查仍保留。该控制期限不延长业务执行，也不授予 late fact/recovery 新提交权限。

独立只读复核在上述范围内未发现具体阻塞，指出新增两项不替代停止/副作用覆盖。源码新增两项和原仲裁三项全部通过15.017秒，`/tmp/sdk-published-gate-fixed-20261106.log`。新安装包原46项加新增2项完整组合 **48通过、0失败/error/skip，87.051秒**，`{verify.py,result.json,installed-tests.log}`；涵盖预算结果、重开恢复、期限协议、原生入口、监控副作用拒绝、未知发布顺序、命令截止重试和旧线程仲裁。

这关闭了该48项组合的当前失败，不删除历史间歇失败，也不关闭任何完整G01–G18 Gate。尤其G06真实多轮、G12原截止现场、G15真实用量和完整旧API/平台仍需按原合同验证。未运行模型、CI或全项目回归，未修改ModPort或内部数据库。


## 当前安装包旧API剩余范围：首批40项通过

`/tmp/sdk-gate-window-remaining-regression-20261106/batch-125.{manifest.json,result.json,log,progress.jsonl}`：当前 gate-window 安装包，冻结工作区 tests 输入，五模块40项全部通过，0失败/error/skip，80.347秒；原超时/断言不变。范围为 RuntimeHost、Linux进程树取消、LargeHandoffRetry（除下列一项）、嵌套进程取消和容量。实际包含父子进程派生和清理、准确代次交付，不以mock替代这些真实进程子例；模块内其他隔离控制测试按其自身范围解释。

明确暂缓 `tests.test_runtime_large_handoff_retry.LargeHandoffRetryTests.test_lost_journal_ack_reconciles_exact_committed_retry`，因直接UPDATE内部execution/event；保留在manifest，不算passed或不适用。测试解释器和主包实际导入路径位于当前候选env。该批不是184模块全量回归，G17整项仍未通过。无产品改动、模型调用或CI。


### 尾段批次145：17项通过，1个模块导入错误

`/tmp/sdk-gate-window-remaining-regression-20261106/batch-145.{manifest.json,result.json,log}`：SDK恢复、SDK结果、脚本唤醒端到端、指定收据消费者四模块17个实际测试通过。第五模块 `tests.test_sqlite_contention` 因冻结source缺少 `scripts` 而导入失败，loader以1个_FailedTest计入18项、1 error，总26.412秒。该模块两个真实用例均未执行；不能将result.json的complete_selected_scope=true解释为该模块已完成，也不把它计作通过。

父代理沿缺失依赖追查发现 `scripts/benchmark_sqlite_contention.py:434` 在run_benchmark返回环境信息时实际计算implementation_sha256；此前只读审计把该模块列为safe不完整，已要求追踪必要helper并纠正。没有补依赖后盲目重跑，也未运行该摘要路径。至少 `SQLiteContentionBenchmarkTests.test_small_multiprocess_run_reports_latency_and_correctness` 暂缓；另一容量故障注入用例需进一步核对直接数据库操作边界。该批原始导入错误保留，缺失依赖不伪装成产品失败或完整通过。

截至此处，当前gate-window包两批新增40+17个实际测试通过，仍有明确暂缓和未执行范围；这些与48项定向验证分别保留，不宣称G17完整通过。


## 剩余旧API批次132：发现预算无感知处理器兼容性缺陷

当前包 `/tmp/sdk-gate-window-remaining-regression-20261106/batch-132.{manifest.json,result.json,log}`：选择104项，failfast实际运行9项（8通过、1失败），0error/skip，21.533秒；余95项未执行。失败 `RuntimeObservationCleanupTests.test_revoked_handler_cannot_start_observer_after_storage_cleanup`：原0.2秒期限、处理器一直等待release且不调用context.budget；两秒原恢复观察窗后仍running/result=None，无法进入原终态及清理断言。

代码核对确认当前handler-owned expiry限制对不主动读取预算的旧线程处理器造成兼容性缺口。该测试的业务调用并未返回，不能将缺少终态归因于测试的恢复等待短，也不能给handler添加预算读取或改成接受running。此前48项和57项通过没有覆盖这个输入类别，不证明旧API超时合同已完整恢复。

限定独立复核认为 `_handler_invocation_active` 标记本身无法证明真实调用在到期时仍活跃：存在物理返回与finally清除标记间的暂停窗口。仅检查invoke锚点之上的任意Python帧也不安全，跟踪/性能分析回调可处于该位置。更严格的直接子帧、准确函数代码与原参数绑定，在正常无原生跟踪干预的CPython函数/绑定方法范围内可作为后续设计方向，但尚无实施与验收；不透明C调用和任意原生仪器仍缺证明。此处保留为产品缺陷，不以测试改造关闭。

尾段审计补充：SQLite容量用例依赖的 `run_capacity_limit_exercise` 会暂时解除Kernel连接authorizer并直接设置max_page_count；尽管不直接写业务行，也未据此扩大本任务允许的内部数据库操作。该用例继续暂缓，未执行；不能把独立审计列为safe代替父代理核对。其多进程基准另有implementation_sha256路径，亦未执行。


## 活跃真实处理器的到期证明：新候选验证中

当前候选 `/tmp/sdk-legacy-live-callee-candidate-20261106` 相对 gate-window 候选只改 context.py、_process_runtime.py、runtime.py；149 个产品 Python 文件 source/wheel/installed 直接逐字节相同，见 product-delta.json，无摘要验证。环境继承系统依赖，不证明依赖隔离。

原预算无感知函数及绑定方法测试在旧安装包各失败一次（返回 running），返回后 tracer 暂停反例通过：`/tmp/sdk-live-callee-baseline-20261106.log`。实现先取得可信过期预算，再通过线程栈核实实际 invoke 锚点的直接子帧、函数代码身份和原 payload/context 绑定；证据仅存于本次前台调用，不保存帧或局部变量。处理器物理返回后的 tracer 帧不满足身份。不透明调用、参数重绑定、不可见/过深堆栈及任意原生插桩仍无证明，不声称旧 API 完整兼容。

原源码8项组合 `/tmp/sdk-live-callee-source-20261106.log` 为7通过1失败：入口回调推进预算后立即允许真实处理器进入，监控可取得真实调用活跃证明，与“纯入口读不能授权”的预期发生调度歧义。固定入口暂停至前台返回，保留原无超时决定断言，新增释放前尚未调用处理器的断言，释放后等待原 late owner future。第二次8项全部通过20.724秒，`/tmp/sdk-live-callee-source-v2-20261106.log`。独立复核指出外部线程读的子例同样存在真实调用调度歧义；最终冻结版本将两种读均置于真实处理器进入之前，分别验证本线程和外部线程读不会独自授权。原5秒业务预算、2秒外部读等待及原结果断言保留。最终夹具仍需新安装包结果，不把中间8项通过冒充最终验证。

新安装包 verify.py 冻结9模块：原48项、新活跃调用2项、原观察器清理模块11项，共61项；原断言/期限保持，执行日志 installed-tests.log，结果待定。无模型请求、CI、ModPort修改或内部数据库写入。此工作未关闭任何完整G01–G18验收项。


### 验证器入口错误及独立线程身份覆盖

首批 verify.py 遗漏 `if __name__ == "__main__"`，原生spawn子进程重新执行测试套件，`installed-tests.log` 的混杂失败不是有效61项结果。原句柄92607已终止exit143；通过准确脚本路径定位原PID及其两个子进程，身份与退出核对见 invalid-run-processes-host.json、invalid-run-cleanup.json（live_original_processes为空）。不使用进程模糊匹配或清理其他任务。修正仅在 verify-v2.py 加入入口保护；保留原验证器和日志，再执行同一冻结61项，installed-tests-v2.log，结果仍待定。

独立复核确认前述入口前正交两种读取反例，但指出不再覆盖真实处理器活跃期间的外部线程身份限制。新增独立 `test_foreign_read_during_actual_handler_does_not_mint_handler_observation`，真实外部线程读取可信过期预算，要求活跃处理器标记为真而handler-owned expiry仍为空；允许前台另由真实调用栈证明到期，不混淆两种权限。冻结在 foreign-read-supplement/fixture.py，当前安装包独立1项通过，0失败/error/skip，1.830秒，output.log/result.json。此补充与61项冻结范围分列，不覆写其输入。


### 有效安装包批次：59通过，2个原生期限失败

`verify-v2.py` 正确入口保护下原句柄34348退出1；`result.json`、`installed-tests-v2.log`：61实际方法，59通过、2失败、0error/skip，115.735秒。原观察器清理11项、新预算无感知函数/绑定方法、返回后tracer反例、前入口两种读、发布锁窗口等通过；加上独立外部读1项，分别记录，不合并成整批全绿。此处不重跑失败以寻找偶然通过。

失败1 `RuntimeDeadlineEnvelopeTests.test_parent_work_deadline_stops_already_running_real_worker`：原2秒parent限制、0.5秒reserve不变；真实blocked函数仅写PID文件、sleep30、写late，不读预算。但backend返回handler_error/TimeoutError：Kernel control admission budget elapsed，completion_time_known=true，完成预算仍有1.081秒work。不能归因于函数业务耗尽期限，也不把异常归一化成timeout。原夹具临时目录会清理，只有日志outcome，缺准确产生栈；下一定位应围绕业务前入口/预算控制路径捕获原异常传播，不能仅凭同名错误判定锁来源。

失败2 `test_real_child_stops_at_inherited_parent_deadline`：保留 `/tmp/sdk-inherited-parent-deadline-aaimv50b/evidence.json` 及storage现场。parent实际进入后按原5秒预算timed_out，但child未进入实际业务。child backend已返回 handler_error/BudgetClockUnknownError: budget_clock_sample_unresolved:sampling，completion_time_known=false，遥测关闭仍有owned budget checkpoint pending，原因OperationalError/database is locked。完整invocations与callbacks保留；其未触发on_entered，因此不能称为子处理器运行后正常被父期限终止。该现场不支持唯一锁栈归因，也不关闭G06相关未知预算采样问题。

独立源实现审查限定于正常CPython函数/绑定方法、无恶意原生插桩的正向调用证明，未发现具体阻塞；不替代不透明调用/平台兼容性。G01–G18仍未完整通过。当前先定位这两个原生业务前预算失败，不扩大CI或真实模型回归。


## 业务前原始异常诊断与旧原生入口的有限重试

诊断候选 `/tmp/sdk-entry-diagnostic-candidate-20261106` 相对live-callee只改 `_process_runtime.py`：入口捕获的原handler_error附加现有有界bootstrap诊断（无locals，保留原分类/消息/堆栈），不把TimeoutError改为业务超时。149个产品Python文件source/wheel/installed直接一致，product-delta.json。3项（诊断检查+原两个原生期限用例）通过，result.json/output.log，10.279秒。没有改两个原用例的控制逻辑，这次未复现失败，因此不能宣称间歇故障已消除；旧现场仍有效。

新 `tests/test_legacy_entry_admission_retry.py` 确定性复现两个独立旧入口缺口：真实外部SQLite连接只持BEGIN IMMEDIATE后rollback、不写内部表，0.25秒争用就让仍有原1秒startup窗口的context提前handler_error；入口实际提交后注入TimeoutError确认中断也直接失败。基线最初因错误import未执行，`/tmp/sdk-legacy-entry-retry-baseline-20261106.log`；修正导入后的两个真实预期失败在 baseline-v2 日志，准确堆栈分别指向 `_capture_budget` 短窗口和 `record_execution_budget`。这些证明对应缺口，不证明此前间歇现场唯一原因。

修复context：有原startup期限时，旧入口也使用已有 `_capture_entry_budget` 重试，保留旧调用者clock及lease；原生旧入口发布则在原startup与原work较早期限内重放准确同一entry envelope，caller control deadline覆盖prepare+confirm，不新建业务预算。仅重试TimeoutError/SQLite争用，保留其他错误和未知采样的token/事实身份约束；每次检查执行权限，发布后原剩余工作检查保留。无startup参数的旧调用保留原接口行为。

源码第一次修复检查2项通过、1个测试结果类型访问错误，fixed日志保留；修正dict字段读取并补原期限耗尽与不可重试错误后，`/tmp/sdk-legacy-entry-retry-fixed-v2-20261106.log` 5项通过，1.195秒。原期限耗尽不执行handler；确认中断重试要求同一对象、同一started_at、业务只执行一次。独立只读审查未发现此限定改动具体阻塞，确认Kernel重放不能削弱截止、租约及准入仍复核；单独guarded child失败未归因。

当前候选 `/tmp/sdk-entry-retry-candidate-20261106` 相对诊断候选仅context.py改变；149文件source/wheel/installed逐字节一致，product-delta.json。环境依旧继承系统依赖。冻结67项包含原61、新增活跃外部线程1、旧入口重试4及诊断1；verify.py有multiprocessing入口保护，原句柄76816在运行，output.log/result.json待定。尚不关闭完整G17/G18或任何其他验收Gate。未执行CI、真实模型调用或ModPort写入。


### 当前入口重试候选有效结果：66通过，原线程异常结算1失败

原句柄76816退出1；`/tmp/sdk-entry-retry-candidate-20261106/{result.json,output.log}`：67项，66通过、1失败、0error/skip，122.830秒。两个原生期限用例、原清理11项、真实写锁争用及同entry确认重试、原期限耗尽、非瞬态拒绝、诊断和线程身份检查均通过。guarded child此前失败未唯一归因，不能用本次通过声称原因已修复。独立审查无该有限重试改动的具体阻塞，不证明所有结算路径。

失败 `RuntimeBudgetOutcomeTests.test_thread_raw_failure_preserves_expired_floor`（完整类名以output.log为准）：原10秒工作/90秒租约不变，实际handler自己采样可信过期预算并抛原始original_failure。夹具原要求首轮queued，实际running；`/tmp/sdk-terminal-budget-outcome-pr2lyahl/evidence.json` 保留准确attempt/fence、预算过期floor及原业务错误。收据state=pending，deferred.kind=completion_time_unknown，outcome仍为original_failure/raw original failure/retryable=true，但completion_time_error为 `InspectionBudgetExceeded: inspection timeout exceeded`。无最终结果，不能视为已交付。此观察不足以把该完成采样超时归因于本次入口重试，也没有产生栈可作唯一调用点证明。

下一步沿该实际原始异常→completion capture→deferred receipt追查原检查预算的来源和失效位置；不重跑整批寻找偶然通过，不把未知改为timed_out，不延长原业务预算，不以测试数替代G01–G18验收。当前候选仍未完整通过，Goal保持active。


## 异常返回的过期边界与已提交重试的准确确认

代码检查确认：正常返回在完成采样未知时会保留实际handler已经观察到的可信过期边界，但legacy异常回调未保留，随后异常归一化得到unknown，无法提供相同超时发布标记。新增两个用例让实际handler采样过期后抛original_failure，并强制原完成采样不可用，控制真实completion gate释放/持续占用。旧entry-retry安装包两项均失败（没有过期标记），`/tmp/sdk-expired-failure-boundary-baseline-20261106.log`，2.186秒。

修复legacy observe_failure：仅在同一handler已持有handler-owned expired observation、实际异常边界projection可信且过期时保存该边界；原采样未知不改成known，不构造成功时间，保留原业务异常于details.business_outcome；仍由live monitor以原0.1秒共享控制窗口复核当前代次/lease/clock/effects/stop再决定。独立只读审查未发现该限定变化具体权限阻塞。

首组合 `/tmp/sdk-expired-failure-boundary-fixed-20261106.log` 9项8通过1失败，20.313秒，现场 `/tmp/sdk-terminal-budget-outcome-ucv9k_v7/evidence.json`。两个边界正反例通过，但原异常用例第一返回running，Kernel随后能进入原attempt2并拒绝重新执行。核对发现 `_complete_monitor_timeout` 成功调度重试时合法返回queued/result=None，而Runtime只以终态result确认提交，因此把已经提交的准确重试当作未知。此为与过期边界分开的确认缺口，不将前者通过冒充完整解决。

另增返回与异常、retry与nonretry、发布锁释放与持续占用共8个用例。旧包返回retry正例稳定失败running!=queued，`/tmp/sdk-monitor-retry-receipt-baseline-20261106.log`，1.236秒。Kernel新增只读 `_is_committed_retry_result`，以准确结果、lease代次、提交revision及同revision retry_scheduled事件确认；当前已进入后续代次仍只能证明旧历史，不能为新代次授权。读取有原deadline/进度中断和256KiB事件上限；Python支持setlimit时在VM物化前限制单值长度，并保留更低的调用方限制且finally恢复。Python3.10缺setlimit，物化限制仍best-effort，未作平台验收。二次结算核验争用仍fail-closed，不能把早先确认等同后续收据已经记录。

Runtime只传递同一已提交candidate及其retry revision；结算重新核对准确事件后，仅记recorded收据，不再次complete。三个无发布timeout返回及已发布路径均带准确revision；不以queued状态本身作证明，无新增内部DB写入或业务预算。

首9项检查7通过2失败为测试将completion Future与executor Future对同一结果的发布重复计数（原业务调用仍一次）；修正只对首次同一发布保存业务字段，保留原错误code/message及unknown断言。`/tmp/sdk-monitor-retry-receipt-fixed-v2-20261106.log` 9项全部通过10.332秒，含原异常用例；第一次日志fixed仍保留。新只读证明3项通过 `/tmp/sdk-monitor-retry-proof{-v2}-20261106.log`：准确历史在新claim后仍可读、错误result/revision/fence拒绝、通过公共complete写入的300KiB结果拒绝且连接limit恢复。无直接fixture内部表写入。

中间 `/tmp/sdk-monitor-retry-candidate-20261106` 为未运行测试的构建，独立复核建议保留已有更低连接limit后已修正，最终冻结为 `/tmp/sdk-monitor-retry-reviewed-candidate-20261106`，不把中间构建算已验收。新旧构建日志及product-delta保留，均直接比较source/wheel/installed，不计算摘要；系统依赖继承限制不变。最终76项影响范围待验证，完整G01–G18未通过。


## 最新安装包影响验证完成与剩余回归阻断

`/tmp/sdk-monitor-retry-reviewed-candidate-20261106/result.json`：76项全部通过，0失败、error或skip，130.8678066秒，原进程退出0。不关闭任何完整G01–G18。

同包剩余10模块93项，`remaining-132.result.json`：2项已执行，1通过1error，91未执行。手工object.__new__创建的Runtime漏了正式构造函数已有的_delivery_reconciler/_delivery_cursor；仅在测试工厂补None，不修改产品、不替换恢复逻辑、不变期限或断言。

新冻结夹具remaining-fixture-v2与验证器verify-remaining-132-v2.py保留原失败输入；remaining-132-v2.result.json为4项已执行、3通过1失败、89未执行，0error/skip，0.0268秒。准确恢复证明用例通过；Windows模拟timely子例预期ok而得到budget_clock_unknown。remaining-windows-diagnostic.log原始结果message为original completion budget is not verified，details.business_outcome为kind=ok。该诊断单例仍失败，不能算通过；诊断驱动未传播unittest失败退出码，故只以日志断言为证据。下一步核对模拟返回包与真实生产者的完成预算字段及消费合同，不绕过权限验证，不据此推断真实Windows平台已验收。未调用模型、CI或改动ModPort。


### Windows模拟生产者合同及未知收据保留断言

产品未修改。真实_windows_runtime._worker_main通过_capture_completion_time及_serialize_handler_outcome产生带原完成时刻、budget_envelope和_sdk_completion_budget_view的包。旧模拟仅kind=ok且entry为空constraints，前者被拒绝，后者在补字段后仍无法证明剩余工作；v3日志保留timeout!=ok失败。夹具改为enter_handler原5秒native工作界限并发布同一entry约束和对应completion view，没有绕过_budget_outcome。

v4已通过timely等子例，随后watchdog_unreadable旧断言要求恢复把未知收据归档error，与当前recover_completions的completion_time_unknown合同相反：没有准确已提交结果时必须保留pending，并报告original completion authority is unconfirmed。夹具的kernel.get补result=None以避免缺字段错误被unknown捕获；断言改为检查pending、原supervisor_return_observation逐值保留、准确unknown原因和原_complete_sdk_result未调用。此为测试合同修正，不能称原断言未改变。v4失败原日志保留。

最终夹具冻结remaining-fixture-v5，原93项范围及deferred清单不变，verify-remaining-132-v5.py继续failfast，结果待定；已请求独立只读复核上述夹具与现有生产者/消费者合同，不以模拟证明真实Windows验收。


最终v5结果：remaining-132-v5.result.json/log，93项选择中13执行、12通过1失败、0error/skip、80未执行，4.308秒，原进程退出1。Windows模拟12种子例及监督恢复、worker凭据传输范围通过；独立只读审查未发现夹具合同修正具体阻塞，限制仍为模拟平台证据。

新失败SamplingRefusalTests.test_retry_admission_expiry_preserves_exact_sql_refusal：原0.1秒、两次准入，真实SQL拒绝BudgetClockUnknownError原对象和消息均保留，但__cause__为None，原断言要求TimeoutError。原现场/tmp/sdk-sampling-refusal-7bbo23lm/evidence.json保留SQL轨迹、准确token及refusal_count=1；尚未确定丢失因果链的实现位置，不改原断言、不计通过。下一步检查_sample_budget重试异常传播，原模型G06/G12问题不因这些模块通过而关闭。


## 预算采样重试拒绝的真实准入因果链

supervision._sample_budget在重试进入control scope后若原deadline已耗尽，原实现直接抛之前SQL拒绝，遗漏本次TimeoutError；另一个_ControlAdmissionTimeout分支显式from None。修复在实际准入耗尽处产生原有TimeoutError，并由已有捕获分支以原SQL拒绝对象from该timeout重抛；未新建token、期限或SQL拒绝。首次仅修from None仍1失败日志/sdk-sampling-refusal-cause-source-20261106.log（完整/tmp前缀），第二次原2测试通过0.640秒，/tmp/sdk-sampling-refusal-cause-source-v2-20261106.log。原断言与0.1秒不变。独立审查未发现权限/期限阻塞；依赖cause-free拒绝的入口重试将对这类已耗尽准入fail-closed，不能宣称所有调用可用性不受影响。

新安装候选/tmp/sdk-sampling-cause-candidate-20261106：产品只改supervision.py，149个Python文件source/wheel/installed逐字节一致，无摘要检查，环境继承系统依赖。原93项范围、45项暂缓清单及修正的监督夹具已冻结，remaining-132结果待定。不自动继承前包76项为新候选通过，不关闭G06/G12/G15/G17/G18。


新候选remaining-132.result.json/log最终27执行、26通过1error、0failure/skip、66未执行，31.323秒，原进程退出1。原采样拒绝2项及监督交接模块通过。新阻断SandboxRuntimeTests.test_explicit_not_applied_creates_new_generation_only_after_old_cleanup第459行：runtime.run_once()返回None，访问.state报AttributeError。现场/tmp/sdk-sandbox-runtime-kafc3gu4/evidence.json及sandbox-before-cleanup.json已保留，尚未归因，不改断言/期限，不把旧代清理成功当新代执行完成。当前产品候选为sampling-cause；76项历史影响范围未在此新包复验，完整Goal仍active。


### 沙箱恢复领取空值的最小诊断

/tmp/sdk-sandbox-claim-diagnostic-20261106.py只包装现有_diagnostic_claim_exclusions记录返回，保留原单例与参数，使用同一安装包；log记录四次(False, ())，原失败用例此次通过4.974秒，退出0。新现场/tmp/sdk-sandbox-runtime-867tvcrr。不能以未复现宣布修复，产品未修改，原kafc3gu4失败仍有效。原失败现场显示公开resolve_effect已把准确旧代从recovery_required排队，但没有领取事件；现有证据未记录当时排除列表/监督义务/lifecycle容量，尚不足以唯一归因。

将该用例加入既有capture_empty_retry触发范围：仅在原run_once返回None时，清理前采集有界只读执行、预算、监督义务、lifecycle producer/outbox及诊断排除列表；原断言、原10秒预算及业务行为未改。未继续无修改重复寻找偶然通过；下一次原范围执行若复现可直接辨认领取阻断，不需要再用清理后的状态推测。此诊断夹具变化尚未在安装包新冻结范围执行。


## 未执行66项的独立续跑

verify-remaining-66.py从原remaining-132.progress.jsonl准确27个finished方法中减去已执行部分，断言选择66项；不把其中失败项加入deferred，不清除原失败。新manifest/log/result以remaining-66命名，原93项输入/结果保留。同一sampling-cause安装包，产品无新修改，结果待定。

领取静态路径已核对：排除列表之外，_next_claim_row还对同代未解决监督义务、任何open或未投递outbox的lifecycle producer、root未完成预算采样加领取屏障。原失败现场缺当时这些事实，不能把空值唯一归因于沙箱或产品错误；新清理前取证覆盖这些判定所需字段。诊断通过不替代原恢复验收。


66项续跑已完成：/tmp/sdk-sampling-cause-candidate-20261106/remaining-66.result.json与log，66通过、0failure/error/skip，107.9015秒，原进程退出0，complete_selected_scope=true。与同包先前26通过1error为不重叠方法，故此93项范围累计92通过、1个沙箱间歇error仍开放，已无未执行方法；不将单例诊断通过覆盖error。显式暂缓45项及其他回归批次另计，不能称完整G17/G18通过。产品采样修复后旧包76项影响验证尚未转移为新包证据。


## 沙箱恢复调用按原工作预算等待可领取

新取证夹具sandbox-diagnostic-v2原单例再通过4.947秒，未复现原领取空值，不据此解释旧现场。run_once明确为at most one claim，诊断排除、生命周期事件未投递等均可合法返回None；原断言直接访问None.state把立即可领取当成合同。修正仅该测试：按原get_execution_limits返回的可信envelope工作剩余期限轮询，deadline取历次原预算投影与本地单调截止的更早者，未增加10秒工作预算，未知时钟/耗尽立即失败。最终实际succeeded、旧清理、operation_key换代、旧sandbox/history归档断言保留。原空值现场仍未唯一归因，不能宣称产品间歇故障已被修复。

独立只读复核未发现此调用合同修正阻塞，确认不能从最终成功推断原None具体原因。最终冻结sandbox-original-budget-v3/verify.py使用sampling-cause已安装产品，单例通过5.042秒、原进程退出0，output.log及/tmp/sdk-sandbox-runtime-nulq4raa/evidence.json。产品未变。这是原93项范围中修正单例的独立结果，与92项批次通过分列，不声称同一冻结93项整批通过；该范围原唯一error已取得合同修正后的成功证据，完整G17/G18及其他Gate仍缺验收。


## 当前候选完整G01验收

使用sampling-cause安装包，在/tmp下以-I执行当前仓库verify_agent_control.py --case G01 --layer integration；/tmp/sdk-sampling-cause-G01-20261106/acceptance.json明确G01 passed。G01.json记录实际site-packages导入、YAML/Python等价、有效配置、duplicate/unknown/constructor/invalid_override四类拒绝、两份Wiki JSON默认值与字段注册表一致、实际CLI validate/config show --effective均退出0且结果等价。未调用模型，未改内部数据库。

补充冻结当前公共配置测试test_agents_spec/test_agents_null_defaults/test_agents_validation于public-api-tests，独立安装包执行：18项通过，0failure/error/skip，原进程退出0，result.json/output.log记录。当前Linux x64 Python3.12范围G01完成；平台矩阵仍在G18单列，其他Gate不随之通过。历史基线表不覆写为新候选证据。


G13当前验收执行均原进程退出0，无模型请求或CI。能力测试冻结当前两个模块并使用-I导入site-packages，5通过0failure/error/skip。其公共App拒绝和直调adapter的Popen未调用检查均通过；不以能力报告或mock调用证明原生隔离。


## sampling-cause候选76项影响补验失败

/tmp/sdk-sampling-cause-candidate-20261106/result.json/output.log：76执行，75通过1error，0failure/skip，155.355秒，原进程退出1。error为LegacyThreadReturnArbitrationTests.test_on_time_return_or_failure_paused_before_publication_is_not_monitor_timeout的before_callback=True/failure=False子例。最初test第222行captured.wait(3)为False（errors=[]）；其后context close在runtime.py:555抛_UnpersistedDiagnosticsError覆盖为最终error。两个失败必须同时保留，不能将关闭错误当第一原因。未延长3秒屏障、1.5秒业务预算或关闭等待；当前候选该范围不通过，不能沿用旧包76全绿。下一检查应核对驱动线程为何未到原暂停点及其准确诊断待投递事实，不能无修改重跑以求通过。

G12独立只读审查核实原两秒用例tests/test_agents_technical_retries.py:609，旧现场2ks_l33z的late_thread_fact无原始异常栈，只有类型计时，无法定位第一因果位置。测试observe_boundary新增至多8级异常链、每级至多16帧，只存file/line/function及类型，不存消息/参数/locals；原2秒预算及断言不变。该取证变化尚未执行，不把它算G12进展通过。下一步先处理上述76项新失败，避免同时启动计时测试引入竞争。


## 线程暂停点与G12原截止的本次定向证据

原线程竞争夹具仅成功时写证据，导致76项首个屏障失败没有业务/线程快照。新增仅失败时的boundary-failure.json，在captured.wait(3)返回False之后保存至多16帧/线程的file/line/function、calls/facts/errors/返回值与公开execution snapshot；不记录frame locals或改变等待期限。冻结arbitration-boundary-diagnostic，当前安装包单方法四组合通过9.526秒，output.log，原进程退出0。未复现不说明原屏障/关闭故障修复，76项失败仍开放；没有整批重跑。

G12冻结当前异常位置取证版原两秒单例于/tmp/sdk-sampling-cause-candidate-20261106/g12-original-stack。受限环境第一次因本机回环端口PermissionError跳过，output.log保留，不能计通过（该临时驱动当时未把skip作为失败，退出0不是验收证据）。随后同一输入在已授权宿主执行，output-host.log：1项通过、无skip，4.178秒，原进程退出0。现场/tmp/sdk-confirmed-abort-expiry-v_ni1dum；真实adapter_entered时原预算剩0.531秒，prepare_entered剩0.439秒，abort_confirmed仍剩0.222秒。原2秒、wait30和无重试/原deadline不变断言均通过，不以40秒伴随例替代。这是当前包的原短窗口正向证据，未解释历史晚abort及其他G12故障分类全部范围，G12整体仍incomplete。


## 当前包G12技术重试分类15项补验

/tmp/sdk-sampling-cause-candidate-20261106/g12-original-stack/classification-manifest.json冻结同一技术重试模块的15方法；明确排除已单列的原2秒用例与40秒补充例，不将40秒例替代原合同。classification-result.json/log：15全部通过，0failure/error/skip，102.3426秒，原进程退出0。覆盖真实SDK效果/预算/监督资源路径中的瞬态未启动重试、耗尽/非瞬态、无效证明/未知效果/清理不明禁止重试、预算未知、取消/租约撤销、setup到期业务前拒绝、旧goal操作不可授权新轮次、监督观察器join及启动不明等。子进程负例均沿原测试执行，无数据库内部行改写或模型调用。

此范围与先前原2秒短窗口合计16个不同方法已有当前包证据；40秒补充例未在本候选执行。适配器为合成native边界，非真实OpenCode提供方失败/返工路径，因此仍不关闭完整G12；真实retries_native、业务拒绝/返工/不明效果完整合同及历史失败因果解释仍需分别核对。没有触发CI。


## 当前候选真实OpenCode预启动重试与耗尽负例

/tmp/sdk-sampling-cause-G12-native-20261106/report.json：verify_agent_retries_native.py通过授权宿主反代、local/gpt-6-luna及既有OpenCode可执行文件运行，当前sampling-cause site-packages来源明确，原150秒请求预算未变。原进程退出0，12个checks全true，host_close_completed=true。正例准确not_launched后同一完整请求/执行attempt/fence/lease/effect/deadline与workspace恢复，原输出RETRY_OK，原agent_calls spent=1，无unknown或残余reserved；原生成功操作cleaned。负例两次不同operation的准确未启动证明，零模型计费，耗尽保持原失败；重投同request ID没有额外adapter进入或结果变化。未修改ModPort，仅使用其现存二进制。

实际正例model_turns spent=2，非单个提供方请求证明。此前用户进度预估说一次模型请求不准确，已明确纠正。独立脚本审查确认此脚本没有新增内部表写入或hash检查，能覆盖一次pre-workdir EMFILE及耗尽身份/预算不变，但未直接计数提供方HTTP请求；不扩张为所有技术失败或HTTP重试保证。真实OpenCode正向证据与合成分类15项、原两秒例分列，G12仍缺完整业务拒绝/返工/不明效果组合核对；G02若复用此证据还需按其进程/会话要求独立核对，不在此自动关闭。


## 复用真实调用完成当前G02核对

未新增模型请求。按G02原最低证据，读取当前G12真实场景的控制库与OpenCode库（mode=ro，未调用任何写入接口）：原SDK结果succeeded/RETRY_OK含非空session_id，结果session与控制记录相同；同一invocation runtime的OpenCode数据库session表中准确ID唯一存在。保留的OpenCode lock meta给出实际PID597302（历史启动证据，不作当前存活证明）；准确原生operation/tree_cleanup receipt与原SDK lease/attempt/fence一致，host_close_completed=true。结果metadata含opencode_version/selected_model/process_cleanup，模型账本spent=2。证据汇总G02-reused-evidence.json只保存相关结果/身份/清理和源路径，不复制lock token或宿主密钥。

由此当前Linux x64 Python3.12安装包G02通过，无需重跑独立writer示例；writer示例的命名产物行为属于G03及示例验证，不能因此删除。venv为新构建但使用system-site-packages，依赖完全隔离与跨平台仍缺G18证据。当前已重新核实G01/G02/G13，其他完整Gate保持未完成。


## 当前候选G03真实文件与产物链通过、G04部分完成

/tmp/sdk-sampling-cause-G03-G04-native-20261106/acceptance.json：G03 passed，G04 partial，原进程exit1是partial被判非完整成功，不是图执行异常。四个真实OpenCode Agent完成seed→fast/slow→consumer；consumer_waited_for_inputs、stable_replay及conflicting_replay=AgentConflictError有效，files_valid=true。G03.json保留真实file_write允许result.txt、../escape.txt被路径校验拒绝、linked.txt被nofollow拒绝的实际决策和实际产物值；消费者输出证明读取两个绑定产物而非仅启动成功。

路径替换竞争原500次：106次替换，1次允许499次拒绝，errors为空，worker停止，外部文件保持原内容。能力限SDK tools，root及祖先须由宿主保护，atomic_write=false/strict_backend=false，不扩张为进程强隔离。

G04缺duplicate_dependency_event_redelivery，明确not_run。独立审查现存verify_agent_dependency_redelivery_native.py可在单个新图中对准确消费事件pre-ack故障后通过真实租约重投取证；目前已完成图没有公开接口重投已ack事件，不能改库或用同root重放替代。下一步该专门场景另立真实执行，不重跑本G03图。当前G01/G02/G03/G13有本候选证据，其余Gate未完成。


## 当前候选G04实际租约重投证据

/tmp/sdk-sampling-cause-G04-redelivery-20261106/report.json：status=controlled_redelivery_passed、stage=closed，原进程退出0。新真实四节点图，pre-ack异常只注入一次；同event_id/scope/epoch重获实际租约，generation1→2且lease改变；first_consumption true→false、same_outcome=true，consumer_entries=1。原consumer invocation/bindings/effect lease/attempt/fence保持相同，最终answer_matches=true、agent_calls=4、model_turns=16、四个原生操作SDK清理回执匹配。private fault hook影响投递时序，不替换模型，不直接改库。

同ID改内容的primitive_conflict负例被拒绝，事务回滚且事件和回执不变；明确其为存储原语负例，不冒充真实宿主接收冲突外部消息。前一真实G03/G04图提供输入未齐不启动、齐备启动以及root重放/冲突证据。已请求独立按G04最低合同合并审查，不将本报告自述的非完整scope误改为单报告完整验收；G14进程崩溃/丢失已提交ack响应与独立OS进程树证明不在此场景，仍缺各自Gate证据。


独立审查已核对两个报告同一installed candidate，确认组合满足G04最低合同；当前Linux x64 Python3.12 G04记passed。原单报告partial和not_run不覆写，保持单份证据范围。不能据此声称后续候选/平台、崩溃恢复、丢失已提交ACK或独立OS清理完成。


## 线程暂停点失败：原顺序前驱范围核对

`/tmp/sdk-arbitration-predecessors-20261106/result.json`、output.log：同一sampling-cause安装包，按原76项批次顺序执行发布门、预算结果、线程返回仲裁三个模块，共17项通过，0failure/error/skip，37.909秒，原进程退出0；各原预算/暂停屏障不变，无模型调用。此为新增前驱组合证据，未复现原错误，不关闭76项失败，也不证明模块间无任何影响。

独立只读审查确认run_once只承诺至多领取一个任务，可在诊断背压或资源准入时返回None，故测试单次调用后等待callback并不能唯一定位产品故障。原失败缺当时results、calls、线程栈，不能推断必然走了空返回。失败取证已修正None序列化，避免再次丢失快照；进一步只读快照记录有锁保护的诊断计数、领取排除状态及目标是否被排除，不更改原1.5秒业务窗口、3秒屏障、调度或断言。17项冻结采用前一快照版本，后补计数版仅语法解析通过，未把未执行代码算测试通过。不无修改继续重复此批次。


## G05当前链启动与历史证据影响审查

历史return-admission返工报告9个checks成立，但报告自身标注非完整G05/G06。与当前installed产品直接逐字节对比7个文件不同，覆盖预算流、原生入口、控制准入、上下文和完成结算；不是只改路由之外的无关文件，不能继承真实链成功。差异列表`/tmp/sdk-sampling-cause-G05-rework-impact-20261106.json`。独立审查认可实际返工/逻辑reviewer消费事实及必须重验当前链；其另建议新增独立计划产物，但原G05未要求自主规划或计划产物，不增加该门槛，按真实模型编排角色、调用链和绑定核对。

当前安装包同脚本已启动，原请求预算600秒、8agent_calls/96model_turns，输出`/tmp/sdk-sampling-cause-G05-rework-20261106`，原进程句柄81150，log为同目录名加.log。预计8–11分钟核对一次；不因观察超时重启，不与旧G06小时级图混淆，不自动标G05通过。G06并发、组及多轮隔离仍需独立证据。未触发CI或修改ModPort。


## 验证入口报告状态合同修正

G04图成功但重复事件未执行时，入口原先写partial，违反Goal第6节仅允许passed/failed/blocked/not_run/not_applicable的报告合同。现写not_run，事实中另保留graph_scenario_status=passed与duplicate_dependency_event_redelivery=not_run；仍退出1，不把子场景升级成完整通过。历史G04 partial原报告不改写，组合G04独立审查结论不变。当前安装包解释器以-I运行仓库验证器配套测试，5项通过、0failure/error/skip，原进程退出0，日志`/tmp/sdk-verifier-status-contract-20261106.log`。产品未改，未调用模型或CI，当前G05进程不变。


## 当前wheel完全隔离Python3.12环境证据

新环境`/tmp/sdk-sampling-cause-isolated-py312-20261106`，pyvenv.cfg明确include-system-site-packages=false；离线no-deps安装同一sampling-cause wheel。安装可选依赖前，-I确认yaml不存在，公共Python ApplicationSpec构造成功，from_yaml明确报缺少可选依赖；证据`/tmp/sdk-sampling-cause-isolated-core-20261106.json`。PyYAML6.0.3从官方PyPI下载wheel后离线安装，日志`/tmp/sdk-sampling-cause-yaml-download-20261106.log`及`/tmp/sdk-sampling-cause-isolated-yaml-install-20261106.log`。未运行用户禁止的hash检查。

同环境-I从/tmp执行冻结的配置/默认值/校验三模块18项，全部通过、无跳过、退出0；`/tmp/sdk-sampling-cause-isolated-g01-20261106/result.json`及output.log保留SDK/YAML准确环境路径、sys.path、prefix/base_prefix，并拒绝系统site-packages混入。此前真实模型证据仍来自继承系统包的环境，不能把这18项升级为完全隔离的真实OpenCode验收；G18完整平台矩阵/回归仍缺。没有新增模型调用，不影响G05当前执行。


## 当前wheel配置层Python3.10–3.13隔离矩阵

`/tmp/sdk-sampling-cause-isolated-config-matrix-20261106.json`汇总四个新环境：各自include-system-site-packages=false，同一当前wheel与PyYAML6.0.3离线安装；四个真实CPython解释器均在/tmp下-I导入准确安装模块，每版本同一冻结配置/默认值/校验18项通过，0failure/error/skip，原进程均退出0。每行有精确Python版本、Linux/x86_64、SDK/YAML路径与原result.json；310/311/313证据目录为`/tmp/sdk-sampling-cause-isolated-g01-py<minor>-20261106`，312沿前段目录。此为4×18执行，不能说72个不同测试；不覆盖旧API全量、Windows/ARM或真实模型版本矩阵，不关闭G18。未改变当前G05进程、产品或任何原预算。


## 当前G05最低合同验收通过

约定检查窗口19:48核对原句柄81150已退出0；report.json的9项checks均true，host_close_completed=true，return_failure_files为空。实际6次原生Agent入口、32次已结算model_turns，均无reserved/unknown；原600秒、8Agent/96轮预算未改变。两个初稿DRAFT_A/DRAFT_B被reviewer读取，准确B成员绑定原反馈FIX_B返工为FIXED_B，下一reviewer调用绑定原logical_reviewer_id、原反馈版本与新产物版本，实际发布ACCEPTED/REVIEW_REPLAY_OK，root发布ROUTE_OK。三次相同route请求跨组关闭保持同一返工实例及组回执；准确SDK lease/attempt/fence与native清理匹配，宿主关闭完成。

独立只读审查及主审确认满足原G05最低合同。root为实际调用工具的模型编排角色；合同未要求新增自主规划产物，审查者已撤回该额外门槛。原脚本“no full G05/G06”保守scope不改写，独立补充G05-minimum-acceptance.json明确为何仅最低G05通过：不包含G06并发/多轮隔离、G14崩溃恢复、独立OS进程树清理或无系统依赖的真实原生环境。当前完整Goal仍未完成。


## 当前隔离安装包文档执行与G07启动

`/tmp/sdk-sampling-cause-docs-20261106.log`：当前完全隔离Python3.12安装包解释器以-I执行check_docs，581条本地链接有效，4个双语README示例通过、0跳过，原进程退出0；逐例原始证据保存在`/tmp/sdk-sampling-cause-docs-20261106`。不是CI，未调用模型；不替代Agent原生场景或完整G18。

G07经独立只读预检无具体阻塞后，于北京时间19:50:40启动，同一完全隔离py312当前wheel，原360秒请求预算，句柄58807；输出`/tmp/sdk-sampling-cause-G07-native-20261106`及同名.log，预计3–7分钟检查。实际call/send/拒绝和等待环结果尚待报告，不提前标通过。

G08预检发现验证器ObservedAdapter未转发真实adapter配置校验和host_tools_revision，现已修正；新增正向goal两次native调用的准确清理检查，语法解析通过，独立复核中，尚未真实执行。产品未修改，不能把此准备工作算G08通过。


## 当前G07验收通过及G08最终预检

原句柄58807退出0，acceptance.json G07 passed；开始19:50:39、结束19:54:25。独立复核确认准确root调用者、相同请求ID返回相同call子实例、真实send/wait子实例、原agent_permission_denied/agent_wait_cycle错误、两子产物和组合输出，controller真实lease验证、准确父预算和提交准入effect，Run succeeded。3 Agent/18轮模型，reserved与unknown均0；完全隔离Python3.12当前wheel，未继承系统site-packages。等待环负例为自等待，不代表所有动态图排列；没有独立OS清理声明。G07最低合同通过。

G08验证器的host_tools_revision/配置校验转发及正向两operation准确identity/receipt核对已按独立复核修正，新增distinct operation IDs和完整effect请求/lease核对，最终预检无具体阻塞。-I --list入口检查退出0（sdk-sampling-cause-verifier-list-20261106.log）；这是预检，不是G08验收。


G08当前完全隔离安装包场景已于19:59:25启动，句柄42171，输出`/tmp/sdk-sampling-cause-G08-native-20261106`及同名.log。三个独立请求各沿原240秒预算；正向两轮native续接加两个负例，预计4–8分钟，约20:07:25检查。不是每轮增加请求预算，不因等待观察超时重启。当前G08仍未通过，结果及正向准确清理新增检查待实际核对。


## 当前包六个公共类型消费文件通过

冻结当前tests/typing六文件于`/tmp/sdk-sampling-cause-typing-20261106`；从/tmp执行工作区mypy，--python-executable准确指向当前完全隔离py312安装环境，类型目标3.10，清除MYPYPATH/PYTHONPATH并使用独立缓存。output.log为Success: no issues found in 6 source files，原进程退出0，manifest.json保留范围/工具/来源。不是原生Python3.10运行，不替代旧API全量或G17完成。没有模型调用。


## 当前双语Wiki本地导出预览

`/tmp/sdk-sampling-cause-wiki-preview-20261106`包含25页本地导出与PREVIEW-MANIFEST.json；导出器验证原本地文件目标存在，原进程退出0，日志同目录名加.log。仓库链接ref为本地release/0.8.0，未发布且未声称公共URL可访问；仅本地预览，没有push/Wiki发布。G01既有代码默认值与双语Wiki对照证据不变；G18整体仍未完成。


## NOTICE遗漏的本地打包输入修正

当前临时source快照遗漏根NOTICE，导致原sampling-cause wheel仅包含LICENSE；仓库pyproject已正确声明LICENSE/NOTICE，产品代码不是缺陷。独立复制相同冻结source并补原NOTICE于`/tmp/sdk-sampling-cause-distributions-20261106`，本地build_wheel/build_sdist均成功；后续临时候选构建helper也补复制NOTICE，未改变原候选或当前G08进程。parity.json确认新wheel/sdist和旧wheel的151个产品文件逐字节一致、产品路径集合一致、Name/Version/Requires-Python/Requires-Dist/Provides-Extra相同，新两分发均有准确NOTICE；不运行hash检查。

由新sdist使用既有宿主build tools离线构建wheel（sdist-build.log），再离线安装到include-system-site-packages=false的新`/tmp/sdk-sampling-cause-dist-check-20261106`。installed-parity.json确认151个产品文件与两wheel一致；冻结配置三模块18项通过，无跳过；六个公共类型消费者对该环境检查通过。此非隔离构建后端依赖解析证明，新分发没有另跑真实模型。当前运行证据的旧wheel来源不改写，打包修正的影响复用由独立审查核对，不自动宣布G18完成。原构建失败边界及缺NOTICE旧wheel保留。


NOTICE修正分发的独立审查完成：直接比较wheel条目，仅新增dist-info/NOTICE、METADATA的License-File及RECORD内容变化，其他全部条目含入口点均相同。新sdist构建wheel与新直接wheel全部条目路径/内容一致；新安装除pip会更新的RECORD之外全部分发条目（含NOTICE/metadata）一致，installed-parity.json已补记。不是校验RECORD哈希。独立复核认可新环境18测试及六类型消费者、实际sdist→wheel→安装链的有限等价性；宿主构建工具未隔离，不能声称干净构建依赖解析。原生执行仍确切来自旧wheel，新分发适用性是上述明确等价审查，不伪称已重新原生执行。未切换当前G08环境或覆盖旧制品。


## 当前G08原生最低合同通过

约定20:07核对原句柄42171退出0；实际19:59:24开始、20:01:06结束。acceptance.json G08 passed，G08.json保留同一调用/执行lease与原deadline、首次创建的真实session和第二轮准确续接、两次验证共享session、draft→fixed产物版本1→2。writer只消耗1Agent、6model_turns；两个负例各1Agent、4model_turns，总3Agent/14轮，各原240秒预算不变。writer两个不同native operation准确清理且共享原effect authority；blocked及validator异常的具体goal_blocked/validator_execution_failed均为调用与Run failed，准确清理/finish/replay核对为true，原错误保留且下游未执行。普通response成功已由同包G07真实证据覆盖。

独立只读终审无G08最低合同阻塞，G08记passed。限当前Linux/x86_64 Python3.12安装包和准确SDK清理回执，不扩张为独立OS进程树或其他平台。验证器修正已被本次实际执行，产品代码未变；完整目标仍未完成。


## G11验证入口预检修正

G11原有native_knowledge已包含活动旧请求暂停后更新prompt/配置、新请求先执行、旧请求继续及知识权限/版本冲突断言。预检发现包装适配器未转发host_tools_revision和validate_configuration，现已修正；另补两请求原始身份/deadline/冻结预算与实际入口lease匹配、准确runtime effect及native清理回执检查，复用既有mailbox只读证据工具。原240秒/32模型轮次预算及原等待上限不变，产品未改。语法解析通过，既有验证器配套5项测试通过；这些不算G11真实验收，尚未执行新模型请求。

G11独立预检未发现具体阻塞后，于北京时间20:14左右启动完全隔离Python3.12当前wheel的两个真实请求，原进程句柄72412，输出`/tmp/sdk-sampling-cause-G11-native-20261106`及同名.log。原240秒/32轮预算不变，预计4–6分钟，20:20核对一次；不提前标通过，不因观察超时重启。

G11原句柄72412在20:20按约核对退出0，acceptance.json报告passed；实际20:14:09至20:16:03，2Agent/14模型轮次，reserved/unknown均0。主审逐项核对旧/新prompt与配置版本、实际knowledge_read v1/v2、knowledge_permission_denied、knowledge_version_conflict、历史INITIAL/UPDATED及当前v2未覆盖；两原240秒预算、准确effect/lease/attempt/fence与native cleaned回执、Run finish均匹配。独立终审中，暂不更新顶部Gate总数。证据`/tmp/sdk-sampling-cause-G11-native-20261106/{acceptance.json,G11.json}`，限Linux x64 Python3.12与SDK准确清理，不声称其他平台/OS树独立证明。

G11独立只读终审确认满足原最低合同，无具体阻塞；顶部当前表与未完成计数已更新。原生报告与源进程退出证据保持不变，未增加任何模型调用。完整Goal仍未完成，剩余G06、G09、G10、G12、G14–G18九项。


## G09全部邮箱策略预检

独立只读审查确认需要mailbox验证器五场景：fifo覆盖两并发调用者/两会话/同键续接/FIFO/满队列，reject，replace_pending，以及cancel_and_replace的prelaunch和unknown。发现initial预算快照在放行后取值的取证缺口，现改提交后立即保存，queued/replacement在放行前保存，不改产品、原300秒/16模型轮次请求预算及330秒场景等待。语法解析通过；最终预检和真实结果另报，不标G09通过。预计合并10–20分钟，原等待总上限约28分钟，不高频刷新或重启。

unknown分支另补最终owner/replacement对提交时initial预算/deadline的比较，语法解析通过。G09五场景于北京时间20:24启动，完全隔离Python3.12当前wheel，原进程句柄70757；输出`/tmp/sdk-sampling-cause-G09-mailbox-20261106/report.json`及同名.log。预计20:44核对一次；原上限约20:52，不因观察超时重启。尚无最终验收结论。


## G10入口独立预检（未执行）

等待G09期间，独立只读审查native_foreground未发现G10最低合同具体阻塞：独立CLI宿主、短命客户端退出后继续、跨底层Run独立预算及同一服务/session、真实宿主重启、准确已提交effect且消息仍排队的进程故障窗口、原身份/队列/预算恢复、跨Run取消和停止后准确SDK回读。原600秒/8Agent/12模型轮次请求预算、3600秒外层截止保留。补失败exception_locations，只保留类型/源码位置，不记录异常正文或密钥；语法解析通过。尚未启动G10模型调用，不与G09并发增加宿主负载；不声称其他崩溃窗口或独立OS树清理验收。


## G09真实结果及错误断言补充评估

20:44按约核对原句柄70757已退出1，report.json四场景fifo/reject/replace/prelaunch为passed；unknown只有original_identity_unchanged断言为false。逐字段差异仅原账户model_turns.spent从1增至2、available从15减至14，原allowance16/deadline/身份/lease/attempt/fence/effect均未变化，agent_calls仍1，reserved/unknown均0；实际替代请求始终零调用、未调度、quarantined，准确indeterminate effect清理以及3秒观察均通过。预算库只读unknown-budget-readback.json保留相同原invocation/fence的两次settled计量；不证明额外计量的具体时点原因或两次上游发送。

独立审查确认冻结已用量不是G09原预算不变的正确要求；修正验证器为原计量身份/allowance/deadline不变、已用量单调且不超原上限、无reserved/unknown且available一致，agent_calls仍不得增加。原失败report及进程退出1不改写。`G09-minimum-supplement.json`明确按保留原生事实补充重评、非新模型运行；重新核对身份、清理、其余原checks和四个通过场景，并验证8种预算重置/扩展/超额/未结算变体均被拒绝。补充评估通过，独立终审中；当前产品未改，不重复模型。

G09补充评估经独立只读终审认可原五场景最低合同，无具体阻塞；顶部表及未完成计数已更新。实际9Agent/29模型轮次（含unknown原账户2轮计量，不等于上游请求数），替代/被替换的未执行请求零消耗。原失败未覆盖，准确计量原因仍未知但不影响本Gate所要求的原预算与隔离证明。剩余G06、G10、G12、G14–G18八项未完整验收。

G10通过既有独立预检后，于北京时间20:48启动完全隔离Python3.12当前wheel真实场景，原进程句柄90385，输出`/tmp/sdk-sampling-cause-G10-native-20261106`及同名.log。预计8–15分钟，21:03检查一次；保留原600秒/8Agent/12模型轮次请求预算与3600秒外层截止，不因观察超时重启，不提前标通过。


## G12当前原生证据合并最低合同通过

G12-combined-minimum.json逐项映射技术重试与耗尽、reviewer业务反馈FIX_B/显式返工、原reviewer消费、unknown保持indeterminate/recovery_required且继任者隔离；原技术/G05/G09报告不改写。新增只读G05全Run agent_requests+agent_nodes取证G12-readonly-admission-origins.json：完整六实例与六实际入口一一相等，作者仅两个原成员加准确显式route成员，每个子入口原检查均验证匹配committed父准入effect。独立审查撤回要求任意额外等待区间的建议，认可该真实观察序列没有自动多启动作者；FIX_B是应用业务反馈，不虚构SDK verdict枚举，不宣称单次观察证明所有流程。主审组合脚本7项核对均通过，未调用模型或改SDK数据库；G12最低合同通过，原回归/历史晚abort与G09原退出1均保留。剩余G06、G10、G14–G18七项未完整验收；G10原句柄90385仍待21:03按约核对，不据启动记录判当前活跃。

G10按21:03约定核对原句柄90385已退出0；实际20:48:03至20:50:02，约1分59秒。G10.json全部22checks为true、missing_checks为空。主审独立重核八个请求回读，其中七个真实原生成功、一个排队取消零调用；七个exact native cleanup与committed effect、原600秒预算和绝对deadline均匹配。实际7Agent/14模型轮次。独立终审中；故障宿主exit27保留descendant_cleanup=unknown，其他宿主正常退出，不声称故障宿主独立OS进程树清理或所有G14窗口。没有新增模型或重启。该实际耗时表明同规模后续验证应据此缩短首次检查估计，不能把15分钟当固定等待周期。

G10独立只读终审确认无最低合同具体阻塞，当前G10通过，顶部表与计数更新。完整目标剩余G06、G14、G15、G16、G17、G18六项未完整验收；没有本轮仍运行的原生验证进程。


## G14四故障窗口预检与分段执行

独立审查映射B=意图已持久化/SDK未提交、D=依赖消费与后继意图已提交/ACK未确认、C=实际本地上游HTTP写入返回后故障。原A在mark_submitted（SDK已返回）处退出，不充分覆盖SDK提交已接受/调用方未获返回。现将A拦截点移至公开orchestrator.apply_operations包装：先真实原调用持久接受，再在返回给AgentApp前核对原admit command_id、持久SDK回执、queued Kernel与无业务effect/native operation，记录sdk_return_delivered=false后退出31。SDK持久回执已存在与调用方未收到返回分别记录，不伪造SDK内不存在回执；无直接库写入、无产品变更，语法解析通过，最终独立预检中。G10故障不替代这些四窗口。

B/D已通过预检，于北京时间21:08启动，完全隔离Python3.12当前wheel，原300秒/32模型轮次请求预算、每场景600秒观察上限；句柄12577，输出`/tmp/sdk-sampling-cause-G14-commit-20261106/report.json`及同名.log。预计3–5分钟，21:11首次检查，不因观察超时重启；尚无真实验收结论。

G14 B/D原句柄12577按21:11核对已退出0，两场景全部9/13项checks通过，实际原Run/调用/截止一致，D消费记录重投ACK且产物绑定与后继身份不变，生产者无重跑。A修订经独立预检无具体阻塞。A/C于21:11启动原生故障验证，输出`/tmp/sdk-sampling-cause-G14-native-20261106/report.json`及同名.log；预计6–8分钟，21:18核对，C须真实观察原300秒预算到期，不能提前缩短或延长；原每场景600秒观察上限保留。G14整体仍待A/C实际结果与终审。

A/C原进程句柄为19827；已修订A只验证接受后返回丢失，不声称所有提交微观时序均已覆盖。等待期间仅做G16停止/竞争/撤权入口只读预检，不并发新增模型负载。

G16下一步入口只读预检：独立审查确认最小新增组合为host_competition、permissions、cleanup_unknown。前两者分别覆盖同状态目录多宿主排他/停止持久性与实际发送后的撤权/准确取消/无关角色继续；第三者通过真实守卫清理后扣留回执，使SDK清理权限保持未知，跨两次宿主重启核对原operation/effect/lease和同会话继任者不启动。是缺清理证据的保守行为，不冒称物理清理失败；宿主竞争验证实际OS宿主锁排他并保持原执行lease，不冒称直接Kernel租约行竞争。没有直接SDK表写或hash检查，尚未执行新增G16模型调用。


## G14四个真实故障窗口最低合同通过

A/C原句柄19827按21:18核对已退出0，A全部9checks、C全部16checks为true。A在真实SDK接受持久admit回执后、返回AgentApp前退出，原queued execution/无effect/native操作事实与同身份恢复单一原生操作一致。C有准确发送/effect/lease观察，早期原身份重放不再发送，原300秒期限后仍保持recovery_required/indeterminate和会话quarantine，排队请求未执行并可到期，独立会话成功。主审另逐字段检查A/C原始native receipt中operation/invocation/deadline/effect/execution/lease/attempt/fence与准确effect匹配且tree_cleanup=confirmed。

独立终审核对B/D/A/C全部原报告认可最低G14合同。G14-combined-minimum.json保存四窗口映射；实际总6Agent/21轮计量，不等于上游请求数。所有故障原进程及恢复宿主退出事实保留；故障宿主独立OS树清理unknown、本地HTTP发送不证明远端完成/远端exactly-once等限制不改。当前G14通过，G06、G15、G16、G17、G18五项仍未完整验收。G16三个必要入口已预检，未新增执行；没有本轮仍运行的原生验证进程。


## 额度审计后的无模型回归取证

上一轮为状态核对，未改变验收状态。本轮不启动真实模型、子代理或CI。使用当前sampling-cause安装包、原12模块/76测试范围，仅替换已补充失败取证的arbitration测试文件；原业务/屏障/释放/等待期限不变。原始失败及历史日志均保留。

`/tmp/sdk-arbitration-full-diagnostic-20261106/result.json`：76项、74通过、2错误、0跳过，124.747秒，原会话77108退出1。原arbitration失败项本次四组合通过，未触发新的boundary-failure现场；这只说明未复现，不能证明根因或修复。两错误为本次执行者误加`-I`，阻止两个明确依赖sitecustomize子进程取证的测试启动，非产品失败。纠正启动参数后只补跑这两项，`instrumentation-correction-result.json`为2项通过、0跳过、5.256秒，原会话84767退出0。两批合计覆盖原76项，但不声称单批76全绿，不覆盖旧API全量或其他平台。

本轮没有产品修复，因此原线程暂停点未到达/关闭诊断错误仍开放，不能以本次通过关闭。避免无变化连续重跑；后续需要从准确失败取证推进，而不是猜测run_once返回空值就是历史根因。启动隔离参数错误由本次执行者引入，已明确记录并纠正。G06、G15、G16、G17、G18仍未完整验收。


## G16 当前安装包分段验证启动

2026-11-06T13:29:20.172394+00:00：host_competition已启动，原会话86622，输出`/tmp/sdk-sampling-cause-G16-competition-20261106/report.json`及同名.log；完全隔离py312现有wheel，原120秒请求预算/420秒观察上限，首次预计2–4分钟核对。此记录不证明通过，不重启原句柄；本轮不跑CI。权限撤销与缺清理回执仍待本段结果后顺序执行。


## G16 两段通过、缺清理回执段失败：不可整项验收

`/tmp/sdk-sampling-cause-G16-competition-20261106/report.json`原句柄86622退出0，5项checks全true；独立复核确认原120秒预算下第二OS宿主被拒，准确lease/effect不变，原请求完成及准确native清理，停止服务后重启拒绝新请求且重放无新增入口/发送。仅OS宿主锁竞争，不冒称直接Kernel租约行竞态。实际1Agent/2计量轮。

`/tmp/sdk-sampling-cause-G16-permissions-20261106/report.json`原句柄65915退出0，14项checks全true；独立复核确认发送后撤销权限，原180秒请求准确取消并保留indeterminate及native清理回执，排队请求零调用，无关角色成功；撤权跨重启保持，恢复权限仅影响未来请求。实际3Agent/9计量轮。

`/tmp/sdk-sampling-cause-G16-cleanup-unknown-20261106/report.json`原句柄73168退出1/TimeoutError；只有fault_and_real_guard_exit检查已完成。真实guard已清理后扣留回执，原请求最终recovery_required/indeterminate，原operation仍authorized且无receipt，同会话继任者零调用并因原期限到期取消/保持隔离。无关会话真实执行后也recovery_required，准确native清理回执已确认，但代理清理拒绝：只读agent_diagnostics给出ProxyCleanupUnknownError，cleanup_error位置proxy.py:592，经opencode.py:777/789传播，无已记录body error。`failure-diagnosis.json`保留有界原始事实摘要。不能从该行判断具体哪个线程/资源未退出，也不能将原先submitted的中间快照当最终状态。未到达第二次恢复，G16仍未通过，不重跑或延长原120秒预算。此段2Agent/4计量轮；本轮三段合计6Agent/15计量轮，不等于上游请求数。

后续取证仅改验证器：close失败后非阻塞获取资源计数/标志/错误类型及至多32个所属线程的8帧basename+行号；不记录消息、内容、局部变量或凭据，不改变两秒产品清理窗口，异常原样传播，每invocation仅记录首次失败。新增4个无模型单测通过（0.017秒），覆盖保留未知资源、锁竞争不等待、准确异常/只记一次、取证自身失败仍保留原BaseException。此修改不能补回本次缺失的线程快照，不是产品修复或G16通过。

独立只读复核未发现上述验证器取证具体阻塞；限制为快照发生在拒绝后，不是拒绝瞬间原子快照，且证据append/fsync为同步存储写入，存储停滞可延迟异常传播。非阻塞仅指资源锁，不声明整个取证路径有硬时限。没有新增产品候选或额外真实模型重跑。


## G16 最小带取证重验启动

2026-11-06T13:44:36.046750+00:00：仅cleanup_unknown重验，原会话52122，输出`/tmp/sdk-sampling-cause-G16-cleanup-observed-20261106/report.json`及同名.log；现有完全隔离py312安装包、原120秒请求预算/600秒场景上限不变，首次预计3–5分钟检查。唯一变化是上轮已审查的失败后资源取证，不重跑competition/permissions，不提前宣布通过。


## G16 带取证场景通过最低合同；先前失败保留

原会话52122退出0；`/tmp/sdk-sampling-cause-G16-cleanup-observed-20261106/report.json`全部10项检查通过。真实guard清理返回true后回执被扣留，原准确operation始终authorized/receipt=null，原effect为indeterminate，原资源预留和会话owner保持；两次重启原invocation/Run/lease/attempt/fence/deadline/冻结预算及已用量不变，原入口/本地发送均一次。同会话后继没有command/effect/native/调用消耗，到期取消而隔离仍保持；独立session实际成功并准确清理，原预算可信。原故障宿主exit32，两次恢复宿主均exit1，worker-exit记录HostError host.py:503（未解决所有权/隔离导致drain拒绝），三个监督器均cleanup_confirmed，不能说所有宿主正常exit0。

主审按原始身份、预算、回执及两次恢复逐字段复核；独立审查认可与前两段合并满足限定G16最低合同。可复现合并检查`/tmp/sdk-g16-combine-20261106.py`，结果`G16-combined-minimum.json`；没有改写先前失败报告。此次2Agent/5计量轮；通过组合6Agent/16轮，连同失败尝试总8Agent/20轮。本次无proxy-cleanup-failures文件，表示未触发失败取证，不解释或修复先前ProxyCleanupUnknownError，后者仍是完整回归开放项。当前整项目标剩余G06、G15、G17、G18。

## G15 原合同边界复核

主审与独立只读复核确认：Goal第3.2节默认tokens=null，G15明文最低证据为实际原预算前后、到期拒绝、父子取消/无关会话及重启连续性，并没有无条件要求真实非空token正例。此前将缺可信模型目录视为G15默认路径必需外部前置是额外解释，现纠正；不改Goal、不把未验证能力算通过。仍须准确核对请求/子调用/goal/排队/重试的秒数、Agent调用与模型轮次账户，不能仅拼接绿色计数；父子取消与排队到期的当前安装包完整证据尚未齐。非空token为已公开实验能力，其真实限额尚未验收、可信上界缺失时失败关闭等限制继续显式保留，不能宣称正向计量已验证。


## G15 父子取消与队列到期顺序验收

独立只读预检未发现两个验证器具体接口/归属阻塞。2026-11-06T13:51:28.166194+00:00：父子取消原会话99666已启动，输出`/tmp/sdk-sampling-cause-G15-parent-cancel-20261106/report.json`及同名.log；当前完全隔离py312安装包，原180秒/4Agent/16模型轮次预算不变，预计2–4分钟首次核对。排队到期后续顺序运行，不并发新增原生负载；未提前标通过。


G15父子取消原会话99666退出1，host_close_completed=true；报告保留failed，checks尚空，未到公开parent.cancel。准确失败在读取parent get_execution_limits时，verifier.py:238/193→supervision.py:673→_sqlite_base.py:413，当前SDK抛_ControlAdmissionTimeout（TimeoutError子类），验证器旧type(exc) is TimeoutError拒绝原本可在原期限内重试的锁准入负例。controller预算证据已trusted；不能因此宣称取消传播有问题或通过。

仅修正验证器已知锁准入识别：精确base TimeoutError或当前_ControlAdmissionTimeout类且精确锁准入消息；交易body/原预算期限耗尽/其他子类/身份错误均不重试。原cutoff、0.1秒片和有限等待循环不变，不重放业务/效果。两项安装包配套测试通过，日志`/tmp/sdk-g15-parent-admission-fix-20261106.log`；独立复核待结论，不提前重跑。

排队到期独立场景于上述失败后顺序启动，原会话63428，输出`/tmp/sdk-sampling-cause-G15-queue-expiry-20261106/report.json`及同名.log。原120秒请求预算/300秒观察上限不变，预计约3分钟核对；没有并发启动父子重验或扩大预算。

## G15 无模型入口分段诊断（2026-11-06）

父子取消修正验证器后原会话76225仍退出1：`/tmp/sdk-sampling-cause-G15-parent-cancel-fixed-20261106/report.json`在independent_service等待原期限内发送失败，尚未调用parent.cancel。独立只读复核确认：parent/worker的child_wait锁超时发生在parent原deadline之后；service的controller authority ended及子取消发生在验证器收尾附近，不能将这些后发生错误当作此前入口停顿根因。服务Kernel执行已在parent截止约102秒前started，adapter无入口。

不调用模型的安装包探针`/tmp/sdk-g15-local-entry-probe.py`，证据`/tmp/sdk-g15-local-entry-probe-20261106/observation.json`及同前缀.log：真实SDK父/子/独立service，application=3、原30秒预算，合成适配器。首发仅因合成适配器未声明resume被配置层拒绝；补齐能力后运行exit0。worker进入后5秒观察点service尚无handler/adapter入口；其sdk-child_2线程位于_prepare_handler_admission→_prepare_handler_entry→_prepare_execution_budget事务退出/控制锁release附近，随后收尾时记录到service handler入口，未记录adapter入口。此单快照不证明连续卡在该行、锁持有者或原生失败同因；探针主动释放门并close，不是G15取消验收。没有产品修复或新模型调用。

下一定位应在原期限内多阶段记录入口准备耗时与控制锁实际等待/持有区间，区分预算准备延迟和进入Agent后的延迟；不能直接按controller后续失权修改取消规则。

## G15 本地入口计时结果（2026-11-06）

`/tmp/sdk-g15-local-timing-probe.py`对同一当前安装包增加仅观察的_control_lock上下文包装与_prepare_handler_admission计时，原30秒合成场景不变。原会话11305退出0，原始`/tmp/sdk-g15-local-timing-probe-20261106/{observation.json,final-events.json}`及同前缀.log。service实际adapter进入1753503.627；worker adapter进入1753495.699，相差7.928秒；service handler进入1753502.360。service预算准备1753501.709–1753501.800，约0.091秒。此次三Agent均进入，没有重现原生场景持续至截止未进入的问题；不能称为修复或G15通过。

最长观察控制区间为agent-wait父线程的_sample_budget约0.967秒，其中已yield后的_begin_budget_sample/事务约0.935秒；同期get控制锁等待约0.951秒。区间嵌套，不能相加，不等于SQL/磁盘独占耗时。包装记录仅保存超过20毫秒或抛异常的上下文，2297条，未记录凭据/模型正文；观察开销和调度会影响时序。当前证据否定“服务预算准备在此轮持续卡住”的推断；尚无法区分原生失败中启动准备、资源准入及适配器前工具设置的具体阶段。没有产品修改、模型调用或CI。

## G15 原生入口失败准确栈与定向修复（2026-11-06）

进一步只读查询同一失败现场的obs_events，service在1793973611.464已产生handler_outcome，而非一直没有执行结果。其handler_entry准确异常栈为context._capture_entry_budget→budget_capture._run→supervision._sample_budget→_control_lock，BudgetClockUnknownError('budget_clock_sample_unresolved:sampling')的直接cause为_ControlAdmissionTimeout（未yield锁准入失败）。资源owner/effect/nativeowner均0，entry_state=pending、无自身execution cutoff，仅一条准备采样回执。准确有界读回`service-pre-entry-readback.json`。此前仅从最终cancelled和无adapter入口推断“持续停顿”的描述不充分：至少已证实入口错误早于deadline，后续未交付/取消另需核对。

新增test_entry_sampling_contention.test_entry_retries_sampling_refusal_wrapped_by_pre_yield_admission，修复前失败，`/tmp/sdk-entry-wrapped-admission-baseline-20261106.log`。context入口重试现在接受此精确marker cause、无cause链及无采样token的包装拒绝；保留原owner pending/retained/publication检查、原startup/work截止及权限检查，不重放已持有采样。独立只读审查未发现该限定分支权限/清理阻塞，建议额外补nested-cause/token负例。

模块运行`/tmp/sdk-entry-wrapped-admission-fixed-20261106.log`，7项中6通过1失败，5.390秒。新增用例及锁退出清理失败负例通过；原startup截止场景暴露另一入口提前退出：同名采样拒绝cause为普通TimeoutError，来自_sample_budget在_drain_budget_samples之后、当前样本注册前的短窗口耗尽（supervision.py:461），失败在原startup截止前约29秒。此普通cause尚未放宽为可重试；不能混同未知清理失败或按字符串直接重试。原证据`/tmp/sdk-runtime-entry-sampler-qen0ggu6/sampling-evidence.json`保留。当前源码存在一个限定修复、尚未新打包或真实重验；既有安装包证据不自动转为新源码通过，G15仍开放，不运行CI。

## 入口采样窗口耗尽明确标记及安装包验证

新增内部_BudgetSamplingAdmissionTimeout，仅在_sample_budget的drain正常返回后、当前观察注册token前短窗口耗尽处抛出。入口仅接受精确marker类型、无嵌套cause、无采样token的包装拒绝；持有pending/retained或publication改变仍拒绝，普通TimeoutError清理失败不重试，原期限与权限检查不变。新增两类marker正例及嵌套清理/token/普通超时三个负例；独立只读审查未发现该范围具体阻塞。源码8项35.022秒全部通过；独立venv安装包8项35.942秒全部通过、0skip，`/tmp/sdk-entry-wrapped-admission-v2-20261106`保存wheel、product-delta、parity、entry-sampling-v2-result.json及日志。151产品文件直接字节比较一致；相对sampling-cause仅context.py/errors.py/supervision.py变化。不自动继承原生Gate通过，未调用模型、未运行CI。

执行失误保留：构建第一次因pip缓存只读而未完成成功状态，改用no-cache-dir构建成功。操作误复用历史`/tmp/sdk-entry-retry-candidate-20261106`路径，wheel/env及result.json/output.log已被本轮更新，不能再用该路径当前内容作为历史制品/历史运行证明；本轮最终候选复制到上述唯一v2路径。误启动目录内既有11模块脚本，67项111.802秒，65通过2error；两error均隔离解释器-I阻止原测试sitecustomize进程探针，不能作为产品失败或全量通过。未重跑该批；正确入口8项使用独立冻结测试目录及不同结果文件，不与67项混算。此失误没有额外模型调用，但消耗本地运行时间。

## 入口修复候选相邻安装包回归与G15真实重验

同一入口修复wheel，冻结入口准备时间戳及采样回执两个模块。原相邻脚本遗漏__main__保护，使spawn子进程重入测试；首次22项6failure/1error、75.102秒结果原样保留adjacent-result.json/log。修正脚本入口保护后，adjacent-corrected-result.json：22项全部通过、0跳过、17.051秒。不将启动脚本缺陷算作产品修复。

时间戳末项旧预期在lease已因真实后续时钟跳变过期时仍先完成_enter_handler，然后confirm才拒绝；当前guarded_entry会先拒绝陈旧租约。夹具保持原跳变及首个事务单次采样断言，明确断言_enter_handler抛StaleFenceError、_entered=false、持久entry pending及sampler pending、关闭拒绝budget_clock_cleanup_pending。独立审查指出原TemporaryDirectory会在关闭拒绝后删除未确认资源，已改为retained_directory并保留准确kernel/context/owner；最终冻结fixture-final，单项0.447秒通过。相邻22项冻结在此保留目录修正前，最终单项另列，不混称同一批次。

真实G15父子取消仅一次，原会话18024，输出`/tmp/sdk-entry-wrapped-admission-v2-G15-parent-cancel-20261106/report.json`及同前缀.log；当前安装包，原180秒/4Agent/16模型轮次不变，预计2–4分钟首查。其余原生场景未启动，未提前判通过。

## G15 入口修复包真实父子取消通过

原会话18024退出0，`/tmp/sdk-entry-wrapped-admission-v2-G15-parent-cancel-20261106/report.json`全部12检查及host_close_completed为true。父9d7db3060d50453d821d9650fe099d4a、子806f3f46269e4f6aa3727b378190fd67实际进入OpenCode并发送，公开parent.cancel传播后同为recovery_required/runtime effect indeterminate，原生operation均cleaned且准确回执tree_cleanup=confirmed。此结果诚实保留已发送业务效果未知，不冒充业务回滚或结果cancelled。独立service aa6c9156d26042f092a81aa0c32cf6c5为succeeded，准确native清理确认；无子孙重新启动及晚原生入口。五项controller/parent/child/service_controller/service deadline读回均true，原180秒/4calls/16turn预算及lease/attempt/fence绑定匹配。父子共享Run花费2Agent/4轮（不得重复累计两行），独立Run1Agent/2轮，总3Agent/6轮。

这是当前入口修复包的实际原生取消证据，独立原始报告复核待结论。G15的其余预算/排队到期/重启最低合同仍须按当前三产品文件变化核对证据适用性；不凭本场景宣布整项或G06/G17/G18完成。旧原生失败仍保留，不能据一次通过解释全部历史结算缺陷。

独立只读复核已认可上述父子取消限定场景，无具体阻塞；原始共享用量前后2/4 calls、4/16 turns，服务1/4 calls、2/16 turns。测试门仅放置顺序，本地发送不证明提供方执行/取消；整项G15仍待组合合同核对。

## G15 新候选证据适用性与G06原始事件核对

独立只读审查确认：sampling-cause的G07/G08/G10/G12/queue报告保留有效历史事实，但三产品文件修复涉及这些场景共用的入口采样路径，原报告没有记录是否经过新增异常分支，不能只凭其余148文件不变就宣称新安装包全部通过。当前v2已有原生父子取消；仍须新包goal同会话轮次、技术重试、排队到期及重启预算连续性。未新增nonnull token门槛。当前队列到期会话78413，输出`/tmp/sdk-entry-wrapped-admission-v2-G15-queue-expiry-20261106/report.json`，原120秒/300秒观察上限不变，预计约3分钟首查。

G06旧现场只读obs_events摘要`/tmp/sdk-g06-observation-phase-readback-20261106.json`：291626在1793939494.290记录handler_entered，1793939566.803记录kind=ok handler_outcome；074a511仅worker_dispatch后handler_error，details只含exception_type、无entry_failure栈。这不能与G15已确认入口锁准入包装缺陷合并为同根因，也不能恢复缺失完成时间。未重跑G06模型图、未修改其原冻结输入或状态。

当前v2队列到期原会话78413退出0，report.json六项检查全部true，原宿主及重开宿主均关闭。排队请求在原120秒期限到期取消，native入口/发送均0，重开后相同请求重放仍保留原到期；独立服务实际成功并准确清理，消耗1Agent/3轮，原8calls/16turn/120秒账户未扩展。入口owner为人为门控的排队前置条件，不能称其执行过模型；此次不是跨进程崩溃恢复证明，后者仍需当前包G10。剩余G15新包goal轮次、技术重试及重启连续性未齐。

## 当前入口修复包技术重试与goal续接验收

真实技术重试原会话6118退出0，`/tmp/sdk-entry-wrapped-admission-v2-G12-retry-20261106/report.json`全部12项检查通过、host_close_completed=true，environment指向当前独立venv安装包。首个工作目录准备故障发生在原生获取前，准确not_launched回执、0模型轮；下一次相同调用/请求/lease/attempt/fence/工作区/原deadline成功，工具authority换新，准确native cleanup和SDKfinish回执通过。成功Run消耗1Agent/2轮，原150秒/4calls/8turn不变；另一个原调用耗尽重试预算，失败保留且没有原生模型启动。技术重试不是业务返工或模型请求发送后的重复执行证据。

goal真实场景仅G08，当前会话8956，输出`/tmp/sdk-entry-wrapped-admission-v2-G08-native-20261106/G08.json`及同前缀.log；原240秒预算及其验证器/blocked/异常范围不变，预计2–4分钟首查。未启动G10或G06并发模型图。

G08原会话8956退出0，acceptance.json的G08=passed，当前安装包G08.json保存同一writer调用05a2f3cbc9974ac688dfdb2dbb07e30f、同一session ses_e4eac3e51ffeueHMRIUp86NcpH两次验证DRAFT_NATIVE→GOAL_NATIVE_FIXED，准确两个native operation cleanup通过。原240秒/64calls/32turn账户，writer实际1Agent/6轮；两个负例各1Agent/4轮，总3Agent/14轮。blocked和验证器异常均按对应业务失败、下游未启动，不把Kernel成功运输业务失败结果误判为业务成功。G15同会话goal轮次切片获得当前包实际证据，技术重试及goal原始报告独立复核待结论；跨进程重启预算连续性仍未齐。未运行CI或重跑G06。

独立终审核对G12重试和G08原始报告及断言后，认可限定最低证据，无具体阻塞。重试成功1Agent/2轮、耗尽负例1Agent/0轮，总2Agent/2轮；goal三Run合计3Agent/14轮。G08响应模式可复用同当前包父级/重试普通响应实际成功，G08最低合同成立。G15 goal/重试切片成立，不声明远端exactly-once或nonnull token真实上限。当前G15跨进程重启连续性仍缺新包证据。

## 新包跨进程服务恢复与静态消费验证

G10真实独立CLI/跨Run/故障恢复场景会话36201，输出`/tmp/sdk-entry-wrapped-admission-v2-G10-native-20261106`及同前缀.log；原600秒/8calls/12turn账户及场景期限不变，首次预计4–6分钟检查。当前独立venv离线从原PyYAML6.0.3 wheel安装YAML extra，yaml-install.log保留；未改变SDK产品字节。

利用等待时间冻结当前六个公开类型消费者到`/tmp/sdk-entry-wrapped-admission-v2-typing-20261106`，清除PYTHONPATH/MYPYPATH，从/tmp用mypy2.3.1、准确当前安装包解释器、3.10类型目标和独立缓存检查，原会话46834退出0：Success: no issues found in 6 source files。manifest/output.log保留；此为静态类型证据，不冒充原生3.10运行或完整旧API回归，无模型调用。

## 当前包G10与G15最低合同通过独立终审

G10原会话36201退出0，acceptance.json标passed，G10.json全部22项true、missing_checks=[]；宿主真实exit27后恢复，跨Run独立原600秒/8calls/12turn预算、同原生会话映射及排队身份保持，队列取消无command/effect/native/费用；七个实际执行具准确SDK command/deadline/effect/native cleanup。7Agent/14轮，不把未执行排队项要求为存在SDK执行预算（其sdk_deadline_proven=null，且正确零执行）。故障宿主独立OS后代树清理仍unknown，不能用各native operation回执替代。

主审组合校验`/tmp/sdk-entry-wrapped-admission-v2-20261106/verify-G15-combined.py`，产物G15-combined-minimum.json；直接检查五份报告的安装来源、父子原身份/预算、goal原lease/session、重试同请求、到期零执行与原重开、重启原预算和精确队列取消。第一轮组合断言错误地要求未提交的排队取消项也具有SDK执行期限证明，已按准确零执行分支纠正；未更改业务报告或减少原合同。独立终审逐项认可新包G10与G15最低合同，无具体阻塞；五报告计量总16Agent/39轮（父子3/6、到期1/3、重试2/2、goal3/14、重启7/14），不是HTTP请求数。

G15默认tokens=null最低合同通过；实验nonnull token真实上限仍未验收，不声明外部效果恰好一次/提供方取消成功。完整Goal仍开放：G06、G17、G18，以及其余基线Gate的最新包影响审查和未解释历史回归/代理清理失败；不运行CI、不推送发布。

## 当前包G17 CLI及资源准入

CLI原会话39550退出0，`/tmp/sdk-entry-wrapped-admission-v2-G17-cli-20261106/report.json`status=passed；独立进程validate/config effective/idle serve/client/stop生命周期，无模型调用，准确当前安装来源。六类型消费者见前段已通过，不替代旧API全回归。

资源限制及默认关闭对照原会话74122，输出`/tmp/sdk-entry-wrapped-admission-v2-G17-resources-20261106/report.json`，保留原360秒预算，预计3–5分钟首查。该脚本G17总项及supervision本来标not_run且固定返回1，应分别检查resources_limited/resources_disabled原始场景状态，不能只用退出码判产品失败或全部G17通过。真实监督四场景尚未启动。

## 入口修复 v2：G17 资源与监督结果

当前安装包资源正反例 `/tmp/sdk-entry-wrapped-admission-v2-G17-resources-20261106/report.json` 经独立复核：128 MiB 容量中96 MiB真实父执行占用时，64 MiB同Run子执行保持未启动，准确父预留释放及native清理先于子准入；禁用限制对照父子实际重叠。两例共4次Agent调用/12轮模型，均正常关闭。脚本整项G17为not_run且按设计退出1，不视为完整G17通过。当前CLI报告 `/tmp/sdk-entry-wrapped-admission-v2-G17-cli-20261106/report.json` 的安装来源、validate/effective/status/stop/resume及空闲宿主退出0经独立复核，无模型调用。

监督原句柄19317已退出1，原报告 `/tmp/sdk-entry-wrapped-admission-v2-G17-supervision-20261106/report.json` 保留。stale、disabled、stop三种情形通过；stable诊断子执行已成功、准确重放及单代际唯一子成立，但验证器第211行读取 get_execution_limits 时发生 _ControlAdmissionTimeout，尚未释放父charge gate。finally清理快照中原父operation仍authorized，不能声称清理确认或稳定场景通过。没有重启或增加原360秒预算，先只读诊断及复核验证器观察路径。

当前v2安装环境文档检查已退出0：582个本地链接、4个README示例全部通过，0跳过，日志 `/tmp/sdk-entry-wrapped-admission-v2-20261106/docs-check.log`。从/tmp使用安装环境运行，未使用-I以保留示例进程取证钩子，无真实模型调用；不替代G18完整平台/回归验收。

### G17 stable只读补证与观察器修正

`/tmp/sdk-entry-wrapped-admission-v2-20261106/G17-stable-readback.json` 只读补证确认原父、诊断子native均cleaned，回执身份与原租约/attempt/fence/deadline一致；子预算准确继承原controller。父Kernel仍recovery_required、controller failed，原失败报告不改判。独立复核确认controller错误为controller authority ended、父effect indeterminate，清理不等于成功。

验证器仅对get_execution_limits观察读取的精确_ControlAdmissionTimeout类型在原observation_end内续读；其余异常直接传播，等待后再次检查截止，各次读取保持原默认准入时间。不改产品、业务重试或原360秒预算。无模型检查4项通过，含成功续读、异常传播、过期及截止后不再读取，证据G17-observer-check.json；独立复核指出截止检查及精确异常类型，均已落实。稳定场景尚未重验，不据观察器修正宣布通过。

仅stable修正观察器后的真实重验已启动，句柄63380；输出 `/tmp/sdk-entry-wrapped-admission-v2-G17-stable-observer-fixed-20261106`。原360秒、5Agent/32轮上限不变，预计2–3分钟首次检查，不重跑已通过的stale/disabled/stop。最终精确异常子类传播与截止后不再读取检查通过，G17-observer-check.json保留。

当前v2源码包离线no-deps安装已通过：`/tmp/sdk-entry-wrapped-admission-v2-20261106/sdist-install-result.json`，151产品文件逐字节匹配wheel、安装后METADATA完全相同。首个命令误用下划线文件名而未找到归档，保留sdist-install.log；修正为真实连字符文件名后退出0，sdist-install-corrected.log。不证明联网依赖解析或完整G18。

stable观察器修正后句柄63380在首次预计检查时仍live且无最终report，未重启；下一检查等原360秒收尾，预计再3–4分钟。

### 稳定监督重验：定位到入口发布阶段采样竞争

原句柄63380已退出1，`/tmp/sdk-entry-wrapped-admission-v2-G17-stable-observer-fixed-20261106/report.json` 保留失败。诊断子64d7b6186fb840d3b2555b9397324cbf在handler entry失败，未创建native操作：原始obs_events保留 `guarded_entry -> _finish_budget_sample -> _assert_child_claim -> _assert_budget_clock` 的 BudgetClockUnknownError: budget_clock_sample_unresolved:sampling。它与先前修复的预注册准入不同，发生在准确entry token/fact已持有的发布事务内，不能直接扩大成所有unknown重试。压缩原始证据 `/tmp/sdk-entry-wrapped-admission-v2-20261106/G17-diagnostic-entry-observations.json`；准确后续状态与父清理见G17-stable-observer-fixed-readback.json。父后续recovery_required/authority revoked，controller failed；不以清理改判成功。不再无修改重跑模型，先验证发布回滚及准确样本续接的安全条件。

本地25页Wiki导出完成 `/tmp/sdk-entry-wrapped-admission-v2-wiki-20261106`，wiki-export.log保留。ref release/0.8.0未发布，不声明远程链接可用。

回归范围复核发现历史184模块runner只排除24个hash相关ID，没有排除后续识别的13个内部SQL写入用例，禁止直接复用。较新45项deferred已包含这13项；remaining-66.manifest.json仅能作为66个准确ID的范围，不自动转移旧包通过结论。原76项准确范围及测试源码另冻结到 `/tmp/sdk-entry-wrapped-admission-v2-arbitration-regression-20261106`，未执行；字面SQL筛查无命中但不等于完整动态调用审查，不能宣称全范围已审计。

### 已实现入口发布竞争的准确事实续接（未打包）

新真实祖先/子执行采样复现 `tests/test_entry_publication_sampling.py`：先修正夹具补齐父confirm_handler_entry；修正后旧产品在与原生现场相同 `_finish_budget_sample -> _assert_child_claim -> _assert_budget_clock` 栈失败，原日志sdk-entry-publication-sampling-baseline-confirmed-20261106.log保留。

仅在匹配的子entry marker仍存在的真实发布事务内，祖先sampling拒绝产生私有信号；外层control lock内、事务退出后核实同一可用idle连接、准确marker恢复、receipt不存在、owner及fact相同，才确认可续接。guarded_entry保持原token/fact/lease与原deadline，继续检查authority；其他clock错误、ACK replay、清理异常不进入此路径，不结束祖先样本。独立复核无该范围具体阻塞。

正例、祖先不解除直到原截止、清理clock ACK失败不认证/不重试三个无模型测试通过1.388秒，日志 `/tmp/sdk-entry-publication-sampling-three-cases-20261106.log`。相关四模块回归句柄1434已启动，预计约一分钟；不启动新模型或CI，不将源代码结果当作当前安装包原生通过。

上述相关四模块源码33项全通过52.287秒，`/tmp/sdk-entry-publication-related-regression-20261106.log`。已冻结新候选 `/tmp/sdk-entry-publication-candidate-20261106`，独立venv未继承系统依赖；151产品文件source/wheel/installed逐字节一致，相对v2仅budget_capture.py及supervision.py改变，parity.json保留。安装包同一33项范围已启动，预计约一分钟；原生监督尚未重验，旧候选原生通过不自动迁移。

### 新安装包定向回归及稳定监督通过（待独立终审）

`/tmp/sdk-entry-publication-candidate-20261106/result.json` 证明隔离安装包33项全通过，0失败/错误/跳过，56.907秒。已离线安装PyYAML6.0.3供真实Agent配置使用。

真实稳定监督句柄79061退出0，`/tmp/sdk-entry-publication-G17-stable-20261106/report.json` stable=passed。原360秒/5Agent/32轮上限保持；实际2Agent/5轮，准确Run/controller预算、原观察消费、诊断产物、准确重放及单代际唯一子成立；父native及诊断native均cleaned。原失败保留，新结果待独立核对父子最终业务状态/回执，不将整项G17改判通过，其余旧候选Gate也不自动转移。

当前安装包准确66-ID旧API范围已启动，冻结remaining-66.manifest.json，预计1–2分钟，不运行45项deferred。184模块字面内部SQL写入清单已生成legacy-sql-literal-inventory.json，407处候选待进一步区分夹具/错误断言/实际写入；仅静态清单，不是安全全量执行证明。

稳定监督独立终审通过该切片：control请求父/子、Kernel父/子/controller均succeeded，两个runtime effects committed；两个native精确回执均匹配原lease/attempt/fence/deadline。不是只凭调用次数或退出0改判。原360秒/5calls32turn，实际2calls5turn。完整G17仍缺其余当前包范围及旧API全量证据。

当前安装包G01/G13无模型验证退出0，`/tmp/sdk-entry-publication-G01-G13-20261106/acceptance.json` 两项passed，限配置/能力合同及拒绝路径，不冒充strict后端。

当前66项旧API整批65通过1失败，0错误/跳过，102.156秒，remaining-66-result.json及remaining-66.log保留。失败test_crash_after_kernel_acceptance_replays_one_execution预期succeeded实际failed；原TemporaryDirectory已删除现场。仅增加失败条件下保存public Kernel执行/返回/业务attempt的诊断，未改原5秒budget或断言；安装包单例1项通过1.323秒，不关闭原批次失败。准确原66-ID范围带诊断重验已启动，预计约2分钟；不运行模型或CI。

带失败取证、原66项准确范围整批退出0，66全通过/0错误/0跳过，91.278秒，remaining-66-diagnostic-result.json及日志保留。首次65/66失败原因仍未解释，不能据后续通过宣称已修复。

当前安装包G05/G06完整组/轮次原生场景共用一次图已启动，输出 `/tmp/sdk-entry-publication-G05-G06-native-20261106`，原3600秒/16Agent/128轮上限不变，预计5–10分钟首次检查。此为当前包多轮/返工实证，不宣称先前G06同因修复；脚本对G06的工具负例/完整清理尚保留显式not_run项，必须结合准确补证和审查后才能判定整个Gate。

G03/G04独立影响复核：两候选仅4个Kernel文件改变，Agent依赖/产物/输入/文件工具/事件重投代码逐字节相同；旧原生结果可证明其原发生事实，不能伪称新wheel执行。新包最低需补一次现有依赖图；相同重投/ID冲突路径不因该delta机械重跑，旧报告来源保持不变。

## G06 歧义负例的保留证据补充评估

2026-11-06 23:50 CST附近：原多轮图句柄42623确认仍live，无最终报告；未重启或变更原预算，下一预计约5分钟后检查。

只读复核原歧义case，独立审查确认bindings在读取输出前先拒绝多个匹配行，因此不需要为此负例证明每个候选自身都有模型响应。可复现脚本 `/tmp/sdk-entry-publication-candidate-20261106/verify-G06-retained-ambiguity.py` 已执行成功，产物 `G06-ambiguity-retained-supplement.json`：准确同Run/problem/round、不同root/child、root真实模型返回及有序open/send/close/wait、consumer ambiguous且无command/execution/effect/adapter入口、准确native清理回执与原600秒/8calls/48turn预算均逐项断言。

原报告仍为failed，child模型返回仍未证实；补充结论仅覆盖历史歧义拒绝最低负例，不冒充当前wheel执行或完整G06。44个Agent产品文件影响比较见G06-negative-agent-path-parity.json；除默认null未进入的token_budget外该路径未变，Kernel变化须结合当前多轮图另行验证。没有新增模型调用。

## 当前安装包完整默认值与双语文档一致性

隔离安装包的ApplicationSpec({'coder': {}}).to_dict()['defaults']与详细指南及中英文Wiki的完整JSON注册表逐字段比较。初次检查发现docs/AGENT_CONTROL.md遗漏recovery.cancel_grace_seconds=2；仅补齐该文档字段，未改产品。两个Wiki已有该默认值。修正后24个顶层字段及全部嵌套默认值一致，产物 `/tmp/sdk-entry-publication-candidate-20261106/defaults-docs-parity.json`，可复现脚本verify-defaults-docs.py。该检查不调用模型、不冒充行为或完整G01/G18验收。

## G06 新包真实图定位到已知完成事实的提交准入缺口（2026-11-07）

23:55 CST原句柄42623确认live；只读快照G06-progress-2355.json保留：首轮两个coder及reviewer成功，第二轮一个coder成功，另一个65817556280147f2bbc55d5bc61eabee仍submitted。两组closed。准确Kernel执行agent:65817556280147f2bbc55d5bc61eabee仍running。obs_events已记录handler_outcome kind=ok；settlement记录late_thread_fact，completion_time_known=true，保留原成功candidate，但_sdk_completion_decision_error.phase=owned_decision、exception_type=_ControlAdmissionTimeout。准确证据G06-pending-child-events.json及G06-pending-settlement-readback.json位于最新候选目录。没有准确栈，不能区别提交初次锁准入或拒绝后连接核验锁准入。原图预算/状态未改，未重启。

无模型实际Kernel RLock竞争复现已失败（running而非succeeded），日志 `/tmp/sdk-owned-decision-control-source-baseline-20261106.log`；最初系统python无SDK依赖仅导入失败，另存baseline日志，不算复现。

源码修复：_control_lock仅对本身生成的pre-yield拒绝、原异常身份一致且清理成功后追加准确连接证据；_transaction复用原_begin_failure证据通道。Runtime释放生命周期及decision guard后按原循环继续，先在原权限/期限内验证原连接可用且idle，再尝试同一candidate；不重放handler或采样。拒绝后只读核验锁支持原期限内分片准入，并核验active/stop/owner.revoked。初稿在共享生命周期锁内持续等待，被独立审查指出会阻塞无关操作；已撤除，未打包或原生运行。修正版独立审查无具体安全阻塞。

初步五个无模型用例通过13.534秒；进一步将body负例定位到实际事务内部_validate_result，并明确断言无关生命周期操作在Kernel锁释放前已推进，最终五项正在检查。产品尚未重新打包，当前原生图仍运行旧冻结包；不得以源码修复改判原图或G06通过。

强化五项结果：4通过1断言失败，14.064秒，`/tmp/sdk-owned-decision-control-final-five-20261107.log`。body负例的计数断言误将已证明未进入事务的首次锁拒绝也算作body重试；准确流程为两次candidate尝试、仅一次_validate_result事务body。改为同时断言两次尝试及仅一次body，单项2.628秒通过，`/tmp/sdk-owned-decision-body-final-20261107.log`。没有放宽原异常或期限断言；不称最终同批五项全部通过。成功路径明确验证无关生命周期操作先于Kernel锁释放推进。源码补丁仍待相关边界回归和新制品验收。

现有scripts/check_docs.py已加入三份完整默认值表与被导入ApplicationSpec的比较，语法检查通过。之前独立安装包默认值比较通过；新增入口尚未完整运行，不将语法检查当作文档检查全通过。

## 已知完成事实准入修复：新候选冻结

`/tmp/sdk-owned-decision-candidate-20261107`为唯一新目录，隔离venv、PyYAML6.0.3离线安装及parity.json保存151产品文件逐字节一致。相对上一候选仅Kernel _sqlite_base.py/runtime.py改变；没有改Agent层或冻结业务配置。独立修正版审查无具体安全阻塞。新增控制锁边界模块10项通过2.272秒，`/tmp/sdk-owned-decision-control-boundaries-20261107.log`，明确真实pre-yield拒绝成功清理后才记录原异常/连接；connection-check伪同型异常、body同型异常及release清理失败不记录授权证据。

隔离安装包原句柄1644执行六完整模块及14项准确选中无SQL写入的Runtime用例，manifest.json记录准确ID；没有运行同模块直接SQL BEGIN竞争分支。预计1–2分钟。原模型图句柄42623保留，不改输入/预算/状态、不重启；源码修复不影响其已安装旧wheel。

新候选安装包回归句柄1644退出0，result.json：78项、0failure/0error/0skip、120.711秒，原六模块与14准确选中ID完整执行，原预算与断言不变。最终五个新增Runtime边界均在此批次通过（成功、stop、revoked、expiry、body）。安装来源为准确隔离site-packages；不替代完整旧API/平台矩阵。文档链接/新增默认值注册表检查及README四例开始执行，预计30–60秒，无模型调用。

## 当前包文档运行入口出现旧API示例失败

原句柄23370退出1，docs-check.log保留。链接及三个默认值JSON比较阶段没有失败，英文两个示例执行后，中文README第1例原task.wait(timeout=10)超时，随后OrchestratorHost.stop未在关闭期限内完成，外层原30秒TimeoutExpired。原现场 `/tmp/sdk-docs-README.zh-CN.md-example-1-x4geldmb`：checker.json、wait-failure-before-cleanup.json、stdout/stderr及原数据库全部保留。不是四例全部通过。

失败时Kernel已claim/running，无handler观测；worker位于_diagnostic_note(execution_claimed)重试，未到处理函数。结算journal文件为空，具体初始化错误原诊断未保存；不能仅凭此断言与本次完成提交补丁同因。诊断sql_events虽持有RLock，但逐个dict分配可能触发本线程连接析构的重入追加，导致deque mutated during iteration丢失SQL快照。仅将事件容器先冻结为tuple，并新增runtime settlement_error/storage/diagnostic_errors快照。

保持原示例内容、10秒等待及30秒外层上限，单例附加诊断重验输出 `/tmp/sdk-owned-decision-readme-diagnostic-20261107`，句柄21819，预计30秒；未运行模型或全量重验。原失败不因后续通过自动关闭。

独立影响复核明确：本轮仅完成准入变化，不应机械重跑全部历史模型功能。未来当前wheel完整G05/G06图若真实通过，可与准确Agent/adapter路径字节一致、当前安装包改变边界测试及原历史功能报告组合判断适用性；不是把旧报告改写为当前来源。G14须按具体崩溃marker判断是否涉及改变的owned-decision准入/清理窗口；仅相交窗口需要新原生切片。平台矩阵和G18仍独立开放。尚未发生未来通过，不据此改判任何Gate。

## 新候选交付切片与README保留失败

单例附加诊断句柄21819退出0、3.977秒、输出42，`/tmp/sdk-owned-decision-readme-diagnostic-20261107/result.json`。未重现首次失败，因此settlement初始化具体异常仍未知，原文档批次failed保持开放，不能将单例通过解释为已修复。原英文两例完成，中文第2例未在失败批次运行；不宣称四例全过。

当前包源码归档构建及实际离线no-deps安装句柄81697退出0：sdist-result.json证明151产品文件sdist/wheel/安装逐字节一致，安装后METADATA一致。sdist-env继承system-site-packages，不证明干净依赖解析或完整平台矩阵。

静态文档链接单独核验582个链接/89个文档全部有效，doc-links.json；不替代README执行。25页Wiki本地导出至 `/tmp/sdk-owned-decision-wiki-20261107`，wiki-export.log保留；ref release/0.8.0尚未发布，不声称远程链接可访问。

原G05/G06图仍保留原冻结entry-publication包及3600秒截止，已确认第二轮一个成功处理结果卡在owned_decision准入；没有改变其状态或重启。预计按原一小时截止于00:42 CST附近核对最终退出/清理，不在此之前反复刷新。新包原生图应在原进程终态、已知回归问题处理后顺序执行；当前不启动第二张模型图。

完整发现的独立复核边界：仅证明冻结树在本机Python/平台/导入环境的范围；59为名称规范化后的额外重复实例，原短/全名拼写未逐项保留，不代表59种独立行为。其他平台条件发现可能不同。full-current-discovery-review.json 保留这些限制，不据索引成员身份重新认证历史通过。
