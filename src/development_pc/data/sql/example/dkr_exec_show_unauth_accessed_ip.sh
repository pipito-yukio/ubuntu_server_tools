#!/bin/bash

# ホストOSから dockerコンテナ内のシェルスクリプトを実行するシェルスクリプト
# 検索期間で ipアドレスの出現回数が3回以上のIPアドレスを出力する
# (例) ./dkr_exec_show_unauth_accessed_ip.sh 2024-06-01 2024-06-30

script_name_in_container="show_unauth_accessed_ip_for_morethan_3days.sh"
# コンテナ内で実行する場合は絶対パス
scrpit_path_in_container="$HOME/data/sql/example/${script_name_in_container}"

# 実行中のコンテナ内で、新しいコマンドを実行
# https://docs.docker.jp/engine/reference/commandline/exec.html
#  Docs » コマンドライン リファレンス » Docker CLI (docker) » docker exec
#   docker exec
# [補足説明] ...が、docker exec -ti my_container sh -c "echo a && echo b" は動作します 
docker exec -it postgres-16 sh -c "${scrpit_path_in_container} ${1} ${2}"

