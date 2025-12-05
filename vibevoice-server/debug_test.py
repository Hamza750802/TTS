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
print(f"Processor type: {type(processor)}")
print(f"Processor attributes: {dir(processor)}")

print("\nProcessing text...")
text = "Speaker 0: Hello, this is a test."
inputs = processor(
    text=text,
    padding=True,
    return_tensors="pt",
    return_attention_mask=True,
)

print(f"\nInputs type: {type(inputs)}")
print(f"Inputs keys: {inputs.keys() if hasattr(inputs, 'keys') else 'N/A'}")
for k, v in inputs.items():
    if torch.is_tensor(v):
        print(f"  {k}: tensor shape {v.shape}, dtype {v.dtype}")
    else:
        print(f"  {k}: {type(v)} = {v}")

print("\nLoading model...")
model = VibeVoiceForConditionalGenerationInference.from_pretrained(
    "hmzh59/vibevoice-models",
    subfolder="VibeVoice-1.5B",
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    attn_implementation="sdpa"
)
model.eval()
print(f"Model type: {type(model)}")
print(f"Has generate: {hasattr(model, 'generate')}")

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
    print(f"Outputs attributes: {dir(outputs)}")
    if hasattr(outputs, 'speech_outputs'):
        print(f"speech_outputs: {outputs.speech_outputs}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
