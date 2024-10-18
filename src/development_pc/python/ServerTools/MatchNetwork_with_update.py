import argparse
import os
from collections import OrderedDict
from dataclasses import asdict, dataclass
from logging import Logger
from ipaddress import ip_address, ip_network, IPv4Address, IPv4Network
import typing
from typing import Any, List, Dict, Iterator, Optional, Tuple

import psycopg2
from psycopg2.extensions import connection

from db import pgdatabase
from dao.rir_ipv4_allocated import (
    RirRecord, make_like_ip, get_rir_table_matches
)
from dao.match_network import (
    RegMatchNetwork,
    rec_count_in_match_network, exists_in_match_network, bulk_insert_into_match_network
)
import dao.unauth_ip_addr as dao_ip_mst

import util.ipv4_util as ipv4_u
from log import logsetting

"""
国コードとネットワークアドレス検索処理で下記テーブルを登録・更新する
(1) ネットワークアドレス国コードテーブルに一括登録
(2) 不正アクセスIPマスタの当該フィールドを一括更新

[スキーマ] mainte
[テーブル]
(1) 不正アクセスIPアドレスマスタ (unath_ip_addr)
  国コードがNULLの全てのIPアドレス取得
(2) RIRデータマスターテーブル (rir_ipv4_allocated)　　
(3) ネットワークアドレス国コードテーブル (match_network)
"""

# データベース接続情報
DB_CONF_FILE: str = os.path.join("conf", "db_conn.json")


# ネットワークアドレス(Ipv4)の国コードとホストIPアドレスリストを保持するデータクラス
@dataclass
class IpNetworkWithCC:
    ip_network: str
    # ネットワークアドレス国コードテーブルに未登録の場合: None
    # 上書き可能とする
    network_id: Optional[int]
    country_code: str
    ip_hosts: list[str]


# レコードが存在する場合のみ呼び出す
def check_match_network_main(
        conn: connection,
        target_ip_addr: IPv4Address,
        dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        logger: Optional[Logger] = None) -> bool:
    target_ip: str = str(target_ip_addr)
    match_network_data: Optional[Tuple[int, str, str]] = exists_in_match_network(
        conn, target_ip, logger=logger
    )
    if match_network_data is not None:
        cc: str
        # 2列目がキーとなるネットワークアドレス
        key_network: str = match_network_data[1]
        data: Optional[IpNetworkWithCC] = dict_ip_network_cc.get(key_network)
        if data is None:
            # 辞書オブジェクトに存在しない場合はレコードを追加
            dict_ip_network_cc[key_network] = IpNetworkWithCC(
                ip_network=key_network,
                network_id=match_network_data[0],
                country_code=match_network_data[2],
                ip_hosts=[target_ip]
            )
        else:
            # 辞書オブジェクトに存在したらターケットをホストリストに追加
            data.ip_hosts.append(target_ip)
        return True

    return False


def insert_match_network_main(
        conn: connection,
        dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        logger: Logger, enable_debug: bool = False) -> None:
    # 登録用レコードリスト
    reg_datas: List[RegMatchNetwork] = []
    for key_ip in dict_ip_network_cc.keys():
        data: IpNetworkWithCC = dict_ip_network_cc[key_ip]
        if data.network_id is None:
            reg_datas.append(RegMatchNetwork(data.ip_network, data.country_code))
    reg_data_cnt: int = len(reg_datas)
    logger.info(f"register_match_network_cnt: {reg_data_cnt}")

    if reg_data_cnt > 0:
        if enable_debug:
            for item in reg_datas:
                logger.debug(f"{item}")
        # dataclassを辞書のタプルに変換
        params: Tuple[Dict[str, Any], ...] = tuple(
            [dict(asdict(rec)) for rec in reg_datas]
        )
        # 一括登録関数では大量のDEBUGログが出力されるのでロガーをNoneに設定
        registered_dict: Dict[str, int] = bulk_insert_into_match_network(
            conn, params, logger=logger if enable_debug else None
        )
        # 戻り値のDEBUG出力
        if enable_debug:
            for registered_key in registered_dict.keys():
                logger.debug(f"{registered_dict[registered_key]}: {registered_key}")
        # ターゲットIPが属するネットワーク情報辞書オブジェクトの登録IDを更新する
        for key_network in registered_dict.keys():
            ip_network_cc: IpNetworkWithCC = dict_ip_network_cc[key_network]
            # 登録IDを更新
            ip_network_cc.network_id = registered_dict[key_network]


@typing.no_type_check
def detect_cc_in_matches(
        target_ip_addr: IPv4Address,
        matches: List[Tuple[str, int, str]],
        dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        logger: Optional[Logger] = None) -> Tuple[Optional[str], Optional[str]]:

    def next_record(rows: List[Tuple[str, int, str]]) -> Iterator[RirRecord]:
        for (ip_sta, ip_cnt, country_code) in rows:
            yield RirRecord(ip_start=ip_sta, ip_count=ip_cnt, country_code=country_code)

    match_network: Optional[str] = None
    match_cc: Optional[str] = None
    rec: RirRecord
    for rec in next_record(matches):
        # ターゲットIP が ネットワークアドレスアドレスより大きい場合は範囲外のため処理終了
        if ip_address(rec.ip_start) > target_ip_addr:  # type: ignore
            # マッチするデータなし
            break

        # 開始ネットワークアドレスのブロードキャストアドレスがターゲットIPより小さければ次のレコードへ
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
            data: Optional[IpNetworkWithCC] = dict_ip_network_cc.get(match_network)
            if data is None:
                # 辞書オブジェクトに存在しない場合はレコードを追加
                dict_ip_network_cc[match_network] = IpNetworkWithCC(
                    network_id=None,
                    ip_network=match_network,
                    country_code=match_cc,
                    ip_hosts=[str(target_ip_addr)]
                )
            else:
                # 辞書オブジェクトに存在したらターケットをホストリストに追加
                data.ip_hosts.append(str(target_ip_addr))

    return match_network, match_cc


# dict_ip_network_cc にターゲットIPが含まれるネットワークが存在するかチェック
# 存在したらネットワークのIPホストリストに追加
@typing.no_type_check
def check_if_add_dict_ip_network_cc(
        target_ip_addr: IPv4Address,
        dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        logger: Optional[Logger] = None) -> bool:
    # dict_ip_network_cc が空なら該当なし
    if len(dict_ip_network_cc) == 0:
        return False

    # RIRデータ検索で見つかったネットワークアドレスにターゲットIPを含むものがあるか
    for key in dict_ip_network_cc.keys():
        data: IpNetworkWithCC = dict_ip_network_cc[key]
        if data.network_id is None:
            if target_ip_addr in ip_network(data.ip_network):
                # ターゲットIPアドレスを含むネットワークアドレス有り
                if logger is not None:
                    logger.debug(f"{str(target_ip_addr)} include {data.ip_network}")
                # IPホストリストに追加
                data.ip_hosts.append(str(target_ip_addr))
                return True

    # IPアドレスを含むネットワークアドレス無し
    return False


def rir_table_matches_main(
        conn: connection,
        match_network_rec_cnt: int,
        target_ip_list: List[str],
        dict_ip_network_cc: Dict[str, IpNetworkWithCC],
        unknown_ip_list: List[str],
        logger: Logger, enable_debug: bool = False) -> None:

    debug_logger: Optional[Logger] = logger if enable_debug else None
    for i, target_ip in enumerate(target_ip_list):
        logger.info(f"{i + 1:04d}: START {target_ip}")
        target_ip_addr: IPv4Address = ip_address(target_ip)  # type: ignore
        # ネットワークアドレス国コードテーブルに当該IPを含むネットワークアドレスが存在するか
        if match_network_rec_cnt > 0:
            is_match_network: bool = check_match_network_main(
                conn, target_ip_addr, dict_ip_network_cc, logger=debug_logger
            )
            if is_match_network:
                # ネットワークアドレス国コードテーブルに存在したのでRIRデータ検索処理をスキップ
                logger.info(f"{i + 1:04d}: END {target_ip} matched in match_network")
                continue

        # dict_ip_network_cc にターゲットIPが含まれるネットワークが存在するかチェック
        is_match_network = check_if_add_dict_ip_network_cc(
                target_ip_addr, dict_ip_network_cc, logger=debug_logger
            )
        if is_match_network:
            # 辞書オブジェクト内に見つかったのでRIRデータ検索処理をスキップ
            logger.info(f"{i + 1:04d}: END {target_ip} matched in dict_ip_network_cc")
            continue

        # RIRテーブル検索処理
        like_ip: Optional[str] = make_like_ip(target_ip)
        matches: Optional[List[Tuple[str, int, str]]] = None
        while like_ip is not None:
            matches = get_rir_table_matches(conn, like_ip, logger=debug_logger)
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
                    logger.debug(f"{i + 1:04d}: first_ip: {first_ip}, last_ip: {last_ip}")

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
                dict_ip_network_cc=dict_ip_network_cc,
                logger=debug_logger
            )
            upd_cc = match_cc if match_cc is not None else dao_ip_mst.CC_UNKNOWN
            logger.info(f"{i + 1:04d}: END   {target_ip}, {upd_cc}")
            if upd_cc == dao_ip_mst.CC_UNKNOWN:
                unknown_ip_list.append(target_ip)
        else:
            # 一致なし
            logger.warning(
                f"{i + 1:04d}: END   {target_ip}, RIR_ipv4_allocated no match."
            )
            unknown_ip_list.append(target_ip)


# 判明した国コードとネットワークアドレスIDの更新用クエリーパラメータ作成
def make_update_query_params(
        dict_ip_network_cc: Dict[str, IpNetworkWithCC]) -> List[Tuple[str, str, int]]:
    result: List[Tuple[str, str, int]] = []
    # 国コード判明分
    for key in dict_ip_network_cc.keys():
        ip_network_cc: IpNetworkWithCC = dict_ip_network_cc[key]
        network_id: Optional[int] = ip_network_cc.network_id
        # network_idは設定済みの想定 ※ NoneならBUG
        assert network_id is not None
        cc: str = ip_network_cc.country_code
        host_list: List[str] = ip_network_cc.ip_hosts
        for host_ip in host_list:
            # param = (ipアドレス, 国コード, ネットワークアドレスID)
            param: Tuple[str, str, int] = (host_ip, cc, network_id)
            result.append(param)
    return result


def batch_main():
    app_logger: Logger = logsetting.get_logger("match_network")

    parser = argparse.ArgumentParser()
    # 毎日のバッチから起動された場合はデフォルトで200件とする ※過去の実行でこれ以上にならない想定
    parser.add_argument("--fetch-limit", type=int, default=200,
                        help="Fetch target ip List count.")
    # fetch-limitが10件程度の場合に指定する ※大量のログが出力される
    parser.add_argument("--enable-debug", action="store_true",
                        help="Enable logger debug out.")
    args: argparse.Namespace = parser.parse_args()
    fetch_limit: int = args.fetch_limit
    enable_debug: bool = args.enable_debug
    app_logger.info(f"fetch-limit: {fetch_limit}, enable_debug: {enable_debug}")

    # ターゲットIPが属するネットワーク情報辞書オブジェクト
    dict_ip_network_cc: Dict[str, IpNetworkWithCC] = OrderedDict()
    # 国コードが不明なIPアドレスのリスト
    unknown_ip_list: List[str] = []

    db: Optional[pgdatabase.PgDatabase] = None
    try:
        db = pgdatabase.PgDatabase(DB_CONF_FILE, logger=None)
        conn: connection = db.get_connection()
        # ネットワークアドレス国コードテーブル件数
        match_network_rec_cnt: int = rec_count_in_match_network(
            conn, logger=app_logger if enable_debug else None
        )
        app_logger.info(f"match_network_rec_cnt: {match_network_rec_cnt}")
        # 国コードがNULLのIPアドレスを取得 ※大量にログが出力されるためloggerにNoneを設定する
        target_ip_list: List[str] = dao_ip_mst.get_ip_list_with_null_cc(
            conn, fetch_limit, logger=None
        )
        target_ip_list_size: int = len(target_ip_list)
        app_logger.info(f"target_ip_list.size: {target_ip_list_size}")

        if target_ip_list_size > 0:
            rir_table_matches_main(
                conn, match_network_rec_cnt, target_ip_list,
                dict_ip_network_cc, unknown_ip_list,
                logger=app_logger, enable_debug=enable_debug
            )
            # DEBUG出力: ネットワークアドレスと国コード検索後の辞書オブジェクト
            if enable_debug:
                app_logger.debug("After: rir_table_matches_main.dict_ip_network_cc")
                for key in dict_ip_network_cc.keys():
                    app_logger.debug(f"{key}: {dict_ip_network_cc[key]}")

            # 見つかった国コードとネットワークアドレスを一括登録する
            insert_match_network_main(
                conn, dict_ip_network_cc, logger=app_logger, enable_debug=enable_debug
            )
            # DEBUG
            if enable_debug:
                app_logger.debug("After: insert_match_network_main.dict_ip_network_cc")
                for key in dict_ip_network_cc.keys():
                    app_logger.debug(f"{key}: {dict_ip_network_cc[key]}")

            # 不正アクセスIPアドレス管理マスターの国コード列等の更新処理
            # (1) 判明した国コードとネットワーク
            match_params: List[Tuple[str, str, int]] = make_update_query_params(
                dict_ip_network_cc
            )
            if len(match_params) > 0:
                dao_ip_mst.bulk_update_cc(
                    conn, match_params, logger=app_logger if enable_debug else None
                )
            # (2) 国コート不明リスト: タプルのリストに変換
            if len(unknown_ip_list) > 0:
                unknown_params: List[Tuple[str]] = [(ip,) for ip in unknown_ip_list]
                dao_ip_mst.bulk_update_unknown(
                    conn, unknown_params, logger=app_logger if enable_debug else None
                )
            conn.commit()

        app_logger.info("Done.")
    except psycopg2.Error as db_err:
        app_logger.error(db_err)
        exit(1)
    except Exception as err:
        app_logger.error(err)
        exit(1)
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    batch_main()
