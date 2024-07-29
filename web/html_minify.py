import re
import io

def __minify_text(text):
    """
    テキストを圧縮
    """
    olen = len(text)
    # コメントを削除
    text = re.sub(r'<!--.*-->', '', text, flags=re.DOTALL)
    # 改行を空白にする
    text = re.sub(r'\s+', ' ', text)
    # 前後空白の除去
    text = text.strip()
    #if len(text) == 0 and olen > 0:
    #    return ' '
    return text.strip()

def __minify_attr(attr):
    """
    属性を圧縮
    """
    attrs = []
    for m in re.finditer(r'((\w+:)?[\w\-_]+)(\s*=\s*(("?).*?\5))?', attr):
        if m.group(3):
            attrs.append('%s=%s' % (m.group(1), m.group(4)))
        else:
            attrs.append(m.group(1))
    if len(attrs) > 0:
        return ' '.join(attrs)
    else:
        return ''

def __minify_js(js):
    """
    JavaScriptを圧縮
    """
    # コメントを削除
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.DOTALL)
    js = re.sub(r'^\s*//.*$', '', js, flags=re.MULTILINE)
    def __minify_code(code):
        # 空白を削除
        code = re.sub(r'\s+', ' ', code)
        return code
    with io.StringIO() as buff:
        while js != '':
            txt = re.search(r'(["\']).*?\1', js, flags=re.DOTALL)
            if txt is None:
                buff.write(__minify_code(js))
                break
            if txt.start() > 0:
                buff.write(__minify_code(js[:txt.start()]))
            buff.write(txt.group(0))
            js = js[txt.end():]
        js = buff.getvalue()
        return js

def __minify_css(css):
    """
    スタイルシートを圧縮
    """
    # コメントを削除
    css = re.sub(r'//.*\n', '', css)
    css = re.sub(r'/\*\*.\*\*/', '', css, flags=re.DOTALL)
    # インデントを削除
    css = re.sub(r'(\n)\s*', ' ', css)
    return css

def minify(origin):
    """
    HTMLを圧縮
    """
    with io.StringIO() as buff:

        while origin != '':

            # タグを探す
            m = re.search(r'<(/?)([\w\-_]+)(\s+.*?)?>', origin, flags=re.DOTALL)

            # タグが見つからなければ終端
            if m is None:
                buff.write(__minify_text(origin))
                break

            # タグより前のテキストを処理
            if m.start() > 0:
                buff.write(__minify_text(origin[:m.start()]))

            # タグの開始
            buff.write('<')

            # 終了タグ
            if m.group(1):
                buff.write(m.group(1))

            # タグ本体
            tag = m.group(2).lower()
            buff.write(tag)

            # 属性の処理
            if m.group(3) and m.group(3) != '':
                attr = __minify_attr(m.group(3))
                if attr != '':
                    buff.write(' ' + attr)

            # タグの完了
            buff.write('>')

            # タグに応じた処理
            if m.group(1) is None or m.group(1) != '/':

                if tag == 'script':

                    # JavaScriptを処理
                    origin = origin[m.end():]
                    m2 = re.match(r'(.*?)</script\s*>', origin, flags=(re.DOTALL + re.IGNORECASE))
                    assert m2, 'no end of script'

                    buff.write(__minify_js(m2.group(1)))
                    buff.write('</script>')
                    origin = origin[m2.end():]
                    continue

                elif tag == 'style':

                    # スタイルシートを処理
                    origin = origin[m.end():]
                    m2 = re.match(r'(.*?)</style\s*>', origin, flags=(re.DOTALL + re.IGNORECASE))
                    assert m2, 'no end of style'

                    buff.write(__minify_css(m2.group(1)))
                    buff.write('</style>')
                    origin = origin[m2.end():]
                    continue

                elif tag in ('textarea', 'pre',):

                    # そのまま出力する要素
                    origin = origin[m.end():]
                    m2 = re.match(r'(.*?)</%s\s*>' % re.escape(tag), origin, flags=(re.DOTALL + re.IGNORECASE))
                    assert m2, 'no end of %s' % tag

                    buff.write(m2.group(1))
                    buff.write('</%s>' % tag)
                    origin = origin[m2.end():]
                    continue

            # 処理済の部分を削る
            origin = origin[m.end():]

        # 処理結果
        html = buff.getvalue()

        # 圧縮結果を返す
        return buff.getvalue()

if __name__ == '__main__':
    with open('sample.html', 'r', encoding='utf-8') as fin:
        html = fin.read()
        #minify(html)
        print(minify(html))
