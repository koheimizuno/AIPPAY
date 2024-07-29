import logging
import sys
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email import charset
from pathlib import Path
import configparser
from datetime import datetime, timedelta
import base64

from local_config import Config

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 設定ファイルの読み込み
conf = Config()

# 接続全てをSSLとするか、接続後にSSL(TLS)にするか
if 'strict_ssl' in conf['smtp'] and conf['smtp']['strict_ssl'] == '1':
    ssl = True
    from smtplib import SMTP_SSL as SMTP
else:
    ssl = False
    from smtplib import SMTP as SMTP
import ssl

def send_mail(subject, body, to, cc=None, bcc=None, attachments=None):
    """
    メールの送信
    """
    enc = 'utf-8'

    # 件名の調整
    if subject is None:
        subject = ""
    if 'subject_prefix' in conf['smtp'] and conf['smtp']['subject_prefix'] != '':
        subject = conf['smtp']['subject_prefix'] + subject

    # リストをカンマ区切りに変換
    if not to is None:
        if isinstance(to, list):
            to = ','.join(to)
        to = str(to)
    if not cc is None:
        if isinstance(cc, list):
            cc = ','.join(cc)
        cc = str(cc)    
    if not bcc is None:
        if isinstance(bcc, list):
            bcc = ','.join(bcc)
        bcc = str(bcc)

    # デバッグ時のメールフィルター
    if 'domain_filter' in conf['smtp']:
        filter = conf['smtp']['domain_filter'].split(',')
        filter = ['@' + x.strip() for x in filter if x.strip() != ""]
        if len(filter) > 0:
            logger.debug('apply domain filters (%s)', ','.join(filter))
            def apply_filter(s):
                if s is None or s == "":
                    return s
                return ','.join([x for x in s.split(',') if len([y for y in filter if x.strip().endswith(y)]) > 0])
            to = apply_filter(to)
            cc = apply_filter(cc)
            bcc = apply_filter(bcc)

    if not to is None and to.strip() == "":
        to = None
    if not cc is None and cc.strip() == "":
        cc = None
    if not bcc is None and bcc.strip() == "":
        bcc = None

    if to == "" and cc == "" and bcc == "":
        logger.warning("sending email was canceled, because address was not specified.")
        return

    if attachments is None or len(attachments) == 0:

        # 本文
        message = MIMEText(body, 'plain', enc)

    else:

        # メッセージの生成
        message = MIMEMultipart()

        # 本文
        message.attach(MIMEText(body, 'plain', enc))

        # 添付
        for f in attachments:

            # ファイル名のエンコード
            enc_name = base64.b64encode(f['Name'].encode("utf-8")).decode()
            
            # マルチパートの生成
            tmp = MIMEApplication(
                f['Data'],
                'pdf' if f['Name'].endswith('.pdf') else 'octet-stream',
                name="=?utf-8?b?{}?=".format(enc_name),
            )

            # Content-Dispositionの指定
            tmp.add_header("Content-Disposition", "attachment", filename="{}".format(f['Name']))
            message.attach(tmp)

    message['Subject'] = Header(subject, enc)
    message['To'] = to
    if cc:
        message['Cc'] = cc
    if bcc:
        message['Bcc'] = bcc
    message['From'] = conf['smtp']['from']

    # SMTP-AUTH を通して送信
    with SMTP(conf['smtp']['host'], int(conf['smtp']['port'])) as smtp:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        smtp.ehlo()
        if SMTP.__name__ != 'SMTP_SSL':
            smtp.starttls(context=context)
        if 'user' in conf['smtp']:
            smtp.login(conf['smtp']['user'], conf['smtp']['pwd'])
            smtp.noop()
        smtp.send_message(message)
        smtp.quit()

    logger.info('sent mail to %s (cc: %s, bcc: %s)', to, cc, bcc)

if __name__ == '__main__':
    import io
    import os.path
    with open('20231107_特許6791731号_手続完了報告書.pdf', 'rb') as fin:
        attrs = [{
            'Data': fin.read(),
            'Name': '20231107_特許6791731号_手続完了報告書.pdf',
        }]
    # テストメールの送信
    send_mail('テスト', 'テストです。', ['go2anj.1108@gmail.com',], attachments=attrs)
    #send_mail('テスト', 'テストです。', 'hideto@isgs-lab.com')
