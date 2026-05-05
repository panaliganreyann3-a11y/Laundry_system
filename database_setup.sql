-- XAMPP / phpMyAdmin bootstrap for this Django project.
-- Import this first, then run Django migrations to create all tables.

CREATE DATABASE IF NOT EXISTS `laundry_db`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `laundry_db`;

-- Optional: if you do not want to use XAMPP's root MySQL account,
-- uncomment these lines and update .env to DB_USER=laundry_user and DB_PASSWORD=laundry_pass.
-- CREATE USER IF NOT EXISTS 'laundry_user'@'localhost' IDENTIFIED BY 'laundry_pass';
-- GRANT ALL PRIVILEGES ON `laundry_db`.* TO 'laundry_user'@'localhost';
-- FLUSH PRIVILEGES;
