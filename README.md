# 🚀 GitHub 极客情报局 (AI 驱动版)

自动化抓取 GitHub 每日/每周热门项目，使用 Google Gemini API 提取核心功能与配置需求，并带有**上榜连击统计**和**智能缓存机制**，最终推送至你的个人邮箱。

## 🎯 核心功能
* **按需抓取**：固定抓取 8 个周热门项目和 12 个日飙升项目。
* **AI 智能提炼**：通过大模型直击核心，提取【它是干嘛的】和【配置需要啥】。
* **连榜统计**：记录项目连续霸榜天数。
* **智能护航**： 
    * **历史缓存复用**：出现过的项目不再调用 AI，极致节省 API Token。
    * **限流保护**：每次调用 API 后强制冷却 5 秒，防止触发 Google 的防滥用风控机制。

## ⚙️ 如何配置 (Secrets 设定)

为了让 GitHub Actions 正常工作，你需要前往当前仓库的 **Settings** -> **Secrets and variables** -> **Actions**，新建以下 4 个 `Repository secrets`：

| Secret 名称 | 说明 |
| :--- | :--- |
| `GEMINI_API_KEY` | 你的 Google AI Studio API 密钥 |
| `SENDER_EMAIL` | 用于发件的邮箱账号 (如 `your-email@qq.com`) |
| `SENDER_PASS` | 发件邮箱的 SMTP 授权码 (注意不是登录密码) |
| `RECEIVER_EMAIL` | 接收这份情报邮件的邮箱 |

## 🛠️ 本地运行测试
```bash
pip install requests beautifulsoup4 google-generativeai
# 设置好环境变量后运行
python main.py
