import yaml
import boto3


def get_config():
    with open("config.yml") as f:
        config = yaml.load(f.read())
    return config


def get_db_client():
    return boto3.resource("dynamodb")
