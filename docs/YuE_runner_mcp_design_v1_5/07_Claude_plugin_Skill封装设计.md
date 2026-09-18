# Claude plugin Skill 封装设计

**版本：1.3｜日期：2026-09-17｜交付类型：独立设计文档。**

## 1. 封装目标

以官方 `skills/yue2-music/SKILL.md` 为业务步骤依据，封装成 Claude plugin Skill。**生成、转录、翻唱、编辑、检查和试听对比的步骤保持原样，只把直接执行模型的入口替换为 agent-sandbox 发布的任务服务。** [S17]

```text
原 Skill：组织请求 → 本地模型脚本 → 检查输出 → 取得产物
封装后：组织同类请求 → 任务服务 → 同样的检查 → 取得同类产物
```

本文件只定义 Skill 内容和服务调用对应关系，不定义独立客户端产品、额外应用接入或第二套业务编排系统。全部 Task 名称及上传扩展是待实施契约；文档不是已发布插件。

## 2. 最小插件结构

```text
yue-task-service/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── yue2-music/
        ├── SKILL.md
        ├── assets/
        │   └── prompt.json
        └── references/
            └── service-api.md
```

`plugin.json` 记录插件名称、版本和描述；`SKILL.md` 沿用原工作流选择、请求组织、乐谱检查与交付规则。`prompt.json` 保留原生请求模板；`service-api.md` 说明下列四个接口与服务参数边界。`.claude-plugin` 与 `skills` 位于同一级。[W01][W02]

原有乐谱编辑、生成与翻唱、试听评估等参考文档按实际引用保留，并保留来源与许可说明。模型安装说明用于服务端部署准备；Skill 使用者无需在调用端安装模型。需要复用的非模型辅助脚本按原用途保留，不额外设计一套客户端 SDK 或客户端服务。

## 3. 原步骤与任务服务入口对照

下表左列来自原 Skill 与已有脚本，右列为本方案服务映射，不是上游新增命令。[S17][S19][S25][S27]

| 原步骤／执行入口 | Claude plugin Skill 中的对应处理 |
|---|---|
| 选择生成、转录、翻唱或编辑流程 | 保持原 Skill 的选择规则 |
| 安装并选择模型环境 | 作为任务服务的部署前提；每个 Task 固定绑定对应 preprocess 与 environment，调用中不安装模型 |
| `run_yue2.py generate --request ... --output ...` | `POST /runner/submit`，`task_name=yue2_task`，`operation=generate` |
| `run_yue2.py plan` | 同一提交入口，`task_name=yue2_task`，`operation=plan` |
| `run_yue2.py all-modes` | 同一提交入口，`task_name=yue2_task`，`operation=all_modes` |
| `run_yue2.py decode` | 同一提交入口，`task_name=yue2_task`，`operation=decode`，引用已完成的原始结果 |
| `transcribe.py <audio> --task ...` | 先通用上传音频，再提交 `task_name=sheetsage2_task`、`operation=transcribe` |
| `abc_tools.py inspect/strip-chords/compare` | 提交 `task_name=yue2_task`、`operation=score_check` 及对应检查动作；保留原来的检查顺序 |
| 修订 ABC、风格或歌词 | 保留原修改步骤与允许变化说明；修改文件通过通用上传产生新资产，不覆盖原稿 |
| 检查结果和读取输出文件 | `GET /runner/result` 取得状态及清单，再按 `task_id + result_source_name` 调用 `GET /runner/result_source` |
| 试听和比较原版／修改版 | 取得对应音频、请求、乐谱和检查报告，继续原试听比较步骤；需要原 `listen.py` 的比较页时，在下载后的结果上复用它，不建设播放器业务模块 |

原 `listen.py` 生成的是本地比较页，不执行模型、不自动发布或上传。该步骤与模型执行入口替换分别处理；模型和乐谱检查任务仍经任务服务调用。[S17]

## 4. 服务调用约定

| 接口 | 状态 | Skill 使用方式 |
|---|---|---|
| `POST /runner/upload` | 拟新增通用接口 | multipart 的 `file`、`user_id`；返回 `asset_id`、`sha256`、`size_bytes` |
| `POST /runner/submit` | 复用入口、扩展模型任务类型 | 提交原生请求与输入引用，保存返回的 `task_id` |
| `GET /runner/result?task_id=...` | 复用入口、扩展资源清单 | 查询真实状态及 `data.result.artifacts` |
| `GET /runner/result_source?task_id=...&result_source_name=...` | 复用 | 按清单真实名称取得对应文件 |

服务地址和用户凭据由调用配置提供，例如拟议配置名 `YUE_TASK_SERVICE_URL`、`YUE_TASK_SERVICE_TOKEN`。不把凭据写进歌词、请求产物、下载地址或明文操作记录。上传 `user_id` 与任务归属均由服务端核对认证主体。

普通文本生成直接提交 `payload.request`，无需先上传文件。音频上传后写入 `payload.audio_asset_id`；修改后的 ABC 上传后写入 `payload.abc_source.asset_id`。已有任务产物可用 `{task_id, result_source_name}` 引用，服务端校验同用户归属后读取。输入路径、模型路径、脚本路径和输出根目录不接受调用方透传。

每个独立执行模型的绑定保持：

```text
yue2_task       → yue2_processor       → /root/yue-env/bin/python
sheetsage2_task → sheetsage2_processor → /root/sheetsage2-env/bin/python
```

YuE2-Vae 随 YuE2 生成链加载；SheetSage2 所需的 MERT-v2-FullSong 父模型由其加载，不在普通生成或翻唱中另加一次 MERT 任务。[S18]

## 5. 保持原业务步骤

### 5.1 生成并保留乐谱

从原模板整理 `style`、`lyrics`、`cot`、`seed` 及已确认支持的其他字段。按需求选择 `full`、`melody` 或 `off`，提交相应生成任务。`full/melody` 和 `off` 的产物差异沿用上游语义，`off` 不虚构可编辑 ABC。[S17][S19]

取得任务标识后查询状态；完成后读取音频、请求、结果元数据和实际存在的乐谱。按原步骤检查截断、符号检查和音乐结果，保留模型／解码器身份。比较多个模式时保留每个模式的结果与失败，不把部分成功说成全部成功。

### 5.2 转录与录音翻唱

上传原音频 → 提交转录任务 → 取得 ABC、转录警告及实际产物 → 检查并按需修正漏音、拍号或调性 → 按原要求去除和弦条件并检查保留声部 → 用已检查的 ABC、目标风格和歌词提交 `cot=melody` 生成 → 取得新音频并试听比较。

需要修订时保留原音频和原始转录；新 ABC 上传为新资产。`strip_chords` 产生新谱后，后续生成必须引用该步骤输出的资源名，不能误用处理前乐谱。转录失败或 ABC 不可用时停止后续采样。保留和声时按原工作流采用完整转录与 `cot=full`，不把它称为仅旋律条件翻唱。[S17]

### 5.3 编辑与再生成

取得原完整计划和基线音频并保留原稿 → 明确允许修改及必须保留的音高、节奏、声部、速度等约束 → 另写 ABC、歌词或风格修改稿 → 上传新谱 → 按原步骤运行 `inspect/compare` → 检查通过或明确记录有意变化后提交修改稿条件生成 → 比较修改前后音频与乐谱。

检查以音乐事件而非字符相等为依据。修改后的乐谱必须真实进入后续生成输入；不能省略 ABC 后生成一份新计划。旧 latent 重解码不等于改词或音乐编辑。上游没有的局部音频修补、声纹保留、音素强制对齐等能力不增加承诺。[S17]

### 5.4 取得可听结果与对比材料

先读任务结果清单，再逐项下载需要的音频、请求、修改前后 ABC、检查报告及实际生成的评估资料。继续原试听比较步骤；需要比较页时复用原辅助方式，不增加新的应用界面或媒体服务。可播放不等于音乐质量合格，符号检查通过不等于声学结果严格实现了所有约束。[S17]

## 6. 异步调用只增加任务等待，不改变业务步骤

首次提交前保存请求键；接受后保存 `task_name`、`task_id`、输入引用和当前步骤。多阶段流程可沿用 `workflow_id` 记录关联；不另建会话或调度模型。

每次等待有上限：建议每5秒查询，最多12次且总等待不超过60秒，任一条件先到即结束本次等待，终态立即退出。这些是调用策略，不是模型长度限制。等待结束后返回真实任务标识和阶段；再次查询同一任务，不重新提交采样。

`result_source_name` 只能使用真实清单中的值；下载失败最多3次重取同一资源。文件大小与校验和通过后再完成本地保存。认证失败、文件缺失或登记失败明确报告；两个 GET 不触发修复、发布或模型重跑。服务没有提供的自动通知、百分比进度和断点续跑不作承诺。

## 7. 文档验收

完成标准是原 Skill 的步骤顺序和输入输出语义得到保留，模型执行入口明确替换成任务服务；上传、提交、结果清单和文件读取互相对应；两个模型的 Task/preprocess/environment 分开；错误与有限等待说明完整。

不以新客户端、应用会话、安装管线或播放器代码作为本文件交付物。运行验收另行检查任务服务可用性、原步骤对应的真实生成／转录／编辑结果以及只读下载重试，本轮均未执行。

## 来源

[S17]: https://github.com/multimodal-art-projection/YuE/blob/bd90e4ccae671d869b3ecaca6d7e893927d29442/skills/yue2-music/SKILL.md
[S18]: https://github.com/multimodal-art-projection/YuE/blob/bd90e4ccae671d869b3ecaca6d7e893927d29442/skills/yue2-music/references/models-and-setup.md
[S19]: https://github.com/multimodal-art-projection/YuE/blob/bd90e4ccae671d869b3ecaca6d7e893927d29442/skills/yue2-music/scripts/run_yue2.py
[S25]: https://github.com/multimodal-art-projection/YuE/blob/bd90e4ccae671d869b3ecaca6d7e893927d29442/skills/yue2-music/scripts/transcribe.py
[S27]: https://github.com/multimodal-art-projection/YuE/blob/bd90e4ccae671d869b3ecaca6d7e893927d29442/skills/yue2-music/scripts/abc_tools.py
[W01]: https://code.claude.com/docs/en/plugins
[W02]: https://code.claude.com/docs/en/plugins-reference

## v1.6：通过 MCP 调用相同 Runner 能力

Skill可通过agent-sandbox的/mcp使用runner_upload、runner_submit、runner_result、runner_result_source；与前述四个HTTP能力一一对应。原流程、parameter/payload、asset_id、task_id和result_source_name不变，模型执行仍由同一Task/Processor完成。

上传采用“云端签发、本地直传”：调用 `runner_upload(file_path, client_os)` 取得一次性、短效 PUT URL 和原样 `curl`/`curl.exe` 命令，再在 Skill 所在本地客户端执行命令。只有 PUT 返回 `asset_id`、`sha256`、`size_bytes`，才能把 `asset_id` 写入 `runner_submit`。远端不读取客户端路径，MCP 消息不携带 Base64 文件内容。

URL 已使用、过期、超限或传输失败时重新调用 `runner_upload`；不要重跑旧命令、修改 URL、添加 Authorization 或直接提交任务。原 `POST /runner/upload` 继续供直接 HTTP 客户端使用；`/api/uploads/{token}` 只是同一服务的单次传输路由。资源链接不等于已下载，MCP 与 HTTP 只选择一次提交入口，不因失败自动重复采样。详细契约见[10_Runner接口MCP封装与文件传输.md](10_Runner接口MCP封装与文件传输.md)。
