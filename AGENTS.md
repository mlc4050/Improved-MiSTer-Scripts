# Script versioning

For every major script change, increment the script's version number in both its
filename (for example, `_v1.py` to `_v2.py`) and its `VERSION` constant, when present.
Update README links, usage examples, and other references to the new filename.
Use Git history for previous versions rather than leaving duplicate old scripts.
Small corrections do not require a version bump unless the user requests one.
