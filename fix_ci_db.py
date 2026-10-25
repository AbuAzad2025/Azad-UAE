import yaml
import sys

with open('.github/workflows/ci.yml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

jobs = data.get('jobs', {})

# Fix verify-boot env - add AUTO_MIGRATE
verify_job = data['jobs'].get('verify-boot', {})
if 'env' in verify_job:
    verify_job['env']['AUTO_MIGRATE'] = '1'

# Fix verify-boot steps - add database creation after wait
verify_job = data['jobs'].get('verify-boot', {})
if 'steps' in verify_job:
    steps = verify_job['steps']
    for i, step in enumerate(steps):
        if step.get('name') == 'Wait for PostgreSQL to be ready':
            steps.insert(i+1, {
                'name': 'Ensure database exists',
                'run': '# Ensure database exists (POSTGRES_DB should create it, but just in case)\nPGPASSWORD=azad_test psql -h localhost -U azad_test -d postgres -c "SELECT 1 FROM pg_database WHERE datname = \'azad_test\'" | grep -q 1 || PGPASSWORD=azad_test psql -h localhost -U azad_test -d postgres -c "CREATE DATABASE azad_test;"',
                'name': 'Ensure database exists'
            })
            break

# Fix test job - add explicit database creation step
test_job = data['jobs'].get('test', {})
if 'steps' in test_job:
    steps = test_job['steps']
    for i, step in enumerate(steps):
        if step.get('name') == 'Wait for PostgreSQL to be ready':
            steps.insert(i+1, {
                'name': 'Ensure database exists',
                'run': '# Ensure database exists (POSTGRES_DB should create it, but just in case)\nPGPASSWORD=azad_test psql -h localhost -U azad_test -d postgres -c "SELECT 1 FROM pg_database WHERE datname = \'azad_test\'" | grep -q 1 || PGPASSWORD=azad_test psql -h localhost -U azad_test -d postgres -c "CREATE DATABASE azad_test;"',
                'name': 'Ensure database exists'
            })
            break

# Fix verify-boot env - add AUTO_MIGRATE
verify_job = data['jobs'].get('verify-boot', {})
if 'env' in verify_job:
    verify_job['env']['AUTO_MIGRATE'] = '1'

print('Modified')
with open('.github/workflows/ci.yml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2, width=1000)

print('Done')