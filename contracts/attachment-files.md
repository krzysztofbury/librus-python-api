# Optional attachment file publication

`librus_python_api.files.publish_attachment` owns reusable filesystem safeguards;
the application selects an existing, trusted local directory and supplies the
attachment's display filename. It does not discover destinations, create directories,
change consumer configuration, open message content or instantiate a network client.

Publication consumes an API `AttachmentStream` or `ModernAttachmentStream`, with its existing shared
traffic, byte, deadline, credential isolation and cancellation budgets. A second
explicit byte ceiling protects the local writer. Only complete EOF publishes.
Upstream filenames are reduced to portable bounded UTF-8 basenames, with control
and bidi characters replaced and reserved device names neutralized. Filenames and
paths are omitted from result reprs and storage errors.

The writer pins an existing nonsymlink directory descriptor, creates one exclusive
owner-only random temporary file there, and joins every disk worker before cleanup.
After fsync, a same-directory hard link publishes atomically without overwriting
any existing regular file, directory or symlink. At most 100 candidate names are
tried. The final file retains mode 0600. Failures remove only this call's temporary
file, not final paths or another call's work. Cancellation during atomic commit
can leave a complete final file; it cannot roll back a file someone may already
have opened. Filesystem failure after linking may likewise leave a complete file.
The selected directory and its ancestors must remain trusted and stable; this is
not a sandbox for an attacker-controlled download destination. Hard-link/fsync/
directory-descriptor support is required; unsupported filesystems fail explicitly.

Original tests exercise real loopback HTTP streams, collision and symlink targets,
four-account concurrent large files, incomplete/oversized streams, storage failure,
and repeated cancellation during an actual disk worker. No consumer files or
production download directories are touched. Broader signed URL and modern stream
qualification remain separate from this local publication contract.
