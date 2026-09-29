from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Film recommender", {"fields": ("display_name", "apple_sub", "can_moderate")}),
    )
    list_display = (
        "display_name",
        "username",
        "email",
        "can_moderate",
        "is_staff",
        "date_joined",
    )
    list_filter = BaseUserAdmin.list_filter + ("can_moderate",)
    search_fields = BaseUserAdmin.search_fields + ("display_name", "apple_sub")
    readonly_fields = ("apple_sub",)
    actions = ["ban_from_moderating", "allow_moderating"]

    @action(description="Ban selected users from editing and voting")
    def ban_from_moderating(self, request, queryset):
        count = queryset.update(can_moderate=False)
        self.message_user(request, f"{count} user(s) banned from moderating.")

    @action(description="Allow selected users to edit and vote again")
    def allow_moderating(self, request, queryset):
        count = queryset.update(can_moderate=True)
        self.message_user(request, f"{count} user(s) can moderate again.")

    readonly_fields = ("last_login", "date_joined")


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
