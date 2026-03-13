#!/bin/bash
set -e

echo "=== LeidsaOracle API Starting ==="

# Wait for PostgreSQL to be ready
echo "Waiting for database..."
python -c "
import asyncio
import asyncpg
import os
import time

async def wait():
    url = os.environ.get('DATABASE_URL', '').replace('+asyncpg', '')
    # Convert SQLAlchemy URL to asyncpg format
    url = url.replace('postgresql://', 'postgresql://')
    for i in range(30):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print('Database is ready!')
            return
        except Exception as e:
            print(f'Attempt {i+1}/30: {e}')
            time.sleep(2)
    raise RuntimeError('Database not available after 60 seconds')

asyncio.run(wait())
"

# Run database migrations
echo "Running migrations..."
alembic upgrade head

# Start the API server
echo "Starting FastAPI server on port 8000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level info
