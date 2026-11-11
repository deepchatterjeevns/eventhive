from django.urls import path

from .views import BookTicketView, EventListView, health_check

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path("book/", BookTicketView.as_view(), name="book-ticket"),
    path("health/", health_check, name="health-check"),
]
