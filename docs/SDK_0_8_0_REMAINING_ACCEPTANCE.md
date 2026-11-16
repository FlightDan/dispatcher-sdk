## 2026-11-15 当前安装包的待收口项

上一安装包 `/tmp/sdk-080-g04.UAOzl4` 有 G01–G17 共 17 项通过的原始证据。G18 入口修复包为 `/tmp/sdk-080-g18-entry.yqdWYt`，151 个产品文件与工作区内容一致，相对上一包仅变动 `execution_kernel/context.py`。本包按候选目录的 `candidate-impact.json` 复用和补验，逐项保留证据对应的安装包。

逐项复用依据、对应原始记录和当前证据见 `/tmp/sdk-080-g18-entry.yqdWYt/current-candidate-acceptance.json`。

| 验收项 | 剩余证据 |
| --- | --- |
| G18 | 按 2026-11-16 更正，交付目标是 Linux x86_64，已有真实 OpenCode 证据。完整安装包回归及最终验收仍未完成。当前修复包 G04 两个真实场景、G11 原场景与受控入口竞态均通过。原 G11 现场的确切交错顺序未留存。当前修复包已完成独立 sdist 安装、双语 Wiki 导出、592 条链接与 4 个 README 示例，以及 Python 3.10.21 的 19 项入口定向回归。 |

以下保留 G18 原 G11 失败现场的初步只读核对。worker_dispatch 到 handler_outcome 为 0.513 秒，原租约仍余约 274 秒。准确第一代入口仍 pending，持久预算尚无 execution 起点，保留两个已确认采样回执、无未决采样标记、无效果、无原生监督义务，存在一条完成意图。进程退出时保留 running 与 late_thread_fact，现场未观察宿主后续扫尾结果。现有 1.5 秒夹具只复现同一外部症状与不同的协调器拒绝。下一步应区分入口采样异常保护分支和协调线程交权分支，保留原预算与原生状态。原始只读结果见 `/tmp/sdk-080-g04.UAOzl4/G18-original-G11-entry-window.json`。

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

## 2026-11-07 G02 复用当前候选真实执行证据通过

只读复核既有G05现场，确认新建独立Python3.13环境关闭system-site-packages并实际安装当前wheel；原报告记录实际安装导入路径。8份OpenCode1.18.32原会话数据库以mode=ro读取，session ID与SDK一致，均有完成的assistant模型响应、真实工具活动及SDK成功产物；原精确guard清理回执和实际授权Popen路径共同证明原生执行。149产品Python文件在当前工作树、冻结来源、安装目录和wheel逐字节一致。独立复审无G02具体缺口，G02现passed，范围仅Linux x86_64/Python3.13。未保留历史OS PID快照的限制明列，不宣称新增执行或完整平台矩阵。

审计脚本、result.json、independent-review.md见 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/G02-retained-native-audit。未新增模型、未运行测试或CI。当前完整通过G01/G02/G05/G13；其余Gate与整体Goal保持未完成。G06专项按原定13:51再检查。

## 2026-11-07 G05 当前原生两轮返工链通过；G06仍缺两个原生负例

原监督单元终态退出1且tree_reaped=true；必须按Gate分开解释：正式acceptance.json中G05=passed/exit0，G06=not_run/exit1（两个负例未执行），并非本轮G05失败。全部8次真实调用、两轮coder实际adapter区间重叠、准确输入/产物/反馈绑定、显式返工、reviewer读取修正结果和每次原生清理回执均通过；独立只读审查支持当前Linux x86_64/Python3.13安装包G05关闭。reviewer延续是逻辑lineage，两轮原生session不同，不宣称同会话。

G06还缺真实工具路径歧义引用、调用组缺失输入负例，不提升passed；历史失败保留。此次560事件无丢失，第二轮一个coder从服务submit至claim仍等待63.965秒：已直接定位到run_once/claim重试，存在控制锁准入超时、lifecycle短窗口超时和预算采样超时，非工作线程未分配；尚未确认锁持有者或安全修复，不宣称延迟已解决。原始事件及错误代码位置见slow-child-evidence.json。

完整准确报告、terminal-stage-audit.json、slow-child-evidence.json、independent-G05-review.md位于 /tmp/sdk-supervisor-parent-diagnostic-candidate-20261107/native-filtered-dispatch-attempt。当前索引G01/G05/G13通过；目标未完成、无活跃测试、不自动重跑。

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

# 0.8.0 剩余验收清单

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


核对日期：2026-11-07。范围以 SDK_0_8_0_AGENT_CONTROL_GOAL.md §7–8 为准；本清单不修改合同。当前本地分支 release/0.8.0，工作树存在大量既有改动，未重置、推送或发布。

## 当前边界

G01–G16 的最低功能合同状态见 SDK_0_8_0_CURRENT_ACCEPTANCE.md；G13 仅能力声明及拒绝路径，不提供原生 strict 后端。G17 未完成，G18 缺平台证据。不能把这些概括成三个同等大小的 bug，也不能用新增通过数量表示它们已经关闭。

此前源码候选为 /tmp/sdk-commit-ack-candidate-20261107（当前新增delivery-guard修订及其候选见本文顶部）：包含W的等待退避、参与锁拒绝清理回执及COMMIT实际尝试边界修复；wheel已安装，149个Python产品文件与当前源码/冻结来源一致。准确18项合同索引见该目录current-candidate-acceptance.json；27项前候选通过保留来源；最新29项为27通过、两项原setUp期限失败，不能整体提升。尚无最终sdist、全量回归或平台验收。

原N真实链路14927已终止失败：两轮功能协作完成，但coder适配器没有重叠，不能继续写“未有结果”。正式退避修复后的真实重验原句柄64270已启动，原预算3600秒/16调用/128轮不变，计划北京时间07:54检查，详细启动及宿主PID证据见新候选native-groups-launch.json。07:54按期检查已发现两名coder在claimed_setup因activation非open被取消，G05本场景已失败，进程仍live并待原期限终态；准确证据见新候选native-first-scheduled-check.json，下一计划08:35检查。G06还缺真实工具路径歧义引用、缺输入负例及逐操作清理关联证据。不得将“G05/G06共用链路”解释为此次能够自动关闭两个Gate。历史失败和缺平台保持开放。

## 固定工作项与关闭条件

| ID / Gate | 尚缺什么 | 现有证据及关闭条件 | 下一步与耗时边界 |
| --- | --- | --- | --- |
| R1 / G17 | 继承父期限测试的原间歇失败没有解释 | 原失败现场 /tmp/sdk-inherited-parent-deadline-9u_xzf9m/evidence.json、/tmp/sdk-inherited-parent-deadline-caeh8a9q/evidence.json：child ready，但未实际进入 callable。后续通过不能关闭原失败。需定位实际等待/执行阶段，明确合同或实现缺陷，修复后验证原入口、期限及清理不变量。 | 先检查 ready→entry、父进程 enqueue→宿主接收的实际代码路径及原证据；没有新假设不再重复单例或原 31 项前缀。根因定位无法给可靠总时长，不冒报完成时间。 |
| R2 / G17、G18 | 全量旧 API 与完整 Python 回归未闭合 | 旧settlement-startup候选的发现快照为3509实例/3450不同ID，3395静态声明及55继承项；它不包含后来新增的修复测试，不能再称当前源码完整计数。历史逐ID结果和排除原因保留原来源。当前native-admission候选50项针对性验证通过，原presample候选另有100项尾部通过，均不等于当前全量。 | 对当前源码重新收集并逐ID核对可复用证据、受限夹具、平台条件与待执行项；保留Python3.10–3.13完整适用范围。先完成当前真实graph，避免并行负载；不直接运行未审查夹具。 |
| R3 / G17 | 替换结算夹具的支持范围已核对，原非等价语义仍保留未证实 | 实际 Runtime 串行 WAL 锁竞争及独立触发器异常传播已通过；旧 Kernel DELETE 保护绕过不适用于受支持构造；手工未知记录不能凭后来水位生成终态。独立审查及逐项处置见 runtime-settlement-gap-disposition.json。 | 此夹具差异清单已处置，不再为禁止操作或无授权终态补跑；不代表一般旧 API/认证超时路径或 G17 完成。 |
| R4 / G18 | Linux/Windows、x64/ARM 原生支持矩阵不完整 | 合同要求每个宣称支持 OpenCode 的原生组合至少有安装包核心场景；已有本机 Linux 证据及部分 Python 矩阵不替代其他原生平台。Windows ARM Python 3.10 仅沿用已有明确 x64 兼容范围。 | 缺授权可用原生主机/执行入口；此前询问尚无答复。可准备可携带验证入口，不能在缺环境时标不适用。主机到位后按准确场景估时，不报跨平台完成 ETA。 |
| R5 / G18、§8 | 最终候选一致性与独立审查未结束 | 本机 sdist→wheel→干净环境安装、默认值、双语示例、Wiki 本地导出已有证据；尚非最终归档。需在产品及必要测试修复稳定后核对受影响回归、公开类型、示例、报告及制品来源，并完成独立审查阻塞项闭环。 | 依赖 R1–R4；不为每次报告编辑重复构建，不推送、不发布。最终验证范围稳定后估时。 |

## 执行与成本约束

历史完整候选要求索引（不代表当前执行候选）：/tmp/sdk-full-clock-pairing-delivery-20261107/current-candidate-acceptance.json。两项修复相关20-ID范围及配置/能力拒绝22-ID范围已完成四Python版本。完整sdist→wheel已补齐NOTICE，151个产品文件等于已验clock-pairing候选；此前最小wheel缺件记录保留为历史限制，不再列为当前待修复项。

当前候选Python3.13 Agent状态48项通过，163.802秒；四个README示例、三份默认值注册表、592个本地链接及六个公开类型消费者已通过。完整Python回归、原失败根因、原生平台和最终归档仍缺证据，不能整体沿用旧passed表。

R2最新补验：跨进程接管恢复夹具改用正常SDK创建/决策操作，完整单路径在Python3.10–3.13通过；两次真实崩溃恢复、原预算、历史事件及实际独立handler进程断言保留。source_revision参数默认0维持其他消费者，本夹具显式1；独立审查及默认AST等价证据保留。此不等价于原人工legacy.waiting事件，也不证明真实宿主隔离。准确结果见process-adoption-public和process-adoption-python-matrix系列。动态归并更新1002/3450、2448个无索引证据；33个继承夹具含后续人工回执，尚未改造或执行，不能只替换setUp后整体标通过。

### R1 原失败路径审计补充

只读复查原两个失败的 child worker_ready 宿主回调，分别耗时 0.0006 秒和 0.0005 秒（四位小数），均正常返回且没有 child on_entered。准确浮点值、原始来源及复查脚本保存于候选目录 original-ready-callback-audit.json / audit-original-ready-callbacks.py。排除的仅是该回调函数本身长时间阻塞；没有排除宿主其他工作、调度或 worker 内部等待。

当前 POSIX 路径：worker 发 ready → supervisor 收 ready 并转发宿主、向 worker 发 invoke → worker 调用 invoke_handler → HandlerContext._enter_handler 先做 _start_observation，再做入口预算捕获/guarded_entry → _confirmed_entry_packet 再做 _confirm_handler_entry 的 checkpoint 与 confirm → worker 发 entered → 才调用用户 handler。宿主收到 ready 不证明 worker 已取得 invoke，更不证明实际 handler 进入。原失败缺这些 worker 内部阶段边界；不能仅依据 SQLite 聚合耗时认定哪次写锁导致失败。下一份有价值的取证必须区分这些阶段，而不是只增加宿主 ready 回调记录或重复单例。未修改产品、未关闭原失败。

1. 优先 R1 的原始失败及执行路径审计；R2 先归并已有证据。无变化重跑和零散新增通过数量不作为推进依据。
2. 39 项 shutdown 子集现已完成：原批 27 passed、1 failed、11 未执行；审查修正异常类型判断后仅补跑 12 项，全部通过。32 项源未改、7 项采用修正夹具，原失败保留。索引更新至 836 个不同 raw pass、2557 个静态方法无该索引证据；表中 797/2596 是本清单初次核对快照。此子集不代表完整回归，不关闭原期限失败。
   后续五个初始化/宿主/工具/服务清理模块准确 47 项原样通过、无 skip，80.352 秒。当前索引更新至 883/3393、2510 个无该索引证据；成功顶层结果清单的有界遗漏审计无未归并 ID。没有把这些局部通过提升为 Gate 完成。
3. 每次实际执行前给出准确清单、它关闭哪个缺口及有证据的 ETA；只到 ETA 或用户要求时检查。保留原句柄、期限和原失败，不因观察超时重启。
4. 当前存在已知未解决失败，不启动 CI；没有新模型验收需求时不调用模型。外部平台缺失不妨碍本机独立工作，但不得宣称整体完成。
5. 前一轮状态核对没有关闭任何 Gate。此清单明确剩余范围和下一步，不是验收通过证据，也不给无依据的整体完成时间。

原生资源 61-ID 范围已有逐项通过证据，native-resource-scope-resolution.json 保留原失败及两项共享辅助方法修正边界；受限环境的五项 skip 均已单独在允许本地通信的环境补验通过。此为 R2 的局部范围闭合，不关闭 R1/R3/R4/R5。

### R1 原失败采样所有者差异

三方取证已实现并经独立审查：host并发记录锁、spawn supervisor入口及fork worker独立记录器；fork后在使用继承锁前检查PID，并解包继承wrapper，退出恢复host方法。隔离检查覆盖四线程161事件连续序号、fork/spawn主体分离及恢复，无SDK库/模型执行；原异常保留检查仍通过。随后仅一次原期限安装包用例通过8.658秒，原句柄93343退出0、tree_reaped=true。现场 /tmp/sdk-inherited-parent-deadline-0sxthnwb 保存host913、两个supervisor各15、两个worker385/61条记录，无显式截断。父worker三次采样拒绝均与准确同execution的host采样调用区间重叠，其中一次发生于host begin返回之后、finish调用之前；另两次在finish调用内部。方法边界不等于事务提交边界，不能据此确认具体拒绝行，更不能解释历史child失败，但已明确后续不得只考虑父worker而漏掉host采样者。child无拒绝，原失败未重现，不继续重复单例。当前候选deadline-all-actors-{result,supervisor,analysis}.json、冻结source、入口及check-all-actor-probe.py保留证据；未改产品、未关闭Gate。

修正容量后仅运行一次原5秒父期限用例：当前安装包1/1通过，8.497秒，0 failure/error/skip；原句柄48359退出0，专属子树tree_reaped=true。deadline-overlap-result.json / supervisor.json / log、冻结deadline-overlap-source及analyze-deadline-overlap.py / analysis.json保留来源。现场 /tmp/sdk-inherited-parent-deadline-e69ajpe_：父worker405条、子worker55条，无显式截断；父记录覆盖子入口时段。子_capture_entry_budget约0.315秒、guarded_entry约0.043秒，子无采样拒绝；父另有一次拒绝。因_assert_budget_clock只检查自身与祖先，不查后代，不能把父拒绝归因于子标记。新确认的限制是工具仅覆盖worker，未覆盖同一execution的supervisor/host采样者；下一次因果诊断必须覆盖这些主体，不能原样重复worker-only probe。原历史失败仍未解释，未修产品或关闭Gate。

前一轮取证工具已修正为独立 sampling=1024、entry=128 条容量，并在采样 begin/finish 记录准确 token 与 execution_id；每类耗尽时尝试写一次截断标记，缺少标记不证明未截断。安装包环境下的隔离工具检查确认：600 次合成采样调用耗尽采样容量后，入口事件仍保存；标识、连续序号、原返回值保留，诊断写入失败不替换不可字符串化的原异常。check-worker-probe.py / worker-probe-check-result.json 保存入口与结果。独立审查指出截断写入只能 best-effort，元数据已据此纠正。工具检查不打开 SDK 数据库、不执行 handler，不计 G17 验收；工具检查当时尚未运行原期限用例，后续实际运行结果见上段，侧写 I/O 扰动仍存在。

2026-11-07 时间线交叉核对发现取证缺陷：最近一次 worker probe 的父进程 128 条记录，在子进程 probe 启动前 0.403 秒就已耗尽；子进程首次 sampling refusal 发生在父记录结束后 0.687 秒。六次拒绝全部没有同期父进程记录，因此不能用这份日志确认具体父采样占用或饥饿。可复查入口与结果为当前候选 audit-deadline-trace-overlap.py / deadline-trace-overlap-audit.json。下一次原期限诊断前必须先解决父记录保留窗口，不能原样重复运行。已有 test_entry_sampling_contention.py 和 test_entry_publication_sampling.py 覆盖受控采样释放/原窗口耗尽，不另跑同类测试冒充历史根因证据。本次只读分析，无测试、模型调用或产品修改，R1 仍开放。

只读检查两个原失败数据库的 kernel_budget_samples 与 sample receipts，原 9u_xzf9m 现场最终遗留 child sampling，caeh8a9q 最终遗留 parent sampling。准确记录为候选目录 original-sampling-owner-audit.json。最终行不能给出标记创建时间或存活区间；第一现场最终无 parent marker 也不排除此前短暂的父采样竞争。因此尚无共同根因，不能仅凭父采样假设改产品或重复通过单例。若开展新诊断，必须在父/子 worker 同时区分 begin/finish/ack、sampling refusal 与入口阶段。

R2 当前逐 ID 原始通过索引更新为 944/3393；新增仅来自已保留的 native-resource-tail/permitted 实际通过，跳过未计入，原失败仍保留。静态差值仍不等于未执行数或完整动态范围。

R3 补证：实际 Runtime 串行完成采样在真实 WAL 写锁下消费原 work cutoff，单项安装包通过 6.039 秒；实际存储 contention、每次传入上限 <=.1、durable expiry witness、准确 unknown/pending 与不得成功结算均有证据（live-serialized-clock 系列）。该部分缺口关闭；DELETE EXCLUSIVE 读阻塞、trigger 专属错误及旧终态合同处置仍保留。

R3 更新：真实独立 SQLite trigger 的 IntegrityError(1811) 在归档边界传播单项通过 1.681 秒，原异常对象/cause、原 receipt/胜者及一次业务调用保留，之后正常归档通过。实际 SDK 表 trigger 事务语义未测，目标禁止该修改。独立审查确认文件型 Kernel 构造固定 WAL，旧绕过保护改 DELETE/EXCLUSIVE 夹具为目标禁止的非支持配置，不作为发布必测项；DELETE 行为仍记未测，不推广到 settlement journal。R3 仍需处置旧 unknown 完成时间的终态预期。证据为 trigger-error-review.json 及 result/source/supervisor。

R3 最终处置：旧 later_watermark fixture 手工调用 handler 并写入 completion_time_unknown，没有认证监督器结算决定。独立审查确认后续水位只证明当前时钟，不能授权原返回生成新 timed_out 结果；旧该预期无效，旧终态行为明确未证实。现有 runtime-authority-final 三项当前安装包证据可用；AST 核对相关方法及 helper 未变，runtime.py 当前源码与安装文件逐字节相同。runtime-settlement-gap-disposition.json 统一记录四类差异，不宣称通用旧 API 或认证超时验收通过。最新静态索引 480 模块、3395 声明方法、946 个不同原始通过 ID（新增两项有效覆盖），不是全量动态验收。

R2 依赖范围：准确77项审查后33项在Python3.10/3.11/3.12/3.13全部通过，44项逐ID保留未执行（依赖夹具直接写表或锁事务非rollback），不自动改标不适用。manifest及review/matrix证据在交付快照dependency-api系列；同33项跨版本不重复计数。

R1 新上下文审查：deadline-fresh-causal-review.json 核对原 child worker_ready 的 observed_at 到继承 cutoff 仅0.866/1.326秒。存储写入时间不是ready或invoke时刻；尚不能证明哪个阶段耗尽余量。父采样可重复竞争，但无历史饥饿证据；采样还承担观测时钟前跳及共享水位，不得无依据删减。没有新增产品缺陷结论或重复单例。

完整发现的独立复核边界：仅证明冻结树在本机Python/平台/导入环境的范围；59为名称规范化后的额外重复实例，原短/全名拼写未逐项保留，不代表59种独立行为。其他平台条件发现可能不同。full-current-discovery-review.json 保留这些限制，不据索引成员身份重新认证历史通过。

### R1 原ready消息携带的预算下界

只读复核两个原失败：child-ready包内observed_budget_envelope的持久checkpoint距最紧work cutoff仅0.627844/0.587181秒。这是发出该包时已保留的预算余量上界，宿主实际收到后只会更少；此前worker原始observed_at到cutoff的0.866/1.326秒不是收到后的可用窗口。host invoke开始到ready回调分别约0.658/1.238秒，回调本身仍不足1毫秒。不能将原始wall与floor差值直接归因于某段锁等待、时钟前跳或调度。准确原字段与计算见当前候选original-ready-published-floor-audit.json。下一次因果取证必须同时覆盖child请求/准入/启动至ready和ready至entry，不能只针对ready之后的采样竞争。未修改产品、测试或预算，未重跑，R1仍开放。

### R2 Python3.11三级进程暂停续接新增原始失败

split-recovery-python-matrix按原范围顺序补验：Python3.10两项通过40.465秒；Python3.11接管项通过4.663秒，三级进程项在release后driver.join(15)仍存活，原AssertionError保留，整版55.422秒失败。原句柄16553退出1，监督器tree_reaped=true；Python3.13未启动，不标通过。原结果、逐版日志和冻结测试保存在当前候选split-recovery-python-matrix目录。不能用Python3.10/3.12通过抵销该失败。

失败日志缺少驱动线程栈，临时工作目录已由原夹具清理。仅对失败断言补充清理前所有线程栈、原outcomes/errors及诊断错误；不改15秒join或其他等待、产品及业务断言。AST解析通过，尚未重验该诊断版本。该新增失败需定位并修复/验证后才能关闭R2；不启动CI。

### 恢复路径矩阵后续结果：原3.11失败仍开放

仅对3.11失败项增加失败清理前线程栈后单项执行，34.821秒通过，原句柄36607退出0；没有触发栈记录，不能解释或修复原15秒join失败，不继续重复该单例。之前未执行的3.13两项续测通过38.658秒，原句柄65623退出0。两监督器tree_reaped=true，原超时及产品均未修改。当前各版本至少各有所选路径通过证据，但3.11原失败仍开放，不将矩阵标为稳定通过。候选split-recovery-python-resolution.json保留原失败、重验与各版准确来源；不新增ID计数，不关闭G17/G18，无模型调用。

R2取证补强：三级暂停夹具改为失败时原地保留sdk-nested-pause-*临时目录（包括原WAL），成功时删除；driver超时报告附目录路径和清理前线程栈。独立静态审查未发现确认的换代权限缺陷，原失败无栈/现场不能定位。单独检查目录helper成功清理、失败保留以及原异常对象不变，通过；未打开SDK数据库，不计业务/回归通过。尚未重跑此取证版本，不关闭原3.11失败。

## 2026-11-07 Agent状态与取消回归46项完成逐项补验

八模块经独立审查，46个尚缺证据ID完成Python3.12安装包补验；三个直接写内部表的方法及Windows专用锁用例保留排除原因。原受限批31项通过、8项通信权限skip、1项错误、6项未执行；结果写出后解释器仍未退出，显式SIGTERM原监督器，exit143且tree_reaped=true，不冒充正常退出。允许本地通信的续批5项通过后，在知识写入/宿主取消竞态遇到旧预期失败，原日志保留。

独立审查确认原默认协作取消窗口允许原本地执行收尾；不能一律要求recovery_required。仅修正该夹具：host cancelled分支必须验证原execution/attempt/fence/lease、准确runtime效果请求、committed及settled响应、真实Kernel终态和结果；其余分支仍要求indeterminate、准确recovery_effect_id及recovery_required。外部Kernel取消、知识已提交/CAS拒绝重放断言均保留。无产品或超时修改。剩余10项通过66.986秒，原句柄80545退出0、tree_reaped=true；包括原权限环境错误项，原错误不抹除、不推定单一根因。

当前候选agent-state-scope-resolution.json逐ID映射三批结果及排除项；冻结source/manifest/日志/supervisor保留。合成适配器及本地SDK/回环通信不计真实模型验收。静态1028/3395、动态1050/3450已有索引通过证据，2400个无索引证据不等于从未执行。仅闭合该46-ID范围，原期限、3.11暂停退出失败及完整回归/平台Gate仍开放。

## 2026-11-07 离线协议与收件箱回归91项通过

五模块114项独立审查后选91个缺证据ID，当前Python3.12安装包全部通过、0 failure/error/skip，16.618秒；原句柄22898及监督器退出0、tree_reaped=true。覆盖真实本地监督进程/清理证据校验、收件箱SDK事务与应用自有表原子性、OpenSandbox假客户端边界以及两个零期限identity查询；没有连接外部沙箱或模型。23项因测试直接改SDK表/保护尝试、构造SDK形状的测试库或专门摘要验证而排除，不能标通过。SDK内部正常标识生成不属于新增摘要检查。

原来源/manifest/result/supervisor保存protocol-regression系列；protocol-regression-scope.json补充准确范围，原runner复用的Agent状态描述不准确，原结果不改写，适用性按准确ID/来源及补充范围判断。产品和测试断言未改。三分钟预估偏保守，同类后续本机批次应按本次16.6秒而非固定分钟数校准。静态索引1119/3395，动态1141/3450，2309项无索引证据不等于从未运行；Python其他版本仍需适用范围补验。原期限及3.11暂停退出失败仍开放，不关闭G17/G18。

## 2026-11-07 离线协议91项完成Python3.10–3.13验证

原句柄48456退出0、专属监督器tree_reaped=true。相同91-ID冻结清单在现有独立安装环境Python3.10/3.11/3.13各91项通过，分别15.902/16.151/17.523秒，均无failure/error/skip；加上既有Python3.12的16.618秒证据，完成本子集四版本验证。产品期间未改，适用性沿用三个环境与当前候选151文件一致性证据。protocol-python-matrix的逐版本结果/日志、supervisor及protocol-python-matrix-scope.json保留准确ID、来源和解释器路径。

不把跨版本重复计为不同ID，不提升为完整Python或原生平台验收；91项范围及23项排除仍见protocol-regression-manifest.json。原父期限、3.11三级暂停退出失败及其他回归/平台缺口保持开放，无模型调用、产品修改、CI或发布。

### R1 原失败时钟偏移取证边界（2026-11-07）

只读复查两个原始evidence.json，同一boot域分别保留11和10个检查点；精确浮点wall−elapsed偏移跨度分别约0.356毫秒和0.022毫秒。报告及可复查脚本在完整候选original-clock-offset-audit.json、audit-original-clock-offset.py。独立复核确认这些已记录偏移没有支持“大幅新累积时钟错配造成历史失败”的归因；初始偏移、未记录瞬态、未观察锚点及墙钟调整仍不能排除。父入口宿主回调到子invoke开始分别约3.547秒和3.083秒，子invoke到ready回调约0.658秒和1.238秒；这些不是实际事务或callable入口边界。原失败保持开放，不以新时钟修复后的通过代替因果证据。不重复无新假设的通过单例。
