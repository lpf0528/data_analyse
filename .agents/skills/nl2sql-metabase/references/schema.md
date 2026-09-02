# Schema Reference — 多数据库 Schema 规范

## 表元数据协议说明

每张表用以下结构声明约束，SKILL.md 中的规则引擎会读取并应用这些元数据：

```
- **db_name**: 目标数据库名（如 warehouse / lh_teaching）
- **use_for**: 适合回答哪类问题（用于表选择决策）
- **required_filters**: 使用此表必须注入的强制条件（无 [[]]），CTE 型表则为固定 WITH 写法
- **optional_filters**: 可选条件（有则加 [[]]）；未列出时按业务需要自行添加
- **examples**: 该表的典型 SQL 用法（1-2 个）
```

---

## 基础维度表

### dim_lh_basic_team

- **db_name**: `warehouse`
- **use_for**: 定义不同的团队/训练营，其余数据表都使用 `camp_id` 或 `tid`（对应本表 `id`）实现数据隔离，且二者在查询时均为必填参数
- **required_filters**:
  ```sql
  AND `t`.`id` = {{tid}}
    AND `t`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 团队id（PK），其他表对应 tid 字段 |
| name | varchar | 团队名称 |
| camp_id | int | 训练营id(唯一键) |

---

### dim_lh_teaching_class_term

- **db_name**: `warehouse`
- **use_for**: 每个团队/训练营下定义不同的营期，实现不同营期之间的数据隔离
- **required_filters**:
  ```sql
  AND `ct`.`tid` = {{tid}}
    AND `ct`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 营期id（PK），其他表对应 term_id/camp_term_id 字段 |
| tid | int | 团队id（外键） → dim_lh_basic_team.id |
| camp_id | int | 训练营id |
| rank | int | 第N期（同个团队/训练营下rank从1开始递增） |
| op_start_time | datetime | 开营时间 |
| op_end_time | datetime | 结营时间 |

**示例 1：查询某团队所有营期列表**
```sql
SELECT
  `ct`.`id`   AS `term_id`,
  `ct`.`rank` AS `term_rank`,
  `ct`.`op_start_time`,
  `ct`.`op_end_time`
FROM `warehouse`.`dim_lh_teaching_class_term` `ct`
WHERE 1=1
  AND `ct`.`camp_id` = {{camp_id}}
  AND `ct`.`tid` = {{tid}}
  [[ AND `ct`.`id` IN ({{term_ids}}) ]]
ORDER BY `ct`.`rank`
```

---

### dwd_lh_classes

- **db_name**: `warehouse`
- **use_for**: 每个营期下定义不同的班级，实现不同班级之间的数据隔离。
- **required_filters**:
  ```sql
  AND `c`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 班级id（PK） |
| camp_id | int | 训练营id |
| camp_term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| class_name | varchar | 班级名称 |
| monitor_user_id | int | 教练id |
| monitor_name | varchar | 教练名称 |
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

### ods_lh_teaching_lh_teaching_student

- **db_name**: `warehouse`
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
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| big_class_id | int | 班级id(外键) → dwd_lh_classes.id |
| account_id | int | 荔课ID（用户学习的ID,同一个学员ID可能存在多个荔课ID） |
| account_main_id | int | 学员ID（标识唯一的用户） |
| wechat_nickname | varchar | 学员昵称 |
| add_status | varchar | 添加状态：added=已添加, to_add=未添加, 默认 null |
| authorization_status | varchar | 授权状态：unauthorized=未授权, authorized=已授权 |
| student_status | varchar | 学员状态枚举：to_start=待开营, reading=在读, postpone=延期, refunding=退费受理, refunded=退费, relearning=重学, graduate=毕业, abandon=废弃，默认 to_start |
| add_robot_id | int | 添加机器人id |
| is_teacher | tinyint | 是否导师：1=是, 0=不是，默认 0 |
| grant_time | datetime | 授权时间 |

**示例 2：查询学员列表**
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
  AND `s`.`term_id` IN ({{term_ids}})
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `s`.`wechat_nickname` LIKE CONCAT('%', {{name}}, '%') ]]
```

---

## 业务配置表

### dim_lh_teaching_weeks_conf

- **db_name**: `warehouse`
- **use_for**: 记录自定义的自然周（某年、某月、某周）配置的开始时间和结束时间，因为需要根据周维度来查看班级/营期下学员相关数据的变化，例如：添加人数、授权人数、退费人数等，这些数据都以周维度的方式记录在`dws_lh_teaching_term_class_week`表中，经常用来作为筛选列表。
- **required_filters**:
  ```sql
  AND `wc`.`tid` = {{tid}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK，自然周配置唯一ID，可作为 `{{week_id}}` 入参 |
| tid | int | 团队id |
| year | int | 年，eg:2026 |
| month | int | 月，eg:2 |
| week | int | 周，eg:1、2、3 |
| week_days | int | 每周的天数，eg:7 |
| start_time | date | 该自然周开始日期 |
| end_time | date | 该自然周结束日期 |

---

## 汇总统计表

### dws_lh_teaching_repurchase_category_class_day

- **db_name**: `warehouse`
- **use_for**: 记录**班级**每天学员数据指标定格的汇总快照
- **required_filters**:
  ```sql
  AND `rcd`.`term_id` IN ({{term_ids}})
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| category_id | int | 品类id |
| class_id | int | 班级id（外键） → dwd_lh_classes.id |
| dt | date | 日期 |
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| pay_num | int | 当日尾款+定金支付人数 |
| pay_num_have_refund | int | 当日尾款+定金支付人数（含退费） |
| deposit_pay_live_num | int | 直播间定金支付人数 |
| deposit_pay_live_num_have_refund | int | 直播间定金支付人数(含退费) |
| deposit_pay_no_live_num | int | 个销定金支付人数 |
| deposit_pay_no_live_num_have_refund | int | 个销定金支付人数(含退费) |
| pay_live_num | int | 直播间尾款+定金支付人数 |
| pay_live_num_have_refund | int | 直播间尾款+定金支付人数(含退费) |
| pay_no_live_num | int | 个销尾款+定金支付人数 |
| pay_no_live_num_have_refund | int | 个销尾款+定金支付人数(含退费) |
| tail_pay_live_num | int | 直播间尾款支付人数 |
| tail_pay_live_num_have_refund | int | 直播间尾款支付人数(含退费) |
| tail_pay_not_live_num | int | 个销尾款支付人数 |
| tail_pay_not_live_num_have_refund | int | 个销尾款支付人数(含退费) |
| tail_pay_intraday_num | int | 当日尾款支付人数 |
| tail_pay_intraday_num_have_refund | int | 当日尾款支付人数(含退费) |
| deposit_pay_num | int | 定金支付人数 |
| deposit_pay_num_have_refund | int | 定金支付人数(含退费) |
| deposit_tail_pay_num | int | 天定金追回人数 |
| deposit_tail_pay_num_have_refund | int | 天定金追回人数(含退费) |
| deposit_complete_pay_total_num | int | 累计定金结清人数 |
| deposit_complete_pay_total_num_have_refund | int | 累计定金结清人数(含退费) |
| deposit_pay_total_num | int | 累计定金人数 |
| deposit_pay_total_num_have_refund | int | 累计定金人数(含退费) |
| pay_intraday_amount | int | 当天支付产生流水 |
| pay_intraday_amount_have_refund | int | 当天支付流水(含退费) |
| pay_intraday_amount_guaranteed | int | 打底流水 |
| pay_intraday_amount_g_have_refund | int | 打底流水(含退费) |
| pay_intraday_live_amount | int | 当天直播间流水 |
| pay_intraday_live_amount_have_refund | int | 当天直播间流水(含退费) |
| pay_intraday_not_live_amount | int | 当天非直播间/私聊流水 |
| pay_intraday_not_live_amount_have_refund | int | 当天非直播间/私聊流水(含退费) |
| watch_live_num | int | 到播人数 |
| valid_watch_live_num | int | 有效到播人数 |
| valid_watch_live_num_realtime | int | 有效到播人数(实时) |
| real_discuss_cnt | int | 真实用户发言数（发言数） |
| lecturer_reply_cnt | int | 讲师回复数 |
| barrage_cnt | int | 学员评论数 |
| no_pay_live_num | int | 直播间待支付人数 |
| follow_live_num | int | 直播间跟读人数(day1为空) |
| lecture_id | int | 当天选取的直播课 |
| create_order_ot_num | int | 当天超时待支付人数 |
| create_order_ot_pay_num | int | 当天超时待支付购买人数 |
| no_pay_special_num | int | 未购买人数 |
| no_pay_valid_watch_live_num | int | 授权未购买有效到播人数 |
| no_pay_authorize_num | int | 授权未购买人数 |
| full_pay_amount | int | 全款流水 |
| full_pay_amount_have_refund | int | 全款流水(含退费) |
| high_potential_pay_num | int | 高潜力用户支付人数 |
| high_potential_pay_num_have_refund | int | 高潜力用户支付人数(含退费) |
| max_concurrent_users | int | 最高同时在线人数 |
| watch_duration_attended | int | 到播学员的观看总时长 |
| avg_watch_duration_attended | int | 到播学员的平均观看时长 |

---

### dws_lh_teaching_term_class_week

- **db_name**: `warehouse`
- **use_for**: 记录某个自然周结束时，班级下学员指标定格的汇总快照。通常用来：
1. 对比某自然周不同班级学员指标的差异
2. 对比某个班级在连续自然周学员指标的变化
3. 对比某自然周不同营期学员指标的差异（需按营期分组聚合，因一个营期下存在多个班级）
- **required_filters**:
  ```sql
  AND `cw`.`term_id` IN ({{term_ids}})
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| class_id | int | 班级id（外键） → dwd_lh_classes.id |
| year | int | 年，year、month、week对应`dim_lh_teaching_weeks_conf`表中的一行自然周记录 |
| month | int | 月 |
| week | int | 周 |
| abs_week | int | 绝对周数：根据term_id对应营期的开营时间（dim_lh_teaching_class_term.op_start_time）计算经历过多少个自然周（dim_lh_teaching_weeks_conf） |
| authorize_num | int | 授权人数：自然周（year、month、week）结束时，该班级学员授权状态（authorization_status=authorized）的学员数 |
| original_num | int | 原始人数 |
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
| bw_learn_time_gt7 | int | 保温录播课学习时长大于70%的人数 |
| finish_course_gt8 | int | 完成的录播课课程达标率超过80%的人数(达标) |
| external_complain_num | int | 外诉人数(提出工单人为风控组，学员状态为退费) |
| high_intention_num | int | 高意向人数(沉浸度和作业提交率都大于等于80%的学员) |
| access_lecture_num | int | 到课人数(录播课学习时长大于0%) |
| lecture_num | int | 专栏下每周的课程数(布置了作业) |
| total_lecture_num | int | 专栏下的累积课程数(布置了作业) |
| homework_num | int | 作业提交数 |
| total_homework_num | int | 专栏下的累积作业提交数 |
| live_lecture_num | int | 周直播课数量 |
| access_live_lecture_num | int | 周直播到课数 |
| live_finish_lecture_num | int | 周直播完课数 |
| watch_live_finish_lecture_num | int | 周观看直播完课数 |
| no_watch_live_finish_lecture_num | int | 周直播观看未完课数 |
| playback_finish_lecture_num | int | 周直播回放完课数 |
| live_finish_total_num | int | 总直播完课数 |
| avg_reply_time | int | 平均跟进时长(分钟)[除100是实际结果] |
| raise_order_refund_num | int | 提退人数(通过工单) |
| teacher_retain_num | int | 讲师挽回人数 |
| retain_receive_num | int | 挽单承接人数 |
| retain_retrieve_num | int | 挽单挽回人数 |
| high_potential_num | int | 高潜力学员数 |
| buy_course_complain_num7 | int | 购课7天内外诉人数 |
| course_end_authorize_num | int | 授权人数(课程截止时间前一天截止) |
| avg_video_finish_num | int | 周平均录播完课人数 |
| avg_live_finish_num | int | 周平均直播完课人数 |
| avg_homework_finish_homework_num | int | 周平均作业提交人数 |
| avg_homework_course_finish_num | int | 周平均作业完课人数 |
| avg_practice_course_finish_num | int | 周平均训练完课人数 |
| avg_video_finish_total_num | int | 总平均录播完课人数 |
| avg_live_finish_total_num | int | 总平均直播完课人数 |
| avg_homework_finish_total_num | int | 总平均作业提交人数 |
| avg_homework_course_finish_total_num | int | 总平均作业完课人数 |
| avg_practice_course_finish_total_num | int | 总平均训练完课人数 |
| first_operate_task_order_num | int | 首次试音提交人数(包含撤回) |
| second_operate_task_order_num | int | 第二次试音提交人数(包含撤回) |
| first_official_task_order_num | int | 首次正式音频提交人数(包含撤回) |
| second_official_task_order_num | int | 第二次正式音频提交人数(包含撤回) |

**示例 1：查询某个班级在连续多个自然周（start_week_id ~ end_week_id）内各指标的变化趋势**
```sql

```

**示例 2：对比营期内某个自然周下不同班级学员指标**
```sql

```

**示例 3：对比不同营期某自然周下学员指标（需要根据营期进行分组聚合，因为某个营期下存在多个班级）**
```sql

```

---

## 复购订单表

### authorize_account_order

- **db_name**: `warehouse`
- **use_for**: 查询学员的复购订单数据。同一荔课 ID 可能存在于多个营期/班级，订单关联复杂，已封装为固定 CTE，无需关注内部表结构与 JOIN。使用时：
> 1. 将下方 **完整 CTE 块**原样粘贴到 SQL 最前面，业务查询从 CTE `authorize_account_order` 取数（别名 `aao`）
> 2. 3 个必填参数已写入 CTE：`{{tid}}`、`{{start_date}}`、`{{end_date}}`（日期格式 `'YYYY-MM-DD'`）；其余可选参数按用户问题增减

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | int | 订单 id |
| account_id | int | 荔课 id |
| source | varchar | 商品类型：'physical': '实体商品','high': '课程商品' |
| pay_fee | int | 支付金额 |
| pay_product_id | int | 商品ID |
| product_name | varchar | 商品名称 |
| category_id | int | 品类 id |
| category_name | varchar | 品类名称 |
| pay_status | tinyint | 订单支付状态：1: '待支付',2: '未退款',3: '已退款' |
| order_pay_scene | int | 出单方式: live_v:直播间， 其他：私聊 |
| pay_order_time | datetime | 下单时间 |
| pay_time | datetime | 支付时间 |
| pay_amount | int | 应付金额 |
| refund_time | datetime | 退费时间 |
| order_coach_name | varchar | 出单教练名 |
| repurchase_rank | varchar | 复购训练营期数 |
| repurchase_term_id | varchar | 复购训练营期ID |
| repurchase_camp_id | varchar | 复购训练营ID |
| repurchase_camp_name | varchar | 复购训练营名称 |
| deposit_plan_id | int | 交易订单号 |
| deposit_plan_status | int | 定金计划状态：0: '-',1: '已结清',2: '未结清' |
| deposit_status | int | 出单类型：-1: '-', 0: '专栏尾款',1: '专栏定金',2: '定金计划-定金',3: '定金计划-尾款' |
| term_id | int | 学员下单时授权营期 id |
| rank | int | 学员下单时授权营期对应的第 N 期 |
| class_id | int | 学员下单时授权班级 id |
| class_name | varchar | 学员下单时授权班级名称 |
| student_status | varchar | 学员下单时学员状态 |
| account_main_id | int | 学员主账号 |

**示例 1：统计指定时间段内各班级的已支付订单金额**
```sql
-- （在 WITH 块末尾追加）
SELECT
  `aao`.`class_id`,
  `aao`.`class_name`,
  COUNT(DISTINCT `aao`.`order_id`) AS `order_count`,
  SUM(`aao`.`pay_fee`)             AS `total_pay_fee`
FROM `authorize_account_order` `aao`
WHERE `aao`.`pay_status` = 2
GROUP BY `aao`.`class_id`, `aao`.`class_name`
ORDER BY `total_pay_fee` DESC
```

---

## 消息跟进表

### ods_lh_efficiency_platform_term_student_chat_message_all

- **db_name**: `warehouse`
- **use_for**: 记录营期学员与机器人/客服的聊天消息跟进明细（全部消息类型），包含消息类型、发送状态、回复时长（等待时长）、回复场景（私聊/客服/AI自动/关键词）及消息标签等。适合回答：
1. 营期学员消息跟进率、跟进响应时长及逾期未回复（`wait_interval >= 7200`）统计
2. 消息类型（文字、图片、语音、视频、图文链接、小程序、视频号等）与回复场景分布
3. 学员与机器人的互动跟进明细及消息标签分析
- **required_filters**:
  ```sql
  AND `m`.`term_id` IN ({{term_ids}})
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 自增，消息id（PK） |
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| account_id | int | 荔课ID（学员ID） |
| external_users_id | int | 学员在群控系统中的ID |
| robot_id | int | 机器人id |
| msg_time | datetime | 消息时间 |
| msg_content | text | 聊天消息内容 |
| msg_type | int | 消息类型：10000='系统消息', 2001='文字', 2002='图片', 2003='语音', 2004='视频', 2005='图文链接', 2006='好友名片', 2010='文件', 2013='小程序', 2017='视频号消息', 2021='位置消息', 2018='转发消息' |
| label | varchar | 消息标签 |
| manual_label | varchar | 人工标记的标签 |
| state | varchar | 发送状态：sending, success=发送成功, fail, recall=撤回 |
| create_time | datetime | 创建时间 |
| update_time | datetime | 更新时间 |
| reply_msg_id | bigint | 回复消息id |
| reply_time | datetime | 回复时间 |
| wait_interval | int | 等待时长（单位：秒），等于7200s（120分钟）为逾期未回复 |
| reply_content | text | 回复内容 |
| reply_msg_type | int | 回复消息类型（枚举同 msg_type） |
| reply_msg_scene | varchar | 回复消息场景："chat 聊天", "web 客服工作台发送", "ai_auto AI消息发送", "keyword 关键词回复" |
| reply_title | varchar | 文件/链接/视频号消息标题 |
| reply_href | varchar | 链接/视频号消息URL |
| process_time | datetime | 消息处理时间 |

**示例 1：查询某营期学员消息跟进明细与等待时长**
```sql
SELECT
  `m`.`id`               AS `msg_id`,
  `m`.`term_id`,
  `m`.`account_id`,
  `m`.`msg_time`,
  `m`.`msg_content`,
  `m`.`msg_type`,
  `m`.`state`,
  `m`.`reply_time`,
  `m`.`wait_interval`,
  `m`.`reply_msg_scene`
FROM `warehouse`.`ods_lh_efficiency_platform_term_student_chat_message_all` `m`
WHERE 1=1
  AND `m`.`term_id` IN ({{term_ids}})
  [[ AND `m`.`account_id` IN ({{account_ids}}) ]]
  [[ AND `m`.`msg_time` BETWEEN {{start_time}} AND {{end_time}} ]]
ORDER BY `m`.`msg_time` DESC
```

---
