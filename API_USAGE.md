# Cheap TTS API Examples

This document shows how to use the Cheap TTS API programmatically.

## Your Admin API Key (FREE)

Generate your own personal admin API key for unlimited FREE access:
```
python - <<'PY'
import secrets
print('ctts_' + secrets.token_urlsafe(32))
PY
```
Set it in your environment before running examples:
```
export ADMIN_API_KEY=ctts_...
# Windows: set ADMIN_API_KEY=ctts_...
```

**⚠️ IMPORTANT:** This key gives you free unlimited access. Keep it secret and never commit it to public repositories!

---

## API Endpoints

### 1. Synthesize Text to Speech

**Endpoint:** `POST /api/v1/synthesize`

**Headers:**
```
Content-Type: application/json
X-API-Key: your_api_key_here
```

**Request Body:**
```json
{
  "text": "Hello, this is a test of the text to speech API!",
  "voice": "en-US-AriaNeural",
  "rate": "+0%",
  "volume": "+0%",
  "pitch": "+0Hz"
}
```

**Response:**
```json
{
  "success": true,
  "audio_url": "http://localhost:5000/api/audio/speech_abc123.mp3",
  "filename": "speech_abc123.mp3"
}
```

### 2. List Available Voices

**Endpoint:** `GET /api/v1/voices`

**Headers:** None required (public endpoint)

**Response:**
```json
{
  "success": true,
  "count": 550,
  "voices": [
    {
      "name": "Microsoft Server Speech Text to Speech Voice (en-US, AriaNeural)",
      "short_name": "en-US-AriaNeural",
      "gender": "Female",
      "locale": "en-US",
      "local_name": "Aria"
    },
    ...
  ]
}
```

---

## Code Examples

### Python

```python
import requests
import os

API_KEY = os.environ.get("ADMIN_API_KEY")  # Your admin key from env
BASE_URL = "http://localhost:5000"  # Change to your deployed URL

if not API_KEY:
    raise RuntimeError("Set ADMIN_API_KEY in your environment before calling the API.")

def text_to_speech(text, voice="en-US-AriaNeural"):
    """Convert text to speech and return audio URL"""
    
    response = requests.post(
        f"{BASE_URL}/api/v1/synthesize",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        },
        json={
            "text": text,
            "voice": voice,
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz"
        }
    )
    
    data = response.json()
    
    if data["success"]:
        return data["audio_url"]
    else:
        raise Exception(data.get("error", "Unknown error"))

def download_audio(audio_url, filename="output.mp3"):
    """Download the audio file"""
    response = requests.get(audio_url)
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"Audio saved to {filename}")

# Example usage
if __name__ == "__main__":
    # Generate speech
    audio_url = text_to_speech("Hello! This is a test of the Cheap TTS API.")
    print(f"Audio generated: {audio_url}")
    
    # Download the audio file
    download_audio(audio_url, "my_speech.mp3")
```

### JavaScript/Node.js

```javascript
const API_KEY = process.env.ADMIN_API_KEY;
const BASE_URL = "http://localhost:5000";

if (!API_KEY) {
  throw new Error("Set ADMIN_API_KEY in your environment before calling the API.");
}

async function textToSpeech(text, voice = "en-US-AriaNeural") {
  const response = await fetch(`${BASE_URL}/api/v1/synthesize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({
      text: text,
      voice: voice,
      rate: "+0%",
      volume: "+0%",
      pitch: "+0Hz",
    }),
  });

  const data = await response.json();

  if (data.success) {
    return data.audio_url;
  } else {
    throw new Error(data.error || "Unknown error");
  }
}

// Example usage
textToSpeech("Hello! This is a test of the Cheap TTS API.")
  .then((audioUrl) => {
    console.log("Audio generated:", audioUrl);
  })
  .catch((error) => {
    console.error("Error:", error.message);
  });
```

### cURL

```bash
# Generate speech
curl -X POST http://localhost:5000/api/v1/synthesize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -d '{
    "text": "Hello, this is a test!",
    "voice": "en-US-AriaNeural",
    "rate": "+0%",
    "volume": "+0%",
    "pitch": "+0Hz"
  }'

# List all voices
curl http://localhost:5000/api/v1/voices
```

---

## Voice Parameters

### Rate (Speed)
- Format: `"+X%"` or `"-X%"`
- Range: `-50%` to `+100%`
- Examples: `"-20%"` (slower), `"+0%"` (normal), `"+50%"` (faster)

### Volume
- Format: `"+X%"` or `"-X%"`
- Range: `-50%` to `+50%`
- Examples: `"-20%"` (quieter), `"+0%"` (normal), `"+20%"` (louder)

### Pitch
- Format: `"+XHz"` or `"-XHz"`
- Range: `-200Hz` to `+200Hz`
- Examples: `"-50Hz"` (lower), `"+0Hz"` (normal), `"+50Hz"` (higher)

---

## Popular Voices

### English (US)
- `en-US-AriaNeural` - Female, versatile
- `en-US-JennyNeural` - Female, warm
- `en-US-GuyNeural` - Male, professional
- `en-US-DavisNeural` - Male, conversational

### English (UK)
- `en-GB-SoniaNeural` - Female
- `en-GB-RyanNeural` - Male

### Other Languages
- `es-ES-ElviraNeural` - Spanish (Spain), Female
- `fr-FR-DeniseNeural` - French, Female
- `de-DE-KatjaNeural` - German, Female
- `ja-JP-NanamiNeural` - Japanese, Female

Use `GET /api/v1/voices` to see all 550+ available voices!

---

## Error Handling

All API responses include a `success` field:

**Success:**
```json
{
  "success": true,
  "audio_url": "...",
  "filename": "..."
}
```

**Error:**
```json
{
  "success": false,
  "error": "Error message here"
}
```

Common error codes:
- `401` - Invalid or missing API key
- `400` - Bad request (missing required fields)
- `402` - Subscription required (for non-admin keys)
- `500` - Server error

---

## Using in Your Projects

### For Your Personal Projects (FREE)
Use your admin API key: `$ADMIN_API_KEY`

This key has:
- ✅ Unlimited usage
- ✅ No subscription required
- ✅ Free forever (for your personal use)

### For Other Users
Other users need to:
1. Sign up at your app
2. Subscribe for $4.99/mo
3. Create an API key in the dashboard
4. Use that key in their requests

---

## Security Best Practices

1. **Never commit API keys to git repositories**
2. **Use environment variables** to store your API key
3. **Rotate keys** if they're exposed
4. **Use HTTPS** in production (not HTTP)
5. **Keep your admin key secret** - it's only for you!

---

## Need Help?

- API not working? Check that the server is running: `python -m webapp.app`
- Getting 401 errors? Verify your API key is correct
- Want to change voices? Use `GET /api/v1/voices` to see all options
