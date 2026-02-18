# emoscreen/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/bulk-upload/", include(("content.urls", "content"), namespace="content_admin")),
    path("admin/", admin.site.urls),
    path("", include("content.urls")),  # your app's other routes
    path("", include("paid.urls")),
    path("oauth/", include("social_django.urls", namespace="social")),  # NEW
    path("auth/complete/", include("content.auth_urls")),               # NEW
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
