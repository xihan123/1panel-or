#!/usr/bin/env bash
# 检查 1panel/openresty 上游是否有新版本，并判断本仓库是否需要重新构建。
#
# 满足以下任一条件就构建：
#   1. 上游最新 tag 还没构建过       -> 基础镜像内容变了
#   2. 模块清单指纹对应的 tag 不存在  -> 模块定义变了
#   3. FORCE=true                    -> 手动强制
#
# 结果写入 $GITHUB_OUTPUT，同时打印到终端。
set -euo pipefail

UPSTREAM_REPO="${UPSTREAM_REPO:-1panel/openresty}"
# CI 的 ubuntu runner 上是 python3，Windows 本地通常只有 python
PYTHON="${PYTHON:-python3}"
# 上游 tag 形如 1.31.1.1-2-4-noble；排除 -amd64 / -arm64 变体
TAG_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+-[0-9]+-[0-9]+-(noble|focal|jammy)$'

FORCE="${FORCE:-false}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-}"
IMAGE_NAME="${IMAGE_NAME:-openresty}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES_PY="${SCRIPT_DIR}/modules.py"

log() { printf '%s\n' "$*" >&2; }

emit() {
    # $GITHUB_OUTPUT 里的多行值必须用 heredoc 分隔符语法
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        {
            printf '%s<<__EOF__\n' "$1"
            printf '%s\n' "$2"
            printf '__EOF__\n'
        } >> "$GITHUB_OUTPUT"
    fi
    printf '%s=%s\n' "$1" "$2"
}

tag_exists() {
    [[ -z "$1" ]] && return 1
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 \
        "https://hub.docker.com/v2/repositories/$1/${IMAGE_NAME}/tags/$2")"
    [[ "$code" == "200" ]]
}

upstream_tag="$(curl -sS --max-time 30 \
    "https://hub.docker.com/v2/repositories/${UPSTREAM_REPO}/tags?page_size=100&ordering=last_updated" \
    | "$PYTHON" -c "
import json, re, sys
pattern = re.compile(r'''${TAG_PATTERN}''')
for entry in json.load(sys.stdin).get('results', []):
    if pattern.match(entry.get('name', '')):
        print(entry['name'])
        break
")"

if [[ -z "$upstream_tag" ]]; then
    log "::error::上游没有匹配 ${TAG_PATTERN} 的 tag"
    exit 1
fi

# 1.31.1.1-2-4-noble -> RESTY_VERSION=1.31.1.1, UBUNTU_CODENAME=noble
resty_version="${upstream_tag%%-*}"
ubuntu_codename="${upstream_tag##*-}"

module_hash="$("$PYTHON" "$MODULES_PY" hash)"
module_count="$("$PYTHON" "$MODULES_PY" count)"
module_list="$("$PYTHON" "$MODULES_PY" list)"
mod_tag="${upstream_tag}-mod${module_hash}"
modules_present="false"
[[ "$module_count" -gt 0 ]] && modules_present="true"

if [[ "$FORCE" == "true" ]]; then
    should_build="true"; reason="手动触发，强制构建"
elif ! tag_exists "$IMAGE_NAMESPACE" "$upstream_tag"; then
    should_build="true"; reason="上游 tag ${upstream_tag} 尚未构建"
elif [[ "$modules_present" == "true" ]] && ! tag_exists "$IMAGE_NAMESPACE" "$mod_tag"; then
    should_build="true"; reason="模块清单已变更（${mod_tag} 不存在）"
else
    should_build="false"; reason="上游与模块清单均无变化"
fi

log "上游 tag: ${upstream_tag}  模块数: ${module_count}  指纹: ${module_hash}"
log "判定: ${reason}"

emit "should_build" "$should_build"
emit "reason" "$reason"
emit "upstream_tag" "$upstream_tag"
emit "resty_version" "$resty_version"
emit "ubuntu_codename" "$ubuntu_codename"
emit "module_hash" "$module_hash"
emit "module_count" "$module_count"
emit "modules_present" "$modules_present"
emit "mod_tag" "$mod_tag"
emit "module_list" "$module_list"
