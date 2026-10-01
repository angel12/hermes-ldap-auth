# hermes-ldap-auth

LDAP / Active Directory password login for the [Hermes Agent](https://github.com/NousResearch/hermes-agent) web dashboard.

This is a Hermes plugin. It registers a `DashboardAuthProvider` named `ldap` that checks each login with an **LDAP bind**, so Hermes never stores or hashes passwords. It works with OpenLDAP, Active Directory, FreeIPA, 389-ds, and any other LDAPv3 directory.

Once you sign in, Hermes's shared dashboard-auth framework takes over: the login form, `/auth/password-login`, session cookies, refresh, WebSocket tickets, logout, audit logging and the login rate limit.

## Install

```bash
hermes plugins install https://github.com/angel12/hermes-ldap-auth --enable
```

Hermes doesn't load user plugins until they're enabled. Without `--enable`, you get an interactive prompt; otherwise run `hermes plugins enable dashboard-auth-ldap` later. Enabling the plugin installs its one dependency, [`ldap3`](https://pypi.org/project/ldap3/) (pure Python, so it works on native Windows and Termux), into the Hermes environment.

The plugin does nothing until `dashboard.ldap_auth` is configured. Restart the dashboard after changing the config.

Requires Hermes 0.21 or newer.

## Configure

There are two bind modes, and you configure exactly one.

**Direct bind.** Use this when you know the DN shape. It's the simplest option and needs no service account:

```yaml
dashboard:
  ldap_auth:
    server_url: ldaps://ldap.example.com
    user_dn_template: "uid={username},ou=people,dc=example,dc=com"
    secret: "<32+ random bytes, base64>"   # openssl rand -base64 32
```

**Search-then-bind.** A service account finds the user first, then the plugin binds as them. You need this mode for Active Directory `sAMAccountName` logins, and whenever you want the email and display name in the session:

```yaml
dashboard:
  ldap_auth:
    server_url: ldaps://dc01.corp.example.com
    bind_dn: "CN=svc-hermes,OU=Service Accounts,DC=corp,DC=example,DC=com"
    bind_password: "..."                     # or HERMES_DASHBOARD_LDAP_BIND_PASSWORD in .env
    user_search_base: "OU=Staff,DC=corp,DC=example,DC=com"
    user_search_filter: "(sAMAccountName={username})"
    require_group: "CN=hermes-users,OU=Groups,DC=corp,DC=example,DC=com"
    secret: "<32+ random bytes, base64>"
```

### All keys

| Key | Default | Notes |
|---|---|---|
| `server_url` | — | Required. Must be `ldaps://`, or `ldap://` together with `start_tls` or `allow_insecure`. |
| `user_dn_template` | — | Direct bind. Must contain `{username}`, which is RFC 4514-escaped before substitution. |
| `bind_dn` / `bind_password` | `""` | Service account for search mode. Leave `bind_dn` empty for an anonymous search. |
| `user_search_base` | — | Search mode. Mutually exclusive with `user_dn_template`. |
| `user_search_filter` | `(uid={username})` | Use `(sAMAccountName={username})` for AD. The username is RFC 4515-escaped. |
| `require_group` | `""` | Group DN. Checks `member`, `uniqueMember` and `memberUid`. Non-members get the same generic 401 as a wrong password. |
| `start_tls` | `false` | Upgrades a plain `ldap://` connection. |
| `allow_insecure` | `false` | Explicitly permits cleartext `ldap://`. Don't use it. |
| `ca_certs_file` | `""` | Private CA bundle. Certificate validation is always on. |
| `email_attribute` / `display_name_attribute` | `mail` / `cn` | Search mode only. |
| `display_name` | `LDAP` | Label on the login form. |
| `secret` | random per process | Token-signing key (base64, hex, or raw). If unset, sessions don't survive restarts or span workers. |
| `session_ttl_seconds` | `43200` (12h) | Access-token lifetime. |
| `refresh_ttl_seconds` | `2592000` (30d) | Refresh-token lifetime. |
| `timeout_seconds` | `5` | Connect and receive timeout. |
| `verify_user_on_refresh` | `true` | Search mode: re-checks that the account still exists at each refresh. |

### Environment overrides

An environment variable wins over `config.yaml` when it's set and non-empty:

`HERMES_DASHBOARD_LDAP_SERVER_URL`, `_USER_DN_TEMPLATE`, `_BIND_DN`, `_BIND_PASSWORD`, `_USER_SEARCH_BASE`, `_USER_SEARCH_FILTER`, `_REQUIRE_GROUP`, `_START_TLS`, `_ALLOW_INSECURE`, `_CA_CERTS_FILE`, `_SECRET`, `_TTL_SECONDS`

All of them share the `HERMES_DASHBOARD_LDAP` prefix. Put credentials (`_BIND_PASSWORD`, `_SECRET`) in `~/.hermes/.env` rather than in `config.yaml`.

## Security posture

- **TLS is required.** Cleartext `ldap://` without StartTLS is refused unless `allow_insecure: true` is set.
- **Empty passwords are rejected before any bind.** LDAP treats an empty password as an *anonymous* bind, so accepting one would bypass authentication.
- **No LDAP injection.** Usernames are escaped before they go into a filter or DN.
- **No account probing.** An unknown user and a wrong password look the same. In search mode, a dummy bind evens out the response timing.
- **Referral chasing is off.** The plugin never replays credentials to a host that the directory names.
- **A filter that matches more than one entry rejects the login.**

### Session freshness

Sessions are stateless signed tokens. The plugin contacts the directory only at **login** and, in search mode, at each **token refresh**.

- **Deleted or moved accounts.** In search mode, the refresh check cuts them off within `session_ttl_seconds` (12h by default).
- **Disabled accounts are not detected.** The refresh check only asks whether the DN still exists. An account that is merely disabled (AD `userAccountControl`, OpenLDAP `pwdAccountLockedTime`) keeps refreshing until its refresh token expires. If you need immediate lockout, delete or move the entry, or shorten `refresh_ttl_seconds`.
- **Direct-bind mode re-checks nothing.** It has no service credentials, so sessions last until the refresh token expires whatever happens to the account.

### Group-restriction caveats

- **Direct membership only.** `require_group` reads the group entry's own `member`, `uniqueMember` and `memberUid` values. AD *nested* groups and `primaryGroupID` membership read as non-members.
- **Group ACLs.** The check runs on the user's own connection, so authenticated users must be allowed to read the group entry.
- **DN form in direct-bind mode.** The templated DN must match the group's `member` value exactly, so a difference in spacing or attribute case rejects an otherwise valid login. Search mode avoids this because the DN comes from the directory.

## Troubleshooting

If the dashboard says no auth provider is available, check `~/.hermes/logs/agent.log` for `dashboard-auth-ldap:` lines. They explain why the provider didn't register, such as no bind mode, an invalid setting (for example plain `ldap://` without TLS), or `ldap3` not installed. A missing `server_url` counts as "not configured" and is only logged at debug level. If `ldap3` is missing, run `hermes pm repair` and restart.

## Development

The tests run against a real Hermes checkout, the same setup as CI. Hermes refuses to build wheels, so its own package manager builds the environment:

```bash
git clone https://github.com/NousResearch/hermes-agent ../hermes-agent
(cd ../hermes-agent && python -m pm.build_env --source . --out .venv --group dev --group test)
python -m pip install --target .deps "ldap3>=2.9.1,<3"
PYTHONPATH=../hermes-agent:.deps ../hermes-agent/.venv/bin/python -m pytest tests
PYTHONPATH=../hermes-agent:.deps HERMES_HOME="$(mktemp -d)" ../hermes-agent/.venv/bin/python -m hermes_cli.main plugins validate .
```

`tests/test_discovery.py` installs the plugin into a temp `HERMES_HOME` and loads it through Hermes's real `PluginManager`.

## License

MIT. `_shared.py` is adapted from hermes-agent's `plugins/dashboard_auth/_shared.py` (MIT, Nous Research).
