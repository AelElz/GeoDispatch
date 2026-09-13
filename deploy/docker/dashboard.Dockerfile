FROM node:22-alpine AS build

WORKDIR /src
COPY dashboard/interface/package*.json ./
RUN npm ci
COPY dashboard/interface/ .
ARG VITE_WS_URL=ws://localhost:3000/ws
ENV VITE_WS_URL=$VITE_WS_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/dashboard-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 80
