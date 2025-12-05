import os
import sys
sys.path.insert(0, '/root/VV')

os.environ['MODEL_REPO'] = 'hmzh59/vibevoice-models'
os.environ['MODEL_SUBFOLDER'] = 'VibeVoice-1.5B'

import torch
from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

print("Loading processor...")
processor = VibeVoiceProcessor.from_pretrained("hmzh59/vibevoice-models", subfolder="VibeVoice-1.5B")

# Use a voice sample file
voice_file = "/root/voices/Adam.wav"
print(f"Using voice: {voice_file}")

print("\nProcessing text with voice sample...")
text = "Speaker 0: Hello, this is a test of the studio model."

# Process with voice sample
inputs = processor(
    text=text,
    voice_samples=[voice_file],
    padding=True,
    return_tensors="pt",
    return_attention_mask=True,
)

print(f"\nInputs keys: {inputs.keys()}")
for k, v in inputs.items():
    if torch.is_tensor(v):
        print(f"  {k}: tensor shape {v.shape}, dtype {v.dtype}")
    elif v is None:
        print(f"  {k}: None")
    else:
        print(f"  {k}: {type(v).__name__}")

print("\nLoading model...")
model = VibeVoiceForConditionalGenerationInference.from_pretrained(
    "hmzh59/vibevoice-models",
    subfolder="VibeVoice-1.5B",
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    attn_implementation="sdpa"
)
model.eval()

# Move inputs to device
for k, v in inputs.items():
    if torch.is_tensor(v):
        inputs[k] = v.to("cuda")

print("\nGenerating...")
try:
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            cfg_scale=1.5,
            tokenizer=processor.tokenizer,
        )
    print(f"Outputs type: {type(outputs)}")
    if hasattr(outputs, 'speech_outputs') and outputs.speech_outputs:
        audio = outputs.speech_outputs[0]
        print(f"Audio shape: {audio.shape if torch.is_tensor(audio) else 'N/A'}")
        
        # Save audio
        import scipy.io.wavfile as wavfile
        import numpy as np
        
        if torch.is_tensor(audio):
            audio = audio.float().cpu().numpy()  # Convert bfloat16 to float32 first
        if audio.ndim > 1:
            audio = audio.squeeze()
        audio = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio * 32767).astype(np.int16)
        wavfile.write("/root/output_test.wav", 24000, audio_int16)
        print("Saved to /root/output_test.wav")
    else:
        print(f"No speech_outputs found. Outputs: {outputs}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
