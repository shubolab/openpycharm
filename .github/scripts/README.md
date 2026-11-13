# Verified installer transfer

`transfer-ci-installers.yml` is a manual, main-branch workflow for an already
prepared draft release. It attaches the DMG and EXE from one successful official
native build, using the job's ephemeral `github.token` with `actions:read` and
`contents:write`. It does not create a release/tag, edit release notes, overwrite
an asset, delete an asset, or publish. The historical dev.1 Windows-only workflow
is retained separately as a record of that delivery.

Prepare the draft with reviewed notes and its **full documentation/GIF commit
SHA** as `targetCommitish`. Supply all eight dispatch inputs: tag, full production
SHA, full documentation SHA, build run ID, both artifact IDs, and both standalone
installer SHA-256 values. The documentation commit must descend from the
production commit with every captured production input unchanged; an existing
lightweight or annotated tag must resolve to that documentation commit.

Choose the final approved source/build/artifacts and the actual reviewed
documentation/GIF commit when dispatching. No candidate values are selected
automatically. Final installed GUI/GIF acceptance remains a separate release
gate; a successful CI transfer is only evidence of the byte/provenance checks
described here.

The helper obtains the archive SHA-256 from GitHub artifact metadata, requires
the exact own-repository workflow/run/source/target identity, verifies both
archives and installer receipts before uploading anything, and streams only the
two exact installer members. ZIP links, special files, path traversal,
duplicates, excess sizes, mismatched manifests/checksums and stale source inputs
are rejected. Windows capture may match an exact UTF-8 LF-to-CRLF checkout
conversion; all such paths are listed in the result. No artifact code is run.

The upload uses the frozen release ID, not a fresh tag lookup, and has no clobber
option. The draft's ID/tag/target, notes and existing assets are checked before
each upload and again after it. Workflow concurrency serializes transfers for
the same tag. These checks are not atomic with an external concurrent
publication: keep the release in draft during transfer.
A detected state change fails the job; already attached assets may remain.
There is deliberately no automatic deletion or publication rollback.

Run isolated controls with:

```sh
python3 -m unittest discover -s .github/tests -v
```

The CLI defaults to verification without upload. Upload mode additionally
requires the manual main-branch Actions context; no personal-token fallback is
used. The helper and tests live under `.github/`, outside the production-source
inventory, so this release tooling does not require rebuilding tested IDE bytes.
