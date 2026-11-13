# Python 原生工作流示例

这个项目使用 Python 3.10 或更新版本，只依赖标准库。用 OpenPyCharm 打开本目录，选择本机 Python 解释器，运行 `main.py`。

预期输出：

```text
OpenPyCharm demo: subtotal=34.00, tax=2.04, total=36.04
```

命令行核对：

```sh
python3 main.py
python3 -m unittest discover -s tests -v
```

可用于人工验收的操作：

- 编辑 `main.py` 中的 `QuoteLine` 调用，检查参数补全与类型提示；从 `QuoteCalculator` 跳转定义，再查看其引用。
- 在 `hello_python/calculator.py` 的 `tax = ...` 一行设置断点，Debug `main.py`，查看 `subtotal`、`self.tax_rate`，求值 `subtotal * self.tax_rate`，然后继续运行。
- 用原生 unittest 入口运行 `tests/test_calculator.py`，查看 9 个用例及子测试结果。修改断言后可检查失败跳转与重新运行，再撤销修改。
- 在示例副本中重命名 `QuoteCalculator`，确认导入、调用与测试一起更新；Undo 后重新运行测试。

命令行通过只证明示例代码正确。IDE 的补全、导航、重构、测试树和调试仍需分别记录实际桌面验收结果。
