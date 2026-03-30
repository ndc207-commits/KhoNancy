import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
from datetime import datetime
from io import BytesIO
from pyzbar.pyzbar import decode
import cv2
import numpy as np

st.set_page_config(page_title="Quản lý kho", layout="wide")

# ================= DATABASE =================
conn = sqlite3.connect("warehouse.db", check_same_thread=False)
cursor = conn.cursor()

# Tạo bảng nếu chưa có
cursor.execute("""
CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    code TEXT UNIQUE
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS stock (
    product_id INTEGER,
    warehouse_id INTEGER,
    quantity INTEGER,
    PRIMARY KEY (product_id, warehouse_id)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    warehouse_id INTEGER,
    type TEXT,
    quantity INTEGER,
    date TEXT,
    user TEXT,
    undone INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password BLOB,
    role TEXT,
    warehouse_id INTEGER
)
""")
conn.commit()


# ================= TẠO KHO =================
for name in ["La Pagode", "Muse", "Metz Ville", "Nancy"]:
    cursor.execute("INSERT OR IGNORE INTO warehouses (name) VALUES (?)", (name,))

# ================= TẠO ADMIN =================
admin_password = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
cursor.execute("""
INSERT OR IGNORE INTO users (username,password,role,warehouse_id) 
VALUES (?,?,?,?)
""", ("admin", admin_password, "admin", None))

# ================= TẠO USER DEMO =================
user_demo = [
    ("nancy", "nancy123", "user", "Nancy"),
    ("muse", "muse123", "user", "Muse"),
    ("metz", "metz123", "user", "Metz Ville"),
    ("lapagode", "lp123", "user", "La Pagode")
]

for u,p,role,wh_name in user_demo:
    cursor.execute("SELECT id FROM warehouses WHERE name=?",(wh_name,))
    wh_id = cursor.fetchone()[0]
    hashed = bcrypt.hashpw(p.encode(), bcrypt.gensalt())
    cursor.execute("""
    INSERT OR IGNORE INTO users (username,password,role,warehouse_id) 
    VALUES (?,?,?,?)
    """, (u,hashed,role,wh_id))

conn.commit()
conn.close()
print("✅ Khởi tạo dữ liệu thành công!")


# ================= AUTH =================
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

if "login" not in st.session_state:
    st.session_state["login"] = False

# ================= LOGIN / REGISTER =================
def login():
    st.subheader("Đăng nhập")
    u = st.text_input("Tên đăng nhập")
    p = st.text_input("Mật khẩu", type="password")
    if st.button("Đăng nhập"):
        cursor.execute("SELECT password, role, warehouse_id FROM users WHERE username=?", (u,))
        user = cursor.fetchone()
        if user and check_password(p, user[0]):
            st.session_state["login"] = True
            st.session_state["role"] = user[1]
            st.session_state["warehouse_id"] = user[2]
            st.session_state["user"] = u
        else:
            st.error("Sai tên đăng nhập hoặc mật khẩu")

def register():
    st.subheader("Đăng ký")
    u = st.text_input("Tên đăng nhập mới")
    p = st.text_input("Mật khẩu mới", type="password")
    role = st.selectbox("Vai trò", ["user", "admin"])
    if role=="user":
        warehouses = [w[0] for w in cursor.execute("SELECT name FROM warehouses").fetchall()]
        warehouse_name = st.selectbox("Chọn kho", warehouses)
        warehouse_id = cursor.execute("SELECT id FROM warehouses WHERE name=?",(warehouse_name,)).fetchone()[0]
    else:
        warehouse_id = None
    if st.button("Tạo tài khoản"):
        try:
            cursor.execute("INSERT INTO users (username,password,role,warehouse_id) VALUES (?,?,?,?)",
                           (u, hash_password(p), role, warehouse_id))
            conn.commit()
            st.success("Tạo tài khoản thành công!")
        except:
            st.error("Tên đăng nhập đã tồn tại")

# ================= MAIN =================
if not st.session_state["login"]:
    st.sidebar.title("Menu")
    menu = st.sidebar.selectbox("Chọn", ["Đăng nhập", "Đăng ký"])
    if menu=="Đăng nhập":
        login()
    else:
        register()
else:
    st.sidebar.title(f"Xin chào, {st.session_state['user']}")
    menu = st.sidebar.radio("Menu", [
        "Kho tổng", "Nhập/Xuất", "Thêm sản phẩm",
        "Cảnh báo tồn kho", "Lịch sử", "Dashboard",
        "Scan QR/Barcode", "Chuyển kho", "Xuất Excel"
    ])

    # Xác định kho cho user
    if st.session_state["role"]=="admin":
        warehouses = cursor.execute("SELECT id,name FROM warehouses").fetchall()
        kho_select = st.sidebar.selectbox("Chọn kho", [w[1] for w in warehouses])
        warehouse_id = [w[0] for w in warehouses if w[1]==kho_select][0]
    else:
        warehouse_id = st.session_state["warehouse_id"]
        kho_name = cursor.execute("SELECT name FROM warehouses WHERE id=?",(warehouse_id,)).fetchone()[0]
        st.sidebar.text(f"Kho của bạn: {kho_name}")
        kho_select = kho_name

    # ================= KHO TỔNG =================
    if menu=="Kho tổng":
        st.title(f"🏬 Kho tổng - {kho_select}")
        df = pd.read_sql("""
            SELECT p.id,p.name,p.code,s.quantity
            FROM products p
            JOIN stock s ON p.id=s.product_id
            WHERE s.warehouse_id=?
        """, conn, params=(warehouse_id,))
        if st.session_state["role"]=="admin":
            edited_df = st.data_editor(df, num_rows="dynamic")
            if st.button("💾 Lưu thay đổi"):
                for i,row in edited_df.iterrows():
                    old_qty = df.loc[i,"quantity"]
                    new_qty = row["quantity"]
                    if new_qty != old_qty:
                        diff = new_qty - old_qty
                        cursor.execute("UPDATE stock SET quantity=? WHERE product_id=? AND warehouse_id=?",
                                       (new_qty,row["id"],warehouse_id))
                        cursor.execute("INSERT INTO transactions VALUES (NULL,?,?,?,?,?,0)",
                                       (row["id"],warehouse_id,"adjust",diff,datetime.now(),st.session_state["user"]))
                conn.commit()
                st.success("Cập nhật thành công!")
        else:
            st.dataframe(df)

    # ================= NHẬP / XUẤT =================
    elif menu=="Nhập/Xuất":
        st.title(f"📥📤 Nhập / Xuất kho - {kho_select}")
        products = cursor.execute("""
            SELECT p.id,p.name,p.code,s.quantity
            FROM products p
            JOIN stock s ON p.id=s.product_id
            WHERE s.warehouse_id=?
        """,(warehouse_id,)).fetchall()
        d = {f"{p[1]} ({p[2]})": (p[0],p[3]) for p in products}
        p = st.selectbox("Chọn sản phẩm", list(d.keys()))
        qty = st.number_input("Số lượng", 1)
        action = st.radio("Hành động", ["Nhập kho","Xuất kho"])
        if st.button("Thực hiện"):
            pid,current = d[p]
            if action=="Nhập kho":
                cursor.execute("UPDATE stock SET quantity=quantity+? WHERE product_id=? AND warehouse_id=?",
                               (qty,pid,warehouse_id))
                cursor.execute("INSERT INTO transactions VALUES (NULL,?,?,?,?,?,0)",
                               (pid,warehouse_id,"import",qty,datetime.now(),st.session_state["user"]))
                conn.commit()
                st.success("Nhập kho thành công!")
            else:
                if qty>current:
                    st.error("Không đủ hàng!")
                else:
                    cursor.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?",
                                   (qty,pid,warehouse_id))
                    cursor.execute("INSERT INTO transactions VALUES (NULL,?,?,?,?,?,0)",
                                   (pid,warehouse_id,"export",qty,datetime.now(),st.session_state["user"]))
                    conn.commit()
                    st.success("Xuất kho thành công!")

    # ================= THÊM SẢN PHẨM =================
    elif menu=="Thêm sản phẩm":
        st.title(f"➕ Thêm sản phẩm - {kho_select}")
        name = st.text_input("Tên sản phẩm")
        code = st.text_input("Mã sản phẩm")
        qty = st.number_input("Số lượng",0)
        if st.button("Thêm sản phẩm"):
            try:
                cursor.execute("INSERT OR IGNORE INTO products (name,code) VALUES (?,?)",(name,code))
                product_id = cursor.execute("SELECT id FROM products WHERE code=?",(code,)).fetchone()[0]
                cursor.execute("INSERT OR REPLACE INTO stock (product_id,warehouse_id,quantity) VALUES (?,?,?)",
                               (product_id,warehouse_id,qty))
                conn.commit()
                st.success("Thêm sản phẩm thành công!")
            except:
                st.error("Có lỗi xảy ra!")

    # ================= CẢNH BÁO =================
    elif menu=="Cảnh báo tồn kho":
        st.title(f"⚠️ Cảnh báo tồn kho - {kho_select}")
        df = pd.read_sql("""
            SELECT p.name,p.code,s.quantity
            FROM products p
            JOIN stock s ON p.id=s.product_id
            WHERE s.warehouse_id=?
        """,(warehouse_id,))
        df_warn = df[df["quantity"]<=5]
        if df_warn.empty:
            st.success("Không có sản phẩm nào sắp hết kho")
        else:
            for i,row in df_warn.iterrows():
                st.warning(f"Sản phẩm {row['name']} ({row['code']}) sắp hết! Tồn: {row['quantity']}")
            st.dataframe(df_warn)

    # ================= LỊCH SỬ =================
    elif menu=="Lịch sử":
        st.title(f"📜 Lịch sử giao dịch - {kho_select}")
        df_trans = pd.read_sql("""
            SELECT t.id,p.name,p.code,t.type,t.quantity,t.date,t.user,t.undone
            FROM transactions t
            JOIN products p ON t.product_id=p.id
            WHERE t.warehouse_id=?
            ORDER BY t.date DESC
        """,(warehouse_id,))
        st.dataframe(df_trans)
        if st.session_state["role"]=="admin":
            st.subheader("🔄 Hoàn tác giao dịch")
            trans_id = st.number_input("ID giao dịch",min_value=1)
            if st.button("Hoàn tác"):
                t = cursor.execute("SELECT product_id,type,quantity,undone FROM transactions WHERE id=?",(trans_id,)).fetchone()
                if not t:
                    st.error("Không tồn tại giao dịch")
                elif t[3]==1:
                    st.warning("Giao dịch đã hoàn tác")
                else:
                    pid,t_type,qty,_ = t
                    if t_type=="import":
                        cursor.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?",(qty,pid,warehouse_id))
                    elif t_type=="export":
                        cursor.execute("UPDATE stock SET quantity=quantity+? WHERE product_id=? AND warehouse_id=?",(qty,pid,warehouse_id))
                    elif t_type=="adjust":
                        cursor.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?",(qty,pid,warehouse_id))
                    cursor.execute("UPDATE transactions SET undone=1 WHERE id=?",(trans_id,))
                    conn.commit()
                    st.success("Hoàn tác thành công!")

    # ================= DASHBOARD =================
    elif menu=="Dashboard":
        st.title(f"📊 Dashboard tồn kho - {kho_select}")
        df = pd.read_sql("""
            SELECT p.name,p.code,s.quantity
            FROM products p
            JOIN stock s ON p.id=s.product_id
            WHERE s.warehouse_id=?
        """,(warehouse_id,))
        st.dataframe(df)
        st.bar_chart(df.set_index("name"))
        st.subheader("Cảnh báo tồn kho ≤5")
        df_warn = df[df["quantity"]<=5]
        if df_warn.empty:
            st.success("Không có sản phẩm nào sắp hết kho")
        else:
            st.dataframe(df_warn)

    # ================= SCAN QR / BARCODE =================
    elif menu=="Scan QR/Barcode":
        st.title("📷 Scan QR / Barcode")
        img_file = st.camera_input("Scan sản phẩm")
        if img_file:
            bytes_data = img_file.getvalue()
            np_arr = np.frombuffer(bytes_data,np.uint8)
            img = cv2.imdecode(np_arr,cv2.IMREAD_COLOR)
            decoded = decode(img)
            if decoded:
                code = decoded[0].data.decode("utf-8")
                st.success(f"Mã sản phẩm: {code}")
                prod = cursor.execute("""
                    SELECT p.name,s.quantity
                    FROM products p
                    JOIN stock s ON p.id=s.product_id
                    WHERE p.code=? AND s.warehouse_id=?
                """,(code,warehouse_id)).fetchone()
                if prod:
                    st.info(f"Sản phẩm: {prod[0]} | Tồn kho: {prod[1]}")
                else:
                    st.warning("Sản phẩm chưa có trong kho")
            else:
                st.warning("Không đọc được QR / Barcode")

    # ================= CHUYỂN KHO =================
    elif menu=="Chuyển kho":
        st.title("🔄 Chuyển kho")
        if st.session_state["role"]!="admin":
            st.warning("Chỉ admin mới có quyền chuyển kho")
        else:
            products = cursor.execute("SELECT id,name,code FROM products").fetchall()
            d = {f"{p[1]} ({p[2]})":p[0] for p in products}
            p = st.selectbox("Chọn sản phẩm",list(d.keys()))
            qty = st.number_input("Số lượng",1)
            warehouses = cursor.execute("SELECT id,name FROM warehouses").fetchall()
            wh_dict = {w[1]:w[0] for w in warehouses}
            from_wh = st.selectbox("Từ kho", [w[1] for w in warehouses])
            to_wh = st.selectbox("Đến kho", [w[1] for w in warehouses if w[1]!=from_wh])
            if st.button("Chuyển"):
                pid = d[p]
                from_id = wh_dict[from_wh]
                to_id = wh_dict[to_wh]
                current = cursor.execute("SELECT quantity FROM stock WHERE product_id=? AND warehouse_id=?",(pid,from_id)).fetchone()
                if not current or current[0]<qty:
                    st.error("Không đủ hàng để chuyển")
                else:
                    cursor.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?",(qty,pid,from_id))
                    cursor.execute("INSERT OR REPLACE INTO stock (product_id,warehouse_id,quantity) VALUES (?,?,COALESCE((SELECT quantity FROM stock WHERE product_id=? AND warehouse_id=?),0)+?)",(pid,to_id,pid,to_id,qty))
                    cursor.execute("INSERT INTO transactions VALUES (NULL,?,?,?,?,?,0)",(pid,from_id,"export",qty,datetime.now(),st.session_state["user"]))
                    cursor.execute("INSERT INTO transactions VALUES (NULL,?,?,?,?,?,0)",(pid,to_id,"import",qty,datetime.now(),st.session_state["user"]))
                    conn.commit()
                    st.success("Chuyển kho thành công!")

    # ================= XUẤT EXCEL =================
    elif menu=="Xuất Excel":
        st.title(f"📥 Xuất báo cáo Excel - {kho_select}")
        df_stock = pd.read_sql("""
            SELECT p.name,p.code,s.quantity
            FROM products p
            JOIN stock s ON p.id=s.product_id
            WHERE s.warehouse_id=?
        """,(warehouse_id,))
        df_trans = pd.read_sql("""
            SELECT t.id,p.name,p.code,t.type,t.quantity,t.date,t.user,t.undone
            FROM transactions t
            JOIN products p ON t.product_id=p.id
            WHERE t.warehouse_id=?
            ORDER BY t.date DESC
        """,(warehouse_id,))
        df_warn = df_stock[df_stock["quantity"]<=5]

        buffer = BytesIO()
        with pd.ExcelWriter(buffer,engine="openpyxl") as writer:
            df_stock.to_excel(writer,index=False,sheet_name="Tồn kho")
            df_trans.to_excel(writer,index=False,sheet_name="Lịch sử giao dịch")
            df_warn.to_excel(writer,index=False,sheet_name="Cảnh báo tồn kho")
            writer.save()
        st.download_button(
            label="Tải Excel",
            data=buffer.getvalue(),
            file_name=f"bao_cao_{kho_select}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
