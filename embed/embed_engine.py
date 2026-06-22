from pathlib import Path
import torch
import numpy as np
from embed.osnet import osnet_x0_25


class embed:

    def __init__(self):

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # -------------------------
        # Model (architecture only)
        # -------------------------
        self.model = osnet_x0_25()

        # -------------------------
        # LOCAL WEIGHT RESOLUTION (LIKE DETECTION)
        # -------------------------
        MODEL_PATH = Path(__file__).parent / "osnet_x0_25_msmt17.pth"

        checkpoint = torch.load(MODEL_PATH, map_location=self.device)

        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        model_dict = self.model.state_dict()

        filtered = {}

        for k, v in state_dict.items():
            k = k.replace("module.", "")

            if "classifier" in k:
                continue

            if k in model_dict and model_dict[k].shape == v.shape:
                filtered[k] = v

        model_dict.update(filtered)
        self.model.load_state_dict(model_dict, strict=False)

        self.model.to(self.device)
        self.model.eval()

    def embed(self, detection: dict):

        img = detection["image"]

        if img is None:
            raise ValueError("Empty image in detection")

        x = torch.from_numpy(img)
        x = x.permute(2, 0, 1).unsqueeze(0).float().to(self.device)

        with torch.inference_mode():
            feat = self.model(x)

        vec = feat.squeeze(0).cpu().numpy()

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return {
            "detection_id": detection["detection_id"],
            "embedding": vec
        }