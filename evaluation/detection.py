"""Class-specific precision/recall and 101-point interpolated AP on explicit labeled subsets."""
import numpy as np
from perception.tracking import iou_matrix


def class_curve(predictions, truth, class_id, iou_threshold):
    targets = {key: [box["xyxy"] for box in boxes if box["class_id"] == class_id] for key, boxes in truth.items()}
    total = sum(len(boxes) for boxes in targets.values())
    if not total:
        return None
    candidates = [(key, detection) for key, detections in predictions.items() for detection in detections if detection["class_id"] == class_id]
    candidates.sort(key=lambda item: -item[1]["score"])
    matched = {key: set() for key in targets}; tp, fp, scores = [], [], []
    for key, detection in candidates:
        boxes = targets.get(key, [])
        overlaps = iou_matrix([detection["xyxy"]], boxes)[0] if boxes else np.array([])
        choices = [index for index in np.argsort(-overlaps) if index not in matched.get(key, set())]
        valid = bool(choices) and overlaps[choices[0]] >= iou_threshold
        if valid:
            matched[key].add(int(choices[0]))
        tp.append(int(valid)); fp.append(int(not valid)); scores.append(detection["score"])
    cumulative_tp, cumulative_fp = np.cumsum(tp), np.cumsum(fp)
    recall = cumulative_tp / total
    precision = cumulative_tp / np.maximum(1, cumulative_tp + cumulative_fp)
    ap = float(np.mean([max(precision[recall >= threshold], default=0.) for threshold in np.linspace(0, 1, 101)]))
    return {"ap": ap, "total_gt": total, "tp": tp, "fp": fp, "scores": scores}


def evaluate_detections(predictions, truth, class_names, score_threshold=.25):
    results = {}
    for class_id, name in class_names.items():
        curves = [class_curve(predictions, truth, class_id, threshold) for threshold in np.linspace(.5, .95, 10)]
        if curves[0] is None:
            results[name] = {"ground_truth": 0, "ap50": None, "ap50_95": None, "precision_at_score": None, "recall_at_score": None}
            continue
        curve = curves[0]
        selected = [index for index, score in enumerate(curve["scores"]) if score >= score_threshold]
        tp = sum(curve["tp"][index] for index in selected); fp = sum(curve["fp"][index] for index in selected)
        results[name] = {"ground_truth": curve["total_gt"], "tp": tp, "fp": fp, "fn": curve["total_gt"] - tp, "precision_at_score": tp / (tp + fp) if tp + fp else 0.,
                         "recall_at_score": tp / curve["total_gt"], "ap50": curve["ap"], "ap50_95": float(np.mean([value["ap"] for value in curves]))}
    valid = [value for value in results.values() if value["ap50"] is not None]
    return {"classes": results, "subset_map50": float(np.mean([value["ap50"] for value in valid])) if valid else None,
            "subset_map50_95": float(np.mean([value["ap50_95"] for value in valid])) if valid else None, "score_threshold_for_precision_recall": score_threshold,
            "protocol": "101-point interpolated AP; IoU .50:.05:.95; no target crowd instances; class-balanced small subset, not official full COCO mAP"}
