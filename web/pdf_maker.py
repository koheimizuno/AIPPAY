import logging
from PyPDF2 import PdfFileReader, PdfFileWriter
import io
import unicodedata
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def text_width(text):
    """
    全角を1としたテキストの幅を取得する
    """
    if not isinstance(text, str):
        return 0.0
    l = 0.0
    for c in text:
        eaw = unicodedata.east_asian_width(c)
        l += 1.0 if eaw in ('F', 'W', 'A') else 0.5
    return l

def wrap_text(text, length):
    """
    テキストの折り返し分割
    """
    assert length > 0.0
    lines = []
    # 改行で分割
    for t in re.split(r'(\r\n|\r|\n)', text):
        # 改行文字はスキップする
        if re.fullmatch(r'[\r\n]+', t):
            continue
        # 空行も維持する
        if t == '':
            lines.append('')
            continue
        # 折り返し処理
        while t != '':
            line = ''
            while t != '' and text_width(line + t[0]) <= length:
                line += t[0]
                t = t[1:]
            while t != "" and t[0] in (',', '.', '、', '。', '・',):
                line += t[0]
                t = t[1:]
                t = re.sub(r'^\s+', '', t)
            lines.append(line)
    # 結果を返す
    return lines

class PdfMaker(object):
    """
    PDF生成機能
    注意: 単位系はpt
    """

    def __init__(self, font_file_name = 'ipag.ttf', fonts=[]):
        """
        コンストラクター
        """
        if fonts is None:
            fonts = []
        tmp = [{'name': 'IPAG', 'file': font_file_name},]
        fonts = tmp + fonts
        self.__default_font = 'IPAG'
        self.__fonts = {}
        if fonts:
            for font in fonts:
                if 'index' in font:
                    pdfmetrics.registerFont(TTFont(font['name'], str(Path(__file__).parent / 'font' / font['file']), subfontIndex=font['index']))
                else:
                    pdfmetrics.registerFont(TTFont(font['name'], str(Path(__file__).parent / 'font' / font['file'])))
                self.__default_font = font['name']
                self.__fonts[font['name']] = font
        self.__buff = io.BytesIO()
        self.__canvas = canvas.Canvas(self.__buff, pagesize=A4)
        self.__page_count = 0

    @property
    def height(self):
        """
        ページの高さ
        """
        return A4[1]

    @property
    def width(self):
        """
        ページの幅
        """
        return A4[0]

    def set_title(self, title):
        """
        タイトルの設定
        """
        self.__canvas.setTitle(title)

    def set_author(self, author):
        """
        作成者の設定
        """
        self.__canvas.setAuthor(author)

    def new_page(self):
        """
        新しい（次の）ページの生成を始める
        """
        # 既存のページを確定する
        if self.__page_count > 0:
            self.__canvas.showPage()
        self.__page_count += 1

    def __set_stroke_color(self, color):
        """
        ストロークを設定
        """
        if isinstance(color, list) or isinstance(color, tuple):
            self.__canvas.setStrokeColorRGB(color[0], color[1], color[2])
        else:
            self.__canvas.setStrokeColorRGB(color, color, color)

    def __set_stroke_width(self, width):
        """
        ストロークの太さを設定
        """
        self.__canvas.setLineWidth(width)

    def __set_dash(self):
        """
        線を破線に切り替える
        """
        self.__canvas.setDash(5, 3)

    def __unset_dash(self):
        """
        破線の指定を解除する
        """
        self.__canvas.setDash([])

    def __set_fill_color(self, color):
        """
        ストロークを設定
        """
        if isinstance(color, list) or isinstance(color, tuple):
            self.__canvas.setFillColorRGB(color[0], color[1], color[2])
        else:
            self.__canvas.setFillColorRGB(color, color, color)

    def put_text(self, x, y, text, font_size=10.5, align_center=False, align_right=False, color=0.0, underline=False, wrap_cols=99999.0, font_name=None, line_height=10.6):
        """
        テキストを追加する
        """
        # パラメーターのチェック
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if text.strip() == "":
            return 0
        if font_size is None or font_size <= 0:
            font_size = 10.5
        font_size = float(font_size)

        # Y座標の換算
        y = self.height - y - font_size

        # 描画の開始
        self.__set_fill_color(color if not color is None else self.default_font_color)
        if font_name:
            self.__canvas.setFont(font_name, font_size)
        else:
            self.__canvas.setFont(self.__default_font, font_size)

        # 折り返し処理をしながらテキストを配置
        rcnt = 0
        for line in wrap_text(text, wrap_cols):
            line = re.sub(r'[\r\n]+$', '', line)
            if align_right:
                offset = self.calc_text_width(text, font_size=font_size, font_name=font_name)
            elif align_center:
                offset = self.calc_text_width(text, font_size=font_size, font_name=font_name) / 2.0
            else:
                offset = 0
            self.__canvas.drawString(x - offset, y, line)
            if underline:
                y -= 2.0
                self.__set_stroke_color((0, 0, 0))
                self.__canvas.line(x - offset, y, x - offset + (text_width(line) * font_size), y)
            y -= line_height
            rcnt += 1
        return rcnt

    def calc_text_width(self, text, font_size=10.5, font_name=None):
        """
        文字列の描画幅を計算する
        """
        if font_name is None:
            font_name = self.__default_font
        if font_name is None or not font_name in self.__fonts:
            return text_width(text) * font_size

        fi = self.__fonts[font_name]
        if 'index' in fi:
            font = ImageFont.truetype(str(Path(__file__).parent / 'font' / fi['file']), int(font_size), index=fi['index'])
        else:
            font = ImageFont.truetype(str(Path(__file__).parent / 'font' / fi['file']), int(font_size))
        
        img = Image.new("RGB", (800, 600))
        draw = ImageDraw.Draw(img)
        bbox = draw.multiline_textsize(text, font=font)
        return bbox[0]

    def put_image(self, x, y, image, max_width=None, max_height=None):
        """
        イメージを追加する
        """
        # 画像を読み込んでサイズをチェックする
        im = Image.open(image)
        v_ratio = 1.0
        h_ratio = 1.0
        if max_width:
            if im.size[0] > max_width:
                h_ratio = float(max_width) / float(im.size[0])
        if max_height:
            if im.size[1] > max_height:
                v_ratio = float(max_height) / float(im.size[1])
        if v_ratio > h_ratio:
            ratio = h_ratio
        else:
            ratio = v_ratio
        
        # 描画サイズを計算
        width = int(im.size[0] * ratio)
        height = int(im.size[1] * ratio)

        # Y座標の換算
        y = self.height - y - height

        # 画像の描画
        self.__canvas.drawInlineImage(im, x, y, width=width, height=height)

    def draw_line(self, x1, y1, x2, y2, color, dash=False):
        """
        線を描画する
        """
        # Y座標の換算
        y1 = self.height - y1
        y2 = self.height - y2

        # 破線の設定
        if dash:
            self.__set_dash()
            self.__set_stroke_width(0.5)

        # 描画
        self.__set_stroke_color(color)
        self.__canvas.line(x1, y1, x2, y2)

        # 破線の解除
        if dash:
            self.__unset_dash()
            self.__set_stroke_width(1.0)

    def draw_rect(self, x, y, w, h, stroke=None, fill=None):
        """
        四角形を描画する
        """
        # 要否判定
        if stroke is None and fill is None:
            return
        if w <= 0.0 or h <= 0.0:
            return

        # Y座標の換算
        y = self.height - y - h

        has_stroke = 0
        has_fill = 0

        # 色の設定
        if not stroke is None:
            self.__set_stroke_color(stroke)
            has_stroke = 1
        if not fill is None:
            self.__set_fill_color(fill)
            has_fill = 1

        # 描画
        self.__canvas.rect(x, y, w, h, stroke=has_stroke, fill=has_fill)

    def get_binary(self):
        """
        生成したPDFをバイナリーデータとして取得する
        """
        if self.__page_count > 0:
            self.__canvas.showPage()
            self.__canvas.save()
        return self.__buff.getvalue()

    def __enter__(self):
        """
        Enter
        """
        return self

    def __exit__(self, ex_type, ex_value, trace):
        """
        Exit
        """
        pass

    def draw_margin_frame(self):
        """
        デバッグ用: 余白枠を表示する
        """
        mm = 0.3528
        self.draw_rect(10 / mm, 10 / mm, self.width - (2 * 10 / mm), self.height - (2 * 10 / mm), stroke=(1, 0, 0))
