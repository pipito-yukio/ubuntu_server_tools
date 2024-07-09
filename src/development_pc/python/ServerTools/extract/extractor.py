import re
from collections import Counter, OrderedDict
from typing import List

from util.file_util import file_read

"""
authentication failure
"""

# rhhost の後ろに何もないケースと "user=xxx"があるパターンがある
# : authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=218.92.0.96  user=root
# : authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=216.181.226.86
re_auth_fail: re.Pattern = re.compile(r"^.+?rhost=([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}).*$")


def extract_ip_list(log_file: str) -> List[str]:
    lines: List[str] = file_read(log_file)
    # 重複の可能性のあるIPリスト
    ip_list: List[str] = []
    for line in lines:
        mat: re.Match = re_auth_fail.search(line)
        if mat:
            ip_list.append(mat.group(1))
    return ip_list


def extract_over_ip_list(ip_list: List[str], appear_limit: int)-> OrderedDict[str, int]:
    ip_dict: OrderedDict[str, int] = OrderedDict()
    # 出現数カウント
    counter: Counter = Counter(ip_list)
    # ('20.244.134.31', 41)
    for (ip, appear_cnt) in counter.most_common():
        if appear_cnt >= appear_limit:
            ip_dict[ip] = appear_cnt
    return ip_dict
