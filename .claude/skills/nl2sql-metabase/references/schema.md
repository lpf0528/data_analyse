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
- **use_for**: 定义不同的团队/训练营，其余数据表都使用 camp_id 或者 tid 实现数据的隔离
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
  > ⚠️ 该表无独立的 `tid` 字段，数据隔离通过 `camp_id` 实现。每个 `camp_id` 归属唯一一个团队，因此 `camp_id` 已足够隔离数据，无需额外注入 `tid`。若业务上存在多团队共享同一 `camp_id` 的场景，需在查询时额外 JOIN `dim_lh_teaching_class_term` 并过滤 `tid`。

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

  1. 一般使用 `account_id`（荔课ID）代表一个学员，其余数据表通过 `account_id` 关联到该学员。
  2. 用户可能通过不同主体注册，存在多个 `account_id`（荔课ID）记录。为标识多个 `account_id` 属于同一学员，需通过 `account_main_id`（学员主账号ID）关联。
  
  ⚠️ **统计人数时，必须用 `NVL(s.account_main_id, s.account_id)` 作为去重键**，避免同一学员因多荔课ID被重复计算。此处直接使用 `s.account_main_id` 字段（学员表自带，无需额外 JOIN `ods_mdb_account_main_relation`）。

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
| account_main_id | int | 学员主账号ID（去重键）。若同一学员有多个荔课ID，统一归并到同一 account_main_id；统计人数时以此去重，等效于 `NVL(s.account_main_id, s.account_id)` |
| wechat_nickname | varchar | 学员昵称 |
| add_status | varchar | 添加状态：added=已添加, to_add=未添加, 默认 null |
| authorization_status | varchar | 授权状态：unauthorized=未授权, authorized=已授权 |
| student_status | varchar | 学员状态枚举：to_start=待开营, reading=在读, postpone=延期, refunding=退费受理, refunded=退费, relearning=重学, graduate=毕业, abandon=废弃，默认 to_start |
| add_robot_id | int | 添加机器人id |
| is_teacher | tinyint | 是否导师：1=是, 0=不是，默认 0 |
| grant_time | datetime | 授权时间 |

**示例 1：统计各班级已授权学员数（按 account_main_id 去重）**
```sql
SELECT
  `s`.`big_class_id`                                              AS `class_id`,
  `c`.`class_name`,
  COUNT(DISTINCT NVL(`s`.`account_main_id`, `s`.`account_id`))   AS `authorized_student_num`
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
- **use_for**: 记录荔课ID（`account_id`）对应的主账号ID（`account_main_id`）。

  **适用场景**：当查询的数据表只有 `account_id` 字段，且**未 JOIN `ods_lh_teaching_lh_teaching_student`**（该表已内置 `account_main_id`）时，必须 LEFT JOIN 本表，用 `NVL(amr.account_main_id, <表>.account_id)` 作为去重键，避免重复计算同一学员。

  **两种去重写法对比**：

  | 场景 | 写法 | 说明 |
  |------|------|------|
  | 已 JOIN `ods_lh_teaching_lh_teaching_student` | `NVL(s.account_main_id, s.account_id)` | 直接取学员表字段，无需额外 JOIN |
  | 未 JOIN 学员表，仅有 `account_id` | `NVL(amr.account_main_id, <表>.account_id)` | 需 LEFT JOIN 本表补全主账号ID |

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

## 业务配置表

### dim_lh_teaching_weeks_conf（自然周配置表）

- **别名**: `wc`
- **use_for**: 记录每个自然周（某年、某月、某周）配置的开始时间和结束时间，主要作为 `dws_lh_teaching_term_class_week` 的自然周维度查找表，通过 `year`、`month`、`week` 三字段关联。通常以 `wc.id`（周配置主键）作为查询特定自然周的入参。
- **required_filters**:
  ```sql
  AND `wc`.`tid` = {{tid}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK，自然周配置唯一ID，可作为 `{{week_id}}` 入参 |
| tid | int | 团队id |
| year | int | 年 |
| month | int | 月 |
| week | int | 周（自然周序号，同年同月内从1开始） |
| start_time | date | 该自然周开始日期 |
| end_time | date | 该自然周结束日期 |

---

## 汇总统计表

### dws_lh_teaching_term_class_week（班级自然周指标定格汇总表）

- **别名**: `cw`
- **use_for**: 记录某个自然周结束时，每个班级数据定格的汇总快照。

  **预聚合表维度键**：（`year`, `month`, `week`, `term_id`, `class_id`），即某年某月某周下某营期的某个班级只有一条记录。
  - 按**完整维度键**查询时，无需 SUM
  - 按**维度键子集**（如仅按 `term_id` 或仅按 `class_id`）汇总时，需 SUM

  > ⚠️ 该表无 `tid` / `camp_id` 字段，数据隔离通过 `term_id` 实现（`term_id` 归属唯一团队和训练营）。使用时无需额外注入 `tid`，但需确保传入的 `term_ids` 属于目标团队，避免越权访问。

- **required_filters**:
  ```sql
  -- 查询多个班级或者所有班级的指标定格汇总
  AND `cw`.`term_id` IN ({{term_ids}})
  [[ AND `cw`.`class_id` IN ({{class_ids}}) ]]
  ```
  或者
  ```sql
  -- 查询单个班级的指标定格汇总
  AND `cw`.`term_id` = {{term_id}}
  AND `cw`.`class_id` = {{class_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| term_id | int | 营期id → dim_lh_teaching_class_term.id |
| class_id | int | 班级id → dwd_lh_classes.id |
| year | int | 年 |
| month | int | 月 |
| week | int | 周 |
| abs_week | int | 绝对周数：该营期从开营起第几周，从1开始递增，每个营期独立计算（不跨营期累加）。可用于跨营期同位周对比（如"第3周"的横向对比） |
| authorize_num | int | 授权人数：截至该自然周末完成微信授权的学员数（按 account_main_id 去重） |
| original_num | int | 原始人数：截至该自然周末该班级招募的总报名学员数（含所有状态，含未授权），是班级规模的基准口径。|
| add_robot_num | int | 添加（机器人）人数 |
| reading_num | int | 在读人数 |
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
| app_login_num | int | APP登录人数 |

**示例 1：查询某个班级在连续多个自然周（start_week_id ~ end_week_id）内各指标的变化趋势**

```sql
SELECT
  `cw`.`year`,
  `cw`.`month`,
  `cw`.`week`,
  `cw`.`authorize_num`,
  `cw`.`original_num`,
  `cw`.`ws_num`,
  `cw`.`raise_refund_num`,
  `cw`.`add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_weeks_conf` `wc`
  ON `wc`.`year` = `cw`.`year`
  AND `wc`.`month` = `cw`.`month`
  AND `wc`.`week` = `cw`.`week`
  AND `wc`.`tid` = {{tid}}
  AND `wc`.`id` BETWEEN {{start_week_id}} AND {{end_week_id}}
WHERE 1=1
  AND `cw`.`term_id` = {{term_id}}
  AND `cw`.`class_id` = {{class_id}}
```

**示例 2：对比多个营期在同一自然周下的汇总指标（营期间横向对比）**

```sql
SELECT
  `ct`.`id`                    AS `term_id`,
  `ct`.`rank`,
  SUM(`cw`.`authorize_num`)    AS `authorize_num`,
  SUM(`cw`.`original_num`)     AS `original_num`,
  SUM(`cw`.`ws_num`)           AS `ws_num`,
  SUM(`cw`.`raise_refund_num`) AS `raise_refund_num`,
  SUM(`cw`.`add_robot_num`)    AS `add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `cw`.`term_id` = `ct`.`id`
JOIN `warehouse`.`dim_lh_teaching_weeks_conf` `wc`
  ON `wc`.`year` = `cw`.`year`
  AND `wc`.`month` = `cw`.`month`
  AND `wc`.`week` = `cw`.`week`
  AND `wc`.`tid` = {{tid}}
  AND `wc`.`id` = {{week_id}}
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  AND `cw`.`term_id` IN ({{term_ids}})
GROUP BY `ct`.`id`, `ct`.`rank`
ORDER BY `ct`.`rank`
```

**示例 3：对比营期内多个班级在某自然周下的指标（班级间横向对比）**

因维度键包含 `class_id`，单周单班只有一条记录，无需 SUM。

```sql
SELECT
  `ct`.`rank`          AS `term_rank`,
  `c`.`class_name`,
  `c`.`id`             AS `class_id`,
  `cw`.`authorize_num`,
  `cw`.`original_num`,
  `cw`.`ws_num`,
  `cw`.`raise_refund_num`,
  `cw`.`add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `cw`.`term_id` = `ct`.`id`
JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `cw`.`class_id` = `c`.`id`
JOIN `warehouse`.`dim_lh_teaching_weeks_conf` `wc`
  ON `wc`.`year` = `cw`.`year`
  AND `wc`.`month` = `cw`.`month`
  AND `wc`.`week` = `cw`.`week`
  AND `wc`.`tid` = {{tid}}
  AND `wc`.`id` = {{week_id}}
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  AND `cw`.`term_id` IN ({{term_ids}})
  [[ AND `c`.`id` IN ({{class_ids}}) ]]
```

---

## 复购订单表

### authorize_student_pay（授权学员订单视图，CTE 型）

- **别名**: `aap`
- **use_for**: 查询复购订单数据，包括高价课订单（`high`）与实物订单（`physical`）的合并明细，以及订单对应的授权学员信息（班级、营期、学员状态等）。

  > 💡 **当作视图使用**：内部实现已封装为固定 CTE，无需关注其内部表结构和 JOIN 逻辑。使用时只需：
  > 1. 将下方 **完整 CTE 块**原样粘贴到 SQL 最前面
  > 2. 3 个必填参数（团队 ID:`{{tid}}`、订单时间范围起始:`{{start_date}}`、订单时间范围截止:`{{end_date}}`， 格式 `'YYYY-MM-DD'`）
  > 3. 在 CTE 块末尾直接写业务查询，FROM `authorize_account_pay` 即可


- **CTE 块**（完整复制，不得修改内部内容）：
```sql
WITH `repurchase_term` AS (
  SELECT
    `trc`.`tid`,
    `trc`.`camp_id`              AS `repurchase_camp_id`,
    `ct`.`id`                    AS `repurchase_term_id`,
    `ct`.`rank`                  AS `repurchase_term_rank`,
    `cc`.`camp_name`             AS `repurchase_camp_name`
  FROM `warehouse`.`dim_lh_teaching_repurchase_camp` `trc`
  JOIN [shuffle] `warehouse`.`dim_lh_class_term` `ct`
    ON `trc`.`camp_id` = `ct`.`camp_id`
  JOIN [shuffle] `warehouse`.`dim_lh_class_camp` `cc`
    ON `trc`.`camp_id` = `cc`.`id`
  WHERE `trc`.`status` = 1
    AND `trc`.`tid` = {{tid}}
),
`high_pay_order` AS (
  SELECT
    `tsp`.`id`,
    'high'                                        AS `source`,
    `tsp`.`pay_fee`,
    `tsp`.`pay_channel_id`                        AS `pay_product_id`,
    `mlc`.`name`                                  AS `product_name`,
    `mpc`.`id`                                    AS `category_id`,
    `mpc`.`name`                                  AS `category_name`,
    `tsp`.`account_id`,
    NVL(`amr`.`account_main_id`, `tsp`.`account_id`) AS `account_main_id`,
    `tsp`.`pay_status`,
    `tsp`.`lecture_id`,
    `tsp`.`is_deposit`,
    `tsp`.`pay_time`,
    `tsp`.`pay_refund_time`,
    `tsp`.`pay_order_time`,
    `tsp`.`coach_name`,
    `tsp`.`order_source`,
    `tsp`.`pay_amount`
  FROM `warehouse`.`dwd_lh_class_term_student_pay` `tsp`
  JOIN [shuffle] `repurchase_term` `rt`
    ON `tsp`.`term_id` = `rt`.`repurchase_term_id`
  JOIN [shuffle] `warehouse`.`dim_mdb_liveroom_channel` `mlc`
    ON `tsp`.`pay_channel_id` = `mlc`.`id`
  JOIN [shuffle] `warehouse`.`dim_mdb_product_category` `mpc`
    ON `mlc`.`category_id` = `mpc`.`id`
  LEFT JOIN `warehouse`.`ods_mdb_account_main_relation` `amr`
    ON `tsp`.`account_id` = `amr`.`object_id`
    AND `amr`.`object_type` = 'account'
  WHERE `tsp`.`pay_order_time` BETWEEN {{start_date}} AND {{end_date}}
),
`physical_pay_order` AS (
  SELECT
    `tpp`.`id`,
    'physical'                                    AS `source`,
    `tpp`.`pay_fee`,
    `tpp`.`pay_product_id`,
    `omp`.`name`                                  AS `product_name`,
    `mpc`.`id`                                    AS `category_id`,
    `mpc`.`name`                                  AS `category_name`,
    `tpp`.`account_id`,
    NVL(`amr`.`account_main_id`, `tpp`.`account_id`) AS `account_main_id`,
    `tpp`.`pay_status`,
    `tpp`.`lecture_id`,
    0                                             AS `is_deposit`,
    `tpp`.`pay_time`,
    `tpp`.`pay_refund_time`,
    `tpp`.`pay_order_time`,
    `tpp`.`coach_name`,
    `tpp`.`order_source`,
    `tpp`.`pay_amount`
  FROM `warehouse`.`dwd_lh_class_term_student_pay_physical` `tpp`
  JOIN [shuffle] `repurchase_term` `rt`
    ON `tpp`.`term_id` = `rt`.`repurchase_term_id`
  JOIN [shuffle] `warehouse`.`ods_miniprogram_product` `omp`
    ON `tpp`.`pay_product_id` = `omp`.`id`
  JOIN [shuffle] `warehouse`.`dim_mdb_product_category` `mpc`
    ON `omp`.`first_class` = `mpc`.`id`
  LEFT JOIN `warehouse`.`ods_mdb_account_main_relation` `amr`
    ON `tpp`.`account_id` = `amr`.`object_id`
    AND `amr`.`object_type` = 'account'
  WHERE `tpp`.`pay_order_time` BETWEEN {{start_date}} AND {{end_date}}
),
`authorize_account` AS (
  SELECT * FROM (
    SELECT DISTINCT
      `tsm`.`term_id`,
      `tsm`.`grant_class_id`,
      `tsm`.`student_status`,
      `tsm`.`account_id`,
      `lct`.`tid`,
      NVL(`amr`.`account_main_id`, `tsm`.`account_id`) AS `account_main_id`,
      `lct`.`rank`,
      `c`.`class_name`,
      RANK() OVER (
        PARTITION BY NVL(`amr`.`account_main_id`, `tsm`.`account_id`)
        ORDER BY `tsm`.`grant_time` DESC
      ) AS `r`
    FROM `warehouse`.`dim_lh_term_student_metrics` `tsm`
    JOIN [shuffle] `warehouse`.`dim_lh_teaching_class_term` `lct`
      ON `tsm`.`term_id` = `lct`.`id`
      AND `lct`.`tid` = {{tid}}
    JOIN [shuffle] `warehouse`.`dwd_lh_classes` `c`
      ON `tsm`.`grant_class_id` = `c`.`id`
    LEFT JOIN `warehouse`.`ods_mdb_account_main_relation` `amr`
      ON `tsm`.`account_id` = `amr`.`object_id`
      AND `amr`.`object_type` = 'account'
    WHERE `tsm`.`student_status` NOT IN ('abandon')
    [[AND `tsm`.`term_id` IN ({{term_ids}})]]
    [[AND `tsm`.`grant_class_id` IN ({{class_ids}})]]
  ) `res`
  WHERE `res`.`r` = 1
),
`authorize_account_pay` AS (
  SELECT
    `r1`.*,
    `r2`.`student_status`,
    `r2`.`grant_class_id`                         AS `class_id`,
    `r2`.`class_name`,
    `r2`.`rank`,
    `r2`.`term_id`,
    IF(`r2`.`account_id` IS NULL, 0, 1)           AS `order_account_flag`
  FROM (
    SELECT * FROM `high_pay_order`
    UNION ALL
    SELECT * FROM `physical_pay_order`
  ) `r1`
  JOIN [shuffle] `authorize_account` `r2`
    ON `r1`.`account_main_id` = `r2`.`account_main_id`
)
-- ↑ CTE 结束，在此之后写业务查询 ↓
```


| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 订单 id |
| source | varchar | 订单来源类型：`high`=高价课, `physical`=实物 |
| pay_fee | int | 支付费用 |
| pay_product_id | int | 支付商品 id |
| product_name | varchar | 商品名称 |
| category_id | int | 品类 id |
| category_name | varchar | 品类名称 |
| account_id | int | 荔课 id |
| account_main_id | int | 学员主账号 id（去重键） |
| pay_status | tinyint | 支付状态：1=待支付, 2=已支付, 3=已退款 |
| lecture_id | int | 直播课 id |
| is_deposit | int | 是否定金：0=否, 1=是 |
| pay_time | datetime | 支付时间 |
| pay_refund_time | datetime | 退款时间 |
| pay_order_time | datetime | 下单时间 |
| coach_name | varchar | 出单教练名 |
| order_source | varchar | 订单来源渠道 |
| pay_amount | int | 应付金额 |
| student_status | varchar | 学员状态（来自授权学员表） |
| class_id | int | 授权班级 id |
| class_name | varchar | 授权班级名称 |
| rank | int | 授权营期第 N 期 |
| term_id | int | 授权营期 id |
| order_account_flag | int | 是否授权学员下单：1=是, 0=否 |

**示例 1：统计指定时间段内各班级的已支付订单金额**
```sql
-- （在 WITH 块末尾追加）
SELECT
  `aap`.`class_id`,
  `aap`.`class_name`,
  COUNT(DISTINCT `aap`.`id`)  AS `order_count`,
  SUM(`aap`.`pay_fee`)        AS `total_pay_fee`
FROM `authorize_account_pay` `aap`
WHERE `aap`.`pay_status` = 2
GROUP BY `aap`.`class_id`, `aap`.`class_name`
ORDER BY `total_pay_fee` DESC
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