from django.conf import settings
from django.conf.urls.static import static

from django.urls import path
from . import views

urlpatterns = [
    path("", views.about, name="about"),
    path("about/", views.about, name="about"),
    path("metrics/", views.metrics, name="metrics"),
    path("dvm/", views.dvm, name="dvm"),
    path("dvm/<str:pub_key>/", views.dvm, name="dvm_with_pub_key"),
    path("kind/", views.kind, name="kind"),
    path("kind/<str:kind_num>/", views.kind, name="kind_with_kind_num"),
    path("event/<str:event_id>/", views.see_event, name="see_event"),
    path("npub/<str:npub>/", views.see_npub, name="see_npub"),
    path("debug/", views.debug, name="debug"),
    path("debug/<str:event_id>/", views.debug, name="debug"),
    path("recent/", views.recent, name="recent"),
    path(
        "api/graph/<str:request_event_id>", views.get_graph_data, name="get_graph_data"
    ),
    path("playground/", views.playground, name="playground"),
]

handler404 = "monitor.views.custom_404"

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
