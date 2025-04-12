import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# تحميل ملف الإكسل
df = pd.read_excel("chat_messages (1).xlsx")

# ترتيب وتنظيف الأعمدة
df_cleaned = pd.DataFrame({
    'system_time': pd.to_datetime(df.iloc[:, 0], errors='coerce'),
    'time_sent': pd.to_datetime(df.iloc[:, 0], errors='coerce').dt.strftime('%H:%M'),
    'username': df.iloc[:, 2].astype(str),
    'message': df.iloc[:, 3].astype(str)
})
df_cleaned.dropna(subset=['system_time', 'username', 'message'], inplace=True)

# إنشاء قاعدة بيانات جديدة
engine = create_engine("sqlite:///chat_messages_with_excel.db")

# إدخال البيانات
df_cleaned.to_sql("messages", con=engine, if_exists="replace", index=False)

print(f"✅ تم إنشاء قاعدة بيانات جديدة وفيها {len(df_cleaned)} رسالة.")
