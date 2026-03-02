CREATE DATABASE IF NOT EXISTS expo_kiosk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'expo_kiosk_user'@'%' IDENTIFIED BY 'ExpoKiosk_2026_x7Qm9pL2';
GRANT ALL PRIVILEGES ON expo_kiosk.* TO 'expo_kiosk_user'@'%';
FLUSH PRIVILEGES;
