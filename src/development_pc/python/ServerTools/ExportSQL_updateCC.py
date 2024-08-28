import argparse
import logging
import os
from collections import OrderedDict
from datetime import date
from dataclasses import asdict, dataclass
from ipaddress import ip_address, IPv4Address, IPv4Network
import typing
from typing import Any, List, Dict, Iterator, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection, cursor

from db import pgdatabase
from dao.rir_ipv4_allocated import (
    RirRecord, make_like_ip, get_rir_table_matches
)

import util.ipv4_util as ipv4_u
import util.file_util as fu
from log import logsetting

"""
国コード更新用SQL出力バッチスクリプト
RIR_ipv4_allocated テーブルから各IPアドレスに部分一致するRIRレコードを取得し、
更新用SQLとその他有用な情報を出力する

[テーブル]
(1) 不正アクセスIPアドレスマスタ (mainte.unath_ip_addr)
  国コードがNULLの全てのIPアドレス取得
(2) RIRデータマスターテーブル (mainte.rir_ipv4_allocated)　　

[出力ファイル]
1. 国コード更新用SQLファイル
    ~/data/sql/webriverside/batch/
      upd_ip_cc_YYYY-mm-dd.sql
2. IPアドレスが所属するネットワークアドレスと国コードを紐付けるファイル
    ~/Documents/webriverside/match-networks/
      ip_network_cc_with_hosts_YYYY-mm-dd.txt
      ※国コード不明IPアドレスリスト
      unknown_ip_hosts_YYYY-mm-dd.txt
"""

# データベース接続情報
DB_CONF_FILE: str = os.path.join("conf", "db_conn.json")
# 出力先情報
CONF_FILE: str = os.path.join("conf", "export_sql_with_ip_country_code.json")

# UPDATEクエリーフォーマット
FMT_SQL: str = "UPDATE mainte.unauth_ip_addr SET country_code='{}' WHERE ip_addr='{}';"
# 国コード不明
CC_UNKNOWN: str = "??"


@dataclass(frozen=True)
class IpNetworkWithCC:
    ip_network: str
    country_code: str
    ip_hosts: list[str]


def get_ip_list_with_null_cc(
        conn: connection,
        fetch_limit: int,
        logger: Optional[logging.Logger] = None) -> List[str]:
    try:
        cur: cursor
        with conn.cursor() as cur:
            # 国コードがNULLのレコード取得
            cur.execute(f"""
SELECT ip_addr FROM mainte.unauth_ip_addr
 WHERE country_code IS NULL ORDER BY ip_number LIMIT {fetch_limit}"""
                        )
            # レコード取得件数チェック
            if cur.rowcount > 0:
                rows: List[Tuple[str, ...]] = cur.fetchall()
                if logger is not None:
                    if cur.query is not None:
                        logger.debug(f"{cur.query.decode('utf-8')}")
                    logger.debug(f"rows: {rows}")
                # IPアドレスのリスト
                result = [row[0] for row in rows]
            else:
                # マッチしなかったら空のリスト
                result = []
        return result
    except (Exception, psycopg2.DatabaseError) as errors:
        raise errors


@typing.no_type_check
def detect_cc_in_matches(
        target_ip_addr: IPv4Address,
        matches: List[Tuple[str, int, str]],
        param_dict_ip_net: Optional[Dict[str, IpNetworkWithCC]] = None,
        logger: Optional[logging.Logger] = None) -> Tuple[Optional[str], Optional[str]]:

    def next_record(rows: List[Tuple[str, int, str]]) -> Iterator[RirRecord]:
        for (ip_sta, ip_cnt, country_code) in rows:
            yield RirRecord(ip_start=ip_sta, ip_count=ip_cnt, country_code=country_code)

    match_network: Optional[str] = None
    match_cc: Optional[str] = None
    rec: RirRecord
    for rec in next_record(matches):
        # 開始IPアドレスがターゲットIPアドレスより大きい場合は範囲外なので処理終了
        if ip_address(rec.ip_start) > target_ip_addr:  # type: ignore
            break

        # 開始IPアドレスのブロードキャストアドレスがターゲットIP未満なら次のレコードへ
        broadcast_addr: IPv4Address = (
                ip_address(rec.ip_start) + rec.ip_count - 1)  # type: ignore
        if broadcast_addr < target_ip_addr:
            continue

        cidr_cc_list: List[Tuple[IPv4Network, str]] = ipv4_u.get_cidr_cc_list(
            **asdict(rec)
        )
        if logger is not None:
            logger.debug(cidr_cc_list)
        match_network, match_cc = ipv4_u.detect_cc_in_cidr_cc_list(
            str(target_ip_addr), cidr_cc_list
        )
        if match_network is not None and match_cc is not None:
            # ネットワークと国コードが取得できた
            if param_dict_ip_net is not None:
                # IPネットワークに属する全てのホストをリストに追加
                data: Optional[IpNetworkWithCC] = param_dict_ip_net.get(match_network)
                if data is None:
                    # 辞書オブジェクトに存在しない場合はレコードを追加
                    param_dict_ip_net[match_network] = IpNetworkWithCC(
                        ip_network=match_network,
                        country_code=match_cc,
                        ip_hosts=[str(target_ip_addr)]
                    )
                else:
                    # 辞書オブジェクトに存在したらターケットをホストリストに追加
                    data.ip_hosts.append(str(target_ip_addr))

    return match_network, match_cc


def rir_table_matches_main(
        conn: connection,
        target_ip_list: List[str],
        dict_ip_network_cc: Optional[Dict[str, IpNetworkWithCC]],
        unknown_ip_list: Optional[List[str]],
        sql_lines: Optional[List[str]],
        logger: logging.Logger,
        enable_debug: bool = False) -> None:
    for i, target_ip in enumerate(target_ip_list):
        logger.info(f"{i + 1:04d}: START {target_ip}")
        target_ip_addr: IPv4Address = ip_address(target_ip)  # type: ignore
        like_ip: Optional[str] = make_like_ip(target_ip)
        matches: Optional[List[Tuple[str, int, str]]] = None
        while like_ip is not None:
            matches = get_rir_table_matches(conn, like_ip, logger=None)
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
                if enable_debug:
                    logger.debug(f"{i + 1:04d}: first: {first_ip}, last: {last_ip}")

                if first_ip_addr < target_ip_addr < broadcast_addr:
                    # ターゲットIPが先頭レコードの開始IPと最終レコードのブロードキャストの範囲内なら終了
                    if enable_debug:
                        logger.debug(
                            f"Range in ({first_ip} < {target_ip} < {str(broadcast_addr)})"
                            f", break"
                        )
                    break
                else:
                    # 範囲外
                    if enable_debug:
                        logger.debug(f"({target_ip} out of range, continue")
                    # 次のlike検索を実行
                    like_ip = make_like_ip(like_ip)
            else:
                # レコード無し: 次のlike検索文字列を生成して検索処理に戻る
                if enable_debug:
                    logger.debug(f"{like_ip} is no match.")
                like_ip = make_like_ip(like_ip)

        # ターケットIPが属するネットワークアドレスと国コードを取得する
        upd_cc: Optional[str]
        if matches is not None and len(matches) > 0:
            match_network: Optional[str]
            match_cc: Optional[str]
            match_network, match_cc = detect_cc_in_matches(
                target_ip_addr,
                matches,
                param_dict_ip_net=dict_ip_network_cc,
                logger=logger if enable_debug else None
            )
            upd_cc = match_cc if match_cc is not None else CC_UNKNOWN
            logger.info(f"{i + 1:04d}: END   {target_ip}, {upd_cc}")
            if upd_cc == CC_UNKNOWN:
                if unknown_ip_list is not None:
                    unknown_ip_list.append(target_ip)
        else:
            # 一致なし
            upd_cc = CC_UNKNOWN
            logger.warning(
                f"{i + 1:04d}: END   {target_ip}, RIR_ipv4_allocated no match."
            )
            if unknown_ip_list is not None:
                unknown_ip_list.append(target_ip)

        if sql_lines is not None:
            sql_line: str = FMT_SQL.format(upd_cc, target_ip)
            sql_lines.append(sql_line)


def save_network_cc_dict(
        date_part: str, save_dir: str, dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        logger: logging.Logger) -> None:
    file_name: str = f"ip_network_cc_with_hosts_{date_part}.txt"
    save_file: str = os.path.join(save_dir, file_name)
    # 行形式: "ip_network","cc",["host1","host2",...]
    net_cc_rec: IpNetworkWithCC
    net_cc_lines: List[str] = []
    for key in dict_ip_network_cc.keys():
        net_cc_rec = dict_ip_network_cc[key]
        line_hosts: str = '",\n"'.join(net_cc_rec.ip_hosts)
        line: str = f'"{key}","{net_cc_rec.country_code}",["{line_hosts}"]'
        net_cc_lines.append(line)
    fu.write_text_lines(save_file, net_cc_lines)
    logger.info(f"Saved: {save_file}")


def save_unknown_list(
        date_part: str, save_dir: str, unknown_ip_list: List[str],
        logger: logging.Logger) -> None:
    file_name: str = f"unknown_ip_hosts_{date_part}.txt"
    save_file: str = os.path.join(save_dir, file_name)
    fu.write_text_lines(save_file, unknown_ip_list)
    logger.info(f"Saved: {save_file}")


def save_sql_lines(
        date_part: str, save_dir: str, sql_lines: List[str],
        logger: logging.Logger) -> None:
    file_name: str = f"upd_ip_cc_{date_part}.sql"
    save_file: str = os.path.join(save_dir, file_name)
    fu.write_text_lines(save_file, sql_lines)
    logger.info(f"Saved: {save_file}")


def export_main():
    app_logger: logging.Logger = logsetting.get_logger("export_main")
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-limit", type=int, default=100,
                        help="Fetch target ip List count.")
    # IPネットワークに属する全てのホストIP記録したファイルを出力する
    parser.add_argument("--save-match-network", action="store_true",
                        help="Save matches IP Network Hosts file.")
    # 不正アクセスIPマスタの国コード更新クエリーファイルを出力しない
    parser.add_argument("--no-output-sql", action="store_true",
                        help="No output country_code update SQL file.")
    # fetch-limitが10件程度の場合に指定する ※大量のログが出力される
    parser.add_argument("--enable-debug", action="store_true",
                        help="Enable logger debug out.")
    args: argparse.Namespace = parser.parse_args()
    fetch_limit: int = args.fetch_limit
    save_match_network: bool = args.save_match_network
    no_output_sql: bool = args.no_output_sql
    enable_debug: bool = args.enable_debug

    # クエリーの出力先
    conf: Dict[str, Any] = fu.read_json(CONF_FILE)
    output_sql_dir: str = os.path.expanduser(conf["output-dir"])
    # IPネットワークに属する全てのホストIPを出力するファイルの出力先ディレクトリ
    match_networks_dir: str = os.path.expanduser(conf["query"]["match-networks-dir"])
    # ターゲットIPが属するネットワーク情報を出力するか
    dict_ip_network_cc: Optional[Dict[str, IpNetworkWithCC]]
    # 国コードが不明なIPアドレスのリスト
    unknown_ip_list: Optional[List[str]]
    if save_match_network:
        if not os.path.exists(match_networks_dir):
            os.makedirs(match_networks_dir)
        dict_ip_network_cc = OrderedDict()
        unknown_ip_list = []
    else:
        dict_ip_network_cc = None
        unknown_ip_list = None
    # 国コード更新用クエリー生成
    sql_lines: Optional[List[str]]
    if not no_output_sql:
        sql_lines = []
    else:
        sql_lines = None

    db: Optional[pgdatabase.PgDatabase] = None
    try:
        db = pgdatabase.PgDatabase(DB_CONF_FILE, logger=app_logger)
        conn: connection = db.get_connection()
        # 国コードがNULLのIPアドレスを取得 ※大量にログが出力されるためloggerにNoneを設定する
        target_ip_list: List[str] = get_ip_list_with_null_cc(
            conn, fetch_limit, logger=None
        )
        target_ip_list_size: int = len(target_ip_list)
        app_logger.info(f"target_ip_list.size: {target_ip_list_size}")

        if target_ip_list_size > 0:
            rir_table_matches_main(
                conn, target_ip_list, dict_ip_network_cc, unknown_ip_list, sql_lines,
                app_logger, enable_debug
            )

    except psycopg2.Error as db_err:
        app_logger.error(db_err)
        exit(1)
    except Exception as err:
        app_logger.error(err)
        exit(1)
    finally:
        if db is not None:
            db.close()

    # ターゲットIPの属するIPネットワークと国コード情報ファイル
    date_part: str = date.today().isoformat()
    if dict_ip_network_cc is not None and len(dict_ip_network_cc):
        save_network_cc_dict(
            date_part, match_networks_dir, dict_ip_network_cc, app_logger
        )
    # 国コード不明リスト
    if unknown_ip_list is not None and len(unknown_ip_list) > 0:
        save_unknown_list(date_part, match_networks_dir, unknown_ip_list, app_logger)
    # クエリーファイル出力
    if sql_lines is not None and len(sql_lines) > 0:
        save_sql_lines(date_part, output_sql_dir, sql_lines, app_logger)

    app_logger.info("Done.")


if __name__ == '__main__':
    export_main()
