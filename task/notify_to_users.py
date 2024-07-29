import logging
import io
import re
from datetime import datetime, timedelta
from pathlib import Path
import traceback
from bson.objectid import ObjectId

from enums import RequestStatus
from database import DbClient
import mail
import common_util
import language
from local_config import Config
import patent_reference
import direct_link

conf = Config()
log_file = None

if conf['log']['directory']:
    log_file = Path(conf['log']['directory']) / 'notify_to_users.log'

logging.basicConfig(
    filename=str(log_file) if log_file else None,
    level=logging.INFO if log_file else logging.DEBUG,
    format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s'
)

logger = logging.getLogger('notify_to_users')

def make_url(path=''):
    """
    URLの生成
    """
    url = conf['web']['base_url']
    if path is None:
        return url
    elif not isinstance(path, str):
        path = str(path)
    if path == '':
        return url
    if not path.startswith('/'):
        path = '/' + path
    return url + path

def preamble(user, lang):
    """
    メールの宛名表現を生成する
    """
    with io.StringIO() as buff:

        # 組織
        if 'Organization' in user:
            buff.write('%s\n' % user['Organization'])

        # 名前
        s = '%s %s %s' % (lang['Common']['NamePrefix'], user['Name'], lang['Common']['NameSuffix'])
        buff.write(s.strip())

        return buff.getvalue().strip()

def about_next_procedure(db, user, lang):
    """
    次回依頼期限についての通知を行う
    """
    # 通知基準日
    today = common_util.get_today()

    # 次回期限が6ヶ月以内のものを抽出する
    month_six = after_month(today, 6)
    month_three = after_month(today, 3)

    # 対象権利の抽出
    props = db.Properties.find({ '$and':[
            {'User': user['_id']},
            {'Country': {'$in': ['JP',]}},
            {'Ignored': {'$exists': False}},
            {'Abandoned': {'$exists': False}},
            {'$or':[
                {
                    'Law': 'Trademark',
                    'NextProcedureLimit': {'$lte': month_six},
                },
                {
                    'Law': {'$in': ['Patent', 'Utility', 'Design',]},
                    'NextProcedureLimit': {'$lte': month_three},
                },
            ]},
            {'NextProcedureLimit': {'$gte': today}},
            {'$or': [
                {'Silent': {'$exists': False}},
                {'Silent': False},
            ]},
            {'$or': [
                {'MailPendingDate': {'$exists': False}},
                {'MailPendingDate': {'$lte': today}},
            ]},
    ]})

    # 通知条件日当日のみ対象とする
    props = list(props)
    props = [x for x in props if today in get_checkpoints(x['NextProcedureLimit'])]

    def check_active_request(prop_id):
        """
        依頼済み判定
        """
        req_cnt = db.Requests.count_documents({'$and':[
            {'Properties': {'$elemMatch': {
                'Property': prop_id,
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
            logger.info('Property[%s] has active request.', prop_id)
            return True
        else:
            return False

    # 依頼済の権利を除外する
    props = [x for x in props if not check_active_request(x['_id'])]
    
    # 通知対象がなければ終了
    if len(props) == 0:
        return

    # 通知対象がなければ終了
    if len(props) == 0:
        return

    def refer_to_db(prop):
        """
        特許庁DB照会を実施
        :return 通知の要否(True->要, False->不要(になった))
        """
        # 処理前の次回期限を保存
        next_limit = prop['NextProcedureLimit']

        # 特許情報の検索サービスの照会
        data, message = patent_reference.refer(
            prop['Country'],
            prop['Law'],
            prop['RegistrationNumber'],
            'registration',
            lang)

        # 取得できず -> とりあえず通知に関してはそのまま処理
        if data is None:
            logger.warning('Property[%s,%s,%s,%s] cannot be updated by Office DB.', prop['_id'], prop['Country'], prop['Law'], prop['RegistrationNumber'])
            return True

        # 取得した情報でデータベースを更新する
        data['Id'] = prop['_id']
        _, _, _, _ = db.update_prop(data, prop['User'], update_abandonment=True, lang=lang)

        # 次回手続期限の取得
        p = db.Properties.find_one({'_id': prop['_id']}, {'NextProcedureLimit':1})
        if p is None or not 'NextProcedureLimit' in p:
            # 次回手続期限がなくなっていたら通知をスキップ
            logger.info('The next limit is removed, because Patent Office Data is updated. (%s,%s,%s,%s)', prop['_id'], prop['Country'], prop['Law'], prop['RegistrationNumber'])
            return False
        if p['NextProcedureLimit'] > next_limit:
            # 次回手続期限が更新されていたら通知をスキップ
            logger.info('The next limit is updateed, because Patent Office Data is updated. (%s,%s,%s,%s)', prop['_id'], prop['Country'], prop['Law'], prop['RegistrationNumber'])
            return False

        # 期限更新等なければ通知する        
        return True

    # 特許庁DBの照会と再フィルター
    props = [x for x in props if refer_to_db(x)]

    # 通知対象がなければ終了
    if len(props) == 0:
        return

    # 対象の再取得（料金計算等を含む）
    props = [db.get_prop_info(x['_id'], lang, date_to_str=False) for x in props]

    # ユーザー名の付与
    def set_user_name(prop):
        prop_id = ObjectId(prop['_id'])
        pdb = db.Properties.find_one({'_id': prop_id})
        if not pdb is None:
            if 'UserName' in pdb:
                prop['UserName'] = pdb['UserName']
                if 'Organization' in pdb:
                    prop['UserOrganization'] = pdb['Organization']
                if 'UserOrganization' in pdb:
                    prop['UserOrganization'] = pdb['UserOrganization']
                return prop
            reqs = db.Requests.find({
                'Properties': {'$elemMatch': {'Property': prop_id}}
            })
            reqs = list(reqs)
            if len(reqs) > 0:
                reqs = sorted(reqs, key=lambda x: x['RequestedTime'], reverse=True)
                if 'UserName' in reqs[0]:
                    prop['UserName'] = reqs[0]['UserName']
                    if 'Organization' in reqs[0]:
                        prop['UserOrganization'] = pdb['Organization']
                    if 'UserOrganization' in reqs[0]:
                        prop['UserOrganization'] = pdb['UserOrganization']
                    return prop
        if 'Name' in user:
            prop['UserName'] = user['Name']
        if 'Organization' in user:
            prop['UserOrganization'] = user['Organization']
        return prop
    props = [set_user_name(prop) for prop in props]

    # 並べ替え
    props = sorted(props, key=lambda x: x['NextProcedureLimit'])

    # 通貨情報の取得
    currencies = common_util.get_currencies(db)

    # 次回通知日（通知抑制日）の計算
    for prop in props:

        # 通知タイミングと次回通知日の判定
        ns = get_checkpoints(prop['NextProcedureLimit'])
        i = len(ns)
        for j in range(len(ns)):
            if ns[j] <= today:
                i = j
                break
        if i >= len(ns):
            continue
        timing = None
        if i <= 1:
            timing = 'd10'
        elif i == 2:
            timing = 'm1'
        elif i == 3:
            timing = 'm3'
        elif i == 4:
            timing = 'm6'
        else:
            continue
        ns_min = min([x for x in ns if x > today])
        if not ns_min is None:
            prop['MailPendingDate'] = ns_min

        # 件名の生成
        subject = lang['Mail']['MAIL0004']['TEXT000041'].format(lang.format_date(prop['NextProcedureLimit'], ignore_year=True))
        if 'ManagementNumber' in prop:
            subject += '{}{}/'.format(
                lang['Pages']['Request']['TEXT000266'],
                prop['ManagementNumber']
            )
        subject += lang.format_reg_number(prop['Country'], prop['Law'], prop['RegistrationNumber'])
        if 'Subject' in prop:
            subject += '({})'.format(prop['Subject'])
        subject += lang['Mail']['MAIL0004']['TEXT000042']
        if prop['Country'] == 'JP':
            if prop['Law'] == 'Trademark':
                if not 'PaidYears' in prop or prop['PaidYears'] == 10:
                    subject += lang['Mail']['MAIL0004']['TEXT000043']
                else:
                    subject += lang['Mail']['MAIL0004']['TEXT000044']
            else:
                subject += lang['Mail']['MAIL0004']['TEXT000045'].format(prop['PaidYears'] + 1)
        else:
            subject += lang['Mail']['MAIL0004']['TEXT000046']
        subject += lang['Mail']['MAIL0004']['TEXT000047']
        d_m, d_d = diff_months_or_days(today, prop['NextProcedureLimit'])
        if d_d == 'd':
            subject += lang['Mail']['MAIL0004']['TEXT000048'].format(d_m)
        else:
            subject += lang['Mail']['MAIL0004']['TEXT000049'].format(d_m)

        # 通知文の生成
        with io.StringIO() as body:

            # 区切り線
            hr = '-' * 72
            hr += '\n\n'

            # ユーザー向けメールの前段
            user_name = ''
            if 'UserName' in prop:
                user_name = prop['UserName']
            if 'UserOrganization' in prop:
                user_name = prop['UserOrganization'] + '\n' + user_name
                user_name = user_name.strip()
            body.write(lang['Mail']['MAIL0004']['TEXT000001'].format(user_name))
            body.write('\n\n')

            body.write(lang['Mail']['MAIL0004']['TEXT000002'])
            body.write('\n')
            body.write(lang['Mail']['MAIL0004']['TEXT000003'])
            body.write('\n')
            body.write(lang['Mail']['MAIL0004']['TEXT000017'])
            body.write('\n\n')

            body.write(hr)

            # 書誌的事項
            items = []

            items.append([lang['Mail']['MAIL0004']['TEXT000004'], prop['CountryDescription']])
            s = lang.format_reg_number(prop['Country'], prop['Law'], prop['RegistrationNumber'])
            if 'RegistrationDate' in prop:
                s += ' (%s %s)' % (lang['Mail']['MAIL0004']['TEXT000029'], lang.format_date(prop['RegistrationDate']))
            items.append([lang['Mail']['MAIL0004']['TEXT000006'], s])
            if 'ApplicationNumber' in prop:
                s = lang.format_app_number(prop['Country'], prop['Law'], prop['ApplicationNumber'])
                if 'ApplicationDate' in prop:
                    s += ' (%s %s)' % (lang['Mail']['MAIL0004']['TEXT000031'], lang.format_date(prop['ApplicationDate']))
                items.append([lang['Mail']['MAIL0004']['TEXT000030'], s])
            if 'ManagementNumber' in prop:
                items.append([lang['Mail']['MAIL0004']['TEXT000016'], prop['ManagementNumber']])
            if 'Subject' in prop:
                items.append([lang['Mail']['MAIL0004']['TEXT000007'], prop['Subject']])
            if 'Holders' in prop:
                holder_names = [x['Name'] for x in prop['Holders'] if 'Name' in x]
                if len(holder_names) > 0:
                    items.append([lang['Mail']['MAIL0004']['TEXT000052'], ', '.join(holder_names)])
            if prop['Country'] == 'JP' and prop['Law'] == 'Trademark' and 'PaidYears' in prop and prop['PaidYears'] == 10:
                # 商標の場合は更新期間を表示する
                items.append([lang['Mail']['MAIL0004']['TEXT000018'], '%s - %s' % (lang.format_date(common_util.add_months(prop['NextProcedureLimit'], -6)), lang.format_date(prop['NextProcedureLimit']))])
            else:
                items.append([lang['Mail']['MAIL0004']['TEXT000008'], lang.format_date(prop['NextProcedureLimit'])])
            if 'NumberOfClaims' in prop:
                items.append([lang['Mail']['MAIL0004']['TEXT000009'], str(prop['NumberOfClaims'])])
            if 'Classes' in prop:
                items.append([lang['Mail']['MAIL0004']['TEXT000010'], str(prop['Classes'])])

            # 次回料金
            tmp = []
            v = 0.0
            def disp_cur(cur):
                if lang.name == 'ja' and cur == 'JPY':
                    return '円'
                else:
                    return cur            
            if 'NextOfficialFee' in prop:
                s = '%s%s' % (prop['NextOfficialFee'], disp_cur(prop['Currency']))
                v = float(prop['NextOfficialFee'].replace(',', ''))
                if 'NextOfficialFee_Exchanged' in prop:
                    s += " (%s%s)" % (prop['NextOfficialFee_Exchanged'], disp_cur(prop['ExchangedCurrency']))
                    v = float(prop['NextOfficialFee_Exchanged'].replace(',', ''))
                if common_util.in_and_true(prop, 'ApplyDiscount'):
                    t = lang['Mail']['MAIL0004']['TEXT000051']
                else:
                    t = ''
                tmp.append([lang['Mail']['MAIL0004']['TEXT000011'], s, t])
            
            if 'NextAgentFee' in prop:
                # 消費税を加算
                t = float(prop['NextAgentFee'].replace(',', ''))
                t *= (1.0 + 0.10)
                t = common_util.fit_currency_precision(t, currencies[prop['AgentFeeCurrency']]['Precision'])
                t = currencies[prop['AgentFeeCurrency']]['Format'].format(t)
                s = '%s%s' % (t, disp_cur(prop['AgentFeeCurrency']))
                v += float(t.replace(',', ''))

                tmp.append([lang['Mail']['MAIL0004']['TEXT000012'], s, ''])
            
            if v > 0.0:
                v = common_util.fit_currency_precision(v, currencies[prop['AgentFeeCurrency']]['Precision'])
                v = currencies[prop['AgentFeeCurrency']]['Format'].format(v)
                s = '%s%s' % (v, disp_cur(prop['AgentFeeCurrency']))
                tmp.append([lang['Mail']['MAIL0004']['TEXT000019'], s, ''])

            # 右揃え処理
            if len(tmp) > 0:
                w = max([common_util.text_width(x[1]) for x in tmp])
                for i in range(len(tmp)):
                    x = common_util.text_width(tmp[i][1])
                    if x < w:
                        tmp[i][1] = (' ' * int((w - x) * 2)) + tmp[i][1]
                # アイテムリストに追加
                items += tmp
                tmp = None

            # 見出しの幅を統一してメール本文に掲載
            w = max([common_util.text_width(x[0]) for x in items])
            for item in items:
                # 見出しの幅を統一する
                x = w - common_util.text_width(item[0])
                s = item[0]
                if x > 0:
                    s += "　" * int(x)
                if len(item) > 2:
                    body.write('%s  %s %s\n' % (s, item[1], item[2]))
                else:
                    body.write('%s  %s\n' % (s, item[1],))
                
            body.write('\n')

            # 直接操作用のリンク
            body.write(lang['Mail']['MAIL0004']['TEXT000013'])
            body.write('\n')
            body.write(direct_link.get_link('/d/req', prop['UserId'], prop['Id']))
            body.write('\n\n')

            if 'SourceURL' in prop:
                body.write(lang['Mail']['MAIL0004']['TEXT000014'])
                body.write('\n')
                body.write(prop['SourceURL'])
                body.write('\n\n')

            body.write(lang['Mail']['MAIL0004']['TEXT000015'])
            body.write('\n')
            body.write(direct_link.get_link('/d/silent', prop['UserId'], prop['Id']))
            body.write('\n\n')

            # メールのフッター
            body.write(lang.mail_footer())

            # ユーザー向けメールの送信
            to_addr, cc_addr, bcc_addr = db.get_mail_addresses(user['_id'])

            mail.send_mail(
                subject,
                body.getvalue(),
                to=to_addr, cc=cc_addr, bcc=bcc_addr,
            )

            # 通知日の記録
            q = {'$set': {
                'NotifiedDate': today,
                'NotifiedDateTime': datetime.now(),
            }, '$push': {
                'NotifiedDates': {
                    'Timing': timing,
                    'Date': today,
                }
            }}
            if 'MailPendingDate' in prop:
                q['$set']['MailPendingDate'] = prop['MailPendingDate']
            else:
                q['$unset'] = {'MailPendingDate': ''}
            db.Properties.update_one({'_id': ObjectId(prop['_id'])}, q)

def diff_months_or_days(d1, d2):
    """
    月 or 日の差を求める
    """
    m = 0
    while common_util.add_months(d2, -1 * m) >= d1:
        m += 1
    if m < 1:
        return (d2 - d1).days, 'd'
    elif m == 1:
        d = (d2 - d1).days
        if d > 20:
            return 1, 'm'
        else:
            return d, 'd'
    else:
        if d1.day == d2.day:
            return m - 1, 'm'
        else:
            return m, 'm'

def notify_all(db):
    """
    全ユーザーに対して必要な通知を行う
    """
    for user in db.Users.find({'Ignored': {'$exists': False}}):

        # 言語設定
        lang_code = 'ja'
        if 'Language' in user:
            lang_code = user['Language']
        lang = language.get_dictionary(lang_code)

        # 次回手続期限の警告
        about_next_procedure(db, user, lang)

def after_month(basis, months):
    """
    ○ヶ月前
    """
    # 月末日判定
    last_of_month = False
    tommorow = basis + timedelta(days=1)
    if tommorow.month != basis.month:
        last_of_month = True

    # ○か月後
    x = common_util.add_months(basis, months)

    # 月末日起点の場合は計算結果も月末日にする
    if last_of_month:
        a = x.month
        while x.month == a:
            x += timedelta(days=1)
        x -= timedelta(days=1)

    # 計算した日付を返す
    return x

def get_checkpoints(d):
    """
    """
    points = []

    # 6, 3, 1ヶ月前
    points.append(common_util.add_months(d, -6))
    points.append(common_util.add_months(d, -3))
    points.append(common_util.add_months(d, -1))

    # 10日前
    points.append(d - timedelta(days=10))

    # 当日の翌日
    points.append(d + timedelta(days=1))

    # 生成したリストを返す
    return sorted(points, reverse=True)

if __name__ == '__main__':

    # 処理
    with DbClient() as db:
        notify_all(db)
