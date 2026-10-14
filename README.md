# Society Library Management System (Offline)

A local Windows desktop application built with Python, Tkinter, and SQLite. It does not require internet access at runtime. The database and files are stored under `%LOCALAPPDATA%\SocietyLibrary` on Windows (or the home directory equivalent on other platforms).

## Current implementation scope

Included in this staged baseline:
- First-run setup creates exactly one Admin and four Librarian accounts; each password is chosen locally and must be at least 10 characters.
- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes.
- SQLite database with foreign keys, transaction-safe issue/return operations, one-active-loan-per-copy constraint, and audit records for key actions.
- Books and individual physical copies, accession numbers, cover paths, configurable rack/shelf/compartment locations; book list export uses the same columns as the import template.
- Member registration and duplicate/format validation.
- Issue and return workflows with 7/15/21/28-day issue periods; a member may hold no more than two active issues at once.
- Effective-dated daily penalty rules with grace days and optional maximum penalty.
- Waiting-list queue available from the Issue screen when a title has no available copy; in-app notification appears when a matching copy is returned.
- Fuzzy catalogue search, dashboard, inventory/active-loan/overdue/waiting reports.
- Excel/PDF report export, book/member Excel export, Excel/CSV import with row-level error report, database backup/restore. Book export produces one row per physical copy and is compatible with the book import columns.
- Unit tests for account setup, permissions, availability, circulation, penalty calculation, duplicates, and inactive members.

This is a staged baseline, not yet a fully verified production release. In particular, penalty-payment allocation and outstanding-balance accounting, complete user activation/deactivation screens, date/member/librarian report filters, bulk multi-copy editing, robust image lifecycle management, and end-to-end Windows packaging/restore testing remain follow-up work. See the checklist below before using it for live circulation.

## Install and run

1. Install Python 3.11 or later from the official Python distribution. During installation, enable **Add Python to PATH**.
2. Extract this folder to a writable local directory.
3. Open Command Prompt in the extracted `library_management_system` folder.
4. Create and activate a virtual environment:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Run:

   ```bat
   python run_library.py
   ```

6. On first launch, set the Admin password and all four Librarian passwords. Usernames are `admin`, `librarian1`, `librarian2`, `librarian3`, and `librarian4`. Do not use a shared or easily guessed password.

No internet connection is needed after Python and dependencies have been installed.

## Excel templates

The Books import sheet uses these column names (row 1):

`title, author, publisher, edition, isbn, language, page_count, category, publication_year, cover_path, acquisition_date, source, cost, remarks, accession_no, rack, shelf, compartment`

The Members import sheet uses:

`member_id, sno, name, father_name, address, registration_no, mobile, registration_date, status, remarks`

Dates should be ISO format `YYYY-MM-DD` where possible. Each book import row currently represents one physical copy and requires a unique `accession_no`. Duplicate rows are rejected and reported; existing records are not overwritten.

To create a template, run this in the project environment:

```python
from library_app.io_utils import export_template, BOOK_FIELDS, MEMBER_FIELDS
export_template('books_template.xlsx', BOOK_FIELDS)
export_template('members_template.xlsx', MEMBER_FIELDS)
```

Legacy `.xls` files require the optional `xlrd` package listed in `requirements.txt`.

## Data, backup, and restore

- Database: `%LOCALAPPDATA%\SocietyLibrary\library.sqlite3`
- Covers: `%LOCALAPPDATA%\SocietyLibrary\covers\`
- Logs: `%LOCALAPPDATA%\SocietyLibrary\logs\library.log`
- Backups: `%LOCALAPPDATA%\SocietyLibrary\backups\`

Use **Admin & Backup → Create database backup**. Keep a second backup on separate local removable media. Restoring replaces the current database; create a fresh backup first. Book cover images are stored separately, so back up the entire `SocietyLibrary` folder to preserve them.

## Tests

From the project folder:

```bat
pytest -q
```

## Windows executable packaging

After the app and tests have been validated in the target Windows environment:

```bat
pyinstaller --noconfirm --clean --windowed --name SocietyLibrary run_library.py
```

The executable is created under `dist\SocietyLibrary\` (one-folder mode). Keep the writable data folder separate from the executable. Test launch, database creation, backup, restore, and offline operation on a clean Windows account before deployment.

## Feature checklist

| Requirement | Status in this baseline |
|---|---|
| Offline desktop GUI and SQLite | Implemented; smoke test still required on target Windows PC |
| One Admin + four Librarians on first setup | Implemented; unit tested |
| Secure password hashing | Implemented; authentication unit tested |
| Role checks in service layer | Admin-only penalty configuration tested; broader admin controls incomplete |
| Book catalogue and multiple physical copies | Implemented; duplicate accession tested |
| Excel/CSV book and member imports | Implemented with row-level error export; comprehensive format tests pending |
| Member registry and validation | Implemented; broader validation tests pending |
| Issue/return and configurable loan period | Implemented; core workflow tested |
| Waiting queue and in-app notification status | Implemented at service level; member-facing notification screen pending |
| Effective-dated overdue penalties | Implemented for daily rate, grace days, cap; partial-day/holiday rules not fully implemented |
| Penalty payments and outstanding balances | Payment recording schema/service started; allocation and balance workflow pending |
| Fuzzy search | Implemented using standard-library matching; ranking tests pending |
| Reports and Excel/PDF export | Basic reports implemented; filters and printing workflow pending |
| Backup/restore and logging | Implemented; disaster-recovery validation pending |
| Full auditability, deletion/archive administration | Audit basics and archive field present; admin archive workflow pending |
| Automated tests for all requested requirements | Core tests included; full coverage pending |
| Production-ready certification | **Not yet complete** |


## Stage 3 changes

- User-facing circulation terminology uses **Issue** rather than **Loan**. The internal SQLite table remains named `loans` to preserve existing databases.
- Books can be exported to Excel. The export is one row per physical copy and matches the book import column format; matching title metadata is grouped on import to rebuild a title with multiple copies.
- If a title has no available copy, select the waiting-list checkbox and confirm to register the member. When a copy is returned, the first waiting member is marked notified and a notification message is shown to the librarian.
- Returns are selected by member name, then by the issued title/copy held by that member.
- The service layer enforces a maximum of two active issues per member.
- Only Admin can remove books or members. Records with historical references are archived/deactivated rather than physically erased; books with an active issue cannot be removed.
- Added tests for the two-issue limit, waitlist notification, and admin-only removal.


## Stage 4 interface improvements

- Dashboard now displays Total Members and Active Members alongside inventory and circulation summaries.
- The Issue / Return screen has a vertical scrollbar and supports mouse-wheel scrolling, so the return controls and transaction history remain reachable on smaller screens.
- The application uses an ocean-blue and pale-blue theme with larger, higher-contrast buttons, tabs, table headings and dashboard counters.

To update an existing installation, close the application, back up the project and database, extract the updated project files, then run `python run_library.py` from the project directory with its virtual environment activated. Existing local data remains under `%LOCALAPPDATA%\SocietyLibrary`.
