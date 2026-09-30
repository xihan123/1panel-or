1panel/openresty @TAG@ 自定义模块制品包
=========================================

1Panel 的 docker-compose.yml 把 conf/modules-enabled 与 modules 两个目录整体
bind mount 进容器，宿主机上的空目录会遮蔽镜像内置的配置。所以本制品包不是给
镜像用的，而是让你把文件直接放进宿主机对应目录，无需修改 docker-compose.yml。

放置步骤
--------
假设 1Panel 的 openresty 安装目录为 INSTALL（通常是
/opt/1panel/apps/openresty/openresty）：

1. 模块本体，按机器架构选择 amd64 或 arm64：

     for d in amd64/*/; do
       name=$(basename "$d")
       mkdir -p "INSTALL/modules/manual/$name"
       cp "$d"*.so "INSTALL/modules/manual/$name/"
     done

2. load_module 配置：

     mkdir -p INSTALL/conf/modules-enabled
     cp modules-enabled/*.conf INSTALL/conf/modules-enabled/

3. 如有 http.d/，把里面的指令并入 INSTALL/conf/http.d/

4. 重启容器：

     cd INSTALL && docker compose restart

验证：

  docker exec 1Panel-openresty /usr/local/openresty/nginx/sbin/nginx -T | grep load_module

注意事项
--------
* 1Panel 会清理 conf/modules-enabled 下所有以 1panel-module- 开头的文件。如果
  你在面板里对同名模块执行过编译，可能会覆盖本制品包放置的配置，重新复制一次即可。
* 本制品包不含 1Panel 的 module.json 状态文件，所以面板界面不会把这些模块显示为
  「已启用」。模块本身是正常加载的，用上面的 nginx -T 可以确认。
* 模块与 OpenResty 版本强绑定，升级 OpenResty 后需要换用对应版本的新制品包。
