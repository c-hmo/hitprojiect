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
            desc = desc_tag.text.strip() if desc_tag else "No description provided."
            
            repos.append({
                "name": name,
                "url": f"https://github.com/{name}",
                "description": desc
            })
    except Exception as e:
        print(f"抓取 {since} 失败: {e}")
    return repos

def batch_call_gemini(repos_to_process):
    """【核心优化】将所有需要翻译的项目打包，一次性请求 API，彻底解决并发超限"""
    if not GEMINI_API_KEY or not repos_to_process:
        return {}
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 构造输入数据映射表
    input_data = {}
    for repo in repos_to_process:
        input_data[repo["name"]] = repo["description"]
        
    prompt = f"""
    你需要分析以下一组 GitHub 项目，并为每个项目生成中文总结。

    项目输入（JSON格式，键为项目名，值为原英文描述）：
    {json.dumps(input_data, ensure_ascii=False)}

    请为每个项目用中文简明扼要地总结：
    1. 它是干嘛的（核心功能）
    2. 配置它需要些啥（运行环境、语言、依赖、硬件要求等）

    你必须返回一个严格的 JSON 对象。键必须与输入的项目名完全一致。
    格式示例：
    {{
        "owner/repo1": {{
            "what_it_does": "核心功能...",
            "configuration": "配置需求..."
        }},
        "owner/repo2": {{
            "what_it_does": "核心功能...",
            "configuration": "配置需求..."
        }}
    }}
    只返回纯 JSON，不要 markdown 标记。
    """
    
    for attempt in range(3):
        try:
            print(f"🚀 正在批量打包请求 Gemini API ({len(repos_to_process)}个项目同时处理)...")
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            # 解析并返回包含所有项目的大字典
            return json.loads(response.text.strip())
        except Exception as e:
            print(f"批量请求失败 (尝试 {attempt+1}/3): {e}")
            time.sleep(15) 
            
    return {}

def process_repos(hot_repos, surging_repos):
    """处理历史记录、缓存复用、计算上榜天数及批量 AI 请求"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    db = {"last_run_date": "", "repos": {}}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    db = json.loads(content)
        except json.JSONDecodeError:
            print("⚠️ history.json 格式错误或为空，已自动初始化。")

    all_current_repos = hot_repos + surging_repos
    is_new_day = (db.get("last_run_date") != today_str)

    if "repos" not in db:
        db["repos"] = {}

    repos_needing_summary = []

    # 第一轮遍历：计算天数，挑出需要 AI 处理的“新项目”
    for repo in all_current_repos:
        name = repo["name"]
        
        # 1. 计算连榜天数
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

        # 2. 检查缓存
        is_valid_cache = False
        if name in db["repos"] and "summary" in db["repos"][name]:
            cached_summary = db["repos"][name]["summary"]
            if "AI提取失败" not in cached_summary.get("what_it_does", ""):
                is_valid_cache = True

        if is_valid_cache:
            print(f"[{name}] 命中历史缓存！直接复用，免去请求。")
            repo["summary"] = db["repos"][name]["summary"]
        else:
            # 没命中缓存的，扔进“待处理打包清单”
            repos_needing_summary.append(repo)

    # 第二轮：批量处理清单里的项目（一次 API 请求搞定全部！）
    if repos_needing_summary:
        print(f"\n📦 共收集到 {len(repos_needing_summary)} 个新项目，准备进行 1 次批量 API 请求...")
        batch_results = batch_call_gemini(repos_needing_summary)
        
        # 将批量结果拆解发给各自的项目
        for repo in repos_needing_summary:
            name = repo["name"]
            if name in batch_results:
                repo["summary"] = batch_results[name]
            else:
                repo["summary"] = {"what_it_does": "AI提取失败", "configuration": "AI提取失败"}
    else:
        print("\n🎉 今天所有的项目都在缓存里，无需调用任何 API！")

    # 第三轮：统一步伐，更新数据库
    for repo in all_current_repos:
        db["repos"][repo["name"]] = {
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
                
                <div style="margin-top:10px; font-size:14px; color:#586069; font-style:italic;">
                    "{repo['description']}"
                </div>
                
                <div style="margin-top:12px; background:#f6f8fa; padding:12px; border-radius:6px; font-size:14px; line-height:1.6; color:#24292e; border-left: 4px solid #0366d6;">
                    <strong>🎯 它是干嘛的：</strong><br>{repo['summary'].get('what_it_does', '暂无')}<br><br>
                    <strong>⚙️ 配置需要啥：</strong><br>{repo['summary'].get('configuration', '暂无')}
                </div>
            </div>
            """
        return html

    return f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #d73a49; border-bottom: 2px solid #d73a49; padding-bottom: 5px;">🔥 本周热门项目 (Top 8)</h2>
        {build_cards(hot_repos, "#d73a49", "🔥 热门连续")}
        
        <h2 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 5px; margin-top:30px;">🚀 24小时飙升项目 (Top 12)</h2>
        {build_cards(surging_repos, "#28a745", "🚀 飙升连续")}
        
        <div style="text-align: center; margin-top: 30px; font-size: 12px; color: #888;">
            由 GitHub Actions 与 Gemini API 强力驱动 | 全新极速批处理架构
        </div>
    </body>
    </html>
    """

def send_email(html_content):
    if not (SENDER_EMAIL and SENDER_PASS and RECEIVER_EMAIL):
        print("未配置邮件环境变量，跳过发送。")
        return
        
    # 【核心修改】将逗号分隔的字符串切割成邮箱列表，并自动去除多余空格
    receiver_list = [email.strip() for email in RECEIVER_EMAIL.split(',')]
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🚀 GitHub 极客情报: 热门与飙升项目 AI 总结 ({datetime.now().strftime('%m-%d')})"
    msg['From'] = f"GitHub Trends <{SENDER_EMAIL}>"
    msg['To'] = RECEIVER_EMAIL  # 邮件头上显示的收件人可以直接用原字符串
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        domain = SENDER_EMAIL.split('@')[-1].lower()
        if 'qq.com' in domain:
            server = smtplib.SMTP_SSL('smtp.qq.com', 465)
        elif 'gmail.com' in domain:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
        else:
            server = smtplib.SMTP('smtp.office365.com', 587)
            server.starttls()
            
        server.login(SENDER_EMAIL, SENDER_PASS)
        
        # 【核心修改】这里传入切割好的 receiver_list 列表，实现群发
        server.sendmail(SENDER_EMAIL, receiver_list, msg.as_string())
        server.quit()
        print(f"邮件发送成功！已成功投递给 {len(receiver_list)} 个收件人。")
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
