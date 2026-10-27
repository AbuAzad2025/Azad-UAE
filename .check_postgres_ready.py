#!/usr/bin/env python3
"""Check if PostgreSQL is ready to accept connections with authentication."""
import time
import sys
import os

def check_psycopg2():
    """Check using psycopg2 (Python PostgreSQL driver)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            'postgresql://azad_test:azad_test@localhost:5432/azad_test',
            connect_timeout=10
        )
        conn.close()
        return True
    except ImportError:
        return None  # psycopg2 not available
    except Exception:
        return False  # psycopg2 available but connection failed

def check_socket():
    """Check using Python socket connection."""
    import socket
    try:
        s = socket.create_connection(('localhost', 5432), timeout=5)
        s.close()
        return True
    except Exception:
        return False

def check_psql():
    """Check using psql command."""
    import subprocess
    try:
        env = os.environ.copy()
        env['PGPASSWORD'] = 'azad_test'
        result = subprocess.run(
            ['psql', '-h', 'localhost', '-U', 'azad_test', '-d', 'azad_test',
             '-c', 'SELECT 1'],
            env=env,
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False

def main():
    max_attempts = 120  # Increased from 60 for slower CI environments
    attempt = 0

    # Try psycopg2 first (most reliable for authentication check)
    while attempt < max_attempts:
        attempt += 1
        result = check_psycopg2()
        if result is True:
            print('PostgreSQL is ready (attempt', attempt, ')')
            sys.exit(0)
        if result is False:
            # psycopg2 available but connection not yet ready - keep waiting
            print('Waiting for PostgreSQL... (attempt', attempt, '/', max_attempts, ')')
            time.sleep(2)
            continue
        # result is None (ImportError) - fall through to socket check
        break

    # Fall back to socket check if psycopg2 not available
    while attempt < max_attempts:
        attempt += 1
        if check_socket():
            print('PostgreSQL port open (attempt', attempt, ')')
            sys.exit(0)
        print('Waiting for PostgreSQL... (attempt', attempt, '/', max_attempts, ': port closed)')
        time.sleep(2)

    # Fall back to psql command (last resort)
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        if check_psql():
            print('PostgreSQL is ready (attempt', attempt, ')')
            sys.exit(0)
        print('Waiting for PostgreSQL... (attempt', attempt, '/', max_attempts, ': psql check failed)')
        time.sleep(2)

    print('::error::PostgreSQL did not become ready in time after', max_attempts, 'attempts')
    sys.exit(1)

if __name__ == '__main__':
    main()