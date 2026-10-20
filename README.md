# RepoPilot-test / MiniFix

独立的小型 Coding Agent 项目，用于通过 RepoPilot 展示“发现缺陷 → 提出改进 → 受控实验”。不是 RepoPilot 后端的一部分，也不包含固定修复答案。

## 三个角色

- 本仓库：Agent 源码、镜像构建及版本配置。
- RepoPilot：导入 Agent 描述，管理运行、模型网关、证据、独立验收及配对实验。
- 任务仓库：Agent 要修复的代码，例如独立的 RepoPilot-demo-tasklist。其原始提交和受保护测试由平台冻结。

不要把本仓库登记成 task-list 任务仓库：我们正在评价它修复代码的能力，而非让它修改自身。

## 缺陷与实验变量

`agent.py` 的 `make_messages` 中，prefix 策略只把目标文件前 12 行提供给模型，可能遗漏实际错误及相关行为；full 策略发送完整文件（上限 16000 UTF-8 字节，超限拒绝）。两者使用同一镜像，通过 `--context prefix/full` 选择。

这是有意保留的上下文选择缺陷；full 是待验证的对照策略。模型、任务描述、system 提示词、调用预算及验收测试保持不变。首轮保留这两个策略便于冻结实验，不能在看到结果后调整阈值来制造提升。模型也可能仅根据任务描述就修好，不能保证 prefix 失败或 full 成功。

## 代码做什么

1. 从 `/input/request.json` 读取任务、允许修改的文件和 Run 身份。
2. 读取一个目标 Python 文件；不读取测试、不遍历工作区、不执行 shell。
3. 用短期 Run 凭证向平台注入的模型网关请求一次；不持有供应商 Key，不直接请求供应商。
4. 接收完整文件 JSON，检查目标路径、输出完整性、Python 语法和源码是否被并发修改，然后替换目标文件。
5. 写 `/output/result.json`。execution completed 只表示执行完成，正确性由平台独立测试判断。

平台特定的 protocol-probe-v1/全零提交校验只检查目录协议，不联网、不修改代码，不证明模型质量。Agent 自报能力仅 execution，模型请求与用量通过平台账本查看。

## 本地验证与构建

Python 3.11 标准库即可，不需要安装 RepoPilot、Pydantic 或其他依赖：

```powershell
Set-Location D:\RepoPilot-test
python -m unittest discover -s tests -v
```

先核对已有本地 Python 3.11 基础镜像；本机现成的 repopilot-protocol-demo:v1 也可以用。其旧入口会被 Dockerfile 覆盖，MiniFix 不依赖其中的 demo.py。其他电脑可以指定自己的基础镜像。

```powershell
docker image inspect repopilot-protocol-demo:v1 --format '{{.Id}}'
docker build --network=none --pull=false --build-arg BASE_IMAGE=repopilot-protocol-demo:v1 -t repopilot-minifix:external-v1 .
if ($LASTEXITCODE -ne 0) { throw '构建失败' }
$minifixImage = docker image inspect repopilot-minifix:external-v1 --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw '读取镜像失败' }
python registrations.py --image "$minifixImage" --output-dir artifacts/catalog-v1
```

生成器只生成两个前端导入 JSON，不访问平台或模型；拒绝覆盖旧文件。新实现须使用新注册版本，不覆盖已有版本。镜像 ID 和生成文件只适用于当前构建，不作为跨电脑通用 ID。

## 在 RepoPilot 演示（分三步）

1. Agent 页面导入 artifacts/catalog-v1 下两个 JSON，注册并显式校验。选择绑定原始有缺陷提交的 task-list suite（8 项固定测试、预期 2 项基线失败）。Process 模式不需要向量化此 Agent 或任务仓库。
2. 确认真实网关部署，由用户授权模型调用。批次选择 prefix 为 baseline、full 为 candidate，controlled 模式，changed_fields 为 ["process.argv"]，repetitions=1，超时 180 秒。预览冻结配置后再启动，worker 也须授权模型。每版最多 1 次调用、2048 输出 Token，不等于严格费用上限。
3. 运行结束看请求上下文差异、代码 Diff、平台基线/最终测试、provider 用量与耗时，再查看配对结果。成功、同败、退化都保留；不把一次样本作为通用提升或发布保证。成本未知不补零。

真实部署配置在 RepoPilot 的 docs/model-gateway-live-runtime.md。本仓库不保存 Key、业务数据库配置或运行凭证。

## 当前进度与限制

已完成独立源码、离线测试、Dockerfile 和注册描述生成器。没有执行真实付费模型实验；离线测试模拟模型输出，不是端到端修复成功率。本仓库的测试验证 Agent 自身协议与防护，不替代任务仓库的独立验收测试。

首次实验先演示接入与证据链；之后根据真实证据修改上下文策略，再增加任务与重复运行。尚未支持多文件编辑、工具循环或自主检索。
