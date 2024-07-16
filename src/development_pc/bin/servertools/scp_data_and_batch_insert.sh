#!/bin/bash

# サーバーで収集した不正アクセスログファイルをもとにデータベースに一括登録するスクリプト
# [前提条件]
#  (1)scpコマンドでサーバーからファイルをパスワードなしでコピーできること
#      ※クライアントPCの公開キーがサーバー側に設定済み
#  (2)PostgreSQL16デーベースのdockerコンテナが稼働していること
# [処理手順]
#  1. scpコマンドでサーバーから不正アクセスログファイルをローカルPCにコピーする
#  2. python仮想環境に入り下記 pythonスクリプトを実行
#     2-1. 不正アクセスログファイルからデータベース登録用のCSVファイルを出力する
#     2-2. データベース登録用のCSVファイルをもとに該当するテーブルに一括登録する


# 引数は対象日付のみ必須
if [ $# -ne 1 ]; then
   echo "Require log date!"
   exit 1
fi

# dockerコンテナ(コンテナ名: "postgres-16")の稼働をチェックする
postgres_16=$(docker ps | grep postgres-16)
# 82b11d2cb7bc   16-postgres   "docker-entrypoint.s…"   48 minutes ago   Up 48 minutes   0.0.0.0:5432->5432/tcp, :::5432->5432/tcp   postgres-16
if [ -z "$postgres_16" ]; then
   echo "docker postgres-16 container is not running!"
   exit 1
fi   

# サーバーから不正アクセスログファイルをコピー
log_date=$1
log_file="AuthFail_ssh_$log_date.log"
BASE_DIR="$HOME/Documents/exmaple"
LOG_DIR="$BASE_DIR/error_logs"
cd "$LOG_DIR"
exit_status=$?
if [ $exit_status -ne 0 ]; then
   exit 1
fi

scp "youruser@server_host:~/work/journal_logs/$log_file" .
exit_status=$?
cd ~
echo "scp $log_file >> exit_status=$exit_status"
if [ $exit_status -ne 0 ]; then
   echo "Warning $log_file scp fail!."
   exit $exit_status
fi

# python仮想環境 py_psycopg2 に入る
. ~/py_venv/py_psycopg2/bin/activate

# CSVファイル出力
cd ~/py_project/ServerTools
python ExportCSV_with_autherrorlog.py --log-file "$LOG_DIR/$log_file" --out-csv
exit_status=$?
echo "execute ExportCSV_with_autherrorlog.py >> exit_status=$exit_status"
if [ $exit_status -ne 0 ]; then
   echo "Error export CSV!"
   exit $exit_status
fi

# データベース内の該当するテーブルに一括登録
csv_path="$BASE_DIR/csv/ssh_auth_error_$log_date.csv"
python BatchInsert_with_csv.py --csv-file "$csv_path"

deactivate
echo "Done."
cd ~

