# Hermes 插件独占拥有宠物 server

clawchat-pet server 由当前 Hermes 插件进程启动、拥有并停止，不复用或接管外部 standalone server。我们选择生命周期一致性而不是外部进程复用：Hermes 退出时 server 必须同步停止，端口已被占用时明确失败；因此短时活动状态可以只保存在内存中，并在进程重启时可靠地回到入定。
