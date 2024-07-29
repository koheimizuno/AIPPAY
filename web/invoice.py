import logging
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from bson.objectid import ObjectId
import re

from database import DbClient
from pdf_maker import PdfMaker
import language
import common_util

from colors import Color

def make(req_id, remake=False):
    """
    請求書を生成する
    """
    if not isinstance(req_id, ObjectId):
        req_id = ObjectId(req_id)

    with DbClient() as db:

        # 依頼情報を取得
        req = db.Requests.find_one({'_id': req_id})

        # ユーザー情報を取得
        user = db.Users.find_one({'_id': req['User']})

        # 言語設定を取得
        if 'Language' in user:
            lang_code = user['Language']
        else:
            lang_code = 'ja'
        lang = language.get_dictionary(lang_code)

        # すべての通貨設定
        currencies = common_util.get_currencies(db)

        # ユーザー通貨
        user_cur_name = 'JPY'
        if 'Currency' in req:
            user_cur_name = req['Currency']
        user_cur = currencies[user_cur_name]

        # 明細に必要情報を付与
        for p in req['Properties']:
            prop = db.Properties.find_one({'_id': p['Property']})
            for key in ('Law', 'Country', 'CountryDescription', 'RegistrationNumber', 'ManagementNumber', 'Subject', ):
                if key in prop:
                    p[key] = prop[key]

    # 画像ファイルのベースディレクトリー
    img_path = Path(__file__).parent / 'pict'

    # フォントの選択
    fonts = [{
        'name': 'HG創英角ｺﾞｼｯｸUB',
        'file': 'HGRSGU.TTC',
        'index': 0,
    }, {
        'name': 'HGP創英角ｺﾞｼｯｸUB',
        'file': 'HGRSGU.TTC',
        'index': 1,
    }]

    # PDF の編集
    with PdfMaker(fonts=fonts) as pdf:

        # 書誌情報の設定
        pdf.set_title('%s #%d' % (lang['Invoice']['Info']['Title'], req['RequestNumber']))
        pdf.set_author(lang['Invoice']['Agent'][req['Agent']]['Name'])

        # 改ページ処理（共通化）
        def new_page(first_page=False):

            # 1ページ目の開始
            pdf.new_page()

            # ヘッダーの処理
            pdf.draw_rect(0, 0, pdf.width, 10, fill=Color.DarkBlue.value)

            if first_page:

                # 最初のページ
                pdf.draw_rect(0, 10, pdf.width, 40, fill=Color.LightBlue.value)

                # ロゴの配置
                pdf.put_image(45, 22, str(img_path / 'AIPPAY_logo.png'), max_height=16)

                # テキストタイトル
                pdf.put_text(340, 16, lang['Invoice']['Content']['TEXT000001'], font_size=22.0, color=Color.White.value)

            else:

                # 最初のページ
                pdf.draw_rect(0, 10, pdf.width, 15, fill=Color.LightBlue.value)
        
        # 最初のページの開始
        new_page(first_page=True)

        # 発行日
        pdf.put_text(470, 58, lang.format_date(datetime.now()), font_size=12.0, color=Color.Black.value)

        # あて名
        if 'UserName' in req:
            if 'UserOrganization' in req:
                pdf.put_text(30, 76, req['UserOrganization'], font_size=12.0)
        elif 'Organization' in user:
            pdf.put_text(30, 76, user['Organization'], font_size=12.0)
        user_name = user['Name']
        if 'UserName' in req:
            user_name = req['UserName']
        name = ' '.join([lang['Common']['NamePrefix'], user_name, lang['Common']['NameSuffix']]).strip()
        pdf.put_text(30, 81 + 16, name, font_size=12.0)

        # 請求番号
        if 'RequestNumberV2' in req:
            req_num = req['RequestNumberV2']
        else:
            req_num = '%s-%d' % (datetime.now().strftime('%Y%m%d')[2:], req['RequestNumber'])

        # 請求番号、登録番号
        if lang['Invoice']['Agent'][req['Agent']]['TNumber'] != "":
            pdf.put_text(400, 80, lang['Invoice']['Content']['TEXT000002'], font_size=10.5)
            pdf.put_text(450, 80, req_num, font_size=10.5)
        else:
            pdf.put_text(400, 88, lang['Invoice']['Content']['TEXT000002'], font_size=10.5)
            pdf.put_text(450, 88, req_num, font_size=10.5)

        # 請求金額、入金期限
        pdf.put_text(50, 131, lang['Invoice']['Content']['TEXT000004'], font_size=10.5)
        pdf.draw_rect(48, 160, 200, 30, fill=Color.BgColor.value)
        pdf.put_text(64, 168, lang['Invoice']['Content']['TEXT000005'], font_size=10.5)

        cur_text = req['Currency']
        if cur_text == 'JPY' and lang.name == 'ja':
            cur_text = '円'
        s = currencies[req['Currency']]['Format'].format(req['TotalAmount'])
        pdf.put_text(218, 162, s, font_size=20, align_right=True)
        pdf.put_text(220, 168, cur_text, font_size=14)

        pdf.draw_rect(48, 200, 200, 30, stroke=Color.LineColor.value)
        pdf.draw_line(120, 200, 120, 230, Color.LineColor.value)
        pdf.put_text(64, 208, lang['Invoice']['Content']['TEXT000006'], font_size=10.5)

        s = common_util.date_format(req['PayLimit'], 'ja')
        pdf.put_text(187, 206, s, font_size=14, align_center=True)

        # 入金期限メッセージ
        if req['PayLimit'] <= common_util.get_today() and req['PayLimit'] >= (common_util.get_today() - timedelta(days=14)):
            pdf.put_text(50, 235, lang['Invoice']['Content']['TEXT000008'], font_size=11.0, color=Color.Red.value)

        # 請求人
        if lang['Invoice']['Agent'][req['Agent']]['LogoFile'] != "":
            pdf.put_image(335, 115, str(img_path / lang['Invoice']['Agent'][req['Agent']]['LogoFile']), max_height=135.0, max_width=240)
        else:
            pdf.put_text(370, 120, lang['Invoice']['Agent'][req['Agent']]['LogoAlt'], font_size=14.0)

        # 以降はY座標で管理
        y = 245
        new_page_pos = 40

        # 小計の元の通貨の単位で表示する
        for cur in req['SmallAmounts'].keys():

            # 明細（課税明細と非課税明細に分ける）
            meisai_tmp = {}

            # 費目ごとに集計
            for p in req['Properties']:
                for f in p['FeeList']:
                    if f['Currency'] != cur:
                        continue
                    tax_rate = 0.0
                    if 'TaxRate' in f:
                        tax_rate = f['TaxRate']
                    if not tax_rate in meisai_tmp:
                        meisai_tmp[tax_rate] = {}
                    d = meisai_tmp[tax_rate]
                    if not f['Subject'] in d:
                        d[f['Subject']] = {'Count': 0, 'Amount': 0.0, 'Tax': 0.0}
                    d[f['Subject']]['Count'] += 1
                    d[f['Subject']]['Amount'] += f['Fee']

            min_rows = 4
            #x = sum([len(meisai_tmp[k].keys()) for k in meisai_tmp.keys()])
            #if x > 8:
            #    min_rows = 8

            # 課税区分(税率)ごとに処理する
            for tax_rate in sorted(meisai_tmp.keys(), reverse=True):

                # 税率のテキスト表現
                if tax_rate > 0.0:
                    tax_rate_text = '{:.2f}%'.format(tax_rate * 100)
                else:
                    tax_rate_text = '-'

                # 通貨単位の表示を調整
                cur_text = cur
                if lang.name == 'ja' and cur_text == 'JPY':
                    cur_text = '円'

                # 改ページ
                if y > (pdf.height - 85):

                    new_page()
                    y = new_page_pos

                else:

                    # 表の上部にマージンを取る
                    if y != new_page_pos:
                        y += 13

                # 明細化する
                meisai = []

                for subject in sorted(meisai_tmp[tax_rate].keys()):
                    subject_tmp = subject
                    subject_idx = 0
                    while subject_tmp != '':
                        tmp = ''
                        while common_util.text_width(tmp) < 24 and subject_tmp != '':
                            tmp += subject_tmp[0]
                            if len(subject_tmp) > 1:
                                subject_tmp = subject_tmp[1:]
                            else:
                                subject_tmp = ''
                        tmp, subject_tmp = common_util.smart_split_texts(tmp, subject_tmp)
                        if subject_idx == 0:
                            meisai.append([
                                tmp,
                                meisai_tmp[tax_rate][subject]['Count'],
                                currencies[cur]['Format'].format(meisai_tmp[tax_rate][subject]['Amount']),
                                cur_text,
                            ])
                        else:
                            meisai.append([
                                tmp,
                                0,
                                "",
                                "",
                            ])
                        subject_idx += 1

                # 最低4明細に調整
                while len(meisai) < min_rows:
                    meisai.append([
                        lang['Invoice']['Content']['TEXT000020'] if meisai[-1][0] != lang['Invoice']['Content']['TEXT000020'] and meisai[-1][0] != "" else  "",
                        "", "", ""
                    ])

                # データベースのキー形式に変換
                tax_rate_key = tax_rate_text.replace('.', '__dot__')

                if tax_rate_key == '-':
                    kind = 'Office'
                else:
                    kind = 'Agent'

                # 小計明細
                meisai.append([
                    lang['Invoice']['Content']['TEXT000009'],
                    0,
                    currencies[cur]['Format'].format(req['SmallAmounts'][cur][kind][tax_rate_key][0]),
                    cur_text,
                ])

                line_height = 19
                j = 0
                y += 20

                for i in range(len(meisai)):

                    if i == 0 or y == new_page_pos:
                        row_height = line_height * 1.2
                        pdf.draw_rect(48, y, 470, row_height, fill=Color.DarkBlue.value)
                        pdf.draw_line(380, y, 380, y + row_height, Color.White.value)
                        pdf.draw_line(420, y, 420, y + row_height, Color.White.value)
                        pdf.put_text(225, y + 2 + (line_height * 0.1), lang['Invoice']['Content']['TEXT000010'], font_size=12, align_center=True, color=Color.White.value)
                        pdf.put_text(400, y + 2 + (line_height * 0.1), lang['Invoice']['Content']['TEXT000011'], font_size=12, align_center=True, color=Color.White.value)
                        if kind == 'Office':
                            pdf.put_text(470, y + 2 + (line_height * 0.1), lang['Invoice']['Content']['TEXT000051'], font_size=12, align_center=True, color=Color.White.value)
                        else:
                            pdf.put_text(470, y + 2 + (line_height * 0.1), lang['Invoice']['Content']['TEXT000012'], font_size=12, align_center=True, color=Color.White.value)
                        pdf.draw_rect(48, y, 470, row_height, stroke=Color.LineColor.value)
                        y += row_height
                        j = 0

                    row_height = line_height
                    cell_padding = 2

                    if i == (len(meisai) - 1):
                        row_height = line_height * 1.2
                        cell_padding = 2 + (line_height * 0.1)
                        pdf.draw_rect(48, y, 470, row_height, fill=Color.BgColor.value)
                    elif (j % 2) == 1:
                        pdf.draw_rect(48, y, 470, row_height, fill=Color.VeryLightBlue.value)

                    if i == (len(meisai) - 1):
                        pdf.put_text(240, y + cell_padding, meisai[i][0], font_size=12, align_center=True, color=Color.Black.value)
                    else:
                        pdf.put_text(55, y + cell_padding, meisai[i][0], font_size=12, color=Color.Black.value)
                        if meisai[i][1] != 0:
                            pdf.put_text(410, y + cell_padding, meisai[i][1], font_size=12, align_right=True, color=Color.Black.value)
                    pdf.put_text(501, y + cell_padding, meisai[i][2], font_size=12, align_right=True, color=Color.Black.value)
                    pdf.put_text(503, y + cell_padding + 1, meisai[i][3], font_size=10.5, color=Color.Black.value)

                    pdf.draw_line(48, y, 48, y + row_height, Color.LineColor.value)
                    pdf.draw_line(380, y, 380, y + row_height, Color.LineColor.value)
                    pdf.draw_line(420, y, 420, y + row_height, Color.LineColor.value)
                    pdf.draw_line(518, y, 518, y + row_height, Color.LineColor.value)

                    # 改ページ判定
                    if y > (pdf.height - 80) and i != (len(meisai) - 2):

                        # 最後の明細の下部に実線を引く
                        pdf.draw_line(48, y + row_height, 518, y + row_height, Color.LineColor.value)

                        # 改ページ
                        new_page()
                        y = new_page_pos

                    elif i >= (len(meisai) - 2):

                        # 明細の下部に実線を引く
                        pdf.draw_line(48, y + row_height, 518, y + row_height, Color.LineColor.value)
                        y += row_height

                    else:

                        # 明細の下部に破線を引く
                        pdf.draw_line(48, y + row_height, 518, y + row_height, Color.LineColor.value, dash=True)
                        y += row_height

                    j += 1

            # 改ページ判定
            if y > (pdf.height - 80):

                # 改ページ
                new_page()
                y = new_page_pos + 60
            
            else:

                # マージン
                y += 20

            # 合計明細を生成
            meisai = []

            # 通貨別小計
            cur_total = 0.0

            for key in ('Agent', 'Tax', 'Office', 'SourceWithholdingTax',):
                
                # 該当の小計が無ければスキップ
                if not key in req['SmallAmounts'][cur]:
                    continue

                for tax_rate_key in req['SmallAmounts'][cur][key].keys():

                    # 税率のテキスト表現
                    tax_rate_text = tax_rate_key.replace('__dot__', '.')
                    tax_rate_text = re.sub(r'\.0+%', '%', tax_rate_text)

                    # 見出し
                    if key == 'Agent':
                        midashi = lang['Invoice']['Content']['TEXT000015']
                    elif key == 'Office':
                        midashi = lang['Invoice']['Content']['TEXT000017']
                    elif key == 'Tax':
                        midashi = lang['Invoice']['Content']['TEXT000016'].format(tax_rate_text)
                    elif key == 'SourceWithholdingTax':
                        midashi = lang['Invoice']['Content']['TEXT000019'].format(tax_rate_text)
                    else:
                        midashi = '-'

                    meisai.append([
                        midashi,
                        currencies[cur]['Format'].format(req['SmallAmounts'][cur][key][tax_rate_key][0]),
                    ])

                    # 通貨別小計
                    cur_total += req['SmallAmounts'][cur][key][tax_rate_key][0]

            # 総合計の追加
            meisai.append([
                lang['Invoice']['Content']['TEXT000018'],
                currencies[cur]['Format'].format(cur_total),
            ])

            # 合計は一塊で改ページ判定する
            row_height = line_height * 1.2
            h = (row_height + 3) * len(meisai)

            if (pdf.height - y) < (h + 30):
                new_page()
                y = new_page_pos + 60
            
            for i in range(len(meisai)):

                m = meisai[i]

                # 項目間マージン
                y += 3

                pdf.draw_rect(420, y, 100, row_height, fill=Color.BgColor.value)
                pdf.put_text(415, y + 4, m[0], font_size=12, align_right=True, color=Color.Black.value)
                if i == (len(meisai) - 1):
                    pdf.put_text(503, y + 2, m[1], font_size=16, align_right=True, color=Color.Black.value)
                else:
                    pdf.put_text(503, y + 4, m[1], font_size=12, align_right=True, color=Color.Black.value)
                if user_cur_name != 'JPY' or lang.name != 'ja':
                    pdf.put_text(505, y + 6, user_cur_name, font_size=10.5, color=Color.Black.value)
                else:
                    pdf.put_text(505, y + 6, "円", font_size=10.5, color=Color.Black.value)

                y += row_height

            if y > (pdf.height - 125):
                new_page()
                y = new_page_pos

        y = pdf.height - 120

        # フッター
        pdf.draw_rect(0, y, pdf.width, 3, fill=Color.LightBlue.value)
        pdf.draw_rect(0, y + 3, pdf.width, 3, fill=Color.DarkBlue.value)

        # 入金先
        y += 10
        pdf.put_text(30, y + 10, lang['Invoice']['Content']['TEXT000021'], font_size=10.5, color=Color.Black.value)
        pdf.put_text(45, y + 33, lang['Invoice']['Content']['TEXT000022'], font_size=10.5, color=Color.Black.value)
        pdf.put_text(45, y + 49, lang['Invoice']['Content']['TEXT000027'], font_size=10.5, color=Color.Black.value)
        pdf.put_text(45, y + 65, lang['Invoice']['Content']['TEXT000024'], font_size=10.5, color=Color.Black.value)

        # PDFファイル化
        return pdf.get_binary()

if __name__ == '__main__':
    obj = make(ObjectId("668d30b460e9d0bfc9a212bf"), False)
    with open('./log/invoice.pdf', 'wb') as fout:
        fout.write(obj)
