from django.contrib import admin


# Intentionally do not register admin_app.Activity here.
# The production activity table is events.Activity; admin_app.Activity is a legacy
# scaffold kept only for migration compatibility.
