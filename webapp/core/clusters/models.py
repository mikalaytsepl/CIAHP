from django.db import models


class Cluster(models.Model):
    name         = models.CharField(max_length=128, unique=True)
    cluster_cidr = models.CharField(max_length=64, default="192.168.0.0/16")
    vip_address  = models.GenericIPAddressField(null=True, blank=True)
    kube_version = models.CharField(max_length=16, default="1.35")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Node(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        WORKER  = "worker",  "Worker"

    class Status(models.TextChoices):
        DEPLOYING = "deploying", "Deploying"
        HEALTHY   = "healthy",   "Healthy"
        ERROR     = "error",     "Error"

    cluster    = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name="nodes")
    name       = models.CharField(max_length=128)
    ip         = models.GenericIPAddressField()
    role       = models.CharField(max_length=16, choices=Role.choices, db_index=True)
    status     = models.CharField(max_length=16, choices=Status.choices, default=Status.DEPLOYING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cluster", "name")
        ordering = ["role", "name"]

    def __str__(self):
        return f"{self.cluster.name}/{self.role}/{self.name}"
