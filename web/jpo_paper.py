import re
import mojimoji
import logging
import common_util

logger = logging.getLogger(__name__)

def create_payment_paper(req, prop):
    """
    納付書のHTMLを生成する
    """
    doc = []

    # TODO: 防護標章対応

    # 書類名
    if prop['Law'] == 'Patent':
        doc.append('【書類名】　特許料納付書')
    elif prop['Law'] == 'Utility':
        doc.append('【書類名】　実用新案登録料納付書')
    elif prop['Law'] == 'Design':
        doc.append('【書類名】　意匠登録料納付書')
    elif prop['Law'] == 'Trademark':
        if 'Defensive' in prop and prop['Defensive']:
            doc.append('【書類名】　防護標章登録に基づく権利存続期間更新登録願')
        if req['Years'] == 5 and req['PaidYears'] == 5:
            doc.append('【書類名】　商標登録料納付書')
        else:
            doc.append('【書類名】　商標権存続期間更新登録申請書')
    else:
        raise Exception('law %d is not supported' % prop['Law'])

    # 宛先（固定）
    doc.append('【あて先】　特許庁長官　殿')

    # 登録番号
    reg_num = prop['RegistrationNumber']
    reg_num = re.sub(r'^0+', '', reg_num)

    if prop['Law'] == 'Trademark' and 'Defensive' in prop and prop['Defensive']:
        m = re.match(r'(.*)[\-/.](.*)', reg_num)
        reg_num = '商標登録第{}号の防護標章登録第{}号'.format(mojimoji.han_to_zen(m.group(1)), mojimoji.han_to_zen(m.group(2)))
        doc.append('【防護標章登録の登録番号】　%s' % reg_num)
    else:
        reg_num = mojimoji.han_to_zen(reg_num)
        if prop['Law'] == 'Patent':
            doc.append('【特許番号】　特許第%s号' % reg_num)
        elif prop['Law'] == 'Utility':
            doc.append('【実用新案登録番号】　実用新案登録第%s号' % reg_num)
        elif prop['Law'] == 'Design':
            doc.append('【意匠登録番号】　意匠登録第%s号' % reg_num)
        elif prop['Law'] == 'Trademark':
            doc.append('【商標登録番号】　商標登録第%s号' % reg_num)

    # 法区分ごとの処理
    if prop['Law'] != 'Trademark' or (req['Years'] == 5 and req['PaidYears'] == 5):

        # ※特・実・意または商標の分納後期

        # 請求項の数
        if prop['Law'] == 'Patent' or prop['Law'] == 'Utility':
            doc.append('【請求項の数】　%s' % mojimoji.han_to_zen(str(req['NumberOfClaims'])))

        # 指定商品・役務の区分
        if prop['Law'] == 'Trademark':
            if 'Classes' in req:
                doc.append('【商品及び役務の区分の数】　%s' % mojimoji.han_to_zen(str(len(req['Classes']))))
            else:
                doc.append('【商品及び役務の区分の数】　%s' % mojimoji.han_to_zen(str(req['NumberOfClasses'])))

        # 権利者
        for holder in prop['Holders']:
            if not 'Name' in holder:
                continue
            if prop['Law'] == 'Patent':
                doc.append('【特許権者】')
            elif prop['Law'] == 'Utility':
                doc.append('【実用新案権者】')
            elif prop['Law'] == 'Design':
                doc.append('【意匠権者】')
            elif prop['Law'] == 'Trademark':
                doc.append('【商標権者】')
            # 減免の場合は識別番号
            fees = [x for x in req['FeeList'] if 'Discount' in x and x['Discount'] in ('10_4_i', '10_4_ro', '10_3_ro',)]
            if len(fees) > 0:
                if 'Id' in holder:
                    doc.append('　【識別番号】　%s' % mojimoji.han_to_zen(holder['Id']))
                else:
                    # 識別番号を取得できていない場合は住所又は居所の欄だけ作る
                    doc.append('　【住所又は居所】')
            doc.append('　【氏名又は名称】　%s' % mojimoji.han_to_zen(holder['Name']))

        # 納付者
        doc.append('【納付者】')
        doc.append('　【識別番号】　　　　　１１０００４４３９')
        doc.append('　【氏名又は名称】　　　ＡＩＰＰＡＹ弁理士法人')
        doc.append('　【代表者】　　　　　　山下　隆志')
        doc.append('　【電話番号】　　　　　０９０―９８１７―２９２４')
        doc.append('　【ファクシミリ番号】　０６―６５３７―１９７４')
        # 納付年分
        if prop['Law'] != 'Trademark':
            if req['YearFrom'] == req['YearTo']:
                doc.append('【納付年分】　第%s年分' % mojimoji.han_to_zen(str(req['YearFrom'])))
            else:
                doc.append('【納付年分】　第%s年分から第%s年分' % (mojimoji.han_to_zen(str(req['YearFrom'])),
                    mojimoji.han_to_zen(str(req['YearTo']))))

        # 追納
        fees = [x for x in req['FeeList'] if 'AdditionalPayment' in x and x['AdditionalPayment']]
        if len(fees) > 0:
            pass
            # 割増特許料の表示は不要
            # See: https://www.jpo.go.jp/system/process/toroku/youshiki_kisaihouhou.html#1_2
            #if prop['Law'] == 'Patent':
            #    doc.append('【特許料等に関する特記事項】')
            #    doc.append('特許法第１１２条の２第１項の規定による特許料及び割増特許料の追納')
            #elif prop['Law'] == 'Utility':
            #    doc.append('【特許料等に関する特記事項】')
            #    doc.append('実用新案法第33条の2第1項の規定による登録料及び割増登録料の追納')
            #elif prop['Law'] == 'Design':
            #    doc.append('【特許料等に関する特記事項】')
            #    doc.append('意匠法第４４条の２第１項の規定による登録料及び割増登録料の追納')
            #elif prop['Law'] == 'Trademark':
            #    doc.append('【特許料等に関する特記事項】')
            #    doc.append('商標法第４１条の３の規定による後期分割登録料及び割増登録料の追納 ')

    else:

        # ※商標

        # 区分（削除がある場合にのみ表示）
        if 'Classes' in req:
            if len(req['Classes']) < len(req['OriginalClasses']):
                if 'Defensive' in prop and prop['Defensive']:
                    # 防護標章の書き方
                    doc.append('【商品又は役務の区分】')
                    for c in req['Classes']:
                        doc.append('　【第%s類】' % mojimoji.han_to_zen(c))
                else:
                    # 通常の書き方
                    temp = [int(x) for x in req['Classes']]
                    temp = ['第%s類' % mojimoji.han_to_zen(str(x)) for x in temp]
                    doc.append('【商品及び役務の区分】　%s' % '、'.join(temp))

        # 更新登録申請人
        if 'Holders' in prop:
            for holder in prop['Holders']:
                doc.append('【更新登録%s人】' % ('出願' if 'Defensive' in prop and prop['Defensive'] else '申請'))
                if 'Id' in holder:
                    doc.append('　【識別番号】 %s' % mojimoji.han_to_zen(holder['Id']))
                else:
                    doc.append('　【住所又は居所】')
                doc.append('　【氏名又は名称】　%s' % mojimoji.han_to_zen(holder['Name']))
        else:
            doc.append('【更新登録申請人】')
            doc.append('　【識別番号】')
            doc.append('　【住所又は居所】')
            doc.append('　【氏名又は名称】')

        # 納付者
        doc.append('【代理人】')
        doc.append('　【識別番号】　　　　　１１０００４４３９')
        if 'Defensive' in prop and prop['Defensive']:
            doc.append('　【弁理士】')
        doc.append('　【氏名又は名称】　　　ＡＩＰＰＡＹ弁理士法人')
        doc.append('　【代表者】　　　　　　山下　隆志')
        doc.append('　【電話番号】　　　　　０９０―９８１７―２９２４')
        doc.append('　【ファクシミリ番号】　０６―６５３７―１９７４')

        # 追納
        # See: https://www.jpo.go.jp/system/process/toroku/youshiki_kisaihouhou.html#4_4
        #if 'AdditionalPeriod' in req and req['AdditionalPeriod']:
        #    doc.append('【特許料等に関する特記事項】')
        #    doc.append('商標法第２１条第１項の規定による商標権の存続期間の更新登録の申請')

    # 減免の表示
    fees = [x for x in req['FeeList'] if 'Discount' in x]
    if len(fees) > 0:
        # システム互換対応
        if fees[0]['Discount'] == '10_4_i':
            if 'Holders' in prop:
                tmp = [x['Name'] for x in prop['Holders'] if 'Name' in x]
                if len(tmp) > 0:
                    tmp = [common_util.check_jp_genmen(x) for x in tmp]
                    if not tmp[0] is None and tmp[0] == '10_4_ro':
                        logger.warning('genmen kubun changed automatically. (%s -> 10_4_ro)', fees[0]['Discount'])
                        fees[0]['Discount'] = '10_4_ro'
        # 表示判定
        if fees[0]['Discount'] == 'H25_98_66':
            doc.append('【特許料等に関する特記事項】')
            doc.append('産業競争力強化法第６６条第１項の規定による特許料の２／３軽減')
        elif fees[0]['Discount'] == '10_4_i':
            doc.append('【特許料等に関する特記事項】')
            doc.append('特許法施行令第１０条第４号イに掲げる者に該当する特許権者である。減免申請書の提出を省略する。')
        elif fees[0]['Discount'] == '10_4_ro':
            doc.append('【特許料等に関する特記事項】')
            doc.append('特許法施行令第１０条第４号ロに掲げる者に該当する特許権者である。減免申請書の提出を省略する。')
        elif fees[0]['Discount'] == '10_3_ro':
            doc.append('【特許料等に関する特記事項】')
            doc.append('特許法施行令第１０条第３号ロに掲げる者に該当する特許権者である。減免申請書の提出を省略する。')

    # 納付金額
    if prop['Law'] == 'Patent':
        doc.append('【特許料の表示】')
    elif prop['Law'] == 'Utility':
        doc.append('【登録料の表示】')
    elif prop['Law'] == 'Design':
        doc.append('【登録料の表示】')
    elif prop['Law'] == 'Trademark':
        if req['Years'] == 5 and req['PaidYears'] == 10:
            doc.append('【納付の表示】　分割納付')
        doc.append('【登録料の表示】')

    doc.append('　【指定立替納付】')
    fees = [x['Fee'] for x in req['FeeList'] if x['Kind'] == 'Office']
    if len(fees) > 0:
        doc.append('　【納付金額】　　　%s' % mojimoji.han_to_zen(str(int(fees[0]))))
    else:
        doc.append('　【納付金額】　　　')

    # HTML化
    html = '<html><head><meta http-equiv="content-type" content="text/html; charset=shift-jis" /></head><body>\n%s\n</body></html>' % '\n'.join(['<p>%s</p>' % x for x in doc])

    return html

def create_claiming_gembo_paper(req, prop):
    """
    納付書のHTMLを生成する
    """
    doc = []

    # https://www.pcinfo.jpo.go.jp/guide/Content/Guide/Demand/Patent/Doc/DeP_TorokuKirokuJikoEtsuran.htm

    # 書類名、あて名
    doc.append('【書類名】　　　　　　　　登録事項の閲覧請求書')
    doc.append('【あて先】　　　　　　　　特許庁長官殿')

    # 登録番号
    reg_num = prop['RegistrationNumber']
    reg_num = re.sub(r'^0+', '', reg_num)

    if prop['Law'] == 'Trademark' and 'Defensive' in prop and prop['Defensive']:
        m = re.match(r'(.*)[\-/.](.*)', reg_num)
        reg_num = '商標登録第{}号の防護標章登録第{}号'.format(mojimoji.han_to_zen(m.group(1)), mojimoji.han_to_zen(m.group(2)))
        doc.append('【商標登録番号】　%s' % reg_num)
    else:
        #reg_num = mojimoji.han_to_zen(reg_num)
        if prop['Law'] == 'Patent':
            doc.append('【特許番号】　　　　　　　特許第%s号' % reg_num)
        elif prop['Law'] == 'Utility':
            doc.append('【実用新案登録番号】　　　実用新案登録第%s号' % reg_num)
        elif prop['Law'] == 'Design':
            doc.append('【意匠登録番号】　　　　　意匠登録第%s号' % reg_num)
        elif prop['Law'] == 'Trademark':
            doc.append('【商標登録番号】　　　　　商標登録第%s号' % reg_num)

    doc.append('【請求人】')
    doc.append('　【識別番号】　　　　　　110004439')
    doc.append('　【氏名又は名称】　　　　ＡＩＰＰＡＹ弁理士法人')
    doc.append('　【代表者】　　　　　　　山下　隆志')
    doc.append('　【電話番号】　　　　　　090-9817-2924')
    doc.append('【手数料の表示】')
    doc.append('　【指定立替納付】')
    doc.append('　【納付金額】　　　　　　600円')

    # HTML化
    html = '<html><head><meta http-equiv="content-type" content="text/html; charset=shift-jis" /></head><body>\n%s\n</body></html>' % '\n'.join(['<p>%s</p>' % x for x in doc])

    return html

# デバッグコード
if __name__ == '__main__':

    import logging
    import openpyxl
    import fee_calculator
    import language
    import os
    from pathlib import Path
    from datetime import datetime

    logger = logging.getLogger(__name__)

    out_dir = Path('log') / datetime.now().strftime('%Y%m%d%H%M%S')
    if not os.path.isdir(str(out_dir)):
        os.mkdir(str(out_dir))

    book = openpyxl.open('../test/jpo_paper.xlsx', data_only=True)
    sheet = book['Sheet1']

    i = 0

    for row in sheet.iter_rows(values_only=True):
        if i == 0:
            pass
        elif i == 1:
            cols = {}
            for j in range(len(row)):
                if row[j]:
                    cols[row[j]] = j
        else:
            data = {'prop': {'Country': 'JP'}, 'req': {}}
            data['prop']['Holders'] = [
                {'Id': '000186566', 'Name': '権利者１'},
                {'Id': '513155998', 'Name': '権利者２'},
            ]
            for key in ('Law', 'RegistrationNumber', 'Subject', 'PaidYears', 'NumberOfClaims', 'JpGenmen',
                        'ApplicationDate', 'RegistrationDate', 'ExamClaimedDate', 'RegistrationPaymentDate', 'RegistrationInvestigatedDate', 'RenewPaymentDate',):
                if key in cols and not row[cols[key]] is None:
                    data['prop'][key] = row[cols[key]]
            if 'OriginalClasses' in cols and not row[cols['OriginalClasses']] is None:
                data['prop']['Classes'] = [x.strip() for x in row[cols['OriginalClasses']].split(',')]
            for key in ('PaidYears', 'Years', 'YearFrom', 'YearTo', 'NumberOfClaims',):
                if key in cols and not row[cols[key]] is None:
                    data['req'][key] = row[cols[key]]
            for key in ('Classes', 'OriginalClasses',):
                if key in cols and not row[cols[key]] is None:
                    data['req'][key] = [x.strip() for x in row[cols[key]].split(',')]
            def to_zero(d, k):
                if not k in d:
                    return 0
                else:
                    return d[k]
            if data['prop']['Law'] == 'Trademark':
                fees = fee_calculator.calculate_fees(data['prop'], language.get_dictionary('ja'), years=data['req']['Years'], classes=len(data['req']['Classes']))
            else:
                fees = fee_calculator.calculate_fees(data['prop'], language.get_dictionary('ja'), year_from=data['req']['YearFrom'], year_to=data['req']['YearTo'])

            data['req']['FeeList'] = fees

            html = create_payment_paper(data['req'], data['prop'])

            file_path = out_dir / '{:0000}.html'.format(row[cols['Case']])
            with open(str(file_path), 'w', encoding='shift_jis') as fout:
                fout.write(html)

        i += 1
