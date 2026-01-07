
# 📺 Bili-WTF-Monitor (B站纯问号浓度监控系统)

> **"当满屏都是 '?' 的时候，我就知道这个视频不简单。"**

这是一个**全自动化的 B 站“迷惑行为”猎手**。它24小时巡逻各大分区，实时分析视频弹幕中的“问号浓度”，捕捉那些让观众全员懵逼的“名场面”。

系统集成了**数据抓取、Protobuf底层解析、自动归档、Web可视化看板、以及 GitHub Pages 自动部署**的全栈能力。

🌐 **Live Demo (演示站点)**: [wtf.hicatalpa.cn](https://wtf.hicatalpa.cn)



---

## ✨ 核心特性

1.  **🧪 硬核解析**：不依赖庞大的库，手搓 Protobuf 解析器，直接从二进制流中提取弹幕，精准识别 `?` 和 `？`。
2.  **🌗 赛博看板**：
    * **自适应主题**：支持深色/浅色模式（跟随系统）。
    * **时光机**：内置日历控件，可回溯查看任意历史日期的榜单存档。
    * **瀑布流**：精致的 CSS Grid 布局，完美复刻 B 站 UI 风格。
3.  **🤖 自动化运维**：
    * **双进程架构**：爬虫负责抓数据，同步脚本负责推送到 GitHub。
    * **每日快照**：自动生成每日 JSON 存档，并建立索引。
    * **CNAME 支持**：自动维护自定义域名配置。

---

## 🚀 快速开始 (Deployment)

### 1. 环境准备
确保你的环境已安装 Python 3.8+ 和 Git。
```bash
git clone [https://github.com/YourUsername/Bili-WTF-Monitor.git](https://github.com/YourUsername/Bili-WTF-Monitor.git)
cd Bili-WTF-Monitor
pip install requests brotli user-agent qrcode

```

### 2. 核心配置 (⚠️ 重要)

在运行前，请务必修改以下文件以适配你的环境：

#### 修改 `git_sync.py`

打开 `git_sync.py`，找到开头的配置区，填入你的 GitHub 仓库地址：

```python
# [初始化] 请将下方链接替换为你的 GitHub 仓库地址
REPO_URL = "[https://github.com/你的用户名/你的仓库名.git](https://github.com/你的用户名/你的仓库名.git)"

# [初始化] 目标分支，通常为 gh-pages
TARGET_BRANCH = "gh-pages"

```

#### 修改 `CNAME` (可选)

如果你想使用自定义域名（GitHub Pages），请修改 `CNAME` 文件：

```text
your.custom.domain.com

```

*如果不使用自定义域名，请直接删除此文件。*

### 3. 隐私检查 (Security Check)

**非常重要**：请确保项目根目录下存在 `.gitignore` 文件，且包含以下内容，防止你的 B 站 Cookie 泄露：

```text
cookies.json
__pycache__/
*.pyc
venv/

```

### 4. 启动系统

#### 第一步：账号授权

运行登录脚本，扫码登录 B 站（获取 `cookies.json`）：

```bash
python login.py

```

#### 第二步：双进程启动

你需要打开两个终端窗口（或使用 screen/tmux）分别运行：

**窗口 A：启动爬虫** (负责抓取数据)

```bash
python bili_monitor.py

```

**窗口 B：启动同步** (负责上传到 GitHub)

```bash
python git_sync.py

```

---

## 📂 文件结构说明

| 文件名            | 作用                                                         |
| ----------------- | ------------------------------------------------------------ |
| `bili_monitor.py` | **主程序**。负责爬虫、数据分析、本地 Web 服务。              |
| `git_sync.py`     | **同步助手**。负责数据归档、自动 Commit 并**强推**到 GitHub。 |
| `login.py`        | **登录脚本**。扫码获取 Cookie，用于过 B 站风控。             |
| `index.html`      | **前端看板**。单页应用，包含所有 UI 和交互逻辑。             |
| `.gitignore`      | **安全锁**。防止 `cookies.json` 等敏感文件被上传。           |
| `CNAME`           | **域名配置**。用于 GitHub Pages 的自定义域名。               |

---

## ⚠️ 常见问题

1. **图片加载失败？**

* B 站图片有防盗链机制，`index.html` 头部必须包含 `<meta name="referrer" content="no-referrer">`。


2. **风控 (412/403错误)**

* 如果日志中频繁出现错误，请重新运行 `python login.py` 更新 Cookie。



---

## 📜 免责声明

本项目仅供 Python 编程学习与数据分析研究使用。请严格遵守 [Bilibili 用户协议](https://www.bilibili.com/protocal/licence.html) 及 [Robots 协议](https://www.bilibili.com/robots.txt)。严禁将本项目用于任何商业用途、恶意抓取或网络攻击。


