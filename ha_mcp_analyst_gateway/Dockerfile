ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apk add --no-cache nginx tailscale ca-certificates curl jq
COPY rootfs /
RUN chmod 0755 /etc/services.d/gateway/run /etc/services.d/tailscaled/run /usr/local/bin/gateway-diagnostics.sh
