LUXE MEN — fixes, split by source file
=======================================

Each .patch file below corresponds to exactly one file in your repo.
File naming: path/to/file.py  ->  path_to_file.py.patch

Apply an individual patch:
    cd luxe-men-boutique
    git apply /path/to/patches/accounts_views.py.patch

Apply all of them at once:
    cd luxe-men-boutique
    git apply /path/to/patches/*.patch

If a patch fails to apply (e.g. you've since edited that file yourself),
open the .patch — it's a plain unified diff, human-readable — and apply
the change by hand to your version of the file.

---------------------------------------------------------------------
accounts_models.py.patch
  -> accounts/models.py
  Adds 'user_suspended' / 'user_unsuspended' to AuditLog.ACTION_CHOICES.
  NOTE: run `python manage.py makemigrations accounts` after applying —
  this is a field-metadata change Django wants a migration for.

accounts_urls.py.patch
  -> accounts/urls.py
  Registers the new staff 2FA verification route.

accounts_views.py.patch
  -> accounts/views.py
  - LoginView: staff accounts now get emailed a 6-digit code and don't
    get a session until it's verified.
  - Adds StaffTwoFactorVerifyView (the second half of that flow).

NEW_FILE__templates_accounts_login_2fa_verify.html
  -> templates/accounts/login_2fa_verify.html
  This is a brand new file (not a diff) — just drop it in at that path.
  The page the staff 2FA code is entered on.

config_settings_base.py.patch
  -> config/settings/base.py
  Registers StaffSessionTimeoutMiddleware and adds the
  STAFF_SESSION_TIMEOUT_SECONDS setting (default 900s / 15 min).

core_admin_views.py.patch
  -> core/admin_views.py
  - AdminSuspendUserView / AdminUnsuspendUserView now write AuditLog
    entries.
  - AdminSuspendUserView now blocks a staff member from suspending
    another staff account (unless they're a super-admin) or themselves.

core_middleware.py.patch
  -> core/middleware.py
  Adds StaffSessionTimeoutMiddleware — shorter sliding session timeout
  for is_staff users only.

seed_data.py.patch
  -> seed_data.py
  Superuser/demo customer accounts no longer get a hardcoded, publicly
  visible password. Production requires SEED_ADMIN_PASSWORD via env;
  dev generates and prints a random one instead.

start.sh.patch
  -> start.sh
  Seeding no longer runs automatically on every boot — only when
  RUN_SEED=true is set.

templates_core_build_your_look.html.patch
templates_core_home.html.patch
templates_products_partials_shop_product_grid.html.patch
templates_products_product_detail.html.patch
  -> matching paths under templates/
  Replace hardcoded "$" / "KES" with {{ CURRENCY_SYMBOL }} so price
  display is consistent site-wide.

cleanup__remove_debug_and_dead_files.patch
  -> deletes: temp_debug_mpesa.py, temp_search.txt, templates.zip,
     templates/core/home_backup.html
  Removes debug/dead files that shouldn't be in the repo.
---------------------------------------------------------------------

Still outstanding (not yet in these patches, say the word if you want them):
  - AdminUserForm exposes `is_staff` to any user with only the
    'access_user_management' permission (privilege escalation).
  - `{{ message|safe }}` in login.html / resend_verification.html lets
    unescaped user input (the submitted email) render as raw HTML/JS.
