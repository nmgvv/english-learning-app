# 英语学习应用 - 前端架构设计

## 技术选型

| 层级 | 技术选择 | 理由 |
|------|----------|------|
| **后端框架** | FastAPI | 异步、WebSocket 原生支持、已安装 |
| **模板引擎** | Jinja2 | 服务端渲染、首屏快、已安装 |
| **前端交互** | Alpine.js | 轻量级 (15KB)、无构建步骤 |
| **动态更新** | HTMX | 无刷新局部更新 |
| **样式框架** | Tailwind CSS | 原子化 CSS、响应式友好 |
| **音频播放** | Howler.js | 跨浏览器、移动端支持好 |
| **实时通信** | WebSocket | TTS 推送、会话同步 |

---

## 项目目录结构 (简化版)

**核心原则**：最小文件数量，功能按职责划分

```
english-learning-app/
├── server.py                   # FastAPI 入口 + 所有 API 路由
├── dictation.py                # CLI 版本 (保留，FSRS 算法复用)
├── bookmanager.py              # 词书管理 (已有)
├── database.py                 # 数据库模型 + 用户认证 (新增)
│
├── templates/                  # Jinja2 模板 (4个核心页面)
│   ├── base.html               # 基础布局
│   ├── login.html              # 登录页面
│   ├── index.html              # 首页 (词书列表)
│   └── dictation.html          # 听写练习 (核心)
│
├── static/
│   ├── style.css               # 样式 (Tailwind CDN)
│   ├── app.js                  # 所有前端逻辑
│   └── audio/                  # TTS 缓存
│
├── data/                       # 数据目录 (已有)
│   ├── books/
│   ├── progress/               # 保留 JSON 进度 (CLI 兼容)
│   └── app.db                  # SQLite 数据库 (Web 用户数据)
│
├── docs/                       # 文档
│   └── frontend_design.md      # 本文件
│
├── .env
└── requirements.txt
```

**文件数量**：约 10 个核心文件

---

## 页面结构

```
/                           # 首页 - 词书选择
├── /login                  # 登录页面
├── /register               # 注册页面
├── /books                  # 词书列表
├── /book/{book_id}         # 词书详情 - 单元列表
├── /study/today            # 今日学习 (智能推荐)
├── /study/unit/{unit_id}   # 按单元学习
├── /dictation              # 听写练习 (核心页面)
├── /stats                  # 学习统计
└── /settings               # 设置
```

---

## 核心页面：听写练习

```
┌─────────────────────────────────────────┐
│  ←  听写练习        3/20    ⚙️          │  Header
├─────────────────────────────────────────┤
│                                         │
│         【v.】邀请                       │  中文释义
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  i n v i t _                    │   │  输入框
│  └─────────────────────────────────┘   │
│                                         │
│      🔊 听发音    🐢 慢速               │  音频按钮
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  💡 提示: 拼写错误               │   │  提示区
│  └─────────────────────────────────┘   │
│                                         │
├─────────────────────────────────────────┤
│  [确认]           [跳过]                 │  操作按钮
└─────────────────────────────────────────┘
```

---

## API 设计

### 用户认证

```python
POST /api/auth/register           # 用户注册
POST /api/auth/login              # 用户登录 → 返回 JWT
GET  /api/auth/me                 # 获取当前用户信息
```

### 词书管理

```python
GET  /api/books                      # 获取词书列表
GET  /api/books/{book_id}            # 获取词书详情
GET  /api/books/{book_id}/units      # 获取单元列表
```

### 学习会话

```python
POST /api/session/start              # 开始学习会话
     Request:  { book_id, mode, unit?, limit }
     Response: { session_id, total_cards, current_card }

POST /api/session/submit             # 提交答案
     Request:  { session_id, input, attempt }
     Response: { correct, similarity, hint_level, hint, remaining_attempts }

POST /api/session/skip               # 跳过当前词
POST /api/session/end                # 结束会话
```

### 学习数据

```python
GET  /api/progress/{book_id}         # 获取学习进度
GET  /api/due-cards                  # 获取今日待复习
GET  /api/stats                      # 获取学习统计
```

### TTS 音频

```python
GET  /api/tts/{speed}/{word}         # 获取单词发音 (normal/slow)
```

### DeepSeek 集成

```python
POST /api/example-sentence           # 生成例句
```

---

## 数据库设计 (SQLite + SQLAlchemy)

### 用户表 (users)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

### 学习进度表 (progress)

```sql
CREATE TABLE progress (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    book_id VARCHAR(50) NOT NULL,
    word VARCHAR(100) NOT NULL,

    -- FSRS 状态
    difficulty REAL DEFAULT 0.0,
    stability REAL DEFAULT 0.0,
    state INTEGER DEFAULT 0,  -- 0=新卡, 1=学习中, 2=复习中
    reps INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    last_review TIMESTAMP,
    due TIMESTAMP,

    UNIQUE(user_id, book_id, word),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 学习历史表 (history)

```sql
CREATE TABLE history (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    book_id VARCHAR(50) NOT NULL,
    word VARCHAR(100) NOT NULL,

    time TIMESTAMP NOT NULL,
    inputs TEXT,          -- JSON 数组: ["daugter", "daughter"]
    result VARCHAR(20),   -- correct/wrong/skipped
    attempts INTEGER,
    grade INTEGER,        -- FSRS 评分 1-4

    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 用户认证方案

采用 **JWT Token** 认证：

```
注册/登录 → 服务器验证 → 返回 JWT Token
                            ↓
后续请求 → Authorization: Bearer <token> → 验证 Token → 返回数据
```

---

## TTS 音频方案

**预生成 + 缓存方案**

```
用户请求发音 → 服务器检查缓存
                  ├─ 有缓存 → 返回音频 URL
                  └─ 无缓存 → edge-tts 生成 → 保存缓存 → 返回 URL

前端 Howler.js 加载 URL 播放
```

- 词书单词有限 (约 400-600 词/册)，可预生成
- 支持离线缓存 (Service Worker)
- 实现简单，稳定可靠

---

## 移动端适配

| 问题 | 解决方案 |
|------|----------|
| 软键盘遮挡 | `visualViewport` API 动态调整 |
| 点击延迟 | `touch-action: manipulation` |
| 音频自动播放限制 | Howler.js unlockAudio |
| 小屏幕按钮 | 最小 44x44px |

---

## 模块职责

### 1. `server.py` - FastAPI 入口

**职责**:
- 所有 API 路由定义
- 请求处理和响应
- 中间件配置 (CORS, JWT 验证)
- 静态文件和模板服务

**预计行数**: 400-500 行

### 2. `database.py` - 数据库模型 + 认证

**职责**:
- SQLAlchemy 模型定义 (User, Progress, History)
- 数据库连接和初始化
- JWT Token 生成和验证
- 密码哈希工具

### 3. `dictation.py` - CLI 版本 (已有)

**职责**:
- FSRS 间隔重复算法
- 学习会话管理
- TTS 播放 (CLI)
- 用户交互界面 (CLI)
- 学习进度存储

**复用**: Web 版本 import 其 FSRS 算法

### 4. `bookmanager.py` - 词书管理 (已有)

**职责**:
- 词书文件的加载、解析
- 支持多种格式（JSON、TXT）
- 提供统一的单词数据结构
- 词书列表查询

---

## 实现步骤

### Phase 1: 基础框架 + 认证

- 创建 `server.py` FastAPI 入口
- 创建 `database.py` 数据库 + 认证
- 创建 `base.html` 和 `login.html`
- 实现登录/注册 API

### Phase 2: 核心听写功能

- 创建 `index.html` 词书列表
- 创建 `dictation.html` 听写页面
- 实现会话 API (复用 dictation.py 的 FSRS)
- 实现 Alpine.js 交互

### Phase 3: 音频 + DeepSeek

- 实现 TTS 缓存和播放
- 实现 DeepSeek 例句生成

---

## 验证方法

1. 启动服务: `uvicorn server:app --reload`
2. 访问 `http://localhost:8000` 测试页面
3. 测试听写流程: 选词书 → 开始学习 → 输入单词 → 查看提示
4. 测试音频: 点击发音按钮、慢速按钮
5. 测试移动端: Chrome DevTools 设备模拟

---

## 后续细化方向

1. 各步骤的 DeepSeek Prompt 模板设计
2. 异常处理流程（网络错误、API 超时等）
3. PWA 配置（离线支持）
4. 学习统计页面详细设计
