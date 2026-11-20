/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!50503 SET character_set_client = utf8mb4 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
-- 日电量对账：独立日总量 + 缺测小时上限；补值只存于 recon_versions.result，不写入 samples，故始终不进入训练
CREATE TABLE IF NOT EXISTS `recon_days` (
  `id` int NOT NULL AUTO_INCREMENT,
  `day` varchar(10) NOT NULL,
  `daily_total` float NOT NULL,
  `upper_limits` json NOT NULL,
  `active_version` int DEFAULT NULL,
  `status` varchar(20) DEFAULT 'open',
  PRIMARY KEY (`id`),
  UNIQUE KEY `day` (`day`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE IF NOT EXISTS `recon_versions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `recon_id` int NOT NULL,
  `version_no` int NOT NULL,
  `state` varchar(20) DEFAULT 'pending',
  `input_snapshot` json DEFAULT NULL,
  `result` json DEFAULT NULL,
  `error` text,
  `created_by` varchar(100) DEFAULT NULL,
  `created` varchar(40) DEFAULT NULL,
  `reason` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_recon_version` (`recon_id`,`version_no`),
  CONSTRAINT `recon_versions_ibfk_1` FOREIGN KEY (`recon_id`) REFERENCES `recon_days` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
