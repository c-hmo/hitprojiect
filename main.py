import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import requests
from bs4 import BeautifulSoup

AI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")     
SENDER_PASS = os.getenv("SENDER_PASS")       
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL") 

def get_ai_desc(repo_name, raw_desc):
    # 如果没有配置真实的 API Key，返回原始简介
    if not AI_API_KEY or AI_API_KEY == "123": 
        return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> 暂无配置 AI 解析。"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={AI_API_KEY}"
    
    prompt = (
        f"请用中文精炼分析 GitHub 热门项目 '{repo_name}'。\n"
        f"项目的原始英文简介为：{raw_desc}\n\n"
        f"请严格按照以下格式用 HTML 换行符 <br> 分隔返回两行内容（不要包含 Markdown 的加粗星号或任何其他修饰）：\n"
        f"<b>【是什么】</b>[用一句话大白话解释它是干嘛的，解决了什么核心痛点]\n"
        f"<b>【怎么用】</b>[简要说明它怎么用，或者它的核心功能、适用场景是什么]"
    )
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        data = res.json()
        
        # 增加一道防线：看看谷歌到底返回了什么
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            print(f"⚠️ 谷歌大模型报错啦: {data}")
            return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> AI 接口返回异常，请查看日志。"
    except Exception as e:
        print(f"❌ AI 解析网络出错: {e}")
        return f"<b>【是什么】</b> {raw_desc}<br><b>【怎么用】</b> AI 提炼时发生网络波动。"

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
        raw_desc = desc_box.text.strip() if desc_box else "No description available"
        
        print(f"正在处理: {name}")
        ai_analysis = get_ai_desc(name, raw_desc)
        
        html_items += f"""
        <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eaecef;">
            <h3 style="color: #0366d6; margin-bottom: 8px;">
                {idx}. <a href="https://github.com/{name}" style="color: #0366d6; text-decoration: none;">{name}</a>
            </h3>
            <div style="color: #24292e; background: #f6f8fa; padding: 12px; border-left: 4px solid #0076ff; margin: 5px 0; font-size: 14px; line-height: 1.6;">
                {ai_analysis}
            </div>
            <p style="color: #6a737d; font-size: 12px; margin: 5px 0;">📝 项目原话：<i>{raw_desc}</i></p>
        </div>
        """

    email_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #24292e; border-bottom: 2px solid #0076ff; padding-bottom: 10px;">📊 GitHub 今日飙升黑马项目 (AI 深度提炼版)</h2>
        {html_items}
    </body>
    </html>
    """

    print("准备发送邮件...")
    msg = MIMEText(email_content, 'html', 'utf-8')
    msg['From'] = formataddr((Header("GitHub 情报局", 'utf-8').encode(), SENDER_EMAIL))
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = Header("🚀 您的专属 AI 技术情报已送达！", 'utf-8')

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
