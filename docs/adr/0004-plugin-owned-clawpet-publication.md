# 插件拥有固定的 ClawPet 发布

`clawchat-pet` 的网页只通过 Liveware 提供给 ClawChat，因此发布生命周期属于插件，而不是一次性的人工部署步骤。

插件注册时启动本地宠物服务，并把配套的 `clawchat-pet-startup` Gateway hook 幂等安装到当前 Hermes home。Gateway 平台连接完成并发出 `gateway:startup` 后，该 hook 才在后台启动 Liveware agent，并幂等确保：Liveware 已登录、存在且仅复用名称精确为 `ClawPet` 的 app、该 app 绑定到 `http://127.0.0.1:54321`、对应 URL 已以 `ClawPet` 注册到 ClawChat。普通 Hermes CLI 加载插件时不启动 Liveware。Liveware CLI 不提供 binding 查询，所以每次 Gateway 启动都安全地刷新 binding；app 创建和 ClawChat 注册只在缺失或信息过期时执行。

发布身份不随当前宠物、玩法场景或皮肤变化。插件不会删除或接管其他名称的 Liveware app。安装后的 Gateway hook 以本次进程中插件成功注册为启用条件，因此禁用插件后遗留的 hook 不执行。Liveware agent 或外部发布失败会被记录，但不得阻止 Gateway 或宠物服务启动。
