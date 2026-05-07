# Bilibili Bot v2 设计文档

**版本**：2.0.0  
**日期**：2026-05-08  
**状态**：设计定稿

---

## 1. 项目概述

### 1.1 项目定位

Bilibili Bot v2 是一个自动监听 Bilibili 评论和私信、使用 AI 生成回复并发送的后台守护进程。本项目是对 v1 版本的完全重构，旨在解决原代码库中存在的重复代码、紧耦合、性能瓶颈和安全问题。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **多来源监听** | 消息通知回复流、@我消息、自己视频评论、自己动态评论、私信 |
| **AI 智能回复** | OpenAI-compatible API（主通道）+ 本地降级通道 |
| **Cookie 自动刷新** | RSA-OAEP 加密 + refresh_csrf 完整链路 |
| **统一管道处理** | 评论和私信共用同一处理流水线 |
| **历史去重** | 泛型去重服务，TTL dict + JSONL 持久化 |
| **状态持久化** | fcntl.flock() 文件锁 + 原子写入 |
| **保守风控** | 随机延迟、来源熔断、全局熔断、小时/日回复上限 |
| **结构化日志** | structlog，JSON（生产）/ 控制台（开发）渲染器切换 |

### 1.3 设计原则

1. **单一职责**：每个模块只做一件事，做好一件事
2. **显式优于隐式**：配置、依赖、状态变更全部显式声明
3. **可测试性**：从 TDD 开始，所有核心逻辑可独立单元测试
4. **可观测性**：结构化日志、健康检查、状态可查询
5. **安全优先**：文件锁保护并发、敏感信息环境变量管理、WBI 签名内聚

### 1.4 非目标

- 第一版不做 Web 管理台
- 第一版不做人工审核队列
- 第一版不做多账号并发
- 第一版不承诺图片评论理解、多模态回复
- 第一版保持同步架构，不引入异步复杂性

---

## 2. 架构设计

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Bilibili Bot v2                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Sources   │  │  Pipeline   │  │      Providers          │  │
│  │             │  │             │  │                         │  │
│  │ • msgfeed   │──│ • dedup     │──│ • OpenAI-compatible     │  │
│  │ • mention   │  │ • filter    │  │ • OpenCode fallback     │  │
│  │ • own_video │  │ • rate_limit│  │                         │  │
│  │ • own_dyn   │  │ • generate  │  └─────────────────────────┘  │
│  │ • dm        │  │ • safety    │                               │
│  └─────────────┘  │ • send      │  ┌─────────────────────────┐  │
│                   └─────────────┘  │    Infrastructure       │  │
│                                    │                         │  │
│  ┌─────────────┐                   │ • BilibiliSession       │  │
│  │   State     │◄──────────────────│ • WBI Signer            │  │
│  │             │                   │ • StateStore (flock)    │  │
│  │ • bot-state │                   │ • CookieRefresh         │  │
│  │ • processed │                   │ • structlog             │  │
│  │ • history   │                   └─────────────────────────┘  │
│  └─────────────┘                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模块层次

| 层次 | 模块 | 职责 |
|------|------|------|
| **入口层** | `__main__.py` | CLI 参数解析、守护进程循环、信号处理 |
| **配置层** | `config.py` | Pydantic 配置模型、TOML 加载、环境变量覆盖 |
| **网络层** | `client.py`, `wbi.py` | HTTP 客户端、WBI 签名、Cookie 管理 |
| **事件层** | `events.py` | Event 基类、CommentEvent、DMEvent 定义 |
| **采集层** | `sources/` | 5 个 Source 实现，统一输出 Event |
| **管道层** | `pipeline/` | 6 个处理阶段、Pipeline 运行器 |
| **AI 层** | `providers/` | AI Provider 抽象、OpenAI-compatible、降级通道 |
| **基础设施** | `state.py`, `cookie.py`, `log.py` | 状态存储、Cookie 刷新、日志设置 |
| **辅助工具** | `prompt.py`, `health.py` | Prompt 构建器、健康检查服务器 |

### 2.3 目录结构

```
bilibili-bot/
├── pyproject.toml                    # 项目元数据、依赖、pytest 配置
├── requirements.txt                  # 快速 pip install
├── config/
│   ├── bot-config.toml              # 主配置（TOML 格式）
│   ├── bilibili-cookies.txt         # (gitignored) Bilibili Cookies
│   └── bilibili-cookies.example.txt # Cookies 示例
├── data/                             # 运行时状态 (gitignored)
│   ├── bot-state.json               # 机器人运行状态
│   ├── processed.jsonl              # 已处理事件去重记录
│   └── reply-history.jsonl          # 回复历史日志
├── src/
│   └── bilibili_bot/
│       ├── __init__.py              # 包初始化
│       ├── __main__.py              # python -m bilibili_bot 入口
│       ├── config.py                # Pydantic 配置模型
│       ├── client.py                # BilibiliSession（统一 HTTP 客户端）
│       ├── wbi.py                   # WBI 签名（纯函数，无 I/O）
│       ├── events.py                # Event 基类 + CommentEvent + DMEvent
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py              # Source ABC
│       │   ├── msgfeed.py           # MsgFeedReplySource
│       │   ├── mention.py           # MentionMsgFeedSource
│       │   ├── own_video.py         # OwnVideoCommentSource
│       │   ├── own_dynamic.py       # OwnDynamicCommentSource
│       │   └── dm.py                # DMSource
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── base.py              # PipelineStage ABC + Pipeline 运行器
│       │   ├── dedup.py             # 通用 DedupStage
│       │   ├── filter.py            # FilterStage
│       │   ├── rate_limit.py        # RateLimitStage
│       │   ├── generate.py          # AIGenerateStage
│       │   ├── safety.py            # SafetyCheckStage
│       │   └── send.py              # SendStage
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py              # Provider ABC + ReplyResult
│       │   ├── openai_compat.py     # OpenAICompatibleProvider
│       │   └── opencode_fallback.py # OpenCodeFallbackProvider
│       ├── prompt.py                # 统一 Prompt 构建器（评论 + 私信）
│       ├── state.py                 # StateStore（带文件锁）
│       ├── cookie.py                # Cookie 刷新管理器
│       ├── health.py                # 健康检查（可选 HTTP 服务器）
│       └── log.py                   # structlog 设置
├── tests/
│   ├── conftest.py                  # 共享 fixtures
│   ├── test_config.py
│   ├── test_client.py
│   ├── test_wbi.py
│   ├── test_events.py
│   ├── test_dedup.py
│   ├── test_filter.py
│   ├── test_rate_limit.py
│   ├── test_safety.py
│   ├── test_prompt.py
│   ├── test_pipeline.py
│   └── test_state.py
├── cli/
│   └── wbi_tool.py                  # 独立 WBI CLI（从 bilibili_wbi.py 迁移）
├── docs/
│   ├── design.md                    # 本设计文档
│   └── migration.md                 # v1 迁移说明
├── bilibot@.service                 # systemd 服务单元
├── .env.example                     # 环境变量模板
├── .gitignore
└── README.md
```

---

## 3. 核心抽象详解

### 3.1 Event 层次结构 (`events.py`)

Event 是系统内部统一的事件表示，所有 Source 输出和 Pipeline 处理都基于 Event。

```python
@dataclass
class Event:
    """所有事件的基类"""
    source_type: str      # 来源类型：msgfeed/mention/own_video/own_dynamic/dm
    event_key: str        # 通用去重键
    created_at: int       # Unix 时间戳
    raw_payload: dict     # 原始 API 响应数据

    @property
    def author_id(self) -> str:
        """事件作者 ID"""
        ...

    @property
    def content(self) -> str:
        """事件内容文本"""
        ...

    @property
    def target_id(self) -> str:
        """目标 ID：评论为 oid，私信为 talker_id"""
        ...


@dataclass
class CommentEvent(Event):
    """评论事件"""
    business_type: str    # 业务类型：1=视频，2=图文，3=动态，4=课程
    oid: str              # 对象 ID（视频/动态 ID）
    rpid: str             # 回复 ID
    root_rpid: str        # 根回复 ID
    parent_rpid: str      # 父回复 ID
    author_mid: str       # 作者 MID
    author_name: str      # 作者昵称
    content_text: str     # 评论文本
    at_me: bool           # 是否 @ 我


@dataclass
class DMEvent(Event):
    """私信事件"""
    talker_id: int        # 对话者 ID
    talker_name: str      # 对话者昵称
    msg_key: int          # 消息唯一键
```

**设计理由**：
- 统一 Event 基类使得去重、管道、Prompt 构建可以共用逻辑
- CommentEvent 和 DMEvent 分别封装各自特有字段
- `event_key` 是去重的统一键，CommentEvent 使用 `(business_type, oid, rpid)`，DMEvent 使用 `msg_key`

### 3.2 BilibiliSession (`client.py`)

BilibiliSession 是 `requests.Session` 的子类，提供统一的 HTTP 客户端能力。

```python
class BilibiliSession(requests.Session):
    def __init__(self, cookies_file: str, timeout: int = 25):
        super().__init__()
        self._cookies_file = cookies_file
        self._timeout = timeout
        self._wbi_keys: tuple[str, str] | None = None  # img_key, sub_key
        self._wbi_keys_at: float = 0  # WBI 键缓存时间
        self._load_cookies()
        self._setup_retry()

    def _load_cookies(self) -> None:
        """从文件加载 Cookies"""
        ...

    def _save_cookies(self) -> None:
        """保存 Cookies 到文件（原子写入）"""
        ...

    def request(self, method, url, **kwargs):
        """统一请求入口：注入 Cookie、UA、Referer、WBI 签名"""
        ...

    def get_wbi_keys(self) -> tuple[str, str]:
        """获取 WBI 签名键（带缓存）"""
        ...

    def sign_wbi(self, params: dict) -> dict:
        """对请求参数进行 WBI 签名"""
        ...
```

**设计理由**：
- 子类化 `requests.Session` 而非新建客户端，直接获得连接池、Cookie 持久化、重试机制
- WBI 签名逻辑内聚到 HTTP 客户端，调用方无需关心签名细节
- WBI 键缓存避免频繁请求 `/x/web-interface/nav`

### 3.3 Pipeline 架构 (`pipeline/base.py`)

Pipeline 是有序中间件链，评论和私信共用同一处理流程。

```python
class PipelineStage(ABC):
    """管道阶段抽象基类"""

    @abstractmethod
    def process(self, event: Event, context: PipelineContext) -> StageResult:
        """处理事件，返回阶段结果"""
        ...


class Pipeline:
    """管道运行器"""

    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    def run(self, event: Event, context: PipelineContext) -> bool:
        """
        运行完整管道。
        返回 True 表示事件处理完成（成功或跳过），False 表示需要重试。
        """
        for stage in self.stages:
            result = stage.process(event, context)
            if result.action is StageAction.SKIP:
                return True  # 跳过，但视为完成
            if result.action is StageAction.RETRY:
                return False  # 需要重试
            if result.action is StageAction.STOP:
                return False  # 停止处理
        return True
```

**管道阶段顺序**：
```
DedupStage → FilterStage → RateLimitStage → GenerateStage → SafetyStage → SendStage
```

**设计理由**：
- 每个阶段是独立类，可单独测试、替换、扩展
- 统一 `StageResult` 返回类型，Pipeline 运行器根据 `action` 决定后续行为
- 评论和私信共用管道，减少代码重复

### 3.4 PipelineContext

PipelineContext 是管道处理的上下文，包含所有阶段需要的共享依赖。

```python
@dataclass
class PipelineContext:
    config: BotConfig           # 配置对象
    client: BilibiliSession     # HTTP 客户端
    dedup: DedupService         # 去重服务
    providers: ProviderManager  # AI Provider 管理器
    rate_limiter: RateController  # 限流控制器
    dry_run: bool = False       # 干跑模式（不发送）
```

### 3.5 通用 DedupService (`pipeline/dedup.py`)

DedupService 是泛型去重服务，合并了 v1 的 `comment_dedup` 和 `dm_dedup`。

```python
class DedupService:
    def __init__(self, store: StateStore, max_size: int = 50000, ttl_days: int = 7):
        self._store = store
        self._max_size = max_size
        self._ttl_days = ttl_days
        self._cache: dict[str, DedupRecord] = {}  # 内存缓存

    def is_duplicate(self, key: str) -> DedupStatus:
        """
        检查事件是否已处理。
        返回 DedupStatus: NEW / SEEN / REPLIED
        """
        ...

    def mark(self, key: str, status: str, **metadata) -> None:
        """标记事件处理状态"""
        ...

    def flush(self) -> None:
        """将内存缓存刷新到磁盘（JSONL 格式）"""
        ...
```

**设计理由**：
- 单个服务处理所有事件类型的去重，避免逻辑分散
- 内存缓存 + 磁盘持久化，平衡性能和可靠性
- TTL 机制自动清理过期记录，控制存储增长

### 3.6 StateStore (`state.py`)

StateStore 提供带文件锁的状态持久化能力。

```python
class StateStore:
    def __init__(self, state_file: str):
        self._state_file = state_file
        self._lock_fd: int | None = None
        self._state: dict = {}

    def acquire(self) -> None:
        """获取文件锁（fcntl.flock）"""
        ...

    def release(self) -> None:
        """释放文件锁"""
        ...

    def load(self) -> dict:
        """加载状态（需在锁内调用）"""
        ...

    def save(self, state: dict) -> None:
        """保存状态（原子写入：先写临时文件，再 rename）"""
        ...

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
```

**设计理由**：
- v1 代码无文件锁，多进程/线程并发不安全
- `fcntl.flock()` 提供进程级互斥锁
- 原子写入（write to temp + rename）避免写入中断导致文件损坏

### 3.7 AI Provider 抽象 (`providers/base.py`)

```python
class ReplyResult(NamedTuple):
    """AI 回复结果"""
    text: str
    provider: str
    model: str
    tokens_used: int
    latency_ms: int


class Provider(ABC):
    """AI Provider 抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def generate(self, prompt: str, config: ReplyConfig) -> ReplyResult:
        """生成回复"""
        ...


class ProviderManager:
    """Provider 管理器：主通道 + 降级通道"""

    def __init__(self, primary: Provider, fallback: Provider | None = None):
        self._primary = primary
        self._fallback = fallback

    def generate(self, prompt: str, config: ReplyConfig) -> ReplyResult:
        """
        生成回复：先尝试主通道，失败则降级。
        """
        ...
```

**实现**：
- `OpenAICompatibleProvider`：支持 DeepSeek、GPT、Claude 等 OpenAI-compatible API
- `OpenCodeFallbackProvider`：调用本地 `opencode` CLI 作为降级通道

---

## 4. 配置说明

### 4.1 配置模型 (`config.py`)

配置使用 Pydantic v2 `BaseSettings`，支持 TOML 文件加载和环境变量覆盖。

```python
class BotConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BILI_BOT_",
        env_file=".env",
        extra="ignore",
    )

    bot: BotSettings
    sources: SourcesConfig
    filters: FilterConfig
    ai: AIConfig
    reply: ReplyConfig
    dm_reply: ReplyConfig
    rate_limit: RateLimitConfig
    cookie: CookieConfig
    content_safety: SafetyConfig

    @classmethod
    def from_toml(cls, path: Path) -> "BotConfig":
        """从 TOML 文件加载配置"""
        ...
```

### 4.2 配置节详解

#### `[bot]` - 基础配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用机器人 |
| `poll_interval_seconds` | int | 30 | 轮询间隔 |
| `run_mode` | str | "daemon" | 运行模式：daemon/once |
| `conservative_mode` | bool | true | 保守模式（更严格的限频） |
| `log_level` | str | "INFO" | 日志级别 |
| `request_timeout_seconds` | int | 25 | HTTP 请求超时 |
| `source_failure_cooldown_seconds` | int | 180 | 来源失败冷却时间 |

#### `[sources.*]` - 来源配置

**`[sources.msgfeed]`** - 消息通知回复流

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 |
| `poll_interval_seconds` | int | 20 | 轮询间隔 |
| `page_size` | int | 10 | 每页数量 |

**`[sources.mention]`** - @我消息

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 |
| `page_size` | int | 10 | 每页数量 |

**`[sources.own_video]`** - 自己视频评论

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 |
| `video_page_size` | int | 5 | 视频列表每页数量 |
| `comment_page_size` | int | 10 | 评论列表每页数量 |
| `max_retries` | int | 2 | 最大重试次数 |
| `retry_sleep_seconds` | int | 6 | 重试间隔 |

**`[sources.own_dynamic]`** - 自己动态评论

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 |
| `dynamic_page_size` | int | 5 | 动态列表每页数量 |
| `comment_page_size` | int | 10 | 评论列表每页数量 |

**`[sources.dm]`** - 私信

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用 |
| `poll_interval_seconds` | int | 60 | 轮询间隔 |
| `max_reply_per_round` | int | 5 | 每轮最大回复数 |
| `skip_keywords` | list[str] | [] | 跳过含关键词的私信 |
| `whitelist_mids` | list[int] | [] | 白名单用户 UID（空=全部回复） |

#### `[filters]` - 过滤配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `skip_self` | bool | true | 跳过自己的评论 |
| `skip_empty` | bool | true | 跳过空文本 |
| `skip_pure_emoji` | bool | true | 跳过纯表情 |
| `min_meaningful_length` | int | 2 | 最小有意义长度 |
| `blacklist_mids` | list[int] | [] | 黑名单用户 UID |
| `duplicate_window_minutes` | int | 1440 | 去重窗口（分钟） |

#### `[ai]` - AI 配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `primary_provider` | str | "deepseek" | 主 Provider 名称 |
| `fallback_provider` | str | "opencode-local" | 降级 Provider 名称 |
| `timeout_seconds` | int | 25 | AI 请求超时 |
| `max_reply_chars` | int | 100 | 最大回复字符数 |

**`[ai.providers.<name>]`** - Provider 配置

```toml
[ai.providers.deepseek]
type = "openai_compatible"
base_url = "https://api.deepseek.com/v1"
model = "deepseek-v4-flash"
api_key_env = "DEEPSEEK_API_KEY"
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | str | Provider 类型：openai_compatible / opencode_local |
| `base_url` | str | API 基础 URL（openai_compatible） |
| `model` | str | 模型名称 |
| `api_key_env` | str | API Key 环境变量名 |

#### `[reply]` / `[dm_reply]` - 回复配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `system_prompt` | str | - | 系统提示词 |
| `temperature` | float | 0.75 | 回复随机性（0-1） |
| `max_tokens` | int | 200 | 最大 token 数 |
| `prefix` | str | "" | 回复前缀 |
| `mention_style` | str | "friendly" | @提及风格 |

#### `[rate_limit]` - 风控配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `min_request_interval_seconds` | int | 3 | 最小请求间隔 |
| `reply_delay_min_seconds` | int | 3 | 回复前最小延迟 |
| `reply_delay_max_seconds` | int | 8 | 回复前最大延迟 |
| `max_retries` | int | 3 | 最大重试次数 |
| `backoff_base_seconds` | int | 10 | 退避基数 |
| `circuit_breaker_failures` | int | 5 | 熔断失败阈值 |
| `circuit_breaker_cooldown_seconds` | int | 600 | 熔断冷却时间 |
| `max_hourly_replies` | int | 20 | 每小时最大回复数 |
| `max_daily_replies` | int | 100 | 每天最大回复数 |
| `source_circuit_breaker_failures` | int | 3 | 来源熔断失败阈值 |

#### `[cookie]` - Cookie 配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cookies_file` | str | "config/bilibili-cookies.txt" | Cookies 文件路径 |
| `refresh_enabled` | bool | true | 是否启用自动刷新 |
| `refresh_token_env` | str | "BILIBILI_REFRESH_TOKEN" | Refresh Token 环境变量名 |
| `check_interval_minutes` | int | 30 | 检查间隔（分钟） |
| `healthcheck_endpoint` | str | "https://api.bilibili.com/x/web-interface/nav" | 健康检查端点 |

### 4.3 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（主 AI Provider） | 是 |
| `BILIBILI_REFRESH_TOKEN` | Bilibili Refresh Token（Cookie 自动刷新） | 否 |
| `BILI_BOT_LOG_LEVEL` | 覆盖日志级别 | 否 |
| `BILI_BOT_CONFIG_PATH` | 覆盖配置文件路径 | 否 |

---

## 5. 数据流说明

### 5.1 完整数据流

```
┌──────────────────────────────────────────────────────────────────────┐
│  Source.fetch() → list[Event]                                        │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  for event in events:                                                │
│      Pipeline.run(event, context):                                   │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 1. DedupStage                                       │     │
│          │    - 检查 event_key 是否已处理                       │     │
│          │    - 返回 SKIP（已处理）或 CONTINUE（新事件）         │     │
│          └─────────────────────────────────────────────────────┘     │
│                                    │ CONTINUE                        │
│                                    ▼                                 │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 2. FilterStage                                      │     │
│          │    - 跳过自己/空文本/纯表情/黑名单/关键词             │     │
│          │    - 返回 SKIP（过滤）或 CONTINUE（通过）             │     │
│          └─────────────────────────────────────────────────────┘     │
│                                    │ CONTINUE                        │
│                                    ▼                                 │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 3. RateLimitStage                                   │     │
│          │    - 检查小时/日上限、来源熔断、全局熔断              │     │
│          │    - 返回 WAIT（等待）、SKIP（熔断）或 CONTINUE       │     │
│          └─────────────────────────────────────────────────────┘     │
│                                    │ CONTINUE                        │
│                                    ▼                                 │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 4. GenerateStage                                    │     │
│          │    - 构建 Prompt（评论上下文 + 人设 + 约束）          │     │
│          │    - 调用 AI Provider（主通道 → 降级）                │     │
│          │    - 返回 CONTINUE（附加 reply_text 到 context）      │     │
│          └─────────────────────────────────────────────────────┘     │
│                                    │ CONTINUE                        │
│                                    ▼                                 │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 5. SafetyStage                                      │     │
│          │    - 检查回复内容安全（敏感词、长度、格式）           │     │
│          │    - 返回 SKIP（不安全）或 CONTINUE（安全）           │     │
│          └─────────────────────────────────────────────────────┘     │
│                                    │ CONTINUE                        │
│                                    ▼                                 │
│          ┌─────────────────────────────────────────────────────┐     │
│          │ 6. SendStage                                        │     │
│          │    - 如果是 dry_run：仅日志记录                      │     │
│          │    - 否则：POST 到 Bilibili API（/x/v2/reply/add）    │     │
│          │    - 返回 CONTINUE（成功）或 RETRY/STOP（失败）       │     │
│          └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  StateStore.flush() → 原子写入磁盘                                   │
│    - bot-state.json: 运行状态                                        │
│    - processed.jsonl: 去重记录                                       │
│    - reply-history.jsonl: 回复日志                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Source 工作流程

每个 Source 实现统一的 `fetch()` 接口：

```python
class Source(ABC):
    @abstractmethod
    def fetch(self, client: BilibiliSession, config: SourceConfig) -> list[Event]:
        """获取事件列表"""
        ...
```

**Source 列表**：

| Source | API 端点 | 说明 |
|--------|---------|------|
| `MsgFeedReplySource` | `/x/msgfeed/reply` | 别人回复我 / 评论我的消息通知流 |
| `MentionMsgFeedSource` | `/x/msgfeed/at` | 别人视频/动态中 @ 我的评论 |
| `OwnVideoCommentSource` | `/x/v2/reply` + 视频列表 | 自己视频下的评论 |
| `OwnDynamicCommentSource` | `/x/v2/reply` + 动态列表 | 自己动态下的评论 |
| `DMSource` | `/x/web-interface/im/msg` | 未读私信 |

### 5.3 Prompt 构建 (`prompt.py`)

Prompt 构建器统一处理评论和私信的 Prompt 生成：

```python
class PromptBuilder:
    def build_comment_prompt(self, event: CommentEvent, config: ReplyConfig) -> str:
        """构建评论回复 Prompt"""
        ...

    def build_dm_prompt(self, event: DMEvent, config: ReplyConfig) -> str:
        """构建私信回复 Prompt"""
        ...
```

**Prompt 组成**：
1. 系统人设（`system_prompt`）
2. 回复风格约束（简短、自然、不机械）
3. 安全约束（不涉政、不涉黄、不引战）
4. 来源类型（评论/私信）
5. 当前事件内容
6. 根评论/父评论上下文（评论场景）
7. 视频/动态摘要（评论场景）
8. 是否 @ 我

---

## 6. 部署指南

### 6.1 系统要求

- Python 3.10+
- Linux / WSL 环境
- 网络连接（访问 Bilibili API 和 AI Provider）

### 6.2 安装步骤

```bash
# 1. 克隆/进入项目目录
cd /path/to/bilibili-bot

# 2. 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制配置模板
cp .env.example .env
cp config/bilibili-cookies.example.txt config/bilibili-cookies.txt

# 5. 编辑配置
nano .env                          # 填入 API Key 和 Refresh Token
nano config/bilibili-cookies.txt   # 填入真实 Cookies
nano config/bot-config.toml        # 调整机器人配置
```

### 6.3 获取 Bilibili Cookies

1. 用浏览器登录 [https://www.bilibili.com](https://www.bilibili.com)
2. 按 F12 打开开发者工具
3. 切换到 **Application** → **Local Storage** → `https://www.bilibili.com`
4. 复制以下 Cookie 值：
   - `SESSDATA`
   - `bili_jct`
   - `DedeUserID`
   - `DedeUserID__ckMd5`

5. 将 Cookies 写入 `config/bilibili-cookies.txt`，格式：
   ```
   SESSDATA=xxx; bili_jct=yyy; DedeUserID=zzz; DedeUserID__ckMd5=www
   ```

### 6.4 获取 Refresh Token

1. 用浏览器登录 [https://www.bilibili.com](https://www.bilibili.com)
2. 按 F12 打开开发者工具
3. 切换到 **Application** → **Local Storage** → `https://www.bilibili.com`
4. 查找 `ac_time_value` 键，复制其值
5. 将值填入 `.env` 文件的 `BILIBILI_REFRESH_TOKEN` 变量

### 6.5 测试运行

```bash
# 查看当前消息流（只读）
python -m bilibili_bot --print-msgfeed

# 执行一轮 dry-run（生成回复但不发送）
python -m bilibili_bot --once --dry-run

# 执行一轮真实自动回复
python -m bilibili_bot --once
```

### 6.6 启动守护模式

**方式一：前台运行（调试用）**
```bash
python -m bilibili_bot
```

**方式二：tmux 后台运行**
```bash
tmux new-session -d -s bilibot
tmux send-keys -t bilibot "python -m bilibili_bot" Enter

# 查看日志
tmux attach -t bilibot

# 停止
tmux kill-session -t bilibot
```

**方式三：systemd 服务（推荐生产环境）**
```bash
# 复制服务单元文件
sudo cp bilibot@.service /etc/systemd/system/

# 编辑服务配置（如果需要）
sudo nano /etc/systemd/system/bilibot@.service

# 重新加载 systemd
sudo systemctl daemon-reload

# 启动服务（替换 <user> 为你的用户名）
sudo systemctl start bilibot@<user>

# 设置开机自启
sudo systemctl enable bilibot@<user>

# 查看状态
sudo systemctl status bilibot@<user>

# 查看日志
journalctl -u bilibot@<user> -f
```

### 6.7 健康检查

如果启用了健康检查服务器（可选）：

```bash
# 默认监听 http://localhost:8080/health
curl http://localhost:8080/health

# 响应示例
{
  "status": "healthy",
  "last_fetch": "2026-05-08T10:30:00Z",
  "last_reply": "2026-05-08T10:25:00Z",
  "replies_today": 15,
  "replies_hourly": 3
}
```

---

## 7. 开发指南

### 7.1 开发环境设置

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装开发依赖
pip install -e ".[dev]"  # 或 pip install -r requirements.txt + 开发工具

# 3. 安装 pre-commit hooks（可选）
pre-commit install
```

### 7.2 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行单个测试文件
python -m pytest tests/test_config.py

# 运行带覆盖率的测试
python -m pytest tests/ --cov=src/bilibili_bot --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 7.3 代码风格

```bash
# 代码格式化
ruff format src/ tests/

# 代码检查
ruff check src/ tests/

# 类型检查（如果使用 mypy）
mypy src/
```

### 7.4 添加新 Source

1. 在 `src/bilibili_bot/sources/` 创建新文件，例如 `new_source.py`
2. 实现 `Source` 抽象基类：
   ```python
   class NewSource(Source):
       def fetch(self, client: BilibiliSession, config: SourceConfig) -> list[Event]:
           # 调用 Bilibili API
           # 归一化为 Event 列表
           ...
   ```
3. 在 `sources/__init__.py` 导出新 Source
4. 在 `config/bot-config.toml` 添加新 Source 配置节
5. 在 `src/bilibili_bot/__main__.py` 注册新 Source 到调度器
6. 编写单元测试 `tests/test_new_source.py`

### 7.5 添加新 Pipeline 阶段

1. 在 `src/bilibili_bot/pipeline/` 创建新文件，例如 `custom_stage.py`
2. 实现 `PipelineStage` 抽象基类：
   ```python
   class CustomStage(PipelineStage):
       def process(self, event: Event, context: PipelineContext) -> StageResult:
           # 处理逻辑
           # 返回 StageResult(action=StageAction.CONTINUE/SKIP/RETRY/STOP)
           ...
   ```
3. 在 `pipeline/__init__.py` 导出新阶段
4. 在 `src/bilibili_bot/__main__.py` 将新阶段插入 Pipeline 链
5. 编写单元测试 `tests/test_custom_stage.py`

### 7.6 调试技巧

**启用调试日志**：
```bash
# 方式一：环境变量
export BILI_BOT_LOG_LEVEL=DEBUG
python -m bilibili_bot

# 方式二：配置文件
# 编辑 config/bot-config.toml
[bot]
log_level = "DEBUG"
```

**dry-run 模式**：
```bash
# 生成回复但不发送
python -m bilibili_bot --once --dry-run
```

**单轮模式**：
```bash
# 只执行一轮，不进入守护循环
python -m bilibili_bot --once
```

**打印事件流**：
```bash
# 查看当前可处理的事件（标准化 JSON 输出）
python -m bilibili_bot --print-msgfeed
```

### 7.7 常见问题

**Q: Cookie 失效怎么办？**

A: 如果配置了 `BILIBILI_REFRESH_TOKEN`，机器人会自动刷新 Cookie。否则需要手动更新 `config/bilibili-cookies.txt`。

**Q: 如何查看机器人状态？**

A: 查看 `data/bot-state.json` 文件，包含最后运行时间、统计信息等。

**Q: 如何重置去重记录？**

A: 删除或清空 `data/processed.jsonl` 文件。

**Q: 如何查看回复历史？**

A: 查看 `data/reply-history.jsonl` 文件，每行是一条回复记录。

---

## 8. 迁移说明

### 8.1 v1 → v2 变更概览

| 方面 | v1 | v2 |
|------|----|----|
| **配置验证** | 手动解析 TOML | Pydantic v2 BaseSettings |
| **HTTP 客户端** | 分散的 requests 调用 | BilibiliSession（Session 子类） |
| **事件模型** | 评论和私信独立结构 | 统一 Event 基类 + 子类 |
| **管道处理** | 评论和私信独立流程 | 统一 Pipeline 链 |
| **去重服务** | comment_dedup + dm_dedup | 单个泛型 DedupService |
| **状态存储** | 无文件锁 | fcntl.flock() + 原子写入 |
| **日志** | logging 基础配置 | structlog 结构化日志 |
| **WBI 签名** | 独立脚本 bilibili_wbi.py | 吸收进 BilibiliSession |
| **测试** | 无/少量测试 | pytest + respx + fixture-based |

### 8.2 配置文件迁移

v2 的配置文件格式与 v1 **向后兼容**，现有 `config/bot-config.toml` 可直接使用。

**新增配置节**：
```toml
# v2 新增：内容安全检查
[content_safety]
enabled = true
sensitive_words_file = "data/sensitive-words.txt"
```

**配置字段重命名**：
- 无（所有 v1 字段保持兼容）

### 8.3 数据文件迁移

**`bot-state.json`**：格式变化，v2 启动时会自动迁移。

**`processed.jsonl`**：格式变化，v2 启动时会自动迁移旧记录。

**`reply-history.jsonl`**：格式不变，可直接使用。

### 8.4 代码迁移（如需保留 v1 代码）

如果需要在 v2 中复用 v1 的某些逻辑：

1. **WBI 签名**：v1 的 `bilibili_wbi.py` 已迁移到 `cli/wbi_tool.py`（独立 CLI）和 `src/bilibili_bot/wbi.py`（库函数）
2. **Cookie 刷新**：v1 的 `cookie_refresh.py` 逻辑已重构到 `src/bilibili_bot/cookie.py`
3. **Prompt 模板**：v1 的 `reply_prompt.py` 和 `dm_prompt.py` 已合并到 `src/bilibili_bot/prompt.py`

### 8.5 删除旧代码

v2 是完全重写，建议删除所有 v1 代码：

```bash
# 删除旧源代码
rm -rf src/bilibili_bot/*.py

# 创建新包结构
mkdir -p src/bilibili_bot/sources
mkdir -p src/bilibili_bot/pipeline
mkdir -p src/bilibili_bot/providers
mkdir -p tests
mkdir -p cli
```

### 8.6 验证清单

迁移完成后，运行以下验证：

```bash
# 1. 所有单元测试通过
python -m pytest tests/

# 2. 完成一轮 dry-run
python -m bilibili_bot --once --dry-run

# 3. 打印事件流（验证 Source 工作）
python -m bilibili_bot --print-msgfeed

# 4. 独立 WBI CLI 工作
python cli/wbi_tool.py BV1xxx

# 5. 无 lint 错误
ruff check src/

# 6. 守护模式启动，优雅处理 SIGTERM
python -m bilibili_bot &
PID=$!
sleep 5
kill -TERM $PID
# 检查 data/bot-state.json 是否正常保存
```

---

## 附录 A：API 端点参考

| 端点 | 方法 | 用途 | WBI |
|------|------|------|-----|
| `/x/msgfeed/reply` | GET | 获取回复消息流 | 是 |
| `/x/msgfeed/at` | GET | 获取 @我消息 | 是 |
| `/x/v2/reply` | GET | 获取评论列表 | 是 |
| `/x/v2/reply/add` | POST | 发送评论 | 是 |
| `/x/web-interface/im/msg` | GET | 获取私信列表 | 是 |
| `/x/web-interface/im/msg/send` | POST | 发送私信 | 是 |
| `/x/web-interface/nav` | GET | 获取用户信息（健康检查） | 否 |
| `/x/web-interface/cookie/refresh` | POST | 刷新 Cookie | 是 |

---

## 附录 B：错误码参考

**Bilibili API 常见错误码**：

| 代码 | 含义 | 处理 |
|------|------|------|
| 0 | 成功 | - |
| -509 | 请求过于频繁 | 退避等待 |
| -101 | 账号未登录 | 刷新 Cookie |
| -403 | 权限不足 | 检查 Cookie 有效性 |
| 12005 | 内容包含敏感词 | 修改回复内容或跳过 |
| 12006 | 评论已发送 | 忽略（视为成功） |

---

## 附录 C：版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.0.0 | 2026-05-08 | 完全重构：统一 Event 模型、Pipeline 架构、Pydantic 配置、文件锁状态存储 |
| 1.0.0 | 2026-05-07 | 初始版本：基础评论/私信自动回复功能 |
