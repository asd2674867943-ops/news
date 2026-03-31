# 📰 每日新闻聚合 · AI 精选

> 自动抓取科技、AI 前沿资讯 + 新闻联播，由 **DeepSeek AI** 智能总结，保存 15 天历史，一键部署到 GitHub Pages。

![预览](https://img.shields.io/badge/部署-GitHub%20Pages-blue)
![自动化](https://img.shields.io/badge/更新-每日自动-green)
![AI](https://img.shields.io/badge/AI-DeepSeek-purple)

---

## ✨ 功能特性

| 功能 | 描述 |
|------|------|
| 📡 **自动抓取** | GitHub Actions 每天两次自动抓取（早 6 点 + 晚 10 点） |
| 🤖 **AI 总结** | DeepSeek API 对每类新闻生成智能摘要 |
| 💻 **科技新闻** | TechCrunch、The Verge、Wired、36氪、虎嗅等 |
| 🤖 **AI 前沿** | 机器之心、量子位、AI Weekly 等 |
| 📺 **新闻联播** | 新华网、央视网、人民网政治要闻 |
| 📅 **历史归档** | 自动保存最近 15 天数据，可按日期切换 |
| 🌐 **GitHub Pages** | 静态页面直接部署，无需服务器 |

---

## 🚀 快速部署

### 第一步：Fork 本仓库

点击右上角 **Fork** 按钮，将仓库 fork 到你的 GitHub 账号。

### 第二步：配置 DeepSeek API Key

1. 前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册并获取 API Key
2. 进入你 Fork 的仓库 → **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**，添加：
   - **Name**: `DEEPSEEK_API_KEY`
   - **Value**: 你的 DeepSeek API Key

### 第三步：启用 GitHub Pages

1. 进入仓库 **Settings** → **Pages**
2. Source 选择 **Deploy from a branch**
3. Branch 选择 `main`，目录选择 `/docs`
4. 点击 **Save**

### 第四步：手动触发首次抓取

1. 进入仓库 **Actions** 标签
2. 选择 **每日新闻抓取** workflow
3. 点击 **Run workflow** → **Run workflow**
4. 等待约 1-2 分钟完成

### 第五步：访问你的新闻站

等 GitHub Pages 部署完成（约 2 分钟），访问：
```
https://你的用户名.github.io/仓库名/
```

---

## ⚙️ 自定义配置

### 修改新闻源

编辑 `scripts/fetch_news.py` 中的 `RSS_SOURCES` 字典：

```python
RSS_SOURCES = {
    "tech": [
        {"name": "来源名称", "url": "RSS链接", "lang": "zh"},
        # 添加更多...
    ],
    "ai": [...],
    "cctv": [...]
}
```

### 修改更新频率

编辑 `.github/workflows/fetch-news.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 22 * * *'  # UTC 22:00 = 北京时间 06:00
  - cron: '0 14 * * *'  # UTC 14:00 = 北京时间 22:00
```

### 修改历史保存天数

编辑 `scripts/fetch_news.py`：
```python
MAX_DAYS = 15  # 改为你想要的天数
```

---

## 📁 项目结构

```
news-aggregator/
├── .github/
│   └── workflows/
│       └── fetch-news.yml      # GitHub Actions 自动任务
├── scripts/
│   └── fetch_news.py           # 新闻抓取 + DeepSeek 总结脚本
├── docs/                       # GitHub Pages 静态文件
│   ├── index.html              # 前端页面
│   └── data/                   # 自动生成的数据目录
│       ├── index.json          # 日期索引
│       └── news_YYYY-MM-DD.json  # 每日数据
└── README.md
```

---

## 🔧 本地运行测试

```bash
# 克隆仓库
git clone https://github.com/你的用户名/news-aggregator.git
cd news-aggregator

# 设置 API Key（可选）
export DEEPSEEK_API_KEY="your_key_here"

# 运行抓取脚本
python scripts/fetch_news.py

# 用浏览器打开 docs/index.html 查看效果
open docs/index.html
```

---

## 📝 数据格式

每日数据保存为 `docs/data/news_YYYY-MM-DD.json`：

```json
{
  "date": "2025-01-01",
  "generated_at": "2025-01-01T06:30:00",
  "categories": {
    "tech": {
      "articles": [...],
      "summary": "DeepSeek 生成的总结文本",
      "count": 25
    },
    "ai": { ... },
    "cctv": { ... }
  }
}
```

---

## 🙋 常见问题

**Q: 新闻抓取失败怎么办？**  
A: 部分 RSS 源可能因网络原因无法访问，GitHub Actions 运行在境外服务器，国内源（36氪、虎嗅等）可能偶有失败。可在 Actions 日志中查看详情。

**Q: DeepSeek 总结为空？**  
A: 请检查 `DEEPSEEK_API_KEY` secret 是否正确配置，账号余额是否充足。

**Q: 如何添加更多 RSS 源？**  
A: 在 `scripts/fetch_news.py` 的 `RSS_SOURCES` 中添加即可，格式参考已有条目。

---

## 📄 License

MIT License
