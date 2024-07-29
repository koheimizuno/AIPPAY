import logging
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from bson.objectid import ObjectId

from database import DbClient
from docx_maker import DocxMaker
import language
import common_util
import report_common

def make(req_id, prop_id):
    """
    領収書送付状を生成する
    """
    if not isinstance(req_id, ObjectId):
        req_id = ObjectId(req_id)
    if not isinstance(prop_id, ObjectId):
        prop_id = ObjectId(prop_id)

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {
                '_id': req_id,
            },
            {
                'User': 1,
                'Agent': 1,
                'Properties.Property': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Years': 1,
                'Properties.FeeList': 1,
                'Currency': 1,
                'UserName': 1,
                'UserOrganization': 1,
                'UserAddress': 1,
            }
        )

        if req is None:
            return None

        # 依頼に含まれる権利を特定
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id]
        if len(req_p) < 1:
            return None
        req_p = req_p[0]

        # 通貨情報の取得
        currencies = common_util.get_currencies(db)

        # 知財情報の取得
        prop = db.Properties.find_one({
            '_id': req_p['Property'],
        })

        # ユーザー情報の取得
        user = db.Users.find_one({'_id': req['User']})

        # 言語設定を取得
        if 'Language' in user:
            lang_code = user['Language']
        else:
            lang_code = 'ja'
        lang = language.get_dictionary(lang_code)

        doc = DocxMaker(margin=(6, 20, 18.5, 22))

        # 住所
        if 'UserAddress' in req:
            doc.add_paragraph(req['UserAddress'])

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

        # 表題
        doc.add_paragraph(lang['ReceiptMail']['Title'], font_size=16.0, center=True)

        # 前文
        doc.add_paragraph(lang['ReceiptMail']['Preamble'])
        doc.add_paragraph(lang['ReceiptMail']['Preamble_BR'], right=True)

        # 納付の内容
        doc.add_paragraph(lang['ReceiptMail']['ItemTitle'], center=True)

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

        # フッター
        if lang['ReceiptMail']['Footer'].strip()  != "":
            doc.add_paragraph("")
            doc.add_paragraph(lang['ReceiptMail']['Footer'])
        doc.add_paragraph(lang['ReceiptMail']['Footer_BR'], right=True)

        # 添付書類
        doc.add_paragraph('{}\t{}'.format(lang['ReceiptMail']['AttachmentTitle'], lang['ReceiptMail']['AttachmentName']))

        # 権利者名
        holder_names = '_'.join([x['Name'] for x in prop['Holders'] if 'Name' in x])
        if holder_names != '':
            holder_names = '_' + holder_names

        # ファイル名
        fname = '{:%Y%m%d}_{}{}_領収書送付{}.docx'.format(
            datetime.now(),
            lang['Law'][prop['Law']],
            prop['RegistrationNumber'],
            holder_names,
        )

        # 生成したファイルのバイナリーデータを取得
        bin_data = doc.get_binary()

        # レポートをデータベースに保存する
        report = {
            'Name': fname,
            'Time': datetime.now(),
            'Raw': bin_data,
            'ContentType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }

    # データを返す
    return report

if __name__ == '__main__':
    rep = make(ObjectId('6603f9ce45899ce5ff357af0'), ObjectId('6603f939c3ee4eae5ae46c86'))
    with open('log/sending_receipt.docx', 'wb') as fout:
        fout.write(rep['Raw'])
