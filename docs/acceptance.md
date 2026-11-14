# OpenPyCharm 验收矩阵

目标参考是本机 PyCharm 2026.1.4（`PY-261.26222.68`）。OpenPyCharm 沿用同版本的开源
工作台、编辑器与 Python PSI，独立产品的身份、配置目录、安装器和行为另行验收。
**完整 1:1 对齐尚未完成。** 上游已有功能、资源存在、构建通过或 headless 控件测试，
均不能替代本产品的实际桌面证据。

## dev.4 候选的新增实测

当前开发候选为 **0.1.0-dev.4**。本机 DMG 安装后的实际键鼠会话通过下列有界工作流，
本机 DMG 来源 `88387c3`、摘要与实际六帧演示已写入
[dev.4 拍摄清单](demo/v0.1.0-dev.4/capture.json)；与公开安装器的关联仍待封存。源码 `63921a4` 的
[CI 43608150941](https://github.com/shubolab/openpycharm/actions/runs/43608150941)
已通过双平台前端 JVM/完整运行时和产品启动门；Windows 安装器检查通过，macOS
正在完成 DMG 门。完整结果、最终产物收据与公开发行待确认。
当前已发布下载仍为 dev.3。

| 范围 | dev.4 本机安装版已观察 | 仍未验收或未实现 |
| --- | --- | --- |
| Python 编辑与 PSI | 原生补全、跨文件 Rename、引用一起更新、Undo 后再运行测试通过 | 更多诊断/快速修复、重构类型、冲突、Redo、大项目仍待逐项验收 |
| Python Run/Test | 实际运行和原生 unittest 9 个方法/20 项通过，Rename/Undo 后再次通过 | 失败重跑、pytest、完整参数/环境/停止场景待验收 |
| Python Debug | 断点、F8、表达式显示 `2.0400`、F9 继续通过 | Watches、测试调试等其余路径待验收 |
| JavaScript/TypeScript | 产品默认对已信任的本地项目开启；成员补全、类型诊断、Cmd+B 定义跳转；含中文/emoji 的未保存 JS 文本补全通过；正常关闭项目后三个自有 Node 进程退出 | 专用完整语法 PSI/重构、HTML/CSS、前端框架智能分析和调试仍未完成；异常所有者崩溃后的孤儿清理与 Windows 物理桌面未验收 |
| 运行时与分发 | 五插件装配，固定 Node 24.22.3/TS 6.0.3/TLS 6.1.0，191 运行时文件与声明认证；本机安装版树未变、严格签名通过 | 最终双平台产物收据与公开 Release 待封存，dev.4 GIF/清单已记录本机安装候选；开发 M0 和 guardian 原型不随产品分发 |

本轮未将 dev.3 的 Notebook/SQLite 桌面结果改记为 dev.4 新实测。具体新增范围与发行
门槛见[dev.4 候选说明](releases/v0.1.0-dev.4.md)。

## 已发布 dev.3 验收记录

本版为 **0.1.0-dev.3**，安装器源码 `9a243e605c43d86788b0e1b4607ec3bdf11b13d1`，
[双平台 CI 43565932969](https://github.com/shubolab/openpycharm/actions/runs/43565932969)通过。
当前安装包和 SHA-256 见[安装说明](installation.md)，真实安装版演示见
[dev.3 GIF 拍摄清单](demo/v0.1.0-dev.3/capture.json)。
[dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)与
[dev.1 记录](verification/2026-11-14-preview-release.md)保留。

最终 macOS 安装版使用 **macOS 27.2 arm64、Python 3.14**。Windows 已通过实际原生 API
门和内核/安装检查，但真实键盘、鼠标桌面流程仍待验收。下表区分这两类证据。

| 范围 | 必须在独立产品中验证的行为 | 当前状态 |
| --- | --- | --- |
| 产品启动 | 安装后启动；窗口、菜单、About、进程和配置目录属于 OpenPyCharm；无需 IDE 账号 | macOS 安装版与 Windows CI 安装版启动、独立目录通过；前序 macOS 菜单/About 检查通过 |
| 欢迎页与项目 | New Project、Open、Clone、最近项目；新建 Python 项目、重启继续工作 | 前序 macOS 普通 Python、dev.2 FastAPI 新建/venv/关闭重开与 README 预览恢复通过；dev.3 双平台正常 IDE 新建自有 Notebook 项目 API 门通过；Clone 和其余物理交互待验收 |
| 原生布局 | 项目树、标签、导航栏、左右工具条、Run/Test/Debug/Terminal、设置和快捷键 | macOS 项目/编辑器/Run/Test/Debug/设置及本版 Notebook、Database 可见；Terminal/完整快捷键待验收 |
| 解释器 | 选择本机 Python、创建 venv、切换后索引/配置一致、中文/空格路径 | dev.2 Mac 在中文/空格 FastAPI 路径创建 Python 3.14 venv 并调试通过；dev.3 全新本地 venv 的 Notebook 执行通过；解释器切换及其余路径待验收 |
| 包管理 | 当前环境包列表、指定测试包安装/卸载、网络失败、不能误用其他环境 | dev.2 向导显式安装依赖通过；dev.3 Notebook pins 在所选 Python 中手动安装；完整包管理界面、卸载和失败流程待验收 |
| Python 编辑 | 着色、缩进、配对、文档、提示、补全、诊断、快速修复和未保存文件 | Notebook 使用真实原生 Python 单元；完整 Python 编辑语义仍需逐项桌面验收 |
| PSI 与导航 | 定义、引用、Find Usages、Structure、Search Everywhere、继承/实现导航 | 前序 macOS 文件导航及 unittest.TestCase 定义跳转通过；其余待验收 |
| 重构 | Rename、Change Signature、Extract、Inline；跨文件引用、预览、冲突、Undo/Redo | 待验收 |
| Run | 文件/模块、参数、环境、工作目录、输出、停止与重复运行 | dev.3 最终 Mac 示例输出 `total=36.04`、退出 0；前序 FastAPI 原生停止通过；完整参数和停止场景待验收 |
| 测试 | unittest 原生树、失败定位/重跑、停止；pytest 单独选择依赖环境 | dev.3 Mac 原生 unittest 9 个方法、含子测试共 20 项通过；失败重跑/pytest/停止待验收 |
| Debug | 断点、步进、栈帧、变量、表达式、Watches、继续/停止；测试调试另验 | dev.3 最终 Mac 两处断点、F8、`quote.total` 求值 `Decimal('36.04')`、F9 和退出 0 通过；dev.2 FastAPI 请求断点/求值/继续/停止保留；Watches/测试调试待验收 |
| Python Console | 项目解释器、结果/错误、重启和中止 | 待验收 |
| Terminal | 项目目录、shell、venv、输入/中文、退出和终止 | 待验收 |
| Git | 状态、差异、提交、分支、拉取/推送；保留 Git/GitHub/私有仓库认证 | 服务认证入口保留；实际 Git 工作流待验收 |
| 插件 | 原生搜索、兼容性、安装/禁用/卸载与第三方规则 | 待验收 |
| 简体中文 | 匹配版本的语言包、菜单/设置/工具窗及重启持久化 | 待验收 |
| 账号与推广 | 移除 IDE 账号、同步、试用、订阅、计费和升级推广；保留用户选择的开发服务认证 | 本版安装/工作流无需 IDE 账号，双平台描述符过滤控制通过；Git/服务认证保留，具体登录工作流另验 |
| macOS 安装 | DMG、拖拽安装、实际工作流、签名、卸载边界 | dev.3 最终安装版 Python/Notebook/SQLite 工作流通过；产品树未变、严格签名通过；有界日志 0 ERROR/SEVERE、141 WARN，见[发行收据](verification/dev3-installed-20261114.json)；完整卸载边界待验收 |
| Windows 安装 | EXE、含空格安装路径、启动、文件关联、卸载及物理桌面流程 | 本版 CI 安装/文件核对/实际启动/卸载通过；实际原生 Notebook API 门通过；文件关联、卸载残留及物理键鼠流程待验收 |
| 发行证据 | 双平台安装器、SHA-256、源码来源、安装说明、真实原生 GIF | dev.3 对应本页固定源码与双平台 CI；当前下载切至 dev.3，dev.2 保留。GIF 使用最终安装版真实截屏，来源见拍摄清单 |

## 本版新增与完整对齐边界

| 范围 | 已实现与已观察 | 仍未完成或未验收 |
| --- | --- | --- |
| Notebook/科学计算 | 原生 nbformat 4 单元、所选本机 Python 内核、运行/中断/重启、保存/撤销/合并/重开；最终 Mac 全新 venv Run All，PNG/JPEG、DataFrame 显示值 `99`、display update、静态 HTML、Markdown、错误、中断、Shift+Enter 结果 `56` 及保存重开保留原 10 个单元通过 | 用户自行安装 `jupyter_client==8.6.3`、`ipykernel==6.29.5`，IDE 不自动安装；富媒体示例另需可选 pandas/matplotlib/Pillow。远程内核、widgets、交互式 stdin、Notebook 调试、完整科学计算工具未实现；Windows 物理键鼠未验收 |
| 数据库 | 原生连接配置、PasswordSafe、元数据、SQL 编辑/执行、只读结果预览、事务、取消、schema/表/列缓存补全；CI 真实临时 SQLite 事务/取消/超时等后端控制通过；最终 Mac 中文 3 行、物理 Basic+Return 将源文件 `pro` 补为 `"main"."products"`、`p.na` 补为 `p."name"`，再 Disconnect 通过 | 补全前须点 **Refresh tables**；快照 TTL 五分钟，普通 SELECT 不刷新。PostgreSQL 与 MySQL/MariaDB 驱动携带但真实网络连接/TLS/认证/取消未测；结果编辑/导出、SSH 隧道和完整方言智能分析未实现 |
| Web 框架 | 保留 Django/Flask/FastAPI 自有原生生成器与 Run/Debug；双平台 CI 实际 venv/生成/依赖 opt-in 检查通过；dev.2 Mac FastAPI 新建、请求断点、求值、继续、停止、重开记录保留 | 依赖安装默认关闭；Django/Flask 物理桌面、模板/ORM 语义与更广框架导航仍待验收或实现 |
| HTTP/API | 保留 `.http` 原生编辑、Services 响应、当前/批量运行、原始响应字节保存和取消；dev.2 Mac 单条/批量 3×200、中文/emoji、原始 16 字节保存、Stop All 记录保留；本版双平台 bundled API 注册检查通过 | 环境文件/OAuth/更广凭据支持未实现；Windows 物理桌面仍未验收 |
| Markdown | 本版 macOS CI 冷启动原生预览通过；前序最终安装版 README 预览恢复记录保留 | 更多项目、代理、复杂内容和平台组合待验收 |
| 前端开发 | 前端入口兼容性有独立来源与边界控制 | 完整 JavaScript/TypeScript、HTML/CSS、前端框架语义与调试尚待实现或验证 |
| 容器与远程 | 保留用户选择的服务认证边界 | Docker、SSH/远程解释器、远程开发、部署和路径映射待实现或验证 |
| 大项目与兼容性 | 当前有界示例和缓存/生命周期控制 | 大型索引、性能、完整语法、第三方插件、输入法、不同 Python/OS 组合待验收 |

## CI 与记录要求

本版 Windows 仓库控制运行 **125 项，122 项通过、3 项仅限 POSIX 的检查跳过**。
双平台还运行实际 JVM/所选本地 Python 内核、正常新项目生命周期下的原生 Notebook
编辑/撤销/保存/合并/重开，以及安装器检查。这些真实 API/进程证据不代替 Windows
物理键盘、鼠标工作流，也不构成完整 1:1 验收。

当前独立原生门的详细来源还见 [SQL 补全插入](verification/database-completion-native-20261114.json)、
[Notebook 正常新项目保存门](verification/notebook-owned-project-native-20261114.json)与
[Notebook 单元回归](verification/notebook-cell-native-regression-20261114.json)。本版最终
人工安装会话与 GIF 的来源按上述固定源码、安装包 SHA-256 和拍摄清单核对。

每条通过记录注明版本、安装包 SHA-256、系统、Python、示例、操作、可见结果、日志
与剩余限制。先前 JCEF 初始化、SQL 插入范围和 Notebook 保存/信任启动失败记录均保留，
修复后的通过记录单独绑定源码和产物，不改写旧负例。dev.2 的失败候选与最终通过范围
见[历史记录](verification/2026-11-14-dev2-release.md)。

[hello-python](../fixtures/hello-python/README.md)给出确定输出及 9 个 unittest 方法。
命令行测试、headless 控件、原生 API 门与实际键鼠桌面验收分别记录。
