import json
from pathlib import Path
import logging
import io
import re

logger = logging.getLogger(__name__)

class Dictionary(object):
    """
    表示定義を扱う階層化された辞書
    """

    def __init__(self, d, path='', name='no name'):
        """
        コンストラクター
        """
        if not isinstance(d, dict):
            raise ValueError()
        self.__d = d
        self.__p = path
        self.__name = name

    def __getitem__(self, key):
        """
        ローカライズされたテキストの取得
        """
        p = '%s.%s' % (self.__p, key)
        if not key in self.__d:
            raise KeyError('%s is not defined at language file.' % p)
        x = self.__d[key]

        # 子エントリーを返す
        if isinstance(x, dict):
            return Dictionary(x, path=(self.__p + '.' + key if self.__p else key), name=self.name)

        # リストの場合は改行で結合する
        if isinstance(x, list):
            return '\n'.join(x)

        # 文字列型を返す
        return str(x)
    
    def __contains__(self, item):
        """
        包含判定
        """
        return item in self.__d
        
    def __str__(self):
        """
        文字列表現
        """
        t = ""
        for key in self.__d.keys():
            child = self[key]
            if isinstance(child, Dictionary):
                t += str(child) + "\n"
            else:
                t += '%s.%s=%s\n' % (self.__p, key, child)
        return t

    def format_date(self, d, ignore_year=False):
        """
        ローカライズされた日付の整形
        """
        if self.name == 'ja':
            if ignore_year:
                return '%d月%d日' % (d.month, d.day)
            else:
                return '%d年%d月%d日' % (d.year, d.month, d.day)
        else:
            if ignore_year:
                return d.strftime('%m-%d')
            else:
                return d.strftime('%Y-%m-%d')

    def format_reg_number(self, country, law, number):
        """
        登録番号を整形する
        """
        if country == 'JP':
            return self['Format']['RegistrationNumber'][law].format(number)
        else:
            return '%s %s' % (law, number)

    def format_app_number(self, country, law, number):
        """
        出願番号を整形する
        """
        if country == 'JP':
            return self['Format']['ApplicationNumber'][law].format(number)
        else:
            return '%s %s' % (law, number)
    
    def word_separator(self):
        """
        区切り文字を取得する
        """
        if self.name == 'ja':
            return '、'
        else:
            return ', '

    def local_currency(self, currency):
        """
        通貨のローカル表示
        """
        if self.name == 'ja' and currency == 'JPY':
            return '円'
        else:
            return currency

    @property
    def name(self):
        """
        名前
        """
        return self.__name

    def mail_footer(self, agent='0001'):
        """
        メールフッターを取得する
        """
        with io.StringIO() as buff:

            buff.write('\n' * 2)
            buff.write('○●---------------------------------------------------------------●○')
            buff.write('\n')

            buff.write(re.sub(r'(^|\n)\s*', r'\1    ', self['Invoice']['Agent'][agent]['MailFooter'].strip()))

            buff.write('\n')
            buff.write('○●---------------------------------------------------------------●○')
            buff.write('\n')

            return buff.getvalue()

def get_dictionary(lang='ja'):
    """
    辞書の取得
    """
    # 言語ファイルの場所
    d = Path(__file__).parent / 'lang'

    # 日本語の設定ファイルを読み込む
    with open(str(d / 'ja.json'), 'r', encoding='utf-8') as f:
        ja = json.load(f)

    # 指定言語のファイルを開く
    if lang != 'ja':
        with open(str(d / ('%s.json' % lang)), 'r', encoding='utf-8') as f:
            d = json.load(f)
            # 日本語設定を上書き
            ja.update(d)

    # 辞書を構成して返す
    return Dictionary(ja, name=lang)

if __name__ == '__main__':
    d = get_dictionary('ja')
    print(d.mail_footer())
