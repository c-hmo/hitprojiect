import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
from google.genai import types

# 配置区
HISTORY_FILE = "history.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASS = os.environ.get("SENDER_PASS")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

def get_github_trending(since, limit):
    """抓取 GitHub Trending"""
    url = f"https://github.com/trending?since={since}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    print(f"开始抓取榜单: {since} (目标: {limit}个)...")
    repos = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('article', class_='Box-row')
        
        for repo in articles[:limit]:
            name_tag = repo.find('h2', class_='h3 lh-condensed')
            name = "".join(name_tag.text.split()) if name_tag else "Unknown"
            
            desc_tag = repo.find('p')
            desc = desc_tag.text.strip() if desc_tag else "暂无描述"
            
            repos.append({
                "name": name,
                "url": f"https://github.com/{name}",
                "description": desc
            })
    except Exception as e:
        print(f"抓取 {since} 失败: {e}")
    return repos

def call_gemini_with_retry(name, description):
    """调用 Gemini API (使用最新的 google-genai 库) 并严格限制频率防封"""
    if not GEMINI_API_KEY:
        return {"what_it_does": "未配置API Key", "configuration": "未配置API Key"}
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    分析以下GitHub项目：
    项目名：{name}
    原描述：{description}

    请用中文简明扼要地总结：
    1. 它是干嘛的（核心功能）
    2. 配置它需要些啥（运行环境、语言、依赖、硬件要求等）

    必须返回严格的JSON格式，包含两个键："what_it_does" 和 "configuration"
    不要返回 ```json 这种markdown标记，只返回纯JSON字符串。
    """
    
    for attempt in range(3):
        try:
            print(f"[{name}] 请求 Gemini API...")
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            # 解析返回的 JSON 文本
            return json.loads(response.text.strip())
        except Exception as e:
            print(f"请求失败 (尝试 {attempt+1}/3): {e}")
            time.sleep(10) # 失败重试时休息更久
            
    return {"what_it_does": "AI提取失败", "configuration": "AI提取失败"}

def process_repos(hot_repos, surging_repos):
    """处理历史记录、缓存复用、计算上榜天数"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 增加容错机制：尝试加载 JSON，如果文件为空或格式错误，则使用默认结构
    db = {"last_run_date": "", "repos": {}}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:  # 确保文件不是完全空白的
                    db = json.loads(content)
        except json.JSONDecodeError:
            print("⚠️ history.json 格式错误或为空，已自动初始化为默认结构。")

    all_current_repos = hot_repos + surging_repos
    is_new_day = (db.get("last_run_date") != today_str)

    # 确保 db 中有 repos 键
    if "repos" not in db:
        db["repos"] = {}

    for repo in all_current_repos:
        name = repo["name"]
        
        # 1. 计算连榜天数 (Streak)
        if name in db["repos"]:
            last_seen = db["repos"][name].get("last_seen_date", "")
            current_streak = db["repos"][name].get("streak", 1)
            
            if is_new_day and last_seen == yesterday_str:
                repo["streak"] = current_streak + 1
            elif not is_new_day:
                repo["streak"] = current_streak
            else:
                repo["streak"] = 1 
        else:
            repo["streak"] = 1

        # 2. 获取 AI 总结 (Token 节约机制)
        if name in db["repos"] and "summary" in db["repos"][name]:
            print(f"[{name}] 命中历史缓存！直接复用内容，节省 Token。")
            repo["summary"] = db["repos"][name]["summary"]
        else:
            repo["summary"] = call_gemini_with_retry(name, repo["description"])
            # 成功调用API后，强制休眠 5 秒防封
            time.sleep(5)
            
        # 3. 更新数据库内容
        db["repos"][name] = {
            "streak": repo["streak"],
            "last_seen_date": today_str,
            "summary": repo["summary"]
        }

    # 保存历史记录
    db["last_run_date"] = today_str
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    return hot_repos, surging_repos

def build_html_email(hot_repos, surging_repos):
    """构建精美邮件 HTML"""
    def build_cards(repos, badge_color, badge_text):
        html = ""
        for repo in repos:
            streak = repo.get('streak', 1)
            streak_badge = f'<span style="background:{badge_color}; color:#fff; padding:2px 6px; border-radius:4px; font-size:12px;">上榜 {streak} 天</span>'
            html += f"""
            <div style="border:1px solid #ddd; padding:15px; margin-bottom:15px; border-radius:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <a href="{repo['url']}" style="font-size:18px; font-weight:bold; color:#0366d6; text-decoration:none;" target="_blank">{repo['name']}</a>
                    {streak_badge}
                </div>
                <div style="margin-top:10px; background:#f6f8fa; padding:10px; border-radius:6px; font-size:14px; line-height:1.6; color:#24292e;">
                    <strong>🎯 它是干嘛的：</strong><br>{repo['summary'].get('what_it_does', '暂无')}<br><br>
                    <strong>⚙️ 配置需要啥：</strong><br>{repo['summary'].get('configuration', '暂无')}
                </div>
            </div>
            """
        return html

    return f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #d73a49; border-bottom: 2px solid #d73a49; padding-bottom: 5px;">🔥 本周热门项目 (Top 8)</h2>
        {build_cards(hot_repos, "#d73a49", "🔥 热门连续")}
        
        <h2 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 5px; margin-top:30px;">🚀 24小时飙升项目 (Top 12)</h2>
        {build_cards(surging_repos, "#28a745", "🚀 飙升连续")}
        
        <div style="text-align: center; margin-top: 30px; font-size: 12px; color: #888;">
            由 GitHub Actions 与 Gemini API 强力驱动 | 智能缓存已开启
        </div>
    </body>
    </html>
    """

def send_email(html_content):
    if not (SENDER_EMAIL and SENDER_PASS and RECEIVER_EMAIL):
        print("未配置邮件环境变量，跳过发送。")
        return
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🚀 GitHub 极客情报: 热门与飙升项目 AI 总结 ({datetime.now().strftime('%m-%d')})"
    msg['From'] = f"GitHub Trends <{SENDER_EMAIL}>"
    msg['To'] = RECEIVER_EMAIL
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        domain = SENDER_EMAIL.split('@')[-1].lower()
        if 'qq.com' in domain:
            server = smtplib.SMTP_SSL('smtp.qq.com', 465)
        elif 'gmail.com' in domain:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
        else:
            server = smtplib.SMTP('smtp.office365.com', 587) # Outlook
            server.starttls()
            
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    print("=== GitHub AI 情报站启动 ===")
    hot_repos = get_github_trending("weekly", 8)
    surging_repos = get_github_trending("daily", 12)
    
    hot_repos, surging_repos = process_repos(hot_repos, surging_repos)
    
    html = build_html_email(hot_repos, surging_repos)
    send_email(html)
    print("=== 任务全部完成 ===")
