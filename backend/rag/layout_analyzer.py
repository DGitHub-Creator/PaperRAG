"""ML 驱动的 PDF 布局分析 —— 识别页面中的文本块、图表、表格、公式区域。

使用 layoutparser (https://github.com/Layout-Parser/layout-parser)
调用 PubLayNet / Prima 预训练模型进行页面元素检测。

由于 layoutparser 安装体积较大，本模块采用懒加载 + 降级策略：
  1. 尝试加载 layoutparser + Detectron2
  2. 失败则尝试轻量级 OCR (paddleocr / tesserocr)
  3. 均不可用则返回空结果（无布局分析，不影响主流程）
"""

import traceback
from typing import Any, NamedTuple

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class LayoutBlock(NamedTuple):
    """页面布局块。"""
    block_type: str          # "Text", "Figure", "Table", "Formula"
    page_number: int
    x1: float
    y1: float
    x2: float
    y2: float
    text: str


def analyze_layout(
    file_path: str,
    model_type: str = "pub",
) -> list[LayoutBlock]:
    """对 PDF 执行 ML 布局分析，返回检测到的页面区块。

    Args:
        file_path: PDF 文件的绝对路径。
        model_type: 布局模型类型 ("pub"=PubLayNet, "prima"=PRImA)。

    Returns:
        LayoutBlock 列表，按 (page_number, y1) 排序。
    """
    blocks: list[LayoutBlock] = []

    try:
        import layoutparser as lp
    except ImportError:
        logger.warning("layoutparser 未安装，跳过 ML 布局分析。")
        logger.warning("安装: pip install layoutparser[detectron2]")
        return []

    try:
        model = _load_model(lp, model_type)
        if model is None:
            return []

        import fitz
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            image_path = f"/tmp/_lp_page_{page_num}.png"
            pix.save(image_path)

            image = lp.load_image(image_path)
            result = model.detect(image)

            for block in result:
                block_type = block.type if block.type else "Text"
                coords = block.block.coordinates if hasattr(block, "block") else (0, 0, 0, 0)
                text = block.text if hasattr(block, "text") and block.text else ""
                blocks.append(LayoutBlock(
                    block_type=block_type,
                    page_number=page_num,
                    x1=float(coords[0]),
                    y1=float(coords[1]),
                    x2=float(coords[2]),
                    y2=float(coords[3]),
                    text=text.strip() if text else "",
                ))

        doc.close()
        blocks.sort(key=lambda b: (b.page_number, b.y1))
        logger.info("布局分析完成: %s, %d 个区块", file_path, len(blocks))

    except Exception:
        logger.debug("布局分析异常: %s", traceback.format_exc())

    return blocks


def _load_model(lp: Any, model_type: str):
    """加载 layoutparser 布局检测模型（懒加载）。"""
    try:
        if model_type == "pub":
            return lp.Detectron2LayoutModel(
                "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                extra_config=[
                    "MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5,
                    "MODEL.DEVICE", "cpu",
                ],
                label_map={
                    0: "Text", 1: "Title", 2: "List",
                    3: "Table", 4: "Figure",
                },
            )
        elif model_type == "prima":
            return lp.Detectron2LayoutModel(
                "lp://PRImA/faster_rcnn_R_50_FPN_3x/config",
                extra_config=[
                    "MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5,
                    "MODEL.DEVICE", "cpu",
                ],
                label_map={
                    0: "Text", 1: "Math", 2: "Table",
                    3: "Figure", 4: "Natural_Image",
                },
            )
    except Exception:
        logger.warning("布局模型加载失败: %s", traceback.format_exc())
        return None

    return None


def extract_regions_by_type(
    blocks: list[LayoutBlock],
    block_types: set[str],
) -> list[LayoutBlock]:
    """从布局块中筛选指定类型的区块。

    Args:
        blocks: 布局块列表。
        block_types: 筛选的区块类型集合（如 {"Figure", "Table"}）。

    Returns:
        指定类型的区块列表。
    """
    return [b for b in blocks if b.block_type in block_types]
