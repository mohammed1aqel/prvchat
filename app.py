# -*- coding: utf-8 -*- # السطر هذا مهم لو فيه تعليقات عربي

# --- Imports ---
from flask import Flask, render_template, jsonify, request, session # *** تعديل: تم إضافة session هنا ***
import threading
import time
import re
import os # *** تعديل: تم إضافة os ***
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from datetime import datetime # *** تعديل: تم التأكد من استيراد datetime ***
# لا تستخدم requests لإرسال الرسائل لنفسك، استخدم MongoDB مباشرة
# import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse
from pymongo import MongoClient
# from bson.objectid import ObjectId # يمكن إضافته إذا أردت استخدام _id بشكل مباشر

# --- Constants and Setup ---
# ✅ رابط الشات للقناة
chat_url = os.environ.get("KICK_CHAT_URL", "https://kick.com/popout/maherco/chat") # الأفضل كمتغير بيئة

# ✅ استخراج اسم القناة من الرابط
try:
    parsed_url = urlparse(chat_url)
    channel_name = parsed_url.path.strip("/").split("/")[1]
except IndexError:
    channel_name = "default_channel"
    logging.error(f"Could not parse channel name from URL: {chat_url}. Using default.")


# --- إعداد MongoDB ---
# الأفضل كمتغير بيئة في Render
MONGO_URI = os.environ.get("MONGODB_URI", "mongodb+srv://kickuser:kickpass123@kickchat.nxjlt79.mongodb.net/?retryWrites=true&w=majority&appName=kickchat")
try:
    client = MongoClient(MONGO_URI)
    db = client["kick_chat"] # اسم قاعدة البيانات
    # استخدم اسم القناة في اسم المجموعة لتمييز القنوات المختلفة إذا لزم الأمر
    collection_name = f"messages_{channel_name}"
    collection = db[collection_name]
    # Test connection
    client.admin.command('ping')
    logging.info("✅ MongoDB connection successful.")
    # *** إضافة فهرس لـ system_time لتحسين أداء جلب الرسائل الجديدة ***
    collection.create_index("system_time")
    logging.info(f"Ensured index exists for 'system_time' in collection '{collection_name}'")

except Exception as e:
    logging.error(f"❌ Failed to connect to MongoDB: {e}", exc_info=True)
    # يمكنك اختيار إيقاف التطبيق هنا إذا كان الاتصال بقاعدة البيانات ضروريًا
    # exit()
    db = None
    collection = None


# --- إعداد التسجيل (Logging) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App Setup ---
app = Flask(__name__)
# *** تعديل: إضافة المفتاح السري - مهم لعمل session (حتى لو لم تستخدمه مباشرة) ***
# اقرأه من متغيرات البيئة في Render، وضع قيمة افتراضية للتطوير المحلي
app.secret_key = os.environ.get('SECRET_KEY', 'a_very_secret_key_for_dev_only_123!')
if app.secret_key == 'a_very_secret_key_for_dev_only_123!' and os.environ.get('RENDER'):
    logging.warning("⚠️ Using default SECRET_KEY in production (Render)! Please set the SECRET_KEY environment variable.")


# --- هياكل البيانات العامة (للسيلينيوم) ---
processed_messages = set()   # مجموعة لتتبع الرسائل الفريدة ومنع التكرار داخل دورة السيلينيوم

# --- متصفح Selenium ---
# (الكود الخاص بـ start_selenium يبقى كما هو إلى حد كبير)
# *** تعديل مهم داخل start_selenium ***
def start_selenium():
    global driver, processed_messages # لا تحتاج messages_data هنا

    # ... (إعدادات options كما هي) ...

    while True: # حلقة لإعادة المحاولة إذا فشل المتصفح
        driver = None # تأكد من أنه None في بداية كل محاولة
        try:
            logging.info("🚀 تهيئة متصفح Selenium...")
            # ... (إعدادات options كما هي) ...
            # *** تعديل: أضف هذه الخيارات الخاصة بـ Render/Linux headless ***
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox') # مهم جدًا في بيئات مثل Render
            options.add_argument('--disable-dev-shm-usage') # مهم جدًا في بيئات محدودة الموارد

            driver = webdriver.Chrome(options=options)
            logging.info("🧭 الانتقال إلى شات Kick...")
            driver.set_page_load_timeout(60)
            driver.get(chat_url)

            chat_container_locator = (By.CSS_SELECTOR, 'div.group')
            logging.info(f"🕒 في انتظار ظهور أول رسالة باستخدام المحدد: {chat_container_locator}")
            WebDriverWait(driver, 60).until( # زيادة المهلة أكثر قليلاً
                EC.presence_of_element_located(chat_container_locator)
            )
            logging.info("✅ تم العثور على أول رسالة، يفترض أن الشات قد تم تحميله.")
            time.sleep(3)

            while True:
                try:
                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    message_elements = soup.find_all('div', class_='group')
                    logging.debug(f"🔍 تم العثور على {len(message_elements)} عنصر 'div.group' محتمل.")

                    new_messages_saved_this_cycle = 0
                    for message in message_elements:
                        try:
                            # ... (استخراج time_sent_str, time_sent, user_name, message_text_cleaned كما هو) ...
                            # --- (نفس كود الاستخراج والتنظيف للوقت والمستخدم والرسالة) ---
                            time_span = message.find('span', class_='text-neutral') # محدد مؤكد
                            time_sent_str = time_span.text.strip() if time_span else "--:--"
                            time_sent_clean = re.sub(r'\s*(AM|PM)$', '', time_sent_str, flags=re.IGNORECASE).strip()
                            try:
                                parsed_time = datetime.strptime(time_sent_clean, '%H:%M')
                                time_sent = parsed_time.strftime('%H:%M')
                            except ValueError:
                                try:
                                     parsed_time = datetime.strptime(time_sent_clean, '%I:%M')
                                     time_sent = parsed_time.strftime('%H:%M')
                                except ValueError:
                                     time_sent = "--:--"

                            user_button = message.find('button', class_='inline font-bold')
                            user_name = user_button.text.strip() if user_button else "Unknown"
                            if not user_name and user_button and user_button.has_attr('title'):
                                user_name = user_button['title'].strip()
                            if user_name == "Unknown":
                                user_span = message.find('span', class_='chat-entry-username')
                                if user_span: user_name = user_span.text.strip()

                            content_div = message.find('div', class_=lambda c: c and 'break-words' in c.split())
                            if not content_div:
                                content_span = message.find('span', class_='font-normal')
                                if content_span: content_div = content_span
                                else: continue

                            for img in content_div.find_all("img"):
                                if img.has_attr("alt"): img.replace_with(f" {img['alt'].strip()} ")

                            message_text = content_div.get_text(separator=' ', strip=True)
                            message_text = re.sub(rf'^\s*{re.escape(user_name)}\s*[:：]?\s*', '', message_text, flags=re.IGNORECASE).strip()
                            message_text = re.sub(r'\b\d{1,2}:\d{2}(?:\s?[APMapm]{2})?\b', '', message_text).strip()
                            message_text_cleaned = re.sub(rf'^\s*{re.escape(user_name)}\s*[:：]?\s*', '', message_text, flags=re.IGNORECASE).strip()
                            message_text_cleaned = re.sub(r'\b(?:\d{1,2}-Month Subscriber|Gifted Sub|Tier \d|VIP|Founder|Moderator)\b', '', message_text_cleaned, flags=re.IGNORECASE).strip()
                            message_text_cleaned = re.sub(r'\s{2,}', ' ', message_text_cleaned).strip()


                            if not message_text_cleaned:
                                logging.debug(f"رسالة فارغة بعد التنظيف للمستخدم {user_name}.")
                                continue

                            # وقت النظام عند المعالجة
                            # system_time = datetime.now() # استخدم datetime object
                            # *** تعديل: تأكد من استخدام التوقيت العالمي المنسق (UTC) لقاعدة البيانات ***
                            system_time_utc = datetime.utcnow()

                            message_signature = f"{time_sent}_{user_name}_{message_text_cleaned[:50]}"
                            unique_id_for_session = re.sub(r'\s+', '_', message_signature.strip().lower())

                            # --- إضافة الرسالة إلى MongoDB إذا لم تتم معالجتها في هذه الجلسة ---
                            if unique_id_for_session not in processed_messages:
                                if collection: # تأكد من أن الاتصال بقاعدة البيانات ناجح
                                    try:
                                        # *** تعديل: الحفظ مباشرة في MongoDB ***
                                        message_doc = {
                                            "system_time": system_time_utc, # تخزين كـ datetime object (UTC)
                                            "time_sent": time_sent,
                                            "username": user_name,
                                            "message": message_text_cleaned,
                                            "channel": channel_name # إضافة اسم القناة للفرز لاحقاً إذا لزم الأمر
                                        }
                                        # استخدم update_one مع upsert=True للتحقق من عدم وجود الرسالة بناءً على المحتوى/الوقت
                                        # هذا يوفر حماية إضافية ضد التكرار إذا أعيد تشغيل السكربت وقرأ نفس الرسائل القديمة
                                        # سنستخدم معيار بسيط هنا: نفس المستخدم، نفس النص، ونفس وقت الإرسال الظاهر
                                        filter_query = {
                                            "username": user_name,
                                            "message": message_text_cleaned,
                                            "time_sent": time_sent
                                        }
                                        # $setOnInsert يضيف الحقول فقط إذا كان المستند جديدًا (upsert)
                                        update_result = collection.update_one(
                                            filter_query,
                                            { "$setOnInsert": message_doc },
                                            upsert=True
                                        )

                                        if update_result.upserted_id:
                                            logging.debug(f"💾 تم حفظ رسالة جديدة في MongoDB (ID: {update_result.upserted_id})")
                                            processed_messages.add(unique_id_for_session)
                                            new_messages_saved_this_cycle += 1
                                        elif update_result.matched_count > 0:
                                            logging.debug(f"🔄 تم العثور على رسالة مكررة (نفس المستخدم/النص/الوقت)، لم يتم إعادة إدراجها.")
                                            # أضفها إلى processed_messages لهذه الجلسة أيضًا لمنع إعادة المعالجة
                                            processed_messages.add(unique_id_for_session)
                                        else:
                                            # لم يتم التحديث ولم يتم الإدراج - حالة غريبة
                                             logging.warning(f"❓ حالة غير متوقعة من update_one لرسالة {user_name}: {message_text_cleaned}")


                                    except Exception as db_error:
                                        logging.error(f"❌ خطأ أثناء حفظ الرسالة في MongoDB: {db_error}", exc_info=True)
                                else:
                                    logging.warning("⚠️ MongoDB connection not available. Message not saved.")
                                    # أضفها لـ processed_messages لتجنب محاولة حفظها مراراً
                                    processed_messages.add(unique_id_for_session)


                        # ... (معالجة الاستثناءات StaleElementReferenceException وغيرها كما هي) ...
                        except StaleElementReferenceException:
                             logging.warning(" عنصر قديم (StaleElementReferenceException)، سيتم تجاهله والمتابعة.")
                             continue
                        except Exception as e:
                             logging.error(f"⚠️ خطأ في معالجة رسالة فردية للمستخدم '{user_name}': {e}", exc_info=True)


                    if new_messages_saved_this_cycle > 0:
                         logging.info(f"💾 تم حفظ {new_messages_saved_this_cycle} رسالة جديدة في MongoDB.")

                # ... (معالجة الاستثناءات الخارجية KeyboardInterrupt وغيرها كما هي) ...
                except KeyboardInterrupt:
                     raise
                except Exception as e:
                    logging.error(f"💥 خطأ في حلقة قراءة الرسائل الرئيسية: {e}", exc_info=True)
                    # لا تقم بإعادة تحميل الصفحة تلقائيًا، قد يسبب مشاكل. دع الحلقة الخارجية تعيد تشغيل المتصفح.
                    time.sleep(5) # انتظر قليلاً قبل الدورة التالية عند حدوث خطأ

                time.sleep(1.5)

        # ... (باقي كود معالجة الاستثناءات TimeoutException و finally كما هو) ...
        except KeyboardInterrupt:
             logging.info("🛑 تم طلب الإيقاف (KeyboardInterrupt).")
             break
        except TimeoutException:
            logging.error(f"⏳ انتهت مهلة انتظار تحميل عنصر الشات المحدد ({chat_container_locator}).")
        except Exception as e:
            logging.error(f"❌ فشل كبير في تشغيل Selenium أو الاتصال بالصفحة: {e}", exc_info=True)
        finally:
            if driver:
                logging.warning("🚦 إغلاق متصفح Selenium الحالي...")
                driver.quit() # استخدم quit() بدلاً من close() لإغلاق المتصفح تمامًا
                # لا تحتاج لتعيين driver = None هنا، سيتم إعادة تعيينه في بداية الحلقة الخارجية
            if not isinstance(e, KeyboardInterrupt):
                 logging.info("⏳ الانتظار 20 ثانية قبل محاولة إعادة تشغيل Selenium...")
                 time.sleep(20) # زيادة وقت الانتظار قليلاً
            else:
                 break # اخرج إذا كان السبب هو KeyboardInterrupt

# --- بدء خيط Selenium ---
# تأكد من أن هذه البداية بعد تعريف الدالة وقبل تشغيل Flask
selenium_thread = threading.Thread(target=start_selenium, daemon=True)
selenium_thread.start()


# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/log')
def message_log():
    # لا نحتاج لتمرير أي بيانات هنا، log.html سيطلبها عبر /get_all_messages
    return render_template('log.html')

# --- *** تعديل: نقطة نهاية لجلب *كل* الرسائل من MongoDB *** ---
@app.route('/get_all_messages')
def get_all_messages():
    if collection is None:
         logging.error("get_all_messages: Attempted to access when collection is None.")
         return jsonify({"error": "Database connection not available"}), 503
    try:
        # جلب كل الرسائل وفرزها حسب وقت النظام (الأحدث أولاً كمثال، أو الأقدم أولاً)
        # الفرز في قاعدة البيانات أفضل من الفرز في بايثون للكميات الكبيرة
        all_msgs_cursor = collection.find({"channel": channel_name}).sort("system_time", -1) # -1 للأحدث أولاً

        messages_list = []
        for msg in all_msgs_cursor:
            messages_list.append({
                # *** تعديل: تحويل _id إلى نص وإرجاع الحقول الصحيحة ***
                "id": str(msg["_id"]), # تحويل ObjectId إلى string
                # تحويل datetime إلى ISO format string (متوافق مع JS Date)
                "system_time": msg["system_time"].isoformat() + "Z", # إضافة Z للإشارة إلى UTC
                "time_sent": msg.get("time_sent", "--:--"), # استخدام .get للأمان
                "username": msg.get("username", "Unknown"),
                "message": msg.get("message", "")
            })
        return jsonify(messages_list)
    except Exception as e:
        logging.error(f"Error fetching all messages: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch messages from database"}), 500


# --- *** تعديل: نقطة نهاية للحصول على الرسائل *الجديدة* فقط من MongoDB *** ---
@app.route('/get_new_messages')
def get_new_messages():
    if collection is None:
         return jsonify({"error": "Database connection not available"}), 503

    # *** تعديل: استقبال 'since' كطابع زمني (ISO string) ***
    since_timestamp_str = request.args.get("since")
    query = {"channel": channel_name} # فلترة حسب القناة دائمًا

    if since_timestamp_str:
        try:
            # *** تعديل: محاولة تحليل الطابع الزمني ***
            # إزالة 'Z' إذا كانت موجودة للتحليل الصحيح كـ UTC naive
            if since_timestamp_str.endswith('Z'):
                since_timestamp_str = since_timestamp_str[:-1]
            since_datetime = datetime.fromisoformat(since_timestamp_str)
            # *** تعديل: بناء استعلام MongoDB للبحث عن الأحدث ***
            query["system_time"] = {"$gt": since_datetime}
        except ValueError:
            logging.warning(f"Invalid 'since' timestamp format received: {since_timestamp_str}")
            # إذا كان التنسيق خاطئًا، لا ترجع شيئًا أو أرجع خطأ
            return jsonify({"error": "Invalid 'since' timestamp format"}), 400

    try:
        # *** تعديل: جلب الرسائل الأحدث وفرزها تصاعديًا لتطبيقها بالترتيب الصحيح في الواجهة ***
        new_msgs_cursor = collection.find(query).sort("system_time", 1) # 1 للأقدم أولاً (الترتيب الصحيح للإضافة)

        messages_list = []
        for msg in new_msgs_cursor:
             messages_list.append({
                "id": str(msg["_id"]),
                "system_time": msg["system_time"].isoformat() + "Z", # إضافة Z للإشارة إلى UTC
                "time_sent": msg.get("time_sent", "--:--"),
                "username": msg.get("username", "Unknown"),
                "message": msg.get("message", "")
            })

        # إذا لم يتم تقديم 'since'، قد لا ترغب في إرجاع أي شيء أو إرجاع عدد محدود جداً
        if not since_timestamp_str and len(messages_list) > 0:
             logging.warning("/get_new_messages called without 'since', returning potentially large list initially.")
             # يمكنك اختيار إرجاع قائمة فارغة هنا إذا أردت
             # return jsonify([])

        return jsonify(messages_list)

    except Exception as e:
        logging.error(f"Error fetching new messages: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch new messages from database"}), 500


# --- نقطة نهاية Debug (اختياري) ---
@app.route('/debug_messages')
def debug_messages():
    if collection is None:
         return "Database connection not available", 503
    try:
        # عرض آخر 10 رسائل محفوظة لهذه القناة
        msgs = collection.find({"channel": channel_name}).sort("system_time", -1).limit(10)
        output = f"<h2>آخر 10 رسائل من MongoDB (Collection: {collection_name}):</h2><ul>"
        count = 0
        for msg in msgs:
            username = msg.get("username", "مجهول")
            message = msg.get("message", "")
            time_rec = msg.get("system_time", "N/A")
            if isinstance(time_rec, datetime):
                time_rec = time_rec.strftime("%Y-%m-%d %H:%M:%S UTC")
            output += f"<li><i>[{time_rec}]</i> <b>{username}</b>: {message}</li>"
            count += 1
        if count == 0:
            output += "<li>لا توجد رسائل.</li>"
        output += "</ul>"
        return output
    except Exception as e:
        logging.error(f"Error in debug_messages: {e}", exc_info=True)
        return f"Error fetching debug messages: {e}", 500

# --- نقطة النهاية submit_message لم تعد ضرورية إذا كان Selenium يحفظ مباشرة ---
# يمكنك إزالتها أو تعديل Selenium ليبقى يستخدمها إذا أردت فصل المنطق
# @app.route('/submit_message', methods=['POST'])
# def submit_message():
#     # ... (الكود القديم هنا) ...


# --- تشغيل التطبيق ---
if __name__ == '__main__':
    # الحصول على البورت من متغيرات البيئة (مهم لـ Render) وإلا استخدم 5050
    port = int(os.environ.get('PORT', 5050))
    # استخدم use_reloader=False مهم جدًا لمنع تشغيل خيط Selenium مرتين
    logging.info(f"🚀 تشغيل خادم Flask على المنفذ {port}...")
    # host='0.0.0.0' مهم ليستمع الخادم على كل الواجهات (ضروري لـ Render)
    app.run(debug=False, port=port, host='0.0.0.0', use_reloader=False)

    # الكود هنا لن يتم الوصول إليه عادةً إلا إذا تم إيقاف الخادم برمجياً
    logging.info("🏁 تم إيقاف خادم Flask.")
