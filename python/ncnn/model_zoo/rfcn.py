# Copyright 2020 Tencent
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
import ncnn
from .model_store import get_model_file
from ..utils.objects import Detect_Object


class RFCN:
    def __init__(
        self,
        target_size=224,
        max_per_image=100,
        confidence_thresh=0.6,
        nms_threshold=0.3,
        num_threads=1,
        use_gpu=False,
    ):
        self.target_size = target_size
        self.max_per_image = max_per_image
        self.confidence_thresh = confidence_thresh
        self.nms_threshold = nms_threshold
        self.num_threads = num_threads
        self.use_gpu = use_gpu

        self.mean_vals = [102.9801, 115.9465, 122.7717]
        self.norm_vals = []

        self.net = ncnn.Net()
        self.net.opt.use_vulkan_compute = self.use_gpu

        # original pretrained model from https://github.com/YuwenXiong/py-R-FCN
        # https://github.com/YuwenXiong/py-R-FCN/blob/master/models/pascal_voc/ResNet-50/rfcn_end2end/test_agnostic.prototxt
        # https://1drv.ms/u/s!AoN7vygOjLIQqUWHpY67oaC7mopf
        # resnet50_rfcn_final.caffemodel
        # the ncnn model https://github.com/nihui/ncnn-assets/tree/master/models
        self.net.load_param(get_model_file("rfcn_end2end.param"))
        self.net.load_model(get_model_file("rfcn_end2end.bin"))

        self.class_names = [
            "background",
            "aeroplane",
            "bicycle",
            "bird",
            "boat",
            "bottle",
            "bus",
            "car",
            "cat",
            "chair",
            "cow",
            "diningtable",
            "dog",
            "horse",
            "motorbike",
            "person",
            "pottedplant",
            "sheep",
            "sofa",
            "train",
            "tvmonitor",
        ]

    def __del__(self):
        self.net = None

    def __call__(self, img):
        h = img.shape[0]
        w = img.shape[1]

        scale = 1.0
        if w < h:
            scale = float(self.target_size) / w
            w = self.target_size
            h = h * scale
        else:
            scale = float(self.target_size) / h
            h = self.target_size
            w = w * scale

        mat_in = ncnn.Mat.from_pixels_resize(
            img,
            ncnn.Mat.PixelType.PIXEL_BGR,
            img.shape[1],
            img.shape[0],
            int(w),
            int(h),
        )
        mat_in.substract_mean_normalize(self.mean_vals, self.norm_vals)

        im_info = ncnn.Mat(3)
        im_info[0] = h
        im_info[1] = w
        im_info[2] = scale

        # step1, extract feature and all rois
        ex1 = self.net.create_extractor()
        ex1.set_num_threads(self.num_threads)
        ex1.input("data", mat_in)
        ex1.input("im_info", im_info)

        ret1, rfcn_cls = ex1.extract("rfcn_cls")
        ret2, rfcn_bbox = ex1.extract("rfcn_bbox")
        ret3, rois = ex1.extract("rois")  # all rois

        # step2, extract bbox and score for each roi
        class_candidates = []
        for i in range(rois.c):
            ex2 = self.net.create_extractor()

            roi = rois.channel(i)  # get single roi
            ex2.input("rfcn_cls", rfcn_cls)
            ex2.input("rfcn_bbox", rfcn_bbox)
            ex2.input("rois", roi)

            ret1, bbox_pred = ex2.extract("bbox_pred")
            ret2, cls_prob = ex2.extract("cls_prob")

            num_class = cls_prob.w
            while len(class_candidates) < num_class:
                class_candidates.append([])

            # find class id with highest score
            label = 0
            score = 0.0
            for j in range(num_class):
                class_score = cls_prob[j]
                if class_score > score:
                    label = j
                    score = class_score

            # ignore background or low score
            if label == 0 or score <= self.confidence_thresh:
                continue

            # fprintf(stderr, "%d = %f\n", label, score)

            # unscale to image size
            x1 = roi[0] / scale
            y1 = roi[1] / scale
            x2 = roi[2] / scale
            y2 = roi[3] / scale

            pb_w = x2 - x1 + 1
            pb_h = y2 - y1 + 1

            # apply bbox regression
            dx = bbox_pred[4]
            dy = bbox_pred[4 + 1]
            dw = bbox_pred[4 + 2]
            dh = bbox_pred[4 + 3]

            cx = x1 + pb_w * 0.5
            cy = y1 + pb_h * 0.5

            obj_cx = cx + pb_w * dx
            obj_cy = cy + pb_h * dy

            obj_w = pb_w * np.exp(dw)
            obj_h = pb_h * np.exp(dh)

            obj_x1 = obj_cx - obj_w * 0.5
            obj_y1 = obj_cy - obj_h * 0.5
            obj_x2 = obj_cx + obj_w * 0.5
            obj_y2 = obj_cy + obj_h * 0.5

            # clip
            obj_x1 = np.maximum(np.minimum(obj_x1, float(img.shape[1] - 1)), 0.0)
            obj_y1 = np.maximum(np.minimum(obj_y1, float(img.shape[0] - 1)), 0.0)
            obj_x2 = np.maximum(np.minimum(obj_x2, float(img.shape[1] - 1)), 0.0)
            obj_y2 = np.maximum(np.minimum(obj_y2, float(img.shape[0] - 1)), 0.0)

            # append object
            obj = Detect_Object()
            obj.rect.x = obj_x1
            obj.rect.y = obj_y1
            obj.rect.w = obj_x2 - obj_x1 + 1
            obj.rect.h = obj_y2 - obj_y1 + 1
            obj.label = label
            obj.prob = score

            class_candidates[label].append(obj)

        # post process
        objects = []
        for candidates in class_candidates:
            if len(candidates) == 0:
                continue

            candidates.sort(key=lambda obj: obj.prob, reverse=True)

            picked = self.nms_sorted_bboxes(candidates, self.nms_threshold)

            for j in range(len(picked)):
                z = picked[j]
                objects.append(candidates[z])

        objects.sort(key=lambda obj: obj.prob, reverse=True)

        objects = objects[: self.max_per_image]

        return objects

    def nms_sorted_bboxes(self, objects, nms_threshold):
        picked = []

        n = len(objects)

        areas = np.zeros((n,), dtype=np.float32)
        for i in range(n):
            areas[i] = objects[i].rect.area()

        for i in range(n):
            a = objects[i]

            keep = True
            for j in range(len(picked)):
                b = objects[picked[j]]

                # intersection over union
                inter_area = a.rect.intersection_area(b.rect)
                union_area = areas[i] + areas[picked[j]] - inter_area
                # float IoU = inter_area / union_area
                if inter_area / union_area > nms_threshold:
                    keep = False

            if keep:
                picked.append(i)

        return picked
