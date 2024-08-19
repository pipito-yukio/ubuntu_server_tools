from typing import List, Optional

"""
RIR_ipv4_allocatedテーブルの1文字(アンダースコア)Like検索文字列を生成するモジュール
※このロジックでは捉えきれないIPが発生する可能性があるため使用することはないが
処理方法の参考として残しておく

ターゲットIP=83.222.191.62 を1文字(アンダースコア)Like検索文字列生成
(1) 83.222.191.%	0	▲レコードなし
(2) 83.222.19_.%	1	▲レコード有りだが範囲外
(3) 83.222.1__.%	17	●該当IP有り
(4) 83.222.___.%	18
(5) 83.222.%		29
(6) 83.22_.%		137
(7) 83.2__.%		225
(8) 83.___.%		569
(9) 83.%		626	■終了条件

※パーセントLIKE文字列の方がスピードが早いのでこちらを選択
(1) 83.222.191.%	0	▲レコードなし
(2) 83.222.%		29	●該当IP有り
(3) 83.%		626	■終了条件
"""

def gen_like_ip_with_underscore(like_ip: str) -> Optional[str]:
    # 末尾の likeプレースホルダを削除する
    raw_ip: str = like_ip.replace(".%", "")
    fields: List[str] = raw_ip.split(".")
    # コンマで区切って残りが1つなら終了
    field_size: int = len(fields)
    if field_size == 1:
        return None

    # 最後の項目が対象
    last_part: str = fields[field_size - 1]
    last_size: int = len(last_part)
    # 全てが1文字プレースホルダ('_')か
    if last_part == '_' * last_size:
        # フィールドの最後を削除
        del fields[-1]
        return ".".join(fields) + ".%"

    # 文字列を逆順にする
    s_reverse: str = last_part[::-1]
    # 数値を1文字プレースホルダに置き換える
    is_replaced: bool = False
    s_replaced: str = ""
    for i in range(last_size):
        ch: str = s_reverse[i]
        if not is_replaced and ch.isdigit():
            # 後ろから最初に見つかった数字のみ置き換える
            s_replaced = "_" + s_replaced
            is_replaced = True
        else:
            # 置換済みなので先頭側の文字列を足し込む
            s_replaced = ch + s_replaced
    # 置き換え対象フィールドの文字列を置き換える
    fields[field_size - 1] = s_replaced
    # 末尾にlikeプレースホルダ(".%")を付加して終了
    return ".".join(fields) + ".%"
