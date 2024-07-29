import sys
import os
import logging
from pathlib import Path

# ディレクトリー関係の調整
dirpath = os.path.dirname(os.path.abspath(__file__))
sys.path.append(dirpath)
os.chdir(dirpath)

from local_config import Config
conf = Config()

log_path = Path(conf['log']['directory']) / 'webapp.log'

# ログの設定
logging.basicConfig(level=logging.INFO,
    filename=str(log_path),
    format='%(asctime)s:%(process)d:%(name)s:%(levelname)s:%(message)s'
)

# アプリケーションの読み込み
import bottle
from index import myApp

application = myApp
