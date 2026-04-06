FROM node:20-alpine AS build
WORKDIR /app
# Install at workspace root so node_modules is visible to all app source files
COPY package.json ./
COPY apps/portal/package.json apps/portal/package.json
RUN npm install
COPY . .
WORKDIR /app/apps/portal
RUN npm run build

FROM nginx:alpine
COPY apps/portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/portal/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --from=build /app/apps/portal/dist/exam-corrector-frontend/browser /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
