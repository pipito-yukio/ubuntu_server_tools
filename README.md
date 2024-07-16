# ubuntu_server_tools

自宅サーバー(Ubuntu Server 24.04)のセキュリティを管理する運用ツール集

自宅サーバーを運用していると日々不特定多数のクライアントから不正アクセスを頻繁に受けています。

対策としては継続的(3〜4日以上)かつ1日あたりの不正アクセス回数(30回以上)の多いクライアントIPをバケットフィルタリングの対象にしています。

### ソースコードのディレクトリ構成

```
└── src
    ├── development_pc      # A) クライアントPCで実行するスクリプト類
    │   ├── data            #  1. SQLスクリプト
    │   │   └── sql        #
    │   ├── docker          #  2. PostgreSQL16サーバー用 docker コンテナ生成ソース 
    │   └── python          #  3. pythonスクリプト
    │       └── ServerTools #    3-1. サーバーで収集したログをもとにデータベース一括登録
    └── server_pc            # B) サーバー側で実行するスクリプト類
        ├── logs             #  1. サンプルログファイル
        └── scripts          #  2. シェルスクリプト
            ├── bin          #  
            └── var         
                └── spool
                    └── cron
                        └── crontabs
```

## 実行環境

+ サーバーPC
  + Ubuntu Server 24.04

+ 開発PC
  + Ubuntu Desktop 22.04


## 1. データベース

不正アクセスのIPアドレスとアクセス回数を管理するデータベースとして **PostgreSQL 16** を dockerコンテナ内で稼働させています。

### 1-1. dockerコンテナ生成用ソース

PostgreSQL 16 データベースコンテナ  
※ initdbディレクトリにテーブル生成用SQLファイルを入れておくとテーブルも同時に生成されますが、運用環境作成時に実行しています。

```
src/development_pc/docker/
├── .env
├── Dockerfile
├── docker-compose.yml
└── initdb
    └── 10_createdatabase.sql  # コンテナビルド時にデータベース作成
```

### 1-2. テーブル生成用ソース

運用環境作成時にでテーブル生成用のSQLを実行してテーブルを作成します。

```
src/development_pc/data/sql
└── example
    ├── 11_createtables.sql    # 不正アクセスIPアドレス管理テーブル生成
    ├── 12_add_createview.sql　# ビューの定義
    ├── dkr_exec_show_unauth_accessed_ip.sh
    └── show_unauth_accessed_ip_for_morethan_3days.sh
```

**不正アクセスIP管理テーブル生成クエリ** ```11_createtables.sql```  
※テーブルのカラム定義のみ下記に示します。

```11_createtables.sql
CREATE SCHEMA mainte;

-- 不正アクセスされたIPアドレス管理テーブル
CREATE TABLE mainte.unauth_ip_addr(
   id INTEGER NOT NULL,
   ip_addr VARCHAR(15) NOT NULL,
   reg_date DATE NOT NULL,
   ip_number BIGINT NOT NULL,
   country_code CHAR(2),
   dropped_date DATE
);
... 一部省略 ...
-- 不正アクセスされたIPアドレスの出現回数管理テーブル
CREATE TABLE mainte.ssh_auth_error(
   log_date DATE NOT NULL,
   ip_id INTEGER NOT NULL,
   appear_count INTEGER NOT NULL
);
```



## 2. 不正アクセスのログ収集

journalctlログ(対象: ssh.service) から取得された不正アクセスされたログの一例

```bash
2024-06-12T20:57:27+09:00 examplehost sshd[102632]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=103.77.241.34  user=root
2024-06-12T20:57:30+09:00 examplehost sshd[102632]: Failed password for root from 103.77.241.34 port 57052 ssh2
2024-06-12T20:57:36+09:00 examplehost sshd[102632]: Connection closed by authenticating user root 103.77.241.34 port 57052 [preauth]
2024-06-12T20:57:55+09:00 examplehost sshd[102634]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=103.77.241.34  user=root
2024-06-12T20:57:58+09:00 examplehost sshd[102634]: Failed password for root from 103.77.241.34 port 36960 ssh2
2024-06-12T20:58:04+09:00 examplehost sshd[102634]: Connection closed by authenticating user root 103.77.241.34 port 36960 [preauth]
```

さらにpythonスクリプトで集計処理しやすくなるよう下記のようにログを限定します

```bash
2024-06-12T20:57:55+09:00 localhost.webriverside sshd[102634]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=103.77.241.34  user=root
2024-06-12T20:58:21+09:00 localhost.webriverside sshd[102636]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=103.77.241.34  user=root
```

+ 上記のログを出力するスクリプト  
**```src/server_pc/scripts/bin/ssh_auth_error_log.sh```**

+ 毎日翌日の0時10分に上記スクリプトを実行するcron  
**```src/server_pc/scripts/var/spool/cron/crontabs/cronuser```**


## 3. テーブル登録処理

運用管理用PC (デスクトップOS) で pythonスクリプトを実行。

### 3-1. テーブル登録用CSVファイル生成

不正アクセスログからテーブル登録用のCSVファイルを生成するpythonスクリプト  
**```src/python/ServerTools/ExportCSV_with_autherrorlog.py```**

生成したCSVの内容 ※1日あたり不正アクセス回数が30回超のIPアドレス
```
"log_date","ip_addr","appear_count"
"2024-06-10","45.246.204.41",467
"2024-06-10","36.108.171.189",373
"2024-06-10","165.22.85.249",283
"2024-06-10","223.108.114.238",281
"2024-06-10","218.92.0.22",83
"2024-06-10","36.64.232.117",49
"2024-06-10","82.151.65.155",41
"2024-06-10","20.244.134.31",41
"2024-06-10","165.232.115.144",40
"2024-06-10","43.136.95.69",38
"2024-06-10","122.46.163.188",33
"2024-06-10","60.188.49.52",31
```


### 3-2. テーブル一括登録

上記 3-1で生成したCSVファイルからテーブルに一括登録するpythonスクリプト  
**```src/python/ServerTools/BatchInsert_with_csv.py```**



### 参考URL

PostgreSQL 16 に関しては下記日本語サイトを参考にしています。

+ PostgreSQL PostgreSQL 16.0文書
    + [第43章 PL/pgSQL — SQL手続き言語](https://www.postgresql.jp/document/16/html/plpgsql.html)
    + [SQLコマンド CREATE FUNCTION](https://www.postgresql.jp/document/16/html/sql-createfunction.html)
    + [第43章 PL/pgSQL — SQL手続き言語 43.10. トリガ関数](https://www.postgresql.jp/document/16/html/sql-createfunction.html)


Dockerに関してはコンテナ作成が容易なので Compose を使っています。
+ 公式ドキュメント
    + [Manuals / Docker Compose / install / Install the Compose plugin](https://docs.docker.com/compose/install/linux/)
    + [Postgresドッカーの公式イメージの使用方法](https://www.docker.com/ja-jp/blog/how-to-use-the-postgres-docker-official-image/#Start-a-Postgres-instance)  
    ※自動的に日本語に翻訳された公式ドキュメントのようですが、日本語訳が微妙です。
    + [postgres Docker Official Image
](https://hub.docker.com/_/postgres)  
※オフィシャルイメージ。どのバージョンを使うかはこのサイトを見ないとわかりません。

### 参考書

```
「ビックデータ分析・活用のためのＳＱＬレシピ」
  Chapter 3 | データ加工のためのSQL  
     3-2-6 IPアドレスを扱う
```

<div>
<img width="300" src="images/top/book_BigDataSQLKatuyou.jpg">
</div>
<br/>

10年以上前の発行ながらいまでも PostgreSQL のバイブル。

<div>
<img width="300" src="images/top/book_postgreSQL.jpg">
</div>
<br/>

発行から10年くらい過っていますが今でも役に立っています。  
※ 最近のUbuntu なら Firewalldをインストールすることで ufw を使わないパケットフィルタリングが可能 

```
Chapter1 systemd
   1.6 ジャーナルの制御 (journalctl)

Chapter3 Firewalld
   3.2 firewall-cmd によるパケットフィルタリング
   3.4 フィルタリングルールの設定
```

<div>
<img width="300" src="images/top/book_CentOS7.jpg">
</div>
<br/>
