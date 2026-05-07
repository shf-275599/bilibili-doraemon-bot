# Bilibili Agent 评论自动回复机器人实施计划

日期：2026-05-07
关联设计文档：`/home/shf/.config/opencode/docs/superpowers/specs/2026-05-07-bilibili-comment-bot-design.md`

## 1. 实施目标

基于已确认设计，按分阶段方式为当前 `bilibili-agent` 增加评论自动回复机器人能力。

本实施计划的目标不是直接覆盖全部能力，而是按以下顺序逐步落地：

1. 先完成最小可运行闭环。
2. 再扩展到更多评论来源。
3. 最后补齐稳定性与长期运行能力。

## 2. 实施原则

- 优先复用现有 `bilibili_wbi.py`、Cookies 路径和目录规范。
- 第一版优先 Python 实现主守护进程与核心模块。
- 所有状态文件放到 `/home/shf/.config/opencode/data/bilibili-bot/`。
- 外部模型优先采用 OpenAI-compatible Provider。
- 全程按保守风控策略实现。
- 每个阶段都要有可执行的手动 QA 和通过标准。

## 3. 分阶段实施总览

### Phase 1：最小可运行闭环

目标：只基于“别人回复我 / 评论我”的消息通知流，实现自动采集、去重、AI 生成、发送回复、基础退避。

交付结果：

- 守护进程可在本机长期前台运行。
- 能命中 `/x/msgfeed/reply` 新事件。
- 能对新评论生成回复并发送。
- 同一条评论不会重复回复。
- 主 Provider 失败时有明确 fallback 路径。

### Phase 2：扩展评论来源

目标：在 Phase 1 基础上，接入自己视频评论、自己动态评论、@我评论三类扫描型来源。

交付结果：

- 多 source 统一归一化。
- 多 source 去重一致。
- 来源间重复命中不会触发重复回复。

### Phase 3：稳定性与长期运行增强

目标：补齐 Cookie 自动刷新、熔断、限频、状态恢复和长期运行能力。

交付结果：

- Cookie 状态可自动检查。
- 连续失败自动退避和熔断。
- 重启后可恢复已处理状态。
- 长时间运行风险更低。

## 4. 详细任务拆解

## Phase 1 详细任务

### Task 1：创建目录与基础文件骨架

文件：

- `/home/shf/.config/opencode/scripts/bilibili bot/bilibili-comment-bot.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/bot_config.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/state_store.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/comment_normalizer.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/comment_sources.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/comment_filters.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/comment_dedup.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/reply_prompt.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/reply_providers.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/comment_sender.py`
- `/home/shf/.config/opencode/scripts/bilibili bot/rate_control.py`
- `/home/shf/.config/opencode/data/bilibili-bot/bot-config.toml`

产出要求：

- 每个文件只承载单一职责。
- `bilibili-comment-bot.py` 只做编排。
- 不提前引入 Phase 2 / Phase 3 的复杂逻辑。

QA：

- 所有文件可被 Python 正常导入。
- 配置文件可成功解析。

### Task 2：实现配置层与环境变量解析

目标：

- 解析 `bot-config.toml`。
- 读取环境变量中的 API Key / refresh token。
- 启动时检查必要配置是否存在。

关键点：

- 必填项缺失时，程序必须直接失败并给出可读错误。
- 不允许打印真实敏感凭据。

QA：

- 配置正确时启动成功。
- 缺少 `DEEPSEEK_API_KEY` 等关键变量时给出明确报错。

### Task 3：实现状态存储与历史去重

目标：

- 用 `processed-comments.jsonl` 记录已处理评论。
- 用 `reply-history.jsonl` 记录回复结果。
- 支持根据 `(business_type, oid, rpid)` 查询去重。

关键点：

- 区分“已看到但未回复成功”和“已成功回复”。
- 写入应尽量原子化，避免中途中断导致状态污染。

QA：

- 插入同一条评论两次，第二次被去重拦截。
- 重启程序后仍能识别历史已处理记录。

### Task 4：实现 `msgfeed` 来源采集

目标：

- 从 `/x/msgfeed/reply` 拉取消息通知流。
- 把响应归一化为统一 `CommentEvent`。

关键点：

- 正确映射 `rpid`、`oid`、业务类型、作者信息、评论内容。
- 兼容不同回复消息结构。

QA：

- 手动运行采集命令时，能输出归一化后的事件对象。
- 对空数据、异常结构、未登录情况有清晰报错。

### Task 5：实现基础过滤

目标：

- 跳过自己。
- 跳过空文本。
- 跳过纯表情 / 纯符号。
- 跳过黑名单用户。
- 跳过无意义超短评论。

QA：

- 构造多种事件输入，过滤结果符合预期。
- 过滤日志能说明“为什么跳过”。

### Task 6：实现 Prompt 构建与主 Provider 调用

目标：

- 实现 `OpenAICompatibleProvider`。
- 使用统一 prompt 生成回复。

关键点：

- 控制回复长度。
- 保持回复自然、友好、不灌水。
- 对 provider 超时、空响应、错误码做标准化返回。

QA：

- 对测试评论能生成回复。
- 当 provider 返回 401/429/5xx 时能得到结构化失败结果。

### Task 7：定义并接入 fallback provider

目标：

- 主 Provider 失败后，走本地 OpenCode / bilibili agent 模型能力。

关键点：

- 第一版先把 fallback 抽象接口做稳定。
- 具体调用链必须可观测且不会静默吞错。

QA：

- 人为让主 Provider 失败时，确认 fallback 被触发。
- fallback 失败时，也要返回明确失败状态。

### Task 8：实现评论发送器

目标：

- 封装 `/x/v2/reply/add`。
- 支持 `csrf`、WBI 参数、`root`、`parent`。

关键点：

- 先复用现有 WBI 能力，而不是重新散落实现。
- 统一返回：成功 / 可重试失败 / 不可重试失败。

QA：

- 手动调用发送器，成功发出一条测试回复。
- 对 `-111`、`-101`、频控错误码有正确分类。

### Task 9：实现基础频率控制与退避

目标：

- 每次发送前随机等待。
- 失败时指数退避。
- 连续失败达到阈值时暂时停止发送。

QA：

- 模拟失败后观察退避时间增长。
- 熔断期间不再继续高频发送。

### Task 10：实现主守护流程

目标：

- 按“采集 → 过滤 → 去重 → 生成 → 发送 → 落盘 → 等待”跑通完整闭环。

QA：

- 真实触发一条新评论事件。
- 观察机器人完成整条链路并写入历史。

## Phase 2 详细任务

### Task 11：接入自己视频评论来源

- 定义视频评论扫描 source。
- 明确视频列表来源。
- 统一归一化结构。

QA：

- 对自己视频下的新评论可成功采集。

### Task 12：接入自己动态评论来源

- 定义动态评论扫描 source。
- 建立与视频评论不同的业务类型映射。

QA：

- 对自己动态下的新评论可成功采集。

### Task 13：接入 @我评论来源

- 定义 @我 检索 source。
- 保留 `at_me=true` 标志进入 prompt。

QA：

- 对别人内容里 @我的评论能成功识别并进入同一流水线。

### Task 14：完善多 source 去重

- 避免多 source 重复命中同一条评论。
- 补充冲突处理策略。

QA：

- 同一条评论被多个 source 看到时，实际只回复一次。

## Phase 3 详细任务

### Task 15：实现 Cookie 状态检查与自动刷新

- 定期检测 Cookie 有效性。
- 按设计接入 refresh 流程。

QA：

- 可独立执行 Cookie 检查。
- 模拟需刷新场景时可成功刷新。

### Task 16：增强熔断与恢复逻辑

- Source 熔断。
- Provider 熔断。
- Sender 熔断。

QA：

- 连续失败后进入冷却。
- 冷却结束后能探测恢复。

### Task 17：增强状态恢复与日志

- 崩溃后恢复游标与历史状态。
- 日志分级与错误分类。

QA：

- 杀进程后重启，机器人不会重复回复旧评论。

## 5. 依赖关系

### Phase 1 依赖顺序

1. Task 1 → Task 2。
2. Task 2 → Task 3。
3. Task 3 → Task 4 / Task 5 可并行。
4. Task 5 → Task 6。
5. Task 6 → Task 7。
6. Task 4 + Task 7 + Task 8 + Task 9 → Task 10。

### 核心串联关系

- 没有配置层，就不能安全启动。
- 没有状态存储，就不能正确去重。
- 没有 `msgfeed` 采集，就没有最小事件入口。
- 没有发送器和退避，就不能形成可运行闭环。

## 6. Phase 1 实现准备结果

### 6.1 需要优先确认的现有文件

- `/home/shf/.config/opencode/scripts/bilibili scripts/bilibili_wbi.py`
- `/home/shf/.config/opencode/docs/bilibili-msg/bilibili-cookies.txt`
- `/home/shf/.config/opencode/agents/bilibili-agent.md`

### 6.2 需要优先复用的现有能力

- Cookies 读取方式。
- WBI 签名逻辑。
- 现有 Bilibili 路径规范。
- 现有错误处理和输出风格。

### 6.3 Phase 1 功能成功标准

1. 机器人能读取配置并启动。
2. 机器人能拉取 `/x/msgfeed/reply`。
3. 新评论事件能被去重层拦截重复项。
4. 主 Provider 能生成回复。
5. 能成功发送一条自动回复。
6. 发送后历史记录正确写入。
7. 出错时能退避，不会连续狂刷接口。

### 6.4 Phase 1 手动 QA 计划

#### Objective

验证最小可运行闭环是否真实工作。

#### Prerequisites

- 可用的 Bilibili Cookies。
- 至少一个可用的 OpenAI-compatible API Key。
- 一个真实可观测的新评论或回复事件。

#### Test Cases

1. 启动测试：运行守护进程 → 成功启动 → 日志显示配置加载完成。
2. 采集测试：执行一次 `msgfeed` 采集 → 返回标准化事件 → 可看到 `rpid/oid/content`。
3. 去重测试：重复注入同一事件 → 第二次被跳过。
4. 生成测试：给定评论文本 → Provider 返回有效回复。
5. 发送测试：构造真实回复 → B 站返回成功。
6. 退避测试：人为让发送失败 → 观察退避时间增长。
7. fallback 测试：主 Provider 不可用 → 本地降级链路被调用。

#### Success Criteria

所有测试用例通过。

## 7. 当前建议的下一步

进入实际实现时，建议严格按以下顺序推进：

1. 先做 Task 1-4。
2. 再做 Task 5-9。
3. 最后联调 Task 10。

这样可以最快得到一个可测试、可验证的 Phase 1 闭环。

## 8. 备注

- 本计划已经按当前已确认需求收敛，不再保留占位性假设。
- 若后续用户变更回复策略、改为半自动审核、或改为 Docker 常驻，需要重新调整计划。
