import re
import mojimoji
from datetime import datetime
import common_util
import pdf_reader

def parse(pdf):
    """
    PDFファイルを読み込んで内容を解析する
    """
    return parse_content(pdf_reader.read(pdf))

def parse_content(text):
    """
    コンテンツを解析する
    """
    # 全角スペースを半角に統一(正規表現対応)
    text = re.sub(r'\u3000', ' ', text)

    # 改行を統一
    text = re.sub(r'\r\n', '\n', text)

    # 年金領収書の判定
    m = re.search(r'(年金領収書|商標更新登録)の通知', text)

    if m:

        # 提出日の読み取り
        m2 = re.search(r'^\s*(令和\s*[0-9０-９]{1,2}年\s*[0-9０-９]{1,2}月\s*[0-9０-９]{1,2}日)\s*$', text, flags=re.MULTILINE)
        if m2:
            doc_date = common_util.parse_date(m2.group(1))
        else:
            doc_date = None

        # 解析結果を返す
        return m.group(1), 'JP', doc_date, []

    # 日本特許庁の受領書を判定
    m = re.search(r'^\s+受領書\s*$', text, flags=re.MULTILINE)

    if m:
        title = '受領書'
        country = 'JP'
        submit_date = None

        # 提出日の読み取り
        m2 = re.search(r'^\s*(令和\s*[0-9０-９]{1,2}年\s*[0-9０-９]{1,2}月\s*[0-9０-９]{1,2}日)\s*$', text, flags=re.MULTILINE)
        if m2:
            submit_date = common_util.parse_date(m2.group(1))

        # 明細の見出し行を探す
        m = re.search(r'^\s*項番.*アクセスコード\s*$', text, flags=re.MULTILINE)

        items = []

        if m:

            # 明細を行ごとに処理
            for line in text[m.end()+1:].split('\n'):

                #「以上」の行が来たら終わり
                if re.match(r'^\s*以\s*上\s*$', line):
                    break

                # 手続名を調べる
                m = re.search(r'^\s*\d+\s*(\S*)', line)
                if m:
                    sub_title = m.group(1)
                else:
                    continue

                # 提出日と権利番号を取得
                m = re.search(r'(令\s*\d*\.\s*\d*\.\s*\d*)\s*(\S*)', text)
                if m:
                    submit_date = common_util.parse_date(m.group(1))
                    m = re.match(r'(特許|実用新案登録|意匠登録|商標登録)(\S+)', m.group(2))
                    if m:
                        if m.group(1) == '特許':
                            law = 'Patent'
                        elif m.group(1).startswith('実'):
                            law = 'Utility'
                        elif m.group(1).startswith('意'):
                            law = 'Design'
                        elif m.group(1).startswith('商'):
                            law = 'Trademark'
                        else:
                            law = None
                        reg_num = mojimoji.zen_to_han(m.group(2))
                    else:
                        continue
                else:
                    continue

                item = {
                    'Law': law,
                    'RegistrationNumber': reg_num,
                    'Country': 'JP',
                    'Title': sub_title,
                    'SubmitDate': submit_date,
                }
                items.append(item)

        # 明細の見出し行を探す
        m = re.search(r'^\s*項番.*書類カテゴリ.*筆頭物件\(事件情報\)\s*$', text, flags=re.MULTILINE)

        if m:

            title = '受領書(登録中間手続書類)'

            for m in re.finditer(r'(令\s*\d*\.\s*\d*\.\s*\d*)\s*(\S*)[^\r\n]*(登録中間手続書類（移転申請以外）)[\s\n\r]*\((特許|実用新案登録|意匠登録|商標登録)(\d+)\)', text):

                # 提出日と権利番号を取得
                sub_title = m.group(3)
                submit_date = common_util.parse_date(m.group(1))
                if m.group(4) == '特許':
                    law = 'Patent'
                elif m.group(4).startswith('実'):
                    law = 'Utility'
                elif m.group(4).startswith('意'):
                    law = 'Design'
                elif m.group(4).startswith('商'):
                    law = 'Trademark'
                else:
                    law = None
                reg_num = mojimoji.zen_to_han(m.group(5))

                item = {
                    'Law': law,
                    'RegistrationNumber': reg_num,
                    'Country': 'JP',
                    'Title': sub_title,
                    'SubmitDate': submit_date,
                }
                items.append(item)

        ## DEBUG
        #items.append({'Law': 'Patent', 'RegistrationNumber': '5640702', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
        #items.append({'Law': 'Utility', 'RegistrationNumber': '3219627', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
        #items.append({'Law': 'Design', 'RegistrationNumber': '1624517', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
        #items.append({'Law': 'Trademark', 'RegistrationNumber': '4739471', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
        
        # 解析結果を返す
        return title, country, submit_date, items

    # 日本特許庁への手続書類を判定
    m = re.search(r'\s*【書類名】\s*(\S.*\S)\s*$', text, flags=re.MULTILINE)
    if m:

        title = m.group(1)
        country = 'JP'
        m = re.search(r'提出日:(令和\s*[0-9０-９]{1,2}年\s*[0-9０-９]{1,2}月\s*[0-9０-９]{1,2}日)', text)
        if m:
            submit_date = common_util.parse_date(m.group(1))
        else:
            m = re.search(r'^\s*【提出日】\s*(([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日)', text, flags=re.MULTILINE)
            if m:
                submit_date = common_util.parse_date(re.sub(r'\s+', '', m.group(1)))
            else:
                submit_date = None

        # 権利の番号と法域を判定
        m = re.search(r'^\s*【(特許|実用新案登録|意匠登録|商標登録)番号】\s*(特許|実用新案登録|意匠登録|商標登録)\s*第\s*(\d+.*)\s*号\s*$', text, flags=re.MULTILINE)
        if m:
            if m.group(1).startswith("特許"):
                law = 'Patent'
            elif m.group(1).startswith("実用"):
                law = 'Utility'
            elif m.group(1).startswith("意匠"):
                law = 'Design'
            elif m.group(1).startswith("商標"):
                law = 'Trademark'
            else:
                law = None
            items = [{
                'Law': law,
                'RegistrationNumber': mojimoji.zen_to_han(m.group(3).strip()),
                'Country': 'JP',
                'Title': title,
                'SubmitDate': submit_date,
            }]

            ## DEBUG
            #items.append({'Law': 'Patent', 'RegistrationNumber': '5640702', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
            #items.append({'Law': 'Utility', 'RegistrationNumber': '3219627', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
            #items.append({'Law': 'Design', 'RegistrationNumber': '1624517', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})
            #items.append({'Law': 'Trademark', 'RegistrationNumber': '4739471', 'Country': 'JP', 'Title': 'ああああ', 'SubmitDate': datetime.now(),})

            # 解析結果を返す
            return title, country, submit_date, items

    for pat in (r'^\s*商標権の一部抹消登録申請書\s*$',
                r'^\s*商標権の一部放棄書\s*$',
                r'^\s*委任状\s*$',
                r'(^|\n)\s*委(\s|\n)*任(\s|\n)*状\s*(\n|$)'):

        m = re.search(pat, text, flags=re.MULTILINE)

        if m:

            title = re.sub(r'(\s|\u30000|\r|\n|\t)+', '', m.group(0))
            country = 'JP'
            m = re.search(r'令和\s*[0-9０-９]{1,2}年\s*[0-9０-９]{1,2}月\s*[0-9０-９]{1,2}日', text)
            if m:
                submit_date = common_util.parse_date(m.group(0))
            else:
                submit_date = None

            reg_num = None
            m2 = re.search(r'商標登録番号(\s|\n)*(第\s*)?([0-9０-９]+)', text)
            if m2:
                reg_num = mojimoji.zen_to_han(m2.group(3))
            m2 = re.search(r'商標登録\s?(第\s*)?([0-9０-９]+)', text)
            if m2:
                reg_num = mojimoji.zen_to_han(m2.group(2))

            if reg_num:
                return title, country, submit_date, [{
                    'Law': 'Trademark',
                    'RegistrationNumber': reg_num,
                    'Country': country,
                    'Title': title,
                    'SubmitDate': submit_date,
                }]
    
    # 登録関連手続（移転登録申請関連手続以外）
    m = re.search(r'◆◆◆ 送付票 ◆◆◆\n\s*書類情報\n\s*書類カテゴリ\s*登録関連手続（移転登録申請関連手続以外）', text)

    if m:

        title = '登録関連手続（移転登録申請関連手続以外）'

        m = re.search(r'事件情報欄\n\s*登録番号\s+(特許|実用新案登録|意匠登録|商標登録)第(\d+)号', text)

        if m.group(1).startswith("特許"):
            law = 'Patent'
        elif m.group(1).startswith("実用"):
            law = 'Utility'
        elif m.group(1).startswith("意匠"):
            law = 'Design'
        elif m.group(1).startswith("商標"):
            law = 'Trademark'
        else:
            law = None
        reg_num = mojimoji.zen_to_han(m.group(2)).strip()

        m = re.search(r'提出日:(令和\s*[0-9０-９]{1,2}年\s*[0-9０-９]{1,2}月\s*[0-9０-９]{1,2}日)', text)
        if m:
            submit_date = common_util.parse_date(m.group(1))
        else:
            submit_date = None

        if reg_num:
            return title, 'JP', submit_date, [{
                'Law': 'Trademark',
                'RegistrationNumber': reg_num,
                'Country': 'JP',
                'Title': title,
                'SubmitDate': submit_date,
            }]

    # Unknown
    return None, None, None, None

if __name__ == '__main__':
    test_file = "./test/20240416/登録原簿240416dfce20.pdf"
    with open(test_file, 'rb') as fin:
        b = fin.read()
    import io
    with io.BytesIO(b) as buff:
        d = parse(buff)
    print(d)
