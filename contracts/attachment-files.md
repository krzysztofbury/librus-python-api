# Optional attachment file publication

`librus_python_api.files.publish_attachment` owns reusable filesystem safeguards;
the application selects an existing, trusted local directory and supplies the
attachment's display filename. It does not discover destinations, create directories,
change consumer configuration, open message content or instantiate a network client.
The separate explicit `await prepare_attachment_directory(path)` creates/validates
a selected private directory. Its parent must already exist; unsafe existing
permissions/ACLs reject without changing them. No implicit directory creation occurs
during publication. The helper creates mode 0700 on POSIX and a protected private
inheritable ACL on Windows. Cancellation joins work and may leave an empty directory.

Publication consumes an API `AttachmentStream` or `ModernAttachmentStream`, with its existing shared
traffic, byte, deadline, credential isolation and cancellation budgets. A second
explicit byte ceiling protects the local writer. Only complete EOF publishes.
Upstream filenames are reduced to portable bounded UTF-8 basenames, with control
and bidi characters replaced and reserved device names neutralized. Filenames and
paths are omitted from result reprs and storage errors.

On POSIX the writer pins an existing nonsymlink directory descriptor, creates one exclusive
owner-only random temporary file there, and joins every disk worker before cleanup.
After fsync, a same-directory hard link publishes atomically without overwriting
any existing regular file, directory or symlink. At most 100 candidate names are
tried. The final file retains mode 0600. Failures remove only this call's temporary
file, not final paths or another call's work. Cancellation during atomic commit
can leave a complete final file; it cannot roll back a file someone may already
have opened. Filesystem failure after linking may likewise leave a complete file.
The selected directory and its ancestors must remain trusted and stable; this is
not a sandbox for an attacker-controlled download destination. Hard-link/fsync/
directory-descriptor support is required on POSIX; unsupported filesystems fail explicitly.

On Windows, only fixed local NTFS volumes with persistent ACLs are accepted.
UNC/device/network paths and reparse points in the directory or any ancestor reject
before streaming. The directory and its ancestors are pinned with no-delete-share
handles. The directory requires a protected DACL with inheritable current-user
full control; only current user, SYSTEM and built-in administrators may have allow
entries. Unsafe preexisting ACLs are never repaired automatically. `pywin32` is a
Windows-only runtime dependency; no consumer helper code is reused.

The exclusive random temporary file has an explicit private ACL. After flushing
complete contents, `SetFileInformationByHandle(FileRenameInfo)` renames the owned
file with `ReplaceIfExists=False` into the pinned directory. It never replaces a
regular file, directory or reparse collision; bounded alternate names are tried.
The renamed handle is flushed again. Workers are joined before closing handles;
cleanup removes only the owned temporary path when it still exists. Cancellation
or flush failure after rename may leave the complete final file, not partial data.
This is process-crash/atomic-visibility protection, not a promise that a directory
entry survives arbitrary power loss or broken storage firmware. SQLite durability
and attachment publication have distinct boundaries.

Original tests exercise real loopback HTTP streams, collision and symlink targets,
four-account concurrent large files, incomplete/oversized streams, storage failure,
and repeated cancellation during an actual disk worker. No consumer files or
production download directories are touched. Broader signed URL and modern stream
qualification remain separate from this local publication contract.
