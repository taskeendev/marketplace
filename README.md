# Marketplace — project hub

Omnichannel multi-seller marketplace (greenfield microservices, Java/Spring + React + Kong).
This repo is the **hub**: the spec, the backlog (Issues + Project board), and links to the per-service repos.

## Repos
| Repo | Purpose |
|---|---|
| [marketplace-gateway](https://github.com/taskeendev/marketplace-gateway) | Kong gateway + `jwt-hs512` Lua plugin |
| [marketplace-auth](https://github.com/taskeendev/marketplace-auth) | auth — register/login/JWT/refresh/roles |
| [marketplace-catalog](https://github.com/taskeendev/marketplace-catalog) | products / inventory *(P1)* |
| [marketplace-order](https://github.com/taskeendev/marketplace-order) | cart / checkout *(P1)* |
| [marketplace-web](https://github.com/taskeendev/marketplace-web) | React / Vite / TS / Tailwind / shadcn |
| [marketplace-deploy](https://github.com/taskeendev/marketplace-deploy) | docker-compose stack + run.sh + smoke.sh |
| [marketplace-common](https://github.com/taskeendev/marketplace-common) | shared lib (JWT verify, RFC7807) |

## Stack
Java 21 + Spring Boot + Maven · **Kong** gateway · Postgres-per-service + Flyway · React 19/Vite/TS/Tailwind/shadcn ·
Hermes (AI agent, P4). DB-per-service; JWT as the inter-service contract.

## Run locally
```bash
cd marketplace-deploy && cp .env.example .env && ./run.sh --build -d && ./smoke.sh
# web: http://localhost:3000 (docker)  ·  or: cd marketplace-web && npm run dev  (http://localhost:5173)
```

## Phases
- **P0 — Foundation** ✅ gateway + auth + web shell (stack live, smoke green)
- **P1 — Core marketplace** catalog+inventory, order/checkout, storefront + seller dashboard *(in progress)*
- P2 real-time chat · P3 social FB/IG · P4 Hermes AI + admin · P5 payment / reviews

Full spec + per-task API contracts: **[SPEC.md](./SPEC.md)** · Backlog: **Issues** + **Project board**.
