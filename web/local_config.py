import os
import configparser

class Config(configparser.ConfigParser):
    """
    設定
    """

    def __init__(self):
        """
        config.iniで初期化する
        """
        super().__init__()
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        self.read(p)
