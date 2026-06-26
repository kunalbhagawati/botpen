"""Scaffolding services: everything behind `manage.py scaffold`.

Split by concern:
- ``scaffold``  - the Scaffold provisioning record (mint identity/token, CRUD, link a session).
- ``templates`` - render the playground skeleton (copier) into ``playgrounds/<slug>/`` (Phase 4).
- ``docker``    - docker provisioning: volumes, build, run, attach, the ACL helper (Phase 5).
- ``daemons``   - the in-container daemon set (relay / disk-monitor) wiring, run via `manage daemons` (Phase 5).
"""
