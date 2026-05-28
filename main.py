import json
import os
from datetime import datetime

# --- 1. 初始化和加载缓存 ---
CACHE_FILE = 'translation_cache.json'
today_str = datetime.now().strftime("%Y-%m-%d")

# 尝试读取昨天的记忆
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
else:
    cache_data = {}

# 准备一个空列表，用来装今天要发送的完整 35 个项目数据
final_email_projects = []

# --- 2. 核心遍历与拦截逻辑 ---
# 假设 today_35_projects 是你刚刚抓取下来的 35 个项目的列表
for project in today_35_projects:
    repo_name = project['repo_name']
    original_desc = project['description']
    project_url = project['url']
    
    # 默认上榜天数为 1
    days_on_list = 1
    
    # 💥 判断：如果项目昨天翻译过了（在缓存里）
    if repo_name in cache_data:
        print(f"✅ 命中缓存 (免 Token): {repo_name}")
        translated_desc = cache_data[repo_name]['translation']
        # 天数累加
        days_on_list = cache_data[repo_name].get('days_on_list', 1) + 1
        
    # 💥 判断：如果是今天刚冒出来的新项目
    else:
        print(f"🚀 新项目上榜 (调用 Gemini): {repo_name}")
        
        # ⬇️ 【把你原来调用 Gemini API 的那段代码放在这里】 ⬇️
        # translated_desc = call_gemini_api(original_desc) 
        # ⬆️ ------------------------------------------- ⬆️
    
    # 更新缓存字典，准备下班前保存
    cache_data[repo_name] = {
        'translation': translated_desc,
        'days_on_list': days_on_list,
        'last_seen': today_str
    }
    
    # 把处理好的完美数据，塞进最终要发邮件的列表里
    final_email_projects.append({
        'repo_name': repo_name,
        'description': translated_desc,
        'days_on_list': days_on_list,
        'url': project_url
    })

# --- 3. 运行结束前，将新记忆存回本地文件 ---
with open(CACHE_FILE, 'w', encoding='utf-8') as f:
    json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print("💾 翻译缓存与霸榜天数已成功覆盖保存！")

# ---------------------------------------------------------
# 接下来的代码，你就直接循环 final_email_projects 这个列表，
# 把它拼接成 HTML 或者文本邮件发出去就行了！
