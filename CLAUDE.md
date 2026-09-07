# Facekit

Flask backend for a face-recognition attendance system. Employees are onboarded with a
face scan, matched against a per-company FAISS index for attendance punches, and
optionally synced into an external "OfficeKit" HR system over SQL Server.

## Running / architecture

- Entry point: `main.py` (Flask app), served by gunicorn via `gunicorn_config.py`.
- Gunicorn reads the `PORT` env var natively (gunicorn itself defaults `bind` to
  `0.0.0.0:$PORT` when that var is set) — `gunicorn_config.py` does not set `bind`
  explicitly, so don't be surprised it's absent.
- Data stores:
  - **MongoDB** — one logical "database" per `compony_code` (e.g. `A100`, `A101`), each
    holding collections like `encodings_{compony_code}` (employee/face records),
    `branch_{compony_code}`, `agents_{compony_code}`, `shifts_{compony_code}`,
    `attandance_{compony_code}_{YYYY-MM}`. A separate
    `SettingsDB` database holds per-company feature-flag documents
    (`settings_{compony_code}`), read via `utility/settings.py::Settings`.
  - **OfficeKit SQL Server** — a separate external HR system, reached via
    `connection/db_officekit.py` (thread-local pymssql connections — do NOT share one
    connection across threads, it segfaults the C extension) and queried/written via
    `connection/officekit_onboarding.py::OnboardingOfficekit`. Only specific
    `compony_code`s have a real OfficeKit connection wired up
    (`_KNOWN_OFFICEKIT_COMPANIES` in `db_officekit.py`): default/`A100` (myG),
    `A101`/`A102` (Empire, shared DB), `A860` (Anjuman) — each with its own DB/host/
    credentials from `.env`. Any other `compony_code` gets no OfficeKit connection.

## Naming/spelling note

The existing codebase consistently misspells "company" as `compony` and "required" as
`requerd` (variable names, JSON keys, error strings) — this is intentional/established
convention throughout, not a typo to silently "fix". Match it in new code for
consistency rather than introducing a competing correct spelling.

## Settings pattern (feature flags per company)

`utility/settings.py::Settings` — a per-company key/value store (`SettingsDB.settings_{compony_code}`,
defaults in `Settings.DEFAULT_SETTINGS`). Read with `Settings.get_setting(compony_code, "Some Setting")`
(process-cached via `lru_cache`) in hot paths, or `Settings(compony_code).get_all()` for the full list.
Existing flags: `Location Tracking`, `Individual Login`, `Branch Management`, `Agency Management`,
`Shift Management`, `Office Kit Integration`, `List Employees`,
`Enable Create User`, `Office Kit Onboarding`, `Branch Wise Login`. New optional-employee-field
features (branch/agency/shift) all follow the same shape: a boolean setting that makes the
field required in `add-employee-face`'s `required_fields` list when turned on for that company.
(Policy does NOT follow this shape — see below, it's auto-derived server-side instead of app-selected.)

## Key blueprints/routes

- `blueprints/employee_bp.py` — `/add-employee-face` (add employee + face, the main onboarding
  endpoint), `/compare-face` (attendance punch), `/edit-user`, `/edit-employee-face`, `/all-employees`.
- `blueprints/branch_bp.py` — master-data CRUD for `branch`/`agency`/`shift`:
  `/add-branch`, `/get-branch`, `/get-agency`, `/set-agency`, `/add-shift`, `/get-shift`.
  The `add-*` endpoints only write to a local Mongo collection
  (`branch_{compony_code}`, `agents_{compony_code}`, `shifts_{compony_code}`)
  — for OfficeKit-integrated companies, the corresponding `get-*` endpoint ignores that local
  collection and instead reads live from OfficeKit (see below), so `add-*` is a no-op source for them.
  There is deliberately no `/add-policy` or `/get-policy` — policy is never app-selected, see below.
- `auth/controller.py` — `/add-employee` (create employee WITHOUT a face, lighter-weight), login/
  token endpoints, `/generate-employee-code`.
- `model/compony_model.py::ComponyModel` — company creation/login, and `_get_branch`/`_get_agents`/
  `_get_shift`, each branching on `Settings.get_setting(compony_code, "Office Kit Integration")`
  to decide Mongo-local vs. live-OfficeKit as the data source.
- `model/user_model.py::UserModel` — `edit_user_details` (edit/soft-delete an employee doc),
  attendance report queries, FAISS-based duplicate-face detection.
- `face_match/face_ml.py::FaceAttendance` — the actual face pipeline: `update_face` (onboarding:
  decode/validate images, generate embeddings, duplicate-check via FAISS, insert into
  `encodings_{company_code}`, fire a background OfficeKit onboarding thread), `compare_faces`
  (attendance punch matching).

## OfficeKit schema notes (verified live against production, 2026-09)

Discovered by direct read-only schema/data inspection since none of this was documented in-repo:

- **Shift master**: `HR_SHIFT00` (`ShiftID`, `ShiftCode`, `ShiftName`, `ShiftType`) joined to
  `HR_SHIFT01` (timing per shift — `StartTimeMinutes`/`EndTimeMinutes`, minutes-since-midnight; a
  split shift has multiple `HR_SHIFT01` rows, one per segment).
- **Shift assignment** (employee → shift): `SHIFT_MASTER_ACCESS` (`EmployeeID`, `ShiftID`,
  `IsCompanyLevel`, `Active`, `ValidDatefrom`/`ValidDateTo`, `WeekEndMasterID`, `ShiftApprovalID`,
  `ApprovalStatus`, `ProjectID`). No FK constraints on this table — safe to insert a minimal row.
- **Attendance policy master**: `ATTENDANCEPOLICY00` (`AttendancePolicyID`, `PolicyName`, plus
  late-in/OT/rounding rules). **Varies significantly per tenant** — myG has 2 policies, A101 has 5,
  A860 has 6, and there is no single safe "default" to hardcode (A860 in particular assigns a
  different policy per employee with no consistent pattern). Policy is deliberately NOT app-selected
  (no dropdown, no `/get-policy`) — it's auto-resolved server-side from the chosen shift, see below.
- **Policy assignment**: `ATTENDANCEPOLICY_MASTER_ACCESS` (`EmployeeID`, `PolicyID`, `IsCompanyLevel`,
  `Active`, `ValidDatefrom`/`ValidDateTo`, `IsExcludeBreakHours`). No FK constraints.
- `OnboardingOfficekit.add_user(employee_code, branch, agency, _, fullname, gender, shift=None)`
  does a multi-table insert in one transaction: `HR_EMP_MASTER` → `ADM_User_Master` →
  `HR_EMPLOYEE_USER_RELATION` → `ADM_UserRoleMaster` → `HR_EMP_IMAGES` → `HR_EMP_ADDRESS` →
  `BIOMETRICS_DTL` → (if `shift` given) `SHIFT_MASTER_ACCESS` → (if a policy resolves)
  `ATTENDANCEPOLICY_MASTER_ACCESS`, then commits. `branch`/`agency`/`shift` here are all OfficeKit
  **numeric IDs** (e.g. the `_id` field returned by `/get-branch`, `/get-agency`, `/get-shift`), never
  display names.
- `OnboardingOfficekit._resolve_policy_for_shift(shift_id)` is the auto-policy rule: look up the
  shift's name/code and total duration (`HR_SHIFT00`/`HR_SHIFT01`); if it looks like a ~24-hour shift
  (name/code contains "24", or total duration ≥ 20 hours), use whichever `ATTENDANCEPOLICY00` row has
  "guard" in its name (myG has one, "Guard Policy" id 2 — matches exactly, since it also requires 22
  min. work hours, consistent with round-the-clock guard duty); otherwise, or if the tenant has no
  "guard" policy at all (A101, A860 currently don't), fall back to the tenant's lowest
  `AttendancePolicyID` as its generic default. Verified live: myG's 3 known 24-hour shifts (ids 2/3/4)
  all resolve to policy 2, its normal shift (id 1) resolves to policy 1; A101/A860 always resolve to
  their id-1 policy regardless of shift, since neither has a "guard"-named policy to match.
- Before this, employees onboarded via the app never got a `SHIFT_MASTER_ACCESS` row at all — an
  OfficeKit admin had to assign shift manually after the fact (confirmed live: several recently
  created employees had zero shift assignment). The `shift` parameter (and the policy it now implies)
  closes that gap.

## Environments / deployment

Three systemd template services exist: `facekit@5001` (production, always active — nginx's
`facekit_backend` upstream and `/facekit/` location), `facekit@5002` and `facekit@5003` (spare/UAT
slots, normally inactive — nginx routes `/uatfacekit/` to `127.0.0.1:5002`). All three share the
exact same `WorkingDirectory` and the exact same `.env` — **there is only one `.env` in this repo,
and it holds production credentials for Mongo and all three OfficeKit databases (myG/Empire/
Anjuman)**. So starting `facekit@5002` gives you a separate app *process* for testing request/
response behavior, but it is NOT database-isolated: any write made through `/uatfacekit/...` (e.g.
`add-employee-face`) creates a real record in the real production Mongo and, if `Office Kit
Onboarding` is on for that company, a real row in the real production OfficeKit SQL Server. Genuine
data isolation would require a separate UAT `.env` with its own Mongo/OfficeKit credentials, which
does not currently exist.

Manage with `sudo systemctl restart facekit@5001|5002|5003` (passwordless sudo works for this).
