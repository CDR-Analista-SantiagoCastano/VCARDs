FROM nginx:1.27-alpine

# Serve the static business card files from nginx default web root
WORKDIR /usr/share/nginx/html

RUN rm -rf ./*
COPY . .

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
