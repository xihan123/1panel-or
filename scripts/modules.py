#!/usr/bin/env python3
"""modules.json 处理工具，见 --help。

加载配置的命名与路径规则必须与 1Panel 的 nginx_module.go 一致，产物才能落进
1Panel 的原生机制：文件名 1panel-module-<loadOrder 补零4位>-<modulePathName>.conf，
内容为 load_module /usr/local/openresty/nginx/modules/1panel/<modulePathName>/<file>.so，
modulePathName = 清洗后的 name 截断 48 字符 + "-" + sha256(name) 前 8 位十六进制。
http 上下文指令另放 http.d/1panel-http-<httpLoadOrder 补零4位>-<modulePathName>.conf。
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys

PACKAGE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9+.-]*$")   # 1Panel NginxModulePackagePattern
ARTIFACT_PATTERN = re.compile(r"^[a-zA-Z0-9_./+-]+\.so$")       # 1Panel NginxModuleArtifactPattern

MODULE_CONTAINER_ROOT = "/usr/local/openresty/nginx/modules/1panel"
MODULE_CONF_PREFIX = "1panel-module-"
HTTP_CONF_PREFIX = "1panel-http-"
CONF_HEADER = "# 由 1panel-or 生成\n"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fail(message):
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_modules(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    modules = data.get("modules")
    if not isinstance(modules, list):
        fail(f"{path}: 顶层必须包含 modules 数组")

    seen = set()
    for module in modules:
        name = module.get("name", "")
        if not isinstance(name, str) or not name:
            fail(f"{path}: 模块 name 必须是非空字符串")
        if name in seen:
            fail(f"{path}: 模块 name 重复：{name}")
        seen.add(name)

        source = module.get("source") or {}
        if source.get("type") not in ("image", "git"):
            fail(f"{name}: source.type 必须是 image 或 git")
        if not source.get("dir"):
            fail(f"{name}: source.dir 不能为空")
        if source["type"] == "git" and not (source.get("url") and source.get("ref")):
            fail(f"{name}: source.url 与 source.ref 都不能为空（ref 请固定到 tag 或 commit）")

        packages = module.get("packages", [])
        if not isinstance(packages, list):
            fail(f"{name}: packages 必须是数组")
        for package in packages:
            if not isinstance(package, str) or not PACKAGE_PATTERN.match(package):
                fail(f"{name}: 非法的包名 {package!r}")

        if "--add-dynamic-module=" not in module.get("params", ""):
            fail(f"{name}: params 必须包含 --add-dynamic-module=")

        for key in ("loadOrder", "httpLoadOrder"):
            value = module.get(key, module.get("loadOrder"))
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
                fail(f"{name}: {key} 必须是 0-9999 的整数")

        if not isinstance(module.get("script", ""), str):
            fail(f"{name}: script 必须是字符串")

    return modules


def sanitize_path_part(value):
    """对应 1Panel 的 sanitizeModulePathPart：非 [A-Za-z0-9.-_] 一律换成 -。"""
    return "".join(
        char if (char.isascii() and (char.isalnum() or char in ".-_")) else "-"
        for char in value
    ).strip("-")


def module_path_name(name):
    """对应 1Panel 的 nginxModulePathName。"""
    return f"{sanitize_path_part(name)[:48] or 'module'}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"


def module_hash(modules):
    canonical = json.dumps(modules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def write_file(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def cmd_hash(args):
    print(module_hash(load_modules(args.modules)))


def cmd_count(args):
    print(len(load_modules(args.modules)))


def cmd_list(args):
    """Markdown 表格行，供 Release 正文使用。"""
    modules = sorted(load_modules(args.modules), key=lambda m: (m["loadOrder"], m["name"]))
    for module in modules:
        print(f"| `{module['name']}` | {module['loadOrder']} |")


def cmd_prepare(args):
    # 一次 docker build 只编译一个模块，这样 /out 顶层的 .so 天然属于该模块
    modules = sorted(load_modules(args.modules), key=lambda m: (m["loadOrder"], m["name"]))
    root = os.path.join(args.ctx, "modules")

    entries = []
    for module in modules:
        path_name = module_path_name(module["name"])
        module_dir = os.path.join(root, path_name)
        tmp_dir = os.path.join(module_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        source = module["source"]
        lines = ["#!/bin/bash", "set -euo pipefail", ""]
        if source["type"] == "git":
            clone = ["git", "clone", "--depth", "1", "--branch", source["ref"]]
            if source.get("recursive"):
                clone.append("--recurse-submodules")
            clone += [source["url"], source["dir"]]
            lines += [f"rm -rf {shlex.quote(source['dir'])}",
                      " ".join(shlex.quote(part) for part in clone)]
        else:
            # 源码已由 Dockerfile 从基础镜像 COPY 进来
            lines.append(f"test -d {shlex.quote(source['dir'])}")
        if module.get("script"):
            lines.append(module["script"].strip())
        lines.append("")

        write_file(os.path.join(tmp_dir, "module-pre.sh"), "\n".join(lines))
        write_file(os.path.join(tmp_dir, "module-config.args"),
                   "\n".join(shlex.split(module["params"])) + "\n")
        write_file(os.path.join(module_dir, "packages.txt"),
                   " ".join(module.get("packages", [])) + "\n")
        entries.append((path_name, module["name"]))

    write_file(os.path.join(args.ctx, "module-dirs.txt"),
               "".join(f"{path}\t{name}\n" for path, name in entries))

    print(f"构建上下文：{args.ctx}（{len(entries)} 个模块）")
    for path_name, name in entries:
        print(f"  {path_name}  {name}")


def cmd_loadconf(args):
    modules = load_modules(args.modules)
    enabled_dir = os.path.join(args.out, "modules-enabled")
    http_dir = os.path.join(args.out, "http.d")
    modules_dir = os.path.join(args.out, "modules")
    for directory in (enabled_dir, http_dir, modules_dir):
        os.makedirs(directory, exist_ok=True)

    # 清掉上一轮的产物，避免残留的 conf 导致 load_module 重复
    for directory, prefix in ((enabled_dir, MODULE_CONF_PREFIX), (http_dir, HTTP_CONF_PREFIX)):
        for entry in os.listdir(directory):
            if entry.startswith(prefix):
                os.remove(os.path.join(directory, entry))
    for entry in os.listdir(modules_dir):
        shutil.rmtree(os.path.join(modules_dir, entry), ignore_errors=True)

    for module in modules:
        name = module["name"]
        path_name = module_path_name(name)
        source_dir = os.path.join(args.compiled, path_name)
        if not os.path.isdir(source_dir):
            fail(f"{name}: 找不到编译产物目录 {source_dir}")

        # 顶层 .so 是模块本体，lib/ 下是依赖库，靠 rpath $ORIGIN/lib 解析
        artifacts = sorted(
            entry for entry in os.listdir(source_dir)
            if entry.endswith(".so") and os.path.isfile(os.path.join(source_dir, entry))
        )
        if not artifacts:
            fail(f"{name}: {source_dir} 下没有 .so 产物")
        for artifact in artifacts:
            if not ARTIFACT_PATTERN.match(artifact):
                fail(f"{name}: 产物文件名不合法：{artifact}")

        shutil.copytree(source_dir, os.path.join(modules_dir, path_name))

        conf_name = f"{MODULE_CONF_PREFIX}{module['loadOrder']:04d}-{path_name}.conf"
        write_file(os.path.join(enabled_dir, conf_name),
                   CONF_HEADER + "".join(
                       f"load_module {MODULE_CONTAINER_ROOT}/{path_name}/{a};\n" for a in artifacts))

        http_config = module.get("httpConfig") or []
        if http_config:
            http_name = f"{HTTP_CONF_PREFIX}{module.get('httpLoadOrder', module['loadOrder']):04d}-{path_name}.conf"
            write_file(os.path.join(http_dir, http_name),
                       CONF_HEADER + "".join(f"{line}\n" for line in http_config))

        print(f"{name}: {', '.join(artifacts)}")
        lib_dir = os.path.join(source_dir, "lib")
        if os.path.isdir(lib_dir):
            print(f"  lib/: {', '.join(sorted(os.listdir(lib_dir)))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--modules", default=os.path.join(REPO_ROOT, "modules.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("hash", parents=[common]).set_defaults(func=cmd_hash)
    subparsers.add_parser("count", parents=[common]).set_defaults(func=cmd_count)
    subparsers.add_parser("list", parents=[common]).set_defaults(func=cmd_list)

    prepare = subparsers.add_parser("prepare", parents=[common])
    prepare.add_argument("--ctx", required=True)
    prepare.set_defaults(func=cmd_prepare)

    loadconf = subparsers.add_parser("loadconf", parents=[common])
    loadconf.add_argument("--out", required=True)
    loadconf.add_argument("--compiled", required=True)
    loadconf.set_defaults(func=cmd_loadconf)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
