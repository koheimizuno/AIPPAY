from bottle import Bottle, HTTPResponse
from bottle import run, request, response, redirect, abort, static_file
from beaker.middleware import SessionMiddleware
import logging
import re
from datetime import datetime, timedelta
import os
import io
import json
from pathlib import Path
import markdown

# local modules
import common_util
from customized_bottle import app
from database import DbClient
import security
import auth
import local_config
import web_util
import language
import mail
from web_util import InvalidRequestException

import user_page
import staff_page

# ロガーの設定
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)

@app.route('/js/<file_path:path>')
def static(file_path):
    """
    JS
    """
    root_dir = './js'
    p = Path(root_dir) / file_path
    if not p.is_file():
        abort(404)
    
    # ファイルの読み込み
    with open(str(p), 'r', encoding='utf-8') as fin:
        src = fin.read()
    
    # 指定言語で置換
    lang = language.get_dictionary(web_util.get_language())

    def a(match):
        keys = match.group(1).split(".")
        keys = keys[1:]
        d = lang
        for i in range(len(keys) - 1):
            if keys[i] in d:
                d = d[keys[i]]
            else:
                return match.group(1)
        if keys[-1] in d and isinstance(d[keys[-1]], str):
            return d[keys[-1]]
        else:
            return match.group(1)

    src = re.sub(r'\{\{\s*(\S+)\s*\}\}', a, src)

    # 返す
    res = HTTPResponse(status=200, body=src)
    res.set_header('Content-Type', 'text/javascript')
    return res

@app.route('/static/<file_path:path>')
def static(file_path):
    """
    静的パス
    """
    root_dir = './static'
    p = Path(root_dir) / file_path
    if not p.is_file():
        abort(404)
    return static_file(file_path, root=root_dir)

@app.get('/favicon.ico')
def favicon():
    """
    ファビコン
    """
    return static_file('static/img/favicon.ico', root='.')

@app.get('/favicon.jpg')
def favicon():
    """
    ファビコン
    """
    return static_file('static/img/favicon.ico', root='.')

@app.get('/robots.txt')
def robots():
    """
    robots.txt
    """
    return static_file('robots.txt', root='./static')

@app.get('/sitemap.xml')
def robots():
    """
    sitemap.xml
    """
    return static_file('sitemap.xml', root='./static')

@app.get('/css_debug')
def css_debug():
    """
    CSS確認用
    """
    return web_util.apply_template('css_debug')

def default():
    """
    フロントページ（非ログイン）
    """
    return static_file('portal/index.html', root='.')

@app.get('/')
def default():
    """
    フロントページ（非ログイン）
    """
    # 直接依頼ページにリダイレクト
    redirect('/e/req/')

@app.get('/loginlink')
def pre_signup_page_default():
    """
    ログインリンク取得ページ
    """
    return web_util.apply_template('login_link')

@app.post('/loginlink')
@web_util.local_page()
def pre_signup_page_posted():
    """
    会員仮登録の受付
    """
    lang = web_util.get_ui_texts()

    # スパム防止
    c_cnt = web_util.get_cookie('PK.Reg')
    if not c_cnt is None:
        c_cnt = datetime.strptime(c_cnt, '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - c_cnt).total_seconds() < 100:
            return web_util.apply_template('login_link', doc={'AlertMessage': lang['Error']['PleaseWait']})

    if request.forms.recaptchaResponse:
        if not web_util.verifyReCAPTCHA(request.forms.recaptchaResponse):
            # エラーがある場合はページを戻す
            return web_util.apply_template('login_link', doc={'AlertMessage': lang['Error']['E10003']})

    # 受信データの取得
    posted = web_util.get_posted_data()

    # メールアドレスの取得
    addr = posted['MailAddress']

    if addr is None:
        return web_util.apply_template('login_link', doc={'AlertMessage': lang['Pages']['SignUp']['TEXT000001']})

    addr = addr.strip()

    # メールアドレスの検証
    if addr == '':
        return web_util.apply_template('login_link', doc={'AlertMessage': lang['Pages']['SignUp']['TEXT000001']})

    if not security.is_email(addr):
        return web_util.apply_template('login_link', doc={'MailAddress': addr, 'AlertMessage': lang['Pages']['SignUp']['TEXT000002']})

    with DbClient() as db:

        # 登録済のメールアドレスを確認する
        user = db.Users.find_one(
            {'MailAddress': addr, 'Ignore':{'$exists': False}}
        )

        if user is None:

            # 未登録なら新規に登録
            res = db.Users.insert_one({
                'MailAddress': addr,
                'IsClient': True,
                'Language': web_util.get_language(),
                'Currency': 'JPY',
                'ModifiedTime': datetime.now(),
            })
            user = db.Users.find_one({'_id': res.inserted_id})

        # 固定リンクの取得
        if 'LoginLinkKey' in user:

            key = user['LoginLinkKey']

        else:

            # キーの生成
            key = security.generate_passwd(32)
            while db.Users.count_documents({'LoginLinkKey': key}) > 0:
                key = security.generate_passwd(32)
            db.Users.update_one(
                {'_id': user['_id']},
                {'$set': {'LoginLinkKey': key}}
            )

        # URLの生成
        url = web_util.complete_url("/ll?k=" + key)

    # メールメッセージの生成
    with io.StringIO() as buff:

        buff.write('\n')
        s = '{} {} {}'.format(lang['Common']['NamePrefix'], addr, lang['Common']['NameSuffix'])
        s = s.strip()
        buff.write('%s\n\n' % s)
        buff.write(lang['Pages']['LogIn']['TEXT000006'].format(URL=url))
        buff.write(lang.mail_footer())

        mail_body = buff.getvalue()

    # メールの送信
    try:
        mail.send_mail(lang['Pages']['LogIn']['TEXT000005'], mail_body, addr)
    except:
        logger.exception('smtp error at publish login url process.')
        return web_util.apply_template('login_link', doc={'MailAddress': addr, 'AlertMessage': lang['Pages']['LogIn']['TEXT000007']})

    # スパム防止用の Cookie を埋める
    web_util.set_cookie(
        'PK.Reg',
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        expires=datetime.now()+timedelta(seconds=10*60)
    )

    # 案内ページを返す
    return web_util.apply_template('login_link', doc={'Message': lang['Pages']['LogIn']['TEXT000003']})

@app.get('/ll')
def login_by_link():
    """
    固定リンクでのログイン
    """
    lang = web_util.get_ui_texts()

    # キーの取得
    key = request.query.k
    if key is None:
        return web_util.apply_template('error', doc={'message': lang['Pages']['LogIn']['TEXT000008']})
    key = str(key).strip()
    if key == '':
        return web_util.apply_template('error', doc={'message': lang['Pages']['LogIn']['TEXT000008']})

    with DbClient() as db:

        # 該当するユーザーの取得
        user = db.Users.find_one({
            'LoginLinkKey': key,
            'Ignored': {'$exists': False},
        })

        if user is None:
            return web_util.apply_template('error', doc={'message': lang['Pages']['LogIn']['TEXT000008']})

        # 認証済セッションの開始
        try:
            auth.enter(user['MailAddress'])
        except auth.AuthenticationException:
            redirect('/')

        # 知的財産権ページに飛ばす
        redirect('/kigen')

@app.get('/newuser')
@auth.require()
def new_user_page_default():
    """
    氏名等の初期登録ページ
    """
    user_id = auth.get_account_id()

    with DbClient() as db:

        # 現状の登録を取得
        user = db.Users.find_one({'_id': user_id})

        # 入力ページの表示
        return web_util.apply_template('login_user', doc=user)

@app.post('/newuser')
@auth.require()
def new_user_page_default():
    """
    氏名等の初期登録ページ
    """
    lang = web_util.get_ui_texts()
    user_id = auth.get_account_id()
    posted = web_util.get_posted_data()

    if not 'Name' in posted or posted['Name'].strip() == '':
        posted['Alert'] = lang['Pages']['LogIn']['TEXT000009']
        return web_util.apply_template('login_user', doc=posted)

    with DbClient() as db:

        # 更新クエリー
        update = {'$set':{
            'Name': posted['Name'],
            'ModifiedTime': datetime.now(),
        }}
        if 'Organization' in posted and posted['Organization'].strip() != '':
            update['$set']['Organization'] = posted['Organization']
        else:
            update['$unset'] = {'Organization':''}

        # ユーザー情報を更新
        res = db.Users.update_one(
            {'_id': user_id},
            update
        )

        # ページ遷移
        if res.modified_count > 0:
            if auth.is_staff():
                redirect('/s/reqs')
            else:
                redirect('/kigen')
        else:
            # 入力ページの表示
            return web_util.apply_template('login_user', doc=posted)

@app.get('/login')
def login_page(info=None):
    """
    ログインフォーム
    """
    # 既にログインしている場合はリダイレクト
    if auth.is_authenticated():
        if auth.is_staff():
            redirect('/s/reqs')
        else:
            redirect('/kigen')
    # ログインフォームを表示する
    return web_util.apply_template('login', info=info, csrf_name='login')

@app.route('/login/<path:path>')
def login_page_wth_path(path):
    """
    ログインフォーム（リダイレクト先付き）
    """
    if path:
        return web_util.apply_template('login', doc={'_rd': path}, csrf_name='login')
    else:
        return login_page()

@app.post('/login')
@web_util.local_page()
def login_page_posted():
    """
    ログイン (POST)
    """
    # POSTデータの取得
    posted = web_util.get_posted_data(csrf_name='login')
    lang = web_util.get_ui_texts()

    if request.forms.recaptchaResponse:
        if not web_util.verifyReCAPTCHA(request.forms.recaptchaResponse):
            # エラーがある場合はページを戻す
            return web_util.apply_template('login'
                , doc={x: posted[x] for x in posted.keys() if x == '_rd'}
                , alert=lang['Error']['E10003']
                , csrf_name='new_1')

    # パスワードのハッシュ化
    passwd = security.hash(posted['Password'])

    with DbClient() as db:

        # エントリーの確認
        ent = db.Users.find_one({'MailAddress': posted['MailAddress']
            , 'Password': passwd
            , 'Ignored' : {'$exists': False}})

        if ent is None:
            return web_util.apply_template('login'
                , doc={x: posted[x] for x in posted.keys() if x == '_rd'}
                , alert=lang['Pages']['LogIn']['Ummatch']
                , csrf_name='login')

        # セッションの開始
        try:
            auth.enter(posted['MailAddress'])
        except auth.AuthenticationException:
            redirect('/')

    # URLで指定されたページに飛ばす
    if '_rd' in posted:
        path = posted['_rd']
        path = security.decrypt(path)
        if path and path != '':
            redirect(path)

    # 初期ページにリダイレクト
    if auth.is_staff():
        redirect('/s/reqs')
    else:
        redirect('/kigen')

@app.get('/me')
@auth.require()
def user_page(info=None, alert=None):
    """
    ユーザー（会員）情報ページ
    """
    # ユーザー情報の取得
    with DbClient() as db:
        u = db.Users.find_one({'_id': auth.get_account_id()})

    # 言語設定の追加
    if not 'Language' in u:
        u['Language'] = web_util.get_language()

    # 通貨設定の追加
    if not 'Currency' in u:
        u['Currency'] = 'JPY'

    # 追加アドレスを配列からスカラーに置き換える
    if 'CcAddresses' in u:
        for i in range(len(u['CcAddresses'])):
            u['CcAddress_%d' % i] = u['CcAddresses'][i]
        del u['CcAddresses']

    # ページの生成
    u['cdata']= security.encrypt_dict(u)
    return web_util.apply_template('user_user', doc=u, info=info, alert=alert, csrf_name='user_user')

def user_page_validate(posted):
    """
    ユーザー情報の検証
    """
    lang = web_util.get_ui_texts()

    # メールアドレス
    if not 'MailAddress' in posted:
        return False, lang['Error']['RequireField'].format(lang['Vocabulary']['MailAddress'])
    if not security.is_email(posted['MailAddress']):
        return False, lang['Error']['InvalidField'].format(lang['Vocabulary']['MailAddress'])

    # 名前
    if not 'Name' in posted:
        return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Name'])

    # ※言語・通貨は更新しない
    ## 言語
    #if not 'Language' in posted:
    #    return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Language'])
    #if not posted['Language'] in ('ja', 'en', 'zh_CN', 'zh_TW'):
    #    return False, lang['Error']['InvalidField'].format(lang['Vocabulary']['Language'])

    ## 通貨
    #if not 'Currency' in posted:
    #    return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Currency'])
    #if not posted['Currency'] in ('JPY', 'CNY'):
    #    return False, lang['Error']['InvalidField'].format(lang['Vocabulary']['Currency'])

    # OK
    return True, None

@app.post('/me')
@auth.require()
def user_page_posted():
    """
    ユーザー（会員）情報ページ (POST)
    """
    posted = web_util.get_posted_data(csrf_name='user_user')
    cdata = security.decrypt_dict(posted['cdata'])
    lang = web_util.get_ui_texts()

    # 必須フィールドのチェック
    result, message = user_page_validate(posted)
    if not result:
        return user_page(alert=message)

    with DbClient() as db:

        # 現在の情報を取得
        cur = db.Users.find_one({'_id': auth.get_account_id()})

        # IDをチェック
        if cur['_id'] != cdata['_id']:
            raise InvalidRequestException()

        # 更新クエリー
        tran = {'$set':{}, '$unset':{}}

        if cur['MailAddress'] != posted['MailAddress']:
            tran['$set']['MailAddress'] = posted['MailAddress']

        # 言語・通貨は更新しない
        #tran['$set']['Language'] = posted['Language']
        #tran['$set']['Currency'] = posted['Currency']

        # 追加アドレスをリストに置き換える
        tmp = []
        for i in range(0, 3):
            field = 'CcAddress_%d' % i
            if field in posted and posted[field] != "":
                if posted[field] == posted['MailAddress']:
                    continue
                if posted[field] in tmp:
                    continue
                if not security.is_email(posted[field]):
                    return user_page(alert=lang['Pages']['User']['TEXT000009'])
                tmp.append(posted[field])
        if len(tmp) > 0:
            tran['$set']['CcAddresses'] = tmp
        else:
            tran['$unset']['CcAddresses'] = ''
        
        # 他で登録されたアドレスでないか調べる
        tmp = [posted['MailAddress'],]
        #if 'CcAddresses' in tran['$set']:
        #    tmp += tran['$set']['CcAddresses']
        tmp = [x for x in tmp if x != cur['MailAddress']]
        for addr in tmp:
            cnt = db.Users.count_documents({'$and':[
                {'Ignored': {'$exists': False}},
                {'$or':[
                    {'MailAddress': addr},
                    {'CcAddresses': {'$in':[addr,]}},
                ]},
                {'_id':{'$ne': cur['_id']}},
            ]})
            if cnt > 0:
                return user_page(alert=lang['Pages']['User']['TEXT000008'].format(addr))

        # 更新日
        tran['$set']['ModifiedTime'] = datetime.now()

        if len(tran['$unset']) == 0:
            del tran['$unset']

        # 更新
        db.Users.update_one({'_id': cur['_id']}, tran)

        # 名前の変更
        user_name = posted['Name']
        if 'Organization' in posted:
            user_org = posted['Organization']
        else:
            user_org = None
        common_util.update_user_name(db, cur['_id'], user_name, user_org)

    # ページの再表示
    return user_page(info=lang['Common']['Updated'])

@app.get('/user/transfer')
@auth.require()
def user_transfer_page(doc={}, info=None, alert=None):
    """
    引き継ぎページ
    """
    return web_util.apply_template('user_transfer', doc=doc, info=info, alert=alert, csrf_name='user_user')

@app.post('/user/transfer')
@auth.require()
def user_transfer_page_posted():
    """
    引き継ぎページ
    """
    posted = web_util.get_posted_data(csrf_name='user_user')
    lang = web_util.get_ui_texts()

    if not 'MailAddress' in posted:
        return user_transfer_page(doc=posted, alert=lang['Pages']['User']['TEXT000013'])

    with DbClient() as db:

        # 現在の情報を取得
        cur = db.Users.find_one({'_id': auth.get_account_id()})

        # メールアドレスのチェック
        if posted['MailAddress'] == cur['MailAddress']:
            return user_transfer_page(doc=posted, alert=lang['Pages']['User']['TEXT000014'])

        # 引き継ぎ先のユーザーを取得
        new_user = db.Users.find_one({
            'MailAddress': posted['MailAddress'],
            'Ignored': {'$exists': False},
        })
        if new_user is None:
            return user_transfer_page(doc=posted, alert=lang['Pages']['User']['TEXT000015'])

        # 引き継ぎの実行
        common_util.transfer_properties(db, cur['_id'], new_user['_id'])

    # ページの再表示
    return user_transfer_page(info=lang['Common']['Updated'])

@app.route('/me/m/<key>')
@auth.require()
def user_page_change_address(key):
    """
    メールアドレスの検証（変更時）
    """
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 現在のユーザー情報を取得
        user = db.Users.find_one({'_id': auth.get_account_id()})

        if not 'MailAddressValidateKey' in user:
            return user_page(alert=lang['Error']['CannotUpdate'])
        elif user['MailAddressValidateKey'] != key:
            return user_page(alert=lang['Error']['CannotUpdate'])

        if not 'MailAddressValidateLimit' in user:
            return user_page(alert=lang['Error']['CannotUpdate'])
        elif user['MailAddressValidateLimit'] < datetime.now():
            return user_page(alert=lang['Error']['Expired'])

        # 既に同じメールアドレスで本登録されていないか調べる
        if db.Users.count_documents({
            'MailAddress': user['UncertainMailAddress'],
            'Password': {'$exists': True},
            'Ignored': {'$exists': False},
            '_id': {'$ne': user['_id']}}) > 0:
            return user_page(alert=lang['Error']['CannotUpdate'])

        # メールアドレスの書き換え
        db.Users.update_one(
            {'_id': user['_id']},
            {'$set': {
                'MailAddress': user['UncertainMailAddress'],
                'ModifiedTime': datetime.now()
            },
             '$unset': {
                'MailAddressValidateKey': '',
                'MailAddressValidateLimit' : '',
                'UncertainMailAddress': '',
            }}
        )

    # 会員ページを開く
    return user_page(info=lang['Pages']['User']['MailAddressIsUpdated'])

@app.get('/pwd')
@auth.require()
def password_page_default():
    """
    パスワード変更ページ
    """
    return password_page()

def password_page(info=None, alert=None):
    """
    パスワード変更ページ
    """
    # 現在のユーザーにパスワード設定があるか調べる
    with DbClient() as db:
        user = db.Users.find_one({'_id': auth.get_account_id()})
        has_pwd = ('Password' in user)
    # ページを表示する
    return web_util.apply_template('passwd', doc={'HasPassword': has_pwd}, info=info, alert=alert, csrf_name='passwd')

def password_page_validate(db, posted):
    """
    パスワード変更ページでの入力チェック
    """
    lang = web_util.get_ui_texts()

    # 必須フィールドのチェック
    for k in ('NewPassword1', 'NewPassword2'):
        if not k in posted:
            return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Password'])

    # 現在のパスワードのチェック
    u = db.Users.find_one({'_id': auth.get_account_id()})

    if 'Password' in u:

        if not 'Password' in posted:
            return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Password'])

        if u['Password'] != security.hash(posted['Password']):
            return False, lang['Pages']['User']['CurrentPasswordIsIncorrect']

        # 新旧同一チェック
        if posted['Password'] == posted['NewPassword1']:
            return False, lang['Pages']['User']['PasswordIsNotChanged']

    # 新しいパスワードのチェック
    if posted['NewPassword1'] != posted['NewPassword2']:
        return False, lang['Pages']['User']['NewPasswordsAreNotMatched']

    # パスワードの強度チェック
    if not security.is_safe_as_password(posted['NewPassword1']):
        return False, lang['Error']['WeakPassword']

    # OK
    return True, None

@app.post('/pwd')
@auth.require()
@web_util.local_page()
def password_page_posted():
    """
    パスワード変更ページ (POST)
    """
    posted = web_util.get_posted_data(csrf_name='passwd')
    lang = web_util.get_ui_texts()

    with DbClient() as db:

        # 入力チェック
        res, msg = password_page_validate(db, posted)

        # チェック結果を確認
        if not res:
            return password_page(alert=msg)

        # パスワードを更新
        db.Users.update_one(
            {'_id': auth.get_account_id()},
            {'$set':{
                'Password': security.hash(posted['NewPassword1'])
            }}
        )

    # 更新済メッセージの表示（項目は再現しない）
    return password_page(info=lang['Common']['Updated'])

@app.get('/bye')
def logout():
    """
    ログアウト
    """
    # 認証セッションの終了
    if auth.is_authenticated():
        auth.quit()
    # フロントページに飛ばす
    redirect('/')

@app.get('/pwd/reset')
def passwd_request_page(info=None, alert=None):
    """
    パスワードのリセットページ
    """
    return web_util.apply_template('pwd_reset_1', info=info, alert=alert, csrf_name='pwd_reset_1')

@app.post('/pwd/reset')
def passwd_request_page_posted():
    """
    パスワードのリセットページ
    """
    posted = web_util.get_posted_data(csrf_name='pwd_reset_1')
    lang = web_util.get_ui_texts()

    if request.forms.recaptchaResponse:
        if not web_util.verifyReCAPTCHA(request.forms.recaptchaResponse):
            # エラーがある場合はページを戻す
            return passwd_request_page(alert=lang['Error']['E10003'])

    # 必須フィールドのチェック
    if not 'MailAddress' in posted:
        return passwd_request_page(alert=lang['Error']['RequireField'].format(lang['Vocabulary']['MailAddress']))

    # スパムの防止
    c_cnt = web_util.get_cookie('PK.Reg')
    if not c_cnt is None:
        c_cnt = datetime.strptime(c_cnt, '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - c_cnt).total_seconds() < 100:
            return passwd_request_page(alert=lang['Error']['PleaseWait'])

    with DbClient() as db:

        doc = db.Users.find_one({
            'MailAddress': posted['MailAddress']
            , 'Password': {'$exists': True}
            , 'Ignored': {'$exists': False}
        })

        if doc is None:
            return passwd_request_page(alert=lang['Error']['DataIsNotFound'])

        # キー値の生成
        key = security.generate_passwd(32)

        # パスワードリセット要求の登録
        db.Password.insert_one({
            '_id':key
            , 'User': doc['_id']
            , 'MailAddress': posted['MailAddress']
            , 'DateTime': datetime.now()
        })

    # リセット用URLの生成
    url = web_util.complete_url('/pwd/reset/c/%s' % key)

    # メッセージの生成
    mail_body = lang['Pages']['User']['Mail2']['Body'].format(URL=url)
    mail_body += lang.mail_footer()

    # メールの送信
    mail.send_mail(lang['Pages']['User']['Mail2']['Subject'], mail_body, posted['MailAddress'])

    # スパム防止のCookieを埋める
    web_util.set_cookie(
        'PK.Reg',
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        expires=datetime.now()+timedelta(seconds=10*60)
    )

    # 完了の通知
    return passwd_request_page(info=lang['Pages']['User']['Mail2']['Sent'])

@app.route('/pwd/reset/c/<key>')
def passwd_reset_page(key):
    """
    パスワードリセットページ (メールから開くページ)
    """
    with DbClient() as db:

        # リセット要求を探す
        p = db.Password.find_one({
            '_id': key
            , 'DateTime': {'$gt': datetime.now() - timedelta(seconds=30*60)}
        })

        # 見つからなければ初期ページへリダイレクトする
        if p is None:
            redirect('/')

        # ユーザー情報を取得
        u = db.Users.find_one({
            '_id': p['User']
            , 'Password': {'$exists': True}
            , 'Ignored': {'$exists': False}
        })

        # 見つからなければ初期ページへリダイレクトする
        if u is None:
            redirect('/')

    # パスワード登録用ページを生成
    cdata = security.encrypt_dict({'_id': u['_id']})
    return web_util.apply_template('pwd_reset_2', doc={'cdata': cdata}, csrf_name='pwd_reset_2')

def passwd_reset_page_validate(posted):
    """
    パスワードリセットの事前チェック
    """
    lang = web_util.get_ui_texts()

    # 入力値の検証
    if not 'NewPassword1' in posted or not 'NewPassword2' in posted:
        return False, lang['Error']['RequireField'].format(lang['Vocabulary']['Password'])

    if posted['NewPassword1'] != posted['NewPassword2']:
        return False, lang['Pages']['User']['NewPasswordsAreNotMatched']

    # パスワードの強度チェック
    if not security.is_safe_as_password(posted['NewPassword1']):
        return False, lang['Error']['WeakPassword']

    # OK
    return True, None

@app.post('/pwd/reset/c')
@web_util.local_page()
def passwd_reset_page_posted():
    """
    パスワードのリセットページ
    """
    posted = web_util.get_posted_data(csrf_name='pwd_reset_2')
    cdata = security.decrypt_dict(posted['cdata'])

    # 入力値の検証
    res, msg = passwd_reset_page_validate(posted)
    if not res:
        return web_util.apply_template('pwd_reset_2'
            , doc={'cdata': posted['cdata']}
            , alert=msg
            , csrf_name='pwd_reset_2')

    # パスワードをハッシュ化
    passwd = security.hash(posted['NewPassword1'])

    with DbClient() as db:

        # データベースを更新
        db.Users.update_one({'_id': cdata['_id']}
            , {'$set': {'Password': passwd, 'PasswordChangedTime': datetime.now()}}
        )

        # 同一ユーザーのパスワードのリセット要求をすべて削除
        db.Password.remove({'User': cdata['_id']})

    # ログインページへ飛ばす
    auth.quit()
    return login_page(info=web_util.get_ui_texts()['Common']['Updated'])

@app.get('/exit')
@auth.require()
def exit_page(alert=None):
    """
    退会フォーム
    """
    lang = web_util.get_ui_texts()

    # 退会可否判定
    can_exit = True

    with DbClient() as db:

        # 未完了の依頼があるか否かを確認
        req_cnt = db.Requests.count_documents({
            '$and':[
                {'User': auth.get_account_id()},
                {'CompletedTime': {'$exists': False}},
                {'CanceledTime': {'$exists': False}},
                {'Ignored': {'$exists': False}},
            ]
        })

        if req_cnt > 0:
            alert = lang['Pages']['Exit']['CanNotExit']

    if not alert is None:
        can_exit = False

    # ページの生成
    return web_util.apply_template('exit_1', doc={'can_exit':can_exit}, alert=alert, csrf_name='exit_1')

@app.post('/exit')
@web_util.local_page()
@auth.require()
def exit_page_posted():
    """
    退会フォーム
    """
    web_util.get_posted_data(csrf_name='exit_1')
    lang = web_util.get_ui_texts()

    # ユーザー名の取得
    with DbClient() as db:

        user_id = auth.get_account_id()

        # 退会可否の再チェック
        req_cnt = db.Requests.count_documents({
            '$and': [
                {'User': user_id},
                {'CompletedTime': {'$exists': False}},
                {'CanceledTime': {'$exists': False}},
                {'Ignored': {'$exists': False}},
            ]
        })

        if req_cnt > 0:
            return exit_page(alert=lang['Pages']['Exit']['CanNotExit'])

        # ユーザー名の取得
        name = db.Users.find_one({'_id':auth.get_account_id()})['Name']

        now = datetime.now()

        # ユーザーの無効化
        db.Users.update_one(
            {'_id': user_id},
            {'$set':{
                'Ignored': now,
                'ModifiedTime': now,
                'Modifier': user_id,
            }}
        )

        # 知的財産権の無効化
        db.Properties.update_many(
            {
                'User': user_id,
                'Ignored': {'$exists': False},
            },
            {
                '$set':{
                    'Ignored': now,
                    'ModifiedTime': now,
                    'Modifier': user_id,
                }
            }
        )

    # セッションの破棄
    auth.quit()

    # 退会後ページを表示
    doc = {'UserName': name}

    return web_util.apply_template('exit_2', doc=doc)

def show_document(file_name, subject):
    """
    定型ドキュメントの表示
    """
    p = str(Path(__file__).parent / 'doc' / file_name)
    with open(p, 'r', encoding='utf-8') as fin:
        s = fin.read()
    html = markdown.markdown(s)
    for i in range(3, 0, -1):
        html = re.sub('</h%d>' % i, '</h%d>' % (i + 1), html)
        html = re.sub('<h%d>' % i, '<h%d>' % (i + 1), html)
    return web_util.apply_template('document', doc={'Subject': subject, 'Contents': html})

@app.get('/contract')
def privacy():
    """
    利用規約
    """
    lang = web_util.get_ui_texts()
    return show_document('contract.md', lang['Vocabulary']['Contract'])

@app.get('/privacy')
def privacy():
    """
    プライバシーポリシー
    """
    lang = web_util.get_ui_texts()
    return show_document('privacy.md', lang['Vocabulary']['PrivacyPolicy'])

@app.get('/legal')
def privacy():
    """
    特商法表示
    """
    lang = web_util.get_ui_texts()
    return show_document('legal_info.md', lang['Vocabulary']['LegalInfo'])

@app.route('/', method='OPTIONS')
def default_options():
    """
    OPTIONSリクエストへの対応
    """
    response.headers['Allow'] = 'GET, POST, HEAD, OPTIONS'

# 設定ファイルの取得
config = local_config.Config()

# beaker セッションの設定
# https://beaker.readthedocs.io/en/latest/configuration.html#configuration
session_opts = {
    'session.type': 'file',
    'session.cookie_expires': 48 * 60 * 60,
    'session.cookie_path': '/',
    'session.save_accessed_time': True,
    'session.timeout': 60 * 60,
    'session.data_dir': config['beaker']['data_dir'],
    'session.auto': True,
    'session.secure': True if __name__ != '__main__' else False,
    'session.httponly': True,
    'session.secret': 'Mm34w682',
    'session.samesite': 'Lax',
}

# beaker
myApp = SessionMiddleware(app, session_opts)

# Webサービスの起動
if __name__ == '__main__':
    # bottle
    run(host='localhost', port=8080, app=myApp, debug=False)
