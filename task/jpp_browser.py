from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as expected_conditions
#from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException, StaleElementReferenceException, ElementNotVisibleException, TimeoutException
import logging
import re
import time
import json
from datetime import datetime, timedelta

import browser
import common_util

# ロガーの取得
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)

# J-PlatPat の URL
_jpp_url = 'https://www.j-platpat.inpit.go.jp'
# Selenium のタイムアウト値（秒）
_timeout = 3

# 実行制限
_timestamp = datetime(1900, 1, 1)

# 権利情報が見つからない場合に発生する例外
class NotFoundException(Exception):
    def __init__(self, law, number_kind, number):
        self._message = 'information is not found (%s, %s, %s)' % (law, number_kind, number)
    def __str__(self):
        return self._message

# 検索結果が多すぎる場合の例外
class TooManyResultException(Exception):
    def __init__(self, actual, limited):
        self._message = 'There are too many result (actual %d, limited %d)' % (actual, limited)
    def __str__(self):
        return self._message

# アクセス過多でWebサーバーに拒否された場合の例外
class AccessRejectionException(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'The server rejected my frequently access.'

class UnderMaintenanceException(Exception):
    """
    J-PlatPat がメンテナンスにより利用できない場合に発生する例外
    """
    def __init__(self):
        pass
    def __str__(self):
        return 'J-PlatPat is under maintenance.'

# Seleniumのログレベルを設定
logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

# J-PlatPat をブラウズする機能の提供
class JppBrowser(browser.Browser):

    # 初期化
    def __init__(self, headless=True):
        super().__init__(headless)
        self.open_url(_jpp_url)
        self.set_implicitly_wait(_timeout)

    def get_status(self, law, number, number_type='registration'):
        """
        経過情報の検索を実行し、その結果を取得する
        """
        _logger.info('start inquiring ... law=%s, number=%s, number_type=%s', law, number, number_type)

        # 実行制限の確認(65秒以上の間隔)
        global _timestamp
        now = datetime.now()
        if now <= _timestamp:
            d_time = (_timestamp - now)
            _logger.debug('wait for specified interval (%s).', d_time)
            time.sleep(d_time.total_seconds() + 1)
        _timestamp = now + timedelta(seconds=65)

        if not number:
            raise ValueError('number is missing.')

        # ホームに戻る
        self.back_to_home()

        # メンテナンスページにリダイレクトされていたら例外を起こす
        if self.current_url == 'https://www.j-platpat.inpit.go.jp/cache/support/mainte_sorry.html':
            raise browser.OutOfServiceException('Now, J-PlatPat is under maintenance.')

        # 番号表記の正規化
        if number_type == 'registration':
            number = common_util.regularize_reg_num('JP', law, number)
        elif number_type == 'application':
            number = common_util.regularize_app_num('JP', law, number)

        # 待機の設定
        wait = WebDriverWait(self.driver, _timeout)

        # 法域ごとに処理を分ける
        if law == 'Design':

            # 番号照会を開く
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'cfc001_globalNav_item_1')))
            elem1 = self.driver.find_element_by_id('cfc001_globalNav_item_1')
            elem1.click()

            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'cfc001_globalNav_sub_item_1_0')))
            elem2 = self.driver.find_element_by_id('cfc001_globalNav_sub_item_1_0')
            elem2.click()
            #ActionChains(self.driver).move_to_element(elem1).click(elem1).pause(1).move_to_element(elem2).click(elem2).perform()

            # 番号の種別を指定する
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'd00_srchCondtn_numInput_selNumType0')))
            elem1 = self.driver.find_element_by_id('d00_srchCondtn_numInput_selNumType0')
            elem1.click()

            wait.until(expected_conditions.visibility_of_element_located((By.ID, 'cdk-overlay-0')))
            elem0 = self.driver.find_element_by_id('cdk-overlay-0')
            if number_type == 'application':
                # 出願番号
                elem2 = elem0.find_elements_by_xpath('.//mat-option/span[contains(text(),\'出願番号\')]')[0]
            else:
                # 登録番号
                elem2 = elem0.find_elements_by_xpath('.//mat-option/span[contains(text(),\'登録番号\')]')[0]
            elem2.click()

            # 番号の設定
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'd00_srchCondtn_numInput_txtNum0')))
            elem1 = self.driver.find_element_by_id('d00_srchCondtn_numInput_txtNum0')
            elem1.send_keys(number)

            # 検索の実行
            elem1 = self.driver.find_element_by_id('d00_srchBtn_btnInqry')
            elem1.click()

            time.sleep(1)

            # 経過情報の参照
            try:
                wait.until(expected_conditions.element_to_be_clickable((By.ID, 'd0003_srchRsltLst_numonly_progInfo0')))
            except TimeoutException:
                return None
            elem1 = self.driver.find_element_by_id('d0003_srchRsltLst_numonly_progInfo0')
            num_of_windows = self.num_of_windows
            elem1.click()

            # 子ウィンドウが開くまで待機
            wait.until(expected_conditions.number_of_windows_to_be(num_of_windows + 1))

            # 子ウィンドウに切り替え
            self.switch_window(self.last_window)

        elif law == 'Trademark':

            # 番号照会を開く
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'cfc001_globalNav_item_2')))
            elem1 = self.driver.find_element_by_id('cfc001_globalNav_item_2')
            elem2 = self.driver.find_element_by_id('cfc001_globalNav_sub_item_2_0')
            ActionChains(self.driver).move_to_element(elem1).pause(1).move_to_element(elem2).click(elem2).perform()

            # 番号の種別を指定する
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 't00_srchCondtn_numInput_selNumType0')))
            elem1 = self.driver.find_element_by_id('t00_srchCondtn_numInput_selNumType0')
            elem1.click()

            wait.until(expected_conditions.visibility_of_element_located((By.ID, 'cdk-overlay-0')))
            elem1 = self.driver.find_element_by_id('cdk-overlay-0')
            if number_type == 'application':
                # 出願番号
                elem1.find_elements_by_xpath('.//mat-option/span[contains(text(),\'出願番号\')]')[0].click()
            else:
                # 登録番号
                elem1.find_elements_by_xpath('.//mat-option/span[contains(text(),\'登録番号\')]')[0].click()

            # 番号の設定
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 't00_srchCondtn_numInput_txtNum0')))
            elem1 = self.driver.find_element_by_id('t00_srchCondtn_numInput_txtNum0')
            elem1.send_keys(number)

            # 検索の実行
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 't00_srchBtn_btnInqry')))
            elem1 = self.driver.find_element_by_id('t00_srchBtn_btnInqry')
            elem1.click()

            time.sleep(1)

            # 経過情報の参照
            try:
                wait.until(expected_conditions.element_to_be_clickable((By.ID, 'trademarkBblTrademarkSampleLstFormal_tableView_progReferenceInfo0')))
            except TimeoutException:
                return None
            elem1 = self.driver.find_element_by_id('trademarkBblTrademarkSampleLstFormal_tableView_progReferenceInfo0')
            num_of_windows = self.num_of_windows
            elem1.click()

            # 子ウィンドウが開くまで待機
            wait.until(expected_conditions.number_of_windows_to_be(num_of_windows + 1))

            # 子ウィンドウに切り替え
            self.switch_window(self.last_window)

        elif law == 'Patent' or law == 'Utility':

            # 番号照会を開く
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'cfc001_globalNav_item_0')))
            elem1 = self.driver.find_element_by_id('cfc001_globalNav_item_0')
            elem1.click()

            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'cfc001_globalNav_sub_item_0_0')))
            elem2 = self.driver.find_element_by_id('cfc001_globalNav_sub_item_0_0')
            elem2.click()
            #ActionChains(self.driver).move_to_element(elem1).click(elem1).pause(1).move_to_element(elem2).click(elem2).perform()

            # 番号の種別を指定する
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'p00_srchCondtn_selDocNoInputType0')))
            elem1 = self.driver.find_element_by_id('p00_srchCondtn_selDocNoInputType0')
            elem1.click()

            try:
                wait.until(expected_conditions.visibility_of_element_located((By.ID, 'p00_srchCondtn_selDocNoInputType0-panel')))
                elem2 = self.driver.find_element_by_id('p00_srchCondtn_selDocNoInputType0-panel')
            except TimeoutException:
                _logger.exception('cannot find the panel of selection for number-kind (%s,%s)', law, number)
                try:
                    self.save_screenshot()
                except:
                    pass
                return None

            if law == 'Patent':
                if number_type == 'application':
                    # 特許出願番号
                    opt_elem = elem2.find_elements_by_xpath('.//mat-option/span[contains(text(),\'特許出願番号\')]')[0]
                    #opt_elem = elem2.find_element_by_id('mat-option-12')
                else:
                    # 特許番号
                    opt_elem = elem2.find_elements_by_xpath('.//mat-option/span[contains(text(),\'特許番号\')]')[0]
                    #opt_elem = elem2.find_element_by_id('mat-option-15')
            else:
                if number_type == 'application':
                    # 実用新案出願番号
                    opt_elem = elem2.find_elements_by_xpath('.//mat-option/span[contains(text(),\'実用新案出願番号\')]')[0]
                    #opt_elem = elem2.find_element_by_id('mat-option-18')
                else:
                    # 実用新案登録番号
                    opt_elem = elem2.find_elements_by_xpath('.//mat-option/span[contains(text(),\'実用新案登録番号\')]')[0]
                    #opt_elem = elem2.find_element_by_id('mat-option-22')
            opt_elem.click()

            # 番号の設定
            wait.until(expected_conditions.element_to_be_clickable((By.ID, 'p00_srchCondtn_txtDocNoInputNo0')))
            elem1 = self.driver.find_element_by_id('p00_srchCondtn_txtDocNoInputNo0')
            elem1.send_keys(number)

            # 検索の実行
            elem1 = self.driver.find_element_by_id('p00_searchBtn_btnDocInquiry')
            elem1.click()

            time.sleep(1)

            # 経過情報の参照
            try:
                wait.until(expected_conditions.element_to_be_clickable((By.ID, 'patentUtltyIntnlNumOnlyLst_tableView_progReferenceInfo0')))
            except TimeoutException:
                return None
            elem1 = self.driver.find_element_by_id('patentUtltyIntnlNumOnlyLst_tableView_progReferenceInfo0')
            num_of_windows = self.num_of_windows
            elem1.click()

            # 子ウィンドウが開くまで待機
            wait.until(expected_conditions.number_of_windows_to_be(num_of_windows + 1))

            # 子ウィンドウに切り替え
            self.switch_window(self.last_window)

        # タブごとに処理する
        info = {}

        # エラーの確認
        self.set_implicitly_wait(2)

        try:
            mat_error = self.driver.find_element_by_tag_name('mat-error')
        except NoSuchElementException:
            mat_error = None

        if not mat_error is None:
            msg = [x.text for x in mat_error.find_elements_by_css_selector('ul > li')]
            if len(msg) > 0:
                raise browser.OutOfServiceException('\n'.join(msg))
            else:
                raise browser.OutOfServiceException('ERROR TAG is found.')
        
        # タブごとの処理
        for tab_id in ('mat-tab-label-0-0', 'mat-tab-label-0-1', 'mat-tab-label-0-2',):

            self.set_implicitly_wait(0)

            # タブのラベルを探す
            try:
                wait.until(expected_conditions.element_to_be_clickable((By.ID, tab_id)))
            except TimeoutException:
                _logger.warning('%s tab is not found. (%s, %s)', tab_id, law, number)
                continue

            # タブを選ぶ
            tab_label = self.driver.find_element_by_id(tab_id)
            tab_label.click()

            self.set_implicitly_wait(_timeout)

            # タブのタイトルを取得
            name = tab_label.text.strip()

            # タブのコンテンツのID
            tab_content_id = tab_id.replace('label', 'content')

            # タブを取得する
            wait.until(expected_conditions.visibility_of_element_located((By.ID, tab_content_id)))
            tab = self.driver.find_element_by_id(tab_content_id)

            _logger.debug('tab is found.')

            if name == '経過記録':
                info[name] = []
            else:
                info[name] = {}

            # パネルを取得する
            for panel in tab.find_elements_by_xpath('div/div/*/mat-expansion-panel'):

                _logger.debug('panel is found')

                self.set_implicitly_wait(0)

                # パネルの見出しを取得する
                elem1 = panel.find_elements_by_tag_name('mat-panel-title')
                if elem1 is None or len(elem1) < 1:
                    _logger.warning('panel title is not found.')
                    continue
                panel_head = elem1[0]
                elem1 = panel_head.find_elements_by_css_selector('span.p-pc')
                if elem1 is None or len(elem1) < 1:
                    _logger.warning('panel title is not found.')
                    continue
                panel_title = elem1[0].text.strip()
                
                _logger.debug(panel_title)

                # 登録番号の指定があるか確認する
                self.set_implicitly_wait(0)
                elem1 = panel_head.find_elements_by_css_selector('span.panel-subTitle.p-pc')
                panel_sub_title = ''
                if len(elem1) > 0:
                    panel_sub_title = elem1[0].text.strip()
                panel_sub_title = re.sub(r'\s+', '', panel_sub_title)

                # 関係ないパネルの読み飛ばし
                if panel_sub_title != '':
                    if not number in panel_sub_title:
                        _logger.debug('%s %s is skipped.', panel_title, panel_sub_title)
                        continue

                _logger.debug('sub title is checked.')

                ## パネルを開く
                #elem1 = panel.find_elements_by_xpath('.//p[text()="開く"]')
                #if len(elem1) > 0:
                #    elem1[0].click()
                #    time.sleep(3)
                #else:
                #    elem1 = panel.find_elements_by_xpath('.//p[text()="閉じる"]')
                #    assert len(elem1) > 0

                # パネルの本体部を取得する
                panel_body = panel.find_elements_by_css_selector('div.mat-expansion-panel-body')

                if len(panel_body) < 1:
                    _logger.warning('panel body is missing. (%s)' % panel_title)
                    continue

                panel_body = panel_body[0]
                _logger.debug('panel body is found.')

                # テーブルから内容を取得する
                for row in panel_body.find_elements_by_xpath('table/tbody/tr'):

                    # 項目名を取得する
                    th = row.find_elements_by_tag_name('th')
                    if th is None or len(th) < 1:
                        continue
                    th = th[0]
                    item_name = re.sub(r' +', ' ', common_util.zen_to_han(th.text)).strip()

                    # 値を取得する
                    td = row.find_elements_by_xpath('td')[1]

                    if item_name == "商品区分記事":
                        item_value = ""
                        for item in td.find_elements_by_css_selector('div.listItem'):
                            e1 = item.find_elements_by_css_selector('div.itemHeader')
                            e2 = item.find_elements_by_css_selector('div.itemContent')
                            if not e1 is None and len(e1) > 0 and not e2 is None and len(e2) > 0:
                                item_value += '%s\n%s\n' % (
                                    re.sub(r' +', ' ', common_util.zen_to_han(e1[0].text)).strip(),
                                    re.sub(r' +', ' ', common_util.zen_to_han(e2[0].text)).strip()
                                )
                        item_value = item_value.strip()
                    elif item_name == '出願人･代理人記事' or item_name == '権利者記事':
                        item_value = ""
                        for inner_cell in td.find_elements_by_xpath('table/tbody/tr/td'):
                            item_value += inner_cell.text
                            item_value += '\n'
                        item_value = item_value.strip()
                    else:
                        item_value = re.sub(r' +', ' ', common_util.zen_to_han(td.text)).strip()

                    # 取得値をオブジェクトに格納する
                    if name == '経過記録':
                        if item_value != '':
                            info[name].append([item_name, item_value])
                    else:
                        info[name][item_name] = item_value

        # サブウィンドウを閉じる
        self.driver.close()
        self.switch_window(self.main_window)

        # 審査請求書確認
        if law in ('Patent',):

            has_exam_date = False

            if '経過記録' in info:
                if len([x for x in info['経過記録'] if x[0] == '出願審査請求書']) > 0:
                    has_exam_date = True

            # 審査請求日が不明なら公報情報を開いて確認
            if not has_exam_date:

                _logger.debug('try getting exam-claimed-date from gazette info (%s, %s)', law, number)

                # 登録公報のリンク
                elem1 = self.driver.find_element(By.ID, 'patentUtltyIntnlNumOnlyLst_tableView_regNumNum0')
                elem1.find_element(By.TAG_NAME, 'a').click()
                time.sleep(3)

                # 子ウィンドウに切り替え
                self.switch_window(self.last_window)

                try:
                    wait.until(expected_conditions.visibility_of_element_located((By.ID, "p0201_DocuDispArea_isBiblioAccordionOpened_DocuDispArea")))
                    elem1 = self.driver.find_element(By.ID, 'p0201_DocuDispArea_isBiblioAccordionOpened_DocuDispArea')
                except TimeoutException:
                    _logger.exception('cannot get exam-claimed-date, because could not check gazette (%s, %s)', law, number)
                    try:
                        self.save_screenshot()
                    except:
                        pass
                    elem1 = None
                except NoSuchElementException:
                    _logger.exception('cannot get exam-claimed-date, because could not check gazette (%s, %s)', law, number)
                    try:
                        self.save_screenshot()
                    except:
                        pass
                    elem1 = None

                if not elem1 is None:

                    elem2 = elem1.find_element(By.TAG_NAME, 'rti')

                    m = re.search(r'【審査請求日】.*\((\d+)\.(\d+)\.(\d+)\)', elem2.text)
                    if m:
                        dtxt = '%s/%s/%s' % (m.group(1), m.group(2), m.group(3))
                        if not '経過記録' in info:
                            info['経過記録'] = []
                        info['経過記録'].append(['出願審査請求書', dtxt,])

                # サブウィンドウを閉じる
                self.driver.close()
                self.switch_window(self.main_window)

        try:

            if law == "Design":

                # 固定URL参照
                elem1 = self.driver.find_element(By.ID, 'd0003_srchRsltLst_numonly_url0')
                elem1.click()

                # リンクが表示されるまで待機
                wait.until(expected_conditions.visibility_of_element_located((By.ID, "lnkUrl")))
                elem = self.driver.find_element(By.ID, "lnkUrl")
                info['URL'] = elem.get_attribute("href")

            elif law == "Trademark":

                # 固定URL参照
                elem1 = self.driver.find_element(By.ID, 'trademarkBblTrademarkSampleLstFormal_tableView_url0')
                elem1.click()

                # リンクが表示されるまで待機
                wait.until(expected_conditions.visibility_of_element_located((By.ID, "lnkUrl")))
                elem = self.driver.find_element(By.ID, "lnkUrl")
                info['URL'] = elem.get_attribute("href")

            elif law == "Patent" or law == "Utility":

                # 固定URL参照
                elem1 = self.driver.find_element(By.ID, 'patentUtltyIntnlNumOnlyLst_tableView_url0')
                elem1.click()

                # リンクが表示されるまで待機
                wait.until(expected_conditions.visibility_of_element_located((By.ID, "lnkUrl")))
                elem = self.driver.find_element(By.ID, "lnkUrl")
                info['URL'] = elem.get_attribute("href")

        except NoSuchElementException:

            # 固定URLは見つからなくてもスルー
            pass

        except TimeoutException:

            # 固定URLは見つからなくてもスルー
            _logger.warning('connot find static url (%s,%s)', law, number)
            try:
                self.save_screenshot()
            except:
                pass
            pass

        # 取得した情報を返す。
        return info

if __name__ == '__main__':
    logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    # 直接開いたらテスト実行する。
    with JppBrowser(headless=False) as browser:
        a = browser.get_status('Patent', '4731618')
        _logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
        #a = browser.get_status('Patent', '6671329')
        #_logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
        #a = browser.get_status('Design', '1347589')
        #_logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
        #a = browser.get_status('Trademark', '0789650')
        #_logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
        #a = browser.get_status('Trademark', '0052723-2')
        #_logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
        #a = browser.get_status('Trademark', '1387042/04')
        #_logger.debug(json.dumps(a, indent=2, ensure_ascii=False))
