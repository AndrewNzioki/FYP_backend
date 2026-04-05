from django.contrib import admin
from .models import SystemState, TankState, Command, TelemetryLog, FaultLog, SystemConfig


class TankStateInline(admin.TabularInline):
    model = TankState
    extra = 0
    readonly_fields = ('tank_id', 'level_percent', 'status', 'valve_actual')
    can_delete = False

    def has_add_permission(self, request, obj):
        return False  # Tanks should only be created by incoming telemetry


@admin.register(SystemState)
class SystemStateAdmin(admin.ModelAdmin):
    list_display = ('id', 'mode', 'source_level_percent', 'source_fault', 'pump_actual', 'updated_at')
    readonly_fields = ('mode', 'source_level_percent', 'source_fault', 'pump_actual', 'updated_at')
    inlines = [TankStateInline]

    def has_add_permission(self, request):
        return False  # There should only ever be ONE SystemState row (ID 1)


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ('id', 'command_type', 'issued_by', 'status', 'mqtt_published', 'created_at')
    list_filter = ('status', 'command_type', 'mqtt_published')
    search_fields = ('command_type', 'issued_by')
    # Matches the restored model perfectly
    readonly_fields = ('mqtt_topic', 'mqtt_qos', 'mqtt_published', 'mqtt_published_at', 'mqtt_publish_attempts', 'mqtt_last_error', 'created_at')


@admin.register(TelemetryLog)
class TelemetryLogAdmin(admin.ModelAdmin):
    list_display = ('ts', 'mode', 'source_level_percent', 'pump_actual')
    list_filter = ('mode', 'pump_actual')
    search_fields = ('ts',)

    # 🚨 FORENSIC LOCKDOWN 🚨
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # Never delete history manually


@admin.register(FaultLog)
class FaultLogAdmin(admin.ModelAdmin):
    list_display = ('ts', 'fault_type', 'detected_by')
    list_filter = ('detected_by', 'fault_type')
    search_fields = ('fault_type',)

    # 🚨 FORENSIC LOCKDOWN 🚨
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'value', 'updated_at')
    search_fields = ('name',)
    list_editable = ('value',)  # Quick edits for things like Hysteresis constants