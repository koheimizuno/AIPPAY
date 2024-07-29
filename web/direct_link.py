from local_config import Config
import security
import urllib.parse

conf = Config()

def get_link(path, user_id, prop_id):
    """
    依頼等へのダイレクトリンクを生成する
    """
    t = '\t'.join([str(user_id), str(prop_id)])
    t = security.encrypt(t)
    url = conf['web']['base_url'] + path + '?t=' + urllib.parse.quote(t)
    return url

if __name__ == '__main__':
    print(get_link('/d/silent', '5eace6d5d93cf558192767d4', '659481a682e62410c547cb5a'))
