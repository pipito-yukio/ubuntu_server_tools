from logging import Logger
from typing import Any, List, Dict, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import execute_values

from dataclasses import dataclass

"""
ネットワークアドレス国コードテーブル
レコード操作モジュール
[スキーマ] mainte
[テーブル] match_network
"""


# ネットワークIP国コードテーブル登録用データ
@dataclass(frozen=True)
class RegMatchNetwork:
    ip_network: str
    country_code: str


@dataclass(frozen=True)
class MatchNetworkRecord:
    id: int
    ip_network: str
    country_code: str


# ネットワーク国コードテーブルの登録済件数
def rec_count_in_match_network(
        conn: connection,
        logger: Optional[Logger] = None) -> int:
    result: int
    try:
        cur: cursor
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mainte.match_network")
            row: Optional[Tuple[int]] = cur.fetchone()
            if logger is not None:
                logger.debug(f"row: {row}")
            if row is not None:
                result = row[0]
            else:
                result = 0
        return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


# ターゲットIPのネットワークがネットワーク国コードテーブルに存在するかチェック
def exists_in_match_network(
        conn: connection,
        target_ip: str,
        logger: Optional[Logger] = None) -> Optional[Tuple[int, str, str]]:
    result: Optional[Tuple[int, str, str]]
    try:
        cur: cursor
        with conn.cursor() as cur:
            cur.execute("""
SELECT
  id, cidr_addr, country_code
FROM
  mainte.match_network
WHERE
  inet %(target_ip)s << cidr_addr""",
                        ({'target_ip': target_ip}))
            row: Optional[Tuple[int, str, str]] = cur.fetchone()
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
                logger.debug(f"row: {row}")
            result = row
        return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


# ネットワーク国コードテーブルに一括登録
def bulk_insert_into_match_network(
        conn: connection,
        qry_params: tuple[Dict[str, Any], ...],
        logger: Optional[Logger] = None) -> Dict[str, int]:
    if logger is not None:
        logger.debug(f"qry_params: \n{qry_params}")
    try:
        cur: cursor
        with conn.cursor() as cur:
            rows: List[Tuple[int, str]] = execute_values(
                cur,
                """
INSERT INTO mainte.match_network(cidr_addr, country_code)
 VALUES %s RETURNING id,cidr_addr""",
                qry_params,
                template="(%(ip_network)s, %(country_code)s)",
                fetch=True
            )

            if logger is not None:
                for row in rows:
                    logger.debug(f"{row}")
            # 戻り値: ネットワークアドレスをキーとする登録IDの辞書
            result: Dict[str, int] = {net_addr: reg_id for (reg_id, net_addr) in rows}
            return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err
