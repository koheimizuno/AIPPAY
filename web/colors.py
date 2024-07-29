from enum import Enum

class Color(Enum):
    """
    カラーパレットの定義
    """

    # 黒
    Black = (0.0, 0.0, 0.0)

    # 白
    White = (1.0, 1.0, 1.0)        

    # 罫線の色
    LineColor = (0.13, 0.17, 0.4)

    # 背景の色
    BgColor = (0.85, 0.85, 0.85)

    # 暗い青
    DarkBlue = (0.1176, 0.1294, 0.5333)

    # 明るい青
    LightBlue = (0.0196, 0.7255, 0.9333)

    # 薄い青（表の背景色）
    VeryLightBlue = (0.8745, 0.9412, 0.9608)

    # 赤
    Red = (0.7020, 0.0627, 0.0627)
