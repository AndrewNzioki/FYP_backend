"""
URL configuration for digitaltwin_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/telemetry/history/", views.get_telemetry_history, name="telemetry-history"),
    path("api/faults/history/", views.get_fault_history, name="fault-history"),
    path("api/commands/request-mode-change/", views.request_mode_change, name="request-mode-change"),
    path("api/commands/request-supply-to-tank/", views.request_supply_to_tank, name="request-supply-to-tank"),
    path("api/commands/request-stop/", views.request_stop, name="request-stop"),
    path("api/commands/enable-manual-override/", views.enable_manual_override, name="enable-manual-override"),
    path("api/commands/disable-manual-override/", views.disable_manual_override, name="disable-manual-override"),
    path("api/commands/system-shutdown/", views.system_shutdown, name="system-shutdown"),
    path("api/commands/set-priority/", views.set_priority, name="set-priority"),
    path("api/commands/modify-constants/", views.modify_constants, name="modify-constants"),
]
