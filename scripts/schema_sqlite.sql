-- ==============================================================================
-- NL2SQL Metabase 配置元数据 SQLite 数据库 Schema 定义文件
-- 保存位置: scripts/schema_sqlite.sql
-- 说明: 维护 SQLite 配置数据库的初始化表结构，变更 SQLite 表结构时须同步更新本文件。
-- ==============================================================================

-- 1. 表级元数据表
CREATE TABLE IF NOT EXISTS nl2sql_table_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    db_name TEXT NOT NULL DEFAULT 'warehouse',      -- 目标数据库名，如 warehouse
    table_name TEXT NOT NULL UNIQUE,                -- 数据表名，如 dim_lh_basic_team
    table_alias TEXT NOT NULL,                      -- 推荐 SQL 别名，如 t
    domain TEXT NOT NULL DEFAULT '未分类',            -- 所属业务板块，如 基础维度表 / 汇总统计表
    use_for TEXT NOT NULL DEFAULT '',               -- 业务场景说明（表选择决策依据）
    required_filters TEXT NOT NULL DEFAULT '',      -- 必须注入的强制 WHERE 条件 snippet
    optional_filters TEXT NOT NULL DEFAULT '',      -- 可选 WHERE 条件 snippet（含 [[ ]]）
    status INTEGER NOT NULL DEFAULT 1,              -- 状态: 1=正常, 0=停用
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 字段字典表
CREATE TABLE IF NOT EXISTS nl2sql_column_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,                      -- 外键 -> nl2sql_table_meta.id
    column_name TEXT NOT NULL,                      -- 字段名，如 camp_term_id
    data_type TEXT NOT NULL DEFAULT 'varchar',       -- 数据类型，如 int, varchar, datetime
    column_comment TEXT NOT NULL DEFAULT '',        -- 字段说明/业务含义
    ref_table_name TEXT DEFAULT NULL,               -- 关联外键表名，如 dim_lh_teaching_class_term
    ref_column_name TEXT DEFAULT NULL,              -- 关联外键字段名，如 id
    is_pk INTEGER NOT NULL DEFAULT 0,               -- 是否主键: 1=是, 0=否
    is_fk INTEGER NOT NULL DEFAULT 0,               -- 是否外键: 1=是, 0=否
    sort_order INTEGER NOT NULL DEFAULT 0,          -- 界面与展示排序字段
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (table_id) REFERENCES nl2sql_table_meta(id) ON DELETE CASCADE,
    UNIQUE(table_id, column_name)
);

-- 3. 表典型示例 SQL 表
CREATE TABLE IF NOT EXISTS nl2sql_table_example (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,                      -- 外键 -> nl2sql_table_meta.id
    example_name TEXT NOT NULL,                     -- 示例标题，如 示例 1：查询某团队所有营期列表
    sql_content TEXT NOT NULL,                      -- SQL 代码内容
    description TEXT NOT NULL DEFAULT '',           -- 示例补充说明
    sort_order INTEGER NOT NULL DEFAULT 0,          -- 排序字段
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (table_id) REFERENCES nl2sql_table_meta(id) ON DELETE CASCADE
);

-- 4. 常用/特定查询模板表 (对应 queries.md)
CREATE TABLE IF NOT EXISTS nl2sql_query_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,                     -- 模板名称，如 营期班级最新周基数查询
    category TEXT NOT NULL DEFAULT '常用查询',        -- 场景分类，如 最新周基数 / 率值计算
    scenario TEXT NOT NULL DEFAULT '',              -- 业务场景说明
    related_tables TEXT NOT NULL DEFAULT '',        -- 涉及的数据源表，逗号分隔
    sql_template TEXT NOT NULL,                     -- 完整 SQL 模板代码 (含 Metabase 变量)
    notes TEXT NOT NULL DEFAULT '',                 -- 规范与防错约定说明
    status INTEGER NOT NULL DEFAULT 1,              -- 状态: 1=正常, 0=停用
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引优化查询性能
CREATE INDEX IF NOT EXISTS idx_col_table_id ON nl2sql_column_meta(table_id);
CREATE INDEX IF NOT EXISTS idx_example_table_id ON nl2sql_table_example(table_id);
CREATE INDEX IF NOT EXISTS idx_template_category ON nl2sql_query_template(category);
