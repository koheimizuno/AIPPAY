from bottle import run, request, response, redirect, abort, static_file
from bottle import TEMPLATE_PATH, jinja2_template as template
from bottle import BaseTemplate
from bottle import HTTPResponse
from bson.objectid import ObjectId
import base64
from datetime import datetime, timedelta, date
import re
import urllib.parse
import math
import html
import json
import requests
import logging
from pathlib import Path
import markdown
import mojimoji

from database import DbClient
import auth

import common_util
import security
import language
import html_minify
import patent_reference
import jp_calendar

logger = logging.getLogger(__name__)

def comma_currency(value):
    """
    数値（整数）をカンマ区切り表記にする
    """
    return '{:,.2f}'.format(value)

def truncate(text, length):
    """
    テキストを20文字で切る
    """
    if text is None:
        return None
    text = html.escape(text)
    if len(text) < length:
        return text
    else:
        return text[:length] + '&hellip;'

def date_format(d):
    """
    言語設定に合わせて日付を整形する
    """
    # 日付値でなければそのまま返す
    if not (isinstance(d, datetime) or isinstance(d, date)):
        return d

    # 言語の取得
    lang = get_language()

    # 言語ごとに整形
    return common_util.date_format(d, lang, markup=True)

def date_format_std(d):
    """
    日付を標準形式で整形する
    """
    # 日付値でなければそのまま返す
    if not (isinstance(d, datetime) or isinstance(d, date)):
        return d

    # 整形
    return d.strftime('%Y-%m-%d')

# Jnnja2にカスタムフィルターを追加する
BaseTemplate.settings.update({'filters': {
    'comma_currency': lambda content: comma_currency(content),
    'truncate10': lambda content: truncate(content, 10),
    'truncate20': lambda content: truncate(content, 20),
    'truncate30': lambda content: truncate(content, 30),
    'date_format': lambda content: date_format(content),
    'date_format_std': lambda content: date_format_std(content),
    'nl2br': lambda content: html.escape(content).replace('\n', '<br>')
}})

def apply_template(name, doc=None, info=None, alert=None, csrf_name=None):
    """
    Jinja2のテンプレート適用についてのユーティリティ
    """
    if doc is None:
        doc = {}

    # 言語指定
    doc['UI_LANG'] = get_language()

    # UI用の辞書をセットする
    doc['UI'] = get_ui_texts()

    # ログインフラグ
    doc['logged_in'] = False
    doc['user_name'] = 'Guest'

    with DbClient() as db:

        if auth.is_authenticated():

            doc['logged_in'] = True

            # ユーザー名
            user = db.Users.find_one({'_id': auth.get_account_id()})
            doc['user_name'] = user['Name'] if 'Name' in user else ''

            # 権限の取得と設定
            doc['is_client'] = user['IsClient'] if 'IsClient' in user else False
            doc['is_staff'] = user['IsStaff'] if 'IsStaff' in user else False
            doc['is_admin'] = user['IsAdmin'] if 'IsAdmin' in user else False

    # 通知の設定
    if info:
        if isinstance(info, list):
            info = '\n'.join([str(x).strip() for x in info])
        else:
            info = str(info).strip()
        if info != '':
            doc['information'] = info

    # 警告の設定
    if alert:
        if isinstance(alert, list):
            alert = '\n'.join([str(x).strip() for x in alert])
        else:
            alert = str(alert).strip()
        if info != '':
            doc['alert'] = alert

    # 今日の日付
    doc['Today'] = datetime.now()

    # CSRF対策トークン
    if csrf_name:
        token = security.get_csrf_token()
        doc['_csrf'] = token
        # セッションに保存
        sess = auth.get_session()
        sess['_csrf.' + csrf_name] = token
        sess.save()

    # テンプレートの適用
    return template(name, doc)
    return html_minify.minify(template(name, doc))

def save_in_cookie(prefix, d):
    """
    dictの内容をCookieに保存する
    """
    # dictに含まれないキーを削除する
    for key in get_cookie_keys(prefix):
        if not key in [prefix + x for x in d]:
            set_cookie(key, None)
    # 値を保存する
    for key in d:
        # list, dictはスキップする
        if isinstance(d[key], list) or isinstance(d[key], dict):
            continue
        if isinstance(d[key], datetime):
            set_cookie('%s%s' % (prefix, key), repr(d[key]))
        else:
            set_cookie('%s%s' % (prefix, key), d[key])

def load_from_cookie(prefix=''):
    """
    Cookieからdictを再現する
    """
    t = {}
    for key in get_cookie_keys(prefix):
        s = get_cookie(key)
        if re.match(r'datetime\.datetime\(.*\)', s):
            s = eval(re.sub(r'^datetime\.', '', s))
        t[key[len(prefix):]] = s
    return t

# Cookie を設定する
def set_cookie(name, value, expires=None):
    if value is None or value == '':
        # None が指定されたら expires を指定して消す
        response.set_cookie(name, '', expires=(datetime.now() - timedelta(days=1)))
        return
    elif not isinstance(value, str):
        # str 型に変換する
        value = str(value)
    # 期限
    if expires is None:
        expires = datetime.now() + timedelta(days=30)
    # 日本語のために base64 エンコードする
    value = base64.b64encode(value.encode('utf-8')).decode('us-ascii')
    # Cookie を設定する
    response.set_cookie(name, value, expires=expires, httponly=True, secure=(request.urlparts[0] == 'https'))
    request.cookies[name] = value

def get_cookie_keys(prefix=''):
    """
    指定したプリフィクスを持つ Cookie の名前を返す
    """
    return [x for x in request.cookies.keys() if x.startswith(prefix)]

# Cookie を取得する
def get_cookie(name):
    # 取得
    value = request.get_cookie(name)
    if value is None or value == '':
        return None
    # デコード (base64)
    return base64.b64decode(value.encode('us-ascii')).decode('utf-8')

def get_language():
    """
    現在設定されている言語を取得する
    """
    allowed = ('ja',)

    # ログイン情報から取得
    if auth.is_authenticated():
        with DbClient() as db:
            u = db.Users.find_one({'_id': auth.get_account_id()})
            if 'Language' in u and u['Language'] in allowed:
                return u['Language']

    # Cookieから取得
    lang = get_cookie('lang')
    if not lang is None and lang in allowed:
        return lang

    ## Accept-Languageから判別
    #try:
    #    lang = request.headers['Accept-Language']
    #except KeyError:
    #    lang = None

    #if not lang is None and lang != '':
    #    for m in re.finditer(r'([a-z]{2})(-?([A-Z]+))?\s*(,|;|$)', lang):
    #        if m.group(1) == 'zh' and m.group(3):
    #            x = '{}_{}'.format(m.group(1), m.group(3))
    #        else:
    #            x = m.group(1)
    #        if x in ('ja', 'zh_CN'):
    #            return x

    # 判別不能の場合は日本語
    return 'ja'

def get_ui_texts():
    """
    言語設定に従ってUIテキストの辞書を取得する
    """
    return language.get_dictionary(get_language())

# ファイルを送る
def push_file(data, name, content_type='application/octet-stream', content_disposition='attachment'):
    res = HTTPResponse(status=200, body=data)
    if name.lower().endswith('.docx') and content_type == 'application/octet-stream':
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    res.content_type = content_type
    res.set_header('Content-Length', str(len(data)))
    name = urllib.parse.quote(name)
    res.set_header('Content-Disposition', '%s;filename="%s";filename*=utf8''%s' % (content_disposition, name, name))
    return res

# ファイルをダウンロードする
def download_attachment(req_id, uuid):
    if not isinstance(req_id, ObjectId):
        req_id = ObjectId(req_id)
    with DbClient() as db:
        req = db.requests.find_one({'_id': req_id})
        if not 'attachments' in req:
            assert False
        for attachment in req['attachments']:
            if attachment['uuid'] == uuid:
                return push_file(attachment['data'], attachment['name'], content_type=attachment['content_type'])
    assert False

def get_posted_data(allow_multiline=[], csrf_name=None):
    """
    POSTデータをdict形式で取得する
    """
    ## CSRF検証
    #if csrf_name:
    #    if not '_csrf' in request.forms.keys() or request.forms._csrf is None:
    #        logger.warning('CSRF request is detected. [1]')
    #        abort(400, 'csrf validation error.')
    #    sess = auth.get_session()
    #    token_name = '_csrf.' + csrf_name
    #    if not token_name in sess:
    #        logger.warning('CSRF request is detected. [2]')
    #        abort(400, 'csrf validation error.')
    #    if request.forms._csrf != sess[token_name]:
    #        logger.warning('CSRF request is detected. [3]')
    #        abort(400, 'csrf validation error.')

    # 受信データの取得
    post = {}

    if allow_multiline:
        if not isinstance(allow_multiline, list):
            allow_multiline = [allow_multiline,]
    else:
        allow_multiline = []

    for k in request.forms.keys():
        if k == '_csrf':
            continue
        if k == '':
            continue
        if re.search(r'[^0-9a-zA-Z_\-]', k):
            continue
        s = eval('request.forms.%s' % k)
        s = s.strip()
        if s and s != '':
            post[k] = s
        else:
            continue
        if not k in allow_multiline:
            post[k] = re.sub(r'[\r\n]', '', post[k])

    # 受信データを返す
    return post

def paging(targets, page_size, current_page):
    """
    リストに対するページング処理
    """
    if len(targets) <= page_size:
        return targets, 1, 1
    current_page = int(current_page)
    p_max = int(math.floor((len(targets) - 1) / page_size)) + 1
    current_page = max(1, min(p_max, current_page))
    return targets[page_size * (current_page - 1):page_size * current_page], p_max, current_page

def complete_url(path):
    """
    スキーマ、ホスト名等を付与してURLを完成する
    """
    if not path.startswith('/'):
        path = '/' + path
    return '{}://{}{}'.format(request.urlparts[0], request.urlparts[1], path)

def json_response(data, cross_domain=None):
    """
    Bottle: JSONのレスポンスを生成する
    """
    data = json.dumps(data)

    res = HTTPResponse(status=200, body=data)
    res.set_header('Content-Type', 'application/json')
    if cross_domain:
        res.set_header('Access-Control-Allow-Origin', cross_domain)
        res.set_header('Access-Control-Allow-Credentials', 'true')

    return res

class InvalidRequestException(Exception):
    """
    不正なリクエストを検出した場合に発生する例外
    """

    def __init__(self, message='不正なリクエストです。'):
        super().__init__(message)
        self._msg = message

    def __str__(self):
        return self._msg

def verifyReCAPTCHA(token):
    """
    reCAPTCHAのトークンを検証する
    """

    # Google APIへの問い合わせ
    p = {
        'secret': 'YOUR KEY',
        'response': token,
    }
    res = requests.post('https://www.google.com/recaptcha/api/siteverify', data=p)

    # 結果の確認
    result = json.loads(res.content)
    return result['success']

def get_document(md_name):
    """
    文書の取得
    """
    f = str(Path(__file__).parent / 'doc' / md_name)
    with open(f, 'r', encoding='utf-8') as fin:
        html = markdown.markdown(fin.read())
    for i in range(1, 6):
        html = re.sub('</h%d>' % i, '</div>', html)
        html = re.sub('<h%d>' % i, '<div class="article article-%d">' % i, html)
    return html

def update_prop(input, update_abandonment=False):
    """
    知的財産権の情報の更新
    """
    lang = get_ui_texts()

    # 情報の追加 or 更新
    if 'Id' in input:
        is_new = False
    else:
        is_new = True

    # 共通処理に移譲
    with DbClient() as db:
        return db.update_prop(input, auth.get_account_id(), update_abandonment=update_abandonment, lang=lang)

import papers

def download_delegation(id, user_id=None, prop_id=None):
    """
    委任状のダウンロード
    """
    id = ObjectId(id)
    if not prop_id is None:
        prop_id = ObjectId(prop_id)
    lang = get_ui_texts()

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {'_id': id},
            {
                'User': 1,
                'Properties.Property': 1,
                'Properties.Classes': 1,
                'Properties.OriginalClasses': 1,
                'Properties.CanceledTime': 1,
            }
        )

        # 要否判定と対象の抽出
        needs, targets = common_util.needs_delegation_paper(req, db, prop_id=prop_id)

    if not needs:
        abort(404)

    # ユーザーチェック
    if not user_id is None:
        if targets[0]['user'] != user_id:
            abort(403)

    # 委任状の生成
    paper = papers.delegation(datetime.now())

    for t in targets:
        paper.add_item(t['reg_num'], t['names'])

    bin = paper.get_binary()

    # 生成した委任状(docx)を返す
    return push_file(bin, '%s_%s.docx' % (lang['Vocabulary']['DelegationPaper'], targets[0]['reg_num']))

def check_deletion(id, prop_id=None):
    """
    一部放棄書の要否の判定
    """
    id = ObjectId(id)
    if not prop_id is None:
        prop_id = ObjectId(prop_id)

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {'_id': id},
            {
                'User': 1,
                'Properties.PaidYears': 1,
                'Properties.Years': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Property': 1,
                'Properties.Classes': 1,
                'Properties.OriginalClasses': 1,
                'Properties.CanceledTime': 1,
            }
        )

        # 要否判定と対象の抽出
        needs, targets = common_util.needs_deletion_paper(req, db, prop_id=prop_id)

    # 結果を返す
    return needs, targets

def download_deletion(id, prop_id=None):
    """
    一部放棄書のダウンロード
    """
    lang = get_ui_texts()

    # 判定と対象の抽出
    needs, targets = check_deletion(id, prop_id)

    if not needs:
        abort(404)

    # 委任状の生成
    paper = papers.abandonment(datetime.now())

    for t in targets:
        paper.add_item(t['reg_num'], t['classes'], t['names'])

    bin = paper.get_binary()

    # 生成した委任状(docx)を返す
    return push_file(bin, '%s_%s.docx' % (lang['Vocabulary']['DeletionPaper'], targets[0]['reg_num']))

def check_hoju(id, prop_id=None):
    """
    補充更新登録申請書の要否判定
    """
    id = ObjectId(id)
    if not prop_id is None:
        prop_id = ObjectId(prop_id)

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {'_id': id},
            {
                'User': 1,
                'Properties.PaidYears': 1,
                'Properties.Years': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Property': 1,
                'Properties.Classes': 1,
                'Properties.OriginalClasses': 1,
                'Properties.CanceledTime': 1,
            }
        )

        # 要否判定と対象の抽出
        needs, targets = common_util.needs_hoju_paper(req, db, prop_id=prop_id)

    # 結果を返す
    return needs, targets

def download_hoju(id, prop_id=None):
    """
    更新登録申請書（補充）のダウンロード
    """
    # 要否判定とターゲットの抽出
    needs, targets = check_hoju(id, prop_id)

    if not needs:
        abort(404)

    # 委任状の生成
    paper = papers.koshin_shinsei_hoju(datetime.now())

    for t in targets:
        paper.add_item(t['reg_num'], t['classes'], t['holders'])

    bin = paper.get_binary()

    # 生成した委任状(docx)を返す
    return push_file(bin, '更新登録申請書（補充）_%s.docx' % targets[0]['reg_num'])

def download_abandonment(id, user_id=None, prop_id=None):
    """
    一部放棄書のダウンロード
    """
    id = ObjectId(id)
    if not prop_id is None:
        prop_id = ObjectId(prop_id)
    lang = get_ui_texts()

    with DbClient() as db:

        # 依頼情報の取得
        req = db.Requests.find_one(
            {'_id': id},
            {
                'User': 1,
                'Properties.PaidYears': 1,
                'Properties.Years': 1,
                'Properties.YearFrom': 1,
                'Properties.YearTo': 1,
                'Properties.Property': 1,
                'Properties.Classes': 1,
                'Properties.OriginalClasses': 1,
                'Properties.CanceledTime': 1,
            }
        )

        # 要否判定と対象の抽出
        needs, targets = common_util.needs_abandonment_paper(req, db, prop_id=prop_id)

    if not needs:
        abort(404, 'Not Found')

    # ユーザーチェック
    if not user_id is None:
        if targets[0]['user'] != user_id:
            abort(403)

    # 委任状の生成
    paper = papers.abandonment(datetime.now())

    for t in targets:
        paper.add_item(t['reg_num'], t['classes'], t['names'])

    bin = paper.get_binary()

    # 生成した委任状(docx)を返す
    return push_file(bin, '%s.docx' % lang['Vocabulary']['AbandonmentPaper'])

def json_safe():
    """
    dictをJSON形式に対応させる
    """
    def _json_safe(f):
        def wrapper(*args, **kwargs):
            # そのままの処理
            res = f(*args, **kwargs)
            # 再帰的な形式変換
            res = adjust_to_json(res)
            return res
        return wrapper
    return _json_safe

def adjust_to_json(d):
    """
    dictの値をjson化可能な形式に変換する
    """
    # dictは要素を再帰的に処理
    if isinstance(d, dict):
        n = {}
        for key in d.keys():
            if isinstance(d[key], datetime):
                n[key + "_Date"] = d[key].strftime('%Y-%m-%d')
                n[key + "_DateTime"] = d[key].strftime('%Y-%m-%d %H:%M:%S')
                n[key] = n[key + "_Date"]
            else:
                n[key] = adjust_to_json(d[key])
        return n
    # listは要素を再帰的に処理
    if isinstance(d, list):
        tmp = []
        for i in range(len(d)):
            tmp.append(adjust_to_json(d[i]))
        return tmp
    # datetimeは文字列に変換
    if isinstance(d, datetime):
        return d.strftime('%Y-%m-%d %H:%M:%S')
    # ObjectIdを文字列に変換
    if isinstance(d, ObjectId):
        return str(d)
    # そのまま返す
    return d

def get_property_info_from_jpp(posted_data, ui_lang, force=False):
    """
    J-PlatPatから知的財産権の情報を取得する
    """
    # キーの取得
    if 'Id' in posted_data:

        # Idが存在する場合はDBの登録情報を優先して使う
        use_id = True
        id = ObjectId(posted_data['Id'])

        with DbClient() as db:

            # 手続が進行中の場合は更新不可
            proc = common_util.under_process(db, id, include_cart=(not force))
            if proc:
                return {'Result': False, 'Message': ui_lang['Error']['UnderProcess']}

            # 権利の情報を取得
            p = db.Properties.find_one({'_id': id}, {'RegistrationNumber':1, 'Law':1, 'Country':1})

            # 取得した情報を展開
            if p:
                country = p['Country']
                law = p['Law']
                num_type = 'registration'
                num = p['RegistrationNumber']
            else:
                return {
                    'Result': False,
                    'Message': ui_lang['Pages']['Property']['JPlatPat']['CannotGetInformation']
                }

    else:

        # Id が指定されていない場合は入力された基本情報を利用する
        use_id = False

        # 入力のチェック
        if not 'Country' in posted_data:
            return {'Result': False, 'Message': 'Country is not selected.'}
        if not 'Law' in posted_data:
            return {'Result': False, 'Message': 'Law is not selected.'}

        law = posted_data['Law']
        country = posted_data['Country']

        # 番号の判別
        if 'RegistrationNumber' in posted_data:
            num_type = 'registration'
            num = common_util.regularize_reg_num(country, law, posted_data['RegistrationNumber'])
        elif 'ApplicationNumber' in posted_data:
            num_type = 'application'
            num = common_util.regularize_app_num(country, law, posted_data['ApplicationNumber'])
        else:
            return {'Result': False, 'Message': 'Missing property number.'}

    # 特許情報の検索サービスの照会
    data, message = patent_reference.refer(country, law, num, num_type, ui_lang)

    # 取得できず
    if data is None:
        return {'Result': False, 'Message': message}

    # Idが指定されていた場合はDBも更新する
    if use_id and data:

        data['Id'] = posted_data['Id']
        updated, id, message, is_new = update_prop(data, update_abandonment=True)

        # 次回手続期限の取得
        with DbClient() as db:
            p = db.Properties.find_one({'_id': id}, {'NextProcedureLimit':1})
            if p and 'NextProcedureLimit' in p:
                data['NextProcedureLimit'] = p['NextProcedureLimit']
            if p and 'NextProcedureLastLimit' in p:
                data['NextProcedureLastLimit'] = p['NextProcedureLastLimit']
            
    else:

        updated = False

        # 次回手続期限の計算
        if country == 'JP':
            if 'PaidYears' in data:
                # 商標は特別
                if law == 'Trademark':
                    # 存続期間満了日が設定されていない場合は計算しない
                    if 'ExpirationDate' in data and data['PaidYears'] <= 10:
                        data['NextProcedureLimit'] = common_util.add_months(data['ExpirationDate'], -1 * 12 * (10 - data['PaidYears']))
                    elif 'ExpirationDate' in data:
                        data['NextProcedureLimit'] = data['ExpirationDate']
                    # 分割納付でない場合は次回手続の開始日をセットする
                    if data['PaidYears'] == 10 and 'NextProcedureLimit' in data:
                        if common_util.in_and_true(data, 'Disappered') or 'DisappearanceDate' in data:
                            # 消滅している場合は計算しない
                            pass
                        if data['NextProcedureLimit'] < jp_calendar.add_months(common_util.get_today(), 6):
                            # 期限を渡過している場合は計算しない
                            pass
                        else:
                            data['NextProcedureOpenDate'] = common_util.add_months(data['NextProcedureLimit'], -6)
                    # 追納期限と閉庁日調整
                    if 'NextProcedureLimit' in data:
                        data['NextProcedureLastLimit'] = jp_calendar.add_months(data['NextProcedureLimit'], 6, consider_holiday=True)
                        data['NextProcedureLimit'] = jp_calendar.add_months(data['NextProcedureLimit'], 0, consider_holiday=True)
                else:
                    # 登録日が設定されていない場合は計算しない
                    if 'RegistrationDate' in data:
                        data['NextProcedureLimit'] = jp_calendar.add_months(data['RegistrationDate'], 12 * data['PaidYears'], consider_holiday=True)
                        data['NextProcedureLastLimit'] = jp_calendar.add_months(data['RegistrationDate'], (12 * data['PaidYears']) + 6, consider_holiday=True)
            elif law == 'Trademark':
                # 納付年数のない商標は更新
                if 'ExpirationDate' in data:
                    data['NextProcedureLimit'] = data['ExpirationDate']
                # 分割納付でない場合は次回手続の開始日をセットする
                if common_util.in_and_true(data, 'Disappered') or 'DisappearanceDate' in data:
                    # 消滅している場合は計算しない
                    pass
                if data['NextProcedureLimit'] < jp_calendar.add_months(common_util.get_today(), 6):
                    # 期限を渡過している場合は計算しない
                    pass
                else:
                    data['NextProcedureOpenDate'] = common_util.add_months(data['NextProcedureLimit'], -6)
                # 追納期限と閉庁日調整
                if 'NextProcedureLimit' in data:
                    data['NextProcedureLastLimit'] = jp_calendar.add_months(data['NextProcedureLimit'], 6, consider_holiday=True)
                    data['NextProcedureLimit'] = jp_calendar.add_months(data['NextProcedureLimit'], 0, consider_holiday=True)
            
    # レスポンスの生成
    res = {
        'Result': True,
        'Data': data,
        'Updated': updated,
    }
    return res

def local_page():
    """
    同一ホスト内でのリクエストに制限するデコレーター
    """
    def _local_page(f):
        def wrapper(*args, **kwargs):
            # リクエスト元を確認
            referer = request.headers.get('Referer')
            if referer is None:
                logger.warning('Referer is None.')
                for k in request.headers.keys():
                    logger.warning(' %s: %s', k, request.headers.get(k))
            host = request.headers.get('Host')
            if referer is None or host is None:
                redirect('/login')
            if not re.match(r'https?://' + re.escape(host) + '/', referer):
                redirect('/login')
            # 問題なければそのままの処理
            return f(*args, **kwargs)
        return wrapper
    return _local_page

def show_error_page(message):
    """
    エラーページを表示する
    """
    return apply_template('error', doc={'message': message})
