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

def call_gemini_with_retry(name, description):
    """调用 Gemini API 并严格限制频率防封"""
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
            # 使用最新的模型版本
            response = client.models.generate_content(
                model='gemini-3.5-flash',
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
    yesterday_str =
