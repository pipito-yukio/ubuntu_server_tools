import argparse
import logging
import os
import re
from collections import Counter
from datetime import date
from typing import Any, List, Dict, Optional
import util.file_util as fu

"""
example.com サーバーでjournalctlでsshサービスに関連したログインエラーログファイルから
不正アクセスしているクライアントのIPアドレスとカウンターを抽出してCSVファイルに出力する
"""

CONF_FILE: str = os.path.join("conf", "export_csv_with_invalid_ip.json")

# rhhost の後ろに何もないケースと "user=xxx"があるパターンがある
# authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=218.92.0.96 user=root
# authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=216.181.226.86
re_auth_fail: re.Pattern = re.compile(
    r"^.+?rhost=([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}).*$"
)
# ファイル名のログ日付抽出
re_log_file: re.Pattern = re.compile(r"^AuthFail_ssh_(\d{4}-\d{2}-\d{2})\.log$")
FMT_OUT_CSV: str = "ssh_auth_error_{}.csv"
# CSV format
CSV_HEADER: str = '"log_date","ip_addr","appear_count"'


def extract_log_date(file_path: str) -> str:
    # ファイル名から日付を取得
    b_name: str = os.path.basename(file_path)
    f_mat: Optional[re.Match] = re_log_file.search(b_name)
    if f_mat:
        return f_mat.group(1)
    else:
        return date.today().isoformat()


def get_csv_path(s_date: str, out_csv_dir: str) -> str:
    save_name: str = FMT_OUT_CSV.format(s_date)
    return os.path.join(os.path.expanduser(out_csv_dir), save_name)


def file_read(file_name: str):
    with open(file_name, 'r') as fp:
        for ln in fp:
            yield ln


def batch_main():
    logging.basicConfig(format="%(message)s")
    app_logger = logging.getLogger(__name__)
    app_logger.setLevel(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", required=True, type=str, help="Log File name.")
    parser.add_argument("--show-top", type=int, help="Show top N.")
    parser.add_argument("--out-csv", action="store_true", help="Output csv.")
    args: argparse.Namespace = parser.parse_args()
    app_logger.info(args)

    is_out_csv: bool = args.out_csv
    f_path: str = os.path.expanduser(args.log_file)
    lines = file_read(f_path)
    # 出現回数設定
    conf: Dict[str, Any] = fu.read_json(CONF_FILE)
    # CSV出力するカウンター数
    out_count_limit: int = conf["out-count-limit"]
    # 表示する場合のTop N
    show_top: int = conf["show-top"]
    if args.show_top is not None:
        show_top = int(args.show_top)

    ip_list: List = []
    for line in lines:
        mat: Optional[re.Match] = re_auth_fail.search(line)
        if mat:
            ip_list.append(mat.group(1))
    list_size: int = len(ip_list)
    app_logger.info(f"ip_list.size: {list_size}")

    if list_size > 0:
        # 抽出した ip の出現数をカウント
        counter: Counter = Counter(ip_list)
        if not is_out_csv:
            # コンソール出力の場合: Top N
            for item in counter.most_common(show_top):
                app_logger.info(item)
        else:
            csv_list: List[str] = []
            log_date = extract_log_date(f_path)
            app_logger.info(f"log_date: {log_date}")
            # CSV出力: 出現回数が指定件数以上
            for (ip_addr, cnt) in counter.most_common():
                if cnt >= out_count_limit:
                    csv_line: str = f'"{log_date}","{ip_addr}",{cnt}'
                    csv_list.append(csv_line)
            app_logger.info(f"output_lines: {len(csv_list)}")
            save_path: str = get_csv_path(log_date, conf["csv-dir"])
            fu.write_csv(save_path, csv_list, header=CSV_HEADER)
            app_logger.info(f"Saved: {save_path}")


if __name__ == '__main__':
    batch_main()
