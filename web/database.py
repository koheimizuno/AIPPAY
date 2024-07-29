from pymongo import MongoClient
import logging
from datetime import datetime
#from filelock import Lock
from bson.objectid import ObjectId
import re
from datetime import datetime, timedelta

import common_util
import jp_calendar
import fee_calculator
from local_config import Config

# ログの初期設定
logger = logging.getLogger(__name__)

class DbClient:
    """
    MongoDB用のラッパー
    """

    def __init__(self):
        """
        コンストラクター
        """

        # コレクションのリスト
        collections = ['Users','Properties','Requests','Counters','Misc','Password','Carts','Currencies']

        # 設定ファイルから設定を取得
        config = Config()

        # データベースに接続
        self.__mongo = MongoClient(config['mongo']['host'], int(config['mongo']['port']), retryWrites=False)
        self.__db = self.__mongo[config['mongo']['db']]
        self.__db.authenticate(config['mongo']['user'], config['mongo']['pwd'])

        # インスタンスの属性としてコレクションへの参照をセットする
        for name in collections:
            setattr(self, name, self.__db[name])

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()

    def next_number(self, name):
        """
        カウンター管理の番号について、次の番号を取得する
        """
        cnt = self.Counters.find_one({'Name':name})
        while True:
            if cnt is None:
                x = 0
                self.Counters.insert_one({'Name':name, 'Current':0})
            else:
                x = cnt['Current']
            res = self.Counters.update_one({'Name':name, 'Current':x }
                , {'$inc':{'Current':1}, '$set':{'LastTime':datetime.now()}})
            if res.modified_count == 1:
                return x + 1

    def get_mail_addresses(self, user_id):
        """
        指定したユーザーのメールアドレスを取得する
        """
        # 常にBCCに保守アドレスを入れる
        bcc_addrs = ['support@isgs-lab.com',]

        # ユーザー情報を取得
        user = self.Users.find_one({'_id': user_id})
        if user is None:
            return None, [], []

        # TOアドレス
        to_addr = user['MailAddress']

        # CCアドレス
        cc_addrs = []
        if 'CcAddresses' in user:
            cc_addrs = user['CcAddresses']
        
        # 結果を返す（タプル）
        return [to_addr,], cc_addrs, bcc_addrs

    def get_staff_addresses(self):
        """
        スタッフのメールアドレスを取得する
        """
        # 常にBCCに保守アドレスを入れる
        bcc_addrs = ['support@isgs-lab.com',]

        # リスト
        to_addrs = []
        cc_addrs = []

        # ユーザー情報を取得
        for user in self.Users.find({'IsStaff': True, 'Ignored': {'$exists': False}, 'MailAddress': 'info@jipps.net'}):

            # TO
            if not user['MailAddress'] in to_addrs:
                to_addrs.append(user['MailAddress'])
            
            # CC
            if 'CcAddresses' in user:
                for cc in user['CcAddresses']:
                    if not cc in cc_addrs:
                        cc_addrs.append(cc)

        # 結果を返す（タプル）
        return to_addrs, cc_addrs, bcc_addrs

    def update_prop(self, input, user_id, update_abandonment=False, lang=None):
        """
        知的財産権の情報の更新
        """
        # パラメーター名の補正
        if not 'Id' in input:
            if '_id' in input:
                input['Id'] = input['_id']
            elif 'ID' in input:
                input['Id'] = input['ID']

        # 情報の追加 or 更新
        if 'Id' in input:
            id = input['Id']
            if not isinstance(id, ObjectId):
                id = ObjectId(id)
            is_new = False
        else:
            id = None
            is_new = True

        if is_new:

            # 国・地域の指定のチェック
            if not 'Country' in input:
                return False, None, lang['Error']['E00010'], is_new
            if input['Country'] == 'UNK' and not 'CountryDescription' in input:
                return False, None, lang['Error']['E00010'], is_new
            country = input['Country']

            # 法域の指定のチェック
            if not 'Law' in input:
                return False, None, lang['Error']['E00020'], is_new
            law = input['Law']

            # 登録番号の指定のチェック
            if not 'RegistrationNumber' in input:
                return False, None, lang['Error']['E00030'], is_new

            # 既に登録された権利でないか調べる
            if self.Properties.count_documents({
                'Country': input['Country'],
                'Law': input['Law'],
                'RegistrationNumber': input['RegistrationNumber'],
                'Ignored': {'$exists': False},
                'User': user_id,
            }) > 0:
                return False, None, lang['Error']['E00050'], is_new

        else:

            # 書き換え不可項目を更新データから消す
            for key in ('Id', '_id', 'Country', 'CountryDescription', 'Law', 'RegistrationNumber', 'ApplicationNumber',):
                if key in input:
                    del input[key]

        if not is_new:
            # 依頼中か否かをチェック
            if self.under_process(id, include_cart=True):
                return False, None, lang['Error']['UnderProcess'], is_new

        # 更新クエリーの組み立て
        q = {'$set':{}, '$unset':{}}

        if id is None:

            # 新規登録のためにキー情報を設定
            q['$set']['User'] = user_id
            q['$set']['Country'] = input['Country']
            if q['$set']['Country'] == 'UNK':
                q['$set']['CountryDescription'] = input['CountryDescription']
            q['$set']['Law'] = input['Law']
            current = q['$set'].copy()

        else:

            # 現在の情報を取得
            current = self.Properties.find_one({'_id': id})

            # 入力側にキーをフィードバック
            for key in ('Country', 'Law', 'RegistrationNumber', 'ApplicationNumber'):
                if key in current:
                    if not key in input:
                        input[key] = current[key]
                    elif key in ('Country', 'Law',):
                        # 国と法域は変更されてはならない
                        assert current[key] == input[key]
            
            country = current['Country']
            law = current['Law']

        # 減免区分の調整
        if country != 'JP' or law != 'Patent':
            if 'JpGenmen' in input:
                del input['JpGenmen']

        # 登録番号と出願番号
        if 'RegistrationNumber' in input:
            q['$set']['RegistrationNumber'] = common_util.regularize_reg_num(input['Country'], input['Law'], input['RegistrationNumber'])
        if 'ApplicationNumber' in input:
            q['$set']['ApplicationNumber'] = common_util.regularize_app_num(input['Country'], input['Law'], input['ApplicationNumber'])

        # 登録番号の形式チェック
        if id is None:
            if 'RegistrationNumber' in q['$set']:
                if input == 'JP':
                    if input == 'Trademark':
                        if not re.fullmatch(r'\d+([\-/]\d+)?', q['$set']['RegistrationNumber']):
                            return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['RegistrationNumber']), True
                    else:
                        if not re.fullmatch(r'\d+', q['$set']['RegistrationNumber']):
                            return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['RegistrationNumber']), True

        # 特に加工の必要のない項目
        for k in ('Subject', 'ManagementNumber', 'PctNumber', 'PriorNumber',):
            if k in input:
                q['$set'][k] = input[k]
            else:
                q['$unset'][k] = ''

        # 登録のみ。削除無し。
        for k in ('JpGenmen', 'SourceURL',):
            if k in input:
                q['$set'][k] = input[k]

        # 日付に変換する項目
        for k in ('NextProcedureLimit', 'ApplicationDate', 'RegistrationDate', 'ExpirationDate', 'ExamClaimedDate',
                  'RegistrationPaymentDate', 'RegistrationInvestigatedDate', 'RenewPaymentDate', 'DisappearanceDate',):
            if k in input:
                try:
                    q['$set'][k] = common_util.parse_date(input[k])
                except ValueError:
                    return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary'][k]), is_new
            elif k in ('RenewPaymentDate', 'DisappearanceDate',):
                q['$unset'][k] = ''

        # 整数化する項目
        for k in ('NumberOfClaims', 'NumberOfClasses',):
            if k in input:
                try:
                    q['$set'][k] = int(input[k])
                except ValueError:
                    return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary'][k]), is_new
        for k in ('PaidYears',):
            if k in input:
                try:
                    q['$set'][k] = float(input[k])
                except ValueError:
                    return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary'][k]), is_new

        # 納付済年分の値域のチェック
        if 'PaidYears' in q['$set']:
            if q['$set']['PaidYears'] < 0:
                return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['PaidYears']), is_new
            if current['Country'] == 'JP':
                if current['Law'] in ('Patent', 'Utility',):
                    if q['$set']['PaidYears'] < 3:
                        return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['PaidYears']), is_new
                elif current['Law'] in ('Design',):
                    if q['$set']['PaidYears'] < 1:
                        return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['PaidYears']), is_new
                elif current['Law'] == 'Trademark':
                    if not q['$set']['PaidYears'] in (5, 10):
                        return False, None, lang['Error']['InvalidField'].format(lang['Vocabulary']['PaidYears']), is_new

        # 商品または役務の区分
        if 'Classes' in input:
            temp = common_util.sort_classes(input['Classes'])
            q['$set']['Classes'] = temp
            q['$set']['NumberOfClasses'] = len(temp)
            if 'NumberOfClasses' in q['$unset']:
                del q['$unset']['NumberOfClasses']

        # 権利者
        if 'Holders' in input and len(input['Holders']):
            q['$set']['Holders'] = input['Holders']

        # 防護標章
        if current['Law'] == 'Trademark':
            if 'Defensive' in input and input['Defensive']:
                q['$set']['Defensive'] = True
            else:
                q['$unset']['Defensive'] = ''

        # ゼロならunset
        for key in ('NumberOfClaims', 'NumberOfClasses'):
            if key in q['$set'] and q['$set'][key] < 1:
                del q['$set'][key]
                q['$unset'][key] = ''

        # 消滅
        if 'Disappered' in input and input['Disappered']:
            q['$set']['Disappered'] = True

        # 放棄の解除
        if update_abandonment:
            if 'Abandoned' in current and not 'Abandon' in input:
                q['$unset']['Abandoned'] = ''

        # 通知の制限
        if 'Silent' in input:
            if common_util.in_and_true(input, 'Silent'):
                q['$set']['Silent'] = True
            else:
                q['$unset']['Silent'] = ''

        # 検証用にマージオブジェクトを生成する
        test = current.copy()
        for k in q['$set']:
            test[k] = q['$set'][k]
        for k in q['$unset']:
            if k in test:
                del test[k]

        # 日付の前後関係をチェック
        for key1, key2 in (('ExamClaimedDate', 'RegistrationDate'),
            ('RegistrationDate', 'ExpirationDate'),
            ('ApplicationDate', 'RegistrationDate'),
            ('ApplicationDate', 'ExamClaimedDate'),):
            if key1 in test and key2 in test:
                if test[key1] > test[key2]:
                    field_name = '%s, %s' % (lang['Vocabulary'][key1], lang['Vocabulary'][key2])
                    return False, id, lang['Error']['InvalidField'].format(field_name), is_new

        # 米国の更新情報
        if 'USPTO' in input:
            q['$set']['USPTO'] = input['USPTO']

        q['$set']['Timestamp'] = datetime.now()

        if is_new:

            # 新規登録
            q = q['$set']
            q['RegisteredTime'] = datetime.now()
            ins = self.Properties.insert_one(q)
            id = ins.inserted_id

        else:

            # 更新
            if len(q['$unset']) < 1:
                del q['$unset']
            self.Properties.update_one({'_id': id}, q)

        # 次回手続期限を更新
        self.renew_limit_date(id)

        # 結果を返す
        return True, id, None, is_new

    def under_process(self, id, include_cart=True):
        """
        依頼を処理中か否かを判定する
        """
        # カートをチェックする
        if include_cart:
            # 権利情報を取得
            prop = self.Properties.find_one({'_id': id}, {'Cart':1})
            if 'Cart' in prop and prop['Cart']['Years'] > 0:
                return True

        # 依頼をチェックする
        req_cnt = self.Requests.count_documents({'$and':[
            {'Properties': {'$elemMatch': {
                'Property': id, 
                'CanceledTime': {'$exists': False},
                'CompletedTime': {'$exists': False},
            }}},
            {'Ignored': {'$exists': False}},
            {'CompletedTime': {'$exists': False}},
            {'CanceledTime': {'$exists': False}},
        ]})
        return (req_cnt > 0)

    def renew_limit_date(self, prop_id):
        """
        知的財産権の次回庁期限を再計算する
        """
        # 権利情報を取得する
        prop = self.Properties.find_one({'_id': prop_id})

        # 納付済年分を取得する
        if 'PaidYears' in prop:
            y = prop['PaidYears']
        else:
            y = 0

        # 完了済の依頼を取得する
        reqs = self.Requests.find({
            'Ignored': {'$exists': False},
            'Properties': {'$elemMatch': {
                'Property': prop_id,
                '$or': [
                    {'CompletedTime': {'$exists': True}},
                    {'SendingReceiptTime': {'$exists': True}},
                ]
            }}
        }, {
            'RequestedTime': 1,
            'Properties.Property': 1,
            'Properties.PaidYears': 1,
            'Properties.Years': 1,
            'Properties.YearFrom': 1,
            'Properties.YearTo': 1,
            'Properties.CompletedTime': 1,
        })
        reqs = sorted(reqs, key=lambda x: x['RequestedTime'])
        
        if len(reqs) > 0:

            # 最後の依頼のみ取得する
            req = reqs[-1]
            req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

            # 納付済年分の調整
            if prop['Law'] == 'Trademark':

                # 商標は存続期間満了日を基準に直近の納付手続か否かを判定する
                if 'ExpirationDate' in prop:
                    if req_p['PaidYears'] == 5:
                        # 分納後期 -> 満了日の11年前より後なら直近の納付とみなす
                        if req_p['CompletedTime'] > common_util.add_months(prop['ExpirationDate'], -11 * 12):
                            # 完納済
                            logger.info('changing PaidYears %d -> %d by completed request %s', y, 10, req['_id'])
                            y = 10
                    else:
                        # 満了日の12月前より後なら直近の更新とみなす
                        if req_p['CompletedTime'] > common_util.add_months(prop['ExpirationDate'], -12):
                            logger.info('changing PaidYears %d -> %d by completed request %s', y, req_p['Years'], req['_id'])
                            next_exp = common_util.add_months(prop['ExpirationDate'], 10 * 12)
                            logger.info('changing ExpirationDate %s -> %s by completed request %s', prop['ExpirationDate'], next_exp, req['_id'])
                            # 納付年数
                            y = req_p['Years']
                            # 次の存続期間満了日
                            prop['ExpirationDate'] = next_exp

            else:

                # 商標以外は単純に納付済年分を置き換える
                if 'YearTo' in req_p:
                    y2 = req_p['YearTo']
                else:
                    assert req_p['Years'] == 1
                    y2 = req_p['YearFrom']
                
                if y2 > y:
                    logger.info('changing PaidYears %d -> %d by completed request %s', y, y2, req['_id'])
                    y = y2

        # 更新クエリーの生成
        query = {'$set': {}, '$unset': {}}

        if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':

            # 日本の商標

            # 存続期間満了日が設定されていない場合は計算しない
            if 'ExpirationDate' in prop:

                exp = prop['ExpirationDate']

                ## 仮の存続期限（更新予定）があれば、それで上書き
                #if 'TempExpirationDate' in prop and prop['TempExpirationDate'] > exp:
                #    exp = prop['TempExpirationDate']

                # 存続期間満了日から分納分を差し引いた日を次の期限とする
                if y <= 10:
                    query['$set']['NextProcedureLimit'] = common_util.add_months(exp, -1 * 12 * (10 - y))
                else:
                    query['$set']['NextProcedureLimit'] = jp_calendar.add_months(exp, 0, consider_holiday=False)

                if 'NextProcedureLimit' in query['$set']:
                    query['$set']['NextProcedureOpenDate'] = jp_calendar.add_months(query['$set']['NextProcedureLimit'], -6, consider_holiday=False)
                    query['$set']['NextProcedureLastLimit'] = jp_calendar.add_months(query['$set']['NextProcedureLimit'], 6, consider_holiday=True)
                    # 閉庁日調整
                    query['$set']['NextProcedureLimit'] = jp_calendar.add_months(query['$set']['NextProcedureLimit'], 0, consider_holiday=True)

        else:

            # 通常の計算

            # 登録日が設定されていない場合は計算しない
            if 'RegistrationDate' in prop:
        
                # 次回庁期限の計算
                if prop['Country'] == 'JP':
                    query['$set']['NextProcedureLimit'] = jp_calendar.add_months(prop['RegistrationDate'], 12 * y, consider_holiday=True)
                else:
                    query['$set']['NextProcedureLimit'] = common_util.add_months(prop['RegistrationDate'], 12 * y)

                # 追納期間の計算
                if prop['Country'] == 'JP':
                    query['$set']['NextProcedureLastLimit'] = jp_calendar.add_months(prop['RegistrationDate'], (12 * y) + 6, consider_holiday=True)
 
        # 計算した次回期限が存続期間を超える場合は期限日を消す
        if 'NextProcedureLimit' in query['$set'] and 'ExpirationDate' in prop:
            if 'ExpirationDate' in prop and query['$set']['NextProcedureLimit'] > prop['ExpirationDate'] and prop['Law'] != 'Trademark':
                del query['$set']['NextProcedureLimit']
                query['$unset']['NextProcedureLimit'] = ''

        # 消滅しているのに次回期限があったら消す
        if 'NextProcedureLimit' in query['$set'] and common_util.in_and_true(prop, 'Disappered'):
            del query['$set']['NextProcedureLimit']
            query['$unset']['NextProcedureLimit'] = ''

        if 'NextProcedureLastLimit' in query['$set'] and not 'NextProcedureLimit' in query['$set']:
            del query['$set']['NextProcedureLastLimit']
            query['$unset']['NextProcedureLastLimit'] = ''
        if not 'NextProcedureLastLimit' in query['$set'] and 'NextProcedureLimit' in query['$set']:
            query['$set']['NextProcedureLastLimit'] = query['$set']['NextProcedureLimit']
        else:
            query['$unset']['NextProcedureLastLimit'] = ''

        # $set に次回期限が無ければ、$unset に入れる
        if not 'NextProcedureLimit' in query['$set']:
            query['$unset']['NextProcedureLimit'] = ''
            query['$unset']['NextProcedureOpenDate'] = ''
            query['$unset']['NextProcedureLastLimit'] = ''

        # $set にあるキーを $unset から消す
        for key in query['$set'].keys():
            if key in query['$unset']:
                del query['$unset'][key]

        if len(query['$set']) == 0:
            del query['$set']
        if len(query['$unset']) == 0:
            del query['$unset']
        if len(query) == 0:
            return

        # クエリーの実行
        self.Properties.update_one({'_id': prop_id}, query)

    def get_prop_info(self, id, lang, date_to_str=True):
        """
        知的財産権の情報を取得する
        """
        # 詳細情報の取得
        if not isinstance(id, ObjectId):
            id = ObjectId(id)

        # 通貨設定の取得
        currencies = common_util.get_currencies(self)

        # 情報の取得
        info = self.Properties.find_one({'_id': id})

        # 法令名の付与
        info['LawName'] = lang['Law'][info['Law']]

        # 国名の付与
        if info['Country'] != 'UNK':
            info['CountryDescription'] = lang['Country'][info['Country']]

        # 優先権番号の形式変換
        if 'PriorNumber' in info and not isinstance(info['PriorNumber'], list):
            info['PriorNumber'] = [info['PriorNumber'],]

        # 依頼可能か調べる
        requestable, reason, max_year, additional = common_util.is_requestable(self, id, consider_cart=True)
        info['Requestable'] = requestable

        if not requestable:
            info['RequestWarning'] = lang['Pages']['Property']['NotRequestable'][reason]
            info['RequestWarning_Short'] = lang['Pages']['Property']['NotRequestable_Short'][reason]
            info['RequestWarning_Reason'] = reason

        # 権利者名の結合
        if 'Holders' in info:
            info['HolderNames'] = ','.join([x['Name'] for x in info['Holders'] if 'Name' in x])

        # 次回料金計算用の判定
        _, _, _, additional = common_util.is_requestable(self, id, consider_cart=False, consider_request=False)

        # 次回納付料金を計算
        y_f = 0
        y_s = 0

        ## 内部の仮情報が存在する場合の置き換え
        #if 'TempPaidYears' in info and 'PaidYears' in info:
        #    if info['TempPaidYears'] > info['PaidYears']:
        #        info['PaidYears'] = info['TempPaidYears']
        #if 'TempExpirationDate' in info and 'ExpirationDate' in info:
        #    if info['TempExpirationDate'] > info['ExpirationDate']:
        #        info['ExpirationDate'] = info['TempExpirationDate']

        if not requestable and reason in ('Disappered', 'PassLimit',):
            # 期限切れの場合は計算不要
            pass
        elif info['Country'] == 'JP' and info['Law'] in ('Patent', 'Utility', 'Design',) and 'PaidYears' in info:
            # 日本の特許、実用新案、意匠
            y_f = info['PaidYears'] + 1
            # 消滅判定
            if 'ExpirationDate' in info and 'RegistrationDate' in info:
                d = common_util.add_months(info['RegistrationDate'], 12 * (y_f - 1))
                if d >= info['ExpirationDate']:
                    y_f = 0
        elif info['Country'] == 'JP' and info['Law'] in ('Trademark',) and 'PaidYears' in info:
            # 日本の商標
            y_s = 5 if info['PaidYears'] == 5 else 10

        if 'PaidYears' in info:
            info['PaidYears'] = int(info['PaidYears'])

        # 料金の計算
        if y_f > 0 or y_s > 0:
            if 'Classes' in info:
                c = len(info['Classes'])
            else:
                c = None
            fees = fee_calculator.calculate_fees(info, lang, year_from=y_f, years=y_s, classes=c, additional=additional)
            fee, cur, _ = fee_calculator.total_fee_list(fees, 'Office')
            if fee > 0:
                info['NextOfficialFee'] = currencies[cur]['Format'].format(fee)
                info['Currency'] = cur
                info['CurrencyLocal'] = lang.local_currency(cur)
                if y_f > 0:
                    if (y_f % 1) > 0:
                        info['YearForPay'] = str(y_f)
                    else:
                        info['YearForPay'] = str(int(y_f))
                elif y_s == 10:
                    info['YearForPay'] = "1-10"
                elif y_s == 5:
                    info['YearForPay'] = "6-10"
                
                # ユーザー通貨に換算
                user_cur = cur
                if 'User' in info:
                    user_info = self.Users.find_one({'_id': info['User']})
                    if not user_info is None and 'Currency' in user_info:
                        user_cur = user_info['Currency']

                if cur != user_cur:
                    fee2, _ = common_util.currency_exchange(fee, cur, user_cur, currencies)
                    info['NextOfficialFee_Exchanged'] = currencies[user_cur]['Format'].format(fee2)
                    info['ExchangedCurrency'] = user_cur
                    info['ExchangedCurrencyLocal'] = lang.local_currency(user_cur)
                
                # 減免の判定
                tmp = [x for x in fees if x['Kind'] == 'Office' and 'Discount' in x]
                if len(tmp) > 0:
                    info['ApplyDiscount'] = True

            fee, cur, _ = fee_calculator.total_fee_list(fees, 'Agent')
            if fee > 0:
                info['NextAgentFee'] = currencies[cur]['Format'].format(fee)
                info['AgentFeeCurrency'] = cur
                info['AgentFeeCurrencyLocal'] = lang.local_currency(cur)

        if additional:
            info['AdditionalPeriod'] = True

        # 依頼中か否かを判定
        info['UnderProcess'] = self.under_process(id, include_cart=True)

        # レスポンス用にデータを編集
        res = {
            'Id': str(info['_id']),
            '_id': str(info['_id']),
            'Country': info['Country'],
            'Law': str(info['Law']),
        }

        if 'User' in info:
            res['UserId'] = str(info['User'])

        for key in ('RegistrationNumber', 'ApplicationNumber',):
            if key in info:
                res[key] = info[key]

        if info['Country'] == 'UNK':
            res['CountryDescription'] = info['CountryDescription']
        else:
            res['CountryDescription'] = lang['Country'][res['Country']]
        res['LawName'] = lang['Law'][res['Law']]

        if info['Country'] == 'JP':
            res['ApplicationNumberPrefix'] = lang['JP']['ApplicationNumberPrefix'][info['Law']]
            res['RegistrationNumberPrefix'] = lang['JP']['RegistrationNumberPrefix'][info['Law']]

        for key in ('Subject', 'PctNumber', 'PriorNumber', 'ManagementNumber',
            'NumberOfClaims', 'NumberOfClaims', 'PaidYears', 'YearForPay', 'Currency', 'CurrencyLocal', 'UsEntity', 'JpGenmen', 'SourceURL', 'ApplyDiscount',):
            if key in info:
                res[key] = info[key]

        for key in ('NextProcedureLimit', 'NextProcedureLastLimit', 'ExamClaimedDate', 'RegistrationDate', 'ExpirationDate', 'Abandoned', 'ApplicationDate',
                    'RegistrationInvestigatedDate', 'RegistrationPaymentDate', 'RenewPaymentDate',):
            if key in info and isinstance(info[key], datetime):
                if date_to_str:
                    res[key] = info[key].strftime('%Y-%m-%d')
                else:
                    res[key] = info[key]

        if 'PriorNumber' in res and not isinstance(res['PriorNumber'], list):
            res['PriorNumber'] = [res['PriorNumber'], ]

        if 'Classes' in info:
            res['Classes'] = ','.join(info['Classes'])
            if not 'NumberOfClasses' in res:
                res['NumberOfClasses'] = len(info['Classes'])

        if 'Holders' in info and len(info['Holders']) > 0:
            res['Holders'] = []
            for h in info['Holders']:
                obj = {}
                if 'Name' in h:
                    obj['Name'] = h['Name']
                if 'Id' in h:
                    obj['Id'] = h['Id']
                if len(obj) > 0:
                    res['Holders'].append(obj)
            if len(res['Holders']) < 1:
                del res['Holders']
            else:
                res['HolderNames'] = ','.join([x['Name'] for x in res['Holders'] if 'Name' in x])

        if 'Defensive' in info and info['Defensive']:
            res['Defensive'] = True

        res['Requestable'] = requestable
        if not requestable:
            res['RequestWarning'] = lang['Pages']['Property']['NotRequestable'][reason]
            res['RequestWarning_Short'] = lang['Pages']['Property']['NotRequestable_Short'][reason]
        else:
            res['MaxYear'] = max_year
        if 'AdditionalPeriod' in info:
            res['AdditionalPeriod'] = info['AdditionalPeriod']
        if 'NextOfficialFee' in info:
            res['NextOfficialFee'] = info['NextOfficialFee']
        if 'NextOfficialFee_Exchanged' in info:
            res['NextOfficialFee_Exchanged'] = info['NextOfficialFee_Exchanged']
            res['ExchangedCurrency'] = info['ExchangedCurrency']
            res['ExchangedCurrencyLocal'] = info['ExchangedCurrencyLocal']
        if 'NextAgentFee' in info:
            res['NextAgentFee'] = info['NextAgentFee']
            res['AgentFeeCurrency'] = info['AgentFeeCurrency']
            res['AgentFeeCurrencyLocal'] = info['AgentFeeCurrencyLocal']

        res['UnderProcess'] = info['UnderProcess']

        # 通知制限
        res['Silent'] = info['Silent'] if 'Silent' in info else False

        # 結果を返す
        return res

    def close(self):
        """
        データベースへの接続を閉じる
        """
        # 接続を切る
        self.__mongo.close()

if __name__ == '__main__':
    with DbClient() as db:
        logger.debug(db.next_number('Test'))
