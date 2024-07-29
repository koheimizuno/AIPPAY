"""
期限管理リスト共通処理
"""

from bottle import request
from datetime import datetime

def get_page_paramegers():
    """
    表示用パラメーターを取得する
    :return 1:ページ番号(1-based), 2:ソートキー, 3:ソート方向
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
    elif not sort in ('r', 'h', 'u', 'n','m',):
        sort = 'n'
    
    if dire is None:
        dire = 'a'
    elif not dire in ('a', 'd',):
        dire = 'a'

    # 決定したパラメーターを返す
    return page, sort, dire

def sort_properties(props, sort_key, sort_direction):
    """
    指定条件に従ってリストを並べ替える
    """
    if sort_key == 'n':
        # 次回納付期限
        props = sorted(props, key=lambda x: x['NextProcedureLimit'] if 'NextProcedureLimit' in x else (datetime.min if (sort_direction == 'd') else datetime.max), reverse=(sort_direction == 'd'))
    elif sort_key == 'r':
        # 登録番号
        props = sorted(props, key=lambda x: x['RegistrationNumber'] if 'RegistrationNumber' in x else '\U00010FFFF', reverse=(sort_direction == 'd'))
    elif sort_key == 'm':
        # 整理番号
        props = sorted(props, key=lambda x: x['ManagementNumber'] if 'ManagementNumber' in x else '\U00010FFFF', reverse=(sort_direction == 'd'))
    elif sort_key == 'h':
        # 権利者
        def first_holder(x):
            if 'Holders' in x:
                return x['Holders'][0]
            return '\U00010FFFF'
        props = sorted(props, key=lambda x: first_holder(x), reverse=(sort_direction == 'd'))
    elif sort_key == 'u':
        # ユーザー
        def user_name(x):
            if 'UserOrganization' in x:
                return x['UserOrganization']
            if 'UserName' in x:
                return '\U00010FFFF' + x['UserName']
            return '\U00010FFFF' * 2
        props = sorted(props, key=lambda x: user_name(x), reverse=(sort_direction == 'd'))
    return props
