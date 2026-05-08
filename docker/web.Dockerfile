# ============================================================================
# CustDevAI Web SPA — multi-stage Dockerfile
# ----------------------------------------------------------------------------
# Stage `dev` — Vite dev server :5173 c HMR. Используется в docker-compose
# (target: dev). Стадия `build` собирает production-bundle в /app/dist/ —
# его подхватит Nginx или FastAPI StaticFiles в Phase 5.
# ============================================================================

# ---------------------------------------------------------------------- build
FROM node:20-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install
COPY apps/web/ ./
RUN npm run build

# ------------------------------------------------------------------------ dev
FROM node:20-alpine AS dev
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install
EXPOSE 5173
# Bind-mount исходников из docker-compose делает COPY избыточным,
# но он нужен на случай ad-hoc запуска `docker run`.
COPY apps/web/ ./
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ------------------------------------------------------------- (Phase 5) prod
# В Phase 5 будет добавлена стадия `serve` с Nginx, копирующая dist/
# из стадии build. Пока (Phase 4) production-обслуживание SPA лежит
# на FastAPI StaticFiles в api-контейнере.
