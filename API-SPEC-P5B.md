# API Spec — P5b: cancel + refund + address + รูป upload

> เอกสาร API ละเอียดของเฟส P5b (epic MAR-116) — คู่กับ SPEC.md section "SPEC — P5b" (ระดับ phase/task)
> สถานะ: T1 (#2 refund) = **as-built** (payment#3 merged) · T2–T4 = spec ก่อน implement
> ผู้ใช้เอกสาร: dev ที่ implement T2–T4 + frontend (T5) เอาไป mock ได้ทันที

---

## 1. Overview

API ชุดนี้เติม flow หลังการขายให้ marketplace: **ยกเลิกออเดอร์** (พร้อมคืนเงิน mock ถ้าจ่ายแล้ว และคืน stock เสมอ), **สมุดที่อยู่จัดส่ง** (buyer จัดการที่อยู่ + checkout ต้องแนบที่อยู่ → seller เห็นเพื่อส่งของ), และ **อัปโหลดรูปสินค้า** (แทนการวาง URL ภายนอก) ผู้เรียกคือ React web (ผ่าน Kong) และ service ภายใน (refund: order → payment)

## 2. Conventions กลาง

| เรื่อง | ค่า |
|---|---|
| Base URL (dev, ผ่าน Kong) | `http://localhost:8080` |
| Versioning | ไม่มี version ใน path (ตามระบบเดิม — `/api/{service}/...`) |
| Date format | ISO 8601 พร้อม offset เช่น `2026-07-08T10:15:30.123456+07:00` (Java `OffsetDateTime`) |
| Timezone | เก็บ/ตอบเป็น offset จริงของ server (dev = `+07:00` Asia/Bangkok) |
| JSON naming | camelCase |
| Pagination | **ไม่มี** ใน endpoint ชุดนี้ (list เล็ก: ที่อยู่ต่อคน, ออเดอร์ต่อคน) — คืน array เต็ม |
| ค่า null | field ที่ไม่มีค่า ใส่มาเป็น `null` ใน JSON (Jackson default) เช่น `qrData`, address fields ของ order เก่า |
| Content-Type | `application/json` ยกเว้น upload = `multipart/form-data`, serve รูป = content-type ของรูป |

## 3. Authentication & Authorization

**Flow:** client ส่ง `Authorization: Bearer <JWT>` → Kong (plugin `jwt-hs512`) verify แล้ว inject `X-Auth-User`, `X-Auth-Role` (+ `X-Auth-Sig`/`X-Auth-Ts` HMAC บน k8s) ให้ service — **service ไม่เห็น JWT**; ยิง service ตรงโดยไม่ผ่าน Kong ต้องปลอม header ซึ่งโดน 401 เมื่อ signed-header เปิด (CMN1)

**Internal endpoints** (`/internal/**` และ `/api/catalog/inventory/*`): ไม่ route ผ่าน Kong, gate ด้วย header `X-Internal-Key` (shared secret `INTERNAL_API_KEY`) — key ผิด/ไม่มี → 403

| Role | สิทธิ์ในชุดนี้ |
|---|---|
| BUYER | cancel order ตัวเอง · address CRUD ของตัวเอง · checkout |
| SELLER | upload รูป · เห็นที่อยู่จัดส่งบนออเดอร์ร้านตัวเอง (ตั้งแต่ `paid`) |
| ADMIN | ไม่เกี่ยวกับชุดนี้ |
| (internal) | `POST /internal/payments/refund` — เฉพาะ service ถือ `X-Internal-Key` |

**Ownership (กัน IDOR):** ทุก endpoint เช็คเจ้าของจาก `X-Auth-User` ใน service layer — cancel: `order.buyerUsername == user` ไม่งั้น 403 · address: `address.buyerUsername == user` ไม่งั้น 403 · checkout: `addressId` ต้องเป็นของ buyer ไม่งั้น 403

## 4. Error Response Format กลาง

ระบบใช้ **RFC 7807/9457 ProblemDetail** (Spring `spring.mvc.problemdetails.enabled=true` + `CommonExceptionHandler` ใน common) ทุก error ยกเว้นข้อยกเว้นด้านล่าง:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "order not cancellable in status: shipped",
  "instance": "/api/orders/42/cancel"
}
```

Validation error (bean validation) เพิ่ม property `errors`:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Validation failed",
  "instance": "/api/orders/addresses",
  "errors": { "recipient": "must not be blank" }
}
```

**ข้อยกเว้น (as-built, คงไว้):** checkout 409 ตอบ body เฉพาะ `{"outOfStock":[7,9]}` หรือ `{"unavailable":[3]}` · 401/403 จาก Spring Security (ไม่ผ่าน handler) = body ว่าง status อย่างเดียว

## 5. Error Code Catalog

ระบบ**ไม่มี machine-readable error code** — client แยกเคสจาก HTTP status + endpoint ที่เรียก (`detail` เป็นข้อความให้คนอ่าน อย่า parse)

| HTTP | detail (ตัวอย่างจริง) | สาเหตุ | client ควรทำ |
|---|---|---|---|
| 400 | `Validation failed` (+`errors`) | body ขาด field/ผิด format | โชว์ error รายฟิลด์จาก `errors` |
| 400 | `cart empty` | checkout ตะกร้าว่าง | พาไปหน้า cart |
| 401 | (body ว่าง) | ไม่มี/หมดอายุ JWT | refresh token หรือพาไป login |
| 403 | (body ว่าง) | role ไม่ถูก (Spring Security) | ซ่อน UI ที่ไม่มีสิทธิ์ |
| 403 | `not your order` / `not your address` | ownership ไม่ตรง | ไม่ควรเกิดจาก UI ปกติ — โชว์ error ทั่วไป |
| 403 | `internal endpoint` | `X-Internal-Key` ผิด (internal) | เช็ค config service |
| 404 | `order not found` / `address not found` / `payment not found` / `image not found` | id ไม่มีจริง/ถูกลบ | โชว์ not found, refresh list |
| 409 | `order not cancellable in status: shipped` | ยกเลิกหลังส่งของแล้ว | refresh สถานะ order, ซ่อนปุ่ม |
| 409 | `payment not paid` | refund payment ที่ยัง pending/failed | (internal) — order ฝั่งเรียกตัดสินใจ |
| 409 | `{"outOfStock":[...]}` / `{"unavailable":[...]}` | stock ไม่พอ / สินค้าถูกแบน-ลบ ระหว่าง checkout | โชว์รายการสินค้าที่มีปัญหา ให้แก้ตะกร้า |
| 413 | `image too large (max 2MB)` | ไฟล์เกิน 2MB | บอกผู้ใช้ย่อรูป |
| 415 | `unsupported image type` | ไม่ใช่ jpeg/png/webp | บอกชนิดไฟล์ที่รับ |
| 502 | `refund failed, please retry` | payment service ล่ม/ตอบ error ระหว่าง cancel | ให้ผู้ใช้กด retry (ปลอดภัย — idempotent) |

---

## Endpoints

### E1. `POST /api/orders/{id}/cancel` — buyer ยกเลิกออเดอร์ (T2 · order)

**Use case:** buyer เปลี่ยนใจหลัง checkout (ยังไม่จ่าย) หรือหลังจ่าย (ยังไม่ส่งของ) — กดปุ่ม "ยกเลิก" ในหน้า Orders

**Authorization:** role `BUYER` (SecurityConfig matcher ใหม่ `POST /api/orders/*/cancel`) + ownership: `order.buyerUsername == X-Auth-User` ไม่งั้น 403

**Request**
- Path: | `id` | long | required | order id > 0 | `42` |
- Headers: `Authorization: Bearer <JWT>` (Kong แปลงเป็น X-Auth-*)
- Body: ไม่มี

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 200 | ยกเลิกสำเร็จ (จาก `pending`) | `{"orderId": 42, "status": "cancelled", "refunded": false}` |
| 200 | ยกเลิกสำเร็จ (จาก `paid` — refund แล้ว) | `{"orderId": 42, "status": "cancelled", "refunded": true}` |
| 200 | order เป็น `cancelled` อยู่แล้ว (idempotent no-op) | `{"orderId": 42, "status": "cancelled", "refunded": false}` |
| 401 | ไม่มี/หมดอายุ token | (ว่าง) |
| 403 | ไม่ใช่ order ของตัวเอง | ProblemDetail `detail: "not your order"` |
| 404 | ไม่มี order นี้ | ProblemDetail `detail: "order not found"` |
| 409 | สถานะ `shipped`/`done`/`paid_mock` | ProblemDetail `detail: "order not cancellable in status: shipped"` |
| 502 | เรียก payment refund ไม่สำเร็จ | ProblemDetail `detail: "refund failed, please retry"` |

**Business rules & edge cases**
- ยกเลิกได้เฉพาะ `pending` และ `paid` — เส้นตายคือ `shipped` (ไม่มี return flow, non-goal)
- **ลำดับกรณี `paid`:** เรียก `POST {payment}/internal/payments/refund` ก่อน → สำเร็จค่อย flip เป็น `cancelled` + restock ใน tx เดียว; refund fail → 502, order คง `paid` (ไม่มีอะไรเปลี่ยน)
- **Restock ทุกกรณี:** `POST /api/catalog/inventory/restore` (เดิม) ด้วย `idempotencyKey = "cancel-<orderId>"` — ledger กัน restore ซ้ำที่ฝั่ง catalog
- order เก่า status `paid_mock` (pre-P5) → 409 (ไม่รองรับ — มีแต่ข้อมูลเก่าใน dev)
- **Concurrent:** กด cancel พร้อม seller กด ship — คนที่ commit ก่อนชนะ; อีกฝั่งได้ 409 (transition ผิด)

**Idempotency & side effects:** idempotent (cancelled แล้วเรียกซ้ำ = 200 เดิม, refund/restock ไม่ยิงซ้ำ — refund idempotent ที่ payment, restore idempotent ด้วย key) · side effects: payment status เปลี่ยน, stock คืน · ไม่มี notification/audit log

```bash
# สำเร็จ (order pending ของตัวเอง)
curl -s -X POST http://localhost:8080/api/orders/42/cancel -H "Authorization: Bearer $BUYER_JWT"
# → 200 {"orderId":42,"status":"cancelled","refunded":false}

# error: ยกเลิกหลังส่งของ
curl -s -X POST http://localhost:8080/api/orders/41/cancel -H "Authorization: Bearer $BUYER_JWT"
# → 409 {"type":"about:blank","title":"Conflict","status":409,"detail":"order not cancellable in status: shipped","instance":"/api/orders/41/cancel"}
```

---

### E2. `POST /internal/payments/refund` — refund (mock) — **as-built T1** (payment)

**Use case:** order service เรียกระหว่าง cancel order ที่ `paid` — ไม่เปิดให้ client ภายนอก (ไม่ route ผ่าน Kong)

**Authorization:** header `X-Internal-Key` ตรงกับ `INTERNAL_API_KEY` — ผิด/ไม่มี → 403

**Request** — Headers: `X-Internal-Key`, `Content-Type: application/json`

| field | type | required | validation | example |
|---|---|---|---|---|
| orderId | long | ✔ (`@NotNull`) | order ที่จะ refund payment | `42` |

```json
{ "orderId": 42 }
```

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 200 | refund สำเร็จ หรือ refunded อยู่แล้ว (idempotent) | `{"paymentId": 7, "status": "refunded"}` |
| 400 | `orderId` null | ProblemDetail + `errors` |
| 403 | key ผิด | ProblemDetail `detail: "internal endpoint"` |
| 404 | ไม่มี payment ของ order นี้ | ProblemDetail `detail: "payment not found"` |
| 409 | payment ยัง `pending`/`failed` | ProblemDetail `detail: "payment not paid"` |

**Business rules:** `paid`→`refunded` เท่านั้น + stamp `refunded_at` · `MockPaymentProvider.refund` สำเร็จเสมอ (ของจริง = เรียก refund API ของ gateway) · **idempotent** — เรียกซ้ำได้ปลอดภัย (จุดที่ order พึ่งตอน retry cancel)

```bash
curl -s -X POST http://payment:8087/internal/payments/refund -H "X-Internal-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" -d '{"orderId":42}'
# → 200 {"paymentId":7,"status":"refunded"}
# ซ้ำ → 200 เดิม · ยังไม่จ่าย → 409 "payment not paid"
```

---

### E3. `GET /api/orders/addresses` — list ที่อยู่ของตัวเอง (T3 · order)

**Authorization:** role `BUYER` · คืนเฉพาะของ `X-Auth-User`

**Request:** ไม่มี parameter

**Response** — 200 เสมอ (ไม่เคยมี = `[]`), เรียงเก่า→ใหม่ตาม `id`:

```json
[
  { "id": 1, "recipient": "สมชาย ใจดี", "phone": "0891234567",
    "addressLine": "99/12 หมู่ 4 ถ.สุขุมวิท ต.บางเมือง อ.เมือง จ.สมุทรปราการ 10270" }
]
```

| Status | เมื่อไหร่ |
|---|---|
| 200 | สำเร็จ (array, อาจว่าง) |
| 401 / 403 | ไม่มี token / role ไม่ใช่ BUYER |

```bash
curl -s http://localhost:8080/api/orders/addresses -H "Authorization: Bearer $BUYER_JWT"
```

---

### E4. `POST /api/orders/addresses` — เพิ่มที่อยู่ (T3 · order)

**Authorization:** role `BUYER` · สร้างให้ `X-Auth-User` เสมอ (ไม่รับ username จาก body)

**Request body**

| field | type | required | validation | example |
|---|---|---|---|---|
| recipient | string | ✔ | `@NotBlank @Size(max=100)` | `"สมชาย ใจดี"` |
| phone | string | ✔ | `@NotBlank @Size(max=20)` (free format — ไม่ validate เลขไทย) | `"0891234567"` |
| addressLine | string | ✔ | `@NotBlank @Size(max=500)` (free text บรรทัดเดียว รวม ตำบล/อำเภอ/จังหวัด/รหัส) | `"99/12 หมู่ 4 ... 10270"` |

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 201 | สร้างสำเร็จ | `{"id": 2, "recipient": "สมชาย ใจดี", "phone": "0891234567", "addressLine": "99/12 หมู่ 4 ... 10270"}` |
| 400 | validation fail | ProblemDetail + `errors: {"recipient": "must not be blank"}` |
| 401 / 403 | auth/role | (ว่าง) |

**Business rules:** ไม่จำกัดจำนวนที่อยู่ต่อคน · ที่อยู่ซ้ำกันได้ (ไม่มี unique) · ไม่มี default address — web จำ/เลือกเอง

```bash
curl -s -X POST http://localhost:8080/api/orders/addresses -H "Authorization: Bearer $BUYER_JWT" \
  -H "Content-Type: application/json" \
  -d '{"recipient":"สมชาย ใจดี","phone":"0891234567","addressLine":"99/12 หมู่ 4 ถ.สุขุมวิท ต.บางเมือง อ.เมือง จ.สมุทรปราการ 10270"}'
# → 201 · ขาด recipient → 400 Validation failed
```

---

### E5. `DELETE /api/orders/addresses/{id}` — ลบที่อยู่ (T3 · order)

**Authorization:** role `BUYER` + ownership (ของคนอื่น → 403)

**Request** — Path: | `id` | long | required | address id | `2` |

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 204 | ลบสำเร็จ | (ว่าง) |
| 403 | ที่อยู่ของคนอื่น | ProblemDetail `detail: "not your address"` |
| 404 | ไม่มี id นี้ (รวมลบซ้ำ) | ProblemDetail `detail: "address not found"` |

**Business rules & edge cases:** order ที่เคย checkout ด้วยที่อยู่นี้**ไม่กระทบ** (snapshot ไว้ใน orders แล้ว) · **ไม่ idempotent เป๊ะ:** ลบซ้ำ → 404 (client ถือ 404 หลัง DELETE = สำเร็จแล้วได้)

```bash
curl -s -X DELETE http://localhost:8080/api/orders/addresses/2 -H "Authorization: Bearer $BUYER_JWT" -w "%{http_code}"
# → 204 · ซ้ำ → 404
```

---

### E6. `POST /api/orders/checkout` — **breaking change:** บังคับ `addressId` (T3 · order)

**Use case:** buyer กด checkout จากหน้า Cart หลังเลือกที่อยู่จัดส่ง

**Authorization:** role `BUYER` (เดิม) + `addressId` ต้องเป็นของ buyer

**Request body (เดิมไม่มี body — ตอนนี้ required)**

| field | type | required | validation | example |
|---|---|---|---|---|
| addressId | long | ✔ (`@NotNull`) | ต้องมีจริง + เป็นของ buyer | `1` |

```json
{ "addressId": 1 }
```

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 201 | สำเร็จ — 1 order ต่อร้าน, snapshot ที่อยู่ลงทุก order | `{"orders":[{"orderId":43,"shopName":"ร้านป้าแดง","status":"pending","totalBaht":250}]}` (ตาม `OrderView` เดิม — ไม่เพิ่ม field) |
| 400 | ไม่มี body/`addressId` null | ProblemDetail + `errors` |
| 400 | ตะกร้าว่าง | ProblemDetail `detail: "cart empty"` |
| 403 | `addressId` ของคนอื่น | ProblemDetail `detail: "not your address"` |
| 404 | `addressId` ไม่มีจริง | ProblemDetail `detail: "address not found"` |
| 409 | stock ไม่พอ | `{"outOfStock":[7]}` (เดิม) |
| 409 | สินค้าถูกแบน/ลบ | `{"unavailable":[3]}` (เดิม) |

**Business rules & edge cases:** validate address **ก่อน** decrement stock (fail เร็ว ไม่ต้อง reconcile) · snapshot `recipient/phone/addressLine` ลงทุก order ที่แตกต่อร้าน · ตะกร้า/oversell/reconcile behavior เดิมทั้งหมดไม่เปลี่ยน · **ผลกระทบ:** client เก่าที่ POST ไม่มี body จะได้ 400 → web (T5) + smoke (T6) ต้องอัปเดตพร้อมกัน

```bash
curl -s -X POST http://localhost:8080/api/orders/checkout -H "Authorization: Bearer $BUYER_JWT" \
  -H "Content-Type: application/json" -d '{"addressId":1}'
# → 201 {"orders":[{"orderId":43,"shopName":"ร้านป้าแดง","status":"pending","totalBaht":250}]}
# ไม่ส่ง body → 400 Validation failed
```

---

### E7. `GET /api/orders/me` · `GET /api/orders/shops/me` — response += address (T3 · order)

ไม่มี endpoint ใหม่ — `OrderDto` เพิ่ม 3 field (nullable):

```json
{
  "orderId": 43, "shopName": "ร้านป้าแดง", "status": "paid", "totalBaht": 250,
  "createdAt": "2026-07-08T10:15:30.123456+07:00",
  "items": [ { "title": "เสื้อยืดสีขาว", "qty": 2, "unitPriceBaht": 125 } ],
  "recipient": "สมชาย ใจดี", "phone": "0891234567",
  "addressLine": "99/12 หมู่ 4 ถ.สุขุมวิท ต.บางเมือง อ.เมือง จ.สมุทรปราการ 10270"
}
```

**กติกาการเห็นที่อยู่ (กันข้อมูลรั่วก่อนจำเป็น):**

| ผู้เรียก | เห็น address เมื่อ |
|---|---|
| buyer (`/me`) | ทุกสถานะ (ของตัวเอง) |
| seller (`/shops/me`) | order `paid`/`shipped`/`done` เท่านั้น — `pending`/`cancelled` ได้ `null` ทั้ง 3 field |
| order เก่า (ก่อน P5b) | `null` ทั้ง 3 field (ทั้งสองฝั่ง) |

---

### E8. `POST /api/catalog/images` — upload รูปสินค้า (T4 · catalog)

**Use case:** seller เลือกไฟล์ในฟอร์มสินค้า → ได้ `url` ไป append ใน `imageUrls` ของ product create/update (**flow เดิมไม่แตะ**)

**Authorization:** role `SELLER` (ไม่เช็คว่ารูปถูกใช้กับ product ของร้านไหน — url เป็น public อยู่แล้ว)

**Request** — `Content-Type: multipart/form-data`

| part | type | required | validation | หมายเหตุ |
|---|---|---|---|---|
| file | file | ✔ | ≤ **2MB** · content-type ∈ `image/jpeg`, `image/png`, `image/webp` | เช็คจาก Content-Type ของ part (ไม่ sniff magic bytes) |

**Response**

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 201 | สำเร็จ | `{"imageId": 5, "url": "/api/catalog/images/5"}` (`url` เป็น relative — web prefix ด้วย origin เดียวกับ /api อื่น) |
| 400 | ไม่มี part `file` | ProblemDetail |
| 401 / 403 | ไม่ login / ไม่ใช่ SELLER | (ว่าง) |
| 413 | ไฟล์ > 2MB | ProblemDetail `detail: "image too large (max 2MB)"` |
| 415 | ชนิดไฟล์ไม่รับ | ProblemDetail `detail: "unsupported image type"` |

**Business rules & implementation notes**
- เก็บ `bytea` ใน catalogdb — stateless, ไม่แตะ compose/k8s (ponytail: ย้าย MinIO/S3 เมื่อรูปเยอะจริง)
- ⚠️ Spring Boot default `max-file-size` = **1MB** — ต้องตั้ง `spring.servlet.multipart.max-file-size=3MB` + `max-request-size=3MB` (สูงกว่า limit เรา เพื่อให้เช็คเองแล้วตอบ 413 พร้อม ProblemDetail แทน error ดิบของ Spring)
- ไม่ลบรูป orphan (อัปโหลดแล้วไม่ใช้/product ถูกลบ) — จด debt ไว้, non-goal

**Idempotency & side effects:** ไม่ idempotent (อัปโหลดซ้ำ = รูปใหม่ id ใหม่) — ยอมรับได้, orphan เป็น debt ที่จดแล้ว

```bash
curl -s -X POST http://localhost:8080/api/catalog/images -H "Authorization: Bearer $SELLER_JWT" \
  -F "file=@shirt.png;type=image/png"
# → 201 {"imageId":5,"url":"/api/catalog/images/5"}
curl -s -X POST http://localhost:8080/api/catalog/images -H "Authorization: Bearer $SELLER_JWT" \
  -F "file=@notes.txt;type=text/plain"
# → 415 "unsupported image type"
```

---

### E9. `GET /api/catalog/images/{id}` — serve รูป (T4 · catalog)

**Authorization:** public (เหมือน product detail — รูปสินค้าเป็นข้อมูล public)

**Request** — Path: | `id` | long | required | image id | `5` |

| Status | เมื่อไหร่ | Body / Headers |
|---|---|---|
| 200 | มีรูป | raw bytes + `Content-Type: image/png` (ตามตอน upload) + `Cache-Control: public, max-age=31536000, immutable` |
| 404 | ไม่มี id นี้ | ProblemDetail `detail: "image not found"` |

**Business rules:** immutable ปลอดภัยเพราะรูปแก้ไม่ได้ (เปลี่ยนรูป = upload ใหม่ได้ id ใหม่) — cache ยาวได้เต็มที่

```bash
curl -s http://localhost:8080/api/catalog/images/5 -o out.png -w "%{http_code} %{content_type}"
# → 200 image/png
```

---

## 13. Data Models

**order — `address` (ตารางใหม่, V7)**

| column | type | หมายเหตุ |
|---|---|---|
| id | BIGSERIAL PK | |
| buyer_username | VARCHAR(64) NOT NULL, index | เจ้าของ |
| recipient | VARCHAR(100) NOT NULL | ชื่อผู้รับ |
| phone | VARCHAR(20) NOT NULL | free format |
| address_line | VARCHAR(500) NOT NULL | free text บรรทัดเดียว |
| created_at | TIMESTAMPTZ DEFAULT now() | |

**order — `orders` (เพิ่ม 3 คอลัมน์ snapshot, nullable):** `recipient VARCHAR(100)` · `phone VARCHAR(20)` · `address_line VARCHAR(500)` — status CHECK มี `'cancelled'` อยู่แล้วตั้งแต่ V2, ไม่ต้อง migrate

**payment — `payment` (as-built V2):** status CHECK += `'refunded'` + `refunded_at TIMESTAMPTZ`

**catalog — `image` (ตารางใหม่, V8):** `id BIGSERIAL PK` · `owner_username VARCHAR(64) NOT NULL` · `content_type VARCHAR(32) NOT NULL` · `bytes BYTEA NOT NULL` · `created_at TIMESTAMPTZ DEFAULT now()`

**DTO ↔ entity mapping:** `OrderDto` += `recipient/phone/addressLine` ← columns ใหม่ของ `orders` (seller ได้ null เมื่อ `pending`/`cancelled` — ตัดสินใน service ไม่ใช่ DTO) · `AddressDto(id, recipient, phone, addressLine)` ← `address` (ไม่ expose `buyerUsername`) · checkout `OrderView` ไม่เปลี่ยน

## 14. Assumptions (เดาตาม best practice — ท้วงได้)

1. cancel เป็น **idempotent**: order `cancelled` แล้วเรียกซ้ำ → 200 no-op (สอดคล้อง `markPaid` เดิม)
2. order `paid_mock` เก่า → cancel ได้ 409 (ไม่เขียน logic refund ให้ข้อมูล pre-P5)
3. `refunded` flag ใน response cancel = "รอบนี้มีการ refund เกิดขึ้น" (no-op ซ้ำ → `false`)
4. seller เห็นที่อยู่ตั้งแต่ `paid` แต่ **ไม่เห็น**บน `cancelled` (หมดความจำเป็นในการส่งของ)
5. phone ไม่ validate รูปแบบเลขไทย (free ≤20) — รองรับเบอร์ต่างประเทศ/ต่อ
6. ไม่จำกัดจำนวน address ต่อ user และไม่มี default address (web เลือกล่าสุดเอง)
7. ตรวจชนิดรูปจาก Content-Type ของ multipart part ไม่ sniff magic bytes (ponytail — ระบบ learning, ผู้ upload ต้องเป็น SELLER ที่ login แล้ว)
8. upload รูปไม่ผูกกับ product/shop ตอน upload (`owner_username` เก็บไว้เฉย ๆ เผื่ออนาคต)
9. `url` ที่คืนเป็น relative path — ใช้ได้ทั้ง dev/prod เพราะ web เสิร์ฟใต้ origin เดียวกับ Kong
10. multipart part name = `file`

## 15. Open Questions (ไม่บล็อก implement — default ตาม Assumptions)

1. อยากให้ cancel order `paid` แจ้ง seller (chat/notification) ไหม? — ตอนนี้ non-goal, seller เห็นจาก order list
2. ควรจำกัดรูปต่อ product (เช่น ≤10) ที่ product create/update ไหม? — ตอนนี้ไม่จำกัด (เท่าเดิม)
3. Meta/LLM channel orders (`channel: fb/ig`) cancel ผ่าน API นี้ได้เหมือนกัน — ต้องแจ้งกลับช่องทางเดิมไหม? — ตอนนี้ไม่ทำ
