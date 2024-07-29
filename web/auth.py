from bottle import request, redirect, abort
import beaker
import logging
import re
import pymongo.errors
from datetime import datetime
from bson.objectid import ObjectId

import security
from database import DbClient

# ロガーの取得
logger = logging.getLogger(__name__)

def get_session():
    """
    Beakerで管理されるセッションを取得する
    """
    return request.environ.get('beaker.session')

def get_account_id():
    """
    現在のセッションでログイン中のアカウントの_idを取得する
    """
    # セッションからIDを取得する
    t = get_session().get('%s.account' % __name__)

    if t and t != '':
        # ObjectId
        return ObjectId(t)

    # 条件を満たさなければid値を返さない
    return None

def is_authenticated():
    """
    現在のセッションが認証済か否かを取得する
    """
    return not (get_account_id() is None)

def enter(mail_address):
    """
    認証済セッションの開始
    """
    # 念のため、アカウントの存在だけチェック
    # ※パスワードは事前に検証されること！
    with DbClient() as db:

        ent = db.Users.find_one({'MailAddress': mail_address, 'Ignored':{'$exists':False}})

        if ent is None:
            raise AuthenticationException()

        # メンテナンスモード下ではログインを制限する
        x = db.Misc.find_one({'Key': 'MaintenanceMode'})
        if x is None:
            pass
        elif x['Value']:
            if not ('IsAdmin' in ent and ent['IsAdmin']):
                raise AuthenticationException()

        # ログイン時刻の記録
        db.Users.update_one({'_id': ent['_id']}, {'$set':{'LastLogInTime':datetime.now()}})
        logger.info('%s logged in (%s, %s)', ent['_id'], request.headers['User-Agent'], request.remote_addr)

    # セッションを開始
    sess = get_session()
    sess.invalidate()
    sess['%s.account' % __name__] = ent['_id']
    sess.save()

def quit():
    """
    セッションの終了
    """
    # ログアウトの記録
    id = get_account_id()
    if not id is None:
        logger.info('%s (user) logged out.', id)
    # セッションの破棄
    sess = get_session()
    if not sess is None:
        sess.invalidate()

def require():
    """
    認証済セッションを要求するデコレーター
    """
    def _require(f):

        def wrapper(*args, **kwargs):

            # ログイン状態の確認
            if not is_authenticated():

                # ログイン後のリダイレクト先を付与
                path = ''
                if request.urlparts[2] != '':
                    path = request.urlparts[2]
                    if request.urlparts[3] != '':
                        path += '?' + request.urlparts[3]

                if path != '':
                    path = '/' + security.encrypt(path)

                redirect('/login' + path)

            # 名前が未登録の場合は登録ページにリダイレクト
            if request.urlparts[2] != '/newuser' and request.urlparts[2] != '/bye':
                with DbClient() as db:
                    ent = db.Users.find_one({'_id': get_account_id()})
                    if not ent is None and not 'Name' in ent:
                        redirect('/newuser')

            # 元の関数をそのまま実行する
            return f(*args, **kwargs)

        return wrapper

    return _require

def require_ajax():
    """
    認証済セッションを要求するデコレーター (for Ajax)
    """

    def _require(f):

        def wrapper(*args, **kwargs):

            # ログイン状態の確認
            if not is_authenticated():
                abort(401)

            # 元のメソッドを実行
            return f(*args, **kwargs)

        return wrapper

    return _require

def client_only():
    """
    会員権限を要求するデコレーター
    """
    def _require(f):
        def wrapper(*args, **kwargs):
            # ログイン状態の確認
            if not is_client():
                abort(401)
            return f(*args, **kwargs)
        return wrapper
    return _require

def staff_only():
    """
    スタッフ権限を要求するデコレーター
    """
    def _require(f):
        def wrapper(*args, **kwargs):
            # ログイン状態の確認
            if not is_staff():
                abort(401)
            return f(*args, **kwargs) 
        return wrapper
    return _require

def admin_only():
    """
    管理者権限を要求するデコレーター
    """
    def _require(f):
        def wrapper(*args, **kwargs):
            # ログイン状態の確認
            if not is_admin():
                abort(401) 
            return f(*args, **kwargs)
        return wrapper
    return _require

def _get_account_info():
    """
    現在のアカウントについての権限を取得する
    """
    # 現在のアカウントの _id を取得する
    _id = get_account_id()
    if not _id:
        return None

    # データベースから情報を取得する
    with DbClient() as db:
        return db.Users.find_one({
            '_id': _id
            , 'Ignored':{'$exists':False}
        }, {'IsClient':1, 'IsStaff': 1, 'IsAdmin': 1})

def get_user_currency():
    """
    ログインしているユーザーに関連付けられた通貨を取得する
    """
    info = _get_account_info()
    if info is None or not 'Currency' in info:
        return "JPY"
    else:
        return info["Currency"]

def is_client():
    """
    現在のユーザーが「会員」権限を所有しているか否かを調べる
    """
    doc = _get_account_info()

    if doc is None or not 'IsClient' in doc:
        return False
    else:
        return doc['IsClient']

def is_staff():
    """
    現在のユーザーが「スタッフ」権限を所有しているか否かを調べる
    """
    doc = _get_account_info()

    if doc is None or not 'IsStaff' in doc:
        return False
    else:
        return doc['IsStaff']

def is_admin():
    """
    現在のユーザーが「管理者」権限を所有しているか否かを調べる
    """
    doc = _get_account_info()

    if doc is None or not 'IsAdmin' in doc:
        return False
    else:
        return doc['IsAdmin']

# 認証関係のエラー
class AuthenticationException(Exception):
    def __init__(self, message='Authentication Error'):
        self._message = message
    def __str__(self):
        return self._message

def save_in_session(name, value):
    """
    情報をセッションに保持させる
    """
    sess = get_session()
    sess[name] = value
    sess.save()

def load_from_session(name):
    """
    セッションに保持させた情報を取得する
    """
    sess = get_session()
    return sess.get(name)
