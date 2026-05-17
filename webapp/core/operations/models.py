import uuid

from django.db import models


class Operation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED  = "failed",  "Failed"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook    = models.CharField(max_length=256)
    extra_vars  = models.JSONField(default=dict)
    status      = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    stdout      = models.TextField(blank=True)
    stderr      = models.TextField(blank=True)
    return_code = models.IntegerField(null=True, blank=True)
    started_at  = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Operation({self.playbook}, {self.status})"
