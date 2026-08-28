# 特定/常用查询模板 Reference

本文件记载特定的常用查询模式与复杂指标计算模板，辅助 NL2SQL 生成高质量 Metabase 报表模板。

---

## 1. 营期班级最新周基数查询

### 业务场景
在分析营期或班级维度的数据时，经常需要使用**最新周**的人数作为基数（如原始人数、授权人数、退费人数等），用于计算各类率值（如定金率、转化率、完课率）。

### 数据源
`warehouse.dws_lh_teaching_term_class_week` (`cw`)

### SQL 模板

```sql
-- CTE: 获取每个营期、班级的最新周基数数据
WITH latest_term_class_week AS (
  SELECT
    `cw`.`term_id`,
    `cw`.`class_id`,
    `cw`.`original_num`,  -- 最新的原始人数
    `cw`.`authorize_num`, -- 最新的授权人数
    `cw`.`refund_num`,    -- 最新的退费人数
    `cw`.`abs_week` AS `current_week`
  FROM (
    SELECT
      `cw`.`term_id`,
      `cw`.`class_id`,
      `cw`.`original_num`,
      `cw`.`authorize_num`,
      `cw`.`refund_num`,
      `cw`.`abs_week`,
      ROW_NUMBER() OVER (
        PARTITION BY `cw`.`term_id`, `cw`.`class_id`
        ORDER BY NVL(`cw`.`abs_week`, 0) DESC
      ) AS `r`
    FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
    WHERE 1=1
      [[ AND `cw`.`term_id` IN ({{term_ids}}) ]]
      [[ AND `cw`.`class_id` IN ({{class_ids}}) ]]
  ) `cw`
  WHERE `cw`.`r` = 1
)
```

---

## 2. 复购班级天指标率值计算（结合最新周基数）

### 业务场景
在复购班级天指标统计表 `dws_lh_teaching_repurchase_category_class_day` 中计算日维度的率值指标。
例如：**当天直播间定金率** = `直播间定金支付人数 (deposit_pay_live_num) / 最新周原始人数 (或授权人数)`

### SQL 模板

```sql
WITH latest_term_class_week AS (
  SELECT
    `cw`.`term_id`,
    `cw`.`class_id`,
    `cw`.`original_num`,  -- 最新的原始人数
    `cw`.`authorize_num`, -- 最新的授权人数
    `cw`.`refund_num`,    -- 最新的退费人数
    `cw`.`abs_week` AS `current_week`
  FROM (
    SELECT
      `cw`.`term_id`,
      `cw`.`class_id`,
      `cw`.`original_num`,
      `cw`.`authorize_num`,
      `cw`.`refund_num`,
      `cw`.`abs_week`,
      ROW_NUMBER() OVER (
        PARTITION BY `cw`.`term_id`, `cw`.`class_id`
        ORDER BY NVL(`cw`.`abs_week`, 0) DESC
      ) AS `r`
    FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
    WHERE 1=1
      [[ AND `cw`.`term_id` IN ({{term_ids}}) ]]
      [[ AND `cw`.`class_id` IN ({{class_ids}}) ]]
  ) `cw`
  WHERE `cw`.`r` = 1
)
SELECT
  `d`.`term_id`,
  `d`.`class_id`,
  `d`.`dt`,
  SUM(`d`.`deposit_pay_live_num`) AS `deposit_pay_live_num`, -- 直播间定金支付人数
  MAX(`w`.`original_num`)         AS `original_num`,         -- 最新原始人数基数
  MAX(`w`.`authorize_num`)        AS `authorize_num`,        -- 最新授权人数基数
  ROUND(
    SUM(`d`.`deposit_pay_live_num`) * 100.0 / NULLIF(MAX(`w`.`original_num`), 0),
    2
  ) AS `deposit_pay_live_rate`                              -- 当天直播间定金率 (%)
FROM `warehouse`.`dws_lh_teaching_repurchase_category_class_day` `d`
LEFT JOIN `latest_term_class_week` `w`
  ON `d`.`term_id` = `w`.`term_id`
 AND `d`.`class_id` = `w`.`class_id`
WHERE 1=1
  [[ AND `d`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `d`.`class_id` IN ({{class_ids}}) ]]
  [[ AND `d`.`dt` BETWEEN {{start_date}} AND {{end_date}} ]]
GROUP BY
  `d`.`term_id`,
  `d`.`class_id`,
  `d`.`dt`
ORDER BY
  `d`.`dt` DESC,
  `d`.`class_id`;
```

---

## 3. 率值计算规范与防错约定

## 3. 率值计算规范与防错约定

1. **除零保护**：使用 `NULLIF(denominator, 0)` 包裹分母，防止除零报错。
2. **百分比处理**：分子乘以 `100.0`，保留 2 位小数 `ROUND(..., 2)`，不追加 `%` 字符（由 Metabase 列格式处理）。
3. **最新周/最新状态提取**：针对多周数据表提取最新周基数，统一采用 `ROW_NUMBER() OVER (PARTITION BY term_id, class_id ORDER BY NVL(abs_week, 0) DESC)` 过滤 `r = 1`。
4. **Metabase 变量支持**：内层与外层均保持 `[[ AND ... IN ({{variable}}) ]]` 条件注入规范，确保筛选参数能正确透传并裁剪。
