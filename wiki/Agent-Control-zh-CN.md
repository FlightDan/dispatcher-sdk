# 实验性 Agent 控制

> 本页记录本地 0.8.0 开发候选包。实现目前仍在本地开发分支。

等待子任务结果时，初始休眠50毫秒；持久状态和诊断不变时逐步退避，最多500毫秒，变化后重置为50毫秒。每次未完成观察仍检查权限并重新采样预算，休眠不超过原工作窗口的剩余时间。因此结果与取消的观察可能延迟最多500毫秒加操作及调度耗时，不增加执行预算。已有结果仍沿用原有先读取后采样及事实交付规则。


调用的原宿主截止时间过后，`Invocation.wait()` 和 `AgentRun.wait()` 若在有界查询中发现与当前执行、attempt、fence 和 lease 精确匹配的待处理迟到事实，可能抛出 `AgentExecutionError`，其 `completion_state="unknown"`。异常快照保留真实调用状态和执行状态，不将其改为完成、取消或待恢复。这仅说明观察时完成状态未知，之后仍可能出现有效结果；不赋予重试、清理、发布结果或额外预算的权限。已确认的终态结果优先。证据缺失、过期、过大、忙或不完整时继续正常等待，仍可能最终抛出 `TimeoutError`，并不保证发现所有不明执行。查询共用调用者原等待期限，每次合计最多50毫秒、间隔至少250毫秒；Run 按轮转顺序检查符合条件的调用。


AgentApp 在接纳请求前要求完成账本初始化成功；账本不可用时构造失败并尝试清理，清理失败仍明确保留。修复存储问题后再用同一状态目录重新打开。该检查不保证后续写入始终成功，也不延长任何请求预算。

Linux 普通返回与适用的通用异常回调在仲裁或存储前采集启动经过时间，原生时钟域查询不能平移该时间。若这次 SDK 首次观察已耗尽原预算，即使返回时间持久化失败，存活监控器仍可尝试超时决定，但仍须通过原有时钟、代次、停止和 effect 检查。该时间是 SDK 观察时间，不证明函数物理返回的瞬间；较早观察后发布被延迟、且持久时间无法确认时仍保持未知。其他平台对此回退保持保守行为。

持久运行时观察不会等待本地待结算登记锁。锁忙时报告不完整、本地结算检查未知，不能据此认定没有待结算事项。观察不授予完成或重试权限。

存活调用的监控器可在生命周期锁与完成仲裁锁内决定已耗尽的超时。它携带原预算，在排除effect准入的同一事务中检查共享时钟连续性：未完成effect进入恢复，否则形成终态。刚发布的超时只由该存活监控器按准确内存发布对象消费；保留的迟到事实不能取得此权限。工作期限后只允许确认本地已捕获的同一预算事实，不新增采样、不确认其他所有者的采样。停止、竞争、缺失事实及不明提交保持保守；响应丢失时核对准确已提交结果。

所有者完成决策抛出异常且无法确认准确提交回执时，保留的结果事实记录失败阶段与异常类型。为避免保留供应商输入，不记录异常正文；此诊断不授予重试或完成权限。

本地结果候选的构造不要求生命周期锁，也不授予交付权限。实际所有者决策之前未取得生命周期锁时，可在原期限内继续准入，保留同一候选与返回事实；停止或原期限耗尽后不再准入。

存活线程的完成提交仅重试已明确证明未开始的 SQLite BEGIN 准入失败，或尚未写入结果即因全局采样拒绝的尝试；须先确认事务清理及准确连接状态。其他执行保留自己的采样所有权，当前提交只等待，不替它确认或接管。按时捕获的返回保留延迟收集后的既有首次提交机会，额外尝试仍受原工作期限约束。各次保留原结果身份与返回事实，尝试间释放生命周期锁，并重查停止及原工作期限。短时写锁准入仍最多 0.1 秒；已准入的完成事务提交前检查原工作截止时间。事务体、提交或清理结果不明不属于此重试。监控采样与返回提交共用仲裁锁；提交持锁时监控只投影已有时间，不新增采样。最终安装包验收仍未完成。

子调用等待的短时收据编码窗口耗尽后，只能在原工作期限内继续发布同一采样令牌和已取得的输入事实。伴随清理失败的异常、尚未取得事实、停止或原期限耗尽，均不授权重新采样或重跑业务。结果事实交付也会拒绝其他调用者尚未确认的全局时钟采样，不替其他所有者完成确认。此源码行为仍待最终安装包验收。

调用或计划待处理期间，宿主仍定期协调；未变化的待处理记录不计作新进展，也不强制增加工作线程检查。实际提交仍显式唤醒宿主，新触发器受理或依赖交付确认会报告进展。

依赖队列为空时使用只读快照检查，仍校验代际、参数和时钟，并在独占宿主代际内保留进程内时钟高水位，不写持久时钟。只要存在任何未确认回执，仍通过新的写事务执行原领取流程。空结果不缓存，后续投递由下一轮检查发现。

托管线程的成功返回和普通异常捕获现也传入入口的原工作截止时间。每次短时存储准入重查确切的有效所有者及停止／撤销信号；停止不能抢占已经执行中的准入。未决或不明采样原样保留，不生成替代事实。此源码修订仍在回归验证，不代表最终安装包验收通过。

调用状态、Run节点列表和原生操作列表使用一致的只读快照观察。其他连接写入期间可返回最后已提交的状态；读取结果本身不授权启动或资源释放，这些动作仍须执行独立的身份、权限和持久化占用核验。

原生进程的完成采样只在入口确认时保留的原工作期限内等待。每次存储尝试最多等待 0.1 秒，配置的控制超时更小时采用更小值；所有重试共用原期限，并按预算经过时间继续收紧。重试保留同一租约、采样所有者和事实；已采样的事实只允许确认，不重新采样。缺少已确认的有限工作期限时，仍只使用单个有限控制窗口。采样未决或存储失败保持未知，不授权重跑处理器；发布时钟事实本身不授权成功结果。

处理器入口尚未建立自己的采样标记时，可在原启动／工作期限内等待其他采样完成；每轮重查权限，不清除或接管原标记。自身已有未取得事实的采样，或确认结果不明时，仍保持未知。

有限超时的 `RuntimeHost.stop` 可能在运行时已完成清理后返回 `False`，原因是启动器退役未能在同一期限内取得锁。停止报告保留已确认的清理结果；后续 stop 重试退役，不重复执行清理。队列交接前的启动器准入超时允许重试同一个已绑定所有者；交接结果不确定时不允许替换所有者或重复提交。

有限超时的 RuntimeHost stop 调用记录固定错误摘要，不读取自定义异常属性或格式化异常。此诊断步骤不替换原始错误；限时记录的类型统一为 `BaseException`，并省略执行上下文字段。后台诊断保留原有详细行为。

AgentApp 自动开启 SDK 管理的完成交付，并在重启时复用
`execution.sqlite3.delivery.sqlite3` 配套日志；请随状态目录一起保留。
已有执行历史但缺失交付日志时会拒绝启动，此路径不会迁移旧日志。
底层 Runtime 的 `managed_delivery` 默认值为 `False`，开启时要求使用文件数据库和线程隔离。

0.8.0 Agent API 仍处于实验阶段，已实现任务和服务调用、依赖触发、动态调用组、显式返工、goal 验证和持久会话。G17 的旧 API、CLI、监督及资源准入已有上一安装包证据。G18 仍需安装包回归、平台覆盖及最终制品和文档核对；准确候选范围见[当前验收记录](../docs/SDK_0_8_0_CURRENT_ACCEPTANCE.md)。详细说明见[英文指南](../docs/AGENT_CONTROL.md)，目标和验收条件见[Agent 控制目标](../docs/SDK_0_8_0_AGENT_CONTROL_GOAL.md)。

关闭阶段默认按批提交生命周期回执：最多八条事件、262144 字节编码后 payload；单条较大记录可推进至 1048576 字节。接收端最多接受 64 层 JSON 容器并拒绝循环，不支持的事实保留待处理。包括单条在内的关闭批次共用原剩余期限，超时不授权重放或新的写入窗口。已接纳事务的必要回滚和只维护逻辑时钟的清理可能稍后结束。详见[回执与期限说明](../docs/EXECUTION_OBSERVABILITY.md)。

## 发起独立调用

使用 `pip install 'dispatcher-sdk[agents]'` 安装包含 YAML 支持的包。在 Linux 上安装 `opencode`，在宿主环境设置 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`，并选择可用的 `openai/...` 或 `anthropic/...` 模型。可选端点变量为 `OPENAI_BASE_URL` 和 `ANTHROPIC_BASE_URL`。凭据应保留在宿主环境中。

```yaml
# agents.yaml
schema_version: 1
defaults:
  runtime:
    model: openai/YOUR_MODEL_ID
agents:
  coder: {}
```

```python
from dispatcher_sdk.agents import AgentApp, ApplicationSpec

spec = ApplicationSpec.from_yaml("agents.yaml")
with AgentApp(spec, state_dir="./agent-state") as app:
    call = app.coder("说明这个任务。")
    print(call.request_id)
    print(call.wait(timeout=120))
```

导入 `AgentSpec` 后，等价的 Python 配置为 `ApplicationSpec({"coder": AgentSpec("coder")}, defaults={"runtime": {"model": "openai/YOUR_MODEL_ID"}})`。也可使用 `app.agent("coder")` 获取同一角色句柄。如果名称包含连字符、以下划线开头，或与 `start`、`close` 等 `AgentApp` 现有属性同名，请使用 `app.agent(name)`；这些名称不能可靠地使用 `app.coder` 形式的简写。状态目录须由宿主管理，且不能允许组或其他用户写入。`soul` 和 `prompt` 是文件路径，相对路径以 `base_dir` 为基准；否则调用输入必须提供任务说明。成功关闭应用会停止其本地宿主，不会留下持久服务；若清理未完成，关闭会抛出异常并保留所有权，以便后续重试。

未启用交付机制的旧版 `Kernel.open_sqlite(..., isolation_mode="thread")` 保留原关闭行为：撤销处理器权限，并完成观察与预算清理，不等待任意 Python 函数返回。Python 线程无法强制终止。托管 Agent 交付还须保留完成能力，直到处理函数结束；所有权未解决时不能成功关闭。两种模式都不会丢弃释放状态不明的容量、待处理结算或仍活动的观察／预算读取器。

需要显式配置运行时时，从公开适配器模块导入，并将实例传给 `AgentApp`。下面保留默认工具权限；需要时在构造器中增加宿主授权或提供商选项。

```python
from dispatcher_sdk.agents.opencode import OpenCodeAdapter

adapter = OpenCodeAdapter(executable="opencode")
with AgentApp(spec, state_dir="./agent-state", adapter=adapter) as app:
    print(app.coder("解释这项任务。").wait(timeout=120))
```

## 配置目前能做什么

YAML 和 Python 定义使用同一套校验：映射递归合并、列表整体替换、省略值继承，只有明确允许的字段可为 null。应用的 `defaults` 如果提供，必须是映射；需要继承时可省略或使用 `{}`，不能传入 `null` 或 Python `None`。未知字段、重复 YAML 键、未知角色引用及静态依赖环会被拒绝。`spec.to_dict()` 返回展开后的默认值与各角色配置，`spec.agent("coder").to_dict()` 返回单个角色的有效配置。完整默认值列于本页下方。

OpenAI 兼容流式 token 结算要求单一结果已结束，且最终用量与所有结果分块绑定同一个非空响应 ID。完成后的用量分块允许 choices 为空，也支持仅工具调用或空文本结果。身份缺失或冲突、结果未结束、用量畸形或传输中断均保留完整未知预留。此源码修复尚待安装包验收。

解析成功不代表运行时已支持该能力。动态分组和宿主提交的服务在当前源码中仍属实验性功能；监督仍属实验性功能，完整恢复尚未完成。非空 token 预算在当前源码中属实验性功能，仅限 SDK 自有 OpenCode 代理，且要求版本化的宿主模型合同：`token_budget.request_limit` 承诺总计费上界，`output_limit` 限制输出。所有回退模型均须有合同，否则拒绝执行。源码用量解析支持 Chat Completions 和 Anthropic Messages，暂不支持 Responses。待结算分组按完整上界占用额度，未知用量阻止后续准入。该功能尚未通过真实 OpenCode 验收；`budget.tokens` 默认仍为 `null`；模型回退只按下文宿主配置选择；推理档位须由宿主显式授权，见下文；strict 执行所需的原生后端尚未提供。每次尝试提供商推理请求在连接前计入一次 `budget.model_turns`，包括失败或中止的尝试；默认上限为 128。执行前必须配置模型。

Windows 当前源码可在空文件策略下构造绝对路径的私有工作区；SDK 文件读取、列目录和写入仍未实现并保持失败关闭，共享文件根目录不受支持。尚未宣称原生 Windows 验证。Windows hello 和 operation-ready 握手各最多五秒，且均受原调用期限限制；套接字 I/O 等待每片最多 0.1 秒，在片间检查取消。只读启动 SQLite 的 busy timeout 为 0.05 秒。这些限制不约束任意文件系统 I/O、自定义回调、后续完整 SDK 授权，也不保证整个启动或返回延迟。guard 清理等待为五秒，宿主等待 guard 为八秒；清理不能解决未知业务结果。

当前源码实现了宿主授权的原生工具；现有原生证据仅限 Linux。`OpenCodeAdapter(allow_shell=False, mcp_servers=None, host_tools_revision=None)` 默认关闭 shell，且不配置外部 MCP 服务。Agent 还须分别声明 `tools.shell: true` 或在 `tools.mcp` 中列出精确服务名；超出宿主授权的请求在准入前被拒绝。宿主启用任一能力时必须提供非空 `host_tools_revision`。本地 MCP 条目须为 `type: local`，包含非空 `command` 参数列表，可选 `environment` 和 `timeout`（1–300000 毫秒）；服务名最多 64 个字符，以小写 ASCII 字母开头，只含小写字母和数字，不能是 `dispatcher`。不支持远程 MCP。仅授权可信命令和环境变量：它们作为原生宿主代码执行。

`tools.network` 默认为 `false`。在可信 Agent 配置中设为 `true` 会允许 OpenCode 的 `webfetch` 和 `websearch` 工具，不需要单独的 shell 或 MCP 授权。该设置控制这些工具的权限，不提供操作系统级网络隔离。

宿主必须将 `host_tools_revision` 作为不可变的不透明标识，并在命令、环境变量、授权、模型推理档位选项或本地模型可用性发生变化时更换。SDK 将该值写入冻结配置和计划；重新打开未完成计划时版本不符会被拒绝，运行中版本漂移也会被拒绝。SDK 不验证版本值是否对应实际授权内容；对不同内容复用同一版本会破坏该保护。Shell 和本地 MCP 不受 SDK 文件工具路径授权限制，也不构成沙箱。子进程清理需要对应原生 guard 的清理证据；清理回执本身不能证明模型结果。候选 16 在 Linux x64／Python 3.12.3／OpenCode 1.18.32 上分别通过正常完成与取消场景：真实模型执行授权 shell 和本地 MCP，记录后代进程存活，再用准确认证 guard 回执确认清理。正常 effect 提交且必需产物匹配；取消后的模型 effect 仍为 indeterminate，调用保持 recovery_required，清理不解决该未知业务结果。其他平台及更完整的能力故障场景尚未验收。

只读共享输入同时需要绝对路径 `files.shared_read` 声明和宿主上限：`AgentApp(..., shared_roots=["/srv/agent-inputs"])`，或重复指定 `serve --shared-root /srv/agent-inputs`。宿主根目录列表默认为空，不能包含文件系统根目录、Agent 状态目录或与其重叠的路径，路径各层均拒绝符号链接。`file_read`、`file_list` 和文件产物提交使用相同授权，`file_write` 不能写共享路径。宿主须保护根目录及其祖先不被替换，并把无关凭据放在授权目录之外。候选 15 已在 Linux x86_64 上通过真实 OpenCode 读取、列目录、拒绝写入及下游原文件快照消费。可写工作区采用下面单独的宿主所有权机制，最终候选的完整验收尚未完成。

当前源码支持显式授予可写工作区：`AgentApp(..., workspace_roots=["/srv/work"], workspace_registry="/srv/agent-workspace-registry")`；CLI 对应重复的 `serve --workspace-root DIR` 和 `--workspace-registry DIR`。两项默认均不授予访问权。注册表目录必须预先存在、权限为 `0700`，位于 Agent 状态目录和所有可写根目录之外。所有使用同一根目录的合作宿主必须使用同一个受保护、稳定的注册表和无别名路径。根目录必须真实存在、为规范绝对目录路径，不含符号链接，不能互相重叠，也不能与状态目录或注册表重叠。宿主须防止根目录及其祖先被不可信写入者替换，保护注册表不被修改。建议锁不约束不合作的进程或原生代码。

`workspace.mode` 默认仍为 `private`，`path: null`、`shared: []`。`persistent` 需要在宿主根目录下指定绝对 `workspace.path`；相对 `files.read/write` 声明以此为根，内容在调用和宿主重开后保留。`shared` 保持 `path: null`，在 `workspace.shared` 列出绝对目录；主工作区仍私有，共享文件还需单独配置绝对 `files.read` 或 `files.write` 授权。相对授权只适用于主工作区，`files.shared_read` 始终只允许读取。SDK 保守地独占整个包含这些路径的宿主根目录，包括兄弟子目录和选择此目录的只读调用。动态子调用不能选择祖先仍持有的根目录，准入在创建 effect 前返回 `agent_workspace_ancestor_conflict`；顺序执行的下游角色可以在前一个调用释放后使用该根目录。

目录所有权在运行时 effect 和适配器启动前持久预留，在 goal 各轮和技术重试之间保留，沿用原期限。只有本地辅助资源静止、原始 effect／原生清理证明准确时才释放。进程死亡或期限到期不会清除未知所有者；只有原状态目录的宿主持有其独占宿主锁时，才能凭准确清理证据恢复释放，其他状态目录无权代为恢复。冻结计划记录准确宿主根目录和注册表，未完成计划不接受变更后重开。非私有工作区目前拒绝 shell 和外部 MCP 工具，因为文件工具授权无法保护注册表免受这些工具访问。候选 24 在 Linux x64／Python 3.12.3 使用安装包适配器启动 OpenCode 1.18.32 通过七项检查：持久写入、重开和稳定重放、共享写入、越界及状态目录写入拒绝、宿主刻意修改文件后下游仍消费原产物、原预算和准确原生清理。源码 SDK 集成也通过取消后未知所有权保留及祖先目录冲突测试。这不证明原生崩溃恢复、并发宿主排他或其他平台。候选 47 已完成 Linux x64 Python 3.12 安装包全量回归但有跳过；Windows 专项、其他平台和最终验收仍未完成。

SDK 文件工具检查声明的路径权限；这不构成操作系统级进程隔离。当前文件后端要求 Linux x86-64 或 ARM64 且系统支持 `openat2`。尚未提供原生 strict 强隔离后端，也未完成真实强隔离验收。当前源码还实现了 Windows 宿主锁和 Job Object 原生 guard，但尚未在原生 Windows 上验证；本页不宣称跨平台验收通过。

## 自动依赖图

宿主调用一个无 Agent 依赖的根角色后，系统在接纳前冻结可通过依赖或输入引用到达的 `inputs_ready` 角色。所选角色的所有依赖都必须在同一个根图中；需要另一个独立入口的混合入口图会在接纳前拒绝。当前每个角色在第 0 轮执行一次。

将下面的图配置保存为 `graph-agents.yaml`：

```yaml
schema_version: 1
defaults:
  runtime:
    model: openai/YOUR_MODEL_ID
agents:
  seed: {}
  writer:
    inputs:
      task: {ref: seed.output}
      instruction: "Publish your answer as the declared answer artifact."
    output:
      declared:
        answer: {}
      required: [answer]
  reviewer:
    inputs:
      task: {ref: seed.output}
  consumer:
    inputs:
      sources:
        - {ref: writer.artifacts.answer}
        - {ref: reviewer.output}
```

writer 必须通过 SDK 的 `artifact_publish` 工具发布已声明的 `answer`。consumer 等待两个生产者成功且所需成员存在后启动。显式 `{ref: ...}` 可嵌套在映射和列表中；普通字符串作为数据。引用按当前 run、problem 和 round 匹配，记录确切的生产者 invocation 和成员，不使用全局最新结果，匹配歧义会被拒绝。上游失败或所需成员缺失会使受影响节点失败。

```python
from dispatcher_sdk.agents import AgentApp, ApplicationSpec

spec = ApplicationSpec.from_yaml("graph-agents.yaml")
with AgentApp(spec, state_dir="./agent-state") as app:
    root = app.seed("Prepare a response to the task.")
    print(root.wait(timeout=120))       # root output only
    print(root.run.wait(timeout=300))   # waits for the graph; returns root output
    for invocation in root.run.invocations:
        print(invocation.snapshot)     # includes exact producer bindings
    print(root.run.usage)              # agent calls and model turns
```

`Invocation.wait()` 只等待该调用；`AgentRun.wait()` 等待整个图，成功时返回根输出，图失败、取消、需要恢复或超时则抛出异常。`AgentRun.invocations` 返回调用句柄，`AgentRun.usage` 返回 run 级 Agent 调用和模型轮次用量。等待超时不会延长预算。YAML 为可选依赖，也可通过 Python 构造配置。

调用者等待准入将 `wait(timeout)` 的原绝对截止时间传给应用锁、Kernel 控制／读取锁及 AgentStore 写锁／提交竞争。SQLite 明确确认 BUSY 且原事务仍有效时，只重试同一事务的提交，不重放事务内容。到期后回滚已确认未提交的事务；提交结果不明时保留恢复围栏。这些约束限于准入和提交前检查，不是系统调用抢占，也不代表所有存储与协调路径都已验证完整等待期限。等待超时不会取消或重新提交执行。 原调用者期限也传入 Orchestrator 连接配置、写事务准入和已确认未提交的 BUSY 提交重试，以及 AgentStore 连接配置竞争；整个等待路径仍在验证。

第三个隔离 wheel 候选在 Linux x86_64、Python 3.12 和 OpenCode 1.18.32 上报告 G02–G04 通过。真实 `seed → fast + slow → consumer` 运行中，宿主闸门阻塞 slow 时 consumer 尚未启动；放行后 consumer 读取 `FAST_NATIVE` 文件快照和 `SLOW_NATIVE` 产物，并发布 `FAST_NATIVE|SLOW_NATIVE`。四次调用属于同一个 SDK Run，计入 4 次 Agent 调用和 15 次推理请求。相同稳定 ID 重放没有新增执行，不同内容的重放被拒绝。文件工具诊断记录了失败，但未保留请求路径，不能独立对应路径穿越和符号链接两项拒绝。在直接调用文件工具的根目录替换竞争中，62 次替换期间的 500 次操作均失败关闭，外部文件保持不变；允许写入的正例由其他模型调用证明。此候选仅覆盖其记录的场景；后续证据及当前验收限制见[验收记录](../docs/SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md)。

隔离 wheel 候选 05 的验证器在 Linux x86_64、Python 3.12.3 和 OpenCode 1.18.32 上报告 G01、G02、G03、G04、G08、G11 和 G13 通过。G01 是配置检查；G02、G03、G04、G08 和 G11 使用真实模型。历史 G03 报告未保留被拒绝的请求路径，G04 未证明依赖事件重复投递；两者都不能单独证明当前完整验收通过。G13 仅覆盖能力合同和拒绝：尚无原生 strict 后端，也未验收真实隔离。准入原语与 controller 在打包之后加入，不构成该候选或 G07、G17 的验收证据。后续证据与剩余限制见[验收记录](../docs/SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md)。

## 当前源码中的 Agent 调用与请求范围

声明的访问权限启用协作时，当前源码使用按需创建的 SDK controller，并提供 `agent_call`、`agent_send`、`agent_wait` 和 `agent_context`。`agent_call` 与 `agent_send` 只接受 `agent`、`input` 和稳定的 `request_id`；该 ID 按调用方 invocation 分域。同 ID、同输入返回同一个子调用，输入改变则拒绝。`agent_call` 等待结果；`agent_send` 保留原 Run 和预算。`agent_wait` 接受 invocation ID，只能等待同一 Run 内已授权的调用。`agent_context({})` 返回由 SDK 绑定的自身角色、invocation、Run、problem、round、depth、tags 和状态，额外参数会被拒绝。调用方身份由 SDK 提供，不由工具参数指定。

授权配置在**目标角色**上：`access.invoke` 和 `access.send` 列出允许的调用方角色或显式 `*`。调用方隐含获得其调用结果的读取权；`access.read_artifacts` 可授权其他已声明角色等待和读取该目标结果，各项授权相互独立。普通且未经恢复的 SDK 接纳效果完成后，才使用实际 controller lease 和调用方派生预算。controller 的 Kernel 父级与逻辑 Agent 父级是不同身份。所有祖先的调用和模型轮次配额及深度限制沿调用链只能收紧，子调用不会重置预算。取消精确作用于逻辑子树，外部 SDK 撤销也会投射到该子树。

等待的 call 让出活动执行槽，同时保留 session 和内存预留。活动准入上限适用于全部模型执行，包括配置更新前后，默认 4；宿主另有固定的 64 个 SDK 子任务等待槽，属于技术限制。资源等待环返回 `agent_capacity_deadlock`，直接等待环返回 `agent_wait_cycle`。当前源码在进程内准入池执行 `concurrency.agent` 以及声明的 `resources.memory` 容量和每角色预留；内存准入默认关闭。等待的父调用保留其预留；如果等待链中保留的资源使子调用不可能准入，等待返回 `agent_memory_deadlock`，已接纳的子调用继续排队，直到父调用实际清理完成。修改宿主内存容量或角色上限需要关闭并重新打开宿主。持久资源所有权账本会恢复先前清理未知的全部预留，包括已关闭计划；限制匹配时排队工作可以重新打开，不兼容的原始上限仍会被拒绝。确认对应原生清理且本地工具、代理、观察器和已注册工作线程均停止后才释放容量；延迟清理可释放容量，但业务结果仍可能未知。这些源码控制不构成 G14、G16 或 G17 验收。动态分组、显式返工、服务、CLI 操作和监督尚未完成完整验收。候选 07 的原生 G07 已通过，但不能据此推定 G14、G16 或 G17 通过。

候选 07 原生 G02、G07 通过：一个 SDK Run 中三次模型调用完成 call/send/wait 和稳定重放，产物为 `CALL_NATIVE|SEND_NATIVE`，并核对原始权限及等待环错误、controller lease 和限制与调用方接纳效果。该候选包含资源接线，早于实验性调用组源码。候选 06 的 G07 因额外引号导致产物精确值不匹配而失败，保留失败记录。范围见验收记录。

当前源码提供实验性的 `agent_group_open`、`agent_group_send`、`agent_group_close`、`agent_group_wait`、`agent_group_call` 和 `agent_group_rework`，并检查 SDK 回执、记录有序精确成员及消费者绑定。显式返工打开下一轮调用组并冻结先前反馈。下一次审查使用相同的冻结 reviewer 角色和逻辑 reviewer ID，但创建新的 invocation 和原生 session；这不证明原生 session 连续。允许等待空组，空组消费者和返工会被拒绝；新增迟到成员或第二个后继在创建 SDK effect 前被拒绝。使用合成适配器的 SDK 集成、生命周期、权限和返工测试已通过；候选 08 的 G05、G06 原生测试在第二次 reviewer 执行时达到原始 600 秒期限并失败；候选 09 的全部工作流调用及反馈、绑定检查成功，但未观察到 coder 适配器重叠，G05/G06 整体仍失败；候选 07 早于调用组源码。

`agent_rework(group_id, review_invocation_id, member_invocation_id, request_id)` 使用已完成 reviewer 冻结配置中的 `recovery.rework` 目标。调用组所有者必须指定已关闭源组中一个准确、成功且角色匹配的成员；目标必须是无待绑定输入的 task，并通过 `access.send` 单独授权所有者。工具返回 `{group_id, invocation_id}`，表示包含该成员的开放后继组；新轮次冻结其原输入及准确版本的审查反馈，由调用者显式关闭组并发起下一轮审查。null 不授权此路由。稳定请求重放保持同组同子调用，也支持在两个独立 SDK effect 之间中断后的原身份续接；成员或内容变化报冲突。提交不明仍保持未知，不推断回滚或自动重做业务。普通分组 API 保留原请求命名空间。认证 loopback 运行时集成及候选 24 的安装包路由测试已通过。候选 33 在 Linux x64 通过真实 OpenCode 路由场景，核对了指定成员的反馈及 reviewer 实际消费；当前候选验收仍未完成。

## 实验性任务实例与会话

任务的 `instance`、`session` 或 `mailbox` 使用非默认设置时，宿主提交的根调用和 Agent 创建的节点都使用任务实例注册表。默认任务行为仍按每次调用隔离。`instance.mode: per_task` 为每次调用创建新实例；`fixed` 在角色及冻结配置代次内使用同一实例；`keyed` 使用 `instance.key` 指定的输入顶层非空字段精确选择实例。每次配置切换都创建新代次，包括 A → B → A；已接纳调用保留原绑定。

实例内的 `session.mode: problem` 按问题分域，`new` 为每次调用创建会话，`keyed` 使用 `session.key` 指定的输入字段或宿主传入的 `session_key`；两者同时提供时必须一致。会话属于实例：每次创建的 `per_task` 实例之间无法通过 keyed 会话续接，跨调用续接需要 fixed 或 keyed 实例。fixed 和 keyed 实例的各会话共享该实例的私有工作区，原生运行时状态则按会话范围分别保存。同一实例的所有会话始终只有一个写入者；不同 keyed 实例可以并行。

非 null 的 `instance.key` 要求 `instance.mode: keyed`；任务的非 null `session.key` 要求 `session.mode: keyed`。其他组合在准入时被拒绝。

任务邮箱支持 `queue`、`reject`、`replace_pending` 和 `cancel_and_replace`。根调用及节点的绑定随接纳持久化。子调用只有在原始普通 SDK 准入得到验证后才能替换待处理工作或取消当前写入者；准入不明时保守阻塞。FIFO 等待和超时继续使用原 Run、截止时间和预算，不会隐式延长。同实例同步递归等待会被拒绝；异步发送可排队，直到当前写入者完成且确认清理。即使已确认原生进程清理，效果结果未知仍会使实例保持隔离。

`Invocation.snapshot["instance"]` 返回任务或显式服务实例绑定，否则为 `None`；`agent_context` 返回绑定的 `instance_id` 和 `session_scope_id`。服务实例行为见下文；持久和可写共享工作区的支持边界见前文。候选 17 已通过真实 OpenCode 的固定实例 A/B/A 会话身份、FIFO、工作区及重启路径，以及按键实例配合新会话的独立执行。仅在首轮对话给出的随机挑战，已由第三次调用及宿主重开后的第四次调用实际回忆；观察到的 SDK 工作区文件调用及声明产物均未包含该挑战。安装包聚合 SDK 测试出现过一项重放错误，后续三项定向诊断全部通过，但尚未确认旧错误根因；完整回归和 G18 验收仍待完成。

## 实验性服务

宿主提交的服务根请求支持 `problem`（默认）、`keyed` 和 `new` 会话。前两者需要非空 `session_key`，可由调用传入，或从 `session.key` 指定的输入顶层字段取值；新请求同时提供两者时，值必须一致。`new` 会话拒绝宿主传入的 key。`trigger.mode: message` 仅对服务受支持。Agent 工具嵌套调用服务目前返回 `agent_service_session_required`。

服务使用 Agent 所有的 schema 4，每个角色有稳定服务 ID。每次已接纳配置切换递增角色代次，包括 A → B → A；稳定请求重放保留原配置、实例／会话绑定、期限和预算，每个请求仍有独立的有限 SDK Run。默认 `instance.mode: per_task` 保留已有按服务会话隔离的行为与目录。显式 `fixed` 在角色及配置代次内使用同一个可写实例；`keyed` 从 `instance.key` 指定的输入顶层非空字符串选择实例。同一实例的各会话共享私有工作区，按实例级 FIFO 保持一个写入者；原生对话 ID 和运行时状态仍按会话隔离。不同 keyed 实例可以独立执行。`Invocation.snapshot["instance"]` 返回显式服务绑定，包括 `instance_owner`、`instance_quarantined`；默认服务会话仍返回 `None`。`agent_context` 返回绑定的实例及会话 ID。

邮箱容量及替换仍按会话计算；`cancel_and_replace` 仅取消同一会话的所有者和待处理消息，不会取消正在拥有共享实例的其他会话。stop/resume 和控制代次作用于整个角色的全部实例及配置代次。明确完成须核对准确 SDK execution／effect、本地及持久资源清理后才释放；业务效果不明会隔离整个实例，并跨重开保留。定时／状态触发支持默认或 fixed 服务实例；keyed 实例需要显式提交带实例键的输入。源码 SDK 集成覆盖 fixed/keyed、未知所有权保留及存活资源清理。候选 25 在 Linux x64／Python 3.12.3／OpenCode 1.18.32 通过五项原生 fixed 实例检查：排队时无执行或消耗、后继进入前已有准确前驱清理和 SDK 成功 finish、会话共享工作区但原生身份隔离、关闭重开后准确重放不新增执行或消耗。三个实际调用对应三个原预算有限 Run，重开后会话 A 续接。另一个候选 25 keyed 切片通过六项原生检查：X 各会话串行共享工作区，X 在入口受控暂停时 Y 独立完成，四个有限 Run 经重开保持准确重放与会话续接。两份服务脚本当时未检查 SDK envelope 的绝对截止；另一返工验证发现约 74 微秒的期限延后，仍在修复，服务结果不证明该预算边界、对话回忆、提供商并发、进程崩溃恢复或整个 Goal；候选 25 安装包另通过服务实例、显式升级、goal、任务实例和工作区集成 62 项，无跳过；完整回归及平台矩阵仍待完成。

旧服务 schema 2、3 在宿主初始化写入前被拒绝。先停止宿主，再显式调用 `upgrade_service_store(state_dir, from_version=2)`（或 `3`），或执行 `dispatcher-agents upgrade-service-store --state-dir DIR --from-version 3`。该 API 取得相同独占宿主锁，在一个事务中升级 Agent 控制 sidecar；保留原服务身份、停止及控制状态、会话／原生目录、队列绑定、所有者及隔离标记，旧会话不会新增实例绑定。不会修改 SDK 存储或重置预算。不完整／未知 schema 拒绝升级，活动宿主会阻止升级。结构升级不代表未知执行可以续跑。

依赖事件存储也需要对旧控制存储显式升级：确认宿主已停止后，执行 `dispatcher-agents upgrade-dependency-store --state-dir DIR --from-version 1`。旧计划保持扫描方式，新计划使用事件投递；升级不会修改 SDK 存储。可用 `dispatcher-agents inspect-dependency-store --state-dir DIR` 查看模式数量、未封口事件及未确认记录；它还检查部分结构一致性，结果仅是一个只读快照，不证明宿主已停止或全部数据健康。命令要求宿主私有状态目录；当前源码的旧计划实际 SDK 执行、完整升级兼容及跨平台行为仍待验收。正常关闭等待已进入的投递，未领取记录保留供下次启动恢复，确认投递也不等于 Agent 已执行成功。

宿主可使用 `app.service_status(name)`、`app.stop_service(name, mode="drain" | "cancel")` 和 `app.resume_service(name)`。drain 停止新接纳并允许已接纳工作完成；cancel 持久记录取消。当前源码提供前台 CLI 服务宿主。候选 10 的真实 G10 场景通过，覆盖 CLI／宿主、同 key 原生会话延续、独立 Run、重启、所观察崩溃窗口中的队列恢复和跨 Run 取消。候选 17 的五个真实 G09 邮箱场景全部通过：两个并发宿主调用者及两条待处理消息的 FIFO、队满、拒绝、替换未开始请求、启动前取消替换，以及发送后未知隔离。逐一核对普通 runtime effect、最终 SDK 回执和认证原生清理的精确调用身份；本地清理不解除未知业务结果。候选 10 的 G10 早于后续 guard、监督及保留服务停止修复，最终候选 G10 和 G18 验收仍待完成。

## Goal 完成模式

将 `completion.mode` 设为 `goal`，并将 `completion.validator` 设为宿主注册的名称。宿主可通过 `AgentApp(..., validators={"check": check})` 提供可信 callable，也可先向 `ValidatorRegistry` 注册再传入。配置只选择名称，不执行表达式。callable 接收 `ValidationContext`，其中包含执行身份以及响应和产物的副本，并返回 `ValidationResult("passed")`、`ValidationResult("continue", feedback)` 或 `ValidationResult("blocked", feedback)`；反馈必须是 JSON。

`continue` 会在同一个 invocation、session、运行时状态、截止时间、冻结配置和根预算内，以验证反馈继续下一步。`passed` 且必需产物齐全时才成功；产物缺失时继续执行。每一步使用新的工具端点。Goal 产物按宿主步骤保留不可变版本历史；`invocation.artifact_history(name)` 返回已提交的版本、宿主步骤和值，也可检查未完成 goal 的历史。下游产物绑定记录成功生产者的最终版本。

`blocked` 映射为失败的 Agent invocation，outcome 为 `blocked`、failure code 为 `goal_blocked`，不会满足下游成功依赖。验证器异常和无效结果会产生独立、安全的失败代码，不暴露异常详情。response 模式配置 validator 会被拒绝；goal 配置的验证器未注册或适配器未声明同 session 恢复能力时，接纳会在执行前拒绝。未知执行效果不会盲目重放。候选 05 的 G08 验证了同 session 从 continue 到 passed 和不可变步骤产物；blocked 和验证器异常场景失败，未产生下游成功。

## 知识库与配置版本

`AgentApp` 提供宿主管理的 `knowledge_store`（`KnowledgeStore`），并向各次调用提供 `knowledge_read` 和 `knowledge_write` 工具。`knowledge.read` 和 `knowledge.write` 分别配置精确的命名空间名称列表；写权限不包含读权限，读权限也不包含写权限。名称是 ASCII 标识符，不是路径或通配符。工具使用调用冻结的授权和当前有效执行权限；宿主通过 `app.knowledge_store` 执行管理操作，不受这些调用级授权约束。

知识值为 JSON。`read(name)` 返回最新的 `{name, version, value}`，`read(name, version)` 读取不可变的历史版本。`commit(name, value, expected_version)` 使用比较并交换：首次创建时传 `None`，更新时传精确的当前版本。版本冲突抛出 `KnowledgeConflictError`，不会覆盖历史；每个命名空间从版本 1 开始递增。读取工具接受 `name` 和可选 `version`，写入工具接受 `name`、`value` 和 `expected_version`。作用域授权及版本冲突以工具错误报告。绑定授权检查由 `ScopedKnowledge` 实现，可从 `dispatcher_sdk.agents.knowledge` 导入。

宿主取消和关闭会与知识操作接纳串行化。独立发起的 Kernel 撤销仍可能与已接纳的独立知识库提交发生竞争：取消或未知响应不能证明提交已回滚。请先检查持久化的命名空间版本和值，再决定后续操作，不要盲目重放写入。

`app.update_config(new_spec)` 为后续请求激活冻结配置版本，已有计划和提示内容保持不变。修改应用工作线程容量、内存容量或角色上限需要关闭并重新打开宿主，并受上述未完成计划限制。配置激活和每次新请求接纳都会捕获**所有**已声明角色的 `soul` 和 `prompt` 源内容，包括所选图之外的角色；任何已声明源缺失或无法读取都会导致新的激活或接纳失败。已有冻结请求的重放和恢复不依赖这些源文件继续存在。相对源路径以 `base_dir` 为基准。

新建的 Agent 及控制器 SDK 命令同时携带准确冻结的绝对 `deadline_at`，协调子调用继承自身冻结截止；排队、进入及重开不会把剩余时长换成更晚的 SDK 期限。旧实验候选包留下的相对超时未完成请求在调度前拒绝，保留原命令和回执；已关闭旧请求仅在公开 SDK 准确命令及终态核对后允许重放。AgentApp 之外普通旧 SDK 命令保持原相对超时行为。

## 完整默认值

历史 observation-reads 候选证据：安装包影响检查74项中69通过、3项等待错误、2项子进程测试导入失败。导入路径已修正，同一隔离安装包两项定向通过，但不覆盖整组失败。异常等待已保留关闭前线程证据，统一根因仍未证明。后续修复、当前证据及各包边界见[当前验收记录](../docs/SDK_0_8_0_CURRENT_ACCEPTANCE.md)。

`recovery.cancel_grace_seconds` 默认为 `2`，接受非负整数秒；`0` 表示立即调用 SDK 取消。显式取消后，仅准确匹配当前执行身份的本地处理线程可在该时间内结算，且不超过原请求期限。工具及新的模型／原生进程启动仍被拒绝。首次宿主观察开始计时，轮询不重置；所有者缺失或变化、重启、权限撤销、宿主关闭及原期限到期均不享有该等待。线程正常返回后 Agent 仍投影为取消；效果或清理未知仍须恢复／隔离，等待本身不构成服务复用证明。

`recovery.technical_retries` 默认为 `0`，最多允许 `16` 次额外尝试，所有 goal 轮次共用计数。OpenCode 重试必须持久记录当前启动前尝试的准确 `not_launched` 证明。创建运行时私有工作目录时遇到暂时性错误，且上述证明已确认的，可以重试。控制通道获取失败只有在清理已被证明时才可重试：套接字工厂可能获取资源后抛错，却未返回句柄。此类获取保持未知并阻止重试，即使错误属于暂时性；错误码本身不足以证明清理。宿主重核原始 SDK 租约／effect 身份、期限、共享及祖先模型轮次预算，并确认代理、工具和工作线程已清理。重试更换工具访问凭证，继续使用同一 invocation、SDK effect、会话、工作区及冻结预算，不增加 Agent 调用计数；成功元数据记录 `technical_retries`。证明充分但重试耗尽或错误不属暂时性时按失败结束；证明缺失、陈旧或清理不明仍保留未知。HTTP／提供商错误、已经尝试创建进程、guard 启动失败、超时及可能已发出的请求均不重试；崩溃后也不盲目续跑循环。适配器需声明 `technical_retries: verified_native_prelaunch`，声明本身不代替账本证明。`recovery.rework` 默认为 null；配置目标只供下面的显式 `agent_rework` 路由使用，普通 reviewer 拒绝不会自动触发返工。候选 20 曾在 Linux x64／Python 3.12.3／OpenCode 1.18.32 上通过安装包真实启动前重试；该结果属于历史候选，不能证明当前重试行为或跨平台支持。

`runtime.fallbacks` 默认为 `[]`，按顺序声明明确的 `provider/model`。当前源码只在受信宿主于任何代理或原生进程启动前声明前面的模型本地不可用时选择备选：`OpenCodeAdapter(..., unavailable_models=["provider/primary"], host_tools_revision="runtime-v1", provider_config=...)`，CLI 可重复传入 `serve --unavailable-model provider/primary`。主模型与全部备选必须在私有宿主模型目录中明确声明，并有非空、不可变的宿主版本；选择前检查所有候选的提供商、凭据和推理档位，配置错误或缺凭据不算不可用。在冻结配置与同一宿主版本下选择第一个本地可用模型，成功元数据记录 `selected_model`，原请求保留主模型与备选声明。可用性变化必须更换宿主版本。HTTP 错误、超时、进程失败或已提交结果不明均不切换模型；不会探测提供商健康。候选 20 在 Linux x64／Python 3.12.3／OpenCode 1.18.32 上通过安装包测试与两次真实模型调用：宿主声明夹具主模型不可用，实际选择备选；宿主重开保持同键会话，稳定重放没有新增提供商请求，两次普通 SDK effect 与准确原生清理均通过。该结果仅证明本地选择，不代表自动检测提供商故障或跨平台验收。

`runtime.reasoning` 默认为 null，用于选择宿主模型配置中明确授权的档位名。当前 OpenAI-compatible 后端只接受 `{reasoningEffort: low|medium|high}`；未知选项、Anthropic 档位及含点的 provider ID 在启动前拒绝。宿主在私有 `provider_config` 的 `models.MODEL.variants.NAME` 中定义档位，并提供非空、不可变的 `host_tools_revision`；该版本也覆盖模型选项。CLI 通过 `--host-tools-revision VERSION` 配合私有提供商配置传入。候选 19 已在 Linux x64／Python 3.12.3／OpenCode 1.18.32 验证真实请求传递 `reasoningEffort: low`，并核对普通 SDK 完成及准确认证清理。medium/high 尚未分别实测，传参也不证明提供商内部如何推理。

自动触发运行于前台宿主。新增默认值 `trigger.interval_seconds: null` 和 `trigger.session_key: null`。定时模式要求正整数间隔，首次激活等待下一个 UTC Unix 时间边界，停机或暂停期间错过的时间槽合并为最新一个。状态模式使用 `[source.succeeded]` 等精确选择器，只观察以该角色为入口的有限根 SDK Run 的 succeeded、failed、cancelled 终态，并核对原始公开完成回执；不把任意子调用状态当成根 Run 事件。新代次排除此前已完成的历史，激活前已运行、之后完成的来源仍可触发，重启重复扫描不重复创建调用。

每个事件将根意图及稳定事件绑定原子写入 Agent 控制存储，再通过 SDK 提交；它有独立 Run 和冻结的原预算。状态触发环和无法取得输入键的任务目标会明确拒绝。持续会话服务要求显式 `trigger.session_key`，new 会话拒绝 key。`app.triggers_status()` 及客户端同名 API 返回暂停状态、目标和最近 100 个事件的调用身份，可通过普通调用 API 查询结果。`pause_triggers()` 和 `resume_triggers()` 管理准入；CLI 为 `status|stop|resume --triggers`，与 `--agent` 互斥。停止整个宿主会持久暂停自动准入，重启不会自动解除；已接纳工作保留原期限，暂停后恢复已有冻结命令不要求未来触发的提示词源仍存在。详细语义见[指南](../docs/AGENT_CONTROL.md)。候选 19 的真实 OpenCode 状态、定时场景分别通过 14、13 项检查，覆盖准确来源、原预算、去重、暂停后重开和认证清理；完整 G18 回归及平台覆盖仍待完成。

以下是 schema 1 中每个 Agent 的完整默认值；解析某字段并不代表运行时支持其所有取值。

```json
{
  "tags": [],
  "soul": null,
  "prompt": null,
  "runtime": {
    "name": "opencode",
    "model": null,
    "reasoning": null,
    "fallbacks": []
  },
  "lifetime": "task",
  "instance": {
    "mode": "per_task",
    "key": null
  },
  "trigger": {
    "mode": "inputs_ready",
    "events": [],
    "interval_seconds": null,
    "session_key": null
  },
  "session": {
    "mode": "problem",
    "key": null
  },
  "mailbox": {
    "capacity": 100,
    "policy": "queue"
  },
  "concurrency": {
    "application": 4,
    "agent": null,
    "session": 1
  },
  "resources": {
    "memory": {
      "capacity_bytes": null,
      "reservation_bytes": null
    }
  },
  "access": {
    "invoke": [],
    "send": [],
    "read_artifacts": [],
    "cancel": [],
    "resume": []
  },
  "files": {
    "mode": "tools",
    "read": [],
    "write": [],
    "shared_read": []
  },
  "tools": {
    "shell": false,
    "mcp": [],
    "network": false
  },
  "workspace": {
    "mode": "private",
    "path": null,
    "shared": []
  },
  "completion": {
    "mode": "response",
    "validator": null
  },
  "output": {
    "required": [],
    "declared": {}
  },
  "budget": {
    "seconds": 3600,
    "agent_calls": 64,
    "model_turns": 128,
    "tokens": null,
    "call_depth": 8
  },
  "recovery": {
    "technical_retries": 0,
    "cancel_grace_seconds": 2,
    "rework": null
  },
  "supervision": {
    "enabled": false,
    "interval_seconds": null,
    "metrics": [],
    "diagnostic_agent": null,
    "actions": []
  },
  "knowledge": {
    "read": [],
    "write": []
  },
  "service_stop": {
    "mode": "drain"
  },
  "dependencies": [],
  "inputs": {}
}
```

Linux subreaper guard 已通过进程和合成协议测试，候选 11 的真实 OpenCode G02 及对应 SDK 代次的认证清理回读通过；更完整的 guard 故障验收仍未完成。其 `ECHILD` 回执证明进程清理，不证明模型效果结果或 strict 隔离。源码监督账本和诊断准入已通过使用合成适配器的真实 SDK 测试。候选 34 在 Linux x64 通过有界原生监督触发、过期、关闭及停止场景；当前候选完整 G17 和其他平台仍未验收。


候选 15 的原生 G05/G06 通过：每轮两个 coder 实际重叠，显式返工后由相同逻辑 reviewer 消费新结果，绑定和原预算准确。未关闭组负例使用真实返回 ID 并命中拒绝。此前失败候选保留在验收索引中；该证据不表示整个 Goal 完成。

## Agent 控制权限

`access.cancel`、`access.resume` 是目标角色接收的授权，默认都为空。`agent_cancel` 只接受 `invocation_id`、`request_id`，仅能请求取消同一 Run、根请求和问题内获授权的严格后代；拒绝自身、祖先、兄弟及其他 Run。`agent_resume` 只接受 `agent`、`request_id`，用于全局重新开放已建立身份的服务角色接纳；调用方冻结计划和当前宿主配置必须同时授权。它不清除已取消调用或被隔离的会话。

调用身份和预算绑定实际 SDK 上下文，只有原始普通 `agent.control.admission` effect 的精确已提交回执才能授权投影。applied 表示请求已投影，不表示进程清理成功。相同请求 ID 可重放，改变操作或目标会冲突；重放已应用的 resume 不会解除之后的宿主 stop，需新的显式请求。当前服务 schema 为 4，旧 schema 2／3 须按前文在停止宿主后显式升级。重开仍检查原期限、lease/fence 和预算；SDK 撤销与 Agent 存储动作分属两个存储，不能承诺原子回滚已接纳命令。当前源码的真实 SDK／本地工具链定向测试通过。候选 23 在 Linux x64／Python 3.12.3 使用真实 OpenCode 1.18.32 通过 13 项检查：实际自身取消被拒且无 effect，服务 resume、介入宿主 stop 后的精确重放、新显式 resume、同键会话延续、三个独立 Run 的原预算不变，以及认证原生清理。它不证明原生后代取消、控制路径崩溃重开或完整 G16／G18 验收。


宿主通过 `app.revoke_permissions("worker", request_id="revoke-1", reason="宿主决定")` 撤销角色调用权，`app.permissions_status("worker")` 查询，`app.restore_permissions("worker", request_id="restore-1")` 恢复未来接纳；已认证的 `AgentClient` 提供相同方法。CLI 为 `revoke-permissions`、`permissions-status`、`restore-permissions`，均带 `--state-dir DIR --agent worker`；写入决定必须带 `--request-id`，撤销可带 `--reason`。这些是宿主管理入口，模型工具不能恢复自身权限。

默认未撤销、代次 `0`，调用仍须满足配置中的 incoming access 授权。撤销会持久拒绝该角色的新接纳，并取消各开放 Run 内该角色的未完成调用和委托后代，包括已完成父调用留下的存活子调用；保留既有完成结果及无关角色。调用状态的 `permission_revocation` 返回决定请求 ID、角色、代次与可选原因。SDK 取消、原生清理和业务结果分别保留，不确定效果仍不确定。恢复仅允许未来接纳，不复活已取消调用，不解除未知所有权、服务停止或触发器暂停。配置更新、服务 resume 和宿主重启均不清除决定。相同请求原样重放返回原回执，不把旧决定重新覆盖到新代次；异内容报冲突。管理决定 ID 在整个状态目录内唯一。角色及决定 ID 为最多 256 字符的非空字符串；可选原因最多 4096 字符且非空；拒绝 NUL。活动调用继续保留冻结配置和原预算。此入口撤销角色调用权，不逐项改写活动调用冻结的文件或工具授权。


### 安装包 CLI 生命周期验证

使用已安装候选包且包含可选 YAML 依赖的解释器运行 `python -I /absolute/path/scripts/verify_agent_cli_lifecycle.py --output /new/private/evidence-directory`。验证器实际启动空闲 `serve` 进程，核对有效配置、服务和触发器的准入控制、状态回读及宿主正常退出。此检查不提交模型任务，不证明跨 Run 会话续接。输出目录必须不存在；`report.json` 保留各命令结果及是否使用兜底清理。
