FROM python:3.12-alpine AS builder

WORKDIR /src
COPY . .

RUN python docker/build_vcards.py /src /out /nginx-generated

FROM nginx:1.27-alpine

COPY --from=builder /nginx-generated/ /etc/nginx/conf.d/
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /out /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
