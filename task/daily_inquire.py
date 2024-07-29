import logging
import io
import os
import tarfile
import re
from datetime import datetime, timedelta
from pathlib import Path
import traceback

from database import DbClient
from jpo_bulk_data import Browser
import common_util
from local_config import Config

conf = Config()
log_file = None

if conf['log']['directory']:
    log_file = Path(conf['log']['directory']) / 'daily_inquire.log'

logging.basicConfig(
    filename=str(log_file) if log_file else None,
    level=logging.INFO if log_file else logging.DEBUG,
    format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s'
)

logger = logging.getLogger('daily_inquire')

def read_tsv(target):
    """
    タブ区切りテキストを読み込む
    """
    # ストリームの調整
    if not isinstance(target, io.BufferedReader):
        raise TypeError('%s is not BufferedReader' % target)
    wrapper = io.TextIOWrapper(target, encoding='utf-8')

    # 1行目を読み込み
    line = wrapper.readline()
    cnt = 0

    while line:

        line = line.rstrip()

        if line != '':

            if cnt == 0:

                # 1行目をフィールド名の定義として読み込む
                headers = line.split('\t')

            else:

                # フィールドに分割
                values = [x if x.strip() != '' else None for x in line.split('\t')]

                # ヘッダーと対応付ける
                info = {}
                for i in range(len(values)):
                    if values[i]:
                        info[headers[i]] = values[i]

                # 1行分のドキュメントを返す
                yield info

            cnt += 1

        # 次の行
        line = wrapper.readline()


def extract_and_import(filepath, db):
    """
    1ファイルをインポートする
    """
    # 展開
    with tarfile.open(filepath, mode='r:gz') as tf:

        # メンバーリストの取得
        members = { Path(m.name).name: m for m in tf.getmembers() }

        # 法域ごとにチェックする
        for law, c in (('Patent', 'p'), ('Utility', 'u'), ('Design', 'd'), ('Trademark', 't')):

            # 管理情報ファイル（の更新データ）が含まれるかチェックする
            name = 'upd_mgt_info_%s.tsv' % c

            if not name in members:
                continue

            # 管理情報ファイルを展開する
            with tf.extractfile(members[name]) as ef:

                for info in read_tsv(ef):

                    # 登録番号を取得する
                    reg_num = common_util.pad0(info['reg_num'], length=7)

                    # 既存の登録を調べる
                    props = list(db.Properties.find({
                        'Country': 'JP',
                        'Law': law,
                        'RegistrationNumber': reg_num,
                        'Ignored': {'$exists': False}
                    }))

                    # 該当がなければスキップする
                    if len(props) < 1:
                        continue

                    logger.debug('[%s] (props) are found for updating.', ','.join([str(x['_id']) for x in props]))

                    # 更新情報を生成する
                    update = {}

                    # 存続期間満了日
                    if 'conti_prd_expire_ymd' in info and info['conti_prd_expire_ymd'] != '00000000':
                        update['ExpirationDate'] = datetime.strptime(info['conti_prd_expire_ymd'], '%Y%m%d')

                    # 次回手続期限
                    if 'next_pen_pymnt_tm_lmt_ymd' in info and info['next_pen_pymnt_tm_lmt_ymd'] != '00000000':
                        update['NextProcedureLimit'] = datetime.strptime(info['next_pen_pymnt_tm_lmt_ymd'], '%Y%m%d')

                    # 最終納付年分
                    if 'last_pymnt_yearly' in info and info['last_pymnt_yearly'] != '00':
                        update['PaidYears'] = int(info['last_pymnt_yearly'])

                    # 消滅日
                    if 'right_disppr_year_month_day' in info and info['right_disppr_year_month_day'] != '00000000':
                        update['DisappearanceDate'] = datetime.strptime(info['right_disppr_year_month_day'], '%Y%m%d')

                    # 出願日
                    if 'app_year_month_day' in info and info['app_year_month_day'] != '00000000':
                        update['ApplicationDate'] = datetime.strptime(info['app_year_month_day'], '%Y%m%d')

                    # 登録日
                    if 'set_reg_year_month_day' in info and info['set_reg_year_month_day'] != '00000000':
                        update['RegistrationDate'] = datetime.strptime(info['set_reg_year_month_day'], '%Y%m%d')

                    # 請求項の数
                    if 'invent_cnt_claim_cnt_cls_cnt' in info and info['invent_cnt_claim_cnt_cls_cnt'] != '000':
                        update['NumberOfClaims'] = int(info['invent_cnt_claim_cnt_cls_cnt'])

                    # 発明等の名称
                    if 'invent_title_etc' in info:
                        update['Subject'] = common_util.zen_to_han(info['invent_title_etc'])

                    # 権利者ファイルを探す
                    name2 = 'upd_right_person_art_%s.tsv' % c

                    if name2 in members:

                        holders = []

                        with tf.extractfile(members[name2]) as ef2:

                            for info2 in read_tsv(ef2):

                                if info2['law_cd'] == info['law_cd'] \
                                    and info2['reg_num'] == info['reg_num']:
                                    doc = {}
                                    if 'right_person_appl_id' in info2:
                                        doc['Id'] = info2['right_person_appl_id']
                                    else:
                                        # 識別番号を取得できない場合は権利者を更新しない
                                        holders = []
                                        break
                                    if 'right_person_name' in info2:
                                        doc['Name'] = common_util.zen_to_han(info2['right_person_name'])
                                    if len(doc) > 0:
                                        holders.append(doc)

                        if len(holders) > 0:
                            update['Holders'] = holders

                    # 指定区分ファイルを探す
                    name2 = 'upd_goods_class_art.tsv'

                    if name2 in members:

                        classes = []

                        with tf.extractfile(members[name2]) as ef2:

                            for info2 in read_tsv(ef2):

                                if info2['law_cd'] == info['law_cd'] \
                                    and info2['reg_num'] == info['reg_num']:
                                    if 'desig_goods_or_desig_wrk_class' in info2:
                                        classes.append(info2['desig_goods_or_desig_wrk_class'])

                            if len(classes) > 0:
                                update['Classes'] = classes
                                update['NumberOfClasses'] = len(classes)

                    # 権利（エントリー）ごとに更新する
                    for prop in props:

                        query = { '$set': {}, '$unset': {} }

                        for key in update:
                            if key in ('PaidYears', 'NextProcedureLimit',):
                                query['$set'][key] = update[key]

                        # 納付済年分
                        if 'PaidYears' in update:
                            if not 'PaidYears' in prop or prop['PaidYears'] < update['PaidYears']:
                                query['$set']['PaidYears'] = update['PaidYears']

                        # 次回手続期限
                        if 'NextProcedureLimit' in update:
                            if not 'NextProcedureLimit' in prop or prop['NextProcedureLimit'] < update['NextProcedureLimit']:
                                query['$set']['NextProcedureLimit'] = update['NextProcedureLimit']

                        # 照会日時等
                        query['$set']['JpoInquiredTime'] = datetime.now()
                        query['$set']['InquiredTime'] = query['$set']['JpoInquiredTime']
                        query['$set']['ModifiedTime'] = query['$set']['JpoInquiredTime']

                        # 更新
                        if len(query['$unset']) == 0:
                            del query['$unset']
                        db.Properties.update_one({'_id': prop['_id']}, query)

def bulk_import():
    """
    一括でダウンロード・インポートを行う
    """
    with DbClient() as db:
        with Browser('temp') as browser:
            for _, _, filepath in browser.download():
                try:
                    # インポート
                    extract_and_import(filepath, db)
                finally:
                    # ファイルの削除
                    os.remove(filepath)

def single_import(filepath):
    """
    特定のファイルをインポートする
    """
    with DbClient() as db:
        extract_and_import(filepath, db)

if __name__ == '__main__':
    single_import('sample_data/JPDRT_20200619.tar.gz')
