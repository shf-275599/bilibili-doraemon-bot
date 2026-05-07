# Bilibili 评论自动回复机器人 v2

自动监听 Bilibili 评论和私信，使用 AI 生成回复并发送的后台守护进程。

## 功能特性

- **Pipeline 管道架构** - 模块化处理流程，易于扩展
- **多来源监听** - 消息通知回复、@我消息、自己动态评论、自己视频评论、私信
- **AI 智能回复** - 支持 OpenAI-compatible API（DeepSeek/GPT/Claude 等）+ 本地降级通道
- **Cookie 自动刷新** - RSA-OAEP 加密 + refresh_csrf 完整链路
- **保守风控** - 随机延迟、来源熔断、全局熔断、小时/日回复上限
- **类型安全配置** - Pydantic v2 配置验证
- **结构化日志** - structlog JSON 格式，便于监控
- **单元测试** - 20+ 测试用例，保证代码质量

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt

# 或使用 pyproject.toml（推荐）
pip install -e .
```

### 2. 配置

```bash
# 复制配置模板
cp .env.example .env
cp config/bilibili-cookies.example.txt config/bilibili-cookies.txt

# 编辑配置文件
nano .env                          # 填入 API Key 和 Refresh Token
nano config/bilibili-cookies.txt   # 填入真实 Cookies
nano config/bot-config.toml        # 调整机器人配置
```

### 3. 测试运行

```bash
# 执行一轮 dry-run（生成回复但不发送）
python -m bilibili_bot --once --dry-run

# 执行一轮真实自动回复
python -m bilibili_bot --once
```

### 4. 启动守护模式

```bash
# 前台运行
python -m bilibili_bot

# 后台运行（推荐使用 tmux）
tmux new-session -d -s bilibot "export DEEPSEEK_API_KEY=xxx && python -m bilibili_bot"
```

## 配置说明

### 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（主 AI Provider） | 是 |
| `BILIBILI_REFRESH_TOKEN` | Bilibili Refresh Token（Cookie 自动刷新） | 否 |

### 获取 Refresh Token

1. 用浏览器登录 [https://www.bilibili.com](https://www.bilibili.com)
2. 按 F12 打开开发者工具
3. 切换到 **Application** → **Local Storage** → `https://www.bilibili.com`
4. 查找 `ac_time_value` 键，复制其值

### 配置文件

编辑 `config/bot-config.toml`：

```toml
[bot]
poll_interval_seconds = 30    # 轮询间隔
log_level = "INFO"            # 日志级别

[sources.msgfeed]
enabled = true                # 启用消息通知回复监听
poll_interval_seconds = 20    # 独立轮询间隔

[sources.mention]
enabled = true                # 启用 @我 消息监听

[sources.dm]
enabled = true                # 启用私信自动回复
poll_interval_seconds = 60    # 私信轮询间隔
max_reply_per_round = 5       # 每轮最大回复数
skip_keywords = ["广告", "推广"]  # 跳过含关键词的私信

[ai]
primary_provider = "deepseek" # 主 AI Provider
fallback_provider = "opencode-local"  # 降级 Provider

[reply]
system_prompt = "你是一只小苏doge，一个友善、有梗、说话自然的B站UP主..."
temperature = 0.75            # 回复随机性（0-1）
max_tokens = 200              # 最大 token 数

[rate_limit]
max_hourly_replies = 20       # 每小时最大回复数
max_daily_replies = 100       # 每天最大回复数
reply_delay_min_seconds = 3   # 最小回复延迟
reply_delay_max_seconds = 8   # 最大回复延迟
```

## 目录结构

```
bilibili-bot/
├── src/bilibili_bot/          # 源代码（标准 Python 包）
│   ├── __init__.py
│   ├── __main__.py           # 入口（python -m bilibili_bot）
│   ├── config.py             # Pydantic 配置模型
│   ├── client.py             # 统一 HTTP 客户端
│   ├── events.py             # 事件模型（CommentEvent/DMEvent）
│   ├── wbi.py                # WBI 签名
│   ├── state.py              # 状态存储（带文件锁）
│   ├── cookie.py             # Cookie 刷新管理
│   ├── log.py                # 结构化日志
│   ├── pipeline/             # 处理管道
│   │   ├── base.py           # PipelineStage ABC
│   │   ├── dedup.py          # 去重阶段
│   │   ├── filter.py         # 过滤阶段
│   │   ├── rate_limit.py     # 频控阶段
│   │   ├── generate.py       # AI 生成阶段
│   │   ├── safety.py         # 安全审查阶段
│   │   └── send.py           # 发送阶段
│   ├── providers/            # AI Provider
│   │   ├── base.py           # Provider ABC
│   │   ├── openai_compat.py  # OpenAI 兼容
│   │   ├── opencode_fallback.py  # 本地降级
│   │   └── manager.py        # Provider 管理器
│   └── sources/              # 数据来源
│       ├── base.py           # Source ABC
│       ├── msgfeed.py        # 消息通知
│       ├── mention.py        # @我消息
│       ├── own_video.py      # 自己视频评论
│       ├── own_dynamic.py    # 自己动态评论
│       └── dm.py             # 私信
├── tests/                    # 单元测试
│   ├── test_config.py
│   ├── test_events.py
│   ├── test_dedup.py
│   ├── test_filter.py
│   ├── test_safety.py
│   ├── test_state.py
│   └── test_wbi.py
├── cli/                      # CLI 工具
│   └── wbi_tool.py           # WBI 签名工具
├── config/                   # 配置文件
│   ├── bot-config.toml       # 机器人配置
│   ├── bilibili-cookies.txt  # Cookies（gitignored）
│   └── bilibili-cookies.example.txt
├── data/                     # 运行时数据（gitignored）
│   ├── bot-state.json        # 运行状态
│   ├── processed.jsonl       # 去重记录
│   └── reply-history.jsonl   # 回复历史
├── docs/                     # 文档
│   └── design.md             # 设计文档
├── pyproject.toml            # 项目配置
├── requirements.txt          # 依赖
├── bilibot@.service          # systemd 服务
├── .env.example              # 环境变量模板
├── .gitignore
└── README.md
```

## 架构设计

### Pipeline 管道

所有事件（评论/私信）通过统一的处理管道：

```
Source.fetch() → [Event]
    ↓
DedupStage      → 跳过已处理
FilterStage     → 跳过自己/空/黑名单
RateLimitStage  → 等待/阻塞如果超限
GenerateStage   → 调用 AI 生成回复
SafetyStage     → 检查回复内容安全
SendStage       → 发送到 Bilibili API
```

### 事件模型

```python
@dataclass
class Event:
    source_type: str      # "msgfeed" | "mention" | "own_video" | "own_dynamic" | "dm"
    event_key: str        # 去重键
    created_at: int       # 时间戳

@dataclass
class CommentEvent(Event):
    business_type: str    # "video" | "dynamic" | "dynamic_draw"
    oid: str              # 内容 ID
    rpid: str             # 评论 ID
    author_mid: str       # 评论者 UID
    content_text: str     # 评论内容

@dataclass
class DMEvent(Event):
    talker_id: int        # 发送者 UID
    dm_content: str       # 私信内容
    msg_key: int          # 消息 ID
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--config PATH` | 指定配置文件路径（默认 `config/bot-config.toml`） |
| `--once` | 只执行一轮，不进入守护模式 |
| `--dry-run` | 只生成回复，不实际发送 |

## 风控策略

- **随机延迟** - 每条回复前随机等待 3-8 秒
- **来源熔断** - 单来源连续失败 3 次 → 冷却 180 秒
- **全局熔断** - 连续失败 5 次 → 冷却 600 秒
- **小时上限** - 每小时最多 20 条回复
- **日上限** - 每天最多 100 条回复
- **用户限频** - 每用户每小时最多 5 条
- **内容限频** - 每内容每小时最多 10 条

## 自定义 AI Provider

在 `config/bot-config.toml` 中添加新的 Provider：

```toml
[ai.providers.openai]
type = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4"
api_key_env = "OPENAI_API_KEY"

[ai.providers.claude]
type = "openai_compatible"
base_url = "https://api.anthropic.com/v1"
model = "claude-3-sonnet-20240229"
api_key_env = "ANTHROPIC_API_KEY"
```

然后修改 `primary_provider` 或 `fallback_provider` 为新 Provider 名称。

## 运行测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=src/bilibili_bot --cov-report=html
```

## 常见问题

### Cookie 失效怎么办？

机器人会自动检测 Cookie 失效并停止发送。如果配置了 `BILIBILI_REFRESH_TOKEN`，会自动刷新。否则需要手动更新 `config/bilibili-cookies.txt`。

### 如何查看日志？

```bash
# 前台运行时直接看输出（JSON 格式）
# 后台运行时查看 tmux 会话
tmux attach -t bilibot
```

### 如何停止机器人？

```bash
# 如果是前台运行，按 Ctrl+C（优雅退出）
# 如果是 tmux 后台运行
tmux send-keys -t bilibot C-c  # 优雅退出
# 或
tmux kill-session -t bilibot   # 强制退出
```

## 从 v1 迁移

1. 配置格式不变（`config/bot-config.toml`）
2. 数据文件格式可能变化，建议备份 `data/` 目录
3. 启动命令改为 `python -m bilibili_bot`
4. 查看 `docs/design.md` 了解完整架构变更

## 许可证

MIT
