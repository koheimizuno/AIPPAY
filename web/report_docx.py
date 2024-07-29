import logging
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from bson.objectid import ObjectId

from database import DbClient
from docx_maker import DocxMaker
import language
import common_util
from colors import Color
import report_common

def make(req_id, prop_id):
    """
    手続完了報告書を生成する
    """
    if not isinstance(req_id, ObjectId):
        req_id = ObjectId(req_id)
    if not isinstance(prop_id, ObjectId):
        prop_id = ObjectId(prop_id)

    with DbClient() as db:

        # 依頼情報を取得
        req = db.Requests.find_one({'_id': req_id})
        req_p = [x for x in req['Properties'] if 'Property' in x and x['Property'] == prop_id][0]

        # 権利情報を取得
        prop = db.Properties.find_one({'_id': prop_id})

        # ユーザー情報を取得
        user = db.Users.find_one({'_id': req['User']})

        # 言語設定を取得
        if 'Language' in user:
            lang_code = user['Language']
        else:
            lang_code = 'ja'
        lang = language.get_dictionary(lang_code)

        # 通貨設定を取得
        currencies = common_util.get_currencies(db)

    # 画像ファイルのベースディレクトリー
    img_path = Path(__file__).parent / 'pict'

    # Wordドキュメントの生成
    doc = DocxMaker()

    # 日付
    doc.add_paragraph(lang.format_date(datetime.now()), right=True)

    # 宛名
    if 'UserOrganization' in req:
        doc.add_paragraph(req['UserOrganization'], font_size=12.0)
    elif 'Organization' in user:
        doc.add_paragraph(user['Organization'], font_size=12.0)
    user_name = user['Name']
    if 'UserName' in req:
        user_name = req['UserName']
    doc.add_paragraph(('{} {} {}'.format(lang['Common']['NamePrefix'], user_name, lang['Common']['NameSuffix'])).strip(), font_size=12.0)

    # 署名
    img_path = Path(__file__).parent / 'pict'
    doc.add_picture(str(img_path / lang['Invoice']['Agent'][req['Agent']]['LogoFile']), right=True, width=(65.0 * 3))

    # タイトル
    if prop['Law'] == 'Trademark':
        if req_p['PaidYears'] == 5:
            title = lang['ReportMail']['Procedure']['Trademark_2']
        else:
            title = lang['ReportMail']['Procedure']['Trademark_1']
    else:
        title = lang['ReportMail']['Procedure'][prop['Law']]
    title = lang['ReportMail']['Title'].format(title)
    doc.add_paragraph(title, font_size=16.0, center=True)

    # ファイル名（拡張子除く）
    fname = '{:%Y%m%d}_{}{}_{}'.format(
        datetime.now(),
        lang['Law'][prop['Law']],
        prop['RegistrationNumber'],
        lang['ReportMail']['FileTitle']
    )

    # 前文
    doc.add_paragraph(lang['ReportMail']['Preamble'])
    doc.add_paragraph(lang['ReportMail']['Preamble_BR'], right=True)

    # 記
    doc.add_paragraph(lang['ReportMail']['ItemTitle'], center=True)

    # コンテンツの生成
    contents = report_common.get_table_contents(req, req_p, prop, lang, currencies)
    table = []
    underline = []

    for row in contents['Table']:
        table.append(row[:2])
        underline.append([False, row[2]])

    doc.add_table(table, underline=underline)

    if 'Footer' in contents:
        doc.add_paragraph("")
        doc.add_paragraph(contents['Footer'])

    # 添付書類
    doc.add_paragraph("")
    attachments = report_common.attachmens_list(req_p, prop, lang)

    for i in range(len(attachments)):
        if i == 0:
            s = lang['ReportMail']['AttachmentTitle'] + '　'
        else:
            s = ''
        s += attachments[i]
        doc.add_paragraph(
            s,
            indent=0 if i == 0 else 1.83,
            follow_indent=1.83 if i == 0 else 0,
        )

    # フッター
    if lang['ReportMail']['Footer'].strip()  != "":
        doc.add_paragraph("")
        doc.add_paragraph(lang['ReportMail']['Footer'])
    doc.add_paragraph(lang['ReportMail']['Footer_BR'], right=True)

    # ファイル名
    fname = '{:%Y%m%d}_{}{}号_手続完了報告書.docx'.format(
        datetime.now(),
        lang['Law'][prop['Law']],
        prop['RegistrationNumber']
    )

    # バイナリーとファイル名を返す
    return doc.get_binary(), fname, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

if __name__ == '__main__':
    d, n, t = make(ObjectId('6603f9ce45899ce5ff357af0'), ObjectId('6603f939c3ee4eae5ae46c86'))
    with open('log/report.docx', 'wb') as fout:
        fout.write(d)
