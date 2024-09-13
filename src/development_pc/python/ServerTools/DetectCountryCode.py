import argparse
import logging
import os
from dataclasses import dataclass, asdict
from ipaddress import ip_address, IPv4Address, IPv4Network
from typing import List, Iterator, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor

from db import pgdatabase
import util.ipv4_util as ipv4_u

# ログフォーマット
LOG_FMT: str = '%(levelname)s %(message)s'
# データベース接続情報
DB_CONF_FILE: str = os.path.join("conf", "db_conn.json")


@dataclass(frozen=True)
class RirRecord:
    ip_start: str
    ip_count: int
    country_code: str


def get_rir_table_matches(
        conn: connection,
        like_ip: str,
        logger: Optional[logging.Logger] = None) -> List[Tuple[str, int, str]]:
    if logger is not None:
        logger.debug(f"like_ip: {like_ip}")
    result: List[Tuple[str, int, str]]
    try:
        cur: cursor
        # ゼロ埋めしたIPアドレスの昇順にソートする
        with conn.cursor() as cur:
            cur.execute("""
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
 LPAD(SPLIT_PART(ip_start,'.',4), 3, '0')""",
                        ({'partial_match': like_ip}))
            # レコード取得件数チェック
            if cur.rowcount > 0:
                rows: List[Tuple[str, int, str]] = cur.fetchall()
                if logger is not None:
                    logger.debug(f"rows.size: {len(rows)}")
                    for row in rows:
                        logger.debug(f"{row}")
                result = rows
            else:
                # マッチしなかったら空のリスト
                result = []
        return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


def get_country_code_name(
        conn: connection,
        country_code: str,
        logger: Optional[logging.Logger] = None) -> Optional[str]:
    if logger is not None:
        logger.debug(f"country_code: {country_code}")
    result: Optional[str]
    try:
        cur: cursor
        # ゼロ埋めしたIPアドレスの昇順にソートする
        with conn.cursor() as cur:
            cur.execute("""
SELECT japanese_name FROM mainte.country_code_name_mst WHERE country_code=%(cc)s""",
                        ({'cc': country_code})
                        )
            # レコード取得件数チェック
            if cur.rowcount > 0:
                row: Optional[Tuple] = cur.fetchone()
                if logger is not None:
                    logger.debug(f"row: {row}")
                result = row[0] if row is not None else None
            else:
                result = None
        return result
    except (Exception, psycopg2.DatabaseError) as err:
        raise err


def get_matches_main(
        conn: connection,
        target_ip: str,
        logger: Optional[logging.Logger] = None) -> Optional[List[Tuple[str, int, str]]]:
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

    target_ip_addr: IPv4Address = ip_address(target_ip)  # type: ignore
    like_ip: Optional[str] = make_like_ip(target_ip)
    matches: Optional[List[Tuple[str, int, str]]] = None
    while like_ip is not None:
        matches = get_rir_table_matches(conn, like_ip, logger=logger)
        if len(matches) > 0:
            # 先頭レコードの開始IPアドレス
            first_ip: str = matches[0][0]
            first_ip_addr: IPv4Address = ip_address(first_ip)  # type: ignore
            # 最終レコードの開始IPアドレス
            last: Tuple[str, int, str] = matches[-1]
            last_ip: str = last[0]
            ip_cnt: int = int(last[1])
            last_ip_addr: IPv4Address = ip_address(last_ip)  # type: ignore
            # 最終レコードのブロードキャストアドレス計算
            broadcast_addr: IPv4Address = last_ip_addr + ip_cnt - 1  # type: ignore
            if logger is not None:
                logger.info(f"match_first: {first_ip}, match_last: {last_ip}")

            if first_ip_addr < target_ip_addr < broadcast_addr:
                # ターゲットIPが先頭レコードの開始IPと最終レコードのブロードキャストの範囲内なら終了
                if logger is not None:
                    logger.debug(
                        f"Range in ({first_ip} < {target_ip} < {str(broadcast_addr)})"
                        f", break"
                    )
                break
            else:
                # 範囲外: 次のlike検索文字列を生成して検索処理に戻る
                like_ip = make_like_ip(like_ip)
                if logger is not None:
                    logger.info(f"next {like_ip} continue.")
        else:
            # レコード無し: 次のlike検索文字列を生成して検索処理に戻る
            if logger is not None:
                logger.info(f"{like_ip} is no match.")
            like_ip = make_like_ip(like_ip)
    return matches


def detect_cc_in_matches(
        target_ip: str,
        matches: List[Tuple[str, int, str]],
        logger: Optional[logging.Logger] = None) -> Tuple[Optional[str], Optional[str]]:
    def next_record(rows: List[Tuple[str, int, str]]) -> Iterator[RirRecord]:
        for (ip_sta, ip_cnt, cc) in rows:
            yield RirRecord(ip_start=ip_sta, ip_count=ip_cnt, country_code=cc)

    target_ip_addr: IPv4Address = ip_address(target_ip)  # type: ignore
    match_network: Optional[str] = None
    match_cc: Optional[str] = None
    rec: RirRecord
    for rec in next_record(matches):
        # ターゲットIP が ネットワークIPアドレスより大きい場合は範囲外のため処理終了
        if ip_address(rec.ip_start) > target_ip_addr:  # type: ignore
            if logger is not None:
                logger.debug(
                    f"{target_ip} < {rec.ip_start} break. No more match."
                )
            # マッチするデータなし
            break

        # 開始ネットワークIPのブロードキャストアドレスがターゲットIPより小さければ次のレコードへ
        broadcast_addr: IPv4Address = (
                ip_address(rec.ip_start) + rec.ip_count - 1)  # type: ignore
        if broadcast_addr < target_ip_addr:
            if logger is not None:
                logger.debug(f"({str(broadcast_addr)} < {target_ip}) -> continue")
            continue

        cidr_cc_list: List[Tuple[IPv4Network, str]] = ipv4_u.get_cidr_cc_list(
            **asdict(rec)
        )
        if logger is not None:
            logger.debug(cidr_cc_list)
        match_network, match_cc = ipv4_u.detect_cc_in_cidr_cc_list(
            target_ip, cidr_cc_list
        )
        break

    return match_network, match_cc


def exec_main():
    logging.basicConfig(format=LOG_FMT)
    app_logger = logging.getLogger(__name__)
    app_logger.setLevel(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-ip", required=True, type=str,
                        help="IP address.")
    parser.add_argument("--enable-debug", action="store_true",
                        help="Enable logger debug out.")
    args: argparse.Namespace = parser.parse_args()
    target_ip: str = args.target_ip
    enable_debug: bool = args.enable_debug
    app_logger.info(f"target_ip: {target_ip}, enable_debug: {enable_debug}")

    db: Optional[pgdatabase.PgDatabase] = None
    try:
        db = pgdatabase.PgDatabase(DB_CONF_FILE, logger=None)
        conn: connection = db.get_connection()
        matches: Optional[List[Tuple[str, int, str]]] = get_matches_main(
            conn, target_ip, logger=app_logger if enable_debug else None)

        # ターゲットIPのネットワーク(CIDR表記)と国コードを取得する
        if matches is not None and len(matches) > 0:
            network: Optional[str]
            cc: Optional[str]
            network, cc = detect_cc_in_matches(
                target_ip, matches, logger=app_logger if enable_debug else None)
            if network is not None and cc is not None:
                cc_name: Optional[str] = get_country_code_name(
                    conn, cc, logger=app_logger if enable_debug else None
                )
                app_logger.info(
                    f'Find {target_ip} in (network: "{network}", "{cc}:{cc_name}")'
                )
            else:
                app_logger.info(f"Not match in data.")
        else:
            # このケースは想定しない
            app_logger.warning(f"Not exists in RIR table.")
    except psycopg2.Error as db_err:
        app_logger.error(db_err)
        exit(1)
    except Exception as exp:
        app_logger.error(exp)
        exit(1)
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    exec_main()
