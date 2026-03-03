-- Ajustar estos valores antes de ejecutar en cada entorno.
-- 1) Nombre de DB
-- 2) Usuario de aplicacion
-- 3) Password fuerte y unica

CREATE DATABASE IF NOT EXISTS expo_kiosk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'expo_kiosk_user'@'%' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON expo_kiosk.* TO 'expo_kiosk_user'@'%';
FLUSH PRIVILEGES;
