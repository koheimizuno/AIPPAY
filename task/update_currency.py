from database import DbClient
import requests
from bs4 import BeautifulSoup
from datetime import datetime

def main():
    """
    為替レートの更新
    """
    # X-RATES
    res = requests.get('https://www.x-rates.com/table/?from=JPY&amount=1')
    doc = BeautifulSoup(res.content, 'lxml')

    # JPY基準のテーブルを取得
    e1 = doc.find('table', {'class': 'tablesorter ratesTable'})

    # 表示名と通貨コードのマッピング
    map = {
        'Chinese Yuan Renminbi': 'CNY',
        'Euro': 'EUR',
        'South Korean Won': 'KRW',
        'Taiwan New Dollar': 'TWD',
        'US Dollar': 'USD',
    }

    with DbClient() as db:

        # 該当通貨を探す
        for row in e1.findAll('tr'):

            cells = row.findAll('td')
            if len(cells) == 0:
                continue

            # 通貨の名称を取得
            name = cells[0].get_text()
            if name in map:

                # レートを取得
                rate = float(cells[1].get_text())

                # DBを更新
                db.Currencies.update_one(
                    {'_id': map[name]},
                    {'$set': {
                        'Rate': rate,
                        'RateUpdated': datetime.now(),
                        'RateBy': 'X-RATES',
                    }}
                )


if __name__ == '__main__':
    main()
