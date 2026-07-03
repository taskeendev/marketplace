# STATUS — marketplace (อ่านไฟล์นี้ก่อนเริ่มทุก session)

> จุดเดียวที่บอกว่า "อยู่ตรงไหน + ทำอะไรต่อ" — อัปเดตทุกครั้งที่ปิด task
> Source of truth ลึก = [SPEC.md](./SPEC.md) · tracker = JIRA project **MAR** (@devtaskeen.atlassian.net, ผ่าน Atlassian MCP)

## ตอนนี้อยู่ตรงไหน (2026-07-03)
- **เสร็จ:** P0 · P1 · P2 · P3 (a/b/c) · **P4a-T1..T4** — T4 (MAR-48): Kong `/api/agent` (gateway#8) + compose agent+postgres-agent (deploy#10) + **smoke ครบ 13/13 สด** (step 13: Hermes ตอบราคาจริง/ปิดแล้วเงียบ, webhook เซ็น HMAC) + Hermes search scope ตามร้าน (บั๊ก HIGH จาก review — catalog#15 +shopId filter, agent#4)
- deploy note: JVM ทั้ง 6 cap `-Xmx256m` + Kong 1 worker — Docker VM 3.8GB OOM ตอน 7 JVM cold start (auth exit 137); run.sh guard ตัวแปร .env ใหม่
- **ถัดไป → P4a-T5** [FE] web: seller Hermes toggle (GET/POST /api/agent/config) + ป้าย 🤖 บนข้อความ `hermes` + i18n (MAR-49) — ปิดเฟส P4a
- แล้วค่อย spec-sync drift/quality อื่นๆ

## ค้างอยู่ / จำไว้ (จาก spec audit 2026-07-02)
- ✅ **tech-debt เคลียร์ครบ 13/13 (2026-07-03)**: C1 C2 SD1 SD2 SD8 D1 D5 OD1 SDc1 C3 CD1 O1 + MAR-74 (Origin allowlist) — ทุกใบมีเทสตาม KPI + PR merged + MAR-xx Done. เหลือ debt ที่**เลื่อนโดยตั้งใจ**: D4/I1/CMN1 (เฟส Ops) · D6 (e2e FE) · SD6/SD7 (ติด Meta จริง)
- ✅ auth bypass MAR-72 (verified live) · ✅ ordering fix ใน T3
- **spec-sync รอบถัดไป (ยังไม่ทำ):** drift/quality in-place — logout(cookie/204) · search=ILIKE ไม่ใช่ full-text · shops/{slug} products ว่าง · cart error contract · simulate-inbound เปิด public (ควร gate SELLER)
- เฟส **Ops (สุดท้าย, เคาะแล้ว — ห้ามดึงมาก่อน)**: deploy จริง + CI/CD + Prometheus/Grafana — ยังไม่เขียนลง SPEC.md เป็นเฟส · ขยาย P5 (cancel/refund/address/รูป upload)
- รายการเต็ม audit: workflow `spec-vs-reality-audit` (กลุ่ม A แก้ SPEC เดิม · B เติมก่อน build · C เฟสใหม่)

## คำสั่งที่ใช้บ่อย
```bash
# test ต่อ service (Testcontainers)
cd ~/marketplace-<svc> && mvn -q test
# รันทั้ง stack + smoke ผ่าน Kong :8080
cd ~/marketplace-deploy && ./run.sh --build -d && ./smoke.sh
```

## กติกาการทำงาน (มาตรฐานที่ตกลงไว้)
- **task-by-task**: ทำ 1 task → รายงาน (ทำอะไร/เป็นส่วนของอะไร/ติดปัญหาอะไร) → รอ "ลุย Tx ต่อเลย"
- **feature-branch + PR ต่อ task** ห้าม commit ตรง main · footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- ship: push → `git ls-remote --heads` verify → `gh pr create` → squash merge → `git checkout main && git pull --ff-only`
- ปิด task: comment ผลวัด + move การ์ด MAR-xx เป็น Done ผ่าน Atlassian MCP + flip status ใน `gen_jira_csv.py`
- mock external deps (Meta/LLM/payment) หลัง interface · แผน/รายงาน/สเปค = ภาษาไทย

## repos (10)
`marketplace-{common,gateway,auth,catalog,order,chat,social,agent,web,deploy}` @ github.com/taskeendev
ports: auth 8081 · catalog 8082 · order 8083 · chat 8084 (+/ws) · social 8085 · agent 8086 · Kong 8080
