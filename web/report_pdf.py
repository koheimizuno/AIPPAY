import logging
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from bson.objectid import ObjectId

from database import DbClient
from pdf_maker import PdfMaker
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

    # フォントの選択
    font_name = 'Roboto-Regular.ttf'
    if lang_code == 'ja':
        #font_name = 'ipag.ttf'
        font_name = 'yumin.ttf'
    elif lang_code == 'zh_CN':
        font_name = 'MicrosoftJhengHeiRegular.ttf'
    elif lang_code == 'zh_TW':
        font_name = 'MicrosoftJhengHeiRegular.ttf'

    # PDF の編集
    with PdfMaker(font_file_name=font_name) as pdf:

        # タイトル
        if prop['Law'] == 'Trademark':
            if req_p['PaidYears'] == 5:
                title = lang['ReportMail']['Procedure']['Trademark_2']
            else:
                title = lang['ReportMail']['Procedure']['Trademark_1']
        else:
            title = lang['ReportMail']['Procedure'][prop['Law']]
        title = lang['ReportMail']['Title'].format(title)

        # ファイル名（拡張子除く）
        fname = '{:%Y%m%d}_{}{}_{}'.format(
            datetime.now(),
            lang['Law'][prop['Law']],
            prop['RegistrationNumber'],
            lang['ReportMail']['FileTitle']
        )

        # 書誌情報の設定
        pdf.set_title(title)
        pdf.set_author(lang['Invoice']['Agent'][req['Agent']]['Name'])

        # 1ページ目の開始
        pdf.new_page()

        # 発行日
        pdf.put_text(480, 48, lang.format_date(datetime.now()), font_size=10.5, color=Color.Black.value)

        # あて名
        if 'UserOrganization' in req:
            pdf.put_text(30, 80, req['UserOrganization'], font_size=12.0)
        elif 'Organization' in user:
            pdf.put_text(30, 80, user['Organization'], font_size=12.0)
        user_name = user['Name']
        if 'UserName' in req:
            user_name = req['UserName']
        name = lang['ReportMail']['TEXT000009'] + ' '
        name += ' '.join([lang['Common']['NamePrefix'], user_name, lang['Common']['NameSuffix']]).strip()
        pdf.put_text(30, 80 + 16, name, font_size=12.0)

        # 差出人
        if lang['Invoice']['Agent'][req['Agent']]['LogoFile'] != "":
            pdf.put_image(350, 80, str(img_path / lang['Invoice']['Agent'][req['Agent']]['LogoFile']), max_height=120.0, max_width=220.0)
        else:
            pdf.put_text(350, 80, lang['Invoice']['Agent'][req['Agent']]['LogoAlt'], font_size=14.0)

        line_height = 18
        y = 230

        # タイトル
        pdf.put_text(pdf.width / 2, y, title, font_size=20.0, align_center=True, wrap_cols=30)
        y += line_height * 3

        # 前文
        y += pdf.put_text(65, y, lang['ReportMail']['Preamble'], wrap_cols=44, line_height=line_height) * line_height
        y += 3
        y += pdf.put_text(pdf.width - 65, y, lang['ReportMail']['Preamble_BR'], align_right=True) * line_height
        y += line_height

        # 納付の内容
        pdf.put_text(pdf.width / 2, y, lang['ReportMail']['ItemTitle'], align_center=True)
        y += line_height * 1.5
        contents = report_common.get_table_contents(req, req_p, prop, lang, currencies)

        def put_item(pdf, title, item, underline):
            r1 = pdf.put_text(120, y, title, wrap_cols=10)
            r2 = pdf.put_text(240, y, item, wrap_cols=26, underline=underline)
            return max(r1, r2)

        for row in contents['Table']:
            y += put_item(
                pdf,
                row[0],
                row[1],
                row[2]
            ) * (10.5 + 0.1)
            y += (line_height - 10.5 - 0.1)

        # 次回期限についてのメッセージ
        if 'Footer' in contents:
            y += line_height
            y += pdf.put_text(80, y, contents['Footer'], wrap_cols=44, line_height=line_height) * line_height

        y += line_height

        # 添付書類
        attachments = report_common.attachmens_list(req_p, prop, lang)

        if len(attachments) > 0:
            pdf.put_text(80, y, lang['ReportMail']['AttachmentTitle'])
            for at in attachments:
                y += pdf.put_text(130, y, at, wrap_cols=38) * line_height

        # フッター
        y += pdf.put_text(80, y, lang['ReportMail']['Footer'], wrap_cols=(pdf.width - 1)) * line_height
        pdf.put_text(pdf.width - 80, y, lang['ReportMail']['Footer_BR'], align_right=True)

        # ファイル名
        fname = '{:%Y%m%d}_{}{}号_手続完了報告書.pdf'.format(
            datetime.now(),
            lang['Law'][prop['Law']],
            prop['RegistrationNumber']
        )

        # バイナリーとファイル名を返す
        return pdf.get_binary(), fname, 'application/pdf'

if __name__ == '__main__':
    d, n, t = make(ObjectId('6603f9ce45899ce5ff357af0'), ObjectId('6603f939c3ee4eae5ae46c86'))
    with open('log/report.pdf', 'wb') as fout:
        fout.write(d)
