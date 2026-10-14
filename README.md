# منصة إدارة حسابات WhatsApp Web المتعددة | FastAPI & Playwright

نظام متكامل واحترافي لإدارة حسابات **WhatsApp Web** المتعددة في وقت واحد، مع حفظ الجلسات الدائم (`Session Persistence`) وتوفير واجهة تحكم ويب حديثة و **RESTful API** للتحكم الكامل.

---

## 🌟 الميزات الرئيسية

1. **إدارة حسابات متعددة في نفس الوقت**:
   - تشغيل عدة حسابات واتساب مستقلة تماماً داخل متصفحات معزولة في الخلفية.
2. **حفظ الجلسات التلقائي (Session Persistence)**:
   - يتم تخزين ملفات تعريف الارتباط وبيانات الدخول داخل مجلد `data/sessions/{session_id}`.
   - بمجرد مسح رمز QR لمرة واحدة، يبقى الحساب متصلاً حتى بعد إعادة تشغيل السيرفر.
3. **لوحة تحكم ويب عصرية (Web Dashboard)**:
   - تدعم اللغة العربية بالكامل (RTL) مع تصميم Dark Mode جذاب.
   - عرض حالة الحسابات لحظياً (متصل، مسح QR، متوقف، تسجيل الدخول).
   - نافذة تفاعلية لمسح رمز QR مع التحديث التلقائي.
   - ميزة التقاط شاشة حية (Live Screenshot) لمتابعة ما يظهر في واتساب ويب.
   - واجهة إرسال رسائل فردية ورسائل جماعية (Bulk Messaging).
4. **REST API متكامل وسريع (FastAPI)**:
   - توثيق تفاعلي مدمج عبر **Swagger UI** على الرابط: `http://localhost:8000/docs`.

---

## 🚀 طريقة التشغيل

### 1. تثبيت المتطلبات (تم تثبيتها مسبقاً)
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. بدء تشغيل الخادم
عبر ملف التشغيل السريع:
```bash
run.bat
```
أو عبر سطر الأوامر:
```bash
py -m uvicorn main:app --host 0.0.0.0 --port 8000
```

افتح المتصفح على:
- **لوحة التحكم**: [http://localhost:8000](http://localhost:8000)
- **توثيق الـ API (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🚆 خطوات النشر على GitHub و Railway

### 1. الرفع على GitHub:
```bash
git add .
git commit -m "Initial commit for WhatsApp Multi-Account Manager API"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```

### 2. النشر على Railway (بخطوات بسيطة):
1. ادخل إلى [Railway.app](https://railway.app) وسجّل الدخول بحساب GitHub.
2. اضغط على **New Project** واختر **Deploy from GitHub repo**.
3. اختر المستودع الخاص بك. سيكتشف Railway ملف `Dockerfile` تلقائياً ويبدأ بالبناء فوراً.
4. **هام جداً لحفظ الجلسات (Volume):**
   - داخل إعدادات الخدمة على Railway، اذهب إلى تبويب **Volumes**.
   - اضغط على **Add Volume** واجعل المسار (Mount Path):
     `/app/data`
   - هذا يضمن بقاء جميع جلسات الواتساب وحساباتك مسجلة الدخول حتى لو قمت بإعادة تشغيل أو تحديث السيرفر!
5. قم بتوليد رابط عام (Public Domain) من تبويب **Settings** > **Generate Domain** للوصول للموقع عبر الإنترنت.

---

## 📡 دليل الـ REST API

### 1. عرض جميع الحسابات
```http
GET /api/sessions
```

### 2. إنشاء حساب جديد
```http
POST /api/sessions
Content-Type: application/json

{
  "session_id": "sales_01",
  "name": "حساب المبيعات",
  "description": "مخصص للمبيعات والاستفسارات"
}
```

### 3. تشغيل الجلسة (لبدء المتصفح ومسح QR)
```http
POST /api/sessions/{session_id}/start
```

### 4. استرجاع رمز QR
```http
GET /api/sessions/{session_id}/qr?format=json
```
- يمكنك أيضاً الحصول على الصورة مباشرة كملف PNG عبر: `format=image`

### 5. إرسال رسالة فردية
```http
POST /api/sessions/{session_id}/send-message
Content-Type: application/json

{
  "phone": "966501234567",
  "message": "مرحباً بك! هذه رسالة آلية عبر الـ API."
}
```

### 6. إرسال رسائل جماعية (مع فاصل زمني لحماية الحساب)
```http
POST /api/sessions/{session_id}/send-bulk
Content-Type: application/json

{
  "phones": ["966501111111", "966502222222", "964770000000"],
  "message": "عرض خاص بمناسبة نهاية الأسبوع!",
  "delay_seconds": 3.5
}
```

### 7. التقاط صورة شاشة حية لشاشة واتساب ويب
```http
GET /api/sessions/{session_id}/screenshot
```

### 8. إيقاف الجلسة مؤقتاً (مع الحفاظ على تسجيل الدخول)
```http
POST /api/sessions/{session_id}/stop
```

### 9. حذف الحساب ومسح بيانات جلسته
```http
DELETE /api/sessions/{session_id}
```

---

## 💻 أمثلة استدعاء برمجية

### بايثون (Python Requests)
```python
import requests

# إرسال رسالة
url = "http://localhost:8000/api/sessions/sales_01/send-message"
payload = {
    "phone": "966501234567",
    "message": "أهلاً بك، تم تأكيد طلبك بنجاح!"
}
response = requests.post(url, json=payload)
print(response.json())
```

### cURL
```bash
curl -X POST "http://localhost:8000/api/sessions/sales_01/send-message" \
     -H "Content-Type: application/json" \
     -d '{"phone": "966501234567", "message": "تجربة إرسال عبر الـ API"}'
```

---

## 📁 هيكلية المشروع

```
c:\AllProject\whatsapp\
├── app/
│   ├── config.py             # إعدادات النظام ومسارات التخزين
│   ├── models.py             # نماذج البيانات (Pydantic Schemas)
│   ├── whatsapp_manager.py   # مدير الجلسات المعزولة عبر Playwright
│   ├── routers/
│   │   ├── sessions.py       # مسارات إدارة الحسابات والـ QR
│   │   └── messages.py       # مسارات إرسال الرسائل
│   └── static/               # لوحة التحكم الأمامية (HTML/CSS/JS)
├── data/
│   ├── sessions/             # مجلد تخزين بيانات المتصفح والجلسات
│   └── sessions.json         # سجل بيانات الحسابات
├── main.py                   # نقطة تشغيل تطبيق FastAPI
├── requirements.txt          # مكتبات بايثون المطلوبة
└── run.bat                   # ملف تشغيل السيرفر بنقرة واحدة
```
