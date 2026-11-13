import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_raw_bucket: str
    s3_region: str
    metadata_db_url: str
    gharchive_base_url: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            s3_endpoint=os.environ["S3_ENDPOINT"],
            s3_access_key=os.environ["S3_ACCESS_KEY"],
            s3_secret_key=os.environ["S3_SECRET_KEY"],
            s3_raw_bucket=os.environ["S3_RAW_BUCKET"],
            s3_region=os.environ.get("S3_REGION", "us-east-1"),
            metadata_db_url=os.environ["METADATA_DB_URL"],
            gharchive_base_url=os.environ.get(
                "GHARCHIVE_BASE_URL", "https://data.gharchive.org"
            ),
        )
