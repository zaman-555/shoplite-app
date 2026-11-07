FROM nginx:1.27-alpine AS assets

COPY services/web/index.html services/web/styles.css services/web/app.js /assets/
COPY services/web/nginx.conf /tmp/default.conf
COPY services/web/nginx.main.conf /tmp/nginx.conf

FROM nginx:1.27-alpine AS runtime

COPY --from=assets /tmp/nginx.conf /etc/nginx/nginx.conf
COPY --from=assets /tmp/default.conf /etc/nginx/conf.d/default.conf
COPY --from=assets /assets/ /usr/share/nginx/html/

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

ENTRYPOINT ["nginx", "-g", "daemon off;"]
