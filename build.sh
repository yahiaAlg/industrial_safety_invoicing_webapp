pip install -r requirements.txt

find . -path "./.venv" -prune -o -path "*/migrations/0*.py" -print | xargs rm -f

python manage.py makemigrations core clients accounts etudes formations resources financial

# NOTE: DB is PostgreSQL in production - never drop it here.
# Migration files are regenerated from scratch above, so the
# django_migrations bookkeeping table (not the actual data tables)
# is now stale/inconsistent with them. Clear just that tracking
# table, then re-migrate with --fake-initial so Django matches new
# migration files against tables that already exist instead of
# trying to recreate them or erroring on dependency order.
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('TRUNCATE django_migrations;')
"

# Built-in Django apps (contenttypes/auth/admin/sessions) are already
# fully migrated to their final schema in this production DB - their
# migration chains predate this project and are untouched by the
# regeneration above. --fake-initial only verifies the FIRST migration
# per app, so if we let it touch these, later built-in migrations
# (e.g. contenttypes.0002_remove_content_type_name) try to run real
# SQL against columns that were already dropped long ago -> crash.
# Fully fake their entire history instead - nothing to actually apply.
python manage.py migrate contenttypes --fake
python manage.py migrate auth --fake
python manage.py migrate admin --fake
python manage.py migrate sessions --fake

# Now handle this project's own apps. These were just regenerated into
# single 0001_initial files, so --fake-initial's table-existence check
# is reliable here: it fakes only if the table/columns already match.
python manage.py migrate --fake-initial

python manage.py collectstatic --noinput -v 0

#python manage.py seed_db

# python manage.py seed_db_minimal

# python manage.py seed_formations    # all 505 specialties

# python manage.py seed_initial_expenses      # 1000 random expenses for testing reports
