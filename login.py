import requests
import time
import json
import os
import qrcode
import sys
from user_agent import generate_user_agent

# --- 配置 ---
COOKIES_FILE = 'cookies.json'

class BiliLogin:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': generate_user_agent(),
            'Referer': 'https://www.bilibili.com/'
        }
        self.qrcode_key = ''

    def get_qrcode(self):
        """获取登录二维码"""
        url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
        try:
            resp = self.session.get(url, headers=self.headers)
            data = resp.json()
            if data['code'] == 0:
                self.qrcode_key = data['data']['qrcode_key']
                qrcode_url = data['data']['url']
                return qrcode_url
            else:
                print(f"获取二维码失败: {data['message']}")
                return None
        except Exception as e:
            print(f"网络错误: {e}")
            return None

    def show_qrcode(self, url):
        """在终端显示二维码，并生成图片作为备用"""
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        
        # 1. 尝试在终端打印 ASCII 二维码 (看起来很极客)
        print("\n请使用 Bilibili 手机App 扫码登录：")
        try:
            qr.print_ascii(invert=True)
        except:
            print("(终端不支持显示，请打开目录下的 qrcode.png)")

        # 2. 同时也保存为图片，防止终端显示乱码
        img = qr.make_image()
        img.save('qrcode.png')
        print(">>如果不显示，请手动打开当前目录下的 qrcode.png 扫描")
        
        # 尝试自动打开图片 (Windows)
        if os.name == 'nt':
            os.system('start qrcode.png')

    def check_login_status(self):
        """轮询登录状态"""
        url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        params = {'qrcode_key': self.qrcode_key}
        
        while True:
            try:
                resp = self.session.get(url, headers=self.headers, params=params)
                data = resp.json()
                code = data['data']['code']
                
                if code == 0:
                    print("\n[成功] 登录成功！")
                    # 获取Cookie
                    cookies = self.session.cookies.get_dict()
                    self.save_cookies(cookies)
                    break
                elif code == 86101:
                    print("\r[等待] 请扫码...", end="")
                elif code == 86090:
                    print("\r[已扫码] 请在手机上点击确认...", end="")
                elif code == 86038:
                    print("\n[失效] 二维码已过期，请重新运行")
                    break
                else:
                    print(f"\n[错误] 未知状态: {code}")
                    break
                
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n用户取消")
                break
            except Exception as e:
                print(f"\n轮询异常: {e}")
                break

    def save_cookies(self, cookies):
        """保存为与主程序兼容的格式"""
        # 转换为 EditThisCookie 类似的列表格式，或者简单的字典
        # 我们的主程序已经支持读取 {"name": "value"} 格式的字典了，所以直接存字典
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
        print(f"Cookie 已保存至 {COOKIES_FILE}")
        
        # 清理二维码图片
        if os.path.exists('qrcode.png'):
            os.remove('qrcode.png')

if __name__ == '__main__':
    login = BiliLogin()
    url = login.get_qrcode()
    if url:
        login.show_qrcode(url)
        login.check_login_status()
    input("\n按回车退出...")