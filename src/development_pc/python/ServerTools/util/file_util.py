import csv
import json
from typing import Any, Dict, List, Optional


def read_json(file_name: str) -> Dict[str, Any]:
    with open(file_name, 'r') as fp:
        data = json.load(fp)
    return data


def read_text(file_name: str) -> List[str]:
    lines: List[str] = []
    with open(file_name, 'r') as fp:
        for line in fp:
            lines.append(line)
    return lines


def write_text_lines(file_name: str, save_list: List[str],
                     append_file: bool = False) -> None:
    save_mode: str = 'a' if append_file else 'w'
    with open(file_name, save_mode) as fp:
        for save_line in save_list:
            fp.write(f"{save_line}\n")
        fp.flush()


def read_csv(file_name: str,
             skip_header=True, header_cnt=1) -> List[str]:
    with open(file_name, 'r') as fp:
        reader = csv.reader(fp, dialect='unix')
        if skip_header:
            for skip in range(header_cnt):
                next(reader)
        # リストをカンマ区切りで連結する
        csv_lines = [",".join(rec) for rec in reader]
    return csv_lines


def write_csv(
        file_name: str, save_list: List[str],
        header: Optional[str] = None) -> None:
    with open(file_name, 'w') as fp:
        if header is not None:
            fp.write(f"{header}\n")
        for save_line in save_list:
            fp.write(f"{save_line}\n")
        fp.flush()
