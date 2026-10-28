from django.contrib import admin
from .models import Event, Ticket, Booking

admin.site.register(Event)
admin.site.register(Ticket)
admin.site.register(Booking)