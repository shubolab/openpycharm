# OpenPyCharm

Build an independent native Python IDE matching the installed PyCharm 2026.1.4.

- Use the pinned open-source PyCharm/IntelliJ Platform from JetBrains/intellij-community. Reference installations are read-only; never modify their files, configuration, licenses or projects.
- Keep the IntelliJ desktop/editor/PSI architecture. No WebView replacement.
- Keep local IDE use free of IDE accounts, billing, subscriptions, trials and upgrade promotions. Preserve Git/GitHub/private repository and user-selected service authentication.
- Do not redistribute proprietary implementation code. Preserve upstream open-source and third-party notices.
- Record observed, inferred and unknown behavior separately. A build or launch is not full 1:1 acceptance.
- Never do blocking filesystem/process work on the Swing event dispatch thread. Terminate only project-owned processes.
- Keep isolated OpenPyCharm config, caches, plugins and logs.
- Keep at least 20 GiB free before large builds. Reuse pinned downloads and compact evidence; retain the latest verified installer and app.
- Delivered versions need actual macOS DMG and Windows EXE installers, checksums, installation instructions, and GitHub Release evidence. Mark unverified platforms explicitly.
- Maintain English and clear Chinese READMEs with real native example captures. Never use mock screenshots as runtime evidence.
- User explicitly requires the feature-demo GIF in README to be updated with each publishable release. Capture the actual installed version and state its version, OS and workflow; retain the capture manifest.

Checks: python3 -m unittest discover -s tests -v; fixture tests; authenticated native product build; real Python edit/run/test/debug desktop checks.
