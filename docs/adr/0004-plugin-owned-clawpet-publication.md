# 插件拥有固定的 ClawPet 发布

`clawchat-pet` 的网页只通过 Liveware 提供给 ClawChat，因此发布生命周期属于插件，而不是一次性的人工部署步骤。

插件启动本地宠物服务和 Liveware agent，并在后台幂等确保：Liveware 已登录、存在且仅复用名称精确为 `ClawPet` 的 app、该 app 绑定到 `http://127.0.0.1:54321`、对应 URL 已以 `ClawPet` 注册到 ClawChat。Liveware CLI 不提供 binding 查询，所以每次启动都安全地刷新 binding；app 创建和 ClawChat 注册只在缺失或信息过期时执行。

发布身份不随当前宠物、玩法场景或皮肤变化。插件不会删除或接管其他名称的 Liveware app。外部发布失败会被记录，但不得阻止 Gateway、宠物服务或现有 Liveware agent 启动。
