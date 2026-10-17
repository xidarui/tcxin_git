
-- ============================================================
-- 知药 · 智能服药提醒系统  数据库结构
-- MySQL 8.0 / utf8mb4
--
-- 四张表及关系：
--   medication    药品字典        (1)
--   alarm_plan    提醒计划        (N) → medication.id   级联删除
--   dose_log      服药记录        (N) → alarm_plan.id   计划删了置空，历史保留
--   chat_message  对话历史
--
-- 首次使用（用管理员账号执行一次）：
--   CREATE DATABASE IF NOT EXISTS pill_reminder
--     CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
--   CREATE USER IF NOT EXISTS 'dev_app'@'localhost' IDENTIFIED BY 'your-password';
--   GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
--     ON pill_reminder.* TO 'dev_app'@'localhost';
--
-- 然后用业务账号导入本文件：
--   mysql -u dev_app -p pill_reminder < sql/schema.sql
-- ============================================================

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `alarm_plan`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alarm_plan` (
  `id` int NOT NULL AUTO_INCREMENT,
  `medication_id` int NOT NULL COMMENT '关联药品',
  `remind_time` time NOT NULL COMMENT '提醒时刻 HH:MM',
  `repeat_daily` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否每天重复',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `note` text NOT NULL COMMENT '如 饭后服用',
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `medication_id` (`medication_id`),
  KEY `ix_alarm_plan_enabled` (`enabled`),
  KEY `ix_alarm_plan_time` (`remind_time`),
  CONSTRAINT `alarm_plan_ibfk_1` FOREIGN KEY (`medication_id`) REFERENCES `medication` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `chat_message`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_message` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role` varchar(20) NOT NULL COMMENT 'system / user / assistant',
  `content` text NOT NULL,
  `source` varchar(20) NOT NULL DEFAULT 'text' COMMENT '输入来源: text 文字 / ocr 拍照 / voice 语音 / mixed 混合',
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_chat_message_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dose_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dose_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plan_id` int DEFAULT NULL COMMENT '关联计划，计划被删后置空以保留历史',
  `medication_name` varchar(100) NOT NULL COMMENT '药品名快照，避免联表',
  `scheduled_at` datetime NOT NULL COMMENT '应服药时间',
  `taken_at` datetime DEFAULT NULL COMMENT '实际服药时间',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending 待服 / taken 已服 / missed 漏服 / skipped 跳过',
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `plan_id` (`plan_id`),
  KEY `ix_dose_log_status` (`status`),
  KEY `ix_dose_log_scheduled` (`scheduled_at`),
  CONSTRAINT `dose_log_ibfk_1` FOREIGN KEY (`plan_id`) REFERENCES `alarm_plan` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `medication`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `medication` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '药品名称',
  `dosage` varchar(100) NOT NULL DEFAULT '' COMMENT '单次剂量，如 1粒/5ml',
  `note` text NOT NULL COMMENT '备注、注意事项',
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

