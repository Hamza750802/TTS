import requests
import os

# Try health check first
endpoint_id = os.environ["RUNPOD_ENDPOINT_ID"]
api_key = os.environ["RUNPOD_API_KEY"]

# Check endpoint health
health_url = f'https://api.runpod.ai/v2/{endpoint_id}/health'
headers = {
    'Authorization': f'Bearer {api_key}',
}

print(f'Checking health: {health_url}')
try:
    resp = requests.get(health_url, headers=headers, timeout=10)
    print(f'Health Status: {resp.status_code}')
    print(f'Response: {resp.text}')
except Exception as e:
    print(f'Health Error: {e}')

# Try async (run) instead of runsync to avoid timeout
print('\n--- Trying async job ---')
run_url = f'https://api.runpod.ai/v2/{endpoint_id}/run'
payload = {
    'input': {
        'text': 'Hello world.',
        'voice': 'v2/en_speaker_6'
    }
}
headers['Content-Type'] = 'application/json'

try:
    resp = requests.post(run_url, headers=headers, json=payload, timeout=30)
    print(f'Run Status: {resp.status_code}')
    print(f'Response: {resp.text}')
except Exception as e:
    print(f'Run Error: {e}')
