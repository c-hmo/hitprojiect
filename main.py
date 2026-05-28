import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import google.generativeai as genai

# ==========================================
# 1. 基础配置与安全密钥读取
# ==========================================
# 从 GitHub Secrets 中安全读取两把钥匙
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

if not GEMINI_API_KEY:
    raise ValueError("❌ 错误：未在 GitHub Secrets 中找到 GEMINI_API_KEY")
if not EMAIL_PASSWORD:
    raise ValueError("❌ 错误：未在 GitHub Secrets 中找到 EMAIL_PASSWORD")

# 配置 Gemini 模型 (使用高性价比的 1.5-flash)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

CACHE_FILE = 'translation_cache.json'
today_str = datetime.now().strftime("%Y-%m-%d")

# 定向配置收发件邮箱
SENDER_EMAIL = "2757467386@qq.com" 
RECEIVER_EMAIL = "c-hmo@outlook.com"
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465 

# ==========================================
# 2. 抓取 GitHub 榜单数据 (15热门 + 20飙升)
# ==========================================
print("📡 正在向 GitHub 全速抓取数据...")
today_35_projects = []
recent_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
headers = {"Accept": "application/vnd.github.v3+json"}

# 抓取 15 个全站热门项目
url_trending = "https://api.github.com/search/repositories?q=stars:>5000&sort=updated&order=desc&per_page=15"
try:
    res_trending = requests.get(url_trending, headers=headers).json()
    if 'items' in res_trending:
        for item in res_trending['items']:
            today_35_projects.append({
                'repo_name': item['full_name'],
                'description': item['description'] or "No description provided.",
                'url': item['html_url'],
                'category': '🔥 热门推荐'
            })
except Exception as e:
    print(f"⚠️ 热门项目抓取异常: {e}")

# 抓取 20 个近期飙升项目
url_rising = f"https://api.github.com/search/repositories?q=created:>{recent_date}&sort=stars&order=desc&per_page=20"
try:
    res_rising = requests.get(url_rising, headers=headers).json()
    if 'items' in res_rising:
        for item in res_rising['items']:
            today_35_projects.append({
                'repo_name': item['full_name'],
                'description': item['description'] or "No description provided.",
                'url': item['html_url'],
                'category': '🚀 近期飙升'
            })
except Exception as e:
    print(f"⚠️ 飙升项目抓取异常: {e}")

print(f"📊 成功获取 {len(today_35_projects)} 个项目，准备进入记忆防御引擎...")

# ==========================================
# 3. 核心省钱护城河 (历史缓存比对 & 动态计天)
# ==========================================
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
else:
    cache_data = {}

final_email_projects = []

for project in today_35_projects:
    repo_name = project['repo_name']
    original_desc = project['description']
    
    days_on_list = 1
    
    # 💰 检查缓存：如果项目之前出现过
    if repo_name in cache_data:
        print(f"✅ 命中缓存 (⚡ 0 Token 消耗): {repo_name}")
        translated_desc = cache_data[repo_name]['translation']
        # 在昨天的天数基础上 +1
        days_on_list = cache_data[repo_name].get('days_on_list', 1) + 1
    else:
        # 如果是新项目，调用 Gemini 翻译
        print(f"✨ 发现新项目 (💸 消耗 Token 翻译): {repo_name}")
        try:
            prompt = f"请将以下 GitHub 开源项目的英文简介翻译成中文，要求通顺且专业。简介：{original_desc}"
            response = model.generate_content(prompt)
            translated_desc = response.text.strip()
        except Exception as e:
            print(f"⚠️ Gemini 翻译失败 {repo_name}: {e}")
            translated_desc = original_desc 
            
    # 将今天的最新状态写入缓存缓存（供明天对比）
    cache_data[repo_name] = {
        'translation': translated_desc,
        'days_on_list': days_on_list,
        'last_seen': today_str
    }
    
    final_email_projects.append({
        'repo_name': repo_name,
        'category': project['category'],
        'description': translated_desc,
        'url': project['url'],
        'days_on_list': days_on_list
    })

# 下班前，将最新的记忆本地持久化
with open(CACHE_FILE, 'w', encoding='utf-8') as f:
    json.dump(cache_data, f, ensure_ascii=False, indent=2)
print("💾 翻译数据与霸榜天数缓存同步成功！")

# ==========================================
# 4. 自动化构建精美 HTML 邮件并发送
# ==========================================
print("📧 正在组装全量数据日报...")

html_content = f"""
<div style="font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; max-width: 750px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #24292e; border-bottom: 1px solid #e1e4e8; padding-bottom: 10px;">🚀 GitHub 每日开源趋势情报局 ({today_str})</h2>
    <p style="color: #586069; font-size: 14px;">今日共为您锁定 35 个全站顶尖项目，老项目已为您自动引用历史翻译并更新连榜天数。</p>
"""

for p in final_email_projects:
    # 动态渲染天数标签样式
    badge_style = "background-color: #ffd33d; color: #24292e;" if p['days_on_list'] > 1 else "background-color: #28a745; color: #fff;"
    badge_text = f"🔥 连续霸榜 {p['days_on_list']} 天" if p['days_on_list'] > 1 else "✨ 今日新上榜"

    html_content += f"""
    <div style="margin-bottom: 15px; padding: 15px; border: 1px solid #e1e4e8; border-radius: 6px; background-color: #fff;">
        <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px;">
            <a href="{p['url']}" style="text-decoration: none; color: #0366d6;">{p['repo_name']}</a>
        </h3>
        <div style="margin-bottom: 10px; font-size: 12px;">
            <span style="padding: 3px 6px; border-radius: 3px; background-color: #f1f8ff; color: #0366d6; font-weight: bold; margin-right: 5px;">{p['category']}</span>
            <span style="padding: 3px 6px; border-radius: 3px; font-weight: bold; {badge_style}">{badge_text}</span>
        </div>
        <p style="margin: 0; font-size: 14px; color: #24292e; line-height: 1.5;">
            <b>中文简介：</b>{p['description']}
        </p>
    </div>
    """

html_content += "</div>"

# 配置邮件传输协议对象
msg = MIMEMultipart()
msg['From'] = SENDER_EMAIL
msg['To'] = RECEIVER_EMAIL
msg['Subject'] = f"🚀 GitHub 趋势日报：35个顶尖项目情报 ({today_str})"
msg.attach(MIMEText(html_content, 'html', 'utf-8'))

try:
    print("📡 正在连接 QQ 邮箱安全安全加密服务器...")
    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(SENDER_EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("🎉 完美成功！35个项目的全量中英日报已顺利投递至 c-hmo@outlook.com！")
except Exception as e:
    print(f"❌ 邮件投递遇到不可抗力阻碍: {e}")
