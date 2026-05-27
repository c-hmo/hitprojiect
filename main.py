import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import requests
from bs4 import BeautifulSoup

AI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")     
SENDER_PASS = os.getenv("SENDER_PASS")       
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL") 

def get_ai_desc(repo_name, raw_desc):
    # 如果没有配置 API Key，直接返回原始简介
    if not AI_API_KEY or AI_API_KEY == "123": 
        return raw_desc
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={AI_API_KEY}"
    prompt = f"请用一句话中文大白话解释 GitHub 项目 '{repo_name}' 是干嘛的，解决了什么痛点。原简介：{raw_desc}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return raw_desc

def send_email_report():
    print("开始抓取 GitHub Trending...")
    url = 'https://github.com/trending'
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    articles = soup.find_all('article', class_='Box-row')
    
    html_items = ""
    for idx, article in enumerate(articles[:5], 1):
        title_box = article.find('h2', class_='h3')
        name = "".join(title_box.text.split()) if title_box else "Unknown"
        desc_box = article.find('p', class_='col-9')
        raw_desc = desc_box.text.strip() if desc_box else "No description"
        
        print(f"正在处理: {name}")
        ai_desc = get_ai_desc(name, raw_desc)
        
        html_items += f"""
        <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eaecef;">
            <h3 style="color: #0366d6; margin-bottom: 5px;">
                {idx}. <a href="https://github.com/{name}" style="color: #0366d6; text-decoration: none;">{name}</a>
            </h3>
            <p style="color: #24292e; font-weight: bold; margin: 5px 0;">💡 核心亮点：</p>
            <p style="color: #24292e; background: #f6f8fa; padding: 10px; border-left: 4px solid #0076ff; margin: 5px 0;">{ai_desc}</p>
            <p style="color: #586069; font-size: 13px; margin: 5px 0;">📝 原始简介：<i>{raw_desc}</i></p>
        </div>
        """

    email_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #24292e; border-bottom: 2px solid #0076ff; padding-bottom: 10px;">📊 GitHub 今日飙升黑马项目</h2>
        {html_items}
    </body>
    </html>
    """

    print("准备发送邮件...")
    msg = MIMEText(email_content, 'html', 'utf-8')
    msg['From'] = Header(f"GitHub 情报局 <{SENDER_EMAIL}>")
    msg['To'] = Header(RECEIVER_EMAIL)
    msg['Subject'] = Header("🚀 今天的 GitHub 飙升项目已经送达！", 'utf-8')

    try:
        # QQ 或 163 邮箱的专用发信配置 (SMTP_SSL)
        smtp_server = "smtp.qq.com"  # 默认使用 QQ 邮箱
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
