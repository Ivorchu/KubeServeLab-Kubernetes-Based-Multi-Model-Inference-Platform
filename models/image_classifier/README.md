# Image Classifier Model

**Status:** Placeholder — fake implementation in `services/worker/app/models.py`

## Planned real implementation

Replace `image_small` in [services/worker/app/models.py](../../services/worker/app/models.py):

```python
# Option A: torchvision ResNet (pretrained)
import torch
from torchvision import models, transforms
from PIL import Image
import base64, io

_model = models.resnet18(pretrained=True).eval()
_transform = transforms.Compose([transforms.Resize(224), transforms.ToTensor()])

def image_small(input: Any) -> Any:
    img = Image.open(io.BytesIO(base64.b64decode(input)))
    tensor = _transform(img).unsqueeze(0)
    with torch.no_grad():
        logits = _model(tensor)
    label_idx = logits.argmax(dim=1).item()
    return {"label_idx": label_idx, "confidence": float(logits.softmax(1).max())}

# Option B: ONNX Runtime (EfficientNet)
```

## Model assets
- `model.onnx` — ONNX export
- `labels.json` — ImageNet label mapping
