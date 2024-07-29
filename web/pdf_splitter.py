import PyPDF2
import re
import io
import mojimoji

import common_util
import pdf_reader

def split(pdf):
    """
    PDFファイルを読み込んで内容を解析する
    """
    pages = pdf_reader.read_pages(pdf)
    pos = [0,]

    # 2ページ目以降で「タイトル」の含まれるページを探す
    for i in range(1, len(pages)):

        page = pages[i]

        if re.search(r'^\s*商標権の一部抹消登録申請書\s*$', page, flags=re.MULTILINE):
            pos.append(i)
            continue

        if re.search(r'^\s*商標権の一部放棄書\s*$', page, flags=re.MULTILINE):
            pos.append(i)
            continue

        if re.search(r'^\s*委任状\s*$', page, flags=re.MULTILINE):
            pos.append(i)
            continue

        # 委任状は特殊（間に空白があり別の行として読み取られる）
        if re.search(r'(^|\n)(\s|\r|\u3000)*委(\s|\n|\r|\u3000)*任(\s|\n|\r|\u3000)*状(\s|\r|\u3000)*(\n|$)', page):
            pos.append(i)
            continue

    # ファイルポインターをリセット
    pdf.seek(0)

    if len(pos) == 1:
        with io.BytesIO() as buff:
            buff.write(pdf.read())
            return [buff.getvalue(),]

    # 生成されたPDF
    new_pdfs = []

    # 最終ページ
    pos.append(len(pages))

    for i in range(len(pos) - 1):
        # PDFページの結合
        merger = PyPDF2.PdfMerger()
        pdf.seek(0)
        merger.append(pdf, pages=(pos[i], pos[i+1]))
        with io.BytesIO() as buff:
            merger.write(buff)
            merger.close()
            new_pdfs.append(buff.getvalue())

    return new_pdfs

if __name__ == '__main__':
    test_file = "./log/sample1.pdf"
    with open(test_file, 'rb') as fin:
        b = fin.read()
    import io
    with io.BytesIO(b) as buff:
        d = split(buff)
    for i in range(len(d)):
        print(i)
        with open('./log/out_%d.pdf' % (i+10), 'wb') as fout:
            fout.write(d[i])
