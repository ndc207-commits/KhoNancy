import sqlite3
import bcrypt

conn = sqlite3.connect("warehouse.db")
cursor = conn.cursor()

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
