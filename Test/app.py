from flask import Flask, render_template, jsonify, request
import threading
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from datetime import datetime
from bs4 import BeautifulSoup
import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# إعداد قاعدة البيانات
Base = declarative_base()
engine = create_engine('sqlite:///chat_messages.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# تعريف جدول الرسائل
class ChatMessage(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    system_time = Column(DateTime)
    time_sent = Column(String)
    username = Column(String)
    message = Column(String)

# إنشاء الجداول (مرة واحدة)
Base.metadata.create_all(engine)



# --- إعداد التسجيل (Logging) ---
# يعرض معلومات مفيدة حول ما يفعله السكربت والأخطاء المحتملة
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- هياكل البيانات العامة ---
messages_data = []           # قائمة لتخزين جميع الرسائل المستلمة
processed_messages = set()   # مجموعة لتتبع الرسائل الفريدة ومنع التكرار
last_sent_index = 0          # مؤشر لتتبع آخر رسالة تم إرسالها إلى الواجهة الأمامية لتحسين الكفاءة

# --- متصفح Selenium ---
driver = None

def start_selenium():
    global driver, messages_data, processed_messages
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # اختياري: تشغيل المتصفح بدون واجهة رسومية
    # options.add_argument('--disable-gpu') # غالبًا ما يكون ضروريًا عند التشغيل بدون واجهة رسومية
    options.add_argument('--log-level=3') # لتقليل كمية الرسائل غير الضرورية من المتصفح/الويب درايفر
    options.add_argument("--mute-audio") # كتم صوت المتصفح
    options.add_argument("--disable-infobars") # تعطيل شريط المعلومات (مثل "Chrome is being controlled...")
    options.add_argument("--disable-extensions") # تعطيل الإضافات

    while True: # حلقة لإعادة المحاولة إذا فشل المتصفح
        try:
            logging.info("🚀 تهيئة متصفح Selenium...")
            driver = webdriver.Chrome(options=options)
            logging.info("🧭 الانتقال إلى شات Kick...")
            # --- زيادة مهلة تحميل الصفحة الافتراضية ---
            driver.set_page_load_timeout(60) # الانتظار حتى 60 ثانية لتحميل الصفحة
            driver.get("https://kick.com/popout/maherco/chat") # تأكد من صحة اسم المستخدم

            # --- الانتظار حتى يتم تحميل عنصر الشات الرئيسي (أول رسالة) ---
            # ننتظر ظهور أول عنصر رسالة يحمل الكلاس 'group'
            chat_container_locator = (By.CSS_SELECTOR, 'div.group')
            logging.info(f"🕒 في انتظار ظهور أول رسالة باستخدام المحدد: {chat_container_locator}")
            WebDriverWait(driver, 45).until( # زيادة المهلة إلى 45 ثانية
                EC.presence_of_element_located(chat_container_locator)
            )
            logging.info("✅ تم العثور على أول رسالة، يفترض أن الشات قد تم تحميله.")
            # --- إضافة انتظار قصير إضافي للسماح بتحميل المزيد من المحتوى الأولي ---
            time.sleep(3)

            # --- الحلقة الرئيسية لقراءة الرسائل ---
            while True:
                try:
                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')

                    # --- تحديد عناصر الرسائل باستخدام المحدد المؤكد 'div.group' ---
                    message_elements = soup.find_all('div', class_='group')

                    logging.debug(f"🔍 تم العثور على {len(message_elements)} عنصر 'div.group' محتمل.")

                    new_messages_found_this_cycle = 0
                    for message in message_elements:
                        try:
                            # --- استخراج وقت الرسالة ---
                            time_span = message.find('span', class_='text-neutral') # محدد مؤكد
                            time_sent_str = time_span.text.strip() if time_span else "--:--"
                            # --- تنظيف الوقت (إزالة AM/PM) ---
                            time_sent_clean = re.sub(r'\s*(AM|PM)$', '', time_sent_str, flags=re.IGNORECASE).strip()
                            try:
                                # محاولة تحويل الوقت إلى صيغة HH:MM (24 ساعة)
                                parsed_time = datetime.strptime(time_sent_clean, '%H:%M')
                                time_sent = parsed_time.strftime('%H:%M')
                            except ValueError:
                                try:
                                     # محاولة صيغة I:MM (12 ساعة بدون AM/PM)
                                     parsed_time = datetime.strptime(time_sent_clean, '%I:%M')
                                     time_sent = parsed_time.strftime('%H:%M')
                                except ValueError:
                                     time_sent = "--:--" # العودة للقيمة الافتراضية عند الفشل

                            # --- استخراج اسم المستخدم ---
                            user_button = message.find('button', class_='inline font-bold') # محدد مؤكد
                            # قد يكون اسم المستخدم في النص الداخلي للزر أو في title
                            user_name = user_button.text.strip() if user_button else "Unknown"
                            if not user_name and user_button and user_button.has_attr('title'):
                                user_name = user_button['title'].strip() # محاولة الحصول عليه من الـ title

                            if user_name == "Unknown":
                                # قد يكون اسم المستخدم في span مختلف في بعض الحالات
                                user_span = message.find('span', class_='chat-entry-username') # محدد بديل محتمل
                                if user_span:
                                    user_name = user_span.text.strip()


                            # --- استخراج نص الرسالة ---
                            # البحث عن الـ div الذي يحتوي على class='break-words'
                            content_div = message.find('div', class_=lambda c: c and 'break-words' in c.split())

                            if not content_div:
                                # قد يكون المحتوى في مكان آخر أحيانًا، جرب span.font-normal
                                content_span = message.find('span', class_='font-normal')
                                if content_span:
                                    content_div = content_span # اعتبر هذا هو الحاوية للمعالجة التالية
                                else:
                                    logging.warning(f"⚠️ لم يتم العثور على حاوية المحتوى (break-words أو font-normal) للمستخدم {user_name}. تخطي.")
                                    # logging.debug(f"HTML للرسالة التي فشلت: {message}")
                                    continue

                            # --- التعامل مع الإيموجيات (استبدال الصور بنص ALT) ---
                            for img in content_div.find_all("img"):
                                if img.has_attr("alt"):
                                    alt_text = img['alt'].strip()
                                    # استبدال مع إضافة مسافات إذا لم تكن موجودة بالفعل
                                    img.replace_with(f" {alt_text} ")

                            # --- استخراج النص وتنظيفه ---
                            message_text = content_div.get_text(separator=' ', strip=True)

                            # --- إزالة الوقت واسم المستخدم المكرر في بداية النص ---
                            # إزالة الوقت أولاً (إذا كان موجوداً في البداية)
                            if time_sent_str != "--:--" and message_text.startswith(time_sent_str):
                                message_text = message_text[len(time_sent_str):].strip()

                            # إزالة اسم المستخدم والنقطتين (إذا كان موجوداً في البداية)
                            # جعل النمط أكثر مرونة ليشمل النقطتين أو لا
                            pattern = rf'^{re.escape(user_name)}\s*:?\s*'
                            message_text_cleaned = re.sub(pattern, '', message_text, count=1, flags=re.IGNORECASE).strip()

                            # --- التحقق من أن النص ليس فارغًا بعد التنظيف ---
                            if not message_text_cleaned:
                                logging.debug(f"رسالة فارغة بعد التنظيف للمستخدم {user_name}. النص الأصلي: '{message_text}'")
                                continue

                            system_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            # --- إنشاء معرف فريد للتحقق من التكرار ---
                            unique_id_part = message_text_cleaned[:50] # استخدام جزء من الرسالة المنظفة
                            minute_identifier = datetime.now().strftime("%Y%m%d%H%M") # المعرف الدقيق
                            unique_id = f"{minute_identifier}_{user_name}_{unique_id_part}"

                            # --- إضافة الرسالة إذا لم تتم معالجتها من قبل ---
                            if unique_id not in processed_messages:
                                from datetime import datetime as dt
                                msg_obj = ChatMessage(
                                    system_time=dt.strptime(system_time, "%Y-%m-%d %H:%M:%S"),
                                    time_sent=time_sent,
                                    username=user_name,
                                    message=message_text_cleaned
                                )
                                session.add(msg_obj)
                                session.commit()
                                processed_messages.add(unique_id)

                                new_messages_found_this_cycle += 1

                        except StaleElementReferenceException:
                            logging.warning(" عنصر قديم (StaleElementReferenceException)، سيتم تجاهله والمتابعة.")
                            continue # تجاهل هذا العنصر ومتابعة الحلقة
                        except Exception as e:
                            # تسجيل خطأ أكثر تفصيلاً للمعالجة الفردية
                            logging.error(f"⚠️ خطأ في معالجة رسالة فردية للمستخدم '{user_name}': {e}", exc_info=True)

                    if new_messages_found_this_cycle > 0:
                         logging.info(f"💬 تمت إضافة {new_messages_found_this_cycle} رسالة جديدة.")

                except KeyboardInterrupt:
                     raise # السماح بـ CTRL+C لإيقاف البرنامج
                except Exception as e:
                    logging.error(f"💥 خطأ في حلقة قراءة الرسائل الرئيسية: {e}", exc_info=True)
                    # قد تحتاج لإعادة تحميل الصفحة هنا إذا كان الخطأ جسيمًا ويتكرر
                    # logging.info("🔄 محاولة إعادة تحميل الصفحة...")
                    # driver.refresh()
                    # time.sleep(10) # انتظر بعد التحديث

                # --- الانتظار قبل الدورة التالية ---
                time.sleep(1.5) # تقليل التردد قليلاً (1.5 ثانية)

        except KeyboardInterrupt:
             logging.info("🛑 تم طلب الإيقاف (KeyboardInterrupt).")
             break # الخروج من حلقة إعادة المحاولة الخارجية
        except TimeoutException:
            logging.error(f"⏳ انتهت مهلة انتظار تحميل عنصر الشات المحدد ({chat_container_locator}). قد تكون الصفحة بطيئة، أو تغير تصميمها، أو هناك عائق.")
            # لا تحاول إعادة التحميل هنا، سيتم إغلاق المتصفح وإعادة المحاولة
        except Exception as e:
            logging.error(f"❌ فشل كبير في تشغيل Selenium أو الاتصال بالصفحة: {e}", exc_info=True)
        finally:
            if driver:
                logging.warning("🚦 إغلاق متصفح Selenium الحالي...")
                driver.quit()
                driver = None # تعيينه إلى None لإعادة المحاولة
            # لا تخرج من البرنامج هنا، انتظر لإعادة المحاولة
            if not isinstance(e, KeyboardInterrupt): # لا تنتظر إذا كان الإيقاف بسبب CTRL+C
                 logging.info("⏳ الانتظار 15 ثانية قبل محاولة إعادة تشغيل Selenium...")
                 time.sleep(15) # انتظر قبل إعادة المحاولة
            else:
                 break # اخرج من الحلقة إذا كان السبب هو KeyboardInterrupt

# --- تشغيل Selenium في خيط منفصل ---
thread = threading.Thread(target=start_selenium)
thread.daemon = True # يسمح بإيقاف البرنامج الرئيسي حتى لو كان الخيط لا يزال يعمل
thread.start()

# --- نقطة نهاية Flask لعرض الواجهة الأمامية ---
@app.route('/')
def index():
    # لا نمرر البيانات هنا مباشرة، سيتم جلبها بواسطة JavaScript
    return render_template('index.html')

# --- *** نقطة نهاية جديدة لصفحة سجل الرسائل *** ---
@app.route('/log')
def message_log():
    # يمكن تمرير الفلاتر كمعلمات URL إذا أردت
    # user_filter = request.args.get('user', '')
    # from_filter = request.args.get('from', '')
    # to_filter = request.args.get('to', '')
    # return render_template('log.html', user_filter=user_filter, ...)
    return render_template('log.html') # أبسط نسخة

# --- نقطة نهاية Flask للحصول على الرسائل *الجديدة* فقط ---
from sqlalchemy import desc

@app.route('/get_new_messages')
def get_new_messages():
    global last_sent_index
    # نحصل على آخر الرسائل حسب الترتيب
    new_msgs = session.query(ChatMessage).order_by(ChatMessage.id.desc()).limit(50).all()
    # نحولها إلى الشكل المناسب للواجهة الأمامية
    result = [
        [msg.system_time.strftime("%Y-%m-%d %H:%M:%S"), msg.time_sent, msg.username, msg.message]
        for msg in reversed(new_msgs)
    ]
    return jsonify(result)


# --- *** نقطة نهاية جديدة لجلب *كل* الرسائل (لصفحة السجل) *** ---
@app.route('/get_all_messages')
def get_all_messages():
    all_msgs = session.query(ChatMessage).all()
    return jsonify([[msg.system_time.strftime("%Y-%m-%d %H:%M:%S"), msg.time_sent, msg.username, msg.message] for msg in all_msgs])


# --- تشغيل تطبيق Flask ---
if __name__ == '__main__':
    # استخدم use_reloader=False أثناء الاختبار والتصحيح لتجنب تشغيل خيوط Selenium متعددة
    # بعد التأكد من عمل كل شيء، يمكنك إزالته إذا أردت إعادة التحميل التلقائي عند تغيير الكود
    logging.info("🚀 تشغيل خادم Flask...")
    app.run(debug=True, port=5050, host='0.0.0.0', use_reloader=False)

    # عند إيقاف خادم Flask (عادة بـ CTRL+C)، سيتم إيقاف خيط Selenium تلقائيًا لأنه daemon
    logging.info("🏁 تم إيقاف خادم Flask.")