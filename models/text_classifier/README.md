# Text Classifier Model

**Status:** Placeholder — fake implementation in `services/worker/app/models.py`

## Planned real implementation

Replace `text_small` and `text_large` in [services/worker/app/models.py](../../services/worker/app/models.py) with actual model loading:

```python
# Option A: HuggingFace transformers (DistilBERT sentiment)
from transformers import pipeline
_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

def text_small(input: Any) -> Any:
    result = _pipeline(str(input)[:512])[0]
    return {"label": result["label"].lower(), "confidence": round(result["score"], 4)}

# Option B: ONNX Runtime (faster, lower memory)
import onnxruntime as ort
# ... load model.onnx and run inference
```

## Model assets
Place model files here and update the worker config to reference the path.
- `model.onnx` — quantized ONNX export
- `tokenizer/` — tokenizer files
