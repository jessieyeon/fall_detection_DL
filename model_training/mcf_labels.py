"""MCF (Multiple Cameras Fall) annotation from technicalReport.pdf, scenarios 1-22.
FALLS[scenario] = list of (start, end) frame intervals with position code 2 (falling),
in the REFERENCE camera's frame numbers. DELAYS[scenario][cam-1] = frame delay per camera.
REF_CAM values as printed in the report (11/10 are ambiguous prints; onset is refined
per-camera from the pose signal anyway, using a +-search window around the annotation)."""

FALLS = {
    1: [(1080, 1108)], 2: [(375, 399)], 3: [(591, 625)],
    4: [(288, 314), (601, 638)], 5: [(311, 336)], 6: [(583, 629)],
    7: [(476, 507)], 8: [(271, 298)], 9: [(628, 651)],
    10: [(512, 530)], 11: [(464, 489)], 12: [(605, 653)],
    13: [(823, 863)], 14: [(989, 1023)], 15: [(755, 787)],
    16: [(891, 940)], 17: [(730, 770)], 18: [(571, 601)],
    19: [(499, 600)], 20: [(545, 672)], 21: [(864, 901)],
    22: [(767, 808)],
}

REF_CAM = {1: 1, 2: 4, 3: 1, 4: 6, 5: 1, 6: 1, 7: 6, 8: 4, 9: 1, 10: 1,
           11: 7, 12: 1, 13: 4, 14: 6, 15: 1, 16: 4, 17: 6, 18: 6, 19: 1,
           20: 1, 21: 1, 22: 1}

DELAYS = {
    1:  [3, 3, 8, 4, 23, 6, 6, 0],
    2:  [25, 40, 0, 16, 18, 33, 33, 6],
    3:  [12, 16, 8, 16, 35, 20, 20, 0],
    4:  [72, 79, 78, 0, 68, 82, 83, 56],
    5:  [17, 24, 5, 11, 18, 26, 28, 0],   # report prints "18 7" merged; using 18
    6:  [0, 100, 106, 90, 89, 103, 104, 89],
    7:  [28, 14, 16, 0, 1, 17, 18, 20],
    8:  [92, 79, 0, 81, 64, 81, 82, 56],
    9:  [18, 9, 1, 19, 13, 11, 12, 0],
    10: [14, 15, 19, 33, 12, 17, 19, 0],
    11: [23, 4, 20, 14, 0, 6, 7, 12],
    12: [21, 6, 13, 8, 0, 3, 7, 0],
    13: [16, 33, 0, 7, 27, 27, 36, 13],
    14: [49, 36, 38, 0, 29, 29, 7, 14],
    15: [15, 19, 19, 15, 34, 40, 23, 0],
    16: [23, 29, 0, 2, 12, 9, 3, 3],
    17: [21, 26, 15, 0, 10, 0, 29, 18],
    18: [99, 105, 86, 0, 84, 108, 109, 77],
    19: [19, 27, 16, 19, 5, 29, 0, 20],
    20: [25, 9, 3, 10, 10, 4, 5, 0],
    21: [20, 30, 22, 3, 8, 33, 32, 0],
    22: [0, 46, 51, 41, 53, 46, 47, 34],
}


def fall_intervals_for_cam(scenario, cam):
    """Map annotated fall intervals (ref-camera frames) to camera `cam` frames."""
    ref = REF_CAM[scenario]
    d = DELAYS[scenario]
    shift = d[cam - 1] - d[ref - 1]
    return [(s + shift, e + shift) for s, e in FALLS[scenario]]
