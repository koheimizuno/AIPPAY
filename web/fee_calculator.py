from datetime import datetime
import re
import math
import logging

import common_util
import jpo_price

_logger = logging.getLogger(__name__)

def calculate_fees(prop, lang, year_from=0, year_to=0, years=0, classes=None, additional=False):
    """
    料金の計算
    """
    # パラメーターのチェック
    if prop['Law'] in ('Patent', 'Utility', 'Design',):
        assert year_from > 0
        year_to = max(year_to, year_from)
    elif prop['Law'] in ('Trademark',):
        assert years in (5, 10,)

    # 明細
    fees = []

    # 変数の初期化
    discount = None

    # 登録番号等のテキスト表現 (明細用)
    if prop['Country'] == 'UNK':
        reg_txt = prop['CountryDescription']
    else:
        reg_txt = lang['Country'][prop['Country']]
    reg_txt += lang['Law'][prop['Law']]
    reg_txt += lang['Pages']['Request']['TEXT000122'].format(prop['RegistrationNumber'])
    if 'ManagementNumber' in prop and prop['ManagementNumber'] != '':
        reg_txt += '({}{})'.format(lang['Pages']['Request']['TEXT000266'], prop['ManagementNumber'])

    # 料金の計算
    if prop['Country'] == 'JP' and prop['Law'] == 'Patent':

        # 日本の特許
        rate = [1.0, 1.0,]
        discount = None

        if not 'NumberOfClaims' in prop:

            # 情報不足の場合は計算しない
            pass

        else:

            # 審査請求日がセットされていなければ便宜的な日付を用いる
            if not 'ExamClaimedDate' in prop:
                prop['ExamClaimedDate'] = datetime.now()

            # 減免の適用制度を判定
            if prop['ExamClaimedDate'] >= datetime(2019, 4, 1):
                if 'JpGenmen' in prop:
                    discount = prop['JpGenmen']
                    if discount == '10_4_i':
                        rate = [1.0, 3.0,]
                    elif discount == '10_4_ro':
                        rate = [1.0, 3.0,]
                    elif discount == '10_3_ro':
                        rate = [1.0, 2.0,]
                    else:
                        discount = None
                        rate = [1.0, 1.0,]
            else:
                if 'JpGenmen' in prop:
                    discount = prop['JpGenmen']
                    if discount == 'H25_98_66':
                        rate = [1.0, 3.0,]
                    else:
                        discount = None
                        rate = [1.0, 1.0,]

            # 10年分以前でなければ減免はない
            if year_from > 10:
                discount = None
                rate = [1.0, 1.0,]

            # 計算
            if additional:
                fee = jpo_price.patent(prop['NumberOfClaims'], year_from,
                    exam_request_date=prop['ExamClaimedDate'], rate=rate) * 2.0
                if year_to > year_from:
                    fee += jpo_price.patent(prop['NumberOfClaims'], year_from + 1, year_to=year_to,
                        exam_request_date=prop['ExamClaimedDate'], rate=rate)
            else:
                fee = jpo_price.patent(prop['NumberOfClaims'], year_from, year_to=year_to,
                    exam_request_date=prop['ExamClaimedDate'], rate=rate)

            # 明細の生成
            p = [reg_txt,]
            p.append(lang['Pages']['Request']['TEXT000126'].format(prop['NumberOfClaims']))
            if year_from != year_to:
                p.append(lang['Pages']['Request']['TEXT000127'].format('%d-%d' % (year_from, year_to)))
            else:
                p.append(lang['Pages']['Request']['TEXT000127'].format(year_to))
            if additional:
                p.append(lang['Pages']['Request']['TEXT000128'])
            if discount:
                p.append(lang['Pages']['Request']['TEXT000168'])
            sjt = ' '.join(p)

            temp = {
                'Kind': 'Office',
                'Fee': fee,
                'Currency': 'JPY',
                'Subject': sjt,
                'AdditionalPayment': additional,
            }

            if discount:
                temp['Discount'] = discount
                temp['DiscountRate'] = rate

            fees.append(temp)

    elif prop['Country'] == 'JP' and prop['Law'] == 'Utility':

        # 日本の実用新案
        if not 'NumberOfClaims' in prop:

            # 審査請求日が設定されていなければ計算しない
            pass

        else:

            # 計算
            if additional:
                fee = jpo_price.utility(prop['NumberOfClaims'], year_from) * 2.0
                if year_to > year_from:
                    fee += jpo_price.utility(prop['NumberOfClaims'], year_from + 1, year_to=year_to)
            else:
                fee = jpo_price.utility(prop['NumberOfClaims'], year_from, year_to=year_to)

            # 明細の生成
            p = [reg_txt,]
            p.append(lang['Pages']['Request']['TEXT000126'].format(prop['NumberOfClaims']))
            if year_from != year_to:
                p.append(lang['Pages']['Request']['TEXT000127'].format('%d-%d' % (year_from, year_to)))
            else:
                p.append(lang['Pages']['Request']['TEXT000127'].format(year_to))
            if additional:
                p.append(lang['Pages']['Request']['TEXT000128'])
            sjt = ' '.join(p)

            temp = {
                'Kind': 'Office',
                'Fee': fee,
                'Currency': 'JPY',
                'Subject': sjt,
                'AdditionalPayment': additional,
            }

            fees.append(temp)

    elif prop['Country'] == 'JP' and prop['Law'] == 'Design':

        # 日本の意匠
        if additional:
            fee = jpo_price.design(year_from) * 2.0
            if year_to > year_from:
                fee += jpo_price.design(year_from + 1, year_to=year_to)
        else:
            fee = jpo_price.design(year_from, year_to=year_to)

        # 明細の生成
        p = [reg_txt,]
        if 'NumberOfClaims' in prop:
            p.append(lang['Pages']['Request']['TEXT000126'].format(prop['NumberOfClaims']))
        if year_from != year_to:
            p.append(lang['Pages']['Request']['TEXT000127'].format('%d-%d' % (year_from, year_to)))
        else:
            p.append(lang['Pages']['Request']['TEXT000127'].format(year_to))
        if additional:
            p.append(lang['Pages']['Request']['TEXT000128'])
        sjt = ' '.join(p)

        temp = {
            'Kind': 'Office',
            'Fee': fee,
            'Currency': 'JPY',
            'Subject': sjt,
            'AdditionalPayment': additional,
        }

        fees.append(temp)

    elif prop['Country'] == 'JP' and prop['Law'] == 'Trademark':

        # 日本の商標
        if classes is None:
            classes = 0

        # パラメーターの確認 → 省略時は権利情報から取得
        if classes == 0:
            if 'Cart' in prop and 'Classes' in prop['Cart']:
                classes = len(prop['Cart']['Classes'])
            elif 'Classes' in prop:
                classes = len(prop['Classes'])

        # 情報不足の場合は計算しない
        if classes < 1 or not 'RegistrationDate' in prop or not 'PaidYears' in prop:

            pass

        else:

            # 防護標章判定
            if common_util.in_and_true(prop, 'Defensive'):

                # 防護標章の更新登録料の計算
                fee = jpo_price.defensive_trademark_renew(classes)

            elif prop['PaidYears'] < 10:

                # 分納後期の登録料の計算

                # パラメーターとなる日付の取得
                reg_date = prop['RegistrationDate'] if 'RegistrationDate' in prop else None
                reg_pay_date = prop['RegistrationPaymentDate'] if 'RegistrationPaymentDate' in prop else None
                investigated_date = prop['RegistrationInvestigatedDate'] if 'RegistrationInvestigatedDate' in prop else None
                renew_pay_date = prop['RenewPaymentDate'] if 'RenewPaymentDate' in prop else None

                if reg_pay_date is None:
                    _logger.warning('%s-%s does not have RegistrationPaymentDate', prop['Law'], prop['RegistrationNumber'])
                    reg_pay_date = reg_date
                if investigated_date is None:
                    _logger.warning('%s-%s does not have RegistrationInvestigatedDate', prop['Law'], prop['RegistrationNumber'])
                    investigated_date = reg_pay_date

                # 計算
                fee = jpo_price.trademark_splitted(classes, investigated_date, reg_pay_date, reg_date, renew_pay_date)

            else:

                # 通常の更新登録料の計算
                fee = jpo_price.trademark_renewal(years, classes)

            # 追納加算
            if additional:
                fee *= 2

            # 明細の生成
            p = [reg_txt,]
            p.append(lang['Pages']['Request']['TEXT000130'].format(classes))
            p.append(lang['Pages']['Request']['TEXT000129'].format(years))
            if additional:
                p.append(lang['Pages']['Request']['TEXT000128'])
            sjt = ' '.join(p)

            temp = {
                'Kind': 'Office',
                'Fee': fee,
                'Currency': 'JPY',
                'Subject': sjt,
                'AdditionalPayment': additional,
            }
            fees.append(temp)

            # 区分減かつ分割後半の場合は+1000円
            if prop['PaidYears'] == 5 and years == 5:
                if classes < len(prop['Classes']):
                    p = [reg_txt,]
                    p.append(lang['Pages']['Request']['TEXT000131'].format(len(prop['Classes']) - classes))
                    sjt = ' '.join(p)
                    temp = {
                        'Kind': 'Office',
                        'Fee': 1000,
                        'Currency': 'JPY',
                        'Subject': sjt,
                    }
                    fees.append(temp)

    # 事務所手数料
    fee = 5000.0

    if prop['Law'] == 'Trademark':
        if prop['PaidYears'] == 10:
            sjt = lang['Pages']['Request']['TEXT000124'].format(reg_txt)
        else:
            sjt = lang['Pages']['Request']['TEXT000123'].format(reg_txt)
    elif prop['Country'] != 'JP':
        sjt = lang['Pages']['Request']['TEXT000124'].format(reg_txt)
    else:
        sjt = lang['Pages']['Request']['TEXT000123'].format(reg_txt)

    temp = {
        'Kind': 'Agent',
        'Fee': fee,
        'Currency': 'JPY',
        'Subject': sjt,
    }
    fees.append(temp)

    # 商標で区分の削除がある場合は+10,000円
    if fee > 0 and prop['Country'] == 'JP' and prop['Law'] == 'Trademark' and 'Classes' in prop:
        if classes < len(prop['Classes']):
            temp = {
                'Kind': 'Agent',
                'Fee': 10000.0,
                'Currency': 'JPY',
                'Subject': lang['Pages']['Request']['TEXT000125'].format(reg_txt),
            }
            fees.append(temp)

    # 減免がある場合は3000円を加算
    if len([x for x in fees if 'Discount' in x]) > 0:
        temp = {
            'Kind': 'Agent',
            'Fee': 3000.0,
            'Currency': 'JPY',
            'Subject': lang['Pages']['Request']['TEXT000200'],
        }
        fees.append(temp)

    # 日本円の事務所手数料に消費税を設定
    for x in fees:
        if x['Currency'] == 'JPY' and x['Kind'] == 'Agent':
            rate = 0.1
            x['TaxRate'] = rate
            x['TaxRateText'] = '{:.2f}%'.format(rate * 100)

    # 計算結果を返す
    return fees

def total_fee_list(fee_list, kind, field='Fee'):
    """
    料金明細を集計する
    """
    cur = None
    total = 0.0
    tax_rate = 0.0
    for x in fee_list:
        if not field in x:
            continue
        if x['Kind'] != kind:
            continue
        # 通貨の混在はないはず
        if cur is None:
            cur = x['Currency']
        assert cur == x['Currency']
        # 税率の混在もないはず
        if 'TaxRate' in x:
            assert tax_rate == 0.0 or tax_rate == x['TaxRate']
            tax_rate = x['TaxRate']
        else:
            assert tax_rate == 0.0
        # 合計加算
        total += x[field]
    return total, cur, tax_rate
