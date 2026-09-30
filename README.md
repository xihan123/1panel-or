![1panel-or](https://socialify.git.ci/xihan123/1panel-or/image?description=1&forks=1&issues=1&language=1&name=1&owner=1&pulls=1&stargazers=1&theme=Auto)

[![Build and Publish](https://github.com/xihan123/1panel-or/actions/workflows/build.yml/badge.svg)](https://github.com/xihan123/1panel-or/actions/workflows/build.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/xihan123/openresty)](https://hub.docker.com/r/xihan123/openresty)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

## 1panel-or（1Panel OpenResty 自定义模块镜像）

自动跟随 `1panel/openresty` 上游更新，并把自定义 Nginx 动态模块预先编译好。模块清单写在 [`modules.json`](modules.json)，改完推送即触发重建

1Panel 的 `1panel/openresty` 镜像内置了 `ngx_brotli`、`rtmp`、`web_dav`、`geoip2`、`http_substitutions_filter` 五个模块的源码，但运行镜像里只预置了 `ngx_brotli` 的 `.so`，其余模块要在面板里手动触发编译，重装或升级后得重来。本仓库把这一步搬到 CI

产物有两个去处：

| 产物 | 用途 |
| --- | --- |
| 镜像 `xihan123/openresty` | 自带模块，适用于 `docker run` 或自写 compose |
| Release 里的制品包 | 放进 1Panel 宿主机目录，走 1Panel 原生机制，无需改 compose |

## 在 1Panel 中使用

从 [Releases](https://github.com/xihan123/1panel-or/releases) 下载对应版本的制品包，按包内 `README.txt` 放置：

```bash
TAG=1.31.1.1-2-4-noble
INSTALL=/opt/1panel/apps/openresty/openresty

tar -xzf 1panel-openresty-${TAG}-modules.tar.gz -C /tmp/or-modules

# 模块本体，按机器架构选 amd64 或 arm64
for d in /tmp/or-modules/amd64/*/; do
  name=$(basename "$d")
  mkdir -p "$INSTALL/modules/manual/$name"
  cp "$d"*.so "$INSTALL/modules/manual/$name/"
done

mkdir -p "$INSTALL/conf/modules-enabled" "$INSTALL/conf/http.d"
cp /tmp/or-modules/modules-enabled/*.conf "$INSTALL/conf/modules-enabled/"
cp /tmp/or-modules/http.d/*.conf "$INSTALL/conf/http.d/" 2>/dev/null || true

cd "$INSTALL" && docker compose restart
```

确认模块已加载：

```bash
docker exec 1Panel-openresty /usr/local/openresty/nginx/sbin/nginx -T | grep load_module
```

1Panel 会清理 `conf/modules-enabled/` 下所有 `1panel-module-` 开头的文件，如果面板里对同名模块执行过编译，配置可能被覆盖，重新复制一次即可

## 直接使用镜像

```bash
docker run -d --name openresty -p 80:80 -p 443:443 \
  -v "$PWD/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro" \
  xihan123/openresty:1.31.1.1-2-4-noble
```

镜像内置的模块会自动加载

## 标签

| 标签 | 说明 |
| --- | --- |
| `1.31.1.1-2-4-noble` | 对应上游同名标签，内容为上游镜像 + 本项目模块 |
| `latest` | 最新构建 |
| `1.31.1.1-2-4-noble-modcf9f38bc650f` | 带模块清单指纹的不可变标签，`modules.json` 一变它就变 |

模块清单为空时不产生 `-mod` 后缀的标签

## 增删模块

```jsonc
{
  "modules": [
    {
      "name": "geoip2",
      "source": {
        "type": "git",                        // git = 构建时 clone；image = 用基础镜像里已内置的源码
        "url": "https://github.com/leev/ngx_http_geoip2_module.git",
        "ref": "3.4",                         // 固定到 tag 或 commit
        "dir": "/tmp/ngx_http_geoip2_module"  // clone 到构建容器里的位置
      },
      "packages": ["libmaxminddb-dev"],       // 编译期 apt 依赖
      "params": "--add-dynamic-module=/tmp/ngx_http_geoip2_module",
      "script": "find /usr/lib -maxdepth 2 -name 'libmaxminddb*.so*' -exec cp -a {} /usr/local/lib/ \\;",
      "loadOrder": 40,                        // load_module 顺序，0-9999，小的先加载
      "httpConfig": []                        // 可选的 http 上下文指令
    }
  ]
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 模块名，全局唯一 |
| `source.type` | 是 | `git`（clone 源码）或 `image`（源码已在基础镜像里，如 `ngx_brotli`） |
| `source.url` / `source.ref` | `git` 时 | 仓库地址与 ref，请固定 ref，用分支会导致构建结果不可复现 |
| `source.dir` | 是 | 源码在构建容器里的路径 |
| `source.recursive` | 否 | 是否 `--recurse-submodules` |
| `packages` | 否 | 编译期 apt 依赖 |
| `params` | 是 | 传给 `./configure` 的参数，必须含 `--add-dynamic-module=` |
| `script` | 否 | `./configure` 之前执行的 shell 片段，用于准备源码或拷贝依赖库 |
| `loadOrder` | 是 | `load_module` 顺序，0-9999 |
| `httpLoadOrder` | 否 | http 指令的顺序，默认取 `loadOrder` |
| `httpConfig` | 否 | 写入 `http.d/` 的 http 上下文指令 |

模块若依赖外部 `.so`，用 `script` 把它拷进 `/usr/local/lib`，Dockerfile 会把该目录下的库收进产物的 `lib/`，并给模块打上 `rpath=$ORIGIN/lib`，所以制品是自包含的

`ngx_brotli` 用 `"type": "image"` 是因为它的源码连同已编译好的 brotli 依赖库都在基础镜像的 `/usr/local/openresty/modules/ngx_brotli` 下，直接复用即可，既不用联网 clone，也不受上游 `google/ngx_brotli`（master 停留在 2023 年）的影响

## 工作流

```
check          查上游标签、算模块指纹、判断是否需要构建
  ↓
build-modules  按架构原生编译每个模块
  ↓
push           各架构分别推送 <tag>-amd64 / <tag>-arm64
  ↓
manifest       合并多架构 manifest → <tag> / latest / <tag>-mod<hash>，并冒烟测试
  ↓
release        打包 .so 与 conf 上传到 GitHub Release
```

触发方式：定时（每天 UTC 02:23 / 北京时间 10:23）、手动（可勾选 `force` 强制重建）、推送非 `.md` 文件

## 本地构建

```bash
python scripts/modules.py prepare --ctx build/ctx

for d in build/ctx/modules/*/; do
  curl -fsSL https://openresty.org/download/openresty-1.31.1.1.tar.gz \
    -o "${d}tmp/openresty-1.31.1.1.tar.gz"
done

docker buildx build --file docker/Dockerfile.modules --target module-export \
  --platform linux/amd64 \
  --build-arg PANEL_OPENRESTY_VERSION=1.31.1.1-2-4-noble \
  --build-arg RESTY_VERSION=1.31.1.1 \
  --build-arg RESTY_ADD_PACKAGE_BUILDDEPS="$(cat build/ctx/modules/geoip2-*/packages.txt)" \
  --output type=local,dest=build/compiled/geoip2-c938ae6e \
  build/ctx/modules/geoip2-c938ae6e

python scripts/modules.py loadconf --out build/image --compiled build/compiled

docker build --file docker/Dockerfile \
  --build-arg PANEL_OPENRESTY_VERSION=1.31.1.1-2-4-noble \
  --build-arg MODULES_PRESENT=1 \
  -t 1panel-or:test build/image
```

## 需要的仓库密钥

| 密钥 | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名，同时用作镜像路径前缀 |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token，权限需 Read & Write |

## 实现说明

模块编译流程复刻了 1Panel 的 `apps/openresty/*/build/Dockerfile.modules` 契约（`tmp/module-pre.sh` + `tmp/module-config.args` + `/out` 产物布局），加载配置的命名也与其 `nginx_module.go` 一致，产物才能直接落进 1Panel 的原生机制

选动态模块而不是静态编译，是因为动态模块只需针对 `--with-compat` 编译，不用重编整个 nginx，单模块构建从 1-2 小时降到 1 分钟左右，也不受上游 Dockerfile 变更影响

## 致谢

- [1Panel](https://github.com/1Panel-dev/1Panel) - 模块加载与动态编译的机制来源
- [1Panel-dev/appstore](https://github.com/1Panel-dev/appstore) - openresty 镜像的构建脚本
- [openresty/docker-openresty](https://github.com/openresty/docker-openresty) - 基础镜像
