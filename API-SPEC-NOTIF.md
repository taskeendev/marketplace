# API Spec — NOTIF: การแจ้งเตือนสถานะออเดอร์ (in-app + realtime)

> เอกสาร API ละเอียดของเฟส NOTIF — คู่กับ SPEC.md section "SPEC — NOTIF" (ระดับ phase/task)
> สถานะ: spec ก่อน implement ทั้งหมด (T1–T4)
> ผู้ใช้เอกสาร: dev ที่ implement T1–T3 + frontend (T3) เอาไป mock ได้ทันที

---

## 1. Overview

ระบบแจ้งเตือน in-app: **buyer** รู้เมื่อของถูกส่ง/ปิดงาน (`order_shipped`/`order_done`), **seller** รู้เมื่อเงินเข้า/ถูกยกเลิก (`order_paid`/`order_cancelled`) — แสดงเป็นกระดิ่ง+badge บน nav, เด้งสดผ่าน WS เดิมของ chat, เก็บประวัติอ่าน/ยังไม่อ่านใน chatdb ผู้เรียก: order-service (ยิง event ภายใน) + React web (อ่าน/mark read)

## 2. Conventions กลาง

เหมือน **API-SPEC-P5B.md §2** ทุกข้อ (base URL ผ่าน Kong `http://localhost:8080`, ไม่มี versioning, ISO 8601 + offset, camelCase, null คงอยู่ใน JSON) — เพิ่มเฉพาะ: **ไม่มี pagination** ใน list (คืน 50 รายการล่าสุดเสมอ, retention = non-goal)

## 3. Authentication & Authorization

เหมือน **API-SPEC-P5B.md §3**: JWT ผ่าน Kong → `X-Auth-User`/`X-Auth-Role` · internal = `X-Internal-Key` ไม่ route ผ่าน Kong

| ผู้เรียก | สิทธิ์ในชุดนี้ |
|---|---|
| ทุก role ที่ login | อ่าน/mark read ของตัวเอง — **recipientKey ถูก resolve ฝั่ง server จาก identity เสมอ** (`user:<me>` + `shop:<myShopId>` ถ้า SELLER) client ส่ง key เองไม่ได้ → ไม่มี IDOR |
| order-service (internal) | `POST /internal/notifications` ด้วย `X-Internal-Key` |

**Recipient key model:** notification เก็บ `recipient_key` เป็น string เดียว — `user:<username>` (ฝั่ง buyer) หรือ `shop:<shopId>` (ฝั่ง seller) ตรงกับ key ของ `SessionRegistry` ใน chat-service เป๊ะ (WS push ใช้ key เดียวกัน)

## 4. Error Response Format กลาง

เหมือน **API-SPEC-P5B.md §4** — RFC 7807 ProblemDetail + `errors` สำหรับ validation

## 5. Error Code Catalog (เฉพาะที่เพิ่มในชุดนี้)

| HTTP | detail (ตัวอย่างจริง) | สาเหตุ | client ควรทำ |
|---|---|---|---|
| 400 | `Validation failed` (+`errors`) | internal POST ขาด field / type ไม่อยู่ในชุดที่รับ | (internal) เช็คโค้ดฝั่ง order |
| 401 | (body ว่าง) | ไม่มี token | พาไป login |
| 403 | `internal endpoint` | `X-Internal-Key` ผิด | เช็ค config |

---

## Endpoints

### N1. `POST /internal/notifications` — order ยิง event (T1 · chat)

**Use case:** order-service เรียกตอน order เปลี่ยนสถานะ (best-effort — ล้มเหลวห้ามทำ operation หลักพัง) ไม่เปิดให้ client ภายนอก

**Authorization:** header `X-Internal-Key` — ผิด/ไม่มี → 403

**Request** (`application/json`)

| Field | In | Type | Required | Description |
|---|---|---|---|---|
| recipientKey | body | String | Yes (`@NotBlank`) | `user:<username>` หรือ `shop:<shopId>` — ตรง SessionRegistry |
| type | body | String | Yes | หนึ่งใน `order_paid` `order_cancelled` `order_shipped` `order_done` — นอกชุด → 400 |
| orderId | body | Long | Yes (`@NotNull`) | order ที่เกี่ยวข้อง (web ใช้ทำลิงก์/ข้อความ) |

```json
{ "recipientKey": "shop:7", "type": "order_paid", "orderId": 42 }
```

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 200 | บันทึก + broadcast แล้ว | `{"id": 15}` |
| 400 | ขาด field / `type` นอกชุด | ProblemDetail + `errors` |
| 403 | key ผิด | ProblemDetail `detail: "internal endpoint"` |

**Business rules & side effects:** save ลง `notification` เสมอ (source of truth) → publish Redis `notif.broadcast` (best-effort — Redis ล่ม row ยังอยู่, client เห็นตอน fetch) → ทุก instance ส่ง WS frame ให้ session ของ `recipientKey` · **ไม่ idempotent** (เรียกซ้ำ = แจ้งซ้ำ — ยอมรับได้ order ยิงครั้งเดียวต่อ transition)

```bash
curl -s -X POST http://chat:8084/internal/notifications -H "X-Internal-Key: $INTERNAL_API_KEY" \
  -H 'Content-Type: application/json' -d '{"recipientKey":"shop:7","type":"order_paid","orderId":42}'
# → 200 {"id":15} · type แปลก → 400 · key ผิด → 403
```

---

### N2. `GET /api/chat/notifications` — list + unread count (T1 · chat)

**Use case:** web โหลดตอนเปิดกระดิ่ง/เข้าแอป — badge ใช้ `unread`

**Authorization:** login ทุก role · server resolve key จาก identity: ทุกคนได้ `user:<me>`, SELLER ได้ `shop:<myShopId>` เพิ่ม (ผ่าน `CatalogClient.shopOfOwner` เดิม — SELLER ที่ยังไม่มีร้าน = ได้เฉพาะ `user:` key)

**Request:** ไม่มี parameter

**Response (200)** — รวมทุก key ของผู้เรียก, เรียงใหม่→เก่า, สูงสุด 50:

```json
{
  "unread": 2,
  "items": [
    { "id": 15, "type": "order_paid", "orderId": 42, "createdAt": "2026-07-08T12:00:01.5+07:00", "read": false },
    { "id": 9,  "type": "order_shipped", "orderId": 40, "createdAt": "2026-07-08T11:30:00+07:00", "read": true }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| unread | Int | จำนวนที่ `read_at IS NULL` (ทุก key ของผู้เรียก — ไม่ cap ที่ 50) |
| items[].id | Long | ไอดี notification |
| items[].type | String | ชนิด event — web แปลเป็นข้อความผ่าน i18n |
| items[].orderId | Long | order ที่เกี่ยวข้อง |
| items[].createdAt | String (ISO 8601) | เวลาเกิด event |
| items[].read | Boolean | อ่านแล้วหรือยัง |

| Status | เมื่อไหร่ |
|---|---|
| 200 | สำเร็จ (ไม่เคยมี = `{"unread":0,"items":[]}`) |
| 401 | ไม่มี token |

```bash
curl -s http://localhost:8080/api/chat/notifications -H "Authorization: Bearer $JWT"
```

---

### N3. `POST /api/chat/notifications/read` — mark ทั้งหมดว่าอ่านแล้ว (T1 · chat)

**Use case:** web เรียกตอนผู้ใช้เปิด dropdown กระดิ่ง (per-item read = non-goal)

**Authorization:** login · กระทบเฉพาะ key ของผู้เรียก (resolve แบบ N2)

**Request:** ไม่มี body

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 200 | สำเร็จ (idempotent — ไม่มี unread ก็ 200) | `{"read": 3}` (จำนวนที่เพิ่ง mark) |
| 401 | ไม่มี token | (ว่าง) |

```bash
curl -s -X POST http://localhost:8080/api/chat/notifications/read -H "Authorization: Bearer $JWT"
# → 200 {"read":3} · ซ้ำ → 200 {"read":0}
```

---

### N4. WS frame `notification` (push, T1 chat → T3 web)

ไม่ใช่ REST — frame ใหม่บน `/ws/chat` เดิม (หลัง `auth` แล้ว) ส่งให้ทุก session ของ `recipientKey` ณ เวลาที่ event เกิด:

```json
{ "type": "notification",
  "notification": { "id": 15, "type": "order_paid", "orderId": 42, "createdAt": "2026-07-08T12:00:01.5+07:00", "read": false } }
```

- web: `unread += 1` + prepend เข้า dropdown (ถ้าเปิดอยู่) — **ไม่ต้อง refetch**
- client ที่ไม่ต่อ WS อยู่ = ไม่พลาด (row อยู่ใน DB, เห็นตอน GET ครั้งถัดไป)
- frame type อื่น (`authed/pong/message/error`) เดิมทั้งหมดไม่เปลี่ยน

---

## Data Models

**chat — `notification` (ตารางใหม่, V3)**

| column | type | หมายเหตุ |
|---|---|---|
| id | BIGSERIAL PK | |
| recipient_key | VARCHAR(80) NOT NULL, index | `user:<username>` / `shop:<shopId>` |
| type | VARCHAR(32) NOT NULL | `order_paid` `order_cancelled` `order_shipped` `order_done` |
| order_id | BIGINT NOT NULL | ไม่มี FK (order อยู่คนละ service) |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| read_at | TIMESTAMPTZ | NULL = ยังไม่อ่าน |

**order-side (T2):** `NotificationClient` (RestClient + X-Internal-Key, timeout 2s, **try/catch ทั้งก้อน — log warn แล้วไปต่อ**) + config `chat.url` (`${CHAT_URL:http://localhost:8084}`) · จุด hook: `markPaid`→`order_paid`(shop) · `cancel`→`order_cancelled`(shop) · `updateStatus` shipped/done→buyer

## Assumptions (ท้วงได้)

1. แจ้งซ้ำได้ถ้า internal ถูกเรียกซ้ำ (ไม่ทำ dedup) — จุด hook ฝั่ง order ยิงครั้งเดียวต่อ transition จริงอยู่แล้ว (markPaid idempotent = no-op ไม่ยิงซ้ำ, cancel no-op ไม่ยิงซ้ำ)
2. SELLER ที่ยังไม่เปิดร้าน → GET ได้เฉพาะ `user:` key (ไม่ error)
3. `unread` นับทั้งหมดไม่ cap (จำนวนจริงย่อมเล็กในระบบ learning)
4. WS frame ส่งเฉพาะตัวใหม่ ไม่มี replay หลัง reconnect (DB คือ source of truth — reconnect แล้ว web refetch เองผ่าน N2)
5. mark-read ตอน "เปิด dropdown" (ไม่ใช่ตอน click รายการ) — UX ง่ายสุด

## Open Questions (default ตาม Assumptions)

1. ควรแจ้ง buyer ตอน checkout สำเร็จด้วยไหม? — ตอนนี้ไม่ (เขากดเอง เห็นหน้า Pay อยู่แล้ว)
2. กระดิ่งควรอยู่ทุกหน้าหรือเฉพาะหลัง login? — เฉพาะหลัง login (guest ไม่มี notification)
