from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as expected_conditions
#from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException, StaleElementReferenceException, ElementNotVisibleException, TimeoutException, ElementClickInterceptedException
import sys
import logging
from datetime import datetime
import os
from local_config import Config

# ロガーの取得
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)

class OutOfServiceException(Exception):
    """
    サービスが停止している場合に発生する例外
    """
    def __init__(self, *args):
        super().__init__(args)

# J-PlatPat をブラウズする機能の提供
class Browser:

    # 初期化
    def __init__(self, headless=True):
        opt = Options()
        exec_path = '/usr/bin/chromedriver'
        opt.binary_location = '/usr/bin/google-chrome'
        if sys.platform.startswith('win'):
            exec_path = 'C:\\bin\\chromedriver_win32\\chromedriver.exe'
            #opt.binary_location = 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
            opt.binary_location = 'C:\\bin\\chrome-win64\\chrome.exe'
        if headless:
            opt.add_argument('--headless')
            opt.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36')
        opt.add_argument('--disable-gpu')
        opt.add_argument('--disable-extensions')
        opt.add_argument('--incognito')
        opt.add_argument('--log-level=3')
        #opt.add_argument('--verbose')
        prefs = {'profile':{}}
        prefs['profile']['default_content_setting_values'] = {'popups':1,'images':2}
        opt.add_experimental_option('prefs', prefs)
        self.__driver = webdriver.Chrome(options=opt, executable_path=exec_path)
        self.__driver.set_window_size(1280, 960)
        self.__disposed = False

    def __enter__(self):
        """
        Enter into With-Block.
        """
        return self

    def close(self):
        """
        ブラウザーの終了
        """
        if self.__disposed:
            return
        try:
            self.close_sub_windows()
            self.driver.close()
            self.driver.quit()
        except:
            pass
        self.__disposed = True

    def __exit__(self, exception_type, exception_value, traceback):
        """
        Exit from With-Block.
        """
        self.close()

    def close_sub_windows(self):
        """
        子ウィンドウ（タブ）をすべて閉じる
        """
        while self.main_window != self.last_window:
            self.driver.switch_to.window(self.last_window)
            self.driver.close()
            _logger.debug('sub window closed')
        self.switch_window(self.main_window)

    def open_url(self, url):
        """
        指定したURLを開く
        """
        # 子ウィンドウをすべて閉じる
        self.close_sub_windows()
        # URLを開く
        self.driver.get(url)
        self.__home_url = url

    def switch_window(self, window_handle):
        """
        ウィンドウを切り替える
        """
        self.driver.switch_to.window(window_handle)

    def back_to_home(self):
        """
        ホームに戻す
        """
        self.open_url(self.home_url)

    @property
    def driver(self):
        """
        Selenium の driver インスタンスを取得する
        """
        return self.__driver

    @property
    def home_url(self):
        """
        ホームに設定されているURLを取得する
        """
        return self.__home_url

    @property
    def current_url(self):
        """
        現在のURLを取得する
        """
        return self.driver.current_url

    def set_implicitly_wait(self, wait):
        """
        暗黙のタイムアウト(秒数)を設定する
        """
        self.driver.implicitly_wait(wait)

    @property
    def main_window(self):
        """
        メインウィンドウ（最初のウィンドウ）を取得する
        """
        return self.driver.window_handles[0]

    @property
    def last_window(self):
        """
        最後に開かれたウィンドウを取得する
        """
        return self.driver.window_handles[-1]
    
    @property
    def num_of_windows(self):
        """
        現在のウィンドウの数を取得する
        """
        return len(self.driver.window_handles)

    def save_screenshot(self):
        """
        スクリーンショットを保存する（デバッグ用）
        """
        conf = Config()
        p = None
        if 'selenium' in conf and 'screenshots' in conf['selenium']:
            p = conf['selenium']['screenshots']
        if p is None or p == "":
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
        d = datetime.now()
        fname = "selenium_%s.png" % d.strftime('%Y%m%d%H%M%S')
        fname = os.path.join(p, fname)
        self.driver.save_screenshot(fname)

if __name__ == '__main__':
    # 直接開いたらテスト実行する。
    logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    with Browser(headless=False) as browser:
        browser.open_url("https://www.google.com")
