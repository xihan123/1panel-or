# 在 1panel/openresty 上游镜像上追加本项目编译好的动态模块。
#
# 构建上下文由 scripts/modules.py loadconf 生成：modules/（模块本体与 lib/ 依赖库）、
# modules-enabled/（load_module 指令）、http.d/（http 上下文指令）。
#
# 1Panel 的 compose 会把 modules 与 modules-enabled 两个目录整体 bind mount 进容器，
# 宿主机空目录会遮蔽镜像里的内容。所以内置的 load_module 只在不用 1Panel compose 时
# 生效，1Panel 场景请用 Release 里的制品包。

ARG PANEL_OPENRESTY_VERSION
FROM 1panel/openresty:${PANEL_OPENRESTY_VERSION}

ARG MODULES_PRESENT=0

LABEL org.opencontainers.image.title="1panel-openresty-custom" \
      org.opencontainers.image.description="1panel/openresty with custom dynamic modules pre-built" \
      org.opencontainers.image.source="https://github.com/xihan123/1panel-or"

ENV NGINX_ROOT=/usr/local/openresty/nginx \
    MODULE_CONTAINER_ROOT=/usr/local/openresty/nginx/modules/1panel

COPY modules/ ${MODULE_CONTAINER_ROOT}/
COPY modules-enabled/ ${NGINX_ROOT}/conf/modules-enabled/
COPY http.d/ ${NGINX_ROOT}/conf/http.d/

# 上游 nginx.conf 来自 openresty/docker-openresty，不含这两个 include。load_module 必须
# 在任何 http 块之前被解析，所以插到 events {} 之前；http.d 的指令则要插到 http {} 之内。
# 两个锚点都要求行首即为关键字，避免匹配到文件顶部注释里的示例文本。
RUN set -eux; \
    NGINX_CONF="${NGINX_ROOT}/conf/nginx.conf"; \
    MODULE_INCLUDE='include /usr/local/openresty/nginx/conf/modules-enabled/*.conf;'; \
    HTTP_INCLUDE='include /usr/local/openresty/nginx/conf/http.d/*.conf;'; \
    if ! grep -Fq "$MODULE_INCLUDE" "$NGINX_CONF"; then \
      awk -v inc="$MODULE_INCLUDE" \
        '!done && /^[[:space:]]*events[[:space:]]*\{/ { print inc; print ""; done=1 } { print }' \
        "$NGINX_CONF" > "$NGINX_CONF.tmp"; \
      mv "$NGINX_CONF.tmp" "$NGINX_CONF"; \
    fi; \
    if ! grep -Fq "$HTTP_INCLUDE" "$NGINX_CONF"; then \
      awk -v inc="    $HTTP_INCLUDE" \
        '{ print } !done && /^[[:space:]]*http[[:space:]]*\{/ { print inc; done=1 }' \
        "$NGINX_CONF" > "$NGINX_CONF.tmp"; \
      mv "$NGINX_CONF.tmp" "$NGINX_CONF"; \
    fi; \
    grep -Fn "$MODULE_INCLUDE" "$NGINX_CONF"; \
    grep -Fn "$HTTP_INCLUDE" "$NGINX_CONF"

# load_module 路径错误、ABI 不兼容或依赖库缺失都会在这里暴露
RUN if [ "$MODULES_PRESENT" = "1" ]; then \
      ${NGINX_ROOT}/sbin/nginx -t; \
    fi

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]
STOPSIGNAL SIGQUIT
