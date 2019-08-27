import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
from typing import List

pred_out_w, pred_out_h = 128, 128


def draw_rectangle(box_and_score, img, color):
    number_of_rect = np.minimum(500, len(box_and_score))

    for i in reversed(list(range(number_of_rect))):
        top, left, bottom, right = box_and_score[i, :]

        top = np.floor(top + 0.5).astype('int32')
        left = np.floor(left + 0.5).astype('int32')
        bottom = np.floor(bottom + 0.5).astype('int32')
        right = np.floor(right + 0.5).astype('int32')

        draw = ImageDraw.Draw(img)

        thickness = 4
        if color == "red":
            rect_color = (255, 0, 0)
        elif color == "blue":
            rect_color = (0, 0, 255)
        else:
            rect_color = (0, 0, 0)

        if i == 0:
            thickness = 4
        for j in range(2 * thickness):  # Disegna diversi strati perchè è sottile
            draw.rectangle([left + j, top + j, right - j, bottom - j],
                           outline=rect_color)

    del draw
    return img


def check_iou_score(true_boxes, detected_boxes, iou_thresh):
    iou_all = []
    for detected_box in detected_boxes:
        y1 = np.maximum(detected_box[0], true_boxes[:, 0])
        x1 = np.maximum(detected_box[1], true_boxes[:, 1])
        y2 = np.minimum(detected_box[2], true_boxes[:, 2])
        x2 = np.minimum(detected_box[3], true_boxes[:, 3])

        cross_section = np.maximum(0, y2 - y1) * np.maximum(0, x2 - x1)
        all_area = (detected_box[2] - detected_box[0]) * (detected_box[3] - detected_box[1]) + (
                true_boxes[:, 2] - true_boxes[:, 0]) * (true_boxes[:, 3] - true_boxes[:, 1])
        iou = np.max(cross_section / (all_area - cross_section))
        # argmax=np.argmax(cross_section/(all_area-cross_section))
        iou_all.append(iou)
    score = 2 * np.sum(iou_all) / (len(detected_boxes) + len(true_boxes))
    print("score:{}".format(np.round(score, 3)))
    return score


#################################################################


def get_bb_boxes(predictions: np.ndarray, annotation_list: np.array, print: bool = False) \
        -> List[np.array]:
    """
    Compute the bounding boxes and perform non maximum supression
    :param predictions: array of predictions with shape (batch, out_width, out_height, n_cat + 4)
    :param annotation_list: list o samples where:
            - annotation_list[0] = path to image
            - annotation_list[1] = annotations, as np.array
            - annotation_list[2] = recommended height split
            - annotation_list[3] = recommended width split
    :param print: whether to show bboxes and iou scores
    :return: list of boxes, as [image_path,category,score,ymin,xmin,ymax,xmax].
            Category is always 0 in our case.
    """
    all_boxes = []
    for i in np.arange(0, predictions.shape[0]):
        img = Image.open(annotation_list[i][0]).convert("RGB")
        width, height = img.size

        box_and_score = boxes_for_image(predictions[i], 1, score_thresh=0.3, iou_thresh=0.4)

        if len(box_and_score) == 0:
            continue

        true_boxes = annotation_list[i][1][:, 1:]  # c_x,c_y,width_height
        top = true_boxes[:, 1:2] - true_boxes[:, 3:4] / 2
        left = true_boxes[:, 0:1] - true_boxes[:, 2:3] / 2
        bottom = top + true_boxes[:, 3:4]
        right = left + true_boxes[:, 2:3]
        true_boxes = np.concatenate((top, left, bottom, right), axis=1)

        heatmap = predictions[i, :, :, 0]

        print_w, print_h = img.size
        # resize predicted box to original size. Leave unchanged score, category
        box_and_score = box_and_score * [1, 1, print_h / pred_out_h, print_w / pred_out_w,
                                         print_h / pred_out_h, print_w / pred_out_w]

        # Add a field for image path to each box
        image_path = np.full((box_and_score.shape[0], 1), annotation_list[i][0])
        box_and_score = np.concatenate((image_path, box_and_score), axis=1)

        all_boxes.append(box_and_score)

        if print:
            check_iou_score(true_boxes, box_and_score[:, 3:].astype(np.float32), iou_thresh=0.5)
            img = draw_rectangle(box_and_score[:, 3:].astype(np.float32), img, "red")
            img = draw_rectangle(true_boxes, img, "blue")

            fig, axes = plt.subplots(1, 2, figsize=(15, 15))
            axes[0].imshow(img)
            axes[1].imshow(heatmap)
            plt.show()

    return all_boxes


# Originally NMS_all
def boxes_for_image(predicts, category_n, score_thresh, iou_thresh):
    y_c = predicts[..., category_n] + np.arange(pred_out_h).reshape(-1, 1)
    x_c = predicts[..., category_n + 1] + np.arange(pred_out_w).reshape(1, -1)
    height = predicts[..., category_n + 2] * pred_out_h
    width = predicts[..., category_n + 3] * pred_out_w

    count = 0
    # Well, in our case category_n = 1, so category=0 (just one cycle)
    for category in range(category_n):
        predict = predicts[..., category]
        mask = (predict > score_thresh)

        # If no center is predicted with enough confidence
        if not mask.all:
            continue
        box_and_score = boxes_image_nms(predict[mask], y_c[mask], x_c[mask], height[mask], width[mask],
                                        iou_thresh)
        box_and_score = np.insert(box_and_score, 0, category,
                                  axis=1)  # category,score,ymin,xmin,ymax,xmax
        if count == 0:
            box_and_score_all = box_and_score
        else:
            box_and_score_all = np.concatenate((box_and_score_all, box_and_score), axis=0)
        count += 1

    # Get indexes to sort by score descending order
    score_sort = np.argsort(box_and_score_all[:, 1])[::-1]
    box_and_score_all = box_and_score_all[score_sort]

    # If there are more than one box starting at same coordinate (ymin) remove it
    _, unique_idx = np.unique(box_and_score_all[:, 2], return_index=True)
    # Sorted preserves original order of boxes
    return box_and_score_all[sorted(unique_idx)]


# Originally: NMS
def boxes_image_nms(score, y_c, x_c, height, width, iou_thresh, merge_mode=False):
    if merge_mode:
        score = score
        ymin = y_c
        xmin = x_c
        ymax = height
        xmax = width
    else:
        # flatten
        score = score.reshape(-1)
        y_c = y_c.reshape(-1)
        x_c = x_c.reshape(-1)
        height = height.reshape(-1)
        width = width.reshape(-1)
        size = height * width

        xmin = x_c - width / 2  # left
        ymin = y_c - height / 2  # top
        xmax = x_c + width / 2  # right
        ymax = y_c + height / 2  # bottom

        inside_pic = (ymin > 0) * (xmin > 0) * (ymax < pred_out_h) * (xmax < pred_out_w)
        # outside_pic = len(inside_pic) - np.sum(inside_pic)

        normal_size = (size < (np.mean(size) * 10)) * (size > (np.mean(size) / 10))
        score = score[inside_pic * normal_size]
        ymin = ymin[inside_pic * normal_size]
        xmin = xmin[inside_pic * normal_size]
        ymax = ymax[inside_pic * normal_size]
        xmax = xmax[inside_pic * normal_size]

    # Sort boxes in descending order
    score_sort = np.argsort(score)[::-1]
    score = score[score_sort]
    ymin = ymin[score_sort]
    xmin = xmin[score_sort]
    ymax = ymax[score_sort]
    xmax = xmax[score_sort]

    area = ((ymax - ymin) * (xmax - xmin))

    boxes = np.concatenate((score.reshape(-1, 1), ymin.reshape(-1, 1), xmin.reshape(-1, 1),
                            ymax.reshape(-1, 1), xmax.reshape(-1, 1)), axis=1)

    # Non maximum suppression
    box_idx = np.arange(len(ymin))
    alive_box = []
    while len(box_idx) > 0:

        # Take first index (of best bbox)
        alive_box.append(box_idx[0])

        y1 = np.maximum(ymin[0], ymin)
        x1 = np.maximum(xmin[0], xmin)
        y2 = np.minimum(ymax[0], ymax)
        x2 = np.minimum(xmax[0], xmax)

        cross_h = np.maximum(0, y2 - y1)
        cross_w = np.maximum(0, x2 - x1)
        still_alive = (((cross_h * cross_w) / area[0]) < iou_thresh)
        if np.sum(still_alive) == len(box_idx):
            print("error")
            print(np.max((cross_h * cross_w)), area[0])
        ymin = ymin[still_alive]
        xmin = xmin[still_alive]
        ymax = ymax[still_alive]
        xmax = xmax[still_alive]
        area = area[still_alive]
        box_idx = box_idx[still_alive]

    return boxes[alive_box]  # score,top,left,bottom,right

######################################################
##############  #THINGS I TRIED ###################
######################################################


# def visualize_heatmap(img: np.array, heatmap: np.array):
#     gaussian = heatmap[:, :, 0]
#     centers = heatmap[:, :, 1]
#     fig, axes = plt.subplots(1, 3, figsize=(15, 15))
#     axes[0].set_axis_off()
#     axes[0].imshow(img)
#     axes[1].set_axis_off()
#     axes[1].imshow(gaussian)
#     axes[2].set_axis_off()
#     axes[2].imshow(centers)
#     plt.show()


# def infer_bounding_box(predicts, category_n, score_thresh) -> np.array:
#     y_c = predicts[..., category_n] + np.arange(pred_out_h).reshape(-1, 1)
#     x_c = predicts[..., category_n + 1] + np.arange(pred_out_w).reshape(1, -1)
#     height = predicts[..., category_n + 2] * pred_out_h
#     width = predicts[..., category_n + 3] * pred_out_w
#     score = predicts[..., 0]
#
#     mask = (score > score_thresh)
#
#     y_c = y_c[mask].reshape(-1)
#     x_c = x_c[mask].reshape(-1)
#     height = height[mask].reshape(-1)
#     width = width[mask].reshape(-1)
#     score = score[mask].reshape(-1)
#     size = height * width  # ??
#
#     xmin = x_c - width / 2  # left
#     ymin = y_c - height / 2  # top
#     xmax = x_c + width / 2  # right
#     ymax = y_c + height / 2  # bottom
#
#     inside_pic = (ymin > 0) * (xmin > 0) * (ymax < pred_out_h) * (xmax < pred_out_w)
#     outside_pic = len(inside_pic) - np.sum(inside_pic)
#
#     normal_size = (size < (np.mean(size) * 10)) * (size > (np.mean(size) / 10))
#     score = score[inside_pic * normal_size]
#     xmin = xmin[inside_pic * normal_size]
#     xmax = xmax[inside_pic * normal_size]
#     ymin = ymin[inside_pic * normal_size]
#     ymax = ymax[inside_pic * normal_size]
#
#     boxes = np.concatenate((
#         score.reshape(-1, 1),
#         ymin.reshape(-1, 1),
#         xmin.reshape(-1, 1),
#         ymax.reshape(-1, 1),
#         xmax.reshape(-1, 1)), axis=1)
#     # box: score, ymin, xmin, ymax, xmax
#     return boxes

# count = 0
# all_boxes_and_score = []
# for category in range(category_n):
#     predict = predicts[..., category]
#     mask = (predict > score_thresh)
#     # print("box_num",np.sum(mask))
#     if not mask.all():
#         continue
#
#     box_and_score = nms(predict[mask], y_c[mask], x_c[mask], height[mask], width[mask])
#
#     # Add format: category,score,top,left,bottom,right
#     box_and_score = np.insert(box_and_score, 0, category, axis=1)
#
#     all_boxes_and_score.append(box_and_score)
#     count += 1
#
# all_boxes_and_score = np.array(all_boxes_and_score)
#
# # Sort over score, descending order
# sorted_indexes = np.argsort(all_boxes_and_score[:, 1])[::-1]
# box_and_score_all = all_boxes_and_score[sorted_indexes]
#
# _, unique_idx = np.unique(box_and_score_all[:, 2], return_index=True)
# # print(unique_idx)
# return box_and_score_all[sorted(unique_idx)]


# def UpSampling2DBilinear(size):
#     return Lambda(lambda x: image.resize_bilinear(x, size, align_corners=True))
#
#
# def nms(predicts):
#     pooled = MaxPooling2D((3, 3), padding='same')(predicts)
#     upsampled = UpSampling2DBilinear((pred_out_w, pred_out_h))(pooled)
#     res = upsampled.numpy()
#     return res


# def print_bboxes(predictions, ann_list):
#     nms_predictions = nms(predictions[..., 0])
#     predictions[..., 0] = nms_predictions
#
#     for prediction, ann in zip(predictions, ann_list):
#         # print(cv_list[i][2:])
#         img = Image.open(ann[0]).convert("RGB")
#         width, height = img.size
#
#         box_and_score = infer_bounding_box(prediction, 1, score_thresh=0.3)
#
#         # print("after NMS",len(box_and_score))
#         if len(box_and_score) == 0:
#             continue
#
#         true_boxes = ann_list[i][1][:, 1:]  # c_x,c_y,width_height
#         top = true_boxes[:, 1:2] - true_boxes[:, 3:4] / 2
#         left = true_boxes[:, 0:1] - true_boxes[:, 2:3] / 2
#         bottom = top + true_boxes[:, 3:4]
#         right = left + true_boxes[:, 2:3]
#         true_boxes = np.concatenate((top, left, bottom, right), axis=1)
#
#         heatmap = prediction[:, :, 0]
#
#         print_w, print_h = img.size
#
#         # resize predicted box to original size
#         box_and_score = box_and_score * [1, print_h / pred_out_h, print_w / pred_out_w,
#                                          print_h / pred_out_h, print_w / pred_out_w]
#
#         # check_iou_score(true_boxes, box_and_score[:, 2:], iou_thresh=0.5)
#         img = draw_rectangle(box_and_score[:, 1:], img, "red")
#         img = draw_rectangle(true_boxes, img, "blue")
#
#         fig, axes = plt.subplots(1, 2, figsize=(15, 15))
#         # axes[0].set_axis_off()
#         axes[0].imshow(img)
#         # axes[1].set_axis_off()
#         axes[1].imshow(heatmap)  # , cmap='gray')
#         # axes[2].set_axis_off()
#         # axes[2].imshow(heatmap_1)#, cmap='gray')
#         plt.show()
