#!/usr/bin/env python3
# ponytail: hardcoded task data lifted from SPEC.md; one-shot migration, no parser needed.
import csv, sys

OUT = "/Users/taskeen/marketplace/marketplace-jira-import.csv"

# epics: (epic_name, summary, status, description)
epics = [
    ("P0 รากฐาน", "P0: รากฐาน (Foundation)", "Done",
     "เป้าหมาย: gateway + auth + web shell รันทั้ง stack ด้วย docker-compose ในเครื่อง → สมัคร/ล็อกอินผ่าน Kong เข้าหน้า account ได้จริง (8 task)\n\n"
     "API (ผ่าน Kong :8080):\n"
     "POST /api/auth/register · public → in {email,username,password} → 201 {id,username,email,role:BUYER} · err 400,409\n"
     "POST /api/auth/login · public → in {username,password} → 200 {accessToken,expiresIn}+Set-Cookie refresh · err 401\n"
     "POST /api/auth/refresh · cookie → 200 {accessToken,expiresIn} · err 401\n"
     "POST /api/auth/logout · Bearer → 204 · err 401\n"
     "GET /api/users/me · Bearer → 200 {id,username,email,role} · err 401\n"
     "GET /health · public → 200 {status:UP}"),
    ("P1 แก่น marketplace", "P1: แก่น marketplace (web MVP)", "Done",
     "เป้าหมาย: marketplace หลายผู้ขายครบลูปบน web — เปิดร้าน/ลงสินค้า/ตั้งสต็อก; ผู้ซื้อค้นหา-ใส่ตะกร้า-checkout(จำลอง)-ดูออเดอร์; ตัดสต็อก atomic กัน oversell; ผู้ขายอัปสถานะ; TH/EN (~14 task)\n\n"
     "API catalog:\n"
     "GET /api/catalog/categories · public → 200 [{id,slug,nameEn,nameTh}]\n"
     "POST /api/catalog/shops · SELLER → in {name,slug?,description} → 201 {shop} · err 403,409\n"
     "GET /api/catalog/shops/me · SELLER → 200 {shop} · err 404\n"
     "GET /api/catalog/shops/{slug} · public → 200 {shop+products} · err 404\n"
     "POST /api/catalog/shops/me/products · SELLER → in {categoryId,titleEn,titleTh,descEn,descTh,priceBaht,imageUrls[],stockQty,status?} → 201 {product} · err 400,403\n"
     "PUT /api/catalog/shops/me/products/{id} · SELLER → 200 {product} · err 400,403,404\n"
     "GET /api/catalog/shops/me/products · SELLER → 200 [{product+stockQty}] · err 403\n"
     "GET /api/catalog/products · public → ?q=&categoryId=&page=&size= → 200 {items[],page,total}\n"
     "GET /api/catalog/products/{id} · public → 200 {product+images+stockQty} · err 404\n"
     "POST /api/catalog/inventory/decrement · internal → in {items[{productId,qty}],idempotencyKey} → 200 {ok:true} · err 409 {outOfStock[]}\n\n"
     "API order:\n"
     "GET /api/orders/cart · BUYER → 200 {items[],total} · err 401\n"
     "POST /api/orders/cart/items · BUYER → in {productId,qty} → 200 {cart} · err 400,404\n"
     "PUT /api/orders/cart/items/{productId} · BUYER → in {qty} → 200 {cart} · err 400,404\n"
     "DELETE /api/orders/cart/items/{productId} · BUYER → 200 {cart} · err 404\n"
     "POST /api/orders/checkout · BUYER → 201 {orders[{orderId,shopName,status:paid_mock,totalBaht}]} · err 409 {outOfStock[]}\n"
     "GET /api/orders/me · BUYER → 200 [orders+items] · err 401\n"
     "GET /api/orders/shops/me · SELLER → ?status= → 200 [orders ของร้าน] · err 403\n"
     "PATCH /api/orders/{id}/status · SELLER → in {status} → 200 {orderId,status} · err 400,403,404\n\n"
     "API auth (เพิ่ม):\n"
     "POST /api/users/me/become-seller · Bearer → 200 {role:SELLER} (ต้อง refresh token) · err 401"),
    ("P2 แชต real-time", "P2: แชต real-time (พระเอก)", "Done",
     "เป้าหมาย: buyer↔seller คุยสดจากหน้าสินค้า (WebSocket), เก็บประวัติ, รายการห้อง, unread — รากฐานให้ P4 (Hermes) ตอบอัตโนมัติทีหลัง (10 task). ห้อง = ต่อร้าน (1 ห้อง/คู่ buyer–shop), scope Lean core, transport = Raw WebSocket\n\n"
     "REST /api/chat (identity จาก X-Auth-User/Role):\n"
     "POST /api/chat/conversations · BUYER → in {productId} → 200 {id,shopId,shopName,productId,lastMessageAt} (find-or-create) · err 400,404\n"
     "GET /api/chat/conversations · BUYER/SELLER → 200 [{id,shopId,shopName,productId,lastMessage,unread,lastMessageAt}] · err 401\n"
     "GET /api/chat/conversations/{id}/messages · participant → ?before=&limit= → 200 [messages] · err 403,404\n"
     "POST /api/chat/conversations/{id}/read · participant → 204 · err 403,404\n\n"
     "WebSocket /ws/chat (JSON frames, auth ด้วย frame แรก):\n"
     "client→ {type:auth,token} (frame แรก) → {type:authed} ; ผิด close 4401\n"
     "client→ {type:send,conversationId,body} → persist+push buyer+shop ; ไม่ใช่คู่ close 4403\n"
     "→client {type:message,message:{...}} (echo ทั้งสองฝั่ง)\n"
     "→client {type:error,detail}"),
    ("P3 omnichannel social", "P3: omnichannel social (FB/IG)", "Done",
     "3 ระบบอิสระ แตกเป็น sub-phase, mock external Meta ก่อน (⚠️ blocker: Meta Business verification):\n"
     "- P3a Omnichannel inbox (FB Messenger DM → รวมกล่องแชต P2) — เสร็จ 2026-07-01\n"
     "- P3b Product sync (catalog → FB/IG Shops)\n"
     "- P3c Social login (FB/IG OAuth) — skeleton\n\n"
     "P3a internal/REST API:\n"
     "GET /webhooks/fb · social · public → Meta webhook verify (echo hub.challenge)\n"
     "POST /webhooks/fb · social · Meta sig → รับ event → normalize → chat /internal/inbound\n"
     "POST /internal/social/simulate-inbound · social · internal → จำลอง FB inbound\n"
     "POST /internal/social/send · social · X-Internal-Key → mock Meta Send + outbound_log\n"
     "POST /internal/chat/inbound · chat · X-Internal-Key → find-or-create external conv + persist + broadcast WS\n"
     "POST /api/social/connections · social · SELLER → เชื่อม FB Page (mock) ผูก pageId↔shop\n\n"
     "P3b API (reuse /api/social):\n"
     "POST /api/social/sync · SELLER → ดึง /shops/me/products → mock push → upsert → {synced,syncedAt}\n"
     "GET /api/social/sync · SELLER → {count,lastSyncedAt}"),
    ("P4 Hermes AI + admin", "P4: Hermes AI agent + admin", "To Do",
     "เป้าหมาย: ตอบลูกค้าอัตโนมัติ (เรียกข้อมูลจริง) + เครื่องมือ admin. marketplace-agent รัน Hermes (self-host), ห่อ catalog/order เป็น tool/MCP, guardrail, hook เข้า chat. admin: นาทีทอง (flash-sale), ban (user/ร้าน/สินค้า), จัดการ caption. ⚠️ เคาะโมเดลไทย+งบ LLM ก่อนเริ่ม"),
    ("P5 ทีหลัง", "P5: จ่ายเงินจริง + รีวิว", "To Do",
     "จ่ายเงินจริง (PromptPay/บัตร) · รีวิว/ดาว · wishlist · ระบบแนะนำสินค้า"),
]

# stories: (summary, label, status, scope, verify)  -> epic assigned per block
stories = {
 "P0 รากฐาน": [
  ("P0-T1: marketplace-common","BE","Done","lib กลาง (Java): JwtVerifier(HS512) + RFC7807 error model + @RestControllerAdvice handler → publish com.taskeendev:marketplace-common:0.1.0 ไป GitHub Packages","mvn -q -DskipTests install ผ่าน + service อื่น depend แล้ว resolve ได้"),
  ("P0-T2: marketplace-auth scaffold","BE","Done","Boot+Maven+Postgres+Flyway+common+springdoc · Flyway V1__users.sql, V2__refresh_tokens.sql","Testcontainers ขึ้น Postgres + app boot + /health→200 + /swagger-ui ขึ้น"),
  ("P0-T3: auth register/login/JWT","BE","Done","issue access JWT(HS512, TTL 15m, sub=username, role) + refresh (hash เก็บ DB, HttpOnly cookie 14 วัน)","integration test register→login ได้ token, /users/me ใช้ token ได้"),
  ("P0-T4: auth refresh/logout/me + roles","BE","Done","rotate refresh + reuse-detection; role default BUYER","test refresh ได้ token ใหม่, logout แล้วใช้ refresh เดิมไม่ได้"),
  ("P0-T5: marketplace-gateway (Kong)","GW","Done","declarative kong.yml: route /api/auth,/api/users→auth; plugin verify HS512 + inject X-Auth-User/Role; rate-limit; CORS; correlation-id","ยิงผ่าน :8080 ทะลุไป auth, token เสีย→401 ที่ Kong"),
  ("P0-T6: marketplace-deploy","Infra","Done","docker-compose.yml (kong+auth+postgres-auth) + .env.example + run.sh + smoke.sh","./run.sh --build -d ขึ้นครบ healthy"),
  ("P0-T7: marketplace-web shell","FE","Done","Vite/TS/Tailwind/shadcn: config.ts(env), api/client.ts(fetch+JWT memory+refresh-on-401), auth.tsx+ProtectedRoute, i18n locales/{en,th}.ts, หน้า Login/Register/Account, ApiStatus","npm run build ผ่าน, ล็อกอินผ่าน Kong ได้, สลับ TH/EN ได้"),
  ("P0-T8: smoke P0","Infra","Done","smoke.sh: register→login→/users/me ผ่าน gateway = 200","smoke เขียว"),
 ],
 "P1 แก่น marketplace": [
  ("P1-T1: catalog scaffold + category","BE","Done","Boot+Maven+Postgres+Flyway · category + seed (Fashion/Food/Gadget…) · GET /api/catalog/categories","คืน list หมวด"),
  ("P1-T2: auth become-seller","BE","Done","POST /api/users/me/become-seller เปลี่ยน role→SELLER (ต้อง refresh token ใหม่)","test BUYER→SELLER"),
  ("P1-T3: shop","BE","Done","สร้าง/ดูร้าน (เจ้าของ 1 ร้าน/คนใน MVP)","SELLER สร้างร้านได้, BUYER โดน 403"),
  ("P1-T4: product CRUD (seller)","BE","Done","ลง/แก้/ลบ/ดูสินค้าของร้านตัวเอง (i18n field + ราคา + รูป URL + สต็อกเริ่มต้น)","ลงสินค้าแล้ว inventory ถูกสร้าง stock=ที่กรอก"),
  ("P1-T5: inventory decrement (atomic+idempotent)","BE","Done","POST /api/catalog/inventory/decrement: UPDATE…WHERE stock_qty>=qty + เขียน stock_ledger ตาม idempotency_key","เทสต์ขนานบน stock=1 → สำเร็จ 1 อันเท่านั้น; ยิงซ้ำ key เดิม → ไม่ตัดเบิ้ล"),
  ("P1-T6: public browse/search","BE","Done","GET /products (q+categoryId+paging, PG full-text บน title), GET /products/{id}","ค้นหาเจอ, สินค้า banned/draft ไม่โผล่"),
  ("P1-T7: order scaffold + cart","BE","Done","Boot+Postgres+Flyway · ตะกร้าต่อผู้ซื้อ (เพิ่ม/แก้จำนวน/ลบ)","เพิ่มของลงตะกร้าแล้วดูได้"),
  ("P1-T8: checkout (mock)","BE","Done","POST /api/orders/checkout: แตกตะกร้าตามร้าน → catalog decrement (idempotency=orderId) → สร้าง order/order_item (paid_mock) → เคลียร์ตะกร้า; ของหมด rollback ทั้งบิล","checkout สำเร็จ stock ลด; ของหมด → 409 ไม่สร้าง order"),
  ("P1-T9: orders (buyer/seller)","BE","Done","buyer ดูออเดอร์ตัวเอง; seller ดูออเดอร์ร้าน + อัปสถานะ (paid_mock→shipped→done)","เห็นตรงฝั่ง, อัปสถานะผิดลำดับ → 400"),
  ("P1-T10: gateway + deploy ขยาย","GW","Done","Kong route /api/catalog,/api/orders; compose เพิ่ม catalog+order+postgres แต่ละตัว","ยิงผ่าน :8080 ได้ทั้งคู่"),
  ("P1-T11: web — storefront + product","FE","Done","หน้าหลัก (หมวด+ค้นหา), หน้าสินค้า (รูป/ราคา/สต็อก/ปุ่มใส่ตะกร้า)","เลือกสินค้า→ใส่ตะกร้าได้"),
  ("P1-T12: web — cart + checkout + my orders","FE","Done","ตะกร้า, checkout(จำลอง)→หน้ายืนยัน, ออเดอร์ของฉัน","ครบลูปซื้อ"),
  ("P1-T13: web — seller dashboard","FE","Done","become-seller, ร้านฉัน, สินค้า CRUD+สต็อก, ออเดอร์ร้าน+อัปสถานะ","ผู้ขายจัดการได้ครบ"),
  ("P1-T14: i18n + smoke P1","FE","Done","เพิ่ม key TH/EN ครบ (shop/seller/cart/order); smoke.sh ครบลูป + oversell test","smoke เขียว, สลับภาษาครบ"),
 ],
 "P2 แชต real-time": [
  ("P2-T1: chat scaffold + data model","BE","Done","Boot+Postgres(chatdb)+Flyway+common+websocket · ตาราง conversation/message · health","boot + Testcontainers"),
  ("P2-T2: CatalogClient + สร้างห้อง","BE","Done","CatalogClient (product→shop, shops/me→shopId) + POST /conversations find-or-create","ยิงซ้ำ productId เดิม → ห้องเดิม"),
  ("P2-T3: รายการห้อง + unread","BE","Done","GET /conversations (buyer by username / seller by shopId) + unread count","เห็นถูกฝั่ง, unread ถูก"),
  ("P2-T4: ประวัติข้อความ + guard","BE","Done","GET /{id}/messages?before=&limit= + participant guard","คนนอกห้อง → 403"),
  ("P2-T5: mark-read","BE","Done","POST /{id}/read (set last_read_at ตามฝั่ง)","read แล้ว unread = 0"),
  ("P2-T6: WS endpoint + auth + registry","BE","Done","/ws/chat TextWebSocketHandler, frame แรก auth (common.JwtVerifier), in-memory registry","auth ✓ → authed / ผิด → ปิด 4401"),
  ("P2-T7: WS send + delivery","BE","Done","{type:send} persist + push ไป buyer+shop (echo), guard ไม่ใช่คู่ → 4403","2 client ส่ง→อีกฝั่งได้รับจริง"),
  ("P2-T8: gateway + deploy","GW","Done","Kong route /api/chat+/ws/chat (WS upgrade); compose เพิ่ม chat+postgres-chat; run.sh","ยิงผ่าน :8080 + WS ทะลุ"),
  ("P2-T9: web — chat page","FE","Done","ปุ่ม แชตผู้ขาย หน้าสินค้า + หน้า /chat (list+thread+WS send/recv+mark-read)","คุยสองทางผ่าน Kong"),
  ("P2-T10: web — unread badge + i18n + smoke","FE","Done","badge unread ใน header, i18n TH/EN, e2e smoke P2","badge อัปเดต, สลับภาษา, smoke เขียว"),
 ],
 "P3 omnichannel social": [
  ("P3a-T1: scaffold marketplace-social","BE","Done","scaffold marketplace-social (:8085, Postgres+Flyway+common) + page_connection + webhook verify (GET challenge)","boot + test"),
  ("P3a-T2: chat extend external + inbound","BE","Done","chat extend conversation/message (channel/external) + POST /internal/chat/inbound (find-or-create external + broadcast WS)","test"),
  ("P3a-T3: social receive webhook","BE","Done","social: receive POST /webhooks/fb → normalize → เรียก chat /inbound + POST /internal/social/simulate-inbound","test"),
  ("P3a-T4: outbound send (mock Meta)","BE","Done","seller ตอบในห้อง fb → chat เรียก social /internal/send → mock send + outbound_log","test"),
  ("P3a-T5: gateway + deploy + smoke","GW","Done","Kong route /api/social + /webhooks/fb · compose +social +postgres-social · run.sh build social · smoke step 11","smoke step 11 เขียว (ทะลุ Kong)"),
  ("P3a-T6: web — channel badge + connect FB","FE","Done","web: channel badge + external name ใน /chat + connect FB (mock) + ปุ่ม dev simulate","seller เห็น FB message + ตอบได้"),
  ("P3b-T1: product sync BE","BE","Done","social: published_product + CatalogClient.listMyProducts (forward identity) + FbCatalog(mock) + POST/GET /api/social/sync","sync ดึง N (MockWebServer stub) → published_product N + mock pusher ถูกเรียก; re-sync upsert; non-seller 403"),
  ("P3b-T2: product sync FE + smoke","FE","Done","web: ปุ่ม Sync สินค้าไป Facebook + สถานะ + i18n + smoke step 12","seller sync → GET status = N (ทะลุ Kong)"),
  ("P3c-T1 auth: FB OAuth","BE","Done","real FB OAuth: app_user +external_provider_id + password nullable; GraphClient (code→token→profile); FbOAuthService; AuthService.socialLogin (find-by-provider→link-by-email→create BUYER); GET/POST /api/auth/oauth/fb/{login-url,callback}","tests mock Graph: new/link/existing; login-url live ผ่าน Kong"),
  ("P3c-T2 web: Login with Facebook","FE","Done","web ปุ่ม Continue with Facebook + /oauth/fb/callback route + api/auth + i18n; compose auth FB_* env","npm run build; login-url redirect FB; callback set token"),
 ],
 "P4 Hermes AI + admin": [
  ("P4a-T1 agent: scaffold + config + tools","BE","Done","scaffold marketplace-agent (:8086, agentdb, common) + agent_config + POST/GET /api/agent/config (SELLER toggle) + CatalogClient/OrderClient read-only tools","boot+test; toggle เปิด/ปิดต่อร้าน"),
  ("P4a-T2 chat: /internal/chat/reply + notify agent","BE","Done","chat: POST /internal/chat/reply (บอท reply sender=hermes + broadcast + outbound relay) + AgentClient + ยิง agent เมื่อมีข้อความฝั่งลูกค้า (best-effort, กัน loop) + AGENT_URL","reply post+broadcast; customer msg → notify; seller/bot → ไม่ยิง"),
  ("P4a-T3 agent: incoming + MockLlmAgent","BE","Done","agent: POST /internal/agent/incoming → LlmAgent + MockLlmAgent (intent→tool→templated, guardrail) → post via chat + agent_reply_log","MockWebServer stub catalog/order/chat: ตอบอิง tool data; disabled shop → no-op"),
  ("P4a-T4 gateway/deploy + smoke step 13","GW","To Do","Kong route /api/agent + compose +agent+postgres-agent + chat AGENT_URL + run.sh build agent + smoke step 13","enable Hermes → ลูกค้าถามราคา → บอทตอบราคาจริง ผ่าน Kong; ปิด → ไม่ตอบ"),
  ("P4a-T5 web: Hermes toggle + bot badge","FE","To Do","web: seller dashboard 🤖 Hermes on/off toggle + ป้าย 🤖 บนข้อความ hermes + i18n","npm run build; toggle ทำงาน; บอทมีป้าย"),
 ],
}

# tech-debt filed as individual tasks: (id, title, sev, service, fix, impact, kpi, issue_type, epic_link)
# kpi = ONE runnable check + concrete expected value ([e2e]/[infra]/[partial] = not a plain unit test)
debt = [
 ("D1","seller resolve shop ไม่ cache (ยิง catalog ทุก request)","🟡","chat · BE","cache shop_id (TTL/Caffeine) หรือใส่ JWT claim","seller ทุก req ยิง catalog +1 → latency+coupling","GET /shops/me ไป catalog ต่อ 10 requests ของ seller คนเดียว = 1 (หลัง cache; นับด้วย MockWebServer)","Story","P2 แชต real-time"),
 ("D4","WS session registry in-memory ตัวเดียว","🟡","chat · BE","Redis pub/sub fan-out ข้าม node","chat รันได้แค่ 1 instance, ไม่ HA","[e2e/infra: Redis] chat 2 instance หลัง LB → client คนละ instance ส่งข้อความถึงกันข้าม instance","Story","P2 แชต real-time"),
 ("D5","WS delivery ใช้ synchronized(session)","🟢","chat · BE","ConcurrentWebSocketSessionDecorator","ไม่ optimal ตอน concurrency สูง","100 concurrent send ไป session เดียว → 0 IllegalStateException + ทุก frame ครบ","Story","P2 แชต real-time"),
 ("D6","web WS ไม่มี auto-reconnect/token-refresh","🟢","web · FE","reconnect + re-auth token ใหม่ + heartbeat","token หมด/เน็ตหลุด → ต้อง refresh หน้า","[e2e] drop WS จาก server → client reconnect+re-auth เองใน ~5s + รับข้อความใหม่ได้ (ไม่ต้อง refresh)","Story","P2 แชต real-time"),
 ("O1","checkout decrement-then-create → stock leak","🟡","order · BE","reconcile job keyed idempotencyKey หรือ outbox/saga","crash หลัง decrement → สต็อกรั่ว","mock orders.save throw หลัง catalog.decrement → catalog stock −qty + orders=0 (repro); หลัง reconcile → catalog stock กลับเท่าเดิม + stock_ledger ที่ idempotencyKey ไม่มี order ผูก = 0","Bug","P1 แก่น marketplace"),
 ("C1","inventory concurrent same idempotencyKey → 500","🟡","catalog · BE","catch unique-violation → idempotent no-op / upsert","2 call key เดียวพร้อมกัน → ตัวแพ้ 500","ยิงขนาน 2 request idempotencyKey เดียวกัน → 0 responses = 5xx + stock_ledger 1 แถวต่อ key","Bug","P1 แก่น marketplace"),
 ("C2","catalog HeaderAuthFilter สำเนาเอง (ไม่ใช้ common)","🟢","catalog · BE","ใช้ common.HeaderAuthFilter","DRY 2 ที่ เสี่ยง drift","HeaderAuthFilter สำเนาใน catalog = 0 คลาส (ใช้ common) + auth/role tests เดิมเขียว","Story","P1 แก่น marketplace"),
 ("C3","catalog browse/listMine N+1","🟢","catalog · BE","join projection / batch fetch","ช้าตอน list ใหญ่","query count ต่อ browse 20 สินค้า ≤ 3 (Hibernate statistics; เดิม ~21)","Story","P1 แก่น marketplace"),
 ("I1","common แค่ mavenLocal (ยัง GitHub Packages)","🟢","common · Infra","publish GitHub Packages + CI auth","build ได้เฉพาะเครื่องที่ install common","build repo ที่ depend common บนเครื่องสะอาด (ไม่มี mavenLocal) ผ่าน — resolve จาก GitHub Packages ใน CI","Story","P0 รากฐาน"),
 ("SD1","social outbound best-effort (ไม่มี retry/outbox)","🟡","social · BE","outbox + retry หรือ mark ส่งไม่สำเร็จ","social ล่ม → ข้อความหายเงียบ","send ล้ม 2 ครั้งแรก สำเร็จครั้งที่ 3 → outbound_log status=sent + 0 ข้อความหายเงียบ","Bug","P3 omnichannel social"),
 ("SD2","webhook ไม่เช็ค X-Hub-Signature-256","🟡","social · BE (security)","verify HMAC-SHA256 ด้วย app secret","POST webhook ปลอมได้ (security)","webhook signature ผิด → status ≠ 2xx + 0 message persisted; ถูก (HMAC app secret) → 200 + persisted","Bug","P3 omnichannel social"),
 ("SD6","page token เป็น mock string","🟡","social · BE","OAuth เก็บ real Page Access Token","ส่ง/รับจริงกับ FB ไม่ได้","[partial จน Meta จริง] page_connection เก็บ token จาก OAuth exchange (mock Graph) ไม่ใช่ literal 'mock'","Story","P3 omnichannel social"),
 ("SD7","inbound display_name เป็น mock","🟢","social · BE","ดึงชื่อจริงจาก Graph API","ชื่อลูกค้าเป็น 'FB xxxx'","inbound → ดึงชื่อจาก Graph (mock) → conversation.display_name = ชื่อจริง ไม่ใช่ 'FB <id>'","Story","P3 omnichannel social"),
 ("SD8","webhook ไม่ dedup message id (mid)","🟢","social · BE","เก็บ mid กัน insert ซ้ำ","Meta ส่งซ้ำ → ข้อความซ้ำ","POST webhook mid เดียวกัน 2 ครั้ง → persist 1 ข้อความ (count=1)","Bug","P3 omnichannel social"),
 ("SDc1","FB OAuth state ไม่ validate (CSRF)","🟢","auth · BE (security)","เก็บ state cookie/store + validate ตอน callback","เสี่ยง CSRF บน OAuth callback","callback state ไม่ตรง/หมดอายุ → ไม่ออก token (400/401); state ถูก → สำเร็จ","Story","P3 omnichannel social"),
 ("CD1","catalog slug heuristic (ASCII/Thai, blank->shop)","🟢","catalog · BE","transliteration ไทย→latin ดีขึ้น หรือให้ผู้ขายกำหนด slug เอง","ร้านชื่อไทยล้วนได้ slug 'shop'/'shop-2'","2 ร้านชื่อไทยล้วน → slug ต่างกันและอ่านออก (ไม่ใช่ shop/shop-2) หรือ seller ตั้ง slug เองได้","Story","P1 แก่น marketplace"),
 ("CMN1","header-trust model (service เชื่อ X-Auth headers)","🟢","gateway+all · Infra (security)","mTLS หรือ signed headers ระหว่าง Kong↔service","เข้า service ตรง (bypass Kong) ปลอม identity ได้ (defense-in-depth)","ยิง service ตรง (bypass Kong) ด้วย X-Auth-* ปลอม → 401/403 (mTLS/signed headers) — ต่อยอด MAR-72","Story","P0 รากฐาน"),
 ("OD1","order tolerant cart (banned/removed product ยังโชว์)","🟢","order · BE","เอาออกอัตโนมัติ หรือแจ้ง+บล็อก checkout ชัดเจน","ผู้ซื้อเห็นของที่ซื้อไม่ได้ในตะกร้า (checkout 409 อยู่แล้ว)","สินค้า banned/ถูกลบในตะกร้า → checkout → 409 ระบุ item ที่มีปัญหา (ไม่ 500/ไม่เงียบ) + เอาออกจากตะกร้าได้","Story","P1 แก่น marketplace"),
]

rows = []
header = ["Issue Type","Summary","Epic Name","Epic Link","Labels","Status","Description"]
for epic_name, summary, status, desc in epics:
    rows.append(["Epic", summary, epic_name, "", "", status, desc])
    for st in stories.get(epic_name, []):
        s_sum, label, s_status, scope, verify = st
        d = f"ทำ: {scope}\n\nVerify: {verify}"
        rows.append(["Story", s_sum, "", epic_name, label, s_status, d])
# junior-friendly acceptance tables (problem/fix/success-fail) live in debt_bodies.json — edit there, keep in sync with JIRA
BODIES = __import__("json").load(open("/Users/taskeen/marketplace/debt_bodies.json", encoding="utf-8"))
SEVNAME = {"🟡": "medium", "🟢": "low", "🔴": "high"}
DEBT_DONE = {"C1", "C2", "SD2", "SD8", "SD1", "D1", "D5", "OD1", "SDc1", "C3", "CD1", "O1"}  # cleared debt (PR merged, KPI green) — flip here when each debt task lands
for did, dtitle, dsev, dsvc, dfix, dimp, dkpi, dtype, depic in debt:
    # JIRA project MAR ไม่มี issue type Bug -> ใช้ Story + label "bug" (ตรงกับการ์ดจริง MAR-54..71)
    labels = "tech-debt bug" if dtype == "Bug" else "tech-debt"
    body = BODIES.get(did) or f"**ปัญหา:** {dtitle}. **วิธีแก้:** {dfix}. 🎯 KPI: {dkpi}"
    desc = f"🔧 **{dsvc}** · {dsev} {SEVNAME.get(dsev, '')}\n\n{body}"
    rows.append(["Story", f"[debt] {did}: {dtitle}", "", depic, labels,
                 "Done" if did in DEBT_DONE else "To Do", desc])

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(rows)

# self-check: every task's Epic Link must match an existing Epic Name
epic_names = {e[0] for e in epics}
for r in rows:
    if r[0] in ("Story", "Bug"):
        assert r[3] in epic_names, f"orphan epic link: {r[3]}"
n_epic = sum(1 for r in rows if r[0]=="Epic")
n_task = sum(1 for r in rows if r[0] in ("Story","Bug"))
print(f"OK wrote {OUT}: {n_epic} epics + {n_task} tasks = {len(rows)} rows")
