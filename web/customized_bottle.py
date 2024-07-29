from bottle import Bottle
from bottle import HTTPResponse
from bottle import TEMPLATE_PATH, jinja2_template as template
from bottle import request, response, install
import json
import logging

import web_util
import language

logger = logging.getLogger(__name__)

def add_common_headers(f):
    """
    共通ヘッダーの付与（プラグイン）
    """

    def add_common_headers_(*args, **kwargs):

        # 応答の取得
        body = f(*args, **kwargs)

        # 応答の形式の判定
        if isinstance(body, HTTPResponse):
            target = body
        else:
            target = response

        # 共通ヘッダーの設定
        target.set_header('X-Frame-Options', 'deny')
        target.set_header('X-XSS-Protection', '1; mode=block')
        target.set_header('Cache-Control', 'no-cache')
        target.set_header('X-Content-Type-Options', 'nosniff')

        # 返す
        return body

    return add_common_headers_

def set_language(f):
    """
    言語の設定
    """

    def set_language_(*args, **kwargs):

        # クエリーパラメーターから言語を取得
        lang = request.query.lang
        if not lang is None and lang != '':
            web_util.set_cookie("lang", lang)

        # 応答の取得
        return f(*args, **kwargs)

    return set_language_

error_messages = {
    400: '許可されない要求が検出されました。',
    401: 'アクセスできません。',
    403: 'アクセスできません。',
    404: 'ページが見つかりません。',
    500: 'エラーが発生しました。',
}

class CustomBottle(Bottle):
    """
    Bottleの拡張クラス
    """

    @add_common_headers
    def default_error_handler(self, res):
        """
        既定のエラーハンドラー
        """
        try:
            logger.warning('default error handler: %s at %s', res, request.url)
        except:
            pass

        # 辞書の取得
        lang = web_util.get_cookie('lang')
        if lang is None or lang == '':
            lang = 'ja'
        lang = language.get_dictionary(lang)

        # メッセージ判定
        if res.status_code in error_messages:
            msg = error_messages[res.status_code]
        else:
            msg = 'エラーが発生しました。'

        # Ajax判定
        res2 = None

        try:
            t = request.headers['X_Requested_With'].lower()
            if t == 'xmlhttprequest':
                body = json.dumps({'message': msg})
                res2 = HTTPResponse(status=res.status_code, body=body)
                res2.set_header('Content-Type', 'application/json')
        except KeyError:
            pass

        # HTMLのエラーページを返す
        if res2 is None:
            body = template('error', {'message': msg, 'UI': lang})
            res2 = HTTPResponse(status=res.status_code, body=body)

        return res2

# app
app = CustomBottle()
app.install(set_language)
app.install(add_common_headers)
