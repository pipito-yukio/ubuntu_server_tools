#!/bin/bash

# sshサービスに関する前日のジャーナルログを所定のディレクトリに出力するスクリプト
# (利用想定) cron で 毎日 0:10 に実行される

next_day() {
   retval=$(date -d "$1 1 day" +'%F')
   echo "$retval"
}

before_day() {
   retval=$(date -d "$1 - 1 day" +'%F')
   echo "$retval"
}

HOME="/home/cronuser"
CMD="/usr/bin/journalctl"
GREP_KWD=": authentication failure;"
OUTPUT_DIR="$HOME/work/journal_logs"

# 引数(開始日付のみ)の有無で開始日付を設定する
start_day=
if [ $# -eq 0 ]; then
    # スクリプト実行日 ※cron実行を想定
   today=$(date +'%F')
    # 前日
   start_day=$(before_day "$today")
else
    # 指定日
   start_day="$1"
fi
end_datetime="$start_day 23:59:59"
file_name="AuthFail_ssh_$start_day.log"

echo $sudo_passwd | {
  sudo --stdin $CMD --since="$start_day" --until="$end_datetime" -u ssh.service -o short-iso | grep "$GREP_KWD" > "$OUTPUT_DIR/$file_name"
}
echo "Saved $file_name" 

