# Notebook examples / Notebook 示例

`native-demo.ipynb` is a small state/error example needing only the kernel packages.
`native-rich-demo.ipynb` is the unexecuted ten-cell control used for the dev.3 Mac
recording: PNG/JPEG, a pandas table updated to 99, static HTML/Markdown, an expected
ValueError, an interruptible sleep and Shift+Enter recovery to 56.

`native-demo.ipynb` 是简单的状态与错误示例，仅需内核依赖。
`native-rich-demo.ipynb` 是 dev.3 Mac 演示使用的未执行十单元夹具：图像、更新到 99 的
表格、静态 HTML/Markdown、预期 ValueError、可中断等待及 Shift+Enter 恢复到 56。

Choose a local project interpreter in OpenPyCharm and explicitly install the
packages into that same interpreter. The IDE does not install them automatically.
For the recorded Python 3.14 environment, from the repository root:

先在 OpenPyCharm 选择本机项目解释器，再将依赖显式安装到同一解释器；IDE 不会自动
安装。对于演示所用 Python 3.14 环境，在仓库根目录运行：

```sh
/absolute/path/to/selected/python -m pip install -r tests/notebooks/rich-requirements-314.txt
```

Open the rich notebook in a normally trusted owned project and use **Run All**.
At the 120-second sleep prompt, click **Interrupt**; focus the final cell and press
**Shift+Enter**. Save, close and reopen to inspect the preserved actual outputs.
Foreign metadata and unknown MIME values are deliberate preservation controls.
The repository fixture itself has empty outputs/counts; it is not execution evidence.

在正常信任的自有项目打开富输出夹具，点击 **Run All**。看到 120 秒等待提示时点击
**Interrupt**，然后聚焦最后单元按 **Shift+Enter**。保存、关闭并重新打开，可查看保留
的真实输出。额外元数据和未知 MIME 是保留性控制；仓库夹具输出/次数为空，本身不代表
执行证据。实际结果见[本版记录](../../docs/verification/2026-11-14-dev3-release.md)。
