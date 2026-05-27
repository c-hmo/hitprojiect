import os
import json
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import requests
from bs4 import BeautifulSoup

AI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")     
SENDER_PASS = os.getenv("SENDER_PASS")       
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL") 

HISTORY_FILE = "history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def update_and_get_streak(repo_name, history, today_str):
    today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    
    if repo_name in history:
        last_seen_str = history[repo_name]["last_seen"]
        last_seen_date = datetime.strptime(last_seen_str, "%Y-%m-%d").date()
        
        if last_seen_date == today_date - timedelta(days=1):
            streak = history[repo_name]["streak"] + 1
        elif last_seen_date == today_date:
            streak = history[repo_name]["streak"] 
        else:
            streak = 1 
    else:
        streak = 1
        
    history[repo_name] = {"streak": streak, "last_seen": today_str}
    return streak

def get_ai_desc(repo_name, raw_desc):
    if not AI_API_KEY or AI_API_KEY == "123": 
        return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> 暂无配置 AI 解析。"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={AI_API_KEY}"
    prompt = (
        f"请用中文精炼分析 GitHub 项目 '{repo_name}'。\n原始英文简介：{raw_desc}\n\n"
        f"请严格用 HTML 换行符 <br> 分隔返回两行（勿用Markdown星号）：\n"
        f"<b>【是什么】</b>[一句话大白话解释它是干嘛的]\n"
        f"<b>【怎么用】</b>[核心功能或适用场景]"
    )
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            print(f"⚠️ 谷歌大模型报错啦: {data}")
            return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> AI 接口返回异常，请查看 Actions 日志。"
    except Exception as e:
        print(f"❌ 网络请求报错: {e}")
        return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> AI 网络超时。"

def fetch_list(url_suffix, section_title, history, today_str, max_items=5):
    url = f'https://github.com/trending{url_suffix}'
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    articles = soup.find_all('article', class_='Box-row')
    
    html_items = f"""
    <div style="background-color: #f6f8fa; padding: 10px 15px; border-left: 5px solid #d73a49; margin: 30px 0 15px 0;">
        <h2 style="color: #24292e; margin: 0; font-size: 18px;">{section_title}</h2>
    </div>
    """
    
    for idx, article in enumerate(articles[:max_items], 1):
        title_box = article.find('h2', class_='h3')
        name = "".join(title_box.text.split()) if title_box else "Unknown"
        desc_box = article.find('p', class_='col-9')
        raw_desc = desc_box.text.strip() if desc_box else "No description available"
        
        streak = update_and_get_streak(name, history, today_str)
        streak_badge = f"<span style='background:#ffd33d; color:#24292e; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:bold; margin-left:10px; vertical-align: middle;'>🔥 连续上榜 {streak} 天</span>" if streak > 1 else ""
        
        print(f"正在处理: {name} (连榜: {streak})")
        ai_analysis = get_ai_desc(name, raw_desc)
        
        # 究极护盾：强制休息 15 秒！完美破解谷歌的“1分钟5次”限流魔法
        time.sleep(15) 
        
        html_items += f"""
        <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eaecef;">
            <h3 style="color: #0366d6; margin-bottom: 8px; font-size: 16px;">
                {idx}. <a href="https://github.com/{name}" style="color: #0366d6; text-decoration: none;">{name}</a>
                {streak_badge}
            </h3>
            <div style="color: #24292e; background: #fafbfc; padding: 12px; border-radius: 6px; border: 1px solid #e1e4e8; margin: 5px 0; font-size: 14px; line-height: 1.6;">
                {ai_analysis}
            </div>
        </div>
        """
    return html_items

def send_email_report():
    today_str = datetime.now().strftime("%Y-%m-%d")
    history = load_history()
    
    daily_html = fetch_list("?since=daily", "🚀 今日飙升榜 (Daily)", history, today_str, 5)
    weekly_html = fetch_list("?since=weekly", "🌟 本周热门榜 (Weekly)", history, today_str, 5)
    
    save_history(history)
    
    email_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 650px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #24292e; border-bottom: 2px solid #0076ff; padding-bottom: 10px; text-align: center;">📊 GitHub 技术情报局</h1>
        <p style="text-align: center; color: #586069; font-size: 14px;">{today_str} · AI 深度提炼版</p>
        {daily_html}
        {weekly_html}
    </body>
    </html>
    """

    print("准备发送邮件...")
    msg = MIMEText(email_content, 'html', 'utf-8')
    msg['From'] = formataddr((Header("GitHub 情报局", 'utf-8').encode(), SENDER_EMAIL))
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = Header(f"🚀 {today_str} GitHub 飙升与热门项目送达！", 'utf-8')

    try:
        smtp_server = "smtp.qq.com" 
        port = 465 
        server = smtplib.SMTP_SSL(smtp_server, port) 
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], msg.as_string())
        server.quit()
        print("🎉 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    send_email_report()
