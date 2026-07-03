# SPEC — Omnichannel Marketplace (greenfield, multi-repo)

> **สำหรับ agent ที่ลงมือทำ:** ใช้ superpowers:writing-plans (task ทีละ 2–5 นาที, TDD, commit ถี่). task ใช้ checkbox.
> เขียนใหม่ทั้งหมด ไม่แตะ lab เดิม. P0–P2 + P3 + P4a = สเปคเต็ม (task + API input/output). P4b/P5 = โครง (ลง API ตอนเริ่มแต่ละเฟส).

## ข้อสรุปที่ยืนยันแล้ว (ผู้ใช้เคาะเอง)

greenfield ทั้งหมด · **Java 21 + Spring Boot 3.4.x + Maven** · **React 19 + Vite + TS + Tailwind + shadcn** ·
**Kong** gateway · **multi-repo** `marketplace-*` ใต้ GitHub **taskeendev** (common lib ผ่าน GitHub Packages) ·
role **BUYER/SELLER/ADMIN** · **Postgres ต่อ service + Flyway** · catalog = สต็อกก้อนเดียว (atomic/idempotent) ·
**P1 รูป = URL อย่างเดียว** · **P0/P1 รัน docker-compose ในเครื่อง** (deploy จริงทีหลัง) · i18n typed TH/EN ·
JWT(HS512) access ใน memory + refresh ใน HttpOnly cookie · cart ฝั่ง server · search P1 = PG full-text · ฿ THB ·
AI = Hermes (P4) · จ่ายเงินจริง = P5 · แพลนภาษาไทย

## สถาปัตยกรรม + repos

```
React (marketplace-web) ─► Kong (:8080) ─┬─► marketplace-auth     :8081
   + WebSocket (P2)   (JWT plugin, inject  ├─► marketplace-catalog  :8082 (สต็อกจริง)
                       X-Auth-User/Role,    ├─► marketplace-order    :8083
                       rate-limit, CORS)    ├─► marketplace-chat     :8084 + /ws/chat (P2)
                                            ├─► marketplace-social   :8085 (P3)
                                            └─► marketplace-agent    :8086 (P4, Hermes)
```
repo: `marketplace-{gateway,auth,catalog,order,chat,social,agent,web,deploy,common}` · DB-per-service ·
JWT เป็น contract (service เชื่อ `X-Auth-User`/`X-Auth-Role` จาก Kong, ไม่ยิงถาม auth ข้าม service)

## กติกา API (ใช้ทุกเส้น)

- Auth: client ส่ง `Authorization: Bearer <JWT>` → Kong plugin `jwt-hs512` verify แล้ว inject `X-Auth-User`(sub/username), `X-Auth-Role`(role) ให้ service ปลายทาง
- **Trust boundary (สำคัญ):** Kong plugin **ลบ `X-Auth-User`/`X-Auth-Role` ที่ client แนบมาเสมอ** (ต้น access phase) แล้วจึง set ใหม่เฉพาะ token ที่ valid → service เชื่อ 2 header นี้ได้เพราะรับประกันว่ามาจาก Kong เท่านั้น. พฤติกรรม plugin: **ไม่มี token → ปล่อยผ่าน** (public endpoint ตัดสินเองที่ service) · **token ผิด/หมดอายุ → 401 ที่ Kong** `{status, detail}` · **valid → inject X-Auth-***
- **X-Internal-Key:** service-to-service (order→catalog decrement, chat↔social, chat→agent) ยืนยันตัวด้วย header `X-Internal-Key` (env `INTERNAL_KEY`, docker network เท่านั้น). `/internal/*` และ `/api/catalog/inventory/decrement` = internal → **ไม่ route ผ่าน Kong**
- Error = **RFC 7807** JSON: `{ "status": int, "detail": string, "errors": { field: msg }? }`
- Content-Type `application/json` · เวลา = ISO-8601 UTC · เงิน = integer สตางค์? → **ใช้ราคาเป็น integer บาท** (ไม่มีจุดทศนิยมในขอบเขตนี้)
- กรณีไม่มีสิทธิ์ = 403, ไม่ล็อกอิน = 401, validation = 400 + `errors`, ชนกัน = 409, ไม่พบ = 404
- **Swagger/OpenAPI:** ทุก service ใส่ `springdoc-openapi` → `/swagger-ui.html` + `/v3/api-docs` (Kong route ให้เข้าได้ตอน dev)

## Data model (P0/P1)

**auth** (db: authdb): `app_user(id, email UNIQUE, username UNIQUE, password_hash, role[BUYER|SELLER|ADMIN]
default BUYER, created_at)` · `refresh_token(id, user_id, token_hash UNIQUE, expires_at, revoked_at, created_at)`

**catalog** (db: catalogdb): `category(id, slug UNIQUE, name_en, name_th)` ·
`shop(id, owner_username UNIQUE, name, slug UNIQUE, description, created_at)` ·
`product(id, shop_id, category_id, title_en, title_th, desc_en, desc_th, price_baht int, status[draft|active|
banned] default active, created_at)` · `product_image(id, product_id, url, sort)` ·
`inventory(product_id PK→product, stock_qty int, reserved_qty int default 0)` ·
`stock_ledger(id, product_id, change int, reason, idempotency_key UNIQUE, created_at)` ← กันตัดซ้ำ

**order** (db: orderdb): `cart(id, buyer_username UNIQUE)` · `cart_item(id, cart_id, product_id, qty)` ·
`orders(id, buyer_username, shop_id, channel[web|fb|ig] default web, status[pending|paid_mock|shipped|done|
cancelled], total_baht int, created_at)` · `order_item(id, order_id, product_id, title_snapshot, unit_price_baht,
qty)`

---

# SPEC — Phase 0: รากฐาน (Foundation)

**เป้าหมายเฟส:** มี gateway + auth + web shell + รันทั้ง stack ด้วย docker-compose ในเครื่องได้ →
สมัคร/ล็อกอินผ่าน Kong แล้วเข้าหน้า account ได้จริง (8 task)

- [ ] **P0-T1: marketplace-common** — เป้าหมาย: lib กลาง (Java) มี `JwtVerifier`(HS512) + RFC7807 error model +
  `@RestControllerAdvice` handler → publish `com.taskeendev:marketplace-common:0.1.0` ไป GitHub Packages ·
  verify: `mvn -q -DskipTests install` ผ่าน + service อื่น depend แล้ว resolve ได้
- [ ] **P0-T2: marketplace-auth scaffold** — Boot+Maven+Postgres+Flyway+common+**springdoc** · Flyway `V1__users.sql`,
  `V2__refresh_tokens.sql` · verify: Testcontainers ขึ้น Postgres + app boot + `/health`→200 + `/swagger-ui` ขึ้น
- [ ] **P0-T3: auth register/login/JWT** — issue access JWT(HS512, TTL 15m, claim sub=username, role) + refresh
  (hash เก็บ DB, HttpOnly cookie 14 วัน) · verify: integration test register→login ได้ token, /users/me ใช้ token ได้
- [ ] **P0-T4: auth refresh/logout/me + roles** — rotate refresh + reuse-detection; role default BUYER · verify: test refresh ได้ token ใหม่, logout แล้วใช้ refresh เดิมไม่ได้
- [ ] **P0-T5: marketplace-gateway (Kong)** — declarative `kong.yml`: route `/api/auth`,`/api/users`→auth;
  plugin verify HS512 + inject `X-Auth-User`/`X-Auth-Role`; rate-limit; CORS; correlation-id · verify: ยิงผ่าน :8080 ทะลุไป auth, token เสีย→401 ที่ Kong
- [ ] **P0-T6: marketplace-deploy** — `docker-compose.yml` (kong + auth + postgres-auth) + `.env.example` +
  `run.sh` + `smoke.sh` · verify: `./run.sh --build -d` ขึ้นครบ healthy
- [ ] **P0-T7: marketplace-web shell** — Vite/TS/Tailwind/shadcn: `config.ts`(env), `api/client.ts`(fetch+JWT
  memory+refresh-on-401), `auth.tsx`+`ProtectedRoute`, i18n `locales/{en,th}.ts`, หน้า Login/Register/Account,
  ApiStatus(ping /health) · verify: `npm run build` ผ่าน, ล็อกอินผ่าน Kong ได้, สลับ TH/EN ได้
- [ ] **P0-T8: smoke P0** — `smoke.sh`: register→login→/users/me ผ่าน gateway = 200 · verify: smoke เขียว

### API — Phase 0 (auth, ผ่าน Kong :8080)
| Method/Path | สิทธิ์ | input | output (สำเร็จ) | error |
|---|---|---|---|---|
| `POST /api/auth/register` | public | `{email, username, password}` | `201 {id, username, email, role:"BUYER"}` | 400 errors, 409 dup |
| `POST /api/auth/login` | public | `{username, password}` | `200 {accessToken, expiresIn}` + Set-Cookie refresh | 401 |
| `POST /api/auth/refresh` | cookie | — (refresh cookie) | `200 {accessToken, expiresIn}` | 401 |
| `POST /api/auth/logout` | Bearer | — | `204` | 401 |
| `GET /api/users/me` | Bearer | — | `200 {id, username, email, role}` | 401 |
| `GET /health` | public | — | `200 {status:"UP"}` | — |

---

# SPEC — Phase 1: แก่น marketplace (web MVP)

**เป้าหมายเฟส:** marketplace หลายผู้ขายครบลูปบน web — ผู้ใช้เป็นผู้ขายได้/เปิดร้าน/ลงสินค้า(ตั้งสต็อก); ผู้ซื้อ
เลือก-ค้นหา-ใส่ตะกร้า-checkout(จำลอง)-ดูออเดอร์; **ตัดสต็อก atomic กัน oversell**; ผู้ขายดู/อัปสถานะออเดอร์; TH/EN
(รวม ~14 task)

**Service ใหม่:** `marketplace-catalog` (:8082), `marketplace-order` (:8083) · แก้ auth (become-seller), gateway, deploy, web

- [ ] **P1-T1: catalog scaffold + category** — Boot+Maven+Postgres+Flyway · `category` + seed (Fashion/Food/Gadget…) · `GET /api/catalog/categories` · verify: คืน list หมวด
- [ ] **P1-T2: auth become-seller** — `POST /api/users/me/become-seller` เปลี่ยน role→SELLER (ต้อง refresh token ใหม่ถึงมีสิทธิ์) · verify: test BUYER→SELLER
- [ ] **P1-T3: shop** — สร้าง/ดูร้าน (เจ้าของ 1 ร้าน/คนใน MVP) · verify: SELLER สร้างร้านได้, BUYER โดน 403
- [ ] **P1-T4: product CRUD (seller)** — ลง/แก้/ลบ/ดูสินค้าของร้านตัวเอง (มี i18n field + ราคา + รูป URL + สต็อกเริ่มต้น) · verify: ลงสินค้าแล้ว inventory ถูกสร้าง stock=ที่กรอก
- [ ] **P1-T5: inventory decrement (atomic+idempotent)** — `POST /api/catalog/inventory/decrement`: `UPDATE … WHERE stock_qty>=qty` + เขียน `stock_ledger` ตาม idempotency_key · verify: **เทสต์ขนานบน stock=1 → สำเร็จ 1 อันเท่านั้น**; ยิงซ้ำ key เดิม → ไม่ตัดเบิ้ล
- [ ] **P1-T6: public browse/search** — `GET /products` (q + categoryId + paging, PG full-text บน title), `GET /products/{id}` · verify: ค้นหาเจอ, สินค้า banned/draft ไม่โผล่
- [ ] **P1-T7: order scaffold + cart** — Boot+Postgres+Flyway · ตะกร้าต่อผู้ซื้อ (เพิ่ม/แก้จำนวน/ลบ) · verify: เพิ่มของลงตะกร้าแล้วดูได้
- [ ] **P1-T8: checkout (mock)** — `POST /api/orders/checkout`: แตกตะกร้าตามร้าน → เรียก catalog decrement (idempotency=orderId) → สร้าง order/order_item (status `paid_mock`) → เคลียร์ตะกร้า; ถ้าของหมด rollback ทั้งบิล · verify: checkout สำเร็จ stock ลด; ของหมด → 409 ไม่สร้าง order
- [ ] **P1-T9: orders (buyer/seller)** — buyer ดูออเดอร์ตัวเอง; seller ดูออเดอร์ร้าน + อัปสถานะ (paid_mock→shipped→done) · verify: เห็นตรงฝั่ง, อัปสถานะผิดลำดับ → 400
- [ ] **P1-T10: gateway + deploy ขยาย** — Kong route `/api/catalog`,`/api/orders`; compose เพิ่ม catalog+order+postgres ของแต่ละตัว · verify: ยิงผ่าน :8080 ได้ทั้งคู่
- [ ] **P1-T11: web — storefront + product** — หน้าหลัก (หมวด+ค้นหา), หน้าสินค้า (รูป/ราคา/สต็อก/ปุ่มใส่ตะกร้า) · verify: เลือกสินค้า→ใส่ตะกร้าได้
- [ ] **P1-T12: web — cart + checkout + my orders** — ตะกร้า, checkout(จำลอง)→หน้ายืนยัน, ออเดอร์ของฉัน · verify: ครบลูปซื้อ
- [ ] **P1-T13: web — seller dashboard** — become-seller, ร้านฉัน, สินค้า CRUD+สต็อก, ออเดอร์ร้าน+อัปสถานะ · verify: ผู้ขายจัดการได้ครบ
- [ ] **P1-T14: i18n + smoke P1** — เพิ่ม key TH/EN ครบ (shop/seller/cart/order); `smoke.sh` ครบลูป + oversell test · verify: smoke เขียว, สลับภาษาครบ

### API — Phase 1
**catalog**
| Method/Path | สิทธิ์ | input | output | error |
|---|---|---|---|---|
| `GET /api/catalog/categories` | public | — | `200 [{id, slug, nameEn, nameTh}]` | — |
| `POST /api/catalog/shops` | SELLER | `{name, slug?, description}` | `201 {id, ownerUsername, name, slug, description}` | 403/409 |
| `GET /api/catalog/shops/me` | SELLER | — | `200 {shop…}` | 404 |
| `GET /api/catalog/shops/{slug}` | public | — | `200 {shop + products}` | 404 |
| `POST /api/catalog/shops/me/products` | SELLER | `{categoryId, titleEn, titleTh, descEn, descTh, priceBaht, imageUrls:[], stockQty, status?}` | `201 {id, …, stockQty}` | 400/403 |
| `PUT /api/catalog/shops/me/products/{id}` | SELLER | (เหมือนสร้าง; stockQty = ตั้งใหม่) | `200 {product}` | 400/403/404 |
| `GET /api/catalog/shops/me/products` | SELLER | — | `200 [{product + stockQty}]` | 403 |
| `GET /api/catalog/products` | public | `?q=&categoryId=&page=&size=` | `200 {items:[{id, titleEn, titleTh, priceBaht, imageUrl, shopName, stockQty}], page, total}` | — |
| `GET /api/catalog/products/{id}` | public | — | `200 {id, shop, category, titleEn/Th, descEn/Th, priceBaht, images:[], stockQty, status}` | 404 |
| `POST /api/catalog/inventory/decrement` | internal | `{items:[{productId, qty}], idempotencyKey}` | `200 {ok:true}` | `409 {outOfStock:[productId]}` |

**order**
| Method/Path | สิทธิ์ | input | output | error |
|---|---|---|---|---|
| `GET /api/orders/cart` | BUYER | — | `200 {items:[{productId, title, priceBaht, qty, lineTotal, stockQty}], total}` | 401 |
| `POST /api/orders/cart/items` | BUYER | `{productId, qty}` | `200 {cart}` | 400/404 |
| `PUT /api/orders/cart/items/{productId}` | BUYER | `{qty}` | `200 {cart}` | 400/404 |
| `DELETE /api/orders/cart/items/{productId}` | BUYER | — | `200 {cart}` | 404 |
| `POST /api/orders/checkout` | BUYER | — (ใช้ตะกร้า) | `201 {orders:[{orderId, shopName, status:"paid_mock", totalBaht}]}` | `409 {outOfStock:[…]}` |
| `GET /api/orders/me` | BUYER | — | `200 [{orderId, shopName, status, totalBaht, createdAt, items:[{title, qty, unitPriceBaht}]}]` | 401 |
| `GET /api/orders/shops/me` | SELLER | `?status=` | `200 [orders ของร้าน]` | 403 |
| `PATCH /api/orders/{id}/status` | SELLER | `{status}` | `200 {orderId, status}` | 400/403/404 |

**auth (เพิ่ม)**
| `POST /api/users/me/become-seller` | Bearer | — | `200 {role:"SELLER"}` (ต้อง refresh token) | 401 |

---

# SPEC — Phase 2: แชต real-time (พระเอก)

**เป้าหมายเฟส:** buyer↔seller คุยกันสดจากหน้าสินค้า (WebSocket), เก็บประวัติ, รายการห้องแชต, unread —
เป็นรากฐานที่ P4 (Hermes agent) จะมาตอบอัตโนมัติทีหลัง (10 task — แตกละเอียดเพื่อจัดการง่าย, scope = Lean เท่าเดิม)

**Service ใหม่:** `marketplace-chat` (:8084) · แก้ gateway (route `/api/chat` + `/ws/chat`), deploy, web

**ตัดสินใจ (ผู้ใช้เคาะ):** ห้อง = **ต่อร้าน** (1 ห้อง/คู่ buyer–shop) + แนบสินค้าที่เริ่ม · ขอบเขต = **Lean core**
(text เรียลไทม์/ประวัติ/รายการ/unread/การ์ดสินค้า; ตัด typing/presence/read-receipt/รูป/multi-instance/group) ·
transport = **Raw WebSocket** (`TextWebSocketHandler` + JSON) · เผื่อ P4 agent seam = ไว้ทำตอน P4

- [ ] **P2-T1: chat scaffold + data model** — Boot+Postgres(chatdb)+Flyway+common+websocket · ตาราง `conversation`/`message` · health · verify: boot + Testcontainers
- [ ] **P2-T2: CatalogClient + สร้างห้อง** — `CatalogClient` (product→shop, shops/me→shopId) + `POST /conversations` find-or-create · verify: ยิงซ้ำ productId เดิม → ห้องเดิม
- [ ] **P2-T3: รายการห้อง + unread** — `GET /conversations` (buyer by username / seller by shopId) + unread count · verify: เห็นถูกฝั่ง, unread ถูก
- [ ] **P2-T4: ประวัติข้อความ + guard** — `GET /{id}/messages?before=&limit=` + participant guard · verify: คนนอกห้อง → 403
- [ ] **P2-T5: mark-read** — `POST /{id}/read` (set last_read_at ตามฝั่ง) · verify: read แล้ว unread = 0
- [ ] **P2-T6: WS endpoint + auth + registry** — `/ws/chat` `TextWebSocketHandler`, frame แรก auth (`common.JwtVerifier`), in-memory registry · verify: auth ✓ → `authed` / ผิด → ปิด 4401
- [ ] **P2-T7: WS send + delivery** — `{type:"send"}` persist + push ไป buyer+shop (echo), guard ไม่ใช่คู่ → 4403 · verify: **2 client ส่ง→อีกฝั่งได้รับจริง**
- [ ] **P2-T8: gateway + deploy** — Kong route `/api/chat`+`/ws/chat` (WS upgrade); compose เพิ่ม chat+postgres-chat; run.sh · verify: ยิงผ่าน :8080 + WS ทะลุ
- [ ] **P2-T9: web — chat page** — ปุ่ม "แชตผู้ขาย" หน้าสินค้า + หน้า `/chat` (list+thread+WS send/recv+mark-read) · verify: คุยสองทางผ่าน Kong
- [ ] **P2-T10: web — unread badge + i18n + smoke** — badge unread ใน header, i18n TH/EN, e2e smoke P2 · verify: badge อัปเดต, สลับภาษา, smoke เขียว

### Data model — Phase 2 (db: chatdb)
- `conversation(id, buyer_username, shop_id, shop_name, product_id NULL, buyer_last_read_at, seller_last_read_at, last_message_at, created_at)` · **UNIQUE(buyer_username, shop_id)** = 1 ห้อง/คู่
- `message(id, conversation_id →conversation ON DELETE CASCADE, sender_username, body, created_at)` · INDEX(conversation_id, created_at)
- unread (ฝั่งฉัน) = `COUNT(message WHERE created_at > my_last_read_at AND sender_username != ฉัน)` · ฝั่งผู้ขาย route ด้วย `shop_id` (resolve จาก catalog `/shops/me`)

### API — Phase 2
**chat REST `/api/chat`** (ผ่าน Kong, identity จาก `X-Auth-User`/`X-Auth-Role`)
| Method/Path | สิทธิ์ | input | output | error |
|---|---|---|---|---|
| `POST /api/chat/conversations` | BUYER | `{productId}` | `200 {id, shopId, shopName, productId, lastMessageAt}` (find-or-create) | 400/404 |
| `GET /api/chat/conversations` | BUYER/SELLER | — | `200 [{id, shopId, shopName, productId, lastMessage, unread, lastMessageAt}]` | 401 |
| `GET /api/chat/conversations/{id}/messages` | participant | `?before=&limit=` | `200 [{id, conversationId, senderUsername, body, createdAt}]` | 403/404 |
| `POST /api/chat/conversations/{id}/read` | participant | — | `204` | 403/404 |

**chat WebSocket `/ws/chat`** (JSON text frames · auth ด้วย frame แรก เพราะ browser ตั้ง header บน WS handshake ไม่ได้)
| ทิศ | frame | หมายเหตุ |
|---|---|---|
| client→ | `{type:"auth", token}` (frame แรกบังคับ) | ✓ → `{type:"authed"}` ; ✗ → close **4401** |
| client→ | `{type:"send", conversationId, body}` | เช็คเป็นคู่สนทนา → persist → push ไป buyer+shop; ไม่ใช่คู่ → close **4403** |
| →client | `{type:"message", message:{id, conversationId, senderUsername, body, createdAt}}` | ส่งถึงทั้งสองฝั่ง (echo ผู้ส่งด้วย) |
| →client | `{type:"error", detail}` | error อื่นๆ |

**เชื่อม catalog (chat→catalog, internal docker net):** สร้างห้อง → `GET /api/catalog/products/{id}` (shopId, shopName) · seller resolve ร้าน → `GET /api/catalog/shops/me` (forward identity)
**gateway (เพิ่ม):** Kong route `/api/chat`→chat-service · `/ws/chat`→chat-service (WS upgrade; global jwt-hs512 plugin ปล่อยผ่านเมื่อไม่มี token header บน handshake)

---

# โครง P3–P5 (ลงรายละเอียด API ตอนเริ่มแต่ละเฟส)

**Phase 3 — omnichannel social (FB/IG)** = 3 ระบบอิสระ → แตกเป็น sub-phase (แต่ละอันมี spec+plan+build แยก). ทั้งหมด **mock external Meta ก่อน**, เสียบ Graph จริงตอน Meta Business verification ผ่าน (⚠️ blocker เดิม):
- **P3a — Omnichannel inbox**: FB Messenger DM → รวมในกล่องแชต P2 *(สเปคเต็มด้านล่าง)*
- **P3b — Product sync**: catalog → FB/IG Shops *(สเปคเต็มด้านล่าง)*
- **P3c — Social login**: FB OAuth ใน auth *(สเปคเต็มด้านล่าง)*

### SPEC — P3a: Omnichannel inbox (FB Messenger, 2-way, mock Meta)
**เคาะแล้ว (brainstorm 2026-06-30):** external contact (conversation +channel +external_id +display_name, **ไม่สร้าง user**) · รวมในกล่องแชต P2 เดิม · **FB Messenger ช่องเดียว 2-way** · social↔chat = **internal REST** (ตัด queue/Kafka)

**สถาปัตยกรรม:** service ใหม่ `marketplace-social` (:8085) = FB gateway (webhook verify + receive + Meta Send *mock* + page connection *mock*); chat (P2) extend รองรับ channel/external. ทั้งคู่หลัง Kong + ใช้ `common`.

**Data flow**
- **ขาเข้า:** FB webhook → social normalize → `POST {chat}/internal/inbound {channel:fb, pageId, externalId, displayName, body}` → chat map pageId→shop, find-or-create external conversation, persist, **broadcast เข้า WS ของ seller** → seller เห็นใน `/chat` (badge FB)
- **ขาออก:** seller ตอบในห้อง fb → `POST {social}/internal/send {pageId, externalId, body}` → social → Meta Send API (**mock:** บันทึก `outbound_log`)

**Mock Meta:** Send = mock client หลัง interface (บันทึก+log; เสียบ Graph จริงทีหลัง) · inbound = `POST /internal/social/simulate-inbound` จำลอง webhook (smoke/demo) · connection = "เชื่อม FB Page (mock)" ผูก `pageId↔shop` + fake token

**Data model**
- `chat.conversation`: +`channel` default `'web'`, +`external_id` null, +`display_name` null · unique ใหม่ `(shop_id, channel, external_id)` (web คงเดิม `(buyer_username, shop_id)`)
- `chat.message`: inbound external → `sender_username` null = customer · unread ของ seller = นับฝั่ง customer หลัง `last_read`
- `social`: `page_connection(shop_id, page_id, page_token, channel)` · `outbound_log(page_id, external_id, body, created_at)`

**Internal/REST API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `GET /webhooks/fb` | social | public | Meta webhook verify (echo `hub.challenge`) |
| `POST /webhooks/fb` | social | (Meta sig) | รับ event → normalize → เรียก chat `/internal/inbound` |
| `POST /internal/social/simulate-inbound` | social | internal | จำลอง FB inbound (dev/smoke) |
| `POST /internal/social/send` | social | `X-Internal-Key` | mock Meta Send + บันทึก `outbound_log` |
| `POST /internal/chat/inbound` | chat | `X-Internal-Key` | find-or-create external conversation + persist + broadcast WS |
| `POST /api/social/connections` | social | SELLER | เชื่อม FB Page (mock) ผูก `pageId↔shop` |

**Web:** `/chat` แสดง badge ช่อง (web/FB) + ชื่อ external contact (seller ตอบเหมือนเดิม) · seller dashboard: "เชื่อม Facebook Page (mock)" + ปุ่ม dev "จำลองข้อความ FB เข้า"

**gateway/deploy:** Kong route `/api/social` + `/webhooks/fb`→social · compose +social +postgres-social · **smoke step 11:** simulate inbound → โผล่ใน chat ของ seller → seller ตอบ → `outbound_log` มี record (ทะลุ Kong)

**แตกงาน (P3a-T1..T6 — ทำทีละ task + test ก่อน done)**
- **T1 [BE]** scaffold `marketplace-social` (:8085, Postgres+Flyway+common) + `page_connection` + webhook verify (GET challenge) → boot + test
- **T2 [BE]** chat extend conversation/message (channel/external) + `POST /internal/chat/inbound` (find-or-create external + broadcast WS) → test
- **T3 [BE]** social: receive `POST /webhooks/fb` → normalize → เรียก chat `/inbound` + `POST /internal/social/simulate-inbound` → test
- **T4 [BE]** outbound: seller ตอบในห้อง fb → chat เรียก social `/internal/send` → mock send + `outbound_log` → test
- **T5 [GW]** Kong route `/api/social` + `/webhooks/fb` · compose +social +postgres-social · run.sh build social · **smoke step 11**
- **T6 [FE]** web: channel badge + external name ใน `/chat` + "connect FB (mock)" + ปุ่ม dev simulate

### SPEC — P3b: Product sync (catalog → FB Shops, mock)
**เคาะแล้ว (brainstorm 2026-07-01):** seller กดปุ่ม **"sync ทั้งหมดไป FB"** (manual) · **social** เป็นเจ้าของ FB catalog sync · mock Meta · scope = push สินค้า **ACTIVE ทั้งหมด**, กดซ้ำ = upsert, ไม่จัดการลบ (Lean) · reuse route `/api/social` + service social เดิม (P3a) → ไม่ต้องแตะ gateway/compose

**Flow:** seller `POST /api/social/sync` → social ดึงสินค้าจาก catalog `GET /shops/me/products` (forward identity) → mock push แต่ละชิ้นขึ้น FB catalog (`FbCatalog` interface + `MockFbCatalog`) → upsert `published_product` → คืน `{synced:N, syncedAt}`

**Data model (social):** `published_product(id, shop_id, product_id, fb_product_id, title, price_baht, synced_at)` UNIQUE(shop_id, product_id)

**API (reuse `/api/social`):**
| Method Path | Auth | ทำอะไร |
|---|---|---|
| `POST /api/social/sync` | SELLER | ดึง `/shops/me/products` → mock push → upsert published_product → `{synced, syncedAt}` |
| `GET /api/social/sync` | SELLER | สถานะ `{count, lastSyncedAt}` |

**Web:** seller dashboard ปุ่ม "Sync สินค้าไป Facebook" → "sync แล้ว N ชิ้น เมื่อ [เวลา]" · i18n TH/EN

**Testing:** social — sync ดึง N (MockWebServer stub catalog) → published_product N แถว + mock pusher ถูกเรียก · re-sync = upsert (ไม่ซ้ำ) · non-seller 403 · **smoke step 12:** seller sync → GET status = N (ทะลุ Kong)

**แตกงาน (P3b-T1..T2)**
- **T1 [BE]** social: `published_product` + CatalogClient.listMyProducts (forward identity) + `FbCatalog`(mock) + `POST/GET /api/social/sync` · verify: sync ดึง N (MockWebServer stub catalog) → `published_product` N แถว + mock pusher ถูกเรียก; re-sync = upsert (ไม่ซ้ำ); non-seller → 403
- **T2 [FE]** web: ปุ่ม "Sync สินค้าไป Facebook" + สถานะ ("sync แล้ว N ชิ้น เมื่อ [เวลา]") + i18n TH/EN · verify: seller กด sync → `GET /api/social/sync` = N (ทะลุ Kong) = **smoke step 12**

### SPEC — P3c: Social login (real FB OAuth)
**เคาะแล้ว (brainstorm 2026-07-01):** **real FB OAuth** (authorization-code flow จริงผ่าน Graph API) · สร้าง user ใหม่ + ผูกถ้า email ซ้ำ · test ด้วย **mock Graph** (MockWebServer) ไม่ติด Meta · แตะแค่ **auth + web** (route `/api/auth` ผ่าน Kong อยู่แล้ว → ไม่แตะ gateway)

**Flow:** web "Login with Facebook" → FB OAuth dialog → callback(`?code`) → web POST code ให้ auth → auth แลก `code→access_token` (Graph) → ดึงโปรไฟล์ `id,name,email` → find-or-create/link user → issueTokens (JWT+refresh เดิม) → ล็อกอิน

**Data model (auth `app_user`):** +`external_provider_id VARCHAR(64) UNIQUE NULL` (เช่น `facebook:<id>`) · `password_hash` → **nullable** (social user ไม่มีรหัส; password-login กัน null hash)

**API (auth, public)**
| Method Path | In → Out |
|---|---|
| `GET /api/auth/oauth/fb/login-url` | → `{url}` (auth สร้าง FB authorize URL + state) |
| `POST /api/auth/oauth/fb/callback` `{code, redirectUri}` | แลก token + โปรไฟล์ → find-or-create/link → `{accessToken, expiresIn}` + refresh cookie (เหมือน login) |

**Config (auth yml + compose env):** `fb.app-id`, `fb.app-secret`, `fb.redirect-uri`, `fb.graph-url` (`${FB_GRAPH_URL:https://graph.facebook.com}` — test ชี้ MockWebServer)

**Web:** ปุ่ม "เข้าสู่ระบบด้วย Facebook" (Login) → GET login-url → redirect · route `/oauth/fb/callback` อ่าน `?code` → POST callback → set token → หน้าแรก · i18n TH/EN

**Prereq ใช้จริง:** Meta app (App ID/Secret) + redirect URI ตั้งใน Meta dashboard → ใส่ `.env` · **ไม่มี smoke step** (real OAuth ผ่าน Kong ต้องมี creds) → coverage ด้วย integration test (mock Graph)

**แตกงาน (P3c-T1..T2)**
- **T1 [BE]** auth: `V3__social.sql` (external_provider_id + password nullable) + `FbOAuthService` + `GraphClient` (RestClient แลก code→token + GET `/me?fields=id,name,email`) + `OAuthController` (2 endpoints) + config `fb.*` + UserRepository `findByExternalProviderId` + reuse `JwtIssuer` · verify: callback → สร้าง user ใหม่ + JWT ถูก; email ซ้ำ → ผูก user เดิม (ไม่สร้างซ้ำ); external_provider_id เดิม → login เดิม; login-url มี app-id + state (MockWebServer graph)
- **T2 [FE]** web: ปุ่ม Login-with-Facebook + route `/oauth/fb/callback` + `api/auth.ts` (fbLoginUrl/fbCallback) + i18n · compose auth env `FB_*` + `.env.example` · verify: `npm run build`; ปุ่ม redirect FB dialog; callback set token

**Phase 4 — Hermes AI agent + admin** = แตกเป็น P4a (agent) + P4b (admin). ทำ **P4a ก่อน**:
- **P4a — Hermes agent**: ตอบลูกค้าอัตโนมัติในแชต (mock LLM) *(สเปคเต็มด้านล่าง)*
- **P4b — admin**: นาทีทอง (flash-sale ตั้งเวลา) · ban (user/ร้าน/สินค้า) · จัดการ caption *(skeleton)*

### SPEC — P4a: Hermes AI agent (auto-reply, mock LLM)
**เคาะแล้ว (brainstorm 2026-07-01):** ทำ P4a ก่อน · **mock LLM** หลัง interface `LlmAgent` (`MockLlmAgent` = จับ intent → เรียก tool → ตอบ templated อิงข้อมูลจริง; เสียบ Claude จริงทีหลัง — ปรัชญาเดียวกับ mock Meta) · **auto-reply + toggle เปิด/ปิดต่อร้าน** + guardrail · **tools = สินค้า/สต็อก/ราคา (catalog) + สถานะออเดอร์ (order)**

**สถาปัตยกรรม:** service ใหม่ `marketplace-agent` (:8086, Boot 3.4 + Postgres `agentdb` + common; template = `marketplace-social`). Reuse internal-key + RestClient.

**Flow (auto-reply):**
1. ลูกค้าส่งข้อความเข้า chat (web buyer `send` / external `inbound`) → chat persist ข้อความ**ฝั่งลูกค้า** + broadcast ให้ทั้งสองฝั่งก่อน แล้วจึง **async (หลัง broadcast, นอก @Transactional)** เรียก `POST {agent}/internal/agent/incoming` *(ข้อความ seller/บอท ไม่ยิง → กัน loop; async กันคำตอบบอทแซงคำถาม + กันค้าง WS thread — ดูรายละเอียด T3)*
2. agent เช็ค `agent_config(shop_id).enabled`; ปิด → no-op
3. `LlmAgent.reply(ctx)` → MockLlmAgent: intent (ราคา/สต็อก, สถานะออเดอร์, อื่นๆ) → เรียก tool → ตอบไทย templated (guardrail: ใช้แต่ tool data; ไม่เจอ → fallback สุภาพ)
4. โพสต์คำตอบ `POST {chat}/internal/chat/reply {conversationId, body}` → chat persist เป็นข้อความบอท (`senderUsername="hermes"`) + broadcast + ถ้า `channel!=web` relay ออก FB (ใช้ของเดิม)

**Data model (agentdb):** `agent_config(id, shop_id UNIQUE, enabled boolean, created_at)` · `agent_reply_log(id, shop_id, conversation_id, body, created_at)`

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `POST /internal/chat/reply` | chat | `X-Internal-Key` | โพสต์ข้อความบอท (sender=hermes) + broadcast + outbound relay |
| `POST /internal/agent/incoming` | agent | `X-Internal-Key` | รับข้อความลูกค้า → MockLLM → ตอบผ่าน chat |
| `POST /api/agent/config` `{enabled}` | agent | SELLER | เปิด/ปิด Hermes (resolve shop via catalog `/shops/me`) |
| `GET /api/agent/config` | agent | SELLER | `{enabled}` |

**tools (agent internal):** CatalogClient.search(q)/product(id) → `/api/catalog/products?q=` , `/products/{id}` · OrderClient.ordersOf(username) → `/api/orders/me` forward `X-Auth-User` (web buyer เท่านั้น; external ไม่มี account → ข้าม)

**Web:** seller dashboard toggle "🤖 Hermes — ตอบลูกค้าอัตโนมัติ" (GET/POST `/api/agent/config`) · chat: ข้อความ `senderUsername="hermes"` โชว์ป้าย 🤖 · i18n TH/EN

**gateway/deploy:** Kong route `/api/agent` · compose +agent +postgres-agent · chat ได้ `AGENT_URL` · **smoke step 13** (เปิด Hermes → ลูกค้าถามราคา → บอทตอบราคาจริงในห้อง ผ่าน Kong; ร้านที่ปิด → ไม่ตอบ)

### P4a-T3 — `/internal/agent/incoming` + MockLlmAgent (รายละเอียด input/output — pin ก่อน build)

**Endpoint** `POST /internal/agent/incoming` · auth `X-Internal-Key` · **ไม่ route ผ่าน Kong**
- **Request** `{conversationId:long, shopId:long, channel:"web"|"fb", customerName:string, buyerUsername:string|null, body:string}`
- **Response** `200 {handled:boolean, replied:boolean}` — `handled`=Hermes เปิดสำหรับร้านนี้ · `replied`=โพสต์คำตอบเข้า chat แล้ว · **ร้านปิด Hermes → `200 {handled:false, replied:false}` (no-op ไม่ยิง chat)** · best-effort (error ภายใน → log + `{handled:true, replied:false}`)

**MockLlmAgent — intent detection** (keyword ไทย/อังกฤษ, case-insensitive, เช็คตามลำดับ PRICE→STOCK→ORDER_STATUS→UNKNOWN)
| intent | trigger keywords | tool | reply template (ไทย) |
|---|---|---|---|
| PRICE | ราคา, กี่บาท, เท่าไหร่, price, cost, how much | `CatalogClient.search(body)` | «{titleTh}» ราคา {priceBaht} บาทค่ะ (เจอหลายชิ้น → top 3 เป็น bullet) |
| STOCK | สต็อก, มีของ, เหลือ, พร้อมส่ง, stock, available | `CatalogClient.search(body)` | «{titleTh}» เหลือ {stockQty} ชิ้นค่ะ · ถ้า 0 → «{titleTh}» หมดสต็อกพอดีค่ะ |
| ORDER_STATUS | ออเดอร์, คำสั่งซื้อ, สถานะ, พัสดุ, order, status, tracking | `OrderClient.ordersOf(buyerUsername)` (web เท่านั้น) | ออเดอร์ #{orderId} สถานะ {status} ค่ะ (ล่าสุด) |
| UNKNOWN | ไม่เข้าเงื่อนไขข้างบน | — | fallback: ขออภัยค่ะ Hermes ตอบได้เฉพาะราคา สต็อก และสถานะออเดอร์ เดี๋ยวผู้ขายมาตอบนะคะ |

- **Query extraction:** ส่ง `body` ทั้งประโยคเป็น `q` (catalog ทำ ILIKE substring อยู่แล้ว — ไม่ตัดคำ)
- **External channel** (`channel="fb"`, `buyerUsername=null`): intent ORDER_STATUS → ไม่มี account → ตอบ fallback (ไม่ query order)
- **Guardrail:** ตอบจาก tool data เท่านั้น · search ไม่เจอ/ว่าง/error → "ไม่พบสินค้าที่ถามค่ะ ลองบอกชื่อสินค้าอีกครั้งนะคะ"
- **Tool I/O:** `CatalogClient.search(q)` → `GET /api/catalog/products?q={q}` → ใช้ `items[].{id, titleTh, priceBaht, stockQty}` · `OrderClient.ordersOf(u)` → `GET /api/orders/me` forward `X-Auth-User:{u}` + `X-Auth-Role:BUYER` → `orders[].{orderId, status}`
- **โพสต์คำตอบ:** `POST {chat}/internal/chat/reply {conversationId, body}` (X-Internal-Key) + เขียน `agent_reply_log(shop_id, conversation_id, body, created_at)`
- **Ordering fix (บั๊ก audit 2026-07-02):** chat เรียก `agent.incoming` **async หลัง broadcast** (ย้ายออกจาก `send()`/`inbound()` @Transactional ไปหลัง `broadcaster.deliver`) + `AgentClient` RestClient ตั้ง connect/read timeout ~2s → คำตอบบอทไม่แซงคำถาม + ไม่ค้าง WS thread + `last_message_at` ไม่ถูก overwrite ด้วยค่าเก่า

**Test (MockWebServer stub catalog/order/chat):** PRICE→ราคาจริงจาก stub · STOCK→เหลือ N (และเคส 0) · ORDER_STATUS(web)→สถานะจริง · UNKNOWN→fallback · external+ORDER_STATUS→fallback · **disabled shop→`{handled:false}` ไม่ยิง chat/reply** · search ว่าง→guardrail reply
**smoke step 13 (ทำใน T4):** reuse FB inbound แบบ step 11 ผ่าน Kong — simulate "ราคาเท่าไหร่" เข้าร้านที่เปิด Hermes → poll `GET messages` ~3s → มี message `senderUsername="hermes"` ที่มีเลขราคาจริงของสินค้า seed · ร้านปิด Hermes → หลัง 3s ไม่มี message hermes

### P4a-T5 — web: Hermes toggle + ป้ายบอท (รายละเอียด input/output — pin ก่อน build)

**หน้า `/seller` — component ใหม่ `HermesToggle` (การ์ดวางต่อจาก FbConnect, แสดงเมื่อมีร้านแล้วเท่านั้น)**
- **โหลด:** `GET /api/agent/config` (SELLER token ผ่าน Kong) → `200 {enabled:boolean}` · error/ยังโหลดไม่เสร็จ → แสดง loading, toggle กดไม่ได้
- **สลับ:** `POST /api/agent/config {enabled:!current}` → `200 {enabled:boolean}` → อัปเดต state จาก response (ไม่เดาเอง) · ระหว่างรอ → ปุ่ม disabled · error → ข้อความ `t.hermes.failed` (pattern เดียวกับ FbConnect)
- **State:** `enabled: boolean | undefined`(undefined=loading) · `busy` · `msg`
- **UI:** CardTitle `t.hermes.title` ("Hermes — บอทช่วยตอบแชต") + คำอธิบาย `t.hermes.hint` (ตอบราคา/สต็อก/สถานะออเดอร์อัตโนมัติ) + ปุ่มสลับสถานะ: เปิดอยู่ → ปุ่ม outline "ปิดบอท" + ป้ายเขียว "เปิดอยู่" · ปิดอยู่ → ปุ่ม primary "เปิดบอท"

**หน้า `/chat` — ป้ายบอท**
- เงื่อนไข render ต่อ message: `m.senderUsername === 'hermes'` → บับเบิลฝั่งซ้าย (ไม่ใช่ mine อยู่แล้ว) เพิ่มหัวบรรทัดเล็ก `🤖 {t.chat.bot}` เหนือ body + พื้นหลังต่างจากคนจริง (`bg-accent`) — ทั้งฝั่ง buyer และ seller เห็นเหมือนกัน
- ไม่มี state ใหม่ (เช็คตอน render เท่านั้น)

**i18n (th/en):** `hermes.{title, hint, enable, disable, on, failed}` + `chat.bot`
**Verify:** `npm run build` เขียว · ผ่าน Kong จริง: toggle ใน UI → `GET /api/agent/config` คืนค่าตรงปุ่ม (สลับ 2 รอบ) · message จาก hermes ใน chat มีป้าย 🤖 (spot-check DOM ผ่าน web :3000)

**แตกงาน (P4a-T1..T5)**
- **T1 [BE]** scaffold `marketplace-agent` (:8086, agentdb, common) + `agent_config` + `POST/GET /api/agent/config` (SELLER) + CatalogClient/OrderClient (read-only tools) → test
- **T2 [BE]** chat: `POST /internal/chat/reply` (บอท reply + broadcast + outbound relay) + `AgentClient` + ยิง agent เมื่อมีข้อความ**ฝั่งลูกค้า** (best-effort, กัน loop) + `AGENT_URL` → test
- **T3 [BE]** agent: `POST /internal/agent/incoming` → `LlmAgent` + `MockLlmAgent` (intent→tools→templated, guardrail) → post via ChatClient + `agent_reply_log` → test (MockWebServer stub catalog/order/chat)
- **T4 [GW/Infra]** Kong route `/api/agent` + compose +agent +postgres-agent + chat `AGENT_URL` + run.sh build agent + **smoke step 13**
- **T5 [FE]** web: seller Hermes toggle + ป้าย 🤖 บนข้อความบอท + i18n

**Non-goals (P4a):** เรียก LLM/Claude จริง (interface พร้อม, mock ก่อน) · streaming · memory ข้าม turn · admin tools (P4b) · rate-limit คำตอบบอท · multi-step tool planning

**Phase 5 — ทีหลัง** · จ่ายเงินจริง (PromptPay/บัตร) · รีวิว/ดาว · wishlist · ระบบแนะนำสินค้า

---

## การตรวจสอบรวม (per phase)
1. `marketplace-deploy/run.sh --build -d` + `smoke.sh` (P0: register→login→me · P1: register→become-seller→เปิดร้าน→
   ลงสินค้า stock=N→ผู้ซื้อใส่ตะกร้า→checkout→stock=N-1→ผู้ขายเห็นออเดอร์)
2. **oversell:** checkout ขนาน 2 อันบน stock=1 → สำเร็จ 1, อีกอัน 409
3. web e2e ครบลูป + สลับ TH/EN · ทุก service มี Testcontainers test
4. (เมื่อ deploy จริง) รายงาน URL ทุกเฟส

## จุดเปิด / ความเสี่ยง (ไม่บล็อก P0/P1)
- **FB/IG** ต้อง Meta Business verification + Graph API review (เริ่ม FB Page ก่อน) → เคาะก่อน P3
- **Hermes** เลือกโมเดลไทย + งบ LLM + guardrail → เคาะก่อน P4
- repo layout = multi-repo (`marketplace-common` publish GitHub Packages บัญชี taskeendev)
