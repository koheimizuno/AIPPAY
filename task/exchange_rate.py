import logging
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

from database import DbClient
from local_config import Config

conf = Config()
log_file = None

if conf['log']['directory']:
    log_file = Path(conf['log']['directory']) / 'exchange_rate.log'

logging.basicConfig(
    filename=str(log_file) if log_file else None,
    level=logging.INFO if log_file else logging.DEBUG,
    format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s'
)

logger = logging.getLogger('exchange_rate')


import requests
from bs4 import BeautifulSoup
import logging

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_rate(s, t):
    """
    換算レートを取得する
    ----
    Params:
        s  換算元通貨（コード）
        t  換算先通貨（コード）
    """
    # Yahoo!ファイナンスのURLを生成
    url = "https://info.finance.yahoo.co.jp/fx/convert/?a=1&s=%s&t=%s" % (s, t)

    # ページ読み込み
    res = requests.get(url)

    if res.status_code != 200:

        # HTTP200 以外はエラーとして扱う
        logger.warning('HTTP ERROR %d: %s', res.status_code, url)

    else:

        # 解析
        page = BeautifulSoup(res.text, "lxml")
        elem1 = page.select('#main table.fxRateTbl td.newest')

        if len(elem1) > 0 and len(elem1[0].contents) > 0:
            text = float(elem1[0].contents[0])
            try:
                v = float(text)
                if v > 0:
                    return v, 'Yahoo'
                else:
                    logger.warning('invalid currency rate data 0.0 (%s -> %s) at Yahoo!Finance.', s, t)
            except ValueError:
                logger.warning('invalid currency rate data %s (%s -> %s) at Yahoo!Finance.', text, s, t)
        else:
            logger.warning('Cannot get a currency rate %s -> %s at Yahoo!Finance.', s, t)

    # ロイターのURLを生成
    url = "https://jp.reuters.com/quote/%s%s" % (s, t)

    # ページ読み込み
    res = requests.get(url)

    if res.status_code != 200:

        # HTTP200 以外はエラーとして扱う
        logger.warning('HTTP ERROR %d: %s', res.status_code, url)

    else:

        # 解析
        page = BeautifulSoup(res.text, "lxml")
        elem1 = page.find(text='現在値')

        if elem1 is None or elem1.parent is None or elem1.parent.next_sibling is None:

            logger.warning('Cannot get a currency rate %s -> %s at REUTERS.', s, t)

        else:

            text = elem1.parent.next_sibling.text

            try:
                v = float(text)
                if v > 0:
                    return v, 'REUTERS'
                else:
                    logger.warning('invalid currency rate data 0.0 (%s -> %s) at REUTERS.', s, t)
            except ValueError:
                logger.warning('invalid currency rate data %s (%s -> %s) at REUTERS.', text, s, t)

    return None, None

def update_all():
    """
    すべての通貨設定を更新する
    """

    with DbClient() as db:

        # 通貨のリストを取得
        currencies = [x['_id'] for x in db.Currencies.find({}, {'_id':1})]

        for i in range(len(currencies)):

            for j in range(len(currencies)):

                # 通貨ペア
                base = currencies[i]
                opp = currencies[j]

                if base == opp:
                    continue

                # 換算レートを取得する
                rate, src = get_rate(base, opp)

                if not rate is None:

                    # レートを取得できていれば更新
                    db.Currencies.update_one(
                        { '_id': base, },
                        { '$set': {
                            opp: rate,
                        }}
                    )

if __name__ == '__main__':
    update_all()