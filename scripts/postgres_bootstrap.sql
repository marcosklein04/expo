-- Ajustar estos valores antes de ejecutar en cada entorno.
-- 1) Nombre de DB
-- 2) Usuario de aplicacion
-- 3) Password fuerte y unica

CREATE DATABASE expo_kiosk ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C';
CREATE USER expo_kiosk_user WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE expo_kiosk TO expo_kiosk_user;

-- En Postgres 15+ el owner del esquema public no es publico por defecto.
\connect expo_kiosk
GRANT ALL ON SCHEMA public TO expo_kiosk_user;
ALTER SCHEMA public OWNER TO expo_kiosk_user;
