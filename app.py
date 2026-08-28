import streamlit as st
from utils.query import render_sidebar_controls

st.set_page_config(
    layout='wide'
)

if "role" not in st.session_state:
    st.session_state.role = 'Admin'  # None

ROLES = [None, "Requester", "Admin"]

# 侧边栏：查询方式（默认 Metabase）+ tid/camp_id 列表（默认第一项）
render_sidebar_controls()


def login():

    st.header("Log in")
    # 登录
    role = st.selectbox("Choose your role", ROLES)

    if st.button("Log in"):
        st.session_state.role = role

        # 登录成功后，刷新页面
        st.rerun()


def logout():
    st.session_state.role = None
    st.rerun()


role = st.session_state.role

logout_page = st.Page(logout, title="Log out", icon=":material/logout:")
# settings = st.Page("pages/settings/general.py",
#                    title="通用设置", icon=":material/settings:")


account_pages = [logout_page]

student_list = st.Page(
    "pages/data/student_list.py",
    title="学员列表",
    icon=":material/person_search:",
)
student_message_list = st.Page(
    "pages/data/student_message_list.py",
    title="学员消息明细",
    icon=":material/chat:",
)
class_auth_stats = st.Page(
    "pages/data/class_auth_stats.py",
    title="班级授权学员数",
    icon=":material/bar_chart:",
)
category_refund_stats = st.Page(
    "pages/data/category_refund_stats.py",
    title="品类退款分析",
    icon=":material/money_off:",
)
class_week_stats = st.Page(
    "pages/data/class_week_stats.py",
    title="班级周数据汇总",
    icon=":material/date_range:",
)
data_pages = [
    student_list,
    student_message_list,
    class_auth_stats,
    category_refund_stats,
    class_week_stats,
]

nl2sql_config_page = st.Page(
    "pages/settings/nl2sql_config_mgmt.py",
    title="NL2SQL配置管理",
    icon=":material/settings_suggest:",
)

# 首页
# st.title("Request manager")
st.logo("images/horizontal_blue.png", icon_image="images/icon_blue.png")

page_dict = {}

if st.session_state.role == "Admin":
    page_dict["数据汇总"] = data_pages
    page_dict["系统配置"] = [nl2sql_config_page]

if len(page_dict) > 0:
    pg = st.navigation(page_dict | {"Account": account_pages})
else:
    # 登录内容
    pg = st.navigation([st.Page(login)])

pg.run()
