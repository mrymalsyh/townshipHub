from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Lets PostgreSQL combine 'same facility' with 'overlapping time' in one rule."""

    dependencies = []
    operations = [BtreeGistExtension()]
