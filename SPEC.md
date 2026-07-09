# SPEC — Omnichannel Marketplace (greenfield, multi-repo)

> **สำหรับ agent ที่ลงมือทำ:** ใช้ superpowers:writing-plans (task ทีละ 2–5 นาที, TDD, commit ถี่). task ใช้ checkbox.
> เขียนใหม่ทั้งหมด ไม่แตะ lab เดิม. P0–P2 + P3 + P4a = สเปคเต็ม (task + API input/output). P4b/P5 = โครง (ลง API ตอนเริ่มแต่ละเฟส).

## ข้อสรุปที่ยืนยันแล้ว (ผู้ใช้เคาะเอง)

greenfield ทั้งหมด · **Java 21 + Spring Boot 3.4.x + Maven** · **React 19 + Vite + TS + Tailwind + shadcn** ·
**Kong** gateway · **multi-repo** `marketplace-*` ใต้ GitHub **taskeendev** (common lib ผ่าน GitHub Packages) ·
role **BUYER/SELLER/ADMIN** · **Postgres ต่อ service + Flyway** · catalog = สต็อกก้อนเดียว (atomic/idempotent) ·
**P1 รูป = URL อย่างเดียว** · **P0/P1 รัน docker-compose ในเครื่อง** (deploy จริงทีหลัง) · i18n typed TH/EN ·
JWT(HS512) access ใน memory + refresh ใน HttpOnly cookie · cart ฝั่ง server · search P1 = ILIKE substring · ฿ THB ·
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
| `POST /api/auth/logout` | cookie | — (refresh cookie) | `204` + Set-Cookie clear refresh | — |
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
- [ ] **P1-T6: public browse/search** — `GET /products` (q + categoryId + paging, ILIKE substring บน title TH/EN), `GET /products/{id}` · verify: ค้นหาเจอ, สินค้า banned/draft ไม่โผล่
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
| `GET /api/catalog/shops/{slug}` | public | — | `200 {shop}` (สินค้า: `GET /api/catalog/products?shopId=`) | 404 |
| `POST /api/catalog/shops/me/products` | SELLER | `{categoryId, titleEn, titleTh, descEn, descTh, priceBaht, imageUrls:[], stockQty, status?}` | `201 {id, …, stockQty}` | 400/403 |
| `PUT /api/catalog/shops/me/products/{id}` | SELLER | (เหมือนสร้าง; stockQty = ตั้งใหม่) | `200 {product}` | 400/403/404 |
| `GET /api/catalog/shops/me/products` | SELLER | — | `200 [{product + stockQty}]` | 403 |
| `GET /api/catalog/products` | public | `?q=&categoryId=&shopId=&page=&size=` | `200 {items:[{id, titleEn, titleTh, priceBaht, imageUrl, shopName, stockQty}], page, total}` | — |
| `GET /api/catalog/products/{id}` | public | — | `200 {id, shop, category, titleEn/Th, descEn/Th, priceBaht, images:[], stockQty, status}` | 404 |
| `POST /api/catalog/inventory/decrement` | internal | `{items:[{productId, qty}], idempotencyKey}` | `200 {ok:true}` | `409 {outOfStock:[productId]}` |

**order**
| Method/Path | สิทธิ์ | input | output | error |
|---|---|---|---|---|
| `GET /api/orders/cart` | BUYER | — | `200 {items:[{productId, title, priceBaht, qty, lineTotal, stockQty}], total}` | 401 |
| `POST /api/orders/cart/items` | BUYER | `{productId, qty}` | `200 {cart}` | 400 |
| `PUT /api/orders/cart/items/{productId}` | BUYER | `{qty}` | `200 {cart}` | 400/404 |
| `DELETE /api/orders/cart/items/{productId}` | BUYER | — | `200 {cart}` | — |
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
| client→ | `{type:"ping"}` (heartbeat, D6) | authed แล้วเท่านั้น → ตอบ `{type:"pong"}`; ก่อน authed = ปิด 4401 ตามเดิม |
| →client | `{type:"pong"}` (D6) | ตอบ heartbeat; ไม่ persist ไม่ side-effect |
| →client | `{type:"error", detail}` | error อื่นๆ |

**D6 keep-alive — client `chatSocket.ts` (MAR-59):** WS หลุด (เน็ตวูบ / Kong idle-timeout / token หมด) ต้องต่อกลับเองไม่ต้อง refresh หน้า
- **reconnect:** close ที่ไม่ได้ตั้งใจ → ต่อใหม่ · backoff 1→2→4→8s (cap 10s) · reset counter+backoff เมื่อได้ `authed`
- **re-auth:** close code **4401** (token verify ไม่ผ่าน) → `refresh()` (rotate refresh-cookie → access token ใหม่) ก่อนต่อใหม่
- **heartbeat:** หลัง `authed` ส่ง `{type:"ping"}` ทุก **25s**; ไม่ได้ `pong` ใน **10s** → force close → เข้า reconnect (จับ silent-death ที่ `onclose` ไม่ยิง; อิง Kong idle ~60s)
- **give up → สถานะ "หลุดการเชื่อมต่อ":** (ก) `refresh()` ล้มเหลว (refresh cookie หมด) **หรือ** (ข) reconnect ครบ **10 ครั้ง** ยังไม่ `authed` → หยุด reconnect + เคลียร์ timer + แจ้ง caller ผ่าน `onDisconnected` → `Chat.tsx` แสดงแบนเนอร์ "หลุดการเชื่อมต่อ" (ไม่เด้ง login)
- **deliberate close:** `close()` (ออกจากหน้า) → ไม่ reconnect + เคลียร์ timer ทั้งหมด
- **side-effects:** ping/pong ไม่ persist/notify/audit · reconnect = re-register session ใน SessionRegistry (session เก่าถูกถอดโดย `afterConnectionClosed`) → ไม่มี duplicate delivery · msg ที่พลาดช่วงหลุด = out-of-scope (msg ใหม่มาเองหลัง re-register)
- **KPI:** D6-a → `ws_check.py` ยิง `ping` ได้ `pong` ผ่าน Kong · D6-b → `npm test` (Vitest + fake WebSocket) assert reconnect / refresh-on-4401 / ping-sent / no-pong→reconnect / give-up-after-10

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

**Mock Meta:** Send = mock client หลัง interface (บันทึก+log; เสียบ Graph จริงทีหลัง) · inbound = `POST /api/social/simulate-inbound` (SELLER) จำลอง webhook (smoke/demo) · connection = "เชื่อม FB Page (mock)" ผูก `pageId↔shop` + fake token

**Data model**
- `chat.conversation`: +`channel` default `'web'`, +`external_id` null, +`display_name` null · unique ใหม่ `(shop_id, channel, external_id)` (web คงเดิม `(buyer_username, shop_id)`)
- `chat.message`: inbound external → `sender_username` null = customer · unread ของ seller = นับฝั่ง customer หลัง `last_read`
- `social`: `page_connection(shop_id, page_id, page_token, channel)` · `outbound_log(page_id, external_id, body, created_at)`

**Internal/REST API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `GET /webhooks/fb` | social | public | Meta webhook verify (echo `hub.challenge`) |
| `POST /webhooks/fb` | social | (Meta sig) | รับ event → normalize → เรียก chat `/internal/inbound` |
| `POST /api/social/simulate-inbound` | social | SELLER (เจ้าของ page) | จำลอง FB inbound (dev/smoke) |
| `POST /internal/social/send` | social | `X-Internal-Key` | mock Meta Send + บันทึก `outbound_log` |
| `POST /internal/chat/inbound` | chat | `X-Internal-Key` | find-or-create external conversation + persist + broadcast WS |
| `POST /api/social/connections` | social | SELLER | เชื่อม FB Page (mock) ผูก `pageId↔shop` |

**Web:** `/chat` แสดง badge ช่อง (web/FB) + ชื่อ external contact (seller ตอบเหมือนเดิม) · seller dashboard: "เชื่อม Facebook Page (mock)" + ปุ่ม dev "จำลองข้อความ FB เข้า"

**gateway/deploy:** Kong route `/api/social` + `/webhooks/fb`→social · compose +social +postgres-social · **smoke step 11:** simulate inbound → โผล่ใน chat ของ seller → seller ตอบ → `outbound_log` มี record (ทะลุ Kong)

**แตกงาน (P3a-T1..T6 — ทำทีละ task + test ก่อน done)**
- **T1 [BE]** scaffold `marketplace-social` (:8085, Postgres+Flyway+common) + `page_connection` + webhook verify (GET challenge) → boot + test
- **T2 [BE]** chat extend conversation/message (channel/external) + `POST /internal/chat/inbound` (find-or-create external + broadcast WS) → test
- **T3 [BE]** social: receive `POST /webhooks/fb` → normalize → เรียก chat `/inbound` + `POST /api/social/simulate-inbound` → test
- **T4 [BE]** outbound: seller ตอบในห้อง fb → chat เรียก social `/internal/send` → mock send + `outbound_log` → test
- **T5 [GW]** Kong route `/api/social` + `/webhooks/fb` · compose +social +postgres-social · run.sh build social · **smoke step 11**
- **T6 [FE]** web: channel badge + external name ใน `/chat` + "connect FB (mock)" + ปุ่ม dev simulate

### SPEC — P3a debt: SD6 (MAR-65) + SD7 (MAR-66) — real page token + display_name ผ่าน Graph (mock)
**เคาะแล้ว 2026-07-05:** รวม Graph calls เป็น seam เดียว `FbGraph` + `MockFbGraph` (ตาม `auth.GraphClient`; real client เสียบทีหลัง gated by `fb.graph-url/app-id/app-secret`) · `code`=optional (server-gen ถ้าไม่ส่ง → **web ไม่ต้องแตะ**) · ทั้งคู่ social · BE, 2 task/2 PR, **SD6 ก่อน SD7**

**FbGraph seam** (interface + `MockFbGraph`)
| method | ใช้โดย | mock behavior |
|---|---|---|
| `String exchangePageToken(String code, String pageId)` | SD6 connect | token derive จาก code (deterministic, code ต่าง→token ต่าง) ไม่ hardcode 'mock' |
| `Optional<String> fetchProfileName(String pageToken, String psid)` | SD7 inbound | คืน `"Customer <last4 psid>"` (ไม่ขึ้นต้น "FB ") |

**SD6 — page token:** `ConnectRequest` +`code` (optional) · `ConnectionService.connect(user, role, pageId, code)`: `code = req.code() ?? "mockcode-"+pageId` → `token = fbGraph.exchangePageToken(code, pageId)` → save/update (re-point เดิม → `setPageToken` ค่าใหม่ด้วย) · **เลิกใช้** `"mock-token-"+pageId`
- **KPI (integration test social):** connect ด้วย code → `page_token` ≠ 'mock' & len>0 · exchange 2 code ต่างกัน → 2 token ต่างกัน

**SD7 — display_name:** `WebhookService.relay`: `displayName` null/blank → `fbGraph.fetchProfileName(conn.pageToken, externalId)` → ใช้ชื่อ · error/empty → fallback `"FB "+last4` (try/catch, ไม่ crash) · simulate path (displayName != null) → ใช้ค่าเดิม Graph ไม่ถูกเรียก
- **KPI (integration test social):** mock คืน "สมชาย ใจดี" → `display_name`="สมชาย ใจดี" · 3 inbound → ไม่มีห้องขึ้นต้น "FB " · mock throw → fallback "FB <id>" + ไม่ 500

**Real Graph hookup (BLOCKED — รอ Meta verify, card แยกใน JIRA):** seam พร้อมแล้ว (`FbGraph` + `MockFbGraph` + signature verify จริง + tests). งานที่เหลือ:
- **โค้ด (dev):** `RealFbGraph implements FbGraph` (`@ConditionalOnProperty(name="fb.graph-url")`, ใช้ `RestClient` แบบ `auth.GraphClient`): `exchangePageToken` = `/oauth/access_token`→`/me/accounts` (page token long-lived) · `fetchProfileName` = `GET /{psid}?fields=name` · `MockFbGraph` +`@ConditionalOnMissingBean(FbGraph.class)` (default เมื่อไม่มี real) · `.env`: `fb.graph-url/app-id/app-secret/redirect-uri`
- **Meta (มนุษย์เท่านั้น = blocker):** สมัคร Meta app + Business Verification + App Review (`pages_messaging`, `pages_read_engagement`) → ได้ credential จริง
- **acceptance:** ใส่ real creds → connect page จริง → page_token เป็น long-lived จริง (ไม่ใช่ `pat-`) · inbound จาก FB user จริง → display_name = ชื่อ profile จริง · `fb.graph-url` ว่าง → mock ยัง default (28 tests เดิมเขียว)

### SPEC — Web FB Login page-connect flow (real OAuth) [card แยก, ต่อจาก MAR-101]
**เคาะแล้ว 2026-07-05:** seller **เลือก page ใน UI** (multi-page) · เก็บปุ่ม mock connect + simulate ไว้**คู่** real (config-gate) · ใช้จริงได้เมื่อมี RealFbGraph (MAR-101) + real Meta creds
**ปม:** real OAuth `code` ใช้ครั้งเดียว + ตอนกด connect ยังไม่รู้ pageId → **exchange ครั้งเดียวใน callback** → เก็บ page tokens ชั่วคราว server-side → seller เลือก pageId → promote เป็น connection (**ไม่ส่ง token ออก browser**)
- **seam:** `FbGraph` +`List<Page> pagesForCode(code)` (code→userToken→/me/accounts → `[{pageId,name,pageToken}]`) · `MockFbGraph` คืน 1 fake page · `exchangePageToken` เดิมคงไว้ (mock manual path SD6)
- **data (social):** `pending_page_connection(id, username, page_id, name, page_token, created_at)` อายุสั้น ~10 นาที → เลือกแล้ว promote → `page_connection`
- **endpoints (social, SELLER):** `GET /api/social/oauth/fb/connect-url` = FB dialog URL (scope `pages_show_list,pages_messaging` — ตัด `pages_read_engagement` ที่ไม่ได้ใช้ + FB reject ถ้าแอปไม่มีสิทธิ์) + state cookie **`SameSite=None; Secure`** (ต้องรอด cross-site OAuth redirect; Lax โดน drop) · `POST /api/social/oauth/fb/callback {code,state}` = validate state → `pagesForCode` → upsert pending → คืน `{pages:[{pageId,name}]}` (ไม่มี token) · `POST /api/social/connections {pageId}` (extend) = มี pending(username,pageId) → connect ด้วย pending token (promote); ไม่มี → mock path `{pageId,code}` เดิม
- **web:** FbConnect +ปุ่ม "Connect Facebook" → connect-url → redirect FB → route `/oauth/fb/page-callback` (?code&state) → POST callback → แสดง list page → seller เลือก → POST `/connections {pageId}` → โชว์ที่เชื่อม · ปุ่ม mock+simulate เดิมคงไว้ · i18n th/en
- **gateway:** Kong `/api/social` ครอบ subpath แล้ว (ไม่แตะ) · redirect-uri whitelist ใน Meta app · **config:** fb.app-id/redirect-uri (OAuth เวิร์กเฉพาะมี real Meta app → flow นี้ real-only, mock ใช้ปุ่มเดิม)
- **แตกงาน:** T1 [BE] `pagesForCode` + pending table + 3 endpoints + state CSRF → integration test · T2 [FE] button+callback+pick UI+i18n → build
- **KPI:** integration test social — connect-url มี scope+state · callback (test-double `pagesForCode`) valid → คืน pages + pending saved · state ผิด → 403 · POST `/connections {pageId}` หลัง callback → PageConnection มี pending token · (web e2e จริง = รอ real creds)

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
- **P4b — admin + seller tools**: นาทีทอง (flash-sale ตั้งเวลา) · ban (user/ร้าน/สินค้า) · จัดการ caption *(สเปคเต็มด้านล่าง)*

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

### SPEC — P4b: admin + seller tools (flash-sale · ban/moderation · caption)
**เคาะแล้ว (brainstorm 2026-07-05):** ครบ 3 feature · **ADMIN role + SELLER ผสม** (ADMIN=moderation ทั้งแพลตฟอร์ม; SELLER=flash-sale+caption ของร้านตัวเอง) · **ต่อยอด service เดิม ไม่มี service ใหม่** · flash-sale=ราคาตายตัว · banned user JWT เดิมปล่อยหมดอายุเอง (ไม่มี revocation list — stateless, ยอมรับใน lab)

**Role:** เพิ่ม `ADMIN` ใน role · **seed admin user** (username `admin`, password จาก env `ADMIN_SEED_PASSWORD`, role=ADMIN) ผ่าน Flyway · auth ออก JWT `role=ADMIN` · Kong route `/api/admin/**` (ต้องมี token; service เช็ค `hasRole('ADMIN')`)

**Data model (เพิ่ม, Flyway ต่อ service):**
- auth `app_user`: +`banned boolean not null default false`
- catalog `shop`: +`banned boolean not null default false` · `product`: +`banned boolean not null default false` *(แยกจาก `active` ที่ seller คุมเอง — `banned`=admin คุม)* · ตาราง `flash_sale(id, product_id bigint UNIQUE FK, sale_price_baht int not null, starts_at timestamptz not null, ends_at timestamptz not null, created_at)`
- social `product_caption(id, shop_id bigint, product_id bigint UNIQUE, caption_th text, caption_en text, updated_at)`

**Effective price (flash-sale):** catalog คำนวณ server-side — `now ∈ [starts_at, ends_at)` → `sale_price_baht` ไม่งั้น `price_baht`. ทุกที่ที่คืนราคา (browse/detail/lookup) คืน **effective price ในฟิลด์ `priceBaht` เดิม** + บล็อก `flashSale:{salePriceBaht, endsAt}` เมื่อ active (null เมื่อไม่ active) → **checkout (order→catalog `/products/{id}`) ใช้ราคาลดอัตโนมัติโดยไม่ต้องแก้ order** · badge/countdown ใช้ `flashSale`

**Ban enforcement:** banned product **หรือ** product ของ banned shop → หายจาก browse (`/api/catalog/products`) + lookup `/products/{id}` →404 → checkout →400 "product unavailable" (reuse ของเดิม) · banned user → auth login →403 `account_banned`

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `POST /api/admin/users/{username}/ban` · `/unban` | auth | ADMIN | set/clear `banned` |
| `GET /api/admin/users?banned=true` | auth | ADMIN | list banned users |
| `POST /api/admin/shops/{id}/ban` · `/unban` | catalog | ADMIN | set/clear shop `banned` |
| `POST /api/admin/products/{id}/ban` · `/unban` | catalog | ADMIN | set/clear product `banned` |
| `POST /api/catalog/shops/me/products/{id}/flash-sale` `{salePriceBaht,startsAt,endsAt}` | catalog | SELLER (own) | upsert flash-sale (validate: salePrice<price, starts<ends, ends>now) |
| `DELETE /api/catalog/shops/me/products/{id}/flash-sale` | catalog | SELLER (own) | ยกเลิก |
| `GET /api/social/products/{id}/caption` | social | SELLER (own) | `{captionTh,captionEn}` (null ถ้ายังไม่ตั้ง) |
| `PUT /api/social/products/{id}/caption` `{captionTh,captionEn}` | social | SELLER (own) | upsert caption |

*(browse/detail คืน `priceBaht`=effective + `flashSale` — ไม่มี endpoint ใหม่)* · caption: social sync (P3) ใช้ `caption_th` ถ้ามี ไม่งั้น title เดิม

**แตกงาน (P4b-T1..T6)** — feature-branch+PR ต่อ task, service tag + 1 KPI ต่อตัว
- **T1 [auth]** ADMIN role + seed admin (Flyway) + `app_user.banned` + `/api/admin/users/{u}/ban|unban` + `GET /api/admin/users?banned` + login เช็ค banned→403 → test · **KPI:** ban user → login 403; unban → login 200
- **T2 [catalog]** `shop.banned`+`product.banned` + `/api/admin/shops|products/{id}/ban|unban` (ADMIN) + enforcement (browse exclude banned + banned-shop products; lookup→404) → test · **KPI:** ban product → หายจาก `/products` list + `/products/{id}`→404 + checkout→400
- **T3 [catalog]** `flash_sale` + seller upsert/delete `/shops/me/products/{id}/flash-sale` (validate) + effective price ใน browse/detail/lookup + `flashSale` block → test · **KPI:** ตั้ง flash-sale active → `/products/{id}`.priceBaht=salePrice + checkout ใช้ราคาลด; หมดเวลา → ราคาปกติ
- **T4 [social]** `product_caption` + seller GET/PUT `/api/social/products/{id}/caption` + sync ใช้ caption override title → test · **KPI:** ตั้ง caption → sync ส่ง caption_th (ไม่ใช่ title) ไป FB stub
- **T5 [web]** admin ban console (route `/admin`, ADMIN-only) + seller flash-sale form + caption editor (หน้า product ของ seller) + buyer flash-sale badge+ราคาลด+นับถอยหลัง · i18n · verify `npm run build` + ผ่าน Kong
- **T6 [gateway/deploy]** Kong route `/api/admin/**` + seed admin env + **smoke steps** (flash-sale ราคาลดตอน checkout · admin ban product→browse หาย/checkout 400 · admin auth: ไม่มี ADMIN → 403)

**Non-goals (P4b):** admin จัด flash-sale event ทั้งแพลตฟอร์ม (seller-driven เท่านั้น) · % discount (ราคาตายตัว) · JWT revocation ตอน ban (ปล่อยหมดอายุ) · flash-sale ซ้อน/หลายช่วงต่อสินค้า (1 ต่อสินค้า) · audit log admin actions · appeal/notification ตอนโดน ban · schedule แบบ recurring

### SPEC — P5: จ่ายเงิน (mock) + รีวิว/ดาว + wishlist
**เคาะแล้ว (brainstorm 2026-07-05):** payment + reviews + wishlist (เลื่อน recommendations) · **จ่ายเงิน mock behind interface** (ปรัชญาเดียวกับ mock Meta/LLM — `PaymentProvider` + `MockPaymentProvider`, จำลอง PromptPay QR/บัตร + confirm, ไม่ต้อง creds จริง, เสียบ Omise/Stripe ทีหลัง) · **payment-service ใหม่** · reviews→catalog · wishlist→order

**สถาปัตยกรรม:** service ใหม่ `marketplace-payment` (:8087, Boot 3.4 + Postgres `paymentdb` + common; template = `marketplace-agent`). reuse internal-key + RestClient.

**เปลี่ยน order lifecycle (หัวใจ P5):** checkout → order **`pending`** (เดิม instant `paid_mock`) → buyer จ่าย → **`paid`** → seller `shipped` → `done`. `paid_mock` เลิกใช้ (แทนด้วย pending+paid). seller ship ได้เฉพาะ order `paid`.

**Flow จ่ายเงิน:**
1. buyer checkout (order) → order `pending` (คืน orderId)
2. `POST /api/payments {orderId, method}` → payment ดึง order ผ่าน internal (`GET {order}/internal/orders/{id}` → buyer/total/status), validate (buyer ตรง + status=pending + ยังไม่จ่าย) → สร้าง payment(status=pending) → `MockPaymentProvider.initiate` → PromptPay: `{qrData}` จำลอง / card: awaiting
3. `POST /api/payments/{id}/confirm` (buyer กด "จ่ายแล้ว") → `MockPaymentProvider.confirm` (mock สำเร็จเสมอ; จริง = webhook) → payment `paid` → แจ้ง order `POST {order}/internal/orders/{orderId}/paid` (X-Internal-Key) → order `paid`

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `POST /api/payments` `{orderId, method:"promptpay"\|"card"}` | payment | BUYER | สร้าง payment สำหรับ order ของตัวเอง → `{paymentId, status:"pending", method, qrData?}` |
| `POST /api/payments/{id}/confirm` | payment | BUYER (own) | mock จ่าย → payment `paid` + แจ้ง order → `{paymentId, status:"paid"}` |
| `GET /internal/orders/{id}` | order | X-Internal-Key | `{buyerUsername, totalBaht, status}` (payment ใช้ validate+amount) |
| `POST /internal/orders/{id}/paid` | order | X-Internal-Key | order `pending`→`paid` (idempotent) |
| `GET /internal/orders/purchased?buyer=&productId=` | order | X-Internal-Key | `{purchased:bool}` (มี order paid/shipped/done ที่มีสินค้านั้น) |
| `POST /api/catalog/products/{id}/reviews` `{stars:1-5, body}` | catalog | BUYER (ซื้อแล้ว) | เช็ค purchased ผ่าน order → upsert review (1/คน/สินค้า) |
| `GET /api/catalog/products/{id}/reviews` | catalog | public | `{avgStars, count, items:[{buyer, stars, body, createdAt}]}` |
| `GET /api/orders/wishlist` | order | BUYER | `[productId]` |
| `POST /api/orders/wishlist` `{productId}` | order | BUYER | เพิ่ม (idempotent) |
| `DELETE /api/orders/wishlist/{productId}` | order | BUYER | ลบ |

*(product detail (catalog) += `avgStars`, `reviewCount`)*

**Data model:**
- payment `payment(id, order_id UNIQUE, buyer_username, amount_baht, method, status[pending|paid|failed], provider_ref, created_at, paid_at)`
- catalog `review(id, product_id, buyer_username, stars smallint CHECK 1..5, body text, created_at, UNIQUE(product_id, buyer_username))`
- order `wishlist(id, buyer_username, product_id, created_at, UNIQUE(buyer_username, product_id))` · order.status enum +`pending`,`paid` (retire `paid_mock`)

**แตกงาน (P5-T1..T6)** — feature-branch+PR ต่อ task, service tag + 1 KPI
- **T1 [payment]** scaffold `marketplace-payment` (:8087, paymentdb) + `PaymentProvider`+`MockPaymentProvider` + `POST /api/payments` + `/{id}/confirm` + `GET /{id}` + OrderClient (internal get + notify paid) → test (MockWebServer stub order) · **KPI:** create payment → confirm → payment status=paid + order-notify ยิง
- **T2 [order]** checkout → `pending` (แทน paid_mock) + `GET /internal/orders/{id}` + `POST /internal/orders/{id}/paid` + ship guard (advance ได้เฉพาะ `paid`) → test · **KPI:** checkout → pending; internal/paid → paid; seller ship บน pending → 400/409
- **T3 [order]** wishlist `wishlist` + GET/POST/DELETE `/api/orders/wishlist` → test · **KPI:** add → GET มี; delete → หาย; ซ้ำ → idempotent
- **T4 [catalog]** `review` + POST/GET `/api/catalog/products/{id}/reviews` (purchased-check via order internal) + avgStars/reviewCount ใน detail → test · **KPI:** ยังไม่ซื้อ → review 403; ซื้อแล้ว → review 201 + avgStars อัปเดต
- **T5 [web]** payment page (`/pay/{orderId}` QR/บัตร + "จ่ายแล้ว" → order paid) + review UI (ดาว+ฟอร์ม บน product ถ้าซื้อแล้ว) + wishlist ❤️ + หน้า `/wishlist` + i18n · verify `npm run build` + ผ่าน Kong
- **T6 [gateway/deploy]** Kong route `/api/payments` + payment-service+postgres-payment ใน compose/k8s + **smoke steps** (checkout→pending→pay→paid→seller ship · review หลังซื้อ · wishlist add/remove)

**Non-goals (P5):** gateway จ่ายเงินจริง (mock behind interface; Omise/Stripe เสียบทีหลัง) · async webhook จริง (confirm = buyer กด) · refund/void · แนะนำสินค้า (recommendations เลื่อน) · review รูปภาพ/reply · แก้/ลบ review (upsert เท่านั้น) · partial payment/หลาย method ต่อ order · wishlist batch-get (คืน productIds, web fetch เอง)

---

## เฟส Ops — deploy จริง (local k8s) + CI/CD + observability + infra debt (เคาะ 2026-07-04)

**เป้าหมาย:** ยกสแตกจาก docker-compose (local orchestration) ขึ้น **kubernetes จริง (local)** + มี **CI/CD** อัตโนมัติ + **observability เต็มระบบ** + ปิด infra debt 3 ตัว (I1, D4, CMN1). โฟกัส = resume DevOps/SRE, zero-cost, รันบนเครื่องได้จริง

**การตัดสินใจ (default — ไม่ถามซ้ำ):**
- **k8s local = `kind`** (single binary, ใกล้ cluster จริง, สร้าง/ทิ้งเร็ว, ใช้ใน CI ได้)
- **คง Kong ไว้** เป็น Deployment (DB-less, `kong.yml` ผ่าน ConfigMap) — **ไม่แทนด้วย Ingress-nginx** เพราะจะเสีย custom plugin `jwt-hs512` + Origin allowlist + header inject. cluster Ingress → Kong Service → services
- **Prometheus/Grafana เขียน manifest เอง** (Deployment + ConfigMap + provisioned dashboards) ไม่ใช้ kube-prometheus-stack Helm — เรียนรู้มากกว่า + เบากว่า; reuse `~/monitor/prometheus.yml` เป็นฐาน
- **CMN1 = HMAC-signed headers** (Kong เซ็น X-Auth-* + ts; service verify) — ไม่ใช่ mTLS/service-mesh (future)
- **CI = GitHub Actions**, 1 workflow/repo; **images → GHCR** `ghcr.io/taskeendev/*` tag `sha-<short>` + `latest`
- k8s manifests อยู่ใน `marketplace-deploy/k8s/` (kustomize) — repo เดิม ไม่แตก repo ใหม่

**แตกงาน (Ops-T1..T8)** — dependency: T1→T2→T3→T4→(T5,T6,T7)→T8
- [ ] **Ops-T1 [Infra] I1: common → GitHub Packages** — `marketplace-common` เพิ่ม `distributionManagement` (GitHub Packages) + workflow publish (on push main / tag) + repo ที่ depend เพิ่ม `settings.xml`/repo config auth ด้วย `GITHUB_TOKEN` · verify: build repo ที่ depend common บน runner ที่**ไม่มี** `~/.m2` common → resolve จาก Packages ผ่าน (จำลอง: `mvn -Dmaven.repo.local=$(mktemp -d) test` เขียว)
- [ ] **Ops-T2 [Infra] CI build+test ทุก repo** — `.github/workflows/ci.yml` ต่อ service repo: checkout → setup-java 21 → `mvn -B verify` (Testcontainers บน ubuntu runner มี Docker) · web: `npm ci` + `npm run build` · common จาก Packages · verify: เปิด PR → check เขียว; ทำเทสพังใน branch → check แดง (บล็อก merge)
- [ ] **Ops-T3 [Infra] Docker images → GHCR** — workflow build+push ต่อ service (docker/build-push-action) on merge main; login GHCR ด้วย `GITHUB_TOKEN`; tag `sha-<short>` + `latest` · verify: merge → image ขึ้น `ghcr.io/taskeendev/marketplace-<svc>`; `docker pull` sha tag ได้
- [ ] **Ops-T4 [Infra] k8s base manifests (kind)** — `k8s/`: namespace `marketplace`; ConfigMap (env ไม่ลับ) + Secret (JWT_SECRET, INTERNAL_API_KEY, db creds); postgres ต่อ service = StatefulSet + PVC + Service; service Deployment (image GHCR) + Service + **liveness/readiness probe** (`/health`) + resources requests/limits; Kong Deployment + ConfigMap(kong.yml) + Service; Ingress → Kong · verify: `kind create cluster` + `kubectl apply -k k8s/` → ทุก pod `Ready` + port-forward Kong → **`smoke.sh` (ชี้ Ingress/port-forward) ผ่านครบ 13 step**
- [ ] **Ops-T5 [BE/Infra] D4: Redis WS pub/sub + chat 2 replica** — chat: broadcaster publish message → Redis channel → ทุก instance subscribe → ส่งเข้า WS session ของ instance ตัวเอง (registry ยัง in-memory ต่อ instance, fan-out ข้าม instance ผ่าน Redis); +Redis (Deployment/StatefulSet); k8s chat `replicas: 2` · verify: test (Testcontainers Redis) publish instance A → instance B ได้รับ; k8s: 2 client คนละ pod ส่งถึงกัน (extend smoke WS step)
- [ ] **Ops-T6 [Infra] Observability เต็มระบบ** — `micrometer-registry-prometheus` ทุก Java service (expose `/actuator/prometheus`) + Prometheus Deployment (scrape services ผ่าน k8s SD/annotation) + Grafana Deployment (provisioned datasource + **overview dashboard** + **per-service dashboard**: req rate, 5xx error rate, latency p99, JVM heap) + **alert rules** (`up==0`, 5xx rate สูง, p99 สูง) · verify: Grafana มีข้อมูลจริงหลังยิง smoke; `kubectl delete pod` 1 ตัว → Prometheus `/alerts` เห็น `up==0` firing
- [ ] **Ops-T7 [Security] CMN1: signed headers Kong↔service** — `jwt-hs512` plugin: หลัง verify JWT + set `X-Auth-User/Role` → เซ็น `X-Auth-Sig = HMAC-SHA256(secret, "user|role|ts")` + `X-Auth-Ts`; `marketplace-common` HeaderAuthFilter: verify sig + ts (replay window ~30s) ก่อนเชื่อ identity, ไม่มี/หมดอายุ/ไม่ตรง → 401 · verify: ยิง service ตรง (bypass Kong ผ่าน port-forward) ด้วย `X-Auth-*` ปลอมไม่มี sig → **401**; ผ่าน Kong (มี sig) → 200 (ต่อยอด MAR-72)
- [ ] **Ops-T8 [Infra] HPA + k8s smoke gate** — HPA (chat/catalog, CPU target) + `smoke.sh` ชี้ k8s Ingress ผ่านครบ + (option) CI job: `kind` + apply + smoke · verify: smoke ครบทุก step บน k8s เขียว; โหลด CPU → HPA scale replica เพิ่ม (spot-check `kubectl get hpa`)

**Non-goals (Ops):** cloud จริง (AWS/GCP/DO) · service mesh (Istio/Linkerd) · mTLS (HMAC ก่อน) · log aggregation (Loki/ELK) · secrets manager (Vault/SOPS) · GitOps (ArgoCD — kustomize+kubectl ก่อน) · multi-cluster/multi-region

**Phase 5** · จ่ายเงิน (mock behind interface) · รีวิว/ดาว · wishlist *(สเปคเต็มด้านล่าง; recommendations เลื่อน)*

---

### SPEC — P5b: ขยาย P5 — cancel + refund + address + รูป upload (เคาะ 2026-07-08)
**เคาะแล้ว:** ไม่มี service ใหม่ ไม่มี Kong route ใหม่ (ทุกอย่างใต้ `/api/orders` `/api/payments` `/api/catalog` เดิม) — internal endpoints ยิงตรง service-to-service ไม่ผ่าน Kong เหมือนเดิม · รูปเก็บ bytea ใน catalogdb (ไม่ตั้ง volume/S3 — stateless ไม่แตะ compose/k8s; ย้าย MinIO/S3 เมื่อรูปเยอะจริง) · paid ยกเลิกได้จนกว่าจะ shipped (ไม่มี return flow) · address = free text (recipient/phone/addressLine ไม่แยกตำบล/อำเภอ/จังหวัด) · checkout บังคับ `addressId` (smoke เดิมต้องเพิ่ม step สร้าง address ก่อน checkout)

**เปลี่ยน order lifecycle (หัวใจ P5b):** `pending`→`paid`→`shipped`→`done` เดิม + buyer cancel ได้จาก `pending` (ยกเลิกเฉย ๆ) หรือ `paid` (refund ก่อน) → **`cancelled`** · `shipped`/`done` ห้าม (409) · cancel ทุกกรณีคืน stock (reuse catalog internal restore ของ reconcile job) · `NEXT_STATUS` ฝั่ง seller ไม่แตะ (cancel เป็นคนละ path)

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `POST /api/orders/{id}/cancel` | order | BUYER (own) | `pending`→cancelled+restock · `paid`→refund ผ่าน payment internal สำเร็จแล้ว→cancelled+restock → `{orderId, status:"cancelled", refunded:bool}` · `shipped/done`→409 |
| `POST /internal/payments/refund` `{orderId}` | payment | X-Internal-Key | payment `paid`→`refunded` ผ่าน `PaymentProvider.refund` (mock สำเร็จเสมอ) → `{paymentId, status:"refunded"}` **idempotent** (refunded แล้วเรียกซ้ำ = no-op) · ไม่มี payment paid → 404 |
| `GET /api/orders/addresses` | order | BUYER | `[{id, recipient, phone, addressLine}]` ของตัวเอง |
| `POST /api/orders/addresses` `{recipient, phone, addressLine}` | order | BUYER | เพิ่ม |
| `DELETE /api/orders/addresses/{id}` | order | BUYER (own) | ลบ (order เดิมไม่กระทบ เพราะ snapshot) |
| checkout เดิม | order | BUYER | body += **`addressId` (required)** → validate เป็นของ buyer → snapshot ลง orders |
| `POST /api/catalog/images` (multipart) | catalog | SELLER | ไฟล์ **≤2MB, jpeg/png/webp เท่านั้น** → เก็บ bytea → `{url:"/api/catalog/images/{id}"}` (เกิน→413, ผิดชนิด→415) — จากนั้น flow `imageUrls` เดิมไม่แตะ |
| `GET /api/catalog/images/{id}` | catalog | public | serve bytes + content-type + `Cache-Control: immutable` |

*(seller เห็นที่อยู่ใน order list/detail ตั้งแต่ `paid` ขึ้นไป — เอาไว้ส่งของ)*

**Data model:**
- payment `payment.status` += `refunded` + คอลัมน์ `refunded_at`
- order `address(id, buyer_username, recipient, phone, address_line, created_at)` · orders += `recipient, phone, address_line` (nullable รองรับ row เก่า)
- catalog `image(id, owner_username, content_type, bytes bytea, created_at)`

**แตกงาน (P5b-T1..T6)** — feature-branch+PR ต่อ task, service tag + 1 KPI
- [ ] **T1 [payment]** `PaymentProvider.refund` + `MockPaymentProvider` + `POST /internal/payments/refund` + status `refunded` · **KPI:** paid→refund→`refunded` + เรียกซ้ำ idempotent · ยังไม่ paid → error
- [ ] **T2 [order]** `POST /api/orders/{id}/cancel` + PaymentClient(refund) + restock ผ่าน CatalogClient เดิม · **KPI:** pending cancel→cancelled+restore ยิง · paid cancel→refund ยิง+cancelled · shipped→409 · order คนอื่น→403
- [ ] **T3 [order]** address CRUD + checkout require `addressId` + snapshot + seller view · **KPI:** checkout ไม่มี addressId→400 · มี→orders snapshot ครบ · addressId คนอื่น→403
- [ ] **T4 [catalog]** upload/serve images · **KPI:** upload png → GET คืน bytes เดิม (md5 ตรง) · 3MB→413 · text/plain→415 · ไม่ login→401
- [ ] **T5 [web]** ปุ่มยกเลิก (Orders, เฉพาะ pending/paid) · address book ใน Account + เลือกที่อยู่ตอน checkout (Cart) · Seller เห็นที่อยู่ · file picker ในฟอร์มสินค้า (upload→append imageUrls) · i18n · **KPI:** `npm run build` + Vitest เดิมผ่าน + ใช้จริงผ่าน Kong
- [ ] **T6 [deploy]** smoke steps ใหม่: cancel pending→stock คืน · paid→cancel→refunded · checkout แนบ address→seller เห็น · upload รูป→โชว์ใน product · **KPI: smoke 22/22 PASS ผ่าน Kong สด**

**Non-goals (P5b):** partial refund · seller เป็นคน cancel · return/refund หลัง `shipped` · refund gateway จริง (mock behind interface) · แก้ไข address (ลบ+เพิ่มแทน) · validate ที่อยู่ไทย (free text พอ) · resize/thumbnail/หลายขนาด · orphan image GC (จด debt) · ย้ายรูปเก่าที่เป็น external URL

---

### SPEC — NOTIF: การแจ้งเตือนสถานะออเดอร์ in-app + realtime (เคาะ 2026-07-08)
> spec ละเอียดระดับ implement/mock: **API-SPEC-NOTIF.md**

**เคาะแล้ว:** ไม่มี service ใหม่ — notification อยู่ใน **chat-service** (เจ้าของ WS + Redis fan-out) · order ยิง event ผ่าน internal HTTP (**best-effort** — chat ล่ม order ไม่พัง) · ไม่มี Kong route ใหม่ (ใต้ `/api/chat`) · ไม่เก็บข้อความ — web render จาก `type` ผ่าน i18n (TH/EN ฟรี) · แจ้ง seller ผ่าน key `shop:<shopId>` (มีใน SessionRegistry แล้ว, order รู้ shopId อยู่แล้ว)

**Flow:** order (จุด transition) → `POST {chat}/internal/notifications` → chat save ลง chatdb + publish Redis channel `notif.broadcast` → ทุก pod ส่ง WS frame `{type:"notification",...}` เข้า session ของ recipientKey → web กระดิ่ง badge เด้งสด

**Events (4):** `order_paid`→`shop:<id>` (เงินเข้า เตรียมส่ง) · `order_cancelled`→`shop:<id>` (ทุกกรณี ไม่แยก branch) · `order_shipped`→`user:<buyer>` · `order_done`→`user:<buyer>`

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `POST /internal/notifications` `{recipientKey, type, orderId}` | chat | X-Internal-Key | save + push WS ผ่าน Redis ไปทุก pod |
| `GET /api/chat/notifications` | chat | login | `{unread, items:[{id,type,orderId,createdAt,read}]}` ล่าสุด 50 — resolve key ผู้เรียก (`user:<me>` + `shop:<myShopId>` ถ้า SELLER) |
| `POST /api/chat/notifications/read` | chat | login | mark ทั้งหมดเป็นอ่านแล้ว (per-item = yagni) |

**Data:** chatdb V3 `notification(id, recipient_key, type, order_id, created_at, read_at)` index `recipient_key`

**แตกงาน (NOTIF-T1..T4)** — feature-branch+PR ต่อ task, service tag + 1 KPI
- [ ] **T1 [chat]** V3 + entity + internal POST + GET/read + NotificationBroadcaster (channel `notif.broadcast` คู่ `chat.broadcast`) + WS push · **KPI:** Testcontainers+Redis — post→row+deliver ถึง session · seller เห็นของ shop ตัวเอง · read→unread 0 · key ผิด→403
- [ ] **T2 [order]** NotificationClient (best-effort, config `CHAT_URL` ใหม่) hook: markPaid→`order_paid` · cancel→`order_cancelled` · updateStatus→`order_shipped`/`order_done` · **KPI:** MockWebServer — ครบ 4 event · **chat ล่ม → order operation สำเร็จปกติ**
- [ ] **T3 [web]** กระดิ่งใน nav + badge unread + dropdown (render จาก type ผ่าน i18n) + mark-read ตอนเปิด + รับ WS frame live · **KPI:** `npm run build` + Vitest เดิมผ่าน + ใช้จริงผ่าน Kong
- [ ] **T4 [deploy]** env `CHAT_URL` ให้ order (compose+k8s) + smoke: paid→seller notif · shipped→buyer notif · read→unread 0 · **KPI: smoke 25/25 PASS ผ่าน Kong สด**

**Non-goals (NOTIF):** email/LINE/FCM จริง · per-item read · preferences/mute · แจ้ง admin · chat unread count · pagination (50 ล่าสุดพอ) · retention/ลบเก่า

---

### SPEC — RECO: "คนที่ซื้อสินค้านี้ยังซื้อ..." co-purchase recommendations (เคาะ 2026-07-09)
> spec ละเอียดระดับ implement/mock: **API-SPEC-RECO.md**

**เคาะแล้ว:** ไม่มี service/ตาราง/Kong route ใหม่ — ข้อมูลอยู่ใน order-service (`orders`+`order_item`) · **native query เดียว** ไม่มี ML/batch/cache (จด ceiling: ข้อมูลโตค่อยทำ materialized view) · คืน **productIds เรียงแล้ว ≤8** ให้ web fetch รายละเอียดจาก catalog เอง (pattern เดียวกับ wishlist — banned product ถูกกรองฟรีด้วย 404) · endpoint **public** (guest เห็นเหมือน e-commerce จริง)

**นิยาม:** คนที่เคยซื้อ X (order `paid/paid_mock/shipped/done`) → สินค้าอื่นที่คนกลุ่มนั้นซื้อ (ตัด X) → เรียงตาม `COUNT(DISTINCT buyer)` (ไม่ใช่ qty — กัน 1 คนซื้อเยอะลากอันดับ), tie-break ด้วย product_id → top 8

**API**
| Method Path | service | auth | ทำอะไร |
|---|---|---|---|
| `GET /api/orders/products/{productId}/also-bought` | order | public | `{productIds:[...]}` เรียงแล้ว ≤8 · ไม่มีข้อมูล → `{productIds:[]}` (ไม่ 404) |

**Web (หน้า Product):** section "คนที่ซื้อสินค้านี้ยังซื้อ" — fetch ids → fetch product รายตัว (404/แบน = ข้าม) · ว่าง → ซ่อนทั้ง section · i18n TH/EN

**แตกงาน (RECO-T1..T3)** — feature-branch+PR ต่อ task, service tag + 1 KPI
- [ ] **T1 [order]** native query ใน OrderItemRepository + endpoint + SecurityConfig permitAll path นี้ · **KPI:** อันดับถูกตาม DISTINCT buyer · ตัด X · `pending/cancelled` ไม่นับ · ว่าง → `[]` · ไม่ login → 200
- [ ] **T2 [web]** section บนหน้า Product + skip 404 + ซ่อนเมื่อว่าง + i18n · **KPI:** `npm run build` + Vitest เดิมผ่าน + ใช้จริงผ่าน Kong
- [ ] **T3 [deploy]** smoke step 26: 2 buyers ซื้อทับซ้อน → also-bought เรียงถูก · **KPI: smoke 26/26 PASS ผ่าน Kong สด** (ไม่มี env ใหม่)

**Non-goals (RECO):** ML/embeddings · personalized per-user · reco หน้า Home · cache/materialized view · น้ำหนักตามเวลา/ราคา · cross-sell ตอน checkout

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
