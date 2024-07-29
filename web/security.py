import hashlib
import random
import base64
from bson.objectid import ObjectId
from Crypto import Random
from Crypto.Cipher import AES
import string
import uuid
import copy
import json
import datetime
import re
import logging

from local_config import Config

logger = logging.getLogger(__name__)

def generate_passwd(length=12):
    """
    ランダムな文字列を生成する
    """
    chars = string.ascii_letters + string.digits
    return ''.join([chars[random.randint(0,len(chars)-1)] for x in range(length)])

def hash(text):
    """
    テキストのハッシュ値を取得する
    """
    if text is None or len(text) == 0:
        return None
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

__key_phrase = 'QQ6mzydNjdQWU3fsANjwYFyAnaUvGNsBY3U5fbkR'
__block_size = 32

def _padding(s):
    return s + ((__block_size - len(s) % __block_size) * chr(__block_size - len(s) % __block_size)).encode('us-ascii')

if len(__key_phrase) >= len(str(__block_size)):
    __secret_key = __key_phrase[:__block_size]
else:
    __secret_key = _padding(__key_phrase)

def encrypt(raw):
    """
    文字列を暗号化したBASE64文字列を取得した
    """
    raw = _padding(raw.encode('utf-8'))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(__secret_key.encode('us-ascii'), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw)).decode('us-ascii')

def _unpadding(s):
    return s[:-ord(s[len(s)-1:])]

def decrypt(enc):
    """
    BASE64文字列で表された暗号化データ（文字列）を復号する
    """
    try:
        enc = base64.b64decode(enc.encode('us-ascii'))
        iv = enc[:AES.block_size]
        cipher = AES.new(__secret_key.encode('us-ascii'), AES.MODE_CBC, iv)
        s = _unpadding(cipher.decrypt(enc[AES.block_size:])).decode('utf-8')
        return s if s != '' else None
    except Exception as e:
        logger.warning('cannot decrypt (%s, %s)', type(e), e)
        return None

def generate_uuid():
    """
    UUIDを生成する
    """
    return str(uuid.uuid4())

def encrypt_dict(d):
    """
    dictを暗号化する
    """
    w = copy.deepcopy(d)
    for k in w.keys():
        if k in ('alert', 'information'):
            continue
        if w[k] is None:
            w[k] = 'None'
        else:
            w[k] = repr(w[k])
    s = json.dumps(w)
    return encrypt(s)

def decrypt_dict(p):
    """
    暗号化されたdictを復号する
    """
    s = decrypt(p)
    d = json.loads(s)
    for k in d:
        d[k] = eval(d[k])
    return d

def random_mask(s):
    """
    文字列をランダムにマスクする
    """
    return ''.join([x if random.random() < 0.5 else '*' for x in s])

def mask_mail_address(mail_address):
    """
    メールアドレスを表示用にマスクする
    """
    m = re.match(r'(.*?)@(.*)', mail_address)
    if m:
        a = m.group(1)
        b = m.group(2)
        return '%s@%s' % (random_mask(a), random_mask(b))
    else:
        return random_mask(mail_address)

def is_safe_as_password(raw):
    """
    文字列がパスワードとして妥当かチェックする
    """
    if raw is None:
        return False
    if not isinstance(raw, str):
        raw = str(raw).trim()
    # 8文字必要
    if len(raw) < 8:
        return False
    # 同じ文字の羅列は認めない
    if re.match(r'(.)\1+$', raw):
        return False
    # 数字のみの羅列は認めない
    if re.match(r'\d+$', raw):
        return False
    # OK
    return True

def get_csrf_token():
    """
    CSRF対策のトークンを生成する
    """
    return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(32)])

def is_email(addr):
    """
    文字列がメールアドレスとして妥当か検証します。
    """
    m = re.match(r'[a-zA-Z0-9.!#$%&\'*+\/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$', addr)
    return not (m is None)
