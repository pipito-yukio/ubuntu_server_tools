from logging import Logger
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import execute_values

"""
不正アクセスカウンターテーブルDB操作関数モジュール
[スキーマ] mainte
[対象テーブル] ssh_auth_error
"""

# 主キーレコード検索クエリ: log_date and ip_addrリスト
QRY_EXISTS_REC_JOINED: str = """
SELECT
   ip_addr, ip_id
FROM
   mainte.ssh_auth_error sae
   INNER JOIN mainte.unauth_ip_addr uia ON uia.id = sae.ip_id
WHERE
   log_date = %(log_date)s AND ip_addr IN %(in_clause)s"""

# 主キーレコード検索クエリ: log_date and ip_idリスト
QRY_EXISTS_REC: str = """
SELECT
   ip_id
FROM
   mainte.ssh_auth_error
WHERE
   log_date = %(log_date)s AND ip_id IN %(in_clause)s"""

# バッチ登録クエリー ※戻り値なし
QRY_INSERT_WITH_NO_RETURN: str = """
INSERT INTO mainte.ssh_auth_error(log_date, ip_id, appear_count) VALUES %s"""
# バッチ登録クエリー時のパラメータ生成用のテンプレート
VALUES_TEMPLATE: str = "(%(log_date)s, %(ip_id)s, %(appear_count)s)"


# ログ採取日のIPアドレスリストが登録済みかチェックする
def bulk_exists_record_with_joined(
        conn: connection,
        log_date: str,
        ip_list: List[str],
        logger: Optional[Logger] = None) -> Dict[str, int]:
    # IN ( in_clause )
    in_clause: Tuple[str, ...] = tuple(ip_list, )
    try:
        cur: cursor
        with conn.cursor() as cur:
            cur.execute(
                QRY_EXISTS_REC_JOINED, {"log_date": log_date, "in_clause": in_clause}
            )
            # 実行されたSQLを出力
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
            # 戻り値を取得する
            # def fetchall(self) -> list[tuple[Any, ...]]
            rows: List[Tuple[Any, ...]] = cur.fetchall()
            if logger is not None:
                logger.debug(f"rows: {rows}")

            result_dict: Dict[str, int] = {ip_addr: ip_id for (ip_id, ip_addr) in rows}
            return result_dict
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


def bulk_exists_record(
        conn: connection,
        log_date: str,
        ipid_list: List[int],
        logger: Optional[Logger] = None) -> List[int]:
    # IN ( in_clause )
    in_clause: Tuple[int, ...] = tuple(ipid_list, )
    try:
        cur: cursor
        with conn.cursor() as cur:
            cur.execute(
                QRY_EXISTS_REC, {"log_date": log_date, "in_clause": in_clause}
            )
            # 実行されたSQLを出力
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
            # 戻り値を取得する
            # def fetchall(self) -> list[tuple[Any, ...]]
            rows: List[Tuple[Any, ...]] = cur.fetchall()
            if logger is not None:
                logger.debug(f"rows: {rows}")

            # 結果が1カラムだけなのでタプルの先頭[0]をリストに格納
            result: List[int] = [row[0] for row in rows]
            return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


def bulk_insert_with_nofetch(
        conn: connection,
        qry_params: tuple[Dict[str, Any], ...],
        logger: Optional[Logger] = None) -> None:
    try:
        cur: cursor
        with conn.cursor() as cur:
            # 登録の戻り値不要
            execute_values(
                cur,
                QRY_INSERT_WITH_NO_RETURN,
                qry_params,
                template=VALUES_TEMPLATE,
            )
            # 実行されたSQLを出力
            if logger is not None:
                if cur.query is not None:
                    logger.debug(f"{cur.query.decode('utf-8')}")
    except (Exception, psycopg2.DatabaseError) as err:
        raise err
