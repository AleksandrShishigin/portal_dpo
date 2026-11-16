import hashlib
from django.db import migrations


def fill_metadata(apps, schema_editor):
    Document = apps.get_model('portal', 'Document')
    for document in Document.objects.filter(sha256='').iterator():
        try:
            with document.file.open('rb') as file:
                digest = hashlib.sha256()
                for chunk in file.chunks():
                    digest.update(chunk)
                document.size, document.sha256 = file.size, digest.hexdigest()
                document.save(update_fields=['size', 'sha256'])
        except OSError:
            pass  # Existing missing files are reported by the submit validation.


class Migration(migrations.Migration):
    dependencies = [('portal', '0003_preserve_existing_applications')]
    operations = [migrations.RunPython(fill_metadata, migrations.RunPython.noop)]
