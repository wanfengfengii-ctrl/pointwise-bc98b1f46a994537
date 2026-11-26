# 榆桥读剧联排服务

剧团舞监从导演提交的读本发行正式版，为两处提词台开排。演员领取角色单，用原预取号亮词。舞监可以补设一个指定引句，收班时按实显记录查漏，并把固定摘录交给次班。

## 运行

使用 Python 3.11 标准库。以下命令从项目根目录运行。

```sh
python3 -B check_project.py
python3 -B -m call.runtime demo
```

演示从 `samples/rehearsal.json` 通过环回 HTTP 录入读本并开排。甲先亮出同文提示 A0，乙原预取的 B1 仍等待指定的 A1。乙先亮无关的 B0，甲实际亮出 A1 后，乙按原号亮出 B1。演示用 `samples/expected-excerpt.json` 核对签发和重开后的复领结果。

持续运行时，使用同一个库目录在三个 shell 分别启动两台和排练台。默认 HTTP 端口为 8761、8762、8760，均绑定 `127.0.0.1`。端口可用 `--left-port`、`--right-port`、`--coordinator-port` 覆盖，三个命令须使用相同配置。

```sh
python3 -B -m call.runtime --root ./.rehearsal init
python3 -B -m call.runtime --root ./.rehearsal terminal left
python3 -B -m call.runtime --root ./.rehearsal terminal right
python3 -B -m call.runtime --root ./.rehearsal coordinator
```

使用原目录重启可复领已提交记录。`init` 只创建缺失的目录和表。样例数据通过公开入口显式录入。

## 排练台 API

所有入口使用 `POST /<操作>`，请求和响应均为 UTF-8 JSON 对象。标识符是非空字符串，按原值比较。以下请求以全新库为例。

| 操作 | 请求字段 | 成功结果 |
| --- | --- | --- |
| `release` | `script`、`roles`、`cues`，格式见样例 | `edition` 冻结版号，例如 `V1` |
| `open` | `edition`、`bindings`。绑定形如 `{"terminal":"left","role":"甲","station":"left"}` | `session` 场次号，例如 `S1`，及 `edition` |
| `sheet` | `session`、`terminal` | 场次、正式版、角色、端名和有序 `cues` |
| `preload` | `session`、`terminal`、`cue`、`request` | `preloaded` 及原身份和文字 |
| `amend` | `session`、`target`、`predecessor`、`request` | `pending`、`applied` 或 `rejected`，带原身份，业务拒绝带 `reason` |
| `show` | 与 `preload` 相同的四个身份字段 | `waiting`，或 `shown` 和 `receipt` |
| `close` | `session` | 带 `excerpt` 摘录号、正式版和角色核对内容的固定摘录 |
| `lookup` | `session`、`kind`、`id`。类型为 `amendment`、`receipt` 或 `excerpt` | 对应原结局、已提交实显回执或固定摘录 |

请求示例 `{"session":"S1","target":"B1","predecessor":"A1","request":"M"}`。两处绑定须使用不同的端名、角色和运行端。运行端是 `left` 与 `right`。端名等于运行端时可省略 `station`，也可给同一运行端在不同场次配置不同的端名。角色必须在冻结版声明，已绑定的空角色获得空单。后续发行同一读本不会更改既有场次。

提示含 `cue`、`role`、`text`。整份读本可省略 `position` 并按列表从 1 编号，或逐条提供严格递增的整数 `position`。提示号版内唯一，文字可重复。角色单保留读本顺序。改单只能指定同场有归属台且原序更早的提示。每个目标最多采用一个前置关系。目标已经实显时返回 `rejected` 和 `already_shown`，已有前置时返回 `already_has_predecessor`。结局待查时可按号查询或同参重提。以目标端采用前置与首次实显的持久顺序裁定。前置须按指定身份实际亮出，旧预取在条件满足后仍用原号 `show`。端不可查时没有前置证据，原待办可继续重试。

实显回执保留 `session`、`terminal`、`station`、`cue`、`request`、`sequence` 和原文字。`sequence` 是各端独立递增的正整数。等待中查询实显原号返回 404。端侧提交后 HTTP 若失答，可重发原请求或查询原回执。收班以该次读取并核清的两端实显为准，已亮按各端真实序号列出，漏亮按角色单原序列出。每次成功收班签发固定摘录，之后继续练读不改变已签摘录。端账暂不可查时可在恢复后重试收班。

错误响应带 `error`。输入非法为 400，未知或不匹配身份为 404，原号参数冲突或另一原号已亮同提示为 409，服务或完整端账暂不可用为 503。排练台与两处提词端分别提交各自的数据库。演示及测试使用临时目录和环回端口。
