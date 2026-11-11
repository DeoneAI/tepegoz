"""Turn measured throughput into a cloud cost estimate (planning numbers, not a quote).

cost per processed hour of video = instance $/h x (video fps / measured pipeline fps)
Use END-TO-END pipeline FPS measured ON THAT INSTANCE TYPE. Model-only FPS from
bench_inference.py understates cost because decode, NMS, tracking, depth and I/O are excluded.

  python scripts/estimate_cloud_cost.py --pricing configs/cloud_pricing.example.json \
      --pipeline-fps c7i.xlarge=9.5 --pipeline-fps g4dn.xlarge=60 --video-hours-per-month 40 --video-fps 30
"""
import argparse
import json


def estimate(pricing, measured, video_hours, video_fps, storage_gb):
    rows = []
    storage = storage_gb * pricing.get("s3_standard_usd_per_gb_month", 0)
    for name, fps in measured.items():
        instance = pricing["instances"][name]
        realtime_factor = video_fps / fps  # compute hours needed per hour of video
        compute_hours = video_hours * realtime_factor
        rows.append({"instance": name, "kind": instance["kind"], "usd_per_hour": instance["on_demand_usd_per_hour"],
                     "pipeline_fps": fps, "compute_hours_per_video_hour": round(realtime_factor, 3),
                     "batch_compute_usd_per_month": round(compute_hours * instance["on_demand_usd_per_hour"], 2),
                     "always_on_usd_per_month": round(730 * instance["on_demand_usd_per_hour"], 2),
                     "storage_usd_per_month": round(storage, 2), "can_keep_up_live": fps >= video_fps})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pricing", required=True)
    parser.add_argument("--pipeline-fps", action="append", required=True, help="instance=fps (end-to-end, measured)")
    parser.add_argument("--video-hours-per-month", type=float, default=20)
    parser.add_argument("--video-fps", type=float, default=30)
    parser.add_argument("--storage-gb", type=float, default=100)
    args = parser.parse_args()
    pricing = json.load(open(args.pricing, encoding="utf-8"))
    measured = {k: float(v) for k, v in (item.split("=", 1) for item in args.pipeline_fps)}
    print(json.dumps({"assumptions": {"video_hours_per_month": args.video_hours_per_month, "video_fps": args.video_fps, "storage_gb": args.storage_gb,
                                      "prices_checked": pricing.get("checked"), "region": pricing.get("region"),
                                      "excluded": ["data transfer out", "EBS volumes", "taxes", "engineering time"]},
                      "rows": estimate(pricing, measured, args.video_hours_per_month, args.video_fps, args.storage_gb)}, indent=2))


if __name__ == "__main__":
    main()
