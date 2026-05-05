# HAPPYTAIL Discord Bot

Discord bot ของ HAPPYTAIL — auto-alert ตารางไลฟ์ + ตารางงาน
ดึงข้อมูลจาก Google Sheets ตรงๆ ผ่าน Service Account

---

## ฟีเจอร์

### Auto-notify (โพสต์ลง channel ที่ตั้งไว้ใน `.env`)
| เวลา | สิ่งที่โพสต์ |
|---|---|
| `12:00` ทุกวัน | งานวันนี้ + งานพรุ่งนี้ |
| `18:00` ทุกวัน | ตารางไลฟ์ของวันนั้น |

> เวลาทั้งหมดใช้ timezone `Asia/Bangkok` (ปรับได้ใน `.env`)
> ไม่มี slash command — บอทแค่ส่งแจ้งเตือนเข้า channel เดียวเท่านั้น

---

## โครงสร้างไฟล์

```
discord-bot/
├── bot.py              ← main entrypoint
├── sheets_client.py    ← wrapper Google Sheets API
├── scheduler.py        ← cron jobs auto-notify
├── formatter.py        ← format Discord embed
├── requirements.txt
├── .env.example        ← template env (ห้าม commit .env จริง)
├── .gitignore
└── credentials.json    ← service account key (พี่นัทต้องดาวน์โหลดมาวางเอง)
```

---

## Setup ทีละขั้น

### 1. ติดตั้ง Python dependencies

เปิด PowerShell ที่ `D:\NIA OS\discord-bot\` แล้วรัน:

```powershell
cd "D:\NIA OS\discord-bot"
& "C:\Users\AORUS\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> ถ้าไม่อยากใช้ venv ก็ `pip install -r requirements.txt` ตรงๆ ได้เลย

---

### 2. Discord Bot + Channel

> Bot Token + Channel ID พี่นัทเตรียมไว้แล้วในขั้นตอนก่อนหน้า ถ้ายังไม่มีให้กลับไปทำ:
> 1. https://discord.com/developers/applications → New Application → Bot → Reset Token
> 2. Invite bot เข้า HAPPYTAIL server (Permissions: Send Messages + Embed Links)
> 3. Right-click channel `schedule-alerts` → Copy Channel ID (ต้องเปิด Developer Mode)

---

### 3. สร้าง Google Cloud Project + Service Account

#### 3.1 สร้าง project + เปิด Sheets API
1. เข้า https://console.cloud.google.com/
2. สร้าง project ใหม่ (เช่น `happytail-bot`)
3. เมนู **APIs & Services → Library** → ค้น **Google Sheets API** → **Enable**

#### 3.2 สร้าง Service Account
1. **APIs & Services → Credentials → Create Credentials → Service Account**
2. ตั้งชื่อ (เช่น `happytail-bot-reader`) → **Create and Continue**
3. Role ใส่ **Viewer** (หรือเว้นไว้ก็ได้ เพราะ scope จำกัดผ่าน Sheets share อยู่แล้ว) → **Done**
4. คลิก service account ที่เพิ่งสร้าง → แท็บ **Keys → Add Key → Create New Key → JSON**
5. ไฟล์ JSON จะดาวน์โหลดมา → **rename เป็น `credentials.json`** → ย้ายไปไว้ที่ `D:\NIA OS\discord-bot\`

#### 3.3 Share Google Sheet ให้ service account
- เปิดไฟล์ JSON หา field `client_email` (เช่น `happytail-bot-reader@happytail-bot.iam.gserviceaccount.com`)
- เปิด Sheet ตารางไลฟ์ (`1jAviWHXUQzXavwU-DVPE21wtCCE0YJCSjcOVrHyk5go`) → **Share** → ใส่ email → permission **Viewer**
- เปิด Sheet HAPPYTAIL Schedule (`1yhhQRorLer_nx7QxLdLl769ZJIXXVUa58Sd_ia4t2r0`) → ทำเหมือนกัน

---

### 4. ตั้งค่า `.env`

```powershell
copy .env.example .env
notepad .env
```

แก้ค่าตามนี้:

```
BOT_TOKEN=<token จากขั้น 2>
CHANNEL_ID=<channel id ของ #schedule-alerts>
SHEET_LIVE_ID=1jAviWHXUQzXavwU-DVPE21wtCCE0YJCSjcOVrHyk5go
SHEET_EVENT_ID=1yhhQRorLer_nx7QxLdLl769ZJIXXVUa58Sd_ia4t2r0
GOOGLE_CREDENTIALS_PATH=./credentials.json
TIMEZONE=Asia/Bangkok
NOTIFY_LIVE_TIME=18:00
NOTIFY_EVENT_TIME=12:00
```

---

### 5. รันบอท

```powershell
cd "D:\NIA OS\discord-bot"
& "C:\Users\AORUS\AppData\Local\Programs\Python\Python313\python.exe" bot.py
```

ถ้า login สำเร็จจะเห็น log:
```
Logged in as HAPPYTAIL Bot (id=...)
Scheduler started — live notify 18:00, event notify 12:00
```

---

## Deploy แนะนำ

| Option | ข้อดี | ข้อเสีย |
|---|---|---|
| **รันบนเครื่องพี่นัทตลอดเวลา** | ฟรี, debug ง่าย | ปิดเครื่อง = บอทตาย |
| **Windows Task Scheduler** (autostart ตอน login) | ฟรี, หลัง reboot ก็มาเอง | ยังต้องเปิดเครื่อง |
| **Raspberry Pi / มินิ-PC ที่บ้าน** | เปิดตลอด ค่าไฟน้อย | ต้องมี hardware |
| **VPS** (เช่น DigitalOcean $4/mo, Vultr, Hetzner) | uptime สูง | เสียเงินรายเดือน |
| **Free tier**: Oracle Cloud Free Tier | ฟรี, สเปคพอ | setup ยุ่ง, account อาจถูกล็อก |

**แนะนำ:** เริ่มจากรันบนเครื่องตัวเองก่อนทดสอบ 1-2 สัปดาห์ ถ้าใช้จริงค่อยย้ายไป VPS เล็กๆ ($4-5/เดือน) หรือ mini-PC

ถ้ารันบนเครื่อง Windows ตลอด แนะนำใช้ **Task Scheduler** + script `.bat`:

`run_bot.bat`:
```bat
@echo off
cd /d "D:\NIA OS\discord-bot"
"C:\Users\AORUS\AppData\Local\Programs\Python\Python313\python.exe" bot.py
```

ใน Task Scheduler ตั้ง trigger = `At log on` + restart on failure

---

## การ Debug

### Bot ไม่ขึ้น online
- เช็ค Log ว่ามี error อะไร — ส่วนใหญ่จะเป็น token ผิด หรือ `.env` หาไม่เจอ

### Auto-notify ไม่ทำงาน
- เช็คว่า `CHANNEL_ID` ถูกต้อง
- เช็คว่าบอทมีสิทธิ์ Send Messages + Embed Links ใน channel นั้น
- เช็ค timezone ใน `.env` (default `Asia/Bangkok`)
- เช็ค log ตอน startup ว่า `Scheduler started` ขึ้นรึยัง

### Auto-notify ขึ้น แต่ไม่มีข้อมูล
- เช็คว่า service account email ถูก share เข้า Sheet ครบทั้ง 2 ไฟล์หรือยัง
- เช็คว่า tab ของเดือนปัจจุบันมีอยู่ใน Sheet ตารางไลฟ์ไหม (สคริปต์ match ชื่อเดือนแบบ substring เช่น "พ.ค." / "May" / "พฤษภาคม")
- เช็ค log จะมี HttpError บอกสาเหตุถ้า API ผิด

---

## TODO ให้พี่นัทตัดสินใจ

- [ ] **ทดสอบ tab name matching จริง** — สคริปต์ใช้ substring match (`"พ.ค."` ใน `"พ.ค. 69"`) ถ้า sheet ใช้ชื่อแปลกๆ เช่น `"05/2025"` จะหาไม่เจอ ให้ User บอก IT จะปรับ regex
- [ ] **เปลี่ยน embed color** — ตอนนี้ใช้ pastel pink `#FFB6C1` ถ้า HAPPYTAIL มีสีแบรนด์จริง บอก IT
- [ ] **เพิ่ม @mention** — ถ้าอยากให้ auto-notify ping role เช่น `@ชาวหมู่บ้าน` หรือ role พิเศษ บอก IT ค่อย add
- [ ] **Format วันที่ที่ display** — ตอนนี้ใช้ พ.ศ. (เช่น "5 พ.ค. 2569") ถ้าอยาก ค.ศ. แทน บอก IT
