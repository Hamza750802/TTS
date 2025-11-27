# Voice & Emotion Availability Guide

## Summary

**Total Voices with Emotion Support: 47**
- Female: 27 voices
- Male: 20 voices

**Emotion Range per Voice: 1-14 styles**

## Most Common Emotions (Available in 5+ voices)

| Emotion | Available in # Voices | Use Cases |
|---------|----------------------|-----------|
| **cheerful** | 31 voices | Happy announcements, greetings, celebrations |
| **sad** | 27 voices | Emotional stories, empathy, condolences |
| **angry** | 22 voices | Confrontations, frustration, intensity |
| **excited** | 14 voices | Product launches, enthusiasm, energy |
| **fearful** | 12 voices | Suspense, concern, anxiety |
| **friendly** | 12 voices | Casual conversation, approachable tone |
| **serious** | 12 voices | Business, news, formal announcements |
| **chat** | 11 voices | Conversational, informal dialogue |
| **whispering** | 10 voices | Secrets, intimacy, ASMR |
| **disgruntled** | 10 voices | Complaints, dissatisfaction |

## Multi-Speaker Dialogue Capabilities

### ✅ What Works
- **Different voices per speaker**: Mix any combination of the 47 emotion-capable voices
- **Different emotions per speaker**: Each speaker can use emotions from their own emotion set
- **Single audio output**: All speakers combined in one MP3 file
- **Natural transitions**: Seamless voice switching

### ⚠️ Important Limitations
1. **Emotions are voice-specific**: Not all voices support all emotions
2. **Check compatibility**: Each voice has its own emotion list (1-14 styles)
3. **Prosody disabled in multi-speaker**: Rate/pitch/volume controls are disabled when using multiple voices (compatibility requirement)

## Example Voice Capabilities

### High Versatility (10+ emotions)
- **en-US-JennyNeural** (14 emotions): assistant, chat, customerservice, newscast, angry, cheerful, sad, excited, friendly, terrified, shouting, unfriendly, whispering, hopeful
- **en-US-GuyNeural** (11 emotions): newscast, angry, cheerful, sad, excited, friendly, terrified, shouting, hopeful, unfriendly, whispering
- **en-US-DavisNeural** (11 emotions): chat, angry, cheerful, excited, friendly, hopeful, sad, shouting, terrified, unfriendly, whispering

### Medium Versatility (3-9 emotions)
- **en-US-AriaNeural** (8 emotions): chat, cheerful, empathetic, excited, friendly, hopeful, sad, unfriendly
- **en-US-SaraNeural** (7 emotions): angry, cheerful, excited, friendly, hopeful, sad, whispering

### Limited Versatility (1-2 emotions)
- **de-DE-ConradNeural** (1 emotion): cheerful
- **en-GB-RyanNeural** (2 emotions): cheerful, chat

## Best Practices for Multi-Speaker Dialogue

### Strategy 1: Match Common Emotions
Pick voices that share the emotions you need:
```
Jenny (cheerful, sad, friendly) + Guy (cheerful, sad, friendly) = Full compatibility
```

### Strategy 2: Use Most Common Emotions
Stick to emotions available in 20+ voices:
- cheerful, sad, angry, excited, friendly

### Strategy 3: Per-Character Emotional Range
Each character uses only their available emotions:
```
Speaker A (Jenny): cheerful, friendly, excited
Speaker B (Guy): serious, angry, hopeful
```

## API Usage

### Check Available Emotions
```bash
curl -H "X-API-Key: YOUR_KEY" https://cheaptts.com/api/voices
```

Response includes `styles` array for each voice.

### Multi-Speaker Request
```json
{
  "chunks": [
    {
      "content": "Hello!",
      "voice": "en-US-JennyNeural",
      "emotion": "cheerful"
    },
    {
      "content": "Hi there!",
      "voice": "en-US-GuyNeural",
      "emotion": "friendly"
    }
  ]
}
```

## Validation

The system automatically validates emotions:
- If an emotion is not supported by the selected voice, it's removed
- A warning is returned in the response
- Audio still generates with neutral tone for that chunk

## Questions?

Check the dashboard to see real-time emotion availability for each voice!
