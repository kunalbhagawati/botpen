"""Scaffolding services: everything behind `botpen scaffold`.

Split by concern:
- ``scaffold``  - the Scaffold provisioning record (mint identity/token, CRUD, link a session).
- ``templates`` - render the playground skeleton (copier) into ``playgrounds/<slug>/``.
- ``docker``    - host-side docker provisioning: shared volume, build, run, attach, teardown
  (``/shared`` ops are delegated to the ``hub`` command).
"""
