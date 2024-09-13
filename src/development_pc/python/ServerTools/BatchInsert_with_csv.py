import argparse
import logging
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extensions import connection

from db import pgdatabase
from dao.record.tabledata import RegUnauthIpAddr, SshAuthError
# unauth_ip_addr テーブル
from dao.unauth_ip_addr import (
    bulk_exists_ip_addr,
    bulk_insert_with_fetch as bulk_insert_into_unauth_ip_addr
)
# ssh_auth_error テーブル
from dao.ssh_auth_error import (
    bulk_exists_ssh_auth_error,
    bulk_insert_with_nofetch as bulk_insert_into_ssh_auth_error
)

import util.file_util as fu
from log import logsetting

"""
不正アクセスカウンターCSVファイルを読み込みし2つのテーブルに一括登録する
[スキーマ] mainte
[テーブル]
  (1) 不正アクセスIPアドレステーブル
     unauth_ip_addr
  (2) 不正アクセスエラーカウントテーブル
     ssh_auth_error
"""

# データベース接続情報
DB_CONF_FILE: str = os.path.join("conf", "db_conn.json")


def get_register_ip_list(
        exists_ip_dict: Dict[str, int],
        csv_lines: List[str],
        logger: Optional[logging.Logger] = None) -> List[RegUnauthIpAddr]:
    result: List[RegUnauthIpAddr] = []
    if len(exists_ip_dict) > 0:
        registered_cnt: int = 0
        for line in csv_lines:
            fields: List[str] = line.split(",")
            registered_id: Optional[int] = exists_ip_dict.get(fields[1])
            if registered_id is None:
                result.append(RegUnauthIpAddr(
                    ip_addr=fields[1], reg_date=fields[0])
                )
            else:
                registered_cnt += 1
        if registered_cnt > 0:
            if logger is not None:
                logger.info(f"Registered_count: {registered_cnt}")
    else:
        # 登録済みレコードがない場合はすべて登録
        for line in csv_lines:
            fields = line.split(",")
            result.append(RegUnauthIpAddr(
                ip_addr=fields[1], reg_date=fields[0])
            )
    return result


def get_register_ssh_auth_error_list(
        exists_ip_dict: Dict[str, int],
        csv_lines: List[str],
        logger: Optional[logging.Logger] = None) -> List[SshAuthError]:
    result: List[SshAuthError] = []
    for line in csv_lines:
        fields: List[str] = line.split(",")
        ip_id: Optional[int] = exists_ip_dict.get(fields[1])
        if ip_id is not None:
            #  当該日のIPアドレスは不正アクセスIPアドレステーブルに登録済み
            result.append(
                SshAuthError(
                    log_date=fields[0], ip_id=ip_id, appear_count=int(fields[2])
                )
            )
        else:
            # このケースはない想定
            if logger is not None:
                logger.warning(f"{fields[1]} is not regstered!")
    return result


def insert_unauth_ip_main(
        conn: connection,
        exists_ip_dict: Dict[str, int],
        reg_ip_list: List[RegUnauthIpAddr],
        logger: Optional[logging.Logger] = None, enable_debug=False) -> None:
    # namedtupleを辞書のタプルに変換
    params: Tuple[Dict[str, Any], ...] = tuple([asdict(rec) for rec in reg_ip_list])
    registered_ip_ids: Dict[str, int] = bulk_insert_into_unauth_ip_addr(
        conn, params, logger=logger
    )
    if logger is not None:
        logger.info(f"registered_ip_ids.size: {len(registered_ip_ids)}")
        if logger is not None and enable_debug:
            logger.debug(f"registered_ip_ids: {registered_ip_ids}")
    # 新たに登録されたIPアドレスとIDを追加する
    exists_ip_dict.update(registered_ip_ids)
    if logger is not None and enable_debug:
        logger.debug(f"update.exists_ip_dict:\n{exists_ip_dict}")


def insert_ssh_auth_error_main(
        conn: connection,
        ssh_auth_error_list: List[SshAuthError],
        logger: Optional[logging.Logger] = None, enable_debug=False) -> None:
    # 当該日にIP_IDが登録済みかどうかチェックする ※誤って同一CSVを実行した場合を想定
    #  先頭レコードから当該日取得
    log_date: str = ssh_auth_error_list[0].log_date
    #  チェック用の ip_id リスト生成
    ipid_list: List[int] = [int(reg.ip_id) for reg in ssh_auth_error_list]
    exists_ipid_list: List[int] = bulk_exists_record(
        conn, log_date, ipid_list, logger=logger if enable_debug else None
    )
    # 未登録の ip_id があれば登録レコード用のパラメータを生成
    if len(ipid_list) > len(exists_ipid_list):
        param_list: List[Any] = []
        for rec in ssh_auth_error_list:
            if rec.ip_id not in exists_ipid_list:
                # 当該日に未登録の ip_id のみのレコードの辞書オブジェクトを追加
                param_list.append(asdict(rec))
            else:
                if logger is not None and enable_debug:
                    logger.debug(f"Registered: {rec}")
        if len(param_list) > 0:
            if logger is not None and enable_debug:
                logger.debug(f"param_list: \n{param_list}")
            bulk_insert_into_ssh_auth_error(
                conn, tuple(param_list),
                logger=logger if enable_debug else None
            )
    else:
        if logger is not None:
            logger.info("ssh_auth_error テーブルに登録可能データなし.")


def batch_main():
    app_logger: logging.Logger = logsetting.get_logger("batch_insert")
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    # レコード登録用CSVファイル: ~/Documents/webriverside/csv/ssh_auth_error_[日付].csv
    parser.add_argument("--csv-file", type=str, required=True,
                        help="Insert CSV file path.")
    parser.add_argument("--enable-debug", action="store_true",
                        help="Enable logger debug out.")
    args: argparse.Namespace = parser.parse_args()
    csv_file: str = args.csv_file
    enable_debug: bool = args.enable_debug
    app_logger.info(f"csv-file: {csv_file}")

    # CSVファイルを開く
    csv_path = os.path.join(os.path.expanduser(csv_file))
    if not os.path.exists(csv_path):
        app_logger.error(f"FileNotFound: {csv_path}")
        exit(1)

    # CSVレコード: "log_date,ip_addr,appear_count"
    csv_lines: List[str] = fu.read_csv(csv_path)
    line_cnt: int = len(csv_lines)
    # CSVファイル行数
    app_logger.info(f"csv: {line_cnt} lines.")
    if line_cnt == 0:
        app_logger.warning("Empty csv record.")
        exit(0)

    # database
    db: Optional[pgdatabase.PgDatabase] = None
    try:
        db = pgdatabase.PgDatabase(DB_CONF_FILE)
        conn: connection = db.get_connection()

        # CSVから取得したIPアドレス(2列目)が登録済みかチェック
        ip_list: List[str] = [line.split(",")[1] for line in csv_lines]
        exists_ip_dict: Dict[str, int] = bulk_exists_ip_addr(
            conn, ip_list, logger=app_logger)
        app_logger.info(f"exists_ip_dict.size: {len(exists_ip_dict)}")
        if enable_debug:
            app_logger.debug(f"exists_ip_dict: {exists_ip_dict}")

        # 登録済みIPアドレスを除外した追加登録用のレコードリストを作成
        reg_ip_datas: List[RegUnauthIpAddr] = get_register_ip_list(
            exists_ip_dict, csv_lines, logger=app_logger
        )

        # unauth_ip_addrテーブルとssh_auth_errorテーブル登録トランザクション
        reg_ip_datas_cnt: int = len(reg_ip_datas)
        app_logger.info(f"reg_ip_datas.size: {reg_ip_datas_cnt}")

        # 不正アクセスIPアドレステーブルに新規登録
        if reg_ip_datas_cnt > 0:
            insert_unauth_ip_main(
                conn, exists_ip_dict, reg_ip_datas,
                logger=app_logger, enable_debug=enable_debug
            )

        # 不正アクセスカウンターテーブル登録用リスト
        ssh_auth_error_list: List[SshAuthError] = get_register_ssh_auth_error_list(
            exists_ip_dict, csv_lines, logger=app_logger
        )
        app_logger.info(
            f"Register ssh_auth_error_list.size: {len(ssh_auth_error_list)}"
        )

        # 不正アクセスカウンターテーブルに新規
        if len(ssh_auth_error_list) > 0:
            insert_ssh_auth_error_main(
                conn, ssh_auth_error_list,
                logger=app_logger, enable_debug=enable_debug
            )
        # 両方のテーブル登録で正常終了したらコミット
        db.commit()
    except Exception as exp:
        if db is not None:
            db.rollback()
        app_logger.error(exp)
        exit(1)
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    batch_main()
