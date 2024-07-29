import re
from datetime import datetime, timedelta
import math
import logging
from bottle import request, redirect, abort
from bson.objectid import ObjectId
import io
import json
import operator
import urllib.parse
import direct_link

from customized_bottle import app
import web_util
import security
import auth
from database import DbClient
import language
import jpo_price
import mail
import common_util
import invoice
import fee_calculator
import kigen_common

logger = logging.getLogger(__name__)

@app.route('/props/<page:int>')
@auth.require()
@auth.client_only()
def props_page_index(page, info=None):
    """
    知的財産権一覧
    """
    # フィルターの復元
    if 'rstr' in request.query:
        filters = web_util.load_from_cookie('filter_uprops_')
    else:
        filters = {}
    # 一覧ページを生成
    return props_page(filters=filters, page=page, info=info)

@app.route('/props/i/<id>')
@auth.require()
@auth.client_only()
def props_page_index2(id, info=None):
    """
    知的財産権一覧
    """
    # IDの取得
    id = ObjectId(id)

    # フィルターの復元
    if 'rstr' in request.query:
        filters = web_util.load_from_cookie('filter_uprops_')
    else:
        filters = {}

    # 一覧ページを生成
    return props_page(filters=filters, id=id, info=info)

@app.get('/props')
@auth.require()
@auth.client_only()
def props_page_default():
    """
    知的財産権一覧
    """
    return props_page_index(1)

@app.post('/props')
@web_util.local_page()
@auth.require()
@auth.client_only()
def props_page_query():
    """
    知的財産権一覧フィルターの適用
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()

    # フィルターの適用
    return props_page(filters=posted, page=1)

@app.route('/prop/<id>')
@auth.require()
@auth.client_only()
def props_page_with_id(id):
    """
    ID指定での知的財産権の表示
    """
    # フィルターの適用
    return props_page(filters={"_id": id}, page=1)

def props_page(filters={}, page=1, id=None, target=None, info=None):
    """
    知的財産権一覧
    """
    # 言語辞書の取得
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 通貨設定の取得
        currencies = common_util.get_currencies(db)

        # DB用のクエリーの構築
        query = {'$and':[
            {'User': auth.get_account_id()},
            {'Ignored': {'$exists': False}},
        ]}

        # サポートする国・地域に制限
        query['$and'].append({'Country': {'$in': ['JP',]}})

        if 'q' in filters:
            p = re.compile(r'.*' + re.escape(filters['q']) + r'.*', flags=re.IGNORECASE)
            sq = [
                {'RegistrationNumber': p},
                {'Subject': p},
                {'PctNumber': p},
                {'PriorNumber': p},
                {'ManagementNumber': p},
                {'Holders':{'$elemMatch':{'Name': p}}}
            ]
            query['$and'].append({'$or':sq})

        if '_id' in filters:
            id = ObjectId(filters['_id'])
            query['$and'].append({'_id': id})
        else:
            id = None

        # 権利リストの取得
        props = []

        # 検索の実行
        for prop in db.Properties.find(query, {'_id': 1}):

            # 詳細を取得してリストに追加
            props.append(get_prop_info(prop['_id'], date_to_str=False))

    # 並べ替え指定
    # ※以前の並べ替え指定を復元
    if not 's' in filters:
        filters['s'] = '1'
    if 'ss' in filters:
        sort_seq = filters['ss'].split(',')
    else:
        sort_seq = []
    sort_seq = [x for x in sort_seq if x != filters['s']]
    sort_seq.append(filters['s'])
    sort_seq = [x.strip() for x in sort_seq if x.strip() != "" and x in ('1', '2', '3', '4', '5',)]
    if len(sort_seq) == 0:
        sort_seq.append('1')
    sort = sort_seq[-1]

    for sort_key in sort_seq:

        if sort_key == '1':

            # 次回手続期限順に並べ替え
            def order_1(x):
                if 'AbandonedTime' in x:
                    return datetime.max
                if not 'NextProcedureLimit' in x:
                    return datetime.max
                if x['NextProcedureLimit'] > datetime.now():
                    return x['NextProcedureLimit']
                else:
                    if 'NextProcedureLastLimit' in x and x['NextProcedureLastLimit'] > datetime.now():
                        return x['NextProcedureLastLimit']
                    elif common_util.add_months(x['NextProcedureLimit'], 6) > datetime.now():
                        return common_util.add_months(x['NextProcedureLimit'], 6)
                    return datetime.max
            props = sorted(props, key=lambda x: order_1(x))

        elif sort == '2':

            # 法区分で並べ替え
            order = ['Patent', 'Utility', 'Design', 'Trademark',]
            props = sorted(props, key=lambda x: order.index(x['Law']))

        elif sort == '3':

            # 状態で並べ替え
            def order(x):
                if common_util.in_and_true(x, 'Disappered'):
                    return 999
                if 'ExpirationDate' in x and x['ExpirationDate'] < datetime.now():
                    return 999
                if 'Abandoned' in x:
                    return 999
                if 'NextProcedureLimit' in x:
                    if common_util.add_months(x['NextProcedureLimit'], 6) < datetime.now():
                        return 999
                if 'RequestWarning_Reason' in x:
                    if x['RequestWarning_Reason'] == 'AlreadyRequested':
                        return 81
                    if x['RequestWarning_Reason'] == 'AlreadySelected':
                        return 80
                    if x['RequestWarning_Reason'] == 'PassLimit':
                        return 40
                if x['Law'] == 'Trademark':
                    if 'NextProcedureLimit' in x and x['NextProcedureLimit'] > common_util.add_months(datetime.now(), 6):
                        return 5
                return 1
            props = sorted(props, key=lambda x: order(x))

        elif sort == '4':

            # 権利者で並べ替え
            def first_holder_name(x):
                if 'Holders' in x and len(x['Holders']) > 0:
                    for h in x['Holders']:
                        if 'Name' in h:
                            return h['Name']
                return chr(0xffff)
            props = sorted(props, key=lambda x: first_holder_name(x))

        elif sort == '5':

            # 登録番号で並べ替え
            props = sorted(props, key=lambda x: x['RegistrationNumber'] if 'RegistrationNumber' in x else chr(0xffff))

    # ページに渡す値の生成
    filters['s'] = sort
    filters['ss'] = ','.join(sort_seq)
    doc = {'Filters': filters, 'Sort': sort, 'SortSeq': ','.join(sort_seq)}

    result = None
    page_size = 100

    # ページング処理
    if not id is None:
        # 該当するキーが存在するページを探す
        p = 1
        while p < 10000:
            props_, p_max, p_ = web_util.paging(props, page_size, p)
            if len([x for x in props_ if x['_id'] == id]) > 0:
                result = props_
                page = p_
                break
            if p != p_:
                break
            p += 1

    # 通常のページング処理
    if result is None:
        result, p_max, page = web_util.paging(props, page_size, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/props'
    }

    # リストの設定
    doc['Props'] = [json.dumps(web_util.adjust_to_json(x)) for x in result]

    # 自動的に詳細を表示
    if id:
        doc['SpecId'] = id

    # フィルターの保存
    web_util.save_in_cookie('filter_uprops_', filters)

    # ページの生成
    return web_util.apply_template('user_props', doc=doc, info=info, csrf_name='user_props')

def get_prop_info(id, date_to_str=True):
    """
    知的財産権の情報を取得する
    """
    # 詳細情報の取得
    if not isinstance(id, ObjectId):
        id = ObjectId(id)

    # 表示言語
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 情報の取得
        res = db.get_prop_info(id, lang, date_to_str=date_to_str)

    if 'NextProcedureLimit' in res:
        # 一旦日付型化
        res['NextProcedureLimit'] = common_util.parse_date(res['NextProcedureLimit'])
        # 追納を考慮した次回期限
        res['NextProcedureLimit2'] = res['NextProcedureLimit']
        if common_util.in_and_true(res, 'AdditionalPeriod'):
            if 'NextProcedureLastLimit' in res:
                res['NextProcedureLimit2'] = common_util.parse_date(res['NextProcedureLastLimit'])
            else:
                res['NextProcedureLimit2'] = common_util.add_months(res['NextProcedureLimit'], 6)
        # 期限日間近
        today = common_util.get_today()
        if res['NextProcedureLimit2'] <= (today + timedelta(days=10)) and res['NextProcedureLimit2'] >= today:
            res['Hurry'] = True
        if date_to_str:
            # 文字列化
            res['NextProcedureLimit'] = res['NextProcedureLimit'].strftime('%Y-%m-%d')
            res['NextProcedureLimit2'] = res['NextProcedureLimit2'].strftime('%Y-%m-%d')

    # 結果を返す
    return res

@app.post('/props/api/detail')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_detail():
    """
    Ajax: 知的財産権の詳細を取得
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='user_props')

    # 詳細情報の取得
    res = get_prop_info(posted['id'])

    if res is None:
        abort(500)

    # レスポンス用にデータを編集
    res['Result'] = True

    # 結果を返す
    return res

@app.post('/props/api/update')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_update():
    """
    Ajax: 知的財産権の情報の更新
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='user_props', allow_multiline=['PriorNumber',])

    # Idの指定がある場合（更新の場合）、整理番号と通知制限のみ更新する
    if 'Id' in posted:
        id = ObjectId(posted['Id'])
        q = {'$set':{}, '$unset':{}}
        if 'ManagementNumber' in posted:
            q['$set']['ManagementNumber'] = posted['ManagementNumber']
        else:
            q['$unset']['ManagementNumber'] = ''
        if common_util.in_and_true(posted, 'Silent'):
            q['$set']['Silent'] = True
        else:
            q['$unset']['Silent'] = ''
        if len(q['$set']) == 0:
            del q['$set']
        if len(q['$unset']) == 0:
            del q['$unset']
        if len(q) == 0:
            return {
                'Result': True,
            }
        with DbClient() as db:
            db.Properties.update_one(
                {'_id': id},
                q
            )
            res = get_prop_info(id)
            res['Result'] = True
            return res

    # 権利者をリストに戻す
    if 'Holders' in posted:
        posted['Holders'] = json.loads(posted['Holders'])

    # 優先権番号をリストにする
    if 'PriorNumber' in posted:
        temp = posted['PriorNumber'].split('\n')
        temp = [x.strip() for x in temp]
        posted['PriorNumber'] = temp

    # 更新処理
    result, id, message, is_new = web_util.update_prop(posted, update_abandonment=True)

    # 更新結果を返す
    if result:
        res = get_prop_info(id)
        res['Result'] = True
        res['IsNew'] = is_new
    else:
        res = {
            'Result': False,
            'Message': message
        }
    return res

@app.post('/props/api/delete')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_delete():
    """
    Ajax: 知的財産権の情報の更新
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='user_props')
    lang = web_util.get_ui_texts()

    # idの取得
    id = ObjectId(posted['id'])

    with DbClient() as db:

        # 依頼中か否かを判定
        proc = common_util.under_process(db, id, include_cart=True)

        if proc:
            return {'result': False, 'message': lang['Error']['UnderProcess'], 'id': id}

        now = datetime.now()

        # 削除マーク
        db.Properties.update_one(
            {'_id': id},
            {'$set': {
                'Ignored': now,
                'Timestamp': now,
            }}
        )

        # 結果を返す
        return {'result': True, 'id': id}

@app.post('/props/api/refer')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_refer():
    """
    Ajax: 特許庁DBの照会
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='user_props')
    lang = web_util.get_ui_texts()

    # 情報を取得して結果を返す
    return web_util.get_property_info_from_jpp(posted, lang)

@app.post('/props/api/cart')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_count_cart():
    """
    Ajax: カート内の件数を取得
    """
    with DbClient() as db:

        cnt = db.Properties.count_documents({
            'User': auth.get_account_id(),
            'Ignored': {'$exists': False},
            'Cart': {'$exists':True},
        })

    return {'result': True, 'count': cnt}

@app.post('/props/api/req')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_add_to_cart():
    """
    Ajax: カートへの追加
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # ID
        prop_id = ObjectId(posted['id'])

        # 権利の所有者を確認
        prop = db.Properties.find_one({'_id': prop_id}, {'User':1})

        # ログイン中のユーザーで無ければ失敗レスポンスとメッセージを返す
        if prop is None:
            return {'result': False}
        if prop['User'] != auth.get_account_id():
            u = db.Users.find_one({'_id': prop['User']}, {'MailAddress':1})
            msg = lang['Pages']['Property']['TEXT000145'].format(u['MailAddress'])
            return {
                'result': False,
                'invalidOwner': True,
                'message': msg,
            }

        # カートに追加する
        return {'result': add_to_cart(db, ObjectId(posted['id']))}

@app.post('/props/api/reqf')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_add_to_cart():
    """
    Ajax: カートへの追加（オーナーを強制変更）
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()

    with DbClient() as db:

        # ID
        prop_id = ObjectId(posted['id'])

        # 権利の所有者を確認
        prop = db.Properties.find_one({'_id': prop_id}, {'User':1})

        # ログイン中のユーザーで無ければ失敗レスポンスとメッセージを返す
        if prop is None:
            return {'result': False}
        if prop['User'] != auth.get_account_id():
            # オーナー変更
            common_util.transfer_properties(db, prop['User'], auth.get_account_id(), prop_id=prop_id)
            if db.Properties.count_documents({
                '_id': prop_id,
                'User': auth.get_account_id(),
            }) == 0:
                return {'result': False}

        # カートに追加する
        return {'result': add_to_cart(db, ObjectId(posted['id']))}

@app.post('/props/api/requestable')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def props_api_check_requestable():
    """
    Ajax: 依頼可否の判定
    """
    # POSTデータの取得
    posted = web_util.get_posted_data()
    id = ObjectId(posted['id'])

    lang = web_util.get_ui_texts()
    res = {}

    with DbClient() as db:

        # 依頼可否判定
        requestable, reason, _, _ = common_util.is_requestable(db, id, consider_cart=True)

        res['requestable'] = requestable

        if not requestable:
            res['reason'] = reason
            res['message'] = lang['Pages']['Property']['NotRequestable_Short'][reason]

        # 結果を返す
        return res

def add_to_cart(db, id, user_id=None):
    """
    カートに追加する
    """
    if user_id is None:
        user_id = auth.get_account_id()

    # 依頼可否判定
    requestable, _, _, _ = common_util.is_requestable(db, id, consider_cart=True)

    if not requestable:
        return False

    # 情報の取得
    prop = db.Properties.find_one({'_id': id, 'User': user_id})

    # 年数の初期設定
    year = 1
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        if not 'PaidYears' in prop or prop['PaidYears'] == 10:
            year = 10
        else:
            year = 5

    # カートのフラグを立てる
    db.Properties.update_one(
        {'_id': prop['_id']},
        {'$set': {'Cart': {'Years': year}, 'Timestamp': datetime.now()}}
    )

    # 結果を返す
    return True

def update_fees_in_cart(db, prop_id=None):
    """
    カート内の料金をすべて再計算する
    """
    if prop_id is None:
        # 現在カートに入っている権利を取得
        props = db.Properties.find({
            'User': auth.get_account_id(),
            'Ignored': {'$exists': False},
            'Cart': {'$exists': True},
        })
    else:
        props = db.Properties.find({
            '_id': prop_id,
            'Ignored': {'$exists': False},
            'Cart': {'$exists': True},
        })

    # 権利の情報を付与
    for prop in props:

        # カート情報（最後に更新）
        cart = prop['Cart']

        # 依頼可能か否かを判定
        requestable, reason, _, _ = common_util.is_requestable(db, prop['_id'], consider_cart=False, consider_request=True)

        # 依頼不可の場合はスキップ
        if not requestable:
            cart['Requestable'] = False
            cart['WarningMessage'] = reason
            for key in ('OfficialFee', 'AgentFee', 'ExchangedOfficialFee', 'ExchangedAgentFee', 'FeeList',
                        'Agent', 'RequireEstimation', ):
                if key in cart:
                    del cart[key]
            db.Properties.update_one(
                {'_id': prop['_id']},
                {
                    '$set': {'Cart': cart},
                }
            )
            continue

        # 更新用の Cart オブジェクトを生成する
        cart = update_cart(prop, cart)

        # データベースの更新
        db.Properties.update_one({'_id': prop['_id']}, {'$set': {'Cart': cart}})

def update_cart(prop, cart):
    """
    元の Cart オブジェクトから更新用のオブジェクトを生成する
    """
    if cart is None:
        return None

    # 言語設定を取得
    lang = web_util.get_ui_texts()

    # 手続の説明文の格納場所
    description = []

    # 依頼可能か否かを判定
    requestable, reason, max_year, additional = common_util.is_requestable_no_db(prop)

    # 依頼不可の場合はスキップ
    if not requestable:
        cart['Requestable'] = False
        cart['WarningMessage'] = reason
        for key in ('OfficialFee', 'AgentFee', 'ExchangedOfficialFee', 'ExchangedAgentFee', 'FeeList',
                    'Agent', 'RequireEstimation', ):
            if key in cart:
                del cart[key]
        return cart

    # 受任者判定
    #if prop['Country'] == 'JP' and prop['Law'] == 'Trademark' and (not 'PaidYears' in prop or prop['PaidYears'] != 5):
    #    # 特許事務所
    #    cart['Agent'] = '0002'
    #else:
    #    # 株式会社
    #    cart['Agent'] = '0001'

    # 株式会社
    cart['Agent'] = '0001'

    # 依頼可
    cart['Requestable'] = True

    # 追納期間
    cart['AdditionalPeriod'] = additional

    # 商標の区分削除可否
    cart['CanDeleteClass'] = True
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        if not 'Classes' in prop or len(prop['Classes']) < 2:
            cart['CanDeleteClass'] = False
        if additional:
            cart['CanDeleteClass'] = False

    # 納付する年分の情報
    cart['MaxYear'] = max_year
    cart['MinYear'] = 1
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        cart['MinYear'] = 5

    # 存続期間についてのメッセージ
    if 'ExpiringMessage' in cart:
        del cart['ExpiringMessage']
    if prop['Law'] in ('Patent', 'Utility', 'Design'):
        if 'ExpirationDate' in prop:
            d = common_util.add_months(prop['RegistrationDate'], 12 * (cart['Years'] + prop['PaidYears']))
            if d > prop['ExpirationDate']:
                cart['ExpiringMessage'] = lang['Pages']['Property']['ExpiringMessage'].format(prop['ExpirationDate'])

    # 請求項数
    if 'NumberOfClaims' in prop:
        description.append(lang['Format']['NumberOfClaims'].format(prop['NumberOfClaims']))

    # 商標の区分の数を確認
    if prop['Law'] == 'Trademark':
        if not 'Classes' in cart:
            cart['Classes'] = prop['Classes']
        cart['ClassesForUpdate'] = len(cart['Classes'])
        cart['ClassesForDelete'] = len(prop['Classes']) - cart['ClassesForUpdate']
        if cart['ClassesForDelete'] > 0:
            description.append(lang['Format']['ClassesForUpdate'].format(','.join([str(x) for x in cart['Classes']]), cart['ClassesForUpdate']))
            description.append(lang['Format']['ClassesForDelete'].format(','.join([str(x) for x in prop['Classes'] if not x in cart['Classes']]), cart['ClassesForDelete']))
        else:
            description.append(lang['Format']['NumberOfClaims'].format(cart['ClassesForUpdate']))

    # 対象年分の表示
    if prop['Law'] in ('Patent', 'Utility', 'Design',):
        if not 'PaidYears' in prop:
            prop['PaidYears'] = 0
        if True:
            cart['YearFrom'] = int(prop['PaidYears'] + 1)
            cart['YearTo'] = int(cart['YearFrom'] + cart['Years'] - 1)
            cart['YearRangeText'] = str(cart['YearFrom'])
            if cart['YearTo'] > cart['YearFrom']:
                cart['YearRangeText'] += ('-' + str(cart['YearTo']))
                description.append(lang['Format']['FromTo'].format(
                    lang['Format']['TheYear'].format(cart['YearFrom']),
                    lang['Format']['TheYear'].format(cart['YearTo'])
                ))
            else:
                description.append(lang['Format']['TheYear'].format(cart['YearFrom']))
        # 庁料金の再計算
        if prop['Country'] in ('JP',):
            fees = calculate_fees(prop, year_from=cart['YearFrom'], year_to=cart['YearTo'], additional=cart['AdditionalPeriod'])
            cart['FeeList'] = fees

    # 商標の庁料金
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        nc = len(prop['Classes'])
        if 'Classes' in cart:
            nc = len(cart['Classes'])
        fees = calculate_fees(prop, years=cart['Years'], classes=nc, additional=cart['AdditionalPeriod'])
        cart['FeeList'] = fees
        cart['YearRangeText'] = str(cart['Years'])
        cart['YearTo'] = (prop['PaidYears'] + cart['Years']) % 10
        if cart['YearTo'] == 0:
            cart['YearTo'] = 10
        description.append(lang['Format']['Years'].format(cart['Years']))

    # 手続期限
    if cart['AdditionalPeriod']:
        cart['NextProcedureLimit'] = common_util.add_months(prop['NextProcedureLimit'], 6)
        description.append(lang['Pages']['Request']['AdditionalPrice'])
    else:
        cart['NextProcedureLimit'] = prop['NextProcedureLimit']

    for key in ('OfficialFee', 'AgentFee',):
        if key in cart:
            del cart[key]

    # 合計の計算
    if 'FeeList' in cart:

        # 減免の有無の確認
        if len([x for x in cart['FeeList'] if 'Discount' in x]) > 0:
            description.append(lang['Pages']['Request']['Discount'])
        
        # 庁料金の計算
        fee, cur, _ = total_fee_list(cart['FeeList'], 'Office')
        if fee > 0:
            cart['OfficialFee'] = {
                'Amount': fee,
                'Currency': cur,
                'TaxRate': 0.0,
                'TaxRateText': "-",
            }

        # 事務所手数料の計算
        fee, cur, _ = total_fee_list(cart['FeeList'], 'Agent', 'Fee')
        if fee > 0:
            cart['AgentFee'] = {
                'Amount': fee,
                'Currency': cur,
            }
            # 税抜金額
            if cur == 'JPY':
                cart['AgentFee']['AmountWitoutTax'], _, _ = total_fee_list(cart['FeeList'], 'Agent', 'FeeWithoutTax')
                cart['AgentFee']['Tax'], _, _ = total_fee_list(cart['FeeList'], 'Agent', 'Tax')
                temp = [x for x in cart['FeeList'] if x['Kind'] == 'Agent']
                if len(temp) > 0:
                    cart['AgentFee']['TaxRate'] = temp[0]['TaxRate']
                    cart['AgentFee']['TaxRateText'] = temp[0]['TaxRateText']

    else:

        # 要見積
        cart['RequireEstimation'] = True

    if len(description) > 0:
        cart['Description'] = description
    elif 'Description' in cart:
        del cart['Description']

    # 更新用オブジェクトを返す
    return cart

@app.get('/ready')
@auth.require()
@auth.client_only()
def cart_page_default(info=None, alert=None):
    """
    カートフォーム
    """
    # 言語設定
    lang = web_util.get_ui_texts()

    # 対象をカテゴリーで分ける
    doc = {
        'Candidates': {
            '0001': {
                'Request': [],
                'Estimate': [],
            },
            '0002': {
                'Request': [],
                'Estimate': [],
            },
            '9999': {
                'Invalid': [],
            },
        },
    }

    with DbClient() as db:

        # 通貨情報の取得
        currencies = common_util.get_currencies(db)

        # カート内を再計算
        update_fees_in_cart(db)

        # 現在カートに入っている権利を取得
        props = db.Properties.find({
            'User': auth.get_account_id(),
            'Ignored': {'$exists': False},
            'Cart': {'$exists': True},
        })

        # 権利の情報を付与
        for prop in props:

            # 情報を付与
            prop['LawName'] = lang['Law'][prop['Law']]
            if prop['Country'] != 'UNK':
                prop['CountryDescription'] = lang['Country'][prop['Country']]

            # 権利者名を結合
            if 'Holders' in prop:
                prop['HolderNames'] = ','.join([x['Name'] for x in prop['Holders'] if 'Name' in x])

            # 依頼不可メッセージの変換
            if not prop['Cart']['Requestable']:
                prop['Cart']['WarningMessage'] = lang['Pages']['Property']['NotRequestable'][prop['Cart']['WarningMessage']]
                if not 'InvalidCandidates' in doc:
                    doc['InvalidCandidates'] = {'Properties':[]}
                doc['Candidates']['9999']['Invalid'].append(prop)
                continue

            # 料金計算済み
            if 'OfficialFee' in prop['Cart']:
                # 計算済み
                prop['Cart']['OfficialFeeText'] = currencies[prop['Cart']['OfficialFee']['Currency']]['Format'].format(prop['Cart']['OfficialFee']['Amount'])
                prop['Cart']['OfficialFeeCurrency'] = prop['Cart']['OfficialFee']['Currency']
                prop['Cart']['AgentFeeText'] = currencies[prop['Cart']['AgentFee']['Currency']]['Format'].format(prop['Cart']['AgentFee']['Amount'])
                prop['Cart']['AgentFeeCurrency'] = prop['Cart']['AgentFee']['Currency']
                doc['Candidates'][prop['Cart']['Agent']]['Request'].append(prop)
            else:
                # 要見積
                doc['Candidates'][prop['Cart']['Agent']]['Estimate'].append(prop)

    # 空ではない候補の展開
    keys = []

    for key1 in ('0001', '0002', '9999',):
        for key2 in ('Request', 'Estimate', 'Invalid',):
            if key2 in doc['Candidates'][key1] and len(doc['Candidates'][key1][key2]) > 0:
                key = {
                    'Agent': key1,
                    'AgentName': lang['Agent'][key1],
                    'Category': key2,
                    'FirstLimit': min([x['Cart']['NextProcedureLimit'] for x in doc['Candidates'][key1][key2]])
                }
                if key2 == 'Request':
                    key['CategoryMessage'] = lang['Pages']['Request']['TEXT000060'].format(lang['Agent'][key1])
                elif key2 == 'Estimate':
                    key['CategoryMessage'] = lang['Pages']['Request']['TEXT000061'].format(lang['Agent'][key1])
                elif key2 == 'Invalid':
                    key['CategoryMessage'] = lang['Pages']['Request']['TEXT000062']
                keys.append(key)

    doc['Keys'] = keys

    # 空判定
    doc['IsEmpty'] = (len(keys) == 0)

    # ページの生成
    return web_util.apply_template('user_cart_1', doc=doc, info=info, alert=alert, csrf_name='user_cart')

def update_years_in_cart(id, direction):
    """
    カートに設定された納付年数を更新する
    """
    with DbClient() as db:

        # 情報の取得
        prop = db.Properties.find_one({'_id': id})

        # 依頼可否の判定
        check, _, max_year, additional = common_util.is_requestable(db, id, consider_cart=False)

        # 最小年数の設定
        if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
            min_year = 5
            step = 5
        else:
            min_year = 1
            step = 1

        # 更新後の年数を試算
        new_year = int(prop['Cart']['Years']) + (step * direction)

        # 範囲判定
        if new_year < min_year or new_year > max_year:
            return False

        # 更新
        db.Properties.update_one(
            {'_id': id},
            {'$set': {'Cart.Years': new_year, 'Timestamp': datetime.now()}}
        )

        # 再計算
        update_fees_in_cart(db, prop_id=id)

        # 結果を返す
        return True

def remove_from_cart(id):
    """
    候補の削除
    """
    with DbClient() as db:

        # 候補マークの削除
        res = db.Properties.update_one(
            {'_id': id, 'User': auth.get_account_id()},
            {'$set':{'Timestamp': datetime.now()}, '$unset': {'Cart': ''}}
        )

    # 成否を返す
    return (res.matched_count == 1)

def update_classes_in_cart(id, up_class, act):
    """
    カートの中の区分の更新有無を切り替える
    """

    with DbClient() as db:

        # 通貨情報の取得
        currencies = common_util.get_currencies(db)

        # 権利情報の取得
        prop = db.Properties.find_one({'_id': id})

        # 知らない区分が指定されていないかチェック
        if not 'Cart' in prop or not up_class in prop['Classes']:
            return {'result': False, 'message': 'invalid class is specified.'}

        temp = prop['Classes']
        if 'Classes' in prop['Cart']:
            temp = prop['Cart']['Classes']

        # 削除によって選択区分がゼロになるのはNG
        if act == 'off' and len(temp) == 1:
            return {'result': False, 'message': 'no class is selected.'}

        # 選択状態の変更
        if act == 'on':
            if not up_class in temp:
                temp.append(up_class)
                temp = sorted(temp)
        elif act == 'off':
            if up_class in temp:
                temp = [x for x in temp if x != up_class]

        # 候補を更新
        res = db.Properties.update_one(
            {'_id': id},
            {'$set':{
                'Cart.Classes': temp,
                'Timestamp': datetime.now(),
            }}
        )

        if (res.matched_count < 1):
            return {'result': False, 'message': 'no data'}

        # 料金の再計算
        update_fees_in_cart(db, prop_id=id)

        # 計算後の情報を再取得
        prop = db.Properties.find_one({'_id': prop['_id']})

        res = {
            'result': True,
            'selected': temp
        }
        if 'OfficialFee' in prop['Cart']:
            res['officialFee'] = prop['Cart']['OfficialFee']
            res['officialFeeText'] = currencies[prop['Cart']['OfficialFee']['Currency']]['Format'].format(prop['Cart']['OfficialFee']['Amount'])

    # 取得した情報を返す
    return res

def calculate_fees(prop, year_from=0, year_to=0, years=0, classes=None, additional=False, user_id=None):
    """
    料金の計算
    """
    # 言語設定の取得
    lang = web_util.get_ui_texts()

    # 計算
    return fee_calculator.calculate_fees(prop, lang, year_from=year_from, year_to=year_to, years=years, classes=classes, additional=additional)

def total_fee_list(fee_list, kind, field='Fee'):
    """
    料金明細を集計する
    """
    # 集計
    return fee_calculator.total_fee_list(fee_list, kind, field=field)

def total_fees_for_request(targets, currencies, user_currency):
    """
    依頼対象の金額を集計する
    """
    # 合計用のオブジェクト
    totals = {}
    taxs = {}
    gensen_tmp = {}
    has_additional = False
    cur_rates = {}
    gensen = {}
    kazei = {}

    # 換算に必要なレート情報のみを抽出
    for target in targets:
        if not 'Cart' in target or not 'FeeList' in target['Cart']:
            continue
        for x in target['Cart']['FeeList']:
            if not x['Currency'] in cur_rates:
                cur_rates[x['Currency']] = {
                    user_currency: currencies[x['Currency']][user_currency] if x['Currency'] != user_currency else 1.0
                }
            elif not user_currency in cur_rates[x['Currency']]:
                cur_rates[x['Currency']][user_currency] = currencies[x['Currency']][user_currency] if x['Currency'] != user_currency else 1.0

    # 金額集計
    for target in targets:

        # 明細小計の再計算（元通貨、ユーザー通貨）
        sub_total = {
            'Office': {
                'Amount': 0.0,
                'ExchangedAmount': 0.0,
                'Tax': 0.0,
                'ExchangedTax': 0.0,
            },
            'Agent': {
                'Amount': 0.0,
                'ExchangedAmount': 0.0,
                'Tax': 0.0,
                'ExchangedTax': 0.0,
            },
        }

        # 明細ごとに集計（料金種別ごとに集計）
        for x in target['Cart']['FeeList']:

            if x['Fee'] > 0:

                # Key1: 通貨
                if not x['Currency'] in totals:
                    totals[x['Currency']] = {}
                # Key2: 料金種別(Office/Agent)
                if not x['Kind'] in totals[x['Currency']]:
                    assert x['Kind'] in ('Office', 'Agent',)
                    totals[x['Currency']][x['Kind']] = {}
                # Key3: 表示税率
                if not 'TaxRateText' in x:
                    x['TaxRateText'] = '-'
                if not x['TaxRateText'] in totals[x['Currency']][x['Kind']]:
                    # list -> 0.為替換算前 1.為替換算後
                    totals[x['Currency']][x['Kind']][x['TaxRateText']] = [0.0, 0.0,]
                
                # 料金合計を計算
                v = x['Fee']
                totals[x['Currency']][x['Kind']][x['TaxRateText']][0] += v
                sub_total[x['Kind']]['Amount'] += v
                if x['Currency'] != user_currency:
                    v *= cur_rates[x['Currency']][user_currency]
                    v = common_util.fit_currency_precision(v, currencies[user_currency]['Precision'])
                totals[x['Currency']][x['Kind']][x['TaxRateText']][1] += v
                sub_total[x['Kind']]['ExchangedAmount'] += v

                # 課税対象の合計を計算
                if 'TaxRate' in x:
                    v = x['Fee']
                    if not x['Currency'] in kazei:
                        # list -> 0.為替換算前 1.為替換算後
                        kazei[x['Currency']] = {x['TaxRate']: [0.0, 0.0]}
                    if not x['TaxRate'] in kazei[x['Currency']]:
                        kazei[x['Currency']][x['TaxRate']] = [0.0, 0.0]
                    kazei[x['Currency']][x['TaxRate']][0] += v
                    if x['Currency'] != user_currency:
                        v *= cur_rates[x['Currency']][user_currency]
                        v = common_util.fit_currency_precision(v, currencies[user_currency]['Precision'])
                    kazei[x['Currency']][x['TaxRate']][1] += v

                # 源泉徴収税対象額
                if target['Cart']['Agent'] == "0002" and x['Kind'] == 'Agent':
                    v = x['Fee']
                    if not x['Currency'] in gensen_tmp:
                        # list -> 0.為替換算前 1.為替換算後
                        gensen_tmp[x['Currency']] = [0.0, 0.0]
                    gensen_tmp[x['Currency']][0] += v
                    if x['Currency'] != user_currency:
                        v *= cur_rates[x['Currency']][user_currency]
                        v = common_util.fit_currency_precision(v, currencies[user_currency]['Precision'])
                    gensen_tmp[x['Currency']][1] += v

                # 追納判定
                if 'AdditionalPayment' in x and x['AdditionalPayment']:
                    has_additional = True
                
        # 明細合計を更新する（同時に整形済みテキストを設定）
        for key1 in ('Office', 'Agent',):
            item_name = 'OfficialFee' if key1 == 'Office' else key1 + 'Fee'
            for key2 in ('Amount', 'ExchangedAmount', 'Tax', 'ExchangedTax',):
                target["Cart"][item_name][key2] = sub_total[key1][key2]
                if key2.startswith("Exchanged"):
                    target["Cart"][item_name][key2 + "Text"] = currencies[user_currency]["Format"].format(sub_total[key1][key2])
                else:
                    target["Cart"][item_name][key2 + "Text"] = currencies[target["Cart"][item_name]["Currency"]]["Format"].format(sub_total[key1][key2])

    if len(kazei) > 0:

        # 消費税の計算
        for cur in kazei.keys():
            for tax_rate in kazei[cur].keys():
                tax = common_util.fit_currency_precision(kazei[cur][tax_rate][0] * tax_rate, currencies[cur]['Precision'])
                tax_ex = tax
                if cur != user_currency:
                    tax_ex *= currencies[cur][user_currency]
                    tax_ex = common_util.fit_currency_precision(tax_ex, currencies[user_currency]['Precision'])
                taxs[cur] = {'Tax': {'{:.2f}%'.format(tax_rate * 100): [tax, tax_ex]}}

        # 計算結果を合計に追加
        for cur in taxs.keys():
            for kind in taxs[cur].keys():
                for tax_rate_text in taxs[cur][kind].keys():
                    totals[cur][kind] = {tax_rate_text: taxs[cur][kind][tax_rate_text]}

    if len(gensen_tmp) > 0:

        # 源泉徴収税の計算
        for cur in gensen_tmp.keys():
            if cur == 'JPY':
                tax_rate = 0.1021
            else:
                raise Exception('%s is not supported for source withholding tax.' % cur)
            tax = -1.0 * common_util.fit_currency_precision(gensen_tmp[cur][0] * tax_rate, currencies[cur]['Precision'])
            tax_ex = tax
            if cur != user_currency:
                tax_ex *= currencies[cur][user_currency]
                tax_ex = common_util.fit_currency_precision(tax_ex, currencies[user_currency]['Precision'])
            gensen[cur] = {'SourceWithholdingTax': {'{:.2f}%'.format(tax_rate * 100): [tax, tax_ex]}}

        # 計算結果を合計に追加
        for cur in gensen.keys():
            for kind in gensen[cur].keys():
                for tax_rate_text in gensen[cur][kind].keys():
                    totals[cur][kind] = {tax_rate_text: gensen[cur][kind][tax_rate_text]}

    # 集計結果を返す
    return targets, totals, taxs, gensen, cur_rates, has_additional

def create_request_object(agent, category, targets, totals, taxs, gensen, cur_rates, user_currency, currencies, lang, has_additional):
    """
    依頼登録用のオブジェクトを生成する
    """
    # 依頼情報をまとめる
    req_obj = {
        'Targets': targets,
        'Agent': agent,
        'Category': category,
    }

    if 'User' in targets[0]:
        req_obj['User'] = targets[0]['User']

    # 小計
    if len(totals) > 0:
        req_obj['SmallAmounts'] = totals

    # 為替レート
    if len(cur_rates) > 0:
        req_obj['ExchangeRate'] = cur_rates

    # 通貨別の小計
    amounts = {}
    # 通貨別・為替換算後の小計
    amounts_ex = {}
    # 総合計（為替換算後）
    amount = 0.0

    if category == "Request":
        for cur in totals.keys():
            if not cur in amounts:
                amounts[cur] = 0.0
                amounts_ex[cur] = 0.0
            for key1 in totals[cur].keys():
                for key2 in totals[cur][key1].keys():
                    v = totals[cur][key1][key2]
                    amounts[cur] += v[0]
                    amounts_ex[cur] += v[1]
                    amount += v[1]
        req_obj['Amounts'] = amounts
        req_obj['ExchangedAmounts'] = amounts_ex
        req_obj['TotalAmount'] = amount
        req_obj['Currency'] = user_currency
        req_obj['CurrencyLocal'] = lang.local_currency(user_currency)

    # 入金期限の計算
    # 2週間後または最早の手続期限の前日
    today = common_util.get_today()
    temp = [x['Cart']['NextProcedureLimit'] for x in targets if 'Cart' in x]
    if len(temp) > 0:
        d1 = today + timedelta(days=2 * 7)
        d2 = min([x['Cart']['NextProcedureLimit'] for x in targets]) - timedelta(days=1)
        if d2 < d1:
            d1 = d2
        if d1 < today:
            d1 = today
        req_obj['PayLimit'] = d1

    # 計算結果を暗号化 -> 完了画面への引継ぎ用
    req_obj['cdata'] = security.encrypt_dict(req_obj)

    # 合計を表形式に変換
    total_table = []

    for cur in totals:
        for kind in ('Office', 'Agent', 'Tax', 'SourceWithholdingTax',):
            if not kind in totals[cur]:
                continue
            for tax_rate in totals[cur][kind]:
                if kind == 'Office':
                    name = 'OfficialFee'
                elif kind == 'Agent':
                    name = 'AgentFee'
                elif kind == 'Tax':
                    name = 'Tax'
                elif kind == 'SourceWithholdingTax':
                    name = 'SourceWithholdingTax'
                row = [
                    lang.local_currency(cur),
                    lang['Vocabulary'][name],
                    "",
                    currencies[cur]['Format'].format(totals[cur][kind][tax_rate][0]),
                    "",
                    currencies[user_currency]['Format'].format(totals[cur][kind][tax_rate][1]),
                    "",
                    "",
                ]
                if name == 'OfficialFee':
                    row[2] = lang['Vocabulary']['TaxExempt']
                if name == 'AgentFee':
                    row[2] = lang['Pages']['Request']['TEXT000080'] + ' ' + tax_rate
                if name == 'Tax':
                    row[1] = lang['Vocabulary'][name] + '(' + tax_rate + ')'
                if name == 'SourceWithholdingTax':
                    row[2] = lang['Pages']['Request']['TEXT000080'] + ' ' + tax_rate

                total_table.append(row)

        # 複数通貨が混在する場合は通貨別小計を表示
        if len(amounts) > 1:
            total_table.append([
                lang.local_currency(cur),
                lang.local_currency(cur) + lang['Vocabulary']['SmallAmount'],
                "",
                currencies[cur]['Format'].format(amounts[cur]),
                "",
                currencies[user_currency]['Format'].format(amounts_ex[cur]),
                "",
                "sub-total-row",
            ])

    if len(total_table) > 0:
        req_obj['Totals'] = total_table

    # 数値整形
    if 'TotalAmount' in req_obj:
        req_obj['TotalAmountText'] = currencies[user_currency]['Format'].format(req_obj['TotalAmount'])

    # 追納の有無
    req_obj['HasAdditional'] = has_additional

    # 生成したオブジェクトを返す
    return req_obj

def requestable_agents_and_categories(db):
    """
    依頼可能なカテゴリーを取得する
    """
    cats = []

    for key1 in ('Request', 'Estimate',):
        for key2 in ('0001', '0002',):
            q = {
                'User': auth.get_account_id(),
                'Cart.Years': {'$gte': 1},
                'Cart.Agent': key2,
                'Ignored': {'$exists': False}
            }
            if key1 == 'Request':
                q['$and'] = [
                    {'Cart.OfficialFee': {'$exists': True}},
                    {'Cart.Requestable': True},
                ]
            else:
                # if Estimate
                q['$and'] = [
                    {'Cart.OfficialFee': {'$exists': False}},
                    {'Cart.Requestable': True},
                ]
            if db.Properties.count_documents(q) > 0:
                cats.append([key2, key1,])

    # 結果を返す
    return cats

@app.route('/order/confirm/<agent>/<category>')
@auth.require()
@auth.client_only()
def cart_page_order(agent, category):
    """
    手続依頼
    """
    return cart_page_order_core(agent, category)

def cart_page_order_core(agent, category, user_org=None, user_name=None, message=None):
    """
    手続依頼
    """
    if not agent in ('0001', '0002',):
        abort(400)
    if not category in ('Request', 'Estimate',):
        abort(400)
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 通貨情報の取得
        currencies = common_util.get_currencies(db)

        # 再計算
        update_fees_in_cart(db)

        # 依頼可能なカテゴリー
        requestable_keys = requestable_agents_and_categories(db)

        # ユーザー情報の取得
        user = db.Users.find_one({'_id': auth.get_account_id()})

        # ユーザー通貨の特定
        if not 'Currency' in user:
            user['Currency'] = 'JPY'
        usr_cur = user['Currency']

        if user_name is None:
            #user_name = user['Name']
            #if 'Organization' in user:
            #    user_org = user['Organization']
            #else:
            #    user_org = ''
            user_name = ''
            user_org = ''

        # 通貨別の対象リスト
        targets = []

        # クエリー
        q = {
            'User': auth.get_account_id(),
            'Cart.Years': {'$gte': 1},
            'Cart.Agent': agent,
            'Ignored': {'$exists': False}
        }

        if category == 'Request':
            q['$and'] = [
                {'Cart.OfficialFee': {'$exists': True}},
                {'Cart.Requestable': True},
            ]
        else:
            # if Estimate
            q['$and'] = [
                {'Cart.OfficialFee': {'$exists': False}},
                {'Cart.Requestable': True},
            ]

        # 対象の抽出
        targets_tmp = db.Properties.find(q)
        targets_tmp = list(targets_tmp)

        # 対象が存在しない場合、別のカテゴリーでの候補の存在をチェック
        if len(targets_tmp) == 0:

            tmp = [x for x in requestable_keys if x[0] != agent or x[1] != category]
            if len(tmp) > 0:
                print('a')
                return cart_page_order(tmp[0][0], tmp[0][1])

            # まったく該当がない場合は候補が存在しない旨の表示
            return web_util.apply_template('user_cart_2', doc={}, csrf_name='user_cart')

        # 合計オブジェクト
        totals = {}
        taxs = {}
        has_additional = False
        cur_rates = {}
        gensen = {}

        for target in targets_tmp:

            # 依頼可否判定
            # ※カートに追加した後に依頼不可の事由が発生した場合に該当
            r1, _, max_year, additional = common_util.is_requestable(db, target['_id'], consider_cart=False)
            assert r1, 'Invalid Operation.'
            # TODO: 該当する場合の表示方法を修正

            # 国名、法令名を付与
            if target['Country'] != 'UNK':
                target['CountryDescription'] = lang['Country'][target['Country']]
            target['LawName'] = lang['Law'][target['Law']]

            # 権利者名の結合（表示用）
            if 'Holders' in target:
                target['HolderNames'] = ','.join([x['Name'] for x in target['Holders'] if 'Name' in x])

            # 年数の上限、下限を設定
            target['Cart']['MaxYears'] = max_year
            target['Cart']['MinYears'] = 1
            if target['Law'] == 'Trademark':
                target['Cart']['MinYears'] = 5

            # 減免対象候補
            if target['Country'] == 'JP' and target['Law'] == 'Patent':
                if target['PaidYears'] > 10:
                    # 11年目以降は減免なし
                    pass
                elif 'ExamClaimedDate' in target and target['ExamClaimedDate'] >= datetime(2019, 4, 1):
                    # 権利者名から適用される減免の区分を判定
                    if 'Holders' in target:
                        tmp = [x['Name'] for x in target['Holders'] if 'Name' in x]
                        if len(tmp) > 0:
                            tmp = [common_util.check_jp_genmen(x) for x in tmp]
                            # 異なる区分をもつ複数権利者がいる場合は減免を受け付けない
                            if not common_util.check_more_two(tmp) and not tmp[0] is None:
                                target['JpGenmenCandidate'] = tmp[0]
                                target['JpGenmenCandidateText'] = lang['JpGenmenShort'][tmp[0]]
                elif 'ExamClaimedDate' in target and target['ExamClaimedDate'] < datetime(2014, 4, 1):
                    # Nothing
                    pass
                else:
                    target['JpGenmenCandidate'] = 'H25_98_66'
                    target['JpGenmenCandidateText'] = lang['JpGenmenShort']['H25_98_66']
            
            # 減免区分が候補と一致しない場合は削除する
            if 'JpGenmen' in target:
                if not 'JpGenmenCandidate' in target or target['JpGenmen'] != target['JpGenmenCandidate']:
                    del target['JpGenmen']

            # 対象に追加
            targets.append(target)
    
        # 並べ替え
        targets = sorted(targets, key=operator.itemgetter('Country', 'Law'))
        
        if category == "Request":

            # 明細を集計
            targets, totals, taxs, gensen, cur_rates, has_additional = total_fees_for_request(targets, currencies, usr_cur)

    # 表示・登録用のオブジェクトに加工する
    req_obj = create_request_object(
        agent, category, targets, totals, taxs, gensen,
        cur_rates, usr_cur, currencies,
        lang, has_additional
    )

    # 受任者名
    req_obj['AgentName'] = lang['Agent'][agent]

    if len(requestable_keys) > 1:
        tmp = []
        for a in requestable_keys:
            if a[0] == agent and a[1] == category:
                continue
            tmp.append({
                'AgentName': lang['Agent'][a[0]],
                'Agent': a[0],
                'Category': a[1],
            })
        req_obj['OtherAgents'] = tmp

    # 請求書のあて名
    req_obj['Organization'] = user_org
    req_obj['UserName'] = user_name

    # メッセージ
    if not message is None:
        req_obj['Message'] = message

    # 通貨の表示
    for target in req_obj['Targets']:
        if 'OfficialFee' in target['Cart']:
            target['Cart']['OfficialFee']['CurrencyLocal'] = lang.local_currency(target['Cart']['OfficialFee']['Currency'])
        if 'AgentFee' in target['Cart']:
            target['Cart']['AgentFee']['CurrencyLocal'] = lang.local_currency(target['Cart']['AgentFee']['Currency'])
    req_obj['CurrencyLocal'] = lang.local_currency(req_obj['Currency'])

    # 年分表示の調整
    for target in req_obj['Targets']:
        if 'YearRangeText' in target['Cart']:
            if target['Law'] in ('Patent', 'Utility', 'Design',):
                if target['Cart']['YearTo'] > target['Cart']['YearFrom']:
                    target['Cart']['YearRangeText'] = lang['Format']['TheYearRange'].format(target['Cart']['YearFrom'], target['Cart']['YearTo'])
                else:
                    target['Cart']['YearRangeText'] = lang['Format']['TheYear'].format(target['Cart']['YearFrom'])
            elif target['Law'] == 'Trademark':
                target['Cart']['YearRangeText'] = lang['Format']['Years'].format(target['Cart']['Years'])

    # 追納分の期限表示を追納の期限に変更
    for target in req_obj['Targets']:
        if common_util.in_and_true(target['Cart'], 'AdditionalPeriod'):
            if 'NextProcedureLimit' in target:
                if 'NextProcedureLastLimit' in target:
                    target['NextProcedureLimit'] = target['NextProcedureLastLimit']
                else:
                    target['NextProcedureLimit'] = common_util.add_months(target['NextProcedureLimit'], 6)

    # 最早の期限日を取得
    tmp = [target['NextProcedureLimit'] for target in req_obj['Targets'] if 'NextProcedureLimit']
    if len(tmp) > 0:
        req_obj['FastestProcedureLimit'] = min(tmp)

    # 確認ページを生成
    return web_util.apply_template('user_cart_2', doc=req_obj, csrf_name='user_cart')

def clean_up_targets(targets):
    """
    対象リストを登録に必要な項目だけにする
    """
    new_targets = []

    # 登録に必要な項目のみのターゲットリストに置き換える
    for i in range(len(targets)):
        temp = {
            'Years': targets[i]['Cart']['Years'],
            'Completed': False,
        }
        if '_id' in targets[i]:
            temp['Property'] = targets[i]['_id']
        for k in ('NumberOfClaims', 'PaidYears', 'Timestamp',):
            if k in targets[i]:
                temp[k] = targets[i][k]
        if 'Classes' in targets[i]:
            temp['OriginalClasses'] = targets[i]['Classes']
        for k in ('Classes', 'OriginalClasses', 'YearFrom', 'YearTo', 
                  'FeeList', 'NextProcedureLimit', 'Timestamp', 'AdditionalPeriod'):
            if k in targets[i]['Cart']:
                temp[k] = targets[i]['Cart'][k]
        new_targets.append(temp)

    # 新しいリストを返す
    return new_targets

def update_jp_genmen(db, prop_id, enable):
    """
    減免区分を更新する
    """
    prop = db.Properties.find_one({'_id': prop_id})

    if prop is None:
        return

    if enable:

        # 有効化
        if prop['Country'] == 'JP' and prop['Law'] == 'Patent':
            kubun = None
            if prop['PaidYears'] > 10:
                # 11年目以降は減免なし
                pass
            elif 'ExamClaimedDate' in prop and prop['ExamClaimedDate'] >= datetime(2019, 4, 1):
                # 権利者名から適用される減免の区分を判定
                if 'Holders' in prop:
                    tmp = [x['Name'] for x in prop['Holders'] if 'Name' in x]
                    if len(tmp) > 0:
                        tmp = [common_util.check_jp_genmen(x) for x in tmp]
                        # 異なる区分をもつ複数権利者がいる場合は減免を受け付けない
                        if not common_util.check_more_two(tmp) and not tmp[0] is None:
                            kubun = tmp[0]
            else:
                kubun = 'H25_98_66'
            if not kubun is None:
                db.Properties.update_one(
                    {'_id': prop_id,},
                    {'$set': {'JpGenmen': kubun},}
                )
            else:
                db.Properties.update_one(
                    {'_id': prop_id,},
                    {'$unset': {'JpGenmen': ''},}
                )

    else:

        # 無効化
        db.Properties.update_one(
            {'_id': prop_id,},
            {'$unset': {'JpGenmen': ''},}
        )

    return True

@app.post('/order/accept')
@auth.require()
@auth.client_only()
def cart_page_accept():
    """
    カートページ →手続依頼の受付
    """
    posted = web_util.get_posted_data(csrf_name='user_cart')
    cdata = security.decrypt_dict(posted['cdata'])
    targets = cdata['Targets']
    agent = cdata['Agent']
    category = cdata['Category']
    lang = web_util.get_ui_texts()

    # 操作の取得
    action = posted['Action'] if 'Action' in posted else ''
    params = action.split('_')

    user_org = ''
    user_name = ''
    if 'UserName' in posted:
        user_name = posted['UserName']
    if 'Organization' in posted:
        user_org = posted['Organization']

    if params[0] == 'years':

        # カート内の年数を更新
        prop_id = ObjectId(params[2])
        update_years_in_cart(prop_id, -1 if params[1] == 'dec' else 1)

        # ページを再表示
        return cart_page_order_core(agent, category, user_name=user_name, user_org=user_org)

    elif params[0] == 'tmclass':

        # カート内の区分を更新
        prop_id = ObjectId(params[1])
        update_classes_in_cart(prop_id, params[3], params[2])

        # ページを再表示
        return cart_page_order_core(agent, category, user_name=user_name, user_org=user_org)

    elif params[0] == 'jpgenmen':

        # カート内の区分を更新
        prop_id = ObjectId(params[1])
        with DbClient() as db:
            update_jp_genmen(db, prop_id, params[2] == 'on')

        # ページを再表示
        return cart_page_order_core(agent, category, user_name=user_name, user_org=user_org)

    elif params[0] == 'remove':

        # カートから削除
        remove_from_cart(ObjectId(params[1]))

        # ページを再表示
        return cart_page_order_core(agent, category, user_name=user_name, user_org=user_org)

    if params[0] != 'Request':
        abort(403, 'Invalid operation.')

    # 請求書のあて名のチェック
    if user_name is None or user_name == '':
        # ページを再表示
        return cart_page_order_core(agent, category, user_name=user_name, user_org=user_org, message=lang['Pages']['Request']['TEXT000214'])

    # 登録に必要な項目のみのターゲットリストに置き換える
    targets = clean_up_targets(targets)

    # 依頼を登録する
    req_id, req_num, req_time, has_invoice, _, _ = register_request(agent, category, targets, cdata, user_id=auth.get_account_id(), user_name=user_name, user_org=user_org)

    with DbClient() as db:
        # 表示用にユーザー情報を取得する
        req_info = db.Requests.find_one({'_id': req_id}, {'User': 1})
        user_info = db.Users.find_one({'_id': req_info['User']})

    # 受付済のページを生成
    result_doc = {
        'RequestId': req_id,
        'RequestNumber': req_num,
        'RequestedTime': req_time,
        'HasInvoice': has_invoice,
        'NeedsDelegation': False,
        'NeedsAbandonment': False,
    }
    if 'PayLimit' in cdata:
        result_doc['PayLimit'] = cdata['PayLimit']
    result_doc['UserName'] = user_name
    if user_org:
        result_doc['Organization'] = user_org
    return web_util.apply_template('user_cart_3', doc=result_doc)

def register_request(agent, category, targets, cdata, user_id=None, user_name=None, user_org=None, user_email=None):
    """
    依頼を登録する
    """
    if user_id is None:
        user_id = auth.get_account_id()

    with DbClient() as db:

        # 依頼番号（連番の取得）
        num = db.next_number('Request')
        now = datetime.now()
        currencies = common_util.get_currencies(db)

        # 依頼番号v2の生成（日付文字列+連番）
        req_num_base = now.strftime('%Y%m%d')[2:]
        i = 1
        req_num = '%s-%d' % (req_num_base, i)
        while db.Requests.count_documents({'RequestNumberV2': req_num,}) > 0:
            i += 1
            req_num = '%s-%d' % (req_num_base, i)

        # 依頼の登録
        req = {
            'RequestedTime': now,
            'RequestNumber': num,
            'RequestNumberV2': req_num,
            'User': user_id,
            'Properties': targets,
            'PayLimit': cdata['PayLimit'],
            'Invoice': [],
            'Agent': agent,
        }
        if not user_name is None:
            req['UserName'] = user_name
        if not user_org is None:
            req['UserOrganization'] = user_org
        if not user_email is None:
            req['UserMailAddress'] = user_email

        # 通貨別小計
        if 'Amounts' in cdata:
            req['Amounts'] = cdata['Amounts']
            req['ExchangedAmounts'] = cdata['ExchangedAmounts']

        if 'SmallAmounts' in cdata:
            # キーの置き換え
            # ※MongoDBはキーに . を使えない
            temp = cdata['SmallAmounts']
            for cur in temp:
                for kind in temp[cur]:
                    keys = [x for x in temp[cur][kind].keys() if '.' in x]
                    if len(keys) > 0:
                        for key in keys:
                            new_key = key.replace(".", "__dot__")
                            temp[cur][kind][new_key] = temp[cur][kind][key]
                            del temp[cur][kind][key]
            req['SmallAmounts'] = temp

        # 合計
        if 'TotalAmount' in cdata:
            req['TotalAmount'] = cdata['TotalAmount']
            req['Currency'] = cdata['Currency']

        # 為替レート
        if 'ExchangeRate' in cdata:
            req['ExchangeRate'] = cdata['ExchangeRate']

        res = db.Requests.insert_one(req)
        req_id = res.inserted_id
        has_invoice = False
        invoice_file = None

        try:

            if category == "Request":

                # 請求書の生成
                invoice_file = invoice.make(req_id)

                # データベースへの登録
                db.Requests.update_one(
                    {'_id': req_id},
                    {
                        '$push': {'Invoice': {'File': invoice_file, 'Date': now}},
                    }
                )

                # フラグ
                has_invoice = True

            else:

                # 請求書なし
                db.Requests.update_one(
                    {'_id': req_id},
                    {
                        '$set': {'RequireEstimation': True },
                    }
                )

        except Exception as e:

            logger.exception('Cannot make a invoice. ')

            # 請求書の生成に失敗した場合、依頼の登録自体を無かったことにする
            db.Requests.delete_one({'_id': req_id})
            raise e

        # 権利情報の準備状態を解除
        db.Properties.update_many(
            {'_id': {'$in': [x['Property'] for x in targets]}},
            {'$set':{'Timestamp': datetime.now()}, '$unset':{'Cart': '', 'Ready': '', 'Ready_Classes': ''}}
        )

        # 権利にユーザー名を設定する
        if not user_name is None:
            q = {'$set': {'UserName': user_name}}
            if not user_org is None:
                q = {'$set': {'UserOrganization': user_org}}
            else:
                q = {'$unset': {'UserOrganization': ''}}
            db.Properties.update_many(
                {'_id': {'$in': [x['Property'] for x in targets]}},
                q
            )

        # 書類の要否判定
        needs_d, _ = common_util.needs_delegation_paper(req, db)
        needs_a, _ = common_util.needs_abandonment_paper(req, db)

        # メール通知
        lang = web_util.get_ui_texts()
        filename = lang['Mail']['MAIL0001']['TEXT000021']
        body_u = io.StringIO()
        body_s = io.StringIO()

        # メールの件名
        if common_util.not_in_or_false(req, 'RequireEstimation'):
            subject_u = lang['Mail']['MAIL0001']['TEXT000011'].format(lang.format_date(req['PayLimit'], ignore_year=True))
            subject_s = lang['Mail']['MAIL0002']['TEXT000011'].format(lang.format_date(req['PayLimit'], ignore_year=True))
        else:
            subject_u = lang['Mail']['MAIL0001']['TEXT000010']
            subject_s = lang['Mail']['MAIL0002']['TEXT000010']

        # ユーザー向けメールの前段
        user = db.Users.find_one({'_id': req['User']})
        body_u.write('\n')
        if 'UserName' in req:
            if 'UserOrganization' in req:
                body_u.write(req['UserOrganization'])
                body_u.write('\n')
            user_name = req['UserName']
        else:
            if 'Organization' in user:
                body_u.write(user['Organization'])
                body_u.write('\n')
            user_name = user['Name']
        body_u.write(lang['Mail']['MAIL0001']['TEXT000001'].format(user_name))
        body_u.write('\n\n')
        body_u.write(lang['Mail']['MAIL0001']['TEXT000002'])
        body_u.write('\n')

        if common_util.not_in_or_false(req, 'RequireEstimation'):

            # 見積不要（即請求書発行）の場合
            body_u.write(lang['Mail']['MAIL0001']['TEXT000003'])
            body_u.write('\n\n')
            body_u.write(lang['Invoice']['Agent'][req['Agent']]['BankOnMail'])
            body_u.write('\n\n')

            if 'SmallAmounts' in req:
                resum = {}
                for cur in req['SmallAmounts']:
                    for kind in req['SmallAmounts'][cur].keys():
                        for tax in req['SmallAmounts'][cur][kind].keys():
                            if not kind in resum:
                                resum[kind] = 0.0
                            # 通貨換算済みの値を合計
                            resum[kind] += req['SmallAmounts'][cur][kind][tax][1]
                cur_name = req['Currency']
                if req['Currency'] == 'JPY' and lang.name == 'ja':
                    cur_name = '円'
                if 'Tax' in resum and 'Agent' in resum:
                    resum['Agent'] += resum['Tax']
                    del resum['Tax']
                table = []
                for kind in ('Office', 'Agent', 'Tax', 'SourceWithholdingTax',):
                    if kind in resum:
                        table.append([
                            lang['Price'][kind],
                            currencies[req['Currency']]['Format'].format(resum[kind]),
                            cur_name,
                        ])
                if 'TotalAmount' in req:
                    table.append([
                        lang['Mail']['MAIL0001']['TEXT000020'],
                        currencies[req['Currency']]['Format'].format(req['TotalAmount']),
                        cur_name,
                    ])
                # 費目と金額の長さを測る（揃え）
                ln1 = max([common_util.text_width(x[0]) for x in table])
                ln2 = max([common_util.text_width(x[1]) for x in table])
                for i in range(len(table)):
                    # 費目は左寄せ
                    x = common_util.text_width(table[i][0])
                    if x < ln1:
                        table[i][0] += ' ' * int(2 * (ln1- x))
                    # 金額は右寄せ
                    x = common_util.text_width(table[i][1])
                    if x < ln2:
                        table[i][1] = (' ' * int(2 * (ln2 - x))) + table[i][1]
                # 金額の表示
                for row in table:
                    body_u.write('%s: %s%s\n' % (row[0], row[1], row[2]))
                body_u.write('\n')

            body_u.write(lang['Mail']['MAIL0001']['TEXT000009'])
            body_u.write('\n\n')

        else:

            # 要見積の場合
            body_u.write(lang['Mail']['MAIL0001']['TEXT000005'])
            body_u.write('\n\n')

        # スタッフ向けメールの前段
        body_s.write('\n')
        if 'UserName' in req:
            if 'UserOrganization' in req:
                body_s.write(req['UserOrganization'])
                body_s.write('\n')
        else:
            if 'Organization' in user:
                body_s.write(user['Organization'])
                body_s.write('\n')
        if common_util.not_in_or_false(req, 'RequireEstimation'):
            body_s.write(lang['Mail']['MAIL0002']['TEXT000002'].format(user_name))
        else:
            body_s.write(lang['Mail']['MAIL0002']['TEXT000003'].format(user_name))
        body_s.write('\n\n')

        n = 0

        for p in req['Properties']:

            # 権利情報の取得
            prop = db.Properties.find_one({'_id': p['Property']})

            # 件名とファイル名の構成
            if n == 0:
                tmp = ''
                tmp += lang['Law'][prop['Law']]
                tmp += prop['RegistrationNumber']
                tmp += lang['Common']['RegistrationNumberSuffix']
                if prop['Country'] == 'JP':
                    if prop['Law'] == 'Trademark':
                        tmp += '(%s)' % (lang['Mail']['MAIL0001']['TEXT000014'].format(p['Years']))
                    elif p['YearTo'] != p['YearFrom']:
                        tmp += '(%s)' % (lang['Mail']['MAIL0001']['TEXT000013'].format(p['YearFrom'], p['YearTo']))
                    else:
                        tmp += '(%s)' % (lang['Mail']['MAIL0001']['TEXT000012'].format(p['YearTo']))
                    if prop['Law'] == 'Trademark':
                        if p['Years'] == 10 or p['YearTo'] == 10:
                            tmp += lang['Mail']['MAIL0001']['TEXT000015']
                        else:
                            tmp += lang['Mail']['MAIL0001']['TEXT000017']
                    elif prop['Law'] == 'Patent':
                        tmp += lang['Mail']['MAIL0001']['TEXT000016']
                    else:
                        tmp += lang['Mail']['MAIL0001']['TEXT000017']
                if len(req['Properties']) > 1:
                    tmp += lang['Common']['MoreN'].format(len(req['Properties']) - 1)
                filename += '_%s.pdf' % tmp
                subject_u += tmp
                subject_s += tmp
                if common_util.not_in_or_false(req, 'RequireEstimation'):
                    subject_u += lang['Mail']['MAIL0001']['TEXT000018']
                else:
                    subject_u += lang['Mail']['MAIL0001']['TEXT000019']
                subject_s += lang['Mail']['MAIL0002']['TEXT000018']
            n += 1

            items = []
            if prop['Country'] == 'UNK':
                items.append(prop['CountryDescription'])
            else:
                items.append(lang['Country'][prop['Country']])
            items.append(lang['Law'][prop['Law']])
            items.append(prop['RegistrationNumber'])
            for proc in common_util.list_procedures(p, prop, lang):
                items.append(proc)
            body_s.write(' '.join(items))
            body_s.write('\n')

            if 'FeeList' in p:
                a, b, _ = total_fee_list(p['FeeList'], 'Office')
                a = currencies[b]['Format'].format(a)
                if b == 'JPY' and lang.name == 'ja':
                    a += ' 円'
                else:
                    a += ' ' + b
                body_s.write(lang['Mail']['MAIL0002']['TEXT000019'])
                body_s.write(': ')
                body_s.write(a)
                body_s.write('\n')

        # ユーザー向けメールの後段
        body_u.write(lang.mail_footer(req['Agent']))

        if len(req['Properties']) > 1:
            body_s.write('\n')

        # スタッフ向けメールの後段
        if 'TotalAmount' in req:
            a = currencies[req['Currency']]['Format'].format(req['TotalAmount'])
            if req['Currency'] == 'JPY' and lang.name == 'ja':
                a += ' 円'
            else:
                a += ' ' + req['Currency']
            body_s.write(lang['Mail']['MAIL0002']['TEXT000020'])
            body_s.write(': ')
            body_s.write(a)
            body_s.write('\n')
        
        if 'PayLimit' in req:
            body_s.write(lang['Mail']['MAIL0002']['TEXT000021'])
            body_s.write(': ')
            body_s.write(lang.format_date(req['PayLimit']))
            body_s.write('\n')
            
        body_s.write('\n')
        body_s.write('Login: ' + web_util.complete_url('/login'))
        body_s.write('\n\n')
        body_s.write(lang.mail_footer(req['Agent']))

        # ユーザー向けメールの送信
        to_addr, cc_addr, bcc_addr = db.get_mail_addresses(req['User'])
        if has_invoice:
            attachments = [{'Name': filename, 'Data': invoice_file},]
        else:
            attachments = None
        mail.send_mail(
            subject_u,
            body_u.getvalue(),
            to=to_addr, cc=cc_addr, bcc=bcc_addr,
            attachments=attachments,
        )

        # スタッフ向けメールの送信
        to_addr, cc_addr, bcc_addr = db.get_staff_addresses()
        mail.send_mail(
            subject_s,
            body_s.getvalue(),
            to=to_addr, cc=cc_addr, bcc=bcc_addr,
            attachments=attachments,
        )

        # StringIOの破棄
        body_u.close()
        body_s.close()
    
    # 各種情報を返す
    return req_id, num, now, has_invoice, needs_d, needs_a

def get_direct_parameters():
    """
    URLから直接開けるページでのパラメーターを取得する
    """
    # GETパラメーターを取得
    v = request.query.t
    if v is None or v == '':
        return None, None
    # 復号
    v = str(v)
    v = security.decrypt(v)
    if v is None:
        return None, None
    # タブで分割
    v = v.split('\t')
    if len(v) != 2:
        return None, None
    # ObjectIdに変換
    try:
        return ObjectId(v[0]), ObjectId(v[1])
    except ValueError:
        return None, None

@app.get('/d/req')
def direct_request_page():
    """
    URLから直接開く依頼ページ (非ログイン)
    """
    # IDの取得
    user_id, prop_id = get_direct_parameters()
    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10004']})

    # ページの表示
    return direct_request_page_view(user_id, prop_id)

def direct_request_page_view(user_id ,prop_id):
    """
    URLから直接開く依頼ページ (非ログイン)
    """
    with DbClient() as db:

        # ユーザー情報の取得
        user_info = db.Users.find_one({'_id': user_id})
        if user_info is None:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        if not 'Currency' in user_info:
            user_info['Currency'] = 'JPY'

        # 言語指定の更新
        if 'Language' in user_info:
            web_util.set_cookie('lang', user_info['Language'])
        
        # 表示言語の取得
        lang = web_util.get_ui_texts()

        # 権利情報の取得
        prop_info = db.Properties.find_one({'_id': prop_id, 'User': user_id})
        if prop_info is None:
            return web_util.apply_template('direct_msg', doc={'Message': lang['Error']['E10001']})

        # 依頼可能か否かを判定
        requestable, reason, _, _ = common_util.is_requestable_no_db(prop_info)

        prop_info['IsRequestable'] = requestable
        prop_info['NotOpened'] = False
        if not requestable:
            prop_info['NotRequestableReason'] = reason
            if reason == "TooEarly":
                prop_info['NotOpened'] = True

        if requestable:
            # 依頼情報を生成
            cart = {'Years': 1}
            if prop_info['Law'] == 'Trademark':
                if prop_info['PaidYears'] == 5:
                    cart['Years'] = 5
                else:
                    cart['Years'] = 10
            # 追納期限の計算
            if not 'NextProcedureLastLimit' in prop_info:
                prop_info['NextProcedureLastLimit'] = common_util.add_months(prop_info['NextProcedureLimit'], 6)
        else:
            cart = None

        # ユーザー情報をリセット
        user_info_bk = user_info
        user_info = {
            '_id': user_info_bk['_id'],
            'MailAddress': user_info_bk['MailAddress'],
        }

        # 権利情報に紐づけられたユーザー名を取得
        if 'UserName' in prop_info:
            user_info['UserName'] = prop_info['UserName']
            if 'UserOrganization' in prop_info:
                user_info['Organization'] = prop_info['UserOrganization']
        else:
            # 過去に依頼された際のユーザー名を取得
            reqs = db.Requests.find({
                'User': user_id,
                'Properties': {'$elemMatch': {
                    'Property': prop_id,
                }},
                'UserName': {'$exists': True},
            }, {
                'UserName': 1,
                'UserOrganization': 1,
                'RequestedTime': 1,
            })
            reqs = sorted(list(reqs), key=lambda x: x['RequestedTime'], reverse=True)
            if len(reqs) > 0:
                user_info['UserName'] = reqs[0]['UserName']
                if 'UserOrganization' in reqs[0]:
                    user_info['Organization'] = reqs[0]['UserOrganization']
        # 他の情報から取得できない場合はユーザーの登録情報を用いる
        if not 'UserName' in user_info and 'Name' in user_info_bk:
            user_info['UserName'] = user_info_bk['Name']
            if 'Organization' in user_info_bk:
                user_info['Organization'] = user_info_bk['Organization']

        # 確認画面を生成
        return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info=user_info)

@app.get('/d/prop')
def direct_property_page():
    """
    URLから直接開く権利詳細のページ (非ログイン)
    """
    # IDの取得
    user_id, prop_id = get_direct_parameters()
    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    with DbClient() as db:

        # ユーザー情報の取得
        user_info = db.Users.find_one({'_id': user_id})
        if user_info is None:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        if not 'Currency' in user_info:
            user_info['Currency'] = 'JPY'

        # 言語指定の更新
        if 'Language' in user_info:
            web_util.set_cookie('lang', user_info['Language'])
        
        # 表示言語の取得
        lang = web_util.get_ui_texts()

        # 権利情報の取得（１）
        prop_info = db.Properties.find_one({
            '_id': prop_id,
            'Ignored': {'$exists': False},
        }, {'User':1})

        # ユーザーのチェック
        if prop_info is None or prop_info['User'] != user_id:
            return web_util.apply_template('direct_msg', doc={'Message': lang['Error']['E10001']})

        # 権利情報の取得（２）
        prop_info = get_prop_info(prop_id, date_to_str=False)

        # ユーザー名の付加
        prop_info['d_user_name'] = user_info['Name']

        # 不正なリクエスト
        return web_util.apply_template('direct_prop', doc=prop_info)

@app.get('/d/silent')
def direct_silent_page():
    """
    URLから直接開く通知停止のページ (非ログイン)
    """
    # IDの取得
    user_id, prop_id = get_direct_parameters()
    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    with DbClient() as db:

        # ユーザー情報の取得
        user_info = db.Users.find_one({'_id': user_id})
        if user_info is None:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        if not 'Currency' in user_info:
            user_info['Currency'] = 'JPY'

        # 言語指定の更新
        if 'Language' in user_info:
            web_util.set_cookie('lang', user_info['Language'])
        
        # 表示言語の取得
        lang = web_util.get_ui_texts()

        # 権利情報の取得
        prop_info = db.Properties.find_one({
            '_id': prop_id,
            'Ignored': {'$exists': False},
        })

        # ユーザーのチェック
        if prop_info is None or prop_info['User'] != user_id:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        # 法域名
        prop_info['LawName'] = lang['Law'][prop_info['Law']]

        # 権利番号
        prop_info['RegistrationNumber'] = lang.format_reg_number(prop_info['Country'], prop_info['Law'], prop_info['RegistrationNumber'])

        # 権利者名
        if 'Holders' in prop_info:
            tmp = [x['Name'] for x in prop_info['Holders'] if 'Name' in x]
            if len(tmp) > 0:
                prop_info['HolderNames'] = ', '.join(tmp)

        # 更新後メッセージ
        prop_info['d_user_name'] = user_info['Name']

    # キーの暗号化
    prop_info['key'] = security.encrypt_dict({'userId': str(user_id), 'propId': str(prop_id)})

    # ページの生成
    return web_util.apply_template('direct_cancel_pre', doc=prop_info)

@app.post('/d/silent')
def direct_silent_page_post():
    """
    URLから直接開く通知停止のページ (非ログイン)
    """
    # IDの取得
    posted = web_util.get_posted_data()

    if not 'key' in posted:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})
    
    try:
        keys = security.decrypt_dict(posted['key'])
        user_id = ObjectId(keys['userId'])
        prop_id = ObjectId(keys['propId'])
    except:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    # 放棄処理
    result, message, prop_info = silent_notification(prop_id, user_id)

    # 放棄を取り消すリンク
    prop_info['CancelLink'] = direct_link.get_link('/d/cancel_silent', str(user_id), str(prop_id))

    # 結果判定
    if result:
        # 成功
        return web_util.apply_template('direct_cancel', doc=prop_info)
    else:
        # 失敗
        return web_util.apply_template('direct_msg', doc={'Message': message})

def silent_notification(prop_id, user_id):
    """
    通知を無効にする
    """
    with DbClient() as db:

        # ユーザー情報の取得
        user_info = db.Users.find_one({'_id': user_id})
        if user_info is None:
            return False, language.get_dictionary()['Error']['E10001'], None

        if not 'Currency' in user_info:
            user_info['Currency'] = 'JPY'

        # 言語指定の更新
        if 'Language' in user_info:
            web_util.set_cookie('lang', user_info['Language'])
        
        # 表示言語の取得
        lang = web_util.get_ui_texts()

        # 権利情報の取得
        prop_info = db.Properties.find_one({
            '_id': prop_id,
            'Ignored': {'$exists': False},
        })

        # ユーザーのチェック
        if prop_info is None or prop_info['User'] != user_id:
            return False, lang['Error']['E10001'], None

        # 更新
        res = db.Properties.update_one(
            {'_id': prop_info['_id'],},
            {'$set': {'Silent': True, 'SilentTime': datetime.now(), }}
        )

        if res.matched_count < 1:
            return False, lang['Error']['E10001'], None

        # 法域名
        prop_info['LawName'] = lang['Law'][prop_info['Law']]

        # 権利番号
        prop_info['RegistrationNumber'] = lang.format_reg_number(prop_info['Country'], prop_info['Law'], prop_info['RegistrationNumber'])

        # 権利者名
        if 'Holders' in prop_info:
            tmp = [x['Name'] for x in prop_info['Holders'] if 'Name' in x]
            if len(tmp) > 0:
                prop_info['HolderNames'] = ', '.join(tmp)

        # 更新後メッセージ
        prop_info['Message'] = lang['Pages']['Property']['TEXT000011']
        prop_info['d_user_name'] = user_info['Name']

        # メール通知
        mail_subject = lang['Mail']['MAIL0005']['Subject']
        mail_body = io.StringIO()

        # メールの前段
        mail_body.write('\n')
        if 'UserName' in prop_info:
            if 'UserOrganization' in prop_info:
                mail_body.write(prop_info['UserOrganization'])
                mail_body.write('\n')
            user_name = prop_info['UserName']
        else:
            if 'Organization' in user_info:
                mail_body.write(user_info['Organization'])
                mail_body.write('\n')
            user_name = user_info['Name']
        mail_body.write(lang['Mail']['MAIL0005']['TEXT000001'].format(user_name))
        mail_body.write('\n\n')
        mail_body.write(lang['Mail']['MAIL0005']['TEXT000002'])
        mail_body.write('\n')
        mail_body.write(direct_link.get_link('/d/cancel_silent', str(user_id), str(prop_id)))
        mail_body.write('\n\n')

        # 権利情報の表示
        items = []

        # 登録番号
        items.append([
            lang['Pages']['Property']['TEXT000161'],
            prop_info['RegistrationNumber'],
        ])

        # 権利者
        items.append([
            lang['Pages']['Property']['TEXT000162'],
            prop_info['HolderNames'],
        ])

        # 名称
        items.append([
            lang['Pages']['Property']['TEXT000163'],
            '%s (%s)' % (prop_info['Subject'], prop_info['LawName']),
        ])

        # 次回期限
        items.append([
            lang['Pages']['Property']['TEXT000164'],
            lang.format_date(prop_info['NextProcedureLimit']),
        ])

        # 見出しの幅を統一してメール本文に掲載
        w = max([common_util.text_width(x[0]) for x in items])
        for item in items:
            # 見出しの幅を統一する
            x = w - common_util.text_width(item[0])
            s = item[0]
            if x > 0:
                s += "　" * int(x)
            mail_body.write('%s  %s\n' % (s, item[1],))

        # メールの後段
        mail_body.write(lang.mail_footer('0001'))

        # メールの送信
        to_addr, cc_addr, bcc_addr = db.get_mail_addresses(user_id)

        mail.send_mail(
            mail_subject,
            mail_body.getvalue(),
            to=to_addr, cc=cc_addr, bcc=bcc_addr,
        )

    # 成功
    return True, '', prop_info

@app.get('/d/cancel_silent')
def direct_cancel_silent_page():
    """
    URLから直接開く通知停止のキャンセルページ (非ログイン)
    """
    # IDの取得
    user_id, prop_id = get_direct_parameters()
    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    with DbClient() as db:

        # ユーザー情報の取得
        user_info = db.Users.find_one({'_id': user_id})
        if user_info is None:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        # 言語指定の更新
        if 'Language' in user_info:
            web_util.set_cookie('lang', user_info['Language'])
        
        # 表示言語の取得
        lang = web_util.get_ui_texts()

        # 権利情報の取得
        prop_info = db.Properties.find_one({
            '_id': prop_id,
            'Ignored': {'$exists': False},
        })

        # ユーザーのチェック
        if prop_info is None or prop_info['User'] != user_id:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        # 更新
        res = db.Properties.update_one(
            {'_id': prop_info['_id'],},
            {'$unset': {'Silent': "", 'SilentTime': "", }}
        )

        if res.matched_count < 1:
            return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

        # 法域名
        prop_info['LawName'] = lang['Law'][prop_info['Law']]

        # 権利番号
        prop_info['RegistrationNumber'] = lang.format_reg_number(prop_info['Country'], prop_info['Law'], prop_info['RegistrationNumber'])

        # 権利者名
        if 'Holders' in prop_info:
            tmp = [x['Name'] for x in prop_info['Holders'] if 'Name' in x]
            if len(tmp) > 0:
                prop_info['HolderNames'] = ', '.join(tmp)

        # 更新後メッセージ
        prop_info['d_user_name'] = user_info['Name']

        # メール通知
        mail_subject = lang['Mail']['MAIL0007']['Subject']
        mail_body = io.StringIO()

        # メールの前段
        mail_body.write('\n')
        if 'UserName' in prop_info:
            if 'UserOrganization' in prop_info:
                mail_body.write(prop_info['UserOrganization'])
                mail_body.write('\n')
            user_name = prop_info['UserName']
        else:
            if 'Organization' in user_info:
                mail_body.write(user_info['Organization'])
                mail_body.write('\n')
            user_name = user_info['Name']
        mail_body.write(lang['Mail']['MAIL0007']['TEXT000001'].format(user_name))
        mail_body.write('\n\n')
        mail_body.write(lang['Mail']['MAIL0007']['TEXT000002'])
        mail_body.write('\n\n')

        # 権利情報の表示
        items = []

        # 登録番号
        items.append([
            lang['Pages']['Property']['TEXT000161'],
            prop_info['RegistrationNumber'],
        ])

        # 権利者
        items.append([
            lang['Pages']['Property']['TEXT000162'],
            prop_info['HolderNames'],
        ])

        # 名称
        items.append([
            lang['Pages']['Property']['TEXT000163'],
            '%s (%s)' % (prop_info['Subject'], prop_info['LawName']),
        ])

        # 次回期限
        items.append([
            lang['Pages']['Property']['TEXT000164'],
            lang.format_date(prop_info['NextProcedureLimit']),
        ])

        # 見出しの幅を統一してメール本文に掲載
        w = max([common_util.text_width(x[0]) for x in items])
        for item in items:
            # 見出しの幅を統一する
            x = w - common_util.text_width(item[0])
            s = item[0]
            if x > 0:
                s += "　" * int(x)
            mail_body.write('%s  %s\n' % (s, item[1],))

        # メールの後段
        mail_body.write(lang.mail_footer('0001'))

        # メールの送信
        to_addr, cc_addr, bcc_addr = db.get_mail_addresses(user_id)

        mail.send_mail(
            mail_subject,
            mail_body.getvalue(),
            to=to_addr, cc=cc_addr, bcc=bcc_addr,
        )

    # 成功
    return web_util.apply_template('direct_cancel_cancel', doc=prop_info)

@app.get('/reqs')
@auth.require()
@auth.client_only()
def requests_page_default():
    """
    依頼一覧ページ
    """
    return requests_page_index(1)

@app.route('/reqs/<page:int>')
@auth.require()
@auth.client_only()
def requests_page_index(page):
    """
    依頼一覧ページ
    """
    # 言語設定
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # クエリーの構築
        # ※同一グループの他のユーザー分も表示する
        query = {
            '$and':[
                {'User': {'$in': common_util.get_group_user_ids(db, auth.get_account_id())}},
                {'Ignored': {'$exists': False}},
            ]
        }

        # クエリーの実行
        reqs = db.Requests.find(query, {'_id':1, 'RequestNumber':1})
        reqs = list(reqs)

    # 並べ替え
    reqs = sorted(reqs, key=lambda x: x['RequestNumber'], reverse=True)

    # ページング処理
    result, p_max, page = web_util.paging(reqs, 30, page)

    # 詳細データに置き換え
    result = [get_request_info(req['_id']) for req in result]

    doc = {}

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/reqs'
    }

    # リストの設定
    doc['Ids'] = [{'Id': x['_id'], 'Props': len(x['Properties'])} for x in result]
    doc['Requests'] = [json.dumps(web_util.adjust_to_json(x)) for x in result]

    # ページの生成
    return web_util.apply_template('user_reqs', doc=doc)

@app.post('/reqs/api/get')
@auth.require_ajax()
@web_util.local_page()
@auth.client_only()
@web_util.json_safe()
def requests_api_detail():
    """
    Ajax: 依頼の詳細を取得する
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['Id'])

    # 情報を取得する
    return get_request_info(id)

def get_request_info(id):
    """
    依頼の詳細を取得する
    """
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 通貨設定の取得
        currencies = common_util.get_currencies(db)

        # 依頼の取得
        req = db.Requests.find_one(
            {'_id': id},
            {
                'RequestNumber': 1,
                'RequestedTime': 1,
                'TotalAmount': 1,
                'Amounts': 1,
                'ExchangedAmounts': 1,
                'SmallAmounts': 1,
                'Currency': 1,
                'User': 1,
                'Properties.Property': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Years': 1,
                'Properties.PaidYears': 1,
                'Properties.NumberOfClaims': 1,
                'Properties.Classes': 1,
                'Properties.OriginalClasses': 1,
                'Properties.FeeList': 1,
                'Properties.CanceledTime': 1,
                'Properties.CompletedTime': 1,
                'Invoice.Date': 1,
                'RequireEstimation': 1,
                'EstimatedTime': 1,
                'CanceledTime': 1,
                'CompletedTime': 1,
            }
        )

        if req is None:
            abort(404)

        # データの補正
        req['Id'] = req['_id']

        if not 'RequireEstimation' in req:
            req['RequireEstimation'] = False

        # 金額の書式整形
        if 'Currency' in req:
            req['CurrencyLocal'] = lang.local_currency(req['Currency'])
        if 'TotalAmount' in req:
            req['TotalAmountText'] = currencies[req['Currency']]['Format'].format(req['TotalAmount'])
        if 'Amounts' in req:
            req['AmountsText'] = {}
            for key in req['Amounts'].keys():
                req['AmountsText'][key] = currencies[key]['Format'].format(req['Amounts'][key])
        if 'ExchangedAmounts' in req:
            req['ExchangedAmountsText'] = {}
            for key in req['ExchangedAmounts'].keys():
                req['ExchangedAmountsText'][key] = currencies[req['Currency']]['Format'].format(req['ExchangedAmounts'][key])
        if 'SmallAmounts' in req:
            req['SmallAmountsText'] = {}
            req['ExchangedSmallAmountsText'] = {}
            req['Price'] = []
            for cur in req['SmallAmounts'].keys():
                req['SmallAmountsText'][cur] = {}
                req['ExchangedSmallAmountsText'][cur] = {}
                for kind in ('Office', 'Agent', 'Tax', 'SourceWithholdingTax',):
                    if not kind in req['SmallAmounts'][cur]:
                        continue
                    for tax in req['SmallAmounts'][cur][kind].keys():
                        # 名目のテキスト
                        kind_title = '-'
                        if kind == 'Office':
                            kind_title = lang['Pages']['Request']['TEXT000023']
                        elif kind == 'Agent':
                            kind_title = lang['Pages']['Request']['TEXT000024']
                        elif kind == 'Tax':
                            kind_title = lang['Pages']['Request']['TEXT000132']
                        elif kind == 'SourceWithholdingTax':
                            kind_title = lang['Pages']['Request']['TEXT000063']
                        req['Price'].append({
                            'Title': kind_title,
                            'PriceText': currencies[cur]['Format'].format(req['SmallAmounts'][cur][kind][tax][0]),
                            'Currency': cur,
                            'CurrencyLocal': lang.local_currency(cur),
                            'Exchanged': currencies[req['Currency']]['Format'].format(req['SmallAmounts'][cur][kind][tax][1]),
                        })
                    v1 = sum([req['SmallAmounts'][cur][kind][tax][0] for tax in req['SmallAmounts'][cur][kind].keys()])
                    v2 = sum([req['SmallAmounts'][cur][kind][tax][1] for tax in req['SmallAmounts'][cur][kind].keys()])
                    req['SmallAmountsText'][cur][kind] = currencies[cur]['Format'].format(v1)
                    req['ExchangedSmallAmountsText'][cur][kind] = currencies[req['Currency']]['Format'].format(v2)
            del req['SmallAmounts']

        # 権利情報の付与
        for i in range(len(req['Properties'])):

            prop = db.Properties.find_one({
                '_id': req['Properties'][i]['Property']
            })

            req['Properties'][i]['Country'] = prop['Country']
            if prop['Country'] != 'UNK':
                req['Properties'][i]['CountryDescription'] = lang['Country'][prop['Country']]
            else:
                req['Properties'][i]['CountryDescription'] = prop['CountryDescription']
            req['Properties'][i]['Law'] = prop['Law']
            req['Properties'][i]['Law'] = prop['Law']
            req['Properties'][i]['LawName'] = lang['Law'][prop['Law']]
            req['Properties'][i]['RegistrationNumber'] = prop['RegistrationNumber']
            if 'Subject' in prop:
                req['Properties'][i]['Subject'] = prop['Subject']

            # 料金の再集計
            if 'FeeList' in req['Properties'][i]:
                req['Properties'][i]['OfficialFee'], req['Properties'][i]['OfficialFeeCurrency'], _ = total_fee_list(req['Properties'][i]['FeeList'], 'Office')
                req['Properties'][i]['AgentFee'], req['Properties'][i]['AgentFeeCurrency'], _ = total_fee_list(req['Properties'][i]['FeeList'], 'Agent')
                if req['Properties'][i]['OfficialFeeCurrency'] == req['Properties'][i]['AgentFeeCurrency']:
                    t = req['Properties'][i]['OfficialFee'] + req['Properties'][i]['AgentFee']
                else:
                    t, _, _ = total_fee_list(req['Properties'][i]['FeeList'], 'Office', 'ExchangedFee')
                    t += req['Properties'][i]['AgentFee']
                req['Properties'][i]['TotalFee'] = t
                req['Properties'][i]['TotalFeeCurrency'] = req['Properties'][i]['AgentFeeCurrency']

                req['Properties'][i]['OfficialFeeCurrencyLocal'] = lang.local_currency(req['Properties'][i]['OfficialFeeCurrency'])
                req['Properties'][i]['AgentFeeCurrencyLocal'] = lang.local_currency(req['Properties'][i]['AgentFeeCurrency'])
                req['Properties'][i]['TotalFeeCurrencyLocal'] = lang.local_currency(req['Properties'][i]['TotalFeeCurrency'])

                req['Properties'][i]['OfficialFeeText'] = currencies[req['Properties'][i]['OfficialFeeCurrency']]['Format'].format(req['Properties'][i]['OfficialFee'])
                req['Properties'][i]['AgentFeeText'] = currencies[req['Properties'][i]['AgentFeeCurrency']]['Format'].format(req['Properties'][i]['AgentFee'])
                req['Properties'][i]['TotalFeeText'] = currencies[req['Properties'][i]['TotalFeeCurrency']]['Format'].format(req['Properties'][i]['TotalFee'])

            # 手続内容の生成
            req['Properties'][i]['Procedures'] = common_util.list_procedures(req['Properties'][i], prop, lang)

            # ステータス
            if 'CanceledTime' in req['Properties'][i]:
                # キャンセル
                req['Properties'][i]['StatusMessage'] = lang['Pages']['Request']['TEXT000051']
            elif 'CompletedTime' in req['Properties'][i]:
                # 完了
                req['Properties'][i]['StatusMessage'] = lang['Pages']['Request']['TEXT000049']
            elif 'PaidTime' in req:
                # 対応中
                req['Properties'][i]['StatusMessage'] = lang['Pages']['Request']['TEXT000050']
            else:
                req['Properties'][i]['StatusMessage'] = lang['Pages']['Request']['TEXT000048']

        # 入金状況のメッセージ化
        status = [None, None, None,]
        if 'CanceledTime' in req:
            pass
        elif req['RequireEstimation']:
            if not 'EstimatedTime' in req:
                # 見積中
                status[0] = lang['Pages']['Request']['TEXT000047']
            elif not 'PaidTime' in req:
                # 入金確認
                status[0] = lang['Pages']['Request']['TEXT000048']
        elif not 'PaidTime' in req:
            # 入金確認
            status[0] = lang['Pages']['Request']['TEXT000048']

        # 進捗状況のメッセージ化
        comp_cnt = len([x for x in req['Properties'] if 'CompletedTime' in x and not 'CanceledTime' in x])
        all_cnt = len([x for x in req['Properties'] if not 'CanceledTime' in x])
        if comp_cnt == all_cnt and all_cnt > 0:
            # 完了
            status[1] = lang['Pages']['Request']['TEXT000049']
        elif 'PaidTime' in req and all_cnt > 0:
            # 対応中
            status[1] = lang['Pages']['Request']['TEXT000050']

        # キャンセル状態のメッセージ化
        cancel_cnt = len([x for x in req['Properties'] if 'CanceledTime' in x])
        all_cnt = len(req['Properties'])
        if cancel_cnt == all_cnt:
            # すべてキャンセル
            status[2] = lang['Pages']['Request']['TEXT000051']
        elif cancel_cnt > 0:
            # 一部キャンセル
            status[2] = lang['Pages']['Request']['TEXT000052']

        # ステータスメッセージ化
        req['StatusMessage'] = ','.join([x for x in status if not x is None])

        # 請求書の有無
        if 'Invoice' in req and len(req['Invoice']) > 0:
            req['HasInvoice'] = True

    # 取得した情報を返す
    return req

@app.route('/reqs/api/invoice/<id>')
@web_util.local_page()
@auth.require()
@auth.client_only()
def download_invoice(id):
    """
    請求書のダウンロード
    """
    id = ObjectId(id)

    with DbClient() as db:

        req = db.Requests.find_one(
            {'_id': id, 'User': auth.get_account_id()},
            {'RequestNumber':1, 'Invoice':1}
        )

        if len(req['Invoice']) < 1:
            abort(404)

        data = req['Invoice'][-1]['File']
        file_name = 'invoice_{}.pdf'.format(req['RequestNumber'])

    return web_util.push_file(data, file_name, content_type='application/pdf')

@app.get('/reqs/api/pp/1/<id>')
@auth.require()
@auth.client_only()
def api_papers_delegation(id):
    """
    委任状のダウンロード
    """
    id = ObjectId(id)
    # 生成した委任状(docx)を返す
    return web_util.download_delegation(id, user_id=auth.get_account_id())

@app.get('/reqs/api/pp/2/<id>')
@auth.require()
@auth.client_only()
def api_papers_abandonment(id):
    """
    一部放棄書のダウンロード
    """
    id = ObjectId(id)
    # 生成した委任状(docx)を返す
    return web_util.download_abandonment(id)

@app.get('/d/req/invoice/')
def direct_download_invoice():
    """
    請求書のダウンロード
    """
    # パラメーターの取得
    user_id, req_id = get_direct_parameters()

    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    with DbClient() as db:

        req = db.Requests.find_one(
            {'_id': req_id, 'User': user_id},
            {'RequestNumber':1, 'Invoice':1}
        )

        if len(req['Invoice']) < 1:
            abort(404)

        data = req['Invoice'][-1]['File']
        file_name = 'invoice_{}.pdf'.format(req['RequestNumber'])

    return web_util.push_file(data, file_name, content_type='application/pdf')

@app.get('/d/req/pp/1/')
def direct_download_delegation():
    """
    委任状のダウンロード
    """
    # パラメーターの取得
    user_id, req_id = get_direct_parameters()

    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    # 生成した委任状(docx)を返す
    return web_util.download_delegation(req_id, user_id=user_id)

@app.get('/d/req/pp/2/')
def direct_download_abandonment():
    """
    一部放棄書のダウンロード
    """
    # パラメーターの取得
    user_id, req_id = get_direct_parameters()

    if user_id is None:
        return web_util.apply_template('direct_msg', doc={'Message': language.get_dictionary()['Error']['E10001']})

    # 生成した委任状(docx)を返す
    return web_util.download_abandonment(req_id, user_id=user_id)

@app.get('/e/req/')
def guest_req_1():
    """
    ゲストの依頼（１）
    """
    return web_util.apply_template('easy_req_1')

@app.post('/e/req/')
def guest_req_2():
    """
    ゲストの依頼（１）
    """
    posted = web_util.get_posted_data()
    msg = []
    lang = web_util.get_ui_texts()

    # パラメーターのチェック
    if not 'RegistrationNumber' in posted:
        msg.append(lang['Pages']['Request']['TEXT000088'])
        posted['Messages'] = msg
        return web_util.apply_template('easy_req_1', doc=posted)

    # パラメーターの補完
    posted['Country'] = 'JP'
    if not 'Law' in posted or not posted['Law'] in ('Patent', 'Utility', 'Design', 'Trademark',):
        posted['Law'] = 'Patent'

    # 登録番号の桁数チェック
    if len(posted['RegistrationNumber']) > 7:
        msg.append(lang['Pages']['Request']['TEXT000118'])
        posted['Messages'] = msg
        return web_util.apply_template('easy_req_1', doc=posted)
    if len(posted['RegistrationNumber']) < (7 if posted['Law'] != 'Trademark' else 6):
        msg.append(lang['Pages']['Request']['TEXT000118'])
        posted['Messages'] = msg
        return web_util.apply_template('easy_req_1', doc=posted)

    # 登録番号の正規化
    posted['RegistrationNumber'] = common_util.regularize_reg_num('JP', posted['Law'], posted['RegistrationNumber'])

    # ログ
    logger.info('guest mode: start entry: %s-%s', posted['Law'], posted['RegistrationNumber'])

    user_id = None

    # 前ページからユーザーIDが渡っているか確認
    if 'udata' in posted:
        udata = security.decrypt_dict(posted['udata'])
        if 'userId' in udata:
            user_id = ObjectId(udata['userId'])
    # ログイン判定
    if user_id is None:
        user_id = auth.get_account_id()

    # 権利キー
    prop_id = None

    if not user_id is None:

        with DbClient() as db:

            # ユーザーに該当する権利があるか調べる
            prop_info_db = db.Properties.find_one(
                {
                    'Country': 'JP',
                    'Law': posted['Law'],
                    'RegistrationNumber': posted['RegistrationNumber'],
                    'User': user_id,
                    'Ignored': {'$exists': False},
                }
            )

            if not prop_info_db is None:
                prop_id = prop_info_db['_id']

    # 特許庁DBの照会
    prop_info = web_util.get_property_info_from_jpp(posted, lang)

    if prop_info is None or not prop_info['Result']:
        if not prop_info is None and 'Message' in prop_info:
            msg.append(prop_info['Message'])
        else:
            msg.append(lang['Pages']['Request']['TEXT000089'])
        posted['Messages'] = msg
        return web_util.apply_template('easy_req_1', doc=posted)

    # 権利情報を抽出
    prop_info = prop_info['Data']

    # 依頼可能か否かを判定
    requestable, reason, _, _ = common_util.is_requestable_no_db(prop_info)

    prop_info['IsRequestable'] = requestable
    prop_info['NotOpened'] = False
    if not requestable:
        prop_info['NotRequestableReason'] = reason
        if reason == "TooEarly":
            prop_info['NotOpened'] = True

    if requestable:
        # 依頼情報を生成
        cart = {'Years': 1}
        if prop_info['Law'] == 'Trademark':
            if prop_info['PaidYears'] == 5:
                cart['Years'] = 5
            else:
                cart['Years'] = 10
    else:
        cart = None

    # 確認画面を生成
    return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info={})

def guest_req_3(prop_info, cart, lang, user_id=None, user_info={}, messages=None):
    """
    ゲストモードでの確認画面を生成
    """
    if messages is None:
        messages = []

    # カート情報をアップデート
    cart = update_cart(prop_info, cart)

    target = prop_info
    if not cart is None:
        target['Cart'] = cart
    targets = [target,]

    with DbClient() as db:

        # 通貨設定の取得
        currencies = common_util.get_currencies(db)

        # ユーザー情報の取得
        if not user_id is None and (user_info is None or len(user_info) == 0):
            # 権利に設定されたユーザーを調べる
            props = db.Properties.find({
                'User': user_id,
                'Country': target['Country'],
                'Law': target['Law'],
                'RegistrationNumber': target['RegistrationNumber'],
                'Ignored': {'$exists': False,},
            }, {'_id': 1, 'UserName': 1, 'UserOrganization': 1})
            props = list(props)
            if len(props) > 0:
                if 'UserName' in props[0]:
                    user_info = {'UserName': props[0]['UserName'],}
                    if 'UserOrganization' in props[0]:
                        user_info['Organization'] = props[0]['UserOrganization']
                else:
                    # 過去、同一ユーザーで同一権利について依頼された履歴を調べる
                    prop_ids = [x['_id'] for x in props]
                    if len(prop_ids) > 0:
                        reqs = db.Requests.find({
                            'User': user_id,
                            'Properties': {'$elemMatch': {
                                'Property': {'$in': prop_ids,},
                            }},
                            'UserName': {'$exists': True},
                        }, {
                            'UserName': 1,
                            'UserOrganization': 1,
                            'RequestedTime': 1,
                        })
                        reqs = sorted(list(reqs), key=lambda x: x['RequestedTime'], reverse=True)
                        if len(reqs) > 0:
                            user_info = {'UserName': reqs[0]['UserName'],}
                            if 'UserOrganization' in reqs[0]:
                                user_info['Organization'] = reqs[0]['UserOrganization']                
            tmp = db.Users.find_one(
                {'_id': user_id},
                {
                    'Organization': 1,
                    'Name': 1,
                    'MailAddress': 1,
                }
            )
            if user_info is None:
                user_info = {}
            if not tmp is None:
                if 'Name' in tmp and not 'UserName' in user_info:
                    user_info['UserName'] = tmp['Name']
                if 'Organization' in tmp and not 'Organization' in user_info:
                    user_info['Organization'] = tmp['Organization']
                if 'MailAddress' in tmp:
                    user_info['MailAddress'] = tmp['MailAddress']

            # 初期状態ではユーザー情報は空 (2023.10.25)
            user_info = {}

    if not cart is None:

        # 明細を集計
        targets, totals, taxs, gensen, cur_rates, has_additional = total_fees_for_request(targets, currencies, 'JPY')

        # 表示・登録用のオブジェクトに加工する
        req_obj = create_request_object(
            target['Cart']['Agent'], "Request", targets, totals, taxs, gensen,
            cur_rates, 'JPY', currencies,
            lang, has_additional
        )

        # 減免対象候補
        if target['Country'] == 'JP' and target['Law'] == 'Patent':
            candidates = []
            if target['PaidYears'] > 10:
                # 11年目以降は減免なし
                pass
            elif 'ExamClaimedDate' in target and target['ExamClaimedDate'] >= datetime(2019, 4, 1):
                # 権利者名から適用される減免の区分を判定
                if 'Holders' in target:
                    tmp = [x['Name'] for x in target['Holders'] if 'Name' in x]
                    if len(tmp) > 0:
                        tmp = [common_util.check_jp_genmen(x) for x in tmp]
                        # 異なる区分をもつ複数権利者がいる場合は減免を受け付けない
                        if not common_util.check_more_two(tmp) and not tmp[0] is None:
                            candidates.append({
                                'Kind': tmp[0],
                                'Text': lang['JpGenmen'][tmp[0]],
                            })
            elif 'ExamClaimedDate' in target and target['ExamClaimedDate'] < datetime(2014, 4, 1):
                # Nothing
                pass
            else:
                candidates.append({
                    'Kind': 'H25_98_66',
                    'Text': lang['Pages']['Property']['TEXT000008'],
                })
            if len(candidates) > 0:
                req_obj['JpGenmenCandidates'] = candidates

        # 区分の削除可否
        if target['Country'] == 'JP' and target['Law'] == 'Trademark':
            if 'CanDeleteClass' in cart:
                target['CanDeleteClass'] = cart['CanDeleteClass']
            else:
                target['CanDeleteClass'] = True

    else:

        # 表示・登録用のオブジェクトに加工する
        req_obj = create_request_object(
            "0001", "Request", targets, {}, {}, {},
            {}, 'JPY', currencies,
            lang, False
        )

    # 権利情報を追加
    req_obj['pdata'] = security.encrypt_dict(prop_info)

    # ユーザー情報を付与
    if not user_info is None:
        for key in user_info.keys():
            req_obj[key] = user_info[key]

    # 依頼の可否
    req_obj['IsRequestable'] = (not cart is None)
    if not req_obj['IsRequestable']:
        if 'NotRequestableReason' in prop_info and not prop_info['NotOpened']:
            messages.append(lang['Pages']['Property']['NotRequestable'][prop_info['NotRequestableReason']])

    # メッセージの追加
    if not messages is None and len(messages) > 0:
        req_obj['Messages'] = messages

    # 納付期限と存続期間満了日のチェック
    req_obj['Less6Month'] = False
    if req_obj['IsRequestable']:
        if targets[0]['Law'] != 'Trademark' and 'NextProcedureLimit' in targets[0] and 'ExpirationDate' in targets[0]:
            npl = targets[0]['NextProcedureLimit']
            exp = targets[0]['ExpirationDate']
            if npl <= exp and common_util.add_months(npl, 6) > exp:
                req_obj['Less6Month'] = True

    # 整理番号
    if 'ManagementNumber' in prop_info:
        req_obj['ManagementNumber'] = prop_info['ManagementNumber']

    # ページを生成
    return web_util.apply_template('easy_req_2', doc=req_obj)

@app.post('/e/req/a/')
def guest_req_4():
    """
    ゲストモードで依頼登録処理等 (POST受付)
    """
    # 受信データの復元
    posted = web_util.get_posted_data()
    req_obj = security.decrypt_dict(posted['cdata'])
    targets = req_obj['Targets']
    target = targets[0]
    prop_info = security.decrypt_dict(posted['pdata'])
    user_id = None

    # ユーザーデータの構成
    user_info = {}
    for key in ('Organization', 'UserName', 'MailAddress',):
        if key in posted:
            user_info[key] = posted[key]

    # 整理番号
    if 'ManagementNumber' in posted and posted['ManagementNumber'] != '':
        prop_info['ManagementNumber'] = posted['ManagementNumber']
    elif 'ManagementNumber' in prop_info:
        del prop_info['ManagementNumber']

    # 表示言語の取得
    lang = web_util.get_ui_texts()

    # カートの復元
    if 'Cart' in req_obj['Targets'][0]:
        cart = req_obj['Targets'][0]['Cart']
        # 整理番号を反映するためにカートを再計算
        cart = update_cart(prop_info, cart)
    else:
        cart = None

    # 操作判定
    if posted['Action'].startswith('Years_'):

        # ★納付年分の増減処理★

        # パラメーターの分割
        p = posted['Action'].split('_')

        # 変更する方向の判定
        direction = -1 if p[1].lower() == 'minus' else 1

        if prop_info['Country'] == 'JP' and prop_info['Law'] == 'Trademark':
            direction *= 5

        # 更新
        if not cart is None:

            y = cart['Years'] + direction

            if y >= cart['MinYear'] and y <= cart['MaxYear']:
                cart['Years'] = y

        # ページを再生成
        return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info=user_info)

    elif posted['Action'].startswith('TmClass_'):

        # ★更新区分の変更処理★

        # パラメーターの分割
        p = posted['Action'].split('_')

        # 区分
        c = p[2].strip()

        # 操作の判定
        act = 'on' if p[1] == 'A' else 'off'

        # 更新
        if not cart is None:

            if not 'Classes' in cart:
                cart['Classes'] = prop_info['Classes']

            if act == 'off':

                # 区分の削除
                if len(cart['Classes']) > 1:
                    cart['Classes'] = [x for x in cart['Classes'] if x != c]

            else:

                # 区分の追加
                if c in prop_info['Classes'] and not c in cart['Classes']:
                    cart['Classes'].append(c)

        # ページを再生成
        return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info=user_info)

    elif posted['Action'].startswith('Discount_'):

        # ★減免区分の変更処理★

        # パラメーターの分割
        p = posted['Action'].split('_', 1)

        # 変更する方向の判定
        kind = p[1]

        # 更新
        if kind in ('10_4_i', '10_4_ro', '10_3_ro', 'H25_98_66',):
            prop_info['JpGenmen'] = kind
        elif 'JpGenmen' in prop_info:
            del prop_info['JpGenmen']

        # ページを再生成
        return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info=user_info)

    elif posted['Action'] == 'Back':

        # ★前ページに戻る★
        return web_util.apply_template('easy_req_1', doc={
            'Law': prop_info['Law'],
            'RegistrationNumber': prop_info['RegistrationNumber'],
        })

    elif posted['Action'] == 'Order':

        # ★依頼の確定処理★
        msg = []

        # ユーザー情報の確認
        if user_id is None:
            if not 'UserName' in user_info:
                msg.append(lang['Pages']['Request']['TEXT000095'])
            if not 'MailAddress' in user_info:
                msg.append(lang['Pages']['Request']['TEXT000096'])

        if len(msg) > 0:
            # ページを再生成
            return guest_req_3(prop_info, cart, lang, user_id=user_id, user_info=user_info, messages=msg)

        agent = req_obj['Agent']
        category = req_obj['Category']

        # 登録に必要な項目のみのターゲットリストに置き換える
        targets = clean_up_targets([target,])
        target = targets[0]

        with DbClient() as db:

            if user_id is None:

                # ゲストユーザーを登録する
                mail_address = user_info['MailAddress']

                user_id, _, _, user_email, _ = common_util.find_user_by_email(db, mail_address)
                if not user_id is None:
                    user_db = db.Users.find_one({'_id': user_id})
                else:
                    user_db = None

                if not user_db is None:

                    # 登録済みのメールアドレスの場合は、そのユーザーに関連付ける
                    user_id = user_db['_id']
                    #logger.info('requested in guest mode, but the accepted email is registered for existed user.(%s, %s)', mail_address, user_id)

                    # 仮登録のユーザーであれば、名前などを登録し直す
                    if not 'Name' in user_db:
                        if 'UserName' in user_info:
                            db.Users.update_one({'_id': user_db['_id']}, {'$set': {'Name': user_info['UserName']}})
                        if 'Organization' in user_info:
                            db.Users.update_one({'_id': user_db['_id']}, {'$set': {'Organization': user_info['Organization']}})
                        else:
                            db.Users.update_one({'_id': user_db['_id']}, {'$unset': {'Organization': ''}})

                else:

                    # 新規のメールアドレスの場合は、ユーザーを仮登録する
                    user_info_2 = {}
                    for key in ('UserName', 'Organization', 'MailAddress',):
                        if key in user_info:
                            if key == 'UserName':
                                user_info_2['Name'] = user_info[key]
                            else:
                                user_info_2[key] = user_info[key]
                    user_info_2['IsClient'] = True
                    res = db.Users.insert_one(user_info_2)
                    user_id = res.inserted_id
                    user_email = mail_address
                    logger.debug('the guest user (%s) is registered as a user (%s).', mail_address, user_id)

                targets[0]['User'] = user_id
            
            else:

                # 既存のユーザーに関連付ける
                user_db = db.Users.find_one({'_id': user_id})
                if user_db is None:
                    abort(500)

            # 権利情報の有無を確認
            prop_db = db.Properties.find_one({
                'Country': 'JP',
                'Law': prop_info['Law'],
                'RegistrationNumber': prop_info['RegistrationNumber'],
                'Ignored': {'$exists': False},
                'User': user_id,
            })

            # 権利を仮登録
            if prop_db is None:

                prop_info['User'] = user_id
                prop_info['RegisteredTime'] = datetime.now()
                if '_id' in prop_info:
                    del prop_info['_id']
                res = db.Properties.insert_one(prop_info)
                prop_info['_id'] = res.inserted_id
            
            else:

                # 既存の権利情報を更新
                q = {'$set': {}}
                for key in ('PaidYears', 'Claims', 'Classes','Holders','JpGenmen','ManagementNumber',):
                    if key in prop_info:
                        q['$set'][key] = prop_info[key]
                if len(q['$set']):
                    db.Properties.update_one(
                        {'_id': prop_db['_id']},
                        q
                    )
                prop_info['_id'] = prop_db['_id']

            # 権利のキーを設定
            targets[0]['Property'] = prop_info['_id']

            # 結果の表示用にユーザー情報を取得しておく
            user_db = db.Users.find_one({'_id': user_id})
            user_name = user_db['Name']
            if 'Organization' in user_db:
                user_org=user_db['Organization']
            else:
                user_org=None
            if 'UserName' in user_info:
                user_db['Name'] = user_info['UserName']
                user_name=user_info['UserName']
                if 'Organization' in user_info:
                    user_db['Organization'] = user_info['Organization']
                    user_org=user_info['Organization']
                else:
                    if 'Organization' in user_db:
                        del user_db['Organization']
                    user_org=None

        if user_email == mail_address:
            user_email = None
        else:
            user_email = mail_address

        # 依頼を登録する
        req_id, req_num, req_time, has_invoice, has_delegation, has_abandonment = register_request(agent, category, targets, req_obj, user_id=user_id, user_name=user_name, user_org=user_org, user_email=user_email)

        # 受付済のページを生成
        result_doc = {
            'RequestId': req_id,
            'RequestNumber': req_num,
            'RequestedTime': req_time,
            'HasInvoice': has_invoice,
            'NeedsDelegation': False,
            'NeedsAbandonment': False,
            'DirectParameter': urllib.parse.quote(security.encrypt('\t'.join([str(user_id), str(req_id)]))),
            'UserName': user_name,
        }
        if 'PayLimit' in req_obj:
            result_doc['PayLimit'] = req_obj['PayLimit']
            if 'PaidYears' in target and 'Classes' in target and 'OriginalClasses' in target:
                if target['PaidYears'] < 10 and len(target['Classes']) < len(target['OriginalClasses']):
                    result_doc['DeleteClassAlert'] = True
        if not user_org is None:
            result_doc['Organization'] = user_org
        return web_util.apply_template('easy_req_3', doc=result_doc)

    else:

        # 不正なリクエスト
        posted['Messages'] = [lang['Error']['E10001'],]
        return web_util.apply_template('easy_req_1', doc=posted)

@app.get('/kigen')
@auth.require()
@auth.client_only()
def kigen_page_default():
    """
    期限管理リスト
    """
    # 表示指定パラメーターの取得
    page, sort, dire = kigen_common.get_page_paramegers()

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
            {'User': {'$in': common_util.get_group_user_ids(db, auth.get_account_id())}},
        ]}

        # サポートする国・地域に制限
        query['$and'].append({'Country': {'$in': ['JP',]}})

        # 権利リストの取得
        props = []

        for info in db.Properties.find(query):

            # 表示用に編集
            prop = {'_id': str(info['_id'])}
            for key in ('Country', 'Law', 'RegistrationNumber', 'Subject', 'NextProcedureLimit', 'ManagementNumber',):
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

            # 通知制限
            if 'Silent' in info:
                prop['Silent'] = info['Silent']
                if 'SilentTime' in info:
                    prop['SilentTime'] = info['SilentTime']
            else:
                prop['Silent'] = False

            # その他情報の取得
            info2 = db.get_prop_info(info['_id'], lang=lang, date_to_str=False)

            # 情報の転記
            for key in ('Requestable', 'RequestWarning_Short', 'AdditionalPeriod', 'NextOfficialFee', 'CurrencyLocal',
                        'ApplyDiscount',):
                if key in info2:
                    prop[key] = info2[key]

            # 表示候補に追加
            props.append(prop)

    # 並べ替え
    props = kigen_common.sort_properties(props, sort, direction)

    # ページング処理
    doc = {}

    # 通常のページング
    props, p_max, page = web_util.paging(props, 500, page)

    doc['Page'] = {
        'Current': page,
        'Max': p_max,
        'Path': '/kigen',
    }
    doc['Props'] = props
    doc['Control'] = {
        'Sort': sort,
        'Direction': direction,
        'Mode': 'User',
    }

    # ページの生成
    return web_util.apply_template('staff_kigen', doc=doc)

@app.post('/kigen/api/reg')
@web_util.local_page()
@web_util.json_safe()
@auth.require()
@auth.client_only()
def kengen_page_reg():
    """
    権利を追加する
    """
    posted = web_util.get_posted_data()
    lang = web_util.get_ui_texts()
    with DbClient() as db:
        # ユーザー情報の取得
        user_id = auth.get_account_id()
        user_db = db.Users.find_one({
            '_id': user_id,
        })
        # ユーザー名のチェック
        userName = None
        userOrg = None
        if 'userName' in posted:
            userName = posted['userName']
        if 'userOrganization' in posted:
            userOrg = posted['userOrganization']
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
        # ユーザーの名前を更新（未設定の場合のみ）
        if not 'Name' in user_db:
            q = {'$set': {'Name': userName}}
            if not userOrg is None:
                q['$set']['Organization'] = userOrg
            else:
                q['$unset'] = {'Organization': ''}
            db.Users.update_one(
                {'_id': user_id},
                q
            )
        # 整理番号を設定
        if 'managementNumber' in posted:
            prop_info['ManagementNumber'] = posted['managementNumber']
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

@app.post('/kigen/api/mannum')
@web_util.local_page()
@web_util.json_safe()
@auth.require()
@auth.client_only()
def kengen_page_mannum():
    """
    整理番号を更新する
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['id'])
    manNum = None
    if 'managementNumber' in posted:
        manNum = posted['managementNumber']
    with DbClient() as db:
        # 更新クエリー
        if manNum is None:
            q = {'$unset': {'ManagementNumber': ''}}
        else:
            q = {'$set': {'ManagementNumber': manNum}}
        db.Properties.update_one(
            {'_id': id, 'User': auth.get_account_id(),},
            q
        )
    return {'result': True}

@app.post('/kigen/api/silent')
@web_util.local_page()
@web_util.json_safe()
@auth.require()
@auth.client_only()
def kengen_page_silent():
    """
    通知制限を更新する
    """
    posted = web_util.get_posted_data()
    id = ObjectId(posted['id'])
    stime = datetime.now()
    with DbClient() as db:
        # 現在の設定を取得
        prop = db.Properties.find_one({'_id': id}, {'Silent': 1, 'User': 1,})
        cur = False
        if not prop is None and 'Silent' in prop:
            cur = prop['Silent']
        # 反転
        cur = not cur
        # 更新クエリー
        if cur:
            silent_notification(prop['_id'], prop['User'])
            return {'result': True, 'silent': cur, 'silentDate': stime.strftime('%Y-%m-%d'), }
        else:
            q = {'$unset': {'Silent': '', 'SilentTime': '', }}
            db.Properties.update_one(
                {'_id': id, 'User': auth.get_account_id(),},
                q
            )
            return {'result': True, 'silent': cur, }
