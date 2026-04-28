import streamlit as st

st.set_page_config(
    layout='wide'
)

st.session_state.tid = 20
st.session_state.camp_id = 102150

if "role" not in st.session_state:
    st.session_state.role = 'Admin'  # None

ROLES = [None, "Requester", "Admin"]


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
class_auth_stats = st.Page(
    "pages/data/class_auth_stats.py",
    title="班级授权学员数",
    icon=":material/bar_chart:",
)
data_pages = [student_list, class_auth_stats]

# 首页
# st.title("Request manager")
st.logo("images/horizontal_blue.png", icon_image="images/icon_blue.png")

page_dict = {}

if st.session_state.role == "Admin":
    page_dict["数据汇总"] = data_pages

if len(page_dict) > 0:
    pg = st.navigation(page_dict | {"Account": account_pages})
else:
    # 登录内容
    pg = st.navigation([st.Page(login)])

pg.run()
