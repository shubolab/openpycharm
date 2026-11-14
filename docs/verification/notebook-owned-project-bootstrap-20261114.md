# Owned native Notebook gate project creation

The previous CLI launch opens an existing fixture project. In pinned platform
`456919a9624bae72ac12efafc35d2b916cb0c5c5`, `ProjectManagerImpl` checks project
trust before project initialization and post-startup activities (lines 622–643).
A post-startup probe therefore cannot resolve the initial modal dialog.
Passing `asNewProject()` to `openProject` alone still reaches that earlier check.

The normal `newProject(Path, OpenProjectTask)` API is different. Its implementation
grants trust to the new path and created project model before returning
(`ProjectManagerImpl`, lines 843–869). The public blocking wrappers are intended
for tests and cases such as the New Project wizard (`ProjectManagerEx`, lines
60–69). Source URLs, Git blob IDs and SHA-256 receipts are retained in the
[source and compilation record](notebook-owned-project-bootstrap-20261114.json).

The test launcher now starts without a CLI project argument. Its application
listener schedules a worker that validates a fresh project directory containing
only the generated Notebook fixture, its expected hash, canonical paths, and
the actual isolated profile. It calls normal `newProject`, then normal
`openProject` with that same created model. The existing post-startup edit/save
sequence continues afterward. The helper does not call a trust setter or change
production trust protection. Parent trust must remain false. Normal project-root
trust includes descendants; it does not authorize the parent or sibling projects.

Runtime evidence records `normalIdeNewProjectCreation`, `normalIdeProjectOpen`,
`expectedInitialFixtureHash`, the exact root, parent trust before/after, and
`manualTrustClicked=false`. This identifies API-created project acceptance;
it does not claim that a person clicked Trust Project. Constructor/open failures
write a failing native report. A bounded bootstrap watchdog also reports a
blocked wrapper, and a failed bootstrap cannot subsequently pass the save gate.

The candidate compiled with the authenticated SDK. Headless filesystem controls
and launcher/evidence controls passed; their full counts are in the JSON record.
No IDE was launched for this change. Actual desktop project creation and save
acceptance remain pending for root's exclusive native run. Existing manual trust
and modal-timeout evidence is retained unchanged.

中文：此增量只调整测试夹具的创建入口。IDE 通过正常的新建项目 API 为已校验的自有
目录建立项目与信任，再执行原有原生保存测试；不启用全局信任、不自动信任父目录，
也不把 API 创建记录描述成人工点击。编译及边界控制通过不代表原生运行已通过。
