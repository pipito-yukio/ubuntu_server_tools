from logging import Logger
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import execute_values

"""
不正アクセスIPテーブルのDB操作関数モジュール
[スキーマ] mainte
[対象テーブル] unauth_ip_addr
"""

QRY_EXISTS_IP_ADDR: str = """
SELECT id,ip_addr FROM mainte.unauth_ip_addr WHERE ip_addr IN %(in_clause)s;"""

QRY_INSERT_WITH_RETURN: str = """
INSERT INTO mainte.unauth_ip_addr(ip_addr, reg_date) VALUES %s RETURNING id,ip_addr"""

VALUES_TEMPLATE: str = "(%(ip_addr)s, %(reg_date)s)"


def bulk_exists_ip_addr(conn: connection,
                        ip_list: List[str],
                        logger: Optional[Logger] = None) -> Dict[str, int]:
    # IN ( in_clause )
    in_clause: Tuple[str, ...] = tuple(ip_list)
    try:
        cur: cursor
        with conn.cursor() as cur:
            cur.execute(QRY_EXISTS_IP_ADDR, {"in_clause": in_clause})
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
            # IN句で一致したIPアドレスの idとIPアドレスのタプルをすべて取得
            rows: List[tuple[Any, ...]] = cur.fetchall()
            if logger is not None:
                logger.debug(f"rows: {rows}")

            # 戻り値: IPアドレスをキーとするIPのIDの辞書
            result_dict: Dict[str, int] = {ip_addr: ip_id for (ip_id, ip_addr) in rows}
            return result_dict
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


# execute_values()メソッドを実行する ※内部で (%s,%s),(%s,),... 部分を生成してくれる
def bulk_insert_with_fetch(
        conn: connection,
        qry_params: tuple[Dict[str, Any], ...],
        logger: Optional[Logger] = None) -> Dict[str, int]:
    try:
        cur: cursor
        with conn.cursor() as cur:
            rows: List[Tuple[Any, ...]] = execute_values(
                cur,
                QRY_INSERT_WITH_RETURN,
                qry_params,
                template=VALUES_TEMPLATE,
                fetch=True
            )
            # 実行されたSQLを出力
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
                logger.debug(f"rows: {rows}")

            # 戻り値: IPアドレスをキーとするIPのIDの辞書
            result_dict: Dict[str, int] = {ip_addr: ip_id for (ip_id, ip_addr) in rows}
            return result_dict
    except (Exception, psycopg2.DatabaseError) as err:
        raise err
