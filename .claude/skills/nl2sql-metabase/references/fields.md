# 派生字段定义

## 使用说明

本文件定义业务中常用的**派生字段**——由多个基础字段组合判断而来的新字段。

生成 SQL 时的处理规则：
1. 用户描述中出现业务术语（如"原始学员"）→ 先查本文件，命中则直接套用对应 SQL 表达式
2. 用户描述中出现"是否XXX"、"判断XXX"等新字段需求，但本文件未收录 → 根据用户描述的判断逻辑生成表达式，并提示用户可补充进本文件
3. 派生字段可直接用在 SELECT、WHERE、HAVING 中

每个派生字段的结构：
```
- **触发词**: 用户提问中可能出现的词汇
- **依赖表**: 需要哪张表的哪个别名
- **SQL 表达式**: 直接复制进 SELECT 的片段
- **业务说明**: 该字段的判断逻辑说明
```

---

## 学员维度派生字段

---

### is_original（是否原始学员）

- **触发词**: "原始学员"、"是否原始"、"原始人数"
- **依赖表**: `ods_lh_teaching_lh_teaching_student`，别名 `s`
- **SQL 表达式**:
  ```sql
  IF(
    `s`.`student_status` != 'abandon'
    AND IF(
      `s`.`student_status` NOT IN ('change_num'),
      IF(`s`.`student_status` = 'refunded', `s`.`add_robot_id` > 0, TRUE),
      FALSE
    ),
    1, 0
  ) AS `is_original`
  ```
- **业务说明**:
  - 排除废弃学员（student_status = 'abandon'）
  - 排除换号学员（student_status = 'change_num'）
  - 已退费学员（student_status = 'refunded'）中，只有已添加机器人（add_robot_id > 0）才算原始
  - 其余在读/毕业等状态均视为原始学员

**用法示例：统计各班级原始学员数**
```sql
SELECT
  `s`.`big_class_id`    AS `class_id`,
  `c`.`class_name`,
  SUM(
    IF(
      `s`.`student_status` != 'abandon'
      AND IF(
        `s`.`student_status` NOT IN ('change_num'),
        IF(`s`.`student_status` = 'refunded', `s`.`add_robot_id` > 0, TRUE),
        FALSE
      ),
      1, 0
    )
  ) AS `original_num`
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  [[ AND `s`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
GROUP BY `s`.`big_class_id`, `c`.`class_name`
```

---

<!--
新增派生字段模板（复制此块填写）：

### <字段名>（<中文说明>）

- **触发词**: "<词1>"、"<词2>"
- **依赖表**: `<表名>`，别名 `<alias>`
- **SQL 表达式**:
  ```sql
  <表达式> AS `<字段名>`
  ```
- **业务说明**: <判断逻辑的自然语言描述>

**用法示例：<场景>**
```sql
-- SQL
```
-->