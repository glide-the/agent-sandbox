# 示例使用边界

全部服务示例均为**拟新增 yue2_task / sheetsage2_task 契约**，不是当前 main 已可接受的请求。`parameter/payload`、`code/msg/data`、`/runner/submit`、`/runner/result`、`/runner/result_source` 来自现有代码；yue2_task、sheetsage2_task、operation、业务参数和 artifacts 元数据为本方案新增。

提交时另带 `Authorization: Bearer <按用户映射的服务凭据>` 和 `Idempotency-Key: <客户端在首次提交前保存的UUID>`。示例 userId 仅用于保持现有索引结构，服务端必须与认证主体核对并重写，不能视为认证。

示例 task_id/asset_id 为说明用值，不能直接跨环境使用。完成响应中的大小与全零 SHA256 仅展示数据形状，不代表已生成音频。真实响应必须填写实际字节数和实际摘要。

原生 `style/lyrics/cot/seed/id` 依据固定版本的 SongRequest。拟议服务不允许直接提交 `abc_path`、解释器、模型路径、输出路径或 shell 命令；ABC 文件通过资源引用映射，内联 abc 则使用原生字段且不得与 abc_source 并存。

自动翻唱先提交 02，再检查该任务返回的实际 score 产物，最后提交 04。需要修改乐谱时，将修改后 ABC 上传为新资产，再使用 05，绝不覆盖原谱。

## v1.2 接口修订

新增仅 POST /runner/upload，multipart字段file/user_id；09_upload.response.json展示返回结构。转录引用audio_asset_id；修改谱引用abc_source.asset_id，摘要和大小由服务器登记并验证，不强制重复提交。已有输出引用统一使用task_id/result_source_name；result响应清单也用result_source_name。删除公开重发布动作，结果只通过现有两个GET获取。文件大小和全零摘要是示例形状，未生成实际音频。
