# LLM 接入：输出契约、校验与有预算返工

LLM 生成的产物需要应用宿主校验后才能参与业务放行。提示词应传达精确契约，
但提示词、模型提供方的结构化输出功能以及 Agent 自报的“Validated”都不能
替代宿主校验。SDK 不调用模型，也不生成提示词或解释应用产物。

下文用应用示例说明接入方式。其中的分类、错误码、预算和 gap 不属于 SDK
内置字段或状态，也不代表 SDK 提供自动修复能力。

## 1. 分开判断执行、结构和业务验收

| 判断 | 谁验证 | 通过意味着什么 |
| --- | --- | --- |
| 执行结果与 SDK 协议 | Kernel / Orchestrator | 执行及协议满足 SDK 规则；handler 正常返回可以产生 `succeeded` |
| 产物结构 | 应用宿主的权威校验器 | 必填字段、类型、枚举、版本及字段间约束合法 |
| 业务验收 | 应用策略与证据校验 | 证据符合当前输入与验收要求，阻断项已解决，允许下一步 |

handler 正常返回 `{"accepted": false}` 或 `{"error": "invalid output"}`
仍是返回业务数据；SDK 不会据此自动将执行判为失败。即使执行为 `succeeded`，
应用仍需验证产物结构和业务条件。通过 JSON 解析也不等于通过产物结构校验。

例如，某分析产物有 97 条候选的 `status` 是非法值 `confirmed_change`。
按契约修正为 `confirmed` 后，结构校验可能通过，但报告仍有 16 项未解决 gap。
这时仍不能派发迁移任务。格式修复不能删除 gap、降低证据要求或将它们改成已解决。

## 2. Agent 交接状态必须使用结构化枚举

上下游 Agent 交接时，状态必须放在约定的结构化字段中，并使用契约规定的
精确枚举值。自然语言段落不能作为状态载体、状态值或业务路由依据。
说明文字应放在独立的解释字段或报告段落中；下游不能从文字中猜测、提取或翻译
出一个状态，也不能将空格改成下划线来构造枚举。

例如，契约可以规定以下交接片段（仅展示状态与解释，不是完整产物）：

```json
{"status": "confirmed", "explanation": "已确认发生变化；证据见报告。"}
```

只写“已确认发生变化”或 “confirmed change” 的交接段落不构成合法状态；
`{"status": "confirmed_change"}` 也不合法。状态缺失、出现未声明值或说明与
结构化结论相矛盾时，宿主应拒绝放行并反馈诊断，不能由下游自行补全或默认成功。
下游只消费经过宿主校验、关联当前产物与 attempt 的结构化状态，并继续检查
业务放行条件。合法的 `confirmed` 只表达候选分类，不代表整个阶段已经通过验收。

结构化枚举消除交接状态的自然语言歧义，运行时校验则拦截违反约定的输出。

### 用同一份权威契约生成提示词和校验规则

将应用 schema 或契约模块纳入版本管理，由它生成提示词中的字段约束，
并用于宿主校验。避免分别手写提示词枚举和校验器枚举。每次执行应绑定具体的
应用契约版本或摘要；该身份独立于 SDK 的 `SCHEMA_VERSION`。

以下是应用契约模块的最小片段，只演示枚举约束，不能替代完整产物校验：

```python
import json

CONTRACT_VERSION = "analysis-output-v1"
CANDIDATE_STATUSES = (
    "import_only", "confirmed", "candidate", "false_positive", "unknown",
)

def valid_candidate_status(value):
    return isinstance(value, str) and value in CANDIDATE_STATUSES

status_instruction = (
    "每条 candidates[].status 必须且只能使用以下字符串之一："
    + json.dumps(CANDIDATE_STATUSES, ensure_ascii=False)
    + "。不得创造别名；confirmed_change 是非法值，confirmed 才是合法值。"
)
```

完整提示词还应从契约中提供：

- 输出文件或返回位置、JSON 顶层结构、必填字段、类型及是否允许额外字段。
- 每个枚举的精确字符串及含义；自然语言 “confirmed change” 只能解释含义，
  不能代替合法值 `confirmed`。
- 合法示例与典型非法示例，以及缺证据时应使用的状态和 gap 记录方式。
- 可用时给出应用自检入口、参数和失败反馈格式；入口应调用与宿主同源、同版本
  的校验代码。入口不可用时明确记录未执行自检，不能声称校验通过。

若模型提供方支持约束生成，应从同一契约派生输出 schema。宿主仍须独立验证
实际收到的完整产物，包括约束生成未覆盖的字段间关系和证据规则。
产物中的 `status_definitions`、模型自行编写的脚本或“校验通过”文本均不具有
修改契约的权限。宿主必须使用自己冻结的规则，不能按产物自带的允许值验证产物。

## 3. 让校验错误可以定位和修复

宿主先解析并校验完整产物，再执行业务验收。结构错误应提供字段路径、错误码、
实际值、期望类型或允许值，并关联产物身份及应用契约版本。例如：

```json
{
  "contract_version": "analysis-output-v1",
  "artifact_id": "analysis-attempt-0",
  "errors": [
    {
      "code": "invalid_enum",
      "path": "$.platform.candidates[0].status",
      "actual": "confirmed_change",
      "allowed": ["import_only", "confirmed", "candidate", "false_positive", "unknown"]
    }
  ],
  "errors_truncated": true
}
```

路径必须对应实际结构；保留阶段、Run/task/attempt、产物路径或摘要，方便定位
原始证据。能够继续检查时收集多处错误，并为反馈大小设置上限；有截断应明确
标记，不能让一条错误看起来像完整清单。解析失败则返回可用的行列和解析原因。

修复输出写入新的产物，保留原产物、诊断和两者关联。宿主重新校验新产物，
不能只检查先前失败的字段，也不能原地修改历史结果来制造成功记录。

## 4. 显式安排有预算的格式返工

`RetryPolicy.max_attempts` 管理同一执行命令的机械尝试次数，包含首次领取。
它不会把业务校验错误转成修复提示词，也不会自动安排业务返工。handler 可通过
`HandlerExecutionError(..., retryable=True)` 显式上报可重试执行错误，普通异常
默认按不可重试失败处理。即使这样上报校验错误，机械重试仍使用原命令，SDK
不会为它追加诊断或修改 payload。执行重试、结果投递重试和业务返工应分别计数。

应用应在派发前配置格式返工路由和有限预算，例如“首次生成后最多修复 2 次”，
并定义耗尽后的失败或人工处理路径。以下步骤由应用策略执行，SDK 不会自动安排：

1. 观察并确认当前 attempt 已结算，校验其产物，持久化失败分类和诊断。
2. 对可修复的结构错误检查格式预算；证据不足则进入独立的 gap 处理策略。
   若决定返工，保持 Run 为 `running`，不要先 `finish`。
3. 构造新命令，提供冻结契约、原产物引用和宿主诊断，要求修复结构并保留证据
   与未解决项。命令使用新的 `execution_id` 和 `idempotency_key`。
4. 通过 `apply_operations` 显式提交 `new_attempt` 和 `dispatch`，同时在
   `application_state` 中保存更新后的预算、诊断引用和原 attempt 关联。
   这使预算扣减与返工决定在同一 SDK 事务中提交；独立应用数据库另需 inbox/outbox。
5. 使用稳定命令身份处理响应丢失，原样重放请求，不重复扣预算。遇到
   `RevisionConflict` 则重新观察并重新决定，使用新的命令身份。
6. 收到修复产物后重新执行完整结构校验与业务验收；预算耗尽时按预定策略结算，
   不能靠增加执行次数或新建 Run 来无限延长返工预算。

`new_attempt` 只创建新的应用 attempt，还需要显式 `dispatch`。它要求旧 attempt
已结算，且 Run 仍为 `running`。已经 `finish` 的 Run 不能重新开启或追加返工；
若应用决定重新发起工作，应创建新的 Run，并保留原 Run、失败证据及预算关联。
存在未决外部副作用时，先遵循[恢复协议](SDK_RECOVERY.md)，不能以格式返工绕过它。

## 5. 格式通过后再决定业务路由

| 校验结果 | 应用动作 |
| --- | --- |
| 解析、类型、枚举或其他结构约束失败 | 有预算则反馈诊断并安排格式返工，否则失败或等待人工处理 |
| 结构通过，但存在阻断 gap | 保留 gap 与证据；按独立业务预算补证据、返工或等待人工处理 |
| 结构和业务验收均通过 | 检查当前 attempt、等待及其他放行条件，再显式派发后继任务 |

应用可以记录 `blocked / relevant_skill_gap` 等业务分类，但它们不是 SDK 的
Run 状态。若使用 SDK `wait` 记录等待，应用还必须阻止相应后继派发；`wait`
本身不会自动拦截 `dispatch`。准备 `finish` 时须先结算任务并释放等待。

接入验证至少应覆盖：合法枚举、非法别名、自定义 `status_definitions` 无法放宽
契约、格式修复后仍有 gap、返工预算耗尽，以及重放决定不会重复扣预算。
交接判断示例见[接入 FAQ](SDK_INTEGRATION_FAQ.md)，API 语义见 [SDK 指南](SDK.md)。
