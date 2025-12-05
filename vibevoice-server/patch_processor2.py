#!/usr/bin/env python3
"""
Rewrite vibevoice_processor.py with subfolder support
"""

PROCESSOR_FILE = "/root/vibevoice-server/vibevoice/processor/vibevoice_processor.py"

# Read the original file  
with open(PROCESSOR_FILE + ".bak", 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # After the imports in from_pretrained, add subfolder extraction
    if '# Try to load from local path first' in line:
        # Insert subfolder handling before this line
        new_lines.append('        # Extract subfolder for HuggingFace repos with models in subfolders\n')
        new_lines.append('        subfolder = kwargs.pop("subfolder", None)\n')
        new_lines.append('        cached_file_kwargs = dict(kwargs)\n')
        new_lines.append('        if subfolder:\n')
        new_lines.append('            cached_file_kwargs["subfolder"] = subfolder\n')
        new_lines.append('\n')
    
    # Fix config_path to handle subfolder
    if 'config_path = os.path.join(pretrained_model_name_or_path, "preprocessor_config.json")' in line:
        new_lines.append('        if subfolder:\n')
        new_lines.append('            config_path = os.path.join(pretrained_model_name_or_path, subfolder, "preprocessor_config.json")\n')
        new_lines.append('        else:\n')
        new_lines.append('            config_path = os.path.join(pretrained_model_name_or_path, "preprocessor_config.json")\n')
        i += 1
        continue
    
    # Fix cached_file call to use cached_file_kwargs
    if '**kwargs' in line and 'cached_file' in lines[i-3] if i >= 3 else False:
        new_lines.append(line.replace('**kwargs', '**cached_file_kwargs'))
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

# Write the new file
with open(PROCESSOR_FILE, 'w') as f:
    f.writelines(new_lines)

print("SUCCESS: Patched vibevoice_processor.py with subfolder support")

# Verify
with open(PROCESSOR_FILE, 'r') as f:
    content = f.read()
    
if 'subfolder = kwargs.pop' in content:
    print("VERIFIED: subfolder extraction code found")
else:
    print("WARNING: subfolder code not found - may need manual fix")
