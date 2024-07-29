from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage
import io
import logging

logging.getLogger('pdfminer.psparser').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfinterp').setLevel(logging.WARNING)
logging.getLogger('pdfminer.cmapdb').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfdocument').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfparser').setLevel(logging.WARNING)
logging.getLogger('pdfminer.pdfpage').setLevel(logging.WARNING)
logging.getLogger('pdfminer.converter').setLevel(logging.WARNING)

def read(pdf):
    """
    PDFファイルを読み取る
    """
    manager = PDFResourceManager()
    pdf.seek(0)

    with io.BytesIO() as buff:

        with TextConverter(manager, buff, codec='utf-8', laparams=LAParams()) as conv:
            interpreter = PDFPageInterpreter(manager, conv)
            for page in PDFPage.get_pages(pdf):
                interpreter.process_page(page)

        return buff.getvalue().decode('utf-8')

def read_pages(pdf):
    """
    PDFファイルをページごとに読み取る
    """
    pages = []

    manager = PDFResourceManager()
    pdf.seek(0)

    for page in PDFPage.get_pages(pdf):
        with io.BytesIO() as buff:
            with TextConverter(manager, buff, codec='utf-8', laparams=LAParams()) as conv:
                interpreter = PDFPageInterpreter(manager, conv)
                interpreter.process_page(page)
            pages.append(buff.getvalue().decode('utf-8'))

    return pages

if __name__ == '__main__':
    with open('./log/sample.pdf', 'rb') as sample:
        print(read_pages(sample))