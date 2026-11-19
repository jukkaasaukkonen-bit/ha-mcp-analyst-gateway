ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apk add --no-cache python3 tailscale jq ca-certificates
COPY rootfs /
RUN chmod 0755 /etc/services.d/report-mcp/run /usr/local/bin/report_mcp.py
