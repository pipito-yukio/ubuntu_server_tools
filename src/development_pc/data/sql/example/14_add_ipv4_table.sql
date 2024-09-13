-- 2024-08-30 DROP追加
DROP TABLE IF EXISTS mainte.RIR_ipv4_allocated CASCADE;
DROP TABLE IF EXISTS mainte.RIR_registory_mst;
-- 2024-08-06 レジストリ名テーブル追加
-- name: {afrinic,apnic,arin,iana,lacnic,ripencc}
-- https://www.apnic.net/about-apnic/corporate-documents/documents/
--     resource-guidelines/rir-statistics-exchange-format/
CREATE TABLE mainte.RIR_registory_mst(
   id SMALLINT PRIMARY KEY,
   name VARCHAR(8) NOT NULL
);

INSERT INTO mainte.RIR_registory_mst(id, name) VALUES 
   (1,'apnic')
  ,(2,'afrinic')
  ,(3,'arin')
  ,(4,'lacnic')
  ,(5,'ripencc')
  ,(6,'iana');

-- APNICで公開している各国に割り当てているIPアドレス情報からipv4アドレスのみを抽出したマスタテーブル
-- (変更) region -> registry
CREATE TABLE mainte.RIR_ipv4_allocated(
   ip_start VARCHAR(15) NOT NULL,
   ip_count INTEGER NOT NULL,
   country_code CHAR(2) NOT NULL,
   allocated_date DATE NOT NULL,
   registry_id SMALLINT NOT NULL
);

ALTER TABLE mainte.RIR_ipv4_allocated ADD CONSTRAINT pk_RIR_ipv4_allocated
  PRIMARY KEY (ip_start);
ALTER TABLE mainte.RIR_ipv4_allocated ADD CONSTRAINT fk_RIR_ipv4_allocated_registry
  FOREIGN KEY (registry_id) REFERENCES mainte.RIR_registory_mst (id);

ALTER TABLE mainte.RIR_registory_mst OWNER TO developer;
ALTER TABLE mainte.RIR_ipv4_allocated OWNER TO developer;

