# OpenPyCharm 验收矩阵

目标参考是本机 PyCharm 2026.1.4（`PY-261.26222.68`）。OpenPyCharm 以相同版本的开源 PyCharm 为基础，独立产品的身份、配置目录、安装器和运行行为需另外验收。本表的“待验收”表示尚无本产品的实际桌面证据；上游已有功能、资源存在或自动化构建成功都不能替代它。

首个已发布预览版的结果见 [dev.1 记录](verification/2026-11-14-preview-release.md)。
dev.2 最终候选来源为 `d5fc10d`，双平台 CI 与 Mac 实际安装版检查见
[本版记录](verification/2026-11-14-dev2-release.md)和
[版本固定的截屏动画清单](demo/v0.1.0-dev.2/capture.json)；目前尚未公开发布。
下表只更新已观察到的部分，剩余场景继续开放，Windows 交互式桌面流程仍未验收。

| 范围 | 必须在独立产品中验证的行为 | 状态 |
| --- | --- | --- |
| 产品启动 | 从安装后的应用启动；窗口、菜单、About、进程和配置目录属于 OpenPyCharm；无需 IDE 账号 | macOS 安装版启动、菜单/About、独立目录通过；Windows 安装版启动及独立目录通过 |
| 欢迎页与项目 | New Project、Open、Clone Repository、最近项目；新建普通 Python 项目，重启后可继续工作 | macOS 前序普通 Python 项目流程通过；dev.2 最终安装版 FastAPI 新建/venv/关闭重开、最近项目 README 预览恢复通过；Clone 待验收 |
| 原生布局 | 项目树、编辑器标签、导航栏、左右工具条、底部 Run/Test/Debug/Terminal、设置与快捷键 | macOS 项目/编辑器/Run/Test/Debug/设置已观察；Terminal/完整快捷键待验收 |
| 解释器 | 选择已有 Python；创建 venv；切换解释器后索引与运行配置一致；路径含中文和空格 | dev.2 Mac 在含中文/空格的 FastAPI 项目原生创建 Python 3.14 venv 并调试通过；解释器切换及其他路径场景待验收 |
| 包管理 | 查看当前环境的软件包，安装/卸载指定测试包，展示网络或安装失败；不能误用其他环境 | dev.2 FastAPI 向导在所选新 venv 显式安装依赖通过；完整管理界面、卸载与失败流程待验收 |
| Python 编辑 | 语法着色、缩进、配对、文档、参数提示、补全、诊断、快速修复，覆盖未保存文件 | 待验收 |
| PSI 与导航 | 定义、引用、Find Usages、Structure、Search Everywhere、继承与实现导航 | macOS 文件导航及 unittest.TestCase 定义跳转通过；其余待验收 |
| 重构 | Rename、Change Signature、Extract、Inline；跨文件引用、差异预览、冲突提示、Undo/Redo | 待验收 |
| Run | 文件/模块运行，参数、环境变量、工作目录、输出、停止与重复运行；只终止本产品启动的任务 | dev.2 Mac 示例 Run 输出及退出码通过，FastAPI 原生停止退出 0；其他参数/停止场景待验收 |
| 测试 | unittest 原生测试树、失败定位、失败重跑、停止；pytest 需另选带该依赖的环境验收 | macOS 9 个方法/20 个含子测试项通过；失败重跑/pytest/停止待验收 |
| Debug | 断点、步进、栈帧、变量、表达式、Watches、继续、停止；运行与测试调试分别检查 | dev.1 Mac 示例 F8/F9 通过；dev.2 FastAPI 请求断点/求值/继续/原生停止通过；Watches/测试调试待验收 |
| Python Console | 使用项目解释器执行代码，查看结果和错误，重启控制台与中止执行 | 待验收 |
| Terminal | 项目目录、shell、解释器/venv 环境、输入与中文显示、进程退出及终止 | 待验收 |
| Git | 状态、差异、提交、分支、拉取与推送；保留用户选择的 Git/GitHub/私有仓库认证 | 待验收 |
| 插件 | 原生搜索、兼容性检查、安装/禁用/卸载；第三方插件规则单独遵守 | 待验收 |
| 简体中文 | 匹配平台版本的语言包；菜单、设置、项目树、运行/调试面板及重启持久化 | 待验收 |
| 账号与推广 | IDE 账号、同步、试用、订阅与升级推广入口应按产品要求移除；开发服务认证可用 | 待验收 |
| macOS 安装 | DMG 内拖拽安装、应用签名检查、安装后实际启动、Python Run/Test/Debug、卸载边界 | dev.2 最终 DMG 挂载/复制/安装后 Run/Test/FastAPI Debug/HTTP 通过；流程后文件树未变、严格签名通过；卸载边界待完整验收 |
| Windows 安装 | `.exe` 安装到含空格目录、实际启动、Python Run/Test/Debug、文件关联与卸载 | CI 静默安装/文件核对/安装后原生启动/卸载进程通过；文件关联、卸载残留和 Python 桌面流程待验收 |
| 发行证据 | 安装器、SHA-256、来源清单、版本对应源码、安装说明与真实原生演示 | dev.1 已发布；dev.2 双平台安装器、SHA-256、来源收据、安装版截屏 GIF 已备好，公开发布待完成 |

## 完整对齐仍需独立实现和验收的范围

本机统一发行的 PyCharm 还包含 Python 开源基础之外的组件。不能因为基础产品已启动，就把下列工作记为完成：

| 范围 | 尚需核对与完成的工作 | 状态 |
| --- | --- | --- |
| Web 框架 | Django/Flask/FastAPI 的项目创建、路由、模板、运行调试及框架相关导航 | dev.2 双平台 CI 通过三个自有原生配置/生成器 API、真实 venv/服务检查；最终 Mac 安装版 FastAPI 新建、请求断点、求值、继续、停止和重开配置通过，见[本版记录](verification/2026-11-14-dev2-release.md)。不等于完整框架语义；Django/Flask 桌面及模板/ORM/更广导航待验收 |
| 数据库 | 连接管理、凭据、查询编辑、执行、结果表、事务与数据库导航 | 未纳入 dev.2，完整实现与验收未完成 |
| Notebook/科学计算 | Jupyter 内核、单元格、变量、图表、数据查看与错误恢复 | 未纳入 dev.2，完整实现与验收未完成 |
| 前端开发 | JavaScript/TypeScript、HTML/CSS 与前端框架语义支持及调试 | 待调研、待实现或验证 |
| 容器与远程 | Docker、SSH/远程解释器、远程开发、部署与路径映射 | 待调研、待实现或验证 |
| HTTP/API | 请求文件、环境、响应、凭据与批量执行 | dev.2 最终 Mac 安装版的原生 .http/Services 单条/批量 3×200、中文/emoji 响应、原始 16 字节保存和 Stop All 通过；环境文件/OAuth/更广凭据支持未实现，Windows 桌面未验收 |
| 大项目与兼容性 | 大型项目索引、性能、完整语法、第三方插件、输入法与不同 Python/操作系统版本 | 待验收 |

## 记录要求

每条通过记录应注明产品版本、安装包 SHA-256、系统、Python 版本、示例项目、操作、可见结果、日志与剩余限制。失败记录保留复现步骤，不用“已实现入口”替代“已通过”。

dev.2 的 `26da493` CI 安装候选恢复 Markdown 预览时记录了代理服务在 JCEF 静态初始化中创建的 SEVERE；该候选被拒绝，其记录保留为历史失败。公开源码回放修复后的最终 `d5fc10d` 安装版已重新完成 README 原生预览恢复、Python Run/Test、FastAPI Debug 和 HTTP 检查；产品树未变、严格签名通过，有界会话日志含 0 条错误、20 条保留警告。新安装版 GIF 已更新并记录来源；dev.2 公开 Release 与下载仍待发布，当前已发布下载继续对应 dev.1。

首个可复用项目是 [hello-python](../fixtures/hello-python/README.md)，它给出确定的运行输出与 9 个 unittest 用例。其命令行测试结果与 IDE 桌面验收分别记录。
