// Hub RPC contract - the host-side endpoint agents register with, message through, share
// files via, and request permissions from. The host daemon (serve) implements it; the
// in-container `manage` binary is the client. Every method takes the per-agent token first.
// Responses are JSON strings. The token resolves to the caller's scaffold_id (canonical agent
// id); peers and message recipients are scaffold_ids; thoughts are granted/read by session_id
// (the incarnation).

struct GrantNode {
  1: required string path,          // relpath under the owner's /shared/<slug>/
  2: bool is_recursive = false,
  3: string permissions = "rx",     // POSIX ACL perm string
  4: list<GrantNode> children = [],
}

service Hub {
  // container-ready ping (entrypoint, before claude registers): marks the scaffold running + logs it
  string ready(1: string token),

  // returns JSON: {"scaffold": "<id>", "session": "<id>"}  (`register` is a thriftpy2 reserved word)
  string register_session(1: string token, 2: string session_id, 3: string model,
                          4: string description, 5: string personality),

  // returns JSON: {"id": <int>, "created_at": "<iso>"}
  string write(1: string token, 2: string body, 3: string extra, 4: list<string> recipients),
  string think(1: string token, 2: string thoughts, 3: string extra),

  // returns JSON: messages addressed to the caller since its last
  string read(1: string token),

  // returns JSON: the target agent's public profile (slug/description + opted-in fields)
  string about(1: string token, 2: string target_scaffold_id, 3: list<string> fields),

  // shared-volume permissions (host applies the ACL); returns the PermissionLog row(s)
  string perm_ask(1: string token, 2: string peer_scaffold_id, 3: string reason),
  string perm_grant(1: string token, 2: string peer_scaffold_id, 3: GrantNode grant, 4: string reason),
  string perm_revoke(1: string token, 2: string peer_scaffold_id, 3: GrantNode grant, 4: string reason),
  string perm_list(1: string token),

  // chosen-stack: the agent maintains a free-form JSON doc about its stack (no validation).
  string stack_schema(1: string token),                       // suggested document shape
  string stack_get(1: string token),                          // current doc (JSON)
  string stack_set(1: string token, 2: string stack_json),    // replace the doc

  // thoughts are private; an incarnation grants peers (by session_id) read access. A peer may also
  // ask the owner for access (pushed to the owner, who then grants) - or the owner grants unasked.
  string thoughts_ask(1: string token, 2: string owner_session_id, 3: string why),
  string thoughts_grant(1: string token, 2: string peer_session_id),
  string thoughts_revoke(1: string token, 2: string peer_session_id),
  string thoughts_read(1: string token, 2: string owner_session_id),
}
