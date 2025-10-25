"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

try:
    from django.core.management import call_command
    call_command('migrate', interactive=False)
    print("✅ Migrations applied successfully on startup.")
except Exception as e:
    print(f"⚠️ Migration error: {e}")

from django.contrib.auth import get_user_model

User = get_user_model()

try:
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        print("✅ Superuser 'admin' created successfully!")
    else:
        print("ℹ️ Superuser already exists, skipping creation.")
except Exception as e:
    print(f"⚠️ Superuser creation error: {e}")
