import redis
from django.conf import settings

def get_redis_client():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)