"""Crée le bucket de stockage des justificatifs s'il n'existe pas.

Le stockage objet ne crée pas de bucket à la volée : sans cette étape, le
premier dépôt de justificatif échouerait.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Vérifie ou crée le bucket S3/MinIO des justificatifs."

    def handle(self, *args, **options):
        if not settings.AWS_S3_ENDPOINT_URL:
            self.stdout.write(
                "Stockage local : aucun bucket à créer."
            )
            return

        import boto3
        from botocore.exceptions import ClientError

        bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME", "justificatifs")
        client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        )
        try:
            client.head_bucket(Bucket=bucket)
            self.stdout.write(f"Bucket « {bucket} » déjà présent.")
        except ClientError:
            client.create_bucket(Bucket=bucket)
            self.stdout.write(self.style.SUCCESS(f"Bucket « {bucket} » créé."))
