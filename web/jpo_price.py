from datetime import datetime, date, timedelta
import math
import common_util

# see also: https://www.jpo.go.jp/tetuzuki/ryoukin/hyou.htm

# 特許
def patent(claims, year, year_to=0, exam_request_date=None, rate=[1.0, 1.0]):
    """
    特許の年金を計算する
    """
    assert claims > 0, 'invalid parametes'

    # 金額表の選択
    if exam_request_date and exam_request_date < datetime(2004, 4, 1):
        if year <= 3:
            base_price = 10300
            claim_price = 900
        elif year <= 6:
            base_price = 16100
            claim_price = 1300
        elif year <= 9:
            base_price = 32200
            claim_price = 2500
        else:
            base_price = 64400
            claim_price = 5000
    else:
        if year <= 3:
            base_price = 4300
            claim_price = 300
        elif year <= 6:
            base_price = 10300
            claim_price = 800
        elif year <= 9:
            base_price = 24800
            claim_price = 1900
        else:
            base_price = 59400
            claim_price = 4600

    # 計算
    price = base_price + (claims * claim_price)

    if year <= 10:
        # 減免の計算
        price = price / rate[1] * rate[0]
        # 10円未満は切り捨て（特許法施行令）
        price = math.floor(price / 10.0) * 10.0
    else:
        price = float(price)

    if year_to > year:
        price += patent(claims, year + 1, year_to=year_to, exam_request_date=exam_request_date, rate=rate)

    # 結果の料金表を返す
    return price

# 実用新案
def utility(claims, year, year_to=0):
    """
    実用新案登録の年金を計算する
    """
    # 料金表の選択
    if year <= 3:
        base_price = 2100
        claim_price = 100
    elif year <= 6:
        base_price = 6100
        claim_price = 300
    else:
        base_price = 18100
        claim_price = 900

    # 計算
    price = base_price + (claims * claim_price)
    price = float(price)

    if year_to > year:
        price += utility(claims, year + 1, year_to=year_to)

    # 結果と料金表を返す
    return price

# 意匠
def design(year, year_to=0):
    """
    意匠登録の年金を計算する
    """
    # 料金表の選択
    if year <= 3:
        price = 8500
    else:
        price = 16900
    price = float(price)
    if year_to > year:
        price += design(year + 1, year_to=year_to)
    return price

def trademark_renewal(years, classes):
    """
    商標の登録料を計算する
    """
    if years == 5:
        price = 22800
    elif years == 10:
        price = 43600
    else:
        raise ValueError('%d is a invalid years.' % years)
    # 計算して返す
    return float(classes * price)

def trademark_splitted(classes, investigated_date, reg_pay_date, reg_date, renew_pay_date=None):
    """
    商標登録の設定登録料を計算する
    :param investigated_date  登録査定日
    :param reg_date       設定登録日
    :param reg_pay_date   設定納付書の提出日
    :param renew_pay_date 更新登録申請書の提出日
    """
    # 登録料/更新料の判定
    is_renew = False
    pay_limit = None
    if not renew_pay_date is None:
        is_renew = True
    if (datetime.now().year - reg_date.year) > 8:
        is_renew = True
        # 直前の更新期限を計算
        n = 1
        while common_util.add_months(reg_date, n * 12 * 10) < datetime.now():
            n += 1
        n -= 1
        pay_limit = common_util.add_months(reg_date, n * 12 * 10)

    # 料金表の選択
    if (investigated_date >= datetime(2018, 4, 1) and investigated_date <= datetime(2022, 3, 1)) \
        or (reg_pay_date >= datetime(2017, 4, 1) and reg_pay_date <= datetime(2022, 3, 31)):
        # ・登録査定が2018年4月1日～2022年3月1日
        # ・初回の「設定納付書」が2017年4月1日～2022年3月31日
        # のいずれか
        price = 16400
    elif investigated_date >= datetime(2022, 3, 2) and reg_pay_date > datetime(2022, 4, 1):
        # 登録査定日が2022-03-02以降、且つ、設定納付書が2022-04-01以降
        price = 17200
    elif not renew_pay_date is None and renew_pay_date > datetime(2022, 4, 1) and reg_date.month >= 4 and reg_date.month <= 8:
        # 直近の「商標権存続期間更新登録申請書」が2022年4月1日以降、且つ、登録日が年度を問わず4月1日～8月31日
        price = 22800
    elif not renew_pay_date is None and ((renew_pay_date >= datetime(2018, 4, 1) and renew_pay_date <= datetime(2022, 3, 31)) \
            or (renew_pay_date >= datetime(2022, 4, 1) and \
                ((reg_date >= datetime(2016, 9, 1) and reg_date <= datetime(2017, 3, 31)) \
                or (reg_date >= datetime(2006, 9, 1) and reg_date <= datetime(2007, 3, 31)) \
                or (reg_date >= datetime(1996, 9, 1) and reg_date <= datetime(1997, 3, 31))))):
        # ・直近の「商標権存続期間更新登録申請書」が2018年4月1日～2022年3月31日
        # ・直近の「商標権存続期間更新登録申請書」が2022年4月1日以降で、かつ登録日が2016年9月1日～2017年3月31日、2006年9月1日～2007年3月31日、1996年9月1日～1997年3月31日、1986年9月1日～1997年3月31日
        # のいずれか
        price = 22600
    elif not is_renew and (investigated_date <= datetime(2022, 3, 1) or reg_pay_date < datetime(2022, 4, 1)):
        price = 16400
    elif is_renew and not renew_pay_date is None and renew_pay_date < datetime(2022, 4, 1):
        price = 22600
    elif is_renew and not pay_limit is None and pay_limit < datetime(2022, 4, 1):
        price = 22600
    elif is_renew:
        price = 22800
    else:
        price = 17200
    #else:
    #    raise ValueError('unexpected paramerter (登録査定=%s, 設定納付=%s, 登録=%s, 更新納付=%s)' % (investigated_date, reg_pay_date, reg_date, renew_pay_date))

    # 計算して単価とともに返す
    return float(classes * price)

# 防護標章（更新）
def defensive_trademark_renew(classes):
    """
    防護標章の登録料（更新）を計算する
    """
    assert classes > 0, 'invalid parameters'
    return float(classes * 37500)

if __name__ == '__main__':
    lx = [1, 2, 3]
    for l in lx:
        if l == 1:
            ex = [datetime(2008, 3, 31), datetime(2008, 4, 1)]
        else:
            ex = [None]
        for e in ex:
            if l == 3:
                cx = [1,]
            else:
                cx = [1, 3, 5]
            for c in cx:
                if l == 2:
                    m = 10
                else:
                    m = 20
                for y in range(1, m + 1):
                    if l == 1:
                        p = patent(c, y, e)
                    elif l == 2:
                        p = utility(c, y)
                    elif l == 3:
                        p = design(y)
                    else:
                        p = -1
                    print('\t'.join([
                        str(l),
                        str(c),
                        str(y),
                        e.strftime('%Y-%m-%d') if not e is None else '',
                        '\t'.join([str(x) for x in p]) if isinstance(p, tuple) else str(p),
                    ]))
