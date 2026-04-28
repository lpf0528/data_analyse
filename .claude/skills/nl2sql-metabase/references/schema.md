# Schema Reference — warehouse 数据库

## 表元数据协议说明

每张表用以下结构声明约束，SKILL.md 中的规则引擎会读取并应用这些元数据：

```
- **别名**: 推荐别名
- **use_for**: 适合回答哪类问题（用于表选择决策）
- **required_filters**: 使用此表必须注入的强制条件（无 [[]]），CTE 型表则为固定 WITH 写法
- **examples**: 该表的典型 SQL 用法（1-2 个）
```

---

## 外键关系

```
dim_lh_basic_team.id                         ↔  dim_lh_teaching_class_term.tid
dim_lh_basic_team.camp_id                    ↔  dwd_lh_classes.camp_id
dim_lh_teaching_class_term.id                ↔  dwd_lh_classes.camp_term_id
dim_lh_teaching_class_term.id                ↔  ods_lh_teaching_lh_teaching_student.term_id
dim_lh_teaching_class_term.id                ↔  dws_lh_teaching_term_class_week.term_id
dwd_lh_classes.id                            ↔  ods_lh_teaching_lh_teaching_student.big_class_id
dwd_lh_classes.id                            ↔  dws_lh_teaching_term_class_week.class_id
ods_mdb_account_main_relation.object_id      ↔  ods_lh_teaching_lh_teaching_student.account_id
```

---

## 基础维度表

### dim_lh_basic_team（团队表）

- **别名**: `t`
- **use_for**: 定义不同的团队/训练营，其余数据表都使用camp_id或者tid实现数据的隔离
- **required_filters**:
  ```sql
  AND `t`.`id` = {{tid}}
  AND `t`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 团队id（PK），其他表对应 tid 字段 |
| name | varchar | 团队名称 |
| camp_id | int | 训练营id |

---

### dim_lh_teaching_class_term（营期表）

- **别名**: `ct`
- **use_for**: 每个团队/训练营下定义不同的营期，实现不同营期之间的数据隔离，对比不同营期下所有班级汇总的数据
- **required_filters**:
  ```sql
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 营期id（PK），其他表对应 term_id/camp_term_id 字段 |
| tid | int | 团队id → dim_lh_basic_team.id |
| camp_id | int | 训练营id |
| rank | int | 第N期（同个团队/训练营下rank从1开始递增） |
| start_time | datetime | 开始招生时间 |
| op_start_time | datetime | 开营时间 |
| op_end_time | datetime | 结营时间 |
| close_term_time | datetime | 营期关闭时间 |

**示例 1：查询所有营期列表**
```sql
SELECT
  `ct`.`id`   AS `term_id`,
  `ct`.`rank` AS `term_rank`,
  `ct`.`op_start_time`,
  `ct`.`op_end_time`
FROM `warehouse`.`dim_lh_teaching_class_term` `ct`
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  [[ AND `ct`.`id` IN ({{term_ids}}) ]]
ORDER BY `ct`.`rank`
```

---

### dwd_lh_classes（班级表）

- **别名**: `c`
- **use_for**: 每个营期下定义不同的班级，实现不同班级之间的数据隔离，对比不同班级下所有学员汇总的数据
- **required_filters**:
  ```sql
  AND `c`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 班级id（PK） |
| camp_id | int | 训练营id |
| camp_term_id | int | 营期id → dim_lh_teaching_class_term.id |
| class_name | varchar | 班级名称 |
| state | varchar | 枚举：normal=正常, invalid=无效, deleted=已删除 |

**示例 1：查询某营期下所有有效班级**
```sql
SELECT
  `c`.`id`         AS `class_id`,
  `c`.`class_name`
FROM `warehouse`.`dwd_lh_classes` `c`
WHERE 1=1
  AND `c`.`camp_id` = {{camp_id}}
  AND `c`.`state` = 'normal'
  [[ AND `c`.`camp_term_id` IN ({{term_ids}}) ]]
ORDER BY `c`.`class_name`
```

---

### ods_lh_teaching_lh_teaching_student（学员明细表）

- **别名**: `s`
- **use_for**: 班级下所有学员。

1、一般使用account_id（荔课ID）代表一个学员，其余数据表，学员相关数据表都通过account_id关联到该学员。
2、用户可能通过不同的主体注册，存在多个account_id（荔课ID）记录。但是为了标识多个account_id（荔课ID）是同一个学员，需要通过account_main_id（学员ID主账号ID）关联。
⚠️ 统计人数时需通过 `account_main_id` 去重，避免同一学员多荔课ID重复计算。

- **required_filters**:
  ```sql
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK |
| tid | int | 团队id |
| camp_id | int | 训练营id |
| term_id | int | 营期id → dim_lh_teaching_class_term.id |
| big_class_id | int | 班级id → dwd_lh_classes.id |
| account_id | int | 荔课ID |
| account_main_id | int | 学员ID（主账号ID）→ ods_mdb_account_main_relation.account_main_id（通过 account_id 关联） |
| wechat_nickname | varchar | 学员昵称 |
| add_status | varchar | 添加状态：added=已添加, to_add=未添加, 默认 null |
| authorization_status | varchar | 授权状态：unauthorized=未授权, authorized=已授权 |
| student_status | varchar | 学员状态：to_start=待开营, reading=在读, postpone=延期, refunding=退费受理, refunded=退费, relearning=重学, graduate=毕业, abandon=废弃，默认 to_start |
| add_robot_id | int | 添加机器人id |
| is_teacher | tinyint | 是否导师：1=是, 0=不是，默认 0 |
| grant_time | datetime | 授权时间 |

**示例 1：统计各班级已授权学员数（按 account_main_id 去重）**
```sql
SELECT
  `s`.`big_class_id`                        AS `class_id`,
  `c`.`class_name`,
  COUNT(DISTINCT NVL(`s`.`account_main_id`, `s`.`account_id`)) AS `authorized_student_num`
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  AND `s`.`authorization_status` = 'authorized'
  [[ AND `s`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
GROUP BY `s`.`big_class_id`, `c`.`class_name`
ORDER BY `authorized_student_num` DESC
```

**示例 2：查询班级学员明细（含姓名模糊搜索）**
```sql
SELECT
  `c`.`class_name`,
  `s`.`account_id`,
  `s`.`wechat_nickname`,
  `s`.`student_status`,
  `s`.`authorization_status`,
  `s`.`add_status`
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  [[ AND `s`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `s`.`wechat_nickname` LIKE CONCAT('%', {{name}}, '%') ]]
LIMIT 1000
```

---

### ods_mdb_account_main_relation（主账号关联表）

- **别名**: `amr`
- **use_for**: 记录荔课ID（account_id）对应的主账号ID（account_main_id）。

  很多数据表记录的都是account_id（荔课ID），如果不需要关联ods_lh_teaching_lh_teaching_student表，**统计人数时必须 LEFT JOIN 此表，用 `NVL(amr.account_main_id, s.account_id)` 作为去重键**，避免重复计算。

- **required_filters**:
  ```sql
  AND `amr`.`object_type` = 'account'
  ```
  ⚠️ 此条件为硬编码枚举，不加 `[[]]`，JOIN 时写在 ON 子句或 WHERE 中均可

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK |
| account_main_id | int | 学员主账号ID（去重用） |
| object_type | varchar | 关联对象类型，固定值 'account' |
| object_id | int | 关联对象ID → ods_lh_teaching_lh_teaching_student.account_id |

---

## 汇总统计表

### dws_lh_teaching_term_class_week（班级自然周指标汇总表）

- **别名**: `w`
- **use_for**: 对某个自然周下（某年、某月、某周）所有营期下的班级该自然周结束时数据定格的汇总记录。
  
  预聚合表的“维度键”:（`year`, `month`, `week`, `term_id`, `class_id`），对于某年、某月、某周、某营期下的某个班级只有一条数据。
  按"维度键"的全部字段分组时，无需 SUM
  按"维度键"的子集（如仅按 term_id 或仅按 class_id）汇总时，才需要 SUM

- **required_filters**:
```sql
AND `w`.`year` = {{year}}
AND `w`.`month` = {{month}}
AND `w`.`week` = {{week}}
AND `w`.`term_id` IN ({{term_ids}})
```

| 字段 | 类型 | 说明 |
|------|------|------|
| term_id | int | 营期id → dim_lh_teaching_class_term.id |
| class_id | int | 班级id → dwd_lh_classes.id |
| year | int | 年 |
| month | int | 月 |
| week | int | 周 |
| abs_week | int | 绝对周数(该营期从开营开始的周数，从1开始递增) |
| authorize_num | int | 授权人数 |
| original_num | int | 原始人数 |
| add_robot_num | int | 添加（机器人）人数 |
| reading_num | int | 读取人数 |
| raise_refund_num | int | 提出退费人数 |
| refund_num | int | 退费人数 |
| homework_submit_num | int | 作业提交人数 |
| high_interact_num_day | int | 当天高互动学员人数 |
| high_interact_num_week | int | 当周高互动学员人数 |
| high_interact_num_yesterday | int | 昨日高互动学员人数 |
| external_complain_count | int | 外诉单数 |
| combine_raise_refund_num | int | 预提退费人数 |
| ws_num | int | 外诉次数 |
| high_interact_intention_num | int | 高意向人数 |
| app_login_num | int | APP登录登录人数 |


**示例 1：营期维度汇总数据对比**
```sql
SELECT
  `ct`.`id`                    AS `term_id`,
  `ct`.`rank`                  AS `term_rank`,
  SUM(`w`.`authorize_num`)     AS `authorize_num`,
  SUM(`w`.`original_num`)      AS `original_num`,
  SUM(`w`.`ws_num`)            AS `ws_num`,
  SUM(`w`.`raise_refund_num`)  AS `raise_refund_num`,
  SUM(`w`.`add_robot_num`)     AS `add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `w`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `w`.`term_id` = `ct`.`id`
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  AND `w`.`year` = {{year}}
  AND `w`.`month` = {{month}}
  AND `w`.`week` = {{week}}
  AND `w`.`term_id` IN ({{term_ids}})
GROUP BY `ct`.`id`, `ct`.`rank`
ORDER BY `ct`.`rank`
```

**示例 2：班级维度汇总数据对比**

因为预聚合表的“维度键”:（`year`, `month`, `week`, `term_id`, `class_id`），对于个某年、某月、某周，某营期下的某个班级只有一条数据，所以不需要聚合。

```sql
SELECT
  `ct`.`rank`          AS `term_rank`,
  `c`.`class_name`,
  `c`.`id`             AS `class_id`,
  `w`.`year`,
  `w`.`month`,
  `w`.`week`,
  `w`.`authorize_num`,
  `w`.`original_num`,
  `w`.`ws_num`,
  `w`.`raise_refund_num`,
  `w`.`add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `w`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `w`.`term_id` = `ct`.`id`
JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `w`.`class_id` = `c`.`id`
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  AND `c`.`camp_id` = {{camp_id}}
  AND `w`.`year` = {{year}}
  AND `w`.`month` = {{month}}
  AND `w`.`week` = {{week}}
  AND `w`.`term_id` IN ({{term_ids}})
  [[ AND `c`.`id` IN ({{class_ids}}) ]]
ORDER BY `w`.`month`, `w`.`week`
```
---
<!--
新增汇总表模板（复制此块填写）：

### <表名>（<注释>）

- **别名**: `<alias>`
- **use_for**: <适用场景描述>
- **global_fields**: <填写含有的 tid / camp_id 等全局隔离字段，无则填"无">
- **required_filters**: <强制注入的条件（无 [[]]），通常是分区键/快照键>
  ```sql
  AND `<alias>`.`<field>` = {{<var>}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| ... | ... | ... |

**示例 1：<场景描述>**
```sql
-- SQL
```
-->