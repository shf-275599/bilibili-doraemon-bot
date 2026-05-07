# Bilibili Agent 评论自动回复机器人设计文档

日期：2026-05-07

## 1. 目标

在当前 `bilibili-agent` 基础上新增一个运行于本机 WSL / Linux 环境的常驻后台评论自动回复机器人，支持以下六项能力：

1. 评论监听模块。
2. AI 回复生成。
3. 评论发送。
4. Cookie 自动刷新。
5. 历史去重。
6. 频率控制。

该机器人应优先稳定、保守、可观测，并与现有 `~/.config/opencode` 目录结构、Cookies、WBI 能力、脚本资产保持兼容。

## 2. 已确认约束

- 运行模式：常驻后台自动机器人。
- 发送方式：全自动直接发送。
- 智能回复：双通道。
  - 主通道：外部 AI Provider。
  - 降级通道：当前 OpenCode / bilibili agent 模型能力。
- 外部 AI Provider：OpenAI-compatible 优先。
- 密钥管理：环境变量。
- 监听范围：
  1. 别人回复我 / 评论我的消息通知流。
  2. 我自己视频、动态下的评论列表。
  3. 别人视频、动态中 @ 我的评论。
- 过滤策略：基础过滤。
- 风控策略：保守模式。
- 第一版部署环境：当前 WSL / Linux 本机。

## 3. 非目标

- 第一版不做 Web 管理台。
- 第一版不做人工审核队列。
- 第一版不做多账号并发。
- 第一版不承诺图片评论理解、多模态回复。
- 第一版不承诺 OAuth Provider 的完整刷新闭环，只保留适配接口和注入位。

## 4. 总体方案

采用“主控守护进程 + 可复用脚本模块”的结构。

### 4.1 角色分层

- `bilibili-agent.md`：保留为交互型 agent，负责手动触发、诊断、查看状态、辅助排障。
- 评论机器人守护进程：负责后台常驻轮询、自动回复、去重、风控和状态落盘。

### 4.2 数据流

```text
评论来源
  ├─ /x/msgfeed/reply
  ├─ 自己视频评论列表
  ├─ 自己动态评论列表
  └─ 别人视频/动态中 @我的评论
        ↓
事件归一化
        ↓
基础过滤
        ↓
历史去重
        ↓
上下文补全
        ↓
AI Provider 抽象层
  ├─ 主通道：OpenAI-compatible provider
  └─ 降级通道：OpenCode / bilibili agent 模型能力
        ↓
评论发送器
        ↓
状态落盘 / 风控计数 / 退避 / 下轮调度
```

## 5. 文件与目录设计

### 5.1 脚本目录

建议新增目录：

```text
/home/shf/.config/opencode/scripts/bilibili bot/
  bilibili-comment-bot.py
  comment_sources.py
  comment_normalizer.py
  comment_filters.py
  comment_dedup.py
  reply_providers.py
  reply_prompt.py
  comment_sender.py
  cookie_refresh.py
  rate_control.py
  state_store.py
  bot_config.py
```

### 5.2 状态目录

```text
/home/shf/.config/opencode/data/bilibili-bot/
  bot-config.toml
  processed-comments.jsonl
  reply-history.jsonl
  bot-state.json
  bot-errors.log
  provider-cache.json
```

### 5.3 复用现有资产

- `/home/shf/.config/opencode/docs/bilibili-msg/bilibili-cookies.txt`
- `/home/shf/.config/opencode/scripts/bilibili scripts/bilibili_wbi.py`
- 现有脚本路径规范和输出目录规范。

## 6. 模块职责

### 6.1 `bilibili-comment-bot.py`

- 守护进程入口。
- 加载配置和环境变量。
- 初始化日志、状态存储、Provider、退避器。
- 调度所有 source。
- 执行健康检查、重试、熔断、恢复。

### 6.2 `comment_sources.py`

建议拆成多个 source：

- `MsgFeedReplySource`
- `OwnVideoCommentSource`
- `OwnDynamicCommentSource`
- `MentionCommentSource`

每个 source 输出统一的 `CommentEvent`。

### 6.3 `comment_normalizer.py`

把不同 API 返回结构归一为同一事件模型。

建议字段：

- `source_type`
- `business_type`
- `oid`
- `rpid`
- `root_rpid`
- `parent_rpid`
- `author_mid`
- `author_name`
- `content_text`
- `at_me`
- `created_at`
- `raw_payload`

### 6.4 `comment_filters.py`

基础过滤规则：

- 跳过自己。
- 跳过空文本。
- 跳过纯表情 / 纯符号。
- 跳过无意义超短内容。
- 跳过黑名单用户。
- 跳过近期相似重复互动。

### 6.5 `comment_dedup.py`

- 主键优先使用 `(business_type, oid, rpid)`。
- 记录 `seen_at`、`replied_at`、`reply_status`、`provider_used`、`reply_text_hash`。
- 支持判断“已见过但未成功发送”和“已成功回复”。

### 6.6 `reply_providers.py`

统一接口：

```python
generate_reply(event, context, config) -> ReplyResult
```

第一版包含：

- `OpenAICompatibleProvider`
- `OpenCodeFallbackProvider`

Provider 配置字段应至少支持：

- `type`
- `base_url`
- `model`
- `api_key_env`
- `timeout_seconds`
- `temperature`
- `max_tokens`

### 6.7 `reply_prompt.py`

Prompt 组成建议：

- 系统人设。
- 回复风格约束。
- 安全约束。
- 来源类型。
- 当前评论。
- 根评论 / 父评论上下文。
- 视频 / 动态摘要。
- 是否 @ 我。

### 6.8 `comment_sender.py`

负责统一封装 `/x/v2/reply/add`：

- 业务类型映射。
- `oid`、`root`、`parent` 参数。
- `csrf=bili_jct`。
- WBI 参数。
- Referer / UA / Cookie。
- 错误码解析。

### 6.9 `cookie_refresh.py`

- 定期检查 Cookie 状态。
- 按 B 站刷新流程刷新 Cookie。
- 刷新成功后回写持久化文件。
- 刷新失败时触发告警与发送熔断。

### 6.10 `rate_control.py`

- 请求节流。
- 发送前随机延迟。
- 连续失败自适应退避。
- Provider 熔断与恢复。
- Source 级降频。

### 6.11 `state_store.py`

- JSON / JSONL 状态落盘。
- 启动恢复。
- 历史窗口查询。
- 崩溃后的最小恢复能力。

## 7. 配置设计

建议使用 `/home/shf/.config/opencode/data/bilibili-bot/bot-config.toml`。

### 7.1 基础配置

```toml
[bot]
enabled = true
poll_interval_seconds = 30
run_mode = "daemon"
conservative_mode = true
log_level = "INFO"
```

### 7.2 来源配置

```toml
[sources.msgfeed]
enabled = true
poll_interval_seconds = 20

[sources.own_video]
enabled = true
poll_interval_seconds = 120

[sources.own_dynamic]
enabled = true
poll_interval_seconds = 120

[sources.mention]
enabled = true
poll_interval_seconds = 60
```

### 7.3 过滤配置

```toml
[filters]
skip_self = true
skip_empty = true
skip_pure_emoji = true
min_meaningful_length = 2
blacklist_mids = []
duplicate_window_minutes = 1440
```

### 7.4 AI 配置

```toml
[ai]
primary_provider = "deepseek"
fallback_provider = "opencode-local"
timeout_seconds = 25
max_reply_chars = 100

[ai.providers.deepseek]
type = "openai_compatible"
base_url = "https://api.deepseek.com/v1"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"

[ai.providers.mimo]
type = "openai_compatible"
base_url = "https://example.invalid/v1"
model = "your-model"
api_key_env = "MIMO_API_KEY"
```

### 7.5 回复风格配置

```toml
[reply]
system_prompt = "你是一个友善、自然、不过度营销的B站UP主。"
temperature = 0.7
max_tokens = 200
prefix = ""
mention_style = "friendly"
```

### 7.6 风控配置

```toml
[rate_limit]
min_request_interval_seconds = 3
reply_delay_min_seconds = 8
reply_delay_max_seconds = 20
max_retries = 3
backoff_base_seconds = 10
circuit_breaker_failures = 5
circuit_breaker_cooldown_seconds = 600
max_hourly_replies = 20
max_daily_replies = 100
```

### 7.7 Cookie 配置

```toml
[cookie]
cookies_file = "/home/shf/.config/opencode/docs/bilibili-msg/bilibili-cookies.txt"
refresh_enabled = true
refresh_token_env = "BILIBILI_REFRESH_TOKEN"
check_interval_minutes = 30
```

## 8. 风控策略

第一版采用保守模式。

### 8.1 轮询节奏

- `msgfeed`：20~30 秒。
- 自己视频 / 动态评论扫描：1~3 分钟。
- @我评论检索：约 1 分钟。

### 8.2 发送节奏

- 每次真正发送前随机等待 8~20 秒。
- 单轮最多回复 3~5 条。
- 同一用户短时间内限频。
- 同一视频 / 动态下短时间内限频。

### 8.3 自适应退避

发生以下情况时进入退避：

- 429 / -509 / 疑似风控。
- Provider 超时连续失败。
- 评论发送接口异常。

建议退避梯度：30 秒 → 60 秒 → 2 分钟 → 5 分钟 → 10 分钟 → 熔断冷却。

### 8.4 熔断策略

- 连续发送失败达到阈值时暂停发送。
- 熔断期间仍可继续采集并记录事件。
- 冷却期后先小流量探测恢复。

### 8.5 硬保险

- 最大小时回复数。
- 最大日回复数。
- 单用户回复频率上限。
- Cookie 刷新失败后禁止自动发送。

## 9. 验证方案

### 9.1 成功标准

1. 后台运行至少 12 小时不崩。
2. 三类来源中的新评论事件都能被捕获。
3. 同一条评论不会重复回复。
4. 主 Provider 正常时能生成并发送回复。
5. 主 Provider 失败时能触发降级通道。
6. 连续失败时会自动退避，而不是高频重试。
7. Cookie 检查与刷新流程可独立验证。

### 9.2 手动 QA 场景

- 场景 1：制造一条“回复我”的评论，观察是否自动回复。
- 场景 2：在自己视频下发布新评论，观察扫描型 source 是否命中。
- 场景 3：让主 Provider 故意失效，验证 fallback。
- 场景 4：重复投喂同一评论，验证 dedup。
- 场景 5：模拟接口失败，验证退避与熔断。
- 场景 6：模拟 Cookie 失效，验证 refresh。

## 10. 分阶段实施计划

### Phase 1：最小可运行闭环

- `msgfeed` 监听。
- 历史去重。
- OpenAI-compatible Provider。
- 评论发送。
- 基础退避。

验收：能对“别人回复我 / 评论我”的消息通知流进行全自动回复。

### Phase 2：扩展监听范围

- 自己视频评论。
- 自己动态评论。
- @我评论。

验收：三类来源统一进入同一回复流水线。

### Phase 3：稳定性增强

- Cookie 自动刷新。
- 熔断器。
- 更强的限频和黑名单。
- 更完整的状态与运行记录。

验收：可长期后台稳定运行，并在失败时自动自我保护。

## 11. 风险与注意事项

- 评论发送接口与评论读取接口的风控强于普通只读接口。
- `@我评论` 来源在不同业务类型下的归一化可能需要额外字段适配。
- OpenCode 本地模型降级通道的稳定调用路径需要在实施阶段再精确确认。
- Cookie 刷新涉及敏感凭据，必须只通过环境变量和本地受控文件处理。
- 用户刚刚贴出的真实密钥与 Token 必须视为已泄露并尽快轮换。

## 12. 本文档自检结果

- 无占位符。
- 模块边界与数据流一致。
- 范围聚焦于第一版后台自动回复机器人。
- 通用 Provider 能力明确为“OpenAI-compatible 优先”，避免第一版过度泛化。

## 13. 后续动作

1. 用户审阅本设计文档。
2. 如无修改，基于本文档输出详细实施计划。
3. 按 Phase 1 → Phase 2 → Phase 3 顺序实施。
