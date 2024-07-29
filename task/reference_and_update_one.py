from datetime import datetime, timedelta
import re
import logging
import traceback
from pathlib import Path
import mojimoji

from database import DbClient
import jpp_browser
import patent_reference
import jp_calendar
import common_util
import language
from local_config import Config

conf = Config()
log_file = None

if conf['log']['directory']:
    log_file = Path(conf['log']['directory']) / 'reference_and_update.log'

logging.basicConfig(
    filename=str(log_file) if log_file else None,
    level=logging.INFO if log_file else logging.DEBUG,
    format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s'
)
logger = logging.getLogger('jpo_inquire')

def get_keys(db, law, number):
    """
    照会対象のキーを抽出する
    """
    keys = []

    # 検索クエリー
    props = db.Properties.find({
        '$and':[
            {'Ignored': {'$exists': False}},
            {'Country': 'JP'},
            {'Law': law},
            {'RegistrationNumber': number},
        ]
    })

    for prop in props:

        # 検索キー・優先度
        key = {
            '_id': prop['_id'],
            'Country': prop['Country'],
            'Law': prop['Law'],
            'RegistrationNumber': prop['RegistrationNumber'],
            'Priority': 300,
        }
        keys.append(key)

        # 納付済年分がない
        if not 'PaidYears' in prop:
            if 'AutoInquiredTime' in prop and prop['AutoInquiredTime'] > (datetime.now() - timedelta(days=30)):
                key['Priority'] = 1
            else:
                key['Priority'] = 999
            continue

        # 手続の完了から1～3ヶ月
        if not 'AutoInquiredSuccessTime' in prop or prop['AutoInquiredSuccessTime'] < (datetime.now() - timedelta(days=90)):
            req = db.Requests.find_one({'$and':[
                {'CanceledTime': {'$exists': False}},
                {'Properties': {'$elemMatch': {
                    'Property': prop['_id'],
                    '$and': [
                        {'CompletedTime': {'$lt': datetime.now() - timedelta(days=30)}},
                        {'CompletedTime': {'$gt': datetime.now() - timedelta(days=90)}},
                    ],
                    'CanceledTime': {'$exists': False},
                }}}
            ]}, {'_id': 1})
            if not req is None:
                key['Priority'] = 800
                continue

        # 1度も自動照会されていない
        if not 'AutoInquiredTime' in prop:
            key['Priority'] = 400
            continue

    # 並べ替え (1:優先度, 2:前回照会日)
    keys = sorted(keys, key=lambda x: x['AutoInquiredTime'] if 'AutoInquiredTime' in x else datetime(1900, 1, 1))
    keys = sorted(keys, key=lambda x: x['Priority'], reverse=True)

    # 未照会分を抽出する
    for prop in keys:

        # 依頼処理中の案件はスキップ（更新不可）
        if common_util.under_process(db, prop['_id'], include_cart=True):
            continue

        # 照会候補として返す
        yield prop

def inquire_one(db, law, number):
    """
    登録済みの権利についてJ-PlatPatを照会する
    """
    # 開始時刻
    started_time = datetime.now()

    # 言語設定の取得
    lang = language.get_dictionary('ja')

    for key in get_keys(db, law, number):

        # 開始から6時間経過していたら終了する
        if (datetime.now() - started_time).total_seconds() > (6 * 60 * 60):
            logger.warning('%s is running too long. stop this process.', __name__)
            break

        logger.info('reference and update ... %s/%s/%s/%s/%s', key['_id'], key['Country'], key['Law'], key['RegistrationNumber'], key['Priority'])

        # 権利情報の照会
        data, msg = patent_reference.refer(key['Country'], key['Law'], key['RegistrationNumber'], 'registration', lang, exception_on_maintenance=True)

        if data is None:
            logger.warning('patent infomation is not found.')
            if msg:
                logger.warning(msg)
            db.Properties.update_one({'_id': key['_id']}, {'$set': {
                'AutoInquiredTime': datetime.now(),
            }})
            continue

        # 現在の登録情報を取得
        current = db.Properties.find_one({'_id': key['_id']})

        query = {
            '$set': {},
            '$unset': {},
        }

        # 取得した情報を更新クエリーに反映
        for key in data.keys():
            if key in ('Country', 'Law', 'RegistrationNumber',):
                continue
            if key in ('HolderNames', 'RegistrationNumberPrefix',):
                continue
            query['$set'][key] = data[key]

        query['$set']['AutoInquiredTime'] = datetime.now()
        query['$set']['AutoInquiredSuccessTime'] = query['$set']['AutoInquiredTime']
        if not 'FirstAutoInquiredTime' in key:
            query['$set']['FirstAutoInquiredTime'] = query['$set']['AutoInquiredTime']
        query['$set']['InquiredTime'] = query['$set']['AutoInquiredTime']
        query['$set']['ModifiedTime'] = query['$set']['AutoInquiredTime']

        # 消滅判定
        if 'DisappearanceDate' in data:
            query['$set']['Disappered'] = True
        if 'ExpirationDate' in data and data['ExpirationDate'] < common_util.add_months(common_util.get_today(), -7):
            query['$set']['Disappered'] = True

        if len(query['$unset']) == 0:
            del query['$unset']

        # データベースを更新する
        db.Properties.update_one({'_id': current['_id']}, query)

        # 次回手続期限を更新する
        common_util.renew_limit_date(db, current['_id'])

# 照会処理の実行
with DbClient() as db:
    inquire_one(db, 'Patent', '5154103')
