# moph_api

โครง Python สำหรับแปลงงานส่ง API เดิมจาก PHP ให้มาใช้ config และฟังก์ชันกลางร่วมกัน

## โครงไฟล์

- `common/config.py` อ่านค่าตั้งค่าจาก `.env`
- `common/db.py` ต่อ SQL Server และ helper สำหรับ query/log
- `common/moph_client.py` ขอ token และส่ง API กลาง เช่น 506, EPI, DMHT, DT
- `jobs/send_506.py` งานส่งข้อมูล 506
- `jobs/send_epi.py` งานส่งข้อมูล EPI

## ตั้งค่า

คัดลอก `.env.example` เป็น `.env` แล้วใส่ค่าให้ครบ

ค่าที่ต้องใส่เอง:

- `DB_PASSWORD`
- `MOPH_TOKEN_USER`
- `MOPH_TOKEN_PASSWORD_HASH`

## ติดตั้ง

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## รันงาน

ส่ง 506 ของเมื่อวาน:

```bash
.venv/bin/python jobs/send_506.py
```

ส่ง 506 ระบุวันที่:

```bash
.venv/bin/python jobs/send_506.py --date 2026-06-15
```

ส่ง EPI ของวันนี้:

```bash
.venv/bin/python jobs/send_epi.py
```

ส่ง EPI ระบุวันที่:

```bash
.venv/bin/python jobs/send_epi.py --date 2026-03-26
```

## เพิ่มงาน API ใหม่

สร้างไฟล์ใหม่ใน `jobs/` แล้วเรียกใช้ตัวกลาง เช่น

```python
from common.moph_client import MophApiClient

client = MophApiClient()
result = client.send_dmht(payload)
```

ถ้าเป็น API ใหม่ที่ยังไม่มี method ให้เพิ่ม URL ใน `.env.example` และเพิ่ม method ใน `common/moph_client.py`
