"""S3-compatible storage client. Works against MinIO locally, AWS in prod."""

import boto3
from botocore.config import Config as BotoConfig
from src.config import Config


def get_s3_client(config: Config):
    return boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint,
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
        region_name=config.s3_region,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 5}),
    )


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except client.exceptions.ClientError:
        return False
