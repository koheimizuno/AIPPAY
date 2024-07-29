import jpp_browser
from browser import OutOfServiceException
from datetime import datetime
import mojimoji
import re
import logging

import common_util

# ログ
__logger = logging.getLogger(__name__)

def refer(country, law, number, number_type, lang, exception_on_maintenance=False):
    """
    特許に関する情報を収集する
    :return 取得したデータ, 失敗時の理由
    :rtype dict, str
    """
    # 日本
    if country == 'JP':
        return refer_jpp(law, number, number_type, lang, exception_on_maintenance)
    
    # ここまでに検索できていない場合は NOT SUPPORTED
    return None, 'Not supported'

def parse_jpp_holder_line(line):
    """
    J-PlatPatの権利者の表示をパースする
    """
    m = re.search(r'(\S.*\S)\s*\((\d+)\)\s*(.+)$', line)
    if m:
        # 名称, 住所, 識別番号
        return m.group(3), m.group(1), m.group(2)
    m = re.search(r'\((\d+)\)\s*(.+)$', line)
    if m:
        # 住所不明
        return m.group(2), None, m.group(1)
    m = re.search(r'(\S+)\s+(.+)$', line)
    if m:
        # 識別番号不明
        return m.group(2), m.group(1), None
    # パース失敗
    return None, None, None

def find_date_from_text(text):
    """
    テキストに含まれる日付を抽出する
    """
    text = str(text)
    mw = re.search(r'\d{4}/\d{1,2}/\d{1,2}', text)
    if mw:
        return datetime.strptime(mw.group(0), '%Y/%m/%d')
    else:
        return None

def refer_jpp(law, number, number_type, lang, exception_on_maintenance=False):
    """
    J-PlatPatを照会して登録情報（経過情報）を取得する
    """

    # J-PlatPatを照会
    with jpp_browser.JppBrowser() as b:
        try:
            status = b.get_status(law, number, number_type=number_type)
        except OutOfServiceException:
            if exception_on_maintenance:
                raise
            else:
                return None, lang['Pages']['Property']['JPlatPat']['UnderMaintenance']
        except jpp_browser.UnderMaintenanceException:
            if exception_on_maintenance:
                raise
            else:
                return None, lang['Pages']['Property']['JPlatPat']['UnderMaintenance']
        except:
            __logger.exception('J-PlatPat Reference -> Unexpected Exception')
            return None, lang['Pages']['Property']['JPlatPat']['CannotGetInformation']

    # 失敗判定
    if status is None:
        return None, lang['Pages']['Request']['TEXT000089']
    if not '登録情報' in status:
        return None, lang['Pages']['Request']['TEXT000089']

    # 情報の整形
    res = {'Country': 'JP', 'Law': law}

    if '登録情報' in status:

        # 登録番号
        if '登録記事' in status['登録情報']:
            m = re.search(r'\d+', status['登録情報']['登録記事'])
            if m:
                res['RegistrationNumber'] = m.group(0)

            # 登録日
            m = re.search(r'\((\d+/\d+/\d+)\)', status['登録情報']['登録記事'])
            if m:
                res['RegistrationDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')
            res['RegistrationNumberPrefix'] = lang['JP']['RegistrationNumberPrefix'][law]

        # 発明等の名称
        if law != 'Trademark':
            for name in ('発明等の名称(漢字)記事', '発明等の名称記事', ):
                if name in status['登録情報']:
                    res['Subject'] = status['登録情報'][name]
                    break

        # 請求項の数の確認
        if '請求項の数記事' in status['登録情報']:
            res['NumberOfClaims'] = int(status['登録情報']['請求項の数記事'])

        # 権利者
        if '権利者記事' in status['登録情報']:
            # 識別番号と名称に分解
            holders = []
            for line in status['登録情報']['権利者記事'].split('\n'):
                line = line.strip()
                if line == '':
                    continue
                h_name, h_addr, h_id = parse_jpp_holder_line(line)
                if h_name is None:
                    continue
                h_obj = {
                    'Name': h_name,
                }
                if h_addr:
                    h_obj['Address'] = h_addr
                if h_id:
                    h_obj['Id'] = h_id
                holders.append(h_obj)
            if len(holders) > 0:
                res['Holders'] = holders

        # 商品及び役務の区分
        if '商品区分記事' in status['登録情報']:
            c = []
            lines = status['登録情報']['商品区分記事'].split('\n')
            lines = [x.strip() for x in lines]
            lines = [x for x in lines if x != '']
            for line in lines:
                if re.match(r'\d+$', line):
                    c.append(line)
            if len(c) > 0:
                res['Classes'] = c
                res['NumberOfClasses'] = len(c)

        # 防護標章
        if '防護標章登録記事' in status['登録情報']:

            res['Defensive'] = True
            res['PaidYears'] = 10

            m = re.search(r'登録日\((\d+/\d+/\d+)\)', status['登録情報']['防護標章登録記事'])
            if m:
                res['RegistrationDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')
            m = re.search(r'防護存続期間満了日\((\d+/\d+/\d+)\)', status['登録情報']['防護標章登録記事'])
            if m:
                res['ExpirationDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')

            classes = []
            m = re.search(r'(商品|役務)区分\s*(.*)', status['登録情報']['防護標章登録記事'], flags=re.DOTALL)
            if m:
                for m2 in re.finditer(r'\n\s*([0-9０-９]+)\s', '\n' + m.group(2)):
                    c = mojimoji.zen_to_han(m2.group(1))
                    classes.append(c)
            if len(classes) > 0:
                res['Classes'] = classes
                res['NumberOfClasses'] = len(c)

        # 権利者
        if not 'Holders' in res:
            if '出願情報' in status and '出願人･代理人記事' in status['出願情報']:
                # 識別番号と名称に分解
                holders = []
                for line in status['出願情報']['出願人･代理人記事'].split('\n'):
                    line = line.strip()
                    if line == '':
                        continue
                    m = re.match(r'出願人(.*)', line)
                    if m:
                        print(m.group(1))
                        h_name, h_addr, h_id = parse_jpp_holder_line(m.group(1).strip())
                        if h_name is None:
                            continue
                        h_obj = {
                            'Name': h_name,
                        }
                        if h_addr:
                            h_obj['Address'] = h_addr
                        if h_id:
                            h_obj['Id'] = h_id
                        holders.append(h_obj)
                if len(holders) > 0:
                    res['Holders'] = holders

        if '登録細項目記事' in status['登録情報']:

            # 存続期間満了日
            m = re.search(r'存続期間満了日\((\d+/\d+/\d+)\)', status['登録情報']['登録細項目記事'])
            if m:
                res['ExpirationDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')

            # 消滅日
            m = re.search(r'本権利消滅日\((\d+/\d+/\d+)\)', status['登録情報']['登録細項目記事'])
            if m:
                res['DisappearanceDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')

        # 最終納付年分
        if '最終納付年分記事' in status['登録情報']:
            m = re.search(r'(\d+)年', status['登録情報']['最終納付年分記事'])
            if m:
                y = int(m.group(1))
                res['PaidYears'] = y

    if '出願情報' in status:

        # 出願番号、出願日
        if '出願記事' in status['出願情報']:
            m = re.search(r'[明大昭平令MTSHR]\d+-\d+', status['出願情報']['出願記事'])
            if m:
                res['ApplicationNumber'] = common_util.kanji_to_alpha_in_number(m.group(0))
            else:
                m = re.search(r'\d+-\d+', status['出願情報']['出願記事'])
                if m:
                    res['ApplicationNumber'] = m.group(0)
            m = re.search(r'\((\d+/\d+/\d+)\)', status['出願情報']['出願記事'])
            if m:
                res['ApplicationDate'] = datetime.strptime(m.group(1), '%Y/%m/%d')
            # 出願番号の接頭辞
            res['ApplicationNumberPrefix'] = lang['JP']['ApplicationNumberPrefix'][law]

        # 商標の名称
        for name in ('商標名記事', '称呼記事', ):
            if name in status['出願情報']:
                lines = status['出願情報'][name].split('\n')
                lines = [x.strip() for x in lines]
                lines = [x for x in lines if x != '']
                if len(lines) > 0:
                    res['Subject'] = lines[0]
                    break

        # PCT出願番号
        if '国際出願記事' in status['出願情報']:
            m = re.search(r'PCT\S+', status['出願情報']['国際出願記事'])
            if m:
                res['PctNumber'] = m.group(0)

        # 優先権番号
        if '優先権記事' in status['出願情報']:
            pn = []
            for m in re.finditer(r'([A-Z]{1,})(\(.*\))?(.*)$', status['出願情報']['優先権記事'], flags=re.MULTILINE):
                pn.append('%s %s' % (m.group(1), m.group(3)))
            if len(pn) > 0:
                res['PriorNumber'] = pn

    if '経過記録' in status:

        for history in status['経過記録']:

            # 登録査定日
            if history[0] == '登録査定':
                res['RegistrationInvestigatedDate'] = datetime.strptime(history[1], '%Y/%m/%d')

            # 審査請求日
            if law in ('Patent', 'Utility',):
                if history[0] != '出願審査請求書':
                    continue
                dx = find_date_from_text(history[1])
                if not dx is None:
                    res['ExamClaimedDate'] = dx

            # 前回の設定登録・更新登録申請書の提出日
            if law == 'Trademark':
                if history[0] == '設定納付書':
                    dx = find_date_from_text(history[1])
                    if not dx is None:
                        res['RegistrationPaymentDate'] = dx
                if history[0] == '商標権存続期間更新登録申請書':
                    dx = find_date_from_text(history[1])
                    if not dx is None:
                        res['RenewPaymentDate'] = dx

    # 権利者名を結合する
    if 'Holders' in res and len(res['Holders']) > 0:
        res['HolderNames'] = ','.join([x['Name'] for x in res['Holders'] if 'Name' in x])

    # 固定リンク
    if 'URL' in status:
        res['SourceURL'] = status['URL']

    # 取得・整形した情報を返す。
    return res, ''

def kanji_to_alpha_in_number(s):
    """
    番号中の漢字元号をアルファベットに置き換える
    """
    s = s.strip()
    s = re.sub(r'[ー‐―－]', '-', s)
    for k, a in (('明', 'M'), ('大', 'T'), ('昭', 'S'), ('平', 'H'), ('令', 'R')):
        if s.startswith(k):
            return a + s[1:]
    return s

if __name__ == '__main__':
    import language
    #d, x = refer('JP', 'Patent', '6473901', 'registration', language.get_dictionary('ja'))
    d, x = refer('JP', 'Trademark', '0789650', 'registration', language.get_dictionary('ja'))
    print(d)
