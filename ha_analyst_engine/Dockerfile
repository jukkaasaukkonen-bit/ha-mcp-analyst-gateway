ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apk add --no-cache python3 py3-tzdata
COPY rootfs /
RUN chmod +x /etc/services.d/analyst/run
