import logging
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from bson.objectid import ObjectId

from database import DbClient
import language
import common_util
import fee_calculator

def get_table_contents(req, req_p, prop, lang, currencies):
    """
    報告書に記載するテーブルの内容を取得する
    """
    contents = {
        'Table': [],
    }

    # 登録番号
    s = lang['Format']['RegistrationNumber'][prop['Law']].format(prop['RegistrationNumber'])
    if 'RegistrationDate' in prop:
        s += ' (%s: %s)' % (lang['ReportMail']['TEXT000010'], lang.format_date(prop['RegistrationDate']))
    contents['Table'].append([
        lang['Vocabulary']['RegistrationNumber'],
        s,
        False,
    ])

    # 出願番号
    if 'ApplicationNumber' in prop:
        s = lang['Format']['ApplicationNumber'][prop['Law']].format(prop['ApplicationNumber'])
        if 'ApplicationDate' in prop:
            s += ' (%s: %s)' % (lang['ReportMail']['TEXT000011'], lang.format_date(prop['ApplicationDate']))
        contents['Table'].append([
            lang['Vocabulary']['ApplicationNumber'],
            s,
            False,
        ])

    # 整理番号
    if 'ManagementNumber' in prop:
        contents['Table'].append([
            lang['Pages']['Request']['TEXT000266'],
            prop['ManagementNumber'],
            False,
        ])

    # 権利者
    contents['Table'].append([
        lang['Vocabulary']['RightHolder'],
        ', '.join([x['Name'] for x in prop['Holders']]),
        False,
    ])

    # 名称
    if 'Subject' in prop:
        contents['Table'].append([
            lang['Vocabulary']['SubjectOf' + prop['Law']],
            prop['Subject'],
            False,
        ])

    # 存続期間満了日
    if 'ExpirationDate' in prop:
        contents['Table'].append([
            lang['Vocabulary']['ExpirationDate'],
            lang.format_date(prop['ExpirationDate']),
            False,
        ])

    # 納付年分
    if prop['Law'] != 'Trademark':
        if req_p['YearFrom'] != req_p['YearTo']:
            s = lang['Format']['TheYearRange'].format(req_p['YearFrom'], req_p['YearTo'])
        else:
            s = lang['Format']['TheYear'].format(req_p['YearFrom'])
    else:
        s = lang['Format']['Years'].format(req_p['Years'])
    contents['Table'].append([
        lang['Vocabulary']['PayingYear'],
        s,
        False,
    ])

    # 納付金額
    if 'FeeList' in req_p:
        #fee, cur, _ = fee_calculator.total_fee_list(req_p['FeeList'], 'Office')
        # 最初の特許庁料金を納付金額とみなす
        tmp = [x for x in req_p['FeeList'] if x['Kind'] == 'Office']
        if len(tmp) > 0:
            fee = tmp[0]['Fee']
            cur = tmp[0]['Currency']
            if cur == 'JPY' and lang.name == 'ja':
                cur_text = '円'
            else:
                cur_text = cur
            if fee > 0:
                contents['Table'].append([
                    lang['Vocabulary']['PayingFee'],
                    currencies[cur]['Format'].format(fee) + ' ' + cur_text,
                    False,
                ])

    # 次回納付期限
    has_next = False

    if prop['Law'] != 'Trademark':
        d = common_util.next_limit(prop['RegistrationDate'], req_p['YearTo'])
        if d < prop['ExpirationDate']:
            contents['Table'].append([
                lang['ReportMail']['TEXT000001'],
                lang.format_date(d),
                True,
            ])
            has_next = True
    else:
        midashi = lang['ReportMail']['TEXT000001']
        if req_p['YearTo'] == 10:
            # 次の登録更新申請（1年先から見た次の期限）
            d = common_util.next_limit_tm(prop['RegistrationDate'], 1)
            # 手続期間は6月前から
            d1 = common_util.add_months(d, - 6)
            s1 = lang.format_date(d1)
            s2 = lang.format_date(d)
            s = '{} - {}'.format(s1, s2)
            midashi = lang['ReportMail']['TEXT000002']
        else:
            # 分納の納付期限 -> 現在（追納を考慮して1年前）の期限からみた5年後
            d = common_util.next_limit_tm(prop['RegistrationDate'], -1)
            d = common_util.add_months(d, 12 * req_p['YearTo'])
            s = lang.format_date(d)
        contents['Table'].append([
            midashi,
            s,
            True,
        ])
        has_next = True

    # 次回期限についてのメッセージ
    if has_next:

        # 次回期限あり
        contents['Footer'] = lang['ReportMail']['TEXT000003']

    elif prop['Country'] == 'JP':

        # 次回期限なし → 最終納付
        if prop['Law'] == 'Patent':
            contents['Footer'] = lang['ReportMail']['TEXT000004']
        elif prop['Law'] == 'Utility':
            contents['Footer'] = lang['ReportMail']['TEXT000005']
        elif prop['Law'] == 'Design':
            if not 'ApplicationDate' in prop:
                pass
            elif prop['ApplicationDate'] < datetime(2006, 4, 1):
                contents['Footer'] = lang['ReportMail']['TEXT000006']
            elif prop['ApplicationDate'] < datetime(2020, 4, 1):
                contents['Footer'] = lang['ReportMail']['TEXT000007']
            else:
                contents['Footer'] = lang['ReportMail']['TEXT000008']

    # 生成したコンテンツを返す
    return contents

def attachmens_list(req_p, prop, lang):
    """
    添付書類のリストを生成する
    """
    res = []
    attachments = []

    # データベース上のアップロード済みファイルを調べる
    # ※メールに添付される書類
    if 'UploadedFiles' in req_p:
        for title in [x['Title'] for x in req_p['UploadedFiles'] if 'Title' in x]:
            if not title in attachments:
                attachments.append(title)

    # アップロード済みファイルがない場合はとりあえず従来通りの表示とする
    if len(attachments) < 1:
        res.append(lang['ReportMail']['AttachmentName1'])
        s = lang['ReportMail']['AttachmentName2']
        if prop['Country'] == 'JP':
            if prop['Law'] in ('Patent', 'Utility', 'Design',):
                s += '（%s）' % lang['ReportMail']['FileName2'][prop['Law']]
            elif prop['Law'] == 'Trademark' and req_p['PaidYears'] == 5:
                s += '（%s）' % lang['ReportMail']['FileName2']['Trademark_2']
            elif prop['Law'] == 'Trademark':
                s += '（%s）' % lang['ReportMail']['FileName2']['Trademark_1']
        res.append(s)
        return res

    # 受領書とそれ以外に分ける
    sub_list = []
    for i in range(len(attachments)):
        name = attachments[i]
        if name == '受領書':
            res.append(lang['ReportMail']['AttachmentName1'])
        else:
            if not name in sub_list:
                sub_list.append(name)
    if len(sub_list) > 0:
        s = lang['ReportMail']['AttachmentName2']
        s += '(%s)' % lang.word_separator().join(sub_list)
        res.append(s)
    return res
