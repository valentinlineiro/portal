FROM node:20-alpine AS build
WORKDIR /app/apps/portal

# Install portal dependencies (includes Angular CLI)
COPY apps/portal/package.json ./package.json
RUN npm install

# Copy portal source and build
COPY apps/portal/ ./
RUN npm run build

FROM nginx:alpine
COPY apps/portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/portal/dist/exam-corrector-frontend/browser /usr/share/nginx/html
EXPOSE 80
