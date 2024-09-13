-- 2024-09-12 国コードと和名国名、英語名マスター
CREATE TABLE mainte.country_code_name_mst(
   country_code CHAR(2) PRIMARY KEY,
   japanese_name VARCHAR(32) NOT NULL,
   public_name VARCHAR(128) NOT NULL
);
ALTER TABLE mainte.country_code_name_mst OWNER TO developer;

