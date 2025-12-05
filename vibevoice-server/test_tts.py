import requests

data = {"text": "Hello, this is a test of the studio model.", "voice": "adam"}
response = requests.post("http://localhost:8070/generate", json=data)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    with open("/root/test.wav", "wb") as f:
        f.write(response.content)
    print(f"Saved {len(response.content)} bytes to test.wav")
else:
    print(f"Error: {response.text}")
