from docx_maker import DocxMaker
import mojimoji
from pdf_maker import PdfMaker
from pathlib import Path
import re

class delegation(object):
    """
    委任状の生成
    """

    def __init__(self, date):
        """
        コンストラクター
        """
        self._doc = DocxMaker(default_font="ＭＳ 明朝")
        self._date = date
        self._page = 0

    def add_item(self, reg_num, names, addrs=None):
        """
        アイテムの追加
        """
        if not isinstance(names, list):
            names = [names,]

        for name in names:

            # 改ページ処理
            if self._page > 0:
                self._doc.new_page()
            self._page += 1

            # 作成日
            if self._date:
                d_txt = '令和{}年{}月{}日'.format(
                    mojimoji.han_to_zen(str(self._date.year - 2018)),
                    mojimoji.han_to_zen(str(self._date.month)),
                    mojimoji.han_to_zen(str(self._date.day)))
            else:
                d_txt = '令和　　年　　月　　日'

            # 委任状の挿入
            insert_delegation(self._doc, d_txt, reg_num, names, addrs)

    def get_binary(self):
        """
        Docxデータを取得
        """
        return self._doc.get_binary()

class abandonment(object):
    """
    商標権の一部抹消登録申請書、商標権の一部放棄書、委任状
    """

    def __init__(self, date):
        """
        コンストラクター
        """
        self._doc = DocxMaker(default_font="ＭＳ 明朝")
        self._date = date
        self._cnt = 0

    def add_item(self, reg_num, classes, names, addrs=None):
        """
        対象の追加
        """
        if self._cnt > 0:
            self._doc.new_page()
        self._cnt += 1

        if not isinstance(classes, list):
            classes = [classes,]
        if not isinstance(names, list):
            names = [names,]

        # ここから、商標権の一部抹消登録申請書
        contents = get_deletion_contents(self._date, reg_num, classes, names, addrs=addrs, enable_wrap_text=False)

        # タイトル
        self._doc.add_paragraph("(登録免許税:1,000円)", font_size=10.5)

        # 収入印紙
        img_path = Path(__file__).parent / 'pict'
        self._doc.add_picture(str(img_path / 'shunyu_inshi.jpg'), width=76.5)
        self._doc.add_paragraph("", font_size=24)
        self._doc.add_paragraph(contents['Title'], font_size=24, center=True)
        self._doc.add_paragraph("")

        # 作成日
        self._doc.add_paragraph(contents['Date'], font_size=12, right=True)

        for p in contents['Paragraphs']:
            if '氏名（名称）' in p or '住所（居所）' in p:
                self._doc.add_paragraph(p, font_size=12, follow_indent=4.7)
            else:
                self._doc.add_paragraph(p, font_size=12)

        # ここから、商標権の一部放棄書
        self._doc.new_page()

        # タイトル
        self._doc.add_paragraph("", font_size=24)
        self._doc.add_paragraph("", font_size=24)
        self._doc.add_paragraph("商標権の一部放棄書", font_size=24, center=True)
        self._doc.add_paragraph("")

        # 作成日
        self._doc.add_paragraph(contents['Date'], font_size=12, right=True)
        self._doc.add_paragraph("")

        # 本文
        self._doc.add_paragraph("商標登録番号　第{}号".format(reg_num), font_size=12)
        self._doc.add_paragraph("")
        self._doc.add_paragraph("上記商標権の指定商品（役務）及び商品又は役務の区分中、下記指定商品（役務）及び商品又は役務の区分について一部放棄します。", font_size=12)
        self._doc.add_paragraph("")
        self._doc.add_paragraph("記", font_size=12, center=True)
        self._doc.add_paragraph("")
        self._doc.add_paragraph("一部放棄に係る指定商品（役務）及び商品（役務）の区分", font_size=12)
        for c in classes:
            self._doc.add_paragraph("　　　　第{}類　　　全部".format(mojimoji.han_to_zen(str(c))), font_size=12)
        self._doc.add_paragraph("")

        self._doc.add_paragraph("")
        self._doc.add_paragraph("")

        # 氏名等
        self._doc.add_paragraph("商標権者", font_size=12, indent=5)
        for i in range(len(names)):
            if not addrs is None and i < len(addrs):
                self._doc.add_paragraph("　　住所（居所）　{}".format(addrs[i]), font_size=12, indent=5.5, follow_indent=9.3)
            else:
                self._doc.add_paragraph("　　住所（居所）　", font_size=12, indent=5.5, follow_indent=9.3)
            self._doc.add_paragraph("　　氏名（名称）　{}".format(names[i]), font_size=12, indent=5.5, follow_indent=9.3)
            if re.search(r'(有限会社|株式会社|有限公司)', names[i]):
                self._doc.add_paragraph("　　代表取締役　　", font_size=12, indent=5.5, follow_indent=9.3)
            elif re.search(r'(合同会社)', names[i]):
                self._doc.add_paragraph("　　代表者　　　　", font_size=12, indent=5.5, follow_indent=9.3)
            elif re.search(r'(一般社団法人)', names[i]):
                self._doc.add_paragraph("　　理事　　　　　", font_size=12, indent=5.5, follow_indent=9.3)
        self._doc.add_paragraph("")

        # ここから、委任状
        self._doc.new_page()
        insert_delegation(self._doc, contents['Date'], reg_num, names, addrs)

    def get_binary(self):
        """
        Docxデータを取得
        """
        return self._doc.get_binary()

def insert_delegation(doc, date, reg_num, names, addrs=None, font_size=12):
    """
    文書に委任状を挿入する
    """
    # タイトル
    doc.add_paragraph("", font_size=24)
    doc.add_paragraph("", font_size=24)
    doc.add_paragraph("委　　　任　　　状", font_size=24, center=True)
    doc.add_paragraph("")

    # 作成日
    doc.add_paragraph(date, font_size=font_size, right=True)
    doc.add_paragraph("")

    # 本文
    doc.add_paragraph("私儀、識別番号１００１８５６９４ 弁理士　山下　隆志　氏を代理人として下記の事項を委任します。", font_size=font_size)
    doc.add_paragraph("")
    doc.add_paragraph("１　商標登録第{}号の商標権の一部抹消登録申請に関する手続並びにこの申請の放棄及び取下げ".format(reg_num), font_size=font_size, follow_indent=0.9)
    doc.add_paragraph("")
    doc.add_paragraph("２　上記商標権及びこれに関する権利に関する手続並びにこの権利の放棄並びにこの手続に関する請求の取下げ、申請の取下げ及び申立ての取下げ", font_size=font_size, follow_indent=0.9)
    doc.add_paragraph("")
    doc.add_paragraph("３　上記各項に関し行政不服審査法に基づく諸手続きを為すこと", font_size=font_size, follow_indent=0.9)
    doc.add_paragraph("")
    doc.add_paragraph("")

    # 氏名等
    for i in range(len(names)):
        if i > 0:
            doc.add_paragraph("")
        if not addrs is None and i < len(addrs):
            doc.add_paragraph("　　住所（居所）　{}".format(addrs[i]), font_size=font_size, follow_indent=3.9)
        else:
            doc.add_paragraph("　　住所（居所）　", font_size=font_size, follow_indent=3.9)
        doc.add_paragraph("　　氏名（名称）　{}".format(names[i]), font_size=font_size, follow_indent=3.9)
        if re.search(r'(有限会社|株式会社|有限公司)', names[i]):
            doc.add_paragraph("　　代表取締役　　", font_size=font_size, follow_indent=3.9)
        elif re.search(r'(合同会社)', names[i]):
            doc.add_paragraph("　　代表者　　　　", font_size=font_size, follow_indent=3.9)
        elif re.search(r'(一般社団法人)', names[i]):
            doc.add_paragraph("　　理事　　　　　", font_size=font_size, follow_indent=3.9)

    # 締め
    doc.add_paragraph("")
    doc.add_paragraph("以上", font_size=font_size, right=True)

def get_deletion_contents(date, reg_num, classes, names, addrs=None, enable_wrap_text=False):
    """
    商標権の一部放棄書に表示する内容を取得する
    """
    contents ={}

    # 日付
    contents['Date'] ='令和{}年{}月{}日'.format(
                mojimoji.han_to_zen(str(date.year - 2018)),
                mojimoji.han_to_zen(str(date.month)),
                mojimoji.han_to_zen(str(date.day)))

    # タイトル
    contents['Title'] = "商標権の一部抹消登録申請書"

    # 内容
    contents['Paragraphs'] = [
        "",
        "　　特許庁長官　　　　　　　　　殿",
        "",
    ]
    contents['Paragraphs'].append("１．商標登録番号　　　　第{}号　".format(reg_num))
    contents['Paragraphs'] += [
        "",
        "２．一部放棄に係る指定商品（役務）及び商品又は役務の区分"
    ]
    for c in classes:
        contents['Paragraphs'].append("　　　　第{}類　　　全部".format(mojimoji.han_to_zen(str(c))))
    contents['Paragraphs'] += [
        "",
        "３．登録の目的　　本商標権の登録の一部抹消",
        "",
        "４．申請人（商標権者）",
    ]
    def wrap_text(line):
        if not enable_wrap_text:
            return [line,]
        max_len = 11 + 25
        tmp = []
        while True:
            if line is None or line == '':
                tmp.append('')
                break
            if len(line) > max_len:
                tmp.append(line[:max_len])
                line = ('　' * 11) + line[max_len:]
            else:
                tmp.append(line)
                break
        return tmp
    for i in range(len(names)):
        if i > 0:
            contents['Paragraphs'].append('')
        if not addrs is None and i < len(addrs):
            contents['Paragraphs'] += wrap_text("　　住所（居所）　　　%s" % mojimoji.han_to_zen(addrs[i]))
        else:
            contents['Paragraphs'] += wrap_text("　　住所（居所）　　　")
        contents['Paragraphs'] += wrap_text("　　氏名（名称）　　　%s" % mojimoji.han_to_zen(names[i]))
    contents['Paragraphs'].append("代理人")
    contents['Paragraphs'].append("　　氏名（名称）　　　三重県志摩市大王町名田２７２")
    contents['Paragraphs'].append("　　　　　　　　　　　ＡＩＰＰＡＹ弁理士事務所配送担当")
    contents['Paragraphs'].append("　　氏名（名称）　　　山下　隆志")
    contents['Paragraphs'].append("")
    contents['Paragraphs'].append("　　電話番号　　　　　０９０－９８１７－２９２４")
    contents['Paragraphs'].append("")
    contents['Paragraphs'] += [
        "５．添付書面の目録",
        "　　(1)　商標権の一部放棄書　　　　　　　　　　　　　　　　　　　１通",
        "　　(2)　委任状　　　　　　　　　　　　　　　　　　　　　　　　　１通"
    ]

    return contents

class deletion_pdf(object):
    """
    商標権の一部抹消登録申請書(PDF)
    """

    def __init__(self, date):
        """
        コンストラクター
        """
        # PDF
        self._doc = PdfMaker(font_file_name='msmincho.ttc')
        # 書誌情報の設定
        self._doc.set_title("商標権の一部抹消登録申請書")
        self._doc.set_author("AIPPAY")
        self._date = date
        self._cnt = 0

    def add_item(self, reg_num, classes, names, addrs=None):
        """
        対象の追加
        """
        self._doc.new_page()
        self._cnt += 1

        # コンテンツの取得
        contents = get_deletion_contents(self._date, reg_num, classes, names, addrs)

        # 画像ファイルのベースディレクトリー
        img_path = Path(__file__).parent / 'pict'

        # 収入印紙
        self._doc.put_text(80, 60, "(登録免許税:1,000円)", font_size=10.5)
        self._doc.put_image(80,72, str(img_path / 'shunyu_inshi.jpg'), max_height=90)

        # タイトル
        y = 180
        self._doc.put_text(self._doc.width / 2, y, contents['Title'], font_size=20, align_center=True)
        y += 55
        self._doc.put_text(self._doc.width - 80, y, contents['Date'], font_size=12, align_right=True)
        y += 20

        # コンテンツ
        for p in contents['Paragraphs']:
            self._doc.put_text(80, y, p, font_size=12)
            y += 20

    def get_binary(self):
        """
        PDFデータを取得
        """
        return self._doc.get_binary()

class koshin_shinsei_hoju(object):
    """
    商標権存続期間更新登録申請書（補充）、委任状
    """

    def __init__(self, date):
        """
        コンストラクター
        """
        self._doc = DocxMaker(default_font="ＭＳ 明朝", margin=(35, 30, 30, 30))
        self._date = date
        self._cnt = 0

    def add_item(self, reg_num, classes, holders=[]):
        """
        対象の追加
        """
        if self._cnt > 0:
            self._doc.new_page()
        self._cnt += 1

        if not isinstance(classes, list):
            classes = [classes,]
        
        self._doc.add_paragraph('【書類名】　　　　　　　　　商標権存続期間更新登録申請書（補充）')
        self._doc.add_paragraph('')

        if not self._date is None:
            d_txt = '{}年{}月{}日'.format(self._date.year, self._date.month, self._date.day)
        else:
            d_txt = '    年  月  日'
        self._doc.add_paragraph('【提出日】　　　　　　　　　' + d_txt)
        self._doc.add_paragraph('')

        self._doc.add_paragraph('【あて先】　　　　　　　　　特許庁長官殿')
        self._doc.add_paragraph('')

        self._doc.add_paragraph('【商標登録番号】　　　　　　商標登録第%s号' % reg_num)
        self._doc.add_paragraph('')

        s = '【商品及び役務の区分】　　　'
        for i in range(len(classes)):
            if i > 0:
                s += '、'
            s += '第%s類' % mojimoji.han_to_zen(classes[i])
        self._doc.add_paragraph(s)
        self._doc.add_paragraph('')

        for holder in holders:
            self._doc.add_paragraph('【更新登録申請人】')
            self._doc.add_paragraph('')
            if 'Id' in holder:
                self._doc.add_paragraph('　　【識別番号】　　　　　　%s' % mojimoji.han_to_zen(holder['Id']))
            else:
                self._doc.add_paragraph('　　【識別番号】　　　　　　')
            self._doc.add_paragraph('')
            self._doc.add_paragraph('　　【氏名又は名称】　　　　%s' % mojimoji.han_to_zen(holder['Name']))
            self._doc.add_paragraph('')

        self._doc.add_paragraph('【代理人】')
        self._doc.add_paragraph('')
        self._doc.add_paragraph('　　【識別番号】　　　　　　１００１８５６９４')
        self._doc.add_paragraph('')
        self._doc.add_paragraph('　　【氏名又は名称】　　　　山下　隆志')
        self._doc.add_paragraph('')
        self._doc.add_paragraph('　　【電話番号】　　　　　　０９０－９８１７－２９２４')
        self._doc.add_paragraph('')

        self._doc.add_paragraph('【提出物件の目録】')
        self._doc.add_paragraph('')
        self._doc.add_paragraph('　　【物件名】　　　　　　　委任状　　　１')
        self._doc.add_paragraph('')

        # ここから、委任状
        self._doc.new_page()

        if self._date:
            d_txt = '令和{}年{}月{}日'.format(
                mojimoji.han_to_zen(str(self._date.year - 2018)),
                mojimoji.han_to_zen(str(self._date.month)),
                mojimoji.han_to_zen(str(self._date.day)))
        else:
            d_txt = '令和　　年　　月　　日'

        names = [x['Name'] for x in holders]
        addrs = [x['Address'] if 'Address' in x else '' for x in holders]

        insert_delegation(self._doc, d_txt, reg_num, names, addrs=addrs, font_size=10.5)

    def get_binary(self):
        """
        Docxデータを取得
        """
        return self._doc.get_binary()

if __name__ == '__main__':
    from datetime import datetime
    bin = abandonment(datetime.now())
    bin.add_item(
        '12345',
        ['39', '44',],
        ['権利者名が入ります。権利者名が入ります。権利者名が入ります。権利者名が入ります。株式会社',],
        addrs=['権利者住所が入ります。権利者住所が入ります。権利者住所が入ります。権利者住所が入ります。権利者住所が入ります。']
    )
    #bin = koshin_shinsei_hoju(datetime.now())
    #bin.add_item(
    #    '12345',
    #    ['39', '44',],
    #    [
    #        {'Id': '123456789', 'Name': 'ああああああ株式会社',},
    #        {'Id': '923456789', 'Name': 'あああああい株式会社', 'Address': 'アイチケン',},
    #    ]
    #)
    bin = bin.get_binary()
    with open('log/out.docx', 'wb') as fout:
        fout.write(bin)
