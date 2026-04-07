FROM node:20-alpine AS attendance-build
WORKDIR /app/apps/attendance-checker
COPY apps/attendance-checker/package.json ./
RUN npm install
COPY apps/attendance-checker/ ./
RUN npm run build

FROM node:20-alpine AS portal-build
WORKDIR /app/apps/portal
COPY apps/portal/package.json ./package.json
RUN npm install
COPY apps/portal/ ./
COPY --from=attendance-build /app/apps/attendance-checker/dist/element/ public/apps/attendance-checker/element/
RUN npm run build

FROM nginx:alpine
COPY apps/portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=portal-build /app/apps/portal/dist/exam-corrector-frontend/browser /usr/share/nginx/html
EXPOSE 80
