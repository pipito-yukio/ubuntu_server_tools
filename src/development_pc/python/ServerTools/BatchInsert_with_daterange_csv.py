import argparse
import glob
import logging
import os
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
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
※1 定期的な更新忘れを想定する
※2 DEBUGログは出力しない
[スキーマ] mainte
[テーブル]
  (1) 不正アクセスIPアドレステーブル
     unauth_ip_addr
  (2) 不正アクセスエラーカウントテーブル
     ssh_auth_error
"""


# データベース接続情報
DB_CONF_FILE: str = os.path.join("conf", "db_conn.json")


def check_date_range(from_date: str, to_date: str) -> bool:
    # 日付の大小チェック
    try:
        dt_from: date = date.fromisoformat(from_date)
        dt_to: date = date.fromisoformat(to_date)
        return dt_from <= dt_to
    except ValueError:
        return False


def extract_date_range(csv_files: List[str], from_date: str, to_date: str) -> List[str]:
    result: List[str] = []
    match_first: bool = False
    for f_name in csv_files:
        f_fields: Tuple[Any, Any] = os.path.splitext(f_name)
        f_name_only: str = f_fields[0]
        # to_date が含まれたCSVファイルなら追加して終了
        if match_first and f_name_only.endswith(to_date):
            result.append(f_name)
            break

        # 開始日が含まれたら開始フラグをTrueに設定
        if f_name_only.endswith(from_date):
            match_first = True

        # 開始フラグをTrueならファイル追加
        if match_first:
            result.append(f_name)

    return result


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
    exists_ipid_list: List[int] = bulk_exists_ssh_auth_error(
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


def csv_lines_insert(conn: connection,
                     csv_lines: List[str],
                     logger: Optional[logging.Logger] = None) -> None:
    try:
        # CSVから取得したIPアドレス(2列目)が登録済みかチェック
        ip_list: List[str] = [line.split(",")[1] for line in csv_lines]
        exists_ip_dict: Dict[str, int] = bulk_exists_ip_addr(conn, ip_list, logger=None)
        if logger is not None:
            logger.info(f"exists_ip_dict.size: {len(exists_ip_dict)}")

        # 登録済みIPアドレスを除外した追加登録用のレコードリストを作成
        reg_ip_datas: List[RegUnauthIpAddr] = get_register_ip_list(
            exists_ip_dict, csv_lines, logger=None
        )

        # unauth_ip_addrテーブルとssh_auth_errorテーブル登録トランザクション
        reg_ip_datas_cnt: int = len(reg_ip_datas)
        if logger is not None:
            logger.info(f"reg_ip_datas.size: {reg_ip_datas_cnt}")

        # 不正アクセスIPアドレステーブル新規登録
        if reg_ip_datas_cnt > 0:
            insert_unauth_ip_main(conn, exists_ip_dict, reg_ip_datas)

        # 不正アクセスカウンターテーブル登録用リスト
        ssh_auth_error_list: List[SshAuthError] = get_register_ssh_auth_error_list(
            exists_ip_dict, csv_lines
        )
        if logger is not None:
            logger.info(
                f"Register ssh_auth_error_list.size: {len(ssh_auth_error_list)}"
            )

        # 不正アクセスカウンターテーブルに新規
        if len(ssh_auth_error_list) > 0:
            insert_ssh_auth_error_main(conn, ssh_auth_error_list)
    except psycopg2.Error:
        raise
    except Exception:
        raise


def batch_main():
    app_logger: logging.Logger = logsetting.get_logger("batch_insert")
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    # CSVファイルが格納されているディレクトリ
    parser.add_argument("--csv-dir", type=str, required=True,
                        help="CSV file directory.")
    # レコード登録用CSVファイルの処理開始日付
    parser.add_argument("--from-date", type=str, required=True,
                        help="CSV file from date.")
    # レコード登録用CSVファイルの処理終了日付
    parser.add_argument("--to-date", type=str, required=True,
                        help="CSV file to date.")
    args: argparse.Namespace = parser.parse_args()
    # CSVディレクトリ
    csv_dir: str = args.csv_dir
    csv_dir_path: str
    if csv_dir.find("~") == 0:
        csv_dir_path = os.path.expanduser(csv_dir)
    else:
        csv_dir_path = csv_dir
    if not os.path.exists(csv_dir_path):
        app_logger.warning(f"{csv_dir_path} not found!")
        exit(1)

    # CSVファイルの開始日
    from_date: str = args.from_date
    to_date: str = args.to_date
    # 終了日が未指定なら当日
    if to_date is None:
        to_date = date.today().isoformat()

    app_logger.info(f"from-date: {from_date}, to-date: {to_date}")
    if not check_date_range(from_date, to_date):
        app_logger.error(
            f"Invalid date range: from_date={from_date}, to_date={to_date}"
        )
        exit(1)

    # CSVディレクトリ内のファイルリスト
    # 指定したディレクトリ内の全てのCSVファイル ※取得したファイルはソートされていない
    csv_files: List[str] = glob.glob(os.path.join(csv_dir_path, "ssh_auth_error_*.csv"))
    csv_files = sorted(csv_files)
    match_files: List[str] = extract_date_range(csv_files, from_date, to_date)
    if len(match_files) == 0:
        app_logger.warning(f"Not match ({from_date} 〜 {to_date}) csv files.")
        exit(0)

    app_logger.debug(match_files)

    # database
    db: Optional[pgdatabase.PgDatabase] = None
    try:
        db = pgdatabase.PgDatabase(DB_CONF_FILE, logger=None)
        conn: connection = db.get_connection()
        for filename in match_files:
            csv_lines: List[str] = fu.read_csv(filename)
            csv_line: int = len(csv_lines)
            app_logger.info(f"{filename}: {csv_line}")
            if len(csv_lines) > 0:
                csv_lines_insert(conn, csv_lines, logger=app_logger)
        # 正常終了したらコミット
        db.commit()
    except psycopg2.Error as err:
        if db is not None:
            db.rollback()
        app_logger.error(err)
    except Exception as err:
        if db is not None:
            db.rollback()
        app_logger.error(err)
    finally:
        if db is not None:
            db.close()    


if __name__ == '__main__':
    batch_main()
