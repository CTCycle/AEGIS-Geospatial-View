FROM node:22.12.0-alpine3.20 AS build

WORKDIR /app/client

COPY AEGIS/client/package.json AEGIS/client/package-lock.json ./
RUN npm ci

COPY AEGIS/client ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27.4-alpine

COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/client/dist /usr/share/nginx/html

EXPOSE 80
