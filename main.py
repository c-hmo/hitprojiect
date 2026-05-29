import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import google.generativeai as genai

# Language colors matching GitHub design
def get_lang_color(lang):
    colors = {
        "Python": "#3572A5",
        "JavaScript": "#f1e05a",
        "TypeScript": "#3178c6",
        "Go": "#00ADD8",
        "Java": "#b07219",
        "C++": "#f34b7d",
        "C": "#555555",
        "HTML": "#e34c26",
        "CSS": "#563d7c",
        "Rust": "#dea584",
        "Ruby": "#701516",
        "PHP": "#4F5D95",
        "Swift": "#F05138",
        "Kotlin": "#A97BFF",
        "Shell": "#89e051",
        "Vue": "#41b883",
        "React": "#61dafb",
        "C#": "#178600"
    }
    return colors.get(lang, "#808080")

def scrape_github_trending(since="daily", limit=12):
    """
    Scrape top repositories from GitHub Trending page
    since: "daily", "weekly", "monthly"
    """
    url = f"https://github.com/trending?since={since}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"Scraping GitHub Trending since={since}...")
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            print(f"[{since}] Failed to fetch GitHub Trending. HTTP Status: {response.status_code}")
            return []
    except Exception as e:
        print(f"[{since}] Network error scraping GitHub Trending: {e}")
        return []
        
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = soup.find_all('article', class_='Box-row')
    
    repos = []
    for repo in articles[:limit]:
        # Name (owner/repo)
        name_tag = repo.find('h2', class_='h3 lh-condensed')
        name = "".join(name_tag.text.split()) if name_tag else "Unknown/Repo"
        
        # URL
        repo_url = f"https://github.com/{name}"
        
        # Description - robustly select paragraph
        desc_tag = repo.find('p')
        description = desc_tag.text.strip() if desc_tag else "No description provided."
        
        # Meta info
        meta_div = repo.find('div', class_='f6 color-fg-muted mt-2')
        lang = "Unknown"
        stars = "0"
        forks = "0"
        stars_in_period = "0"
        
        if meta_div:
            # Language
            lang_tag = meta_div.find('span', itemprop='programmingLanguage')
            if lang_tag:
                lang = lang_tag.text.strip()
            
            # Stars & Forks
            links = meta_div.find_all('a', class_='Link--muted')
            if len(links) >= 1:
                stars = links[0].text.strip()
            if len(links) >= 2:
                forks = links[1].text.strip()
            
            # Stars built in period (e.g. "123 stars today")
            text_lines = meta_div.text.strip().split('\n')
            if text_lines:
                stars_in_period = text_lines[-1].strip()
                
        repos.append({
            "name": name,
            "url": repo_url,
            "description": description,
            "language": lang,
            "stars": stars,
            "forks": forks,
            "stars_in_period": stars_in_period
        })
        
    print(f"Successfully scraped {len(repos)} repositories for since={since}.")
    return repos

def get_gemini_summary(name, description):
    """
    Generate professional Chinese summary using Google AI Studio Gemini API with JSON structure
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"Skipping Gemini for {name}: GEMINI_API_KEY environment variable is missing.")
        return None
        
    genai.configure(api_key=api_key)
    
    prompt = f"""
Analyze the following GitHub repository:
- Name: {name}
- Original Description: {description}

Please translate the project's purpose and details into clear, concise, and professional Chinese.
Specifically, extract the following three parts:
1. 这个是个啥 (What is this project / Brief Introduction)
2. 能拿来干嘛 (What can it be used for / Main features and use cases)
3. 项目的实行需要些啥 (What is needed to run, deploy, or implement this project, e.g., requirements, languages, dependencies, APIs, hardware, etc.)

Your output MUST be in a clean JSON format with these exact keys:
- what_is_it
- what_can_it_do
- requirements

Do not include any markdown formatting like ```json or any other text in your response. Only return the pure JSON string.
"""

    model = genai.GenerativeModel("gemini-1.5-flash")
    
    retries = 3
    delay = 10
    
    for attempt in range(retries):
        try:
            print(f"[{name}] Contacting Gemini (Attempt {attempt+1}/{retries})...")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response as JSON
            result = json.loads(response.text.strip())
            print(f"[{name}] Successfully generated summary from Gemini.")
            return result
        except json.JSONDecodeError as jde:
            print(f"[{name}] Failed to parse JSON from Gemini. Attempting to parse manually. Raw: {response.text}")
        except Exception as e:
            print(f"[{name}] Gemini API request failed: {e}")
            if attempt < retries - 1:
                print(f"Sleeping for {delay} seconds before retrying...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print(f"[{name}] Max retries reached. Gemini summary failed.")
                
    return None

def process_repositories(daily_repos, weekly_repos):
    """
    Calculate streaks, apply Gemini API with rate limit safety, and manage the history cache.
    """
    db_path = "data/trending_history.json"
    
    # Load or initialize history database
    db = {
        "repo_streaks": {},
        "repo_cache": {},
        "previous_daily_repos": [],
        "previous_weekly_repos": [],
        "last_run_date": ""
    }
    
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                loaded_db = json.load(f)
                # Merge keys securely
                for key in db.keys():
                    if key in loaded_db:
                        db[key] = loaded_db[key]
            print(f"Loaded existing history database from {db_path}.")
        except Exception as e:
            print(f"Failed to read existing database: {e}. Starting fresh.")
            
    repo_streaks = db["repo_streaks"]
    repo_cache = db["repo_cache"]
    previous_daily_repos = db["previous_daily_repos"]
    previous_weekly_repos = db["previous_weekly_repos"]
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    current_daily_names = [r["name"] for r in daily_repos]
    current_weekly_names = [r["name"] for r in weekly_repos]
    
    new_repo_streaks = {}
    
    # Calculate daily streaks
    for name in current_daily_names:
        # Check historical daily streak
        prev_streak = 0
        if name in repo_streaks:
            prev_streak = repo_streaks[name].get("daily_streak", 0)
            
        # If it was in yesterday's daily list, increment streak, else reset to 1
        if name in previous_daily_repos:
            daily_streak = prev_streak + 1
        else:
            daily_streak = 1
            
        new_repo_streaks[name] = {
            "daily_streak": daily_streak,
            "weekly_streak": repo_streaks.get(name, {}).get("weekly_streak", 0),
            "last_seen_daily": today_str,
            "last_seen_weekly": repo_streaks.get(name, {}).get("last_seen_weekly", "")
        }
        
    # Calculate weekly streaks (weekly trending runs)
    for name in current_weekly_names:
        prev_streak = 0
        if name in repo_streaks:
            prev_streak = repo_streaks[name].get("weekly_streak", 0)
            
        if name in previous_weekly_repos:
            weekly_streak = prev_streak + 1
        else:
            weekly_streak = 1
            
        if name in new_repo_streaks:
            new_repo_streaks[name]["weekly_streak"] = weekly_streak
            new_repo_streaks[name]["last_seen_weekly"] = today_str
        else:
            new_repo_streaks[name] = {
                "daily_streak": repo_streaks.get(name, {}).get("daily_streak", 0),
                "weekly_streak": weekly_streak,
                "last_seen_daily": repo_streaks.get(name, {}).get("last_seen_daily", ""),
                "last_seen_weekly": today_str
            }
            
    # Preserve streak records for other historical repositories
    for name, info in repo_streaks.items():
        if name not in new_repo_streaks:
            new_repo_streaks[name] = info
            
    # Merge unique current repositories to query Gemini once per repo
    unique_current_repos = {}
    for r in daily_repos:
        unique_current_repos[r["name"]] = r
    for r in weekly_repos:
        if r["name"] not in unique_current_repos:
            unique_current_repos[r["name"]] = r
            
    # Process Gemini translations & summary with caching to respect rate limits
    for name, repo in unique_current_repos.items():
        # Check cache
        if name in repo_cache and "gemini_summary" in repo_cache[name] and repo_cache[name]["gemini_summary"]:
            print(f"[{name}] Found in cache. Reusing summary.")
            repo["gemini_summary"] = repo_cache[name]["gemini_summary"]
        else:
            # Not in cache, query Gemini API
            summary = get_gemini_summary(name, repo["description"])
            if summary:
                repo["gemini_summary"] = summary
                # Store in cache
                repo_cache[name] = {
                    "name": name,
                    "url": repo["url"],
                    "description": repo["description"],
                    "language": repo["language"],
                    "stars": repo["stars"],
                    "forks": repo["forks"],
                    "gemini_summary": summary,
                    "cached_date": today_str
                }
            else:
                # Fallback on failure
                repo["gemini_summary"] = {
                    "what_is_it": "暂无（AI提取失败，可能是内容为空或网络问题）",
                    "what_can_it_do": "暂无核心用途提取",
                    "requirements": "暂无运行要求提取"
                }
            # Rate limit protection: sleep 3 seconds between Gemini requests
            time.sleep(3)
            
    # Assign the summaries and streaks back to the original lists
    for repo in daily_repos:
        name = repo["name"]
        repo["gemini_summary"] = unique_current_repos[name]["gemini_summary"]
        repo["daily_streak"] = new_repo_streaks[name]["daily_streak"]
        
    for repo in weekly_repos:
        name = repo["name"]
        repo["gemini_summary"] = unique_current_repos[name]["gemini_summary"]
        repo["weekly_streak"] = new_repo_streaks[name]["weekly_streak"]
        
    # Save updated database
    db["repo_streaks"] = new_repo_streaks
    db["repo_cache"] = repo_cache
    db["previous_daily_repos"] = current_daily_names
    db["previous_weekly_repos"] = current_weekly_names
    db["last_run_date"] = today_str
    
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        print("Database successfully saved.")
    except Exception as e:
        print(f"Failed to write database: {e}")
        
    return daily_repos, weekly_repos

def get_smtp_config(email_address):
    """
    Automatically resolve SMTP server based on email domain
    """
    domain = email_address.split('@')[-1].lower()
    if 'gmail' in domain:
        return 'smtp.gmail.com', 587, True  # TLS
    elif 'qq.com' in domain:
        return 'smtp.qq.com', 465, False  # SSL
    elif '163.com' in domain:
        return 'smtp.163.com', 465, False  # SSL
    elif 'outlook' in domain or 'hotmail' in domain:
        return 'smtp-mail.outlook.com', 587, True  # TLS
    elif 'sina' in domain:
        return 'smtp.sina.com', 465, False  # SSL
    else:
        # Default fallback standard
        return f'smtp.{domain}', 465, False

def send_email(sender, password, receiver, subject, html_content):
    """
    Send the beautifully styled email report via resolved SMTP
    """
    if not sender or not password or not receiver:
        print("SMTP Credentials or Receiver email are missing. Cannot send email.")
        return False
        
    smtp_server, port, use_tls = get_smtp_config(sender)
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"GitHub Trends Bot <{sender}>"
    msg['To'] = receiver
    
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        print(f"Connecting to SMTP server {smtp_server}:{port}...")
        if use_tls:
            server = smtplib.SMTP(smtp_server, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(smtp_server, port, timeout=30)
            
        print("Logging into SMTP server...")
        server.login(sender, password)
        print("Sending email...")
        server.sendmail(sender, receiver, msg.as_string())
        print("Newsletter email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
    finally:
        try:
            server.quit()
        except:
            pass

def generate_newsletter_html(daily_repos, weekly_repos):
    """
    Construct a stunning, high-end responsive HTML email newsletter
    """
    today_str = datetime.now().strftime("%Y年%m月%d日")
    
    # Render hot weekly repos
    weekly_cards_html = ""
    for idx, repo in enumerate(weekly_repos):
        lang = repo["language"]
        lang_color = get_lang_color(lang)
        streak = repo.get("weekly_streak", 1)
        
        # Streak badge if on the list for more than 1 week
        streak_badge = ""
        if streak > 1:
            streak_badge = f'<span style="background-color: #ecfdf5; color: #059669; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; margin-left: 8px; display: inline-block; border: 1px solid #a7f3d0;">🔥 连续 {streak} 周在榜</span>'
        else:
            streak_badge = '<span style="background-color: #f3f4f6; color: #4b5563; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px; display: inline-block;">新晋榜单</span>'
            
        sum_dict = repo.get("gemini_summary", {})
        what_is_it = sum_dict.get("what_is_it", "暂无")
        what_can_it_do = sum_dict.get("what_can_it_do", "暂无")
        requirements = sum_dict.get("requirements", "暂无")
        
        weekly_cards_html += f"""
        <div style="padding: 20px; border-bottom: 1px solid #e2e8f0; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                <a href="{repo["url"]}" style="font-size: 17px; font-weight: 700; color: #2563eb; text-decoration: none; word-break: break-all;" target="_blank">
                    #{idx+1} {repo["name"]}
                </a>
                {streak_badge}
            </div>
            
            <div style="margin-top: 6px; font-size: 12px; color: #64748b;">
                <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: {lang_color}; margin-right: 4px;"></span>
                <strong style="color: #475569; margin-right: 12px;">{lang}</strong>
                <span style="margin-right: 12px;">⭐ {repo["stars"]}</span>
                <span style="margin-right: 12px;">🍴 {repo["forks"]}</span>
                <span style="color: #059669; font-weight: 600;">📈 {repo["stars_in_period"]}</span>
            </div>
            
            <div style="background-color: #f8fafc; border-left: 4px solid #cbd5e1; padding: 10px 14px; margin: 12px 0; font-size: 13px; color: #475569; font-style: italic; border-radius: 0 6px 6px 0; line-height: 1.5;">
                {repo["description"]}
            </div>
            
            <!-- Gemini AI analysis block -->
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin-top: 12px;">
                <div style="font-size: 12px; font-weight: bold; color: #4f46e5; text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center;">
                    <span style="font-size: 14px; margin-right: 6px;">🤖</span> GEMINI 深度解析
                </div>
                
                <div style="margin-bottom: 8px; font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">📦 这个是个啥：</strong>{what_is_it}
                </div>
                
                <div style="margin-bottom: 8px; font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">🛠️ 能用来干嘛：</strong>{what_can_it_do}
                </div>
                
                <div style="font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">⚙️ 实行需要些啥：</strong>{requirements}
                </div>
            </div>
        </div>
        """
        
    # Render surging daily repos
    daily_cards_html = ""
    for idx, repo in enumerate(daily_repos):
        lang = repo["language"]
        lang_color = get_lang_color(lang)
        streak = repo.get("daily_streak", 1)
        
        # Streak badge if on the list for more than 1 day
        streak_badge = ""
        if streak > 1:
            streak_badge = f'<span style="background-color: #fffbeb; color: #d97706; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; margin-left: 8px; display: inline-block; border: 1px solid #fde68a;">⚡ 连续 {streak} 天飙升</span>'
        else:
            streak_badge = '<span style="background-color: #f3f4f6; color: #4b5563; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px; display: inline-block;">新晋飙升</span>'
            
        sum_dict = repo.get("gemini_summary", {})
        what_is_it = sum_dict.get("what_is_it", "暂无")
        what_can_it_do = sum_dict.get("what_can_it_do", "暂无")
        requirements = sum_dict.get("requirements", "暂无")
        
        daily_cards_html += f"""
        <div style="padding: 20px; border-bottom: 1px solid #e2e8f0; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                <a href="{repo["url"]}" style="font-size: 17px; font-weight: 700; color: #2563eb; text-decoration: none; word-break: break-all;" target="_blank">
                    #{idx+1} {repo["name"]}
                </a>
                {streak_badge}
            </div>
            
            <div style="margin-top: 6px; font-size: 12px; color: #64748b;">
                <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: {lang_color}; margin-right: 4px;"></span>
                <strong style="color: #475569; margin-right: 12px;">{lang}</strong>
                <span style="margin-right: 12px;">⭐ {repo["stars"]}</span>
                <span style="margin-right: 12px;">🍴 {repo["forks"]}</span>
                <span style="color: #b45309; font-weight: 600;">📈 {repo["stars_in_period"]}</span>
            </div>
            
            <div style="background-color: #f8fafc; border-left: 4px solid #cbd5e1; padding: 10px 14px; margin: 12px 0; font-size: 13px; color: #475569; font-style: italic; border-radius: 0 6px 6px 0; line-height: 1.5;">
                {repo["description"]}
            </div>
            
            <!-- Gemini AI analysis block -->
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin-top: 12px;">
                <div style="font-size: 12px; font-weight: bold; color: #4f46e5; text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center;">
                    <span style="font-size: 14px; margin-right: 6px;">🤖</span> GEMINI 深度解析
                </div>
                
                <div style="margin-bottom: 8px; font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">📦 这个是个啥：</strong>{what_is_it}
                </div>
                
                <div style="margin-bottom: 8px; font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">🛠️ 能用来干嘛：</strong>{what_can_it_do}
                </div>
                
                <div style="font-size: 13px; line-height: 1.5; color: #334155;">
                    <strong style="color: #0f172a;">⚙️ 实行需要些啥：</strong>{requirements}
                </div>
            </div>
        </div>
        """
        
    # Full responsive email layout with tech blue/navy premium aesthetics
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GitHub Trending Newsletter</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
        <div style="max-width: 680px; margin: 20px auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;">
            
            <!-- Beautiful Gradient Header -->
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #2563eb 100%); padding: 36px 24px; color: #ffffff; text-align: center;">
                <h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">GitHub 极客情报局</h1>
                <p style="margin: 8px 0 0 0; font-size: 14px; color: #bfdbfe; font-weight: 500;">每日自动抓取热点与飙升榜 • Gemini 大模型深度解读</p>
                <div style="display: inline-block; margin-top: 14px; background-color: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; color: #ffffff;">
                    📅 报告日期: {today_str}
                </div>
            </div>
            
            <!-- Quick Stats / TLDR Nav -->
            <div style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 12px 20px; text-align: center; font-size: 13px; color: #475569;">
                🔥 <strong style="color: #0f172a;">7 个每周热点</strong> &nbsp;&nbsp;|&nbsp;&nbsp; 🚀 <strong style="color: #0f172a;">12 个每日飙升</strong> &nbsp;&nbsp;|&nbsp;&nbsp; 🤖 <strong style="color: #0f172a;">Gemini AI 智能拆解</strong>
            </div>
            
            <!-- SECTION 1: HOT WEEKLY REPOS (7 items) -->
            <div style="padding: 24px 20px 8px 20px; background-color: #fff;">
                <h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 800; color: #0f172a; border-bottom: 3px solid #3b82f6; padding-bottom: 6px; display: inline-block;">
                    🔥 本周最热技术项目 (TOP 7)
                </h2>
                {weekly_cards_html}
            </div>
            
            <div style="height: 16px; background-color: #f1f5f9;"></div>
            
            <!-- SECTION 2: SURGING DAILY REPOS (12 items) -->
            <div style="padding: 24px 20px 8px 20px; background-color: #fff;">
                <h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 800; color: #0f172a; border-bottom: 3px solid #f59e0b; padding-bottom: 6px; display: inline-block;">
                    🚀 24小时飙升新星 (TOP 12)
                </h2>
                {daily_cards_html}
            </div>
            
            <!-- Footer Block -->
            <div style="background-color: #0f172a; color: #94a3b8; padding: 32px 24px; text-align: center; font-size: 12px; border-top: 1px solid #e2e8f0; line-height: 1.6;">
                <p style="margin: 0; font-weight: bold; color: #ffffff;">GitHub 极客情报局 (Geek Intelligence Bureau)</p>
                <p style="margin: 6px 0 0 0;">本邮件由 GitHub Actions 与 Google AI Studio Gemini API 自动构建发送</p>
                <p style="margin: 4px 0 0 0;">连续在榜天数根据每日抓取历史记录计算。大模型抓取已自带缓存机制，环保节约配额。</p>
                <div style="margin-top: 18px; border-top: 1px solid #334155; padding-top: 18px; font-size: 11px; color: #64748b;">
                    © {datetime.now().strftime("%Y")} Antigravity Automation Team. Code released under MIT.
                </div>
            </div>
            
        </div>
    </body>
    </html>
    """
    return html_template

def main():
    print("=== GitHub Trending & AI Newsletter Service Starting ===")
    
    # 1. Scrape 7 weekly hot repos and 12 daily surging repos
    weekly_repos = scrape_github_trending(since="weekly", limit=7)
    daily_repos = scrape_github_trending(since="daily", limit=12)
    
    if not weekly_repos and not daily_repos:
        print("ERROR: Scraped both lists and found absolutely nothing. Exiting to avoid sending blank newsletter.")
        sys.exit(1)
        
    # 2. Process streaks, cache, and apply Gemini translation summaries
    print("\n--- Processing history streaks and Gemini translation summaries ---")
    processed_daily, processed_weekly = process_repositories(daily_repos, weekly_repos)
    
    # 3. Generate the gorgeous newsletter HTML
    print("\n--- Generating high-end Newsletter HTML ---")
    html_content = generate_newsletter_html(processed_daily, processed_weekly)
    
    # 4. Fetch SMTP credentials
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_pass = os.environ.get("SENDER_PASS")
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    
    subject = f"🔥 GitHub极客情报: 7大周热点与12大日飙升项目深度拆解 ({datetime.now().strftime('%m-%d')})"
    
    # 5. Send the email
    print("\n--- Distributing report via SMTP Email ---")
    success = send_email(sender_email, sender_pass, receiver_email, subject, html_content)
    
    if success:
        print("\n=== Workflow completed successfully! ===")
    else:
        print("\n=== Workflow finished, but email sending FAILED! ===")
        sys.exit(1)

if __name__ == "__main__":
    main()
