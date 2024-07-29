import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from pathlib import Path
from PIL import Image

def stamp(pdf):

    # 既存のファイル読み込み
    input_file = PdfReader(pdf)

    # 新規の出力ファイル作成
    output_file = PdfWriter()

    # ページ数
    page_number = 0

    # 既存の全体ページをループで回す
    for input_page in input_file.pages:

        if page_number == 0:

            # 最初のページに収入印紙画像を合成
            with io.BytesIO() as buff:

                tmp = canvas.Canvas(buff)
                tmp.setPageSize(A4)

                # 画像ファイルのベースディレクトリー
                img_path = Path(__file__).parent / 'pict'

                # 画像を読み込む
                im = Image.open(str(img_path / 'shunyu_inshi.jpg'))

                # 画像の描画
                # 696x752
                tmp.drawInlineImage(im, 58, 635, width=87, height=94)

                tmp.showPage()
                tmp.save()

                buff.seek(0)

                # PDFとして読み込み
                stamp_pdf = PdfReader(buff)

                # PDFページのマージ
                input_page.merge_page(stamp_pdf.pages[0])

        # 出力ファイルにページを追加する
        output_file.add_page(input_page)

        page_number += 1

    with io.BytesIO() as buff:
        output_file.write(buff)
        return buff.getvalue()

if __name__ == '__main__':
    with open('./log/sample.pdf', 'rb') as fin:
        d = stamp(fin)
        with open('./log/sample_stamp.pdf', 'wb') as fout:
            fout.write(d)