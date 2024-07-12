#!/bin/bash

# dockerコンテナ内の psqlでクエリを実行するシェルスクリプト
#  ※dockerコンテナ内で実行する必要がある
# 検索期間で ipアドレスの出現回数が3回以上のIPアドレスを出力する
# (例) 2024-06-01 2024-06-30

# docker コンテナ内の bash (16-alpine) では下記の整形フォーマットは使えない
# $(date -d "$1 1 day" +'%F')

echo "[検索期間] $1 〜 $2"

cat<<-EOF | psql -Udeveloper example_pgdb --tuples-only
WITH ip_cnt_in_days_over as(
SELECT
   ip_addr,ip_number,count(ip_addr) as ip_cnt_in_days
FROM
   -- VIEW with appear count > 30
   mainte.v_ip_appear_over_30
WHERE
   log_date BETWEEN '${1}' AND '${2}'
group by ip_addr,ip_number
),
-- ip_cnt_in_days が3日以上出現するIPアドレスの集合
ip_all_day as(
SELECT ip_addr FROM ip_cnt_in_days_over WHERE ip_cnt_in_days >= 3 ORDER BY ip_number
)
-- 検索期間で 3日以上不正アクセスを受けたIPアドレスをログ収集日を含め出力
SELECT
   log_date, ip_addr,appear_count
FROM
   mainte.v_ip_inner_joined
WHERE
   log_date BETWEEN '${1}' AND '${2}'
   AND
   ip_addr in (SELECT * FROM ip_all_day)
-- IPアドレス(数値)順 > ログ日付順
ORDER BY ip_number, log_date;   
EOF
