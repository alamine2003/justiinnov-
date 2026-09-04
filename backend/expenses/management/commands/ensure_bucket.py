"""Crée le bucket de stockage des justificatifs s'il n'existe pas.

Le stockage objet ne crée pas de bucket à la volée : sans cette étape, le
premier dépôt de justificatif échouerait.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Vérifie ou crée le bucket S3/MinIO des justificatifs."

    def handle(self, *args, **options):
        if not settings.AWS_S3_ENDPOINT_URL:
            self.stdout.write(
                "Stockage local : aucun bucket à créer."
            )
            return

        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME", "justificatifs")
        client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        )
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            # Toute erreur était lue comme « le bucket n'existe pas », et la
            # commande enchaînait sur une création qui échouait à son tour
            # avec une trace boto illisible. Des identifiants faux ou un
            # accès refusé ne se règlent pas en créant un bucket : ils
            # doivent être nommés, et faire échouer le démarrage.
            code = str(exc.response.get("Error", {}).get("Code", ""))
            statut = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in ("404", "NoSuchBucket") or statut == 404:
                self._creer(client, bucket, ClientError, BotoCoreError)
                return
            if code in ("403", "AccessDenied", "InvalidAccessKeyId",
                        "SignatureDoesNotMatch") or statut == 403:
                raise CommandError(
                    f"Accès refusé au bucket « {bucket} » ({code}) : vérifiez "
                    "AWS_ACCESS_KEY_ID et AWS_SECRET_ACCESS_KEY."
                ) from exc
            raise CommandError(
                f"Stockage injoignable pour le bucket « {bucket} » : {exc}"
            ) from exc
        except BotoCoreError as exc:
            raise CommandError(
                f"Stockage injoignable ({settings.AWS_S3_ENDPOINT_URL}) : {exc}"
            ) from exc
        self.stdout.write(f"Bucket « {bucket} » déjà présent.")

    def _creer(self, client, bucket, ClientError, BotoCoreError):
        try:
            client.create_bucket(Bucket=bucket)
        except (ClientError, BotoCoreError) as exc:
            raise CommandError(
                f"Impossible de créer le bucket « {bucket} » : {exc}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Bucket « {bucket} » créé."))
