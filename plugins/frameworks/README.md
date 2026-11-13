# Python 框架运行配置

这个独立插件给原生 **Run > Edit Configurations > +** 增加可运行的 Django、Flask 和 FastAPI 类型，使用开源 PythonCore 的配置编辑器、解释器/venv 选择、环境变量、工作目录、持久化、运行状态与调试器。

| 类型 | 默认执行入口 | 默认行为 |
| --- | --- | --- |
| Django | 所选 Python 执行项目的 `manage.py` | `runserver 127.0.0.1:8000 --noreload` |
| Flask | 所选 Python 执行模块 `flask` | `--app app run --host 127.0.0.1 --port 5000 --no-reload --no-debugger` |
| FastAPI | 所选 Python 执行模块 `uvicorn` | `app:app --host 127.0.0.1 --port 8000` |

打开实际项目后选择项目解释器，在该环境安装框架依赖，再创建对应配置。Flask 的 `--app`、FastAPI 的 `app:app` 和 Django 的 `manage.py` 路径要与项目相符。参数仍使用 PythonCore 的原生输入与宏规则；生成默认配置时以参数列表构建，再使用原生编码器保存，不经过 shell。

默认关闭自动重载，方便本机调试和明确的进程生命周期。Flask 浏览器交互调试器也默认关闭；调试使用 IDE 的 Python 调试器。生产部署、远程解释器、自动重载子进程、多进程调试、框架模板/ORM/路由智能分析、新建项目向导仍需单独实现或验收。

本插件没有引用商业框架实现，也没有启用付费组件或恢复已移除的锁定推广类。示例见 [`fixtures/frameworks`](../../fixtures/frameworks/README.md)，API 与证据边界见 [`framework-api.md`](../../docs/verification/framework-api.md)。

The plugin adds independent native Django, Flask and FastAPI Run/Debug configuration types. It preserves PythonCore's editor, interpreter selection, environment, working directory, persistence and execution state. Framework packages belong to the selected Python environment. Full framework intelligence, new-project generators, reloaders and remote workflows remain separate work.
