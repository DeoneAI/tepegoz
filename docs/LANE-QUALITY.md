# Day 7 lane-quality acceptance protocol

Status: **evidence pending**. Classical and pretrained inference, per-module timing and confidence availability are implemented. The rendering fixes enforce the documented gates. They do not complete temporal continuity, false-marking or phone-domain evaluation automatically.

The assignment does not prescribe a sample count or numerical pass threshold. Declare a review scope and decision criteria before interpreting the results; do not invent a completion percentage from confidence availability.

## 1. Declare the sample

Record source/license, file hash, original frame indices, timestamps, stride, model hashes, code revision and parameters. Include representative marked/curved roads, shade/weak markings and day/night conditions when available. Use consecutive temporal windows rather than disconnected still images for continuity. Record the reviewer and review date.

If a required condition is unavailable, label it **not evaluated**. Six day/night/snow stills are qualitative examples; they cannot demonstrate nighttime temporal continuity. Public footage and actual phone footage must retain separate source labels.

## 2. Inspect expected and rendered geometry

For each reviewed frame record whether true left/right boundaries are visible, whether the model supplies a boundary/centerline, whether it follows the correct marking, and whether a false/non-lane marking was selected. A missing true marking is different from a correctly withheld estimate in an unobservable scene.

Suggested review columns:

```text
source,frame_index,timestamp_ns,condition,method,reviewer,
left_visible,right_visible,left_correct,right_correct,
centerline_present,centerline_correct,false_marking_count,confidence,notes
```

Human correctness labels must come from inspection or annotations, not confidence. Document exclusions and ambiguous cases rather than silently counting them as correct.

## 3. Inspect temporal behavior

Report missing-output fractions and consecutive missing intervals for the declared windows. Compare centerline/boundary changes at consistent image rows, normalize pixel displacement if needed, and preserve elapsed time across stride gaps. Large output changes may be real camera/road motion; inspect them before labeling discontinuities.

Do not label confidence-based availability as temporal continuity. Do not report calibrated vehicle offset or lane-departure accuracy from uncalibrated image geometry.

## 4. Confirm renderer behavior

- Below confidence 0.4, no lane boundary/centerline/corridor geometry is displayed; raw estimates remain in JSONL.
- At confidence 0.4 or above, geometry may be displayed.
- Below confidence 0.6, no lane-offset indicator is displayed.
- At confidence 0.6 or above, a known left/right/centered indicator requires a valid corridor and centerline, and is explicitly labeled image-space/uncalibrated.
- Missing, invalid and incomplete geometry must not create an indicator.

Automated renderer tests verify these rules, not the visual correctness of model predictions on roads.

## 5. Hand back the evidence

Retain the scoped review table, aggregate quality findings by condition/method, inference timings, representative indexed success/failure overlays and unresolved cases. Keep private/third-party imagery local unless redistribution is permitted; hashes and source indices still identify the reviewed inputs.

Only close the Day 7 quality checkbox when this evidence has been reviewed. The narrower public-data index/log functional gate and the original recorded-phone-footage outcome remain distinct acceptance statements.
