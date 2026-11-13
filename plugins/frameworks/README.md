# Python 框架项目与运行配置

这个独立插件给原生 **Run > Edit Configurations > +** 增加可运行的 Django、Flask 和 FastAPI 类型，使用开源 PythonCore 的配置编辑器、解释器/venv 选择、环境变量、工作目录、持久化、运行状态与调试器。

| 类型 | 默认执行入口 | 默认行为 |
| --- | --- | --- |
| Django | 所选 Python 执行项目的 `manage.py` | `runserver 127.0.0.1:8000 --noreload` |
| Flask | 所选 Python 执行模块 `flask` | `--app app run --host 127.0.0.1 --port 5000 --no-reload --no-debugger` |
| FastAPI | 所选 Python 执行模块 `uvicorn` | `app:app --host 127.0.0.1 --port 8000` |

打开实际项目后选择项目解释器，在该环境安装框架依赖，再创建对应配置。Flask 的 `--app`、FastAPI 的 `app:app` 和 Django 的 `manage.py` 路径要与项目相符。参数仍使用 PythonCore 的原生输入与宏规则；生成默认配置时以参数列表构建，再使用原生编码器保存，不经过 shell。

原生 **New Project** 的 Python 分类也注册了三个框架生成器，复用 PythonCore 的目录与解释器/venv 选择界面。生成最小项目、固定版本的 `requirements.txt` 和绑定所选模块 SDK 的运行配置。依赖安装复选框每次打开向导均默认关闭；勾选后才使用所选解释器执行 `-m pip install -r requirements.txt`。点击创建时按模块保存安装选择，避免其他向导改变正在创建项目的选择。文件生成、依赖安装、进程等待和 VFS 刷新都在后台完成，只有运行配置模型提交回到 EDT。文件冲突会报告错误并保留原文件；取消文件写入会回滚本次创建的文件。依赖安装失败或取消后保留已经生成的项目和所选环境，便于检查和手动继续。

默认关闭自动重载，方便本机调试和明确的进程生命周期。Flask 浏览器交互调试器也默认关闭；调试使用 IDE 的 Python 调试器。生产部署、远程解释器、自动重载子进程、多进程调试、框架模板/ORM/路由智能分析，以及完整向导桌面操作仍需单独实现或验收。初期模板只支持普通本地 Python/venv 项目，不支持 uv/Hatch/Poetry 的模块布局。

本插件没有引用商业框架实现，也没有启用付费组件或恢复已移除的锁定推广类。示例见 [`fixtures/frameworks`](../../fixtures/frameworks/README.md)，API 与证据边界见 [`framework-api.md`](../../docs/verification/framework-api.md)。

The plugin adds independent native Django, Flask and FastAPI project generators and Run/Debug configuration types. It preserves PythonCore's editor, interpreter selection, environment, working directory, persistence and execution state. New projects use PythonCore's native interpreter/venv UI. Installing pinned requirements is opt-in and targets the selected interpreter; cleanup acts only on that process and observed descendants. Full framework intelligence, actual wizard Create/Cancel desktop acceptance, reloaders and remote workflows remain separate work.
