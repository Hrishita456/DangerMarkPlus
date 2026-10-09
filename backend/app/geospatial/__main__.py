"""Run the configured scenario locally using the same service as the API."""
import json
from app.services.consequences import config, create_run, read_run

if __name__ == '__main__':
    result = create_run(config().scenario_id)
    print(json.dumps({'run': result, 'summary': read_run(result['run_id'], 'summary')}, indent=2))
