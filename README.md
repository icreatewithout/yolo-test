# River Dead Fish Monitoring (YOLO Industrial Pipeline)

工业级河道死鱼监控系统完整打包方案：支持公开数据下载、自动伪标注、YOLOv8训练、视频推理+跟踪、实时统计与可选Web面板。

## 1. 项目结构

```text
river_dead_fish_monitoring/
├── dataset/
│   ├── images/{train,val}
│   └── labels/{train,val}
├── videos/
├── auto_label/auto_label.py
├── download_data/download_datasets.py
├── train/train_yolov8.py
├── inference/{infer_video.py,tracker.py}
├── web_dashboard/{app.py,templates/index.html}
├── data.yaml
├── requirements.txt
└── README.md
```

## 2. 环境安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 下载公开数据

```bash
python download_data/download_datasets.py --datasets risid
# 或多个
python download_data/download_datasets.py --datasets risid deepfish plitter
```

下载后建议将可用样本统一整理为 YOLO 目录结构：
- `dataset/images/train`
- `dataset/labels/train`
- `dataset/images/val`
- `dataset/labels/val`

## 4. 自动伪标注

将河道视频放入 `videos/river.mp4` 后执行：

```bash
python auto_label/auto_label.py \
  --video videos/river.mp4 \
  --images-dir dataset/images/train \
  --labels-dir dataset/labels/train \
  --interval 10 \
  --model yolov8n.pt
```

> 建议后续人工复核并区分类别：`dead_fish`、`live_fish`、`floating_object`。

## 5. 训练 YOLOv8

```bash
python train/train_yolov8.py \
  --weights yolov8n.pt \
  --data data.yaml \
  --epochs 100 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --name river_dead_fish
```

## 6. 视频推理 + 跟踪 + 统计

```bash
python inference/infer_video.py \
  --video videos/river.mp4 \
  --weights train/runs/detect/river_dead_fish/weights/best.pt \
  --output results/output.mp4 \
  --show
```

输出：
- 带目标ID轨迹的视频
- 每帧统计（死鱼/活鱼/漂浮物）叠加显示

## 7. Web 监控（可选）

```bash
python web_dashboard/app.py
```

浏览器访问 `http://localhost:8000`。

## 8. 工业级优化建议

- 小目标增强：Mosaic、Copy-Paste、CutMix
- 轨迹与速度联合判别漂浮物和死鱼
- 多摄像头同河段融合（ReID + 时空同步）
- 边缘设备实时推理 + 云端集中告警
- 阈值报警：连续N帧死鱼数 > 阈值触发
