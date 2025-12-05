# Studio Model TTS - Future Deployment Guide

## Step 1: Create Vast.ai Instance

1. Go to **vast.ai** and log in
2. Click **Search** to find instances
3. Filter by:
   - GPU: RTX 4080, 4090, or 3090 (16GB+ VRAM)
   - Disk: 30GB+
4. Look for template: **PyTorch 2.x + CUDA 12**
5. **IMPORTANT**: Before renting, click "Edit Image & Config"
   - Under "Ports to open", add: `8070`
6. Click **Rent**

## Step 2: Get Your Static URL

After renting, on your instance card:
1. Click the **Open** button (or the IP address)
2. You'll see something like: `https://xyz123.vast.ai:8070`
3. **Save this URL** - this is your static VIBEVOICE_URL

Or construct it manually:
```
https://<INSTANCE-ID>.vast.ai:8070
```

## Step 3: Connect via SSH

Copy the SSH command from Vast.ai dashboard and run it in PowerShell:

```powershell
ssh -p PORT root@IP_ADDRESS
```

Example:
```powershell
ssh -p 45165 root@171.250.13.44
```

## Step 4: Deploy (ONE Command)

Paste this in the Vast terminal:

```bash
curl -sSL https://raw.githubusercontent.com/Hamza750802/TTS/master/vibevoice-server/deploy.sh | bash
```

Wait ~5 minutes for everything to download.

## Step 5: Start Server

```bash
./start.sh
```

## Step 6: Keep Server Running (Optional)

To keep server running even if you disconnect:

```bash
tmux new -s studio
./start.sh
```

Then press `Ctrl+B` then `D` to detach.

To reconnect later:
```bash
tmux attach -t studio
```

---

## Update Your Webapp

Set this environment variable in your webapp (Railway/Render):

```
VIBEVOICE_URL=https://YOUR-INSTANCE.vast.ai:8070
```

---

## Quick Reference Commands

### Check if server is running:
```bash
curl http://localhost:8070/health
```

### Test audio generation:
```bash
curl -X POST http://localhost:8070/generate -H "Content-Type: application/json" -d '{"text": "Hello world", "voice": "adam"}' -o test.wav
```

### List available voices:
```bash
curl http://localhost:8070/voices
```

### Restart server:
```bash
tmux attach -t studio
# Press Ctrl+C to stop
./start.sh
# Press Ctrl+B then D to detach
```

---

## Adding New Voices

1. Go to: https://huggingface.co/hmzh59/vibevoice-voices
2. Click "Files" → "Upload files"
3. Upload your WAV file (name it like `VoiceName.wav`)
4. Restart server on Vast

---

## Available Voices (24)

**Custom:** Adam, Aloy, Bill, Chris, Dace, Emily, Grace, Hannah, Jennifer, John, Michael, Natalie, Oliva, Sean, Sophia

**Demo:** Alice, Carter, Frank, Mary, Maya, Samuel, Anchen, Bowen, Xinran
