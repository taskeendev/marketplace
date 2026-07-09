# API Spec — RECO: "คนที่ซื้อสินค้านี้ยังซื้อ..." (co-purchase recommendations)

> เอกสาร API ละเอียดของเฟส RECO — คู่กับ SPEC.md section "SPEC — RECO"
> สถานะ: spec ก่อน implement (T1–T3) · ผู้ใช้เอกสาร: dev T1 + frontend T2 (mock ได้ทันที)

---

## 1. Overview

แนะนำสินค้าแบบ co-purchase บนหน้า product detail: "คนที่ซื้อสินค้านี้ยังซื้อ..." — คำนวณสดจากประวัติออเดอร์จริงใน order-service ด้วย SQL เดียว ไม่มี ML/batch ผู้เรียก: React web (หน้า Product, รวม guest)

## 2–4. Conventions / Auth / Error format

เหมือน **API-SPEC-P5B.md §2–§4** ทุกข้อ — endpoint นี้ **public** (ไม่มี ownership/IDOR เพราะเป็นข้อมูล aggregate ไม่ระบุตัวบุคคล — ไม่คืนชื่อผู้ซื้อ/จำนวน แค่ productIds)

## 5. Error Code Catalog

endpoint เดียว ไม่มี error เฉพาะ — ตอบ 200 เสมอ (product ไม่มีจริง/ไม่มีข้อมูล = `[]` ไม่ใช่ 404, ดู Business rules)

---

## Endpoints

### R1. `GET /api/orders/products/{productId}/also-bought` — top co-purchased products (T1 · order)

**Use case:** web โหลด section แนะนำใต้ product detail — เรียกได้ทั้ง guest และ login

**Authorization:** public (`permitAll` เฉพาะ path นี้ — path อื่นใต้ `/api/orders` เดิมไม่เปลี่ยน)

**Request**

| Field | In | Type | Required | Description |
|---|---|---|---|---|
| productId | path | Long | Yes | สินค้าที่กำลังดู |

**Response (200)**

| Field | Type | Description |
|---|---|---|
| productIds | Long[] | ≤8 ตัว เรียงจากคะแนนมาก→น้อย (คะแนน = จำนวนผู้ซื้อที่ทับซ้อน, tie-break = product_id น้อยก่อน) — ไม่รวม productId ที่ขอ |

```json
{ "productIds": [7, 3, 9] }
```

| Status | เมื่อไหร่ | Body |
|---|---|---|
| 200 | เสมอ — รวมกรณี product ไม่มีจริง/ไม่มีผู้ซื้อ/ไม่มี co-purchase | `{"productIds":[]}` |

**Business rules & edge cases**
- นับเฉพาะ order สถานะ **`paid` `paid_mock` `shipped` `done`** — `pending`/`cancelled` ไม่ใช่การซื้อจริง
- ผู้ซื้อคนเดียวกันนับ **1 เสียงต่อสินค้า** (`COUNT(DISTINCT buyer)`) ไม่ว่าซื้อกี่ชิ้น/กี่ออเดอร์
- นับข้ามออเดอร์ของผู้ซื้อคนเดียวกัน (ซื้อ X เดือนก่อน ซื้อ Y วันนี้ = co-purchase) — ไม่จำกัดช่วงเวลา (non-goal)
- product ที่ถูกแบน**อาจโผล่ใน ids ได้** — web กรองเองตอน fetch detail (ได้ 404 → ข้าม) → order ไม่ต้องรู้เรื่อง catalog
- product ไม่มีจริง → `[]` ธรรมดา (ไม่เช็คว่ามีอยู่ — ไม่คุ้ม 1 hop ไป catalog)

**Idempotency & side effects:** GET ล้วน ไม่มี side effect · ผลเปลี่ยนตามข้อมูลจริง (ไม่ cache — ponytail: scale นี้ query สดพอ, ceiling = materialized view)

```bash
curl -s http://localhost:8080/api/orders/products/42/also-bought
# → 200 {"productIds":[7,3]} · ไม่มีข้อมูล → {"productIds":[]}
```

---

## Data Models

**ไม่มีตาราง/คอลัมน์ใหม่** — query จาก `orders(buyer_username, status)` + `order_item(order_id, product_id)` เดิม:

```sql
SELECT oi2.product_id
FROM order_item oi1
JOIN orders o1 ON o1.id = oi1.order_id AND o1.status IN ('paid','paid_mock','shipped','done')
JOIN orders o2 ON o2.buyer_username = o1.buyer_username AND o2.status IN ('paid','paid_mock','shipped','done')
JOIN order_item oi2 ON oi2.order_id = o2.id AND oi2.product_id <> :productId
WHERE oi1.product_id = :productId
GROUP BY oi2.product_id
ORDER BY COUNT(DISTINCT o2.buyer_username) DESC, oi2.product_id
LIMIT 8
```

**Web (T2):** `alsoBought(productId)` ใน `src/api/orders.ts` → หน้า Product fetch ids แล้ว `getProduct(id)` รายตัว (มีอยู่แล้ว) — 404 ข้ามเงียบ

## Assumptions (ท้วงได้)

1. LIMIT 8 (แถวเดียวบนหน้า product) — ไม่ทำ pagination
2. ไม่กรอง product ร้านเดียวกัน/ต่างร้าน — co-purchase ข้ามร้านคือจุดขายของ marketplace
3. guest เรียกได้ (aggregate ไม่หลุดข้อมูลส่วนตัว)
4. ไม่จำกัดช่วงเวลา — ข้อมูลทั้งหมดนับเท่ากัน

## Open Questions (default ตาม Assumptions)

1. ควรโชว์บน Cart ด้วยไหม ("เพิ่มอีกนิด")? — ตอนนี้ไม่ (non-goal cross-sell)
