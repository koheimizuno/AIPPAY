import re
import sys
from datetime import datetime, timedelta, date
import mojimoji
import math
import jp_calendar
import json
import unicodedata
import logging

logger = logging.getLogger(__name__)

def parse_date(text):
    """
    テキストから日付を抽出する
    """
    if isinstance(text, datetime):
        return text
    m = re.search(r'令和\s*(\d+)年\s*(\d+)月\s*(\d+)日', mojimoji.zen_to_han(text))
    if m:
        year = int(m.group(1)) + 2018
        month = int(m.group(2))
        day = int(m.group(3))
        return datetime(year, month, day)
    m = re.search(r'令\s*(\d+)\.\s*(\d+)\.\s*(\d+)', mojimoji.zen_to_han(text))
    if m:
        year = int(m.group(1)) + 2018
        month = int(m.group(2))
        day = int(m.group(3))
        return datetime(year, month, day)
    m = re.search(r'(\d{4})年\s*(\d+)月\s*(\d+)日', mojimoji.zen_to_han(text))
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        return datetime(year, month, day)
    m = re.search(r'(\d{4})(\d{2})(\d{2})', text)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        return datetime(year, month, day)
    m = re.search(r'(\d{4})([\-/.])(\d{1,2})\2(\d{1,2})', text)
    if m:
        year = int(m.group(1))
        month = int(m.group(3))
        day = int(m.group(4))
    else:
        raise ValueError('"%s" is not correct date (correct format is "yyyy-mm-dd").' % text)
    return datetime(year, month, day)

def get_today():
    """
    時以下を切り落とした当日の日付値を取得する
    """
    return truncate_time(datetime.now())

def truncate_time(d):
    """
    時以下を切り落とす
    """
    return datetime(d.year, d.month, d.day)

def add_months(basis, delta):
    """
    日付に対して月を加算する
    """
    return jp_calendar.add_months(basis, delta)

def diff_years(reg_date, dead_date):
    """
    年の差を求める
    """
    i = 0
    while add_months(reg_date, i * 12) < dead_date:
        i += 1
    return i

def last_day_of_month(d):
    """
    月末日を計算する
    """
    return add_months(datetime(d.year, d.month, 1), 1) - timedelta(days=1)

def pad0(origin, length=7):
    """
    先頭の連続する数字部分が指定桁数になるように左にゼロを埋める
    """
    # 先頭のゼロを捨てる
    origin = re.sub(r'^0+', '', origin)
    # ゼロを補完する
    m = re.match(r'(\d+)(.*)', origin)
    if m:
        s = m.group(1)
        s = (('0' * length) + s)[-1 * max(length, len(s)):]
        if m.group(2):
            s += m.group(2)
        return s
    else:
        return s

def months_to_date(d):
    """
    指定された日付までの月数を数える
    """
    t = datetime.now()
    if d < t:
        return 0
    for i in range(0, 999999):
        if d <= add_months(t, i):
            return i
    return 999999

def kanji_to_alpha_in_number(s):
    """
    番号中の漢字元号をアルファベットに置き換える
    """
    s = s.strip()
    s = re.sub(r'[ー‐―－]', '-', s)
    for k, a in (('明', 'M'), ('大', 'T'), ('昭', 'S'), ('平', 'H'), ('令', 'R')):
        if s.startswith(k):
            return a + s[1:]
    return s

def date_format(d, lang, markup=False):
    """
    言語設定に合わせて日付を整形する
    """
    # 日付値でなければそのまま返す
    if not (isinstance(d, datetime) or isinstance(d, date)):
        return d

    # 言語ごとに整形
    if lang == 'ja':
        # 日本語
        if markup:
            return '{}<span class="date-sep">年</span>{}<span class="date-sep">月</span>{}<span class="date-sep">日</span>'.format(d.year, d.month, d.day)
        else:
            return '{}年{}月{}日'.format(d.year, d.month, d.day)
    else:
        # その他の言語は標準形式
        return d.strftime('%Y-%m-%d')

def renew_limit_date(db, prop_id):
    """
    知的財産権の次回庁期限を再計算する
    """
    return db.renew_limit_date(prop_id)

def under_process(db, id, include_cart=True):
    """
    依頼を処理中か否かを判定する
    """
    return db.under_process(id, include_cart)

def is_requestable(db, id, consider_cart=True, consider_request=True):
    """
    知的財産権が手続依頼の可能な状態か確認する（データベース参照）
    """
    # 権利情報の取得
    prop = db.Properties.find_one({'_id': id})

    # 通常の判定
    result, reason, max_year, additional = is_requestable_core(prop, consider_cart=consider_cart)

    # 依頼中（未完了）
    if consider_request:
        if under_process(db, id, include_cart=False):
            return False, 'AlreadyRequested', 0, False

    # 6ヶ月以内に完了した依頼があれば依頼済扱いと考える
    if result:
        today = get_today()
        req_cnt = db.Requests.count_documents({'$and':[
            {'Properties': {'$elemMatch': {
                'Property': id,
                '$or': [
                    {'CompletedTime': {'$exists': False},},
                    {'CompletedTime': {'$gt': today - timedelta(days=183)},},
                ],
                'CanceledTime': {'$exists': False},
            }}},
            {'Ignored': {'$exists': False}},
            {'$or': [
                {'CompletedTime': {'$exists': False},},
                {'CompletedTime': {'$gt': today - timedelta(days=183)},},
            ]},
            {'CanceledTime': {'$exists': False}},
        ]})
        if req_cnt > 0:
            return False, 'AlreadyRequestedAndDone', 0, False

    # 通常の結果を返す
    return result, reason, max_year, additional

def is_requestable_no_db(prop):
    """
    知的財産権が手続依頼の可能な状態か確認する（データベース登録なし）
    """
    return is_requestable_core(prop, consider_cart=False)

def is_requestable_core(prop, consider_cart=True):
    """
    知的財産権が手続依頼の可能な状態か確認する
    """
    # 権利情報の取得
    today = get_today()

    # 権利情報の不在
    if prop is None:
        return False, 'NoData', 0, False

    # 既に消滅
    if in_and_true(prop, 'Disappered') or 'DisappearanceDate' in prop:
        return False, 'Disappered', 0, False

    # 存続期間のチェック
    if 'ExpirationDate' in prop:
        # 存続期間後は依頼不可（消滅扱い）
        if prop['Law'] != 'Trademark' or prop['Country'] != 'JP':
            if 'NextProcedureLastLimit' in prop:
                if prop['NextProcedureLastLimit'] < get_today():
                    return False, 'Disappered', 0, False
            elif prop['ExpirationDate'] < get_today():
                return False, 'Disappered', 0, False
        else:
            # 商標は追納期間を考慮する
            if 'NextProcedureLastLimit' in prop:
                if prop['NextProcedureLastLimit'] < get_today():
                    return False, 'Disappered', 0, False
            else:
                d = add_months(prop['ExpirationDate'], 6)
                if d < get_today():
                    return False, 'Disappered', 0, False

    # 既にカートに入っている
    if consider_cart:
        if 'Cart' in prop and prop['Cart']['Years'] > 0:
            return False, 'AlreadySelected', 0, False

    # 次回期限の欠如
    if not 'NextProcedureLimit' in prop:
        return False, 'Miss_NextProcedureLimit', 0, False

    # 納付期限のチェック
    if prop['Country'] == 'JP':
        if 'NextProcedureLastLimit' in prop:
            if today > prop['NextProcedureLastLimit']:
                return False, 'PassLimit', 0, False
        else:
            if today > add_months(prop['NextProcedureLimit'], 6):
                return False, 'PassLimit', 0, False
    else:
        if today > prop['NextProcedureLimit']:
            return False, 'PassLimit', 0, False

    # 商標の更新申請は期限の6月前から可能
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        p = 10
        if 'PaidYears' in prop:
            p = prop['PaidYears']
        if today < add_months(prop['NextProcedureLimit'], -6) and p == 10:
            return False, 'TooEarly', 10, False

    # 登録日・存続期間の欠如
    if prop['Country'] == 'JP':
        if not 'RegistrationDate' in prop:
            return False, "Miss_RegistrationDate", 0, False
        if not 'ExpirationDate' in prop:
            return False, "Miss_ExpirationDate", 0, False

    # 権利者
    if not 'Holders' in prop or len(prop['Holders']) == 0:
        return False, 'Miss_Holders', 0, False

    # 法区分ごとの判定
    if prop['Country'] == 'JP' and prop['Law'] == 'Patent':
        if not 'ExamClaimedDate' in prop:
            return False, 'Miss_ExamClaimedDate', 0, False
    if prop['Country'] == 'JP' and prop['Law'] in ('Patent', 'Utility',):
        if not 'NumberOfClaims' in prop:
            return False, 'Miss_NumberOfClaims', 0, False
    if prop['Country'] == 'JP' and prop['Law'] == 'Trademark':
        if not 'Classes' in prop or len(prop['Classes']) == 0:
            return False, 'Miss_Classes', 0, False

    # 納付可能年数の計算
    if prop['Country'] == 'JP':
        paid = prop['PaidYears'] if 'PaidYears' in prop else 0
        if prop['Law'] == 'Trademark':
            max_year = 5 if paid == 5 else 10
        else:
            def add_years(d, y):
                return datetime(d.year + y, d.month, d.day)
            max_year = 0
            while add_years(prop['RegistrationDate'], max_year) < prop['ExpirationDate']:
                max_year += 1
            if 'PaidYears' in prop:
                max_year -= prop['PaidYears']
    else:
        max_year = 99

    if max_year < 1:
        return False, 'PassLimit', 0, False

    # 追納判定
    additional = False

    if today > prop['NextProcedureLimit']:
        additional = True

    # 依頼可能
    return True, None, max_year, additional

def zen_to_han(original):
    """
    全角文字を半角にする
    """
    s = original
    keep = 'ー－―‐'
    r = re.compile('([' + re.escape(keep) + r'])(.*)')
    buff = ''
    while s and s != '':
        m = r.search(s)
        if m:
            if m.start() > 0:
                buff += mojimoji.zen_to_han(s[0:m.start()], kana=False)
            t = m.group(1)
            if m.start() > 0 and re.match(r'[ァ-ヴ]', s[m.start()-1]):
                # カタカナに続く場合は長音符を変換しない
                buff += m.group(1)
            else:
                buff += mojimoji.zen_to_han(m.group(1), kana=False)
            s = m.group(2)
        else:
            buff += mojimoji.zen_to_han(s, kana=False)
            s = None
    return buff

def regularize_reg_num(country, law, number):
    """
    登録番号を正規化する
    """
    # 半角化
    number = mojimoji.zen_to_han(number)

    if country == 'JP':

        # 頭のゼロをとる
        m = re.match(r'0*([1-9][0-9]*)(.*)', number)
        if m:
            s = m.group(1)
            if len(s) < 7:
                s = (('0' * 7) + s)[-7:]
            number = s + m.group(2)

    # 編集後のテキストを返す
    return number

def regularize_app_num(country, law, number):
    """
    出願番号を正規化する
    """
    # 半角化
    number = mojimoji.zen_to_han(number)

    if country == 'JP':

        # 整形
        m = re.match(r'(.)\s*(\d+)\s*[-ー‐‑―−ｰ]\s*(\d+)(.*)', number)

        if m:
            if m.group(1) == "明":
                t = "M"
            elif m.group(1) == "大":
                t = "T"
            elif m.group(1) == "昭":
                t = "S"
            elif m.group(1) == "平":
                t = "H"
            elif m.group(1) == "令":
                t = "R"
            else:
                t = m.group(1).upper()
            t += m.group(2)
            t += "-"
            s = m.group(3)
            if len(s) < 6:
                s = ("000000" + s)[-6:]
            t += s + m.group(4)
            number = t

    # 編集後のテキストを返す
    return number

def get_currencies(db):
    """
    通貨の設定情報をすべて取得する
    """
    curs = {}
    for rec in db.Currencies.find({}):
        curs[rec['_id']] = {
        }
        if 'Precision' in rec and rec['Precision'] > 0:
            curs[rec['_id']]['Format'] = '{:,.%df}' % rec['Precision']
        else:
            curs[rec['_id']]['Format'] = '{:,.0f}'
        if 'Precision' in rec:
            curs[rec['_id']]['Precision'] = rec['Precision']
        else:
            curs[rec['_id']]['Precision'] = 0
        for key in ('JPY',):
            if key in rec:
                curs[rec['_id']][key] = rec[key]
    return curs

def currency_exchange(value, from_, to, currencies):
    """
    通貨換算
    """
    if not isinstance(value, float):
        value = float(value)

    # 通貨定義を確認
    if not from_ in currencies or not to in currencies:
        raise Exception('Exchange Rate (%s-%s) is not found.' % (from_, to))

    # 為替レートが定義されているかチェック
    if not to in currencies[from_]:
        raise Exception('Exchange Rate (%s-%s) is not found.' % (from_, to))

    # レート摘要
    value = value * currencies[from_][to]

    # 符号無しで換算先通貨の精度(小数桁)に切り落として符号を付けなおす
    sign = 1.0 if value > 0 else -1.0
    value *= sign
    z = 10 ** currencies[to]['Precision']
    value = float(math.floor(value * z) / z) * sign

    # 結果を返す
    return value, currencies[from_][to]

def sort_classes(classes):
    """
    「商品および役務の区分」のリストを並べ替える
    """
    if isinstance(classes, str):
        classes = classes.split(",")
        classes = [x.strip() for x in classes if x.strip() != ""]
    temp = sorted(classes)
    def to_int(key):
        m = re.match(r'\d+', key)
        if m:
            return int(m.group(0))
        else:
            return sys.maxsize
    temp = sorted(temp, key=lambda x: to_int(x))
    temp = list(dict.fromkeys(temp))
    return temp

def needs_delegation_paper(req, db, prop_id=None):
    """
    委任状が必要か判定する
    """
    # 対象の取得
    targets = []

    for p in req['Properties']:

        # 権利が指定されている場合、該当しないものはスキップする
        if not prop_id is None:
            if p['Property'] != prop_id:
                continue

        # 権利情報の取得
        prop = db.Properties.find_one(
            {'_id': p['Property']},
            {
                'Country': 1,
                'Law': 1,
                'RegistrationNumber': 1,
                'Holders': 1,
            }
        )

        # 商標以外はスキップ
        if prop['Country'] != 'JP' or prop['Law'] != 'Trademark':
            continue

        # TODO: キャンセル案件はスキップ

        if not 'Classes' in p:
            continue

        # 区分削除があるか判定
        if len(p['OriginalClasses']) == len(p['Classes']):
            continue

        # 対象に追加
        targets.append({
            'reg_num': prop['RegistrationNumber'],
            'names': [x['Name'] for x in prop['Holders']],
            'user': req['User'],
        })

    # 判定
    if len(targets) > 0:
        return True, targets
    else:
        return False, None

def needs_abandonment_paper(req, db, prop_id=None):
    """
    放棄書が必要か判定する
    """
    # 対象の取得
    targets = []

    for p in req['Properties']:

        # 権利が指定されている場合、該当しないものはスキップする
        if not prop_id is None:
            if p['Property'] != prop_id:
                continue

        # 権利情報の取得
        prop = db.Properties.find_one(
            {'_id': p['Property']},
            {
                'Country': 1,
                'Law': 1,
                'RegistrationNumber': 1,
                'Holders': 1,
            }
        )

        # 商標以外はスキップ
        if prop['Country'] != 'JP' or prop['Law'] != 'Trademark':
            continue

        # TODO: キャンセル案件はスキップ

        # 分納後期以外はスキップ
        if not 'PaidYears' in p:
            continue
        if not (p['PaidYears'] == 5 and p['Years'] == 5):
            continue

        if not 'Classes' in p:
            continue

        # 区分削除があるか判定
        if len(p['OriginalClasses']) == len(p['Classes']):
            continue

        # 対象に追加
        targets.append({
            'reg_num': prop['RegistrationNumber'],
            'classes': [x for x in p['OriginalClasses'] if not x in p['Classes']],
            'names': [x['Name'] for x in prop['Holders']],
            'user': req['User'],
        })

    # 判定
    if len(targets) > 0:
        return True, targets
    else:
        return False, None

def needs_deletion_paper(req, db, prop_id=None):
    """
    一部抹消申請書が必要か判定する
    """
    # 判定は放棄書と同じ
    return needs_abandonment_paper(req, db, prop_id=prop_id)

def needs_hoju_paper(req, db, prop_id=None):
    """
    更新登録申請書（補充）が必要か判定する
    """
    # 対象の取得
    targets = []

    for p in req['Properties']:

        # 権利が指定されている場合、該当しないものはスキップする
        if not prop_id is None:
            if p['Property'] != prop_id:
                continue

        # 権利情報の取得
        prop = db.Properties.find_one(
            {'_id': p['Property']},
            {
                'Country': 1,
                'Law': 1,
                'RegistrationNumber': 1,
                'Holders': 1,
            }
        )

        # 商標以外はスキップ
        if prop['Country'] != 'JP' or prop['Law'] != 'Trademark':
            continue

        # TODO: キャンセル案件はスキップ

        # 更新登録申請以外はスキップ
        if 'PaidYears' in p and p['PaidYears'] != 10:
            continue

        if not 'Classes' in p:
            continue

        # 区分削除があるか判定
        if len(p['OriginalClasses']) == len(p['Classes']):
            continue

        # 対象に追加
        targets.append({
            'reg_num': prop['RegistrationNumber'],
            'classes': p['Classes'],
            'holders': prop['Holders'],
            'user': req['User'],
        })

    # 判定
    if len(targets) > 0:
        return True, targets
    else:
        return False, None

def list_procedures(prop_of_req, prop, lang, least_one=True):
    """
    依頼に対する手続内容を示すテキストのリストを生成する。
    """
    procs = []

    # 法域別に判定
    if prop['Law'] in ('Patent', 'Utility', 'Design',):

        if True:

            # 年分の表示
            if not 'YearTo' in prop_of_req or prop_of_req['YearFrom'] == prop_of_req['YearTo']:

                # 単年
                procs.append(lang['Pages']['Request']['TEXT000031'].format(prop_of_req['YearFrom']))

            else:

                # 複数年
                procs.append(lang['Pages']['Request']['TEXT000032'].format(prop_of_req['YearFrom'], prop_of_req['YearTo']))

    elif prop['Law'] == 'Trademark':

        if prop['Country'] == 'JP':

            if prop_of_req['PaidYears'] == 10:

                # 更新登録申請

                # 分納判定
                if prop_of_req['Years'] == 5:
                    # 分納
                    procs.append(lang['Pages']['Request']['TEXT000035'])
                else:
                    # 完納
                    procs.append(lang['Pages']['Request']['TEXT000034'])

                # 区分の削除の確認
                cs = [x for x in prop_of_req['OriginalClasses'] if not x in prop_of_req['Classes']]
                if len(cs) > 0:
                    procs.append(lang['Pages']['Request']['TEXT000037'].format(','.join(cs)))

            else:

                assert prop_of_req['Years'] == 5

                # 分納後期
                procs.append(lang['Pages']['Request']['TEXT000036'])

                # 区分の放棄の確認
                cs = [x for x in prop_of_req['OriginalClasses'] if not x in prop_of_req['Classes']]
                if len(cs) > 0:
                    procs.append(lang['Pages']['Request']['TEXT000038'].format(','.join(cs)))

    # 要見積
    if len(procs) == 0 and least_one:
        procs.append(lang['Pages']['Request']['TEXT000030'])

    # リストのまま返す
    return procs

def fit_currency_precision(price, precision):
    """
    通貨の小数桁数を調整する
    """
    price = float(price)
    s = 1.0 if price >= 0.0 else -1.0
    price *= s
    p = 10 ** precision
    return s * (math.floor(price * p) / p)

def dict_to_json(d):
    """
    ditcをjson形式のstrに変換する
    """
    def a(v):
        if isinstance(v, datetime):
            return v.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return v
    return json.dumps(d, default=a)

def not_in_or_false(d, key):
    """
    dict中にキーがない又は値がFalseであるか確認する
    """
    if not isinstance(d, dict):
        return False
    if not key in d:
        return True
    if d[key]:
        return False
    else:
        return True

def in_and_true(d, key):
    """
    dict中にキーがあって、且つ値がTrueであるか確認する
    """
    if not isinstance(d, dict):
        return False
    if not key in d:
        return False
    v = d[key]
    if isinstance(d[key], str):
        v = v.strip()
        if v.lower() == 'false':
            return False
        if re.match(r'\d+$', v):
            v = int(v)
        elif re.match(r'\d+\.\d+$', v):
            v = float(v)
    if v:
        return True
    else:
        return False

def in_and_false(d, key):
    """
    dict中にキーがあって、且つ値がFalseであるか確認する
    """
    if not isinstance(d, dict):
        return False
    if not key in d:
        return False
    v = d[key]
    if isinstance(d[key], str):
        v = v.strip()
        if v.lower() == 'false':
            return True
        if re.match(r'\d+$', v):
            v = int(v)
        elif re.match(r'\d+\.\d+$', v):
            v = float(v)
    if v:
        return False
    else:
        return True

def next_limit(reg_date, paid_years_to):
    """
    次回納付期限を計算する
    """
    return add_months(reg_date, 12 * paid_years_to)

def next_limit_tm(reg_date, forward=0):
    """
    商標の次回の登録更新申請の期限を計算する
    """
    n = 0
    d = reg_date

    # 「次回」を計算する基準日
    today = get_today()
    if forward != 0:
        today = add_months(today, int(12 * forward))

    # 設定登録日から10年ずつ進めて今日を超える日を探す
    dt = d
    while dt < today:
        n += 1
        dt = add_months(d, (n * 12) * 10)
    d = dt

    # 初めて今日を超えた日を返す
    return d

def text_width(text):
    """
    全角を1としたテキストの幅を取得する
    """
    if not isinstance(text, str):
        return 0.0
    l = 0.0
    for c in text:
        eaw = unicodedata.east_asian_width(c)
        l += 1.0 if eaw in ('F', 'W', 'A') else 0.5
    return l

def smart_split_texts(left, right):
    """
    いい感じにテキストを分割しなおす
    """
    if right is None or right == '':
        return left, right
    # 後ろが1文字だけなら前に送る
    if len(right) < 2:
        return left + right, ''
    # 後ろが括弧で始まるならその文字だけ前に送る
    m = re.match(r'[)）]+', right)
    if m:
        tmp = m.group(0)
        left += tmp
        if len(right) > len(tmp):
            right = right[len(tmp):]
        else:
            right = ''
        return left, right.strip()
    # 前の空白文字が近ければそこまで後ろに送る
    m = re.search(r'[)）\s\u3000]([^)）\s\u3000]{1,2})$', left)
    if m:
        tmp = m.group(1)
        left = left[:-1 * len(tmp)].strip()
        right = tmp + right
        return left, right.strip()
    # そのまま
    return left, right.strip()

def check_jp_genmen(name):
    """
    名称に基づいて該当し得る減免の区分を調べる
    """
    if re.search(r'(有限会社|株式会社|合同会社|有限公司)', name):
        return '10_4_ro'
    if re.search(r'(学校法人|国立大学法人|大学)', name):
        return '10_3_ro'
    if re.search(r'(一般社団法人)', name):
        return None
    return '10_4_i'

def check_more_two(a):
    """
    異なる2つ以上の値が含まれるか調べる
    """
    if a is None or not isinstance(a, list):
        return
    for i in range(len(a) - 1):
        for j in range(i + 1, len(a)):
            if a[i] is None and a[j] is None:
                pass
            elif a[i] is None or a[j] is None:
                return True
            elif a[i] != a[j]:
                return True
    return False

def not_in_alt(d, key, alt):
    """
    dictに指定キーが含まれない場合に代替値に置き換える
    """
    # キーが存在するかチェック
    if not key in d:
        return alt
    # キーがあってもNoneなら置き換える
    if d[key] is None:
        return alt
    # 存在する値を返す絵
    return d[key]

def find_user_by_email(db, mailAddress):
    """
    メールアドレスから該当ユーザーを探す
    :return 1:user id, 2:name, 3:org, 4:main address, 5:optional addresses
    """
    # メインアドレスを探す
    u = db.Users.find_one({
        'MailAddress': mailAddress,
        'Ignored': {'$exists': False},
    })
    if not u is None:
        return u['_id'], not_in_alt(u, 'Name', None), not_in_alt(u, 'Organization', None), u['MailAddress'], not_in_alt(u, 'CcAddresses', [])
    ## 予備アドレスを探す
    #u = db.Users.find_one({
    #    'CcAddresses': {'$in':[mailAddress,]},
    #    'Ignored': {'$exists': False},
    #})
    #if not u is None:
    #    return u['_id'], not_in_alt(u, 'Name', None), not_in_alt(u, 'Organization', None), u['MailAddress'], not_in_alt(u, 'CcAddresses', [])
    # 該当なし
    return None, None, None, None, []

def update_user_name(db, user_id, user_name, user_org):
    """
    ユーザー名を変更する
    """
    # 現在のユーザー情報を取得する
    current = db.Users.find_one({'_id': user_id})

    if not current is None and 'Name' in current:

        # 現在の登録から変更されているか確認
        if user_name != not_in_alt(current, 'Name', '') or (user_org if not user_org is None else '') != not_in_alt(current, 'Organization', ''):

            logger.info('detect user name changed.(%s)', user_id)

            # 登録済の権利について同じ名前での登録を更新する
            cond = {'$and':[
                {'User': user_id},
                {'UserName': current['Name']},
                {'Ignored': {'$exists': False}},
            ]}
            if 'Organization' in current:
                cond['$and'].append({
                    'UserOrganization': current['Organization'],
                })
            else:
                cond['$and'].append({'$or':[
                    {'UserOrganization': {'$exists': False}},
                    {'UserOrganization': ''},
                ]})
            update = {'$set': {'UserName': user_name}}
            if not user_org is None:
                update['$set']['UserOrganization'] = user_org
            else:
                update['$unset'] = {'UserOrganization': ''}
            res = db.Properties.update_many(cond, update)

            if res.modified_count > 0:
                logger.info('%d properties are modified (user-name, user-org)', res.modified_count)

    # ユーザーの名前を更新する
    update = {'$set': {'Name': user_name}}
    if not user_org is None:
        update['$set']['Organization'] = user_org
    else:
        update['$unset'] = {'Organization': ''}

    # 名前の更新
    db.Users.update_one({'_id': user_id}, update)

def transfer_properties(db, old_user, new_user, prop_id=None):
    """
    登録済権利の所有者を変更する
    """
    if old_user == new_user:
        return
    
    # 現在のユーザー情報を取得する
    old_db = db.Users.find_one({'_id': old_user})
    new_db = db.Users.find_one({'_id': new_user})

    logger.info('transfer properties from %s to %s', old_user, new_user)

    # 権利に関連付けたユーザーを更新
    for prop in db.Properties.find(
            {
                'User': old_user,
                'Ignored': {'$exists': False},
            }, {'_id':1,'Country':1, 'Law': 1,'RegistrationNumber':1,'UserName':1,'UserOrganization':1}):
        if not prop_id is None:
            if prop['_id'] != prop_id:
                continue
        if db.Properties.count_documents({
            'Country': prop['Country'],
            'Law': prop['Law'],
            'RegistrationNumber': prop['RegistrationNumber'],
            'User': new_user,
        }) > 0:
            logger.info("skip transfer, because %s/%s/%s is duplicated", prop['Country'], prop['Law'], prop['RegistrationNumber'])
        else:
            update = {'$set': {
                    'User': new_user,
                    'ModifiedTime': datetime.now(),
            }}
            # 名前の変更判定（旧アカウントと同一名が権利についていたら新アカウントの名前に付け替える）
            if 'Name' in new_db:
                sw_name = False
                if not 'UserName' in prop:
                    sw_name = True
                else:
                    if not old_db is None and 'Name' in old_db:
                        if prop['UserName'] == old_db['Name']:
                            sw_name = True
                    else:
                        sw_name = True
                if sw_name:
                    update['$set']['UserName'] = new_db['Name']
                    if 'Organization' in new_db:
                        update['$set']['UserOrganization'] = new_db['Organization']
                    else:
                        update['$unset'] = {'UserOrganization': ''}
            # 更新
            db.Properties.update_one(
                {'_id': prop['_id']},
                update
            )

def get_group_user_ids(db, my_user_id):
    """
    表示グループに属するユーザーIDのリストを取得する
    """
    ids = [my_user_id,]
    # メールアドレスの取得
    u1 = db.Users.find_one({'_id': my_user_id}, {'MailAddress':1, 'CcAddresses':1})
    if u1 is None or not 'MailAddress' in u1:
        return ids
    addr = u1['MailAddress']
    # 自身のアドレスを追加アドレスにしているユーザーを探す
    for u2 in db.Users.find({
        'Ignored': {'$exists': False},
        'CcAddresses': {'$in': [addr,]},
    }, {'_id':1}):
        if not u2['_id'] in ids:
            ids.append(u2['_id'])
    # 自身が追加アドレスにしているユーザーを探す
    if 'CcAddresses' in u1:
        for u2 in db.Users.find({
            'Ignored': {'$exists': False},
            'MailAddress': {'$in': u1['CcAddresses']},
        }, {'_id':1}):
            if not u2['_id'] in ids:
                ids.append(u2['_id'])
    # 収集したidを返す
    return ids

if __name__ == '__main__':
    tmp = ['あああああ一般社団法人', '一般社団法人いいいい']
    tmp2 = [check_jp_genmen(x) for x in tmp]
    print(tmp2)
    print(check_more_two(tmp2))
