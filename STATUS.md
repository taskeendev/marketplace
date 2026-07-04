# STATUS — marketplace (อ่านไฟล์นี้ก่อนเริ่มทุก session)

> จุดเดียวที่บอกว่า "อยู่ตรงไหน + ทำอะไรต่อ" — อัปเดตทุกครั้งที่ปิด task
> Source of truth ลึก = [SPEC.md](./SPEC.md) · tracker = JIRA project **MAR** (@devtaskeen.atlassian.net, ผ่าน Atlassian MCP)

## ตอนนี้อยู่ตรงไหน (2026-07-04)
- **เฟส Ops กำลังทำ (Epic MAR-80, spec ใน SPEC.md "เฟส Ops", 8 tasks Ops-T1..T8 = MAR-81..88):**
  - ✅ **Ops-T1 (I1, MAR-81)** — common publish GitHub Packages (tag v0.1.0)
  - ✅ **Ops-T2 (CI, MAR-82)** — GitHub Actions build+test ครบ 7 repo เขียว (6 Java resolve common จาก Packages via **PACKAGES_TOKEN** = PAT read:packages, repo secret ทั้ง 6; web = npm). GITHUB_TOKEN อ่าน package ข้าม repo ไม่ได้แม้ public → ต้อง PAT. **⚠️ PAT อยู่ใน transcript — ควร rotate**
  - ✅ **Ops-T3 (GHCR, MAR-83)** — publish-image workflow ทั้ง 7 repo push images ขึ้น `ghcr.io/taskeendev/marketplace-*` (tag sha-<short>+latest) on merge main. **CI/CD ครบ T1→T3**
  - 🟡 **Ops-T4 (k8s, MAR-84)** — manifests เสร็จ+merged (deploy#11, kustomize 31 objects) แต่ **live deploy ติด Docker daemon ตัน** → **ปลดล็อก: restart Docker Desktop → `cd ~/marketplace-deploy && ./deploy-kind.sh`** (ใช้ image build local + kind load; ไม่พึ่ง GHCR สำหรับ local)
  - ⬜ Ops-T5 (D4 Redis) · T6 (observability) · T7 (CMN1) · T8 (HPA+smoke) — ยังไม่เริ่ม
- **เสร็จ:** P0 · P1 · P2 · P3 (a/b/c) · **P4a ครบ (T1..T5)** — T4 (MAR-48) Kong `/api/agent`+smoke 13/13 · T5 (MAR-49) web HermesToggle+🤖 badge
- deploy note: JVM ทั้ง 6 cap `-Xmx256m` + Kong 1 worker — Docker VM 3.8GB OOM ตอน 7 JVM cold start (auth exit 137); run.sh guard ตัวแปร .env ใหม่
- ✅ **spec-sync ครบ 5 จุด (MAR-77, 2026-07-03):** logout · search=ILIKE · shops/{slug} · cart error → แก้ SPEC in-place (#95) · simulate-inbound gate SELLER+owner = โค้ด (social#8) + shops/{slug} cleanup (catalog#16); verify สดผ่าน Kong
- **ถัดไป (เลือก):** P4b (Hermes admin tools) **หรือ** P5 (จ่ายเงินจริง/รีวิว/wishlist) **หรือ** เฟส Ops (deploy จริง + CI/CD + monitoring)

## ค้างอยู่ / จำไว้ (จาก spec audit 2026-07-02)
- ✅ **tech-debt เคลียร์ครบ 13/13 (2026-07-03)**: C1 C2 SD1 SD2 SD8 D1 D5 OD1 SDc1 C3 CD1 O1 + MAR-74 (Origin allowlist) — ทุกใบมีเทสตาม KPI + PR merged + MAR-xx Done. เหลือ debt ที่**เลื่อนโดยตั้งใจ**: D4/I1/CMN1 (เฟส Ops) · D6 (e2e FE) · SD6/SD7 (ติด Meta จริง)
- ✅ auth bypass MAR-72 (verified live) · ✅ ordering fix ใน T3 · ✅ spec-sync 5 จุด (MAR-77)
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
