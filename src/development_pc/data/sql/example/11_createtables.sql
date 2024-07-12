-- このクエリー実行前に予めスキーマをドロップしておく
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

-- シーケンス定義 ※OWNEDでテーブルを削除するとシーケンスも削除される
CREATE SEQUENCE mainte.seq_ip_addr_id OWNED BY mainte.unauth_ip_addr.id;
-- カラムidのデフォルト値をシーケンスに変更
ALTER TABLE mainte.unauth_ip_addr ALTER id SET DEFAULT nextval('mainte.seq_ip_addr_id');
ALTER TABLE mainte.unauth_ip_addr ADD CONSTRAINT pk_unauth_ip_addr PRIMARY KEY (id);
-- IPアドレスはユニーク
CREATE UNIQUE INDEX idx_ip_addr ON mainte.unauth_ip_addr(ip_addr);

-- PostgreSQL PostgreSQL 16.0文書: 第43章 PL/pgSQL — SQL手続き言語
-- https://www.postgresql.jp/document/16/html/plpgsql.html
-- SQLコマンド CREATE FUNCTION
-- https://www.postgresql.jp/document/16/html/sql-createfunction.html
-- PostgreSQL 16.0文書 第43章 PL/pgSQL — SQL手続き言語 43.10. トリガ関数
-- https://www.postgresql.jp/document/16/html/sql-createfunction.html

-- ip_number列計算関数: ip_addr をもとにソート用の数値を計算する
CREATE FUNCTION mainte.compute_ip_number(ip_addr text)
   RETURNS BIGINT
   LANGUAGE plpgsql
AS $$
DECLARE
   IP_NUM_1 BIGINT;
   IP_NUM_2 BIGINT;
   IP_NUM_3 BIGINT;
   IP_NUM_4 BIGINT;
BEGIN
   IP_NUM_1 := CAST(split_part(ip_addr,'.',1) AS INTEGER) * 2^24;
   IP_NUM_2 := CAST(split_part(ip_addr,'.',2) AS INTEGER) * 2^16;
   IP_NUM_3 := CAST(split_part(ip_addr,'.',3) AS INTEGER) * 2^8;
   IP_NUM_4 := CAST(split_part(ip_addr,'.',4) AS INTEGER) * 2^0;
   RETURN IP_NUM_1 + IP_NUM_2 + IP_NUM_3 + IP_NUM_4;
END $$;

-- トリガー関数: ip_addr から ip_numberを計算し当該カラムに設定する
CREATE FUNCTION mainte.calc_and_set_ip_number()
   RETURNS trigger
   LANGUAGE plpgsql
AS $$
DECLARE
   IP_NUM BIGINT;
BEGIN
   -- NEW: INSERT/UPDATE操作によって更新されたレコードの値
   IP_NUM := mainte.compute_ip_number(NEW.ip_addr);
   NEW.ip_number := IP_NUM;
   RETURN NEW;
END $$;

-- トリガー定義
-- (1) INSERT 前に ip_number を計算し設定する
CREATE TRIGGER trigger_insert_set_ip_number BEFORE INSERT
   ON mainte.unauth_ip_addr FOR EACH ROW
   EXECUTE PROCEDURE mainte.calc_and_set_ip_number();

-- Creating a PostgreSQL Trigger with a When Condition
-- https://www.postgresqltutorial.com/postgresql-triggers/postgresql-trigger-when-condition/
-- (2) UPDATE 前に ip_addrが変更されたら ip_number を再計算し設定する
CREATE TRIGGER trigger_update_set_ip_number BEFORE UPDATE
   ON mainte.unauth_ip_addr FOR EACH ROW
   WHEN (OLD.ip_addr <> NEW.ip_addr)
   EXECUTE PROCEDURE mainte.calc_and_set_ip_number();

-- 不正アクセスされたIPアドレスの出現回数管理テーブル
CREATE TABLE mainte.ssh_auth_error(
   log_date DATE NOT NULL,
   ip_id INTEGER NOT NULL,
   appear_count INTEGER NOT NULL
);

ALTER TABLE mainte.ssh_auth_error ADD CONSTRAINT pk_ssh_auth_error PRIMARY KEY (log_date, ip_id);
ALTER TABLE mainte.ssh_auth_error ADD CONSTRAINT fk_ssh_auth_error FOREIGN KEY (ip_id) REFERENCES mainte.unauth_ip_addr (id);

ALTER SCHEMA mainte OWNER TO developer;
ALTER TABLE mainte.unauth_ip_addr OWNER TO developer;
ALTER TABLE mainte.seq_ip_addr_id OWNER TO developer;
ALTER TABLE mainte.ssh_auth_error OWNER TO developer;
ALTER FUNCTION mainte.compute_ip_number(text) OWNER TO developer;
ALTER FUNCTION mainte.calc_and_set_ip_number() OWNER TO developer;

