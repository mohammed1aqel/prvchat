from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime
import time
import threading

# إعداد الـ WebDriver
driver = None

# قائمة لتخزين الرسائل
messages_data = []
processed_messages = set()  # لتخزين الرسائل المعالجة مسبقًا

# دالة لتشغيل سكربت Selenium في الخلفية
def start_selenium():
    global driver
    if driver is None:
        driver = webdriver.Chrome()  # تأكد من أن كروم درايفر موجود
        driver.get("https://kick.com/popout/maherco/chat")  # رابط الشات الخاص بالقناة

        time.sleep(5)

        try:
            while True:
                # استخراج جميع الرسائل
                messages = driver.find_elements(By.XPATH, "//div[@class='group relative px-2 lg:px-3']")

                for message in messages:
                    try:
                        # استخراج اسم المستخدم
                        user_name = message.find_element(By.XPATH, ".//button[@class='inline font-bold']").text

                        # استخراج وقت الرسالة
                        time_sent = message.find_element(By.XPATH, ".//span[contains(@class, 'text-neutral') and contains(@class, 'pr-1') and contains(@class, 'font-semibold')]").text

                        # استخراج نص الرسالة
                        message_text = message.find_element(By.XPATH, ".//span[@class='font-normal leading-[1.55]']").text

                        # إضافة الإيموجيات التي قد تكون ضمن صورة (img)
                        emojis = message.find_elements(By.XPATH, ".//img")
                        for emoji in emojis:
                            emoji_alt = emoji.get_attribute('alt')  # بعض الإيموجيات قد تحتوي على alt text
                            if emoji_alt:
                                message_text += f" {emoji_alt}"

                        # إضافة الوقت الفعلي للنظام
                        system_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        # إنشاء معرف فريد للرسالة (يمكن أن يكون النص + الوقت)
                        message_id = f"{time_sent}_{message_text}"

                        # تحقق مما إذا كانت الرسالة قد تمت معالجتها من قبل
                        if message_id not in processed_messages:
                            # إضافة البيانات إلى القائمة
                            messages_data.append([system_time, time_sent, user_name, message_text])

                            # إضافة معرف الرسالة إلى مجموعة المعرفات المعالجة
                            processed_messages.add(message_id)

                    except Exception as e:
                        print(f"مشكلة في استخراج الرسالة: {e}")

                time.sleep(2)  # تأخير بين كل دورة لاستخراج الرسائل الجديدة

        except KeyboardInterrupt:
            driver.quit()
            print("تم إيقاف متصفح كروم.")

# بدء سكربت Selenium في خيط منفصل
thread = threading.Thread(target=start_selenium)
thread.daemon = True  # جعل الخيط يعمل في الخلفية
thread.start()

# بدء التطبيق Flask
from flask import Flask, render_template, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', messages_data=messages_data)

@app.route('/get_new_messages')
def get_new_messages():
    # هنا سنقوم بإرجاع الرسائل في صيغة JSON
    return jsonify(messages_data)

if __name__ == '__main__':
    app.run(debug=True)
