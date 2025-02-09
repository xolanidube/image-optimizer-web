#!/usr/bin/env python3
import os
import redis
from rq import Worker, Queue, connections

listen = ['default']

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with connections(conn):
        worker = Worker(list(map(Queue, listen)))
        worker.work()
