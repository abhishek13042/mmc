# HuggingFace free Inference API tokens.
# Get yours free at: https://huggingface.co/settings/tokens  (read-only token is enough)
# Create multiple free HF accounts to get multiple tokens — the tool rotates them
# automatically when one hits a rate limit.
HF_TOKENS = [
    "hf_REPLACE_WITH_YOUR_TOKEN_1",
    # "hf_REPLACE_WITH_YOUR_TOKEN_2",
    # "hf_REPLACE_WITH_YOUR_TOKEN_3",
]

# Whisper large-v3 = best quality.  Switch to whisper-medium if large-v3 queue is long.
MODEL_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
FALLBACK_MODEL_URL = "https://api-inference.huggingface.co/models/openai/whisper-medium"

# Each audio chunk sent to the API (seconds).  30s FLAC ~ 300 KB — well under the 25 MB limit.
CHUNK_SECONDS = 30
