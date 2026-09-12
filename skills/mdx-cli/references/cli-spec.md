# MDX CLI Specification

This reference describes the `mdx` CLI implemented by `mdx_cli.main:app`.

## Runtime

- Package script: `mdx = mdx_cli.main:app`
- Python: 3.13+
- Install locally: `uv tool install .`
- Update locally: `git pull && uv tool install . --force`
- Must run from MDX internal network, MDX VPN, or an MDX VM.
- API base: `https://oprpl.mdx.jp`
- SSO IdP: `mdxidm.mdx.jp`

## Global Options

| Option | Meaning |
|---|---|
| `--verbose`, `-v` | Enable API request/response debug logging. |
| `--install-completion` | Install shell completion through Typer. |
| `--show-completion` | Print shell completion script. |
| `--help` | Show help. |

Project-scoped commands usually accept `--project-id`, `-p`; it also reads `MDX_PROJECT_ID`. If omitted, the saved project from `mdx project select` is used.

## Environment And Settings

| Environment variable | Default | Meaning |
|---|---|---|
| `MDX_BASE_URL` | `https://oprpl.mdx.jp` | API base URL. |
| `MDX_DEFAULT_PROJECT_ID` | unset | Pydantic setting, but project resolution uses CLI option, `MDX_PROJECT_ID`, or saved project. |
| `MDX_PROJECT_ID` | unset | Typer env var for project-scoped commands. |
| `MDX_REQUEST_TIMEOUT` | `120` | HTTP timeout in seconds. |
| `MDX_TASK_POLL_INTERVAL` | `3` | Task polling interval in seconds. |
| `MDX_TASK_POLL_TIMEOUT` | `600` | Task polling timeout in seconds. |

Configuration directory: `~/.config/mdx-cli/`.

## Output

- Most list/show commands default to Rich table output.
- Use `--json` for JSON output and quiet API spinners.
- For automation, prefer `--json | jq ...`.

## Name Patterns

VM targets and deploy names support patterns:

| Pattern | Meaning |
|---|---|
| `my-vm` | One VM. |
| `my-vm-{0-9}` | `my-vm-0` through `my-vm-9`; deploy converts single-digit numeric ranges to MDX API `[0-9]` notation. |
| `crawler-{a-g}-{0-9}` | 70 VMs; deploy batches by alphabet range and server-side numeric expansion. |
| `node-{00-05}` | Zero-padded range, client-expanded. |
| `vm-{1-99}` | Multi-digit range, client-expanded. |
| `worker-*` | Shell-style match for existing VM names. Quote this in the shell. |

Always quote patterns containing `*`, `{}`, or spaces.

## Authentication

| Command | Purpose | Notes |
|---|---|---|
| `mdx auth login` | Login through Shibboleth SSO. | Interactive username/password/OTP. Saved username/password become defaults. MDX Local Auth only; Gakunin is unsupported. |
| `mdx auth status` | Show whether a token is saved. | Shows saved username when available. |
| `mdx auth logout` | Delete token and saved credentials. | Removes all stored credentials for this CLI. |

Tokens are auto-refreshed where possible. If token refresh fails, normal API auth handling can prompt re-login.

## Projects

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx project list [--json]` | none | List assigned projects. |
| `mdx project summary [-p ID] [--json]` | project optional | Show VM counts, disk/pack resources, and storage usage. |
| `mdx project select` | interactive | Select and save the default project. |
| `mdx project show [project-id] [-p ID] [--json]` | explicit ID, environment, or saved project | Show ID, name, type, applicant, begin, and limit. |
| `mdx project resources [-p ID] [--json]` | project optional | CPU/GPU requested, used, current/future allocation, Rmin, storage, and global IP resources. |
| `mdx project users [-p ID] [--json]` | `--page`, `--page-size`, `--ordering`, `--username`, `--email`, `--auth` | List project users; all pages by default. |
| `mdx project points [-p ID] [--json]` | project optional | Total remaining balance, last consumption time, purchased/used/remaining points, and expiration dates. |
| `mdx project usage [-p ID]` | `--days`, `--hours`, `--start`, `--end`, `--lang`, `--json`, `--html`, `--output` / `-o` | Read resource usage and consumed points through a report POST. |
| `mdx project overview [-p ID] [--json]` | `--kind all\|resource\|resource_list\|vm\|spot_vm\|guarantee_vm` | Dashboard resources and VM counts; all five sections by default. |
| `mdx project storage <project-id> [--json]` | required ID | Show storage information. |
| `mdx project keys <project-id> [--json]` | required ID | List access keys. |

`project list --json` retains tenant `name` and nested `projects[]`; text output includes the tenant beside each project.
Tenants do not need a UUID. Empty tenants are not selectable. Legacy flat project responses are also accepted.
`project select` flattens nested projects in organizations and saves the selected project UUID.

`project users` defaults to all pages, fetched in batches of 100. Use `--page N` (1-based) for one page;
`--page-size` accepts 1–100. JSON contains `count` and `results`; single-page mode also retains server pagination
metadata and the server's total count, while all-page mode sets `count` to the number of fetched users.
Sort/filter strings pass through unchanged. Use `--ordering=-username` for descending order.
Exact versus partial filter matching is not verified. Point requests have no pagination parameters.
The user `auth` field is an authentication method (e.g. `学認` or `mdx認証基盤`), not a permission role.

`project points` displays a separate total remaining balance, summing every `remaining_points` value with Decimal.
No expiration filtering is applied. JSON adds `total_remaining_points` as a decimal string.
If any balance is missing, nonnumeric, or nonfinite, the total is unavailable (`null` in JSON), not a partial sum.

Normal `project overview` output expands nested objects and arrays into individual field/value rows grouped by
resource overview, allocated resources, dedicated VMs, spot VMs, and guaranteed VMs. Known keys use Japanese labels;
unknown keys remain visible. JSON retains the original response structure.

`project usage` defaults to the last 7 days. `--days` accepts 7, 30, 90, or 365 and maps to `input_type` 1–4.
For a custom range, supply both `--start 'YYYY-MM-DD HH'` and `--end 'YYYY-MM-DD HH'` (`input_type: 0`),
with end later than start. Custom ranges cannot be combined with `--days`. Hours must be 00–23;
no timezone conversion is performed. Server timezone and endpoint inclusivity remain unverified.
The report body language is `--lang jp` (default) or `--lang en`.

Use `--hours 24` for the 24 hours ending at the latest whole hour in JST (UTC+09:00), independent of the OS timezone.
For example, at September 12 14:37 JST it submits September 11 14:00 through September 12 14:00 with `input_type: 0`.
Minute-level rolling windows are not supported by the API contract. Any positive integer hour count is accepted;
`--hours` cannot be combined with `--days`, `--start`, or `--end`.
Text output shows the actual submitted period. JSON adds `period` with `start`, `end`, `hours`, and `timezone: "JST"`.
The CLI uses JST to construct the request; server timezone/endpoint inclusivity are still not independently established.

Normal usage output displays HTML tables. JSON includes the original response plus `tables`, each containing
`caption`, `headers`, and `rows`. Row/column spans are expanded by duplicating cell text; multiple header rows
are joined with ` / `. Tables without headers have `headers: []`. All cells, including totals and numeric values,
remain strings to preserve units and precision. Convert only known numeric columns downstream.
`--html` writes raw HTML to stdout; `--output PATH` saves UTF-8 HTML. These two options and `--json` are mutually
exclusive. `err_msg` and empty HTML fail with exit status 1. A report without tables fails in text mode;
HTML and JSON modes still allow inspecting it.

API paths use `/api/project/{id}/summary/`, `/resources/`, `/point/`, and POST `/resource_usage/`.
Users use GET `/api/user/project/{id}/`. Overview sections use GET `/api/project/{id}/overview/{kind}/`.
The standard client sends `Authorization: JWT <token>`, `Content-Type: application/json`, and
`Accept-Language: ja`. `MDX_BASE_URL` stays the origin URL without `/api`.
These contracts are based on the supplied portal implementation; automated tests use synthetic responses.
On 2026-09-12, live execution confirmed assigned projects, summary, resources, users, points, all five overview
sections, and seven-day report HTML/table extraction for one normal project. Other project types and permission
differences remain unverified.
The custom range `2026-09-05 00` to `2026-09-12 00` in English, HTML file output, and explicit user pagination
with ordering were also exercised successfully.

## VM Inventory

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx vm list [-p ID] [--json]` | project optional | List VMs. |
| `mdx vm show [target] [-p ID] [--json]` | target is UUID or exact VM name; omitted means interactive list | Show VM detail including OS, resources, disks, service networks, storage networks, and VMware Tools. |
| `mdx vm sync [-p ID]` | project optional | Request VM information sync. |
| `mdx vm csv [target] [-p ID] [-o PATH]` | target pattern optional | Export Web portal-compatible CSV. Without `-o`, writes stdout. |

`vm csv` fetches per-VM CSV detail in parallel and emits columns:

- `VM_NAME`
- `SERVICE_NET_<n>_IPv4` and `SERVICE_NET_<n>_IPv6` for `n = 1..8`
- `STORAGE_NET_<n>_IPv4` and `STORAGE_NET_<n>_IPv6` for `n = 1..8`

## VM Deploy

Command:

```bash
mdx vm deploy [options]
```

Options:

| Option | Meaning |
|---|---|
| `--project-id ID`, `-p ID` | Project ID; falls back to saved project or `MDX_PROJECT_ID`. |
| `--template TEXT`, `-t TEXT` | Template name substring, case-insensitive; first match is used. |
| `--name PATTERN`, `-n PATTERN` | VM name or batch pattern. |
| `--pack-type cpu|gpu` | CPU or GPU pack. |
| `--pack-num N` | Number of packs. CPU max is 152; GPU max is 8. |
| `--disk GB` | Disk size in GB. |
| `--service-level spot|guarantee` | Service level. |
| `--key PATH`, `-k PATH` | SSH public key path. Must be absolute or `~/...`. |
| `--power-on` | Start VM after deploy. |
| `--yes`, `-y` | Skip confirmation and nonessential prompts. If multiple segments exist and `--yes` is used, the first segment is selected. |
| `--no-wait` | Do not wait for deploy tasks. |

Interactive defaults:

- Template: numbered list.
- Segment: first segment automatically when only one; numbered list when multiple and not `--yes`.
- SSH public key: first of `~/.ssh/id_ed25519.pub`, `id_rsa.pub`, `id_ecdsa.pub`, then first `*.pub`.
- Pack type: `cpu` or `gpu`.
- Pack number: default `3` for CPU, `1` for GPU.
- Disk: template `lower_limit_disk`.
- Service level: `spot` or `guarantee`.
- Auto power-on: confirm unless `--power-on` or `--yes`.

Deploy creates one or more tasks. Without `--no-wait`, it waits for all task IDs in parallel and prints final status.

Example:

```bash
mdx vm deploy \
  -t "Ubuntu 22.04" \
  -n "worker-{a-e}-{0-9}" \
  --pack-type cpu \
  --pack-num 3 \
  --disk 40 \
  --service-level spot \
  -k ~/.ssh/id_ed25519.pub \
  --power-on \
  -y \
  --no-wait
```

## VM Lifecycle

All target arguments accept UUID, exact name, or name pattern.

| Command | Arguments/options | Behavior |
|---|---|---|
| `mdx vm start <target> [-p ID] [-s LEVEL]` | `--service-level`, `-s`, default `spot` | Starts VMs with the requested service level. Confirms only when multiple VMs match. |
| `mdx vm stop <target> [-p ID]` | none | Force power off. Use `shutdown` for graceful OS shutdown. Confirms only when multiple VMs match. |
| `mdx vm shutdown <target> [-p ID]` | none | Graceful shutdown. Confirms only when multiple VMs match. |
| `mdx vm reboot <target> [-p ID]` | none | Reboot. Confirms only when multiple VMs match. |
| `mdx vm reset <target> [-p ID]` | none | Hard reset. Always asks a high-risk confirmation. |
| `mdx vm destroy <target> [-p ID] [--no-wait]` | none | Deletes VMs. If any are `PowerON`, force-stops them, waits for power-off, then destroys. Always asks a high-risk confirmation. |

Bulk lifecycle operations run in chunks of 30 and refresh the token before each chunk. Parallel action progress is displayed.

## VM Reconfigure

Command:

```bash
mdx vm reconfigure [target] [-p ID] [--no-wait]
```

Behavior:

- If target is omitted, choose from a VM list.
- If target is a pattern, multiple VMs can be reconfigured together.
- Fetches full VM details before reconfiguring.
- For multiple VMs, all must have the same `pack_type` and the same disk count.
- If any target is `PowerON`, asks to shut down, sends shutdown requests, and waits for power-off.
- Prompts for new pack count and each disk capacity.
- Keeps each VM's existing disk `device_key` and network segment where possible.
- Without `--no-wait`, waits for reconfigure task completion.

## VM SSH

Command:

```bash
mdx vm ssh [target] [-p ID] [-u USER] [-i KEY] [-g]
```

Options:

| Option | Meaning |
|---|---|
| `--user USER`, `-u USER` | SSH username; default `mdxuser`. |
| `--identity PATH`, `-i PATH` | Private key path, `~/` supported. |
| `--global`, `-g` | Use global IP instead of private IP when available. |

If target is omitted, it lists only `PowerON` VMs. It uses the first service network. When the user is still the default `mdxuser`, it tries to infer the template `login_username` from template metadata and VM host name. The command ends by `execvp`-ing `ssh`.

## Network Segments

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx network segment list [-p ID] [--json]` | project optional | List segments. |
| `mdx network segment show [segment-id] [-p ID] [--json]` | segment optional | Show segment summary; if omitted, auto-selects only segment or asks from list. |

## Global IP Checks

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx network ips [-p ID] [--json]` | project optional | List assignable global IPs. |
| `mdx network check-ip [-p ID] [--json] [--fix]` | project optional | Show global IPv4 usage across assignable IPs, DNAT, and direct VM assignment. Detects stale DNAT to dead `10.15.*` VM IPs. |
| `mdx network check-acl [-p ID] [--json] [--fix]` | project optional | Scan all segment ACLs for host rules to dead `10.15.*` VM IPs. |

`check-ip` status values in JSON:

- `未使用`
- `VM割当`
- `DNAT`

`check-acl` status values in JSON:

- `alive`
- `hole`
- `range`

Deletion safety:

- Without `--fix`, stale DNAT/ACL deletion is interactive.
- With `--fix`, stale rules are deleted without confirmation.
- If VM detail fetching partially fails, cleanup is skipped to prevent false deletion.

## DNAT

Commands live under `mdx network dnat`.

| Command | Arguments/options | Behavior |
|---|---|---|
| `list [-p ID] [--json]` | project optional | List DNAT rules. |
| `add [-p ID]` | interactive | Pick an assignable global IP, resolve segment, enter private destination IP, confirm, create DNAT. |
| `edit [dnat-id] [-p ID]` | interactive | Pick existing rule if ID omitted, choose global IP, resolve segment, edit destination IP, confirm, update. |
| `delete [dnat-id] [-p ID] [-y]` | interactive unless ID and `-y` | Delete DNAT rule. |

## ACL

Commands live under `mdx network acl`.

| Command | Arguments/options | Behavior |
|---|---|---|
| `list [segment-id] [-p ID] [--json]` | segment optional | Resolve segment and list ACLs. |
| `add [segment-id] [-p ID] [--json]` | interactive | Select protocol `TCP`/`UDP`/`ICMP`, source address/mask/port, destination address/mask/port, confirm, create ACL. |
| `edit [acl-id] [--segment-id ID] [-p ID] [--json]` | interactive | Resolve segment, find ACL, edit current values, confirm, update ACL. |
| `delete [acl-id] [--segment-id ID] [-p ID] [-y]` | interactive unless ID and `-y` | Delete ACL rule. |

Defaults for ACL add:

- Source address: `0.0.0.0`
- Source mask: `0.0.0.0`
- Source port: `Any` for TCP/UDP; omitted for ICMP
- Destination mask: `255.255.255.255`
- Destination port: `Any` for TCP/UDP; omitted for ICMP

## Templates

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx template list [-p ID] [--json]` | project optional | List templates. |
| `mdx template show [template-id] [-p ID] [--json]` | template optional | Show detail; if omitted, choose from list. |

Template detail includes UUID, template name, OS, OS type, GPU requirement, minimum disk, minimum memory, hardware version, login username, description, creator, publication date, scope, and summary URL when present.

## Tasks And History

| Command | Arguments/options | Purpose |
|---|---|---|
| `mdx task list [-p ID] [-n LIMIT] [-t TYPE] [--json]` | limit default `100`, max `1000` | List operation history. |
| `mdx task status <task-id> [--json]` | required task ID | Show task status. |
| `mdx task wait <task-id> [--json]` | required task ID | Wait for completion using configured poll interval and timeout. |

Common `--type`, `-t` values are operation names such as `デプロイ` and `自動休止`.

## Safe Planning Examples

List running VMs:

```bash
mdx vm list --json | jq '.[] | select(.status == "PowerON") | .name'
```

Inspect before bulk shutdown:

```bash
mdx vm list --json | jq '.[] | select(.name | test("^worker-")) | {name, status, uuid}'
mdx vm shutdown "worker-*"
```

Deploy then follow tasks manually:

```bash
mdx vm deploy -t "Ubuntu" -n "worker-{0-9}" --pack-type cpu --pack-num 3 --disk 40 --service-level spot -k ~/.ssh/id_ed25519.pub --no-wait
mdx task status <task-id>
```

Audit network holes without deleting:

```bash
mdx network check-ip
mdx network check-acl
```

Delete stale holes only after explicit approval:

```bash
mdx network check-ip --fix
mdx network check-acl --fix
```
