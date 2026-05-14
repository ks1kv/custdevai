# ============================================================================
# CustDevAI Web SPA — multi-stage Dockerfile
# ----------------------------------------------------------------------------
# Стадии:
#   build  — компилирует SPA в /app/dist/ (Vite production).
#   dev    — Vite dev server :5173 с HMR (используется в docker-compose dev).
#   serve  — Nginx serving production dist + reverse-proxy на API (Phase 5).
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

# ---------------------------------------------------------------------- serve
# Production-стадия: Nginx 1.27-alpine, копирует dist/ из стадии build.
# nginx.conf проксирует /api/* на upstream api:8000 и обслуживает SPA
# (try_files index.html fallback для React Router).
FROM nginx:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx/nginx.conf /etc/nginx/templates/default.conf.template
# Эти ENV подставляются в nginx.conf через envsubst при старте.
ENV NGINX_API_UPSTREAM=api:8000
ENV NGINX_SERVER_NAME=_
EXPOSE 80 443
