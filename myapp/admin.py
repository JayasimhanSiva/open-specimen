from django.contrib import admin

from .models import Submission, Typeface

admin.site.site_header = "Open Specimen"
admin.site.site_title = "Open Specimen admin"
admin.site.index_title = "Index and submissions"


@admin.register(Typeface)
class TypefaceAdmin(admin.ModelAdmin):
    list_display = ["name", "designer", "year", "classification", "order"]
    list_filter = ["classification"]
    list_editable = ["order"]
    prepopulated_fields = {"slug": ["name"]}
    search_fields = ["name", "designer"]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["typeface", "designer", "email", "created"]
    search_fields = ["typeface", "designer", "email"]
