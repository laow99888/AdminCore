# AdminCore 前端镜像：构建 + Nginx 托管
# Node 版本与 版本要求.md 基线一致（24.x）
FROM node:24.21.0-slim AS build

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
COPY vendor/ ./vendor/
RUN npm ci

COPY . .
RUN npm run build

# ---- 运行阶段 ----
FROM nginx:1.29.8-alpine

COPY --from=build /app/dist /usr/share/nginx/html
ENV TRUSTED_PROXY_IP=127.0.0.1
ENV REALTIME_UPSTREAM=backend:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY spa-csp.conf /etc/nginx/spa-csp.conf

EXPOSE 80
