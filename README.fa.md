# 📤 ربات آپلود فایل از تلگرام به گیت‌هاب

> **چرا این ابزار ساخته شد؟** — ۸ اردیبهشت ۱۴۰۵
>
> در ایران، قطعی مکرر اینترنت و هزینه بالای VPN دسترسی به فایل‌های شخصی را سخت می‌کند.
> گیت‌هاب یکی از معدود سرویس‌هایی است که اغلب بدون VPN در دسترس است.
> این ربات به شما امکان می‌دهد فایل‌های سنگین درون تلگرام را (ویدیو، صدا، سند و …)
> مستقیماً در یک مخزن گیت‌هاب ذخیره کنید تا هر زمان، بدون VPN، از گیت‌هاب دانلود کنید.
>
> تنها نیاز: یک VPS ساعتی ارزان با حداقل ۱۰ گیگابایت SSD — و همین ربات.

---

## امکانات

- **پشتیبانی از همه انواع فایل** — سند، عکس، ویدیو، ویس، استیکر، انیمیشن، ویدیو مسیج
- **مسیریابی هوشمند:** فایل‌های زیر ۵۰ مگابایت از طریق Contents API و فایل‌های بزرگ‌تر از طریق **Git LFS** ذخیره می‌شوند
- **پاکسازی خودکار** — وقتی حجم مخزن از آستانه تعریف‌شده بگذرد، قدیمی‌ترین فایل‌ها حذف می‌شوند (مناسب VPS با SSD کوچک)
- **کنترل دسترسی** — لیست سفید کاربران مجاز تلگرام
- **مدیریت تداخل فایل** — بازنویسی یا نسخه‌بندی خودکار (`file_1.ext`، `file_2.ext`، …)
- **مسیر آپلود سفارشی** — دستور `/setpath` برای هر کاربر
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
│       └── github_service.py  ← ارتباط با GitHub Contents API و Git LFS
├── logs/                      ← ساخته می‌شود هنگام اجرا
├── .env                       ← اطلاعات محرمانه (هرگز کامیت نکنید)
├── .env.example               ← قالب — کپی کرده و پر کنید
├── .gitignore
├── requirements.txt
└── README.fa.md
```

---

## راهنمای نصب و راه‌اندازی

### ⚡ نصب یک‌خطی (سریع‌ترین روش)

اگر می‌خواهید بدون کلون‌کردن دستی، همه چیز را در یک مرحله انجام دهید، کافی است این دستور را در ترمینال VPS اجرا کنید:

```bash
bash <(curl -sL https://raw.githubusercontent.com/mirhajian/GitHub-uploader/main/setup.sh)
```

این دستور به‌صورت خودکار:
1. `apt update` را اجرا می‌کند و بسته‌های لازم را نصب می‌کند
2. مخزن را کلون می‌کند
3. محیط مجازی Python می‌سازد و وابستگی‌ها را نصب می‌کند
4. فایل `.env` را با راهنمایی گام‌به‌گام می‌سازد
5. Git LFS را (در صورت نیاز) فعال می‌کند
6. سرویس `systemd` را (در صورت تمایل) نصب می‌کند

> **پیش‌نیاز:** دسترسی `sudo` روی VPS و اتصال اینترنت.

---

### 🛠️ نصب دستی (روش کلاسیک)

#### ۱. دریافت کد و نصب وابستگی‌ها

```bash
sudo apt update
sudo apt install build-essential python3 python3-dev python3-venv python3-pip git git-lfs curl -y

git clone https://github.com/mirhajian/GitHub-uploader.git
cd GitHub-uploader

python3 -m venv .venv
source .venv/bin/activate        # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt
```

#### ۲. ساخت فایل تنظیمات

```bash
cp .env.example .env
nano .env   # یا با هر ویرایشگر دلخواه باز کنید
```

مقادیر لازم را پر کنید (راهنمای هر مقدار در ادامه آمده است).

#### ۳. فعال‌سازی Git LFS در مخزن گیت‌هاب (برای فایل‌های بزرگ)

اگر می‌خواهید فایل‌های بزرگ‌تر از ۵۰ مگابایت هم ذخیره شوند، باید یک‌بار Git LFS را در مخزن خود راه‌اندازی کنید:

```bash
# روی کامپیوتر شخصی خود (نه VPS) اجرا کنید:
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

git lfs install
git lfs track "*"          # همه انواع فایل را تحت LFS قرار می‌دهد
git add .gitattributes
git commit -m "chore: enable Git LFS for all files"
git push
```

> اگر Git LFS روی کامپیوتر شما نصب نیست:
> - Ubuntu/Debian: `sudo apt install git-lfs`
> - macOS: `brew install git-lfs`
> - ویندوز: از [git-lfs.com](https://git-lfs.com) دانلود کنید

> 💡 اگر فقط فایل‌های زیر ۵۰ مگابایت آپلود می‌کنید، این مرحله اختیاری است.

#### ۴. اجرای ربات

```bash
screen -S tel2github   # اجازه دهید تا ربات در بکگراند اجرا شود
source .venv/bin/activate
python -m bot
```

برای جدا شدن از screen بدون متوقف کردن ربات: `Ctrl+A` سپس `D`

---

## راهنمای دریافت مقادیر لازم

### 🔐 شناسه و هش API تلگرام (`TELEGRAM_API_ID` و `TELEGRAM_API_HASH`)

این مقادیر برای Pyrogram (اتصال MTProto مستقیم) الزامی هستند.

۱. به [my.telegram.org](https://my.telegram.org) بروید و با شماره تلفن تلگرام خود وارد شوید.

۲. روی **"API development tools"** کلیک کنید.

۳. یک فرم کوچک نمایش داده می‌شود — نام و توضیح کوتاهی برای اپلیکیشن خود بنویسید (مثلاً `my-bot`).

۴. روی **"Create application"** کلیک کنید.

۵. مقادیر `App api_id` (عدد) و `App api_hash` (رشته) را کپی کنید.

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
```

> ⚠️ این مقادیر را با کسی به اشتراک نگذارید و در فایل‌های عمومی کامیت نکنید.

---

### 🤖 توکن ربات تلگرام (`TELEGRAM_BOT_TOKEN`)

۱. در تلگرام، [@BotFather](https://t.me/BotFather) را جستجو کرده و شروع کنید.

۲. دستور `/newbot` را ارسال کنید.

۳. یک نام برای ربات انتخاب کنید (مثال: `My File Uploader`).

۴. یک نام کاربری انتخاب کنید که به `bot` ختم شود (مثال: `myfileuploader_bot`).

۵. BotFather یک توکن مانند زیر به شما می‌دهد:

```
TELEGRAM_BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### 🔑 توکن گیت‌هاب (`GITHUB_TOKEN`)

این یک «Personal Access Token» (PAT) است که به ربات اجازه می‌دهد فایل در مخزن شما بنویسد.

۱. به github.com وارد شوید.

۲. از گوشه بالا-راست روی عکس پروفایل خود کلیک کنید ← Settings.

۳. از منوی چپ به پایین اسکرول کنید ← Developer settings.

۴. روی Personal access tokens کلیک کنید ← Tokens (classic).

۵. روی Generate new token ← Generate new token (classic) کلیک کنید.

۶. یک نام توضیحی بنویسید (مثال: `telegram-uploader-bot`).

۷. در بخش Expiration یک زمان انقضا انتخاب کنید (یا `No expiration`).

۸. در بخش **Select scopes**، تیک **`repo`** را بزنید.

۹. روی Generate token کلیک کنید.

۱۰. توکن را همان لحظه کپی کنید — بعد از بستن صفحه دیگر نمایش داده نمی‌شود.

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ این توکن را در هیچ فایلی کامیت نکنید و با کسی به اشتراک نگذارید.

---

### 📁 اطلاعات مخزن گیت‌هاب

**`GITHUB_OWNER`** — نام کاربری گیت‌هاب شما.
**`GITHUB_REPO`** — نام مخزن.
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
| `TELEGRAM_API_ID` | ✅ | — | شناسه API از my.telegram.org |
| `TELEGRAM_API_HASH` | ✅ | — | هش API از my.telegram.org |
| `GITHUB_TOKEN` | ✅ | — | توکن دسترسی شخصی گیت‌هاب |
| `GITHUB_OWNER` | ✅ | — | نام کاربری یا سازمان گیت‌هاب |
| `GITHUB_REPO` | ✅ | — | نام مخزن |
| `GITHUB_BRANCH` | ❌ | `main` | شاخه هدف |
| `UPLOAD_BASE_PATH` | ❌ | `uploads` | پوشه ریشه در مخزن |
| `FILE_CONFLICT_STRATEGY` | ❌ | `version` | `overwrite` یا `version` |
| `LFS_THRESHOLD_MB` | ❌ | `50` | فایل‌های بزرگ‌تر از این مقدار (مگابایت) از طریق Git LFS آپلود می‌شوند |
| `CLEANUP_ENABLED` | ❌ | `false` | پاکسازی خودکار فایل‌های قدیمی را فعال می‌کند |
| `CLEANUP_MAX_REPO_MB` | ❌ | `800` | آستانه حجم مخزن (مگابایت) برای شروع پاکسازی |
| `CLEANUP_KEEP_LATEST` | ❌ | `10` | تعداد جدیدترین فایل‌هایی که هیچ‌گاه حذف نمی‌شوند |
| `ALLOWED_USER_IDS` | ❌ | *(همه)* | شناسه‌های مجاز با کاما جدا |
| `ADMIN_USER_ID` | ❌ | *(هیچ)* | شناسه ادمین برای دریافت خطاها |
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

## محدودیت حجم فایل و مسیریابی هوشمند

| لایه | حداکثر |
|---|---|
| Pyrogram / MTProto (دانلود از تلگرام) | **۲۰۰۰ مگابایت** |
| GitHub Contents API (فایل‌های زیر ۵۰ مگابایت) | **۱۰۰ مگابایت** |
| Git LFS (فایل‌های بزرگ‌تر از ۵۰ مگابایت) | **۲ گیگابایت** (در حساب رایگان) |

ربات به صورت خودکار تصمیم می‌گیرد:
- فایل‌های کوچک‌تر از `LFS_THRESHOLD_MB` (پیش‌فرض ۵۰ مگابایت) → **Contents API**
- فایل‌های بزرگ‌تر → **Git LFS**

---

## پاکسازی خودکار (مناسب VPS ارزان)

برای VPS‌هایی با SSD کوچک (مثلاً ۱۰ گیگابایت)، می‌توانید پاکسازی خودکار را فعال کنید.
وقتی حجم کل فایل‌های آپلودشده از `CLEANUP_MAX_REPO_MB` بگذرد، ربات قدیمی‌ترین فایل‌ها را
حذف می‌کند و `CLEANUP_KEEP_LATEST` جدیدترین فایل را همیشه نگه می‌دارد.

```
CLEANUP_ENABLED=true
CLEANUP_MAX_REPO_MB=800    # شروع پاکسازی وقتی مخزن از ۸۰۰ مگابایت گذشت
CLEANUP_KEEP_LATEST=10     # ۱۰ فایل آخر هیچ‌وقت حذف نمی‌شوند
```

---

## فرمت مسیر آپلود

```
{UPLOAD_BASE_PATH}/{پوشه}/{نام_فایل}

# پیش‌فرض (بدون /setpath):
uploads/2024-01-15/photo.jpg

# با /setpath پروژه/تصاویر:
uploads/پروژه/تصاویر/photo.jpg
```
