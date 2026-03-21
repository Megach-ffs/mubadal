FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html

RUN printf 'server {\n\
  listen 4000;\n\
  location / {\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
  location /api/ {\n\
    proxy_pass http://backend:8000;\n\
    proxy_set_header Host $host;\n\
    proxy_set_header X-Real-IP $remote_addr;\n\
    client_max_body_size 200m;\n\
    proxy_read_timeout 120s;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 4000
CMD ["nginx", "-g", "daemon off;"]
