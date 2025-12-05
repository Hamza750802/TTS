#!/usr/bin/env python3
"""
Patch the vibevoice_processor.py to properly handle subfolder kwarg
"""

import os

PROCESSOR_FILE = "/root/vibevoice-server/vibevoice/processor/vibevoice_processor.py"

# Read the file
with open(PROCESSOR_FILE, 'r') as f:
    content = f.read()

# The fix: Extract subfolder from kwargs before passing to tokenizer
old_code = '''    @classmethod
    def from_pretrained(cls, pretrained_model_name_or_path, **kwargs):
        """
        Instantiate a VibeVoiceProcessor from a pretrained VibeVoice processor.

        Args:
            pretrained_model_name_or_path (`str` or `os.PathLike`):
                This can be either:
                - a string, the *model id* of a pretrained model
                - a path to a *directory* containing processor config

        Returns:
            [`VibeVoiceProcessor`]: The processor object instantiated from pretrained model.
        """
        import os
        import json
        from transformers.utils import cached_file
        from .vibevoice_tokenizer_processor import VibeVoiceTokenizerProcessor
        from vibevoice.modular.modular_vibevoice_text_tokenizer import (
            VibeVoiceTextTokenizer,
            VibeVoiceTextTokenizerFast
        )

        # Try to load from local path first, then from HF hub
        config_path = os.path.join(pretrained_model_name_or_path, "preprocessor_config.json")
        config = None

        if os.path.exists(config_path):
            # Local path exists
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            # Try to load from HF hub
            try:
                config_file = cached_file(
                    pretrained_model_name_or_path,
                    "preprocessor_config.json",
                    **kwargs
                )'''

new_code = '''    @classmethod
    def from_pretrained(cls, pretrained_model_name_or_path, **kwargs):
        """
        Instantiate a VibeVoiceProcessor from a pretrained VibeVoice processor.

        Args:
            pretrained_model_name_or_path (`str` or `os.PathLike`):
                This can be either:
                - a string, the *model id* of a pretrained model
                - a path to a *directory* containing processor config

        Returns:
            [`VibeVoiceProcessor`]: The processor object instantiated from pretrained model.
        """
        import os
        import json
        from transformers.utils import cached_file
        from .vibevoice_tokenizer_processor import VibeVoiceTokenizerProcessor
        from vibevoice.modular.modular_vibevoice_text_tokenizer import (
            VibeVoiceTextTokenizer,
            VibeVoiceTextTokenizerFast
        )

        # Extract subfolder - this is for HuggingFace repos with models in subfolders
        subfolder = kwargs.pop("subfolder", None)
        
        # Build kwargs for cached_file
        cached_file_kwargs = dict(kwargs)
        if subfolder:
            cached_file_kwargs["subfolder"] = subfolder

        # Try to load from local path first, then from HF hub
        if subfolder:
            config_path = os.path.join(pretrained_model_name_or_path, subfolder, "preprocessor_config.json")
        else:
            config_path = os.path.join(pretrained_model_name_or_path, "preprocessor_config.json")
        config = None

        if os.path.exists(config_path):
            # Local path exists
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            # Try to load from HF hub
            try:
                config_file = cached_file(
                    pretrained_model_name_or_path,
                    "preprocessor_config.json",
                    **cached_file_kwargs
                )'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(PROCESSOR_FILE, 'w') as f:
        f.write(content)
    print("SUCCESS: Patched vibevoice_processor.py")
else:
    print("ERROR: Could not find the code to patch. File may have different content.")
    print("\nLooking for the from_pretrained method...")
    if "def from_pretrained" in content:
        print("Found from_pretrained method in file.")
    else:
        print("from_pretrained method NOT found!")
