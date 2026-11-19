
  INSTALL httpfs;
  LOAD httpfs;
  CREATE OR REPLACE SECRET minio_s3 (
    TYPE S3,
    KEY_ID 'ghsignal',
    SECRET 'ghsignal_dev_password',
    REGION 'us-east-1',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false
  );
