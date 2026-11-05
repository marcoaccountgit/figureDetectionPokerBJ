"""Validate training with the same single-label decisions as deployment."""
from copy import copy
import numpy as np
import torch
from ultralytics.models.yolo.detect.train import DetectionTrainer
from ultralytics.models.yolo.detect.val import DetectionValidator
from ultralytics.utils import nms


class DeploymentValidator(DetectionValidator):
    def postprocess(self, predictions):
        raw = predictions[0] if isinstance(predictions, (tuple, list)) else predictions
        raw = raw.clone()
        scores = raw[:, 4:4+self.nc]
        top = scores.topk(2, dim=1).values
        ambiguous = (top[:, 0]-top[:, 1]) < .15
        raw[:, 4:4+self.nc] = scores.masked_fill(ambiguous.unsqueeze(1), 0)
        outputs = nms.non_max_suppression(raw, .60, .45, nc=self.nc,
                                          multi_label=False, agnostic=True, max_det=100)
        return [{'bboxes': x[:, :4], 'conf': x[:, 4], 'cls': x[:, 5], 'extra': x[:, 6:]} for x in outputs]

    def get_stats(self):
        stats = self.metrics.stats
        true_positive = int(np.concatenate(stats['tp'])[:, 0].sum())
        predicted = len(np.concatenate(stats['conf']))
        targets = len(np.concatenate(stats['target_cls']))
        precision = true_positive / predicted if predicted else 0
        recall = true_positive / targets if targets else 0
        f1 = 2*true_positive/(predicted+targets) if predicted+targets else 0
        result = super().get_stats()
        result.update({'deployment/precision': precision, 'deployment/recall': recall,
                       'deployment/f1': f1, 'fitness': f1})
        return result


class DeploymentTrainer(DetectionTrainer):
    def build_dataset(self, img_path, mode='train', batch=None):
        dataset = super().build_dataset(img_path, mode, batch)
        if mode == 'val':
            dataset.rect = False
            dataset.transforms = dataset.build_transforms(hyp=self.args)
        return dataset

    def get_validator(self):
        self.loss_names = 'box_loss', 'cls_loss', 'dfl_loss'
        return DeploymentValidator(self.test_loader, save_dir=self.save_dir,
                                   args=copy(self.args), _callbacks=self.callbacks)
