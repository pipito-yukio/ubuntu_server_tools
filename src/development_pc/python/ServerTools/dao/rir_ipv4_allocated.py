import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor

"""
RIR (Regional Internet Registry) の 各国割り当てIPアドレス情報からIpv4アドレスの割当済みデータを
登録したテーブルから指定したIPアドレスに後方部分一致したレコードを取得する
"""

# LIKE検索では呼び出し側でクエリーパラメータに "%" を付与すること
QRY_IP_LIKE: str = """
SELECT
   ip_start,ip_count,country_code
FROM
   mainte.RIR_ipv4_allocated
WHERE
   ip_start LIKE %(partial_match)s
ORDER BY
 LPAD(SPLIT_PART(ip_start,'.',1), 3, '0') || '.' ||
 LPAD(SPLIT_PART(ip_start,'.',2), 3, '0') || '.' ||
 LPAD(SPLIT_PART(ip_start,'.',3), 3, '0') || '.' ||
 LPAD(SPLIT_PART(ip_start,'.',4), 3, '0')"""


@dataclass(frozen=True)
class RirRecord:
    ip_start: str
    ip_count: int
    country_code: str


def make_like_ip(like_old: str) -> Optional[str]:
    # 末尾の likeプレースホルダを削除する
    raw_ip: str = like_old.replace(".%", "")
    fields: List[str] = raw_ip.split(".")
    # コンマで区切って残りが1つなら終了
    field_size: int = len(fields)
    if field_size == 1:
        return None

    # フィールドを1つ減らす
    del fields[field_size - 1]
    # 末尾にlikeプレースホルダ(".%")を付加して終了
    return ".".join(fields) + ".%"


def get_rir_table_matches(
        con: connection,
        qry_params: str,
        logger: Optional[logging.Logger] = None) -> List[Tuple[str, int, str]]:
    if logger is not None:
        logger.debug(f"qry_params: {qry_params}")
    result: List[Tuple[str, int, str]]
    try:
        cur: cursor
        with con.cursor() as cur:
            cur.execute(QRY_IP_LIKE, ({'partial_match': qry_params}))
            # レコード取得件数チェック
            if cur.rowcount > 0:
                rows: List[Tuple[str, int, str]] = cur.fetchall()
                if logger is not None:
                    logger.debug(f"rows: {rows}")
                result = rows
            else:
                # マッチしなかったら空のリスト
                result = []
        return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err
