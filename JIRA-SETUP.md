# JIRA setup — Marketplace board

ย้าย task tracking มา JIRA (สเปคลึกยังอยู่ที่ `SPEC.md` ใน git). ขั้นที่ต้องกดเองในเบราว์เซอร์ เรียงตามนี้.

## 1. สร้าง JIRA Cloud (ฟรี)
1. ไป https://www.atlassian.com/software/jira/free → สมัคร (ฟรี ≤10 users)
2. สร้าง site เช่น `taskeendev.atlassian.net`
3. Create project → **Jira Software** → **Kanban** (team-managed พอ) → ชื่อ **Marketplace**, key **MKT**
4. Statuses default = `To Do` / `In Progress` / `Done` — ใช้ตามนี้ ไม่ต้องแต่งเพิ่ม

## 2. Import งานจาก CSV
ไฟล์: `marketplace-jira-import.csv` (root repo นี้ — 6 epics + 40 stories)

1. ⚙️ (Settings มุมขวาบน) → **System** → **External System Import** → **CSV**
   *(ถ้าไม่เจอเมนูนี้ = ต้องเป็น Jira admin; team-managed project ใช้ Project settings → หรือ import ผ่าน site admin)*
2. อัปโหลด CSV → เลือก project **Marketplace (MKT)**
3. Map fields:
   | คอลัมน์ CSV | Jira field |
   |---|---|
   | Issue Type | Issue Type |
   | Summary | Summary |
   | Epic Name | Epic Name |
   | Epic Link | Epic Link |
   | Labels | Labels |
   | Status | Status |
   | Description | Description |
4. Import → ตรวจว่าได้ 6 epic + 40 story, story อยู่ใต้ epic ถูกตัว

> ถ้า wizard ไม่ยอม set Status ตอน import (บาง plan) → import แล้วค่อยลาก card ที่เป็นเฟสเสร็จ (P0/P1/P2/P3a) ไป Done ทีเดียว

## 3. เชื่อม GitHub ↔ JIRA
1. Apps → **Find new apps** → ติดตั้ง **GitHub for Jira** (ฟรี)
2. เชื่อม GitHub org **taskeendev** → เลือก repo `marketplace-*`
3. เปิดใช้ smart commits / branch linking

## 4. วิธีลิงก์งาน (ลด double-entry กับ GitHub issues)
- ตั้งชื่อ branch มี key: `feature/MKT-12-inventory-decrement`
- commit/PR ใส่ key ในข้อความ: `MKT-12 atomic decrement + ledger`
- JIRA จะโชว์ commit/PR/branch ใต้ ticket อัตโนมัติ → ไม่ต้องแปะมือ

## 5. Flow ต่อจากนี้ (เฟสใหม่ P3b+)
1. เขียนสเปคเฟสลง `SPEC.md` (source of truth)
2. เพิ่มแถวใน CSV เฉพาะ task เฟสนั้น → import เพิ่ม (หรือสร้าง ticket มือใน JIRA ก็ได้)
3. approve → code (feature-branch + PR อ้าง `MKT-xx`)

---
GitHub issues เดิม: คงไว้เป็น log ให้ PR อ้างอิง — ไม่ต้องซิงก์มือกับ JIRA
