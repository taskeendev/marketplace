# STATUS — marketplace (อ่านไฟล์นี้ก่อนเริ่มทุก session)

> จุดเดียวที่บอกว่า "อยู่ตรงไหน + ทำอะไรต่อ" — อัปเดตทุกครั้งที่ปิด task
> Source of truth ลึก = [SPEC.md](./SPEC.md) · tracker = JIRA project **MAR** (@devtaskeen.atlassian.net, ผ่าน Atlassian MCP)

## ตอนนี้อยู่ตรงไหน (2026-07-04)
- **เฟส Ops กำลังทำ (Epic MAR-80, spec ใน SPEC.md "เฟส Ops", 8 tasks Ops-T1..T8 = MAR-81..88):**
  - ✅ **Ops-T1 (I1, MAR-81)** — common publish GitHub Packages (tag v0.1.0)
  - ✅ **Ops-T2 (CI, MAR-82)** — GitHub Actions build+test ครบ 7 repo เขียว (6 Java resolve common จาก Packages via **PACKAGES_TOKEN** = PAT read:packages, repo secret ทั้ง 6; web = npm). GITHUB_TOKEN อ่าน package ข้าม repo ไม่ได้แม้ public → ต้อง PAT. **⚠️ PAT อยู่ใน transcript — ควร rotate**
  - ✅ **Ops-T3 (GHCR, MAR-83)** — publish-image workflow ทั้ง 7 repo push images ขึ้น `ghcr.io/taskeendev/marketplace-*` (tag sha-<short>+latest) on merge main. **CI/CD ครบ T1→T3**
  - ✅ **Ops-T4 (k8s, MAR-84)** — **ยกทั้ง stack ขึ้น kind สำเร็จ, smoke 13/13 ผ่านสด** (15 pod Ready: 7 app+chat×2 / 6 postgres StatefulSet / redis / kong). deploy #11+#12+#14. hardening: startupProbe · REDIS_PORT explicit · enableServiceLinks:false · Recreate strategy · drop CPU limits (Fable review). รัน: `./deploy-kind.sh` → `kubectl -n marketplace port-forward svc/kong 8080:8080 &` → `./smoke.sh`
  - ✅ **Ops-T5 (D4 Redis, MAR-85)** — Redis pub/sub fan-out. **⚠️→✅ แก้บั๊ก half-merge:** PR #20 ทำ MessageBroadcaster หาย publisher (Fable จับ) → PR #21 publish-only. **cross-pod verified live** (smoke step 10, chat replicas=2)
  - ✅ **Ops-T7 (CMN1 signed headers, MAR-87)** — common HeaderAuthFilter signed mode (HMAC X-Auth-Sig+Ts, config-gated, backward-compat) CI-verified 6/0 + **common 0.2.0 published**; gateway Kong เซ็น header (luac OK); HEADER_SIG_SECRET env. **activation รอ T8:** services bump common 0.2.0 + สร้าง filter (secret, required=true) + verify live (bypass Kong→401)
  - ✅ **Ops-T6 (observability, MAR-86)** — Prometheus (annotation SD + cAdvisor + alert rules ServiceDown/5xx/p99, emptyDir 2d) + Grafana ("Marketplace overview" dashboard). 6 service instrumented (actuator+micrometer /actuator/prometheus). **verified: scrape 6/6 up=1, dashboard render, ServiceDown fires**. deploy#15 + 6 svc PRs. Gotchas: zsh `:l` modifier ทำ image name เพี้ยน (quote!), kind `:local` reuse (rollout restart), mvn -o ก่อน dep cached. chat→replicas=1 (fit 4GB).
  - ✅ **Ops-T8 (MAR-88)** — **HPA on catalog** (metrics-server --kubelet-insecure-tls; hpa cpu 2%/70% min1/max2) + **CMN1 activation** (staged per Fable: common 0.2.1 AuthHeaderSigner → 5 svc receiver+4 caller sign → flip required=true chat/social/agent→catalog→order, smoke 13/13 ทุก step). **KPI: forged bypass Kong → 401 (probe-sig.sh)**. common#5 v0.2.1 + 5 svc PR + deploy#16. ปิด debt CMN1 (MAR-70).
  - 🎉 **เฟส Ops ปิดครบ 8/8** (MAR-80 epic Done): T1 Packages · T2 CI · T3 GHCR · T4 k8s-live · T5 Redis(D4) · T6 observability · T7+T8 CMN1 · HPA
  - **⚠️ git process:** อย่า checkout main กลางทางแล้วลืม checkout branch ก่อน commit ถัดไป (เคย commit ลง main โดยไม่ตั้งใจ); poll CI ต้องรอ run id ใหม่ ไม่ใช่ `--limit 1` ทันที
- **เสร็จ:** P0 · P1 · P2 · P3 (a/b/c) · **P4 ครบ (epic MAR-45 Done)** = P4a Hermes (T1-5) + **P4b admin/seller tools (T1-6, 2026-07-05)**
- **P4b (MAR-89..94):** T1 ban user (auth#9) · T2 ban ร้าน/สินค้า (catalog#21) · T3 flash-sale นาทีทอง+effective price (catalog#22) · T4 caption (social#13) · T5 web admin console+flash-sale/caption UI+buyer badge (web#21) · T6 Kong `/api/admin`+seed admin+**smoke 16/16** (gateway#10 deploy#17). Spring gotcha: accessDeniedHandler ต้อง `setStatus` (sendError→/error→401)
- **เฟส Ops ปิดครบ 8/8** (MAR-80) — k8s(kind) live smoke 13/13 · CI 7 repos · GHCR · Redis D4 · Prometheus/Grafana · CMN1 signed headers · HPA
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
