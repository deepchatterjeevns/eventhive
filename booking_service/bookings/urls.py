from django.urls import path
from .views import EventListView, BookTicketView

urlpatterns = [
    path('events/', EventListView.as_view(), name='event-list'),
    path('book/', BookTicketView.as_view(), name='book-ticket'),
]