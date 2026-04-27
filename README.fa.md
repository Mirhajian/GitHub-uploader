# 📤 ربات آپلود فایل از تلگرام به گیت‌هاب

این ربات تلگرام هر نوع فایلی را دریافت کرده و آن را مستقیماً از طریق GitHub Contents API در یک مخزن گیت‌هاب ذخیره می‌کند.

---

## امکانات

- **پشتیبانی از همه انواع فایل** — سند، عکس، ویدیو، صدا، ویس، استیکر، انیمیشن، ویدیو گرد
- **کنترل دسترسی** — لیست سفید کاربران مجاز تلگرام
- **مدیریت تداخل فایل** — بازنویسی یا نسخه‌بندی خودکار (`file_1.ext`، `file_2.ext`، …)
- **مسیر آپلود سفارشی** — دستور `/setpath` برای هر کاربر
- **پشتیبانی از فایل‌های بزرگ** — با سرور Bot API محلی تا ۲ گیگابایت
- **تلاش مجدد خودکار** — با تأخیر نمایی در صورت محدودیت نرخ گیت‌هاب
- **اطلاع‌رسانی به ادمین** — ارسال خطاها به کاربر ادمین تنظیم‌شده
- **لاگ فایل چرخشی** — ۱۰ مگابایت × ۵ نسخه پشتیبان

---

## ساختار پروژه

```
telegram-github-uploader/
├── bot/
│   ├── __init__.py
│   ├── __main__.py            ← نقطه ورود — با python -m bot اجرا کنید
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py        ← تمام تنظیمات از متغیرهای محیطی
│   │   └── logging_config.py  ← راه‌اندازی لاگر
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py        ← دستورات /start /help /setpath /clearpath /status
│   │   └── upload.py          ← هندلر اصلی آپلود فایل
│   └── services/
│       ├── __init__.py
│       ├── file_service.py    ← استخراج و دانلود فایل از تلگرام
│       └── github_service.py  ← ارتباط با GitHub Contents API
├── logs/                      ← ساخته می‌شود هنگام اجرا
├── .env                       ← اطلاعات محرمانه (هرگز کامیت نکنید)
├── .env.example               ← قالب — کپی کرده و پر کنید
├── .gitignore
├── requirements.txt
└── README.md
```

---

## راهنمای نصب و راه‌اندازی

### ۱. دریافت کد و نصب وابستگی‌ها

```bash
git clone https://github.com/mirhajian/GitHub-uploader.git
cd GitHub-uploader


python -m venv .venv
source .venv/bin/activate        # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt
```

### ۲. ساخت فایل تنظیمات

```bash
cp .env.example .env
```

سپس فایل `.env` را باز کرده و مقادیر را پر کنید (راهنمای هر مقدار در ادامه آمده است).

### ۳. اجرای ربات

```bash
python -m bot
```

---

## راهنمای دریافت مقادیر لازم

### 🤖 توکن ربات تلگرام (`TELEGRAM_BOT_TOKEN`)

۱. در تلگرام، [@BotFather](https://t.me/BotFather) را جستجو کرده و شروع کنید.
۲. دستور `/newbot` را ارسال کنید.
۳. یک نام برای ربات انتخاب کنید (مثال: `My File Uploader`).
۴. یک نام کاربری انتخاب کنید که به `bot` ختم شود (مثال: `myfileuploader_bot`).
۵. BotFather یک توکن مانند زیر به شما می‌دهد:

```
1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

این مقدار را در `.env` قرار دهید:

```
TELEGRAM_BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### 🔑 توکن گیت‌هاب (`GITHUB_TOKEN`)

این یک «Personal Access Token» (PAT) است که به ربات اجازه می‌دهد فایل در مخزن شما بنویسد.

۱. به [github.com](https://github.com) وارد شوید.
۲. از گوشه بالا-راست روی عکس پروفایل خود کلیک کنید → **Settings**.
۳. از منوی چپ به پایین اسکرول کنید → **Developer settings**.
۴. روی **Personal access tokens** کلیک کنید → **Tokens (classic)**.
۵. روی **Generate new token** → **Generate new token (classic)** کلیک کنید.
۶. یک نام توضیحی بنویسید (مثال: `telegram-uploader-bot`).
۷. در بخش **Expiration** یک زمان انقضا انتخاب کنید (یا `No expiration`).
۸. در بخش **Select scopes**، تیک **`repo`** را بزنید (تمام زیرمجموعه‌ها انتخاب می‌شوند).
۹. روی **Generate token** کلیک کنید.
۱۰. توکن را **همان لحظه** کپی کنید — بعد از بستن صفحه دیگر نمایش داده نمی‌شود.

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ **هشدار:** این توکن را در هیچ فایلی کامیت نکنید و با کسی به اشتراک نگذارید.

---

### 📁 اطلاعات مخزن گیت‌هاب

**`GITHUB_OWNER`** — نام کاربری یا سازمان گیت‌هاب شما.
برای پیدا کردن آن، به صفحه مخزن در گیت‌هاب بروید. در آدرس زیر:
`https://github.com/USERNAME/REPONAME`
بخش `USERNAME` همان `GITHUB_OWNER` است.

**`GITHUB_REPO`** — نام مخزن (بخش `REPONAME` در آدرس بالا).

**`GITHUB_BRANCH`** — نام شاخه‌ای که فایل‌ها در آن ذخیره می‌شوند (معمولاً `main` یا `master`).

```
GITHUB_OWNER=your_username
GITHUB_REPO=your_repo_name
GITHUB_BRANCH=main
```

> 💡 مخزن باید از قبل ساخته شده باشد. اگر ندارید، در [github.com/new](https://github.com/new) یکی بسازید.

---

### 👤 شناسه کاربری تلگرام (`ALLOWED_USER_IDS` و `ADMIN_USER_ID`)

برای پیدا کردن شناسه عددی خود در تلگرام:

۱. ربات [@userinfobot](https://t.me/userinfobot) را در تلگرام پیدا کنید.
۲. `/start` بزنید.
۳. شناسه عددی شما (مانند `123456789`) نمایش داده می‌شود.

```
ALLOWED_USER_IDS=123456789,987654321
ADMIN_USER_ID=123456789
```

> اگر `ALLOWED_USER_IDS` را خالی بگذارید، همه کاربران می‌توانند از ربات استفاده کنند.

---

## متغیرهای محیطی — جدول کامل

| متغیر | اجباری | پیش‌فرض | توضیح |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | توکن ربات از BotFather |
| `GITHUB_TOKEN` | ✅ | — | توکن دسترسی شخصی گیت‌هاب |
| `GITHUB_OWNER` | ✅ | — | نام کاربری یا سازمان گیت‌هاب |
| `GITHUB_REPO` | ✅ | — | نام مخزن |
| `GITHUB_BRANCH` | ❌ | `main` | شاخه هدف |
| `UPLOAD_BASE_PATH` | ❌ | `uploads` | پوشه ریشه در مخزن |
| `FILE_CONFLICT_STRATEGY` | ❌ | `version` | `overwrite` یا `version` |
| `ALLOWED_USER_IDS` | ❌ | *(همه)* | شناسه‌های مجاز با کاما جدا |
| `ADMIN_USER_ID` | ❌ | *(هیچ)* | شناسه ادمین برای دریافت خطاها |
| `TELEGRAM_LOCAL_SERVER_URL` | ❌ | *(هیچ)* | آدرس سرور Bot API محلی |
| `LOG_LEVEL` | ❌ | `INFO` | سطح لاگ: `DEBUG`، `INFO`، `WARNING` |
| `LOG_FILE` | ❌ | `logs/bot.log` | مسیر فایل لاگ |

---

## دستورات ربات

| دستور | توضیح |
|---|---|
| `/start` | پیام خوش‌آمدگویی با دکمه‌های اینلاین |
| `/help` | راهنمای کامل |
| `/setpath <پوشه>` | تنظیم زیرپوشه سفارشی برای آپلود |
| `/clearpath` | بازگشت به مسیر پیش‌فرض (بر اساس تاریخ) |
| `/status` | نمایش تنظیمات فعلی |

---

## محدودیت حجم فایل

| حالت | حداکثر آپلود | حداکثر دانلود |
|---|---|---|
| سرورهای رسمی تلگرام | ۵۰ مگابایت | ۲۰ مگابایت |
| سرور Bot API محلی | ۲۰۰۰ مگابایت | ۲۰۰۰ مگابایت |
| حد سخت GitHub Contents API | **۱۰۰ مگابایت** | — |

برای فایل‌های بیش از ۱۰۰ مگابایت از [Git LFS](https://git-lfs.com) یا یک سرویس ذخیره‌سازی ابری (مانند S3 یا Cloudflare R2) استفاده کنید.

---

## فرمت مسیر آپلود

```
{UPLOAD_BASE_PATH}/{پوشه}/{نام_فایل}

# پیش‌فرض (بدون /setpath):
uploads/2024-01-15/photo.jpg

# با /setpath پروژه/تصاویر:
uploads/پروژه/تصاویر/photo.jpg
```

---
