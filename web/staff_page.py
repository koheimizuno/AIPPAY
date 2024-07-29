from bottle import request, redirect, abort
import re
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import mojimoji
import logging
import json
import io
from pathlib import Path
import copy
import unicodedata

from customized_bottle import app
import auth
from database import DbClient
import web_util
import security
import common_util
from enums import RequestStatus
import pdf_reader
import pdf_parser
import pdf_splitter
import mail
import language
import report_pdf
import report_docx
import sending_receipt
import sending_receipt_pdf
import jpo_paper

logger = logging.getLogger(__name__)

@app.route('/s/props/<page:int>')
@auth.require()
@auth.staff_only()
def props_page_index(page):
    """
    知的財産権一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_props_')
    # 一覧ページを生成
    return props_page(filters=filters, page=page)

@app.get('/s/props')
@auth.require()
@auth.staff_only()
def props_page_default():
    """
    知的財産権一覧
    """
    return props_page_index(1)

@app.post('/s/props')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def props_page_posted():
    """
    知的財産権一覧 フィルターの適用
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()

    # フィルターの適用
    return props_page(filters=posted, page=1)

def props_page(filters={}, page=1, target=None):
    """
    知的財産権一覧
    """
    # フィルターの取得
    filters['Laws'] = [x for x in ('Patent', 'Utility', 'Design', 'Trademark') if 'Law_%s' % x in filters]
    if len(filters['Laws']) == 0:
        filters['Laws'] = ['Patent', 'Utility', 'Design', 'Trademark']
    if 'RegistrationNumber' in filters:
        filters['RegistrationNumber'] = re.sub(r'^0+', '', filters['RegistrationNumber'])
        if filters['RegistrationNumber'] == '':
            del filters['RegistrationNumber']

    # 言語設定
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # クエリーの構築
        query = {'$and':[
            {'Ignored': {'$exists':False}},
            {'Law': {'$in': filters['Laws']}},
        ]}

        # サポートする国・地域に制限
        query['$and'].append({'Country': {'$in': ['JP',]}})

        if 'RegistrationNumber' in filters:
            query['$and'].append({'RegistrationNumber': re.compile(r'^0*' + re.escape(filters['RegistrationNumber']) + r'$')})
        if 'Subject' in filters:
            query['$and'].append({'Subject': re.compile(re.escape(filters['Subject']))})

        # 権利リストの取得
        props = []

        for prop_id in db.Properties.find(query, {'_id':1}):
            # 情報を取得してリストに追加
            props.append(get_property_info(prop_id['_id']))

    # 次回手続期限順に並べ替え
    props = sorted(props, key=lambda x: x['RegistrationNumber'])
    props = sorted(props, key=lambda x: x['Law'])
    props = sorted(props, key=lambda x: x['NextProcedureLimit'] if 'NextProcedureLimit' in x else datetime.max)

    # フィルターの保存
    web_util.save_in_cookie('filter_s_props_', filters)

    # ページに渡す値を生成
    doc = {'Filters': filters,}

    # ページング処理
    result = None

    if not target is None:
        # 指定したidが含まれるページを探す
        p = 1
        while p < 10000:
            props_, p_max, p_ = web_util.paging(props, 10000, p)
            if len([x for x in props_ if x['_id'] == target]) > 0:
                result = props_
                page = p_
                break
            if p_ != p:
                break
            p += 1

    # 通常のページング
    if result is None:
        result, p_max, page = web_util.paging(props, 10000, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/s/props'
    }

    # リストの設定
    doc['Ids'] = [x['_id'] for x in result]
    doc['Properties'] = [json.dumps(web_util.adjust_to_json(x)) for x in result]

    # ページの生成
    return web_util.apply_template('staff_props', doc=doc)

@app.route('/s/props/<id>')
@auth.require()
@auth.staff_only()
def props_page_target(id):
    """
    知的財産権一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_props_')
    # idの変換
    id = ObjectId(id)
    # 一覧ページを生成
    return props_page(filters=filters, target=id)

@app.post('/s/props/api/get')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def props_api_get():
    """
    知的財産権の情報の取得
    """
    # 受信した情報を取得
    posted = web_util.get_posted_data()
    return get_property_info(ObjectId(posted['Id']))

def get_property_info(id):
    """
    知的財産権の情報の取得
    """
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 知的財産権の情報の取得
        prop = db.Properties.find_one({'_id': id, 'Ignored': {'$exists': False}})
        prop['Id'] = prop['_id']

        if prop is None:
            abort(404)

        # 国・地域名
        if prop['Country'] != 'UNK':
            prop['CountryDescription'] = lang['Country'][prop['Country']]
        
        # 法域名
        prop['LawName'] = lang['Law'][prop['Law']]

        # 会員情報を補足
        user = db.Users.find_one({'_id': prop['User']})
        if not user is None:
            if not 'UserOrganization' in prop:
                if 'Organization' in user:
                    # 名前が個別指定されていない場合のみ組織名を取得する
                    if not 'UserName' in prop:
                        prop['UserOrganization'] = user['Organization']
            if not 'UserName' in prop:
                prop['UserName'] = user['Name']
            prop['UserMailAddress'] = user['MailAddress']

        # 優先権番号の型変換
        if 'PriorNumber' in prop and not isinstance(prop['PriorNumber'], list):
            prop['PriorNumber'] = [prop['PriorNumber'],]

        # 商標区分の型変換
        if 'Classes' in prop and not isinstance(prop['Classes'], list):
            prop['Classes'] = [prop['Classes'],]

        # 通知制限
        if not 'Silent' in prop:
            prop['Silent'] = False

    # キー情報の埋め込み
    prop['cdata'] = security.encrypt_dict({'_id':prop['_id']})

    # 情報を返す
    return prop

@app.post('/s/props/api/update')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def props_api_update():
    """
    知的財産権の更新 (Ajax)
    """
    posted = web_util.get_posted_data()

    # 商標区分のリスト化
    if 'Classes' in posted:
        temp = mojimoji.zen_to_han(posted['Classes'])
        temp = temp.split(',')
        temp = [x.strip() for x in temp]
        posted['Classes'] = temp

    # 優先権番号のリスト化
    if 'PriorNumber' in posted:
        temp = posted['PriorNumber']
        temp = temp.split('\t')
        temp = [x.strip() for x in temp]
        posted['PriorNumber'] = temp

    # 権利者のオブジェクト・リスト化
    i = 0
    holders = []
    while i < 1000:
        fn = 'Holder_Name_%d' % i
        if not fn in posted:
            break
        holder = { 'Name': posted[fn] }
        fn = 'Holder_Id_%d' % i
        if fn in posted:
            holder['Id'] = posted[fn]
        holders.append(holder)
        i += 1
    if len(holders) > 0:
        posted['Holders'] = holders

    # 更新処理
    result, id, message, _ = web_util.update_prop(posted)

    if not result:
        # エラー（未更新）
        return {
            'Result': False,
            'Message': message,
        }
    else:
        # 更新後の情報の取得
        info = get_property_info(id)
        info['Result'] = True
        return info

@app.post('/s/props/api/delete')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def props_api_delete():
    """
    知的財産権の削除 (Ajax)
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['Id'])

    with DbClient() as db:

        # データベースの更新
        res = db.Properties.update_one(
            {
                '_id': id,
                'Ignored': {'$exists': False}
            },
            {
                '$set': {
                    'Ignored': datetime.now(),
                    'Modifier': auth.get_account_id(),
                    'ModifiedTime': datetime.now(),
                }
            }
        )

        # 結果を返す    
        return {
            'Result': (res.modified_count > 0),
            'Id': id,
        }

@app.post('/s/props/api/refer')
@auth.require_ajax()
@web_util.local_page()
@auth.staff_only()
@web_util.json_safe()
def props_api_refer():
    """
    Ajax: 特許庁DBの照会
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='staff_prop')
    lang = web_util.get_ui_texts()

    # 情報を取得して返す
    return web_util.get_property_info_from_jpp(posted, lang)

@app.route('/s/reqs/<page:int>')
@auth.require()
@auth.staff_only()
def reqs_page_index(page):
    """
    依頼一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_reqs_')
    # 一覧ページを生成
    return reqs_page(filters=filters, page=page)

@app.get('/s/reqs')
@auth.require()
@auth.staff_only()
def reqs_page_default():
    """
    依頼一覧
    """
    return reqs_page_index(1)

@app.post('/s/reqs')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def reqs_page_posted():
    """
    依頼一覧 フィルターの適用
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()

    # フィルターの適用
    return reqs_page(filters=posted, page=1)

def reqs_page(filters={}, page=1, target=None):
    """
    依頼一覧
    """
    lang = web_util.get_ui_texts()

    # フィルターの調整
    if filters is None:
        filters = {}
    for k in ('RequestDate1', 'RequestDate2'):
        if k in filters:
            try:
                filters[k] = common_util.parse_date(filters[k])
            except ValueError:
                del filters[k]
    if 'RequestNumber' in filters:
        try:
            filters['RequestNumber'] = int(filters['RequestNumber'])
        except ValueError:
            del filters['RequestNumber']

    filters['Status'] = [x.value for x in list(RequestStatus) if 'Status_%d' % x.value in filters]
    if len(filters['Status']) == 0:
        filters['Status'] = [x.value for x in list(RequestStatus)]

    # 言語設定
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 通貨の定義を取得
        currencies = common_util.get_currencies(db)

        # クエリーの構築
        query = {'$and':[
            {'Ignored':{'$exists':False}},
        ]}

        if 'RequestNumber' in filters:
            query['$and'].append({'RequestNumber': filters['RequestNumber']})
        if 'RequestDate1' in filters:
            query['$and'].append({'RequestedTime':{'$gte':filters['RequestDate1']}})
        if 'RequestDate2' in filters:
            query['$and'].append({'RequestedTime':{'$lt':filters['RequestDate2']+timedelta(days=1)}})

        # ユーザーフィルター
        if 'UserName' in filters:

            # 会員の情報を補完
            user_ids = db.Users.find({'$or': [
                {'Name': re.Regex(r'.*' + re.escape(filters['UserName']) + r'.*', flags=re.IGNORECASE)},
                {'Organization': re.Regex(r'.*' + re.escape(filters['UserName']) + r'.*', flags=re.IGNORECASE)},
                {'MailAddress': re.Regex(r'.*' + re.escape(filters['UserName']) + r'.*', flags=re.IGNORECASE)},
            ]},
            {'_id': 1})
            user_ids = [x['_id'] for x in user_ids]

            # クエリーに追加
            query['$and'].append({'User': {'$in': user_ids}})

        # ステータスフィルター
        status = []

        # 見積中
        if RequestStatus.Estimating.value in filters['Status']:
            status.append({
                'RequireEstimation': True,
                'EstimatedTime': {'$exists': False},
                'Ignored': {'$exists': False},
                'CanceledTime': {'$exists': False},
            })        

        # 入金待ち
        if RequestStatus.Paying.value in filters['Status']:
            status.append({
                '$or': [
                    {'RequireEstimation': False,},
                    {'RequireEstimation': {'$exists': False},},
                    {'EstimatedTime': {'$exists': False},},
                ],
                'PaidTime': {'$exists': False},
                'Ignored': {'$exists': False},
                'CanceledTime': {'$exists': False},
            })

        # 対応中
        if RequestStatus.Doing.value in filters['Status']:
            status.append({
                'PaidTime': {'$exists': True},
                'CompletedTime': {'$exists': False},
                'Ignored': {'$exists': False},
                'CanceledTime': {'$exists': False},
            })        

        # 完了
        if RequestStatus.Done.value in filters['Status']:
            status.append({
                'CompletedTime': {'$exists': True},
                'Ignored': {'$exists': False},
                'CanceledTime': {'$exists': False},
            })        

        # キャンセル
        if RequestStatus.Canceled.value in filters['Status']:
            status.append({
                '$or': [
                    {'CanceledTime': {'$exists': True},},
                    {'Properties': {'$elemMatch': {
                        'CanceledTime': {'$exists': True},
                    }}},
                ],
                'Ignored': {'$exists': False},
            })        

        query['$and'].append({'$or': status})

        # 依頼リストの取得
        reqs = []

        # クエリーの実行 + 詳細情報を補完してリストに追加
        for req in db.Requests.find(query, {'_id':1, 'Properties.CanceledTime': 1}):
            # キャンセル済みは対象にしない
            if 'CanceledTime' in req:
                continue
            if not 'Properties' in req:
                continue
            if len(req['Properties']) == len([x for x in req['Properties'] if 'CanceledTime' in x]):
                continue
            # 依頼の詳細情報の取得
            reqs.append(get_request_status_2(req['_id'], db, lang, currencies))

    # 並べ替え
    reqs = sorted(reqs, key=lambda x: x['RequestedTime'])
    reqs.reverse()

    # フィルターの保存
    web_util.save_in_cookie('filter_s_reqs_', filters)

    # ページに渡す値の生成
    doc = {'Filters': filters, 'FiltersData': security.encrypt_dict(filters)}

    # ステータス条件の生成
    doc['StatusCandidates'] = []
    for v in list(RequestStatus):
        sc = {
            'Value': v.value,
            'Name': lang['Pages']['Request']['Status'][v.name]
        }
        doc['StatusCandidates'].append(sc)

    # ページング処理
    result = None

    if not target is None:
        # 指定したidが含まれるページを探す
        p = 1
        while p < 10000:
            reqs_, p_max, p_ = web_util.paging(reqs, 1000, p)
            if len([x for x in reqs_ if x['_id'] == target]) > 0:
                result = reqs_
                page = p_
                break
            if p_ != p:
                break
            p += 1

    # 通常のページング
    if result is None:
        result, p_max, page = web_util.paging(reqs, 1000, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/s/reqs'
    }

    # リストの設定
    doc['Requests'] = [json.dumps(web_util.adjust_to_json(x)) for x in result]

    # 行生成用のリスト（依頼ごとの権利の数）
    doc['PropCounts'] = [{'Id': x['_id'], 'Props': len(x['Properties'])} for x in result]

    # ページの生成
    return web_util.apply_template('staff_reqs', doc=doc)

def get_request_status_2(id, db, lang, currencies):
    """
    一覧に表示するための依頼と権利のリストを生成する
    """
    req = db.Requests.find_one(
        {'_id': id},
        {
            '_id': 1,
            'RequestNumber': 1,
            'RequestedTime': 1,
            'User': 1,
            'PaidTime': 1,
            'EstimatedTime': 1,
            'RequireEstimation': 1,
            'Properties.Property': 1,
            'Properties.NextProcedureLimit': 1,
            'Properties.PaidTime': 1,
            'Properties.PaperMadeTime': 1,
            'Properties.OfficePaidTime': 1,
            'Properties.UploadedTime': 1,
            'Properties.SendingReceiptTime': 1,
            'Properties.CompletedTime': 1,
            'Properties.CanceledTime': 1,
            'Properties.FeeList': 1,
            'TotalAmount': 1,
            'SmallAmounts': 1,
            'Amounts': 1,
            'ExchangedAmounts': 1,
            'ExchangeRate': 1,
            'Currency': 1,
            'UserName': 1,
            'UserOrganization': 1,
            'CompletedTime': 1,
            'CanceledTime': 1,
            'UserMailAddress': 1,
        }
    )

    # 知的財産権の情報を補完
    temp = [x['NextProcedureLimit'] for x in req['Properties'] if 'NextProcedureLimit' in x]
    if len(temp) > 0:
        req['NextProcedureLimit'] = min(temp)

    # 権利についての情報の補完
    for p in req['Properties']:

        prop = db.Properties.find_one({'_id': p['Property']})

        # 国
        if prop['Country'] != 'UNK':
            prop['CountryDescription'] = lang['Country'][prop['Country']]

        # 必要情報の転記
        for k in ('Law', 'RegistrationNumber', 'Country', 'CountryDescription', 'Subject', 'Memo',):
            if k in prop:
                p[k] = prop[k]

        p['LawName'] = lang['Law'][p['Law']]

        # 権利者名
        if 'Holders' in prop:
            holders = [x['Name'] for x in prop['Holders'] if 'Name' in x]
            if len(holders) > 0:
                p['Holders_F'] = ','.join(holders)

        # 会員の情報を補完
        user = db.Users.find_one({'_id': req['User']})
        if not user is None:
            if not 'UserName' in req:
                req['UserName'] = user['Name']
            if not 'UserOrganization' in req:
                if 'Organization' in user:
                    # 名前が個別指定されていない場合のみ組織名も取得する
                    if not 'UserName' in req:
                        req['UserOrganization'] = user['Organization']
            req['UserEmail'] = user['MailAddress']

        # メールアドレスの上書き
        if 'UserMailAddress' in req:
            req['UserEmail'] = req['UserMailAddress']

        # 料金の計算
        if 'FeeList' in p:
            for c in ('Office', 'Agent'):
                fees = [x for x in p['FeeList'] if x['Kind'] == c]
                if len(fees) > 0:
                    v = sum([x['Fee'] for x in fees])
                    item_name = 'OfficialFee' if c == 'Office' else c + 'Fee'
                    p[item_name] = {
                        'Amount': v,
                        'Amount_F': currencies[fees[0]['Currency']]['Format'].format(v),
                        'Currency': fees[0]['Currency'],
                    }
                    if req['Currency'] != fees[0]['Currency']:
                        p[item_name]['ExchangedAmount'] = common_util.fit_currency_precision(v * req['ExchangeRate'][fees[0]['Currency']][req['Currency']], currencies[req['Currency']]['Precision'])
                        p[item_name]['ExchangedAmount_F'] = currencies[req['Currency']]['Format'].format(p[item_name]['ExchangedAmount']),
                        p[item_name]['ExchangedCurrency'] = req['Currency']

        # 整理番号
        if 'ManagementNumber' in prop:
            p['ManagementNumber'] = prop['ManagementNumber']

        # 存続期間満了日
        if 'ExpirationDate' in prop:
            p['ExpirationDate'] = prop['ExpirationDate']

    # 請求合計のフォーマット
    if 'TotalAmount' in req:
        req['TotalAmountText'] = currencies[req['Currency']]['Format'].format(req['TotalAmount'])

    # 取得したオブジェクトを返す    
    return req

@app.route('/s/reqs/<id>')
@auth.require()
@auth.staff_only()
def reqs_page_target(id):
    """
    依頼一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_reqs_')
    # idの変換
    id = ObjectId(id)
    # 一覧ページを生成
    return reqs_page(filters=filters, target=id)

def get_request_status(db, id, lang):
    """
    依頼のステータスを取得する
    """
    req = db.Requests.find_one({'_id': id})
    return {
        'Status': req['Status'],
        'StatusName': lang['Pages']['Request']['Status'][RequestStatus(req['Status']).name],
    }

@app.post('/s/reqs/api/memo')
@web_util.local_page()
@web_util.json_safe()
@auth.require_ajax()
@auth.staff_only()
def reqs_api_memo():
    """
    依頼についての備考を更新する
    """
    posted = web_util.get_posted_data(allow_multiline=['memo',])
    reqId = ObjectId(posted['reqId'])
    propId = ObjectId(posted['propId'])
    if 'memo' in posted:
        memo = str(posted['memo'])
    else:
        memo = ''
    memo = memo.strip()
    with DbClient() as db:
        q = {}
        if memo and memo != '':
            q = {'$set': {'Memo': memo}}
        else:
            q = {'$unset': {'Memo': ''}}
        res = db.Properties.update_one(
            {'_id': propId,},
            q
        )
    return {'result': (res.matched_count > 0)}

@app.post('/s/reqs/api/mannum/get')
@web_util.local_page()
@web_util.json_safe()
@auth.require_ajax()
@auth.staff_only()
def reqs_api_mannum_get():
    """
    依頼ページから整理番号の取得リクエスト
    """
    posted = web_util.get_posted_data()
    propId = ObjectId(posted['id'])
    with DbClient() as db:
        prop = db.Properties.find_one(
            {'_id': propId,},
            {'ManagementNumber':1},
        )
        if not prop is None and 'ManagementNumber' in prop:
            return {'managementNumber':prop['ManagementNumber'], 'result':True}
        else:
            return {'managementNumber':'', 'result':True}

@app.post('/s/reqs/api/mannum/update')
@web_util.local_page()
@web_util.json_safe()
@auth.require_ajax()
@auth.staff_only()
def reqs_api_mannum_update():
    """
    依頼ページから整理番号の更新リクエスト
    """
    posted = web_util.get_posted_data()
    propId = ObjectId(posted['id'])
    manNum = None
    if 'managementNumber' in posted:
        manNum = posted['managementNumber']
        manNum = str(manNum).strip()
        if manNum == '':
            manNum = None    
    with DbClient() as db:
        if not manNum is None:
            db.Properties.update_one(
                {'_id': propId,},
                {'$set':{'ManagementNumber':manNum}},
            )
        else:
            db.Properties.update_one(
                {'_id': propId,},
                {'$unset':{'ManagementNumber':''}},
            )
    return {'result':True}

@app.post('/s/reqs/api/paid')
@web_util.local_page()
@web_util.json_safe()
@auth.require_ajax()
@auth.staff_only()
def reqs_api_paid():
    """
    依頼について入金確認済として更新する
    """
    posted = web_util.get_posted_data()
 
    # id
    reqId = ObjectId(posted['requestId'])
    propId = ObjectId(posted['propertyId'])

    # 結果
    result = {
        'updated': False,
    }

    with DbClient() as db:

        # 入金日が記録されていなければ更新
        res = db.Requests.update_one(
            {
                '_id': reqId,
                'Properties': { '$elemMatch': {
                    'Property': propId,
                    'PaidTime': {'$exists': False},
                    'CanceledTime': {'$exists': False},
                }},
            },
            {
                '$set': {
                    'Properties.$.PaidTime': datetime.now(),
                    'ModifiedTime': datetime.now(),
                    'Modifier': auth.get_account_id(),
                }
            }
        )

        if res.modified_count > 0:

            # 更新有り
            result['updated'] = True

            # 依頼全体で入金済になっているかチェック
            req = db.Requests.find_one({'_id': reqId}, {
                'PaidTime': 1,
                'Properties.Property': 1,
                'Properties.PaidTime': 1,
                'Properties.CanceledTime': 1,
            })

            # 依頼に含まれる権利が全て入金済になっていたら依頼自体にも日時をセットする
            if len(req['Properties']) == len([x for x in req['Properties'] if 'PaidTime' in x or 'CanceledTime' in x]) \
                and len([x for x in req['Properties'] if 'PaidTime' in x]) > 0:

                db.Requests.update_one(
                    {
                        '_id': reqId,
                        'PaidTime': {'$exists': False},
                        'CanceledTime': {'$exists': False},
                    },
                    {
                        '$set':{
                            'PaidTime': datetime.now(),
                            'ModifiedTime': datetime.now(),
                            'Modifier': auth.get_account_id(),
                        }
                    }
                )
        
        # 依頼情報の再取得
        req = db.Requests.find_one({'_id': reqId}, {
            'Properties.PaidYears': 1,
            'Properties.Years': 1,
            'Properties.Property': 1,
            'Properties.FeeList': 1,
        })

        # 権利情報の取得
        prop = db.Properties.find_one({'_id': propId})

    # 納付書類のダウンロードURLを返す
    result['url'] = '/s/reqs/api/paper/%s/%s' % (reqId, propId)

    # 原簿の閲覧要否の判定
    if check_gembo(req, prop):
        result["url3"] = '/s/reqs/api/gembo/{}/{}'.format(str(reqId), str(propId))

    # 更新登録申請書（補充）の有無を調べる
    needs, _ = web_util.check_hoju(reqId, propId)
    if needs:
        result['url2'] = '/s/reqs/api/pp/v2/4/{}/{}'.format(reqId, propId)
    else:
        needs, _ = web_util.check_deletion(reqId, propId)
        if needs:
            result['url2'] = '/s/reqs/api/pp/v2/3/{}/{}'.format(reqId, propId)

    # 結果を返す
    return result

def check_gembo(req, prop):
    """
    登録原簿の照会が必要か判定する
    """
    # 識別番号不明の権利者がいるか判定
    if not 'Holders' in prop:
        pass
    elif len([x for x in prop['Holders'] if not 'Id' in x]) > 0:
        pass
    else:
        # 全ての権利者の識別番号が分かっているなら原簿の閲覧は不要
        return False

    req_p = [x for x in req['Properties'] if x['Property'] == prop['_id']][0]

    # 手続の種類による再判定
    if prop['Law'] == 'Trademark':
        # 更新登録申請のみ対象（分納は対象外）
        if req_p['PaidYears'] == 5:
            return False
        else:
            return True
    else:
        # 減免がある場合のみ対象
        if len([x for x in req_p['FeeList'] if 'Discount' in x and x['Discount'] in ('10_4_i', '10_4_ro', '10_3_ro',)]) > 0:
            return True

    # 不要    
    return False

@app.post('/s/reqs/estimated')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def reqs_estimated():
    """
    依頼について見積提示済として更新する
    """
    posted = web_util.get_posted_data()
 
    if not 'Filters' in posted:
        posted['Filters'] = {}
    else:
        posted['Filters'] = security.decrypt_dict(posted['Filters'])

    if not 'Page' in posted:
        posted['Page'] = 1
    else:
        posted['Page'] = int(posted['Page'])

    # id
    id = ObjectId(posted['Request'])

    with DbClient() as db:

        # EstimatedTime をセットする。
        db.Requests.update_one(
            {
                '_id': id,
                'RequireEstimatioon': True,
                'EstimatedTime': {'$exists': False},
            },
            {
                '$set':{
                    'EstimatedTime': datetime.now(),
                    'ModifiedTime': datetime.now(),
                    'Modifier': auth.get_account_id(),
                }
            }
        )

    # 一覧ページを表示し直す。
    return reqs_page(filters=posted['Filters'], page=posted['Page'])

@app.post('/s/reqs/completed')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def reqs_completed():
    """
    依頼中の権利について完了として更新する
    """
    posted = web_util.get_posted_data()
 
    if not 'Filters' in posted:
        posted['Filters'] = {}
    else:
        posted['Filters'] = security.decrypt_dict(posted['Filters'])

    if not 'Page' in posted:
        posted['Page'] = 1
    else:
        posted['Page'] = int(posted['Page'])

    # id
    req_id = ObjectId(posted['Request'])
    prop_id = ObjectId(posted['Property'])

    with DbClient() as db:

        # 権利に完了日をセットする
        db.Requests.update_one(
            {
                '_id': req_id,
                'Properties': { '$elemMatch': {
                    'Property': prop_id,
                }},
            },
            {
                '$set': {
                    'Properties.$.CompletedTime': datetime.now(),
                    'ModifiedTime': datetime.now(),
                    'Modifier': auth.get_account_id(),
                }
            }
        )

        # 次回期限を更新する
        db.renew_limit_date(prop_id)

        send_completed_message(db, req_id, prop_id)

    # 一覧ページを表示し直す。
    return reqs_page(filters=posted['Filters'], page=posted['Page'])

@app.post('/s/reqs/cancel')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def reqs_cancel():
    """
    依頼に含まれる権利についてキャンセル済として更新する
    """
    posted = web_util.get_posted_data()
 
    if not 'Filters' in posted:
        posted['Filters'] = {}
    else:
        posted['Filters'] = security.decrypt_dict(posted['Filters'])

    if not 'Page' in posted:
        posted['Page'] = 1
    else:
        posted['Page'] = int(posted['Page'])

    # id
    req_id = ObjectId(posted['Request'])
    prop_id = ObjectId(posted['Property'])

    with DbClient() as db:

        # 権利に完了日をセットする
        db.Requests.update_one(
            {
                '_id': req_id,
                'Properties': { '$elemMatch': {
                    'Property': prop_id,
                    'Properties.CompletedTime': { '$exists': False },
                }},
            },
            {
                '$set': {
                    'Properties.$.CanceledTime': datetime.now(),
                    'ModifiedTime': datetime.now(),
                    'Modifier': auth.get_account_id(),
                }
            }
        )

        # すべての権利がキャンセルされていたら依頼自体をキャンセル
        tmp = db.Requests.find_one(
            {'_id': req_id},
            {
                'Properties.Property': 1,
                'Properties.CanceledTime': 1,
            }
        )

        if len(tmp['Properties']) == len([x for x in tmp['Properties'] if 'CanceledTime' in x]):
            # 依頼にキャンセル日をセットする
            db.Requests.update_one(
                {
                    '_id': req_id,
                    'CanceledTime': { '$exists': False },
                },
                {
                    '$set': {
                        'CanceledTime': datetime.now(),
                        'ModifiedTime': datetime.now(),
                        'Modifier': auth.get_account_id(),
                    }
                }
            )

    # 一覧ページを表示し直す。
    return reqs_page(filters=posted['Filters'], page=posted['Page'])

@app.post('/s/reqs/api/status/prop')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def reqs_api_update():
    """
    アップロード済みファイルの一覧と、権利ごとのステータスの取得
    """
    posted = web_util.get_posted_data()
    lang = web_util.get_ui_texts()

    # IDの取得
    req_id = ObjectId(posted['RequestId'])
    prop_id = ObjectId(posted['PropertyId'])

    # データベースの更新
    with DbClient() as db:

        # ステータス更新の確認
        req = db.Requests.find_one(
            {'_id': req_id},
            {
                'Properties.Property': 1, 
                'Properties.UploadedFiles.Name': 1, 
                'Properties.UploadedFiles.IsProcedurePaper': 1,
                'Properties.UploadedFiles.IsReceiptPaper': 1, 
                'Properties.UploadedFiles.UploadedTime': 1,
                'Properties.OfficePaidTime': 1,
                'Properties.CompletedTime': 1,
            }
        )
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

        # レスポンスの生成
        res = {
            'OfficePaid': False,
            'Reported': False,
            'Completed': False,
            'Files': [],
        }

        if 'OfficePaidTime' in req_p:
            res['OfficePaid'] = True
            res['OfficePaidTime'] = req_p['OfficePaidTime']

        if 'CompletedTime' in req_p:
            res['Completed'] = True
            res['CompletedTime'] = req_p['CompletedTime']

        for i in range(len(req_p)):
            uf = req_p['UploadedFiles'][i]
            f = {
                'Id': i,
                'Name': uf['Name'],
                'Time': uf['UploadedTime'].strftime('%Y-%m-%d %H:%M'),
            }
            if 'IsProcedurePaper' in uf and uf['IsProcedurePaper']:
                f['Kind'] = lang['Pages']['Request']['TEXT000009']
            if 'IsReceiptPaper' in uf and uf['IsReceiptPaper']:
                f['Kind'] = lang['Pages']['Request']['TEXT000010']
            res['Files'].append(f)

        # 生成したデータを返す
        return res

@app.post('/s/reqs/api/upload')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def reqs_api_upload():
    """
    受領書等のファイルのアップロード (Ajax)
    """
    lang = web_util.get_ui_texts()
    msg = []
    files = []
    imgpdfs = []
    i = -1
    while True:

        # ファイルの取得
        i += 1
        f = request.files.get('file_%d' % i, None)
        if f is None:
            break

        name = f.raw_filename
        if not name:
            name = f.filename

        # PDFの読み取り
        with io.BytesIO() as pdf:

            # ファイルを一旦バイナリーデータに展開
            f.save(pdf)

            # ファイルを分割
            pdf.seek(0)

            # 年金領収書判定
            m = re.search(r'(年金領収書|商標更新登録)\s*\(([PUTDputd])(\d+)\)', name)

            if m:

                # 年金領収書は加工せずにそのまま使う
                pdfs = [pdf.getvalue(),]
                is_receipt = True
                receipt_law = {'P':'Patent', 'U':'Utility', 'D':'Design', 'T':'Trademark'}[m.group(2).upper()]
                receipt_reg_num = m.group(3)

            else:

                # 登録原簿判定
                m = re.match(r'(登録|特許)原簿.*\.pdf$', name)

                if m:

                    # 登録原簿は番号を読み取れない → 同時にアップロードされたほかのファイルと同じ権利に紐付ける
                    # ※他のファイルの処理後に処理する
                    imgpdf = {
                        'Name': name,
                        'OriginalName': name,
                        'Raw': pdf.getvalue(),
                        'UploadedTime': datetime.now(),
                        'Title': '登録原簿',
                        'Country': 'JP',
                        'SubmitDate': common_util.get_today(),
                    }
                    if f.content_type:
                        imgpdf['ContentType'] = f.content_type
                    imgpdfs.append(imgpdf)
                    continue

                else:

                    try:
                        pdfs = pdf_splitter.split(pdf)
                    except Exception as e:
                        logger.info('cannot split pdf file. (filename=%s, content-type=%s, exception=%s, message=%s)', name, f.content_type, str(type(e)), str(e))
                        pdf.seek(0)
                        pdfs = [pdf.getvalue(),]
                    is_receipt = False

        for j in range(len(pdfs)):

            filename = name

            if len(pdfs) > 1:
                m = re.match(r'(.*)(\.[^.]+)', filename)
                if m:
                    filename = '%s_%d%s' % (m.group(1), j + 1, m.group(2))

            with io.BytesIO() as pdf:

                pdf.write(pdfs[j])
                pdf.seek(0)

                data = {
                    'Raw': pdf.getvalue(),
                    'UploadedTime': datetime.now(),
                }

                data['Name'] = filename
                data['OriginalName'] = filename

                if f.content_type:
                    data['ContentType'] = f.content_type

                # コンテンツの読み取り
                try:
                    data['Content'] = pdf_reader.read(pdf)
                except Exception as e:
                    logger.warning('cannot read pdf file. (filename=%s, content-type=%s, exception=%s, message=%s)', filename, f.content_type, str(type(e)), str(e))
                    msg.append(lang['Pages']['Request']['TEXT000178'].format(filename))
                    continue

                # 内容の解読
                pdf_title, pdf_country, pdf_date, pdf_items = pdf_parser.parse_content(data['Content'])

                if pdf_title is None:
                    msg.append(lang['Pages']['Request']['TEXT000179'].format(filename))
                    continue

                # 年金領収書判定
                if (pdf_title == '年金領収書' or pdf_title == '商標更新登録') and pdf_country == 'JP':
                    if not is_receipt:
                        msg.append(lang['Pages']['Request']['TEXT000258'].format(filename))
                        continue
                    # 年金領収書はファイル名から対象権利を特定
                    pdf_items = [{
                        'Country': 'JP',
                        'Law': receipt_law,
                        'RegistrationNumber': receipt_reg_num,
                    }]

                if pdf_items is None or len(pdf_items) < 1:
                    msg.append(lang['Pages']['Request']['TEXT000180'].format(filename))
                    continue

                data['Title'] = pdf_title
                data['Country'] = pdf_country
                if not pdf_date is None:
                    data['SubmitDate'] = pdf_date

                # 書類種別の判定
                if pdf_title == '受領書':
                    data['IsReceiptPaper'] = True
                elif re.match(r'.*(納付書|更新登録申請書)$', pdf_title):
                    data['IsProcedurePaper'] = True

                # 対象権利情報を付与
                data['Includes'] = pdf_items

                # ファイルリストに追加
                files.append(data)

    # 読み取らなかったPDFの処理
    if len(imgpdfs) > 0:

        # 読み取れたPDFの権利番号を収集
        pdf_items = []
        for file in files:
            if not 'Includes' in file:
                continue
            for inc in file['Includes']:
                if len([x for x in pdf_items if (x['Country'] == inc['Country'] and x['Law'] == inc['Law'] and x['RegistrationNumber'] == inc['RegistrationNumber'])]) == 0:
                    pdf_items.append({
                        'Country': inc['Country'],
                        'Law': inc['Law'],
                        'RegistrationNumber': inc['RegistrationNumber'],
                    })

        if len(pdf_items) > 0:
            # 同時にアップロードされたファイルの権利に紐付け
            for imgpdf in imgpdfs:
                imgpdf['Includes'] = pdf_items
                files.append(imgpdf)
        else:
            # 単独でアップロードされると判定不能
            for imgpdf in imgpdfs:
                msg.append(lang['Pages']['Request']['TEXT000180'].format(imgpdf['OriginalName']))
                continue

    # 更新された依頼のID
    updated_ids = []

    # データベースの更新
    with DbClient() as db:

        # ファイルを依頼に紐つける（手続書類）
        for file in files:

            # 年金領収書をスキップする
            if file['Title'] == '年金領収書' or file['Title'] == '商標更新登録':
                continue

            for inc in file['Includes']:

                # 該当する権利を探す
                props = db.Properties.find({
                    'Country': inc['Country'],
                    'Law': inc['Law'],
                    'RegistrationNumber': inc['RegistrationNumber'],
                })
                props = list(props)

                reg_txt = lang.format_reg_number(inc['Country'], inc['Law'], inc['RegistrationNumber'])

                if len(props) < 1:
                    msg.append(lang['Pages']['Request']['TEXT000181'].format(reg_txt, file['OriginalName']))
                    continue

                candidates = []

                # 取得した権利ごとに依頼を調べる
                for prop in props:

                    # 該当する権利を含む依頼を抽出
                    reqs = db.Requests.find({
                        'Ignored': {'$exists': False},
                        'CompletedTime': {'$exists': False},
                        'CanceledTime': {'$exists': False},
                        'Properties.Property': prop['_id'],
                        'Properties.CompletedTime': {'$exists': False},
                        'Properties.CanceledTime': {'$exists': False},
                        'Properties.CompletedReportSentTime': {'$exists': False},
                    }, {
                        '_id': 1,
                        'Properties.Property': 1, 
                        'Properties.CompletedTime': 1, 
                        'Properties.CanceledTime': 1, 
                        'Properties.CompletedReportSentTime': 1,
                    })

                    # 取得した依頼のステータスを判定
                    for req in reqs:

                        # 依頼に含まれる権利を特定
                        req_p = [x for x in req['Properties'] if x['Property'] == prop['_id']]
                        if len(req_p) == 0:
                            continue
                        req_p = req_p[0]

                        # ステータスを確認。未完了のもののみ対象とする
                        if 'CompletedTime' in req_p:
                            continue
                        if 'CanceledTime' in req_p:
                            continue
                        if 'CompletedReportSentTime' in req_p:
                            continue

                        # 更新対象に追加
                        candidates.append({
                            'RequestId': req['_id'],
                            'PropertyId': prop['_id'],
                        })
                
                if len(candidates) < 1:
                    msg.append(lang['Pages']['Request']['TEXT000181'].format(reg_txt, file['OriginalName']))
                    continue

                # 複数がマッチするケースもあり得る？
                for candidate in candidates:

                    # 登録用オブジェクトを生成
                    regfile = copy.deepcopy(file)
                    del regfile['Includes']

                    date_txt = file['SubmitDate'].strftime('%Y%m%d')
                    if 'SubmitDate' in inc:
                        date_txt = inc['SubmitDate'].strftime('%Y%m%d')
                    law_name = lang['Law'][inc['Law']]
                    regfile['Name'] = '%s_%s%s号_%s.pdf' % (date_txt, law_name, inc['RegistrationNumber'], file['Title'])

                    # 依頼に紐つけて登録
                    db.Requests.update_one(
                        {
                            '_id': candidate['RequestId'],
                            'Properties': {'$elemMatch': {
                                'Property': candidate['PropertyId'],
                            }}
                        },
                        {
                            '$push': {
                                'Properties.$.UploadedFiles': regfile,
                            },
                            '$set': {
                                'ModifiedTime': datetime.now(),
                                'Modifier': auth.get_account_id(),
                            },
                        },
                    )

                    # 更新済IDに追加
                    if not candidate['RequestId'] is updated_ids:
                        updated_ids.append(candidate['RequestId'])

        # 完了チェックと完了報告書の送信
        # ※今回更新した依頼のみチェック対象とする
        msg += check_request_is_completed(db, lang, targets=updated_ids)

        # ファイルを依頼に紐つける（年金領収書）
        for file in files:

            # 年金領収書をスキップする
            if file['Title'] != '年金領収書' and file['Title'] != '商標更新登録':
                continue

            for inc in file['Includes']:

                # 該当する権利を探す
                props = db.Properties.find({
                    'Country': inc['Country'],
                    'Law': inc['Law'],
                    'RegistrationNumber': inc['RegistrationNumber'],
                    'Ignored': {'$exists': False},
                })
                props = list(props)

                reg_txt = lang.format_reg_number(inc['Country'], inc['Law'], inc['RegistrationNumber'])

                if len(props) < 1:
                    msg.append(lang['Pages']['Request']['TEXT000181'].format(reg_txt, file['OriginalName']))
                    continue

                candidates = []

                # 取得した権利ごとに依頼を調べる
                for prop in props:

                    # 該当する権利を含む依頼を抽出
                    # ※過去の仕様で個別に送付状(SendingReceipt)が生成されているものを除く
                    reqs = db.Requests.find({
                        'Ignored': {'$exists': False},
                        'CanceledTime': {'$exists': False},
                        'Properties.Property': prop['_id'],
                        'Properties.CanceledTime': {'$exists': False},
                        'Properties.SendingReceiptTime': {'$exists': False},
                        'Properties.SendingReceipt': {'$exists': False},
                    }, {
                        '_id': 1,
                        'Properties.Property': 1, 
                        'Properties.CanceledTime': 1, 
                        'Properties.SendingReceiptTime': 1,
                    })

                    # 取得した依頼のステータスを判定
                    for req in reqs:

                        # 依頼に含まれる権利を特定
                        req_p = [x for x in req['Properties'] if x['Property'] == prop['_id']]
                        if len(req_p) == 0:
                            continue
                        req_p = req_p[0]

                        # ステータスを確認。未完了のもののみ対象とする
                        if 'CanceledTime' in req_p:
                            continue
                        if 'SendingReceiptTime' in req_p:
                            continue

                        # 更新対象に追加
                        candidates.append({
                            'RequestId': req['_id'],
                            'PropertyId': prop['_id'],
                        })
                
                if len(candidates) < 1:
                    msg.append(lang['Pages']['Request']['TEXT000181'].format(reg_txt, file['OriginalName']))
                    continue

                # 複数がマッチするケースもあり得る？
                for candidate in candidates:

                    # 登録用オブジェクトを生成
                    regfile = copy.deepcopy(file)
                    del regfile['Includes']

                    date_txt = file['SubmitDate'].strftime('%Y%m%d')
                    if 'SubmitDate' in inc:
                        date_txt = inc['SubmitDate'].strftime('%Y%m%d')
                    law_name = lang['Law'][inc['Law']]
 
                    # 依頼に紐つけて登録
                    db.Requests.update_one(
                        {
                            '_id': candidate['RequestId'],
                            'Properties': {'$elemMatch': {
                                'Property': candidate['PropertyId'],
                            }}
                        },
                        {
                            '$set': {
                                'Properties.$.JpoReceiptFile': regfile,
                                'ModifiedTime': datetime.now(),
                                'Modifier': auth.get_account_id(),
                            },
                        },
                    )

                    # 更新済IDに追加
                    if not candidate['RequestId'] is updated_ids:
                        updated_ids.append(candidate['RequestId'])

        # 領収書アップロード済みチェック
        # ※今回の処理対象か否かに関わらず、未完了分全件をチェックする
        msg += check_request_has_jpo_receipt(db, lang)

    # 更新済IDを文字列型に変換
    updated_ids = [str(x) for x in updated_ids]

    # 結果を返す
    return {
        'result': True,
        'messages': msg,
        'updatedIds': updated_ids,
    }

def check_request_is_completed(db, lang, targets=None):
    """
    依頼が完了しているか（書類がすべてアップロードされているか）確認する
    """
    msg = []

    # ステータス更新の確認
    q = {
        'CompletedTime': {'$exists': False},
        'CanceledTime': {'$exists': False},
        'Ignored': {'$exists': False},
        'Properties.UploadedFiles': {'$exists': True}, 
    }
    if not targets is None and len(targets) >= 0:
        q['_id'] = {'$in':targets}

    reqs = db.Requests.find(q, {
        'Properties.Property': 1, 
        'Properties.PaidYears': 1, 
        'Properties.Years': 1, 
        'Properties.YearFrom': 1, 
        'Properties.YearTo': 1, 
        'Properties.Classes': 1, 
        'Properties.OriginalClasses': 1, 
        'Properties.UploadedFiles.Title': 1, 
        'Properties.UploadedFiles.IsReceiptPaper': 1, 
        'Properties.UploadedFiles.IsProcedurePaper': 1,
        'Properties.OfficePaidTime': 1,
        'Properties.CompletedTime': 1,
        'Properties.CanceledTime': 1,
        'Properties.CompletedReportSentTime': 1,
    })

    # 依頼ごとに確認
    for req in reqs:

        # 権利ごとに確認
        for req_p in req['Properties']:

            # キャンセルされている権利はスキップする
            if 'CanceledTime' in req_p:
                continue

            # アップロードファイルのない権利はスキップ
            # ※1依頼に複数権利が含まれている場合
            if not 'UploadedFiles' in req_p:
                continue

            # 権利情報を取得
            prop = db.Properties.find_one({
                '_id': req_p['Property'],
            }, {
                'Country': 1,
                'Law': 1,
            })

            # ファイルが揃っているか判定
            all_files = True

            if len([x for x in req_p['UploadedFiles'] if 'Title' in x]) < 1:
                all_files = False
            elif len([x for x in req_p['UploadedFiles'] if 'Title' in x and re.match(r'.*(納付書|更新登録申請書)$', x['Title'])]) < 1:
                all_files = False
            # 2024.5.20 受領書はなくてもいい

            if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
                if len(req_p['Classes']) != len(req_p['OriginalClasses']):
                    if req_p['PaidYears'] == 10:
                        # 更新登録申請は区分削除でもその他書類の添付は任意 (2024.4.17)
                        pass
                    else:
                        if len([x for x in req_p['UploadedFiles'] if 'Title' in x and x['Title'] == '委任状']) < 1:
                            all_files = False
                        if len([x for x in req_p['UploadedFiles'] if 'Title' in x and  x['Title'] == '商標権の一部抹消登録申請書']) < 1:
                            all_files = False
                        elif len([x for x in req_p['UploadedFiles'] if 'Title' in x and  x['Title'] == '商標権の一部放棄書']) < 1:
                            all_files = False

            if not all_files:
                continue

            # 受領書と納付書が登録されたらステータスを変える
            if not 'OfficePaidTime' in req_p:

                db.Requests.update_one(
                    {
                        '_id': req['_id'],
                        'Properties': {'$elemMatch': {
                            'Property': req_p['Property'],
                        }}
                    },
                    {'$set': {
                        'Properties.$.OfficePaidTime': datetime.now(),
                        'ModifiedTime': datetime.now(),
                        'Modifier': auth.get_account_id(),
                    }}
                )

            # ファイルが揃っていれば自動で完了ステータスにする
            if not 'CompletedTime' in req_p:

                # 完了通知メールを送る
                send_completed_message(db, req['_id'], req_p['Property'])

                prop = db.Properties.find_one({'_id': req_p['Property']})
                num_txt = '%s%s' % (lang['Law'][prop['Law']], prop['RegistrationNumber'])
                msg.append(lang['Pages']['Request']['TEXT000170'].format(num_txt))

                now = datetime.now()

                # 完了日時を記録する
                db.Requests.update_one(
                    {
                        '_id': req['_id'],
                        'Properties': {'$elemMatch': {
                            'Property': req_p['Property'],
                        }}
                    },
                    {'$set': {
                        'Properties.$.Completed': True,
                        'Properties.$.CompletedTime': now,
                        'ModifiedTime': now,
                        'Modifier': auth.get_account_id(),
                    }}
                )

                if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':

                    d = prop['RegistrationDate']
                    i = 0
                    while d < common_util.add_months(now, 12):
                        i += 1
                        d = common_util.add_months(prop['RegistrationDate'], 12 * 10 * i)

                    # 最終納付年分と存続期間満了日を更新する
                    db.Properties.update_one(
                        {'_id': prop['_id']},
                        {'$set': {
                            'TempPaidYears': req_p['YearTo'],
                            'TempExpirationDate': d,
                            'TempClasses': req_p['Classes'],
                            'Timestamp': now,
                            'ModifiedTime': now,
                            'Modifier': auth.get_account_id(),
                        }}
                    )

                else:

                    # 最終納付年分を更新する
                    db.Properties.update_one(
                        {'_id': prop['_id']},
                        {'$set': {
                            'TempPaidYears': req_p['YearTo'],
                            'Timestamp': now,
                            'ModifiedTime': now,
                            'Modifier': auth.get_account_id(),
                        }}
                    )

                # 次回期限を更新する
                db.renew_limit_date(prop['_id'])

    # 戻り値として処理についてもメッセージを返す
    return msg

def send_completed_message(db, req_id, prop_id):
    """
    手続完了のメッセージの送信
    """
    # 依頼情報の取得
    req = db.Requests.find_one(
        {
            '_id': req_id,
        },
        {
            'User': 1,
            'RequestNumber': 1,
            'RequestedTime': 1,
            'Properties' : {
                '$elemMatch': {'Property': prop_id}
            },
        }
    )
    req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

    if not 'Agent' in req:
        req['Agent'] = '0001'

    # 権利情報
    prop = db.Properties.find_one({'_id': req_p['Property']})

    # ユーザー情報の取得
    user = db.Users.find_one({'_id': req['User']})

    # 言語
    lang_code = web_util.get_language()
    if 'Language' in user:
        lang_code = user['Language']
    lang = language.get_dictionary(lang_code)

    subject = lang['Law'][prop['Law']]
    subject += '%s%s%s' % (lang['Common']['RegistrationNumberPreffix'], prop['RegistrationNumber'], lang['Common']['RegistrationNumberSuffix'],)
    subject += ' '
    procs = common_util.list_procedures(req_p, prop, lang, least_one=True)
    subject += procs[0]
    subject += lang['Mail']['MAIL0003']['TEXT000003']

    # メール文面の作成
    with io.StringIO() as buff:

        user_name = user['Name']
        user_org = None
        if 'Organization' in user:
            user_org = user['Organization']
        
        if 'UserName' in req:
            user_name = req['UserName']
            if 'UserOrganization' in req:
                user_org = req['UserOrganization']

        # ユーザー名
        if not user_org is None:
            user_name = '%s\n%s' % (user_org, user_name)

        # メール本文
        buff.write('\n')
        buff.write(lang['Mail']['MAIL0003']['TEXT000001'].format(user_name))
        buff.write('\n\n')
        buff.write(lang['Mail']['MAIL0003']['TEXT000002'])
        buff.write('\n\n')

        # 後段
        buff.write(lang.mail_footer(req['Agent']))

        mail_body = buff.getvalue()

    # 添付ファイル
    attachments = []

    # 報告書
    report = get_report_document(req_id, prop_id)
    attachments.append({
        'Data': report['Raw'],
        'Name': report['Name'],
    })

    # アップロードされたファイル
    if 'UploadedFiles' in req_p:
        for uf in req_p['UploadedFiles']:
            #if common_util.in_and_true(uf, 'IsProcedurePaper') or common_util.in_and_true(uf, 'IsReceiptPaper'):
            attachments.append({
                'Data': uf['Raw'],
                'Name': uf['Name'],
            })

    # メールの送信
    to_addr, cc_addr, bcc_addr = db.get_mail_addresses(req['User'])
    mail.send_mail(
        subject,
        mail_body,
        to=to_addr, cc=cc_addr, bcc=bcc_addr,
        attachments=attachments,
    )

    # 通知日時を記録する
    db.Requests.update_one(
        {
            '_id': req_id,
            'Properties': {'$elemMatch': {
                'Property': prop_id,
            }}
        },
        {'$set': {
            'Properties.$.CompletedReportSentTime': datetime.now(),
        }}
    )

def check_request_has_jpo_receipt(db, lang):
    """
    年金領収書がアップロードされているかチェックする
    """
    msg = []

    # ステータス更新の確認
    reqs = db.Requests.find({
        'CanceledTime': {'$exists': False},
        'Ignored': {'$exists': False},
        'Properties.JpoReceiptFile': {'$exists': True}, 
        'Properties.SendingReceiptTime': {'$exists': False}, 
    }, {
        'Properties.Property': 1, 
        'Properties.PaidYears': 1, 
        'Properties.Years': 1, 
        'Properties.YearFrom': 1, 
        'Properties.YearTo': 1, 
        'Properties.Classes': 1, 
        'Properties.OriginalClasses': 1, 
        'Properties.JpoReceiptFile': 1,
        'Properties.CanceledTime': 1,
        'Properties.SendingReceiptTime': 1,
        'Properties.SendingReceipt': 1,
    })

    # 依頼ごとに確認
    for req in reqs:

        # 権利ごとに確認
        for req_p in req['Properties']:

            # キャンセルされている権利はスキップする
            if 'CanceledTime' in req_p:
                continue

            # 古い形式で送付状が作成されているものはスキップする
            if 'SendingReceipt' in req_p:
                continue

            # アップロードファイルのない権利はスキップ
            # ※1依頼に複数権利が含まれている場合
            if not 'JpoReceiptFile' in req_p:
                continue

            # 権利情報を取得
            prop = db.Properties.find_one({
                '_id': req_p['Property'],
            }, {
                'Country': 1,
                'Law': 1,
            })

            # メールを送信する
            if not 'SendingReceiptTime' in req_p:

                # 完了通知メールを送る
                send_jpo_receipt_message(db, req['_id'], req_p['Property'])

                prop = db.Properties.find_one({'_id': req_p['Property']})
                num_txt = '%s%s' % (lang['Law'][prop['Law']], prop['RegistrationNumber'])
                msg.append(lang['Pages']['Request']['TEXT000259'].format(num_txt))

    # 戻り値として処理についてもメッセージを返す
    return msg

def send_jpo_receipt_message(db, req_id, prop_id):
    """
    年金領収書のメッセージの送信
    """
    # 通貨情報の取得
    currencies = common_util.get_currencies(db)

    # 依頼情報の取得
    req = db.Requests.find_one(
        {
            '_id': req_id,
        },
        {
            'User': 1,
            'RequestNumber': 1,
            'RequestedTime': 1,
            'Properties' : {
                '$elemMatch': {'Property': prop_id}
            },
        }
    )
    req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

    if not 'Agent' in req:
        req['Agent'] = '0001'

    # 権利情報
    prop = db.Properties.find_one({'_id': req_p['Property']})

    # ユーザー情報の取得
    user = db.Users.find_one({'_id': req['User']})

    # 言語
    lang_code = web_util.get_language()
    if 'Language' in user:
        lang_code = user['Language']
    lang = language.get_dictionary(lang_code)

    subject = lang['Law'][prop['Law']]
    subject += '%s%s%s' % (lang['Common']['RegistrationNumberPreffix'], prop['RegistrationNumber'], lang['Common']['RegistrationNumberSuffix'],)
    subject += ' '
    procs = common_util.list_procedures(req_p, prop, lang, least_one=True)
    subject += procs[0]
    subject = re.sub(r'の納付$', '', subject)
    subject = lang['Mail']['MAIL0006']['Subject'].format(subject)

    # メール文面の作成
    with io.StringIO() as buff:

        user_name = user['Name']
        user_org = None
        if 'Organization' in user:
            user_org = user['Organization']
        
        if 'UserName' in req:
            user_name = req['UserName']
            if 'UserOrganization' in req:
                user_org = req['UserOrganization']

        # ユーザー名
        if not user_org is None:
            user_name = '%s\n%s' % (user_org, user_name)

        # メール本文
        buff.write('\n')
        buff.write(lang['Mail']['MAIL0006']['TEXT000001'].format(user_name))
        buff.write('\n\n')
        buff.write(lang['Mail']['MAIL0006']['TEXT000002'])
        buff.write('\n\n')

        # 詳細表示
        table = []

        # 登録番号
        table.append((
            lang['Mail']['MAIL0006']['TEXT000004'],
            lang['Format']['RegistrationNumber'][prop['Law']].format(prop['RegistrationNumber'])
        ))

        # 出願番号
        if 'ApplicationNumber' in prop:
            table.append((
                lang['Mail']['MAIL0006']['TEXT000005'],
                lang['Format']['ApplicationNumber'][prop['Law']].format(prop['ApplicationNumber'])
            ))

        # 権利者
        if 'Holders' in prop:
            tmp = [x['Name'] for x in prop['Holders'] if 'Name' in x]
            if len(tmp) > 0:
                table.append((
                    lang['Mail']['MAIL0006']['TEXT000006'],
                    ', '.join(tmp)
                ))

        # 名称
        if 'Subject' in prop:
            table.append((
                lang['Vocabulary']['SubjectOf' + prop['Law']],
                prop['Subject']
            ))

        # 存続期間満了日
        if 'ExpirationDate' in prop:
            table.append((
                lang['Mail']['MAIL0006']['TEXT000008'],
                lang.format_date(prop['ExpirationDate']),
            ))
        
        # 納付年分
        if prop['Law'] != 'Trademark':
            if req_p['YearFrom'] != req_p['YearTo']:
                s = lang['Format']['TheYearRange'].format(req_p['YearFrom'], req_p['YearTo'])
            else:
                s = lang['Format']['TheYear'].format(req_p['YearFrom'])
        else:
            s = lang['Format']['Years'].format(req_p['Years'])
        table.append((
            lang['Mail']['MAIL0006']['TEXT000009'],
            s,
        ))

        # 納付金額
        if 'FeeList' in req_p:
            # 最初の特許庁料金を納付金額とみなす
            tmp = [x for x in req_p['FeeList'] if x['Kind'] == 'Office']
            if len(tmp) > 0:
                fee = tmp[0]['Fee']
                cur = tmp[0]['Currency']
                if cur == 'JPY' and lang.name == 'ja':
                    cur_text = '円'
                else:
                    cur_text = cur
                if fee > 0:
                    table.append((
                        lang['Mail']['MAIL0006']['TEXT000010'],
                        currencies[cur]['Format'].format(fee) + ' ' + cur_text,
                    ))

        # 次回納付期限
        if prop['Law'] != 'Trademark':
            d = common_util.next_limit(prop['RegistrationDate'], req_p['YearTo'])
            if d < prop['ExpirationDate']:
                table.append((
                    lang['Mail']['MAIL0006']['TEXT000011'],
                    lang.format_date(d),
                ))
        else:
            midashi = lang['ReportMail']['TEXT000001']
            if req_p['YearTo'] == 10:
                # 次の登録更新申請（1年先から見た次の期限）
                d = common_util.next_limit_tm(prop['RegistrationDate'], 1)
                # 手続期間は6月前から
                d1 = common_util.add_months(d, - 6)
                s1 = lang.format_date(d1)
                s2 = lang.format_date(d)
                s = '{} - {}'.format(s1, s2)
                midashi = lang['ReportMail']['TEXT000002']
            else:
                # 分納の納付期限 -> 現在（追納を考慮して1年前）の期限からみた5年後
                d = common_util.next_limit_tm(prop['RegistrationDate'], -1)
                d = common_util.add_months(d, 12 * req_p['YearTo'])
                s = lang.format_date(d)
            table.append((
                midashi,
                lang.format_date(d),
            ))

        def get_text_width(s):
            l = 0
            for c in s:
                eaw = unicodedata.east_asian_width(c)
                l += 2 if eaw in ('F', 'W', 'A') else 1
            return l

        max_width = max([get_text_width(x[0]) for x in table])
        for i in range(len(table)):
            s = table[i][0]
            d = max_width - get_text_width(s)
            if d > 0:
                s += ' ' * d
            buff.write('{}  {}\n'.format(s, table[i][1]))
        buff.write('\n')

        buff.write(lang['Mail']['MAIL0006']['TEXT000003'])
        buff.write('\n\n')

        # 後段
        buff.write(lang.mail_footer(req['Agent']))

        mail_body = buff.getvalue()

    # 添付ファイル
    attachments = []

    # メールあて先の取得
    to_addr, cc_addr, bcc_addr = db.get_mail_addresses(req['User'])
    for_pdf = not ('info@jipps.net' in to_addr)

    # 報告書
    report = get_sending_receipt_document(req_id, prop_id, for_pdf)
    attachments.append({
        'Data': report['Raw'],
        'Name': report['Name'],
    })

    # アップロードされたファイル
    if 'JpoReceiptFile' in req_p:
        attachments.append({
            'Data': req_p['JpoReceiptFile']['Raw'],
            'Name': req_p['JpoReceiptFile']['Name'],
        })

    # メールの送信
    mail.send_mail(
        subject,
        mail_body,
        to=to_addr, cc=cc_addr, bcc=bcc_addr,
        attachments=attachments,
    )

    # 通知日時を記録する
    db.Requests.update_one(
        {
            '_id': req_id,
            'Properties': {'$elemMatch': {
                'Property': prop_id,
            }}
        },
        {'$set': {
            'Properties.$.SendingReceiptTime': datetime.now(),
        }}
    )

@app.route('/s/reqs/api/download/<req_id>/<prop_id>/<file_idx>')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def reqs_api_download(req_id, prop_id, file_idx):
    """
    アップロードされた受領書等のダウンロード
    """
    # キーの型変換
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)

    with DbClient() as db:

        # データの取得
        req = db.Requests.find_one(
            {'_id': req_id},
            {
                'Properties.Property': 1,
                'Properties.UploadedFiles.Name': 1,
                'Properties.UploadedFiles.ContentType': 1,
                'Properties.UploadedFiles.Raw': 1,
                'Properties.CompletedReport.Name': 1,
                'Properties.CompletedReport.ContentType': 1,
                'Properties.CompletedReport.Raw': 1,
            }
        )

        # 権利の特定
        prop = [x for x in req['Properties'] if x['Property'] == prop_id]

        if len(prop) != 1:
            abort(404)
        prop = prop[0]

        if file_idx == 'c':

            # 完了報告書の取得
            if not 'CompletedReport' in prop:
                abort(404, 'File is not found')
            file = prop['CompletedReport']

        else:

            # アップロードされたファイルの取得
            try:
                file_idx = int(file_idx)
            except ValueError:
                abort(404, 'File is not found.')

            # ファイルの特定
            if not 'UploadedFiles' in prop or len(prop['UploadedFiles']) <= file_idx:
                abort(404)
            file = prop['UploadedFiles'][file_idx]

        # Content-Type の確認
        if not 'ContentType' in file:
            file['ContentType'] = 'application/octet-stream'

        # 名前の確認
        if not 'Name' in file:
            file['Name'] = 'no_name.dat'

    # ファイルを返す
    return web_util.push_file(file['Raw'], file['Name'], content_type=file['ContentType'])

@app.route('/s/req/api/invoice/<id>')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def req_api_invoice(id):
    """
    請求書のダウンロード
    """
    id = ObjectId(id)

    with DbClient() as db:

        req = db.Requests.find_one(
            {'_id': id},
            {'RequestNumber':1, 'Invoice':1}
        )

        if len(req['Invoice']) < 1:
            abort(404)

        data = req['Invoice'][-1]['File']
        file_name = 'invoice_{}.pdf'.format(req['RequestNumber'])

    return web_util.push_file(data, file_name, content_type='application/pdf')

@app.get('/s/reqs/api/pp/3/<id>')
@auth.require()
@auth.client_only()
def api_papers_deletion(id):
    """
    一部抹消登録申請書のダウンロード
    """
    id = ObjectId(id)
    # 生成した削除申請書(docx)を返す
    return web_util.download_deletion(id)

@app.get('/s/reqs/api/pp/v2/3/<req_id>/<prop_id>')
@auth.require()
@auth.client_only()
def api_papers_deletion_v2(req_id, prop_id):
    """
    一部抹消登録申請書のダウンロード
    """
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)
    # 生成した削除申請書(docx)を返す
    return web_util.download_deletion(req_id, prop_id=prop_id)

@app.get('/s/reqs/api/pp/v2/4/<req_id>/<prop_id>')
@auth.require()
@auth.client_only()
def api_papers_hoju_v2(req_id, prop_id):
    """
    更新登録申請書（補充）のダウンロード
    """
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)
    # 生成した書類(docx)を返す
    return web_util.download_hoju(req_id, prop_id=prop_id)

@app.route('/s/reqs/api/paper/<rid>/<pid>')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def paper_page_make_get(rid, pid):
    """
    特許庁納付書類(HTML)の生成 (GET)
    """
    req_id = ObjectId(rid)
    prop_id = ObjectId(pid)

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one({
            '_id': req_id,
            'Ignored': {'$exists': False}
        })

        if req is None:
            abort(404)

        # 依頼に含まれる権利を特定
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

        # 知財情報の取得
        prop = db.Properties.find_one({
            '_id': req_p['Property'],
        })

        # 納付書（HTML）の生成
        html = jpo_paper.create_payment_paper(
            req_p,
            prop
        )

        if html is None:
            abort(500)

        # ZIPファイル上の名前を追加
        arcname = '{}_{}_{}_{}.html'.format(
            req['RequestNumber'],
            prop['Law'],
            prop['RegistrationNumber'],
            datetime.now().strftime('%Y%m%d%H%M%S')
        )

        # 納付書作成済をマーク
        res = db.Requests.update_one(
            {
                '_id': req_id,
                'Properties': {'$elemMatch': {
                    'Property': prop_id
                }}
            },
            {'$set':{
                'Properties.$.PaperMadeTime': datetime.now(),
                'Properties.$.PaperMakeUser': auth.get_account_id(),
                'Modifier': auth.get_account_id(),
                'ModifiedTime': datetime.now()
            }}
        )

        # ファイルを返す
        return web_util.push_file(
            html.encode('shift_jisx0213'),
            arcname,
            content_type='text/html'
        )

@app.route('/s/reqs/api/gembo/<rid>/<pid>')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def claiming_gembo_gen(rid, pid):
    """
    閲覧請求書類(HTML)の生成 (GET)
    """
    req_id = ObjectId(rid)
    prop_id = ObjectId(pid)

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one({
            '_id': req_id,
            'Ignored': {'$exists': False}
        })

        if req is None:
            abort(404)

        # 依頼に含まれる権利を特定
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

        # 知財情報の取得
        prop = db.Properties.find_one({
            '_id': req_p['Property'],
        })

        # 納付書（HTML）の生成
        html = jpo_paper.create_claiming_gembo_paper(
            req_p,
            prop
        )

        if html is None:
            abort(500)

        # ZIPファイル上の名前を追加
        arcname = '閲覧請求_{}_{}_{}_{}.html'.format(
            req['RequestNumber'],
            prop['Law'],
            prop['RegistrationNumber'],
            datetime.now().strftime('%Y%m%d%H%M%S')
        )

        # ファイルを返す
        return web_util.push_file(
            html.encode('shift_jisx0213'),
            arcname,
            content_type='text/html'
        )

@app.route('/s/reqs/api/receipt/dl/<req_id>/<prop_id>')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def download_sending_receipt_paper(req_id, prop_id):
    """
    領収書発送書類をダウンロードする
    """
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)

    # 書類を取得する
    with DbClient() as db:

        # 依頼情報を取得する
        req = db.Requests.find_one(
            {'_id': req_id},
            {
                'Properties.Property': 1,
                'Properties.SendingReceipt': 1,
            }
        )
        if req is None:
            abort(404)
        
        # 対象権利を特定する
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id]
        if len(req_p) < 1:
            abort(404)
        req_p = req_p[0]

    # 文書が登録されていなければNOT FOUND
    if not 'SendingReceipt' in req_p:
        abort(404)

    # 取得したファイルを返す
    return web_util.push_file(
        req_p['SendingReceipt']['Raw'],
        req_p['SendingReceipt']['Name'],
        content_type=req_p['SendingReceipt']['ContentType'],
    )

def get_report_document(req_id, prop_id):
    """
    完了報告書を取得する
    """
    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {
                '_id': req_id,
            },
            {
                'User': 1,
                'Properties.Property': 1,
                'Properties.CompletedReport': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Years': 1,
                'Properties.FeeList': 1,
                'Currency': 1,
            }
        )

        if req is None:
            return None

        # 依頼に含まれる権利を特定
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id]
        if len(req_p) < 1:
            return None
        req_p = req_p[0]

        # 既に作成済ならそのファイルを返す
        if 'CompletedReport' in req_p:
            return req_p['CompletedReport']

        # ユーザーのメールアドレスを取得
        user_info = db.Users.find_one({'_id': req['User']})

        # レポートを生成
        if user_info['MailAddress'] in ('info@jipps.net',):
            rep_file, fname, content_type = report_docx.make(req_id, prop_id)
        else:
            rep_file, fname, content_type = report_pdf.make(req_id, prop_id)

        # レポートをデータベースに保存する
        rep = {
            'Name': fname,
            'Time': datetime.now(),
            'Raw': rep_file,
            'ContentType': content_type,
            'CreatedBy': auth.get_account_id(),
        }

        db.Requests.update_one(
            {
                '_id': req_id,
                'Properties': {'$elemMatch': {
                    'Property': prop_id
                }}
            },
            {'$set':{
                'Properties.$.CompletedReport': rep,
                'Modifier': auth.get_account_id(),
                'ModifiedTime': datetime.now()
            }}
        )

    # データを返す
    return rep

def get_sending_receipt_document(req_id, prop_id, pdf=True):
    """
    領収書送付状を取得する
    """
    # 送付状の生成
    if pdf:
        rep = sending_receipt_pdf.make(req_id, prop_id)
    else:
        rep = sending_receipt.make(req_id, prop_id)
    if rep is None:
        abort(404)
    return rep

@app.route('/s/users/<page:int>')
@auth.require()
@auth.admin_only()
def users_page_index(page):
    """
    ユーザー一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_users_')
    # 一覧ページを生成
    return users_page(filters=filters, page=page)

@app.get('/s/users')
@auth.require()
@auth.admin_only()
def users_page_default():
    """
    ユーザー一覧
    """
    return users_page_index(1)

@app.post('/s/users')
@web_util.local_page()
@auth.require()
@auth.admin_only()
def users_page_posted():
    """
    ユーザー一覧 フィルターの適用
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()

    # フィルターの適用
    return users_page(filters=posted, page=1)

def users_page(filters={}, page=1, target=None):
    """
    ユーザー一覧
    """
    if filters is None:
        filters = {}
    for key in ('IsClient', 'IsStaff', 'IsAdmin',):
        if not key in filters:
            filters[key] = False
    if not (filters['IsClient'] or filters['IsStaff'] or filters['IsAdmin']):
        filters['IsClient'] = True
        filters['IsStaff'] = True
        filters['IsAdmin'] = True

    with DbClient() as db:

        # クエリーの構築
        query = {'$and':[
            {'Ignored':{'$exists':False}},
            {'MailAddress': {'$exists':True}},
        ]}

        # メールアドレスフィルター
        if 'MailAddress' in filters:
            expr = re.Regex('.*' + re.escape(filters['MailAddress']) + '.*')
            query['$and'].append({'$or':[
                {'MailAddress': expr},
                {'CcAddresses': expr},
            ]})

        # 権限フィルター
        role = []
        if filters['IsClient']:
            role.append({'$or':[{'IsClient': {'$exists': False}}, {'IsClient': True}]})
        if filters['IsStaff']:
            role.append({'IsStaff': True})
        if filters['IsAdmin']:
            role.append({'IsAdmin': True})
        if len(role) > 0:
            query['$and'].append({'$or': role})

        # 名前フィルター
        if 'Name' in filters:
            expr = re.Regex('.*' + re.escape(filters['Name']) + '.*')
            query['$and'].append({'$or':[
                {'Name': expr},
                {'Organization': expr},
            ]})

        # ユーザーの取得
        users = []

        for user_id in db.Users.find(query, {'_id':1}):
            # 情報を取得してリストに追加
            users.append(get_user_info(user_id['_id']))

    # 並べ替え
    users = sorted(users, key=lambda x: x['MailAddress'])

    # フィルターの保存
    web_util.save_in_cookie('filter_s_users_', filters)

    # ページに渡す値の生成
    doc = {'Filters': filters,}

    # ページング処理
    result = None

    if not target is None:
        # 指定したidが含まれるページを探す
        p = 1
        while p < 10000:
            users_, p_max, p_ = web_util.paging(users, 500, p)
            if len([x for x in users_ if x['_id'] == target]) > 0:
                result = users_
                page = p_
                break
            if p_ != p:
                break
            p += 1

    # 通常のページング
    if result is None:
        result, p_max, page = web_util.paging(users, 500, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/s/users'
    }

    # リストの設定
    doc['Ids'] = [x['_id'] for x in result]
    doc['Users'] = [json.dumps(web_util.adjust_to_json(x)) for x in result]

    # ページの生成
    return web_util.apply_template('staff_users', doc=doc)

@app.route('/s/users/<id>')
@auth.require()
@auth.admin_only()
def users_page_target(id):
    """
    ユーザー一覧
    """
    # フィルターの復元
    filters = web_util.load_from_cookie('filter_s_users_')
    # idの変換
    id = ObjectId(id)
    # 一覧ページを生成
    return users_page(filters=filters, target=id)

@app.post('/s/users/api/get')
@web_util.local_page()
@auth.require_ajax()
@auth.admin_only()
@web_util.json_safe()
def users_api_get():
    """
    ユーザー情報の取得
    """
    posted = web_util.get_posted_data()
    return get_user_info(ObjectId(posted['Id']))

def get_user_info(id):
    """
    ユーザー情報の取得
    """
    with DbClient() as db:

        # 依頼情報の取得
        user = db.Users.find_one({'_id': id})

        if user is None:
            abort(404)

        user['Id'] = user['_id']

        # 自身か否かを判定
        user['Me'] = (user['_id'] == auth.get_account_id())

        # 登録している権利の数を取得
        user['PropertiesCount'] = db.Properties.count_documents({
            'User': user['_id'],
            'Ignored': {'$exists': False}
        })

        # 追加アドレスのスカラー化
        if 'CcAddresses' in user:
            for i in range(len(user['CcAddresses'])):
                user['CcAddress_%d' % i] = user['CcAddresses'][i]

    # キー情報の埋め込み
    user['cdata'] = security.encrypt_dict({'_id': user['_id']})

    # ページの生成
    return user

@app.post('/s/users/api/update')
@web_util.local_page()
@auth.require_ajax()
@auth.admin_only()
@web_util.json_safe()
def users_api_update():
    """
    ユーザー詳細ページ (POST)
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['Id'])
    lang = web_util.get_ui_texts()

    # 更新データの作成
    update = {'$set':{}, '$unset': {}}

    # 管理者権限の変更は自身以外の場合のみ有効
    if id != auth.get_account_id():
        update['$set']['IsStaff'] = ('IsStaff' in posted)
        update['$set']['IsAdmin'] = ('IsAdmin' in posted)

    # メールアドレス
    if 'MailAddress' in posted:
        if not security.is_email(posted['MailAddress']):
            return {
                'Result': False,
                'Message': lang['Pages']['User']['TEXT000009']
            }
        update['$set']['MailAddress'] = posted['MailAddress']

    # 追加メールアドレスのリスト化
    cc_addr = []
    for i in range(0, 3):
        field = 'CcAddress_%d' % i
        if field in posted and posted[field] != "":
            if not security.is_email(posted[field]):
                return {
                    'Result': False,
                    'Message': lang['Pages']['User']['TEXT000009']
                }
            if posted[field] == posted['MailAddress']:
                continue
            if posted[field] in cc_addr:
                continue
            cc_addr.append(posted[field])
    if len(cc_addr) > 0:
        update['$set']['CcAddresses'] = cc_addr
    else:
        update['$unset']['CcAddresses'] = ''

    # その他の情報
    update['$set']['ModifiedTime'] = datetime.now()
    update['$set']['Modifier'] = auth.get_account_id()

    # データベースの更新
    with DbClient() as db:
        # 他で登録されたアドレスでないか調べる
        tmp = []
        if 'MailAddress' in update['$set']:
            tmp.append(update['$set']['MailAddress'])
        #if 'CcAddresses' in update['$set']:
        #    tmp += update['$set']['CcAddresses']
        for addr in tmp:
            cnt = db.Users.count_documents({'$and':[
                {'Ignored': {'$exists': False}},
                {'$or':[
                    {'MailAddress': addr},
                    {'CcAddresses': {'$in':[addr,]}},
                ]},
                {'_id':{'$ne': id}},
            ]})
            if cnt > 0:
                return {
                    'Result': False,
                    'Message': lang['Pages']['User']['TEXT000008'].format(addr)
                }
        if len(update['$unset']) == 0:
            del update['$unset']
        db.Users.update_one({'_id': id}, update)

        # 名前等の更新
        if 'Name' in posted:
            user_name = posted['Name']
            if 'Organization' in posted:
                user_org = posted['Organization']
            else:
                user_org = None
            common_util.update_user_name(db, id, user_name, user_org)

    # 更新後の情報の取得
    res = get_user_info(id)
    res['Result'] = True
    return res

@app.post('/s/users/api/delete')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def users_api_delete():
    """
    ユーザーの削除 (Ajax)
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['Id'])

    with DbClient() as db:

        # データベースの更新
        res = db.Users.update_one(
            {
                '_id': id,
                'Ignored': {'$exists': False}
            },
            {
                '$set': {
                    'Ignored': datetime.now(),
                    'Modifier': auth.get_account_id(),
                    'ModifiedTime': datetime.now(),
                }
            }
        )

        # 結果を返す    
        return {
            'Result': (res.modified_count > 0),
            'Id': id,
        }

@app.get('/s/reqs/api/pp/1/<id>')
@auth.require()
@auth.staff_only()
def api_papers_delegation(id):
    """
    委任状のダウンロード
    """
    id = ObjectId(id)
    # 生成した委任状(docx)を返す
    return web_util.download_delegation(id)

@app.get('/s/reqs/api/pp/v2/1/<req_id>/<prop_id>')
@auth.require()
@auth.staff_only()
def api_papers_delegation_v2(req_id, prop_id):
    """
    委任状のダウンロード
    """
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)
    # 生成した委任状(docx)を返す
    return web_util.download_delegation(req_id, prop_id=prop_id)

@app.get('/s/reqs/api/pp/2/<id>')
@auth.require()
@auth.staff_only()
def api_papers_abandonment(id):
    """
    一部放棄書のダウンロード
    """
    id = ObjectId(id)
    # 生成した放棄書(docx)を返す
    return web_util.download_abandonment(id)

@app.get('/s/reqs/api/pp/v2/2/<req_id>/<prop_id>')
@auth.require()
@auth.staff_only()
def api_papers_abandonment_v2(req_id, prop_id):
    """
    一部放棄書のダウンロード
    """
    req_id = ObjectId(req_id)
    prop_id = ObjectId(prop_id)
    # 生成した放棄書(docx)を返す
    return web_util.download_abandonment(req_id, prop_id=prop_id)

@app.post('/s/reqs/api/has')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def reqs_api_has_paper():
    """
    依頼データにつき、権利の詳細を取得する
    """
    posted = web_util.get_posted_data()
    lang = web_util.get_ui_texts()

    # キーの変換
    req_id = ObjectId(posted['Request'])
    prop_id = ObjectId(posted['Property'])

    with DbClient() as db:

        # 通貨情報の取得
        currencies = common_util.get_currencies(db)

        # 依頼情報の取得
        req = db.Requests.find_one({'_id': req_id})

        # 依頼中の権利の取得
        req_p = [x for x in req['Properties'] if x['Property'] == prop_id][0]

        # 権利情報の取得
        prop = db.Properties.find_one({'_id': prop_id})

        res = {
            "RequestNumber": req["RequestNumber"],
            "Urls": {},
        }

        # 権利情報の転記
        res['Country'] = prop['Country']
        if res['Country'] == 'UNK':
            res['Country'] = prop['CountryDescription']
        else:
            res['Country'] = lang['Country'][prop['Country']]
        res['law'] = prop['Law']
        res['lawName'] = lang['Law'][prop['Law']]
        res['RegistrationNumber'] = prop['RegistrationNumber']
        if 'Subject' in prop:
            res['Subject'] = prop['Subject']
        if 'Holders' in prop:
            res['Holders'] = ','.join([x['Name'] for x in prop['Holders'] if 'Name' in x])

        # 依頼情報の転記
        res['NextProcedureLimit'] = req_p['NextProcedureLimit']

        # 請求項数等の転記
        for key in ('NumberOfClaims', 'PaidYears', 'YearFrom', 'YearTo', 'Years', 'Classes', 'OriginalClasses',):
            if key in req_p:
                res[key] = req_p[key]

        # 権利情報の付与
        for key in ('ApplicationDate', 'ExamClaimedDate', 'RegistrationDate',):
            if key in prop:
                res[key] = prop[key]

        # 日付情報の転記
        for key in ('CompletedReportSentTime', 'CanceledTime', 'CompletedTime', 'PaidTime', 'PaperMadeTime',):
            if key in req_p:
                res[key] = req_p[key]
        for key in ('RequestedTime', 'PayLimit',):
            if key in req:
                res[key] = req[key]

        if 'FeeList' in req_p:

            # 料金データを表示用に編集
            res['Fees'] = {
                'Office': [],
                'Agent': [],
            }

            total = {
                'Office': [0.0, 0.0,],
                'Agent': [0.0, 0.0,],
            }
            total_cur = {
                'Office': "",
                'Agent': "",
            }

            for fee in req_p['FeeList']:
                # 為替換算
                ex_fee = fee['Fee']
                if fee['Currency'] != req['Currency']:
                    ex_fee = ex_fee * req['ExchangeRate'][fee['Currency']][req['Currency']]
                    ex_fee = common_util.fit_currency_precision(ex_fee, currencies[req['Currency']]['Precision'])
                item = {
                    'Subject': fee['Subject'],
                    'Price': currencies[fee['Currency']]['Format'].format(fee['Fee']),
                    'Currency': fee['Currency'],
                    'ExchangedPrice': currencies[req['Currency']]['Format'].format(ex_fee),
                    'ExchangedCurrency': req['Currency'],
                }
                res['Fees'][fee['Kind']].append(item)
                # 合計
                total[fee['Kind']][0] += fee['Fee']
                total[fee['Kind']][1] += ex_fee
                total_cur[fee['Kind']] = fee['Currency']

            # 合計行の追加
            for kind in total.keys():
                if total[kind][0] != 0.0:
                    res['Fees'][kind].append({
                        'Subject': lang['Pages']['Request']['TEXT000025'],
                        'Price': currencies[total_cur[kind]]['Format'].format(total[kind][0]),
                        'Currency': total_cur[kind],
                        'ExchangedPrice': currencies[req['Currency']]['Format'].format(total[kind][1]),
                        'ExchangedCurrency': req['Currency'],
                    })

        # 手続内容の生成
        res['Procedures'] = common_util.list_procedures(req_p, prop, lang)

        # 請求書の判定
        if 'Invoice' in req:
            res["Urls"]['Invoice'] = '/s/req/api/invoice/{}'.format(str(req_id))

        # 商標の一部抹消申請書の判定
        if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
            if len(req_p['Classes']) != len(req_p['OriginalClasses']):
                if req_p['Years'] == 5 and req_p['PaidYears'] == 5:
                    res["Urls"]['Deletion'] = '/s/reqs/api/pp/v2/3/{}/{}'.format(req_id, prop_id)
                else:
                    res["Urls"]['Hoju'] = '/s/reqs/api/pp/v2/4/{}/{}'.format(req_id, prop_id)

        # 納付書の判定
        if prop['Country'] == 'JP':
            res["Urls"]['JpoPayment'] = '/s/reqs/api/paper/{}/{}'.format(str(req_id), str(prop_id))
            # 原簿の閲覧要否の判定
            if check_gembo(req, prop):
                res["Urls"]['Gembo'] = '/s/reqs/api/gembo/{}/{}'.format(str(req_id), str(prop_id))

        # 受任名義
        if not 'Agent' in req:
            req['Agent'] = '0001'
        res['Agent'] = req['Agent']
        res['AgentName'] = lang['Agent'][req['Agent']]

        # アップロードされたファイル
        if 'UploadedFiles' in req_p:
            res['files'] = []
            for i in range(len(req_p['UploadedFiles'])):
                res['files'].append({
                    'url': '/s/reqs/api/download/%s/%s/%d' % (req_id, prop_id, i,),
                    'name': req_p['UploadedFiles'][i]['Name'],
                    'time': req_p['UploadedFiles'][i]['UploadedTime'],
                })

        # 完了報告書をリストに追加
        if 'CompletedReport' in req_p:
            if not 'files' in res:
                res['files'] = []
            res['files'].append({
                'url': '/s/reqs/api/download/%s/%s/c' % (req_id, prop_id,),
                'name': req_p['CompletedReport']['Name'],
                'time': req_p['CompletedReport']['Time'],
            })

        # 合計請求金額
        if 'TotalAmount' in req:
            res['total'] = {
                'price': currencies[req['Currency']]['Format'].format(req['TotalAmount']),
                'currency': req['Currency'],
            }

        # 依頼に含まれるその他の権利
        if len(req['Properties']) > 1:
            res['others'] = []
            for prop2 in db.Properties.find({'_id': {'$in': [x['Property'] for x in req['Properties'] if x['Property'] != prop_id]}}):
                res['others'].append({
                    'country': lang['Country'][prop2['Country']] if prop2['Country'] != 'UNK' else prop2['CountryDescription'],
                    'law': lang['Law'][prop2['Law']],
                    'registrationNumber': prop2['RegistrationNumber'],
                })
        
        # ユーザーの情報
        user = db.Users.find_one({'_id': req['User']})
        res['userName'] = user['Name']
        if 'UserMailAddress' in req:
            res['userEmail'] = req['UserMailAddress']
        else:
            res['userEmail'] = user['MailAddress']
        if 'Organization' in user:
            res['userOrganization'] = user['Organization']
        if 'UserName' in req:
            res['userName'] = req['UserName']
            if 'UserOrganization' in req:
                res['userOrganization'] = req['UserOrganization']
            elif 'userOrganization' in res:
                del res['userOrganization']

    # 取得結果を返す
    return res

@app.post('/s/reqs/api/req/for/list')
@web_util.local_page()
@auth.require_ajax()
@auth.staff_only()
@web_util.json_safe()
def reqs_api_req_v2():
    """
    依頼の詳細を取得する
    """
    # キーの取得
    posted = web_util.get_posted_data()
    id = ObjectId(posted['Key'])

    with DbClient() as db:

        # 必要情報の取得
        lang = web_util.get_ui_texts()
        currencies = common_util.get_currencies(db)

        # データを取得して返す
        return get_request_status_2(id, db, lang, currencies)

@app.post('/s/reqs/api/receipt/user')
@auth.require()
@auth.staff_only()
def reqs_api_receipt_user():
    """
    領収書発送書類作成のためのユーザー情報を取得する
    """
    posted = web_util.get_posted_data()

    # キーの取得
    if not 'Request' in posted:
        abort(400)
    req_id = ObjectId(posted['Request'])

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one({'_id': req_id}, {'User': 1, 'UserName': 1, 'UserOrganization': 1, 'UserAddress': 1,})

        # ユーザー情報の取得
        user = db.Users.find_one({'_id': req['User']}, {'Name':1, 'Organization':1, 'Address':1, '_id':0})

        if 'UserName' in req:
            user['Name'] = req['UserName']
            if 'UserOrganization' in req:
                user['Organization'] = req['UserOrganization']
            elif 'Organization' in user:
                del user['Organization']

        if 'UserAddress' in req:
            user['Address'] = req['UserAddress']
        else:
            # 過去の依頼で同一組織の住所があればそれを使う
            q = {
                'UserAddress': {'$exists': True},
                'UserName': user['Name'],
            }
            if 'Organization' in user:
                q['UserOrganization'] = user['Organization']
            else:
                q['UserOrganization'] = {'$exists': False}
            temp = db.Requests.find(q, {
                'UserAddress': 1,
                'RequestedTime': 1,
            })
            temp = sorted(list(temp), key=lambda x: x['RequestedTime'], reverse=True)
            if len(temp) > 0:
                user['Address'] = temp[0]['UserAddress']

    # 取得したユーザー情報を返す
    return user

@app.post('/s/reqs/api/receipt/make')
@auth.require()
@auth.staff_only()
def reqs_api_receipt_make():
    """
    領収書発送書を作成する
    """
    posted = web_util.get_posted_data()
    lang = web_util.get_language()

    # 必須情報の確認
    if not 'Request' in posted or not 'Property' in posted:
        abort(400)
    if not 'Address' in posted:
        return {
            'Result': False,
            'Message': lang['Pages']['Request']['TEXT000158']
        }

    req_id = ObjectId(posted['Request'])
    prop_id = ObjectId(posted['Property'])

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one({'_id': req_id}, {'User': 1, 'UserName': 1,})

        # ユーザー情報の住所を更新
        user_info = db.Users.find_one({'_id': req['User']})
        if not user_info is None:
            if 'UserName' in req and req['UserName'] != user_info['Name']:
                pass
            else:
                db.Users.update_one(
                    {'_id': req['User']},
                    {'$set': {'Address': posted['Address']}}
                )

        # 依頼情報の住所を更新
        db.Requests.update_one(
            {'_id': req_id},
            {'$set': {'UserAddress': posted['Address']}}
        )

        # ファイルを生成
        file = get_sending_receipt_document(req_id, prop_id)

        # 生成したファイルをデータベースに登録
        # ※作成済の場合は上書き
        db.Requests.update_one(
            {
                '_id': req_id,
                'Properties': {'$elemMatch': {
                    'Property': prop_id
                }}
            },
            {'$set':{
                'Properties.$.SendingReceipt': file,
                'Properties.$.SendingReceiptTime': datetime.now(),
                'Modifier': auth.get_account_id(),
                'ModifiedTime': datetime.now()
            }}
        )

    # 結果とURLを返す
    return {
        'Result': True,
        'Url': '/s/reqs/api/receipt/dl/%s/%s' % (str(req_id), str(prop_id))
    }

@app.get('/s/kigen')
@auth.require()
@auth.staff_only()
def kigen_page_default():
    """
    期限管理リスト
    """
    page = request.query.p
    sort = request.query.s
    dire = request.query.d

    # ページ番号の指定
    if page is None:
        page = 1
    else:
        try:
            page = int(page)
        except ValueError:
            page = 1
    
    # 並べ替えの指定
    if sort is None:
        sort = 'n'
    elif not sort in ('r', 'h', 'u', 'n',):
        sort = 'n'
    
    if dire is None:
        dire = 'a'
    elif not dire in ('a', 'd',):
        dire = 'a'

    # ページの生成
    return kigen_page(page, sort, dire)

def kigen_page(page, sort, direction):
    """
    期限管理リスト
    """
    # 言語設定
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # クエリーの構築
        query = {'$and':[
            {'Ignored': {'$exists':False}},
        ]}

        # サポートする国・地域に制限
        query['$and'].append({'Country': {'$in': ['JP',]}})

        # 権利リストの取得
        props = []

        for info in db.Properties.find(query):

            # 表示用に編集
            prop = {'_id': str(info['_id'])}
            for key in ('Country', 'Law', 'RegistrationNumber', 'Subject', 'NextProcedureLimit',):
                if key in info:
                    prop[key] = info[key]

            if info['Country'] == 'UNK':
                prop['CountryDescription'] = info['CountryDescription']
            else:
                prop['CountryDescription'] = lang['Country'][info['Country']]
            prop['LawName'] = lang['Law'][info['Law']]

            # 関連付けられたユーザー
            user_info = db.Users.find_one({'_id': info['User']})

            if user_info is None:
                continue

            # 必要な場合は直近の依頼を取得
            req_info_1 = None
            req_info_2 = None

            if not 'UserName' in info or 'RegisteredTime' in info:
                reqs = db.Requests.find({
                    'Properties': {
                        '$elemMatch': {
                            'Property': info['_id'],
                        }
                    }
                }, {
                    'Properties.Property': 1,
                    'RequestedTime': 1,
                    'User': 1,
                    'UserName': 1,
                    'UserOrganization': 1,
                    'Organization': 1,
                })
                reqs = [x for x in reqs]
                reqs = sorted(reqs, key=lambda x: x['RequestedTime'])
                if len(reqs) > 0:
                    req_info_1 = reqs[0]
                    req_info_2 = reqs[-1]

            # 申込日
            if 'RegisteredTime' in info:
                prop['RegisteredTime'] = info['RegisteredTime']
            elif not req_info_1 is None:
                prop['RegisteredTime'] = req_info_1['RequestedTime']
            elif 'ModifiedTime' in info:
                prop['RegisteredTime'] = info['ModifiedTime']

            # メールアドレス
            if 'MailAddress' in user_info:
                prop['MailAddress'] = user_info['MailAddress']

            # 申込人
            if 'UserName' in info:
                prop['UserName'] = info['UserName']
                if 'Organization' in info:
                    prop['UserOrganization'] = info['Organization']
                elif 'UserOrganization' in info:
                    prop['UserOrganization'] = info['UserOrganization']
            elif not req_info_2 is None and 'UserName' in req_info_2:
                # 直近の依頼から取得
                if 'UserName' in req_info_2:
                    prop['UserName'] = req_info_2['UserName']
                if 'Organization' in req_info_2:
                    prop['UserOrganization'] = req_info_2['Organization']
                if 'UserOrganization' in req_info_2:
                    prop['UserOrganization'] = req_info_2['UserOrganization']
            else:
                # 権利に関連付けられたユーザー情報を取得
                if 'Name' in user_info:
                    prop['UserName'] = user_info['Name']
                if 'Organization' in user_info:
                    prop['UserOrganization'] = user_info['Organization']

            # 権利者
            if 'Holders' in info:
                tmp = [x['Name'] for x in info['Holders'] if 'Name' in x]
                if len(tmp) > 0:
                    prop['Holders'] = tmp

            # 通知日
            if 'NotifiedDates' in info and 'NextProcedureLimit' in info:
                nds = info['NotifiedDates']
                d = common_util.add_months(info['NextProcedureLimit'], -7)
                nds = [x for x in nds if x['Date'] > d]
                nds = sorted(nds, key=lambda x: x['Date'])
                for x in nds:
                    if x['Timing'] == 'm6':
                        prop['NotifiedM6'] = x['Date']
                    elif x['Timing'] == 'm3':
                        prop['NotifiedM3'] = x['Date']
                    elif x['Timing'] == 'm1':
                        prop['NotifiedM1'] = x['Date']
                    elif x['Timing'] == 'd10':
                        prop['NotifiedD10'] = x['Date']

            # 備考
            if 'Memo' in info:
                prop['Memo'] = info['Memo']

            # 通知制限
            if 'Silent' in info:
                prop['Silent'] = info['Silent']
                if 'SilentTime' in info:
                    prop['SilentTime'] = info['SilentTime']
            else:
                prop['Silent'] = False

            # 表示候補に追加
            props.append(prop)

    # 並べ替え
    if sort == 'n':
        # 次回納付期限
        props = sorted(props, key=lambda x: x['NextProcedureLimit'] if 'NextProcedureLimit' in x else (datetime.min if (direction == 'd') else datetime.max), reverse=(direction == 'd'))
    elif sort == 'r':
        # 登録番号
        props = sorted(props, key=lambda x: x['RegistrationNumber'] if 'RegistrationNumber' in x else '熙熙熙', reverse=(direction == 'd'))
    elif sort == 'h':
        # 権利者
        def first_holder(x):
            if 'Holders' in x:
                return x['Holders'][0]
            return '\U00010FFFF'
        props = sorted(props, key=lambda x: first_holder(x), reverse=(direction == 'd'))
    elif sort == 'u':
        # ユーザー
        def user_name(x):
            if 'UserOrganization' in x:
                return x['UserOrganization']
            if 'UserName' in x:
                return '\U00010FFFF' + x['UserName']
            return '\U00010FFFF' * 2
        props = sorted(props, key=lambda x: user_name(x), reverse=(direction == 'd'))

    # ページング処理
    doc = {}

    # 通常のページング
    props, p_max, page = web_util.paging(props, 500, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/s/kigen',
    }
    doc['Props'] = props
    doc['Control'] = {
        'Sort': sort,
        'Direction': direction,
        'Mode': 'Staff',
    }

    # ページの生成
    return web_util.apply_template('staff_kigen', doc=doc)

@app.post('/s/kigen/api/memo')
@web_util.local_page()
@web_util.json_safe()
@auth.require_ajax()
@auth.staff_only()
def kengen_page_api_memo():
    """
    権利についての備考を更新する
    """
    posted = web_util.get_posted_data(allow_multiline=['memo',])
    propId = ObjectId(posted['propId'])
    if 'memo' in posted:
        memo = str(posted['memo'])
    else:
        memo = ''
    memo = memo.strip()
    with DbClient() as db:
        q = {}
        if memo and memo != '':
            q = {'$set': {'Memo': memo}}
        else:
            q = {'$unset': {'Memo': ''}}
        res = db.Properties.update_one(
            {'_id': propId,},
            q
        )
    return {'result': (res.matched_count > 0)}

@app.post('/s/kigen/api/rm')
@web_util.local_page()
@auth.require()
@auth.staff_only()
def kengen_page_rm():
    """
    権利を削除する
    """
    posted = web_util.get_posted_data()
    propId = ObjectId(posted['propId'])
    with DbClient() as db:
        res = db.Properties.update_one(
            {'_id': propId,},
            {'$set':{
                'Ignored': datetime.now(),
                'Modifier': auth.get_account_id(),
            }}
        )
    return {'result': (res.matched_count > 0)}

@app.post('/s/kigen/api/reg')
@web_util.local_page()
@web_util.json_safe()
@auth.require()
@auth.staff_only()
def kengen_page_reg():
    """
    権利を追加する
    """
    posted = web_util.get_posted_data()
    lang = web_util.get_ui_texts()
    with DbClient() as db:
        # メールアドレスのチェック
        email = posted['mailAddress']
        if not security.is_email(email):
            return {
                'result': False,
                'message': lang['Pages']['Property']['TEXT000134'],
            }
        userName = None
        userOrg = None
        if 'userName' in posted:
            userName = posted['userName']
        if 'userOrganization' in posted:
            userOrg = posted['userOrganization']
        user_id, _, _, _, _ = common_util.find_user_by_email(db, email)
        if not user_id is None:
            user_db = db.Users.find_one({'_id': user_id})
        else:
            user_db = None
        if user_db is None:
            if userName is None:
                return {
                    'result': False,
                    'message': lang['Pages']['Property']['TEXT000131'],
                }
        else:
            # 仮登録ユーザーの可能性がある
            if not 'Name' in user_db and userName is None:
                return {
                    'result': False,
                    'message': lang['Pages']['Property']['TEXT000131'],
                }
        # 国・法域・登録番号
        param = {
            'Country': posted['country'],
            'Law': posted['law'],
            'RegistrationNumber': posted['registrationNumber'],
        }
        # 既に登録されていないかチェック
        if not user_db is None:
            if db.Properties.count_documents({
                'User': user_db['_id'],
                'Country': param['Country'],
                'Law': param['Law'],
                'RegistrationNumber': param['RegistrationNumber'],
                'Ignored': {'$exists': False},
            }) > 0:
                return {
                    'result': False,
                    'message': lang['Pages']['Property']['TEXT000133'],
                }
        # J-PlatPat照会
        prop_info = web_util.get_property_info_from_jpp(param, lang, True)
        if prop_info is None or not prop_info['Result']:
            msg = lang['Pages']['Property']['TEXT000132']
            if not prop_info is None and 'Message' in prop_info:
                msg = prop_info['Message']
            return {
                'result': False,
                'message': msg,
            }
        prop_info = prop_info['Data']
        # ユーザーを登録
        if user_db is None:
            user_info = {
                'MailAddress': email,
                'IsClient': True,
                'ModifiedTime': datetime.now(),
                'RegisteredTime': datetime.now(),
                'Modifier': auth.get_account_id(),
            }
            if not userName is None:
                user_info['Name'] = userName
                if not userOrg is None:
                    user_info['Organization'] = userOrg
            res = db.Users.insert_one(user_info)
            user_id = res.inserted_id
        else:
            user_id = user_db['_id']
        # 権利を登録
        result, prop_id, msg, _ = db.update_prop(prop_info, user_id, lang=lang)
        if not result:
            return {
                'result': False,
                'message': msg,
            }
        # 担当者名を関連付け
        if not userName is None:
            param = {
                'UserName': userName,
            }
            if not userOrg is None:
                param['UserOrganization'] = userOrg
            db.Properties.update_one(
                {'_id': prop_id},
                {'$set': param}
            )
        # 登録後の情報を取得
        prop_db = db.Properties.find_one({'_id': prop_id})
        if not 'UserName' in prop_db and not user_db is None:
            if 'Name' in user_db:
                prop_db['UserName'] = user_db['Name']
            if 'Organization' in user_db:
                prop_db['UserOrganization'] = user_db['Organization']
    # 結果を返す
    return {'result': True, 'data': prop_db,}

import import_props

@app.get('/import')
@app.get('/import/home')
@auth.require()
@auth.staff_only()
def import_page_default(doc={}):
    """
    インポート
    """
    if doc is None:
        doc = {}
    # ページの生成
    return web_util.apply_template('staff_import', doc=doc, csrf_name='import')

@app.get('/api/import/template/simple')
@auth.require()
@auth.staff_only()
def import_page_template():
    """
    テンプレートの取得
    """
    tmpl = import_props.get_template()
    return web_util.push_file(tmpl, 'template.xlsx', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post('/import/props')
@auth.require()
@auth.staff_only()
def import_page_props():
    """
    知的財産権のインポート
    """
    lang = web_util.get_ui_texts()

    # データの取得
    posted = web_util.get_posted_data(csrf_name='import')
    file = request.files.get('wb', '')

    # ページ復元用のオブジェクト
    restore = {}
    #for key in ('cnt', 'cnt_unk', 'user',):
    #    if key in posted:
    #        restore[key] = posted[key]

    # Excelファイルの展開
    with io.BytesIO() as buff:
        file.save(buff)
        buff.seek(0)
        targets, msg = import_props.workbook_to_list(buff.getvalue())

    # 読み込めていない場合はエラーメッセージを表示
    if targets is None:
        restore['message'] = msg
        return import_page_default(doc=restore)

    with DbClient() as db:

        # エラーチェック
        errors = []

        for i in range(len(targets)):

            target = targets[i]

            # 国の付与
            target['Country'] = 'JP'

            if not 'Law' in target:
                errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['Errors']['Missing'].format(lang['Vocabulary']['LawKind'])})
            else:
                # 法域の正規化
                for key in ('Patent', 'Utility', 'Design', 'Trademark'):
                    if target['Law'].lower() == lang['Law'][key].lower():
                        target['Law'] = key
                if not target['Law'] in ('Patent', 'Utility', 'Design', 'Trademark'):
                    errors.append({'Line': i + 2, 'Message':lang['Pages']['Import']['Errors']['Invalid'].format(lang['Vocabulary']['LawKind'])})

            if not 'RegistrationNumber' in target:
                errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['Errors']['Missing'].format(lang['Vocabulary']['RegistrationNumber'])})
            else:
                # 登録番号の正規化
                if 'Law' in target:
                    target['RegistrationNumber'] = common_util.regularize_reg_num(target['Country'], target['Law'], target['RegistrationNumber'])

            # ユーザー名等の正規化
            if 'UserName' in target and target['UserName'].strip() == '':
                del target['UserName']
            if 'UserOrganization' in target and target['UserOrganization'].strip() == '':
                del target['UserOrganization']

            # ユーザーの判定
            if not 'MailAddress' in target or target['MailAddress'].strip() == "":
                errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['Errors']['Missing'].format(lang['Vocabulary']['MailAddress'])})
            elif not security.is_email(target['MailAddress']):
                errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['TEXT000012']})
            else:
                user_db = db.Users.find_one(
                    {'MailAddress': target['MailAddress'], 'Ignored': {'$exists': False}}
                )
                if not user_db is None:
                    target['User'] = user_db['_id']
                else:
                    if not 'UserName' in target:
                        errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['TEXT000013']})
                    else:
                        user_db = {
                            'MailAddress': target['MailAddress'],
                            'Name': target['UserName'],
                            'IsClient': True,
                        }
                        if 'UserOrganization' in target:
                            user_db['Organization'] = target['UserOrganization']
                        res = db.Users.insert_one(user_db)
                        target['User'] = res.inserted_id

            # 既に登録された権利かチェックする
            if 'Country' in target and 'Law' in target and 'RegistrationNumber' in target:
                props = db.Properties.count_documents({
                    'Country': target['Country'],
                    'Law': target['Law'],
                    'RegistrationNumber': target['RegistrationNumber'],
                    'Ignored': {'$exists': False,},
                })
                if props > 0:
                    errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['TEXT000006']})

        # 登録対象内での重複をチェック
        for i in range(len(targets)):

            target = targets[i]

            # キーが揃っていなければ無視
            if not 'Country' in target or not 'Law' in target or not 'RegistrationNumber' in target:
                continue

            # キーが一致する候補を抽出
            def key_match(x, county, law, reg_num):
                if not 'Country' in x or not 'Law' in x or not 'RegistrationNumber' in x:
                    return False
                return (x['Country'] == county and x['Law'] == law and x['RegistrationNumber'] == reg_num)
            tmp = [x for x in targets if key_match(x, target['Country'], target['Law'], target['RegistrationNumber'])]

            # 重複チェック
            if len(tmp) > 1:
                errors.append({'Line': i + 2, 'Message': lang['Pages']['Import']['TEXT000014']})

        if len(errors) > 0:
            restore['Errors'] = errors
            restore['message'] = lang['Pages']['Import']['TEXT000007']
            return import_page_default(doc=restore)

        # 登録日を追加
        now = datetime.now()
        for i in range(len(targets)):
            targets[i]['RegisteredTime'] = now

        # 登録
        res = db.Properties.insert_many(targets)

    # 登録結果
    return import_page_default(
        doc={'message': lang['Pages']['Import']['Imported'].format(len(res.inserted_ids))},
    )
