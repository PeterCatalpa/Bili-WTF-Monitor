import time
import subprocess
import datetime
import os
import shutil
import json

# --- 核心配置 (请在上传前修改此处或保持为占位符) ---
# [初始化] 请将下方链接替换为你的 GitHub 仓库地址
REPO_URL = "https://github.com/PeterCatalpa/Bili-WTF-Monitor"

# [初始化] 目标分支，通常为 gh-pages
TARGET_BRANCH = "gh-pages"

# 同步间隔 (秒)，默认1小时
SYNC_INTERVAL = 3600 

def run_git_cmd(cmd):
    """执行 git 命令"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        return True
    except subprocess.CalledProcessError as e:
        print(f"   [Error] {e.stderr.strip()}")
        return False

def archive_current_data():
    """
    备份策略：每日只保留一份最新的存档 (覆盖模式)
    """
    now = datetime.datetime.now()
    today_date = now.strftime("%Y-%m-%d")  # 只取日期
    
    if not os.path.exists("archives"):
        os.makedirs("archives")

    source_file = "rank_report.json"
    archive_filename = f"rank_report_{today_date}.json"
    archive_path = os.path.join("archives", archive_filename)
    
    if os.path.exists(source_file):
        shutil.copy(source_file, archive_path)
        print(f"   [归档] 更新今日快照: {archive_filename}")
    else:
        print("   [警告] 找不到 rank_report.json，跳过归档")
        return False

    # 更新 history.json 索引
    history_file = "history.json"
    history_list = []
    
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
        except:
            history_list = []
    
    new_record = {
        "display": today_date,
        "filename": f"archives/{archive_filename}"
    }

    exists = False
    for item in history_list:
        if item['filename'] == new_record['filename']:
            exists = True
            break
    
    if not exists:
        history_list.insert(0, new_record)
        # 限制保留最近365天
        history_list = history_list[:365]

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)
            print("   [索引] 新增历史记录条目")
    else:
        print("   [索引] 历史列表已存在今日条目，无需更新")
    
    return True

def sync_to_github():
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] 开始同步流程...")

    # 1. 执行数据归档
    if not archive_current_data():
        return

    # 2. Git 操作 (白名单机制)
    files_to_add = [
        "index.html",
        "rank_report.json",
        "history.json",
        "archives/",
        "CNAME"  # 包含域名配置文件
    ]
    
    add_cmd = "git add " + " ".join(files_to_add)
    run_git_cmd(add_cmd)

    # 3. 提交
    commit_msg = f"Auto update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if run_git_cmd(f'git commit -m "{commit_msg}"'):
        print("   [Git] 本地提交成功")
    else:
        print("   [Git] 本地无新文件变更")
        
    # 4. 推送 (使用 -f 强制覆盖远程，确保 Dashboard 与本地一致)
    push_cmd = f"git push -f origin HEAD:{TARGET_BRANCH}"
    
    if run_git_cmd(push_cmd):
        print(f"   [Git] ✅ 成功推送到 {TARGET_BRANCH} 分支")
    else:
        print("   [Git] ❌ 推送失败，请检查网络或仓库权限")

if __name__ == "__main__":
    print(f">>>  B站监控同步助手 v2.0 (Public Version)")
    print(f">>> 目标仓库: {REPO_URL}")
    print(f">>> 目标分支: {TARGET_BRANCH}")
    
    if "YourUsername" in REPO_URL:
        print("!!! 警告: 检测到未配置的仓库地址，请编辑 git_sync.py 修改 REPO_URL !!!")
        time.sleep(5)
    
    # 隐私检查
    if not os.path.exists(".gitignore"):
        print("!!! 警告: 未检测到 .gitignore 文件，建议立即创建以防止 Cookie 泄露 !!!")
        time.sleep(3)

    # 首次启动同步一次
    sync_to_github()
    
    while True:
        time.sleep(SYNC_INTERVAL)
        sync_to_github()