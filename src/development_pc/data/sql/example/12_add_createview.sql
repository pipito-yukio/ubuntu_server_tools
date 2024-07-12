-- 2024-07-10
DROP VIEW IF EXISTS mainte.v_ip_inner_joined;
DROP VIEW IF EXISTS mainte.v_ip_appear_over_30;

-- mainte.ssh_auth_error INNER JOIN mainte.unauth_ip_addr 
CREATE VIEW mainte.v_ip_inner_joined AS
SELECT
   log_date, ip_addr, ip_number, appear_count
FROM
   mainte.ssh_auth_error sae
   INNER JOIN mainte.unauth_ip_addr ip_t
   ON sae.ip_id = ip_t.id;

-- inner joined appear_count over 30
CREATE VIEW mainte.v_ip_appear_over_30  AS
SELECT
   log_date, ip_addr, ip_number, appear_count
FROM
   mainte.v_ip_inner_joined
WHERE
   appear_count > 30;

ALTER TABLE mainte.v_ip_inner_joined OWNER TO developer;
ALTER TABLE mainte.v_ip_appear_over_30 OWNER TO developer;

