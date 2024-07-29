from enum import IntEnum as Enum, unique

@unique
class RequestStatus(Enum):

    # 見積中
    Estimating = 0,

    # 入金待ち
    Paying = 10

    # 対応中
    Doing = 50

    # 完了
    Done = 90

    # キャンセル
    Canceled = 102
