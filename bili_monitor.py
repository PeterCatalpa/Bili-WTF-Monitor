import requests
import time
import json
import os
import logging
import random
import math
import brotli
import threading
import http.server
import sys
from datetime import datetime, timedelta
from user_agent import generate_user_agent

# ================= 配置区域 =================
COOKIES_FILE = 'cookies.json'
DATA_FILE = 'danmaku_stats.json'
ARCHIVE_FILE = 'bili_archive.json'  # [新增] 博物馆文件
RANK_FILE = 'rank_report.json'
LOG_FILE = 'monitor.log'

# 扫描深度
SCAN_PAGES_PER_REGION = 15 
PAGE_INTERVAL = (1.5, 3.0)

# 门槛配置
HARD_THRESHOLD = 1500       
SOFT_THRESHOLD = 1200       
RATIO_THRESHOLD = 15.0      

# 数据库自动净化
MAX_DB_SIZE = 5000          
CLEAN_INTERVAL = 20         

GLOBAL_COOLDOWN = 1         
MONTH_LIMIT_DAYS = 30       
REFRESH_OLD_BATCH = 30      

WEB_PORT = 8000

TARGET_REGIONS = {
    1: '动画', 4: '游戏', 119: '鬼畜', 
    160: '生活', 5: '娱乐', 3: '音乐', 
    36: '科技', 129: '舞蹈', 188: '数码'
}
# ===========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)

class SimpleProtoReader:
    def __init__(self, data): self.data, self.pos = data, 0
    def _read_varint(self):
        result, shift = 0, 0
        while True:
            if self.pos >= len(self.data): raise IndexError
            b = self.data[self.pos]; self.pos += 1; result |= (b & 0x7f) << shift
            if not (b & 0x80): return result
            shift += 7
    def extract_danmaku_content(self):
        contents = []
        if not self.data: return contents
        while self.pos < len(self.data):
            try:
                tag = self._read_varint(); wire_type = tag & 0x07; field_id = tag >> 3
                if wire_type == 2:
                    length = self._read_varint()
                    if self.pos + length > len(self.data): break 
                    payload = self.data[self.pos : self.pos + length]; self.pos += length
                    if field_id == 1: contents.extend(SimpleProtoReader(payload)._parse_inner_dm_message())
                elif wire_type == 0: self._read_varint()
                elif wire_type == 1: self.pos += 8
                elif wire_type == 5: self.pos += 4
                else: break 
            except Exception: break
        return contents
    def _parse_inner_dm_message(self):
        res = []
        while self.pos < len(self.data):
            try:
                tag = self._read_varint(); wire_type = tag & 0x07; field_id = tag >> 3
                if wire_type == 2:
                    length = self._read_varint()
                    if field_id == 7:
                        try:
                            text = self.data[self.pos : self.pos + length].decode('utf-8', errors='ignore')
                            if text: res.append(text)
                        except: pass
                    self.pos += length
                elif wire_type == 0: self._read_varint()
                elif wire_type == 1: self.pos += 8
                elif wire_type == 5: self.pos += 4
                else: break
            except Exception: break
        return res

class BiliDanmakuMonitor:
    def __init__(self):
        self.session = requests.Session()
        
        # 加载活跃库
        self.stats = self._load_data()
        # 加载博物馆
        self.archive = self._load_archive()
        
        self.save_counter = 0 
        
        curr_len = len(self.stats.get('videos', {}))
        arch_len = len(self.archive)
        print(f"\n[系统] 活跃库存: {curr_len} | 🏛️ 博物馆藏品: {arch_len} | 总捕获: {curr_len + arch_len}")
        
        self.headers = {'User-Agent': generate_user_agent(), 'Referer': 'https://www.bilibili.com/'}
        self._load_cookies()
        self.generate_report()

    def _load_cookies(self):
        if not os.path.exists(COOKIES_FILE): logging.warning("未找到 cookies.json"); return
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)
            if isinstance(cookie_data, list): cookies = {item['name']: item['value'] for item in cookie_data}
            else: cookies = cookie_data
            self.session.cookies.update(cookies)
            logging.info("Cookies 加载成功")
        except Exception: logging.error("Cookies 加载失败")

    def _load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
            except Exception as e:
                print(f"[错误] 读取活跃数据失败: {e}")
        return {"last_update": "", "videos": {}}

    def _load_archive(self):
        if os.path.exists(ARCHIVE_FILE):
            try:
                with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
            except Exception as e:
                print(f"[错误] 读取博物馆数据失败: {e}")
        return {} # 格式: {aid: {mini_data}}

    # [核心修改] 数据库清洗 + 移交博物馆
    def clean_database(self):
        videos = self.stats.get('videos', {})
        total_count = len(videos)
        
        if total_count <= MAX_DB_SIZE:
            return

        logging.info(f"⚡ 触发清理与归档: 当前 {total_count} 条")
        
        all_items = list(videos.items())
        
        # 制定保留白名单 (Keep List)
        # 1. 保大 (Top 2000 弹幕数)
        top_count = sorted(all_items, key=lambda x: x[1]['total_danmaku'], reverse=True)[:2000]
        keep_ids = {x[0] for x in top_count}
        
        # 2. 保精 (Top 2000 浓度)
        top_ratio = sorted(all_items, key=lambda x: x[1]['ratio_percent'], reverse=True)[:2000]
        keep_ids.update(x[0] for x in top_ratio)
        
        # 3. 保新 (最近3天)
        now_time = datetime.now()
        for vid, data in all_items:
            try:
                fs_str = data.get('first_seen', '')
                if fs_str:
                    fs_dt = datetime.strptime(fs_str, "%Y-%m-%d %H:%M:%S")
                    if (now_time - fs_dt).days <= 3:
                        keep_ids.add(vid)
            except: pass
            
        new_active_videos = {}
        archive_candidates = []
        
        for vid, data in videos.items():
            if vid in keep_ids:
                # 在白名单里，留在活跃库
                new_active_videos[vid] = data
            else:
                # 不在白名单，准备移出
                archive_candidates.append((vid, data))
        
        # 处理移出的数据：分拣垃圾与文物
        added_to_archive = 0
        trashed = 0
        
        for vid, data in archive_candidates:
            # 只有弹幕量 > 软门槛 的，才有资格进博物馆
            # 否则直接丢弃
            if data.get('total_danmaku', 0) >= SOFT_THRESHOLD:
                # [压缩存入博物馆] 只存核心字段，极省空间
                self.archive[vid] = {
                    "t": data.get("title", "")[:30], # 标题截断
                    "o": data.get("owner", ""),
                    "d": data.get("total_danmaku", 0),
                    "r": data.get("ratio_percent", 0),
                    "dt": data.get("first_seen", "")[:10] # 只留日期
                }
                added_to_archive += 1
            else:
                trashed += 1
                
        self.stats['videos'] = new_active_videos
        
        # 保存一下博物馆
        try:
            with open(ARCHIVE_FILE, 'w', encoding='utf-8') as f: 
                json.dump(self.archive, f, ensure_ascii=False)
        except: pass
        
        logging.info(f"🧹 清理报告: 活跃-{len(archive_candidates)} | 🏛️入馆+{added_to_archive} | 🗑️粉碎-{trashed}")

    def save_data(self):
        try:
            self.save_counter += 1
            if self.save_counter >= CLEAN_INTERVAL:
                self.clean_database()
                self.save_counter = 0

            temp_file = DATA_FILE + '.tmp'
            self.stats['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(temp_file, 'w', encoding='utf-8') as f: json.dump(self.stats, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, DATA_FILE)
            
            # 统计总数 = 活跃 + 博物馆
            total_history = len(self.stats['videos']) + len(self.archive)
            logging.info(f">> 数据已保存 (活跃: {len(self.stats['videos'])} | 🏛️总馆藏: {total_history})")
        except Exception: pass

    # --- 接口部分保持不变 ---
    def get_region_dynamic(self, rid, page=1):
        url = 'https://api.bilibili.com/x/web-interface/dynamic/region'
        params = {'rid': rid, 'ps': 20, 'pn': page}
        try:
            resp = self.session.get(url, headers=self.headers, params=params, timeout=10)
            data = resp.json()
            if data['code'] == 0:
                if 'data' in data and 'archives' in data['data']:
                    return data['data']['archives']
        except Exception: pass
        return []

    def get_region_new(self, rid, page=1):
        url = 'https://api.bilibili.com/x/web-interface/newlist'
        params = {'rid': rid, 'ps': 20, 'pn': page}
        try:
            resp = self.session.get(url, headers=self.headers, params=params, timeout=10)
            data = resp.json()
            if data['code'] == 0:
                if 'data' in data and 'archives' in data['data']:
                    return data['data']['archives']
        except Exception: pass
        return []

    def fetch_video_details(self, aid):
        url = 'https://api.bilibili.com/x/web-interface/view'
        try:
            resp = self.session.get(url, headers=self.headers, params={'aid': aid}, timeout=10)
            data = resp.json()
            if data['code'] == 0: return data['data']
        except Exception: pass
        return None

    def get_hot_reply(self, aid):
        url = 'https://api.bilibili.com/x/v2/reply/main'
        params = {'type': 1, 'oid': aid, 'mode': 3, 'ps': 1}
        try:
            resp = self.session.get(url, headers=self.headers, params=params, timeout=5)
            data = resp.json()
            if data['code'] == 0 and 'data' in data and 'replies' in data['data']:
                replies = data['data']['replies']
                if replies and len(replies) > 0:
                    content = replies[0]['content']['message']
                    return content.replace('\n', ' ')
        except Exception: pass
        return ""

    def get_danmaku_proto(self, aid, cid, duration):
        total_segments = math.ceil(duration / 360.0); all_contents = []
        for i in range(1, total_segments + 1):
            url = "https://api.bilibili.com/x/v2/dm/web/seg.so"
            try:
                resp = self.session.get(url, headers=self.headers, params={"type": 1, "oid": cid, "pid": aid, "segment_index": i}, timeout=15)
                if resp.status_code != 200: continue
                raw_data = resp.content
                try: data = brotli.decompress(raw_data)
                except: data = raw_data
                all_contents.extend(SimpleProtoReader(data).extract_danmaku_content())
                time.sleep(random.uniform(0.05, 0.1))
            except Exception: pass
        return all_contents

    def analyze_video(self, video_info):
        aid = str(video_info.get('aid') or video_info.get('id'))
        title = video_info['title'].replace('<em class="keyword">','').replace('</em>','')
        
        # [新增] 博物馆查重：如果已经在博物馆里了，要不要“复活”？
        # 策略：如果它又上热门了，说明它还没凉，把它从博物馆里捞出来，放回活跃库更新数据
        if aid in self.archive:
            # logging.info(f"🧟‍♂️ 僵尸复活: {title[:10]} 从博物馆回归!")
            del self.archive[aid] 

        stat = video_info.get('stat', {})
        api_dm_count = stat.get('danmaku', 0)
        
        if api_dm_count < SOFT_THRESHOLD:
            return

        cid = video_info.get('cid', 0)
        duration = video_info.get('duration', 0)
        owner = video_info.get('owner', {})
        owner_name = owner.get('name', '未知')
        owner_mid = owner.get('mid', 0)
        pubdate = video_info.get('pubdate', 0)
        view_count = stat.get('view', 0)

        dm_contents = self.get_danmaku_proto(aid, cid, duration)
        total_dm = len(dm_contents)

        is_qualified = False
        
        q_mark_count = 0
        allowed_chars = {'?', '？'}
        for c in dm_contents:
            if c.strip() and set(c.strip()).issubset(allowed_chars): q_mark_count += 1
        ratio = (q_mark_count / total_dm * 100) if total_dm > 0 else 0

        if total_dm >= HARD_THRESHOLD:
            is_qualified = True
        elif total_dm >= SOFT_THRESHOLD:
            if ratio >= RATIO_THRESHOLD:
                is_qualified = True

        if not is_qualified:
            return

        time.sleep(random.uniform(0.1, 0.3)) 
        top_reply = self.get_hot_reply(aid)
        
        old_data = self.stats['videos'].get(aid, {})
        first_seen = old_data.get('first_seen', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        history = old_data.get('rank_history', {})
        last_total_rank = old_data.get('last_total_rank', None)
        last_ratio_rank = old_data.get('last_ratio_rank', None)

        is_new = aid not in self.stats['videos']
        status_tag = "[NEW]" if is_new else "[UPD]"
        
        self.stats['videos'][aid] = {
            "title": title,
            "pic": video_info.get('pic', ''),
            "owner": owner_name,
            "owner_mid": owner_mid,
            "top_reply": top_reply,
            "cid": cid,
            "duration": duration,
            "view": view_count,
            "pubdate": pubdate,
            "total_danmaku": total_dm,
            "q_mark_count": q_mark_count,
            "ratio_percent": round(ratio, 4),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "first_seen": first_seen,
            "rank_history": history,
            "last_total_rank": last_total_rank,
            "last_ratio_rank": last_ratio_rank
        }
        
        logging.info(f"   {status_tag} {title[:10]}... | 弹幕:{total_dm} | 问号:{q_mark_count} ({ratio:.2f}%)")

    def generate_report(self):
        videos = self.stats.get('videos', {})
        current_time = datetime.now()
        
        def process_ranking(video_list, sort_key, rank_key_name):
            sorted_list = sorted(video_list, key=lambda x: x[1][sort_key], reverse=True)
            trend_map = {}
            for idx, (vid, data) in enumerate(sorted_list):
                cur = idx + 1
                history = data.get('rank_history', {})
                last = history.get(rank_key_name)
                trend = (last - cur) if last else 'new'
                if 'rank_history' not in self.stats['videos'][vid]:
                    self.stats['videos'][vid]['rank_history'] = {}
                self.stats['videos'][vid]['rank_history'][rank_key_name] = cur
                trend_map[vid] = trend
            return sorted_list, trend_map

        month_videos = []
        all_videos = list(videos.items())
        
        for vid, data in all_videos:
            first_seen_str = data.get('first_seen', '')
            if first_seen_str:
                try:
                    fs_dt = datetime.strptime(first_seen_str, "%Y-%m-%d %H:%M:%S")
                    if (current_time - fs_dt).days <= MONTH_LIMIT_DAYS:
                        month_videos.append((vid, data))
                except: pass
        
        _, mt_trend = process_ranking(month_videos, 'q_mark_count', 'month_total')
        m_final_list, mr_trend = process_ranking(month_videos, 'ratio_percent', 'month_ratio')
        _, at_trend = process_ranking(all_videos, 'q_mark_count', 'all_total')
        a_final_list, ar_trend = process_ranking(all_videos, 'ratio_percent', 'all_ratio')

        def pack_list(sorted_source, t_trend_map, r_trend_map):
            res = []
            for vid, data in sorted_source[:1000]: 
                item = data.copy()
                item['aid'] = vid
                item.pop('rank_history', None)
                item.pop('cid', None)
                item['count_trend'] = t_trend_map.get(vid, 'new')
                item['ratio_trend'] = r_trend_map.get(vid, 'new')
                res.append(item)
            return res

        # [核心] 计算总数
        total_history = len(all_videos) + len(self.archive)

        output_json = {
            "update_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "active_sample": len(all_videos),
            "total_history": total_history,
            "month_rank": pack_list(m_final_list, mt_trend, mr_trend),
            "all_rank": pack_list(a_final_list, at_trend, ar_trend)
        }
            
        try:
            with open(RANK_FILE, 'w', encoding='utf-8') as f: json.dump(output_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"写入榜单失败: {e}")

    def run_task(self):
        logging.info(f">>> [任务启动] 双接口巡逻 | 🏛️总馆藏: {len(self.stats['videos']) + len(self.archive)}")
        current_batch_aids = set()
        
        for rid, rname in TARGET_REGIONS.items():
            logging.info(f"--- 巡逻分区: {rname} (Rid:{rid}) ---")
            for api_type in ['dynamic', 'new']:
                for page in range(1, SCAN_PAGES_PER_REGION + 1):
                    if api_type == 'dynamic':
                        v_list = self.get_region_dynamic(rid, page)
                    else:
                        v_list = self.get_region_new(rid, page)

                    if not v_list: 
                        time.sleep(1)
                        break
                    
                    processed_in_page = 0
                    for video in v_list:
                        aid = str(video.get('aid') or video.get('id'))
                        if aid in current_batch_aids: continue
                        current_batch_aids.add(aid)

                        in_cd = False
                        if aid in self.stats['videos']:
                            last_t = self.stats['videos'][aid].get('update_time', '')
                            if last_t:
                                try:
                                    dt = datetime.strptime(last_t, "%Y-%m-%d %H:%M:%S")
                                    if (datetime.now() - dt).total_seconds() / 3600 < GLOBAL_COOLDOWN:
                                        in_cd = True
                                except: pass
                        if in_cd: continue

                        try:
                            self.analyze_video(video)
                            processed_in_page += 1
                        except Exception as e:
                            logging.error(f"分析异常: {e}")
                    
                    time.sleep(random.uniform(*PAGE_INTERVAL))
                    
                    if processed_in_page > 0:
                        self.save_data()
                        self.generate_report()

        logging.info("--- 开始巡检库存 ---")
        candidates = []
        now = datetime.now()
        for vid, data in self.stats['videos'].items():
            if vid in current_batch_aids: continue
            if data.get('total_danmaku', 0) < SOFT_THRESHOLD: continue
            if 'cid' not in data: continue
            last_t = data.get('update_time', '')
            if not last_t: continue
            try:
                dt = datetime.strptime(last_t, "%Y-%m-%d %H:%M:%S")
                if (now - dt).total_seconds() / 3600 > 12:
                    candidates.append((vid, dt))
            except: pass
        candidates.sort(key=lambda x: x[1])
        refresh_list = candidates[:REFRESH_OLD_BATCH]
        logging.info(f"维护队列: {len(refresh_list)} 个...")
        for vid, _ in refresh_list:
            try:
                logging.info(f"   [巡检] {vid}...")
                video_info = self.fetch_video_details(vid)
                if video_info:
                    self.analyze_video(video_info)
                    self.generate_report()
                time.sleep(random.uniform(1.0, 2.0))
            except Exception: pass

        self.save_data()
        self.generate_report()
        logging.info("<<< 全流程结束")

    def start(self):
        print("========================================")
        print(f" B站弹幕监控 v19.0 (赛博博物馆版)")
        print(f" 活跃库限额: {MAX_DB_SIZE} | 淘汰数据移入 Archive")
        print("========================================")
        threading.Thread(target=lambda: http.server.HTTPServer(("", WEB_PORT), http.server.SimpleHTTPRequestHandler).serve_forever(), daemon=True).start()
        print(f"\n[Web] http://localhost:{WEB_PORT}\n")
        
        try:
            while True:
                self.run_task()
                print(">>> 本轮结束，休息 10 秒...")
                time.sleep(10) 
        except KeyboardInterrupt:
            print("\n\n>>> 用户手动停止 (Ctrl+C) <<<")
            self.save_data()
            sys.exit(0)

if __name__ == "__main__":
    BiliDanmakuMonitor().start()