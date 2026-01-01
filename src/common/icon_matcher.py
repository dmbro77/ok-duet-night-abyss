import cv2
import numpy as np
from typing import Sequence, Tuple, Optional, Iterable, Any, Dict

from ok import Box, Logger


logger = Logger.get_logger(__name__)


def _ensure_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _compute_hist_similarity(template_hsv: np.ndarray, patch_hsv: np.ndarray) -> float:
    h_bins = 32
    s_bins = 32
    v_bins = 32
    hist_template_h = cv2.calcHist([template_hsv], [0], None, [h_bins], [0, 180])
    hist_template_s = cv2.calcHist([template_hsv], [1], None, [s_bins], [0, 256])
    hist_template_v = cv2.calcHist([template_hsv], [2], None, [v_bins], [0, 256])
    hist_patch_h = cv2.calcHist([patch_hsv], [0], None, [h_bins], [0, 180])
    hist_patch_s = cv2.calcHist([patch_hsv], [1], None, [s_bins], [0, 256])
    hist_patch_v = cv2.calcHist([patch_hsv], [2], None, [v_bins], [0, 256])
    cv2.normalize(hist_template_h, hist_template_h)
    cv2.normalize(hist_template_s, hist_template_s)
    cv2.normalize(hist_template_v, hist_template_v)
    cv2.normalize(hist_patch_h, hist_patch_h)
    cv2.normalize(hist_patch_s, hist_patch_s)
    cv2.normalize(hist_patch_v, hist_patch_v)
    score_h = cv2.compareHist(hist_template_h, hist_patch_h, cv2.HISTCMP_CORREL)
    score_s = cv2.compareHist(hist_template_s, hist_patch_s, cv2.HISTCMP_CORREL)
    score_v = cv2.compareHist(hist_template_v, hist_patch_v, cv2.HISTCMP_CORREL)
    score = float((score_h + score_s + score_v) / 3.0)
    return max(0.0, min(1.0, score))


def _compute_edge_similarity(template_gray: np.ndarray, patch_gray: np.ndarray) -> float:
    template_edges = cv2.Canny(template_gray, 50, 150)
    patch_edges = cv2.Canny(patch_gray, 50, 150)
    result = cv2.matchTemplate(patch_edges, template_edges, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def _create_box(x: int, y: int, w: int, h: int, name: Optional[str]) -> Box:
    try:
        return Box(x=x, y=y, width=w, height=h, name=name)
    except TypeError:
        try:
            return Box(x, y, w, h, name)
        except TypeError:
            return Box(x, y, w, h)


def _normalize_templates(
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]]
) -> Iterable[Tuple[str, np.ndarray, Dict[str, Any]]]:
    for name, template, params in icon_templates:
        if params is None:
            params = {}
        yield str(name), template, dict(params)


def _create_red_mask_from_hsv(hsv: np.ndarray) -> np.ndarray:
    lower1 = np.array([0, 80, 80], dtype=np.uint8)
    upper1 = np.array([10, 255, 255], dtype=np.uint8)
    lower2 = np.array([170, 80, 80], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def match_icon_in_screenshot(
    box: Box,
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]],
    frame_bgr: np.ndarray,
    scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2),
    max_candidates_per_scale: int = 5,
) -> Tuple[Optional[Box], Optional[str], float]:
    if not icon_templates:
        return None, None, 0.0
    templates_seq = list(_normalize_templates(icon_templates))
    if not templates_seq:
        return None, None, 0.0
    frame_bgr = _ensure_bgr(frame_bgr)
    screenshot_bgr = box.crop_frame(frame_bgr)
    if screenshot_bgr is None or screenshot_bgr.size == 0:
        return None, None, 0.0
    screenshot_bgr = _ensure_bgr(screenshot_bgr)
    screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    screenshot_hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
    screenshot_red_mask = None
    logger.debug(
        f"图标匹配开始 模板数量={len(templates_seq)} "
        f"截图尺寸={tuple(screenshot_bgr.shape)} "
        f"缩放比例={tuple(scales)} "
    )
    for index, (name, template, params) in enumerate(templates_seq):
        template_mode = str(params.get("mode", "default"))
        template_gray_threshold = float(params.get("gray_threshold", 0.7))
        template_color_threshold = float(params.get("color_threshold", 0.6))
        logger.debug(
            f"开始匹配模板 序号={index} 名称={name} "
            f"模式={template_mode} 灰度阈值={template_gray_threshold} 颜色阈值={template_color_threshold}"
        )
        template_bgr = _ensure_bgr(template)
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        template_hsv = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)
        th, tw = template_gray.shape[:2]
        best_box_for_template: Optional[Box] = None
        best_score_for_template: float = 0.0
        if template_mode == "vector_red":
            effective_gray_threshold = template_gray_threshold * 0.8
            use_color_gate = False
            template_red_mask = _create_red_mask_from_hsv(template_hsv)
            if screenshot_red_mask is None:
                screenshot_red_mask = _create_red_mask_from_hsv(screenshot_hsv)
        else:
            effective_gray_threshold = template_gray_threshold
            use_color_gate = True
            template_red_mask = None
        for scale in scales:
            if scale <= 0:
                continue
            scaled_tw = int(tw * scale)
            scaled_th = int(th * scale)
            if scaled_tw < 4 or scaled_th < 4:
                continue
            if scaled_tw > screenshot_gray.shape[1] or scaled_th > screenshot_gray.shape[0]:
                continue
            scaled_template_gray = cv2.resize(
                template_gray, (scaled_tw, scaled_th), interpolation=cv2.INTER_LINEAR
            )
            scaled_template_hsv = cv2.resize(
                template_hsv, (scaled_tw, scaled_th), interpolation=cv2.INTER_LINEAR
            )
            result = cv2.matchTemplate(screenshot_gray, scaled_template_gray, cv2.TM_CCOEFF_NORMED)
            flat_red = None
            if template_mode == "vector_red":
                scaled_template_red_mask = cv2.resize(
                    template_red_mask,
                    (scaled_tw, scaled_th),
                    interpolation=cv2.INTER_NEAREST,
                )
                result_red = cv2.matchTemplate(
                    screenshot_red_mask, scaled_template_red_mask, cv2.TM_CCOEFF_NORMED
                )
            else:
                result_red = None
            if result.size == 0:
                continue
            flat = result.ravel()
            if result_red is not None:
                flat_red = result_red.ravel()
            if max_candidates_per_scale <= 0:
                if flat_red is not None:
                    combined_flat = flat + flat_red
                    indices = np.argmax(combined_flat)[None]
                else:
                    indices = np.argmax(flat)[None]
            else:
                k = min(max_candidates_per_scale, flat.size)
                if flat_red is not None:
                    combined_flat = flat + flat_red
                    indices = np.argpartition(combined_flat, -k)[-k:]
                else:
                    indices = np.argpartition(flat, -k)[-k:]
            for idx in indices:
                similarity_gray = float(flat[idx])
                if similarity_gray < effective_gray_threshold:
                    continue
                y = int(idx // result.shape[1])
                x = int(idx % result.shape[1])
                global_x = box.x + x
                global_y = box.y + y
                y2 = y + scaled_th
                x2 = x + scaled_tw
                if y2 > screenshot_bgr.shape[0] or x2 > screenshot_bgr.shape[1]:
                    continue
                patch_bgr = screenshot_bgr[y:y2, x:x2]
                patch_gray = screenshot_gray[y:y2, x:x2]
                patch_hsv = screenshot_hsv[y:y2, x:x2]
                color_score = _compute_hist_similarity(scaled_template_hsv, patch_hsv)
                if use_color_gate and color_score < template_color_threshold:
                    continue
                edge_score = _compute_edge_similarity(scaled_template_gray, patch_gray)
                if template_mode == "vector_red":
                    mask_score = float(flat_red[idx])
                    combined_score = (
                        0.15 * similarity_gray
                        + 0.15 * color_score
                        + 0.35 * edge_score
                        + 0.35 * mask_score
                    )
                else:
                    combined_score = (
                        0.5 * similarity_gray + 0.3 * color_score + 0.2 * edge_score
                    )
                if combined_score > best_score_for_template:
                    if template_mode == "vector_red":
                        logger.debug(
                            f"候选更新 模板={name} 综合得分={combined_score:.4f} "
                            f"灰度={similarity_gray:.4f} 颜色={color_score:.4f} 边缘={edge_score:.4f} "
                            f"红色掩码={mask_score:.4f} "
                            f"x={global_x} y={global_y} w={scaled_tw} h={scaled_th}"
                        )
                    else:
                        logger.debug(
                            f"候选更新 模板={name} 综合得分={combined_score:.4f} "
                            f"灰度={similarity_gray:.4f} 颜色={color_score:.4f} 边缘={edge_score:.4f} "
                            f"x={global_x} y={global_y} w={scaled_tw} h={scaled_th}"
                        )
                    best_score_for_template = combined_score
                    best_box_for_template = _create_box(global_x, global_y, scaled_tw, scaled_th, name)
        if best_box_for_template is not None:
            template_score_threshold = float(params.get("score_threshold", 0.67))
            if best_score_for_template < template_score_threshold:
                logger.debug(
                    f"模板匹配得分低于阈值 名称={name} 最佳得分={best_score_for_template:.4f} "
                    f"阈值={template_score_threshold:.2f}"
                )
                continue
            logger.debug(
                f"模板匹配成功 名称={name} 最佳得分={best_score_for_template:.4f} "
                f"位置={best_box_for_template}"
            )
            return best_box_for_template, name, best_score_for_template
        logger.debug(f"模板未匹配到 名称={name}")
    return None, None, 0.0

# 使用的颜色匹配，匹配颜色最接近的色块
def match_icon_special_symbols(
    box: Box,
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]],
    frame_bgr: np.ndarray,
    scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2),
    max_candidates_per_scale: int = 8,
) -> Tuple[Optional[Box], Optional[str], float]:
    if not icon_templates:
        return None, None, 0.0
    templates_seq = list(_normalize_templates(icon_templates))
    if not templates_seq:
        return None, None, 0.0
    frame_bgr = _ensure_bgr(frame_bgr)
    screenshot_bgr = box.crop_frame(frame_bgr)
    if screenshot_bgr is None or screenshot_bgr.size == 0:
        return None, None, 0.0
    screenshot_bgr = _ensure_bgr(screenshot_bgr)
    screenshot_hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
    h_map, s_map, v_map = cv2.split(screenshot_hsv)
    best_box: Optional[Box] = None
    best_name: Optional[str] = None
    best_score: float = 0.0
    for name, template, params in templates_seq:
        template_bgr = _ensure_bgr(template)
        template_hsv = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)
        th, tw = template_hsv.shape[:2]
        if th < 3 or tw < 3:
            continue
        for scale in scales:
            if scale <= 0:
                continue
            w = int(max(3, round(tw * scale)))
            h = int(max(3, round(th * scale)))
            if w > screenshot_hsv.shape[1] or h > screenshot_hsv.shape[0]:
                continue
            tpl_h_mean = float(np.mean(template_hsv[:, :, 0]))
            tpl_s_mean = float(np.mean(template_hsv[:, :, 1]))
            tpl_v_mean = float(np.mean(template_hsv[:, :, 2]))
            mean_h = cv2.blur(h_map, (w, h))
            mean_s = cv2.blur(s_map, (w, h))
            mean_v = cv2.blur(v_map, (w, h))
            dh_raw = np.abs(mean_h.astype(np.float32) - tpl_h_mean)
            dh = np.minimum(dh_raw, 180.0 - dh_raw) / 90.0
            ds = np.abs(mean_s.astype(np.float32) - tpl_s_mean) / 255.0
            dv = np.abs(mean_v.astype(np.float32) - tpl_v_mean) / 255.0
            dist = np.sqrt(dh * dh + ds * ds + dv * dv)
            score_map = 1.0 - np.clip(dist, 0.0, 1.0)
            cx_min = h // 2
            cy_min = w // 2
            cx_max = screenshot_hsv.shape[0] - (h - h // 2)
            cy_max = screenshot_hsv.shape[1] - (w - w // 2)
            valid = score_map[cx_min:cx_max, cy_min:cy_max]
            if valid.size == 0:
                continue
            idx = np.unravel_index(np.argmax(valid), valid.shape)
            cx = idx[0] + cx_min
            cy = idx[1] + cy_min
            x0 = int(np.clip(cy - w // 2, 0, screenshot_hsv.shape[1] - w))
            y0 = int(np.clip(cx - h // 2, 0, screenshot_hsv.shape[0] - h))
            x1 = x0 + w
            y1 = y0 + h
            score = float(valid[idx])
            threshold = float(params.get("score_threshold", 0.6))
            if score >= threshold and score > best_score:
                best_score = score
                best_box = _create_box(box.x + x0, box.y + y0, w, h, name)
                best_name = name
    if best_box is None or best_name is None:
        return None, None, 0.0
    return best_box, best_name, best_score
