import os
import sys
sys.path.insert(0, '.')

import sqlite3

db_path = 'data/wallet.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== 补充预置数据 ===')

# 检查分类表
cursor.execute("SELECT COUNT(*) FROM bill_categories")
count = cursor.fetchone()[0]
print(f'当前分类数量: {count}')

if count < 12:
    print('正在插入预置分类...')
    categories = [
        (1, "餐饮美食", "🍽️", None, 1),
        (2, "交通出行", "🚗", None, 2),
        (3, "购物消费", "🛒", None, 3),
        (4, "生活缴费", "🏠", None, 4),
        (5, "通讯网络", "📱", None, 5),
        (6, "医疗健康", "🏥", None, 6),
        (7, "教育学习", "📚", None, 7),
        (8, "休闲娱乐", "🎮", None, 8),
        (9, "居住房租", "🏡", None, 9),
        (10, "金融保险", "💰", None, 10),
        (11, "人情往来", "🎁", None, 11),
        (99, "其他支出", "📦", None, 99),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO bill_categories (id, name, icon, parent_id, sort_order) VALUES (?, ?, ?, ?, ?)",
        categories,
    )
    conn.commit()
    print('预置分类已插入')

# 检查家庭表
cursor.execute("SELECT COUNT(*) FROM families")
count = cursor.fetchone()[0]
print(f'当前家庭数量: {count}')

if count == 0:
    print('正在插入默认家庭...')
    cursor.execute(
        "INSERT OR IGNORE INTO families (id, name, is_default) VALUES (1, '默认家庭', 1)"
    )
    conn.commit()
    print('默认家庭已插入')

# 验证
print('')
print('=== 验证结果 ===')
cursor.execute("SELECT COUNT(*) FROM bill_categories")
print(f'分类数量: {cursor.fetchone()[0]}')

cursor.execute("SELECT COUNT(*) FROM families")
print(f'家庭数量: {cursor.fetchone()[0]}')

cursor.execute("SELECT id, name, icon FROM bill_categories ORDER BY sort_order")
print('')
print('分类列表:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]} {row[2]}')

conn.close()
print('')
print('预置数据补充完成')