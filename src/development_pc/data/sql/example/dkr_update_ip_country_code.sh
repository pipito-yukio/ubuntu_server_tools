#!/bin/bash

# IPアドレスに対応する国コードを更新するSQLを実行するスクリプト
#  ※ホスト側シェルスクリプト
#  [引数] 複数のUPDATE文が記述されたSQLファイルパス
#  ./dkr_update_ip_country_code.sh batch/upd_ip_cc_2024-07-15.sql

# 引数はCSVファイル必須
if [ $# -ne 1 ]; then
   echo "Require csv file!"
   exit 1
fi

# ホストOSから dockerコンテナ内のシェルスクリプトを実行するシェルスクリプト
# ./drk_update_ip_country_code.sh 
# 国コード更新SQLの一括実行 ※$HOME はホストOSのバッチ実行ユーザー
UPDATE_QUERIES="$HOME/data/sql/example/batch/$1"
docker exec -it postgres-16 sh -c "psql -Udeveloper example_pgdb < $UPDATE_QUERIES"

