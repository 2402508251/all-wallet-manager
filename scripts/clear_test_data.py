import os
import sys
sys.path.insert(0, '.')

import sqlite3

db_path = 'data/wallet.db'
if not os.path.exists(db_path):
    print('数据库文件不存在')
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== 清除前数据统计 ===')
tables = ['unified_bills', 'source_bills', 'import_batches', 'collection_records', 'snapshots', 'snapshot_details', 'bill_accounting', 'credit_accounts']
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    count = cursor.fetchone()[0]
    print(f"{t}: {count} 条")

print('')
print('正在清除测试数据...')

# 清除测试数据（保留预置数据）
tables_to_clear = ['unified_bills', 'source_bills', 'import_batches', 'collection_records', 'snapshots', 'snapshot_details', 'bill_accounting', 'credit_accounts']
for t in tables_to_clear:
    cursor.execute(f"DELETE FROM {t}")
    print(f"{t} 已清除")

# 重置自增序列
cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('unified_bills', 'source_bills', 'import_batches', 'collection_records', 'snapshots', 'snapshot_details', 'bill_accounting', 'credit_accounts')")
print("自增序列已重置")

conn.commit()
conn.close()

print('')
print('=== 清除后数据统计 ===')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    count = cursor.fetchone()[0]
    print(f"{t}: {count} 条")

conn.close()

print('')
print('测试数据已清除完成')